"""Routes per la libreria "Gestioni Modelli".

Permette CRUD sui ``TemplateModello`` (testi/HTML editabili per Email,
WhatsApp, SMS e PDF). I modelli sono usati dai flussi di invio (avvisi
scadenze, sollecitazioni, lettera abbuono, ecc.) tramite il helper
``get_template_or_default``.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import TemplateModello, _now_iso
from shared import log_attivita


router = APIRouter()


_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class ModelloBody(BaseModel):
    tipo: str
    nome: str
    oggetto: Optional[str] = None
    corpo: str = ""
    sezioni: list[dict] = []
    sezioni_visibili: list[str] = []
    template_riga: Optional[str] = None
    categoria: Optional[str] = None
    default: bool = False
    attivo: bool = True
    note: Optional[str] = None
    richiede_firma: bool = False
    logo_url: Optional[str] = None


def _autodetect_placeholders(body: ModelloBody) -> list[str]:
    """Estrae i placeholder ``{nome}`` da corpo + oggetto + sezioni."""
    texts: list[str] = [body.corpo or "", body.oggetto or ""]
    for s in (body.sezioni or []):
        texts.append(str(s.get("titolo") or ""))
        texts.append(str(s.get("contenuto") or ""))
    out: list[str] = []
    seen: set[str] = set()
    for t in texts:
        for m in _PLACEHOLDER_RE.findall(t):
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


import os as _os_seed
import json as _json_seed

_MODELLI_DEFAULT_DIR = _os_seed.path.join(_os_seed.path.dirname(_os_seed.path.dirname(__file__)), "assets", "modelli_default")


async def _seed_modelli_default() -> None:
    """Importa i modelli PDF predefiniti per sezione (idempotente per nome+categoria)."""
    if not _os_seed.path.isdir(_MODELLI_DEFAULT_DIR):
        return
    for fn in sorted(_os_seed.listdir(_MODELLI_DEFAULT_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(_os_seed.path.join(_MODELLI_DEFAULT_DIR, fn), encoding="utf-8") as fh:
                spec = _json_seed.load(fh)
        except Exception:
            continue
        exists = await db.template_modelli.find_one(
            {"nome": spec["nome"], "categoria": spec.get("categoria", "default_sezione")}, {"_id": 1},
        )
        if exists:
            continue
        body = ModelloBody(
            tipo=spec.get("tipo", "pdf_altro"), nome=spec["nome"], corpo=spec.get("corpo", ""),
            sezioni_visibili=spec.get("sezioni_visibili", []), categoria=spec.get("categoria", "default_sezione"),
            default=spec.get("default", False),
        )
        doc = TemplateModello(
            tipo=body.tipo, nome=body.nome, corpo=body.corpo, sezioni=body.sezioni,
            sezioni_visibili=body.sezioni_visibili, categoria=body.categoria, default=body.default,
            placeholders=_autodetect_placeholders(body),
        ).model_dump()
        await db.template_modelli.insert_one(doc)


@router.get("/librerie/modelli")
async def list_modelli(
    tipo: Optional[str] = None,
    categoria: Optional[str] = None,
    sezione: Optional[str] = None,
    user: dict = Depends(current_user),
) -> list[dict]:
    await _seed_modelli_default()
    flt: dict = {}
    if tipo:
        flt["tipo"] = tipo
    if categoria:
        flt["categoria"] = categoria
    if sezione:
        flt["sezioni_visibili"] = sezione
    items = await db.template_modelli.find(flt, {"_id": 0}).sort([
        ("tipo", 1), ("nome", 1),
    ]).to_list(500)
    return items


@router.get("/librerie/modelli/{mid}")
async def get_modello(mid: str, user: dict = Depends(current_user)) -> dict:
    m = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Modello non trovato")
    return m


@router.post("/librerie/modelli", status_code=201)
async def create_modello(
    body: ModelloBody,
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    placeholders = _autodetect_placeholders(body)
    doc = TemplateModello(
        tipo=body.tipo,                 # type: ignore[arg-type]
        nome=body.nome.strip(),
        oggetto=body.oggetto,
        corpo=body.corpo,
        sezioni=body.sezioni,
        sezioni_visibili=body.sezioni_visibili,
        categoria=body.categoria,
        default=body.default,
        attivo=body.attivo,
        note=body.note,
        richiede_firma=body.richiede_firma,
        logo_url=body.logo_url,
        placeholders=placeholders,
    ).model_dump()
    # Se default=True, sbianca altri default dello stesso tipo
    if body.default:
        await db.template_modelli.update_many(
            {"tipo": body.tipo, "default": True},
            {"$set": {"default": False}},
        )
    await db.template_modelli.insert_one(doc)
    doc.pop("_id", None)
    await log_attivita(user, "create", "modello", doc["id"], doc["nome"])
    return doc


_PLACEHOLDER_DISPONIBILI = [
    "azienda_nome", "azienda_indirizzo", "azienda_telefono", "azienda_email", "data_oggi",
    "numero_polizza", "ramo", "prodotto", "stato_polizza", "scadenza", "data_scadenza",
    "effetto", "data_effetto", "premio", "premio_lordo", "importo", "compagnia", "compagnia_nome",
    "cliente", "cliente_nome", "cliente_cognome", "cliente_indirizzo", "cliente_comune",
    "cliente_cap", "cliente_provincia", "cliente_cf", "cliente_codice_fiscale",
    "cliente_partita_iva", "cliente_email", "cliente_telefono", "cliente_cellulare",
    "cliente_data_nascita", "cliente_luogo_nascita", "cliente_professione", "cliente_iban",
    "numero_sinistro", "data_sinistro", "descrizione_sinistro", "stato_sinistro", "data_denuncia",
    # Collaboratore/operatore selezionato in fase di generazione
    "operatore_nome", "operatore_email", "operatore_telefono", "operatore_rui", "operatore_sezione",
    "agenzia_rui", "azienda_iban", "azienda_pec",
    # Immagini e firma (gestite come elementi grafici, non testo)
    "logo", "firma_operatore", "firma",
]


def _estrai_testo_pdf(raw: bytes) -> str:
    """Estrae il testo da un PDF (pdfplumber)."""
    import io
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            pagine = [(pg.extract_text() or "") for pg in pdf.pages]
        return "\n\n".join(pagine).strip()
    except Exception as e:  # noqa
        raise HTTPException(400, f"Impossibile leggere il PDF: {str(e)[:150]}")


def _estrai_testo_docx(raw: bytes) -> str:
    """Estrae il testo da un file Word .docx (paragrafi + tabelle)."""
    import io
    from docx import Document
    try:
        doc = Document(io.BytesIO(raw))
    except Exception as e:  # noqa
        raise HTTPException(400, f"Impossibile leggere il Word: {str(e)[:150]}")
    parti: list[str] = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            celle = [c.text.strip() for c in row.cells if c.text.strip()]
            if celle:
                parti.append(" | ".join(celle))
    return "\n".join(x for x in parti if x is not None).strip()


async def _ai_trasforma_in_modello(testo: str, user: dict) -> str:
    """Trasforma il testo grezzo di un documento in un modello con {segnaposto}."""
    import os
    ph_list = ", ".join("{" + p + "}" for p in _PLACEHOLDER_DISPONIBILI)
    prompt = (
        "Trasforma il seguente documento in un MODELLO riutilizzabile per un CRM assicurativo italiano.\n"
        "Sostituisci i dati specifici (nome cliente, indirizzo, codice fiscale/P.IVA, numero polizza, "
        "compagnia, importi, date, contatti dell'agenzia e del collaboratore, ecc.) con i SEGNAPOSTO "
        "tra parentesi graffe SOLO da questo elenco disponibile:\n"
        f"{ph_list}\n\n"
        "Regole:\n"
        "- Usa esclusivamente i segnaposto elencati; se un dato non ha un segnaposto adatto, lascia il testo generico.\n"
        "- Dove nel documento c'è lo spazio per la FIRMA del cliente, inserisci il segnaposto {firma}.\n"
        "- Dove va la firma/timbro del collaboratore/intermediario, usa {firma_operatore}.\n"
        "- Mantieni la struttura e i paragrafi del documento (intestazioni, articoli, elenchi).\n"
        "- NON aggiungere commenti, spiegazioni o markdown: restituisci solo il testo del modello.\n"
        "- Conserva la lingua originale (italiano).\n\n"
        "DOCUMENTO:\n" + testo[:20000]
    )
    try:
        from llm_compat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"modello_doc_{user.get('id')}",
            system_message="Sei un assistente che converte documenti assicurativi in modelli con segnaposto. Rispondi solo con il testo del modello.",
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        corpo = str(resp).strip() if resp else ""
    except Exception as e:  # noqa
        raise HTTPException(502, f"Errore AI durante la trasformazione: {str(e)[:200]}")
    return corpo or testo


@router.post("/librerie/modelli/da-pdf", status_code=201)
async def crea_modello_da_pdf(
    file: UploadFile = File(...),
    tipo: str = Form("pdf_altro"),
    nome: Optional[str] = Form(None),
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Carica un PDF, ne estrae il testo con l'AI e lo trasforma in un modello
    editabile con i {segnaposto} del CRM, poi lo salva come TemplateModello."""
    if file is None:
        raise HTTPException(400, "Nessun file caricato")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "File vuoto")
    testo = _estrai_testo_pdf(raw)
    if not testo:
        raise HTTPException(422, "Il PDF non contiene testo estraibile (potrebbe essere una scansione immagine)")
    corpo = await _ai_trasforma_in_modello(testo, user)
    nome_finale = (nome or "").strip() or (file.filename or "Modello da PDF").rsplit(".", 1)[0]
    body = ModelloBody(tipo=tipo, nome=nome_finale, corpo=corpo)
    doc = TemplateModello(
        tipo=body.tipo,                 # type: ignore[arg-type]
        nome=body.nome.strip(),
        corpo=body.corpo,
        categoria="da_pdf",
        note=f"Generato da PDF: {file.filename}",
        placeholders=_autodetect_placeholders(body),
    ).model_dump()
    await db.template_modelli.insert_one(doc)
    doc.pop("_id", None)
    await log_attivita(user, "create", "modello", doc["id"], doc["nome"])
    return doc


@router.post("/librerie/modelli/da-word", status_code=201)
async def crea_modello_da_word(
    file: UploadFile = File(...),
    tipo: str = Form("word"),
    nome: Optional[str] = Form(None),
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Carica un file Word (.docx), ne estrae il testo con l'AI e lo trasforma in
    un modello editabile con i {segnaposto} del CRM."""
    if file is None:
        raise HTTPException(400, "Nessun file caricato")
    fname = (file.filename or "").lower()
    if not fname.endswith((".docx", ".doc")):
        raise HTTPException(400, "Carica un file Word (.docx)")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "File vuoto")
    testo = _estrai_testo_docx(raw)
    if not testo:
        raise HTTPException(422, "Il Word non contiene testo leggibile")
    corpo = await _ai_trasforma_in_modello(testo, user)
    nome_finale = (nome or "").strip() or (file.filename or "Modello da Word").rsplit(".", 1)[0]
    body = ModelloBody(tipo=tipo, nome=nome_finale, corpo=corpo)
    doc = TemplateModello(
        tipo=body.tipo,                 # type: ignore[arg-type]
        nome=body.nome.strip(),
        corpo=body.corpo,
        categoria="da_word",
        note=f"Generato da Word: {file.filename}",
        placeholders=_autodetect_placeholders(body),
    ).model_dump()
    await db.template_modelli.insert_one(doc)
    doc.pop("_id", None)
    await log_attivita(user, "create", "modello", doc["id"], doc["nome"])
    return doc


@router.post("/librerie/modelli/estrai-testo")
async def estrai_testo_documento(
    file: UploadFile = File(...),
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Estrae e trasforma in {segnaposto} il testo di un PDF o Word, SENZA salvare.
    Usato dai Modelli MUP per importare un documento e renderlo compilabile."""
    if file is None:
        raise HTTPException(400, "Nessun file caricato")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "File vuoto")
    fname = (file.filename or "").lower()
    if fname.endswith((".docx", ".doc")):
        testo = _estrai_testo_docx(raw)
    elif fname.endswith(".pdf"):
        testo = _estrai_testo_pdf(raw)
    else:
        raise HTTPException(400, "Formato non supportato: carica un PDF o un Word (.docx)")
    if not testo:
        raise HTTPException(422, "Nessun testo estraibile dal documento")
    corpo = await _ai_trasforma_in_modello(testo, user)
    return {"corpo": corpo, "nome": (file.filename or "Modello").rsplit(".", 1)[0]}



@router.put("/librerie/modelli/{mid}")
async def update_modello(
    mid: str,
    body: ModelloBody,
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    existing = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Modello non trovato")
    placeholders = _autodetect_placeholders(body)
    upd = body.model_dump()
    upd["placeholders"] = placeholders
    upd["updated_at"] = _now_iso()
    if body.default:
        await db.template_modelli.update_many(
            {"tipo": body.tipo, "default": True, "id": {"$ne": mid}},
            {"$set": {"default": False}},
        )
    await db.template_modelli.update_one({"id": mid}, {"$set": upd})
    await log_attivita(user, "update", "modello", mid, upd["nome"])
    out = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    return out  # type: ignore[return-value]


@router.delete("/librerie/modelli/{mid}")
async def delete_modello(
    mid: str,
    user: dict = Depends(require_user("admin")),
) -> dict:
    res = await db.template_modelli.delete_one({"id": mid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Modello non trovato")
    await log_attivita(user, "delete", "modello", mid)
    return {"ok": True}


# ============================================================
# Helper riutilizzato da altri moduli (avvisi, lettera abbuono, ecc.)
# ============================================================
async def get_default_template(tipo: str) -> Optional[dict]:
    """Ritorna il modello marcato come default per il tipo, oppure None."""
    return await db.template_modelli.find_one(
        {"tipo": tipo, "default": True, "attivo": True}, {"_id": 0},
    )


async def seed_default_models() -> None:
    """Crea modelli di esempio se la collezione è vuota (idempotente)."""
    if await db.template_modelli.count_documents({}) > 0:
        return

    defaults = [
        {
            "tipo": "email",
            "nome": "Avviso scadenza - Email",
            "oggetto": "Promemoria scadenza polizza/e — {azienda_nome}",
            "corpo": (
                "Gentile {cliente_nome},\n\n"
                "riteniamo opportuno ricordarLe la scadenza delle rate di premio "
                "relative alle coperture assicurative i cui termini risultano sotto evidenziati.\n\n"
                "Per il rinnovo e per verificare insieme che tutte le garanzie corrispondano "
                "alle Sue attuali esigenze, La aspettiamo in Agenzia.\n\n"
                "La ringraziamo per l'attenzione e Le inviamo i nostri migliori saluti.\n\n"
                "{azienda_nome}"
            ),
            "categoria": "scadenze",
            "default": True,
        },
        {
            "tipo": "whatsapp",
            "nome": "Avviso scadenza - WhatsApp",
            "corpo": (
                "Buongiorno {cliente_nome}, le ricordiamo che ha {numero_titoli} titolo/i in scadenza "
                "per un totale di {totale} €. La invitiamo a contattarci in Agenzia. "
                "Grazie, {azienda_nome}."
            ),
            "categoria": "scadenze",
            "default": True,
        },
        {
            "tipo": "sms",
            "nome": "Avviso scadenza - SMS",
            "corpo": (
                "{azienda_nome}: gentile {cliente_nome}, titoli in scadenza totale {totale} €. "
                "Contattaci per il rinnovo."
            ),
            "categoria": "scadenze",
            "default": True,
        },
        {
            "tipo": "pdf_avviso",
            "nome": "Avviso scadenza - PDF (default)",
            "oggetto": "Gentile {cliente_nome},",
            "corpo": (
                "riteniamo opportuno ricordarLe la scadenza delle rate di premio relative alle "
                "coperture assicurative i cui termini risultano sotto evidenziati.\n\n"
                "Per il rinnovo e per verificare insieme che tutte le garanzie corrispondano alle "
                "Sue attuali esigenze, La aspettiamo in Agenzia, dove continuerà a godere "
                "dell'attenzione e del servizio che dedichiamo ai nostri Clienti.\n\n"
                "La ringraziamo per l'attenzione e Le inviamo i nostri migliori saluti."
            ),
            "sezioni": [
                {
                    "ordine": 1,
                    "attiva": True,
                    "titolo": "QUANTO COSTA IN MEDIA UNA CAUSA O UNA CONTROVERSIA IN ITALIA? CIRCA 3.500 €",
                    "contenuto": (
                        "La polizza di Tutela Legale dovrebbe essere una polizza obbligatoria. "
                        "Quali garanzie ci fornisce?\n\n"
                        "• Libera scelta del proprio legale di fiducia\n"
                        "• Libera scelta di un perito di parte\n"
                        "• Controversie con compagnie di assicurazione\n"
                        "• Assicurati tutti i componenti del nucleo familiare nello stato di famiglia\n\n"
                        "E QUANTO COSTA ALL'ANNO ? 15 €"
                    ),
                },
            ],
            "categoria": "scadenze",
            "default": True,
        },
        {
            "tipo": "pdf_lettera_abbuono",
            "nome": "Lettera di Abbuono (default)",
            "corpo": (
                "Con la presente si attesta che, in occasione del pagamento del titolo "
                "n. {numero_titolo} relativo alla polizza n. {numero_polizza}, è stato "
                "concesso un abbuono di € {importo_abbuono} per i motivi sotto indicati."
            ),
            "categoria": "fiscale",
            "default": True,
        },
    ]
    for d in defaults:
        doc = TemplateModello(**d).model_dump()
        # Auto-detect placeholders
        body = ModelloBody(**{k: v for k, v in d.items() if k in ModelloBody.model_fields})
        doc["placeholders"] = _autodetect_placeholders(body)
        await db.template_modelli.insert_one(doc)


# ============================================================
# Rendering + generazione documenti (PDF / Word) + invio WhatsApp
# ============================================================
def render_text(text: str, ctx: dict) -> str:
    """Sostituisce i placeholder {nome} in modo sicuro (mancanti → lasciati)."""
    return _PLACEHOLDER_RE.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), text or "")


def _fmt_eur_doc(v) -> str:
    try:
        return f"{float(v):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "-"


def _fmt_date_doc(s) -> str:
    if not s:
        return "-"
    s = str(s)[:10]
    parts = s.split("-")
    return f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else s


async def _load_logo_bytes(az: dict) -> Optional[bytes]:
    """Carica il logo dell'agenzia come bytes.

    Prova prima da ``logo_storage_path`` (file locale), poi da ``logo_url``
    (data URL base64 o URL remoto). Ritorna None se non esiste o è illeggibile.
    """
    import base64
    import pathlib
    # 1) file locale
    p = az.get("logo_storage_path")
    if p:
        try:
            path = pathlib.Path(p)
            if path.exists() and path.is_file():
                return path.read_bytes()
        except OSError:
            pass
    # 2) URL: data:image/...;base64,XXX oppure http(s)
    url = az.get("logo_url") or ""
    if url.startswith("data:"):
        try:
            b64 = url.split(",", 1)[1]
            return base64.b64decode(b64)
        except (ValueError, IndexError):
            return None
    if url.startswith(("http://", "https://")):
        try:
            import httpx  # type: ignore
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.content
        except Exception:
            return None
    return None


async def build_context(cliente_id: Optional[str] = None,
                         polizza_id: Optional[str] = None,
                         extra: Optional[dict] = None,
                         operatore_id: Optional[str] = None) -> dict:
    """Contesto placeholder standard: azienda + cliente + polizza + operatore."""
    from datetime import date
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    ctx: dict = {
        "azienda_nome": az.get("ragione_sociale") or az.get("nome") or "",
        "azienda_indirizzo": az.get("indirizzo") or "",
        "azienda_telefono": az.get("telefono") or "",
        "azienda_email": az.get("email") or "",
        "azienda_pec": az.get("pec") or "",
        "azienda_iban": az.get("iban") or "",
        "agenzia_rui": az.get("rui") or "",
        "data_oggi": date.today().strftime("%d/%m/%Y"),
    }
    p = None
    if polizza_id:
        p = await db.polizze.find_one({"id": polizza_id}, {"_id": 0})
    if p:
        comp = await db.compagnie.find_one({"id": p.get("compagnia_id")}, {"_id": 0, "nome": 1}) or {}
        ctx.update({
            "numero_polizza": p.get("numero_polizza") or "-",
            "ramo": p.get("ramo") or "-",
            "prodotto": p.get("prodotto") or "-",
            "stato_polizza": p.get("stato") or "-",
            "scadenza": _fmt_date_doc(p.get("scadenza")),
            "data_scadenza": _fmt_date_doc(p.get("scadenza")),
            "effetto": _fmt_date_doc(p.get("effetto")),
            "data_effetto": _fmt_date_doc(p.get("effetto")),
            "premio": _fmt_eur_doc(p.get("premio_lordo")),
            "premio_lordo": _fmt_eur_doc(p.get("premio_lordo")),
            "importo": _fmt_eur_doc(p.get("premio_lordo")),
            "compagnia": comp.get("nome") or "-",
            "compagnia_nome": comp.get("nome") or "-",
        })
        cliente_id = cliente_id or p.get("contraente_id")
    if cliente_id:
        a = await db.anagrafiche.find_one({"id": cliente_id}, {"_id": 0})
        if a:
            nome = a.get("ragione_sociale") or f"{a.get('nome') or ''} {a.get('cognome') or ''}".strip()
            indirizzo = ", ".join(x for x in [a.get("indirizzo"), a.get("cap"), a.get("citta")] if x)
            ctx.update({
                "cliente": nome, "cliente_nome": nome,
                "cliente_cognome": a.get("cognome") or "",
                "cliente_indirizzo": indirizzo,
                "cliente_comune": a.get("citta") or "-",
                "cliente_cap": a.get("cap") or "-",
                "cliente_provincia": a.get("provincia") or "-",
                "cliente_cf": a.get("codice_fiscale") or a.get("partita_iva") or "-",
                "cliente_codice_fiscale": a.get("codice_fiscale") or "-",
                "cliente_partita_iva": a.get("partita_iva") or "-",
                "cliente_email": a.get("email") or "-",
                "cliente_telefono": a.get("telefono") or "-",
                "cliente_cellulare": a.get("cellulare") or a.get("telefono") or "-",
                "cliente_data_nascita": _fmt_date_doc(a.get("data_nascita")),
                "cliente_luogo_nascita": a.get("luogo_nascita") or "-",
                "cliente_professione": a.get("professione") or a.get("attivita") or "-",
                "cliente_iban": a.get("iban") or "-",
            })
    if operatore_id:
        u = await db.users.find_one({"id": operatore_id}, {"_id": 0}) or {}
        if u:
            ctx.update({
                "operatore_nome": u.get("name") or u.get("nome") or "",
                "operatore_email": u.get("email") or "",
                "operatore_telefono": u.get("telefono") or "",
                "operatore_rui": u.get("rui") or az.get("rui") or "",
                "operatore_sezione": u.get("rui_sezione") or az.get("rui_sezione") or "",
            })
            # URL firma collaboratore (interno: usato per inserire l'immagine, non come testo)
            ctx["_firma_operatore_url"] = u.get("firma_digitale_url")
    ctx.update(extra or {})
    return ctx


async def _load_image_from_url(url: Optional[str]) -> Optional[bytes]:
    """Carica i bytes di un'immagine da un URL interno /api/storage/... , data URL o http(s)."""
    if not url:
        return None
    import base64
    if url.startswith("/api/storage/"):
        path = url[len("/api/storage/"):]
        try:
            import storage as obj_storage
            data, _ = obj_storage.get_object(path)
            return data
        except Exception:
            return None
    if url.startswith("data:"):
        try:
            return base64.b64decode(url.split(",", 1)[1])
        except (ValueError, IndexError):
            return None
    if url.startswith(("http://", "https://")):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.content
        except Exception:
            return None
    return None


class GeneraDocBody(BaseModel):
    cliente_id: Optional[str] = None
    polizza_id: Optional[str] = None
    operatore_id: Optional[str] = None
    extra: dict = {}
    formato: str = "pdf"  # pdf | docx
    invia_firma: bool = False               # invia a firma digitale Yousign
    email_firmatario: Optional[str] = None  # email del firmatario (override cliente)
    auth_mode: Optional[str] = None         # otp_email | otp_sms | no_otp


class PreviewBody(BaseModel):
    tipo: str = "email"
    oggetto: Optional[str] = None
    corpo: str = ""
    sezioni: list[dict] = []
    template_riga: Optional[str] = None
    cliente_id: Optional[str] = None
    polizza_id: Optional[str] = None
    extra: dict = {}


@router.post("/librerie/modelli/preview")
async def preview_modello(body: PreviewBody, user: dict = Depends(current_user)) -> dict:
    """Rende un modello con placeholder → testo compilato (senza salvare).

    Usato dall'editor "Gestioni Modelli" per l'anteprima live durante la
    modifica del template. Se ``cliente_id``/``polizza_id`` non sono forniti,
    usa dati di esempio così l'utente vede come apparirà il messaggio finale.
    """
    ctx = await build_context(body.cliente_id, body.polizza_id, body.extra)
    # Se non abbiamo cliente reale, popoliamo con dati di esempio realistici
    # per rendere l'anteprima più utile durante la creazione del modello.
    if not body.cliente_id:
        ctx.setdefault("cliente_nome", "Mario Rossi")
        ctx.setdefault("cliente_cellulare", "+39 333 1234567")
        ctx.setdefault("cliente_email", "mario.rossi@example.com")
        ctx.setdefault("cliente_indirizzo", "Via Roma 12, 23100 Sondrio")
    if not body.polizza_id:
        ctx.setdefault("numero_polizza", "POL-2026-000123")
        ctx.setdefault("ramo", "RCA")
        ctx.setdefault("data_scadenza", "31/12/2026")
        ctx.setdefault("premio_lordo", "1.240,50 €")
        ctx.setdefault("compagnia_nome", "AXA Assicurazioni")
    ctx.setdefault("numero_titoli", "1")
    ctx.setdefault("totale", "1.240,50 €")
    ctx.setdefault("importo_abbuono", "50,00 €")
    ctx.setdefault("numero_titolo", "T-2026-4587")
    ctx.setdefault("targa", "AB123CD")
    # Se l'utente ha definito un template_riga custom, lo applichiamo a 3 titoli fittizi
    if body.template_riga:
        _rows_data = [
            {"numero_polizza": "184643240", "ramo": "RC Auto", "prodotto": "Active Auto",
             "targa": "AB123CD", "scadenza": "27/07/2026", "importo": "1.240,50"},
            {"numero_polizza": "1001797290", "ramo": "TUTELA_LEGALE", "prodotto": "Tutela Legale",
             "targa": "", "scadenza": "23/06/2026", "importo": "10,00"},
            {"numero_polizza": "182260076", "ramo": "RCA", "prodotto": "Active Auto Business",
             "targa": "CD456EF", "scadenza": "29/07/2026", "importo": "637,50"},
        ]
        ctx["elenco_titoli"] = "\n".join(render_text(body.template_riga, r) for r in _rows_data)
    else:
        ctx.setdefault("elenco_titoli",
            "• Polizza 184643240 (RC Auto) [AB123CD] — scad. 27/07/2026 — € 1.240,50\n"
            "• Polizza 1001797290 (TUTELA_LEGALE) — scad. 23/06/2026 — € 10,00\n"
            "• Polizza 182260076 (RCA) [CD456EF] — scad. 29/07/2026 — € 637,50")
    # Placeholder agenzia (letti dalla config)
    az_cfg = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    ctx.setdefault("azienda_iban", az_cfg.get("iban") or "IT00 X 00000 00000 000000000000")
    ctx.setdefault("azienda_telefono", az_cfg.get("telefono") or "+39 0342 000000")
    ctx.setdefault("azienda_email", az_cfg.get("email") or "info@agenzia.it")
    ctx.setdefault("azienda_indirizzo", az_cfg.get("indirizzo") or "Via Roma 1, 23100 Sondrio")

    return {
        "tipo": body.tipo,
        "oggetto": render_text(body.oggetto or "", ctx),
        "corpo": render_text(body.corpo or "", ctx),
        "sezioni": [
            {
                "titolo": render_text(str(s.get("titolo") or ""), ctx),
                "contenuto": render_text(str(s.get("contenuto") or ""), ctx),
                "attiva": s.get("attiva", True),
            }
            for s in (body.sezioni or [])
        ],
        "context_sample": {k: v for k, v in ctx.items() if k in (
            "cliente_nome", "numero_polizza", "ramo", "data_scadenza",
            "premio_lordo", "totale", "azienda_nome",
        )},
    }


@router.post("/librerie/modelli/{mid}/genera")
async def genera_documento(mid: str, body: GeneraDocBody,
                           user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Genera un documento PDF o Word dal modello, compilato coi dati reali.

    Supporta i segnaposto immagine ``{logo}`` (logo agenzia) e ``{firma_operatore}``
    (firma del collaboratore selezionato). Se il modello richiede firma e
    ``invia_firma`` è attivo, il PDF viene inviato a firma digitale Yousign nella
    posizione del segnaposto ``{firma}``.
    """
    from fastapi.responses import Response
    m = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Modello non trovato")
    ctx = await build_context(body.cliente_id, body.polizza_id, body.extra, body.operatore_id)
    titolo = render_text(m.get("oggetto") or m.get("nome") or "Documento", ctx)
    corpo = render_text(m.get("corpo") or "", ctx)
    sezioni = [
        {"titolo": render_text(str(s.get("titolo") or ""), ctx),
         "contenuto": render_text(str(s.get("contenuto") or ""), ctx)}
        for s in (m.get("sezioni") or []) if s.get("attiva", True)
    ]
    az_nome = ctx.get("azienda_nome") or ""
    fname = re.sub(r"[^a-zA-Z0-9_-]+", "_", m.get("nome") or "documento")[:50]

    # Logo: specifico del modello se impostato, altrimenti logo agenzia
    az_full = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    if m.get("logo_url"):
        logo_bytes: Optional[bytes] = await _load_logo_bytes({"logo_url": m.get("logo_url")})
    else:
        logo_bytes = await _load_logo_bytes(az_full)
    firma_op_bytes: Optional[bytes] = await _load_image_from_url(ctx.get("_firma_operatore_url"))

    richiede_firma = bool(m.get("richiede_firma")) or "{firma}" in (m.get("corpo") or "")
    fai_firma = bool(body.invia_firma and richiede_firma and body.formato != "docx")

    if body.formato == "docx":
        import io
        from docx import Document
        from docx.shared import Pt, Inches
        doc = Document()
        if logo_bytes:
            try:
                run = doc.add_paragraph().add_run()
                run.add_picture(io.BytesIO(logo_bytes), width=Inches(1.6))
            except Exception:
                pass
        if az_nome:
            h = doc.add_paragraph(az_nome)
            h.runs[0].bold = True
            h.runs[0].font.size = Pt(14)
        contatti = " · ".join(x for x in [
            ctx.get("azienda_indirizzo"), ctx.get("azienda_telefono"), ctx.get("azienda_email"),
        ] if x)
        if contatti:
            doc.add_paragraph(contatti).runs[0].font.size = Pt(9)
        doc.add_paragraph(ctx.get("data_oggi") or "")
        doc.add_heading(titolo, level=1)

        def _docx_para(testo: str):
            """Aggiunge un paragrafo gestendo i segnaposto immagine/firma."""
            t = testo.strip()
            if t == "{logo}":
                if logo_bytes:
                    try:
                        doc.add_paragraph().add_run().add_picture(io.BytesIO(logo_bytes), width=Inches(1.6))
                    except Exception:
                        pass
                return
            if t == "{firma_operatore}":
                if firma_op_bytes:
                    try:
                        doc.add_paragraph().add_run().add_picture(io.BytesIO(firma_op_bytes), width=Inches(1.8))
                    except Exception:
                        pass
                else:
                    doc.add_paragraph("_______________________________")
                return
            t = t.replace("{logo}", "").replace("{firma_operatore}", "")
            t = t.replace("{firma}", "_______________________________")
            doc.add_paragraph(t)

        for para in corpo.split("\n\n"):
            _docx_para(para)
        for s in sezioni:
            if s["titolo"]:
                doc.add_heading(s["titolo"], level=2)
            for para in s["contenuto"].split("\n\n"):
                _docx_para(para)
        buf = io.BytesIO()
        doc.save(buf)
        return Response(
            buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={fname}.docx"},
        )

    # PDF
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors as rl_colors
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=18 * mm)
    el = []
    contatti = "<br/>".join(x for x in [
        ctx.get("azienda_indirizzo"), ctx.get("azienda_telefono"), ctx.get("azienda_email"),
    ] if x)
    header_right = f"<para align='right'><b>{az_nome}</b><br/><font size='8'>{contatti}</font></para>"
    if logo_bytes:
        try:
            img = Image(io.BytesIO(logo_bytes), width=40 * mm, height=20 * mm, kind="proportional")
            head_tbl = Table([[img, Paragraph(header_right, styles["Normal"])]], colWidths=[45 * mm, 135 * mm])
            head_tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#5b21b6")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            el.append(head_tbl)
        except Exception:
            if az_nome:
                el.append(Paragraph(f"<b>{az_nome}</b>", styles["Heading2"]))
    elif az_nome:
        el.append(Paragraph(f"<b>{az_nome}</b>", styles["Heading2"]))
        if contatti:
            el.append(Paragraph(f"<font size='8'>{contatti}</font>", styles["Normal"]))
    el.append(Spacer(1, 6))
    el.append(Paragraph(ctx.get("data_oggi") or "", styles["Normal"]))
    el.append(Spacer(1, 10))
    el.append(Paragraph(f"<b>{titolo}</b>", styles["Heading1"]))
    el.append(Spacer(1, 6))

    def _pdf_para(testo: str):
        """Aggiunge flowable(s) gestendo i segnaposto immagine/firma."""
        t = testo.strip()
        if t == "{logo}":
            if logo_bytes:
                try:
                    el.append(Image(io.BytesIO(logo_bytes), width=40 * mm, height=20 * mm, kind="proportional"))
                    el.append(Spacer(1, 6))
                except Exception:
                    pass
            return
        if t == "{firma_operatore}":
            if firma_op_bytes:
                try:
                    el.append(Image(io.BytesIO(firma_op_bytes), width=45 * mm, height=20 * mm, kind="proportional"))
                    el.append(Spacer(1, 6))
                except Exception:
                    pass
            else:
                el.append(Paragraph("_______________________________", styles["Normal"]))
                el.append(Spacer(1, 6))
            return
        t = t.replace("{logo}", "").replace("{firma_operatore}", "")
        if fai_firma:
            # mantiene il marcatore {firma} nel PDF per il posizionamento Yousign
            t_html = t.replace("\n", "<br/>")
        else:
            t_html = t.replace("{firma}", "_______________________________").replace("\n", "<br/>")
        el.append(Paragraph(t_html, styles["Normal"]))
        el.append(Spacer(1, 6))

    for para in corpo.split("\n\n"):
        _pdf_para(para)
    for s in sezioni:
        if s["titolo"]:
            el.append(Spacer(1, 8))
            el.append(Paragraph(f"<b>{s['titolo']}</b>", styles["Heading3"]))
        for para in s["contenuto"].split("\n\n"):
            _pdf_para(para)
    pdf.build(el)
    pdf_bytes = buf.getvalue()

    # Invio a firma digitale Yousign (posizione del segnaposto {firma})
    if fai_firma:
        import uuid as _uuid
        import os as _os
        import fitz  # pymupdf
        import storage as obj_storage
        from routes.firma_modelli import _invia_yousign
        doc_f = fitz.open(stream=pdf_bytes, filetype="pdf")
        firma_fields = []
        for page in doc_f:
            for r in page.search_for("{firma}"):
                page.add_redact_annot(r, text="", fill=(1, 1, 1))
                firma_fields.append({
                    "page": page.number, "x": round(r.x0), "y": round(r.y0),
                    "width": max(120, round(r.width)), "height": max(40, round(r.height * 2.2)),
                })
            page.apply_redactions()
        pdf_bytes = doc_f.tobytes()
        doc_f.close()
        if not firma_fields:
            raise HTTPException(422, "Nessun segnaposto {firma} trovato nel documento")
        cliente_email = ctx.get("cliente_email") if ctx.get("cliente_email") not in (None, "-", "") else ""
        valori = {"nome_cliente": ctx.get("cliente_nome") or "Cliente", "email": cliente_email}
        body_y = {"email_firmatario": body.email_firmatario,
                  "auth_mode": body.auth_mode or "otp_email", "invia_firma": True}
        signing = await _invia_yousign(db, {"nome": m.get("nome")}, pdf_bytes, firma_fields, valori, body_y)
        fr = (signing or {}).get("firma") or {}
        if not fr.get("ok"):
            raise HTTPException(400, f"Invio a firma non riuscito: {fr.get('error') or 'errore sconosciuto'}")
        # salva il PDF come allegato del cliente/polizza
        aid = str(_uuid.uuid4())
        path = f"{_os.environ.get('APP_NAME', 'assicura')}/documenti_firma/{aid}.pdf"
        obj_storage.put_object(path, pdf_bytes, "application/pdf")
        nome_file = f"{m.get('nome') or 'documento'} - {valori['nome_cliente']}.pdf"
        await db.allegati.insert_one({
            "id": aid, "entita_tipo": "polizza" if body.polizza_id else "anagrafica",
            "entita_id": body.polizza_id or body.cliente_id, "nome_file": nome_file,
            "storage_path": path, "content_type": "application/pdf",
            "size": len(pdf_bytes), "categoria": "documento_firma", "visibile_cliente": True,
            "descrizione": f"Generato da modello {m.get('nome')}",
            "autore_id": user.get("id"), "created_at": _now_iso(), "updated_at": _now_iso(),
        })
        await log_attivita(user, "genera_firma", "modello", mid, nome_file)
        return {"ok": True, "allegato_id": aid, "nome_file": nome_file, "firma_presente": True,
                "signing_url": fr.get("signing_url"), "request_id": fr.get("request_id"),
                "status": fr.get("status"), "firma": fr}

    return Response(pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={fname}.pdf"})


class InviaWaModelloBody(BaseModel):
    cliente_id: Optional[str] = None
    numero: Optional[str] = None
    polizza_id: Optional[str] = None
    extra: dict = {}


@router.post("/librerie/modelli/{mid}/invia-whatsapp")
async def invia_modello_whatsapp(mid: str, body: InviaWaModelloBody,
                                 user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))) -> dict:
    """Invia il modello via WhatsApp (Evolution API) al cliente/numero indicato."""
    import uuid as _uuid
    m = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Modello non trovato")
    ctx = await build_context(body.cliente_id, body.polizza_id, body.extra)
    dest = (body.numero or ctx.get("cliente_cellulare") or "").strip()
    if not dest or dest == "-":
        raise HTTPException(400, "Nessun numero: il cliente non ha cellulare in anagrafica")
    msg = render_text(m.get("corpo") or "", ctx)
    from routes.whatsapp_evo import send_text_via_evolution
    r = await send_text_via_evolution(dest, msg)
    await db.storico_avvisi.insert_one({
        "id": str(_uuid.uuid4()), "canale": "whatsapp",
        "contraente_id": body.cliente_id, "contraente_nome": ctx.get("cliente_nome"),
        "polizza_id": body.polizza_id, "destinatario": dest, "target": dest,
        "oggetto": m.get("nome"), "soggetto": m.get("nome"), "messaggio": msg,
        "tipo": "modello_whatsapp",
        "esito": "inviato" if r.get("ok") else f"errore: {r.get('error')}",
        "sent_at": _now_iso(), "operatore_id": user.get("id"),
        "operatore_nome": user.get("name") or user.get("email"),
    })
    if not r.get("ok"):
        raise HTTPException(400, f"Invio WhatsApp fallito: {r.get('error')}")
    await log_attivita(user, "whatsapp_modello", "modello", mid, f"→ {dest}")
    return {"ok": True, "instance": r.get("instance_name"), "anteprima": msg[:200]}


# =====================================================================
# Comunicazioni unificate (Email / WhatsApp) da anagrafica/polizza/titolo/sinistro
# =====================================================================

async def _resolve_contatti(entita_tipo: str, entita_id: str) -> dict:
    """Risolve cliente_id + polizza_id + contatti per anagrafica/polizza/titolo/sinistro."""
    cliente_id = None
    polizza_id = None
    et = (entita_tipo or "").lower()
    if et in ("anagrafica", "cliente"):
        cliente_id = entita_id
    elif et == "polizza":
        polizza_id = entita_id
        p = await db.polizze.find_one({"id": entita_id}, {"_id": 0, "contraente_id": 1})
        cliente_id = (p or {}).get("contraente_id")
    elif et == "titolo":
        t = await db.titoli.find_one({"id": entita_id}, {"_id": 0, "polizza_id": 1})
        polizza_id = (t or {}).get("polizza_id")
        if polizza_id:
            p = await db.polizze.find_one({"id": polizza_id}, {"_id": 0, "contraente_id": 1})
            cliente_id = (p or {}).get("contraente_id")
    elif et == "sinistro":
        s = await db.sinistri.find_one(
            {"id": entita_id}, {"_id": 0, "polizza_id": 1, "contraente_id": 1})
        polizza_id = (s or {}).get("polizza_id")
        cliente_id = (s or {}).get("contraente_id")
        if not cliente_id and polizza_id:
            p = await db.polizze.find_one({"id": polizza_id}, {"_id": 0, "contraente_id": 1})
            cliente_id = (p or {}).get("contraente_id")
    email = cellulare = nome = ""
    if cliente_id:
        a = await db.anagrafiche.find_one({"id": cliente_id}, {"_id": 0}) or {}
        email = a.get("email") or ""
        cellulare = a.get("cellulare") or a.get("telefono") or ""
        nome = a.get("ragione_sociale") or f"{a.get('nome') or ''} {a.get('cognome') or ''}".strip()
    return {"cliente_id": cliente_id, "polizza_id": polizza_id,
            "email": email, "cellulare": cellulare, "cliente_nome": nome}


class ComunicaRenderBody(BaseModel):
    entita_tipo: str
    entita_id: str
    modello_id: Optional[str] = None


@router.post("/librerie/comunica/contesto")
async def comunica_contesto(body: ComunicaRenderBody, user: dict = Depends(current_user)) -> dict:
    """Ritorna contatti (email/cellulare/nome) e id risolti per l'entità."""
    return await _resolve_contatti(body.entita_tipo, body.entita_id)


@router.post("/librerie/comunica/render")
async def comunica_render(body: ComunicaRenderBody, user: dict = Depends(current_user)) -> dict:
    """Compila un modello (oggetto+corpo) coi dati reali dell'entità."""
    c = await _resolve_contatti(body.entita_tipo, body.entita_id)
    out = {**c, "oggetto": "", "corpo": ""}
    if body.modello_id:
        m = await db.template_modelli.find_one({"id": body.modello_id}, {"_id": 0})
        if not m:
            raise HTTPException(404, "Modello non trovato")
        ctx = await build_context(c.get("cliente_id"), c.get("polizza_id"),
                                  operatore_id=user.get("id"))
        out["oggetto"] = render_text(m.get("oggetto") or m.get("nome") or "", ctx)
        out["corpo"] = render_text(m.get("corpo") or "", ctx)
    return out


class ComunicaInviaBody(BaseModel):
    entita_tipo: str
    entita_id: str
    canale: str  # "email" | "whatsapp"
    destinatario: Optional[str] = None
    oggetto: Optional[str] = None
    corpo: str = ""


@router.post("/librerie/comunica/invia")
async def comunica_invia(body: ComunicaInviaBody, user: dict = Depends(current_user)) -> dict:
    """Invia realmente Email o WhatsApp al cliente usando i canali configurati."""
    import uuid as _uuid
    c = await _resolve_contatti(body.entita_tipo, body.entita_id)
    canale = (body.canale or "").lower()
    if not (body.corpo or "").strip():
        raise HTTPException(400, "Il messaggio è vuoto")

    if canale == "email":
        dest = (body.destinatario or c.get("email") or "").strip()
        if not dest or dest == "-":
            raise HTTPException(400, "Nessuna email del destinatario")
        from notification_helpers import send_email
        html = body.corpo if "<" in body.corpo else body.corpo.replace("\n", "<br>")
        r = await send_email(dest, body.oggetto or "Comunicazione", body.corpo, html=html)
    elif canale == "whatsapp":
        dest = (body.destinatario or c.get("cellulare") or "").strip()
        if not dest or dest == "-":
            raise HTTPException(400, "Nessun cellulare del destinatario")
        from notification_helpers import send_whatsapp_message
        r = await send_whatsapp_message(dest, body.corpo)
    else:
        raise HTTPException(400, "Canale non supportato")

    await db.storico_avvisi.insert_one({
        "id": str(_uuid.uuid4()), "canale": canale,
        "contraente_id": c.get("cliente_id"), "contraente_nome": c.get("cliente_nome"),
        "polizza_id": c.get("polizza_id"), "destinatario": dest, "target": dest,
        "oggetto": body.oggetto, "soggetto": body.oggetto,
        "messaggio": body.corpo[:4000], "tipo": f"comunica_{canale}",
        "esito": "inviato" if r.get("ok") else f"errore: {r.get('error')}",
        "sent_at": _now_iso(), "operatore_id": user.get("id"),
        "operatore_nome": user.get("name") or user.get("email"),
    })
    if not r.get("ok"):
        raise HTTPException(400, r.get("error") or f"Invio {canale} fallito")
    await log_attivita(user, f"comunica_{canale}", body.entita_tipo, body.entita_id, dest)
    return {"ok": True, "canale": canale, "destinatario": dest}
