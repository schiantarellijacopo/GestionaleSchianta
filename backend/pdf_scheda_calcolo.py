"""Generatore PDF per Schede di Calcolo pensionistiche.

Produce un PDF verificabile che riporta, per ogni categoria previdenziale:
- Requisiti d'accesso alla prestazione
- Formule di calcolo utilizzate
- Parametri numerici estratti dai PDF ufficiali (con fonte)
- Confronto e discrepanze rispetto ai criteri del CRM
- Esempio di calcolo passo-passo (se presente)
- Fonti documentali (elenco dei PDF analizzati)

Uso reportlab (già installato per gli altri PDF del CRM).
"""
from __future__ import annotations
import io
from datetime import datetime
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak, KeepTogether,
)


COLORS = {
    "primary": colors.HexColor("#0f172a"),
    "accent": colors.HexColor("#0369a1"),
    "success": colors.HexColor("#059669"),
    "danger": colors.HexColor("#dc2626"),
    "warning": colors.HexColor("#d97706"),
    "muted": colors.HexColor("#64748b"),
    "bg_soft": colors.HexColor("#f1f5f9"),
    "bg_warn": colors.HexColor("#fef3c7"),
    "bg_danger": colors.HexColor("#fee2e2"),
    "bg_ok": colors.HexColor("#dcfce7"),
    "border": colors.HexColor("#cbd5e1"),
}


def _stili():
    s = getSampleStyleSheet()
    styles = {
        "titolo": ParagraphStyle("Titolo", parent=s["Title"],
                                 fontSize=16, textColor=COLORS["primary"],
                                 alignment=TA_LEFT, spaceAfter=2, leading=19),
        "sottotitolo": ParagraphStyle("Sottotitolo", parent=s["Normal"],
                                       fontSize=9, textColor=COLORS["muted"],
                                       spaceAfter=10),
        "h2": ParagraphStyle("H2", parent=s["Heading2"],
                             fontSize=11, textColor=COLORS["accent"],
                             spaceBefore=10, spaceAfter=5, leading=14),
        "h3": ParagraphStyle("H3", parent=s["Heading3"],
                             fontSize=9.5, textColor=COLORS["primary"],
                             spaceBefore=6, spaceAfter=3, leading=12),
        "body": ParagraphStyle("Body", parent=s["Normal"],
                               fontSize=9, textColor=colors.black,
                               leading=12, spaceAfter=3),
        "small": ParagraphStyle("Small", parent=s["Normal"],
                                fontSize=8, textColor=COLORS["muted"],
                                leading=10),
        "code": ParagraphStyle("Code", parent=s["Normal"],
                               fontSize=8.5, textColor=COLORS["primary"],
                               fontName="Courier", leading=11,
                               backColor=COLORS["bg_soft"],
                               borderPadding=4, spaceAfter=4),
        "danger": ParagraphStyle("Danger", parent=s["Normal"],
                                 fontSize=9, textColor=COLORS["danger"],
                                 leading=11.5),
        "warning": ParagraphStyle("Warning", parent=s["Normal"],
                                  fontSize=9, textColor=COLORS["warning"],
                                  leading=11.5),
    }
    return styles


def _kv_table(data: list[tuple[str, str]], col1_w: float = 55) -> Table:
    """Tabella a 2 colonne (chiave|valore) elegante."""
    rows = [[Paragraph(f"<b>{k}</b>", _stili()["body"]),
             Paragraph(v or "—", _stili()["body"])] for k, v in data]
    t = Table(rows, colWidths=[col1_w * mm, (170 - col1_w) * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, COLORS["border"]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (0, -1), COLORS["bg_soft"]),
    ]))
    return t


def _param_row_bg(gravita: str) -> colors.Color:
    return {
        "alta": COLORS["bg_danger"],
        "media": COLORS["bg_warn"],
        "bassa": COLORS["bg_soft"],
    }.get(gravita, COLORS["bg_soft"])


def _sicura(v) -> str:
    """Sanifica una stringa per Paragraph (escape XML)."""
    if v is None:
        return "—"
    s = str(v)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("\n", "<br/>"))


def _stato_badge(stato: str) -> str:
    m = {
        "nuova": '<font color="#059669"><b>NUOVA</b></font>',
        "invariata": '<font color="#059669"><b>INVARIATA</b></font>',
        "cambiata": '<font color="#dc2626"><b>CRITERI CAMBIATI</b></font>',
    }
    return m.get(stato or "", '<font color="#64748b"><b>—</b></font>')


def genera_pdf_scheda_calcolo(scheda: dict, ragione_sociale: str = "Assicura CRM") -> bytes:
    """Genera il PDF completo di una scheda di calcolo previdenziale."""
    st = _stili()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"Scheda di Calcolo — {scheda.get('categoria', '')}",
        author=ragione_sociale,
    )

    story = []
    categoria = scheda.get("categoria", "(senza categoria)")
    anno = scheda.get("anno") or datetime.now().year
    gen_at = str(scheda.get("generated_at") or "")[:10]
    gen_by = scheda.get("generato_da") or "—"
    stato = scheda.get("stato_verifica") or ""
    contenuto = scheda.get("contenuto") or {}

    # ─────────────────── HEADER ───────────────────
    story.append(Paragraph(
        f"Scheda di Calcolo — <b>{_sicura(categoria)}</b>", st["titolo"]))
    story.append(Paragraph(
        f"Anno {anno} · generata il {gen_at} da {_sicura(gen_by)} · "
        f"Stato verifica annuale: {_stato_badge(stato)} · Documento tecnico verificabile",
        st["sottotitolo"]))

    # ─────────────────── SINTESI ───────────────────
    sintesi = contenuto.get("sintesi")
    if sintesi:
        story.append(Paragraph("Sintesi", st["h2"]))
        story.append(Paragraph(_sicura(sintesi), st["body"]))
        story.append(Spacer(1, 4))

    # ─────────────────── DISCREPANZE CRM ───────────────────
    discrepanze = contenuto.get("discrepanze_crm") or []
    if discrepanze:
        story.append(Paragraph(
            f"⚠ Discrepanze con i criteri del CRM ({len(discrepanze)})", st["h2"]))
        story.append(Paragraph(
            "Confronto AI dei parametri estratti dai PDF ufficiali con quelli attualmente "
            "usati dal sistema per il calcolo. Verifica ogni riga prima di considerarla applicabile.",
            st["small"]))
        story.append(Spacer(1, 3))

        header = ["Parametro", "Valore CRM", "Valore documenti", "Gravità", "Correzione suggerita"]
        data = [[Paragraph(f"<b>{h}</b>", st["body"]) for h in header]]
        row_bgs = []
        for d in discrepanze:
            data.append([
                Paragraph(_sicura(d.get("parametro")), st["body"]),
                Paragraph(_sicura(d.get("valore_crm")), st["body"]),
                Paragraph(_sicura(d.get("valore_documenti")), st["body"]),
                Paragraph(_sicura((d.get("gravita") or "").upper()), st["body"]),
                Paragraph(_sicura(d.get("correzione_suggerita")), st["body"]),
            ])
            row_bgs.append(_param_row_bg(d.get("gravita") or ""))

        tbl = Table(data, colWidths=[35 * mm, 30 * mm, 30 * mm, 18 * mm, 61 * mm], repeatRows=1)
        tbl_style = [
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["accent"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, COLORS["border"]),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, bg in enumerate(row_bgs, 1):
            tbl_style.append(("BACKGROUND", (0, i), (-1, i), bg))
        tbl.setStyle(TableStyle(tbl_style))
        story.append(tbl)
        story.append(Spacer(1, 6))

    # ─────────────────── REQUISITI ───────────────────
    requisiti = contenuto.get("requisiti") or []
    if requisiti:
        story.append(Paragraph("Requisiti d'accesso alle prestazioni", st["h2"]))
        rq_data = [[Paragraph("<b>Prestazione</b>", st["body"]),
                    Paragraph("<b>Requisito</b>", st["body"])]]
        for r in requisiti:
            rq_data.append([
                Paragraph(_sicura(r.get("prestazione")), st["body"]),
                Paragraph(_sicura(r.get("requisito")), st["body"]),
            ])
        rq_tbl = Table(rq_data, colWidths=[55 * mm, 119 * mm], repeatRows=1)
        rq_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["accent"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, COLORS["border"]),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, COLORS["bg_soft"]]),
        ]))
        story.append(rq_tbl)
        story.append(Spacer(1, 6))

    # ─────────────────── FORMULE ───────────────────
    formule = contenuto.get("formule") or []
    if formule:
        story.append(Paragraph("Formule di calcolo", st["h2"]))
        for f in formule:
            story.append(Paragraph(
                f"<b>{_sicura(f.get('prestazione'))}</b>", st["h3"]))
            story.append(Paragraph(_sicura(f.get("formula")), st["code"]))
        story.append(Spacer(1, 4))

    # ─────────────────── PARAMETRI NUMERICI ───────────────────
    parametri = contenuto.get("parametri") or []
    if parametri:
        story.append(Paragraph(
            f"Parametri numerici estratti dai documenti ({len(parametri)})", st["h2"]))
        story.append(Paragraph(
            "Ogni parametro riporta la fonte documentale (nome del PDF nella biblioteca) "
            "così da poter risalire alla norma o alla circolare di riferimento.",
            st["small"]))
        story.append(Spacer(1, 3))

        pr_data = [[Paragraph("<b>Nome</b>", st["body"]),
                    Paragraph("<b>Valore</b>", st["body"]),
                    Paragraph("<b>Fonte</b>", st["body"])]]
        for p in parametri:
            pr_data.append([
                Paragraph(_sicura(p.get("nome")), st["body"]),
                Paragraph(_sicura(p.get("valore")), st["body"]),
                Paragraph(_sicura(p.get("fonte")), st["body"]),
            ])
        pr_tbl = Table(pr_data, colWidths=[70 * mm, 40 * mm, 64 * mm], repeatRows=1)
        pr_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["accent"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, COLORS["border"]),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, COLORS["bg_soft"]]),
        ]))
        story.append(pr_tbl)
        story.append(Spacer(1, 6))

    # ─────────────────── MODIFICHE (se scheda cambiata) ───────────────────
    modifiche = scheda.get("modifiche") or []
    if modifiche:
        story.append(Paragraph(
            f"Modifiche rispetto alla scheda precedente ({len(modifiche)})", st["h2"]))
        if scheda.get("spiegazione_modifiche"):
            story.append(Paragraph(_sicura(scheda["spiegazione_modifiche"]), st["body"]))
            story.append(Spacer(1, 3))

        for m in modifiche:
            story.append(Paragraph(
                f"<b>[{_sicura(m.get('sezione', '').upper())}]</b> {_sicura(m.get('criterio'))}",
                st["h3"]))
            story.append(_kv_table([
                ("Prima:", _sicura(m.get("prima"))),
                ("Dopo:", _sicura(m.get("dopo"))),
                ("Impatto sul calcolo:", _sicura(m.get("impatto_sul_calcolo"))),
            ], col1_w=45))
            story.append(Spacer(1, 3))

    # ─────────────────── ESEMPIO CALCOLO PASSO-PASSO ───────────────────
    esempio = contenuto.get("esempio_calcolo") or contenuto.get("esempio")
    if esempio:
        story.append(Paragraph("Esempio di calcolo passo-passo", st["h2"]))
        if isinstance(esempio, str):
            story.append(Paragraph(_sicura(esempio), st["body"]))
        elif isinstance(esempio, list):
            for step in esempio:
                if isinstance(step, dict):
                    story.append(Paragraph(
                        f"<b>{_sicura(step.get('passo'))}</b>: {_sicura(step.get('descrizione'))}",
                        st["body"]))
                    if step.get("formula"):
                        story.append(Paragraph(_sicura(step["formula"]), st["code"]))
                    if step.get("risultato"):
                        story.append(Paragraph(
                            f"→ Risultato: <b>{_sicura(step['risultato'])}</b>", st["body"]))
                else:
                    story.append(Paragraph(_sicura(str(step)), st["body"]))
        story.append(Spacer(1, 6))

    # ─────────────────── FONTI ───────────────────
    fonti = scheda.get("fonti") or []
    if fonti:
        story.append(PageBreak())
        story.append(Paragraph(
            f"Fonti documentali analizzate ({len(fonti)} documenti)", st["h2"]))
        story.append(Paragraph(
            "Elenco dei PDF della biblioteca previdenziale (categoria "
            f"«{_sicura(categoria)}») usati dall'AI per estrarre requisiti, formule e parametri.",
            st["small"]))
        story.append(Spacer(1, 3))
        fo_data = [[Paragraph("<b>#</b>", st["body"]),
                    Paragraph("<b>Nome file</b>", st["body"]),
                    Paragraph("<b>Pagine</b>", st["body"])]]
        for i, f in enumerate(fonti, 1):
            if isinstance(f, dict):
                nome = f.get("nome_file") or f.get("nome") or "—"
                pag = f.get("pagine") or "—"
            else:
                nome = str(f)
                pag = "—"
            fo_data.append([
                Paragraph(str(i), st["body"]),
                Paragraph(_sicura(nome), st["body"]),
                Paragraph(str(pag), st["body"]),
            ])
        fo_tbl = Table(fo_data, colWidths=[10 * mm, 140 * mm, 24 * mm], repeatRows=1)
        fo_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["accent"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, COLORS["border"]),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, COLORS["bg_soft"]]),
        ]))
        story.append(fo_tbl)
        story.append(Spacer(1, 6))

    # ─────────────────── NOTE VERIFICA ANNUALE ───────────────────
    note_verifica = contenuto.get("note_verifica_annuale")
    if note_verifica:
        story.append(Paragraph("Note per la prossima verifica annuale", st["h2"]))
        story.append(Paragraph(_sicura(note_verifica), st["body"]))

    diff = scheda.get("diff_note")
    if diff and not modifiche:
        story.append(Spacer(1, 4))
        story.append(Paragraph("Confronto con scheda precedente", st["h2"]))
        story.append(Paragraph(_sicura(diff), st["body"]))

    # ─────────────────── FOOTER LEGALE ───────────────────
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<i>Documento generato dall'AI del CRM per uso interno di verifica. "
        "Non sostituisce il calcolo ufficiale INPS o della cassa previdenziale. "
        "Verificare sempre i parametri numerici sulle fonti ufficiali indicate.</i>",
        st["small"]))

    doc.build(story)
    return buf.getvalue()
