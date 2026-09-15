"""Test end-to-end: KPI Contabilità/Anagrafiche, Tag su Anagrafiche/Polizze/Titoli, autocomplete."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
ADMIN = {"email": "admin@assicura.it", "password": "Admin123!"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# --- KPI Contabilità ---
def test_kpi_prima_nota(client):
    r = client.get(f"{BASE_URL}/api/kpi/prima_nota/stats", timeout=15)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    if isinstance(data, dict):
        data = data.get("default", data)
    assert isinstance(data, list) and len(data) == 4, f"attese 4 card, ottenute: {data}"
    labels = [c["label"] for c in data]
    assert "Movimenti mese" in labels
    assert "Entrate mese" in labels
    assert "Uscite mese" in labels
    assert "Saldo mese" in labels
    for c in data:
        assert c["value"] is not None
        assert "NaN" not in str(c["value"])


def test_kpi_anagrafiche(client):
    for sez in ("polizze", "titoli", "sinistri", "avvisi", "prima_nota"):
        r = client.get(f"{BASE_URL}/api/kpi/{sez}/stats", timeout=15)
        assert r.status_code == 200, f"{sez}: {r.status_code} {r.text[:100]}"


# --- Anagrafiche stats ---
def test_anagrafiche_list(client):
    r = client.get(f"{BASE_URL}/api/anagrafiche?limit=5", timeout=15)
    assert r.status_code == 200, r.text[:200]


def test_anagrafiche_tags_endpoint(client):
    r = client.get(f"{BASE_URL}/api/anagrafiche/tags", timeout=15)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert isinstance(data, list), f"tags list expected, got {type(data)}"


# --- Tag Polizza CRUD ---
@pytest.fixture(scope="module")
def polizza_id(client):
    r = client.get(f"{BASE_URL}/api/polizze?limit=1", timeout=15)
    assert r.status_code == 200
    items = r.json()
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    assert items, "no polizza found"
    return items[0]["id"]


def test_polizza_tags_add_persist_remove(client, polizza_id):
    # Add
    r = client.put(f"{BASE_URL}/api/polizze/{polizza_id}/tags", json={"tags": ["TEST_vip", "Test Spazio"]}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert "test_vip" in data["tags"]
    assert "test_spazio" in data["tags"], f"normalizzazione fallita: {data}"

    # Persist via GET polizza
    r2 = client.get(f"{BASE_URL}/api/polizze/{polizza_id}", timeout=15)
    assert r2.status_code == 200
    assert "test_vip" in (r2.json().get("tags") or [])

    # Verifica autocomplete include tag polizza
    r3 = client.get(f"{BASE_URL}/api/anagrafiche/tags", timeout=15)
    assert r3.status_code == 200
    assert "test_vip" in r3.json(), "autocomplete non include tag polizza"

    # Remove
    r4 = client.put(f"{BASE_URL}/api/polizze/{polizza_id}/tags", json={"tags": []}, timeout=15)
    assert r4.status_code == 200
    assert r4.json()["tags"] == []


# --- Tag Titolo CRUD ---
@pytest.fixture(scope="module")
def titolo_id(client):
    r = client.get(f"{BASE_URL}/api/titoli?limit=5", timeout=15)
    assert r.status_code == 200
    items = r.json()
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    assert items, "no titolo found"
    return items[0]["id"]


def test_titolo_tags_add_persist_remove(client, titolo_id):
    r = client.put(f"{BASE_URL}/api/titoli/{titolo_id}/tags", json={"tags": ["TEST_urgente"]}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    assert "test_urgente" in r.json()["tags"]

    # Verifica persistenza via list endpoint (GET /titoli/{id} restituisce 405 - endpoint singolo non esposto)
    lst = client.get(f"{BASE_URL}/api/titoli?limit=200", timeout=15).json()
    items = lst if isinstance(lst, list) else (lst.get("items") or lst.get("data") or [])
    found = [x for x in items if x.get("id") == titolo_id]
    if found:
        assert "test_urgente" in (found[0].get("tags") or []), "tag titolo non persistito"

    r3 = client.get(f"{BASE_URL}/api/anagrafiche/tags", timeout=15)
    assert "test_urgente" in r3.json(), "autocomplete non include tag titolo"

    # Verifica anche update via PUT /titoli/{id} (payload completo con campo tags)
    r4 = client.put(f"{BASE_URL}/api/titoli/{titolo_id}", json={"tags": ["test_via_full_update"]}, timeout=15)
    assert r4.status_code == 200
    assert "test_via_full_update" in (r4.json().get("tags") or []), "tags non persistito via PUT completo"

    # cleanup
    client.put(f"{BASE_URL}/api/titoli/{titolo_id}/tags", json={"tags": []}, timeout=15)


# --- Tag Anagrafica CRUD (esistente) ---
def test_anagrafica_tags_flow(client):
    r = client.get(f"{BASE_URL}/api/anagrafiche?limit=1", timeout=15)
    items = r.json()
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    if not items:
        pytest.skip("no anagrafica")
    aid = items[0]["id"]
    # PUT tags via patch anagrafica
    orig_tags = items[0].get("tags") or []
    r2 = client.put(f"{BASE_URL}/api/anagrafiche/{aid}", json={"tags": orig_tags + ["TEST_ana"]}, timeout=15)
    assert r2.status_code in (200, 204), r2.text[:200]
    r3 = client.get(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=15)
    assert r3.status_code == 200
    tags_after = r3.json().get("tags") or []
    assert any("test_ana" in str(t).lower() for t in tags_after), f"tag anagrafica non salvato: {tags_after}"
    # cleanup
    client.put(f"{BASE_URL}/api/anagrafiche/{aid}", json={"tags": orig_tags}, timeout=15)
