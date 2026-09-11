"""
Iter 87 — Backend tests
1) DELETE /polizze/{pid} → 409 se esiste titolo incassato; polizza NON eliminata
2) DELETE /polizze/{pid} → 200 su polizza senza titoli
3) KPI /kpi/sinistri/stats: conteggia solo sinistri con data_avvenimento anno in corso;
   label 'Totale <anno corrente>'
"""
import os
import time
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@assicura.it", "password": "Admin123!"}


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def compagnia_id(sess):
    r = sess.get(f"{API}/compagnie?limit=1", timeout=20)
    assert r.status_code == 200
    lst = r.json()
    if isinstance(lst, dict):
        lst = lst.get("items", [])
    assert lst
    return lst[0]["id"]


@pytest.fixture(scope="module")
def contraente_id(sess):
    ts = int(time.time())
    r = sess.post(f"{API}/anagrafiche", json={
        "nome": f"TEST_Iter87_{ts}",
        "cognome": "Contraente",
        "tipo": "persona_fisica",
        "codice_fiscale": f"TSTITE{ts % 1000000:06d}A",
    }, timeout=20)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _mkpol(sess, contraente_id, compagnia_id, suffix):
    ts = int(time.time() * 1000)
    body = {
        "numero_polizza": f"TESTP87{suffix}-{ts}",
        "contraente_id": contraente_id,
        "compagnia_id": compagnia_id,
        "ramo": "INCENDIO",
        "premio_lordo": 100.0,
        "stato": "attiva",
        "effetto": "2024-01-01",
        "scadenza": "2025-01-01",
    }
    r = sess.post(f"{API}/polizze", json=body, timeout=20)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# 1) DELETE su polizza CON titolo incassato → 409
def test_delete_polizza_con_titolo_incassato_409(sess, contraente_id, compagnia_id):
    pid = _mkpol(sess, contraente_id, compagnia_id, "BL")
    rt = sess.post(f"{API}/titoli", json={
        "polizza_id": pid,
        "contraente_id": contraente_id,
        "importo_lordo": 100.0,
        "scadenza": "2024-01-01",
        "effetto": "2024-01-01",
        "stato": "incassato",
        "data_incasso": "2024-01-05",
    }, timeout=20)
    assert rt.status_code in (200, 201), rt.text

    d = sess.delete(f"{API}/polizze/{pid}", timeout=20)
    assert d.status_code == 409, f"expected 409 got {d.status_code}: {d.text}"
    body = d.text.lower()
    assert "incass" in body or "copert" in body, d.text

    # NON eliminata: GET 200
    g = sess.get(f"{API}/polizze/{pid}", timeout=20)
    assert g.status_code == 200


# 2) DELETE su polizza senza titoli → 200
def test_delete_polizza_senza_titoli_ok(sess, contraente_id, compagnia_id):
    pid = _mkpol(sess, contraente_id, compagnia_id, "OK")
    d = sess.delete(f"{API}/polizze/{pid}", timeout=20)
    assert d.status_code == 200, d.text
    g = sess.get(f"{API}/polizze/{pid}", timeout=20)
    assert g.status_code == 404


# 3) KPI sinistri: solo anno in corso; label 'Totale <anno>'
def test_kpi_sinistri_solo_anno_corrente(sess, contraente_id, compagnia_id):
    anno = datetime.now(timezone.utc).year
    pid = _mkpol(sess, contraente_id, compagnia_id, "SIN")

    # baseline
    r = sess.get(f"{API}/kpi/sinistri/stats", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # struttura: può essere lista o dict con 'items'
    items = data if isinstance(data, list) else (data.get("default") or data.get("items") or data.get("stats") or [])
    totale_before_kpi = next((it for it in items if it.get("key") == "totale"), None)
    assert totale_before_kpi is not None, data
    assert str(anno) in totale_before_kpi.get("label", ""), totale_before_kpi
    baseline_totale = totale_before_kpi.get("value", 0)

    ts = int(time.time())
    # sinistro anno corrente
    r1 = sess.post(f"{API}/sinistri", json={
        "polizza_id": pid,
        "numero_sinistro": f"TEST87-CUR-{ts}",
        "data_avvenimento": f"{anno}-06-15",
        "descrizione": "TEST anno corrente",
        "stato": "aperto",
    }, timeout=20)
    assert r1.status_code in (200, 201), r1.text
    sid_cur = r1.json()["id"]

    # sinistro 3 anni fa
    r2 = sess.post(f"{API}/sinistri", json={
        "polizza_id": pid,
        "numero_sinistro": f"TEST87-OLD-{ts}",
        "data_avvenimento": f"{anno - 3}-06-15",
        "descrizione": "TEST vecchio",
        "stato": "aperto",
    }, timeout=20)
    assert r2.status_code in (200, 201), r2.text
    sid_old = r2.json()["id"]

    # ricontrolla KPI
    r = sess.get(f"{API}/kpi/sinistri/stats", timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else (data.get("default") or data.get("items") or data.get("stats") or [])
    totale_after = next((it for it in items if it.get("key") == "totale"), None)
    assert totale_after is not None
    # solo il sinistro anno corrente deve incrementare
    assert totale_after["value"] == baseline_totale + 1, {
        "baseline": baseline_totale, "after": totale_after["value"],
    }

    # cleanup best-effort
    sess.delete(f"{API}/sinistri/{sid_cur}", timeout=20)
    sess.delete(f"{API}/sinistri/{sid_old}", timeout=20)
    sess.delete(f"{API}/polizze/{pid}", timeout=20)
