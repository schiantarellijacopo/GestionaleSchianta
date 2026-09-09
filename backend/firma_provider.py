"""Adapter provider-neutrale per firma elettronica avanzata.

Attualmente implementa Namirial eSignAnyWhere v6 (documentazione:
https://namirial.atlassian.net/wiki/spaces/eSign/pages/91882730).

Design: nessuna credenziale è hard-coded — sono lette da ``db.azienda_config``:
- ``firma_provider``      = "namirial" (default)
- ``firma_base_url``      = es. "https://demo.esignanywhere.net/Api/v6"
- ``firma_api_token``     = token 64ch generato in eSAW → Settings → API Tokens
- ``firma_environment``   = "sandbox" | "production"
- ``firma_webhook_secret``= (opzionale, se Namirial lo attiva sul tenant)

Le funzioni non sollevano eccezioni non gestite: ritornano dict con ``ok`` e ``error``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


async def _load_config() -> dict:
    """Legge la config firma da azienda_config."""
    from database import db
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    return {
        "provider": (az.get("firma_provider") or "namirial").lower(),
        "base_url": (az.get("firma_base_url") or "").rstrip("/"),
        "api_token": az.get("firma_api_token"),
        "environment": az.get("firma_environment") or "sandbox",
        "webhook_secret": az.get("firma_webhook_secret"),
    }


def _headers(cfg: dict) -> dict:
    return {
        "Authorization": f"Bearer {cfg['api_token']}",
        "Accept": "application/json",
    }


async def is_configured() -> bool:
    cfg = await _load_config()
    return bool(cfg.get("base_url") and cfg.get("api_token"))


async def upload_pdf(pdf_bytes: bytes, filename: str = "documento.pdf") -> dict:
    """Carica un PDF su eSAW. Ritorna {ok, file_id?, error?}."""
    cfg = await _load_config()
    if not (cfg["base_url"] and cfg["api_token"]):
        return {"ok": False, "error": "Firma non configurata (Librerie → Firme)"}
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                f"{cfg['base_url']}/file/upload",
                headers=_headers(cfg),
                files={"File": (filename, pdf_bytes, "application/pdf")},
            )
        if r.is_error:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        return {"ok": True, "file_id": r.json().get("FileId")}
    except Exception as e:
        logger.exception("Upload PDF fallito: %s", e)
        return {"ok": False, "error": str(e)}


def _build_signature_config(mode: str) -> dict:
    """AllowedSignatureTypes in base alla modalità richiesta.

    - otp_sms       → TransactionCode via SMS (OtpData.PhoneMobile)
    - otp_email     → TransactionCode via Email
    - biometric     → Firma grafometrica FEA (app SIGNificant su tablet)
    - simple / link → ClickToSign (link remoto WhatsApp/SMS/Email)
    """
    if mode in ("simple", "link", "link_whatsapp", "otp_email"):
        # ClickToSign: link remoto (inviabile via email/WhatsApp dal nostro sistema).
        # NB: eSAW v6 NON espone un "Email OTP" nativo come firma → si usa il link.
        return {"ClickToSign": {}}
    if mode == "otp_sms":
        # v6: il tipo firma è OtpSignature; l'OTP via SMS è un metodo di autenticazione
        # del destinatario (vedi _build_envelope → AuthenticationMethods).
        return {"OtpSignature": {}}
    if mode == "biometric":
        return {"Biometric": {
            "BiometricVerification": False,
            "AllowBiometricStoringOnly": False,
            "StoreSignedResponseWithoutBioData": True,
            "AllowSkipBiometricVerification": False,
            "SignaturePositioning": "WithinField",
            "Preferred": True,
        }}
    raise ValueError(f"Modalità firma non supportata: {mode}")


def _build_envelope(
    file_id: str,
    signer: dict,
    mode: str,
    callback_url: str,
    display_name: str = "Documento da firmare",
    page_number: int = 1,
    pos_x: int = 100,
    pos_y: int = 150,
) -> dict:
    """Costruisce il payload envelope conforme eSAW v6."""
    contact = {
        "Email": signer.get("email"),
        "GivenName": signer.get("nome") or signer.get("given_name") or "",
        "Surname": signer.get("cognome") or signer.get("surname") or "",
        "LanguageCode": "IT",
    }
    recipient = {
        "ContactInformation": contact,
        # In presenza (biometric) o link custom (via nostri canali) disabilita l'email
        # automatica di Namirial: l'utente riceve il link solo dal nostro sistema.
        "DisableEmail": mode in ("biometric", "simple", "link", "link_whatsapp", "otp_email"),
        "AuthenticationMethods": [],
    }
    if mode == "otp_sms":
        # v6: autenticazione del destinatario via SMS-OTP (E.164)
        phone = signer.get("cellulare") or signer.get("phone")
        contact["PhoneNumber"] = phone
        recipient["AuthenticationMethods"] = [{"Method": "Sms", "Parameter": phone}]

    signature = {
        "ElementId": f"sig-{file_id[:8]}",
        "Required": True,
        "DocumentNumber": 1,
        "DisplayName": display_name,
        "AllowedSignatureTypes": _build_signature_config(mode),
        "FieldDefinition": {
            "Position": {"PageNumber": page_number, "X": pos_x, "Y": pos_y},
            "Size": {"Width": 180, "Height": 60},
        },
    }
    return {
        "Documents": [{"FileId": file_id, "DocumentNumber": 1}],
        "Name": display_name,
        "Activities": [{"Action": {"Sign": {
            "RecipientConfiguration": recipient,
            "Elements": {"Signatures": [signature]},
        }}}],
        "CallbackConfiguration": {
            "CallbackUrl": callback_url,
            "StatusUpdateCallbackUrl": callback_url,
        },
    }


async def create_envelope(
    pdf_bytes: bytes,
    filename: str,
    signer: dict,
    mode: str,
    callback_url: str,
    display_name: str = "Documento da firmare",
) -> dict:
    """Crea envelope su eSAW (upload → send → viewer links). Ritorna
    ``{ok, envelope_id?, viewer_links?, error?}``."""
    up = await upload_pdf(pdf_bytes, filename)
    if not up.get("ok"):
        return up
    cfg = await _load_config()
    payload = _build_envelope(up["file_id"], signer, mode, callback_url, display_name)
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{cfg['base_url']}/envelope/send",
                             headers=_headers(cfg), json=payload)
        if r.is_error:
            return {"ok": False, "error": f"envelope/send {r.status_code}: {r.text[:200]}"}
        eid = r.json().get("EnvelopeId")
        # viewer links (per link remoto o app tablet)
        async with httpx.AsyncClient(timeout=30) as c:
            r2 = await c.get(f"{cfg['base_url']}/envelope/{eid}/viewerlinks",
                             headers=_headers(cfg))
        viewer = r2.json() if not r2.is_error else {}
        return {"ok": True, "envelope_id": eid, "viewer_links": viewer, "mode": mode}
    except Exception as e:
        logger.exception("create_envelope: %s", e)
        return {"ok": False, "error": str(e)}


async def get_status(envelope_id: str) -> dict:
    cfg = await _load_config()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{cfg['base_url']}/envelope/{envelope_id}",
                            headers=_headers(cfg))
        if r.is_error:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        return {"ok": True, "data": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def download_signed_pdf(envelope_id: str) -> dict:
    """Scarica il PDF firmato + audit PDF/XML. Ritorna
    ``{ok, signed_pdf, audit_pdf?, audit_xml?, error?}``."""
    cfg = await _load_config()
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            meta = await c.get(f"{cfg['base_url']}/envelope/{envelope_id}/files",
                                headers=_headers(cfg))
            if meta.is_error:
                return {"ok": False, "error": f"envelope/files {meta.status_code}"}
            m = meta.json()
            docs = m.get("Documents") or []
            if not docs:
                return {"ok": False, "error": "Nessun documento in envelope"}
            signed_fid = docs[0].get("FileId")
            audit_fid = (m.get("AuditTrail") or {}).get("FileId")
            audit_xml_fid = (m.get("AuditTrail") or {}).get("XmlFileId")

            signed_r = await c.get(f"{cfg['base_url']}/file/{signed_fid}",
                                    headers=_headers(cfg))
            out = {"ok": True, "signed_pdf": signed_r.content}
            if audit_fid:
                audit_r = await c.get(f"{cfg['base_url']}/file/{audit_fid}",
                                       headers=_headers(cfg))
                if not audit_r.is_error:
                    out["audit_pdf"] = audit_r.content
            if audit_xml_fid:
                x_r = await c.get(f"{cfg['base_url']}/file/{audit_xml_fid}",
                                    headers=_headers(cfg))
                if not x_r.is_error:
                    out["audit_xml"] = x_r.content
            return out
    except Exception as e:
        logger.exception("download_signed_pdf: %s", e)
        return {"ok": False, "error": str(e)}


async def verify_webhook_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """Verifica la firma del webhook Namirial se il tenant fornisce l'HMAC secret.

    Documentazione pubblica: Namirial NON specifica un header standard.
    Se il tenant l'ha attivato, il segreto è in ``azienda_config.firma_webhook_secret``.
    Se non è configurato, ritorniamo True (dovrai proteggere l'endpoint via IP allowlist).
    """
    cfg = await _load_config()
    secret = cfg.get("webhook_secret")
    if not secret:
        return True  # nessuna verifica configurata
    if not signature_header:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    expected_b64 = base64.b64encode(
        hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    ).decode()
    # accetta sia formato hex sia base64 (Namirial può usare l'uno o l'altro)
    return any(
        hmac.compare_digest(signature_header, c)
        for c in (expected, f"sha256={expected}", expected_b64)
    )
