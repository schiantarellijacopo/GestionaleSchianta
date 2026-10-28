"""Modelli firma — designer di documenti con campi posizionati.

Flusso:
1. L'agenzia carica un PDF (modello personalizzato).
2. Il backend renderizza le pagine come immagini (base64) per l'editor visivo.
3. L'utente posiziona i campi (tipo 'dato' con una chiave, oppure 'firma') e li salva
   sul modello (coordinate in frazioni 0..1 della pagina).
4. In fase di "compila", i campi 'dato' vengono scritti dentro il PDF con i valori reali
   del cliente/polizza; se esiste un campo 'firma' si crea la richiesta Yousign con il
   campo firma esattamente in quel punto.

Le coordinate sono salvate come frazioni (x,y,w,h ∈ [0,1]) dell'angolo in alto a sinistra,
così restano valide a prescindere dalla risoluzione di rendering.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

import fitz  # pymupdf
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import require_user
import storage as obj_storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/firma/modelli", tags=["firma-modelli"])

# chiavi dato disponibili da posizionare sul documento
CAMPI_DATO = {
    # --- Cliente / contraente ---
    "nome_cliente": "Cliente - Nome / Ragione sociale",
    "codice_fiscale": "Cliente - Codice fiscale",
    "partita_iva": "Cliente - Partita IVA",
    "indirizzo": "Cliente - Indirizzo",
    "cap": "Cliente - CAP",
    "comune": "Cliente - Comune",
    "provincia": "Cliente - Provincia",
    "email": "Cliente - Email",
    "telefono": "Cliente - Telefono/Cellulare",
    "data_nascita": "Cliente - Data di nascita",
    "luogo_nascita": "Cliente - Luogo di nascita",
    # --- Polizza ---
    "numero_polizza": "Polizza - Numero",
    "compagnia": "Polizza - Compagnia",
    # --- Collaboratore (intermediario) ---
    "collab_nome": "Collaboratore - Nome",
    "collab_codice_fiscale": "Collaboratore - Codice fiscale",
    "collab_email": "Collaboratore - Email",
    "collab_rui": "Collaboratore - Numero RUI",
    "collab_rui_sezione": "Collaboratore - Sezione RUI",
    # --- Agenzia ---
    "agenzia_nome": "Agenzia - Ragione sociale",
    "agenzia_piva": "Agenzia - Partita IVA",
    "agenzia_rui": "Agenzia - Numero RUI",
    "agenzia_rui_sezione": "Agenzia - Sezione RUI",
    # --- Varie ---
    "data_oggi": "Data odierna",
    "x": "Sbarra casella (scrive una X)",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tenant(user: dict) -> str | None:
    return user.get("agenzia_tenant_id")


def _word_to_pdf(raw: bytes, filename: str) -> bytes | None:
    """Converte .docx/.doc in PDF usando LibreOffice headless. None se non disponibile."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    ext = ".docx" if filename.endswith(".docx") else ".doc"
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, f"in{ext}")
        with open(src, "wb") as f:
            f.write(raw)
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, src],
                check=True, capture_output=True, timeout=90,
                env={**os.environ, "HOME": tmp},
            )
        except Exception as e:
            logger.warning("Conversione Word fallita: %s", e)
            return None
        out = os.path.join(tmp, "in.pdf")
        if not os.path.exists(out):
            return None
        with open(out, "rb") as f:
            return f.read()


def _render_pages(pdf_bytes: bytes, dpi: int = 110) -> tuple[list[dict], list[str]]:
    """Ritorna (pages_meta, images_b64). pages_meta: [{w,h}] in punti PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_meta, images = [], []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for p in doc:
        rect = p.rect
        pages_meta.append({"w": round(rect.width, 2), "h": round(rect.height, 2)})
        pix = p.get_pixmap(matrix=mat, alpha=False)
        images.append("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode())
    doc.close()
    return pages_meta, images


@router.get("")
async def lista_modelli(user=Depends(require_user("admin", "collaboratore"))):
    from server import db
    flt = {"agenzia_tenant_id": _tenant(user)}
    docs = await db.firma_modelli.find(flt, {"_id": 0, "pages": 0}).sort("nome", 1).to_list(200)
    return docs


@router.post("", status_code=201)
async def carica_modello(
    file: UploadFile = File(...),
    nome: str = Form(...),
    user=Depends(require_user("admin", "collaboratore")),
):
    from server import db
    raw = await file.read()
    fn = (file.filename or "").lower()
    if fn.endswith(".pdf"):
        pdf_bytes = raw
    elif fn.endswith(".docx") or fn.endswith(".doc"):
        pdf_bytes = _word_to_pdf(raw, fn)
        if pdf_bytes is None:
            raise HTTPException(
                400, "Conversione Word non disponibile su questo server. "
                     "Da Word usa 'Salva come' → PDF e ricarica.")
    else:
        raise HTTPException(400, "Formato non supportato: carica un PDF o un Word (.docx).")

    try:
        pages_meta, _ = _render_pages(pdf_bytes)
    except Exception as e:
        raise HTTPException(400, f"PDF non valido: {e}")

    mid = str(uuid.uuid4())
    path = f"{os.environ.get('APP_NAME', 'assicura')}/firma_modelli/{mid}.pdf"
    obj_storage.put_object(path, pdf_bytes, "application/pdf")
    doc = {
        "id": mid, "agenzia_tenant_id": _tenant(user), "nome": nome,
        "storage_path": path, "pages": pages_meta, "campi": [],
        "created_at": _now(), "updated_at": _now(), "autore_id": user.get("id"),
    }
    await db.firma_modelli.insert_one(doc)
    return {"id": mid, "nome": nome, "num_pagine": len(pages_meta)}


@router.get("/campi-disponibili")
async def campi_disponibili(user=Depends(require_user("admin", "collaboratore"))):
    return [{"chiave": k, "label": v} for k, v in CAMPI_DATO.items()]


@router.get("/{mid}")
async def dettaglio_modello(mid: str, user=Depends(require_user("admin", "collaboratore"))):
    from server import db
    doc = await db.firma_modelli.find_one(
        {"id": mid, "agenzia_tenant_id": _tenant(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Modello non trovato")
    pdf_bytes, _ = obj_storage.get_object(doc["storage_path"])
    pages_meta, images = _render_pages(pdf_bytes)
    doc["pages"] = pages_meta
    doc["immagini"] = images
    return doc


@router.put("/{mid}")
async def salva_campi(mid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    from server import db
    doc = await db.firma_modelli.find_one(
        {"id": mid, "agenzia_tenant_id": _tenant(user)}, {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(404, "Modello non trovato")
    campi = body.get("campi") or []
    norm = []
    for c in campi:
        tipo = c.get("tipo")
        if tipo not in ("dato", "firma", "libero"):
            continue
        if tipo == "dato" and c.get("chiave") not in CAMPI_DATO:
            continue
        if tipo == "libero" and not (c.get("valore") or "").strip():
            continue
        norm.append({
            "id": c.get("id") or str(uuid.uuid4()),
            "tipo": tipo,
            "chiave": c.get("chiave") if tipo == "dato" else None,
            "valore": (c.get("valore") or "").strip() if tipo == "libero" else None,
            "page": int(c.get("page") or 0),
            "x": float(c.get("x") or 0), "y": float(c.get("y") or 0),
            "w": float(c.get("w") or 0.2), "h": float(c.get("h") or 0.04),
            "font_size": int(c.get("font_size") or 11),
        })
    upd = {"campi": norm, "updated_at": _now()}
    if body.get("nome"):
        upd["nome"] = body["nome"]
    await db.firma_modelli.update_one({"id": mid}, {"$set": upd})
    return {"ok": True, "campi": len(norm)}


@router.delete("/{mid}")
async def elimina_modello(mid: str, user=Depends(require_user("admin", "collaboratore"))):
    from server import db
    doc = await db.firma_modelli.find_one(
        {"id": mid, "agenzia_tenant_id": _tenant(user)}, {"_id": 0, "storage_path": 1})
    if not doc:
        raise HTTPException(404, "Modello non trovato")
    try:
        obj_storage.delete_object(doc["storage_path"])
    except Exception:
        pass
    await db.firma_modelli.delete_one({"id": mid})
    return {"ok": True}


async def _valori_dato(db, anagrafica_id, polizza_id, collaboratore_id=None, user=None):
    ana = await db.anagrafiche.find_one({"id": anagrafica_id}, {"_id": 0}) if anagrafica_id else {}
    pol = await db.polizze.find_one({"id": polizza_id}, {"_id": 0}) if polizza_id else {}
    ana = ana or {}
    pol = pol or {}
    comp_nome = ""
    if pol.get("compagnia_id"):
        c = await db.compagnie.find_one({"id": pol["compagnia_id"]}, {"_id": 0, "ragione_sociale": 1})
        comp_nome = (c or {}).get("ragione_sociale") or ""
    # collaboratore: body → polizza → utente corrente (se collaboratore)
    cid = collaboratore_id or pol.get("collaboratore_id")
    if not cid and user and user.get("role") == "collaboratore":
        cid = user.get("id")
    collab = await db.users.find_one({"id": cid}, {"_id": 0}) if cid else {}
    collab = collab or {}
    # agenzia (singleton config)
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    from datetime import date
    nome_cliente = ana.get("ragione_sociale") or f"{ana.get('cognome','')} {ana.get('nome','')}".strip()
    indirizzo = ana.get("indirizzo") or ""
    comune = ana.get("comune") or ana.get("citta") or ""
    cap = ana.get("cap") or ""
    provincia = ana.get("provincia") or ""
    codice_fiscale = ana.get("codice_fiscale") or ""
    partita_iva = ana.get("partita_iva") or ""
    email = ana.get("email") or ""
    telefono = ana.get("cellulare") or ana.get("telefono") or ""
    data_nascita = ana.get("data_nascita") or ""
    luogo_nascita = ana.get("comune_nascita") or ana.get("luogo_nascita") or ""
    collab_nome = collab.get("name") or collab.get("nome") or collab.get("collaboratore_nome") or ""
    collab_cf = collab.get("codice_fiscale") or ""
    collab_email = collab.get("email") or ""
    collab_rui = collab.get("rui") or collab.get("rui_numero_iscrizione") or az.get("rui") or ""
    collab_rui_sez = collab.get("rui_sezione") or az.get("rui_sezione") or ""
    return {
        # --- Vocabolario Firma Moduli (CAMPI_DATO) ---
        "nome_cliente": nome_cliente,
        "codice_fiscale": codice_fiscale,
        "partita_iva": partita_iva,
        "indirizzo": indirizzo,
        "cap": cap,
        "comune": comune,
        "provincia": provincia,
        "email": email,
        "telefono": telefono,
        "data_nascita": data_nascita,
        "luogo_nascita": luogo_nascita,
        "numero_polizza": pol.get("numero_polizza") or "",
        "compagnia": comp_nome,
        "collab_nome": collab_nome,
        "collab_codice_fiscale": collab_cf,
        "collab_email": collab_email,
        "collab_rui": collab_rui,
        "collab_rui_sezione": collab_rui_sez,
        "agenzia_nome": az.get("ragione_sociale") or "",
        "agenzia_piva": az.get("partita_iva") or "",
        "agenzia_rui": az.get("rui") or "",
        "agenzia_rui_sezione": az.get("rui_sezione") or "",
        "data_oggi": date.today().strftime("%d/%m/%Y"),
        "x": "X",
        # --- Alias vocabolario "Modelli" (cliente_* / operatore_*) ---
        "cliente": nome_cliente, "cliente_nome": nome_cliente,
        "cliente_cognome": ana.get("cognome") or "",
        "cliente_ragione_sociale": ana.get("ragione_sociale") or nome_cliente,
        "cliente_via": indirizzo, "cliente_indirizzo": indirizzo,
        "cliente_comune": comune, "cliente_citta": comune,
        "cliente_cap": cap, "cliente_provincia": provincia,
        "cliente_cf": codice_fiscale, "cliente_codice_fiscale": codice_fiscale,
        "cliente_partita_iva": partita_iva,
        "cliente_email": email, "cliente_pec": ana.get("pec") or "",
        "cliente_telefono": telefono, "cliente_cellulare": telefono,
        "cliente_data_nascita": data_nascita, "cliente_luogo_nascita": luogo_nascita,
        # Operatore / intermediario (= collaboratore)
        "operatore_nome": collab_nome,
        "operatore_codice_fiscale": collab_cf,
        "operatore_email": collab_email,
        "operatore_rui": collab_rui,
        "operatore_sezione": collab_rui_sez, "operatore_rui_sezione": collab_rui_sez,
    }


def _compila_pdf(pdf_bytes: bytes, valori: dict) -> tuple[bytes, list[dict], list[dict]]:
    """Sostituisce i segnaposto {chiave} nel PDF con i valori reali (ricerca testo).
    Ritorna (pdf_compilato, firma_fields, data_fields) dove firma_fields/data_fields
    sono i rettangoli (in punti, page 0-based) dove compaiono {firma} e {data_firma},
    usati per i campi firma/data Yousign."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    firma_fields = []
    data_fields = []
    for page in doc:
        # campi dato: sostituzione testo in-place (redaction)
        for chiave, val in valori.items():
            token = "{" + chiave + "}"
            rects = page.search_for(token)
            for r in rects:
                fs = max(7, min(12, r.height * 0.9))
                page.add_redact_annot(r, text=str(val or ""), fontsize=fs,
                                      fontname="helv", align=0, fill=(1, 1, 1))
        # segnaposto immagine/strutturali senza valore testuale: li rimuoviamo
        # (il logo è già nell'intestazione del documento caricato).
        for tok in ("{logo}", "{firma_operatore}"):
            for r in page.search_for(tok):
                page.add_redact_annot(r, text="", fill=(1, 1, 1))
        # segnaposto data firma: rimosso e posizione salvata per Yousign
        for r in page.search_for("{data_firma}"):
            page.add_redact_annot(r, text="", fill=(1, 1, 1))
            data_fields.append({
                "page": page.number,
                "x": round(r.x0), "y": round(r.y0),
                "width": max(120, round(r.width)), "height": max(20, round(r.height * 1.4)),
            })
        # segnaposto firma: lo rimuoviamo e salviamo la posizione
        for r in page.search_for("{firma}"):
            page.add_redact_annot(r, text="", fill=(1, 1, 1))
            firma_fields.append({
                "page": page.number,
                "x": round(r.x0), "y": round(r.y0),
                "width": max(120, round(r.width)), "height": max(40, round(r.height * 2.2)),
            })
        page.apply_redactions()
    out = doc.tobytes()
    doc.close()
    return out, firma_fields, data_fields


def _stamp_campi(doc, campi, valori, pages_meta):
    """Scrive i campi dato/libero alle coordinate salvate (frazioni 0..1) e
    raccoglie i rettangoli dei campi 'firma' (in punti PDF) per Yousign."""
    firma_fields = []
    for c in campi:
        page_idx = int(c.get("page") or 0)
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        pw = page.rect.width
        ph = page.rect.height
        x = float(c.get("x") or 0) * pw
        y = float(c.get("y") or 0) * ph
        w = float(c.get("w") or 0.2) * pw
        h = float(c.get("h") or 0.04) * ph
        tipo = c.get("tipo")
        if tipo == "firma":
            firma_fields.append({
                "page": page_idx, "x": round(x), "y": round(y),
                "width": max(100, round(w)), "height": max(40, round(h)),
            })
            continue
        val = str(valori.get(c.get("chiave")) or "") if tipo == "dato" else str(c.get("valore") or "")
        if not val:
            continue
        fs = int(c.get("font_size") or 11)
        try:
            page.insert_textbox(fitz.Rect(x, y, x + w, y + h), val, fontsize=fs, fontname="helv", align=0)
        except Exception:
            page.insert_text((x, y + fs), val, fontsize=fs, fontname="helv")
    return firma_fields


async def _recapita_link(canali, valori, signing_url, nome_doc) -> dict:
    """Recapita il link di firma via WhatsApp e/o Email secondo i canali scelti."""
    out = {"wa": None, "email": None}
    if not signing_url:
        return out
    nome = valori.get("nome_cliente") or "Cliente"
    testo = (f"Gentile {nome}, per firmare il documento \"{nome_doc}\" "
             f"clicca qui: {signing_url}")
    if canali.get("wa"):
        cell = valori.get("telefono") or ""
        if cell:
            from notification_helpers import send_whatsapp_message
            out["wa"] = await send_whatsapp_message(cell, testo)
        else:
            out["wa"] = {"ok": False, "error": "Nessun cellulare in anagrafica"}
    if canali.get("email"):
        em = valori.get("email") or ""
        if em:
            from notification_helpers import send_email
            html = testo.replace(signing_url, f'<a href="{signing_url}">{signing_url}</a>')
            out["email"] = await send_email(em, f"Documento da firmare — {nome_doc}", testo, html=html)
        else:
            out["email"] = {"ok": False, "error": "Nessuna email in anagrafica"}
    return out


@router.post("/{mid}/compila")
async def compila_modello(mid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    """Compila i campi dato con i valori del cliente/polizza, salva il PDF come allegato e,
    se è presente un campo firma, crea la richiesta Yousign (sandbox) con il campo firma
    nel punto salvato. Ritorna allegato_id e (se firma) signing_url."""
    from server import db
    doc = await db.firma_modelli.find_one(
        {"id": mid, "agenzia_tenant_id": _tenant(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Modello non trovato")
    anagrafica_id = body.get("anagrafica_id")
    polizza_id = body.get("polizza_id")
    if (not anagrafica_id) and body.get("entita_tipo") and body.get("entita_id"):
        from routes.modelli import _resolve_contatti
        rc = await _resolve_contatti(body["entita_tipo"], body["entita_id"])
        anagrafica_id = rc.get("cliente_id")
        polizza_id = polizza_id or rc.get("polizza_id")
    if not anagrafica_id:
        raise HTTPException(400, "anagrafica_id richiesto")

    pdf_bytes, _ = obj_storage.get_object(doc["storage_path"])
    valori = await _valori_dato(db, anagrafica_id, polizza_id,
                                collaboratore_id=body.get("collaboratore_id"), user=user)
    campi = doc.get("campi") or []
    if campi:
        fdoc = fitz.open(stream=pdf_bytes, filetype="pdf")
        firma_fields = _stamp_campi(fdoc, campi, valori, doc.get("pages") or [])
        filled = fdoc.tobytes()
        fdoc.close()
        data_fields = []
    else:
        filled, firma_fields, data_fields = _compila_pdf(pdf_bytes, valori)

    # salva come allegato
    aid_alleg = str(uuid.uuid4())
    path = f"{os.environ.get('APP_NAME', 'assicura')}/documenti_firma/{aid_alleg}.pdf"
    res = obj_storage.put_object(path, filled, "application/pdf")
    nome_file = f"{doc['nome']} - {valori.get('nome_cliente','documento')}.pdf"
    alleg = {
        "id": aid_alleg, "entita_tipo": "polizza" if polizza_id else "anagrafica",
        "entita_id": polizza_id or anagrafica_id, "nome_file": nome_file,
        "storage_path": res["path"], "content_type": "application/pdf",
        "size": len(filled), "categoria": "documento_firma", "visibile_cliente": True,
        "descrizione": f"Generato da modello {doc['nome']}",
        "autore_id": user.get("id"), "created_at": _now(), "updated_at": _now(),
    }
    await db.allegati.insert_one(dict(alleg))

    out = {"ok": True, "allegato_id": aid_alleg, "nome_file": nome_file,
           "firma_presente": bool(firma_fields)}

    if firma_fields and body.get("invia_firma"):
        signing = await _invia_yousign(db, doc, filled, firma_fields, valori, body, data_fields=data_fields)
        out.update(signing)
        canali = body.get("canali") or {}
        if signing.get("firma", {}).get("ok") and (canali.get("wa") or canali.get("email")):
            out["recapito"] = await _recapita_link(
                canali, valori, signing["firma"].get("signing_url"), doc["nome"])
    elif body.get("invia_firma") and not firma_fields:
        out["firma"] = {"ok": False, "error": "Nessun campo firma posizionato nel documento"}
    return out


def _yousign_cfg() -> dict:
    """Config Yousign: sandbox (default) o produzione, con chiave unica condivisa.

    Env:
      YOUSIGN_ENVIRONMENT        = "sandbox" | "production"  (default sandbox)
      YOUSIGN_SANDBOX_API_KEY    = chiave ambiente di test
      YOUSIGN_PRODUCTION_API_KEY = chiave ambiente di produzione
    """
    env = (os.environ.get("YOUSIGN_ENVIRONMENT") or "sandbox").strip().lower()
    if env == "production":
        return {"env": "production",
                "api_key": (os.environ.get("YOUSIGN_PRODUCTION_API_KEY") or "").strip(),
                "base": "https://api.yousign.app/v3"}
    return {"env": "sandbox",
            "api_key": (os.environ.get("YOUSIGN_SANDBOX_API_KEY") or "").strip(),
            "base": "https://api-sandbox.yousign.app/v3"}


async def _invia_yousign(db, modello, pdf_bytes, firma_fields, valori, body, data_fields=None) -> dict:
    """Crea richiesta firma Yousign con il campo firma alle posizioni dei {firma} e,
    se presenti ``data_fields``, un campo 'mention' con la data di firma (Firmato il %date%)."""
    cfg = _yousign_cfg()
    api_key = cfg["api_key"]
    if not api_key:
        return {"firma": {"ok": False, "error": f"Firma Yousign non configurata ({cfg['env']})"}}
    base = cfg["base"]
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    email = (body.get("email_firmatario") or valori.get("email") or "").strip()
    nome = valori.get("nome_cliente") or "Cliente"
    parts = nome.split(" ", 1)
    first, last = (parts[0], parts[1] if len(parts) > 1 else "Cliente")
    auth_mode = body.get("auth_mode") or "otp_email"
    try:
        async with httpx.AsyncClient(base_url=base, headers=headers, timeout=40) as cli:
            if not email:
                r = await cli.get("/users", params={"limit": 5})
                if r.status_code == 200:
                    for u in r.json().get("data", []):
                        email = u.get("email") or (u.get("info") or {}).get("email") or ""
                        if email:
                            break
            if not email:
                return {"firma": {"ok": False, "error": "Email firmatario mancante"}}
            req = await cli.post("/signature_requests",
                                 json={"name": f"{modello['nome']} - {nome}", "delivery_mode": "none"})
            if req.is_error:
                return {"firma": {"ok": False, "error": req.text[:200]}}
            rid = req.json()["id"]
            up = await cli.post(f"/signature_requests/{rid}/documents",
                                files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
                                data={"nature": "signable_document"})
            if up.is_error:
                return {"firma": {"ok": False, "error": up.text[:200]}}
            did = up.json()["id"]
            fields = [{
                "type": "signature", "document_id": did, "page": f["page"] + 1,
                "x": f["x"], "y": f["y"],
                "width": max(85, f["width"]), "height": max(37, f["height"]),
            } for f in firma_fields]
            for f in (data_fields or []):
                fields.append({
                    "type": "mention", "document_id": did, "page": f["page"] + 1,
                    "x": f["x"], "y": f["y"],
                    "width": max(90, f["width"]), "height": max(24, f["height"]),
                    "mention": "Firmato il %date%", "name": "Data firma",
                })
            signer_body = {
                "info": {"first_name": first, "last_name": last, "email": email, "locale": "it"},
                "signature_level": "electronic_signature",
                "signature_authentication_mode": auth_mode,
                "fields": fields,
            }
            sg = await cli.post(f"/signature_requests/{rid}/signers", json=signer_body)
            if sg.is_error:
                return {"firma": {"ok": False, "error": sg.text[:300]}}
            signer_id = sg.json()["id"]
            act = await cli.post(f"/signature_requests/{rid}/activate", json={})
            if act.is_error:
                return {"firma": {"ok": False, "error": act.text[:300]}}
            link = None
            sdet = await cli.get(f"/signature_requests/{rid}/signers/{signer_id}")
            if sdet.status_code == 200:
                link = sdet.json().get("signature_link")
        return {"firma": {"ok": True, "request_id": rid, "status": act.json().get("status"),
                          "signing_url": link, "email": email}}
    except Exception as e:
        return {"firma": {"ok": False, "error": str(e)[:200]}}


@router.post("/render-pdf")
async def render_pdf(file: UploadFile = File(...),
                     user=Depends(require_user("admin", "collaboratore"))):
    """Renderizza un PDF/Word caricato al volo in immagini per posizionare la firma.
    Salva temporaneamente il PDF e ritorna storage_path da usare in /adhoc."""
    raw = await file.read()
    fn = (file.filename or "").lower()
    if fn.endswith(".pdf"):
        pdf_bytes = raw
    elif fn.endswith(".docx") or fn.endswith(".doc"):
        pdf_bytes = _word_to_pdf(raw, fn)
        if pdf_bytes is None:
            raise HTTPException(400, "Conversione Word non disponibile: carica un PDF.")
    else:
        raise HTTPException(400, "Formato non supportato: carica un PDF o Word.")
    try:
        pages, images = _render_pages(pdf_bytes)
    except Exception as e:
        raise HTTPException(400, f"PDF non valido: {e}")
    tmp_id = str(uuid.uuid4())
    path = f"{os.environ.get('APP_NAME', 'assicura')}/firma_adhoc/{tmp_id}.pdf"
    res = obj_storage.put_object(path, pdf_bytes, "application/pdf")
    return {"storage_path": res["path"], "pages": pages, "immagini": images,
            "nome": (file.filename or "documento").rsplit(".", 1)[0]}


@router.post("/adhoc")
async def firma_adhoc(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    """Invia a firma Yousign un PDF caricato (storage_path da /render-pdf) coi campi
    posizionati visivamente. Recapita il link via WhatsApp/Email secondo i canali scelti."""
    from server import db
    storage_path = body.get("storage_path")
    if not storage_path:
        raise HTTPException(400, "storage_path richiesto")
    campi = body.get("campi") or []
    anagrafica_id = body.get("anagrafica_id")
    polizza_id = body.get("polizza_id")
    if (not anagrafica_id) and body.get("entita_tipo") and body.get("entita_id"):
        from routes.modelli import _resolve_contatti
        rc = await _resolve_contatti(body["entita_tipo"], body["entita_id"])
        anagrafica_id = rc.get("cliente_id")
        polizza_id = polizza_id or rc.get("polizza_id")
    if not anagrafica_id:
        raise HTTPException(400, "Cliente non risolto per questa entità")

    pdf_bytes, _ = obj_storage.get_object(storage_path)
    valori = await _valori_dato(db, anagrafica_id, polizza_id, user=user)
    fdoc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_meta = [{"w": p.rect.width, "h": p.rect.height} for p in fdoc]
    firma_fields = _stamp_campi(fdoc, campi, valori, pages_meta)
    filled = fdoc.tobytes()
    fdoc.close()

    nome_doc = body.get("nome") or "Documento"
    aid = str(uuid.uuid4())
    path = f"{os.environ.get('APP_NAME', 'assicura')}/documenti_firma/{aid}.pdf"
    res = obj_storage.put_object(path, filled, "application/pdf")
    await db.allegati.insert_one({
        "id": aid, "entita_tipo": "polizza" if polizza_id else "anagrafica",
        "entita_id": polizza_id or anagrafica_id, "nome_file": f"{nome_doc}.pdf",
        "storage_path": res["path"], "content_type": "application/pdf",
        "size": len(filled), "categoria": "documento_firma", "visibile_cliente": True,
        "descrizione": "Documento inviato a firma (caricato)", "autore_id": user.get("id"),
        "created_at": _now(), "updated_at": _now(),
    })
    out = {"ok": True, "allegato_id": aid, "firma_presente": bool(firma_fields)}
    if not firma_fields:
        out["firma"] = {"ok": False, "error": "Nessun campo firma posizionato"}
        return out
    signing = await _invia_yousign(db, {"nome": nome_doc}, filled, firma_fields, valori, body)
    out.update(signing)
    canali = body.get("canali") or {}
    if signing.get("firma", {}).get("ok") and (canali.get("wa") or canali.get("email")):
        out["recapito"] = await _recapita_link(
            canali, valori, signing["firma"].get("signing_url"), nome_doc)
    return out

