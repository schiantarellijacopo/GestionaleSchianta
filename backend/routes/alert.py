"""Alert + Notifications routes.

Endpoint:
  /api/alert-rules      → CRUD regole alert
  /api/alert-rules/{id}/toggle  → attiva/disattiva
  /api/alert-rules/{id}/test    → invio di test (a chi chiama)
  /api/alert-events     → storico invii
  /api/notifications/me → notifiche in-app dell'utente
  /api/notifications/me/unread-count
  /api/notifications/me/mark-read
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from auth import current_user, require_user
from alert_models import (
    AlertRule, AlertEvent, AlertProviderConfig,
    ALERT_EVENT_TYPES, ALERT_SCHEDULE_TYPES, CANALI, DESTINATARI,
    EMAIL_PRESETS, WHATSAPP_PRESETS,
)
from alert_dispatcher import dispatch_rule
from db_models import _now_iso

router = APIRouter()


# ============================================================
# CATALOGO META (per UI)
# ============================================================
@router.get("/alert-meta")
async def alert_meta(user: dict = Depends(current_user)) -> dict:
    """Restituisce eventi, schedule type, canali, destinatari disponibili."""
    return {
        "eventi": ALERT_EVENT_TYPES,
        "schedule_kinds": ALERT_SCHEDULE_TYPES,
        "canali": CANALI,
        "destinatari": DESTINATARI,
    }


# ============================================================
# CRUD REGOLE
# ============================================================
@router.get("/alert-rules")
async def list_alert_rules(
    tipo: Optional[str] = None,
    attivo: Optional[bool] = None,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> list[dict]:
    flt: dict = {}
    if tipo:
        flt["tipo"] = tipo
    if attivo is not None:
        flt["attivo"] = attivo
    items = await db.alert_rules.find(flt, {"_id": 0}).sort([("is_preset", -1), ("nome", 1)]).to_list(500)
    return items


@router.get("/alert-rules/{rid}")
async def get_alert_rule(rid: str, user: dict = Depends(current_user)) -> dict:
    r = await db.alert_rules.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Regola non trovata")
    return r


class AlertRulePatch(BaseModel):
    nome: Optional[str] = None
    descrizione: Optional[str] = None
    canali: Optional[list[str]] = None
    destinatari: Optional[list[str]] = None
    destinatari_user_ids: Optional[list[str]] = None
    template_oggetto: Optional[str] = None
    template_corpo: Optional[str] = None
    condizioni: Optional[dict] = None
    soglia_giorni: Optional[int] = None
    cron: Optional[str] = None
    attivo: Optional[bool] = None


@router.put("/alert-rules/{rid}")
async def update_alert_rule(
    rid: str, body: AlertRulePatch,
    user: dict = Depends(require_user("admin")),
) -> dict:
    upd = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not upd:
        raise HTTPException(400, "Nessun campo da aggiornare")
    upd["updated_at"] = _now_iso()
    res = await db.alert_rules.update_one({"id": rid}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Regola non trovata")
    return await db.alert_rules.find_one({"id": rid}, {"_id": 0})


@router.post("/alert-rules", status_code=201)
async def create_alert_rule(body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    obj = AlertRule(**body, is_preset=False)
    await db.alert_rules.insert_one(obj.model_dump())
    return obj.model_dump()


@router.delete("/alert-rules/{rid}")
async def delete_alert_rule(rid: str, user: dict = Depends(require_user("admin"))) -> dict:
    res = await db.alert_rules.delete_one({"id": rid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Regola non trovata")
    return {"ok": True}


@router.post("/alert-rules/from-preset/{preset_key}", status_code=201)
async def create_from_preset(preset_key: str, user: dict = Depends(require_user("admin"))) -> dict:
    """Crea una nuova regola partendo da un template del catalogo. Nuova regola
    è completamente modificabile/eliminabile (is_preset=False)."""
    from alert_presets import PRESETS
    tpl = next((p for p in PRESETS if p["preset_key"] == preset_key), None)
    if not tpl:
        raise HTTPException(404, "Template non trovato")
    body = dict(tpl)
    body["is_preset"] = False
    body["preset_key"] = None
    body["attivo"] = False
    obj = AlertRule(**body)
    await db.alert_rules.insert_one(obj.model_dump())
    return obj.model_dump()


@router.get("/alert-presets/catalog")
async def alert_catalog(user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))) -> list[dict]:
    """Catalogo template a cui l'utente può attingere per creare nuove regole."""
    from alert_presets import PRESETS
    return [
        {
            "preset_key": p["preset_key"],
            "nome": p["nome"],
            "descrizione": p["descrizione"],
            "tipo": p["tipo"],
            "evento": p.get("evento"),
            "schedule_kind": p.get("schedule_kind"),
            "canali": p["canali"],
            "destinatari": p["destinatari"],
        }
        for p in PRESETS
    ]


@router.post("/alert-rules/{rid}/toggle")
async def toggle_alert_rule(rid: str, user: dict = Depends(require_user("admin"))) -> dict:
    r = await db.alert_rules.find_one({"id": rid}, {"_id": 0, "attivo": 1})
    if not r:
        raise HTTPException(404, "Regola non trovata")
    new_val = not bool(r.get("attivo"))
    await db.alert_rules.update_one({"id": rid}, {"$set": {"attivo": new_val, "updated_at": _now_iso()}})
    return {"id": rid, "attivo": new_val}


@router.post("/alert-rules/{rid}/test")
async def test_alert_rule(rid: str, body: dict | None = None, user: dict = Depends(require_user("admin"))) -> dict:
    """Esegue la regola in modalità test. Il payload viene preso da `body`
    oppure ricostruito automaticamente con valori demo. Le notifiche vengono
    inviate a CHI CHIAMA (user)."""
    r = await db.alert_rules.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Regola non trovata")
    payload = dict(body or {})
    # default demo payload
    payload.setdefault("entita_tipo", "test")
    payload.setdefault("entita_id", "test-id")
    payload.setdefault("numero_polizza", "TEST-001")
    payload.setdefault("numero_sinistro", "TEST-S-001")
    payload.setdefault("ramo", "Auto")
    payload.setdefault("premio_totale", "100,00")
    payload.setdefault("scadenza", "2026-12-31")
    payload.setdefault("data_effetto", "2026-01-01")
    payload.setdefault("importo_liquidato", "1.500,00")
    # forza destinatario = utente_specifico (chi chiama)
    rule_test = dict(r)
    rule_test["destinatari"] = ["utente_specifico"]
    rule_test["destinatari_user_ids"] = [user["id"]]
    rule_test["attivo"] = True
    stats = await dispatch_rule(rule_test, payload)
    return {"ok": True, **stats}


# ============================================================
# STORICO EVENTI
# ============================================================
@router.get("/alert-events")
async def list_alert_events(
    rule_id: Optional[str] = None,
    status: Optional[str] = None,
    canale: Optional[str] = None,
    limit: int = 200,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> list[dict]:
    flt: dict = {}
    if rule_id:
        flt["rule_id"] = rule_id
    if status:
        flt["status"] = status
    if canale:
        flt["canale"] = canale
    items = await db.alert_events.find(flt, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


# ============================================================
# NOTIFICHE IN-APP
# ============================================================
@router.get("/notifications/me")
async def my_notifications(
    only_unread: bool = False,
    limit: int = 50,
    user: dict = Depends(current_user),
) -> list[dict]:
    flt: dict = {"user_id": user["id"], "archiviata": False}
    if only_unread:
        flt["letta"] = False
    items = await db.notifications.find(flt, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


@router.get("/notifications/me/unread-count")
async def my_unread_count(user: dict = Depends(current_user)) -> dict:
    n = await db.notifications.count_documents(
        {"user_id": user["id"], "letta": False, "archiviata": False},
    )
    return {"count": n}


@router.post("/notifications/me/mark-read")
async def mark_read(body: dict | None = None, user: dict = Depends(current_user)) -> dict:
    """Mark as read. body = {ids?: [n1, n2]}. Se ids vuoto → segna TUTTE."""
    ids = (body or {}).get("ids")
    flt: dict = {"user_id": user["id"], "letta": False}
    if ids:
        flt["id"] = {"$in": ids}
    res = await db.notifications.update_many(flt, {"$set": {"letta": True, "letta_at": _now_iso()}})
    return {"updated": res.modified_count}


@router.delete("/notifications/me/{nid}")
async def archive_notification(nid: str, user: dict = Depends(current_user)) -> dict:
    res = await db.notifications.update_one(
        {"id": nid, "user_id": user["id"]},
        {"$set": {"archiviata": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Notifica non trovata")
    return {"ok": True}


# ============================================================
# CONFIGURAZIONE PROVIDER (email/sms/whatsapp)
# ============================================================
def _mask_secret(s: Optional[str]) -> Optional[str]:
    """Maschera password/token nei response (mostra solo ultimi 4 char)."""
    if not s:
        return None
    if len(s) <= 4:
        return "****"
    return "•" * (len(s) - 4) + s[-4:]


@router.get("/alert-providers/presets")
async def list_presets(user: dict = Depends(current_user)) -> dict:
    """Restituisce i preset disponibili per email e WhatsApp."""
    return {
        "email": EMAIL_PRESETS,
        "whatsapp": WHATSAPP_PRESETS,
    }


@router.get("/alert-providers/{tipo}")
async def get_provider(tipo: str, user: dict = Depends(require_user("admin"))) -> dict:
    """Restituisce la config provider corrente (password mascherate)."""
    if tipo not in ("email", "sms", "whatsapp"):
        raise HTTPException(400, "Tipo non valido")
    cfg = await db.alert_providers.find_one({"tipo": tipo}, {"_id": 0})
    if not cfg:
        # ritorna default vuoto
        return {
            "tipo": tipo, "provider": "gmail" if tipo == "email" else "twilio",
            "enabled": False,
        }
    # mascheriamo i secret
    out = dict(cfg)
    out["smtp_password_set"] = bool(cfg.get("smtp_password"))
    out["twilio_token_set"] = bool(cfg.get("twilio_token"))
    out["meta_token_set"] = bool(cfg.get("meta_token"))
    out["smtp_password"] = _mask_secret(cfg.get("smtp_password"))
    out["twilio_token"] = _mask_secret(cfg.get("twilio_token"))
    out["meta_token"] = _mask_secret(cfg.get("meta_token"))
    return out


@router.put("/alert-providers/{tipo}")
async def save_provider(tipo: str, body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    """Salva/aggiorna la config provider. I campi password vengono mantenuti se
    non inviati (per evitare di sovrascrivere con maschera)."""
    if tipo not in ("email", "sms", "whatsapp"):
        raise HTTPException(400, "Tipo non valido")

    existing = await db.alert_providers.find_one({"tipo": tipo}, {"_id": 0}) or {}
    provider = body.get("provider") or existing.get("provider") or ("gmail" if tipo == "email" else "twilio")

    # Auto-fill host/porta da preset per email
    smtp_host = body.get("smtp_host") or existing.get("smtp_host")
    smtp_port = body.get("smtp_port") or existing.get("smtp_port") or 587
    smtp_starttls = body.get("smtp_starttls")
    if smtp_starttls is None:
        smtp_starttls = existing.get("smtp_starttls", True)
    if tipo == "email" and provider in EMAIL_PRESETS and provider != "custom":
        preset = EMAIL_PRESETS[provider]
        smtp_host = preset["host"]
        smtp_port = preset["port"]
        smtp_starttls = preset["starttls"]

    def _take_secret(field: str) -> Optional[str]:
        """Mantieni vecchio valore se il nuovo è None/vuoto/mascherato (•)."""
        new = body.get(field)
        if new is None or new == "":
            return existing.get(field)
        if isinstance(new, str) and new.startswith("•"):
            return existing.get(field)
        return new

    update = {
        "tipo": tipo,
        "provider": provider,
        "enabled": bool(body.get("enabled", existing.get("enabled", False))),
        "smtp_host": smtp_host,
        "smtp_port": int(smtp_port) if smtp_port else 587,
        "smtp_starttls": bool(smtp_starttls),
        "smtp_user": body.get("smtp_user") or existing.get("smtp_user"),
        "smtp_password": _take_secret("smtp_password"),
        "smtp_from": body.get("smtp_from") or existing.get("smtp_from") or body.get("smtp_user"),
        "smtp_from_name": body.get("smtp_from_name") or existing.get("smtp_from_name"),
        "twilio_sid": body.get("twilio_sid") or existing.get("twilio_sid"),
        "twilio_token": _take_secret("twilio_token"),
        "twilio_from": body.get("twilio_from") or existing.get("twilio_from"),
        "meta_phone_id": body.get("meta_phone_id") or existing.get("meta_phone_id"),
        "meta_token": _take_secret("meta_token"),
        "updated_at": _now_iso(),
    }
    await db.alert_providers.update_one(
        {"tipo": tipo}, {"$set": update}, upsert=True,
    )
    return await get_provider(tipo, user)


@router.post("/alert-providers/{tipo}/test")
async def test_provider(tipo: str, body: dict | None = None, user: dict = Depends(require_user("admin"))) -> dict:
    """Invia messaggio di test all'admin via il canale specificato.

    body: {to_email?, to_phone?, message?} → se mancanti usa l'utente corrente.
    """
    body = body or {}
    if tipo not in ("email", "sms", "whatsapp"):
        raise HTTPException(400, "Tipo non valido")
    cfg = await db.alert_providers.find_one({"tipo": tipo}, {"_id": 0})
    if not cfg or not cfg.get("enabled"):
        raise HTTPException(400, "Provider non configurato o disabilitato")

    # destinatario test
    dest: dict = {
        "tipo": "utente_specifico",
        "label": user.get("name"),
        "email": body.get("to_email") or user.get("email"),
        "cellulare": body.get("to_phone") or user.get("cellulare"),
        "whatsapp": body.get("to_phone") or user.get("cellulare"),
    }
    ctx = {
        "oggetto": body.get("subject") or "Test invio dal sistema Alert",
        "corpo": body.get("message")
                 or f"Ciao {user.get('name')},\n\nquesto è un messaggio di test inviato tramite il canale {tipo.upper()} dal sistema Alert.\n\nSe lo ricevi, la configurazione funziona ✓",
    }
    from alert_dispatcher import send_email as _se, send_sms as _ss, send_whatsapp as _sw
    fn = {"email": _se, "sms": _ss, "whatsapp": _sw}[tipo]
    res = await fn({"id": "test"}, dest, ctx)

    # aggiorna stato test sulla config
    await db.alert_providers.update_one(
        {"tipo": tipo},
        {"$set": {
            "last_test_at": _now_iso(),
            "last_test_status": "ok" if res.get("status") == "ok" else "errore",
            "last_test_error": res.get("error") if res.get("status") != "ok" else None,
        }},
    )
    return {"sent_to": dest.get("email") if tipo == "email" else dest.get("cellulare"), **res}
