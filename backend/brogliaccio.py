"""Generazione PDF Brogliaccio (prima nota) formato giornaliero."""
from __future__ import annotations
import io
from datetime import date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)


def _fmt(n: float | None) -> str:
    if n is None or n == 0:
        return ""
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def genera_brogliaccio_pdf(db, data_giorno: str, conti: list[dict],
                                 ragione_sociale: str = "Assicura - Gestione Agenzia") -> bytes:
    """Genera il PDF del Brogliaccio del giorno.

    Args:
        data_giorno: 'YYYY-MM-DD'
        conti: lista di Conti Cassa attivi (dict con id, nome, saldo_precedente)
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    h_style = ParagraphStyle("h", parent=styles["Heading1"], fontSize=14, alignment=1, spaceAfter=2)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, alignment=1, textColor=colors.HexColor("#475569"))
    elements = []
    elements.append(Paragraph(f"<b>{ragione_sociale}</b>", h_style))
    d = date.fromisoformat(data_giorno)
    elements.append(Paragraph(f"Brogliaccio del {d.strftime('%d-%m-%Y')}", sub_style))
    elements.append(Spacer(1, 4 * mm))

    # carica movimenti del giorno con join polizza e anagrafica
    movs = await db.movimenti.find(
        {"data_movimento": data_giorno}, {"_id": 0}
    ).sort("data_registrazione", 1).to_list(2000)

    # arricchimento descrizioni
    pol_ids = list({m["polizza_id"] for m in movs if m.get("polizza_id")})
    ana_ids = list({m["anagrafica_id"] for m in movs if m.get("anagrafica_id")})
    com_ids = list({m["compagnia_id"] for m in movs if m.get("compagnia_id")})
    polizze = {p["id"]: p async for p in db.polizze.find({"id": {"$in": pol_ids}},
                                                         {"_id": 0, "id": 1, "numero_polizza": 1, "compagnia_id": 1})}
    anagrafiche = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}},
                                                                 {"_id": 0, "id": 1, "ragione_sociale": 1})}
    compagnie = {c["id"]: c async for c in db.compagnie.find({"id": {"$in": com_ids + [p.get("compagnia_id") for p in polizze.values()]}},
                                                             {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1})}

    conti_attivi = [c for c in conti if c.get("attivo", True)]
    # header colonne
    base_headers = ["Descrizione", "Totale", "Provv", "Saldo", "Crediti", "Spese"]
    bank_headers = [c["nome"].upper()[:14] for c in conti_attivi]
    headers = base_headers + bank_headers

    # totalizzatori
    tot_totale = tot_provv = tot_saldo = tot_crediti = tot_spese = 0.0
    tot_per_conto = {c["id"]: 0.0 for c in conti_attivi}

    rows = [headers]
    for m in movs:
        pol = polizze.get(m.get("polizza_id", "")) or {}
        ana = anagrafiche.get(m.get("anagrafica_id") or pol.get("contraente_id", "")) or {}
        com = compagnie.get(m.get("compagnia_id") or pol.get("compagnia_id", "")) or {}
        desc_parts = []
        if pol.get("numero_polizza"):
            desc_parts.append(f"N. {pol['numero_polizza']}")
        if ana.get("ragione_sociale"):
            desc_parts.append(ana["ragione_sociale"])
        if com.get("ragione_sociale"):
            desc_parts.append(com["ragione_sociale"].upper().split()[0])
        if not desc_parts:
            desc_parts.append(m.get("descrizione", "")[:60])
        desc = " - ".join(desc_parts)[:55]
        importo = m.get("importo", 0.0)
        prov = m.get("provvigioni", 0.0) or 0.0
        # tipologia
        if m.get("categoria") == "incasso_premio":
            totale = importo; saldo = importo - prov; crediti = 0.0; spese = 0.0
            tot_totale += totale; tot_saldo += saldo; tot_provv += prov
        elif m.get("categoria") in ("rimborso_cliente", "spese_amministrative", "pagamento_compagnia"):
            totale = 0.0; saldo = 0.0; crediti = 0.0; spese = importo
            tot_spese += spese
        elif m.get("categoria") == "provvigioni":
            totale = 0.0; saldo = 0.0; crediti = importo; spese = 0.0
            tot_crediti += crediti
        else:
            totale = importo if m.get("tipo") == "entrata" else 0.0
            saldo = totale
            crediti = 0.0; spese = importo if m.get("tipo") == "uscita" else 0.0
            if totale: tot_totale += totale; tot_saldo += saldo
            if spese: tot_spese += spese
        # conto cassa
        bank_cells = []
        signed_amount = importo if m.get("tipo") == "entrata" else -importo
        for c in conti_attivi:
            if m.get("conto_cassa_id") == c["id"]:
                bank_cells.append(_fmt(signed_amount))
                tot_per_conto[c["id"]] += signed_amount
            else:
                bank_cells.append("")
        rows.append([desc] + [_fmt(totale), _fmt(prov), _fmt(saldo), _fmt(crediti), _fmt(spese)] + bank_cells)

    rows.append(
        ["TOTALE GIORNATA",
         _fmt(tot_totale), _fmt(tot_provv), _fmt(tot_saldo),
         _fmt(tot_crediti), _fmt(tot_spese)]
        + [_fmt(tot_per_conto[c["id"]]) for c in conti_attivi]
    )

    n_cols = len(headers)
    col_w = [55 * mm] + [16 * mm] * 5 + [max(14 * mm, (240 * mm) / max(1, len(bank_headers)))] * len(bank_headers)
    if sum(col_w) > 280 * mm:
        # comprimi banche
        free = 280 * mm - 55 * mm - 16 * mm * 5
        col_w = [55 * mm] + [16 * mm] * 5 + [free / len(bank_headers)] * len(bank_headers) if bank_headers else col_w[:6]

    tbl = Table(rows, colWidths=col_w[:n_cols], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#0F172A")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E0F2FE")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0369A1")),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 6 * mm))

    # Riepilogo conti
    elements.append(Paragraph("<b>Riepilogo conti</b>", styles["Heading4"]))
    riep_rows = [["Conto", "Imp. precedente", "Imp. giornata", "Totale periodo"]]
    for c in conti_attivi:
        prec = c.get("saldo_iniziale", 0.0)
        gg = tot_per_conto[c["id"]]
        riep_rows.append([c["nome"], _fmt(prec), _fmt(gg), _fmt(prec + gg)])
    riep = Table(riep_rows, colWidths=[80 * mm, 40 * mm, 40 * mm, 40 * mm])
    riep.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
    ]))
    elements.append(riep)

    doc.build(elements)
    buf.seek(0)
    return buf.read()
