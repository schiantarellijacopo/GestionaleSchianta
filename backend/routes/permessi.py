"""Permessi profilo — matrice granulare di permessi per area.

Ogni utente ha un ``profilo_permessi_id`` che punta a un record
``ProfiloPermessi`` con la mappa ``area → "none" | "read" | "write"``.

Aree gestite (sezioni del CRM):
  - anagrafiche, polizze, titoli, sinistri, avvisi, contabilita
  - estratti_conto, compagnie, prodotti, modelli, comunicazioni
  - alert, calendario, posta, diario, dashboard, librerie, importazioni
"""
from __future__ import annotations

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_user
from database import db
from db_models import _now_iso


router = APIRouter()


AREE = [
    "anagrafiche", "polizze", "titoli", "sinistri", "avvisi",
    "contabilita", "estratti_conto", "compagnie", "prodotti",
    "modelli", "comunicazioni", "alert", "calendario",
    "posta", "diario", "dashboard", "librerie", "importazioni",
    "documenti", "marketing", "pipeline", "corsi",
]

LIVELLI = ["none", "read", "write"]


class ProfiloPermessiBody(BaseModel):
    nome: str
    descrizione: Optional[str] = None
    area_levels: dict = Field(default_factory=dict)        # area → "none"|"read"|"write"
    attivo: bool = True


@router.get("/permessi-profili")
async def list_profili(user: dict = Depends(require_user("admin"))) -> list[dict]:
    return await db.profili_permessi.find({}, {"_id": 0}).sort("nome", 1).to_list(100)


@router.get("/permessi-aree")
async def list_aree(user: dict = Depends(require_user("admin"))) -> dict:
    """Restituisce l'elenco delle aree disponibili e dei livelli supportati."""
    return {"aree": AREE, "livelli": LIVELLI}


@router.post("/permessi-profili", status_code=201)
async def create_profilo(body: ProfiloPermessiBody,
                          user: dict = Depends(require_user("admin"))) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        **body.model_dump(),
        "created_at": _now_iso(),
    }
    await db.profili_permessi.insert_one(doc)
    return doc


@router.put("/permessi-profili/{pid}")
async def update_profilo(pid: str, body: ProfiloPermessiBody,
                          user: dict = Depends(require_user("admin"))) -> dict:
    res = await db.profili_permessi.update_one(
        {"id": pid}, {"$set": {**body.model_dump(), "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Profilo non trovato")
    return await db.profili_permessi.find_one({"id": pid}, {"_id": 0})


@router.delete("/permessi-profili/{pid}")
async def delete_profilo(pid: str, user: dict = Depends(require_user("admin"))) -> dict:
    in_use = await db.users.count_documents({"profilo_permessi_id": pid})
    if in_use:
        raise HTTPException(400, f"Profilo in uso da {in_use} utenti")
    res = await db.profili_permessi.delete_one({"id": pid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Profilo non trovato")
    return {"ok": True}


async def seed_default_profili() -> None:
    """Crea i 3 profili di default se non esistono (idempotente)."""
    if await db.profili_permessi.count_documents({}) > 0:
        return
    full = {a: "write" for a in AREE}
    read_only = {a: "read" for a in AREE}
    collab = {a: "write" for a in AREE}
    collab["compagnie"] = "read"
    collab["importazioni"] = "none"
    collab["librerie"] = "read"
    defaults = [
        {"nome": "Admin agente", "descrizione": "Accesso completo a tutto", "area_levels": full},
        {"nome": "Collaboratore", "descrizione": "Operatore standard - no librerie/import",
         "area_levels": collab},
        {"nome": "Sola lettura", "descrizione": "Read-only per audit/back-office",
         "area_levels": read_only},
    ]
    for d in defaults:
        await db.profili_permessi.insert_one({
            "id": str(uuid.uuid4()),
            **d, "attivo": True, "created_at": _now_iso(),
        })
