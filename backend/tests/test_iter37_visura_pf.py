"""iter37 — Visura ora supporta anche persone fisiche (CF fallback).

Copre:
  1. POST /api/openapi-it/visura/{aid} su anagrafica PF (solo CF) → 200
     con provider='openapi.it/visure (MOCK)' e piva=CF.
  2. Nessuna regressione su /company, /status, /automotive-by-targa, /risk,
     /company/{aid}, /openapi-it/company?piva=... .
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL non impostato")

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"

AID_PF_MELLO = "e15e701a-4b0f-490d-9848-23c7e9147500"  # persona_fisica CF 01075160141
PIVA_TEST = "12485671007"


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login fallito: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def s(token) -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return sess


# --------- /api/openapi-it/status ---------
def test_status(s):
    r = s.get(f"{BASE_URL}/api/openapi-it/status", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("mode") in ("mock", "live")
    assert isinstance(d.get("has_credentials"), bool)


# --------- /api/openapi-it/company?piva=... (autocomplete) ---------
def test_company_lookup_by_piva(s):
    r = s.get(f"{BASE_URL}/api/openapi-it/company?piva={PIVA_TEST}", timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    # In MOCK deve tornare comunque una ragione_sociale/pv
    assert (d.get("piva") or "").strip() != "" or (d.get("ragione_sociale") or "").strip() != ""


# --------- MELLO (persona fisica) esiste con CF ? ---------
def test_mello_exists_pf_with_cf(s):
    r = s.get(f"{BASE_URL}/api/anagrafiche/{AID_PF_MELLO}", timeout=20)
    assert r.status_code == 200, r.text
    ana = r.json()
    assert ana.get("tipo") == "persona_fisica" or ana.get("codice_fiscale"), (
        f"MELLO non è PF o non ha CF: {ana.get('tipo')} cf={ana.get('codice_fiscale')}"
    )
    assert (ana.get("codice_fiscale") or "").upper() == "01075160141"


# --------- ⭐ FEATURE PRINCIPALE: Visura su PF ---------
def test_visura_on_pf_uses_cf(s):
    r = s.post(f"{BASE_URL}/api/openapi-it/visura/{AID_PF_MELLO}", timeout=60)
    assert r.status_code == 200, f"Visura PF fallita: {r.status_code} {r.text}"
    d = r.json()
    prov = (d.get("provider") or "").lower()
    assert "visure" in prov or "visengine" in prov, f"provider inatteso: {prov}"
    # piva field deve contenere il CF usato come fallback
    piva_field = str(d.get("piva") or d.get("cf") or "").upper()
    assert "01075160141" in piva_field, f"piva/cf non riflette il CF PF: {d}"
    # In sandbox il MOCK non ha download_url → allegato_saved absent / False è OK
    assert d.get("allegato_saved") in (True, False, None)


# --------- Regression: /automotive-by-targa ---------
def test_automotive_by_targa_cached_or_mock(s):
    r = s.get(f"{BASE_URL}/api/openapi-it/automotive-by-targa/AB123CD", timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "veicolo" in d
    assert d.get("fonte") in ("cache", "openapi_live", "openapi_mock")


# --------- Regression: /risk/{aid} su PF ---------
def test_risk_on_pf(s):
    r = s.post(f"{BASE_URL}/api/openapi-it/risk/{AID_PF_MELLO}", timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d, dict) and len(d) > 0


# --------- Regression: /company/{aid} su PF (usa CF fallback) ---------
def test_company_on_pf_uses_cf(s):
    r = s.post(f"{BASE_URL}/api/openapi-it/company/{AID_PF_MELLO}", timeout=45)
    assert r.status_code == 200, r.text
    d = r.json()
    # provider deve essere presente
    assert (d.get("provider") or "") != ""
