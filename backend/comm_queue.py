"""Coda di invio asincrona con throttling per-agenzia (anti-spam / anti rate-limit).

Protegge gli account dai blocchi:
- Email (Gmail API): delay 5-10s tra un invio e il successivo per la stessa agenzia;
  retry con exponential backoff su 429 / errori temporanei (max 3 tentativi).
- WhatsApp (Evolution API): jitter 5-10s tra messaggi; (il "composing" 2s è gestito
  in `alert_dispatcher.send_whatsapp`); se l'istanza è disconnessa resta in retry.

Isolamento per tenant: un worker indipendente per agenzia. L'agenzia A non rallenta
l'agenzia B (worker concorrenti), ma all'interno della stessa agenzia gli invii sono
serializzati e distanziati.

Stati item: pending → sending → sent | failed | retry (riprogrammato).
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from db_models import _now_iso, _uid

logger = logging.getLogger("comm_queue")

DELAY_MIN = float(__import__("os").environ.get("COMM_QUEUE_DELAY_MIN", "5"))
DELAY_MAX = float(__import__("os").environ.get("COMM_QUEUE_DELAY_MAX", "10"))
MAX_ATTEMPTS = 3
BACKOFF_BASE_SEC = 30

_raw_db = None
_active_tenants: set[str] = set()
_manager_task = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_retryable(err: str) -> bool:
    e = (err or "").lower()
    keys = ("429", "rate limit", "ratelimit", "too many", "temporarily",
            "timeout", "timed out", "disconnect", "not open", "connection",
            "503", "502", "500", "unavailable", "quota")
    return any(k in e for k in keys)


async def enqueue(*, tenant_id: str, canale: str, event_id: str,
                  rule: dict, dest: dict, ctx: dict) -> str:
    """Accoda un invio (email/whatsapp). Ritorna l'id dell'item."""
    from database import raw_db
    qid = _uid()
    await raw_db.comm_queue.insert_one({
        "id": qid,
        "agenzia_tenant_id": tenant_id or "global",
        "canale": canale,
        "event_id": event_id,
        "rule_id": rule.get("id"),
        "rule_nome": rule.get("nome") or "",
        "dest_label": dest.get("label"),
        "to": dest.get("email") if canale == "email" else (dest.get("whatsapp") or dest.get("cellulare")),
        "rule": rule,
        "dest": dest,
        "ctx": ctx,
        "status": "pending",
        "attempts": 0,
        "next_attempt_at": _now_iso(),
        "error": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    })
    return qid


async def _update_event(event_id: str, status: str, error: str | None):
    if not event_id:
        return
    from database import raw_db
    upd = {"status": status, "error_message": error}
    if status == "ok":
        upd["sent_at"] = _now_iso()
    try:
        await raw_db.alert_events.update_one({"id": event_id}, {"$set": upd})
    except Exception:
        logger.exception("comm_queue: update alert_event fallito")


async def _process(item: dict):
    from database import raw_db, set_current_user, reset_current_user
    from alert_dispatcher import CHANNEL_ADAPTERS
    canale = item["canale"]
    adapter = CHANNEL_ADAPTERS.get(canale)
    tok = set_current_user({
        "id": "__comm_queue__", "agenzia_tenant_id": item.get("agenzia_tenant_id"),
        "role": "admin", "is_super_admin": False,
    })
    try:
        if not adapter:
            res = {"status": "skipped", "error": f"canale '{canale}' non gestito"}
        else:
            res = await adapter(item["rule"], item["dest"], item["ctx"])
    except Exception as e:  # noqa: BLE001
        res = {"status": "errore", "error": str(e)}
    finally:
        reset_current_user(tok)

    status = res.get("status")
    err = res.get("error")
    now = _now_iso()
    if status == "ok":
        await raw_db.comm_queue.update_one(
            {"id": item["id"]},
            {"$set": {"status": "sent", "error": None, "sent_at": now, "updated_at": now}})
        await _update_event(item.get("event_id"), "ok", None)
        return
    if status == "skipped":
        await raw_db.comm_queue.update_one(
            {"id": item["id"]},
            {"$set": {"status": "failed", "error": err, "updated_at": now}})
        await _update_event(item.get("event_id"), "skipped", err)
        return
    # errore: valuta retry
    attempts = int(item.get("attempts", 0)) + 1
    if _is_retryable(err or "") and attempts < MAX_ATTEMPTS:
        wait = BACKOFF_BASE_SEC * (2 ** (attempts - 1)) + random.uniform(0, 10)
        nxt = (_now() + timedelta(seconds=wait)).isoformat()
        await raw_db.comm_queue.update_one(
            {"id": item["id"]},
            {"$set": {"status": "retry", "attempts": attempts, "error": err,
                      "next_attempt_at": nxt, "updated_at": now}})
        await _update_event(item.get("event_id"), "pending", f"retry {attempts}/{MAX_ATTEMPTS}: {err}")
        logger.info("comm_queue: retry %s/%s tra %.0fs (tenant=%s, canale=%s): %s",
                    attempts, MAX_ATTEMPTS, wait, item.get("agenzia_tenant_id"), canale, (err or "")[:120])
    else:
        await raw_db.comm_queue.update_one(
            {"id": item["id"]},
            {"$set": {"status": "failed", "attempts": attempts, "error": err, "updated_at": now}})
        await _update_event(item.get("event_id"), "errore", err)


async def _drain_tenant(tenant_id: str):
    from database import raw_db
    try:
        while True:
            item = await raw_db.comm_queue.find_one_and_update(
                {"agenzia_tenant_id": tenant_id,
                 "$or": [{"status": "pending"},
                         {"status": "retry", "next_attempt_at": {"$lte": _now_iso()}}]},
                {"$set": {"status": "sending", "updated_at": _now_iso()}},
                sort=[("created_at", 1)],
            )
            if not item:
                break
            await _process(item)
            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    except Exception:
        logger.exception("comm_queue: errore drain tenant %s", tenant_id)
    finally:
        _active_tenants.discard(tenant_id)


async def _manager_loop():
    from database import raw_db
    logger.info("comm_queue manager avviato (delay %.0f-%.0fs/tenant)", DELAY_MIN, DELAY_MAX)
    while True:
        try:
            tenants = await raw_db.comm_queue.distinct(
                "agenzia_tenant_id",
                {"$or": [{"status": "pending"},
                         {"status": "retry", "next_attempt_at": {"$lte": _now_iso()}}]})
            for t in tenants:
                if t in _active_tenants:
                    continue
                _active_tenants.add(t)
                asyncio.create_task(_drain_tenant(t))
        except Exception:
            logger.exception("comm_queue: errore manager loop")
        await asyncio.sleep(3)


def start_comm_queue():
    global _manager_task
    if _manager_task is not None:
        return
    try:
        _manager_task = asyncio.create_task(_manager_loop())
    except RuntimeError:
        logger.warning("comm_queue: nessun event loop attivo, worker non avviato")


async def queue_status(tenant_id: str) -> dict:
    """Riepilogo code per la dashboard comunicazioni dell'agenzia."""
    from database import raw_db
    out = {"email": {}, "whatsapp": {}, "totali": {}}
    base = {"agenzia_tenant_id": tenant_id}
    for canale in ("email", "whatsapp"):
        for stato in ("pending", "retry", "sending", "sent", "failed"):
            n = await raw_db.comm_queue.count_documents({**base, "canale": canale, "status": stato})
            out[canale][stato] = n
    for stato in ("pending", "retry", "sending", "sent", "failed"):
        out["totali"][stato] = out["email"].get(stato, 0) + out["whatsapp"].get(stato, 0)
    # ultimi falliti con motivo
    falliti = await raw_db.comm_queue.find(
        {**base, "status": "failed"},
        {"_id": 0, "canale": 1, "dest_label": 1, "to": 1, "error": 1, "updated_at": 1, "rule_nome": 1},
    ).sort("updated_at", -1).to_list(10)
    out["ultimi_falliti"] = falliti
    out["in_coda"] = out["totali"].get("pending", 0) + out["totali"].get("retry", 0) + out["totali"].get("sending", 0)
    return out
