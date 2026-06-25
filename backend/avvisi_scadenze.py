"""Modulo Avvisi di Scadenza.

Job giornaliero (08:00 locale) che:
1. Calcola le polizze e i titoli in scadenza nei prossimi N giorni (configurabile).
2. Compone e invia un'email di riepilogo all'amministratore (se SMTP configurato).
3. Salva una notifica in DB (collection: ``notifiche_scadenze``) per log/audit.

Configurazione (collection: ``azienda_config``):
    - ``notifica_scadenze_attiva`` (bool, default True)
    - ``notifica_scadenze_giorni`` (int, default 15)
    - ``notifica_scadenze_email_admin`` (string) — destinatario; fallback ADMIN_EMAIL env.
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


def _today() -> date:
    return date.today()


def _iso(d: date) -> str:
    return d.isoformat()


def _fmt_eur(v: Optional[float]) -> str:
    try:
        return f"{float(v or 0):.2f} €"
    except Exception:
        return "0.00 €"


def _fmt_date(s: Optional[str]) -> str:
    if not s:
        return "—"
    try:
        return date.fromisoformat(s[:10]).strftime("%d/%m/%Y")
    except Exception:
        return s


async def cerca_scadenze(db: AsyncIOMotorDatabase, giorni: int) -> dict[str, list[dict]]:
    """Ritorna polizze e titoli in scadenza nei prossimi `giorni` giorni (oggi compreso)."""
    oggi = _today()
    limite = oggi + timedelta(days=max(0, giorni))
    oggi_iso, limite_iso = _iso(oggi), _iso(limite)

    # POLIZZE: scadenza compresa, stato attiva/in_attesa.
    polizze_cur = db.polizze.find(
        {
            "scadenza": {"$gte": oggi_iso, "$lte": limite_iso},
            "stato": {"$in": ["attiva", "in_attesa"]},
        },
        {"_id": 0},
    ).sort("scadenza", 1)
    polizze = await polizze_cur.to_list(2000)

    # arricchimento: contraente + compagnia
    ana_ids = list({p.get("contraente_id") for p in polizze if p.get("contraente_id")})
    cmp_ids = list({p.get("compagnia_id") for p in polizze if p.get("compagnia_id")})
    anas: dict[str, dict] = {}
    cmps: dict[str, dict] = {}
    if ana_ids:
        async for a in db.anagrafiche.find(
            {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "cellulare": 1, "email": 1},
        ):
            anas[a["id"]] = a
    if cmp_ids:
        async for c in db.compagnie.find(
            {"id": {"$in": cmp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1},
        ):
            cmps[c["id"]] = c

    polizze_out: list[dict] = []
    for p in polizze:
        a = anas.get(p.get("contraente_id"), {})
        c = cmps.get(p.get("compagnia_id"), {})
        try:
            g = (date.fromisoformat(p["scadenza"][:10]) - oggi).days
        except Exception:
            g = None
        polizze_out.append({
            "id": p["id"],
            "numero_polizza": p.get("numero_polizza"),
            "ramo": p.get("ramo"),
            "targa": p.get("targa"),
            "scadenza": p.get("scadenza"),
            "giorni_alla_scadenza": g,
            "premio_lordo": p.get("premio_lordo", 0.0),
            "contraente_id": a.get("id"),
            "contraente_nome": a.get("ragione_sociale"),
            "contraente_cellulare": a.get("cellulare"),
            "contraente_email": a.get("email"),
            "compagnia_nome": c.get("ragione_sociale"),
        })

    # TITOLI: scadenza nel range, stato da_incassare/insoluto.
    titoli_cur = db.titoli.find(
        {
            "scadenza": {"$gte": oggi_iso, "$lte": limite_iso},
            "stato": {"$in": ["da_incassare", "insoluto"]},
        },
        {"_id": 0},
    ).sort("scadenza", 1)
    titoli = await titoli_cur.to_list(2000)
    pol_ids = list({t.get("polizza_id") for t in titoli if t.get("polizza_id")})
    pol_map: dict[str, dict] = {}
    if pol_ids:
        async for p in db.polizze.find(
            {"id": {"$in": pol_ids}},
            {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "contraente_id": 1, "compagnia_id": 1},
        ):
            pol_map[p["id"]] = p
    # arricchisci anagrafica/compagnia mancanti
    extra_ana = [p.get("contraente_id") for p in pol_map.values() if p.get("contraente_id") and p["contraente_id"] not in anas]
    extra_cmp = [p.get("compagnia_id") for p in pol_map.values() if p.get("compagnia_id") and p["compagnia_id"] not in cmps]
    if extra_ana:
        async for a in db.anagrafiche.find(
            {"id": {"$in": extra_ana}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "cellulare": 1, "email": 1},
        ):
            anas[a["id"]] = a
    if extra_cmp:
        async for c in db.compagnie.find(
            {"id": {"$in": extra_cmp}}, {"_id": 0, "id": 1, "ragione_sociale": 1},
        ):
            cmps[c["id"]] = c

    titoli_out: list[dict] = []
    for t in titoli:
        p = pol_map.get(t.get("polizza_id"), {})
        a = anas.get(p.get("contraente_id"), {})
        c = cmps.get(p.get("compagnia_id"), {})
        try:
            g = (date.fromisoformat(t["scadenza"][:10]) - oggi).days
        except Exception:
            g = None
        titoli_out.append({
            "id": t["id"],
            "polizza_id": t.get("polizza_id"),
            "numero_polizza": p.get("numero_polizza"),
            "ramo": p.get("ramo"),
            "scadenza": t.get("scadenza"),
            "giorni_alla_scadenza": g,
            "importo_lordo": t.get("importo_lordo", 0.0),
            "stato": t.get("stato"),
            "contraente_id": a.get("id"),
            "contraente_nome": a.get("ragione_sociale"),
            "contraente_cellulare": a.get("cellulare"),
            "contraente_email": a.get("email"),
            "compagnia_nome": c.get("ragione_sociale"),
        })

    return {"polizze": polizze_out, "titoli": titoli_out}


def _render_email_html(scadenze: dict[str, list[dict]], giorni: int) -> tuple[str, str, str]:
    """Ritorna (subject, text, html) della mail di riepilogo."""
    pol = scadenze.get("polizze", [])
    tit = scadenze.get("titoli", [])
    oggi = _today().strftime("%d/%m/%Y")
    subject = f"Avvisi di scadenza — {oggi} ({len(pol)} polizze, {len(tit)} titoli nei prossimi {giorni} gg)"

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

    # versione HTML
    def _rows_pol(items: list[dict]) -> str:
        if not items:
            return "<tr><td colspan='6' style='padding:8px;color:#94a3b8;font-style:italic'>Nessuna polizza in scadenza.</td></tr>"
        rows = []
        for p in items:
            urgent = (p.get("giorni_alla_scadenza") or 999) <= 3
            color = "#dc2626" if urgent else "#0f172a"
            rows.append(
                f"<tr>"
                f"<td style='padding:6px 10px;color:{color};font-weight:600'>{_fmt_date(p['scadenza'])}</td>"
                f"<td style='padding:6px 10px;color:{color}'>{p.get('giorni_alla_scadenza','?')} gg</td>"
                f"<td style='padding:6px 10px;font-family:monospace'>{p.get('numero_polizza','—')}</td>"
                f"<td style='padding:6px 10px'>{p.get('ramo','—')}</td>"
                f"<td style='padding:6px 10px'>{p.get('contraente_nome','—')}</td>"
                f"<td style='padding:6px 10px;text-align:right'>{_fmt_eur(p.get('premio_lordo'))}</td>"
                f"</tr>"
            )
        return "".join(rows)

    def _rows_tit(items: list[dict]) -> str:
        if not items:
            return "<tr><td colspan='6' style='padding:8px;color:#94a3b8;font-style:italic'>Nessun titolo in scadenza.</td></tr>"
        rows = []
        for t in items:
            urgent = (t.get("giorni_alla_scadenza") or 999) <= 3
            color = "#dc2626" if urgent else "#0f172a"
            rows.append(
                f"<tr>"
                f"<td style='padding:6px 10px;color:{color};font-weight:600'>{_fmt_date(t['scadenza'])}</td>"
                f"<td style='padding:6px 10px;color:{color}'>{t.get('giorni_alla_scadenza','?')} gg</td>"
                f"<td style='padding:6px 10px;font-family:monospace'>{t.get('numero_polizza','—')}</td>"
                f"<td style='padding:6px 10px'>{t.get('ramo','—')}</td>"
                f"<td style='padding:6px 10px'>{t.get('contraente_nome','—')}</td>"
                f"<td style='padding:6px 10px;text-align:right'>{_fmt_eur(t.get('importo_lordo'))}</td>"
                f"</tr>"
            )
        return "".join(rows)

    th_style = "padding:8px 10px;background:#f1f5f9;text-align:left;font-size:11px;text-transform:uppercase;color:#475569;letter-spacing:0.05em"
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
        <tbody>{_rows_pol(pol)}</tbody>
      </table>

      <h3 style='margin:24px 0 8px;font-size:14px;color:#0f172a'>Titoli</h3>
      <table style='width:100%;border-collapse:collapse;border:1px solid #e2e8f0;font-size:13px'>
        <thead><tr>
          <th style='{th_style}'>Scadenza</th><th style='{th_style}'>Tra</th>
          <th style='{th_style}'>N. Polizza</th><th style='{th_style}'>Ramo</th>
          <th style='{th_style}'>Contraente</th><th style='{th_style};text-align:right'>Importo</th>
        </tr></thead>
        <tbody>{_rows_tit(tit)}</tbody>
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


async def esegui_job_scadenze(db: AsyncIOMotorDatabase, *, manuale: bool = False) -> dict[str, Any]:
    """Esegue il job avvisi scadenze. Salva traccia su ``db.notifiche_scadenze``."""
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    if not manuale and not az.get("notifica_scadenze_attiva", True):
        logger.info("Avvisi scadenze: disattivato in configurazione.")
        return {"ok": False, "skipped": True, "motivo": "Disattivato in Librerie/Azienda"}

    giorni = int(az.get("notifica_scadenze_giorni") or 15)
    scadenze = await cerca_scadenze(db, giorni)
    n_pol = len(scadenze["polizze"])
    n_tit = len(scadenze["titoli"])

    to_addr = (
        az.get("notifica_scadenze_email_admin")
        or az.get("email_commercialista")
        or os.environ.get("ADMIN_EMAIL")
    )
    smtp_ok = bool(az.get("smtp_host") and az.get("smtp_user"))

    log_entry: dict[str, Any] = {
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

    if n_pol == 0 and n_tit == 0:
        log_entry["motivo"] = "Nessuna scadenza nel periodo"
        await db.notifiche_scadenze.insert_one(log_entry)
        logger.info("Avvisi scadenze: nessuna scadenza nei prossimi %s giorni.", giorni)
        return {"ok": True, "n_polizze": 0, "n_titoli": 0, "email_inviata": False,
                "motivo": "Nessuna scadenza nel periodo"}

    if not to_addr:
        log_entry["errore"] = "Destinatario non configurato (notifica_scadenze_email_admin / email_commercialista)"
        await db.notifiche_scadenze.insert_one(log_entry)
        return {"ok": False, "errore": log_entry["errore"], "n_polizze": n_pol, "n_titoli": n_tit}

    if not smtp_ok:
        log_entry["errore"] = "SMTP non configurato in Librerie/Azienda"
        await db.notifiche_scadenze.insert_one(log_entry)
        return {"ok": False, "errore": log_entry["errore"], "n_polizze": n_pol, "n_titoli": n_tit,
                "scadenze": scadenze}

    subject, text, html = _render_email_html(scadenze, giorni)
    try:
        _invia_email(az, to_addr, subject, text, html)
        log_entry["email_inviata"] = True
        await db.notifiche_scadenze.insert_one(log_entry)
        logger.info("Avvisi scadenze inviati a %s: %d polizze, %d titoli", to_addr, n_pol, n_tit)
        return {"ok": True, "n_polizze": n_pol, "n_titoli": n_tit,
                "email_inviata": True, "destinatario": to_addr}
    except Exception as e:
        log_entry["errore"] = str(e)
        await db.notifiche_scadenze.insert_one(log_entry)
        logger.exception("Errore invio avvisi scadenze")
        return {"ok": False, "errore": str(e), "n_polizze": n_pol, "n_titoli": n_tit}


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
