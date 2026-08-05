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

    if body.formato == "docx":
        import io
        from docx import Document
        from docx.shared import Pt
        doc = Document()
        if az_nome:
            h = doc.add_paragraph(az_nome)
            h.runs[0].bold = True
            h.runs[0].font.size = Pt(14)
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
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    el = []
    if az_nome:
        el.append(Paragraph(f"<b>{az_nome}</b>", styles["Heading2"]))
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
