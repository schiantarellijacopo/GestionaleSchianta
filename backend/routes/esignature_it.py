"""Router Firma Elettronica via OpenAPI.it eSignature (EU-AES, OTP SMS).

Flusso:
  POST /api/esignature/invia            → crea richiesta da un allegato PDF esistente,
                                           invia link firma via WhatsApp/Email
  GET  /api/esignature/richieste        → lista richieste per una entità (badge stato)
  GET  /api/esignature/stato/{req_id}   → aggiorna stato e, se firmato, salva il PDF
                                           firmato nella STESSA sezione/categoria del doc
  POST /api/esignature/finalizza-pending→ (interno/scheduler) finalizza le firme completate
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import current_user
from database import db
from db_models import Allegato, _now_iso
import storage as obj_storage
import esignature_openapi as esvc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/esignature", tags=["esignature"])


async def _resolve_signer(entita_tipo: str, entita_id: str) -> dict:
    """Ricava il firmatario (contraente) da polizza/sinistro/anagrafica."""
    ana = None
    if entita_tipo == "anagrafica":
        ana = await db.anagrafiche.find_one({"id": entita_id}, {"_id": 0})
    elif entita_tipo == "polizza":
        pol = await db.polizze.find_one({"id": entita_id}, {"_id": 0, "contraente_id": 1})
        if pol and pol.get("contraente_id"):
            ana = await db.anagrafiche.find_one({"id": pol["contraente_id"]}, {"_id": 0})
    elif entita_tipo == "sinistro":
        sin = await db.sinistri.find_one({"id": entita_id}, {"_id": 0, "contraente_id": 1, "polizza_id": 1})
        cid = (sin or {}).get("contraente_id")
        if not cid and (sin or {}).get("polizza_id"):
            pol = await db.polizze.find_one({"id": sin["polizza_id"]}, {"_id": 0, "contraente_id": 1})
            cid = (pol or {}).get("contraente_id")
        if cid:
            ana = await db.anagrafiche.find_one({"id": cid}, {"_id": 0})
    if not ana:
        return {}
    return {
        "anagrafica_id": ana.get("id"),
        "name": ana.get("nome") or "",
        "surname": ana.get("cognome") or "",
        # per persona giuridica usiamo la ragione sociale come "surname"
        "ragione_sociale": ana.get("ragione_sociale"),
        "email": ana.get("email") or "",
        "mobile": ana.get("cellulare") or ana.get("telefono") or "",
    }


@router.post("/invia")
async def invia_per_firma(body: dict, user=Depends(current_user)) -> dict:
    """Invia un allegato PDF esistente per la firma FEA (OTP SMS).

    Body: {allegato_id, message?, invia_whatsapp?=true, invia_email?=true,
           firmatario?:{name,surname,email,mobile}}
    """
    if not esvc.has_credentials():
        raise HTTPException(400, "Credenziali OpenAPI eSignature non configurate")
    allegato_id = body.get("allegato_id")
    if not allegato_id:
        raise HTTPException(400, "allegato_id obbligatorio")
    al = await db.allegati.find_one({"id": allegato_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not al:
        raise HTTPException(404, "Allegato non trovato")
    ct = (al.get("content_type") or "").lower()
    if "pdf" not in ct and not (al.get("nome_file") or "").lower().endswith(".pdf"):
        raise HTTPException(400, "La firma è disponibile solo su documenti PDF")

    try:
        pdf_bytes, _ct = obj_storage.get_object(al["storage_path"])
    except Exception as e:
        raise HTTPException(502, f"Impossibile leggere il documento: {e}")

    # Firmatario: da body oppure risolto dall'entità dell'allegato
    signer = body.get("firmatario") or {}
    resolved = await _resolve_signer(al["entita_tipo"], al["entita_id"])
    signer = {
        "name": signer.get("name") or resolved.get("name") or "",
        "surname": signer.get("surname") or resolved.get("surname") or resolved.get("ragione_sociale") or "",
        "email": signer.get("email") or resolved.get("email") or "",
        "mobile": signer.get("mobile") or resolved.get("mobile") or "",
    }
    if not signer["mobile"]:
        raise HTTPException(400, "Cellulare del firmatario mancante (necessario per OTP SMS)")

    display = al.get("nome_file") or "documento.pdf"
    res = await esvc.create_signature(
        pdf_bytes=pdf_bytes, signer=signer,
        message=body.get("message") or f"Firma il documento: {display}",
    )
    if not res.get("ok"):
        raise HTTPException(502, res.get("error") or "Errore creazione firma")

    signing_url = res.get("signing_url")
    rec = {
        "id": str(uuid.uuid4()),
        "provider": "openapi_esignature",
        "signature_id": res.get("id"),
        "stato": (res.get("state") or "WAIT_VALIDATION"),
        "allegato_origine_id": allegato_id,
        "entita_tipo": al["entita_tipo"],
        "entita_id": al["entita_id"],
        "categoria": al.get("categoria"),
        "nome_file": display,
        "firmatario_id": resolved.get("anagrafica_id"),
        "firmatario_nome": f"{signer['surname']} {signer['name']}".strip(),
        "firmatario_email": signer["email"],
        "firmatario_mobile": signer["mobile"],
        "signing_url": signing_url,
        "allegato_firmato_id": None,
        "created_at": _now_iso(),
        "created_by": user.get("id"),
    }
    await db.firma_requests.insert_one(dict(rec))

    # Consegna link via WhatsApp + Email IN BACKGROUND (non blocca la risposta:
    # SMTP è sincrono/bloccante e Evolution può essere lento → eviterebbe timeout/502).
    async def _deliver():
        if not signing_url:
            return
        testo = (
            f"Gentile {signer['name']} {signer['surname']},\n"
            f"le è stato inviato un documento da firmare digitalmente ({display}).\n\n"
            f"🔗 Firma qui: {signing_url}\n\n"
            f"Riceverà un codice OTP via SMS per completare la firma. Il link è personale."
        )
        try:
            from notification_helpers import send_email, send_whatsapp_message
            if body.get("invia_whatsapp", True) and signer["mobile"]:
                await send_whatsapp_message(signer["mobile"], testo)
            if body.get("invia_email", True) and signer["email"]:
                await send_email(signer["email"], f"Documento da firmare — {display}", testo)
        except Exception as e:
            logger.warning("Consegna link firma fallita: %s", e)

    asyncio.create_task(_deliver())
    return {**rec, "canali": "in_invio"}


@router.get("/richieste")
async def lista_richieste(entita_tipo: str, entita_id: str, user=Depends(current_user)) -> dict:
    items = await db.firma_requests.find(
        {"provider": "openapi_esignature", "entita_tipo": entita_tipo, "entita_id": entita_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"items": items}


async def _finalizza(rec: dict) -> Optional[str]:
    """Se la firma è completata, scarica il PDF firmato e lo salva come Allegato
    nella STESSA sezione (entità + categoria) del documento originale. Ritorna allegato_id."""
    sig_id = rec.get("signature_id")
    if not sig_id or rec.get("allegato_firmato_id"):
        return rec.get("allegato_firmato_id")
    dl = await esvc.download_signed(sig_id)
    if not dl.get("ok"):
        return None
    content = dl["content"]
    base_name = (rec.get("nome_file") or "documento.pdf").rsplit(".", 1)[0]
    fname = f"{base_name}_firmato.pdf"
    file_id = str(uuid.uuid4())
    path = f"{os.environ.get('APP_NAME', 'assicura')}/firme/{rec['id']}/{file_id}.pdf"
    try:
        up = obj_storage.put_object(path, content, "application/pdf")
    except Exception as e:
        logger.warning("Storage firma put fallito: %s", e)
        return None
    al = Allegato(
        entita_tipo=rec["entita_tipo"], entita_id=rec["entita_id"],
        nome_file=fname, storage_path=up["path"],
        content_type="application/pdf", size=up.get("size", len(content)),
        descrizione="Documento firmato (OpenAPI eSignature)",
        categoria=rec.get("categoria"), visibile_cliente=True,
    )
    doc = al.model_dump()
    doc["firma_request_id"] = rec["id"]
    await db.allegati.insert_one(doc)
    await db.firma_requests.update_one(
        {"id": rec["id"]},
        {"$set": {"stato": "DONE", "allegato_firmato_id": al.id, "updated_at": _now_iso()}},
    )
    return al.id


@router.get("/stato/{req_id}")
async def stato_richiesta(req_id: str, user=Depends(current_user)) -> dict:
    rec = await db.firma_requests.find_one({"id": req_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Richiesta non trovata")
    if rec.get("allegato_firmato_id"):
        return {"stato": "DONE", "allegato_firmato_id": rec["allegato_firmato_id"]}
    det = await esvc.get_detail(rec.get("signature_id"))
    stato = det.get("state") or rec.get("stato")
    allegato_firmato_id = None
    if esvc.is_done(stato):
        allegato_firmato_id = await _finalizza(rec)
        stato = "DONE"
    else:
        await db.firma_requests.update_one({"id": req_id}, {"$set": {"stato": stato, "updated_at": _now_iso()}})
    return {"stato": stato, "allegato_firmato_id": allegato_firmato_id}


async def finalizza_pending() -> int:
    """Scheduler: finalizza le firme completate e invia solleciti WhatsApp dopo 48h."""
    import datetime as _dt
    n = 0
    now = _dt.datetime.now(_dt.timezone.utc)
    try:
        from database import raw_db
        from notification_helpers import send_whatsapp_message
        cur = raw_db.firma_requests.find(
            {"provider": "openapi_esignature", "allegato_firmato_id": None,
             "stato": {"$nin": ["ERROR"]}},
            {"_id": 0},
        )
        async for rec in cur:
            if not rec.get("signature_id"):
                continue
            det = await esvc.get_detail(rec["signature_id"])
            state = (det.get("state") or "").upper()
            if esvc.is_done(det.get("state")):
                if await _finalizza(rec):
                    n += 1
                continue
            if state == "ERROR":
                await raw_db.firma_requests.update_one(
                    {"id": rec["id"]}, {"$set": {"stato": "ERROR", "updated_at": _now_iso()}})
                continue
            # Sollecito WhatsApp dopo 48h se non ancora firmato e non già sollecitato
            if not rec.get("reminder_sent") and rec.get("firmatario_mobile") and rec.get("signing_url"):
                try:
                    created = _dt.datetime.fromisoformat(str(rec.get("created_at")).replace("Z", "+00:00"))
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=_dt.timezone.utc)
                except Exception:
                    created = now
                if (now - created).total_seconds() >= 48 * 3600:
                    testo = (
                        f"Promemoria: il documento \"{rec.get('nome_file')}\" è ancora in attesa della sua firma.\n"
                        f"🔗 Firma qui: {rec['signing_url']}\n"
                        f"Riceverà un codice OTP via SMS per completare."
                    )
                    await send_whatsapp_message(rec["firmatario_mobile"], testo)
                    await raw_db.firma_requests.update_one(
                        {"id": rec["id"]}, {"$set": {"reminder_sent": True, "reminder_at": _now_iso()}})
            await raw_db.firma_requests.update_one(
                {"id": rec["id"]}, {"$set": {"stato": det.get("state") or rec.get("stato"), "updated_at": _now_iso()}})
    except Exception as e:
        logger.warning("finalizza_pending errore: %s", e)
    return n


def start_scheduler() -> None:
    """Avvia un poller ogni 2 minuti per finalizzare le firme completate."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        sched = AsyncIOScheduler(timezone="UTC")
        sched.add_job(finalizza_pending, "interval", minutes=2, id="esignature_poller",
                      replace_existing=True, max_instances=1)
        sched.start()
        logger.info("[eSignature] Poller avviato (ogni 2 min)")
    except Exception as e:
        logger.warning("[eSignature] Poller non avviato: %s", e)
