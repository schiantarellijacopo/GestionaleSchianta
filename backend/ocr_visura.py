"""OCR visura camerale italiana via Gemini Vision (emergentintegrations).

Estrae dati ditta + amministratore/legale rappresentante dalla visura.
"""
from __future__ import annotations
import base64
import json
import os
import re
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent


PROMPT = """Sei un OCR specializzato in visure camerali italiane (Camera di Commercio).
Analizza il documento e restituisci ESCLUSIVAMENTE un JSON valido con questo schema:

{
  "ragione_sociale": "stringa o null",
  "forma_giuridica": "SRL | SAS | SNC | SPA | ditta individuale | altro o null",
  "partita_iva": "stringa 11 cifre o null",
  "codice_fiscale_ditta": "stringa o null",
  "rea": "stringa o null",
  "data_iscrizione_cciaa": "YYYY-MM-DD o null",
  "data_costituzione": "YYYY-MM-DD o null",
  "capitale_sociale": "stringa con cifra es '10.000,00 i.v.' o null",
  "indirizzo_sede": "stringa o null",
  "comune_sede": "stringa o null",
  "provincia_sede": "sigla 2 lettere o null",
  "cap_sede": "stringa o null",
  "telefono": "stringa o null",
  "pec": "stringa o null",
  "email": "stringa o null",
  "oggetto_sociale": "stringa breve (max 200 caratteri) o null",
  "codice_ateco": "stringa o null",
  "stato_attivita": "attiva | inattiva | cessata | null",
  "data_inizio_attivita": "YYYY-MM-DD o null",
  "numero_dipendenti": "intero o null",
  "amministratori": [
    {
      "ruolo": "Amministratore unico | Presidente | Consigliere | Socio | Legale rappresentante | altro",
      "cognome": "stringa o null",
      "nome": "stringa o null",
      "codice_fiscale": "16 caratteri o null",
      "data_nascita": "YYYY-MM-DD o null",
      "comune_nascita": "stringa o null",
      "provincia_nascita": "sigla 2 lettere o null",
      "indirizzo_residenza": "stringa o null",
      "comune_residenza": "stringa o null",
      "data_nomina": "YYYY-MM-DD o null",
      "poteri": "stringa breve o null"
    }
  ]
}

Regole:
- Tutti i campi opzionali, restituisci null se non leggibili
- Ragione sociale e cognomi/nomi in MAIUSCOLO senza accenti speciali
- Date sempre in formato YYYY-MM-DD
- Per amministratori restituisci array (anche con un solo elemento o vuoto se nessuno)
- Non aggiungere testo prima o dopo il JSON
- Non includere markdown ```json```
"""


async def estrai_dati_visura(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Restituisce dict con i campi estratti dalla visura camerale."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY non configurata")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    image_content = ImageContent(image_base64=b64)

    chat = LlmChat(
        api_key=key,
        session_id=f"ocr-visura-{os.urandom(4).hex()}",
        system_message="Estrai dati strutturati da visure camerali italiane.",
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

    raw = response_text.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Risposta non JSON: {raw[:300]}")
    data: dict = {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON non valido: {e}. Raw: {raw[:300]}") from e
    # normalizza valori vuoti
    def _clean(v):
        return v if v not in ("", "null", None) else None
    out = {k: _clean(v) for k, v in data.items() if k != "amministratori"}
    out["amministratori"] = [
        {k: _clean(v) for k, v in a.items()} for a in (data.get("amministratori") or [])
    ]
    return out
