"""Biblioteca Previdenza — archivio PDF normativi (PASS PREVIDENZA) organizzato
in cartelle + knowledge base AI per i calcoli pensione (invalidità/superstiti/premorienza).

Endpoint:
- GET    /biblioteca-previdenza/cartelle
- POST   /biblioteca-previdenza/cartelle
- GET    /biblioteca-previdenza/documenti?cartella=
- POST   /biblioteca-previdenza/upload         (multi-file drag&drop)
- DELETE /biblioteca-previdenza/documenti/{id}
- GET    /biblioteca-previdenza/documenti/{id}/download
- POST   /biblioteca-previdenza/consulta-ai    (RAG sui documenti della cartella)
- POST   /biblioteca-previdenza/sync-drive     (import da Google Drive collegato)
"""
from __future__ import annotations

import io
import logging
import os
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
MAX_TESTO = 80_000  # caratteri di testo estratto salvati per documento


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
async def list_cartelle(user=Depends(current_user)):
    counts = {}
    async for row in db.biblioteca_previdenza.aggregate([
        {"$group": {"_id": "$cartella", "n": {"$sum": 1}}},
    ]):
        counts[row["_id"]] = row["n"]
    custom = [c["nome"] async for c in db.biblioteca_previdenza_cartelle.find({}, {"_id": 0, "nome": 1})]
    nomi = list(dict.fromkeys(DEFAULT_CARTELLE + custom + list(counts.keys())))
    return [{"nome": n, "documenti": counts.get(n, 0)} for n in nomi]


@router.post("/cartelle", status_code=201)
async def create_cartella(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    nome = (body.get("nome") or "").strip().upper()
    if not nome:
        raise HTTPException(400, "Nome cartella obbligatorio")
    if nome not in DEFAULT_CARTELLE:
        await db.biblioteca_previdenza_cartelle.update_one(
            {"nome": nome}, {"$set": {"nome": nome, "created_at": _now_iso()}}, upsert=True)
    return {"nome": nome}


@router.get("/documenti")
async def list_documenti(cartella: Optional[str] = None, user=Depends(current_user)):
    q = {}
    if cartella:
        q["cartella"] = cartella
    docs = await db.biblioteca_previdenza.find(
        q, {"_id": 0, "testo": 0}).sort("created_at", -1).to_list(500)
    return docs


@router.post("/upload")
async def upload_documenti(
    files: list[UploadFile] = File(...),
    cartella: str = Form(...),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Upload multiplo (drag&drop). Estrae il testo per la knowledge base AI."""
    cartella = (cartella or "").strip().upper() or "ALTRE CATEGORIE"
    importati, saltati, errori = [], [], []
    for f in files:
        try:
            contents = await f.read()
            if len(contents) > 25 * 1024 * 1024:
                errori.append({"file": f.filename, "errore": "oltre 25 MB"})
                continue
            dup = await db.biblioteca_previdenza.find_one(
                {"cartella": cartella, "nome_file": f.filename}, {"_id": 0, "id": 1})
            if dup:
                saltati.append(f.filename)
                continue
            testo, pagine = _estrai_testo(contents, f.filename or "")
            ext = (f.filename or "doc.pdf").rsplit(".", 1)[-1].lower() or "pdf"
            path = f"{os.environ.get('APP_NAME', 'assicura')}/biblioteca_previdenza/{_uid()}.{ext}"
            url = None
            try:
                res = obj_storage.put_object(path, contents, f.content_type or "application/pdf")
                path = res["path"]
                url = f"/api/storage/{path}"
            except Exception as e:
                errori.append({"file": f.filename, "errore": f"storage: {e}"})
                continue
            doc = {
                "id": _uid(),
                "cartella": cartella,
                "nome_file": f.filename,
                "mime": f.content_type or "application/pdf",
                "size_kb": round(len(contents) / 1024, 1),
                "pagine": pagine,
                "storage_path": path,
                "url": url,
                "testo": testo,
                "testo_ok": bool(testo.strip()),
                "caricato_da_nome": user.get("name") or user.get("email"),
                "fonte": "upload",
                "created_at": _now_iso(),
            }
            await db.biblioteca_previdenza.insert_one(doc)
            importati.append(f.filename)
        except Exception as e:
            errori.append({"file": f.filename, "errore": str(e)[:120]})
    return {"importati": importati, "saltati": saltati, "errori": errori}


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
@router.post("/consulta-ai")
async def consulta_ai(body: dict, user=Depends(current_user)):
    """Risponde a una domanda previdenziale usando i PDF della cartella indicata
    come base di conoscenza (+ dati del cliente se anagrafica_id è passato)."""
    cartella = (body.get("cartella") or "").strip()
    domanda = (body.get("domanda") or "").strip()
    anagrafica_id = body.get("anagrafica_id")
    if not domanda:
        raise HTTPException(400, "Domanda obbligatoria")

    q = {"testo_ok": True}
    if cartella:
        q["cartella"] = cartella
    docs = await db.biblioteca_previdenza.find(
        q, {"_id": 0, "nome_file": 1, "cartella": 1, "testo": 1},
    ).sort("created_at", -1).to_list(12)
    if not docs:
        raise HTTPException(404, "Nessun documento con testo leggibile nella cartella. Carica prima i PDF in Biblioteca Previdenza.")

    budget = 28_000
    chunks, fonti = [], []
    for d in docs:
        if budget <= 0:
            break
        t = (d.get("testo") or "")[: min(3200, budget)]
        if not t.strip():
            continue
        chunks.append(f"### Documento: {d['nome_file']} (cartella {d['cartella']})\n{t}")
        fonti.append(d["nome_file"])
        budget -= len(t)

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

    prompt = (
        "Sei un consulente previdenziale esperto del sistema pensionistico italiano (INPS, casse professionali, "
        "pensione integrativa). Rispondi SOLO sulla base dei documenti forniti qui sotto, citando il nome del "
        "documento da cui prendi ogni regola. Se i documenti non coprono la domanda, dillo chiaramente. "
        "Rispondi in italiano, in modo strutturato e operativo (requisiti, formule, coefficienti, passi da fare).\n\n"
        + "\n\n".join(chunks) + cliente_ctx
        + f"\n\nDOMANDA: {domanda}"
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"bibl_prev_{user.get('id')}",
            system_message="Consulente previdenziale italiano. Preciso, cita sempre le fonti documentali fornite.",
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        risposta = str(resp) if resp else "(nessuna risposta)"
    except Exception as e:
        logger.exception("Errore AI biblioteca previdenza: %s", e)
        raise HTTPException(502, f"Errore AI: {str(e)[:200]}")

    return {"risposta": risposta, "fonti": fonti, "documenti_usati": len(fonti)}


# ============================================================
# SYNC GOOGLE DRIVE — importa la cartella PASS PREVIDENZA
# ============================================================
DRIVE_API = "https://www.googleapis.com/drive/v3"


async def _drive_list(x: httpx.AsyncClient, token: str, q: str) -> list[dict]:
    out, page_token = [], None
    while True:
        params = {"q": q, "fields": "nextPageToken,files(id,name,mimeType,size)",
                  "pageSize": 100, "supportsAllDrives": "true",
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
    """Sincronizza con Google Drive. Al primo avvio CREA la cartella
    'Assicura CRM/PASS PREVIDENZA' con le sottocartelle categoria: l'utente
    ci trascina i PDF e rilancia la sincronizzazione.
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

    # 1) assicura Assicura CRM/PASS PREVIDENZA + sottocartelle categoria
    root_id = await _ensure_folder_path(
        "google_drive", token, ["Assicura CRM", "PASS PREVIDENZA"], tenant)
    cartelle_create = []
    for cart in DEFAULT_CARTELLE:
        found = await _find_folder("google_drive", token, cart, root_id)
        if not found:
            await _create_folder("google_drive", token, cart, root_id)
            cartelle_create.append(cart)

    async with httpx.AsyncClient(timeout=60) as x:
        # 2) sottocartelle → cartelle biblioteca; PDF nella root → ALTRE CATEGORIE
        subfolders = await _drive_list(
            x, token,
            f"'{root_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false")
        targets = [(root_id, "ALTRE CATEGORIE")] + [(sf["id"], sf["name"].strip().upper()) for sf in subfolders]

        da_importare = []
        for fid, cart in targets:
            pdfs = await _drive_list(
                x, token,
                f"'{fid}' in parents and mimeType='application/pdf' and trashed=false")
            for p in pdfs:
                da_importare.append((p, cart))

        importati, saltati, errori = [], [], []
        processati = 0
        restanti = 0
        for p, cart in da_importare:
            dup = await db.biblioteca_previdenza.find_one(
                {"cartella": cart, "nome_file": p["name"]}, {"_id": 0, "id": 1})
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
                if cart not in DEFAULT_CARTELLE:
                    await db.biblioteca_previdenza_cartelle.update_one(
                        {"nome": cart}, {"$set": {"nome": cart, "created_at": _now_iso()}}, upsert=True)
                await db.biblioteca_previdenza.insert_one({
                    "id": _uid(), "cartella": cart, "nome_file": p["name"],
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
        messaggio = ("Nessun PDF trovato in 'Assicura CRM/PASS PREVIDENZA'. "
                     "Trascina i PDF nelle sottocartelle e premi di nuovo Sincronizza.")
    return {"importati": importati, "saltati": saltati, "errori": errori,
            "restanti": restanti, "cartelle_create": cartelle_create, "messaggio": messaggio}
