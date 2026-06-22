"""Generatore PDF generico per stampe elenco di una sezione."""
from __future__ import annotations
import io
from datetime import datetime
from typing import List, Sequence
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(v)


def stampa_elenco(
    titolo: str,
    sottotitolo: str | None,
    headers: Sequence[str],
    rows: Sequence[Sequence],
    col_widths_mm: Sequence[float] | None = None,
    landscape_mode: bool = True,
    ragione_sociale: str = "Assicura - Gestione Agenzia",
    filtri_attivi: dict | None = None,
) -> bytes:
    buf = io.BytesIO()
    page_size = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(
        buf, pagesize=page_size,
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    h_style = ParagraphStyle("h", parent=styles["Heading1"], fontSize=14, alignment=0, spaceAfter=2, textColor=colors.HexColor("#0F172A"))
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, alignment=0, textColor=colors.HexColor("#475569"))
    chip_style = ParagraphStyle("chip", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#0369A1"))
    foot_style = ParagraphStyle("foot", parent=styles["Normal"], fontSize=7, alignment=2, textColor=colors.HexColor("#94A3B8"))

    el = []
    el.append(Paragraph(f"<b>{ragione_sociale}</b>", sub_style))
    el.append(Paragraph(f"<b>{titolo}</b>", h_style))
    if sottotitolo:
        el.append(Paragraph(sottotitolo, sub_style))
    if filtri_attivi:
        parts = []
        for k, v in filtri_attivi.items():
            if v not in (None, "", "all"):
                parts.append(f"<b>{k}</b>: {v}")
        if parts:
            el.append(Paragraph(" &nbsp;·&nbsp; ".join(parts), chip_style))
    el.append(Spacer(1, 4 * mm))

    data = [list(headers)] + [[_fmt(c) for c in r] for r in rows]
    page_w = (297 if landscape_mode else 210) - 20  # mm util
    if col_widths_mm:
        col_w = [w * mm for w in col_widths_mm]
    else:
        col_w = [(page_w / len(headers)) * mm] * len(headers)

    tbl = Table(data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.HexColor("#0F172A")),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.15, colors.HexColor("#E2E8F0")),
    ]))
    el.append(tbl)
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')} · {len(rows)} righe",
        foot_style,
    ))
    doc.build(el)
    buf.seek(0)
    return buf.read()
