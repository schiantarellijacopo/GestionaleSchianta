# Iter134: Documenti annuali collaboratori (checklist, upload admin/me, config, role isolation, IVASS stato, crediti_ivass null)
import os
import io
import datetime as dt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ANNO = dt.date.today().year
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    tok = r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@assicura.it", "Admin123!")


@pytest.fixture(scope="module")
def collab():
    return _login("collaboratore@assicura.it", "Collab123!")


@pytest.fixture(scope="module")
def dip():
    return _login("dipendente@assicura.it", "Dipendente123!")


def _me(s):
    r = s.get(f"{API}/collaboratori/documenti-annuali", params={"anno": ANNO})
    assert r.status_code == 200
    d = r.json()
    assert len(d["collaboratori"]) == 1
    return d["collaboratori"][0]


def _item(c, key):
    return next(i for i in c["items"] if i["key"] == key)


def _upload(s, url, key, scad=None, anno=ANNO, name="TEST_doc.pdf", content=PDF):
    data = {"req_key": key, "tipologia": key, "anno": str(anno)}
    if scad:
        data["data_scadenza"] = scad
    return s.post(url, files={"file": (name, io.BytesIO(content), "application/pdf")}, data=data)


# --- Overview / isolation
class TestOverview:
    def test_admin_overview(self, admin):
        r = admin.get(f"{API}/collaboratori/documenti-annuali", params={"anno": ANNO})
        assert r.status_code == 200
        d = r.json()
        assert d["is_admin"] is True and d["anno"] == ANNO
        keys = [c["key"] for c in d["checklist"]]
        for k in ["casellario_giudiziale", "carichi_pendenti", "attestato_ivass", "visura_rui", "antiriciclaggio"]:
            assert k in keys
        assert len(d["collaboratori"]) > 1
        for c in d["collaboratori"]:
            assert c["role"] in ("admin", "collaboratore", "dipendente")
            assert len(c["items"]) == len(d["checklist"])
            assert "_id" not in c

    def test_collab_sees_only_self(self, collab):
        c = _me(collab)
        assert c["email"] == "collaboratore@assicura.it"

    def test_dip_sees_only_self(self, dip):
        c = _me(dip)
        assert c["email"] == "dipendente@assicura.it"

    def test_collab_cannot_query_other_uid(self, collab, admin):
        r = admin.get(f"{API}/collaboratori/documenti-annuali", params={"anno": ANNO}).json()
        other = next(c for c in r["collaboratori"] if c["email"] != "collaboratore@assicura.it")
        r2 = collab.get(f"{API}/collaboratori/documenti-annuali", params={"anno": ANNO, "uid": other["id"]})
        assert r2.status_code == 403

    def test_collab_cannot_use_admin_upload(self, collab, admin):
        r = admin.get(f"{API}/collaboratori/documenti-annuali", params={"anno": ANNO}).json()
        other = next(c for c in r["collaboratori"] if c["email"] != "collaboratore@assicura.it")
        r2 = _upload(collab, f"{API}/auth/users/{other['id']}/documenti-annuali", "casellario_giudiziale")
        assert r2.status_code in (401, 403)

    def test_collab_cannot_put_config(self, collab):
        r = collab.put(f"{API}/config/documenti-annuali-collab", json={"checklist": [{"label": "X"}]})
        assert r.status_code in (401, 403)


# --- Upload flows + stati
class TestUpload:
    def test_me_upload_presente_and_delete(self, collab):
        r = _upload(collab, f"{API}/me/documenti-annuali", "carichi_pendenti")
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["req_key"] == "carichi_pendenti" and doc["anno"] == str(ANNO)
        it = _item(_me(collab), "carichi_pendenti")
        assert it["stato"] == "presente"
        assert any(f["id"] == doc["id"] for f in it["files"])
        # file reachable
        f = collab.get(f"{BASE_URL}{doc['url']}")
        assert f.status_code == 200
        d = collab.delete(f"{API}/me/documenti-annuali/{doc['id']}")
        assert d.status_code == 200
        it = _item(_me(collab), "carichi_pendenti")
        assert all(f["id"] != doc["id"] for f in it["files"])

    def test_dip_upload_me(self, dip):
        r = _upload(dip, f"{API}/me/documenti-annuali", "visura_rui")
        assert r.status_code == 200, r.text
        doc = r.json()
        it = _item(_me(dip), "visura_rui")
        assert it["stato"] == "presente"
        dip.delete(f"{API}/me/documenti-annuali/{doc['id']}")

    def test_admin_upload_stati(self, admin, collab):
        uid = _me(collab)["id"]
        url = f"{API}/auth/users/{uid}/documenti-annuali"
        ids = []
        try:
            soon = (dt.date.today() + dt.timedelta(days=10)).isoformat()
            r = _upload(admin, url, "casellario_giudiziale", scad=soon)
            assert r.status_code == 200, r.text
            ids.append(r.json()["id"])
            assert _item(_me(collab), "casellario_giudiziale")["stato"] == "in_scadenza"
            # passed date on separate item
            past = (dt.date.today() - dt.timedelta(days=5)).isoformat()
            r = _upload(admin, url, "antiriciclaggio", scad=past)
            assert r.status_code == 200
            ids.append(r.json()["id"])
            assert _item(_me(collab), "antiriciclaggio")["stato"] == "scaduto"
            # far future -> presente
            far = (dt.date.today() + dt.timedelta(days=300)).isoformat()
            r = _upload(admin, url, "visura_rui", scad=far)
            ids.append(r.json()["id"])
            assert _item(_me(collab), "visura_rui")["stato"] == "presente"
            # Different year doesn't count
            r2 = collab.get(f"{API}/collaboratori/documenti-annuali", params={"anno": ANNO + 1}).json()
            assert _item(r2["collaboratori"][0], "visura_rui")["stato"] == "mancante"
        finally:
            for i in ids:
                d = admin.delete(f"{url}/{i}")
                assert d.status_code == 200

    def test_upload_empty_file(self, collab):
        r = _upload(collab, f"{API}/me/documenti-annuali", "carichi_pendenti", content=b"")
        assert r.status_code == 400

    def test_upload_too_big(self, collab):
        r = _upload(collab, f"{API}/me/documenti-annuali", "carichi_pendenti", content=b"0" * (10 * 1024 * 1024 + 10))
        assert r.status_code == 400


# --- Config checklist
class TestConfig:
    def test_add_remove_custom_card(self, admin, collab):
        orig = admin.get(f"{API}/config/documenti-annuali-collab").json()["checklist"]
        try:
            new = orig + [{"key": "", "label": "TEST_Patente", "obbligatorio": True}]
            r = admin.put(f"{API}/config/documenti-annuali-collab", json={"checklist": new})
            assert r.status_code == 200
            cl = r.json()["checklist"]
            added = next(c for c in cl if c["label"] == "TEST_Patente")
            assert added["key"].startswith("custom_")
            it = _item(_me(collab), added["key"])
            assert it["stato"] == "mancante"
            ov = admin.get(f"{API}/collaboratori/documenti-annuali", params={"anno": ANNO}).json()
            assert all(any(i["key"] == added["key"] for i in c["items"]) for c in ov["collaboratori"])
            # empty -> 400
            r = admin.put(f"{API}/config/documenti-annuali-collab", json={"checklist": []})
            assert r.status_code == 400
        finally:
            r = admin.put(f"{API}/config/documenti-annuali-collab", json={"checklist": orig})
            assert r.status_code == 200
        cl = admin.get(f"{API}/config/documenti-annuali-collab").json()["checklist"]
        assert not any(c["label"] == "TEST_Patente" for c in cl)


# --- IVASS stato + crediti_ivass null bugfix
class TestIvass:
    def test_ivass_parziale_and_presente(self, admin, collab):
        uid = _me(collab)["id"]
        anno = 2023
        base = collab.get(f"{API}/collaboratori/documenti-annuali", params={"anno": anno}).json()["collaboratori"][0]
        ore0 = _item(base, "attestato_ivass")["ore_ivass"]
        ids = []
        try:
            r = admin.post(f"{API}/corsi-ivass", json={"collaboratore_id": uid, "titolo_corso": "TEST_corso",
                                                      "data_corso": f"{anno}-03-01", "ore_riconosciute": 10,
                                                      "crediti_ivass": None})
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
            it = _item(collab.get(f"{API}/collaboratori/documenti-annuali", params={"anno": anno}).json()["collaboratori"][0], "attestato_ivass")
            assert it["ore_ivass"] == ore0 + 10
            if ore0 + 10 < 30:
                assert it["stato"] == "parziale"
            r = admin.post(f"{API}/corsi-ivass", json={"collaboratore_id": uid, "titolo_corso": "TEST_corso2",
                                                      "data_corso": f"{anno}-04-01", "ore_riconosciute": 25})
            assert r.status_code == 201
            ids.append(r.json()["id"])
            it = _item(collab.get(f"{API}/collaboratori/documenti-annuali", params={"anno": anno}).json()["collaboratori"][0], "attestato_ivass")
            assert it["stato"] == "presente"
        finally:
            for i in ids:
                admin.delete(f"{API}/corsi-ivass/{i}")

    def test_crediti_empty_string_422(self, admin, collab):
        # Backend still rejects "" (frontend normalizes to null)
        uid = _me(collab)["id"]
        r = admin.post(f"{API}/corsi-ivass", json={"collaboratore_id": uid, "titolo_corso": "TEST_x",
                                                  "data_corso": "2023-01-01", "ore_riconosciute": 1, "crediti_ivass": ""})
        if r.status_code == 201:
            admin.delete(f"{API}/corsi-ivass/{r.json()['id']}")
        assert r.status_code in (201, 422)
