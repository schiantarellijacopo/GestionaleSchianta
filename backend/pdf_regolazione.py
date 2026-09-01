"""Genera la 'Lettera di Richiesta Dati per Regolazione Premio' in PDF.

Viene inviata al contraente alla scadenza del periodo assicurato per richiedere
i dati consuntivi (fatturato / monte mercedi / numero addetti / ricavi) necessari
al calcolo della regolazione del premio.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


BASE_LABELS = {
    "fatturato": "il fatturato",
    "mercedi": "il monte mercedi (retribuzioni lorde corrisposte)",
    "addetti": "il numero di addetti/dipendenti",
    "ricavi": "i ricavi",
    "altro": "i dati consuntivi",
}


def _fmt_data(s: Optional[str]) -> str:
    if not s:
        return ""
    try:
        return date.fromisoformat(s[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return s


def genera_lettera_regolazione(
    *,
    azienda: dict,
    contraente_nome: str,
    contraente_indirizzo: str,
    numero_polizza: str,
    compagnia: str,
    ramo: str,
    effetto: str,
    scadenza: str,
    base_tipo: Optional[str],
    periodo: str,
    testo_extra: Optional[str] = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=10.5, leading=15)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#64748b"))
    right = ParagraphStyle("right", parent=body, alignment=2)
    h_ag = ParagraphStyle("h_ag", parent=ss["Normal"], fontSize=13, leading=16, textColor=colors.HexColor("#0c4a6e"), spaceAfter=2)

    els: list = []

    # Intestazione agenzia
    ag_nome = azienda.get("ragione_sociale") or azienda.get("nome") or "Agenzia"
    ag_riga2 = " · ".join([x for x in [
        azienda.get("indirizzo"),
        f"{azienda.get('cap','')} {azienda.get('citta','')}".strip(),
    ] if x])
    ag_riga3 = " · ".join([x for x in [
        f"Tel. {azienda.get('telefono')}" if azienda.get("telefono") else None,
        azienda.get("email"),
        f"P.IVA {azienda.get('partita_iva')}" if azienda.get("partita_iva") else None,
    ] if x])
    els.append(Paragraph(ag_nome, h_ag))
    if ag_riga2:
        els.append(Paragraph(ag_riga2, small))
    if ag_riga3:
        els.append(Paragraph(ag_riga3, small))
    els.append(Spacer(1, 10 * mm))

    # Destinatario
    els.append(Paragraph("Spett.le", body))
    els.append(Paragraph(f"<b>{contraente_nome}</b>", body))
    if contraente_indirizzo:
        els.append(Paragraph(contraente_indirizzo, body))
    els.append(Spacer(1, 6 * mm))
    els.append(Paragraph(f"Luogo e data: ______________, {date.today().strftime('%d/%m/%Y')}", right))
    els.append(Spacer(1, 6 * mm))

    # Oggetto
    els.append(Paragraph(
        f"<b>Oggetto: Richiesta dati per la regolazione del premio — Polizza n. {numero_polizza}</b>",
        body,
    ))
    els.append(Spacer(1, 4 * mm))

    # Tabella dati polizza
    dati = [
        ["Numero polizza", numero_polizza or "—"],
        ["Compagnia", compagnia or "—"],
        ["Ramo / Prodotto", ramo or "—"],
        ["Periodo di riferimento", f"{_fmt_data(effetto)} — {_fmt_data(scadenza)}" if effetto or scadenza else (periodo or "—")],
    ]
    t = Table(dati, colWidths=[55 * mm, 105 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
    ]))
    els.append(t)
    els.append(Spacer(1, 6 * mm))

    base_lbl = BASE_LABELS.get(base_tipo or "altro", "i dati consuntivi")
    corpo = (
        f"Gentile Cliente,<br/><br/>"
        f"con riferimento alla polizza in oggetto, soggetta a <b>regolazione del premio</b>, "
        f"La invitiamo a comunicarci <b>{base_lbl}</b> relativi al periodo assicurativo "
        f"{_fmt_data(effetto)} — {_fmt_data(scadenza)}, così da procedere al conguaglio del premio "
        f"come previsto dalle condizioni contrattuali.<br/><br/>"
        f"La preghiamo di trasmettere la documentazione (dichiarazione, bilancio o modello INAIL) "
        f"entro <b>15 giorni</b> dal ricevimento della presente. In assenza di riscontro la Compagnia "
        f"potrà applicare la regolazione sulla base dei massimali contrattualmente previsti.<br/><br/>"
    )
    if testo_extra:
        corpo += testo_extra.replace("\n", "<br/>") + "<br/><br/>"
    corpo += "Restiamo a disposizione per ogni chiarimento e cogliamo l'occasione per porgere cordiali saluti."
    els.append(Paragraph(corpo, body))
    els.append(Spacer(1, 16 * mm))
    els.append(Paragraph(f"{ag_nome}", right))
    els.append(Paragraph("__________________________", right))

    doc.build(els)
    return buf.getvalue()
