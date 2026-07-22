"""OpenAPI.it integration service — LIVE (OAuth2 client_credentials) con fallback MOCK.

Flusso OAuth2 v2 (documentazione: https://console.openapi.com/it/apis/oauth/documentation):
  1. Basic Auth con email + APIkey a POST https://oauth.openapi.it/token
     con body {"scopes": [...], "ttl": seconds}  → riceve access token
  2. Bearer token per chiamate alle API di dominio (imprese.openapi.it, visengine2, ecc.)

Variabili d'ambiente lette:
  OPENAPI_IT_CLIENT_ID     → email account OpenAPI.it (es "user@example.com")
  OPENAPI_IT_CLIENT_SECRET → APIkey personale (da console.openapi.com/it/oauth)
  OPENAPI_IT_ENV           → "prod" (default) | "sandbox"

Se le credenziali mancano OPPURE una chiamata live fallisce (402 saldo zero,
401 non autorizzato, connection error, ecc.) → **automatic fallback** su dati MOCK
con seed deterministico per non spezzare l'UI.

Ogni token è cache-ato in memoria fino a scadenza-60s.
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

# ---------- Config ----------
def _cfg() -> dict:
    env = (os.environ.get("OPENAPI_IT_ENV") or "prod").strip().lower()
    is_sandbox = env == "sandbox"
    return {
        "client_id": (os.environ.get("OPENAPI_IT_CLIENT_ID") or "").strip(),
        "client_secret": (os.environ.get("OPENAPI_IT_CLIENT_SECRET") or "").strip(),
        "env": env,
        "oauth_base": "https://test.oauth.openapi.it" if is_sandbox else "https://oauth.openapi.it",
        # Le API di dominio non hanno "test." (sono gli stessi endpoint ma consumano crediti test)
        "imprese_base": "https://imprese.openapi.it",
        "visengine_base": "https://visengine2.altravia.com",
        "catasto_base": "https://catasto.openapi.it",  # se non esistente → mock fallback
        "automotive_base": "https://automotive.openapi.it",  # se non esistente → mock fallback
    }


def has_credentials() -> bool:
    c = _cfg()
    return bool(c["client_id"] and c["client_secret"])


def is_mock_mode() -> bool:
    """Legacy compatibility — se non ci sono credenziali usiamo mock."""
    return not has_credentials()


# ---------- Token cache (in-memory) ----------
# _token_cache: dict mapping scope_key → {"token": str, "expire": epoch_seconds}
_token_cache: dict = {}


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


async def _get_token(scopes: list[str], ttl_sec: int = 3600) -> Optional[str]:
    """Ottiene un access_token dagli scopes richiesti. Usa cache in memoria.

    Ritorna None se le credenziali non sono presenti o se il POST /token fallisce.
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
                "OpenAPI.it token endpoint HTTP %s: %s", r.status_code, r.text[:300]
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
    """Ritorna il credito residuo in € (o None se non disponibile).

    Usa direttamente Basic Auth (endpoint /credit non richiede token specifico).
    """
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


# ---------- API calls ----------
async def _call_api(scopes: list[str], method: str, url: str, **kwargs) -> Optional[dict]:
    """Wrapper per chiamate live all'API OpenAPI.it. Ritorna dict o None su errore."""
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
# ===================================================================
async def fetch_company(piva_or_cf: str) -> dict:
    """Lookup dati camerali per P.IVA/CF. Usa `imprese.openapi.it/advance/{key}` in live mode.

    Livello 'advance' include ATECO, capitale, LR, PEC.
    """
    key = (piva_or_cf or "").strip()
    if has_credentials():
        c = _cfg()
        scopes = [f"GET:imprese.openapi.it/advance"]
        url = f"{c['imprese_base']}/advance/{key}"
        res = await _call_api(scopes, "GET", url)
        if res and res.get("success") and res.get("data"):
            return _normalize_company(res["data"], key)
        # Fallback su livello base
        res_base = await _call_api([f"GET:imprese.openapi.it/base"], "GET", f"{c['imprese_base']}/base/{key}")
        if res_base and res_base.get("success") and res_base.get("data"):
            return _normalize_company(res_base["data"], key)
        logger.info("OpenAPI.it live fetch_company fallito, fallback a MOCK per '%s'", key)
    return _mock_company(key)


def _normalize_company(data: dict, key: str) -> dict:
    """Normalizza il JSON di imprese.openapi.it al formato usato dal frontend."""
    # imprese.openapi.it può restituire un oggetto o una lista; gestiamo entrambi
    if isinstance(data, list):
        data = data[0] if data else {}
    addr = data.get("indirizzo") or {}
    if isinstance(addr, str):
        addr_str, cap, comune, provincia = addr, None, None, None
    else:
        addr_str = addr.get("registeredAddress") or addr.get("strada") or addr.get("street") or ""
        cap = addr.get("cap") or addr.get("zipCode")
        comune = addr.get("comune") or addr.get("town")
        provincia = addr.get("provincia") or addr.get("province")
    return {
        "provider": "openapi.it (LIVE)",
        "piva": data.get("vatCode") or data.get("piva") or (key if len(key) == 11 else None),
        "cf": data.get("taxCode") or data.get("cf") or key,
        "ragione_sociale": data.get("companyName") or data.get("denominazione") or data.get("ragione_sociale"),
        "indirizzo": addr_str,
        "cap": cap,
        "comune": comune,
        "provincia": provincia,
        "ateco": data.get("atecoCode") or data.get("codice_ateco"),
        "ateco_descrizione": data.get("atecoDescription") or data.get("descrizione_ateco"),
        "pec": data.get("pec"),
        "capitale_sociale_versato": data.get("shareCapital") or data.get("capitale_sociale"),
        "legale_rappresentante": data.get("legalForm") or data.get("legale_rappresentante"),
        "forma_giuridica": data.get("legalForm") or data.get("forma_giuridica"),
        "data_costituzione": data.get("startDate") or data.get("data_costituzione"),
        "attiva": data.get("companyStatus", "").upper() != "CESSATA",
        "cciaa": data.get("cciaa"),
        "rea": data.get("rea") or data.get("reaCode"),
        "raw": data,  # per debugging
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
# SERVIZIO 2 · CATASTO (immobili di persona fisica/giuridica)
# ===================================================================
async def fetch_cadastre(cf_or_piva: str) -> list[dict]:
    """Lookup immobili al catasto per CF/P.IVA.

    Se ci sono credenziali OpenAPI.it, tenta il servizio Italian Cadastre di
    OpenAPI. Se fallisce (endpoint non attivo, saldo=0, credenziali errate) →
    fallback MOCK.
    """
    key = (cf_or_piva or "").strip()
    if has_credentials():
        c = _cfg()
        # Endpoint documentato: catasto.openapi.it richiede scope specifico
        scopes = [f"GET:catasto.openapi.it/persona"]
        url = f"{c['catasto_base']}/persona/{key}"
        res = await _call_api(scopes, "GET", url)
        if res and res.get("success") and res.get("data"):
            return _normalize_cadastre(res["data"])
        logger.info("OpenAPI.it live fetch_cadastre fallito, fallback a MOCK per '%s'", key)
    return _mock_cadastre(key)


def _normalize_cadastre(data) -> list[dict]:
    if isinstance(data, dict):
        data = data.get("immobili") or data.get("proprieta") or [data]
    if not isinstance(data, list):
        return []
    out = []
    for im in data:
        out.append({
            "provider": "openapi.it/cadastre (LIVE)",
            "comune": im.get("comune"),
            "foglio": im.get("foglio"),
            "particella": im.get("particella"),
            "subalterno": im.get("subalterno") or im.get("sub"),
            "categoria": im.get("categoria"),
            "classe": im.get("classe"),
            "consistenza": im.get("consistenza"),
            "superficie_catastale_mq": im.get("superficie") or im.get("mq"),
            "rendita_eur": im.get("rendita"),
            "indirizzo": im.get("indirizzo"),
            "titolo": im.get("titolarita") or im.get("titolo") or "Proprietà",
        })
    return out


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
# SERVIZIO 3 · AUTOMOTIVE (veicoli PRA)
# ===================================================================
async def fetch_vehicles(cf_or_piva: str) -> list[dict]:
    key = (cf_or_piva or "").strip()
    if has_credentials():
        c = _cfg()
        scopes = [f"GET:automotive.openapi.it/pra"]
        url = f"{c['automotive_base']}/pra/{key}"
        res = await _call_api(scopes, "GET", url)
        if res and res.get("success") and res.get("data"):
            return _normalize_vehicles(res["data"])
        logger.info("OpenAPI.it live fetch_vehicles fallito, fallback a MOCK per '%s'", key)
    return _mock_vehicles(key)


def _normalize_vehicles(data) -> list[dict]:
    if isinstance(data, dict):
        data = data.get("veicoli") or data.get("vehicles") or [data]
    if not isinstance(data, list):
        return []
    out = []
    for v in data:
        out.append({
            "provider": "openapi.it/automotive (LIVE)",
            "targa": v.get("targa") or v.get("plate"),
            "marca": v.get("marca") or v.get("make"),
            "modello": v.get("modello") or v.get("model"),
            "alimentazione": v.get("alimentazione"),
            "cilindrata": v.get("cilindrata"),
            "potenza_kw": v.get("potenza_kw") or v.get("power_kw"),
            "data_immatricolazione": v.get("data_immatricolazione") or v.get("first_registration"),
            "scadenza_revisione": v.get("scadenza_revisione"),
            "categoria": v.get("categoria"),
            "tipo_alimentazione": v.get("euro"),
        })
    return out


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
# SERVIZIO 4 · VISURA CAMERALE ORDINARIA (Visengine)
# ===================================================================
async def fetch_visura(piva: str) -> dict:
    """Visura camerale via visengine2. Flusso a 2 step (richiesta + poll).

    Nota: la visura ordinaria è un servizio asincrono; l'endpoint POST /richiesta
    ritorna un id, poi si polla GET /richiesta/{id} finché "stato"=="COMPLETATO"
    ed infine si scarica il PDF via GET /documento/{id}.

    In questa versione facciamo solo lo step POST/GET per ottenere metadata
    veloci; il download PDF va gestito lato UI (link/download_url).
    """
    key = (piva or "").strip()
    if has_credentials():
        c = _cfg()
        scopes = [
            "POST:visengine2.altravia.com/richiesta",
            "GET:visengine2.altravia.com/richiesta",
        ]
        res_post = await _call_api(
            scopes, "POST",
            f"{c['visengine_base']}/richiesta",
            json={"tipo_visura": "ordinaria", "piva": key},
        )
        if res_post and res_post.get("success"):
            rid = (res_post.get("data") or {}).get("id") or res_post.get("id")
            if rid:
                # Un solo poll (l'UI può richiamare l'endpoint per aggiornamenti)
                res_get = await _call_api(
                    scopes, "GET",
                    f"{c['visengine_base']}/richiesta/{rid}",
                )
                if res_get:
                    return _normalize_visura(res_get.get("data") or {}, key, rid)
        logger.info("OpenAPI.it live fetch_visura fallito, fallback a MOCK per '%s'", key)
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
