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
    // SE polizza:
    "numero_polizza": "stringa o null",
    "compagnia": "MAIUSCOLO o null",
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
- Restituisci null per i campi non leggibili o non pertinenti
- Date sempre YYYY-MM-DD
- foto_volto_bbox: SOLO per carta_identita/patente/passaporto/tessera_sanitaria/codice_fiscale.
  Coordinate normalizzate 0-1 della regione rettangolare che contiene la foto del volto del titolare.
  Restituisci null/null/null/null se il documento non ha una foto visibile.
- Niente testo prima/dopo, niente markdown
"""


async def _convert_pdf_to_jpeg(contents: bytes) -> tuple[bytes, str]:
    import pdfplumber
    with pdfplumber.open(BytesIO(contents)) as pdf:
        if not pdf.pages:
            raise HTTPException(400, "PDF vuoto")
        img = pdf.pages[0].to_image(resolution=200).original
        out = BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue(), "image/jpeg"


async def _ocr_classifica(image_bytes: bytes, mime: str) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY non configurata")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    chat = LlmChat(
        api_key=key,
        session_id=f"docinbox-{os.urandom(4).hex()}",
        system_message="Sei un OCR/classificatore di documenti italiani.",
    ).with_model("gemini", "gemini-3-flash-preview")
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

    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY non configurata")
    b64 = base64.b64encode(img_bytes).decode("ascii")
    chat = LlmChat(
        api_key=key, session_id=f"ocrveic-{os.urandom(4).hex()}",
        system_message="Sei un OCR di libretti di circolazione italiani.",
    ).with_model("gemini", "gemini-3-flash-preview")
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

    # Inferenza target: se troviamo CF nei dati → ricerca anagrafica
    dati = result.get("dati") or {}
    target_anagrafica = None
    cf = (dati.get("codice_fiscale") or "").upper()
    if cf:
        anag = await db.anagrafiche.find_one(
            {"codice_fiscale": cf},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1},
        )
        if anag:
            target_anagrafica = anag
    # Fallback: cerca per cognome + nome se non trovato per CF
    if not target_anagrafica and dati.get("cognome") and dati.get("nome"):
        anag = await db.anagrafiche.find_one(
            {"cognome": {"$regex": f"^{re.escape(dati['cognome'])}$", "$options": "i"},
             "nome": {"$regex": f"^{re.escape(dati['nome'])}$", "$options": "i"}},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1},
        )
        if anag:
            target_anagrafica = anag

    # Polizza: ricerca per numero (numero_polizza o numero)
    target_polizza = None
    nump = (dati.get("numero_polizza") or "").strip()
    if nump:
        pol = await db.polizze.find_one(
            {"$or": [{"numero_polizza": nump}, {"numero": nump}]},
            {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1},
        )
        if pol:
            target_polizza = pol
            # Se non c'è anagrafica ma la polizza ha un contraente, usa quello
            if not target_anagrafica and pol.get("contraente_id"):
                anag = await db.anagrafiche.find_one(
                    {"id": pol["contraente_id"]},
                    {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1},
                )
                if anag:
                    target_anagrafica = anag

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
        "foto_volto_bbox": result.get("foto_volto_bbox"),
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
    if auto_archive and confidenza_ok and tipo_ok and has_target:
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
    allegato_id = None
    if entita_tipo == "anagrafica" and categoria in ANAG_CARD_KEYS:
        # → card nel dict `anagrafiche.documenti[categoria]`
        sp = inb.get("storage_path")
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
        await db.anagrafiche.update_one(
            {"id": entita_id},
            {"$set": {f"documenti.{categoria}": doc_entry, "updated_at": _now_iso()}},
        )
    else:
        # → allegato con categoria = card key (polizza/sinistro o anagrafica "altro")
        if not inb.get("storage_path"):
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
        await db.allegati.insert_one(alleg.model_dump())
        allegato_id = alleg.id

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
        and inb.get("foto_volto_bbox")
        and inb.get("storage_path")
    ):
        bbox = inb["foto_volto_bbox"] or {}
        try:
            from PIL import Image
            # Re-fetch original file from storage and crop the face
            blob, _orig_ct = obj_storage.get_object(inb["storage_path"])
            ct_orig = inb.get("content_type") or ""
            if ct_orig == "application/pdf":
                img_bytes, _ = await _convert_pdf_to_jpeg(blob)
            else:
                img_bytes = blob
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            W, H = img.size
            x = float(bbox.get("x") or 0)
            y = float(bbox.get("y") or 0)
            w = float(bbox.get("w") or 0)
            h = float(bbox.get("h") or 0)
            if w > 0 and h > 0:
                # Padding +10% e bound
                pad = 0.05
                left = max(0, int((x - pad) * W))
                top = max(0, int((y - pad) * H))
                right = min(W, int((x + w + pad) * W))
                bottom = min(H, int((y + h + pad) * H))
                face = img.crop((left, top, right, bottom))
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


@router.post("/documenti-inbox/retry-auto-archive")
async def retry_auto_archive(
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Riprocessa tutti i documenti pending che sono eleggibili per auto-archiviazione
    (confidenza alta + tipo riconosciuto + anagrafica trovata)."""
    archived = 0
    failed = 0
    errors = []
    async for inb in db.documenti_inbox.find({"stato": "pending"}, {"_id": 0}):
        if inb.get("confidenza") != "alta":
            continue
        tipo = inb.get("tipo_documento")
        if not tipo or tipo == "altro":
            continue
        routed_entita, _ = DOC_ROUTING.get(tipo, ("anagrafica", "altro"))
        if routed_entita == "sinistro":
            continue  # sinistro → solo manuale
        target_a = inb.get("target_anagrafica") or {}
        target_p = inb.get("target_polizza") or {}
        if routed_entita == "anagrafica" and not target_a.get("id"):
            continue
        if routed_entita == "polizza" and not target_p.get("id"):
            continue
        body = {
            "anagrafica_id": target_a.get("id"),
            "polizza_id": target_p.get("id"),
            "campi_da_applicare": list((inb.get("dati") or {}).keys()),
            "dati": inb.get("dati") or {},
            "salva_avatar": True,
        }
        try:
            await _do_save(inb["id"], body, user)
            archived += 1
        except Exception as e:
            failed += 1
            errors.append({"id": inb["id"], "err": str(e)[:200]})
            await db.documenti_inbox.update_one({"id": inb["id"]}, {"$set": {
                "auto_archive_errore": str(e)[:300],
            }})
    return {"archived": archived, "failed": failed, "errors": errors}
