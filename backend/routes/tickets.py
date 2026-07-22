"""Tickets router — helpdesk agenzia ↔ super_admin.

Endpoints Agenzia:
  GET  /tickets/mie            → lista ticket della mia agenzia
  POST /tickets                → apri nuovo ticket
  GET  /tickets/{tid}          → dettaglio ticket + thread messaggi
  POST /tickets/{tid}/messaggi → aggiungi messaggio al thread

Endpoints Super Admin (in `routes/super_admin.py`):
  GET   /super-admin/tickets                    → tutti i ticket cross-tenant
  GET   /super-admin/tickets/{tid}              → dettaglio (con thread)
  POST  /super-admin/tickets/{tid}/rispondi     → risposta admin + cambio stato
  PATCH /super-admin/tickets/{tid}/stato        → aggiorna stato
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Literal, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_user
from database import raw_db
from db_models import Ticket, TicketMessage, _now_iso
from tenant import user_tenant_id, is_super_admin


router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketBody(BaseModel):
    oggetto: str
    categoria: Literal["bug", "feature_request", "supporto", "billing", "integrazione", "altro"] = "supporto"
    priorita: Literal["bassa", "normale", "alta", "urgente"] = "normale"
    descrizione: str
    allegati: List[dict] = []


class MessaggioBody(BaseModel):
    messaggio: str
    allegati: List[dict] = []


async def _numero_ticket() -> str:
    year = datetime.now(timezone.utc).year
    n = await raw_db.tickets.count_documents({"numero": {"$regex": f"^TCK-{year}-"}}) + 1
    return f"TCK-{year}-{n:04d}"


@router.get("/mie")
async def my_tickets(user=Depends(current_user)) -> list[dict]:
    tid = user_tenant_id(user)
    if not tid:
        return []
    return await raw_db.tickets.find(
        {"tenant_id": tid}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)


@router.post("", status_code=201)
async def create_ticket(body: TicketBody, user=Depends(current_user)) -> dict:
    tid = user_tenant_id(user)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant non identificato")
    tenant = await raw_db.tenants.find_one({"id": tid}, {"_id": 0, "ragione_sociale": 1})
    numero = await _numero_ticket()
    t = Ticket(
        tenant_id=tid,
        tenant_ragione_sociale=(tenant or {}).get("ragione_sociale"),
        numero=numero,
        oggetto=body.oggetto,
        categoria=body.categoria,
        priorita=body.priorita,
        descrizione=body.descrizione,
        allegati=body.allegati or [],
        aperto_da_user_id=user.get("id") if user else None,
        aperto_da_email=user.get("email") if user else None,
    ).model_dump()
    await raw_db.tickets.insert_one(t)
    # Primo messaggio = descrizione
    msg = TicketMessage(
        ticket_id=t["id"],
        autore_user_id=user.get("id") if user else None,
        autore_email=user.get("email") if user else None,
        autore_ruolo="agenzia",
        messaggio=body.descrizione,
        allegati=body.allegati or [],
    ).model_dump()
    await raw_db.ticket_messages.insert_one(msg)
    t.pop("_id", None)
    return t


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str, user=Depends(current_user)) -> dict:
    tid = user_tenant_id(user)
    t = await raw_db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket non trovato")
    # Un'agenzia può vedere solo i propri ticket
    if not is_super_admin(user) and t.get("tenant_id") != tid:
        raise HTTPException(status_code=403, detail="Accesso negato")
    messages = await raw_db.ticket_messages.find(
        {"ticket_id": ticket_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    t["messages"] = messages
    return t


@router.post("/{ticket_id}/messaggi", status_code=201)
async def add_messaggio(ticket_id: str, body: MessaggioBody,
                        user=Depends(current_user)) -> dict:
    tid = user_tenant_id(user)
    t = await raw_db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket non trovato")
    if not is_super_admin(user) and t.get("tenant_id") != tid:
        raise HTTPException(status_code=403, detail="Accesso negato")
    msg = TicketMessage(
        ticket_id=ticket_id,
        autore_user_id=user.get("id") if user else None,
        autore_email=user.get("email") if user else None,
        autore_ruolo="super_admin" if is_super_admin(user) else "agenzia",
        messaggio=body.messaggio,
        allegati=body.allegati or [],
    ).model_dump()
    await raw_db.ticket_messages.insert_one(msg)
    # Aggiorna stato ticket
    new_state = "in_lavorazione" if is_super_admin(user) and t.get("stato") == "aperto" else t.get("stato")
    await raw_db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {"stato": new_state, "updated_at": _now_iso()}},
    )
    msg.pop("_id", None)
    return msg
