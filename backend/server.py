"""Main FastAPI application for Programma Assicurativo.

Tutti gli endpoint sono sotto /api.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Literal
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

from auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, get_token_from_request, require_user, current_user, can_see_all,
)
from db_models import (
    UserCreate, UserPublic, LoginRequest, Compagnia, Anagrafica, Polizza, Titolo,
    Sinistro, MovimentoContabile, Intervista, CalcoloPensione, EmailMessaggio,
    AttivitaLog, ImportLog, Banca, ContoCassa, ProdottoLibreria, RamoLibreria,
    Allegato, DiarioVoce, MessaggioChat, Corso, ProgressoCorso, _now_iso, _uid,
)
import ania_importer
import inps_calculator
import storage as obj_storage
import pdf_report
import brogliaccio as brog
from fastapi.responses import StreamingResponse
import io as _io

# ---------- DB ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Programma Assicurativo")
api = APIRouter(prefix="/api")


# ---------- Helpers ----------
async def log_attivita(utente: dict, azione: str, entita: str,
                       entita_id: str | None = None, descrizione: str | None = None,
                       payload: dict | None = None):
    log = AttivitaLog(
        utente_id=utente.get("id") if utente else None,
        utente_email=utente.get("email") if utente else None,
        azione=azione, entita=entita, entita_id=entita_id,
        descrizione=descrizione, payload=payload,
    )
    await db.attivita_log.insert_one(log.model_dump())


def strip_mongo_id(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


async def visibility_filter(user: dict, base_filter: dict | None = None) -> dict:
    """Applica filtro per ruolo:
    - admin/collaboratore: vede tutto
    - dipendente: vede tutto (ma alcune azioni saranno bloccate)
    - cliente: vede solo le proprie polizze/anagrafica
    """
    base_filter = dict(base_filter or {})
    if user["role"] == "cliente" and user.get("anagrafica_id"):
        base_filter["contraente_id"] = user["anagrafica_id"]
    return base_filter


# ============================================================
# AUTH
# ============================================================
@api.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    response.set_cookie("access_token", access, httponly=True, secure=False,
                        samesite="lax", max_age=60 * 60 * 8, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=False,
                        samesite="lax", max_age=60 * 60 * 24 * 7, path="/")
    user.pop("password_hash", None)
    user.pop("_id", None)
    await log_attivita(user, "login", "auth", user["id"], f"Login utente {email}")
    return {"user": user, "access_token": access}


@api.post("/auth/logout")
async def logout(response: Response, user=Depends(current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    await log_attivita(user, "logout", "auth", user["id"], "Logout")
    return {"ok": True}


@api.get("/auth/me")
async def auth_me(user=Depends(current_user)):
    return user


@api.post("/auth/users", status_code=201)
async def create_user(payload: UserCreate, user=Depends(require_user("admin"))):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email già registrata")
    doc = UserPublic(email=email, name=payload.name, role=payload.role,
                     anagrafica_id=payload.anagrafica_id).model_dump()
    doc["password_hash"] = hash_password(payload.password)
    await db.users.insert_one(doc)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    await log_attivita(user, "create", "user", doc["id"], f"Creato utente {email}")
    return doc


@api.get("/auth/users")
async def list_users(user=Depends(require_user("admin", "collaboratore"))):
    users = await db.users.find({}, {"password_hash": 0, "_id": 0}).to_list(500)
    return users


@api.put("/auth/users/{uid}")
async def update_user(uid: str, body: dict, user=Depends(require_user("admin"))):
    body.pop("password_hash", None)
    body.pop("id", None)
    if body.get("password"):
        body["password_hash"] = hash_password(body.pop("password"))
    body["updated_at"] = _now_iso()
    res = await db.users.update_one({"id": uid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Utente non trovato")
    await log_attivita(user, "update", "user", uid)
    u = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    return u


@api.delete("/auth/users/{uid}")
async def delete_user(uid: str, user=Depends(require_user("admin"))):
    if uid == user["id"]:
        raise HTTPException(400, "Non puoi eliminare te stesso")
    res = await db.users.delete_one({"id": uid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Utente non trovato")
    await log_attivita(user, "delete", "user", uid)
    return {"ok": True}


# ============================================================
# COMPAGNIE
# ============================================================
@api.get("/compagnie")
async def list_compagnie(user=Depends(current_user)):
    items = await db.compagnie.find({}, {"_id": 0}).to_list(1000)
    return items


@api.post("/compagnie", status_code=201)
async def create_compagnia(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    obj = Compagnia(**body)
    await db.compagnie.insert_one(obj.model_dump())
    await log_attivita(user, "create", "compagnia", obj.id, f"Creata compagnia {obj.codice}")
    return obj.model_dump()


@api.put("/compagnie/{cid}")
async def update_compagnia(cid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    body["updated_at"] = _now_iso()
    res = await db.compagnie.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Compagnia non trovata")
    await log_attivita(user, "update", "compagnia", cid)
    doc = await db.compagnie.find_one({"id": cid}, {"_id": 0})
    return doc


@api.delete("/compagnie/{cid}")
async def delete_compagnia(cid: str, user=Depends(require_user("admin"))):
    await db.compagnie.delete_one({"id": cid})
    await log_attivita(user, "delete", "compagnia", cid)
    return {"ok": True}


# ============================================================
# ANAGRAFICHE
# ============================================================
@api.get("/anagrafiche")
async def list_anagrafiche(
    q: Optional[str] = None,
    limit: int = 200,
    user=Depends(current_user),
):
    flt: dict = {}
    if user["role"] == "cliente" and user.get("anagrafica_id"):
        flt["id"] = user["anagrafica_id"]
    if q:
        flt["$or"] = [
            {"ragione_sociale": {"$regex": q, "$options": "i"}},
            {"codice_fiscale": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
        ]
    items = await db.anagrafiche.find(flt, {"_id": 0}).sort("ragione_sociale", 1).to_list(limit)
    return items


@api.get("/anagrafiche/{aid}")
async def get_anagrafica(aid: str, user=Depends(current_user)):
    if user["role"] == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Permesso negato")
    doc = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Non trovata")
    # arricchisci con relazioni risolte
    relazioni_risolte = []
    for rel in doc.get("parente_di", []):
        rel_doc = await db.anagrafiche.find_one(
            {"id": rel.get("anagrafica_id")},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "codice_fiscale": 1, "data_nascita": 1},
        )
        if rel_doc:
            relazioni_risolte.append({**rel_doc, "relazione": rel.get("relazione")})
    doc["relazioni_risolte"] = relazioni_risolte
    return doc


@api.post("/anagrafiche", status_code=201)
async def create_anagrafica(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    obj = Anagrafica(**body)
    await db.anagrafiche.insert_one(obj.model_dump())
    await log_attivita(user, "create", "anagrafica", obj.id, f"Creata anagrafica {obj.ragione_sociale}")
    return obj.model_dump()


@api.put("/anagrafiche/{aid}")
async def update_anagrafica(aid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["updated_at"] = _now_iso()
    res = await db.anagrafiche.update_one({"id": aid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Non trovata")
    await log_attivita(user, "update", "anagrafica", aid)
    return strip_mongo_id(await db.anagrafiche.find_one({"id": aid}, {"_id": 0}))


@api.delete("/anagrafiche/{aid}")
async def delete_anagrafica(aid: str, user=Depends(require_user("admin"))):
    await db.anagrafiche.delete_one({"id": aid})
    await log_attivita(user, "delete", "anagrafica", aid)
    return {"ok": True}


@api.post("/anagrafiche/{aid}/relazioni")
async def add_relazione(aid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Aggiunge una relazione di parentela bidirezionale."""
    target = body.get("anagrafica_id")
    relazione = body.get("relazione", "altro")
    relazione_inversa = body.get("relazione_inversa", "altro")
    if not target or target == aid:
        raise HTTPException(400, "anagrafica_id non valido")
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$push": {"parente_di": {"anagrafica_id": target, "relazione": relazione}}},
    )
    await db.anagrafiche.update_one(
        {"id": target},
        {"$push": {"parente_di": {"anagrafica_id": aid, "relazione": relazione_inversa}}},
    )
    await log_attivita(user, "update", "anagrafica", aid,
                       f"Relazione {relazione} con {target}")
    return {"ok": True}


@api.delete("/anagrafiche/{aid}/relazioni/{target_id}")
async def remove_relazione(aid: str, target_id: str, user=Depends(require_user("admin", "collaboratore"))):
    await db.anagrafiche.update_one(
        {"id": aid}, {"$pull": {"parente_di": {"anagrafica_id": target_id}}}
    )
    await db.anagrafiche.update_one(
        {"id": target_id}, {"$pull": {"parente_di": {"anagrafica_id": aid}}}
    )
    return {"ok": True}


# ============================================================
# INTERVISTA
# ============================================================
@api.get("/anagrafiche/{aid}/interviste")
async def list_interviste(aid: str, user=Depends(current_user)):
    items = await db.interviste.find({"anagrafica_id": aid}, {"_id": 0}).sort("data_intervista", -1).to_list(50)
    return items


@api.post("/anagrafiche/{aid}/interviste", status_code=201)
async def create_intervista(aid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["anagrafica_id"] = aid
    body["operatore_id"] = user["id"]
    obj = Intervista(**body)
    await db.interviste.insert_one(obj.model_dump())
    await log_attivita(user, "create", "intervista", obj.id, f"Intervista per {aid}")
    return obj.model_dump()


# ============================================================
# POLIZZE
# ============================================================
@api.get("/polizze")
async def list_polizze(
    q: Optional[str] = None,
    stato: Optional[str] = None,
    ramo: Optional[str] = None,
    contraente_id: Optional[str] = None,
    limit: int = 500,
    user=Depends(current_user),
):
    flt = await visibility_filter(user)
    if stato:
        flt["stato"] = stato
    if ramo:
        flt["ramo"] = ramo
    if contraente_id:
        flt["contraente_id"] = contraente_id
    if q:
        flt["$or"] = [
            {"numero_polizza": {"$regex": q, "$options": "i"}},
            {"targa": {"$regex": q, "$options": "i"}},
        ]
    items = await db.polizze.find(flt, {"_id": 0}).sort("scadenza", 1).to_list(limit)
    # enrich con contraente e compagnia
    ana_ids = list({i["contraente_id"] for i in items if i.get("contraente_id")})
    comp_ids = list({i["compagnia_id"] for i in items if i.get("compagnia_id")})
    anas = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}},
                                                          {"_id": 0, "id": 1, "ragione_sociale": 1})}
    comps = {c["id"]: c async for c in db.compagnie.find({"id": {"$in": comp_ids}},
                                                         {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1})}
    for it in items:
        it["contraente_nome"] = anas.get(it.get("contraente_id"), {}).get("ragione_sociale")
        it["compagnia_nome"] = comps.get(it.get("compagnia_id"), {}).get("ragione_sociale")
    return items


@api.get("/polizze/{pid}")
async def get_polizza(pid: str, user=Depends(current_user)):
    doc = await db.polizze.find_one({"id": pid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Non trovata")
    if user["role"] == "cliente" and user.get("anagrafica_id") != doc.get("contraente_id"):
        raise HTTPException(403, "Permesso negato")
    doc["contraente"] = await db.anagrafiche.find_one({"id": doc["contraente_id"]}, {"_id": 0})
    doc["compagnia"] = await db.compagnie.find_one({"id": doc["compagnia_id"]}, {"_id": 0})
    doc["titoli"] = await db.titoli.find({"polizza_id": pid}, {"_id": 0}).sort("effetto", -1).to_list(100)
    doc["sinistri"] = await db.sinistri.find({"polizza_id": pid}, {"_id": 0}).sort("data_avvenimento", -1).to_list(100)
    return doc


@api.post("/polizze", status_code=201)
async def create_polizza(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    obj = Polizza(**body)
    await db.polizze.insert_one(obj.model_dump())
    await log_attivita(user, "create", "polizza", obj.id, f"Polizza {obj.numero_polizza}")
    return obj.model_dump()


@api.put("/polizze/{pid}")
async def update_polizza(pid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["updated_at"] = _now_iso()
    res = await db.polizze.update_one({"id": pid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Non trovata")
    await log_attivita(user, "update", "polizza", pid)
    return strip_mongo_id(await db.polizze.find_one({"id": pid}, {"_id": 0}))


@api.delete("/polizze/{pid}")
async def delete_polizza(pid: str, user=Depends(require_user("admin"))):
    await db.polizze.delete_one({"id": pid})
    await log_attivita(user, "delete", "polizza", pid)
    return {"ok": True}


# ============================================================
# TITOLI
# ============================================================
@api.get("/titoli")
async def list_titoli(
    polizza_id: Optional[str] = None,
    stato: Optional[str] = None,
    compagnia_id: Optional[str] = None,
    collaboratore_id: Optional[str] = None,
    ramo: Optional[str] = None,
    prodotto: Optional[str] = None,
    mezzo_pagamento: Optional[str] = None,
    conto_cassa_id: Optional[str] = None,
    in_scadenza_giorni: Optional[int] = None,
    coperti_non_pagati: Optional[bool] = None,
    # nuovi filtri scadenza dettagliata
    scadute_oggi: Optional[bool] = None,
    scadute_da_min: Optional[int] = None,    # es. 5 (scadute da almeno 5 giorni)
    scadute_da_max: Optional[int] = None,    # es. 14 (scadute al massimo da 14 giorni)
    scadenza_oltre_giorni: Optional[int] = None,  # in scadenza oltre N gg
    # filtro periodo (sulla scadenza)
    dal: Optional[str] = None,
    al: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 2000,
    user=Depends(current_user),
):
    flt: dict = {}
    if polizza_id:
        flt["polizza_id"] = polizza_id
    if stato:
        flt["stato"] = stato

    # filtri lato polizza (compagnia/collaboratore/ramo/prodotto/q-su-targa-numero)
    pol_filter: dict = {}
    if compagnia_id: pol_filter["compagnia_id"] = compagnia_id
    if collaboratore_id: pol_filter["collaboratore_id"] = collaboratore_id
    if ramo: pol_filter["ramo"] = ramo
    if prodotto: pol_filter["prodotto"] = prodotto
    if user["role"] == "cliente" and user.get("anagrafica_id"):
        pol_filter["contraente_id"] = user["anagrafica_id"]

    ana_match_ids = None
    if q:
        # ricerca generica: numero polizza, targa, contraente
        qrx = {"$regex": q, "$options": "i"}
        pol_q = {"$or": [{"numero_polizza": qrx}, {"targa": qrx}]}
        # cerca anche tra anagrafiche
        ana_ids = [a["id"] async for a in db.anagrafiche.find(
            {"ragione_sociale": qrx}, {"_id": 0, "id": 1}
        )]
        if ana_ids:
            pol_q["$or"].append({"contraente_id": {"$in": ana_ids}})
        if pol_filter:
            pol_filter = {"$and": [pol_filter, pol_q]}
        else:
            pol_filter = pol_q

    if pol_filter:
        pol_ids = [p["id"] async for p in db.polizze.find(pol_filter, {"_id": 0, "id": 1})]
        flt["polizza_id"] = {"$in": pol_ids}

    if mezzo_pagamento:
        flt["mezzo_pagamento"] = mezzo_pagamento
    if conto_cassa_id:
        flt["conto_cassa_id"] = conto_cassa_id

    from datetime import date, timedelta
    today = date.today()
    today_s = today.isoformat()

    if in_scadenza_giorni is not None:
        limite = (today + timedelta(days=int(in_scadenza_giorni))).isoformat()
        flt["stato"] = {"$in": ["da_incassare", "insoluto"]}
        flt["scadenza"] = {"$gte": today_s, "$lte": limite}

    if scadenza_oltre_giorni is not None:
        oltre = (today + timedelta(days=int(scadenza_oltre_giorni))).isoformat()
        flt["stato"] = {"$in": ["da_incassare", "insoluto"]}
        flt["scadenza"] = {"$gt": oltre}

    if scadute_oggi:
        flt["stato"] = {"$in": ["da_incassare", "insoluto"]}
        flt["scadenza"] = today_s

    if scadute_da_min is not None or scadute_da_max is not None:
        flt["stato"] = {"$in": ["da_incassare", "insoluto"]}
        cond = {}
        if scadute_da_min is not None:
            # scadenza <= oggi - min
            cond["$lte"] = (today - timedelta(days=int(scadute_da_min))).isoformat()
        if scadute_da_max is not None:
            # scadenza >= oggi - max
            cond["$gte"] = (today - timedelta(days=int(scadute_da_max))).isoformat()
        flt["scadenza"] = cond if isinstance(flt.get("scadenza"), str) is False else {**(flt.get("scadenza") if isinstance(flt.get("scadenza"), dict) else {}), **cond}

    if coperti_non_pagati:
        flt["stato"] = {"$in": ["da_incassare", "insoluto"]}
        flt["effetto"] = {"$lte": today_s}
        flt["scadenza"] = {"$gte": today_s}

    # filtro periodo (sulla scadenza, sovrascrive eventuali altri set sulla scadenza)
    if dal or al:
        cond = {}
        if dal: cond["$gte"] = dal
        if al: cond["$lte"] = al
        if isinstance(flt.get("scadenza"), dict):
            flt["scadenza"] = {**flt["scadenza"], **cond}
        else:
            flt["scadenza"] = cond

    items = await db.titoli.find(flt, {"_id": 0}).sort("scadenza", 1).to_list(limit)
    pol_ids = list({t["polizza_id"] for t in items if t.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find(
        {"id": {"$in": pol_ids}}, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1,
                                   "ramo": 1, "prodotto": 1, "compagnia_id": 1,
                                   "collaboratore_id": 1, "targa": 1})}
    ana_ids = list({p.get("contraente_id") for p in pols.values() if p.get("contraente_id")})
    anas = {a["id"]: a async for a in db.anagrafiche.find(
        {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    com_ids = list({p.get("compagnia_id") for p in pols.values() if p.get("compagnia_id")})
    coms = {c["id"]: c async for c in db.compagnie.find(
        {"id": {"$in": com_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    collab_ids = list({p.get("collaboratore_id") for p in pols.values() if p.get("collaboratore_id")})
    collabs = {u["id"]: u async for u in db.users.find(
        {"id": {"$in": collab_ids}}, {"_id": 0, "id": 1, "name": 1})}
    for t in items:
        p = pols.get(t.get("polizza_id"), {})
        t["numero_polizza"] = p.get("numero_polizza")
        t["ramo"] = p.get("ramo")
        t["prodotto"] = p.get("prodotto")
        t["targa"] = p.get("targa")
        t["contraente_id"] = p.get("contraente_id")
        t["contraente_nome"] = anas.get(p.get("contraente_id", ""), {}).get("ragione_sociale")
        t["compagnia_nome"] = coms.get(p.get("compagnia_id", ""), {}).get("ragione_sociale")
        t["collaboratore_id"] = p.get("collaboratore_id")
        t["collaboratore_nome"] = collabs.get(p.get("collaboratore_id", ""), {}).get("name")
    return items


# Bulk actions sui titoli
@api.post("/titoli/bulk-incassa")
async def bulk_incassa(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """body: {ids: [...], data_incasso, mezzo_pagamento, conto_cassa_id}"""
    ids = body.get("ids") or []
    if not ids:
        raise HTTPException(400, "Nessun titolo selezionato")
    data_incasso = body.get("data_incasso") or _now_iso()[:10]
    mezzo = body.get("mezzo_pagamento") or "bonifico"
    conto_id = body.get("conto_cassa_id")
    n_incassati = 0; tot = 0.0
    for tid in ids:
        titolo = await db.titoli.find_one({"id": tid}, {"_id": 0})
        if not titolo or titolo.get("stato") == "incassato":
            continue
        await db.titoli.update_one(
            {"id": tid},
            {"$set": {"stato": "incassato", "data_incasso": data_incasso,
                      "mezzo_pagamento": mezzo, "conto_cassa_id": conto_id,
                      "updated_at": _now_iso()}},
        )
        pol = await db.polizze.find_one({"id": titolo["polizza_id"]}, {"_id": 0})
        mov = MovimentoContabile(
            data_movimento=data_incasso, tipo="entrata", categoria="incasso_premio",
            importo=titolo.get("importo_lordo", 0.0),
            descrizione=f"Incasso polizza {pol['numero_polizza'] if pol else titolo['polizza_id']}",
            polizza_id=titolo["polizza_id"], titolo_id=tid,
            anagrafica_id=pol.get("contraente_id") if pol else None,
            compagnia_id=pol.get("compagnia_id") if pol else None,
            conto_cassa_id=conto_id, mezzo_pagamento=mezzo,
            provvigioni=titolo.get("provvigioni", 0.0),
        )
        await db.movimenti.insert_one(mov.model_dump())
        n_incassati += 1
        tot += titolo.get("importo_lordo", 0.0)
    await log_attivita(user, "bulk_incasso", "titolo", None, f"{n_incassati} titoli incassati per €{tot:.2f}")
    return {"incassati": n_incassati, "totale": round(tot, 2)}


@api.post("/titoli/bulk-copertura")
async def bulk_copertura(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Imposta una data di copertura sui titoli (senza incassarli).
    body: {ids: [...], coperto_fino_a: 'YYYY-MM-DD'}"""
    ids = body.get("ids") or []
    coperto = body.get("coperto_fino_a")
    if not ids or not coperto:
        raise HTTPException(400, "ids e coperto_fino_a richiesti")
    res = await db.titoli.update_many(
        {"id": {"$in": ids}},
        {"$set": {"coperto_fino_a": coperto, "updated_at": _now_iso()}},
    )
    await log_attivita(user, "bulk_copertura", "titolo", None,
                       f"{res.modified_count} titoli con copertura fino al {coperto}")
    return {"aggiornati": res.modified_count}


@api.get("/export/titoli.csv")
async def export_titoli_csv(stato: Optional[str] = None,
                            user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    items = await list_titoli(stato=stato, limit=10000, user=user)
    import csv as _csv
    out = _io.StringIO()
    w = _csv.writer(out, delimiter=";")
    w.writerow(["Numero polizza", "Targa", "Contraente", "Compagnia", "Collaboratore",
                "Ramo", "Tipo", "Effetto", "Scadenza", "Stato",
                "Lordo", "Netto", "Imposte", "Provvigioni",
                "Mezzo pagamento", "Data incasso", "Coperto fino a"])
    for t in items:
        w.writerow([t.get("numero_polizza"), t.get("targa"), t.get("contraente_nome"),
                    t.get("compagnia_nome"), t.get("collaboratore_nome"),
                    t.get("ramo"), t.get("tipo"), t.get("effetto"), t.get("scadenza"),
                    t.get("stato"), t.get("importo_lordo"), t.get("importo_netto"),
                    t.get("imposte"), t.get("provvigioni"),
                    t.get("mezzo_pagamento"), t.get("data_incasso"), t.get("coperto_fino_a")])
    csv_bytes = out.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        _io.BytesIO(csv_bytes), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="titoli.csv"'},
    )


@api.get("/export/titoli.xlsx")
async def export_titoli_xlsx(stato: Optional[str] = None,
                             user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    items = await list_titoli(stato=stato, limit=10000, user=user)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = "Titoli"
    headers = ["Numero polizza", "Targa", "Contraente", "Compagnia", "Collaboratore",
               "Ramo", "Tipo", "Effetto", "Scadenza", "Stato",
               "Lordo €", "Netto €", "Imposte €", "Provvigioni €",
               "Mezzo pag.", "Data incasso", "Coperto fino"]
    ws.append(headers)
    head_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    head_font = Font(bold=True, color="FFFFFF")
    for col in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col)
        c.fill = head_fill; c.font = head_font; c.alignment = Alignment(horizontal="center")
    for t in items:
        ws.append([t.get("numero_polizza"), t.get("targa"), t.get("contraente_nome"),
                   t.get("compagnia_nome"), t.get("collaboratore_nome"),
                   t.get("ramo"), t.get("tipo"), t.get("effetto"), t.get("scadenza"),
                   t.get("stato"), t.get("importo_lordo"), t.get("importo_netto"),
                   t.get("imposte"), t.get("provvigioni"),
                   t.get("mezzo_pagamento"), t.get("data_incasso"), t.get("coperto_fino_a")])
    # auto column widths
    for col in ws.columns:
        ml = max((len(str(c.value)) if c.value else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(ml + 2, 10), 30)
    out = _io.BytesIO(); wb.save(out); out.seek(0)
    return StreamingResponse(
        out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="titoli.xlsx"'},
    )


@api.delete("/titoli/{tid}")
async def delete_titolo(tid: str, user=Depends(require_user("admin", "collaboratore"))):
    res = await db.titoli.delete_one({"id": tid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Titolo non trovato")
    await db.movimenti.delete_many({"titolo_id": tid})
    await log_attivita(user, "delete", "titolo", tid)
    return {"ok": True}


@api.post("/titoli", status_code=201)
async def create_titolo(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    obj = Titolo(**body)
    await db.titoli.insert_one(obj.model_dump())
    await log_attivita(user, "create", "titolo", obj.id)
    return obj.model_dump()


@api.put("/titoli/{tid}")
async def update_titolo(tid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["updated_at"] = _now_iso()
    res = await db.titoli.update_one({"id": tid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Non trovato")
    await log_attivita(user, "update", "titolo", tid)
    return strip_mongo_id(await db.titoli.find_one({"id": tid}, {"_id": 0}))


@api.post("/titoli/{tid}/incassa")
async def incassa_titolo(tid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Marca un titolo come incassato e crea un movimento contabile."""
    titolo = await db.titoli.find_one({"id": tid}, {"_id": 0})
    if not titolo:
        raise HTTPException(404, "Titolo non trovato")
    data_incasso = body.get("data_incasso") or _now_iso()[:10]
    mezzo = body.get("mezzo_pagamento") or "bonifico"
    await db.titoli.update_one(
        {"id": tid},
        {"$set": {"stato": "incassato", "data_incasso": data_incasso,
                  "mezzo_pagamento": mezzo, "updated_at": _now_iso()}},
    )
    pol = await db.polizze.find_one({"id": titolo["polizza_id"]}, {"_id": 0})
    mov = MovimentoContabile(
        data_movimento=data_incasso,
        tipo="entrata",
        categoria="incasso_premio",
        importo=titolo.get("importo_lordo", 0.0),
        descrizione=f"Incasso titolo polizza {pol['numero_polizza'] if pol else titolo['polizza_id']}",
        polizza_id=titolo["polizza_id"],
        titolo_id=tid,
        anagrafica_id=pol.get("contraente_id") if pol else None,
        compagnia_id=pol.get("compagnia_id") if pol else None,
        mezzo_pagamento=mezzo,
    )
    await db.movimenti.insert_one(mov.model_dump())
    await log_attivita(user, "incasso", "titolo", tid)
    return {"ok": True, "movimento": mov.model_dump()}


# ============================================================
# SINISTRI
# ============================================================
@api.get("/sinistri")
async def list_sinistri(
    stato: Optional[str] = None,
    polizza_id: Optional[str] = None,
    limit: int = 500,
    user=Depends(current_user),
):
    flt = await visibility_filter(user)
    if stato:
        flt["stato"] = stato
    if polizza_id:
        flt["polizza_id"] = polizza_id
    items = await db.sinistri.find(flt, {"_id": 0}).sort("data_avvenimento", -1).to_list(limit)
    pol_ids = list({s["polizza_id"] for s in items if s.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find(
        {"id": {"$in": pol_ids}}, {"_id": 0, "id": 1, "numero_polizza": 1})}
    for s in items:
        s["numero_polizza"] = pols.get(s.get("polizza_id"), {}).get("numero_polizza")
    return items


@api.post("/sinistri", status_code=201)
async def create_sinistro(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    obj = Sinistro(**body)
    await db.sinistri.insert_one(obj.model_dump())
    await log_attivita(user, "create", "sinistro", obj.id, f"Sinistro {obj.numero_sinistro}")
    return obj.model_dump()


@api.put("/sinistri/{sid}")
async def update_sinistro(sid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["updated_at"] = _now_iso()
    res = await db.sinistri.update_one({"id": sid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Non trovato")
    await log_attivita(user, "update", "sinistro", sid)
    return strip_mongo_id(await db.sinistri.find_one({"id": sid}, {"_id": 0}))


@api.delete("/sinistri/{sid}")
async def delete_sinistro(sid: str, user=Depends(require_user("admin", "collaboratore"))):
    res = await db.sinistri.delete_one({"id": sid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Sinistro non trovato")
    await log_attivita(user, "delete", "sinistro", sid)
    return {"ok": True}


# ============================================================
# CONTABILITA
# ============================================================
@api.get("/contabilita/movimenti")
async def list_movimenti(
    dal: Optional[str] = None,
    al: Optional[str] = None,
    tipo: Optional[str] = None,
    anagrafica_id: Optional[str] = None,
    limit: int = 500,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    flt: dict = {}
    if tipo:
        flt["tipo"] = tipo
    if anagrafica_id:
        flt["anagrafica_id"] = anagrafica_id
    if dal or al:
        cond = {}
        if dal:
            cond["$gte"] = dal
        if al:
            cond["$lte"] = al
        flt["data_movimento"] = cond
    items = await db.movimenti.find(flt, {"_id": 0}).sort("data_movimento", -1).to_list(limit)
    return items


@api.post("/contabilita/movimenti", status_code=201)
async def create_movimento(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    obj = MovimentoContabile(**body)
    await db.movimenti.insert_one(obj.model_dump())
    await log_attivita(user, "create", "movimento", obj.id, f"€{obj.importo} {obj.descrizione}")
    return obj.model_dump()


@api.put("/contabilita/movimenti/{mid}")
async def update_movimento(mid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["updated_at"] = _now_iso()
    res = await db.movimenti.update_one({"id": mid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Movimento non trovato")
    await log_attivita(user, "update", "movimento", mid)
    return strip_mongo_id(await db.movimenti.find_one({"id": mid}, {"_id": 0}))


@api.delete("/contabilita/movimenti/{mid}")
async def delete_movimento(mid: str, user=Depends(require_user("admin", "collaboratore"))):
    res = await db.movimenti.delete_one({"id": mid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Movimento non trovato")
    await log_attivita(user, "delete", "movimento", mid)
    return {"ok": True}


@api.get("/contabilita/estratto-conto/{anagrafica_id}")
async def estratto_conto(anagrafica_id: str, user=Depends(current_user)):
    if user["role"] == "cliente" and user.get("anagrafica_id") != anagrafica_id:
        raise HTTPException(403, "Permesso negato")
    movs = await db.movimenti.find({"anagrafica_id": anagrafica_id}, {"_id": 0}) \
        .sort("data_movimento", 1).to_list(1000)
    saldo = 0.0
    rows = []
    for m in movs:
        delta = m["importo"] if m["tipo"] == "entrata" else -m["importo"]
        saldo += delta
        rows.append({**m, "saldo_progressivo": round(saldo, 2)})
    ana = await db.anagrafiche.find_one({"id": anagrafica_id}, {"_id": 0})
    return {"anagrafica": ana, "movimenti": rows, "saldo_finale": round(saldo, 2)}


@api.get("/contabilita/prima-nota")
async def prima_nota(
    dal: Optional[str] = None, al: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    flt: dict = {}
    if dal or al:
        cond = {}
        if dal:
            cond["$gte"] = dal
        if al:
            cond["$lte"] = al
        flt["data_movimento"] = cond
    items = await db.movimenti.find(flt, {"_id": 0}).sort("data_movimento", 1).to_list(2000)
    totale_entrate = sum(m["importo"] for m in items if m["tipo"] == "entrata")
    totale_uscite = sum(m["importo"] for m in items if m["tipo"] == "uscita")
    return {
        "movimenti": items,
        "totale_entrate": round(totale_entrate, 2),
        "totale_uscite": round(totale_uscite, 2),
        "saldo": round(totale_entrate - totale_uscite, 2),
    }


# ============================================================
# IMPORTAZIONE ANIA
# ============================================================
@api.post("/import/ania")
async def import_ania(file: UploadFile = File(...),
                      user=Depends(require_user("admin", "collaboratore"))):
    contents = await file.read()
    log = await ania_importer.importa_zip(db, contents, file.filename, user)
    await log_attivita(user, "import", "ania", log.id,
                       f"Import file {file.filename}", payload=log.record_types_processati)
    return log.model_dump()


@api.get("/import/storico")
async def import_storico(limit: int = 50, user=Depends(require_user("admin", "collaboratore"))):
    items = await db.import_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


# ============================================================
# PENSIONI INPS
# ============================================================
class CalcoloRequest(BaseModel):
    tipo_pensione: Literal["invalidita", "inabilita", "superstite"]
    settimane_contributive: int = 0
    retribuzione_media_annua: float = 0.0
    eta: int = 0
    percentuale_invalidita: Optional[float] = None
    numero_familiari: int = 0
    anagrafica_id: Optional[str] = None


@api.post("/pensioni/calcola")
async def calcola_pensione(body: CalcoloRequest, user=Depends(current_user)):
    risultato = inps_calculator.calcola_pensione(
        tipo=body.tipo_pensione,
        settimane_contributive=body.settimane_contributive,
        retribuzione_media_annua=body.retribuzione_media_annua,
        eta=body.eta,
        percentuale_invalidita=body.percentuale_invalidita,
        numero_familiari=body.numero_familiari,
    )
    calc = CalcoloPensione(
        anagrafica_id=body.anagrafica_id,
        tipo_pensione=body.tipo_pensione,
        data_inizio_contribuzione="",
        settimane_contributive=body.settimane_contributive,
        retribuzione_media_annua=body.retribuzione_media_annua,
        eta_richiedente=body.eta,
        percentuale_invalidita=body.percentuale_invalidita,
        numero_familiari=body.numero_familiari,
        **risultato,
    )
    await db.calcoli_pensione.insert_one(calc.model_dump())
    await log_attivita(user, "calc_pensione", "pensione", calc.id, body.tipo_pensione)
    return calc.model_dump()


@api.post("/pensioni/parse-estratto")
async def parse_estratto(file: UploadFile = File(...), user=Depends(current_user)):
    raw = await file.read()
    fname = (file.filename or "").lower()
    text = ""

    if fname.endswith(".pdf"):
        try:
            import pdfplumber
            import io as _io
            with pdfplumber.open(_io.BytesIO(raw)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    pages_text.append(t)
                text = "\n".join(pages_text)
        except Exception as e:
            logger.error("PDF parse error: %s", e)
            raise HTTPException(400, f"Impossibile leggere il PDF: {e}")
        if not text.strip():
            return {
                "settimane_contributive": 0,
                "retribuzione_media_annua": 0.0,
                "anni_stimati": 0,
                "warning": "Il PDF non contiene testo estraibile (potrebbe essere scansionato). Inserisci manualmente i dati.",
            }
    else:
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            text = raw.decode("latin-1", errors="ignore")

    result = inps_calculator.parse_estratto_conto_inps(text)
    # se non ho trovato nulla nel PDF avviso
    if fname.endswith(".pdf") and not result.get("settimane_contributive") and not result.get("retribuzione_media_annua"):
        result["warning"] = (
            "PDF letto correttamente ma non sono riuscito a riconoscere settimane/retribuzione. "
            "Inseriscili manualmente o controlla che l'estratto contenga voci come "
            "\"Totale settimane\" e \"Retribuzione imponibile\"."
        )
    return result


@api.get("/pensioni/storico")
async def storico_pensioni(anagrafica_id: Optional[str] = None, user=Depends(current_user)):
    flt: dict = {}
    if anagrafica_id:
        flt["anagrafica_id"] = anagrafica_id
    items = await db.calcoli_pensione.find(flt, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@api.get("/anagrafiche/{aid}/calcolo-pensione/preview")
async def calcolo_pensione_preview(aid: str, user=Depends(current_user)):
    """Restituisce dati pre-compilati per il calcolo pensione partendo dall'anagrafica.

    Calcola:
    - eta corrente
    - numero_familiari aventi diritto (coniuge se sposato + figli a carico)
    - settimane stimate (da anni contributivi se presenti)
    - flag requisiti_superstite_ok (se ha coniuge o figli a carico)
    """
    if user["role"] == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Permesso negato")
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")

    from datetime import date
    eta = 0
    if ana.get("data_nascita"):
        try:
            d = date.fromisoformat(ana["data_nascita"])
            today = date.today()
            eta = today.year - d.year - (1 if (today.month, today.day) < (d.month, d.day) else 0)
        except Exception:
            pass

    # familiari aventi diritto per pensione superstite
    coniugato = (ana.get("stato_civile") or "").lower() in ("coniugato", "coniugata", "sposato", "sposata", "unito civilmente")
    figli_carico = int(ana.get("numero_figli_a_carico") or 0)
    n_familiari = (1 if coniugato else 0) + figli_carico
    requisiti_superstite_ok = n_familiari > 0

    # settimane stimate
    settimane = ana.get("settimane_contributive")
    if not settimane and ana.get("data_inizio_contribuzione"):
        try:
            di = date.fromisoformat(ana["data_inizio_contribuzione"])
            anni = (date.today() - di).days / 365.25
            settimane = int(anni * 52)
        except Exception:
            settimane = 0

    return {
        "anagrafica_id": aid,
        "nome": ana["ragione_sociale"],
        "eta": eta,
        "data_nascita": ana.get("data_nascita"),
        "stato_civile": ana.get("stato_civile"),
        "coniugato": coniugato,
        "tipo_lavoratore": ana.get("tipo_lavoratore"),
        "professione": ana.get("professione"),
        "reddito_annuo_lordo": ana.get("reddito_annuo_lordo") or 0.0,
        "numero_figli": ana.get("numero_figli") or 0,
        "numero_figli_a_carico": figli_carico,
        "numero_familiari": n_familiari,
        "requisiti_superstite_ok": requisiti_superstite_ok,
        "settimane_contributive": settimane or 0,
        "warnings": [
            "Nessun coniuge né figli a carico: la pensione superstite non spetta." if not requisiti_superstite_ok else None,
            "Reddito annuo non valorizzato: il calcolo del GAP non è significativo." if not ana.get("reddito_annuo_lordo") else None,
        ],
    }


@api.post("/anagrafiche/{aid}/calcolo-pensione/calcola")
async def calcolo_pensione_anagrafica(aid: str, body: dict, user=Depends(current_user)):
    """Esegue il calcolo per i 3 tipi di pensione + GAP di reddito.

    body può sovrascrivere i parametri ricavati dall'anagrafica.
    """
    if user["role"] == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Permesso negato")
    preview = await calcolo_pensione_preview(aid, user)

    settimane = int(body.get("settimane_contributive") or preview["settimane_contributive"] or 0)
    retribuzione = float(body.get("retribuzione_media_annua") or preview.get("reddito_annuo_lordo") or 0)
    eta = int(body.get("eta") or preview["eta"] or 0)
    invalidita = body.get("percentuale_invalidita")
    familiari = int(body.get("numero_familiari") if body.get("numero_familiari") is not None else preview["numero_familiari"])

    risultati = {}
    for tipo in ("invalidita", "inabilita", "superstite"):
        # superstite: se non ha familiari, restituisci 0 con avviso
        if tipo == "superstite" and familiari == 0:
            risultati[tipo] = {
                "pensione_lorda_mensile": 0,
                "pensione_lorda_annua": 0,
                "pensione_netta_stimata": 0,
                "metodologia": "Non spettante (assenza di coniuge/figli a carico)",
                "coefficiente_applicato": 0,
                "dettaglio": {"note": ["Requisiti soggettivi non soddisfatti."]},
            }
            continue
        risultati[tipo] = inps_calculator.calcola_pensione(
            tipo=tipo,
            settimane_contributive=settimane,
            retribuzione_media_annua=retribuzione,
            eta=eta,
            percentuale_invalidita=invalidita,
            numero_familiari=familiari,
        )

    # GAP di reddito: differenza tra reddito attuale e pensione lorda annua per ogni tipo
    gap = {}
    for tipo, r in risultati.items():
        diff = retribuzione - (r.get("pensione_lorda_annua") or 0)
        gap[tipo] = {
            "gap_annuo": round(diff, 2),
            "gap_mensile": round(diff / 12.0, 2),
            "copertura_percentuale": round(((r.get("pensione_lorda_annua") or 0) / retribuzione * 100), 1) if retribuzione else 0,
        }

    # salva storico (un calcolo per il principale - invalidità)
    main = risultati["invalidita"]
    calc = CalcoloPensione(
        anagrafica_id=aid,
        tipo_pensione="invalidita",
        data_inizio_contribuzione="",
        settimane_contributive=settimane,
        retribuzione_media_annua=retribuzione,
        eta_richiedente=eta,
        percentuale_invalidita=invalidita,
        numero_familiari=familiari,
        **main,
    )
    await db.calcoli_pensione.insert_one(calc.model_dump())
    await log_attivita(user, "calc_pensione", "pensione", aid)

    return {
        "anagrafica": preview,
        "parametri_usati": {
            "settimane": settimane, "retribuzione_annua": retribuzione,
            "eta": eta, "familiari": familiari, "invalidita": invalidita,
        },
        "risultati": risultati,
        "gap_reddito": gap,
    }


# ============================================================
# PIPELINE (kanban-like data)
# ============================================================
@api.get("/pipeline/{entita}")
async def pipeline_data(entita: str, user=Depends(current_user)):
    """Ritorna dati per visualizzazione pipeline/kanban.

    entita: 'polizze' | 'sinistri' | 'titoli' | 'clienti' | 'email'
    """
    flt = await visibility_filter(user) if entita in ("polizze", "sinistri") else {}
    if entita == "polizze":
        stages = [
            ("in_emissione", "In emissione"), ("attiva", "Attive"),
            ("sospesa", "Sospese"), ("scaduta", "Scadute"), ("annullata", "Annullate"),
        ]
        items = await db.polizze.find(flt, {"_id": 0}).to_list(5000)
        ana_ids = list({i.get("contraente_id") for i in items})
        anas = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
        com_ids = list({i.get("compagnia_id") for i in items})
        coms = {c["id"]: c async for c in db.compagnie.find({"id": {"$in": com_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
        cols = []
        for stato, label in stages:
            cards = [i for i in items if i.get("stato") == stato]
            cols.append({
                "key": stato, "label": label, "count": len(cards),
                "cards": [{
                    "id": p["id"], "title": p["numero_polizza"],
                    "subtitle": anas.get(p.get("contraente_id", ""), {}).get("ragione_sociale", ""),
                    "footer": coms.get(p.get("compagnia_id", ""), {}).get("ragione_sociale", ""),
                    "extra": f"{p.get('ramo','')} · €{p.get('premio_lordo', 0):.2f}",
                    "date": p.get("scadenza"), "link": f"/polizze/{p['id']}",
                } for p in cards[:50]],
            })
        return {"entita": "polizze", "colonne": cols}

    if entita == "sinistri":
        stages = [
            ("aperto", "Aperti"), ("in_istruttoria", "In istruttoria"),
            ("liquidato", "Liquidati"), ("chiuso_senza_seguito", "Chiusi"), ("respinto", "Respinti"),
        ]
        items = await db.sinistri.find(flt, {"_id": 0}).to_list(5000)
        pol_ids = list({i.get("polizza_id") for i in items})
        pols = {p["id"]: p async for p in db.polizze.find({"id": {"$in": pol_ids}}, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1})}
        ana_ids = list({p.get("contraente_id") for p in pols.values()})
        anas = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
        cols = []
        for stato, label in stages:
            cards = [i for i in items if i.get("stato") == stato]
            cols.append({
                "key": stato, "label": label, "count": len(cards),
                "cards": [{
                    "id": s["id"], "title": s["numero_sinistro"],
                    "subtitle": anas.get(pols.get(s.get("polizza_id",""), {}).get("contraente_id", ""), {}).get("ragione_sociale", ""),
                    "footer": pols.get(s.get("polizza_id", ""), {}).get("numero_polizza", ""),
                    "extra": f"Riserva: €{s.get('riserva', 0):.2f}",
                    "date": s.get("data_avvenimento"), "link": f"/polizze/{s.get('polizza_id')}",
                } for s in cards[:50]],
            })
        return {"entita": "sinistri", "colonne": cols}

    if entita == "titoli":
        stages = [
            ("da_incassare", "Da incassare"), ("insoluto", "Insoluti"),
            ("incassato", "Incassati"), ("stornato", "Stornati"),
        ]
        items = await db.titoli.find({}, {"_id": 0}).to_list(5000)
        pol_ids = list({i.get("polizza_id") for i in items})
        pols = {p["id"]: p async for p in db.polizze.find({"id": {"$in": pol_ids}}, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1})}
        ana_ids = list({p.get("contraente_id") for p in pols.values()})
        anas = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
        cols = []
        for stato, label in stages:
            cards = [i for i in items if i.get("stato") == stato]
            cols.append({
                "key": stato, "label": label, "count": len(cards),
                "cards": [{
                    "id": t["id"],
                    "title": pols.get(t.get("polizza_id",""), {}).get("numero_polizza", "—"),
                    "subtitle": anas.get(pols.get(t.get("polizza_id",""), {}).get("contraente_id",""), {}).get("ragione_sociale", ""),
                    "footer": f"€{t.get('importo_lordo', 0):.2f}",
                    "extra": t.get("tipo", ""),
                    "date": t.get("scadenza"),
                    "link": f"/polizze/{t.get('polizza_id')}",
                } for t in cards[:50]],
            })
        return {"entita": "titoli", "colonne": cols}

    if entita == "clienti":
        # raggruppamento per quantità polizze
        stages = [
            ("prospect", "Prospect (0 polizze)"),
            ("nuovo", "Nuovo (1 polizza)"),
            ("attivo", "Attivo (2-3)"),
            ("top", "Top cliente (4+)"),
        ]
        anas = await db.anagrafiche.find({}, {"_id": 0}).to_list(5000)
        from collections import defaultdict
        counts = defaultdict(int)
        async for p in db.polizze.find({"stato": "attiva"}, {"contraente_id": 1, "_id": 0}):
            counts[p.get("contraente_id", "")] += 1
        cols_data = {k: [] for k, _ in stages}
        for a in anas:
            n = counts.get(a["id"], 0)
            if n == 0: cols_data["prospect"].append(a)
            elif n == 1: cols_data["nuovo"].append(a)
            elif n in (2, 3): cols_data["attivo"].append(a)
            else: cols_data["top"].append(a)
        cols = [{
            "key": k, "label": label, "count": len(cols_data[k]),
            "cards": [{
                "id": a["id"], "title": a["ragione_sociale"],
                "subtitle": f"{a.get('comune', '')} ({a.get('provincia', '')})" if a.get("comune") else "",
                "footer": a.get("email") or a.get("cellulare") or "",
                "extra": f"{counts.get(a['id'], 0)} polizze attive",
                "link": f"/anagrafiche/{a['id']}",
            } for a in cols_data[k][:50]],
        } for k, label in stages]
        return {"entita": "clienti", "colonne": cols}

    raise HTTPException(400, "Entità pipeline non supportata")


# ============================================================
# EMAIL PIPELINE
# ============================================================
@api.get("/email")
async def list_email(stato: Optional[str] = None, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    flt: dict = {}
    if stato:
        flt["stato"] = stato
    items = await db.email.find(flt, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api.post("/email", status_code=201)
async def create_email(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["autore_id"] = user["id"]
    obj = EmailMessaggio(**body)
    await db.email.insert_one(obj.model_dump())
    await log_attivita(user, "create", "email", obj.id, f"Email a {obj.destinatario_email}")
    return obj.model_dump()


@api.post("/email/{eid}/invia")
async def invia_email(eid: str, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Invio email (MOCK - non invia realmente, marca come inviata)."""
    res = await db.email.update_one(
        {"id": eid},
        {"$set": {"stato": "inviata", "data_invio": _now_iso(), "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Non trovata")
    await log_attivita(user, "invio", "email", eid, "Email inviata (mock)")
    return {"ok": True, "note": "Invio simulato. Configurare SMTP per invio reale."}


@api.post("/email/avvisi-scadenze")
async def genera_avvisi_scadenze(giorni: int = 30, user=Depends(require_user("admin", "collaboratore"))):
    """Genera email di avviso per polizze in scadenza nei prossimi N giorni."""
    from datetime import date, timedelta
    oggi = date.today()
    limite = (oggi + timedelta(days=giorni)).isoformat()
    polizze = await db.polizze.find(
        {"stato": "attiva", "scadenza": {"$gte": oggi.isoformat(), "$lte": limite}},
        {"_id": 0},
    ).to_list(1000)
    creati = 0
    for p in polizze:
        ana = await db.anagrafiche.find_one({"id": p["contraente_id"]}, {"_id": 0})
        if not ana or not ana.get("email"):
            continue
        email = EmailMessaggio(
            destinatario_anagrafica_id=ana["id"],
            destinatario_email=ana["email"],
            oggetto=f"Promemoria scadenza polizza {p['numero_polizza']}",
            corpo=(f"Gentile {ana['ragione_sociale']},\n\n"
                   f"la informiamo che la sua polizza n. {p['numero_polizza']} "
                   f"({p['ramo']}) scadrà il {p['scadenza']}.\n\n"
                   f"La invitiamo a contattarci per il rinnovo.\n\n"
                   f"Cordiali saluti."),
            template="scadenza_polizza",
            stato="in_coda",
            polizza_id=p["id"],
            autore_id=user["id"],
        )
        await db.email.insert_one(email.model_dump())
        creati += 1
    await log_attivita(user, "genera_avvisi", "email", None,
                       f"Generati {creati} avvisi di scadenza")
    return {"avvisi_creati": creati}


# ============================================================
# ATTIVITA LOG
# ============================================================
@api.get("/attivita")
async def list_attivita(
    entita: Optional[str] = None,
    utente_id: Optional[str] = None,
    limit: int = 200,
    user=Depends(require_user("admin", "collaboratore")),
):
    flt: dict = {}
    if entita:
        flt["entita"] = entita
    if utente_id:
        flt["utente_id"] = utente_id
    items = await db.attivita_log.find(flt, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


# ============================================================
# STATISTICHE / DASHBOARD
# ============================================================
@api.get("/stats/dashboard")
async def stats_dashboard(user=Depends(current_user)):
    flt = await visibility_filter(user)
    today = _now_iso()[:10]
    from datetime import date, timedelta
    sessanta_gg = (date.today() + timedelta(days=60)).isoformat()

    n_anagrafiche = await db.anagrafiche.count_documents({} if user["role"] != "cliente" else {"id": user.get("anagrafica_id", "_none_")})
    n_polizze = await db.polizze.count_documents(flt)
    polizze_attive = await db.polizze.count_documents({**flt, "stato": "attiva"})
    in_scadenza = await db.polizze.count_documents({
        **flt, "stato": "attiva",
        "scadenza": {"$gte": today, "$lte": sessanta_gg},
    })
    sinistri_aperti = await db.sinistri.count_documents({**flt, "stato": {"$in": ["aperto", "in_istruttoria"]}})

    # Premi incassati (anno corrente) - filtra per cliente se necessario
    anno = today[:4]
    pol_match = {}
    if user["role"] == "cliente" and user.get("anagrafica_id"):
        cli_pol_ids = [p["id"] async for p in db.polizze.find(
            {"contraente_id": user["anagrafica_id"]}, {"_id": 0, "id": 1})]
        pol_match = {"polizza_id": {"$in": cli_pol_ids}}

    pipeline = [
        {"$match": {**pol_match, "stato": "incassato", "data_incasso": {"$regex": f"^{anno}"}}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo_lordo"}}},
    ]
    cur = db.titoli.aggregate(pipeline)
    res = await cur.to_list(1)
    premi_anno = res[0]["totale"] if res else 0.0

    # Distribuzione polizze per ramo
    pipeline_ramo = [
        {"$match": flt},
        {"$group": {"_id": "$ramo", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    rami = await db.polizze.aggregate(pipeline_ramo).to_list(20)

    # Incassi ultimi 6 mesi
    from datetime import date
    sei_mesi = []
    for i in range(5, -1, -1):
        d = date.today().replace(day=1)
        # naive: scendi di i mesi
        m = d.month - i
        y = d.year
        while m <= 0:
            m += 12
            y -= 1
        mese = f"{y}-{m:02d}"
        agg = await db.titoli.aggregate([
            {"$match": {**pol_match, "stato": "incassato", "data_incasso": {"$regex": f"^{mese}"}}},
            {"$group": {"_id": None, "totale": {"$sum": "$importo_lordo"}}},
        ]).to_list(1)
        sei_mesi.append({"mese": mese, "totale": round(agg[0]["totale"], 2) if agg else 0.0})

    return {
        "anagrafiche": n_anagrafiche,
        "polizze_totali": n_polizze,
        "polizze_attive": polizze_attive,
        "polizze_in_scadenza": in_scadenza,
        "sinistri_aperti": sinistri_aperti,
        "premi_anno_corrente": round(premi_anno, 2),
        "polizze_per_ramo": [{"ramo": r["_id"] or "N/D", "count": r["count"]} for r in rami],
        "incassi_mensili": sei_mesi,
    }


# ============================================================
# LIBRERIE: Banche, Conti cassa, Prodotti, Rami
# ============================================================
def _libreria_routes(coll_name: str, model_cls, ruoli_modifica=("admin", "collaboratore")):
    """Crea endpoint CRUD standard per una collezione di libreria."""
    pass  # implementato direttamente sotto per ogni risorsa


# --- BANCHE ---
@api.get("/librerie/banche")
async def list_banche(user=Depends(current_user)):
    return await db.banche.find({}, {"_id": 0}).sort("nome", 1).to_list(500)


@api.post("/librerie/banche", status_code=201)
async def create_banca(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    obj = Banca(**body)
    await db.banche.insert_one(obj.model_dump())
    await log_attivita(user, "create", "banca", obj.id, obj.nome)
    return obj.model_dump()


@api.put("/librerie/banche/{bid}")
async def update_banca(bid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    body["updated_at"] = _now_iso()
    res = await db.banche.update_one({"id": bid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Banca non trovata")
    await log_attivita(user, "update", "banca", bid)
    return strip_mongo_id(await db.banche.find_one({"id": bid}, {"_id": 0}))


@api.delete("/librerie/banche/{bid}")
async def delete_banca(bid: str, user=Depends(require_user("admin"))):
    await db.banche.delete_one({"id": bid})
    await log_attivita(user, "delete", "banca", bid)
    return {"ok": True}


# --- CONTI CASSA ---
@api.get("/librerie/conti-cassa")
async def list_conti(attivi: Optional[bool] = None, user=Depends(current_user)):
    flt = {}
    if attivi is not None:
        flt["attivo"] = attivi
    return await db.conti_cassa.find(flt, {"_id": 0}).sort("ordine", 1).to_list(500)


@api.post("/librerie/conti-cassa", status_code=201)
async def create_conto(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    obj = ContoCassa(**body)
    await db.conti_cassa.insert_one(obj.model_dump())
    await log_attivita(user, "create", "conto_cassa", obj.id, obj.nome)
    return obj.model_dump()


@api.put("/librerie/conti-cassa/{cid}")
async def update_conto(cid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    body["updated_at"] = _now_iso()
    res = await db.conti_cassa.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Conto non trovato")
    await log_attivita(user, "update", "conto_cassa", cid)
    return strip_mongo_id(await db.conti_cassa.find_one({"id": cid}, {"_id": 0}))


@api.delete("/librerie/conti-cassa/{cid}")
async def delete_conto(cid: str, user=Depends(require_user("admin"))):
    await db.conti_cassa.delete_one({"id": cid})
    await log_attivita(user, "delete", "conto_cassa", cid)
    return {"ok": True}


# --- PRODOTTI ---
@api.get("/librerie/prodotti")
async def list_prodotti(compagnia_id: Optional[str] = None, user=Depends(current_user)):
    flt = {}
    if compagnia_id:
        flt["compagnia_id"] = compagnia_id
    return await db.prodotti.find(flt, {"_id": 0}).sort("nome", 1).to_list(1000)


@api.post("/librerie/prodotti", status_code=201)
async def create_prodotto(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    obj = ProdottoLibreria(**body)
    await db.prodotti.insert_one(obj.model_dump())
    await log_attivita(user, "create", "prodotto", obj.id, obj.nome)
    return obj.model_dump()


@api.put("/librerie/prodotti/{pid}")
async def update_prodotto(pid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    body["updated_at"] = _now_iso()
    res = await db.prodotti.update_one({"id": pid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    await log_attivita(user, "update", "prodotto", pid)
    return strip_mongo_id(await db.prodotti.find_one({"id": pid}, {"_id": 0}))


@api.delete("/librerie/prodotti/{pid}")
async def delete_prodotto(pid: str, user=Depends(require_user("admin"))):
    await db.prodotti.delete_one({"id": pid})
    await log_attivita(user, "delete", "prodotto", pid)
    return {"ok": True}


# --- RAMI ---
@api.get("/librerie/rami")
async def list_rami(user=Depends(current_user)):
    return await db.rami.find({}, {"_id": 0}).sort("nome", 1).to_list(200)


@api.post("/librerie/rami", status_code=201)
async def create_ramo(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    obj = RamoLibreria(**body)
    await db.rami.insert_one(obj.model_dump())
    await log_attivita(user, "create", "ramo", obj.id, obj.nome)
    return obj.model_dump()


@api.put("/librerie/rami/{rid}")
async def update_ramo(rid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    body["updated_at"] = _now_iso()
    res = await db.rami.update_one({"id": rid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Ramo non trovato")
    return strip_mongo_id(await db.rami.find_one({"id": rid}, {"_id": 0}))


@api.delete("/librerie/rami/{rid}")
async def delete_ramo(rid: str, user=Depends(require_user("admin"))):
    await db.rami.delete_one({"id": rid})
    return {"ok": True}


# ============================================================
# DIARIO CLIENTE
# ============================================================
@api.get("/anagrafiche/{aid}/diario")
async def list_diario(aid: str, user=Depends(current_user)):
    if user["role"] == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Permesso negato")
    items = await db.diario.find({"anagrafica_id": aid}, {"_id": 0}).sort("data_evento", -1).to_list(500)
    return items


@api.post("/anagrafiche/{aid}/diario", status_code=201)
async def create_diario(aid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["anagrafica_id"] = aid
    body["autore_id"] = user["id"]
    body["autore_nome"] = user.get("name")
    obj = DiarioVoce(**body)
    await db.diario.insert_one(obj.model_dump())
    await log_attivita(user, "create", "diario", obj.id, obj.titolo)
    return obj.model_dump()


@api.put("/diario/{did}")
async def update_diario(did: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body["updated_at"] = _now_iso()
    res = await db.diario.update_one({"id": did}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Voce non trovata")
    return strip_mongo_id(await db.diario.find_one({"id": did}, {"_id": 0}))


@api.delete("/diario/{did}")
async def delete_diario(did: str, user=Depends(require_user("admin", "collaboratore"))):
    await db.diario.delete_one({"id": did})
    return {"ok": True}


# ============================================================
# ALLEGATI (object storage)
# ============================================================
@api.get("/allegati")
async def list_allegati(
    entita_tipo: str, entita_id: str,
    user=Depends(current_user),
):
    items = await db.allegati.find(
        {"entita_tipo": entita_tipo, "entita_id": entita_id, "is_deleted": False},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return items


@api.post("/allegati", status_code=201)
async def upload_allegato(
    entita_tipo: str = Query(...),
    entita_id: str = Query(...),
    descrizione: Optional[str] = Query(None),
    file: UploadFile = File(...),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    if entita_tipo not in ("anagrafica", "polizza", "sinistro", "compagnia", "corso", "movimento"):
        raise HTTPException(400, "Tipo entità non valido")
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 25 MB)")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    file_id = _uid()
    path = f"{os.environ.get('APP_NAME', 'assicura')}/{entita_tipo}/{entita_id}/{file_id}.{ext}"
    content_type = file.content_type or obj_storage.mime_for(file.filename or "")
    try:
        result = obj_storage.put_object(path, data, content_type)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    obj = Allegato(
        entita_tipo=entita_tipo, entita_id=entita_id,
        nome_file=file.filename, storage_path=result["path"],
        content_type=content_type, size=result.get("size", len(data)),
        descrizione=descrizione, autore_id=user["id"],
    )
    await db.allegati.insert_one(obj.model_dump())
    await log_attivita(user, "upload", "allegato", obj.id, f"{file.filename} su {entita_tipo}:{entita_id}")
    return obj.model_dump()


@api.get("/allegati/{aid}/download")
async def download_allegato(aid: str, user=Depends(current_user)):
    rec = await db.allegati.find_one({"id": aid, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Allegato non trovato")
    # ACL su cliente: vede solo allegati relativi alla sua anagrafica/polizze/sinistri
    if user["role"] == "cliente":
        ok = False
        if rec["entita_tipo"] == "anagrafica" and rec["entita_id"] == user.get("anagrafica_id"):
            ok = True
        elif rec["entita_tipo"] in ("polizza", "sinistro"):
            target = await db.polizze.find_one({"id": rec["entita_id"]}, {"_id": 0, "contraente_id": 1}) \
                if rec["entita_tipo"] == "polizza" else \
                await db.sinistri.find_one({"id": rec["entita_id"]}, {"_id": 0, "contraente_id": 1})
            ok = target and target.get("contraente_id") == user.get("anagrafica_id")
        if not ok:
            raise HTTPException(403, "Permesso negato")
    try:
        data, ctype = obj_storage.get_object(rec["storage_path"])
    except Exception as e:
        raise HTTPException(503, f"Errore download: {e}")
    return StreamingResponse(
        _io.BytesIO(data),
        media_type=rec.get("content_type") or ctype,
        headers={"Content-Disposition": f'inline; filename="{rec["nome_file"]}"'},
    )


@api.delete("/allegati/{aid}")
async def delete_allegato(aid: str, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    res = await db.allegati.update_one({"id": aid}, {"$set": {"is_deleted": True, "updated_at": _now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Allegato non trovato")
    await log_attivita(user, "delete", "allegato", aid)
    return {"ok": True}


# ============================================================
# CHAT INTERNA
# ============================================================
@api.get("/chat/utenti")
async def chat_utenti(user=Depends(current_user)):
    """Restituisce gli utenti con cui posso chattare."""
    if user["role"] == "cliente":
        flt = {"role": {"$in": ["admin", "collaboratore", "dipendente"]}}
    else:
        flt = {"id": {"$ne": user["id"]}}
    users = await db.users.find(flt, {"_id": 0, "password_hash": 0}).sort("name", 1).to_list(500)
    # arricchisci con count non letti e ultimo messaggio
    for u in users:
        unread = await db.chat.count_documents(
            {"destinatario_id": user["id"], "mittente_id": u["id"], "letto": False}
        )
        u["unread"] = unread
        last = await db.chat.find_one(
            {"$or": [
                {"mittente_id": user["id"], "destinatario_id": u["id"]},
                {"mittente_id": u["id"], "destinatario_id": user["id"]},
            ]},
            {"_id": 0, "testo": 1, "created_at": 1},
            sort=[("created_at", -1)],
        )
        u["ultimo_messaggio"] = last
    return users


@api.get("/chat/messaggi")
async def chat_messaggi(con: str, limit: int = 200, user=Depends(current_user)):
    """Messaggi della conversazione con un altro utente."""
    items = await db.chat.find(
        {"$or": [
            {"mittente_id": user["id"], "destinatario_id": con},
            {"mittente_id": con, "destinatario_id": user["id"]},
        ]},
        {"_id": 0},
    ).sort("created_at", 1).to_list(limit)
    # marca come letti i messaggi a me
    await db.chat.update_many(
        {"mittente_id": con, "destinatario_id": user["id"], "letto": False},
        {"$set": {"letto": True, "letto_at": _now_iso()}},
    )
    return items


@api.post("/chat/messaggi", status_code=201)
async def chat_invia(
    destinatario_id: str = Query(None),
    testo: str = Query(""),
    file: Optional[UploadFile] = File(None),
    body: Optional[dict] = None,
    user=Depends(current_user),
):
    # supporta sia JSON (body) che multipart (con file)
    if body is None:
        try:
            from fastapi import Request as _Req
            pass
        except Exception:
            pass
    # multipart: prendi destinatario_id e testo dai query/form param
    dest_id = destinatario_id or (body or {}).get("destinatario_id")
    txt = testo or (body or {}).get("testo", "")
    if not dest_id:
        raise HTTPException(400, "destinatario_id richiesto")
    if not txt.strip() and not file:
        raise HTTPException(400, "Testo o allegato richiesto")
    dest = await db.users.find_one({"id": dest_id}, {"_id": 0})
    if not dest:
        raise HTTPException(404, "Destinatario non trovato")
    if user["role"] == "cliente" and dest.get("role") == "cliente":
        raise HTTPException(403, "I clienti possono scrivere solo allo staff")

    allegato_id = allegato_nome = allegato_ct = None
    if file:
        data = await file.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(400, "File troppo grande (max 25 MB)")
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
        file_id = _uid()
        path = f"{os.environ.get('APP_NAME', 'assicura')}/chat/{user['id']}/{file_id}.{ext}"
        ct = file.content_type or obj_storage.mime_for(file.filename or "")
        try:
            result = obj_storage.put_object(path, data, ct)
        except Exception as e:
            raise HTTPException(503, f"Errore upload: {e}")
        al = Allegato(
            entita_tipo="anagrafica", entita_id=dest_id,  # uso anagrafica come fallback
            nome_file=file.filename, storage_path=result["path"],
            content_type=ct, size=result.get("size", len(data)),
            descrizione=f"Allegato chat tra {user.get('name')} e {dest.get('name')}",
            autore_id=user["id"],
        )
        await db.allegati.insert_one(al.model_dump())
        allegato_id = al.id
        allegato_nome = file.filename
        allegato_ct = ct

    msg = MessaggioChat(
        mittente_id=user["id"], mittente_nome=user.get("name", ""),
        destinatario_id=dest_id, destinatario_nome=dest.get("name", ""),
        testo=txt, allegato_id=allegato_id, allegato_nome=allegato_nome,
        allegato_content_type=allegato_ct,
    )
    await db.chat.insert_one(msg.model_dump())
    return msg.model_dump()


@api.get("/notifiche/sommario")
async def notifiche_sommario(user=Depends(current_user)):
    """Aggrega notifiche per il badge in sidebar."""
    chat_unread = await db.chat.count_documents({"destinatario_id": user["id"], "letto": False})
    res = {"chat": chat_unread, "totale": chat_unread}
    if user["role"] in ("admin", "collaboratore", "dipendente"):
        from datetime import date, timedelta
        oggi = date.today().isoformat()
        in_scad = (date.today() + timedelta(days=15)).isoformat()
        polizze_scad = await db.polizze.count_documents({
            "stato": "attiva", "scadenza": {"$gte": oggi, "$lte": in_scad},
        })
        titoli_scaduti = await db.titoli.count_documents({
            "stato": {"$in": ["da_incassare", "insoluto"]}, "scadenza": {"$lt": oggi},
        })
        email_coda = await db.email.count_documents({"stato": "in_coda"})
        sinistri_aperti = await db.sinistri.count_documents({"stato": "aperto"})
        res["polizze_scadenza"] = polizze_scad
        res["titoli_scaduti"] = titoli_scaduti
        res["email_coda"] = email_coda
        res["sinistri_aperti"] = sinistri_aperti
        res["totale"] = chat_unread + polizze_scad + titoli_scaduti + sinistri_aperti
    return res


@api.get("/search")
async def search_globale(q: str, limit: int = 8, user=Depends(current_user)):
    """Ricerca rapida cross-entità per la barra in alto."""
    if not q or len(q.strip()) < 2:
        return {"anagrafiche": [], "polizze": [], "sinistri": [], "titoli": []}
    qrx = {"$regex": q.strip(), "$options": "i"}
    is_client = user["role"] == "cliente"
    ana_filter = {"id": user.get("anagrafica_id")} if is_client else {
        "$or": [{"ragione_sociale": qrx}, {"codice_fiscale": qrx}, {"partita_iva": qrx}, {"email": qrx}]
    }
    anas = await db.anagrafiche.find(
        ana_filter, {"_id": 0, "id": 1, "ragione_sociale": 1, "codice_fiscale": 1, "comune": 1}
    ).limit(limit).to_list(limit)

    pol_filter = {"$or": [{"numero_polizza": qrx}, {"targa": qrx}]}
    if is_client:
        pol_filter = {"$and": [pol_filter, {"contraente_id": user.get("anagrafica_id")}]}
    polizze = await db.polizze.find(
        pol_filter, {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "stato": 1, "targa": 1, "contraente_id": 1}
    ).limit(limit).to_list(limit)
    # arricchisci con contraente
    ana_ids = [p.get("contraente_id") for p in polizze if p.get("contraente_id")]
    ana_map = {a["id"]: a["ragione_sociale"] async for a in db.anagrafiche.find(
        {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    for p in polizze:
        p["contraente_nome"] = ana_map.get(p.get("contraente_id", ""))

    sin_filter = {"numero_sinistro": qrx}
    if is_client:
        sin_filter = {"$and": [sin_filter, {"contraente_id": user.get("anagrafica_id")}]}
    sinistri = await db.sinistri.find(
        sin_filter, {"_id": 0, "id": 1, "numero_sinistro": 1, "polizza_id": 1, "stato": 1, "data_avvenimento": 1}
    ).limit(limit).to_list(limit)

    return {
        "anagrafiche": anas, "polizze": polizze, "sinistri": sinistri, "titoli": [],
    }


@api.get("/chat/unread")
async def chat_unread(user=Depends(current_user)):
    n = await db.chat.count_documents({"destinatario_id": user["id"], "letto": False})
    return {"unread": n}


# ============================================================
# CORSI
# ============================================================
@api.get("/corsi")
async def list_corsi(user=Depends(current_user)):
    flt: dict = {"pubblicato": True}
    if user["role"] != "admin":
        flt["$or"] = [
            {"visibile_ruoli": user["role"]},
            {"visibile_utenti": user["id"]},
        ]
    items = await db.corsi.find(flt, {"_id": 0}).sort("created_at", -1).to_list(500)
    # arricchisci con progresso utente
    ids = [c["id"] for c in items]
    progressi = {p["corso_id"]: p async for p in db.progressi_corso.find(
        {"corso_id": {"$in": ids}, "utente_id": user["id"]}, {"_id": 0})}
    for c in items:
        c["progresso"] = progressi.get(c["id"])
    return items


@api.get("/corsi/{cid}")
async def get_corso(cid: str, user=Depends(current_user)):
    doc = await db.corsi.find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Corso non trovato")
    # check visibility
    if user["role"] != "admin":
        ok = user["role"] in (doc.get("visibile_ruoli") or []) or user["id"] in (doc.get("visibile_utenti") or [])
        if not ok:
            raise HTTPException(403, "Corso non visibile")
    doc["progresso"] = await db.progressi_corso.find_one(
        {"corso_id": cid, "utente_id": user["id"]}, {"_id": 0}
    )
    return doc


@api.post("/corsi", status_code=201)
async def create_corso(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    body["autore_id"] = user["id"]
    obj = Corso(**body)
    await db.corsi.insert_one(obj.model_dump())
    await log_attivita(user, "create", "corso", obj.id, obj.titolo)
    return obj.model_dump()


@api.put("/corsi/{cid}")
async def update_corso(cid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    body["updated_at"] = _now_iso()
    res = await db.corsi.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Corso non trovato")
    return strip_mongo_id(await db.corsi.find_one({"id": cid}, {"_id": 0}))


@api.delete("/corsi/{cid}")
async def delete_corso(cid: str, user=Depends(require_user("admin"))):
    await db.corsi.delete_one({"id": cid})
    await db.progressi_corso.delete_many({"corso_id": cid})
    return {"ok": True}


@api.post("/corsi/{cid}/progresso")
async def upsert_progresso(cid: str, body: dict, user=Depends(current_user)):
    """body: {secondi_visti, durata_totale_sec, ultima_posizione_sec}"""
    pos = int(body.get("ultima_posizione_sec", 0))
    dur = int(body.get("durata_totale_sec", 0))
    seen = int(body.get("secondi_visti", pos))
    perc = (seen / dur * 100.0) if dur > 0 else 0.0
    completato = perc >= 95.0
    existing = await db.progressi_corso.find_one({"corso_id": cid, "utente_id": user["id"]}, {"_id": 0})
    if existing:
        new_seen = max(existing.get("secondi_visti", 0), seen)
        new_dur = max(existing.get("durata_totale_sec", 0), dur)
        new_perc = (new_seen / new_dur * 100.0) if new_dur > 0 else 0.0
        await db.progressi_corso.update_one(
            {"id": existing["id"]},
            {"$set": {
                "secondi_visti": new_seen, "durata_totale_sec": new_dur,
                "percentuale": round(new_perc, 1), "completato": new_perc >= 95.0,
                "ultima_posizione_sec": pos,
                "ultima_visualizzazione": _now_iso(), "updated_at": _now_iso(),
            }},
        )
        return await db.progressi_corso.find_one({"id": existing["id"]}, {"_id": 0})
    obj = ProgressoCorso(
        corso_id=cid, utente_id=user["id"], secondi_visti=seen,
        durata_totale_sec=dur, percentuale=round(perc, 1),
        completato=completato, ultima_posizione_sec=pos,
    )
    await db.progressi_corso.insert_one(obj.model_dump())
    return obj.model_dump()


@api.get("/corsi/{cid}/progressi")
async def list_progressi(cid: str, user=Depends(require_user("admin", "collaboratore"))):
    """Stato di avanzamento di tutti gli utenti su un corso."""
    items = await db.progressi_corso.find({"corso_id": cid}, {"_id": 0}).to_list(2000)
    uids = list({p["utente_id"] for p in items})
    users = {u["id"]: u async for u in db.users.find(
        {"id": {"$in": uids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1})}
    for p in items:
        u = users.get(p["utente_id"], {})
        p["utente_nome"] = u.get("name")
        p["utente_email"] = u.get("email")
        p["utente_ruolo"] = u.get("role")
    return items


# ============================================================
# GEOLOCALIZZAZIONE
# ============================================================
@api.get("/geo/anagrafiche")
async def geo_anagrafiche(user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Restituisce solo anagrafiche con lat/lng valide."""
    items = await db.anagrafiche.find(
        {"lat": {"$ne": None}, "lng": {"$ne": None}},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "comune": 1, "provincia": 1,
         "indirizzo": 1, "lat": 1, "lng": 1, "telefono": 1, "cellulare": 1, "email": 1},
    ).to_list(5000)
    return items


@api.post("/geo/anagrafiche/{aid}/geocode")
async def geocode_anagrafica(aid: str, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Geocoding gratuito con Nominatim (OpenStreetMap)."""
    import requests as _rq
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    parts = [ana.get("indirizzo"), ana.get("cap"), ana.get("comune"), ana.get("provincia"), ana.get("nazione") or "Italia"]
    q = ", ".join([p for p in parts if p])
    if not q:
        raise HTTPException(400, "Indirizzo insufficiente per geocoding")
    try:
        r = _rq.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": 1, "countrycodes": "it"},
            headers={"User-Agent": "AssicuraApp/1.0"}, timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(503, f"Geocoding fallito: {e}")
    if not data:
        return {"found": False, "query": q}
    lat = float(data[0]["lat"]); lng = float(data[0]["lon"])
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$set": {"lat": lat, "lng": lng, "indirizzo_geocoded": data[0].get("display_name"),
                  "updated_at": _now_iso()}},
    )
    return {"found": True, "lat": lat, "lng": lng, "address": data[0].get("display_name")}


# ============================================================
# STAMPE PDF
# ============================================================
def _pdf_response(pdf_bytes: bytes, filename: str):
    return StreamingResponse(
        _io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@api.get("/stampa/anagrafiche")
async def stampa_anagrafiche(q: Optional[str] = None, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    flt = {}
    if q:
        flt["$or"] = [
            {"ragione_sociale": {"$regex": q, "$options": "i"}},
            {"codice_fiscale": {"$regex": q, "$options": "i"}},
        ]
    items = await db.anagrafiche.find(flt, {"_id": 0}).sort("ragione_sociale", 1).to_list(5000)
    headers = ["Ragione sociale", "CF / P.IVA", "Tipo", "Comune", "Email", "Telefono", "Cellulare"]
    rows = [[a["ragione_sociale"], a.get("codice_fiscale") or a.get("partita_iva") or "",
             "PG" if a.get("tipo") == "persona_giuridica" else "PF",
             f"{a.get('comune','')} ({a.get('provincia','')})" if a.get("comune") else "",
             a.get("email") or "", a.get("telefono") or "", a.get("cellulare") or ""] for a in items]
    pdf = pdf_report.stampa_elenco(
        "Elenco Anagrafiche", f"{len(items)} clienti", headers, rows,
        col_widths_mm=[60, 35, 12, 45, 45, 35, 35],
        filtri_attivi={"Ricerca": q} if q else None,
    )
    return _pdf_response(pdf, "anagrafiche.pdf")


@api.get("/stampa/polizze")
async def stampa_polizze(
    stato: Optional[str] = None, compagnia_id: Optional[str] = None,
    ramo: Optional[str] = None, collaboratore_id: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    flt = await visibility_filter(user)
    if stato: flt["stato"] = stato
    if compagnia_id: flt["compagnia_id"] = compagnia_id
    if ramo: flt["ramo"] = ramo
    if collaboratore_id: flt["collaboratore_id"] = collaboratore_id
    items = await db.polizze.find(flt, {"_id": 0}).sort("scadenza", 1).to_list(5000)
    ana_ids = list({i["contraente_id"] for i in items if i.get("contraente_id")})
    com_ids = list({i["compagnia_id"] for i in items if i.get("compagnia_id")})
    anas = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    coms = {c["id"]: c async for c in db.compagnie.find({"id": {"$in": com_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    headers = ["N. polizza", "Contraente", "Compagnia", "Ramo", "Stato", "Effetto", "Scadenza", "Premio €"]
    rows = [[p["numero_polizza"],
             anas.get(p.get("contraente_id",""), {}).get("ragione_sociale", ""),
             coms.get(p.get("compagnia_id",""), {}).get("ragione_sociale", ""),
             p.get("ramo",""), p.get("stato",""), p.get("effetto",""), p.get("scadenza",""),
             p.get("premio_lordo", 0)] for p in items]
    pdf = pdf_report.stampa_elenco(
        "Elenco Polizze", f"{len(items)} polizze", headers, rows,
        col_widths_mm=[35, 55, 50, 25, 22, 22, 22, 25],
        filtri_attivi={"Stato": stato, "Ramo": ramo, "Compagnia": compagnia_id},
    )
    return _pdf_response(pdf, "polizze.pdf")


@api.get("/stampa/titoli")
async def stampa_titoli(
    stato: Optional[str] = None, in_scadenza_giorni: Optional[int] = None,
    coperti_non_pagati: Optional[bool] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    # riusa la logica list_titoli replicando i filtri base
    flt: dict = {}
    if stato: flt["stato"] = stato
    from datetime import date, timedelta
    today = date.today().isoformat()
    if in_scadenza_giorni is not None:
        limite = (date.today() + timedelta(days=int(in_scadenza_giorni))).isoformat()
        flt["stato"] = {"$in": ["da_incassare", "insoluto"]}
        flt["scadenza"] = {"$gte": today, "$lte": limite}
    if coperti_non_pagati:
        flt["stato"] = {"$in": ["da_incassare", "insoluto"]}
        flt["effetto"] = {"$lte": today}
        flt["scadenza"] = {"$gte": today}
    items = await db.titoli.find(flt, {"_id": 0}).sort("scadenza", 1).to_list(5000)
    pol_ids = list({t["polizza_id"] for t in items})
    pols = {p["id"]: p async for p in db.polizze.find({"id": {"$in": pol_ids}}, {"_id": 0})}
    ana_ids = list({p.get("contraente_id") for p in pols.values() if p.get("contraente_id")})
    anas = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    headers = ["Polizza", "Contraente", "Ramo", "Tipo", "Effetto", "Scadenza", "Stato", "Lordo €", "Provv. €"]
    rows = []
    for t in items:
        p = pols.get(t["polizza_id"], {})
        rows.append([
            p.get("numero_polizza", ""),
            anas.get(p.get("contraente_id",""), {}).get("ragione_sociale", ""),
            p.get("ramo", ""), t.get("tipo", ""),
            t.get("effetto", ""), t.get("scadenza", ""), t.get("stato", ""),
            t.get("importo_lordo", 0), t.get("provvigioni", 0),
        ])
    pdf = pdf_report.stampa_elenco(
        "Elenco Titoli",
        f"{len(items)} titoli" + (" - in scadenza" if in_scadenza_giorni else "") + (" - coperti non pagati" if coperti_non_pagati else ""),
        headers, rows,
        col_widths_mm=[32, 55, 25, 22, 22, 22, 25, 25, 25],
    )
    return _pdf_response(pdf, "titoli.pdf")


@api.get("/stampa/sinistri")
async def stampa_sinistri(stato: Optional[str] = None,
                          user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    flt = await visibility_filter(user)
    if stato: flt["stato"] = stato
    items = await db.sinistri.find(flt, {"_id": 0}).sort("data_avvenimento", -1).to_list(5000)
    pol_ids = list({s["polizza_id"] for s in items if s.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find({"id": {"$in": pol_ids}}, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1})}
    ana_ids = list({p.get("contraente_id") for p in pols.values()})
    anas = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    headers = ["N. sinistro", "Polizza", "Contraente", "Avvenimento", "Denuncia", "Stato", "Riserva €", "Liquidato €"]
    rows = []
    for s in items:
        p = pols.get(s.get("polizza_id", ""), {})
        rows.append([s["numero_sinistro"], p.get("numero_polizza", ""),
                     anas.get(p.get("contraente_id", ""), {}).get("ragione_sociale", ""),
                     s.get("data_avvenimento", ""), s.get("data_denuncia", ""),
                     s.get("stato", ""), s.get("riserva", 0), s.get("liquidazione", 0)])
    pdf = pdf_report.stampa_elenco(
        "Elenco Sinistri", f"{len(items)} sinistri", headers, rows,
        col_widths_mm=[30, 32, 55, 25, 25, 25, 28, 28],
    )
    return _pdf_response(pdf, "sinistri.pdf")


@api.get("/stampa/prima-nota")
async def stampa_prima_nota(dal: Optional[str] = None, al: Optional[str] = None,
                            user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    flt: dict = {}
    if dal or al:
        cond = {}
        if dal: cond["$gte"] = dal
        if al: cond["$lte"] = al
        flt["data_movimento"] = cond
    items = await db.movimenti.find(flt, {"_id": 0}).sort("data_movimento", 1).to_list(5000)
    headers = ["Data", "Tipo", "Categoria", "Descrizione", "Mezzo", "Entrata €", "Uscita €"]
    rows = []
    for m in items:
        rows.append([m.get("data_movimento", ""), m.get("tipo", ""), m.get("categoria", ""),
                     (m.get("descrizione") or "")[:60], m.get("mezzo_pagamento") or "",
                     m["importo"] if m["tipo"] == "entrata" else "",
                     m["importo"] if m["tipo"] == "uscita" else ""])
    sub = f"Periodo: {dal or '—'} → {al or '—'}"
    pdf = pdf_report.stampa_elenco(
        "Prima Nota", sub, headers, rows,
        col_widths_mm=[25, 18, 35, 90, 35, 28, 28],
    )
    return _pdf_response(pdf, "prima_nota.pdf")


@api.get("/stampa/brogliaccio")
async def stampa_brogliaccio(data: str, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Brogliaccio del giorno (stile Schiantarelli)."""
    conti = await db.conti_cassa.find({"attivo": True}, {"_id": 0}).sort("ordine", 1).to_list(50)
    pdf = await brog.genera_brogliaccio_pdf(db, data, conti)
    return _pdf_response(pdf, f"brogliaccio_{data}.pdf")


@api.get("/stampa/estratto-conto/{aid}")
async def stampa_estratto_conto(aid: str, user=Depends(current_user)):
    if user["role"] == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Permesso negato")
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    movs = await db.movimenti.find({"anagrafica_id": aid}, {"_id": 0}).sort("data_movimento", 1).to_list(5000)
    saldo = 0.0
    headers = ["Data", "Descrizione", "Dare €", "Avere €", "Saldo €"]
    rows = []
    for m in movs:
        delta = m["importo"] if m["tipo"] == "entrata" else -m["importo"]
        saldo += delta
        rows.append([m["data_movimento"], (m.get("descrizione") or "")[:80],
                     m["importo"] if m["tipo"] == "entrata" else "",
                     m["importo"] if m["tipo"] == "uscita" else "",
                     round(saldo, 2)])
    rows.append(["", "SALDO FINALE", "", "", round(saldo, 2)])
    pdf = pdf_report.stampa_elenco(
        f"Estratto conto - {ana['ragione_sociale']}",
        f"CF/P.IVA: {ana.get('codice_fiscale') or ana.get('partita_iva') or '—'}",
        headers, rows,
        col_widths_mm=[25, 130, 28, 28, 32], landscape_mode=False,
    )
    return _pdf_response(pdf, f"estratto_{ana['ragione_sociale']}.pdf")


# ============================================================
# HEALTH
# ============================================================
@api.get("/")
async def root():
    return {"app": "Programma Assicurativo", "status": "ok"}


# ----- Mount -----
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----- Startup -----
@app.on_event("startup")
async def startup():
    # indexes
    await db.users.create_index("email", unique=True)
    await db.anagrafiche.create_index("ragione_sociale")
    await db.anagrafiche.create_index("codice_fiscale")
    await db.anagrafiche.create_index("id_anagrafica_exp")
    await db.polizze.create_index("numero_polizza")
    await db.polizze.create_index("contraente_id")
    await db.polizze.create_index("id_polizza_exp")
    await db.titoli.create_index("polizza_id")
    await db.titoli.create_index("id_titolo_exp")
    await db.sinistri.create_index("polizza_id")
    await db.sinistri.create_index("id_sinistro_exp")
    await db.attivita_log.create_index("created_at")

    # admin seed
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@assicura.it").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin123!")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        admin = UserPublic(email=admin_email, name="Amministratore", role="admin").model_dump()
        admin["password_hash"] = hash_password(admin_password)
        await db.users.insert_one(admin)
        logger.info("Admin seeded: %s", admin_email)
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one(
            {"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}}
        )
        logger.info("Admin password updated: %s", admin_email)

    # demo users (dipendente + cliente collegato a anagrafica demo)
    from seed_demo import seed_demo
    await seed_demo(db)

    # seed librerie (banche, conti cassa, rami) - solo se vuote
    if await db.conti_cassa.count_documents({}) == 0:
        for i, c in enumerate([
            {"nome": "Cassa Contanti", "tipo": "cassa", "ordine": 1},
            {"nome": "Assegni", "tipo": "cassa", "ordine": 2},
            {"nome": "BPER Sondrio", "tipo": "banca", "ordine": 3},
            {"nome": "Intesa Sanpaolo", "tipo": "banca", "ordine": 4},
            {"nome": "Credit Agricole", "tipo": "banca", "ordine": 5},
            {"nome": "RID Direzione", "tipo": "rid", "ordine": 6},
            {"nome": "PayPal / Online", "tipo": "online", "ordine": 7},
        ]):
            await db.conti_cassa.insert_one(ContoCassa(**c).model_dump())

    if await db.rami.count_documents({}) == 0:
        for r in [
            {"codice": "RCA", "nome": "RC Auto"},
            {"codice": "INCENDIO", "nome": "Incendio"},
            {"codice": "FURTO", "nome": "Furto"},
            {"codice": "VITA", "nome": "Vita"},
            {"codice": "MALATTIA", "nome": "Malattia"},
            {"codice": "INFORTUNI", "nome": "Infortuni"},
            {"codice": "RC_PROF", "nome": "RC Professionale"},
            {"codice": "RC_GEN", "nome": "RC Generale"},
            {"codice": "MULTIRISCHIO", "nome": "Multirischio Casa/Azienda"},
            {"codice": "TUTELA_LEGALE", "nome": "Tutela Legale"},
            {"codice": "ASSISTENZA", "nome": "Assistenza"},
        ]:
            await db.rami.insert_one(RamoLibreria(**r).model_dump())

    if await db.banche.count_documents({}) == 0:
        for b in [
            {"nome": "BPER Banca", "codice_abi": "05387"},
            {"nome": "Intesa Sanpaolo", "codice_abi": "03069"},
            {"nome": "Credit Agricole Italia", "codice_abi": "06230"},
            {"nome": "Unicredit", "codice_abi": "02008"},
        ]:
            await db.banche.insert_one(Banca(**b).model_dump())

    # init object storage (non bloccante)
    try:
        obj_storage.init_storage()
    except Exception as e:
        logger.warning("Object storage non disponibile: %s", e)


@app.on_event("shutdown")
async def shutdown():
    client.close()
