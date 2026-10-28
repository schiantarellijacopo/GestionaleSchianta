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
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import require_user
from database import raw_db  # bypassa il wrapper: super_admin è già bloccato sui dati clienti
from db_models import Tenant, _now_iso, _uid
from tenant import (
    TENANT_PRINCIPALE_ID, TENANT_DEMO_ID, TENANT_CLEAN_ID,
    is_super_admin, TENANT_SCOPED_COLLECTIONS,
)
from audit_super_admin import log_action, get_agency_name
from resend_service import (
    send_marketplace_activation, send_ticket_reply, send_welcome_user,
    send_agency_credentials,
)


router = APIRouter(prefix="/super-admin", tags=["super-admin"])


def _ensure_super_admin(user):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Solo super_admin")


# ---------------------------------------------------------------------------
# CHIAVI API (firma digitale, Twilio, Spoki, WhatsApp Evolution)
# Visibili e modificabili SOLO dal super admin: le agenzie usano i servizi
# senza mai vedere token/chiavi.
# ---------------------------------------------------------------------------
_CHIAVI_AZIENDA = [
    "firma_provider", "firma_environment", "firma_base_url",
    "firma_api_token", "firma_webhook_secret",
    "yousign_environment", "yousign_sandbox_api_key", "yousign_production_api_key",
    "twilio_account_sid", "twilio_auth_token", "twilio_sms_from", "twilio_whatsapp_from",
    "spoki_api_key", "spoki_sender_name", "whatsapp_provider",
    "ai_studio_api_key", "openai_api_key",
    "openapi_it_bearer_token",
]

# Chiavi AI del vault → variabile d'ambiente sincronizzata nel processo.
# La chiave del pannello ha SEMPRE priorità sulla chiave gestita Emergent.
_CHIAVI_AI_ENV = {
    "ai_studio_api_key": "GEMINI_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
}

# Altre chiavi provider del vault → variabile d'ambiente sincronizzata.
_CHIAVI_EXTRA_ENV = {
    "openapi_it_bearer_token": "OPENAPI_IT_BEARER_TOKEN",
    "yousign_environment": "YOUSIGN_ENVIRONMENT",
    "yousign_sandbox_api_key": "YOUSIGN_SANDBOX_API_KEY",
    "yousign_production_api_key": "YOUSIGN_PRODUCTION_API_KEY",
}


@router.get("/chiavi-api")
async def sa_get_chiavi_api(user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    az = await raw_db.azienda_config.find_one({}, {"_id": 0}) or {}
    out = {k: az.get(k) for k in _CHIAVI_AZIENDA}
    evo = await raw_db.whatsapp_server_config.find_one({}, {"_id": 0}) or {}
    out["evolution_server_url"] = evo.get("server_url") or (os.environ.get("WHATSAPP_API_URL") or None)
    out["evolution_api_key"] = evo.get("api_key") or (os.environ.get("WHATSAPP_API_KEY") or None)
    out["evolution_source"] = ("db" if evo.get("server_url")
                               else "env" if os.environ.get("WHATSAPP_API_URL") else None)
    return out


@router.put("/chiavi-api")
async def sa_put_chiavi_api(body: dict, user=Depends(require_user("admin")),
                            request: Request = None) -> dict:
    _ensure_super_admin(user)
    upd = {k: body[k] for k in _CHIAVI_AZIENDA if k in body}
    if upd.get("whatsapp_provider") not in (None, "wame", "evolution", "twilio", "spoki"):
        raise HTTPException(400, "whatsapp_provider non valido")
    if upd:
        upd["updated_at"] = _now_iso()
        az = await raw_db.azienda_config.find_one({}, {"_id": 0, "id": 1})
        if az:
            await raw_db.azienda_config.update_one({"id": az["id"]}, {"$set": upd})
    # AI Studio (Gemini): rendi subito effettiva la chiave nel processo come fallback GEMINI_API_KEY
    for _field, _env in _CHIAVI_AI_ENV.items():
        if _field in body:
            _k = (body.get(_field) or "").strip()
            if _k:
                os.environ[_env] = _k
            else:
                os.environ.pop(_env, None)
    # Altre chiavi provider (es. OpenAPI.it bearer token) → env immediato
    for _field, _env in _CHIAVI_EXTRA_ENV.items():
        if _field in body:
            _k = (body.get(_field) or "").strip()
            if _k:
                os.environ[_env] = _k
            else:
                os.environ.pop(_env, None)
    if "evolution_server_url" in body or "evolution_api_key" in body:
        url = (body.get("evolution_server_url") or "").strip().rstrip("/")
        key = (body.get("evolution_api_key") or "").strip()
        if url and key:
            doc = {"server_url": url, "api_key": key,
                   "updated_at": _now_iso(), "updated_by": user.get("id")}
            existing = await raw_db.whatsapp_server_config.find_one({}, {"_id": 0, "id": 1})
            if existing:
                await raw_db.whatsapp_server_config.update_one({"id": existing["id"]}, {"$set": doc})
            else:
                await raw_db.whatsapp_server_config.insert_one({"id": _uid(), "created_at": _now_iso(), **doc})
        elif not url and not key:
            await raw_db.whatsapp_server_config.delete_many({})
    await log_action(user=user, action_type="chiavi_api_update",
                     details="Aggiornate chiavi API piattaforma", request=request)
    return {"ok": True}


@router.post("/chiavi-api/test-aistudio")
async def sa_test_aistudio(body: dict | None = None,
                           user=Depends(require_user("admin"))) -> dict:
    """Valida la chiave Google AI Studio (Gemini) senza esporne il valore."""
    _ensure_super_admin(user)
    key = ((body or {}).get("ai_studio_api_key") or "").strip()
    if not key:
        az = await raw_db.azienda_config.find_one({}, {"_id": 0, "ai_studio_api_key": 1}) or {}
        key = (az.get("ai_studio_api_key") or "").strip()
    if not key:
        raise HTTPException(400, "Nessuna chiave AI Studio configurata")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get("https://generativelanguage.googleapis.com/v1beta/models",
                            params={"key": key, "pageSize": 1})
        if r.status_code >= 400:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        return {"ok": True, "info": "Chiave AI Studio valida"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@router.post("/chiavi-api/test-openai")
async def sa_test_openai(body: dict | None = None,
                         user=Depends(require_user("admin"))) -> dict:
    """Valida la chiave OpenAI senza esporne il valore."""
    _ensure_super_admin(user)
    key = ((body or {}).get("openai_api_key") or "").strip()
    if not key:
        az = await raw_db.azienda_config.find_one({}, {"_id": 0, "openai_api_key": 1}) or {}
        key = (az.get("openai_api_key") or "").strip()
    if not key:
        raise HTTPException(400, "Nessuna chiave OpenAI configurata")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get("https://api.openai.com/v1/models",
                            headers={"Authorization": f"Bearer {key}"})
        if r.status_code >= 400:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        return {"ok": True, "info": "Chiave OpenAI valida"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@router.get("/chiavi-api/ai-status")
async def sa_ai_status(user=Depends(require_user("admin"))) -> dict:
    """Riporta quale chiave è attiva per ogni provider AI: pannello (ha priorità),
    Emergent (fallback) o nessuna. Non espone alcun valore."""
    _ensure_super_admin(user)
    emergent = bool((os.environ.get("EMERGENT_LLM_KEY") or "").strip())

    def _src(env_name: str) -> str:
        if (os.environ.get(env_name) or "").strip():
            return "pannello"
        return "emergent" if emergent else "nessuna"

    return {
        "emergent_disponibile": emergent,
        "gemini": {"attiva": _src("GEMINI_API_KEY")},
        "openai": {"attiva": _src("OPENAI_API_KEY")},
    }


@router.post("/chiavi-api/test-whatsapp")
async def sa_test_evolution(user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    evo = await raw_db.whatsapp_server_config.find_one({}, {"_id": 0}) or {}
    url = (evo.get("server_url") or os.environ.get("WHATSAPP_API_URL") or "").rstrip("/")
    key = evo.get("api_key") or os.environ.get("WHATSAPP_API_KEY") or ""
    if not url or not key:
        raise HTTPException(400, "Server Evolution non configurato")
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{url}/instance/fetchInstances", headers={"apikey": key})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
    n = len(data) if isinstance(data, list) else len(data.get("instances", []) if isinstance(data, dict) else [])
    return {"ok": True, "istanze_sul_server": n}


@router.post("/chiavi-api/test-yousign")
async def sa_test_yousign(body: dict = None, user=Depends(require_user("admin"))) -> dict:
    """Esegue un test end-to-end della firma Yousign/YouTrust in SANDBOX:
    crea richiesta → carica un PDF di prova → aggiunge firmatario → attiva →
    restituisce il LINK DI FIRMA da aprire per provare davvero.
    Usa la API key sandbox da env (YOUSIGN_SANDBOX_API_KEY)."""
    _ensure_super_admin(user)
    import io
    import httpx
    api_key = (os.environ.get("YOUSIGN_SANDBOX_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(400, "API key Yousign sandbox non configurata")
    base = "https://api-sandbox.yousign.app/v3"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    # PDF di prova (1 pagina) con reportlab
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 14)
    c.drawString(100, 760, "Documento di TEST firma — Axicura / Yousign Sandbox")
    c.drawString(100, 700, "Questo documento serve solo a verificare l'integrazione.")
    c.drawString(100, 620, "Firma qui sotto:")
    c.rect(100, 540, 180, 60)
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    email_override = ((body or {}).get("email") or "").strip()
    try:
        async with httpx.AsyncClient(base_url=base, headers=headers, timeout=40) as cli:
            # email firmatario: in sandbox deve appartenere all'organizzazione
            signer_email = email_override
            if not signer_email:
                r = await cli.get("/users", params={"limit": 5})
                if r.status_code == 200:
                    for u in r.json().get("data", []):
                        em = u.get("email") or (u.get("info") or {}).get("email")
                        if em:
                            signer_email = em
                            break
            if not signer_email:
                return {"ok": False, "error": "Nessuna email organizzazione trovata; indica un'email del tuo account Yousign."}

            req = await cli.post("/signature_requests",
                                 json={"name": "TEST firma Axicura (sandbox)", "delivery_mode": "email"})
            if req.is_error:
                return {"ok": False, "step": "crea richiesta", "error": req.text[:300]}
            rid = req.json()["id"]

            doc = await cli.post(f"/signature_requests/{rid}/documents",
                                 files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
                                 data={"nature": "signable_document"})
            if doc.is_error:
                return {"ok": False, "step": "carica PDF", "error": doc.text[:300]}
            did = doc.json()["id"]

            signer_body = {
                "info": {"first_name": "Test", "last_name": "Firma",
                         "email": signer_email, "locale": "it"},
                "signature_level": "electronic_signature",
                "signature_authentication_mode": "no_otp",
                "fields": [{"type": "signature", "document_id": did,
                            "page": 1, "x": 100, "y": 540, "width": 180, "height": 60}],
            }
            sg = await cli.post(f"/signature_requests/{rid}/signers", json=signer_body)
            if sg.is_error:
                return {"ok": False, "step": "aggiungi firmatario", "error": sg.text[:300]}
            signer_id = sg.json()["id"]

            act = await cli.post(f"/signature_requests/{rid}/activate", json={})
            if act.is_error:
                return {"ok": False, "step": "attiva", "error": act.text[:300]}
            status = act.json().get("status")

            # recupera il link di firma del firmatario
            link = None
            sdet = await cli.get(f"/signature_requests/{rid}/signers/{signer_id}")
            if sdet.status_code == 200:
                link = sdet.json().get("signature_link")

        return {
            "ok": True,
            "request_id": rid,
            "status": status,
            "signer_email": signer_email,
            "signing_url": link,
            "message": "Firma sandbox attivata. Apri il link di firma per provare, oppure controlla l'email ricevuta.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}



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
    tipo_modulo: Literal["core", "estensione"] = "estensione"
    tipo: Literal["ricorrente", "una_tantum", "consumo"] = "ricorrente"
    categoria: Optional[str] = None
    icona: Optional[str] = None
    attivo: bool = True
    ordine: int = 0


@router.post("/marketplace/moduli", status_code=201)
async def sa_create_modulo(body: ModuloCatalogoBody, request: Request,
                           user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    from db_models import MarketplaceModule
    existing = await raw_db.marketplace_modules.find_one({"codice": body.codice}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail=f"Modulo con codice {body.codice} già esistente")
    m = MarketplaceModule(**body.model_dump()).model_dump()
    await raw_db.marketplace_modules.insert_one(m)
    m.pop("_id", None)
    await log_action(user=user, action_type="MARKETPLACE_MODULE_CREATED",
                     details=f"Nuovo modulo '{body.nome}' ({body.tipo_modulo}) - €{body.prezzo_eur}/mese",
                     request=request)
    return m


@router.patch("/marketplace/moduli/{modulo_id}")
async def sa_update_modulo(modulo_id: str, body: ModuloCatalogoBody, request: Request,
                           user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    payload = {**body.model_dump(exclude_unset=True), "updated_at": _now_iso()}
    res = await raw_db.marketplace_modules.update_one({"id": modulo_id}, {"$set": payload})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Modulo non trovato")
    await log_action(user=user, action_type="MARKETPLACE_MODULE_CREATED",
                     details=f"Modulo aggiornato: {body.nome}", request=request)
    return await raw_db.marketplace_modules.find_one({"id": modulo_id}, {"_id": 0})


@router.delete("/marketplace/moduli/{modulo_id}")
async def sa_delete_modulo(modulo_id: str, request: Request,
                           user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    m = await raw_db.marketplace_modules.find_one({"id": modulo_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Modulo non trovato")
    # Soft-delete: mark inattivo invece di cancellare (per non rompere le richieste)
    await raw_db.marketplace_modules.update_one({"id": modulo_id},
                                                {"$set": {"attivo": False, "updated_at": _now_iso()}})
    await log_action(user=user, action_type="MARKETPLACE_MODULE_CREATED",
                     details=f"Modulo disattivato: {m.get('nome')}", request=request)
    return {"ok": True}


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
    yousign_workspace_id: Optional[str] = None


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
    # Mappa workspace Yousign per tenant (vive in azienda_config, non in tenants)
    ws_map = {}
    async for cfg in raw_db.azienda_config.find(
            {}, {"_id": 0, "agenzia_tenant_id": 1, "yousign_workspace_id": 1}):
        ws_map[cfg.get("agenzia_tenant_id")] = cfg.get("yousign_workspace_id") or ""
    # Per ogni tenant, aggiungi il conteggio utenti/clienti/polizze (SOLO cifre)
    for t in items:
        t["stats"] = await _tenant_stats(t["id"])
        t["yousign_workspace_id"] = ws_map.get(t["id"], "")
    return items


@router.get("/agenzie/{tid}")
async def get_agenzia(tid: str, user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    t = await raw_db.tenants.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    t["stats"] = await _tenant_stats(tid)
    cfg = await raw_db.azienda_config.find_one(
        {"agenzia_tenant_id": tid}, {"_id": 0, "yousign_workspace_id": 1}) or {}
    t["yousign_workspace_id"] = cfg.get("yousign_workspace_id") or ""
    return t


# ---------------------------------------------------------------------------
# CREDITO OpenAPI per agenzia (prepagato) + listino costi estrazioni
# ---------------------------------------------------------------------------
class CreditoOpenApiBody(BaseModel):
    importo: float
    modo: Literal["set", "add"] = "add"


@router.post("/agenzie/{tid}/openapi-credito")
async def imposta_credito_openapi(tid: str, body: CreditoOpenApiBody,
                                  user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    import openapi_credito as credito
    t = await raw_db.tenants.find_one({"id": tid}, {"_id": 0, "id": 1})
    if not t:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    res = await credito.imposta_credito(tid, body.importo, body.modo, user)
    return res


@router.get("/agenzie/{tid}/openapi-storico")
async def storico_credito_openapi(tid: str, user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    t = await raw_db.tenants.find_one(
        {"id": tid},
        {"_id": 0, "openapi_credito_eur": 1, "openapi_credito_ricariche": 1, "openapi_credito_movimenti": 1},
    )
    if not t:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    ricariche = list(reversed(t.get("openapi_credito_ricariche") or []))
    movimenti = list(reversed(t.get("openapi_credito_movimenti") or []))
    return {
        "credito_eur": t.get("openapi_credito_eur"),
        "ricariche": ricariche,
        "movimenti": movimenti,
        "totale_ricaricato": round(sum(r.get("importo", 0) for r in ricariche if r.get("importo", 0) > 0), 2),
        "totale_consumato": round(sum(-m.get("importo", 0) for m in movimenti if m.get("importo", 0) < 0), 2),
    }


@router.get("/openapi-listino")
async def get_openapi_listino(user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    import openapi_credito as credito
    return {"costi": await credito.get_listino(), "labels": credito.LISTINO_LABELS}


@router.put("/openapi-listino")
async def set_openapi_listino(body: dict, user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    import openapi_credito as credito
    costi = await credito.set_listino(body.get("costi") or {})
    return {"costi": costi, "labels": credito.LISTINO_LABELS}


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

    # Seed conti/banche di default per il nuovo tenant (dropdown pagamenti)
    from db_models import ContoCassa
    for c in [
        {"nome": "Cassa Contanti", "tipo": "cassa", "ordine": 1},
        {"nome": "Assegni", "tipo": "cassa", "ordine": 2},
        {"nome": "Banca", "tipo": "banca", "ordine": 3},
        {"nome": "Pagamento Direzione", "tipo": "rid", "ordine": 4},
    ]:
        doc = ContoCassa(**c).model_dump()
        doc["agenzia_tenant_id"] = tenant["id"]
        await raw_db.conti_cassa.insert_one(doc)

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
            # Invia le CREDENZIALI DI ACCESSO via email (email + password)
            cred_res = await send_agency_credentials(
                to=body.admin_email.lower(),
                name=admin_doc["name"],
                agency_name=tenant["ragione_sociale"],
                login_email=body.admin_email.lower(),
                password=body.admin_password,
            )
            tenant["credenziali_email"] = cred_res.get("status")

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
    # Il workspace Yousign è tenant-scoped e vive in azienda_config, non nel tenant
    workspace_id = payload.pop("yousign_workspace_id", None)
    if workspace_id is not None:
        await raw_db.azienda_config.update_one(
            {"agenzia_tenant_id": tid},
            {"$set": {"yousign_workspace_id": workspace_id.strip(),
                      "agenzia_tenant_id": tid, "updated_at": _now_iso()}},
            upsert=True,
        )
    payload["updated_at"] = _now_iso()
    res = await raw_db.tenants.update_one({"id": tid}, {"$set": payload})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Tenant non trovato")
    await log_action(user=user, action_type="AGENCY_UPDATED",
                     target_agency_id=tid, target_agency_name=await get_agency_name(tid),
                     details=f"Campi aggiornati: {', '.join(list(payload.keys()) + (['yousign_workspace_id'] if workspace_id is not None else []))}",
                     request=request)
    t = await raw_db.tenants.find_one({"id": tid}, {"_id": 0})
    cfg = await raw_db.azienda_config.find_one(
        {"agenzia_tenant_id": tid}, {"_id": 0, "yousign_workspace_id": 1}) or {}
    t["yousign_workspace_id"] = cfg.get("yousign_workspace_id") or ""
    return t


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
# 🔥 RESET DATI TENANT (super-destructive, richiede password custode)
# ---------------------------------------------------------------------------
# Password custode: letta da env (non hardcoded, non esposta al frontend).
_RESET_CUSTODE_PASSWORD = os.environ.get("RESET_CUSTODE_PASSWORD", "")

# Collezioni azzerate dal reset. Manteniamo tenant, users admin, e config di sistema.
_RESET_COLLECTIONS = [
    "anagrafiche", "polizze", "titoli", "sinistri", "movimenti",
    "allegati", "veicoli", "applicazioni", "libro_matricola",
    "diario", "voci_diario", "avvisi", "notifiche",
    "documenti_solleciti", "copilot_sessions", "copilot_messages",
    "activity_log", "attivita",
    "brogliaccio_chiusure", "prima_nota_chiusure",
    "commissioni", "pagamenti_provvigioni", "ritenute",
    "estratti_conto_compagnia", "rimesse_compagnia",
    "whatsapp_instances", "whatsapp_messages",
    "importazioni", "ocr_jobs",
    "asset_immobili",
]


class ResetDatiBody(BaseModel):
    password_custode: str
    mantieni_admin: bool = True   # se True conserva gli utenti admin del tenant (default)
    conferma_ragione_sociale: Optional[str] = None  # doppio-check anti-errore


@router.post("/agenzie/{tid}/reset-dati")
async def reset_dati_tenant(tid: str, body: ResetDatiBody, request: Request,
                            user=Depends(require_user("admin"))) -> dict:
    """🔥 RESET COMPLETO dei dati operativi di un tenant.

    Rimuove: anagrafiche, polizze, titoli, sinistri, movimenti, allegati,
    veicoli, diario, avvisi, brogliaccio, chat AI, ecc.

    NON rimuove: il tenant stesso, la sua configurazione (libreria conti/
    tipi_pagamento/compagnie/collaboratori), gli utenti admin del tenant
    (se mantieni_admin=True).

    SAFETY NET: prima di cancellare crea un dump JSON gzip di tutte le
    collezioni impattate, salvato in /app/backups/{tid}_{timestamp}.json.gz.
    Scaricabile via GET /api/super-admin/backups/{filename}.

    Richiede la password custode (server-side) per prevenire disastri.
    """
    _ensure_super_admin(user)

    if not _RESET_CUSTODE_PASSWORD or body.password_custode != _RESET_CUSTODE_PASSWORD:
        raise HTTPException(status_code=403, detail="Password custode errata")

    if tid == TENANT_PRINCIPALE_ID:
        raise HTTPException(
            status_code=400,
            detail="Tenant principale non resettabile via questa API (usa cleanup manuale)",
        )

    tenant = await raw_db.tenants.find_one({"id": tid}, {"_id": 0, "ragione_sociale": 1})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant non trovato")

    if body.conferma_ragione_sociale:
        if body.conferma_ragione_sociale.strip().lower() != (tenant.get("ragione_sociale") or "").strip().lower():
            raise HTTPException(
                status_code=400,
                detail="Ragione sociale di conferma non corrisponde",
            )

    # ================================================================
    # 🛟 BACKUP JSON GZIP prima del reset
    # ================================================================
    import gzip
    import json as _json
    import os as _os
    from datetime import datetime as _dt
    from bson import ObjectId

    def _json_default(o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, (_dt,)):
            return o.isoformat()
        return str(o)

    backup_dir = "/app/backups"
    _os.makedirs(backup_dir, exist_ok=True)
    timestamp = _dt.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() else "_" for c in (tenant.get("ragione_sociale") or "tenant"))[:40]
    backup_filename = f"reset_{safe_name}_{tid[:8]}_{timestamp}.json.gz"
    backup_path = _os.path.join(backup_dir, backup_filename)
    backup_data: dict = {
        "meta": {
            "tenant_id": tid,
            "ragione_sociale": tenant.get("ragione_sociale"),
            "timestamp": _now_iso(),
            "eseguito_da": user.get("email") or user.get("id"),
            "mantieni_admin": body.mantieni_admin,
        },
        "collections": {},
    }
    for coll_name in _RESET_COLLECTIONS:
        try:
            docs = await raw_db[coll_name].find({"agenzia_tenant_id": tid}, {"_id": 0}).to_list(100000)
            if docs:
                backup_data["collections"][coll_name] = docs
        except Exception:
            pass
    # Aggiungi anche gli utenti che stiamo per cancellare
    if body.mantieni_admin:
        users_filt = {"agenzia_tenant_id": tid, "role": {"$nin": ["admin", "super_admin"]}}
    else:
        users_filt = {"agenzia_tenant_id": tid, "role": {"$ne": "super_admin"}}
    users_bak = await raw_db.users.find(users_filt, {"_id": 0}).to_list(10000)
    if users_bak:
        backup_data["collections"]["users_deleted"] = users_bak
    # Scrivi gzipped JSON
    try:
        with gzip.open(backup_path, "wt", encoding="utf-8") as gz:
            _json.dump(backup_data, gz, ensure_ascii=False, default=_json_default)
        backup_size_kb = round(_os.path.getsize(backup_path) / 1024, 1)
    except Exception as e:
        # Se il backup fallisce ABORT — non procedere col reset
        raise HTTPException(
            status_code=500,
            detail=f"Backup fallito, reset annullato: {e}",
        )

    # ================================================================
    # DELETE
    # ================================================================
    dettaglio: dict[str, int] = {}
    for coll_name in _RESET_COLLECTIONS:
        try:
            res = await raw_db[coll_name].delete_many({"agenzia_tenant_id": tid})
            if res.deleted_count > 0:
                dettaglio[coll_name] = res.deleted_count
        except Exception as e:
            dettaglio[f"{coll_name}_err"] = str(e)[:100]

    res_u = await raw_db.users.delete_many(users_filt)
    if res_u.deleted_count > 0:
        dettaglio["users"] = res_u.deleted_count

    await raw_db.tenants.update_one(
        {"id": tid},
        {"$set": {
            "ultimo_reset_dati": _now_iso(),
            "reset_effettuato_da": user.get("id"),
            "ultimo_backup_reset": backup_filename,
            "updated_at": _now_iso(),
        }},
    )

    await log_action(user=user, action_type="TENANT_DATA_RESET",
                     target_agency_id=tid, target_agency_name=tenant.get("ragione_sociale"),
                     details=f"Reset dati: {sum(v for v in dettaglio.values() if isinstance(v, int))} record eliminati. "
                             f"Backup: {backup_filename} ({backup_size_kb} KB)",
                     request=request)

    return {
        "ok": True,
        "tenant": tenant.get("ragione_sociale"),
        "totale_record_eliminati": sum(v for v in dettaglio.values() if isinstance(v, int)),
        "dettaglio": dettaglio,
        "backup": {
            "filename": backup_filename,
            "size_kb": backup_size_kb,
            "download_url": f"/api/super-admin/backups/{backup_filename}",
        },
    }


class EliminaDefinitivaBody(BaseModel):
    password_custode: str
    conferma_ragione_sociale: str


@router.post("/agenzie/{tid}/elimina-definitiva")
async def elimina_definitiva_tenant(tid: str, body: EliminaDefinitivaBody, request: Request,
                                    user=Depends(require_user("admin"))) -> dict:
    """🗑️ ELIMINAZIONE DEFINITIVA e IRREVERSIBILE di un tenant.

    Rimuove: tutti i dati operativi, la configurazione tenant-scoped, TUTTI gli
    utenti (admin inclusi) e il record del tenant stesso (sparisce dalla lista).
    Prima crea un backup JSON gzip in /app/backups. Richiede password custode +
    conferma della ragione sociale (doppia protezione, come il reset).
    """
    _ensure_super_admin(user)

    if not _RESET_CUSTODE_PASSWORD or body.password_custode != _RESET_CUSTODE_PASSWORD:
        raise HTTPException(status_code=403, detail="Password custode errata")

    if tid in (TENANT_PRINCIPALE_ID, TENANT_DEMO_ID, TENANT_CLEAN_ID):
        raise HTTPException(status_code=400, detail="Tenant di sistema non eliminabile")

    tenant = await raw_db.tenants.find_one({"id": tid}, {"_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant non trovato")

    if body.conferma_ragione_sociale.strip().lower() != (tenant.get("ragione_sociale") or "").strip().lower():
        raise HTTPException(status_code=400, detail="Ragione sociale di conferma non corrisponde")

    # ---- Backup completo (dati + tutti gli utenti + record tenant) ----
    import gzip
    import json as _json
    import os as _os
    from datetime import datetime as _dt
    from bson import ObjectId

    def _json_default(o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, _dt):
            return o.isoformat()
        return str(o)

    backup_dir = "/app/backups"
    _os.makedirs(backup_dir, exist_ok=True)
    timestamp = _dt.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() else "_" for c in (tenant.get("ragione_sociale") or "tenant"))[:40]
    backup_filename = f"elimina_{safe_name}_{tid[:8]}_{timestamp}.json.gz"
    backup_path = _os.path.join(backup_dir, backup_filename)
    backup_data: dict = {
        "meta": {"tenant_id": tid, "ragione_sociale": tenant.get("ragione_sociale"),
                 "timestamp": _now_iso(), "eseguito_da": user.get("email") or user.get("id"),
                 "tipo": "elimina_definitiva"},
        "tenant": tenant,
        "collections": {},
    }
    for coll_name in _RESET_COLLECTIONS:
        try:
            docs = await raw_db[coll_name].find({"agenzia_tenant_id": tid}, {"_id": 0}).to_list(100000)
            if docs:
                backup_data["collections"][coll_name] = docs
        except Exception:
            pass
    users_bak = await raw_db.users.find({"agenzia_tenant_id": tid, "role": {"$ne": "super_admin"}}, {"_id": 0}).to_list(10000)
    if users_bak:
        backup_data["collections"]["users_deleted"] = users_bak
    try:
        with gzip.open(backup_path, "wt", encoding="utf-8") as gz:
            _json.dump(backup_data, gz, ensure_ascii=False, default=_json_default)
        backup_size_kb = round(_os.path.getsize(backup_path) / 1024, 1)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup fallito, eliminazione annullata: {e}")

    # ---- DELETE definitivo ----
    dettaglio: dict[str, int] = {}
    for coll_name in _RESET_COLLECTIONS:
        try:
            res = await raw_db[coll_name].delete_many({"agenzia_tenant_id": tid})
            if res.deleted_count > 0:
                dettaglio[coll_name] = res.deleted_count
        except Exception as e:
            dettaglio[f"{coll_name}_err"] = str(e)[:100]
    # Config tenant-scoped extra + utenti (TUTTI, admin inclusi) + record tenant
    for extra_coll in ("azienda_config", "conti", "compagnie", "agenzie", "tipi_pagamento", "modelli", "mup_modelli"):
        try:
            res = await raw_db[extra_coll].delete_many({"agenzia_tenant_id": tid})
            if res.deleted_count > 0:
                dettaglio[extra_coll] = res.deleted_count
        except Exception:
            pass
    res_u = await raw_db.users.delete_many({"agenzia_tenant_id": tid, "role": {"$ne": "super_admin"}})
    if res_u.deleted_count > 0:
        dettaglio["users"] = res_u.deleted_count
    await raw_db.tenants.delete_one({"id": tid})
    dettaglio["tenant"] = 1

    await log_action(user=user, action_type="TENANT_DELETED_PERMANENTLY",
                     target_agency_id=tid, target_agency_name=tenant.get("ragione_sociale"),
                     details=f"Eliminazione definitiva: {sum(v for v in dettaglio.values() if isinstance(v, int))} record. Backup: {backup_filename} ({backup_size_kb} KB)",
                     request=request)

    return {
        "ok": True,
        "tenant": tenant.get("ragione_sociale"),
        "totale_record_eliminati": sum(v for v in dettaglio.values() if isinstance(v, int)),
        "dettaglio": dettaglio,
        "backup": {"filename": backup_filename, "size_kb": backup_size_kb,
                   "download_url": f"/api/super-admin/backups/{backup_filename}"},
    }


@router.get("/backups")
async def list_backups(user=Depends(require_user("admin"))) -> list[dict]:
    """Lista tutti i backup di reset disponibili sul server."""
    _ensure_super_admin(user)
    import os as _os
    backup_dir = "/app/backups"
    if not _os.path.exists(backup_dir):
        return []
    files = []
    for fn in sorted(_os.listdir(backup_dir), reverse=True):
        if fn.endswith(".json.gz"):
            fp = _os.path.join(backup_dir, fn)
            st = _os.stat(fp)
            files.append({
                "filename": fn,
                "size_kb": round(st.st_size / 1024, 1),
                "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "download_url": f"/api/super-admin/backups/{fn}",
            })
    return files


@router.get("/backups/{filename}")
async def download_backup(filename: str, user=Depends(require_user("admin"))):
    """Scarica un backup gzipped."""
    from fastapi.responses import FileResponse
    _ensure_super_admin(user)
    import os as _os
    # Guardia path traversal
    if "/" in filename or ".." in filename or not filename.endswith(".json.gz"):
        raise HTTPException(status_code=400, detail="Nome file non valido")
    fp = _os.path.join("/app/backups", filename)
    if not _os.path.exists(fp):
        raise HTTPException(status_code=404, detail="Backup non trovato")
    return FileResponse(fp, media_type="application/gzip", filename=filename)


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


# ============================================================
# DOMINI AGENZIA — sottodominio e credenziali dedicate
# ============================================================
class DominioBody(BaseModel):
    sottodominio: str
    attivo: bool = True


@router.post("/agenzie/{tid}/dominio")
async def imposta_dominio(tid: str, body: DominioBody, request: Request,
                          user=Depends(require_user("admin"))) -> dict:
    """Attiva/aggiorna il sottodominio dedicato dell'agenzia."""
    _ensure_super_admin(user)
    import re as _re
    slug = (body.sottodominio or "").strip().lower()
    if not _re.fullmatch(r"[a-z0-9][a-z0-9-]{1,38}[a-z0-9]", slug):
        raise HTTPException(400, "Sottodominio non valido: usa 3-40 caratteri (lettere, numeri, trattini)")
    t = await raw_db.tenants.find_one({"id": tid}, {"_id": 0, "id": 1, "ragione_sociale": 1})
    if not t:
        raise HTTPException(404, "Tenant non trovato")
    dup = await raw_db.tenants.find_one({"sottodominio": slug, "id": {"$ne": tid}}, {"_id": 1})
    if dup:
        raise HTTPException(409, f"Sottodominio '{slug}' già assegnato ad un'altra agenzia")
    await raw_db.tenants.update_one({"id": tid}, {"$set": {
        "sottodominio": slug, "dominio_attivo": bool(body.attivo), "updated_at": _now_iso()}})
    base = os.environ.get("BASE_APP_DOMAIN") or (request.headers.get("host") or "").split(":")[0]
    url = f"https://{slug}.{base}" if base else f"https://{slug}.tuodominio.it"
    await log_action(user=user, action_type="DOMAIN_SET", target_agency_id=tid,
                     target_agency_name=t["ragione_sociale"],
                     details=f"Sottodominio: {slug} (attivo={body.attivo})", request=request)
    return {"ok": True, "sottodominio": slug, "dominio_attivo": bool(body.attivo), "url": url}


class CredenzialiBody(BaseModel):
    email: str
    name: Optional[str] = None
    role: str = "admin"


@router.post("/agenzie/{tid}/credenziali")
async def crea_credenziali(tid: str, body: CredenzialiBody, request: Request,
                           user=Depends(require_user("admin"))) -> dict:
    """Crea (o resetta) le credenziali dedicate per l'agenzia.
    La password generata viene mostrata UNA SOLA volta."""
    _ensure_super_admin(user)
    import secrets as _secrets
    import uuid as _uuid
    from auth import hash_password
    t = await raw_db.tenants.find_one({"id": tid}, {"_id": 0, "id": 1, "ragione_sociale": 1})
    if not t:
        raise HTTPException(404, "Tenant non trovato")
    email = body.email.lower().strip()
    if "@" not in email:
        raise HTTPException(400, "Email non valida")
    role = body.role if body.role in ("admin", "collaboratore", "dipendente") else "admin"
    password = _secrets.token_urlsafe(9)
    existing = await raw_db.users.find_one({"email": email}, {"_id": 0, "id": 1, "agenzia_tenant_id": 1})
    if existing:
        if existing.get("agenzia_tenant_id") not in (None, tid):
            raise HTTPException(409, "Email già usata da un utente di un'altra agenzia")
        await raw_db.users.update_one({"email": email}, {"$set": {
            "password_hash": hash_password(password), "role": role, "attivo": True,
            "agenzia_tenant_id": tid, "updated_at": _now_iso()}})
        azione = "reset"
    else:
        await raw_db.users.insert_one({
            "id": str(_uuid.uuid4()), "email": email,
            "name": body.name or t["ragione_sociale"],
            "role": role, "attivo": True, "is_super_admin": False,
            "agenzia_tenant_id": tid,
            "password_hash": hash_password(password),
            "created_at": _now_iso(), "updated_at": _now_iso(),
        })
        azione = "creato"
    await log_action(user=user, action_type="CREDENTIALS_ISSUED", target_agency_id=tid,
                     target_agency_name=t["ragione_sociale"],
                     details=f"Credenziali {azione} per {email} (role={role})", request=request)
    return {"ok": True, "email": email, "password": password, "azione": azione, "role": role}


@router.get("/agenzie/{tid}/utenti")
async def utenti_agenzia(tid: str, user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    return await raw_db.users.find(
        {"agenzia_tenant_id": tid},
        {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1, "attivo": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(200)


# ============================================================
# SCAMBIO CONTROLLATO — console approvazione scambi dati
# ============================================================
@router.get("/scambi")
async def lista_scambi(user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    items = await raw_db.scambi_richieste.find({}, {"_id": 0}).sort("richiesto_at", -1).to_list(300)
    tids = {i.get("agenzia_richiedente_id") for i in items} | {i.get("agenzia_sorgente_id") for i in items}
    nomi = {t["id"]: t["ragione_sociale"] async for t in raw_db.tenants.find(
        {"id": {"$in": [t for t in tids if t]}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    for i in items:
        i["agenzia_richiedente_nome"] = nomi.get(i.get("agenzia_richiedente_id"), i.get("agenzia_richiedente_id"))
        i["agenzia_sorgente_nome"] = nomi.get(i.get("agenzia_sorgente_id"), i.get("agenzia_sorgente_id"))
    return items


@router.post("/scambi/{rid}/approva")
async def approva_scambio(rid: str, request: Request,
                          user=Depends(require_user("admin"))) -> dict:
    """Approva ed esegue subito lo scambio dati richiesto da un'agenzia."""
    _ensure_super_admin(user)
    r = await raw_db.scambi_richieste.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Richiesta non trovata")
    if r.get("stato") != "in_attesa":
        raise HTTPException(400, f"Richiesta già {r.get('stato')}")
    from routes.setup_scambio import ScambioBody, esegui_scambio_core
    body = ScambioBody(
        agenzia_sorgente_id=r["agenzia_sorgente_id"],
        operatore_email=r["operatore_email"],
        importa_anagrafiche=r.get("importa_anagrafiche", True),
        importa_polizze=r.get("importa_polizze", True),
        importa_titoli=r.get("importa_titoli", True),
        importa_sinistri=r.get("importa_sinistri", True),
        importa_documenti=r.get("importa_documenti", True),
    )
    try:
        risultato = await esegui_scambio_core(body, r["richiesto_da_user_id"])
    except HTTPException as e:
        await raw_db.scambi_richieste.update_one({"id": rid}, {"$set": {
            "stato": "errore", "deciso_da": user.get("email"), "deciso_at": _now_iso(),
            "motivo_rifiuto": f"Errore esecuzione: {e.detail}"}})
        raise
    await raw_db.scambi_richieste.update_one({"id": rid}, {"$set": {
        "stato": "eseguito", "deciso_da": user.get("email"),
        "deciso_at": _now_iso(), "risultato": risultato}})
    await log_action(user=user, action_type="EXCHANGE_APPROVED",
                     target_agency_id=r.get("agenzia_richiedente_id"),
                     target_agency_name=await get_agency_name(r.get("agenzia_richiedente_id")),
                     details=f"Scambio approvato ed eseguito (operatore {r['operatore_email']}): {risultato}",
                     request=request)
    return {"ok": True, "risultato": risultato}


class RifiutoBody(BaseModel):
    motivo: Optional[str] = None


@router.post("/scambi/{rid}/rifiuta")
async def rifiuta_scambio(rid: str, body: RifiutoBody, request: Request,
                          user=Depends(require_user("admin"))) -> dict:
    _ensure_super_admin(user)
    r = await raw_db.scambi_richieste.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Richiesta non trovata")
    if r.get("stato") != "in_attesa":
        raise HTTPException(400, f"Richiesta già {r.get('stato')}")
    await raw_db.scambi_richieste.update_one({"id": rid}, {"$set": {
        "stato": "rifiutato", "deciso_da": user.get("email"),
        "deciso_at": _now_iso(), "motivo_rifiuto": body.motivo or ""}})
    await log_action(user=user, action_type="EXCHANGE_REJECTED",
                     target_agency_id=r.get("agenzia_richiedente_id"),
                     target_agency_name=await get_agency_name(r.get("agenzia_richiedente_id")),
                     details=f"Scambio rifiutato: {body.motivo or 'senza motivo'}", request=request)
    return {"ok": True}
