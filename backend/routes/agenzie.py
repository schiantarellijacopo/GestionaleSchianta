"""Agenzie — libreria delle agenzie assicurative (propria + partner).

Una compagnia ha un mandato che è:
- **diretto**: con l'agenzia principale (la nostra agenzia)
- **collaborazione**: con un'altra agenzia partner che ha il mandato
  diretto con la compagnia. Es. Agenzia Schiantarelli collabora con
  Agenzia Bottoni che ha mandato Unipol/AXA. Le nostre provvigioni le
  fattureremo a Bottoni.
"""
from __future__ import annotations

import uuid
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter(prefix="/agenzie", tags=["agenzie"])


class AgenziaBody(BaseModel):
    ragione_sociale: str
    codice: Optional[str] = None
    tipo: Literal["principale", "partner"] = "partner"
    referente: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    indirizzo: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    cap: Optional[str] = None
    partita_iva: Optional[str] = None
    codice_fiscale: Optional[str] = None
    iban: Optional[str] = None
    note: Optional[str] = None
    attiva: bool = True
    # Ritenuta d'acconto applicata alle fatture provvigioni dell'agenzia
    # (es. 20% per professionisti, 23% per società di intermediazione).
    perc_ritenuta_acconto: float = 0
    # Collegamento bidirezionale (informativo) con le compagnie partner.
    # Sorgente di verità = compagnia.agenzie_partner_ids: qui è "passthrough".
    compagnie_ids: Optional[list[str]] = None


async def _compagnie_ids_of(aid: str) -> list[str]:
    """Compagnie collegate a questa agenzia via campo plurale agenzie_partner_ids."""
    return [c["id"] async for c in db.compagnie.find(
        {"agenzie_partner_ids": aid}, {"_id": 0, "id": 1})]


async def _sync_agenzia_to_compagnie(aid: str, compagnie_ids: list[str]) -> None:
    """Write-through dal lato agenzia: allinea compagnia.agenzie_partner_ids."""
    compagnie_ids = compagnie_ids or []
    if compagnie_ids:
        await db.compagnie.update_many(
            {"id": {"$in": compagnie_ids}},
            {"$addToSet": {"agenzie_partner_ids": aid}})
    # rimuovi il legame dalle compagnie non più selezionate
    await db.compagnie.update_many(
        {"agenzie_partner_ids": aid, "id": {"$nin": compagnie_ids}},
        {"$pull": {"agenzie_partner_ids": aid}})


@router.get("")
async def list_agenzie(
    tipo: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if tipo: flt["tipo"] = tipo
    items = await db.agenzie.find(flt, {"_id": 0}).sort("ragione_sociale", 1).to_list(500)
    # per ogni agenzia partner: conteggio compagnie collegate
    for a in items:
        if a.get("tipo") == "principale":
            # mandato diretto = compagnie ATTIVE senza ALCUNA agenzia partner (plurale o legacy)
            a["n_compagnie_collegate"] = await db.compagnie.count_documents(
                {"$and": [
                    {"attiva": {"$ne": False}},
                    {"$or": [{"agenzia_partner_id": None}, {"agenzia_partner_id": {"$exists": False}}]},
                    {"$or": [{"agenzie_partner_ids": {"$exists": False}}, {"agenzie_partner_ids": []}, {"agenzie_partner_ids": None}]},
                ]},
            )
        else:
            a["n_compagnie_collegate"] = await db.compagnie.count_documents(
                {"$and": [
                    {"attiva": {"$ne": False}},
                    {"$or": [{"agenzia_partner_id": a["id"]}, {"agenzie_partner_ids": a["id"]}]},
                ]},
            )
            a["compagnie_ids"] = await _compagnie_ids_of(a["id"])
    return items


@router.get("/{aid}")
async def get_agenzia(aid: str, user=Depends(current_user)) -> dict:
    a = await db.agenzie.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Agenzia non trovata")
    a["compagnie_collegate"] = await db.compagnie.find(
        {"$or": [{"agenzia_partner_id": aid}, {"agenzie_partner_ids": aid}]},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1, "tipo_mandato": 1},
    ).to_list(200)
    a["compagnie_ids"] = await _compagnie_ids_of(aid)
    return a


@router.post("", status_code=201)
async def create_agenzia(
    body: AgenziaBody,
    user=Depends(require_user("admin")),
) -> dict:
    if not body.ragione_sociale.strip():
        raise HTTPException(400, "Ragione sociale obbligatoria")
    # vincolo: una sola agenzia principale
    if body.tipo == "principale":
        existing = await db.agenzie.find_one({"tipo": "principale"}, {"_id": 0, "id": 1})
        if existing:
            raise HTTPException(400, "Esiste già un'agenzia principale (modifica quella)")
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": _now_iso()}
    compagnie_ids = doc.pop("compagnie_ids", None)
    await db.agenzie.insert_one(doc)
    doc.pop("_id", None)
    if compagnie_ids is not None:
        await _sync_agenzia_to_compagnie(doc["id"], compagnie_ids)
    doc["compagnie_ids"] = await _compagnie_ids_of(doc["id"])
    return doc


@router.put("/{aid}")
async def update_agenzia(
    aid: str, body: AgenziaBody,
    user=Depends(require_user("admin")),
) -> dict:
    data = body.model_dump()
    compagnie_ids = data.pop("compagnie_ids", None)  # non persistito: derivato
    data["updated_at"] = _now_iso()
    res = await db.agenzie.update_one({"id": aid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Agenzia non trovata")
    if compagnie_ids is not None:
        await _sync_agenzia_to_compagnie(aid, compagnie_ids)
    doc = await db.agenzie.find_one({"id": aid}, {"_id": 0})
    doc["compagnie_ids"] = await _compagnie_ids_of(aid)
    return doc


@router.delete("/{aid}")
async def delete_agenzia(
    aid: str, user=Depends(require_user("admin")),
) -> dict:
    # blocco se ci sono compagnie collegate col mandato (singolare)
    n = await db.compagnie.count_documents({"agenzia_partner_id": aid})
    if n > 0:
        raise HTTPException(400, f"Impossibile eliminare: {n} compagnie sono collegate a questa agenzia")
    res = await db.agenzie.delete_one({"id": aid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Agenzia non trovata")
    # pulizia: rimuovi il riferimento dalle compagnie collegate (plurale)
    await db.compagnie.update_many(
        {"agenzie_partner_ids": aid}, {"$pull": {"agenzie_partner_ids": aid}})
    return {"ok": True}
