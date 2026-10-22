"""
Iter — Business rules: delete/archivia anagrafica, delete polizza con titolo in
Prima Nota chiusa, permesso riapertura giornate (puo_riaprire_giornate).
All writes on SANDBOX tenant.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SB_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it")  # sandbox user assente in preview DB
SB_PWD = os.environ.get("TEST_ADMIN_PWD", "Admin123!")
# Date remota per non interferire con dati sandbox reali
TEST_DAY = "2019-03-%02d" % (int(uuid.uuid4().int % 27) + 1)


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(SB_EMAIL, SB_PWD)


@pytest.fixture(scope="module")
def compagnia_id(admin):
    r = admin.get(f"{BASE_URL}/api/compagnie", timeout=30)
    assert r.status_code == 200
    comps = r.json()
    if not comps:
        r = admin.post(f"{BASE_URL}/api/compagnie", json={"nome": "TEST_COMP"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]
    return comps[0]["id"]


def _new_anag(admin, tag):
    suf = uuid.uuid4().hex[:6].upper()
    r = admin.post(f"{BASE_URL}/api/anagrafiche", json={
        "tipo": "persona_fisica", "nome": "TEST_DEL", "cognome": f"{tag}{suf}",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _new_polizza(admin, aid, cid, stato=None):
    body = {"contraente_id": aid, "compagnia_id": cid,
            "numero_polizza": f"TEST-DEL-{uuid.uuid4().hex[:8]}", "ramo": "RCA",
            "effetto": "2019-01-01", "scadenza": "2030-01-01", "frazionamento": "annuale"}
    if stato:
        body["stato"] = stato
    r = admin.post(f"{BASE_URL}/api/polizze", json=body, timeout=30)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    if stato and r.json().get("stato") != stato:
        r2 = admin.put(f"{BASE_URL}/api/polizze/{pid}", json={"stato": stato}, timeout=30)
        assert r2.status_code == 200, r2.text
    g = admin.get(f"{BASE_URL}/api/polizze/{pid}", timeout=30).json()
    if stato:
        assert g.get("stato") == stato, f"stato polizza atteso {stato}, got {g.get('stato')}"
    return pid


# ---------------- Anagrafica delete rules ----------------
class TestAnagraficaDelete:
    def test_blocked_with_analisi(self, admin):
        aid = _new_anag(admin, "ANALISI")
        r = admin.put(f"{BASE_URL}/api/anagrafiche/{aid}/analisi",
                      json={"liquidita": 5000, "contesto_familiare": "sposato"}, timeout=30)
        assert r.status_code == 200, r.text
        r = admin.delete(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["blocked"] is True and "analisi" in d["message"].lower()
        g = admin.get(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert g.status_code == 200
        assert not g.json().get("archiviata")

    def test_empty_analisi_tab_opened_not_blocking(self, admin):
        aid = _new_anag(admin, "ANEMPTY")
        g = admin.get(f"{BASE_URL}/api/anagrafiche/{aid}/analisi", timeout=30)
        assert g.status_code == 200
        r = admin.delete(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("eliminata") is True, r.json()

    @pytest.mark.parametrize("stato", ["attiva", "sospesa", "in_emissione"])
    def test_blocked_with_active_policy(self, admin, compagnia_id, stato):
        aid = _new_anag(admin, f"POL{stato[:3].upper()}")
        _new_polizza(admin, aid, compagnia_id, stato)
        r = admin.delete(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["blocked"] is True and d["message"]
        g = admin.get(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30).json()
        assert not g.get("archiviata")

    def test_archived_with_annullata_policy_and_restore(self, admin, compagnia_id):
        aid = _new_anag(admin, "ARCH")
        _new_polizza(admin, aid, compagnia_id, "annullata")
        r = admin.delete(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("archiviata") is True
        g = admin.get(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert g.status_code == 200 and g.json().get("archiviata") is True
        # restore
        r = admin.post(f"{BASE_URL}/api/anagrafiche/{aid}/ripristina", timeout=30)
        assert r.status_code == 200, r.text
        g = admin.get(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30).json()
        assert g.get("archiviata") is False
        # restore non-archived -> 400
        r = admin.post(f"{BASE_URL}/api/anagrafiche/{aid}/ripristina", timeout=30)
        assert r.status_code == 400

    def test_archived_with_sinistro(self, admin):
        aid = _new_anag(admin, "SIN")
        r = admin.post(f"{BASE_URL}/api/sinistri", json={
            "contraente_id": aid, "numero_sinistro": f"TEST-SIN-{uuid.uuid4().hex[:6]}",
            "data_avvenimento": "2019-02-01", "descrizione": "TEST"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        r = admin.delete(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("archiviata") is True

    def test_empty_deleted(self, admin):
        aid = _new_anag(admin, "EMPTY")
        r = admin.delete(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("eliminata") is True
        g = admin.get(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30)
        assert g.status_code == 404

    def test_list_contains_archiviata_field(self, admin, compagnia_id):
        aid = _new_anag(admin, "LISTARC")
        _new_polizza(admin, aid, compagnia_id, "annullata")
        assert admin.delete(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=30).json().get("archiviata")
        r = admin.get(f"{BASE_URL}/api/anagrafiche", params={"q": "LISTARC"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else (data.get("items") or data.get("data") or [])
        match = [a for a in items if a.get("id") == aid]
        assert match, "anagrafica archiviata non presente in lista (search q)"
        assert match[0].get("archiviata") is True


# ---------------- Polizza + Prima Nota chiusa + riapertura ----------------
@pytest.fixture(scope="module")
def collab(admin):
    email = f"test_collab_{uuid.uuid4().hex[:6]}@sandbox-test.it"
    pwd = "Collab1234!"
    r = admin.post(f"{BASE_URL}/api/auth/users", json={
        "email": email, "password": pwd, "name": "TEST Collab Riapri",
        "role": "collaboratore", "accesso_software": True}, timeout=30)
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    s = _login(email, pwd)
    yield {"id": uid, "s": s}
    admin.delete(f"{BASE_URL}/api/auth/users/{uid}", timeout=30)


@pytest.fixture(scope="module")
def chiusura(admin, compagnia_id):
    aid = _new_anag(admin, "PNCH")
    pid = _new_polizza(admin, aid, compagnia_id, None)
    r = admin.post(f"{BASE_URL}/api/titoli", json={
        "polizza_id": pid, "stato": "da_incassare", "importo_lordo": 100.0,
        "effetto": TEST_DAY, "scadenza": TEST_DAY}, timeout=30)
    assert r.status_code in (200, 201), r.text
    tid = r.json()["id"]
    r = admin.post(f"{BASE_URL}/api/contabilita/movimenti", json={
        "data_movimento": TEST_DAY, "tipo": "entrata", "categoria": "altro",
        "importo": 100.0, "descrizione": "TEST mov PN", "titolo_id": tid,
        "polizza_id": pid, "mezzo_pagamento": "contanti"}, timeout=30)
    assert r.status_code == 201, r.text
    r = admin.post(f"{BASE_URL}/api/contabilita/chiusura-giorno", json={"data": TEST_DAY}, timeout=60)
    assert r.status_code == 201, r.text
    return {"pid": pid, "tid": tid, "cid": r.json()["id"], "aid": aid}


class TestPrimaNota:
    def test_delete_polizza_blocked_by_closed_day(self, admin, chiusura):
        r = admin.delete(f"{BASE_URL}/api/polizze/{chiusura['pid']}", timeout=30)
        assert r.status_code == 409, r.text
        assert "giornata chiusa" in r.json()["detail"].lower()

    def test_giornata_stato_admin(self, admin, chiusura):
        r = admin.get(f"{BASE_URL}/api/contabilita/giornata-stato/{TEST_DAY}", timeout=30)
        assert r.status_code == 200
        assert r.json()["chiusa"] is True and r.json()["can_riapri"] is True

    def test_giornata_stato_collab_no_flag(self, collab, chiusura):
        r = collab["s"].get(f"{BASE_URL}/api/contabilita/giornata-stato/{TEST_DAY}", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["chiusa"] is True and r.json()["can_riapri"] is False

    def test_riapri_collab_no_flag_403(self, collab, chiusura):
        r = collab["s"].post(f"{BASE_URL}/api/contabilita/chiusura-giorno/{chiusura['cid']}/riapri",
                             json={"motivo": "test"}, timeout=30)
        assert r.status_code == 403, r.text

    def test_riapri_collab_with_flag_200(self, admin, collab, chiusura):
        r = admin.put(f"{BASE_URL}/api/auth/users/{collab['id']}",
                      json={"puo_riaprire_giornate": True}, timeout=30)
        assert r.status_code == 200 and r.json().get("puo_riaprire_giornate") is True
        r = collab["s"].get(f"{BASE_URL}/api/contabilita/giornata-stato/{TEST_DAY}", timeout=30)
        assert r.json()["can_riapri"] is True
        r = collab["s"].post(f"{BASE_URL}/api/contabilita/chiusura-giorno/{chiusura['cid']}/riapri",
                             json={"motivo": "test"}, timeout=30)
        assert r.status_code == 200, r.text
        r = admin.get(f"{BASE_URL}/api/contabilita/giornata-stato/{TEST_DAY}", timeout=30)
        assert r.json()["chiusa"] is False

    def test_admin_riapri_and_delete_polizza_after(self, admin, chiusura):
        # chiudi di nuovo e riapri come admin
        r = admin.post(f"{BASE_URL}/api/contabilita/chiusura-giorno", json={"data": TEST_DAY}, timeout=60)
        assert r.status_code == 201, r.text
        cid2 = r.json()["id"]
        r = admin.post(f"{BASE_URL}/api/contabilita/chiusura-giorno/{cid2}/riapri",
                       json={"motivo": "test"}, timeout=30)
        assert r.status_code == 200, r.text
        # ora polizza eliminabile (giornata aperta)
        r = admin.delete(f"{BASE_URL}/api/polizze/{chiusura['pid']}", timeout=30)
        assert r.status_code == 200, r.text
        # cleanup movimenti
        movs = admin.get(f"{BASE_URL}/api/contabilita/movimenti",
                         params={"titolo_id": chiusura["tid"]}, timeout=30).json()
        for m in movs:
            admin.delete(f"{BASE_URL}/api/contabilita/movimenti/{m['id']}", timeout=30)

    def test_riapri_missing_motivo_400(self, admin):
        r = admin.post(f"{BASE_URL}/api/contabilita/chiusura-giorno/nonexist/riapri", json={}, timeout=30)
        assert r.status_code == 400
