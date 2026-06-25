"""Shared pytest fixtures and constants for backend tests.

Credentials are sourced from environment variables to avoid hardcoded secrets.
Defaults match the seeded admin user used during local development.
"""
import os
import pytest
import requests

# Best-effort load of REACT_APP_BACKEND_URL from /app/frontend/.env when running pytest
# directly from /app/backend (where dotenv only points to backend/.env).
try:
    from dotenv import load_dotenv
    if not os.environ.get("REACT_APP_BACKEND_URL"):
        load_dotenv("/app/frontend/.env", override=False)
except Exception:
    pass

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

# Test credentials — pulled from env, never hardcoded.
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")


@pytest.fixture(scope="session")
def admin_credentials():
    return {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s
