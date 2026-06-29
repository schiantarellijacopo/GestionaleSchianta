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
  "tipo_documento": "carta_identita | patente | codice_fiscale | libretto | polizza | fattura | tessera_sanitaria | passaporto | altro",
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


@router.post("/documenti-inbox/analyze")
async def analizza_documento(
    file: UploadFile = File(...),
    auto_archive: bool = Form(True),  # NEW: auto-salva se confidenza alta + match
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
    }
    await db.documenti_inbox.insert_one(doc_inbox)
    doc_inbox.pop("_id", None)

    # === AUTO-ARCHIVE ===
    # Se confidenza alta + tipo riconosciuto + target trovato → archivia automaticamente
    confidenza_ok = (result.get("confidenza") == "alta")
    tipo_ok = result.get("tipo_documento") and result.get("tipo_documento") != "altro"
    has_target = bool(target_anagrafica or target_polizza)
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
            logging.warning("Auto-archive fallito per %s: %s", inbox_id, e)
            # Lascia in pending: l'utente potrà rivedere manualmente

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


# Mappa tipo_documento → categoria documenti (per la "sezione" corretta)
TIPO_DOC_TO_CATEGORIA = {
    "carta_identita": "documento_identita",
    "patente": "patente",
    "codice_fiscale": "codice_fiscale",
    "tessera_sanitaria": "codice_fiscale",
    "passaporto": "documento_identita",
    "libretto": "libretto_circolazione",
    "polizza": "polizza",
    "fattura": "fattura",
    "altro": "altro",
}


async def _do_save(iid: str, body: dict, user: dict) -> dict:
    inb = await db.documenti_inbox.find_one({"id": iid}, {"_id": 0})
    if not inb:
        raise HTTPException(404, "Documento non trovato")
    if inb.get("stato") == "salvato":
        return inb

    anagrafica_id = body.get("anagrafica_id") or (inb.get("target_anagrafica") or {}).get("id")
    polizza_id = body.get("polizza_id") or (inb.get("target_polizza") or {}).get("id")
    if not anagrafica_id and not polizza_id:
        raise HTTPException(400, "Specificare almeno un'entità (anagrafica o polizza) di destinazione")

    dati = body.get("dati") or inb.get("dati") or {}
    campi = body.get("campi_da_applicare") or []

    # 1. Crea allegato copiando dal path inbox al path definitivo
    # Se c'è una polizza E un'anagrafica → preferisci POLIZZA come entità per allegati polizza
    tipo_doc = inb.get("tipo_documento") or "altro"
    categoria = TIPO_DOC_TO_CATEGORIA.get(tipo_doc, "altro")
    # Documenti d'identità vanno SEMPRE su anagrafica anche se è disponibile una polizza
    if tipo_doc in ("carta_identita", "patente", "codice_fiscale", "tessera_sanitaria", "passaporto"):
        entita_tipo = "anagrafica"
        entita_id = anagrafica_id or polizza_id
    else:
        entita_tipo = "polizza" if polizza_id else "anagrafica"
        entita_id = polizza_id or anagrafica_id

    alleg = Allegato(
        entita_tipo=entita_tipo, entita_id=entita_id,
        nome_file=inb.get("filename") or "documento",
        storage_path=inb.get("storage_path"),
        content_type=inb.get("content_type"),
        size=inb.get("size") or 0,
        descrizione=f"Documenti inbox ({tipo_doc})",
        categoria=categoria,
        autore_id=user.get("id"),
    )
    await db.allegati.insert_one(alleg.model_dump())

    # 2. Applica campi all'anagrafica (se presente)
    ana_updates = {}
    if anagrafica_id and campi:
        ana_field_map = {
            "cognome": "cognome", "nome": "nome",
            "codice_fiscale": "codice_fiscale",
            "data_nascita": "data_nascita",
            "luogo_nascita": "luogo_nascita",
            "sesso": "sesso",
        }
        for k in campi:
            if k in ana_field_map and dati.get(k) not in (None, ""):
                ana_updates[ana_field_map[k]] = dati[k]
        if ana_updates:
            ana_updates["updated_at"] = _now_iso()
            await db.anagrafiche.update_one({"id": anagrafica_id}, {"$set": ana_updates})

    pol_updates = {}
    if polizza_id and campi:
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
        "salvato_in": {"entita_tipo": entita_tipo, "entita_id": entita_id},
        "campi_applicati": list(ana_updates.keys()) + list(pol_updates.keys()),
        "allegato_id": alleg.id,
        "avatar_url": avatar_url,
    }})

    return {
        "ok": True,
        "allegato_id": alleg.id,
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
