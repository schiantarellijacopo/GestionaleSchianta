"""Cloud OCR Scanner — pipeline notturna che legge la cartella INBOX del cloud
storage collegato, esegue OCR con Gemini Vision, classifica i documenti e li
smista automaticamente nelle sotto-cartelle corrette + collega al gestionale.

Flusso per ogni file trovato in INBOX:
  1) Download → Gemini Vision → JSON classificato con tipo documento e dati chiave
  2) Match anagrafica/polizza/sinistro nel CRM (per codice_fiscale, targa, numero)
  3) Se match trovato:
       - Sposta file nella cartella specifica corretta
       - Crea record in `documenti_inbox_processed` collegato all'entità
       - Log nel Diario Cliente
  4) Se NON match:
       - Sposta file in "Da smistare manualmente"
       - Crea alert per l'admin dell'agenzia

Scheduler: cron ogni ora dalle 22:00 alle 06:00 UTC (finestra notturna).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("cloud_ocr_scanner")

_scheduler: Optional[AsyncIOScheduler] = None


# ============================================================
# PROMPT Gemini per classificazione documento
# ============================================================
CLASSIFY_PROMPT = """Sei un classificatore documenti per un CRM assicurativo italiano.
Analizza l'immagine/PDF e restituisci ESCLUSIVAMENTE un JSON valido con questa struttura:

{
  "tipo_documento": "carta_identita | patente | passaporto | codice_fiscale | privacy | polizza_frontespizio | quietanza | denuncia_sinistro | estratto_conto_compagnia | bonifico | rid | altro",
  "confidenza": "alta | media | bassa",
  "dati_estratti": {
    "codice_fiscale": "16 caratteri uppercase o null",
    "partita_iva": "11 cifre o null",
    "cognome": "stringa o null",
    "nome": "stringa o null",
    "numero_polizza": "stringa o null",
    "numero_titolo": "stringa quietanza o null",
    "numero_sinistro": "stringa o null",
    "targa": "AA000AA uppercase o null",
    "compagnia": "nome compagnia o null",
    "data_avvenimento": "YYYY-MM-DD o null",
    "data_effetto": "YYYY-MM-DD o null",
    "data_scadenza": "YYYY-MM-DD o null",
    "data_pagamento": "YYYY-MM-DD o null",
    "importo": "numero decimale o null",
    "anno_riferimento": "YYYY o null",
    "mese_riferimento": "1-12 o null"
  }
}

Regole:
- Non aggiungere testo prima o dopo il JSON
- Non usare markdown ```json```
- Se il documento non è classificabile, usa tipo_documento="altro"
- Cognome/Nome in MAIUSCOLO
- Targa in MAIUSCOLO senza spazi
"""


async def _pdf_to_image_bytes(pdf_bytes: bytes) -> bytes:
    """Converte la PRIMA PAGINA di un PDF in un PNG (da passare a Gemini Vision).

    Uso pypdfium2 perché è già installato e non richiede poppler-utils.
    """
    import pypdfium2 as pdfium
    from io import BytesIO
    pdf = pdfium.PdfDocument(pdf_bytes)
    if len(pdf) == 0:
        raise ValueError("PDF vuoto")
    page = pdf[0]
    # Renderizza a 200 DPI (compromesso qualità/dimensione per Gemini)
    pil_image = page.render(scale=200 / 72).to_pil()
    # Se pagina troppo grande, ridimensiona (Gemini accetta max ~4MB)
    max_dim = 2000
    if max(pil_image.size) > max_dim:
        ratio = max_dim / max(pil_image.size)
        new_size = (int(pil_image.size[0] * ratio), int(pil_image.size[1] * ratio))
        pil_image = pil_image.resize(new_size)
    buf = BytesIO()
    pil_image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def _classify_document(file_bytes: bytes, mime: str) -> dict:
    """Chiama Gemini Vision per classificare + estrarre dati.

    Se il file è PDF, converte la prima pagina in PNG (Gemini Vision accetta
    solo immagini). File multi-pagina: viene classificata solo la prima.
    """
    from emergentintegrations.llm.chat import (
        LlmChat, UserMessage, ImageContent, TextDelta, StreamDone,
    )
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY non configurata")

    # Conversione PDF → immagine se necessario
    if mime == "application/pdf" or file_bytes[:4] == b"%PDF":
        try:
            file_bytes = await _pdf_to_image_bytes(file_bytes)
        except Exception as e:
            logger.warning("Conversione PDF→image fallita (%s): fallback su bytes originali", e)

    b64 = base64.b64encode(file_bytes).decode("ascii")
    img = ImageContent(image_base64=b64)
    chat = LlmChat(
        api_key=key,
        session_id=f"cloud-ocr-{os.urandom(4).hex()}",
        system_message="Classifica e estrai dati da documenti assicurativi italiani.",
    ).with_model("gemini", "gemini-3-flash-preview")
    msg = UserMessage(text=CLASSIFY_PROMPT, file_contents=[img])
    text = ""
    async for ev in chat.stream_message(msg):
        if isinstance(ev, TextDelta):
            text += ev.content
        elif isinstance(ev, StreamDone):
            break
    raw = re.sub(r"^```(?:json)?", "", text.strip(),
                 flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        logger.warning("Gemini classify: risposta senza JSON: %s", raw[:200])
        return {"tipo_documento": "altro", "confidenza": "bassa", "dati_estratti": {}}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"tipo_documento": "altro", "confidenza": "bassa", "dati_estratti": {}}
    parsed.setdefault("tipo_documento", "altro")
    parsed.setdefault("confidenza", "bassa")
    parsed.setdefault("dati_estratti", {})
    return parsed


# ============================================================
# MATCHING nel CRM
# ============================================================
async def _find_anagrafica(db, tenant_id: str, data: dict) -> Optional[dict]:
    """Cerca l'anagrafica per CF/P.IVA (tenant-safe: matcha anche legacy senza tenant_id)."""
    cf = (data.get("codice_fiscale") or "").upper().strip()
    piva = (data.get("partita_iva") or "").strip()
    tenant_q = {"$or": [{"tenant_id": tenant_id}, {"tenant_id": {"$exists": False}}, {"tenant_id": None}]}
    if cf:
        a = await db.anagrafiche.find_one(
            {**tenant_q, "codice_fiscale": cf},
            {"_id": 0, "id": 1, "cognome_nome": 1, "cognome": 1, "nome": 1,
             "ragione_sociale": 1, "codice_fiscale": 1},
        )
        if a:
            a["cognome_nome"] = (a.get("cognome_nome")
                                  or a.get("ragione_sociale")
                                  or f"{a.get('cognome','')} {a.get('nome','')}".strip())
            return a
    if piva:
        a = await db.anagrafiche.find_one(
            {**tenant_q, "partita_iva": piva},
            {"_id": 0, "id": 1, "cognome_nome": 1, "cognome": 1, "nome": 1,
             "ragione_sociale": 1, "partita_iva": 1},
        )
        if a:
            a["cognome_nome"] = (a.get("cognome_nome")
                                  or a.get("ragione_sociale")
                                  or f"{a.get('cognome','')} {a.get('nome','')}".strip())
            return a
    return None


async def _find_polizza(db, tenant_id: str, data: dict) -> Optional[dict]:
    """Cerca la polizza per numero_polizza o per targa."""
    num = (data.get("numero_polizza") or "").strip()
    targa = (data.get("targa") or "").upper().strip()
    tenant_q = {"$or": [{"tenant_id": tenant_id}, {"tenant_id": {"$exists": False}}, {"tenant_id": None}]}
    if num:
        p = await db.polizze.find_one(
            {**tenant_q, "numero_polizza": num},
            {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "targa": 1},
        )
        if p:
            return p
    if targa:
        p = await db.polizze.find_one(
            {**tenant_q, "targa": targa, "stato": {"$in": ["attiva", "sospesa"]}},
            {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "targa": 1},
        )
        if p:
            return p
    return None


async def _find_or_create_anagrafica(db, tenant_id: str, data: dict) -> tuple:
    """Cerca anagrafica per CF/P.IVA. Se non trovata E ci sono dati sufficienti,
    la crea automaticamente e ritorna (anagrafica, was_created).

    Ritorna: (ana | None, bool_created)
    """
    ana = await _find_anagrafica(db, tenant_id, data)
    if ana:
        return ana, False

    cf = (data.get("codice_fiscale") or "").upper().strip()
    piva = (data.get("partita_iva") or "").strip()
    cognome = (data.get("cognome") or "").strip().upper()
    nome = (data.get("nome") or "").strip().upper()

    # Servono almeno CF (persona fisica) o P.IVA (giuridica) + un nome/ragione
    if not (cf or piva):
        return None, False
    if not (cognome or nome):
        return None, False

    from uuid import uuid4
    now = datetime.now(timezone.utc).isoformat()
    is_persona_giuridica = bool(piva) and not cf
    ana_id = str(uuid4())
    doc = {
        "id": ana_id,
        "tenant_id": tenant_id if tenant_id != "default" else None,
        "tipo": "persona_giuridica" if is_persona_giuridica else "persona_fisica",
        "created_at": now, "updated_at": now,
        "fonte": "ocr_cloud_drive",
        "note_interne": "Anagrafica creata automaticamente dallo scan OCR notturno del Google Drive/OneDrive",
    }
    if is_persona_giuridica:
        doc["ragione_sociale"] = cognome or nome  # in questo caso "cognome" è il nome ditta
        doc["partita_iva"] = piva
        doc["cognome_nome"] = doc["ragione_sociale"]
        if cf:
            doc["codice_fiscale"] = cf
    else:
        doc["cognome"] = cognome or "SCONOSCIUTO"
        doc["nome"] = nome or ""
        doc["cognome_nome"] = f"{doc['cognome']} {doc['nome']}".strip()
        if cf:
            doc["codice_fiscale"] = cf
        if piva:
            doc["partita_iva"] = piva
        # Aggiungi data scadenza documento se estratta (per calendar reminder)
        scad = data.get("data_scadenza")
        if scad:
            doc["scadenza_documento_identita"] = scad

    try:
        await db.anagrafiche.insert_one(doc)
        # Rimuovi _id per output pulito
        doc.pop("_id", None)
        return doc, True
    except Exception as e:
        logger.warning("Impossibile creare anagrafica auto (CF=%s): %s", cf, e)
        return None, False


async def _find_sinistro(db, tenant_id: str, data: dict) -> Optional[dict]:
    """Cerca il sinistro per numero_sinistro."""
    num = (data.get("numero_sinistro") or "").strip()
    if not num:
        return None
    return await db.sinistri.find_one(
        {"$or": [{"tenant_id": tenant_id}, {"tenant_id": {"$exists": False}}, {"tenant_id": None}],
         "numero_sinistro": num},
        {"_id": 0, "id": 1, "polizza_id": 1, "contraente_id": 1, "numero_sinistro": 1},
    )


# ============================================================
# ROUTING: mappa tipo_documento → (category, context builder)
# ============================================================
def _route_document(classification: dict, ana: Optional[dict],
                    pol: Optional[dict], sin: Optional[dict]) -> tuple:
    """Ritorna (category, context_dict, related_entity) per il routing.

    related_entity: {"kind": "anagrafica|polizza|sinistro", "id": "..."} o None
    """
    tipo = (classification.get("tipo_documento") or "altro").lower()
    data = classification.get("dati_estratti") or {}
    now = datetime.now(timezone.utc)

    ana_name = (ana or {}).get("cognome_nome", "").strip() or None
    pol_num = (pol or {}).get("numero_polizza", "").strip() or None
    sin_num = (sin or {}).get("numero_sinistro", "").strip() or None

    # Ogni categoria di doc → (folder_category, ha_bisogno_di_cliente)
    ROUTING = {
        "carta_identita": ("contraente_identita", "cliente"),
        "patente": ("contraente_identita", "cliente"),
        "passaporto": ("contraente_identita", "cliente"),
        "codice_fiscale": ("contraente_codice_fiscale", "cliente"),
        "privacy": ("contraente_privacy", "cliente"),
        "polizza_frontespizio": ("polizza_documenti", "polizza"),
        "quietanza": ("quietanze_anno", "anno"),
        "denuncia_sinistro": ("sinistro_specifico", "sinistro"),
        "estratto_conto_compagnia": ("contabilita_estratti", "anno"),
        "bonifico": ("contabilita_prima_nota", "anno_mese"),
        "rid": ("contabilita_prima_nota", "anno_mese"),
    }
    routing_info = ROUTING.get(tipo)
    if not routing_info:
        return ("da_smistare", {}, None)

    category, requirement = routing_info
    if requirement == "cliente":
        if not ana_name:
            return ("da_smistare", {}, None)
        return (category, {"cliente": ana_name}, {"kind": "anagrafica", "id": ana["id"]})
    if requirement == "polizza":
        if not pol_num:
            return ("da_smistare", {}, None)
        return (category, {"polizza": pol_num}, {"kind": "polizza", "id": pol["id"]})
    if requirement == "sinistro":
        if not sin_num:
            return ("da_smistare", {}, None)
        return (category, {"sinistro": sin_num}, {"kind": "sinistro", "id": sin["id"]})
    if requirement == "anno":
        anno = data.get("anno_riferimento") or now.year
        return (category, {"anno": anno}, None)
    if requirement == "anno_mese":
        anno = data.get("anno_riferimento") or now.year
        mese = data.get("mese_riferimento") or now.month
        return (category, {"anno": anno, "mese": mese}, None)
    return ("da_smistare", {}, None)


# ============================================================
# PIPELINE MAIN
# ============================================================
async def scan_tenant_inbox(db, tenant_id: str, provider: str,
                            manual: bool = False) -> dict:
    """Scansiona la cartella INBOX di un tenant/provider ed elabora ogni file.

    Ritorna un report {letti, abbinati, in_attesa, errori: [...], entries: [...]}.
    """
    from routes.cloud_storage import (
        _fresh_access_token, _find_folder, _ensure_folder_path,
        _resolve_category_path,
    )
    conn = await db.cloud_connections.find_one({
        "tenant_id": tenant_id, "provider": provider,
    })
    if not conn:
        return {"skipped": True, "reason": "Nessuna connessione cloud", "letti": 0}

    try:
        token = await _fresh_access_token(provider, conn)
    except Exception as e:
        return {"skipped": True, "reason": f"Token refresh fallito: {e}", "letti": 0}

    # 1) Trova la cartella INBOX
    inbox_segments = await _resolve_category_path("inbox", {})
    parent = None
    for seg in inbox_segments:
        fid = await _find_folder(provider, token, seg, parent)
        if not fid:
            return {"skipped": True, "reason": "Cartella INBOX non ancora creata",
                    "letti": 0}
        parent = fid
    inbox_id = parent

    # 2) Lista file in INBOX
    files = await _list_files_in_folder(provider, token, inbox_id)
    if not files:
        return {"letti": 0, "abbinati": 0, "in_attesa": 0, "entries": [],
                "provider": provider}

    report = {
        "letti": len(files), "abbinati": 0, "in_attesa": 0,
        "anagrafiche_create": 0,
        "errori": [], "entries": [], "provider": provider,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    for f in files:
        try:
            entry = await _process_file(db, provider, token, tenant_id, f)
            report["entries"].append(entry)
            if entry.get("routed_to") and entry.get("routed_to") != "da_smistare":
                report["abbinati"] += 1
            else:
                report["in_attesa"] += 1
            if entry.get("anagrafica_creata"):
                report["anagrafiche_create"] += 1
        except Exception as e:
            logger.exception("Errore processing file %s", f.get("name"))
            report["errori"].append({"file": f.get("name"), "error": str(e)[:200]})
            report["in_attesa"] += 1

    report["ended_at"] = datetime.now(timezone.utc).isoformat()
    report["manual"] = manual

    # Salva report in DB per la history
    await db.cloud_scan_history.insert_one({
        "tenant_id": tenant_id,
        **{k: v for k, v in report.items() if k != "entries"},
        "entries_summary": report["entries"][:50],  # limita per non gonfiare
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return report


async def _list_files_in_folder(provider: str, token: str, folder_id: str) -> list:
    """Lista i file (non cartelle) dentro folder_id."""
    if provider == "google_drive":
        q = (f"'{folder_id}' in parents and trashed=false "
             f"and mimeType != 'application/vnd.google-apps.folder'")
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": q, "fields": "files(id,name,mimeType,size)", "pageSize": 100},
            )
        r.raise_for_status()
        return r.json().get("files", [])
    # OneDrive
    url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}/children"
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.get(url, headers={"Authorization": f"Bearer {token}"},
                        params={"$filter": "file ne null",
                                "$select": "id,name,file,size"})
    r.raise_for_status()
    return [
        {"id": it["id"], "name": it["name"],
         "mimeType": (it.get("file") or {}).get("mimeType", "application/octet-stream"),
         "size": it.get("size", 0)}
        for it in r.json().get("value", [])
    ]


async def _download_file(provider: str, token: str, file_id: str) -> bytes:
    """Scarica il contenuto del file."""
    if provider == "google_drive":
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    else:
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as x:
        r = await x.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.content


async def _move_file(provider: str, token: str, file_id: str,
                     new_parent_id: str, old_parent_id: str) -> None:
    """Sposta il file dalla cartella old_parent alla new_parent."""
    if provider == "google_drive":
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.patch(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"addParents": new_parent_id, "removeParents": old_parent_id},
            )
        r.raise_for_status()
    else:
        # OneDrive: PATCH per cambiare parentReference
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.patch(
                url,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"parentReference": {"id": new_parent_id}},
            )
        r.raise_for_status()


async def _process_file(db, provider: str, token: str, tenant_id: str,
                        f: dict) -> dict:
    """Elabora un singolo file: download → OCR → match → sposta → log."""
    from routes.cloud_storage import _ensure_folder_path, _resolve_category_path

    file_id = f["id"]
    name = f.get("name", "unknown")
    mime = f.get("mimeType", "application/octet-stream")

    # Skip file troppo grandi (>15MB)
    size = int(f.get("size") or 0)
    if size > 15 * 1024 * 1024:
        return {"file_id": file_id, "name": name,
                "routed_to": "da_smistare", "reason": "File >15MB, saltato"}

    # Solo PDF/immagini
    if not (mime.startswith("image/") or mime == "application/pdf"):
        # Sposta comunque in "da smistare" e prosegui
        try:
            segments = await _resolve_category_path("da_smistare", {})
            parent = await _ensure_folder_path(provider, token, segments, tenant_id)
            # Trova il parent originale (INBOX)
            inbox_segments = await _resolve_category_path("inbox", {})
            inbox_id = await _ensure_folder_path(provider, token, inbox_segments, tenant_id)
            await _move_file(provider, token, file_id, parent, inbox_id)
        except Exception as e:
            logger.warning("Errore spostamento file non-supportato %s: %s", name, e)
        return {"file_id": file_id, "name": name,
                "routed_to": "da_smistare", "reason": f"MIME non supportato ({mime})"}

    # Download + OCR
    file_bytes = await _download_file(provider, token, file_id)
    try:
        classification = await _classify_document(file_bytes, mime)
    except Exception as e:
        classification = {"tipo_documento": "altro", "confidenza": "bassa",
                          "dati_estratti": {}, "ocr_error": str(e)[:200]}

    data = classification.get("dati_estratti") or {}

    # Match nel CRM (crea anagrafica automaticamente se manca e ci sono dati sufficienti)
    ana, anagrafica_creata = await _find_or_create_anagrafica(db, tenant_id, data)
    pol = await _find_polizza(db, tenant_id, data)
    sin = await _find_sinistro(db, tenant_id, data)

    # Routing
    category, ctx, related = _route_document(classification, ana, pol, sin)

    # Ricalcola parent INBOX (per _move_file)
    inbox_segments = await _resolve_category_path("inbox", {})
    inbox_id = await _ensure_folder_path(provider, token, inbox_segments, tenant_id)
    dest_segments = await _resolve_category_path(category, ctx)
    dest_id = await _ensure_folder_path(provider, token, dest_segments, tenant_id)

    try:
        await _move_file(provider, token, file_id, dest_id, inbox_id)
    except Exception as e:
        logger.warning("Errore move file %s: %s", name, e)

    # Log nella collection dei documenti smistati
    doc_record = {
        "tenant_id": tenant_id,
        "provider": provider,
        "file_id": file_id,
        "file_name": name,
        "mime_type": mime,
        "size": size,
        "classification": classification,
        "matched_anagrafica_id": (ana or {}).get("id"),
        "matched_polizza_id": (pol or {}).get("id"),
        "matched_sinistro_id": (sin or {}).get("id"),
        "routed_to": category,
        "routed_path": " / ".join(dest_segments),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.cloud_documents.insert_one(doc_record)

    # Se abbinato ad anagrafica → log nel Diario Cliente
    if ana:
        try:
            titolo_diario = (f"👤 Anagrafica creata da OCR: {classification.get('tipo_documento', 'documento')}"
                             if anagrafica_creata
                             else f"📄 OCR notturno: {classification.get('tipo_documento', 'documento')}")
            await db.diario_voci.insert_one({
                "tenant_id": tenant_id,
                "anagrafica_id": ana["id"],
                "tipo": "documento_ocr",
                "titolo": titolo_diario,
                "descrizione": (f"File '{name}' letto e archiviato in {' / '.join(dest_segments)}."
                                + (" Anagrafica creata automaticamente dai dati estratti." if anagrafica_creata else "")),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "autore": "OCR Automatico",
                "meta": {"file_id": file_id, "provider": provider,
                         "anagrafica_creata": anagrafica_creata},
            })
        except Exception as e:
            logger.debug("Skip log diario: %s", e)

    # Se non abbinato → crea alert
    if category == "da_smistare":
        try:
            await db.avvisi.insert_one({
                "tenant_id": tenant_id,
                "tipo": "documento_non_smistato",
                "priorita": "media",
                "titolo": f"Documento da smistare: {name}",
                "descrizione": (
                    f"Il documento '{name}' è stato analizzato ma non è stato possibile "
                    f"abbinarlo automaticamente. Tipo rilevato: "
                    f"{classification.get('tipo_documento', 'sconosciuto')}."
                ),
                "stato": "aperto",
                "meta": {"cloud_file_id": file_id, "provider": provider,
                         "classification": classification},
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.debug("Skip alert: %s", e)

    return {
        "file_id": file_id, "name": name,
        "tipo_documento": classification.get("tipo_documento"),
        "confidenza": classification.get("confidenza"),
        "routed_to": category,
        "routed_path": " / ".join(dest_segments),
        "matched_anagrafica": (ana or {}).get("cognome_nome"),
        "anagrafica_creata": anagrafica_creata,
        "anagrafica_id": (ana or {}).get("id") if anagrafica_creata else None,
        "matched_polizza": (pol or {}).get("numero_polizza"),
        "matched_sinistro": (sin or {}).get("numero_sinistro"),
    }


# ============================================================
# SCHEDULER
# ============================================================
async def _scan_all_tenants_job(db):
    """Job periodico: scansiona INBOX di TUTTI i tenant con cloud collegato."""
    logger.info("[Cloud OCR] Job notturno avviato")
    connections = db.cloud_connections.find({}, {"_id": 0, "tenant_id": 1, "provider": 1})
    tenants_seen = set()
    async for c in connections:
        key = (c["tenant_id"], c["provider"])
        if key in tenants_seen:
            continue
        tenants_seen.add(key)
        try:
            report = await scan_tenant_inbox(db, c["tenant_id"], c["provider"])
            logger.info("[Cloud OCR] tenant=%s provider=%s: %s",
                        c["tenant_id"], c["provider"],
                        {k: v for k, v in report.items()
                         if k in ("letti", "abbinati", "in_attesa")})
        except Exception:
            logger.exception("[Cloud OCR] Errore su tenant %s", c["tenant_id"])


def start_scheduler(db):
    """Avvia lo scheduler: ogni ora dalle 22:00 alle 06:00 UTC."""
    global _scheduler
    if _scheduler:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _scan_all_tenants_job,
        CronTrigger(hour="22-23,0-5", minute="0"),  # ogni ora dalle 22 alle 05
        args=[db],
        id="cloud_ocr_nightly",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("[Cloud OCR] Scheduler avviato (cron 22-23,0-5, tz=UTC)")


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
