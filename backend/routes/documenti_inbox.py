"""Documenti Inbox — caricamento e OCR di documenti generici.

L'utente carica una foto/PDF di qualsiasi documento (carta d'identità, patente,
codice fiscale, libretto, polizza, fattura). Il sistema:

1. Classifica automaticamente il tipo di documento via Gemini 3 Flash
2. Estrae i dati strutturati pertinenti
3. Suggerisce dove salvare il file (anagrafica / polizza) e quali campi auto-compilare
4. L'utente conferma → il documento viene archiviato come allegato + i dati applicati
"""
from __future__ import annotations
import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import current_user, require_user
from database import db
from db_models import _now_iso, Allegato
import storage as obj_storage


router = APIRouter()


PROMPT_CLASSIFICA = """Sei un sistema di OCR e classificazione documenti italiani. Analizza l'immagine
e restituisci ESCLUSIVAMENTE un JSON valido con questo schema:

{
  "tipo_documento": "carta_identita | patente | passaporto | codice_fiscale | tessera_sanitaria | visura_camerale | mandato_sdd | libretto | polizza | condizioni | appendice | atto_vendita | quietanza | mup | questionario | preventivo | fattura | cid | perizia | denuncia | altro",
  "confidenza": "alta | media | bassa",
  "foto_volto_bbox": {
    "x": "numero 0-1 (sx normalizzato) o null se assente",
    "y": "numero 0-1 (top normalizzato) o null",
    "w": "numero 0-1 (larghezza normalizzata) o null",
    "h": "numero 0-1 (altezza normalizzata) o null"
  },
  "dati": {
    // SE carta_identita o codice_fiscale o tessera_sanitaria o passaporto:
    "cognome": "MAIUSCOLO o null",
    "nome": "MAIUSCOLO o null",
    "codice_fiscale": "CF italiano MAIUSCOLO 16 caratteri o null",
    "data_nascita": "YYYY-MM-DD o null",
    "luogo_nascita": "MAIUSCOLO o null",
    "sesso": "M | F | null",
    "numero_documento": "numero del documento o null",
    "data_emissione": "YYYY-MM-DD o null",
    "data_scadenza": "YYYY-MM-DD o null",
    "comune_emissione": "comune/ente di emissione del documento (es. Comune di X, 'MIT-UCO' per patenti, 'Questura di X' per passaporti) o null",
    "cittadinanza": "stringa MAIUSCOLA o null",
    // SE patente:
    "categorie_patente": "lista di categorie (es. B, C+E) o null",
    // SE libretto:
    "targa": "stringa MAIUSCOLA o null",
    "telaio": "VIN 17 caratteri o null",
    "marca": "MAIUSCOLO o null",
    "modello": "MAIUSCOLO o null",
    // SE polizza / libretto / quietanza / appendice / condizioni / mup / questionario / preventivo:
    "numero_polizza": "numero del CONTRATTO/polizza (NON la P.IVA della compagnia) o null",
    "compagnia": "ragione sociale della COMPAGNIA assicuratrice (es. GROUPAMA, CATTOLICA, UNIPOL) MAIUSCOLO o null",
    "contraente_cognome": "COGNOME del CONTRAENTE/assicurato persona fisica (MAI la compagnia) o null",
    "contraente_nome": "NOME del CONTRAENTE/assicurato persona fisica o null",
    "contraente_ragione_sociale": "ragione sociale del CONTRAENTE se è un'azienda (MAI la compagnia assicuratrice) o null",
    "contraente_codice_fiscale": "CODICE FISCALE del CONTRAENTE/cliente (16 caratteri persona, MAIUSCOLO) o null",
    "contraente_partita_iva": "PARTITA IVA del CONTRAENTE/cliente azienda (11 cifre, NON quella della compagnia) o null",
    "premio_lordo": "numero decimale o null",
    "decorrenza": "YYYY-MM-DD o null",
    "scadenza": "YYYY-MM-DD o null",
    // SE fattura:
    "numero_fattura": "stringa o null",
    "fornitore": "MAIUSCOLO o null",
    "data_fattura": "YYYY-MM-DD o null",
    "importo_totale": "numero decimale o null"
  }
}

REGOLE:
- LIBRETTO di circolazione: la TARGA è nel campo "A" (in alto). Restituiscila in
  MAIUSCOLO SENZA spazi né trattini (es. 'FR798LT', 'AB12345', 'MI123456').
  Le targhe auto italiane moderne hanno 2 LETTERE + 3 CIFRE + 2 LETTERE: nelle
  posizioni delle lettere non usare mai cifre e viceversa. Attenzione a NON confondere
  la lettera O con lo zero 0, la I con 1, la B con 8, la S con 5, la Z con 2.
  Il TELAIO (VIN, campo "E", 17 caratteri) è DIVERSO dalla targa: non scambiarli.
- Restituisci null per i campi non leggibili o non pertinenti
- Date sempre YYYY-MM-DD
- POLIZZE/QUIETANZE/APPENDICI/LIBRETTI: distingui SEMPRE la COMPAGNIA assicuratrice
  (es. GROUPAMA, CATTOLICA, UNIPOL, ALLIANZ…) dal CONTRAENTE (il cliente assicurato).
  NON mettere MAI il nome della compagnia nei campi cognome/nome/contraente_*.
  Il campo "compagnia" è l'assicuratore; i campi "contraente_*" sono la persona/azienda
  assicurata. Non usare la Partita IVA della compagnia come numero_polizza né come
  contraente_partita_iva: il CODICE FISCALE / P.IVA nei campi contraente_* deve essere
  SEMPRE quello del CLIENTE assicurato, mai dell'assicuratore.
- Per la CARTA D'IDENTITÀ italiana (anche elettronica CIE): l'immagine può contenere FRONTE e RETRO impilati.
  Cerca in TUTTO il documento (anche nella parte bassa/retro):
  * "COMUNE DI EMISSIONE" / "COMUNE DI" / "MUNICIPALITY" → campo comune_emissione (es. TIRANO)
  * "DATA DI EMISSIONE" / "DATA DI RILASCIO" / "EMISSIONE" / "ISSUING" → campo data_emissione
  * "DATA DI SCADENZA" / "SCADENZA" / "EXPIRY" → campo data_scadenza
  Le date sulla CI italiana sono in formato GG.MM.AAAA: convertile in YYYY-MM-DD.
- foto_volto_bbox: SOLO per carta_identita/patente/passaporto/tessera_sanitaria/codice_fiscale.
  Coordinate normalizzate 0-1 della regione rettangolare che contiene la foto del VOLTO del titolare
  (il ritratto fotografico grande, NON la firma né l'impronta). Fornisci SEMPRE il bbox se il volto è visibile.
  Restituisci null/null/null/null solo se il documento non ha una foto del volto.
- Niente testo prima/dopo, niente markdown
"""


def _norm_bbox(bbox):
    """Normalizza il bbox del volto a chiavi {x,y,w,h} (float 0-1).
    Il modello può restituire w/h oppure width/height: accetta entrambi."""
    if not isinstance(bbox, dict):
        return None
    def _f(*keys):
        for k in keys:
            v = bbox.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
        return None
    x, y = _f("x"), _f("y")
    w, h = _f("w", "width"), _f("h", "height")
    if None in (x, y, w, h):
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def _detect_face_crop(img):
    """Rileva il volto del titolare con OpenCV (Haar cascade) e ritorna il ritaglio
    PIL del volto più grande (con padding), oppure None se nessun volto trovato.
    Affidabile per la foto ritratto di carte d'identità/patenti."""
    try:
        import cv2
        import numpy as np
        arr = np.array(img)  # RGB
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        cascade_path = os.path.join(os.path.dirname(cv2.__file__), "data",
                                    "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                         minSize=(60, 60))
        if len(faces) == 0:
            return None
        # volto più grande = ritratto principale
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        W, H = img.size
        padx, pady = int(w * 0.35), int(h * 0.45)
        left = max(0, x - padx)
        top = max(0, y - pady)
        right = min(W, x + w + padx)
        bottom = min(H, y + h + pady)
        return img.crop((left, top, right, bottom))
    except Exception as e:
        logging.warning("Face detection fallita: %s", e)
        return None




async def _convert_pdf_to_jpeg(contents: bytes) -> tuple[bytes, str]:
    import pdfplumber
    from PIL import Image
    with pdfplumber.open(BytesIO(contents)) as pdf:
        if not pdf.pages:
            raise HTTPException(400, "PDF vuoto")
        # Renderizza fino a 3 pagine (fronte/retro dei documenti) e le impila
        # verticalmente in un'unica immagine, così l'OCR vede TUTTO il documento
        # (es. il retro della carta d'identità con comune e data di emissione).
        imgs = []
        for page in pdf.pages[:3]:
            imgs.append(page.to_image(resolution=150).original.convert("RGB"))
        if len(imgs) == 1:
            combined = imgs[0]
        else:
            width = max(im.width for im in imgs)
            scaled = []
            for im in imgs:
                if im.width != width:
                    nh = int(im.height * (width / im.width))
                    im = im.resize((width, nh))
                scaled.append(im)
            total_h = sum(im.height for im in scaled)
            combined = Image.new("RGB", (width, total_h), (255, 255, 255))
            yoff = 0
            for im in scaled:
                combined.paste(im, (0, yoff))
                yoff += im.height
        out = BytesIO()
        # Downscale finale: larghezza max 1400px → OCR più rapido
        if combined.width > 1400:
            r = 1400 / combined.width
            combined = combined.resize((1400, int(combined.height * r)))
        combined.save(out, format="JPEG", quality=80, optimize=True)
        return out.getvalue(), "image/jpeg"


async def _ocr_classifica(image_bytes: bytes, mime: str) -> dict:
    from llm_compat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
    key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise HTTPException(503, "Nessuna chiave LLM configurata (EMERGENT_LLM_KEY o GEMINI_API_KEY)")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    chat = LlmChat(
        api_key=key,
        session_id=f"docinbox-{os.urandom(4).hex()}",
        system_message="Sei un OCR/classificatore di documenti italiani.",
    ).with_model("gemini", "gemini-3-flash-preview").with_json()
    msg = UserMessage(text=PROMPT_CLASSIFICA, file_contents=[ImageContent(image_base64=b64)])
    resp = ""
    try:
        async for ev in chat.stream_message(msg):
            if isinstance(ev, TextDelta): resp += ev.content
            elif isinstance(ev, StreamDone): break
    except Exception as e:
        raise HTTPException(503, f"OCR fallito: {e}")
    raw = re.sub(r"^```(?:json)?|```$", "", resp.strip(), flags=re.IGNORECASE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise HTTPException(502, f"Risposta non JSON: {raw[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise HTTPException(502, f"JSON malformato: {e}")


_PROMPT_LIBRETTO = """Sei un OCR di libretti di circolazione italiani (carta di circolazione).
Estrai i dati del veicolo e restituisci SOLO questo JSON:
{
  "targa": "MAIUSCOLO o null",
  "telaio": "VIN o null",
  "marca": "MAIUSCOLO o null (campo D.1)",
  "modello": "MAIUSCOLO o null (campo D.3 / tipo-variante-versione)",
  "categoria": "AUTOVETTURA | AUTOCARRO | MOTOCICLO | CICLOMOTORE | RIMORCHIO | null",
  "alimentazione": "BENZINA | DIESEL | GPL | METANO | ELETTRICA | IBRIDA | null (campo P.3)",
  "cilindrata": "numero cc o null (campo P.1)",
  "potenza_kw": "numero kW o null (campo P.2)",
  "potenza_cv": "numero CV fiscali o null",
  "posti": "numero posti o null (campo S.1)",
  "data_immatricolazione": "YYYY-MM-DD o null (campo B)"
}
REGOLE: null per campi non leggibili; date YYYY-MM-DD; nessun markdown, nessun testo extra."""


@router.post("/documenti-inbox/ocr-veicolo")
async def ocr_veicolo(
    file: UploadFile = File(...),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """OCR dedicato al libretto di circolazione: estrae i dati veicolo per
    auto-compilare l'applicazione del Libro Matricola."""
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 20 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    if ct == "application/pdf":
        img_bytes, img_ct = await _convert_pdf_to_jpeg(contents)
    elif ct.startswith("image/"):
        img_bytes, img_ct = contents, ct
    else:
        raise HTTPException(400, "Formato non supportato (PDF/JPG/PNG/WEBP)")

    from llm_compat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
    key = os.environ.get("EMERGENT_LLM_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise HTTPException(503, "Nessuna chiave LLM configurata (EMERGENT_LLM_KEY o GEMINI_API_KEY)")
    b64 = base64.b64encode(img_bytes).decode("ascii")
    chat = LlmChat(
        api_key=key, session_id=f"ocrveic-{os.urandom(4).hex()}",
        system_message="Sei un OCR di libretti di circolazione italiani.",
    ).with_model("gemini", "gemini-3-flash-preview").with_json()
    msg = UserMessage(text=_PROMPT_LIBRETTO, file_contents=[ImageContent(image_base64=b64)])
    resp = ""
    try:
        async for ev in chat.stream_message(msg):
            if isinstance(ev, TextDelta):
                resp += ev.content
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        raise HTTPException(503, f"OCR fallito: {e}")
    raw = re.sub(r"^```(?:json)?|```$", "", resp.strip(), flags=re.IGNORECASE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise HTTPException(502, "Impossibile leggere il libretto")
    try:
        return {"ok": True, "veicolo": json.loads(m.group(0))}
    except json.JSONDecodeError:
        raise HTTPException(502, "Dati libretto non leggibili")



_PLATE_RX = re.compile(r"\b([A-Z]{2}\s?\d{3}\s?[A-Z]{2})\b")
_FN_STOPWORDS = {
    "LIBRETTO", "POLIZZA", "POLIZZE", "QUIETANZA", "APPENDICE", "CONDIZIONI",
    "MUP", "CID", "PATENTE", "CARTA", "IDENTITA", "IDENTITÀ", "FATTURA",
    "PREVENTIVO", "QUESTIONARIO", "ATTO", "VENDITA", "PASSAPORTO", "TESSERA",
    "SANITARIA", "VISURA", "CAMERALE", "MANDATO", "SDD", "PDF", "DOC", "SCAN",
    "COPIA", "DOCUMENTO", "ALLEGATO",
}


def _norm_targa(t: str) -> str:
    """Normalizza una targa per il confronto: MAIUSCOLO, senza spazi/trattini/punti
    e senza zeri di riempimento iniziali (alcune targhe sono salvate zero-padded)."""
    t = re.sub(r"[^A-Z0-9]", "", (t or "").upper())
    return t.lstrip("0")


def _guess_from_filename(filename: str) -> dict:
    """Estrae dal NOME FILE indizi utili: numero polizza, targa e nome cliente.
    I file Omnia hanno tipicamente la forma '117264695 - ANGELINI ANNAMARIA.pdf'
    oppure 'LIBRETTO FR798LT.pdf'. Classifica ogni token una sola volta per evitare
    che le cifre di una targa (es. AB12345) vengano prese come numero polizza."""
    out = {"numero_polizza": None, "targa": None, "nome": None}
    if not filename:
        return out
    up = filename.rsplit(".", 1)[0].upper()
    for sep in ("–", "-", "_", "·", "|", ","):
        up = up.replace(sep, " ")
    name_toks = []
    for raw in re.split(r"\s+", up):
        tk = re.sub(r"[^A-Z0-9]", "", raw)
        if not tk or tk in _FN_STOPWORDS:
            continue
        has_a = bool(re.search(r"[A-Z]", tk))
        has_d = bool(re.search(r"\d", tk))
        # targa: formato standard oppure token alfanumerico lettere+cifre (vecchie/moto)
        if _PLATE_RX.match(tk) or (5 <= len(tk) <= 8 and has_a and has_d):
            if not out["targa"]:
                out["targa"] = tk
            continue
        # numero polizza: token tutto cifre, lungo
        if tk.isdigit() and len(tk) >= 5:
            if not out["numero_polizza"]:
                out["numero_polizza"] = tk
            continue
        # nome cliente: token solo lettere
        if has_a and not has_d:
            name_toks.append(raw.strip())
    if name_toks:
        out["nome"] = " ".join(name_toks).strip()
    return out


async def _match_anag_by_name(name: str):
    """Trova un'anagrafica per nome testuale (ragione_sociale o cognome+nome)."""
    name = (name or "").strip()
    if len(name) < 3:
        return None
    proj = {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1}
    a = await db.anagrafiche.find_one(
        {"ragione_sociale": {"$regex": re.escape(name), "$options": "i"}}, proj)
    if a:
        return a
    toks = name.split()
    if len(toks) >= 2:
        for cog, nom in ((toks[0], " ".join(toks[1:])), (toks[-1], " ".join(toks[:-1]))):
            a = await db.anagrafiche.find_one(
                {"cognome": {"$regex": f"^{re.escape(cog)}$", "$options": "i"},
                 "nome": {"$regex": f"^{re.escape(nom)}$", "$options": "i"}}, proj)
            if a:
                return a
    return None


_FN_TIPO_KEYWORDS = [
    ("libretto", ("LIBRETTO", "CARTA DI CIRCOLAZIONE", "CIRCOLAZIONE")),
    ("quietanza", ("QUIETANZA",)),
    ("appendice", ("APPENDICE",)),
    ("condizioni", ("CONDIZIONI",)),
    ("mup", ("MUP",)),
    ("questionario", ("QUESTIONARIO",)),
    ("preventivo", ("PREVENTIVO",)),
    ("atto_vendita", ("ATTO DI VENDITA", "ATTO VENDITA")),
    ("polizza", ("POLIZZA", "CONTRATTO")),
    ("patente", ("PATENTE",)),
    ("passaporto", ("PASSAPORTO",)),
    ("tessera_sanitaria", ("TESSERA SANITARIA", "SANITARIA")),
    ("visura_camerale", ("VISURA",)),
    ("mandato_sdd", ("MANDATO", "SDD")),
    ("carta_identita", ("CARTA IDENTITA", "CARTA D'IDENTITA", "IDENTITA", "C.I.", "C.I ", "CI.")),
    ("cid", ("CID", "CONSTATAZIONE")),
    ("fattura", ("FATTURA",)),
]


def _guess_tipo_from_filename(filename: str):
    """Deduce il tipo documento dal nome file quando l'OCR non riesce (tipo='altro').
    Es. 'LIBRETTO FR798LT.pdf' → 'libretto'."""
    up = (filename or "").upper()
    for tipo, kws in _FN_TIPO_KEYWORDS:
        if any(k in up for k in kws):
            return tipo
    return None


async def _infer_targets(dati: dict, filename: str, tipo_documento: str,
                         existing_a: dict = None, existing_p: dict = None) -> tuple:
    """Deduce (anagrafica, polizza) dai dati OCR + nome file.
    Per i documenti di POLIZZA la fonte autorevole del CLIENTE è il CONTRAENTE
    della polizza trovata (numero/targa), NON il nome OCR (spesso è la COMPAGNIA)."""
    dati = dati or {}
    proj_a = {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1}
    proj_p = {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1}
    routed_entita = DOC_ROUTING.get(tipo_documento or "altro", ("anagrafica", "altro"))[0]
    fn = _guess_from_filename(filename)

    target_a = existing_a if (existing_a or {}).get("id") else None
    target_p = existing_p if (existing_p or {}).get("id") else None

    # 1) POLIZZA — per numero (OCR o filename), poi per targa (OCR o filename)
    if not (target_p or {}).get("id"):
        nump = (dati.get("numero_polizza") or dati.get("numero") or "").strip() or (fn["numero_polizza"] or "")
        if nump:
            target_p = await db.polizze.find_one(
                {"$or": [{"numero_polizza": nump}, {"numero": nump}]}, proj_p)
        if not (target_p or {}).get("id"):
            targa = _norm_targa((dati.get("targa") or "") or (fn["targa"] or ""))
            if targa and len(targa) >= 4:
                # match robusto: ignora spazi/trattini e zeri di padding iniziali
                target_p = await db.polizze.find_one(
                    {"targa": {"$regex": f"^0*{re.escape(targa)}$", "$options": "i"}},
                    proj_p, sort=[("effetto", -1)])

    # 2) ANAGRAFICA
    # 2a) autorevole: contraente della polizza trovata
    if not (target_a or {}).get("id") and (target_p or {}).get("contraente_id"):
        target_a = await db.anagrafiche.find_one({"id": target_p["contraente_id"]}, proj_a)
    # 2b) codice fiscale / partita IVA del CLIENTE (chiavi forti e univoche)
    if not (target_a or {}).get("id"):
        cf_vals = [v for v in (
            (dati.get("contraente_codice_fiscale") or "").upper().strip(),
            (dati.get("codice_fiscale") or "").upper().strip(),
        ) if v and len(v) >= 11]
        for cf in cf_vals:
            target_a = await db.anagrafiche.find_one({"codice_fiscale": cf}, proj_a)
            if target_a:
                break
    if not (target_a or {}).get("id"):
        # per i documenti di polizza NON usare la P.IVA generica (spesso è la compagnia)
        piva_vals = [(dati.get("contraente_partita_iva") or "").strip()]
        if routed_entita != "polizza":
            piva_vals.append((dati.get("partita_iva") or "").strip())
        for piva in [p for p in piva_vals if p and len(p) >= 8]:
            target_a = await db.anagrafiche.find_one({"partita_iva": piva}, proj_a)
            if target_a:
                break
    # 2c) cognome+nome OCR SOLO per documenti anagrafici (CI, patente…); per le
    #     polizze NON ci si fida del cognome OCR (è spesso la compagnia).
    if not (target_a or {}).get("id") and routed_entita == "anagrafica":
        cog = (dati.get("cognome") or "").strip(); nom = (dati.get("nome") or "").strip()
        if cog and nom:
            target_a = await db.anagrafiche.find_one(
                {"cognome": {"$regex": f"^{re.escape(cog)}$", "$options": "i"},
                 "nome": {"$regex": f"^{re.escape(nom)}$", "$options": "i"}}, proj_a)
    # 2d) contraente esplicito estratto dalla polizza
    if not (target_a or {}).get("id"):
        cog = (dati.get("contraente_cognome") or "").strip()
        nom = (dati.get("contraente_nome") or "").strip()
        rs = (dati.get("contraente_ragione_sociale") or "").strip()
        if cog and nom:
            target_a = await db.anagrafiche.find_one(
                {"cognome": {"$regex": f"^{re.escape(cog)}$", "$options": "i"},
                 "nome": {"$regex": f"^{re.escape(nom)}$", "$options": "i"}}, proj_a)
        if not (target_a or {}).get("id") and rs:
            target_a = await _match_anag_by_name(rs)
    # 2e) nome dedotto dal filename
    if not (target_a or {}).get("id") and fn["nome"]:
        target_a = await _match_anag_by_name(fn["nome"])

    return (target_a or None), (target_p or None)


@router.post("/documenti-inbox/analyze")
async def analizza_documento(
    file: UploadFile = File(...),
    auto_archive: bool = Form(True),  # NEW: auto-salva se confidenza alta + match
    scope: Optional[str] = Form(None),  # NEW: cartella scelta (anagrafica|polizza|sinistro)
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Analizza un documento appena caricato: classifica + estrae dati.
    Se confidenza == "alta" E è stata trovata un'anagrafica → AUTO-ARCHIVIA
    nella sezione corretta (e applica i campi compatibili) senza intervento utente.
    Altrimenti resta in stato 'pending' per revisione manuale."""
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 20 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    if ct == "application/pdf":
        img_bytes, img_ct = await _convert_pdf_to_jpeg(contents)
    elif ct.startswith("image/"):
        img_bytes, img_ct = contents, ct
    else:
        raise HTTPException(400, "Formato non supportato (PDF/JPG/PNG/WEBP)")
    result = await _ocr_classifica(img_bytes, img_ct)

    # Inferenza target: polizza (per numero/targa/filename) + anagrafica autorevole
    # (il CONTRAENTE della polizza, non il nome OCR che spesso è la COMPAGNIA).
    dati = result.get("dati") or {}
    target_anagrafica, target_polizza = await _infer_targets(
        dati, file.filename, result.get("tipo_documento"))

    # Salva temp nell'inbox (con il file binario in storage)
    inbox_id = str(uuid.uuid4())
    ext = (file.filename or "doc").rsplit(".", 1)[-1].lower() or "bin"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/inbox/{inbox_id}.{ext}"
    try:
        obj_storage.put_object(path, contents, ct)
    except Exception as e:
        logging.warning("Errore put_object inbox: %s", e)
        path = None

    doc_inbox = {
        "id": inbox_id,
        "filename": file.filename,
        "content_type": ct,
        "size": len(contents),
        "storage_path": path,
        "tipo_documento": result.get("tipo_documento"),
        "confidenza": result.get("confidenza"),
        "foto_volto_bbox": _norm_bbox(result.get("foto_volto_bbox")),
        "dati": dati,
        "target_anagrafica": target_anagrafica,
        "target_polizza": target_polizza,
        "stato": "pending",
        "created_at": _now_iso(),
        "created_by": user.get("id"),
        "scope": scope if scope in ("anagrafica", "polizza", "sinistro") else None,
    }
    await db.documenti_inbox.insert_one(doc_inbox)
    doc_inbox.pop("_id", None)

    # === AUTO-ARCHIVE ===
    # Auto-archivia SOLO se: confidenza alta + tipo riconosciuto + l'entità richiesta
    # dalla card di destinazione è stata trovata. I documenti di sinistro NON vengono
    # mai auto-archiviati (nessun match automatico): restano in "Da rivedere".
    tipo_riconosciuto = result.get("tipo_documento")
    routed_entita, _routed_card = DOC_ROUTING.get(tipo_riconosciuto or "altro", ("anagrafica", "altro"))
    confidenza_ok = (result.get("confidenza") == "alta")
    tipo_ok = tipo_riconosciuto and tipo_riconosciuto != "altro"
    if routed_entita == "anagrafica":
        has_target = bool(target_anagrafica)
    elif routed_entita == "polizza":
        has_target = bool(target_polizza)
    else:
        has_target = False  # sinistro → solo manuale
    # Se l'utente ha scelto una cartella (scope), non auto-archiviare fuori da quello scope
    if scope in ("anagrafica", "polizza", "sinistro") and routed_entita != scope:
        has_target = False
    # Un match DETERMINISTICO su una polizza (per numero o targa) è una prova forte:
    # consente l'auto-archiviazione anche a confidenza media/bassa (riduce gli scarti
    # dei libretti, spesso a bassa confidenza ma con targa univoca).
    strong_match = routed_entita == "polizza" and bool(target_polizza)
    if auto_archive and (confidenza_ok or strong_match) and tipo_ok and has_target:
        try:
            # Tutti i campi disponibili vengono applicati
            campi_auto = [k for k, v in (dati or {}).items() if v not in (None, "", [])]
            auto_body = {
                "anagrafica_id": (target_anagrafica or {}).get("id"),
                "polizza_id": (target_polizza or {}).get("id"),
                "campi_da_applicare": campi_auto,
                "dati": dati,
                "salva_avatar": True,
            }
            res = await _do_save(inbox_id, auto_body, user)
            # Re-fetch the updated inbox doc to return the saved state
            updated = await db.documenti_inbox.find_one({"id": inbox_id}, {"_id": 0})
            if updated:
                updated["auto_archiviato"] = True
                updated["auto_archive_result"] = res
                return updated
        except Exception as e:
            logging.exception("Auto-archive fallito per %s: %s", inbox_id, e)
            # Lascia in pending: l'utente potrà rivedere manualmente.
            # Annota l'errore nel doc inbox così è visibile in UI
            await db.documenti_inbox.update_one({"id": inbox_id}, {"$set": {
                "auto_archive_errore": str(e)[:300],
            }})

    return doc_inbox


@router.get("/documenti-inbox")
async def lista_inbox(
    stato: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt = {}
    if stato: flt["stato"] = stato
    items = await db.documenti_inbox.find(flt, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@router.post("/documenti-inbox/{iid}/save")
async def salva_inbox(
    iid: str,
    body: dict,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Salva il documento nella destinazione corretta + applica i dati.

    body = {
        anagrafica_id?, polizza_id?,  # destinazione allegato
        campi_da_applicare?: [str],   # quali campi dei `dati` applicare
        dati?: dict,                  # eventualmente sovrascrive i dati estratti
    }
    """
    return await _do_save(iid, body, user)


# Card documenti dell'anagrafica salvati nel dict `anagrafiche.documenti`
ANAG_CARD_KEYS = {
    "carta_identita", "patente", "passaporto", "codice_fiscale_doc",
    "tessera_sanitaria", "visura_camerale", "mandato_sdd",
    "autocertificazione_stato_famiglia", "privacy_firmata",
}

# Mappa tipo_documento OCR → (entità target, card/categoria key di destinazione)
# anagrafica → card nel dict `documenti` (se card_key ∈ ANAG_CARD_KEYS) altrimenti allegato
# polizza/sinistro → allegato con `categoria` = card_key (letto da DocumentiSezioneSplit)
DOC_ROUTING = {
    "carta_identita":    ("anagrafica", "carta_identita"),
    "patente":           ("anagrafica", "patente"),
    "passaporto":        ("anagrafica", "passaporto"),
    "codice_fiscale":    ("anagrafica", "codice_fiscale_doc"),
    "tessera_sanitaria": ("anagrafica", "tessera_sanitaria"),
    "visura_camerale":   ("anagrafica", "visura_camerale"),
    "mandato_sdd":       ("anagrafica", "mandato_sdd"),
    "polizza":           ("polizza", "polizza"),
    "polizza_frontespizio": ("polizza", "polizza"),
    "frontespizio":      ("polizza", "polizza"),
    "condizioni":        ("polizza", "condizioni"),
    "appendice":         ("polizza", "appendici"),
    "libretto":          ("polizza", "libretto_veicolo"),
    "atto_vendita":      ("polizza", "atto_vendita"),
    "quietanza":         ("polizza", "quietanza"),
    "mup":               ("polizza", "mup"),
    "questionario":      ("polizza", "questionario"),
    "preventivo":        ("polizza", "preventivo"),
    "fattura":           ("polizza", "altri"),
    "cid":               ("sinistro", "cid"),
    "perizia":           ("sinistro", "perizia"),
    "denuncia":          ("sinistro", "denuncia"),
    "altro":             ("anagrafica", "altro"),
}


async def _default_visibile(entita_tipo: str, categoria: str) -> bool:
    """Visibilità cliente di default per la card, configurabile in Librerie.
    Legge da azienda_config.card_visibilita se presente, altrimenti usa i default."""
    az = await db.azienda_config.find_one({}, {"_id": 0, "card_visibilita": 1}) or {}
    cfg = (az.get("card_visibilita") or {}).get(entita_tipo) or {}
    if categoria in cfg:
        return bool(cfg[categoria])
    # default statici (allineati alle card frontend)
    DEFAULTS = {
        "polizza": {"polizza", "condizioni", "appendici", "libretto_veicolo",
                    "atto_vendita", "quietanza", "mup", "questionario"},
        "sinistro": {"cid", "foto", "fattura", "denuncia"},
        "anagrafica": set(),
    }
    return categoria in DEFAULTS.get(entita_tipo, set())


async def _do_save(iid: str, body: dict, user: dict) -> dict:
    inb = await db.documenti_inbox.find_one({"id": iid}, {"_id": 0})
    if not inb:
        raise HTTPException(404, "Documento non trovato")
    if inb.get("stato") == "salvato":
        return inb

    dati = body.get("dati") or inb.get("dati") or {}
    campi = body.get("campi_da_applicare") or []
    tipo_doc = inb.get("tipo_documento") or "altro"

    # --- Routing: entità + card di destinazione ---
    default_entita, default_card = DOC_ROUTING.get(tipo_doc, ("anagrafica", "altro"))
    entita_tipo = body.get("entita_tipo") or default_entita
    categoria = body.get("categoria") or default_card

    anagrafica_id = body.get("anagrafica_id") or (inb.get("target_anagrafica") or {}).get("id")
    polizza_id = body.get("polizza_id") or (inb.get("target_polizza") or {}).get("id")
    sinistro_id = body.get("sinistro_id")

    if entita_tipo == "anagrafica":
        entita_id = anagrafica_id or body.get("entita_id")
        anagrafica_id = entita_id
    elif entita_tipo == "polizza":
        entita_id = polizza_id or body.get("entita_id")
        polizza_id = entita_id
    elif entita_tipo == "sinistro":
        entita_id = sinistro_id or body.get("entita_id")
        sinistro_id = entita_id
    else:
        raise HTTPException(400, "entita_tipo non valido")
    if not entita_id:
        raise HTTPException(400, "Specificare l'entità di destinazione")

    # 1. Salva il file nella CARD corretta
    import cloud_doc_sync
    tenant_id = user.get("agenzia_tenant_id") or user.get("tenant_id") or "default"
    providers = await cloud_doc_sync.connected_providers(tenant_id)
    sp = inb.get("storage_path")

    async def _mirror_inbox_file(doc_id: str, label: str):
        """Copia il file inbox sul Drive dell'agenzia. Ritorna il dict cloud_sync o None."""
        if not providers or entita_tipo not in ("anagrafica", "polizza", "sinistro") or not sp:
            return None
        try:
            data, mime = obj_storage.get_object(sp)
        except Exception as e:
            logging.warning("Mirror inbox: impossibile leggere il file %s: %s", sp, e)
            return None
        try:
            return await cloud_doc_sync.mirror_document(
                tenant_id=tenant_id, entita_tipo=entita_tipo, entita_id=entita_id,
                doc_label_text=label, doc_id=doc_id,
                data=data, mime=mime, filename=inb.get("filename") or "documento",
            )
        except Exception as e:
            logging.warning("Mirror inbox su cloud fallito: %s", e)
            return None

    allegato_id = None
    if entita_tipo == "anagrafica" and categoria in ANAG_CARD_KEYS:
        # → card nel dict `anagrafiche.documenti[categoria]`
        doc_entry = {
            "url": f"/api/storage/{sp}" if sp else None,
            "storage_path": sp,
            "nome_file": inb.get("filename") or "documento",
            "mime": inb.get("content_type"),
            "size_kb": round((inb.get("size") or 0) / 1024, 1),
            "data_caricamento": _now_iso(),
            "scadenza": (dati.get("data_scadenza") if tipo_doc == "carta_identita" else None),
            "caricato_da": user.get("id"),
        }
        cloud_sync = await _mirror_inbox_file(iid, categoria)
        if cloud_sync:
            doc_entry["cloud_sync"] = cloud_sync
            doc_entry["storage_provider"] = cloud_sync["provider"]
            doc_entry["url"] = None
            doc_entry["storage_path"] = None
            doc_entry["pending_sync"] = False
        elif providers:
            doc_entry["pending_sync"] = True  # cloud collegato ma upload fallito → ritenta
        elif sp:
            doc_entry["pending_sync"] = True  # nessun cloud → sincronizza appena collegato
        await db.anagrafiche.update_one(
            {"id": entita_id},
            {"$set": {f"documenti.{categoria}": doc_entry, "updated_at": _now_iso()}},
        )
    else:
        # → allegato con categoria = card key (polizza/sinistro o anagrafica "altro")
        if not sp:
            raise HTTPException(400, "File non disponibile nello storage: impossibile archiviare")
        alleg = Allegato(
            entita_tipo=entita_tipo, entita_id=entita_id,
            nome_file=inb.get("filename") or "documento",
            storage_path=inb.get("storage_path"),
            content_type=inb.get("content_type"),
            size=inb.get("size") or 0,
            descrizione=f"Documenti inbox ({tipo_doc})",
            categoria=categoria,
            visibile_cliente=await _default_visibile(entita_tipo, categoria),
            autore_id=user.get("id"),
        )
        allegato_id = alleg.id
        cloud_sync = await _mirror_inbox_file(alleg.id, categoria)
        alleg_dict = alleg.model_dump()
        if cloud_sync:
            alleg_dict["storage_provider"] = cloud_sync["provider"]
            alleg_dict["cloud_sync"] = cloud_sync
            alleg_dict["pending_sync"] = False
            alleg_dict["storage_path"] = ""
        else:
            alleg_dict["pending_sync"] = True
        await db.allegati.insert_one(alleg_dict)

    # 2. Applica campi all'anagrafica (se disponibile un'anagrafica di riferimento)
    ana_updates = {}
    if anagrafica_id and campi:
        ana_field_map = {
            "cognome": "cognome", "nome": "nome",
            "codice_fiscale": "codice_fiscale",
            "data_nascita": "data_nascita",
            "luogo_nascita": "comune_nascita",
            "sesso": "sesso",
        }
        if tipo_doc == "carta_identita":
            ana_field_map.update({
                "numero_documento": "numero_carta_identita",
                "data_emissione": "ci_data_emissione",
                "data_scadenza": "ci_data_scadenza",
                "comune_emissione": "ci_comune_emissione",
            })
        for k in campi:
            if k in ana_field_map and dati.get(k) not in (None, ""):
                ana_updates[ana_field_map[k]] = dati[k]
        if ana_updates:
            ana_updates["updated_at"] = _now_iso()
            await db.anagrafiche.update_one({"id": anagrafica_id}, {"$set": ana_updates})

    pol_updates = {}
    if polizza_id and campi and entita_tipo == "polizza":
        pol_field_map = {
            "targa": "targa", "telaio": "telaio",
            "marca": "veicolo_marca", "modello": "veicolo_modello",
            "decorrenza": "data_decorrenza", "scadenza": "data_scadenza",
            "premio_lordo": "premio_lordo",
        }
        for k in campi:
            if k in pol_field_map and dati.get(k) not in (None, ""):
                pol_updates[pol_field_map[k]] = dati[k]
        if pol_updates:
            pol_updates["updated_at"] = _now_iso()
            await db.polizze.update_one({"id": polizza_id}, {"$set": pol_updates})

    # ------ AUTO AVATAR per carta_identita / patente / passaporto / tessera_sanitaria ------
    avatar_url = None
    salva_avatar = bool(body.get("salva_avatar", True))  # default true
    if (
        salva_avatar
        and anagrafica_id
        and inb.get("tipo_documento") in {"carta_identita", "patente", "passaporto", "tessera_sanitaria"}
        and inb.get("storage_path")
    ):
        try:
            from PIL import Image
            # Re-fetch original file from storage
            blob, _orig_ct = obj_storage.get_object(inb["storage_path"])
            ct_orig = inb.get("content_type") or ""
            if ct_orig == "application/pdf":
                img_bytes, _ = await _convert_pdf_to_jpeg(blob)
            else:
                img_bytes = blob
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            W, H = img.size
            # 1) Metodo affidabile: rilevamento volto con OpenCV (Haar cascade).
            face = _detect_face_crop(img)
            # 2) Fallback: bbox restituito dall'OCR (se valido).
            if face is None:
                bbox = _norm_bbox(inb.get("foto_volto_bbox"))
                if bbox and bbox["w"] > 0 and bbox["h"] > 0:
                    pad = 0.05
                    left = max(0, int((bbox["x"] - pad) * W))
                    top = max(0, int((bbox["y"] - pad) * H))
                    right = min(W, int((bbox["x"] + bbox["w"] + pad) * W))
                    bottom = min(H, int((bbox["y"] + bbox["h"] + pad) * H))
                    if right > left and bottom > top:
                        face = img.crop((left, top, right, bottom))
            if face is not None:
                # quadrato
                side = max(face.size)
                square = Image.new("RGB", (side, side), (240, 240, 240))
                square.paste(face, ((side - face.size[0]) // 2, (side - face.size[1]) // 2))
                square.thumbnail((512, 512))
                out = BytesIO()
                square.save(out, format="JPEG", quality=85)
                avatar_bytes = out.getvalue()
                avatar_path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{anagrafica_id}/avatar_{uuid.uuid4().hex[:8]}.jpg"
                up = obj_storage.put_object(avatar_path, avatar_bytes, "image/jpeg")
                avatar_url = up.get("url") or up.get("path") or avatar_path
                await db.anagrafiche.update_one(
                    {"id": anagrafica_id},
                    {"$set": {"avatar_url": avatar_url, "updated_at": _now_iso()}},
                )
        except Exception as e:
            logging.warning("Errore crop avatar: %s", e)
            avatar_url = None

    # 3. Mark inbox as saved
    await db.documenti_inbox.update_one({"id": iid}, {"$set": {
        "stato": "salvato",
        "salvato_at": _now_iso(),
        "salvato_in": {"entita_tipo": entita_tipo, "entita_id": entita_id, "categoria": categoria},
        "campi_applicati": list(ana_updates.keys()) + list(pol_updates.keys()),
        "allegato_id": allegato_id,
        "avatar_url": avatar_url,
    }})

    return {
        "ok": True,
        "allegato_id": allegato_id,
        "entita_tipo": entita_tipo,
        "categoria": categoria,
        "anagrafica_aggiornata": list(ana_updates.keys()),
        "polizza_aggiornata": list(pol_updates.keys()),
        "avatar_url": avatar_url,
    }


@router.delete("/documenti-inbox/{iid}")
async def elimina_inbox(
    iid: str,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    res = await db.documenti_inbox.delete_one({"id": iid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Documento non trovato")
    return {"ok": True}


async def _rematch_pending_targets(inb: dict) -> tuple:
    """Ri-cerca anagrafica/polizza nel DB ATTUALE usando i dati OCR salvati + nome
    file. Necessario quando la polizza/anagrafica/targa è stata creata DOPO l'ingest
    del documento. Ritorna (target_anagrafica | None, target_polizza | None)."""
    return await _infer_targets(
        inb.get("dati") or {}, inb.get("filename") or "", inb.get("tipo_documento"),
        existing_a=inb.get("target_anagrafica"), existing_p=inb.get("target_polizza"))


async def _retry_one_pending(inb: dict, user) -> dict:
    """Riprocessa UN documento pending. Ritorna un esito:
    {"esito": "archiviato"|"rematched"|"saltato"|"errore", "rematched": bool,
     "entita": "polizza"|"anagrafica"|None, "err": str|None}."""
    tipo = inb.get("tipo_documento")
    scope = inb.get("scope")
    # tipo effettivo: OCR, altrimenti dedotto dal nome file
    eff_tipo = tipo if (tipo and tipo != "altro") else _guess_tipo_from_filename(inb.get("filename"))

    # entità "hint" nota a priori: dal tipo (anche varianti 'polizza_*'), altrimenti
    # dalla CARTELLA scelta in upload (scope). Può restare None per i doc 'altro'.
    hint = None
    if eff_tipo and eff_tipo != "altro":
        if eff_tipo in DOC_ROUTING:
            hint = DOC_ROUTING[eff_tipo][0]
        elif eff_tipo.startswith("polizza") or eff_tipo.endswith("frontespizio"):
            hint = "polizza"
    if not hint and scope in ("anagrafica", "polizza"):
        hint = scope
    if hint == "sinistro":
        return {"esito": "saltato", "rematched": False, "entita": None, "err": None}

    # 🔄 Ri-match: instrada con un tipo coerente (polizza se non sappiamo meglio)
    tipo_for_match = eff_tipo if (eff_tipo and eff_tipo in DOC_ROUTING) else (
        "polizza" if hint != "anagrafica" else "carta_identita")
    new_a, new_p = await _rematch_pending_targets({**inb, "tipo_documento": tipo_for_match})
    persist = {}
    did_rematch = False
    if (new_a or {}).get("id") and not (inb.get("target_anagrafica") or {}).get("id"):
        persist["target_anagrafica"] = new_a
    if (new_p or {}).get("id") and not (inb.get("target_polizza") or {}).get("id"):
        persist["target_polizza"] = new_p
    if eff_tipo and eff_tipo != tipo and ((new_p or {}).get("id") or (new_a or {}).get("id")):
        persist["tipo_documento"] = eff_tipo
    if persist:
        await db.documenti_inbox.update_one({"id": inb["id"]}, {"$set": persist})
        did_rematch = True

    target_a = new_a or (inb.get("target_anagrafica") or {}) or {}
    target_p = new_p or (inb.get("target_polizza") or {}) or {}

    # entità finale: hint se noto, altrimenti si deduce dai target trovati
    # (una polizza trovata vince sull'anagrafica, es. frontespizio polizza).
    routed_entita = hint
    if not routed_entita:
        if target_p.get("id"):
            routed_entita = "polizza"
        elif target_a.get("id"):
            routed_entita = "anagrafica"
        else:
            return {"esito": "saltato", "rematched": did_rematch, "entita": None, "err": None}
    if routed_entita == "polizza" and not target_p.get("id"):
        if target_a.get("id"):
            routed_entita = "anagrafica"
        else:
            return {"esito": "saltato", "rematched": did_rematch, "entita": None, "err": None}
    if routed_entita == "anagrafica" and not target_a.get("id"):
        return {"esito": "saltato", "rematched": did_rematch, "entita": None, "err": None}

    # Auto-archivia se: confidenza alta, OPPURE match deterministico su polizza,
    # OPPURE l'utente aveva scelto esplicitamente la cartella (scope).
    strong_match = (routed_entita == "polizza" and bool(target_p.get("id"))) \
        or (scope in ("anagrafica", "polizza"))
    if inb.get("confidenza") != "alta" and not strong_match:
        return {"esito": "saltato", "rematched": did_rematch, "entita": None, "err": None}
    body = {
        "entita_tipo": routed_entita,
        "anagrafica_id": target_a.get("id"),
        "polizza_id": target_p.get("id"),
        "campi_da_applicare": list((inb.get("dati") or {}).keys()),
        "dati": inb.get("dati") or {},
        "salva_avatar": True,
    }
    try:
        await _do_save(inb["id"], body, user)
        return {"esito": "archiviato", "rematched": did_rematch, "entita": routed_entita, "err": None}
    except Exception as e:
        await db.documenti_inbox.update_one({"id": inb["id"]}, {"$set": {
            "auto_archive_errore": str(e)[:300],
        }})
        return {"esito": "errore", "rematched": did_rematch, "entita": routed_entita, "err": str(e)[:200]}


@router.get("/documenti-inbox/pending-ids")
async def pending_ids(
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Elenco ordinato degli id dei documenti pending — usato dalla UI per
    riprocessarli uno alla volta mostrando la barra di avanzamento su ogni card."""
    ids = []
    async for inb in db.documenti_inbox.find({"stato": "pending"}, {"_id": 0, "id": 1}).sort("created_at", 1):
        ids.append(inb["id"])
    return {"ids": ids}


@router.post("/documenti-inbox/{iid}/retry-auto-archive")
async def retry_auto_archive_one(
    iid: str,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Riprocessa un SINGOLO documento pending (usato dalla UI card-by-card)."""
    inb = await db.documenti_inbox.find_one({"id": iid}, {"_id": 0})
    if not inb:
        raise HTTPException(404, "Documento non trovato")
    if inb.get("stato") != "pending":
        return {"esito": "saltato", "rematched": False, "entita": None, "err": None}
    return await _retry_one_pending(inb, user)


@router.post("/documenti-inbox/retry-auto-archive")
async def retry_auto_archive(
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Riprocessa tutti i documenti pending che sono eleggibili per auto-archiviazione
    (confidenza alta + tipo riconosciuto + anagrafica/polizza trovata).
    Ri-cerca ogni volta nel DB attuale, così recupera i documenti arrivati PRIMA
    che la relativa polizza/anagrafica/targa fosse creata."""
    archived = 0
    failed = 0
    rematched = 0
    errors = []
    async for inb in db.documenti_inbox.find({"stato": "pending"}, {"_id": 0}):
        res = await _retry_one_pending(inb, user)
        if res["rematched"]:
            rematched += 1
        if res["esito"] == "archiviato":
            archived += 1
        elif res["esito"] == "errore":
            failed += 1
            errors.append({"id": inb["id"], "err": res["err"]})
    return {"archived": archived, "failed": failed, "rematched": rematched, "errors": errors}
