"""Estratto conto contraente — elenco titoli di un contraente (ed eventuali
contraenti collegati) in un periodo, con dati di pagamento e totali.
Genera l'anteprima JSON e il PDF di stampa, replicando il layout richiesto.
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from database import db
from auth import current_user
from db_models import Allegato, _now_iso
from storage_service import StorageService

router = APIRouter()

_GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
_MESI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio",
         "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
_TIPO_COD = {"quietanza": "QU", "appendice": "AP", "rinnovo": "RI", "nuova": "NU",
             "regolazione": "RE", "storno": "ST", "sostituzione": "SO", "annullo": "AN",
             "sospensione": "SP", "ripresa": "RP"}


def _to_iso(d: str | None) -> str | None:
    if not d:
        return None
    d = d.strip()
    if not d:
        return None
    if "-" in d and len(d.split("-")[0]) == 4:
        return d[:10]                       # già ISO
    p = d.replace("/", "-").split("-")
    if len(p) == 3 and len(p[0]) <= 2:      # DD-MM-YYYY
        return f"{p[2]}-{int(p[1]):02d}-{int(p[0]):02d}"
    return d


def _fmt(d: str | None) -> str:
    iso = _to_iso(d)
    if not iso:
        return ""
    try:
        y, m, g = iso[:10].split("-")
        return f"{g}-{m}-{y}"
    except Exception:
        return d or ""


def _eur(v) -> str:
    try:
        return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


def _data_estesa(iso: str) -> str:
    try:
        dt = datetime.strptime(iso[:10], "%Y-%m-%d")
        return f"{_GIORNI[dt.weekday()]} {dt.day} {_MESI[dt.month]} {dt.year}"
    except Exception:
        return iso


async def _build(contraente_id: str, dal: str | None, al: str | None,
                 filtra_per: str, includi_collegati: bool, includi_pagamenti: bool) -> dict:
    ana = await db.anagrafiche.find_one({"id": contraente_id}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Contraente non trovato")

    contr_ids = [contraente_id]
    if includi_collegati:
        for rel in ana.get("parente_di", []) or []:
            rid = rel.get("anagrafica_id")
            if rid and rid not in contr_ids:
                contr_ids.append(rid)

    pols = await db.polizze.find(
        {"contraente_id": {"$in": contr_ids}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "compagnia_id": 1, "ramo": 1,
         "prodotto": 1, "targa": 1, "oggetto_assicurato": 1},
    ).to_list(10000)
    pol_map = {p["id"]: p for p in pols}
    if not pol_map:
        pol_ids = []
    else:
        pol_ids = list(pol_map.keys())

    comp_ids = list({p.get("compagnia_id") for p in pols if p.get("compagnia_id")})
    comp_map = {}
    if comp_ids:
        async for c in db.compagnie.find({"id": {"$in": comp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1}):
            comp_map[c["id"]] = c.get("ragione_sociale", "")

    conti_map = {}
    async for cc in db.conti_cassa.find({}, {"_id": 0, "id": 1, "nome": 1}):
        conti_map[cc["id"]] = cc.get("nome", "")

    field = {"emissione": "data_emissione", "copertura": "data_copertura"}.get(filtra_per, "effetto")
    dal_iso, al_iso = _to_iso(dal), _to_iso(al)

    righe = []
    tot_premi = tot_add = tot_lordo = tot_pagato = 0.0
    if pol_ids:
        cursor = db.titoli.find(
            {"polizza_id": {"$in": pol_ids}, "stato_carico": {"$ne": "annullato_carico"}},
            {"_id": 0},
        )
        titoli = await cursor.to_list(50000)
        for t in titoli:
            dref = _to_iso(t.get(field) or t.get("effetto"))
            if dal_iso and (not dref or dref < dal_iso):
                continue
            if al_iso and (not dref or dref > al_iso):
                continue
            pol = pol_map.get(t.get("polizza_id"), {})
            lordo = float(t.get("importo_lordo") or 0)
            add = float(t.get("accessori") or 0)
            premio = round(lordo - add, 2)
            contratto = pol.get("numero_polizza", "")
            if t.get("numero_titolo"):
                contratto = f"{contratto} - {t['numero_titolo']}"
            pagamento = None
            pagato = 0.0
            if t.get("data_incasso"):
                imp = float(t.get("importo_pagato") if t.get("importo_pagato") is not None else lordo)
                pagato = imp
                mezzo = t.get("mezzo_pagamento") or conti_map.get(t.get("conto_cassa_id")) or ""
                pagamento = {"data": _fmt(t.get("data_incasso")), "importo": imp, "mezzo": mezzo}
            targa_oggetto = " ".join([x for x in [pol.get("targa"), pol.get("oggetto_assicurato")] if x]).strip()
            righe.append({
                "contratto": contratto,
                "rata_del": _fmt(t.get("effetto")),
                "scad_mora": _fmt(t.get("scadenza_mora")),
                "data_copertura": _fmt(t.get("data_copertura")),
                "compagnia": comp_map.get(pol.get("compagnia_id"), ""),
                "rischio": pol.get("prodotto") or pol.get("ramo") or "",
                "premio": premio,
                "addizionali": add,
                "totale": lordo,
                "tipo_cod": _TIPO_COD.get(t.get("tipo"), (t.get("tipo") or "")[:2].upper()),
                "targa_oggetto": targa_oggetto,
                "pagamento": pagamento if includi_pagamenti else None,
                "_sort": _to_iso(t.get("effetto")) or "",
            })
            tot_premi += premio
            tot_add += add
            tot_lordo += lordo
            tot_pagato += pagato

    righe.sort(key=lambda r: r["_sort"], reverse=True)
    for r in righe:
        r.pop("_sort", None)

    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "contraente": {
            "ragione_sociale": ana.get("ragione_sociale")
                or f"{ana.get('nome','')} {ana.get('cognome','')}".strip(),
            "indirizzo": ana.get("indirizzo") or "",
            "cap": ana.get("cap") or "",
            "comune": ana.get("comune") or "",
            "provincia": ana.get("provincia") or "",
            "codice_fiscale": ana.get("codice_fiscale") or ana.get("partita_iva") or "",
        },
        "collegati_inclusi": includi_collegati,
        "n_contraenti": len(contr_ids),
        "dal": _fmt(dal) if dal else "",
        "al": _fmt(al) if al else "",
        "data_emissione": _data_estesa(oggi),
        "righe": righe,
        "totali": {
            "premi": round(tot_premi, 2),
            "addizionali": round(tot_add, 2),
            "totale": round(tot_lordo, 2),
            "gia_pagato": round(tot_pagato, 2),
            "da_pagare": round(tot_lordo - tot_pagato, 2),
        },
    }


@router.get("/estratto-conto-contraente")
async def preview(contraente_id: str, dal: str | None = None, al: str | None = None,
                  filtra_per: str = Query("rata"), includi_collegati: bool = False,
                  includi_pagamenti: bool = True, user=Depends(current_user)):
    return await _build(contraente_id, dal, al, filtra_per, includi_collegati, includi_pagamenti)


@router.get("/estratto-conto-contraente/pdf")
async def pdf(contraente_id: str, dal: str | None = None, al: str | None = None,
              filtra_per: str = Query("rata"), includi_collegati: bool = False,
              includi_pagamenti: bool = True, user=Depends(current_user)):
    data = await _build(contraente_id, dal, al, filtra_per, includi_collegati, includi_pagamenti)
    pdf_bytes = _pdf(data)
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="estratto_conto_{contraente_id[:8]}.pdf"'})


@router.post("/estratto-conto-contraente/salva")
async def salva(contraente_id: str, dal: str | None = None, al: str | None = None,
                filtra_per: str = Query("rata"), includi_collegati: bool = False,
                includi_pagamenti: bool = True, user=Depends(current_user)):
    """Genera il PDF e lo salva come allegato nell'anagrafica del contraente
    (categoria 'estratto_conto' → cartella 'Estratti conto')."""
    data = await _build(contraente_id, dal, al, filtra_per, includi_collegati, includi_pagamenti)
    pdf_bytes = _pdf(data)
    periodo = f"{data['dal'] or ''}_{data['al'] or ''}".replace("-", "").strip("_")
    fname = f"Estratto conto {data['dal'] or ''} - {data['al'] or ''}.pdf".replace("  ", " ")
    stored = await StorageService.put(
        user=user, entita_tipo="anagrafica", entita_id=contraente_id,
        filename=f"estratto_conto_{periodo or contraente_id[:8]}.pdf",
        data=pdf_bytes, content_type="application/pdf")
    alleg = Allegato(entita_tipo="anagrafica", entita_id=contraente_id, anagrafica_id=contraente_id,
                     nome_file=fname, storage_path=stored["storage_path"],
                     storage_provider=stored["storage_provider"], content_type="application/pdf",
                     size=stored.get("size", len(pdf_bytes)), categoria="estratto_conto",
                     descrizione=f"Estratto conto {data['dal']} - {data['al']}")
    await db.allegati.insert_one(alleg.model_dump())
    return {"ok": True, "allegato_id": alleg.id, "nome_file": fname}


def _pdf(data: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)

    c = data["contraente"]
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.4 * cm,
                            leftMargin=1.2 * cm, rightMargin=1.2 * cm, title="Estratto conto")
    ss = getSampleStyleSheet()
    navy = colors.HexColor("#0f2f4a")
    h_name = ParagraphStyle("hn", parent=ss["Title"], fontSize=13, leading=16,
                            alignment=TA_LEFT, textColor=navy, spaceAfter=0)
    h_addr = ParagraphStyle("ha", parent=ss["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"))
    h_meta = ParagraphStyle("hm", parent=ss["BodyText"], fontSize=9, leading=12, spaceBefore=4)
    cell = ParagraphStyle("c", parent=ss["BodyText"], fontSize=6.0, leading=7.5)
    cellr = ParagraphStyle("cr", parent=cell, alignment=2)
    subpay = ParagraphStyle("sp", parent=ss["BodyText"], fontSize=6.0, leading=7.5,
                            textColor=colors.HexColor("#0369a1"))

    def P(t, s=cell):
        return Paragraph(str(t or "").replace("&", "&amp;").replace("<", "&lt;"), s)

    story = [P(c["ragione_sociale"], h_name)]
    if c["indirizzo"]:
        story.append(P(c["indirizzo"], h_addr))
    loc = f"{c['cap']} - {c['comune'].title() if c['comune'] else ''} - {c['provincia']}".strip(" -")
    if loc:
        story.append(P(loc, h_addr))
    story.append(P(f"Data: {data['data_emissione']}", h_meta))
    periodo = f"Estratto conto - DAL: {data['dal'] or '—'} AL {data['al'] or '—'}"
    story.append(P(periodo, h_meta))
    story.append(Spacer(1, 8))

    headers = ["Contratto", "Rata del", "Scad. mora", "Data cop.", "Compagnia",
               "Rischio", "Premio", "Addiz.", "Totale", "Tipo"]
    rows = [[P(h, ParagraphStyle("th", parent=cell, fontName="Helvetica-Bold", fontSize=6.2,
                                 textColor=colors.white, alignment=2 if h in ("Premio", "Addiz.", "Totale") else 0))
             for h in headers]]
    span_rows = []
    for r in data["righe"]:
        rows.append([
            P(r["contratto"]), P(r["rata_del"]), P(r["scad_mora"]), P(r["data_copertura"]),
            P(r["compagnia"]), P(r["rischio"]),
            P(_eur(r["premio"]), cellr), P(_eur(r["addizionali"]), cellr),
            P(_eur(r["totale"]), cellr), P(r["tipo_cod"]),
        ])
        # righe extra (targa/oggetto e pagamenti)
        extra = []
        if r.get("targa_oggetto"):
            extra.append(P(r["targa_oggetto"], subpay))
        if r.get("pagamento"):
            pg = r["pagamento"]
            extra.append(P(f"Pagamento: {pg['data']} - € {_eur(pg['importo'])} - {pg['mezzo']}", subpay))
        if extra:
            idx = len(rows)
            rows.append([extra, "", "", "", "", "", "", "", "", ""])
            span_rows.append(idx)

    colw = [c * cm for c in [2.2, 1.55, 1.55, 1.55, 2.5, 3.0, 1.6, 1.55, 1.7, 0.75]]
    t = Table(rows, colWidths=colw, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]
    for idx in span_rows:
        style.append(("SPAN", (0, idx), (-1, idx)))
        style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#eff6ff")))
    t.setStyle(TableStyle(style))
    story.append(t)

    # Totali
    story.append(Spacer(1, 6))
    tt = data["totali"]
    bold = ParagraphStyle("b", parent=cell, fontName="Helvetica-Bold", fontSize=6.5, alignment=2)
    tot_tbl = Table([
        [P("Totale", ParagraphStyle("l", parent=bold, alignment=0)), P(_eur(tt["premi"]), bold),
         P(_eur(tt["addizionali"]), bold), P(_eur(tt["totale"]), bold)],
    ], colWidths=[c * cm for c in [12.35, 1.6, 1.55, 1.7]])
    tot_tbl.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, navy),
                                 ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    story.append(tot_tbl)
    story.append(Spacer(1, 6))
    riep = ParagraphStyle("rp", parent=ss["BodyText"], fontSize=9, leading=13)
    riep_b = ParagraphStyle("rpb", parent=riep, fontName="Helvetica-Bold", textColor=navy)
    story.append(P(f"Totale premi: € {_eur(tt['premi'])}", riep))
    story.append(P(f"Totale addizionali: € {_eur(tt['addizionali'])}", riep))
    story.append(P(f"Totale già pagato: € {_eur(tt['gia_pagato'])}", riep))
    story.append(P(f"DA PAGARE: € {_eur(tt['da_pagare'])}", riep_b))

    doc.build(story)
    return buf.getvalue()
