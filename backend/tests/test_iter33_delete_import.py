"""iter33 — test:
   (1) DELETE anagrafica con cascade + force flag
   (2) Import Anagrafiche Excel/CSV preview + execute (skip/overwrite policies)
   (3) Regression smoke: iter30 (openapi.it, iban lookup) + iter31 (check-duplicate + overwrite_id)
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://whatsapp-crm-146.preview.emergentagent.com"

MELLO_ID = "e15e701a-4b0f-490d-9848-23c7e9147500"
MELLO_CF = "01075160141"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@assicura.it", "password": "Admin123!"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.json()
    return tok


@pytest.fixture(scope="session")
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# (A) DELETE anagrafica: 409 su record con collegati, 200 con force=true
# ============================================================
class TestDeleteAnagrafica:
    def test_delete_mello_without_force_returns_409(self, hdr):
        r = requests.delete(f"{BASE_URL}/api/anagrafiche/{MELLO_ID}", headers=hdr)
        assert r.status_code == 409, f"expected 409 got {r.status_code}: {r.text[:200]}"
        data = r.json()
        detail = data.get("detail", data)
        collegati = detail.get("collegati", {})
        assert "polizze" in collegati
        assert isinstance(collegati["polizze"], int)
        # MELLO deve avere almeno 1 polizza (dai dati backend)
        assert collegati["polizze"] >= 1, "MELLO dovrebbe avere polizze collegate"

    def test_delete_non_existing_returns_404(self, hdr):
        r = requests.delete(f"{BASE_URL}/api/anagrafiche/non-existent-id-xyz", headers=hdr)
        assert r.status_code == 404

    def test_create_then_delete_no_cascade(self, hdr):
        # crea anagrafica senza polizze
        payload = {
            "tipo": "persona_fisica",
            "nome": "TESTFIX",
            "cognome": "REGRESSION",
            "codice_fiscale": "TSTFXR80A01H501Z",
        }
        r = requests.post(f"{BASE_URL}/api/anagrafiche", json=payload, headers=hdr)
        assert r.status_code == 201, r.text[:200]
        aid = r.json()["id"]
        # delete senza force → deve andare (nessun collegato)
        r2 = requests.delete(f"{BASE_URL}/api/anagrafiche/{aid}", headers=hdr)
        assert r2.status_code == 200, r2.text[:200]
        # verifica cancellazione
        r3 = requests.get(f"{BASE_URL}/api/anagrafiche/{aid}", headers=hdr)
        assert r3.status_code == 404


# ============================================================
# (B) IMPORT Excel/CSV — preview + execute
# ============================================================
CSV_CONTENT_SIMPLE = (
    "Nome;Cognome;Codice Fiscale;Email\n"
    "MARIO;ROSSI;RSSMRA80A01H501U;mario@test.it\n"
    "LUIGI;VERDI;VRDLGU75B15L219X;luigi@test.it\n"
)

CSV_CONTENT_AMBIGUOUS = (
    "colonna A;foo123;Codice Fiscale;Nome;Cognome\n"
    "xxx;yyy;ZZZZZZ80A01H501T;PIPPO;PLUTO\n"
)

CSV_CONTENT_MELLO = (
    "Ragione Sociale;Codice Fiscale;Partita IVA;Email\n"
    "A. S. D. MELLO IMPORT TEST;01075160141;01075160141;overwritetest@x.it\n"
)


class TestImportPreview:
    def test_preview_simple_csv_automapping(self, hdr):
        files = {"file": ("test.csv", CSV_CONTENT_SIMPLE, "text/csv")}
        r = requests.post(f"{BASE_URL}/api/import/anagrafiche/preview",
                          files=files, headers=hdr)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # deve rilevare 4 header
        assert len(data["headers"]) == 4
        # tutti gli header standard devono avere canonical
        detected = {d["header"]: d["canonical"] for d in data["detected"]}
        assert detected.get("Nome") == "nome"
        assert detected.get("Cognome") == "cognome"
        assert detected.get("Codice Fiscale") == "codice_fiscale"
        assert detected.get("Email") == "email"
        # total rows == 2
        assert data["total_rows"] == 2
        # available_fields presente per Select
        assert isinstance(data.get("available_fields"), list)
        assert "codice_fiscale" in data["available_fields"]
        # rows preview con normalized
        assert len(data["rows"]) == 2
        assert data["rows"][0]["normalized"]["codice_fiscale"] == "RSSMRA80A01H501U"

    def test_preview_ambiguous_headers(self, hdr):
        files = {"file": ("amb.csv", CSV_CONTENT_AMBIGUOUS, "text/csv")}
        r = requests.post(f"{BASE_URL}/api/import/anagrafiche/preview",
                          files=files, headers=hdr)
        assert r.status_code == 200
        data = r.json()
        detected = {d["header"]: d["canonical"] for d in data["detected"]}
        # 'colonna A' e 'foo123' NON devono essere riconosciute
        assert detected.get("colonna A") is None
        assert detected.get("foo123") is None
        # 'Codice Fiscale' sì
        assert detected.get("Codice Fiscale") == "codice_fiscale"

    def test_preview_duplicates_detection(self, hdr):
        files = {"file": ("mello.csv", CSV_CONTENT_MELLO, "text/csv")}
        r = requests.post(f"{BASE_URL}/api/import/anagrafiche/preview",
                          files=files, headers=hdr)
        assert r.status_code == 200
        data = r.json()
        # deve rilevare almeno 1 duplicato (MELLO CF=01075160141)
        assert data["duplicates_stimati"] >= 1, f"expected >= 1 dup, got {data['duplicates_stimati']}"


class TestImportExecute:
    def test_execute_skip_policy_creates_new(self, hdr):
        files = {"file": ("test.csv", CSV_CONTENT_SIMPLE, "text/csv")}
        mapping = {
            "Nome": "nome",
            "Cognome": "cognome",
            "Codice Fiscale": "codice_fiscale",
            "Email": "email",
        }
        import json
        data_form = {"mapping_json": json.dumps(mapping), "policy": "skip"}
        r = requests.post(f"{BASE_URL}/api/import/anagrafiche/execute",
                          files=files, data=data_form, headers=hdr)
        assert r.status_code == 200, r.text[:300]
        report = r.json()
        assert report["total_rows"] == 2
        # con policy=skip su CF NUOVI, devono essere create almeno le 2 (se non già presenti)
        # ma potrebbero essere già in DB → almeno created+skipped == 2
        assert report["created"] + report["skipped"] >= 2
        # se create, ripulisci
        # trova le anagrafiche appena create per CF
        for cf in ["RSSMRA80A01H501U", "VRDLGU75B15L219X"]:
            r_search = requests.get(
                f"{BASE_URL}/api/anagrafiche/check-duplicate",
                params={"codice_fiscale": cf}, headers=hdr,
            )
            if r_search.status_code == 200 and r_search.json().get("existing"):
                aid = r_search.json()["existing"]["id"]
                requests.delete(f"{BASE_URL}/api/anagrafiche/{aid}?force=true", headers=hdr)

    def test_execute_ignore_field(self, hdr):
        """Se una colonna è mappata a __ignore__ (assente dal mapping), NON deve andare al server."""
        files = {"file": ("test.csv", CSV_CONTENT_SIMPLE, "text/csv")}
        # Omettiamo 'Email' dal mapping (equivale a __ignore__ in UI)
        mapping = {
            "Nome": "nome",
            "Cognome": "cognome",
            "Codice Fiscale": "codice_fiscale",
        }
        import json
        data_form = {"mapping_json": json.dumps(mapping), "policy": "skip"}
        r = requests.post(f"{BASE_URL}/api/import/anagrafiche/execute",
                          files=files, data=data_form, headers=hdr)
        assert r.status_code == 200
        # Cleanup
        for cf in ["RSSMRA80A01H501U", "VRDLGU75B15L219X"]:
            r_search = requests.get(f"{BASE_URL}/api/anagrafiche/check-duplicate",
                                    params={"codice_fiscale": cf}, headers=hdr)
            if r_search.status_code == 200 and r_search.json().get("existing"):
                aid = r_search.json()["existing"]["id"]
                # verifica che email NON sia stata salvata
                r_get = requests.get(f"{BASE_URL}/api/anagrafiche/{aid}", headers=hdr)
                if r_get.status_code == 200:
                    email = r_get.json().get("email")
                    assert not email or "mario@test.it" not in email
                requests.delete(f"{BASE_URL}/api/anagrafiche/{aid}?force=true", headers=hdr)


# ============================================================
# (C) REGRESSION smoke: iter30 + iter31
# ============================================================
class TestRegression:
    def test_check_duplicate_iter31(self, hdr):
        r = requests.get(f"{BASE_URL}/api/anagrafiche/check-duplicate",
                         params={"codice_fiscale": MELLO_CF}, headers=hdr)
        assert r.status_code == 200
        data = r.json()
        assert data["existing"] is not None
        assert data["existing"]["id"] == MELLO_ID
        assert data["match_on"] == "codice_fiscale"

    def test_iban_lookup_iter30(self, hdr):
        # ABI Intesa Sanpaolo
        r = requests.get(f"{BASE_URL}/api/utility/iban-lookup",
                         params={"iban": "IT60X0542811101000000123456"}, headers=hdr)
        # Non blocking se il servizio è disabled, ma non deve dare 500
        assert r.status_code in (200, 404, 400), f"got {r.status_code}: {r.text[:200]}"

    def test_openapi_it_smoke_iter30(self, hdr):
        # Endpoint openapi.it (may return 400 for invalid, but never 500)
        r = requests.get(f"{BASE_URL}/api/utility/openapi/company",
                         params={"partita_iva": "00795070143"}, headers=hdr)
        assert r.status_code in (200, 400, 404, 501, 503), \
            f"got {r.status_code}: {r.text[:200]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
