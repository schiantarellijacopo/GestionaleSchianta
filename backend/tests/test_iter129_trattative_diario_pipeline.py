# Iter129: Trattative (checklist/premio/invia validation/board totals), WhatsApp chat by numero,
# Diario documents download, storage ?token= auth for images.
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
EMAIL = "jacopo@schiantarelli.it"   # qa.tester@schiantarelli.it does NOT exist in preview DB
PASSWORD = "NtdZs5ilxTSP"
NO_CONTACT_ANA = "1694b6b8-34ac-4525-b3ac-f0ad62dfe401"   # "TEST CATENA": no email, no cellulare
WA_ANA = "9beed006-704f-4339-ac05-9d3dcd23efbc"           # has 6 WA messages on 393402934389
WA_NUM = "393402934389"
DOC_ANA = "45e8c0a1-da0d-4775-b3b7-abbd1a50fa9f"          # diario w/ attached PDF
AVATAR_PATH = "/api/storage/assicura/anagrafiche/99b2fdc0-cddc-4071-8de0-75ca4274ead6/avatar_4c7ca589-98f4-447d-908f-25c1b85b89ff.jpg"
LOGO_PATH = "/api/storage/assicura/azienda/logo_e4645236-a5b5-4a53-a20c-5e85ce71970a.png"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def s(token):
    se = requests.Session()
    se.headers.update({"Authorization": f"Bearer {token}"})
    return se


@pytest.fixture(scope="module")
def trattativa(s):
    body = {"anagrafica_id": NO_CONTACT_ANA, "titolo": "TEST_iter129 preventivo", "premio_proposto": 1234.5,
            "premio_corrente": 1500, "stato": "aperta",
            "checklist": [{"id": "c1", "testo": "TEST_doc identita", "done": False}]}
    r = s.post(f"{API}/trattative", json=body)
    assert r.status_code == 201, r.text
    t = r.json()
    yield t
    s.delete(f"{API}/trattative/{t['id']}")


# --- Trattative CRUD: checklist + premio persist ---
class TestTrattative:
    def test_create_persist(self, s, trattativa):
        g = s.get(f"{API}/trattative/{trattativa['id']}").json()
        assert g["premio_proposto"] == 1234.5
        assert g["checklist"][0]["testo"] == "TEST_doc identita"
        assert g["checklist"][0]["done"] is False

    def test_toggle_checklist(self, s, trattativa):
        g = s.get(f"{API}/trattative/{trattativa['id']}").json()
        body = {k: g.get(k) for k in ["anagrafica_id", "titolo", "premio_proposto", "premio_corrente", "stato", "checklist"]}
        body["checklist"][0]["done"] = True
        r = s.put(f"{API}/trattative/{trattativa['id']}", json=body)
        assert r.status_code == 200
        g2 = s.get(f"{API}/trattative/{trattativa['id']}").json()
        assert g2["checklist"][0]["done"] is True

    def test_board_totals_and_move(self, s, trattativa):
        b = s.get(f"{API}/pipeline/trattative").json()
        cols = {c["key"]: c for c in b["colonne"]}
        before_aperta, before_vinta = cols["aperta"]["valore"], cols["vinta"]["valore"]
        assert any(c["id"] == trattativa["id"] for c in cols["aperta"]["cards"])
        r = s.post(f"{API}/pipeline/trattative/{trattativa['id']}/move", json={"nuovo_stato": "vinta"})
        assert r.status_code == 200, r.text
        cols2 = {c["key"]: c for c in s.get(f"{API}/pipeline/trattative").json()["colonne"]}
        assert round(cols2["aperta"]["valore"], 2) == round(before_aperta - 1234.5, 2)
        assert round(cols2["vinta"]["valore"], 2) == round(before_vinta + 1234.5, 2)
        s.post(f"{API}/pipeline/trattative/{trattativa['id']}/move", json={"nuovo_stato": "aperta"})

    # --- invia validation (no real send) ---
    @pytest.mark.parametrize("canale", ["email", "whatsapp"])
    def test_invia_missing_dest(self, s, trattativa, canale):
        r = s.post(f"{API}/trattative/{trattativa['id']}/invia", json={"canale": canale})
        assert r.status_code == 400
        assert "Destinatario" in r.json()["detail"] and "mancante" in r.json()["detail"]

    def test_invia_invalid_canale(self, s, trattativa):
        r = s.post(f"{API}/trattative/{trattativa['id']}/invia", json={"canale": "fax"})
        assert r.status_code == 400

    def test_invia_404(self, s):
        r = s.post(f"{API}/trattative/nonexistent-id/invia", json={"canale": "email"})
        assert r.status_code == 404


# --- WhatsApp chat by numero ---
class TestWAChat:
    def test_chat_numero(self, s):
        r = s.get(f"{API}/anagrafiche/{WA_ANA}/whatsapp-chat", params={"numero": WA_NUM})
        assert r.status_code == 200
        assert len(r.json()["messages"]) > 0

    def test_chat_numero_with_plus_prefix(self, s):
        r = s.get(f"{API}/anagrafiche/{WA_ANA}/whatsapp-chat", params={"numero": "+39 340 293 4389"})
        assert len(r.json()["messages"]) > 0


# --- Diario docs + download ---
class TestDiarioDocs:
    def test_diario_doc_download(self, s):
        d = s.get(f"{API}/anagrafiche/{DOC_ANA}/diario").json()
        docs = [doc for v in d for doc in (v.get("documenti") or [])]
        assert docs
        r = s.get(f"{API}{docs[0]['url']}")
        assert r.status_code == 200 and len(r.content) > 0

    def test_diario_doc_download_cookie_only(self, token):
        # simulates <a href target=_blank>: cookie only, no header
        se = requests.Session()
        se.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        d = se.get(f"{API}/anagrafiche/{DOC_ANA}/diario").json()
        docs = [doc for v in d for doc in (v.get("documenti") or [])]
        r = se.get(f"{API}{docs[0]['url']}")
        assert r.status_code == 200


# --- storage ?token= ---
class TestStorageToken:
    @pytest.mark.parametrize("path", [AVATAR_PATH, LOGO_PATH])
    def test_token_qp(self, token, path):
        r = requests.get(f"{BASE_URL}{path}", params={"token": token})
        assert r.status_code == 200 and len(r.content) > 0
        r2 = requests.get(f"{BASE_URL}{path}")
        assert r2.status_code == 401
