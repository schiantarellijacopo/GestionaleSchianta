"""
Iter7 - Brogliaccio: verify /api/contabilita/brogliaccio?data=YYYY-MM-DD response
includes BOTH 'riepilogo_kpi' (7 fields) and 'liquidita' object with math:
  liquidita_disponibile = sum_conti - sospesi_attivi - saldo_cassa_compagnie
  liquidita_postera     = sum_conti - saldo_cassa_compagnie
"""
import os
import datetime as dt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# --- Brogliaccio response shape & math ----------------------------------------

class TestBrogliaccioLiquidita:
    def _fetch(self, session, data):
        r = session.get(f"{API}/contabilita/brogliaccio", params={"data": data}, timeout=20)
        assert r.status_code == 200, f"GET /contabilita/brogliaccio failed: {r.status_code} {r.text}"
        return r.json()

    def test_response_has_riepilogo_kpi_with_7_fields(self, session):
        today = dt.date.today().isoformat()
        body = self._fetch(session, today)
        assert "riepilogo_kpi" in body, "Missing riepilogo_kpi in response"
        kpi = body["riepilogo_kpi"]
        expected = {"entrate", "provvigioni", "crediti", "rimesse", "sconti", "spese", "saldo_cassa"}
        missing = expected - set(kpi.keys())
        assert not missing, f"riepilogo_kpi missing fields: {missing}; actual keys={list(kpi.keys())}"
        for k in expected:
            assert isinstance(kpi[k], (int, float)), f"kpi.{k} should be numeric, got {type(kpi[k])}"

    def test_response_has_liquidita_object_with_required_fields(self, session):
        today = dt.date.today().isoformat()
        body = self._fetch(session, today)
        assert "liquidita" in body, "Missing 'liquidita' object in brogliaccio response"
        liq = body["liquidita"]
        expected = {
            "sum_conti",
            "sospesi_attivi",
            "saldo_cassa_compagnie",
            "liquidita_disponibile",
            "liquidita_postera",
        }
        missing = expected - set(liq.keys())
        assert not missing, f"liquidita missing fields: {missing}; actual={list(liq.keys())}"
        for k in expected:
            assert isinstance(liq[k], (int, float)), f"liquidita.{k} not numeric"

    def test_liquidita_math_is_correct(self, session):
        today = dt.date.today().isoformat()
        body = self._fetch(session, today)
        liq = body["liquidita"]
        sum_conti = liq["sum_conti"]
        sospesi = liq["sospesi_attivi"]
        sal_cmp = liq["saldo_cassa_compagnie"]
        ld = liq["liquidita_disponibile"]
        lp = liq["liquidita_postera"]

        expected_ld = round(sum_conti - sospesi - sal_cmp, 2)
        expected_lp = round(sum_conti - sal_cmp, 2)
        assert abs(ld - expected_ld) < 0.011, (
            f"liquidita_disponibile mismatch: got {ld}, expected {expected_ld} "
            f"(sum_conti={sum_conti}, sospesi={sospesi}, saldo_cmp={sal_cmp})"
        )
        assert abs(lp - expected_lp) < 0.011, (
            f"liquidita_postera mismatch: got {lp}, expected {expected_lp}"
        )

    def test_saldo_cassa_compagnie_is_cumulative(self, session):
        """liquidita.saldo_cassa_compagnie is cumulative (sum of saldi_compagnie)
        and is used by the 7th KPI card on the frontend (label 'Saldo Cassa Cmp.').
        Note: riepilogo_kpi.saldo_cassa is the per-day saldo and is NOT the same value."""
        today = dt.date.today().isoformat()
        body = self._fetch(session, today)
        liq_saldo = body["liquidita"]["saldo_cassa_compagnie"]
        sum_saldi = round(sum(s.get("saldo_cassa", 0) for s in body.get("saldi_compagnie", [])), 2)
        assert abs(liq_saldo - sum_saldi) < 0.011, (
            f"liquidita.saldo_cassa_compagnie ({liq_saldo}) should equal sum of saldi_compagnie ({sum_saldi})"
        )

    def test_saldi_compagnie_still_present(self, session):
        today = dt.date.today().isoformat()
        body = self._fetch(session, today)
        assert "saldi_compagnie" in body, "saldi_compagnie key missing from response"
        assert isinstance(body["saldi_compagnie"], list)

    def test_past_date_also_returns_liquidita(self, session):
        """Cumulative computation up to a past date should also work."""
        past = (dt.date.today() - dt.timedelta(days=30)).isoformat()
        body = self._fetch(session, past)
        assert "liquidita" in body
        assert "riepilogo_kpi" in body
        liq = body["liquidita"]
        expected_ld = round(liq["sum_conti"] - liq["sospesi_attivi"] - liq["saldo_cassa_compagnie"], 2)
        assert abs(liq["liquidita_disponibile"] - expected_ld) < 0.011
