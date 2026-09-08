"""Test estratto conto contraente (iter79)."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
CONTRAENTE_ID = "abe0cbf1-52a7-4d4b-b703-9a49ca89d924"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "admin@assicura.it", "password": "Admin123!"},
                      timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_preview_rata(h):
    r = requests.get(f"{BASE}/api/estratto-conto-contraente",
                     params={"contraente_id": CONTRAENTE_ID,
                             "dal": "01-05-2026", "al": "08-09-2026",
                             "filtra_per": "rata"}, headers=h, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["contraente"]["ragione_sociale"].upper().startswith("AUTOTRASPORTI VIVIANI")
    assert "righe" in data and isinstance(data["righe"], list)
    assert "totali" in data
    tot = data["totali"]
    assert round(tot["premi"] + tot["addizionali"], 2) == round(tot["totale"], 2)
    # ordinamento data decrescente
    from datetime import datetime
    def _k(s):
        try:
            return datetime.strptime(s, "%d-%m-%Y")
        except Exception:
            return datetime.min
    dates = [_k(r_["rata_del"]) for r_ in data["righe"]]
    assert dates == sorted(dates, reverse=True)
    # tutti i campi
    if data["righe"]:
        r0 = data["righe"][0]
        for k in ("contratto", "rata_del", "scad_mora", "data_copertura",
                  "compagnia", "rischio", "premio", "addizionali", "totale",
                  "tipo_cod", "targa_oggetto", "pagamento"):
            assert k in r0, f"campo mancante: {k}"


def test_preview_emissione(h):
    r = requests.get(f"{BASE}/api/estratto-conto-contraente",
                     params={"contraente_id": CONTRAENTE_ID,
                             "dal": "01-05-2026", "al": "08-09-2026",
                             "filtra_per": "emissione"}, headers=h, timeout=60)
    assert r.status_code == 200


def test_preview_copertura(h):
    r = requests.get(f"{BASE}/api/estratto-conto-contraente",
                     params={"contraente_id": CONTRAENTE_ID,
                             "dal": "01-05-2026", "al": "08-09-2026",
                             "filtra_per": "copertura"}, headers=h, timeout=60)
    assert r.status_code == 200


def test_includi_pagamenti_false(h):
    r = requests.get(f"{BASE}/api/estratto-conto-contraente",
                     params={"contraente_id": CONTRAENTE_ID,
                             "dal": "01-05-2026", "al": "08-09-2026",
                             "includi_pagamenti": "false"}, headers=h, timeout=60)
    assert r.status_code == 200
    for row in r.json()["righe"]:
        assert row["pagamento"] is None


def test_includi_collegati(h):
    r = requests.get(f"{BASE}/api/estratto-conto-contraente",
                     params={"contraente_id": CONTRAENTE_ID,
                             "dal": "01-05-2026", "al": "08-09-2026",
                             "includi_collegati": "true"}, headers=h, timeout=60)
    assert r.status_code == 200
    assert r.json()["collegati_inclusi"] is True


def test_pdf(h):
    r = requests.get(f"{BASE}/api/estratto-conto-contraente/pdf",
                     params={"contraente_id": CONTRAENTE_ID,
                             "dal": "01-05-2026", "al": "08-09-2026"},
                     headers=h, timeout=60)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 2048


def test_404_contraente_inesistente(h):
    r = requests.get(f"{BASE}/api/estratto-conto-contraente",
                     params={"contraente_id": "00000000-0000-0000-0000-000000000000"},
                     headers=h, timeout=30)
    assert r.status_code == 404
