"""Provider OpenAPI.it eSignature — Firma Elettronica Avanzata (EU-AES) con OTP via SMS.

Riusa le credenziali OpenAPI.it già configurate (OPENAPI_IT_CLIENT_ID / _SECRET).
L'ambiente eSignature è indipendente dal resto: controllato da
``OPENAPI_ESIGNATURE_SANDBOX`` (default "true") così possiamo testare in sandbox
mentre gli altri servizi OpenAPI restano in produzione.

Endpoints OpenAPI:
- POST   https://{host}/EU-AES                      → crea richiesta firma
- GET    https://{host}/signatures/{id}/detail      → stato/dettaglio
- GET    https://{host}/signatures/{id}/signedDocument → PDF firmato (binario)

Nessuna eccezione propagata: le funzioni ritornano dict con ``ok``/``error``.
"""
from __future__ import annotations

import base64
import os
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _sandbox() -> bool:
    return (os.environ.get("OPENAPI_ESIGNATURE_SANDBOX", "true")).strip().lower() not in ("0", "false", "no")


def _host() -> str:
    return "test.esignature.openapi.com" if _sandbox() else "esignature.openapi.com"


def _oauth_base() -> str:
    return "https://test.oauth.openapi.it" if _sandbox() else "https://oauth.openapi.it"


def _creds() -> tuple[str, str]:
    return (
        (os.environ.get("OPENAPI_IT_CLIENT_ID") or "").strip(),
        (os.environ.get("OPENAPI_IT_CLIENT_SECRET") or "").strip(),
    )


def has_credentials() -> bool:
    cid, csec = _creds()
    return bool(cid and csec)


_token_cache: dict = {}


async def _get_token(ttl_sec: int = 3600) -> Optional[str]:
    cid, csec = _creds()
    if not (cid and csec):
        return None
    host = _host()
    scopes = [f"POST:{host}/EU-AES", f"GET:{host}/signatures"]
    cache_key = f"{host}|" + "|".join(sorted(scopes))
    now = int(time.time())
    cached = _token_cache.get(cache_key)
    if cached and cached.get("expire", 0) - 60 > now:
        return cached["token"]
    auth = "Basic " + base64.b64encode(f"{cid}:{csec}".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{_oauth_base()}/token",
                json={"scopes": scopes, "ttl": ttl_sec},
                headers={"Authorization": auth, "Content-Type": "application/json"},
            )
        if r.status_code != 200:
            logger.warning("eSignature token HTTP %s: %s", r.status_code, r.text[:300])
            return None
        data = r.json()
        token = data.get("token")
        expire = int(data.get("expire") or (now + ttl_sec))
        if token:
            _token_cache[cache_key] = {"token": token, "expire": expire}
        return token
    except Exception as e:
        logger.warning("eSignature token error: %s", e)
        return None


async def create_signature(
    *,
    pdf_bytes: bytes,
    signer: dict,
    message: str = "",
    page: int = 1,
    x: str = "331",
    y: str = "45",
) -> dict:
    """Crea una richiesta EU-AES per un singolo firmatario (OTP via SMS).

    signer: {name, surname, email, mobile}
    Ritorna {ok, id?, state?, signers?:[{id,url,...}], signing_url?, error?}
    """
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "Credenziali OpenAPI eSignature mancanti o scope non attivo"}
    if not signer.get("mobile"):
        return {"ok": False, "error": "Cellulare obbligatorio per la firma FEA con OTP SMS"}
    body = {
        "signers": [{
            "name": signer.get("name") or "",
            "surname": signer.get("surname") or "",
            "email": signer.get("email") or "",
            "mobile": signer.get("mobile"),
            "message": message or "Documento da firmare",
            "signatures": [{"page": page, "x": str(x), "y": str(y), "name": "signature_1"}],
        }],
        "inputDocuments": base64.b64encode(pdf_bytes).decode(),
        "signatureMode": ["typed", "drawn"],
        "userEditableData": {"name": False, "mobile": False, "email": False},
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"https://{_host()}/EU-AES", json=body,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        if r.status_code >= 400:
            logger.warning("eSignature create HTTP %s: %s", r.status_code, r.text[:400])
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        data = (r.json() or {}).get("data") or {}
        signers = data.get("signers") or []
        signing_url = signers[0].get("url") if signers else None
        return {
            "ok": True,
            "id": data.get("id"),
            "state": data.get("state"),
            "signers": signers,
            "signing_url": signing_url,
        }
    except Exception as e:
        logger.exception("eSignature create error")
        return {"ok": False, "error": str(e)}


async def get_detail(signature_id: str) -> dict:
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "Credenziali mancanti"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"https://{_host()}/signatures/{signature_id}/detail",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        if r.status_code >= 400:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        data = (r.json() or {}).get("data") or r.json()
        return {"ok": True, "state": data.get("state"), "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def download_signed(signature_id: str) -> dict:
    """Scarica il PDF firmato. Ritorna {ok, content, content_type} oppure {ok:False,error}."""
    token = await _get_token()
    if not token:
        return {"ok": False, "error": "Credenziali mancanti"}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"https://{_host()}/signatures/{signature_id}/signedDocument",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/pdf"},
            )
        if r.status_code >= 400 or not r.content:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        return {"ok": True, "content": r.content,
                "content_type": r.headers.get("content-type", "application/pdf")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def is_terminal(state: Optional[str]) -> bool:
    return (state or "").upper() in ("DONE", "ERROR")


def is_done(state: Optional[str]) -> bool:
    return (state or "").upper() == "DONE"
