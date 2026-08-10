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

G_SCOPE = "https://www.googleapis.com/auth/drive"
M_SCOPE = "openid profile offline_access Files.ReadWrite User.Read"

# Struttura cartelle standard che il CRM crea automaticamente quando l'agenzia
# clicca "Crea struttura cartelle" (o al primo upload di ogni categoria).
# Ogni categoria è una tupla (path_segments, descrizione).
STANDARD_FOLDER_STRUCTURE: dict = {
    "root": ["Assicura CRM"],
    "inbox": ["Assicura CRM", "INBOX"],
    "da_smistare": ["Assicura CRM", "Da smistare manualmente"],
    "contraenti": ["Assicura CRM", "Contraenti"],
    "contraente_privacy": ["Assicura CRM", "Contraenti", "{cliente}", "Privacy"],
    "contraente_identita": ["Assicura CRM", "Contraenti", "{cliente}", "Carta d'Identità"],
    "contraente_codice_fiscale": ["Assicura CRM", "Contraenti", "{cliente}", "Codice Fiscale"],
    "contraente_altri": ["Assicura CRM", "Contraenti", "{cliente}", "Altri Documenti"],
    "polizze": ["Assicura CRM", "Polizze"],
    "polizza_condizioni": ["Assicura CRM", "Polizze", "{polizza}", "Condizioni di Polizza"],
    "polizza_documenti": ["Assicura CRM", "Polizze", "{polizza}", "Documenti di Polizza"],
    "quietanze": ["Assicura CRM", "Quietanze"],
    "quietanze_anno": ["Assicura CRM", "Quietanze", "{anno}"],
    "sinistri": ["Assicura CRM", "Sinistri"],
    "sinistro_specifico": ["Assicura CRM", "Sinistri", "{sinistro}"],
    "contabilita": ["Assicura CRM", "Contabilità"],
    "contabilita_prima_nota": ["Assicura CRM", "Contabilità", "Prima Nota", "{anno}", "{mese}"],
    "contabilita_estratti": ["Assicura CRM", "Contabilità", "Estratti Conto Compagnie", "{anno}"],
    "contabilita_provvigioni": ["Assicura CRM", "Contabilità", "Provvigioni Collaboratori", "{anno}"],
}

# Categorie che vengono create SUBITO al primo setup (senza placeholder).
INIT_CATEGORIES = [
    "root", "inbox", "da_smistare", "contraenti", "polizze",
    "quietanze", "sinistri", "contabilita",
]

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


async def _load_tenant_config(tenant_id: str, provider: str) -> dict:
    """Carica config OAuth per tenant: prima cerca in MongoDB, poi fallback su ENV.

    Consente all'admin di ogni agenzia di configurare le proprie credenziali OAuth
    dall'interfaccia (Librerie → Cloud Storage → Configurazione admin), senza dover
    modificare il file .env.
    """
    doc = await db.cloud_oauth_configs.find_one(
        {"tenant_id": tenant_id, "provider": provider},
    )
    if doc and doc.get("client_id") and doc.get("client_secret_enc"):
        return {
            "client_id": doc["client_id"],
            "client_secret": _dec(doc["client_secret_enc"]),
            "source": "db",
        }
    # Fallback su ENV
    if provider == "google_drive":
        if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
            return {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "source": "env"}
    elif provider == "onedrive":
        if MS_CLIENT_ID and MS_CLIENT_SECRET:
            return {"client_id": MS_CLIENT_ID, "client_secret": MS_CLIENT_SECRET, "source": "env"}
    return {}


async def _provider_cfg_async(provider: str, tenant_id: str) -> dict:
    """Ritorna la config OAuth per il provider richiesto (versione async con tenant)."""
    creds = await _load_tenant_config(tenant_id, provider)
    if not creds:
        label = "Google Drive" if provider == "google_drive" else "OneDrive"
        raise HTTPException(
            501,
            f"{label} non configurato per questa agenzia. Vai su Librerie → "
            f"Cloud Storage → Configurazione admin e incolla Client ID e Client Secret.",
        )
    if provider == "google_drive":
        return {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "scope": G_SCOPE,
        }
    base = f"https://login.microsoftonline.com/{MS_TENANT}/oauth2/v2.0"
    return {
        "auth_url": f"{base}/authorize",
        "token_url": f"{base}/token",
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "scope": M_SCOPE,
    }


def _provider_cfg(provider: str) -> dict:
    """Legacy sync helper — usa solo ENV. Preferire _provider_cfg_async."""
    if provider == "google_drive":
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise HTTPException(501, "Google Drive non configurato")
        return {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scope": G_SCOPE,
        }
    if provider == "onedrive":
        if not MS_CLIENT_ID or not MS_CLIENT_SECRET:
            raise HTTPException(501, "OneDrive non configurato")
        base = f"https://login.microsoftonline.com/{MS_TENANT}/oauth2/v2.0"
        return {
            "auth_url": f"{base}/authorize",
            "token_url": f"{base}/token",
            "client_id": MS_CLIENT_ID,
            "client_secret": MS_CLIENT_SECRET,
            "scope": M_SCOPE,
        }
    raise HTTPException(400, "Provider non valido")


# ============================================================
# ENDPOINTS
# ============================================================
@router.get("/config-status")
async def config_status(user=Depends(current_user)):
    """Ritorna lo stato di configurazione dei provider per l'agenzia dell'utente.

    Cerca prima le credenziali salvate in DB (per il tenant), poi fallback su ENV.
    """
    tenant = _tenant_id(user)
    g_cfg = await _load_tenant_config(tenant, "google_drive")
    m_cfg = await _load_tenant_config(tenant, "onedrive")
    return {
        "google_drive": {
            "configured": bool(g_cfg),
            "source": g_cfg.get("source") if g_cfg else None,
            "client_id_masked": _mask(g_cfg.get("client_id")) if g_cfg else None,
            "redirect_uri": REDIRECT_URI,
        },
        "onedrive": {
            "configured": bool(m_cfg),
            "source": m_cfg.get("source") if m_cfg else None,
            "client_id_masked": _mask(m_cfg.get("client_id")) if m_cfg else None,
            "redirect_uri": REDIRECT_URI,
        },
        "encryption_configured": bool(ENC_KEY),
        "tenant_id": tenant,
    }


def _mask(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return v[:8] + "…" + v[-4:] if len(v) > 15 else v[:4] + "…"


@router.post("/admin-config")
async def save_admin_config(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    user=Depends(current_user),
):
    """Salva/aggiorna le credenziali OAuth per l'agenzia (solo admin dell'agenzia).

    Le credenziali sono cifrate con Fernet prima di essere salvate.
    Una volta salvate, tutti gli utenti dell'agenzia possono collegare il proprio
    account cloud usando queste credenziali (ma la connessione è unica per agenzia).
    """
    if (user.get("role") or "").lower() not in ("admin", "superadmin"):
        raise HTTPException(403, "Solo gli amministratori dell'agenzia possono configurare le credenziali OAuth")
    cid = (client_id or "").strip()
    sec = (client_secret or "").strip()
    if not cid or not sec:
        raise HTTPException(400, "client_id e client_secret sono obbligatori")
    tenant = _tenant_id(user)
    await db.cloud_oauth_configs.update_one(
        {"tenant_id": tenant, "provider": provider},
        {"$set": {
            "client_id": cid,
            "client_secret_enc": _enc(sec),
            "updated_at": _now().isoformat(),
            "updated_by": user.get("email") or user.get("id"),
        }},
        upsert=True,
    )
    return {"ok": True, "provider": provider, "client_id_masked": _mask(cid)}


@router.delete("/admin-config")
async def delete_admin_config(
    provider: str = Query(..., regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    """Rimuove le credenziali OAuth salvate per l'agenzia (torna al fallback ENV)."""
    if (user.get("role") or "").lower() not in ("admin", "superadmin"):
        raise HTTPException(403, "Solo gli amministratori dell'agenzia possono rimuovere le credenziali OAuth")
    tenant = _tenant_id(user)
    await db.cloud_oauth_configs.delete_one({"tenant_id": tenant, "provider": provider})
    # Rimuove anche eventuali connessioni attive di quell'agenzia (ora invalide)
    await db.cloud_connections.delete_many({"tenant_id": tenant, "provider": provider})
    return {"ok": True, "provider": provider}


@router.get("/oauth-url")
async def oauth_url(
    provider: str = Query(..., regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    """Genera l'authorize URL con un `state` random legato al tenant/utente."""
    if not REDIRECT_URI:
        raise HTTPException(500, "BACKEND_PUBLIC_URL non configurato in backend/.env")
    tenant = _tenant_id(user)
    cfg = await _provider_cfg_async(provider, tenant)
    state = secrets.token_urlsafe(32)
    await db.cloud_oauth_states.insert_one({
        "_id": state,
        "tenant_id": tenant,
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
    """Callback OAuth: scambia il code per il refresh_token e lo salva.

    Il collegamento è per AGENZIA (tenant), non per utente. Il primo utente della
    stessa agenzia che completa OAuth diventa il "proprietario del cloud aziendale".
    Se un altro utente della stessa agenzia connette lo stesso provider, sovrascrive.
    """
    if error:
        raise HTTPException(400, f"OAuth error: {error}")
    st = await db.cloud_oauth_states.find_one_and_delete({"_id": state})
    if not st:
        raise HTTPException(400, "state non valido o già usato")
    # MongoDB può restituire il datetime offset-naive: normalizza a UTC-aware per il confronto
    exp = st["expires_at"]
    if isinstance(exp, datetime) and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < _now():
        raise HTTPException(400, "state scaduto — riprova")
    provider = st["provider"]
    cfg = await _provider_cfg_async(provider, st["tenant_id"])
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
        # Se non c'è il refresh (utente che ricollega senza revoca), usa il vecchio
        old = await db.cloud_connections.find_one({
            "tenant_id": st["tenant_id"], "provider": provider,
        })
        if old:
            refresh = _dec(old["refresh_token"])
    if not refresh:
        raise HTTPException(
            400,
            "Nessun refresh_token restituito. Revoca l'accesso dall'account provider e riprova.",
        )
    # UPSERT per tenant (1 drive per agenzia)
    await db.cloud_connections.update_one(
        {"tenant_id": st["tenant_id"], "provider": provider},
        {"$set": {
            "refresh_token": _enc(refresh),
            "scopes": t.get("scope", cfg["scope"]),
            "connected_at": _now().isoformat(),
            "connected_by": st["user_id"],
            "folder_id": None,
        }},
        upsert=True,
    )
    frontend_target = (FRONTEND_URL or BACKEND_PUBLIC_URL).rstrip("/")
    return RedirectResponse(
        f"{frontend_target}/librerie?cloud=connected&provider={provider}",
        status_code=302,
    )


async def _fresh_access_token(provider: str, connection: dict) -> str:
    """Refresh dell'access_token via refresh_token."""
    tenant = connection["tenant_id"]
    cfg = await _provider_cfg_async(provider, tenant)
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.post(cfg["token_url"], data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "refresh_token": _dec(connection["refresh_token"]),
            "grant_type": "refresh_token",
        })
    if r.status_code in (400, 401):
        # Token revocato: rimuovi la connessione
        await db.cloud_connections.delete_one({
            "tenant_id": tenant, "provider": provider,
        })
        raise HTTPException(401, "Cloud account disconnesso — ricollega dall'UI")
    r.raise_for_status()
    data = r.json()
    if data.get("refresh_token"):
        # MS ruota i refresh token — aggiorna atomically
        await db.cloud_connections.update_one(
            {"tenant_id": tenant, "provider": provider},
            {"$set": {"refresh_token": _enc(data["refresh_token"])}},
        )
    return data["access_token"]


@router.get("/status")
async def status(user=Depends(current_user)):
    """Ritorna le connessioni attive dell'agenzia (1 max per provider)."""
    tenant = _tenant_id(user)
    rows = db.cloud_connections.find(
        {"tenant_id": tenant},
        {"_id": 0, "provider": 1, "folder_id": 1, "folder_name": 1,
         "connected_at": 1, "scopes": 1, "connected_by": 1},
    )
    connections = [
        {
            "provider": r["provider"],
            "connected": True,
            "folder_id": r.get("folder_id"),
            "folder_name": r.get("folder_name"),
            "connected_at": r.get("connected_at"),
            "connected_by": r.get("connected_by"),
        }
        async for r in rows
    ]
    return {"connections": connections, "tenant_id": tenant}


@router.delete("/disconnect")
async def disconnect(
    provider: str = Query(..., regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    tenant = _tenant_id(user)
    if (user.get("role") or "").lower() not in ("admin", "superadmin"):
        raise HTTPException(403, "Solo gli amministratori dell'agenzia possono scollegare il cloud")
    await db.cloud_connections.delete_one({
        "tenant_id": tenant, "provider": provider,
    })
    return {"disconnected": provider}


@router.post("/set-folder")
async def set_folder(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    folder_id: Optional[str] = Form(None),
    folder_name: Optional[str] = Form(None),
    user=Depends(current_user),
):
    """Salva la cartella di destinazione (o root se folder_id=None). Per l'intera agenzia."""
    r = await db.cloud_connections.update_one(
        {"tenant_id": _tenant_id(user), "provider": provider},
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
        "tenant_id": _tenant_id(user), "provider": provider,
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
    """Carica un file PDF sul cloud storage dell'agenzia."""
    conn = await db.cloud_connections.find_one({
        "tenant_id": _tenant_id(user), "provider": provider,
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
        chunk = 10 * 320 * 1024
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



# ============================================================
# GESTIONE STRUTTURA CARTELLE
# ============================================================
def _sanitize_folder_name(name: str) -> str:
    """Sanitizza il nome cartella (rimuove caratteri illegali su Drive/OneDrive)."""
    if not name:
        return "senza-nome"
    bad = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    s = str(name).strip()
    for ch in bad:
        s = s.replace(ch, '-')
    return s[:120] or "senza-nome"


async def _find_folder(provider: str, token: str, name: str, parent_id: Optional[str]) -> Optional[str]:
    """Cerca una cartella con `name` sotto `parent_id`. Ritorna l'id se esiste."""
    if provider == "google_drive":
        parent = parent_id or "root"
        safe = name.replace("'", "\\'")
        q = (f"mimeType='application/vnd.google-apps.folder' and trashed=false "
             f"and name='{safe}' and '{parent}' in parents")
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": q, "fields": "files(id,name)", "pageSize": 5},
            )
        r.raise_for_status()
        files = r.json().get("files", [])
        return files[0]["id"] if files else None
    # OneDrive
    if parent_id and parent_id != "root":
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{parent_id}/children"
    else:
        url = "https://graph.microsoft.com/v1.0/me/drive/root/children"
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.get(url, headers={"Authorization": f"Bearer {token}"},
                        params={"$filter": f"name eq '{name}' and folder ne null",
                                "$select": "id,name,folder"})
    r.raise_for_status()
    items = r.json().get("value", [])
    for it in items:
        if it.get("folder"):
            return it["id"]
    return None


async def _create_folder(provider: str, token: str, name: str,
                         parent_id: Optional[str]) -> str:
    """Crea una cartella (senza controllare duplicati)."""
    if provider == "google_drive":
        body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            body["parents"] = [parent_id]
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.post(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json=body,
            )
        r.raise_for_status()
        return r.json()["id"]
    # OneDrive
    if parent_id and parent_id != "root":
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{parent_id}/children"
    else:
        url = "https://graph.microsoft.com/v1.0/me/drive/root/children"
    body = {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.post(url, headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json"},
                         json=body)
    r.raise_for_status()
    return r.json()["id"]


async def _ensure_folder_path(provider: str, token: str, segments: list,
                              tenant_id: str) -> str:
    """Naviga o crea ogni segmento del path. Usa cache per tenant."""
    cache_key = "/".join(segments)
    cache = await db.cloud_folder_cache.find_one({
        "tenant_id": tenant_id, "provider": provider, "path": cache_key,
    })
    if cache and cache.get("folder_id"):
        return cache["folder_id"]
    parent: Optional[str] = None
    for seg in segments:
        seg_clean = _sanitize_folder_name(seg)
        found = await _find_folder(provider, token, seg_clean, parent)
        parent = found or await _create_folder(provider, token, seg_clean, parent)
    if parent:
        await db.cloud_folder_cache.update_one(
            {"tenant_id": tenant_id, "provider": provider, "path": cache_key},
            {"$set": {"folder_id": parent, "created_at": _now().isoformat()}},
            upsert=True,
        )
    return parent or ""


async def _resolve_category_path(category: str, context: dict) -> list:
    """Espande i placeholder ({cliente}, {polizza}, ecc.) nei path standard."""
    template = STANDARD_FOLDER_STRUCTURE.get(category)
    if not template:
        raise HTTPException(400, f"Categoria cartella non valida: {category}")
    ctx = {
        "cliente": _sanitize_folder_name(context.get("cliente", "")),
        "polizza": _sanitize_folder_name(context.get("polizza", "")),
        "sinistro": _sanitize_folder_name(context.get("sinistro", "")),
        "anno": str(context.get("anno") or _now().year),
        "mese": f"{int(context.get('mese') or _now().month):02d}",
    }
    return [seg.format(**ctx) if "{" in seg else seg for seg in template]


@router.post("/init-structure")
async def init_structure(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    """Crea la struttura di cartelle base dell'agenzia:
       Assicura CRM/
       ├── Contraenti/
       ├── Polizze/
       ├── Quietanze/{anno}/
       ├── Sinistri/
       └── Contabilità/{Prima Nota, Estratti Conto, Provvigioni}/{anno}/
    """
    tenant = _tenant_id(user)
    conn = await db.cloud_connections.find_one({
        "tenant_id": tenant, "provider": provider,
    })
    if not conn:
        raise HTTPException(409, "Account non collegato per questo provider")
    token = await _fresh_access_token(provider, conn)

    created_paths = []
    initial = INIT_CATEGORIES + [
        "contabilita_prima_nota", "contabilita_estratti",
        "contabilita_provvigioni", "quietanze_anno",
    ]
    for cat in initial:
        segments = await _resolve_category_path(cat, {})
        fid = await _ensure_folder_path(provider, token, segments, tenant)
        created_paths.append({
            "category": cat, "path": "/".join(segments), "folder_id": fid,
        })

    root_id = created_paths[0]["folder_id"]
    await db.cloud_connections.update_one(
        {"tenant_id": tenant, "provider": provider},
        {"$set": {
            "folder_id": root_id,
            "folder_name": "Assicura CRM",
            "structure_initialized_at": _now().isoformat(),
        }},
    )

    # Crea anche le sottocartelle INBOX (Polizze, Quietanze, Libretti, ...)
    # così l'utente può trascinare i file direttamente nella cartella corretta.
    try:
        from cloud_ocr_scanner import _ensure_inbox_subfolders
        inbox_segments = await _resolve_category_path("inbox", {})
        inbox_id = await _ensure_folder_path(provider, token, inbox_segments, tenant)
        inbox_subs = await _ensure_inbox_subfolders(provider, token, inbox_id)
        for sub_name, sub_id in inbox_subs.items():
            created_paths.append({
                "category": f"inbox/{sub_name}",
                "path": f"Assicura CRM/INBOX/{sub_name}",
                "folder_id": sub_id,
            })
    except Exception as e:
        # non blocca l'init: sono cartelle "hint", il flusso funziona anche senza
        created_paths.append({"category": "inbox_subfolders", "error": str(e)[:200]})

    return {"ok": True, "provider": provider, "created": created_paths}


@router.post("/upload-document")
async def upload_document(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    category: str = Form(..., description="es. contraente_privacy, polizza_condizioni"),
    file: UploadFile = File(...),
    cliente: Optional[str] = Form(None),
    polizza: Optional[str] = Form(None),
    sinistro: Optional[str] = Form(None),
    anno: Optional[int] = Form(None),
    mese: Optional[int] = Form(None),
    user=Depends(current_user),
):
    """Upload di un file nella cartella corretta secondo la struttura standard.

    Esempi:
      category=contraente_privacy, cliente="Rossi Mario"
        → Assicura CRM/Contraenti/Rossi Mario/Privacy/{file}
      category=polizza_condizioni, polizza="POL-2026-001"
        → Assicura CRM/Polizze/POL-2026-001/Condizioni di Polizza/{file}
      category=contabilita_prima_nota, anno=2026, mese=2
        → Assicura CRM/Contabilità/Prima Nota/2026/02/{file}
    """
    tenant = _tenant_id(user)
    conn = await db.cloud_connections.find_one({
        "tenant_id": tenant, "provider": provider,
    })
    if not conn:
        raise HTTPException(409, "Account non collegato per questo provider")
    token = await _fresh_access_token(provider, conn)
    ctx = {"cliente": cliente, "polizza": polizza, "sinistro": sinistro,
           "anno": anno, "mese": mese}
    segments = await _resolve_category_path(category, ctx)
    folder_id = await _ensure_folder_path(provider, token, segments, tenant)

    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "File troppo grande (max 50 MB)")
    name = file.filename or "documento.pdf"
    mime = file.content_type or "application/pdf"

    if provider == "google_drive":
        metadata = {"name": name, "mimeType": mime, "parents": [folder_id]}
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
        return {"provider": provider, "id": info.get("id"), "name": name,
                "size": len(data), "path": "/".join(segments)}

    # OneDrive
    if len(data) < 4 * 1024 * 1024:
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}:/{name}:/content"
        async with httpx.AsyncClient(timeout=120) as x:
            r = await x.put(url, headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": mime},
                            content=data)
        r.raise_for_status()
        info = r.json()
        return {"provider": provider, "id": info.get("id"), "name": name,
                "size": len(data), "path": "/".join(segments)}
    raise HTTPException(413, "Per file OneDrive >4MB usa /upload con folder_id esplicito")


@router.get("/categories")
async def list_categories(user=Depends(current_user)):
    """Ritorna le categorie di cartelle standard supportate (per l'UI)."""
    return {
        "categories": [
            {
                "key": k,
                "path_template": " / ".join(v),
                "placeholders": [seg for seg in v if "{" in seg],
            }
            for k, v in STANDARD_FOLDER_STRUCTURE.items()
        ],
    }


@router.post("/create-folder")
async def create_folder_manual(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    name: str = Form(...),
    parent_id: Optional[str] = Form(None),
    user=Depends(current_user),
):
    """Crea una cartella manuale (per il folder picker)."""
    tenant = _tenant_id(user)
    conn = await db.cloud_connections.find_one({
        "tenant_id": tenant, "provider": provider,
    })
    if not conn:
        raise HTTPException(409, "Account non collegato")
    token = await _fresh_access_token(provider, conn)
    safe = _sanitize_folder_name(name)
    fid = await _create_folder(provider, token, safe, parent_id)
    return {"ok": True, "id": fid, "name": safe}


@router.post("/ensure-inbox-subfolders")
async def ensure_inbox_subfolders(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    """Crea (se mancanti) le sottocartelle categorizzate dentro INBOX:
    Polizze, Quietanze, Libretti, Carta d'Identità, Patente, Visura Camerale,
    Mandato SDD, Privacy, Passaporto, Codice Fiscale, Tessera Sanitaria,
    Condizioni, Atto di Vendita, Denunce Sinistro, Estratti Conto, Bonifici.

    L'utente può trascinare i file dentro la sottocartella corretta:
    lo scan OCR salterà la classificazione AI e userà direttamente la
    categoria della cartella (l'AI estrae solo i dati anagrafici/polizza).
    """
    tenant = _tenant_id(user)
    conn = await db.cloud_connections.find_one({
        "tenant_id": tenant, "provider": provider,
    })
    if not conn:
        raise HTTPException(409, "Account non collegato")
    token = await _fresh_access_token(provider, conn)

    inbox_segments = await _resolve_category_path("inbox", {})
    inbox_id = await _ensure_folder_path(provider, token, inbox_segments, tenant)

    from cloud_ocr_scanner import _ensure_inbox_subfolders as _ensure_subs, INBOX_SUBFOLDERS_TO_CREATE
    created = await _ensure_subs(provider, token, inbox_id)
    return {
        "ok": True, "provider": provider,
        "inbox_id": inbox_id,
        "subfolders": [
            {"name": n, "id": created.get(n), "created": bool(created.get(n))}
            for n in INBOX_SUBFOLDERS_TO_CREATE
        ],
    }


# ============================================================
# OCR NOTTURNO — trigger manuale + history
# ============================================================
@router.post("/scan-now")
async def scan_inbox_now(
    provider: str = Form(..., regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    """Trigger MANUALE dello scan OCR della cartella INBOX (per test o urgenze).

    In produzione lo scan gira automaticamente ogni ora dalle 22:00 alle 06:00 UTC.
    """
    tenant = _tenant_id(user)
    from cloud_ocr_scanner import scan_tenant_inbox
    report = await scan_tenant_inbox(db, tenant, provider, manual=True)
    return report


@router.get("/scan-history")
async def scan_history(
    limit: int = Query(20, ge=1, le=100),
    user=Depends(current_user),
):
    """History degli ultimi run dello scanner OCR notturno."""
    tenant = _tenant_id(user)
    rows = db.cloud_scan_history.find(
        {"tenant_id": tenant},
        {"_id": 0},
    ).sort("created_at", -1).limit(limit)
    return {"runs": [r async for r in rows]}


@router.get("/scan-summary")
async def scan_summary(user=Depends(current_user)):
    """Riepilogo dell'ultimo run + totali cumulativi (per widget dashboard/Inbox)."""
    tenant = _tenant_id(user)
    latest = await db.cloud_scan_history.find_one(
        {"tenant_id": tenant}, {"_id": 0, "entries_summary": 0},
        sort=[("created_at", -1)],
    )
    # Totali cumulativi tutti i tempi
    pipeline = [
        {"$match": {"tenant_id": tenant}},
        {"$group": {
            "_id": None,
            "letti": {"$sum": "$letti"},
            "abbinati": {"$sum": "$abbinati"},
            "in_attesa": {"$sum": "$in_attesa"},
            "anagrafiche_create": {"$sum": {"$ifNull": ["$anagrafiche_create", 0]}},
            "runs": {"$sum": 1},
        }},
    ]
    cumulative = None
    async for c in db.cloud_scan_history.aggregate(pipeline):
        cumulative = {k: v for k, v in c.items() if k != "_id"}
    # File attualmente in "Da smistare" (documenti_inbox pending da cloud_ocr_scan)
    pending_manual = await db.documenti_inbox.count_documents({
        "fonte": "cloud_ocr_scan", "stato": "pending",
    })
    return {
        "latest_run": latest,
        "cumulative": cumulative or {"letti": 0, "abbinati": 0, "in_attesa": 0,
                                     "anagrafiche_create": 0, "runs": 0},
        "pending_manual_smistamento": pending_manual,
    }


@router.get("/inbox-files")
async def list_inbox_files(
    provider: str = Query("google_drive", regex="^(google_drive|onedrive)$"),
    user=Depends(current_user),
):
    """Lista i file attualmente presenti nella cartella INBOX del Drive del tenant.
    Serve alla UI per far vedere il contenuto vivo del Drive prima dello scan.
    """
    tenant = _tenant_id(user)
    conn = await db.cloud_connections.find_one({"tenant_id": tenant, "provider": provider})
    if not conn:
        return {"files": [], "error": "Cloud non collegato"}
    try:
        token = await _fresh_access_token(provider, conn)
    except Exception as e:
        return {"files": [], "error": str(e)}
    inbox_segments = await _resolve_category_path("inbox", {})
    parent = None
    for seg in inbox_segments:
        fid = await _find_folder(provider, token, seg, parent)
        if not fid:
            return {"files": [], "error": "Cartella INBOX non ancora creata"}
        parent = fid
    from cloud_ocr_scanner import _list_files_in_folder
    files = await _list_files_in_folder(provider, token, parent)
    # Ordina per nome
    files.sort(key=lambda x: (x.get("name") or "").lower())
    return {"files": files, "count": len(files), "inbox_id": parent}


@router.get("/archivio")
async def list_archivio(
    limit: int = Query(100, ge=1, le=500),
    only_matched: bool = Query(False),
    user=Depends(current_user),
):
    """Elenco documenti già processati/archiviati (storico OCR)."""
    tenant = _tenant_id(user)
    q: dict = {"tenant_id": tenant}
    if only_matched:
        q["routed_to"] = {"$ne": "da_smistare"}
    rows = db.cloud_documents.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    docs = []
    async for d in rows:
        cls = d.get("classification", {}) or {}
        de = cls.get("dati_estratti", {}) or {}
        # Enrichment: carica nome anagrafica/polizza per la UI
        ana_name = None
        if d.get("matched_anagrafica_id"):
            a = await db.anagrafiche.find_one(
                {"id": d["matched_anagrafica_id"]},
                {"_id": 0, "cognome": 1, "nome": 1, "ragione_sociale": 1},
            )
            if a:
                ana_name = (a.get("ragione_sociale")
                            or f"{a.get('cognome', '')} {a.get('nome', '')}".strip())
        docs.append({
            "file_name": d.get("file_name"),
            "file_id": d.get("file_id"),
            "provider": d.get("provider"),
            "tipo_documento": cls.get("tipo_documento"),
            "confidenza": cls.get("confidenza"),
            "routed_to": d.get("routed_to"),
            "routed_path": d.get("routed_path"),
            "matched_anagrafica_id": d.get("matched_anagrafica_id"),
            "matched_polizza_id": d.get("matched_polizza_id"),
            "anagrafica_nome": ana_name,
            "codice_fiscale": de.get("codice_fiscale"),
            "targa": de.get("targa"),
            "numero_polizza": de.get("numero_polizza"),
            "created_at": d.get("created_at"),
        })
    # Statistiche
    tot = await db.cloud_documents.count_documents({"tenant_id": tenant})
    abbinati = await db.cloud_documents.count_documents({
        "tenant_id": tenant, "routed_to": {"$ne": "da_smistare"},
    })
    return {
        "documenti": docs,
        "totale": tot,
        "abbinati": abbinati,
        "da_smistare": tot - abbinati,
    }
