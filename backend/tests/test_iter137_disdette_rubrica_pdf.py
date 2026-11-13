# Iter137: Disdette enhancements - rubrica destinatari CRUD, new fields, PDF, allegati on disdetta
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    sess.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return sess


@pytest.fixture(scope="module")
def created():
    return {"rub": [], "dis": [], "all": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup(s, created):
    yield
    for a in created["all"]:
        s.delete(f"{API}/allegati/{a}")
    for d in created["dis"]:
        s.delete(f"{API}/disdette/{d}")
    for r in created["rub"]:
        s.delete(f"{API}/disdette-destinatari/{r}")


# --- Rubrica CRUD
class TestRubrica:
    def test_crud(self, s, created):
        r = s.post(f"{API}/disdette-destinatari", json={"nome": "TEST_Agenzia Bianchi", "indirizzo": "Via Verdi 10", "pec": "b@pec.it"})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]; created["rub"].append(rid)
        lst = s.get(f"{API}/disdette-destinatari").json()
        assert any(x["id"] == rid and x["pec"] == "b@pec.it" for x in lst)
        u = s.put(f"{API}/disdette-destinatari/{rid}", json={"nome": "TEST_Agenzia Bianchi2", "pec": "c@pec.it"})
        assert u.status_code == 200 and u.json()["nome"] == "TEST_Agenzia Bianchi2"
        assert "_id" not in u.json()
        d = s.delete(f"{API}/disdette-destinatari/{rid}")
        assert d.status_code == 200
        created["rub"].remove(rid)
        assert s.delete(f"{API}/disdette-destinatari/{rid}").status_code == 404

    def test_empty_name_rejected(self, s):
        r = s.post(f"{API}/disdette-destinatari", json={"nome": "   "})
        assert r.status_code in (400, 422)

    def test_put_missing_404(self, s):
        r = s.put(f"{API}/disdette-destinatari/nonexistent-xyz", json={"nome": "x"})
        assert r.status_code == 404

    def test_unauth(self):
        assert requests.get(f"{API}/disdette-destinatari").status_code in (401, 403)


# --- Disdetta new fields + PDF + allegati
class TestDisdetta:
    def test_create_with_new_fields(self, s, created):
        body = {"compagnia_da_disdire": "TEST_UnipolSai", "numero_polizza": "P123", "ramo": "RCAUTO",
                "data_scadenza": "2026-02-01", "data_scadenza_polizza": "2026-02-10",
                "destinatario_nome": "Agenzia Bianchi", "destinatario_indirizzo": "Via Verdi 10 Milano",
                "destinatario_pec": "bianchi@pec.it", "polizza_emessa": False, "note": "nota"}
        r = s.post(f"{API}/disdette", json=body)
        assert r.status_code == 201, r.text
        d = r.json(); created["dis"].append(d["id"])
        lst = s.get(f"{API}/disdette").json()
        got = next(x for x in lst if x["id"] == d["id"])
        for k in ("data_scadenza_polizza", "destinatario_nome", "destinatario_indirizzo", "destinatario_pec"):
            assert got[k] == body[k]
        assert got["polizza_emessa"] is False

    def test_update_polizza_emessa(self, s, created):
        did = created["dis"][0]
        r = s.put(f"{API}/disdette/{did}", json={"compagnia_da_disdire": "TEST_UnipolSai", "polizza_emessa": True,
                                                 "data_scadenza_polizza": "2026-02-10"})
        assert r.status_code == 200 and r.json()["polizza_emessa"] is True

    def test_pdf(self, s, created):
        did = created["dis"][0]
        r = s.get(f"{API}/disdette/{did}/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_pdf_404(self, s):
        assert s.get(f"{API}/disdette/nonexistent-xyz/pdf").status_code == 404

    def test_pdf_special_chars(self, s, created):
        # names with & and < are common ("Rossi & Figli") - reportlab Paragraph markup must be escaped
        r = s.post(f"{API}/disdette", json={"compagnia_da_disdire": "TEST_Rossi & Figli <srl>",
                                            "destinatario_nome": "Agenzia A&B", "note": "costo < 100 & altro"})
        assert r.status_code == 201
        did = r.json()["id"]; created["dis"].append(did)
        p = s.get(f"{API}/disdette/{did}/pdf")
        assert p.status_code == 200, f"PDF fails with special chars: {p.status_code} {p.text[:200]}"

    def test_pdf_token_query(self, s, created):
        # frontend link uses imgUrl() (token in query string)
        did = created["dis"][0]
        tok = s.headers["Authorization"][7:]
        r = requests.get(f"{API}/disdette/{did}/pdf", params={"token": tok})
        assert r.status_code == 200

    def test_allegato_on_disdetta(self, s, created):
        did = created["dis"][0]
        files = {"file": ("TEST_doc.txt", io.BytesIO(b"hello disdetta"), "text/plain")}
        r = s.post(f"{API}/allegati", params={"entita_tipo": "disdetta", "entita_id": did}, files=files)
        assert r.status_code in (200, 201), r.text
        aid = r.json()["id"]; created["all"].append(aid)
        lst = s.get(f"{API}/allegati", params={"entita_tipo": "disdetta", "entita_id": did}).json()
        assert any(a["id"] == aid for a in lst)
        dr = s.delete(f"{API}/allegati/{aid}")
        assert dr.status_code in (200, 204)
        created["all"].remove(aid)
        lst = s.get(f"{API}/allegati", params={"entita_tipo": "disdetta", "entita_id": did}).json()
        assert not any(a["id"] == aid for a in lst)
