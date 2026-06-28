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
    """KPI Polizze suddivise per business: Auto privati/aziende, Altri rami
    privati/aziende, Vita Investimenti/Protezione + Totali stato.

    Implementazione semplice in Python: fetch polizze + anagrafiche e
    classifica per categoria. Adeguato per dimensioni tipiche di un'agenzia.
    """
    # Mappa anagrafiche → tipo (persona_fisica / persona_giuridica)
    anag_map: dict[str, str] = {}
    async for a in db.anagrafiche.find({}, {"id": 1, "tipo": 1, "tags": 1, "_id": 0}):
        tipo = a.get("tipo") or "persona_fisica"
        tags = [t.lower() for t in (a.get("tags") or [])]
        if "azienda" in tags or "condominio" in tags:
            tipo = "persona_giuridica"
        anag_map[a.get("id")] = tipo

    def _eur_fmt(v):
        return f"€ {_eur(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    cat = {
        "auto_priv": {"n": 0, "p": 0.0},
        "auto_az": {"n": 0, "p": 0.0},
        "altri_priv": {"n": 0, "p": 0.0},
        "altri_az": {"n": 0, "p": 0.0},
        "vita_inv": {"n": 0, "p": 0.0},
        "vita_prot": {"n": 0, "p": 0.0},
    }
    state_cnt = {"attiva": {"n": 0, "p": 0.0}, "annullata": {"n": 0, "p": 0.0},
                 "scaduta": {"n": 0, "p": 0.0}}

    active_states = {"attiva", "in_emissione"}
    async for p in db.polizze.find(scope_filter, {"_id": 0}):
        stato = (p.get("stato") or "").lower()
        premio = float(p.get("premio_lordo") or 0)
        # totali per stato (su tutte le polizze nello scope)
        if stato in state_cnt:
            state_cnt[stato]["n"] += 1
            state_cnt[stato]["p"] += premio

        # categorizzazione business — solo polizze "attive"
        if stato not in active_states:
            continue
        ramo = (p.get("ramo") or "").upper()
        prodotto = (p.get("prodotto") or "").upper()
        tipo_anag = anag_map.get(p.get("contraente_id"), "persona_fisica")
        is_priv = tipo_anag == "persona_fisica"

        is_vita = "VITA" in ramo or "VITA" in prodotto
        is_auto = ("AUTO" in ramo and ("RC" in ramo or "RCA" in ramo or ramo.startswith("AUTO"))) \
                  or ramo == "RCA" or "RCAUTO" in ramo
        if is_vita:
            is_invest = "INVEST" in prodotto or "INVEST" in ramo
            key = "vita_inv" if is_invest else "vita_prot"
        elif is_auto:
            key = "auto_priv" if is_priv else "auto_az"
        else:
            key = "altri_priv" if is_priv else "altri_az"
        cat[key]["n"] += 1
        cat[key]["p"] += premio

    attive = state_cnt["attiva"]
    annullate = state_cnt["annullata"]
    scadute = state_cnt["scaduta"]

    return [
        {"key": "auto_priv", "label": "Auto privati", "value": cat["auto_priv"]["n"],
         "sub": _eur_fmt(cat["auto_priv"]["p"]), "color": "sky", "icon": "FileText",
         "link": "/polizze?preset=attive&categoria=auto_priv"},
        {"key": "auto_az", "label": "Auto aziende", "value": cat["auto_az"]["n"],
         "sub": _eur_fmt(cat["auto_az"]["p"]), "color": "indigo", "icon": "Building",
         "link": "/polizze?preset=attive&categoria=auto_az"},
        {"key": "altri_priv", "label": "Altri rami privati", "value": cat["altri_priv"]["n"],
         "sub": _eur_fmt(cat["altri_priv"]["p"]), "color": "emerald", "icon": "Shield",
         "link": "/polizze?preset=attive&categoria=altri_priv"},
        {"key": "altri_az", "label": "Altri rami aziende", "value": cat["altri_az"]["n"],
         "sub": _eur_fmt(cat["altri_az"]["p"]), "color": "amber", "icon": "Building",
         "link": "/polizze?preset=attive&categoria=altri_az"},
        {"key": "vita_inv", "label": "Vita Investimenti", "value": cat["vita_inv"]["n"],
         "sub": _eur_fmt(cat["vita_inv"]["p"]), "color": "violet", "icon": "TrendingUp",
         "link": "/polizze?preset=attive&categoria=vita_inv"},
        {"key": "vita_prot", "label": "Vita Protezione", "value": cat["vita_prot"]["n"],
         "sub": _eur_fmt(cat["vita_prot"]["p"]), "color": "rose", "icon": "Shield",
         "link": "/polizze?preset=attive&categoria=vita_prot"},
        # === Totali stato (sempre in fondo) ===
        {"key": "totale_attive", "label": "TOTALE Attive", "value": attive["n"],
         "sub": _eur_fmt(attive["p"]), "color": "emerald", "icon": "CheckCircle",
         "link": "/polizze?preset=attive"},
        {"key": "totale_annullate", "label": "TOTALE Annullate", "value": annullate["n"],
         "sub": _eur_fmt(annullate["p"]), "color": "rose", "icon": "XCircle",
         "link": "/polizze?preset=annullate"},
        {"key": "totale_scadute", "label": "TOTALE Scadute", "value": scadute["n"],
         "sub": _eur_fmt(scadute["p"]), "color": "slate", "icon": "Archive",
         "link": "/polizze?preset=scadute"},
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
         "color": "amber", "icon": "Clock",
         "link": "/titoli?preset=tutti_aperti"},
        {"key": "incassati", "label": "Incassati",
         "value": res.get("incassato", {}).get("n", 0),
         "sub": f"€ {_eur(res.get('incassato', {}).get('tot', 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "emerald", "icon": "CheckCircle",
         "link": "/titoli-storici?preset=storico_anno"},
        {"key": "scaduti", "label": "Scaduti",
         "value": res.get("scaduto", {}).get("n", 0),
         "sub": f"€ {_eur(res.get('scaduto', {}).get('tot', 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "rose", "icon": "AlertTriangle",
         "link": "/titoli?preset=scad_oltre15"},
        {"key": "sospesi", "label": "Sospesi",
         "value": res.get("sospeso", {}).get("n", 0),
         "color": "indigo", "icon": "Pause",
         "link": "/titoli?preset=sospesi"},
        {"key": "totale", "label": "Totale", "value": total_n,
         "sub": f"€ {_eur(total_eur):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "violet", "icon": "Receipt",
         "link": "/titoli?preset=tutti_aperti"},
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
         "color": "rose", "icon": "AlertTriangle", "link": "/sinistri?stato=aperto"},
        {"key": "in_istruttoria", "label": "In istruttoria",
         "value": res.get("in_istruttoria", {}).get("n", 0),
         "color": "amber", "icon": "Clock", "link": "/sinistri?stato=in_istruttoria"},
        {"key": "liquidati", "label": "Liquidati",
         "value": res.get("liquidato", {}).get("n", 0),
         "sub": f"€ {_eur(res.get('liquidato', {}).get('liquidato', 0)):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "emerald", "icon": "CheckCircle", "link": "/sinistri?stato=liquidato"},
        {"key": "chiusi", "label": "Chiusi",
         "value": res.get("chiuso", {}).get("n", 0),
         "color": "slate", "icon": "Archive", "link": "/sinistri?stato=chiuso"},
        {"key": "respinti", "label": "Respinti",
         "value": res.get("respinto", {}).get("n", 0),
         "color": "indigo", "icon": "XCircle", "link": "/sinistri?stato=respinto"},
        {"key": "totale", "label": "Totale",
         "value": sum(r["n"] for r in res.values()),
         "color": "violet", "icon": "Layers", "link": "/sinistri"},
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
         "color": "amber", "icon": "Users", "link": "/avvisi"},
        {"key": "titoli", "label": "Titoli scaduti", "value": n_titoli,
         "sub": f"€ {_eur(tot_eur):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "rose", "icon": "AlertTriangle", "link": "/avvisi"},
        {"key": "email_inviate", "label": "Email inviate",
         "value": inv_map.get("email", 0), "color": "sky", "icon": "Mail",
         "link": "/avvisi?storico=email"},
        {"key": "wa_inviati", "label": "WhatsApp inviati",
         "value": inv_map.get("whatsapp", 0), "color": "emerald", "icon": "MessageCircle",
         "link": "/avvisi?storico=whatsapp"},
        {"key": "sms_inviati", "label": "SMS inviati",
         "value": inv_map.get("sms", 0), "color": "violet", "icon": "Smartphone",
         "link": "/avvisi?storico=sms"},
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
         "color": "sky", "icon": "Receipt", "link": "/contabilita"},
        {"key": "entrate", "label": "Entrate", "value": 0,
         "sub": f"€ {entrate:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "emerald", "icon": "TrendingUp", "link": "/contabilita?tipo=entrata"},
        {"key": "uscite", "label": "Uscite", "value": 0,
         "sub": f"€ {uscite:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "rose", "icon": "TrendingDown", "link": "/contabilita?tipo=uscita"},
        {"key": "saldo", "label": "Saldo mese", "value": 0,
         "sub": f"€ {(entrate - uscite):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
         "color": "violet", "icon": "Wallet", "link": "/contabilita"},
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
        return {"value": 0, "sub": None, "link": None}
    flt: dict = {}
    link_params: list[tuple[str, str]] = []
    if fk == "tag" and params.get("tag"):
        flt["tags"] = params["tag"]
        link_params.append(("tag", params["tag"]))
    elif fk == "stato" and params.get("stato"):
        flt["stato"] = params["stato"]
        link_params.append(("stato", params["stato"]))
    elif fk == "ramo" and params.get("ramo"):
        flt["ramo"] = params["ramo"]
        link_params.append(("ramo", params["ramo"]))
    elif fk == "compagnia" and params.get("compagnia_id"):
        flt["compagnia_id"] = params["compagnia_id"]
        link_params.append(("compagnia_id", params["compagnia_id"]))
    elif fk == "prodotto" and params.get("prodotto"):
        flt["prodotto"] = params["prodotto"]
        link_params.append(("prodotto", params["prodotto"]))
    elif fk == "mezzo_pagamento" and params.get("mezzo_pagamento"):
        flt["mezzo_pagamento"] = params["mezzo_pagamento"]
        link_params.append(("mezzo_pagamento", params["mezzo_pagamento"]))
    elif fk == "conto_cassa" and params.get("conto_cassa_id"):
        flt["conto_cassa_id"] = params["conto_cassa_id"]
        link_params.append(("conto_cassa_id", params["conto_cassa_id"]))
    elif fk == "custom":
        flt = params.get("mongo_filter") or {}
    n = await coll.count_documents(flt)
    # Somma campo "importo" più sensata per sezione
    sum_field = {
        "polizze": "premio_lordo", "titoli": "importo_lordo",
        "sinistri": "importo_liquidato",
        "avvisi": "importo_lordo", "prima_nota": "importo",
    }.get(sezione)

@router.get("/kpi/options")
async def kpi_filter_options(
    sezione: str,
    kind: str,
    user: dict = Depends(current_user),
) -> list[dict]:
    """Opzioni a tendina per il campo "Valore filtro" del dialog KPI custom.

    Restituisce ``[{value, label}]`` in base a ``kind``:
      - tag → tutti i tag distinti delle anagrafiche
      - stato → stati validi per la sezione
      - ramo → codici/nomi rami dalla libreria
      - compagnia → compagnie attive
      - prodotto → prodotti distinti
      - mezzo_pagamento → mezzi pagamento attivi
      - conto_cassa → conti/banche
    """
    out: list[dict] = []
    if kind == "tag":
        tags = await db.anagrafiche.distinct("tags")
        out = [{"value": t, "label": t} for t in sorted(t for t in tags if t)]
    elif kind == "stato":
        stati_map = {
            "polizze": ["attiva", "in_emissione", "annullata", "scaduta", "sospesa"],
            "titoli": ["da_incassare", "incassato", "scaduto", "stornato", "sospeso"],
            "sinistri": ["aperto", "in_istruttoria", "liquidato", "chiuso", "respinto"],
            "avvisi": ["scaduto", "sospeso"],
            "prima_nota": [],
        }
        out = [{"value": s, "label": s.replace("_", " ").capitalize()}
               for s in stati_map.get(sezione, [])]
    elif kind == "ramo":
        async for r in db.rami.find({}, {"_id": 0, "codice": 1, "nome": 1}).sort("nome", 1):
            out.append({"value": r.get("codice") or r.get("nome"),
                        "label": r.get("nome") or r.get("codice")})
    elif kind == "compagnia":
        async for c in db.compagnie.find({}, {"_id": 0, "id": 1, "ragione_sociale": 1}).sort("ragione_sociale", 1):
            out.append({"value": c["id"], "label": c.get("ragione_sociale") or c["id"]})
    elif kind == "prodotto":
        async for p in db.prodotti.find({}, {"_id": 0, "nome": 1}).sort("nome", 1):
            if p.get("nome"):
                out.append({"value": p["nome"], "label": p["nome"]})
    elif kind == "mezzo_pagamento":
        async for m in db.mezzi_pagamento.find({"attivo": {"$ne": False}}, {"_id": 0}).sort("ordine", 1):
            out.append({"value": m.get("codice"), "label": m.get("label") or m.get("codice")})
    elif kind == "conto_cassa":
        async for c in db.conti_cassa.find({}, {"_id": 0, "id": 1, "nome": 1}).sort("nome", 1):
            out.append({"value": c["id"], "label": c.get("nome") or c["id"]})
    return out


    sub = None
    if sum_field and n:
        agg = await coll.aggregate([
            {"$match": flt}, {"$group": {"_id": None, "t": {"$sum": f"${sum_field}"}}},
        ]).to_list(1)
        if agg:
            t = _eur(agg[0]["t"])
            sub = f"€ {t:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    # costruisci link verso la pagina sezione con i filtri applicati
    sezione_route = {
        "polizze": "/polizze", "titoli": "/titoli", "sinistri": "/sinistri",
        "avvisi": "/avvisi", "prima_nota": "/contabilita",
    }.get(sezione, "/")
    qs = "&".join(f"{k}={v}" for k, v in link_params)
    link = f"{sezione_route}?{qs}" if qs else sezione_route
    return {"value": n, "sub": sub, "link": link}


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
            "link": r.get("link"),
            "custom_id": c["id"],
        })
    return {"default": base, "custom": custom_out}
