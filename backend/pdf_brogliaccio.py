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


def _header_table(azienda: dict, data_giorno: str, logo_bytes: bytes = None) -> dict:
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


# ---------------------------------------------------------------------------
# Helpers di sezione (estratti da stampa_brogliaccio)
# ---------------------------------------------------------------------------
def _build_riga_dettaglio(r: dict, conti_cassa: list, small_style) -> list:
    """Costruisce una riga della tabella dettaglio."""
    per_conto = r.get("per_conto") or {}
    contr = r.get("contraente") or r.get("descrizione") or "—"
    sotto_parts = []
    if r.get("numero_polizza"):
        sotto_parts.append(f"N. {r['numero_polizza']}")
    if r.get("compagnia"):
        sotto_parts.append(r["compagnia"])
    sotto = " · ".join(sotto_parts) if sotto_parts else r.get("descrizione", "")
    descr_html = f"<b>{contr[:60]}</b>"
    if sotto:
        descr_html += f"<br/><font size=6 color='#475569'>{sotto[:80]}</font>"
    row = [
        Paragraph(descr_html, small_style),
        _eur(r.get("totale", 0)),
        _eur(r.get("provv", 0)),
        _eur(r.get("saldo", 0)),
        _eur(r.get("crediti", 0)),
        _eur(r.get("spese", 0)),
    ]
    row.extend(_eur(per_conto.get(c["id"], 0)) for c in conti_cassa)
    return row


def _build_riga_totale_giornata(tg: dict, conti_cassa: list) -> list:
    tg_per_conto = tg.get("per_conto") or {}
    row = [
        "TOTALE GIORNATA",
        _eur_zero(tg.get("totale", 0)),
        _eur_zero(tg.get("provv", 0)),
        _eur_zero(tg.get("saldo", 0)),
        _eur_zero(tg.get("crediti", 0)),
        _eur_zero(tg.get("spese", 0)),
    ]
    row.extend(_eur_zero(tg_per_conto.get(c["id"], 0)) for c in conti_cassa)
    return row


def _calcola_larghezze(n_conti: int) -> list:
    page_w = landscape(A4)[0] - 16 * mm
    fixed_w = 18 * mm * 5
    conti_w = max(15 * mm, (page_w - fixed_w - 70 * mm) / max(1, n_conti))
    descr_w = page_w - fixed_w - conti_w * n_conti
    return [descr_w] + [18 * mm] * 5 + [conti_w] * n_conti


def _stile_tabella_dettaglio() -> TableStyle:
    return TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
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


def _tabella_dettaglio(conti_cassa: list, righe: list, totali_giornata: dict,
                       small_style) -> Table:
    headers = (["Descrizione", "Totale", "Provv", "Saldo", "Sospesi", "Spese"]
               + [c["nome"] for c in conti_cassa])
    data_rows: list[list] = [headers]
    for r in righe:
        data_rows.append(_build_riga_dettaglio(r, conti_cassa, small_style))
    data_rows.append(_build_riga_totale_giornata(totali_giornata or {}, conti_cassa))
    tbl = Table(data_rows, colWidths=_calcola_larghezze(len(conti_cassa)), repeatRows=1)
    tbl.setStyle(_stile_tabella_dettaglio())
    return tbl


def _tabella_riepilogo_conti(conti_riepilogo: list) -> Table:
    headers = ["Descrizione", "Imp. Precedente", "Imp. Giornata", "Totale Periodo"]
    rows = [headers]
    for c in conti_riepilogo:
        rows.append([
            c.get("nome"), _eur_zero(c.get("imp_precedente", 0)),
            _eur_zero(c.get("imp_giornata", 0)),
            _eur_zero(c.get("totale_periodo", 0)),
        ])
    tbl = Table(rows, colWidths=[80 * mm, 50 * mm, 50 * mm, 60 * mm])
    tbl.setStyle(TableStyle([
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
    return tbl


def _tabella_saldi_compagnie(saldi: list) -> Table:
    headers = ["Compagnia", "Regime", "Incassi lordi",
               "Provvigioni", "Saldo dovuto", "Rimesse pagate", "Saldo cassa"]
    rows = [headers]
    for s in saldi:
        regime = "Tratteniamo" if s.get("trattiene_provvigioni") else "No trattenute"
        rows.append([
            s.get("compagnia", "")[:40], regime,
            _eur_zero(s.get("incassi_lordi", 0)),
            _eur_zero(s.get("provvigioni", 0)),
            _eur_zero(s.get("saldo_dovuto", 0)),
            _eur_zero(s.get("rimesse_pagate", 0)),
            _eur_zero(s.get("saldo_cassa", 0)),
        ])
    tbl = Table(rows, colWidths=[60 * mm, 25 * mm, 30 * mm, 28 * mm, 30 * mm, 30 * mm, 32 * mm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F8FAFC")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("FONTNAME", (-1, 1), (-1, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _tabella_kpi_bottom(k: dict) -> Table:
    headers = ["ENTRATE", "PROVVIGIONI", "CREDITI", "RIMESSE", "SCONTI", "SPESE", "SALDO CASSA"]
    values = [_eur_zero(k.get(key, 0)) for key in
              ("entrate", "provvigioni", "crediti", "rimesse", "sconti", "spese", "saldo_cassa")]
    tbl = Table([headers, values], colWidths=[35 * mm] * 7)
    tbl.setStyle(TableStyle([
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
    return tbl


def _tabella_liquidita(k: dict) -> Table | None:
    ld = k.get("liquidita_disponibile")
    lp = k.get("liquidita_postera")
    if ld is None and lp is None:
        return None
    rows = []
    if ld is not None:
        rows.append(["LIQUIDITÀ DISPONIBILE", _eur_zero(ld)])
    if lp is not None:
        rows.append(["LIQUIDITÀ POSTERA", _eur_zero(lp)])
    tbl = Table(rows, colWidths=[60 * mm, 45 * mm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _footer_chiusura(chiusura_info: dict, styles) -> Paragraph:
    msg = (f"Giornata chiusa il {chiusura_info.get('closed_at', '')} da "
           f"{chiusura_info.get('closed_by_name', '')}")
    return Paragraph(
        f"<i>{msg}</i>",
        ParagraphStyle("foot", parent=styles["Normal"],
                       fontName="Helvetica-Oblique", fontSize=8,
                       textColor=colors.HexColor("#64748B")),
    )


# ---------------------------------------------------------------------------
# Entrypoint pubblico
# ---------------------------------------------------------------------------
def stampa_brogliaccio(
    data_giorno: str,
    azienda: dict,
    conti_cassa: list,
    righe: list,
    totali_giornata: dict,
    conti_riepilogo: list,
    riepilogo_kpi: dict,
    saldi_compagnie: list = None,
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
    h1 = ParagraphStyle("h1", parent=styles["Normal"],
                        fontName="Helvetica-Bold", fontSize=11)

    story: list = []
    # === Pagina 1: Dettaglio movimenti ===
    story.append(_header_table(azienda, data_giorno, logo_bytes))
    story.append(Spacer(1, 4 * mm))
    story.append(_tabella_dettaglio(conti_cassa, righe, totali_giornata, small))

    # === Pagina 2: Riepilogo + KPI ===
    story.append(PageBreak())
    story.append(_header_table(azienda, data_giorno, logo_bytes))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>RIEPILOGO CONTI</b>", h1))
    story.append(Spacer(1, 2 * mm))
    story.append(_tabella_riepilogo_conti(conti_riepilogo))

    if saldi_compagnie:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(
            "<b>SALDO CASSA PER COMPAGNIA</b> "
            "<font size=8 color='#475569'>(cumulativo periodo)</font>", h1,
        ))
        story.append(Spacer(1, 2 * mm))
        story.append(_tabella_saldi_compagnie(saldi_compagnie))

    story.append(Spacer(1, 8 * mm))
    story.append(_tabella_kpi_bottom(riepilogo_kpi or {}))

    liq = _tabella_liquidita(riepilogo_kpi or {})
    if liq:
        story.append(Spacer(1, 4 * mm))
        story.append(liq)

    if chiusura_info:
        story.append(Spacer(1, 6 * mm))
        story.append(_footer_chiusura(chiusura_info, styles))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
