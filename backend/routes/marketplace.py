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
    # ===== MODULI CORE (inclusi nel pacchetto base) =====
    {"codice": "CORE_PORTAFOGLIO", "nome": "Portafoglio Polizze", "descrizione": "Gestione completa polizze, titoli, garanzie e libro matricola.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "file", "categoria": "gestione", "ordine": 1},
    {"codice": "CORE_CLIENTI", "nome": "Anagrafica Clienti", "descrizione": "Anagrafica clienti, mappa, diario cliente, analisi rischi.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "users", "categoria": "gestione", "ordine": 2},
    {"codice": "CORE_SINISTRI", "nome": "Gestione Sinistri", "descrizione": "Apertura, gestione e liquidazione sinistri con workflow completo.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "alert", "categoria": "gestione", "ordine": 3},
    {"codice": "CORE_PRIMANOTA", "nome": "Prima Nota & Contabilità", "descrizione": "Prima nota, titoli storici, sospesi anticipati, E/C compagnie.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "book", "categoria": "contabilita", "ordine": 4},
    {"codice": "CORE_PROVVIGIONI", "nome": "Estratto Conto Collaboratori", "descrizione": "Calcolo provvigioni, ritenute d'acconto, pagamenti sub-agenti.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "wallet", "categoria": "contabilita", "ordine": 5},
    {"codice": "CORE_IMPORT_ANIA", "nome": "Importazione Flussi ANIA", "descrizione": "Import automatico dei flussi ANIA (rec20/30/40) con OCR.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "upload", "categoria": "gestione", "ordine": 6},
    {"codice": "CORE_STATISTICHE", "nome": "Statistiche & Dashboard", "descrizione": "KPI portafoglio, scadenzari, statistiche compagnie e produzione.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "activity", "categoria": "analisi", "ordine": 7},
    {"codice": "CORE_ALERT", "nome": "Alert & Automazioni", "descrizione": "Avvisi scadenza polizze, quietanze, corsi IVASS, sinistri.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "bell", "categoria": "automazione", "ordine": 8},
    {"codice": "CORE_CHAT_INTERNA", "nome": "Chat Interna & Diario", "descrizione": "Chat interna tra collaboratori, diario cliente cronologico, ticket interni.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "message", "categoria": "comunicazione", "ordine": 9},
    {"codice": "CORE_WHATSAPP", "nome": "WhatsApp Base (Evolution API)", "descrizione": "Chat WhatsApp business multi-numero via Evolution API.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "message", "categoria": "comunicazione", "ordine": 10},
    {"codice": "CORE_OCR", "nome": "OCR Documenti (Gemini)", "descrizione": "Estrazione automatica dati da documenti (carta id, patente, polizze).", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "sparkles", "categoria": "analisi", "ordine": 11},
    {"codice": "CORE_AI_ASSISTENTE", "nome": "Assistente AI (OpenAI/Claude)", "descrizione": "Chat AI + Il Cervello: analisi cross-cliente, insight, suggerimenti.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "brain", "categoria": "analisi", "ordine": 12},
    {"codice": "CORE_CORSI_IVASS", "nome": "Corsi IVASS 30h", "descrizione": "Tracciamento corsi obbligatori IVASS per collaboratori.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "graduation", "categoria": "compliance", "ordine": 13},
    {"codice": "CORE_MARKETING", "nome": "Marketing & Newsletter", "descrizione": "Campagne marketing, newsletter, liste lead, voucher compagnia.", "prezzo_eur": 0.0, "tipo_modulo": "core", "tipo": "ricorrente", "icona": "megaphone", "categoria": "marketing", "ordine": 14},

    # ===== ESTENSIONI (add-on acquistabili) =====
    {"codice": "RISK_3D", "nome": "Risk Assessment 3D", "descrizione": "Analisi rischio avanzata con visualizzazione 3D di scenari.", "prezzo_eur": 89.0, "tipo_modulo": "estensione", "tipo": "ricorrente", "icona": "shield", "categoria": "analisi", "ordine": 101},
    {"codice": "FIRMA_DIG", "nome": "Firma Digitale Qualificata", "descrizione": "Firma digitale eIDAS-compliant integrata con InfoCert/Aruba.", "prezzo_eur": 49.0, "tipo_modulo": "estensione", "tipo": "ricorrente", "icona": "signature", "categoria": "firma", "ordine": 102},
    {"codice": "SMS_1000", "nome": "Pacchetto SMS 1.000", "descrizione": "1.000 SMS transazionali (avvisi scadenze, promemoria).", "prezzo_eur": 39.0, "tipo_modulo": "estensione", "tipo": "consumo", "icona": "message", "categoria": "comunicazione", "ordine": 103},
    {"codice": "WA_ILIMITED", "nome": "WhatsApp Illimitato", "descrizione": "Messaggi WhatsApp illimitati + broadcast marketing.", "prezzo_eur": 29.0, "tipo_modulo": "estensione", "tipo": "ricorrente", "icona": "whatsapp", "categoria": "comunicazione", "ordine": 104},
    {"codice": "GDRIVE", "nome": "Google Drive Sync", "descrizione": "Sincronizzazione automatica documenti su Google Drive.", "prezzo_eur": 19.0, "tipo_modulo": "estensione", "tipo": "ricorrente", "icona": "cloud", "categoria": "integrazioni", "ordine": 105},
    {"codice": "ONEDRIVE", "nome": "Microsoft OneDrive Sync", "descrizione": "Sincronizzazione documenti su OneDrive/SharePoint.", "prezzo_eur": 19.0, "tipo_modulo": "estensione", "tipo": "ricorrente", "icona": "cloud", "categoria": "integrazioni", "ordine": 106},
    {"codice": "S3", "nome": "Storage AWS S3 dedicato", "descrizione": "Bucket S3 dedicato con presigned URL sicuri.", "prezzo_eur": 25.0, "tipo_modulo": "estensione", "tipo": "ricorrente", "icona": "database", "categoria": "integrazioni", "ordine": 107},
    {"codice": "STRIPE_PAY", "nome": "Pagamenti Online Stripe", "descrizione": "Incassi premi e provvigioni via Stripe (carte, SEPA, Bonifico).", "prezzo_eur": 15.0, "tipo_modulo": "estensione", "tipo": "ricorrente", "icona": "credit-card", "categoria": "pagamenti", "ordine": 108},
    {"codice": "PENSIONI", "nome": "Calcolo Pensione INPS", "descrizione": "Simulatore pensione INPS + gap analysis per proposte previdenza.", "prezzo_eur": 25.0, "tipo_modulo": "estensione", "tipo": "ricorrente", "icona": "calculator", "categoria": "analisi", "ordine": 109},
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
