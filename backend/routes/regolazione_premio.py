"""Regolazione Premio — sezione dedicata.

Gestisce l'intero ciclo delle polizze soggette a regolazione premio:
  - elenco polizze flaggate con scadenze e stato workflow
  - invio (manuale o pianificato) della lettera di richiesta dati al contraente
  - generazione del titolo di regolazione dal calcolo salvato
  - cambio stato manuale del workflow

Workflow stato (campo polizza.regolazione_stato):
  None/"da_richiedere" → "lettera_inviata" → "dati_ricevuti" → "calcolata" → "titolo_generato" → "chiusa"
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import Titolo, _now_iso
from shared import log_attivita, strip_mongo_id

router = APIRouter()


def _anag_nome(a: dict) -> str:
    if not a:
        return "—"
    return (a.get("ragione_sociale")
            or f"{a.get('cognome', '')} {a.get('nome', '')}".strip()
            or a.get("cognome_nome") or "—")


def _anag_indirizzo(a: dict) -> str:
    if not a:
        return ""
    parts = [a.get("indirizzo")]
    cap_citta = f"{a.get('cap', '')} {a.get('citta', '')} {('(' + a.get('provincia') + ')') if a.get('provincia') else ''}".strip()
    if cap_citta:
        parts.append(cap_citta)
    return "<br/>".join([p for p in parts if p])


def _data_invio_prevista(scadenza: Optional[str], giorni: int) -> Optional[str]:
    if not scadenza:
        return None
    try:
        return (date.fromisoformat(scadenza[:10]) + timedelta(days=int(giorni or 0))).isoformat()
    except (TypeError, ValueError):
        return None


# ============================================================================
# LISTA + STATS
# ============================================================================
@router.get("/regolazione-premio")
async def list_regolazioni(
    stato: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    """Elenco polizze soggette a regolazione premio, arricchite con
    contraente, compagnia, scadenza e data prevista invio lettera."""
    polizze = await db.polizze.find(
        {"regolazione_premio": True},
        {"_id": 0, "documenti": 0, "garanzie": 0, "addizionali": 0},
    ).to_list(2000)

    # Pre-carico anagrafiche e compagnie coinvolte
    contraente_ids = list({p.get("contraente_id") for p in polizze if p.get("contraente_id")})
    compagnia_ids = list({p.get("compagnia_id") for p in polizze if p.get("compagnia_id")})
    anags = {a["id"]: a async for a in db.anagrafiche.find(
        {"id": {"$in": contraente_ids}},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "nome": 1, "cognome": 1,
         "cognome_nome": 1, "email": 1, "indirizzo": 1, "cap": 1, "citta": 1, "provincia": 1},
    )}
    comps = {c["id"]: c.get("nome") async for c in db.compagnie.find(
        {"id": {"$in": compagnia_ids}}, {"_id": 0, "id": 1, "nome": 1},
    )}

    today = date.today().isoformat()
    out = []
    for p in polizze:
        a = anags.get(p.get("contraente_id"), {})
        st = p.get("regolazione_stato") or "da_richiedere"
        giorni = p.get("regolazione_giorni_invio", 30)
        data_invio = _data_invio_prevista(p.get("scadenza"), giorni)
        da_inviare = bool(data_invio and today >= data_invio and st in ("da_richiedere",))
        row = {
            "polizza_id": p["id"],
            "numero_polizza": p.get("numero_polizza"),
            "ramo": p.get("ramo"),
            "prodotto": p.get("prodotto"),
            "contraente_id": p.get("contraente_id"),
            "contraente_nome": _anag_nome(a),
            "contraente_email": a.get("email"),
            "compagnia": comps.get(p.get("compagnia_id"), "—"),
            "effetto": p.get("effetto"),
            "scadenza": p.get("scadenza"),
            "base_tipo": p.get("regolazione_base"),
            "tasso": p.get("regolazione_tasso"),
            "minima": p.get("regolazione_minima"),
            "periodicita": p.get("regolazione_periodicita"),
            "giorni_invio": giorni,
            "data_invio_prevista": data_invio,
            "stato": st,
            "ultimo_calcolo": p.get("regolazione_ultimo_calcolo"),
            "dovuto": p.get("regolazione_dovuto") or 0,
            "lettera_inviata_data": p.get("regolazione_lettera_inviata_data"),
            "titolo_id": p.get("regolazione_titolo_id"),
            "da_inviare": da_inviare,
            "note": p.get("regolazione_note"),
        }
        if stato and st != stato:
            continue
        out.append(row)

    # Ordina: prima quelle da inviare, poi per data invio prevista
    out.sort(key=lambda r: (not r["da_inviare"], r["data_invio_prevista"] or "9999"))
    return out


@router.get("/regolazione-premio/stats")
async def stats_regolazioni(user=Depends(current_user)) -> dict:
    rows = await list_regolazioni(user=user)
    stati = {}
    for r in rows:
        stati[r["stato"]] = stati.get(r["stato"], 0) + 1
    return {
        "totale": len(rows),
        "da_inviare": sum(1 for r in rows if r["da_inviare"]),
        "per_stato": stati,
        "dovuto_totale": round(sum(r["dovuto"] or 0 for r in rows), 2),
    }


# ============================================================================
# LETTERA RICHIESTA DATI
# ============================================================================
class LetteraBody(BaseModel):
    invia_email: bool = False
    testo_extra: Optional[str] = None
    periodo: Optional[str] = None


async def _build_lettera(pid: str, body: LetteraBody):
    pol = await db.polizze.find_one({"id": pid}, {"_id": 0})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")
    if not pol.get("regolazione_premio"):
        raise HTTPException(400, "Polizza non soggetta a regolazione premio")
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    a = await db.anagrafiche.find_one(
        {"id": pol.get("contraente_id")}, {"_id": 0},
    ) or {}
    comp = await db.compagnie.find_one(
        {"id": pol.get("compagnia_id")}, {"_id": 0, "nome": 1},
    ) or {}
    from pdf_regolazione import genera_lettera_regolazione
    pdf = genera_lettera_regolazione(
        azienda=az,
        contraente_nome=_anag_nome(a),
        contraente_indirizzo=_anag_indirizzo(a),
        numero_polizza=pol.get("numero_polizza") or "",
        compagnia=comp.get("nome") or "",
        ramo=f"{pol.get('ramo') or ''} {pol.get('prodotto') or ''}".strip(),
        effetto=pol.get("effetto") or "",
        scadenza=pol.get("scadenza") or "",
        base_tipo=pol.get("regolazione_base"),
        periodo=body.periodo or "",
        testo_extra=body.testo_extra,
    )
    return pol, a, az, pdf


@router.post("/regolazione-premio/{pid}/lettera-pdf")
async def scarica_lettera(
    pid: str, body: LetteraBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Genera e restituisce il PDF della lettera (download, senza inviare)."""
    _, _, _, pdf = await _build_lettera(pid, body)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="regolazione-{pid}.pdf"'},
    )


@router.post("/regolazione-premio/{pid}/invia-lettera")
async def invia_lettera(
    pid: str, body: LetteraBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Segna la lettera come inviata. Se invia_email=True prova l'invio SMTP
    con il PDF in allegato al contraente."""
    pol, a, az, pdf = await _build_lettera(pid, body)
    email_esito = None
    if body.invia_email:
        dest = (a.get("email") or "").strip()
        if not dest:
            raise HTTPException(400, "Il contraente non ha un'email registrata")
        if not (az.get("smtp_host") and az.get("smtp_user")):
            raise HTTPException(400, "SMTP non configurato (host/user mancanti)")
        from email_utils import smtp_send
        try:
            smtp_send(
                az, to_addrs=dest,
                subject=f"Richiesta dati regolazione premio — Polizza {pol.get('numero_polizza')}",
                text=(
                    "Gentile Cliente,\nin allegato trova la richiesta dei dati necessari "
                    "alla regolazione del premio della Sua polizza.\nCordiali saluti."
                ),
                attachments=[(f"regolazione-{pol.get('numero_polizza')}.pdf", pdf, "application", "pdf")],
            )
            email_esito = f"inviata a {dest}"
        except Exception as e:
            raise HTTPException(503, f"Errore invio email: {e}")

    oggi = _now_iso()[:10]
    await db.polizze.update_one({"id": pid}, {"$set": {
        "regolazione_stato": "lettera_inviata",
        "regolazione_lettera_inviata_data": oggi,
        "updated_at": _now_iso(),
    }})
    await db.regolazione_storico.insert_one({
        "id": str(uuid.uuid4()), "polizza_id": pid, "evento": "lettera_inviata",
        "data": oggi, "email": email_esito, "operatore_id": user.get("id"),
        "created_at": _now_iso(),
    })
    await log_attivita(user, "lettera_regolazione", "polizza", pid)
    return {"ok": True, "stato": "lettera_inviata", "data": oggi, "email": email_esito}


# ============================================================================
# STATO WORKFLOW
# ============================================================================
class StatoBody(BaseModel):
    stato: str
    note: Optional[str] = None


@router.post("/regolazione-premio/{pid}/stato")
async def cambia_stato(
    pid: str, body: StatoBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    validi = {"da_richiedere", "lettera_inviata", "dati_ricevuti", "calcolata", "titolo_generato", "chiusa"}
    if body.stato not in validi:
        raise HTTPException(400, f"Stato non valido. Ammessi: {sorted(validi)}")
    upd = {"regolazione_stato": body.stato, "updated_at": _now_iso()}
    if body.note is not None:
        upd["regolazione_note"] = body.note
    res = await db.polizze.update_one({"id": pid}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Polizza non trovata")
    await db.regolazione_storico.insert_one({
        "id": str(uuid.uuid4()), "polizza_id": pid, "evento": f"stato:{body.stato}",
        "data": _now_iso()[:10], "note": body.note, "operatore_id": user.get("id"),
        "created_at": _now_iso(),
    })
    return {"ok": True, "stato": body.stato}


# ============================================================================
# GENERAZIONE TITOLO DI REGOLAZIONE
# ============================================================================
class TitoloRegBody(BaseModel):
    importo: Optional[float] = None  # override; default = regolazione_dovuto
    effetto: Optional[str] = None
    scadenza: Optional[str] = None
    imposte: float = 0.0


@router.post("/regolazione-premio/{pid}/genera-titolo", status_code=201)
async def genera_titolo(
    pid: str, body: TitoloRegBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    pol = await db.polizze.find_one({"id": pid}, {"_id": 0})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")
    if not pol.get("regolazione_premio"):
        raise HTTPException(400, "Polizza non soggetta a regolazione premio")
    importo = body.importo if body.importo is not None else float(pol.get("regolazione_dovuto") or 0)
    if not importo or importo <= 0:
        raise HTTPException(400, "Nessun importo dovuto: eseguire prima il calcolo della regolazione")
    oggi = _now_iso()[:10]
    netto = round(importo - (body.imposte or 0), 2)
    titolo = Titolo(
        polizza_id=pid,
        tipo="regolazione",
        effetto=body.effetto or oggi,
        scadenza=body.scadenza or oggi,
        importo_lordo=importo,
        importo_netto=netto if netto > 0 else importo,
        imposte=body.imposte or 0.0,
        stato="da_incassare",
        collaboratore_id=pol.get("collaboratore_id"),
    )
    await db.titoli.insert_one(titolo.model_dump())
    await db.polizze.update_one({"id": pid}, {"$set": {
        "regolazione_stato": "titolo_generato",
        "regolazione_titolo_id": titolo.id,
        "updated_at": _now_iso(),
    }})
    await db.regolazione_storico.insert_one({
        "id": str(uuid.uuid4()), "polizza_id": pid, "evento": "titolo_generato",
        "data": oggi, "titolo_id": titolo.id, "importo": importo,
        "operatore_id": user.get("id"), "created_at": _now_iso(),
    })
    await log_attivita(user, "genera_titolo_regolazione", "titolo", titolo.id)
    return strip_mongo_id(titolo.model_dump())


@router.get("/regolazione-premio/{pid}/eventi")
async def eventi_regolazione(pid: str, user=Depends(current_user)) -> list[dict]:
    return await db.regolazione_storico.find(
        {"polizza_id": pid}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)
