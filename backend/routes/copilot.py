"""AI Copilot + TTS endpoints — chat conversazionale con Claude Sonnet 4.6."""
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
    session_id: str
    context_summary: dict
    audio_available: bool = False


@router.post("/chat", response_model=CopilotResponse)
async def copilot_chat(body: CopilotRequest, user=Depends(current_user)) -> CopilotResponse:
    """Chat conversazionale (multi-turno con memoria in Mongo, Claude Sonnet 4.6)."""
    if not body.message or len(body.message.strip()) < 2:
        raise HTTPException(400, "Messaggio troppo corto")
    out = await copilot.copilot_chat(body.message, user, session_id=body.session_id)
    return CopilotResponse(
        answer=out["answer"],
        session_id=out["session_id"],
        context_summary=out["context_summary"],
        audio_available=tts_svc.is_configured() and body.use_tts,
    )


@router.get("/sessions")
async def list_sessions(user=Depends(current_user)) -> list[dict]:
    """Lista sessioni chat dell'utente corrente (ordinate per ultimo aggiornamento)."""
    return await copilot.list_sessions(user)


@router.get("/sessions/{sid}/messages")
async def get_session_messages(sid: str, user=Depends(current_user)) -> list[dict]:
    """Cronologia messaggi di una sessione."""
    msgs = await copilot.get_session_messages(sid, user)
    return msgs


@router.delete("/sessions/{sid}")
async def delete_session(sid: str, user=Depends(current_user)) -> dict:
    ok = await copilot.delete_session(sid, user)
    if not ok:
        raise HTTPException(404, "Sessione non trovata")
    return {"ok": True}


class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = "21m00Tcm4Tlm"
    model_id: Optional[str] = "eleven_multilingual_v2"


@router.post("/tts")
async def copilot_tts(body: TTSRequest, user=Depends(current_user)):
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
