"""Tests iter31 — feature: gestione duplicati anagrafiche (OCR / Excel import).

Endpoint testati:
  - GET /api/anagrafiche/check-duplicate?codice_fiscale=X&tipo=persona_fisica
  - GET /api/anagrafiche/check-duplicate?partita_iva=Y&tipo=persona_giuridica
  - POST /api/anagrafiche con overwrite_id (UPDATE invece di INSERT)
  - POST /api/anagrafiche con overwrite_id inesistente (404)
  - POST /api/anagrafiche senza overwrite_id (INSERT, regression)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Anagrafiche note esistenti (da testing brief)
EXISTING_CF_PF = "01075160141"  # A. S. D. MELLO — persona fisica
EXISTING_PIVA_PG = "00795070143"  # AZ. AGRICOLA DI LIBERA DUILIO
EXISTING_PF_ID = "e15e701a-4b0f-490d-9848-23c7e9147500"
EXISTING_PG_ID = "4871fe9f-7f57-43b3-a80a-e27eeec2c3e9"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={
        "email": "admin@assicura.it", "password": "Admin123!"
    }, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def created_ids():
    ids = []
    yield ids
    # Cleanup: elimina tutte le anagrafiche create
    # (ma non toccare EXISTING_PF_ID / EXISTING_PG_ID)
    r = requests.post(f"{API}/auth/login", json={
        "email": "admin@assicura.it", "password": "Admin123!"
    }, timeout=15)
    if r.status_code == 200:
        tok = r.json().get("access_token") or r.json().get("token")
        h = {"Authorization": f"Bearer {tok}"}
        for aid in ids:
            try:
                requests.delete(f"{API}/anagrafiche/{aid}", headers=h, timeout=10)
            except Exception:
                pass


# ============================================================
# GET /api/anagrafiche/check-duplicate
# ============================================================
class TestCheckDuplicate:
    def test_check_dup_cf_existing_pf(self, auth):
        r = requests.get(
            f"{API}/anagrafiche/check-duplicate",
            params={"codice_fiscale": EXISTING_CF_PF, "tipo": "persona_fisica"},
            headers=auth, timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["match_on"] == "codice_fiscale"
        assert data["existing"] is not None
        e = data["existing"]
        assert e["codice_fiscale"] == EXISTING_CF_PF
        assert e["id"] == EXISTING_PF_ID
        assert "ragione_sociale" in e
        assert "updated_at" in e or "created_at" in e

    def test_check_dup_piva_existing_pg(self, auth):
        r = requests.get(
            f"{API}/anagrafiche/check-duplicate",
            params={"partita_iva": EXISTING_PIVA_PG, "tipo": "persona_giuridica"},
            headers=auth, timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["match_on"] == "partita_iva"
        assert data["existing"] is not None
        e = data["existing"]
        assert e["partita_iva"] == EXISTING_PIVA_PG
        assert e["id"] == EXISTING_PG_ID

    def test_check_dup_cf_not_existing(self, auth):
        r = requests.get(
            f"{API}/anagrafiche/check-duplicate",
            params={"codice_fiscale": "ZZZZZZ00Z00Z000Z", "tipo": "persona_fisica"},
            headers=auth, timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["existing"] is None
        assert data["match_on"] is None

    def test_check_dup_piva_not_existing(self, auth):
        r = requests.get(
            f"{API}/anagrafiche/check-duplicate",
            params={"partita_iva": "99999999999", "tipo": "persona_giuridica"},
            headers=auth, timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["existing"] is None
        assert data["match_on"] is None

    def test_check_dup_no_params(self, auth):
        r = requests.get(
            f"{API}/anagrafiche/check-duplicate", headers=auth, timeout=10,
        )
        assert r.status_code == 200
        assert r.json() == {"existing": None, "match_on": None}

    def test_check_dup_pg_priority_piva_over_cf(self, auth):
        """Per persona_giuridica, se sia CF che P.IVA sono forniti, prevale P.IVA."""
        # Fornisci P.IVA esistente + CF INESISTENTE → deve matchare su piva
        r = requests.get(
            f"{API}/anagrafiche/check-duplicate",
            params={
                "codice_fiscale": "ZZZZZZ00Z00Z000Z",
                "partita_iva": EXISTING_PIVA_PG,
                "tipo": "persona_giuridica",
            },
            headers=auth, timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["match_on"] == "partita_iva"
        assert data["existing"]["partita_iva"] == EXISTING_PIVA_PG

    def test_check_dup_pf_priority_cf_over_piva(self, auth):
        """Per persona_fisica, se sia CF che P.IVA sono forniti, prevale CF."""
        r = requests.get(
            f"{API}/anagrafiche/check-duplicate",
            params={
                "codice_fiscale": EXISTING_CF_PF,
                "partita_iva": "99999999999",
                "tipo": "persona_fisica",
            },
            headers=auth, timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["match_on"] == "codice_fiscale"
        assert data["existing"]["codice_fiscale"] == EXISTING_CF_PF


# ============================================================
# POST /api/anagrafiche con overwrite_id
# ============================================================
class TestOverwriteAnagrafica:
    def test_create_new_pf_no_dup_regression(self, auth, created_ids):
        """Regression: POST senza overwrite_id crea nuova anagrafica."""
        payload = {
            "tipo": "persona_fisica",
            "cognome": "TEST_ITER31",
            "nome": "REGRESSION",
            "codice_fiscale": f"ZZZTEST00Z00{int(time.time()) % 10000:04d}Z",
        }
        r = requests.post(f"{API}/anagrafiche", json=payload, headers=auth, timeout=15)
        assert r.status_code == 201, f"expected 201, got {r.status_code}: {r.text}"
        data = r.json()
        assert "id" in data
        assert data["cognome"] == "TEST_ITER31"
        created_ids.append(data["id"])

        # Verify persistenza via GET
        rg = requests.get(f"{API}/anagrafiche/{data['id']}", headers=auth, timeout=10)
        assert rg.status_code == 200
        assert rg.json()["cognome"] == "TEST_ITER31"

    def test_overwrite_existing_by_id(self, auth, created_ids):
        """Crea una anagrafica, poi la sovrascrive tramite overwrite_id."""
        # STEP 1: crea anagrafica
        cf1 = f"ZZOVW{int(time.time()) % 100000:05d}Z000Z"
        payload_create = {
            "tipo": "persona_fisica",
            "cognome": "TEST_ITER31_OVW",
            "nome": "ORIGINAL",
            "codice_fiscale": cf1,
            "email": "original@test.local",
        }
        rc = requests.post(f"{API}/anagrafiche", json=payload_create, headers=auth, timeout=15)
        assert rc.status_code == 201
        new_id = rc.json()["id"]
        created_ids.append(new_id)
        original_updated_at = rc.json().get("updated_at") or rc.json().get("created_at")

        time.sleep(1)  # per far cambiare updated_at

        # STEP 2: overwrite tramite overwrite_id
        payload_overwrite = {
            "tipo": "persona_fisica",
            "cognome": "TEST_ITER31_OVW",
            "nome": "UPDATED",
            "codice_fiscale": cf1,
            "email": "updated@test.local",
            "telefono": "0123456789",
            "overwrite_id": new_id,
        }
        ro = requests.post(f"{API}/anagrafiche", json=payload_overwrite, headers=auth, timeout=15)
        assert ro.status_code == 201, f"overwrite failed: {ro.status_code} {ro.text}"
        data = ro.json()
        # ID deve rimanere lo stesso
        assert data["id"] == new_id, "L'id non deve cambiare dopo overwrite"
        # I nuovi campi devono essere applicati
        assert data["nome"] == "UPDATED"
        assert data["email"] == "updated@test.local"
        assert data["telefono"] == "0123456789"
        # updated_at deve essere aggiornato
        assert data.get("updated_at") is not None
        if original_updated_at:
            assert data["updated_at"] != original_updated_at or data["updated_at"] > original_updated_at

        # STEP 3: verifica persistenza via GET
        rg = requests.get(f"{API}/anagrafiche/{new_id}", headers=auth, timeout=10)
        assert rg.status_code == 200
        got = rg.json()
        assert got["nome"] == "UPDATED"
        assert got["email"] == "updated@test.local"

        # STEP 4: non deve essere stata creata una nuova anagrafica (stessa CF)
        rl = requests.get(f"{API}/anagrafiche", params={"q": cf1}, headers=auth, timeout=10)
        assert rl.status_code == 200
        matches = [a for a in rl.json() if a.get("codice_fiscale") == cf1]
        assert len(matches) == 1, f"Expected 1 anagrafica with CF {cf1}, found {len(matches)}"

    def test_overwrite_nonexistent_id_returns_404(self, auth):
        payload = {
            "tipo": "persona_fisica",
            "cognome": "TEST_ITER31_404",
            "nome": "NON",
            "codice_fiscale": "ZZZZZZ00Z00Z000Z",
            "overwrite_id": "non-existent-id-12345",
        }
        r = requests.post(f"{API}/anagrafiche", json=payload, headers=auth, timeout=15)
        assert r.status_code == 404
        detail = r.json().get("detail", "")
        assert "non trovata" in detail.lower() or "non-existent-id-12345" in detail

    def test_overwrite_existing_pf_from_brief(self, auth):
        """Sovrascrittura di anagrafica esistente EXISTING_PF_ID (A. S. D. MELLO).
        Salva prima i dati originali, sovrascrive con nuovi valori, poi ripristina."""
        # Salva stato originale
        r0 = requests.get(f"{API}/anagrafiche/{EXISTING_PF_ID}", headers=auth, timeout=10)
        assert r0.status_code == 200
        original = r0.json()

        try:
            payload = {
                "tipo": original.get("tipo", "persona_fisica"),
                "cognome": original.get("cognome") or "MELLO",
                "nome": original.get("nome") or "TEST",
                "codice_fiscale": EXISTING_CF_PF,
                "ragione_sociale": original.get("ragione_sociale"),
                "email": "test_iter31_overwrite@example.local",
                "overwrite_id": EXISTING_PF_ID,
            }
            r = requests.post(f"{API}/anagrafiche", json=payload, headers=auth, timeout=15)
            assert r.status_code == 201, f"overwrite failed: {r.status_code} {r.text}"
            data = r.json()
            assert data["id"] == EXISTING_PF_ID
            assert data["email"] == "test_iter31_overwrite@example.local"
        finally:
            # Ripristina i dati originali (rimuovendo overwrite_id, tenendo l'id)
            restore_body = {k: v for k, v in original.items() if k not in ("relazioni_risolte",)}
            requests.put(
                f"{API}/anagrafiche/{EXISTING_PF_ID}",
                json=restore_body,
                headers=auth, timeout=15,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
