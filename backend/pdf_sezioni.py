"""Generatore PDF per le 9 sezioni dell'Analisi Cliente.

Ogni sezione può essere stampata singolarmente oppure tutte insieme in un
"PDF unico" (compendio completo).
Logo aziendale in alto a sinistra in ogni pagina.
"""
from __future__ import annotations
import io
import os
from datetime import datetime, date
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Image as RLImage, KeepTogether, HRFlowable,
)


PRIMARY = colors.HexColor("#0369A1")
ACCENT = colors.HexColor("#0EA5E9")
DARK = colors.HexColor("#0F172A")
MID = colors.HexColor("#475569")
LIGHT = colors.HexColor("#F1F5F9")
ROSE = colors.HexColor("#BE123C")
EMERALD = colors.HexColor("#047857")
AMBER = colors.HexColor("#B45309")
VIOLET = colors.HexColor("#7C3AED")
SKY = colors.HexColor("#0284C7")


def _fmt_eur(v) -> str:
    if v is None:
        return "—"
    try:
        return f"€ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)


def _fmt_int(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{int(v):,}".replace(",", ".")
    except Exception:
        return str(v)


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=20, leading=24, textColor=PRIMARY, spaceAfter=10, fontName="Helvetica-Bold"),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=14, leading=18, textColor=DARK, spaceAfter=6, fontName="Helvetica-Bold"),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=11, leading=14, textColor=DARK, spaceAfter=4, fontName="Helvetica-Bold"),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9, leading=12, textColor=DARK, spaceAfter=5),
        "body_just": ParagraphStyle("bj", parent=base["Normal"], fontSize=9, leading=12, alignment=TA_JUSTIFY, textColor=DARK, spaceAfter=5),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=8, textColor=MID),
        "kpi_label": ParagraphStyle("kpil", parent=base["Normal"], fontSize=8, textColor=MID, alignment=TA_CENTER),
        "kpi_value": ParagraphStyle("kpiv", parent=base["Normal"], fontSize=14, textColor=PRIMARY, alignment=TA_CENTER, fontName="Helvetica-Bold"),
    }


def _logo_bytes(azienda: dict) -> bytes | None:
    """Recupera il logo dell'azienda dallo storage (se presente)."""
    url = azienda.get("logo_url")
    if not url:
        return None
    try:
        import storage as obj_storage
        path = url.split("/api/storage/", 1)[-1] if "/api/storage/" in url else url
        result = obj_storage.get_object(path)
        if isinstance(result, tuple):
            return result[0]
        return result
    except Exception:
        return None


def _make_header(azienda: dict, titolo: str, nome_cliente: str):
    logo_b = _logo_bytes(azienda)

    def _draw(canvas, doc):
        canvas.saveState()
        w, h = A4
        # Logo in alto a sinistra
        if logo_b:
            try:
                from reportlab.lib.utils import ImageReader
                img = ImageReader(io.BytesIO(logo_b))
                canvas.drawImage(img, 15 * mm, h - 30 * mm, width=35 * mm, height=20 * mm,
                                 preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        # Titolo a destra
        canvas.setFillColor(DARK)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawRightString(w - 15 * mm, h - 15 * mm, (azienda.get("ragione_sociale") or "Assicura").upper())
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MID)
        canvas.drawRightString(w - 15 * mm, h - 19 * mm, titolo)
        canvas.drawRightString(w - 15 * mm, h - 23 * mm, f"Cliente: {nome_cliente}")
        # Linea decorativa
        canvas.setStrokeColor(PRIMARY)
        canvas.setLineWidth(0.6)
        canvas.line(15 * mm, h - 32 * mm, w - 15 * mm, h - 32 * mm)
        # Footer
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MID)
        ind = " · ".join(filter(None, [
            azienda.get("indirizzo"),
            f"{azienda.get('cap') or ''} {azienda.get('comune') or ''}".strip(),
            f"P.IVA {azienda.get('partita_iva')}" if azienda.get("partita_iva") else None,
            azienda.get("email") or "",
        ]))
        canvas.drawString(15 * mm, 10 * mm, ind[:140])
        canvas.drawRightString(w - 15 * mm, 10 * mm,
                               f"Pagina {doc.page}  ·  {datetime.now().strftime('%d/%m/%Y')}")
        canvas.restoreState()
    return _draw


def _kpi_card(label: str, value: str, color=PRIMARY, w_mm=55) -> Table:
    s = _styles()
    t = Table(
        [[Paragraph(label.upper(), s["kpi_label"])],
         [Paragraph(value, ParagraphStyle("v", parent=s["kpi_value"], textColor=color))]],
        colWidths=[w_mm * mm], rowHeights=[6 * mm, 14 * mm],
    )
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    return t


def _section_band(text: str, color=PRIMARY) -> Table:
    p = Paragraph(f"<b>{text}</b>", ParagraphStyle("sb", fontSize=14, textColor=colors.white, alignment=TA_LEFT, leading=18, fontName="Helvetica-Bold"))
    t = Table([[p]], colWidths=[180 * mm], rowHeights=[10 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def _data_table(headers, rows, col_widths_mm=None):
    data = [list(headers)] + [list(r) for r in rows]
    cw = [w * mm for w in col_widths_mm] if col_widths_mm else None
    t = Table(data, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]))
    return t


# ============================================================
# SEZIONI (ogni funzione restituisce una lista di Flowables)
# ============================================================
def _sez_finanza(ac, ana, s):
    el = [_section_band("1. Situazione Finanziaria", color=EMERALD), Spacer(1, 5 * mm)]
    rows = [
        ["Reddito lordo annuo", _fmt_eur(ac.get("reddito_lordo_annuo"))],
        ["Dividendi partecipazioni", _fmt_eur(ac.get("dividendi_partecipazioni"))],
        ["Altri redditi annuali", _fmt_eur(ac.get("altri_redditi_annuali"))],
        ["Reddito da affitti", _fmt_eur(ac.get("reddito_da_affitti"))],
        ["Regime forfettario", "Sì" if ac.get("regime_forfettario") else "No"],
        ["TFR maturato", _fmt_eur(ac.get("tfr_maturato"))],
        ["Liquidità", _fmt_eur(ac.get("liquidita"))],
        ["Debiti totali", _fmt_eur(ac.get("debiti"))],
        ["Oneri deducibili", _fmt_eur(ac.get("oneri_deducibili"))],
        ["Oneri fondo pensione", _fmt_eur(ac.get("oneri_fondo_pensione"))],
        ["Capacità risparmio annuale", _fmt_eur(ac.get("capacita_risparmio_annuale"))],
        ["Soglia danno entrate €/mese", _fmt_eur(ac.get("danno_devastante_entrate_mensili"))],
        ["Soglia danno patrimonio", _fmt_eur(ac.get("danno_devastante_patrimonio"))],
    ]
    el.append(_data_table(["Voce", "Valore"], rows, [110, 70]))
    return el


def _sez_patrimonio(ac, ana, s):
    el = [_section_band("2. Patrimonio", color=SKY), Spacer(1, 5 * mm)]
    imm = ac.get("immobili") or []
    vei = ac.get("veicoli") or []
    az = ac.get("aziende") or []
    el.append(Paragraph(f"<b>Immobili ({len(imm)})</b>", s["h3"]))
    if imm:
        el.append(_data_table(
            ["Tipo", "Indirizzo", "Comune", "%", "Valore €", "Rendita"],
            [(i.get("tipo", "—"), i.get("indirizzo", "—") or "—", i.get("comune", "—") or "—",
              f"{i.get('percentuale_proprieta', 100)}%",
              _fmt_eur(i.get("valore_commerciale")),
              _fmt_eur(i.get("rendita_catastale"))) for i in imm],
            [25, 50, 35, 18, 30, 22],
        ))
    else:
        el.append(Paragraph("<i>Nessun immobile</i>", s["small"]))
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(f"<b>Veicoli ({len(vei)})</b>", s["h3"]))
    if vei:
        el.append(_data_table(
            ["Tipo", "Marca/Modello", "Targa", "Valore €"],
            [(v.get("tipo", "—"), f"{v.get('marca', '')} {v.get('modello', '')}".strip() or "—",
              v.get("targa", "—") or "—", _fmt_eur(v.get("valore_commerciale"))) for v in vei],
            [30, 80, 30, 40],
        ))
    else:
        el.append(Paragraph("<i>Nessun veicolo</i>", s["small"]))
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(f"<b>Aziende ({len(az)})</b>", s["h3"]))
    if az:
        el.append(_data_table(
            ["Tipo", "Ragione sociale", "% partecip.", "EBITDA", "Valore €"],
            [(a.get("tipo", "—"), a.get("ragione_sociale", "—"),
              f"{a.get('percentuale_partecipazione', 100)}%",
              _fmt_eur(a.get("ebitda")), _fmt_eur(a.get("valore_ipotetico"))) for a in az],
            [20, 80, 25, 30, 30],
        ))
    return el


def _sez_contesto(ac, ana, s):
    el = [_section_band("3. Contesto & Obiettivi", color=VIOLET), Spacer(1, 5 * mm)]
    for titolo, key in [
        ("Contesto familiare", "contesto_familiare"),
        ("Contesto lavorativo", "contesto_lavorativo"),
        ("Contesto patrimoniale", "contesto_patrimoniale"),
        ("Cosa renderebbe felice il cliente", "cosa_renderebbe_felice"),
        ("Cosa NON deve accadere durante la carriera", "cosa_non_vuoi_carriera"),
        ("Cosa NON deve accadere dopo (eredità)", "cosa_non_vuoi_dopo"),
        ("Cosa NON deve accadere in pensione", "cosa_non_vuoi_pensione"),
    ]:
        el.append(Paragraph(f"<b>{titolo}</b>", s["h3"]))
        el.append(Paragraph(ac.get(key) or "<i>Non compilato</i>", s["body_just"]))
        el.append(Spacer(1, 3 * mm))
    return el


def _sez_redditi(ac, ana, dati, s):
    el = [_section_band("4. Approfondimento Redditi", color=EMERALD), Spacer(1, 5 * mm)]
    d = dati.get("redditi") or {}
    el.append(Paragraph(
        f"Tipo lavoratore: <b>{d.get('tipo_lavoratore', '—').title()}</b> · "
        f"{'Regime forfettario' if d.get('regime_forfettario') else 'Regime ordinario'}",
        s["body"]))
    el.append(Spacer(1, 3 * mm))
    rows = [
        ["Reddito lordo", _fmt_eur(d.get("reddito_lordo"))],
        ["Altri redditi", _fmt_eur(d.get("altri_redditi"))],
        [f"Contributi previdenziali ({d.get('aliquota_contributiva_lavoratore_pct', 0)}%)",
         f"- {_fmt_eur(d.get('contributi_lavoratore'))}"],
        ["Reddito imponibile", _fmt_eur(d.get("reddito_imponibile"))],
        [f"IRPEF lorda (marginale {d.get('aliquota_irpef_marginale_pct', 0)}%)",
         _fmt_eur(d.get("irpef_lorda"))],
        ["Detrazione lavoro dipendente", f"- {_fmt_eur(d.get('detrazione_lavoro_dipendente'))}"],
        ["Detrazione coniuge", f"- {_fmt_eur(d.get('detrazione_coniuge'))}"],
        ["Altre detrazioni", f"- {_fmt_eur(d.get('altre_detrazioni'))}"],
        ["IRPEF netta", _fmt_eur(d.get("irpef_netta"))],
        ["REDDITO NETTO STIMATO", _fmt_eur(d.get("reddito_netto"))],
    ]
    el.append(_data_table(["Voce", "Importo"], rows, [110, 70]))
    return el


def _sez_pensione(ac, ana, dati, s):
    el = [_section_band("5. Pensione INPS", color=PRIMARY), Spacer(1, 5 * mm)]
    p = dati.get("pensioni") or {}
    kpis = Table([[
        _kpi_card("Anni contrib.", str(int(p.get("anni_contribuzione", 0))), EMERALD, 40),
        _kpi_card("Settimane", _fmt_int(p.get("settimane_contributive")), SKY, 40),
        _kpi_card("Tot. versato", _fmt_eur(p.get("totale_versato")), AMBER, 50),
        _kpi_card("Montante stimato", _fmt_eur(p.get("montante_contributivo_attuale")), EMERALD, 50),
    ]], colWidths=[45 * mm, 45 * mm, 55 * mm, 55 * mm])
    el.append(kpis)
    el.append(Spacer(1, 5 * mm))
    # Pensioni di oggi
    el.append(Paragraph("<b>Pensioni di OGGI</b> (Invalidità · Inabilità · Superstiti)", s["h3"]))
    oggi = p.get("pensioni_oggi") or {}
    rows = []
    for tipo, label in (("invalidita", "Invalidità (66-99%)"),
                        ("inabilita", "Inabilità (100%)"),
                        ("superstite", "Superstiti")):
        po = oggi.get(tipo) or {}
        rows.append([label, _fmt_eur(po.get("pensione_lorda_mensile")), _fmt_eur(po.get("pensione_lorda_annua"))])
    el.append(_data_table(["Tipo", "Mensile (lordo)", "Annuo (lordo)"], rows, [80, 50, 50]))
    el.append(Spacer(1, 4 * mm))
    # Pensioni del domani
    el.append(Paragraph("<b>Pensioni del DOMANI</b> (proiezione 64-71 anni)", s["h3"]))
    domani = p.get("pensioni_domani") or []
    if domani:
        rows = [(d.get("eta_pensionamento"), d.get("anno_pensionamento"), d.get("modalita"),
                 _fmt_eur(d.get("importo_mensile")), _fmt_eur(d.get("importo_annuo")),
                 _fmt_eur(d.get("montante_contributivo"))) for d in domani]
        el.append(_data_table(["Età", "Anno", "Modalità", "Mensile", "Annuo", "Montante"], rows,
                              [15, 20, 30, 35, 40, 40]))
    return el


def _sez_scoperture(ac, ana, dati, s):
    el = [_section_band("6. Riepilogo Pensionistico (Scoperture)", color=ROSE), Spacer(1, 5 * mm)]
    sc = dati.get("scoperture") or {}
    for key, label, color in [
        ("invalidita", "Invalidità", ROSE),
        ("inabilita", "Inabilità", AMBER),
        ("superstiti", "Superstiti (Premorienza)", ROSE),
        ("vecchiaia", "Pensione di Vecchiaia", PRIMARY),
    ]:
        d = sc.get(key) or {}
        el.append(Paragraph(
            f"<b><font color='{color.hexval()}'>{label}</font></b>",
            s["h3"]))
        rows = [
            ["Pensione mensile", _fmt_eur(d.get("pensione_mensile"))],
            ["Pensione annua", _fmt_eur(d.get("pensione_annua"))],
            ["Scopertura mensile", _fmt_eur(d.get("scopertura_mensile"))],
            ["Scopertura annua", _fmt_eur(d.get("scopertura_annua"))],
            ["Copertura attuale", f"{d.get('copertura_pct', 0)}%"],
            ["CAPITALE DA ASSICURARE", _fmt_eur(d.get("capitale_da_assicurare"))],
        ]
        el.append(_data_table(["Voce", "Importo"], rows, [110, 70]))
        el.append(Spacer(1, 4 * mm))
    return el


def _sez_successione(ac, ana, dati, s):
    el = [_section_band("7. Successione", color=AMBER), Spacer(1, 5 * mm)]
    su = dati.get("successione") or {}
    el.append(Paragraph(
        f"Patrimonio stimato: <b>{_fmt_eur(su.get('patrimonio'))}</b>", s["body"]))
    el.append(Spacer(1, 3 * mm))
    for scen_key, titolo in (("senza_testamento", "Senza testamento (legittima)"),
                              ("quote_legittima", "Con testamento (quote di legittima)")):
        scen = su.get(scen_key) or {}
        el.append(Paragraph(f"<b>{titolo}</b>", s["h3"]))
        if scen.get("label"):
            rows = [(lbl, f"{q}%", _fmt_eur(eu))
                    for lbl, q, eu in zip(scen.get("label", []), scen.get("quota_pct", []), scen.get("quota_eur", []))]
            if scen.get("disponibile_pct"):
                rows.append(("Quota disponibile", f"{scen['disponibile_pct']}%", _fmt_eur(scen.get("disponibile_eur"))))
            el.append(_data_table(["Erede", "Quota", "Importo"], rows, [90, 30, 60]))
        else:
            el.append(Paragraph("<i>Nessun erede legittimo</i>", s["small"]))
        if scen.get("note"):
            el.append(Paragraph(f"<i>{scen['note']}</i>", s["small"]))
        el.append(Spacer(1, 3 * mm))
    return el


def _sez_trattativa(ac, ana, s):
    el = [_section_band("8. Trattativa A/B", color=ACCENT), Spacer(1, 5 * mm)]
    t = ac.get("trattativa") or {}
    a = t.get("scenario_a") or {}
    b = t.get("scenario_b") or {}
    voci = [
        ("invalidita", "Invalidità"), ("importo_pensione", "Importo pensione"),
        ("premorienza", "Premorienza"), ("responsabilita", "Responsabilità"),
        ("perdita_beni", "Perdita beni"), ("prima_data_pensionabile", "Prima data pensionabile"),
        ("versamento_fondo", "Versamento fondo pensione"),
        ("risparmio_annuo", "Risparmio annuo"), ("vantaggio_fiscale", "Vantaggio fiscale"),
        ("reddito", "Reddito"),
    ]
    rows = []
    for k, label in voci:
        va = a.get(k)
        vb = b.get(k)
        fa = _fmt_eur(va) if k != "prima_data_pensionabile" else (str(va) if va else "—")
        fb = _fmt_eur(vb) if k != "prima_data_pensionabile" else (str(vb) if vb else "—")
        rows.append([label, fa, fb])
    el.append(_data_table(["Voce", "A · Non fai nulla", "B · Ti affidi a me"], rows, [70, 55, 55]))
    el.append(Spacer(1, 4 * mm))
    if t.get("obiettivi"):
        el.append(Paragraph("<b>Obiettivi e desideri</b>", s["h3"]))
        el.append(Paragraph(t["obiettivi"], s["body_just"]))
    if t.get("perdita_entrate"):
        el.append(Paragraph("<b>Perdita Entrate</b>", s["h3"]))
        el.append(Paragraph(t["perdita_entrate"], s["body_just"]))
    return el


def _sez_piramide(ac, ana, s):
    el = [_section_band("9. Piramide delle Soluzioni", color=VIOLET), Spacer(1, 5 * mm)]
    pir = ac.get("piramide_soluzioni") or []
    if not pir:
        el.append(Paragraph("<i>Nessuna copertura ancora definita.</i>", s["body"]))
        return el
    # Raggruppa per categoria
    by_cat = {}
    for p in pir:
        by_cat.setdefault(p.get("categoria") or "Altro", []).append(p)
    rows = []
    stati_map = {"adeguata": "✓ Adeguata", "non_adeguata": "⚠ Non adeguata",
                 "non_presente": "✗ Non presente"}
    for cat, items in by_cat.items():
        rows.append([f"━━ {cat.upper()} ━━", "", "", "", "", ""])
        for p in items:
            rows.append([
                stati_map.get(p.get("stato"), "—"),
                p.get("titolo") or "—",
                _fmt_eur(p.get("capitale_assicurato")),
                _fmt_eur(p.get("premio_annuo")),
                f"{p.get('durata_anni', 1)} anni",
                p.get("compagnia") or "—",
            ])
    tot_cap = sum(float(p.get("capitale_assicurato") or 0) for p in pir)
    tot_pre = sum(float(p.get("premio_annuo") or 0) for p in pir)
    rows.append(["", "TOTALE", _fmt_eur(tot_cap), _fmt_eur(tot_pre), "", ""])
    el.append(_data_table(["Stato", "Titolo", "Capitale", "Premio €/anno", "Durata", "Compagnia"], rows,
                          [28, 50, 28, 28, 20, 26]))
    return el


SEZIONI = {
    "finanza": ("Situazione Finanziaria", _sez_finanza, False),
    "patrimonio": ("Patrimonio", _sez_patrimonio, False),
    "contesto": ("Contesto & Obiettivi", _sez_contesto, False),
    "redditi": ("Approfondimento Redditi", _sez_redditi, True),
    "pensione": ("Pensione INPS", _sez_pensione, True),
    "scoperture": ("Riepilogo Pensionistico", _sez_scoperture, True),
    "successione": ("Successione", _sez_successione, True),
    "trattativa": ("Trattativa A/B", _sez_trattativa, False),
    "piramide": ("Piramide Soluzioni", _sez_piramide, False),
}


def genera_pdf_sezione(sezione: str, ana: dict, ac: dict, azienda: dict, dati: dict | None = None) -> bytes:
    """Genera il PDF di una singola sezione o di tutte ('all')."""
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=38 * mm, bottomMargin=18 * mm,
    )
    nome_cliente = (f"{ana.get('nome', '') or ''} {ana.get('cognome', '') or ''}").strip() or ana.get("ragione_sociale", "")
    el = []
    dati = dati or {}

    if sezione == "all":
        # Copertina
        el.append(Spacer(1, 50 * mm))
        el.append(Paragraph("Analisi Cliente Completa", s["h1"]))
        el.append(Spacer(1, 8 * mm))
        el.append(Paragraph(f"<b>{nome_cliente.upper()}</b>", s["h2"]))
        el.append(Spacer(1, 6 * mm))
        el.append(Paragraph(f"Codice Fiscale: <b>{ana.get('codice_fiscale') or ana.get('partita_iva') or '—'}</b>", s["body"]))
        el.append(Paragraph(f"Data del report: {datetime.now().strftime('%d/%m/%Y')}", s["body"]))
        el.append(Spacer(1, 30 * mm))
        # Indice
        el.append(Paragraph("<b>Contenuti del Report</b>", s["h3"]))
        for k, (titolo, _, _) in SEZIONI.items():
            el.append(Paragraph(f"• {titolo}", s["body"]))
        el.append(PageBreak())
        # Tutte le sezioni
        for k, (_titolo, fn, needs_dati) in SEZIONI.items():
            try:
                if needs_dati:
                    el += fn(ac, ana, dati, s)
                else:
                    el += fn(ac, ana, s)
            except Exception as e:
                el.append(Paragraph(f"<i>Errore nel rendering della sezione: {e}</i>", s["small"]))
            el.append(PageBreak())
        titolo_doc = "Analisi Cliente Completa"
    else:
        spec = SEZIONI.get(sezione)
        if not spec:
            raise ValueError(f"Sezione sconosciuta: {sezione}")
        _titolo, fn, needs_dati = spec
        if needs_dati:
            el += fn(ac, ana, dati, s)
        else:
            el += fn(ac, ana, s)
        titolo_doc = _titolo

    doc.build(el,
              onFirstPage=_make_header(azienda, titolo_doc, nome_cliente),
              onLaterPages=_make_header(azienda, titolo_doc, nome_cliente))
    return buf.getvalue()
