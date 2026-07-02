"""Alert dispatcher — invia notifiche multi-canale (inapp/email/sms/whatsapp).

Canali:
- inapp:    sempre attivo, scrive Notification per ogni destinatario.
- email:    via SMTP. Config: SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/SMTP_FROM.
            Pensato per Google Workspace (smtp.gmail.com:587, app password).
- sms:      PREDISPOSTO. Adapter Twilio (richiede TWILIO_ACCOUNT_SID +
            TWILIO_AUTH_TOKEN + TWILIO_SMS_FROM). Se mancano → status=skipped.
- whatsapp: PREDISPOSTO. Adapter Twilio WhatsApp (TWILIO_WA_FROM con prefisso
            "whatsapp:+...") oppure Meta Cloud API (META_WA_TOKEN +
            META_WA_PHONE_ID). Se mancano → status=skipped.

Tutti i tentativi vengono loggati in AlertEvent (storico).
"""
from __future__ import annotations
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Awaitable, Callable

from database import db
from alert_models import AlertEvent, Notification
from db_models import _now_iso

logger = logging.getLogger(__name__)


# ============================================================
# TEMPLATE — placeholder substitution
# ============================================================
def render_template(tpl: str, context: dict) -> str:
    """Sostituisce {placeholder} con i valori del context. Sicuro (no eval)."""
    if not tpl:
        return ""
    out = tpl
    for k, v in (context or {}).items():
        out = out.replace("{" + str(k) + "}", str(v) if v is not None else "")
    return out


# ============================================================
# RESOLVE DESTINATARI — refactored (complessità 26 → ~5 per helper)
# ============================================================
def _user_to_destinatario(u: dict, tipo: str) -> dict:
    """Mappa un documento user nel formato destinatario standard."""
    return {
        "tipo": tipo, "user_id": u["id"],
        "label": u.get("name"), "email": u.get("email"),
        "cellulare": u.get("cellulare"), "whatsapp": u.get("cellulare"),
    }


async def _dest_cliente(payload: dict) -> list[dict]:
    anag_id = payload.get("anagrafica_id") or payload.get("contraente_id")
    if not anag_id:
        return []
    ana = await db.anagrafiche.find_one({"id": anag_id}, {"_id": 0})
    if not ana:
        return []
    return [{
        "tipo": "cliente", "anagrafica_id": anag_id,
        "label": ana.get("ragione_sociale"),
        "email": ana.get("email"),
        "cellulare": ana.get("cellulare") or ana.get("telefono"),
        "whatsapp": ana.get("whatsapp") or ana.get("cellulare"),
    }]


async def _dest_collaboratore_da_payload(payload: dict) -> list[dict]:
    coll_id = payload.get("collaboratore_id")
    if not coll_id:
        pol_id = payload.get("polizza_id")
        if pol_id:
            pol = await db.polizze.find_one({"id": pol_id}, {"_id": 0, "collaboratore_id": 1})
            coll_id = pol.get("collaboratore_id") if pol else None
    if not coll_id:
        return []
    u = await db.users.find_one({"id": coll_id}, {"_id": 0})
    return [_user_to_destinatario(u, "collaboratore")] if u else []


async def _dest_users_by_query(query: dict, tipo: str) -> list[dict]:
    out: list[dict] = []
    async for u in db.users.find(query, {"_id": 0}):
        out.append(_user_to_destinatario(u, tipo))
    return out


async def _dest_utenti_specifici(user_ids: list[str]) -> list[dict]:
    out: list[dict] = []
    for uid in user_ids:
        u = await db.users.find_one({"id": uid}, {"_id": 0})
        if u:
            out.append(_user_to_destinatario(u, "utente_specifico"))
    return out


def _dedupe_destinatari(items: list[dict]) -> list[dict]:
    seen: set = set()
    unique: list[dict] = []
    for d in items:
        key = (
            d.get("tipo"),
            d.get("user_id") or d.get("anagrafica_id") or d.get("email") or d.get("cellulare"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)
    return unique


async def _dest_altri_collaboratori(rule: dict) -> list[dict]:
    """Risolve il destinatario "altri_collaboratori".

    Legge la lista ``altri_collaboratori_user_ids`` dalla regola stessa:
    sono i collaboratori esplicitamente scelti per ricevere questa notifica
    (es. il responsabile sinistri, il back-office, ecc.).
    """
    ids = rule.get("altri_collaboratori_user_ids") or []
    out: list[dict] = []
    for uid in ids:
        u = await db.users.find_one({"id": uid}, {"_id": 0})
        if u:
            out.append(_user_to_destinatario(u, "altri_collaboratori"))
    return out


async def resolve_destinatari(rule: dict, payload: dict) -> list[dict]:
    """Risolve i destinatari della regola in base al payload dell'evento.

    Output: lista di {tipo, user_id?, anagrafica_id?, label, email?, cellulare?, whatsapp?}
    """
    out: list[dict] = []
    for dt in rule.get("destinatari") or []:
        if dt == "cliente":
            out.extend(await _dest_cliente(payload))
        elif dt == "collaboratore":
            out.extend(await _dest_collaboratore_da_payload(payload))
        elif dt in ("altri_collaboratori", "collaboratore_sinistri"):
            # "collaboratore_sinistri" mantenuto per backward-compat (legacy data)
            out.extend(await _dest_altri_collaboratori(rule))
        elif dt == "admin":
            out.extend(await _dest_users_by_query({"role": "admin"}, "admin"))
        elif dt == "utente_specifico":
            out.extend(await _dest_utenti_specifici(rule.get("destinatari_user_ids") or []))
    return _dedupe_destinatari(out)


# ============================================================
# CHANNEL ADAPTERS
# ============================================================
async def send_inapp(rule: dict, dest: dict, ctx: dict) -> dict:
    """Crea un record Notification per l'utente.

    In più, copia automaticamente la notifica in:
      - ``db.diario_note`` se il destinatario è un collaboratore/admin
        (visibile nel "Diario Collaboratore"),
      - ``db.diario_cliente`` se il destinatario è il cliente
        (visibile nello storico cliente).
    """
    user_id = dest.get("user_id")
    anag_id = dest.get("anagrafica_id")
    titolo = ctx.get("oggetto") or rule.get("nome") or "Notifica"
    messaggio = ctx.get("corpo") or ""

    if user_id:
        n = Notification(
            user_id=user_id,
            titolo=titolo,
            messaggio=messaggio,
            tipo=rule.get("livello") or "info",
            icona=rule.get("icona") or "Bell",
            link=ctx.get("link"),
            rule_id=rule.get("id"),
            entita_tipo=ctx.get("entita_tipo"),
            entita_id=ctx.get("entita_id"),
        )
        await db.notifications.insert_one(n.model_dump())
        # Aggrega nel Diario Collaboratore
        try:
            from db_models import DiarioNota
            diary = DiarioNota(
                user_id=user_id,
                titolo=f"[Alert] {titolo}"[:200],
                contenuto=messaggio[:2000],
                anagrafica_id=ctx.get("anagrafica_id") or ctx.get("contraente_id"),
                polizza_id=ctx.get("polizza_id"),
                tags=["alert", rule.get("evento") or rule.get("schedule_kind") or "alert"],
            ).model_dump()
            await db.diario_note.insert_one(diary)
        except Exception:
            logger.exception("Errore log diario_note da alert in-app")
        return {"status": "ok"}

    if anag_id:
        # cliente: nessun utente CRM → log solo nel diario cliente
        try:
            from shared import log_diario_cliente
            await log_diario_cliente(
                anag_id, "nota",
                f"[Alert in-app] {titolo}"[:200],
                messaggio[:2000],
                autore=None,
            )
            return {"status": "ok"}
        except Exception:
            logger.exception("Errore log diario_cliente da alert in-app")
            return {"status": "error", "error": "diario_cliente log fallito"}

    return {"status": "skipped", "error": "in-app richiede user_id o anagrafica_id"}


async def _load_provider(tipo: str) -> dict:
    """Carica la config provider dal DB (con fallback su env per email)."""
    cfg = await db.alert_providers.find_one({"tipo": tipo, "enabled": True}, {"_id": 0})
    if cfg:
        return cfg
    # Fallback su variabili d'ambiente (retrocompatibilità)
    if tipo == "email":
        host = os.environ.get("SMTP_HOST")
        if host:
            return {
                "tipo": "email", "provider": "custom", "enabled": True,
                "smtp_host": host,
                "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
                "smtp_starttls": True,
                "smtp_user": os.environ.get("SMTP_USER"),
                "smtp_password": os.environ.get("SMTP_PASSWORD"),
                "smtp_from": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER"),
            }
    elif tipo in ("sms", "whatsapp"):
        sid = os.environ.get("TWILIO_ACCOUNT_SID")
        if sid:
            from_key = "TWILIO_SMS_FROM" if tipo == "sms" else "TWILIO_WA_FROM"
            return {
                "tipo": tipo, "provider": "twilio", "enabled": True,
                "twilio_sid": sid,
                "twilio_token": os.environ.get("TWILIO_AUTH_TOKEN"),
                "twilio_from": os.environ.get(from_key),
            }
    return {}


async def send_email(rule: dict, dest: dict, ctx: dict) -> dict:
    """Invia email via SMTP. Provider config dal DB (preferenza) o env (fallback)."""
    to_email = dest.get("email")
    if not to_email:
        return {"status": "skipped", "error": "email destinatario assente"}
    cfg = await _load_provider("email")
    host = cfg.get("smtp_host")
    user = cfg.get("smtp_user")
    pwd = cfg.get("smtp_password")
    sender = cfg.get("smtp_from") or user
    if not (host and user and pwd and sender):
        return {"status": "skipped", "error": "Provider Email non configurato — vai in /alert → tab Configurazione"}
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = ctx.get("oggetto") or rule.get("nome") or "Notifica"
        from_name = cfg.get("smtp_from_name")
        msg["From"] = f"{from_name} <{sender}>" if from_name else sender
        msg["To"] = to_email
        body = ctx.get("corpo") or ""
        msg.attach(MIMEText(body, "plain", "utf-8"))
        html = "<html><body><p>" + body.replace("\n", "<br/>") + "</p></body></html>"
        msg.attach(MIMEText(html, "html", "utf-8"))
        port = int(cfg.get("smtp_port") or 587)
        with smtplib.SMTP(host, port, timeout=20) as srv:
            if cfg.get("smtp_starttls", True):
                srv.starttls()
            srv.login(user, pwd)
            srv.sendmail(sender, [to_email], msg.as_string())
        return {"status": "ok"}
    except Exception as e:
        return {"status": "errore", "error": str(e)}


async def send_sms(rule: dict, dest: dict, ctx: dict) -> dict:
    """SMS via Twilio. Provider config dal DB o env."""
    to_num = dest.get("cellulare")
    if not to_num:
        return {"status": "skipped", "error": "cellulare destinatario assente"}
    cfg = await _load_provider("sms")
    sid = cfg.get("twilio_sid")
    tok = cfg.get("twilio_token")
    from_num = cfg.get("twilio_from")
    if not (sid and tok and from_num):
        return {"status": "skipped", "error": "Provider SMS non configurato — vai in /alert → tab Configurazione"}
    try:
        from twilio.rest import Client  # type: ignore
        client = Client(sid, tok)
        msg = client.messages.create(from_=from_num, to=to_num, body=(ctx.get("corpo") or "")[:480])
        return {"status": "ok", "provider_id": msg.sid}
    except Exception as e:
        return {"status": "errore", "error": str(e)}


async def send_whatsapp(rule: dict, dest: dict, ctx: dict) -> dict:
    """WhatsApp via Evolution API (multi-tenant).

    Sceglie l'istanza in base a:
    - `rule.whatsapp_instance` (nome fisso), oppure
    - istanza dell'agenzia del `collaboratore` proprietario, oppure
    - prima istanza in stato `open` (fallback).
    """
    to_num = dest.get("whatsapp") or dest.get("cellulare")
    if not to_num:
        return {"status": "skipped", "error": "WhatsApp destinatario assente"}

    # normalizza numero (rimuovi +, spazi, trattini)
    to_clean = "".join(c for c in str(to_num) if c.isdigit())
    if not to_clean:
        return {"status": "skipped", "error": "Numero non valido"}

    # sceglie l'istanza
    instance_name = rule.get("whatsapp_instance")
    if not instance_name:
        # cerca la prima istanza connessa
        inst = await db.whatsapp_instances.find_one(
            {"state": {"$in": ["open", "connected"]}}, {"_id": 0, "instance_name": 1, "token": 1},
        )
        if not inst:
            # fallback: prima istanza esistente qualunque stato
            inst = await db.whatsapp_instances.find_one({}, {"_id": 0, "instance_name": 1, "token": 1})
        if not inst:
            return {"status": "skipped", "error": "Nessuna istanza WhatsApp configurata"}
        instance_name = inst["instance_name"]
    else:
        inst = await db.whatsapp_instances.find_one(
            {"instance_name": instance_name}, {"_id": 0, "token": 1},
        )
        if not inst:
            return {"status": "skipped", "error": f"Istanza '{instance_name}' non trovata"}

    url_base = (os.environ.get("WHATSAPP_API_URL") or "").rstrip("/")
    api_key = inst.get("token") or os.environ.get("WHATSAPP_API_KEY") or ""
    if not url_base or not api_key:
        return {"status": "skipped", "error": "Evolution API non configurata"}

    try:
        import httpx  # type: ignore
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{url_base}/message/sendText/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": to_clean, "text": (ctx.get("corpo") or "")[:2000]},
            )
        if r.status_code >= 400:
            return {"status": "errore", "error": f"Evolution API {r.status_code}: {r.text[:200]}"}
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        # trace copia messaggio in inbox
        try:
            await db.whatsapp_messages.insert_one({
                "id": str(__import__('uuid').uuid4()),
                "instance_name": instance_name,
                "direction": "out",
                "number": to_clean,
                "text": (ctx.get("corpo") or "")[:2000],
                "created_at": _now_iso(),
                "rule_id": rule.get("id"),
            })
        except Exception:
            pass
        return {"status": "ok", "provider_id": (data.get("key") or {}).get("id")}
    except Exception as e:
        return {"status": "errore", "error": str(e)}


CHANNEL_ADAPTERS: dict[str, Callable[[dict, dict, dict], Awaitable[dict]]] = {
    "inapp": send_inapp,
    "email": send_email,
    "sms": send_sms,
    "whatsapp": send_whatsapp,
}


# ============================================================
# DISPATCH
# ============================================================
async def dispatch_rule(rule: dict, payload: dict) -> dict:
    """Esegue UNA regola con il payload dato.

    Returns: {sent: N, errors: N, skipped: N, events: [event_id, ...]}
    """
    stats: dict = {"sent": 0, "errors": 0, "skipped": 0, "events": []}
    if not rule.get("attivo"):
        return stats
    destinatari = await resolve_destinatari(rule, payload)
    if not destinatari:
        return stats

    # context per template
    base_ctx = dict(payload)
    canali = rule.get("canali") or []
    for dest in destinatari:
        ctx_dest = dict(base_ctx)
        ctx_dest["nome"] = dest.get("label") or ""
        oggetto = render_template(rule.get("template_oggetto") or rule.get("nome") or "", ctx_dest)
        corpo = render_template(rule.get("template_corpo") or "", ctx_dest)
        ctx_dest["oggetto"] = oggetto
        ctx_dest["corpo"] = corpo
        ctx_dest["link"] = payload.get("link")
        ctx_dest["entita_tipo"] = payload.get("entita_tipo")
        ctx_dest["entita_id"] = payload.get("entita_id")

        for canale in canali:
            adapter = CHANNEL_ADAPTERS.get(canale)
            indirizzo = {
                "inapp": dest.get("user_id"),
                "email": dest.get("email"),
                "sms": dest.get("cellulare"),
                "whatsapp": dest.get("whatsapp") or dest.get("cellulare"),
            }.get(canale)
            ev = AlertEvent(
                rule_id=rule["id"], rule_nome=rule.get("nome") or "",
                canale=canale,
                destinatario_tipo=dest.get("tipo") or "",
                destinatario_user_id=dest.get("user_id"),
                destinatario_anagrafica_id=dest.get("anagrafica_id"),
                destinatario_label=dest.get("label"),
                destinatario_indirizzo=indirizzo,
                oggetto=oggetto, corpo=corpo,
                entita_tipo=payload.get("entita_tipo"),
                entita_id=payload.get("entita_id"),
                payload=payload,
            )
            if not adapter:
                ev.status = "skipped"
                ev.error_message = f"canale '{canale}' non riconosciuto"
            else:
                try:
                    res = await adapter(rule, dest, ctx_dest)
                    ev.status = res.get("status") or "errore"
                    ev.error_message = res.get("error")
                    if ev.status == "ok":
                        ev.sent_at = _now_iso()
                except Exception as e:
                    ev.status = "errore"
                    ev.error_message = str(e)
            await db.alert_events.insert_one(ev.model_dump())
            stats["events"].append(ev.id)
            if ev.status == "ok":
                stats["sent"] += 1
            elif ev.status == "skipped":
                stats["skipped"] += 1
            else:
                stats["errors"] += 1
    # aggiorna contatori rule
    await db.alert_rules.update_one({"id": rule["id"]}, {"$set": {
        "last_event_at": _now_iso(), "updated_at": _now_iso(),
    }, "$inc": {"invii_totali": stats["sent"], "errori_totali": stats["errors"]}})
    return stats


async def dispatch_evento(evento: str, payload: dict) -> dict:
    """Trova tutte le regole attive per `evento` e le esegue.

    `evento`: es. "sinistro.aperto", "polizza.emessa", ...
    `payload`: dict con almeno {entita_tipo, entita_id, ...campi specifici}
    """
    agg: dict = {"matched": 0, "sent": 0, "errors": 0, "skipped": 0}
    async for rule in db.alert_rules.find({"attivo": True, "tipo": "evento", "evento": evento}, {"_id": 0}):
        agg["matched"] += 1
        s = await dispatch_rule(rule, payload)
        agg["sent"] += s["sent"]
        agg["errors"] += s["errors"]
        agg["skipped"] += s["skipped"]
    return agg


# ============================================================
# SAFE WRAPPER — never crash caller
# ============================================================
async def safe_dispatch(evento: str, payload: dict) -> None:
    """Wrapper non-throw da chiamare dai service backend.

    Esempio:
        from alert_dispatcher import safe_dispatch
        await safe_dispatch("sinistro.aperto", {
            "entita_tipo": "sinistro", "entita_id": s.id,
            "anagrafica_id": s.assicurato_id, "polizza_id": s.polizza_id,
            "numero_sinistro": s.numero_sinistro, ...
        })
    """
    try:
        await dispatch_evento(evento, payload)
    except Exception as e:
        logger.error("Alert dispatch failed for evento=%s: %s", evento, e)
