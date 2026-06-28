"""Helper condiviso per inserire branding (logo + nome agenzia) nei PDF.

Usato da pdf_lettera_abbuono, pdf_brogliaccio, pdf_diagnosi, pdf_avviso.
"""
from __future__ import annotations

import io
import urllib.request

from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors


def _safe_logo_flowable(logo_url: str | None, *, width_mm: float = 22, height_mm: float = 22):
    """Scarica/legge il logo e ritorna un Image flowable (o None)."""
    if not logo_url:
        return None
    try:
        if logo_url.startswith(("http://", "https://")):
            req = urllib.request.Request(logo_url, headers={"User-Agent": "Assicura/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            return Image(io.BytesIO(data), width=width_mm * mm,
                          height=height_mm * mm, kind="proportional")
        if logo_url.startswith("/"):
            return Image(logo_url, width=width_mm * mm,
                          height=height_mm * mm, kind="proportional")
    except Exception:
        return None
    return None


def header_branding(azienda: dict, *, with_motto: bool = True) -> list:
    """Ritorna lista di flowables: logo + nome + motto."""
    out: list = []
    logo = _safe_logo_flowable(azienda.get("logo_url"))
    if logo:
        out.append(logo)
        out.append(Spacer(1, 2 * mm))
    nome = azienda.get("ragione_sociale") or "Agenzia Assicurativa"
    style_name = ParagraphStyle(
        "branding_name", fontSize=14, leading=18, alignment=1,
        textColor=colors.HexColor("#1f2937"), fontName="Helvetica-Bold",
    )
    out.append(Paragraph(nome, style_name))
    if with_motto and azienda.get("note_footer_stampe"):
        style_motto = ParagraphStyle(
            "branding_motto", fontSize=8, leading=10, alignment=1,
            textColor=colors.HexColor("#64748b"), fontName="Helvetica-Oblique",
        )
        out.append(Paragraph(azienda["note_footer_stampe"][:120], style_motto))
    out.append(Spacer(1, 4 * mm))
    return out
