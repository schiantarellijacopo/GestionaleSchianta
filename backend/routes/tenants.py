"""Tenants router — gestione delle agenzie tenant (multi-tenant).

Endpoints:
  GET    /tenants                → lista tenant (super_admin ne vede tutti,
                                    utente normale vede solo il proprio).
  GET    /tenants/current        → tenant dell'utente loggato.
  GET    /tenants/{tid}          → dettaglio tenant (super_admin o proprio).
  POST   /tenants                → crea nuovo tenant (super_admin).
  PATCH  /tenants/{tid}          → aggiorna tenant (super_admin).
  DELETE /tenants/{tid}          → soft-delete (super_admin, no principale).
  POST   /tenants/{tid}/switch   → super_admin cambia contesto attivo.
  POST   /tenants/migrate-legacy → migra dati pre-multi-tenant al principale.
"""
from __future__ import annotations
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import Tenant, _now_iso
from tenant import (
    TENANT_PRINCIPALE_ID, is_super_admin, user_tenant_id,
    seed_tenants, migrate_existing_data_to_principale,
)


router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantBody(BaseModel):
    ragione_sociale: str
    codice: Optional[str] = None
    tipo: Literal["principale", "demo", "clean", "partner"] = "partner"
    attivo: bool = True
    storage_provider: Literal["emergent", "s3", "google_drive", "onedrive"] = "emergent"
    storage_config: dict = {}
    referente: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    indirizzo: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    partita_iva: Optional[str] = None
    codice_fiscale: Optional[str] = None
    note: Optional[str] = None


@router.get("")
async def list_tenants(user=Depends(current_user)) -> list[dict]:
    """Super_admin vede tutti i tenant; altri utenti solo il proprio."""
    if is_super_admin(user):
        items = await db.tenants.find({}, {"_id": 0}).sort("ragione_sociale", 1).to_list(200)
    else:
        tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
        items = await db.tenants.find({"id": tid}, {"_id": 0}).to_list(1)
    return items


@router.get("/current")
async def get_current_tenant(user=Depends(current_user)) -> dict:
    tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
    t = await db.tenants.find_one({"id": tid}, {"_id": 0})
    if not t:
        # auto-seed se manca (safety net)
        await seed_tenants()
        t = await db.tenants.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    return {**t, "is_super_admin": is_super_admin(user)}


@router.get("/{tid}")
async def get_tenant(tid: str, user=Depends(current_user)) -> dict:
    if not is_super_admin(user) and user_tenant_id(user) != tid:
        raise HTTPException(status_code=403, detail="Permesso negato")
    t = await db.tenants.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    return t


@router.post("", status_code=201)
async def create_tenant(body: TenantBody, user=Depends(require_user("admin"))) -> dict:
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Solo super_admin")
    obj = Tenant(**body.model_dump()).model_dump()
    await db.tenants.insert_one(obj)
    obj.pop("_id", None)
    return obj


@router.patch("/{tid}")
async def update_tenant(tid: str, body: TenantBody,
                        user=Depends(require_user("admin"))) -> dict:
    if not is_super_admin(user) and user_tenant_id(user) != tid:
        raise HTTPException(status_code=403, detail="Permesso negato")
    payload = {**body.model_dump(exclude_unset=True), "updated_at": _now_iso()}
    res = await db.tenants.update_one({"id": tid}, {"$set": payload})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    return await db.tenants.find_one({"id": tid}, {"_id": 0})


@router.delete("/{tid}")
async def delete_tenant(tid: str, user=Depends(require_user("admin"))) -> dict:
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Solo super_admin")
    if tid == TENANT_PRINCIPALE_ID:
        raise HTTPException(status_code=400, detail="Impossibile eliminare il tenant principale")
    await db.tenants.update_one({"id": tid}, {"$set": {"attivo": False, "updated_at": _now_iso()}})
    return {"ok": True}


@router.post("/migrate-legacy")
async def migrate_legacy(user=Depends(require_user("admin"))) -> dict:
    """Idempotente: assegna `agenzia_tenant_id=TENANT_PRINCIPALE_ID` a tutti i
    documenti pre-esistenti privi del campo. Solo super_admin."""
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Solo super_admin")
    await seed_tenants()
    report = await migrate_existing_data_to_principale()
    return {"ok": True, "report": report}
