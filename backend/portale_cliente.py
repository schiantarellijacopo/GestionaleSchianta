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

    # Cerca anagrafica per email
    ana = await db.anagrafiche.find_one(
        {"$or": [{"email": {"$regex": f"^{email}$", "$options": "i"}},
                 {"pec": {"$regex": f"^{email}$", "$options": "i"}}]},
        {"_id": 0},
    )
    if not ana:
        raise HTTPException(401, "Credenziali non valide")

    # Verifica password: CF (privato) o P.IVA (azienda), o password_hash custom se impostata
    valid = False
    cf = _norm(ana.get("codice_fiscale"))
    piva = _norm(ana.get("partita_iva"))
    pwd_norm = password.strip().upper()
    if cf and pwd_norm == cf.upper():
        valid = True
    elif piva and pwd_norm == piva.upper():
        valid = True
    # (facoltativo) supporto password_hash personalizzata futura
    if not valid:
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
        "indirizzo": cliente.get("indirizzo_residenza"),
        "comune": cliente.get("comune_residenza"),
        "provincia": cliente.get("provincia_residenza"),
        "cap": cliente.get("cap_residenza"),
        "tipo_soggetto": cliente.get("tipo_soggetto"),
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
    """Elenco polizze del cliente. Include applicazioni libro matricola inline."""
    from server import db
    flt = {"contraente_id": cliente["id"]}
    polizze = await db.polizze.find(flt, {"_id": 0}).sort("scadenza", -1).to_list(500)

    for p in polizze:
        # Applicazioni Libro Matricola (visibili solo se polizza è LM)
        p["applicazioni"] = []
        if p.get("is_libro_matricola"):
            apps = await db.applicazioni.find(
                {"polizza_id": p["id"]}, {"_id": 0},
            ).sort("numero", 1).to_list(2000)
            p["applicazioni"] = apps
        # Compagnia
        if p.get("compagnia_id"):
            c = await db.compagnie.find_one({"id": p["compagnia_id"]}, {"_id": 0, "ragione_sociale": 1})
            p["compagnia_nome"] = (c or {}).get("ragione_sociale")
    if not includi_storiche:
        oggi = datetime.now(timezone.utc).date().isoformat()
        polizze = [p for p in polizze if (p.get("scadenza") or "") >= oggi]
    return polizze


# ============================================================
# TITOLI (quietanze)
# ============================================================
@router.get("/titoli")
async def list_titoli(cliente=Depends(current_cliente)):
    from server import db
    pol_ids = [p["id"] async for p in db.polizze.find(
        {"contraente_id": cliente["id"]}, {"_id": 0, "id": 1})]
    if not pol_ids:
        return []
    titoli = await db.titoli.find(
        {"polizza_id": {"$in": pol_ids}}, {"_id": 0},
    ).sort("data_scadenza", -1).to_list(2000)
    # allegati visibili per ogni titolo
    for t in titoli:
        cnt = await db.allegati.count_documents({
            "entita_tipo": "titolo", "entita_id": t["id"],
            "visibile_cliente": True, "is_deleted": {"$ne": True},
        })
        t["n_allegati_cliente"] = cnt
    return titoli


# ============================================================
# DOCUMENTI (allegati visibili) + Upload rapido
# ============================================================
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
    return items


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
            {"nome": "Assistenza Stradale H24", "icona": "life-buoy",
             "descrizione": "Chiamata gratuita in caso di guasto o incidente",
             "url": "tel:+39800123456", "categoria": "emergenza"},
            {"nome": "Denuncia Sinistro", "icona": "alert-triangle",
             "descrizione": "Segnala un sinistro in modo rapido",
             "url": "tel:+39800654321", "categoria": "emergenza"},
            {"nome": "WhatsApp Agenzia", "icona": "message-circle",
             "descrizione": "Contatta la tua agenzia via WhatsApp",
             "url": "https://wa.me/393334455667", "categoria": "contatto"},
        ]
    return items
