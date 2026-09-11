"""Google Contacts (People API) — sincronizzazione anagrafiche → contatti Google.

Ogni agenzia collega il PROPRIO account Google (OAuth offline, refresh token
cifrato in Mongo). Alla creazione/modifica di un'anagrafica il contatto viene
creato/aggiornato in background.
"""
from __future__ import annotations
import asyncio
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from pydantic import BaseModel

from database import db, raw_db
from auth import current_user, require_user
from tenant import user_tenant_id

router = APIRouter(tags=["google-contacts"])

SCOPES = ["https://www.googleapis.com/auth/contacts"]
PERSON_FIELDS = "names,addresses,phoneNumbers,emailAddresses,metadata"
UPDATE_FIELDS = "names,addresses,phoneNumbers,emailAddresses"

_STATES: dict[str, str] = {}
_BG_TASKS: set = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cfg_from(cid: str, csec: str) -> dict:
    if not cid or not csec:
        raise HTTPException(400, "Google Contacts non configurato: inserisci Client ID e Client Secret dell'agenzia")
    return {"web": {
        "client_id": cid,
        "client_secret": csec,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [os.environ["GOOGLE_CONTACTS_REDIRECT_URI"]],
    }}


async def _credenziali_app(tenant_id: str) -> tuple[str, str]:
    """Client ID/Secret dell'agenzia (isolati per tenant); fallback su env."""
    row = await raw_db.google_contacts_config.find_one({"agenzia_tenant_id": tenant_id})
    if row and row.get("client_id") and row.get("client_secret_enc"):
        return row["client_id"], _cipher().decrypt(row["client_secret_enc"].encode()).decode()
    return (os.environ.get("GOOGLE_CONTACTS_CLIENT_ID", ""),
            os.environ.get("GOOGLE_CONTACTS_CLIENT_SECRET", ""))


def _cipher() -> Fernet:
    return Fernet(os.environ["GOOGLE_TOKEN_KEY"].encode())


def _flow(cid: str, csec: str, state: Optional[str] = None) -> Flow:
    # PKCE disabilitato: il code_verifier non sopravvive tra connect e callback
    # (flusso server-side con client secret: PKCE non necessario).
    f = Flow.from_client_config(_cfg_from(cid, csec), scopes=SCOPES, state=state,
                                autogenerate_code_verifier=False)
    f.redirect_uri = os.environ["GOOGLE_CONTACTS_REDIRECT_URI"]
    return f


def _persona(ana: dict) -> dict:
    nome = (ana.get("nome") or "").strip()
    cognome = (ana.get("cognome") or "").strip()
    if not nome and not cognome:
        nome = (ana.get("ragione_sociale") or "").strip()
    indirizzo = (ana.get("indirizzo") or "").strip()
    body: dict = {"names": [{"givenName": nome, "familyName": cognome}]}
    if indirizzo or ana.get("comune"):
        body["addresses"] = [{
            "streetAddress": indirizzo or None,
            "city": (ana.get("comune") or None),
            "region": (ana.get("provincia") or None),
            "postalCode": (ana.get("cap") or None),
            "country": "IT",
        }]
    tels = []
    if ana.get("cellulare"):
        tels.append({"value": ana["cellulare"], "type": "mobile"})
    if ana.get("telefono"):
        tels.append({"value": ana["telefono"], "type": "home"})
    if tels:
        body["phoneNumbers"] = tels
    if ana.get("email"):
        body["emailAddresses"] = [{"value": ana["email"]}]
    return body


async def _credenziali(tenant_id: str) -> Credentials:
    row = await raw_db.google_contacts_connessioni.find_one({"agenzia_tenant_id": tenant_id})
    if not row:
        raise RuntimeError("Google Contacts non collegato per questa agenzia")
    cid, csec = await _credenziali_app(tenant_id)
    creds = Credentials(
        token=None,
        refresh_token=_cipher().decrypt(row["refresh_token_enc"].encode()).decode(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid,
        client_secret=csec,
        scopes=SCOPES,
    )
    creds.refresh(GoogleRequest())
    return creds


def _service(creds: Credentials):
    return build("people", "v1", credentials=creds, cache_discovery=False)


async def sincronizza_anagrafica(tenant_id: str, ana_id: str) -> None:
    """Crea/aggiorna il contatto Google. Non solleva: registra lo stato sull'anagrafica."""
    try:
        ana = await raw_db.anagrafiche.find_one({"id": ana_id}, {"_id": 0})
        if not ana:
            return
        conn = await raw_db.google_contacts_connessioni.find_one({"agenzia_tenant_id": tenant_id})
        if not conn:
            return  # agenzia non collegata → niente sync
        creds = await _credenziali(tenant_id)
        svc = _service(creds)
        body = _persona(ana)
        res_name = ana.get("google_person_resource")
        loop = asyncio.get_running_loop()
        if res_name:
            attuale = await loop.run_in_executor(None, lambda: svc.people().get(
                resourceName=res_name, personFields=PERSON_FIELDS).execute())
            body["resourceName"] = res_name
            body["etag"] = attuale.get("etag")
            person = await loop.run_in_executor(None, lambda: svc.people().updateContact(
                resourceName=res_name, updatePersonFields=UPDATE_FIELDS,
                personFields=PERSON_FIELDS, body=body).execute())
        else:
            person = await loop.run_in_executor(None, lambda: svc.people().createContact(
                body=body, personFields=PERSON_FIELDS).execute())
        await raw_db.anagrafiche.update_one({"id": ana_id}, {"$set": {
            "google_person_resource": person["resourceName"],
            "google_etag": person.get("etag"),
            "google_sync_status": "synced",
            "google_sync_at": _now(),
            "google_sync_error": None,
        }})
    except Exception as e:  # noqa: BLE001
        await raw_db.anagrafiche.update_one({"id": ana_id}, {"$set": {
            "google_sync_status": "errore", "google_sync_error": str(e)[:300],
        }})


def sync_in_background(tenant_id: Optional[str], ana_id: Optional[str]) -> None:
    """Avvia la sincronizzazione senza bloccare la risposta API."""
    if not tenant_id or not ana_id:
        return
    task = asyncio.create_task(sincronizza_anagrafica(tenant_id, ana_id))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


# --------------------------------------------------------------------------
# OAuth + gestione connessione
# --------------------------------------------------------------------------
@router.get("/google/status")
async def google_status(user: dict = Depends(current_user)) -> dict:
    tid = user_tenant_id(user)
    conn = await raw_db.google_contacts_connessioni.find_one(
        {"agenzia_tenant_id": tid}, {"_id": 0, "refresh_token_enc": 0})
    cfg = await raw_db.google_contacts_config.find_one(
        {"agenzia_tenant_id": tid}, {"_id": 0, "client_secret_enc": 0})
    cid, csec = await _credenziali_app(tid)
    tot = await db.anagrafiche.count_documents({})
    sincronizzate = await db.anagrafiche.count_documents({"google_sync_status": "synced"})
    errori = await db.anagrafiche.count_documents({"google_sync_status": "errore"})
    return {
        "configurato": bool(cid and csec),
        "client_id": cfg.get("client_id") if cfg else None,
        "redirect_uri": os.environ["GOOGLE_CONTACTS_REDIRECT_URI"],
        "collegato": bool(conn),
        "connessione": conn,
        "anagrafiche": tot, "sincronizzate": sincronizzate, "errori": errori,
    }


class GoogleConfigBody(BaseModel):
    client_id: str
    client_secret: str


@router.put("/google/config")
async def google_config(body: GoogleConfigBody,
                        user: dict = Depends(require_user("admin"))) -> dict:
    """Client ID/Secret Google isolati per agenzia."""
    tid = user_tenant_id(user)
    if not tid:
        raise HTTPException(400, "Nessuna agenzia associata all'utente")
    cid = body.client_id.strip()
    csec = body.client_secret.strip()
    if not cid or not csec:
        raise HTTPException(400, "Client ID e Client Secret sono obbligatori")
    await raw_db.google_contacts_config.update_one(
        {"agenzia_tenant_id": tid},
        {"$set": {"client_id": cid,
                  "client_secret_enc": _cipher().encrypt(csec.encode()).decode(),
                  "updated_at": _now()},
         "$setOnInsert": {"agenzia_tenant_id": tid, "created_at": _now()}},
        upsert=True)
    # credenziali cambiate → la vecchia connessione non è più valida
    await raw_db.google_contacts_connessioni.delete_one({"agenzia_tenant_id": tid})
    return {"ok": True, "redirect_uri": os.environ["GOOGLE_CONTACTS_REDIRECT_URI"]}


@router.delete("/google/config")
async def google_config_delete(user: dict = Depends(require_user("admin"))) -> dict:
    tid = user_tenant_id(user)
    await raw_db.google_contacts_config.delete_one({"agenzia_tenant_id": tid})
    await raw_db.google_contacts_connessioni.delete_one({"agenzia_tenant_id": tid})
    return {"ok": True}


@router.get("/google/connect")
async def google_connect(email: Optional[str] = None,
                         user: dict = Depends(require_user("admin"))) -> dict:
    tid = user_tenant_id(user)
    if not tid:
        raise HTTPException(400, "Nessuna agenzia associata all'utente")
    state = secrets.token_urlsafe(32)
    _STATES[state] = tid
    await raw_db.google_contacts_states.update_one(
        {"state": state}, {"$set": {"state": state, "agenzia_tenant_id": tid, "created_at": _now()}},
        upsert=True)
    cid, csec = await _credenziali_app(tid)
    extra = {"login_hint": email.strip()} if email else {}
    url, _ = _flow(cid, csec, state).authorization_url(
        access_type="offline", include_granted_scopes="true",
        prompt="consent select_account", **extra)
    return {"authorization_url": url}


@router.get("/google/oauth/callback")
async def google_callback(code: str, state: str):
    tid = _STATES.pop(state, None)
    if not tid:
        row = await raw_db.google_contacts_states.find_one_and_delete({"state": state})
        tid = (row or {}).get("agenzia_tenant_id")
    if not tid:
        raise HTTPException(400, "Stato OAuth non valido o scaduto")
    cid, csec = await _credenziali_app(tid)
    flow = _flow(cid, csec, state)
    try:
        flow.fetch_token(code=code)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Google ha rifiutato l'autorizzazione: {e}") from e
    creds = flow.credentials
    if not creds.refresh_token:
        raise HTTPException(400, "Google non ha restituito il refresh token: ricollega dando il consenso")
    email = None
    try:
        svc = _service(creds)
        me = svc.people().get(resourceName="people/me", personFields="emailAddresses").execute()
        email = (me.get("emailAddresses") or [{}])[0].get("value")
    except Exception:  # noqa: BLE001
        pass
    await raw_db.google_contacts_connessioni.update_one(
        {"agenzia_tenant_id": tid},
        {"$set": {
            "refresh_token_enc": _cipher().encrypt(creds.refresh_token.encode()).decode(),
            "account_email": email,
            "scope": " ".join(creds.scopes or SCOPES),
            "updated_at": _now(),
        }, "$setOnInsert": {"agenzia_tenant_id": tid, "created_at": _now()}},
        upsert=True,
    )
    front = os.environ["GOOGLE_CONTACTS_REDIRECT_URI"].split("/api/")[0]
    return RedirectResponse(f"{front}/librerie?tab=google-contatti&google=connesso")


@router.delete("/google/connection")
async def google_disconnect(user: dict = Depends(require_user("admin"))) -> dict:
    tid = user_tenant_id(user)
    await raw_db.google_contacts_connessioni.delete_one({"agenzia_tenant_id": tid})
    return {"ok": True}


@router.post("/google/sync-anagrafica/{aid}")
async def google_sync_una(aid: str, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    tid = user_tenant_id(user)
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "id": 1})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    await sincronizza_anagrafica(tid, aid)
    doc = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "google_sync_status": 1, "google_sync_error": 1})
    return doc or {}


async def _sync_tutte_job(tenant_id: str, job_id: str) -> None:
    ids = await raw_db.anagrafiche.find(
        {"agenzia_tenant_id": tenant_id}, {"_id": 0, "id": 1}).to_list(100000)
    tot = len(ids)
    fatte = 0
    for a in ids:
        await sincronizza_anagrafica(tenant_id, a["id"])
        fatte += 1
        if fatte % 25 == 0:
            await raw_db.google_contacts_jobs.update_one(
                {"id": job_id}, {"$set": {"fatte": fatte, "totali": tot}})
    await raw_db.google_contacts_jobs.update_one({"id": job_id}, {"$set": {
        "status": "done", "fatte": fatte, "totali": tot, "finished_at": _now()}})


@router.post("/google/sync-tutti")
async def google_sync_tutti(user: dict = Depends(require_user("admin"))) -> dict:
    tid = user_tenant_id(user)
    conn = await raw_db.google_contacts_connessioni.find_one({"agenzia_tenant_id": tid})
    if not conn:
        raise HTTPException(400, "Collega prima l'account Google")
    attivo = await raw_db.google_contacts_jobs.find_one(
        {"agenzia_tenant_id": tid, "status": "running"})
    if attivo:
        return {"job_id": attivo["id"], "status": "running", "giaAttivo": True}
    job_id = secrets.token_hex(12)
    await raw_db.google_contacts_jobs.insert_one({
        "id": job_id, "agenzia_tenant_id": tid, "status": "running",
        "fatte": 0, "totali": 0, "created_at": _now()})
    task = asyncio.create_task(_sync_tutte_job(tid, job_id))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return {"job_id": job_id, "status": "running"}


@router.get("/google/sync-job/{job_id}")
async def google_sync_job(job_id: str, user: dict = Depends(current_user)) -> dict:
    doc = await raw_db.google_contacts_jobs.find_one({"id": job_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Job non trovato")
    return doc
