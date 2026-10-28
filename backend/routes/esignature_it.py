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

# Card documenti dell'anagrafica gestite come dict `anagrafiche.documenti[card]`
_ANAG_DICT_CARDS = {
    "carta_identita", "patente", "passaporto", "codice_fiscale_doc",
    "tessera_sanitaria", "visura_camerale", "mandato_sdd",
    "autocertificazione_stato_famiglia", "privacy_firmata",
}


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


def _mobile_valido(m: str) -> bool:
    digits = "".join(c for c in str(m or "") if c.isdigit())
    return len(digits) >= 8


def _email_valida(e: str) -> bool:
    e = str(e or "").strip()
    return "@" in e and "." in e.split("@")[-1]


# ─────────────────────────── Provider YouSign (v3) ───────────────────────────
import httpx  # noqa: E402

_FIRMA_ANCHOR = "Firma del Contraente"


def _to_e164(mobile: str, default_cc: str = "39") -> str:
    """Normalizza un numero in formato E.164 (+39...). Ritorna '' se non valido."""
    raw = (mobile or "").strip()
    if not raw:
        return ""
    plus = raw.startswith("+")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    if plus:
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith(default_cc) and len(digits) > 10:
        return "+" + digits
    return "+" + default_cc + digits


def _ys_cfg() -> tuple[str, str, str]:
    from routes.firma_modelli import _yousign_cfg
    cfg = _yousign_cfg()
    return cfg["api_key"], cfg["base"], cfg["env"]


def _firma_fields_from_pdf(pdf_bytes: bytes) -> list[dict]:
    """Posizioni del campo firma (coordinate YouSign: origine in alto a sinistra)
    ricavate dall'àncora 'Firma del Contraente' nel PDF generato. Se assente,
    posiziona il campo in basso a destra dell'ultima pagina."""
    try:
        import pymupdf as fitz
    except Exception:  # pragma: no cover
        import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        fields = []
        for page in doc:
            for r in page.search_for(_FIRMA_ANCHOR):
                fields.append({"page": page.number + 1, "x": round(r.x1 + 10),
                               "y": round(max(0, r.y0 - 6)), "width": 130, "height": 40})
        if not fields:
            last = doc[len(doc) - 1]
            fields.append({"page": len(doc), "x": round(last.rect.width - 190),
                           "y": round(last.rect.height - 110), "width": 130, "height": 40})
        return fields
    finally:
        doc.close()


async def _yousign_send(pdf_bytes: bytes, signer: dict, display: str,
                        auth_mode: str = "otp_email", workspace_id: str = "") -> dict:
    """Crea e attiva una richiesta di firma YouSign per un singolo firmatario.
    Ritorna {ok, request_id, document_id, signer_id, status, signing_url}."""
    api_key, base, env = _ys_cfg()
    if not api_key:
        return {"ok": False, "error": f"YouSign non configurato ({env})"}
    email = (signer.get("email") or "").strip()
    if not email:
        return {"ok": False, "error": "Email firmatario mancante"}
    phone = _to_e164(signer.get("mobile"))
    if auth_mode == "otp_sms" and not phone:
        return {"ok": False, "error": "Cellulare del firmatario mancante o non valido (necessario per OTP via SMS)"}
    first = signer.get("name") or "Cliente"
    last = signer.get("surname") or signer.get("ragione_sociale") or "Cliente"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    fields = _firma_fields_from_pdf(pdf_bytes)
    info = {"first_name": first, "last_name": last, "email": email, "locale": "it"}
    if phone:
        info["phone_number"] = phone
    try:
        async with httpx.AsyncClient(base_url=base, headers=headers, timeout=40) as c:
            req_body = {"name": display, "delivery_mode": "none"}
            if workspace_id:
                req_body["workspace_id"] = workspace_id
            r = await c.post("/signature_requests", json=req_body)
            if r.is_error:
                return {"ok": False, "error": r.text[:300]}
            rid = r.json()["id"]
            up = await c.post(f"/signature_requests/{rid}/documents",
                              files={"file": (display or "doc.pdf", pdf_bytes, "application/pdf")},
                              data={"nature": "signable_document"})
            if up.is_error:
                return {"ok": False, "error": up.text[:300]}
            did = up.json()["id"]
            yfields = [{"type": "signature", "document_id": did, "page": f["page"],
                        "x": f["x"], "y": f["y"],
                        "width": max(85, f["width"]), "height": max(37, f["height"])}
                       for f in fields]
            signer_body = {
                "info": info,
                "signature_level": "electronic_signature",
                "signature_authentication_mode": auth_mode,
                "fields": yfields,
            }
            sg = await c.post(f"/signature_requests/{rid}/signers", json=signer_body)
            if sg.is_error:
                return {"ok": False, "error": sg.text[:400]}
            sid = sg.json()["id"]
            act = await c.post(f"/signature_requests/{rid}/activate", json={})
            if act.is_error:
                return {"ok": False, "error": act.text[:400]}
            link = None
            det = await c.get(f"/signature_requests/{rid}/signers/{sid}")
            if det.status_code == 200:
                link = det.json().get("signature_link")
        return {"ok": True, "request_id": rid, "document_id": did, "signer_id": sid,
                "status": act.json().get("status"), "signing_url": link}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _yousign_status(request_id: str) -> str:
    api_key, base, _ = _ys_cfg()
    if not (api_key and request_id):
        return ""
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(base_url=base, headers=headers, timeout=20) as c:
            r = await c.get(f"/signature_requests/{request_id}")
            if r.status_code == 200:
                return (r.json().get("status") or "")
    except Exception as e:
        logger.warning("YouSign status err: %s", e)
    return ""


async def _yousign_download(request_id: str) -> Optional[bytes]:
    api_key, base, _ = _ys_cfg()
    if not (api_key and request_id):
        return None
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/pdf"}
    try:
        async with httpx.AsyncClient(base_url=base, headers=headers, timeout=40) as c:
            r = await c.get(f"/signature_requests/{request_id}/documents/download",
                            params={"version": "completed"})
            if r.status_code == 200 and r.content:
                return r.content
            logger.warning("YouSign download HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("YouSign download err: %s", e)
    return None




@router.get("/firmatario")
async def firmatario_check(entita_tipo: str, entita_id: str, user=Depends(current_user)) -> dict:
    """Restituisce i contatti del firmatario (contraente) e la validità di
    email/cellulare, per mostrare un avviso in UI PRIMA dell'invio firma."""
    resolved = await _resolve_signer(entita_tipo, entita_id)
    email = resolved.get("email") or ""
    mobile = resolved.get("mobile") or ""
    email_ok = _email_valida(email)
    mobile_ok = _mobile_valido(mobile)
    return {
        "nome": resolved.get("name") or "",
        "cognome": resolved.get("surname") or resolved.get("ragione_sociale") or "",
        "email": email,
        "mobile": mobile,
        "email_ok": email_ok,
        "mobile_ok": mobile_ok,
        "ok": email_ok and mobile_ok,
    }



@router.post("/invia")
async def invia_per_firma(body: dict, user=Depends(current_user)) -> dict:
    """Invia un allegato PDF esistente per la firma FEA (OTP SMS).

    Body: {allegato_id, message?, invia_whatsapp?=true, invia_email?=true,
           firmatario?:{name,surname,email,mobile}}
    """
    api_key, _base, _env = _ys_cfg()
    if not api_key:
        raise HTTPException(400, f"YouSign non configurato ({_env})")
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
    if not signer["email"]:
        raise HTTPException(400, "Email del firmatario mancante (obbligatoria per la firma YouSign)")

    auth_mode = body.get("auth_mode") or "otp_sms"
    if auth_mode == "otp_sms" and not _to_e164(signer["mobile"]):
        raise HTTPException(400, "Cellulare del firmatario mancante o non valido (necessario per OTP via SMS)")

    display = al.get("nome_file") or "documento.pdf"
    from routes.firma_modelli import _yousign_workspace_id
    workspace_id = await _yousign_workspace_id(db)
    res = await _yousign_send(
        pdf_bytes=pdf_bytes, signer=signer, display=display, auth_mode=auth_mode,
        workspace_id=workspace_id,
    )
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or "Errore creazione firma")

    signing_url = res.get("signing_url")
    rec = {
        "id": str(uuid.uuid4()),
        "provider": "yousign",
        "signature_id": res.get("request_id"),
        "yousign_document_id": res.get("document_id"),
        "yousign_signer_id": res.get("signer_id"),
        "stato": (res.get("status") or "ongoing"),
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

    # Se il documento è una card dedicata dell'anagrafica, segna "in attesa di firma"
    if al["entita_tipo"] == "anagrafica" and al.get("categoria") in _ANAG_DICT_CARDS:
        await db.anagrafiche.update_one(
            {"id": al["entita_id"], f"documenti.{al['categoria']}": {"$exists": True}},
            {"$set": {
                f"documenti.{al['categoria']}.firma_stato": "in_attesa",
                f"documenti.{al['categoria']}.firma_richiesta_at": _now_iso(),
                f"documenti.{al['categoria']}.firma_request_id": rec["id"],
                "updated_at": _now_iso(),
            }},
        )

    # Consegna link via WhatsApp + Email e riporta l'ESITO REALE di ogni canale
    # (prima avveniva in background e gli errori venivano ingoiati → l'operatore
    # vedeva "inviato" anche quando il link non partiva). Il signing_url viene
    # sempre restituito così l'operatore può inoltrarlo a mano se un canale fallisce.
    recapito = {}
    if signing_url:
        testo = (
            f"Gentile {signer['name']} {signer['surname']},\n"
            f"le è stato inviato un documento da firmare digitalmente ({display}).\n\n"
            f"🔗 Firma qui: {signing_url}\n\n"
            f"Riceverà un codice OTP via SMS per completare la firma. Il link è personale."
        )
        from notification_helpers import send_email, send_whatsapp_message
        if body.get("invia_whatsapp", True) and signer["mobile"]:
            try:
                recapito["whatsapp"] = await asyncio.wait_for(
                    send_whatsapp_message(signer["mobile"], testo), timeout=25)
            except Exception as e:
                recapito["whatsapp"] = {"ok": False, "error": str(e)[:200]}
        if body.get("invia_email", True) and signer["email"]:
            try:
                recapito["email"] = await asyncio.wait_for(
                    send_email(signer["email"], f"Documento da firmare — {display}", testo), timeout=25)
            except Exception as e:
                recapito["email"] = {"ok": False, "error": str(e)[:200]}

    return {**rec, "recapito": recapito}


@router.get("/workspace")
async def get_workspace(user=Depends(current_user)) -> dict:
    """Workspace Yousign configurato per l'agenzia corrente."""
    az = await db.azienda_config.find_one({}, {"_id": 0, "yousign_workspace_id": 1}) or {}
    return {"workspace_id": az.get("yousign_workspace_id") or ""}


@router.put("/workspace")
async def set_workspace(body: dict, user=Depends(current_user)) -> dict:
    """Imposta il workspace Yousign dell'agenzia corrente (le richieste firma vi
    verranno salvate). Ogni agenzia ha il proprio workspace."""
    wid = (body.get("workspace_id") or "").strip()
    await db.azienda_config.update_one({}, {"$set": {"yousign_workspace_id": wid}}, upsert=True)
    return {"ok": True, "workspace_id": wid}



@router.get("/richieste")
async def lista_richieste(entita_tipo: str, entita_id: str, user=Depends(current_user)) -> dict:
    items = await db.firma_requests.find(
        {"provider": {"$in": ["yousign", "openapi_esignature"]},
         "entita_tipo": entita_tipo, "entita_id": entita_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"items": items}


async def _finalizza(rec: dict) -> Optional[str]:
    """Se la firma è completata, scarica il PDF firmato e lo salva come Allegato
    nella STESSA sezione (entità + categoria) del documento originale. Ritorna allegato_id."""
    sig_id = rec.get("signature_id")
    if not sig_id or rec.get("allegato_firmato_id"):
        return rec.get("allegato_firmato_id")
    if rec.get("provider") == "yousign":
        content = await _yousign_download(sig_id)
        if not content:
            return None
        descrizione = "Documento firmato (YouSign)"
    else:
        dl = await esvc.download_signed(sig_id)
        if not dl.get("ok"):
            return None
        content = dl["content"]
        descrizione = "Documento firmato (OpenAPI eSignature)"
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
        descrizione=descrizione, categoria=rec.get("categoria"), visibile_cliente=True,
    )
    doc = al.model_dump()
    doc["firma_request_id"] = rec["id"]
    await db.allegati.insert_one(doc)
    await db.firma_requests.update_one(
        {"id": rec["id"]},
        {"$set": {"stato": "DONE", "allegato_firmato_id": al.id, "updated_at": _now_iso()}},
    )
    # Se il documento appartiene a una card dedicata dell'anagrafica, mostra il
    # firmato anche nella card (dict documenti) con stato/date firma.
    if rec.get("entita_tipo") == "anagrafica" and rec.get("categoria") in _ANAG_DICT_CARDS:
        await db.anagrafiche.update_one(
            {"id": rec["entita_id"]},
            {"$set": {f"documenti.{rec['categoria']}": {
                "url": f"/api/storage/{up['path']}",
                "storage_path": up["path"],
                "nome_file": fname,
                "mime": "application/pdf",
                "size_kb": round(up.get("size", len(content)) / 1024, 1),
                "data_caricamento": _now_iso(),
                "allegato_id": al.id,
                "firmato": True,
                "firma_stato": "firmato",
                "firma_completata_at": _now_iso(),
                "firma_request_id": rec["id"],
            }, "updated_at": _now_iso()}},
        )
    return al.id


@router.get("/stato/{req_id}")
async def stato_richiesta(req_id: str, user=Depends(current_user)) -> dict:
    rec = await db.firma_requests.find_one({"id": req_id}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Richiesta non trovata")
    if rec.get("allegato_firmato_id"):
        return {"stato": "DONE", "allegato_firmato_id": rec["allegato_firmato_id"]}
    if rec.get("provider") == "yousign":
        stato = await _yousign_status(rec.get("signature_id")) or rec.get("stato")
        allegato_firmato_id = None
        if (stato or "").lower() == "done":
            allegato_firmato_id = await _finalizza(rec)
            stato = "DONE"
        else:
            await db.firma_requests.update_one({"id": req_id}, {"$set": {"stato": stato, "updated_at": _now_iso()}})
        return {"stato": stato, "allegato_firmato_id": allegato_firmato_id}
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
            {"provider": {"$in": ["yousign", "openapi_esignature"]}, "allegato_firmato_id": None,
             "stato": {"$nin": ["ERROR"]}},
            {"_id": 0},
        )
        async for rec in cur:
            if not rec.get("signature_id"):
                continue
            if rec.get("provider") == "yousign":
                ys = await _yousign_status(rec["signature_id"])
                state = (ys or "").upper()
                is_done = (ys or "").lower() == "done"
                cur_state = ys or rec.get("stato")
            else:
                det = await esvc.get_detail(rec["signature_id"])
                state = (det.get("state") or "").upper()
                is_done = esvc.is_done(det.get("state"))
                cur_state = det.get("state") or rec.get("stato")
            if is_done:
                if await _finalizza(rec):
                    n += 1
                continue
            if state in ("ERROR", "EXPIRED", "CANCELED", "DECLINED"):
                await raw_db.firma_requests.update_one(
                    {"id": rec["id"]}, {"$set": {"stato": state, "updated_at": _now_iso()}})
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
                        f"Riceverà un codice OTP per completare."
                    )
                    await send_whatsapp_message(rec["firmatario_mobile"], testo)
                    await raw_db.firma_requests.update_one(
                        {"id": rec["id"]}, {"$set": {"reminder_sent": True, "reminder_at": _now_iso()}})
            await raw_db.firma_requests.update_one(
                {"id": rec["id"]}, {"$set": {"stato": cur_state, "updated_at": _now_iso()}})
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
