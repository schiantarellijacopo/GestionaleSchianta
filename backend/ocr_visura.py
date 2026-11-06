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
      "quota_valore": "quota posseduta in euro, solo il numero es 6000 (dal campo 'Quota: 6.000,00 Valuta: Euro') o null",
      "quota_percentuale": "percentuale di possesso es 60 (senza simbolo %) o null",
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
- Nella sezione "SOCI" / "TITOLARI DI DIRITTI SU QUOTE E AZIONI" e per i soci ACCOMANDATARI e ACCOMANDANTI delle S.a.s. estrai SEMPRE TUTTI i soci (sia accomandatari sia accomandanti), ciascuno con il proprio codice fiscale.
- Per ogni socio riporta la quota in euro nel campo quota_valore (es. dal testo "Quota: 6.000,00 Valuta: Euro" → 6000) e, se presente, anche quota_percentuale. Se la percentuale non è indicata lasciala null: verrà calcolata a parte sul capitale sociale.
- NON unire i soci: anche se la visura elenca prima i nomi e poi in un'altra sezione le quote, abbina la quota al socio corretto tramite il codice fiscale.
- Per soci restituisci array (vuoto se non presenti)
- Non aggiungere testo prima o dopo il JSON
- Non includere markdown ```json```
"""


def _pdf_to_images(pdf_bytes: bytes, max_pages: int = 12, zoom: float = 2.0) -> list[bytes]:
    """Converte un PDF in una lista di PNG (una per pagina)."""
    try:
        import pymupdf as _fitz  # type: ignore
    except ImportError:
        import fitz as _fitz  # type: ignore
    imgs: list[bytes] = []
    doc = _fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        mat = _fitz.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            imgs.append(page.get_pixmap(matrix=mat).tobytes("png"))
    finally:
        doc.close()
    return imgs


async def estrai_dati_visura(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Restituisce dict con i campi estratti dalla visura camerale.

    Se il file è un PDF multi-pagina viene convertito in un'immagine per pagina
    (soci/quote e amministratori sono spesso nelle pagine interne): inviare solo
    la prima pagina farebbe perdere questi dati.
    """
    key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Nessuna chiave LLM configurata (EMERGENT_LLM_KEY o GEMINI_API_KEY)")

    is_pdf = (mime_type or "").lower().endswith("pdf") or image_bytes[:4] == b"%PDF"
    page_images: list[bytes] = []
    if is_pdf:
        try:
            page_images = _pdf_to_images(image_bytes)
        except Exception:
            page_images = []
    if not page_images:
        page_images = [image_bytes]  # immagine singola o fallback

    image_contents = [ImageContent(image_base64=base64.b64encode(p).decode("ascii")) for p in page_images]

    chat = LlmChat(
        api_key=key,
        session_id=f"ocr-visura-{os.urandom(4).hex()}",
        system_message="Estrai dati strutturati da visure camerali italiane.",
    ).with_model("gemini", "gemini-3-flash-preview").with_json()

    msg = UserMessage(text=PROMPT, file_contents=image_contents)
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
