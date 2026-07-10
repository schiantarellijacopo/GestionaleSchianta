"""OpenAI Chat integration via Emergent Universal Key.

Endpoint AI per:
- Analisi documenti cliente (riassunti, estrazione dati)
- Generazione template risposta WhatsApp/email
- Chat assistant contestuale sul CRM
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import current_user
from database import db
from db_models import _now_iso


router = APIRouter(prefix="/ai", tags=["ai"])


DEFAULT_MODEL = "gpt-5.4"
DEFAULT_PROVIDER = "openai"


class AiChatBody(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    system_message: Optional[str] = None
    provider: str = DEFAULT_PROVIDER  # openai | anthropic | gemini
    model: str = DEFAULT_MODEL


@router.post("/chat")
async def ai_chat(body: AiChatBody, user=Depends(current_user)) -> dict:
    """One-shot AI response (non-streaming). Per interazioni brevi/veloci."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY non configurata")

    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

    session_id = body.session_id or str(uuid.uuid4())
    chat = LlmChat(
        api_key=key,
        session_id=session_id,
        system_message=body.system_message
        or "Sei un assistente AI del gestionale assicurativo Italiano. Rispondi in italiano, in modo sintetico e professionale.",
    ).with_model(body.provider, body.model)

    try:
        response = await chat.send_message(UserMessage(text=body.prompt))
    except Exception as e:
        raise HTTPException(502, f"Errore LLM: {e}") from e

    # Salva conversazione in DB per persistenza
    await db.ai_chat_messages.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "user_id": user.get("id"),
        "provider": body.provider,
        "model": body.model,
        "prompt": body.prompt,
        "response": response,
        "created_at": _now_iso(),
    })

    return {"session_id": session_id, "response": response, "model": body.model, "provider": body.provider}


@router.post("/chat/stream")
async def ai_chat_stream(body: AiChatBody, user=Depends(current_user)):
    """Streaming response SSE per UI real-time (tokens on-the-fly)."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY non configurata")

    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone  # type: ignore

    session_id = body.session_id or str(uuid.uuid4())
    chat = LlmChat(
        api_key=key,
        session_id=session_id,
        system_message=body.system_message
        or "Sei un assistente AI del gestionale assicurativo Italiano. Rispondi in italiano, in modo sintetico e professionale.",
    ).with_model(body.provider, body.model)

    async def event_generator():
        full_response = ""
        try:
            async for event in chat.stream_message(UserMessage(text=body.prompt)):
                if isinstance(event, TextDelta):
                    full_response += event.content
                    yield f"data: {event.content}\n\n"
                elif isinstance(event, StreamDone):
                    break
        except Exception as e:
            yield f"event: error\ndata: {e}\n\n"
        finally:
            # Persist alla fine
            try:
                await db.ai_chat_messages.insert_one({
                    "id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "user_id": user.get("id"),
                    "provider": body.provider,
                    "model": body.model,
                    "prompt": body.prompt,
                    "response": full_response,
                    "created_at": _now_iso(),
                })
            except Exception:
                pass
            yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/sessions/{session_id}")
async def get_session_history(session_id: str, user=Depends(current_user)) -> list[dict]:
    """Storico messaggi di una sessione AI."""
    msgs = await db.ai_chat_messages.find(
        {"session_id": session_id, "user_id": user.get("id")},
        {"_id": 0},
    ).sort("created_at", 1).to_list(200)
    return msgs
