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

    # crea su Evolution API — usa integration Baileys (default) e richiede QR
    payload = {
        "instanceName": slug,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS",
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
    resp = await _call(
        "POST", f"/message/sendText/{name}",
        json={"number": body.number, "text": body.text},
        instance_token=inst.get("token"),
    )
    return {"ok": True, "resp": resp}
