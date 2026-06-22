"""OCR carta d'identità italiana via Gemini Vision (emergentintegrations).

Estrae dati anagrafici strutturati dall'immagine della CI.
"""
from __future__ import annotations
import base64
import json
import os
import re
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent


PROMPT = """Sei un OCR specializzato in documenti di identità italiani:
carta d'identità (cartacea ed elettronica), patente di guida, passaporto.
Analizza l'immagine e restituisci ESCLUSIVAMENTE un JSON valido:

{
  "tipo_documento": "carta_identita | patente | passaporto | null",
  "cognome": "stringa o null",
  "nome": "stringa o null",
  "sesso": "M | F | null",
  "data_nascita": "YYYY-MM-DD o null",
  "comune_nascita": "stringa o null",
  "provincia_nascita": "sigla 2 lettere o null",
  "codice_fiscale": "stringa 16 caratteri uppercase o null",
  "numero_documento": "stringa o null",
  "data_rilascio": "YYYY-MM-DD o null",
  "data_scadenza": "YYYY-MM-DD o null",
  "comune_emissione": "stringa (o 'MIT-UCO' per patenti, 'Questura di X' per passaporti) o null",
  "indirizzo_residenza": "stringa o null",
  "comune_residenza": "stringa o null",
  "cittadinanza": "stringa o null",
  "categorie_patente": "lista categorie es. ['B','BE'] (solo se patente) o null"
}

Regole:
- Tutti i campi opzionali. Restituisci null se non leggibili
- Cognome/Nome in MAIUSCOLO senza accenti speciali
- Date sempre YYYY-MM-DD
- Non aggiungere testo prima o dopo il JSON
- Non includere markdown ```json```
"""


async def estrai_dati_ci(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Restituisce dict con i campi estratti dalla CI."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY non configurata")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    image_content = ImageContent(image_base64=b64)

    chat = LlmChat(
        api_key=key,
        session_id=f"ocr-ci-{os.urandom(4).hex()}",
        system_message="Estrai dati strutturati da documenti italiani.",
    ).with_model("gemini", "gemini-3-flash-preview")

    msg = UserMessage(text=PROMPT, file_contents=[image_content])
    response_text = ""
    try:
        async for ev in chat.stream_message(msg):
            from emergentintegrations.llm.chat import TextDelta, StreamDone
            if isinstance(ev, TextDelta):
                response_text += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        raise RuntimeError(f"Errore chiamata Gemini: {e}") from e

    # Pulizia: rimuovi eventuali fenced code block
    raw = response_text.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    # Trova primo blocco JSON
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Risposta non JSON: {raw[:300]}")
    data: dict = {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON non valido: {e}. Raw: {raw[:300]}") from e

    return {k: (v if v not in ("", "null") else None) for k, v in data.items()}
