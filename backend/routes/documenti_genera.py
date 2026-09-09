"""Generazione documenti da modello (per sezione: contraente / polizza / sinistro).

Compila il ``corpo`` di un TemplateModello con i dati reali dell'entità,
produce un PDF e (opzionalmente) lo archivia tra gli allegati dell'entità.
Supporta il segnaposto speciale ``{stato_famiglia}`` per l'autocertificazione,
espanso dai familiari del cliente (campo ``parente_di``).
"""
from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database import db
from auth import current_user
from db_models import Allegato
from storage_service import StorageService

router = APIRouter(tags=["documenti-genera"])

_SEZIONE_ENTITA = {"contraente": "anagrafica", "polizza": "polizza", "sinistro": "sinistro"}


def _fmt_date(v):
    if not v:
        return ""
    s = str(v)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s


def _eur(v):
    try:
        return f"€ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "€ 0,00"


async def _logo_bytes():
    az = await db.azienda_config.find_one({}, {"_id": 0, "logo_storage_path": 1}) or {}
    if az.get("logo_storage_path"):
        try:
            import storage as _s
            data, _ = _s.get_object(az["logo_storage_path"])
            return data
        except Exception:
            return None
    return None


def _nome_completo(a: dict) -> str:
    return a.get("ragione_sociale") or f"{a.get('nome','')} {a.get('cognome','')}".strip()


async def _stato_famiglia(ana: dict) -> str:
    """Elenco numerato dei componenti del nucleo familiare dal campo parente_di."""
    rel = ana.get("parente_di") or []
    if not rel:
        return "(nessun familiare registrato nella scheda Relazione del cliente)"
    righe = []
    for i, r in enumerate(rel, start=1):
        aid = r.get("anagrafica_id")
        parente = await db.anagrafiche.find_one({"id": aid}, {"_id": 0}) if aid else None
        if not parente:
            continue
        nome = _nome_completo(parente)
        luogo = parente.get("comune_nascita") or ""
        data = _fmt_date(parente.get("data_nascita"))
        relazione = (r.get("relazione") or "").capitalize()
        pezzi = [f"{i}) {nome}"]
        if luogo or data:
            pezzi.append(f"nato/a a {luogo} il {data}".strip())
        if relazione:
            pezzi.append(f"grado di parentela: {relazione}")
        righe.append(" — ".join(pezzi))
    return "\n".join(righe) if righe else "(nessun familiare collegato)"


async def _context(entita_tipo: str, entita_id: str) -> dict:
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    ana = pol = comp = sin = None
    if entita_tipo == "contraente":
        ana = await db.anagrafiche.find_one({"id": entita_id}, {"_id": 0})
        if not ana:
            raise HTTPException(404, "Anagrafica non trovata")
    elif entita_tipo == "polizza":
        pol = await db.polizze.find_one({"id": entita_id}, {"_id": 0})
        if not pol:
            raise HTTPException(404, "Polizza non trovata")
        ana = await db.anagrafiche.find_one({"id": pol.get("contraente_id")}, {"_id": 0}) or {}
        comp = await db.compagnie.find_one({"id": pol.get("compagnia_id")}, {"_id": 0}) or {}
    elif entita_tipo == "sinistro":
        sin = await db.sinistri.find_one({"id": entita_id}, {"_id": 0})
        if not sin:
            raise HTTPException(404, "Sinistro non trovato")
        pol = await db.polizze.find_one({"id": sin.get("polizza_id")}, {"_id": 0}) if sin.get("polizza_id") else {}
        ana = await db.anagrafiche.find_one({"id": sin.get("contraente_id") or (pol or {}).get("contraente_id")}, {"_id": 0}) or {}
        comp = await db.compagnie.find_one({"id": sin.get("compagnia_id") or (pol or {}).get("compagnia_id")}, {"_id": 0}) or {}
    else:
        raise HTTPException(400, "Sezione non valida")

    ana = ana or {}
    pol = pol or {}
    comp = comp or {}
    sin = sin or {}
    nome_intero = _nome_completo(ana)
    ctx = {
        "cliente": nome_intero, "contraente": nome_intero,
        "cliente_nome": ana.get("nome") or ana.get("ragione_sociale") or "",
        "cliente_cognome": ana.get("cognome") or "",
        "cliente_cf": ana.get("codice_fiscale") or "", "cliente_codice_fiscale": ana.get("codice_fiscale") or "",
        "cliente_partita_iva": ana.get("partita_iva") or "",
        "cliente_professione": ana.get("professione") or "",
        "cliente_indirizzo": ana.get("indirizzo") or "", "cliente_comune": ana.get("comune") or "",
        "cliente_cap": ana.get("cap") or "", "cliente_provincia": ana.get("provincia") or "",
        "cliente_telefono": ana.get("telefono") or "", "cliente_cellulare": ana.get("cellulare") or "",
        "cliente_email": ana.get("email") or "", "cliente_iban": ana.get("iban") or "",
        "cliente_data_nascita": _fmt_date(ana.get("data_nascita")),
        "cliente_luogo_nascita": ana.get("comune_nascita") or "",
        "compagnia": comp.get("ragione_sociale") or "", "compagnia_nome": comp.get("ragione_sociale") or "",
        "numero_polizza": pol.get("numero_polizza") or "", "ramo": pol.get("ramo") or pol.get("prodotto") or "",
        "prodotto": pol.get("prodotto") or "", "stato_polizza": pol.get("stato") or "",
        "data_effetto": _fmt_date(pol.get("data_effetto") or pol.get("effetto")),
        "effetto": _fmt_date(pol.get("data_effetto") or pol.get("effetto")),
        "data_scadenza": _fmt_date(pol.get("data_scadenza") or pol.get("scadenza")),
        "scadenza": _fmt_date(pol.get("data_scadenza") or pol.get("scadenza")),
        "premio": _eur(pol.get("premio") or pol.get("premio_netto")),
        "premio_lordo": _eur(pol.get("premio_lordo") or pol.get("ultimo_premio_pagato")),
        "importo": _eur(pol.get("premio_lordo")),
        "numero_sinistro": sin.get("numero_sinistro") or sin.get("numero_interno") or "",
        "data_sinistro": _fmt_date(sin.get("data_avvenimento")),
        "data_denuncia": _fmt_date(sin.get("data_denuncia") or sin.get("data_apertura")),
        "stato_sinistro": sin.get("stato") or "", "descrizione_sinistro": sin.get("descrizione") or "",
        "azienda_nome": az.get("ragione_sociale") or "", "agenzia_nome": az.get("ragione_sociale") or "",
        "azienda_indirizzo": ", ".join([x for x in [az.get("indirizzo"), az.get("cap"), az.get("comune")] if x]),
        "data_oggi": datetime.now().strftime("%d/%m/%Y"),
    }
    if entita_tipo == "contraente":
        ctx["stato_famiglia"] = await _stato_famiglia(ana)

    # Garanzie + dati veicolo (per il Documento di polizza)
    gar = pol.get("garanzie") or []
    gar_lines = []
    for g in gar:
        if isinstance(g, dict):
            nome = g.get("nome") or g.get("descrizione") or ""
            extra = g.get("massimale") or g.get("somma_assicurata") or g.get("premio") or ""
            gar_lines.append(f"{nome}: {extra}" if extra else nome)
        elif g:
            gar_lines.append(str(g))
    ctx["garanzie"] = "\n".join(gar_lines) if gar_lines else "(nessuna garanzia specificata)"
    ramo_l = f"{pol.get('ramo') or ''} {pol.get('prodotto') or ''}".lower()
    is_auto = ("auto" in ramo_l or "rca" in ramo_l or "veicol" in ramo_l or bool(pol.get("targa")))
    ctx["targa"] = pol.get("targa") or ""
    ctx["modello"] = pol.get("modello") or pol.get("marca_modello") or pol.get("veicolo") or ""
    ctx["sezione_veicolo"] = (f"DATI VEICOLO\nTarga: {ctx['targa']}\nModello: {ctx['modello']}" if is_auto else "")
    return ctx, ana, pol, comp, sin


def _sub(text: str, ctx: dict) -> str:
    return re.sub(r"\{([a-z_]+)\}", lambda m: str(ctx.get(m.group(1), m.group(0))), text or "")


def _build_pdf(titolo: str, corpo: str, ctx: dict, logo: bytes | None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable,
    )

    navy = colors.HexColor("#0f2f4a")
    grey_line = colors.HexColor("#d7dee6")
    label_col = colors.HexColor("#334155")
    ss = getSampleStyleSheet()
    title_st = ParagraphStyle("t", parent=ss["Title"], fontSize=16, leading=20, textColor=navy, alignment=TA_LEFT, spaceAfter=2)
    body_st = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#1f2937"))
    lbl_st = ParagraphStyle("l", parent=body_st, fontName="Helvetica-Bold", textColor=label_col)
    val_st = ParagraphStyle("v", parent=body_st)
    sec_st = ParagraphStyle("s", parent=body_st, fontName="Helvetica-Bold", fontSize=10, textColor=colors.white)
    agency_st = ParagraphStyle("ag", parent=body_st, fontName="Helvetica-Bold", fontSize=11, textColor=navy)

    def esc(t):
        return str(t or "").replace("&", "&amp;").replace("<", "&lt;")

    def is_section(line):
        s = line.strip()
        if not s or ":" in s or len(s) > 48:
            return False
        letters = [c for c in s if c.isalpha()]
        return bool(letters) and s.upper() == s

    testo = _sub(corpo, ctx).replace("\r", "")
    lines = testo.split("\n")

    story = []
    # Intestazione: logo + nome agenzia
    header_left = []
    if logo:
        try:
            img = Image(BytesIO(logo))
            ratio = img.imageWidth / max(img.imageHeight, 1)
            img.drawHeight = 1.3 * cm
            img.drawWidth = 1.3 * cm * ratio
            header_left.append(img)
        except Exception:
            pass
    agency = ctx.get("azienda_nome") or ctx.get("agenzia_nome") or ""
    name_cell = Paragraph(esc(agency), agency_st)
    if header_left:
        htab = Table([[header_left[0], name_cell]], colWidths=[1.6 * cm, None])
        htab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(htab)
    elif agency:
        story.append(name_cell)
    story.append(HRFlowable(width="100%", thickness=1.2, color=navy, spaceBefore=6, spaceAfter=8))

    # Titolo (prima riga in maiuscolo)
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and is_section(lines[idx]):
        story.append(Paragraph(esc(lines[idx].strip()), title_st))
        story.append(Spacer(1, 8))
        idx += 1

    tw = A4[0] - 4 * cm  # larghezza utile
    pending = []  # buffer coppie label/value

    def flush_fields():
        nonlocal pending
        if not pending:
            return
        data = [[Paragraph(esc(l), lbl_st), Paragraph(esc(v), val_st)] for l, v in pending]
        t = Table(data, colWidths=[tw * 0.34, tw * 0.66])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, grey_line),
            ("BOX", (0, 0), (-1, -1), 0.6, grey_line),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f7fa")),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
        pending = []

    def section_bar(text):
        cell = Paragraph(esc(text), sec_st)
        t = Table([[cell]], colWidths=[tw])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), navy),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 5))

    for line in lines[idx:]:
        s = line.strip()
        if not s:
            flush_fields()
            story.append(Spacer(1, 4))
            continue
        if is_section(s):
            flush_fields()
            section_bar(s)
            continue
        # riga campo "Etichetta: valore" (anche più coppie separate da 2+ spazi)
        segs = re.split(r"\s{2,}", s)
        if len(segs) > 1 and all((":" in seg and len(seg.split(":", 1)[0]) <= 42) for seg in segs):
            for seg in segs:
                label, value = seg.split(":", 1)
                pending.append((label.strip(), value.strip()))
            continue
        if ":" in s and len(s.split(":", 1)[0]) <= 42 and not s.startswith("("):
            label, value = s.split(":", 1)
            pending.append((label.strip(), value.strip()))
            continue
        flush_fields()
        story.append(Paragraph(esc(s), body_st))
        story.append(Spacer(1, 2))
    flush_fields()

    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)
    doc.build(story)
    return out.getvalue()


@router.get("/documenti/modelli-sezione")
async def modelli_sezione(sezione: str, user=Depends(current_user)):
    """Modelli disponibili per una sezione (contraente/polizza/sinistro)."""
    if sezione not in _SEZIONE_ENTITA:
        raise HTTPException(400, "Sezione non valida")
    items = await db.template_modelli.find(
        {"sezioni_visibili": sezione, "attivo": {"$ne": False},
         "tipo": {"$in": ["pdf_altro", "pdf", "word", "documento"]}},
        {"_id": 0},
    ).sort("nome", 1).to_list(300)
    return items


@router.post("/documenti/genera")
async def genera_documento(body: dict, user=Depends(current_user)):
    """Genera un PDF da un modello per un'entità. Se salva=true archivia negli allegati."""
    entita_tipo = body.get("entita_tipo")
    entita_id = body.get("entita_id")
    template_id = body.get("template_id")
    if entita_tipo not in _SEZIONE_ENTITA or not entita_id:
        raise HTTPException(400, "entita_tipo/entita_id non validi")

    corpo = body.get("corpo")
    titolo = body.get("titolo") or "Documento"
    if template_id and corpo is None:
        modello = await db.template_modelli.find_one({"id": template_id}, {"_id": 0})
        if not modello:
            raise HTTPException(404, "Modello non trovato")
        corpo = modello.get("corpo", "")
        titolo = body.get("titolo") or modello.get("nome") or "Documento"
    if corpo is None:
        raise HTTPException(400, "Nessun modello o testo fornito")

    ctx, ana, pol, comp, sin = await _context(entita_tipo, entita_id)
    logo = await _logo_bytes()
    pdf = _build_pdf(titolo, corpo, ctx, logo)

    if not body.get("salva"):
        return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                                 headers={"Content-Disposition": f'inline; filename="{titolo}.pdf"'})

    entita = _SEZIONE_ENTITA[entita_tipo]
    fname = f"{titolo}.pdf"
    stored = await StorageService.put(user=user, entita_tipo=entita, entita_id=entita_id,
                                      filename=f"doc_{entita_id[:8]}.pdf", data=pdf, content_type="application/pdf")
    alleg = Allegato(entita_tipo=entita, entita_id=entita_id, nome_file=fname,
                     storage_path=stored["storage_path"], storage_provider=stored["storage_provider"],
                     content_type="application/pdf", size=stored.get("size", len(pdf)),
                     categoria="documento_generato", descrizione=f"Documento generato: {titolo}")
    await db.allegati.insert_one(alleg.model_dump())
    return {"ok": True, "allegato_id": alleg.id, "nome_file": fname}
