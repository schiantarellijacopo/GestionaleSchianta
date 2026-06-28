"""Generazione PDF "Avviso di scadenza" (sollecito al cliente).

Layout ispirato all'esempio caricato dal cliente (Assicurazioni Schiantarelli):
  - Header: logo + nome agenzia (sinistra), destinatario (destra)
  - Corpo: testo intro (configurabile via TemplateModello)
  - Tabella polizze/titoli: Num.Contratto · Rischio · Targa · Rata del · Importo
  - Totale Complessivo
  - Sezioni dinamiche (callout commerciali) caricate da TemplateModello.sezioni
  - Footer: filiali

Tutti i testi (intro, sezioni callout, footer) sono editabili dalla
libreria "Gestioni Modelli" e sostituiti via placeholder.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether,
)


BLUE = colors.HexColor("#1d4e89")
DARK = colors.HexColor("#1f2937")
GREY = colors.HexColor("#475569")
LIGHT = colors.HexColor("#e2e8f0")


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
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _render_placeholders(s: str, ctx: dict) -> str:
    if not s:
        return ""
    out = s
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", "" if v is None else str(v))
    return out


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=18, leading=22,
                              textColor=DARK, spaceAfter=2, fontName="Helvetica-Bold"),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11, leading=14,
                              textColor=DARK, spaceAfter=4, fontName="Helvetica-Bold"),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=13,
                                textColor=DARK, alignment=0),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=8, leading=10,
                                 textColor=GREY),
        "intro": ParagraphStyle("intro", parent=base["BodyText"], fontSize=10, leading=14,
                                  textColor=DARK),
        "callout": ParagraphStyle("callout", parent=base["BodyText"], fontSize=10, leading=14,
                                    textColor=DARK, fontName="Helvetica-Bold"),
        "footer_h": ParagraphStyle("foot_h", parent=base["BodyText"], fontSize=9, leading=12,
                                     textColor=DARK, fontName="Helvetica-Bold"),
        "footer": ParagraphStyle("foot", parent=base["BodyText"], fontSize=8, leading=10,
                                   textColor=GREY),
    }


def generate_avviso_pdf(
    *,
    azienda: dict,
    destinatario: dict,
    righe: list[dict],
    template: Optional[dict] = None,
) -> bytes:
    """Genera il PDF Avviso di scadenza.

    Args:
        azienda: ``AziendaConfig`` (ragione_sociale, indirizzo, telefono, IBAN, ecc.)
        destinatario: ``{ragione_sociale, indirizzo, cap, comune, provincia, codice_fiscale}``
        righe: lista titoli/polizze con campi
               ``{numero_contratto, rischio, targa, rata_del, importo}``
        template: ``TemplateModello`` (tipo='pdf_avviso') con:
                  - ``oggetto`` = saluto (es. "Gentile Cliente,")
                  - ``corpo`` = intro paragrafo principale
                  - ``sezioni`` = lista di {titolo, contenuto, ordine, attiva}
    """
    template = template or {}
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title="Avviso di scadenza",
    )
    story: list = []

    # Placeholder context per sostituzioni
    totale = sum(float(r.get("importo") or 0) for r in righe)
    ctx = {
        "cliente_nome": destinatario.get("ragione_sociale") or "",
        "cliente_indirizzo": destinatario.get("indirizzo") or "",
        "cliente_comune": destinatario.get("comune") or "",
        "cliente_cap": destinatario.get("cap") or "",
        "cliente_provincia": destinatario.get("provincia") or "",
        "azienda_nome": azienda.get("ragione_sociale") or "",
        "azienda_iban": azienda.get("iban") or "",
        "azienda_telefono": azienda.get("telefono") or "",
        "azienda_email": azienda.get("smtp_from") or azienda.get("smtp_user") or "",
        "totale": _fmt_eur(totale),
        "data_oggi": date.today().strftime("%d-%m-%Y"),
        "numero_titoli": str(len(righe)),
    }

    # ===== HEADER =====
    nome_agenzia = azienda.get("ragione_sociale") or "Agenzia Assicurativa"
    motto = azienda.get("note_footer_stampe") or ""
    head_left = [
        Paragraph(f"<b>{nome_agenzia}</b>", st["h1"]),
    ]
    if motto:
        head_left.append(Paragraph(f"<i>{motto[:80]}</i>", st["small"]))

    dest_lines = [Paragraph(f"<b>{ctx['cliente_nome']}</b>", st["body"])]
    if ctx["cliente_indirizzo"]:
        dest_lines.append(Paragraph(ctx["cliente_indirizzo"], st["body"]))
    if ctx["cliente_cap"] or ctx["cliente_comune"]:
        dest_lines.append(Paragraph(
            f"{ctx['cliente_cap']} - {ctx['cliente_comune']} {('- ' + ctx['cliente_provincia']) if ctx['cliente_provincia'] else ''}",
            st["body"],
        ))

    header_tbl = Table(
        [[head_left, dest_lines]],
        colWidths=[80 * mm, 90 * mm],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6 * mm))

    # ===== INTRO =====
    saluto_raw = (template.get("oggetto") or "Gentile Cliente,").strip()
    saluto = _render_placeholders(saluto_raw, ctx)
    intro_raw = template.get("corpo") or (
        "riteniamo opportuno ricordarLe la scadenza delle rate di premio relative "
        "alle coperture assicurative i cui termini risultano sotto evidenziati.\n\n"
        "Per il rinnovo e per verificare insieme che tutte le garanzie corrispondano "
        "alle Sue attuali esigenze, La aspettiamo in Agenzia, dove continuerà a godere "
        "dell'attenzione e del servizio che dedichiamo ai nostri Clienti.\n\n"
        "La ringraziamo per l'attenzione e Le inviamo i nostri migliori saluti."
    )
    intro = _render_placeholders(intro_raw, ctx)

    story.append(Paragraph(f"<b>{saluto}</b>", st["body"]))
    story.append(Spacer(1, 2 * mm))
    for paragrafo in intro.split("\n\n"):
        story.append(Paragraph(paragrafo.replace("\n", "<br/>"), st["body"]))
        story.append(Spacer(1, 2 * mm))

    # ===== PAGAMENTO =====
    if ctx["azienda_iban"]:
        story.append(Paragraph(
            "Il pagamento del/i premio/i potrà essere effettuato presso la nostra sede o tramite bonifico:",
            st["body"],
        ))
        story.append(Paragraph(
            f"<b>{ctx['azienda_nome']}</b><br/><b>IBAN: {ctx['azienda_iban']}</b>",
            st["body"],
        ))
        story.append(Spacer(1, 4 * mm))

    # ===== TABELLA POLIZZE =====
    head = ["Num.Contratto", "Rischio", "Targa", "Rata del", "Imp.Totale"]
    body = [head]
    for r in righe:
        body.append([
            str(r.get("numero_contratto") or ""),
            str(r.get("rischio") or "")[:40],
            str(r.get("targa") or ""),
            _fmt_data(r.get("rata_del")),
            _fmt_eur(r.get("importo")),
        ])
    body.append(["", "", "", "Totale Complessivo", _fmt_eur(totale)])

    tbl = Table(body, colWidths=[34 * mm, 50 * mm, 24 * mm, 28 * mm, 28 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        # Body
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LIGHT),
        # Totale (ultima riga)
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
        ("ALIGN", (3, -1), (3, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6 * mm))

    # ===== SEZIONI DINAMICHE (callout commerciali) =====
    sezioni = template.get("sezioni") or []
    for sez in sorted(sezioni, key=lambda x: x.get("ordine", 0)):
        if not sez.get("attiva", True):
            continue
        titolo = _render_placeholders(sez.get("titolo") or "", ctx)
        contenuto = _render_placeholders(sez.get("contenuto") or "", ctx)
        block = []
        if titolo:
            block.append(Paragraph(f"<b>{titolo}</b>", st["callout"]))
            block.append(Spacer(1, 1 * mm))
        if contenuto:
            for para in contenuto.split("\n\n"):
                block.append(Paragraph(para.replace("\n", "<br/>"), st["body"]))
                block.append(Spacer(1, 1.5 * mm))
        if block:
            story.append(KeepTogether(block))
            story.append(Spacer(1, 3 * mm))

    # ===== FOOTER =====
    footer_text = template.get("note") or azienda.get("note_footer_stampe")
    if footer_text:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(footer_text, st["footer"]))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
