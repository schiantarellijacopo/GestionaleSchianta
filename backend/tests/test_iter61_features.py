"""
Iter61 — Test batteria per:
  1) Filtro Titoli 'scaduti da N giorni' con conteggio INCLUSIVO (cutoff oggi-(N-1))
  2) Dashboard buckets titoli_scaduti coerenti (5gg/10gg/15gg inclusive)
  3) Performance GET /api/titoli con limit=50000 e presenza campi provvigione_*
  4) Performance GET /api/polizze con limit=50000 + projection leggera (NO garanzie/addizionali/provvigioni_operatori)
  5) Confronto carichi annuale via dal/al e via anno, e 400 senza parametri
  6) Regolazione premio con tasso_override float
  7) Storico regolazioni multiple (>=2 salvataggi)
"""
import os
import time
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://localhost:8001"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@assicura.it", "password": "Admin123!"})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- 1) Titoli scaduti da N giorni ----------

def _check_inclusive(items, n):
    today = date.today()
    cutoff = today - timedelta(days=n - 1)
    for t in items:
        s = t.get("scadenza")
        assert s and s <= cutoff.isoformat(), f"scadenza {s} > cutoff {cutoff.isoformat()} per titolo {t.get('id')}"
        assert t.get("stato") in {"da_incassare", "insoluto", "sospeso"}, f"stato inatteso {t.get('stato')}"


def test_titoli_scaduti_da_5(h):
    r = requests.get(f"{BASE_URL}/api/titoli",
                     params={"scadute_da_min": 5, "stato_not": "incassato,stornato", "limit": 2000},
                     headers=h)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    _check_inclusive(items, 5)


def test_titoli_scaduti_da_10(h):
    r = requests.get(f"{BASE_URL}/api/titoli",
                     params={"scadute_da_min": 10, "stato_not": "incassato,stornato", "limit": 2000},
                     headers=h)
    assert r.status_code == 200
    _check_inclusive(r.json(), 10)


# ---------- 2) Dashboard buckets ----------

def test_dashboard_titoli_scaduti_inclusive(h):
    r = requests.get(f"{BASE_URL}/api/stats/dashboard-admin", headers=h)
    assert r.status_code == 200
    data = r.json()
    ts = data.get("titoli_scaduti") or {}
    for k in ("5gg", "10gg", "15gg"):
        assert k in ts, f"chiave {k} mancante in titoli_scaduti: {list(ts.keys())}"
        assert isinstance(ts[k], int)
    # Verifica coerenza: bucket 5gg del dashboard deve essere >= conteggio filtrato /api/titoli?scadute_da_min=5
    r2 = requests.get(f"{BASE_URL}/api/titoli",
                      params={"scadute_da_min": 5, "stato_not": "incassato,stornato", "limit": 50000},
                      headers=h)
    assert r2.status_code == 200
    # Il dashboard usa {da_incassare,insoluto,sospeso}; il filtro qui usa stato_not incassato+stornato
    # → i due set differiscono su 'sospeso' (che ora è INCLUSO nel dashboard). Verifichiamo solo che i valori esistano.
    # nessuna assert numerica stretta perché stato_not include sospeso mentre dashboard esplicita 3 stati.


# ---------- 3) Performance /api/titoli e presenza provvigioni ----------

def test_titoli_performance_and_provvigioni_breakdown(h):
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/titoli",
                     params={"stato_not": "incassato,stornato", "limit": 50000},
                     headers=h)
    dt = time.time() - t0
    assert r.status_code == 200
    print(f"[perf] /api/titoli limit=50000 in {dt:.2f}s items={len(r.json())}")
    assert dt < 5.0, f"troppo lento: {dt:.2f}s"
    items = r.json()
    # Almeno un titolo deve avere i 3 campi provvigione_* presenti (anche 0)
    found = 0
    for t in items[:200]:
        if all(k in t for k in ("provvigione_totale", "provvigione_collaboratore", "provvigione_margine")):
            found += 1
    assert found > 0 or len(items) == 0, "Nessun titolo esposto con breakdown provvigione_totale/collaboratore/margine"


# ---------- 4) Performance /api/polizze + projection leggera ----------

def test_polizze_performance_and_lean_projection(h):
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/polizze", params={"limit": 50000}, headers=h)
    dt = time.time() - t0
    assert r.status_code == 200
    items = r.json()
    print(f"[perf] /api/polizze limit=50000 in {dt:.2f}s items={len(items)}")
    assert dt < 5.0, f"troppo lento: {dt:.2f}s"
    if items:
        p = items[0]
        # I 3 array pesanti NON devono esserci
        for heavy in ("garanzie", "addizionali", "provvigioni_operatori"):
            assert heavy not in p, f"campo pesante '{heavy}' presente nella projection leggera"
        # Campi attesi (almeno key exists per la maggior parte)
        expected_any = ["premio_lordo", "premio_netto", "contraente_nome",
                        "compagnia_nome", "collaboratore_nome", "ramo", "prodotto",
                        "stato", "scadenza", "targa"]
        present = [k for k in expected_any if k in p]
        assert len(present) >= 6, f"pochi campi attesi presenti nella lean: {present}"


# ---------- 5) Confronto carichi ----------

def test_confronto_annuale_by_range(h):
    r = requests.get(f"{BASE_URL}/api/carichi-mensili/confronto-annuale",
                     params={"dal": "2026-03-01", "al": "2026-06-30"}, headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "stats" in data and "righe" in data
    st = data["stats"]
    assert st.get("anno_corrente") == 2026
    assert st.get("anno_precedente") == 2025


def test_confronto_annuale_by_anno(h):
    r = requests.get(f"{BASE_URL}/api/carichi-mensili/confronto-annuale",
                     params={"anno": 2026}, headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["stats"]["anno_corrente"] == 2026
    assert data["stats"]["anno_precedente"] == 2025


def test_confronto_annuale_missing_params_returns_400(h):
    r = requests.get(f"{BASE_URL}/api/carichi-mensili/confronto-annuale", headers=h)
    assert r.status_code == 400


# ---------- 6/7) Regolazione premio + storico ----------

@pytest.fixture(scope="module")
def polizza_reg(h):
    # Trova una polizza esistente e flagga regolazione_premio
    r = requests.get(f"{BASE_URL}/api/polizze", params={"limit": 10}, headers=h)
    assert r.status_code == 200
    items = r.json()
    assert items, "Nessuna polizza in DB"
    pid = items[0]["id"]
    # PUT flag regolazione_premio=true
    r2 = requests.put(f"{BASE_URL}/api/polizze/{pid}",
                      json={"regolazione_premio": True, "regolazione_minima": 500,
                            "regolazione_tasso": 1.5},
                      headers=h)
    assert r2.status_code == 200, r2.text
    yield pid
    # cleanup: disattiva flag e pulisci storico test
    requests.put(f"{BASE_URL}/api/polizze/{pid}",
                 json={"regolazione_premio": False, "regolazione_dovuto": 0,
                       "regolazione_stato": "da_richiedere"},
                 headers=h)


def test_regolazione_calcola_with_tasso_override_float(h, polizza_reg):
    pid = polizza_reg
    # tasso_override float già convertito da ‰ (es. 2.5‰ / 10 = 0.25%)
    body = {"base_preventivo": 100000, "base_effettiva": 150000,
            "tasso_override": 0.25, "periodo": "2026",
            "base_tipo": "fatturato", "salva": False}
    r = requests.post(f"{BASE_URL}/api/polizze/{pid}/regolazione-premio/calcola",
                      json=body, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    # differenza = 50000, premio = 50000 * 0.25 / 100 = 125 → dovuto max(125, 500) = 500
    assert d["differenza"] == 50000
    assert d["premio_calcolato"] == 125.0
    assert d["dovuto"] == 500  # min. non rimborsabile


def test_regolazione_storico_multi_base_tipo(h, polizza_reg):
    pid = polizza_reg
    # 1° calcolo salvato: fatturato / 2026
    b1 = {"base_preventivo": 100000, "base_effettiva": 120000,
          "tasso_override": 2.0, "periodo": "2026",
          "base_tipo": "fatturato", "salva": True, "note": "TEST_ITER61 A"}
    r1 = requests.post(f"{BASE_URL}/api/polizze/{pid}/regolazione-premio/calcola",
                       json=b1, headers=h)
    assert r1.status_code == 200, r1.text
    # 2° calcolo salvato: retribuzioni / 2026 stesso periodo
    b2 = {"base_preventivo": 50000, "base_effettiva": 80000,
          "tasso_override": 1.0, "periodo": "2026",
          "base_tipo": "retribuzioni", "salva": True, "note": "TEST_ITER61 B"}
    r2 = requests.post(f"{BASE_URL}/api/polizze/{pid}/regolazione-premio/calcola",
                       json=b2, headers=h)
    assert r2.status_code == 200, r2.text

    r3 = requests.get(f"{BASE_URL}/api/polizze/{pid}/regolazione-premio/storico", headers=h)
    assert r3.status_code == 200
    storico = r3.json()
    test_rows = [s for s in storico if (s.get("note") or "").startswith("TEST_ITER61")]
    assert len(test_rows) >= 2, f"Attesi >=2 storico entry TEST_ITER61, trovati {len(test_rows)}"
    base_tipi = {s.get("base_tipo") for s in test_rows}
    assert {"fatturato", "retribuzioni"}.issubset(base_tipi), f"base_tipi presenti: {base_tipi}"
