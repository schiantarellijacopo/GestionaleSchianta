"""Evolution API — WhatsApp multi-tenant integration.

Un'istanza per agenzia. Il gestionale si comporta da orchestratore:
- POST /instance/create        → crea sessione WhatsApp isolata
- GET  /instance/connect/:name → recupera QR code per il pairing
- GET  /instance/connectionState/:name → stato connessione
- DELETE /instance/logout/:name / /instance/delete/:name
- POST /message/sendText/:name → invio messaggi

Env vars richieste (`backend/.env`):
- WHATSAPP_API_URL  = URL base Evolution API (es. https://…up.railway.app)
- WHATSAPP_API_KEY  = valore di AUTHENTICATION_API_KEY configurato su Railway
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter(prefix="/whatsapp-evo", tags=["whatsapp-evo"])


# ---------- Client Evolution API ----------
def _cfg() -> tuple[str, str]:
    url = (os.environ.get("WHATSAPP_API_URL") or "").rstrip("/")
    key = os.environ.get("WHATSAPP_API_KEY") or ""
    if not url or not key:
        raise HTTPException(
            503,
            "WhatsApp Evolution API non configurata. "
            "Imposta WHATSAPP_API_URL e WHATSAPP_API_KEY in backend/.env",
        )
    return url, key


async def _call(method: str, path: str, *, json: Optional[dict] = None, instance_token: Optional[str] = None) -> dict:
    """Chiamata HTTP verso Evolution API. Usa la global key di default,
    o il token della singola istanza se fornito."""
    url_base, global_key = _cfg()
    headers = {"apikey": instance_token or global_key, "Content-Type": "application/json"}
    url = f"{url_base}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=headers, json=json)
    except httpx.RequestError as e:
        raise HTTPException(502, f"Evolution API non raggiungibile: {e}") from e
    if resp.status_code >= 400:
        detail = resp.text[:800]
        raise HTTPException(resp.status_code, f"Evolution API error: {detail}")
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"raw": resp.text}


# ---------- Modelli richiesta ----------
class CreateInstanceBody(BaseModel):
    agenzia_id: Optional[str] = None
    agenzia_nome: str  # etichetta visibile (es. "Agenzia Roma")
    instance_name: Optional[str] = None  # se None viene generato


# ---------- Endpoints gestione istanze ----------
@router.get("/config")
async def get_config(user=Depends(current_user)) -> dict:
    """Verifica lo stato della configurazione senza esporre la chiave."""
    url = (os.environ.get("WHATSAPP_API_URL") or "").rstrip("/")
    key = os.environ.get("WHATSAPP_API_KEY") or ""
    return {
        "configured": bool(url and key),
        "url_set": bool(url),
        "key_set": bool(key),
        "url": url or None,
    }


@router.get("/instances")
async def list_instances(user=Depends(require_user("admin", "collaboratore"))) -> list[dict]:
    """Elenco delle istanze WhatsApp create dalle nostre agenzie."""
    rows = await db.whatsapp_instances.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    # arricchisci con stato in tempo reale dall'API (best-effort)
    for r in rows:
        try:
            st = await _call("GET", f"/instance/connectionState/{r['instance_name']}")
            state = (((st or {}).get("instance") or {}).get("state")
                     or (st or {}).get("state") or "unknown")
            r["state_live"] = state
        except HTTPException:
            r["state_live"] = None
    return rows


@router.post("/instances", status_code=201)
async def create_instance(
    body: CreateInstanceBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Crea una nuova istanza WhatsApp isolata per un'agenzia."""
    # slug istanza (sicuro: solo lettere/numeri/-/_)
    raw_name = (body.instance_name or f"agenzia-{body.agenzia_nome}").lower().strip()
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in raw_name)[:60]
    if await db.whatsapp_instances.find_one({"instance_name": slug}):
        raise HTTPException(409, f"Istanza '{slug}' già esistente")

    # Webhook che riceverà i messaggi in arrivo per questa istanza
    backend_base = (os.environ.get("BACKEND_PUBLIC_URL") or "").rstrip("/")
    webhook_url = f"{backend_base}/api/whatsapp-evo/webhook/{slug}" if backend_base else None

    # crea su Evolution API — usa integration Baileys (default) e richiede QR
    payload: dict = {
        "instanceName": slug,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS",
    }
    if webhook_url:
        payload["webhook"] = {
            "url": webhook_url,
            "byEvents": False,
            "base64": False,
            "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "MESSAGES_UPDATE"],
        }
    resp = await _call("POST", "/instance/create", json=payload)
    inst = (resp or {}).get("instance") or {}
    qr = (resp or {}).get("qrcode") or {}
    hash_key = (resp or {}).get("hash") or inst.get("apikey") or inst.get("token")

    doc = {
        "id": str(uuid.uuid4()),
        "instance_name": slug,
        "agenzia_id": body.agenzia_id,
        "agenzia_nome": body.agenzia_nome,
        "token": hash_key,
        "state": inst.get("status") or "created",
        "webhook_url": webhook_url,
        "created_at": _now_iso(),
        "created_by": user.get("id"),
    }
    await db.whatsapp_instances.insert_one(doc.copy())
    doc.pop("_id", None)
    doc["qr"] = {
        "code": qr.get("code"),
        "base64": qr.get("base64"),
        "pairingCode": qr.get("pairingCode"),
    } if qr else None
    return doc


@router.get("/instances/{name}/qr")
async def get_qr(name: str, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    """Recupera il QR Code aggiornato per il pairing."""
    resp = await _call("GET", f"/instance/connect/{name}")
    # struttura tipica: { code, base64, pairingCode, ... }
    code = resp.get("code") or (resp.get("qrcode") or {}).get("code")
    base64 = resp.get("base64") or (resp.get("qrcode") or {}).get("base64")
    return {
        "code": code,
        "base64": base64,
        "pairingCode": resp.get("pairingCode"),
        "count": resp.get("count"),
    }


@router.get("/instances/{name}/status")
async def get_status(name: str, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    """Stato connessione dell'istanza."""
    resp = await _call("GET", f"/instance/connectionState/{name}")
    st = ((resp or {}).get("instance") or {}).get("state") or (resp or {}).get("state") or "unknown"
    await db.whatsapp_instances.update_one(
        {"instance_name": name},
        {"$set": {"state": st, "updated_at": _now_iso()}},
    )
    return {"instance_name": name, "state": st, "raw": resp}


@router.post("/instances/{name}/logout")
async def logout_instance(name: str, user=Depends(require_user("admin"))) -> dict:
    """Disconnette il numero dall'istanza (non elimina la sessione)."""
    resp = await _call("DELETE", f"/instance/logout/{name}")
    await db.whatsapp_instances.update_one(
        {"instance_name": name},
        {"$set": {"state": "disconnected", "updated_at": _now_iso()}},
    )
    return {"ok": True, "raw": resp}


@router.delete("/instances/{name}")
async def delete_instance(name: str, user=Depends(require_user("admin"))) -> dict:
    """Cancella completamente l'istanza (locale + Evolution)."""
    try:
        await _call("DELETE", f"/instance/delete/{name}")
    except HTTPException:
        pass  # istanza già rimossa lato Evolution
    r = await db.whatsapp_instances.delete_one({"instance_name": name})
    return {"ok": True, "deleted": r.deleted_count}


# ---------- Invio messaggi ----------
class SendTextBody(BaseModel):
    number: str  # es. "393401234567"
    text: str


@router.post("/instances/{name}/send-text")
async def send_text(
    name: str, body: SendTextBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Invia messaggio di testo tramite l'istanza indicata."""
    inst = await db.whatsapp_instances.find_one({"instance_name": name}, {"_id": 0})
    if not inst:
        raise HTTPException(404, "Istanza non trovata")
    try:
        resp = await _call(
            "POST", f"/message/sendText/{name}",
            json={"number": body.number, "text": body.text},
            instance_token=inst.get("token"),
        )
        return {"ok": True, "resp": resp}
    finally:
        # salva copia in DB come "sent" per tracking (anche se il call fallisce)
        try:
            await db.whatsapp_messages.insert_one({
                "id": str(uuid.uuid4()),
                "instance_name": name,
                "direction": "out",
                "number": body.number,
                "text": body.text,
                "created_at": _now_iso(),
            })
        except Exception:
            pass


# ---------- Webhook & Inbox messaggi ----------
from fastapi import Request  # noqa: E402


@router.post("/webhook/{name}")
async def evolution_webhook(name: str, request: Request) -> dict:
    """Webhook chiamato da Evolution API per ogni evento.
    NON è autenticato con JWT: Evolution posta liberamente.
    Salviamo il messaggio nella collection `whatsapp_messages` per la inbox.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "reason": "invalid json"}

    event = payload.get("event") or ""
    data = payload.get("data") or payload

    # MESSAGES_UPSERT: nuovo messaggio ricevuto/inviato
    if "messages" in str(event).lower() or "messages" in payload:
        msgs = data if isinstance(data, list) else [data]
        for m in msgs:
            key = m.get("key") or {}
            msg = m.get("message") or {}
            text = (msg.get("conversation")
                    or (msg.get("extendedTextMessage") or {}).get("text")
                    or (msg.get("imageMessage") or {}).get("caption")
                    or "")
            remote = (key.get("remoteJid") or "").split("@")[0]
            direction = "out" if key.get("fromMe") else "in"
            await db.whatsapp_messages.insert_one({
                "id": str(uuid.uuid4()),
                "instance_name": name,
                "direction": direction,
                "number": remote,
                "text": text,
                "message_type": next(iter(msg.keys())) if msg else None,
                "wamid": key.get("id"),
                "push_name": m.get("pushName"),
                "created_at": _now_iso(),
                "received_at": _now_iso() if direction == "in" else None,
            })

    # CONNECTION_UPDATE: aggiornamento stato
    if "connection" in str(event).lower():
        state = (data or {}).get("state") or (data or {}).get("status")
        if state:
            await db.whatsapp_instances.update_one(
                {"instance_name": name},
                {"$set": {"state": state, "updated_at": _now_iso()}},
            )

    return {"ok": True}


@router.get("/instances/{name}/messages")
async def list_messages(
    name: str,
    limit: int = 100,
    number: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> list[dict]:
    """Elenco messaggi (in e out) per l'istanza. Ordina per data desc."""
    flt: dict = {"instance_name": name}
    if number:
        flt["number"] = number
    return await db.whatsapp_messages.find(flt, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)


@router.get("/instances/{name}/chats")
async def list_chats(
    name: str,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> list[dict]:
    """Aggregazione: 1 riga per numero, con ultimo messaggio + count non letti."""
    pipeline = [
        {"$match": {"instance_name": name}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$number",
            "last_text": {"$first": "$text"},
            "last_direction": {"$first": "$direction"},
            "last_time": {"$first": "$created_at"},
            "last_push_name": {"$first": "$push_name"},
            "count_in": {"$sum": {"$cond": [{"$eq": ["$direction", "in"]}, 1, 0]}},
            "count_out": {"$sum": {"$cond": [{"$eq": ["$direction", "out"]}, 1, 0]}},
        }},
        {"$sort": {"last_time": -1}},
        {"$limit": 100},
    ]
    rows = await db.whatsapp_messages.aggregate(pipeline).to_list(100)
    for r in rows:
        r["number"] = r.pop("_id")
    return rows
