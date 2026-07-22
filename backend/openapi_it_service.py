"""OpenAPI.it integration service — MOCK MODE (attivabile a chiavi disponibili).

Se `OPENAPI_IT_TOKEN` è vuota o inizia con `oapi_test_mock` → MOCK con dati realistici.
Altrimenti si effettuano chiamate reali all'endpoint OpenAPI.it (documentazione a
https://oa.wiki e https://developers.openapi.it).

Servizi:
1. Company & Chamber of Commerce (P.IVA/CF → dati camerali)
2. Italian Cadastre (CF/P.IVA → immobili)
3. Automotive (CF/P.IVA → veicoli intestati)
4. Visure Camerali (visura ufficiale)
"""
from __future__ import annotations
import logging
import os
import random
from typing import Optional

logger = logging.getLogger(__name__)


def _token() -> str:
    return os.environ.get("OPENAPI_IT_TOKEN", "").strip()


def is_mock_mode() -> bool:
    t = _token()
    return not t or t.startswith("oapi_test_mock")


# =============== MOCK DATA GENERATORS ===============
async def fetch_company(piva_or_cf: str) -> dict:
    """Simula lookup camera di commercio da P.IVA o CF."""
    if is_mock_mode():
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
    raise NotImplementedError("OpenAPI.it live mode non ancora implementato — configura OPENAPI_IT_TOKEN")


async def fetch_cadastre(cf_or_piva: str) -> list[dict]:
    """Simula lookup catasto immobili."""
    if is_mock_mode():
        random.seed(hash(cf_or_piva + "_cad") % (2**31))
        n = random.randint(0, 4)
        immobili = []
        for i in range(n):
            immobili.append({
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
        return immobili
    raise NotImplementedError("OpenAPI.it live mode non ancora implementato")


async def fetch_vehicles(cf_or_piva: str) -> list[dict]:
    """Simula lookup PRA veicoli intestati."""
    if is_mock_mode():
        random.seed(hash(cf_or_piva + "_veh") % (2**31))
        n = random.randint(0, 3)
        veh = []
        for i in range(n):
            marca = random.choice(["FIAT", "VOLKSWAGEN", "BMW", "AUDI", "RENAULT", "PEUGEOT"])
            model = random.choice(["500", "PANDA", "GOLF", "SERIE 3", "A4", "CLIO"])
            veh.append({
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
        return veh
    raise NotImplementedError("OpenAPI.it live mode non ancora implementato")


async def fetch_visura(piva: str) -> dict:
    """Simula download visura camerale ordinaria."""
    if is_mock_mode():
        company = await fetch_company(piva)
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
            "download_url": None,  # nel real mode qui c'è l'URL PDF firmato
            "rating_finanziario": random.choice(["A", "BBB", "BB", "B"]),
            "punteggio_rischio_credito": random.randint(30, 90),
        }
    raise NotImplementedError("OpenAPI.it live mode non ancora implementato")
