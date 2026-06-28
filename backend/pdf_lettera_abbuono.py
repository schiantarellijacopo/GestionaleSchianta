"""Generazione PDF "Lettera di Abbuono" per documentare uno sconto applicato
in fase di incasso titolo. Supporta firma operatore + firma cliente (PNG b64).
"""
from __future__ import annotations
import base64
import io
from datetime import date
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
)


def _fmt_data(s: Optional[str]) -> str:
    if not s:
        return ""
    try:
        return date.fromisoformat(s[:10]).strftime("%d-%m-%Y")
    except (TypeError, ValueError):
        return s


def _fmt_eur(n: float | int | None) -> str:
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        v = 0
    return f"€ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _decode_b64_png(b64: Optional[str]) -> Optional[bytes]:
    """Estrae i byte PNG da una data-URL `data:image/png;base64,...` o b64 puro."""
    if not b64:
        return None
    try:
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        return base64.b64decode(b64)
    except Exception:
        return None


def _firma_box(name: str, b64: Optional[str], data_at: Optional[str], st: dict) -> Table:
    """Crea un riquadro firma (immagine se presente, altrimenti spazio vuoto)."""
    cell_img: object
    img_bytes = _decode_b64_png(b64)
    if img_bytes:
        try:
            cell_img = RLImage(io.BytesIO(img_bytes), width=70 * mm, height=22 * mm)
        except Exception:
            cell_img = Paragraph("&nbsp;", st["body"])
    else:
        cell_img = Paragraph("&nbsp;", st["body"])

    sotto = []
    sotto.append(Paragraph(f"<b>{name}</b>", st["small"]))
    if data_at:
        sotto.append(Paragraph(f"Data: {_fmt_data(data_at)}", st["small"]))
    inner = [[cell_img]] + [[s] for s in sotto]
    t = Table(inner, colWidths=[75 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor("#888")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def generate_lettera_abbuono(
    *,
    azienda: dict,
    lettera: dict,
    titolo: dict,
    polizza: Optional[dict],
    anagrafica: Optional[dict],
    compagnia: Optional[dict],
    operatore: Optional[dict] = None,
) -> bytes:
    """Genera il PDF della lettera di abbuono. `lettera` contiene firme se presenti."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title="Lettera di abbuono",
    )
    styles = getSampleStyleSheet()
    st = {
        "body": ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=13),
        "title": ParagraphStyle("ttl", parent=styles["Heading2"], fontSize=14,
                                 spaceAfter=8, textColor=colors.HexColor("#0c4a6e")),
        "small": ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                                  textColor=colors.HexColor("#555"), leading=10),
        "right": ParagraphStyle("right", parent=styles["Normal"], fontSize=9, alignment=2),
    }
    flow: list = []

    # Intestazione agenzia con logo (branding condiviso)
    try:
        from pdf_branding import header_branding
        flow.extend(header_branding(azienda or {}, with_motto=False))
    except Exception:
        # Fallback: testo semplice
        ragione = (azienda or {}).get("ragione_sociale") or ""
        if ragione:
            flow.append(Paragraph(f"<b>{ragione}</b>", st["body"]))
    indirizzo = (azienda or {}).get("indirizzo") or ""
    if indirizzo:
        flow.append(Paragraph(indirizzo, st["small"]))
    tel = (azienda or {}).get("telefono") or ""
    if tel:
        flow.append(Paragraph(f"Tel: {tel}", st["small"]))
    flow.append(Spacer(1, 8 * mm))

    # Data e luogo
    data_inc = lettera.get("data_incasso") or date.today().isoformat()
    flow.append(Paragraph(f"<para align='right'>{_fmt_data(data_inc)}</para>", st["body"]))
    flow.append(Spacer(1, 4 * mm))

    # Destinatario (cliente)
    nome = (anagrafica or {}).get("denominazione") \
        or " ".join(filter(None, [(anagrafica or {}).get("cognome"), (anagrafica or {}).get("nome")])).strip() \
        or "—"
    indir_cli = (anagrafica or {}).get("indirizzo") or ""
    flow.append(Paragraph("<b>Spett.le</b>", st["body"]))
    flow.append(Paragraph(f"<b>{nome}</b>", st["body"]))
    if indir_cli:
        flow.append(Paragraph(indir_cli, st["small"]))
    flow.append(Spacer(1, 8 * mm))

    # Titolo
    flow.append(Paragraph("LETTERA DI ABBUONO", st["title"]))
    flow.append(Spacer(1, 4 * mm))

    # Corpo
    num_pol = (polizza or {}).get("numero_polizza") or "—"
    rag_compagnia = (compagnia or {}).get("ragione_sociale") or "—"
    ramo = (polizza or {}).get("ramo") or (titolo or {}).get("ramo") or "—"
    importo_lordo = float(lettera.get("importo_lordo") or 0)
    importo_pagato = float(lettera.get("importo_pagato") or 0)
    importo_sconto = float(lettera.get("importo_sconto") or 0)
    motivo = lettera.get("motivo_sconto") or "Sconto commerciale concordato"

    corpo = (
        f"Con la presente comunichiamo di aver concesso un <b>abbuono</b> "
        f"di <b>{_fmt_eur(importo_sconto)}</b> sul premio assicurativo "
        f"relativo alla polizza n. <b>{num_pol}</b> "
        f"(ramo: {ramo} — compagnia: {rag_compagnia})."
    )
    flow.append(Paragraph(corpo, st["body"]))
    flow.append(Spacer(1, 4 * mm))

    # Tabella riepilogo importi
    tab_data = [
        ["Premio lordo", _fmt_eur(importo_lordo)],
        ["Importo pagato dal cliente", _fmt_eur(importo_pagato)],
        ["Abbuono concesso", _fmt_eur(importo_sconto)],
        ["Motivo", motivo],
    ]
    tab = Table(tab_data, colWidths=[60 * mm, 110 * mm])
    tab.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#0c4a6e")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f9ff")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, 2), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(tab)
    flow.append(Spacer(1, 8 * mm))

    flow.append(Paragraph(
        "Lo sconto è formalmente accordato dall'agenzia. Il cliente ne accetta "
        "i termini sottoscrivendo la presente.",
        st["body"],
    ))
    flow.append(Spacer(1, 14 * mm))

    # Firme
    op_nome = lettera.get("firma_operatore_nome") or (operatore or {}).get("name") or "L'Operatore"
    cli_nome = lettera.get("firma_cliente_nome") or nome
    firme = Table(
        [[
            _firma_box(f"Firma Operatore\n({op_nome})", lettera.get("firma_operatore_b64"),
                       lettera.get("firma_operatore_at"), st),
            _firma_box(f"Firma Cliente\n({cli_nome})", lettera.get("firma_cliente_b64"),
                       lettera.get("firma_cliente_at"), st),
        ]],
        colWidths=[85 * mm, 85 * mm],
    )
    firme.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    flow.append(firme)

    doc.build(flow)
    return buf.getvalue()
