# Iteration 127: Disdette CRUD + pipeline trattative/disdette boards & move
import os
import pytest
import requests
from datetime import date, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    r = ses.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    if r.status_code != 200:
        pytest.skip("login failed")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        ses.headers.update({"Authorization": f"Bearer {tok}"})
    return ses


@pytest.fixture(scope="module")
def created(s):
    ids = []
    yield ids
    for i in ids:
        s.delete(f"{BASE_URL}/api/disdette/{i}")


# Disdette CRUD
def test_disdette_crud(s, created):
    past = (date.today() - timedelta(days=2)).isoformat()
    r = s.post(f"{BASE_URL}/api/disdette", json={"compagnia_da_disdire": "TEST_UnipolSai", "data_scadenza": past})
    assert r.status_code == 201, r.text
    d = r.json(); created.append(d["id"])
    assert d["stato"] == "da_inviare" and "_id" not in d
    lst = s.get(f"{BASE_URL}/api/disdette").json()
    assert any(x["id"] == d["id"] for x in lst)
    up = s.put(f"{BASE_URL}/api/disdette/{d['id']}", json={"compagnia_da_disdire": "TEST_UnipolSai", "stato": "inviata", "data_scadenza": past})
    assert up.status_code == 200 and up.json()["stato"] == "inviata"
    f = s.get(f"{BASE_URL}/api/disdette", params={"stato": "inviata"}).json()
    assert any(x["id"] == d["id"] for x in f)


def test_disdette_validation(s):
    r = s.post(f"{BASE_URL}/api/disdette", json={"compagnia_da_disdire": "   "})
    assert r.status_code in (400, 422)
    assert s.put(f"{BASE_URL}/api/disdette/nope", json={"compagnia_da_disdire": "x"}).status_code == 404
    assert s.delete(f"{BASE_URL}/api/disdette/nope").status_code == 404


# Pipeline disdette board + move
def test_pipeline_disdette_move(s, created):
    r = s.post(f"{BASE_URL}/api/disdette", json={"compagnia_da_disdire": "TEST_Pipe", "data_scadenza": date.today().isoformat()})
    did = r.json()["id"]; created.append(did)
    b = s.get(f"{BASE_URL}/api/pipeline/disdette").json()
    keys = [c["key"] for c in b["colonne"]]
    assert keys == ["da_inviare", "inviata", "confermata", "annullata"]
    card = [c for c in b["colonne"][0]["cards"] if c["id"] == did]
    assert card and "⚠ scaduta" in card[0]["tags"]
    m = s.post(f"{BASE_URL}/api/pipeline/disdette/{did}/move", json={"nuovo_stato": "confermata"})
    assert m.status_code == 200
    b = s.get(f"{BASE_URL}/api/pipeline/disdette").json()
    conf = [c for c in b["colonne"] if c["key"] == "confermata"][0]
    assert any(c["id"] == did for c in conf["cards"])
    bad = s.post(f"{BASE_URL}/api/pipeline/disdette/{did}/move", json={"nuovo_stato": "xxx"})
    assert bad.status_code == 400
    assert s.post(f"{BASE_URL}/api/pipeline/disdette/nope/move", json={"nuovo_stato": "inviata"}).status_code == 404


# Pipeline trattative board + move (restores original stato)
def test_pipeline_trattative_move(s):
    b = s.get(f"{BASE_URL}/api/pipeline/trattative").json()
    assert [c["key"] for c in b["colonne"]] == ["aperta", "proposta_inviata", "in_attesa", "vinta", "persa"]
    src = next((c for c in b["colonne"] if c["cards"]), None)
    if not src:
        pytest.skip("no trattative")
    tid = src["cards"][0]["id"]
    tgt = "in_attesa" if src["key"] != "in_attesa" else "aperta"
    assert s.post(f"{BASE_URL}/api/pipeline/trattative/{tid}/move", json={"nuovo_stato": tgt}).status_code == 200
    b2 = s.get(f"{BASE_URL}/api/pipeline/trattative").json()
    assert any(c["id"] == tid for col in b2["colonne"] if col["key"] == tgt for c in col["cards"])
    assert s.post(f"{BASE_URL}/api/pipeline/trattative/{tid}/move", json={"nuovo_stato": src["key"]}).status_code == 200
    assert s.post(f"{BASE_URL}/api/pipeline/trattative/{tid}/move", json={"nuovo_stato": "bogus"}).status_code == 400


def test_pipeline_sinistri_still_works(s):
    r = s.get(f"{BASE_URL}/api/pipeline/sinistri")
    assert r.status_code == 200 and r.json().get("colonne")
