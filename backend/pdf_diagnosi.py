"""Generatore PDF delle diagnosi cliente:
- Diagnosi del Reddito (17 pagine)
- Progetto Futuro Senza Sorprese (metodo AZZOB ISO 31000, ~25 pagine)

Stile ispirato ai report HubSicura.
"""
from __future__ import annotations
import io
from datetime import datetime, date
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
    KeepTogether, Image, HRFlowable,
)


# === Palette ===
PRIMARY = colors.HexColor("#0369A1")   # sky-700
ACCENT = colors.HexColor("#0EA5E9")    # sky-500
DARK = colors.HexColor("#0F172A")
MID = colors.HexColor("#475569")
LIGHT = colors.HexColor("#F1F5F9")
ROSE = colors.HexColor("#BE123C")
EMERALD = colors.HexColor("#047857")
AMBER = colors.HexColor("#B45309")


def _fmt_eur(v) -> str:
    if v is None:
        return "—"
    try:
        return f"€ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)


def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}%".replace(".", ",")
    except Exception:
        return str(v)


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1_cover": ParagraphStyle("h1c", parent=base["Title"], fontSize=28, leading=34, alignment=TA_LEFT, textColor=PRIMARY, spaceAfter=8),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=20, leading=24, textColor=DARK, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=14, leading=18, textColor=PRIMARY, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=11, leading=14, textColor=DARK, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14, textColor=DARK, spaceAfter=6),
        "body_just": ParagraphStyle("body_just", parent=base["Normal"], fontSize=10, leading=14, alignment=TA_JUSTIFY, textColor=DARK, spaceAfter=6),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=8, textColor=MID),
        "caption": ParagraphStyle("caption", parent=base["Normal"], fontSize=8, textColor=MID, alignment=TA_CENTER),
        "footer": ParagraphStyle("footer", parent=base["Normal"], fontSize=7, textColor=MID, alignment=TA_LEFT),
        "kpi_label": ParagraphStyle("kpil", parent=base["Normal"], fontSize=8, textColor=MID, alignment=TA_CENTER),
        "kpi_value": ParagraphStyle("kpiv", parent=base["Normal"], fontSize=16, textColor=PRIMARY, alignment=TA_CENTER, spaceAfter=0),
        "big_amount": ParagraphStyle("ba", parent=base["Normal"], fontSize=22, textColor=ROSE, alignment=TA_CENTER, spaceAfter=4),
        "callout": ParagraphStyle("co", parent=base["Normal"], fontSize=10, textColor=DARK, spaceAfter=6, leftIndent=8),
    }


def _header_footer(canvas, doc, azienda: dict, operatore_nome: str, report_num: str):
    canvas.saveState()
    w, h = A4
    # Footer
    canvas.setFillColor(MID)
    canvas.setFont("Helvetica", 7)
    ind = azienda.get("indirizzo") or ""
    rui = azienda.get("rui") or ""
    email = azienda.get("email") or ""
    ragione = azienda.get("ragione_sociale") or operatore_nome or "Assicura"
    txt = f"{ragione} · {ind} · N° RUI {rui} · {email}"
    canvas.drawString(15 * mm, 10 * mm, txt[:130])
    canvas.drawRightString(w - 15 * mm, 10 * mm, f"{doc.page}  ·  Report {report_num}")
    # Top decorative line
    canvas.setStrokeColor(PRIMARY)
    canvas.setLineWidth(0.8)
    canvas.line(15 * mm, h - 14 * mm, w - 15 * mm, h - 14 * mm)
    canvas.restoreState()


def _kpi_card(label: str, value: str, color=PRIMARY, w=55, h=24) -> Table:
    s = _styles()
    t = Table(
        [[Paragraph(label.upper(), s["kpi_label"])], [Paragraph(value, ParagraphStyle("v", parent=s["kpi_value"], textColor=color))]],
        colWidths=[w * mm], rowHeights=[6 * mm, (h - 6) * mm],
    )
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    return t


def _section_title(text: str, color=PRIMARY) -> Table:
    p = Paragraph(f"<b>{text}</b>", ParagraphStyle("st", fontSize=16, textColor=colors.white, alignment=TA_LEFT, leading=20))
    t = Table([[p]], colWidths=[170 * mm], rowHeights=[12 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def _info_box(text: str, color=AMBER) -> Table:
    p = Paragraph(f"<i>{text}</i>", ParagraphStyle("ib", fontSize=9, textColor=color, leading=12))
    t = Table([[p]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
        ("BOX", (0, 0), (-1, -1), 0.5, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _data_table(headers, rows, col_widths_mm=None, header_color=PRIMARY):
    data = [list(headers)] + [list(r) for r in rows]
    cw = [w * mm for w in col_widths_mm] if col_widths_mm else None
    t = Table(data, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]))
    return t


def _build_doc(buf: io.BytesIO):
    return SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=20 * mm, bottomMargin=18 * mm,
    )


def _eta(data_nascita_iso: str) -> int:
    try:
        d = date.fromisoformat(data_nascita_iso)
        t = date.today()
        return t.year - d.year - (1 if (t.month, t.day) < (d.month, d.day) else 0)
    except Exception:
        return 0


def _next_report_num(now: datetime, anagrafica_id: str) -> str:
    return f"{now.year}/{abs(hash(anagrafica_id)) % 9999:04d}"


# ============================================================
# PDF 1: DIAGNOSI DEL REDDITO
# ============================================================
def genera_diagnosi_reddito(ana: dict, ac: dict, pens: dict, scop: dict, azienda: dict, user: dict) -> bytes:
    s = _styles()
    buf = io.BytesIO()
    doc = _build_doc(buf)
    el = []
    now = datetime.now()
    rnum = _next_report_num(now, ana["id"])
    nome_op = (user.get("name") or "OPERATORE").upper()

    # --- PAGINA 1: COPERTINA ---
    el.append(Spacer(1, 40 * mm))
    el.append(Paragraph("Diagnosi del<br/>reddito", s["h1_cover"]))
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph(f"di <b>{ana.get('nome', '') or ''} {ana.get('cognome', '') or ''}</b>".upper() or ana.get("ragione_sociale", "").upper(), s["h2"]))
    el.append(Spacer(1, 30 * mm))
    el.append(Paragraph("Diagnosi redatta da:", s["small"]))
    el.append(Paragraph(f"<b>{nome_op}</b>", s["h3"]))
    if azienda.get("indirizzo"):
        el.append(Paragraph(azienda["indirizzo"], s["small"]))
    if azienda.get("rui"):
        el.append(Paragraph(f"N° RUI {azienda['rui']}", s["small"]))
    el.append(Spacer(1, 10 * mm))
    el.append(Paragraph(f"Numero Univoco Report {rnum}", s["small"]))
    el.append(PageBreak())

    # --- PAGINA 2: La diagnosi del tuo reddito ---
    el.append(_section_title("La diagnosi del tuo reddito"))
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph(
        "Questa diagnosi analizza il tuo reddito attuale, la tua posizione contributiva e le pensioni "
        "che maturerai. Identifichiamo insieme le scoperture economiche e il capitale necessario a "
        "garantire la stabilità tua e della tua famiglia.",
        s["body_just"],
    ))
    el.append(Spacer(1, 6 * mm))
    el.append(_info_box("Il risultato della simulazione non ha valore certificativo, è solo un'ipotesi. "
                        "Fa fede l'estratto conto contributivo ufficiale INPS."))
    el.append(PageBreak())

    # --- PAGINA 3: Situazione famigliare ---
    el.append(_section_title("La tua situazione famigliare"))
    el.append(Spacer(1, 10 * mm))
    parente = ana.get("parente_di") or []
    nucleo_rows = [(f"{ana.get('nome', '') or ''} {ana.get('cognome', '') or ''}".strip() or ana.get("ragione_sociale", ""), "Cliente (contraente)")]
    nucleo_rows += [(p.get("nome", p.get("anagrafica_id", "")[:8]), (p.get("relazione") or "—").title()) for p in parente]
    el.append(_data_table(["Nome", "Relazione"], nucleo_rows, [85, 85]))
    el.append(PageBreak())

    # --- PAGINA 4: Situazione contributiva ---
    el.append(_section_title("La tua situazione contributiva"))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph("<b>LA TUA SITUAZIONE ATTUALE</b>", s["h3"]))
    tipo_lav = (ac.get("tipo_lavoratore") or ana.get("tipologia_lavoratore") or "—").title()
    el.append(Paragraph(
        f"Attualmente sei un <b>{tipo_lav}</b>, con <b>{int(pens.get('anni_contribuzione', 0))} anni</b> di "
        f"contributi versati e un reddito lordo di <b>{_fmt_eur(ac.get('reddito_lordo_annuo'))}</b>.",
        s["body_just"],
    ))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph("<b>Dettaglio periodi di contribuzione:</b>", s["h3"]))
    periodi = ac.get("periodi_contributivi") or []
    if periodi:
        pr_rows = [(p.get("inizio_periodo", "—"), p.get("fine_periodo") or "in corso", p.get("fondo") or "—",
                    "Sì" if p.get("riscattato") else "No") for p in periodi]
    else:
        pr_rows = [("—", "—", "—", "—")]
    el.append(_data_table(["Dal", "Al", "Cassa", "Riscattato"], pr_rows, [35, 35, 60, 30]))
    el.append(PageBreak())

    # --- PAGINA 5: Storico redditi ---
    el.append(_section_title("La tua situazione contributiva"))
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph("Situazione contributiva dall'entrata in vigore del sistema contributivo:", s["body"]))
    kpi_row = Table([[_kpi_card("Totale versato", _fmt_eur(pens.get("totale_versato")), EMERALD, 80),
                      _kpi_card("Totale rivalutato", _fmt_eur(pens.get("totale_rivalutato")), PRIMARY, 80)]],
                    colWidths=[85 * mm, 85 * mm])
    el.append(kpi_row)
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph("<b>Questa è la tua storia reddituale:</b>", s["h3"]))
    storico = sorted(ac.get("storico_redditi") or [], key=lambda r: r.get("anno", 0), reverse=True)
    rows = [(str(r.get("anno", "—")), _fmt_eur(r.get("reddito")), _fmt_eur(r.get("contributi"))) for r in storico]
    if not rows:
        rows = [("—", "—", "—")]
    el.append(_data_table(["Anno", "Reddito", "Contributi"], rows, [40, 60, 60]))
    el.append(PageBreak())

    # --- PAGINA 6: Prestazioni maturate ---
    el.append(_section_title("Le tue prestazioni maturate"))
    el.append(Spacer(1, 6 * mm))
    oggi = pens.get("pensioni_oggi", {})
    rows = []
    if oggi.get("invalidita"):
        i = oggi["invalidita"]
        rows.append(("Pensione di Invalidità (dal 66% al 99%)", _fmt_eur(i.get("pensione_lorda_mensile")),
                     _fmt_eur(scop.get("invalidita", {}).get("scopertura_annua"))))
    if oggi.get("inabilita"):
        i = oggi["inabilita"]
        rows.append(("Pensione di Inabilità (totale al 100%)", _fmt_eur(i.get("pensione_lorda_mensile")),
                     _fmt_eur(scop.get("inabilita", {}).get("scopertura_annua"))))
    if oggi.get("superstite"):
        i = oggi["superstite"]
        rows.append(("Pensione Superstiti", _fmt_eur(i.get("pensione_lorda_mensile")),
                     _fmt_eur(scop.get("superstiti", {}).get("scopertura_annua"))))
    el.append(_data_table(["Pensione", "Importo mensile", "Diminuzione annua"], rows, [85, 45, 45]))
    el.append(PageBreak())

    # --- PAGINA 7: Riduzione reversibilità ---
    el.append(_section_title("Attenzione: riduzione della pensione di reversibilità"))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        "In caso di redditi del beneficiario superiori alle soglie, la pensione di reversibilità subisce "
        "una riduzione percentuale come da tabella seguente:",
        s["body_just"],
    ))
    el.append(Spacer(1, 4 * mm))
    riduzioni = [
        ("0 €", "23.862,15 €", "Nessuna riduzione", "60%"),
        ("23.862,15 €", "31.816,20 €", "25%", "45%"),
        ("31.816,20 €", "39.769,25 €", "40%", "36%"),
        ("39.769,25 €", "—", "50%", "30%"),
    ]
    el.append(_data_table(["Da", "A", "Riduzione", "% spettante a vedova/o"], riduzioni, [40, 40, 45, 45]))
    el.append(PageBreak())

    # --- PAGINA 8: Riserve ---
    el.append(_section_title("Le tue riserve"))
    el.append(Spacer(1, 10 * mm))
    riserve_liquide = (ac.get("liquidita") or 0) + (ac.get("tfr_maturato") or 0) - (ac.get("debiti") or 0)
    riserve_immobili = sum(float(i.get("valore_commerciale") or 0) for i in (ac.get("immobili") or []))
    riserve_az = sum(float(a.get("valore_ipotetico") or 0) for a in (ac.get("aziende") or []))
    el.append(Table([
        [_kpi_card("Riserve Liquide", _fmt_eur(riserve_liquide), EMERALD if riserve_liquide >= 0 else ROSE, 50)],
        [_kpi_card("Riserve Immobiliari", _fmt_eur(riserve_immobili), PRIMARY, 50)],
        [_kpi_card("Riserve Aziendali", _fmt_eur(riserve_az), AMBER, 50)],
    ], colWidths=[55 * mm], rowHeights=[28 * mm, 28 * mm, 28 * mm]))
    el.append(PageBreak())

    # --- PAGINA 9: Quanto dureranno ---
    el.append(_section_title("Le tue prestazioni maturate · quanto dureranno?"))
    el.append(Spacer(1, 6 * mm))
    durata_rows = []
    for tipo, label in (("invalidita", "Invalidità"), ("inabilita", "Inabilità"), ("superstiti", "Superstiti")):
        sc = scop.get(tipo, {})
        mensile = sc.get("scopertura_mensile") or 0
        if mensile > 0 and riserve_liquide > 0:
            mesi = int(riserve_liquide / mensile)
            anni = mesi // 12
            m_resto = mesi % 12
            durata = f"{anni} anni e {m_resto} mesi"
        else:
            durata = "—"
        durata_rows.append((label, _fmt_eur(sc.get("pensione_mensile")), "—", durata, "—"))
    el.append(_data_table(["Prestazione", "Importo mensile", "R. Liquide", "Durata", "R. Aziendali"],
                          durata_rows, [38, 33, 30, 35, 30]))
    if riserve_liquide <= 0:
        el.append(Spacer(1, 4 * mm))
        el.append(_info_box("Attenzione: non sei in possesso di riserve liquide.", ROSE))
    el.append(PageBreak())

    # --- PAGINA 10: Il tuo fabbisogno ---
    el.append(_section_title("Il tuo fabbisogno"))
    el.append(Spacer(1, 4 * mm))
    fabb_rows = []
    inv = scop.get("invalidita", {})
    fabb_rows.append(("Invalidità", _fmt_eur(inv.get("pensione_mensile")),
                      f"Reddito mancante fino a 70 anni: <b>{_fmt_eur(inv.get('capitale_da_assicurare'))}</b>"))
    inab = scop.get("inabilita", {})
    fabb_rows.append(("Non Autosufficienza", _fmt_eur(inab.get("pensione_mensile")),
                      f"Capitale necessario: <b>{_fmt_eur(inab.get('capitale_da_assicurare'))}</b>"))
    sup = scop.get("superstiti", {})
    fabb_rows.append(("Premorienza", _fmt_eur(sup.get("pensione_mensile")),
                      f"Entrate mancanti famiglia fino ai 70 anni del coniuge: <b>{_fmt_eur(sup.get('capitale_da_assicurare'))}</b>"))
    # Trasforma testo HTML in paragrafi
    fabb_data = [["Rischio", "Pensione maturata", "Fabbisogno"]]
    for r in fabb_rows:
        fabb_data.append([Paragraph(r[0], s["body"]), Paragraph(r[1], s["body"]), Paragraph(r[2], s["body"])])
    t = Table(fabb_data, colWidths=[35 * mm, 35 * mm, 100 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    el.append(t)
    el.append(PageBreak())

    # --- PAGINA 11-12: La nostra raccomandazione ---
    el.append(_section_title("La nostra raccomandazione"))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        "Trasferisci queste somme alle compagnie assicurative, sia per casi di infortunio che malattia, "
        "con la possibilità di diminuire l'importo di anno in anno fino al compimento dei 70 anni:",
        s["body_just"],
    ))
    el.append(Spacer(1, 8 * mm))
    rec_data = [
        ["In caso di premorienza *", _fmt_eur(sup.get("capitale_da_assicurare"))],
        ["In caso di invalidità *", _fmt_eur(inv.get("capitale_da_assicurare"))],
        ["In caso di non autosufficienza - rendita vitalizia mensile", _fmt_eur(inab.get("scopertura_mensile"))],
    ]
    t = Table(rec_data, colWidths=[110 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 0), (1, -1), ROSE),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    el.append(t)
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph(
        "(*) La somma risulta congrua anche al 70% dell'effettiva scopertura perché verrebbe "
        "liquidata anticipatamente e al netto di qualsiasi tassazione. Verifica con la tua cassa "
        "di previdenza eventuali prestazioni assicurative aggiuntive.",
        s["small"],
    ))
    el.append(PageBreak())

    # --- PAGINA 13: Cosa devi controllare ---
    el.append(_section_title("Cosa devi controllare?"))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        "Prima di aderire a qualsiasi polizza, controlla il documento informativo precontrattuale e "
        "fatti spiegare con precisione tutti questi punti:",
        s["body_just"],
    ))
    checklist = [
        "Garanzie incluse e garanzie escluse (carenze, franchigie, limiti).",
        "Massimali per evento e per anno assicurativo.",
        "Durata del contratto e modalità di disdetta.",
        "Esistenza e ammontare delle franchigie e scoperti.",
        "Modalità di rivalutazione del capitale (indicizzato o no).",
        "Decorrenza e termini di pagamento del sinistro.",
        "Documenti necessari per la liquidazione.",
        "Esclusione di malattie pregresse o sport rischiosi.",
        "Riduzione automatica dell'importo dopo i 65 anni.",
        "Possibilità di adeguamento annuo del capitale.",
    ]
    for c in checklist:
        el.append(Paragraph(f"• {c}", s["body"]))
    el.append(PageBreak())

    # --- PAGINA 14: Scheda Cassa ---
    el.append(_section_title("Scheda Cassa Previdenziale"))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(f"<b>Cassa di appartenenza:</b> {tipo_lav}", s["body"]))
    el.append(Spacer(1, 4 * mm))
    cassa_info = [
        ("Aliquota contributiva totale", f"{int(((reddito_calc_alq(tipo_lav)) * 100))}%"),
        ("Aliquota a carico del lavoratore", f"{int(((reddito_calc_alq(tipo_lav)) * 100))}%"),
        ("Età vecchiaia", "67 anni"),
        ("Età pensione anticipata", "64-66 anni"),
        ("Anzianità contributiva minima", "20 anni"),
    ]
    el.append(_data_table(["Voce", "Valore"], cassa_info, [110, 60]))
    el.append(PageBreak())

    # --- PAGINA 15-16: Note personali ---
    el.append(_section_title("Note personali"))
    el.append(Spacer(1, 4 * mm))
    for i in range(25):
        el.append(HRFlowable(width="100%", color=colors.HexColor("#E2E8F0"), thickness=0.3, spaceAfter=10))
    el.append(PageBreak())

    # --- PAGINA 17: Indice ---
    el.append(_section_title("Indice"))
    el.append(Spacer(1, 6 * mm))
    indice = [
        ("La diagnosi del tuo reddito", "2"),
        ("La tua situazione famigliare", "3"),
        ("La tua situazione contributiva", "4"),
        ("Le tue prestazioni maturate", "6"),
        ("Le tue riserve", "8"),
        ("Le tue prestazioni · quanto dureranno?", "9"),
        ("Il tuo fabbisogno", "10"),
        ("La nostra raccomandazione personale", "11"),
        ("Cosa devi controllare?", "13"),
        ("Scheda cassa previdenziale", "14"),
        ("Note personali", "15"),
    ]
    el.append(_data_table(["Sezione", "Pagina"], indice, [140, 30]))

    doc.build(el, onFirstPage=lambda c, d: _header_footer(c, d, azienda, nome_op, rnum),
              onLaterPages=lambda c, d: _header_footer(c, d, azienda, nome_op, rnum))
    return buf.getvalue()


def reddito_calc_alq(tipo_lavoratore: str) -> float:
    """Wrapper per import indiretto."""
    import reddito_calc
    return reddito_calc.ALIQUOTE_CONTRIBUTIVE.get((tipo_lavoratore or "").lower(), 0.24)


# ============================================================
# PDF 2: PROGETTO FUTURO SENZA SORPRESE (AZZOB / ISO 31000)
# ============================================================
def genera_progetto_azzob(ana: dict, ac: dict, pens: dict, scop: dict, patr: dict, azienda: dict, user: dict) -> bytes:
    s = _styles()
    buf = io.BytesIO()
    doc = _build_doc(buf)
    el = []
    now = datetime.now()
    rnum = f"{now.year}/BOZZA"
    nome_op = (user.get("name") or "OPERATORE").upper()
    nome_cliente = (f"{ana.get('nome', '') or ''} {ana.get('cognome', '') or ''}").strip() or ana.get("ragione_sociale", "")

    # --- COPERTINA ---
    el.append(Spacer(1, 30 * mm))
    el.append(Paragraph("Progetto Futuro<br/>Senza Sorprese", s["h1_cover"]))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(f"di <b>{nome_cliente}</b>", s["h2"]))
    el.append(Spacer(1, 14 * mm))
    el.append(Paragraph(
        "Immagina di avere una mappa dettagliata per navigare attraverso ogni rischio e ostacolo che "
        "potrebbe frapporsi tra te e i tuoi obiettivi. Il Progetto Futuro Senza Sorprese è nato per "
        "questo: aiutarti a identificare e misurare ogni rischio, seguendo i principi della "
        "<b>ISO 31000</b>.",
        s["body_just"],
    ))
    el.append(Spacer(1, 10 * mm))
    el.append(Paragraph(f"Progetto redatto da: <b>{nome_op}</b>", s["body"]))
    el.append(Paragraph(f"Numero Univoco Report: <b>{rnum}</b>", s["small"]))
    el.append(PageBreak())

    # --- METODO ISO 31000 ---
    el.append(_section_title("Il metodo: ISO 31000 · Risk Management"))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        "Benvenuto nel tuo personale Progetto Futuro Senza Sorprese, redatto seguendo i principi della "
        "norma UNI ISO 31000. Questo documento ti guiderà attraverso un percorso di consapevolezza e "
        "gestione dei rischi, analizzando le minacce che potrebbero influenzare il raggiungimento dei "
        "tuoi obiettivi personali.",
        s["body_just"],
    ))
    el.append(Spacer(1, 6 * mm))
    metodo = [
        ("A", "CONTESTO", "Analizziamo la tua situazione familiare, lavorativa e patrimoniale per comprendere il quadro generale."),
        ("Z", "OBIETTIVI E IMPEGNI", "Stabiliamo insieme cosa è importante per te e cosa desideri evitare a tutti i costi."),
        ("Z", "APPETITO AL RISCHIO", "Definiamo quanto sei disposto a sopportare in termini di perdita economica."),
        ("O", "MAPPATURA DEI RISCHI", "Identifichiamo i rischi principali che minacciano la tua stabilità."),
        ("B", "VALUTAZIONE DEI RISCHI", "Analizziamo e quantifichiamo questi rischi."),
    ]
    for letter, title, desc in metodo:
        kt = Table([[
            Paragraph(f"<font size=24 color='{PRIMARY.hexval()}'><b>{letter}</b></font>", s["body"]),
            Paragraph(f"<b>{title}</b><br/><font size=9 color='#475569'>{desc}</font>", s["body"]),
        ]], colWidths=[15 * mm, 155 * mm])
        kt.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        el.append(kt)
        el.append(Spacer(1, 3 * mm))
    el.append(PageBreak())

    # --- A. CONTESTO ---
    el.append(_section_title("1. Contesto", color=PRIMARY))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph("<b>Situazione familiare</b>", s["h3"]))
    el.append(Paragraph(ac.get("contesto_familiare") or
                        "Per costruire una strategia di gestione dei rischi solida ed efficace, è fondamentale "
                        "partire da una chiara comprensione del tuo contesto familiare, stabilendo 'chi dipende "
                        "da chi'.",
                        s["body_just"]))
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph("<b>Situazione contributiva</b>", s["h3"]))
    kpis = Table([[
        _kpi_card("Totale versato", _fmt_eur(pens.get("totale_versato")), EMERALD, 80),
        _kpi_card("Totale rivalutato", _fmt_eur(pens.get("totale_rivalutato")), PRIMARY, 80),
    ]], colWidths=[85 * mm, 85 * mm])
    el.append(kpis)
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        f"Attualmente sei un <b>{(ac.get('tipo_lavoratore') or 'lavoratore').title()}</b>, con "
        f"<b>{int(pens.get('anni_contribuzione', 0))} anni</b> di contributi versati e un reddito lordo "
        f"di <b>{_fmt_eur(ac.get('reddito_lordo_annuo'))}</b>.",
        s["body_just"],
    ))
    el.append(PageBreak())

    el.append(_section_title("1. Contesto · La tua situazione patrimoniale", color=PRIMARY))
    el.append(Spacer(1, 6 * mm))
    immobili = ac.get("immobili") or []
    for i in immobili:
        el.append(Paragraph(
            f"• Per il <b>{i.get('percentuale_proprieta', 100):.2f}%</b>: Immobile {i.get('tipo', '').title()} "
            f"(del valore pari a {_fmt_eur(i.get('valore_commerciale'))}) "
            f"{i.get('indirizzo', '') or ''} {i.get('comune', '') or ''}",
            s["body"],
        ))
    for v in ac.get("veicoli") or []:
        el.append(Paragraph(
            f"• Veicolo {v.get('tipo', '').title()} {v.get('marca', '')} {v.get('modello', '')} "
            f"(valore {_fmt_eur(v.get('valore_commerciale'))}) targa: {v.get('targa', '—')}",
            s["body"],
        ))
    el.append(Spacer(1, 6 * mm))

    patr_table = [
        ("Patrimonio liquido", _fmt_eur(patr.get("patrimonio_liquido"))),
        ("Patrimonio in immobili", _fmt_eur(patr.get("patrimonio_immobiliare"))),
        ("Patrimonio aziendale", _fmt_eur(patr.get("patrimonio_aziendale"))),
        ("Montante contributivo", _fmt_eur(patr.get("montante_contributivo"))),
        ("Altri beni", _fmt_eur(patr.get("altri_beni"))),
        ("Debiti", _fmt_eur(patr.get("debiti"))),
    ]
    el.append(_data_table(["Voce", "Valore"], patr_table, [110, 60]))
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        "<i>Patrimonio liquido = Liquidità + TFR. Altri beni = comprende veicoli. "
        "Patrimonio aziendale = valore ipotetico minimo sui dati di bilancio.</i>",
        s["small"],
    ))
    el.append(PageBreak())

    # --- Z. OBIETTIVI E IMPEGNI ---
    el.append(_section_title("2. Obiettivi e impegni", color=PRIMARY))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        "Dopo aver analizzato il tuo contesto personale e patrimoniale, definiamo i tuoi obiettivi e ciò "
        "che desideri evitare a tutti i costi. Durante il nostro incontro ti abbiamo posto delle domande "
        "precise. Ecco le tue risposte:",
        s["body_just"],
    ))
    el.append(Spacer(1, 4 * mm))
    obiettivi = [
        ("Cosa ti renderebbe veramente felice e soddisfatto?", ac.get("cosa_renderebbe_felice")),
        ("Cosa NON vuoi che accada durante la tua carriera?", ac.get("cosa_non_vuoi_carriera")),
        ("Quando non ci sarai più, cosa NON vuoi che accada?", ac.get("cosa_non_vuoi_dopo")),
        ("Quando andrai in pensione, cosa NON vuoi che accada?", ac.get("cosa_non_vuoi_pensione")),
    ]
    for q, a in obiettivi:
        el.append(Paragraph(f"<b>{q}</b>", s["h3"]))
        el.append(Paragraph(a or "<i>Non compilato</i>", s["body_just"]))
        el.append(Spacer(1, 4 * mm))
    el.append(PageBreak())

    # --- Z. APPETITO AL RISCHIO ---
    el.append(_section_title("3. Appetito al rischio", color=PRIMARY))
    el.append(Spacer(1, 6 * mm))
    soglia_e = float(ac.get("danno_devastante_entrate_mensili") or 0)
    soglia_p = float(ac.get("danno_devastante_patrimonio") or 0)
    el.append(Paragraph("<b>ENTRATE</b>", s["h3"]))
    el.append(Paragraph(
        f"Per te e la tua famiglia sarebbe un danno devastante se le tue entrate diminuissero più di "
        f"<b>{_fmt_eur(soglia_e)} al mese</b>.",
        s["body"],
    ))
    if soglia_e > 0:
        step = soglia_e / 5
        rischio_e = [
            ["TRASCURABILE", "BASSO", "MEDIO", "ALTO", "MOLTO ALTO"],
            [_fmt_eur(step), f"{_fmt_eur(step)} - {_fmt_eur(step*2)}",
             f"{_fmt_eur(step*2)} - {_fmt_eur(step*3)}", f"{_fmt_eur(step*3)} - {_fmt_eur(step*4)}",
             f"{_fmt_eur(step*4)} - {_fmt_eur(step*5)}"],
        ]
        t = Table(rischio_e, colWidths=[34*mm]*5)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#86EFAC")),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#FDE68A")),
            ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FED7AA")),
            ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#FCA5A5")),
            ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#F87171")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        el.append(t)
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph("<b>PATRIMONIO</b>", s["h3"]))
    el.append(Paragraph(
        f"Per te e la tua famiglia sarebbe un danno devastante se il tuo patrimonio diminuisse più di "
        f"<b>{_fmt_eur(soglia_p)}</b>.",
        s["body"],
    ))
    el.append(PageBreak())

    # --- O. MAPPATURA RISCHI ---
    el.append(_section_title("4. Mappatura dei rischi", color=PRIMARY))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        "Per garantire la tua tranquillità economica, è essenziale identificare e gestire i principali "
        "rischi che potrebbero farti rimanere senza soldi. Abbiamo individuato <b>quattro grandi "
        "rischi</b>:",
        s["body_just"],
    ))
    rischi = [
        ("MENO ENTRATE", "Mettere al sicuro l'ossigeno che permette ad ogni famiglia di respirare ogni mese."),
        ("PERDITA BENI E RESPONSABILITÀ", "Proteggere i beni accumulati durante l'intera vita dai gravi rischi."),
        ("PERDITA RISPARMIO", "Poggiare i risparmi su una base solida di protezione: cassa liquidità, cassa lievi esigenze, cassa grandi esigenze, investimenti."),
        ("BLOCCO EREDITÀ", "Lasciare quanto di buono si è costruito alle persone care, senza intoppi, senza liti, senza erosioni."),
    ]
    for titolo, desc in rischi:
        kt = Table([[Paragraph(f"<b>{titolo}</b><br/><font size=9 color='#475569'>{desc}</font>", s["body"])]],
                   colWidths=[170 * mm])
        kt.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, PRIMARY),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        el.append(kt)
        el.append(Spacer(1, 4 * mm))
    el.append(PageBreak())

    # --- B. VALUTAZIONE RISCHI ---
    el.append(_section_title("5. Valutazione dei rischi", color=PRIMARY))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph("<b>Perdita delle entrate · Invalidità</b>", s["h3"]))
    inv = scop.get("invalidita", {})
    inab = scop.get("inabilita", {})
    el.append(Paragraph(
        f"In caso di grave invalidità (superiore al 66%) la pensione maturata sarebbe di "
        f"<b>{_fmt_eur(inv.get('pensione_mensile'))} lordi/mese</b>. In caso di invalidità totale "
        f"(inabilità) sarebbe di <b>{_fmt_eur(inab.get('pensione_mensile'))} lordi/mese</b>.",
        s["body_just"],
    ))
    el.append(Spacer(1, 4 * mm))
    inv_table = [
        ["Tipo", "Diminuzione annuale", "Diminuzione mensile"],
        ["Pensione d'invalidità", f"{_fmt_eur(inv.get('scopertura_annua'))} ({_fmt_pct(100 - inv.get('copertura_pct', 0))})", _fmt_eur(inv.get("scopertura_mensile"))],
        ["Pensione d'inabilità", f"{_fmt_eur(inab.get('scopertura_annua'))} ({_fmt_pct(100 - inab.get('copertura_pct', 0))})", _fmt_eur(inab.get("scopertura_mensile"))],
    ]
    el.append(_data_table(inv_table[0], inv_table[1:], [50, 65, 55]))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        f"<b>REDDITO MANCANTE in caso di grave invalidità:</b> "
        f"<font color='{ROSE.hexval()}' size=18><b>{_fmt_eur(inv.get('capitale_da_assicurare'))}</b></font>",
        s["body"],
    ))
    el.append(PageBreak())

    # --- Premorienza ---
    el.append(_section_title("5. Valutazione dei rischi · Premorienza", color=PRIMARY))
    el.append(Spacer(1, 6 * mm))
    sup = scop.get("superstiti", {})
    el.append(Paragraph(
        f"In caso di premorienza la pensione ai superstiti maturata sarebbe di "
        f"<b>{_fmt_eur(sup.get('pensione_mensile'))} lordi/mese</b>.",
        s["body_just"],
    ))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(
        f"<b>ENTRATE MANCANTI alla famiglia fino al compimento dei 70 anni del coniuge:</b> "
        f"<font color='{ROSE.hexval()}' size=18><b>{_fmt_eur(sup.get('capitale_da_assicurare'))}</b></font>",
        s["body"],
    ))
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        f"Eventuali debiti da estinguere: <b>{_fmt_eur(sup.get('debiti_inclusi'))}</b>.",
        s["small"],
    ))
    el.append(PageBreak())

    # --- Vecchiaia ---
    el.append(_section_title("5. Valutazione dei rischi · Vecchiaia", color=PRIMARY))
    el.append(Spacer(1, 6 * mm))
    vec = scop.get("vecchiaia", {})
    el.append(Paragraph(
        f"Al raggiungimento dell'età pensionabile (<b>{vec.get('eta_pensionamento')} anni</b>), la pensione "
        f"di vecchiaia maturata sarebbe di <b>{_fmt_eur(vec.get('pensione_mensile'))} lordi/mese</b>.",
        s["body_just"],
    ))
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(
        f"La scopertura mensile sarà di <b>{_fmt_eur(vec.get('scopertura_mensile'))}</b> rispetto al "
        f"tuo tenore di vita attuale.",
        s["body_just"],
    ))
    el.append(Spacer(1, 4 * mm))
    cop_pct = vec.get("copertura_pct", 0)
    el.append(Paragraph(f"Copertura attuale: <b>{_fmt_pct(cop_pct)}</b> del reddito attuale.", s["body"]))

    doc.build(el, onFirstPage=lambda c, d: _header_footer(c, d, azienda, nome_op, rnum),
              onLaterPages=lambda c, d: _header_footer(c, d, azienda, nome_op, rnum))
    return buf.getvalue()
