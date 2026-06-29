"""Commerciale — Trattative, Ritenute (collaboratori) e Ritenute Compagnia.

Tre moduli distinti tutti in negativo/avere sul piano contabile:

- **Trattative**: proposte commerciali / disdette in corso, pipeline pre-polizza.
- **Ritenute collaboratore**: ritenuta d'acconto F24 dei collaboratori. CRUD + totali.
- **Ritenute compagnia**: trattenute che la compagnia applica sulle nostre
  provvigioni (es. ritenuta su provv. vita). Funziona ESATTAMENTE come Rappel,
  ma in negativo nelle provvigioni: aumenta il saldo da versare alla compagnia.
  Si registra in estratto conto + prima nota. Solo per compagnie con
  mandato diretto.
- **Fatture agenzia partner**: per compagnie a mandato di collaborazione,
  quando l'agenzia partner ci paga le nostre provvigioni si registra una
  fattura/partita che riduce il saldo verso la compagnia/partner.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter()


# ===========================================================
#  TRATTATIVE
# ===========================================================
class TrattativaBody(BaseModel):
    anagrafica_id: str
    titolo: str
    descrizione: Optional[str] = None
    ramo: Optional[str] = None
    compagnia_di_provenienza: Optional[str] = None
    compagnia_target_id: Optional[str] = None
    data_scadenza_corrente: Optional[str] = None
    premio_corrente: float = 0
    premio_proposto: float = 0
    stato: str = "aperta"  # aperta | proposta_inviata | in_attesa | vinta | persa
    note: Optional[str] = None
    visibili_cliente: bool = False


async def _enrich_trattativa(t: dict) -> dict:
    if t.get("anagrafica_id"):
        a = await db.anagrafiche.find_one(
            {"id": t["anagrafica_id"]},
            {"_id": 0, "ragione_sociale": 1, "cognome": 1, "nome": 1},
        ) or {}
        t["anagrafica_nome"] = a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip()
    if t.get("compagnia_target_id"):
        c = await db.compagnie.find_one(
            {"id": t["compagnia_target_id"]}, {"_id": 0, "ragione_sociale": 1},
        ) or {}
        t["compagnia_target_nome"] = c.get("ragione_sociale")
    return t


@router.get("/trattative")
async def list_trattative(
    stato: Optional[str] = None,
    anagrafica_id: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if stato: flt["stato"] = stato
    if anagrafica_id: flt["anagrafica_id"] = anagrafica_id
    # visibility: collaboratore vede solo i propri
    if user.get("role") == "collaboratore":
        flt["collaboratore_id"] = user.get("id")
    items = await db.trattative.find(flt, {"_id": 0}).sort("created_at", -1).to_list(2000)
    for t in items:
        await _enrich_trattativa(t)
    return items


@router.get("/trattative/{tid}")
async def get_trattativa(tid: str, user=Depends(current_user)) -> dict:
    t = await db.trattative.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Trattativa non trovata")
    return await _enrich_trattativa(t)


@router.post("/trattative", status_code=201)
async def create_trattativa(
    body: TrattativaBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    if not body.anagrafica_id or not body.titolo.strip():
        raise HTTPException(400, "Cliente e titolo obbligatori")
    if not await db.anagrafiche.find_one({"id": body.anagrafica_id}, {"_id": 1}):
        raise HTTPException(400, "Anagrafica non trovata")
    doc = {
        "id": str(uuid.uuid4()),
        **body.model_dump(),
        "collaboratore_id": user.get("id"),
        "created_at": _now_iso(),
    }
    await db.trattative.insert_one(doc); doc.pop("_id", None)
    fresh = await db.trattative.find_one({"id": doc["id"]}, {"_id": 0}) or doc
    return await _enrich_trattativa(fresh)


@router.put("/trattative/{tid}")
async def update_trattativa(
    tid: str, body: TrattativaBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    data = body.model_dump()
    data["updated_at"] = _now_iso()
    res = await db.trattative.update_one({"id": tid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Trattativa non trovata")
    doc = await db.trattative.find_one({"id": tid}, {"_id": 0})
    return await _enrich_trattativa(doc)


@router.delete("/trattative/{tid}")
async def delete_trattativa(
    tid: str, user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    res = await db.trattative.delete_one({"id": tid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Trattativa non trovata")
    return {"ok": True}


# ===========================================================
#  RITENUTE COLLABORATORE
# ===========================================================
class RitenutaBody(BaseModel):
    anno: int
    collaboratore_id: str
    descrizione: Optional[str] = None
    imponibile: float = 0
    aliquota: float = 20
    importo_ritenuta: float = 0
    causale: str = "1040"
    data: Optional[str] = None  # YYYY-MM-DD
    versata: bool = False
    data_versamento: Optional[str] = None
    note: Optional[str] = None


async def _enrich_ritenuta(r: dict) -> dict:
    if r.get("collaboratore_id"):
        u = await db.users.find_one(
            {"id": r["collaboratore_id"]},
            {"_id": 0, "name": 1, "email": 1},
        ) or {}
        r["collaboratore_nome"] = u.get("name") or u.get("email")
    return r


@router.get("/ritenute")
async def list_ritenute(
    anno: Optional[int] = None,
    collaboratore_id: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore")),
) -> list[dict]:
    flt: dict = {}
    if anno: flt["anno"] = anno
    if collaboratore_id: flt["collaboratore_id"] = collaboratore_id
    items = await db.ritenute.find(flt, {"_id": 0}).sort([("anno", -1), ("data", -1)]).to_list(5000)
    for r in items:
        await _enrich_ritenuta(r)
    return items


@router.get("/ritenute/totali")
async def totali_ritenute(
    anno: Optional[int] = None,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    match: dict = {}
    if anno: match["anno"] = anno
    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {
            "_id": "$collaboratore_id",
            "n_record": {"$sum": 1},
            "imponibile_tot": {"$sum": {"$ifNull": ["$imponibile", 0]}},
            "ritenuta_tot": {"$sum": {"$ifNull": ["$importo_ritenuta", 0]}},
            "versata_tot": {"$sum": {"$cond": [{"$eq": ["$versata", True]},
                                                  {"$ifNull": ["$importo_ritenuta", 0]}, 0]}},
        }},
    ]
    rows = await db.ritenute.aggregate(pipeline).to_list(500)
    # enrich nome collab
    ids = [r["_id"] for r in rows if r["_id"]]
    users_map: dict = {}
    if ids:
        async for u in db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}):
            users_map[u["id"]] = u.get("name") or u.get("email")
    out_rows = [{
        "collaboratore_id": r["_id"],
        "collaboratore_nome": users_map.get(r["_id"]),
        "n_record": r["n_record"],
        "imponibile_tot": round(r["imponibile_tot"], 2),
        "ritenuta_tot": round(r["ritenuta_tot"], 2),
        "versata_tot": round(r["versata_tot"], 2),
    } for r in rows]
    out_rows.sort(key=lambda x: x["ritenuta_tot"], reverse=True)
    return {"anno": anno, "per_collaboratore": out_rows}


@router.post("/ritenute", status_code=201)
async def create_ritenuta(
    body: RitenutaBody,
    user=Depends(require_user("admin")),
) -> dict:
    if not body.collaboratore_id:
        raise HTTPException(400, "Collaboratore obbligatorio")
    # Auto-calc importo se non fornito
    if not body.importo_ritenuta and body.imponibile and body.aliquota:
        body.importo_ritenuta = round(body.imponibile * body.aliquota / 100.0, 2)
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": _now_iso()}
    await db.ritenute.insert_one(doc); doc.pop("_id", None)
    fresh = await db.ritenute.find_one({"id": doc["id"]}, {"_id": 0})
    return await _enrich_ritenuta(fresh)


@router.put("/ritenute/{rid}")
async def update_ritenuta(
    rid: str, body: RitenutaBody,
    user=Depends(require_user("admin")),
) -> dict:
    data = body.model_dump()
    if not data.get("importo_ritenuta") and data.get("imponibile") and data.get("aliquota"):
        data["importo_ritenuta"] = round(data["imponibile"] * data["aliquota"] / 100.0, 2)
    data["updated_at"] = _now_iso()
    res = await db.ritenute.update_one({"id": rid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Ritenuta non trovata")
    doc = await db.ritenute.find_one({"id": rid}, {"_id": 0})
    return await _enrich_ritenuta(doc)


@router.delete("/ritenute/{rid}")
async def delete_ritenuta(
    rid: str, user=Depends(require_user("admin")),
) -> dict:
    res = await db.ritenute.delete_one({"id": rid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Ritenuta non trovata")
    return {"ok": True}


# ===========================================================
#  RITENUTE COMPAGNIA (gemella negativa del Rappel)
# ===========================================================
class RitenutaCompagniaBody(BaseModel):
    compagnia_id: str
    data: str  # YYYY-MM-DD
    importo: float  # sempre positivo: viene salvato come "negativo" sulle provvigioni
    descrizione: Optional[str] = None
    note: Optional[str] = None
    anno: Optional[int] = None


@router.get("/ritenute-compagnia")
async def list_ritenute_compagnia(
    compagnia_id: Optional[str] = None,
    anno: Optional[int] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if compagnia_id: flt["compagnia_id"] = compagnia_id
    if anno: flt["anno"] = anno
    items = await db.ritenute_compagnia.find(flt, {"_id": 0}).sort("data", -1).to_list(5000)
    comp_ids = list({r["compagnia_id"] for r in items if r.get("compagnia_id")})
    comps: dict = {}
    if comp_ids:
        async for c in db.compagnie.find(
            {"id": {"$in": comp_ids}},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1},
        ):
            comps[c["id"]] = c
    for r in items:
        c = comps.get(r.get("compagnia_id"), {})
        r["compagnia_nome"] = c.get("ragione_sociale")
        r["compagnia_codice"] = c.get("codice")
    return items


@router.post("/ritenute-compagnia", status_code=201)
async def create_ritenuta_compagnia(
    body: RitenutaCompagniaBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    comp = await db.compagnie.find_one({"id": body.compagnia_id}, {"_id": 0})
    if not comp:
        raise HTTPException(404, "Compagnia non trovata")
    if comp.get("tipo_mandato") and comp.get("tipo_mandato") != "diretto":
        raise HTTPException(
            400,
            "Le ritenute compagnia si applicano solo a compagnie con mandato diretto",
        )
    if body.importo <= 0:
        raise HTTPException(400, "Importo deve essere positivo (verrà trattenuto come negativo)")
    anno = body.anno or int(body.data[:4])
    doc = {
        "id": str(uuid.uuid4()),
        "compagnia_id": body.compagnia_id,
        "data": body.data,
        "anno": anno,
        "importo": round(body.importo, 2),
        "descrizione": body.descrizione,
        "note": body.note,
        "stato": "da_versare",  # da_versare → versata
        "created_at": _now_iso(),
        "created_by": user.get("id"),
    }
    await db.ritenute_compagnia.insert_one(doc); doc.pop("_id", None)
    return doc


@router.put("/ritenute-compagnia/{rid}")
async def update_ritenuta_compagnia(
    rid: str, body: RitenutaCompagniaBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    cur = await db.ritenute_compagnia.find_one({"id": rid}, {"_id": 0})
    if not cur:
        raise HTTPException(404, "Ritenuta non trovata")
    if cur.get("stato") == "versata":
        raise HTTPException(400, "Ritenuta già versata: stornare prima di modificare")
    data = body.model_dump()
    data["anno"] = body.anno or int(body.data[:4])
    data["updated_at"] = _now_iso()
    await db.ritenute_compagnia.update_one({"id": rid}, {"$set": data})
    return await db.ritenute_compagnia.find_one({"id": rid}, {"_id": 0})


@router.delete("/ritenute-compagnia/{rid}")
async def delete_ritenuta_compagnia(
    rid: str, user=Depends(require_user("admin")),
) -> dict:
    cur = await db.ritenute_compagnia.find_one({"id": rid}, {"_id": 0})
    if not cur:
        raise HTTPException(404, "Ritenuta non trovata")
    # se versata, rimuovo anche il movimento collegato in prima nota
    if cur.get("movimento_id"):
        await db.movimenti.delete_one({"id": cur["movimento_id"]})
    await db.ritenute_compagnia.delete_one({"id": rid})
    return {"ok": True}


@router.post("/ritenute-compagnia/{rid}/versa")
async def versa_ritenuta_compagnia(
    rid: str,
    body: dict | None = None,
    user=Depends(require_user("admin")),
) -> dict:
    """Versamento della ritenuta compagnia: crea un movimento USCITA in
    Prima Nota e marca lo stato come 'versata'."""
    r = await db.ritenute_compagnia.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Ritenuta non trovata")
    if r.get("stato") == "versata":
        return r
    body = body or {}
    data_vers = body.get("data_versamento") or _now_iso()[:10]
    comp = await db.compagnie.find_one({"id": r["compagnia_id"]}, {"_id": 0, "ragione_sociale": 1})
    mov_id = str(uuid.uuid4())
    await db.movimenti.insert_one({
        "id": mov_id,
        "tipo": "uscita",
        "categoria": "ritenuta_compagnia",
        "data_movimento": data_vers,
        "importo": round(float(r["importo"]), 2),
        "descrizione": f"Ritenuta {comp.get('ragione_sociale','')}: {r.get('descrizione') or ''}".strip(),
        "compagnia_id": r["compagnia_id"],
        "ritenuta_compagnia_id": rid,
        "created_at": _now_iso(),
        "created_by": user.get("id"),
    })
    await db.ritenute_compagnia.update_one({"id": rid}, {"$set": {
        "stato": "versata",
        "data_versamento": data_vers,
        "movimento_id": mov_id,
    }})
    fresh = await db.ritenute_compagnia.find_one({"id": rid}, {"_id": 0})
    return fresh


@router.post("/ritenute-compagnia/{rid}/storna")
async def storna_ritenuta_compagnia(
    rid: str,
    user=Depends(require_user("admin")),
) -> dict:
    r = await db.ritenute_compagnia.find_one({"id": rid}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Ritenuta non trovata")
    if r.get("movimento_id"):
        await db.movimenti.delete_one({"id": r["movimento_id"]})
    await db.ritenute_compagnia.update_one({"id": rid}, {"$set": {
        "stato": "da_versare",
        "movimento_id": None,
        "data_versamento": None,
    }})
    return await db.ritenute_compagnia.find_one({"id": rid}, {"_id": 0})


# ===========================================================
#  FATTURE AGENZIA PARTNER (mandato di collaborazione)
# ===========================================================
class FatturaAgenziaPartnerBody(BaseModel):
    agenzia_partner_id: str  # agenzia partner (es. Bottoni) → ref db.agenzie
    compagnie_ids: list[str]  # 1+ compagnie a mandato collaborazione coperte dalla fattura
    data: str
    importo: float  # provvigioni lorde fatturate dall'agenzia partner
    perc_ritenuta: float = 0  # default = quello dell'agenzia (auto)
    importo_ritenuta: float = 0
    importo_netto: float = 0  # importo - ritenuta
    descrizione: Optional[str] = None
    numero_fattura: Optional[str] = None
    note: Optional[str] = None
    # legacy
    compagnia_id: Optional[str] = None


@router.get("/fatture-agenzia-partner")
async def list_fatture_partner(
    compagnia_id: Optional[str] = None,
    agenzia_partner_id: Optional[str] = None,
    stato: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if compagnia_id: flt["compagnia_id"] = compagnia_id
    if agenzia_partner_id: flt["agenzia_partner_id"] = agenzia_partner_id
    if stato: flt["stato"] = stato
    items = await db.fatture_agenzia_partner.find(flt, {"_id": 0}).sort("data", -1).to_list(2000)
    comp_ids = [r.get("compagnia_id") for r in items if r.get("compagnia_id")]
    age_ids = [r.get("agenzia_partner_id") for r in items if r.get("agenzia_partner_id")]
    cmap: dict = {}
    if comp_ids:
        async for c in db.compagnie.find({"id": {"$in": comp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1}):
            cmap[c["id"]] = c["ragione_sociale"]
    amap: dict = {}
    if age_ids:
        async for a in db.agenzie.find({"id": {"$in": age_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1}):
            amap[a["id"]] = a["ragione_sociale"]
    for r in items:
        r["compagnia_nome"] = cmap.get(r.get("compagnia_id"))
        r["agenzia_partner_nome"] = amap.get(r.get("agenzia_partner_id"))
    return items


@router.post("/fatture-agenzia-partner", status_code=201)
async def create_fattura_partner(
    body: FatturaAgenziaPartnerBody,
    user=Depends(require_user("admin", "collaboratore")),
) -> dict:
    if not body.agenzia_partner_id:
        raise HTTPException(400, "Agenzia partner obbligatoria")
    age = await db.agenzie.find_one({"id": body.agenzia_partner_id}, {"_id": 0})
    if not age:
        raise HTTPException(404, "Agenzia partner non trovata")
    # Lista compagnie (multi). Accetta anche compagnia_id legacy.
    comp_ids = list(body.compagnie_ids) if body.compagnie_ids else []
    if not comp_ids and body.compagnia_id:
        comp_ids = [body.compagnia_id]
    if not comp_ids:
        raise HTTPException(400, "Seleziona almeno una compagnia")
    # Verifica che le compagnie siano tutte a mandato collaborazione
    async for c in db.compagnie.find({"id": {"$in": comp_ids}}, {"_id": 0, "id": 1, "tipo_mandato": 1, "ragione_sociale": 1}):
        if c.get("tipo_mandato") != "collaborazione":
            raise HTTPException(
                400,
                f"La compagnia {c.get('ragione_sociale')} non è a mandato di collaborazione",
            )
    # Auto-compila ritenuta dal profilo agenzia se non fornita
    perc_rit = body.perc_ritenuta if body.perc_ritenuta else float(age.get("perc_ritenuta_acconto") or 0)
    importo = round(float(body.importo), 2)
    if importo <= 0:
        raise HTTPException(400, "Importo deve essere positivo")
    importo_ritenuta = round(importo * perc_rit / 100.0, 2) if perc_rit > 0 else round(float(body.importo_ritenuta or 0), 2)
    importo_netto = round(importo - importo_ritenuta, 2)
    doc = {
        "id": str(uuid.uuid4()),
        "agenzia_partner_id": body.agenzia_partner_id,
        "compagnie_ids": comp_ids,
        "compagnia_id": comp_ids[0],  # legacy/compat per gli aggregati
        "data": body.data,
        "importo": importo,
        "perc_ritenuta": perc_rit,
        "importo_ritenuta": importo_ritenuta,
        "importo_netto": importo_netto,
        "descrizione": body.descrizione,
        "numero_fattura": body.numero_fattura,
        "note": body.note,
        "stato": "da_pagare",
        "created_at": _now_iso(),
        "created_by": user.get("id"),
    }
    await db.fatture_agenzia_partner.insert_one(doc); doc.pop("_id", None)
    return doc


@router.post("/fatture-agenzia-partner/{fid}/registra-pagamento")
async def registra_pagamento_fattura(
    fid: str,
    body: dict,
    user=Depends(require_user("admin")),
) -> dict:
    """Registra la fattura come pagata e crea un movimento ENTRATA in
    Prima Nota (le provvigioni che riceviamo dall'agenzia partner)."""
    f = await db.fatture_agenzia_partner.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Fattura non trovata")
    if f.get("stato") == "pagata":
        return f
    data_pag = body.get("data_pagamento") or _now_iso()[:10]
    importo = float(body.get("importo") or f.get("importo_netto") or f["importo"])
    mov_id = str(uuid.uuid4())
    await db.movimenti.insert_one({
        "id": mov_id,
        "tipo": "entrata",
        "categoria": "provvigione_da_partner",
        "data_movimento": data_pag,
        "importo": round(importo, 2),
        "descrizione": f"Fattura provvigioni partner (n. {f.get('numero_fattura') or '—'})",
        "compagnia_id": f.get("compagnia_id"),
        "compagnie_ids": f.get("compagnie_ids") or [f.get("compagnia_id")],
        "agenzia_partner_id": f["agenzia_partner_id"],
        "fattura_partner_id": fid,
        "created_at": _now_iso(),
        "created_by": user.get("id"),
    })
    await db.fatture_agenzia_partner.update_one({"id": fid}, {"$set": {
        "stato": "pagata",
        "data_pagamento": data_pag,
        "importo_pagato": round(importo, 2),
        "movimento_id": mov_id,
    }})
    return await db.fatture_agenzia_partner.find_one({"id": fid}, {"_id": 0})


@router.delete("/fatture-agenzia-partner/{fid}")
async def delete_fattura_partner(
    fid: str, user=Depends(require_user("admin")),
) -> dict:
    f = await db.fatture_agenzia_partner.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Fattura non trovata")
    if f.get("movimento_id"):
        await db.movimenti.delete_one({"id": f["movimento_id"]})
    await db.fatture_agenzia_partner.delete_one({"id": fid})
    return {"ok": True}


# ===========================================================
#  PARTITE APERTE (auto-generate da estratto conto)
# ===========================================================
@router.get("/partite-agenzia-partner")
async def partite_aperte(
    compagnia_id: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    """Per compagnie a mandato di collaborazione: calcola dinamicamente
    le provvigioni maturate (cumulate da titoli incassati) ancora non
    fatturate dall'agenzia partner. Ritorna l'elenco delle "partite
    aperte" che l'utente può selezionare per registrare la fattura."""
    flt_c = {"tipo_mandato": "collaborazione"}
    if compagnia_id:
        flt_c["id"] = compagnia_id
    out: list[dict] = []
    async for c in db.compagnie.find(flt_c, {"_id": 0}):
        # totale provvigioni maturate (titoli incassati di polizze della compagnia)
        pol_ids = [p["id"] async for p in db.polizze.find(
            {"compagnia_id": c["id"]}, {"_id": 0, "id": 1},
        )]
        if not pol_ids:
            continue
        prov_agg = await db.titoli.aggregate([
            {"$match": {"polizza_id": {"$in": pol_ids}, "stato": "incassato"}},
            {"$group": {"_id": None, "tot": {"$sum": {"$ifNull": ["$provvigioni", 0]}}}},
        ]).to_list(1)
        provv_maturate = round(prov_agg[0]["tot"], 2) if prov_agg else 0.0
        # fatture già registrate
        fat_agg = await db.fatture_agenzia_partner.aggregate([
            {"$match": {"compagnia_id": c["id"]}},
            {"$group": {"_id": None, "tot": {"$sum": {"$ifNull": ["$importo", 0]}},
                         "tot_pagate": {"$sum": {"$cond": [{"$eq": ["$stato", "pagata"]},
                                                            {"$ifNull": ["$importo", 0]}, 0]}}}},
        ]).to_list(1)
        tot_fatt = round(fat_agg[0]["tot"], 2) if fat_agg else 0.0
        tot_pagate = round(fat_agg[0]["tot_pagate"], 2) if fat_agg else 0.0
        partita_aperta = round(provv_maturate - tot_fatt, 2)
        out.append({
            "compagnia_id": c["id"],
            "compagnia_nome": c["ragione_sociale"],
            "agenzia_partner_id": c.get("agenzia_partner_id"),
            "provvigioni_maturate": provv_maturate,
            "totale_fatturato": tot_fatt,
            "totale_pagato": tot_pagate,
            "partita_aperta": partita_aperta,
        })
    return out
