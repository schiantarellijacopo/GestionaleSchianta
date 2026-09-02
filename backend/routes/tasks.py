"""Modulo TASK — bacheca attività stile Google Tasks.

- Ogni operatore vede le PROPRIE attività (owner) + quelle CONDIVISE con lui.
- Condivisione con uno o più operatori (`assegnatari`).
- Allegati documenti (object storage).
- Stampa (il frontend usa i dati della bacheca).

Multi-tenant: la collection `tasks` è tenant-scoped (vedi tenant.py).
"""
from __future__ import annotations

import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import db
from auth import current_user, require_user
from db_models import _now_iso, _uid
from tenant import tenant_filter
import storage as obj_storage

router = APIRouter(prefix="/tasks", tags=["tasks"])

_ROLES = ("admin", "collaboratore", "dipendente")


def _visibile_a(user: dict) -> dict:
    """Filtro: task di cui l'utente è owner OPPURE assegnatario."""
    uid = user["id"]
    return {"$or": [{"owner_id": uid}, {"assegnatari": uid}]}


async def _get_task_or_404(tid: str, user: dict) -> dict:
    t = await db.tasks.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Attività non trovata")
    if user.get("role") != "admin" and user["id"] not in (
        [t.get("owner_id")] + (t.get("assegnatari") or [])
    ):
        raise HTTPException(403, "Non hai accesso a questa attività")
    return t


class TaskCreate(BaseModel):
    titolo: str
    note: Optional[str] = None
    owner_id: Optional[str] = None          # colonna operatore (default: me)
    assegnatari: List[str] = []             # condivisa con altri operatori
    data_scadenza: Optional[str] = None     # YYYY-MM-DD
    priorita: Optional[str] = "normale"     # bassa | normale | alta


class TaskUpdate(BaseModel):
    titolo: Optional[str] = None
    note: Optional[str] = None
    owner_id: Optional[str] = None
    assegnatari: Optional[List[str]] = None
    data_scadenza: Optional[str] = None
    priorita: Optional[str] = None
    stato: Optional[str] = None             # todo | done


@router.get("/operatori")
async def list_operatori(user: dict = Depends(require_user(*_ROLES))) -> list[dict]:
    """Operatori dell'agenzia (per colonne bacheca + condivisione)."""
    flt = {"role": {"$in": list(_ROLES)}, **(tenant_filter(user) or {})}
    items = await db.users.find(flt, {"_id": 0, "id": 1, "name": 1, "role": 1, "email": 1}).sort("name", 1).to_list(500)
    return items


@router.get("")
async def list_tasks(
    include_done: bool = False,
    tutti: bool = False,
    user: dict = Depends(require_user(*_ROLES)),
) -> list[dict]:
    """Attività visibili all'utente: di default SOLO le proprie + quelle condivise.

    Solo l'admin può richiedere `tutti=true` per vedere le attività di tutti gli
    operatori dell'agenzia (scelta esplicita, non di default)."""
    if tutti and user.get("role") == "admin":
        flt: dict = {}
    else:
        flt = _visibile_a(user)
    if not include_done:
        flt = {"$and": [flt, {"stato": {"$ne": "done"}}]} if flt else {"stato": {"$ne": "done"}}
    items = await db.tasks.find(flt, {"_id": 0}).sort([("stato", 1), ("data_scadenza", 1), ("created_at", -1)]).to_list(2000)
    return items


@router.post("", status_code=201)
async def create_task(body: TaskCreate, user: dict = Depends(require_user(*_ROLES))) -> dict:
    if not body.titolo.strip():
        raise HTTPException(400, "Titolo obbligatorio")
    owner = body.owner_id or user["id"]
    # non-admin può creare solo nella PROPRIA colonna
    if user.get("role") != "admin" and owner != user["id"]:
        owner = user["id"]
    doc = {
        "id": _uid(),
        "titolo": body.titolo.strip(),
        "note": body.note,
        "owner_id": owner,
        "assegnatari": [a for a in (body.assegnatari or []) if a and a != owner],
        "data_scadenza": body.data_scadenza,
        "priorita": body.priorita or "normale",
        "stato": "todo",
        "allegati": [],
        "creato_da": user["id"],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "completed_at": None,
    }
    await db.tasks.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{tid}")
async def update_task(tid: str, body: TaskUpdate, user: dict = Depends(require_user(*_ROLES))) -> dict:
    await _get_task_or_404(tid, user)
    upd = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if "titolo" in upd and not str(upd["titolo"]).strip():
        raise HTTPException(400, "Titolo non valido")
    if "stato" in upd:
        upd["completed_at"] = _now_iso() if upd["stato"] == "done" else None
    if "assegnatari" in upd:
        upd["assegnatari"] = [a for a in upd["assegnatari"] if a]
    upd["updated_at"] = _now_iso()
    await db.tasks.update_one({"id": tid}, {"$set": upd})
    return await db.tasks.find_one({"id": tid}, {"_id": 0})


@router.post("/{tid}/toggle")
async def toggle_task(tid: str, user: dict = Depends(require_user(*_ROLES))) -> dict:
    t = await _get_task_or_404(tid, user)
    new_stato = "todo" if t.get("stato") == "done" else "done"
    await db.tasks.update_one({"id": tid}, {"$set": {
        "stato": new_stato,
        "completed_at": _now_iso() if new_stato == "done" else None,
        "updated_at": _now_iso(),
    }})
    return {"id": tid, "stato": new_stato}


@router.delete("/{tid}")
async def delete_task(tid: str, user: dict = Depends(require_user(*_ROLES))) -> dict:
    t = await _get_task_or_404(tid, user)
    if user.get("role") != "admin" and t.get("owner_id") != user["id"] and t.get("creato_da") != user["id"]:
        raise HTTPException(403, "Solo il proprietario può eliminare l'attività")
    for a in (t.get("allegati") or []):
        try:
            obj_storage.delete_object(a["storage_path"])
        except Exception:
            pass
    await db.tasks.delete_one({"id": tid})
    return {"ok": True}


@router.post("/{tid}/allegati")
async def upload_allegato(tid: str, file: UploadFile = File(...),
                          user: dict = Depends(require_user(*_ROLES))) -> dict:
    await _get_task_or_404(tid, user)
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "File troppo grande (max 20 MB)")
    ext = (file.filename or "").split(".")[-1].lower() if file.filename and "." in file.filename else "bin"
    fname = f"{uuid.uuid4()}.{ext}"
    spath = f"{os.environ.get('APP_NAME', 'assicura')}/tasks/{tid}/{fname}"
    res = obj_storage.put_object(spath, content, file.content_type or obj_storage.mime_for(file.filename or fname))
    allegato = {
        "id": _uid(),
        "nome_file": file.filename or fname,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "storage_path": res["path"],
        "caricato_da": user["id"],
        "created_at": _now_iso(),
    }
    await db.tasks.update_one({"id": tid}, {"$push": {"allegati": allegato}, "$set": {"updated_at": _now_iso()}})
    return allegato


@router.get("/{tid}/allegati/{aid}/download")
async def download_allegato(tid: str, aid: str, user: dict = Depends(require_user(*_ROLES))):
    t = await _get_task_or_404(tid, user)
    a = next((x for x in (t.get("allegati") or []) if x["id"] == aid), None)
    if not a:
        raise HTTPException(404, "Allegato non trovato")
    data, ctype = obj_storage.get_object(a["storage_path"])
    import io
    return StreamingResponse(
        io.BytesIO(data),
        media_type=a.get("content_type") or ctype or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{a["nome_file"]}"'},
    )


@router.delete("/{tid}/allegati/{aid}")
async def delete_allegato(tid: str, aid: str, user: dict = Depends(require_user(*_ROLES))) -> dict:
    t = await _get_task_or_404(tid, user)
    a = next((x for x in (t.get("allegati") or []) if x["id"] == aid), None)
    if not a:
        raise HTTPException(404, "Allegato non trovato")
    try:
        obj_storage.delete_object(a["storage_path"])
    except Exception:
        pass
    await db.tasks.update_one({"id": tid}, {"$pull": {"allegati": {"id": aid}}, "$set": {"updated_at": _now_iso()}})
    return {"ok": True}
