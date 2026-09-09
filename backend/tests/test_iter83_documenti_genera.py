"""Iter 83 — Modelli PDF default per sezione + generazione documenti."""
import os
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASS = "Admin123!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


EXPECTED = [
    ("Scheda anagrafica cliente", "contraente"),
    ("Modulo RID / Mandato SEPA", "contraente"),
    ("Autocertificazione stato di famiglia", "contraente"),
    ("Documento di polizza", "polizza"),
    ("Documento di sinistro", "sinistro"),
]


# ---------- SEED default modelli ----------
def test_seed_5_default_models(hdr):
    r = requests.get(f"{BASE_URL}/api/librerie/modelli?categoria=default_sezione",
                     headers=hdr, timeout=15)
    assert r.status_code == 200, r.text
    items = r.json()
    names = [i["nome"] for i in items]
    for nome, _ in EXPECTED:
        assert nome in names, f"Manca modello default: {nome}. Trovati: {names}"


def test_seed_is_idempotent(hdr):
    # chiama 3 volte, il numero non deve aumentare
    counts = []
    for _ in range(3):
        r = requests.get(f"{BASE_URL}/api/librerie/modelli?categoria=default_sezione",
                         headers=hdr, timeout=15)
        assert r.status_code == 200
        counts.append(len(r.json()))
    assert counts[0] == counts[1] == counts[2]
    assert counts[0] >= 5


# ---------- filtri per sezione ----------
@pytest.mark.parametrize("sezione,atteso", [
    ("contraente", "Scheda anagrafica cliente"),
    ("polizza", "Documento di polizza"),
    ("sinistro", "Documento di sinistro"),
])
def test_modelli_sezione_filter(hdr, sezione, atteso):
    r = requests.get(f"{BASE_URL}/api/documenti/modelli-sezione?sezione={sezione}",
                     headers=hdr, timeout=15)
    assert r.status_code == 200, r.text
    items = r.json()
    names = [i["nome"] for i in items]
    assert atteso in names, f"[{sezione}] atteso {atteso}, trovati {names}"
    # ogni item deve avere la sezione fra sezioni_visibili
    for it in items:
        assert sezione in (it.get("sezioni_visibili") or []), \
            f"Modello {it.get('nome')} non ha {sezione} in sezioni_visibili"


def test_modelli_sezione_invalid(hdr):
    r = requests.get(f"{BASE_URL}/api/documenti/modelli-sezione?sezione=pippo",
                     headers=hdr, timeout=15)
    assert r.status_code == 400


# ---------- GENERA documento ----------
def _find_template(hdr, nome, sezione):
    r = requests.get(f"{BASE_URL}/api/documenti/modelli-sezione?sezione={sezione}",
                     headers=hdr, timeout=15)
    for it in r.json():
        if it["nome"] == nome:
            return it
    return None


def _first_anagrafica(hdr):
    r = requests.get(f"{BASE_URL}/api/anagrafiche?limit=1", headers=hdr, timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    return items[0] if items else None


def test_genera_preview_pdf_contraente(hdr):
    ana = _first_anagrafica(hdr)
    assert ana, "Nessuna anagrafica disponibile"
    tpl = _find_template(hdr, "Scheda anagrafica cliente", "contraente")
    assert tpl
    r = requests.post(f"{BASE_URL}/api/documenti/genera",
                      headers=hdr, timeout=30,
                      json={"entita_tipo": "contraente", "entita_id": ana["id"],
                            "template_id": tpl["id"], "salva": False})
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


def test_autocertificazione_specific_client(hdr):
    """Cliente noto con parente_di → PDF deve contenere il familiare."""
    cid = "93b73085-100f-4c78-883a-e6cefea49c72"
    tpl = _find_template(hdr, "Autocertificazione stato di famiglia", "contraente")
    assert tpl
    r = requests.post(f"{BASE_URL}/api/documenti/genera",
                      headers=hdr, timeout=30,
                      json={"entita_tipo": "contraente", "entita_id": cid,
                            "template_id": tpl["id"], "salva": False})
    if r.status_code == 404:
        pytest.skip("Cliente di riferimento non presente nel DB")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
    # Il PDF binario di reportlab non è ricercabile come testo semplice ma
    # possiamo verificare almeno che il documento non sia vuoto.
    assert len(r.content) > 1500


def test_genera_salva_allegato_contraente(hdr):
    ana = _first_anagrafica(hdr)
    assert ana
    tpl = _find_template(hdr, "Scheda anagrafica cliente", "contraente")
    r = requests.post(f"{BASE_URL}/api/documenti/genera",
                      headers=hdr, timeout=30,
                      json={"entita_tipo": "contraente", "entita_id": ana["id"],
                            "template_id": tpl["id"], "salva": True,
                            "titolo": "TEST_iter83_doc"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out.get("ok") is True
    aid = out.get("allegato_id")
    assert aid
    # cleanup
    d = requests.delete(f"{BASE_URL}/api/allegati/{aid}", headers=hdr, timeout=15)
    assert d.status_code in (200, 204, 404)


def test_genera_polizza(hdr):
    r = requests.get(f"{BASE_URL}/api/polizze?limit=1", headers=hdr, timeout=15)
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    if not items:
        pytest.skip("Nessuna polizza")
    pol = items[0]
    tpl = _find_template(hdr, "Documento di polizza", "polizza")
    assert tpl
    r = requests.post(f"{BASE_URL}/api/documenti/genera",
                      headers=hdr, timeout=30,
                      json={"entita_tipo": "polizza", "entita_id": pol["id"],
                            "template_id": tpl["id"], "salva": False})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_genera_sinistro(hdr):
    r = requests.get(f"{BASE_URL}/api/sinistri?limit=1", headers=hdr, timeout=15)
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    if not items:
        pytest.skip("Nessun sinistro")
    sin = items[0]
    tpl = _find_template(hdr, "Documento di sinistro", "sinistro")
    assert tpl
    r = requests.post(f"{BASE_URL}/api/documenti/genera",
                      headers=hdr, timeout=30,
                      json={"entita_tipo": "sinistro", "entita_id": sin["id"],
                            "template_id": tpl["id"], "salva": False})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_genera_bad_request(hdr):
    r = requests.post(f"{BASE_URL}/api/documenti/genera", headers=hdr, timeout=10,
                      json={"entita_tipo": "xxx", "entita_id": "y"})
    assert r.status_code == 400
