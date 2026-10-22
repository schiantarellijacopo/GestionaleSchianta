"""Studio Marketing — caroselli Instagram, video reel MP4, siti/landing AI.

- Caroselli: piano AI (Sonnet) → sfondi Nano Banana → testo overlay Pillow (italiano perfetto)
- Video reel 9:16: scene AI → immagini verticali → ffmpeg (Ken Burns + fade) → MP4
- Siti web / landing: HTML completo generato dall'AI, pubblicabile su URL pubblico + ZIP scaricabile
Tutti i lavori girano in background (asyncio) con polling dello stato.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from auth import require_user, decode_token, get_token_from_request
from database import db
from db_models import _now_iso, _uid
import storage as obj_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/marketing")

STAFF = ("admin", "collaboratore", "dipendente")
TEXT_MODEL = ("anthropic", "claude-sonnet-4-6")
IMG_MODEL = ("gemini", "gemini-3.1-flash-image-preview")
FONT_BOLD = "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
FONT_REG = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
APP_NAME = os.environ.get("APP_NAME", "assicura")


# ------------------------------------------------------------
# Helpers comuni
# ------------------------------------------------------------
def _parse_json(raw: str) -> dict:
    t = re.sub(r"```(?:json)?", "", raw or "").strip().strip("`")
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("Risposta AI non in formato JSON")
    return json.loads(t[a:b + 1])


async def _llm_text(prompt: str, system: str = "Rispondi SOLO con JSON valido, in italiano.") -> str:
    from llm_compat import LlmChat, UserMessage
    llm = LlmChat(api_key=os.environ.get("EMERGENT_LLM_KEY"),
                  session_id=f"mkt_{_uid()}", system_message=system).with_model(*TEXT_MODEL)
    return str(await llm.send_message(UserMessage(text=prompt)))


async def _genera_sfondo(prompt: str, verticale: bool = False, orizzontale: bool = False) -> bytes:
    from llm_compat import LlmChat, UserMessage
    chat = LlmChat(api_key=os.environ.get("EMERGENT_LLM_KEY"),
                   session_id=f"mktimg_{_uid()}", system_message="You are a helpful AI assistant")
    chat.with_model(*IMG_MODEL).with_params(modalities=["image", "text"])
    fmt = ("vertical 9:16 portrait format" if verticale
           else "wide 16:9 landscape format" if orizzontale else "square 1:1 format")
    full = (f"Professional marketing background image for an Italian insurance agency. {prompt}. "
            f"{fmt}. NO text, NO words, NO letters in the image. Cinematic, high quality.")
    _t, images = await chat.send_message_multimodal_response(UserMessage(text=full))
    if not images:
        raise ValueError("Il modello non ha restituito immagini")
    return base64.b64decode(images[0]["data"])


def _cover_resize(img, w: int, h: int):
    from PIL import Image
    ratio = max(w / img.width, h / img.height)
    nw, nh = int(img.width * ratio) + 1, int(img.height * ratio) + 1
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = f"{cur} {wd}".strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def _overlay_slide(img_bytes: bytes, *, titolo: str, testo: str, n: int, tot: int,
                   brand: str, w: int = 1080, h: int = 1080, logo=None) -> bytes:
    """Sfondo AI + gradiente scuro + testi (titolo/corpo/numero/brand) → JPEG."""
    from PIL import Image, ImageDraw, ImageFont
    img = _cover_resize(Image.open(io.BytesIO(img_bytes)).convert("RGB"), w, h)
    grad = Image.new("L", (1, h), 0)
    for y in range(h):
        p = max(0, (y - int(h * 0.38)) / (h * 0.62))
        grad.putpixel((0, y), int(210 * (p ** 1.3)))
    overlay = Image.new("RGB", (w, h), (10, 18, 28))
    img = Image.composite(overlay, img, grad.resize((w, h)))
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(FONT_BOLD, int(w * 0.062))
    f_body = ImageFont.truetype(FONT_REG, int(w * 0.036))
    f_small = ImageFont.truetype(FONT_BOLD, int(w * 0.026))
    margin = int(w * 0.074)
    # chip numero slide
    if tot > 1:
        chip = f"{n}/{tot}"
        cw = d.textlength(chip, font=f_small) + 36
        d.rounded_rectangle((margin, margin, margin + cw, margin + int(w * 0.05)), radius=22,
                            fill=(255, 255, 255, 230))
        d.text((margin + 18, margin + int(w * 0.009)), chip, font=f_small, fill=(15, 23, 42))
    # testi dal basso
    body_lines = _wrap(d, testo, f_body, w - 2 * margin) if testo else []
    title_lines = _wrap(d, titolo.upper(), f_title, w - 2 * margin)
    lh_t, lh_b = int(w * 0.075), int(w * 0.05)
    total_h = len(title_lines) * lh_t + len(body_lines) * lh_b + int(w * 0.028)
    y = h - margin - int(w * 0.045) - total_h
    for ln in title_lines:
        d.text((margin, y), ln, font=f_title, fill=(255, 255, 255))
        y += lh_t
    y += int(w * 0.02)
    for ln in body_lines:
        d.text((margin, y), ln, font=f_body, fill=(226, 232, 240))
        y += lh_b
    # brand
    d.text((margin, h - margin - int(w * 0.016)), brand.upper(), font=f_small, fill=(148, 163, 184))
    img = _applica_logo(img, logo, w=w, h=h)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


async def _brand_name() -> str:
    cfg = await db.azienda_config.find_one({}, {"_id": 0, "ragione_sociale": 1}) or {}
    return cfg.get("ragione_sociale") or "La tua agenzia"


_LOGO_CACHE: dict = {}


async def _logo_img():
    """Logo agenzia come PIL RGBA (cache in memoria), o None."""
    if "img" in _LOGO_CACHE:
        return _LOGO_CACHE["img"]
    from PIL import Image
    logo = None
    try:
        cfg = await db.azienda_config.find_one({}, {"_id": 0, "logo_storage_path": 1}) or {}
        sp = cfg.get("logo_storage_path")
        if sp:
            data, _ = obj_storage.get_object(sp)
            logo = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.warning("Logo agenzia non caricabile: %s", e)
    _LOGO_CACHE["img"] = logo
    return logo


def _applica_logo(img, logo, *, w: int, h: int):
    """Incolla il logo in alto a destra (~14% larghezza) su fondo semi-trasparente."""
    from PIL import Image
    if logo is None:
        return img
    lw = int(w * 0.14)
    lh = int(logo.height * lw / logo.width)
    lg = logo.resize((lw, lh), Image.LANCZOS)
    margin = int(w * 0.045)
    x, y = w - lw - margin, margin
    pad = int(w * 0.012)
    base = img.convert("RGBA")
    from PIL import ImageDraw
    chip = Image.new("RGBA", (lw + 2 * pad, lh + 2 * pad), (255, 255, 255, 0))
    d = ImageDraw.Draw(chip)
    d.rounded_rectangle((0, 0, chip.width - 1, chip.height - 1), radius=14, fill=(255, 255, 255, 215))
    base.alpha_composite(chip, (x - pad, y - pad))
    base.alpha_composite(lg, (x, y))
    return base.convert("RGB")


# ------------------------------------------------------------
# CAROSELLI
# ------------------------------------------------------------
@router.post("/caroselli/genera", status_code=202)
async def carosello_genera(body: dict, user=Depends(require_user(*STAFF))):
    argomento = (body.get("argomento") or "").strip()
    if not argomento:
        raise HTTPException(400, "Argomento obbligatorio")
    n = min(8, max(3, int(body.get("n_slides") or 6)))
    con_logo = body.get("con_logo") is not False
    cid = _uid()
    await db.mkt_caroselli.insert_one({
        "id": cid, "argomento": argomento, "n_slides": n, "stato": "generating",
        "progress": "Scrittura piano slide…", "slides": [], "caption": None,
        "creato_da": user.get("name") or user.get("email"), "created_at": _now_iso(),
    })
    asyncio.create_task(_run_carosello(cid, argomento, n, con_logo))
    return {"id": cid}


async def _run_carosello(cid: str, argomento: str, n: int, con_logo: bool = True):
    try:
        brand = await _brand_name()
        logo = await _logo_img() if con_logo else None
        raw = await _llm_text(
            f"Crea il piano di un carosello Instagram di {n} slide per un'agenzia assicurativa "
            f"italiana sull'argomento: {argomento}.\n"
            "Slide 1 = hook fortissimo. Ultima slide = call to action (contattaci). "
            "Ogni slide: titolo (max 8 parole, incisivo), testo (max 25 parole, italiano perfetto), "
            "image_prompt (in inglese, descrive SOLO lo sfondo fotografico, coerente tra slide, senza testo).\n"
            'JSON: {"caption": "caption IG con emoji e 8-12 hashtag italiani", '
            '"slides": [{"titolo": "...", "testo": "...", "image_prompt": "..."}]}')
        piano = _parse_json(raw)
        slides_plan = (piano.get("slides") or [])[:n]
        if not slides_plan:
            raise ValueError("Piano slide vuoto")
        slides = []
        for i, sl in enumerate(slides_plan, start=1):
            await db.mkt_caroselli.update_one({"id": cid}, {"$set": {
                "progress": f"Generazione slide {i}/{len(slides_plan)}…"}})
            bg = await _genera_sfondo(sl.get("image_prompt") or argomento)
            jpg = _overlay_slide(bg, titolo=sl.get("titolo") or "", testo=sl.get("testo") or "",
                                 n=i, tot=len(slides_plan), brand=brand, logo=logo)
            path = f"{APP_NAME}/marketing/caroselli/{cid}/slide_{i}.jpg"
            obj_storage.put_object(path, jpg, "image/jpeg")
            slides.append({"n": i, "titolo": sl.get("titolo"), "testo": sl.get("testo"),
                           "url": f"/api/storage/{path}", "storage_path": path})
        await db.mkt_caroselli.update_one({"id": cid}, {"$set": {
            "stato": "ready", "slides": slides, "caption": piano.get("caption"),
            "progress": None, "completed_at": _now_iso()}})
    except Exception as e:
        logger.exception("Carosello %s fallito", cid)
        await db.mkt_caroselli.update_one({"id": cid}, {"$set": {
            "stato": "errore", "errore": str(e)[:300], "progress": None}})


@router.get("/caroselli")
async def caroselli_list(user=Depends(require_user(*STAFF))):
    return await db.mkt_caroselli.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/caroselli/{cid}/zip")
async def carosello_zip(cid: str, user=Depends(require_user(*STAFF))):
    c = await db.mkt_caroselli.find_one({"id": cid}, {"_id": 0})
    if not c or c.get("stato") != "ready":
        raise HTTPException(404, "Carosello non pronto")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for s in c["slides"]:
            data, _ = obj_storage.get_object(s["storage_path"])
            z.writestr(f"slide_{s['n']:02d}.jpg", data)
        z.writestr("caption.txt", c.get("caption") or "")
    buf.seek(0)
    return Response(buf.read(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="carosello_{cid[:8]}.zip"'})


@router.delete("/caroselli/{cid}")
async def carosello_delete(cid: str, user=Depends(require_user(*STAFF))):
    c = await db.mkt_caroselli.find_one({"id": cid}, {"_id": 0, "slides": 1})
    for s in (c or {}).get("slides") or []:
        try:
            obj_storage.delete_object(s["storage_path"])
        except Exception:
            pass
    await db.mkt_caroselli.delete_one({"id": cid})
    return {"ok": True}


# ------------------------------------------------------------
# VIDEO REEL 9:16
# ------------------------------------------------------------
@router.post("/video/genera", status_code=202)
async def video_genera(body: dict, user=Depends(require_user(*STAFF))):
    argomento = (body.get("argomento") or "").strip()
    if not argomento:
        raise HTTPException(400, "Argomento obbligatorio")
    n = min(6, max(3, int(body.get("n_scene") or 4)))
    con_audio = body.get("con_audio") is not False
    con_sottotitoli = body.get("con_sottotitoli") is not False
    con_logo = body.get("con_logo") is not False
    vid = _uid()
    await db.mkt_video.insert_one({
        "id": vid, "argomento": argomento, "n_scene": n, "stato": "generating",
        "con_audio": con_audio, "con_sottotitoli": con_sottotitoli,
        "progress": "Scrittura sceneggiatura…", "storage_path": None, "caption": None,
        "creato_da": user.get("name") or user.get("email"), "created_at": _now_iso(),
    })
    asyncio.create_task(_run_video(vid, argomento, n, con_audio, con_sottotitoli, con_logo))
    return {"id": vid}


def _ffprobe_durata(path: str) -> float:
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=20)
        return float(out.stdout.strip())
    except Exception:
        return 0.0


async def _run_video(vid: str, argomento: str, n: int,
                     con_audio: bool = True, con_sottotitoli: bool = True, con_logo: bool = True):
    import tempfile
    try:
        brand = await _brand_name()
        logo = await _logo_img() if con_logo else None
        raw = await _llm_text(
            f"Crea la sceneggiatura di un reel Instagram di {n} scene per "
            f"un'agenzia assicurativa italiana su: {argomento}.\n"
            "Scena 1 = hook. Ultima = call to action. Ogni scena: titolo (max 6 parole), "
            "voiceover (frase parlata naturale di 8-15 parole, italiano perfetto), "
            "image_prompt (inglese, solo sfondo, no testo, stile coerente).\n"
            'JSON: {"caption": "caption IG con hashtag", '
            '"scene": [{"titolo": "...", "voiceover": "...", "image_prompt": "..."}]}')
        piano = _parse_json(raw)
        scene = (piano.get("scene") or [])[:n]
        if not scene:
            raise ValueError("Sceneggiatura vuota")

        tts = None
        if con_audio:
            from emergentintegrations.llm.openai import OpenAITextToSpeech
            from ai_keys import openai_key
            tts = OpenAITextToSpeech(api_key=openai_key())

        with tempfile.TemporaryDirectory() as tmp:
            clip_paths = []
            for i, sc in enumerate(scene, start=1):
                voiceover = (sc.get("voiceover") or sc.get("testo") or "").strip()
                await db.mkt_video.update_one({"id": vid}, {"$set": {
                    "progress": f"Scena {i}/{len(scene)}: immagine…"}})
                bg = await _genera_sfondo(sc.get("image_prompt") or argomento, verticale=True)
                jpg = _overlay_slide(
                    bg, titolo=sc.get("titolo") or "",
                    testo=voiceover if con_sottotitoli else "",
                    n=i, tot=len(scene), brand=brand, w=1080, h=1920, logo=logo)
                img_p = os.path.join(tmp, f"scena_{i}.jpg")
                open(img_p, "wb").write(jpg)

                # audio TTS → la durata della scena segue il parlato
                dur = 3.0
                audio_p = None
                if con_audio and voiceover:
                    await db.mkt_video.update_one({"id": vid}, {"$set": {
                        "progress": f"Scena {i}/{len(scene)}: voce narrante…"}})
                    try:
                        mp3 = await tts.generate_speech(text=voiceover, model="tts-1", voice="onyx")
                        audio_p = os.path.join(tmp, f"voce_{i}.mp3")
                        open(audio_p, "wb").write(mp3)
                        dur = max(3.0, _ffprobe_durata(audio_p) + 0.5)
                    except Exception as e:
                        logger.warning("TTS scena %d fallito: %s", i, e)
                        audio_p = None

                clip_p = os.path.join(tmp, f"clip_{i}.mp4")
                frames = int(dur * 25)
                zoom = "z='min(zoom+0.0013,1.13)'" if i % 2 else "z='if(eq(on,1),1.13,max(zoom-0.0013,1.0))'"
                vf = (f"scale=1080:1920,zoompan={zoom}:d={frames}:s=1080x1920:fps=25,"
                      f"fade=t=in:st=0:d=0.35,fade=t=out:st={max(0.4, dur - 0.35):.2f}:d=0.35")
                cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img_p]
                if audio_p:
                    cmd += ["-i", audio_p]
                else:
                    cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
                cmd += ["-vf", vf, "-t", f"{dur:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-preset", "veryfast", "-c:a", "aac", "-shortest", clip_p]
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await proc.wait()
                if proc.returncode != 0 or not os.path.exists(clip_p):
                    raise ValueError(f"ffmpeg fallito sulla scena {i}")
                clip_paths.append((clip_p, dur))

            await db.mkt_video.update_one({"id": vid}, {"$set": {"progress": "Montaggio finale…"}})
            lst = os.path.join(tmp, "list.txt")
            open(lst, "w").write("\n".join(f"file '{p}'" for p, _ in clip_paths))
            out_p = os.path.join(tmp, "reel.mp4")
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                "-c:a", "aac", out_p,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
            if proc.returncode != 0:
                raise ValueError("ffmpeg concat fallito")
            data = open(out_p, "rb").read()
            durata_tot = round(sum(d for _, d in clip_paths), 1)
        path = f"{APP_NAME}/marketing/video/{vid}.mp4"
        obj_storage.put_object(path, data, "video/mp4")
        await db.mkt_video.update_one({"id": vid}, {"$set": {
            "stato": "ready", "storage_path": path, "caption": piano.get("caption"),
            "durata_sec": durata_tot, "size_kb": round(len(data) / 1024, 1),
            "progress": None, "completed_at": _now_iso()}})
    except Exception as e:
        logger.exception("Video %s fallito", vid)
        await db.mkt_video.update_one({"id": vid}, {"$set": {
            "stato": "errore", "errore": str(e)[:300], "progress": None}})


@router.get("/video")
async def video_list(user=Depends(require_user(*STAFF))):
    return await db.mkt_video.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/video/{vid}/file")
async def video_file(vid: str, request: Request, token: Optional[str] = None):
    tk = get_token_from_request(request) or token
    if not tk:
        raise HTTPException(401, "Non autenticato")
    try:
        decode_token(tk)
    except Exception:
        raise HTTPException(401, "Token non valido")
    v = await db.mkt_video.find_one({"id": vid}, {"_id": 0, "storage_path": 1})
    if not v or not v.get("storage_path"):
        raise HTTPException(404, "Video non trovato")
    data, _ = obj_storage.get_object(v["storage_path"])
    return StreamingResponse(io.BytesIO(data), media_type="video/mp4",
                             headers={"Content-Disposition": f'inline; filename="reel_{vid[:8]}.mp4"'})


@router.delete("/video/{vid}")
async def video_delete(vid: str, user=Depends(require_user(*STAFF))):
    v = await db.mkt_video.find_one({"id": vid}, {"_id": 0, "storage_path": 1})
    if v and v.get("storage_path"):
        try:
            obj_storage.delete_object(v["storage_path"])
        except Exception:
            pass
    await db.mkt_video.delete_one({"id": vid})
    return {"ok": True}


# ------------------------------------------------------------
# SITI WEB / LANDING PAGE
# ------------------------------------------------------------
SITO_SYSTEM = """Sei un web designer senior specializzato in siti per agenzie assicurative italiane.
Generi UN SOLO file HTML completo, moderno e professionale:
- CSS inline in <style>, JS minimo inline, responsive mobile-first
- Google Fonts via CDN, palette coerente, sezioni con spaziatura generosa
- Italiano perfetto, testi persuasivi, CTA chiare (tel: e mailto:)
- NIENTE placeholder tipo lorem ipsum: scrivi contenuti reali e credibili
Rispondi SOLO con l'HTML, senza spiegazioni e senza markdown."""


@router.post("/siti/genera", status_code=202)
async def sito_genera(body: dict, user=Depends(require_user(*STAFF))):
    descrizione = (body.get("descrizione") or "").strip()
    if not descrizione:
        raise HTTPException(400, "Descrizione obbligatoria")
    tipo = body.get("tipo") if body.get("tipo") in ("landing", "sito") else "landing"
    sid = _uid()
    slug = re.sub(r"[^a-z0-9-]", "-", (body.get("slug") or descrizione[:30]).lower()).strip("-")[:40] or sid[:8]
    if await db.mkt_siti.find_one({"slug": slug}, {"_id": 1}):
        slug = f"{slug}-{sid[:4]}"
    await db.mkt_siti.insert_one({
        "id": sid, "tipo": tipo, "descrizione": descrizione, "slug": slug,
        "titolo": descrizione[:60], "html": None, "stato": "generating",
        "pubblicato": False,
        "creato_da": user.get("name") or user.get("email"), "created_at": _now_iso(),
    })
    asyncio.create_task(_run_sito(sid, tipo, descrizione))
    return {"id": sid, "slug": slug}


async def _run_sito(sid: str, tipo: str, descrizione: str, istruzioni: str | None = None,
                    html_prec: str | None = None):
    try:
        brand = await _brand_name()
        if istruzioni and html_prec:
            prompt = (f"Modifica questo HTML secondo le istruzioni, mantenendo la qualità: "
                      f"{istruzioni}\n\nHTML ATTUALE:\n{html_prec[:60000]}")
        elif tipo == "sito":
            prompt = (f"Crea il SITO WEB completo (one-page con più sezioni: hero, servizi, "
                      f"chi siamo, perché sceglierci, recensioni, contatti con form mailto) per "
                      f"l'agenzia assicurativa '{brand}'. Richiesta del cliente: {descrizione}")
        else:
            prompt = (f"Crea una LANDING PAGE ad alta conversione (hero con CTA, benefici, "
                      f"prova sociale, FAQ, CTA finale) per l'agenzia assicurativa '{brand}'. "
                      f"Obiettivo della pagina: {descrizione}")
        raw = await _llm_text(prompt, system=SITO_SYSTEM)
        html = re.sub(r"^```(?:html)?|```$", "", raw.strip(), flags=re.M).strip()
        if "<html" not in html.lower():
            raise ValueError("L'AI non ha restituito HTML valido")
        m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        await db.mkt_siti.update_one({"id": sid}, {"$set": {
            "stato": "ready", "html": html,
            "titolo": (m.group(1).strip()[:80] if m else descrizione[:60]),
            "completed_at": _now_iso()}})
    except Exception as e:
        logger.exception("Sito %s fallito", sid)
        await db.mkt_siti.update_one({"id": sid}, {"$set": {
            "stato": "errore", "errore": str(e)[:300]}})


@router.post("/siti/{sid}/modifica", status_code=202)
async def sito_modifica(sid: str, body: dict, user=Depends(require_user(*STAFF))):
    s = await db.mkt_siti.find_one({"id": sid}, {"_id": 0})
    if not s or not s.get("html"):
        raise HTTPException(404, "Sito non trovato o non pronto")
    istruzioni = (body.get("istruzioni") or "").strip()
    if not istruzioni:
        raise HTTPException(400, "Istruzioni obbligatorie")
    await db.mkt_siti.update_one({"id": sid}, {"$set": {"stato": "generating"}})
    asyncio.create_task(_run_sito(sid, s["tipo"], s["descrizione"], istruzioni, s["html"]))
    return {"ok": True}


@router.get("/siti")
async def siti_list(user=Depends(require_user(*STAFF))):
    return await db.mkt_siti.find({}, {"_id": 0, "html": 0}).sort("created_at", -1).to_list(100)


@router.get("/siti/{sid}")
async def sito_get(sid: str, user=Depends(require_user(*STAFF))):
    s = await db.mkt_siti.find_one({"id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Sito non trovato")
    return s


@router.patch("/siti/{sid}")
async def sito_patch(sid: str, body: dict, user=Depends(require_user(*STAFF))):
    upd = {}
    if "pubblicato" in body:
        upd["pubblicato"] = bool(body["pubblicato"])
    if body.get("slug"):
        slug = re.sub(r"[^a-z0-9-]", "-", str(body["slug"]).lower()).strip("-")[:40]
        if await db.mkt_siti.find_one({"slug": slug, "id": {"$ne": sid}}, {"_id": 1}):
            raise HTTPException(409, "Slug già in uso")
        upd["slug"] = slug
    if not upd:
        raise HTTPException(400, "Nessuna modifica")
    r = await db.mkt_siti.update_one({"id": sid}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "Sito non trovato")
    return {"ok": True, **upd}


@router.get("/siti/{sid}/zip")
async def sito_zip(sid: str, user=Depends(require_user(*STAFF))):
    s = await db.mkt_siti.find_one({"id": sid}, {"_id": 0})
    if not s or not s.get("html"):
        raise HTTPException(404, "Sito non pronto")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", s["html"])
        z.writestr("LEGGIMI.txt",
                   "SITO GENERATO CON AI — COME PUBBLICARLO SUL TUO DOMINIO\n"
                   "1) Hosting statico (consigliato): carica index.html su Netlify/Vercel/Aruba/hosting FTP.\n"
                   "2) Dominio: punta il tuo dominio (record A o CNAME) all'hosting scelto.\n"
                   "3) In alternativa il sito è già online sull'URL pubblico del CRM (vedi Studio Marketing).\n")
    buf.seek(0)
    return Response(buf.read(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{s.get("slug", "sito")}.zip"'})


@router.delete("/siti/{sid}")
async def sito_delete(sid: str, user=Depends(require_user(*STAFF))):
    await db.mkt_siti.delete_one({"id": sid})
    return {"ok": True}


# Route PUBBLICA (senza auth): serve il sito pubblicato
@router.get("/public-sito/{slug}")
async def sito_pubblico(slug: str):
    s = await db.mkt_siti.find_one({"slug": slug, "pubblicato": True}, {"_id": 0, "html": 1})
    if not s or not s.get("html"):
        raise HTTPException(404, "Sito non trovato o non pubblicato")
    return HTMLResponse(s["html"])
