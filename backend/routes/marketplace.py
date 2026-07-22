"""Marketplace router — moduli aggiuntivi (SaaS add-ons).

Endpoints Agenzia (utenti admin del tenant):
  GET  /marketplace/moduli          → catalogo moduli disponibili + stato per la mia agenzia
  POST /marketplace/richieste       → invia richiesta di attivazione
  GET  /marketplace/richieste/mie   → storico richieste dell'agenzia

Endpoints Super Admin (in `routes/super_admin.py`):
  GET   /super-admin/marketplace/moduli        → CRUD moduli catalogo
  POST  /super-admin/marketplace/moduli        → crea modulo
  GET   /super-admin/marketplace/richieste     → tutte le richieste cross-tenant
  PATCH /super-admin/marketplace/richieste/{id}/toggle  → attiva/disattiva
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_user
from database import raw_db
from db_models import MarketplaceModule, MarketplaceRequest, _now_iso
from tenant import user_tenant_id, is_super_admin


router = APIRouter(prefix="/marketplace", tags=["marketplace"])


DEFAULT_MODULI = [
    {"codice": "RISK_3D", "nome": "Risk Assessment 3D", "descrizione": "Analisi rischio avanzata con visualizzazione 3D di scenari.", "prezzo_eur": 89.0, "tipo": "ricorrente", "icona": "shield", "categoria": "analisi", "ordine": 1},
    {"codice": "FIRMA_DIG", "nome": "Firma Digitale Qualificata", "descrizione": "Firma digitale eIDAS-compliant integrata con InfoCert/Aruba.", "prezzo_eur": 49.0, "tipo": "ricorrente", "icona": "signature", "categoria": "firma", "ordine": 2},
    {"codice": "SMS_1000", "nome": "Pacchetto SMS 1.000", "descrizione": "1.000 SMS transazionali (avvisi scadenze, promemoria).", "prezzo_eur": 39.0, "tipo": "consumo", "icona": "message", "categoria": "comunicazione", "ordine": 3},
    {"codice": "WA_ILIMITED", "nome": "WhatsApp Illimitato", "descrizione": "Messaggi WhatsApp illimitati via Evolution API.", "prezzo_eur": 29.0, "tipo": "ricorrente", "icona": "whatsapp", "categoria": "comunicazione", "ordine": 4},
    {"codice": "GDRIVE", "nome": "Google Drive Sync", "descrizione": "Sincronizzazione automatica documenti su Google Drive.", "prezzo_eur": 19.0, "tipo": "ricorrente", "icona": "cloud", "categoria": "integrazioni", "ordine": 5},
    {"codice": "ONEDRIVE", "nome": "Microsoft OneDrive Sync", "descrizione": "Sincronizzazione documenti su OneDrive/SharePoint.", "prezzo_eur": 19.0, "tipo": "ricorrente", "icona": "cloud", "categoria": "integrazioni", "ordine": 6},
    {"codice": "S3", "nome": "Storage AWS S3 dedicato", "descrizione": "Bucket S3 dedicato per l'archiviazione documenti.", "prezzo_eur": 25.0, "tipo": "ricorrente", "icona": "database", "categoria": "integrazioni", "ordine": 7},
]


async def seed_default_moduli():
    """Idempotente: assicura la presenza dei moduli standard nel catalogo."""
    for m in DEFAULT_MODULI:
        await raw_db.marketplace_modules.update_one(
            {"codice": m["codice"]},
            {"$setOnInsert": {**MarketplaceModule(**m).model_dump()}},
            upsert=True,
        )


class RichiestaBody(BaseModel):
    module_codice: str
    note: Optional[str] = None


@router.get("/moduli")
async def list_moduli(user=Depends(current_user)) -> list[dict]:
    """Lista catalogo moduli + stato per il tenant dell'utente."""
    tid = user_tenant_id(user)
    moduli = await raw_db.marketplace_modules.find(
        {"attivo": True}, {"_id": 0}
    ).sort("ordine", 1).to_list(200)
    # Stato per il mio tenant
    if tid:
        req_by_cod = {}
        async for r in raw_db.marketplace_requests.find(
            {"tenant_id": tid}, {"_id": 0}
        ).sort("created_at", -1):
            req_by_cod.setdefault(r["module_codice"], r)
        for m in moduli:
            r = req_by_cod.get(m["codice"])
            m["stato_agenzia"] = r["stato"] if r else "non_attivo"
            m["request_id"] = r["id"] if r else None
    else:
        for m in moduli:
            m["stato_agenzia"] = "non_attivo"
    return moduli


@router.post("/richieste", status_code=201)
async def create_richiesta(body: RichiestaBody, user=Depends(require_user("admin"))) -> dict:
    """L'admin dell'agenzia invia richiesta di attivazione modulo."""
    tid = user_tenant_id(user)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant non identificato")
    mod = await raw_db.marketplace_modules.find_one({"codice": body.module_codice}, {"_id": 0})
    if not mod:
        raise HTTPException(status_code=404, detail="Modulo non trovato")
    # Se esiste già una richiesta attiva/in_lavorazione, non duplicare
    existing = await raw_db.marketplace_requests.find_one(
        {"tenant_id": tid, "module_codice": body.module_codice,
         "stato": {"$in": ["richiesto", "in_lavorazione", "attivo"]}},
        {"_id": 0},
    )
    if existing:
        return existing
    req = MarketplaceRequest(
        tenant_id=tid,
        module_codice=body.module_codice,
        module_nome=mod["nome"],
        prezzo_concordato_eur=mod.get("prezzo_eur", 0.0),
        stato="richiesto",
        note_agenzia=body.note,
        richiesto_da_user_id=user.get("id") if user else None,
    ).model_dump()
    await raw_db.marketplace_requests.insert_one(req)
    req.pop("_id", None)
    return req


@router.get("/richieste/mie")
async def my_richieste(user=Depends(current_user)) -> list[dict]:
    tid = user_tenant_id(user)
    if not tid:
        return []
    return await raw_db.marketplace_requests.find(
        {"tenant_id": tid}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
