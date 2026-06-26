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
    AlertRule, AlertEvent, ALERT_EVENT_TYPES, ALERT_SCHEDULE_TYPES, CANALI, DESTINATARI,
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
    r = await db.alert_rules.find_one({"id": rid}, {"_id": 0, "is_preset": 1})
    if not r:
        raise HTTPException(404, "Regola non trovata")
    if r.get("is_preset"):
        raise HTTPException(400, "Le regole preset non si possono eliminare. Disattivale invece.")
    await db.alert_rules.delete_one({"id": rid})
    return {"ok": True}


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
