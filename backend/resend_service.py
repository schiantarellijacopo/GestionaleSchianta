"""Resend email service — modalità MOCK/PROD.

Se `RESEND_API_KEY` è vuota o inizia con `re_test_mock`, siamo in MOCK MODE:
gli invii vengono solo loggati (nessuna chiamata a Resend). Ideale per test/dev.

Altrimenti si usa il vero SDK Resend (import lazy).

Casi d'uso supportati:
  send_ticket_reply(...)         → risposta ticket helpdesk
  send_marketplace_activation()  → attivazione modulo marketplace
  send_welcome_user()            → benvenuto nuovo utente
  send_policy_expiring()         → notifica scadenza polizza
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _app_base() -> str:
    return (os.environ.get("APP_BASE_URL") or "https://gestionaleschianta.it").rstrip("/")


def _html_to_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def _sender() -> str:
    return os.environ.get("SENDER_EMAIL", "onboarding@resend.dev").strip()


def is_mock_mode() -> bool:
    key = _api_key()
    return not key or key.startswith("re_test_mock")


async def _send(to: str, subject: str, html: str) -> dict:
    """Invio email. Priorità: SMTP admin (Gmail) se configurato → Resend → MOCK."""
    # 1) SMTP configurato dall'admin (Librerie › Comunicazioni) = invio reale via Gmail/SMTP
    try:
        from database import raw_db
        az = await raw_db.azienda_config.find_one({}, {"_id": 0}) or {}
        if az.get("smtp_host") and az.get("smtp_user"):
            from email_utils import smtp_send
            await asyncio.to_thread(
                smtp_send, az, to_addrs=to, subject=subject,
                text=_html_to_text(html), html=html)
            logger.info("[EMAIL SMTP] to=%s subject=%r", to, subject)
            return {"status": "sent", "transport": "smtp", "to": to}
    except Exception as e:
        logger.error("Invio SMTP fallito to=%s: %s (fallback Resend/mock)", to, e)
    # 2) Resend / MOCK
    if is_mock_mode():
        logger.info("[EMAIL MOCK] to=%s subject=%r", to, subject)
        return {"status": "mock", "to": to, "subject": subject, "id": "mock_" + str(hash(to + subject))[:12]}
    try:
        import resend  # type: ignore
        resend.api_key = _api_key()
        params = {"from": _sender(), "to": [to], "subject": subject, "html": html}
        res = await asyncio.to_thread(resend.Emails.send, params)
        return {"status": "sent", "transport": "resend", "id": (res or {}).get("id"), "to": to}
    except Exception as e:
        logger.error("resend send failed to=%s: %s", to, e)
        return {"status": "error", "error": str(e), "to": to}


def _html_wrap(title: str, body_html: str, cta_url: Optional[str] = None, cta_label: Optional[str] = None) -> str:
    """Template email HTML con inline CSS (email-safe)."""
    cta_block = ""
    if cta_url and cta_label:
        cta_block = f"""
        <tr><td style="padding:24px 0;text-align:center;">
          <a href="{cta_url}" style="background:#7c3aed;color:#fff;padding:12px 24px;
             text-decoration:none;border-radius:6px;font-weight:600;font-size:14px;
             display:inline-block;">{cta_label}</a>
        </td></tr>"""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px;background:#f8fafc;font-family:Arial,sans-serif;color:#334155;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;">
    <tr><td style="padding:24px 24px 0;">
      <div style="font-size:20px;font-weight:700;color:#1e293b;margin-bottom:8px;">{title}</div>
    </td></tr>
    <tr><td style="padding:8px 24px 24px;font-size:14px;line-height:1.6;">
      {body_html}
    </td></tr>
    {cta_block}
    <tr><td style="padding:16px 24px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;text-align:center;">
      Programma Assicurativo · Piattaforma SaaS per Agenzie Assicurative<br>
      Questa è un'email automatica, non rispondere direttamente.
    </td></tr>
  </table>
</body></html>"""


# =============== CASI D'USO ===============
async def send_ticket_reply(*, to: str, numero_ticket: str, oggetto: str,
                            messaggio: str, stato: str) -> dict:
    """Email all'agenzia quando il super_admin risponde al ticket."""
    body = f"""
    <p>Ciao,<br>abbiamo aggiornato il tuo ticket <b>{numero_ticket}</b> (<i>{oggetto}</i>).</p>
    <div style="background:#f1f5f9;padding:12px;border-radius:6px;margin:12px 0;font-size:13px;">
      {messaggio}
    </div>
    <p><b>Nuovo stato</b>: {stato}</p>
    """
    return await _send(to, f"[Ticket {numero_ticket}] Aggiornamento supporto", _html_wrap("Aggiornamento Ticket", body))


async def send_marketplace_activation(*, to: str, modulo_nome: str, stato: str) -> dict:
    body = f"""
    <p>Ciao,<br>lo stato del modulo <b>{modulo_nome}</b> è stato aggiornato:</p>
    <p style="font-size:16px;font-weight:600;text-transform:uppercase;">{stato}</p>
    <p>Se hai domande, apri un ticket dal pannello Assistenza.</p>
    """
    return await _send(to, f"[Marketplace] {modulo_nome} → {stato}", _html_wrap("Modulo Marketplace", body))


async def send_welcome_user(*, to: str, name: str, agency_name: str,
                            login_url: str = "https://gestionaleschianta.it") -> dict:
    body = f"""
    <p>Ciao <b>{name}</b>,<br>
    benvenuto in <b>{agency_name}</b>! Il tuo account sulla piattaforma è stato creato.</p>
    <p>Effettua l'accesso con l'email <b>{to}</b> e la password che ti è stata comunicata.</p>
    """
    return await _send(to, f"Benvenuto in {agency_name}", _html_wrap("Benvenuto sulla piattaforma!", body, login_url, "Accedi ora"))


async def send_agency_credentials(*, to: str, name: str, agency_name: str,
                                  login_email: str, password: str,
                                  login_url: Optional[str] = None) -> dict:
    """Email con le CREDENZIALI DI ACCESSO alla creazione di una nuova agenzia."""
    login_url = login_url or f"{_app_base()}/login"
    body = f"""
    <p>Ciao <b>{name}</b>,<br>
    è stato creato l'account amministratore per l'agenzia <b>{agency_name}</b> sulla piattaforma.</p>
    <p>Ecco le tue <b>credenziali di accesso</b>:</p>
    <table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;background:#f1f5f9;border-radius:8px;margin:12px 0;">
      <tr><td style="padding:14px 16px;font-size:14px;">
        <div style="margin-bottom:6px;"><span style="color:#64748b;">Email:</span> <b style="color:#1e293b;">{login_email}</b></div>
        <div><span style="color:#64748b;">Password:</span>
          <b style="color:#1e293b;font-family:monospace;font-size:15px;background:#fff;padding:2px 8px;border-radius:4px;border:1px solid #e2e8f0;">{password}</b>
        </div>
      </td></tr>
    </table>
    <p style="font-size:13px;color:#64748b;">Per sicurezza ti consigliamo di cambiare la password al primo accesso.</p>
    """
    return await _send(to, f"Credenziali di accesso — {agency_name}",
                       _html_wrap("Il tuo accesso alla piattaforma", body, login_url, "Accedi ora"))


async def send_user_credentials(*, to: str, name: str, agency_name: str,
                                login_email: str, password: str,
                                login_url: Optional[str] = None) -> dict:
    """Email con le CREDENZIALI DI ACCESSO alla creazione di un nuovo operatore."""
    login_url = login_url or f"{_app_base()}/login"
    body = f"""
    <p>Ciao <b>{name}</b>,<br>
    è stato creato il tuo account operatore su <b>{agency_name}</b>.</p>
    <p>Ecco le tue <b>credenziali di accesso</b>:</p>
    <table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;background:#f1f5f9;border-radius:8px;margin:12px 0;">
      <tr><td style="padding:14px 16px;font-size:14px;">
        <div style="margin-bottom:6px;"><span style="color:#64748b;">Email:</span> <b style="color:#1e293b;">{login_email}</b></div>
        <div><span style="color:#64748b;">Password:</span>
          <b style="color:#1e293b;font-family:monospace;font-size:15px;background:#fff;padding:2px 8px;border-radius:4px;border:1px solid #e2e8f0;">{password}</b>
        </div>
      </td></tr>
    </table>
    <p style="font-size:13px;color:#64748b;">Per sicurezza ti consigliamo di cambiare la password al primo accesso.</p>
    """
    return await _send(to, f"Il tuo accesso — {agency_name}",
                       _html_wrap("Il tuo accesso alla piattaforma", body, login_url, "Accedi ora"))


async def send_password_reset(*, to: str, name: str, reset_url: str) -> dict:
    """Email con il link per reimpostare la password (valido 45 minuti)."""
    body = f"""
    <p>Ciao <b>{name or ''}</b>,<br>
    abbiamo ricevuto una richiesta di reimpostazione della password del tuo account.</p>
    <p>Clicca il pulsante qui sotto per impostare una nuova password.
    Il link è valido per <b>45 minuti</b> e può essere usato una sola volta.</p>
    <p style="font-size:13px;color:#64748b;">Se non hai richiesto tu il reset, ignora questa email:
    la tua password resterà invariata.</p>
    """
    return await _send(to, "Reimposta la tua password",
                       _html_wrap("Recupero password", body, reset_url, "Reimposta password"))


async def send_policy_expiring(*, to: str, contraente: str, numero_polizza: str,
                               scadenza: str, ramo: Optional[str] = None) -> dict:
    body = f"""
    <p>Gentile <b>{contraente}</b>,<br>
    la sua polizza <b>{numero_polizza}</b>{' (' + ramo + ')' if ramo else ''} è in scadenza il <b>{scadenza}</b>.</p>
    <p>Contatti la sua agenzia per il rinnovo.</p>
    """
    return await _send(to, f"Polizza {numero_polizza} in scadenza il {scadenza}", _html_wrap("Promemoria scadenza polizza", body))
