"""NotebookLM assicurativo — notebook tematici con fonti documentali.

- Chat grounded SOLO sulle fonti del notebook, con citazioni [nome_file · pag. N]
- Generazione automatica: riassunto / FAQ / guida studio
- Audio Overview stile podcast (2 voci AI, MP3 scaricabile)
- Fonti: upload manuale (PDF/DOCX/TXT) + documenti già nel CRM (Biblioteca, allegati)
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from auth import current_user, require_user, decode_token
from database import db
from db_models import _now_iso, _uid
import storage as obj_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notebooklm")

STAFF = ("admin", "collaboratore", "dipendente")
MAX_TESTO_FONTE = 120_000     # caratteri max estratti per fonte
CTX_BUDGET = 60_000           # caratteri di contesto passati al modello
CHAT_MODEL = ("anthropic", "claude-sonnet-4-6")
VOICE_HOST = "onyx"           # Marco
VOICE_COHOST = "nova"         # Giulia


# ------------------------------------------------------------
# Estrazione testo per pagina
# ------------------------------------------------------------
def _estrai_pagine(contents: bytes, filename: str) -> tuple[list[dict], int]:
    """Ritorna ([{n, testo}], n_pagine)."""
    fname = (filename or "").lower()
    if fname.endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            pagine, tot = [], 0
            for i, p in enumerate(pdf.pages, start=1):
                t = (p.extract_text() or "").strip()
                if tot + len(t) > MAX_TESTO_FONTE:
                    t = t[: max(0, MAX_TESTO_FONTE - tot)]
                if t:
                    pagine.append({"n": i, "testo": t})
                    tot += len(t)
            return pagine, len(pdf.pages)
    if fname.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(contents))
        testo = "\n".join(p.text for p in doc.paragraphs if p.text.strip())[:MAX_TESTO_FONTE]
        return ([{"n": None, "testo": testo}] if testo else []), 0
    testo = contents.decode("utf-8", errors="ignore")[:MAX_TESTO_FONTE].strip()
    return ([{"n": None, "testo": testo}] if testo else []), 0


async def _fonte_insert(notebook_id: str, nome_file: str, origine: str,
                        pagine: list[dict], n_pagine: int, size_kb: float, user: dict) -> dict:
    doc = {
        "id": _uid(), "notebook_id": notebook_id, "nome_file": nome_file,
        "origine": origine, "stato": "ready" if pagine else "errore",
        "pagine": pagine, "n_pagine": n_pagine, "size_kb": round(size_kb, 1),
        "caricato_da": user.get("name") or user.get("email"),
        "created_at": _now_iso(),
    }
    await db.nb_fonti.insert_one(doc)
    await db.nb_notebooks.update_one({"id": notebook_id}, {"$set": {"updated_at": _now_iso()}})
    doc.pop("_id", None)
    doc.pop("pagine", None)
    return doc


# ------------------------------------------------------------
# NOTEBOOKS CRUD
# ------------------------------------------------------------
@router.get("/notebooks")
async def list_notebooks(user=Depends(require_user(*STAFF))):
    docs = await db.nb_notebooks.find({}, {"_id": 0}).sort("updated_at", -1).to_list(100)
    for d in docs:
        d["n_fonti"] = await db.nb_fonti.count_documents({"notebook_id": d["id"]})
    return docs


@router.post("/notebooks", status_code=201)
async def create_notebook(body: dict, user=Depends(require_user(*STAFF))):
    titolo = (body.get("titolo") or "").strip()
    if not titolo:
        raise HTTPException(400, "Titolo obbligatorio")
    doc = {
        "id": _uid(), "titolo": titolo,
        "descrizione": (body.get("descrizione") or "").strip(),
        "creato_da": user.get("name") or user.get("email"),
        "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db.nb_notebooks.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/notebooks/{nid}")
async def update_notebook(nid: str, body: dict, user=Depends(require_user(*STAFF))):
    upd = {k: v for k, v in body.items() if k in ("titolo", "descrizione")}
    upd["updated_at"] = _now_iso()
    r = await db.nb_notebooks.update_one({"id": nid}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "Notebook non trovato")
    return {"ok": True}


@router.delete("/notebooks/{nid}")
async def delete_notebook(nid: str, user=Depends(require_user("admin", "collaboratore"))):
    await db.nb_notebooks.delete_one({"id": nid})
    await db.nb_fonti.delete_many({"notebook_id": nid})
    await db.nb_messages.delete_many({"notebook_id": nid})
    async for o in db.nb_outputs.find({"notebook_id": nid, "audio_path": {"$ne": None}}, {"audio_path": 1}):
        try:
            obj_storage.delete_object(o["audio_path"])
        except Exception:
            pass
    await db.nb_outputs.delete_many({"notebook_id": nid})
    return {"ok": True}


@router.get("/notebooks/{nid}")
async def get_notebook(nid: str, user=Depends(require_user(*STAFF))):
    nb = await db.nb_notebooks.find_one({"id": nid}, {"_id": 0})
    if not nb:
        raise HTTPException(404, "Notebook non trovato")
    nb["fonti"] = await db.nb_fonti.find(
        {"notebook_id": nid}, {"_id": 0, "pagine": 0}).sort("created_at", 1).to_list(100)
    nb["outputs"] = await db.nb_outputs.find(
        {"notebook_id": nid}, {"_id": 0, "contenuto_md": 0}).sort("created_at", -1).to_list(50)
    return nb


# ------------------------------------------------------------
# FONTI
# ------------------------------------------------------------
@router.post("/notebooks/{nid}/fonti/upload", status_code=201)
async def upload_fonti(nid: str, files: list[UploadFile] = File(...),
                       user=Depends(require_user(*STAFF))):
    nb = await db.nb_notebooks.find_one({"id": nid}, {"_id": 0, "id": 1})
    if not nb:
        raise HTTPException(404, "Notebook non trovato")
    out = []
    for f in files:
        contents = await f.read()
        try:
            pagine, n_pag = _estrai_pagine(contents, f.filename or "documento")
        except Exception as e:
            logger.warning("NotebookLM: estrazione fallita %s: %s", f.filename, e)
            pagine, n_pag = [], 0
        out.append(await _fonte_insert(nid, f.filename or "documento", "upload",
                                       pagine, n_pag, len(contents) / 1024, user))
    return out


@router.get("/crm-docs")
async def list_crm_docs(user=Depends(require_user(*STAFF))):
    """Documenti già nel CRM selezionabili come fonti."""
    bibl = await db.biblioteca_previdenza.find(
        {"testo_ok": True},
        {"_id": 0, "id": 1, "nome_file": 1, "cartella": 1, "sezione": 1, "pagine": 1},
    ).sort("created_at", -1).to_list(300)
    alleg = await db.allegati.find(
        {"is_deleted": {"$ne": True},
         "content_type": {"$in": ["application/pdf", "text/plain"]}},
        {"_id": 0, "id": 1, "nome_file": 1, "entita_tipo": 1, "size": 1},
    ).sort("created_at", -1).to_list(300)
    return {"biblioteca": bibl, "allegati": alleg}


@router.post("/notebooks/{nid}/fonti/da-crm", status_code=201)
async def add_fonti_da_crm(nid: str, body: dict, user=Depends(require_user(*STAFF))):
    nb = await db.nb_notebooks.find_one({"id": nid}, {"_id": 0, "id": 1})
    if not nb:
        raise HTTPException(404, "Notebook non trovato")
    out = []
    for bid in body.get("biblioteca_ids") or []:
        d = await db.biblioteca_previdenza.find_one({"id": bid}, {"_id": 0})
        if not d:
            continue
        testo = (d.get("testo") or "")[:MAX_TESTO_FONTE]
        pagine = [{"n": None, "testo": testo}] if testo.strip() else []
        out.append(await _fonte_insert(nid, d.get("nome_file") or "documento",
                                       "biblioteca", pagine, d.get("pagine") or 0,
                                       d.get("size_kb") or 0, user))
    for aid in body.get("allegato_ids") or []:
        a = await db.allegati.find_one({"id": aid}, {"_id": 0})
        if not a:
            continue
        try:
            data, _ = obj_storage.get_object(a["storage_path"])
            pagine, n_pag = _estrai_pagine(data, a.get("nome_file") or "allegato")
        except Exception as e:
            logger.warning("NotebookLM: allegato non leggibile %s: %s", aid, e)
            pagine, n_pag = [], 0
        out.append(await _fonte_insert(nid, a.get("nome_file") or "allegato",
                                       "allegato", pagine, n_pag,
                                       float(a.get("size") or 0) / 1024, user))
    return out


@router.delete("/fonti/{fid}")
async def delete_fonte(fid: str, user=Depends(require_user(*STAFF))):
    f = await db.nb_fonti.find_one({"id": fid}, {"_id": 0, "notebook_id": 1})
    if not f:
        raise HTTPException(404, "Fonte non trovata")
    await db.nb_fonti.delete_one({"id": fid})
    await db.nb_notebooks.update_one({"id": f["notebook_id"]}, {"$set": {"updated_at": _now_iso()}})
    return {"ok": True}


# ------------------------------------------------------------
# Contesto per il modello
# ------------------------------------------------------------
async def _sorgenti_context(nid: str, budget: int = CTX_BUDGET) -> tuple[str, int]:
    fonti = await db.nb_fonti.find(
        {"notebook_id": nid, "stato": "ready"}, {"_id": 0}).sort("created_at", 1).to_list(50)
    if not fonti:
        return "", 0
    per_fonte = max(3000, budget // len(fonti))
    blocks = []
    for i, f in enumerate(fonti, start=1):
        usato, parts = 0, [f"═══ FONTE {i}: {f['nome_file']} ═══"]
        for pg in f.get("pagine") or []:
            t = pg.get("testo") or ""
            if usato + len(t) > per_fonte:
                t = t[: max(0, per_fonte - usato)]
            if not t:
                break
            parts.append(f"[pag. {pg['n']}]\n{t}" if pg.get("n") else t)
            usato += len(t)
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks), len(fonti)


CHAT_SYSTEM = """Sei l'assistente NotebookLM di un CRM assicurativo italiano.
Rispondi ESCLUSIVAMENTE sulla base delle FONTI fornite (condizioni di polizza, preventivi, normative, circolari).

REGOLE:
1. OGNI affermazione deve avere la citazione della fonte nel formato: [nome_file · pag. N]
   (se la pagina non è indicata nella fonte usa solo [nome_file]).
2. Se le fonti NON coprono la domanda rispondi: "Le fonti caricate non contengono questa informazione." e suggerisci cosa caricare.
3. NON usare conoscenza esterna. NON inventare numeri, franchigie, massimali o clausole.
4. Italiano professionale, markdown, tabelle per i confronti, elenchi puntati per le condizioni.
5. Sii preciso su: garanzie, massimali, franchigie, scoperti, esclusioni, limiti di indennizzo."""


async def _storia_chat(nid: str, limit: int = 8) -> str:
    msgs = await db.nb_messages.find(
        {"notebook_id": nid}, {"_id": 0, "role": 1, "content": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    if not msgs:
        return ""
    rows = [f"{m['role'].upper()}: {m['content'][:400]}" for m in reversed(msgs)]
    return "\n\nConversazione precedente:\n" + "\n".join(rows)


@router.get("/notebooks/{nid}/messages")
async def get_messages(nid: str, user=Depends(require_user(*STAFF))):
    return await db.nb_messages.find(
        {"notebook_id": nid}, {"_id": 0}).sort("created_at", 1).to_list(300)


@router.post("/notebooks/{nid}/chat")
async def chat(nid: str, body: dict, user=Depends(require_user(*STAFF))):
    domanda = (body.get("message") or "").strip()
    if not domanda:
        raise HTTPException(400, "Messaggio vuoto")
    ctx, n_fonti = await _sorgenti_context(nid)
    if not ctx:
        raise HTTPException(400, "Nessuna fonte leggibile nel notebook. Carica prima i documenti.")
    storia = await _storia_chat(nid)

    prompt = f"FONTI DEL NOTEBOOK ({n_fonti} documenti):\n\n{ctx}{storia}\n\nDOMANDA: {domanda}"

    await db.nb_messages.insert_one({
        "id": _uid(), "notebook_id": nid, "role": "user",
        "content": domanda, "created_at": _now_iso(),
    })

    async def event_gen():
        full = []
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
            llm = LlmChat(
                api_key=os.environ.get("EMERGENT_LLM_KEY"),
                session_id=f"nblm_{nid}",
                system_message=CHAT_SYSTEM,
            ).with_model(*CHAT_MODEL)
            async for ev in llm.stream_message(UserMessage(text=prompt)):
                if isinstance(ev, TextDelta):
                    full.append(ev.content)
                    yield f"data: {json.dumps({'delta': ev.content})}\n\n"
                elif isinstance(ev, StreamDone):
                    break
        except Exception as e:
            logger.exception("NotebookLM chat error: %s", e)
            err = f"⚠️ Errore AI: {str(e)[:200]}"
            full.append(err)
            yield f"data: {json.dumps({'delta': err})}\n\n"
        answer = "".join(full)
        await db.nb_messages.insert_one({
            "id": _uid(), "notebook_id": nid, "role": "assistant",
            "content": answer, "created_at": _now_iso(),
        })
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/notebooks/{nid}/messages")
async def clear_chat(nid: str, user=Depends(require_user(*STAFF))):
    await db.nb_messages.delete_many({"notebook_id": nid})
    return {"ok": True}


# ------------------------------------------------------------
# STUDIO — riassunto / FAQ / guida studio (job in background)
# ------------------------------------------------------------
GEN_PROMPTS = {
    "riassunto": ("Riassunto completo",
                  "Genera un RIASSUNTO strutturato e completo di tutte le fonti: "
                  "panoramica, punti chiave per documento, garanzie/massimali/franchigie rilevanti, "
                  "differenze tra i documenti se confrontabili. Cita sempre [nome_file · pag. N]."),
    "faq": ("FAQ",
            "Genera 12-15 FAQ (domanda + risposta) sulle fonti: le domande che un cliente o un "
            "collaboratore farebbe davvero. Risposte precise con citazioni [nome_file · pag. N]."),
    "guida": ("Guida studio",
              "Genera una GUIDA STUDIO: sezioni tematiche, concetti chiave spiegati, glossario dei "
              "termini tecnici presenti nelle fonti, 8 domande di autoverifica con risposte. "
              "Citazioni [nome_file · pag. N]."),
}


async def _run_generazione(oid: str, nid: str, tipo: str):
    try:
        ctx, n_fonti = await _sorgenti_context(nid)
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        llm = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"nblm_gen_{oid}",
            system_message=CHAT_SYSTEM,
        ).with_model(*CHAT_MODEL)
        resp = await llm.send_message(UserMessage(
            text=f"FONTI ({n_fonti} documenti):\n\n{ctx}\n\nCOMPITO: {GEN_PROMPTS[tipo][1]}"))
        await db.nb_outputs.update_one({"id": oid}, {"$set": {
            "stato": "ready", "contenuto_md": str(resp), "completed_at": _now_iso()}})
    except Exception as e:
        logger.exception("NotebookLM generazione %s: %s", tipo, e)
        await db.nb_outputs.update_one({"id": oid}, {"$set": {
            "stato": "errore", "errore": str(e)[:300]}})


@router.post("/notebooks/{nid}/genera", status_code=202)
async def genera_output(nid: str, body: dict, user=Depends(require_user(*STAFF))):
    tipo = body.get("tipo")
    if tipo not in GEN_PROMPTS:
        raise HTTPException(400, "Tipo non valido (riassunto|faq|guida)")
    ctx, _ = await _sorgenti_context(nid, budget=100)
    if not ctx:
        raise HTTPException(400, "Nessuna fonte leggibile nel notebook.")
    oid = _uid()
    await db.nb_outputs.insert_one({
        "id": oid, "notebook_id": nid, "tipo": tipo,
        "titolo": GEN_PROMPTS[tipo][0], "stato": "generating",
        "contenuto_md": None, "audio_path": None, "created_at": _now_iso(),
    })
    asyncio.create_task(_run_generazione(oid, nid, tipo))
    return {"output_id": oid}


# ------------------------------------------------------------
# AUDIO OVERVIEW — podcast a 2 voci
# ------------------------------------------------------------
def _parse_script(raw: str) -> dict:
    t = re.sub(r"```(?:json)?", "", raw or "").strip().strip("`")
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("Script non in formato JSON")
    return json.loads(t[a:b + 1])


async def _run_audio(oid: str, nid: str):
    try:
        ctx, n_fonti = await _sorgenti_context(nid, budget=40_000)
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        llm = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"nblm_audio_{oid}",
            system_message="Sei un autore di podcast italiani. Rispondi SOLO con JSON valido.",
        ).with_model(*CHAT_MODEL)
        resp = await llm.send_message(UserMessage(text=(
            f"FONTI ({n_fonti} documenti):\n\n{ctx}\n\n"
            "Scrivi la sceneggiatura di un podcast italiano di ~4 minuti in cui MARCO (host, "
            "esperto assicurativo) e GIULIA (co-host, curiosa, fa le domande giuste) discutono in modo "
            "vivace e chiaro il contenuto delle fonti: cosa coprono, garanzie, massimali, franchigie, "
            "esclusioni, cose a cui stare attenti. Tono naturale, botta e risposta, niente saluti lunghi. "
            "16-20 battute, ognuna max 600 caratteri. Basati SOLO sulle fonti.\n"
            'JSON: {"titolo": "...", "dialogo": [{"speaker": "MARCO"|"GIULIA", "testo": "..."}]}'
        )))
        script = _parse_script(str(resp))
        dialogo = script.get("dialogo") or []
        if not dialogo:
            raise ValueError("Dialogo vuoto")

        await db.nb_outputs.update_one({"id": oid}, {"$set": {
            "progress": f"Sintesi vocale 0/{len(dialogo)}"}})

        from emergentintegrations.llm.openai import OpenAITextToSpeech
        tts = OpenAITextToSpeech(api_key=os.environ.get("EMERGENT_LLM_KEY"))
        segments = []
        for i, turn in enumerate(dialogo):
            testo = (turn.get("testo") or "").strip()[:4000]
            if not testo:
                continue
            voice = VOICE_HOST if (turn.get("speaker") or "").upper().startswith("M") else VOICE_COHOST
            segments.append(await tts.generate_speech(text=testo, model="tts-1", voice=voice))
            await db.nb_outputs.update_one({"id": oid}, {"$set": {
                "progress": f"Sintesi vocale {i + 1}/{len(dialogo)}"}})

        audio = b"".join(segments)
        path = f"{os.environ.get('APP_NAME', 'assicura')}/notebooklm/{oid}.mp3"
        obj_storage.put_object(path, audio, "audio/mpeg")

        trascrizione = "\n\n".join(
            f"**{t.get('speaker', '?')}**: {t.get('testo', '')}" for t in dialogo)
        await db.nb_outputs.update_one({"id": oid}, {"$set": {
            "stato": "ready", "titolo": script.get("titolo") or "Audio Overview",
            "audio_path": path, "contenuto_md": trascrizione,
            "durata_stimata_min": round(len(dialogo) * 0.22, 1),
            "progress": None, "completed_at": _now_iso()}})
    except Exception as e:
        logger.exception("NotebookLM audio: %s", e)
        await db.nb_outputs.update_one({"id": oid}, {"$set": {
            "stato": "errore", "errore": str(e)[:300], "progress": None}})


@router.post("/notebooks/{nid}/audio-overview", status_code=202)
async def audio_overview(nid: str, user=Depends(require_user(*STAFF))):
    ctx, _ = await _sorgenti_context(nid, budget=100)
    if not ctx:
        raise HTTPException(400, "Nessuna fonte leggibile nel notebook.")
    oid = _uid()
    await db.nb_outputs.insert_one({
        "id": oid, "notebook_id": nid, "tipo": "audio",
        "titolo": "Audio Overview", "stato": "generating", "progress": "Scrittura sceneggiatura…",
        "contenuto_md": None, "audio_path": None, "created_at": _now_iso(),
    })
    asyncio.create_task(_run_audio(oid, nid))
    return {"output_id": oid}


# ------------------------------------------------------------
# OUTPUTS
# ------------------------------------------------------------
@router.get("/outputs/{oid}")
async def get_output(oid: str, user=Depends(require_user(*STAFF))):
    o = await db.nb_outputs.find_one({"id": oid}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Output non trovato")
    return o


@router.delete("/outputs/{oid}")
async def delete_output(oid: str, user=Depends(require_user(*STAFF))):
    o = await db.nb_outputs.find_one({"id": oid}, {"_id": 0, "audio_path": 1})
    if o and o.get("audio_path"):
        try:
            obj_storage.delete_object(o["audio_path"])
        except Exception:
            pass
    await db.nb_outputs.delete_one({"id": oid})
    return {"ok": True}


@router.get("/outputs/{oid}/audio")
async def get_output_audio(oid: str, request: Request, token: Optional[str] = None):
    """Stream MP3. Il tag <audio> non manda header: accetta anche ?token=."""
    from auth import get_token_from_request
    tk = get_token_from_request(request) or token
    if not tk:
        raise HTTPException(401, "Non autenticato")
    try:
        decode_token(tk)
    except Exception:
        raise HTTPException(401, "Token non valido")
    o = await db.nb_outputs.find_one({"id": oid}, {"_id": 0, "audio_path": 1, "titolo": 1})
    if not o or not o.get("audio_path"):
        raise HTTPException(404, "Audio non trovato")
    data, _ = obj_storage.get_object(o["audio_path"])
    safe = re.sub(r"[^\w\s-]", "", o.get("titolo") or "audio_overview")[:60]
    return StreamingResponse(io.BytesIO(data), media_type="audio/mpeg",
                             headers={"Content-Disposition": f'inline; filename="{safe}.mp3"'})
