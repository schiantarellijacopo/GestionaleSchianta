"""Contratto di consulenza assicurativa — precompilazione, modifica, firma OTP, PDF."""
from __future__ import annotations
import hashlib, random, re
from io import BytesIO
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from database import db
from auth import current_user
from db_models import _now_iso, Allegato
from storage_service import StorageService
import contratto_render

router = APIRouter()


async def _logo_bytes() -> bytes | None:
    az = await db.azienda_config.find_one({}, {"_id": 0, "logo_storage_path": 1}) or {}
    if az.get("logo_storage_path"):
        try:
            import storage as _storage
            data, _ct = _storage.get_object(az["logo_storage_path"])
            return data
        except Exception:
            return None
    return None


def _cliente_nome(ana: dict) -> str:
    if ana.get("tipo") == "persona_giuridica":
        return ana.get("ragione_sociale", "")
    return (f"{ana.get('nome','')} {ana.get('cognome','')}".strip() or ana.get("ragione_sociale", ""))


def _sostituisci_placeholder(testo: str, ana: dict, cons: dict, importo: float,
                             luogo: str = "", data: str = "") -> str:
    """Risolve i placeholder {campo} nel testo con i dati reali di cliente/consulente."""
    imp = int(round(importo or 0))
    corr = "a titolo gratuito" if imp == 0 else (f"€ {imp:,.0f}".replace(",", ".") + f" ({_intero_lettere(imp)})")
    indirizzo = ", ".join([x for x in [ana.get("indirizzo"), ana.get("comune"), ana.get("cap")] if x])
    mapping = {
        "{cliente}": _cliente_nome(ana),
        "{codice_fiscale}": ana.get("codice_fiscale") or "",
        "{partita_iva}": ana.get("partita_iva") or "",
        "{indirizzo}": indirizzo,
        "{email}": ana.get("email") or "",
        "{cellulare}": ana.get("cellulare") or ana.get("telefono") or "",
        "{consulente}": cons.get("ragione_sociale") or "",
        "{rui}": cons.get("rui") or "",
        "{importo}": corr,
        "{luogo}": luogo or ana.get("comune") or "",
        "{data}": data or "",
    }
    out = testo or ""
    for k, v in mapping.items():
        out = out.replace(k, v)
    return out



def _intero_lettere(n: int) -> str:
    if n == 0:
        return "zero euro (a titolo gratuito)"
    u = ["", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci",
         "undici", "dodici", "tredici", "quattordici", "quindici", "sedici", "diciassette",
         "diciotto", "diciannove"]
    d = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta"]
    def sotto100(x):
        if x < 20: return u[x]
        dec, un = divmod(x, 10)
        base = d[dec]
        if un == 1 or un == 8:
            base = base[:-1]
        return base + u[un]
    def sotto1000(x):
        cent, r = divmod(x, 100)
        pre = "" if cent == 0 else ("cento" if cent == 1 else u[cent] + "cento")
        return pre + sotto100(r)
    if n < 1000:
        return sotto1000(n) + " euro"
    migl, r = divmod(n, 1000)
    pre = "mille" if migl == 1 else sotto1000(migl) + "mila"
    return (pre + sotto1000(r)).strip() + " euro"


async def _consulente_info(user: dict) -> dict:
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    rui = az.get("rui") or ""
    sez = az.get("rui_sezione") or ""
    return {
        "ragione_sociale": az.get("ragione_sociale") or "—",
        "partita_iva": az.get("partita_iva") or "",
        "sede": az.get("sede") or az.get("indirizzo") or "",
        "rui": (f"RUI n. {rui}" + (f" sez. {sez}" if sez else "")) if rui else "iscritto nel Registro Unico degli Intermediari (RUI)",
        "operatore": (user.get("ragione_sociale") or f"{user.get('nome','')} {user.get('cognome','')}").strip() or user.get("email", ""),
    }


def _costruisci_testo(ana: dict, cons: dict, importo: float) -> str:
    az = ana.get("tipo") == "persona_giuridica"
    if az:
        cliente = f"La società {ana.get('ragione_sociale','')}, partita I.V.A. {ana.get('partita_iva','')}"
        rappr = ana.get("amministratore") or "[Legale rappresentante]"
        qual = "Legale rappresentante"
    else:
        nome = f"{ana.get('nome','')} {ana.get('cognome','')}".strip() or ana.get("ragione_sociale", "")
        cliente = f"Il/La Sig./Sig.ra {nome}, codice fiscale {ana.get('codice_fiscale','')}"
        rappr = nome
        qual = "In proprio"
    sede_cl = ", ".join([x for x in [ana.get("indirizzo"), ana.get("comune"), ana.get("cap")] if x])
    imp = int(round(importo or 0))
    corr = "a titolo gratuito" if imp == 0 else f"€ {imp:,.0f}".replace(",", ".") + f" ({_intero_lettere(imp)})"
    return f"""INCARICO DI CONSULENZA IN MATERIA ASSICURATIVA

Tra
{cliente}
con sede in {sede_cl or '—'} (di seguito anche solo il "Cliente")
e
{cons['ragione_sociale']}, partita I.V.A. {cons['partita_iva']}, con sede in {cons['sede'] or '—'},
{cons['rui']} (di seguito anche solo il "Consulente")

premesso che
a) il Consulente è un intermediario assicurativo, regolarmente iscritto nel Registro di cui all'art. 109 del d.lgs. 209/2005;
b) il Consulente opera nella distribuzione assicurativa fornendo assistenza e consulenza nell'individuazione delle coperture più idonee;
c) il Consulente è dotato della struttura, delle competenze e della professionalità necessarie;
d) il Cliente ha manifestato l'interesse a ricevere una raccomandazione personalizzata;

si stipula quanto segue

Art. 1 (Oggetto) — Il Cliente conferisce al Consulente incarico di fornire una prestazione di consulenza in materia assicurativa.

Art. 2 (Attività di consulenza) — Previa raccolta delle informazioni necessarie: (i) analisi di dati e documentazione, con riguardo alle coperture già in essere; (ii) formulazione di una raccomandazione personalizzata sui prodotti più adeguati. Il Cliente resta libero di non dar corso alle raccomandazioni.

Art. 3 (Collaboratori) — Il Consulente può avvalersi di sostituti e/o ausiliari sotto la propria responsabilità.

Art. 4 (Corrispettivo) — Quale corrispettivo per l'attività di consulenza il Cliente corrisponderà al Consulente {corr}. Tale corrispettivo è ritenuto adeguato all'importanza dell'opera.

Art. 5 (Durata e recesso) — L'incarico decorre dalla sottoscrizione fino al completamento delle attività di cui all'art. 2. Ciascuna parte può recedere con preavviso di 30 giorni tramite raccomandata a.r./pec.

Art. 6 (Obblighi delle parti) — Il Consulente opera secondo diligenza e nel rispetto del d.lgs. 209/2005 e reg. IVASS 40/2018. Il Cliente si impegna a fornire informazioni complete e veritiere.

Art. 7 (Riservatezza e dati personali) — Trattamento dei dati nel rispetto del reg. UE 2016/679 (GDPR) e d.lgs. 196/2003.

Art. 8 (Responsabilità) — Obbligazione di mezzi e non di risultato; responsabilità limitata al compenso corrisposto, salvo dolo o colpa grave.

Art. 9 (Foro esclusivo) — Foro competente in via esclusiva quello della sede del Consulente.

Art. 10 (Rinvio) — Per quanto non previsto si rinvia alla normativa vigente.

Operatore incaricato: {cons['operatore']}
Corrispettivo pattuito: {corr}

Firma Cliente: {rappr} ({qual})
Firma Consulente: {cons['ragione_sociale']}
"""


@router.get("/anagrafiche/{aid}/contratto-consulenza")
async def get_contratto(aid: str, user=Depends(current_user)):
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    cc = ana.get("contratto_consulenza")
    cons = await _consulente_info(user)
    if cc and cc.get("testo"):
        return {**cc, "consulente": cons}
    importo = 0
    return {
        "testo": _costruisci_testo(ana, cons, importo),
        "importo": importo, "stato": "bozza",
        "consulente": cons, "tipo": ana.get("tipo"),
    }


@router.put("/anagrafiche/{aid}/contratto-consulenza")
async def save_contratto(aid: str, body: dict, user=Depends(current_user)):
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "id": 1, "contratto_consulenza": 1})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    prev = ana.get("contratto_consulenza") or {}
    cc = {
        **prev,
        "testo": body.get("testo") or prev.get("testo") or "",
        "importo": float(body.get("importo") or 0),
        "stato": prev.get("stato") if prev.get("stato") == "firmato" else "bozza",
        "aggiornato_il": _now_iso(),
    }
    await db.anagrafiche.update_one({"id": aid}, {"$set": {"contratto_consulenza": cc}})
    return cc


@router.post("/anagrafiche/{aid}/contratto-consulenza/invia-otp")
async def invia_otp(aid: str, body: dict, user=Depends(current_user)):
    canale = (body.get("canale") or "whatsapp").lower()
    ana = await db.anagrafiche.find_one(
        {"id": aid}, {"_id": 0, "cellulare": 1, "telefono": 1, "email": 1, "contratto_consulenza": 1})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    otp = f"{random.randint(0, 999999):06d}"
    scade = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    cc = ana.get("contratto_consulenza") or {}
    cc["otp_hash"] = hashlib.sha256(otp.encode()).hexdigest()
    cc["otp_scade"] = scade
    cc["otp_canale"] = canale
    await db.anagrafiche.update_one({"id": aid}, {"$set": {"contratto_consulenza": cc}})
    inviato = False
    msg = f"Il tuo codice per firmare il contratto di consulenza è: {otp} (valido 10 minuti)."
    try:
        if canale == "whatsapp":
            import routes.whatsapp_evo as wa
            num = re.sub(r"\D", "", ana.get("cellulare") or ana.get("telefono") or "")
            if num and hasattr(wa, "invia_messaggio_diretto"):
                await wa.invia_messaggio_diretto(num, msg)
                inviato = True
    except Exception:
        inviato = False
    dest = {"whatsapp": ana.get("cellulare") or ana.get("telefono"),
            "sms": ana.get("cellulare") or ana.get("telefono"),
            "email": ana.get("email")}.get(canale)
    # In assenza di consegna confermata, restituiamo il codice così l'operatore può dettarlo
    return {"ok": True, "canale": canale, "destinatario": dest,
            "inviato": inviato, "scade": scade,
            "otp_debug": None if inviato else otp}


@router.post("/anagrafiche/{aid}/contratto-consulenza/firma-otp")
async def firma_otp(aid: str, body: dict, user=Depends(current_user)):
    otp = (body.get("otp") or "").strip()
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    cc = ana.get("contratto_consulenza") or {}
    if not cc.get("otp_hash"):
        raise HTTPException(400, "Nessun OTP richiesto. Invia prima il codice.")
    if cc.get("otp_scade") and cc["otp_scade"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(400, "Codice OTP scaduto. Richiedine uno nuovo.")
    if hashlib.sha256(otp.encode()).hexdigest() != cc["otp_hash"]:
        raise HTTPException(400, "Codice OTP errato.")
    # genera PDF impaginato professionale
    cons = await _consulente_info(user)
    logo = await _logo_bytes()
    testo_finale = _sostituisci_placeholder(cc.get("testo") or "", ana, cons, float(cc.get("importo") or 0))
    pdf = contratto_render.build_pdf(
        testo_finale, consulente=cons, cliente_nome=_cliente_nome(ana),
        logo_bytes=logo, firmato=True, firmato_il=_now_iso(),
        firmato_via=cc.get("otp_canale") or "otp")
    stored = await StorageService.put(
        user=user, entita_tipo="anagrafica", entita_id=aid,
        filename=f"Contratto_consulenza_{aid[:8]}.pdf", data=pdf, content_type="application/pdf")
    alleg = Allegato(entita_tipo="anagrafica", entita_id=aid, anagrafica_id=aid,
                     nome_file=f"Contratto consulenza firmato.pdf",
                     storage_path=stored["storage_path"], storage_provider=stored["storage_provider"],
                     content_type="application/pdf", size=stored.get("size", len(pdf)),
                     categoria="contratto", visibile_cliente=True,
                     descrizione="Contratto di consulenza firmato via OTP")
    await db.allegati.insert_one(alleg.model_dump())
    cc.update({"stato": "firmato", "firmato_il": _now_iso(),
               "firmato_via": cc.get("otp_canale") or "otp", "allegato_id": alleg.id,
               "otp_hash": None, "otp_scade": None})
    await db.anagrafiche.update_one({"id": aid}, {"$set": {"contratto_consulenza": cc}})
    return {"ok": True, "stato": "firmato", "allegato_id": alleg.id, "firmato_il": cc["firmato_il"]}


async def _render_data(aid: str, user):
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    cc = ana.get("contratto_consulenza") or {}
    testo = cc.get("testo")
    cons = await _consulente_info(user)
    if not testo:
        testo = _costruisci_testo(ana, cons, float(cc.get("importo") or 0))
    testo = _sostituisci_placeholder(testo, ana, cons, float(cc.get("importo") or 0))
    return ana, cc, testo, cons


@router.get("/anagrafiche/{aid}/contratto-consulenza/pdf")
async def download_pdf(aid: str, user=Depends(current_user)):
    ana, cc, testo, cons = await _render_data(aid, user)
    logo = await _logo_bytes()
    pdf = contratto_render.build_pdf(
        testo, consulente=cons, cliente_nome=_cliente_nome(ana), logo_bytes=logo,
        firmato=cc.get("stato") == "firmato", firmato_il=cc.get("firmato_il") or "",
        firmato_via=cc.get("firmato_via") or "")
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="Contratto_consulenza_{aid[:8]}.pdf"'})


@router.get("/anagrafiche/{aid}/contratto-consulenza/docx")
async def download_docx(aid: str, user=Depends(current_user)):
    ana, cc, testo, cons = await _render_data(aid, user)
    logo = await _logo_bytes()
    docx = contratto_render.build_docx(
        testo, consulente=cons, cliente_nome=_cliente_nome(ana), logo_bytes=logo)
    return StreamingResponse(
        BytesIO(docx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="Contratto_consulenza_{aid[:8]}.docx"'})


# ============================================================
# Libreria modelli di contratto (riutilizzabili per tutti i clienti dell'agenzia)
# ============================================================
@router.get("/contratti-modelli")
async def list_modelli(user=Depends(current_user)):
    docs = await db.contratti_modelli.find({}, {"_id": 0}).sort("nome", 1).to_list(200)
    return docs


@router.post("/contratti-modelli")
async def save_modello(body: dict, user=Depends(current_user)):
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(400, "Nome del modello obbligatorio")
    import uuid
    doc = {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "testo": body.get("testo") or "",
        "importo": float(body.get("importo") or 0),
        "creato_da": user.get("id"),
        "creato_il": _now_iso(),
    }
    await db.contratti_modelli.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/contratti-modelli/{mid}")
async def delete_modello(mid: str, user=Depends(current_user)):
    r = await db.contratti_modelli.delete_one({"id": mid})
    if not r.deleted_count:
        raise HTTPException(404, "Modello non trovato")
    return {"ok": True}


def _pdf_da_testo(testo: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x, y = 2 * cm, H - 2 * cm
    maxw = W - 4 * cm
    c.setFont("Helvetica", 9)
    for raw in (testo or "").split("\n"):
        line = raw
        # wrap semplice
        while line:
            chunk = line
            while c.stringWidth(chunk, "Helvetica", 9) > maxw and len(chunk) > 1:
                chunk = chunk[:-1]
            sp = chunk.rfind(" ")
            if sp > 20 and c.stringWidth(line[:sp], "Helvetica", 9) <= maxw:
                chunk = line[:sp]
            c.drawString(x, y, chunk)
            y -= 0.45 * cm
            line = line[len(chunk):].lstrip()
            if y < 2 * cm:
                c.showPage(); c.setFont("Helvetica", 9); y = H - 2 * cm
        y -= 0.15 * cm
        if y < 2 * cm:
            c.showPage(); c.setFont("Helvetica", 9); y = H - 2 * cm
    c.save()
    return buf.getvalue()
