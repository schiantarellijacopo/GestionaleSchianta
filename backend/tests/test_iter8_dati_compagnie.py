"""Iter8 tests for new Contabilità sub-module 'Dati Compagnie'.

Endpoints tested:
- GET /api/contabilita/dati-compagnie (with/without dal/al)
- GET /api/contabilita/dati-compagnie/stampa (PDF)
- Math validation: incassi_netti = lordi - provv (if trattiene) else lordi
- saldo_attuale is cumulative (stays same regardless of dal/al period)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASS = "Admin123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return s


# ----- Endpoint reachable & shape ------------------------------------------------

class TestDatiCompagnieEndpoint:
    def test_returns_200_and_shape(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(["periodo", "compagnie", "totali"]).issubset(data.keys())
        assert isinstance(data["compagnie"], list)
        assert isinstance(data["totali"], dict)
        for k in ("incassi_lordi", "incassi_netti", "provvigioni",
                  "rimesse_pagate", "saldo_attuale"):
            assert k in data["totali"]

    def test_row_fields_and_types(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=20)
        data = r.json()
        assert len(data["compagnie"]) >= 1, "Expected at least 1 compagnia with movimenti"
        row = data["compagnie"][0]
        expected_keys = {"compagnia_id", "compagnia", "trattiene_provvigioni",
                         "incassi_lordi", "incassi_netti", "provvigioni",
                         "rimesse_pagate", "saldo_attuale"}
        assert expected_keys.issubset(row.keys())
        assert isinstance(row["trattiene_provvigioni"], bool)
        for k in ("incassi_lordi", "incassi_netti", "provvigioni",
                  "rimesse_pagate", "saldo_attuale"):
            assert isinstance(row[k], (int, float))

    def test_sorted_by_abs_saldo_desc(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=20)
        rows = r.json()["compagnie"]
        if len(rows) < 2:
            pytest.skip("Need >=2 rows to validate ordering")
        abs_vals = [abs(x["saldo_attuale"]) for x in rows]
        assert abs_vals == sorted(abs_vals, reverse=True), \
            f"Rows must be sorted by abs(saldo_attuale) DESC, got {abs_vals}"

    def test_skips_zero_compagnie(self, admin_session):
        """Any returned row must NOT have everything = 0."""
        r = admin_session.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=20)
        for row in r.json()["compagnie"]:
            zero_all = (
                abs(row["incassi_lordi"]) < 0.01 and
                abs(row["rimesse_pagate"]) < 0.01 and
                abs(row["saldo_attuale"]) < 0.01
            )
            assert not zero_all, f"Zero-only row leaked: {row}"


# ----- Math validation ------------------------------------------------------------

class TestIncassiNettiMath:
    def test_netti_formula(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=20)
        for row in r.json()["compagnie"]:
            expected = (
                round(row["incassi_lordi"] - row["provvigioni"], 2)
                if row["trattiene_provvigioni"] else round(row["incassi_lordi"], 2)
            )
            assert abs(row["incassi_netti"] - expected) < 0.01, (
                f"{row['compagnia']}: trattiene={row['trattiene_provvigioni']} "
                f"lordi={row['incassi_lordi']} provv={row['provvigioni']} "
                f"netti={row['incassi_netti']} expected={expected}"
            )

    def test_allianz_specific(self, admin_session):
        """As per agent-to-agent context: Allianz with trattiene=true,
        lordi=620, provv=35 → netti=585."""
        r = admin_session.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=20)
        rows = r.json()["compagnie"]
        allianz = next((x for x in rows
                        if "allianz" in x["compagnia"].lower()), None)
        if not allianz:
            pytest.skip("Allianz row not present in current DB")
        # validate the math formula on the actual values
        if allianz["trattiene_provvigioni"]:
            assert abs(allianz["incassi_netti"] -
                       (allianz["incassi_lordi"] - allianz["provvigioni"])) < 0.01

    def test_totali_match_sum_of_rows(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=20)
        data = r.json()
        rows = data["compagnie"]
        t = data["totali"]
        for k in ("incassi_lordi", "incassi_netti", "provvigioni",
                  "rimesse_pagate", "saldo_attuale"):
            assert abs(t[k] - round(sum(r[k] for r in rows), 2)) < 0.01, k


# ----- Period filter --------------------------------------------------------------

class TestPeriodFilter:
    def test_saldo_attuale_cumulative_invariant(self, admin_session):
        """saldo_attuale must NOT depend on dal/al."""
        r1 = admin_session.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=20).json()
        r2 = admin_session.get(
            f"{BASE_URL}/api/contabilita/dati-compagnie",
            params={"dal": "2024-01-01", "al": "2024-01-31"},
            timeout=20,
        ).json()

        # Build maps {compagnia_id -> saldo_attuale} but only for cmp that exist in both
        m1 = {x["compagnia_id"]: x["saldo_attuale"] for x in r1["compagnie"]}
        m2 = {x["compagnia_id"]: x["saldo_attuale"] for x in r2["compagnie"]}
        common = set(m1.keys()) & set(m2.keys())
        if not common:
            pytest.skip("No common compagnie between full-period and Jan2024")
        for cid in common:
            assert abs(m1[cid] - m2[cid]) < 0.01, (
                f"saldo_attuale changed with period filter for {cid}: "
                f"{m1[cid]} vs {m2[cid]}"
            )

    def test_period_zero_window_reduces_incassi(self, admin_session):
        """A 1-day window in 1900 should have all incassi/provv/rimesse = 0,
        but saldo_attuale still cumulative."""
        r = admin_session.get(
            f"{BASE_URL}/api/contabilita/dati-compagnie",
            params={"dal": "1900-01-01", "al": "1900-01-02"},
            timeout=20,
        ).json()
        # rows are only kept if anything is non-zero; saldo cumulative may exist
        for row in r["compagnie"]:
            assert abs(row["incassi_lordi"]) < 0.01
            assert abs(row["provvigioni"]) < 0.01
            assert abs(row["rimesse_pagate"]) < 0.01

    def test_period_echoed_in_response(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/contabilita/dati-compagnie",
            params={"dal": "2024-01-01", "al": "2024-12-31"},
            timeout=20,
        ).json()
        assert r["periodo"]["dal"] == "2024-01-01"
        assert r["periodo"]["al"] == "2024-12-31"


# ----- PDF ----------------------------------------------------------------------

class TestStampaPDF:
    def test_pdf_returns_application_pdf(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/contabilita/dati-compagnie/stampa", timeout=30
        )
        assert r.status_code == 200, r.text[:300]
        assert "application/pdf" in r.headers.get("content-type", "").lower()
        assert r.content[:4] == b"%PDF", f"Not a PDF: starts with {r.content[:8]!r}"
        assert len(r.content) > 500

    def test_pdf_with_period(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/contabilita/dati-compagnie/stampa",
            params={"dal": "2024-01-01", "al": "2024-12-31"},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


# ----- Permissions --------------------------------------------------------------

class TestPermissions:
    def test_unauthenticated_blocked(self):
        r = requests.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=10)
        assert r.status_code in (401, 403)

    def test_cliente_role_blocked(self):
        s = requests.Session()
        lr = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "cliente@assicura.it", "password": "Cliente123!"},
            timeout=15,
        )
        if lr.status_code != 200:
            pytest.skip("Cliente login not available")
        r = s.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=15)
        assert r.status_code in (401, 403), f"cliente should be forbidden, got {r.status_code}"

    def test_dipendente_allowed(self):
        s = requests.Session()
        lr = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "dipendente@assicura.it", "password": "Dipendente123!"},
            timeout=15,
        )
        if lr.status_code != 200:
            pytest.skip("Dipendente login not available")
        r = s.get(f"{BASE_URL}/api/contabilita/dati-compagnie", timeout=15)
        assert r.status_code == 200
