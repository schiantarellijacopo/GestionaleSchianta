"""Esecutore degli AVVISI PROGRAMMATI (alert_rules tipo=schedule/soglia).

Il dispatcher eventi (`alert_dispatcher.dispatch_evento`) gestisce solo le regole
`tipo="evento"`. Le regole ricorrenti (compleanno, polizza scaduta da N giorni,
titolo scaduto oltre soglia, ecc.) non venivano MAI eseguite perché mancava un
loop giornaliero. Questo modulo colma la lacuna:

- `start_alert_scheduler(raw_db)` avvia un tick ogni 10 minuti.
- Ad ogni tick, per OGNI tenant attivo, legge l'orario configurato in
  `azienda_config` (`alert_scheduler_hour`/`alert_scheduler_minute`, default 08:00)
  e, se è l'ora e non è già stato eseguito oggi, lancia le regole schedule/soglia.
- Multi-tenant: imposta il ContextVar utente sul tenant così che `db` filtri
  correttamente. Ogni regola risolve le entità (polizze/titoli/anagrafiche) e
  invia via `dispatch_rule` sul CANALE scelto dal cliente in anagrafica.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from database import db, set_current_user, reset_current_user
from tenant import TENANT_PRINCIPALE_ID
from alert_dispatcher import dispatch_rule
from db_models import _now_iso

logger = logging.getLogger(__name__)

_scheduler = None
_TICK_MINUTES = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _today() -> date:
    return date.today()


def _fmt_date(s: Optional[str]) -> str:
    if not s:
        return "—"
    try:
        return date.fromisoformat(str(s)[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(s)


def _fmt_eur(v) -> str:
    try:
        return f"{float(v or 0):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "0,00 €"


async def _load_anagrafica(aid: Optional[str]) -> dict:
    if not aid:
        return {}
    return await db.anagrafiche.find_one({"id": aid}, {"_id": 0}) or {}


async def _load_compagnia_nome(cid: Optional[str]) -> str:
    if not cid:
        return "-"
    c = await db.compagnie.find_one({"id": cid}, {"_id": 0, "ragione_sociale": 1, "nome": 1})
    return (c or {}).get("ragione_sociale") or (c or {}).get("nome") or "-" if c else "-"


def _payload_polizza(p: dict, ana: dict, compagnia_nome: str) -> dict:
    return {
        "entita_tipo": "polizza",
        "entita_id": p.get("id"),
        "anagrafica_id": p.get("contraente_id"),
        "contraente_id": p.get("contraente_id"),
        "polizza_id": p.get("id"),
        "collaboratore_id": p.get("collaboratore_id"),
        "numero_polizza": p.get("numero_polizza") or "-",
        "ramo": p.get("ramo") or "-",
        "targa": p.get("targa") or "",
        "scadenza": _fmt_date(p.get("scadenza")),
        "premio_totale": _fmt_eur(p.get("premio_lordo")),
        "importo": _fmt_eur(p.get("premio_lordo")),
        "compagnia": compagnia_nome,
        "link": f"/polizze/{p.get('id')}",
    }


# ---------------------------------------------------------------------------
# Resolvers: schedule_kind → lista di payload da notificare
# ---------------------------------------------------------------------------
async def _res_polizze_scadenza_offset(offset_days: int) -> list[dict]:
    """Polizze la cui scadenza cade ESATTAMENTE a `oggi - offset_days`
    (offset 0 = scade oggi, 5 = scaduta da 5 giorni, ...)."""
    target = (_today() - timedelta(days=offset_days)).isoformat()
    out: list[dict] = []
    cur = db.polizze.find(
        {"scadenza": target, "stato": {"$in": ["attiva", "scaduta", "in_attesa"]}},
        {"_id": 0},
    )
    async for p in cur:
        ana = await _load_anagrafica(p.get("contraente_id"))
        cn = await _load_compagnia_nome(p.get("compagnia_id"))
        out.append(_payload_polizza(p, ana, cn))
    return out


async def _res_polizze_in_scadenza(giorni: int) -> list[dict]:
    """Polizze in scadenza esattamente tra `giorni` giorni (promemoria rinnovo)."""
    target = (_today() + timedelta(days=max(0, giorni))).isoformat()
    out: list[dict] = []
    cur = db.polizze.find(
        {"scadenza": target, "stato": {"$in": ["attiva", "in_attesa"]}},
        {"_id": 0},
    )
    async for p in cur:
        ana = await _load_anagrafica(p.get("contraente_id"))
        cn = await _load_compagnia_nome(p.get("compagnia_id"))
        out.append(_payload_polizza(p, ana, cn))
    return out


async def _res_compleanno() -> list[dict]:
    """Anagrafiche il cui compleanno cade oggi (MM-DD)."""
    mmdd = _today().strftime("-%m-%d")
    out: list[dict] = []
    cur = db.anagrafiche.find(
        {"data_nascita": {"$regex": f"{mmdd}$"}},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "data_nascita": 1},
    )
    async for a in cur:
        out.append({
            "entita_tipo": "anagrafica",
            "entita_id": a.get("id"),
            "anagrafica_id": a.get("id"),
            "contraente_id": a.get("id"),
            "cliente_nome": a.get("ragione_sociale") or "",
            "link": f"/anagrafiche/{a.get('id')}",
        })
    return out


async def _res_titolo_scaduto_oltre(giorni: int) -> list[dict]:
    """Titoli non incassati scaduti ESATTAMENTE da `giorni` giorni."""
    target = (_today() - timedelta(days=max(0, giorni))).isoformat()
    out: list[dict] = []
    cur = db.titoli.find(
        {"scadenza": target, "stato": {"$in": ["da_incassare", "insoluto"]}},
        {"_id": 0},
    )
    async for t in cur:
        pol = await db.polizze.find_one({"id": t.get("polizza_id")}, {"_id": 0}) if t.get("polizza_id") else None
        pol = pol or {}
        ana = await _load_anagrafica(pol.get("contraente_id"))
        cn = await _load_compagnia_nome(pol.get("compagnia_id"))
        out.append({
            "entita_tipo": "titolo",
            "entita_id": t.get("id"),
            "anagrafica_id": pol.get("contraente_id"),
            "contraente_id": pol.get("contraente_id"),
            "polizza_id": t.get("polizza_id"),
            "collaboratore_id": t.get("collaboratore_id") or pol.get("collaboratore_id"),
            "numero_polizza": pol.get("numero_polizza") or "-",
            "ramo": pol.get("ramo") or "-",
            "scadenza": _fmt_date(t.get("scadenza")),
            "importo": _fmt_eur(t.get("importo_lordo")),
            "totale": _fmt_eur(t.get("importo_lordo")),
            "compagnia": cn,
            "link": f"/polizze/{t.get('polizza_id')}",
        })
    return out


_OFFSET_KINDS = {
    "polizza_scaduta_giorno": 0,
    "polizza_scaduta_5g": 5,
    "polizza_scaduta_10g": 10,
    "polizza_scaduta_14g": 14,
    "polizza_scaduta_15g": 15,
}


async def resolve_payloads(rule: dict) -> list[dict]:
    """Ritorna la lista di payload (uno per destinatario/entità) per la regola."""
    kind = rule.get("schedule_kind")
    if kind in _OFFSET_KINDS:
        return await _res_polizze_scadenza_offset(_OFFSET_KINDS[kind])
    if kind == "polizza_in_scadenza":
        return await _res_polizze_in_scadenza(int(rule.get("soglia_giorni") or 15))
    if kind == "compleanno_cliente":
        return await _res_compleanno()
    if kind == "titolo_scaduto_oltre":
        return await _res_titolo_scaduto_oltre(int(rule.get("soglia_giorni") or 30))
    # schedule_kind non gestito da questo esecutore (es. digest settimanali,
    # documento_veicolo_mancante gestito da sollecito_veicoli, documento_id_scaduto)
    return []


# ---------------------------------------------------------------------------
# Esecuzione per tenant
# ---------------------------------------------------------------------------
async def _esegui_rule(rule: dict) -> dict:
    payloads = await resolve_payloads(rule)
    agg = {"rule_id": rule.get("id"), "nome": rule.get("nome"),
           "schedule_kind": rule.get("schedule_kind"),
           "entita": len(payloads), "sent": 0, "errors": 0, "skipped": 0}
    for payload in payloads:
        try:
            s = await dispatch_rule(rule, payload)
            agg["sent"] += s.get("sent", 0)
            agg["errors"] += s.get("errors", 0)
            agg["skipped"] += s.get("skipped", 0)
        except Exception as e:  # noqa: BLE001
            agg["errors"] += 1
            logger.exception("Errore dispatch schedule rule %s: %s", rule.get("id"), e)
    await db.alert_rules.update_one({"id": rule["id"]}, {"$set": {"last_run_at": _now_iso()}})
    return agg


async def esegui_schedule_tenant(tenant_id: str, *, only_rule_id: Optional[str] = None) -> dict:
    """Esegue TUTTE le regole schedule/soglia attive di un tenant (o una sola)."""
    user = {"id": "scheduler", "role": "admin",
            "agenzia_tenant_id": tenant_id, "is_super_admin": False}
    token = set_current_user(user)
    try:
        flt: dict = {"attivo": True, "tipo": {"$in": ["schedule", "soglia"]}}
        if only_rule_id:
            flt = {"id": only_rule_id}
        rules = await db.alert_rules.find(flt, {"_id": 0}).to_list(500)
        results = [await _esegui_rule(r) for r in rules]
        return {"tenant_id": tenant_id, "regole": len(results),
                "sent": sum(r["sent"] for r in results),
                "errors": sum(r["errors"] for r in results),
                "skipped": sum(r["skipped"] for r in results),
                "dettaglio": results}
    finally:
        reset_current_user(token)


# ---------------------------------------------------------------------------
# Scheduler tick (multi-tenant, orario configurabile per agenzia)
# ---------------------------------------------------------------------------
async def _tenant_alert_config(raw_db: AsyncIOMotorDatabase, tenant_id: str) -> dict:
    cfg = await raw_db.azienda_config.find_one({"agenzia_tenant_id": tenant_id}, {"_id": 0})
    if not cfg and tenant_id == TENANT_PRINCIPALE_ID:
        cfg = await raw_db.azienda_config.find_one({}, {"_id": 0})
    return cfg or {}


async def _tick(raw_db: AsyncIOMotorDatabase) -> None:
    try:
        from tzlocal import get_localzone
        tz = get_localzone()
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)
    now_min = now.hour * 60 + now.minute
    today = now.date().isoformat()

    async for t in raw_db.tenants.find({"attivo": True}, {"_id": 0, "id": 1}):
        tid = t.get("id")
        if not tid:
            continue
        try:
            cfg = await _tenant_alert_config(raw_db, tid)
            if not cfg.get("alert_scheduler_attivo", True):
                continue
            target = int(cfg.get("alert_scheduler_hour", 8)) * 60 + int(cfg.get("alert_scheduler_minute", 0))
            if not (target <= now_min < target + _TICK_MINUTES):
                continue
            state = await raw_db.alert_scheduler_state.find_one({"tenant_id": tid}, {"_id": 0})
            if state and state.get("last_run_date") == today:
                continue
            await raw_db.alert_scheduler_state.update_one(
                {"tenant_id": tid},
                {"$set": {"tenant_id": tid, "last_run_date": today, "last_run_at": now.isoformat()}},
                upsert=True,
            )
            res = await esegui_schedule_tenant(tid)
            logger.info("Avvisi programmati tenant %s: %s inviati, %s errori",
                        tid, res["sent"], res["errors"])
        except Exception:  # noqa: BLE001
            logger.exception("Errore tick avvisi programmati tenant %s", tid)


async def _daily_auto_diario(raw_db: AsyncIOMotorDatabase) -> None:
    """Salva automaticamente le conversazioni WhatsApp nel diario cliente,
    una volta al giorno, per ogni tenant (upsert → nessun doppione)."""
    from routes.whatsapp_evo import run_auto_diario_tenant
    async for t in raw_db.tenants.find({"attivo": True}, {"_id": 0, "id": 1}):
        tid = t.get("id")
        if not tid:
            continue
        user = {"id": "scheduler", "role": "admin", "agenzia_tenant_id": tid, "is_super_admin": False}
        token = set_current_user(user)
        try:
            res = await run_auto_diario_tenant()
            if res.get("salvati"):
                logger.info("Auto-diario WhatsApp tenant %s: %s conversazioni salvate", tid, res["salvati"])
        except Exception:  # noqa: BLE001
            logger.exception("Errore auto-diario WhatsApp tenant %s", tid)
        finally:
            reset_current_user(token)


async def _daily_upload_reminders(raw_db: AsyncIOMotorDatabase) -> None:
    """Ri-sollecita i link documento non ancora caricati (ogni `reminder_giorni`),
    inviando al cliente sul canale scelto in anagrafica. Max 3 solleciti."""
    from datetime import datetime as _dt
    from alert_dispatcher import CHANNEL_ADAPTERS as CHANNEL_SENDERS
    now_iso = _now_iso()
    async for t in raw_db.tenants.find({"attivo": True}, {"_id": 0, "id": 1}):
        tid = t.get("id")
        if not tid:
            continue
        links = await raw_db.upload_links.find({
            "agenzia_tenant_id": tid, "used": False,
            "reminder_giorni": {"$gt": 0},
        }, {"_id": 0}).to_list(1000)
        if not links:
            continue
        user = {"id": "scheduler", "role": "admin", "agenzia_tenant_id": tid, "is_super_admin": False}
        token = set_current_user(user)
        try:
            for link in links:
                try:
                    if link.get("expires_at") and link["expires_at"] < now_iso:
                        continue
                    if int(link.get("reminder_count") or 0) >= 3:
                        continue
                    riferimento = link.get("last_reminder_at") or link.get("created_at")
                    if riferimento:
                        giorni = (_dt.fromisoformat(now_iso[:19]) - _dt.fromisoformat(str(riferimento)[:19])).days
                        if giorni < int(link.get("reminder_giorni") or 3):
                            continue
                    ana = await db.anagrafiche.find_one({"id": link["anagrafica_id"]}, {"_id": 0})
                    if not ana:
                        continue
                    base = (os.environ.get("BACKEND_PUBLIC_URL") or "").rstrip("/")
                    url = f"{base}/carica/{link['token']}" if base else f"/carica/{link['token']}"
                    corpo = (f"Gentile {ana.get('ragione_sociale') or ''},\n\n"
                             f"non abbiamo ancora ricevuto: {link.get('descrizione')}.\n"
                             f"Può caricarlo comodamente da qui:\n{url}\n\nGrazie.")
                    dest = {
                        "tipo": "cliente", "anagrafica_id": ana["id"],
                        "email": ana.get("email") if ana.get("canale_email") else None,
                        "cellulare": ana.get("cellulare") or ana.get("telefono"),
                        "whatsapp": ana.get("whatsapp") or ana.get("cellulare"),
                    }
                    ctx = {"oggetto": f"Promemoria documento — {link.get('descrizione')}", "corpo": corpo}
                    canali = []
                    if ana.get("canale_email") and ana.get("email"):
                        canali.append("email")
                    if ana.get("canale_whatsapp") and (ana.get("whatsapp") or ana.get("cellulare")):
                        canali.append("whatsapp")
                    if ana.get("canale_sms") and ana.get("cellulare"):
                        canali.append("sms")
                    if not canali and ana.get("email"):
                        canali = ["email"]
                    inviato = False
                    for c in canali:
                        sender = CHANNEL_SENDERS.get(c)
                        if not sender:
                            continue
                        res = await sender({"nome": "Promemoria documento"}, dest, ctx)
                        if res.get("status") == "ok":
                            inviato = True
                    await raw_db.upload_links.update_one({"id": link["id"]}, {"$set": {
                        "last_reminder_at": now_iso,
                        "reminder_count": int(link.get("reminder_count") or 0) + (1 if inviato else 0),
                    }})
                except Exception:  # noqa: BLE001
                    logger.exception("Errore promemoria upload link %s", link.get("id"))
        finally:
            reset_current_user(token)


def start_alert_scheduler(raw_db: AsyncIOMotorDatabase) -> None:
    """Avvia il tick ricorrente degli avvisi programmati (ogni 10 minuti)."""
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    try:
        from tzlocal import get_localzone
        tz = get_localzone()
    except Exception:
        tz = timezone.utc

    sched = AsyncIOScheduler(timezone=tz)

    async def _job() -> None:
        await _tick(raw_db)

    async def _diario_job() -> None:
        await _daily_auto_diario(raw_db)

    async def _reminder_job() -> None:
        await _daily_upload_reminders(raw_db)

    sched.add_job(_job, IntervalTrigger(minutes=_TICK_MINUTES),
                  id="avvisi_programmati_tick", replace_existing=True,
                  misfire_grace_time=600)
    sched.add_job(_diario_job, CronTrigger(hour=6, minute=30),
                  id="auto_diario_whatsapp", replace_existing=True,
                  misfire_grace_time=3600)
    sched.add_job(_reminder_job, CronTrigger(hour=7, minute=0),
                  id="promemoria_upload_documenti", replace_existing=True,
                  misfire_grace_time=3600)
    sched.start()
    _scheduler = sched
    logger.info("Scheduler avvisi programmati avviato (tick ogni %d min, tz=%s) + auto-diario 06:30", _TICK_MINUTES, tz)


def stop_alert_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        finally:
            _scheduler = None
