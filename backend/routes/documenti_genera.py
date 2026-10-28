"""Generazione documenti da modello (per sezione: contraente / polizza / sinistro).

Compila il ``corpo`` di un TemplateModello con i dati reali dell'entità,
produce un PDF e (opzionalmente) lo archivia tra gli allegati dell'entità.
Supporta il segnaposto speciale ``{stato_famiglia}`` per l'autocertificazione,
espanso dai familiari del cliente (campo ``parente_di``).
"""
from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database import db
from auth import current_user
from db_models import Allegato, _now_iso
from storage_service import StorageService

router = APIRouter(tags=["documenti-genera"])

_SEZIONE_ENTITA = {"contraente": "anagrafica", "polizza": "polizza", "sinistro": "sinistro"}


def _fmt_date(v):
    if not v:
        return ""
    s = str(v)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s


def _eur(v):
    try:
        return f"€ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "€ 0,00"


async def _logo_bytes():
    az = await db.azienda_config.find_one({}, {"_id": 0, "logo_storage_path": 1}) or {}
    if az.get("logo_storage_path"):
        try:
            import storage as _s
            data, _ = _s.get_object(az["logo_storage_path"])
            return data
        except Exception:
            return None
    return None


def _nome_completo(a: dict) -> str:
    return a.get("ragione_sociale") or f"{a.get('nome','')} {a.get('cognome','')}".strip()


async def _stato_famiglia(ana: dict) -> str:
    """Elenco numerato dei componenti del nucleo familiare dal campo parente_di."""
    rel = ana.get("parente_di") or []
    if not rel:
        return "(nessun familiare registrato nella scheda Relazione del cliente)"
    righe = []
    for i, r in enumerate(rel, start=1):
        aid = r.get("anagrafica_id")
        parente = await db.anagrafiche.find_one({"id": aid}, {"_id": 0}) if aid else None
        if not parente:
            continue
        nome = _nome_completo(parente)
        luogo = parente.get("comune_nascita") or ""
        data = _fmt_date(parente.get("data_nascita"))
        relazione = (r.get("relazione") or "").capitalize()
        pezzi = [f"{i}) {nome}"]
        if luogo or data:
            pezzi.append(f"nato/a a {luogo} il {data}".strip())
        if relazione:
            pezzi.append(f"grado di parentela: {relazione}")
        righe.append(" — ".join(pezzi))
    return "\n".join(righe) if righe else "(nessun familiare collegato)"


async def _context(entita_tipo: str, entita_id: str, user: dict = None) -> dict:
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    ana = pol = comp = sin = None
    if entita_tipo == "contraente":
        ana = await db.anagrafiche.find_one({"id": entita_id}, {"_id": 0})
        if not ana:
            raise HTTPException(404, "Anagrafica non trovata")
    elif entita_tipo == "polizza":
        pol = await db.polizze.find_one({"id": entita_id}, {"_id": 0})
        if not pol:
            raise HTTPException(404, "Polizza non trovata")
        ana = await db.anagrafiche.find_one({"id": pol.get("contraente_id")}, {"_id": 0}) or {}
        comp = await db.compagnie.find_one({"id": pol.get("compagnia_id")}, {"_id": 0}) or {}
    elif entita_tipo == "sinistro":
        sin = await db.sinistri.find_one({"id": entita_id}, {"_id": 0})
        if not sin:
            raise HTTPException(404, "Sinistro non trovato")
        pol = await db.polizze.find_one({"id": sin.get("polizza_id")}, {"_id": 0}) if sin.get("polizza_id") else {}
        ana = await db.anagrafiche.find_one({"id": sin.get("contraente_id") or (pol or {}).get("contraente_id")}, {"_id": 0}) or {}
        comp = await db.compagnie.find_one({"id": sin.get("compagnia_id") or (pol or {}).get("compagnia_id")}, {"_id": 0}) or {}
    else:
        raise HTTPException(400, "Sezione non valida")

    ana = ana or {}
    pol = pol or {}
    comp = comp or {}
    sin = sin or {}
    nome_intero = _nome_completo(ana)
    ctx = {
        "cliente": nome_intero, "contraente": nome_intero,
        "cliente_nome": ana.get("nome") or ana.get("ragione_sociale") or "",
        "cliente_cognome": ana.get("cognome") or "",
        "cliente_cf": ana.get("codice_fiscale") or "", "cliente_codice_fiscale": ana.get("codice_fiscale") or "",
        "cliente_partita_iva": ana.get("partita_iva") or "",
        "cliente_professione": ana.get("professione") or "",
        "cliente_indirizzo": ana.get("indirizzo") or "", "cliente_comune": ana.get("comune") or "",
        "cliente_cap": ana.get("cap") or "", "cliente_provincia": ana.get("provincia") or "",
        "cliente_telefono": ana.get("telefono") or "", "cliente_cellulare": ana.get("cellulare") or "",
        "cliente_email": ana.get("email") or "", "cliente_iban": ana.get("iban") or "",
        "cliente_data_nascita": _fmt_date(ana.get("data_nascita")),
        "cliente_luogo_nascita": ana.get("comune_nascita") or "",
        "compagnia": comp.get("ragione_sociale") or "", "compagnia_nome": comp.get("ragione_sociale") or "",
        "numero_polizza": pol.get("numero_polizza") or "", "ramo": pol.get("ramo") or pol.get("prodotto") or "",
        "prodotto": pol.get("prodotto") or "", "stato_polizza": pol.get("stato") or "",
        "data_effetto": _fmt_date(pol.get("data_effetto") or pol.get("effetto")),
        "effetto": _fmt_date(pol.get("data_effetto") or pol.get("effetto")),
        "data_scadenza": _fmt_date(pol.get("data_scadenza") or pol.get("scadenza")),
        "scadenza": _fmt_date(pol.get("data_scadenza") or pol.get("scadenza")),
        "premio": _eur(pol.get("premio") or pol.get("premio_netto")),
        "premio_lordo": _eur(pol.get("premio_lordo") or pol.get("ultimo_premio_pagato")),
        "importo": _eur(pol.get("premio_lordo")),
        "numero_sinistro": sin.get("numero_sinistro") or sin.get("numero_interno") or "",
        "data_sinistro": _fmt_date(sin.get("data_avvenimento")),
        "data_denuncia": _fmt_date(sin.get("data_denuncia") or sin.get("data_apertura")),
        "stato_sinistro": sin.get("stato") or "", "descrizione_sinistro": sin.get("descrizione") or "",
        "azienda_nome": az.get("ragione_sociale") or "", "agenzia_nome": az.get("ragione_sociale") or "",
        "azienda_indirizzo": ", ".join([x for x in [az.get("indirizzo"), az.get("cap"), az.get("comune")] if x]),
        "data_oggi": datetime.now().strftime("%d/%m/%Y"),
    }
    # Via/indirizzo cliente (alias) + operatore/intermediario.
    # L'operatore è SEMPRE l'utente loggato che esegue l'operazione (non il
    # collaboratore assegnato al cliente): iscrizione RUI/IVASS, firma, ecc.
    ctx["cliente_via"] = ana.get("indirizzo") or ""
    ctx["cliente_citta"] = ana.get("comune") or ana.get("citta") or ""
    u = {}
    uid = (user or {}).get("id")
    if uid:
        u = await db.users.find_one({"id": uid}, {"_id": 0}) or {}
    if not u:
        # fallback: collaboratore collegato a polizza/cliente
        cid = pol.get("collaboratore_id") or ana.get("collaboratore_id")
        u = (await db.users.find_one({"id": cid}, {"_id": 0}) if cid else None) or {}
    op_sez = u.get("rui_sezione") or az.get("rui_sezione") or ""
    ctx.update({
        "operatore_nome": u.get("name") or u.get("nome") or "",
        "operatore_cognome": u.get("cognome_ragione_sociale") or u.get("cognome") or "",
        "operatore_codice_fiscale": u.get("codice_fiscale") or "",
        "operatore_email": u.get("email") or "",
        "operatore_telefono": u.get("telefono") or "",
        "operatore_rui": u.get("rui") or u.get("rui_numero_iscrizione") or az.get("rui") or "",
        "operatore_sezione": op_sez, "operatore_rui_sezione": op_sez,
        "agenzia_rui": az.get("rui") or "", "agenzia_rui_sezione": az.get("rui_sezione") or "",
    })
    ctx["_firma_operatore_url"] = u.get("firma_digitale_url")
    if entita_tipo == "contraente":
        ctx["stato_famiglia"] = await _stato_famiglia(ana)

    # Garanzie + dati veicolo (per il Documento di polizza)
    gar = pol.get("garanzie") or []
    gar_lines = []
    for g in gar:
        if isinstance(g, dict):
            nome = g.get("nome") or g.get("descrizione") or ""
            extra = g.get("massimale") or g.get("somma_assicurata") or g.get("premio") or ""
            gar_lines.append(f"{nome}: {extra}" if extra else nome)
        elif g:
            gar_lines.append(str(g))
    ctx["garanzie"] = "\n".join(gar_lines) if gar_lines else "(nessuna garanzia specificata)"
    ramo_l = f"{pol.get('ramo') or ''} {pol.get('prodotto') or ''}".lower()
    is_auto = ("auto" in ramo_l or "rca" in ramo_l or "veicol" in ramo_l or bool(pol.get("targa")))
    ctx["targa"] = pol.get("targa") or ""
    ctx["modello"] = pol.get("modello") or pol.get("marca_modello") or pol.get("veicolo") or ""
    ctx["sezione_veicolo"] = (f"DATI VEICOLO\nTarga: {ctx['targa']}\nModello: {ctx['modello']}" if is_auto else "")
    return ctx, ana, pol, comp, sin


def _sub(text: str, ctx: dict) -> str:
    return re.sub(r"\{([a-z_]+)\}", lambda m: str(ctx.get(m.group(1), m.group(0))), text or "")


def _build_pdf(titolo: str, corpo: str, ctx: dict, logo: bytes | None,
               tabelle_map: dict | None = None, firma_op_bytes: bytes | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable,
    )
    from routes.modelli import (
        _TABELLA_RE, _tabella_righe_render, _pdf_build_tabella,
    )
    tabelle_map = tabelle_map or {}

    navy = colors.HexColor("#0f2f4a")
    grey_line = colors.HexColor("#d7dee6")
    label_col = colors.HexColor("#334155")
    ss = getSampleStyleSheet()
    title_st = ParagraphStyle("t", parent=ss["Title"], fontSize=16, leading=20, textColor=navy, alignment=TA_LEFT, spaceAfter=2)
    body_st = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#1f2937"))
    lbl_st = ParagraphStyle("l", parent=body_st, fontName="Helvetica-Bold", textColor=label_col)
    val_st = ParagraphStyle("v", parent=body_st)
    sec_st = ParagraphStyle("s", parent=body_st, fontName="Helvetica-Bold", fontSize=10, textColor=colors.white)
    agency_st = ParagraphStyle("ag", parent=body_st, fontName="Helvetica-Bold", fontSize=11, textColor=navy)

    def esc(t):
        return str(t or "").replace("&", "&amp;").replace("<", "&lt;")

    def is_section(line):
        s = line.strip()
        if not s or ":" in s or len(s) > 48:
            return False
        letters = [c for c in s if c.isalpha()]
        return bool(letters) and s.upper() == s

    testo = _sub(corpo, ctx).replace("\r", "")
    lines = testo.split("\n")

    story = []
    # Intestazione: logo + nome agenzia
    header_left = []
    if logo:
        try:
            img = Image(BytesIO(logo))
            ratio = img.imageWidth / max(img.imageHeight, 1)
            img.drawHeight = 1.3 * cm
            img.drawWidth = 1.3 * cm * ratio
            header_left.append(img)
        except Exception:
            pass
    agency = ctx.get("azienda_nome") or ctx.get("agenzia_nome") or ""
    name_cell = Paragraph(esc(agency), agency_st)
    if header_left:
        htab = Table([[header_left[0], name_cell]], colWidths=[1.6 * cm, None])
        htab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(htab)
    elif agency:
        story.append(name_cell)
    story.append(HRFlowable(width="100%", thickness=1.2, color=navy, spaceBefore=6, spaceAfter=8))

    # Titolo (prima riga in maiuscolo)
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and is_section(lines[idx]):
        story.append(Paragraph(esc(lines[idx].strip()), title_st))
        story.append(Spacer(1, 8))
        idx += 1

    tw = A4[0] - 4 * cm  # larghezza utile
    pending = []  # buffer coppie label/value

    def flush_fields():
        nonlocal pending
        if not pending:
            return
        data = [[Paragraph(esc(l), lbl_st), Paragraph(esc(v), val_st)] for l, v in pending]
        t = Table(data, colWidths=[tw * 0.34, tw * 0.66])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, grey_line),
            ("BOX", (0, 0), (-1, -1), 0.6, grey_line),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f7fa")),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
        pending = []

    def section_bar(text):
        cell = Paragraph(esc(text), sec_st)
        t = Table([[cell]], colWidths=[tw])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), navy),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 5))

    for line in lines[idx:]:
        s = line.strip()
        if not s:
            flush_fields()
            story.append(Spacer(1, 4))
            continue
        # Segnaposto tabella {tabella:slug} → tabella visiva compilata
        mt = _TABELLA_RE.fullmatch(s)
        if mt:
            flush_fields()
            tab = tabelle_map.get(mt.group(1))
            if tab:
                headers, rows, sezioni = _tabella_righe_render(tab, ctx)
                tbl = _pdf_build_tabella(tab, headers, rows, ss, mm, Paragraph,
                                         Table, TableStyle, colors, sezioni)
                if tbl is not None:
                    story.append(tbl)
                    story.append(Spacer(1, 8))
            continue
        # Logo: già presente in intestazione → rimuoviamo il token
        if s == "{logo}":
            flush_fields()
            continue
        # Blocchi firma / data firma
        if s == "{firma_operatore}":
            flush_fields()
            if firma_op_bytes:
                try:
                    fimg = Image(BytesIO(firma_op_bytes))
                    ratio = fimg.imageWidth / max(fimg.imageHeight, 1)
                    fimg.drawHeight = 1.4 * cm
                    fimg.drawWidth = min(6 * cm, 1.4 * cm * ratio)
                    story.append(Spacer(1, 6))
                    story.append(fimg)
                except Exception:
                    story.append(Spacer(1, 10))
            story.append(Paragraph("Firma dell'Intermediario _______________________________", body_st))
            story.append(Spacer(1, 6))
            continue
        if s == "{firma}":
            flush_fields()
            story.append(Spacer(1, 16))
            story.append(Paragraph("Firma del Contraente _______________________________", body_st))
            story.append(Spacer(1, 6))
            continue
        if s == "{data_firma}":
            flush_fields()
            story.append(Paragraph("Data: _______ / _______ / ____________", body_st))
            story.append(Spacer(1, 4))
            continue
        if is_section(s):
            flush_fields()
            section_bar(s)
            continue
        # riga campo "Etichetta: valore" (anche più coppie separate da 2+ spazi)
        segs = re.split(r"\s{2,}", s)
        if len(segs) > 1 and all((":" in seg and len(seg.split(":", 1)[0]) <= 42) for seg in segs):
            for seg in segs:
                label, value = seg.split(":", 1)
                pending.append((label.strip(), value.strip()))
            continue
        if ":" in s and len(s.split(":", 1)[0]) <= 42 and not s.startswith("("):
            label, value = s.split(":", 1)
            pending.append((label.strip(), value.strip()))
            continue
        flush_fields()
        story.append(Paragraph(esc(s), body_st))
        story.append(Spacer(1, 2))
    flush_fields()

    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)
    doc.build(story)
    return out.getvalue()


# Etichetta del blocco firma del contraente (usata come àncora per posizionare
# il riquadro firma OpenAPI esattamente dove compariva il segnaposto {firma}).
_FIRMA_ANCHOR = "Firma del Contraente"


def _find_firma_pos(pdf_bytes: bytes) -> dict | None:
    """Trova la posizione dell'àncora firma nel PDF generato e la converte in
    coordinate OpenAPI (punti, origine in basso a sinistra). Ritorna
    {page, x, y} oppure None se l'àncora non è presente."""
    try:
        import pymupdf as fitz
    except Exception:  # pragma: no cover
        import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            rects = page.search_for(_FIRMA_ANCHOR)
            if rects:
                r = rects[0]
                ph = page.rect.height
                # riquadro firma subito a destra dell'etichetta, allineato alla riga
                x = round(r.x1 + 10)
                y = max(10, round(ph - r.y1 - 2))  # origine bottom-left
                return {"page": page.number + 1, "x": x, "y": y}
    finally:
        doc.close()
    return None


def _applica_override_spunte(tabelle_map: dict, override: dict) -> None:
    """Applica le spunte scelte in anteprima alle tabelle checklist.
    override = {slug: [[bool,...], ...]} (una lista di bool per ogni voce)."""
    if not override:
        return
    for slug, righe_sp in override.items():
        tab = tabelle_map.get(slug)
        if not tab or (tab.get("tipo") or "griglia") != "checklist":
            continue
        voci = tab.get("voci") or []
        for i, voce in enumerate(voci):
            if i < len(righe_sp) and isinstance(righe_sp[i], list):
                voce["spunte"] = [bool(x) for x in righe_sp[i]]


@router.post("/documenti/tabelle-compilabili")
async def tabelle_compilabili(body: dict, user=Depends(current_user)):
    """Ritorna le tabelle di tipo checklist referenziate nel corpo, con le voci e le
    spunte attuali, così l'anteprima può mostrare i flag selezionabili."""
    from routes.modelli import _TABELLA_RE, _load_tabelle_map
    corpo = body.get("corpo") or ""
    slugs = _TABELLA_RE.findall(corpo)
    tabelle_map = await _load_tabelle_map(slugs) if slugs else {}
    out = []
    for slug in dict.fromkeys(slugs):  # preserva l'ordine di comparsa
        tab = tabelle_map.get(slug)
        if not tab or (tab.get("tipo") or "griglia") != "checklist":
            continue
        out.append({
            "slug": slug,
            "nome": tab.get("nome") or slug,
            "colonne": tab.get("colonne") or [],
            "prima_colonna": tab.get("prima_colonna") or "",
            "voci": [{"testo": v.get("testo") or "", "spunte": list(v.get("spunte") or [])}
                     for v in (tab.get("voci") or [])],
        })
    return out




@router.get("/documenti/modelli-sezione")
async def modelli_sezione(sezione: str, user=Depends(current_user)):
    """Modelli disponibili per una sezione (contraente/polizza/sinistro)."""
    if sezione not in _SEZIONE_ENTITA:
        raise HTTPException(400, "Sezione non valida")
    items = await db.template_modelli.find(
        {"sezioni_visibili": sezione, "attivo": {"$ne": False},
         "tipo": {"$in": ["pdf_altro", "pdf", "word", "documento"]}},
        {"_id": 0},
    ).sort("nome", 1).to_list(300)
    return items


@router.post("/documenti/genera")
async def genera_documento(body: dict, user=Depends(current_user)):
    """Genera un PDF da un modello per un'entità. Se salva=true archivia negli allegati."""
    entita_tipo = body.get("entita_tipo")
    entita_id = body.get("entita_id")
    template_id = body.get("template_id")
    if entita_tipo not in _SEZIONE_ENTITA or not entita_id:
        raise HTTPException(400, "entita_tipo/entita_id non validi")

    corpo = body.get("corpo")
    titolo = body.get("titolo") or "Documento"
    if template_id and corpo is None:
        modello = await db.template_modelli.find_one({"id": template_id}, {"_id": 0})
        if not modello:
            raise HTTPException(404, "Modello non trovato")
        corpo = modello.get("corpo", "")
        titolo = body.get("titolo") or modello.get("nome") or "Documento"
    if corpo is None:
        raise HTTPException(400, "Nessun modello o testo fornito")

    ctx, ana, pol, comp, sin = await _context(entita_tipo, entita_id, user)
    logo = await _logo_bytes()
    # Tabelle riutilizzabili {tabella:slug} + firma operatore (immagine)
    from routes.modelli import _TABELLA_RE, _load_tabelle_map, _load_image_from_url
    slugs = _TABELLA_RE.findall(corpo or "")
    tabelle_map = await _load_tabelle_map(slugs) if slugs else {}
    # Override spunte flag per questa generazione (checklist compilate in anteprima)
    _applica_override_spunte(tabelle_map, body.get("tabelle_override") or {})
    firma_op_bytes = await _load_image_from_url(ctx.get("_firma_operatore_url"))
    pdf = _build_pdf(titolo, corpo, ctx, logo, tabelle_map=tabelle_map, firma_op_bytes=firma_op_bytes)

    if not body.get("salva"):
        return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                                 headers={"Content-Disposition": f'inline; filename="{titolo}.pdf"'})

    entita = _SEZIONE_ENTITA[entita_tipo]
    fname = f"{titolo}.pdf"
    stored = await StorageService.put(user=user, entita_tipo=entita, entita_id=entita_id,
                                      filename=f"doc_{entita_id[:8]}.pdf", data=pdf, content_type="application/pdf")
    # La card di destinazione può essere dichiarata a monte nel modello
    # (document_target_card). Se l'operatore non forza una categoria, usiamo
    # quella del modello così il documento (e il PDF firmato) finisce nella card
    # corretta della scheda entità.
    _target_card = None
    if template_id:
        _m = await db.template_modelli.find_one(
            {"id": template_id}, {"_id": 0, "document_target_card": 1})
        _target_card = (_m or {}).get("document_target_card") or None
    categoria = body.get("categoria") or _target_card or "documento_generato"
    alleg = Allegato(entita_tipo=entita, entita_id=entita_id, nome_file=fname,
                     storage_path=stored["storage_path"], storage_provider=stored["storage_provider"],
                     content_type="application/pdf", size=stored.get("size", len(pdf)),
                     categoria=categoria, descrizione=f"Documento generato: {titolo}")
    await db.allegati.insert_one(alleg.model_dump())
    # Posizione del riquadro firma (dove compariva {firma}) per OpenAPI eSignature
    firma_pos = _find_firma_pos(pdf)
    if firma_pos:
        await db.allegati.update_one({"id": alleg.id}, {"$set": {"firma_pos": firma_pos}})
    # Mirror nella card dedicata dell'anagrafica (dict documenti) quando pertinente
    await _mirror_anagrafica_card(entita, entita_id, categoria, alleg, user)
    return {"ok": True, "allegato_id": alleg.id, "nome_file": fname, "firma_pos": firma_pos}


# Card documenti dell'anagrafica gestite come dict `anagrafiche.documenti[card]`
ANAG_DICT_CARDS = {
    "carta_identita", "patente", "passaporto", "codice_fiscale_doc",
    "tessera_sanitaria", "visura_camerale", "mandato_sdd",
    "autocertificazione_stato_famiglia", "privacy_firmata",
}


async def _mirror_anagrafica_card(entita_tipo: str, entita_id: str, categoria: str, alleg, user: dict):
    """Se il documento appartiene a una card dedicata dell'anagrafica, lo rende
    visibile anche nella card (dict `documenti[categoria]`)."""
    if entita_tipo != "anagrafica" or categoria not in ANAG_DICT_CARDS:
        return
    sp = getattr(alleg, "storage_path", None)
    entry = {
        "url": f"/api/storage/{sp}" if sp else None,
        "storage_path": sp,
        "nome_file": getattr(alleg, "nome_file", "documento.pdf"),
        "mime": getattr(alleg, "content_type", "application/pdf"),
        "size_kb": round((getattr(alleg, "size", 0) or 0) / 1024, 1),
        "data_caricamento": _now_iso(),
        "allegato_id": getattr(alleg, "id", None),
        "caricato_da": (user or {}).get("id"),
    }
    await db.anagrafiche.update_one(
        {"id": entita_id},
        {"$set": {f"documenti.{categoria}": entry, "updated_at": _now_iso()}},
    )
