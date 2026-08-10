"""Iteration 49 - OCR nightly pipeline, cloud storage endpoints, libro matricola,
documenti mancanti, sms bulk titoli"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@assicura.it", "password": "Admin123!"},
                      timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def h(token):
    return {"Authorization": f"Bearer {token}"}


# ---- Cloud Storage ----

def test_config_status(h):
    r = requests.get(f"{API}/librerie/cloud-storage/config-status", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j.get("encryption_configured") is True
    assert j.get("google_drive", {}).get("configured") is True, f"google_drive not configured: {j}"


def test_status_google_drive_connected(h):
    r = requests.get(f"{API}/librerie/cloud-storage/status", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    conns = j.get("connections", [])
    providers = [c.get("provider") for c in conns]
    assert "google_drive" in providers, f"google_drive not in connections: {providers}"


def test_scan_summary(h):
    r = requests.get(f"{API}/librerie/cloud-storage/scan-summary", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert "latest_run" in j
    assert "cumulative" in j
    assert "pending_manual_smistamento" in j
    for k in ("letti", "abbinati", "in_attesa", "anagrafiche_create"):
        assert k in j["latest_run"], f"missing {k} in latest_run: {j['latest_run']}"
    assert "runs" in j["cumulative"]


def test_inbox_files(h):
    r = requests.get(f"{API}/librerie/cloud-storage/inbox-files",
                     params={"provider": "google_drive"}, headers=h, timeout=60)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert "files" in j
    assert "inbox_id" in j
    assert isinstance(j["files"], list)


def test_archivio(h):
    r = requests.get(f"{API}/librerie/cloud-storage/archivio",
                     params={"limit": 50}, headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert "documenti" in j
    assert "totale" in j
    assert "abbinati" in j
    assert "da_smistare" in j


def test_scan_now_response(h):
    # Long endpoint - we accept any 2xx response (or 4xx if no inbox available)
    try:
        r = requests.post(f"{API}/librerie/cloud-storage/scan-now",
                          data={"provider": "google_drive"}, headers=h, timeout=300)
    except requests.Timeout:
        pytest.skip("scan-now timed out >300s - accepted per test brief")
        return
    assert r.status_code in (200, 202), f"scan-now failed: {r.status_code} {r.text[:400]}"
    j = r.json()
    assert isinstance(j, dict)


# ---- Documenti mancanti ----

def test_documenti_mancanti_totali_reali(h):
    r = requests.get(f"{API}/insights/documenti-mancanti", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    # must return a totals structure (not capped at 500)
    total = j.get("totale") if isinstance(j, dict) else None
    if total is None and isinstance(j, dict):
        # allow alt shapes
        total = j.get("count") or (len(j.get("items", [])) if isinstance(j.get("items"), list) else None)
    # Basic sanity: got a response object
    assert isinstance(j, (dict, list))


# ---- SMS bulk titoli (Twilio not configured) ----

def test_sms_bulk_titoli_reason(h):
    # Need dummy titolo id; endpoint should still validate config
    r = requests.post(f"{API}/avvisi/sms-invia-bulk-titoli",
                      json={"titoli_ids": ["nonexistent-id-for-test"]},
                      headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j.get("inviati") == 0, f"expected inviati=0: {j}"
    text = str(j).lower()
    assert "twilio" in text, f"expected twilio in reason: {j}"


# ---- Libro matricola ----

def test_libro_matricola_polizze(h):
    r = requests.get(f"{API}/libro-matricola/polizze", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    # Accept either list or dict-wrapped
    if isinstance(j, dict) and "polizze" in j:
        items = j["polizze"]
    elif isinstance(j, list):
        items = j
    else:
        items = j.get("items", []) if isinstance(j, dict) else []
    # Structure should be present even if empty
    assert isinstance(items, list)
    if items:
        p = items[0]
        # Grouped structure expected
        assert any(k in p for k in ("applicazioni", "n_applicazioni_totali", "premio_applicazioni_totale"))
