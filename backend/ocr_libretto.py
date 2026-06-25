"""OCR libretto di circolazione italiano via Gemini 3 Flash."""
from __future__ import annotations
import base64
import json
import os
import re
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone


PROMPT = """Sei un OCR specializzato in libretti di circolazione (Carta di Circolazione) della
Motorizzazione Civile italiana. Estrai i dati e restituisci ESCLUSIVAMENTE un JSON valido
con questo schema:

{
  "targa": "stringa MAIUSCOLA senza spazi (es. AB123CD) o null",
  "telaio": "numero di telaio VIN (17 caratteri) o null",
  "marca": "stringa MAIUSCOLA (es. FIAT, AUDI) o null",
  "modello": "stringa MAIUSCOLA (es. PANDA 1.2) o null",
  "tipo_veicolo": "AUTOVETTURA | AUTOCARRO | MOTOCICLO | CICLOMOTORE | RIMORCHIO | TRATTORE | altro o null",
  "alimentazione": "BENZINA | DIESEL | GPL | METANO | ELETTRICA | IBRIDA | IBRIDA_BENZINA | IBRIDA_DIESEL | altro o null",
  "kw": "potenza in kW (numero) o null",
  "cv": "potenza in CV (numero) o null",
  "cilindrata": "cilindrata in cc (numero intero) o null",
  "data_immatricolazione": "YYYY-MM-DD o null",
  "intestatario": {
    "cognome_nome_o_ragione_sociale": "stringa MAIUSCOLA o null",
    "codice_fiscale_o_partita_iva": "stringa MAIUSCOLA o null",
    "indirizzo": "stringa MAIUSCOLA o null",
    "comune": "stringa MAIUSCOLA o null",
    "provincia": "sigla 2 lettere o null",
    "cap": "stringa o null"
  },
  "posti": "numero totale posti (intero) o null",
  "massa_complessiva": "massa massima a pieno carico in kg (intero) o null",
  "categoria_omologazione": "stringa (es. M1, N1) o null"
}

REGOLE:
- Tutti i campi sono opzionali — restituisci null se non leggibili
- Targhe in MAIUSCOLO senza spazi né trattini (es. AB123CD)
- Date sempre YYYY-MM-DD
- Potenze come numeri decimali se necessario (es. 55.0, non "55 kW")
- Non aggiungere testo prima o dopo il JSON
- Non includere markdown ```json```
"""


async def estrai_dati_libretto(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Restituisce dict con i campi estratti dal libretto."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY non configurata")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    image_content = ImageContent(image_base64=b64)

    chat = LlmChat(
        api_key=key,
        session_id=f"ocr-libretto-{os.urandom(4).hex()}",
        system_message="Estrai dati strutturati da libretti di circolazione italiani.",
    ).with_model("gemini", "gemini-3-flash-preview")

    msg = UserMessage(text=PROMPT, file_contents=[image_content])
    response_text = ""
    try:
        async for ev in chat.stream_message(msg):
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
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON non valido: {e}. Raw: {raw[:300]}") from e

    # Appiattisci la struttura per il frontend (DocumentiPolizzaTab si aspetta campi flat)
    flat = {
        "targa": data.get("targa"),
        "telaio": data.get("telaio"),
        "marca": data.get("marca"),
        "modello": data.get("modello"),
        "tipo_veicolo": data.get("tipo_veicolo"),
        "alimentazione": data.get("alimentazione"),
        "kw": data.get("kw"),
        "cv": data.get("cv"),
        "cilindrata": data.get("cilindrata"),
        "data_immatricolazione": data.get("data_immatricolazione"),
    }
    return flat
