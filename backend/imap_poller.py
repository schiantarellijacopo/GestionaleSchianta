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


def _extract_attachments(msg, *, uid: int) -> list[dict]:
    """Estrae gli allegati dal messaggio MIME e li salva nello storage.

    Restituisce lista di dict ``{filename, content_type, size, storage_path, url}``.
    Storage path: ``email/<uid>/<index>_<filename_sanitized>``.
    """
    import re as _re
    import storage as obj_storage
    out: list[dict] = []
    if not msg.is_multipart():
        return out
    idx = 0
    for part in msg.walk():
        disp = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()
        if not (("attachment" in disp or "inline" in disp) and filename):
            continue
        try:
            from email.header import decode_header as _dh
            decoded = _dh(filename)
            filename = "".join(
                (p.decode(enc or "utf-8", errors="replace") if isinstance(p, bytes) else p)
                for p, enc in decoded
            )
        except Exception:
            pass
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        ctype = part.get_content_type() or "application/octet-stream"
        # sanitize filename
        safe = _re.sub(r"[^\w.\- ]+", "_", filename)[:120].strip() or f"file_{idx}"
        path = f"email/{uid}/{idx}_{safe}"
        try:
            obj_storage.put_object(path, payload, ctype)
        except Exception:
            logger.exception("Errore upload allegato %s", filename)
            continue
        out.append({
            "filename": filename,
            "content_type": ctype,
            "size": len(payload),
            "storage_path": path,
            "url": f"/api/storage/{path}",
        })
        idx += 1
    return out


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
# Auto-collegamento polizze firmate da email
# ============================================================
# Regex per estrarre numeri polizza candidati da testo/oggetto/nome-file.
# Supporta i formati più comuni delle compagnie italiane:
#  - numeri puri di 6-14 cifre
#  - alfanumerici con separatori (POL-2024-000123, P.2024.001, ABC/12345)
#  - preceduti da "polizza n.", "n. polizza", "polizza:"
_NUM_POLIZZA_RE = re.compile(
    r"(?:polizza\s*(?:n[°º\.]|nr\.?|num(?:ero)?\.?)?\s*[:.]?\s*)?"
    r"([A-Z]{0,4}[-\.\/]?\d[\d\-\.\/A-Z]{5,20}\d)",
    re.IGNORECASE,
)


def _candidati_numeri_polizza(*testi: str) -> list[str]:
    """Estrae candidati numero polizza da uno o più testi (oggetto, body, filename).
    Ritorna lista deduplicata di stringhe normalizzate (uppercase, senza spazi)."""
    seen: set[str] = set()
    out: list[str] = []
    for t in testi:
        if not t:
            continue
        for m in _NUM_POLIZZA_RE.finditer(t):
            raw = (m.group(1) or "").strip().upper()
            # scarto stringhe troppo generiche (es. anno "2024" o "20240215")
            cifre = sum(1 for c in raw if c.isdigit())
            if cifre < 6:
                continue
            if raw in seen:
                continue
            seen.add(raw)
            out.append(raw)
    return out


_KEYWORDS_SINISTRO = ("sinistro", "denuncia", "incidente", "danno", "danni", "perizia", "cid", "constatazione")

_DOC_EXTS = (".pdf", ".jpg", ".jpeg", ".png", ".heic", ".webp", ".doc", ".docx", ".xls", ".xlsx")


def _allegabili(attachments: list[dict]) -> list[dict]:
    """Allegati documentali (PDF, immagini, office) — esclude firme/icone minuscole."""
    out = []
    for a in attachments:
        fn = (a.get("filename") or "").lower()
        if not fn.endswith(_DOC_EXTS):
            continue
        if (a.get("size_kb") or 0) < 8 and not fn.endswith(".pdf"):
            continue  # probabile logo/firma inline
        out.append(a)
    return out


async def _copia_allegato_su_entita(
    db: AsyncIOMotorDatabase, att: dict, *, entita_tipo: str, entita_id: str,
    categoria: str, subject: str,
) -> Optional[dict]:
    """Copia un allegato email nello storage dell'entità e crea il record Allegato."""
    import os as _os
    import storage as obj_storage
    from db_models import Allegato
    # idempotenza: stesso file già copiato su questa entità
    dup = await db.allegati.find_one(
        {"entita_tipo": entita_tipo, "entita_id": entita_id,
         "origine_storage_path": att.get("storage_path")}, {"_id": 1})
    if dup:
        return None
    try:
        data, ctype = obj_storage.get_object(att["storage_path"])
    except Exception:
        logger.exception("Impossibile leggere allegato %s", att.get("storage_path"))
        return None
    app_name = _os.environ.get("APP_NAME", "assicura")
    new_path = f"{app_name}/{entita_tipo}/{entita_id}/email_{_now_iso()[:10]}_{att['filename']}"
    try:
        obj_storage.put_object(new_path, data, ctype or "application/octet-stream")
    except Exception:
        logger.exception("Errore salvataggio allegato %s per %s", entita_tipo, entita_id)
        return None
    alleg = Allegato(
        entita_tipo=entita_tipo, entita_id=entita_id,
        nome_file=att["filename"],
        storage_path=new_path,
        content_type=ctype or att.get("content_type") or "application/octet-stream",
        size=len(data),
        autore_id=None,
    ).model_dump()
    alleg["url"] = f"/api/storage/{new_path}"
    alleg["fonte"] = "email_imap"
    alleg["visibile_cliente"] = False
    alleg["categoria"] = categoria
    alleg["origine_email_subject"] = (subject or "")[:200]
    alleg["origine_storage_path"] = att.get("storage_path")
    await db.allegati.insert_one(alleg)
    return {"entita_tipo": entita_tipo, "entita_id": entita_id,
            "filename": att["filename"], "storage_path": new_path}


async def _auto_allega_sinistro(
    db: AsyncIOMotorDatabase, *, subject: str, body_text: str,
    attachments: list[dict], anagrafica_id: Optional[str],
) -> list[dict]:
    """Collega allegati (PDF e foto) a un sinistro: match per numero sinistro /
    numero interno citato, oppure fallback sull'unico sinistro aperto del cliente
    se il testo parla di sinistro/denuncia/danno."""
    docs = _allegabili(attachments)
    if not docs:
        return []
    testi = [subject or "", body_text or ""] + [a.get("filename", "") for a in docs]
    candidati = _candidati_numeri_polizza(*testi)  # stesso estrattore alfanumerico

    sinistri = []
    if candidati:
        q = {"$or": [
            {"numero_sinistro": {"$in": candidati + [c.lower() for c in candidati]}},
            {"numero_interno": {"$in": candidati + [c.lower() for c in candidati]}},
        ]}
        if anagrafica_id:
            q = {"$and": [q, {"contraente_id": anagrafica_id}]}
        sinistri = await db.sinistri.find(
            q, {"_id": 0, "id": 1, "numero_sinistro": 1, "numero_interno": 1}).to_list(10)
        if sinistri and not anagrafica_id:
            pass  # match esplicito per numero: ok anche senza mittente noto
    if not sinistri and anagrafica_id:
        # fallback: testo parla di sinistro e il cliente ha UN solo sinistro aperto
        blob = f"{subject or ''} {body_text or ''}".lower()
        if any(k in blob for k in _KEYWORDS_SINISTRO):
            aperti = await db.sinistri.find(
                {"contraente_id": anagrafica_id, "stato": {"$in": ["aperto", "in_istruttoria"]}},
                {"_id": 0, "id": 1, "numero_sinistro": 1, "numero_interno": 1}).to_list(3)
            if len(aperti) == 1:
                sinistri = aperti
    if not sinistri:
        return []

    matches: list[dict] = []
    for sin in sinistri:
        for att in docs:
            m = await _copia_allegato_su_entita(
                db, att, entita_tipo="sinistro", entita_id=sin["id"],
                categoria="documentazione_sinistro", subject=subject)
            if m:
                m["numero_sinistro"] = sin.get("numero_sinistro") or sin.get("numero_interno")
                matches.append(m)
    return matches


async def _auto_allega_anagrafica(
    db: AsyncIOMotorDatabase, *, subject: str,
    attachments: list[dict], anagrafica_id: str,
    esclusi_paths: set[str],
) -> list[dict]:
    """Fallback: gli allegati del cliente non collegati a polizza/sinistro finiscono
    nei Documenti della sua anagrafica."""
    matches: list[dict] = []
    for att in _allegabili(attachments):
        if att.get("storage_path") in esclusi_paths:
            continue
        m = await _copia_allegato_su_entita(
            db, att, entita_tipo="anagrafica", entita_id=anagrafica_id,
            categoria="documento_da_email", subject=subject)
        if m:
            matches.append(m)
    return matches


async def _auto_allega_polizza(
    db: AsyncIOMotorDatabase, *, subject: str, body_text: str,
    attachments: list[dict], anagrafica_id: Optional[str],
) -> list[dict]:
    """Se una mail ha allegati PDF e nel testo/oggetto/nome file è citato un
    numero polizza esistente, crea automaticamente un record `Allegato`
    (tipo=polizza) collegato alla polizza e all'anagrafica.

    Ritorna la lista dei match (per il diario). Le polizze auto-allegate sono
    marcate `fonte='email_imap'` e `visibile_cliente=False` (verifica manuale
    prima di renderle visibili nel portale cliente).
    """
    import storage as obj_storage
    from db_models import Allegato
    pdf_attachments = [a for a in attachments if (a.get("content_type", "").lower().endswith("pdf"))
                       or (a.get("filename", "").lower().endswith(".pdf"))]
    if not pdf_attachments:
        return []

    # Testi in cui cercare i candidati
    testi = [subject or "", body_text or ""] + [a.get("filename", "") for a in pdf_attachments]
    candidati = _candidati_numeri_polizza(*testi)
    if not candidati:
        return []

    matches: list[dict] = []
    # Cerca polizze per numero_polizza esatto (case-insensitive)
    q = {"numero_polizza": {"$in": [c for c in candidati] +
                                     [c.lower() for c in candidati]}}
    if anagrafica_id:
        # Se conosciamo il mittente, filtriamo solo sulle sue polizze (evita match casuali)
        q["contraente_id"] = anagrafica_id
    polizze = await db.polizze.find(
        q, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1,
            "ramo": 1, "compagnia_id": 1}).to_list(20)
    if not polizze:
        # fallback: se non conosciamo il mittente, NON facciamo match "aperto"
        # per evitare falsi positivi
        return []

    # Per ogni polizza matchata + ogni PDF, crea un allegato
    for pol in polizze:
        for att in pdf_attachments:
            # Recupera i byte dal path già salvato per copiarli in un path polizza-scoped
            try:
                data, ctype = obj_storage.get_object(att["storage_path"])
            except Exception:
                logger.exception("Impossibile leggere allegato %s per riclassificazione polizza",
                                 att.get("storage_path"))
                continue
            import os as _os
            app_name = _os.environ.get("APP_NAME", "assicura")
            new_path = f"{app_name}/polizze/{pol['id']}/firmata_email_{_now_iso()[:10]}_{att['filename']}"
            try:
                obj_storage.put_object(new_path, data, ctype or "application/pdf")
            except Exception:
                logger.exception("Errore salvataggio allegato polizza %s", pol["id"])
                continue
            alleg = Allegato(
                entita_tipo="polizza", entita_id=pol["id"],
                nome_file=att["filename"],
                storage_path=new_path,
                content_type=ctype or att.get("content_type") or "application/pdf",
                size=len(data),
                autore_id=None,   # System via IMAP
            ).model_dump()
            alleg["url"] = f"/api/storage/{new_path}"
            alleg["fonte"] = "email_imap"
            alleg["visibile_cliente"] = False
            alleg["categoria"] = "polizza_firmata"
            alleg["origine_email_subject"] = (subject or "")[:200]
            await db.allegati.insert_one(alleg)
            # Idempotenza: se dovesse riarrivare per ripolling, il match sarà lo stesso e
            # basta un uniqueness soft (per storage_path).
            matches.append({
                "polizza_id": pol["id"],
                "numero_polizza": pol.get("numero_polizza"),
                "filename": att["filename"],
                "storage_path": new_path,
            })
    return matches


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

                # Estrae e salva allegati nello storage
                attachments = _extract_attachments(msg, uid=uid)

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
                    has_attachments=bool(attachments),
                    attachments=attachments,
                    categoria=categoria,
                    smistato_a=smistato_a,
                    anagrafica_id=anagrafica_id,
                ).model_dump()

                await db.email_inbox.insert_one(doc)
                nuovi += 1

                # Auto-collega allegati → polizza / sinistro / anagrafica
                polizze_matched: list[dict] = []
                sinistri_matched: list[dict] = []
                anagrafica_matched: list[dict] = []
                if attachments:
                    try:
                        polizze_matched = await _auto_allega_polizza(
                            db, subject=subject or "", body_text=body_text or "",
                            attachments=attachments, anagrafica_id=anagrafica_id,
                        )
                    except Exception:
                        logger.exception("Errore auto-allegamento polizza per email UID=%s", uid)
                    try:
                        sinistri_matched = await _auto_allega_sinistro(
                            db, subject=subject or "", body_text=body_text or "",
                            attachments=attachments, anagrafica_id=anagrafica_id,
                        )
                    except Exception:
                        logger.exception("Errore auto-allegamento sinistro per email UID=%s", uid)
                    # fallback: mittente = cliente noto → resto degli allegati nei suoi Documenti
                    if anagrafica_id:
                        try:
                            usati = {m.get("storage_path") for m in polizze_matched} | \
                                    {m.get("storage_path") for m in sinistri_matched}
                            origine_usate = set()
                            for m in polizze_matched + sinistri_matched:
                                origine_usate.add(m.get("filename"))
                            esclusi = {a.get("storage_path") for a in attachments
                                       if a.get("filename") in origine_usate}
                            anagrafica_matched = await _auto_allega_anagrafica(
                                db, subject=subject or "", attachments=attachments,
                                anagrafica_id=anagrafica_id, esclusi_paths=esclusi,
                            )
                        except Exception:
                            logger.exception("Errore auto-allegamento anagrafica per email UID=%s", uid)
                    if polizze_matched or sinistri_matched or anagrafica_matched:
                        await db.email_inbox.update_one(
                            {"uid": str(uid), "folder": folder},
                            {"$set": {"polizze_matched": polizze_matched,
                                      "sinistri_matched": sinistri_matched,
                                      "allegati_anagrafica": anagrafica_matched}},
                        )

                # Se mittente conosciuto → log diario cliente (usa collection `db.diario`)
                if anagrafica_id:
                    try:
                        from shared import log_diario_cliente
                        desc = f"Email ricevuta da {from_name or from_addr}: {subject or '(no subject)'}"
                        dettagli = []
                        if polizze_matched:
                            nums = ", ".join(sorted({str(m.get('numero_polizza') or '') for m in polizze_matched}))
                            dettagli.append(f"📎 allegati collegati a polizza {nums}")
                        if sinistri_matched:
                            nums = ", ".join(sorted({str(m.get('numero_sinistro') or '') for m in sinistri_matched}))
                            dettagli.append(f"📎 allegati collegati a sinistro {nums}")
                        if anagrafica_matched:
                            dettagli.append(f"📎 {len(anagrafica_matched)} documenti salvati in anagrafica")
                        if dettagli:
                            desc += " — " + " · ".join(dettagli)
                        await log_diario_cliente(
                            anagrafica_id,
                            "email",
                            desc[:250],
                            (body_text or "")[:2000],
                            autore=None,  # System
                        )
                    except Exception:
                        logger.exception("Errore log diario cliente per email %s", uid)
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
# Backfill: ri-processa allegati di email GIÀ ingerite
# ============================================================
async def retry_auto_allega(db: AsyncIOMotorDatabase, *, limit: int = 500) -> dict:
    """Ri-esegue l'auto-collegamento allegati (polizza/sinistro/anagrafica) sulle
    email già presenti in ``email_inbox`` che hanno allegati ma nessun match salvato.

    Serve quando l'email è arrivata PRIMA che la polizza/sinistro esistesse nel CRM
    (il re-polling IMAP salta le email già ingerite, quindi non ri-tenta il match).
    Idempotente: ``_copia_allegato_su_entita`` salta i file già copiati.
    """
    q = {
        "has_attachments": True,
        "$or": [
            {"polizze_matched": {"$in": [None, []]}},
            {"polizze_matched": {"$exists": False}},
        ],
    }
    cursor = db.email_inbox.find(
        q, {"_id": 0, "id": 1, "uid": 1, "folder": 1, "subject": 1, "body_text": 1,
            "attachments": 1, "anagrafica_id": 1, "from_name": 1, "from_address": 1},
    ).limit(limit)
    esaminate = 0
    con_match = 0
    tot_polizze = 0
    tot_sinistri = 0
    tot_anagrafica = 0
    async for em in cursor:
        esaminate += 1
        attachments = em.get("attachments") or []
        if not attachments:
            continue
        subject = em.get("subject") or ""
        body_text = em.get("body_text") or ""
        anagrafica_id = em.get("anagrafica_id")
        polizze_matched: list[dict] = []
        sinistri_matched: list[dict] = []
        anagrafica_matched: list[dict] = []
        try:
            polizze_matched = await _auto_allega_polizza(
                db, subject=subject, body_text=body_text,
                attachments=attachments, anagrafica_id=anagrafica_id)
        except Exception:
            logger.exception("retry: errore auto-allega polizza email %s", em.get("uid"))
        try:
            sinistri_matched = await _auto_allega_sinistro(
                db, subject=subject, body_text=body_text,
                attachments=attachments, anagrafica_id=anagrafica_id)
        except Exception:
            logger.exception("retry: errore auto-allega sinistro email %s", em.get("uid"))
        if anagrafica_id:
            try:
                origine_usate = {m.get("filename") for m in polizze_matched + sinistri_matched}
                esclusi = {a.get("storage_path") for a in attachments
                           if a.get("filename") in origine_usate}
                anagrafica_matched = await _auto_allega_anagrafica(
                    db, subject=subject, attachments=attachments,
                    anagrafica_id=anagrafica_id, esclusi_paths=esclusi)
            except Exception:
                logger.exception("retry: errore auto-allega anagrafica email %s", em.get("uid"))
        if polizze_matched or sinistri_matched or anagrafica_matched:
            con_match += 1
            tot_polizze += len(polizze_matched)
            tot_sinistri += len(sinistri_matched)
            tot_anagrafica += len(anagrafica_matched)
            await db.email_inbox.update_one(
                {"id": em["id"]},
                {"$set": {"polizze_matched": polizze_matched,
                          "sinistri_matched": sinistri_matched,
                          "allegati_anagrafica": anagrafica_matched}},
            )
            if anagrafica_id:
                try:
                    from shared import log_diario_cliente
                    dettagli = []
                    if polizze_matched:
                        nums = ", ".join(sorted({str(m.get('numero_polizza') or '') for m in polizze_matched}))
                        dettagli.append(f"📎 allegati collegati a polizza {nums}")
                    if sinistri_matched:
                        nums = ", ".join(sorted({str(m.get('numero_sinistro') or '') for m in sinistri_matched}))
                        dettagli.append(f"📎 allegati collegati a sinistro {nums}")
                    if anagrafica_matched:
                        dettagli.append(f"📎 {len(anagrafica_matched)} documenti salvati in anagrafica")
                    if dettagli:
                        desc = f"Allegati email da {em.get('from_name') or em.get('from_address')}: " + " · ".join(dettagli)
                        await log_diario_cliente(anagrafica_id, "email", desc[:250], "", autore=None)
                except Exception:
                    logger.exception("retry: errore log diario email %s", em.get("uid"))
    return {
        "ok": True,
        "esaminate": esaminate,
        "con_match": con_match,
        "allegati_polizza": tot_polizze,
        "allegati_sinistro": tot_sinistri,
        "allegati_anagrafica": tot_anagrafica,
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
