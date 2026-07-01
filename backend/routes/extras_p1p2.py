"""Extras P1/P2 — Documenti per ramo · Libro matricola applicazioni · Regolazione premio
   · OCR bilancio (Cervello) · OCR corsi IVASS · Customer Insights · Storico avvisi.
"""
from __future__ import annotations
import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter()


# ===========================================================
# 10) INSIGHTS · DOCUMENTI MANCANTI (widget dashboard)
# ===========================================================
@router.get("/insights/documenti-mancanti")
async def documenti_mancanti(
    collaboratore_id: Optional[str] = None,
    user=Depends(current_user),
) -> dict:
    """Ritorna le liste di entità senza documenti essenziali, filtrabile per collaboratore.
    - polizze senza PDF/allegato polizza
    - anagrafiche senza carta d'identità o documento equivalente
    - polizze veicolo senza libretto allegato."""
    LIMIT = 500

    # === 1. POLIZZE SENZA ALLEGATO ===
    # Sono "attive" o "in corso" da almeno 1 giorno (date_effetto <= today)
    today = _now_iso()[:10]
    pol_filter = {
        "stato": {"$in": ["attiva", "in_corso", "in corso", "vigente"]},
        "$or": [{"effetto": {"$lte": today}}, {"data_effetto": {"$lte": today}}],
    }
    is_client = user["role"] == "cliente"
    if is_client:
        pol_filter["contraente_id"] = user.get("anagrafica_id")
    if collaboratore_id:
        pol_filter["collaboratore_id"] = collaboratore_id
    polizze = await db.polizze.find(pol_filter, {
        "_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "prodotto": 1,
        "contraente_id": 1, "scadenza": 1, "effetto": 1, "targa": 1,
    }).limit(2000).to_list(2000)
    if polizze:
        pol_ids = [p["id"] for p in polizze]
        # Trova polizze CHE HANNO almeno un allegato (categoria polizza o "polizza" o "contratto")
        pol_con_allegato = set()
        async for a in db.allegati.find(
            {"entita_tipo": "polizza", "entita_id": {"$in": pol_ids}},
            {"_id": 0, "entita_id": 1, "categoria": 1, "nome_file": 1},
        ):
            pol_con_allegato.add(a["entita_id"])
        polizze_senza = [p for p in polizze if p["id"] not in pol_con_allegato][:LIMIT]
    else:
        polizze_senza = []

    # === 2. POLIZZE VEICOLO SENZA LIBRETTO ===
    veicolo_filter = {
        **pol_filter,
        "$and": [{"targa": {"$ne": None, "$exists": True}}, {"targa": {"$ne": ""}}],
    }
    # Rimuovi $or duplicato se presente
    veicoli = await db.polizze.find(veicolo_filter, {
        "_id": 0, "id": 1, "numero_polizza": 1, "targa": 1,
        "contraente_id": 1, "veicolo_marca": 1, "veicolo_modello": 1,
    }).limit(2000).to_list(2000)
    if veicoli:
        v_ids = [v["id"] for v in veicoli]
        v_con_libretto = set()
        async for a in db.allegati.find(
            {"entita_tipo": "polizza", "entita_id": {"$in": v_ids},
             "$or": [{"categoria": "libretto_circolazione"}, {"categoria": "libretto"},
                     {"nome_file": {"$regex": "libretto", "$options": "i"}}]},
            {"_id": 0, "entita_id": 1},
        ):
            v_con_libretto.add(a["entita_id"])
        veicoli_senza = [v for v in veicoli if v["id"] not in v_con_libretto][:LIMIT]
    else:
        veicoli_senza = []

    # === 3. ANAGRAFICHE SENZA CARTA D'IDENTITÀ ===
    ana_filter = {"tipo": {"$ne": "persona_giuridica"}}
    if is_client:
        ana_filter["id"] = user.get("anagrafica_id")
    # Se filtra per collaboratore: solo anagrafiche con almeno 1 polizza assegnata a lui
    if collaboratore_id:
        coll_ana_ids = await db.polizze.distinct("contraente_id", {"collaboratore_id": collaboratore_id})
        ana_filter["id"] = {"$in": coll_ana_ids} if not is_client else user.get("anagrafica_id")
    anagrafiche = await db.anagrafiche.find(ana_filter, {
        "_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1,
        "cellulare": 1, "email": 1,
    }).limit(2000).to_list(2000)
    if anagrafiche:
        a_ids = [a["id"] for a in anagrafiche]
        a_con_ci = set()
        async for a in db.allegati.find(
            {"entita_tipo": "anagrafica", "entita_id": {"$in": a_ids},
             "$or": [
                 {"categoria": "documento_identita"},
                 {"categoria": "carta_identita"},
                 {"categoria": "patente"},
                 {"categoria": "passaporto"},
                 {"nome_file": {"$regex": "(carta|identita|patente|passaport|ci\\b)", "$options": "i"}},
             ]},
            {"_id": 0, "entita_id": 1},
        ):
            a_con_ci.add(a["entita_id"])
        anagrafiche_senza_ci = [a for a in anagrafiche if a["id"] not in a_con_ci][:LIMIT]
    else:
        anagrafiche_senza_ci = []

    # Arricchisci con contraente_nome per le polizze
    cid_set = list({p.get("contraente_id") for p in polizze_senza + veicoli_senza if p.get("contraente_id")})
    if cid_set:
        ana_map = {a["id"]: (a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip())
                   async for a in db.anagrafiche.find(
                       {"id": {"$in": cid_set}},
                       {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    else:
        ana_map = {}
    for p in polizze_senza + veicoli_senza:
        p["contraente_nome"] = ana_map.get(p.get("contraente_id"), "—")

    return {
        "polizze_senza_allegato": polizze_senza,
        "veicoli_senza_libretto": veicoli_senza,
        "anagrafiche_senza_ci": anagrafiche_senza_ci,
        "totali": {
            "polizze": len(polizze_senza),
            "veicoli": len(veicoli_senza),
            "anagrafiche": len(anagrafiche_senza_ci),
        },
    }


# ===========================================================
# 11) STORICO AVVISI · LISTA (vedi sezione 7 più sotto)
# ===========================================================


router = router  # mantieni




# ===========================================================
# 1) DOCUMENTI PRE-IMPOSTATI PER RAMO POLIZZA
# ===========================================================
DOCUMENTI_TEMPLATE_RAMO = {
    "RC_AUTO": ["libretto", "polizza", "condizioni"],
    "auto": ["libretto", "polizza", "condizioni"],
    "rca": ["libretto", "polizza", "condizioni"],
    "moto": ["libretto", "polizza", "condizioni"],
    "casa": ["polizza", "condizioni", "foto"],
    "abitazione": ["polizza", "condizioni", "foto"],
    "vita": ["polizza", "condizioni"],
    "salute": ["polizza", "condizioni"],
    "infortuni": ["polizza", "condizioni"],
    "default": ["polizza", "condizioni", "foto"],
}


@router.get("/polizze/{pid}/documenti-template")
async def documenti_template(pid: str, user=Depends(current_user)) -> dict:
    """Per una polizza ritorna i documenti richiesti dal suo ramo + quali mancano."""
    pol = await db.polizze.find_one({"id": pid}, {"_id": 0})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")
    ramo = (pol.get("ramo") or "").lower().replace(" ", "_")
    template = DOCUMENTI_TEMPLATE_RAMO.get(ramo, DOCUMENTI_TEMPLATE_RAMO["default"])
    # check allegati esistenti per categoria
    allegati = await db.allegati.find(
        {"entita_tipo": "polizza", "entita_id": pid, "is_deleted": {"$ne": True}},
        {"_id": 0, "categoria": 1, "nome_file": 1, "id": 1},
    ).to_list(500)
    cat_count = {c: 0 for c in template}
    for a in allegati:
        c = a.get("categoria")
        if c in cat_count:
            cat_count[c] += 1
    return {
        "polizza_id": pid,
        "ramo": pol.get("ramo"),
        "template": template,
        "presenti": cat_count,
        "completezza_pct": round(
            (sum(1 for v in cat_count.values() if v > 0) / max(1, len(template))) * 100, 0,
        ),
    }


# ===========================================================
# 2) LIBRO MATRICOLA — APPLICAZIONI CON ALLEGATI
# ===========================================================
class ApplicazioneBody(BaseModel):
    polizza_id: str
    targa: Optional[str] = None
    telaio: Optional[str] = None
    marca: Optional[str] = None
    modello: Optional[str] = None
    data_inserimento: Optional[str] = None
    data_uscita: Optional[str] = None
    premio_annuo: float = 0
    note: Optional[str] = None


@router.get("/libro-matricola/{polizza_id}/applicazioni")
async def list_applicazioni(polizza_id: str, user=Depends(current_user)) -> list[dict]:
    items = await db.applicazioni_matricola.find(
        {"polizza_id": polizza_id}, {"_id": 0},
    ).sort("data_inserimento", -1).to_list(2000)
    # enrich con conteggio allegati
    for a in items:
        a["n_allegati"] = await db.allegati.count_documents({
            "applicazione_matricola_id": a["id"], "is_deleted": {"$ne": True},
        })
    return items


@router.get("/libro-matricola")
async def list_all_libro_matricola(
    q: Optional[str] = None,
    stato: Optional[str] = None,  # attivo | cessato
    polizza_id: Optional[str] = None,
    limit: int = 5000,
    user=Depends(current_user),
) -> list[dict]:
    """Lista globale di TUTTE le applicazioni di libro matricola (per pagina standalone).
    Arricchita con polizza_numero, contraente_nome, n_allegati."""
    flt: dict = {}
    or_clauses: list = []
    if polizza_id: flt["polizza_id"] = polizza_id
    if stato == "cessato":
        flt["data_cessazione"] = {"$ne": None, "$exists": True}
    elif stato == "attivo":
        or_clauses.append([{"data_cessazione": None}, {"data_cessazione": {"$exists": False}}])
    if q and q.strip():
        rx = {"$regex": q.strip(), "$options": "i"}
        or_clauses.append([{"targa": rx}, {"descrizione_veicolo": rx}, {"telaio": rx}, {"matricola": rx}])
    if len(or_clauses) == 1:
        flt["$or"] = or_clauses[0]
    elif len(or_clauses) > 1:
        flt["$and"] = [{"$or": o} for o in or_clauses]
    items = await db.applicazioni_matricola.find(flt, {"_id": 0}).sort("data_inserimento", -1).limit(limit).to_list(limit)
    # enrich
    pol_ids = list({a.get("polizza_id") for a in items if a.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find(
        {"id": {"$in": pol_ids}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "contraente_id": 1, "is_libro_matricola": 1})}
    cont_ids = list({pols.get(p, {}).get("contraente_id") for p in pol_ids})
    cont_map = {a["id"]: (a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip())
                async for a in db.anagrafiche.find(
                    {"id": {"$in": [c for c in cont_ids if c]}},
                    {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    for a in items:
        p = pols.get(a.get("polizza_id"), {})
        a["polizza_numero"] = p.get("numero_polizza")
        a["polizza_ramo"] = p.get("ramo")
        a["contraente_nome"] = cont_map.get(p.get("contraente_id"))
        a["n_allegati"] = await db.allegati.count_documents({
            "applicazione_matricola_id": a["id"], "is_deleted": {"$ne": True},
        })
    return items


@router.post("/libro-matricola/applicazioni", status_code=201)
async def create_applicazione(
    body: ApplicazioneBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    pol = await db.polizze.find_one({"id": body.polizza_id}, {"_id": 0, "id": 1, "is_libro_matricola": 1})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": _now_iso()}
    await db.applicazioni_matricola.insert_one(doc); doc.pop("_id", None)
    return doc


@router.put("/libro-matricola/applicazioni/{aid}")
async def update_applicazione(
    aid: str, body: ApplicazioneBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    res = await db.applicazioni_matricola.update_one(
        {"id": aid}, {"$set": {**body.model_dump(), "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Applicazione non trovata")
    return await db.applicazioni_matricola.find_one({"id": aid}, {"_id": 0})


@router.delete("/libro-matricola/applicazioni/{aid}")
async def delete_applicazione(
    aid: str, user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    res = await db.applicazioni_matricola.delete_one({"id": aid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Applicazione non trovata")
    return {"ok": True}


class CessazioneBody(BaseModel):
    data_cessazione: str  # YYYY-MM-DD
    tipo_cessazione: Literal["sostituita", "venduta", "demolita", "esportata", "rubata", "cessata_altro"] = "cessata_altro"
    motivo_dettaglio: Optional[str] = None


@router.post("/libro-matricola/applicazioni/{aid}/annulla")
async def annulla_applicazione(
    aid: str, body: CessazioneBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Cessa un'applicazione (veicolo venduto/demolito/esportato/rubato/altro).
    A differenza di delete, mantiene lo storico marcando data_cessazione + tipo_cessazione."""
    res = await db.applicazioni_matricola.update_one(
        {"id": aid},
        {"$set": {
            "data_cessazione": body.data_cessazione,
            "tipo_cessazione": body.tipo_cessazione,
            "motivo_cessazione": body.motivo_dettaglio,
            "cessata_da": user.get("id"),
            "cessata_il": _now_iso(),
            "updated_at": _now_iso(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Applicazione non trovata")
    return await db.applicazioni_matricola.find_one({"id": aid}, {"_id": 0})


# ===========================================================
# 2.b) CROSS-TARGA SEARCH (warning: polizze multiple con stessa targa)
# ===========================================================
@router.get("/polizze/by-targa/{targa}")
async def cerca_polizze_per_targa(
    targa: str,
    exclude_id: Optional[str] = None,
    user=Depends(current_user),
) -> dict:
    """Cerca tutte le polizze (E applicazioni matricola) che riportano la stessa targa.
    Utile per ricordare aggiornamenti coordinati (RCA + Infortuni Conducente + Tutela Legale, ecc.)."""
    targa_clean = (targa or "").strip().upper().replace(" ", "")
    if not targa_clean:
        return {"polizze": [], "applicazioni": []}
    # polizze dirette
    pol_filter = {"targa": {"$regex": f"^{re.escape(targa_clean)}$", "$options": "i"}}
    if exclude_id:
        pol_filter["id"] = {"$ne": exclude_id}
    is_client = user["role"] == "cliente"
    if is_client:
        pol_filter["contraente_id"] = user.get("anagrafica_id")
    polizze = await db.polizze.find(pol_filter, {
        "_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "prodotto": 1,
        "stato": 1, "contraente_id": 1, "scadenza": 1, "data_scadenza": 1,
        "compagnia_id": 1, "is_libro_matricola": 1,
    }).limit(50).to_list(50)
    # applicazioni matricola con la stessa targa
    applicazioni = await db.applicazioni_matricola.find(
        {"targa": {"$regex": f"^{re.escape(targa_clean)}$", "$options": "i"}},
        {"_id": 0},
    ).limit(50).to_list(50)
    # enrich
    cids = list({p.get("contraente_id") for p in polizze if p.get("contraente_id")})
    cmap = {a["id"]: (a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip())
            async for a in db.anagrafiche.find(
                {"id": {"$in": cids}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    comp_ids = list({p.get("compagnia_id") for p in polizze if p.get("compagnia_id")})
    compmap = {c["id"]: c.get("ragione_sociale") async for c in db.compagnie.find(
        {"id": {"$in": comp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    for p in polizze:
        p["contraente_nome"] = cmap.get(p.get("contraente_id"))
        p["compagnia_nome"] = compmap.get(p.get("compagnia_id"))
    pol_by_id = {p["id"]: p for p in polizze}
    for a in applicazioni:
        pol = pol_by_id.get(a.get("polizza_id"))
        if pol:
            a["polizza_numero"] = pol.get("numero_polizza")
            a["polizza_ramo"] = pol.get("ramo")
            a["contraente_nome"] = pol.get("contraente_nome")
        else:
            sub_pol = await db.polizze.find_one(
                {"id": a.get("polizza_id")},
                {"_id": 0, "numero_polizza": 1, "ramo": 1, "contraente_id": 1},
            )
            if sub_pol:
                a["polizza_numero"] = sub_pol.get("numero_polizza")
                a["polizza_ramo"] = sub_pol.get("ramo")
    return {"polizze": polizze, "applicazioni": applicazioni, "targa": targa_clean}


# ===========================================================
# 3) REGOLAZIONE PREMIO
# ===========================================================
class RegolazioneCalcBody(BaseModel):
    base_imponibile: float  # fatturato / monte mercedi / numero addetti
    tasso_override: Optional[float] = None  # override del tasso polizza
    periodo: Optional[str] = None  # es. "2025"
    note: Optional[str] = None
    salva: bool = True  # se True aggiorna polizza con ultimo calcolo


@router.post("/polizze/{pid}/regolazione-premio/calcola")
async def calcola_regolazione(
    pid: str, body: RegolazioneCalcBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    pol = await db.polizze.find_one({"id": pid}, {"_id": 0})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")
    if not pol.get("regolazione_premio"):
        raise HTTPException(400, "Polizza non flaggata 'regolazione_premio'")
    tasso = body.tasso_override if body.tasso_override is not None else (pol.get("regolazione_tasso") or 0)
    premio_calcolato = round((body.base_imponibile * tasso) / 100.0, 2)
    minima = float(pol.get("regolazione_minima") or 0)
    dovuto = max(premio_calcolato, minima)
    risultato = {
        "polizza_id": pid,
        "periodo": body.periodo,
        "base_imponibile": body.base_imponibile,
        "base_tipo": pol.get("regolazione_base"),
        "tasso_applicato_pct": tasso,
        "premio_calcolato": premio_calcolato,
        "minimo_non_rimborsabile": minima,
        "dovuto": dovuto,
        "data_calcolo": _now_iso()[:10],
        "operatore_id": user.get("id"),
        "note": body.note,
    }
    if body.salva:
        await db.regolazione_storico.insert_one({"id": str(uuid.uuid4()), **risultato, "created_at": _now_iso()})
        await db.polizze.update_one({"id": pid}, {"$set": {
            "regolazione_ultimo_calcolo": risultato["data_calcolo"],
            "regolazione_dovuto": dovuto,
        }})
    return risultato


@router.get("/polizze/{pid}/regolazione-premio/storico")
async def storico_regolazioni(pid: str, user=Depends(current_user)) -> list[dict]:
    return await db.regolazione_storico.find({"polizza_id": pid}, {"_id": 0}).sort("data_calcolo", -1).to_list(200)


# ===========================================================
# 4) OCR BILANCIO (Cervello)
# ===========================================================
async def _ocr_bilancio_gemini(img_bytes: bytes) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY non configurata")
    prompt = """Sei un OCR specializzato in bilanci d'esercizio italiani. Analizza il documento
e ritorna ESCLUSIVAMENTE un JSON con questo schema (numeri in euro, no separatori migliaia, decimali col punto):

{
  "anno": "YYYY (es. 2024)",
  "ricavi": "numero o null",
  "costi_personale": "numero o null",
  "costi_servizi": "numero o null",
  "costi_godimento_beni": "numero o null",
  "ammortamenti": "numero o null",
  "oneri_finanziari": "numero o null",
  "utile_lordo": "numero o null",
  "imposte": "numero o null",
  "utile_netto": "numero o null",
  "totale_attivo": "numero o null",
  "patrimonio_netto": "numero o null",
  "confidenza": "alta | media | bassa"
}

REGOLE: null se non leggibile, no commenti, no markdown."""
    b64 = base64.b64encode(img_bytes).decode("ascii")
    chat = LlmChat(
        api_key=key,
        session_id=f"bilancio-{uuid.uuid4().hex[:8]}",
        system_message="Sei un OCR di bilanci.",
    ).with_model("gemini", "gemini-3-flash-preview")
    msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=b64)])
    resp = ""
    try:
        async for ev in chat.stream_message(msg):
            if isinstance(ev, TextDelta): resp += ev.content
            elif isinstance(ev, StreamDone): break
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"OCR Gemini fallito: {e}")
    m = re.search(r"\{.*\}", resp, re.DOTALL)
    if not m:
        raise HTTPException(502, f"Risposta non JSON: {resp[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise HTTPException(502, f"JSON malformato: {e}")


@router.post("/cervello/ocr-bilancio")
async def ocr_bilancio(
    file: UploadFile = File(...),
    salva: bool = Form(False),
    user=Depends(require_user("admin")),
) -> dict:
    """OCR di un bilancio d'esercizio. Se salva=true, auto-popola i costi annuali
    in db.costi_annuali per l'anno estratto."""
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande")
    ct = file.content_type or ""
    if ct == "application/pdf":
        import pdfplumber
        with pdfplumber.open(BytesIO(contents)) as pdf:
            if not pdf.pages:
                raise HTTPException(400, "PDF vuoto")
            img = pdf.pages[0].to_image(resolution=200).original
            out = BytesIO(); img.save(out, format="JPEG", quality=85)
            img_bytes = out.getvalue()
    elif ct.startswith("image/"):
        img_bytes = contents
    else:
        raise HTTPException(400, "Formato non supportato")
    dati = await _ocr_bilancio_gemini(img_bytes)
    out = {"dati_estratti": dati}
    if salva and dati.get("anno"):
        try:
            anno = int(str(dati["anno"])[:4])
            voci = []
            for k_src, k_dst, label in [
                ("costi_personale", "personale", "Personale"),
                ("costi_servizi", "servizi", "Servizi"),
                ("costi_godimento_beni", "godimento_beni", "Godimento beni"),
                ("ammortamenti", "ammortamenti", "Ammortamenti"),
                ("oneri_finanziari", "oneri_finanziari", "Oneri finanziari"),
                ("imposte", "imposte", "Imposte"),
            ]:
                v = dati.get(k_src)
                if v is not None:
                    voci.append({"chiave": k_dst, "etichetta": label, "importo": float(v)})
            doc = {
                "anno": anno, "voci": voci,
                "ricavi": dati.get("ricavi"),
                "utile_lordo": dati.get("utile_lordo"),
                "utile_netto": dati.get("utile_netto"),
                "ocr_origine": True,
                "ocr_confidenza": dati.get("confidenza"),
                "updated_at": _now_iso(),
            }
            await db.costi_annuali.update_one({"anno": anno}, {"$set": doc}, upsert=True)
            out["salvato_anno"] = anno
            out["voci_create"] = len(voci)
        except Exception as e:
            out["errore_salvataggio"] = str(e)
    return out


# ===========================================================
# 5) OCR CORSI IVASS + GRAFICO 30H
# ===========================================================
class CorsoBody(BaseModel):
    collaboratore_id: str
    titolo_corso: str
    ente: Optional[str] = None
    data_corso: str
    ore_riconosciute: float
    crediti_ivass: Optional[float] = None
    note: Optional[str] = None


@router.post("/corsi-ivass/ocr")
async def ocr_corso_ivass(
    file: UploadFile = File(...),
    collaboratore_id: str = Form(...),
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Estrae dati da un certificato di corso IVASS (ente, titolo, ore, data)."""
    contents = await file.read()
    ct = file.content_type or ""
    if ct == "application/pdf":
        import pdfplumber
        with pdfplumber.open(BytesIO(contents)) as pdf:
            img = pdf.pages[0].to_image(resolution=200).original
            o = BytesIO(); img.save(o, format="JPEG", quality=85); img_bytes = o.getvalue()
    else:
        img_bytes = contents
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY non configurata")
    prompt = """OCR del certificato di un corso IVASS. JSON SCHEMA:
{
  "ente_erogatore": "MAIUSCOLO o null",
  "titolo_corso": "stringa o null",
  "data_corso": "YYYY-MM-DD o null",
  "ore_riconosciute": "numero (float, es. 4 o 4.5) o null",
  "crediti_ivass": "numero o null",
  "discente_nome": "MAIUSCOLO o null",
  "confidenza": "alta | media | bassa"
}
Niente testo prima/dopo, no markdown."""
    chat = LlmChat(api_key=key, session_id=f"ivass-{uuid.uuid4().hex[:6]}",
                   system_message="OCR corso IVASS.").with_model("gemini", "gemini-3-flash-preview")
    msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=base64.b64encode(img_bytes).decode())])
    resp = ""
    async for ev in chat.stream_message(msg):
        if isinstance(ev, TextDelta): resp += ev.content
        elif isinstance(ev, StreamDone): break
    m = re.search(r"\{.*\}", resp, re.DOTALL)
    if not m:
        raise HTTPException(502, f"OCR fallita: {resp[:200]}")
    dati = json.loads(m.group(0))
    return {"dati": dati, "collaboratore_id": collaboratore_id}


@router.post("/corsi-ivass", status_code=201)
async def create_corso(
    body: CorsoBody, user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": _now_iso(), "created_by": user.get("id")}
    await db.corsi_ivass.insert_one(doc); doc.pop("_id", None)
    return doc


@router.get("/corsi-ivass/{collaboratore_id}/storico")
async def storico_corsi(
    collaboratore_id: str, anno: Optional[int] = None,
    user=Depends(current_user),
) -> dict:
    """Storico corsi + totale ore IVASS dell'anno (obiettivo 30h annuali)."""
    flt = {"collaboratore_id": collaboratore_id}
    if anno:
        flt["data_corso"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}
    corsi = await db.corsi_ivass.find(flt, {"_id": 0}).sort("data_corso", -1).to_list(500)
    totale_ore = sum(float(c.get("ore_riconosciute") or 0) for c in corsi)
    # Grafico per mese
    per_mese = {}
    for c in corsi:
        m = (c.get("data_corso") or "0000-01")[:7]
        per_mese[m] = per_mese.get(m, 0) + float(c.get("ore_riconosciute") or 0)
    return {
        "collaboratore_id": collaboratore_id,
        "anno": anno,
        "totale_ore_anno": round(totale_ore, 2),
        "obiettivo_annuo": 30,
        "completamento_pct": round(min(100, (totale_ore / 30) * 100), 1),
        "corsi": corsi,
        "grafico_mensile": [{"mese": k, "ore": round(v, 2)} for k, v in sorted(per_mese.items())],
    }


@router.delete("/corsi-ivass/{cid}")
async def delete_corso(cid: str, user=Depends(require_user("admin"))) -> dict:
    res = await db.corsi_ivass.delete_one({"id": cid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Corso non trovato")
    return {"ok": True}


# ===========================================================
# 6) CUSTOMER INSIGHTS WIDGET (riusa /insights/suggerimenti-ai)
# ===========================================================
@router.get("/anagrafiche/{aid}/customer-insights-widget")
async def customer_insights_widget(aid: str, user=Depends(current_user)) -> dict:
    """Versione compatta dei customer insights ottimizzata per widget AnagraficaDetail.
    Combina dati sintetici (KPI rapide) + ultimo suggerimento AI se presente."""
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    polizze = await db.polizze.find({"contraente_id": aid}, {"_id": 0, "id": 1, "ramo": 1, "stato": 1, "premio_lordo": 1, "data_scadenza": 1}).to_list(200)
    n_attive = sum(1 for p in polizze if p.get("stato") in ("attiva", "in_emissione"))
    n_scadute = sum(1 for p in polizze if p.get("stato") == "scaduta")
    rami_distinti = list({p.get("ramo") for p in polizze if p.get("ramo")})
    n_sinistri = await db.sinistri.count_documents({"anagrafica_id": aid})
    n_sinistri_anno = await db.sinistri.count_documents({
        "anagrafica_id": aid,
        "data_apertura": {"$gte": (datetime.now(timezone.utc).year - 1) and f"{datetime.now(timezone.utc).year}-01-01"},
    })
    premio_tot = sum(float(p.get("premio_lordo") or 0) for p in polizze if p.get("stato") in ("attiva", "in_emissione"))
    # Cross-selling: rami non ancora coperti
    RAMI_PRINCIPALI = ["RC_AUTO", "casa", "vita", "salute", "infortuni"]
    rami_norm = {(r or "").lower() for r in rami_distinti}
    cross_sell_opp = [r for r in RAMI_PRINCIPALI if r.lower() not in rami_norm]
    # Ultimo suggerimento AI se esiste
    ult_ai = await db.insights_log.find_one({"anagrafica_id": aid}, {"_id": 0}, sort=[("created_at", -1)])
    return {
        "anagrafica_id": aid,
        "kpi": {
            "n_polizze_attive": n_attive,
            "n_polizze_scadute": n_scadute,
            "n_rami_coperti": len(rami_distinti),
            "n_sinistri_totali": n_sinistri,
            "n_sinistri_anno_corrente": n_sinistri_anno,
            "premio_totale_attivo": round(premio_tot, 2),
        },
        "rami_coperti": list(rami_norm),
        "cross_selling_opportunita": cross_sell_opp,
        "ultimo_suggerimento_ai": (
            {
                "data": ult_ai.get("created_at"),
                "testo": (ult_ai.get("consiglio") or ult_ai.get("testo") or "")[:400],
            } if ult_ai else None
        ),
        "rischio_score": min(10, n_sinistri * 2 + n_scadute),  # semplice euristica 0-10
    }


# ===========================================================
# 7) STORICO AVVISI (auto-move primo avviso → storico)
# ===========================================================
@router.get("/storico-avvisi")
async def list_storico_avvisi(
    anagrafica_id: Optional[str] = None,
    canale: Optional[str] = None,
    tipo: Optional[str] = None,
    limit: int = 200,
    user=Depends(current_user),
) -> list[dict]:
    flt = {}
    if anagrafica_id: flt["anagrafica_id"] = anagrafica_id
    if anagrafica_id: flt.setdefault("contraente_id", anagrafica_id)
    if canale: flt["canale"] = canale
    if tipo: flt["tipo"] = tipo
    if user["role"] == "cliente":
        flt["contraente_id"] = user.get("anagrafica_id")
    return await db.storico_avvisi.find(flt, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(limit)


@router.post("/storico-avvisi/sposta-attivi")
async def sposta_attivi_in_storico(user=Depends(require_user("admin"))) -> dict:
    """Sposta tutti gli avvisi 'inviati' dalla sezione attiva (db.avvisi)
    a storico. Idempotente."""
    moved = 0
    if "avvisi" in await db.list_collection_names():
        async for a in db.avvisi.find({"stato": "inviato"}, {"_id": 0}):
            await db.storico_avvisi.insert_one({
                **a,
                "moved_to_storico_at": _now_iso(),
                "moved_by": user.get("id"),
            })
            await db.avvisi.delete_one({"id": a["id"]})
            moved += 1
    return {"moved": moved}


class StoricoAvvisoBody(BaseModel):
    model_config = {"extra": "allow"}  # accetta campi extra dal frontend
    canale: str  # "email" | "whatsapp" | "sms" | "pec" | "pdf"
    contraente_id: Optional[str] = None
    contraente_nome: Optional[str] = None
    polizza_id: Optional[str] = None
    titolo_id: Optional[str] = None
    titoli_ids: List[str] = []
    tipo: Optional[str] = "avviso_scadenza"
    target: Optional[str] = None
    destinatario: Optional[str] = None
    oggetto: Optional[str] = None
    soggetto: Optional[str] = None
    messaggio: Optional[str] = None
    importo: Optional[float] = None


@router.post("/storico-avvisi/registra", status_code=201)
async def registra_storico_avviso(
    body: StoricoAvvisoBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Registra l'invio di un avviso nello storico (chiamato dal frontend
    dopo apertura WhatsApp/Email/PDF/SMS)."""
    doc = {
        "id": str(uuid.uuid4()),
        **body.model_dump(exclude_none=False),
        "sent_at": _now_iso(),
        "operatore_id": user.get("id"),
        "operatore_nome": user.get("name") or user.get("email"),
    }
    await db.storico_avvisi.insert_one(doc); doc.pop("_id", None)
    return doc


# ===========================================================
# 8) SALUTE FISCALE CLIENTE (corporate: OCR bilancio + score rischio + cross-sell)
# ===========================================================
@router.post("/anagrafiche/{aid}/salute-fiscale/ocr-bilancio")
async def salute_fiscale_ocr(
    aid: str,
    file: UploadFile = File(...),
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    """OCR del bilancio di un cliente azienda → salva su anagrafica.salute_fiscale_dati
    con calcolo automatico di indicatori (ROE, leva, liquidità, score rischio)."""
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande")
    ct = file.content_type or ""
    if ct == "application/pdf":
        import pdfplumber
        with pdfplumber.open(BytesIO(contents)) as pdf:
            if not pdf.pages:
                raise HTTPException(400, "PDF vuoto")
            img = pdf.pages[0].to_image(resolution=200).original
            out = BytesIO(); img.save(out, format="JPEG", quality=85)
            img_bytes = out.getvalue()
    elif ct.startswith("image/"):
        img_bytes = contents
    else:
        raise HTTPException(400, "Formato non supportato")
    dati = await _ocr_bilancio_gemini(img_bytes)
    # Calcolo indicatori di salute fiscale
    def _f(k):
        try:
            v = dati.get(k)
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
    ricavi = _f("ricavi") or 0
    utile_netto = _f("utile_netto") or 0
    utile_lordo = _f("utile_lordo") or 0
    totale_attivo = _f("totale_attivo") or 0
    patrimonio_netto = _f("patrimonio_netto") or 0
    oneri_fin = _f("oneri_finanziari") or 0
    imposte = _f("imposte") or 0
    indicatori = {
        "roe_pct": round((utile_netto / patrimonio_netto * 100), 2) if patrimonio_netto > 0 else None,
        "ros_pct": round((utile_lordo / ricavi * 100), 2) if ricavi > 0 else None,
        "leva_finanziaria": round((totale_attivo / patrimonio_netto), 2) if patrimonio_netto > 0 else None,
        "incidenza_oneri_fin_pct": round((oneri_fin / ricavi * 100), 2) if ricavi > 0 else None,
        "pressione_fiscale_pct": round((imposte / utile_lordo * 100), 2) if utile_lordo > 0 else None,
    }
    # Score rischio default 0-10 (10 = max rischio)
    rischio = 0
    if utile_netto < 0: rischio += 4
    elif utile_netto < ricavi * 0.02: rischio += 2
    if indicatori["leva_finanziaria"] and indicatori["leva_finanziaria"] > 3: rischio += 2
    if indicatori["incidenza_oneri_fin_pct"] and indicatori["incidenza_oneri_fin_pct"] > 5: rischio += 2
    if indicatori["roe_pct"] is not None and indicatori["roe_pct"] < 3: rischio += 1
    if patrimonio_netto <= 0: rischio += 3
    rischio = min(10, rischio)
    # Cross-selling suggerito (azienda con bilancio positivo + utile > 50k):
    cross_sell = []
    if utile_netto > 50000 and patrimonio_netto > 100000:
        cross_sell.append("RC Professionale / D&O")
        cross_sell.append("Polizze Vita / Key Man")
    if ricavi > 500000:
        cross_sell.append("Cyber Risk")
        cross_sell.append("RC Prodotti")
    if oneri_fin > 10000:
        cross_sell.append("Tutela Legale aziendale")
    payload = {
        "salute_fiscale_dati": {
            "bilancio_estratto": dati,
            "indicatori": indicatori,
            "score_rischio_default": rischio,
            "cross_sell_suggerito": cross_sell,
            "ocr_data": _now_iso()[:10],
        },
        "salute_fiscale_aggiornata_il": _now_iso(),
    }
    await db.anagrafiche.update_one({"id": aid}, {"$set": payload})
    return payload["salute_fiscale_dati"]


@router.get("/anagrafiche/{aid}/salute-fiscale")
async def get_salute_fiscale(aid: str, user=Depends(current_user)) -> dict:
    ana = await db.anagrafiche.find_one(
        {"id": aid}, {"_id": 0, "salute_fiscale_dati": 1, "salute_fiscale_aggiornata_il": 1},
    )
    if ana is None:
        raise HTTPException(404, "Anagrafica non trovata")
    return {
        "dati": ana.get("salute_fiscale_dati") or {},
        "aggiornato_il": ana.get("salute_fiscale_aggiornata_il"),
    }


# ===========================================================
# 9) RACCOLTA DATI + POTENTI DOMANDE (onboarding cliente)
# ===========================================================
class RaccoltaDatiBody(BaseModel):
    raccolta_dati: dict


@router.put("/anagrafiche/{aid}/raccolta-dati")
async def save_raccolta_dati(
    aid: str, body: RaccoltaDatiBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    res = await db.anagrafiche.update_one({"id": aid}, {"$set": {
        "raccolta_dati": body.raccolta_dati,
        "raccolta_dati_aggiornata_il": _now_iso(),
        "updated_at": _now_iso(),
    }})
    if res.matched_count == 0:
        raise HTTPException(404, "Anagrafica non trovata")
    return {"ok": True, "aggiornato_il": _now_iso()}


class PotentiDomandeBody(BaseModel):
    risposte: List[dict]  # [{"domanda_id": int, "domanda": str, "risposta": str}]


@router.put("/anagrafiche/{aid}/potenti-domande")
async def save_potenti_domande(
    aid: str, body: PotentiDomandeBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    res = await db.anagrafiche.update_one({"id": aid}, {"$set": {
        "potenti_domande_risposte": body.risposte,
        "potenti_domande_aggiornate_il": _now_iso(),
        "updated_at": _now_iso(),
    }})
    if res.matched_count == 0:
        raise HTTPException(404, "Anagrafica non trovata")
    return {"ok": True, "aggiornato_il": _now_iso(), "n_risposte": len(body.risposte)}
