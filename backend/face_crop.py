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


def _skin_ratio(rgb_region) -> float:
    """Frazione di pixel con tono pelle nella regione (YCrCb). 0..1."""
    import cv2
    import numpy as np
    if rgb_region.size == 0:
        return 0.0
    ycrcb = cv2.cvtColor(rgb_region, cv2.COLOR_RGB2YCrCb)
    lo = np.array([0, 133, 77], dtype=np.uint8)
    hi = np.array([255, 173, 127], dtype=np.uint8)
    mask = cv2.inRange(ycrcb, lo, hi)
    return float(np.count_nonzero(mask)) / float(mask.size)


def _detect_face_opencv(img_pil) -> Optional[tuple[int, int, int, int]]:
    """Ritorna (left, top, right, bottom) del volto più plausibile, o None.

    Validazione anti-falsi-positivi: scarta box con proporzioni/area implausibili
    e con troppo pochi pixel di tono pelle (evita di ritagliare loghi/testo)."""
    import cv2
    import numpy as np
    rgb = np.array(img_pil)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    H, W = gray.shape[:2]
    min_side = max(40, min(W, H) // 12)
    candidates = []
    for cascade_name in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml"):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + cascade_name)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=7,
                                         minSize=(min_side, min_side))
        for (x, y, w, h) in faces:
            # scarta box implausibili: troppo grandi (documento intero) o proporzioni strane
            if w > 0.6 * W or h > 0.75 * H:
                continue
            if not (0.7 <= w / h <= 1.4):
                continue
            skin = _skin_ratio(rgb[y:y + h, x:x + w])
            if skin < 0.25:  # verosimilmente non è un volto (logo/testo/sfondo)
                continue
            candidates.append((int(x), int(y), int(w), int(h), skin))
        if candidates:
            break
    if not candidates:
        return None
    # miglior candidato: bilancia area e tono pelle
    x, y, w, h, _ = max(candidates, key=lambda f: f[2] * f[3] * (0.5 + f[4]))
    return x, y, x + w, y + h


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
        # accetta solo box plausibili per una fototessera (non il documento intero)
        if 0.05 < w <= 0.5 and 0.05 < h <= 0.8:
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


async def batch_avatar_notturno(db, limite: int = 300, force: bool = False) -> dict:
    """Processa i clienti SENZA avatar che hanno un documento di identità caricato.
    Con force=True rigenera anche gli avatar già creati dai documenti (recrop migliorato)."""
    import storage as obj_storage
    report = {"esaminati": 0, "avatar_creati": 0, "senza_volto": 0, "errori": 0}
    doc_cond = {"$or": [{f"documenti.{t}.storage_path": {"$exists": True}}
                        for t in ("carta_identita", "patente", "passaporto")]}
    if force:
        flt = {"$and": [doc_cond,
                        {"$or": [{"avatar_da_documento": True}, {"avatar_url": {"$in": [None, ""]}},
                                 {"avatar_url": {"$exists": False}}]}]}
    else:
        flt = {"$and": [
            {"$or": [{"avatar_url": None}, {"avatar_url": {"$exists": False}}, {"avatar_url": ""}]},
            doc_cond,
            {"avatar_batch_fallito": {"$ne": True}},
        ]}
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
            if force:
                # se il recrop non trova un volto plausibile, meglio nessun avatar
                # che il documento intero come immagine profilo
                await db.anagrafiche.update_one(
                    {"id": ana["id"], "avatar_da_documento": True},
                    {"$set": {"avatar_url": None}})
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
