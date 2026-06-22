"""OCR polizza assicurativa italiana via Gemini Vision (emergentintegrations).

Estrae dati strutturati di polizze italiane (qualsiasi compagnia).
"""
from __future__ import annotations
import base64
import json
import os
import re
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent


PROMPT = """Sei un OCR specializzato in polizze assicurative italiane (Cattolica, UnipolSai, Generali,
Allianz, Reale Mutua, AXA, Zurich, Genertel, Vittoria, ecc.).
Analizza il documento e restituisci ESCLUSIVAMENTE un JSON valido con questo schema:

{
  "numero_polizza": "stringa o null",
  "compagnia": "stringa (nome compagnia esattamente come scritto) o null",
  "ramo": "RCA | RCAUTO | INFORTUNI | INFR | VITA | CASA | INCENDIO | FURTO | RC_PROFESSIONALE | SANITARIA | TUTELA_GIUDIZIARIA | altro o null",
  "prodotto": "nome commerciale del prodotto (es. 'Cattolica Auto Plus') o null",
  "data_decorrenza": "YYYY-MM-DD (data di effetto) o null",
  "data_scadenza": "YYYY-MM-DD o null",
  "data_emissione": "YYYY-MM-DD o null",
  "frazionamento": "annuale | semestrale | quadrimestrale | trimestrale | mensile | unica o null",
  "tacito_rinnovo": "true | false | null",
  "premio_lordo_totale": "numero decimale o null",
  "premio_netto_totale": "numero decimale o null",
  "imposte_totali": "numero decimale o null",
  "provvigioni_totali": "numero decimale o null",
  "diritti": "numero decimale o null",
  "contraente": {
    "cognome_nome_o_ragione_sociale": "stringa o null",
    "codice_fiscale": "16 caratteri o null",
    "partita_iva": "stringa o null",
    "indirizzo": "stringa o null",
    "comune": "stringa o null",
    "provincia": "sigla 2 lettere o null",
    "cap": "stringa o null"
  },
  "assicurato": {
    "cognome_nome_o_ragione_sociale": "stringa o null se coincide con contraente",
    "codice_fiscale": "stringa o null"
  },
  "veicolo": {
    "targa": "stringa o null",
    "marca": "stringa o null",
    "modello": "stringa o null",
    "tipo_veicolo": "AUTOVETTURA | AUTOCARRO | MOTOCICLO | CICLOMOTORE | altro o null",
    "alimentazione": "BENZINA | DIESEL | GPL | METANO | ELETTRICA | IBRIDA | altro o null",
    "uso_veicolo": "PRIVATO | USO TERZI | altro o null",
    "data_immatricolazione": "YYYY-MM-DD o null",
    "cilindrata": "numero o null",
    "cv_fiscali": "numero o null",
    "kw": "numero o null",
    "numero_posti": "numero o null"
  },
  "bonus_malus": {
    "classe_provenienza": "stringa o null",
    "classe_assegnata": "stringa o null",
    "classe_cu": "stringa o null"
  },
  "garanzie": [
    {
      "codice": "RCA | FUR | INC | KASKO | CRISTALLI | ASSISTENZA | altro o stringa breve",
      "descrizione": "stringa",
      "massimale": "stringa o null",
      "franchigia": "stringa o null",
      "premio": "numero decimale o null"
    }
  ],
  "valore_veicolo": "numero o null",
  "valore_accessori": "numero o null",
  "guida_esperta": "true | false | null",
  "guida_esclusiva": "true | false | null",
  "rinuncia_rivalsa": "true | false | null"
}

Regole:
- Tutti i campi opzionali. Restituisci null se non leggibili
- Targhe in MAIUSCOLO senza spazi (es. AB123CD)
- Cognomi/nomi in MAIUSCOLO
- Date sempre YYYY-MM-DD
- Premi e importi come numeri decimali (es. 850.50, non "850,50 €")
- garanzie: array, può essere vuoto se non visibili
- Non aggiungere testo prima o dopo il JSON
- Non includere markdown ```json```
"""


async def estrai_dati_polizza(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Restituisce dict con i campi estratti dalla polizza."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY non configurata")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    image_content = ImageContent(image_base64=b64)

    chat = LlmChat(
        api_key=key,
        session_id=f"ocr-polizza-{os.urandom(4).hex()}",
        system_message="Estrai dati strutturati da polizze assicurative italiane.",
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
    return data
