"""MUP — Modulo Unico Precontrattuale (IVASS) generato dalla polizza.

Produce un PDF con: dati cliente, richieste/esigenze e garanzie (checklist),
dati prodotto/intermediario e area firma. Firmabile via eSignAnyWhere dal frontend.
"""
from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database import db
from auth import current_user
from db_models import Allegato, _now_iso
from storage_service import StorageService

router = APIRouter()

GARANZIE_RCA = ["Ricorso Terzi", "Rinuncia alla Rivalsa", "Cristalli", "Assistenza Stradale",
                "Incendio", "Furto", "Atti Vandalici", "Eventi Atmosferici", "Kasko",
                "Collisione", "Tutela Legale", "Infortunio del Conducente"]

GARANZIE_BENI = ["Incendio ed eventi complementari", "Furto e rapina", "Eventi atmosferici",
                 "Eventi sociopolitici e atti vandalici", "Danni da acqua condotta", "Fenomeno elettrico",
                 "Cristalli e lastre", "Terremoto", "Alluvione e inondazione",
                 "Responsabilità civile", "Tutela Legale", "Assistenza"]

GARANZIE_INFORTUNI = ["Morte da infortunio", "Invalidità permanente", "Inabilità temporanea",
                      "Diaria da ricovero", "Diaria da gessatura", "Rimborso spese mediche",
                      "Malattia grave", "Assistenza"]

GARANZIE_VITA = ["Caso morte", "Caso vita", "Invalidità totale permanente", "Malattie gravi",
                 "Long Term Care", "Esonero pagamento premi"]

GARANZIE_GENERICHE = ["Garanzia base", "Garanzie accessorie", "Massimali/Somme assicurate",
                      "Franchigie e scoperti", "Assistenza", "Tutela Legale"]


def _area_e_garanzie(pol: dict):
    """Determina area di tutela e set di garanzie in base a ramo/prodotto della polizza."""
    s = f"{pol.get('ramo','')} {pol.get('prodotto','')} {pol.get('tipo','')}".lower()
    if any(k in s for k in ("rca", "auto", "veicol", "autocarr", "libro matricola", "flotta")):
        return "Auto / RC Auto", GARANZIE_RCA
    if any(k in s for k in ("infortun", "malatt", "salute")):
        return "Infortuni e malattie", GARANZIE_INFORTUNI
    if any(k in s for k in ("vita", "tcm", "previdenza", "risparmio", "ltc")):
        return "Vita / Previdenza", GARANZIE_VITA
    if any(k in s for k in ("incendio", "furto", "casa", "fabbricat", "multirisch", "ard", "globale", "property", "beni", "abitazione", "rc")):
        return "Beni", GARANZIE_BENI
    return "Generica", GARANZIE_GENERICHE


def _eur(v):
    try:
        return "€ " + f"{float(v or 0):,.0f}".replace(",", ".")
    except Exception:
        return "—"


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


async def _ctx(pid: str):
    pol = await db.polizze.find_one({"id": pid}, {"_id": 0})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")
    ana = await db.anagrafiche.find_one({"id": pol.get("contraente_id")}, {"_id": 0}) or {}
    comp = await db.compagnie.find_one({"id": pol.get("compagnia_id")}, {"_id": 0}) or {}
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    return pol, ana, comp, az


def _righe_default(pol: dict):
    attive = set()
    for g in (pol.get("garanzie") or []):
        nome = g.get("nome") if isinstance(g, dict) else str(g)
        if nome:
            attive.add(nome.strip().lower())
    area, garanzie = _area_e_garanzie(pol)
    righe = [{"nome": g, "richiesta": g.lower() in attive, "proposta": g.lower() in attive,
              "confermata": g.lower() in attive} for g in garanzie]
    return area, righe


@router.get("/polizze/{pid}/mup/righe-default")
async def mup_righe_default(pid: str, user=Depends(current_user)):
    pol, _, _, _ = await _ctx(pid)
    area, righe = _righe_default(pol)
    return {"area": area, "righe": righe}


@router.get("/polizze/{pid}/mup/pdf")
async def mup_pdf(pid: str, user=Depends(current_user)):
    pol, ana, comp, az = await _ctx(pid)
    logo = await _logo_bytes()
    area, righe = _righe_default(pol)
    pdf = _build(pol, ana, comp, az, area, righe, logo)
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="MUP_{pol.get("numero_polizza", pid[:8])}.pdf"'})


@router.post("/polizze/{pid}/mup/genera")
async def mup_genera(pid: str, body: dict, user=Depends(current_user)):
    """Genera il MUP con le righe/spunte scelte a video. Se salva=true, lo archivia
    tra gli allegati della polizza (categoria 'mup')."""
    pol, ana, comp, az = await _ctx(pid)
    logo = await _logo_bytes()
    area = body.get("area") or _area_e_garanzie(pol)[0]
    righe = body.get("righe") or _righe_default(pol)[1]
    pdf = _build(pol, ana, comp, az, area, righe, logo)
    if not body.get("salva"):
        return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                                 headers={"Content-Disposition": f'inline; filename="MUP_{pol.get("numero_polizza", pid[:8])}.pdf"'})
    fname = f"MUP {pol.get('numero_polizza', '')}.pdf".strip()
    stored = await StorageService.put(user=user, entita_tipo="polizza", entita_id=pid,
                                      filename=f"mup_{pid[:8]}.pdf", data=pdf, content_type="application/pdf")
    alleg = Allegato(entita_tipo="polizza", entita_id=pid, nome_file=fname,
                     storage_path=stored["storage_path"], storage_provider=stored["storage_provider"],
                     content_type="application/pdf", size=stored.get("size", len(pdf)),
                     categoria="mup", descrizione=f"MUP — {area}")
    await db.allegati.insert_one(alleg.model_dump())
    return {"ok": True, "allegato_id": alleg.id, "nome_file": fname}


def _build(pol, ana, comp, az, area, righe, logo) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)

    navy = colors.HexColor("#0f2f4a")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=15, leading=19, textColor=navy, alignment=TA_CENTER, spaceAfter=2)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=11, leading=14, textColor=navy, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=13)
    small = ParagraphStyle("s", parent=ss["BodyText"], fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))
    th = ParagraphStyle("th", parent=body, fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white)

    def esc(t):
        return str(t or "").replace("&", "&amp;").replace("<", "&lt;")

    cliente = ana.get("ragione_sociale") or f"{ana.get('nome','')} {ana.get('cognome','')}".strip()
    ramo = pol.get("prodotto") or pol.get("ramo") or "—"
    story = [Paragraph("MODULO UNICO PRECONTRATTUALE (MUP)", H1),
             Paragraph(f"{esc(ramo)} — Area di tutela: {esc(area)} — Polizza n. {esc(pol.get('numero_polizza',''))}",
                       ParagraphStyle("sub", parent=body, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"))),
             HRFlowable(width="100%", thickness=1, color=navy, spaceAfter=8)]

    def kv(rows):
        t = Table([[Paragraph(esc(k), body), Paragraph(esc(v), body)] for k, v in rows], colWidths=[5 * cm, 11.5 * cm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)

    story.append(Paragraph("Dati del cliente", H2))
    kv([("Nome / Ragione sociale", cliente),
        ("Codice fiscale / P.IVA", ana.get("codice_fiscale") or ana.get("partita_iva") or "—"),
        ("Cellulare", ana.get("cellulare") or ana.get("telefono") or "—"),
        ("Email", ana.get("email") or "—"),
        ("Indirizzo", ", ".join([x for x in [ana.get("indirizzo"), ana.get("cap"), ana.get("comune")] if x]) or "—")])

    story.append(Paragraph("Richieste ed esigenze del cliente — Garanzie", H2))
    header = ["Garanzia", "Richiesta cliente", "Proposta interm.", "Confermata in polizza"]
    rows = [[Paragraph(h, th) for h in header]]
    for r in righe:
        def ck(v):
            return "☑" if v else "☐"
        rows.append([Paragraph(esc(r.get("nome")), body), Paragraph(ck(r.get("richiesta")), body),
                     Paragraph(ck(r.get("proposta")), body), Paragraph(ck(r.get("confermata")), body)])
    t = Table(rows, colWidths=[6.5 * cm, 3.3 * cm, 3.3 * cm, 3.4 * cm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), navy),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                           ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story.append(t)

    story.append(Paragraph("Dati prodotto e intermediario", H2))
    kv([("Compagnia", comp.get("ragione_sociale") or "—"),
        ("Nome prodotto", pol.get("prodotto") or "—"),
        ("Massimale", _eur(pol.get("massimale"))),
        ("Premio lordo", _eur(pol.get("premio_lordo") or pol.get("ultimo_premio_pagato"))),
        ("Intermediario", az.get("ragione_sociale") or "—"),
        ("Iscrizione RUI", (az.get("rui") or "—") + (f" sez. {az.get('rui_sezione')}" if az.get("rui_sezione") else "")),
        ("Vendita in esclusiva", "No"),
        ("Onorario a carico cliente", "No")])

    story.append(Spacer(1, 16))
    story.append(Paragraph("Dichiarazione del cliente", H2))
    story.append(Paragraph("Il sottoscritto dichiara di aver ricevuto e compreso le informazioni precontrattuali, "
                           "che le richieste ed esigenze assicurative sopra riportate corrispondono al vero e conferma "
                           "le garanzie indicate per l'inserimento in proposta/polizza.", body))
    story.append(Spacer(1, 26))
    fr = Table([[Paragraph("Luogo e data", body), Paragraph("Il Cliente", body)],
                [Paragraph("______________________", body), Paragraph("______________________", body)]],
               colWidths=[8.25 * cm, 8.25 * cm])
    fr.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 6)]))
    story.append(fr)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2.4 * cm, bottomMargin=1.6 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm, title="MUP")

    def _hdr(canvas, d):
        canvas.saveState()
        W, H = A4
        if logo:
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(BytesIO(logo)); iw, ih = img.getSize()
                lw = 2.8 * cm; lh = lw * ih / iw
                canvas.drawImage(img, W - 2 * cm - lw, H - 1.0 * cm - lh, lw, lh, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        canvas.setFont("Helvetica", 6.5); canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(2 * cm, 1.0 * cm, "Modulo Unico Precontrattuale — art. 56 Reg. IVASS 40/2018")
        canvas.drawRightString(W - 2 * cm, 1.0 * cm, f"Pag. {d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_hdr, onLaterPages=_hdr)
    return buf.getvalue()
