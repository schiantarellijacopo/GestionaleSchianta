"""Super Admin router — gestione SaaS/licenze/abbonamenti/onboarding agenzie.

Riservato al proprietario della piattaforma (`is_super_admin=True`).

⚠️ PRIVACY / GDPR:
Il super_admin NON può accedere ai dati sensibili delle agenzie clienti
(clienti, polizze, incassi, documenti). Il wrapper `TenantAwareDB` blocca
automaticamente ogni query su collezioni tenant-scoped quando l'utente è
super_admin. Il super_admin gestisce SOLO la parte amministrativa/licenze.

Endpoints:
  GET    /super-admin/agenzie                → lista agenzie clienti + stato
  GET    /super-admin/agenzie/{tid}          → dettaglio (senza dati sensibili)
  POST   /super-admin/agenzie                → crea nuova agenzia (clean|demo)
  PATCH  /super-admin/agenzie/{tid}          → aggiorna metadata + licenza
  POST   /super-admin/agenzie/{tid}/attiva   → attiva abbonamento
  POST   /super-admin/agenzie/{tid}/sospendi → sospendi
  POST   /super-admin/agenzie/{tid}/prova    → estendi/imposta trial
  DELETE /super-admin/agenzie/{tid}          → soft-delete (cancellata)

  GET    /super-admin/abbonamenti            → lista subscription
  GET    /super-admin/transazioni            → storico transazioni Stripe

  POST   /super-admin/demo/seed              → popola tenant demo con dati dummy
  GET    /super-admin/stats                  → KPI piattaforma (senza PII)
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import require_user
from database import raw_db  # bypassa il wrapper: super_admin è già bloccato sui dati clienti
from db_models import Tenant, _now_iso
from tenant import (
    TENANT_PRINCIPALE_ID, TENANT_DEMO_ID, TENANT_CLEAN_ID,
    is_super_admin, TENANT_SCOPED_COLLECTIONS,
)
from audit_super_admin import log_action, get_agency_name
from resend_service import (
    send_marketplace_activation, send_ticket_reply, send_welcome_user,
)


router = APIRouter(prefix="/super-admin", tags=["super-admin"])


def _ensure_super_admin(user):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Solo super_admin")


# ---------------------------------------------------------------------------
# MARKETPLACE MGMT (super_admin cross-tenant)
# ---------------------------------------------------------------------------
@router.get("/marketplace/moduli")
async def sa_list_moduli(user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    return await raw_db.marketplace_modules.find({}, {"_id": 0}).sort("ordine", 1).to_list(200)


class ModuloCatalogoBody(BaseModel):
    codice: str
    nome: str
    descrizione: str
    prezzo_eur: float = 0.0
    tipo: Literal["ricorrente", "una_tantum", "consumo"] = "ricorrente"
    categoria: Optional[str] = None
    icona: Optional[str] = None
    attivo: bool = True
    ordine: int = 0


@router.post("/marketplace/moduli", status_code=201)
async def sa_create_modulo(body: ModuloCatalogoBody,
                           user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    from db_models import MarketplaceModule
    m = MarketplaceModule(**body.model_dump()).model_dump()
    await raw_db.marketplace_modules.insert_one(m)
    m.pop("_id", None)
    return m


@router.get("/marketplace/richieste")
async def sa_list_richieste(user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    items = await raw_db.marketplace_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    tids = {i["tenant_id"] for i in items}
    tenants = {t["id"]: t["ragione_sociale"] async for t in raw_db.tenants.find({"id": {"$in": list(tids)}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    for r in items:
        r["tenant_ragione_sociale"] = tenants.get(r["tenant_id"], "?")
    return items


class ToggleModuloBody(BaseModel):
    stato: Literal["richiesto", "in_lavorazione", "attivo", "non_attivo", "rifiutato"]
    note_admin: Optional[str] = None


@router.patch("/marketplace/richieste/{req_id}/toggle")
async def sa_toggle_richiesta(req_id: str, body: ToggleModuloBody, request: Request,
                              user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    payload = {"stato": body.stato, "updated_at": _now_iso()}
    if body.note_admin is not None:
        payload["note_admin"] = body.note_admin
    if body.stato == "attivo":
        payload["data_attivazione"] = datetime.now(timezone.utc).date().isoformat()
    res = await raw_db.marketplace_requests.update_one({"id": req_id}, {"$set": payload})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    req_doc = await raw_db.marketplace_requests.find_one({"id": req_id}, {"_id": 0})
    # Log + Email
    await log_action(user=user, action_type="MARKETPLACE_MODULE_TOGGLED",
                     target_agency_id=req_doc.get("tenant_id"),
                     target_agency_name=await get_agency_name(req_doc.get("tenant_id", "")),
                     details=f"Modulo {req_doc.get('module_nome')} → {body.stato}",
                     request=request)
    tenant = await raw_db.tenants.find_one({"id": req_doc.get("tenant_id")}, {"_id": 0, "email": 1})
    if tenant and tenant.get("email"):
        await send_marketplace_activation(
            to=tenant["email"], modulo_nome=req_doc.get("module_nome", ""),
            stato=body.stato,
        )
    return req_doc


# ---------------------------------------------------------------------------
# TICKETS MGMT (super_admin helpdesk)
# ---------------------------------------------------------------------------
@router.get("/tickets")
async def sa_list_tickets(stato: Optional[str] = None,
                          user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    q: dict = {}
    if stato:
        q["stato"] = stato
    return await raw_db.tickets.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/tickets/{ticket_id}")
async def sa_get_ticket(ticket_id: str, user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    t = await raw_db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket non trovato")
    msgs = await raw_db.ticket_messages.find({"ticket_id": ticket_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    t["messages"] = msgs
    return t


class RispostaBody(BaseModel):
    messaggio: str
    stato: Optional[Literal["aperto", "in_lavorazione", "risolto", "chiuso"]] = None


@router.post("/tickets/{ticket_id}/rispondi")
async def sa_rispondi_ticket(ticket_id: str, body: RispostaBody, request: Request,
                             user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    t = await raw_db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket non trovato")
    from db_models import TicketMessage
    msg = TicketMessage(
        ticket_id=ticket_id,
        autore_user_id=user.get("id"),
        autore_email=user.get("email"),
        autore_ruolo="super_admin",
        messaggio=body.messaggio,
    ).model_dump()
    await raw_db.ticket_messages.insert_one(msg)
    new_state = body.stato or ("risolto" if body.stato == "risolto" else "in_lavorazione")
    set_payload = {"stato": new_state, "updated_at": _now_iso()}
    if new_state in ("risolto", "chiuso"):
        set_payload["data_chiusura"] = _now_iso()
    await raw_db.tickets.update_one({"id": ticket_id}, {"$set": set_payload})
    # Log + Email
    await log_action(user=user, action_type="TICKET_REPLIED",
                     target_agency_id=t.get("tenant_id"),
                     target_agency_name=t.get("tenant_ragione_sociale"),
                     details=f"Ticket {t.get('numero')} → {new_state}",
                     request=request)
    if t.get("aperto_da_email"):
        await send_ticket_reply(
            to=t["aperto_da_email"],
            numero_ticket=t.get("numero", ""),
            oggetto=t.get("oggetto", ""),
            messaggio=body.messaggio,
            stato=new_state,
        )
    return {"ok": True, "stato": new_state}


class TicketStatoBody(BaseModel):
    stato: Literal["aperto", "in_lavorazione", "risolto", "chiuso"]


@router.patch("/tickets/{ticket_id}/stato")
async def sa_update_stato(ticket_id: str, body: TicketStatoBody,
                          user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    set_payload = {"stato": body.stato, "updated_at": _now_iso()}
    if body.stato in ("risolto", "chiuso"):
        set_payload["data_chiusura"] = _now_iso()
    res = await raw_db.tickets.update_one({"id": ticket_id}, {"$set": set_payload})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Ticket non trovato")
    return {"ok": True, "stato": body.stato}


# ---------------------------------------------------------------------------
# AGENZIE CLIENTI
# ---------------------------------------------------------------------------
class AgenziaNuovaBody(BaseModel):
    ragione_sociale: str
    partita_iva: Optional[str] = None
    codice_fiscale: Optional[str] = None
    referente: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    indirizzo: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    piano: Literal["trial", "starter", "professional", "enterprise", "custom"] = "trial"
    giorni_prova: int = 30
    prezzo_mensile_eur: float = 0.0
    max_utenti: int = 5
    # Se `template` = "demo" copia i dati fittizi del tenant demo nel nuovo tenant.
    # Se `template` = "clean" crea un tenant completamente vuoto.
    template: Literal["clean", "demo"] = "clean"
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None
    admin_name: Optional[str] = None
    note: Optional[str] = None


class AgenziaUpdateBody(BaseModel):
    ragione_sociale: Optional[str] = None
    partita_iva: Optional[str] = None
    codice_fiscale: Optional[str] = None
    referente: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    indirizzo: Optional[str] = None
    citta: Optional[str] = None
    provincia: Optional[str] = None
    piano: Optional[str] = None
    stato_abbonamento: Optional[str] = None
    prezzo_mensile_eur: Optional[float] = None
    max_utenti: Optional[int] = None
    note: Optional[str] = None


async def _tenant_stats(tid: str) -> dict:
    """KPI aggregati (SOLO conteggi, no dati sensibili)."""
    counts = {}
    for coll in ("anagrafiche", "polizze", "titoli", "sinistri"):
        counts[coll] = await raw_db[coll].count_documents({"agenzia_tenant_id": tid})
    n_users = await raw_db.users.count_documents({"agenzia_tenant_id": tid})
    counts["utenti"] = n_users
    return counts


@router.get("/agenzie")
async def list_agenzie(user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    items = await raw_db.tenants.find({}, {"_id": 0}).sort("ragione_sociale", 1).to_list(500)
    # Per ogni tenant, aggiungi il conteggio utenti/clienti/polizze (SOLO cifre)
    for t in items:
        t["stats"] = await _tenant_stats(t["id"])
    return items


@router.get("/agenzie/{tid}")
async def get_agenzia(tid: str, user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    t = await raw_db.tenants.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    t["stats"] = await _tenant_stats(tid)
    return t


@router.post("/agenzie", status_code=201)
async def create_agenzia(body: AgenziaNuovaBody, request: Request,
                         user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    now = datetime.now(timezone.utc)
    fine_prova = (now + timedelta(days=body.giorni_prova)).date().isoformat() if body.piano == "trial" else None
    tenant = Tenant(
        ragione_sociale=body.ragione_sociale,
        codice=(body.ragione_sociale[:6].upper().replace(" ", "")),
        tipo="partner",
        attivo=True,
        storage_provider="emergent",
        partita_iva=body.partita_iva,
        codice_fiscale=body.codice_fiscale,
        referente=body.referente,
        email=body.email,
        telefono=body.telefono,
        indirizzo=body.indirizzo,
        citta=body.citta,
        provincia=body.provincia,
        stato_abbonamento="in_prova" if body.piano == "trial" else "attiva",
        piano=body.piano,
        prezzo_mensile_eur=body.prezzo_mensile_eur,
        data_inizio_abbonamento=now.date().isoformat(),
        data_fine_prova=fine_prova,
        max_utenti=body.max_utenti,
        note=body.note,
    ).model_dump()
    await raw_db.tenants.insert_one(tenant)
    tenant.pop("_id", None)

    # Crea utente admin iniziale se fornito
    if body.admin_email and body.admin_password:
        from auth import hash_password
        import uuid
        existing = await raw_db.users.find_one({"email": body.admin_email.lower()})
        if not existing:
            admin_doc = {
                "id": str(uuid.uuid4()),
                "email": body.admin_email.lower(),
                "name": body.admin_name or body.referente or "Amministratore",
                "role": "admin",
                "attivo": True,
                "is_super_admin": False,
                "agenzia_tenant_id": tenant["id"],
                "password_hash": hash_password(body.admin_password),
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
            await raw_db.users.insert_one(admin_doc)
            tenant["admin_created"] = body.admin_email
            # Welcome email
            await send_welcome_user(
                to=body.admin_email.lower(),
                name=admin_doc["name"],
                agency_name=tenant["ragione_sociale"],
            )

    # Se template == demo → clona i dati fittizi del tenant demo
    if body.template == "demo":
        cloned = await _clone_from_demo(tenant["id"])
        tenant["seeded_from_demo"] = cloned

    await log_action(user=user, action_type="AGENCY_CREATED",
                     target_agency_id=tenant["id"],
                     target_agency_name=tenant["ragione_sociale"],
                     details=f"Piano={body.piano}, template={body.template}, prezzo={body.prezzo_mensile_eur}€/mese",
                     request=request)
    return tenant


@router.patch("/agenzie/{tid}")
async def update_agenzia(tid: str, body: AgenziaUpdateBody, request: Request,
                         user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    payload = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    payload["updated_at"] = _now_iso()
    res = await raw_db.tenants.update_one({"id": tid}, {"$set": payload})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    await log_action(user=user, action_type="AGENCY_UPDATED",
                     target_agency_id=tid, target_agency_name=await get_agency_name(tid),
                     details=f"Campi aggiornati: {', '.join(payload.keys())}",
                     request=request)
    return await raw_db.tenants.find_one({"id": tid}, {"_id": 0})


@router.post("/agenzie/{tid}/attiva")
async def attiva_agenzia(tid: str, request: Request,
                         user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    await raw_db.tenants.update_one(
        {"id": tid},
        {"$set": {"stato_abbonamento": "attiva", "attivo": True, "updated_at": _now_iso()}},
    )
    await log_action(user=user, action_type="TENANT_ACTIVATED",
                     target_agency_id=tid, target_agency_name=await get_agency_name(tid),
                     request=request)
    return {"ok": True, "stato": "attiva"}


@router.post("/agenzie/{tid}/sospendi")
async def sospendi_agenzia(tid: str, request: Request,
                           user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    if tid == TENANT_PRINCIPALE_ID:
        raise HTTPException(status_code=400, detail="Impossibile sospendere il tenant principale")
    await raw_db.tenants.update_one(
        {"id": tid},
        {"$set": {"stato_abbonamento": "sospesa", "attivo": False, "updated_at": _now_iso()}},
    )
    await log_action(user=user, action_type="TENANT_SUSPENDED",
                     target_agency_id=tid, target_agency_name=await get_agency_name(tid),
                     request=request)
    return {"ok": True, "stato": "sospesa"}


@router.post("/agenzie/{tid}/estendi-prova")
async def estendi_prova(tid: str, request: Request, giorni: int = 30,
                        user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    now = datetime.now(timezone.utc)
    fine = (now + timedelta(days=giorni)).date().isoformat()
    await raw_db.tenants.update_one(
        {"id": tid},
        {"$set": {"stato_abbonamento": "in_prova", "attivo": True,
                  "data_fine_prova": fine, "updated_at": _now_iso()}},
    )
    await log_action(user=user, action_type="TENANT_TRIAL_EXTENDED",
                     target_agency_id=tid, target_agency_name=await get_agency_name(tid),
                     details=f"+{giorni} giorni (nuova scadenza: {fine})",
                     request=request)
    return {"ok": True, "data_fine_prova": fine}


@router.delete("/agenzie/{tid}")
async def cancella_agenzia(tid: str, request: Request,
                           user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    if tid in (TENANT_PRINCIPALE_ID, TENANT_DEMO_ID, TENANT_CLEAN_ID):
        raise HTTPException(status_code=400, detail="Tenant di sistema non cancellabile")
    await raw_db.tenants.update_one(
        {"id": tid},
        {"$set": {"stato_abbonamento": "cancellata", "attivo": False, "updated_at": _now_iso()}},
    )
    await log_action(user=user, action_type="AGENCY_DELETED",
                     target_agency_id=tid, target_agency_name=await get_agency_name(tid),
                     request=request)
    return {"ok": True}


# ---------------------------------------------------------------------------
# ABBONAMENTI & TRANSAZIONI
# ---------------------------------------------------------------------------
@router.get("/abbonamenti")
async def list_abbonamenti(user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    items = await raw_db.subscriptions.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Enrichi con ragione sociale tenant
    tids = {i["tenant_id"] for i in items}
    tenants = {t["id"]: t["ragione_sociale"] async for t in raw_db.tenants.find({"id": {"$in": list(tids)}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    for s in items:
        s["tenant_ragione_sociale"] = tenants.get(s["tenant_id"], "?")
    return items


@router.get("/transazioni")
async def list_transazioni(user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    items = await raw_db.transactions.find({}, {"_id": 0}).sort("data_transazione", -1).to_list(500)
    tids = {i["tenant_id"] for i in items}
    tenants = {t["id"]: t["ragione_sociale"] async for t in raw_db.tenants.find({"id": {"$in": list(tids)}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    for t in items:
        t["tenant_ragione_sociale"] = tenants.get(t["tenant_id"], "?")
    return items


# ---------------------------------------------------------------------------
# STATS PIATTAFORMA (aggregati, senza PII)
# ---------------------------------------------------------------------------
@router.get("/stats")
async def platform_stats(user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    tot_agenzie = await raw_db.tenants.count_documents({})
    attive = await raw_db.tenants.count_documents({"stato_abbonamento": "attiva"})
    in_prova = await raw_db.tenants.count_documents({"stato_abbonamento": "in_prova"})
    sospese = await raw_db.tenants.count_documents({"stato_abbonamento": "sospesa"})
    # MRR = somma prezzi mensili degli abbonamenti attivi
    mrr_agg = raw_db.tenants.aggregate([
        {"$match": {"stato_abbonamento": "attiva"}},
        {"$group": {"_id": None, "mrr": {"$sum": "$prezzo_mensile_eur"}}},
    ])
    mrr_docs = await mrr_agg.to_list(1)
    mrr = float(mrr_docs[0]["mrr"]) if mrr_docs else 0.0
    return {
        "totale_agenzie": tot_agenzie,
        "attive": attive,
        "in_prova": in_prova,
        "sospese": sospese,
        "mrr_eur": round(mrr, 2),
        "arr_eur": round(mrr * 12, 2),
    }


# ---------------------------------------------------------------------------
# DEMO SEED
# ---------------------------------------------------------------------------
@router.post("/demo/seed")
async def demo_seed(request: Request, user=Depends(require_user("admin"))) -> dict:
    """Popola il tenant `demo` con dati fittizi per le simulazioni commerciali."""
    _ensure_super_admin(user)
    from demo_seed import seed_demo_tenant
    res = await seed_demo_tenant()
    await log_action(user=user, action_type="DEMO_SEEDED",
                     target_agency_id=TENANT_DEMO_ID,
                     target_agency_name="Agenzia Demo (Staging)",
                     details=f"Records: {res.get('created')}",
                     request=request)
    return res


async def _clone_from_demo(target_tid: str) -> dict[str, int]:
    """Copia i dati fittizi del tenant demo nel target tenant."""
    from uuid import uuid4
    report: dict[str, int] = {}
    for coll in ("anagrafiche", "polizze", "titoli", "sinistri", "compagnie"):
        docs = await raw_db[coll].find({"agenzia_tenant_id": TENANT_DEMO_ID}, {"_id": 0}).to_list(500)
        if not docs:
            continue
        # Rigenera id univoci e riassegna tenant
        for d in docs:
            d["id"] = str(uuid4())
            d["agenzia_tenant_id"] = target_tid
            d["created_at"] = _now_iso()
            d["updated_at"] = _now_iso()
        if docs:
            await raw_db[coll].insert_many(docs)
            report[coll] = len(docs)
    return report
