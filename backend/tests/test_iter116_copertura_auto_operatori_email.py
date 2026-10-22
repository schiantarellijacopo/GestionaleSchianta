# Iter116: copertura auto-invio config + auto-invia-ora, audit operatori tenant isolation, update_user duplicate email
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
GIORNO_TITOLI = "2026-10-12"  # principal tenant has 2 eligible titoli on this day


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
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


@pytest.fixture(scope="module")
def qa():
    return _login("jacopo@schiantarelli.it", "NtdZs5ilxTSP")


# --- Scheduler config: copertura_auto_* fields ---
class TestCoperturaConfig:
    def test_get_config_fields(self, admin):
        r = admin.get(f"{API}/alert-scheduler/config")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("copertura_auto_attivo", "copertura_auto_hour", "copertura_auto_minute",
                  "alert_scheduler_attivo", "alert_scheduler_hour", "alert_scheduler_minute"):
            assert k in d
        assert isinstance(d["copertura_auto_attivo"], bool)
        assert isinstance(d["copertura_auto_hour"], int)

    def test_get_config_dipendente_allowed(self, dip):
        r = dip.get(f"{API}/alert-scheduler/config")
        assert r.status_code == 200
        assert "copertura_auto_hour" in r.json()

    def test_put_clamp_persist_and_restore(self, admin, qa):
        orig = admin.get(f"{API}/alert-scheduler/config").json()
        qa_before = qa.get(f"{API}/alert-scheduler/config").json()
        try:
            r = admin.put(f"{API}/alert-scheduler/config",
                          json={"copertura_auto_hour": 30, "copertura_auto_minute": -5})
            assert r.status_code == 200, r.text
            assert r.json()["copertura_auto_hour"] == 23
            assert r.json()["copertura_auto_minute"] == 0
            r = admin.put(f"{API}/alert-scheduler/config",
                          json={"copertura_auto_hour": 19, "copertura_auto_minute": 45})
            assert r.json()["copertura_auto_hour"] == 19
            g = admin.get(f"{API}/alert-scheduler/config").json()
            assert g["copertura_auto_hour"] == 19 and g["copertura_auto_minute"] == 45
            # alert scheduler fields untouched
            assert g["alert_scheduler_hour"] == orig["alert_scheduler_hour"]
            # other tenant not affected
            qa_after = qa.get(f"{API}/alert-scheduler/config").json()
            assert qa_after["copertura_auto_hour"] == qa_before["copertura_auto_hour"]
            assert qa_after["copertura_auto_minute"] == qa_before["copertura_auto_minute"]
        finally:
            admin.put(f"{API}/alert-scheduler/config", json={
                "copertura_auto_attivo": orig["copertura_auto_attivo"],
                "copertura_auto_hour": orig["copertura_auto_hour"],
                "copertura_auto_minute": orig["copertura_auto_minute"]})

    def test_put_toggle_attivo(self, admin):
        orig = admin.get(f"{API}/alert-scheduler/config").json()["copertura_auto_attivo"]
        try:
            r = admin.put(f"{API}/alert-scheduler/config", json={"copertura_auto_attivo": not orig})
            assert r.status_code == 200
            assert r.json()["copertura_auto_attivo"] is (not orig)
        finally:
            admin.put(f"{API}/alert-scheduler/config", json={"copertura_auto_attivo": orig})

    def test_put_empty_400(self, admin):
        r = admin.put(f"{API}/alert-scheduler/config", json={})
        assert r.status_code == 400

    def test_put_collaboratore_forbidden(self, collab):
        r = collab.put(f"{API}/alert-scheduler/config", json={"copertura_auto_hour": 10})
        assert r.status_code == 403


# --- POST /comunicazioni-copertura/auto-invia-ora ---
class TestAutoInviaOra:
    created: list = []

    def test_invalid_giorno_400(self, admin):
        r = admin.post(f"{API}/comunicazioni-copertura/auto-invia-ora", json={"giorno": "12-10-2026"})
        assert r.status_code == 400

    def test_non_admin_403(self, collab):
        r = collab.post(f"{API}/comunicazioni-copertura/auto-invia-ora", json={})
        assert r.status_code == 403

    def test_empty_day(self, admin):
        r = admin.post(f"{API}/comunicazioni-copertura/auto-invia-ora", json={"giorno": "2000-01-01"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True and d["giorno"] == "2000-01-01"
        assert d["gruppi"] == 0 and d["inviati"] == 0 and d["errori"] == 0

    def test_no_body_defaults_today(self, admin):
        r = admin.post(f"{API}/comunicazioni-copertura/auto-invia-ora")
        assert r.status_code == 200, r.text
        assert len(r.json()["giorno"]) == 10

    def test_other_tenant_does_not_touch_principal(self, qa, admin):
        r = qa.post(f"{API}/comunicazioni-copertura/auto-invia-ora", json={"giorno": GIORNO_TITOLI})
        assert r.status_code == 200, r.text
        assert r.json()["gruppi"] == 0
        # principal genera still sees the titoli
        g = admin.get(f"{API}/comunicazioni-copertura/genera", params={"giorno": GIORNO_TITOLI})
        assert g.status_code == 200
        assert len(g.json().get("gruppi", g.json() if isinstance(g.json(), list) else [])) >= 1

    def test_run_day_with_titoli_then_idempotent(self, admin, qa):
        r = admin.post(f"{API}/comunicazioni-copertura/auto-invia-ora", json={"giorno": GIORNO_TITOLI})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["gruppi"] >= 1
        assert d["inviati"] + d["errori"] == d["gruppi"]
        lst = admin.get(f"{API}/comunicazioni-copertura").json()
        items = lst if isinstance(lst, list) else lst.get("items", [])
        mine = [c for c in items if c.get("giorno") == GIORNO_TITOLI]
        assert len(mine) == d["gruppi"]
        for c in mine:
            TestAutoInviaOra.created.append(c["id"])
            assert c["stato"] in ("inviata", "errore")
            assert c.get("created_by_name")
            if c["stato"] == "errore":
                assert c.get("email_errore")
        # numero is unique
        nums = [c["numero"] for c in items]
        assert len(nums) == len(set(nums))
        # other tenant can't see them
        q = qa.get(f"{API}/comunicazioni-copertura").json()
        q_items = q if isinstance(q, list) else q.get("items", [])
        assert not any(c["id"] in TestAutoInviaOra.created for c in q_items)
        # idempotent: re-run creates nothing
        r2 = admin.post(f"{API}/comunicazioni-copertura/auto-invia-ora", json={"giorno": GIORNO_TITOLI})
        assert r2.status_code == 200
        assert r2.json()["gruppi"] == 0

    def test_cleanup(self, admin):
        for cid in TestAutoInviaOra.created:
            r = admin.delete(f"{API}/comunicazioni-copertura/{cid}")
            assert r.status_code in (200, 400)


# --- GET /audit/operatori tenant isolation ---
class TestAuditOperatori:
    def test_principal_admin_only_own(self, admin):
        r = admin.get(f"{API}/audit/operatori")
        assert r.status_code == 200, r.text
        emails = {u["email"] for u in r.json()}
        assert "admin@assicura.it" in emails
        assert "jacopo@schiantarelli.it" not in emails
        assert not any(e.endswith("@import.assicurapro.it") for e in emails)
        assert all(u["role"] in ("admin", "collaboratore", "dipendente") for u in r.json())

    def test_other_tenant_admin_only_own(self, qa):
        r = qa.get(f"{API}/audit/operatori")
        assert r.status_code == 200, r.text
        emails = {u["email"] for u in r.json()}
        assert "jacopo@schiantarelli.it" in emails
        assert "admin@assicura.it" not in emails
        assert "collaboratore@assicura.it" not in emails

    def test_non_admin_forbidden(self, collab):
        assert collab.get(f"{API}/audit/operatori").status_code == 403


# --- PUT /auth/users/{uid} duplicate email ---
class TestUpdateUserEmail:
    @pytest.fixture(scope="class")
    def collab_user(self, admin):
        users = admin.get(f"{API}/auth/users").json()
        u = next((x for x in users if x.get("email") == "collaboratore@assicura.it"), None)
        if not u:
            pytest.skip("collaboratore not found")
        return u

    def test_dup_same_tenant_400(self, admin, collab_user):
        r = admin.put(f"{API}/auth/users/{collab_user['id']}", json={"email": "  Admin@Assicura.IT "})
        assert r.status_code == 400, r.text
        assert "già in uso" in r.json()["detail"]

    def test_dup_other_tenant_400_not_500(self, admin, collab_user):
        r = admin.put(f"{API}/auth/users/{collab_user['id']}", json={"email": "jacopo@schiantarelli.it"})
        assert r.status_code == 400, r.text

    def test_own_email_normalized_ok(self, admin, collab_user):
        r = admin.put(f"{API}/auth/users/{collab_user['id']}", json={"email": " COLLABORATORE@assicura.it "})
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "collaboratore@assicura.it"
        assert "password_hash" not in r.json()

    def test_empty_email_ignored(self, admin, collab_user):
        r = admin.put(f"{API}/auth/users/{collab_user['id']}", json={"email": "", "name": collab_user["name"]})
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "collaboratore@assicura.it"

    def test_login_still_works(self):
        r = requests.post(f"{API}/auth/login", json={"email": "collaboratore@assicura.it", "password": "Collab123!"})
        assert r.status_code == 200
