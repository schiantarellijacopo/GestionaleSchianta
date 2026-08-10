"""Helper unificati per invio email SMTP e messaggi WhatsApp (Evolution API).

Espone due funzioni async pronte all'uso da qualsiasi modulo:
- ``send_email(to, subject, body, html=None, tenant_id=None)``
- ``send_whatsapp_message(cellulare, testo, tenant_id=None)``

Config:
- SMTP → letta da ``db.azienda_config`` (campi smtp_host/port/user/password/from,
  smtp_use_tls) con fallback su variabili d'ambiente SMTP_HOST/SMTP_PORT/SMTP_USER/
  SMTP_PASSWORD/SMTP_FROM.
- WhatsApp Evolution API → letta da ``db.whatsapp_server_config``
  (server_url, api_key) + prima istanza connessa in ``db.whatsapp_instances``,
  con fallback su WHATSAPP_API_URL/WHATSAPP_API_KEY/WHATSAPP_INSTANCE.

Entrambe le funzioni non sollevano eccezioni: ritornano dict
``{"ok": bool, "error": str?}`` e loggano l'errore.
"""
from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def _load_smtp_config() -> dict:
    """Legge la config SMTP da azienda_config con fallback env."""
    from database import db
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    if az.get("smtp_host") and az.get("smtp_user"):
        return {
            "smtp_host": az.get("smtp_host"),
            "smtp_port": int(az.get("smtp_port") or 587),
            "smtp_user": az.get("smtp_user"),
            "smtp_password": az.get("smtp_password"),
            "smtp_from": az.get("smtp_from") or az.get("smtp_user"),
            "smtp_use_tls": bool(az.get("smtp_use_tls", True)),
        }
    # Fallback env
    host = os.environ.get("SMTP_HOST")
    if host:
        return {
            "smtp_host": host,
            "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
            "smtp_user": os.environ.get("SMTP_USER"),
            "smtp_password": os.environ.get("SMTP_PASSWORD"),
            "smtp_from": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER"),
            "smtp_use_tls": os.environ.get("SMTP_USE_TLS", "1") not in ("0", "false", "False"),
        }
    return {}


async def send_email(
    to: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """Invia una email SMTP. Non solleva mai: ritorna ``{ok, error?}``."""
    if not to:
        return {"ok": False, "error": "destinatario mancante"}
    cfg = await _load_smtp_config()
    if not (cfg.get("smtp_host") and cfg.get("smtp_user")):
        return {"ok": False, "error": "SMTP non configurato (Librerie → Azienda)"}
    try:
        from email_utils import smtp_send
        smtp_send(cfg, to_addrs=to, subject=subject, text=body, html=html)
        return {"ok": True}
    except Exception as e:
        logger.warning("Invio email fallito: %s", e)
        return {"ok": False, "error": str(e)}


async def _load_whatsapp_config() -> tuple[str, str, str]:
    """Ritorna (server_url, api_key, instance_name) — stringhe possibilmente vuote."""
    from database import db
    srv = await db.whatsapp_server_config.find_one({}, {"_id": 0}) or {}
    server_url = (srv.get("server_url") or os.environ.get("WHATSAPP_API_URL") or "").rstrip("/")
    inst = await db.whatsapp_instances.find_one(
        {"state": {"$in": ["open", "connected"]}},
        {"_id": 0, "instance_name": 1, "token": 1},
    ) or await db.whatsapp_instances.find_one({}, {"_id": 0, "instance_name": 1, "token": 1}) or {}
    instance_name = inst.get("instance_name") or os.environ.get("WHATSAPP_INSTANCE") or ""
    api_key = inst.get("token") or srv.get("api_key") or os.environ.get("WHATSAPP_API_KEY") or ""
    return server_url, api_key, instance_name


def _normalize_number(num: str) -> str:
    """Rimuove spazi/simboli e ritorna solo cifre. Se manca il prefisso, aggiunge 39."""
    digits = "".join(c for c in str(num or "") if c.isdigit())
    if not digits:
        return ""
    # Se inizia con 3 e ha 9-10 cifre (numero IT senza prefisso) → aggiungi 39
    if len(digits) in (9, 10) and digits.startswith("3"):
        digits = "39" + digits
    return digits


async def send_whatsapp_message(
    cellulare: str,
    testo: str,
    tenant_id: Optional[str] = None,
    instance_name: Optional[str] = None,
) -> dict:
    """Invia un messaggio WhatsApp via Evolution API.

    Delega alla funzione ufficiale ``routes.whatsapp_evo.send_text_via_evolution``
    (usata anche da avvisi_scadenze, alert_dispatcher, server chat) così condivide
    normalizzazione numeri, fallback su istanza connessa e logging in ``whatsapp_messages``.

    Se ``instance_name`` non è passato, prova a leggere l'istanza di default da
    ``azienda_config.notifica_scadenze_whatsapp_instance`` (la stessa che l'utente
    ha già configurato in Librerie → Azienda).
    """
    if not cellulare:
        return {"ok": False, "error": "numero cellulare non valido"}
    if not instance_name:
        try:
            from database import db
            az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
            instance_name = az.get("notifica_scadenze_whatsapp_instance") or None
        except Exception:
            instance_name = None
    try:
        from routes.whatsapp_evo import send_text_via_evolution
        res = await send_text_via_evolution(cellulare, testo or "", instance_name=instance_name)
        return res
    except Exception as e:
        logger.warning("Invio WhatsApp fallito: %s", e)
        return {"ok": False, "error": str(e)}
