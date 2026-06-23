"""PDF Brogliaccio Prima Nota - replica del facsimile fornito.

Layout (landscape):
  Header: logo + ragione sociale + "Brogliaccio del DD-MM-YYYY"
  Pagina 1 - Tabella dettaglio:
    Descrizione | Totale | Provv | Saldo | Crediti | Spese | <conti_cassa_dinamici...>
  Pagina 2 - Riepilogo:
    Totale giornata
    Sezione "Conti": Descrizione | Imp.Precedente | Imp.Giornata | Totale Periodo
    Bottom KPI: ENTRATE | PROVVIGIONI | CREDITI | RIMESSE | SCONTI | SPESE | SALDO CASSA
"""
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, Image, PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm


def _eur(v: float) -> str:
    if v is None or v == 0:
        return ""
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{s}" if v < 0 else s


def _eur_zero(v: float) -> str:
    if v is None:
        v = 0
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{s}" if v < 0 else s


def _format_data_it(s: str) -> str:
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.strftime("%d-%m-%Y")
    except Exception:
        return s


def _header_table(azienda: dict, data_giorno: str, logo_bytes: bytes = None):
    title = f"Brogliaccio del {_format_data_it(data_giorno)}"
    rs = azienda.get("ragione_sociale") or "Agenzia"
    indirizzo = ", ".join([
        x for x in [azienda.get("indirizzo"), azienda.get("cap"),
                    azienda.get("comune"), azienda.get("provincia")] if x
    ])
    rui = f"RUI: {azienda['rui']}" if azienda.get("rui") else ""
    info = "<br/>".join([x for x in [rs, indirizzo, rui] if x])
    styles = getSampleStyleSheet()
    info_style = ParagraphStyle("info", parent=styles["Normal"],
                                fontName="Helvetica", fontSize=8, leading=10)
    title_style = ParagraphStyle("title", parent=styles["Normal"],
                                 fontName="Helvetica-Bold", fontSize=12,
                                 alignment=2)  # right
    info_p = Paragraph(info, info_style)
    title_p = Paragraph(title, title_style)

    logo_cell = ""
    if logo_bytes:
        try:
            logo_cell = Image(BytesIO(logo_bytes), width=22 * mm, height=22 * mm)
        except Exception:
            logo_cell = ""

    tbl = Table([[logo_cell, info_p, title_p]],
                colWidths=[26 * mm, 140 * mm, 100 * mm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (-1, 0), (-1, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#0F172A")),
    ]))
    return tbl


def stampa_brogliaccio(
    data_giorno: str,
    azienda: dict,
    conti_cassa: list,    # [{id, nome, ordine}]
    righe: list,          # [{descrizione, totale, provv, saldo, crediti, spese, per_conto: {conto_id: importo}}]
    totali_giornata: dict,  # stesso schema righe
    conti_riepilogo: list,  # [{nome, imp_precedente, imp_giornata, totale_periodo}]
    riepilogo_kpi: dict,    # {entrate, provvigioni, crediti, rimesse, sconti, spese, saldo_cassa,
                            #  liquidita_disponibile, liquidita_postera}
    chiusura_info: dict = None,
    logo_bytes: bytes = None,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=8 * mm, rightMargin=8 * mm,
        topMargin=8 * mm, bottomMargin=10 * mm,
        title=f"Brogliaccio {data_giorno}",
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"],
                           fontName="Helvetica", fontSize=7, leading=8)
    story = []
    story.append(_header_table(azienda, data_giorno, logo_bytes))
    story.append(Spacer(1, 4 * mm))

    # === Tabella dettaglio ===
    # Colonne dinamiche: descrizione + 5 fisse + conti
    headers_fissi = ["Descrizione", "Totale", "Provv", "Saldo", "Crediti", "Spese"]
    conti_names = [c["nome"] for c in conti_cassa]
    headers = headers_fissi + conti_names

    data_rows = [headers]
    for r in righe:
        per_conto = r.get("per_conto") or {}
        row = [
            Paragraph(r.get("descrizione", "")[:90], small),
            _eur(r.get("totale", 0)),
            _eur(r.get("provv", 0)),
            _eur(r.get("saldo", 0)),
            _eur(r.get("crediti", 0)),
            _eur(r.get("spese", 0)),
        ]
        for c in conti_cassa:
            row.append(_eur(per_conto.get(c["id"], 0)))
        data_rows.append(row)

    # Riga "Totale giornata"
    tg = totali_giornata or {}
    tg_per_conto = tg.get("per_conto") or {}
    tot_row = [
        "TOTALE GIORNATA",
        _eur_zero(tg.get("totale", 0)),
        _eur_zero(tg.get("provv", 0)),
        _eur_zero(tg.get("saldo", 0)),
        _eur_zero(tg.get("crediti", 0)),
        _eur_zero(tg.get("spese", 0)),
    ]
    for c in conti_cassa:
        tot_row.append(_eur_zero(tg_per_conto.get(c["id"], 0)))
    data_rows.append(tot_row)

    n_cols = len(headers)
    # larghezza colonna conto fissa, descrizione si adatta
    page_w = landscape(A4)[0] - 16 * mm
    fixed_w = sum([18 * mm] * 5)  # totale, provv, saldo, crediti, spese
    conti_w = max(15 * mm, (page_w - fixed_w - 70 * mm) / max(1, len(conti_names)))
    descr_w = page_w - fixed_w - conti_w * len(conti_names)
    col_widths = [descr_w] + [18 * mm] * 5 + [conti_w] * len(conti_names)

    tbl = Table(data_rows, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.white, colors.HexColor("#F8FAFC")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#0F172A")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF3C7")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0F172A")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
    ])
    tbl.setStyle(style)
    story.append(tbl)

    # === Pagina 2: Riepilogo conti + KPI ===
    story.append(PageBreak())
    story.append(_header_table(azienda, data_giorno, logo_bytes))
    story.append(Spacer(1, 4 * mm))

    # Sezione Conti
    story.append(Paragraph(
        "<b>RIEPILOGO CONTI</b>",
        ParagraphStyle("h1", parent=styles["Normal"],
                       fontName="Helvetica-Bold", fontSize=11),
    ))
    story.append(Spacer(1, 2 * mm))
    conti_headers = ["Descrizione", "Imp. Precedente", "Imp. Giornata", "Totale Periodo"]
    conti_rows = [conti_headers]
    for c in conti_riepilogo:
        conti_rows.append([
            c.get("nome"), _eur_zero(c.get("imp_precedente", 0)),
            _eur_zero(c.get("imp_giornata", 0)),
            _eur_zero(c.get("totale_periodo", 0)),
        ])
    conti_tbl = Table(conti_rows, colWidths=[80 * mm, 50 * mm, 50 * mm, 60 * mm])
    conti_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F8FAFC")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(conti_tbl)

    # Bottom KPI
    story.append(Spacer(1, 8 * mm))
    k = riepilogo_kpi or {}
    kpi_headers = ["ENTRATE", "PROVVIGIONI", "CREDITI", "RIMESSE", "SCONTI", "SPESE", "SALDO CASSA"]
    kpi_values = [
        _eur_zero(k.get("entrate", 0)),
        _eur_zero(k.get("provvigioni", 0)),
        _eur_zero(k.get("crediti", 0)),
        _eur_zero(k.get("rimesse", 0)),
        _eur_zero(k.get("sconti", 0)),
        _eur_zero(k.get("spese", 0)),
        _eur_zero(k.get("saldo_cassa", 0)),
    ]
    kpi_tbl = Table([kpi_headers, kpi_values],
                    colWidths=[35 * mm] * 7)
    kpi_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FEF3C7")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 10),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#0F172A")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#94A3B8")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_tbl)

    story.append(Spacer(1, 4 * mm))
    ld = k.get("liquidita_disponibile")
    lp = k.get("liquidita_postera")
    if ld is not None or lp is not None:
        liq_rows = []
        if ld is not None:
            liq_rows.append(["LIQUIDITÀ DISPONIBILE", _eur_zero(ld)])
        if lp is not None:
            liq_rows.append(["LIQUIDITÀ POSTERA", _eur_zero(lp)])
        liq_tbl = Table(liq_rows, colWidths=[60 * mm, 45 * mm])
        liq_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(liq_tbl)

    # Footer chiusura
    if chiusura_info:
        story.append(Spacer(1, 6 * mm))
        msg = (f"Giornata chiusa il {chiusura_info.get('closed_at', '')} da "
               f"{chiusura_info.get('closed_by_name', '')}")
        story.append(Paragraph(
            f"<i>{msg}</i>",
            ParagraphStyle("foot", parent=styles["Normal"],
                           fontName="Helvetica-Oblique", fontSize=8,
                           textColor=colors.HexColor("#64748B")),
        ))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
