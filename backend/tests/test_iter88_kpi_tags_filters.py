"""Tests for iteration 88:
- KPI Contabilità (prima_nota) shows euro amounts as main value
- All sections KPI stats work
- KPI custom CRUD works
- Age tags auto-assigned on anagrafica create/update
- Rami/prodotti/conti/compagnie filters exclude disabled/unused
"""
import os
import pytest
import requests
import uuid

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "admin@assicura.it", "password": "Admin123!"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE}/auth/login", json=ADMIN, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code} {r.text[:200]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        sess.headers["Authorization"] = f"Bearer {tok}"
    return sess


# =============== KPI stats per sezione ===============
@pytest.mark.parametrize("sez", ["polizze", "titoli", "sinistri", "prima_nota", "avvisi"])
def test_kpi_stats(s, sez):
    r = s.get(f"{BASE}/kpi/{sez}/stats", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "default" in data and isinstance(data["default"], list)
    assert len(data["default"]) > 0
    for k in data["default"]:
        assert "key" in k and "label" in k and "value" in k


def test_kpi_prima_nota_shows_euro_value(s):
    """Value delle KPI entrate/uscite/saldo DEVE essere una stringa €, non un numero."""
    r = s.get(f"{BASE}/kpi/prima_nota/stats", timeout=30)
    assert r.status_code == 200
    kpis = {k["key"]: k for k in r.json()["default"]}
    for key in ("entrate", "uscite", "saldo"):
        assert key in kpis, f"missing {key}"
        v = kpis[key]["value"]
        assert isinstance(v, str) and "€" in v, f"KPI {key} value should be euro string, got {v!r}"
    # movimenti = conteggio numerico
    assert isinstance(kpis["movimenti"]["value"], int)


# =============== KPI custom CRUD ===============
def test_kpi_custom_crud_and_stats(s):
    # options tag
    r = s.get(f"{BASE}/kpi/options", params={"sezione": "polizze", "kind": "tag"})
    assert r.status_code == 200
    opts = r.json()
    if not opts:
        pytest.skip("nessun tag disponibile")
    tag = opts[0]["value"]

    payload = {
        "sezione": "polizze", "label": f"TEST_KPI_{uuid.uuid4().hex[:6]}",
        "color": "sky", "icon": "Star", "ordine": 99,
        "filtro_kind": "tag", "filtro_params": {"tag": tag},
    }
    c = s.post(f"{BASE}/kpi/custom", json=payload)
    assert c.status_code == 201, c.text[:300]
    kid = c.json()["id"]

    # stats include custom
    stats = s.get(f"{BASE}/kpi/polizze/stats").json()
    custom_keys = [k["key"] for k in stats.get("custom", [])]
    assert f"custom_{kid}" in custom_keys, f"custom KPI non presente: {custom_keys}"
    # value must be integer (count)
    custom_kpi = next(k for k in stats["custom"] if k["key"] == f"custom_{kid}")
    assert isinstance(custom_kpi["value"], int)

    # cleanup
    d = s.delete(f"{BASE}/kpi/custom/{kid}")
    assert d.status_code == 200


# =============== Age tags automatici ===============
def test_age_tags_on_create_and_update(s):
    payload = {
        "tipo": "persona_fisica",
        "nome": "TEST",
        "cognome": f"AgeTag_{uuid.uuid4().hex[:6]}",
        "data_nascita": "1950-01-01",
        "tags": ["vip"],
    }
    c = s.post(f"{BASE}/anagrafiche", json=payload)
    assert c.status_code in (200, 201), c.text[:300]
    aid = c.json()["id"]
    tags = set(c.json().get("tags") or [])
    assert "vip" in tags
    assert "anziano_over_65" in tags, f"missing anziano_over_65: {tags}"
    assert any(t.startswith("gen_anni_") for t in tags), f"missing gen_anni_*: {tags}"

    # update
    u = s.put(f"{BASE}/anagrafiche/{aid}", json={**payload, "data_nascita": "2006-01-01"})
    assert u.status_code == 200, u.text[:300]
    tags2 = set(u.json().get("tags") or [])
    assert "vip" in tags2, "tag manuale perso"
    assert "giovane_under_30" in tags2, f"missing giovane_under_30: {tags2}"
    assert "gen_anni_00" in tags2, f"missing gen_anni_00: {tags2}"
    assert "anziano_over_65" not in tags2, f"vecchi age tags non puliti: {tags2}"

    # cleanup
    s.delete(f"{BASE}/anagrafiche/{aid}")


# =============== Filtri (disabilitati esclusi) ===============
def test_conti_cassa_attivi_default(s):
    r = s.get(f"{BASE}/librerie/conti-cassa", params={"attivi": "true"})
    assert r.status_code == 200
    for c in r.json():
        assert c.get("attivo", True) is not False, f"conto disabilitato in attivi: {c}"


def test_compagnie_default_hide_disabled(s):
    r = s.get(f"{BASE}/compagnie")
    assert r.status_code == 200
    for c in r.json():
        assert c.get("attiva", True) is not False, f"compagnia disabilitata trovata: {c.get('ragione_sociale')}"
    # tutte=true mostra anche le disabilitate
    r2 = s.get(f"{BASE}/compagnie", params={"tutte": "true"})
    assert r2.status_code == 200
    assert len(r2.json()) >= len(r.json())


def test_rami_con_polizze(s):
    r_all = s.get(f"{BASE}/librerie/rami").json()
    r_pol = s.get(f"{BASE}/librerie/rami", params={"con_polizze": 1}).json()
    assert len(r_pol) <= len(r_all)


def test_prodotti_con_polizze(s):
    r_pol = s.get(f"{BASE}/librerie/prodotti", params={"con_polizze": 1})
    assert r_pol.status_code == 200
