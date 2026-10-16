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
GEMINI_REST = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"


def _direct_gemini_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


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
        self._json_mode = False
        self._real_kwargs = dict(
            api_key=api_key, session_id=session_id, system_message=system_message, **kwargs
        )

    def with_model(self, provider, model):
        self._provider = provider
        self._model = model
        return self

    def with_json(self):
        """Opt-in: forza output JSON puro su Gemini diretto (più veloce e
        affidabile per gli OCR; niente markdown da ripulire). No-op sul
        percorso emergentintegrations."""
        self._json_mode = True
        return self

    # --- routing ---
    def _use_direct(self) -> bool:
        # Se GEMINI_API_KEY è presente, TUTTE le chiamate LLM (testo e vision,
        # qualsiasi provider) passano da Gemini diretto. La chiave Emergent NON
        # viene mai usata. Emergentintegrations resta solo come fallback quando
        # GEMINI_API_KEY non è configurata (es. preview senza chiave).
        return _direct_gemini_enabled()

    def _real_chat(self):
        if self._real is None:
            self._real = _RealLlmChat(**self._real_kwargs)
            if self._provider:
                self._real = self._real.with_model(self._provider, self._model)
        return self._real

    def __getattr__(self, name):
        # Metodi non gestiti (es. send_message_multimodal_response) → libreria reale
        return getattr(self._real_chat(), name)

    # --- Gemini diretto (REST) ---
    def _build_parts(self, message):
        parts = []
        text = getattr(message, "text", None)
        if text:
            parts.append({"text": text})
        for fc in (getattr(message, "file_contents", None) or []):
            b64 = (getattr(fc, "file_content_base64", None)
                   or getattr(fc, "image_base64", None)
                   or getattr(fc, "file_base64", None)
                   or getattr(fc, "content_base64", None))
            if not b64:
                continue
            import base64 as _b64
            ct = getattr(fc, "content_type", None)
            mime = ct if (ct and "/" in ct) else None
            try:
                raw = _b64.b64decode(b64)
                mime = mime or _sniff_mime(raw)
            except Exception:
                mime = mime or "image/png"
            parts.append({"inlineData": {"mimeType": mime, "data": b64}})
        return parts or [{"text": ""}]

    def _direct_call(self, message) -> str:
        import httpx
        import time
        key = os.environ["GEMINI_API_KEY"]
        primary = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        fallbacks = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3-flash-preview"]
        candidates = [primary] + [m for m in fallbacks if m != primary]
        # OTTIMIZZAZIONE VELOCITÀ: disabilita il "thinking" di Gemini 3 flash
        # (riduce drasticamente la latenza) e, per gli OCR, forza output JSON
        # puro (niente markdown da ripulire, meno re-parsing).
        gen_cfg = {"temperature": 0, "thinkingConfig": {"thinkingBudget": 0}}
        if self._json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        parts = self._build_parts(message)
        last_err = "sconosciuto"
        # Budget totale limitato: evita il 502 del proxy su richieste troppo
        # lunghe. Meglio un errore chiaro e rapido che un timeout dell'ingress.
        deadline = time.monotonic() + 70.0
        with httpx.Client(timeout=45.0) as c:
            for model in candidates:
                if time.monotonic() > deadline:
                    break
                url = f"{GEMINI_REST}/{model}:generateContent"
                cfg = dict(gen_cfg)
                for attempt in range(3):
                    payload = {"contents": [{"parts": parts}], "generationConfig": cfg}
                    if self._system:
                        payload["systemInstruction"] = {"parts": [{"text": self._system}]}
                    try:
                        r = c.post(url, params={"key": key},
                                   headers={"Content-Type": "application/json"}, json=payload)
                    except httpx.RequestError as e:
                        last_err = f"timeout/connessione ({model}): {str(e)[:80]}"
                        break  # prova il prossimo modello
                    if r.status_code in (429, 503):
                        # Sovraccarico/limite: backoff esponenziale breve, ma solo
                        # se resta budget. Altrimenti passa subito al modello dopo.
                        last_err = f"{r.status_code} (sovraccarico {model})"
                        wait = min(2.0 * (2 ** attempt), 8.0)
                        if attempt < 2 and (time.monotonic() + wait) < deadline:
                            time.sleep(wait)
                            continue
                        break  # cambia modello
                    if r.status_code == 400:
                        # Una config opzionale (thinking/JSON) potrebbe non essere
                        # supportata dal modello: rimuovila e riprova subito. Così
                        # le ottimizzazioni non causano mai un errore bloccante.
                        if "thinkingConfig" in cfg or "responseMimeType" in cfg:
                            cfg.pop("thinkingConfig", None)
                            cfg.pop("responseMimeType", None)
                            continue
                        last_err = f"400: {r.text[:200]}"
                        break
                    if r.status_code >= 400:
                        last_err = f"{r.status_code}: {r.text[:200]}"
                        break  # errore non transitorio: prova il prossimo modello
                    data = r.json()
                    cands = data.get("candidates") or []
                    parts_out = (cands[0].get("content") or {}).get("parts") or [] if cands else []
                    txt = "".join(p.get("text", "") for p in parts_out)
                    if txt.strip():
                        return txt
                    last_err = "risposta vuota"
                    break
        raise RuntimeError(f"Gemini API non disponibile: {last_err}")

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
