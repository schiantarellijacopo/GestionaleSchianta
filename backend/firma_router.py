"""Router firma elettronica.

Endpoint (tutti sotto /api/firma):
- POST /firma/richieste           crea envelope + salva firma_requests
- GET  /firma/richieste           lista firme in corso / storico (con filtri)
- GET  /firma/richieste/{id}      dettaglio + refresh status da provider
- POST /firma/richieste/{id}/scarica  scarica PDF firmato → allegato
- POST /firma/webhook             callback Namirial (dedup + async processing)
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form

import firma_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/firma", tags=["firma"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/richieste")
async def crea_firma(
    file: UploadFile = File(...),
    modalita: str = Form(...),
    firmatario_id: str = Form(...),  # anagrafica id
    polizza_id: Optional[str] = Form(None),
    display_name: str = Form("Documento da firmare"),
):
    """Crea una richiesta firma. modalita ∈ otp_sms/otp_email/biometric/simple/link."""
    from server import db, require_user  # circular-import safe
    # Autenticazione via dependency risolta a runtime — semplifichiamo con lookup manuale
    if not await firma_provider.is_configured():
        raise HTTPException(400, "Provider firma non configurato — vai in Librerie → Firme")

    ana = await db.anagrafiche.find_one({"id": firmatario_id}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica firmatario non trovata")
    signer = {
        "nome": ana.get("nome") or "",
        "cognome": ana.get("cognome") or "",
        "email": ana.get("email") or "",
        "cellulare": ana.get("cellulare") or "",
        "codice_fiscale": ana.get("codice_fiscale") or "",
    }
    if modalita in ("otp_sms",) and not signer["cellulare"]:
        raise HTTPException(400, "Cellulare obbligatorio per OTP SMS")
    if modalita in ("otp_email", "simple", "link") and not signer["email"]:
        raise HTTPException(400, "Email obbligatoria per questa modalità")

    import os
    base = (os.environ.get("BACKEND_PUBLIC_URL") or os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if not base:
        base = "http://localhost:8001"
    callback_url = f"{base}/api/firma/webhook"

    data = await file.read()
    if not data:
        raise HTTPException(400, "PDF vuoto")

    res = await firma_provider.create_envelope(
        pdf_bytes=data,
        filename=file.filename or "documento.pdf",
        signer=signer,
        mode=modalita,
        callback_url=callback_url,
        display_name=display_name,
    )
    if not res.get("ok"):
        raise HTTPException(502, res.get("error") or "Errore provider")

    doc = {
        "id": str(uuid.uuid4()),
        "envelope_id": res["envelope_id"],
        "provider": "namirial",
        "modalita": modalita,
        "firmatario_id": firmatario_id,
        "firmatario_nome": (
            ana.get("ragione_sociale")
            or f"{ana.get('cognome','')} {ana.get('nome','')}".strip()
        ),
        "polizza_id": polizza_id,
        "display_name": display_name,
        "filename": file.filename,
        "stato": "sent",
        "viewer_links": res.get("viewer_links"),
        "tenant_id": ana.get("tenant_id"),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.firma_requests.insert_one(doc)
    doc.pop("_id", None)

    # Se link/simple/otp_email → invia link via nostri canali (Email + WA se disponibile)
    signing_url = None
    vl = res.get("viewer_links") or {}
    links_list = vl.get("ViewerLinks") or (vl if isinstance(vl, list) else [])
    if links_list:
        first = links_list[0] if isinstance(links_list, list) else links_list
        signing_url = first.get("ViewerLink") or first.get("WorkstepRedirectionUrl")
    if signing_url and modalita in ("simple", "link", "otp_email"):
        oggetto = f"Documento da firmare — {display_name}"
        corpo = (
            f"Gentile {signer['cognome']} {signer['nome']},\n\n"
            f"le è stato inviato un documento da firmare digitalmente.\n\n"
            f"🔗 Firma qui: {signing_url}\n\n"
            f"Il link è personale e ha scadenza limitata."
        )
        try:
            from notification_helpers import send_email, send_whatsapp_message
            if signer["email"]:
                await send_email(signer["email"], oggetto, corpo)
            if signer["cellulare"]:
                await send_whatsapp_message(signer["cellulare"], corpo)
        except Exception as e:
            logger.warning("Invio notifica firma fallito: %s", e)

    return {**doc, "signing_url": signing_url}


@router.get("/richieste")
async def list_firme(
    stato: Optional[str] = None,
    firmatario_id: Optional[str] = None,
    polizza_id: Optional[str] = None,
    limit: int = 200,
):
    from server import db
    flt: dict = {}
    if stato:
        flt["stato"] = stato
    if firmatario_id:
        flt["firmatario_id"] = firmatario_id
    if polizza_id:
        flt["polizza_id"] = polizza_id
    items = await db.firma_requests.find(flt, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return items


@router.get("/richieste/{req_id}")
async def get_firma(req_id: str, refresh: bool = False):
    from server import db
    doc = await db.firma_requests.find_one({"id": req_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Richiesta non trovata")
    if refresh and doc.get("envelope_id"):
        r = await firma_provider.get_status(doc["envelope_id"])
        if r.get("ok"):
            new_state = _map_provider_status(r["data"].get("Status") or "")
            await db.firma_requests.update_one(
                {"id": req_id},
                {"$set": {"stato": new_state, "provider_status": r["data"].get("Status"),
                          "updated_at": _now_iso()}},
            )
            doc["stato"] = new_state
            doc["provider_status"] = r["data"].get("Status")
    return doc


@router.post("/richieste/{req_id}/scarica")
async def scarica_firmato(req_id: str):
    """Scarica il PDF firmato + audit e lo allega come `allegato` visibile al cliente."""
    from server import db, Allegato, obj_storage
    doc = await db.firma_requests.find_one({"id": req_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Richiesta non trovata")
    if not doc.get("envelope_id"):
        raise HTTPException(400, "Envelope mancante")

    r = await firma_provider.download_signed_pdf(doc["envelope_id"])
    if not r.get("ok"):
        raise HTTPException(502, r.get("error") or "Errore download")

    import os as _os
    stored: list[dict] = []
    for kind, ct in (("signed_pdf", "application/pdf"),
                       ("audit_pdf", "application/pdf"),
                       ("audit_xml", "application/xml")):
        if kind not in r:
            continue
        data: bytes = r[kind]
        ext = "pdf" if ct == "application/pdf" else "xml"
        file_id = str(uuid.uuid4())
        path = f"{_os.environ.get('APP_NAME', 'assicura')}/firme/{doc['id']}/{kind}_{file_id}.{ext}"
        try:
            up = obj_storage.put_object(path, data, ct)
        except Exception as e:
            logger.warning("Storage put_object fallito: %s", e)
            continue
        nome_file = f"{kind.replace('_', '-')}.{ext}"
        # link a polizza se presente, altrimenti alla anagrafica
        entita_tipo = "polizza" if doc.get("polizza_id") else "anagrafica"
        entita_id = doc.get("polizza_id") or doc.get("firmatario_id")
        al = Allegato(
            entita_tipo=entita_tipo, entita_id=entita_id,
            nome_file=nome_file, storage_path=up["path"],
            content_type=ct, size=up.get("size", len(data)),
            descrizione=f"Firma Namirial — {kind}",
            visibile_cliente=(kind == "signed_pdf"),
            categoria="firma_namirial",
        )
        rec = al.model_dump()
        rec["firma_request_id"] = doc["id"]
        await db.allegati.insert_one(rec)
        stored.append({"kind": kind, "allegato_id": al.id, "nome_file": nome_file})

    await db.firma_requests.update_one(
        {"id": req_id},
        {"$set": {"stato": "attached", "downloaded_at": _now_iso(),
                  "allegati": stored, "updated_at": _now_iso()}},
    )
    return {"ok": True, "allegati": stored}


@router.post("/webhook")
async def firma_webhook(request: Request):
    """Webhook Namirial: dedup event → refresh stato → auto-download se completato."""
    from server import db
    raw = await request.body()
    sig = (
        request.headers.get("X-Namirial-Signature")
        or request.headers.get("Signature")
        or request.headers.get("X-Signature")
    )
    if not await firma_provider.verify_webhook_signature(raw, sig):
        raise HTTPException(401, "Firma webhook non valida")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(400, "JSON invalido")

    # Dedup
    import hashlib
    event_id = hashlib.sha256(raw).hexdigest()
    if await db.firma_webhook_events.find_one({"id": event_id}, {"_id": 0, "id": 1}):
        return {"ok": True, "duplicate": True}
    await db.firma_webhook_events.insert_one({"id": event_id, "received_at": _now_iso(),
                                                 "payload": event})

    envelope_id = event.get("EnvelopeId") or event.get("envelopeId")
    if not envelope_id:
        return {"ok": True, "warning": "missing envelope_id"}

    doc = await db.firma_requests.find_one({"envelope_id": envelope_id}, {"_id": 0})
    if not doc:
        return {"ok": True, "warning": "envelope non tracciato"}

    # Refresh stato ufficiale (non fidarsi solo del body)
    r = await firma_provider.get_status(envelope_id)
    if r.get("ok"):
        provider_status = (r["data"].get("Status") or "").lower()
        new_state = _map_provider_status(provider_status)
        await db.firma_requests.update_one(
            {"envelope_id": envelope_id},
            {"$set": {"stato": new_state, "provider_status": provider_status,
                      "updated_at": _now_iso()}},
        )
        # Se completato → auto-download come allegato
        if new_state == "signed" and doc.get("stato") != "attached":
            try:
                # richiama internamente la stessa logica
                await scarica_firmato(doc["id"])
            except Exception as e:
                logger.warning("Auto-download post-webhook fallito: %s", e)
    return {"ok": True}


def _map_provider_status(s: str) -> str:
    """Mappa gli stati Namirial sui nostri stati interni."""
    s = (s or "").lower()
    if s in ("completed", "signed", "finished"):
        return "signed"
    if s in ("expired", "cancelled", "canceled", "rejected", "declined"):
        return "expired" if s == "expired" else "rejected"
    if s in ("started", "inprogress", "in_progress", "viewed", "opened"):
        return "viewed"
    return "sent"
