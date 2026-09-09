"""
Iteration 82 tests: MUP models, MUP generation, users filter, agenzie count, anagrafiche duplicati.
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ------------------------- MUP libreria modelli -------------------------
class TestMupModelli:
    def test_list_mup_modelli_has_seed(self, admin_session):
        r = admin_session.get(f"{API}/librerie/mup-modelli")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # 5 seeded models expected
        assert len(data) >= 5, f"Expected >=5 seeded MUP modelli, got {len(data)}"
        nomi = " ".join([(m.get("nome") or "").lower() for m in data])
        for kw in ["auto", "beni", "infortuni", "vita", "generic"]:
            assert kw in nomi, f"Missing MUP modello keyword: {kw}"

    def test_crud_mup_modello(self, admin_session):
        payload = {
            "nome": "TEST_MUP_Modello_82",
            "area": "generica",
            "garanzie": ["Garanzia A", "Garanzia B", "Garanzia C"],
        }
        r = admin_session.post(f"{API}/librerie/mup-modelli", json=payload)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        mid = created.get("id") or created.get("_id")
        assert mid, f"No id returned: {created}"
        assert created["nome"] == payload["nome"]

        # UPDATE
        r2 = admin_session.put(
            f"{API}/librerie/mup-modelli/{mid}",
            json={"nome": "TEST_MUP_Modello_82_upd", "area": "auto", "garanzie": ["G1"]},
        )
        assert r2.status_code == 200, r2.text
        upd = r2.json()
        assert upd["nome"] == "TEST_MUP_Modello_82_upd"

        # DELETE
        r3 = admin_session.delete(f"{API}/librerie/mup-modelli/{mid}")
        assert r3.status_code in (200, 204), r3.text

        # verify gone
        r4 = admin_session.get(f"{API}/librerie/mup-modelli")
        ids = [m.get("id") for m in r4.json()]
        assert mid not in ids


# ------------------------- MUP polizza righe-default & genera -------------------------
class TestMupPolizza:
    @pytest.fixture(scope="class")
    def polizza_id(self, admin_session):
        r = admin_session.get(f"{API}/polizze?limit=1")
        assert r.status_code == 200, r.text
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        if not items:
            pytest.skip("No polizze available")
        pid = items[0].get("id") or items[0].get("_id")
        assert pid
        return pid

    def test_righe_default(self, admin_session, polizza_id):
        r = admin_session.get(f"{API}/polizze/{polizza_id}/mup/righe-default")
        assert r.status_code == 200, r.text
        data = r.json()
        # Expect area + modelli + righe
        assert "area" in data or "righe" in data, f"Unexpected shape: {data}"
        if "modelli" in data:
            assert isinstance(data["modelli"], list)

    def test_genera_e_archivia(self, admin_session, polizza_id):
        payload = {
            "salva": True,
            "righe": [
                {"nome": "Furto", "richiesta": True, "proposta": True, "confermata": True},
                {"nome": "Incendio", "richiesta": True, "proposta": False, "confermata": False},
            ],
        }
        r = admin_session.post(f"{API}/polizze/{polizza_id}/mup/genera", json=payload)
        assert r.status_code == 200, r.text
        # Response could be JSON with allegato info or PDF bytes - check content-type
        ct = r.headers.get("content-type", "")
        if "application/json" in ct:
            data = r.json()
            # Should reference the saved allegato
            assert data, "empty response"


# ------------------------- users filter (no super_admin, no cliente listing) -------------------------
class TestUsersFilter:
    def test_list_users_excludes_super_admin(self, admin_session):
        r = admin_session.get(f"{API}/auth/users")
        assert r.status_code == 200, r.text
        users = r.json()
        assert isinstance(users, list)
        for u in users:
            assert not u.get("is_super_admin"), f"Super admin found in list: {u.get('email')}"


# ------------------------- agenzie principale count -------------------------
class TestAgenzie:
    def test_agenzia_principale_count_compagnie(self, admin_session):
        r = admin_session.get(f"{API}/agenzie")
        assert r.status_code == 200, r.text
        agenzie = r.json()
        principali = [a for a in agenzie if a.get("tipo") == "principale" or a.get("is_principale")]
        assert principali, f"No principale found. Sample: {agenzie[:2]}"
        p = principali[0]
        # Field name based on route: n_compagnie_collegate
        n = p.get("n_compagnie_collegate")
        assert n is not None, f"Missing n_compagnie_collegate: {p}"
        assert isinstance(n, int) and n >= 0


# ------------------------- anagrafiche duplicati endpoint -------------------------
class TestAnagraficheDuplicati:
    def test_endpoint_reachable(self, admin_session):
        r = admin_session.get(f"{API}/anagrafiche-duplicati")
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        data = r.json()
        # Either list of groups or {duplicati:[]}
        assert isinstance(data, (list, dict))
