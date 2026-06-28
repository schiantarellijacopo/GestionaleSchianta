"""Utility condivise per invio email SMTP coerente in tutto il backend.

Centralizza la composizione del campo ``From`` (display name + indirizzo) e
l'invio SMTP, evitando duplicazione e bug come "From malformato" (display
name senza email valida finisce in spam o viene rifiutato).
"""
from __future__ import annotations

import smtplib
import re
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional


def build_from_header(az: dict) -> str:
    """Compone l'header ``From:`` corretto in formato RFC 5322.

    Logica:
      1. Se ``smtp_from`` contiene un indirizzo email valido → usalo
      2. Se ``smtp_from`` contiene solo un nome (no @) → ``"Nome" <smtp_user>``
      3. Altrimenti → solo ``smtp_user``
    """
    smtp_from = (az.get("smtp_from") or "").strip()
    smtp_user = (az.get("smtp_user") or "").strip()
    if smtp_from and "@" in smtp_from:
        # già un indirizzo (eventualmente con display name)
        return smtp_from
    if smtp_from and smtp_user:
        # display name puro: combina con smtp_user
        return formataddr((smtp_from, smtp_user))
    return smtp_user


def smtp_send(
    az: dict,
    *,
    to_addrs: list[str] | str,
    subject: str,
    text: str,
    html: Optional[str] = None,
    reply_to: Optional[str] = None,
    attachments: Optional[list[tuple[str, bytes, str, str]]] = None,
) -> None:
    """Invia un'email SMTP usando la config in ``az``.

    Args:
        az: AziendaConfig dict
        to_addrs: lista o stringa singola di destinatari
        subject: oggetto email
        text: corpo plain text
        html: corpo HTML (opzionale)
        reply_to: indirizzo Reply-To (opzionale)
        attachments: lista (filename, bytes, maintype, subtype)

    Raises:
        ValueError: se SMTP non configurato.
        RuntimeError: se l'invio fallisce (auth, rete, destinatario rifiutato).
    """
    host = az.get("smtp_host")
    user = az.get("smtp_user")
    if not (host and user):
        raise ValueError("SMTP non configurato (host/user mancanti)")

    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]
    # Validazione minima destinatari
    cleaned = []
    for addr in to_addrs:
        addr = (addr or "").strip()
        if addr and re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", addr):
            cleaned.append(addr)
    if not cleaned:
        raise ValueError("Nessun destinatario email valido")

    em = EmailMessage()
    em["Subject"] = subject
    em["From"] = build_from_header(az)
    em["To"] = ", ".join(cleaned)
    if reply_to:
        em["Reply-To"] = reply_to
    em.set_content(text or "")
    if html:
        em.add_alternative(html, subtype="html")
    for fn, payload, maintype, subtype in (attachments or []):
        em.add_attachment(payload, maintype=maintype, subtype=subtype, filename=fn)

    port = int(az.get("smtp_port") or 587)
    pwd = az.get("smtp_password") or ""
    try:
        if port == 465:
            srv = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            srv = smtplib.SMTP(host, port, timeout=30)
            if az.get("smtp_use_tls", True):
                srv.starttls()
        if pwd:
            srv.login(user, pwd)
        # send_message valida che il From contenga un indirizzo
        refused = srv.send_message(em)
        srv.quit()
        if refused:
            raise RuntimeError(f"Destinatari rifiutati: {refused}")
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(
            f"Errore autenticazione SMTP (controlla App Password): {e}",
        ) from e
    except smtplib.SMTPException as e:
        raise RuntimeError(f"Errore SMTP: {e}") from e
