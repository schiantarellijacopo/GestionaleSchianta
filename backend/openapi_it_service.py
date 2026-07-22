"""OpenAPI.it integration service — LIVE (OAuth2 client_credentials) con fallback MOCK.

Flusso OAuth2 v2 (documentazione: https://console.openapi.com/it/apis/oauth/documentation):
  1. Basic Auth con email + APIkey a POST https://oauth.openapi.it/token
     con body {"scopes": [...], "ttl": seconds}  → riceve access token
  2. Bearer token per chiamate alle API di dominio (imprese.openapi.it, visengine2, ecc.)

Variabili d'ambiente lette:
  OPENAPI_IT_CLIENT_ID     → email account OpenAPI.it (es "user@example.com")
  OPENAPI_IT_CLIENT_SECRET → APIkey personale (da console.openapi.com/it/oauth)
  OPENAPI_IT_ENV           → "prod" (default) | "sandbox"

**In sandbox** i domini API hanno prefisso `test.` sia negli scope che nelle URL
(es. `test.imprese.openapi.it` invece di `imprese.openapi.it`).

Se le credenziali mancano OPPURE una chiamata live fallisce (402 saldo zero,
401 non autorizzato, 406 scope non abilitato, connection error, ecc.) →
**automatic fallback** su dati MOCK con seed deterministico per non spezzare l'UI.

Ogni token è cache-ato in memoria fino a scadenza-60s per limitare le richieste.
"""
from __future__ import annotations
import base64
import logging
import os
import random
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _is_sandbox() -> bool:
    return (os.environ.get("OPENAPI_IT_ENV") or "prod").strip().lower() == "sandbox"


def _host(name: str) -> str:
    """Ritorna il dominio API con prefisso `test.` se siamo in sandbox.

    name esempio: "imprese.openapi.it" → sandbox: "test.imprese.openapi.it"
    """
    return f"test.{name}" if _is_sandbox() else name


# ---------- Config ----------
def _cfg() -> dict:
    is_sandbox = _is_sandbox()
    return {
        "client_id": (os.environ.get("OPENAPI_IT_CLIENT_ID") or "").strip(),
        "client_secret": (os.environ.get("OPENAPI_IT_CLIENT_SECRET") or "").strip(),
        "env": "sandbox" if is_sandbox else "prod",
        "oauth_base": "https://test.oauth.openapi.it" if is_sandbox else "https://oauth.openapi.it",
    }


def has_credentials() -> bool:
    c = _cfg()
    return bool(c["client_id"] and c["client_secret"])


def is_mock_mode() -> bool:
    return not has_credentials()


# ---------- Token cache (in-memory) ----------
_token_cache: dict = {}


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


async def _get_token(scopes: list[str], ttl_sec: int = 3600) -> Optional[str]:
    """Ottiene un access_token dagli scopes richiesti. Usa cache in memoria.

    Ritorna None se le credenziali non sono presenti o se il POST /token fallisce
    (es 406 = scope non abilitato / API non attiva sull'account).
    """
    if not has_credentials():
        return None
    c = _cfg()
    cache_key = "|".join(sorted(scopes))
    now = int(time.time())
    cached = _token_cache.get(cache_key)
    if cached and cached.get("expire", 0) - 60 > now:
        return cached["token"]

    url = f"{c['oauth_base']}/token"
    headers = {
        "Authorization": _basic_auth_header(c["client_id"], c["client_secret"]),
        "Content-Type": "application/json",
    }
    payload = {"scopes": scopes, "ttl": ttl_sec}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            logger.warning(
                "OpenAPI.it token endpoint HTTP %s (scopes=%s): %s",
                r.status_code, scopes, r.text[:300],
            )
            return None
        data = r.json()
        token = data.get("token")
        expire = int(data.get("expire") or (now + ttl_sec))
        if token:
            _token_cache[cache_key] = {"token": token, "expire": expire}
            logger.info(
                "OpenAPI.it token acquisito (env=%s, scopes=%d, exp=%s)",
                c["env"], len(scopes), expire,
            )
        return token
    except Exception as e:
        logger.warning("OpenAPI.it token error: %s", e)
        return None


async def get_credit() -> Optional[float]:
    if not has_credentials():
        return None
    c = _cfg()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{c['oauth_base']}/credit",
                headers={"Authorization": _basic_auth_header(c["client_id"], c["client_secret"])},
            )
        if r.status_code == 200:
            return float(r.json().get("data", {}).get("credit") or 0)
    except Exception as e:
        logger.debug("OpenAPI.it credit error: %s", e)
    return None


async def get_available_scopes() -> list[str]:
    """Ritorna la lista completa degli scope disponibili sull'account."""
    if not has_credentials():
        return []
    c = _cfg()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{c['oauth_base']}/scopes",
                headers={"Authorization": _basic_auth_header(c["client_id"], c["client_secret"])},
            )
        if r.status_code == 200:
            return r.json().get("data") or []
    except Exception:
        pass
    return []


# ---------- API call helper ----------
async def _call_api(scopes: list[str], method: str, url: str, **kwargs) -> Optional[dict]:
    token = await _get_token(scopes)
    if not token:
        return None
    headers = kwargs.pop("headers", {}) or {}
    headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.request(method, url, headers=headers, **kwargs)
        if r.status_code == 402:
            logger.warning("OpenAPI.it %s %s → 402 credito insufficiente", method, url)
            return None
        if r.status_code >= 400:
            logger.warning(
                "OpenAPI.it %s %s → HTTP %s: %s", method, url, r.status_code, r.text[:300]
            )
            return None
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
    except Exception as e:
        logger.warning("OpenAPI.it %s %s error: %s", method, url, e)
        return None


# ===================================================================
# SERVIZIO 1 · COMPANY (dati camerali imprese)
# Prod scope:     GET:imprese.openapi.it/advance   |   /base
# Sandbox scope:  GET:test.imprese.openapi.it/advance   |   /base
# ===================================================================
async def fetch_company(piva_or_cf: str) -> dict:
    key = (piva_or_cf or "").strip()
    if has_credentials():
        host = _host("imprese.openapi.it")
        # advance (dati completi con LR, ATECO, PEC, ecc.)
        scope_adv = [f"GET:{host}/advance"]
        res = await _call_api(scope_adv, "GET", f"https://{host}/advance/{key}")
        if res and res.get("success") and res.get("data"):
            return _normalize_company(res["data"], key)
        # fallback su /base
        scope_base = [f"GET:{host}/base"]
        res_b = await _call_api(scope_base, "GET", f"https://{host}/base/{key}")
        if res_b and res_b.get("success") and res_b.get("data"):
            return _normalize_company(res_b["data"], key)
        logger.info("OpenAPI.it live fetch_company fallito, fallback a MOCK per '%s'", key)
    return _mock_company(key)


def _normalize_company(data, key: str) -> dict:
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return _mock_company(key)
    # Sandbox/Prod usa schema italiano con `dettaglio` nested per campi camerali
    dett = data.get("dettaglio") or {}
    # Indirizzo può essere già una stringa ("VIALE MARINETTI 221") o dict con via/civico
    indirizzo_str = data.get("indirizzo") or ""
    if not indirizzo_str and (data.get("via") or data.get("toponimo")):
        indirizzo_str = " ".join(x for x in [
            data.get("toponimo"), data.get("via"), str(data.get("civico") or "")
        ] if x).strip()
    # Legale rappresentante può essere nested in `soci` o `amministratori`
    lr = None
    for coll in ("amministratori", "soci", "cariche"):
        v = dett.get(coll) or data.get(coll)
        if isinstance(v, list) and v:
            first = v[0] if isinstance(v[0], dict) else {}
            lr = first.get("nome_cognome") or first.get("denominazione") or first.get("nome")
            if lr:
                break
    stato = (data.get("stato_attivita") or data.get("companyStatus") or "").upper()
    return {
        "provider": "openapi.it (LIVE)",
        "piva": data.get("piva") or data.get("vatCode") or (key if len(key) == 11 else None),
        "cf": data.get("cf") or data.get("taxCode") or key,
        "ragione_sociale": data.get("denominazione") or data.get("companyName") or data.get("ragione_sociale"),
        "indirizzo": indirizzo_str,
        "cap": data.get("cap") or dett.get("cap"),
        "comune": data.get("comune") or dett.get("comune"),
        "provincia": data.get("provincia") or dett.get("provincia"),
        "ateco": dett.get("codice_ateco") or data.get("codice_ateco") or data.get("atecoCode"),
        "ateco_descrizione": dett.get("descrizione_ateco") or data.get("descrizione_ateco") or data.get("atecoDescription"),
        "pec": dett.get("pec") or data.get("pec"),
        "capitale_sociale_versato": dett.get("capitale_sociale_versato") or dett.get("capitale_sociale") or data.get("capitale_sociale") or data.get("shareCapital"),
        "legale_rappresentante": lr or dett.get("legale_rappresentante") or data.get("legale_rappresentante"),
        "forma_giuridica": dett.get("descrizione_natura_giuridica") or dett.get("codice_natura_giuridica") or data.get("forma_giuridica") or data.get("legalForm"),
        "data_costituzione": dett.get("data_inizio_attivita") or data.get("data_costituzione") or data.get("startDate"),
        "attiva": stato in ("ATTIVA", "ACTIVE", "") or (data.get("attiva") is True),
        "cciaa": dett.get("cciaa") or data.get("cciaa"),
        "rea": dett.get("rea") or data.get("rea") or data.get("reaCode"),
        "raw": data,
    }


def _mock_company(piva_or_cf: str) -> dict:
    random.seed(hash(piva_or_cf) % (2**31))
    return {
        "provider": "openapi.it (MOCK)",
        "piva": piva_or_cf if len(piva_or_cf) == 11 else "".join(random.choices("0123456789", k=11)),
        "cf": piva_or_cf,
        "ragione_sociale": random.choice([
            "Tecnologie Innovative SRL", "Verdi & Bianchi SPA",
            "Milano Servizi SRL", "Alpha Consulting SNC",
        ]) + f" #{random.randint(100,999)}",
        "indirizzo": f"Via {random.choice(['Roma','Milano','Torino'])} {random.randint(1,200)}",
        "cap": f"{random.randint(20000, 39999)}",
        "comune": random.choice(["MILANO", "TORINO", "BOLOGNA", "ROMA"]),
        "provincia": random.choice(["MI", "TO", "BO", "RM"]),
        "ateco": f"{random.randint(10, 82)}.{random.randint(10, 99)}.{random.randint(1, 9)}",
        "ateco_descrizione": random.choice([
            "Attività dei servizi di ristorazione",
            "Consulenza gestionale e amministrativa",
            "Sviluppo software e consulenza informatica",
            "Commercio all'ingrosso di prodotti alimentari",
        ]),
        "pec": f"pec{random.randint(100,999)}@legalmail.it",
        "capitale_sociale_versato": random.choice([10000, 50000, 100000, 500000]),
        "legale_rappresentante": random.choice(["Mario Rossi", "Giulia Bianchi", "Luca Ferrari"]),
        "forma_giuridica": random.choice(["SRL", "SPA", "SNC", "SAS"]),
        "data_costituzione": f"{random.randint(1970, 2020)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
        "attiva": True,
        "cciaa": random.choice(["MI", "TO", "BO"]),
        "rea": f"MI-{random.randint(1000000, 9999999)}",
    }


# ===================================================================
# SERVIZIO 2 · CATASTO
# Note: gli scope disponibili sono catasto.openapi.it/territorio (query per
# foglio/particella) e /indirizzo (reverse). NON esiste lookup catasto per CF
# nel piano attuale. → sempre MOCK finché non attivi il piano dedicato.
# ===================================================================
async def fetch_cadastre(cf_or_piva: str) -> list[dict]:
    if has_credentials():
        logger.info(
            "OpenAPI.it: catasto by CF non disponibile nell'attuale piano — usato MOCK"
        )
    return _mock_cadastre((cf_or_piva or "").strip())


def _mock_cadastre(key: str) -> list[dict]:
    random.seed(hash(key + "_cad") % (2**31))
    n = random.randint(0, 4)
    out = []
    for i in range(n):
        out.append({
            "provider": "openapi.it/cadastre (MOCK)",
            "comune": random.choice(["MILANO", "ROMA", "TORINO", "BOLOGNA"]),
            "foglio": random.randint(1, 999),
            "particella": random.randint(1, 999),
            "subalterno": random.randint(1, 20),
            "categoria": random.choice(["A/2", "A/3", "A/4", "C/6", "C/2"]),
            "classe": str(random.randint(1, 6)),
            "consistenza": random.randint(3, 12),
            "superficie_catastale_mq": random.randint(60, 250),
            "rendita_eur": round(random.uniform(300, 3000), 2),
            "indirizzo": f"Via {random.choice(['Verdi','Rossi','Bianchi'])} {random.randint(1,150)}",
            "titolo": random.choice(["Proprietà 100%", "Proprietà 50%", "Nuda proprietà"]),
        })
    return out


# ===================================================================
# SERVIZIO 3 · AUTOMOTIVE (PRA)
# Note: nessuno scope live disponibile nell'account attuale — sempre MOCK.
# ===================================================================
async def fetch_vehicles(cf_or_piva: str) -> list[dict]:
    if has_credentials():
        logger.info(
            "OpenAPI.it: automotive/PRA non abilitato sull'account — usato MOCK"
        )
    return _mock_vehicles((cf_or_piva or "").strip())


def _mock_vehicles(key: str) -> list[dict]:
    random.seed(hash(key + "_veh") % (2**31))
    n = random.randint(0, 3)
    out = []
    for i in range(n):
        marca = random.choice(["FIAT", "VOLKSWAGEN", "BMW", "AUDI", "RENAULT", "PEUGEOT"])
        model = random.choice(["500", "PANDA", "GOLF", "SERIE 3", "A4", "CLIO"])
        out.append({
            "provider": "openapi.it/automotive (MOCK)",
            "targa": f"{''.join(random.choices('ABCDEFGHJKLMNPRSTVXYZ',k=2))}{random.randint(100,999)}{''.join(random.choices('ABCDEFGHJKLMNPRSTVXYZ',k=2))}",
            "marca": marca,
            "modello": model,
            "alimentazione": random.choice(["BENZINA", "DIESEL", "GPL", "ELETTRICA", "IBRIDA"]),
            "cilindrata": random.choice([1000, 1200, 1400, 1600, 1900]),
            "potenza_kw": random.randint(50, 130),
            "data_immatricolazione": f"{random.randint(2010,2024)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "scadenza_revisione": f"{random.randint(2025,2027)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "categoria": random.choice(["AUTOVETTURA", "AUTOCARRO", "MOTOCICLO"]),
            "tipo_alimentazione": random.choice(["EURO 5", "EURO 6"]),
        })
    return out


# ===================================================================
# SERVIZIO 4 · VISURA CAMERALE (Visengine)
# Prod scope:    POST:visengine2.altravia.com/richiesta + GET .../documento
# Sandbox scope: POST:test.visengine2.altravia.com/richiesta + GET .../documento
# ===================================================================
async def fetch_visura(piva: str) -> dict:
    """Visura sandbox richiede 2 step: prima GET /fornitori per hash, poi POST /richiesta.

    Per ora manteniamo il fallback MOCK finché non è disponibile un piano visura
    completo su prod. Il flusso è documentato in visengine2.altravia.com.
    """
    key = (piva or "").strip()
    if has_credentials():
        host = _host("visengine2.altravia.com")
        # Step 1: recupera hash del prodotto visura dal fornitore
        scope_forn = [f"GET:{host}/fornitori"]
        forn = await _call_api(scope_forn, "GET", f"https://{host}/fornitori")
        hash_visura = None
        if forn and forn.get("success"):
            items = forn.get("data") or []
            for it in items if isinstance(items, list) else []:
                if (it.get("tipo") or "").lower() == "ordinaria":
                    hash_visura = it.get("hash") or it.get("hash_visura")
                    break
        if hash_visura:
            scope_post = [f"POST:{host}/richiesta"]
            res_post = await _call_api(
                scope_post, "POST", f"https://{host}/richiesta",
                json={"hash_visura": hash_visura, "piva": key, "tipo_visura": "ordinaria"},
            )
            if res_post and res_post.get("success"):
                rid = (res_post.get("data") or {}).get("id") or res_post.get("id") or "n/a"
                return _normalize_visura(res_post.get("data") or {}, key, rid)
        logger.info("OpenAPI.it live fetch_visura non completato, fallback a MOCK per '%s'", key)
    return _mock_visura(key)


def _normalize_visura(data: dict, piva: str, request_id: str) -> dict:
    return {
        "provider": "openapi.it/visure (LIVE)",
        "piva": piva,
        "request_id": request_id,
        "stato": data.get("stato") or "IN_LAVORAZIONE",
        "ragione_sociale": data.get("denominazione") or data.get("ragione_sociale"),
        "tipo_visura": data.get("tipo_visura") or "ordinaria",
        "data_estrazione": data.get("data_estrazione"),
        "capitale_sociale": data.get("capitale_sociale"),
        "amministratori": data.get("amministratori") or [],
        "sedi_secondarie": data.get("sedi_secondarie") or 0,
        "unita_locali": data.get("unita_locali") or 0,
        "bilanci_depositati": data.get("bilanci_depositati"),
        "download_url": data.get("download_url"),
        "rating_finanziario": data.get("rating"),
        "punteggio_rischio_credito": data.get("credit_score"),
    }


def _mock_visura(piva: str) -> dict:
    random.seed(hash(piva + "_visura") % (2**31))
    company = _mock_company(piva)
    return {
        "provider": "openapi.it/visure (MOCK)",
        "piva": piva,
        "ragione_sociale": company["ragione_sociale"],
        "tipo_visura": "ordinaria",
        "data_estrazione": "2026-02-04",
        "capitale_sociale": company["capitale_sociale_versato"],
        "amministratori": [
            {"nome_cognome": company["legale_rappresentante"], "carica": "Amministratore Unico"},
        ],
        "sedi_secondarie": random.randint(0, 3),
        "unita_locali": random.randint(1, 5),
        "bilanci_depositati": random.randint(2019, 2024),
        "download_url": None,
        "rating_finanziario": random.choice(["A", "BBB", "BB", "B"]),
        "punteggio_rischio_credito": random.randint(30, 90),
    }


# ===================================================================
# SERVIZIO 5 · AUTOMOTIVE by TARGA
# ===================================================================
async def fetch_automotive_by_targa(targa: str) -> dict:
    """Lookup veicolo per TARGA. Fallback MOCK trasparente."""
    key = (targa or "").upper().strip().replace(" ", "")
    if has_credentials():
        host = _host("automotive.openapi.it")
        for path in ("veicoli", "pra"):
            scope = [f"GET:{host}/{path}"]
            res = await _call_api(scope, "GET", f"https://{host}/{path}/{key}")
            if res and res.get("success") and res.get("data"):
                return _normalize_automotive(res["data"], key)
        logger.info("OpenAPI.it live fetch_automotive_by_targa fallito, fallback MOCK per '%s'", key)
    return _mock_automotive_by_targa(key)


def _normalize_automotive(data, targa: str) -> dict:
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return _mock_automotive_by_targa(targa)
    return {
        "provider": "openapi.it/automotive (LIVE)",
        "targa": data.get("targa") or targa,
        "marca": data.get("marca") or data.get("make"),
        "modello": data.get("modello") or data.get("model"),
        "allestimento": data.get("allestimento") or data.get("versione"),
        "cilindrata": data.get("cilindrata") or data.get("displacement"),
        "potenza_kw": data.get("potenza_kw") or data.get("kw"),
        "potenza_cv": data.get("potenza_cv") or data.get("cv"),
        "alimentazione": data.get("alimentazione") or data.get("fuel"),
        "anno_immatricolazione": data.get("anno_immatricolazione") or data.get("year"),
        "data_immatricolazione": data.get("data_immatricolazione"),
        "scadenza_revisione": data.get("scadenza_revisione"),
        "telaio": data.get("telaio") or data.get("vin"),
        "categoria": data.get("categoria"),
        "euro": data.get("euro"),
        "raw": data,
    }


def _mock_automotive_by_targa(targa: str) -> dict:
    random.seed(hash(targa + "_veh_by_targa") % (2**31))
    marca = random.choice(["FIAT", "VOLKSWAGEN", "BMW", "AUDI", "RENAULT", "PEUGEOT"])
    modello = random.choice(["500", "PANDA", "GOLF", "SERIE 3", "A4", "CLIO"])
    return {
        "provider": "openapi.it/automotive (MOCK)",
        "targa": targa,
        "marca": marca, "modello": modello,
        "allestimento": random.choice(["LOUNGE", "SPORT", "GT LINE"]),
        "cilindrata": random.choice([1000, 1200, 1400, 1600, 1900]),
        "potenza_kw": random.randint(50, 130),
        "potenza_cv": random.randint(70, 180),
        "alimentazione": random.choice(["BENZINA", "DIESEL", "GPL", "IBRIDA"]),
        "anno_immatricolazione": random.randint(2010, 2024),
        "data_immatricolazione": f"{random.randint(2010,2024)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
        "scadenza_revisione": f"{random.randint(2025,2027)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
        "telaio": f"WBA{''.join(random.choices('0123456789ABCDEFGHJKLMNPRSTVWXYZ',k=14))}",
        "categoria": "AUTOVETTURA",
        "euro": random.choice(["EURO 5", "EURO 6"]),
    }


# ===================================================================
# SERVIZIO 6 · RISK
# ===================================================================
async def fetch_risk(cf_or_piva: str) -> dict:
    key = (cf_or_piva or "").strip()
    if has_credentials():
        host = _host("risk.openapi.it")
        res = await _call_api([f"GET:{host}/report"], "GET", f"https://{host}/report/{key}")
        if res and res.get("success") and res.get("data"):
            return _normalize_risk(res["data"], key)
        logger.info("OpenAPI.it live fetch_risk fallito, fallback MOCK per '%s'", key)
    return _mock_risk(key)


def _normalize_risk(data, key: str) -> dict:
    if isinstance(data, dict):
        return {
            "provider": "openapi.it/risk (LIVE)",
            "soggetto": key,
            "rating": data.get("rating"),
            "score_credito": data.get("credit_score") or data.get("score"),
            "livello_rischio": data.get("risk_level"),
            "protesti": data.get("protesti") or [],
            "pregiudizievoli": data.get("pregiudizievoli") or [],
            "procedure_concorsuali": data.get("procedure_concorsuali") or [],
            "eventi_negativi_count": data.get("eventi_negativi_count") or 0,
            "data_report": data.get("data_report"),
        }
    return _mock_risk(key)


def _mock_risk(key: str) -> dict:
    random.seed(hash(key + "_risk") % (2**31))
    n_prot = random.choice([0, 0, 0, 1, 2])
    n_preg = random.choice([0, 0, 0, 1])
    return {
        "provider": "openapi.it/risk (MOCK)",
        "soggetto": key,
        "rating": random.choice(["A", "BBB", "BB", "B"]),
        "score_credito": random.randint(30, 95),
        "livello_rischio": random.choice(["basso", "medio", "medio", "alto"]),
        "protesti": [{"data": "2023-05-15", "importo_eur": 500.0, "tipo": "CAMBIALE"} for _ in range(n_prot)],
        "pregiudizievoli": [{"data": "2022-08-20", "tipo": "IPOTECA", "importo_eur": 15000.0} for _ in range(n_preg)],
        "procedure_concorsuali": [],
        "eventi_negativi_count": n_prot + n_preg,
        "data_report": "2026-02-04",
    }

