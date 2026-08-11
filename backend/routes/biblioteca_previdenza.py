"""Biblioteca — archivio PDF normativi organizzato in sezioni:
- previdenza (PASS PREVIDENZA): base di conoscenza AI per i calcoli pensione
- condizioni (CONDIZIONI DI POLIZZA): condizioni contrattuali delle compagnie

Più le SCHEDE DI CALCOLO auto-generate dall'AI (verifica annuale dei criteri).

Endpoint:
- GET    /biblioteca-previdenza/cartelle?sezione=
- POST   /biblioteca-previdenza/cartelle
- GET    /biblioteca-previdenza/documenti?sezione=&cartella=
- POST   /biblioteca-previdenza/upload         (multi-file drag&drop + push su Drive)
- DELETE /biblioteca-previdenza/documenti/{id}
- GET    /biblioteca-previdenza/documenti/{id}/download
- POST   /biblioteca-previdenza/consulta-ai    (RAG sui documenti della sezione/cartella)
- POST   /biblioteca-previdenza/sync-drive     (import da Google Drive collegato)
- GET    /biblioteca-previdenza/schede-calcolo
- POST   /biblioteca-previdenza/schede-calcolo/genera  (AI: genera/verifica scheda categoria)
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from auth import current_user, require_user
from database import db
from db_models import _now_iso, _uid
import storage as obj_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/biblioteca-previdenza")

DEFAULT_CARTELLE = [
    "DIPENDENTI PRIVATI", "DIPENDENTI PUBBLICI", "LAVORATORI AUTONOMI",
    "LIBERI PROFESSIONISTI", "PENSIONE INTEGRATIVA", "ALTRE CATEGORIE",
    "PLUS", "CHECK LIST",
]
SEZIONI_DRIVE = {
    "PASS PREVIDENZA": "previdenza",
    "CONDIZIONI DI POLIZZA": "condizioni",
}
MAX_TESTO = 80_000  # caratteri di testo estratto salvati per documento
DRIVE_API = "https://www.googleapis.com/drive/v3"


def _sez_query(sezione: str) -> dict:
    """I documenti storici senza campo sezione sono 'previdenza'."""
    if sezione == "previdenza":
        return {"sezione": {"$in": [None, "previdenza"]}}
    return {"sezione": sezione}


# ------------------------------------------------------------
# JOB IN BACKGROUND (evita i timeout del proxy sulle operazioni lunghe)
# ------------------------------------------------------------
async def _job_new(tipo: str) -> str:
    jid = _uid()
    await db.biblioteca_jobs.insert_one({
        "id": jid, "tipo": tipo, "stato": "running", "progress": {},
        "risultato": None, "errore": None, "created_at": _now_iso(),
    })
    return jid


async def _job_update(jid: str, **kw):
    await db.biblioteca_jobs.update_one({"id": jid}, {"$set": kw})


@router.get("/jobs/{jid}")
async def get_job(jid: str, user=Depends(current_user)):
    job = await db.biblioteca_jobs.find_one({"id": jid}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job non trovato")
    return job


def _estrai_testo(contents: bytes, filename: str) -> tuple[str, int]:
    """Ritorna (testo, num_pagine) dal PDF/testo."""
    fname = (filename or "").lower()
    if fname.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(contents)) as pdf:
                pages = [(p.extract_text() or "") for p in pdf.pages]
                return "\n".join(pages)[:MAX_TESTO], len(pages)
        except Exception as e:
            logger.warning("Biblioteca: PDF non leggibile %s: %s", filename, e)
            return "", 0
    try:
        return contents.decode("utf-8", errors="ignore")[:MAX_TESTO], 0
    except Exception:
        return "", 0


@router.get("/cartelle")
async def list_cartelle(sezione: str = "previdenza", user=Depends(current_user)):
    counts = {}
    async for row in db.biblioteca_previdenza.aggregate([
        {"$match": _sez_query(sezione)},
        {"$group": {"_id": "$cartella", "n": {"$sum": 1}}},
    ]):
        counts[row["_id"]] = row["n"]
    custom_q = {"sezione": {"$in": [None, "previdenza"]}} if sezione == "previdenza" else {"sezione": sezione}
    custom = [c["nome"] async for c in db.biblioteca_previdenza_cartelle.find(custom_q, {"_id": 0, "nome": 1})]
    base = DEFAULT_CARTELLE if sezione == "previdenza" else []
    nomi = list(dict.fromkeys(base + custom + list(counts.keys())))
    return [{"nome": n, "documenti": counts.get(n, 0)} for n in nomi]


@router.post("/cartelle", status_code=201)
async def create_cartella(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    nome = (body.get("nome") or "").strip().upper()
    sezione = body.get("sezione") or "previdenza"
    if not nome:
        raise HTTPException(400, "Nome cartella obbligatorio")
    if sezione != "previdenza" or nome not in DEFAULT_CARTELLE:
        await db.biblioteca_previdenza_cartelle.update_one(
            {"nome": nome, "sezione": sezione},
            {"$set": {"nome": nome, "sezione": sezione, "created_at": _now_iso()}}, upsert=True)
    return {"nome": nome, "sezione": sezione}


@router.get("/documenti")
async def list_documenti(cartella: Optional[str] = None, sezione: str = "previdenza",
                         user=Depends(current_user)):
    q = _sez_query(sezione)
    if cartella:
        q["cartella"] = cartella
    docs = await db.biblioteca_previdenza.find(
        q, {"_id": 0, "testo": 0}).sort("created_at", -1).to_list(1500)
    return docs


# ------------------------------------------------------------
# PUSH SU GOOGLE DRIVE dei file caricati manualmente
# ------------------------------------------------------------
async def _drive_push(sezione: str, cartella: str, filename: str,
                      contents: bytes, mime: str, tenant: str) -> bool:
    """Carica il file anche su Google Drive (best-effort)."""
    try:
        from routes.cloud_storage import _fresh_access_token, _ensure_folder_path
        conn = await db.cloud_connections.find_one({"tenant_id": tenant, "provider": "google_drive"})
        if not conn:
            return False
        token = await _fresh_access_token("google_drive", conn)
        root_name = "PASS PREVIDENZA" if sezione == "previdenza" else "CONDIZIONI DI POLIZZA"
        folder_id = await _ensure_folder_path(
            "google_drive", token, ["Assicura CRM", root_name, cartella], tenant)
        meta = {"name": filename, "parents": [folder_id]}
        boundary = "==bibl_bound=="
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
        ).encode() + contents + f"\r\n--{boundary}--".encode()
        async with httpx.AsyncClient(timeout=120) as x:
            r = await x.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true",
                content=body,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": f"multipart/related; boundary={boundary}"})
            r.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Biblioteca: push su Drive fallito per %s: %s", filename, e)
        return False


@router.post("/upload")
async def upload_documenti(
    files: list[UploadFile] = File(...),
    cartella: str = Form(...),
    sezione: str = Form("previdenza"),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Upload multiplo (drag&drop). Estrae il testo per la knowledge base AI
    e carica una copia anche su Google Drive (se collegato)."""
    from routes.cloud_storage import _tenant_id
    cartella = (cartella or "").strip().upper() or "ALTRE CATEGORIE"
    tenant = _tenant_id(user)
    importati, saltati, errori = [], [], []
    su_drive = 0
    for f in files:
        try:
            contents = await f.read()
            if len(contents) > 25 * 1024 * 1024:
                errori.append({"file": f.filename, "errore": "oltre 25 MB"})
                continue
            dup_q = _sez_query(sezione)
            dup_q.update({"cartella": cartella, "nome_file": f.filename})
            dup = await db.biblioteca_previdenza.find_one(dup_q, {"_id": 0, "id": 1})
            if dup:
                saltati.append(f.filename)
                continue
            testo, pagine = _estrai_testo(contents, f.filename or "")
            ext = (f.filename or "doc.pdf").rsplit(".", 1)[-1].lower() or "pdf"
            path = f"{os.environ.get('APP_NAME', 'assicura')}/biblioteca_previdenza/{_uid()}.{ext}"
            try:
                res = obj_storage.put_object(path, contents, f.content_type or "application/pdf")
                path = res["path"]
            except Exception as e:
                errori.append({"file": f.filename, "errore": f"storage: {e}"})
                continue
            await db.biblioteca_previdenza.insert_one({
                "id": _uid(),
                "sezione": sezione,
                "cartella": cartella,
                "sottocartella": None,
                "nome_file": f.filename,
                "mime": f.content_type or "application/pdf",
                "size_kb": round(len(contents) / 1024, 1),
                "pagine": pagine,
                "storage_path": path,
                "url": f"/api/storage/{path}",
                "testo": testo,
                "testo_ok": bool(testo.strip()),
                "caricato_da_nome": user.get("name") or user.get("email"),
                "fonte": "upload",
                "created_at": _now_iso(),
            })
            importati.append(f.filename)
            if await _drive_push(sezione, cartella, f.filename or "documento.pdf",
                                 contents, f.content_type or "application/pdf", tenant):
                su_drive += 1
        except Exception as e:
            errori.append({"file": f.filename, "errore": str(e)[:120]})
    return {"importati": importati, "saltati": saltati, "errori": errori, "su_drive": su_drive}


@router.delete("/documenti/{did}")
async def delete_documento(did: str, user=Depends(require_user("admin", "collaboratore"))):
    doc = await db.biblioteca_previdenza.find_one({"id": did}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Documento non trovato")
    await db.biblioteca_previdenza.delete_one({"id": did})
    return {"ok": True}


@router.get("/documenti/{did}/download")
async def download_documento(did: str, user=Depends(current_user)):
    doc = await db.biblioteca_previdenza.find_one({"id": did}, {"_id": 0})
    if not doc or not doc.get("storage_path"):
        raise HTTPException(404, "Documento non trovato")
    try:
        data, ctype = obj_storage.get_object(doc["storage_path"])
    except Exception as e:
        raise HTTPException(404, f"File non disponibile: {e}")
    return StreamingResponse(
        io.BytesIO(data), media_type=ctype or "application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("nome_file") or "documento.pdf"}"'})


# ============================================================
# AI — consulta la biblioteca come base di conoscenza
# ============================================================
async def _docs_context(sezione: str, cartella: Optional[str], budget: int = 28_000,
                        limit: int = 14) -> tuple[list[str], list[str]]:
    """Ritorna (chunks, fonti) dai documenti con testo leggibile."""
    q = _sez_query(sezione)
    q["testo_ok"] = True
    if cartella:
        q["cartella"] = cartella
    docs = await db.biblioteca_previdenza.find(
        q, {"_id": 0, "nome_file": 1, "cartella": 1, "sottocartella": 1, "testo": 1},
    ).sort("created_at", -1).to_list(limit)
    chunks, fonti = [], []
    for d in docs:
        if budget <= 0:
            break
        t = (d.get("testo") or "")[: min(3000, budget)]
        if not t.strip():
            continue
        origine = d["cartella"] + (f" / {d['sottocartella']}" if d.get("sottocartella") else "")
        chunks.append(f"### Documento: {d['nome_file']} ({origine})\n{t}")
        fonti.append(d["nome_file"])
        budget -= len(t)
    return chunks, fonti


@router.post("/consulta-ai")
async def consulta_ai(body: dict, user=Depends(current_user)):
    """Risponde a una domanda usando i PDF della sezione/cartella indicata
    come base di conoscenza (+ dati del cliente se anagrafica_id è passato)."""
    cartella = (body.get("cartella") or "").strip() or None
    sezione = body.get("sezione") or "previdenza"
    domanda = (body.get("domanda") or "").strip()
    anagrafica_id = body.get("anagrafica_id")
    if not domanda:
        raise HTTPException(400, "Domanda obbligatoria")

    chunks, fonti = await _docs_context(sezione, cartella)
    if not chunks:
        raise HTTPException(404, "Nessun documento con testo leggibile nella cartella. Carica prima i PDF in Biblioteca.")

    cliente_ctx = ""
    if anagrafica_id:
        ana = await db.anagrafiche.find_one({"id": anagrafica_id}, {"_id": 0}) or {}
        ac = await db.analisi_cliente.find_one({"anagrafica_id": anagrafica_id}, {"_id": 0}) or {}
        nome = ana.get("ragione_sociale") or f"{ana.get('cognome', '') or ''} {ana.get('nome', '') or ''}".strip()
        cliente_ctx = (
            f"\n\nDATI CLIENTE:\n- Nome: {nome}\n"
            f"- Data di nascita: {ana.get('data_nascita') or 'n/d'}\n"
            f"- Professione: {ana.get('professione') or 'n/d'}\n"
            f"- Settimane contributive: {ana.get('settimane_contributive') or ac.get('settimane_contributive') or 'n/d'}\n"
            f"- Reddito lordo annuo: {ana.get('reddito_annuo_lordo') or ac.get('reddito_lordo_annuo') or 'n/d'}\n"
            f"- Periodi contributivi registrati: {len(ac.get('periodi_contributivi') or [])}\n"
            f"- Anni di redditi storici: {len(ac.get('storico_redditi') or [])}\n"
        )

    dominio = ("sistema pensionistico italiano (INPS, casse professionali, pensione integrativa)"
               if sezione == "previdenza" else "condizioni contrattuali delle polizze assicurative")
    prompt = (
        f"Sei un consulente esperto del {dominio}. Rispondi SOLO sulla base dei documenti "
        "forniti qui sotto, citando il nome del documento da cui prendi ogni regola. "
        "Se i documenti non coprono la domanda, dillo chiaramente. "
        "Rispondi in italiano, in modo strutturato e operativo.\n\n"
        + "\n\n".join(chunks) + cliente_ctx
        + f"\n\nDOMANDA: {domanda}"
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"bibl_{sezione}_{user.get('id')}",
            system_message="Consulente italiano. Preciso, cita sempre le fonti documentali fornite.",
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        risposta = str(resp) if resp else "(nessuna risposta)"
    except Exception as e:
        logger.exception("Errore AI biblioteca: %s", e)
        raise HTTPException(502, f"Errore AI: {str(e)[:200]}")

    return {"risposta": risposta, "fonti": fonti, "documenti_usati": len(fonti)}


# ============================================================
# SCHEDE DI CALCOLO — generate dall'AI, verificate ogni anno
# ============================================================
def _crm_params_summary() -> str:
    """Fotografia dei criteri di calcolo attuali del CRM (inps_calculator).
    Aggiornato con parametri UFFICIALI verificati 12/02/2026."""
    import inps_calculator as ic
    p = ic.PARAMS
    return (
        "PARAMETRI ATTUALI DEL CRM (modulo inps_calculator) — verifica 12/02/2026:\n"
        f"- Requisito invalidità/inabilità (L. 222/1984): {p['settimane_min_invalidita']} settimane "
        f"(5 anni), di cui {p['settimane_min_invalidita_recenti']} nel quinquennio\n"
        f"- Fallback senza requisiti: invalidità civile 2026 {p['invalidita_civile_mensile_2026']} €/mese × 13\n"
        f"- Trattamento minimo INPS 2026: {p['trattamento_minimo_2026']} €/mese\n"
        "- Montante contributivo: contributi reali se presenti, altrimenti reddito × 33%; "
        "rivalutazione annua con tassi PIL quinquennale INPS ufficiali 2010-2025 (ISTAT)\n"
        "- Assegno ordinario invalidità: montante × coefficiente trasformazione × % invalidità (contributivo puro)\n"
        "- Inabilità (art. 2 L. 222/1984 + L. 335/1995): maggiorazione figurativa fino a 60 anni "
        "(retribuzione × 33% × anni mancanti), poi montante × coefficiente\n"
        "- Superstiti (L. 335/1995 art. 1 c. 41): solo coniuge 60%, coniuge+1 figlio 80%, coniuge+2+ 100%; "
        "solo figli: 1=70%, 2=80%, 3+=100%\n"
        "- Riduzioni Tabella F L.335/1995 per redditi superstite: 0%/25%/40%/50% "
        "(no riduzioni con figli minori/studenti/inabili — Corte Cost. 162/2022)\n"
        f"- Coefficienti di trasformazione biennio 2025-2026 (DM 20/11/2024): "
        f"{json.dumps(p['coefficienti_trasformazione_2025'])}\n"
        f"- Aliquote contributive 2026: dipendenti 33%, gestione separata prof {p['aliquota_gestione_separata_prof']*100:.2f}%, "
        f"artigiani {p['aliquota_artigiani']*100:.0f}%, commercianti {p['aliquota_commercianti']*100:.2f}%\n"
        f"- IRPEF media stimata per netto: {p['irpef_stimata']*100:.0f}%\n"
        "- Pensione mensile = annua / 13 mensilità\n"
    )


@router.get("/schede-calcolo")
async def list_schede(user=Depends(current_user)):
    """Ultima scheda per ogni categoria."""
    out = {}
    async for s in db.schede_calcolo.find({}, {"_id": 0}).sort("generated_at", -1):
        if s["categoria"] not in out:
            out[s["categoria"]] = s
    return list(out.values())


@router.post("/schede-calcolo/genera")
async def genera_scheda(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    """Avvia un JOB IN BACKGROUND per generare la scheda di calcolo di una categoria.
    Ritorna subito il job_id — il frontend polla `GET /biblioteca-previdenza/jobs/{jid}`
    fino a stato "done" (evita i timeout del proxy sulle chiamate AI lunghe).
    """
    import asyncio
    categoria = (body.get("cartella") or body.get("categoria") or "").strip()
    if not categoria:
        raise HTTPException(400, "Categoria obbligatoria")

    chunks, fonti = await _docs_context("previdenza", categoria, budget=30_000, limit=16)
    if not chunks:
        raise HTTPException(404, f"Nessun documento leggibile nella categoria {categoria}")

    jid = await _job_new("schede_calcolo")
    await _job_update(jid, progress={"categoria": categoria, "step": "avvio", "docs": len(fonti)})

    async def _work():
        try:
            await _genera_scheda_worker(jid, categoria, chunks, fonti, user)
        except Exception as e:
            logger.exception("Job schede_calcolo fallito")
            await _job_update(jid, stato="error", errore=str(e)[:500])

    asyncio.create_task(_work())
    return {"job_id": jid, "categoria": categoria, "fonti_count": len(fonti)}


async def _genera_scheda_worker(jid: str, categoria: str, chunks: list, fonti: list, user: dict):
    """Worker in background — genera la scheda AI + confronto semantico + salvataggio."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    await _job_update(jid, progress={"categoria": categoria, "step": "generazione_ai", "docs": len(fonti)})

    prompt = (
        "Sei un attuario esperto del sistema previdenziale italiano. Analizza i documenti "
        f"della categoria «{categoria}» e produci una SCHEDA DI CALCOLO strutturata per le "
        "prestazioni: pensione di invalidità (assegno ordinario), pensione di inabilità, "
        "pensione ai superstiti/premorienza.\n\n"
        + "\n\n".join(chunks)
        + "\n\n" + _crm_params_summary() +
        "\nRispondi SOLO con un JSON valido (nessun testo prima o dopo) con questa struttura:\n"
        "{\n"
        '  "sintesi": "2-3 frasi sulla categoria e le sue specificità",\n'
        '  "requisiti": [{"prestazione": "...", "requisito": "..."}],\n'
        '  "formule": [{"prestazione": "...", "formula": "..."}],\n'
        '  "parametri": [{"nome": "...", "valore": "...", "fonte": "nome documento"}],\n'
        '  "discrepanze_crm": [{"parametro": "...", "valore_crm": "...", "valore_documenti": "...", '
        '"gravita": "alta|media|bassa", "correzione_suggerita": "..."}],\n'
        '  "note_verifica_annuale": "cosa controllare l\'anno prossimo (importi, coefficienti, soglie)"\n'
        "}"
    )
    chat = LlmChat(
        api_key=os.environ.get("EMERGENT_LLM_KEY"),
        session_id=f"scheda_{categoria}_{user.get('id')}_{jid}",
        system_message="Attuario italiano. Rispondi esclusivamente con JSON valido.",
    ).with_model("anthropic", "claude-sonnet-4-6")
    resp = str(await chat.send_message(UserMessage(text=prompt)) or "")

    contenuto = _parse_json_ai(resp)

    await _job_update(jid, progress={"categoria": categoria, "step": "confronto_precedente"})
    anno = datetime.now(timezone.utc).year
    prev = await db.schede_calcolo.find_one(
        {"categoria": categoria}, {"_id": 0}, sort=[("generated_at", -1)])
    stato, diff_note, modifiche, spiegazione_modifiche = await _confronto_scheda(prev, contenuto, categoria, user, jid)

    scheda = {
        "id": _uid(),
        "categoria": categoria,
        "anno": anno,
        "contenuto": contenuto,
        "fonti": fonti,
        "stato_verifica": stato,
        "diff_note": diff_note,
        "modifiche": modifiche,
        "spiegazione_modifiche": spiegazione_modifiche,
        "generato_da": user.get("name") or user.get("email"),
        "generated_at": _now_iso(),
    }
    await db.schede_calcolo.insert_one(dict(scheda))
    scheda.pop("_id", None)
    await _job_update(jid, stato="done", risultato=scheda,
                      progress={"categoria": categoria, "step": "completato"})


def _parse_json_ai(resp: str) -> dict:
    """Parser robusto: pulisce markdown fence, tenta json.loads, fallback progressivi."""
    raw = (resp or "").strip()
    # rimuovi ```json ... ``` fence
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
            if raw.lower().startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
    # rimuovi eventuali \n iniziali/finali
    raw = raw.strip().strip("`").strip()
    if not raw:
        return {"sintesi": "(risposta vuota)", "requisiti": [], "formule": [],
                "parametri": [], "discrepanze_crm": [], "note_verifica_annuale": ""}
    # tentativo 1: parse diretto
    try:
        return json.loads(raw)
    except Exception:
        pass
    # tentativo 2: estrai il primo blocco { ... } valido
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
    except Exception:
        pass
    # fallback: metti tutto il testo nella sintesi
    return {"sintesi": (resp or "")[:2000], "requisiti": [], "formule": [],
            "parametri": [], "discrepanze_crm": [], "note_verifica_annuale": "",
            "_ai_raw_unparsed": True}


async def _confronto_scheda(prev, contenuto, categoria, user, jid):
    """Confronta la nuova scheda con la precedente e ritorna (stato, diff_note, modifiche, spiegazione)."""
    if not prev:
        return "nuova", None, [], None

    def _core(c):
        return json.dumps({k: c.get(k) for k in ("requisiti", "formule", "parametri")},
                          sort_keys=True, ensure_ascii=False)
    if _core(prev.get("contenuto") or {}) == _core(contenuto):
        return "invariata", None, [], None

    # confronto semantico con AI
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        diff_prompt = (
            "Confronta la VECCHIA e la NUOVA scheda di calcolo previdenziale. "
            "Ignora differenze di sola forma/riformulazione: segnala SOLO le modifiche "
            "sostanziali a requisiti, formule, importi, coefficienti o soglie.\n\n"
            f"VECCHIA SCHEDA ({str(prev.get('generated_at'))[:10]}):\n"
            + json.dumps({k: (prev.get("contenuto") or {}).get(k) for k in ("requisiti", "formule", "parametri")}, ensure_ascii=False)
            + "\n\nNUOVA SCHEDA:\n"
            + json.dumps({k: contenuto.get(k) for k in ("requisiti", "formule", "parametri")}, ensure_ascii=False)
            + "\n\nRispondi SOLO con JSON valido:\n"
            "{\n"
            '  "cambiata_sostanza": true/false,\n'
            '  "modifiche": [{"sezione": "requisiti|formule|parametri", "criterio": "...", '
            '"prima": "...", "dopo": "...", "impatto_sul_calcolo": "spiegazione pratica"}],\n'
            '  "spiegazione": "riassunto in 2-4 frasi di cosa è cambiato"\n'
            "}"
        )
        dchat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"scheda_diff_{categoria}_{user.get('id')}_{jid}",
            system_message="Attuario italiano. Rispondi esclusivamente con JSON valido.",
        ).with_model("anthropic", "claude-sonnet-4-6")
        draw = str(await dchat.send_message(UserMessage(text=diff_prompt)) or "").strip()
        dj = _parse_json_ai(draw)
        if dj.get("cambiata_sostanza"):
            return ("cambiata",
                    dj.get("spiegazione") or f"Criteri modificati rispetto alla scheda del {str(prev.get('generated_at'))[:10]}",
                    dj.get("modifiche") or [],
                    dj.get("spiegazione"))
        return "invariata", "Solo riformulazioni testuali: i criteri di calcolo restano invariati.", [], None
    except Exception:
        logger.exception("Errore confronto AI schede")
        return ("cambiata",
                f"Contenuto diverso dalla scheda del {str(prev.get('generated_at'))[:10]} (confronto dettagliato non disponibile)",
                [], None)


# ============================================================
# SYNC GOOGLE DRIVE — importa PASS PREVIDENZA + CONDIZIONI DI POLIZZA
# ============================================================
async def _drive_list(x: httpx.AsyncClient, token: str, q: str) -> list[dict]:
    out, page_token = [], None
    while True:
        params = {"q": q, "fields": "nextPageToken,files(id,name,mimeType,size)",
                  "pageSize": 200, "supportsAllDrives": "true",
                  "includeItemsFromAllDrives": "true"}
        if page_token:
            params["pageToken"] = page_token
        r = await x.get(f"{DRIVE_API}/files", params=params,
                        headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("files") or [])
        page_token = data.get("nextPageToken")
        if not page_token:
            return out


@router.post("/sync-drive")
async def sync_drive(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    """Sincronizza con Google Drive: cerca le cartelle 'PASS PREVIDENZA'
    (sezione previdenza) e 'CONDIZIONI DI POLIZZA' (sezione condizioni),
    anche condivise, e scandisce ricorsivamente le sottocartelle.
    Processa max 20 file per chiamata: rilanciare finché restanti = 0."""
    from routes.cloud_storage import (
        _fresh_access_token, _tenant_id, _ensure_folder_path, _find_folder,
        _create_folder,
    )

    tenant = _tenant_id(user)
    conn = await db.cloud_connections.find_one({"tenant_id": tenant, "provider": "google_drive"})
    if not conn:
        raise HTTPException(400, "Google Drive non collegato: vai in Librerie → Cloud Storage e collega l'account.")
    token = await _fresh_access_token("google_drive", conn)

    async with httpx.AsyncClient(timeout=90) as x:
        roots = []  # (id, sezione)
        cartelle_create = []
        for root_name, sez in SEZIONI_DRIVE.items():
            found = await _drive_list(
                x, token,
                f"name='{root_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false")
            if found:
                roots.extend((f["id"], sez) for f in found)
            elif sez == "previdenza":
                rid = await _ensure_folder_path(
                    "google_drive", token, ["Assicura CRM", root_name], tenant)
                for cart in DEFAULT_CARTELLE:
                    if not await _find_folder("google_drive", token, cart, rid):
                        await _create_folder("google_drive", token, cart, rid)
                        cartelle_create.append(cart)
                roots.append((rid, sez))

        da_importare = []  # (file, sezione, categoria, sottocartella)
        visitate = set()

        async def walk(fid: str, sez: str, categoria: Optional[str],
                       sottocartella: Optional[str], depth: int):
            if fid in visitate or depth > 6:
                return
            visitate.add(fid)
            items = await _drive_list(x, token, f"'{fid}' in parents and trashed=false")
            for it in items:
                if it["mimeType"] == "application/vnd.google-apps.folder":
                    nome_up = (it["name"] or "").strip().upper()
                    if sez == "previdenza" and nome_up in DEFAULT_CARTELLE:
                        await walk(it["id"], sez, nome_up, None, depth + 1)
                    elif categoria is None:
                        await walk(it["id"], sez, nome_up, None, depth + 1)
                    else:
                        sub = it["name"].strip()
                        sub_full = f"{sottocartella} / {sub}" if sottocartella else sub
                        await walk(it["id"], sez, categoria, sub_full, depth + 1)
                elif it["mimeType"] == "application/pdf":
                    da_importare.append((it, sez, categoria or "ALTRE CATEGORIE", sottocartella))

        for rid, sez in roots:
            await walk(rid, sez, None, None, 0)

        importati, saltati, errori = [], [], []
        processati = 0
        restanti = 0
        for p, sez, cart, sub in da_importare:
            dup_q = _sez_query(sez)
            dup_q.update({"cartella": cart, "sottocartella": sub, "nome_file": p["name"]})
            dup = await db.biblioteca_previdenza.find_one(dup_q, {"_id": 0, "id": 1})
            if dup:
                saltati.append(p["name"])
                continue
            if processati >= 20:
                restanti += 1
                continue
            if int(p.get("size") or 0) > 25 * 1024 * 1024:
                errori.append({"file": p["name"], "errore": "oltre 25 MB"})
                continue
            try:
                r = await x.get(f"{DRIVE_API}/files/{p['id']}",
                                params={"alt": "media", "supportsAllDrives": "true"},
                                headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
                contents = r.content
                testo, pagine = _estrai_testo(contents, p["name"])
                path = f"{os.environ.get('APP_NAME', 'assicura')}/biblioteca_previdenza/{_uid()}.pdf"
                res = obj_storage.put_object(path, contents, "application/pdf")
                if sez != "previdenza" or cart not in DEFAULT_CARTELLE:
                    await db.biblioteca_previdenza_cartelle.update_one(
                        {"nome": cart, "sezione": sez},
                        {"$set": {"nome": cart, "sezione": sez, "created_at": _now_iso()}}, upsert=True)
                await db.biblioteca_previdenza.insert_one({
                    "id": _uid(), "sezione": sez, "cartella": cart, "sottocartella": sub,
                    "nome_file": p["name"],
                    "mime": "application/pdf", "size_kb": round(len(contents) / 1024, 1),
                    "pagine": pagine, "storage_path": res["path"],
                    "url": f"/api/storage/{res['path']}",
                    "testo": testo, "testo_ok": bool(testo.strip()),
                    "caricato_da_nome": f"Google Drive ({user.get('name') or user.get('email')})",
                    "fonte": "google_drive", "created_at": _now_iso(),
                })
                importati.append(p["name"])
                processati += 1
            except Exception as e:
                errori.append({"file": p["name"], "errore": str(e)[:120]})

    messaggio = None
    if cartelle_create and not da_importare:
        messaggio = ("Cartella 'Assicura CRM/PASS PREVIDENZA' creata sul tuo Google Drive "
                     "con le sottocartelle categoria. Trascinaci i PDF e premi di nuovo Sincronizza.")
    elif not da_importare:
        messaggio = ("Nessun PDF trovato nelle cartelle 'PASS PREVIDENZA' / 'CONDIZIONI DI POLIZZA'. "
                     "Trascina i PDF nelle sottocartelle e premi di nuovo Sincronizza.")
    return {"importati": importati, "saltati": saltati, "errori": errori,
            "restanti": restanti, "cartelle_create": cartelle_create, "messaggio": messaggio}


# ============================================================
# CERCA CONDIZIONI DI POLIZZA DAL WEB (via AI + download PDF)
# ============================================================
async def _ai_suggerisci_url_condizioni(compagnia: str, prodotto: Optional[str],
                                        ramo: Optional[str]) -> list[str]:
    """Chiede all'AI un elenco di URL PDF pubblici delle condizioni contrattuali.
    Ritorna lista di URL candidati (max 5), da tentare in sequenza."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    q = f"Compagnia: {compagnia}"
    if prodotto:
        q += f"\nProdotto: {prodotto}"
    if ramo:
        q += f"\nRamo: {ramo}"
    prompt = (
        "Sei un assistente esperto del mercato assicurativo italiano. Fornisci fino a 5 URL "
        "PDF ufficiali e pubblicamente accessibili contenenti le CONDIZIONI DI ASSICURAZIONE "
        "(Fascicolo Informativo / Condizioni Generali / Set Informativo) del seguente prodotto.\n\n"
        f"{q}\n\n"
        "Rispondi SOLO con un JSON valido:\n"
        "{\n"
        '  "urls": ["https://...pdf", ...],\n'
        '  "note": "eventuali indicazioni sul reperimento"\n'
        "}\n\n"
        "Se NON conosci URL pubblici affidabili, ritorna urls=[] senza inventare link."
    )
    try:
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"cerca_cond_{compagnia}_{_uid()[:8]}",
            system_message="Assicuratore italiano. Fornisci solo URL PDF reali; se non ne conosci, urls=[].",
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = str(await chat.send_message(UserMessage(text=prompt)) or "")
        raw = resp.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 2:
                raw = parts[1]
                if raw.lower().startswith("json"):
                    raw = raw[4:]
        try:
            data = json.loads(raw.strip())
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(raw[start:end + 1])
            else:
                data = {}
        return [u for u in (data.get("urls") or []) if isinstance(u, str) and u.startswith(("http://", "https://"))][:5]
    except Exception as e:
        logger.warning("AI URL suggestion failed: %s", e)
        return []


async def _scarica_e_salva_pdf(url: str, compagnia: str, cartella: str,
                               nome_file_suggerito: str, user: dict) -> Optional[dict]:
    """Scarica un PDF da URL e lo salva in biblioteca (sezione condizioni).
    Ritorna il documento inserito oppure None se il download fallisce/non è un PDF valido."""
    from urllib.parse import urlparse
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as x:
            r = await x.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AssicuraCRM/1.0)"})
            r.raise_for_status()
            contents = r.content
    except Exception as e:
        logger.info("Download PDF fallito da %s: %s", url, e)
        return None

    if len(contents) < 5_000 or len(contents) > 25 * 1024 * 1024:
        return None
    if not contents.startswith(b"%PDF"):
        return None

    # Estrai testo per verificare che sia davvero un documento di condizioni
    testo, pagine = _estrai_testo(contents, "documento.pdf")
    testo_lower = (testo or "").lower()
    keywords_valide = ["condizioni", "assicurazione", "polizza", "fascicolo informativo",
                       "contratto", "clausola", "articolo"]
    n_keywords = sum(1 for k in keywords_valide if k in testo_lower)
    if n_keywords < 3:
        # Probabilmente non è un documento di condizioni valido
        return None

    # Sanitize nome file
    if not nome_file_suggerito.lower().endswith(".pdf"):
        nome_file_suggerito += ".pdf"
    filename = f"{compagnia}_{nome_file_suggerito}".replace("/", "_").replace("\\", "_")

    # Dedup: se già presente per URL o nome file, skip
    dup = await db.biblioteca_previdenza.find_one(
        {"sezione": "condizioni", "cartella": cartella,
         "$or": [{"nome_file": filename}, {"source_url": url}]},
        {"_id": 0, "id": 1},
    )
    if dup:
        return None

    ext = "pdf"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/biblioteca_previdenza/{_uid()}.{ext}"
    try:
        res = obj_storage.put_object(path, contents, "application/pdf")
        path = res["path"]
    except Exception as e:
        logger.warning("Storage put fallito per %s: %s", filename, e)
        return None

    doc_row = {
        "id": _uid(),
        "sezione": "condizioni",
        "cartella": cartella,
        "sottocartella": None,
        "nome_file": filename,
        "mime": "application/pdf",
        "size_kb": round(len(contents) / 1024, 1),
        "pagine": pagine,
        "storage_path": path,
        "url": f"/api/storage/{path}",
        "source_url": url,
        "testo": testo,
        "testo_ok": bool(testo.strip()),
        "caricato_da_nome": f"Ricerca Web ({user.get('name') or user.get('email')})",
        "fonte": "web_search",
        "created_at": _now_iso(),
    }
    await db.biblioteca_previdenza.insert_one(dict(doc_row))
    return doc_row


@router.post("/cerca-condizioni")
async def cerca_condizioni(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    """Cerca condizioni di polizza dal web per una compagnia+prodotto specifici.
    Chiede all'AI URL PDF candidati e tenta il download automatico.

    Body: {"compagnia": "Generali", "prodotto": "Global 3.0", "ramo": "Auto"}
    """
    compagnia = (body.get("compagnia") or "").strip()
    prodotto = (body.get("prodotto") or "").strip() or None
    ramo = (body.get("ramo") or "").strip() or None
    if not compagnia:
        raise HTTPException(400, "Compagnia obbligatoria")

    urls = await _ai_suggerisci_url_condizioni(compagnia, prodotto, ramo)
    tentati = []
    importati = []
    cartella = (ramo or "GENERALE").upper()

    for url in urls:
        tentati.append(url)
        nome_sugg = (prodotto or ramo or compagnia).replace(" ", "_")
        doc = await _scarica_e_salva_pdf(url, compagnia, cartella, nome_sugg, user)
        if doc:
            importati.append({
                "nome_file": doc["nome_file"], "size_kb": doc["size_kb"],
                "pagine": doc["pagine"], "source_url": doc["source_url"],
            })

    return {
        "compagnia": compagnia,
        "prodotto": prodotto,
        "ramo": ramo,
        "urls_suggeriti": urls,
        "urls_tentati": tentati,
        "importati": importati,
        "messaggio": (
            f"{len(importati)} documenti importati da {len(tentati)} URL tentati."
            if importati else
            "Nessun documento affidabile trovato. Prova a caricare manualmente il PDF "
            "delle condizioni oppure sincronizza da Google Drive."
        ),
    }


@router.post("/cerca-condizioni-bulk")
async def cerca_condizioni_bulk(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    """Avvia un JOB IN BACKGROUND per cercare le condizioni di polizza di tutte
    le compagnie attive del CRM (o del subset specificato).

    Body opzionale:
    - compagnie_ids: lista di ID compagnia (se omesso, prende tutte)
    - solo_mancanti: bool (default true) — salta le compagnie che hanno già almeno un doc
    """
    import asyncio
    compagnie_ids = body.get("compagnie_ids") or None
    solo_mancanti = body.get("solo_mancanti", True)

    q = {}
    if compagnie_ids:
        q["id"] = {"$in": list(compagnie_ids)}
    compagnie = await db.compagnie.find(q, {"_id": 0, "id": 1, "ragione_sociale": 1}).to_list(500)
    if not compagnie:
        raise HTTPException(404, "Nessuna compagnia trovata")

    jid = await _job_new("cerca_condizioni_bulk")
    await _job_update(jid, progress={"totale": len(compagnie), "processate": 0, "importati": 0})

    async def _work():
        try:
            processate = 0
            tot_importati = 0
            report = []
            for comp in compagnie:
                nome_comp = comp.get("ragione_sociale") or "(senza nome)"
                if solo_mancanti:
                    esistente = await db.biblioteca_previdenza.find_one(
                        {"sezione": "condizioni",
                         "$or": [{"nome_file": {"$regex": f"^{re.escape(nome_comp)}", "$options": "i"}}]},
                        {"_id": 0, "id": 1},
                    )
                    if esistente:
                        processate += 1
                        report.append({"compagnia": nome_comp, "esito": "gia_presente"})
                        await _job_update(jid, progress={"totale": len(compagnie),
                                                        "processate": processate,
                                                        "importati": tot_importati,
                                                        "corrente": nome_comp})
                        continue
                urls = await _ai_suggerisci_url_condizioni(nome_comp, None, None)
                importati = 0
                for url in urls:
                    doc = await _scarica_e_salva_pdf(url, nome_comp, "GENERALE",
                                                     f"condizioni_{nome_comp}", user)
                    if doc:
                        importati += 1
                        tot_importati += 1
                processate += 1
                report.append({"compagnia": nome_comp, "urls": len(urls), "importati": importati})
                await _job_update(jid, progress={"totale": len(compagnie),
                                                "processate": processate,
                                                "importati": tot_importati,
                                                "corrente": nome_comp})
                # rate-limit soft per evitare di abusare della LLM key
                await asyncio.sleep(1)
            await _job_update(jid, stato="done", risultato={
                "totale_compagnie": len(compagnie),
                "importati_totali": tot_importati,
                "report": report,
            }, progress={"totale": len(compagnie), "processate": processate,
                         "importati": tot_importati, "step": "completato"})
        except Exception as e:
            logger.exception("Job cerca_condizioni_bulk fallito")
            await _job_update(jid, stato="error", errore=str(e)[:500])

    # import re dentro il worker
    asyncio.create_task(_work())
    return {"job_id": jid, "totale_compagnie": len(compagnie),
            "modalita": "solo_mancanti" if solo_mancanti else "riprocessa_tutte"}
