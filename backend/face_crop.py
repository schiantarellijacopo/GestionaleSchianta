"""Ritaglio automatico della foto volto dai documenti di identità → avatar cliente.

- Rilevamento volti LOCALE con OpenCV (Haar cascade): veloce (<1s), nessun costo AI.
- Fallback: bounding box fornita dall'OCR AI (foto_volto_bbox) se OpenCV non trova volti.
- Batch notturno (02:30): processa i documenti già caricati dei clienti senza avatar.
"""
from __future__ import annotations

import logging
import os
from datetime import timezone
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

_scheduler = None


def _detect_face_opencv(img_pil) -> Optional[tuple[int, int, int, int]]:
    """Ritorna (left, top, right, bottom) del volto più grande, o None."""
    import cv2
    import numpy as np
    arr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(arr, scaleFactor=1.1, minNeighbors=5,
                                     minSize=(max(40, arr.shape[1] // 20),) * 2)
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return int(x), int(y), int(x + w), int(y + h)


def crop_volto_bytes(image_bytes: bytes, ai_bbox: Optional[dict] = None) -> Optional[bytes]:
    """Ritaglia la fototessera dal documento. Ritorna JPEG quadrato max 512px o None."""
    from PIL import Image
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None
    W, H = img.size
    box = None
    try:
        det = _detect_face_opencv(img)
        if det:
            l, t, r, b = det
            # margine 45% attorno al volto per includere spalle/capelli
            mw, mh = int((r - l) * 0.45), int((b - t) * 0.55)
            box = (max(0, l - mw), max(0, t - mh), min(W, r + mw), min(H, b + mh))
    except Exception as e:
        logger.warning("OpenCV face detect fallito: %s", e)
    if box is None and ai_bbox and isinstance(ai_bbox, dict):
        x = float(ai_bbox.get("x") or 0)
        y = float(ai_bbox.get("y") or 0)
        w = float(ai_bbox.get("w") or 0)
        h = float(ai_bbox.get("h") or 0)
        if w > 0.05 and h > 0.05:
            pad = 0.05
            box = (max(0, int((x - pad) * W)), max(0, int((y - pad) * H)),
                   min(W, int((x + w + pad) * W)), min(H, int((y + h + pad) * H)))
    if box is None:
        return None
    face = img.crop(box)
    fw, fh = face.size
    side = min(fw, fh)
    face = face.crop(((fw - side) // 2, (fh - side) // 2,
                      (fw - side) // 2 + side, (fh - side) // 2 + side))
    if side > 512:
        face = face.resize((512, 512), Image.LANCZOS)
    out = BytesIO()
    face.save(out, format="JPEG", quality=88)
    return out.getvalue()


def _pdf_first_page_jpeg(pdf_bytes: bytes) -> Optional[bytes]:
    try:
        import pdfplumber
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return None
            img = pdf.pages[0].to_image(resolution=200).original
            out = BytesIO()
            img.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except Exception:
        return None


async def salva_avatar_da_documento(db, anagrafica_id: str, image_bytes: bytes,
                                    ai_bbox: Optional[dict] = None) -> Optional[str]:
    """Crop volto + upload storage + set avatar_url. Ritorna l'URL o None."""
    import storage as obj_storage
    from db_models import _now_iso, _uid
    face = crop_volto_bytes(image_bytes, ai_bbox)
    if not face:
        return None
    path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{anagrafica_id}/avatar_{_uid()}.jpg"
    res = obj_storage.put_object(path, face, "image/jpeg")
    url = f"/api/storage/{res['path']}"
    await db.anagrafiche.update_one(
        {"id": anagrafica_id},
        {"$set": {"avatar_url": url, "avatar_da_documento": True, "updated_at": _now_iso()}},
    )
    return url


async def batch_avatar_notturno(db, limite: int = 300) -> dict:
    """Processa i clienti SENZA avatar che hanno un documento di identità caricato."""
    import storage as obj_storage
    report = {"esaminati": 0, "avatar_creati": 0, "senza_volto": 0, "errori": 0}
    flt = {
        "$and": [
            {"$or": [{"avatar_url": None}, {"avatar_url": {"$exists": False}}, {"avatar_url": ""}]},
            {"$or": [{f"documenti.{t}.storage_path": {"$exists": True}}
                     for t in ("carta_identita", "patente", "passaporto")]},
            {"avatar_batch_fallito": {"$ne": True}},
        ]
    }
    async for ana in db.anagrafiche.find(flt, {"_id": 0, "id": 1, "documenti": 1}).limit(limite):
        report["esaminati"] += 1
        docs = ana.get("documenti") or {}
        trovato = False
        for tipo in ("carta_identita", "patente", "passaporto"):
            d = docs.get(tipo) or {}
            sp = d.get("storage_path")
            if not sp:
                continue
            try:
                data, ctype = obj_storage.get_object(sp)
                if (ctype or "").startswith("application/pdf") or sp.lower().endswith(".pdf"):
                    data = _pdf_first_page_jpeg(data)
                if not data:
                    continue
                url = await salva_avatar_da_documento(db, ana["id"], data)
                if url:
                    report["avatar_creati"] += 1
                    trovato = True
                    break
            except Exception as e:
                logger.warning("Batch avatar %s (%s): %s", ana["id"], tipo, e)
                report["errori"] += 1
        if not trovato:
            report["senza_volto"] += 1
            # non riprovare ogni notte lo stesso documento senza volto rilevabile
            await db.anagrafiche.update_one({"id": ana["id"]},
                                            {"$set": {"avatar_batch_fallito": True}})
    logger.info("Batch avatar notturno: %s", report)
    return report


def start_scheduler(db, *, hour: int = 2, minute: int = 30) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    try:
        from tzlocal import get_localzone
        tz = get_localzone()
    except Exception:
        tz = timezone.utc
    sched = AsyncIOScheduler(timezone=tz)

    async def _job() -> None:
        try:
            await batch_avatar_notturno(db)
        except Exception:
            logger.exception("Errore batch avatar notturno")

    sched.add_job(_job, CronTrigger(hour=hour, minute=minute), id="avatar_notturno")
    sched.start()
    _scheduler = sched
    logger.info("Scheduler batch avatar avviato (ore %02d:%02d)", hour, minute)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
