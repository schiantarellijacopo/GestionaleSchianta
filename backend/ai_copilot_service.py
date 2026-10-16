"""AI Copilot service — Claude Sonnet 4.6 conversazionale con accesso READ al CRM.

L'utente parla in linguaggio naturale e il Copilot può:
 - cercare clienti/polizze/titoli/sinistri/veicoli/allegati
 - riepilogare portafoglio, scadenze imminenti, sospesi da incassare
 - suggerire cross-sell in base ai rami mancanti
 - restituire link cliccabili verso le pagine del CRM
 - mantenere memoria multi-turno per sessione

RBAC:
 - role="cliente": ogni query è forzata al proprio anagrafica_id
 - role="collaboratore" / "dipendente": filtra solo record di sua competenza
 - role="admin": nessun filtro

Le query MongoDB sono sempre in READ-ONLY (safety by design).
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import uuid
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from database import db

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
COPILOT_MODEL_PROVIDER = "anthropic"
COPILOT_MODEL_NAME = "claude-sonnet-4-6"                 # domande complesse/analitiche
COPILOT_FAST_MODEL_NAME = "claude-haiku-4-5-20251001"    # lookup semplici (veloce)
MAX_HISTORY_MESSAGES = 10  # ultimi 10 messaggi passati al modello per contesto

# Parole che indicano una domanda complessa → modello approfondito
_COMPLEX_HINTS = (
    "perché", "perche", "analizza", "analisi", "confronta", "confronto", "strategia",
    "consiglia", "consigli", "suggerisci", "suggeriment", "piano", "valuta", "valutazione",
    "previdenz", "pension", "calcola", "simula", "proiezione", "cross-sell", "cross sell",
    "spiega", "come posso", "come faccio", "miglior", "ottimizza", "riassumi", "riassunto",
    "report", "relazione", "scoperture", "protezione", "piramide",
)


def _modo_modello(user_message: str) -> tuple[str, str]:
    """Ibrido: (model_name, etichetta) — Haiku per lookup semplici, Sonnet per analisi."""
    msg = (user_message or "").lower()
    if any(k in msg for k in _COMPLEX_HINTS) or len(user_message or "") > 220:
        return COPILOT_MODEL_NAME, "approfondito"
    return COPILOT_FAST_MODEL_NAME, "veloce"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# =========================================================
# RBAC filter helpers
# =========================================================
def _rbac_polizza_filter(user: dict) -> dict:
    role = user.get("role")
    if role == "cliente" and user.get("anagrafica_id"):
        return {"contraente_id": user["anagrafica_id"]}
    if role in ("collaboratore", "dipendente") and user.get("id"):
        return {"collaboratore_id": user["id"]}
    return {}


def _rbac_anagrafica_filter(user: dict) -> dict:
    role = user.get("role")
    if role == "cliente" and user.get("anagrafica_id"):
        return {"id": user["anagrafica_id"]}
    return {}


def _rbac_titoli_filter(user: dict) -> dict:
    return {}  # verrà applicato tramite polizze_ids


async def _rbac_polizze_ids_scope(user: dict) -> Optional[List[str]]:
    """Ritorna la lista di polizza_id visibili all'utente (None = tutte)."""
    role = user.get("role")
    if role == "admin":
        return None
    filt = _rbac_polizza_filter(user)
    if not filt:
        return None
    docs = await db.polizze.find(filt, {"_id": 0, "id": 1}).to_list(5000)
    return [d["id"] for d in docs]


# =========================================================
# TOOL: nome utile per il modello
# =========================================================
def _make_link(kind: str, oid: str) -> str:
    mapping = {
        "anagrafica": f"/anagrafiche/{oid}",
        "polizza": f"/polizze/{oid}",
        "sinistro": f"/sinistri/{oid}",
        "titolo": f"/titoli/{oid}",
        "veicolo": f"/libro-matricola",
    }
    return mapping.get(kind, "")


def _fmt_nome(a: dict) -> str:
    return (a.get("ragione_sociale") or
            f"{a.get('cognome','')} {a.get('nome','')}".strip() or
            "—")


# =========================================================
# READ TOOLS (async, RBAC-aware)
# =========================================================
async def tool_search_clienti(q: str, user: dict, limit: int = 8) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []
    # Splitta la query in parole per ricerca AND (tutte le parole devono comparire)
    words = [w for w in re.split(r"\s+", q) if len(w) >= 2]
    if not words:
        return []
    # Costruisci un $and dove ogni parola è un $or su più campi
    and_clauses = []
    for w in words:
        regex = {"$regex": re.escape(w), "$options": "i"}
        and_clauses.append({"$or": [
            {"ragione_sociale": regex}, {"cognome": regex}, {"nome": regex},
            {"codice_fiscale": {"$regex": w.upper(), "$options": "i"}},
            {"partita_iva": w},
            {"email": regex}, {"cellulare": regex}, {"telefono": regex},
        ]})
    filt = {"$and": and_clauses} if len(and_clauses) > 1 else and_clauses[0]
    rbac = _rbac_anagrafica_filter(user)
    if rbac:
        filt = {"$and": [filt, rbac]}
    proj = {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1,
            "codice_fiscale": 1, "partita_iva": 1, "email": 1, "cellulare": 1,
            "tipo": 1, "comune": 1}
    docs = await db.anagrafiche.find(filt, proj).limit(limit).to_list(limit)
    for d in docs:
        d["nome_completo"] = _fmt_nome(d)
        d["link"] = _make_link("anagrafica", d["id"])
    return docs


async def tool_polizze(
    user: dict,
    anagrafica_id: Optional[str] = None,
    ramo: Optional[str] = None,
    anno_scadenza: Optional[int] = None,
    stato: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    filt: dict = {}
    if anagrafica_id:
        filt["contraente_id"] = anagrafica_id
    if ramo:
        filt["ramo"] = {"$regex": ramo, "$options": "i"}
    if stato:
        filt["stato"] = stato
    if anno_scadenza:
        filt["$or"] = [
            {"scadenza": {"$regex": f"^{anno_scadenza}"}},
            {"data_scadenza": {"$regex": f"^{anno_scadenza}"}},
        ]
    rb = _rbac_polizza_filter(user)
    for k, v in rb.items():
        filt.setdefault(k, v)
    proj = {"_id": 0, "id": 1, "numero_polizza": 1, "compagnia_nome": 1, "ramo": 1,
            "prodotto": 1, "stato": 1, "effetto": 1, "scadenza": 1, "data_scadenza": 1,
            "premio_lordo": 1, "premio_netto": 1, "contraente_id": 1, "targa": 1}
    docs = await db.polizze.find(filt, proj).sort("scadenza", -1).limit(limit).to_list(limit)
    # arricchisci con nome contraente + link
    cids = list({d.get("contraente_id") for d in docs if d.get("contraente_id")})
    if cids:
        cmap = {a["id"]: _fmt_nome(a) async for a in db.anagrafiche.find(
            {"id": {"$in": cids}},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    else:
        cmap = {}
    for d in docs:
        d["contraente_nome"] = cmap.get(d.get("contraente_id"), "—")
        d["link"] = _make_link("polizza", d["id"])
    return docs


async def tool_polizze_in_scadenza(user: dict, giorni: int = 30, limit: int = 40) -> list[dict]:
    """Polizze/titoli in scadenza nei prossimi N giorni."""
    today = datetime.now(timezone.utc).date()
    to = today + timedelta(days=giorni)
    filt: dict = {
        "$or": [
            {"scadenza": {"$gte": today.isoformat(), "$lte": to.isoformat()}},
            {"data_scadenza": {"$gte": today.isoformat(), "$lte": to.isoformat()}},
        ],
        "stato": {"$in": ["attiva", "in_corso", "in corso", "vigente"]},
    }
    filt.update(_rbac_polizza_filter(user))
    proj = {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "prodotto": 1,
            "scadenza": 1, "data_scadenza": 1, "premio_lordo": 1,
            "contraente_id": 1, "targa": 1}
    docs = await db.polizze.find(filt, proj).sort("scadenza", 1).limit(limit).to_list(limit)
    cids = list({d.get("contraente_id") for d in docs if d.get("contraente_id")})
    cmap = {}
    if cids:
        cmap = {a["id"]: _fmt_nome(a) async for a in db.anagrafiche.find(
            {"id": {"$in": cids}},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    for d in docs:
        d["contraente_nome"] = cmap.get(d.get("contraente_id"), "—")
        d["link"] = _make_link("polizza", d["id"])
    return docs


async def tool_titoli(
    user: dict,
    anagrafica_id: Optional[str] = None,
    anno: Optional[int] = None,
    solo_incassati: bool = False,
    solo_sospesi: bool = False,
    limit: int = 30,
) -> list[dict]:
    filt: dict = {}
    if anno:
        filt["data_scadenza"] = {"$regex": f"^{anno}"}
    if solo_incassati:
        filt["stato"] = "incassato"
    elif solo_sospesi:
        filt["stato"] = {"$in": ["sospeso", "da_incassare", "aperto"]}
    if anagrafica_id:
        polizze_ids = await db.polizze.find(
            {"contraente_id": anagrafica_id}, {"_id": 0, "id": 1}
        ).to_list(2000)
        ids = [p["id"] for p in polizze_ids]
        if not ids:
            return []
        filt["polizza_id"] = {"$in": ids}
    scope_ids = await _rbac_polizze_ids_scope(user)
    if scope_ids is not None:
        existing = filt.get("polizza_id", {}).get("$in") if isinstance(filt.get("polizza_id"), dict) else None
        if existing is not None:
            filt["polizza_id"] = {"$in": [i for i in existing if i in scope_ids]}
        else:
            filt["polizza_id"] = {"$in": scope_ids}
        if not filt["polizza_id"]["$in"]:
            return []
    proj = {"_id": 0, "id": 1, "polizza_id": 1, "numero_polizza": 1, "importo_lordo": 1,
            "importo_netto": 1, "data_scadenza": 1, "data_incasso": 1, "stato": 1,
            "compagnia_nome": 1, "tipo": 1}
    docs = await db.titoli.find(filt, proj).sort("data_scadenza", -1).limit(limit).to_list(limit)
    for d in docs:
        d["link"] = _make_link("polizza", d.get("polizza_id", ""))
    return docs


async def tool_titoli_sospesi(user: dict, giorni_scaduti: int = 0, limit: int = 40) -> list[dict]:
    """Titoli con stato 'sospeso/da incassare' — pagamenti in ritardo o da incassare."""
    today = _iso_today()
    filt: dict = {
        "$or": [
            {"stato": {"$in": ["sospeso", "da_incassare", "aperto", "in_sospeso"]}},
            {"stato": {"$exists": False}, "data_incasso": None},
        ],
    }
    if giorni_scaduti > 0:
        soglia = (datetime.now(timezone.utc).date() - timedelta(days=giorni_scaduti)).isoformat()
        filt["data_scadenza"] = {"$lte": soglia}
    scope_ids = await _rbac_polizze_ids_scope(user)
    if scope_ids is not None:
        if not scope_ids:
            return []
        filt["polizza_id"] = {"$in": scope_ids}
    proj = {"_id": 0, "id": 1, "polizza_id": 1, "numero_polizza": 1, "importo_lordo": 1,
            "data_scadenza": 1, "stato": 1, "compagnia_nome": 1, "tipo": 1}
    docs = await db.titoli.find(filt, proj).sort("data_scadenza", 1).limit(limit).to_list(limit)
    # arricchisci con contraente
    pol_ids = list({d.get("polizza_id") for d in docs if d.get("polizza_id")})
    pmap = {}
    if pol_ids:
        pmap = {p["id"]: p async for p in db.polizze.find(
            {"id": {"$in": pol_ids}},
            {"_id": 0, "id": 1, "contraente_id": 1, "numero_polizza": 1})}
    cids = list({p.get("contraente_id") for p in pmap.values() if p.get("contraente_id")})
    cmap = {}
    if cids:
        cmap = {a["id"]: _fmt_nome(a) async for a in db.anagrafiche.find(
            {"id": {"$in": cids}},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    for d in docs:
        pol = pmap.get(d.get("polizza_id"), {})
        d["contraente_nome"] = cmap.get(pol.get("contraente_id"), "—")
        d["link"] = _make_link("polizza", d.get("polizza_id", ""))
    return docs


async def tool_sinistri(
    user: dict, anagrafica_id: Optional[str] = None,
    anno: Optional[int] = None, solo_aperti: bool = False, limit: int = 20,
) -> list[dict]:
    filt: dict = {}
    if anagrafica_id:
        filt["anagrafica_id"] = anagrafica_id
    if anno:
        filt["data_sinistro"] = {"$regex": f"^{anno}"}
    if solo_aperti:
        filt["stato"] = {"$in": ["aperto", "in_gestione", "in_lavorazione"]}
    if user.get("role") == "cliente" and user.get("anagrafica_id"):
        filt["anagrafica_id"] = user["anagrafica_id"]
    elif user.get("role") in ("collaboratore", "dipendente"):
        scope_ids = await _rbac_polizze_ids_scope(user)
        if scope_ids is not None:
            if not scope_ids:
                return []
            filt.setdefault("polizza_id", {"$in": scope_ids})
    proj = {"_id": 0, "id": 1, "numero_sinistro": 1, "data_sinistro": 1, "stato": 1,
            "tipo_sinistro": 1, "importo_richiesto": 1, "importo_liquidato": 1,
            "anagrafica_id": 1, "polizza_id": 1}
    docs = await db.sinistri.find(filt, proj).sort("data_sinistro", -1).limit(limit).to_list(limit)
    for d in docs:
        d["link"] = _make_link("sinistro", d["id"])
    return docs


async def tool_veicoli(user: dict, targa: Optional[str] = None,
                       proprietario_id: Optional[str] = None, limit: int = 20) -> list[dict]:
    filt: dict = {}
    if targa:
        filt["targa"] = targa.upper().replace(" ", "")
    if proprietario_id:
        filt["proprietario_id"] = proprietario_id
    if user.get("role") == "cliente" and user.get("anagrafica_id"):
        filt["proprietario_id"] = user["anagrafica_id"]
    proj = {"_id": 0, "id": 1, "targa": 1, "marca": 1, "modello": 1, "telaio": 1,
            "anno_immatricolazione": 1, "alimentazione": 1, "proprietario": 1,
            "proprietario_id": 1}
    docs = await db.veicoli.find(filt, proj).limit(limit).to_list(limit)
    for d in docs:
        d["link"] = _make_link("veicolo", d.get("id", ""))
    return docs


async def tool_cross_sell(user: dict, anagrafica_id: str) -> dict:
    """Rami principali non ancora coperti per il cliente."""
    if user.get("role") == "cliente":
        anagrafica_id = user.get("anagrafica_id") or anagrafica_id
    polizze = await db.polizze.find(
        {"contraente_id": anagrafica_id, "stato": {"$in": ["attiva", "in_emissione", "in_corso"]}},
        {"_id": 0, "ramo": 1},
    ).to_list(200)
    rami_coperti = {(p.get("ramo") or "").lower() for p in polizze if p.get("ramo")}
    RAMI = ["rc_auto", "casa", "abitazione", "vita", "salute",
            "infortuni", "cyber", "tutela_legale"]
    opportunita = [r for r in RAMI if r not in rami_coperti]
    return {
        "cliente_id": anagrafica_id,
        "rami_coperti": sorted(rami_coperti),
        "opportunita_cross_sell": opportunita,
    }


async def tool_portafoglio_summary(user: dict) -> dict:
    """KPI aggregati del portafoglio visibile."""
    role = user.get("role")
    pol_filt = _rbac_polizza_filter(user)
    n_polizze = await db.polizze.count_documents(pol_filt)
    n_attive = await db.polizze.count_documents({**pol_filt, "stato": {"$in": ["attiva", "in_corso"]}})
    n_scadute = await db.polizze.count_documents({**pol_filt, "stato": "scaduta"})
    scope_ids = await _rbac_polizze_ids_scope(user)
    tit_filt: dict = {}
    if scope_ids is not None:
        if not scope_ids:
            n_sospesi = 0
            n_incassati = 0
        else:
            tit_filt["polizza_id"] = {"$in": scope_ids}
    n_sospesi = await db.titoli.count_documents({**tit_filt, "stato": {"$in": ["sospeso", "da_incassare", "aperto"]}})
    n_incassati = await db.titoli.count_documents({**tit_filt, "stato": "incassato"})
    n_sinistri_aperti = await db.sinistri.count_documents({"stato": {"$in": ["aperto", "in_gestione"]}})
    return {
        "ruolo": role,
        "polizze_totali": n_polizze,
        "polizze_attive": n_attive,
        "polizze_scadute": n_scadute,
        "titoli_sospesi": n_sospesi,
        "titoli_incassati": n_incassati,
        "sinistri_aperti": n_sinistri_aperti,
    }


# =========================================================
# DISPATCH — capisce l'intent e raccoglie dati
# =========================================================
KEYWORDS_PAGAMENTI = ["pagament", "titol", "quietanz", "incass", "sospes", "arretrat", "scadut"]
KEYWORDS_POLIZZE = ["polizz", "contratt", "rinnov", "sostituzion"]
KEYWORDS_SCADENZA = ["scadenz", "in scadenza", "prossim", "prossime", "rinnov"]
KEYWORDS_SINISTRI = ["sinistr", "denunc", "danni"]
KEYWORDS_VEICOLI = ["veicol", "auto", "macchin", "moto", "targa"]
KEYWORDS_CROSS_SELL = ["cross-sell", "cross sell", "opportunit", "propost", "cosa proporr", "cosa vend", "cosa manca"]
KEYWORDS_RIEPILOGO = ["riepilog", "totale", "quanti", "quante", "portafogli", "kpi", "stat"]
KEYWORDS_PENSIONE = ["pension", "invalid", "inabilit", "superstit", "reversibil", "scheda calcol",
                     "biblioteca previdenz", "montant", "coeffic", "requisit contribut", "assegno ordinari"]
KEYWORDS_COMPAGNIA = ["compagni", "assicuratore", "provvigion trattien", "logo compagn"]
KEYWORDS_VIDEO = ["video", "corso", "corsi", "formazion", "tutorial"]
KEYWORDS_AGENZIA = ["agenzia", "sede", "sedi", "team", "il nostro team", "orari agenzia", "contatti agenzia",
                    "app cliente", "portale cliente"]
KEYWORDS_PIRAMIDE = ["piramide", "protezion", "coperture cliente"]


async def tool_schede_calcolo(user: dict, categoria: Optional[str] = None) -> list[dict]:
    """Elenca le schede di calcolo previdenziali generate dall'AI e presenti in
    biblioteca (db.schede_calcolo). Se `categoria` specificata, ritorna solo quella."""
    flt: dict = {}
    if categoria:
        flt["categoria"] = {"$regex": re.escape(categoria), "$options": "i"}
    docs = await db.schede_calcolo.find(
        flt, {"_id": 0, "id": 1, "categoria": 1, "anno": 1, "stato_verifica": 1,
              "generated_at": 1, "spiegazione_modifiche": 1, "contenuto.sintesi": 1,
              "contenuto.parametri": 1, "contenuto.formule": 1,
              "contenuto.discrepanze_crm": 1, "modifiche": 1, "fonti": 1},
    ).sort("generated_at", -1).to_list(20)
    # Prende solo l'ultima per ogni categoria
    seen: set[str] = set()
    out = []
    for d in docs:
        cat = d.get("categoria") or ""
        if cat in seen:
            continue
        seen.add(cat)
        contenuto = d.pop("contenuto", {}) or {}
        d["sintesi"] = contenuto.get("sintesi")
        d["n_parametri"] = len(contenuto.get("parametri") or [])
        d["n_formule"] = len(contenuto.get("formule") or [])
        d["n_discrepanze"] = len(contenuto.get("discrepanze_crm") or [])
        d["parametri_principali"] = [
            f"{p.get('nome')} = {p.get('valore')} (fonte: {p.get('fonte')})"
            for p in (contenuto.get("parametri") or [])[:8]
        ]
        d["n_fonti_pdf"] = len(d.pop("fonti", []) or [])
        d["pdf_url"] = f"/api/biblioteca-previdenza/schede-calcolo/{cat}/pdf"
        out.append(d)
    return out


async def tool_compagnie(user: dict, q: Optional[str] = None) -> list[dict]:
    """Elenco compagnie attive (rubrica). Q = filtro su ragione sociale/codice."""
    flt: dict = {"attiva": True}
    if q:
        flt["$or"] = [
            {"ragione_sociale": {"$regex": re.escape(q), "$options": "i"}},
            {"codice": {"$regex": re.escape(q), "$options": "i"}},
        ]
    docs = await db.compagnie.find(
        flt, {"_id": 0, "id": 1, "codice": 1, "ragione_sociale": 1,
              "referente": 1, "email": 1, "telefono": 1, "sito_web": 1,
              "trattiene_provvigioni": 1, "tipo_mandato": 1, "logo_url": 1},
    ).sort("ragione_sociale", 1).to_list(60)
    return docs


async def tool_video_corsi(user: dict) -> list[dict]:
    """Elenco video/corsi pubblicati con filtro RBAC su visibile_ruoli."""
    flt: dict = {"pubblicato": True}
    role = user.get("role")
    if role and role != "admin":
        flt["visibile_ruoli"] = role
    docs = await db.corsi.find(
        flt, {"_id": 0, "id": 1, "titolo": 1, "categoria": 1, "descrizione": 1,
              "video_url": 1, "durata_minuti": 1, "visibile_ruoli": 1,
              "created_at": 1},
    ).sort("created_at", -1).to_list(40)
    for d in docs:
        d["pubblicato_su_app_cliente"] = "cliente" in (d.get("visibile_ruoli") or [])
    return docs


async def tool_agenzia_info(user: dict) -> dict:
    """Dati dell'agenzia (sedi, team, orari, contatti, slogan) da azienda_config."""
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    return {
        "ragione_sociale": az.get("ragione_sociale"),
        "telefono": az.get("telefono"),
        "email": az.get("email"),
        "pec": az.get("pec"),
        "rui": az.get("rui"),
        "indirizzo_principale": az.get("indirizzo"),
        "comune_principale": az.get("comune"),
        "provincia_principale": az.get("provincia"),
        "sito_web": az.get("sito_web"),
        "slogan_portale": az.get("slogan_portale"),
        "n_sedi": len(az.get("portale_sedi") or []),
        "sedi": [
            {"nome": s.get("nome"), "indirizzo": s.get("indirizzo"),
             "comune": s.get("comune"), "provincia": s.get("provincia"),
             "telefono": s.get("telefono"),
             "n_orari": len(s.get("orari") or [])}
            for s in (az.get("portale_sedi") or [])
        ],
        "n_team": len(az.get("portale_team") or []),
        "team": [
            {"nome": m.get("nome"), "ruolo": m.get("ruolo"),
             "email": m.get("email"), "telefono": m.get("telefono"),
             "descrizione": (m.get("descrizione") or "")[:120]}
            for m in (az.get("portale_team") or [])
        ],
        "orari_generici": az.get("portale_orari") or [],
        "assistenza_compagnie": az.get("assistenza_compagnie") or [],
    }


async def tool_piramide_cliente(user: dict, anagrafica_id: str) -> dict:
    """Piramide protezioni v2 del cliente (voci calcolate + dati reddito + testamento)."""
    ac = await db.analisi_cliente.find_one({"anagrafica_id": anagrafica_id}, {"_id": 0}) or {}
    piramide = ac.get("piramide_v2") or {}
    return {
        "anagrafica_id": anagrafica_id,
        "dati_reddito": piramide.get("dati_reddito") or {},
        "testamento": piramide.get("testamento"),
        "eredi_legittimi": piramide.get("eredi_legittimi") or [],
        "n_voci_custom": sum(len(v) for v in (piramide.get("voci_custom") or {}).values()),
        "override_voci": len(piramide.get("override_voci") or {}),
        "stato_voci": piramide.get("stato_voci") or {},
        "n_estratti_inps": len(ac.get("estratti_conto_inps") or []),
        "n_storico_redditi": len(ac.get("storico_redditi") or []),
    }


async def dispatch_query(user_message: str, user: dict) -> dict:
    """Analizza il messaggio, chiama i tool giusti, ritorna dati strutturati."""
    msg = (user_message or "").lower()
    ctx: dict = {}

    # ANNO
    anno = None
    m = re.search(r"\b(20\d{2}|19\d{2})\b", user_message or "")
    if m:
        anno = int(m.group(1))
    m2 = re.search(r"(\d+)\s+anni\s+fa", msg)
    if m2:
        anno = datetime.now(timezone.utc).year - int(m2.group(1))

    # GIORNI (per scadenze future)
    giorni_scad = 30
    m3 = re.search(r"(?:prossim[ei]?\s+)?(\d{1,3})\s+giorn", msg)
    if m3:
        giorni_scad = int(m3.group(1))
    elif "settiman" in msg:
        giorni_scad = 7
    elif "mese" in msg or "mensile" in msg:
        giorni_scad = 30

    # CLIENTE — estrai TUTTI i candidati nome (case-insensitive, min 3 char)
    anagrafica_id = None
    STOP = {
        "chi","cosa","quando","dove","come","perche","perché","quanti","quante",
        "trova","trovami","trovi","mi","mostra","fammi","dimmi","dammi","dimme","dammelo",
        "il","la","le","lo","i","gli","un","una","uno","del","della","dei","degli","delle","al","alla",
        "polizza","polizze","polizzi","cliente","clienti","titolo","titoli","sinistro","sinistri",
        "quanto","costa","costano","prezzo","premio","importo","valore","questo","questa",
        "che","chi","con","per","tra","fra","sono","sta","stanno","hai","ha","tuo","tua","tuoi","tue","mio","mia","miei","mie",
        "assicurativo","assicurazione","assicurazioni","auto","casa","salute","vita","infortuni","rc","rca",
        "dei","gli","le","voglio","vorrei","posso","puoi","tu","io","noi","voi","loro",
        "e","ed","o","od","ma","se","non","già","ancora","anche","altrettanto","cerca","cercami","cercare",
        "buongiorno","ciao","buonasera","salve","grazie","prego",
    }
    # Prima prova la frase intera (senza stop words) come chiave di ricerca
    words = re.findall(r"[A-Za-zÀ-ù']{2,}", user_message or "")
    keep = [w for w in words if w.lower() not in STOP and len(w) >= 3]
    # Cerca combinazioni ad accoppiate + singole (max 3 tentativi)
    tentativi = []
    if len(keep) >= 2:
        tentativi.append(" ".join(keep[:2]))  # es. "bottoni cristian"
        tentativi.append(" ".join(keep[-2:]))  # ultimi 2
    tentativi.extend(keep[:4])  # singoli
    tried = set()
    cands = []
    for cand in tentativi:
        if cand.lower() in tried or len(cand) < 3:
            continue
        tried.add(cand.lower())
        cands.append(cand)
    if cands:
        # ricerche candidati in PARALLELO, si usa il primo match in ordine di priorità
        found_lists = await asyncio.gather(
            *[tool_search_clienti(c, user, limit=5) for c in cands[:5]],
            return_exceptions=True)
        for cand, found in zip(cands, found_lists):
            if isinstance(found, Exception) or not found:
                continue
            ctx[f"Clienti trovati per '{cand}'"] = found
            if len(found) <= 3:
                anagrafica_id = found[0]["id"]
            break

    # TARGA
    targa_m = re.search(r"\b([A-Z]{2}\s?\d{3}\s?[A-Z]{2}|[A-Z]{2}\d{5}|[A-Z]\d{4}[A-Z]{2})\b", (user_message or "").upper())
    if targa_m:
        targa = targa_m.group(1).replace(" ", "")
        v = await tool_veicoli(user, targa=targa, limit=5)
        ctx[f"Veicoli con targa '{targa}'"] = v

    # KEYWORD DISPATCH — tool eseguiti in PARALLELO (asyncio.gather)
    ask_premio = any(k in msg for k in ["quanto costa", "quanto costano", "prezzo", "importo", "quanto pago", "quanto è", "quanto ho pagato"])
    ramo = None
    for r in ["auto", "casa", "vita", "salute", "infortuni", "cyber"]:
        if r in msg:
            ramo = r
            break

    tasks: list[tuple[str, object]] = []
    if any(k in msg for k in KEYWORDS_SCADENZA) and not any(k in msg for k in KEYWORDS_PAGAMENTI):
        tasks.append((f"Polizze in scadenza nei prossimi {giorni_scad} giorni",
                      tool_polizze_in_scadenza(user, giorni=giorni_scad)))
    if any(k in msg for k in KEYWORDS_PAGAMENTI):
        if "sospes" in msg or "arretrat" in msg or "scadut" in msg or "da incass" in msg or "non pagat" in msg:
            tasks.append(("Titoli sospesi/da incassare", tool_titoli_sospesi(user, limit=40)))
        else:
            tasks.append(("Titoli/pagamenti", tool_titoli(user, anagrafica_id=anagrafica_id, anno=anno)))
    if any(k in msg for k in KEYWORDS_POLIZZE) and "scadenz" not in msg:
        tasks.append(("Polizze", tool_polizze(user, anagrafica_id=anagrafica_id, ramo=ramo, anno_scadenza=anno)))
    if any(k in msg for k in KEYWORDS_SINISTRI):
        tasks.append(("Sinistri", tool_sinistri(user, anagrafica_id=anagrafica_id, anno=anno,
                                                solo_aperti=("apert" in msg or "in corso" in msg))))
    if any(k in msg for k in KEYWORDS_VEICOLI) and not targa_m:
        tasks.append(("Veicoli", tool_veicoli(user, proprietario_id=anagrafica_id, limit=15)))
    if any(k in msg for k in KEYWORDS_CROSS_SELL) and anagrafica_id:
        tasks.append(("Analisi cross-sell", tool_cross_sell(user, anagrafica_id)))
    if any(k in msg for k in KEYWORDS_RIEPILOGO):
        tasks.append(("Riepilogo portafoglio", tool_portafoglio_summary(user)))

    # Se ha chiesto "quanto costa" e ha trovato un cliente ma non ha già le polizze
    if ask_premio and anagrafica_id and not any(lbl == "Polizze" for lbl, _ in tasks):
        tasks.append(("Polizze del cliente (con premio)", tool_polizze(user, anagrafica_id=anagrafica_id)))

    # Fallback: cliente trovato ma nessuna keyword → polizze + titoli; niente di niente → riepilogo
    if not tasks:
        if anagrafica_id:
            tasks = [("Polizze del cliente", tool_polizze(user, anagrafica_id=anagrafica_id)),
                     ("Titoli del cliente", tool_titoli(user, anagrafica_id=anagrafica_id, limit=15))]
        elif not ctx:
            tasks = [("Riepilogo portafoglio", tool_portafoglio_summary(user))]

    if tasks:
        results = await asyncio.gather(*[coro for _, coro in tasks], return_exceptions=True)
        for (label, _), res in zip(tasks, results):
            if isinstance(res, Exception):
                logger.warning("Copilot tool '%s' errore: %s", label, res)
            else:
                ctx[label] = res

    return ctx


# =========================================================
# CHAT LLM (Claude Sonnet 4.6) — multi-turno con storia da Mongo
# =========================================================
SYSTEM_PROMPT = """Sei l'AGENTE AI di "Programma Assicurativo", un CRM per agenzie assicurative italiane.
Sei un agente RIGOROSO che risponde ESCLUSIVAMENTE sui dati del CRM dell'utente e degli oggetti visibili al suo ruolo.

═════════════════════════════════════════════════════════════
REGOLE INDEROGABILI
═════════════════════════════════════════════════════════════

1. **FONTE PRIMARIA = CRM**. Basa ogni risposta ESCLUSIVAMENTE sui dati forniti nella sezione
   "Dati recuperati dal DB". Se il dato non è presente rispondi:
   `Non trovato nel CRM. Puoi affinare la ricerca: [suggerimenti]`.

2. **SEGNALA CONOSCENZA ESTERNA**. Se DEVI usare informazioni FUORI dai dati CRM
   (normativa generale, coefficienti INPS non presenti nella biblioteca del CRM,
   procedure standard di settore, conoscenza attuariale, matematica, ecc.),
   DEVI aprire quel paragrafo con il tag esatto, in grassetto:

   `⚠️ **FONTE ESTERNA (fuori CRM):**`

   Subito dopo il tag spiega BREVEMENTE che tipo di conoscenza stai usando
   (es. "normativa L.335/1995 non presente nella Biblioteca Previdenza del CRM").
   NON mescolare mai dati CRM e conoscenza esterna nello stesso paragrafo:
   separa i due blocchi.

3. **NIENTE INVENTATO**. Non inventare mai numeri, ID, importi, date, CF, polizze,
   nomi, telefoni, indirizzi. Se non c'è nel DB → "non trovato".

4. **CITA LA FONTE INTERNA**. Quando riporti un record, cita la collezione tra parentesi
   (es. "polizza n. 12345 (fonte: db.polizze)", "titolo sospeso (fonte: db.titoli)",
   "scheda calcolo DIPENDENTI PRIVATI (fonte: db.schede_calcolo)").

5. **RENDI CLICCABILE**. Ogni cliente/polizza/sinistro citato deve avere link Markdown:
   `[Mario Rossi](/anagrafiche/abc-123)` · `[Polizza 12345](/polizze/xyz)` ·
   `[Sinistro #789](/sinistri/def)`.

6. **FORMATO**:
   - italiano professionale, tono cordiale
   - importi: € 1.234,56 (separatori italiani)
   - date: DD/MM/YYYY
   - tabelle Markdown per >2 righe (max 10, indica se ne mancano altre)

7. **AZIONI CONCRETE**. Chiudi ogni risposta con 1-2 azioni operative
   (📞/✉/📄) coerenti col dato mostrato.

═════════════════════════════════════════════════════════════
CAPACITÀ (tutte basate su dati CRM)
═════════════════════════════════════════════════════════════
- Ricerca clienti (nome, CF, P.IVA, email, cellulare)
- Polizze / titoli / sinistri / veicoli / allegati (con filtri per ramo, anno, stato)
- Scadenze polizze / titoli sospesi
- Cross-sell (rami mancanti nel portafoglio del cliente)
- Riepilogo KPI portafoglio (n° clienti, polizze attive, premi, sinistri)
- Piramide protezioni cliente (voci calcolate)
- Schede di calcolo previdenziale generate dall'AI (Biblioteca Previdenza)
- Compagnie (rubrica, logo, contatti)
- Video/corsi pubblicati sul portale cliente

═════════════════════════════════════════════════════════════
RIFIUTA
═════════════════════════════════════════════════════════════
- News, meteo, argomenti non assicurativi → "Sono l'agente del tuo CRM, non posso occuparmene."
- Modifiche/scritture (crea/aggiorna/elimina) → "Sono in modalità read-only, effettua l'operazione dalla UI."
"""



async def _get_or_create_session(session_id: Optional[str], user: dict) -> str:
    if session_id:
        existing = await db.copilot_sessions.find_one({"id": session_id}, {"_id": 0, "id": 1})
        if existing:
            return session_id
    sid = str(uuid.uuid4())
    await db.copilot_sessions.insert_one({
        "id": sid,
        "user_id": user.get("id"),
        "user_role": user.get("role"),
        "created_at": _now(),
        "updated_at": _now(),
        "title": None,
    })
    return sid


async def _save_message(session_id: str, role: str, content: str, ctx_summary: Optional[dict] = None) -> None:
    await db.copilot_messages.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": role,
        "content": content,
        "context_summary": ctx_summary or {},
        "created_at": _now(),
    })
    await db.copilot_sessions.update_one(
        {"id": session_id},
        {"$set": {"updated_at": _now()}},
    )


async def _get_history(session_id: str, limit: int = MAX_HISTORY_MESSAGES) -> list[dict]:
    if not session_id:
        return []
    docs = await db.copilot_messages.find(
        {"session_id": session_id},
        {"_id": 0, "role": 1, "content": 1, "created_at": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return list(reversed(docs))


def _serialize_ctx(ctx: dict, max_rows: int = 12) -> str:
    """Trasforma il dict di risultati in testo compatto per il modello."""
    out = []
    for label, val in ctx.items():
        out.append(f"### {label}")
        if isinstance(val, list):
            if not val:
                out.append("(nessun risultato)")
                continue
            for row in val[:max_rows]:
                keys = [k for k in row.keys() if k not in {"id"}]
                bits = []
                for k in keys[:8]:
                    v = row.get(k)
                    if v is None or v == "":
                        continue
                    bits.append(f"{k}={v}")
                out.append("- " + " | ".join(bits))
            if len(val) > max_rows:
                out.append(f"...(+ altri {len(val) - max_rows} record)")
        elif isinstance(val, dict):
            for k, v in val.items():
                out.append(f"- {k}: {v}")
        else:
            out.append(str(val))
        out.append("")
    return "\n".join(out)


async def copilot_chat(
    user_message: str, user: dict, session_id: Optional[str] = None,
) -> dict:
    """Endpoint principale: gestisce dispatch, memoria, chiamata Claude."""
    if not EMERGENT_LLM_KEY:
        return {
            "answer": "⚠️ Emergent LLM Key non configurata. Contatta l'amministratore.",
            "session_id": session_id or "",
            "context_summary": {},
        }

    sid = await _get_or_create_session(session_id, user)
    history = await _get_history(sid)

    # 1. Dispatch DB
    ctx = await dispatch_query(user_message, user)
    ctx_str = _serialize_ctx(ctx)

    # 2. Prompt user con contesto + storia condensata
    history_text = ""
    if history:
        hp = []
        for h in history[-8:]:  # ultimi 8
            hp.append(f"{h['role'].upper()}: {h['content'][:400]}")
        history_text = "\n\nCronologia conversazione recente:\n" + "\n".join(hp) + "\n"

    full_prompt = (
        f"Data odierna: {_iso_today()}. Utente: role={user.get('role')} name={user.get('name') or user.get('email')}."
        f"{history_text}"
        f"\n\nDati recuperati dal DB:\n{ctx_str or '(nessun dato)'}"
        f"\n\nDomanda utente: {user_message}"
    )

    try:
        from llm_compat import LlmChat, UserMessage
        model_name, _ = _modo_modello(user_message)
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"copilot_{sid}",
            system_message=SYSTEM_PROMPT,
        ).with_model(COPILOT_MODEL_PROVIDER, model_name)
        resp = await chat.send_message(UserMessage(text=full_prompt))
        answer = str(resp) if resp else "(nessuna risposta)"
    except Exception as e:
        logger.exception("Errore Claude Copilot: %s", e)
        answer = f"⚠️ Errore Claude: {str(e)[:200]}"

    # Summary per UI
    summary = {}
    for k, v in ctx.items():
        summary[k] = len(v) if isinstance(v, list) else 1

    # 3. Salva user + assistant messages
    await _save_message(sid, "user", user_message, {})
    await _save_message(sid, "assistant", answer, summary)

    # Titolo automatico sessione (dalla prima domanda utente)
    sess = await db.copilot_sessions.find_one({"id": sid}, {"_id": 0, "title": 1})
    if sess and not sess.get("title"):
        title = user_message[:60].strip()
        await db.copilot_sessions.update_one({"id": sid}, {"$set": {"title": title}})

    return {
        "answer": answer,
        "session_id": sid,
        "context_summary": summary,
    }


# =========================================================
# STREAMING SSE — meta → delta token → done
# =========================================================
def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def copilot_chat_stream(user_message: str, user: dict, session_id: Optional[str] = None):
    """Generatore SSE: dispatch DB parallelo, modello ibrido, token in streaming."""
    if not EMERGENT_LLM_KEY:
        yield _sse("error", {"error": "Emergent LLM Key non configurata. Contatta l'amministratore."})
        return

    sid = await _get_or_create_session(session_id, user)
    history, ctx = await asyncio.gather(_get_history(sid), dispatch_query(user_message, user))
    ctx_str = _serialize_ctx(ctx)
    summary = {k: (len(v) if isinstance(v, list) else 1) for k, v in ctx.items()}
    model_name, modo = _modo_modello(user_message)
    yield _sse("meta", {"session_id": sid, "context_summary": summary, "modello": modo})

    history_text = ""
    if history:
        hp = [f"{h['role'].upper()}: {h['content'][:400]}" for h in history[-8:]]
        history_text = "\n\nCronologia conversazione recente:\n" + "\n".join(hp) + "\n"
    full_prompt = (
        f"Data odierna: {_iso_today()}. Utente: role={user.get('role')} name={user.get('name') or user.get('email')}."
        f"{history_text}"
        f"\n\nDati recuperati dal DB:\n{ctx_str or '(nessun dato)'}"
        f"\n\nDomanda utente: {user_message}"
    )

    parts: list[str] = []
    try:
        from llm_compat import LlmChat, UserMessage, TextDelta, StreamDone
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"copilot_{sid}",
            system_message=SYSTEM_PROMPT,
        ).with_model(COPILOT_MODEL_PROVIDER, model_name)
        async for ev in chat.stream_message(UserMessage(text=full_prompt)):
            if isinstance(ev, TextDelta):
                parts.append(ev.content)
                yield _sse("delta", {"t": ev.content})
            elif isinstance(ev, StreamDone):
                break
    except Exception as e:
        logger.exception("Errore streaming Copilot: %s", e)
        yield _sse("error", {"error": str(e)[:200]})
        return

    answer = "".join(parts) or "(nessuna risposta)"
    await _save_message(sid, "user", user_message, {})
    await _save_message(sid, "assistant", answer, summary)
    sess = await db.copilot_sessions.find_one({"id": sid}, {"_id": 0, "title": 1})
    if sess and not sess.get("title"):
        await db.copilot_sessions.update_one({"id": sid}, {"$set": {"title": user_message[:60].strip()}})
    yield _sse("done", {"session_id": sid})


# =========================================================
# Session helpers per il frontend (lista/apri/elimina)
# =========================================================
async def list_sessions(user: dict, limit: int = 30) -> list[dict]:
    filt = {"user_id": user.get("id")}
    docs = await db.copilot_sessions.find(filt, {"_id": 0}).sort("updated_at", -1).limit(limit).to_list(limit)
    return docs


async def get_session_messages(session_id: str, user: dict) -> list[dict]:
    sess = await db.copilot_sessions.find_one({"id": session_id, "user_id": user.get("id")}, {"_id": 0})
    if not sess:
        return []
    msgs = await db.copilot_messages.find(
        {"session_id": session_id},
        {"_id": 0, "role": 1, "content": 1, "context_summary": 1, "created_at": 1},
    ).sort("created_at", 1).to_list(500)
    return msgs


async def delete_session(session_id: str, user: dict) -> bool:
    res = await db.copilot_sessions.delete_one({"id": session_id, "user_id": user.get("id")})
    if res.deleted_count == 0:
        return False
    await db.copilot_messages.delete_many({"session_id": session_id})
    return True


# =========================================================
# Compatibilità: mantenuti alias per il vecchio CopilotWidget
# =========================================================
async def dispatch_query_legacy(user_message: str) -> dict:
    """Alias per l'endpoint /copilot/chat vecchio (usato dal CopilotWidget flottante)."""
    fake_user = {"role": "admin", "id": "system"}
    return await dispatch_query(user_message, fake_user)


async def copilot_answer(user_message: str, ctx_data: dict) -> str:
    """Alias legacy per il vecchio widget (senza sessione)."""
    if not EMERGENT_LLM_KEY:
        return "⚠️ Emergent LLM Key non configurata."
    try:
        from llm_compat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"copilot_legacy_{uuid.uuid4().hex[:8]}",
            system_message=SYSTEM_PROMPT,
        ).with_model(COPILOT_MODEL_PROVIDER, COPILOT_MODEL_NAME)
        ctx_str = _serialize_ctx(ctx_data)
        prompt = f"Data odierna: {_iso_today()}.\n\nDomanda: {user_message}\n\nDati:\n{ctx_str or '(vuoto)'}"
        resp = await chat.send_message(UserMessage(text=prompt))
        return str(resp) if resp else "(nessuna risposta)"
    except Exception as e:
        logger.error("Copilot legacy LLM error: %s", e)
        return f"⚠️ Errore: {str(e)[:200]}"
