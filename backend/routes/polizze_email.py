"""Polizze da Email — whitelist mittenti + estrazione OCR automatica.

Flusso:
1. In Comunicazioni l'agenzia inserisce i mittenti da cui riceve i PDF delle polizze
   (campo `polizze_mittenti` in azienda_config).
2. In Posta, la scheda "Polizze" mostra SOLO le email di quei mittenti con allegati PDF.
3. "Estrai polizza" fa OCR dei PDF (Gemini) e crea Anagrafica + Polizza se non esistenti;
   se la polizza esiste già (stesso numero) allega il PDF senza duplicare.

Visibilità: admin + dipendente (NON collaboratori, che non vedono la casella di agenzia).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth import require_user
from database import db

logger = logging.getLogger(__name__)
router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _is_pdf(att: dict) -> bool:
    ct = (att.get("content_type") or "").lower()
    fn = (att.get("filename") or "").lower()
    return "pdf" in ct or fn.endswith(".pdf")


async def _whitelist() -> set[str]:
    az = await db.azienda_config.find_one({}, {"_id": 0, "polizze_mittenti": 1}) or {}
    return {(x or "").strip().lower() for x in (az.get("polizze_mittenti") or []) if (x or "").strip()}


@router.get("/email/polizze-inbox")
async def polizze_inbox(user: dict = Depends(require_user("admin", "dipendente"))) -> list[dict]:
    """Email dai mittenti whitelist CON allegato PDF."""
    wl = await _whitelist()
    if not wl:
        return []
    cursor = db.email_inbox.find(
        {"has_attachments": True}, {"_id": 0}
    ).sort("date", -1).limit(500)
    out: list[dict] = []
    async for em in cursor:
        if (em.get("from_address") or "").strip().lower() not in wl:
            continue
        pdfs = [a for a in (em.get("attachments") or []) if _is_pdf(a)]
        if not pdfs:
            continue
        out.append({
            "id": em.get("id"),
            "from_address": em.get("from_address"),
            "from_name": em.get("from_name"),
            "subject": em.get("subject"),
            "date": em.get("date"),
            "has_attachments": True,
            "attachments": pdfs,
            "polizze_estratte": bool(em.get("polizze_estratte")),
            "polizze_estratte_result": em.get("polizze_estratte_result") or [],
            "body_html": em.get("body_html"),
            "body_text": em.get("body_text"),
            "to_addresses": em.get("to_addresses") or [],
        })
    return out


async def _resolve_compagnia(nome: str | None) -> str:
    """Trova (o crea) la compagnia e ritorna il suo id."""
    from db_models import Compagnia
    nome = (nome or "").strip()
    if nome:
        comp = await db.compagnie.find_one(
            {"ragione_sociale": {"$regex": f"^{_re_escape(nome)}$", "$options": "i"}},
            {"_id": 0, "id": 1},
        )
        if not comp:
            comp = await db.compagnie.find_one(
                {"ragione_sociale": {"$regex": _re_escape(nome), "$options": "i"}},
                {"_id": 0, "id": 1},
            )
        if comp:
            return comp["id"]
    obj = Compagnia(
        codice=f"AUTO-{uuid.uuid4().hex[:6].upper()}",
        ragione_sociale=(nome or "DA VERIFICARE").upper(),
        descrizione="Creata automaticamente da OCR polizza email",
    )
    await db.compagnie.insert_one(obj.model_dump())
    return obj.id


def _re_escape(s: str) -> str:
    import re
    return re.escape(s)


async def _find_anagrafica(contraente: dict) -> dict | None:
    cf = (contraente.get("codice_fiscale") or "").strip().upper()
    piva = (contraente.get("partita_iva") or "").strip()
    rs = (contraente.get("cognome_nome_o_ragione_sociale") or "").strip().upper()
    if cf:
        a = await db.anagrafiche.find_one({"codice_fiscale": cf}, {"_id": 0})
        if a:
            return a
    if piva:
        a = await db.anagrafiche.find_one({"partita_iva": piva}, {"_id": 0})
        if a:
            return a
    if rs:
        a = await db.anagrafiche.find_one(
            {"ragione_sociale": {"$regex": f"^{_re_escape(rs)}$", "$options": "i"}}, {"_id": 0}
        )
        if a:
            return a
    return None


def _num(v):
    try:
        return float(v) if v not in (None, "", "null") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _map_frazionamento(v: str | None) -> str:
    v = (v or "").strip().lower()
    valid = {"annuale", "semestrale", "quadrimestrale", "trimestrale", "mensile", "unica"}
    return v if v in valid else "annuale"


async def _estrai_una(dati: dict, user: dict) -> dict:
    """Crea anagrafica+polizza (se non esistenti) dai dati OCR. Ritorna un riepilogo."""
    from routes.anagrafiche import create_anagrafica
    import server as _srv

    contr = dati.get("contraente") or {}
    # --- Anagrafica contraente ---
    ana = await _find_anagrafica(contr)
    ana_creata = False
    if not ana:
        ana_body = {
            "ragione_sociale": (contr.get("cognome_nome_o_ragione_sociale") or "").strip(),
            "codice_fiscale": (contr.get("codice_fiscale") or "").strip().upper() or None,
            "partita_iva": (contr.get("partita_iva") or "").strip() or None,
            "indirizzo": contr.get("indirizzo") or None,
            "comune": contr.get("comune") or None,
            "provincia": (contr.get("provincia") or "").strip().upper() or None,
            "cap": contr.get("cap") or None,
        }
        if not ana_body["ragione_sociale"]:
            raise HTTPException(400, "Contraente non leggibile dal PDF: impossibile creare anagrafica")
        ana = await create_anagrafica(body=ana_body, user=user)
        ana_creata = True
    ana_id = ana.get("id")

    # --- Compagnia ---
    compagnia_id = await _resolve_compagnia(dati.get("compagnia"))

    # --- Polizza ---
    numero = (dati.get("numero_polizza") or "").strip()
    pol = None
    if numero:
        pol = await db.polizze.find_one({"numero_polizza": numero}, {"_id": 0, "id": 1, "numero_polizza": 1})
    pol_creata = False
    if pol:
        pol_id = pol["id"]
    else:
        effetto = (dati.get("data_decorrenza") or dati.get("data_emissione") or _today())
        veicolo = dati.get("veicolo") or {}
        pol_body = {
            "numero_polizza": numero or f"DA-INSERIRE-{uuid.uuid4().hex[:6].upper()}",
            "compagnia_id": compagnia_id,
            "contraente_id": ana_id,
            "ramo": (dati.get("ramo") or "ALTRO").upper(),
            "prodotto": dati.get("prodotto") or None,
            "effetto": effetto,
            "scadenza": dati.get("data_scadenza") or None,
            "frazionamento": _map_frazionamento(dati.get("frazionamento")),
            "premio_lordo": _num(dati.get("premio_lordo_totale")),
            "premio_netto": _num(dati.get("premio_netto_totale")),
            "premio_tasse": _num(dati.get("imposte_totali")),
            "provvigioni": _num(dati.get("provvigioni_totali")),
            "targa": (veicolo.get("targa") or "").strip().upper() or None,
            "note": "Creata automaticamente da OCR polizza (email)",
        }
        if not pol_body["scadenza"]:
            pol_body.pop("scadenza")  # create_polizza la calcola da effetto+12m
        created = await _srv.create_polizza(body=pol_body, user=user)
        pol_id = created.get("id")
        pol_creata = True

    return {
        "numero_polizza": numero or None,
        "compagnia_id": compagnia_id,
        "polizza_id": pol_id,
        "polizza_creata": pol_creata,
        "anagrafica_id": ana_id,
        "anagrafica_nome": ana.get("ragione_sociale"),
        "anagrafica_creata": ana_creata,
    }


@router.post("/email/polizze-inbox/{eid}/estrai")
async def estrai_polizze(eid: str, user: dict = Depends(require_user("admin", "dipendente"))) -> dict:
    """OCR dei PDF dell'email → crea polizza+anagrafica (se non esistenti) + allega PDF."""
    import storage as obj_storage
    from ocr_polizza import estrai_dati_polizza
    from routes.documenti_inbox import _convert_pdf_to_jpeg
    from imap_poller import _copia_allegato_su_entita

    em = await db.email_inbox.find_one({"id": eid}, {"_id": 0})
    if not em:
        raise HTTPException(404, "Email non trovata")
    pdfs = [a for a in (em.get("attachments") or []) if _is_pdf(a)]
    if not pdfs:
        raise HTTPException(400, "Nessun allegato PDF nell'email")

    risultati: list[dict] = []
    for att in pdfs:
        voce: dict = {"filename": att.get("filename")}
        try:
            data, ctype = obj_storage.get_object(att["storage_path"])
            img_bytes, img_ct = await _convert_pdf_to_jpeg(data)
            dati = await estrai_dati_polizza(img_bytes, img_ct)
            esito = await _estrai_una(dati, user)
            voce.update(esito)
            # Allega il PDF alla polizza e all'anagrafica (idempotente)
            try:
                await _copia_allegato_su_entita(
                    db, att, entita_tipo="polizza", entita_id=esito["polizza_id"],
                    categoria="polizza", subject=em.get("subject") or "",
                )
                await _copia_allegato_su_entita(
                    db, att, entita_tipo="anagrafica", entita_id=esito["anagrafica_id"],
                    categoria="polizza", subject=em.get("subject") or "",
                )
            except Exception:
                logger.exception("Errore allegamento PDF polizza")
            voce["ok"] = True
        except HTTPException as he:
            voce["ok"] = False
            voce["errore"] = he.detail
        except Exception as e:  # noqa: BLE001
            logger.exception("Errore estrazione polizza da email %s", eid)
            voce["ok"] = False
            voce["errore"] = str(e)
        risultati.append(voce)

    await db.email_inbox.update_one(
        {"id": eid},
        {"$set": {"polizze_estratte": True, "polizze_estratte_result": risultati,
                  "polizze_estratte_at": _now_iso()}},
    )
    return {"ok": any(r.get("ok") for r in risultati), "risultati": risultati}
