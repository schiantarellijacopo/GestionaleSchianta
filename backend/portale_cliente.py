"""Portale Cliente — API dedicate al self-service del cliente finale.

Autenticazione: email (username) + password = codice_fiscale (privato) o
partita_iva (azienda). Il cliente vede SOLO i dati/allegati con
`visibile_cliente=true` collegati alla sua anagrafica (o ai nuclei collegati
se `is_master=true`).

Endpoints (prefix `/api/portale`):
  * POST /auth/login              → JWT client-token
  * GET  /me                      → profilo + eventuali nuclei collegati
  * GET  /polizze                 → polizze attive + storiche visibili
  * GET  /polizze/{pid}/pdf       → download frontespizio polizza (se presente)
  * GET  /titoli                  → titoli visibili con stato + quietanze allegate
  * GET  /documenti               → tutti gli allegati visibili al cliente
  * POST /documenti/upload        → upload rapido da smartphone
  * GET  /sinistri                → sinistri collegati
  * PUT  /anagrafica/richiesta    → invia richiesta modifica anagrafica
  * GET  /servizi                 → servizi collegati dall'agenzia
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header

router = APIRouter(prefix="/api/portale", tags=["portale-cliente"])
JWT_ALG = "HS256"
TOKEN_TTL_HOURS = 24


def _secret() -> str:
    return os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY") or "changeme"


def _issue_token(anagrafica_id: str, tenant_id: Optional[str] = None) -> str:
    payload = {
        "aid": anagrafica_id,
        "tid": tenant_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
        "sub": "portale_cliente",
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALG)


async def current_cliente(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency che verifica il JWT e restituisce l'anagrafica del cliente."""
    from server import db
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Token mancante")
    tok = authorization.split(" ", 1)[1]
    try:
        p = jwt.decode(tok, _secret(), algorithms=[JWT_ALG])
        if p.get("sub") != "portale_cliente":
            raise ValueError("bad subject")
    except Exception as e:
        raise HTTPException(401, f"Token non valido: {e}")
    ana = await db.anagrafiche.find_one({"id": p["aid"]}, {"_id": 0})
    if not ana:
        raise HTTPException(404, "Anagrafica cliente non trovata")
    return ana


def _norm(s: str) -> str:
    return (s or "").strip().lower()


# ============================================================
# AUTH
# ============================================================
@router.post("/auth/login")
async def login_cliente(body: dict):
    """Login cliente: email + password = codice_fiscale (privato) o partita_iva (azienda)."""
    from server import db
    email = _norm(body.get("email") or body.get("username"))
    password = (body.get("password") or "").strip()
    if not email or not password:
        raise HTTPException(400, "Email e password obbligatorie")

    # Cerca TUTTE le anagrafiche con quella email/PEC (possono esserci duplicati:
    # es. familiari o soci che condividono email). Prova la password su ciascuna.
    ana_list = await db.anagrafiche.find(
        {"$or": [{"email": {"$regex": f"^{email}$", "$options": "i"}},
                 {"pec": {"$regex": f"^{email}$", "$options": "i"}}]},
        {"_id": 0},
    ).to_list(20)
    if not ana_list:
        raise HTTPException(401, "Credenziali non valide")

    pwd_norm = password.strip().upper()
    ana = None
    for a in ana_list:
        cf = _norm(a.get("codice_fiscale"))
        piva = _norm(a.get("partita_iva"))
        if (cf and pwd_norm == cf.upper()) or (piva and pwd_norm == piva.upper()):
            ana = a
            break
    if not ana:
        raise HTTPException(401, "Credenziali non valide")

    token = _issue_token(ana["id"], tenant_id=ana.get("tenant_id"))
    return {
        "access_token": token,
        "cliente": {
            "id": ana["id"],
            "nome": ana.get("ragione_sociale") or ana.get("cognome_nome")
                    or f"{ana.get('cognome','')} {ana.get('nome','')}".strip(),
            "email": ana.get("email"),
            "cellulare": ana.get("cellulare"),
            "tipo_soggetto": ana.get("tipo_soggetto"),
            "is_master": bool(ana.get("is_master")),
        },
    }


# ============================================================
# PROFILO
# ============================================================
@router.get("/agenzia")
async def get_agenzia_info(cliente=Depends(current_cliente)):
    """Info dell'agenzia da mostrare nel Portale (logo + contatti + branding)."""
    from server import db
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    logo = az.get("logo_url")
    if az.get("logo_storage_path") or (logo or "").startswith("/api/storage/"):
        logo = "/api/portale/public/logo"
    return {
        "ragione_sociale": az.get("ragione_sociale") or "La tua agenzia",
        "logo_url": logo,
        "telefono": az.get("telefono"),
        "email": az.get("email"),
        "pec": az.get("pec"),
        "indirizzo": az.get("indirizzo"),
        "comune": az.get("comune"),
        "provincia": az.get("provincia"),
        "cap": az.get("cap"),
        "sito_web": az.get("sito_web"),
        "rui": az.get("rui"),
        "slogan": az.get("slogan_portale"),
        "orari": az.get("portale_orari") or [],
        "sedi": az.get("portale_sedi") or [],
        "team": [
            {
                "id": m.get("id"),
                "nome": m.get("nome"),
                "ruolo": m.get("ruolo"),
                "descrizione": m.get("descrizione"),
                "telefono": m.get("telefono"),
                "email": m.get("email"),
                "foto_url": f"/api/portale/public/team-foto/{m.get('id')}" if m.get("foto_path") else None,
            }
            for m in (az.get("portale_team") or [])
        ],
        "assistenza_compagnie": az.get("assistenza_compagnie") or [],
    }


@router.get("/me/avatar")
async def get_me_avatar(cliente=Depends(current_cliente)):
    """Foto profilo del cliente (se presente in anagrafica)."""
    from server import db, obj_storage
    from fastapi.responses import StreamingResponse
    import io
    ana = await db.anagrafiche.find_one({"id": cliente["id"]}, {"_id": 0, "avatar_url": 1}) or {}
    url = ana.get("avatar_url") or ""
    if not url.startswith("/api/storage/"):
        raise HTTPException(404, "Avatar non presente")
    try:
        data, ctype = obj_storage.get_object(url[len("/api/storage/"):])
    except Exception:
        raise HTTPException(404, "Avatar non disponibile")
    return StreamingResponse(io.BytesIO(data), media_type=ctype or "image/jpeg",
                             headers={"Cache-Control": "private, max-age=600"})


@router.get("/me")
async def get_me(cliente=Depends(current_cliente)):
    """Restituisce dati anagrafica cliente + nuclei collegati (se master)."""
    from server import db
    out = {
        "id": cliente["id"],
        "nome": cliente.get("ragione_sociale") or cliente.get("cognome_nome")
                or f"{cliente.get('cognome','')} {cliente.get('nome','')}".strip(),
        "cognome": cliente.get("cognome"),
        "nome_": cliente.get("nome"),
        "ragione_sociale": cliente.get("ragione_sociale"),
        "codice_fiscale": cliente.get("codice_fiscale"),
        "partita_iva": cliente.get("partita_iva"),
        "email": cliente.get("email"),
        "pec": cliente.get("pec"),
        "cellulare": cliente.get("cellulare"),
        "telefono": cliente.get("telefono"),
        # Indirizzo — priorità al campo diretto, poi al suffisso _residenza (compatibilità)
        "indirizzo": cliente.get("indirizzo") or cliente.get("indirizzo_residenza"),
        "comune": cliente.get("comune") or cliente.get("comune_residenza"),
        "provincia": cliente.get("provincia") or cliente.get("provincia_residenza"),
        "cap": cliente.get("cap") or cliente.get("cap_residenza"),
        "nazione": cliente.get("nazione") or "ITALIA",
        # Dati bancari
        "iban": cliente.get("iban"),
        "banca": cliente.get("banca"),
        # Dati anagrafici (persona fisica)
        "data_nascita": cliente.get("data_nascita"),
        "comune_nascita": cliente.get("comune_nascita"),
        "provincia_nascita": cliente.get("provincia_nascita"),
        "sesso": cliente.get("sesso"),
        "stato_civile": cliente.get("stato_civile"),
        # Dati azienda (persona giuridica)
        "sede_legale": cliente.get("sede_legale"),
        "rea": cliente.get("rea"),
        "tipo_soggetto": cliente.get("tipo_soggetto"),
        "professione": cliente.get("professione"),
        "tipologia_lavoratore": cliente.get("tipologia_lavoratore"),
        "is_master": bool(cliente.get("is_master")),
        "nuclei_collegati": [],
    }
    # Nuclei collegati (se master)
    if cliente.get("is_master"):
        async for a in db.anagrafiche.find(
            {"$or": [
                {"master_anagrafica_id": cliente["id"]},
                {"gruppo_familiare_id": cliente.get("gruppo_familiare_id")}
            ], "id": {"$ne": cliente["id"]}},
            {"_id": 0, "id": 1, "cognome": 1, "nome": 1, "ragione_sociale": 1, "cognome_nome": 1},
        ):
            out["nuclei_collegati"].append({
                "id": a["id"],
                "nome": a.get("ragione_sociale") or a.get("cognome_nome")
                        or f"{a.get('cognome','')} {a.get('nome','')}".strip(),
            })
    return out


# ============================================================
# POLIZZE (attive + storiche visibili)
# ============================================================
@router.get("/polizze")
async def list_polizze(cliente=Depends(current_cliente),
                       includi_storiche: bool = True):
    """Elenco polizze del cliente. Include applicazioni libro matricola e stats titoli."""
    from server import db
    flt = {"contraente_id": cliente["id"]}
    polizze = await db.polizze.find(flt, {"_id": 0}).sort("scadenza", -1).to_list(500)

    oggi = datetime.now(timezone.utc).date().isoformat()
    for p in polizze:
        # Applicazioni Libro Matricola
        p["applicazioni"] = []
        if p.get("is_libro_matricola"):
            apps = await db.applicazioni.find(
                {"polizza_id": p["id"]}, {"_id": 0},
            ).sort("numero", 1).to_list(2000)
            p["applicazioni"] = apps
        # Compagnia
        if p.get("compagnia_id"):
            c = await db.compagnie.find_one({"id": p["compagnia_id"]}, {"_id": 0, "ragione_sociale": 1, "logo_url": 1})
            p["compagnia_nome"] = (c or {}).get("ragione_sociale")
            p["compagnia_logo"] = (c or {}).get("logo_url")
        # Statistiche titoli
        n_da_pagare = await db.titoli.count_documents({"polizza_id": p["id"], "stato": "da_incassare"})
        n_arretrati = await db.titoli.count_documents({
            "polizza_id": p["id"], "stato": "da_incassare",
            "scadenza": {"$lt": oggi}})
        # Prossima quietanza
        prox = await db.titoli.find_one(
            {"polizza_id": p["id"], "stato": "da_incassare"},
            {"_id": 0, "scadenza": 1, "importo_lordo": 1},
            sort=[("scadenza", 1)],
        )
        p["stats_titoli"] = {
            "da_pagare": n_da_pagare,
            "arretrati": n_arretrati,
            "prossima_scadenza": prox.get("scadenza") if prox else None,
            "prossimo_importo": prox.get("importo_lordo") if prox else None,
        }
        # Allegati visibili
        p["n_allegati"] = await db.allegati.count_documents({
            "entita_tipo": "polizza", "entita_id": p["id"],
            "visibile_cliente": True, "is_deleted": {"$ne": True},
        })
        # Sinistri collegati
        p["n_sinistri"] = await db.sinistri.count_documents({"polizza_id": p["id"]})
        # Stato semplificato
        p["is_scaduta"] = (p.get("scadenza") or "") < oggi
        p["is_attiva"] = p.get("stato") == "attiva"
    if not includi_storiche:
        polizze = [p for p in polizze if (p.get("scadenza") or "") >= oggi]
    return polizze


# ============================================================
# TITOLI (quietanze)
# ============================================================
@router.get("/titoli")
async def list_titoli(cliente=Depends(current_cliente)):
    from server import db
    # Mappa polizza_id → {numero_polizza, ramo, prodotto, compagnia_nome, targa}
    pol_map = {}
    async for p in db.polizze.find(
        {"contraente_id": cliente["id"]},
        {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1,
         "prodotto": 1, "targa": 1, "compagnia_id": 1},
    ):
        pol_map[p["id"]] = p
    if not pol_map:
        return []
    # Nomi compagnie
    comp_ids = list({v.get("compagnia_id") for v in pol_map.values() if v.get("compagnia_id")})
    comp_names = {c["id"]: c.get("ragione_sociale") async for c in db.compagnie.find(
        {"id": {"$in": comp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})} if comp_ids else {}

    titoli = await db.titoli.find(
        {"polizza_id": {"$in": list(pol_map.keys())}}, {"_id": 0},
    ).sort("scadenza", -1).to_list(2000)
    # Enrichment per ogni titolo
    for t in titoli:
        p = pol_map.get(t.get("polizza_id"), {}) or {}
        t["polizza_numero"] = p.get("numero_polizza")
        t["polizza_ramo"] = p.get("ramo")
        t["polizza_prodotto"] = p.get("prodotto")
        t["polizza_targa"] = p.get("targa")
        t["compagnia_nome"] = comp_names.get(p.get("compagnia_id"))
        # Etichette stato user-friendly
        stato_map = {
            "da_incassare": "Da pagare",
            "incassato": "Pagato",
            "insoluto": "Arretrato",
            "annullato": "Annullato",
            "storno": "Storno",
            "sospeso": "Sospeso",
        }
        t["stato_label"] = stato_map.get(t.get("stato"), t.get("stato"))
        # Allegati visibili
        cnt = await db.allegati.count_documents({
            "entita_tipo": "titolo", "entita_id": t["id"],
            "visibile_cliente": True, "is_deleted": {"$ne": True},
        })
        t["n_allegati_cliente"] = cnt
    return titoli


# ============================================================
# DOCUMENTI (allegati visibili) + Upload rapido
# ============================================================
@router.get("/polizze/{polizza_id}/titoli")
async def polizza_titoli(polizza_id: str, cliente=Depends(current_cliente)):
    """Storico titoli (pagati + da pagare) di una specifica polizza del cliente.

    Ogni titolo include eventuali allegati/quietanze visibili al cliente.
    """
    from server import db
    p = await db.polizze.find_one(
        {"id": polizza_id, "contraente_id": cliente["id"]},
        {"_id": 0, "id": 1},
    )
    if not p:
        raise HTTPException(404, "Polizza non trovata")
    titoli = await db.titoli.find(
        {"polizza_id": polizza_id}, {"_id": 0},
    ).sort("scadenza", -1).to_list(2000)
    # Enrichment: allegati/quietanze per ogni titolo
    for t in titoli:
        allegati = await db.allegati.find({
            "entita_tipo": "titolo",
            "entita_id": t["id"],
            "visibile_cliente": True,
            "is_deleted": {"$ne": True},
        }, {"_id": 0, "id": 1, "nome_file": 1, "categoria": 1, "content_type": 1,
              "created_at": 1}).sort("created_at", -1).to_list(20)
        t["quietanze"] = allegati
        t["n_allegati_cliente"] = len(allegati)
    return titoli


@router.get("/allegati/by-entita")
async def allegati_by_entita(
    entita_tipo: str, entita_id: str,
    cliente=Depends(current_cliente),
):
    """Allegati visibili al cliente filtrati per entità (polizza/titolo/veicolo/sinistro).

    Verifica che l'entità appartenga al cliente prima di rispondere.
    """
    from server import db
    if entita_tipo not in ("polizza", "titolo", "applicazione_matricola", "sinistro", "anagrafica"):
        raise HTTPException(400, "entita_tipo non ammesso")
    # Verifica ownership
    if entita_tipo == "polizza":
        p = await db.polizze.find_one({"id": entita_id, "contraente_id": cliente["id"]},
                                       {"_id": 0, "id": 1})
        if not p:
            raise HTTPException(404, "Polizza non trovata")
        # Esclude gli allegati specifici del veicolo (applicazione_matricola): quelli
        # devono comparire solo nella card del veicolo, non nella polizza principale.
        items = await db.allegati.find({
            "entita_tipo": "polizza",
            "entita_id": entita_id,
            "visibile_cliente": True,
            "is_deleted": {"$ne": True},
            "$or": [
                {"applicazione_matricola_id": {"$exists": False}},
                {"applicazione_matricola_id": None},
                {"applicazione_matricola_id": ""},
            ],
        }, {"_id": 0}).sort("created_at", -1).to_list(500)
        return items
    elif entita_tipo == "titolo":
        t = await db.titoli.find_one({"id": entita_id}, {"_id": 0, "polizza_id": 1})
        if not t:
            raise HTTPException(404, "Titolo non trovato")
        p = await db.polizze.find_one({"id": t["polizza_id"], "contraente_id": cliente["id"]},
                                        {"_id": 0, "id": 1})
        if not p:
            raise HTTPException(403, "Non autorizzato")
    elif entita_tipo == "applicazione_matricola":
        app = await db.applicazioni.find_one({"id": entita_id}, {"_id": 0, "polizza_id": 1})
        if not app:
            raise HTTPException(404, "Applicazione non trovata")
        p = await db.polizze.find_one({"id": app["polizza_id"], "contraente_id": cliente["id"]},
                                        {"_id": 0, "id": 1})
        if not p:
            raise HTTPException(403, "Non autorizzato")
        # I documenti veicolo possono essere salvati come entita_tipo="applicazione_matricola"
        # oppure come entita_tipo="polizza" + campo applicazione_matricola_id (wizard gestionale).
        # Ritorno l'UNIONE dei due casi.
        items = await db.allegati.find({
            "$or": [
                {"entita_tipo": "applicazione_matricola", "entita_id": entita_id},
                {"applicazione_matricola_id": entita_id},
            ],
            "visibile_cliente": True,
            "is_deleted": {"$ne": True},
        }, {"_id": 0}).sort("created_at", -1).to_list(500)
        return items
    elif entita_tipo == "sinistro":
        s = await db.sinistri.find_one({"id": entita_id, "contraente_id": cliente["id"]},
                                         {"_id": 0, "id": 1})
        if not s:
            raise HTTPException(404, "Sinistro non trovato")
    elif entita_tipo == "anagrafica" and entita_id != cliente["id"]:
        raise HTTPException(403, "Non autorizzato")

    items = await db.allegati.find({
        "entita_tipo": entita_tipo,
        "entita_id": entita_id,
        "visibile_cliente": True,
        "is_deleted": {"$ne": True},
    }, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@router.get("/allegati/{allegato_id}/download")
async def portale_allegato_download(allegato_id: str, cliente=Depends(current_cliente)):
    """Download di un qualsiasi allegato visibile al cliente.

    Verifica che l'allegato sia collegato a un'entità (polizza/titolo/veicolo/sinistro/anagrafica)
    appartenente al cliente e che ``visibile_cliente=true``.
    """
    from server import db, obj_storage
    from fastapi.responses import StreamingResponse
    import io
    al = await db.allegati.find_one(
        {"id": allegato_id, "visibile_cliente": True, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not al:
        raise HTTPException(404, "Allegato non trovato")
    # Ownership check
    et, eid = al.get("entita_tipo"), al.get("entita_id")
    authorized = False
    if et == "anagrafica" and eid == cliente["id"]:
        authorized = True
    elif et == "polizza":
        authorized = bool(await db.polizze.find_one({"id": eid, "contraente_id": cliente["id"]}, {"_id": 0, "id": 1}))
    elif et == "titolo":
        t = await db.titoli.find_one({"id": eid}, {"_id": 0, "polizza_id": 1})
        if t:
            authorized = bool(await db.polizze.find_one({"id": t["polizza_id"], "contraente_id": cliente["id"]}, {"_id": 0, "id": 1}))
    elif et == "applicazione_matricola":
        ap = await db.applicazioni.find_one({"id": eid}, {"_id": 0, "polizza_id": 1})
        if ap:
            authorized = bool(await db.polizze.find_one({"id": ap["polizza_id"], "contraente_id": cliente["id"]}, {"_id": 0, "id": 1}))
    elif et == "sinistro":
        authorized = bool(await db.sinistri.find_one({"id": eid, "contraente_id": cliente["id"]}, {"_id": 0, "id": 1}))
    if not authorized:
        raise HTTPException(403, "Non autorizzato")
    try:
        data, _ct = obj_storage.get_object(al["storage_path"])
    except Exception as e:
        raise HTTPException(503, f"Errore download: {e}")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=al.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{al.get("nome_file", "allegato")}"'},
    )


@router.get("/documenti")
async def list_documenti(cliente=Depends(current_cliente)):
    from server import db
    pol_ids = [p["id"] async for p in db.polizze.find(
        {"contraente_id": cliente["id"]}, {"_id": 0, "id": 1})]
    sin_ids = [s["id"] async for s in db.sinistri.find(
        {"contraente_id": cliente["id"]}, {"_id": 0, "id": 1})]
    or_query = [
        {"entita_tipo": "anagrafica", "entita_id": cliente["id"]},
        {"entita_tipo": "polizza", "entita_id": {"$in": pol_ids}},
        {"entita_tipo": "sinistro", "entita_id": {"$in": sin_ids}},
    ]
    items = await db.allegati.find({
        "$or": or_query,
        "visibile_cliente": True,
        "is_deleted": {"$ne": True},
    }, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@router.post("/documenti/upload")
async def upload_documento(
    file: UploadFile = File(...),
    categoria: str = Form("caricato_da_cliente"),
    descrizione: Optional[str] = Form(None),
    polizza_id: Optional[str] = Form(None),
    cliente=Depends(current_cliente),
):
    """Il cliente carica un documento (scatta foto, PDF, ecc.). Va in
    'documenti_da_smistare' del CRM e l'agenzia lo verifica."""
    from server import db
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "File troppo grande (>20 MB)")
    storage_root = os.environ.get("STORAGE_ROOT", "/data/uploads")
    os.makedirs(storage_root, exist_ok=True)
    ext = (file.filename or "").split(".")[-1].lower() if file.filename else "bin"
    fname = f"{uuid.uuid4()}.{ext}"
    fpath = os.path.join(storage_root, fname)
    with open(fpath, "wb") as f:
        f.write(content)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": cliente.get("tenant_id"),
        "entita_tipo": "polizza" if polizza_id else "anagrafica",
        "entita_id": polizza_id or cliente["id"],
        "categoria": categoria,
        "nome_file": file.filename or fname,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "storage_path": fpath,
        "descrizione": descrizione or "Caricato dal cliente via Portale",
        "fonte": "portale_cliente_upload",
        "visibile_cliente": True,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "caricato_da_cliente_id": cliente["id"],
    }
    await db.allegati.insert_one(doc); doc.pop("_id", None)
    # Notifica agenzia con record in "richieste da cliente"
    await db.richieste_cliente.insert_one({
        "id": str(uuid.uuid4()),
        "tipo": "upload_documento",
        "cliente_id": cliente["id"],
        "cliente_nome": cliente.get("ragione_sociale") or cliente.get("cognome_nome")
                        or f"{cliente.get('cognome','')} {cliente.get('nome','')}".strip(),
        "allegato_id": doc["id"],
        "stato": "da_verificare",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "allegato_id": doc["id"]}


# ============================================================
# SINISTRI
# ============================================================
@router.get("/sinistri")
async def list_sinistri(cliente=Depends(current_cliente)):
    from server import db
    items = await db.sinistri.find(
        {"contraente_id": cliente["id"]}, {"_id": 0},
    ).sort("data_denuncia", -1).to_list(500)
    # Enrichment con dati polizza + compagnia
    pol_ids = list({s.get("polizza_id") for s in items if s.get("polizza_id")})
    pol_map = {}
    if pol_ids:
        async for p in db.polizze.find(
            {"id": {"$in": pol_ids}},
            {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "targa": 1, "compagnia_id": 1},
        ):
            pol_map[p["id"]] = p
    comp_ids = list({v.get("compagnia_id") for v in pol_map.values() if v.get("compagnia_id")})
    comp_names = {c["id"]: c.get("ragione_sociale") async for c in db.compagnie.find(
        {"id": {"$in": comp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})} if comp_ids else {}
    for s in items:
        p = pol_map.get(s.get("polizza_id"), {}) or {}
        s["polizza_numero"] = p.get("numero_polizza")
        s["polizza_ramo"] = p.get("ramo")
        s["polizza_targa"] = p.get("targa")
        s["compagnia_nome"] = comp_names.get(p.get("compagnia_id"))
        s["n_allegati"] = await db.allegati.count_documents({
            "entita_tipo": "sinistro", "entita_id": s["id"],
            "visibile_cliente": True, "is_deleted": {"$ne": True},
        })
    return items


# ============================================================
# PIRAMIDE COPERTURE — gamification protezione
# ============================================================
# Mapping keyword ramo → livello piramide.
# Ordine top → bottom della piramide (base larga = fondamentale).
_PIRAMIDE_LIVELLI = [
    {
        "id": "rca", "nome": "RCA / Veicoli", "icona": "car",
        "colore": "sky", "descrizione": "Responsabilità civile veicoli",
        "keywords": ["rca", "rc auto", "rc-auto", "auto", "motocicl",
                     "ciclomotor", "autocarr", "veicoli", "flotta",
                     "libro matricola", "assistenza stradale", "furto veicoli"],
    },
    {
        "id": "casa", "nome": "Casa", "icona": "home",
        "colore": "emerald", "descrizione": "Abitazione, contenuto e fabbricato",
        "keywords": ["casa", "abitazion", "fabbricat", "multirischio",
                     "condominio", "parrocch", "globale fabbricati",
                     "immobil"],
    },
    {
        "id": "vita_salute", "nome": "Vita & Salute", "icona": "heart",
        "colore": "rose", "descrizione": "Tu, la tua famiglia, la tua salute",
        "keywords": ["vita", "tcm", "temporanea caso morte", "misto",
                     "rivalutabile", "unit linked", "salute", "malatt",
                     "infortun", "capitale differ", "risparmio",
                     "generazione", "protezione persona"],
    },
    {
        "id": "impresa", "nome": "Impresa", "icona": "briefcase",
        "colore": "amber", "descrizione": "Attività, RC professionale, dipendenti",
        "keywords": ["impres", "azienda", "artigian", "commercio",
                     "negozio", "attivit", "rc profession", "rc generale",
                     "responsabilit", "industri", "grandine", "trasporti",
                     "cauzion", "cristal"],
    },
    {
        "id": "pensione", "nome": "Previdenza", "icona": "piggy-bank",
        "colore": "violet", "descrizione": "Pensione integrativa, PIP, FIP",
        "keywords": ["pension", "previd", " pip ", " fip ", "fondo pension"],
    },
    {
        "id": "tutela_legale", "nome": "Tutela Legale", "icona": "scale",
        "colore": "slate", "descrizione": "Assistenza legale e ricorsi",
        "keywords": ["tutela legale", "legal", "protezione legale"],
    },
]


def _match_livello(polizza: dict) -> Optional[str]:
    """Ritorna l'id del livello piramide che matcha con la polizza."""
    haystack = " ".join([
        (polizza.get("prodotto") or ""),
        (polizza.get("ramo") or ""),
        (polizza.get("ramo_originale") or ""),
    ]).lower()
    haystack = " " + haystack + " "
    for lvl in _PIRAMIDE_LIVELLI:
        if any(k in haystack for k in lvl["keywords"]):
            return lvl["id"]
    return None


@router.get("/protezione")
async def portale_piramide_protezione(cliente=Depends(current_cliente)):
    """Ritorna la Piramide v2 (schema Schiantarelli) del cliente con voci
    auto-popolate dalle polizze attive + dati salvati (reddito, testamento, eredi).
    """
    from server import db, _piramide_v2_calcola_voci
    ac = await db.analisi_cliente.find_one({"anagrafica_id": cliente["id"]}, {"_id": 0}) or {}
    piramide = ac.get("piramide_v2") or {}
    voci = await _piramide_v2_calcola_voci(cliente["id"])
    return {
        "voci_calcolate": voci,
        "dati_reddito": piramide.get("dati_reddito") or {},
        "testamento": piramide.get("testamento", False),
        "eredi_legittimi": piramide.get("eredi_legittimi") or [],
        "override_voci": piramide.get("override_voci") or {},
        "stato_voci": piramide.get("stato_voci") or {},
        "voci_custom": piramide.get("voci_custom") or {},
        "cliente_nome": (cliente.get("ragione_sociale") or cliente.get("cognome_nome")
                         or f"{cliente.get('cognome', '') or ''} {cliente.get('nome', '') or ''}".strip()),
    }


@router.get("/protezione-legacy")
async def portale_piramide_protezione_legacy(cliente=Depends(current_cliente)):
    """Legacy: ritorna la piramide di protezione semplice del cliente."""
    from server import db
    oggi = datetime.now(timezone.utc).date().isoformat()
    # Prendi tutte le polizze del cliente ancora ATTIVE (non scadute e stato != disdetta)
    polizze = await db.polizze.find(
        {
            "contraente_id": cliente["id"],
            "$or": [
                {"scadenza": {"$gte": oggi}},
                {"scadenza": {"$exists": False}},
                {"scadenza": None},
            ],
            "stato": {"$nin": ["disdettata", "annullata", "sospesa"]},
        },
        {"_id": 0, "id": 1, "ramo": 1, "ramo_originale": 1, "prodotto": 1,
         "numero_polizza": 1, "compagnia_id": 1, "premio_lordo": 1,
         "capitale_assicurato": 1, "massimali": 1, "garanzie": 1, "scadenza": 1},
    ).to_list(500)
    # Aggrega per livello
    by_lvl: dict = {lvl["id"]: {"polizze": [], "massimale_tot": 0.0, "premio_tot": 0.0} for lvl in _PIRAMIDE_LIVELLI}
    for p in polizze:
        lvl_id = _match_livello(p)
        if not lvl_id:
            continue
        # Massimale: prendi il max tra i vari campi disponibili
        maxi = 0.0
        for k in ("capitale_assicurato", "massimali"):
            v = p.get(k)
            if isinstance(v, (int, float)):
                maxi = max(maxi, float(v))
            elif isinstance(v, str):
                try:
                    maxi = max(maxi, float(v.replace(".", "").replace(",", ".")))
                except (ValueError, AttributeError):
                    pass
        # Dai garanzie: max dei capitali
        for g in p.get("garanzie") or []:
            for k in ("capitale_assicurato", "massimale", "capitale", "somma_assicurata"):
                v = g.get(k)
                if isinstance(v, (int, float)):
                    maxi = max(maxi, float(v))
        by_lvl[lvl_id]["polizze"].append({
            "id": p["id"],
            "numero": p.get("numero_polizza"),
            "prodotto": p.get("prodotto"),
            "ramo": p.get("ramo"),
            "scadenza": p.get("scadenza"),
            "massimale": maxi if maxi > 0 else None,
            "premio_lordo": p.get("premio_lordo") or 0,
        })
        by_lvl[lvl_id]["massimale_tot"] += maxi
        by_lvl[lvl_id]["premio_tot"] += float(p.get("premio_lordo") or 0)
    # Costruisci risposta ordinata
    livelli_out = []
    coperti = 0
    for lvl in _PIRAMIDE_LIVELLI:
        agg = by_lvl[lvl["id"]]
        is_coperto = len(agg["polizze"]) > 0
        if is_coperto:
            coperti += 1
        livelli_out.append({
            "id": lvl["id"],
            "nome": lvl["nome"],
            "descrizione": lvl["descrizione"],
            "icona": lvl["icona"],
            "colore": lvl["colore"],
            "coperto": is_coperto,
            "polizze": agg["polizze"],
            "n_polizze": len(agg["polizze"]),
            "massimale_tot": agg["massimale_tot"] if agg["massimale_tot"] > 0 else None,
            "premio_tot": round(agg["premio_tot"], 2) if agg["premio_tot"] > 0 else None,
        })
    tot = len(_PIRAMIDE_LIVELLI)
    return {
        "livelli": livelli_out,
        "coperti": coperti,
        "totali": tot,
        "percentuale": round(coperti / tot * 100),
    }


@router.post("/protezione/richiedi-preventivo")
async def richiedi_preventivo_piramide(body: dict, cliente=Depends(current_cliente)):
    """Cliente clicca "Richiedi preventivo" su un livello scoperto.

    Body: {"livello_id": "casa", "livello_nome": "Casa"}
    Crea:
    - Una richiesta nella dashboard admin (widget "Richieste da verificare")
    - Un messaggio in chat_portale con testo precompilato
    """
    from server import db
    livello_id = (body.get("livello_id") or "").strip()
    livello_nome = (body.get("livello_nome") or livello_id or "protezione").strip()
    if not livello_id:
        raise HTTPException(400, "livello_id richiesto")
    now = datetime.now(timezone.utc).isoformat()
    cliente_nome = (cliente.get("ragione_sociale")
                    or cliente.get("cognome_nome")
                    or f"{cliente.get('cognome','')} {cliente.get('nome','')}".strip()
                    or cliente.get("email"))
    # 1) Richiesta lato admin
    rich_id = str(uuid.uuid4())
    await db.richieste_cliente.insert_one({
        "id": rich_id,
        "tipo": "preventivo_piramide",
        "cliente_id": cliente["id"],
        "cliente_nome": cliente_nome,
        "livello_id": livello_id,
        "livello_nome": livello_nome,
        "messaggio": f"Richiesta preventivo per: {livello_nome}",
        "stato": "da_verificare",
        "tenant_id": cliente.get("tenant_id"),
        "created_at": now,
    })
    # 2) Messaggio in chat portale (visibile sia lato cliente sia lato agenzia)
    await db.chat_portale.insert_one({
        "id": str(uuid.uuid4()),
        "anagrafica_id": cliente["id"],
        "tenant_id": cliente.get("tenant_id"),
        "direzione": "in",
        "testo": f"🛡️ Vorrei ricevere un preventivo per copertura: {livello_nome}.",
        "mittente_admin_id": None,
        "created_at": now,
        "letto": False,
    })
    return {
        "ok": True,
        "richiesta_id": rich_id,
        "messaggio": f"Richiesta inviata all'agenzia per {livello_nome}",
    }


# ============================================================
# ANAGRAFICA — richiesta modifica
# ============================================================
@router.put("/anagrafica/richiesta")
async def richiesta_modifica_anagrafica(body: dict, cliente=Depends(current_cliente)):
    """Il cliente non modifica direttamente l'anagrafica; invia una richiesta
    all'agenzia che dovrà approvare."""
    from server import db
    rich = {
        "id": str(uuid.uuid4()),
        "tipo": "modifica_anagrafica",
        "cliente_id": cliente["id"],
        "cliente_nome": cliente.get("ragione_sociale") or cliente.get("cognome_nome")
                        or f"{cliente.get('cognome','')} {cliente.get('nome','')}".strip(),
        "modifiche_richieste": body,
        "stato": "da_verificare",
        "tenant_id": cliente.get("tenant_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.richieste_cliente.insert_one(rich)
    return {"ok": True, "richiesta_id": rich["id"], "messaggio": "Richiesta inviata all'agenzia"}


# ============================================================
# CHAT — messaggistica cliente ↔ agenzia
# ============================================================
# Utilizza collection `chat_portale` con campi:
#   id, anagrafica_id, tenant_id, direzione ("in"|"out"),
#   testo, mittente_admin_id (nullable), created_at, letto (bool)
# ============================================================
@router.get("/chat/messaggi")
async def portale_chat_messaggi(limit: int = 500, cliente=Depends(current_cliente)):
    """Ritorna l'intera cronologia chat del cliente con l'agenzia."""
    from server import db
    items = await db.chat_portale.find(
        {"anagrafica_id": cliente["id"]}, {"_id": 0},
    ).sort("created_at", 1).to_list(limit)
    # marca i messaggi "out" (dall'agenzia) come letti dal cliente
    await db.chat_portale.update_many(
        {"anagrafica_id": cliente["id"], "direzione": "out", "letto": {"$ne": True}},
        {"$set": {"letto": True, "letto_at": datetime.now(timezone.utc).isoformat()}},
    )
    return items


@router.post("/chat/messaggi")
async def portale_chat_invia(
    testo: str = Form(""),
    file: Optional[UploadFile] = File(None),
    body: Optional[dict] = None,
    cliente=Depends(current_cliente),
):
    """Il cliente invia un messaggio all'agenzia (con eventuale allegato)."""
    from server import db, Allegato, obj_storage
    testo_final = (testo or (body or {}).get("testo") or "").strip()
    if not testo_final and not file:
        raise HTTPException(400, "Testo o allegato obbligatorio")

    allegato_id = allegato_nome = allegato_ct = None
    if file:
        data = await file.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(400, "File troppo grande (max 25 MB)")
        ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "bin"
        file_id = str(uuid.uuid4())
        path = f"{os.environ.get('APP_NAME', 'assicura')}/portale-chat/{cliente['id']}/{file_id}.{ext}"
        ct = file.content_type or "application/octet-stream"
        try:
            result = obj_storage.put_object(path, data, ct)
        except Exception as e:
            raise HTTPException(503, f"Errore upload: {e}")
        al = Allegato(
            entita_tipo="anagrafica", entita_id=cliente["id"],
            nome_file=file.filename, storage_path=result["path"],
            content_type=ct, size=result.get("size", len(data)),
            descrizione="Allegato chat cliente Portale",
            autore_id=None,
        )
        await db.allegati.insert_one(al.model_dump())
        allegato_id = al.id
        allegato_nome = file.filename
        allegato_ct = ct

    msg = {
        "id": str(uuid.uuid4()),
        "anagrafica_id": cliente["id"],
        "tenant_id": cliente.get("tenant_id"),
        "cliente_nome": cliente.get("ragione_sociale") or cliente.get("cognome_nome")
                        or f"{cliente.get('cognome','')} {cliente.get('nome','')}".strip(),
        "direzione": "in",
        "mittente_admin_id": None,
        "testo": testo_final[:4000],
        "allegato_id": allegato_id,
        "allegato_nome": allegato_nome,
        "allegato_content_type": allegato_ct,
        "letto": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.chat_portale.insert_one(msg); msg.pop("_id", None)
    return msg


@router.get("/chat/unread")
async def portale_chat_unread(cliente=Depends(current_cliente)):
    """Numero messaggi non letti dall'agenzia verso il cliente."""
    from server import db
    n = await db.chat_portale.count_documents({
        "anagrafica_id": cliente["id"],
        "direzione": "out",
        "letto": {"$ne": True},
    })
    return {"unread": n}


@router.get("/chat/allegato/{allegato_id}")
async def portale_chat_download_allegato(allegato_id: str, cliente=Depends(current_cliente)):
    """Download di un allegato di chat inviato dall'agenzia al cliente (o viceversa).

    Verifica che l'allegato appartenga a un messaggio della conversazione del cliente.
    """
    from server import db, obj_storage
    from fastapi.responses import StreamingResponse
    import io

    # verifica che l'allegato appartenga alla chat del cliente
    msg = await db.chat_portale.find_one(
        {"anagrafica_id": cliente["id"], "allegato_id": allegato_id},
        {"_id": 0},
    )
    if not msg:
        raise HTTPException(404, "Allegato non trovato")
    al = await db.allegati.find_one({"id": allegato_id}, {"_id": 0})
    if not al:
        raise HTTPException(404, "File non trovato")
    try:
        data, _ct = obj_storage.get_object(al["storage_path"])
    except Exception as e:
        raise HTTPException(503, f"Errore download: {e}")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=al.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{al.get("nome_file", "allegato")}"'},
    )


# ============================================================
# SERVIZI (link/utili configurati dall'agenzia)
# ============================================================
@router.get("/servizi")
async def list_servizi(cliente=Depends(current_cliente)):
    from server import db
    # I servizi possono essere configurati per tenant
    items = await db.portale_servizi.find(
        {"$or": [{"tenant_id": cliente.get("tenant_id")}, {"tenant_id": None}]},
        {"_id": 0},
    ).sort("ordine", 1).to_list(50)
    # Se non ce ne sono, restituisce servizi di default
    if not items:
        items = [
            {"nome": "Denuncia Sinistro", "icona": "alert-triangle",
             "descrizione": "Segnala un sinistro in modo rapido",
             "url": "tel:+39800654321", "categoria": "emergenza"},
            {"nome": "WhatsApp Agenzia", "icona": "message-circle",
             "descrizione": "Contatta la tua agenzia via WhatsApp",
             "url": "https://wa.me/393334455667", "categoria": "contatto"},
        ]
    return items


@router.get("/public/team-foto/{tid}")
async def portale_public_team_foto(tid: str):
    """Serve la foto di un membro del team senza autenticazione (usata dal portale)."""
    from server import db, obj_storage
    from fastapi.responses import StreamingResponse
    import io
    az = await db.azienda_config.find_one(
        {"portale_team.id": tid}, {"_id": 0, "portale_team.$": 1}) or {}
    team = az.get("portale_team") or []
    path = team[0].get("foto_path") if team else None
    if not path:
        raise HTTPException(404, "Foto non trovata")
    try:
        data, ctype = obj_storage.get_object(path)
    except Exception:
        raise HTTPException(404, "Foto non disponibile")
    return StreamingResponse(io.BytesIO(data), media_type=ctype or "image/jpeg",
                             headers={"Cache-Control": "public, max-age=3600"})


@router.get("/video")
async def portale_video(cliente=Depends(current_cliente)):
    """Elenco video pubblicati per i clienti (dalla sezione Video del CRM).
    Sono ritornati SOLO i video con `visibile_ruoli` che include `cliente` e pubblicati.
    """
    from server import db
    items = await db.corsi.find(
        {"pubblicato": True, "visibile_ruoli": "cliente"}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    # Ritorna solo i campi utili al cliente
    return [
        {
            "id": c.get("id"),
            "titolo": c.get("titolo"),
            "descrizione": c.get("descrizione"),
            "categoria": c.get("categoria"),
            "video_url": c.get("video_url"),
            "durata_minuti": c.get("durata_minuti"),
            "created_at": c.get("created_at"),
        }
        for c in items
    ]


# ============================================================
# ASSET PUBBLICI DEL PORTALE (logo + video motivazionale)
# ============================================================
@router.get("/public/logo")
async def portale_public_logo():
    """Serve il logo dell'agenzia senza autenticazione (usato da <img> nel portale)."""
    from server import db, obj_storage
    from fastapi.responses import StreamingResponse
    import io
    az = await db.azienda_config.find_one(
        {}, {"_id": 0, "logo_storage_path": 1, "logo_url": 1}) or {}
    path = az.get("logo_storage_path")
    if not path and (az.get("logo_url") or "").startswith("/api/storage/"):
        path = az["logo_url"][len("/api/storage/"):]
    if not path:
        raise HTTPException(404, "Logo non configurato")
    try:
        data, ctype = obj_storage.get_object(path)
    except Exception:
        raise HTTPException(404, "Logo non trovato")
    return StreamingResponse(io.BytesIO(data), media_type=ctype or "image/png",
                             headers={"Cache-Control": "public, max-age=3600"})


@router.get("/public/video-analisi")
async def portale_public_video_analisi():
    """Serve il video motivazionale caricato dall'agenzia (senza auth, per <video>)."""
    from server import db, obj_storage
    from fastapi.responses import StreamingResponse
    import io
    az = await db.azienda_config.find_one(
        {}, {"_id": 0, "video_analisi_storage_path": 1}) or {}
    path = az.get("video_analisi_storage_path")
    if not path:
        raise HTTPException(404, "Video non configurato")
    try:
        data, ctype = obj_storage.get_object(path)
    except Exception:
        raise HTTPException(404, "Video non trovato")
    return StreamingResponse(io.BytesIO(data), media_type=ctype or "video/mp4",
                             headers={"Accept-Ranges": "bytes"})


# ============================================================
# CTA ANALISI PERSONALIZZATA — video + upload estratto INPS
# ============================================================
@router.get("/analisi-personalizzata")
async def portale_analisi_personalizzata(cliente=Depends(current_cliente)):
    """Config CTA: video motivazionale + estratti INPS già inviati dal cliente."""
    from server import db
    az = await db.azienda_config.find_one(
        {}, {"_id": 0, "video_analisi_url": 1, "video_analisi_storage_path": 1}) or {}
    ac = await db.analisi_cliente.find_one(
        {"anagrafica_id": cliente["id"]}, {"_id": 0, "estratti_conto_inps": 1}) or {}
    estratti = [
        {"id": e.get("id"), "nome_file": e.get("nome_file"),
         "data_caricamento": e.get("data_caricamento"),
         "anno_riferimento": e.get("anno_riferimento")}
        for e in (ac.get("estratti_conto_inps") or [])
        if e.get("fonte") == "portale_cliente"
    ]
    return {
        "video_url": az.get("video_analisi_url"),
        "video_file": bool(az.get("video_analisi_storage_path")),
        "estratti": estratti,
    }


@router.post("/analisi-personalizzata/upload-inps")
async def portale_upload_estratto_inps(
    file: UploadFile = File(...),
    cliente=Depends(current_cliente),
):
    """Il cliente carica il PDF dell'estratto conto contributivo INPS.
    Il file viene parsato, archiviato nell'analisi cliente (badge 'dal portale')
    e l'agenzia riceve una notifica nelle Richieste dal Portale."""
    from server import db, obj_storage, _ensure_analisi, _now_iso, _uid
    import inps_calculator
    import io

    contents = await file.read()
    if len(contents) > 15 * 1024 * 1024:
        raise HTTPException(413, "File troppo grande (max 15 MB)")
    fname = (file.filename or "estratto.pdf")
    if not fname.lower().endswith(".pdf"):
        raise HTTPException(400, "Carica il PDF dell'estratto conto INPS")

    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        text = ""
    parsed = inps_calculator.parse_estratto_conto_inps(text) if text.strip() else {}

    storage_path = (f"{os.environ.get('APP_NAME', 'assicura')}/anagrafiche/"
                    f"{cliente['id']}/estratti_inps/{uuid.uuid4()}.pdf")
    file_url = None
    try:
        res = obj_storage.put_object(storage_path, contents, "application/pdf")
        file_url = f"/api/storage/{res['path']}"
        storage_path = res["path"]
    except Exception:
        storage_path = None

    anno_rif = None
    if parsed.get("storico_redditi"):
        anno_rif = max((r["anno"] for r in parsed["storico_redditi"]), default=None)

    cliente_nome = (cliente.get("ragione_sociale") or cliente.get("cognome_nome")
                    or f"{cliente.get('cognome', '')} {cliente.get('nome', '')}".strip())

    ac = await _ensure_analisi(cliente["id"])
    estratto_entry = {
        "id": _uid(),
        "url": file_url,
        "storage_path": storage_path,
        "nome_file": fname,
        "mime": "application/pdf",
        "size_kb": round(len(contents) / 1024, 1),
        "data_caricamento": _now_iso(),
        "anno_riferimento": anno_rif,
        "totale_settimane": parsed.get("settimane_contributive", 0),
        "totale_versato": parsed.get("totale_versato", 0),
        "totale_retribuzioni": parsed.get("totale_retribuzioni", 0),
        "montante_stimato": parsed.get("montante_stimato", 0),
        "anni_stimati": parsed.get("anni_stimati", 0),
        "fonte": "portale_cliente",
        "caricato_da_nome": cliente_nome,
    }
    update = {"updated_at": _now_iso(),
              "estratti_conto_inps": list(ac.get("estratti_conto_inps") or []) + [estratto_entry]}

    # Merge non distruttivo di storico redditi / periodi contributivi
    existing_storico = {(r.get("anno"), r.get("cassa", "")): r for r in (ac.get("storico_redditi") or [])}
    for nuovo in parsed.get("storico_redditi") or []:
        existing_storico[(nuovo["anno"], nuovo.get("cassa", ""))] = nuovo
    if existing_storico:
        update["storico_redditi"] = list(existing_storico.values())
    existing_periodi = {(p.get("inizio_periodo"), p.get("fondo")): p
                        for p in (ac.get("periodi_contributivi") or [])}
    for nuovo in parsed.get("periodi_contributivi") or []:
        existing_periodi[(nuovo["inizio_periodo"], nuovo["fondo"])] = nuovo
    if existing_periodi:
        update["periodi_contributivi"] = list(existing_periodi.values())

    await db.analisi_cliente.update_one({"anagrafica_id": cliente["id"]}, {"$set": update})

    # Notifica all'agenzia (widget "Richieste dal Portale Cliente")
    await db.richieste_cliente.insert_one({
        "id": str(uuid.uuid4()),
        "tipo": "upload_estratto_inps",
        "cliente_id": cliente["id"],
        "cliente_nome": cliente_nome,
        "dettaglio": f"Estratto conto INPS caricato dal portale: {fname}",
        "stato": "da_verificare",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "ok": True,
        "estratto_id": estratto_entry["id"],
        "parsed": {
            "settimane_contributive": parsed.get("settimane_contributive", 0),
            "anni_stimati": parsed.get("anni_stimati", 0),
        },
    }
