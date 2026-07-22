"""Anagrafiche routes — endpoint CRUD + KPI + network + relazioni + documenti
+ privacy + firma digitale + INPS auto + interviste.

Estratto da server.py (iter23) — blocco 1 (~25 endpoint, ~750 righe).

Altri endpoint anagrafica (analisi cliente, calcolo pensione, tags auto-genera,
riepilogo, diario) restano in server.py e verranno estratti in passi successivi
(`routes/anagrafiche_analisi.py`, `routes/anagrafiche_diario.py`).
"""
from __future__ import annotations
import base64
import io as _io
import logging
import os
import re
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, UploadFile,
)
from fastapi.responses import StreamingResponse

from database import db
from db_models import (
    Anagrafica, Intervista, _now_iso, _uid,
)
from auth import current_user, require_user
from shared import log_attivita, log_diario_cliente, strip_mongo_id
import storage as obj_storage
import inps_calculator
import geocoder as geocoder_svc

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# HELPERS
# ============================================================
UPPER_FIELDS = {
    "ragione_sociale", "nome", "cognome", "codice_fiscale", "partita_iva",
    "comune", "provincia", "comune_nascita", "provincia_nascita",
    "indirizzo", "professione", "stato_civile", "titolo_studio",
    "iban", "intestatario", "provincia_intestatario", "veicolo_marca",
    "veicolo_modello", "targa", "veicolo_targa_rimorchio", "numero_polizza",
    "numero_sinistro", "ragione_sociale", "codice", "nome_file",
}

ANAGRAFICA_DOC_TIPI = {
    "carta_identita", "patente", "passaporto", "codice_fiscale_doc",
    "tessera_sanitaria", "visura_camerale", "estratto_contributivo",
    "privacy_firmata", "mandato_sdd", "altro",
}


def _normalize_upper(body: dict) -> dict:
    """Normalizza in MAIUSCOLO i campi anagrafici/polizza dove ha senso.

    Email/url restano come sono.
    """
    out = dict(body or {})
    for k, v in list(out.items()):
        if k in UPPER_FIELDS and isinstance(v, str):
            out[k] = v.strip().upper()
    # auto-composizione ragione_sociale per persone fisiche
    if out.get("tipo") == "persona_fisica":
        nome = (out.get("nome") or "").strip().upper()
        cognome = (out.get("cognome") or "").strip().upper()
        if nome or cognome:
            out["ragione_sociale"] = f"{cognome} {nome}".strip()
    return out


async def _auto_geocode(body: dict) -> dict:
    """Se l'indirizzo è valorizzato e lat/lng mancano (o indirizzo è cambiato),
    chiama Nominatim per ottenere le coordinate."""
    ind = body.get("indirizzo")
    com = body.get("comune")
    if not (ind and com):
        return body
    if body.get("lat") and body.get("lng"):
        return body
    try:
        res = await geocoder_svc.geocoda_indirizzo(
            indirizzo=ind, comune=com,
            cap=body.get("cap") or "", provincia=body.get("provincia") or "",
        )
        if res and res.get("lat"):
            body["lat"] = res["lat"]
            body["lng"] = res["lng"]
    except Exception:
        pass
    return body


# ============================================================
# KPI CUSTOM
# ============================================================
@router.get("/anagrafiche/kpi-custom")
async def list_kpi_custom(user: dict = Depends(current_user)):
    """Lista KPI custom dell'utente corrente."""
    if user["role"] == "cliente":
        return []
    items = await db.kpi_anagrafiche_custom.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("ordine", 1).to_list(50)
    return items


@router.post("/anagrafiche/kpi-custom", status_code=201)
async def crea_kpi_custom(body: dict, user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Crea una KPI custom basata su tag.
    body = {label, tag, color (sky|emerald|amber|violet|rose|pink|orange), icon}
    """
    label = (body.get("label") or "").strip()
    tag = (body.get("tag") or "").strip().lower()
    if not label or not tag:
        raise HTTPException(400, "label e tag richiesti")
    color = body.get("color") or "sky"
    icon = body.get("icon") or "Star"
    doc = {
        "id": _uid(),
        "user_id": user["id"],
        "label": label,
        "tag": tag,
        "color": color,
        "icon": icon,
        "ordine": int(body.get("ordine") or 99),
        "created_at": _now_iso(),
    }
    await db.kpi_anagrafiche_custom.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/anagrafiche/kpi-custom/{kid}")
async def rimuovi_kpi_custom(kid: str, user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    res = await db.kpi_anagrafiche_custom.delete_one({"id": kid, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Non trovata")
    return {"ok": True}


# ============================================================
# TAGS + STATS
# ============================================================
@router.get("/anagrafiche/tags")
async def list_tags(user: dict = Depends(current_user)):
    """Restituisce la lista di tutti i tag univoci usati nelle anagrafiche."""
    if user["role"] == "cliente":
        return []
    tags = await db.anagrafiche.distinct("tags")
    return sorted([t for t in tags if t])


@router.get("/anagrafiche/stats")
async def anagrafiche_stats(user: dict = Depends(current_user)):
    """KPI aggregati anagrafiche.

    Categorizzazione (euristica su ragione_sociale + tipo + tags):
      - privati: persona_fisica
      - aziende: persona_giuridica, NON condominio/parrocchia
      - condomini: ragione_sociale contiene CONDOMINIO o tag 'condominio'
      - parrocchie: ragione_sociale contiene PARROCCHIA o tag 'parrocchia'

    Per ogni categoria ritorna {n, premio_totale} (premio totale dalle polizze attive).
    """
    if user["role"] == "cliente":
        raise HTTPException(403, "Permesso negato")
    anas = await db.anagrafiche.find({}, {"_id": 0, "id": 1, "tipo": 1, "ragione_sociale": 1, "tags": 1}).to_list(20000)
    bucket: dict[str, list] = {"privati": [], "aziende": [], "condomini": [], "parrocchie": []}
    for a in anas:
        rs = (a.get("ragione_sociale") or "").upper()
        tags = a.get("tags") or []
        if "PARROCCHIA" in rs or "parrocchia" in tags:
            bucket["parrocchie"].append(a["id"])
        elif "CONDOMINIO" in rs or "condominio" in tags:
            bucket["condomini"].append(a["id"])
        elif a.get("tipo") == "persona_giuridica":
            bucket["aziende"].append(a["id"])
        else:
            bucket["privati"].append(a["id"])
    out: dict = {}
    for k, ids in bucket.items():
        premio = 0.0
        if ids:
            agg = await db.polizze.aggregate([
                {"$match": {"contraente_id": {"$in": ids}, "stato": {"$in": ["attiva", "in_emissione"]}}},
                {"$group": {"_id": None, "tot": {"$sum": "$premio_lordo"}}},
            ]).to_list(1)
            premio = float(agg[0]["tot"]) if agg else 0.0
        out[k] = {"n": len(ids), "premio_totale": round(premio, 2)}
    out["totale"] = {
        "n": sum(v["n"] for v in out.values()),
        "premio_totale": round(sum(v["premio_totale"] for v in out.values()), 2),
    }
    # KPI custom basate sui tag dell'utente
    kpi_customs = await db.kpi_anagrafiche_custom.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("ordine", 1).to_list(50)
    custom_out = []
    for k in kpi_customs:
        tag = k.get("tag")
        if not tag:
            continue
        ids_tag = [a["id"] async for a in db.anagrafiche.find(
            {"tags": tag}, {"_id": 0, "id": 1},
        )]
        premio = 0.0
        if ids_tag:
            agg = await db.polizze.aggregate([
                {"$match": {"contraente_id": {"$in": ids_tag},
                            "stato": {"$in": ["attiva", "in_emissione"]}}},
                {"$group": {"_id": None, "tot": {"$sum": "$premio_lordo"}}},
            ]).to_list(1)
            premio = float(agg[0]["tot"]) if agg else 0.0
        custom_out.append({
            "id": k["id"],
            "label": k["label"],
            "tag": tag,
            "color": k.get("color", "sky"),
            "icon": k.get("icon", "Star"),
            "n": len(ids_tag),
            "premio_totale": round(premio, 2),
        })
    out["custom"] = custom_out
    return out


# ============================================================
# CRUD
# ============================================================
@router.get("/anagrafiche")
async def list_anagrafiche(
    q: Optional[str] = None,
    limit: int = 5000,
    tag: Optional[str] = None,
    user: dict = Depends(current_user),
):
    flt: dict = {}
    if user["role"] == "cliente" and user.get("anagrafica_id"):
        flt["id"] = user["anagrafica_id"]
    if q:
        # Multi-token AND: ogni token deve combaciare in almeno uno dei campi.
        tokens = [t for t in re.split(r"\s+", q.strip()) if t]
        and_clauses = []
        for tok in tokens:
            and_clauses.append({"$or": [
                {"ragione_sociale": {"$regex": re.escape(tok), "$options": "i"}},
                {"codice_fiscale": {"$regex": re.escape(tok), "$options": "i"}},
                {"partita_iva": {"$regex": re.escape(tok), "$options": "i"}},
                {"email": {"$regex": re.escape(tok), "$options": "i"}},
                {"telefono": {"$regex": re.escape(tok), "$options": "i"}},
                {"cellulare": {"$regex": re.escape(tok), "$options": "i"}},
            ]})
        if and_clauses:
            flt["$and"] = and_clauses
    if tag:
        flt["tags"] = tag
    items = await db.anagrafiche.find(flt, {"_id": 0}).sort("ragione_sociale", 1).to_list(limit)
    if not items:
        return items
    # arricchimento: conteggio polizze attive per colorazione
    ids = [a["id"] for a in items]
    pipeline = [
        {"$match": {"contraente_id": {"$in": ids}, "stato": "attiva"}},
        {"$group": {"_id": "$contraente_id", "n": {"$sum": 1}}},
    ]
    counts = {row["_id"]: row["n"] async for row in db.polizze.aggregate(pipeline)}
    # collaboratore lookup
    collab_ids = list({a.get("collaboratore_id") for a in items if a.get("collaboratore_id")})
    collab_map = {}
    if collab_ids:
        async for u in db.users.find({"id": {"$in": collab_ids}}, {"_id": 0, "id": 1, "name": 1}):
            collab_map[u["id"]] = u["name"]
    for a in items:
        a["polizze_attive_count"] = counts.get(a["id"], 0)
        a["collaboratore_nome"] = collab_map.get(a.get("collaboratore_id")) if a.get("collaboratore_id") else None
        # categoria per colorazione frontend
        rs = (a.get("ragione_sociale") or "").upper()
        is_condominio = ("CONDOMINIO" in rs) or ("condominio" in (a.get("tags") or []))
        if is_condominio:
            a["categoria_ui"] = "condominio"
        elif a["polizze_attive_count"] > 0:
            a["categoria_ui"] = "con_polizze"
        else:
            a["categoria_ui"] = "senza_polizze"
    return items


@router.get("/anagrafiche/check-duplicate")
async def check_anagrafica_duplicate(
    codice_fiscale: Optional[str] = None,
    partita_iva: Optional[str] = None,
    tipo: Optional[str] = None,
    user: dict = Depends(current_user),
):
    """Verifica se esiste già un'anagrafica con lo stesso CF (persona fisica) o P.IVA
    (persona giuridica). Usato dai flussi di import OCR / Excel per chiedere
    all'utente se sovrascrivere.

    NOTA: questa route DEVE essere definita PRIMA di `GET /anagrafiche/{aid}`
    altrimenti FastAPI la interpreta come `aid="check-duplicate"`.

    Query:
      - codice_fiscale (opzionale)
      - partita_iva (opzionale)
      - tipo: "persona_fisica" | "persona_giuridica" (opzionale, restringe il match)

    Risposta:
      {"existing": {id, ragione_sociale, tipo, codice_fiscale, partita_iva,
                    updated_at, cognome, nome} | null,
       "match_on": "codice_fiscale" | "partita_iva" | null}
    """
    cf = (codice_fiscale or "").strip().upper() or None
    piva = (partita_iva or "").strip() or None
    if not cf and not piva:
        return {"existing": None, "match_on": None}

    # Costruisci query priorità: persona_giuridica → P.IVA primo; persona_fisica → CF primo.
    order = []
    if tipo == "persona_giuridica":
        if piva:
            order.append(("partita_iva", {"partita_iva": piva}))
        if cf:
            order.append(("codice_fiscale", {"codice_fiscale": cf}))
    else:
        if cf:
            order.append(("codice_fiscale", {"codice_fiscale": cf}))
        if piva:
            order.append(("partita_iva", {"partita_iva": piva}))

    proj = {"_id": 0, "id": 1, "ragione_sociale": 1, "tipo": 1,
            "codice_fiscale": 1, "partita_iva": 1, "cognome": 1, "nome": 1,
            "updated_at": 1, "created_at": 1}
    for match_on, flt in order:
        doc = await db.anagrafiche.find_one(flt, proj)
        if doc:
            return {"existing": doc, "match_on": match_on}
    return {"existing": None, "match_on": None}


@router.get("/anagrafiche/{aid}")
async def get_anagrafica(aid: str, user: dict = Depends(current_user)):
    if user["role"] == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Permesso negato")
    doc = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Non trovata")
    relazioni_risolte = []
    for rel in doc.get("parente_di", []):
        rel_doc = await db.anagrafiche.find_one(
            {"id": rel.get("anagrafica_id")},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "codice_fiscale": 1, "data_nascita": 1},
        )
        if rel_doc:
            relazioni_risolte.append({
                **rel_doc,
                "relazione": rel.get("relazione"),
                "lavoratore": rel.get("lavoratore"),
                "a_carico": rel.get("a_carico"),
                "handicap": rel.get("handicap"),
            })
    doc["relazioni_risolte"] = relazioni_risolte
    return doc


@router.post("/anagrafiche", status_code=201)
async def create_anagrafica(body: dict, user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    body = _normalize_upper(body)
    body = await _auto_geocode(body)
    # Default collaboratore_id = utente loggato se non specificato (visibilità)
    if not body.get("collaboratore_id"):
        body["collaboratore_id"] = user.get("id")

    # Se il chiamante indica overwrite_id (flusso import OCR/Excel con conferma
    # utente), esegue una UPDATE sull'anagrafica esistente invece di crearne
    # una nuova. Restituisce comunque lo status_code=201 + il documento aggiornato.
    overwrite_id = body.pop("overwrite_id", None)
    if overwrite_id:
        existing = await db.anagrafiche.find_one({"id": overwrite_id}, {"_id": 0, "id": 1})
        if not existing:
            raise HTTPException(404, f"Anagrafica {overwrite_id} non trovata per sovrascrittura")
        # Rimuovi id/created_at dal payload per non sovrascriverli con valori del form
        body.pop("id", None)
        body.pop("created_at", None)
        body["updated_at"] = _now_iso()
        await db.anagrafiche.update_one({"id": overwrite_id}, {"$set": body})
        updated = strip_mongo_id(await db.anagrafiche.find_one({"id": overwrite_id}, {"_id": 0}))
        await log_attivita(user, "overwrite", "anagrafica", overwrite_id,
                           f"Anagrafica sovrascritta da import: {updated.get('ragione_sociale')}")
        return updated

    obj = Anagrafica(**body)
    await db.anagrafiche.insert_one(obj.model_dump())
    await log_attivita(user, "create", "anagrafica", obj.id, f"Creata anagrafica {obj.ragione_sociale}")
    return obj.model_dump()


@router.put("/anagrafiche/{aid}")
async def update_anagrafica(aid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    body = _normalize_upper(body)
    # Re-geocodifica se l'indirizzo è cambiato
    existing = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "indirizzo": 1, "comune": 1, "cap": 1, "lat": 1, "lng": 1})
    if existing and any(body.get(k) != existing.get(k) for k in ("indirizzo", "comune", "cap") if k in body):
        body["lat"] = None
        body["lng"] = None
        body = await _auto_geocode(body)
    body["updated_at"] = _now_iso()
    res = await db.anagrafiche.update_one({"id": aid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Non trovata")
    await log_attivita(user, "update", "anagrafica", aid)
    return strip_mongo_id(await db.anagrafiche.find_one({"id": aid}, {"_id": 0}))


@router.delete("/anagrafiche/{aid}")
async def delete_anagrafica(
    aid: str,
    force: bool = False,
    user: dict = Depends(require_user("admin")),
):
    """Elimina un'anagrafica.

    Se force=false (default) e l'anagrafica ha polizze, titoli o sinistri
    collegati, blocca l'operazione con 409 CONFLICT e ritorna il numero
    di record collegati per ciascuna entità. L'utente deve confermare
    passando force=true per procedere con la cascade delete.

    Nota: con force=true vengono ELIMINATE anche:
      - polizze, titoli (di quelle polizze), sinistri, allegati, diario,
        interviste, avvisi, raccolta_dati, potenti_domande.
    """
    anag = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "id": 1, "ragione_sociale": 1})
    if not anag:
        raise HTTPException(404, "Anagrafica non trovata")

    # Conta collegati
    n_polizze = await db.polizze.count_documents({"contraente_id": aid})
    n_sinistri = await db.sinistri.count_documents({"anagrafica_id": aid})
    n_allegati = await db.allegati.count_documents({"anagrafica_id": aid})

    if not force and (n_polizze or n_sinistri):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Anagrafica con record collegati. Confermare eliminazione a cascata.",
                "collegati": {
                    "polizze": n_polizze,
                    "sinistri": n_sinistri,
                    "allegati": n_allegati,
                },
                "ragione_sociale": anag.get("ragione_sociale"),
            },
        )

    # Cascade: recupera IDs delle polizze per eliminare titoli
    polizze_ids: List[str] = []
    async for p in db.polizze.find({"contraente_id": aid}, {"_id": 0, "id": 1}):
        polizze_ids.append(p["id"])

    # Elimina in cascata
    if polizze_ids:
        await db.titoli.delete_many({"polizza_id": {"$in": polizze_ids}})
        await db.polizze.delete_many({"id": {"$in": polizze_ids}})
    await db.sinistri.delete_many({"anagrafica_id": aid})
    await db.allegati.delete_many({"anagrafica_id": aid})
    for coll in ("diario_voci", "interviste", "avvisi", "raccolta_dati", "potenti_domande"):
        try:
            await db[coll].delete_many({"anagrafica_id": aid})
        except Exception:
            pass

    await db.anagrafiche.delete_one({"id": aid})
    await log_attivita(
        user, "delete", "anagrafica", aid,
        f"Anagrafica '{anag.get('ragione_sociale')}' eliminata "
        f"(polizze={n_polizze}, sinistri={n_sinistri}, allegati={n_allegati})"
    )
    return {
        "ok": True,
        "cascade": {"polizze": n_polizze, "sinistri": n_sinistri, "allegati": n_allegati},
    }


# ============================================================
# NETWORK + RELAZIONI
# ============================================================
@router.get("/anagrafiche/{aid}/network")
async def anagrafica_network(aid: str, user: dict = Depends(current_user)):
    """Restituisce TUTTE le anagrafiche collegate (parenti, legali rappresentanti,
    aziende rappresentate, capofamiglia, ecc.) con per ognuna:
      - n_polizze attive/preventivi/totali
      - premio_totale, provvigioni_totale (lordi su tutte le polizze)
    e i totali aggregati del network.

    Restituisce anche l'anagrafica root.
    """
    if user["role"] == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Permesso negato")
    root = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not root:
        raise HTTPException(404, "Non trovata")

    rel_ids = [r.get("anagrafica_id") for r in root.get("parente_di", []) if r.get("anagrafica_id")]
    rel_ids = list(dict.fromkeys(rel_ids))
    relazione_per_id = {r["anagrafica_id"]: r.get("relazione") for r in root.get("parente_di", [])}

    all_ids = [aid] + rel_ids
    docs = {}
    async for a in db.anagrafiche.find({"id": {"$in": all_ids}}, {"_id": 0}):
        docs[a["id"]] = a

    async def _stats(anag_id) -> dict:
        n_attive = 0
        n_preventivo = 0
        n_tot = 0
        premio = 0.0
        provv = 0.0
        async for p in db.polizze.find(
            {"contraente_id": anag_id},
            {"_id": 0, "stato": 1, "premio_totale": 1, "provvigione_totale": 1, "numero_polizza": 1},
        ):
            n_tot += 1
            stato = (p.get("stato") or "").lower()
            if stato in ("attiva", "in_emissione"):
                n_attive += 1
            elif stato in ("preventivo", "bozza"):
                n_preventivo += 1
            premio += float(p.get("premio_totale") or 0)
            provv += float(p.get("provvigione_totale") or 0)
        return {
            "n_polizze_attive": n_attive,
            "n_preventivi": n_preventivo,
            "n_polizze_totali": n_tot,
            "premio_totale": round(premio, 2),
            "provvigioni_totale": round(provv, 2),
        }

    def _light(d, relazione=None) -> dict:
        return {
            "id": d.get("id"),
            "ragione_sociale": d.get("ragione_sociale"),
            "tipo": d.get("tipo"),
            "codice_fiscale": d.get("codice_fiscale"),
            "partita_iva": d.get("partita_iva"),
            "email": d.get("email"),
            "telefono": d.get("telefono") or d.get("cellulare"),
            "comune": d.get("comune"),
            "provincia": d.get("provincia"),
            "relazione": relazione,
        }

    out_root = _light(root)
    out_root.update(await _stats(aid))

    out_rel = []
    tot_premio = out_root["premio_totale"]
    tot_provv = out_root["provvigioni_totale"]
    tot_polizze = out_root["n_polizze_totali"]
    tot_attive = out_root["n_polizze_attive"]
    tot_preventivi = out_root["n_preventivi"]
    for rid in rel_ids:
        d = docs.get(rid)
        if not d:
            continue
        rel = relazione_per_id.get(rid)
        item = _light(d, relazione=rel)
        st = await _stats(rid)
        item.update(st)
        out_rel.append(item)
        tot_premio += st["premio_totale"]
        tot_provv += st["provvigioni_totale"]
        tot_polizze += st["n_polizze_totali"]
        tot_attive += st["n_polizze_attive"]
        tot_preventivi += st["n_preventivi"]

    return {
        "root": out_root,
        "collegati": out_rel,
        "totali": {
            "n_persone": 1 + len(out_rel),
            "n_polizze_attive": tot_attive,
            "n_preventivi": tot_preventivi,
            "n_polizze_totali": tot_polizze,
            "premio_totale": round(tot_premio, 2),
            "provvigioni_totale": round(tot_provv, 2),
        },
    }


@router.post("/anagrafiche/{aid}/relazioni")
async def add_relazione(aid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Aggiunge una relazione di parentela bidirezionale.

    Attributi opzionali (impattano assegno familiare / nucleo familiare):
      - lavoratore: bool  (per coniuge: se True non è a carico)
      - a_carico:   bool  (per figli/coniuge)
      - handicap:   bool  (per figli con disabilità)
    """
    target = body.get("anagrafica_id")
    relazione = body.get("relazione", "altro")
    relazione_inversa = body.get("relazione_inversa", "altro")
    if not target or target == aid:
        raise HTTPException(400, "anagrafica_id non valido")
    extra_dir = {}
    for k in ("lavoratore", "a_carico", "handicap"):
        if k in body and body[k] is not None:
            extra_dir[k] = bool(body[k])
    extra_inv = {}
    for k in ("lavoratore_inverso", "a_carico_inverso", "handicap_inverso"):
        if k in body and body[k] is not None:
            extra_inv[k.replace("_inverso", "")] = bool(body[k])
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$push": {"parente_di": {"anagrafica_id": target, "relazione": relazione, **extra_dir}}},
    )
    await db.anagrafiche.update_one(
        {"id": target},
        {"$push": {"parente_di": {"anagrafica_id": aid, "relazione": relazione_inversa, **extra_inv}}},
    )
    await log_attivita(user, "update", "anagrafica", aid,
                       f"Relazione {relazione} con {target}")
    return {"ok": True}


@router.patch("/anagrafiche/{aid}/relazioni/{target_id}")
async def update_relazione(
    aid: str, target_id: str, body: dict,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Aggiorna gli attributi di una relazione esistente (lavoratore / a_carico / handicap)."""
    set_fields = {}
    for k in ("lavoratore", "a_carico", "handicap"):
        if k in body:
            set_fields[f"parente_di.$.{k}"] = bool(body[k]) if body[k] is not None else None
    if "relazione" in body and body["relazione"]:
        set_fields["parente_di.$.relazione"] = body["relazione"]
    if not set_fields:
        return {"ok": True, "no_changes": True}
    res = await db.anagrafiche.update_one(
        {"id": aid, "parente_di.anagrafica_id": target_id},
        {"$set": set_fields},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Relazione non trovata")
    await log_attivita(user, "update", "anagrafica", aid, f"Aggiornati attributi relazione con {target_id}")
    return {"ok": True}


@router.delete("/anagrafiche/{aid}/relazioni/{target_id}")
async def remove_relazione(aid: str, target_id: str, user: dict = Depends(require_user("admin", "collaboratore"))):
    await db.anagrafiche.update_one(
        {"id": aid}, {"$pull": {"parente_di": {"anagrafica_id": target_id}}}
    )
    await db.anagrafiche.update_one(
        {"id": target_id}, {"$pull": {"parente_di": {"anagrafica_id": aid}}}
    )
    return {"ok": True}


# ============================================================
# DOCUMENTI ANAGRAFICA + FIRMA DIGITALE
# ============================================================
@router.post("/anagrafiche/{aid}/documenti/{tipo}")
async def upload_documento_anagrafica(
    aid: str, tipo: str,
    file: UploadFile = File(...),
    scadenza: Optional[str] = Form(None),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Carica un documento del cliente (CI, patente, passaporto, CF, privacy firmata, ecc.)."""
    if tipo not in ANAGRAFICA_DOC_TIPI:
        raise HTTPException(400, f"Tipo non valido: {tipo}")
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "id": 1, "ragione_sociale": 1})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 15 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    ext = (file.filename or "doc.bin").rsplit(".", 1)[-1].lower() or "bin"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{aid}/{tipo}_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, ct)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    url = f"/api/storage/{result['path']}"
    doc_entry = {
        "url": url, "storage_path": result["path"],
        "nome_file": file.filename, "mime": ct,
        "size_kb": round(len(data) / 1024, 1),
        "data_caricamento": _now_iso(),
        "scadenza": scadenza,
        "caricato_da": user.get("id"),
    }
    set_fields = {f"documenti.{tipo}": doc_entry, "updated_at": _now_iso()}
    if tipo == "privacy_firmata":
        set_fields.update({
            "privacy_firmata_url": url,
            "privacy_firmata_il": _now_iso(),
            "consenso_privacy": True,
            "data_consenso_privacy": _now_iso()[:10],
        })
    await db.anagrafiche.update_one({"id": aid}, {"$set": set_fields})
    await log_attivita(user, "upload", "anagrafica_doc", aid, f"Caricato {tipo}: {file.filename}")
    await log_diario_cliente(aid, "documento",
        titolo=f"Caricato documento: {tipo.replace('_', ' ')}",
        descrizione=f"File: {file.filename} ({doc_entry['size_kb']} KB)", autore=user)
    return {tipo: doc_entry}


@router.delete("/anagrafiche/{aid}/documenti/{tipo}")
async def delete_documento_anagrafica(aid: str, tipo: str,
                                       user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    if tipo not in ANAGRAFICA_DOC_TIPI:
        raise HTTPException(400, "Tipo non valido")
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$unset": {f"documenti.{tipo}": ""}, "$set": {"updated_at": _now_iso()}},
    )
    return {"ok": True}


# ============================================================
# PRIVACY GDPR
# ============================================================
@router.get("/anagrafiche/{aid}/privacy/genera-pdf")
async def genera_pdf_privacy(aid: str, salva_archivio: bool = False, user: dict = Depends(current_user)):
    """Genera PDF informativa privacy GDPR completa con checkbox consensi e firma.
    Se salva_archivio=true, salva anche il PDF nello storage e in documenti.privacy_firmata."""
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    cfg = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    import pdf_privacy
    pdf = pdf_privacy.genera_privacy_pdf(ana, cfg, dipendente_nome=user.get("name", ""))
    fname = f"privacy_{ana.get('codice_fiscale') or aid}.pdf"

    if salva_archivio:
        storage_path = (
            f"{os.environ.get('APP_NAME', 'assicura')}/"
            f"anagrafiche/{aid}/privacy/{_uid()}.pdf"
        )
        try:
            res = obj_storage.put_object(storage_path, pdf, "application/pdf")
            url_pdf = f"/api/storage/{res['path']}"
            documenti = dict(ana.get("documenti") or {})
            documenti["privacy_firmata"] = {
                "url": url_pdf,
                "storage_path": res["path"],
                "nome_file": fname,
                "size_kb": round(len(pdf) / 1024, 1),
                "data_caricamento": _now_iso(),
                "caricato_da_nome": user.get("name") or user.get("email"),
                "tipo": "privacy_firmata",
            }
            await db.anagrafiche.update_one(
                {"id": aid},
                {"$set": {
                    "documenti": documenti,
                    "privacy_firmata_url": url_pdf,
                    "privacy_firmata_il": _now_iso(),
                    "consenso_privacy": True,
                    "data_consenso_privacy": _now_iso()[:10],
                    "updated_at": _now_iso(),
                }},
            )
            await log_attivita(user, "privacy_firmata", "anagrafica", aid,
                               descrizione="PDF privacy firmato e salvato in archivio")
        except Exception as e:
            logger.error("Errore salvataggio PDF privacy in archivio: %s", e)

    return StreamingResponse(
        _io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={fname}"},
    )


@router.put("/anagrafiche/{aid}/consensi-privacy")
async def aggiorna_consensi_privacy(
    aid: str, body: dict,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Aggiorna i 4 consensi specifici dell'informativa GDPR.
    body: {consenso_dati_particolari, consenso_commerciale, consenso_comunicazione_terzi,
           consenso_profilazione, data_consenso_privacy?}"""
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    allowed = {
        "consenso_dati_particolari", "consenso_commerciale",
        "consenso_comunicazione_terzi", "consenso_profilazione",
        "consenso_privacy",
    }
    upd: dict = {k: bool(v) for k, v in body.items() if k in allowed}
    if any(upd.get(k) for k in ("consenso_dati_particolari", "consenso_commerciale",
                                 "consenso_comunicazione_terzi", "consenso_profilazione")):
        upd["consenso_privacy"] = True
    if upd:
        upd["data_consenso_privacy"] = body.get("data_consenso_privacy") or _now_iso()[:10]
        upd["updated_at"] = _now_iso()
        await db.anagrafiche.update_one({"id": aid}, {"$set": upd})
        await log_attivita(user, "consensi_privacy", "anagrafica", aid,
                           descrizione=f"Aggiornati: {list(upd.keys())}")
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    return ana


# ============================================================
# FIRMA DIGITALE


@router.post("/anagrafiche/{aid}/avatar")
async def upload_avatar(
    aid: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Upload/sostituzione avatar (foto persona, logo azienda, immagine edificio)."""
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "id": 1})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 5 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "avatar.png")
    if not (ct or "").startswith("image/"):
        raise HTTPException(400, "Il file deve essere un'immagine")
    ext = (file.filename or "avatar.png").rsplit(".", 1)[-1].lower() or "png"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{aid}/avatar_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, ct)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    url = f"/api/storage/{result['path']}"
    await db.anagrafiche.update_one({"id": aid},
                                    {"$set": {"avatar_url": url, "updated_at": _now_iso()}})
    return {"ok": True, "avatar_url": url}


@router.delete("/anagrafiche/{aid}/avatar")
async def delete_avatar(
    aid: str,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    await db.anagrafiche.update_one({"id": aid},
                                    {"$set": {"avatar_url": None, "updated_at": _now_iso()}})
    return {"ok": True}

# ============================================================
@router.post("/anagrafiche/{aid}/firma-digitale")
async def salva_firma_cliente(aid: str, body: dict,
                               user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Salva la firma del cliente come immagine PNG (canvas base64)."""
    img_data = body.get("immagine_base64") or body.get("data")
    if not img_data:
        raise HTTPException(400, "immagine_base64 richiesta")
    if "," in img_data:
        img_data = img_data.split(",", 1)[1]
    try:
        raw = base64.b64decode(img_data)
    except Exception:
        raise HTTPException(400, "Base64 non valido")
    path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{aid}/firma_{_uid()}.png"
    try:
        result = obj_storage.put_object(path, raw, "image/png")
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    url = f"/api/storage/{result['path']}"
    await db.anagrafiche.update_one({"id": aid},
        {"$set": {"firma_cliente_url": url, "updated_at": _now_iso()}})
    await log_attivita(user, "firma", "anagrafica", aid, "Firma digitale salvata")
    return {"firma_cliente_url": url}


# ============================================================
# CALCOLO INPS AUTO DA ESTRATTO CONTRIBUTIVO
# ============================================================
@router.post("/anagrafiche/{aid}/calcolo-pensione/auto-da-estratto")
async def calcola_pensione_da_estratto(
    aid: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Carica un PDF estratto contributivo INPS, estrae i dati e popola
    settimane contributive + data inizio contribuzione sull'anagrafica.
    Salva anche il PDF come documento 'estratto_contributivo'.
    """
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande")
    ext = (file.filename or "ec.pdf").rsplit(".", 1)[-1].lower() or "pdf"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{aid}/estratto_contributivo_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, "application/pdf")
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    url = f"/api/storage/{result['path']}"
    doc_entry = {"url": url, "storage_path": result["path"], "nome_file": file.filename,
                 "mime": "application/pdf", "size_kb": round(len(data) / 1024, 1),
                 "data_caricamento": _now_iso(), "caricato_da": user.get("id")}
    try:
        parsed = inps_calculator.parse_estratto_contributivo(data)
    except Exception as e:
        raise HTTPException(400, f"PDF non parsabile: {e}")
    upd: dict = {"documenti.estratto_contributivo": doc_entry, "updated_at": _now_iso()}
    if parsed.get("settimane_contributive"):
        upd["settimane_contributive"] = parsed["settimane_contributive"]
    if parsed.get("data_inizio_contribuzione"):
        upd["data_inizio_contribuzione"] = parsed["data_inizio_contribuzione"]
    if parsed.get("codice_fiscale") and not ana.get("codice_fiscale"):
        upd["codice_fiscale"] = parsed["codice_fiscale"]
    if parsed.get("nome") and not ana.get("nome"):
        upd["nome"] = parsed["nome"]
    if parsed.get("cognome") and not ana.get("cognome"):
        upd["cognome"] = parsed["cognome"]
    if parsed.get("data_nascita") and not ana.get("data_nascita"):
        upd["data_nascita"] = parsed["data_nascita"]
    await db.anagrafiche.update_one({"id": aid}, {"$set": upd})
    await log_diario_cliente(aid, "documento",
        titolo="Estratto contributivo INPS importato",
        descrizione=f"Settimane: {parsed.get('settimane_contributive')} - File: {file.filename}",
        autore=user)
    return {"ok": True, "parsed": parsed, "documento": doc_entry, "aggiornati": upd}


# ============================================================
# INTERVISTA
# ============================================================
@router.get("/anagrafiche/{aid}/interviste")
async def list_interviste(aid: str, user: dict = Depends(current_user)):
    items = await db.interviste.find({"anagrafica_id": aid}, {"_id": 0}).sort("data_intervista", -1).to_list(50)
    return items


@router.post("/anagrafiche/{aid}/interviste", status_code=201)
async def create_intervista(aid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["anagrafica_id"] = aid
    body["operatore_id"] = user["id"]
    obj = Intervista(**body)
    await db.interviste.insert_one(obj.model_dump())
    await log_attivita(user, "create", "intervista", obj.id, f"Intervista per {aid}")
    return obj.model_dump()
