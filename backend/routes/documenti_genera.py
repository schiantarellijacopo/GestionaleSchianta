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
    return ctx, ana, pol, comp, sin


def _sub(text: str, ctx: dict) -> str:
    return re.sub(r"\{([a-z_]+)\}", lambda m: str(ctx.get(m.group(1), m.group(0))), text or "")


def _build_pdf(titolo: str, corpo: str, ctx: dict, logo: bytes | None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, HRFlowable

    navy = colors.HexColor("#0f2f4a")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=15, leading=19, textColor=navy, alignment=TA_CENTER, spaceAfter=6)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=10, leading=15)

    def esc(t):
        return str(t or "").replace("&", "&amp;").replace("<", "&lt;")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)
    story = []
    if logo:
        try:
            img = Image(BytesIO(logo))
            ratio = img.imageWidth / max(img.imageHeight, 1)
            img.drawHeight = 1.4 * cm
            img.drawWidth = 1.4 * cm * ratio
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 6))
        except Exception:
            pass
    story.append(Paragraph(esc(titolo), H1))
    story.append(HRFlowable(width="100%", thickness=1, color=navy, spaceAfter=10))
    testo = _sub(corpo, ctx)
    for para in testo.split("\n"):
        story.append(Paragraph(esc(para) if para.strip() else "&nbsp;", body))
    doc.build(story)
    return buf.getvalue()


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
