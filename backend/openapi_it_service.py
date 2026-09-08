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
        data = (res or {}).get("data") or {}
        stato = (data.get("stato") or "").lower()
        # La ricerca_nazionale è sincrona: se "evasa" i dati sono già in data.risultato
        if stato in ("evasa", "completato", "success", "done") or data.get("risultato"):
            out = _normalize_cadastre_nazionale(data, key)
            if out:
                return out
        # Eventuale flusso asincrono con id (fallback)
        rid = data.get("id") or (res or {}).get("id")
        if rid and stato not in ("evasa",):
            import asyncio
            for _ in range(4):
                await asyncio.sleep(2.0)
                r2 = await _call_api(
                    [f"GET:{host}/richiesta"], "GET",
                    f"https://{host}/richiesta/{rid}",
                )
                d2 = (r2 or {}).get("data") or {}
                if (d2.get("stato") or "").lower() in ("evasa", "completato", "success", "done"):
                    out = _normalize_cadastre_nazionale(d2, key)
                    if out:
                        return out
        logger.info("OpenAPI.it Catasto fallback MOCK per '%s' (stato=%s)", key, stato)
    return _mock_cadastre(key)


def _normalize_cadastre_nazionale(data: dict, key: str) -> list[dict]:
    """Parsa la risposta 'ricerca_nazionale' del Catasto OpenAPI.it:
    data.risultato.soggetti[].catasti[].comuni[] → riepilogo immobili per comune."""
    ris = data.get("risultato") or {}
    soggetti = ris.get("soggetti") or ris.get("immobili") or []
    if isinstance(soggetti, dict):
        soggetti = [soggetti]
    out = []
    for sog in soggetti:
        if not isinstance(sog, dict):
            continue
        intest = " ".join([x for x in [sog.get("cognome"), sog.get("nome")] if x]) or sog.get("denominazione") or ""
        for cat in (sog.get("catasti") or []):
            prov = cat.get("provincia")
            for com in (cat.get("comuni") or [{"comune": cat.get("citta"), "fabbricati": cat.get("fabbricati"), "terreni": cat.get("terreni")}]):
                fab = com.get("fabbricati") or 0
                ter = com.get("terreni") or 0
                if not (fab or ter):
                    continue
                out.append({
                    "provider": "openapi.it/catasto (LIVE)",
                    "comune": com.get("comune"),
                    "provincia": prov,
                    "intestatario": intest,
                    "fabbricati": fab,
                    "terreni": ter,
                    "titolo": "Proprietà",
                    "id_soggetto": sog.get("id_soggetto"),
                    "note": f"{fab} fabbricati, {ter} terreni a {com.get('comune')} ({prov})",
                })
    return out


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
    # Coppie marca→modello COERENTI (il mock precedente accoppiava marca/modello a caso)
    modelli_per_marca = {
        "FIAT": ["500", "PANDA", "PUNTO", "TIPO"],
        "VOLKSWAGEN": ["GOLF", "POLO", "TIGUAN", "PASSAT"],
        "BMW": ["SERIE 1", "SERIE 3", "X1", "X3"],
        "AUDI": ["A1", "A3", "A4", "Q3"],
        "RENAULT": ["CLIO", "CAPTUR", "MEGANE", "TWINGO"],
    }
    marca = random.choice(list(modelli_per_marca.keys()))
    modello = random.choice(modelli_per_marca[marca])
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


# ===================================================================
# SERVIZIO 7 · CATASTO DETTAGLIATO (visura per soggetto → immobili + PDF)
# ===================================================================
_CAT_HOST = "catasto.openapi.it"


async def _catasto_bytes(url: str) -> tuple[int, bytes, str]:
    """Scarica un file binario (PDF/JSON) dal catasto usando il token."""
    token = await _get_token([f"GET:{_CAT_HOST}/visura_catastale"])
    if not token:
        return 0, b"", ""
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        return r.status_code, r.content, r.headers.get("content-type", "")
    except Exception as e:
        logger.warning("Catasto download error: %s", e)
        return 0, b"", ""


def _tipo_from_categoria(cat: str) -> str:
    c = (cat or "").upper().strip()
    letter = c[:1]
    code = c.split(":")[0].strip()
    if letter == "A":
        return "ufficio" if code in ("A/10",) else "abitativo"
    if letter == "C":
        if code in ("C/6", "C/7"):
            return "garage"
        return "commerciale"
    if letter == "D":
        return "commerciale"
    return "altro"


def _parse_quota(q: str) -> float:
    """'per 1/1' → 100.0 ; ' 1/2' → 50.0"""
    import re
    m = re.search(r"(\d+)\s*/\s*(\d+)", q or "")
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if den:
            return round(num / den * 100, 2)
    return 100.0


def _map_titolo(desc: str) -> str:
    d = (desc or "").lower()
    if "nuda" in d:
        return "nuda_proprieta"
    if "usufrutto" in d:
        return "usufrutto"
    if "propriet" in d:
        return "proprieta"
    return "proprieta"


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _parse_visura_json(jdata: dict, cf: str) -> list[dict]:
    """Estrae gli immobili strutturati dal JSON della visura catastale per soggetto."""
    root = jdata.get("VisuraSoggettoAttuale") or jdata.get("VisuraSoggetto") or jdata
    gruppi = _as_list(root.get("GruppoUnitaImmobiliari"))
    out: list[dict] = []
    cf_up = (cf or "").upper().strip()
    for gr in gruppi:
        if not isinstance(gr, dict):
            continue
        gattr = gr.get("@attributes") or {}
        comune = gattr.get("Descrizione") or ""
        tipo_catasto = (gattr.get("TipoCatasto") or "F").upper()
        # Titolo/quota dal gruppo intestazione (match sul CF del soggetto)
        titolo, quota = "proprieta", 100.0
        try:
            intest = ((gr.get("IntestazioneGruppo") or {}).get("MutazioneSoggettiva") or {})
            intest = (intest.get("Intestazione") or {})
            for it in _as_list(intest.get("Intestato")):
                ia = it.get("@attributes") or it
                if (ia.get("CF") or "").upper() == cf_up:
                    dr = (ia.get("DirittiReali") or {}).get("@attributes") or {}
                    titolo = _map_titolo(dr.get("Descrizione"))
                    quota = _parse_quota(dr.get("Quota"))
                    break
        except Exception:
            pass
        # Fabbricati
        for im in _as_list(gr.get("ImmobileFabbricatiS")):
            if not isinstance(im, dict):
                continue
            ident = ((im.get("DatiIdentificativi") or {}).get("IdentificativoDefinitivo") or {}).get("@attributes") or {}
            clas = (im.get("DatiClassamentoF") or {}).get("@attributes") or {}
            cons = ((im.get("DatiClassamentoF") or {}).get("Consistenza") or {}).get("@attributes") or {}
            sup = (im.get("SuperficieF") or {}).get("@attributes") or {}
            indirizzo = (im.get("DatiIndirizzo") or {}).get("IndirizzoImm") or ""
            cat_full = clas.get("Categoria") or ""
            cat_code = cat_full.split(":")[0].strip()
            rendita = 0.0
            try:
                rendita = float((clas.get("RenditaEuro") or "0").replace(".", "").replace(",", "."))
            except Exception:
                rendita = 0.0
            superficie = 0.0
            try:
                superficie = float(str(sup.get("Totale") or "0").replace(",", "."))
            except Exception:
                superficie = 0.0
            out.append({
                "tipo": _tipo_from_categoria(cat_code),
                "indirizzo": indirizzo.strip(),
                "comune": comune,
                "provincia": ident.get("Provincia"),
                "foglio": str(ident.get("Foglio") or ""),
                "particella": str(ident.get("ParticellaNum") or ""),
                "sub": str(ident.get("Subalterno") or ""),
                "categoria_catastale": cat_code,
                "rendita_catastale": rendita,
                "superficie_mq": superficie,
                "titolo": titolo,
                "percentuale_proprieta": quota,
                "note": f"Importato da Catasto — consistenza {cons.get('Valore','')} {cons.get('Unita','')}".strip(),
                "fonte": "openapi.it/catasto",
            })
        # Terreni
        for im in _as_list(gr.get("ImmobileTerreniS")):
            if not isinstance(im, dict):
                continue
            ident = ((im.get("DatiIdentificativi") or {}).get("IdentificativoDefinitivo") or {}).get("@attributes") or {}
            clas = (im.get("DatiClassamentoT") or {}).get("@attributes") or {}
            rd = 0.0
            try:
                rd = float((clas.get("RedditoDominicaleEuro") or clas.get("RenditaEuro") or "0").replace(".", "").replace(",", "."))
            except Exception:
                rd = 0.0
            out.append({
                "tipo": "terreno",
                "indirizzo": "",
                "comune": comune,
                "provincia": ident.get("Provincia"),
                "foglio": str(ident.get("Foglio") or ""),
                "particella": str(ident.get("ParticellaNum") or ""),
                "sub": str(ident.get("Subalterno") or ""),
                "categoria_catastale": clas.get("Qualita") or "TERRENO",
                "rendita_catastale": rd,
                "superficie_mq": 0.0,
                "titolo": titolo,
                "percentuale_proprieta": quota,
                "note": "Importato da Catasto (terreno)",
                "fonte": "openapi.it/catasto",
            })
    return out


async def _poll_richiesta(rid: str, ready=("evasa", "completato", "success", "done")) -> dict:
    import asyncio
    for _ in range(10):
        r = await _call_api([f"GET:{_CAT_HOST}/richiesta"], "GET", f"https://{_CAT_HOST}/richiesta/{rid}")
        d = (r or {}).get("data") or {}
        if (d.get("stato") or "").lower() in ready or d.get("risultato"):
            return d
        await asyncio.sleep(2.5)
    return {}


async def _poll_visura(vid: str) -> dict:
    import asyncio
    for _ in range(14):
        r = await _call_api([f"GET:{_CAT_HOST}/visura_catastale"], "GET", f"https://{_CAT_HOST}/visura_catastale/{vid}")
        d = (r or {}).get("data") or {}
        if (d.get("stato") or "").lower() == "evasa" and d.get("documento"):
            return d
        await asyncio.sleep(2.5)
    return {}


async def fetch_cadastre_detailed(cf_or_piva: str, want_pdf: bool = True) -> dict:
    """Flusso completo Catasto:
      1) ricerca_nazionale → id_soggetto
      2) visura_catastale (JSON analitica) → immobili strutturati
      3) visura_catastale (PDF ordinaria) → documento ufficiale (bytes)
    Ritorna {found, immobili, soggetto, pdf_bytes, pdf_filename, provider, message}.
    """
    key = (cf_or_piva or "").strip()
    if not has_credentials():
        return {"found": False, "mock": True, "immobili": _mock_cadastre(key),
                "soggetto": None, "pdf_bytes": None, "provider": "openapi.it (MOCK)",
                "message": "Credenziali OpenAPI.it non configurate — dati simulati."}

    # 1) ricerca_nazionale
    r = await _call_api([f"POST:{_CAT_HOST}/richiesta"], "POST",
                        f"https://{_CAT_HOST}/richiesta/ricerca_nazionale",
                        json={"cf_piva": key, "tipo_catasto": "TF"})
    data = (r or {}).get("data") or {}
    if (data.get("stato") or "").lower() != "evasa" and data.get("id"):
        data = await _poll_richiesta(data["id"]) or data
    ris = data.get("risultato") or {}
    soggetti = _as_list(ris.get("soggetti"))
    if not soggetti:
        return {"found": False, "immobili": [], "soggetto": None, "pdf_bytes": None,
                "provider": "openapi.it/catasto (LIVE)",
                "message": "Nessun immobile trovato al Catasto per questo soggetto."}
    # soggetto: match sul CF, altrimenti il primo
    sog = next((s for s in soggetti if (s.get("cf") or "").upper() == key.upper()), soggetti[0])
    id_soggetto = sog.get("id_soggetto")
    soggetto_info = {
        "denominazione": sog.get("denominazione") or " ".join(x for x in [sog.get("cognome"), sog.get("nome")] if x),
        "cf": sog.get("cf") or key,
        "sede": sog.get("sede") or sog.get("luogo_nascita"),
    }
    if not id_soggetto:
        return {"found": False, "immobili": [], "soggetto": soggetto_info, "pdf_bytes": None,
                "provider": "openapi.it/catasto (LIVE)", "message": "id_soggetto non disponibile."}

    # 2) visura JSON analitica → immobili
    immobili: list[dict] = []
    rv = await _call_api([f"POST:{_CAT_HOST}/visura_catastale"], "POST",
                         f"https://{_CAT_HOST}/visura_catastale",
                         json={"entita": "soggetto", "id_soggetto": id_soggetto,
                               "tipo_visura": "ordinaria", "tipo_formato": "json",
                               "tipo_dettaglio": "analitica", "richiedente": "CRM Assicura"})
    vd = (rv or {}).get("data") or {}
    vid_json = vd.get("id")
    if vid_json:
        vd = await _poll_visura(vid_json) or vd
        if vd.get("documento"):
            status, content, _ct = await _catasto_bytes(
                f"https://{_CAT_HOST}/visura_catastale/{vid_json}/documento")
            if status == 200 and content:
                try:
                    import json as _json
                    immobili = _parse_visura_json(_json.loads(content.decode("utf-8", "ignore")), key)
                except Exception as e:
                    logger.warning("Parse visura JSON error: %s", e)

    # 3) visura PDF ufficiale (opzionale)
    pdf_bytes, pdf_filename = None, None
    if want_pdf:
        rp = await _call_api([f"POST:{_CAT_HOST}/visura_catastale"], "POST",
                             f"https://{_CAT_HOST}/visura_catastale",
                             json={"entita": "soggetto", "id_soggetto": id_soggetto,
                                   "tipo_visura": "ordinaria", "richiedente": "CRM Assicura"})
        pd = (rp or {}).get("data") or {}
        vid_pdf = pd.get("id")
        if vid_pdf:
            pd = await _poll_visura(vid_pdf) or pd
            if pd.get("documento"):
                status, content, _ct = await _catasto_bytes(
                    f"https://{_CAT_HOST}/visura_catastale/{vid_pdf}/documento")
                if status == 200 and content:
                    pdf_bytes = content
                    pdf_filename = f"visura_catastale_{key}_{_iso_day()}.pdf"

    # Fallback immobili dal riepilogo se il parsing JSON non ha prodotto nulla
    if not immobili:
        immobili = _normalize_cadastre_nazionale(data, key)

    return {
        "found": bool(immobili) or bool(pdf_bytes),
        "immobili": immobili,
        "soggetto": soggetto_info,
        "pdf_bytes": pdf_bytes,
        "pdf_filename": pdf_filename,
        "provider": "openapi.it/catasto (LIVE)",
        "message": f"{len(immobili)} immobili trovati." if immobili else "Visura generata senza dettaglio strutturato.",
    }


def _iso_day() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().isoformat()


# ===================================================================
# SERVIZIO 8 · VISENGINE — catalogo documenti + richieste
# ===================================================================
_VIS_HOST = "visengine2.altravia.com"

# Lista FISSA curata dei documenti (hash reali verificati sull'account).
VISENGINE_CATALOG = [
    # Camerali
    {"hash": "526b6c8415936433f5a217d2bf7d2a72", "nome": "Visura Centrale Rischi persona fisica", "categoria": "Camerali"},
    {"hash": "8e238ef3e28fd887c014879179ece1b0", "nome": "Visura Centrale Rischi Persona Giuridica", "categoria": "Camerali"},
    {"hash": "b56c410cdfd569bfc0160821d4b3b26b", "nome": "Visura Experian", "categoria": "Camerali"},
    # Patronato / INPS
    {"hash": "cf711d0121f5a2f95a8694d960124bd1", "nome": "Estratto Contributivo", "categoria": "Patronato"},
    {"hash": "6aa0789f5ba34684b2bc5ccf364f8929", "nome": "ISEE", "categoria": "Patronato"},
    {"hash": "57c24ad72bd57ba4d796622504086e02", "nome": "ISEE Corrente", "categoria": "Patronato"},
    {"hash": "38934ffe45179c4d5b88e2a6b849799a", "nome": "730 Singolo", "categoria": "Patronato"},
    {"hash": "38a18478a1b223e0da81a6e0fcc730df", "nome": "730 Congiunto", "categoria": "Patronato"},
    {"hash": "5fec14002548c9ae115758500c8981ee", "nome": "Pensione di vecchiaia", "categoria": "Patronato"},
    {"hash": "079e2c420c93f633ac4c8954f27c1299", "nome": "Pensione Superstiti", "categoria": "Patronato"},
    {"hash": "1f9dfd7e9a73918756470d9618fb317d", "nome": "Calcolo e Previsione Pensione", "categoria": "Patronato"},
    {"hash": "df66c5f10a4ce1162c56f762c562d79c", "nome": "CUD Pensionati", "categoria": "Patronato"},
    {"hash": "bc74d769203eb5c33f2a40e91c076ec3", "nome": "OBIS-M", "categoria": "Patronato"},
    {"hash": "89031e957e9cebc4f6e64948f2353727", "nome": "Visura Proprietari PRA", "categoria": "Patronato"},
    {"hash": "4d085e4448d523d18aa7f76f53662ff8", "nome": "IMU Calcolo", "categoria": "Patronato"},
    {"hash": "224fcc49770edad354cdd9c480a7e50e", "nome": "Domanda Assegno Unico", "categoria": "Patronato"},
]


def visengine_catalog() -> list[dict]:
    return VISENGINE_CATALOG


async def visengine_get_schema(hash_visura: str) -> Optional[dict]:
    res = await _call_api([f"GET:{_VIS_HOST}/visure"], "GET", f"https://{_VIS_HOST}/visure/{hash_visura}")
    if not res:
        return None
    return res.get("data") or res


def _prefill_value(label: str, tipo: str, ana: dict) -> str:
    """Suggerisce un valore per un campo Visengine dai dati dell'anagrafica."""
    lab = (label or "").lower()
    is_pg = (ana.get("tipo") == "persona_giuridica") or bool(ana.get("ragione_sociale"))
    nome = (ana.get("nome") or "").strip()
    cognome = (ana.get("cognome") or "").strip()
    full = ana.get("ragione_sociale") or f"{cognome} {nome}".strip()
    if tipo == "email" or "email" in lab:
        return ana.get("email") or ""
    if "cellulare" in lab or "telefono" in lab:
        return ana.get("cellulare") or ana.get("telefono") or ""
    if "partita iva" in lab or ("piva" in lab):
        return ana.get("partita_iva") or ""
    if tipo in ("codice_fiscale", "codice_fiscale_persona_fisica") or "codice fiscale" in lab:
        if is_pg:
            return ana.get("codice_fiscale") or ana.get("partita_iva") or ""
        return ana.get("codice_fiscale") or ""
    if "denominazione" in lab and "cognome" not in lab:
        return full
    if "cognome" in lab:
        return cognome
    if "nome" in lab:
        # "Nome e Cognome o Denominazione" → nome completo
        if "cognome" in lab or "denominazione" in lab:
            return full
        return nome
    return ""


def visengine_schema_prefilled(schema: dict, ana: dict) -> dict:
    """Trasforma json_struttura in una lista campi con valori suggeriti."""
    js = (schema or {}).get("json_struttura") or {}
    campi = js.get("campi") or {}
    fields = []
    for key in sorted(campi.keys(), key=lambda k: int((campi[k].get("ordine") or k.strip("$") or 0)) if str(campi[k].get("ordine") or k.strip("$") or "0").isdigit() else 999):
        c = campi[key]
        tipo = c.get("tipo") or "testo"
        is_file = tipo == "file"
        fields.append({
            "key": key,
            "nome": c.get("nome") or key,
            "tipo": tipo,
            "istruzioni": c.get("istruzioni") or "",
            "required": c.get("null") is False,
            "is_file": is_file,
            "value": "" if is_file else _prefill_value(c.get("nome"), tipo, ana),
        })
    return {
        "hash_visura": schema.get("hash_visura"),
        "nome_visura": schema.get("nome_visura"),
        "nome_categoria": schema.get("nome_categoria"),
        "prezzo_visura": schema.get("prezzo_visura"),
        "validazione": js.get("validazione"),
        "opzioni": schema.get("opzioni"),
        "sincrona": schema.get("sincrona"),
        "campi": fields,
    }


async def visengine_create_request(hash_visura: str, json_visura: dict, opzioni: Optional[list] = None) -> dict:
    """POST /richiesta → crea la pratica Visengine. Ritorna {ok, id, stato, error}."""
    body = {"hash_visura": hash_visura, "json_visura": json_visura}
    if opzioni:
        body["opzioni"] = opzioni
    token = await _get_token([f"POST:{_VIS_HOST}/richiesta"])
    if not token:
        return {"ok": False, "error": "Token non disponibile"}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(f"https://{_VIS_HOST}/richiesta", json=body,
                                  headers={"Authorization": f"Bearer {token}",
                                           "Content-Type": "application/json"})
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text}
        if r.status_code >= 400 or not j.get("success", True):
            return {"ok": False, "error": j.get("message") or f"HTTP {r.status_code}", "raw": j}
        d = j.get("data") or {}
        rid = d.get("id") or d.get("id_richiesta") or d.get("_id") or j.get("id")
        return {"ok": True, "id": rid, "stato": d.get("stato") or "in_lavorazione", "raw": d}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def visengine_get_request(rid: str) -> dict:
    res = await _call_api([f"GET:{_VIS_HOST}/richiesta"], "GET", f"https://{_VIS_HOST}/richiesta/{rid}")
    return (res or {}).get("data") or {}


async def visengine_download(rid: str) -> tuple[int, bytes, str]:
    token = await _get_token([f"GET:{_VIS_HOST}/documento"])
    if not token:
        return 0, b"", ""
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(f"https://{_VIS_HOST}/documento/{rid}",
                                 headers={"Authorization": f"Bearer {token}"})
        return r.status_code, r.content, r.headers.get("content-type", "")
    except Exception as e:
        logger.warning("Visengine download error: %s", e)
        return 0, b"", ""


def visengine_is_ready(stato: str) -> bool:
    return (stato or "").lower() in ("evasa", "evaso", "completato", "completata", "success", "done", "pronto", "pronta")


# ===================================================================
# SERVIZIO 9 · VISURE CAMERALI (visurecamerali.openapi.it) — ricerca
# gratuita + generazione documenti ufficiali (PDF) a pagamento
# ===================================================================
_VC_HOST = "visurecamerali.openapi.it"
_CO_HOST = "company.openapi.com"

VC_DOC_META = {
    "ordinaria-societa-capitale": {"label": "Visura Ordinaria (Società di Capitali)", "prezzo": 4.90},
    "storica-societa-capitale": {"label": "Visura Storica (Società di Capitali)", "prezzo": 5.90},
    "ordinaria-societa-persone": {"label": "Visura Ordinaria (Società di Persone)", "prezzo": 3.40},
    "storica-societa-persone": {"label": "Visura Storica (Società di Persone)", "prezzo": 4.40},
    "ordinaria-impresa-individuale": {"label": "Visura Ordinaria (Impresa Individuale)", "prezzo": 2.90},
    "storica-impresa-individuale": {"label": "Visura Storica (Impresa Individuale)", "prezzo": 3.90},
    "bilancio-ottico": {"label": "Bilancio Ottico", "prezzo": 4.50},
    "certificato-iscrizione": {"label": "Certificato di Iscrizione", "prezzo": 13.70},
    "certificato-iscrizione-vigenza": {"label": "Certificato con Vigenza", "prezzo": 13.70},
    "soci-attivi": {"label": "Elenco Soci Attivi", "prezzo": 2.30},
}


async def vc_search(cf_piva: str) -> Optional[dict]:
    """Ricerca commerciale GRATUITA (GET /impresa/{cf_piva})."""
    key = (cf_piva or "").strip()
    if not key or not has_credentials():
        return None
    r = await _call_api([f"GET:{_VC_HOST}/impresa"], "GET", f"https://{_VC_HOST}/impresa/{key}")
    if not r:
        return None
    data = r.get("data")
    if isinstance(data, list):
        item = data[0] if data else None
    elif isinstance(data, dict):
        item = data
    else:
        item = None
    if not item:
        return None
    docs = []
    for scope in item.get("chiamate_disponibili") or []:
        dt = scope.split("/")[-1]
        meta = VC_DOC_META.get(dt)
        if meta:
            docs.append({"doc_type": dt, **meta})
    return {
        "id": item.get("id"),
        "cf_piva": key,
        "denominazione": item.get("denominazione"),
        "comune": item.get("comune"),
        "natura_giuridica": item.get("codice_natura_giuridica"),
        "documenti_disponibili": docs,
        "provider": "visurecamerali.openapi.it (LIVE)",
    }


async def vc_generate(doc_type: str, cf_piva_id: str, anno: Optional[str] = None) -> dict:
    """POST /{doc_type} → genera la richiesta del documento (a pagamento)."""
    body = {"cf_piva_id": cf_piva_id}
    if anno and doc_type == "bilancio-ottico":
        body["anno_chiusura"] = str(anno)
    token = await _get_token([f"POST:{_VC_HOST}/{doc_type}"])
    if not token:
        return {"ok": False, "error": "Token non disponibile"}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(f"https://{_VC_HOST}/{doc_type}", json=body,
                                  headers={"Authorization": f"Bearer {token}",
                                           "Content-Type": "application/json"})
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text}
        if r.status_code >= 400 or not j.get("success", True):
            return {"ok": False, "error": j.get("message") or f"HTTP {r.status_code}"}
        d = j.get("data") or {}
        return {"ok": True, "id": d.get("id"), "stato": d.get("stato_richiesta") or "In ricerca"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def vc_status(doc_type: str, rid: str) -> dict:
    r = await _call_api([f"GET:{_VC_HOST}/{doc_type}"], "GET", f"https://{_VC_HOST}/{doc_type}/{rid}")
    return (r or {}).get("data") or {}


async def vc_find_existing(doc_type: str, cf_piva_id: str) -> Optional[str]:
    """GET GRATUITA /{doc_type}: cerca una richiesta GIÀ pronta per la stessa azienda,
    così la riscarichiamo senza pagare di nuovo. Ritorna l'id o None."""
    r = await _call_api([f"GET:{_VC_HOST}/{doc_type}"], "GET", f"https://{_VC_HOST}/{doc_type}")
    data = (r or {}).get("data")
    if not isinstance(data, list):
        return None
    key = (cf_piva_id or "").strip().lower()
    candidates = []
    for it in data:
        cf = str(it.get("cf_piva_id") or "").strip().lower()
        if cf == key and vc_is_ready(it.get("stato_richiesta")):
            candidates.append(it)
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.get("timestamp_creation") or 0, reverse=True)
    return candidates[0].get("id")


async def vc_download(doc_type: str, rid: str) -> tuple[int, bytes, str, str]:
    """Scarica il documento camerale. L'endpoint /allegati può restituire il PDF
    diretto oppure un JSON {data:{nome, file(base64 ZIP)}}: in tal caso decodifica
    il base64 ed estrae il PDF dallo ZIP. Ritorna (status, bytes, content_type, filename)."""
    token = await _get_token([f"GET:{_VC_HOST}/{doc_type}"])
    if not token:
        return 0, b"", "", ""
    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            r = await client.get(f"https://{_VC_HOST}/{doc_type}/{rid}/allegati",
                                 headers={"Authorization": f"Bearer {token}"})
        content = r.content
        ctype = r.headers.get("content-type", "")
        fname = f"{doc_type}_{rid}.pdf"
        if r.status_code != 200 or not content:
            return r.status_code, b"", ctype, fname
        # PDF diretto
        if content[:4] == b"%PDF":
            return 200, content, "application/pdf", fname
        # JSON con base64
        if content[:1] in (b"{", b"[") or "json" in ctype.lower():
            import json as _json, base64 as _b64
            try:
                j = _json.loads(content.decode("utf-8", "ignore"))
                d = j.get("data") or {}
                nome = d.get("nome") or fname
                b64 = d.get("file")
                if not b64:
                    return 200, content, "application/json", fname
                raw = _b64.b64decode(b64)
                # ZIP → estrai primo PDF
                if raw[:2] == b"PK" or str(nome).lower().endswith(".zip"):
                    import io as _io, zipfile as _zip
                    with _zip.ZipFile(_io.BytesIO(raw)) as zf:
                        pdfs = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
                        if pdfs:
                            return 200, zf.read(pdfs[0]), "application/pdf", pdfs[0].split("/")[-1]
                        # nessun pdf: ritorna lo zip
                    return 200, raw, "application/zip", str(nome)
                # non zip: bytes decodificati
                ct = "application/pdf" if raw[:4] == b"%PDF" else "application/octet-stream"
                return 200, raw, ct, str(nome)
            except Exception as e:
                logger.warning("VC download parse error: %s", e)
                return 200, content, "application/json", fname
        return 200, content, ctype or "application/octet-stream", fname
    except Exception as e:
        logger.warning("Visengine/VC download error: %s", e)
        return 0, b"", "", ""


def vc_is_ready(stato: str) -> bool:
    return (stato or "").strip().lower() in ("visura evasa", "dati disponbili", "dati disponibili", "evasa")


# ===================================================================
# SERVIZIO 10 · COMPANY.OPENAPI.COM — dati camerali + BILANCIO strutturato
# ===================================================================
def _co_num(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _normalize_company_co(d: dict, full: bool) -> dict:
    bs = d.get("balanceSheets") or {}
    bilanci = []
    for b in (bs.get("all") or []):
        bilanci.append({
            "anno": b.get("year"),
            "fatturato": _co_num(b.get("turnover")),
            "patrimonio_netto": _co_num(b.get("netWorth")),
            "dipendenti": b.get("employees"),
            "capitale_sociale": _co_num(b.get("shareCapital")),
            "costo_personale": _co_num(b.get("totalStaffCost")),
            "totale_attivo": _co_num(b.get("totalAssets")),
            "stipendio_medio": _co_num(b.get("avgGrossSalary")),
        })
    bilanci.sort(key=lambda x: x.get("anno") or 0, reverse=True)
    ateco_raw = d.get("atecoClassification") or {}
    if isinstance(ateco_raw, list):
        ateco_raw = ateco_raw[0] if ateco_raw else {}
    ateco_obj = ateco_raw.get("ateco2022") or ateco_raw.get("ateco2007") or ateco_raw.get("ateco") or {}
    if not isinstance(ateco_obj, dict):
        ateco_obj = {}
    lf = d.get("detailedLegalForm") or {}
    addr = d.get("address")
    if isinstance(addr, dict):
        ro = addr.get("registeredOffice") or addr
        prov = ro.get("province")
        if isinstance(prov, dict):
            prov = prov.get("code") or prov.get("description")
        indirizzo = ro.get("streetName") or ro.get("street")
        if indirizzo and ro.get("town"):
            indirizzo = f"{indirizzo}, {ro.get('zipCode') or ''} {ro.get('town')} ({prov or ''})".strip()
    else:
        indirizzo = addr if isinstance(addr, str) else None
    out = {
        "provider": "company.openapi.com (LIVE)",
        "ragione_sociale": d.get("companyName"),
        "piva": d.get("vatCode"),
        "cf": d.get("taxCode"),
        "indirizzo": indirizzo,
        "stato_attivita": d.get("activityStatus"),
        "rea": d.get("reaCode"),
        "cciaa": d.get("cciaa"),
        "pec": d.get("pec"),
        "forma_giuridica": lf.get("description") if isinstance(lf, dict) else lf,
        "ateco": ateco_obj.get("code"),
        "ateco_descrizione": ateco_obj.get("description"),
        "data_inizio": d.get("startDate"),
        "bilanci": bilanci,
    }
    if full:
        out["indici"] = {
            "redditivita": d.get("profitability"),
            "liquidita": d.get("liquidityRatios"),
            "leva": d.get("leverageRatios"),
            "kpi_bilancio": d.get("financialStatementKpi"),
            "struttura": d.get("structureRatios"),
            "indebitamento": d.get("indebtedness"),
        }
        out["dipendenti_statistiche"] = d.get("employeesStatistic")
        # amministratori
        managers = []
        for m in (d.get("managers") or [])[:15]:
            roles = ", ".join(r.get("role", {}).get("description", "") for r in (m.get("roles") or []) if isinstance(r, dict))
            managers.append({
                "nome": (m.get("name") or m.get("companyName") or "").strip() + (f" {m.get('surname')}" if m.get("surname") else ""),
                "ruoli": roles,
                "legale_rappresentante": bool(m.get("isLegalRepresentative")),
            })
        out["amministratori"] = managers
        # soci
        soci = []
        for s in (d.get("shareholders") or [])[:15]:
            info = (s.get("shareholdersInformation") or [{}])[0]
            soci.append({
                "nome": info.get("companyName") or (f"{info.get('name','')} {info.get('surname','')}".strip()) or info.get("taxCode"),
                "quota": s.get("percentShare"),
                "tipo": (s.get("shareType") or {}).get("description"),
            })
        out["soci"] = soci
    return out


async def company_dati(cf_piva: str, full: bool = False) -> Optional[dict]:
    """Dati camerali + bilancio strutturato da company.openapi.com (a pagamento)."""
    key = (cf_piva or "").strip()
    if not key or not has_credentials():
        return None
    level = "IT-full" if full else "IT-advanced"
    r = await _call_api([f"GET:{_CO_HOST}/{level}"], "GET", f"https://{_CO_HOST}/{level}/{key}")
    if not r:
        return None
    d = r.get("data")
    if isinstance(d, list):
        d = d[0] if d else {}
    if not isinstance(d, dict) or not d:
        return None
    return _normalize_company_co(d, full)

