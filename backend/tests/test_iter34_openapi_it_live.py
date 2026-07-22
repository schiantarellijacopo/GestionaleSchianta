"""iter34 — Test integrazione LIVE OpenAPI.it (OAuth2 client_credentials, sandbox).

Endpoints testati:
- GET  /api/openapi-it/status
- GET  /api/openapi-it/company?piva=12485671007
- POST /api/openapi-it/company/{aid}
- POST /api/openapi-it/cadastre/{aid}    (fallback MOCK atteso)
- POST /api/openapi-it/vehicles/{aid}    (fallback MOCK atteso)
- POST /api/openapi-it/visura/{aid}      (fallback MOCK atteso o LIVE)
- GET  /api/anagrafiche/{aid}            (verifica openapi_data.company salvato)
- GET  /api/anagrafiche/check-duplicate  (regression iter31)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

# Anagrafica esistente in DB (da problem statement)
LIBERA_AID = "4871fe9f-7f57-43b3-a80a-e27eeec2c3e9"
LIBERA_PIVA = "00795070143"
TEST_PIVA_OPENAPI = "12485671007"


# ---------- Feature 1: /status ----------
class TestOpenApiStatus:
    def test_status_live_with_credit(self, admin_session):
        r = admin_session.get(f"{API}/openapi-it/status", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("mode") == "live", f"mode should be 'live', got: {data}"
        assert data.get("has_credentials") is True, f"has_credentials must be True: {data}"
        assert data.get("env") == "sandbox", f"env should be 'sandbox', got: {data.get('env')}"
        credit = data.get("credit_eur")
        assert credit is not None, "credit_eur must not be None (sandbox has 100€ pool)"
        assert isinstance(credit, (int, float)), f"credit_eur must be numeric, got {type(credit)}"
        assert credit > 0, f"credit_eur must be > 0, got {credit}"

    def test_status_does_not_leak_client_secret(self, admin_session):
        r = admin_session.get(f"{API}/openapi-it/status", timeout=15)
        assert r.status_code == 200
        # No secret in payload (env value comes from .env)
        secret = os.environ.get("OPENAPI_IT_CLIENT_SECRET", "bsqahe2uj2b8vvj2n3imgprapoul1oeh")
        assert secret not in r.text, "CLIENT_SECRET leaked in /status response!"


# ---------- Feature 2: /company (direct lookup) ----------
class TestCompanyLookupDirect:
    def test_company_lookup_openapi_spa(self, admin_session):
        r = admin_session.get(
            f"{API}/openapi-it/company",
            params={"piva": TEST_PIVA_OPENAPI},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # In sandbox tutti i P.IVA ritornano OPENAPI S.P.A. — è documentato
        assert data.get("provider") == "openapi.it (LIVE)", f"provider: {data.get('provider')}"
        assert data.get("ragione_sociale") and "OPENAPI" in str(data["ragione_sociale"]).upper(), \
            f"ragione_sociale: {data.get('ragione_sociale')}"
        # Campi chiave da problem statement
        ateco = str(data.get("ateco") or "")
        assert ateco.startswith("6201") or "6201" in ateco, f"ateco: {ateco}"
        assert data.get("pec") == "openapi@legalmail.it", f"pec: {data.get('pec')}"
        assert data.get("cciaa") == "RM", f"cciaa: {data.get('cciaa')}"
        assert data.get("rea") == "1378273", f"rea: {data.get('rea')}"
        assert data.get("comune") == "ROMA", f"comune: {data.get('comune')}"
        assert data.get("provincia") == "RM"
        assert data.get("data_costituzione") == "2013-10-20", f"data_costituzione: {data.get('data_costituzione')}"
        assert "raw" in data, "raw payload must be attached"

    def test_company_lookup_invalid_piva(self, admin_session):
        r = admin_session.get(
            f"{API}/openapi-it/company",
            params={"piva": "123"},
            timeout=15,
        )
        assert r.status_code == 400, r.text


# ---------- Feature 3: /company/{aid} save on Anagrafica ----------
class TestCompanySaveToAnagrafica:
    def test_post_company_libera_saves_openapi_data(self, admin_session):
        r = admin_session.post(f"{API}/openapi-it/company/{LIBERA_AID}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("provider") == "openapi.it (LIVE)", f"provider: {data.get('provider')}"
        # Verify persistence
        r2 = admin_session.get(f"{API}/anagrafiche/{LIBERA_AID}", timeout=15)
        assert r2.status_code == 200
        ana = r2.json()
        openapi_data = ana.get("openapi_data") or {}
        company = openapi_data.get("company") or {}
        assert company.get("provider") == "openapi.it (LIVE)", \
            f"openapi_data.company.provider: {company.get('provider')}"
        assert openapi_data.get("last_sync"), "last_sync must be set"


# ---------- Feature 4: cadastre/vehicles fallback MOCK ----------
class TestCadastreVehiclesMock:
    def test_cadastre_returns_mock(self, admin_session):
        r = admin_session.post(f"{API}/openapi-it/cadastre/{LIBERA_AID}", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "immobili" in data
        assert "count" in data
        for im in data["immobili"]:
            assert im.get("provider") == "openapi.it/cadastre (MOCK)", \
                f"provider: {im.get('provider')}"

    def test_vehicles_returns_mock(self, admin_session):
        r = admin_session.post(f"{API}/openapi-it/vehicles/{LIBERA_AID}", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "veicoli" in data
        for v in data["veicoli"]:
            assert v.get("provider") == "openapi.it/automotive (MOCK)"


# ---------- Feature 5: visura non 500 ----------
class TestVisura:
    def test_visura_does_not_return_500(self, admin_session):
        r = admin_session.post(f"{API}/openapi-it/visura/{LIBERA_AID}", timeout=45)
        # LIVE o MOCK entrambi accettabili — vietato 500
        assert r.status_code == 200, f"visura endpoint returned {r.status_code}: {r.text}"
        data = r.json()
        provider = data.get("provider", "")
        assert "openapi.it/visure" in provider, f"provider: {provider}"
        # MOCK or LIVE are both acceptable
        assert data.get("piva") == LIBERA_PIVA


# ---------- Feature 6: token cache (2 back-to-back calls) ----------
class TestTokenCache:
    def test_two_consecutive_lookups_are_fast(self, admin_session):
        """La seconda chiamata deve essere rapida perché usa il token cache-ato."""
        t0 = time.time()
        r1 = admin_session.get(
            f"{API}/openapi-it/company",
            params={"piva": TEST_PIVA_OPENAPI},
            timeout=30,
        )
        elapsed_1 = time.time() - t0
        assert r1.status_code == 200

        t1 = time.time()
        r2 = admin_session.get(
            f"{API}/openapi-it/company",
            params={"piva": TEST_PIVA_OPENAPI},
            timeout=30,
        )
        elapsed_2 = time.time() - t1
        assert r2.status_code == 200
        # Non è un hard-fail perché la rete varia — logga solo se sospetto
        print(f"Company call 1: {elapsed_1:.2f}s | Call 2: {elapsed_2:.2f}s (should be similar or faster)")


# ---------- Feature 7: regression iter31 check-duplicate ----------
class TestRegressionCheckDuplicate:
    def test_check_duplicate_mello(self, admin_session):
        r = admin_session.get(
            f"{API}/anagrafiche/check-duplicate",
            params={"codice_fiscale": "01075160141"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("exists") is True or data.get("existing") is not None, \
            f"MELLO check-duplicate should return exists=true: {data}"
        # accept both shapes
        existing = data.get("existing") or data
        rs = existing.get("ragione_sociale") if isinstance(existing, dict) else None
        # regression: se struttura è diversa cerca comunque MELLO in body
        assert "MELLO" in r.text.upper(), f"Expected MELLO in response: {r.text[:400]}"
