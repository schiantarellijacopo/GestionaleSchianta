"""OCR polizza assicurativa italiana via Gemini Vision (emergentintegrations).

Estrae dati strutturati di polizze italiane (qualsiasi compagnia).
"""
from __future__ import annotations
import base64
import json
import os
import re
from llm_compat import LlmChat, UserMessage, ImageContent


PROMPT = """Sei un OCR specializzato in polizze assicurative italiane (Cattolica, UnipolSai, Generali,
Allianz, Reale Mutua, AXA, Zurich, Genertel, Vittoria, ecc.).
Analizza il documento e restituisci ESCLUSIVAMENTE un JSON valido con questo schema:

{
  "numero_polizza": "stringa o null",
  "sostituisce_polizza": "numero della polizza sostituita (campo 'Sostituisce polizza') o null",
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
  "imposte_totali": "numero decimale (SOLO imposte assicurative, SENZA il contributo SSN) o null",
  "contributo_ssn": "numero decimale (Contributo SSN / Servizio Sanitario Nazionale) o null",
  "provvigioni_totali": "numero decimale o null",
  "diritti": "numero decimale o null",
  "contraente": {
    "cognome_nome_o_ragione_sociale": "stringa o null",
    "codice_fiscale": "16 caratteri o null",
    "partita_iva": "stringa o null",
    "email": "indirizzo email del contraente o null",
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
- Il documento può avere PIÙ PAGINE: ti vengono fornite più immagini (una per pagina). Cerca i dati in TUTTE le immagini.
- numero_polizza: cerca etichette tipo "Polizza n.", "N. polizza", "Numero polizza", "Contratto n.", "Certificato n.", "Polizza numero". È di solito un numero lungo (es. 1001870957).
- sostituisce_polizza: se è presente un campo "Sostituisce polizza" (o "Sostituisce la polizza n.", "In sostituzione della polizza") riporta il NUMERO della polizza sostituita. Se il campo è vuoto o assente, null.
- "ID. Veicolo" / "ID Veicolo" / "Identificativo veicolo": se contiene un codice tipo targa (es. DS973SV) usalo come veicolo.targa.
- Durata: se vedi "dalle ore 24 del GG/MM/AAAA alle ore 24 del GG/MM/AAAA" (oppure "dal GG/MM/AAAA al GG/MM/AAAA"), la PRIMA data è data_decorrenza, la SECONDA è data_scadenza.
- Premi (converti virgola→punto): "premio netto"→premio_netto_totale; "imposte"/"tasse"→imposte_totali; "diritti"→diritti; "totale" / "totale da pagare" / "premio lordo"→premio_lordo_totale.
- Contributo SSN: la voce "Contributo SSN", "Contributo S.S.N.", "Servizio Sanitario Nazionale" (tipica dei rami RC Auto) va messa SOLO in `contributo_ssn` e NON va inclusa in imposte_totali. imposte_totali deve contenere esclusivamente le imposte assicurative.
- Se il totale non è esplicito, premio_lordo_totale = premio_netto_totale + imposte_totali + contributo_ssn + diritti.
- UCA / "UcaSicura" / "tutela legale" → ramo = TUTELA_GIUDIZIARIA.
- Targhe in MAIUSCOLO senza spazi (es. AB123CD)
- Cognomi/nomi in MAIUSCOLO
- Date sempre YYYY-MM-DD (converti da GG/MM/AAAA)
- Premi e importi come numeri decimali (es. 850.50, non "850,50 €")
- garanzie: array, può essere vuoto se non visibili
- Non aggiungere testo prima o dopo il JSON
- Non includere markdown ```json```
"""


def pdf_to_page_images(pdf_bytes: bytes, max_pages: int = 10, resolution: int = 150) -> list[bytes]:
    """Converte un PDF in una lista di immagini JPEG (una per pagina),
    ottimizzate per OCR veloce (lato lungo max 1600px, JPEG q80)."""
    from io import BytesIO
    import pdfplumber
    out: list[bytes] = []
    maxd = 1600
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:max_pages]:
            im = page.to_image(resolution=resolution).original.convert("RGB")
            if max(im.size) > maxd:
                r = maxd / max(im.size)
                im = im.resize((int(im.width * r), int(im.height * r)))
            buf = BytesIO()
            im.save(buf, format="JPEG", quality=80, optimize=True)
            out.append(buf.getvalue())
    return out


async def estrai_dati_polizza(image_bytes, mime_type: str = "image/jpeg") -> dict:
    """Estrae i campi dalla polizza. `image_bytes` può essere bytes (singola pagina)
    o una lista di bytes (più pagine → più immagini inviate a Gemini)."""
    key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Nessuna chiave LLM configurata (EMERGENT_LLM_KEY o GEMINI_API_KEY)")

    pages = image_bytes if isinstance(image_bytes, (list, tuple)) else [image_bytes]
    image_contents = [ImageContent(image_base64=base64.b64encode(p).decode("ascii")) for p in pages]

    chat = LlmChat(
        api_key=key,
        session_id=f"ocr-polizza-{os.urandom(4).hex()}",
        system_message="Estrai dati strutturati da polizze assicurative italiane.",
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
    return data
