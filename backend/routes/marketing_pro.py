"""Marketing — Voucher compagnia + Newsletter.

Voucher: la compagnia fornisce codici sconto anonimi che l'agenzia assegna ai clienti.
Newsletter: campagne email/sms/whatsapp a liste segmentate di clienti.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter()


# ============= VOUCHER COMPAGNIA =============
class VoucherBody(BaseModel):
    codice: str
    compagnia_id: Optional[str] = None
    descrizione: Optional[str] = None
    valore: float = 0
    tipo_valore: str = "euro"  # euro | percentuale
    valido_dal: Optional[str] = None
    valido_al: Optional[str] = None
    ramo: Optional[str] = None
    assegnato_a: Optional[str] = None  # anagrafica_id
    note: Optional[str] = None
    usato: bool = False
    data_uso: Optional[str] = None


@router.get("/voucher")
async def list_voucher(
    stato: Optional[str] = None,  # disponibile | assegnato | usato
    compagnia_id: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if compagnia_id: flt["compagnia_id"] = compagnia_id
    if stato == "disponibile":
        flt["assegnato_a"] = None; flt["usato"] = False
    elif stato == "assegnato":
        flt["assegnato_a"] = {"$ne": None}; flt["usato"] = False
    elif stato == "usato":
        flt["usato"] = True
    items = await db.voucher.find(flt, {"_id": 0}).sort("created_at", -1).to_list(5000)
    ana_ids = list({v["assegnato_a"] for v in items if v.get("assegnato_a")})
    anas = {a["id"]: a async for a in db.anagrafiche.find(
        {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    comp_ids = list({v["compagnia_id"] for v in items if v.get("compagnia_id")})
    comps = {c["id"]: c async for c in db.compagnie.find(
        {"id": {"$in": comp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    for v in items:
        a = anas.get(v.get("assegnato_a"), {})
        v["assegnato_a_nome"] = a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip()
        v["compagnia_nome"] = comps.get(v.get("compagnia_id"), {}).get("ragione_sociale")
    return items


@router.post("/voucher", status_code=201)
async def create_voucher(body: VoucherBody,
                          user=Depends(require_user("admin", "collaboratore"))) -> dict:
    if not body.codice.strip():
        raise HTTPException(400, "Codice obbligatorio")
    if await db.voucher.find_one({"codice": body.codice}):
        raise HTTPException(400, "Codice voucher già esistente")
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": _now_iso()}
    await db.voucher.insert_one(doc)
    return doc


@router.put("/voucher/{vid}")
async def update_voucher(vid: str, body: VoucherBody,
                          user=Depends(require_user("admin", "collaboratore"))) -> dict:
    data = body.model_dump()
    data["updated_at"] = _now_iso()
    res = await db.voucher.update_one({"id": vid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Voucher non trovato")
    return await db.voucher.find_one({"id": vid}, {"_id": 0})


@router.delete("/voucher/{vid}")
async def delete_voucher(vid: str, user=Depends(require_user("admin"))) -> dict:
    res = await db.voucher.delete_one({"id": vid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Voucher non trovato")
    return {"ok": True}


@router.post("/voucher/{vid}/assegna")
async def assegna_voucher(vid: str, body: dict,
                          user=Depends(require_user("admin", "collaboratore"))) -> dict:
    ana_id = body.get("anagrafica_id")
    if not ana_id:
        raise HTTPException(400, "anagrafica_id obbligatorio")
    await db.voucher.update_one({"id": vid}, {"$set": {
        "assegnato_a": ana_id, "data_assegnazione": _now_iso(),
    }})
    return await db.voucher.find_one({"id": vid}, {"_id": 0})


@router.post("/voucher/bulk-import")
async def bulk_import_voucher(body: dict,
                              user=Depends(require_user("admin", "collaboratore"))) -> dict:
    """Importa una lista di voucher anonimi (codici).

    Body: ``{compagnia_id, ramo?, valore, tipo_valore, valido_dal, valido_al, codici: [str]}``
    """
    codici = body.get("codici") or []
    if not codici:
        raise HTTPException(400, "Lista codici vuota")
    n = 0
    skipped = 0
    for c in codici:
        c = (c or "").strip()
        if not c: continue
        if await db.voucher.find_one({"codice": c}):
            skipped += 1; continue
        await db.voucher.insert_one({
            "id": str(uuid.uuid4()),
            "codice": c,
            "compagnia_id": body.get("compagnia_id"),
            "ramo": body.get("ramo"),
            "valore": float(body.get("valore") or 0),
            "tipo_valore": body.get("tipo_valore") or "euro",
            "valido_dal": body.get("valido_dal"),
            "valido_al": body.get("valido_al"),
            "descrizione": body.get("descrizione"),
            "usato": False,
            "created_at": _now_iso(),
        })
        n += 1
    return {"creati": n, "duplicati": skipped}


# ============= NEWSLETTER =============
class NewsletterBody(BaseModel):
    nome: str
    oggetto: str
    contenuto: str  # HTML / testo
    canale: str = "email"  # email | sms | whatsapp
    target_filtro: dict = Field(default_factory=dict)  # {tags?, ramo?, compagnia_id?}
    stato: str = "bozza"  # bozza | inviata | programmata
    data_programmata: Optional[str] = None


@router.get("/newsletter")
async def list_newsletter(user=Depends(current_user)) -> list[dict]:
    return await db.newsletter.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/newsletter", status_code=201)
async def create_newsletter(body: NewsletterBody,
                            user=Depends(require_user("admin", "collaboratore"))) -> dict:
    doc = {"id": str(uuid.uuid4()), **body.model_dump(),
           "destinatari_calcolati": 0, "destinatari_inviati": 0,
           "created_at": _now_iso(), "created_by": user.get("id")}
    # Pre-calcolo destinatari
    flt = await _build_target_filter(body.target_filtro)
    doc["destinatari_calcolati"] = await db.anagrafiche.count_documents(flt)
    await db.newsletter.insert_one(doc)
    return doc


@router.put("/newsletter/{nid}")
async def update_newsletter(nid: str, body: NewsletterBody,
                            user=Depends(require_user("admin", "collaboratore"))) -> dict:
    data = body.model_dump()
    data["updated_at"] = _now_iso()
    flt = await _build_target_filter(body.target_filtro)
    data["destinatari_calcolati"] = await db.anagrafiche.count_documents(flt)
    res = await db.newsletter.update_one({"id": nid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Newsletter non trovata")
    return await db.newsletter.find_one({"id": nid}, {"_id": 0})


@router.delete("/newsletter/{nid}")
async def delete_newsletter(nid: str, user=Depends(require_user("admin"))) -> dict:
    res = await db.newsletter.delete_one({"id": nid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Newsletter non trovata")
    return {"ok": True}


async def _build_target_filter(target: dict) -> dict:
    flt: dict = {"consenso_commerciale": True}
    if target.get("tags"):
        flt["tags"] = {"$in": target["tags"] if isinstance(target["tags"], list) else [target["tags"]]}
    if target.get("tipo"):
        flt["tipo"] = target["tipo"]
    return flt


@router.post("/newsletter/{nid}/invia")
async def invia_newsletter(nid: str,
                            user=Depends(require_user("admin"))) -> dict:
    """Marca la newsletter come inviata e simula invio (in produzione qui
    si dispatcia su Resend/Twilio in base al canale)."""
    nl = await db.newsletter.find_one({"id": nid}, {"_id": 0})
    if not nl:
        raise HTTPException(404, "Newsletter non trovata")
    flt = await _build_target_filter(nl.get("target_filtro") or {})
    destinatari = await db.anagrafiche.find(flt, {"_id": 0, "id": 1, "email": 1,
                                                   "cellulare": 1}).to_list(50000)
    # Log invio nel Diario di ogni cliente
    for d in destinatari:
        await db.diario_cliente.insert_one({
            "id": str(uuid.uuid4()),
            "anagrafica_id": d["id"],
            "tipo": "newsletter_inviata",
            "data": _now_iso(),
            "operatore_id": user.get("id"),
            "contenuto": f"Newsletter '{nl['nome']}' inviata via {nl['canale']}",
            "fonte": "marketing",
        })
    await db.newsletter.update_one({"id": nid}, {"$set": {
        "stato": "inviata",
        "destinatari_inviati": len(destinatari),
        "data_invio": _now_iso(),
    }})
    return {"ok": True, "destinatari": len(destinatari)}
