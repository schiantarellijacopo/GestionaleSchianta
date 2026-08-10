"""Solleciti multi-canale per documenti veicolo mancanti.

Gestisce il ciclo di sollecito automatico per applicazioni libro matricola
cessate (venduta/demolita/esportata) senza il relativo atto ufficiale caricato.

Ogni sollecito include un LINK PUBBLICO firmato con JWT che permette al cliente
di caricare il documento direttamente dal proprio smartphone senza login.
Il ciclo si chiude automaticamente all'atto del caricamento.

Endpoints pubblici (unauthenticated):
  * GET  /api/public/upload-doc/info?token=…       → info sulla pratica
  * POST /api/public/upload-doc/veicolo?token=…    → upload file (multipart)

Handler scheduler (chiamato dal preset alert_presets con schedule_kind
"documento_veicolo_mancante"):
  * run_sollecito_documento_veicolo(preset_rule, db)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query

router_public = APIRouter(prefix="/api/public/upload-doc", tags=["public-upload"])

JWT_ALG = "HS256"
TOKEN_TTL_DAYS = 14

# ─── Mappa motivo cessazione → categoria doc obbligatoria ─────────────
MOTIVI_CATEGORIE = {
    "venduta":         "atto_vendita",
    "demolita":        "certificato_demolizione",
    "esportata":       "documento_esportazione",
    "sostituita":      "atto_vendita",
    "cessata_leasing": "cessazione_leasing",
}


def _secret() -> str:
    return os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY") or "changeme"


def build_upload_token(applicazione_id: str, tenant_id: Optional[str] = None) -> str:
    """Firma un token JWT per il link di upload pubblico."""
    payload = {
        "aid": applicazione_id,
        "tid": tenant_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS),
        "sub": "upload_doc_veicolo",
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALG)


def build_upload_link(applicazione_id: str, tenant_id: Optional[str] = None,
                       base_url: Optional[str] = None) -> str:
    """Ritorna un URL pubblico da mettere nel messaggio di sollecito."""
    tok = build_upload_token(applicazione_id, tenant_id)
    base = base_url or os.environ.get("PUBLIC_BASE_URL") or ""
    return f"{base.rstrip('/')}/upload-doc?token={tok}"


def _decode_token(token: str) -> dict:
    try:
        p = jwt.decode(token, _secret(), algorithms=[JWT_ALG])
        if p.get("sub") != "upload_doc_veicolo":
            raise ValueError("bad subject")
        return p
    except Exception as e:
        raise HTTPException(401, f"Token non valido o scaduto: {e}")


# ============================================================
# ENDPOINTS PUBBLICI
# ============================================================
@router_public.get("/info")
async def upload_info(token: str = Query(...)):
    """Ritorna info sulla pratica per costruire la landing page (senza auth)."""
    from server import db  # lazy import per evitare cicli
    p = _decode_token(token)
    aid = p["aid"]
    app = await db.applicazioni.find_one(
        {"id": aid}, {"_id": 0, "id": 1, "targa": 1, "tipo_cessazione": 1,
                     "data_esclusione": 1, "data_cessazione": 1,
                     "intestatario": 1, "polizza_id": 1},
    )
    if not app:
        raise HTTPException(404, "Pratica non trovata")
    # Controlla se già caricato
    cat = MOTIVI_CATEGORIE.get(app.get("tipo_cessazione") or "sostituita", "atto_vendita")
    already = await db.allegati.find_one({
        "applicazione_matricola_id": aid,
        "categoria": cat,
        "is_deleted": {"$ne": True},
    }, {"_id": 0, "id": 1})
    pol = await db.polizze.find_one({"id": app["polizza_id"]},
                                     {"_id": 0, "numero_polizza": 1}) if app.get("polizza_id") else None
    return {
        "targa": app.get("targa"),
        "tipo_cessazione": app.get("tipo_cessazione"),
        "data_cessazione": app.get("data_esclusione") or app.get("data_cessazione"),
        "intestatario": app.get("intestatario"),
        "polizza_numero": (pol or {}).get("numero_polizza"),
        "categoria_richiesta": cat,
        "gia_caricato": bool(already),
    }


@router_public.post("/veicolo")
async def upload_doc_veicolo(
    token: str = Form(...),
    file: UploadFile = File(...),
):
    """Riceve il file caricato dal cliente dal link di sollecito.
    Crea un allegato con `applicazione_matricola_id` popolato + categoria
    corretta (atto_vendita/certificato_demolizione/documento_esportazione).
    Il caricamento chiude automaticamente il ciclo di solleciti.
    """
    from server import db
    p = _decode_token(token)
    aid = p["aid"]
    tenant_id = p.get("tid")

    app = await db.applicazioni.find_one({"id": aid}, {"_id": 0, "id": 1, "tipo_cessazione": 1,
                                                        "polizza_id": 1, "targa": 1})
    if not app:
        raise HTTPException(404, "Pratica non trovata")

    categoria = MOTIVI_CATEGORIE.get(app.get("tipo_cessazione") or "sostituita", "atto_vendita")

    # Salva file (usa storage locale, semplice - lo scanner OCR usa lo stesso pattern)
    storage_root = os.environ.get("STORAGE_ROOT", "/data/uploads")
    os.makedirs(storage_root, exist_ok=True)
    ext = (file.filename or "").split(".")[-1].lower() if file.filename else "bin"
    fname = f"{uuid.uuid4()}.{ext}"
    fpath = os.path.join(storage_root, fname)
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "File troppo grande (>15 MB)")
    with open(fpath, "wb") as f:
        f.write(content)

    allegato = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "entita_tipo": "polizza",
        "entita_id": app["polizza_id"],
        "applicazione_matricola_id": aid,
        "categoria": categoria,
        "nome_file": file.filename or fname,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "storage_path": fpath,
        "descrizione": f"Caricato dal cliente via link pubblico ({categoria})",
        "fonte": "public_upload_client",
        "visibile_cliente": True,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.allegati.insert_one(allegato)

    # Chiude automaticamente i solleciti pendenti per questa applicazione
    await db.solleciti_documento_veicolo.update_many(
        {"applicazione_id": aid, "stato": {"$ne": "chiuso"}},
        {"$set": {"stato": "chiuso",
                  "chiuso_il": datetime.now(timezone.utc).isoformat(),
                  "chiuso_da": "upload_cliente_public"}},
    )

    return {
        "ok": True,
        "allegato_id": allegato["id"],
        "categoria": categoria,
        "targa": app.get("targa"),
        "messaggio": "Documento caricato correttamente. Grazie!",
    }


# ============================================================
# HANDLER SCHEDULER (chiamato dai preset alert_presets)
# ============================================================
async def run_sollecito_documento_veicolo(rule: dict, db) -> dict:
    """Handler per lo scheduler dei solleciti documento veicolo mancante.

    Chiamato dal dispatcher con il `rule` (preset) attivo per un tenant.
    Ritorna statistiche di quanti solleciti inviati.

    Il preset ha:
      - soglia_giorni (3/5/7)
      - canali (email, whatsapp, sms, inapp)
      - template_oggetto / template_corpo
    """
    from datetime import date
    soglia = int(rule.get("soglia_giorni") or 3)
    canali = rule.get("canali") or ["email"]
    tenant_id = rule.get("tenant_id")
    limite_data = (date.today() - timedelta(days=soglia)).isoformat()

    # Trova applicazioni cessate senza atto e con giorni sufficienti
    flt = {
        "stato": {"$in": ["annullata", "sostituita"]},
        "tipo_cessazione": {"$in": list(MOTIVI_CATEGORIE.keys())},
        "$or": [
            {"data_esclusione": {"$lte": limite_data}},
            {"data_cessazione": {"$lte": limite_data}},
        ],
    }
    if tenant_id:
        flt["tenant_id"] = tenant_id

    inviati = 0
    saltati_ok = 0
    async for app in db.applicazioni.find(flt, {"_id": 0}):
        cat = MOTIVI_CATEGORIE.get(app.get("tipo_cessazione") or "sostituita", "atto_vendita")
        # Ha già l'atto?
        has_atto = await db.allegati.find_one({
            "applicazione_matricola_id": app["id"],
            "categoria": cat,
            "is_deleted": {"$ne": True},
        }, {"_id": 0, "id": 1})
        if has_atto:
            saltati_ok += 1
            continue

        # Contraente della polizza per contatti
        pol = await db.polizze.find_one(
            {"id": app["polizza_id"]},
            {"_id": 0, "contraente_id": 1, "numero_polizza": 1}) if app.get("polizza_id") else None
        if not pol:
            continue
        ana = await db.anagrafiche.find_one(
            {"id": pol.get("contraente_id")},
            {"_id": 0, "email": 1, "cellulare": 1, "cognome_nome": 1,
             "ragione_sociale": 1, "cognome": 1, "nome": 1}) if pol.get("contraente_id") else None
        if not ana:
            continue

        upload_link = build_upload_link(app["id"], tenant_id=tenant_id)
        cliente_nome = ana.get("ragione_sociale") or ana.get("cognome_nome") \
                       or f"{ana.get('cognome','')} {ana.get('nome','')}".strip() or "Cliente"

        # Sostituzione variabili nel template
        subst = {
            "{cliente_nome}":    cliente_nome,
            "{targa}":           app.get("targa") or "",
            "{tipo_cessazione}": (app.get("tipo_cessazione") or "").replace("_", " ").upper(),
            "{data_cessazione}": app.get("data_esclusione") or app.get("data_cessazione") or "",
            "{numero_polizza}":  pol.get("numero_polizza") or "",
            "{upload_link}":     upload_link,
        }
        oggetto = rule.get("template_oggetto") or "Documento veicolo mancante"
        corpo = rule.get("template_corpo") or "Manca il documento del veicolo {targa}. Carica qui: {upload_link}"
        for k, v in subst.items():
            oggetto = oggetto.replace(k, v)
            corpo = corpo.replace(k, v)

        # Registra il sollecito nel log
        sollecito_id = str(uuid.uuid4())
        await db.solleciti_documento_veicolo.insert_one({
            "id": sollecito_id,
            "tenant_id": tenant_id,
            "applicazione_id": app["id"],
            "targa": app.get("targa"),
            "canali_inviati": canali,
            "destinatario_email": ana.get("email"),
            "destinatario_cellulare": ana.get("cellulare"),
            "oggetto": oggetto,
            "corpo": corpo,
            "upload_link": upload_link,
            "soglia_giorni": soglia,
            "stato": "inviato",
            "inviato_il": datetime.now(timezone.utc).isoformat(),
        })

        # Invio effettivo via canali (delega ai worker esistenti se disponibili)
        try:
            if "email" in canali and ana.get("email"):
                from notification_helpers import send_email
                await send_email(ana["email"], oggetto, corpo, tenant_id=tenant_id)
            if "whatsapp" in canali and ana.get("cellulare"):
                from notification_helpers import send_whatsapp_message
                await send_whatsapp_message(ana["cellulare"], corpo, tenant_id=tenant_id)
            # SMS: se non c'è ancora un provider, lascio placeholder
        except Exception:
            pass  # errori di invio già loggati dai singoli helper
        inviati += 1

    return {
        "preset_key": rule.get("preset_key"),
        "soglia_giorni": soglia,
        "solleciti_inviati": inviati,
        "gia_ok": saltati_ok,
    }
