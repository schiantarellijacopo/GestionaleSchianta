"""AI Copilot + TTS endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from typing import Optional

from auth import current_user
import ai_copilot_service as copilot
import elevenlabs_service as tts_svc

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    use_tts: bool = False


class CopilotResponse(BaseModel):
    answer: str
    context_summary: dict
    audio_available: bool = False


@router.post("/chat", response_model=CopilotResponse)
async def copilot_chat(body: CopilotRequest, user=Depends(current_user)) -> CopilotResponse:
    """Endpoint principale del Copilot AI. Recupera dati dal DB e chiama LLM."""
    if not body.message or len(body.message.strip()) < 2:
        raise HTTPException(400, "Messaggio troppo corto")

    ctx = await copilot.dispatch_query(body.message)
    answer = await copilot.copilot_answer(body.message, ctx)

    # Riepilogo del contesto per debug/UI (senza esporre tutti i dettagli)
    summary = {k: (len(v) if isinstance(v, list) else 1) for k, v in ctx.items()}

    return CopilotResponse(
        answer=answer,
        context_summary=summary,
        audio_available=tts_svc.is_configured() and body.use_tts,
    )


class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = "21m00Tcm4Tlm"
    model_id: Optional[str] = "eleven_multilingual_v2"


@router.post("/tts")
async def copilot_tts(body: TTSRequest, user=Depends(current_user)):
    """Genera audio MP3 dal testo. Ritorna il file binario direttamente."""
    if not tts_svc.is_configured():
        raise HTTPException(400, "ElevenLabs non configurato — manca ELEVENLABS_API_KEY")
    try:
        audio = await tts_svc.tts_generate(body.text, voice_id=body.voice_id, model_id=body.model_id)
        return Response(content=audio, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(500, f"Errore TTS: {e}")


@router.get("/voices")
async def copilot_voices(user=Depends(current_user)):
    return {"voices": await tts_svc.list_voices(), "configured": tts_svc.is_configured()}
