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
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse

from auth import current_user, require_user
from database import db

router = APIRouter(prefix="/librerie/cloud-storage", tags=["cloud-storage"])

log = logging.getLogger("cloud_storage")

# ============================================================
# Config da environment
# ============================================================
# Client OAuth Google GLOBALE dell'app (una sola app Google per tutte le agenzie).
# Accetta i nomi "globali" GOOGLE_CLIENT_ID/SECRET con fallback ai vecchi
# GOOGLE_DRIVE_CLIENT_ID/SECRET (retrocompatibilità con la config esistente).
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or os.environ.get("GOOGLE_DRIVE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET", "")
MS_CLIENT_ID = os.environ.get("MS_ONEDRIVE_CLIENT_ID", "")
MS_CLIENT_SECRET = os.environ.get("MS_ONEDRIVE_CLIENT_SECRET", "")
MS_TENANT = os.environ.get("MS_ONEDRIVE_TENANT", "common")
ENC_KEY = os.environ.get("CLOUD_STORAGE_ENCRYPTION_KEY", "")
BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL") or BACKEND_PUBLIC_URL

REDIRECT_URI = f"{BACKEND_PUBLIC_URL}/api/librerie/cloud-storage/callback" if BACKEND_PUBLIC_URL else ""

# Scope Google Drive: SOLO archiviazione file (indipendente da Gmail/Contatti).
G_SCOPE = "https://www.googleapis.com/auth/drive"
# Scope Gmail (invio email): integrazione dedicata e separata da Drive.
GMAIL_SCOPE = ("https://www.googleapis.com/auth/gmail.send "
               "https://www.googleapis.com/auth/userinfo.email")
M_SCOPE = "openid profile offline_access Files.ReadWrite User.Read"

# Struttura cartelle standard che il CRM crea automaticamente quando l'agenzia
# clicca "Crea struttura cartelle" (o al primo upload di ogni categoria).
# Ogni categoria è una tupla (path_segments, descrizione).
#
# Due radici nette:
#   • INBOX   → SOLO ingresso: l'utente trascina qui i file da elaborare (OCR).
#   • Archivio→ destinazione di TUTTI i documenti già lavorati nel gestionale.
# Il Drive diventa così l'archivio digitale completo del CRM.
STANDARD_FOLDER_STRUCTURE: dict = {
    "root": ["Assicura CRM"],
    "inbox": ["Assicura CRM", "INBOX"],
    "archivio": ["Assicura CRM", "Archivio"],
    "da_smistare": ["Assicura CRM", "Archivio", "Da smistare manualmente"],
    # ─ Anagrafiche: una cartella per cliente, i documenti dentro col nome della card.
    "anagrafiche": ["Assicura CRM", "Archivio", "Anagrafiche"],
    "anagrafica_cliente": ["Assicura CRM", "Archivio", "Anagrafiche", "{cliente}"],
    # Alias retrocompatibili (OCR): puntano alla stessa cartella piatta del cliente.
    "contraenti": ["Assicura CRM", "Archivio", "Anagrafiche"],
    "contraente_privacy": ["Assicura CRM", "Archivio", "Anagrafiche", "{cliente}"],
    "contraente_identita": ["Assicura CRM", "Archivio", "Anagrafiche", "{cliente}"],
    "contraente_codice_fiscale": ["Assicura CRM", "Archivio", "Anagrafiche", "{cliente}"],
    "contraente_altri": ["Assicura CRM", "Archivio", "Anagrafiche", "{cliente}"],
    # ─ Polizze: una cartella per numero polizza, documenti dentro.
    "polizze": ["Assicura CRM", "Archivio", "Polizze"],
    "polizza_cliente": ["Assicura CRM", "Archivio", "Polizze", "{polizza}"],
    "polizza_condizioni": ["Assicura CRM", "Archivio", "Polizze", "{polizza}"],
    "polizza_documenti": ["Assicura CRM", "Archivio", "Polizze", "{polizza}"],
    # ─ Sinistri: una cartella per numero sinistro.
    "sinistri": ["Assicura CRM", "Archivio", "Sinistri"],
    "sinistro_specifico": ["Assicura CRM", "Archivio", "Sinistri", "{sinistro}"],
    # ─ Trattative / Titoli / Disdette: altri documenti del CRM.
    "trattative": ["Assicura CRM", "Archivio", "Trattative"],
    "trattativa_specifica": ["Assicura CRM", "Archivio", "Trattative", "{cliente}"],
    "titoli": ["Assicura CRM", "Archivio", "Titoli"],
    "titolo_specifico": ["Assicura CRM", "Archivio", "Titoli", "{polizza}"],
    "disdette": ["Assicura CRM", "Archivio", "Disdette"],
    "disdetta_specifica": ["Assicura CRM", "Archivio", "Disdette", "{polizza}"],
    # ─ Documenti firmati digitalmente (FEA / e-signature).
    "firme": ["Assicura CRM", "Archivio", "Documenti Firmati"],
    # ─ Catch-all: qualunque documento di un'entità non mappata finisce comunque qui.
    "altri_documenti": ["Assicura CRM", "Archivio", "Altri documenti"],
    "altro_specifico": ["Assicura CRM", "Archivio", "Altri documenti", "{cliente}"],
    # ─ Quietanze (per anno).
    "quietanze": ["Assicura CRM", "Archivio", "Quietanze"],
    "quietanze_anno": ["Assicura CRM", "Archivio", "Quietanze", "{anno}"],
    # ─ Contabilità: estratti conto compagnia/collaboratore e prima nota storici.
    "contabilita": ["Assicura CRM", "Archivio", "Contabilità"],
    "contabilita_prima_nota_root": ["Assicura CRM", "Archivio", "Contabilità", "Prima Nota"],
    "contabilita_prima_nota": ["Assicura CRM", "Archivio", "Contabilità", "Prima Nota", "{anno}", "{mese}"],
    "contabilita_estratti_root": ["Assicura CRM", "Archivio", "Contabilità", "Estratti Conto Compagnie"],
    "contabilita_estratti": ["Assicura CRM", "Archivio", "Contabilità", "Estratti Conto Compagnie", "{anno}"],
    "contabilita_provvigioni_root": ["Assicura CRM", "Archivio", "Contabilità", "Estratti Conto Collaboratori"],
    "contabilita_provvigioni": ["Assicura CRM", "Archivio", "Contabilità", "Estratti Conto Collaboratori", "{anno}"],
}

# Categorie che vengono create SUBITO al primo setup (senza placeholder),
# così la struttura INBOX + Archivio (con Contabilità) esiste già sul Drive.
INIT_CATEGORIES = [
    "root", "inbox", "archivio", "da_smistare", "anagrafiche", "polizze",
    "sinistri", "trattative", "titoli", "disdette", "firme", "altri_documenti",
    "quietanze", "contabilita",
    "contabilita_prima_nota_root", "contabilita_estratti_root",
    "contabilita_provvigioni_root",
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
    if provider in ("google_drive", "gmail"):
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
        label = {"google_drive": "Google Drive", "gmail": "Gmail",
                 "onedrive": "OneDrive"}.get(provider, provider)
        hint = ("Librerie → Comunicazioni → Email" if provider == "gmail"
                else "Librerie → Cloud Storage → Configurazione admin")
        raise HTTPException(
            501,
            f"{label} non configurato per questa agenzia. Vai su {hint} e incolla "
            f"Client ID e Client Secret (oppure usa le chiavi globali dell'app).",
        )
    if provider == "google_drive":
        return {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "scope": G_SCOPE,
        }
    if provider == "gmail":
        return {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "scope": GMAIL_SCOPE,
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


@router.get("/gmail/status")
async def gmail_status(user=Depends(current_user)):
    """Stato della connessione Gmail (invio email) dell'agenzia — indipendente da Drive."""
    tenant = _tenant_id(user)
    try:
        cfg = await _load_tenant_config(tenant, "gmail")
    except Exception:
        cfg = None
    conn = await db.cloud_connections.find_one(
        {"tenant_id": tenant, "provider": "gmail"},
        {"_id": 0, "account_email": 1, "scopes": 1, "connected_at": 1})
    return {
        "configured": bool(cfg),
        "source": cfg.get("source") if cfg else None,
        "client_id_masked": _mask(cfg.get("client_id")) if cfg else None,
        "connected": bool(conn),
        "account_email": (conn or {}).get("account_email"),
        "connected_at": (conn or {}).get("connected_at"),
        "gmail_send_ok": bool(conn and "gmail.send" in (conn.get("scopes") or "")),
        "redirect_uri": REDIRECT_URI,
    }


@router.delete("/gmail/disconnect")
async def gmail_disconnect(user=Depends(current_user)):
    """Scollega l'account Gmail dell'agenzia (non tocca Drive né Contatti)."""
    if (user.get("role") or "").lower() not in ("admin", "superadmin"):
        raise HTTPException(403, "Solo gli amministratori possono scollegare Gmail")
    tenant = _tenant_id(user)
    await db.cloud_connections.delete_many({"tenant_id": tenant, "provider": "gmail"})
    return {"ok": True}


@router.post("/admin-config")
async def save_admin_config(
    provider: str = Form(..., regex="^(google_drive|onedrive|gmail)$"),
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
    provider: str = Query(..., regex="^(google_drive|onedrive|gmail)$"),
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
    provider: str = Query(..., regex="^(google_drive|onedrive|gmail)$"),
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
    if provider in ("google_drive", "gmail"):
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
    # Indirizzo email dell'account Google collegato (mittente per l'invio Gmail API).
    account_email = None
    if provider in ("google_drive", "gmail") and t.get("access_token"):
        try:
            async with httpx.AsyncClient(timeout=15) as x:
                ui = await x.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {t['access_token']}"})
            if ui.status_code == 200:
                account_email = (ui.json() or {}).get("email")
        except Exception as e:
            log.warning("Userinfo email non recuperata (tenant=%s): %s", st["tenant_id"], str(e)[:160])
    # UPSERT per tenant (1 drive per agenzia). Al (ri)collegamento ripartiamo da uno
    # stato PULITO: azzeriamo folder_id/root custom e svuotiamo la cache dei path,
    # altrimenti se l'utente ha cancellato le cartelle dentro Drive la cache punterebbe
    # a cartelle inesistenti e le cartelle NON verrebbero più rigenerate.
    await db.cloud_connections.update_one(
        {"tenant_id": st["tenant_id"], "provider": provider},
        {"$set": {
            # Il callback OAuth NON ha contesto utente, quindi il wrapper multi-tenant
            # non inietterebbe agenzia_tenant_id: lo impostiamo ESPLICITAMENTE, altrimenti
            # un'agenzia non-principale non ritroverebbe mai la propria connessione
            # (status/set-folder filtrano per agenzia_tenant_id).
            "tenant_id": st["tenant_id"],
            "agenzia_tenant_id": st["tenant_id"],
            "refresh_token": _enc(refresh),
            "scopes": t.get("scope", cfg["scope"]),
            "account_email": account_email,
            "connected_at": _now().isoformat(),
            "connected_by": st["user_id"],
            "folder_id": None,
            "root_is_custom": False,
            "folder_name": None,
            "structure_initialized_at": None,
        }},
        upsert=True,
    )
    # I passi seguenti (struttura cartelle, cache, backfill) sono specifici dello
    # STORAGE. Per Gmail (solo invio email) non vanno eseguiti.
    if provider == "gmail":
        frontend_target = (FRONTEND_URL or BACKEND_PUBLIC_URL).rstrip("/")
        return RedirectResponse(
            f"{frontend_target}/librerie?gmail=connected&provider=gmail",
            status_code=302,
        )
    await db.cloud_folder_cache.delete_many(
        {"tenant_id": st["tenant_id"], "provider": provider})
    # Appena l'agenzia collega il Drive, crea subito la struttura cartelle + INBOX
    # (così "le funzioni devono funzionare appena viene collegato il Google Drive").
    init_ok = "1"
    try:
        await _init_structure_for_tenant(provider, st["tenant_id"])
    except Exception as e:
        init_ok = "0"
        log.warning("Auto init-structure fallito dopo OAuth (tenant=%s): %s",
                    st["tenant_id"], str(e)[:300])
    # Appena collegato, avvia in BACKGROUND il backfill dei documenti storici
    # (caricati prima del collegamento) così finiscono sul Drive senza premere nulla.
    try:
        import asyncio
        import cloud_doc_sync
        asyncio.create_task(cloud_doc_sync.auto_backfill_tenant(st["tenant_id"]))
    except Exception as e:
        log.warning("Avvio auto-backfill fallito (tenant=%s): %s",
                    st["tenant_id"], str(e)[:200])
    frontend_target = (FRONTEND_URL or BACKEND_PUBLIC_URL).rstrip("/")
    return RedirectResponse(
        f"{frontend_target}/librerie?cloud=connected&provider={provider}&init={init_ok}",
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
    # Ripara eventuali connessioni prive di agenzia_tenant_id (create dal callback OAuth
    # senza contesto) così compaiono correttamente per l'agenzia che le possiede.
    for prov in ("google_drive", "onedrive"):
        await _backfill_agenzia_label(prov, tenant)
    rows = db.cloud_connections.find(
        {"tenant_id": tenant},
        {"_id": 0, "provider": 1, "folder_id": 1, "folder_name": 1,
         "connected_at": 1, "scopes": 1, "connected_by": 1,
         "structure_initialized_at": 1},
    )
    connections = [
        {
            "provider": r["provider"],
            "connected": True,
            "folder_id": r.get("folder_id"),
            "folder_name": r.get("folder_name"),
            "connected_at": r.get("connected_at"),
            "connected_by": r.get("connected_by"),
            "structure_initialized_at": r.get("structure_initialized_at"),
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
    """Salva la cartella di destinazione (o root se folder_id=None) e ricrea la
    struttura (sottocartelle + INBOX) DENTRO la cartella scelta. Per l'intera agenzia."""
    tenant = _tenant_id(user)
    # Etichetta eventuali connessioni già esistenti per questo tenant che non hanno
    # agenzia_tenant_id (create dal callback OAuth senza contesto utente): operazione
    # sicura, mai cross-tenant (filtra per lo stesso tenant_id).
    await _backfill_agenzia_label(provider, tenant)
    # Split-tenant: se la connessione è ancora intestata al tenant legacy della stessa
    # agenzia, adottala PRIMA sul tenant attivo. Senza questo, l'update qui sotto non
    # troverebbe il documento e solleverebbe 404 "Account non collegato" (è il motivo
    # per cui, scegliendo una cartella custom, la struttura non veniva creata).
    if not await db.cloud_connections.find_one({"tenant_id": tenant, "provider": provider}):
        await _adopt_legacy_connection(provider, tenant)
    r = await db.cloud_connections.update_one(
        {"tenant_id": tenant, "provider": provider},
        {"$set": {
            "agenzia_tenant_id": tenant,
            "folder_id": folder_id or None,
            "folder_name": folder_name or None,
            "root_is_custom": bool(folder_id),
            "structure_initialized_at": None,
        }},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Account non collegato")
    # La radice è cambiata → invalida la cache dei percorsi e ricrea la struttura
    # dentro la cartella scelta (INBOX + sottocartelle comprese).
    await db.cloud_folder_cache.delete_many({"tenant_id": tenant, "provider": provider})
    structure = None
    try:
        structure = await _init_structure_for_tenant(provider, tenant)
    except Exception as e:
        log.warning("Rebuild struttura dopo set-folder fallito (tenant=%s): %s",
                    tenant, str(e)[:300])
    # Avvia in background il backfill degli storici anche quando si (ri)sceglie la cartella.
    try:
        import asyncio
        import cloud_doc_sync
        asyncio.create_task(cloud_doc_sync.auto_backfill_tenant(tenant))
    except Exception as e:
        log.warning("Avvio auto-backfill dopo set-folder fallito (tenant=%s): %s",
                    tenant, str(e)[:200])
    return {"ok": True, "folder_id": folder_id, "folder_name": folder_name,
            "structure_created": bool(structure)}


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


async def _move_folder(provider: str, token: str, folder_id: str,
                       new_parent_id: str, old_parent_id: Optional[str]) -> bool:
    """Sposta una cartella sotto un nuovo parent. Best-effort (ritorna False su errore)."""
    try:
        if provider == "google_drive":
            params = {"addParents": new_parent_id, "fields": "id,parents"}
            if old_parent_id:
                params["removeParents"] = old_parent_id
            async with httpx.AsyncClient(timeout=30) as x:
                r = await x.patch(
                    f"https://www.googleapis.com/drive/v3/files/{folder_id}",
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                    params=params, json={},
                )
            r.raise_for_status()
            return True
        # OneDrive
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.patch(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"parentReference": {"id": new_parent_id}},
            )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning("Move cartella %s → %s fallito: %s", folder_id, new_parent_id, str(e)[:160])
        return False


# Cartelle d'archivio "legacy" create in radice PRIMA dell'introduzione di ARCHIVIO.
_LEGACY_ROOT_ARCHIVE_FOLDERS = [
    "Anagrafiche", "Contraenti", "Polizze", "Sinistri", "Quietanze", "Contabilità",
    "Da smistare manualmente", "Trattative", "Titoli", "Disdette",
    "Documenti Firmati", "Altri documenti",
]


async def _reorganize_root_into_archivio(provider: str, token: str,
                                         base_root_id: str, tenant_id: str) -> dict:
    """Sposta le cartelle d'archivio presenti in radice dentro una cartella "Archivio",
    lasciando in radice solo INBOX + Archivio. I file dentro le cartelle vengono
    preservati (lo spostamento è a livello di cartella). Idempotente."""
    archivio_id = await _find_folder(provider, token, "Archivio", base_root_id)
    if not archivio_id:
        archivio_id = await _create_folder(provider, token, "Archivio", base_root_id)
    moved = []
    for name in _LEGACY_ROOT_ARCHIVE_FOLDERS:
        src = await _find_folder(provider, token, name, base_root_id)
        if not src or src == archivio_id:
            continue
        # Se "Archivio" contiene già una cartella con lo stesso nome, non spostiamo
        # (eviteremmo duplicati/merge rischiosi): lasciamo quella vecchia in radice.
        existing = await _find_folder(provider, token, name, archivio_id)
        if existing:
            continue
        if await _move_folder(provider, token, src, archivio_id, base_root_id):
            moved.append(name)
    # La cache dei path va invalidata: i vecchi path puntavano alla radice.
    await db.cloud_folder_cache.delete_many({"tenant_id": tenant_id, "provider": provider})
    return {"archivio_id": archivio_id, "moved": moved}



async def _ensure_folder_path(provider: str, token: str, segments: list,
                              tenant_id: str) -> str:
    """Naviga o crea ogni segmento del path. Usa cache per tenant.

    Se l'agenzia ha scelto una cartella di destinazione custom (connection.folder_id),
    la struttura viene creata DENTRO quella cartella: la cartella scelta diventa la
    radice e sostituisce il primo segmento "Assicura CRM".
    """
    conn = await db.cloud_connections.find_one(
        {"tenant_id": tenant_id, "provider": provider},
        {"_id": 0, "folder_id": 1, "root_is_custom": 1},
    )
    base_parent = (conn or {}).get("folder_id") if (conn or {}).get("root_is_custom") else None

    segs = list(segments)
    if base_parent and segs and segs[0] == "Assicura CRM":
        segs = segs[1:]  # la cartella scelta È già la radice

    cache_key = (f"@{base_parent}/" if base_parent else "") + "/".join(segments)
    cache = await db.cloud_folder_cache.find_one({
        "tenant_id": tenant_id, "provider": provider, "path": cache_key,
    })
    if cache and cache.get("folder_id"):
        return cache["folder_id"]
    parent: Optional[str] = base_parent
    for seg in segs:
        seg_clean = _sanitize_folder_name(seg)
        found = await _find_folder(provider, token, seg_clean, parent)
        parent = found or await _create_folder(provider, token, seg_clean, parent)
    if parent:
        await db.cloud_folder_cache.update_one(
            {"tenant_id": tenant_id, "provider": provider, "path": cache_key},
            {"$set": {"agenzia_tenant_id": tenant_id, "folder_id": parent,
                      "created_at": _now().isoformat()}},
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


async def _backfill_agenzia_label(provider: str, tenant: str) -> None:
    """Etichetta i doc esistenti (connessione + cache) che hanno tenant_id corretto ma
    agenzia_tenant_id mancante — successo tipico delle connessioni create dal callback
    OAuth, che gira senza contesto utente e quindi non iniettava agenzia_tenant_id.
    Operazione idempotente e SEMPRE intra-tenant (mai cross-tenant)."""
    from database import raw_db
    for coll in ("cloud_connections", "cloud_folder_cache", "cloud_scan_history"):
        await getattr(raw_db, coll).update_many(
            {"tenant_id": tenant, "provider": provider,
             "agenzia_tenant_id": {"$exists": False}},
            {"$set": {"agenzia_tenant_id": tenant}},
        )


async def _adopt_legacy_connection(provider: str, target_tenant: str) -> Optional[dict]:
    """Self-heal split-tenant: se la connessione cloud è rimasta su un tenant legacy
    della stessa agenzia, la sposta sul tenant attivo così le funzioni ripartono senza
    dover ricollegare Drive. Sposta connessione + cache + cronologia scan + inbox.
    Ritorna la connessione adottata o None."""
    from database import raw_db
    from tenant import TENANT_PRINCIPALE_ID
    if target_tenant == TENANT_PRINCIPALE_ID:
        return None
    legacy_match = {"$or": [
        {"tenant_id": TENANT_PRINCIPALE_ID}, {"agenzia_tenant_id": TENANT_PRINCIPALE_ID}]}
    src = await raw_db.cloud_connections.find_one({**legacy_match, "provider": provider})
    if not src:
        return None
    set_target = {"$set": {"tenant_id": target_tenant, "agenzia_tenant_id": target_tenant}}
    for coll in ("cloud_connections", "cloud_folder_cache", "cloud_scan_history"):
        await getattr(raw_db, coll).update_many(legacy_match, set_target)
    await raw_db.documenti_inbox.update_many(
        {"agenzia_tenant_id": TENANT_PRINCIPALE_ID},
        {"$set": {"agenzia_tenant_id": target_tenant}})
    log.info("Self-heal: connessione cloud %s adottata da %s a %s",
             provider, TENANT_PRINCIPALE_ID, target_tenant)
    return await raw_db.cloud_connections.find_one(
        {"tenant_id": target_tenant, "provider": provider})


async def _folder_alive(provider: str, token: str, folder_id: str) -> bool:
    """True se la cartella esiste ancora (non cestinata). In caso di dubbio ritorna
    True per non azzerare una radice valida."""
    try:
        if provider == "google_drive":
            async with httpx.AsyncClient(timeout=20) as x:
                r = await x.get(
                    f"https://www.googleapis.com/drive/v3/files/{folder_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"fields": "id,trashed", "supportsAllDrives": "true"},
                )
            if r.status_code == 404:
                return False
            r.raise_for_status()
            return not r.json().get("trashed", False)
        async with httpx.AsyncClient(timeout=20) as x:
            r = await x.get(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"$select": "id,deleted"},
            )
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return "deleted" not in r.json()
    except Exception:
        return True


async def _init_structure_for_tenant(provider: str, tenant: str) -> dict:
    """Crea la struttura di cartelle base dell'agenzia + sottocartelle INBOX.

    Riutilizzata dall'endpoint manuale /init-structure E dal callback OAuth
    (così appena l'agenzia collega il Drive la struttura e l'INBOX esistono subito).
    """
    # Ripara eventuali connessioni prive di agenzia_tenant_id (create dal callback OAuth
    # senza contesto) così la find scoped le trova per l'agenzia che le possiede.
    await _backfill_agenzia_label(provider, tenant)
    conn = await db.cloud_connections.find_one({
        "tenant_id": tenant, "provider": provider,
    })
    if not conn:
        # Self-heal split-tenant: la connessione potrebbe essere rimasta su un tenant
        # legacy della stessa agenzia. La adottiamo sul tenant attivo (niente ricollegamento).
        conn = await _adopt_legacy_connection(provider, tenant)
    if not conn:
        raise HTTPException(409, "Account non collegato per questo provider")
    token = await _fresh_access_token(provider, conn)
    # Se la radice personalizzata è stata cancellata dentro Drive, il suo folder_id non
    # esiste più: ripieghiamo sulla root standard "Assicura CRM" così le cartelle si creano.
    if conn.get("root_is_custom") and conn.get("folder_id"):
        if not await _folder_alive(provider, token, conn["folder_id"]):
            from database import raw_db
            await raw_db.cloud_connections.update_one(
                {"tenant_id": tenant, "provider": provider},
                {"$set": {"folder_id": None, "root_is_custom": False, "folder_name": None}},
            )
            conn["folder_id"] = None
            conn["root_is_custom"] = False
    custom_root = bool(conn.get("root_is_custom") and conn.get("folder_id"))

    # Svuotiamo SEMPRE la cache dei path all'inizio dell'init: così la (ri)creazione
    # delle cartelle riflette lo stato REALE del Drive. Senza questo, se l'utente ha
    # cancellato cartelle dentro Drive, la cache punterebbe a id inesistenti e le
    # cartelle non verrebbero rigenerate ("le cartelle non si generano").
    await db.cloud_folder_cache.delete_many({"tenant_id": tenant, "provider": provider})

    # Riorganizzazione: sposta le cartelle d'archivio già esistenti in radice dentro
    # "Archivio", così in radice restano solo INBOX + Archivio. Da fare PRIMA di creare
    # la struttura standard (altrimenti creeremmo doppioni vuoti sotto Archivio).
    reorg = {"moved": []}
    try:
        if custom_root:
            base_root_id = conn["folder_id"]
        else:
            base_root_id = await _ensure_folder_path(provider, token, ["Assicura CRM"], tenant)
        reorg = await _reorganize_root_into_archivio(provider, token, base_root_id, tenant)
    except Exception as e:
        log.warning("Riorganizzazione Archivio fallita (non blocca init): %s", str(e)[:200])

    created_paths = []
    for cat in INIT_CATEGORIES:
        segments = await _resolve_category_path(cat, {})
        fid = await _ensure_folder_path(provider, token, segments, tenant)
        created_paths.append({
            "category": cat, "path": "/".join(segments), "folder_id": fid,
        })

    if custom_root:
        # La cartella scelta dall'agenzia È la radice: non sovrascrivere nome/id.
        await db.cloud_connections.update_one(
            {"tenant_id": tenant, "provider": provider},
            {"$set": {"agenzia_tenant_id": tenant,
                      "structure_initialized_at": _now().isoformat()}},
        )
    else:
        root_id = created_paths[0]["folder_id"]
        await db.cloud_connections.update_one(
            {"tenant_id": tenant, "provider": provider},
            {"$set": {
                "agenzia_tenant_id": tenant,
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

    return {"ok": True, "provider": provider, "created": created_paths,
            "reorganized": reorg.get("moved", [])}


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
    return await _init_structure_for_tenant(provider, _tenant_id(user))


@router.post("/sync-pending")
async def sync_pending(
    provider: str = Form("google_drive", regex="^(google_drive|onedrive)$"),
    include_all: bool = Form(False),
    user=Depends(require_user("admin")),
):
    """Sposta sul cloud i documenti rimasti nel CRM in attesa (caricati prima del
    collegamento del cloud). Eseguito nel contesto utente → scope per-agenzia garantito.

    include_all=True → BACKFILL completo: include anche i documenti storici senza flag."""
    import cloud_doc_sync
    tenant = _tenant_id(user)
    return await cloud_doc_sync.sync_pending_for_tenant(tenant, include_all=include_all)


@router.get("/sync-status")
async def sync_status(user=Depends(current_user)):
    """Riepilogo: quanti documenti sono sincronizzati sul cloud e quanti restano."""
    import cloud_doc_sync
    return await cloud_doc_sync.sync_status_for_tenant(_tenant_id(user))


@router.post("/migrate-tenant")
async def migrate_tenant(
    source_tenant_id: str = Form(""),
    dry_run: bool = Form(False),
    user=Depends(require_user("admin")),
):
    """Migra il collegamento Google Drive/OCR da un tenant legacy al tenant ATTIVO
    dell'utente corrente.

    Caso d'uso: lo stesso studio opera come tenant UUID ma la configurazione Drive
    era agganciata a un vecchio tenant. L'admin consolida tutto sul proprio tenant
    attuale, senza dover ricollegare Drive manualmente.

    `source_tenant_id` vuoto → usa il tenant principale legacy per default.
    Sposta: cloud_connections, cloud_folder_cache, cloud_scan_history, documenti_inbox.
    Aggiorna sia `tenant_id` sia `agenzia_tenant_id` così le query scoped per-agenzia
    trovano subito la connessione. Idempotente. Usa dry_run=true per un'anteprima.
    """
    from database import raw_db
    from tenant import TENANT_PRINCIPALE_ID

    target = _tenant_id(user)
    source = (source_tenant_id or "").strip() or TENANT_PRINCIPALE_ID
    if source == target:
        raise HTTPException(400, "Il tenant di origine coincide con quello attivo: nulla da migrare")

    # Il tenant di origine deve avere una connessione cloud da migrare.
    src_conn = await raw_db.cloud_connections.find_one(
        {"$or": [{"tenant_id": source}, {"agenzia_tenant_id": source}]}, {"_id": 0, "provider": 1})
    if not src_conn:
        raise HTTPException(404, f"Nessun collegamento cloud trovato per il tenant di origine '{source}'")

    # Se il tenant attivo ha GIÀ una connessione, non sovrascriviamo (sicurezza).
    tgt_conn = await raw_db.cloud_connections.find_one(
        {"$or": [{"tenant_id": target}, {"agenzia_tenant_id": target}]}, {"_id": 0})
    if tgt_conn:
        raise HTTPException(409, "Il tenant attivo ha già un collegamento cloud: migrazione non necessaria")

    collections_tenant_keyed = [
        "cloud_connections", "cloud_folder_cache", "cloud_scan_history",
    ]
    src_match = {"$or": [{"tenant_id": source}, {"agenzia_tenant_id": source}]}
    report: dict = {"source": source, "target": target, "dry_run": dry_run, "migrated": {}}

    for coll in collections_tenant_keyed:
        c = getattr(raw_db, coll)
        count = await c.count_documents(src_match)
        if not dry_run and count:
            await c.update_many(src_match, {"$set": {"tenant_id": target, "agenzia_tenant_id": target}})
        report["migrated"][coll] = count

    # documenti_inbox è scoped solo per agenzia_tenant_id
    inbox_match = {"agenzia_tenant_id": source}
    inbox_count = await raw_db.documenti_inbox.count_documents(inbox_match)
    if not dry_run and inbox_count:
        await raw_db.documenti_inbox.update_many(inbox_match, {"$set": {"agenzia_tenant_id": target}})
    report["migrated"]["documenti_inbox"] = inbox_count

    report["ok"] = True
    return report


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

    Lo scan gira in BACKGROUND e la risposta torna subito: con molti file l'OCR+LLM
    richiede diversi minuti e il proxy ingress chiuderebbe la richiesta sincrona
    (timeout ~30-60s) facendo apparire un "Errore scan" pur avendo lo scan in corso.
    La UI fa polling di /scan-summary per mostrare l'esito appena pronto.
    In produzione lo scan gira anche automaticamente dalle 22:00 alle 06:00 UTC.
    """
    tenant = _tenant_id(user)
    from cloud_ocr_scanner import scan_tenant_inbox
    import asyncio
    from database import set_current_user, reset_current_user

    # Pre-check leggero: se non c'è connessione, rispondi subito con un messaggio chiaro
    # (così l'utente non resta in attesa di un background che verrebbe saltato).
    await _backfill_agenzia_label(provider, tenant)
    if not await db.cloud_connections.find_one({"tenant_id": tenant, "provider": provider}):
        await _adopt_legacy_connection(provider, tenant)
    if not await db.cloud_connections.find_one({"tenant_id": tenant, "provider": provider}):
        raise HTTPException(409, "Account cloud non collegato per questa agenzia")

    async def _run_scan():
        token = set_current_user(user)
        try:
            await scan_tenant_inbox(db, tenant, provider, manual=True)
        except Exception as e:
            log.exception("Scan manuale in background fallito (tenant=%s): %s",
                          tenant, str(e)[:300])
        finally:
            reset_current_user(token)

    asyncio.create_task(_run_scan())
    return {"started": True,
            "message": "Scansione avviata in background: i risultati compariranno tra qualche istante."}


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
            "campi_aggiornati": d.get("campi_aggiornati") or [],
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


# ============================================================================
#  RICERCA DOCUMENTI DI POLIZZA SU GOOGLE DRIVE (match per numero polizza)
# ============================================================================
import re as _re
import uuid as _uuid
from datetime import datetime as _dt, timezone as _tz
from storage_service import StorageService
from db_models import Allegato


def _now_iso_cs() -> str:
    return _dt.now(_tz.utc).isoformat()


async def _drive_token(user) -> tuple[str, dict]:
    conn = await db.cloud_connections.find_one(
        {"tenant_id": _tenant_id(user), "provider": "google_drive"})
    if not conn:
        raise HTTPException(409, "Google Drive non collegato per questa agenzia")
    token = await _fresh_access_token("google_drive", conn)
    return token, conn


async def _drive_list_pdf(token: str, folder_id: str | None,
                          fulltext: str | None = None, page_size: int = 500) -> list[dict]:
    q = "trashed=false and mimeType='application/pdf'"
    if fulltext:
        safe = fulltext.replace("'", "\\'")
        q += f" and fullText contains '{safe}'"
    if folder_id:
        q += f" and '{folder_id}' in parents"
    out, page_token = [], None
    async with httpx.AsyncClient(timeout=40) as x:
        for _ in range(6):  # max ~3000 file
            params = {"q": q, "fields": "nextPageToken,files(id,name,size)",
                      "pageSize": min(page_size, 1000)}
            if page_token:
                params["pageToken"] = page_token
            r = await x.get("https://www.googleapis.com/drive/v3/files",
                            headers={"Authorization": f"Bearer {token}"}, params=params)
            r.raise_for_status()
            j = r.json()
            out.extend(j.get("files", []))
            page_token = j.get("nextPageToken")
            if not page_token:
                break
    return out


async def _drive_download(token: str, file_id: str) -> bytes | None:
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as x:
        r = await x.get(f"https://www.googleapis.com/drive/v3/files/{file_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        params={"alt": "media"})
    if r.status_code == 200 and r.content:
        return r.content
    return None


async def _allega_a_polizza(user, polizza_id: str, filename: str, content: bytes) -> str:
    stored = await StorageService.put(
        user=user, entita_tipo="polizza", entita_id=polizza_id,
        filename=filename, data=content, content_type="application/pdf")
    alleg = Allegato(
        entita_tipo="polizza", entita_id=polizza_id, nome_file=filename,
        storage_path=stored["storage_path"], storage_provider=stored["storage_provider"],
        content_type="application/pdf", size=stored.get("size", len(content)),
        categoria="polizza", visibile_cliente=True, descrizione="Importato da Google Drive",
    )
    await db.allegati.insert_one(alleg.model_dump())
    return alleg.id


@router.post("/cerca-documenti-polizza/{polizza_id}")
async def cerca_documenti_polizza(polizza_id: str, user=Depends(current_user)):
    """Cerca su Google Drive i PDF che contengono il numero di polizza (nel nome
    o nel testo) e li salva negli allegati della polizza (categoria 'polizza')."""
    pol = await db.polizze.find_one({"id": polizza_id},
                                    {"_id": 0, "id": 1, "numero_polizza": 1})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")
    numero = (pol.get("numero_polizza") or "").strip()
    if not numero:
        raise HTTPException(400, "Polizza senza numero")
    token, conn = await _drive_token(user)
    files = await _drive_list_pdf(token, conn.get("folder_id"), fulltext=numero)
    # filtro extra: il numero deve comparire nel nome file O il match fulltext basta
    esistenti = set()
    async for a in db.allegati.find({"entita_tipo": "polizza", "entita_id": polizza_id},
                                    {"nome_file": 1}):
        esistenti.add(a.get("nome_file"))
    salvati = []
    for f in files:
        name = f.get("name") or f"{numero}.pdf"
        if name in esistenti:
            continue
        content = await _drive_download(token, f["id"])
        if not content:
            continue
        await _allega_a_polizza(user, polizza_id, name, content)
        salvati.append(name)
    return {"numero_polizza": numero, "trovati": len(files),
            "salvati": salvati, "gia_presenti": len(files) - len(salvati)}


@router.post("/cerca-documenti-tutte-polizze")
async def cerca_documenti_tutte_polizze(limite_download: int = 150, user=Depends(current_user)):
    """Scansione batch: elenca i PDF del Drive e li abbina alle polizze il cui
    numero compare nel nome del file. Salva negli allegati della polizza."""
    token, conn = await _drive_token(user)
    files = await _drive_list_pdf(token, conn.get("folder_id"))
    # mappa numero_polizza -> polizza_id (solo numeri >= 5 cifre)
    num_map: dict[str, str] = {}
    async for p in db.polizze.find({"is_deleted": {"$ne": True}},
                                   {"_id": 0, "id": 1, "numero_polizza": 1}):
        num = _re.sub(r"\s", "", (p.get("numero_polizza") or ""))
        if len(_re.sub(r"\D", "", num)) >= 5:
            num_map[num] = p["id"]
    numeri = sorted(num_map.keys(), key=len, reverse=True)
    scaricati, abbinamenti, polizze_tocc = 0, 0, set()
    for f in files:
        if scaricati >= limite_download:
            break
        name = f.get("name") or ""
        low = name.replace(" ", "")
        match_num = next((n for n in numeri if n and n in low), None)
        if not match_num:
            continue
        pid = num_map[match_num]
        # evita duplicati
        exists = await db.allegati.find_one(
            {"entita_tipo": "polizza", "entita_id": pid, "nome_file": name}, {"_id": 1})
        if exists:
            continue
        content = await _drive_download(token, f["id"])
        if not content:
            continue
        await _allega_a_polizza(user, pid, name, content)
        scaricati += 1
        abbinamenti += 1
        polizze_tocc.add(pid)
    return {
        "file_su_drive": len(files),
        "polizze_totali": len(num_map),
        "documenti_salvati": scaricati,
        "polizze_aggiornate": len(polizze_tocc),
        "completato": scaricati < limite_download,
    }
