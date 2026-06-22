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
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Query, Form
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
    Allegato, DiarioVoce, MessaggioChat, Corso, ProgressoCorso, PagamentoProvvigioni,
    AziendaConfig, SchemaProvvigionale, EventoCalendario,
    PipelineCustom, PipelineColonna, PipelineCard,
    _now_iso, _uid,
)
import ania_importer
import inps_calculator
import storage as obj_storage
import pdf_report
import brogliaccio as brog
import cf_calc
import geocoder as geocoder_svc
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


async def log_diario_cliente(anagrafica_id: str, tipo: str, titolo: str,
                             descrizione: str | None = None, autore: dict | None = None):
    """Crea automaticamente una voce di diario sull'anagrafica cliente.

    Usato per email inviate, messaggi chat, documenti caricati ecc.
    Idempotente per scelta progettuale.
    """
    if not anagrafica_id:
        return
    voce = DiarioVoce(
        anagrafica_id=anagrafica_id,
        data_evento=_now_iso()[:10],
        tipo=tipo, titolo=titolo, descrizione=descrizione,
        autore_id=autore.get("id") if autore else None,
        autore_nome=autore.get("name") if autore else "Sistema",
    )
    await db.diario.insert_one(voce.model_dump())


async def _intestazione_pdf() -> dict:
    """Ritorna kwargs (ragione_sociale, logo_bytes, indirizzo, contatti, note_footer) per stampa_elenco."""
    try:
        return await pdf_report.get_intestazione_azienda(db)
    except Exception:
        return {}


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
# COLLABORATORI / PROVVIGIONI
# ============================================================
@api.get("/collaboratori")
async def list_collaboratori(user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Tutti gli utenti con ruolo collaboratore/dipendente."""
    items = await db.users.find(
        {"role": {"$in": ["collaboratore", "dipendente"]}},
        {"_id": 0, "password_hash": 0},
    ).sort("name", 1).to_list(500)
    return items


@api.get("/collaboratori/{cid}/estratto-provvigioni")
async def estratto_provvigioni(
    cid: str, dal: Optional[str] = None, al: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Estratto conto provvigioni: titoli incassati nel periodo + pagamenti effettuati.

    Restituisce:
      - titoli con provvigione maturata (da pagare o già pagata)
      - pagamenti effettuati (storico)
      - totali del periodo
    """
    collab = await db.users.find_one({"id": cid}, {"_id": 0, "password_hash": 0})
    if not collab:
        raise HTTPException(404, "Collaboratore non trovato")

    pol_filter = {"collaboratore_id": cid}
    pol_ids = [p["id"] async for p in db.polizze.find(pol_filter, {"_id": 0, "id": 1})]

    titolo_filter = {"polizza_id": {"$in": pol_ids}, "stato": "incassato"}
    inc_cond = {}
    if dal: inc_cond["$gte"] = dal
    if al: inc_cond["$lte"] = al
    if inc_cond: titolo_filter["data_incasso"] = inc_cond

    titoli = await db.titoli.find(titolo_filter, {"_id": 0}).to_list(5000)
    # arricchimento polizza/contraente
    pol_map = {p["id"]: p async for p in db.polizze.find(
        {"id": {"$in": pol_ids}}, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "ramo": 1})}
    ana_ids = list({p.get("contraente_id") for p in pol_map.values() if p.get("contraente_id")})
    ana_map = {a["id"]: a async for a in db.anagrafiche.find(
        {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}

    # pagamenti già effettuati nel periodo (per evitare conteggi doppi)
    pag_filter = {"collaboratore_id": cid}
    if dal or al:
        cond = {}
        if dal: cond["$gte"] = dal
        if al: cond["$lte"] = al
        pag_filter["data_pagamento"] = cond
    pagamenti = await db.pagamenti_provvigioni.find(pag_filter, {"_id": 0}).sort("data_pagamento", -1).to_list(500)
    titoli_gia_pagati = set()
    for p in pagamenti:
        for tid in p.get("titoli_ids", []):
            titoli_gia_pagati.add(tid)

    rows = []
    tot_lordo = 0.0
    tot_da_pagare = 0.0
    for t in titoli:
        pol = pol_map.get(t["polizza_id"], {})
        ana = ana_map.get(pol.get("contraente_id", ""), {})
        provv = t.get("provvigioni", 0.0) or 0.0
        gia_pagato = t["id"] in titoli_gia_pagati
        rows.append({
            "titolo_id": t["id"],
            "polizza_id": t["polizza_id"],
            "numero_polizza": pol.get("numero_polizza"),
            "contraente": ana.get("ragione_sociale"),
            "ramo": pol.get("ramo"),
            "data_incasso": t.get("data_incasso"),
            "importo_lordo": t.get("importo_lordo", 0.0),
            "provvigione": provv,
            "gia_pagato": gia_pagato,
        })
        tot_lordo += provv
        if not gia_pagato:
            tot_da_pagare += provv

    # calcolo trattenute sul "da pagare"
    rit = collab.get("perc_ritenuta_acconto", 0.0) or 0.0
    inps = collab.get("perc_inps_inarcassa", 0.0) or 0.0
    ritenuta_calc = round(tot_da_pagare * rit / 100.0, 2)
    contributi_calc = round(tot_da_pagare * inps / 100.0, 2)
    netto_calc = round(tot_da_pagare - ritenuta_calc - contributi_calc, 2)

    return {
        "collaboratore": collab,
        "periodo": {"dal": dal, "al": al},
        "righe": rows,
        "totali": {
            "provvigioni_lorde_periodo": round(tot_lordo, 2),
            "provvigioni_da_pagare": round(tot_da_pagare, 2),
            "ritenuta_acconto_calcolata": ritenuta_calc,
            "contributi_calcolati": contributi_calc,
            "netto_da_pagare": netto_calc,
        },
        "pagamenti_periodo": pagamenti,
    }


@api.post("/collaboratori/{cid}/paga-provvigioni")
async def paga_provvigioni(cid: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    """Esegue pagamento provvigioni: crea PagamentoProvvigioni + movimento contabile uscita.

    body: { titoli_ids: [...], conto_cassa_id, data_pagamento, mezzo_pagamento, note,
            override_provvigioni_lorde?, override_ritenuta?, override_contributi? }
    """
    collab = await db.users.find_one({"id": cid}, {"_id": 0, "password_hash": 0})
    if not collab:
        raise HTTPException(404, "Collaboratore non trovato")
    titoli_ids = body.get("titoli_ids") or []
    if not titoli_ids:
        raise HTTPException(400, "Seleziona almeno un titolo")
    conto_id = body.get("conto_cassa_id")
    data_pag = body.get("data_pagamento") or _now_iso()[:10]

    titoli = await db.titoli.find({"id": {"$in": titoli_ids}}, {"_id": 0}).to_list(5000)
    lordo = sum((t.get("provvigioni") or 0.0) for t in titoli)
    if body.get("override_provvigioni_lorde") is not None:
        lordo = float(body["override_provvigioni_lorde"])

    rit_perc = collab.get("perc_ritenuta_acconto", 0.0) or 0.0
    inps_perc = collab.get("perc_inps_inarcassa", 0.0) or 0.0
    ritenuta = float(body.get("override_ritenuta")) if body.get("override_ritenuta") is not None else round(lordo * rit_perc / 100.0, 2)
    contributi = float(body.get("override_contributi")) if body.get("override_contributi") is not None else round(lordo * inps_perc / 100.0, 2)
    netto = round(lordo - ritenuta - contributi, 2)

    # determina periodo (min/max data_incasso dei titoli)
    inc_dates = [t.get("data_incasso") for t in titoli if t.get("data_incasso")]
    periodo_dal = min(inc_dates) if inc_dates else data_pag
    periodo_al = max(inc_dates) if inc_dates else data_pag

    # Crea movimento contabile (uscita) - va in Brogliaccio
    mov = MovimentoContabile(
        data_movimento=data_pag,
        tipo="uscita",
        categoria="provvigioni",
        importo=netto,
        descrizione=f"Pagamento provvigioni a {collab.get('name')} - periodo {periodo_dal} / {periodo_al}",
        conto_cassa_id=conto_id,
        mezzo_pagamento=body.get("mezzo_pagamento", "bonifico"),
        note=(f"Lordo {lordo:.2f} - rit. {ritenuta:.2f} - contributi {contributi:.2f} = netto {netto:.2f}"),
    )
    await db.movimenti.insert_one(mov.model_dump())

    pag = PagamentoProvvigioni(
        collaboratore_id=cid,
        collaboratore_nome=collab.get("name", ""),
        periodo_dal=periodo_dal,
        periodo_al=periodo_al,
        provvigioni_lorde=round(lordo, 2),
        ritenuta_acconto=ritenuta,
        contributi=contributi,
        netto_pagato=netto,
        conto_cassa_id=conto_id,
        mezzo_pagamento=body.get("mezzo_pagamento", "bonifico"),
        data_pagamento=data_pag,
        movimento_id=mov.id,
        titoli_ids=titoli_ids,
        note=body.get("note"),
    )
    await db.pagamenti_provvigioni.insert_one(pag.model_dump())
    await log_attivita(user, "paga_provvigioni", "collaboratore", cid,
                       f"Pagate provvigioni a {collab.get('name')} per €{netto:.2f}")
    return {
        "ok": True,
        "pagamento": pag.model_dump(),
        "movimento": mov.model_dump(),
    }


@api.get("/collaboratori/{cid}/pagamenti")
async def list_pagamenti(cid: str, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    items = await db.pagamenti_provvigioni.find({"collaboratore_id": cid}, {"_id": 0}) \
        .sort("data_pagamento", -1).to_list(500)
    return items


@api.get("/stampa/provvigioni/{cid}")
async def stampa_provvigioni(cid: str, dal: Optional[str] = None, al: Optional[str] = None,
                             user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    data = await estratto_provvigioni(cid, dal, al, user)
    collab = data["collaboratore"]
    headers = ["Data", "N. polizza", "Contraente", "Ramo", "Premio €", "Provvigione €", "Pagata"]
    rows = []
    for r in data["righe"]:
        rows.append([r.get("data_incasso", ""), r.get("numero_polizza", ""),
                     r.get("contraente", ""), r.get("ramo", ""),
                     r.get("importo_lordo", 0), r.get("provvigione", 0),
                     "SÌ" if r.get("gia_pagato") else "NO"])
    tot = data["totali"]
    rows.append(["", "", "", "TOTALE LORDO", "", tot["provvigioni_lorde_periodo"], ""])
    rows.append(["", "", "", "DA PAGARE", "", tot["provvigioni_da_pagare"], ""])
    rows.append(["", "", "", "RITENUTA ACCONTO", "", tot["ritenuta_acconto_calcolata"], ""])
    rows.append(["", "", "", "CONTRIBUTI", "", tot["contributi_calcolati"], ""])
    rows.append(["", "", "", "NETTO DA PAGARE", "", tot["netto_da_pagare"], ""])
    pdf = pdf_report.stampa_elenco(
        f"Estratto conto provvigioni - {collab.get('name')}",
        f"Periodo: {dal or '—'} → {al or '—'}",
        headers, rows,
        col_widths_mm=[25, 35, 60, 25, 30, 30, 22], landscape_mode=False,
        filtri_attivi={"Dal": dal, "Al": al},
        **(await _intestazione_pdf()),
    )
    return _pdf_response(pdf, f"provvigioni_{collab.get('name')}.pdf")


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
# COMPAGNIE — Estratto conto e Saldo cassa
# ============================================================
async def _compagnia_estratto_data(compagnia_id: str, dal: Optional[str], al: Optional[str]) -> dict:
    """Aggrega dare/avere per una compagnia su un periodo.

    Logica:
      - Titoli incassati nel periodo → DARE verso compagnia = (lordo - provvigioni se trattiene)
      - Movimenti contabili categoria 'pagamento_compagnia' verso questa compagnia → AVERE
    """
    comp = await db.compagnie.find_one({"id": compagnia_id}, {"_id": 0})
    if not comp:
        raise HTTPException(404, "Compagnia non trovata")
    trattiene = comp.get("trattiene_provvigioni", True) is not False

    # titoli incassati nel periodo riferiti a polizze di questa compagnia
    polizze = await db.polizze.find({"compagnia_id": compagnia_id}, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "ramo": 1}).to_list(20000)
    pol_index = {p["id"]: p for p in polizze}
    if not pol_index:
        return {"compagnia": comp, "righe": [], "totale_dare": 0.0, "totale_avere": 0.0, "saldo": 0.0,
                "periodo": {"dal": dal, "al": al}, "trattiene_provvigioni": trattiene}

    titoli_flt: dict = {
        "polizza_id": {"$in": list(pol_index.keys())},
        "stato": "incassato",
    }
    if dal or al:
        cond = {}
        if dal: cond["$gte"] = dal
        if al: cond["$lte"] = al
        titoli_flt["data_incasso"] = cond
    titoli = await db.titoli.find(titoli_flt, {"_id": 0}).sort("data_incasso", 1).to_list(20000)

    # arricchimento contraenti
    contr_ids = list({pol_index[t["polizza_id"]].get("contraente_id") for t in titoli if t["polizza_id"] in pol_index})
    contr_map = {}
    if contr_ids:
        async for c in db.anagrafiche.find({"id": {"$in": contr_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1}):
            contr_map[c["id"]] = c["ragione_sociale"]

    righe = []
    totale_dare = 0.0
    for t in titoli:
        pol = pol_index.get(t["polizza_id"], {})
        provv = float(t.get("provvigioni") or 0)
        lordo = float(t.get("importo_lordo") or 0)
        dovuto_alla_compagnia = (lordo - provv) if trattiene else lordo
        righe.append({
            "data": t.get("data_incasso") or t.get("scadenza"),
            "tipo": "incasso",
            "polizza": pol.get("numero_polizza"),
            "contraente": contr_map.get(pol.get("contraente_id", "")),
            "ramo": pol.get("ramo"),
            "dare": round(dovuto_alla_compagnia, 2),
            "avere": 0.0,
            "lordo": lordo, "provvigioni": provv,
            "_movimento_id": t.get("id"),
        })
        totale_dare += dovuto_alla_compagnia

    # pagamenti verso compagnia
    mov_flt: dict = {"compagnia_id": compagnia_id, "categoria": "pagamento_compagnia"}
    if dal or al:
        cond = {}
        if dal: cond["$gte"] = dal
        if al: cond["$lte"] = al
        mov_flt["data_movimento"] = cond
    movs = await db.movimenti.find(mov_flt, {"_id": 0}).sort("data_movimento", 1).to_list(5000)
    totale_avere = 0.0
    for m in movs:
        imp = float(m.get("importo") or 0)
        righe.append({
            "data": m.get("data_movimento"),
            "tipo": "pagamento",
            "polizza": None,
            "contraente": None,
            "ramo": None,
            "dare": 0.0,
            "avere": imp,
            "descrizione": m.get("descrizione") or m.get("causale"),
            "_movimento_id": m.get("id"),
        })
        totale_avere += imp

    righe.sort(key=lambda r: r["data"] or "")
    saldo = totale_dare - totale_avere
    return {
        "compagnia": comp,
        "righe": righe,
        "totale_dare": round(totale_dare, 2),
        "totale_avere": round(totale_avere, 2),
        "saldo": round(saldo, 2),
        "periodo": {"dal": dal, "al": al},
        "trattiene_provvigioni": trattiene,
    }


@api.get("/compagnie/{cid}/estratto-conto")
async def compagnia_estratto_conto(
    cid: str, dal: Optional[str] = None, al: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    return await _compagnia_estratto_data(cid, dal, al)


@api.get("/compagnie/saldi-cassa")
async def saldi_cassa_compagnie(
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Saldo da versare/da incassare per ciascuna compagnia (tutti i periodi)."""
    compagnie = await db.compagnie.find({}, {"_id": 0}).to_list(500)
    risultati = []
    for c in compagnie:
        try:
            data = await _compagnia_estratto_data(c["id"], None, None)
            risultati.append({
                "compagnia_id": c["id"],
                "codice": c.get("codice"),
                "ragione_sociale": c.get("ragione_sociale"),
                "trattiene_provvigioni": c.get("trattiene_provvigioni", True),
                "totale_incassato": data["totale_dare"],
                "totale_versato": data["totale_avere"],
                "saldo_da_versare": data["saldo"],
                "righe_count": len(data["righe"]),
            })
        except Exception:
            continue
    risultati.sort(key=lambda r: -abs(r["saldo_da_versare"] or 0))
    return risultati


@api.get("/stampa/compagnie/{cid}/estratto-conto")
async def stampa_compagnia_estratto(
    cid: str, dal: Optional[str] = None, al: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    data = await _compagnia_estratto_data(cid, dal, al)
    comp = data["compagnia"]
    headers = ["Data", "Tipo", "Polizza", "Contraente", "Ramo", "Dare €", "Avere €"]
    rows = []
    for r in data["righe"]:
        rows.append([
            r.get("data") or "", r.get("tipo") or "",
            r.get("polizza") or "", (r.get("contraente") or "")[:35],
            r.get("ramo") or "", r.get("dare") or "", r.get("avere") or "",
        ])
    rows.append(["", "", "", "", "TOTALE", round(data["totale_dare"], 2), round(data["totale_avere"], 2)])
    rows.append(["", "", "", "", "SALDO DA VERSARE", round(data["saldo"], 2), ""])
    pdf = pdf_report.stampa_elenco(
        f"Estratto conto compagnia - {comp.get('ragione_sociale')}",
        f"Periodo: {dal or '—'} → {al or '—'} · Trattiene provv: {'SI' if data['trattiene_provvigioni'] else 'NO'}",
        headers, rows,
        col_widths_mm=[22, 22, 32, 60, 22, 28, 28], landscape_mode=False,
        **(await _intestazione_pdf()),
    )
    return _pdf_response(pdf, f"estratto_compagnia_{comp.get('codice') or cid}.pdf")


@api.get("/stampa/compagnie/saldi-cassa")
async def stampa_saldi_compagnie(
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    items = await saldi_cassa_compagnie(user=user)
    headers = ["Codice", "Ragione sociale", "Tratt. provv.", "Incassato €", "Versato €", "Saldo €"]
    rows = []
    tot_inc = tot_vers = tot_sal = 0.0
    for r in items:
        rows.append([
            r.get("codice") or "", (r.get("ragione_sociale") or "")[:50],
            "SI" if r.get("trattiene_provvigioni") else "NO",
            r.get("totale_incassato"), r.get("totale_versato"), r.get("saldo_da_versare"),
        ])
        tot_inc += float(r.get("totale_incassato") or 0)
        tot_vers += float(r.get("totale_versato") or 0)
        tot_sal += float(r.get("saldo_da_versare") or 0)
    rows.append(["", "TOTALI", "", round(tot_inc, 2), round(tot_vers, 2), round(tot_sal, 2)])
    pdf = pdf_report.stampa_elenco(
        "Saldi cassa compagnie", f"{len(items)} compagnie",
        headers, rows,
        col_widths_mm=[22, 70, 22, 30, 30, 30], landscape_mode=False,
        **(await _intestazione_pdf()),
    )
    return _pdf_response(pdf, "saldi_compagnie.pdf")


# ============================================================
# ANAGRAFICHE
# ============================================================
# UTILITY — Codice Fiscale & Geocoding
# ============================================================
@api.post("/utility/codice-fiscale/calcola")
async def calcola_codice_fiscale(body: dict, user=Depends(current_user)):
    """body: {nome, cognome, sesso (M/F), data_nascita (YYYY-MM-DD), comune_nascita}"""
    try:
        cf = cf_calc.calcola_cf(
            lastname=body.get("cognome", ""),
            firstname=body.get("nome", ""),
            gender=body.get("sesso", ""),
            birthdate=body.get("data_nascita", ""),
            birthplace=body.get("comune_nascita", ""),
        )
        return {"codice_fiscale": cf}
    except Exception as e:
        raise HTTPException(400, f"Impossibile calcolare CF: {e}")


@api.post("/utility/codice-fiscale/decodifica")
async def decodifica_codice_fiscale(body: dict, user=Depends(current_user)):
    """body: {codice_fiscale}"""
    try:
        return cf_calc.decodifica_cf(body.get("codice_fiscale", ""))
    except Exception as e:
        raise HTTPException(400, f"CF non valido: {e}")


@api.post("/utility/geocoding")
async def utility_geocoding(body: dict, user=Depends(current_user)):
    """body: {indirizzo, comune, cap, provincia, nazione?}. Ritorna {lat, lng, display_name}."""
    result = await geocoder_svc.geocoda_indirizzo(
        indirizzo=body.get("indirizzo", ""),
        comune=body.get("comune"),
        cap=body.get("cap"),
        provincia=body.get("provincia"),
        nazione=body.get("nazione") or "Italia",
    )
    if not result:
        return {"trovato": False}
    return {"trovato": True, **result}


@api.post("/utility/ocr-documento-identita")
async def ocr_documento_identita(
    file: UploadFile = File(...),
    file_retro: Optional[UploadFile] = File(None),
    anagrafica_id: Optional[str] = Form(None),
    tipo: str = Form("carta_identita"),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """OCR universale per CI / patente / passaporto.

    Supporta:
    - 1 PDF (multi-pagina automatico)
    - 1 immagine (solo fronte)
    - 2 immagini (fronte + retro) -> combinate verticalmente prima dell'OCR
    """
    import ocr_ci
    valid = {"carta_identita", "patente", "passaporto"}
    if tipo not in valid:
        raise HTTPException(400, f"Tipo non valido: {tipo}")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 10 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    file_for_ocr = contents
    ct_for_ocr = ct
    contents_retro = None
    ct_retro = None
    if file_retro is not None:
        contents_retro = await file_retro.read()
        ct_retro = file_retro.content_type or obj_storage.mime_for(file_retro.filename or "")
        if len(contents_retro) > 10 * 1024 * 1024:
            raise HTTPException(400, "Retro troppo grande (max 10 MB)")
    if ct == "application/pdf":
        try:
            import pdfplumber
            from io import BytesIO
            with pdfplumber.open(BytesIO(contents)) as pdf:
                if not pdf.pages:
                    raise HTTPException(400, "PDF vuoto")
                img = pdf.pages[0].to_image(resolution=200).original
                out = BytesIO()
                img.save(out, format="JPEG", quality=85)
                file_for_ocr = out.getvalue()
                ct_for_ocr = "image/jpeg"
        except Exception as e:
            raise HTTPException(400, f"Errore conversione PDF: {e}")
    elif not ct.startswith("image/"):
        raise HTTPException(400, "Formato non supportato (PDF/JPG/PNG)")

    # Combina fronte + retro in singola immagine verticale
    if contents_retro and ct_retro and ct_retro.startswith("image/"):
        try:
            from PIL import Image
            from io import BytesIO
            img_f = Image.open(BytesIO(file_for_ocr))
            img_r = Image.open(BytesIO(contents_retro))
            # Normalizza alla stessa larghezza
            w = max(img_f.width, img_r.width)
            def _resize(i):
                if i.width == w: return i
                h = int(i.height * (w / i.width))
                return i.resize((w, h))
            img_f, img_r = _resize(img_f), _resize(img_r)
            combined = Image.new("RGB", (w, img_f.height + img_r.height + 10), "white")
            combined.paste(img_f.convert("RGB"), (0, 0))
            combined.paste(img_r.convert("RGB"), (0, img_f.height + 10))
            out = BytesIO()
            combined.save(out, format="JPEG", quality=85)
            file_for_ocr = out.getvalue()
            ct_for_ocr = "image/jpeg"
        except Exception as e:
            raise HTTPException(400, f"Errore combinazione fronte/retro: {e}")

    try:
        data = await ocr_ci.estrai_dati_ci(file_for_ocr, ct_for_ocr)
    except Exception as e:
        raise HTTPException(503, f"Errore OCR: {e}")

    documento_url = None
    if anagrafica_id:
        # salva file fronte (o PDF) come documento principale; retro come allegato
        ext = (file.filename or "doc.bin").rsplit(".", 1)[-1].lower() or "bin"
        path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{anagrafica_id}/{tipo}_{_uid()}.{ext}"
        try:
            result = obj_storage.put_object(path, contents, ct)
            documento_url = f"/api/storage/{result['path']}"
            doc_entry = {
                "url": documento_url, "storage_path": result["path"],
                "nome_file": file.filename, "mime": ct,
                "size_kb": round(len(contents) / 1024, 1),
                "data_caricamento": _now_iso(),
                "scadenza": data.get("data_scadenza"),
                "caricato_da": user.get("id"),
            }
            if contents_retro:
                # salva retro come allegato addizionale
                ext_r = (file_retro.filename or "retro.jpg").rsplit(".", 1)[-1].lower() or "jpg"
                path_r = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{anagrafica_id}/{tipo}_retro_{_uid()}.{ext_r}"
                try:
                    res_r = obj_storage.put_object(path_r, contents_retro, ct_retro)
                    doc_entry["url_retro"] = f"/api/storage/{res_r['path']}"
                    doc_entry["nome_file_retro"] = file_retro.filename
                except Exception:
                    pass
            await db.anagrafiche.update_one(
                {"id": anagrafica_id},
                {"$set": {f"documenti.{tipo}": doc_entry, "updated_at": _now_iso()}},
            )
        except Exception:
            pass

    await log_attivita(user, "ocr", tipo, anagrafica_id,
                       f"OCR {tipo}{'(fronte+retro)' if contents_retro else ''}: {data.get('cognome')} {data.get('nome')}")
    if documento_url:
        data["_documento_salvato"] = documento_url
    return data


@api.post("/utility/ocr-polizza")
async def ocr_polizza_endpoint(
    file: UploadFile = File(...),
    salva_come_allegato: bool = Form(False),
    polizza_id: Optional[str] = Form(None),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """OCR di una polizza italiana. Estrae dati strutturati (contraente, veicolo, garanzie, premi).

    Se polizza_id + salva_come_allegato → salva il file come allegato della polizza.
    """
    import ocr_polizza as ocr_pol
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 20 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    file_for_ocr = contents
    ct_for_ocr = ct
    if ct == "application/pdf":
        try:
            import pdfplumber
            from io import BytesIO
            with pdfplumber.open(BytesIO(contents)) as pdf:
                if not pdf.pages:
                    raise HTTPException(400, "PDF vuoto")
                # per polizze processa prime 2 pagine (frontespizio + dettagli)
                images = []
                for p in pdf.pages[:2]:
                    img = p.to_image(resolution=200).original
                    out = BytesIO()
                    img.save(out, format="JPEG", quality=85)
                    images.append(out.getvalue())
                # combina in unica immagine verticale se più pagine
                if len(images) == 1:
                    file_for_ocr = images[0]
                else:
                    from PIL import Image
                    imgs = [Image.open(BytesIO(x)) for x in images]
                    w = max(i.width for i in imgs)
                    h = sum(i.height for i in imgs)
                    combined = Image.new("RGB", (w, h), "white")
                    y = 0
                    for i in imgs:
                        combined.paste(i, (0, y))
                        y += i.height
                    out = BytesIO()
                    combined.save(out, format="JPEG", quality=80)
                    file_for_ocr = out.getvalue()
                ct_for_ocr = "image/jpeg"
        except Exception as e:
            raise HTTPException(400, f"Errore conversione PDF: {e}")
    elif not ct.startswith("image/"):
        raise HTTPException(400, "Formato non supportato (PDF/JPG/PNG)")
    try:
        data = await ocr_pol.estrai_dati_polizza(file_for_ocr, ct_for_ocr)
    except Exception as e:
        raise HTTPException(503, f"Errore OCR polizza: {e}")

    if salva_come_allegato and polizza_id:
        ext = (file.filename or "polizza.pdf").rsplit(".", 1)[-1].lower() or "pdf"
        path = f"{os.environ.get('APP_NAME', 'assicura')}/polizze/{polizza_id}/polizza_{_uid()}.{ext}"
        try:
            result = obj_storage.put_object(path, contents, ct)
            url = f"/api/storage/{result['path']}"
            alleg = Allegato(
                entita_tipo="polizza", entita_id=polizza_id,
                nome_file=file.filename or "polizza.pdf",
                url=url, storage_path=result["path"],
                mime=ct, size_kb=round(len(contents) / 1024, 1),
                caricato_da=user.get("id"),
            )
            await db.allegati.insert_one(alleg.model_dump())
        except Exception:
            pass

    await log_attivita(user, "ocr", "polizza", polizza_id,
                       f"OCR polizza: {data.get('numero_polizza')} - {data.get('compagnia')}")
    return data


@api.post("/utility/ocr-carta-identita")
async def ocr_carta_identita(
    file: UploadFile = File(...),
    anagrafica_id: Optional[str] = Form(None),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """OCR di una carta d'identità italiana. Restituisce dati anagrafici estratti.

    Se anagrafica_id è fornito, salva ANCHE il file come documento 'carta_identita'
    nella scheda cliente.
    """
    import ocr_ci
    contents = await file.read()
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 8 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    file_for_ocr = contents
    ct_for_ocr = ct
    if ct == "application/pdf":
        try:
            import pdfplumber
            from io import BytesIO
            with pdfplumber.open(BytesIO(contents)) as pdf:
                if not pdf.pages:
                    raise HTTPException(400, "PDF vuoto")
                img = pdf.pages[0].to_image(resolution=200).original
                out = BytesIO()
                img.save(out, format="JPEG", quality=85)
                file_for_ocr = out.getvalue()
                ct_for_ocr = "image/jpeg"
        except Exception as e:
            raise HTTPException(400, f"Errore conversione PDF: {e}")
    elif not ct.startswith("image/"):
        raise HTTPException(400, "Formato non supportato (richiesto JPG/PNG/PDF)")
    try:
        data = await ocr_ci.estrai_dati_ci(file_for_ocr, ct_for_ocr)
    except Exception as e:
        raise HTTPException(503, f"Errore OCR: {e}")

    # Se collegato a un'anagrafica, salva il file originale come documento
    documento_url = None
    if anagrafica_id:
        ext = (file.filename or "ci.bin").rsplit(".", 1)[-1].lower() or "bin"
        path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{anagrafica_id}/carta_identita_{_uid()}.{ext}"
        try:
            result = obj_storage.put_object(path, contents, ct)
            documento_url = f"/api/storage/{result['path']}"
            doc_entry = {
                "url": documento_url, "storage_path": result["path"],
                "nome_file": file.filename, "mime": ct,
                "size_kb": round(len(contents) / 1024, 1),
                "data_caricamento": _now_iso(),
                "scadenza": data.get("data_scadenza"),
                "caricato_da": user.get("id"),
            }
            await db.anagrafiche.update_one(
                {"id": anagrafica_id},
                {"$set": {"documenti.carta_identita": doc_entry, "updated_at": _now_iso()}},
            )
        except Exception:
            pass  # OCR ha successo anche se l'upload fallisce

    await log_attivita(user, "ocr", "carta_identita", anagrafica_id,
                       f"OCR CI: {data.get('cognome')} {data.get('nome')}")
    if documento_url:
        data["_documento_salvato"] = documento_url
    return data


@api.post("/utility/ocr-visura-camerale")
async def ocr_visura_camerale(
    file: UploadFile = File(...),
    anagrafica_id: Optional[str] = Form(None),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """OCR di una visura camerale. Estrae dati ditta + amministratori.

    Se anagrafica_id è fornito, salva il file come documento 'visura_camerale'.
    Gli amministratori vengono restituiti per importazione anagrafiche legate
    (decisione lato frontend).
    """
    import ocr_visura
    contents = await file.read()
    if len(contents) > 15 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 15 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    file_for_ocr = contents
    ct_for_ocr = ct
    if ct == "application/pdf":
        try:
            import pdfplumber
            from io import BytesIO
            with pdfplumber.open(BytesIO(contents)) as pdf:
                if not pdf.pages:
                    raise HTTPException(400, "PDF vuoto")
                # per visure camerali analizziamo solo la prima pagina (sintesi)
                img = pdf.pages[0].to_image(resolution=200).original
                out = BytesIO()
                img.save(out, format="JPEG", quality=85)
                file_for_ocr = out.getvalue()
                ct_for_ocr = "image/jpeg"
        except Exception as e:
            raise HTTPException(400, f"Errore conversione PDF: {e}")
    elif not ct.startswith("image/"):
        raise HTTPException(400, "Formato non supportato (PDF/JPG/PNG)")
    try:
        data = await ocr_visura.estrai_dati_visura(file_for_ocr, ct_for_ocr)
    except Exception as e:
        raise HTTPException(503, f"Errore OCR visura: {e}")

    # Salva il file come documento dell'azienda
    if anagrafica_id:
        ext = (file.filename or "visura.pdf").rsplit(".", 1)[-1].lower() or "pdf"
        path = f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{anagrafica_id}/visura_camerale_{_uid()}.{ext}"
        try:
            result = obj_storage.put_object(path, contents, ct)
            doc_entry = {
                "url": f"/api/storage/{result['path']}", "storage_path": result["path"],
                "nome_file": file.filename, "mime": ct,
                "size_kb": round(len(contents) / 1024, 1),
                "data_caricamento": _now_iso(),
                "caricato_da": user.get("id"),
            }
            await db.anagrafiche.update_one(
                {"id": anagrafica_id},
                {"$set": {"documenti.visura_camerale": doc_entry, "updated_at": _now_iso()}},
            )
        except Exception:
            pass

    await log_attivita(user, "ocr", "visura_camerale", anagrafica_id,
                       f"OCR visura: {data.get('ragione_sociale')} - {len(data.get('amministratori') or [])} amministratori")
    return data


@api.get("/anagrafiche")
async def list_anagrafiche(
    q: Optional[str] = None,
    limit: int = 200,
    tag: Optional[str] = None,
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


UPPER_FIELDS = {
    "ragione_sociale", "nome", "cognome", "codice_fiscale", "partita_iva",
    "comune", "provincia", "comune_nascita", "provincia_nascita",
    "indirizzo", "professione", "stato_civile", "titolo_studio",
    "iban", "intestatario", "provincia_intestatario", "veicolo_marca",
    "veicolo_modello", "targa", "veicolo_targa_rimorchio", "numero_polizza",
    "numero_sinistro", "ragione_sociale", "codice", "nome_file",
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


@api.post("/anagrafiche", status_code=201)
async def create_anagrafica(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body = _normalize_upper(body)
    obj = Anagrafica(**body)
    await db.anagrafiche.insert_one(obj.model_dump())
    await log_attivita(user, "create", "anagrafica", obj.id, f"Creata anagrafica {obj.ragione_sociale}")
    return obj.model_dump()


@api.put("/anagrafiche/{aid}")
async def update_anagrafica(aid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body = _normalize_upper(body)
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
# DOCUMENTI ANAGRAFICA + FIRMA DIGITALE
# ============================================================
ANAGRAFICA_DOC_TIPI = {
    "carta_identita", "patente", "passaporto", "codice_fiscale_doc",
    "tessera_sanitaria", "visura_camerale", "estratto_contributivo",
    "privacy_firmata", "altro",
}


@api.post("/anagrafiche/{aid}/documenti/{tipo}")
async def upload_documento_anagrafica(
    aid: str, tipo: str,
    file: UploadFile = File(...),
    scadenza: Optional[str] = Form(None),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
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


@api.delete("/anagrafiche/{aid}/documenti/{tipo}")
async def delete_documento_anagrafica(aid: str, tipo: str,
                                       user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    if tipo not in ANAGRAFICA_DOC_TIPI:
        raise HTTPException(400, "Tipo non valido")
    await db.anagrafiche.update_one(
        {"id": aid},
        {"$unset": {f"documenti.{tipo}": ""}, "$set": {"updated_at": _now_iso()}},
    )
    return {"ok": True}

@api.get("/anagrafiche/{aid}/privacy/genera-pdf")
async def genera_pdf_privacy(aid: str, user=Depends(current_user)):
    """Genera PDF di informativa privacy precompilato con i dati del cliente."""
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")
    cfg = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    headers = ["Voce", "Valore"]
    rows = [
        ["Cognome e nome / Ragione sociale", ana.get("ragione_sociale") or ""],
        ["Codice fiscale", ana.get("codice_fiscale") or ana.get("partita_iva") or ""],
        ["Data di nascita", ana.get("data_nascita") or ""],
        ["Indirizzo", f"{ana.get('indirizzo') or ''}, {ana.get('cap') or ''} {ana.get('comune') or ''} "
                     f"({ana.get('provincia') or ''})"],
        ["Email", ana.get("email") or ""],
        ["Telefono", ana.get("cellulare") or ana.get("telefono") or ""],
        ["", ""],
        ["INFORMATIVA EX ART. 13 GDPR", ""],
        ["Titolare del trattamento", cfg.get("ragione_sociale") or "—"],
        ["Sede legale", f"{cfg.get('indirizzo') or ''} {cfg.get('comune') or ''} ({cfg.get('provincia') or ''})"],
        ["PEC", cfg.get("pec") or cfg.get("email") or "—"],
        ["", ""],
        ["FINALITÀ DEL TRATTAMENTO", ""],
        ["1. Esecuzione contratto", "Stipula e gestione polizze, sinistri, comunicazioni operative"],
        ["2. Adempimenti di legge", "Antiriciclaggio, vigilanza IVASS, obblighi fiscali"],
        ["3. Marketing (consenso facoltativo)", "Newsletter, promozioni"],
        ["", ""],
        ["DIRITTI DELL'INTERESSATO", "Art. 15-22 GDPR: accesso, rettifica, cancellazione, opposizione"],
        ["", ""],
        ["CONSENSO PRESTATO IN DATA", _now_iso()[:10]],
        ["FIRMA DEL CLIENTE", "_______________________________"],
    ]
    pdf = pdf_report.stampa_elenco(
        f"Informativa privacy e consenso - {ana.get('ragione_sociale')}",
        "Documento ai sensi del Regolamento UE 2016/679 (GDPR)",
        headers, rows,
        col_widths_mm=[55, 130], landscape_mode=False,
        **(await _intestazione_pdf()),
    )
    return _pdf_response(pdf, f"privacy_{ana.get('codice_fiscale') or aid}.pdf")




@api.post("/anagrafiche/{aid}/firma-digitale")
async def salva_firma_cliente(aid: str, body: dict,
                               user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Salva la firma del cliente come immagine PNG (canvas base64)."""
    img_data = body.get("immagine_base64") or body.get("data")
    if not img_data:
        raise HTTPException(400, "immagine_base64 richiesta")
    import base64
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
@api.post("/anagrafiche/{aid}/calcolo-pensione/auto-da-estratto")
async def calcola_pensione_da_estratto(
    aid: str,
    file: UploadFile = File(...),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
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
    # 1) salva PDF nello storage come documento
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
    # 2) parsa il PDF
    try:
        parsed = inps_calculator.parse_estratto_contributivo(data)
    except Exception as e:
        raise HTTPException(400, f"PDF non parsabile: {e}")
    # 3) aggiorna anagrafica
    upd = {"documenti.estratto_contributivo": doc_entry, "updated_at": _now_iso()}
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


@api.post("/titoli/bulk-azione-allegato")
async def bulk_azione_allegato(
    action: str = Query(...),  # "incassa" | "copertura"
    ids_json: str = Query(...),  # JSON list di titoli
    data_incasso: Optional[str] = Query(None),
    mezzo_pagamento: Optional[str] = Query("bonifico"),
    conto_cassa_id: Optional[str] = Query(None),
    coperto_fino_a: Optional[str] = Query(None),
    data_copertura: Optional[str] = Query(None),
    invia_cliente: bool = Query(False),
    invia_collaboratore: bool = Query(False),
    note_email: Optional[str] = Query(None),
    file: Optional[UploadFile] = File(None),
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Esegue bulk incasso/copertura con allegato opzionale e invio email a cliente/collaboratore."""
    import json as _json
    try:
        ids = _json.loads(ids_json) if isinstance(ids_json, str) else ids_json
    except Exception:
        raise HTTPException(400, "ids_json non valido")
    if not ids:
        raise HTTPException(400, "Nessun titolo selezionato")

    # 1) carica file su object storage (se presente)
    allegato_meta = None
    if file:
        data = await file.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(400, "File troppo grande (max 25 MB)")
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
        file_id = _uid()
        path = f"{os.environ.get('APP_NAME', 'assicura')}/titoli/{file_id}.{ext}"
        ct = file.content_type or obj_storage.mime_for(file.filename or "")
        try:
            result = obj_storage.put_object(path, data, ct)
        except Exception as e:
            raise HTTPException(503, f"Errore upload: {e}")
        allegato_meta = {
            "nome_file": file.filename, "storage_path": result["path"],
            "content_type": ct, "size": result.get("size", len(data)),
        }

    # 2) esegui l'azione sui titoli
    risultato = {}
    if action == "incassa":
        risultato = await bulk_incassa({
            "ids": ids, "data_incasso": data_incasso,
            "mezzo_pagamento": mezzo_pagamento, "conto_cassa_id": conto_cassa_id,
        }, user)
    elif action == "copertura":
        coperto = data_copertura or coperto_fino_a or _now_iso()[:10]
        risultato = await bulk_copertura({"ids": ids, "data_copertura": coperto}, user)
    else:
        raise HTTPException(400, "action non valida")

    # 3) raccogli contraenti e collaboratori coinvolti
    titoli = await db.titoli.find({"id": {"$in": ids}}, {"_id": 0}).to_list(2000)
    pol_ids = list({t["polizza_id"] for t in titoli})
    polizze = await db.polizze.find({"id": {"$in": pol_ids}}, {"_id": 0}).to_list(2000)
    ana_ids = list({p["contraente_id"] for p in polizze if p.get("contraente_id")})
    collab_ids = list({p["collaboratore_id"] for p in polizze if p.get("collaboratore_id")})
    anas = await db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0}).to_list(500)
    collabs = await db.users.find({"id": {"$in": collab_ids}}, {"_id": 0, "password_hash": 0}).to_list(100)

    azione_label = "Quietanza incasso titolo" if action == "incassa" else "Conferma copertura titolo"
    email_create = 0

    # 4) salva l'allegato come record in db.allegati (collegato al primo cliente per ACL)
    allegato_id = None
    if allegato_meta and anas:
        al = Allegato(
            entita_tipo="anagrafica", entita_id=anas[0]["id"],
            nome_file=allegato_meta["nome_file"], storage_path=allegato_meta["storage_path"],
            content_type=allegato_meta["content_type"], size=allegato_meta["size"],
            descrizione=f"{azione_label} — {len(ids)} titoli", autore_id=user["id"],
        )
        await db.allegati.insert_one(al.model_dump())
        allegato_id = al.id

    # 5) crea email in coda per ogni cliente
    if invia_cliente:
        for ana in anas:
            if not ana.get("email"):
                continue
            corpo = (note_email or
                     f"Gentile {ana['ragione_sociale']},\n\n"
                     f"in allegato {azione_label.lower()} relativa alle Sue polizze.\n\n"
                     f"Cordiali saluti.")
            e = EmailMessaggio(
                destinatario_anagrafica_id=ana["id"], destinatario_email=ana["email"],
                oggetto=azione_label, corpo=corpo,
                template="titolo_quietanza", stato="in_coda", autore_id=user["id"],
            )
            await db.email.insert_one(e.model_dump())
            email_create += 1
            # auto-diario sul cliente
            await log_diario_cliente(
                ana["id"], "documento",
                titolo=f"📎 {azione_label}",
                descrizione=f"{len(ids)} titoli interessati. File: {allegato_meta['nome_file'] if allegato_meta else '—'}",
                autore=user,
            )

    # 6) email ai collaboratori
    if invia_collaboratore:
        for c in collabs:
            if not c.get("email"):
                continue
            corpo = (f"Ciao {c.get('name', '')},\n\n"
                     f"{azione_label} per {len(ids)} titoli delle polizze da te gestite.\n"
                     f"Operazione effettuata da {user.get('name')}.\n\n"
                     + (note_email or ""))
            e = EmailMessaggio(
                destinatario_email=c["email"], oggetto=f"{azione_label} (notifica collaboratore)",
                corpo=corpo, template="titolo_notifica_collab", stato="in_coda",
                autore_id=user["id"],
            )
            await db.email.insert_one(e.model_dump())
            email_create += 1

    return {
        **risultato,
        "allegato_id": allegato_id,
        "allegato_nome": allegato_meta["nome_file"] if allegato_meta else None,
        "email_create": email_create,
        "clienti_notificati": len([a for a in anas if a.get("email")]) if invia_cliente else 0,
        "collaboratori_notificati": len([c for c in collabs if c.get("email")]) if invia_collaboratore else 0,
    }


# Bulk actions sui titoli
@api.get("/titoli/sospesi")
async def titoli_sospesi(
    collaboratore_id: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Elenco titoli COPERTI DALL'AGENZIA (anticipati) ma ancora DA INCASSARE dal cliente.

    Per ogni titolo restituisce: contraente, collaboratore, data_copertura,
    scadenza polizza, importo lordo. Usato dalla pagina 'Sospesi'.
    """
    flt = {"titolo_coperto": True, "stato": {"$in": ["da_incassare", "insoluto"]}}
    items = await db.titoli.find(flt, {"_id": 0}).sort("data_copertura", 1).to_list(5000)
    if not items:
        return []
    pol_ids = list({t["polizza_id"] for t in items if t.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find({"id": {"$in": pol_ids}}, {"_id": 0})}
    ana_ids = list({p.get("contraente_id") for p in pols.values() if p.get("contraente_id")})
    anas = {a["id"]: a async for a in db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0})}
    collab_ids = list({(p.get("collaboratore_id") or t.get("collaboratore_id"))
                       for t, p in [(t, pols.get(t["polizza_id"], {})) for t in items]
                       if (p.get("collaboratore_id") or t.get("collaboratore_id"))})
    collab_map = {}
    if collab_ids:
        async for u in db.users.find({"id": {"$in": collab_ids}}, {"_id": 0, "id": 1, "name": 1}):
            collab_map[u["id"]] = u["name"]
    result = []
    for t in items:
        p = pols.get(t["polizza_id"], {})
        a = anas.get(p.get("contraente_id", ""), {})
        collab_id = p.get("collaboratore_id") or t.get("collaboratore_id")
        if collaboratore_id and collab_id != collaboratore_id:
            continue
        result.append({
            "id": t["id"],
            "polizza_id": t["polizza_id"],
            "numero_polizza": p.get("numero_polizza"),
            "ramo": p.get("ramo"),
            "targa": p.get("targa"),
            "contraente_id": a.get("id"),
            "contraente_nome": a.get("ragione_sociale"),
            "cellulare": a.get("cellulare") or a.get("telefono"),
            "collaboratore_id": collab_id,
            "collaboratore_nome": collab_map.get(collab_id) if collab_id else None,
            "data_copertura": t.get("data_copertura"),
            "scadenza_polizza": p.get("scadenza"),
            "scadenza_titolo": t.get("scadenza"),
            "importo_lordo": t.get("importo_lordo", 0.0),
            "provvigioni": t.get("provvigioni", 0.0),
            "giorni_anticipo": _giorni_da_oggi(t.get("data_copertura")),
        })
    # totali aggregati
    return result


def _giorni_da_oggi(data_iso: Optional[str]) -> Optional[int]:
    if not data_iso:
        return None
    try:
        from datetime import date as _date
        d = _date.fromisoformat(data_iso[:10])
        return (_date.today() - d).days
    except Exception:
        return None


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
    """Marca i titoli come coperti dall'agenzia: l'agenzia ha anticipato i soldi al cliente.

    body: {ids: [...], data_copertura?: 'YYYY-MM-DD' (default oggi), note?}
    Il titolo resta DA INCASSARE finché il cliente non paga.
    """
    ids = body.get("ids") or []
    if not ids:
        raise HTTPException(400, "ids richiesti")
    data_copertura = body.get("data_copertura") or _now_iso()[:10]
    note = body.get("note")
    set_fields = {
        "titolo_coperto": True,
        "data_copertura": data_copertura,
        "updated_at": _now_iso(),
    }
    if note:
        set_fields["note_copertura"] = note
    res = await db.titoli.update_many(
        {"id": {"$in": ids}},
        {"$set": set_fields},
    )
    await log_attivita(user, "bulk_copertura", "titolo", None,
                       f"{res.modified_count} titoli coperti dall'agenzia il {data_copertura}")
    return {"aggiornati": res.modified_count, "data_copertura": data_copertura}


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
                    t.get("mezzo_pagamento"), t.get("data_incasso"), t.get("data_copertura")])
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
    """Marca un titolo come incassato, crea movimento contabile entrata e
    (opzionalmente) movimento uscita 'sconto_cliente' se importo_pagato < lordo.

    body: {data_incasso?, mezzo_pagamento?, conto_cassa_id?, importo_pagato?, motivo_sconto?}
    Se importo_pagato è omesso → si assume pagamento completo del lordo (no sconto).
    """
    titolo = await db.titoli.find_one({"id": tid}, {"_id": 0})
    if not titolo:
        raise HTTPException(404, "Titolo non trovato")
    data_incasso = body.get("data_incasso") or _now_iso()[:10]
    mezzo = body.get("mezzo_pagamento") or "bonifico"
    conto_id = body.get("conto_cassa_id")
    lordo = float(titolo.get("importo_lordo") or 0)
    importo_pagato_raw = body.get("importo_pagato")
    importo_pagato = float(importo_pagato_raw) if importo_pagato_raw is not None else lordo
    sconto = round(max(0.0, lordo - importo_pagato), 2)
    motivo_sconto = body.get("motivo_sconto")

    await db.titoli.update_one(
        {"id": tid},
        {"$set": {
            "stato": "incassato",
            "data_incasso": data_incasso,
            "mezzo_pagamento": mezzo,
            "conto_cassa_id": conto_id,
            "importo_pagato": importo_pagato,
            "sconto_applicato": sconto,
            "motivo_sconto": motivo_sconto,
            "updated_at": _now_iso(),
        }},
    )
    pol = await db.polizze.find_one({"id": titolo["polizza_id"]}, {"_id": 0})

    # Movimento entrata = importo effettivamente pagato dal cliente
    mov_in = MovimentoContabile(
        data_movimento=data_incasso,
        tipo="entrata",
        categoria="incasso_premio",
        importo=importo_pagato,
        descrizione=f"Incasso titolo polizza {pol['numero_polizza'] if pol else titolo['polizza_id']}"
                    + (f" (era €{lordo:.2f}, sconto €{sconto:.2f})" if sconto > 0 else ""),
        polizza_id=titolo["polizza_id"],
        titolo_id=tid,
        anagrafica_id=pol.get("contraente_id") if pol else None,
        compagnia_id=pol.get("compagnia_id") if pol else None,
        conto_cassa_id=conto_id,
        mezzo_pagamento=mezzo,
        provvigioni=titolo.get("provvigioni", 0.0),
    )
    await db.movimenti.insert_one(mov_in.model_dump())

    # aggiorna anagrafica con ultimo mezzo di pagamento usato
    if pol and pol.get("contraente_id"):
        await db.anagrafiche.update_one(
            {"id": pol["contraente_id"]},
            {"$set": {
                "ultimo_mezzo_pagamento": mezzo,
                "ultimo_mezzo_pagamento_data": data_incasso,
                "updated_at": _now_iso(),
            }},
        )

    # Movimento uscita sconto (se applicato)
    mov_sconto_id = None
    if sconto > 0:
        mov_sconto = MovimentoContabile(
            data_movimento=data_incasso,
            tipo="uscita",
            categoria="sconto_cliente",
            importo=sconto,
            descrizione=(f"Sconto applicato su titolo {pol['numero_polizza'] if pol else ''}"
                         + (f" — {motivo_sconto}" if motivo_sconto else "")),
            polizza_id=titolo["polizza_id"],
            titolo_id=tid,
            anagrafica_id=pol.get("contraente_id") if pol else None,
            compagnia_id=pol.get("compagnia_id") if pol else None,
            conto_cassa_id=conto_id,
            mezzo_pagamento=mezzo,
        )
        await db.movimenti.insert_one(mov_sconto.model_dump())
        mov_sconto_id = mov_sconto.id

    # Audit nel diario cliente per tracciabilità storica
    if pol and pol.get("contraente_id"):
        desc = (f"Pagamento titolo polizza {pol.get('numero_polizza')} - "
                f"€{importo_pagato:.2f} via {mezzo} il {data_incasso}")
        if sconto > 0:
            desc += f" (sconto applicato: €{sconto:.2f}"
            if motivo_sconto:
                desc += f" - {motivo_sconto}"
            desc += ")"
        await log_diario_cliente(
            pol["contraente_id"], "documento",
            titolo=f"Incasso titolo - polizza {pol.get('numero_polizza')}",
            descrizione=desc, autore=user,
        )

    await log_attivita(user, "incasso", "titolo", tid,
                       f"€{importo_pagato:.2f} {('sconto €' + format(sconto, '.2f')) if sconto > 0 else ''}".strip())
    return {
        "ok": True,
        "importo_pagato": importo_pagato,
        "sconto_applicato": sconto,
        "movimento_entrata_id": mov_in.id,
        "movimento_sconto_id": mov_sconto_id,
    }


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
PIPELINE_STATI_VALIDI = {
    "polizze": {"in_emissione", "attiva", "sospesa", "scaduta", "annullata"},
    "sinistri": {"aperto", "in_istruttoria", "liquidato", "chiuso_senza_seguito", "respinto"},
    "titoli": {"da_incassare", "insoluto", "incassato", "stornato"},
}


@api.post("/pipeline/{entita}/{eid}/move")
async def pipeline_move(
    entita: str, eid: str, body: dict,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Sposta una card di pipeline in una nuova colonna (cambia stato).

    body: {nuovo_stato: 'attiva' | ...}
    Supporta sia pipeline built-in (polizze/sinistri/titoli) che pipeline custom.
    """
    nuovo = body.get("nuovo_stato") or body.get("colonna_key")
    if entita in PIPELINE_STATI_VALIDI:
        if nuovo not in PIPELINE_STATI_VALIDI[entita]:
            raise HTTPException(400, f"Stato non valido per {entita}: {nuovo}")
        coll = {"polizze": db.polizze, "sinistri": db.sinistri, "titoli": db.titoli}[entita]
        res = await coll.update_one(
            {"id": eid},
            {"$set": {"stato": nuovo, "updated_at": _now_iso()}},
        )
        if res.matched_count == 0:
            raise HTTPException(404, "Elemento non trovato")
        await log_attivita(user, "move_pipeline", entita, eid, f"Stato → {nuovo}")
        return {"ok": True, "id": eid, "stato": nuovo}
    # Pipeline custom: entita = pipeline_id, eid = card_id
    return await move_card(entita, eid, {"colonna_key": nuovo}, user)


@api.get("/pipeline/{entita}")
async def pipeline_data(entita: str, user=Depends(current_user)):
    """Ritorna dati per visualizzazione pipeline/kanban.

    entita: 'polizze' | 'sinistri' | 'titoli' | 'clienti' | 'email' | <id pipeline custom>
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

    # ===== PIPELINE CUSTOM (entita = id pipeline) =====
    pipeline = await db.pipelines_custom.find_one({"id": entita}, {"_id": 0})
    if pipeline:
        # Visibilità: admin vede tutto, gli altri vedono solo le proprie
        if user["role"] != "admin" and pipeline.get("operatore_id") not in (None, user.get("id")):
            raise HTTPException(403, "Pipeline non accessibile")
        colonne_def = sorted(pipeline.get("colonne", []), key=lambda c: c.get("ordine", 0))
        cards = await db.pipeline_cards.find(
            {"pipeline_id": entita, "archiviata": {"$ne": True}},
            {"_id": 0},
        ).sort([("colonna_key", 1), ("ordine", 1), ("created_at", -1)]).to_list(5000)
        # Arricchimento anagrafica / operatore
        ana_ids = list({c.get("anagrafica_id") for c in cards if c.get("anagrafica_id")})
        anas = {}
        if ana_ids:
            async for a in db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1}):
                anas[a["id"]] = a["ragione_sociale"]
        op_ids = list({c.get("operatore_id") for c in cards if c.get("operatore_id")})
        ops = {}
        if op_ids:
            async for u in db.users.find({"id": {"$in": op_ids}}, {"_id": 0, "id": 1, "name": 1}):
                ops[u["id"]] = u["name"]
        cols_out = []
        for cd in colonne_def:
            col_cards = [c for c in cards if c.get("colonna_key") == cd["key"]]
            cols_out.append({
                "key": cd["key"], "label": cd["label"], "colore": cd.get("colore"),
                "count": len(col_cards),
                "cards": [{
                    "id": c["id"], "title": c["titolo"],
                    "subtitle": anas.get(c.get("anagrafica_id", "")) or (c.get("descrizione") or "")[:50],
                    "footer": ops.get(c.get("operatore_id", "")) or "",
                    "extra": (f"€{c.get('valore_stimato', 0):.0f}" if c.get('valore_stimato') else "")
                             + (" · " + c.get("priorita", "") if c.get("priorita") else ""),
                    "date": c.get("scadenza"),
                    "link": f"/anagrafiche/{c['anagrafica_id']}" if c.get("anagrafica_id") else None,
                    "tags": c.get("tags", []),
                    "priorita": c.get("priorita"),
                    "card_id": c["id"],
                } for c in col_cards[:50]],
            })
        return {
            "entita": entita,
            "pipeline": {"id": pipeline["id"], "nome": pipeline["nome"], "tipo": pipeline.get("tipo"),
                         "icona": pipeline.get("icona"), "colore": pipeline.get("colore"),
                         "descrizione": pipeline.get("descrizione")},
            "colonne": cols_out,
            "editabile_struttura": True,  # frontend sa che può modificare colonne / cards
        }

    raise HTTPException(400, "Entità pipeline non supportata")


# ============================================================
# PIPELINE CUSTOM — CRUD pipelines + colonne + cards
# ============================================================
@api.get("/pipelines")
async def list_pipelines_custom(user=Depends(current_user)):
    """Elenco pipeline custom (built-in escluse). Filtra per visibilità."""
    flt = {}
    if user["role"] != "admin":
        flt = {"$or": [{"operatore_id": user.get("id")}, {"operatore_id": None}]}
    items = await db.pipelines_custom.find(flt, {"_id": 0}).sort("nome", 1).to_list(200)
    # arricchimento conteggio cards
    for p in items:
        n = await db.pipeline_cards.count_documents({"pipeline_id": p["id"], "archiviata": {"$ne": True}})
        p["cards_count"] = n
    return items


@api.post("/pipelines", status_code=201)
async def crea_pipeline(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    if not body.get("nome"):
        raise HTTPException(400, "Nome richiesto")
    # se non passa colonne, usa il template del tipo
    if not body.get("colonne"):
        body["colonne"] = _template_colonne(body.get("tipo", "generico"))
    body.setdefault("operatore_id", user.get("id"))
    obj = PipelineCustom(**body)
    await db.pipelines_custom.insert_one(obj.model_dump())
    await log_attivita(user, "create", "pipeline", obj.id, obj.nome)
    return obj.model_dump()


def _template_colonne(tipo: str) -> list:
    templates = {
        "marketing": [
            {"key": "lead", "label": "Lead", "colore": "#94A3B8", "ordine": 1},
            {"key": "contattato", "label": "Contattato", "colore": "#0EA5E9", "ordine": 2},
            {"key": "interessato", "label": "Interessato", "colore": "#F59E0B", "ordine": 3},
            {"key": "trattativa", "label": "Trattativa", "colore": "#7C3AED", "ordine": 4},
            {"key": "vinto", "label": "Vinto", "colore": "#10B981", "ordine": 5},
            {"key": "perso", "label": "Perso", "colore": "#EF4444", "ordine": 6},
        ],
        "vendita": [
            {"key": "qualificazione", "label": "Qualificazione", "colore": "#94A3B8", "ordine": 1},
            {"key": "proposta", "label": "Proposta", "colore": "#0EA5E9", "ordine": 2},
            {"key": "negoziazione", "label": "Negoziazione", "colore": "#F59E0B", "ordine": 3},
            {"key": "chiuso_vinto", "label": "Chiuso vinto", "colore": "#10B981", "ordine": 4},
            {"key": "chiuso_perso", "label": "Chiuso perso", "colore": "#EF4444", "ordine": 5},
        ],
        "onboarding": [
            {"key": "da_iniziare", "label": "Da iniziare", "colore": "#94A3B8", "ordine": 1},
            {"key": "documenti", "label": "Raccolta documenti", "colore": "#0EA5E9", "ordine": 2},
            {"key": "verifica", "label": "Verifica", "colore": "#F59E0B", "ordine": 3},
            {"key": "completato", "label": "Completato", "colore": "#10B981", "ordine": 4},
        ],
        "supporto": [
            {"key": "aperto", "label": "Aperto", "colore": "#0EA5E9", "ordine": 1},
            {"key": "in_lavorazione", "label": "In lavorazione", "colore": "#F59E0B", "ordine": 2},
            {"key": "in_attesa_cliente", "label": "In attesa cliente", "colore": "#94A3B8", "ordine": 3},
            {"key": "risolto", "label": "Risolto", "colore": "#10B981", "ordine": 4},
        ],
    }
    return templates.get(tipo, [
        {"key": "todo", "label": "Da fare", "colore": "#94A3B8", "ordine": 1},
        {"key": "in_corso", "label": "In corso", "colore": "#0EA5E9", "ordine": 2},
        {"key": "fatto", "label": "Fatto", "colore": "#10B981", "ordine": 3},
    ])


@api.get("/pipelines/{pid}")
async def get_pipeline(pid: str, user=Depends(current_user)):
    p = await db.pipelines_custom.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Pipeline non trovata")
    return p


@api.put("/pipelines/{pid}")
async def update_pipeline(pid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body.pop("id", None)
    body["updated_at"] = _now_iso()
    res = await db.pipelines_custom.update_one({"id": pid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Pipeline non trovata")
    return await db.pipelines_custom.find_one({"id": pid}, {"_id": 0})


@api.delete("/pipelines/{pid}")
async def delete_pipeline(pid: str, user=Depends(require_user("admin"))):
    await db.pipeline_cards.delete_many({"pipeline_id": pid})
    res = await db.pipelines_custom.delete_one({"id": pid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Pipeline non trovata")
    return {"ok": True}


# ----- Colonne (manipolazione singola colonna nella pipeline) -----
@api.post("/pipelines/{pid}/colonne")
async def aggiungi_colonna(pid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    if not body.get("label"):
        raise HTTPException(400, "Label colonna richiesto")
    p = await db.pipelines_custom.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Pipeline non trovata")
    key = body.get("key") or _slugify(body["label"])
    if any(c["key"] == key for c in p.get("colonne", [])):
        raise HTTPException(400, f"Esiste già una colonna con chiave '{key}'")
    nuova = PipelineColonna(
        key=key, label=body["label"], colore=body.get("colore"),
        ordine=body.get("ordine", len(p.get("colonne", [])) + 1),
        descrizione=body.get("descrizione"),
    ).model_dump()
    await db.pipelines_custom.update_one({"id": pid}, {"$push": {"colonne": nuova}, "$set": {"updated_at": _now_iso()}})
    return nuova


@api.put("/pipelines/{pid}/colonne/{col_key}")
async def modifica_colonna(pid: str, col_key: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    # rinomina, sposta, cambia colore
    set_ops = {}
    for k, v in body.items():
        if k in ("label", "colore", "descrizione", "ordine"):
            set_ops[f"colonne.$.{k}"] = v
    if not set_ops:
        raise HTTPException(400, "Nessun campo da modificare")
    set_ops["updated_at"] = _now_iso()
    res = await db.pipelines_custom.update_one(
        {"id": pid, "colonne.key": col_key},
        {"$set": set_ops},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Colonna non trovata")
    return {"ok": True}


@api.delete("/pipelines/{pid}/colonne/{col_key}")
async def elimina_colonna(pid: str, col_key: str,
                           sposta_in: Optional[str] = None,
                           user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Elimina una colonna. Se sposta_in è specificato, le card vengono spostate; altrimenti vengono archiviate."""
    p = await db.pipelines_custom.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Pipeline non trovata")
    rimanenti = [c for c in p.get("colonne", []) if c["key"] != col_key]
    if len(rimanenti) == len(p.get("colonne", [])):
        raise HTTPException(404, "Colonna non trovata")
    await db.pipelines_custom.update_one({"id": pid},
        {"$set": {"colonne": rimanenti, "updated_at": _now_iso()}})
    if sposta_in:
        if not any(c["key"] == sposta_in for c in rimanenti):
            raise HTTPException(400, f"Colonna destinazione '{sposta_in}' non esiste")
        await db.pipeline_cards.update_many(
            {"pipeline_id": pid, "colonna_key": col_key},
            {"$set": {"colonna_key": sposta_in, "updated_at": _now_iso()}},
        )
    else:
        await db.pipeline_cards.update_many(
            {"pipeline_id": pid, "colonna_key": col_key},
            {"$set": {"archiviata": True, "updated_at": _now_iso()}},
        )
    return {"ok": True}


# ----- Cards CRUD -----
@api.post("/pipelines/{pid}/cards", status_code=201)
async def crea_card(pid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    p = await db.pipelines_custom.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Pipeline non trovata")
    cols = p.get("colonne", [])
    if not cols:
        raise HTTPException(400, "La pipeline non ha colonne")
    col_key = body.get("colonna_key") or cols[0]["key"]
    if not any(c["key"] == col_key for c in cols):
        raise HTTPException(400, f"Colonna '{col_key}' non esiste")
    body["pipeline_id"] = pid
    body["colonna_key"] = col_key
    body.setdefault("operatore_id", user.get("id"))
    obj = PipelineCard(**body)
    await db.pipeline_cards.insert_one(obj.model_dump())
    await log_attivita(user, "create", "pipeline_card", obj.id, obj.titolo)
    return obj.model_dump()


@api.put("/pipelines/{pid}/cards/{card_id}")
async def update_card(pid: str, card_id: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body.pop("id", None)
    body.pop("pipeline_id", None)
    body["updated_at"] = _now_iso()
    res = await db.pipeline_cards.update_one(
        {"id": card_id, "pipeline_id": pid}, {"$set": body},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Card non trovata")
    return await db.pipeline_cards.find_one({"id": card_id}, {"_id": 0})


@api.delete("/pipelines/{pid}/cards/{card_id}")
async def delete_card(pid: str, card_id: str, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    res = await db.pipeline_cards.delete_one({"id": card_id, "pipeline_id": pid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Card non trovata")
    return {"ok": True}


@api.post("/pipelines/{pid}/cards/{card_id}/move")
async def move_card(pid: str, card_id: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Sposta una card in una nuova colonna della stessa pipeline."""
    nuova_col = body.get("nuovo_stato") or body.get("colonna_key")
    if not nuova_col:
        raise HTTPException(400, "colonna_key richiesto")
    p = await db.pipelines_custom.find_one({"id": pid}, {"_id": 0, "colonne": 1})
    if not p:
        raise HTTPException(404, "Pipeline non trovata")
    if not any(c["key"] == nuova_col for c in p.get("colonne", [])):
        raise HTTPException(400, f"Colonna '{nuova_col}' non esiste in questa pipeline")
    res = await db.pipeline_cards.update_one(
        {"id": card_id, "pipeline_id": pid},
        {"$set": {"colonna_key": nuova_col, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Card non trovata")
    await log_attivita(user, "move_card", "pipeline_card", card_id, f"→ {nuova_col}")
    return {"ok": True}


def _slugify(s: str) -> str:
    import re as _re
    s = _re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")
    return s[:40] or "col"


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
    email_doc = await db.email.find_one({"id": eid}, {"_id": 0})
    if not email_doc:
        raise HTTPException(404, "Non trovata")
    await db.email.update_one(
        {"id": eid},
        {"$set": {"stato": "inviata", "data_invio": _now_iso(), "updated_at": _now_iso()}},
    )
    await log_attivita(user, "invio", "email", eid, "Email inviata (mock)")
    # auto-traccia nel diario del cliente
    if email_doc.get("destinatario_anagrafica_id"):
        await log_diario_cliente(
            email_doc["destinatario_anagrafica_id"], "email",
            titolo=f"📧 Email inviata: {email_doc.get('oggetto', '')}",
            descrizione=(email_doc.get("corpo") or "")[:500],
            autore=user,
        )
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
# LIBRERIE — AZIENDA (DATI INTESTAZIONE / STAMPE)
# ============================================================
@api.get("/librerie/azienda")
async def get_azienda(user=Depends(current_user)):
    """Singleton: dati dell'agenzia (usati nelle stampe)."""
    doc = await db.azienda_config.find_one({}, {"_id": 0})
    if not doc:
        # crea record vuoto al primo accesso (solo se admin)
        cfg = AziendaConfig()
        await db.azienda_config.insert_one(cfg.model_dump())
        doc = cfg.model_dump()
    return doc


@api.put("/librerie/azienda")
async def update_azienda(body: dict, user=Depends(require_user("admin"))):
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


@api.post("/librerie/azienda/logo")
async def upload_logo_azienda(file: UploadFile = File(...),
                               user=Depends(require_user("admin"))):
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
@api.get("/librerie/schema-provvigionale")
async def list_schemi_provvigionali(
    collaboratore_id: Optional[str] = None,
    compagnia_id: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
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


@api.post("/librerie/schema-provvigionale", status_code=201)
async def create_schema_provvigionale(body: dict, user=Depends(require_user("admin"))):
    body = {k: (v if v != "" else None) for k, v in body.items()}
    obj = SchemaProvvigionale(**body)
    await db.schema_provvigionale.insert_one(obj.model_dump())
    await log_attivita(user, "create", "schema_provvigionale", obj.id, f"Schema '{obj.nome}'")
    return obj.model_dump()


@api.put("/librerie/schema-provvigionale/{sid}")
async def update_schema_provvigionale(sid: str, body: dict, user=Depends(require_user("admin"))):
    body = {k: (v if v != "" else None) for k, v in body.items()}
    body.pop("id", None)
    body["updated_at"] = _now_iso()
    res = await db.schema_provvigionale.update_one({"id": sid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Schema non trovato")
    await log_attivita(user, "update", "schema_provvigionale", sid)
    return await db.schema_provvigionale.find_one({"id": sid}, {"_id": 0})


@api.delete("/librerie/schema-provvigionale/{sid}")
async def delete_schema_provvigionale(sid: str, user=Depends(require_user("admin"))):
    res = await db.schema_provvigionale.delete_one({"id": sid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Schema non trovato")
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


@api.get("/librerie/schema-provvigionale/risolvi")
async def api_risolvi_provvigione(
    collaboratore_id: str,
    compagnia_id: Optional[str] = None,
    ramo: Optional[str] = None,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    perc = await risolvi_provvigione_collaboratore(collaboratore_id, compagnia_id, ramo)
    return {"percentuale_collaboratore": perc}


# ============================================================
# UTENTI — DOCUMENTI E CORSI (firma digitale, CI, casellario, ecc.)
# ============================================================
ALLOWED_USER_DOCS = {
    "firma_digitale": "firma_digitale_url",
    "carta_identita": "carta_identita_url",
    "casellario": "casellario_url",
    "carichi_pendenti": "carichi_pendenti_url",
    "documento_iban": "documento_iban_url",
}


@api.post("/auth/users/{uid}/documenti/{doc_tipo}")
async def upload_documento_utente(
    uid: str, doc_tipo: str,
    file: UploadFile = File(...),
    user=Depends(require_user("admin")),
):
    """Carica un documento (firma_digitale | carta_identita | casellario | carichi_pendenti | documento_iban)."""
    if doc_tipo not in ALLOWED_USER_DOCS:
        raise HTTPException(400, f"Tipo documento non valido: {doc_tipo}")
    target = await db.users.find_one({"id": uid}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 10 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    ext = (file.filename or "doc.bin").rsplit(".", 1)[-1].lower() or "bin"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/users/{uid}/{doc_tipo}_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, ct)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    url = f"/api/storage/{result['path']}"
    field = ALLOWED_USER_DOCS[doc_tipo]
    await db.users.update_one({"id": uid}, {"$set": {field: url, "updated_at": _now_iso()}})
    await log_attivita(user, "upload", "user_doc", uid, f"Caricato {doc_tipo} per {uid}")
    return {field: url}


@api.delete("/auth/users/{uid}/documenti/{doc_tipo}")
async def delete_documento_utente(uid: str, doc_tipo: str,
                                   user=Depends(require_user("admin"))):
    if doc_tipo not in ALLOWED_USER_DOCS:
        raise HTTPException(400, "Tipo documento non valido")
    field = ALLOWED_USER_DOCS[doc_tipo]
    await db.users.update_one({"id": uid}, {"$set": {field: None, "updated_at": _now_iso()}})
    return {"ok": True}


@api.post("/auth/users/{uid}/corsi")
async def aggiungi_corso_utente(
    uid: str, body: dict,
    user=Depends(require_user("admin")),
):
    """Aggiunge un corso/attestato al collaboratore. body: {titolo, ente, data_scadenza, url_attestato}"""
    target = await db.users.find_one({"id": uid}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    corso = {
        "id": _uid(),
        "titolo": body.get("titolo") or "Corso",
        "ente": body.get("ente"),
        "data": body.get("data"),
        "data_scadenza": body.get("data_scadenza"),
        "url_attestato": body.get("url_attestato"),
        "note": body.get("note"),
    }
    await db.users.update_one({"id": uid}, {"$push": {"corsi": corso}, "$set": {"updated_at": _now_iso()}})
    return corso


@api.post("/auth/users/{uid}/corsi/upload")
async def upload_attestato_corso(
    uid: str,
    file: UploadFile = File(...),
    titolo: str = "",
    ente: str = "",
    data_scadenza: str = "",
    user=Depends(require_user("admin")),
):
    target = await db.users.find_one({"id": uid}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Utente non trovato")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 10 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    ext = (file.filename or "doc.pdf").rsplit(".", 1)[-1].lower() or "pdf"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/users/{uid}/corso_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, ct)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    corso = {
        "id": _uid(),
        "titolo": titolo or (file.filename or "Corso"),
        "ente": ente or None,
        "data_scadenza": data_scadenza or None,
        "url_attestato": f"/api/storage/{result['path']}",
        "nome_file": file.filename,
    }
    await db.users.update_one({"id": uid}, {"$push": {"corsi": corso}, "$set": {"updated_at": _now_iso()}})
    return corso


@api.delete("/auth/users/{uid}/corsi/{corso_id}")
async def elimina_corso_utente(uid: str, corso_id: str,
                                user=Depends(require_user("admin"))):
    await db.users.update_one({"id": uid}, {"$pull": {"corsi": {"id": corso_id}}})
    return {"ok": True}


# ============================================================
# DIARIO CLIENTE
# ============================================================
@api.get("/anagrafiche/{aid}/riepilogo")
async def riepilogo_cliente(aid: str, user=Depends(current_user)):
    """Riepilogo economico: premi lordi pagati + provvigioni incassate.

    Se l'anagrafica ha relazioni con persone giuridiche (aziende), aggrega anche
    quelle ma le riporta separatamente. Risultato:
    { privato: {premi, provvigioni, polizze_count, titoli_count},
      azienda: {premi, provvigioni, ...},
      totale: {...} }
    """
    if user["role"] == "cliente" and user.get("anagrafica_id") != aid:
        raise HTTPException(403, "Permesso negato")
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica non trovata")

    # raccogli id privati e aziende collegate
    privati = [aid] if ana.get("tipo") != "persona_giuridica" else []
    aziende = [aid] if ana.get("tipo") == "persona_giuridica" else []
    for rel in (ana.get("parente_di") or []):
        rid = rel.get("anagrafica_id")
        if not rid: continue
        rel_doc = await db.anagrafiche.find_one({"id": rid}, {"_id": 0, "tipo": 1})
        if rel_doc:
            if rel_doc.get("tipo") == "persona_giuridica":
                aziende.append(rid)
            else:
                privati.append(rid)

    async def aggrega(ids: list):
        if not ids:
            return {"premi_lordi": 0.0, "provvigioni": 0.0, "polizze_count": 0,
                    "titoli_incassati": 0, "titoli_aperti": 0}
        pol_ids = [p["id"] async for p in db.polizze.find(
            {"contraente_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        if not pol_ids:
            return {"premi_lordi": 0.0, "provvigioni": 0.0,
                    "polizze_count": 0, "titoli_incassati": 0, "titoli_aperti": 0}
        # somma titoli incassati
        agg = await db.titoli.aggregate([
            {"$match": {"polizza_id": {"$in": pol_ids}, "stato": "incassato"}},
            {"$group": {"_id": None,
                        "premi": {"$sum": "$importo_lordo"},
                        "provv": {"$sum": "$provvigioni"},
                        "n": {"$sum": 1}}},
        ]).to_list(1)
        n_aperti = await db.titoli.count_documents({"polizza_id": {"$in": pol_ids},
                                                     "stato": {"$in": ["da_incassare", "insoluto"]}})
        return {
            "premi_lordi": round((agg[0]["premi"] if agg else 0.0), 2),
            "provvigioni": round((agg[0]["provv"] if agg else 0.0), 2),
            "polizze_count": len(pol_ids),
            "titoli_incassati": agg[0]["n"] if agg else 0,
            "titoli_aperti": n_aperti,
        }

    priv = await aggrega(privati)
    az = await aggrega(aziende)
    tot = {
        "premi_lordi": round(priv["premi_lordi"] + az["premi_lordi"], 2),
        "provvigioni": round(priv["provvigioni"] + az["provvigioni"], 2),
        "polizze_count": priv["polizze_count"] + az["polizze_count"],
        "titoli_incassati": priv["titoli_incassati"] + az["titoli_incassati"],
        "titoli_aperti": priv["titoli_aperti"] + az["titoli_aperti"],
    }
    return {"anagrafica": ana, "privato": priv, "azienda": az, "totale": tot,
            "ids_privati": privati, "ids_aziende": aziende}


@api.post("/anagrafiche/tags/auto-genera")
async def auto_genera_tags(user=Depends(require_user("admin", "collaboratore"))):
    """Genera tag automatici per tutte le anagrafiche.

    Tag generati:
      - genitore_con_figli_minori (se ha relazioni 'figlio' con anagrafiche con data_nascita < 18 anni fa)
      - figli_minori (alias, su richiesta utente)
      - gen_anni_XX
      - cliente_attivo / prospect / top_cliente
      - dipendente / autonomo / professionista / imprenditore / pensionato (da tipologia_lavoratore)
    """
    from datetime import date
    today = date.today()
    AUTO_TAGS_GESTITI = {
        "genitore_con_figli_minori", "figli_minori",
        "cliente_attivo", "prospect", "top_cliente",
        "anziano_over_65", "giovane_under_30",
        "dipendente", "autonomo", "professionista", "imprenditore",
        "pensionato", "disoccupato", "studente", "casalinga",
    }
    aggiornate = 0
    cursor = db.anagrafiche.find({}, {"_id": 0})
    async for ana in cursor:
        existing_manual = [t for t in (ana.get("tags") or [])
                           if not (t.startswith("gen_") or t in AUTO_TAGS_GESTITI)]
        auto = []
        # generazione
        if ana.get("data_nascita"):
            try:
                d = date.fromisoformat(ana["data_nascita"])
                eta = today.year - d.year - (1 if (today.month, today.day) < (d.month, d.day) else 0)
                decade = (d.year // 10) * 10
                auto.append(f"gen_anni_{str(decade)[-2:]}")
                if eta >= 65: auto.append("anziano_over_65")
                if eta < 30: auto.append("giovane_under_30")
            except Exception:
                pass
        # genitore con figli minori (genera entrambi i tag: completo + breve)
        for rel in (ana.get("parente_di") or []):
            if rel.get("relazione") != "figlio": continue
            child = await db.anagrafiche.find_one({"id": rel.get("anagrafica_id")}, {"_id": 0, "data_nascita": 1})
            if not child or not child.get("data_nascita"): continue
            try:
                cd = date.fromisoformat(child["data_nascita"])
                eta_f = today.year - cd.year
                if eta_f < 18:
                    auto.append("genitore_con_figli_minori")
                    auto.append("figli_minori")
                    break
            except Exception:
                continue
        # tipologia lavoratore
        tl = ana.get("tipologia_lavoratore")
        if tl:
            auto.append(tl)
        # stato cliente
        n_attive = await db.polizze.count_documents({"contraente_id": ana["id"], "stato": "attiva"})
        if n_attive == 0:
            auto.append("prospect")
        elif n_attive >= 4:
            auto.append("top_cliente"); auto.append("cliente_attivo")
        else:
            auto.append("cliente_attivo")
        nuovi_tags = sorted(set(existing_manual + auto))
        await db.anagrafiche.update_one({"id": ana["id"]}, {"$set": {"tags": nuovi_tags, "updated_at": _now_iso()}})
        aggiornate += 1
    await log_attivita(user, "auto_tag", "anagrafica", None, f"Tag auto generati su {aggiornate} anagrafiche")
    return {"aggiornate": aggiornate}


@api.get("/anagrafiche/tags/elenco")
async def elenco_tags(user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Lista tag distinti con conteggio."""
    pipeline = [
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    res = await db.anagrafiche.aggregate(pipeline).to_list(500)
    return [{"tag": r["_id"], "count": r["count"]} for r in res]


@api.post("/newsletter/invia")
async def newsletter_invia(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    """Crea email in coda per tutti i clienti che matchano i tag (any-of).

    body: { tags: [...], oggetto, corpo }
    """
    tags = body.get("tags") or []
    oggetto = body.get("oggetto", "").strip()
    corpo = body.get("corpo", "").strip()
    if not oggetto or not corpo:
        raise HTTPException(400, "Oggetto e corpo richiesti")
    flt = {"tags": {"$in": tags}} if tags else {}
    flt["email"] = {"$nin": ["", None]}
    targets = await db.anagrafiche.find(flt, {"_id": 0, "id": 1, "email": 1, "ragione_sociale": 1}).to_list(10000)
    creati = 0
    for t in targets:
        if not t.get("email"): continue
        e = EmailMessaggio(
            destinatario_anagrafica_id=t["id"], destinatario_email=t["email"],
            oggetto=oggetto, corpo=corpo.replace("{{nome}}", t.get("ragione_sociale", "")),
            template="newsletter", stato="in_coda", autore_id=user["id"],
        )
        await db.email.insert_one(e.model_dump())
        creati += 1
    await log_attivita(user, "newsletter", "email", None,
                       f"Newsletter su tags {tags}: {creati} email create")
    return {"email_create": creati, "tags": tags}


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
    # auto-traccia nel diario se l'allegato è su anagrafica/polizza/sinistro di un cliente
    anag_id_for_diario = None
    if entita_tipo == "anagrafica":
        anag_id_for_diario = entita_id
    elif entita_tipo in ("polizza", "sinistro"):
        coll = db.polizze if entita_tipo == "polizza" else db.sinistri
        target = await coll.find_one({"id": entita_id}, {"_id": 0, "contraente_id": 1})
        if target:
            anag_id_for_diario = target.get("contraente_id")
    if anag_id_for_diario:
        await log_diario_cliente(
            anag_id_for_diario, "documento_inviato" if False else "altro",
            titolo=f"📎 Documento caricato: {file.filename}",
            descrizione=f"Allegato a {entita_tipo} (size: {result.get('size', len(data))} bytes)" + (f" - {descrizione}" if descrizione else ""),
            autore=user,
        )
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
# STORAGE GENERICO (logo azienda, documenti utente, attestati)
# Path canonico: /api/storage/{full_path}
# ============================================================
@api.get("/storage/{full_path:path}")
async def serve_storage(full_path: str, user=Depends(current_user)):
    """Serve file dallo storage. ACL:
    - file in /users/{uid}/...   -> solo admin o proprietario
    - file in /azienda/...       -> qualunque utente autenticato (logo per stampe)
    - file in /titoli/... ecc.   -> qualunque utente autenticato (gli allegati hanno ACL specifica)
    """
    # ACL sui documenti utente
    parts = full_path.split("/")
    if "users" in parts:
        try:
            idx = parts.index("users")
            owner_uid = parts[idx + 1]
        except (ValueError, IndexError):
            owner_uid = None
        if user["role"] != "admin" and user["id"] != owner_uid:
            raise HTTPException(403, "Permesso negato")
    try:
        data, ctype = obj_storage.get_object(full_path)
    except Exception as e:
        raise HTTPException(404, f"File non trovato: {e}")
    filename = full_path.rsplit("/", 1)[-1]
    return StreamingResponse(
        _io.BytesIO(data),
        media_type=ctype or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
    # auto-traccia nel diario se l'interlocutore è un cliente
    cliente_user = None
    if dest.get("role") == "cliente" and dest.get("anagrafica_id"):
        cliente_user = dest
    elif user.get("role") == "cliente" and user.get("anagrafica_id"):
        cliente_user = user
    if cliente_user:
        direction = "→" if user.get("role") != "cliente" else "←"
        titolo = f"💬 Chat {direction} {cliente_user.get('name')}"
        desc = txt[:300] + (" [+ allegato]" if allegato_nome else "")
        await log_diario_cliente(cliente_user["anagrafica_id"], "chat", titolo, desc, autore=user)
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
        **(await _intestazione_pdf()),
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
        **(await _intestazione_pdf()),
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
        **(await _intestazione_pdf()),
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
        **(await _intestazione_pdf()),
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
        **(await _intestazione_pdf()),
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
        **(await _intestazione_pdf()),
    )
    return _pdf_response(pdf, f"estratto_{ana['ragione_sociale']}.pdf")


# ============================================================
# HEALTH
# ============================================================
@api.get("/")
async def root():
    return {"app": "Programma Assicurativo", "status": "ok"}


# ============================================================
# CALENDARIO — Eventi agenzia / per operatore
# ============================================================
@api.get("/calendario")
async def list_eventi(
    dal: Optional[str] = None,
    al: Optional[str] = None,
    operatore_id: Optional[str] = None,
    tipo: Optional[str] = None,
    includi_scadenze: bool = True,
    user=Depends(current_user),
):
    """Restituisce eventi calendario. Se includi_scadenze=True aggiunge auto-eventi
    sintetici per scadenze polizze e titoli."""
    flt: dict = {}
    if dal or al:
        cond = {}
        if dal: cond["$gte"] = dal
        if al: cond["$lte"] = al + "T23:59:59"
        flt["inizio"] = cond
    if operatore_id:
        flt["$or"] = [{"operatore_id": operatore_id},
                      {"partecipanti_user_ids": operatore_id}]
    if tipo:
        flt["tipo"] = tipo
    if user["role"] == "cliente":
        flt["anagrafica_id"] = user.get("anagrafica_id")
    items = await db.calendario.find(flt, {"_id": 0}).sort("inizio", 1).to_list(2000)

    # arricchimento nome operatore
    op_ids = {e.get("operatore_id") for e in items if e.get("operatore_id")}
    if op_ids:
        op_map = {u["id"]: u["name"] async for u in
                  db.users.find({"id": {"$in": list(op_ids)}}, {"_id": 0, "id": 1, "name": 1})}
        for e in items:
            if e.get("operatore_id"):
                e["operatore_nome"] = op_map.get(e["operatore_id"])

    # scadenze auto
    if includi_scadenze and user["role"] != "cliente":
        scad_flt: dict = {"stato": "attiva"}
        if dal or al:
            cond = {}
            if dal: cond["$gte"] = dal
            if al: cond["$lte"] = al
            scad_flt["scadenza"] = cond
        async for p in db.polizze.find(scad_flt, {"_id": 0, "id": 1, "numero_polizza": 1, "scadenza": 1, "collaboratore_id": 1, "contraente_id": 1, "ramo": 1}):
            if operatore_id and p.get("collaboratore_id") != operatore_id:
                continue
            if not p.get("scadenza"):
                continue
            items.append({
                "id": f"_pol_{p['id']}", "titolo": f"Scadenza polizza {p.get('numero_polizza')}",
                "inizio": p.get("scadenza") + "T09:00:00",
                "tutto_il_giorno": True,
                "tipo": "scadenza_polizza",
                "polizza_id": p.get("id"),
                "anagrafica_id": p.get("contraente_id"),
                "operatore_id": p.get("collaboratore_id"),
                "colore": "#dc2626",
                "descrizione": f"Ramo {p.get('ramo')}",
                "stato": "confermato",
                "_auto": True,
            })
    items.sort(key=lambda e: e.get("inizio", ""))
    return items


@api.post("/calendario", status_code=201)
async def crea_evento(body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body.setdefault("operatore_id", user.get("id"))
    obj = EventoCalendario(**body)
    await db.calendario.insert_one(obj.model_dump())
    await log_attivita(user, "create", "evento", obj.id, obj.titolo)
    return obj.model_dump()


@api.put("/calendario/{eid}")
async def aggiorna_evento(eid: str, body: dict, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    body.pop("id", None)
    body["updated_at"] = _now_iso()
    res = await db.calendario.update_one({"id": eid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Evento non trovato")
    return await db.calendario.find_one({"id": eid}, {"_id": 0})


@api.delete("/calendario/{eid}")
async def elimina_evento(eid: str, user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    res = await db.calendario.delete_one({"id": eid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Evento non trovato")
    return {"ok": True}


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
