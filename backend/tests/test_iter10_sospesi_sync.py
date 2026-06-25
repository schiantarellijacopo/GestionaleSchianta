"""Iter10 backend tests:
1. Sospesi sync between /titoli/sospesi and /contabilita/brogliaccio (riepilogo_kpi.crediti
   + liquidita.sospesi_attivi must equal sum of importo_lordo of /titoli/sospesi)
2. POST /titoli/{id}/incassa with tipo_chiusura='sconto' creates sconto_cliente uscita
3. POST /titoli/{id}/incassa with tipo_chiusura='sospeso' creates new titolo residuo
4. Invalid tipo_chiusura -> 400
5. Avvisi di Scadenza preview / esegui / log endpoints
"""
import os
import datetime as dt
import pytest
import requests

def _read_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # Fallback: read from /app/frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL="):
                    return line.strip().split("=", 1)[1].rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _read_backend_url()
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")},
               timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# --- 1. Sospesi sync -----------------------------------------------------
class TestSospesiSync:
    def test_brogliaccio_kpi_matches_titoli_sospesi(self, session):
        today = dt.date.today().isoformat()
        titoli = session.get(f"{API}/titoli/sospesi", timeout=30).json()
        assert isinstance(titoli, list)
        total_titoli = round(sum(float(t.get("importo_lordo") or 0) for t in titoli), 2)

        br = session.get(f"{API}/contabilita/brogliaccio?data={today}", timeout=60).json()
        assert "riepilogo_kpi" in br and "liquidita" in br

        kpi_crediti = round(float(br["riepilogo_kpi"]["crediti"]), 2)
        liq_sospesi = round(float(br["liquidita"]["sospesi_attivi"]), 2)

        # Both must equal the titoli sospesi total
        assert kpi_crediti == total_titoli, (
            f"riepilogo_kpi.crediti={kpi_crediti} != sum(titoli.importo_lordo)={total_titoli}")
        assert liq_sospesi == total_titoli, (
            f"liquidita.sospesi_attivi={liq_sospesi} != sum(titoli.importo_lordo)={total_titoli}")


# --- helper to create a fresh test titolo --------------------------------
def _create_test_titolo(session, lordo=300.0):
    """Create polizza + titolo da_incassare coperto. Returns (polizza_id, titolo_id)."""
    # Pick first available compagnia + an anagrafica
    comps = session.get(f"{API}/compagnie", timeout=20).json()
    assert comps, "Need at least one compagnia in DB"
    anas = session.get(f"{API}/anagrafiche?limit=1", timeout=20).json()
    assert anas, "Need at least one anagrafica"

    pol_body = {
        "numero_polizza": f"TEST_iter10_{dt.datetime.now().timestamp():.0f}",
        "ramo": "RC Auto",
        "compagnia_id": comps[0]["id"],
        "contraente_id": anas[0]["id"],
        "effetto": dt.date.today().isoformat(),
        "decorrenza": dt.date.today().isoformat(),
        "scadenza": (dt.date.today() + dt.timedelta(days=365)).isoformat(),
        "premio_lordo": lordo,
        "stato": "attiva",
    }
    r = session.post(f"{API}/polizze", json=pol_body, timeout=30)
    assert r.status_code in (200, 201), f"create polizza failed: {r.status_code} {r.text}"
    pol = r.json()
    pol_id = pol["id"]

    titolo_body = {
        "polizza_id": pol_id,
        "tipo": "nuova",
        "effetto": dt.date.today().isoformat(),
        "scadenza": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
        "stato": "da_incassare",
        "importo_lordo": lordo,
        "importo_netto": lordo,
        "imposte": 0.0,
        "provvigioni": 0.0,
        "titolo_coperto": True,
        "data_copertura": dt.date.today().isoformat(),
    }
    r = session.post(f"{API}/titoli", json=titolo_body, timeout=30)
    assert r.status_code in (200, 201), f"create titolo failed: {r.status_code} {r.text}"
    titolo = r.json()
    return pol_id, titolo["id"]


# --- 2. Incasso flow sconto ---------------------------------------------
class TestIncassoSconto:
    def test_incasso_partial_sconto_creates_uscita(self, session):
        pol_id, tid = _create_test_titolo(session, lordo=300.0)
        body = {"importo_pagato": 280.0, "tipo_chiusura": "sconto", "motivo_sconto": "Promo iter10"}
        r = session.post(f"{API}/titoli/{tid}/incassa", json=body, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data["tipo_chiusura"] == "sconto"
        assert data["importo_pagato"] == 280.0
        assert round(data["residuo"], 2) == 20.0
        assert round(data["sconto_applicato"], 2) == 20.0
        assert data["titolo_residuo_id"] is None
        assert data["movimento_sconto_id"] is not None

        # Verify movements exist
        movs = session.get(f"{API}/contabilita/movimenti?titolo_id={tid}", timeout=20).json()
        # fall back: filter manually
        all_movs = movs if isinstance(movs, list) else movs.get("items", [])
        related = [m for m in all_movs if m.get("titolo_id") == tid]
        cats = {m["categoria"]: m for m in related}
        if related:
            assert "incasso_premio" in cats
            assert "sconto_cliente" in cats
            assert round(cats["sconto_cliente"]["importo"], 2) == 20.0


# --- 3. Incasso flow sospeso --------------------------------------------
class TestIncassoSospeso:
    def test_incasso_partial_sospeso_creates_residuo_titolo(self, session):
        pol_id, tid = _create_test_titolo(session, lordo=1124.70)
        body = {"importo_pagato": 1000.0, "tipo_chiusura": "sospeso"}
        r = session.post(f"{API}/titoli/{tid}/incassa", json=body, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data["tipo_chiusura"] == "sospeso"
        assert data["importo_pagato"] == 1000.0
        assert round(data["residuo"], 2) == 124.70
        assert round(data["sconto_applicato"], 2) == 0.0  # No sconto in sospeso mode
        assert data["titolo_residuo_id"], "titolo_residuo_id must be set"
        assert data["movimento_sconto_id"] is None  # No sconto uscita movement

        residuo_id = data["titolo_residuo_id"]
        # Residuo titolo must appear in /titoli/sospesi
        sosp = session.get(f"{API}/titoli/sospesi", timeout=30).json()
        residuo_in_sospesi = [t for t in sosp if t["id"] == residuo_id]
        assert residuo_in_sospesi, f"Residuo titolo {residuo_id} not in /titoli/sospesi"
        assert round(residuo_in_sospesi[0]["importo_lordo"], 2) == 124.70


# --- 4. Validation -------------------------------------------------------
class TestIncassoValidation:
    def test_invalid_tipo_chiusura_returns_400(self, session):
        pol_id, tid = _create_test_titolo(session, lordo=100.0)
        r = session.post(f"{API}/titoli/{tid}/incassa",
                         json={"importo_pagato": 80.0, "tipo_chiusura": "bogus"},
                         timeout=30)
        assert r.status_code == 400


# --- 5. Avvisi di Scadenza ----------------------------------------------
class TestAvvisiScadenze:
    def test_preview_returns_structure(self, session):
        r = session.get(f"{API}/avvisi-scadenze/preview?giorni=15", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        for key in ("giorni", "polizze", "titoli", "n_polizze", "n_titoli"):
            assert key in data, f"Missing key {key} in preview response: {data.keys()}"
        assert data["giorni"] == 15
        assert isinstance(data["polizze"], list)
        assert isinstance(data["titoli"], list)
        assert data["n_polizze"] == len(data["polizze"])
        assert data["n_titoli"] == len(data["titoli"])

    def test_esegui_returns_ok_false_when_smtp_missing(self, session):
        r = session.post(f"{API}/avvisi-scadenze/esegui", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        # SMTP not configured -> ok=false with error message
        assert data.get("ok") == False, f"Expected ok=false when SMTP missing, got {data}"
        err = (data.get("errore") or "").lower()
        assert "smtp" in err, f"Expected SMTP-related error message, got: {data}"

    def test_log_endpoint_returns_list(self, session):
        r = session.get(f"{API}/avvisi-scadenze/log", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        items = r.json()
        assert isinstance(items, list)
        # After esegui above, at least one entry should exist; most recent first
        if len(items) >= 2:
            t0 = items[0].get("eseguito_at") or ""
            t1 = items[1].get("eseguito_at") or ""
            assert t0 >= t1, "Log not sorted descending by eseguito_at"
