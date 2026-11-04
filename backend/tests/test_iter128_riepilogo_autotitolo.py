# Iter128: Trattative riepilogo + auto-titolo on update_polizza + compagnie tipo_mandato
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    r = ses.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    if r.status_code != 200:
        pytest.skip("login failed")
    ses.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return ses


# --- Trattative riepilogo
class TestTrattativeRiepilogo:
    def test_riepilogo_values(self, s):
        r = s.get(f"{BASE_URL}/api/pipeline/trattative")
        assert r.status_code == 200
        d = r.json()
        rp = d["riepilogo"]
        for k in ("valore_aperte", "n_aperte", "valore_vinte", "n_vinte"):
            assert k in rp
        cols = {c["key"]: c for c in d["colonne"]}
        n_ap = sum(cols[k]["count"] for k in ("aperta", "proposta_inviata", "in_attesa"))
        assert rp["n_aperte"] == n_ap
        assert rp["n_vinte"] == cols["vinta"]["count"]

    def test_riepilogo_matches_trattative_sum(self, s):
        r = s.get(f"{BASE_URL}/api/trattative")
        if r.status_code != 200:
            pytest.skip("no /api/trattative list")
        items = r.json()
        items = items.get("items", items) if isinstance(items, dict) else items
        ap = round(sum(float(t.get("premio_proposto") or 0) for t in items
                       if (t.get("stato") or "aperta") in ("aperta", "proposta_inviata", "in_attesa")), 2)
        vi = round(sum(float(t.get("premio_proposto") or 0) for t in items if t.get("stato") == "vinta"), 2)
        rp = s.get(f"{BASE_URL}/api/pipeline/trattative").json()["riepilogo"]
        assert rp["valore_aperte"] == ap
        assert rp["valore_vinte"] == vi


# --- Auto-titolo on update
class TestAutoTitolo:
    def test_auto_titolo_on_update_no_dup(self, s):
        comps = s.get(f"{BASE_URL}/api/compagnie").json()
        anas = s.get(f"{BASE_URL}/api/anagrafiche").json()
        anas = anas.get("items", anas) if isinstance(anas, dict) else anas
        assert comps and anas
        body = {"numero_polizza": "TEST_AUTOTIT_128", "compagnia_id": comps[0]["id"],
                "contraente_id": anas[0]["id"], "ramo": "RCA", "stato": "attiva",
                "frazionamento": "annuale", "effetto": "2026-02-01", "scadenza": "2027-02-01"}
        r = s.post(f"{BASE_URL}/api/polizze", json=body)
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        try:
            t0 = s.get(f"{BASE_URL}/api/titoli", params={"polizza_id": pid}).json()
            t0 = t0.get("items", t0) if isinstance(t0, dict) else t0
            if len(t0):
                # remove auto-created titolo to emulate imported policy
                for t in t0:
                    s.delete(f"{BASE_URL}/api/titoli/{t['id']}")
                t0 = s.get(f"{BASE_URL}/api/titoli", params={"polizza_id": pid}).json()
                t0 = t0.get("items", t0) if isinstance(t0, dict) else t0
            assert len(t0) == 0, "precondition: no titolo"
            upd = {"premio_lordo": 340.0, "premio_netto": 270.01, "premio_tasse": 60.0,
                   "premio_imposte": 5.0, "premio_ssn": 4.99, "provvigioni": 50.0,
                   "effetto": "2026-02-01"}
            r = s.put(f"{BASE_URL}/api/polizze/{pid}", json=upd)
            assert r.status_code == 200, r.text
            ts = s.get(f"{BASE_URL}/api/titoli", params={"polizza_id": pid}).json()
            ts = ts.get("items", ts) if isinstance(ts, dict) else ts
            assert len(ts) == 1
            t = ts[0]
            t = s.get(f"{BASE_URL}/api/titoli/{t['id']}").json()
            print("TITOLO", t)
            assert t["stato"] == "da_incassare"
            assert t["importo_lordo"] == 340.0
            assert t["importo_netto"] == 270.01
            assert t["imposte"] == 65.0
            assert t["ssn"] == 4.99
            assert t["provvigioni"] == 50.0
            assert t["effetto"] == "2026-02-01"
            # edit again -> no duplicates, amounts updated
            r = s.put(f"{BASE_URL}/api/polizze/{pid}", json={"premio_lordo": 400.0, "provvigioni": 60.0})
            assert r.status_code == 200
            ts = s.get(f"{BASE_URL}/api/titoli", params={"polizza_id": pid}).json()
            ts = ts.get("items", ts) if isinstance(ts, dict) else ts
            assert len(ts) == 1
            assert ts[0]["importo_lordo"] == 400.0
            assert ts[0]["provvigioni"] == 60.0
        finally:
            dr = s.delete(f"{BASE_URL}/api/polizze/{pid}")
            print("cleanup polizza", dr.status_code)
