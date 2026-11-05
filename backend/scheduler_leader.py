"""Leader election per gli scheduler in background.

Su Railway l'app può girare con più worker/replica: senza coordinamento ogni
processo avvierebbe i propri scheduler (IMAP poller, avvisi, finalizza firme,
Cloud OCR) facendoli girare DOPPI. Qui usiamo un lock condiviso su MongoDB: solo
l'istanza "leader" avvia gli scheduler; le altre restano in standby e subentrano
automaticamente se il leader smette di rinnovare il lock (crash/deploy).
"""
import os
import socket
import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("scheduler_leader")

INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}"
_LOCK_ID = "scheduler_leader"
_TTL_SEC = 150          # dopo questo tempo senza heartbeat il lock è considerato libero
_HEARTBEAT_SEC = 50     # rinnovo del lock (< TTL con margine)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expiry_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=_TTL_SEC)).isoformat()


async def _try_acquire(raw_db) -> bool:
    """Prende o rinnova la leadership. True se questa istanza è il leader."""
    now = _now_iso()
    exp = _expiry_iso()
    # Rinnova se il lock è nostro, oppure lo prende se è scaduto.
    res = await raw_db.scheduler_locks.update_one(
        {"_id": _LOCK_ID, "$or": [{"holder": INSTANCE_ID}, {"heartbeat": {"$lt": exp}}]},
        {"$set": {"holder": INSTANCE_ID, "heartbeat": now}},
    )
    if res.matched_count:
        return True
    # Documento assente: prima istanza in assoluto → prova a crearlo.
    try:
        await raw_db.scheduler_locks.insert_one(
            {"_id": _LOCK_ID, "holder": INSTANCE_ID, "heartbeat": now})
        return True
    except Exception:
        return False  # un'altra istanza l'ha creato per prima


async def run_leader(raw_db, start_callback) -> None:
    """Loop di elezione: avvia gli scheduler una sola volta quando questa istanza
    diventa leader e mantiene il lock con heartbeat periodici."""
    """Loop di elezione: avvia gli scheduler una sola volta quando questa istanza
    diventa leader e mantiene il lock con heartbeat periodici."""
    started = False
    while True:
        try:
            is_leader = await _try_acquire(raw_db)
            if is_leader and not started:
                logger.info("[scheduler] istanza LEADER %s: avvio scheduler in background", INSTANCE_ID)
                await start_callback()
                started = True
        except Exception as e:
            logger.warning("[scheduler] elezione leader fallita: %s", e)
        await asyncio.sleep(_HEARTBEAT_SEC)


async def release(raw_db) -> None:
    """Rilascia il lock se è nostro (chiamata allo shutdown pulito)."""
    try:
        await raw_db.scheduler_locks.delete_one({"_id": _LOCK_ID, "holder": INSTANCE_ID})
    except Exception:
        pass
