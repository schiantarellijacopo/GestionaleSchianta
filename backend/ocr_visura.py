"""OCR visura camerale italiana via Gemini Vision (emergentintegrations).

Estrae dati ditta + amministratore/legale rappresentante dalla visura.
"""
from __future__ import annotations
import base64
import json
import os
import re
from llm_compat import LlmChat, UserMessage, ImageContent


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
  "soci": [
    {
      "denominazione": "ragione sociale del socio se persona giuridica, altrimenti null",
      "cognome": "stringa o null (se persona fisica)",
      "nome": "stringa o null (se persona fisica)",
      "codice_fiscale": "stringa o null",
      "quota_percentuale": "numero percentuale di possesso es 60 (senza simbolo %) o null",
      "tipo": "socio accomandatario | socio accomandante | socio unico | socio | nudo proprietario | usufruttuario | altro"
    }
  ],
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
- Nella sezione "SOCI" / "TITOLARI DI DIRITTI SU QUOTE E AZIONI" / soci accomandatari e accomandanti estrai TUTTI i soci con la relativa quota di possesso in percentuale (campo quota_percentuale, solo il numero). Se la quota è espressa in valore (euro) e non in percentuale, calcolala sul capitale sociale quando possibile, altrimenti null.
- Per soci restituisci array (vuoto se non presenti)
- Non aggiungere testo prima o dopo il JSON
- Non includere markdown ```json```
"""


async def estrai_dati_visura(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Restituisce dict con i campi estratti dalla visura camerale."""
    key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Nessuna chiave LLM configurata (EMERGENT_LLM_KEY o GEMINI_API_KEY)")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    image_content = ImageContent(image_base64=b64)

    chat = LlmChat(
        api_key=key,
        session_id=f"ocr-visura-{os.urandom(4).hex()}",
        system_message="Estrai dati strutturati da visure camerali italiane.",
    ).with_model("gemini", "gemini-3-flash-preview").with_json()

    msg = UserMessage(text=PROMPT, file_contents=[image_content])
    response_text = ""
    try:
        async for ev in chat.stream_message(msg):
            from llm_compat import TextDelta, StreamDone
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
    out = {k: _clean(v) for k, v in data.items() if k not in ("amministratori", "soci")}
    out["amministratori"] = [
        {k: _clean(v) for k, v in a.items()} for a in (data.get("amministratori") or [])
    ]
    out["soci"] = [
        {k: _clean(v) for k, v in s.items()} for s in (data.get("soci") or [])
    ]
    return out
