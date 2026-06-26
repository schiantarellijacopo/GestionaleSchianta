"""Librerie routes — endpoint CRUD per le tabelle di lookup.

Estratto da server.py (~570 righe). Tutti gli endpoint sono prefissati
`/api/librerie` (oltre a quelli `/api/...` non-librerie del modulo come
banche / mapping-garanzie / mapping-operatori / azienda — che restano
sotto il prefisso /librerie nei loro path completi).
"""
from __future__ import annotations
import os
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from database import db
from db_models import (
    _now_iso, _uid,
    AziendaConfig, Banca, ContattoCompagnia, ContoCassa, MezzoPagamento,
    ProdottoLibreria, RamoLibreria, SchemaProvvigionale, default_mora_for_ramo,
)
from auth import current_user, require_user
from shared import log_attivita, strip_mongo_id
import storage as obj_storage

router = APIRouter()


def _libreria_routes(coll_name: str, model_cls, ruoli_modifica=("admin", "collaboratore")) -> dict:
    """Crea endpoint CRUD standard per una collezione di libreria."""
    pass  # implementato direttamente sotto per ogni risorsa


# --- BANCHE ---
@router.get("/librerie/banche")
async def list_banche(user=Depends(current_user)) -> list[dict]:
    return await db.banche.find({}, {"_id": 0}).sort("nome", 1).to_list(500)


@router.post("/librerie/banche", status_code=201)
async def create_banca(body: dict, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    obj = Banca(**body)
    await db.banche.insert_one(obj.model_dump())
    await log_attivita(user, "create", "banca", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/banche/{bid}")
async def update_banca(bid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    body["updated_at"] = _now_iso()
    res = await db.banche.update_one({"id": bid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Banca non trovata")
    await log_attivita(user, "update", "banca", bid)
    return strip_mongo_id(await db.banche.find_one({"id": bid}, {"_id": 0}))


@router.delete("/librerie/banche/{bid}")
async def delete_banca(bid: str, user=Depends(require_user("admin"))) -> dict:
    await db.banche.delete_one({"id": bid})
    await log_attivita(user, "delete", "banca", bid)
    return {"ok": True}


# --- CONTI CASSA ---
@router.get("/librerie/conti-cassa")
async def list_conti(attivi: Optional[bool] = None, user=Depends(current_user)) -> list[dict]:
    flt = {}
    if attivi is not None:
        flt["attivo"] = attivi
    return await db.conti_cassa.find(flt, {"_id": 0}).sort("ordine", 1).to_list(500)


# --- MAPPING GARANZIE ANIA → nome personalizzato ---
@router.get("/librerie/mapping-garanzie")
async def list_mapping_garanzie(user=Depends(current_user)) -> list[dict]:
    return await db.mapping_garanzie.find({}, {"_id": 0}).sort("codice_ania", 1).to_list(2000)


@router.post("/librerie/mapping-garanzie", status_code=201)
async def create_mapping_garanzia(body: dict, user=Depends(require_user("admin"))) -> dict:
    if not body.get("codice_ania"):
        raise HTTPException(400, "Codice ANIA obbligatorio")
    body["id"] = body.get("id") or _uid()
    body["created_at"] = _now_iso()
    body["updated_at"] = _now_iso()
    body["is_deleted"] = False
    await db.mapping_garanzie.insert_one(body)
    return strip_mongo_id(body)


@router.put("/librerie/mapping-garanzie/{mid}")
async def update_mapping_garanzia(mid: str, body: dict, user=Depends(require_user("admin"))) -> dict:
    body["updated_at"] = _now_iso()
    r = await db.mapping_garanzie.update_one({"id": mid}, {"$set": body})
    if r.matched_count == 0:
        raise HTTPException(404, "Mapping non trovato")
    return strip_mongo_id(await db.mapping_garanzie.find_one({"id": mid}, {"_id": 0}))


@router.delete("/librerie/mapping-garanzie/{mid}")
async def delete_mapping_garanzia(mid: str, user=Depends(require_user("admin"))) -> dict:
    await db.mapping_garanzie.delete_one({"id": mid})
    return {"ok": True}


# --- MAPPING OPERATORI ANIA → user_id applicativo ---
@router.get("/librerie/mapping-operatori")
async def list_mapping_operatori(user=Depends(current_user)) -> list[dict]:
    items = await db.mapping_operatori.find({}, {"_id": 0}).sort("codice_ania", 1).to_list(2000)
    # arricchimento user
    uids = [i["user_id"] for i in items if i.get("user_id")]
    users = {u["id"]: u async for u in db.users.find(
        {"id": {"$in": uids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
    )}
    for i in items:
        if i.get("user_id"):
            i["user"] = users.get(i["user_id"])
    return items


@router.post("/librerie/mapping-operatori", status_code=201)
async def create_mapping_operatore(body: dict, user=Depends(require_user("admin"))) -> dict:
    if not body.get("codice_ania"):
        raise HTTPException(400, "Codice operatore obbligatorio")
    body["id"] = body.get("id") or _uid()
    body["created_at"] = _now_iso()
    body["updated_at"] = _now_iso()
    body["is_deleted"] = False
    await db.mapping_operatori.insert_one(body)
    return strip_mongo_id(body)


@router.put("/librerie/mapping-operatori/{mid}")
async def update_mapping_operatore(mid: str, body: dict, user=Depends(require_user("admin"))) -> dict:
    body["updated_at"] = _now_iso()
    r = await db.mapping_operatori.update_one({"id": mid}, {"$set": body})
    if r.matched_count == 0:
        raise HTTPException(404, "Mapping non trovato")
    return strip_mongo_id(await db.mapping_operatori.find_one({"id": mid}, {"_id": 0}))


@router.delete("/librerie/mapping-operatori/{mid}")
async def delete_mapping_operatore(mid: str, user=Depends(require_user("admin"))) -> dict:
    await db.mapping_operatori.delete_one({"id": mid})
    return {"ok": True}


@router.post("/librerie/mapping-operatori/applica-a-polizze")
async def applica_mapping_operatori(user=Depends(require_user("admin"))) -> dict:
    """Riapplica il mapping operatori a TUTTE le polizze esistenti (utile dopo aver mappato gli operatori)."""
    aggiornate = 0
    async for m in db.mapping_operatori.find({"user_id": {"$ne": None}}, {"_id": 0}):
        if not m.get("user_id"):
            continue
        r = await db.polizze.update_many(
            {"operatore_ania_codice": m["codice_ania"]},
            {"$set": {"collaboratore_id": m["user_id"], "updated_at": _now_iso()}},
        )
        aggiornate += r.modified_count
    return {"polizze_aggiornate": aggiornate}


@router.post("/librerie/mapping-garanzie/applica-a-polizze")
async def applica_mapping_garanzie(user=Depends(require_user("admin"))) -> dict:
    """Riapplica il mapping garanzie alle polizze esistenti (rinomina garanzia.garanzia con nome_personalizzato)."""
    aggiornate = 0
    map_dict = {}
    async for m in db.mapping_garanzie.find({}, {"_id": 0}):
        if not m.get("nome_personalizzato"):
            continue
        k = (m.get("codice_ania") or "").strip().upper()
        if k:
            map_dict[k] = m["nome_personalizzato"]
    async for p in db.polizze.find({"garanzie": {"$exists": True, "$ne": []}}, {"_id": 0, "id": 1, "garanzie": 1}):
        changed = False
        for g in p.get("garanzie") or []:
            codice = (g.get("codice_ania") or "").strip().upper()
            if codice and codice in map_dict and g.get("garanzia") != map_dict[codice]:
                g["garanzia"] = map_dict[codice]
                changed = True
        if changed:
            await db.polizze.update_one({"id": p["id"]}, {"$set": {"garanzie": p["garanzie"], "updated_at": _now_iso()}})
            aggiornate += 1
    return {"polizze_aggiornate": aggiornate}


@router.post("/librerie/conti-cassa", status_code=201)
async def create_conto(body: dict, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    obj = ContoCassa(**body)
    await db.conti_cassa.insert_one(obj.model_dump())
    await log_attivita(user, "create", "conto_cassa", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/conti-cassa/{cid}")
async def update_conto(cid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    body["updated_at"] = _now_iso()
    res = await db.conti_cassa.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Conto non trovato")
    await log_attivita(user, "update", "conto_cassa", cid)
    return strip_mongo_id(await db.conti_cassa.find_one({"id": cid}, {"_id": 0}))


@router.delete("/librerie/conti-cassa/{cid}")
async def delete_conto(cid: str, user=Depends(require_user("admin"))) -> dict:
    await db.conti_cassa.delete_one({"id": cid})
    await log_attivita(user, "delete", "conto_cassa", cid)
    return {"ok": True}



# --- MEZZI DI PAGAMENTO (libreria unificata) ---
class MezzoPagamentoBody(BaseModel):
    codice: str
    label: str
    tipo_conto: Literal["cassa", "banca", "carta", "rid", "online", "altro"] = "altro"
    conto_default_id: Optional[str] = None
    icona: Optional[str] = None
    ordine: int = 0
    attivo: bool = True


@router.get("/librerie/mezzi-pagamento")
async def list_mezzi_pagamento(
    attivi: bool = False,
    user=Depends(current_user),
) -> list[dict]:
    flt = {}
    if attivi:
        flt["attivo"] = True
    items = await db.mezzi_pagamento.find(flt, {"_id": 0}).sort([("ordine", 1), ("label", 1)]).to_list(200)
    return items


@router.post("/librerie/mezzi-pagamento", status_code=201)
async def create_mezzo_pagamento(body: MezzoPagamentoBody, user=Depends(require_user("admin"))) -> dict:
    codice = body.codice.strip().lower()
    if not codice or not body.label:
        raise HTTPException(400, "Codice e label obbligatori")
    existing = await db.mezzi_pagamento.find_one({"codice": codice}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(400, f"Codice '{codice}' già presente")
    item = MezzoPagamento(
        codice=codice, label=body.label, tipo_conto=body.tipo_conto,
        conto_default_id=body.conto_default_id, icona=body.icona,
        ordine=body.ordine, attivo=body.attivo,
    )
    await db.mezzi_pagamento.insert_one(item.model_dump())
    return item.model_dump()


@router.put("/librerie/mezzi-pagamento/{mid}")
async def update_mezzo_pagamento(mid: str, body: MezzoPagamentoBody, user=Depends(require_user("admin"))) -> dict:
    existing = await db.mezzi_pagamento.find_one({"id": mid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Mezzo non trovato")
    upd = {**body.model_dump(), "updated_at": _now_iso()}
    upd["codice"] = upd["codice"].strip().lower()
    await db.mezzi_pagamento.update_one({"id": mid}, {"$set": upd})
    return {**existing, **upd}


@router.delete("/librerie/mezzi-pagamento/{mid}")
async def delete_mezzo_pagamento(mid: str, user=Depends(require_user("admin"))) -> dict:
    res = await db.mezzi_pagamento.delete_one({"id": mid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Mezzo non trovato")
    return {"ok": True}


async def _seed_mezzi_pagamento() -> dict:
    """Idempotente: crea i mezzi pagamento di default se mancano."""
    defaults = [
        {"codice": "contanti", "label": "Contanti", "tipo_conto": "cassa", "ordine": 1, "icona": "Banknote"},
        {"codice": "bonifico", "label": "Bonifico bancario", "tipo_conto": "banca", "ordine": 2, "icona": "Building2"},
        {"codice": "assegno", "label": "Assegno", "tipo_conto": "banca", "ordine": 3, "icona": "FileCheck"},
        {"codice": "pos", "label": "POS / Carta", "tipo_conto": "carta", "ordine": 4, "icona": "CreditCard"},
        {"codice": "rid", "label": "RID / SDD", "tipo_conto": "rid", "ordine": 5, "icona": "Repeat"},
        {"codice": "altro", "label": "Altro", "tipo_conto": "altro", "ordine": 99, "icona": "MoreHorizontal"},
    ]
    for d in defaults:
        existing = await db.mezzi_pagamento.find_one({"codice": d["codice"]}, {"_id": 0, "id": 1})
        if existing:
            continue
        item = MezzoPagamento(**d)
        await db.mezzi_pagamento.insert_one(item.model_dump())


# --- PRODOTTI ---
def _ramo_aliases(ramo: str) -> list[str]:
    """Restituisce gli alias possibili di un ramo (case-insensitive, con/senza spazi/underscore).
    Es: 'RC Auto' -> ['RC Auto', 'RCAuto', 'RC_AUTO', 'RCAUTO', 'RCA', 'RC AUTO']
    """
    if not ramo:
        return []
    base = ramo.strip()
    normalized = base.upper().replace("_", " ").replace("-", " ")
    no_space = normalized.replace(" ", "")
    aliases = {base, base.upper(), base.lower(), normalized, no_space, normalized.replace(" ", "_")}
    # Map noti
    rca_aliases = {"RC AUTO", "RCAUTO", "RCA", "RC_AUTO"}
    if no_space in rca_aliases or normalized in rca_aliases:
        aliases |= rca_aliases
    return [a for a in aliases if a]


@router.get("/librerie/prodotti")
async def list_prodotti(
    compagnia_id: Optional[str] = None,
    ramo: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt = {}
    if compagnia_id:
        flt["compagnia_id"] = compagnia_id
    if ramo:
        # Match fuzzy: cerca tutti gli alias del ramo (case-insensitive con/senza spazi)
        aliases = _ramo_aliases(ramo)
        flt["$or"] = [{"ramo": {"$regex": f"^{re.escape(a)}$", "$options": "i"}} for a in aliases]
    return await db.prodotti.find(flt, {"_id": 0}).sort("nome", 1).to_list(1000)


@router.post("/librerie/prodotti", status_code=201)
async def create_prodotto(body: dict, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    # Default termini_mora_giorni in base al ramo se non specificato
    if not body.get("termini_mora_giorni"):
        from db_models import default_mora_for_ramo
        body["termini_mora_giorni"] = default_mora_for_ramo(body.get("ramo"))
    obj = ProdottoLibreria(**body)
    await db.prodotti.insert_one(obj.model_dump())
    await log_attivita(user, "create", "prodotto", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/prodotti/{pid}")
async def update_prodotto(pid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    body["updated_at"] = _now_iso()
    res = await db.prodotti.update_one({"id": pid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    await log_attivita(user, "update", "prodotto", pid)
    return strip_mongo_id(await db.prodotti.find_one({"id": pid}, {"_id": 0}))


@router.delete("/librerie/prodotti/{pid}")
async def delete_prodotto(pid: str, user=Depends(require_user("admin"))) -> dict:
    await db.prodotti.delete_one({"id": pid})
    await log_attivita(user, "delete", "prodotto", pid)
    return {"ok": True}


# --- RAMI ---
@router.get("/librerie/rami")
async def list_rami(user=Depends(current_user)) -> list[dict]:
    return await db.rami.find({}, {"_id": 0}).sort("nome", 1).to_list(200)


@router.post("/librerie/rami", status_code=201)
async def create_ramo(body: dict, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    obj = RamoLibreria(**body)
    await db.rami.insert_one(obj.model_dump())
    await log_attivita(user, "create", "ramo", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/rami/{rid}")
async def update_ramo(rid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    body["updated_at"] = _now_iso()
    res = await db.rami.update_one({"id": rid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Ramo non trovato")
    return strip_mongo_id(await db.rami.find_one({"id": rid}, {"_id": 0}))


@router.delete("/librerie/rami/{rid}")
async def delete_ramo(rid: str, user=Depends(require_user("admin"))) -> dict:
    await db.rami.delete_one({"id": rid})
    return {"ok": True}


# ============================================================
# LIBRERIE — AZIENDA (DATI INTESTAZIONE / STAMPE)
# ============================================================
@router.get("/librerie/azienda")
async def get_azienda(user=Depends(current_user)) -> dict:
    """Singleton: dati dell'agenzia (usati nelle stampe)."""
    doc = await db.azienda_config.find_one({}, {"_id": 0})
    if not doc:
        # crea record vuoto al primo accesso (solo se admin)
        cfg = AziendaConfig()
        await db.azienda_config.insert_one(cfg.model_dump())
        doc = cfg.model_dump()
    return doc


@router.put("/librerie/azienda")
async def update_azienda(body: dict, user=Depends(require_user("admin"))) -> dict:
    body.pop("id", None)
    body["updated_at"] = _now_iso()
    existing = await db.azienda_config.find_one({})
    if not existing:
        cfg = AziendaConfig(**body)
        await db.azienda_config.insert_one(cfg.model_dump())
    else:
        await db.azienda_config.update_one({"id": existing["id"]}, {"$set": body})
    await log_attivita(user, "update", "azienda", existing["id"] if existing else None,
                       "Aggiornamento dati azienda")
    return await db.azienda_config.find_one({}, {"_id": 0})


@router.post("/librerie/azienda/logo")
async def upload_logo_azienda(file: UploadFile = File(...),
                               user=Depends(require_user("admin"))) -> dict:
    """Carica/sostituisce il logo dell'agenzia (usato in tutte le stampe PDF)."""
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Logo troppo grande (max 5 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    if not ct.startswith("image/"):
        raise HTTPException(400, "Il logo deve essere un'immagine (PNG/JPG/SVG)")
    ext = (file.filename or "logo.png").rsplit(".", 1)[-1].lower() or "png"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/azienda/logo_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, ct)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    url = f"/api/storage/{result['path']}"
    existing = await db.azienda_config.find_one({})
    set_fields = {"logo_url": url, "logo_storage_path": result["path"], "updated_at": _now_iso()}
    if not existing:
        cfg = AziendaConfig(**set_fields)
        await db.azienda_config.insert_one(cfg.model_dump())
    else:
        await db.azienda_config.update_one({"id": existing["id"]}, {"$set": set_fields})
    return {"logo_url": url}


# ============================================================
# LIBRERIE — SCHEMA PROVVIGIONALE
# ============================================================
@router.get("/librerie/schema-provvigionale")
async def list_schemi_provvigionali(
    collaboratore_id: Optional[str] = None,
    compagnia_id: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> list[dict]:
    """Elenco regole provvigionali, opzionalmente filtrate per collaboratore o compagnia."""
    q = {}
    if collaboratore_id:
        q["collaboratore_id"] = collaboratore_id
    if compagnia_id:
        q["compagnia_id"] = compagnia_id
    items = await db.schema_provvigionale.find(q, {"_id": 0}).sort("nome", 1).to_list(500)
    # arricchisci con nomi
    for it in items:
        if it.get("collaboratore_id"):
            u = await db.users.find_one({"id": it["collaboratore_id"]}, {"_id": 0, "name": 1})
            it["collaboratore_nome"] = u.get("name") if u else None
        if it.get("compagnia_id"):
            c = await db.compagnie.find_one({"id": it["compagnia_id"]}, {"_id": 0, "ragione_sociale": 1})
            it["compagnia_nome"] = c.get("ragione_sociale") if c else None
    return items


@router.post("/librerie/schema-provvigionale", status_code=201)
async def create_schema_provvigionale(body: dict, user=Depends(require_user("admin"))) -> dict:
    body = {k: (v if v != "" else None) for k, v in body.items()}
    obj = SchemaProvvigionale(**body)
    await db.schema_provvigionale.insert_one(obj.model_dump())
    await log_attivita(user, "create", "schema_provvigionale", obj.id, f"Schema '{obj.nome}'")
    return obj.model_dump()


@router.put("/librerie/schema-provvigionale/{sid}")
async def update_schema_provvigionale(sid: str, body: dict, user=Depends(require_user("admin"))) -> dict:
    body = {k: (v if v != "" else None) for k, v in body.items()}
    body.pop("id", None)
    body["updated_at"] = _now_iso()
    res = await db.schema_provvigionale.update_one({"id": sid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Schema non trovato")
    await log_attivita(user, "update", "schema_provvigionale", sid)
    return await db.schema_provvigionale.find_one({"id": sid}, {"_id": 0})


@router.delete("/librerie/schema-provvigionale/{sid}")
async def delete_schema_provvigionale(sid: str, user=Depends(require_user("admin"))) -> dict:
    res = await db.schema_provvigionale.delete_one({"id": sid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Schema non trovato")
    return {"ok": True}


# ============================================================
# RUBRICA CONTATTI COMPAGNIA
# ============================================================
@router.get("/contatti-compagnia")
async def list_contatti_compagnia(
    compagnia_id: Optional[str] = None,
    q: Optional[str] = None,
    attivo: Optional[bool] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if compagnia_id:
        flt["compagnia_id"] = compagnia_id
    if attivo is not None:
        flt["attivo"] = attivo
    if q:
        qrx = {"$regex": q, "$options": "i"}
        flt["$or"] = [
            {"nome": qrx}, {"cognome": qrx}, {"ruolo": qrx},
            {"email": qrx}, {"telefono": qrx}, {"cellulare": qrx},
            {"ufficio": qrx},
        ]
    items = await db.contatti_compagnia.find(flt, {"_id": 0}).sort([("cognome", 1), ("nome", 1)]).to_list(2000)
    # arricchimento ragione sociale compagnia
    cmp_ids = list({c.get("compagnia_id") for c in items if c.get("compagnia_id")})
    cmps = {c["id"]: c async for c in db.compagnie.find(
        {"id": {"$in": cmp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1},
    )}
    for c in items:
        cm = cmps.get(c.get("compagnia_id"), {})
        c["compagnia_nome"] = cm.get("ragione_sociale")
        c["compagnia_codice"] = cm.get("codice")
    return items


@router.post("/contatti-compagnia", status_code=201)
async def create_contatto_compagnia(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))) -> dict:
    if not body.get("compagnia_id") or not body.get("nome"):
        raise HTTPException(400, "compagnia_id e nome obbligatori")
    obj = ContattoCompagnia(**body)
    await db.contatti_compagnia.insert_one(obj.model_dump())
    await log_attivita(user, "create", "contatto_compagnia", obj.id,
                       f"Contatto '{obj.nome} {obj.cognome or ''}'")
    return obj.model_dump()


@router.put("/contatti-compagnia/{cid}")
async def update_contatto_compagnia(
    cid: str, body: dict,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    body.pop("id", None)
    body["updated_at"] = _now_iso()
    res = await db.contatti_compagnia.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Contatto non trovato")
    await log_attivita(user, "update", "contatto_compagnia", cid)
    return await db.contatti_compagnia.find_one({"id": cid}, {"_id": 0})


@router.delete("/contatti-compagnia/{cid}")
async def delete_contatto_compagnia(cid: str, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    res = await db.contatti_compagnia.delete_one({"id": cid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Contatto non trovato")
    await log_attivita(user, "delete", "contatto_compagnia", cid)
    return {"ok": True}


async def risolvi_provvigione_collaboratore(
    collaboratore_id: str, compagnia_id: Optional[str], ramo: Optional[str],
) -> float:
    """Ritorna la % di provvigione spettante al collaboratore per la combinazione data.

    Cerca la regola più specifica (collaboratore+compagnia+ramo) e ricade su default agenzia / utente.
    """
    # 1) regole specifiche del collaboratore (ordine di specificità decrescente)
    candidati = [
        {"collaboratore_id": collaboratore_id, "compagnia_id": compagnia_id, "ramo": ramo},
        {"collaboratore_id": collaboratore_id, "compagnia_id": compagnia_id, "ramo": None},
        {"collaboratore_id": collaboratore_id, "compagnia_id": None, "ramo": ramo},
        {"collaboratore_id": collaboratore_id, "compagnia_id": None, "ramo": None},
        {"collaboratore_id": None, "compagnia_id": compagnia_id, "ramo": ramo},
        {"collaboratore_id": None, "compagnia_id": compagnia_id, "ramo": None},
        {"collaboratore_id": None, "compagnia_id": None, "ramo": ramo},
        {"collaboratore_id": None, "compagnia_id": None, "ramo": None},
    ]
    for q in candidati:
        # rimuovi chiavi None tranne quelle che vogliamo esplicitamente None
        q["attivo"] = True
        doc = await db.schema_provvigionale.find_one(q, {"_id": 0})
        if doc:
            return float(doc.get("percentuale_collaboratore") or 0.0)
    # fallback: percentuale di default sull'utente
    u = await db.users.find_one({"id": collaboratore_id}, {"_id": 0, "perc_provvigione_default": 1})
    return float((u or {}).get("perc_provvigione_default") or 0.0)


@router.get("/librerie/schema-provvigionale/risolvi")
async def api_risolvi_provvigione(
    collaboratore_id: str,
    compagnia_id: Optional[str] = None,
    ramo: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    perc = await risolvi_provvigione_collaboratore(collaboratore_id, compagnia_id, ramo)
    return {"percentuale_collaboratore": perc}