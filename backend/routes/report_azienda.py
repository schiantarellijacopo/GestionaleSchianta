"""Report Analisi Azienda (PDF + Word) basato sui dati di Salute Fiscale.

Genera un elaborato di presentazione/consulenza per aziende (persona giuridica)
prendendo i dati economico-finanziari dalla sezione Salute Fiscale
(`salute_fiscale_dati`), gli amministratori dalla governance OpenAPI e includendo
la Piramide Azienda. Struttura ispirata al modello "insurance advisor".
"""
from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database import db
from auth import current_user

router = APIRouter()

INTRO = ("Studio Schiantarelli – Consulenze per la Sicurezza Finanziaria e Patrimoniale nasce "
         "da oltre cinquant'anni di esperienza familiare nel campo assicurativo e si è evoluta in "
         "una struttura di consulenza moderna e indipendente, focalizzata sulla gestione strategica "
         "dei rischi aziendali e personali. La nostra attività si fonda sulla norma internazionale "
         "ISO 31000, standard riconosciuto a livello mondiale per la gestione del rischio. Per le "
         "aziende strutturate come la vostra, il nostro obiettivo è diventare un partner consulenziale, "
         "non un semplice intermediario assicurativo, attraverso un percorso in otto fasi che parte "
         "dalla mappatura completa dei rischi fino alla valutazione delle coperture esistenti.")
INTRO2 = ("Se amministri un'impresa, uno dei principali doveri consiste nel predisporre una mappatura "
          "chiara ed articolata dei rischi aziendali cui collegare un programma assicurativo aderente "
          "a tale analisi. Non è una facoltà, bensì un obbligo regolato dall'art. 2086 c.c.")
NOTE_LEGALI = ("Il presente elaborato è redatto secondo le disposizioni previste dagli artt. 58 e 59 del "
               "Regolamento N° 40 IVASS del 02.08.2018 e dall'art. 119-ter del Codice delle assicurazioni "
               "private (D.Lgs 209/2005). Ogni valutazione, indice, rating e/o somma assicurata indicati "
               "costituiscono mera indicazione e non sono in alcun modo vincolanti, né costituiscono stima "
               "o perizia. Documento riservato e confidenziale.")
NOTE_IA = ("Ai sensi dell'art. 13 della Legge n° 132 del 23 Settembre 2025 si informa che parti del presente "
           "elaborato possono essere state redatte avvalendosi di sistemi di intelligenza artificiale di tipo "
           "generativo, garantendo comunque la prevalenza del lavoro intellettuale e la responsabilità "
           "professionale dell'intermediario.")


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


async def _gather(aid: str):
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    if ana.get("tipo") != "persona_giuridica" and not ana.get("partita_iva"):
        raise HTTPException(400, "Il report azienda è disponibile solo per le persone giuridiche")
    sf = ana.get("salute_fiscale_dati") or {}
    bil = sf.get("bilancio_estratto") or {}
    if not bil:
        raise HTTPException(400, "Nessun dato di Salute Fiscale disponibile. Compila prima da OpenAPI.")
    comp = (ana.get("openapi_data") or {}).get("company") or {}
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    # Piramide azienda (dati reali)
    piramide = {
        "Fatturato": bil.get("valore_produzione") or bil.get("ricavi"),
        "Utile netto": bil.get("utile_netto"),
        "EBITDA": bil.get("ebitda"),
        "N. dipendenti": bil.get("dipendenti"),
        "N. soci": len(comp.get("soci") or []) or None,
        "Patrimonio netto": bil.get("patrimonio_netto"),
    }
    # MDC + metriche impatto (indicativi)
    vp = float(bil.get("valore_produzione") or bil.get("ricavi") or 0)
    cv = sum(float(bil.get(k) or 0) for k in ("costi_materie", "costi_servizi", "costi_godimento_beni", "oneri_diversi_gestione"))
    mdc = round(vp - cv)
    mdc_giorno = round(mdc / 220) if mdc else 0
    impatto = [("Trascurabile", 2), ("Gestibile", 7), ("Grave", 15), ("Critico", 25)]
    impatto = [(lbl, gg, mdc_giorno * gg) for lbl, gg in impatto]
    return ana, sf, bil, comp, az, piramide, mdc, mdc_giorno, impatto


@router.get("/anagrafiche/{aid}/report-azienda/pdf")
async def report_pdf(aid: str, user=Depends(current_user)):
    ctx = await _gather(aid)
    logo = await _logo_bytes()
    return StreamingResponse(BytesIO(_build_pdf(*ctx, logo=logo)), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="report_azienda_{aid[:8]}.pdf"'})


@router.get("/anagrafiche/{aid}/report-azienda/docx")
async def report_docx(aid: str, user=Depends(current_user)):
    ctx = await _gather(aid)
    logo = await _logo_bytes()
    return StreamingResponse(
        BytesIO(_build_docx(*ctx, logo=logo)),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="report_azienda_{aid[:8]}.docx"'})


# ============================================================ PDF
def _build_pdf(ana, sf, bil, comp, az, piramide, mdc, mdc_giorno, impatto, *, logo=None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable)

    navy = colors.HexColor("#0f2f4a")
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=17, leading=21, textColor=navy, alignment=TA_CENTER, spaceAfter=6)
    H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12, leading=15, textColor=navy, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
    small = ParagraphStyle("s", parent=ss["BodyText"], fontSize=7.5, leading=10, textColor=colors.HexColor("#64748b"))
    th = ParagraphStyle("th", parent=body, fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)

    def esc(t):
        return str(t or "").replace("&", "&amp;").replace("<", "&lt;")

    rag = ana.get("ragione_sociale", "")
    story = [Paragraph(f"{esc(rag)}", H1),
             Paragraph(f"PRESENTAZIONE — {esc(az.get('ragione_sociale', 'Studio'))}", ParagraphStyle("sub", parent=body, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"))),
             HRFlowable(width="100%", thickness=1.2, color=navy, spaceAfter=10),
             Paragraph(INTRO, body), Paragraph(INTRO2, body)]

    def sec(title):
        story.append(Paragraph(title, H2))

    def kv_table(rows, w1=6, w2=10):
        t = Table([[Paragraph(esc(k), body), Paragraph(esc(v), body)] for k, v in rows],
                  colWidths=[w1 * cm, w2 * cm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)

    def data_table(header, rows, widths):
        data = [[Paragraph(h, th) for h in header]]
        for r in rows:
            data.append([Paragraph(esc(c), body) for c in r])
        t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), navy),
                               ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)

    sec("Dati anagrafici")
    kv_table([
        ("Denominazione", rag),
        ("Sede legale", ", ".join([x for x in [ana.get("indirizzo"), ana.get("cap"), ana.get("comune"), f"({ana.get('provincia')})" if ana.get("provincia") else ""] if x])),
        ("Partita IVA", ana.get("partita_iva") or "—"),
        ("Cod. ATECO", comp.get("ateco") or ana.get("ateco") or "—"),
        ("N. addetti", str(bil.get("dipendenti") or "—")),
        ("Fatturato (Anno %s)" % (bil.get("anno") or ""), _eur(bil.get("valore_produzione") or bil.get("ricavi"))),
    ])

    ammin = comp.get("amministratori") or []
    if ammin:
        sec("I soggetti interessati")
        data_table(["Nome / Cognome", "Ruolo", "Legale rappr."],
                   [[a.get("nome", ""), a.get("ruoli", ""), "Sì" if a.get("legale_rappresentante") else "No"] for a in ammin[:12]],
                   [7, 6.5, 2.5])

    storico = sf.get("storico") or []
    if storico:
        sec("Valore della produzione e risultato d'esercizio")
        data_table(["Anno", "Valore produzione", "Utile/Perdita", "Dipendenti"],
                   [[str(s.get("anno")), _eur(s.get("fatturato")), _eur(s.get("patrimonio_netto")), str(s.get("dipendenti") or "—")] for s in storico[:6]],
                   [2.5, 5, 5, 3.5])

    sec("Analisi economica — indicatori di bilancio")
    ind = sf.get("indicatori") or {}
    data_table(["Indicatore", "Valore"],
               [["EBITDA", _eur(bil.get("ebitda"))], ["EBIT", _eur(bil.get("ebit"))],
                ["Utile netto", _eur(bil.get("utile_netto"))], ["ROE %", str(ind.get("roe_pct", "—"))],
                ["ROI %", str(ind.get("roi_pct", "—"))], ["ROS %", str(ind.get("ros_pct", "—"))],
                ["EBITDA margin %", str(ind.get("ebitda_margin_pct", "—"))],
                ["PFN/EBITDA", str(ind.get("pfn_ebitda", "—"))]],
               [10, 6])

    sec("Margine di contribuzione e costo del fermo attività")
    story.append(Paragraph(f"Margine di contribuzione (indicativo): <b>{_eur(mdc)}</b> — ogni giorno di fermo totale costa circa <b>{_eur(mdc_giorno)}</b> (su 220 gg lavorativi).", body))
    data_table(["Impatto", "Giorni di fermo", "Valore economico"],
               [[lbl, str(gg), _eur(val)] for lbl, gg, val in impatto], [5, 5, 6])

    sec("Dati da bilancio")
    data_table(["Voce", "Valore"],
               [["Patrimonio netto", _eur(bil.get("patrimonio_netto"))], ["Totale attivo", _eur(bil.get("totale_attivo"))],
                ["Immobilizzazioni", _eur(bil.get("immobilizzazioni"))], ["Attivo circolante", _eur(bil.get("attivo_circolante"))],
                ["Crediti clienti", _eur(bil.get("crediti_clienti"))], ["Debiti a breve", _eur(bil.get("debiti_breve"))],
                ["Disponibilità/Cash flow", _eur(bil.get("cash_flow"))], ["Rimanenze", _eur(bil.get("rimanenze_totali"))]],
               [10, 6])

    sec("Piramide Azienda")
    story.append(Paragraph("Sintesi dei valori chiave utilizzati per l'analisi dei rischi e il dimensionamento delle coperture.", body))
    data_table(["Voce", "Valore"],
               [[k, (_eur(v) if k not in ("N. dipendenti", "N. soci") else (str(v) if v else "—"))] for k, v in piramide.items()],
               [10, 6])

    sec("Note legali")
    story.append(Paragraph(NOTE_LEGALI, small))
    story.append(Paragraph(NOTE_IA, small))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2.4 * cm, bottomMargin=1.8 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm, title="Report Analisi Azienda")

    def _hdr(canvas, d):
        canvas.saveState()
        W, H = A4
        if logo:
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(BytesIO(logo))
                iw, ih = img.getSize(); lw = 3 * cm; lh = lw * ih / iw
                canvas.drawImage(img, W - 2 * cm - lw, H - 1.0 * cm - lh, lw, lh, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        canvas.setFont("Helvetica", 7); canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(2 * cm, 1.1 * cm, "Documento riservato · Analisi redatta con standard ISO 31000")
        canvas.drawRightString(W - 2 * cm, 1.1 * cm, f"Pag. {d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_hdr, onLaterPages=_hdr)
    return buf.getvalue()


# ============================================================ DOCX
def _build_docx(ana, sf, bil, comp, az, piramide, mdc, mdc_giorno, impatto, *, logo=None) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    d = Document()
    navy = RGBColor(0x0f, 0x2f, 0x4a)
    rag = ana.get("ragione_sociale", "")
    if logo:
        try:
            hp = d.sections[0].header.paragraphs[0]; hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            hp.add_run().add_picture(BytesIO(logo), width=Cm(3.2))
        except Exception:
            pass
    tp = d.add_paragraph(); tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = tp.add_run(rag); r.bold = True; r.font.size = Pt(18); r.font.color.rgb = navy
    sp = d.add_paragraph(); sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = sp.add_run(f"PRESENTAZIONE — {az.get('ragione_sociale', 'Studio')}"); sr.font.size = Pt(10); sr.font.color.rgb = RGBColor(0x64, 0x74, 0x8b)

    def para(t, size=9.5):
        p = d.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        rr = p.add_run(t); rr.font.size = Pt(size); return p

    def sec(title):
        p = d.add_paragraph(); rr = p.add_run(title); rr.bold = True; rr.font.size = Pt(12); rr.font.color.rgb = navy

    def table(header, rows):
        t = d.add_table(rows=1, cols=len(header)); t.style = "Light Grid Accent 1"
        for i, h in enumerate(header):
            c = t.rows[0].cells[i]; run = c.paragraphs[0].add_run(h); run.bold = True; run.font.size = Pt(9)
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                run = cells[i].paragraphs[0].add_run(str(v)); run.font.size = Pt(9)

    para(INTRO); para(INTRO2)

    sec("Dati anagrafici")
    table(["Voce", "Valore"], [
        ["Denominazione", rag],
        ["Sede legale", ", ".join([x for x in [ana.get("indirizzo"), ana.get("cap"), ana.get("comune"), f"({ana.get('provincia')})" if ana.get("provincia") else ""] if x])],
        ["Partita IVA", ana.get("partita_iva") or "—"],
        ["Cod. ATECO", comp.get("ateco") or ana.get("ateco") or "—"],
        ["N. addetti", bil.get("dipendenti") or "—"],
        ["Fatturato (Anno %s)" % (bil.get("anno") or ""), _eur(bil.get("valore_produzione") or bil.get("ricavi"))],
    ])

    ammin = comp.get("amministratori") or []
    if ammin:
        sec("I soggetti interessati")
        table(["Nome / Cognome", "Ruolo", "Legale rappr."],
              [[a.get("nome", ""), a.get("ruoli", ""), "Sì" if a.get("legale_rappresentante") else "No"] for a in ammin[:12]])

    storico = sf.get("storico") or []
    if storico:
        sec("Valore della produzione e risultato d'esercizio")
        table(["Anno", "Valore produzione", "Utile/Perdita", "Dipendenti"],
              [[s.get("anno"), _eur(s.get("fatturato")), _eur(s.get("patrimonio_netto")), s.get("dipendenti") or "—"] for s in storico[:6]])

    ind = sf.get("indicatori") or {}
    sec("Analisi economica — indicatori di bilancio")
    table(["Indicatore", "Valore"],
          [["EBITDA", _eur(bil.get("ebitda"))], ["EBIT", _eur(bil.get("ebit"))], ["Utile netto", _eur(bil.get("utile_netto"))],
           ["ROE %", ind.get("roe_pct", "—")], ["ROI %", ind.get("roi_pct", "—")], ["ROS %", ind.get("ros_pct", "—")],
           ["EBITDA margin %", ind.get("ebitda_margin_pct", "—")], ["PFN/EBITDA", ind.get("pfn_ebitda", "—")]])

    sec("Margine di contribuzione e costo del fermo attività")
    para(f"Margine di contribuzione (indicativo): {_eur(mdc)} — ogni giorno di fermo totale costa circa {_eur(mdc_giorno)} (su 220 gg lavorativi).")
    table(["Impatto", "Giorni di fermo", "Valore economico"], [[lbl, gg, _eur(val)] for lbl, gg, val in impatto])

    sec("Dati da bilancio")
    table(["Voce", "Valore"],
          [["Patrimonio netto", _eur(bil.get("patrimonio_netto"))], ["Totale attivo", _eur(bil.get("totale_attivo"))],
           ["Immobilizzazioni", _eur(bil.get("immobilizzazioni"))], ["Attivo circolante", _eur(bil.get("attivo_circolante"))],
           ["Crediti clienti", _eur(bil.get("crediti_clienti"))], ["Debiti a breve", _eur(bil.get("debiti_breve"))],
           ["Cash flow", _eur(bil.get("cash_flow"))], ["Rimanenze", _eur(bil.get("rimanenze_totali"))]])

    sec("Piramide Azienda")
    para("Sintesi dei valori chiave utilizzati per l'analisi dei rischi e il dimensionamento delle coperture.")
    table(["Voce", "Valore"],
          [[k, (_eur(v) if k not in ("N. dipendenti", "N. soci") else (v if v else "—"))] for k, v in piramide.items()])

    sec("Note legali")
    r1 = d.add_paragraph().add_run(NOTE_LEGALI); r1.font.size = Pt(7.5); r1.font.color.rgb = RGBColor(0x64, 0x74, 0x8b)
    r2 = d.add_paragraph().add_run(NOTE_IA); r2.font.size = Pt(7.5); r2.font.color.rgb = RGBColor(0x64, 0x74, 0x8b)

    buf = BytesIO(); d.save(buf); return buf.getvalue()
