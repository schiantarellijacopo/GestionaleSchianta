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
  "imposte_totali": "numero decimale (SOLO imposte assicurative, SENZA il contributo SSN, GIÀ al netto del contributo forzoso) o null",
  "contributo_ssn": "numero decimale (Contributo SSN / Servizio Sanitario Nazionale) o null",
  "contributo_forzoso": "numero decimale del 'Contributo forzoso ex comma 63, L. n. 199/2025' (importo da SOTTRARRE dalle imposte) o null",
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
      "premio_netto": "numero decimale: premio NETTO/imponibile di QUESTA garanzia o null",
      "imposte": "numero decimale: imposte/tasse di QUESTA garanzia o null",
      "premio": "numero decimale: importo complessivo di questa garanzia se indicato come voce unica o null"
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
- TARGA (PRIORITÀ MASSIMA): la targa del veicolo è riportata IN ALTO nell'INTESTAZIONE del documento, accanto al numero di polizza, nella riga "Targa / Telaio n. XXXXXXXX" (es. "Polizza n. 184643597  Targa / Telaio n. VA164193" → targa = VA164193). USA SEMPRE questo valore come veicolo.targa: ha PRIORITÀ ASSOLUTA su qualsiasi altra targa o codice veicolo trovato altrove nel documento (tabelle, sezioni dati veicolo, ecc.). Copia il valore ESATTAMENTE come stampato nell'intestazione.
- Durata: se vedi "dalle ore 24 del GG/MM/AAAA alle ore 24 del GG/MM/AAAA" (oppure "dal GG/MM/AAAA al GG/MM/AAAA"), la PRIMA data è data_decorrenza, la SECONDA è data_scadenza.
- Premi (converti virgola→punto): "premio netto"→premio_netto_totale; "imposte"/"tasse"→imposte_totali; "diritti"→diritti; "totale" / "totale da pagare" / "premio lordo"→premio_lordo_totale.
- premio_lordo_totale è OBBLIGATORIO: riporta SEMPRE il totale del contratto, cercando "Totale", "Totale da pagare", "Premio da pagare", "Premio annuale totale", "Premio lordo". È il numero più grande della sezione premi. Non lasciarlo mai null se nel documento compare un totale.
- NON DUPLICARE le righe garanzia: ogni garanzia va elencata UNA SOLA VOLTA in `garanzie`. Non ripetere la stessa riga (stessa descrizione/importi) più volte.
- DETTAGLIO PER GARANZIA: le polizze auto/multirischio hanno una tabella con una RIGA PER GARANZIA (RCA, Incendio, Furto, Eventi Atmosferici, Grandine, Kasko, Cristalli, Assistenza, ecc.) con per ciascuna il premio netto e le imposte. Per OGNI garanzia compila SEMPRE `premio_netto` e `imposte` con i valori di QUELLA riga.
- premio_netto_totale = SOMMA dei `premio_netto` di TUTTE le garanzie. imposte_totali (prima del contributo forzoso) = SOMMA delle `imposte` di TUTTE le garanzie. NON usare un singolo valore letto male: calcola la somma riga per riga.
- Contributo forzoso: la voce "Contributo forzoso ex comma 63, L. n. 199/2025" (o "ex comma 63") va messa in `contributo_forzoso` e VA SOTTRATTA dalle imposte. Quindi imposte_totali = (somma imposte garanzie) − contributo_forzoso.
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
    _riconcilia_premi(data)
    return data


def _num(x):
    """Coerce un valore OCR in float (gestisce None, stringhe con €/virgole)."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("€", "").replace(" ", "").strip()
    if not s:
        return None
    # formato italiano: migliaia con '.' e decimali con ',' → normalizza
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _riconcilia_premi(data: dict) -> None:
    """Ricalcola i totali di premio in modo deterministico dalle garanzie.

    - premio_netto_totale = somma dei premi netti di ogni garanzia (se disponibili)
    - imposte_totali = somma delle imposte di ogni garanzia − contributo forzoso
    - premio_lordo_totale = netto + imposte + ssn + diritti (ricalcolato se abbiamo
      ricostruito le componenti)
    """
    gar = data.get("garanzie") or []
    # DE-DUPLICA le righe garanzia: l'LLM (gemini) a volte ripete la STESSA riga,
    # gonfiando le somme (netto/imposte raddoppiati). Teniamo una sola riga per chiave.
    seen = set()
    gar_u = []
    for g in gar:
        if not isinstance(g, dict):
            continue
        key = (
            str(g.get("descrizione") or g.get("garanzia") or g.get("ramo") or g.get("nome") or "").strip().upper(),
            _num(g.get("premio_netto")),
            _num(g.get("imposte")),
        )
        if key in seen:
            continue
        seen.add(key)
        gar_u.append(g)
    netti = [n for n in (_num(g.get("premio_netto")) for g in gar_u) if n is not None]
    imposte = [i for i in (_num(g.get("imposte")) for g in gar_u) if i is not None]

    cf = _num(data.get("contributo_forzoso")) or 0.0
    ssn = _num(data.get("contributo_ssn")) or 0.0
    diritti = _num(data.get("diritti")) or 0.0
    lordo_letto = _num(data.get("premio_lordo_totale"))  # totale letto dal PDF

    # NETTO: dalle garanzie de-duplicate se itemizzato, altrimenti dal totale letto
    if len(netti) >= 2:
        data["premio_netto_totale"] = round(sum(netti), 2)
    netto = _num(data.get("premio_netto_totale"))
    if netto is None and netti:
        netto = round(sum(netti), 2)
        data["premio_netto_totale"] = netto

    imposte_righe = round(sum(imposte), 2) if len(imposte) >= 2 else None

    # LORDO di riferimento: se non è stato letto dal PDF, ricostruiscilo dalle garanzie
    # DE-DUPLICATE, così abbiamo SEMPRE un ancoraggio affidabile per la regola primaria.
    lordo_ref = lordo_letto
    if lordo_ref is None and netto is not None and imposte_righe is not None:
        lordo_ref = round(netto + max(imposte_righe - cf, 0.0) + ssn + diritti, 2)
        data["premio_lordo_totale"] = lordo_ref

    # IMPOSTE — REGOLA PRIMARIA richiesta: Imposte = Lordo − Netto − SSN − Diritti.
    # Deterministica e immune al non-determinismo dell'LLM (valori doppi/righe ripetute).
    if lordo_ref is not None and netto is not None:
        data["imposte_totali"] = round(max(lordo_ref - netto - ssn - diritti, 0.0), 2)
    elif imposte_righe is not None:
        data["imposte_totali"] = round(max(imposte_righe - cf, 0.0), 2)
        if lordo_letto is None and netto is not None:
            data["premio_lordo_totale"] = round(netto + data["imposte_totali"] + ssn + diritti, 2)
    else:
        imp_llm = _num(data.get("imposte_totali"))
        if imp_llm is not None:
            data["imposte_totali"] = round(max(imp_llm - cf, 0.0), 2)
        if lordo_letto is None and netto is not None:
            data["premio_lordo_totale"] = round(netto + (data.get("imposte_totali") or 0.0) + ssn + diritti, 2)

    # Collapse di sicurezza: se netto+imposte+ssn+diritti non quadra col lordo (scarto
    # > 0,50 €, tipico di righe duplicate non colte), deriva le imposte come residuo.
    lordo_r = _num(data.get("premio_lordo_totale"))
    netto_r = _num(data.get("premio_netto_totale"))
    imp_r = _num(data.get("imposte_totali")) or 0.0
    if lordo_r and netto_r is not None:
        residuo = round(lordo_r - netto_r - ssn - diritti, 2)
        if residuo >= -0.01 and abs((netto_r + imp_r + ssn + diritti) - lordo_r) > 0.5:
            data["imposte_totali"] = round(max(residuo, 0.0), 2)
