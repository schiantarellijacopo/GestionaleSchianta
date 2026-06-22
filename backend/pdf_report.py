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
    logo_bytes: bytes | None = None,
    indirizzo_azienda: str | None = None,
    contatti_azienda: str | None = None,
    note_footer: str | None = None,
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
    # Intestazione con logo + dati azienda (se presenti)
    intestazione_dx = [Paragraph(f"<b>{ragione_sociale}</b>", sub_style)]
    if indirizzo_azienda:
        intestazione_dx.append(Paragraph(indirizzo_azienda, sub_style))
    if contatti_azienda:
        intestazione_dx.append(Paragraph(contatti_azienda, sub_style))

    if logo_bytes:
        try:
            from reportlab.platypus import Image
            from reportlab.lib.utils import ImageReader  # noqa: F401
            logo_buf = io.BytesIO(logo_bytes)
            img = Image(logo_buf, width=25 * mm, height=15 * mm, kind="proportional")
            header_table = Table([[img, intestazione_dx]], colWidths=[30 * mm, None])
            header_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            el.append(header_table)
        except Exception:
            for p in intestazione_dx:
                el.append(p)
    else:
        for p in intestazione_dx:
            el.append(p)

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
    if note_footer:
        el.append(Paragraph(note_footer, foot_style))
    el.append(Paragraph(
        f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')} · {len(rows)} righe",
        foot_style,
    ))
    doc.build(el)
    buf.seek(0)
    return buf.read()


async def get_intestazione_azienda(db) -> dict:
    """Recupera dati azienda + logo per le stampe. Ritorna kwargs da passare a stampa_elenco."""
    cfg = await db.azienda_config.find_one({}, {"_id": 0})
    if not cfg:
        return {}
    kwargs = {
        "ragione_sociale": cfg.get("ragione_sociale") or "Assicura - Gestione Agenzia",
    }
    # Indirizzo
    indirizzo_parts = []
    if cfg.get("indirizzo"):
        indirizzo_parts.append(cfg["indirizzo"])
    loc_parts = []
    if cfg.get("cap"):
        loc_parts.append(cfg["cap"])
    if cfg.get("comune"):
        loc_parts.append(cfg["comune"])
    if cfg.get("provincia"):
        loc_parts.append(f"({cfg['provincia']})")
    if loc_parts:
        indirizzo_parts.append(" ".join(loc_parts))
    if indirizzo_parts:
        kwargs["indirizzo_azienda"] = " · ".join(indirizzo_parts)
    # Contatti
    contatti = []
    if cfg.get("partita_iva"):
        contatti.append(f"P.IVA {cfg['partita_iva']}")
    if cfg.get("rui"):
        sez = f" sez. {cfg['rui_sezione']}" if cfg.get("rui_sezione") else ""
        contatti.append(f"RUI {cfg['rui']}{sez}")
    if cfg.get("telefono"):
        contatti.append(f"Tel {cfg['telefono']}")
    if cfg.get("email"):
        contatti.append(cfg["email"])
    if contatti:
        kwargs["contatti_azienda"] = " · ".join(contatti)
    if cfg.get("note_footer_stampe"):
        kwargs["note_footer"] = cfg["note_footer_stampe"]
    # Logo (caricato dallo storage se presente)
    if cfg.get("logo_storage_path"):
        try:
            import storage as _storage
            data, _ct = _storage.get_object(cfg["logo_storage_path"])
            kwargs["logo_bytes"] = data
        except Exception:
            pass
    return kwargs
