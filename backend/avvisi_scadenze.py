"""Modulo Avvisi di Scadenza.

Job giornaliero (08:00 locale) che:
1. Calcola le polizze e i titoli in scadenza nei prossimi N giorni (configurabile).
2. Compone e invia un'email di riepilogo all'amministratore (se SMTP configurato).
3. Salva una notifica in DB (collection: ``notifiche_scadenze``) per log/audit.

Refactor: `cerca_scadenze` e `esegui_job_scadenze` sono state spezzate in
helper di responsabilità singola (query DB, formattazione record, costruzione
log entry, risoluzione destinatario, invio email).
"""
from __future__ import annotations

import logging
import os
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers base
# ---------------------------------------------------------------------------
def _today() -> date:
    return date.today()


def _iso(d: date) -> str:
    return d.isoformat()


def _fmt_eur(v: Optional[float]) -> str:
    try:
        return f"{float(v or 0):.2f} €"
    except (TypeError, ValueError):
        return "0.00 €"


def _fmt_date(s: Optional[str]) -> str:
    if not s:
        return "—"
    try:
        return date.fromisoformat(s[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return s


def _giorni_da_oggi(scadenza_iso: Optional[str], oggi: date) -> Optional[int]:
    if not scadenza_iso:
        return None
    try:
        return (date.fromisoformat(scadenza_iso[:10]) - oggi).days
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Query layer
# ---------------------------------------------------------------------------
async def _query_polizze_in_scadenza(
    db: AsyncIOMotorDatabase, oggi_iso: str, limite_iso: str,
) -> list[dict]:
    cur = db.polizze.find(
        {
            "scadenza": {"$gte": oggi_iso, "$lte": limite_iso},
            "stato": {"$in": ["attiva", "in_attesa"]},
        },
        {"_id": 0},
    ).sort("scadenza", 1)
    return await cur.to_list(2000)


async def _query_titoli_arretrati(
    db: AsyncIOMotorDatabase, oggi_iso: str,
) -> list[dict]:
    cur = db.titoli.find(
        {
            "scadenza": {"$lt": oggi_iso},
            "stato": {"$in": ["da_incassare", "insoluto"]},
        },
        {"_id": 0},
    ).sort("scadenza", 1)
    return await cur.to_list(2000)


async def _carica_anagrafiche(
    db: AsyncIOMotorDatabase, ana_ids: list[str], cache: dict[str, dict],
) -> None:
    """Riempie `cache` in-place con anagrafiche non ancora presenti."""
    mancanti = [aid for aid in ana_ids if aid and aid not in cache]
    if not mancanti:
        return
    async for a in db.anagrafiche.find(
        {"id": {"$in": mancanti}},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "cellulare": 1, "email": 1},
    ):
        cache[a["id"]] = a


async def _carica_compagnie(
    db: AsyncIOMotorDatabase, cmp_ids: list[str], cache: dict[str, dict],
) -> None:
    mancanti = [cid for cid in cmp_ids if cid and cid not in cache]
    if not mancanti:
        return
    async for c in db.compagnie.find(
        {"id": {"$in": mancanti}},
        {"_id": 0, "id": 1, "ragione_sociale": 1},
    ):
        cache[c["id"]] = c


# ---------------------------------------------------------------------------
# Formattazione record
# ---------------------------------------------------------------------------
def _format_polizza_record(p: dict, anas: dict, cmps: dict, oggi: date) -> dict:
    a = anas.get(p.get("contraente_id"), {})
    c = cmps.get(p.get("compagnia_id"), {})
    return {
        "id": p["id"],
        "numero_polizza": p.get("numero_polizza"),
        "ramo": p.get("ramo"),
        "targa": p.get("targa"),
        "scadenza": p.get("scadenza"),
        "giorni_alla_scadenza": _giorni_da_oggi(p.get("scadenza"), oggi),
        "premio_lordo": p.get("premio_lordo", 0.0),
        "contraente_id": a.get("id"),
        "contraente_nome": a.get("ragione_sociale"),
        "contraente_cellulare": a.get("cellulare"),
        "contraente_email": a.get("email"),
        "compagnia_nome": c.get("ragione_sociale"),
    }


def _format_titolo_record(
    t: dict, pol_map: dict, anas: dict, cmps: dict, oggi: date,
) -> dict:
    p = pol_map.get(t.get("polizza_id"), {})
    a = anas.get(p.get("contraente_id"), {})
    c = cmps.get(p.get("compagnia_id"), {})
    return {
        "id": t["id"],
        "polizza_id": t.get("polizza_id"),
        "numero_polizza": p.get("numero_polizza"),
        "ramo": p.get("ramo"),
        "scadenza": t.get("scadenza"),
        "giorni_alla_scadenza": _giorni_da_oggi(t.get("scadenza"), oggi),
        "importo_lordo": t.get("importo_lordo", 0.0),
        "stato": t.get("stato"),
        "contraente_id": a.get("id"),
        "contraente_nome": a.get("ragione_sociale"),
        "contraente_cellulare": a.get("cellulare"),
        "contraente_email": a.get("email"),
        "compagnia_nome": c.get("ragione_sociale"),
    }


# ---------------------------------------------------------------------------
# API pubblica: cerca scadenze
# ---------------------------------------------------------------------------
async def cerca_scadenze(db: AsyncIOMotorDatabase, giorni: int) -> dict[str, list[dict]]:
    """Ritorna polizze (in scadenza) + titoli (arretrati) entro `giorni` giorni."""
    oggi = _today()
    limite = oggi + timedelta(days=max(0, giorni))
    oggi_iso, limite_iso = _iso(oggi), _iso(limite)

    polizze = await _query_polizze_in_scadenza(db, oggi_iso, limite_iso)
    titoli = await _query_titoli_arretrati(db, oggi_iso)

    # carico polizze referenziate dai titoli
    pol_ids = list({t.get("polizza_id") for t in titoli if t.get("polizza_id")})
    pol_map: dict[str, dict] = {}
    if pol_ids:
        async for p in db.polizze.find(
            {"id": {"$in": pol_ids}},
            {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1,
             "contraente_id": 1, "compagnia_id": 1},
        ):
            pol_map[p["id"]] = p

    # cache anagrafiche/compagnie usate da polizze + titoli
    anas: dict[str, dict] = {}
    cmps: dict[str, dict] = {}
    ana_ids = [p.get("contraente_id") for p in polizze]
    cmp_ids = [p.get("compagnia_id") for p in polizze]
    ana_ids += [p.get("contraente_id") for p in pol_map.values()]
    cmp_ids += [p.get("compagnia_id") for p in pol_map.values()]
    await _carica_anagrafiche(db, ana_ids, anas)
    await _carica_compagnie(db, cmp_ids, cmps)

    polizze_out = [_format_polizza_record(p, anas, cmps, oggi) for p in polizze]
    titoli_out = [_format_titolo_record(t, pol_map, anas, cmps, oggi) for t in titoli]
    return {"polizze": polizze_out, "titoli": titoli_out}


# ---------------------------------------------------------------------------
# Rendering email
# ---------------------------------------------------------------------------
def _email_row_html(item: dict, *, importo_key: str) -> str:
    urgent = (item.get("giorni_alla_scadenza") or 999) <= 3
    color = "#dc2626" if urgent else "#0f172a"
    return (
        "<tr>"
        f"<td style='padding:6px 10px;color:{color};font-weight:600'>{_fmt_date(item.get('scadenza'))}</td>"
        f"<td style='padding:6px 10px;color:{color}'>{item.get('giorni_alla_scadenza','?')} gg</td>"
        f"<td style='padding:6px 10px;font-family:monospace'>{item.get('numero_polizza','—')}</td>"
        f"<td style='padding:6px 10px'>{item.get('ramo','—')}</td>"
        f"<td style='padding:6px 10px'>{item.get('contraente_nome','—')}</td>"
        f"<td style='padding:6px 10px;text-align:right'>{_fmt_eur(item.get(importo_key))}</td>"
        "</tr>"
    )


def _email_section_rows(items: list[dict], *, importo_key: str, empty_label: str) -> str:
    if not items:
        return (f"<tr><td colspan='6' style='padding:8px;color:#94a3b8;"
                f"font-style:italic'>{empty_label}</td></tr>")
    return "".join(_email_row_html(it, importo_key=importo_key) for it in items)


def _render_email_html(scadenze: dict[str, list[dict]], giorni: int) -> tuple[str, str, str]:
    """Ritorna (subject, text, html) della mail di riepilogo."""
    pol = scadenze.get("polizze", [])
    tit = scadenze.get("titoli", [])
    oggi = _today().strftime("%d/%m/%Y")
    subject = (f"Avvisi di scadenza — {oggi} "
               f"({len(pol)} polizze, {len(tit)} titoli nei prossimi {giorni} gg)")

    # versione testo
    lines = [f"Riepilogo scadenze al {oggi} (prossimi {giorni} giorni)", ""]
    lines.append(f"POLIZZE IN SCADENZA: {len(pol)}")
    for p in pol[:200]:
        lines.append(
            f"  - {_fmt_date(p['scadenza'])} ({p.get('giorni_alla_scadenza','?')} gg) | "
            f"{p.get('numero_polizza','—')} | {p.get('ramo','—')} | "
            f"{p.get('contraente_nome','—')} | {_fmt_eur(p.get('premio_lordo'))}"
        )
    lines.append("")
    lines.append(f"TITOLI IN SCADENZA: {len(tit)}")
    for t in tit[:200]:
        lines.append(
            f"  - {_fmt_date(t['scadenza'])} ({t.get('giorni_alla_scadenza','?')} gg) | "
            f"{t.get('numero_polizza','—')} | {t.get('ramo','—')} | "
            f"{t.get('contraente_nome','—')} | {_fmt_eur(t.get('importo_lordo'))}"
        )
    text = "\n".join(lines)

    th_style = ("padding:8px 10px;background:#f1f5f9;text-align:left;font-size:11px;"
                "text-transform:uppercase;color:#475569;letter-spacing:0.05em")
    rows_pol = _email_section_rows(pol, importo_key="premio_lordo",
                                   empty_label="Nessuna polizza in scadenza.")
    rows_tit = _email_section_rows(tit, importo_key="importo_lordo",
                                   empty_label="Nessun titolo in scadenza.")
    html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'></head>
<body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#f8fafc;padding:20px;color:#0f172a'>
  <div style='max-width:900px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0'>
    <div style='padding:20px 24px;border-bottom:1px solid #e2e8f0;background:#0f172a;color:white'>
      <div style='font-size:20px;font-weight:700'>Avvisi di Scadenza</div>
      <div style='font-size:13px;color:#cbd5e1;margin-top:4px'>Riepilogo del {oggi} — prossimi {giorni} giorni</div>
    </div>
    <div style='padding:24px;display:flex;gap:16px'>
      <div style='flex:1;background:#fef3c7;border:1px solid #fcd34d;border-radius:6px;padding:12px'>
        <div style='font-size:11px;text-transform:uppercase;color:#92400e;letter-spacing:0.05em'>Polizze in scadenza</div>
        <div style='font-size:32px;font-weight:700;color:#b45309'>{len(pol)}</div>
      </div>
      <div style='flex:1;background:#dbeafe;border:1px solid #93c5fd;border-radius:6px;padding:12px'>
        <div style='font-size:11px;text-transform:uppercase;color:#1e40af;letter-spacing:0.05em'>Titoli in scadenza</div>
        <div style='font-size:32px;font-weight:700;color:#1d4ed8'>{len(tit)}</div>
      </div>
    </div>
    <div style='padding:0 24px 24px'>
      <h3 style='margin:16px 0 8px;font-size:14px;color:#0f172a'>Polizze</h3>
      <table style='width:100%;border-collapse:collapse;border:1px solid #e2e8f0;font-size:13px'>
        <thead><tr>
          <th style='{th_style}'>Scadenza</th><th style='{th_style}'>Tra</th>
          <th style='{th_style}'>N. Polizza</th><th style='{th_style}'>Ramo</th>
          <th style='{th_style}'>Contraente</th><th style='{th_style};text-align:right'>Premio</th>
        </tr></thead>
        <tbody>{rows_pol}</tbody>
      </table>

      <h3 style='margin:24px 0 8px;font-size:14px;color:#0f172a'>Titoli</h3>
      <table style='width:100%;border-collapse:collapse;border:1px solid #e2e8f0;font-size:13px'>
        <thead><tr>
          <th style='{th_style}'>Scadenza</th><th style='{th_style}'>Tra</th>
          <th style='{th_style}'>N. Polizza</th><th style='{th_style}'>Ramo</th>
          <th style='{th_style}'>Contraente</th><th style='{th_style};text-align:right'>Importo</th>
        </tr></thead>
        <tbody>{rows_tit}</tbody>
      </table>
    </div>
    <div style='padding:12px 24px;border-top:1px solid #e2e8f0;background:#f8fafc;font-size:11px;color:#64748b'>
      Email generata automaticamente dal sistema Programma Assicurativo.
    </div>
  </div>
</body></html>
"""
    return subject, text, html


def _invia_email(az: dict, to_addr: str, subject: str, text: str, html: str) -> None:
    """Invia email via SMTP. Solleva in caso di errore."""
    msg = EmailMessage()
    msg["From"] = az.get("smtp_from") or az.get("smtp_user") or "noreply@assicura.local"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    port = int(az.get("smtp_port") or 587)
    host = az["smtp_host"]
    if port == 465:
        srv = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        srv = smtplib.SMTP(host, port, timeout=30)
        if az.get("smtp_use_tls", True):
            srv.starttls()
    if az.get("smtp_user"):
        srv.login(az["smtp_user"], az.get("smtp_password") or "")
    srv.send_message(msg)
    srv.quit()


# ---------------------------------------------------------------------------
# Job orchestrazione
# ---------------------------------------------------------------------------
def _resolve_destinatario(az: dict) -> Optional[str]:
    return (
        az.get("notifica_scadenze_email_admin")
        or az.get("email_commercialista")
        or os.environ.get("ADMIN_EMAIL")
    )


def _build_log_entry(*, manuale: bool, giorni: int, n_pol: int, n_tit: int,
                     to_addr: Optional[str]) -> dict[str, Any]:
    return {
        "id": f"NS-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "eseguito_at": datetime.now(timezone.utc).isoformat(),
        "manuale": manuale,
        "giorni": giorni,
        "n_polizze": n_pol,
        "n_titoli": n_tit,
        "destinatario": to_addr,
        "email_inviata": False,
        "errore": None,
    }


async def _persist_log(db: AsyncIOMotorDatabase, log_entry: dict) -> None:
    await db.notifiche_scadenze.insert_one(log_entry)


async def esegui_job_scadenze(db: AsyncIOMotorDatabase, *, manuale: bool = False) -> dict[str, Any]:
    """Esegue il job avvisi scadenze. Salva traccia su ``db.notifiche_scadenze``."""
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    if not manuale and not az.get("notifica_scadenze_attiva", True):
        logger.info("Avvisi scadenze: disattivato in configurazione.")
        return {"ok": False, "skipped": True, "motivo": "Disattivato in Librerie/Azienda"}

    giorni = int(az.get("notifica_scadenze_giorni") or 15)
    scadenze = await cerca_scadenze(db, giorni)
    n_pol, n_tit = len(scadenze["polizze"]), len(scadenze["titoli"])

    to_addr = _resolve_destinatario(az)
    log_entry = _build_log_entry(manuale=manuale, giorni=giorni,
                                 n_pol=n_pol, n_tit=n_tit, to_addr=to_addr)

    # nothing to notify
    if n_pol == 0 and n_tit == 0:
        log_entry["motivo"] = "Nessuna scadenza nel periodo"
        await _persist_log(db, log_entry)
        logger.info("Avvisi scadenze: nessuna scadenza nei prossimi %s giorni.", giorni)
        return {"ok": True, "n_polizze": 0, "n_titoli": 0, "email_inviata": False,
                "motivo": "Nessuna scadenza nel periodo"}

    # destinatario mancante
    if not to_addr:
        log_entry["errore"] = ("Destinatario non configurato "
                               "(notifica_scadenze_email_admin / email_commercialista)")
        await _persist_log(db, log_entry)
        return {"ok": False, "errore": log_entry["errore"], "n_polizze": n_pol, "n_titoli": n_tit}

    # smtp non configurato
    if not (az.get("smtp_host") and az.get("smtp_user")):
        log_entry["errore"] = "SMTP non configurato in Librerie/Azienda"
        await _persist_log(db, log_entry)
        return {"ok": False, "errore": log_entry["errore"], "n_polizze": n_pol, "n_titoli": n_tit,
                "scadenze": scadenze}

    # invio email
    subject, text, html = _render_email_html(scadenze, giorni)
    try:
        _invia_email(az, to_addr, subject, text, html)
    except Exception as e:
        log_entry["errore"] = str(e)
        await _persist_log(db, log_entry)
        logger.exception("Errore invio avvisi scadenze")
        return {"ok": False, "errore": str(e), "n_polizze": n_pol, "n_titoli": n_tit}

    log_entry["email_inviata"] = True
    await _persist_log(db, log_entry)
    logger.info("Avvisi scadenze inviati a %s: %d polizze, %d titoli", to_addr, n_pol, n_tit)
    return {"ok": True, "n_polizze": n_pol, "n_titoli": n_tit,
            "email_inviata": True, "destinatario": to_addr}


# ============== Scheduler =================

_scheduler = None  # AsyncIOScheduler


def start_scheduler(db: AsyncIOMotorDatabase, *, hour: int = 8, minute: int = 0) -> None:
    """Avvia lo scheduler con il cron giornaliero degli avvisi scadenze."""
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    try:
        from tzlocal import get_localzone
        tz = get_localzone()
    except Exception:
        tz = timezone.utc

    sched = AsyncIOScheduler(timezone=tz)

    async def _job():
        try:
            await esegui_job_scadenze(db, manuale=False)
        except Exception:
            logger.exception("Errore esecuzione job avvisi scadenze")

    sched.add_job(
        _job, CronTrigger(hour=hour, minute=minute),
        id="avvisi_scadenze_daily", replace_existing=True, misfire_grace_time=3600,
    )
    sched.start()
    _scheduler = sched
    logger.info("Scheduler avvisi scadenze avviato (cron %02d:%02d, tz=%s)", hour, minute, tz)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        finally:
            _scheduler = None
