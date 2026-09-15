"""Iter92 - Firma elettronica OpenAPI (create/status/list), Dashboard counter,
regressioni Brogliaccio collab / dedup libretto / provvigioni collab-only."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
ADMIN = {"email": "admin@assicura.it", "password": "Admin123!"}
POLIZZA_ID = "a9183098-c6e6-4218-9ab2-312eccfb2d65"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        sess.headers.update({"Authorization": f"Bearer {tok}"})
    return sess


@pytest.fixture(scope="module")
def pdf_allegato_id(s):
    r = s.get(f"{BASE_URL}/api/allegati", params={"entita_tipo": "polizza", "entita_id": POLIZZA_ID}, timeout=30)
    assert r.status_code == 200, r.text
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    pdfs = [a for a in items if "pdf" in (a.get("content_type") or "").lower()
            or (a.get("nome_file") or "").lower().endswith(".pdf")]
    assert pdfs, f"No PDF allegato found on polizza {POLIZZA_ID}"
    return pdfs[0]["id"], items


# ---------- eSignature ----------
class TestEsignature:
    _created = {}

    def test_invia_non_pdf_400(self, s, pdf_allegato_id):
        _pdf, items = pdf_allegato_id
        non_pdf = next((a for a in items if "pdf" not in (a.get("content_type") or "").lower()
                        and not (a.get("nome_file") or "").lower().endswith(".pdf")), None)
        if not non_pdf:
            pytest.skip("Nessun allegato non-PDF disponibile")
        r = s.post(f"{BASE_URL}/api/esignature/invia", json={
            "allegato_id": non_pdf["id"], "invia_whatsapp": False, "invia_email": False,
            "firmatario": {"name": "Mario", "surname": "Rossi", "email": "test@example.com", "mobile": "+393331234567"},
        }, timeout=60)
        assert r.status_code == 400, r.text

    def test_invia_ok(self, s, pdf_allegato_id):
        pdf_id, _ = pdf_allegato_id
        r = s.post(f"{BASE_URL}/api/esignature/invia", json={
            "allegato_id": pdf_id, "invia_whatsapp": False, "invia_email": False,
            "firmatario": {"name": "Mario", "surname": "Rossi",
                           "email": "test@example.com", "mobile": "+393331234567"},
        }, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("signature_id"), data
        assert data.get("stato") in ("WAIT_VALIDATION", "WAIT_SIGNERS", "WAIT_SIGNATURE")
        assert (data.get("signing_url") or "").startswith("https://test.esign.openapi.com"), data.get("signing_url")
        TestEsignature._created["id"] = data["id"]
        TestEsignature._created["sig"] = data["signature_id"]

    def test_stato(self, s):
        req_id = TestEsignature._created.get("id")
        if not req_id:
            pytest.skip("no request created")
        r = s.get(f"{BASE_URL}/api/esignature/stato/{req_id}", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "stato" in d and "allegato_firmato_id" in d
        assert d["allegato_firmato_id"] is None  # sandbox, not signed

    def test_lista(self, s):
        r = s.get(f"{BASE_URL}/api/esignature/richieste",
                  params={"entita_tipo": "polizza", "entita_id": POLIZZA_ID}, timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert any(x.get("id") == TestEsignature._created.get("id") for x in items), "created request non presente nella lista"


# ---------- Dashboard counter ----------
def test_dashboard_firme_in_attesa(s):
    r = s.get(f"{BASE_URL}/api/insights/documenti-mancanti", timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "totali" in d and "firme_in_attesa" in d["totali"]
    assert isinstance(d["totali"]["firme_in_attesa"], int)
    assert d["totali"]["firme_in_attesa"] >= 1
    lst = d.get("firme_in_attesa") or []
    assert isinstance(lst, list) and len(lst) >= 1
    it = lst[0]
    for k in ("id", "nome_file", "firmatario_nome", "stato", "signing_url", "created_at"):
        assert k in it, f"missing key {k} in firme_in_attesa[0]: {it}"


# ---------- Regression: Brogliaccio collab filter ----------
def test_brogliaccio_endpoint(s):
    r = s.get(f"{BASE_URL}/api/contabilita/brogliaccio", timeout=60)
    assert r.status_code == 200, r.text


# ---------- Regression: /api/collaboratori returns all users; frontend filters role=='collaboratore' ----------
def test_collaboratori_endpoint_ok(s):
    r = s.get(f"{BASE_URL}/api/collaboratori", timeout=30)
    assert r.status_code == 200
    items = r.json() if isinstance(r.json(), list) else []
    assert any((it.get("role") or "").lower() == "collaboratore" for it in items), \
        "Nessun user con role=collaboratore (frontend filtra sui role=='collaboratore')"
