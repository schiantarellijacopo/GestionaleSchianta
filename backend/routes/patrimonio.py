"""Patrimonio Cliente — CRUD immobili + geocoding + PDF report.

Ogni anagrafica ha un array `immobili: List[ImmobileItem]` in DB.
Endpoint gestiscono add/edit/delete + geocode Nominatim + generazione PDF report.
"""
from __future__ import annotations
import uuid
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import _now_iso, ImmobileItem
import geocoder as geocoder_svc

router = APIRouter()


def _fmt_eur(v: float | int | None) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except Exception:
        return str(v)
    return f"€ {f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _get_anagrafica_or_404(aid: str, user: dict) -> dict:
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    if user.get("role") == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Non autorizzato")
    return ana


@router.get("/anagrafiche/{aid}/immobili")
async def lista_immobili(aid: str, user=Depends(current_user)) -> list[dict]:
    ana = await _get_anagrafica_or_404(aid, user)
    return ana.get("immobili") or []


@router.post("/anagrafiche/{aid}/immobili", status_code=201)
async def crea_immobile(
    aid: str, body: dict,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    ana = await _get_anagrafica_or_404(aid, user)
    # Valida via pydantic
    im = ImmobileItem(**body).model_dump()
    # Auto-geocoding se indirizzo + comune presenti
    if im.get("indirizzo") and im.get("comune") and not im.get("latitude"):
        try:
            r = await geocoder_svc.geocoda_indirizzo(
                indirizzo=im["indirizzo"], comune=im["comune"],
                provincia=im.get("provincia") or None, paese="it",
            )
            if r and r.get("found"):
                im["latitude"] = r.get("lat")
                im["longitude"] = r.get("lon")
        except Exception:
            pass
    immobili = list(ana.get("immobili") or [])
    immobili.append(im)
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$set": {"immobili": immobili, "updated_at": _now_iso()}},
    )
    return im


@router.put("/anagrafiche/{aid}/immobili/{iid}")
async def aggiorna_immobile(
    aid: str, iid: str, body: dict,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    ana = await _get_anagrafica_or_404(aid, user)
    immobili = list(ana.get("immobili") or [])
    idx = next((i for i, x in enumerate(immobili) if x.get("id") == iid), None)
    if idx is None:
        raise HTTPException(404, "Immobile non trovato")
    merged = {**immobili[idx], **body, "id": iid}
    im = ImmobileItem(**merged).model_dump()
    # se indirizzo cambiato → regeocode
    indir_changed = (
        body.get("indirizzo") and body["indirizzo"] != immobili[idx].get("indirizzo")
    )
    if indir_changed and im.get("indirizzo") and im.get("comune"):
        try:
            r = await geocoder_svc.geocoda_indirizzo(
                indirizzo=im["indirizzo"], comune=im["comune"],
                provincia=im.get("provincia") or None, paese="it",
            )
            if r and r.get("found"):
                im["latitude"] = r.get("lat")
                im["longitude"] = r.get("lon")
        except Exception:
            pass
    immobili[idx] = im
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$set": {"immobili": immobili, "updated_at": _now_iso()}},
    )
    return im


@router.delete("/anagrafiche/{aid}/immobili/{iid}")
async def elimina_immobile(
    aid: str, iid: str,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    ana = await _get_anagrafica_or_404(aid, user)
    immobili = [x for x in (ana.get("immobili") or []) if x.get("id") != iid]
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$set": {"immobili": immobili, "updated_at": _now_iso()}},
    )
    return {"ok": True, "n": len(immobili)}


@router.post("/anagrafiche/{aid}/immobili/{iid}/geocode")
async def geocode_immobile(
    aid: str, iid: str,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    ana = await _get_anagrafica_or_404(aid, user)
    immobili = list(ana.get("immobili") or [])
    idx = next((i for i, x in enumerate(immobili) if x.get("id") == iid), None)
    if idx is None:
        raise HTTPException(404, "Immobile non trovato")
    im = immobili[idx]
    if not (im.get("indirizzo") and im.get("comune")):
        raise HTTPException(400, "Indirizzo o comune mancanti")
    r = await geocoder_svc.geocoda_indirizzo(
        indirizzo=im["indirizzo"], comune=im["comune"],
        provincia=im.get("provincia") or None, paese="it",
    )
    if not (r and r.get("found")):
        raise HTTPException(404, "Indirizzo non geocodificabile")
    im["latitude"] = r.get("lat")
    im["longitude"] = r.get("lon")
    immobili[idx] = im
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$set": {"immobili": immobili, "updated_at": _now_iso()}},
    )
    return {"latitude": im["latitude"], "longitude": im["longitude"], "address": r.get("address")}


@router.get("/anagrafiche/{aid}/immobili/report.pdf")
async def pdf_report_patrimonio(aid: str, user=Depends(current_user)):
    """Report PDF completo del patrimonio immobiliare del cliente."""
    ana = await _get_anagrafica_or_404(aid, user)
    immobili = ana.get("immobili") or []
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=colors.HexColor("#0f172a"),
                        fontSize=18, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=colors.HexColor("#334155"),
                        fontSize=13, spaceAfter=4)
    normal = ParagraphStyle("nrm", parent=styles["Normal"], fontSize=10, leading=13)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontSize=8, leading=11,
                           textColor=colors.HexColor("#64748b"))

    story: list = []
    nome = ana.get("ragione_sociale") or f"{ana.get('cognome', '')} {ana.get('nome', '')}".strip()
    story.append(Paragraph("Report Patrimonio Immobiliare", h1))
    story.append(Paragraph(f"Cliente: <b>{nome}</b>", normal))
    story.append(Paragraph(f"CF/P.IVA: {ana.get('codice_fiscale') or ana.get('partita_iva') or '—'}", small))
    story.append(Paragraph(f"Data report: {_now_iso()[:10]}", small))
    story.append(Spacer(1, 8))

    if not immobili:
        story.append(Paragraph("Nessun immobile registrato.", normal))
    else:
        # Sommario
        tot_ricos = sum(float(i.get("valore_ricostruzione") or 0) for i in immobili)
        tot_comm = sum(float(i.get("valore_commerciale") or 0) for i in immobili)
        tot_sup = sum(float(i.get("superficie_mq") or 0) for i in immobili)
        story.append(Paragraph("Sommario patrimonio", h2))
        summary_data = [
            ["Immobili totali", str(len(immobili))],
            ["Superficie totale", f"{tot_sup:,.0f} mq".replace(",", ".")],
            ["Valore commerciale totale", _fmt_eur(tot_comm)],
            ["Valore ricostruzione totale", _fmt_eur(tot_ricos)],
        ]
        st = Table(summary_data, colWidths=[80 * mm, 60 * mm])
        st.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(st)
        story.append(Spacer(1, 12))

        # Dettaglio ogni immobile
        for i, im in enumerate(immobili, 1):
            valore_netto = float(im.get("valore_ricostruzione") or 0)
            degrado = float(im.get("percentuale_degrado") or 0)
            valore_attuale = valore_netto * (1 - degrado / 100) if valore_netto else 0
            story.append(Paragraph(f"Immobile #{i} — {im.get('tipo', 'abitativo').capitalize()}", h2))
            det = [
                ["Indirizzo", im.get("indirizzo") or "—"],
                ["Comune", f"{im.get('comune') or '—'} {im.get('provincia') or ''}".strip()],
                ["Foglio / Particella / Sub", f"{im.get('foglio') or '—'} / {im.get('particella') or '—'} / {im.get('sub') or '—'}"],
                ["Categoria catastale", im.get("categoria_catastale") or "—"],
                ["Rendita catastale", _fmt_eur(im.get("rendita_catastale"))],
                ["Superficie (mq)", f"{float(im.get('superficie_mq') or 0):,.0f}".replace(",", ".")],
                ["Anno costruzione", str(im.get("anno_costruzione") or "—")],
                ["Titolo", im.get("titolo", "").replace("_", " ").capitalize()],
                ["Quota", f"{float(im.get('percentuale_proprieta') or 100):.0f}%"],
                ["Valore commerciale", _fmt_eur(im.get("valore_commerciale"))],
                ["Valore ricostruzione (nuovo)", _fmt_eur(im.get("valore_ricostruzione"))],
                ["Percentuale degrado", f"{degrado:.1f}%"],
                ["Valore ricostruzione attuale", _fmt_eur(valore_attuale)],
            ]
            if im.get("latitude") and im.get("longitude"):
                det.append(["Coordinate GPS", f"{im['latitude']:.5f}, {im['longitude']:.5f}"])
            if im.get("note"):
                det.append(["Note", im.get("note")])
            t = Table(det, colWidths=[60 * mm, 110 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.15, colors.HexColor("#e2e8f0")),
            ]))
            story.append(t)
            story.append(Spacer(1, 10))
            if i < len(immobili):
                story.append(PageBreak())

    doc.build(story)
    pdf = buf.getvalue()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="patrimonio_{aid}.pdf"'})
