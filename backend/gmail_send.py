"""Invio email via Gmail API (multi-tenant).

Modello scelto dall'utente:
- Un unico client OAuth Google GLOBALE dell'app (GOOGLE_CLIENT_ID/SECRET).
- Il refresh_token di ogni agenzia è salvato nel DB (`cloud_connections`,
  provider ``google_drive``), cifrato con Fernet.
- L'invio usa le Gmail API ufficiali (scope ``gmail.send``) con il token
  dell'agenzia CORRENTE che sta inviando la notifica. Niente SMTP (bloccato su
  Railway), niente Resend.

La stessa connessione Google collegata per Drive viene riusata per Gmail: dopo
aver (ri)collegato Google con lo scope ``gmail.send``, l'agenzia può inviare.
"""
from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.policy import SMTP as SMTP_POLICY
from typing import Optional

import httpx

logger = logging.getLogger("gmail_send")

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailNeedsReconsent(Exception):
    """Il token dell'agenzia non ha lo scope gmail.send: serve ricollegare Google."""


class GmailNotConnected(Exception):
    """L'agenzia non ha un account Google collegato."""


def _html_to_text(html: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


async def send_gmail(access_token: str, sender_email: Optional[str], to: str,
                     subject: str, html: str, text: Optional[str] = None) -> dict:
    """Invia una email via Gmail API. Solleva GmailNeedsReconsent se manca lo scope."""
    msg = MIMEMultipart("alternative")
    if sender_email:
        msg["From"] = sender_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(text or _html_to_text(html), "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes(policy=SMTP_POLICY)).decode("ascii").rstrip("=")

    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.post(
            GMAIL_SEND_URL,
            headers={"Authorization": f"Bearer {access_token}",
                     "Content-Type": "application/json", "Accept": "application/json"},
            json={"raw": raw},
        )
    if r.status_code == 403:
        body = {}
        try:
            body = r.json()
        except ValueError:
            pass
        reasons = {e.get("reason") for e in body.get("error", {}).get("errors", [])
                   if isinstance(e, dict)}
        if "insufficientPermissions" in reasons or "insufficient authentication scopes" in r.text.lower():
            raise GmailNeedsReconsent("Il token Google non ha lo scope gmail.send")
    r.raise_for_status()
    return r.json()


async def send_tenant_email(tenant_id: str, to: str, subject: str,
                            html: str, text: Optional[str] = None) -> dict:
    """Invia una email per conto dell'agenzia (tenant) via Gmail API.

    Usa la connessione Google dell'agenzia (refresh_token nel DB). Solleva
    ``GmailNotConnected`` o ``GmailNeedsReconsent`` con messaggi azionabili.
    """
    from database import db
    from routes.cloud_storage import _fresh_access_token

    conn = await db.cloud_connections.find_one(
        {"tenant_id": tenant_id, "provider": "google_drive"})
    if not conn:
        raise GmailNotConnected(
            "Nessun account Google collegato per questa agenzia. Collega Google da "
            "Librerie → Cloud Storage.")
    token = await _fresh_access_token("google_drive", conn)
    sender = conn.get("account_email")
    res = await send_gmail(token, sender, to, subject, html, text)
    logger.info("Email Gmail API inviata (tenant=%s, msg=%s) → %s",
                tenant_id, res.get("id"), to)
    return res
