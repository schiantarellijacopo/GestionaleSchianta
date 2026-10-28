# Iter124: per-agency firma_provider (super admin), document_target_card on templates, public YouSign webhook
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
# NOTE: sandbox tenant c942fe2a... / test@sandbox.it do NOT exist in this preview DB -> use TEST tenant + admin
SANDBOX_TID = "3b056fe9-9766-4c70-8e13-202eaf964b6f"


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login("superadmin@assicura.it", "superadmin123!")


@pytest.fixture(scope="module")
def sandbox():
    return _login("admin@assicura.it", "Admin123!")


# --- Super Admin firma_provider ---
class TestFirmaProvider:
    def test_list_has_firma_provider(self, sa):
        r = sa.get(f"{BASE_URL}/api/super-admin/agenzie", timeout=60)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and items
        legacy = [(t["id"], t.get("firma_provider")) for t in items if t.get("firma_provider") not in ("yousign", "openapi")]
        print("legacy firma_provider values:", legacy)
        assert all("firma_provider" in t for t in items)
        assert any(t["id"] == SANDBOX_TID for t in items)

    def test_get_detail_has_firma_provider(self, sa):
        r = sa.get(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", timeout=30)
        assert r.status_code == 200
        assert r.json()["firma_provider"] in ("yousign", "openapi")

    def test_patch_openapi_then_yousign(self, sa):
        r = sa.patch(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", json={"firma_provider": "openapi"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["firma_provider"] == "openapi"
        g = sa.get(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", timeout=30)
        assert g.json()["firma_provider"] == "openapi"
        lst = sa.get(f"{BASE_URL}/api/super-admin/agenzie", timeout=60).json()
        assert next(t for t in lst if t["id"] == SANDBOX_TID)["firma_provider"] == "openapi"
        r = sa.patch(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", json={"firma_provider": "YouSign"}, timeout=30)
        assert r.status_code == 200
        g = sa.get(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", timeout=30)
        assert g.json()["firma_provider"] == "yousign"

    def test_patch_invalid_provider(self, sa):
        r = sa.patch(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", json={"firma_provider": "docusign"}, timeout=30)
        assert r.status_code == 400
        g = sa.get(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", timeout=30)
        assert g.json()["firma_provider"] == "yousign"

    def test_patch_does_not_clobber_workspace(self, sa):
        before = sa.get(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", timeout=30).json()
        sa.patch(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", json={"firma_provider": "yousign"}, timeout=30)
        after = sa.get(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", timeout=30).json()
        assert before["yousign_workspace_id"] == after["yousign_workspace_id"]

    def test_non_superadmin_forbidden(self, sandbox):
        r = sandbox.patch(f"{BASE_URL}/api/super-admin/agenzie/{SANDBOX_TID}", json={"firma_provider": "openapi"}, timeout=30)
        assert r.status_code == 403


# --- Template document_target_card ---
class TestTargetCard:
    created = []

    def test_create_documento_tipo(self, sandbox):
        # review request asked tipo='documento' -> check whether it is accepted
        r = sandbox.post(f"{BASE_URL}/api/librerie/modelli", json={
            "tipo": "documento", "nome": "TEST_doc_tipo", "document_target_card": "quietanza"}, timeout=30)
        if r.status_code == 201:
            self.created.append(r.json()["id"])
        print("tipo=documento status", r.status_code, r.text[:200])
        assert r.status_code in (201, 422)

    def test_create_list_update(self, sandbox):
        r = sandbox.post(f"{BASE_URL}/api/librerie/modelli", json={
            "tipo": "word", "nome": "TEST_target_card", "corpo": "Ciao {cliente_nome}",
            "document_target_card": "quietanza"}, timeout=30)
        assert r.status_code == 201, r.text
        m = r.json()
        self.created.append(m["id"])
        assert m["document_target_card"] == "quietanza"
        lst = sandbox.get(f"{BASE_URL}/api/librerie/modelli", timeout=60).json()
        found = next(x for x in lst if x["id"] == m["id"])
        assert found["document_target_card"] == "quietanza"
        upd = {**{k: found.get(k) for k in ("tipo", "nome", "corpo")}, "document_target_card": "privacy_firmata"}
        u = sandbox.put(f"{BASE_URL}/api/librerie/modelli/{m['id']}", json=upd, timeout=30)
        assert u.status_code == 200, u.text
        assert u.json()["document_target_card"] == "privacy_firmata"
        g = sandbox.get(f"{BASE_URL}/api/librerie/modelli/{m['id']}", timeout=30).json()
        assert g["document_target_card"] == "privacy_firmata"
        # clear
        upd["document_target_card"] = None
        u = sandbox.put(f"{BASE_URL}/api/librerie/modelli/{m['id']}", json=upd, timeout=30)
        assert u.json()["document_target_card"] is None

    def test_tenant_isolation(self, sandbox):
        if not self.created:
            pytest.skip("nothing created")
        other = _login("superadmin@assicura.it", "superadmin123!")
        r = other.get(f"{BASE_URL}/api/librerie/modelli/{self.created[-1]}", timeout=30)
        assert r.status_code in (403, 404)

    def test_cleanup(self, sandbox):
        for mid in self.created:
            r = sandbox.delete(f"{BASE_URL}/api/librerie/modelli/{mid}", timeout=30)
            assert r.status_code == 200


# --- Public YouSign webhook ---
class TestWebhook:
    def test_unknown_request(self):
        r = requests.post(f"{BASE_URL}/api/esignature/webhook/yousign", json={
            "event_name": "signature_request.done", "data": {"signature_request": {"id": "does-not-exist"}}}, timeout=30)
        assert r.status_code == 200
        assert r.json() == {"ok": True, "ignored": "richiesta non trovata"}

    def test_empty_body(self):
        r = requests.post(f"{BASE_URL}/api/esignature/webhook/yousign", json={}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and "ignored" in d

    def test_alt_payload_shapes(self):
        r = requests.post(f"{BASE_URL}/api/esignature/webhook/yousign",
                          json={"signature_request_id": "nope", "data": None}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("ignored") == "richiesta non trovata"

    def test_non_dict_data(self):
        r = requests.post(f"{BASE_URL}/api/esignature/webhook/yousign",
                          json={"data": "stringa"}, timeout=30)
        print("non-dict data:", r.status_code, r.text[:200])
        assert r.status_code == 200

    def test_array_body(self):
        r = requests.post(f"{BASE_URL}/api/esignature/webhook/yousign", json=[1, 2], timeout=30)
        print("array body:", r.status_code, r.text[:200])
        assert r.status_code in (200, 422)


# --- orphan config on unknown tenant ---
def test_patch_unknown_tenant_no_orphan_config(sa):
    fake = "TEST-nonexistent-tenant-xyz"
    r = sa.patch(f"{BASE_URL}/api/super-admin/agenzie/{fake}", json={"firma_provider": "openapi"}, timeout=30)
    assert r.status_code == 404
    from pymongo import MongoClient
    c = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    doc = c["test_database"].azienda_config.find_one({"agenzia_tenant_id": fake})
    c["test_database"].azienda_config.delete_many({"agenzia_tenant_id": fake})
    assert doc is None, "PATCH on unknown tenant upserted an orphan azienda_config doc"
