"""Iter17 - P0 refactor regression tests.

Verifies:
- Backend boots after auth.py/server.py circular-import refactor (db lives in database.py).
- Auth login still works.
- KPI/dashboard/contabilita endpoints work after removal of unused vars (week_end,
  crediti_agg/crediti_storno unused, today unused).
- Helpers _calcola_scadenza_titolo / _CORPO_LETTERA_DEFAULT / _MESI_PER_FRAZIONAMENTO
  are referenced correctly by sostituisci_polizza and avvisi/pdf-bulk routes.
- PUT /api/polizze/{pid} accepts and persists the new RCA edit fields.
"""
import os
import datetime as dt
import pathlib
import pytest
import requests

from conftest import API, ADMIN_EMAIL, ADMIN_PASSWORD  # type: ignore


# ----------------------------- code-level invariants --------------------------
BACKEND_DIR = pathlib.Path("/app/backend")


def test_database_module_exists_and_exports_db():
    """database.py must exist and expose client+db (single source of truth)."""
    p = BACKEND_DIR / "database.py"
    assert p.exists(), "database.py is missing"
    text = p.read_text()
    assert "AsyncIOMotorClient" in text
    assert "db = client[" in text


def test_auth_no_longer_imports_from_server():
    """auth.py must import db from database (not late-import from server)."""
    text = (BACKEND_DIR / "auth.py").read_text()
    assert "from server import" not in text, "auth.py still does late import from server"
    assert "from database import db" in text


def test_server_imports_from_database():
    text = (BACKEND_DIR / "server.py").read_text()
    assert "from database import" in text


# ----------------------------- auth & smoke -----------------------------------
@pytest.fixture(scope="module")
def session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    # access_token is also returned in response body (besides cookie)
    assert "access_token" in body or body.get("ok") is True
    return s


def test_admin_login(session):
    r = session.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200
    me = r.json()
    assert me.get("email") == ADMIN_EMAIL
    assert me.get("role") == "admin"


# ----------------------------- anagrafiche/stats ------------------------------
def test_anagrafiche_stats_categoria_split(session):
    r = session.get(f"{API}/anagrafiche/stats", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("privati", "aziende", "condomini", "parrocchie", "totale"):
        assert k in data, f"missing key {k} in stats response: {data}"
        v = data[k]
        # may be int (count) or dict({n, premio_totale}) - both are acceptable shapes
        if isinstance(v, dict):
            assert "n" in v
        else:
            assert isinstance(v, int)


# ----------------------------- dashboard/tasks (week_end fix) -----------------
def test_dashboard_tasks_no_nameerror(session):
    r = session.get(f"{API}/dashboard/tasks", timeout=20)
    assert r.status_code == 200, f"NameError or other failure: {r.status_code} {r.text}"
    data = r.json()
    # response may be a list of task dicts or a dict keyed by task name
    keys = set()
    if isinstance(data, list):
        keys = {t.get("key") for t in data if isinstance(t, dict)}
    elif isinstance(data, dict):
        keys = set(data.keys())
    expected_any = {
        "compleanno_oggi", "compleanno_settimana",
        "titoli_sospesi", "titoli_sospesi_old",
        "polizze_scadenza", "polizze_in_scadenza_30",
        "documenti_scaduti", "documenti_scadenza",
    }
    assert keys & expected_any, f"none of expected keys present: {list(keys)[:20]}"


# ----------------------------- contabilita/brogliaccio ------------------------
def test_contabilita_brogliaccio_smoke(session):
    today = dt.date.today().isoformat()
    r = session.get(f"{API}/contabilita/brogliaccio", params={"data": today}, timeout=20)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), dict)


def test_contabilita_dati_compagnie_smoke(session):
    r = session.get(f"{API}/contabilita/dati-compagnie",
                    params={"dal": "2025-01-01", "al": "2025-12-31"}, timeout=20)
    assert r.status_code == 200, r.text
    # response is a list of compagnie aggregates
    assert isinstance(r.json(), (list, dict))


# ----------------------------- helper unit -------------------------------------
def test_calcola_scadenza_titolo_helper():
    """Direct unit test on the new helper (imported from server)."""
    import sys
    sys.path.insert(0, "/app/backend")
    from server import _calcola_scadenza_titolo  # type: ignore

    assert _calcola_scadenza_titolo("2025-01-15", "annuale") == "2026-01-15"
    assert _calcola_scadenza_titolo("2025-01-15", "semestrale") == "2025-07-15"
    assert _calcola_scadenza_titolo("2025-01-15", "trimestrale") == "2025-04-15"
    assert _calcola_scadenza_titolo("2025-01-15", "mensile") == "2025-02-15"
    # fine mese
    assert _calcola_scadenza_titolo("2025-01-31", "mensile") == "2025-02-28"
    # invalid input
    assert _calcola_scadenza_titolo(None, "annuale") is None
    assert _calcola_scadenza_titolo("bad-date", "annuale") is None


# ----------------------------- sostituisci polizza ----------------------------
def _get_first_active_polizza(session, ramo: str | None = None) -> dict | None:
    params = {"limit": 50}
    if ramo:
        params["ramo"] = ramo
    r = session.get(f"{API}/polizze", params=params, timeout=20)
    assert r.status_code == 200, r.text
    rows = r.json()
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or []
    for p in rows:
        if p.get("stato") == "attiva":
            return p
    return None


def test_sostituisci_polizza_creates_titolo_with_scadenza(session):
    pol = _get_first_active_polizza(session)
    if not pol:
        pytest.skip("No active polizza found to test sostituisci")
    pid = pol["id"]

    today = dt.date.today()
    effetto = today.isoformat()
    new_num = f"TEST_SUB_{int(today.strftime('%Y%m%d'))}_{pid[:6]}"

    body = {
        "numero_polizza": new_num,
        "effetto": effetto,
        "scadenza": (today.replace(year=today.year + 1)).isoformat(),
        "frazionamento": "semestrale",
        "premio_lordo": 100.0,
        "premio_netto": 80.0,
        "premio_imposte": 20.0,
        "crea_titolo": True,
        "motivo": "TEST_iter17_refactor",
    }
    r = session.post(f"{API}/polizze/{pid}/sostituisci", json=body, timeout=20)
    assert r.status_code in (200, 201), f"sostituisci failed: {r.status_code} {r.text}"
    data = r.json()
    new_pid = data.get("nuova_polizza_id")
    tid = data.get("titolo_id")
    assert new_pid, "missing nuova_polizza_id"
    assert tid, "missing titolo_id (crea_titolo=True must create a titolo)"

    # Fetch titolo and verify scadenza
    rt = session.get(f"{API}/titoli", params={"polizza_id": new_pid}, timeout=15)
    assert rt.status_code == 200
    titoli = rt.json()
    if isinstance(titoli, dict):
        titoli = titoli.get("items") or titoli.get("data") or []
    target = next((t for t in titoli if t.get("id") == tid), None)
    assert target is not None, f"new titolo {tid} not found"
    assert target.get("scadenza"), "titolo scadenza missing"
    # semestrale -> +6 months
    expected = (today.replace(month=((today.month - 1 + 6) % 12) + 1,
                              year=today.year + ((today.month - 1 + 6) // 12)))
    # tolerate fine-mese clamp difference but check year-month
    assert target["scadenza"][:7] == expected.isoformat()[:7], (
        f"scadenza {target['scadenza']} not in expected month {expected}")

    # Cleanup: mark substituted policy as TEST cleanup tag (do not delete actual policies)
    # The substituted-from policy was set to stato='sostituita' by the endpoint.


# ----------------------------- avvisi/pdf-bulk (uses _CORPO_LETTERA_DEFAULT) --
def test_avvisi_pdf_bulk_no_nameerror(session):
    """The endpoint must reach validation before failing.

    We send an empty titoli_ids to force a 400 (validated path) instead of a 500
    NameError on _CORPO_LETTERA_DEFAULT. Then we also send invalid ids to force the
    404 branch which still touches _CORPO_LETTERA_DEFAULT.
    """
    r = session.post(f"{API}/avvisi/pdf-bulk", json={"titoli_ids": []}, timeout=15)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    # Now exercise the path that uses _CORPO_LETTERA_DEFAULT in body resolution
    r2 = session.post(f"{API}/avvisi/pdf-bulk",
                      json={"titoli_ids": ["___nonexistent___"]}, timeout=15)
    assert r2.status_code == 404, f"expected 404, got {r2.status_code}: {r2.text}"


# ----------------------------- polizza GET + PUT edit fields ------------------
NEW_EDIT_FIELDS = {
    "veicolo_quintali": 18,
    "veicolo_gancio_traino": True,
    "veicolo_targa_rimorchio": "TEST_RM123",
    "tipo_tariffa": "bonus_malus",
    "bm_provenienza": "CU 6",
    "bm_assegnata": "CU 5",
    "bm_assegnata_cu": "5",
    "pejus": "10%",
    "franchigia": "500€",
    "valore_veicolo": 12000.0,
    "valore_residuo_veicolo": 8000.0,
    "valore_accessori": 1500.0,
    "guida_esperta": True,
    "guida_esclusiva": False,
    "rinuncia_rivalsa": True,
    "intestatario": "TEST_iter17 Mario Rossi",
    "provincia_intestatario": "MI",
    "massimali": "6 mln",
}


def test_put_polizza_persists_new_edit_fields(session):
    pol = _get_first_active_polizza(session, ramo="rca") or _get_first_active_polizza(session)
    if not pol:
        pytest.skip("No polizza found to test PUT")
    pid = pol["id"]

    # GET before to verify endpoint OK and capture original values
    r0 = session.get(f"{API}/polizze/{pid}", timeout=15)
    assert r0.status_code == 200, r0.text
    original = r0.json()
    backup = {k: original.get(k) for k in NEW_EDIT_FIELDS}

    try:
        r = session.put(f"{API}/polizze/{pid}", json=NEW_EDIT_FIELDS, timeout=15)
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text}"

        # GET after to verify persistence
        r2 = session.get(f"{API}/polizze/{pid}", timeout=15)
        assert r2.status_code == 200
        after = r2.json()
        for k, v in NEW_EDIT_FIELDS.items():
            assert after.get(k) == v, f"field {k}: expected {v!r}, got {after.get(k)!r}"
    finally:
        # restore original values to keep the DB clean
        session.put(f"{API}/polizze/{pid}", json=backup, timeout=15)
