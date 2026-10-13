"""Endpoint una-tantum per COPIARE l'intero database di produzione verso un
altro MongoDB (es. Railway), aggirando l'IP allowlist di Atlas.

Perché esiste:
- Il cluster MongoDB Atlas gestito da Emergent accetta connessioni SOLO dalla
  rete interna di Emergent. `mongodump` dall'esterno è impossibile.
- Questo endpoint gira DENTRO il backend di produzione (che Atlas lo raggiunge),
  legge tutte le collezioni dalla sorgente (MONGO_URL/DB_NAME del pod) e le
  scrive sul MongoDB di destinazione (URL pubblico passato nel body).

Sicurezza:
- Richiede ruolo admin + super_admin.
- Richiede una stringa di conferma esatta nel body.
- Sulla SORGENTE esegue SOLO letture.
"""
from __future__ import annotations

import os
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_user
from tenant import is_super_admin

router = APIRouter(prefix="/migrate", tags=["migrate"])

CONFIRM_TOKEN = "MIGRATE-TO-RAILWAY"
BATCH = 1000


class MigrateBody(BaseModel):
    dst_mongo_url: str
    dst_db: str
    confirm: str
    drop: bool = True
    dry_run: bool = False
    collections: Optional[list[str]] = None


def _run_copy(body: MigrateBody) -> dict:
    from pymongo import MongoClient, UpdateOne

    src_url = os.environ["MONGO_URL"]
    src_dbname = os.environ["DB_NAME"]
    src = MongoClient(src_url, serverSelectionTimeoutMS=20000)[src_dbname]
    dst = MongoClient(body.dst_mongo_url, serverSelectionTimeoutMS=20000)[body.dst_db]

    names = [c for c in src.list_collection_names() if not c.startswith("system.")]
    if body.collections:
        names = [c for c in names if c in body.collections]

    report: dict = {
        "source_db": src_dbname,
        "dest_db": body.dst_db,
        "dry_run": body.dry_run,
        "drop": body.drop,
        "collections": {},
    }

    for coll in sorted(names):
        src_count = src[coll].count_documents({})
        if body.dry_run:
            report["collections"][coll] = {"read": src_count, "written": 0, "dry_run": True}
            continue
        if body.drop:
            dst[coll].drop()
        written = 0
        ops: list = []
        for doc in src[coll].find({}, no_cursor_timeout=True):
            ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True))
            if len(ops) >= BATCH:
                dst[coll].bulk_write(ops, ordered=False)
                written += len(ops)
                ops = []
        if ops:
            dst[coll].bulk_write(ops, ordered=False)
            written += len(ops)
        report["collections"][coll] = {"read": src_count, "written": written}

    report["dest_db_after"] = {c: dst[c].count_documents({}) for c in sorted(names)}
    report["total_read"] = sum(v["read"] for v in report["collections"].values())
    return report


@router.post("/to-railway")
async def migrate_to_railway(body: MigrateBody, user=Depends(require_user("admin"))):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Operazione riservata al super admin")
    if body.confirm != CONFIRM_TOKEN:
        raise HTTPException(status_code=400, detail=f"Conferma mancante: invia confirm='{CONFIRM_TOKEN}'")
    try:
        return await asyncio.to_thread(_run_copy, body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Copia fallita: {exc}")
