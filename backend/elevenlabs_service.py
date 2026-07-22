"""ElevenLabs Text-to-Speech service.

Uso:
    from elevenlabs_service import tts_generate, list_voices
    audio_bytes = await tts_generate("Ciao Mario", voice_id="21m00Tcm4Tlm")

Variabili d'ambiente lette:
    ELEVENLABS_API_KEY → chiave API (obbligatoria per live; se vuota → NotConfigured)

Modelli:
    - eleven_multilingual_v2 (default) — supporta italiano
    - eleven_turbo_v2_5 (più veloce, latenza bassa)
"""
from __future__ import annotations
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class NotConfigured(RuntimeError):
    """Sollevato se ELEVENLABS_API_KEY non è configurata."""


def _api_key() -> Optional[str]:
    return (os.environ.get("ELEVENLABS_API_KEY") or "").strip() or None


def is_configured() -> bool:
    return bool(_api_key())


def _client():
    """Crea un client ElevenLabs lazy. Non importa la lib se non serve."""
    key = _api_key()
    if not key:
        raise NotConfigured("ELEVENLABS_API_KEY mancante in .env")
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError as e:
        raise RuntimeError(f"pip install elevenlabs — libreria mancante: {e}")
    return ElevenLabs(api_key=key)


async def tts_generate(
    text: str,
    voice_id: str = "21m00Tcm4Tlm",  # Rachel (default multilingua)
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
) -> bytes:
    """Genera audio MP3 dal testo. Ritorna bytes; solleva NotConfigured se manca la key."""
    client = _client()
    try:
        from elevenlabs import VoiceSettings
        gen = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            voice_settings=VoiceSettings(
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                use_speaker_boost=True,
            ),
        )
        audio = b""
        for chunk in gen:
            audio += chunk
        return audio
    except Exception as e:
        logger.error("ElevenLabs TTS error: %s", e)
        raise


async def list_voices() -> list[dict]:
    """Ritorna la lista di voci disponibili sull'account (name, voice_id, category, description).

    Se ElevenLabs non è configurato, ritorna una lista vuota (mai raise).
    """
    if not is_configured():
        return []
    try:
        client = _client()
        resp = client.voices.get_all()
        voices = getattr(resp, "voices", None) or resp
        out = []
        for v in voices:
            out.append({
                "voice_id": getattr(v, "voice_id", None) or v.get("voice_id"),
                "name": getattr(v, "name", None) or v.get("name"),
                "category": getattr(v, "category", None) or v.get("category", "premade"),
                "description": getattr(v, "description", None) or v.get("description"),
                "labels": getattr(v, "labels", None) or v.get("labels", {}),
            })
        return out
    except Exception as e:
        logger.warning("ElevenLabs list_voices error: %s", e)
        return []


async def clone_voice(name: str, files: list[tuple[str, bytes]], description: Optional[str] = None) -> dict:
    """Instant Voice Cloning. `files` = lista di (filename, bytes) di sample audio."""
    client = _client()
    # elevenlabs SDK richiede path-like; scriviamo su tmp
    import tempfile
    import os as _os
    tmp_paths = []
    try:
        for filename, data in files:
            fd, p = tempfile.mkstemp(suffix=_os.path.splitext(filename)[1] or ".mp3")
            with _os.fdopen(fd, "wb") as f:
                f.write(data)
            tmp_paths.append(p)
        voice = client.voices.ivc.create(
            name=name,
            files=tmp_paths,
            description=description,
        )
        return {
            "voice_id": getattr(voice, "voice_id", None),
            "name": getattr(voice, "name", None),
            "category": "cloned",
        }
    finally:
        for p in tmp_paths:
            try:
                _os.remove(p)
            except OSError:
                pass
