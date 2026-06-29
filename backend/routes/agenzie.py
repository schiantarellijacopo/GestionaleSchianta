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
        a["n_compagnie_collegate"] = await db.compagnie.count_documents(
            {"agenzia_partner_id": a["id"]},
        )
    return items


@router.get("/{aid}")
async def get_agenzia(aid: str, user=Depends(current_user)) -> dict:
    a = await db.agenzie.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Agenzia non trovata")
    a["compagnie_collegate"] = await db.compagnie.find(
        {"agenzia_partner_id": aid},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1, "tipo_mandato": 1},
    ).to_list(200)
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
    await db.agenzie.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{aid}")
async def update_agenzia(
    aid: str, body: AgenziaBody,
    user=Depends(require_user("admin")),
) -> dict:
    data = body.model_dump()
    data["updated_at"] = _now_iso()
    res = await db.agenzie.update_one({"id": aid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Agenzia non trovata")
    return await db.agenzie.find_one({"id": aid}, {"_id": 0})


@router.delete("/{aid}")
async def delete_agenzia(
    aid: str, user=Depends(require_user("admin")),
) -> dict:
    # blocco se ci sono compagnie collegate
    n = await db.compagnie.count_documents({"agenzia_partner_id": aid})
    if n > 0:
        raise HTTPException(400, f"Impossibile eliminare: {n} compagnie sono collegate a questa agenzia")
    res = await db.agenzie.delete_one({"id": aid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Agenzia non trovata")
    return {"ok": True}
