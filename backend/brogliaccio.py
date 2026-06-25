"""Generazione PDF Brogliaccio (prima nota) formato giornaliero.

Refactor: il flusso monolitico è stato spezzato in helper testabili
(carico dati, classificazione movimento, costruzione tabelle).
"""
from __future__ import annotations
import io
from datetime import date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
BASE_HEADERS = ["Descrizione", "Totale", "Provv", "Saldo", "Crediti", "Spese"]
CATEGORIE_USCITA = ("rimborso_cliente", "spese_amministrative", "pagamento_compagnia")


# ---------------------------------------------------------------------------
# Helpers di formattazione
# ---------------------------------------------------------------------------
def _fmt(n: float | None) -> str:
    if n is None or n == 0:
        return ""
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Caricamento dati
# ---------------------------------------------------------------------------
async def _load_movimenti_arricchiti(db, data_giorno: str) -> tuple[list[dict], dict, dict, dict]:
    """Carica i movimenti del giorno con le mappe polizze/anagrafiche/compagnie.

    Returns:
        (movs, polizze_map, anagrafiche_map, compagnie_map)
    """
    movs = await db.movimenti.find(
        {"data_movimento": data_giorno}, {"_id": 0}
    ).sort("data_registrazione", 1).to_list(2000)

    pol_ids = list({m["polizza_id"] for m in movs if m.get("polizza_id")})
    ana_ids = list({m["anagrafica_id"] for m in movs if m.get("anagrafica_id")})
    com_ids = list({m["compagnia_id"] for m in movs if m.get("compagnia_id")})

    polizze = {
        p["id"]: p async for p in db.polizze.find(
            {"id": {"$in": pol_ids}},
            {"_id": 0, "id": 1, "numero_polizza": 1, "compagnia_id": 1},
        )
    }
    anagrafiche = {
        a["id"]: a async for a in db.anagrafiche.find(
            {"id": {"$in": ana_ids}},
            {"_id": 0, "id": 1, "ragione_sociale": 1},
        )
    }
    compagnie_query_ids = com_ids + [p.get("compagnia_id") for p in polizze.values()]
    compagnie = {
        c["id"]: c async for c in db.compagnie.find(
            {"id": {"$in": compagnie_query_ids}},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1},
        )
    }
    return movs, polizze, anagrafiche, compagnie


# ---------------------------------------------------------------------------
# Classificazione movimento → totali colonna
# ---------------------------------------------------------------------------
def _classifica_movimento(m: dict) -> dict[str, float]:
    """Ritorna i totali colonna {totale, prov, saldo, crediti, spese} per UN movimento."""
    importo = m.get("importo", 0.0) or 0.0
    prov = m.get("provvigioni", 0.0) or 0.0
    cat = m.get("categoria")

    if cat == "incasso_premio":
        return {"totale": importo, "prov": prov, "saldo": importo - prov,
                "crediti": 0.0, "spese": 0.0}
    if cat in CATEGORIE_USCITA:
        return {"totale": 0.0, "prov": 0.0, "saldo": 0.0,
                "crediti": 0.0, "spese": importo}
    if cat == "provvigioni":
        return {"totale": 0.0, "prov": 0.0, "saldo": 0.0,
                "crediti": importo, "spese": 0.0}
    # default: entrata/uscita generica
    is_entrata = m.get("tipo") == "entrata"
    totale = importo if is_entrata else 0.0
    spese = importo if not is_entrata else 0.0
    return {"totale": totale, "prov": 0.0, "saldo": totale,
            "crediti": 0.0, "spese": spese}


def _descrizione_movimento(m: dict, pol: dict, ana: dict, com: dict) -> str:
    """Costruisce la descrizione testuale di una riga (max 55 chars)."""
    parts: list[str] = []
    if pol.get("numero_polizza"):
        parts.append(f"N. {pol['numero_polizza']}")
    if ana.get("ragione_sociale"):
        parts.append(ana["ragione_sociale"])
    if com.get("ragione_sociale"):
        parts.append(com["ragione_sociale"].upper().split()[0])
    if not parts:
        parts.append((m.get("descrizione") or "")[:60])
    return " - ".join(parts)[:55]


def _celle_conti_cassa(m: dict, conti_attivi: list[dict],
                       tot_per_conto: dict[str, float]) -> list[str]:
    """Calcola le celle per le colonne 'conto cassa' di una riga.

    Aggiorna in-place il dict `tot_per_conto` con il segno (entrata=+, uscita=-).
    """
    importo = m.get("importo", 0.0) or 0.0
    signed_amount = importo if m.get("tipo") == "entrata" else -importo
    cells: list[str] = []
    for c in conti_attivi:
        if m.get("conto_cassa_id") == c["id"]:
            cells.append(_fmt(signed_amount))
            tot_per_conto[c["id"]] += signed_amount
        else:
            cells.append("")
    return cells


# ---------------------------------------------------------------------------
# Costruzione righe tabella principale
# ---------------------------------------------------------------------------
def _build_righe_dettaglio(
    movs: list[dict], polizze: dict, anagrafiche: dict, compagnie: dict,
    conti_attivi: list[dict],
) -> tuple[list[list], dict[str, float], dict[str, float]]:
    """Costruisce le righe della tabella e i totali.

    Returns:
        (rows, totali_globali, tot_per_conto)
    """
    totali = {"totale": 0.0, "prov": 0.0, "saldo": 0.0, "crediti": 0.0, "spese": 0.0}
    tot_per_conto = {c["id"]: 0.0 for c in conti_attivi}
    rows: list[list] = []

    for m in movs:
        pol = polizze.get(m.get("polizza_id", "")) or {}
        ana = anagrafiche.get(m.get("anagrafica_id") or pol.get("contraente_id", "")) or {}
        com = compagnie.get(m.get("compagnia_id") or pol.get("compagnia_id", "")) or {}

        desc = _descrizione_movimento(m, pol, ana, com)
        cls = _classifica_movimento(m)
        for k, v in cls.items():
            totali[k] += v
        bank_cells = _celle_conti_cassa(m, conti_attivi, tot_per_conto)

        rows.append([desc, _fmt(cls["totale"]), _fmt(cls["prov"]),
                     _fmt(cls["saldo"]), _fmt(cls["crediti"]), _fmt(cls["spese"])]
                    + bank_cells)
    return rows, totali, tot_per_conto


def _calcola_col_widths(n_bank: int) -> list:
    """Calcola le larghezze colonne adattive in mm."""
    base = [55 * mm] + [16 * mm] * 5
    if n_bank == 0:
        return base
    free = 280 * mm - 55 * mm - 16 * mm * 5
    bank_w = max(14 * mm, free / n_bank)
    if sum(base) + bank_w * n_bank > 280 * mm:
        bank_w = free / n_bank
    return base + [bank_w] * n_bank


def _stile_tabella_principale() -> TableStyle:
    return TableStyle([
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
    ])


def _build_tabella_principale(headers: list[str], rows: list[list],
                              totali: dict, tot_per_conto: dict,
                              conti_attivi: list[dict]) -> Table:
    riga_totale = (
        ["TOTALE GIORNATA",
         _fmt(totali["totale"]), _fmt(totali["prov"]), _fmt(totali["saldo"]),
         _fmt(totali["crediti"]), _fmt(totali["spese"])]
        + [_fmt(tot_per_conto[c["id"]]) for c in conti_attivi]
    )
    full_rows = [headers] + rows + [riga_totale]
    col_w = _calcola_col_widths(len(conti_attivi))[:len(headers)]
    tbl = Table(full_rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(_stile_tabella_principale())
    return tbl


def _build_tabella_riepilogo(conti_attivi: list[dict],
                             tot_per_conto: dict[str, float]) -> Table:
    rows = [["Conto", "Imp. precedente", "Imp. giornata", "Totale periodo"]]
    for c in conti_attivi:
        prec = c.get("saldo_iniziale", 0.0)
        gg = tot_per_conto[c["id"]]
        rows.append([c["nome"], _fmt(prec), _fmt(gg), _fmt(prec + gg)])
    tbl = Table(rows, colWidths=[80 * mm, 40 * mm, 40 * mm, 40 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
    ]))
    return tbl


# ---------------------------------------------------------------------------
# Entrypoint pubblico
# ---------------------------------------------------------------------------
async def genera_brogliaccio_pdf(db, data_giorno: str, conti: list[dict],
                                 ragione_sociale: str = "Assicura - Gestione Agenzia") -> bytes:
    """Genera il PDF del Brogliaccio del giorno.

    Args:
        db: handle Motor.
        data_giorno: 'YYYY-MM-DD'.
        conti: lista di Conti Cassa attivi (dict con id, nome, saldo_precedente).
        ragione_sociale: header documento.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    h_style = ParagraphStyle("h", parent=styles["Heading1"], fontSize=14, alignment=1, spaceAfter=2)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, alignment=1,
                               textColor=colors.HexColor("#475569"))

    elements: list = []
    elements.append(Paragraph(f"<b>{ragione_sociale}</b>", h_style))
    d = date.fromisoformat(data_giorno)
    elements.append(Paragraph(f"Brogliaccio del {d.strftime('%d-%m-%Y')}", sub_style))
    elements.append(Spacer(1, 4 * mm))

    movs, polizze, anagrafiche, compagnie = await _load_movimenti_arricchiti(db, data_giorno)

    conti_attivi = [c for c in conti if c.get("attivo", True)]
    bank_headers = [c["nome"].upper()[:14] for c in conti_attivi]
    headers = BASE_HEADERS + bank_headers

    rows, totali, tot_per_conto = _build_righe_dettaglio(
        movs, polizze, anagrafiche, compagnie, conti_attivi,
    )
    elements.append(_build_tabella_principale(headers, rows, totali, tot_per_conto, conti_attivi))
    elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph("<b>Riepilogo conti</b>", styles["Heading4"]))
    elements.append(_build_tabella_riepilogo(conti_attivi, tot_per_conto))

    doc.build(elements)
    buf.seek(0)
    return buf.read()
