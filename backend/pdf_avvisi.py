"""Generazione PDF avvisi di scadenza titoli — un avviso per contraente.

Refactor: la funzione monolitica `genera_pdf_avvisi` è stata spezzata in
helper testabili (formatting, intestazione, corpo, tabella).
"""
from __future__ import annotations
import io
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def _fmt_data(s: str | None) -> str:
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
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Stili
# ---------------------------------------------------------------------------
def _build_styles() -> dict:
    styles = getSampleStyleSheet()
    return {
        "body": ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=13),
        "title": ParagraphStyle("ttl", parent=styles["Heading2"], fontSize=13, spaceAfter=10),
        "small": ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                                textColor=colors.HexColor("#666")),
    }


# ---------------------------------------------------------------------------
# Sezioni della lettera
# ---------------------------------------------------------------------------
def _intestazione_agenzia(azienda: dict, st: dict) -> list:
    """Blocco header con ragione sociale + indirizzo + telefono dell'agenzia."""
    out: list = []
    ragione = azienda.get("ragione_sociale") or ""
    if not ragione:
        return out
    out.append(Paragraph(f"<b>{ragione}</b>", st["body"]))
    via = azienda.get("indirizzo") or ""
    if via:
        out.append(Paragraph(via, st["small"]))
    tel = azienda.get("telefono") or ""
    if tel:
        out.append(Paragraph(f"Tel: {tel}", st["small"]))
    out.append(Spacer(1, 10 * mm))
    return out


def _destinatario(g: dict, st: dict) -> Paragraph:
    """Blocco intestazione cliente, right-aligned."""
    nome = g.get("contraente_nome") or ""
    indirizzo = g.get("contraente_indirizzo") or ""
    email = g.get("contraente_email") or ""
    parts = [
        "<para align='right'><b>Spett.le</b><br/>",
        f"<b>{nome}</b><br/>",
    ]
    if indirizzo:
        parts.append(f"{indirizzo}<br/>")
    if email:
        parts.append(f"{email}<br/>")
    parts.append("</para>")
    return Paragraph("".join(parts), st["body"])


def _corpo_lettera(corpo: str, st: dict) -> list:
    """Trasforma il corpo testo in una lista di Paragraph rispettando i double-newline."""
    out: list = []
    for paragrafo in (corpo or "").split("\n\n"):
        out.append(Paragraph(paragrafo.replace("\n", "<br/>"), st["body"]))
        out.append(Spacer(1, 3 * mm))
    return out


def _modalita_pagamento(azienda: dict, st: dict) -> list:
    """Frase con IBAN/modalità di pagamento."""
    ragione = azienda.get("ragione_sociale") or ""
    iban = azienda.get("iban") or ""
    if not (ragione or iban):
        return []
    mod = "Il pagamento può essere effettuato presso la nostra sede"
    if iban:
        mod += f" oppure tramite bonifico su <b>IBAN {iban}</b>"
    mod += f" intestato a <b>{ragione}</b>."
    return [Spacer(1, 3 * mm), Paragraph(mod, st["body"])]


def _build_riga_titolo(t: dict) -> tuple[list, float]:
    """Ritorna (riga_tabella, importo)."""
    rischio = (t.get("prodotto") or t.get("ramo") or "").upper()
    imp = float(t.get("importo_lordo") or 0)
    riga = [
        str(t.get("numero_polizza") or ""), rischio,
        str(t.get("targa") or ""), _fmt_data(t.get("scadenza")), _fmt_eur(imp),
    ]
    return riga, imp


def _stile_tabella_titoli() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#1f2937")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#cccccc")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])


def _tabella_titoli(titoli: list[dict]) -> Table:
    data: list[list] = [["Num. Contratto", "Rischio", "Targa", "Rata del", "Imp. Totale"]]
    totale = 0.0
    for t in titoli:
        riga, imp = _build_riga_titolo(t)
        totale += imp
        data.append(riga)
    data.append(["", "", "", "Totale Complessivo", _fmt_eur(totale)])
    tbl = Table(data, colWidths=[36 * mm, 38 * mm, 28 * mm, 28 * mm, 28 * mm], repeatRows=1)
    tbl.setStyle(_stile_tabella_titoli())
    return tbl


def _lettera_per_gruppo(g: dict, *, azienda: dict, corpo_lettera: str,
                        soggetto: str, st: dict) -> list:
    """Compone l'intera lettera per un singolo contraente."""
    out: list = []
    out.extend(_intestazione_agenzia(azienda, st))
    out.append(_destinatario(g, st))
    out.append(Spacer(1, 8 * mm))
    out.append(Paragraph(f"<b>Oggetto: </b>{soggetto}", st["title"]))
    out.extend(_corpo_lettera(corpo_lettera, st))
    out.extend(_modalita_pagamento(azienda, st))
    out.append(Spacer(1, 6 * mm))
    out.append(_tabella_titoli(g.get("titoli", [])))
    out.append(Spacer(1, 14 * mm))
    out.append(Paragraph("Cordiali saluti,<br/><b>L'Agenzia</b>", st["body"]))
    return out


# ---------------------------------------------------------------------------
# Entrypoint pubblico
# ---------------------------------------------------------------------------
def genera_pdf_avvisi(
    *, gruppi: list[dict], azienda: dict, corpo_lettera: str,
    soggetto: str = "Promemoria pagamento polizza/e in scadenza",
) -> bytes:
    """Genera un PDF con un avviso per ogni contraente in `gruppi`.

    Ogni `gruppo` deve contenere:
      - contraente_nome (str)
      - contraente_indirizzo (str opzionale)
      - contraente_email / contraente_cellulare (opzionali)
      - titoli: lista dict con numero_polizza, prodotto/ramo, targa, scadenza, importo_lordo.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=soggetto,
    )
    st = _build_styles()
    story: list = []
    for idx, g in enumerate(gruppi):
        if idx > 0:
            story.append(PageBreak())
        story.extend(_lettera_per_gruppo(
            g, azienda=azienda, corpo_lettera=corpo_lettera,
            soggetto=soggetto, st=st,
        ))
    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
