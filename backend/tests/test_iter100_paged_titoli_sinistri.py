"""Tests for iteration 100:
- Paginazione server-side su /api/titoli e /api/sinistri (paged=true)
- Totali server-side su intero set filtrato
- Ordinamento server (sort, dir)
- Regressione: senza paged ritorna LISTA
"""
import os
import math
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EMAIL = "jacopo@schiantarelli.it"
PASSWORD = "NtdZs5ilxTSP"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- TITOLI paged ----------
class TestTitoliPaged:
    def test_paged_structure(self, H):
        r = requests.get(
            f"{BASE_URL}/api/titoli",
            params={"stato_not": "incassato,stornato", "paged": "true",
                    "page": 1, "page_size": 50, "sort": "importo_lordo", "dir": "desc"},
            headers=H, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d, dict), "paged must return object"
        for k in ("items", "total", "pages", "page", "page_size", "totali"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["items"], list)
        assert len(d["items"]) <= 50
        assert d["page"] == 1
        assert d["page_size"] == 50
        assert d["pages"] == math.ceil(d["total"] / 50) if d["total"] else d["pages"] >= 0
        # totali keys
        tot = d["totali"]
        for k in ("t_lordo", "t_netto", "t_provv"):
            assert k in tot, f"totali missing {k}"
        # sorting desc on importo_lordo: first >= second
        if len(d["items"]) >= 2:
            a = float(d["items"][0].get("importo_lordo") or 0)
            b = float(d["items"][1].get("importo_lordo") or 0)
            assert a >= b, f"sort desc failed: {a} < {b}"

    def test_paged_page2_same_total(self, H):
        p1 = requests.get(f"{BASE_URL}/api/titoli",
                          params={"stato_not": "incassato,stornato", "paged": "true",
                                  "page": 1, "page_size": 50, "sort": "importo_lordo", "dir": "desc"},
                          headers=H, timeout=60).json()
        p2 = requests.get(f"{BASE_URL}/api/titoli",
                          params={"stato_not": "incassato,stornato", "paged": "true",
                                  "page": 2, "page_size": 50, "sort": "importo_lordo", "dir": "desc"},
                          headers=H, timeout=60).json()
        assert p1["total"] == p2["total"], "total changed between pages"
        assert p1["totali"] == p2["totali"], "totali changed between pages"
        # items should differ
        ids1 = {it.get("id") for it in p1["items"]}
        ids2 = {it.get("id") for it in p2["items"]}
        if p1["total"] > 50:
            assert ids1 != ids2, "page1 and page2 items identical"

    def test_regression_no_paged_returns_list(self, H):
        # Need a polizza_id to test the usual branch. Pick first titolo.
        r = requests.get(f"{BASE_URL}/api/titoli",
                         params={"paged": "true", "page": 1, "page_size": 1},
                         headers=H, timeout=60).json()
        if not r.get("items"):
            pytest.skip("no titoli to pick polizza from")
        pol_id = r["items"][0].get("polizza_id")
        if not pol_id:
            pytest.skip("first titolo has no polizza_id")
        r2 = requests.get(f"{BASE_URL}/api/titoli",
                         params={"polizza_id": pol_id}, headers=H, timeout=60)
        assert r2.status_code == 200
        data = r2.json()
        assert isinstance(data, list), f"expected list, got {type(data).__name__}"


# ---------- SINISTRI paged ----------
class TestSinistriPaged:
    def test_paged_structure(self, H):
        r = requests.get(f"{BASE_URL}/api/sinistri",
                         params={"paged": "true", "page": 1, "page_size": 50,
                                 "sort": "riserva", "dir": "desc"},
                         headers=H, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d, dict)
        for k in ("items", "total", "pages", "page", "page_size", "totali"):
            assert k in d, f"missing key {k}"
        assert len(d["items"]) <= 50
        tot = d["totali"]
        for k in ("n", "stimato", "liquidato"):
            assert k in tot, f"sinistri totali missing {k}"
        if len(d["items"]) >= 2:
            a = float(d["items"][0].get("riserva") or 0)
            b = float(d["items"][1].get("riserva") or 0)
            assert a >= b

    def test_paged_page2_same_total(self, H):
        p1 = requests.get(f"{BASE_URL}/api/sinistri",
                          params={"paged": "true", "page": 1, "page_size": 50},
                          headers=H, timeout=60).json()
        if p1["total"] <= 50:
            pytest.skip("not enough sinistri for pagination comparison")
        p2 = requests.get(f"{BASE_URL}/api/sinistri",
                          params={"paged": "true", "page": 2, "page_size": 50},
                          headers=H, timeout=60).json()
        assert p1["total"] == p2["total"]
        assert p1["totali"] == p2["totali"]

    def test_regression_no_paged_returns_list(self, H):
        r = requests.get(f"{BASE_URL}/api/sinistri",
                         params={"paged": "true", "page": 1, "page_size": 1},
                         headers=H, timeout=60).json()
        if not r.get("items"):
            pytest.skip("no sinistri")
        pol_id = r["items"][0].get("polizza_id")
        if not pol_id:
            pytest.skip("no polizza_id on first sinistro")
        r2 = requests.get(f"{BASE_URL}/api/sinistri",
                         params={"polizza_id": pol_id}, headers=H, timeout=60)
        assert r2.status_code == 200
        assert isinstance(r2.json(), list), "expected list without paged"
