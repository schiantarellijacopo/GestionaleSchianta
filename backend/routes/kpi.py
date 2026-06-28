"""KPI personalizzabili per ogni sezione del CRM.

Ogni sezione (polizze/titoli/sinistri/avvisi/prima_nota) espone:
  - KPI **predefinite** (sempre presenti, calcolate qui)
  - KPI **custom** create dall'utente in base a filtri/tag

Architettura:
  - Collection `kpi_custom`: ``{user_id, sezione, label, color, icon, ordine,
    filtro_kind, filtro_params}``
  - `GET /api/kpi/{sezione}/stats` → predefinite + custom per la sezione
  - `GET /api/kpi/custom?sezione=` → lista custom
  - `POST /api/kpi/custom` → crea
  - `PUT /api/kpi/custom/{id}` → aggiorna
  - `DELETE /api/kpi/custom/{id}` → rimuove
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter()


# ============================================================
# MODELS
# ============================================================
class KpiCustomBody(BaseModel):
    sezione: str                                # polizze | titoli | sinistri | avvisi | prima_nota
    label: str
    color: str = "sky"                          # sky | emerald | amber | violet | rose | indigo
    icon: str = "Star"
    ordine: int = 0
    filtro_kind: str = "tag"                    # tag | stato | ramo | compagnia | custom
    filtro_params: dict = Field(default_factory=dict)


# ============================================================
# CRUD KPI custom
# ============================================================
@router.get("/kpi/custom")
async def list_kpi_custom(sezione: Optional[str] = None,
                          user: dict = Depends(current_user)) -> list[dict]:
    flt: dict = {"user_id": user["id"]}
    if sezione:
        flt["sezione"] = sezione
    items = await db.kpi_custom.find(flt, {"_id": 0}).sort([
        ("sezione", 1), ("ordine", 1),
    ]).to_list(200)
    return items


@router.post("/kpi/custom", status_code=201)
async def create_kpi_custom(body: KpiCustomBody,
                             user: dict = Depends(current_user)) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        **body.model_dump(),
        "created_at": _now_iso(),
    }
    await db.kpi_custom.insert_one(doc)
    return doc


@router.put("/kpi/custom/{kid}")
async def update_kpi_custom(kid: str, body: KpiCustomBody,
                             user: dict = Depends(current_user)) -> dict:
    res = await db.kpi_custom.update_one(
        {"id": kid, "user_id": user["id"]},
        {"$set": body.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "KPI custom non trovata")
    return await db.kpi_custom.find_one({"id": kid}, {"_id": 0})


@router.delete("/kpi/custom/{kid}")
async def delete_kpi_custom(kid: str, user: dict = Depends(current_user)) -> dict:
    res = await db.kpi_custom.delete_one({"id": kid, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "KPI custom non trovata")
    return {"ok": True}


# ============================================================
# STATS PRECALCOLATE PER SEZIONE
# ============================================================
def _eur(v: float | int | None) -> float:
    return round(float(v or 0), 2)


async def _stats_polizze(scope_filter: dict) -> list[dict]:
    """KPI predefinite Polizze: Attive · In emissione · Sostituite · Annullate · Scadute · Premio totale."""
    pipeline = [
        {"$match": scope_filter},
        {"$group": {
            "_id": "$stato",
            "n": {"$sum": 1},
            "premio": {"$sum": "$premio_lordo"},
        }},
    ]
    res = {r["_id"]: r async for r in db.polizze.aggregate(pipeline)}
    total_n = sum(r["n"] for r in res.values())
    total_premio = sum(r["premio"] for r in res.values())
    attive = res.get("attiva", {"n": 0, "premio": 0})
    return [
        {"key": "attive", "label": "Attive", "value": attive["n"],
         "sub": f"€ {_eur(attive['premio']):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "emerald", "icon": "FileText"},
        {"key": "in_emissione", "label": "In emissione",
         "value": res.get("in_emissione", {}).get("n", 0),
         "color": "sky", "icon": "Clock"},
        {"key": "sostituite", "label": "Sostituite",
         "value": res.get("sostituita", {}).get("n", 0),
         "color": "indigo", "icon": "Replace"},
        {"key": "annullate", "label": "Annullate",
         "value": res.get("annullata", {}).get("n", 0),
         "color": "rose", "icon": "XCircle"},
        {"key": "scadute", "label": "Scadute",
         "value": res.get("scaduta", {}).get("n", 0),
         "color": "amber", "icon": "AlertTriangle"},
        {"key": "totale", "label": "Totale", "value": total_n,
         "sub": f"€ {_eur(total_premio):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "violet", "icon": "Layers"},
    ]


async def _stats_titoli(scope_filter: dict) -> list[dict]:
    """KPI Titoli: Da incassare · Incassati · Scaduti · Sospesi · Totale importo."""
    pipeline = [
        {"$match": scope_filter},
        {"$group": {"_id": "$stato", "n": {"$sum": 1},
                    "tot": {"$sum": "$importo_lordo"}}},
    ]
    res = {r["_id"]: r async for r in db.titoli.aggregate(pipeline)}
    total_n = sum(r["n"] for r in res.values())
    total_eur = sum(r["tot"] for r in res.values())
    return [
        {"key": "da_incassare", "label": "Da incassare",
         "value": res.get("da_incassare", {}).get("n", 0),
         "sub": f"€ {_eur(res.get('da_incassare', {}).get('tot', 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "amber", "icon": "Clock"},
        {"key": "incassati", "label": "Incassati",
         "value": res.get("incassato", {}).get("n", 0),
         "sub": f"€ {_eur(res.get('incassato', {}).get('tot', 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "emerald", "icon": "CheckCircle"},
        {"key": "scaduti", "label": "Scaduti",
         "value": res.get("scaduto", {}).get("n", 0),
         "sub": f"€ {_eur(res.get('scaduto', {}).get('tot', 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "rose", "icon": "AlertTriangle"},
        {"key": "sospesi", "label": "Sospesi",
         "value": res.get("sospeso", {}).get("n", 0),
         "color": "indigo", "icon": "Pause"},
        {"key": "totale", "label": "Totale", "value": total_n,
         "sub": f"€ {_eur(total_eur):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "violet", "icon": "Receipt"},
    ]


async def _stats_sinistri(scope_filter: dict) -> list[dict]:
    """KPI Sinistri: Aperti · Liquidati · Chiusi · Riserva totale."""
    pipeline = [
        {"$match": scope_filter},
        {"$group": {"_id": "$stato", "n": {"$sum": 1},
                    "riserva": {"$sum": "$importo_riserva"},
                    "liquidato": {"$sum": "$importo_liquidato"}}},
    ]
    res = {r["_id"]: r async for r in db.sinistri.aggregate(pipeline)}
    return [
        {"key": "aperti", "label": "Aperti",
         "value": res.get("aperto", {}).get("n", 0),
         "sub": f"Riserva € {_eur(res.get('aperto', {}).get('riserva', 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "rose", "icon": "AlertTriangle"},
        {"key": "in_istruttoria", "label": "In istruttoria",
         "value": res.get("in_istruttoria", {}).get("n", 0),
         "color": "amber", "icon": "Clock"},
        {"key": "liquidati", "label": "Liquidati",
         "value": res.get("liquidato", {}).get("n", 0),
         "sub": f"€ {_eur(res.get('liquidato', {}).get('liquidato', 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "emerald", "icon": "CheckCircle"},
        {"key": "chiusi", "label": "Chiusi",
         "value": res.get("chiuso", {}).get("n", 0),
         "color": "slate", "icon": "Archive"},
        {"key": "respinti", "label": "Respinti",
         "value": res.get("respinto", {}).get("n", 0),
         "color": "indigo", "icon": "XCircle"},
        {"key": "totale", "label": "Totale",
         "value": sum(r["n"] for r in res.values()),
         "color": "violet", "icon": "Layers"},
    ]


async def _stats_avvisi(scope_filter: dict) -> list[dict]:
    """KPI Avvisi/Sospesi: Titoli scaduti raggruppati + contraenti unici."""
    pipeline = [
        {"$match": {"stato": "scaduto", **scope_filter}},
        {"$group": {"_id": "$contraente_id", "n": {"$sum": 1},
                    "tot": {"$sum": "$importo_lordo"}}},
    ]
    contraenti = await db.titoli.aggregate(pipeline).to_list(5000)
    n_clienti = len(contraenti)
    n_titoli = sum(c["n"] for c in contraenti)
    tot_eur = sum(c["tot"] for c in contraenti)
    # KPI inviati (whatsapp/email)
    inv = await db.storico_avvisi.aggregate([
        {"$group": {"_id": "$canale", "n": {"$sum": 1}}},
    ]).to_list(10)
    inv_map = {r["_id"]: r["n"] for r in inv}
    return [
        {"key": "clienti", "label": "Clienti da contattare", "value": n_clienti,
         "color": "amber", "icon": "Users"},
        {"key": "titoli", "label": "Titoli scaduti", "value": n_titoli,
         "sub": f"€ {_eur(tot_eur):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "rose", "icon": "AlertTriangle"},
        {"key": "email_inviate", "label": "Email inviate",
         "value": inv_map.get("email", 0), "color": "sky", "icon": "Mail"},
        {"key": "wa_inviati", "label": "WhatsApp inviati",
         "value": inv_map.get("whatsapp", 0), "color": "emerald", "icon": "MessageCircle"},
        {"key": "sms_inviati", "label": "SMS inviati",
         "value": inv_map.get("sms", 0), "color": "violet", "icon": "Smartphone"},
    ]


async def _stats_prima_nota(scope_filter: dict) -> list[dict]:
    """KPI Prima Nota: entrate/uscite/saldo del mese corrente."""
    today = datetime.now()
    first_day = today.replace(day=1).strftime("%Y-%m-%d")
    pipeline = [
        {"$match": {"data": {"$gte": first_day}, **scope_filter}},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$gt": ["$importo", 0]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$lt": ["$importo", 0]}, "$importo", 0]}},
            "n": {"$sum": 1},
        }},
    ]
    r = await db.movimenti_contabili.aggregate(pipeline).to_list(1)
    r = r[0] if r else {"entrate": 0, "uscite": 0, "n": 0}
    entrate = _eur(r["entrate"])
    uscite = _eur(abs(r["uscite"]))
    return [
        {"key": "movimenti", "label": "Movimenti mese", "value": r["n"],
         "color": "sky", "icon": "Receipt"},
        {"key": "entrate", "label": "Entrate", "value": 0,
         "sub": f"€ {entrate:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "emerald", "icon": "TrendingUp"},
        {"key": "uscite", "label": "Uscite", "value": 0,
         "sub": f"€ {uscite:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "rose", "icon": "TrendingDown"},
        {"key": "saldo", "label": "Saldo mese", "value": 0,
         "sub": f"€ {(entrate - uscite):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "violet", "icon": "Wallet"},
    ]


_STATS_DISPATCH = {
    "polizze": _stats_polizze,
    "titoli": _stats_titoli,
    "sinistri": _stats_sinistri,
    "avvisi": _stats_avvisi,
    "prima_nota": _stats_prima_nota,
}


async def _resolve_custom_kpi(custom: dict) -> dict:
    """Calcola il valore di una KPI custom in base ai suoi filtri."""
    sezione = custom.get("sezione")
    fk = custom.get("filtro_kind") or "tag"
    params = custom.get("filtro_params") or {}
    collection_map = {
        "polizze": db.polizze, "titoli": db.titoli, "sinistri": db.sinistri,
        "avvisi": db.titoli, "prima_nota": db.movimenti_contabili,
    }
    coll = collection_map.get(sezione)
    if coll is None:
        return {"value": 0, "sub": None}
    flt: dict = {}
    if fk == "tag" and params.get("tag"):
        flt["tags"] = params["tag"]
    elif fk == "stato" and params.get("stato"):
        flt["stato"] = params["stato"]
    elif fk == "ramo" and params.get("ramo"):
        flt["ramo"] = params["ramo"]
    elif fk == "compagnia" and params.get("compagnia_id"):
        flt["compagnia_id"] = params["compagnia_id"]
    elif fk == "custom":
        flt = params.get("mongo_filter") or {}
    n = await coll.count_documents(flt)
    # Somma campo "importo" più sensata per sezione
    sum_field = {
        "polizze": "premio_lordo", "titoli": "importo_lordo",
        "sinistri": "importo_liquidato",
        "avvisi": "importo_lordo", "prima_nota": "importo",
    }.get(sezione)
    sub = None
    if sum_field and n:
        agg = await coll.aggregate([
            {"$match": flt}, {"$group": {"_id": None, "t": {"$sum": f"${sum_field}"}}},
        ]).to_list(1)
        if agg:
            t = _eur(agg[0]["t"])
            sub = f"€ {t:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return {"value": n, "sub": sub}


@router.get("/kpi/{sezione}/stats")
async def kpi_stats(sezione: str, user: dict = Depends(current_user)) -> dict:
    if sezione not in _STATS_DISPATCH:
        raise HTTPException(404, f"Sezione '{sezione}' non supportata")
    fn = _STATS_DISPATCH[sezione]
    # Scope: collaboratori non-admin vedono solo i propri
    scope: dict = {}
    if user["role"] not in ("admin",):
        scope["collaboratore_id"] = user["id"]
    base = await fn(scope)
    # Aggiungi custom dell'utente
    customs = await db.kpi_custom.find(
        {"user_id": user["id"], "sezione": sezione}, {"_id": 0},
    ).sort("ordine", 1).to_list(50)
    custom_out = []
    for c in customs:
        r = await _resolve_custom_kpi(c)
        custom_out.append({
            "key": f"custom_{c['id']}",
            "label": c["label"],
            "color": c.get("color", "sky"),
            "icon": c.get("icon", "Star"),
            "value": r["value"],
            "sub": r.get("sub"),
            "custom_id": c["id"],
        })
    return {"default": base, "custom": custom_out}
