# Iteration: global search on libro matricola targa + polizza applicazioni + documenti inbox list
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
POL_ID = "027e3212-d8c5-4e41-a571-47e0782d1023"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "jacopo@schiantarelli.it", "password": "NtdZs5ilxTSP"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


# Global search: targa on applicazioni
def test_search_targa_matricola(client):
    r = client.get(f"{BASE_URL}/api/search", params={"q": "AA41979"}, timeout=60)
    assert r.status_code == 200
    pols = r.json()["polizze"]
    m = [p for p in pols if p.get("numero_polizza") == "153000736"]
    assert m, f"polizza not found: {[p.get('numero_polizza') for p in pols]}"
    assert m[0]["matricola_targa"] == "AA41979"
    assert m[0]["id"] == POL_ID
    assert "MAGANETTI" in (m[0].get("contraente_nome") or "")
    assert "_id" not in m[0]


def test_search_targa_lowercase_with_space(client):
    r = client.get(f"{BASE_URL}/api/search", params={"q": "aa 41979"}, timeout=60)
    assert r.status_code == 200
    assert any(p.get("id") == POL_ID for p in r.json()["polizze"])


def test_search_short_query(client):
    r = client.get(f"{BASE_URL}/api/search", params={"q": "A"})
    assert r.status_code == 200
    assert r.json()["polizze"] == []


# Applicazioni of libro matricola polizza
def test_polizza_applicazioni(client):
    r = client.get(f"{BASE_URL}/api/polizze/{POL_ID}/applicazioni", params={"includi_storico": "true"}, timeout=60)
    assert r.status_code == 200
    apps = r.json()
    assert isinstance(apps, list) and len(apps) >= 400
    assert any(a.get("targa") == "AA41979" for a in apps)
    assert all("_id" not in a for a in apps[:20])


# Polizze search used by ReviewDialog
def test_polizze_q_search(client):
    r = client.get(f"{BASE_URL}/api/polizze", params={"q": "153000736", "limit": 20}, timeout=60)
    assert r.status_code == 200
    assert any(p.get("id") == POL_ID for p in r.json())


# Documenti inbox list
def test_documenti_inbox_list(client):
    r = client.get(f"{BASE_URL}/api/documenti-inbox", timeout=60)
    assert r.status_code == 200
