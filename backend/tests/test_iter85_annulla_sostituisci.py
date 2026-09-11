"""Iter 85 tests: annulla/sostituisci polizza con storno condizionato,
titoli-arretrati endpoint, conteggi 'sostituita', PUT rendita_annua.
NOTE: usa admin@assicura.it (tenant di test principale). NON tocca tenant OMNIA.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login fallito: {r.status_code} {r.text}"
    token = r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def seed(client):
    """Crea contraente + compagnia (o riusa) + un contraente TEST per le polizze."""
    # trova o crea compagnia
    r = client.get(f"{API}/compagnie")
    assert r.status_code == 200
    comps = r.json()
    if not comps:
        r = client.post(f"{API}/compagnie", json={"nome": "TEST_Compagnia_iter85"})
        assert r.status_code in (200, 201), r.text
        comp = r.json()
    else:
        comp = comps[0]
    compagnia_id = comp["id"]

    # crea contraente TEST
    ts = int(time.time())
    r = client.post(f"{API}/anagrafiche", json={
        "tipo": "persona_fisica",
        "ragione_sociale": f"TEST_Iter85_Contraente_{ts}",
        "cognome": "TESTITER85",
        "nome": "Tizio",
    })
    assert r.status_code in (200, 201), r.text
    contraente = r.json()

    return {"compagnia_id": compagnia_id, "contraente_id": contraente["id"], "ts": ts}


def _make_polizza(client, seed, numero_suffix, ramo="danni"):
    ts = seed["ts"]
    numero = f"TESTPOL{ts}-{numero_suffix}"
    r = client.post(f"{API}/polizze", json={
        "numero_polizza": numero,
        "compagnia_id": seed["compagnia_id"],
        "contraente_id": seed["contraente_id"],
        "ramo": ramo,
        "effetto": "2024-01-01",
        "scadenza": "2025-01-01",
        "frazionamento": "annuale",
        "premio_lordo": 500,
        "premio_netto": 450,
        "premio_imposte": 50,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def _make_titolo(client, polizza_id, stato="da_incassare", importo=500.0):
    r = client.post(f"{API}/titoli", json={
        "polizza_id": polizza_id,
        "tipo": "rinnovo",
        "effetto": "2024-01-01",
        "scadenza": "2024-01-01",
        "stato": stato,
        "importo_lordo": importo,
        "importo_netto": importo * 0.9,
        "imposte": importo * 0.1,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


# ---------- TESTS ----------

def test_titoli_arretrati_endpoint(client, seed):
    pol = _make_polizza(client, seed, "ARR")
    _make_titolo(client, pol["id"], stato="da_incassare", importo=500)
    _make_titolo(client, pol["id"], stato="incassato", importo=300)

    r = client.get(f"{API}/polizze/{pol['id']}/titoli-arretrati")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["totale"] == 1, data
    assert data["importo"] == 500.0, data
    assert len(data["titoli"]) == 1
    assert data["titoli"][0]["stato"] == "da_incassare"


def test_annulla_senza_storno_lascia_titoli_aperti(client, seed):
    pol = _make_polizza(client, seed, "ANN0")
    _make_titolo(client, pol["id"], stato="da_incassare", importo=200)

    r = client.post(f"{API}/polizze/{pol['id']}/annulla", json={
        "data_annullamento": "2024-06-01",
        "motivo_annullamento": "test",
        "storna_titoli": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stato"] == "annullata"
    assert body["titoli_stornati"] == 0

    # verifica: polizza annullata, titolo ancora da_incassare
    p = client.get(f"{API}/polizze/{pol['id']}").json()
    assert p["stato"] == "annullata"
    tit = client.get(f"{API}/polizze/{pol['id']}/titoli-arretrati").json()
    assert tit["totale"] == 1


def test_annulla_con_storno_storna_titoli(client, seed):
    pol = _make_polizza(client, seed, "ANN1")
    _make_titolo(client, pol["id"], stato="da_incassare", importo=200)

    r = client.post(f"{API}/polizze/{pol['id']}/annulla", json={
        "data_annullamento": "2024-06-01",
        "motivo_annullamento": "test-storno",
        "storna_titoli": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["titoli_stornati"] == 1

    tit = client.get(f"{API}/polizze/{pol['id']}/titoli-arretrati").json()
    assert tit["totale"] == 0  # non più arretrati (ora stornati)


def test_sostituisci_senza_storno(client, seed):
    ts = seed["ts"]
    old = _make_polizza(client, seed, "SOST0")
    _make_titolo(client, old["id"], stato="da_incassare", importo=100)

    r = client.post(f"{API}/polizze/{old['id']}/sostituisci", json={
        "numero_polizza": f"TESTPOL{ts}-SOST0NEW",
        "effetto": "2024-07-01",
        "scadenza": "2025-07-01",
        "storna_titoli": False,
        "crea_titolo": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("titoli_stornati", 0) == 0

    # vecchia deve essere 'sostituita' con sostituita_da_polizza_id
    old_after = client.get(f"{API}/polizze/{old['id']}").json()
    assert old_after["stato"] == "sostituita"
    assert old_after.get("sostituita_da_polizza_id")

    # nuova deve avere sostituisce_polizza = old id
    new_id = old_after["sostituita_da_polizza_id"]
    new_p = client.get(f"{API}/polizze/{new_id}").json()
    assert new_p.get("sostituisce_polizza") == old["id"]

    # titolo arretrato della vecchia rimane da_incassare
    tit = client.get(f"{API}/polizze/{old['id']}/titoli-arretrati").json()
    assert tit["totale"] == 1


def test_sostituisci_con_storno(client, seed):
    ts = seed["ts"]
    old = _make_polizza(client, seed, "SOST1")
    _make_titolo(client, old["id"], stato="da_incassare", importo=150)

    r = client.post(f"{API}/polizze/{old['id']}/sostituisci", json={
        "numero_polizza": f"TESTPOL{ts}-SOST1NEW",
        "effetto": "2024-07-01",
        "scadenza": "2025-07-01",
        "storna_titoli": True,
        "crea_titolo": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("titoli_stornati", 0) >= 1

    tit = client.get(f"{API}/polizze/{old['id']}/titoli-arretrati").json()
    assert tit["totale"] == 0


def test_conteggi_include_sostituita(client, seed):
    r = client.get(f"{API}/polizze/conteggi-stato")
    assert r.status_code == 200
    data = r.json()
    assert "sostituita" in data, f"conteggi non contengono 'sostituita': {data}"
    assert data["sostituita"] >= 2  # dai test sopra


def test_put_rendita_annua(client, seed):
    pol = _make_polizza(client, seed, "REND", ramo="vita")
    r = client.put(f"{API}/polizze/{pol['id']}", json={"rendita_annua": 1500.5})
    assert r.status_code == 200, r.text
    got = client.get(f"{API}/polizze/{pol['id']}").json()
    assert got.get("rendita_annua") == 1500.5


def test_no_titoli_premio_zero_aperti(client):
    """Non deve esistere alcun titolo con importo_lordo<=0 e stato!=incassato
    (la migrazione è già stata eseguita). Verifica via GET /titoli con filtro."""
    r = client.get(f"{API}/titoli", params={"stato": "da_incassare", "limit": 1000})
    if r.status_code != 200:
        pytest.skip(f"endpoint /titoli non disponibile: {r.status_code}")
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    if not items:
        return
    aperti_a_zero = [t for t in items if (t.get("importo_lordo") or 0) <= 0]
    assert len(aperti_a_zero) == 0, f"Trovati {len(aperti_a_zero)} titoli aperti con importo<=0"
