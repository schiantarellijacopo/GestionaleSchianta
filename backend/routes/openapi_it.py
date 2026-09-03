"""OpenAPI.it router — endpoint per autocompilazione/scaricamento dati.

Endpoints (utenti tenant, salvano risultato su Anagrafica.openapi_data):
  POST /openapi-it/company/{aid}       → lookup camerale + salva
  POST /openapi-it/cadastre/{aid}      → immobili + salva
  POST /openapi-it/vehicles/{aid}      → veicoli + salva
  POST /openapi-it/visura/{aid}        → visura ordinaria + salva
  GET  /openapi-it/company?piva=...    → lookup diretto senza salvare (usato in autocomplete)
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from auth import current_user
from database import db, raw_db
from db_models import _now_iso
import openapi_it_service as svc


router = APIRouter(prefix="/openapi-it", tags=["openapi-it"])


async def _get_anagrafica(aid: str, user):
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(status_code=404, detail="Anagrafica non trovata")
    return ana


async def _update_openapi_field(aid: str, key: str, data) -> None:
    """Salva il risultato in Anagrafica.openapi_data.{key} (patch idempotente)."""
    await raw_db.anagrafiche.update_one(
        {"id": aid},
        {"$set": {
            f"openapi_data.{key}": data,
            "openapi_data.last_sync": _now_iso(),
            "updated_at": _now_iso(),
        }},
    )


@router.get("/company")
async def lookup_company(piva: str, user=Depends(current_user)) -> dict:
    """Lookup diretto per autocomplete P.IVA/CF (non salva su anagrafica)."""
    if not piva or len(piva) < 8:
        raise HTTPException(status_code=400, detail="P.IVA/CF non valido")
    return await svc.fetch_company(piva.strip())


@router.post("/company/{aid}")
async def fetch_company_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    ana = await _get_anagrafica(aid, user)
    key = ana.get("partita_iva") or ana.get("codice_fiscale")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza P.IVA/CF")
    data = await svc.fetch_company(key)
    await _update_openapi_field(aid, "company", data)
    return data


async def _save_allegato(aid: str, user, filename: str, content: bytes,
                         categoria: str, content_type: str = "application/pdf",
                         fonte: str = "openapi.it") -> Optional[str]:
    """Salva un file come Allegato standard (obj_storage + modello Allegato),
    così compare nel tab Allegati ed è scaricabile. Ritorna allegato_id."""
    import os
    import logging
    import storage as obj_storage
    from db_models import Allegato
    try:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
        file_id = str(__import__("uuid").uuid4())
        path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafica/{aid}/{file_id}.{ext}"
        result = obj_storage.put_object(path, content, content_type)
        obj = Allegato(
            entita_tipo="anagrafica", entita_id=aid,
            nome_file=filename, storage_path=result["path"],
            content_type=content_type, size=result.get("size", len(content)),
            descrizione=f"Documento {fonte}", autore_id=user.get("id"),
            categoria=categoria, visibile_cliente=False,
        )
        await db.allegati.insert_one(obj.model_dump())
        return obj.id
    except Exception as e:
        logging.getLogger(__name__).warning("Salvataggio allegato fallito: %s", e)
        return None


@router.post("/cadastre/{aid}")
async def fetch_cadastre_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    """Genera la visura catastale LIVE per il soggetto: estrae gli immobili
    strutturati (per il selettore di import) e salva il PDF ufficiale negli Allegati.
    NON inietta gli immobili: la scelta 'tutti o alcuni' avviene lato UI e poi
    viene chiamato /cadastre/{aid}/importa-immobili."""
    ana = await _get_anagrafica(aid, user)
    key = ana.get("codice_fiscale") or ana.get("partita_iva")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza CF/P.IVA")
    res = await svc.fetch_cadastre_detailed(key, want_pdf=True)
    allegato_id = None
    if res.get("pdf_bytes"):
        allegato_id = await _save_allegato(
            aid, user, res.get("pdf_filename") or f"visura_catastale_{key}.pdf",
            res["pdf_bytes"], "visura_catastale", "application/pdf", "openapi.it/catasto")
    immobili = res.get("immobili") or []
    await _update_openapi_field(aid, "cadastre", immobili)
    return {
        "count": len(immobili),
        "immobili": immobili,
        "soggetto": res.get("soggetto"),
        "provider": res.get("provider"),
        "message": res.get("message"),
        "pdf_salvato": bool(allegato_id),
        "allegato_id": allegato_id,
        "mock": res.get("mock", False),
    }


@router.post("/cadastre/{aid}/importa-immobili")
async def importa_immobili_catasto(aid: str, body: dict, user=Depends(current_user)) -> dict:
    """Aggiunge gli immobili selezionati all'Analisi Cliente (analisi_cliente.immobili).
    Body: {immobili: [ImmobileItem...]}"""
    from db_models import ImmobileItem
    await _get_anagrafica(aid, user)
    selected = body.get("immobili") or []
    if not selected:
        raise HTTPException(status_code=400, detail="Nessun immobile selezionato")
    ac = await db.analisi_cliente.find_one({"anagrafica_id": aid}, {"_id": 0})
    if not ac:
        ac = {"anagrafica_id": aid, "immobili": []}
        await db.analisi_cliente.insert_one({**ac, "created_at": _now_iso()})
    esistenti = list(ac.get("immobili") or [])
    # Dedup su foglio+particella+comune
    seen = {(str(i.get("foglio")), str(i.get("particella")), (i.get("comune") or "").upper())
            for i in esistenti}
    aggiunti = []
    for raw in selected:
        try:
            im = ImmobileItem(**raw).model_dump()
        except Exception:
            im = {k: raw.get(k) for k in raw}
        chiave = (str(im.get("foglio")), str(im.get("particella")), (im.get("comune") or "").upper())
        if chiave in seen and chiave != ("", "", ""):
            continue
        seen.add(chiave)
        esistenti.append(im)
        aggiunti.append(im)
    await db.analisi_cliente.update_one(
        {"anagrafica_id": aid},
        {"$set": {"immobili": esistenti, "updated_at": _now_iso()}},
    )
    return {"aggiunti": len(aggiunti), "totale": len(esistenti)}


@router.post("/vehicles/{aid}")
async def fetch_vehicles_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    ana = await _get_anagrafica(aid, user)
    key = ana.get("codice_fiscale") or ana.get("partita_iva")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza CF/P.IVA")
    data = await svc.fetch_vehicles(key)
    await _update_openapi_field(aid, "automotive", data)
    return {"count": len(data), "veicoli": data}


@router.post("/visura/{aid}")
async def fetch_visura_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    """Scarica la Visura camerale via OpenAPI.it Visengine.

    Ora supporta sia persona giuridica (P.IVA) sia persona fisica (CF) — Visengine
    espone documenti ufficiali anche per persone fisiche (categoria 'Person').

    Se la risposta include un `download_url` (PDF), il backend scarica il file
    e lo salva come `Allegato` legato all'anagrafica (categoria='visura_camerale').
    """
    ana = await _get_anagrafica(aid, user)
    # Accetta P.IVA (PG) o CF (PF)
    key = ana.get("partita_iva") or ana.get("codice_fiscale")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza P.IVA/CF")
    data = await svc.fetch_visura(key)

    # Se OpenAPI ha restituito un download_url PDF → scarica e salva come Allegato.
    dl = (data or {}).get("download_url")
    if dl and dl.startswith("http"):
        try:
            import httpx as _httpx
            import uuid as _uuid
            from storage_service import StorageService
            async with _httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                r = await client.get(dl)
            if r.status_code == 200 and r.content:
                filename = f"visura_{key}_{_now_iso()[:10]}.pdf"
                stored = await StorageService.put(
                    user=user, entita_tipo="anagrafica", entita_id=aid,
                    filename=filename, data=r.content,
                    content_type=r.headers.get("content-type", "application/pdf"),
                )
                allegato = {
                    "id": str(_uuid.uuid4()),
                    "entita_tipo": "anagrafica",
                    "entita_id": aid,
                    "anagrafica_id": aid,
                    "categoria": "visura_camerale",
                    "nome_file": filename,
                    "mime": "application/pdf",
                    "size": stored.get("size"),
                    "storage_path": stored.get("storage_path"),
                    "storage_provider": stored.get("storage_provider"),
                    "agenzia_tenant_id": stored.get("agenzia_tenant_id"),
                    "created_at": _now_iso(),
                    "created_by": user.get("id"),
                    "fonte": "openapi.it/visengine",
                }
                await raw_db.allegati.insert_one(allegato)
                data["allegato_id"] = allegato["id"]
                data["allegato_saved"] = True
        except Exception as e:
            data["allegato_error"] = str(e)[:200]

    await _update_openapi_field(aid, "visura", data)
    return data


@router.get("/status")
async def status(user=Depends(current_user)) -> dict:
    """Diagnostica per il frontend: modalità + credito residuo + env.

    Ritorna:
      {
        "mode": "live" | "mock",
        "has_credentials": bool,
        "env": "prod" | "sandbox",
        "credit_eur": float | null    # None se non disponibile
      }
    """
    from os import environ
    has_creds = svc.has_credentials()
    credit = None
    if has_creds:
        credit = await svc.get_credit()
    return {
        "mode": "live" if has_creds else "mock",
        "has_credentials": has_creds,
        "env": (environ.get("OPENAPI_IT_ENV") or "prod").lower(),
        "credit_eur": credit,
    }


# ============================================================
# SERVIZIO 5 · AUTOMOTIVE BY TARGA (con cache in db.veicoli)
# ============================================================
@router.get("/automotive-by-targa/{targa}")
async def lookup_targa(
    targa: str,
    force_refresh: bool = False,
    user=Depends(current_user),
) -> dict:
    """Cerca il veicolo per targa. Prima consulta la cache interna `db.veicoli`;
    se assente (o force_refresh=true) chiama OpenAPI.it Automotive e persiste
    il risultato nel DB interno per riuso a costo zero.

    Ritorna: {"veicolo": {...}, "fonte": "cache"|"openapi_live"|"openapi_mock"}
    """
    tk = (targa or "").upper().strip().replace(" ", "")
    if not tk or len(tk) < 5:
        raise HTTPException(400, "Targa non valida")

    if not force_refresh:
        cached = await db.veicoli.find_one({"targa": tk}, {"_id": 0})
        if cached:
            return {"veicolo": cached, "fonte": "cache"}

    data = await svc.fetch_automotive_by_targa(tk)
    fonte = "openapi_live" if "LIVE" in (data.get("provider") or "") else "openapi_mock"

    # Upsert nel DB interno (mantenendo eventuali campi custom già presenti)
    existing = await db.veicoli.find_one({"targa": tk}, {"_id": 0, "id": 1})
    payload = {
        "targa": tk,
        "marca": data.get("marca"),
        "modello": data.get("modello"),
        "allestimento": data.get("allestimento"),
        "cilindrata": data.get("cilindrata"),
        "potenza_kw": data.get("potenza_kw"),
        "potenza_cv": data.get("potenza_cv"),
        "alimentazione": data.get("alimentazione"),
        "anno_immatricolazione": data.get("anno_immatricolazione"),
        "data_immatricolazione": data.get("data_immatricolazione"),
        "scadenza_revisione": data.get("scadenza_revisione"),
        "telaio": data.get("telaio"),
        "categoria": data.get("categoria"),
        "euro": data.get("euro"),
        "updated_at": _now_iso(),
    }
    if existing:
        await raw_db.veicoli.update_one({"id": existing["id"]}, {"$set": payload})
        vid = existing["id"]
    else:
        import uuid
        payload["id"] = str(uuid.uuid4())
        payload["created_at"] = _now_iso()
        payload["fonte"] = fonte
        await db.veicoli.insert_one(payload)
        vid = payload["id"]

    fresh = await db.veicoli.find_one({"id": vid}, {"_id": 0})
    return {"veicolo": fresh, "fonte": fonte, "raw_openapi": data}


# ============================================================
# SERVIZIO 6 · RISK REPORT (affidabilità creditizia / protesti)
# ============================================================
@router.post("/risk/{aid}")
async def fetch_risk_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    ana = await _get_anagrafica(aid, user)
    key = ana.get("codice_fiscale") or ana.get("partita_iva")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza CF/P.IVA")
    data = await svc.fetch_risk(
        key,
        name=ana.get("nome") or "",
        surname=ana.get("cognome") or "",
        company_name=ana.get("ragione_sociale") or "",
    )
    await _update_openapi_field(aid, "risk", data)
    return data


# ============================================================
# Aggiunta veicolo/proprietario allo storico (persistente)
# ============================================================
@router.post("/veicoli/{vid}/associa-proprietario/{aid}")
async def associa_proprietario_veicolo(
    vid: str,
    aid: str,
    tipo_operazione: str = "acquisto",   # "acquisto" | "vendita" | "rottamazione" | "eredita"
    user=Depends(current_user),
) -> dict:
    """Associa un proprietario a un veicolo mantenendo lo storico.

    Aggiorna:
      - veicoli.proprietario_id (attuale)
      - veicoli.storico_proprietari (append record)
    """
    veicolo = await db.veicoli.find_one({"id": vid}, {"_id": 0})
    if not veicolo:
        raise HTTPException(404, "Veicolo non trovato")
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")

    nome = ana.get("ragione_sociale") or f"{ana.get('cognome','')} {ana.get('nome','')}".strip()
    new_entry = {
        "anagrafica_id": aid,
        "nome": nome,
        "tipo_operazione": tipo_operazione,
        "data": _now_iso()[:10],
        "utente_id": user.get("id"),
    }
    # Chiude il record precedente (se aperto)
    storico = veicolo.get("storico_proprietari") or []
    for rec in storico:
        if rec.get("data_fine") is None and rec.get("anagrafica_id") != aid:
            rec["data_fine"] = _now_iso()[:10]
    storico.append(new_entry)

    await raw_db.veicoli.update_one(
        {"id": vid},
        {"$set": {
            "proprietario_id": aid,
            "proprietario": nome,
            "storico_proprietari": storico,
            "updated_at": _now_iso(),
        }},
    )
    return {"ok": True, "storico": storico}



# ============================================================
# VISENGINE · Selettore documenti (Camerali / Patronato / INPS)
# ============================================================
@router.get("/visengine/catalog")
async def visengine_catalog(user=Depends(current_user)) -> dict:
    """Lista FISSA dei documenti disponibili, raggruppati per categoria."""
    items = svc.visengine_catalog()
    gruppi: dict[str, list] = {}
    for it in items:
        gruppi.setdefault(it["categoria"], []).append(it)
    return {"catalog": items, "gruppi": gruppi}


@router.get("/visengine/schema/{hash_visura}")
async def visengine_schema(hash_visura: str, aid: Optional[str] = None,
                           user=Depends(current_user)) -> dict:
    """Struttura campi del documento + valori suggeriti dall'anagrafica."""
    schema = await svc.visengine_get_schema(hash_visura)
    if not schema:
        raise HTTPException(status_code=502, detail="Impossibile leggere la struttura del documento")
    ana = {}
    if aid:
        ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0}) or {}
    return svc.visengine_schema_prefilled(schema, ana)


async def _save_visengine_richiesta(aid: str, record: dict) -> None:
    await raw_db.anagrafiche.update_one(
        {"id": aid},
        {"$push": {"openapi_data.visengine_richieste": record},
         "$set": {"openapi_data.last_sync": _now_iso(), "updated_at": _now_iso()}},
    )


@router.post("/visengine/request/{aid}")
async def visengine_request(aid: str, body: dict, user=Depends(current_user)) -> dict:
    """Crea una pratica Visengine per un documento.
    Body: {hash_visura, nome_visura, json_visura, opzioni?}
    Se la pratica è già pronta (sincrona) scarica e salva subito il PDF."""
    import uuid as _uuid
    await _get_anagrafica(aid, user)
    hash_visura = body.get("hash_visura")
    json_visura = body.get("json_visura") or {}
    if not hash_visura or not json_visura:
        raise HTTPException(status_code=400, detail="hash_visura e json_visura obbligatori")
    created = await svc.visengine_create_request(hash_visura, json_visura, body.get("opzioni"))
    if not created.get("ok"):
        raise HTTPException(status_code=400, detail=created.get("error") or "Errore Visengine")
    rid = created.get("id")
    record = {
        "id": str(_uuid.uuid4()),
        "richiesta_id": rid,
        "hash_visura": hash_visura,
        "nome_visura": body.get("nome_visura") or hash_visura,
        "stato": created.get("stato") or "in_lavorazione",
        "allegato_id": None,
        "created_at": _now_iso(),
        "created_by": user.get("id"),
    }
    # Tentativo di download immediato (documenti sincroni)
    if rid:
        import asyncio
        for _ in range(3):
            d = await svc.visengine_get_request(rid)
            if svc.visengine_is_ready(d.get("stato")):
                status, content, ctype = await svc.visengine_download(rid)
                if status == 200 and content:
                    fn = f"{record['nome_visura'].replace(' ', '_')}_{rid}.pdf"
                    aid_alleg = await _save_allegato(aid, user, fn, content,
                                                     "visengine", ctype or "application/pdf",
                                                     "openapi.it/visengine")
                    record["allegato_id"] = aid_alleg
                    record["stato"] = "evasa"
                break
            await asyncio.sleep(2.0)
    await _save_visengine_richiesta(aid, record)
    return record


@router.post("/visengine/refresh/{aid}/{record_id}")
async def visengine_refresh(aid: str, record_id: str, user=Depends(current_user)) -> dict:
    """Ricontrolla lo stato di una pratica Visengine e, se pronta, salva il PDF."""
    ana = await _get_anagrafica(aid, user)
    richieste = (ana.get("openapi_data") or {}).get("visengine_richieste") or []
    rec = next((r for r in richieste if r.get("id") == record_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    rid = rec.get("richiesta_id")
    if not rid:
        raise HTTPException(status_code=400, detail="Richiesta senza id remoto")
    d = await svc.visengine_get_request(rid)
    stato = d.get("stato") or rec.get("stato")
    allegato_id = rec.get("allegato_id")
    if svc.visengine_is_ready(stato) and not allegato_id:
        status, content, ctype = await svc.visengine_download(rid)
        if status == 200 and content:
            fn = f"{(rec.get('nome_visura') or 'documento').replace(' ', '_')}_{rid}.pdf"
            allegato_id = await _save_allegato(aid, user, fn, content,
                                               "visengine", ctype or "application/pdf",
                                               "openapi.it/visengine")
    # aggiorna il record
    await raw_db.anagrafiche.update_one(
        {"id": aid, "openapi_data.visengine_richieste.id": record_id},
        {"$set": {
            "openapi_data.visengine_richieste.$.stato": stato,
            "openapi_data.visengine_richieste.$.allegato_id": allegato_id,
            "updated_at": _now_iso(),
        }},
    )
    return {"id": record_id, "stato": stato, "allegato_id": allegato_id}
