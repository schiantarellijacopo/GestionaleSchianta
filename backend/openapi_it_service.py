"""OpenAPI.it integration — LIVE PROD (OAuth2 client_credentials) con fallback MOCK.

Scopes verificati sull'account (2026-02):
  ✅ Visengine     — `GET:visengine2.altravia.com/fornitori` (+ POST /richiesta, GET /documento)
  ✅ Risk          — `POST:risk.openapi.com/IT-report-persona`, `GET:.../IT-report-azienda`
  ✅ Catasto       — `GET:catasto.openapi.it/territorio`, `POST:.../richiesta`
  🟡 Automotive    — token OK ma serve "Codice Cliente" configurato sull'account
                     (dominio `automotive.openapi.com/IT-car/{targa}` e `/IT-bike/{targa}`)
  ❌ Imprese       — 406 "API not enabled" — richiede attivazione sulla console
                     https://console.openapi.com/it/apis/company

L'utente può in qualunque momento attivare/abilitare prodotti mancanti nella console.
Se manca lo scope o il token OAuth va in errore → fallback MOCK trasparente.

ENV richieste:
  OPENAPI_IT_CLIENT_ID     → email account OpenAPI.it
  OPENAPI_IT_CLIENT_SECRET → APIkey personale (console.openapi.com/it/oauth)
  OPENAPI_IT_ENV           → "prod" (default) | "sandbox"
  OPENAPI_IT_BEARER_TOKEN  → (opzionale) token statico che bypassa OAuth exchange
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


def _host(name: str, *, sandbox_prefix: bool = True) -> str:
    """Ritorna il dominio API con prefisso `test.` in sandbox (dove supportato).

    Alcune API non supportano il prefisso `test.` (automotive.openapi.com,
    risk.openapi.com). In quel caso passa sandbox_prefix=False.
    """
    if _is_sandbox() and sandbox_prefix:
        return f"test.{name}"
    return name


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
    static_bearer = (os.environ.get("OPENAPI_IT_BEARER_TOKEN") or "").strip()
    if static_bearer:
        return True
    c = _cfg()
    return bool(c["client_id"] and c["client_secret"])


def is_mock_mode() -> bool:
    return not has_credentials()


# ---------- Token cache ----------
_token_cache: dict = {}


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


async def _get_token(scopes: list[str], ttl_sec: int = 3600) -> Optional[str]:
    static_bearer = (os.environ.get("OPENAPI_IT_BEARER_TOKEN") or "").strip()
    if static_bearer:
        return static_bearer
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
            logger.warning("OpenAPI.it token %s HTTP %s: %s", scopes, r.status_code, r.text[:300])
            return None
        data = r.json()
        token = data.get("token")
        expire = int(data.get("expire") or (now + ttl_sec))
        if token:
            _token_cache[cache_key] = {"token": token, "expire": expire}
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
            logger.warning("OpenAPI.it %s %s → 402 credito/billing", method, url)
            return None
        if r.status_code >= 400:
            logger.warning("OpenAPI.it %s %s → HTTP %s: %s", method, url, r.status_code, r.text[:300])
            return None
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
    except Exception as e:
        logger.warning("OpenAPI.it %s %s error: %s", method, url, e)
        return None


# ===================================================================
# SERVIZIO 1 · COMPANY (Imprese)
# ===================================================================
async def fetch_company(piva_or_cf: str) -> dict:
    key = (piva_or_cf or "").strip()
    if has_credentials():
        host = _host("imprese.openapi.it")
        for endpoint in ("advance", "base"):
            res = await _call_api(
                [f"GET:{host}/{endpoint}"], "GET",
                f"https://{host}/{endpoint}/{key}",
            )
            if res and res.get("success") and res.get("data"):
                return _normalize_company(res["data"], key)
        logger.info("OpenAPI.it Company fallback MOCK per '%s'", key)
    return _mock_company(key)


def _normalize_company(data, key: str) -> dict:
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return _mock_company(key)
    dett = data.get("dettaglio") or {}
    indirizzo_str = data.get("indirizzo") or ""
    if not indirizzo_str and (data.get("via") or data.get("toponimo")):
        indirizzo_str = " ".join(x for x in [
            data.get("toponimo"), data.get("via"), str(data.get("civico") or "")
        ] if x).strip()
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


def _mock_company(key: str) -> dict:
    random.seed(hash(key) % (2**31))
    return {
        "provider": "openapi.it (MOCK)",
        "piva": key if len(key) == 11 else "".join(random.choices("0123456789", k=11)),
        "cf": key,
        "ragione_sociale": random.choice([
            "Tecnologie Innovative SRL", "Verdi & Bianchi SPA",
            "Milano Servizi SRL", "Alpha Consulting SNC",
        ]) + f" #{random.randint(100,999)}",
        "indirizzo": f"Via {random.choice(['Roma','Milano','Torino'])} {random.randint(1,200)}",
        "cap": f"{random.randint(20000, 39999)}",
        "comune": random.choice(["MILANO", "TORINO", "BOLOGNA", "ROMA"]),
        "provincia": random.choice(["MI", "TO", "BO", "RM"]),
        "ateco": f"{random.randint(10, 82)}.{random.randint(10, 99)}",
        "ateco_descrizione": random.choice([
            "Attività dei servizi di ristorazione",
            "Consulenza gestionale e amministrativa",
            "Sviluppo software e consulenza informatica",
        ]),
        "pec": f"pec{random.randint(100,999)}@legalmail.it",
        "capitale_sociale_versato": random.choice([10000, 50000, 100000]),
        "legale_rappresentante": random.choice(["Mario Rossi", "Giulia Bianchi"]),
        "forma_giuridica": random.choice(["SRL", "SPA"]),
        "data_costituzione": "2010-05-14",
        "attiva": True,
        "cciaa": "MI",
        "rea": f"MI-{random.randint(1000000, 9999999)}",
    }


# ===================================================================
# SERVIZIO 2 · CATASTO (per persona/azienda)
# ===================================================================
async def fetch_cadastre(cf_or_piva: str) -> list[dict]:
    """Catasto — endpoint è PATH PARAMETER (non body field).
    Usa `ricerca_nazionale` (non richiede provincia). Ricerca per CF/PIVA in tutta Italia.
    """
    key = (cf_or_piva or "").strip()
    if has_credentials():
        host = _host("catasto.openapi.it")
        body = {"cf_piva": key, "tipo_catasto": "TF"}
        res = await _call_api(
            [f"POST:{host}/richiesta"], "POST",
            f"https://{host}/richiesta/ricerca_nazionale", json=body,
        )
        if res and res.get("success"):
            rid = (res.get("data") or {}).get("id") or res.get("id")
            if rid:
                import asyncio
                for _ in range(4):
                    await asyncio.sleep(2.0)
                    r2 = await _call_api(
                        [f"GET:{host}/richiesta"], "GET",
                        f"https://{host}/richiesta/{rid}",
                    )
                    if r2 and r2.get("success"):
                        payload = r2.get("data") or {}
                        stato = (payload.get("stato") or "").lower()
                        if stato in ("completato", "success", "done", "evaso"):
                            return _normalize_cadastre(payload, key)
                return _mock_cadastre(key)
        logger.info("OpenAPI.it Catasto fallback MOCK per '%s'", key)
    return _mock_cadastre(key)


def _normalize_cadastre(payload: dict, key: str) -> list[dict]:
    immobili = payload.get("immobili") or payload.get("beni") or payload.get("risultato") or []
    if not isinstance(immobili, list):
        immobili = [immobili]
    out = []
    for im in immobili[:20]:
        if not isinstance(im, dict):
            continue
        out.append({
            "provider": "openapi.it/catasto (LIVE)",
            "comune": im.get("comune") or im.get("Comune"),
            "foglio": im.get("foglio") or im.get("Foglio"),
            "particella": im.get("particella") or im.get("Particella"),
            "subalterno": im.get("subalterno") or im.get("Sub"),
            "categoria": im.get("categoria") or im.get("Categoria"),
            "classe": im.get("classe") or im.get("Classe"),
            "consistenza": im.get("consistenza") or im.get("Consistenza"),
            "superficie_catastale_mq": im.get("superficie") or im.get("Superficie"),
            "rendita_eur": im.get("rendita") or im.get("Rendita"),
            "indirizzo": im.get("indirizzo") or im.get("Indirizzo"),
            "titolo": im.get("titolarita") or im.get("Titolo") or "Proprietà",
        })
    return out


def _mock_cadastre(key: str) -> list[dict]:
    random.seed(hash(key + "_cad") % (2**31))
    n = random.randint(0, 4)
    out = []
    for _ in range(n):
        out.append({
            "provider": "openapi.it/catasto (MOCK)",
            "comune": random.choice(["MILANO", "ROMA", "TORINO"]),
            "foglio": random.randint(1, 999),
            "particella": random.randint(1, 999),
            "subalterno": random.randint(1, 20),
            "categoria": random.choice(["A/2", "A/3", "C/6"]),
            "classe": str(random.randint(1, 6)),
            "consistenza": random.randint(3, 12),
            "superficie_catastale_mq": random.randint(60, 250),
            "rendita_eur": round(random.uniform(300, 3000), 2),
            "indirizzo": f"Via {random.choice(['Verdi','Rossi','Bianchi'])} {random.randint(1,150)}",
            "titolo": "Proprietà 100%",
        })
    return out


# ===================================================================
# SERVIZIO 3 · AUTOMOTIVE by CF/PIVA (non supportato — solo by targa)
# ===================================================================
async def fetch_vehicles(cf_or_piva: str) -> list[dict]:
    """PRA by CF non è disponibile sull'API OpenAPI.it (solo lookup by targa).
    Ritorna sempre MOCK per compatibilità UI."""
    return _mock_vehicles((cf_or_piva or "").strip())


def _mock_vehicles(key: str) -> list[dict]:
    random.seed(hash(key + "_veh") % (2**31))
    n = random.randint(0, 3)
    out = []
    for _ in range(n):
        marca = random.choice(["FIAT", "VOLKSWAGEN", "BMW", "AUDI", "RENAULT"])
        modello = random.choice(["500", "PANDA", "GOLF", "SERIE 3", "A4"])
        out.append({
            "provider": "openapi.it/automotive (MOCK)",
            "targa": f"{''.join(random.choices('ABCDEFGHJKLMNPRSTVXYZ',k=2))}{random.randint(100,999)}{''.join(random.choices('ABCDEFGHJKLMNPRSTVXYZ',k=2))}",
            "marca": marca, "modello": modello,
            "alimentazione": random.choice(["BENZINA", "DIESEL", "IBRIDA"]),
            "cilindrata": random.choice([1200, 1400, 1600]),
            "potenza_kw": random.randint(50, 130),
            "data_immatricolazione": f"{random.randint(2010,2024)}-05-14",
            "scadenza_revisione": f"{random.randint(2025,2027)}-05-14",
            "categoria": "AUTOVETTURA",
        })
    return out


# ===================================================================
# SERVIZIO 4 · VISURA CAMERALE (Visengine)
# ===================================================================
async def fetch_visura(piva: str) -> dict:
    """Flow ufficiale Visengine PROD:
       1) GET /visure → lista prodotti con hash_visura (Camerali/Patronato)
       2) POST /richiesta → id richiesta
       3) GET /richiesta/{id} → polling per download_url
    """
    key = (piva or "").strip()
    if has_credentials():
        host = "visengine2.altravia.com"
        # Step 1: /visure — trova hash Camera Commercio (PF vs PG)
        vis_list = await _call_api([f"GET:{host}/visure"], "GET", f"https://{host}/visure")
        hash_visura = None
        is_pg = len(key) == 11 and key.isdigit()
        if vis_list and vis_list.get("success"):
            items = vis_list.get("data") or []
            # Cerca "Visura Centrale Rischi Persona Giuridica/Fisica"
            keyword_pg = "giuridica"
            keyword_pf = "persona fisica"
            for it in items:
                name = (it.get("nome_visura") or "").lower()
                if is_pg and keyword_pg in name and "camerali" in (it.get("nome_categoria") or "").lower():
                    hash_visura = it.get("hash_visura")
                    break
                if not is_pg and keyword_pf in name and "camerali" in (it.get("nome_categoria") or "").lower():
                    hash_visura = it.get("hash_visura")
                    break
            # Fallback: primo prodotto camerale
            if not hash_visura:
                for it in items:
                    if "camerali" in (it.get("nome_categoria") or "").lower():
                        hash_visura = it.get("hash_visura")
                        break
        if hash_visura:
            # json_visura è REQUIRED — contiene i dati specifici della visura richiesta
            json_visura = {"cf_piva": key}
            if is_pg:
                json_visura["piva"] = key
            else:
                json_visura["cf"] = key.upper()
            body = {
                "hash_visura": hash_visura,
                "json_visura": json_visura,
            }
            res_post = await _call_api(
                [f"POST:{host}/richiesta"], "POST", f"https://{host}/richiesta",
                json=body,
            )
            if res_post and res_post.get("success"):
                pd = res_post.get("data") or {}
                rid = pd.get("id") or pd.get("id_richiesta") or res_post.get("id")
                if rid:
                    import asyncio
                    for _ in range(5):
                        await asyncio.sleep(2.0)
                        r_get = await _call_api(
                            [f"GET:{host}/richiesta"], "GET",
                            f"https://{host}/richiesta/{rid}",
                        )
                        if r_get and r_get.get("success"):
                            gp = r_get.get("data") or {}
                            stato = (gp.get("stato") or "").lower()
                            if stato in ("completato", "success", "done", "pronto", "evaso"):
                                return _normalize_visura(gp, key, rid)
                    # Ritorna comunque i dati parziali (in lavorazione)
                    return _normalize_visura(pd, key, rid)
        logger.info("OpenAPI.it Visura fallback MOCK per '%s' (hash=%s)", key, hash_visura)
    return _mock_visura(key)


def _normalize_visura(data: dict, piva: str, request_id: str) -> dict:
    return {
        "provider": "openapi.it/visure (LIVE)",
        "piva": piva,
        "request_id": request_id,
        "stato": data.get("stato") or "IN_LAVORAZIONE",
        "ragione_sociale": data.get("denominazione") or data.get("ragione_sociale"),
        "tipo_visura": data.get("tipo_visura") or "ordinaria",
        "data_estrazione": data.get("data_estrazione") or data.get("data_richiesta"),
        "capitale_sociale": data.get("capitale_sociale"),
        "amministratori": data.get("amministratori") or [],
        "sedi_secondarie": data.get("sedi_secondarie") or 0,
        "unita_locali": data.get("unita_locali") or 0,
        "bilanci_depositati": data.get("bilanci_depositati"),
        "download_url": data.get("download_url") or data.get("url_documento") or data.get("url"),
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
        "rating_finanziario": random.choice(["A", "BBB", "BB"]),
        "punteggio_rischio_credito": random.randint(30, 90),
    }


# ===================================================================
# SERVIZIO 5 · AUTOMOTIVE by TARGA (dominio .com, NO test. sandbox)
# ===================================================================
async def fetch_automotive_by_targa(targa: str) -> dict:
    key = (targa or "").upper().strip().replace(" ", "")
    if has_credentials():
        # Dominio automotive.openapi.com (NON .it, NON test.)
        host = "automotive.openapi.com"
        for path in ("IT-car", "IT-bike"):
            res = await _call_api(
                [f"GET:{host}/{path}"], "GET",
                f"https://{host}/{path}/{key}",
            )
            if res and res.get("success") and res.get("data"):
                return _normalize_automotive(res["data"], key)
        logger.info("OpenAPI.it Automotive fallback MOCK per '%s'", key)
    return _mock_automotive_by_targa(key)


def _normalize_automotive(data, targa: str) -> dict:
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return _mock_automotive_by_targa(targa)
    return {
        "provider": "openapi.it/automotive (LIVE)",
        "targa": data.get("targa") or data.get("plate") or targa,
        "marca": data.get("marca") or data.get("make") or data.get("brand"),
        "modello": data.get("modello") or data.get("model"),
        "allestimento": data.get("allestimento") or data.get("versione") or data.get("version"),
        "cilindrata": data.get("cilindrata") or data.get("displacement"),
        "potenza_kw": data.get("potenza_kw") or data.get("kw"),
        "potenza_cv": data.get("potenza_cv") or data.get("cv") or data.get("hp"),
        "alimentazione": data.get("alimentazione") or data.get("fuel"),
        "anno_immatricolazione": data.get("anno_immatricolazione") or data.get("year"),
        "data_immatricolazione": data.get("data_immatricolazione"),
        "scadenza_revisione": data.get("scadenza_revisione") or data.get("mot_expiration"),
        "telaio": data.get("telaio") or data.get("vin"),
        "categoria": data.get("categoria"),
        "euro": data.get("euro") or data.get("emission_class"),
        "raw": data,
    }


def _mock_automotive_by_targa(targa: str) -> dict:
    random.seed(hash(targa + "_veh_by_targa") % (2**31))
    marca = random.choice(["FIAT", "VOLKSWAGEN", "BMW", "AUDI", "RENAULT"])
    modello = random.choice(["500", "PANDA", "GOLF", "SERIE 3", "A4"])
    return {
        "provider": "openapi.it/automotive (MOCK)",
        "targa": targa,
        "marca": marca, "modello": modello,
        "allestimento": random.choice(["LOUNGE", "SPORT", "GT LINE"]),
        "cilindrata": random.choice([1000, 1200, 1400, 1600]),
        "potenza_kw": random.randint(50, 130),
        "potenza_cv": random.randint(70, 180),
        "alimentazione": random.choice(["BENZINA", "DIESEL", "IBRIDA"]),
        "anno_immatricolazione": random.randint(2010, 2024),
        "data_immatricolazione": f"{random.randint(2010,2024)}-05-14",
        "scadenza_revisione": f"{random.randint(2025,2027)}-05-14",
        "telaio": f"WBA{''.join(random.choices('0123456789ABCDEFGHJKLMNPRSTVWXYZ',k=14))}",
        "categoria": "AUTOVETTURA",
        "euro": random.choice(["EURO 5", "EURO 6"]),
    }


# ===================================================================
# SERVIZIO 6 · RISK (dominio .com, tipo PF vs PG differenziato)
# ===================================================================
async def fetch_risk(cf_or_piva: str, name: str = "", surname: str = "",
                     company_name: str = "") -> dict:
    """Report rischio credito. PG richiede taxCode+companyName, PF richiede taxCode+name+surname."""
    key = (cf_or_piva or "").strip()
    if has_credentials():
        host = "risk.openapi.com"  # ⚠️ .com — NON .it
        is_pg = len(key) == 11 and key.isdigit()
        if is_pg:
            body = {
                "taxCode": key,
                "companyName": company_name or "Azienda",
            }
            res = await _call_api(
                [f"POST:{host}/IT-report-azienda"], "POST",
                f"https://{host}/IT-report-azienda", json=body,
                headers={"Content-Type": "application/json"},
            )
        else:
            body = {
                "taxCode": key.upper(),
                "name": name or "N/A",
                "surname": surname or "N/A",
            }
            res = await _call_api(
                [f"POST:{host}/IT-report-persona"], "POST",
                f"https://{host}/IT-report-persona", json=body,
                headers={"Content-Type": "application/json"},
            )
        if res and res.get("success"):
            payload = res.get("data") or res
            return _normalize_risk(payload, key)
        logger.info("OpenAPI.it Risk fallback MOCK per '%s' (pg=%s)", key, is_pg)
    return _mock_risk(key)


def _normalize_risk(data, key: str) -> dict:
    if not isinstance(data, dict):
        return _mock_risk(key)
    return {
        "provider": "openapi.it/risk (LIVE)",
        "soggetto": key,
        "id_richiesta": data.get("id") or data.get("request_id"),
        "stato": data.get("stato") or data.get("status"),
        "rating": data.get("rating") or data.get("credit_rating"),
        "score_credito": data.get("credit_score") or data.get("score"),
        "livello_rischio": data.get("risk_level") or data.get("livello_rischio"),
        "protesti": data.get("protesti") or data.get("protests") or [],
        "pregiudizievoli": data.get("pregiudizievoli") or data.get("prejudicial") or [],
        "procedure_concorsuali": data.get("procedure_concorsuali") or data.get("bankruptcy") or [],
        "eventi_negativi_count": data.get("eventi_negativi_count") or 0,
        "data_report": data.get("data_report") or data.get("report_date"),
        "raw": data,
    }


def _mock_risk(key: str) -> dict:
    random.seed(hash(key + "_risk") % (2**31))
    n_prot = random.choice([0, 0, 0, 1, 2])
    n_preg = random.choice([0, 0, 0, 1])
    return {
        "provider": "openapi.it/risk (MOCK)",
        "soggetto": key,
        "rating": random.choice(["A", "BBB", "BB", "B"]),
        "score_credito": random.randint(30, 95),
        "livello_rischio": random.choice(["basso", "medio", "alto"]),
        "protesti": [{"data": "2023-05-15", "importo_eur": 500.0, "tipo": "CAMBIALE"} for _ in range(n_prot)],
        "pregiudizievoli": [{"data": "2022-08-20", "tipo": "IPOTECA", "importo_eur": 15000.0} for _ in range(n_preg)],
        "procedure_concorsuali": [],
        "eventi_negativi_count": n_prot + n_preg,
        "data_report": "2026-02-04",
    }
