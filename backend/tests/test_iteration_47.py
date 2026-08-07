"""Iteration 47: Auto-suggest polizza mancante durante import.

Test:
1. /import/apply con CSV contenente polizze inesistenti popola `unmatched` (non `errori`)
   con suggerimenti fuzzy per anagrafica cliente e numero polizza simile.
2. /import/match-manual crea titoli in stato_carico=in_attesa a partire dai match manuali.
3. Regressione: CSV con polizze esistenti → nessun unmatched, titoli creati.
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PWD = "Admin123!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


def _csv_missing_bytes():
    csv = (
        "Numero Polizza;Cliente;Data Scadenza;Data Effetto;Premio Lordo;Premio Netto;Provvigioni\n"
        "POL-INESISTENTE-999;ARSHAD HUSSNAIN;30/06/2026;01/07/2025;450,00;350,00;45,00\n"
        "POL-FANTASMA-100;VETTRICI MICHELE;15/08/2026;16/08/2025;800,50;650,00;80,00\n"
    )
    return csv.encode("utf-8")


def _mapping():
    return {
        "polizza_numero": "Numero Polizza",
        "cliente_nome": "Cliente",
        "scadenza": "Data Scadenza",
        "effetto": "Data Effetto",
        "importo_lordo": "Premio Lordo",
        "importo_netto": "Premio Netto",
        "provvigioni": "Provvigioni",
    }


# --- Test: apply con polizze non esistenti popola unmatched ---
class TestImportUnmatched:
    def test_apply_unmatched_populated_not_errori(self, headers):
        files = {"file": ("test_missing.csv", _csv_missing_bytes(), "text/csv")}
        data = {"mapping_json": __import__("json").dumps(_mapping())}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/apply",
                          headers=headers, files=files, data=data, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["totale_letti"] == 2
        assert body["creati"] == 0
        assert body["saltati"] == 0
        # Le righe orfane NON devono finire in "errori"
        assert body["errori"] == []
        unmatched = body["unmatched"]
        assert len(unmatched) == 2, f"expected 2 unmatched got {unmatched}"

        by_num = {u["polizza_numero_file"]: u for u in unmatched}
        assert "POL-INESISTENTE-999" in by_num
        assert "POL-FANTASMA-100" in by_num

        arshad = by_num["POL-INESISTENTE-999"]
        assert arshad["cliente_file"] == "ARSHAD HUSSNAIN"
        assert arshad["scadenza"] == "2026-06-30"
        assert arshad["effetto"] == "2025-07-01"
        assert arshad["importo_lordo"] == 450.0
        assert arshad["importo_netto"] == 350.0
        assert arshad["provvigioni"] == 45.0
        # Suggerimenti devono contenere polizze di ARSHAD HUSSNAIN
        assert len(arshad["suggerimenti"]) >= 1
        for s in arshad["suggerimenti"]:
            assert "id" in s and "numero_polizza" in s
            # Cliente_nome allegato al suggerimento
            assert "cliente_nome" in s

        vettrici = by_num["POL-FANTASMA-100"]
        assert vettrici["cliente_file"] == "VETTRICI MICHELE"
        assert len(vettrici["suggerimenti"]) >= 1
        # Store batch_id for next test via class attribute
        TestImportUnmatched.batch_id = body["batch_id"]
        TestImportUnmatched.arshad_suggerimento = arshad["suggerimenti"][0]
        TestImportUnmatched.arshad_row = arshad


# --- Test: match-manual crea titoli ---
class TestManualMatch:
    def test_match_manual_creates_titolo(self, headers):
        # Riusa il batch_id e suggerimento dal test precedente
        sug = getattr(TestImportUnmatched, "arshad_suggerimento", None)
        row = getattr(TestImportUnmatched, "arshad_row", None)
        assert sug and row, "Dipende da TestImportUnmatched"
        batch_id = TestImportUnmatched.batch_id

        payload = {
            "batch_id": batch_id,
            "matches": [{
                "polizza_id": sug["id"],
                "effetto": row["effetto"],
                "scadenza": row["scadenza"],
                "importo_lordo": row["importo_lordo"],
                "importo_netto": row["importo_netto"],
                "provvigioni": row["provvigioni"],
                "polizza_numero_file": row["polizza_numero_file"],
            }],
        }
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/match-manual",
                          headers=headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["creati"] == 1
        assert body["errori"] == []

        # Verify persistence: cerca titolo con batch_id + scadenza specifica
        r2 = requests.get(f"{BASE_URL}/api/carichi-mensili",
                          headers=headers, params={"stato_carico": "in_attesa"}, timeout=30)
        assert r2.status_code == 200
        righe = r2.json()["righe"]
        matched = [t for t in righe if t.get("import_batch_id") == batch_id
                   and t.get("scadenza") == "2026-06-30"]
        assert len(matched) >= 1
        titolo = matched[0]
        assert titolo["stato_carico"] == "in_attesa"
        assert titolo["polizza_id"] == sug["id"]
        assert titolo["importo_lordo"] == 450.0

        # Cleanup: elimina il titolo creato
        try:
            requests.delete(f"{BASE_URL}/api/carichi-mensili/{titolo['id']}",
                            headers=headers, timeout=15)
        except Exception:
            pass

    def test_match_manual_empty_matches(self, headers):
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/match-manual",
                          headers=headers,
                          json={"batch_id": "fake-batch", "matches": []}, timeout=15)
        assert r.status_code == 200
        assert r.json() == {"ok": True, "creati": 0}


# --- Regression: polizze esistenti no unmatched ---
class TestRegressionAllMatched:
    def test_apply_all_valid_no_unmatched(self, headers):
        # Trova una polizza reale
        r = requests.get(f"{BASE_URL}/api/polizze", headers=headers,
                         params={"limit": 1}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        polizze = data if isinstance(data, list) else data.get("righe") or data.get("polizze") or []
        assert polizze, "Nessuna polizza per regression test"
        p = polizze[0]
        num = p["numero_polizza"]

        csv = (
            "Numero Polizza;Cliente;Data Scadenza;Data Effetto;Premio Lordo;Premio Netto;Provvigioni\n"
            f"{num};TEST_CLIENT;31/12/2026;01/01/2026;100,00;80,00;10,00\n"
        ).encode("utf-8")
        files = {"file": ("regression.csv", csv, "text/csv")}
        body_data = {"mapping_json": __import__("json").dumps(_mapping())}
        r2 = requests.post(f"{BASE_URL}/api/carichi-mensili/import/apply",
                           headers=headers, files=files, data=body_data, timeout=30)
        assert r2.status_code == 200, r2.text
        b = r2.json()
        assert b["creati"] == 1
        assert b["unmatched"] == []
        assert b["errori"] == []

        # Cleanup: elimina il titolo appena creato
        batch = b["batch_id"]
        r3 = requests.get(f"{BASE_URL}/api/carichi-mensili",
                          headers=headers, params={"stato_carico": "in_attesa"}, timeout=15)
        for t in r3.json().get("righe", []):
            if t.get("import_batch_id") == batch:
                requests.delete(f"{BASE_URL}/api/carichi-mensili/{t['id']}",
                                headers=headers, timeout=10)


# --- Validazione ---
class TestValidations:
    def test_apply_without_polizza_numero_mapping(self, headers):
        csv = b"a;b\n1;2\n"
        files = {"file": ("bad.csv", csv, "text/csv")}
        data = {"mapping_json": '{"cliente_nome":"a"}'}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/apply",
                          headers=headers, files=files, data=data, timeout=15)
        assert r.status_code == 400
