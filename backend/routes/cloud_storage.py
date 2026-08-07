"""Cloud Storage OAuth integration (Google Drive + Microsoft OneDrive).

Ogni tenant può collegare uno o più account cloud (Google Drive, OneDrive) per
sincronizzare i documenti PDF generati dal CRM (polizze, quietanze, sinistri).

Sicurezza multi-tenant:
- Il tenant è SEMPRE ricavato dal JWT (never from client input).
- Il refresh_token è cifrato con Fernet prima dello storage.
- Ogni query MongoDB include `tenant_id` per garantire isolamento.

Endpoints:
  GET  /api/librerie/cloud-storage/oauth-url?provider=google_drive|onedrive
  GET  /api/librerie/cloud-storage/callback
  GET  /api/librerie/cloud-storage/status
  POST /api/librerie/cloud-storage/upload
  DELETE /api/librerie/cloud-storage/disconnect?provider=...
  GET  /api/librerie/cloud-storage/folders?provider=...

Playbook di riferimento (integrations expert v2): OAuth 2.0 authorization code flow,
Google `drive.file` scope, Microsoft `Files.ReadWrite offline_access`.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse

from auth import current_user
from database import db

router = APIRouter(prefix="/librerie/cloud-storage", tags=["cloud-storage"])

# ============================================================
# Config da environment
# ============================================================
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_DRIVE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET", "")
MS_CLIENT_ID = os.environ.get("MS_ONEDRIVE_CLIENT_ID", "")
MS_CLIENT_SECRET = os.environ.get("MS_ONEDRIVE_CLIENT_SECRET", "")
MS_TENANT = os.environ.get("MS_ONEDRIVE_TENANT", "common")
ENC_KEY = os.environ.get("CLOUD_STORAGE_ENCRYPTION_KEY", "")
BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL") or BACKEND_PUBLIC_URL

REDIRECT_URI = f"{BACKEND_PUBLIC_URL}/api/librerie/cloud-storage/callback" if BACKEND_PUBLIC_URL else ""

G_SCOPE = "https://www.googleapis.com/auth/drive.file"
M_SCOPE = "openid profile offline_access Files.ReadWrite User.Read"

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not ENC_KEY:
            raise HTTPException(500, "CLOUD_STORAGE_ENCRYPTION_KEY non configurata in backend/.env")
        _fernet = Fernet(ENC_KEY.encode() if isinstance(ENC_KEY, str) else ENC_KEY)
    return _fernet


def _enc(v: str) -> str:
    return _get_fernet().encrypt(v.encode()).decode()


def _dec(v: str) -> str:
    return _get_fernet().decrypt(v.encode()).decode()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_id(user: dict) -> str:
    """Ricava il tenant_id dall'utente autenticato."""
    return user.get("agenzia_tenant_id") or user.get("tenant_id") or "default"


def _provider_cfg(provider: str) -> dict:
    """Ritorna la config OAuth per il provider richiesto."""
    if provider == "google_drive":
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                501,
                "Google Drive non configurato. Aggiungi GOOGLE_DRIVE_CLIENT_ID e "
                "GOOGLE_DRIVE_CLIENT_SECRET in backend/.env (vedi Librerie → Cloud Storage → istruzioni)",
            )
        return {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scope": G_SCOPE,
        }
    if provider == "onedrive":
        if not MS_CLIENT_ID or not MS_CLIENT_SECRET:
            raise HTTPException(
                501,
                "OneDrive non configurato. Aggiungi MS_ONEDRIVE_CLIENT_ID e "
                "MS_ONEDRIVE_CLIENT_SECRET in backend/.env",
            )
        base = f"https://login.microsoftonline.com/{MS_TENANT}/oauth2/v2.0"
        return {
            "auth_url": f"{base}/authorize",
            "token_url": f"{base}/token",
            "client_id": MS_CLIENT_ID,
            "client_secret": MS_CLIENT_SECRET,
            "scope": M_SCOPE,
        }
    raise HTTPException(400, "Provider non valido: usa 'google_drive' o 'onedrive'")


# ============================================================
# ENDPOINTS
# ============================================================
@router.get("/config-status")
async def config_status(user=Depends(current_user)):
    """Ritorna lo stato di configurazione dei provider (per l'UI Librerie)."""
    return {
        "google_drive": {
            "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            "redirect_uri": REDIRECT_URI,
        },
        "onedrive": {
            "configured": bool(MS_CLIENT_ID and MS_CLIENT_SECRET),
            "redirect_uri": REDIRECT_URI,
        },
        "encryption_configured": bool(ENC_KEY),
    }


@router.get("/oauth-url")
async def oauth_url(
    provider: str = Query(..., regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    """Genera l'authorize URL con un `state` random legato al tenant/utente."""
    if not REDIRECT_URI:
        raise HTTPException(500, "BACKEND_PUBLIC_URL non configurato in backend/.env")
    cfg = _provider_cfg(provider)
    state = secrets.token_urlsafe(32)
    await db.cloud_oauth_states.insert_one({
        "_id": state,
        "tenant_id": _tenant_id(user),
        "user_id": user.get("id"),
        "provider": provider,
        "expires_at": _now() + timedelta(minutes=10),
    })
    q = {
        "client_id": cfg["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
        "access_type": "offline",
        "include_granted_scopes": "true",
    }
    if provider == "google_drive":
        q["prompt"] = "consent"  # forza il refresh_token
    else:
        q["response_mode"] = "query"
    return {
        "authorize_url": f"{cfg['auth_url']}?{urlencode(q)}",
        "provider": provider,
    }


@router.get("/callback")
async def oauth_callback(code: str = Query(...), state: str = Query(...),
                         error: Optional[str] = Query(None)):
    """Callback OAuth: scambia il code per il refresh_token e lo salva."""
    if error:
        raise HTTPException(400, f"OAuth error: {error}")
    st = await db.cloud_oauth_states.find_one_and_delete({"_id": state})
    if not st:
        raise HTTPException(400, "state non valido o già usato")
    if st["expires_at"] < _now():
        raise HTTPException(400, "state scaduto — riprova")
    provider = st["provider"]
    cfg = _provider_cfg(provider)
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.post(cfg["token_url"], data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": cfg["scope"],
        })
    if r.is_error:
        raise HTTPException(502, f"Token exchange fallito: {r.text[:200]}")
    t = r.json()
    refresh = t.get("refresh_token")
    if not refresh:
        # Se non c'è il refresh (utente che ricollega su Google senza revoca), usa il vecchio
        old = await db.cloud_connections.find_one({
            "tenant_id": st["tenant_id"],
            "user_id": st["user_id"],
            "provider": provider,
        })
        if old:
            refresh = _dec(old["refresh_token"])
    if not refresh:
        raise HTTPException(
            400,
            "Nessun refresh_token restituito. Revoca l'accesso dall'account provider e riprova.",
        )
    await db.cloud_connections.update_one(
        {"tenant_id": st["tenant_id"], "user_id": st["user_id"], "provider": provider},
        {"$set": {
            "refresh_token": _enc(refresh),
            "scopes": t.get("scope", cfg["scope"]),
            "connected_at": _now().isoformat(),
            "folder_id": None,
        }},
        upsert=True,
    )
    # Redirect al frontend Librerie
    frontend_target = (FRONTEND_URL or BACKEND_PUBLIC_URL).rstrip("/")
    return RedirectResponse(
        f"{frontend_target}/librerie?cloud=connected&provider={provider}",
        status_code=302,
    )


async def _fresh_access_token(provider: str, connection: dict) -> str:
    """Refresh dell'access_token via refresh_token. Se il provider fa rotation,
    salva il nuovo refresh_token in DB."""
    cfg = _provider_cfg(provider)
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.post(cfg["token_url"], data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": _dec(connection["refresh_token"]),
            "grant_type": "refresh_token",
            "scope": cfg["scope"],
        })
    if r.status_code in (400, 401):
        # Token revocato: rimuovi la connessione
        await db.cloud_connections.delete_one({"_id": connection.get("_id")}) if connection.get("_id") else None
        await db.cloud_connections.delete_one({
            "tenant_id": connection["tenant_id"],
            "user_id": connection["user_id"],
            "provider": provider,
        })
        raise HTTPException(401, "Cloud account disconnesso — ricollega dall'UI")
    r.raise_for_status()
    data = r.json()
    if data.get("refresh_token"):
        # MS ruota i refresh token — aggiorna atomically
        await db.cloud_connections.update_one(
            {"tenant_id": connection["tenant_id"], "user_id": connection["user_id"],
             "provider": provider},
            {"$set": {"refresh_token": _enc(data["refresh_token"])}},
        )
    return data["access_token"]


@router.get("/status")
async def status(user=Depends(current_user)):
    """Ritorna le connessioni attive del tenant/utente."""
    tenant = _tenant_id(user)
    rows = db.cloud_connections.find(
        {"tenant_id": tenant, "user_id": user.get("id")},
        {"_id": 0, "provider": 1, "folder_id": 1, "folder_name": 1,
         "connected_at": 1, "scopes": 1},
    )
    connections = [
        {
            "provider": r["provider"],
            "connected": True,
            "folder_id": r.get("folder_id"),
            "folder_name": r.get("folder_name"),
            "connected_at": r.get("connected_at"),
        }
        async for r in rows
    ]
    return {"connections": connections}


@router.delete("/disconnect")
async def disconnect(
    provider: str = Query(..., regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    await db.cloud_connections.delete_one({
        "tenant_id": _tenant_id(user),
        "user_id": user.get("id"),
        "provider": provider,
    })
    return {"disconnected": provider}


class SetFolderBody:
    """Utility per parsare form data del set-folder."""
    pass


@router.post("/set-folder")
async def set_folder(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    folder_id: Optional[str] = Form(None),
    folder_name: Optional[str] = Form(None),
    user=Depends(current_user),
):
    """Salva la cartella di destinazione (o root se folder_id=None)."""
    r = await db.cloud_connections.update_one(
        {"tenant_id": _tenant_id(user), "user_id": user.get("id"), "provider": provider},
        {"$set": {"folder_id": folder_id or None, "folder_name": folder_name or None}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Account non collegato")
    return {"ok": True, "folder_id": folder_id, "folder_name": folder_name}


@router.get("/folders")
async def list_folders(
    provider: str = Query(..., regex="^(google_drive|onedrive)$"),
    parent_id: Optional[str] = Query(None),
    user=Depends(current_user),
):
    """Lista le cartelle dell'account (per la selezione destinazione)."""
    conn = await db.cloud_connections.find_one({
        "tenant_id": _tenant_id(user),
        "user_id": user.get("id"),
        "provider": provider,
    })
    if not conn:
        raise HTTPException(409, "Account non collegato")
    token = await _fresh_access_token(provider, conn)
    if provider == "google_drive":
        parent = parent_id or "root"
        q = (f"mimeType='application/vnd.google-apps.folder' and trashed=false "
             f"and '{parent}' in parents")
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": q, "fields": "files(id,name)", "pageSize": 100},
            )
        r.raise_for_status()
        return {"folders": [{"id": f["id"], "name": f["name"]} for f in r.json().get("files", [])]}
    # OneDrive
    if parent_id and parent_id != "root":
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{parent_id}/children"
    else:
        url = "https://graph.microsoft.com/v1.0/me/drive/root/children"
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.get(url, headers={"Authorization": f"Bearer {token}"},
                        params={"$filter": "folder ne null", "$select": "id,name,folder"})
    r.raise_for_status()
    items = r.json().get("value", [])
    return {"folders": [{"id": it["id"], "name": it["name"]}
                        for it in items if it.get("folder")]}


@router.post("/upload")
async def upload_file(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    file: UploadFile = File(...),
    folder_id: Optional[str] = Form(None),
    user=Depends(current_user),
):
    """Carica un file PDF sul cloud storage collegato del tenant."""
    conn = await db.cloud_connections.find_one({
        "tenant_id": _tenant_id(user),
        "user_id": user.get("id"),
        "provider": provider,
    })
    if not conn:
        raise HTTPException(409, "Account non collegato per questo provider")
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "File troppo grande (max 50 MB)")
    name = file.filename or "documento.pdf"
    mime = file.content_type or "application/pdf"
    token = await _fresh_access_token(provider, conn)
    target_folder = folder_id or conn.get("folder_id")

    if provider == "google_drive":
        metadata: dict = {"name": name, "mimeType": mime}
        if target_folder:
            metadata["parents"] = [target_folder]
        async with httpx.AsyncClient(timeout=120) as x:
            r = await x.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                headers={"Authorization": f"Bearer {token}"},
                files={
                    "metadata": ("metadata", json.dumps(metadata), "application/json"),
                    "file": (name, data, mime),
                },
            )
        r.raise_for_status()
        info = r.json()
        return {"provider": provider, "id": info.get("id"),
                "name": name, "size": len(data)}

    # OneDrive: se <4MB usa PUT semplice, altrimenti upload session
    parent = target_folder or "root"
    if len(data) < 4 * 1024 * 1024:
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{parent}:/{name}:/content"
        async with httpx.AsyncClient(timeout=120) as x:
            r = await x.put(url, headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": mime},
                            content=data)
        r.raise_for_status()
        info = r.json()
        return {"provider": provider, "id": info.get("id"),
                "name": name, "size": len(data)}
    # Upload session per file grandi
    session_url = (f"https://graph.microsoft.com/v1.0/me/drive/items/{parent}:/{name}"
                   f":/createUploadSession")
    async with httpx.AsyncClient(timeout=120) as x:
        r = await x.post(session_url, headers={"Authorization": f"Bearer {token}"},
                         json={"item": {"@microsoft.graph.conflictBehavior": "replace"}})
        r.raise_for_status()
        upload_url = r.json()["uploadUrl"]
        chunk = 10 * 320 * 1024   # 3.2 MB — multiplo di 320 KiB
        pos = 0
        last: Optional[dict] = None
        while pos < len(data):
            part = data[pos:pos + chunk]
            end = pos + len(part) - 1
            q = await x.put(upload_url, content=part, headers={
                "Content-Length": str(len(part)),
                "Content-Range": f"bytes {pos}-{end}/{len(data)}",
            })
            if q.status_code not in (200, 201, 202):
                q.raise_for_status()
            if q.status_code in (200, 201):
                last = q.json()
            pos = end + 1
        return {"provider": provider, "id": (last or {}).get("id"),
                "name": name, "size": len(data)}
