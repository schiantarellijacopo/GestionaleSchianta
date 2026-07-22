"""iter35 — Test integrazione OpenAPI.it Automotive by TARGA + Risk + associa proprietario.

Endpoints testati:
- GET  /api/openapi-it/automotive-by-targa/{targa}  (cache + openapi_mock/live)
- POST /api/openapi-it/risk/{aid}                    (rating/protesti/pregiudizievoli)
- POST /api/openapi-it/veicoli/{vid}/associa-proprietario/{aid}
- GET  /api/openapi-it/status                        (regression)
- GET  /api/openapi-it/company?piva=...              (regression diretta)
- POST /api/openapi-it/company/{aid}                 (regression persistenza)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

# Anagrafiche dal problem statement
LIBERA_AID = "4871fe9f-7f57-43b3-a80a-e27eeec2c3e9"  # AZ. AGRICOLA DI LIBERA DUILIO (PG)
MELLO_AID = "e15e701a-4b0f-490d-9848-23c7e9147500"   # MELLO (PF)
TEST_TARGA = "AB123CD"
TEST_PIVA_OPENAPI = "12485671007"


# ---------- Feature 1: Automotive by TARGA ----------
class TestAutomotiveByTarga:
    def test_targa_first_call_persists_and_returns_source(self, admin_session):
        # force_refresh to ensure it hits svc (bypasses cache from a previous run)
        r = admin_session.get(
            f"{API}/openapi-it/automotive-by-targa/{TEST_TARGA}",
            params={"force_refresh": "true"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "veicolo" in data
        assert "fonte" in data
        assert data["fonte"] in ("openapi_live", "openapi_mock"), f"fonte: {data['fonte']}"
        v = data["veicolo"]
        # Campi obbligatori dal problem statement
        assert v.get("targa") == TEST_TARGA.upper()
        assert v.get("marca") is not None
        assert v.get("modello") is not None
        # These may be null in some payloads but keys must exist in normalized doc
        for key in ("potenza_kw", "telaio", "alimentazione", "anno_immatricolazione",
                    "scadenza_revisione", "cilindrata", "euro", "categoria"):
            assert key in v, f"campo mancante: {key}"
        assert "id" in v, "veicolo deve avere un id (persistenza in db.veicoli)"

    def test_targa_second_call_returns_cache(self, admin_session):
        # First ensure the record exists
        admin_session.get(
            f"{API}/openapi-it/automotive-by-targa/{TEST_TARGA}",
            params={"force_refresh": "true"},
            timeout=30,
        )
        # Second call without force_refresh must return cache
        r = admin_session.get(
            f"{API}/openapi-it/automotive-by-targa/{TEST_TARGA}",
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("fonte") == "cache", f"expected cache, got {r.json().get('fonte')}"

    def test_targa_invalid_returns_400(self, admin_session):
        r = admin_session.get(f"{API}/openapi-it/automotive-by-targa/AB1", timeout=15)
        assert r.status_code == 400


# ---------- Feature 2: Risk report ----------
class TestRisk:
    def test_risk_returns_full_report(self, admin_session):
        r = admin_session.post(f"{API}/openapi-it/risk/{MELLO_AID}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Provider is either LIVE or MOCK
        provider = data.get("provider", "")
        assert "openapi.it/risk" in provider, f"provider: {provider}"
        for key in ("soggetto", "rating", "score_credito", "livello_rischio",
                    "protesti", "pregiudizievoli", "procedure_concorsuali",
                    "eventi_negativi_count", "data_report"):
            assert key in data, f"campo mancante: {key}"
        assert isinstance(data["protesti"], list)
        assert isinstance(data["pregiudizievoli"], list)
        assert isinstance(data["procedure_concorsuali"], list)

    def test_risk_persisted_on_anagrafica(self, admin_session):
        r = admin_session.post(f"{API}/openapi-it/risk/{MELLO_AID}", timeout=30)
        assert r.status_code == 200
        # Verifica persistenza in openapi_data.risk
        r2 = admin_session.get(f"{API}/anagrafiche/{MELLO_AID}", timeout=15)
        assert r2.status_code == 200
        ana = r2.json()
        risk = (ana.get("openapi_data") or {}).get("risk") or {}
        assert "openapi.it/risk" in (risk.get("provider") or ""), \
            f"risk not persisted: {risk}"


# ---------- Feature 3: Associa proprietario a veicolo ----------
class TestAssociaProprietario:
    def test_associate_owner_updates_storico(self, admin_session):
        # 1. Crea/verifica veicolo con targa test
        r = admin_session.get(
            f"{API}/openapi-it/automotive-by-targa/{TEST_TARGA}",
            timeout=30,
        )
        assert r.status_code == 200
        vid = r.json()["veicolo"]["id"]
        assert vid

        # 2. Associa proprietario MELLO come acquisto
        r2 = admin_session.post(
            f"{API}/openapi-it/veicoli/{vid}/associa-proprietario/{MELLO_AID}",
            params={"tipo_operazione": "acquisto"},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert d.get("ok") is True
        storico = d.get("storico") or []
        assert len(storico) >= 1
        # L'ultima entry deve essere MELLO con tipo=acquisto
        last = storico[-1]
        assert last.get("anagrafica_id") == MELLO_AID
        assert last.get("tipo_operazione") == "acquisto"
        assert last.get("nome"), "nome non presente nello storico"
        assert last.get("data"), "data non presente nello storico"

    def test_associate_owner_404_if_veicolo_missing(self, admin_session):
        r = admin_session.post(
            f"{API}/openapi-it/veicoli/nonexistent-vid/associa-proprietario/{MELLO_AID}",
            timeout=15,
        )
        assert r.status_code == 404


# ---------- Feature 4: Regression status/company ----------
class TestRegressionStatusCompany:
    def test_status_returns_all_keys(self, admin_session):
        r = admin_session.get(f"{API}/openapi-it/status", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mode") in ("live", "mock")
        assert "has_credentials" in d
        assert "env" in d
        assert "credit_eur" in d  # può essere None ma la chiave deve esistere

    def test_company_direct_lookup(self, admin_session):
        r = admin_session.get(
            f"{API}/openapi-it/company",
            params={"piva": TEST_PIVA_OPENAPI},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "openapi.it" in (d.get("provider") or "")
        assert d.get("ragione_sociale")

    def test_company_save_to_libera(self, admin_session):
        r = admin_session.post(f"{API}/openapi-it/company/{LIBERA_AID}", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "openapi.it" in (d.get("provider") or "")
