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
    AttivitaLog, ImportLog, _now_iso, _uid,
)
import ania_importer
import inps_calculator

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
    limit: int = 500,
    user=Depends(current_user),
):
    flt: dict = {}
    if polizza_id:
        flt["polizza_id"] = polizza_id
    if stato:
        flt["stato"] = stato
    # restringi per cliente
    if user["role"] == "cliente" and user.get("anagrafica_id"):
        pol_ids = [p["id"] async for p in db.polizze.find(
            {"contraente_id": user["anagrafica_id"]}, {"_id": 0, "id": 1})]
        flt["polizza_id"] = {"$in": pol_ids}
    items = await db.titoli.find(flt, {"_id": 0}).sort("scadenza", -1).to_list(limit)
    pol_ids = list({t["polizza_id"] for t in items if t.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find(
        {"id": {"$in": pol_ids}}, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1})}
    for t in items:
        p = pols.get(t.get("polizza_id"), {})
        t["numero_polizza"] = p.get("numero_polizza")
    return items


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


@app.on_event("shutdown")
async def shutdown():
    client.close()
