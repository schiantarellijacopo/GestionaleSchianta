"""Immagini AI — generazione immagini marketing (Gemini Nano Banana, Emergent LLM Key)."""
from __future__ import annotations

import base64
import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from auth import require_user
from database import db
from db_models import _now_iso, _uid
import storage as obj_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/immagini-ai")

STAFF = ("admin", "collaboratore", "dipendente")
MODELLO = ("gemini", "gemini-3.1-flash-image-preview")

FORMATI = {
    "quadrato": "formato quadrato 1:1 (post Instagram 1080x1080)",
    "verticale": "formato verticale 9:16 (storia/reel Instagram 1080x1920)",
    "orizzontale": "formato orizzontale 16:9 (banner/copertina)",
}
STILI = {
    "fotografico": "stile fotografico realistico, luce naturale professionale",
    "illustrazione": "stile illustrazione moderna flat, colori vivaci",
    "minimal": "stile minimalista elegante, molto spazio negativo, palette sobria",
    "elegante": "stile premium elegante, tonalità scure e dettagli dorati",
}


@router.post("/genera", status_code=201)
async def genera_immagine(body: dict, user=Depends(require_user(*STAFF))):
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "Prompt obbligatorio")
    formato = body.get("formato") if body.get("formato") in FORMATI else "quadrato"
    stile = body.get("stile") if body.get("stile") in STILI else None

    full_prompt = f"Crea un'immagine di marketing per un'agenzia assicurativa italiana. {prompt}."
    if stile:
        full_prompt += f" {STILI[stile]}."
    full_prompt += f" Immagine in {FORMATI[formato]}. Nessun testo sgrammaticato; se includi testo, in italiano corretto."

    try:
        from llm_compat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"imgai_{_uid()}",
            system_message="You are a helpful AI assistant",
        )
        chat.with_model(*MODELLO).with_params(modalities=["image", "text"])
        _text, images = await chat.send_message_multimodal_response(UserMessage(text=full_prompt))
    except Exception as e:
        logger.exception("Immagini AI: errore generazione")
        raise HTTPException(503, f"Errore generazione immagine: {str(e)[:200]}")
    if not images:
        raise HTTPException(502, "Il modello non ha restituito immagini. Riprova con un prompt diverso.")

    img = images[0]
    image_bytes = base64.b64decode(img["data"])
    ext = "png" if "png" in (img.get("mime_type") or "") else "jpg"
    iid = _uid()
    path = f"{os.environ.get('APP_NAME', 'assicura')}/immagini-ai/{iid}.{ext}"
    res = obj_storage.put_object(path, image_bytes, img.get("mime_type") or "image/png")
    url = f"/api/storage/{res['path']}"

    doc = {
        "id": iid, "prompt": prompt, "formato": formato, "stile": stile,
        "url": url, "storage_path": res["path"],
        "size_kb": round(len(image_bytes) / 1024, 1),
        "creato_da": user.get("name") or user.get("email"),
        "created_at": _now_iso(),
    }
    await db.immagini_ai.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def lista_immagini(user=Depends(require_user(*STAFF))):
    return await db.immagini_ai.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.delete("/{iid}")
async def elimina_immagine(iid: str, user=Depends(require_user(*STAFF))):
    doc = await db.immagini_ai.find_one({"id": iid}, {"_id": 0, "storage_path": 1})
    if not doc:
        raise HTTPException(404, "Immagine non trovata")
    try:
        obj_storage.delete_object(doc["storage_path"])
    except Exception:
        pass
    await db.immagini_ai.delete_one({"id": iid})
    return {"ok": True}
