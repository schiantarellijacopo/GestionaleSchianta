"""Iter19 - Tests for server.py partial split + KPI Anagrafiche custom (P1)."""
import io
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PWD = "Admin123!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return s


# ------------------------------------------------------------------
# Section 1: Endpoint smoke (still 200 after split)
# ------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/auth/me",
    "/api/anagrafiche/stats",
    "/api/dashboard/tasks",
    "/api/dashboard/links",
    "/api/polizze",
    "/api/titoli",
    "/api/contabilita/brogliaccio?data=2026-06-25",
    "/api/avvisi-scadenze/preview",
    "/api/anagrafiche/kpi-custom",
])
def test_endpoint_200(session, path):
    r = session.get(f"{BASE_URL}{path}", timeout=20)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


# ------------------------------------------------------------------
# Section 2: Dashboard router (extracted module)
# ------------------------------------------------------------------
def test_dashboard_tasks_8_keys(session):
    r = session.get(f"{BASE_URL}/api/dashboard/tasks", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 8
    keys = {t["key"] for t in data}
    expected = {
        "compleanno_oggi", "compleanno_settimana", "documenti_scaduti",
        "documenti_scadenza", "titoli_sospesi_old", "polizze_in_scadenza_30",
        "sinistri_aperti_old", "provvigioni_da_pagare",
    }
    assert keys == expected
    for t in data:
        assert "label" in t and "count" in t and "url" in t
        assert isinstance(t["count"], int)


def test_dashboard_links_crud(session):
    # CREATE
    body = {"label": "TEST_iter19", "url": "test-iter19.local", "ordine": 99}
    r = session.post(f"{BASE_URL}/api/dashboard/links", json=body, timeout=15)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["label"] == "TEST_iter19"
    assert created["url"].startswith("https://")
    lid = created["id"]
    # LIST
    r = session.get(f"{BASE_URL}/api/dashboard/links", timeout=15)
    assert r.status_code == 200
    assert any(l["id"] == lid for l in r.json())
    # UPDATE
    body2 = {"label": "TEST_iter19_upd", "url": "https://updated.example", "ordine": 1}
    r = session.put(f"{BASE_URL}/api/dashboard/links/{lid}", json=body2, timeout=15)
    assert r.status_code == 200
    assert r.json()["label"] == "TEST_iter19_upd"
    # DELETE
    r = session.delete(f"{BASE_URL}/api/dashboard/links/{lid}", timeout=15)
    assert r.status_code == 200
    # 404 after delete
    r = session.delete(f"{BASE_URL}/api/dashboard/links/{lid}", timeout=15)
    assert r.status_code == 404


# ------------------------------------------------------------------
# Section 3: OCR router (extracted module)
# ------------------------------------------------------------------
def test_ocr_libretto_route_reachable(session):
    """The OCR route must exist via the new router. 503 (Gemini missing/error)
    is OK; we only verify the route is registered (not 404)."""
    # Tiny 4x4 JPEG built via PIL
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not available")
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 255, 255)).save(buf, format="JPEG")
    files = {"file": ("t.jpg", io.BytesIO(buf.getvalue()), "image/jpeg")}
    r = session.post(f"{BASE_URL}/api/ocr/libretto", files=files, timeout=60)
    # Route exists if status is NOT 404. Accept 200 / 400 / 503.
    assert r.status_code != 404, "OCR route /api/ocr/libretto not registered!"
    assert r.status_code in (200, 400, 503), f"Unexpected: {r.status_code} {r.text[:200]}"


def test_ocr_libretto_apply_route_reachable(session):
    """OCR apply endpoint route must be registered."""
    r = session.post(f"{BASE_URL}/api/ocr/libretto/apply",
                     json={"polizza_id": "non-existent-xyz", "dati": {}, "campi": []},
                     timeout=15)
    assert r.status_code != 404 or "Polizza" in r.text, \
        f"Route may not be registered: {r.status_code}"
    # We expect 400 (no polizza_id) or 404 (polizza not found)
    assert r.status_code in (400, 404), f"Unexpected: {r.status_code} {r.text[:200]}"


# ------------------------------------------------------------------
# Section 4: KPI Anagrafiche custom (P1)
# ------------------------------------------------------------------
def test_kpi_custom_crud(session):
    # LIST (empty or any)
    r = session.get(f"{BASE_URL}/api/anagrafiche/kpi-custom", timeout=15)
    assert r.status_code == 200
    initial = r.json()
    assert isinstance(initial, list)
    # CREATE
    body = {"label": "TEST_KPI_iter19", "tag": "test_iter19_tag",
            "color": "emerald", "icon": "Star"}
    r = session.post(f"{BASE_URL}/api/anagrafiche/kpi-custom", json=body, timeout=15)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["label"] == "TEST_KPI_iter19"
    assert created["tag"] == "test_iter19_tag"
    assert created["color"] == "emerald"
    assert "id" in created
    kid = created["id"]
    # LIST contains created
    r = session.get(f"{BASE_URL}/api/anagrafiche/kpi-custom", timeout=15)
    assert any(k["id"] == kid for k in r.json())
    # DELETE
    r = session.delete(f"{BASE_URL}/api/anagrafiche/kpi-custom/{kid}", timeout=15)
    assert r.status_code == 200
    # 404 after delete
    r = session.delete(f"{BASE_URL}/api/anagrafiche/kpi-custom/{kid}", timeout=15)
    assert r.status_code == 404


def test_kpi_custom_validation(session):
    # Missing label
    r = session.post(f"{BASE_URL}/api/anagrafiche/kpi-custom",
                     json={"label": "", "tag": "x"}, timeout=15)
    assert r.status_code == 400
    # Missing tag
    r = session.post(f"{BASE_URL}/api/anagrafiche/kpi-custom",
                     json={"label": "X", "tag": ""}, timeout=15)
    assert r.status_code == 400


def test_anagrafiche_stats_has_custom_array(session):
    """Per review: GET /api/anagrafiche/stats deve includere 'custom' array
    con {id,label,tag,color,icon,n,premio_totale}."""
    # Create a custom KPI first
    body = {"label": "TEST_STATS_KPI", "tag": "test_stats_iter19",
            "color": "sky", "icon": "Star"}
    r = session.post(f"{BASE_URL}/api/anagrafiche/kpi-custom", json=body, timeout=15)
    assert r.status_code == 201
    kid = r.json()["id"]
    try:
        r = session.get(f"{BASE_URL}/api/anagrafiche/stats", timeout=20)
        assert r.status_code == 200
        data = r.json()
        # Standard keys
        for k in ("privati", "aziende", "condomini", "parrocchie", "totale"):
            assert k in data, f"missing {k}"
        # Custom array (per review request)
        assert "custom" in data, \
            f"'custom' array missing from /api/anagrafiche/stats. Keys: {list(data.keys())}"
        assert isinstance(data["custom"], list)
        # The newly created KPI should appear
        ids = [c.get("id") for c in data["custom"]]
        assert kid in ids, f"Created KPI {kid} not in custom array"
        # Schema check on the matching one
        match = next(c for c in data["custom"] if c.get("id") == kid)
        for k in ("id", "label", "tag", "color", "icon", "n", "premio_totale"):
            assert k in match, f"missing key {k} in custom entry"
    finally:
        session.delete(f"{BASE_URL}/api/anagrafiche/kpi-custom/{kid}", timeout=15)
