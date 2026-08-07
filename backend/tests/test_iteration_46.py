"""Iteration 46 tests: Import Excel/CSV, filtri date custom, nuove colonne carichi mensili."""
import io
import json
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@assicura.it", "password": "Admin123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# GET /carichi-mensili - date range filter + new columns
# ============================================================================
class TestListaCarichi:
    def test_lista_default(self, headers):
        r = requests.get(f"{BASE_URL}/api/carichi-mensili?stato_carico=tutti", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "righe" in data and "totale" in data

    def test_date_range_dal_al(self, headers):
        r = requests.get(f"{BASE_URL}/api/carichi-mensili",
                         params={"stato_carico": "tutti", "dal": "2026-01-01", "al": "2026-12-31"},
                         headers=headers)
        assert r.status_code == 200
        data = r.json()
        # tutte le righe devono avere scadenza in range (o esserci 0 righe)
        for row in data["righe"][:20]:
            s = row.get("scadenza")
            if s:
                assert "2026-01-01" <= s <= "2026-12-31", f"scadenza fuori range: {s}"

    def test_new_columns_present(self, headers):
        r = requests.get(f"{BASE_URL}/api/carichi-mensili?stato_carico=tutti&dal=2026-01-01&al=2026-12-31",
                         headers=headers)
        assert r.status_code == 200
        righe = r.json()["righe"]
        if not righe:
            pytest.skip("Nessuna riga disponibile per il test colonne")
        row = righe[0]
        for k in ("data_decorrenza", "tipo_rinnovo", "variazione_badge",
                  "compagnia_nome", "polizza_ramo"):
            assert k in row, f"Campo mancante: {k}"

    def test_variazione_badge_nuova(self, headers):
        r = requests.get(f"{BASE_URL}/api/carichi-mensili?stato_carico=tutti&dal=2026-01-01&al=2026-12-31",
                         headers=headers)
        righe = r.json()["righe"]
        if not righe:
            pytest.skip()
        # Almeno una riga deve avere un badge valido
        badges = {row.get("variazione_badge") for row in righe}
        valid = {"🆕 Nuova", "🟢 Regolare"}
        assert any(b == "🆕 Nuova" or (b and "Aumento" in b) or (b and "Riduzione" in b) or b in valid
                   for b in badges), f"Badge non validi: {badges}"


# ============================================================================
# POST /carichi-mensili/import/preview
# ============================================================================
class TestImportPreview:
    def _csv_bytes(self, sep=";"):
        content = f"Numero Polizza{sep}Cliente{sep}Scadenza{sep}Premio Lordo\n"
        content += f"POL-TEST-001{sep}Mario Rossi{sep}30/06/2026{sep}500,00\n"
        content += f"POL-TEST-002{sep}Anna Bianchi{sep}15/07/2026{sep}1.250,50\n"
        return content.encode("utf-8")

    def test_preview_csv_semicolon(self, headers):
        files = {"file": ("test.csv", self._csv_bytes(";"), "text/csv")}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/preview",
                          files=files, headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total_rows"] == 2
        assert "Numero Polizza" in data["headers"]
        m = data["suggested_mapping"]
        assert m.get("polizza_numero") == "Numero Polizza"
        assert m.get("cliente_nome") == "Cliente"
        assert m.get("scadenza") == "Scadenza"
        assert m.get("importo_lordo") == "Premio Lordo"

    def test_preview_csv_comma(self, headers):
        files = {"file": ("test.csv", self._csv_bytes(","), "text/csv")}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/preview",
                          files=files, headers=headers)
        assert r.status_code == 200
        assert r.json()["total_rows"] == 2

    def test_preview_empty_file(self, headers):
        files = {"file": ("empty.csv", b"", "text/csv")}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/preview",
                          files=files, headers=headers)
        assert r.status_code in (400, 200)  # se 200, headers vuoti


# ============================================================================
# POST /carichi-mensili/import/apply
# ============================================================================
class TestImportApply:
    def _get_existing_polizza(self, headers):
        r = requests.get(f"{BASE_URL}/api/carichi-mensili?stato_carico=tutti",
                         headers=headers)
        for row in r.json().get("righe", []):
            if row.get("polizza_numero"):
                return row["polizza_numero"]
        return None

    def test_apply_with_valid_polizza(self, headers):
        pol_num = self._get_existing_polizza(headers)
        if not pol_num:
            pytest.skip("Nessuna polizza esistente")
        content = f"Numero Polizza;Cliente;Scadenza;Premio Lordo\n{pol_num};Mario;30/06/2026;500,00\n".encode()
        files = {"file": ("test.csv", content, "text/csv")}
        mapping = {
            "polizza_numero": "Numero Polizza",
            "cliente_nome": "Cliente",
            "scadenza": "Scadenza",
            "importo_lordo": "Premio Lordo",
        }
        data = {"mapping_json": json.dumps(mapping)}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/apply",
                          files=files, data=data, headers=headers)
        assert r.status_code == 200, r.text
        res = r.json()
        assert "creati" in res and "saltati" in res and "errori" in res
        assert res["creati"] + len(res["errori"]) + res["saltati"] >= 1

    def test_apply_no_polizza_in_mapping(self, headers):
        files = {"file": ("test.csv", b"a;b\n1;2\n", "text/csv")}
        data = {"mapping_json": json.dumps({"cliente_nome": "a"})}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/apply",
                          files=files, data=data, headers=headers)
        assert r.status_code == 400

    def test_apply_invalid_mapping_json(self, headers):
        files = {"file": ("test.csv", b"a\n1\n", "text/csv")}
        data = {"mapping_json": "not-json"}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/apply",
                          files=files, data=data, headers=headers)
        assert r.status_code == 400

    def test_apply_unknown_polizza(self, headers):
        content = b"Numero Polizza;Scadenza;Premio Lordo\nPOL-NON-ESISTE-XYZ;30/06/2026;500,00\n"
        files = {"file": ("test.csv", content, "text/csv")}
        data = {"mapping_json": json.dumps({
            "polizza_numero": "Numero Polizza",
            "scadenza": "Scadenza",
            "importo_lordo": "Premio Lordo",
        })}
        r = requests.post(f"{BASE_URL}/api/carichi-mensili/import/apply",
                          files=files, data=data, headers=headers)
        assert r.status_code == 200
        res = r.json()
        assert res["creati"] == 0
        assert len(res["errori"]) >= 1
        assert "non trovata" in res["errori"][0]["errore"].lower()
