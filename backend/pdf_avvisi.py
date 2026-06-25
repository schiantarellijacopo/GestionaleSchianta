"""Generazione PDF avvisi di scadenza titoli — un avviso per contraente."""
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


def _fmt_data(s: str | None) -> str:
    if not s:
        return ""
    try:
        return date.fromisoformat(s[:10]).strftime("%d-%m-%Y")
    except Exception:
        return s


def _fmt_eur(n: float | int | None) -> str:
    try:
        v = float(n or 0)
    except Exception:
        v = 0
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def genera_pdf_avvisi(
    *, gruppi: list[dict], azienda: dict, corpo_lettera: str,
    soggetto: str = "Promemoria pagamento polizza/e in scadenza",
) -> bytes:
    """Genera un PDF con un avviso per ogni contraente in `gruppi`.

    Ogni `gruppo` deve contenere:
      - contraente_nome (str)
      - contraente_indirizzo (str opzionale)
      - contraente_email / contraente_cellulare (opzionali)
      - titoli: lista dict con: numero_polizza, prodotto/ramo, targa, scadenza, importo_lordo
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=soggetto,
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=13)
    title_st = ParagraphStyle("ttl", parent=styles["Heading2"], fontSize=13, spaceAfter=10)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#666"))

    story: list = []
    ragione_az = azienda.get("ragione_sociale") or ""
    via_az = azienda.get("indirizzo") or ""
    iban = azienda.get("iban") or ""
    tel_az = azienda.get("telefono") or ""

    for idx, g in enumerate(gruppi):
        if idx > 0:
            story.append(PageBreak())
        # Intestazione agenzia (top-left)
        if ragione_az:
            story.append(Paragraph(f"<b>{ragione_az}</b>", body))
            if via_az:
                story.append(Paragraph(via_az, small))
            if tel_az:
                story.append(Paragraph(f"Tel: {tel_az}", small))
            story.append(Spacer(1, 10 * mm))
        # Destinatario (top-right destra-allineato in box)
        intestazione_cliente = (
            f"<para align='right'><b>Spett.le</b><br/>"
            f"<b>{g.get('contraente_nome') or ''}</b><br/>"
            + (f"{g.get('contraente_indirizzo')}<br/>" if g.get("contraente_indirizzo") else "")
            + (f"{g.get('contraente_email') or ''}<br/>" if g.get("contraente_email") else "")
            + "</para>"
        )
        story.append(Paragraph(intestazione_cliente, body))
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(f"<b>Oggetto: </b>{soggetto}", title_st))

        # Corpo lettera
        for paragrafo in (corpo_lettera or "").split("\n\n"):
            story.append(Paragraph(paragrafo.replace("\n", "<br/>"), body))
            story.append(Spacer(1, 3 * mm))

        # Modalità pagamento
        if ragione_az or iban:
            story.append(Spacer(1, 3 * mm))
            mod_pag = (
                "Il pagamento può essere effettuato presso la nostra sede"
                + (f" oppure tramite bonifico su <b>IBAN {iban}</b>" if iban else "")
                + f" intestato a <b>{ragione_az}</b>."
            )
            story.append(Paragraph(mod_pag, body))

        # Tabella titoli
        story.append(Spacer(1, 6 * mm))
        data: list[list] = [["Num. Contratto", "Rischio", "Targa", "Rata del", "Imp. Totale"]]
        totale = 0.0
        for t in g.get("titoli", []):
            rischio = (t.get("prodotto") or t.get("ramo") or "").upper()
            imp = float(t.get("importo_lordo") or 0)
            totale += imp
            data.append([
                str(t.get("numero_polizza") or ""),
                rischio,
                str(t.get("targa") or ""),
                _fmt_data(t.get("scadenza")),
                _fmt_eur(imp),
            ])
        data.append(["", "", "", "Totale Complessivo", _fmt_eur(totale)])

        tbl = Table(
            data,
            colWidths=[36 * mm, 38 * mm, 28 * mm, 28 * mm, 28 * mm],
            repeatRows=1,
        )
        tbl.setStyle(TableStyle([
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
        ]))
        story.append(tbl)

        # Firma
        story.append(Spacer(1, 14 * mm))
        story.append(Paragraph("Cordiali saluti,<br/><b>L'Agenzia</b>", body))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
