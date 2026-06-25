"""OCR routes — libretto di circolazione (Gemini 3 Flash).

Estratto da server.py. Endpoint prefissati `/api/ocr`.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from database import db
from db_models import Allegato, _uid
from auth import require_user
from shared import log_attivita
import storage as obj_storage


router = APIRouter()


async def _convert_pdf_to_jpeg(contents: bytes) -> tuple[bytes, str]:
    """Converte la prima pagina di un PDF in JPEG (200 dpi)."""
    try:
        import pdfplumber
        with pdfplumber.open(BytesIO(contents)) as pdf:
            if not pdf.pages:
                raise HTTPException(400, "PDF vuoto")
            img = pdf.pages[0].to_image(resolution=200).original
            out = BytesIO()
            img.save(out, format="JPEG", quality=85)
            return out.getvalue(), "image/jpeg"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Errore conversione PDF: {e}")


async def _salva_allegato_libretto(polizza_id: str, file: UploadFile,
                                   contents: bytes, ct: str, user: dict) -> Optional[str]:
    """Salva il file caricato come allegato della polizza e ritorna `allegato_id`."""
    ext = (file.filename or "libretto.pdf").rsplit(".", 1)[-1].lower() or "pdf"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/polizze/{polizza_id}/libretto_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, contents, ct)
        alleg = Allegato(
            entita_tipo="polizza", entita_id=polizza_id,
            nome_file=file.filename or "libretto",
            storage_path=result["path"],
            content_type=ct, size=result.get("size", len(contents)),
            descrizione="OCR libretto di circolazione",
            autore_id=user.get("id"),
        )
        await db.allegati.insert_one(alleg.model_dump())
        return alleg.id
    except Exception as exc:
        logging.warning("Errore upload libretto: %s", exc)
        return None


@router.post("/ocr/libretto")
async def ocr_libretto_endpoint(
    file: UploadFile = File(...),
    polizza_id: Optional[str] = Form(None),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """OCR libretto di circolazione veicolo. Salva il file come allegato della polizza
    e restituisce {dati, allegato_id, confidence}.
    """
    import ocr_libretto as ocr_lib
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 20 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")

    if ct == "application/pdf":
        file_for_ocr, ct_for_ocr = await _convert_pdf_to_jpeg(contents)
    elif ct.startswith("image/"):
        file_for_ocr, ct_for_ocr = contents, ct
    else:
        raise HTTPException(400, "Formato non supportato (PDF/JPG/PNG)")

    try:
        dati = await ocr_lib.estrai_dati_libretto(file_for_ocr, ct_for_ocr)
    except Exception as e:
        raise HTTPException(503, f"Errore OCR libretto: {e}")

    allegato_id = None
    if polizza_id:
        allegato_id = await _salva_allegato_libretto(polizza_id, file, contents, ct, user)

    await log_attivita(user, "ocr", "polizza", polizza_id, "OCR libretto eseguito")
    return {"dati": dati, "allegato_id": allegato_id, "confidence": None}


# Mappatura: campi OCR (chiavi semplici) -> campi polizza (db_models convention).
_FIELD_MAP = {
    "targa": "targa",
    "telaio": "telaio",
    "marca": "veicolo_marca",
    "modello": "veicolo_modello",
    "tipo_veicolo": "veicolo_tipo",
    "alimentazione": "veicolo_alimentazione",
    "kw": "veicolo_kw",
    "cv": "veicolo_cv_fiscali",
    "cilindrata": "veicolo_cilindrata",
    "data_immatricolazione": "veicolo_data_immatricolazione",
}


@router.post("/ocr/libretto/apply")
async def ocr_libretto_apply(
    body: dict,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Applica i campi estratti alla polizza.

    body = {polizza_id, dati: {<chiavi semplici>}, allegato_id, campi: [str]}
    """
    polizza_id = body.get("polizza_id")
    dati = body.get("dati") or {}
    campi = body.get("campi") or []
    if not polizza_id:
        raise HTTPException(400, "polizza_id richiesto")
    pol = await db.polizze.find_one({"id": polizza_id}, {"_id": 0})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")

    update = {
        _FIELD_MAP[k]: dati[k]
        for k in campi
        if k in _FIELD_MAP and dati.get(k) not in (None, "")
    }
    if not update:
        return {"updated": 0}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.polizze.update_one({"id": polizza_id}, {"$set": update})
    await log_attivita(
        user, "ocr_applica", "polizza", polizza_id,
        f"Campi applicati: {list(update.keys())}",
    )
    return {"updated": len(update), "campi": list(update.keys())}
