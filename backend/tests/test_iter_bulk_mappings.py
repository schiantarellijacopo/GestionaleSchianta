"""Test bulk save mappings + apply-async for Wizard Mapping OMNIA fix."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
EMAIL = "jacopo@schiantarelli.it"
PASSWORD = "NtdZs5ilxTSP"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, data
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_bulk_save_mappings(headers):
    payload = {
        "flusso": "omnia",
        "items": [
            {"tipo": "collaboratore", "valore_flusso": "ZZTEST1", "entita_id": None},
            {"tipo": "collaboratore", "valore_flusso": "ZZTEST2", "entita_id": None},
        ],
    }
    r = requests.post(f"{BASE_URL}/api/import/mappings/bulk", headers=headers, json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body.get("saved") == 2, body
    assert body.get("total") == 2, body
    assert body.get("errors") == [] or body.get("errors") is None

    # GET and verify both exist, have id and manual=true
    r2 = requests.get(f"{BASE_URL}/api/import/mappings?tipo=collaboratore", headers=headers, timeout=30)
    assert r2.status_code == 200, r2.text
    rows = r2.json() if isinstance(r2.json(), list) else r2.json().get("items", [])
    found = {row["valore_flusso"]: row for row in rows if row.get("valore_flusso") in ("ZZTEST1", "ZZTEST2")}
    assert set(found.keys()) == {"ZZTEST1", "ZZTEST2"}, list(found.keys())
    for k, row in found.items():
        assert row.get("id"), f"{k} missing id: {row}"
        assert row.get("manual") is True, f"{k} manual not True: {row}"

    # Cleanup
    for row in found.values():
        rd = requests.delete(f"{BASE_URL}/api/import/mappings/{row['id']}", headers=headers, timeout=30)
        assert rd.status_code in (200, 204), rd.text

    # Verify gone
    r3 = requests.get(f"{BASE_URL}/api/import/mappings?tipo=collaboratore", headers=headers, timeout=30)
    rows3 = r3.json() if isinstance(r3.json(), list) else r3.json().get("items", [])
    leftover = [r for r in rows3 if r.get("valore_flusso") in ("ZZTEST1", "ZZTEST2")]
    assert leftover == [], leftover


def test_apply_async_returns_fast(headers):
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/import/mappings/apply-async", headers=headers, json={}, timeout=15)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("job_id"), body
    assert body.get("status") in ("running", "queued", "started", "pending"), body
    assert elapsed < 10, f"apply-async took {elapsed}s"

    job_id = body["job_id"]
    # Poll a few times - should not go to error
    final_status = None
    for _ in range(6):
        time.sleep(5)
        rs = requests.get(f"{BASE_URL}/api/import/job/{job_id}", headers=headers, timeout=15)
        assert rs.status_code == 200, rs.text
        st = rs.json()
        final_status = st.get("status")
        assert final_status != "error", st
        if final_status == "done":
            result = st.get("result", {})
            # keys expected on done
            print("Job done result keys:", list(result.keys()) if isinstance(result, dict) else result)
            break
    print(f"Final poll status: {final_status}")
    assert final_status in ("running", "done"), final_status
