"""IMAP Poller — Smistamento automatico email in arrivo per alias.

Ogni `imap_poller_minutes` minuti (default 5):
  1. Connessione IMAP usando le credenziali in `azienda_config`
  2. Fetch dei nuovi messaggi (UID > `imap_poller_last_uid`)
  3. Estrazione header `From`, `To`, `Cc`, `Subject`, `Date` e body
  4. Matching alias destinatari vs `User.email_aliases`:
       - se almeno un alias matcha → categoria='personale', smistato_a=[user_ids]
       - se più collaboratori condividono l'alias (es. sinistri@) → tutti ricevono
       - se nessun alias matcha → categoria='condivisa'
  5. Match mittente vs `Anagrafica.email` → se trovato:
       - imposta `email_inbox.anagrafica_id`
       - inserisce voce in `diario_cliente` (tipo='email_in')
  6. Persiste l'email in `db.email_inbox` (idempotente per `message_id`)
  7. Aggiorna `imap_poller_last_uid` e `imap_poller_last_run`
"""
from __future__ import annotations

import asyncio
import email as _emaillib
import imaplib
import logging
import re
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime, getaddresses
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from db_models import EmailInbox, DiarioCliente, _now_iso

logger = logging.getLogger(__name__)

_scheduler = None  # AsyncIOScheduler
_job_id = "imap_poller_job"


# ============================================================
# Helpers
# ============================================================
def _decode(h: Optional[str]) -> str:
    if not h:
        return ""
    parts = decode_header(h)
    return "".join(
        (p.decode(enc or "utf-8", errors="replace") if isinstance(p, bytes) else p)
        for p, enc in parts
    )


def _extract_addresses(header_value: Optional[str]) -> list[str]:
    """Estrae lista di indirizzi email lowercase da un header (To / Cc)."""
    if not header_value:
        return []
    decoded = _decode(header_value)
    parsed = getaddresses([decoded])
    out: list[str] = []
    for _name, addr in parsed:
        a = (addr or "").strip().lower()
        if a and "@" in a:
            out.append(a)
    return out


def _extract_body(msg) -> tuple[str, str]:
    """Restituisce (text, html). Prende il primo text/plain e text/html."""
    text = ""
    html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/plain" and not text:
                try:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                except Exception:
                    pass
            elif ctype == "text/html" and not html:
                try:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    html = payload.decode(charset, errors="replace")
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace")
            if (msg.get_content_type() or "").lower() == "text/html":
                html = content
            else:
                text = content
        except Exception:
            pass
    return text.strip(), html.strip()


def _parse_date_iso(raw: Optional[str]) -> str:
    if not raw:
        return _now_iso()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return _now_iso()


# ============================================================
# Core polling logic
# ============================================================
async def poll_once(db: AsyncIOMotorDatabase) -> dict:
    """Esegue UN ciclo di polling IMAP. Idempotente.

    Restituisce statistiche: ``{ok, totali, nuovi, errore}``.
    """
    from credentials_utils import clean_password, clean_email
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    host = az.get("imap_host")
    port = int(az.get("imap_port") or 993)
    user_ = clean_email(az.get("imap_user"))
    pwd = clean_password(az.get("imap_password"))
    folder = az.get("imap_folder") or "INBOX"
    last_uid = int(az.get("imap_poller_last_uid") or 0)

    if not (host and user_ and pwd):
        return {"ok": False, "errore": "IMAP non configurato"}

    nuovi = 0
    saltati = 0
    errori = 0
    max_uid_seen = last_uid

    try:
        if az.get("imap_use_ssl", True):
            M = imaplib.IMAP4_SSL(host, port, timeout=25)
        else:
            M = imaplib.IMAP4(host, port, timeout=25)
        M.login(user_, pwd)
    except Exception as e:
        logger.exception("IMAP login fallito")
        return {"ok": False, "errore": f"Login IMAP: {e}"}

    try:
        typ, _ = M.select(folder, readonly=True)
        if typ != "OK":
            return {"ok": False, "errore": f"Cartella '{folder}' non aprita"}

        # Cerca solo i messaggi con UID > last_uid (incrementale)
        # Se last_uid==0, fetch ultimi 50 messaggi (bootstrap)
        if last_uid > 0:
            search_criteria = f"UID {last_uid + 1}:*"
        else:
            search_criteria = "ALL"
        typ, data = M.uid("SEARCH", None, search_criteria)
        if typ != "OK" or not data or not data[0]:
            return {"ok": True, "nuovi": 0, "saltati": 0, "errori": 0, "last_uid": last_uid}

        uids = data[0].split()
        # Bootstrap: prendi solo gli ultimi 50 per non flooddare al primo run
        if last_uid == 0 and len(uids) > 50:
            uids = uids[-50:]

        # Pre-carica utenti con alias + anagrafiche con email per matching
        users = await db.users.find(
            {"role": {"$ne": "cliente"}, "attivo": True},
            {"_id": 0, "id": 1, "email": 1, "email_aliases": 1},
        ).to_list(500)
        # Mappa: alias_lowercase → list[user_id]
        alias_map: dict[str, list[str]] = {}
        for u in users:
            aliases = [a.lower().strip() for a in (u.get("email_aliases") or []) if a]
            # include anche email principale come "alias" implicito
            if u.get("email"):
                aliases.append(u["email"].lower().strip())
            for a in aliases:
                alias_map.setdefault(a, []).append(u["id"])

        for uid_bytes in uids:
            try:
                uid = int(uid_bytes.decode())
                max_uid_seen = max(max_uid_seen, uid)
                # Skip se già presente (idempotenza per UID+folder)
                existing = await db.email_inbox.find_one(
                    {"uid": str(uid), "folder": folder}, {"_id": 0, "id": 1},
                )
                if existing:
                    saltati += 1
                    continue

                typ, msg_data = M.uid("FETCH", uid_bytes, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    errori += 1
                    continue
                raw = msg_data[0][1]
                msg = _emaillib.message_from_bytes(raw)

                from_full = _decode(msg.get("From"))
                from_name, from_addr = parseaddr(from_full)
                from_addr = (from_addr or "").lower().strip()

                to_list = _extract_addresses(msg.get("To"))
                cc_list = _extract_addresses(msg.get("Cc"))
                subject = _decode(msg.get("Subject"))[:300]
                msg_id = (msg.get("Message-Id") or msg.get("Message-ID") or "").strip()
                date_iso = _parse_date_iso(msg.get("Date"))

                body_text, body_html = _extract_body(msg)
                if len(body_text) > 20000:
                    body_text = body_text[:20000] + "\n…[troncato]"
                if len(body_html) > 80000:
                    body_html = body_html[:80000]

                # Idempotenza per Message-Id
                if msg_id:
                    existing_by_mid = await db.email_inbox.find_one(
                        {"message_id": msg_id}, {"_id": 0, "id": 1},
                    )
                    if existing_by_mid:
                        saltati += 1
                        continue

                # Smistamento per alias
                destinatari = set(to_list + cc_list)
                smistato_a: list[str] = []
                for d in destinatari:
                    if d in alias_map:
                        for uid_user in alias_map[d]:
                            if uid_user not in smistato_a:
                                smistato_a.append(uid_user)
                categoria = "personale" if smistato_a else "condivisa"

                # Match mittente vs anagrafica
                anagrafica_id: Optional[str] = None
                if from_addr:
                    anag = await db.anagrafiche.find_one(
                        {"email": {"$regex": f"^{re.escape(from_addr)}$", "$options": "i"}},
                        {"_id": 0, "id": 1, "ragione_sociale": 1},
                    )
                    if anag:
                        anagrafica_id = anag["id"]

                # Build EmailInbox doc
                doc = EmailInbox(
                    message_id=msg_id or None,
                    uid=str(uid),
                    folder=folder,
                    from_address=from_addr,
                    from_name=from_name or None,
                    to_addresses=to_list,
                    cc_addresses=cc_list,
                    subject=subject or None,
                    body_text=body_text or None,
                    body_html=body_html or None,
                    date=date_iso,
                    has_attachments=any(
                        ("attachment" in (p.get("Content-Disposition") or "").lower())
                        for p in (msg.walk() if msg.is_multipart() else [])
                    ),
                    categoria=categoria,
                    smistato_a=smistato_a,
                    anagrafica_id=anagrafica_id,
                ).model_dump()

                await db.email_inbox.insert_one(doc)
                nuovi += 1

                # Se mittente conosciuto → log diario cliente
                if anagrafica_id:
                    diary = DiarioCliente(
                        anagrafica_id=anagrafica_id,
                        tipo="email_in",
                        titolo=f"Email da {from_name or from_addr}: {subject or '(no subject)'}"[:200],
                        contenuto=(body_text or "")[:2000],
                        email_inbox_id=doc["id"],
                    ).model_dump()
                    await db.diario_cliente.insert_one(diary)
            except Exception:
                logger.exception("Errore processing email UID=%s", uid_bytes)
                errori += 1
                continue

        try:
            M.close()
        except Exception:
            pass
        M.logout()
    except Exception as e:
        logger.exception("IMAP poll generico fallito")
        return {"ok": False, "errore": f"IMAP poll: {e}"}

    # Aggiorna stato
    upd = {
        "imap_poller_last_run": _now_iso(),
        "imap_poller_last_uid": max_uid_seen,
    }
    if az.get("id"):
        await db.azienda_config.update_one({"id": az["id"]}, {"$set": upd})

    return {
        "ok": True,
        "nuovi": nuovi,
        "saltati": saltati,
        "errori": errori,
        "last_uid": max_uid_seen,
    }


# ============================================================
# Scheduler control
# ============================================================
def is_running() -> bool:
    return _scheduler is not None and _scheduler.get_job(_job_id) is not None


def start_scheduler(db: AsyncIOMotorDatabase, *, minutes: int = 5) -> None:
    """Avvia (o riavvia) lo scheduler IMAP."""
    global _scheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    if _scheduler is None:
        try:
            from tzlocal import get_localzone
            tz = get_localzone()
        except Exception:
            tz = timezone.utc
        _scheduler = AsyncIOScheduler(timezone=tz)
        _scheduler.start()

    async def _job() -> None:
        try:
            res = await poll_once(db)
            logger.info("IMAP poller: %s", res)
        except Exception:
            logger.exception("Errore esecuzione job IMAP poller")

    _scheduler.add_job(
        _job, IntervalTrigger(minutes=max(1, int(minutes))),
        id=_job_id, replace_existing=True, misfire_grace_time=120,
        max_instances=1, coalesce=True,
    )
    logger.info("IMAP poller scheduler avviato (ogni %d minuti)", minutes)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.remove_job(_job_id)
        except Exception:
            pass
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
