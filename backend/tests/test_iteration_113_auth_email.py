# Iteration 113: password reset non-enumerable + operator creation with credentials email (MOCK)
import os, uuid, subprocess, time
import pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@assicura.it", "password": "Admin123!"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code}")
    tok = r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


# --- Password reset request: non-enumerable ---
def test_reset_request_non_enumerable():
    r1 = requests.post(f"{BASE_URL}/api/auth/password-reset/request",
                       json={"email": f"nonesiste.{uuid.uuid4().hex[:6]}@example.com"})
    r2 = requests.post(f"{BASE_URL}/api/auth/password-reset/request", json={"email": "admin@assicura.it"})
    r3 = requests.post(f"{BASE_URL}/api/auth/password-reset/request", json={})
    assert r1.status_code == r2.status_code == r3.status_code == 200
    assert r1.json() == r2.json() == r3.json()
    assert r1.json()["ok"] is True and "message" in r1.json()


def test_reset_confirm_invalid_token():
    r = requests.post(f"{BASE_URL}/api/auth/password-reset/confirm",
                      json={"token": "TOKENFINTO", "new_password": "Password123"})
    assert r.status_code == 400
    assert "non valido" in r.json()["detail"].lower()


def test_reset_confirm_short_password():
    r = requests.post(f"{BASE_URL}/api/auth/password-reset/confirm",
                      json={"token": "x", "new_password": "short"})
    assert r.status_code == 400


# --- Admin login still works after reset request (request must not change password) ---
def test_admin_login_still_ok():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    assert r.status_code == 200


# --- Operator creation sends credentials email (MOCK) + cleanup ---
def test_create_operator_sends_mock_email(admin_session):
    email = f"operatore.test.{uuid.uuid4().hex[:8]}@example.com"
    r = admin_session.post(f"{BASE_URL}/api/auth/users", json={
        "email": email, "name": "Operatore Test", "role": "collaboratore",
        "accesso_software": True, "password": "TempPass123"})
    assert r.status_code == 201, r.text
    data = r.json()
    uid = data["id"]
    try:
        assert data["email"] == email
        assert "password_hash" not in data and "_id" not in data
        time.sleep(1.5)
        log = subprocess.run(["bash", "-c", f"grep -a '{email}' /var/log/supervisor/backend.err.log | tail -5"],
                             capture_output=True, text=True).stdout
        print(log)
        assert "[EMAIL MOCK]" in log
        assert "Il tuo accesso" in log
        # operator can login with temp password
        lr = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "TempPass123"})
        assert lr.status_code == 200
    finally:
        d = admin_session.delete(f"{BASE_URL}/api/auth/users/{uid}")
        assert d.status_code in (200, 204)
    users = admin_session.get(f"{BASE_URL}/api/auth/users").json()
    assert all(u.get("id") != uid for u in users)
