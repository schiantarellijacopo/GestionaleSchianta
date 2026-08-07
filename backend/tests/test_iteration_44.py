"""Iteration 44 tests: template_riga, diario messaggio/rimanda, IBAN preview"""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ARSHAD_ID = "756628b6-9bf2-457e-9de1-688a30166c9f"
MODELLO_WA_ID = "b0c78bef-9688-4687-b5a4-02c597c776eb"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_iban_preview(h):
    r = requests.post(f"{API}/librerie/modelli/preview",
                      json={"corpo": "IBAN: {azienda_iban}", "canale": "email"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    print("preview:", body)
    # anteprima ritorna corpo risolto
    corpo = body.get("corpo") or body.get("body") or body.get("preview") or ""
    assert "IBAN:" in corpo
    assert "{azienda_iban}" not in corpo


def test_template_riga_persistito(h):
    # GET modello, verifica campo template_riga persiste
    r = requests.get(f"{API}/librerie/modelli/{MODELLO_WA_ID}", headers=h)
    assert r.status_code == 200, r.text
    m = r.json()
    assert "template_riga" in m
    print("template_riga:", m.get("template_riga"))


def test_diario_arshad_ha_voce_comunicazione(h):
    r = requests.get(f"{API}/anagrafiche/{ARSHAD_ID}/diario", headers=h)
    assert r.status_code == 200, r.text
    voci = r.json()
    assert isinstance(voci, list)
    comm = [v for v in voci if v.get("payload", {}).get("storico_avvisi_id")]
    assert len(comm) > 0, "Nessuna voce comunicazione in diario ARSHAD"
    print(f"Voci comunicazione: {len(comm)}, esempio: {comm[0].get('titolo')} canale={comm[0].get('payload',{}).get('canale')}")
    # save for other tests
    pytest.diario_comm = comm[0]


def test_diario_messaggio_endpoint(h):
    r = requests.get(f"{API}/anagrafiche/{ARSHAD_ID}/diario", headers=h)
    voci = r.json()
    comm = [v for v in voci if v.get("payload", {}).get("storico_avvisi_id")]
    assert comm
    did = comm[0]["id"]
    r = requests.get(f"{API}/diario/{did}/messaggio", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    print("messaggio:", {k: (v[:80] if isinstance(v, str) else v) for k, v in d.items()})
    assert "messaggio" in d or "corpo" in d or "contenuto" in d
    assert "destinatario" in d
    assert "canale" in d


def test_diario_rimanda_returns_no_500(h):
    """POST /api/diario/{id}/rimanda deve rispondere senza 500"""
    r = requests.get(f"{API}/anagrafiche/{ARSHAD_ID}/diario", headers=h)
    voci = r.json()
    comm = [v for v in voci if v.get("payload", {}).get("storico_avvisi_id") and v.get("payload", {}).get("canale") == "whatsapp"]
    if not comm:
        pytest.skip("no whatsapp comm voci")
    did = comm[0]["id"]
    # Testing with a fake dest to avoid real send: we don't override, just call
    # Actually per request, no real WA sending needed. But endpoint may attempt real send.
    # We just verify it doesn't 500.
    r = requests.post(f"{API}/diario/{did}/rimanda",
                      json={"destinatario_override": "+390000000000"}, headers=h)
    print(f"rimanda status={r.status_code} body={r.text[:200]}")
    assert r.status_code != 500, f"Server error: {r.text}"
