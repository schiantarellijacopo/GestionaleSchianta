"""Permessi profilo — matrice GRANULARE di permessi per area.

Ogni profilo ha un dizionario ``area_permissions`` con flag specifici per ogni area:
  - read, write, delete (base)
  - upload_docs (poter caricare allegati anche se non scrittura)
  - export (CSV/XLSX/PDF)
  - print (stampe)
  + flag specifici per area (es. sinistri.edit_cid, comunicazioni.send_email)

Compatibilità: il campo ``area_levels`` (none/read/write) viene mantenuto come
preset rapido di scrittura — la lettura derivata da ``area_permissions`` ha la
precedenza quando presente.
"""
from __future__ import annotations

import uuid
from typing import Optional

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

# Mappa area → lista azioni granulari supportate. "read/write/delete" sono
# sempre presenti; le altre dipendono dalla natura dell'area.
AZIONI_PER_AREA: dict[str, list[str]] = {
    "anagrafiche":    ["read", "write", "delete", "upload_docs", "export", "print", "send_email"],
    "polizze":        ["read", "write", "delete", "upload_docs", "export", "print", "transfer"],
    "titoli":         ["read", "write", "delete", "upload_docs", "incassa", "export", "print"],
    "sinistri":       ["read", "write", "delete", "upload_docs", "edit_cid", "liquida", "print"],
    "avvisi":         ["read", "send_email", "send_sms", "send_wa", "print"],
    "contabilita":    ["read", "write", "delete", "chiusura_giorno", "export", "print"],
    "estratti_conto": ["read", "export", "print"],
    "compagnie":      ["read", "write", "delete"],
    "prodotti":       ["read", "write", "delete"],
    "modelli":        ["read", "write", "delete", "template_edit"],
    "comunicazioni":  ["read", "send_email", "send_sms", "send_wa", "template_edit"],
    "alert":          ["read", "write", "delete"],
    "calendario":     ["read", "write", "delete"],
    "posta":          ["read", "send_email", "delete"],
    "diario":         ["read", "write", "delete"],
    "dashboard":      ["read", "customize"],
    "librerie":       ["read", "write", "delete"],
    "importazioni":   ["read", "import"],
    "documenti":      ["read", "upload_docs", "delete", "export"],
    "marketing":      ["read", "write", "send_email", "send_sms", "send_wa"],
    "pipeline":       ["read", "write", "delete"],
    "corsi":          ["read", "write", "delete", "upload_docs"],
}


class ProfiloPermessiBody(BaseModel):
    nome: str
    descrizione: Optional[str] = None
    # Preset rapidi area→none/read/write (compatibilità)
    area_levels: dict = Field(default_factory=dict)
    # Flag granulari: {area: {azione: bool}}
    area_permissions: dict = Field(default_factory=dict)
    attivo: bool = True


def _expand_level_to_permissions(area: str, level: str) -> dict[str, bool]:
    """Espande un livello preset (none/read/write) in flag granulari."""
    azioni = AZIONI_PER_AREA.get(area, ["read", "write", "delete"])
    if level == "none":
        return {a: False for a in azioni}
    if level == "read":
        return {a: (a == "read") for a in azioni}
    # write = tutto tranne delete e azioni "pericolose"
    pericolose = {"delete", "transfer", "liquida", "import"}
    return {a: (a not in pericolose) for a in azioni}


def _merge_permissions(level_map: dict, perm_map: dict) -> dict[str, dict[str, bool]]:
    """Combina ``area_levels`` (preset) e ``area_permissions`` (override puntuali).

    Le ``area_permissions`` hanno la precedenza sulle ``area_levels``.
    """
    out: dict[str, dict[str, bool]] = {}
    for area in AREE:
        # base dal preset
        level = (level_map or {}).get(area, "none")
        base = _expand_level_to_permissions(area, level)
        # override granulari
        override = (perm_map or {}).get(area) or {}
        merged = {**base, **{k: bool(v) for k, v in override.items()}}
        out[area] = merged
    return out


@router.get("/permessi-profili")
async def list_profili(user: dict = Depends(require_user("admin"))) -> list[dict]:
    items = await db.profili_permessi.find({}, {"_id": 0}).sort("nome", 1).to_list(100)
    # arricchisci con effective_permissions (utile al frontend)
    for p in items:
        p["effective_permissions"] = _merge_permissions(
            p.get("area_levels") or {}, p.get("area_permissions") or {},
        )
    return items


@router.get("/permessi-aree")
async def list_aree(user: dict = Depends(require_user("admin"))) -> dict:
    """Restituisce aree disponibili, livelli preset e azioni granulari per area."""
    return {"aree": AREE, "livelli": LIVELLI, "azioni_per_area": AZIONI_PER_AREA}


@router.post("/permessi-profili", status_code=201)
async def create_profilo(body: ProfiloPermessiBody,
                          user: dict = Depends(require_user("admin"))) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        **body.model_dump(),
        "created_at": _now_iso(),
    }
    await db.profili_permessi.insert_one(doc)
    doc["effective_permissions"] = _merge_permissions(
        doc.get("area_levels") or {}, doc.get("area_permissions") or {},
    )
    return doc


@router.put("/permessi-profili/{pid}")
async def update_profilo(pid: str, body: ProfiloPermessiBody,
                          user: dict = Depends(require_user("admin"))) -> dict:
    res = await db.profili_permessi.update_one(
        {"id": pid}, {"$set": {**body.model_dump(), "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Profilo non trovato")
    doc = await db.profili_permessi.find_one({"id": pid}, {"_id": 0})
    doc["effective_permissions"] = _merge_permissions(
        doc.get("area_levels") or {}, doc.get("area_permissions") or {},
    )
    return doc


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
    """Crea i profili di default se non esistono (idempotente)."""
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
            **d, "area_permissions": {}, "attivo": True, "created_at": _now_iso(),
        })
