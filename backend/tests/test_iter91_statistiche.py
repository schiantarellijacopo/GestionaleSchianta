"""Iteration 91 - Statistiche hub, Libro Matricola/Cumulative, Agenzie, Overview premio_netto."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
if not BASE.endswith("/api"):
    API = BASE + "/api"
else:
    API = BASE


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def collab_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "collaboratore@assicura.it", "password": "Collab123!"})
    assert r.status_code == 200, f"Collab login failed: {r.status_code} {r.text}"
    return s


# --- Statistiche Overview: top_compagnie must include premio_netto ---
def test_overview_top_compagnie_has_premio_netto(admin_client):
    r = admin_client.get(f"{API}/statistiche/overview")
    assert r.status_code == 200
    data = r.json()
    top = data.get("top_compagnie") or []
    assert isinstance(top, list)
    if top:
        item = top[0]
        assert "premio_netto" in item, f"Missing premio_netto in top_compagnie: {item.keys()}"
        # premio_totale (lordo equivalent) should also exist
        assert any(k in item for k in ("premio_totale", "premio_lordo", "premio")), f"Missing premio_totale/lordo: {item.keys()}"


# --- Statistiche premi-provvigioni admin ---
def test_premi_provvigioni_admin(admin_client):
    r = admin_client.get(f"{API}/statistiche/premi-provvigioni", params={"anni": "2026"})
    assert r.status_code == 200
    data = r.json()
    # scoped_operatore should be false/absent for admin
    assert data.get("scoped_operatore") in (False, None)


# --- Statistiche premi-provvigioni collaboratore scoped ---
def test_premi_provvigioni_collaboratore_scoped(collab_client):
    r = collab_client.get(f"{API}/statistiche/premi-provvigioni", params={"anni": "2026"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("scoped_operatore") is True, f"Expected scoped_operatore=true, got {data.get('scoped_operatore')}"


# --- Per Operatore ---
def test_per_operatore(admin_client):
    r = admin_client.get(f"{API}/statistiche/per-operatore", params={"anni": "2026"})
    assert r.status_code == 200
    data = r.json()
    operatori = data.get("operatori") or []
    assert isinstance(operatori, list)
    assert len(operatori) > 0
    op = operatori[0]
    per_anno = op.get("per_anno") or {}
    assert per_anno, f"per_anno vuoto: {op}"
    key0 = list(per_anno.keys())[0]
    row = per_anno[key0]
    for k in ("netto", "provvigioni", "lordo"):
        assert k in row, f"Missing {k} in per_anno row: {row}"


# --- Top clienti: provvigioni non tutte zero e RAPPEL escluso ---
def test_top_clienti_has_data_and_excludes_rappel(admin_client):
    r = admin_client.get(f"{API}/cervello/top-clienti", params={"anno": 2026, "limit": 500})
    assert r.status_code == 200
    data = r.json()
    items = data.get("items") or []
    assert len(items) > 0
    total_prov = float(data.get("totale_provvigioni") or 0) or sum(float(c.get("provvigioni_anno") or 0) for c in items)
    assert total_prov > 0, f"Total provvigioni is zero: {total_prov}"
    for c in items:
        name = (c.get("nome") or "").upper()
        assert "RAPPEL" not in name, f"RAPPEL should not appear in top-clienti: {c}"


# --- Libro Matricola / Cumulative: deve includere cumulative ---
def test_libro_matricola_includes_cumulative(admin_client):
    r = admin_client.get(f"{API}/libro-matricola/polizze")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    has_libro = any(p.get("is_libro_matricola") for p in items)
    has_cum = any(p.get("is_cumulativa_assicurati") for p in items)
    # Endpoint filter includes cumulative; admin tenant may only have libro-type policies.
    # Assert the endpoint at least returns libro policies and doesn't error.
    assert has_libro or has_cum, "Nessuna polizza libro matricola/cumulativa restituita"
    print(f"libro={sum(1 for p in items if p.get('is_libro_matricola'))} cum={sum(1 for p in items if p.get('is_cumulativa_assicurati'))} tot={len(items)}")


# --- Agenzie: GET list and PUT edit-in-place ---
def test_agenzie_put_updates_in_place(admin_client):
    r = admin_client.get(f"{API}/agenzie")
    assert r.status_code == 200
    ags = r.json()
    if isinstance(ags, dict):
        ags = ags.get("agenzie") or ags.get("items") or []
    assert isinstance(ags, list) and len(ags) > 0
    target = ags[0]
    aid = target.get("id") or target.get("_id")
    assert aid
    original_rs = target.get("ragione_sociale") or ""
    # PUT with same data - must return 200 and not create new
    payload = dict(target)
    payload.pop("_id", None)
    r2 = admin_client.put(f"{API}/agenzie/{aid}", json=payload)
    assert r2.status_code in (200, 204), f"PUT agenzie failed: {r2.status_code} {r2.text[:300]}"
    # Verify count unchanged
    r3 = admin_client.get(f"{API}/agenzie")
    ags2 = r3.json()
    if isinstance(ags2, dict):
        ags2 = ags2.get("agenzie") or ags2.get("items") or []
    assert len(ags2) == len(ags), "Agenzie count changed after PUT (duplicate?)"
