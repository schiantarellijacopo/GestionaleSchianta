"""Notifica di sicurezza "Nuovo Accesso".

Dopo un login riuscito, registra il dispositivo (fingerprint a bassa invasività
basata su HMAC di User-Agent + rete coarse) in `known_login_devices`. Se il
dispositivo è nuovo e NON è il primo accesso in assoluto dell'utente, invia in
background un'email di avviso. Nessun dato personale grezzo (IP/UA) viene salvato:
solo HMAC con un segreto server-side stabile.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import new as hmac_new
from ipaddress import ip_address

from fastapi import Request
from pymongo.errors import DuplicateKeyError

from database import raw_db

logger = logging.getLogger("auth_device_alert")

DEVICE_TTL_DAYS = 365
_SECRET_CACHE: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_device_indexes() -> None:
    try:
        await raw_db.known_login_devices.create_index(
            [("agenzia_tenant_id", 1), ("user_id", 1), ("device_hash", 1)],
            unique=True, name="tenant_user_device_unique",
        )
        await raw_db.known_login_devices.create_index(
            "expires_at", expireAfterSeconds=0, name="device_expiry",
        )
    except Exception as e:
        logger.warning("Impossibile creare indici known_login_devices: %s", e)


async def _get_secret() -> str:
    """Segreto HMAC stabile: generato una volta e persistito in app_settings."""
    global _SECRET_CACHE
    if _SECRET_CACHE:
        return _SECRET_CACHE
    doc = await raw_db.app_settings.find_one({"_id": "device_hash_secret"})
    if doc and doc.get("value"):
        _SECRET_CACHE = doc["value"]
        return _SECRET_CACHE
    value = secrets.token_hex(32)
    try:
        await raw_db.app_settings.update_one(
            {"_id": "device_hash_secret"},
            {"$setOnInsert": {"value": value, "created_at": _utcnow().isoformat()}},
            upsert=True,
        )
        doc = await raw_db.app_settings.find_one({"_id": "device_hash_secret"})
        _SECRET_CACHE = (doc or {}).get("value", value)
    except Exception:
        _SECRET_CACHE = value
    return _SECRET_CACHE


def _coarse_network(raw_ip: str | None) -> str | None:
    if not raw_ip:
        return None
    try:
        ip = ip_address(raw_ip.strip())
        if ip.version == 4:
            return ".".join(str(ip).split(".")[:3]) + ".0/24"
        return str(ip).split("::", 1)[0] + "::/64"
    except ValueError:
        return None


def _digest(secret: str, label: str, value: str | None) -> str | None:
    if value is None:
        return None
    return hmac_new(secret.encode(), f"{label}|{value}".encode(), sha256).hexdigest()


def _browser_desc(ua: str) -> str:
    """Descrizione sintetica (non salvata) per l'email."""
    u = ua.lower()
    browser = ("Edge" if "edg" in u else "Chrome" if "chrome" in u and "safari" in u
               else "Firefox" if "firefox" in u else "Safari" if "safari" in u
               else "App/Client")
    system = ("Windows" if "windows" in u else "macOS" if "mac os" in u or "macintosh" in u
              else "Android" if "android" in u else "iOS" if "iphone" in u or "ipad" in u
              else "Linux" if "linux" in u else "")
    return f"{browser}{(' · ' + system) if system else ''}"


def _signals(request: Request, secret: str) -> dict:
    ua = (request.headers.get("user-agent", "") or "").strip().lower()[:512]
    ip = request.client.host if request.client else None
    net = _coarse_network(ip)
    return {
        "_ua_raw": ua,
        "_net_coarse": net,
        "ua_hash": _digest(secret, "ua", ua),
        "network_hash": _digest(secret, "net", net),
        "device_hash": _digest(secret, "device", f"{ua}|{net or 'unknown'}"),
    }


async def register_login_device(
    *, tenant_id: str, user_id: str, user_email: str, user_name: str,
    login_count_before: int, request: Request,
) -> None:
    """Registra il dispositivo; invia email solo se nuovo e non primo login."""
    try:
        secret = await _get_secret()
        now = _utcnow()
        sig = _signals(request, secret)
        doc = {
            "agenzia_tenant_id": tenant_id,
            "user_id": user_id,
            "ua_hash": sig["ua_hash"],
            "network_hash": sig["network_hash"],
            "device_hash": sig["device_hash"],
            "first_seen_at": now,
            "last_seen_at": now,
            "last_alerted_at": None,
            "expires_at": now + timedelta(days=DEVICE_TTL_DAYS),
        }
        is_new = False
        try:
            await raw_db.known_login_devices.insert_one(doc)
            is_new = True
        except DuplicateKeyError:
            await raw_db.known_login_devices.update_one(
                {"agenzia_tenant_id": tenant_id, "user_id": user_id,
                 "device_hash": sig["device_hash"]},
                {"$set": {"last_seen_at": now,
                          "expires_at": now + timedelta(days=DEVICE_TTL_DAYS)}},
            )
        if is_new and login_count_before > 0:
            browser = _browser_desc(sig["_ua_raw"])
            asyncio.create_task(_send_new_login_email(
                tenant_id=tenant_id, user_id=user_id, device_hash=sig["device_hash"],
                email=user_email, name=user_name, when=now, browser=browser,
                citta=sig["_net_coarse"] or ""))
    except Exception as e:
        logger.warning("register_login_device fallita (non blocca il login): %s", e)


async def _send_new_login_email(*, tenant_id, user_id, device_hash, email, name,
                                when: datetime, browser: str, citta: str) -> None:
    try:
        result = await raw_db.known_login_devices.update_one(
            {"agenzia_tenant_id": tenant_id, "user_id": user_id,
             "device_hash": device_hash,
             "$or": [{"last_alerted_at": None},
                     {"last_alerted_at": {"$lt": when - timedelta(hours=24)}}]},
            {"$set": {"last_alerted_at": when}},
        )
        if result.modified_count != 1:
            return
        from resend_service import send_new_login_alert
        await send_new_login_alert(
            to=email, name=name,
            when=when.strftime("%d/%m/%Y %H:%M UTC"),
            browser=browser, citta=citta)
    except Exception as e:
        logger.warning("Invio email nuovo accesso fallito: %s", e)
