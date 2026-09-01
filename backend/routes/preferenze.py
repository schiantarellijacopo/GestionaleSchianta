"""Preferenze utente — visualizzazione colonne per tabella (per-utente)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import current_user
from database import db
from db_models import _now_iso

router = APIRouter(prefix="/preferenze")


@router.get("/colonne")
async def get_colonne(user=Depends(current_user)):
    docs = await db.user_column_prefs.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    return {d["table_key"]: {"order": d.get("order") or [], "hidden": d.get("hidden") or []}
            for d in docs}


@router.put("/colonne/{table_key}")
async def save_colonne(table_key: str, body: dict, user=Depends(current_user)):
    order = [str(x)[:80] for x in (body.get("order") or [])][:60]
    hidden = [str(x)[:80] for x in (body.get("hidden") or [])][:60]
    await db.user_column_prefs.update_one(
        {"user_id": user["id"], "table_key": table_key[:80]},
        {"$set": {"order": order, "hidden": hidden, "updated_at": _now_iso()}},
        upsert=True,
    )
    return {"ok": True}


@router.delete("/colonne/{table_key}")
async def reset_colonne(table_key: str, user=Depends(current_user)):
    await db.user_column_prefs.delete_one({"user_id": user["id"], "table_key": table_key})
    return {"ok": True}
