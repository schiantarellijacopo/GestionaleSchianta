"""Routes per la libreria "Gestioni Modelli".

Permette CRUD sui ``TemplateModello`` (testi/HTML editabili per Email,
WhatsApp, SMS e PDF). I modelli sono usati dai flussi di invio (avvisi
scadenze, sollecitazioni, lettera abbuono, ecc.) tramite il helper
``get_template_or_default``.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
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
    categoria: Optional[str] = None
    default: bool = False
    attivo: bool = True
    note: Optional[str] = None


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


@router.get("/librerie/modelli")
async def list_modelli(
    tipo: Optional[str] = None,
    categoria: Optional[str] = None,
    user: dict = Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if tipo:
        flt["tipo"] = tipo
    if categoria:
        flt["categoria"] = categoria
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
        categoria=body.categoria,
        default=body.default,
        attivo=body.attivo,
        note=body.note,
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
                         extra: Optional[dict] = None) -> dict:
    """Contesto placeholder standard: azienda + cliente + polizza."""
    from datetime import date
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    ctx: dict = {
        "azienda_nome": az.get("ragione_sociale") or az.get("nome") or "",
        "azienda_indirizzo": az.get("indirizzo") or "",
        "azienda_telefono": az.get("telefono") or "",
        "azienda_email": az.get("email") or "",
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
    ctx.update(extra or {})
    return ctx


class GeneraDocBody(BaseModel):
    cliente_id: Optional[str] = None
    polizza_id: Optional[str] = None
    extra: dict = {}
    formato: str = "pdf"  # pdf | docx


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
    """Genera un documento PDF o Word dal modello, compilato coi dati reali."""
    from fastapi.responses import Response
    m = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Modello non trovato")
    ctx = await build_context(body.cliente_id, body.polizza_id, body.extra)
    titolo = render_text(m.get("oggetto") or m.get("nome") or "Documento", ctx)
    corpo = render_text(m.get("corpo") or "", ctx)
    sezioni = [
        {"titolo": render_text(str(s.get("titolo") or ""), ctx),
         "contenuto": render_text(str(s.get("contenuto") or ""), ctx)}
        for s in (m.get("sezioni") or []) if s.get("attiva", True)
    ]
    az_nome = ctx.get("azienda_nome") or ""
    fname = re.sub(r"[^a-zA-Z0-9_-]+", "_", m.get("nome") or "documento")[:50]

    # Logo agenzia (Librerie → Azienda → logo_url o logo_storage_path)
    az_full = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    logo_bytes: Optional[bytes] = await _load_logo_bytes(az_full)

    if body.formato == "docx":
        import io
        from docx import Document
        from docx.shared import Pt, Inches
        doc = Document()
        if logo_bytes:
            try:
                header_p = doc.add_paragraph()
                run = header_p.add_run()
                run.add_picture(io.BytesIO(logo_bytes), width=Inches(1.6))
            except Exception:
                pass  # logo corrotto → skip senza rompere il documento
        if az_nome:
            h = doc.add_paragraph(az_nome)
            h.runs[0].bold = True
            h.runs[0].font.size = Pt(14)
        # Contatti agenzia (piccoli, dopo la ragione sociale)
        contatti = " · ".join(x for x in [
            ctx.get("azienda_indirizzo"), ctx.get("azienda_telefono"), ctx.get("azienda_email"),
        ] if x)
        if contatti:
            p_c = doc.add_paragraph(contatti)
            p_c.runs[0].font.size = Pt(9)
        doc.add_paragraph(ctx.get("data_oggi") or "")
        doc.add_heading(titolo, level=1)
        for para in corpo.split("\n\n"):
            doc.add_paragraph(para)
        for s in sezioni:
            if s["titolo"]:
                doc.add_heading(s["titolo"], level=2)
            for para in s["contenuto"].split("\n\n"):
                doc.add_paragraph(para)
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
    # Intestazione: logo (sinistra) + ragione sociale + contatti (destra)
    contatti = "<br/>".join(x for x in [
        ctx.get("azienda_indirizzo"), ctx.get("azienda_telefono"), ctx.get("azienda_email"),
    ] if x)
    header_right = f"<para align='right'><b>{az_nome}</b><br/><font size='8'>{contatti}</font></para>"
    if logo_bytes:
        try:
            img = Image(io.BytesIO(logo_bytes), width=40 * mm, height=20 * mm, kind="proportional")
            head_tbl = Table(
                [[img, Paragraph(header_right, styles["Normal"])]],
                colWidths=[45 * mm, 135 * mm],
            )
            head_tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#5b21b6")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            el.append(head_tbl)
        except Exception:
            if az_nome:
                el.append(Paragraph(f"<b>{az_nome}</b>", styles["Heading2"]))
    else:
        if az_nome:
            el.append(Paragraph(f"<b>{az_nome}</b>", styles["Heading2"]))
            if contatti:
                el.append(Paragraph(f"<font size='8'>{contatti}</font>", styles["Normal"]))
    el.append(Spacer(1, 6))
    el.append(Paragraph(ctx.get("data_oggi") or "", styles["Normal"]))
    el.append(Spacer(1, 10))
    el.append(Paragraph(f"<b>{titolo}</b>", styles["Heading1"]))
    el.append(Spacer(1, 6))
    for para in corpo.split("\n\n"):
        el.append(Paragraph(para.replace("\n", "<br/>"), styles["Normal"]))
        el.append(Spacer(1, 6))
    for s in sezioni:
        if s["titolo"]:
            el.append(Spacer(1, 8))
            el.append(Paragraph(f"<b>{s['titolo']}</b>", styles["Heading3"]))
        for para in s["contenuto"].split("\n\n"):
            el.append(Paragraph(para.replace("\n", "<br/>"), styles["Normal"]))
            el.append(Spacer(1, 4))
    pdf.build(el)
    return Response(buf.getvalue(), media_type="application/pdf",
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
