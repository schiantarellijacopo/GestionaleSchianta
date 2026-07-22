"""Super Admin audit log — tracciamento azioni del platform owner.

Ogni azione critica del super_admin viene registrata in `super_admin_logs`.
Accessibile SOLO al super_admin (nessun utente tenant può leggere questo log).
"""
from __future__ import annotations
import logging
from typing import Optional, Any
from fastapi import Request

from database import raw_db
from db_models import _now_iso, _uid

logger = logging.getLogger(__name__)


# Categorie standard di eventi
ACTION_TYPES = {
    "SUPER_ADMIN_LOGIN": "Accesso al pannello Super Admin",
    "AGENCY_CREATED": "Nuova agenzia cliente creata",
    "AGENCY_UPDATED": "Metadata agenzia aggiornata",
    "AGENCY_DELETED": "Agenzia cancellata (soft delete)",
    "TENANT_ACTIVATED": "Abbonamento agenzia attivato",
    "TENANT_SUSPENDED": "Agenzia sospesa",
    "TENANT_TRIAL_EXTENDED": "Periodo di prova esteso",
    "MARKETPLACE_MODULE_TOGGLED": "Modulo marketplace attivato/disattivato",
    "MARKETPLACE_MODULE_CREATED": "Nuovo modulo aggiunto al catalogo",
    "TICKET_REPLIED": "Risposta a ticket helpdesk",
    "TICKET_STATUS_CHANGED": "Stato ticket modificato",
    "DEMO_SEEDED": "Tenant demo popolato con dati fittizi",
    "SUBSCRIPTION_UPDATED": "Abbonamento modificato",
}


def _get_client_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    # X-Forwarded-For (proxy) → primo IP
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


async def log_action(
    *,
    user: dict[str, Any],
    action_type: str,
    target_agency_id: Optional[str] = None,
    target_agency_name: Optional[str] = None,
    details: Optional[str] = None,
    meta: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Registra un'azione del super_admin. Non blocca in caso di errore."""
    try:
        entry = {
            "id": _uid(),
            "timestamp": _now_iso(),
            "created_at": _now_iso(),
            "super_admin_id": user.get("id") if user else None,
            "super_admin_email": user.get("email") if user else None,
            "super_admin_name": user.get("name") if user else None,
            "action_type": action_type,
            "action_label": ACTION_TYPES.get(action_type, action_type),
            "target_agency_id": target_agency_id,
            "target_agency_name": target_agency_name,
            "ip_address": _get_client_ip(request),
            "user_agent": (request.headers.get("user-agent") if request else None),
            "details": details,
            "meta": meta or {},
        }
        await raw_db.super_admin_logs.insert_one(entry)
    except Exception as e:
        logger.warning("audit log failed: %s", e)


async def get_agency_name(tid: str) -> Optional[str]:
    try:
        t = await raw_db.tenants.find_one({"id": tid}, {"_id": 0, "ragione_sociale": 1})
        return (t or {}).get("ragione_sociale")
    except Exception:
        return None
