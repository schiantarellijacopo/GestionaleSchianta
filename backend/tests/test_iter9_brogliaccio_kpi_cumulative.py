"""
Iter9 - Brogliaccio KPI CUMULATIVE bug fix verification.

Bug reported: KPI cards (Entrate/Provvigioni/Sospesi/Rimesse/Sconti/Spese/Saldo)
on the Brogliaccio were showing only the SELECTED DAY values. They must be
PROGRESSIVE (cumulative): each closed day adds to the totals, so the next day
already shows running totals.

Spec under test:
  GET /api/contabilita/brogliaccio?data=YYYY-MM-DD must return
    riepilogo_kpi   -> CUMULATIVE up to and INCLUDING the date
    totali_giornata -> still DAILY (only the selected day movements)
    liquidita       -> cumulative as before
  Mathematical consistency:
    KPI(D2) == KPI(D1) + delta(movimenti with D1 < data_movimento <= D2)
  saldo_cassa formula:
    saldo_cassa = sum(incasso_premio: (importo-provv) if trattiene else -provv)
                  - cumulative rimesse (pagamento_compagnia)
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"


# --- Shared session fixture ---------------------------------------------------

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


def _brogliaccio(session, data):
    r = session.get(f"{API}/contabilita/brogliaccio", params={"data": data}, timeout=20)
    assert r.status_code == 200, f"GET brogliaccio failed: {r.status_code} {r.text}"
    return r.json()


# --- Module: shape & invariants -----------------------------------------------

class TestKpiShape:
    """riepilogo_kpi must contain exactly the 7 numeric fields."""

    def test_kpi_has_7_numeric_fields(self, session):
        body = _brogliaccio(session, "2026-06-23")
        kpi = body["riepilogo_kpi"]
        expected = {"entrate", "provvigioni", "crediti", "rimesse",
                    "sconti", "spese", "saldo_cassa"}
        assert set(kpi.keys()) >= expected, f"Missing keys: {expected - set(kpi.keys())}"
        for k in expected:
            assert isinstance(kpi[k], (int, float)), f"kpi.{k} not numeric"

    def test_liquidita_object_preserved(self, session):
        body = _brogliaccio(session, "2026-06-23")
        assert "liquidita" in body, "liquidita object missing"
        liq = body["liquidita"]
        for k in ("sum_conti", "sospesi_attivi", "saldo_cassa_compagnie",
                  "liquidita_disponibile", "liquidita_postera"):
            assert k in liq, f"liquidita.{k} missing"
            assert isinstance(liq[k], (int, float)), f"liquidita.{k} not numeric"


# --- Module: cumulative behaviour on bare DB ----------------------------------

class TestKpiCumulativeBasic:
    """KPI before any movement = all zero; KPI grows monotonically (non-decreasing)
    on every metric that is a sum of non-negative entries."""

    def test_date_before_any_movement_is_all_zero(self, session):
        body = _brogliaccio(session, "1900-01-01")
        kpi = body["riepilogo_kpi"]
        for k, v in kpi.items():
            assert v == 0, f"Expected 0 on 1900-01-01 but kpi.{k}={v}"

    def test_kpi_monotonic_non_decreasing(self, session):
        """Sum-of-positives metrics must never decrease as the date advances."""
        a = _brogliaccio(session, "2026-01-01")["riepilogo_kpi"]
        b = _brogliaccio(session, "2026-12-31")["riepilogo_kpi"]
        for k in ("entrate", "provvigioni", "rimesse", "sconti", "spese"):
            assert b[k] >= a[k] - 1e-6, (
                f"KPI.{k} should be non-decreasing: 2026-01-01={a[k]} -> 2026-12-31={b[k]}"
            )

    def test_totali_giornata_is_daily_not_cumulative(self, session):
        """On a date with movements (2026-01-15) totali_giornata should equal
        the per-day delta and be smaller than (or different from) the cumulative
        KPI computed on a later date with no movements (2026-12-31).
        """
        d1 = _brogliaccio(session, "2026-01-15")
        d_future = _brogliaccio(session, "2026-12-31")
        # KPI on a far-future date >= KPI on an earlier date (cumulative)
        assert d_future["riepilogo_kpi"]["entrate"] >= d1["riepilogo_kpi"]["entrate"]
        # totali_giornata on 2026-12-31 must be all zero (no movement on that day)
        if len(d_future["righe"]) == 0:
            tg = d_future["totali_giornata"]
            for k in ("totale", "provv", "saldo", "crediti", "spese", "sconti", "rimesse"):
                assert tg[k] == 0, (
                    f"totali_giornata.{k} should be 0 on a day with no movements,"
                    f" got {tg[k]} (proves it's daily, not cumulative)"
                )


# --- Module: mathematical consistency with seeded test movimenti --------------

class TestKpiCumulativeConsistency:
    """Create 2 movimenti on two different past dates and verify
       KPI(D2) - KPI(D1) == delta(movimenti on (D1, D2])."""

    @pytest.fixture(scope="class")
    def seeded(self, session):
        # Pick two dates in the distant past where there are no other movements
        d1 = "1995-03-10"
        d2 = "1995-03-15"
        # Get a cash account
        # cash accounts live under /librerie/conti-cassa; also they're returned
        # in any brogliaccio response under "conti_cassa"
        r = session.get(f"{API}/librerie/conti-cassa", timeout=10)
        if r.status_code != 200:
            conti = _brogliaccio(session, "2026-01-01")["conti_cassa"]
        else:
            conti = r.json()
        assert conti, "No conti_cassa available - cannot seed test"
        conto_id = conti[0]["id"]

        # Defensive pre-cleanup: remove any leftover TEST_iter9 movements from
        # a previously failed run (fixture teardown didn't fire on collect error)
        try:
            r = session.get(
                f"{API}/contabilita/movimenti",
                params={"data_dal": "1995-01-01", "data_al": "1995-12-31"},
                timeout=15,
            )
            if r.status_code == 200:
                rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
                for m in rows:
                    if "TEST_iter9" in (m.get("descrizione") or ""):
                        session.delete(f"{API}/contabilita/movimenti/{m['id']}", timeout=10)
        except Exception:
            pass

        created = []

        def _create(payload):
            payload.setdefault("conto_cassa_id", conto_id)
            r = session.post(f"{API}/contabilita/movimenti", json=payload, timeout=15)
            assert r.status_code == 201, f"create movimento failed: {r.status_code} {r.text}"
            mid = r.json()["id"]
            created.append(mid)
            return mid

        # Sanity: ensure starting KPI on d1-1day is all zero (no historical data
        # in 1995 timeframe)
        prev = _brogliaccio(session, "1995-03-09")["riepilogo_kpi"]
        assert all(v == 0 for v in prev.values()), (
            f"Pre-condition failed: expected empty KPI for 1995-03-09 but got {prev}"
        )

        # On D1: a generic entrata (incasso_premio without compagnia -> trattiene
        # defaults to True so saldo = importo - provvigioni)
        _create({
            "data_movimento": d1,
            "tipo": "entrata",
            "categoria": "incasso_premio",
            "importo": 1000.0,
            "provvigioni": 100.0,
            "descrizione": f"TEST_iter9_d1_{uuid.uuid4().hex[:6]}",
        })
        # On D1: a spesa
        _create({
            "data_movimento": d1,
            "tipo": "uscita",
            "categoria": "spese_amministrative",
            "importo": 50.0,
            "descrizione": f"TEST_iter9_spesa_d1_{uuid.uuid4().hex[:6]}",
        })

        # On D2: a second incasso + a rimessa (pagamento_compagnia)
        _create({
            "data_movimento": d2,
            "tipo": "entrata",
            "categoria": "incasso_premio",
            "importo": 500.0,
            "provvigioni": 50.0,
            "descrizione": f"TEST_iter9_d2_{uuid.uuid4().hex[:6]}",
        })
        _create({
            "data_movimento": d2,
            "tipo": "uscita",
            "categoria": "pagamento_compagnia",
            "importo": 200.0,
            "descrizione": f"TEST_iter9_rimessa_d2_{uuid.uuid4().hex[:6]}",
        })

        yield {"d1": d1, "d2": d2, "ids": created}

        # Teardown
        for mid in created:
            try:
                session.delete(f"{API}/contabilita/movimenti/{mid}", timeout=10)
            except Exception:
                pass

    def test_kpi_on_d1_matches_d1_movements(self, session, seeded):
        kpi = _brogliaccio(session, seeded["d1"])["riepilogo_kpi"]
        # Expected from the 2 movements on d1:
        # entrate: 1000 ; provvigioni: 100 ; spese: 50 ; saldo: 1000-100 = 900
        assert abs(kpi["entrate"] - 1000.0) < 0.01, kpi
        assert abs(kpi["provvigioni"] - 100.0) < 0.01, kpi
        assert abs(kpi["spese"] - 50.0) < 0.01, kpi
        assert abs(kpi["rimesse"] - 0.0) < 0.01, kpi
        assert abs(kpi["saldo_cassa"] - 900.0) < 0.01, (
            f"saldo_cassa on d1 should be 900 (incasso 1000 - provv 100, no rimesse), got {kpi}"
        )

    def test_kpi_on_d2_is_d1_plus_d2_delta(self, session, seeded):
        kpi_d2 = _brogliaccio(session, seeded["d2"])["riepilogo_kpi"]
        # Cumulative after both days:
        # entrate: 1000 + 500 = 1500
        # provvigioni: 100 + 50 = 150
        # spese: 50
        # rimesse: 200
        # saldo: (1000-100) + (500-50) - 200 = 900 + 450 - 200 = 1150
        assert abs(kpi_d2["entrate"] - 1500.0) < 0.01, kpi_d2
        assert abs(kpi_d2["provvigioni"] - 150.0) < 0.01, kpi_d2
        assert abs(kpi_d2["spese"] - 50.0) < 0.01, kpi_d2
        assert abs(kpi_d2["rimesse"] - 200.0) < 0.01, kpi_d2
        assert abs(kpi_d2["saldo_cassa"] - 1150.0) < 0.01, (
            f"saldo_cassa cumulative formula broken: expected 1150, got {kpi_d2}"
        )

    def test_totali_giornata_d2_only_d2(self, session, seeded):
        """totali_giornata on D2 must contain ONLY the D2 movements (daily,
        not cumulative)."""
        body = _brogliaccio(session, seeded["d2"])
        tg = body["totali_giornata"]
        # Only D2 movements: incasso 500 (provv 50) + uscita rimessa 200
        # totale row sums signed amounts: entrata 500 - uscita 200 = 300
        assert abs(tg["totale"] - 300.0) < 0.01, (
            f"totali_giornata.totale should be 300 (500 in - 200 out on D2 only), got {tg}"
        )
        assert abs(tg["provv"] - 50.0) < 0.01, tg
        assert abs(tg["rimesse"] - 200.0) < 0.01, tg
        # NOT cumulative: D1 entrate (1000) and spesa (50) must NOT be here
        # the previous-day spesa shouldn't appear in today's spese
        assert abs(tg["spese"] - 200.0) < 0.01 or abs(tg["spese"] - 0.0) < 0.01, (
            f"totali_giornata.spese unexpected on D2: got {tg['spese']}"
            " (should be just 200 if rimessa is counted in spese, or 0, but NOT 50+200)"
        )
        # The number of righe on D2 must equal 2 (the 2 D2 movements)
        # Filter out movements pre-existing on this exact date in the seeded DB
        # We rely on the unique TEST_iter9 prefix
        d2_righe = [r for r in body["righe"]
                    if "TEST_iter9" in (r.get("descrizione") or "")]
        assert len(d2_righe) == 2, (
            f"Expected 2 TEST_iter9 righe on D2, got {len(d2_righe)}"
        )

    def test_d_between_d1_and_d2_equals_d1(self, session, seeded):
        """A date strictly between D1 and D2 (no movement) must have KPI ==
        KPI(D1) — proving cumulativity by inclusion of D1 only."""
        # d1=1995-03-10, d2=1995-03-15; in-between with no movement:
        kpi_mid = _brogliaccio(session, "1995-03-12")["riepilogo_kpi"]
        kpi_d1 = _brogliaccio(session, seeded["d1"])["riepilogo_kpi"]
        for k in kpi_mid:
            assert abs(kpi_mid[k] - kpi_d1[k]) < 0.01, (
                f"KPI.{k} should be unchanged between D1 and D2 (no movements in between):"
                f" mid={kpi_mid[k]} d1={kpi_d1[k]}"
            )

    def test_day_before_d1_has_no_d1_data(self, session, seeded):
        """KPI on the day BEFORE D1 must NOT include D1 movements (cumulative
        is up to and INCLUDING the date)."""
        kpi_prev = _brogliaccio(session, "1995-03-09")["riepilogo_kpi"]
        for k, v in kpi_prev.items():
            assert v == 0, f"KPI on day-before-D1 should be 0 but {k}={v}"


# --- Module: liquidita stays cumulative ---------------------------------------

class TestLiquiditaCumulative:
    def test_liquidita_math_consistent(self, session):
        body = _brogliaccio(session, "2026-06-23")
        liq = body["liquidita"]
        expected_ld = round(liq["sum_conti"] - liq["sospesi_attivi"]
                            - liq["saldo_cassa_compagnie"], 2)
        expected_lp = round(liq["sum_conti"] - liq["saldo_cassa_compagnie"], 2)
        assert abs(liq["liquidita_disponibile"] - expected_ld) < 0.011, liq
        assert abs(liq["liquidita_postera"] - expected_lp) < 0.011, liq
