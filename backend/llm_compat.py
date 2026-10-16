"""Shim compatibile con emergentintegrations.llm.chat.

Scopo: in PRODUZIONE (es. Railway, fuori dalla piattaforma Emergent) la chiave
universale Emergent restituisce 403. Se è presente `GEMINI_API_KEY`, le chiamate
al provider "gemini" vengono instradate DIRETTAMENTE all'API Google Gemini
(google-genai), mantenendo invariata l'interfaccia usata dal resto del codice
(`LlmChat(...).with_model(...).send_message(...)` / `.stream_message(...)`).

Se `GEMINI_API_KEY` NON è presente (es. preview Emergent), tutto continua a
passare dalla libreria emergentintegrations come prima.

Ri-esporta UserMessage/ImageContent/TextDelta/StreamDone REALI così che gli
`isinstance(...)` nel codice chiamante continuino a funzionare.
"""
from __future__ import annotations
import os
import base64
import asyncio

from emergentintegrations.llm.chat import (  # noqa: F401
    LlmChat as _RealLlmChat,
    UserMessage,
    ImageContent,
    TextDelta,
    StreamDone,
)

__all__ = ["LlmChat", "UserMessage", "ImageContent", "TextDelta", "StreamDone"]

_gemini_client = None


def _direct_gemini_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _get_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _gemini_client


def _sniff_mime(b: bytes) -> str:
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    if b[:5] == b"%PDF-":
        return "application/pdf"
    return "image/png"


class LlmChat:
    def __init__(self, api_key=None, session_id=None, system_message=None, **kwargs):
        self._system = system_message
        self._provider = None
        self._model = None
        self._real = None
        self._real_kwargs = dict(
            api_key=api_key, session_id=session_id, system_message=system_message, **kwargs
        )

    def with_model(self, provider, model):
        self._provider = provider
        self._model = model
        return self

    # --- routing ---
    def _use_direct(self) -> bool:
        return self._provider == "gemini" and _direct_gemini_enabled()

    def _real_chat(self):
        if self._real is None:
            self._real = _RealLlmChat(**self._real_kwargs)
            if self._provider:
                self._real = self._real.with_model(self._provider, self._model)
        return self._real

    def __getattr__(self, name):
        # Metodi non gestiti (es. send_message_multimodal_response) → libreria reale
        return getattr(self._real_chat(), name)

    # --- Gemini diretto ---
    def _build_contents(self, message):
        from google.genai import types
        contents = []
        text = getattr(message, "text", None)
        if text:
            contents.append(text)
        for fc in (getattr(message, "file_contents", None) or []):
            b64 = (getattr(fc, "image_base64", None)
                   or getattr(fc, "file_base64", None)
                   or getattr(fc, "content_base64", None))
            if not b64:
                continue
            data = base64.b64decode(b64)
            mime = getattr(fc, "mime_type", None) or _sniff_mime(data)
            contents.append(types.Part.from_bytes(data=data, mime_type=mime))
        return contents or [""]

    def _direct_call(self, message) -> str:
        from google.genai import types
        client = _get_client()
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        cfg = types.GenerateContentConfig(
            temperature=0,
            system_instruction=self._system or None,
        )
        resp = client.models.generate_content(
            model=model, contents=self._build_contents(message), config=cfg
        )
        return resp.text or ""

    async def send_message(self, message):
        if self._use_direct():
            return await asyncio.to_thread(self._direct_call, message)
        return await self._real_chat().send_message(message)

    async def stream_message(self, message):
        if self._use_direct():
            text = await asyncio.to_thread(self._direct_call, message)
            yield TextDelta(content=text)
            return
        async for ev in self._real_chat().stream_message(message):
            yield ev
