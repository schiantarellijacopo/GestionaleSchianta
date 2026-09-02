"""Link pubblico per caricamento documenti dal cliente.

Quando un alert (o un operatore) chiede al cliente un documento mancante/scaduto
(es. libretto veicolo), si genera un LINK sicuro con token. Il cliente apre il
link, carica il file SENZA login e lo ritroviamo negli allegati dell'anagrafica.

- Endpoint autenticati: creazione/lista link.
- Endpoint PUBBLICI (no auth): info link + upload. Il tenant viene risolto dal
  token (collection `upload_links` GLOBALE via raw_db) e il file viene scritto
  impostando il ContextVar sul tenant del link.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from database import db, raw_db, set_current_user, reset_current_user
from auth import require_user
from db_models import _now_iso, _uid, Allegato
from tenant import user_tenant_id, TENANT_PRINCIPALE_ID
import storage as obj_storage

router = APIRouter(tags=["upload-link"])

_ROLES = ("admin", "collaboratore", "dipendente")
_MAX = 20 * 1024 * 1024


def _public_base() -> str:
    return (os.environ.get("BACKEND_PUBLIC_URL") or "").rstrip("/")


def _full_url(token: str) -> str:
    base = _public_base()
    return f"{base}/carica/{token}" if base else f"/carica/{token}"


class CreateLinkBody(BaseModel):
    anagrafica_id: str
    descrizione: str
    polizza_id: Optional[str] = None
    giorni_validita: int = 14


@router.post("/upload-links")
async def create_upload_link(body: CreateLinkBody, user: dict = Depends(require_user(*_ROLES))) -> dict:
    ana = await db.anagrafiche.find_one({"id": body.anagrafica_id}, {"_id": 0, "id": 1, "ragione_sociale": 1})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    doc = {
        "id": _uid(),
        "token": token,
        "agenzia_tenant_id": tid,
        "anagrafica_id": body.anagrafica_id,
        "anagrafica_nome": ana.get("ragione_sociale"),
        "polizza_id": body.polizza_id,
        "descrizione": body.descrizione.strip() or "Documento richiesto",
        "created_by": user.get("id"),
        "created_at": _now_iso(),
        "expires_at": (now + timedelta(days=max(1, body.giorni_validita))).isoformat(),
        "used": False,
        "uploads": [],
    }
    await raw_db.upload_links.insert_one(doc.copy())
    return {"token": token, "url": _full_url(token), "descrizione": doc["descrizione"], "expires_at": doc["expires_at"]}


@router.get("/upload-links")
async def list_upload_links(anagrafica_id: str, user: dict = Depends(require_user(*_ROLES))) -> list[dict]:
    tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
    items = await raw_db.upload_links.find(
        {"agenzia_tenant_id": tid, "anagrafica_id": anagrafica_id}, {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    for it in items:
        it["url"] = _full_url(it["token"])
    return items


@router.delete("/upload-links/{lid}")
async def delete_upload_link(lid: str, user: dict = Depends(require_user(*_ROLES))) -> dict:
    tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
    await raw_db.upload_links.delete_one({"id": lid, "agenzia_tenant_id": tid})
    return {"ok": True}


# ============================================================
# PUBBLICI — nessuna autenticazione
# ============================================================
async def _get_link(token: str) -> dict:
    link = await raw_db.upload_links.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(404, "Link non valido")
    return link


@router.get("/public/upload/{token}")
async def public_link_info(token: str) -> dict:
    link = await _get_link(token)
    scaduto = bool(link.get("expires_at") and link["expires_at"] < _now_iso())
    tenant = await raw_db.tenants.find_one({"id": link["agenzia_tenant_id"]}, {"_id": 0, "ragione_sociale": 1, "nome": 1})
    return {
        "descrizione": link.get("descrizione"),
        "cliente_nome": link.get("anagrafica_nome"),
        "agenzia_nome": (tenant or {}).get("ragione_sociale") or (tenant or {}).get("nome") or "La tua agenzia",
        "scaduto": scaduto,
        "n_caricati": len(link.get("uploads") or []),
    }


@router.post("/public/upload/{token}")
async def public_upload(token: str, file: UploadFile = File(...)) -> dict:
    link = await _get_link(token)
    if link.get("expires_at") and link["expires_at"] < _now_iso():
        raise HTTPException(410, "Link scaduto: contatta la tua agenzia")
    data = await file.read()
    if len(data) > _MAX:
        raise HTTPException(413, "File troppo grande (max 20 MB)")
    if len(data) == 0:
        raise HTTPException(400, "File vuoto")
    tid = link["agenzia_tenant_id"]
    ctx = set_current_user({"id": "public-upload", "role": "admin", "agenzia_tenant_id": tid, "is_super_admin": False})
    try:
        ct = file.content_type or obj_storage.mime_for(file.filename or "")
        ext = (file.filename or "documento.bin").rsplit(".", 1)[-1].lower() or "bin"
        path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{link['anagrafica_id']}/richiesta_{_uid()}.{ext}"
        result = obj_storage.put_object(path, data, ct)
        alleg = Allegato(
            entita_tipo="anagrafica", entita_id=link["anagrafica_id"],
            nome_file=file.filename or f"documento.{ext}",
            storage_path=result["path"], content_type=ct, size=len(data),
            descrizione=f"Caricato dal cliente via link — {link.get('descrizione')}",
            categoria="richiesta_cliente", visibile_cliente=False,
        )
        await db.allegati.insert_one(alleg.model_dump())
    finally:
        reset_current_user(ctx)
    up = {"nome_file": file.filename, "storage_path": result["path"], "at": _now_iso()}
    await raw_db.upload_links.update_one(
        {"token": token}, {"$push": {"uploads": up}, "$set": {"used": True, "used_at": _now_iso()}})
    return {"ok": True, "nome_file": file.filename}
