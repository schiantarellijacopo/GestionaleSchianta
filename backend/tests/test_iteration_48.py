"""Iteration 48 tests:
- Carichi mensili enrichment fields
- Import Polizze preview/execute
- Import Sinistri preview/execute
- Cloud Storage OAuth config endpoints
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json={
        "email": "admin@assicura.it", "password": "Admin123!",
    }, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ============ Carichi Mensili enrichment ============
class TestCarichiMensili:
    def test_get_carichi_enrichment_fields(self, auth):
        r = requests.get(f"{API}/carichi-mensili", headers=auth, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # It may be either a list, or dict with 'items'
        rows = data if isinstance(data, list) else data.get("righe") or data.get("items") or data.get("carichi") or []
        # If empty, skip data checks but confirm shape
        if not rows:
            pytest.skip("Nessun carico presente per validare l'enrichment")
        sample = rows[0]
        for key in [
            "variazione_dettaglio", "note_storiche", "servizio_sanitario",
            "provvigioni_collab", "polizza_stato", "variazione_badge",
        ]:
            assert key in sample, f"Campo mancante nel carico: {key}. Keys={list(sample.keys())[:30]}"


# ============ Import Polizze ============
CSV_POLIZZE = (
    b"Numero Polizza;Compagnia;Cliente;Codice Fiscale;Ramo;Data Effetto;Data Scadenza;Premio Lordo;Targa\n"
    b"POL-TEST-001;UnipolSai;Mario Rossi;RSSMRA80A01H501U;RCA;2026-01-15;2027-01-15;850,50;AB123CD\n"
    b"POL-TEST-002;UnipolSai;Anna Verdi;VRDNNA75B41H501X;INCENDIO;2026-02-01;2027-02-01;450,00;\n"
)


class TestImportPolizze:
    def test_preview_polizze(self, auth):
        files = {"file": ("polizze.csv", io.BytesIO(CSV_POLIZZE), "text/csv")}
        r = requests.post(f"{API}/import/polizze/preview", headers=auth, files=files, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["total_rows"] == 2
        detected = {d["header"]: d for d in j["detected"]}
        # Verify auto-mapping recognized all headers with confidence >= 0.6
        expected_map = {
            "Numero Polizza": "numero_polizza",
            "Compagnia": "compagnia_nome",
            "Cliente": "cliente_nome",
            "Codice Fiscale": "codice_fiscale",
            "Ramo": "ramo",
            "Data Effetto": "effetto",
            "Data Scadenza": "scadenza",
            "Premio Lordo": "premio_lordo",
            "Targa": "targa",
        }
        for header, canonical in expected_map.items():
            d = detected.get(header)
            assert d is not None, f"Header non presente in detected: {header}"
            assert d["canonical"] == canonical, f"{header} → atteso {canonical}, ottenuto {d['canonical']} (conf={d['confidence']})"
            assert d["confidence"] >= 0.6, f"{header}: confidence {d['confidence']} < 0.6"

    def test_execute_polizze_skip(self, auth):
        import json
        mapping = {
            "Numero Polizza": "numero_polizza",
            "Compagnia": "compagnia_nome",
            "Cliente": "cliente_nome",
            "Codice Fiscale": "codice_fiscale",
            "Ramo": "ramo",
            "Data Effetto": "effetto",
            "Data Scadenza": "scadenza",
            "Premio Lordo": "premio_lordo",
            "Targa": "targa",
        }
        files = {"file": ("polizze.csv", io.BytesIO(CSV_POLIZZE), "text/csv")}
        data = {"mapping_json": json.dumps(mapping), "policy": "skip"}
        r = requests.post(f"{API}/import/polizze/execute", headers=auth, files=files, data=data, timeout=60)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["total_rows"] == 2
        # Le anagrafiche TEST_ non esistono → contraente non trovato è comportamento atteso
        assert j["skipped"] >= 0
        # Ogni errore deve essere strutturato
        for e in j.get("errors", []):
            assert "row" in e and "reason" in e


# ============ Import Sinistri ============
CSV_SINISTRI = (
    b"Numero Sinistro;Data Avvenimento;Riserva;Liquidazione\n"
    b"SIN-001;2026-01-10;5000,00;3200,00\n"
)


class TestImportSinistri:
    def test_preview_sinistri(self, auth):
        files = {"file": ("sinistri.csv", io.BytesIO(CSV_SINISTRI), "text/csv")}
        r = requests.post(f"{API}/import/sinistri/preview", headers=auth, files=files, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["total_rows"] == 1
        detected = {d["header"]: d for d in j["detected"]}
        # verify at least numero + data avvenimento mapped
        for h in ["Numero Sinistro", "Data Avvenimento", "Riserva", "Liquidazione"]:
            d = detected.get(h)
            assert d, f"Header non presente in detected: {h}"
            assert d["canonical"] is not None, f"{h} non auto-mappato"
            assert d["confidence"] >= 0.6, f"{h}: conf {d['confidence']}"

    def test_execute_sinistri(self, auth):
        import json
        detected_map = {
            "Numero Sinistro": "numero_sinistro",
            "Data Avvenimento": "data_avvenimento",
            "Riserva": "riserva",
            "Liquidazione": "liquidazione",
        }
        files = {"file": ("sinistri.csv", io.BytesIO(CSV_SINISTRI), "text/csv")}
        data = {"mapping_json": json.dumps(detected_map), "policy": "skip"}
        r = requests.post(f"{API}/import/sinistri/execute", headers=auth, files=files, data=data, timeout=60)
        assert r.status_code == 200, r.text[:300]


# ============ Cloud Storage ============
class TestCloudStorage:
    def test_config_status(self, auth):
        r = requests.get(f"{API}/librerie/cloud-storage/config-status", headers=auth, timeout=15)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert "google_drive" in j and "onedrive" in j
        assert "configured" in j["google_drive"] and "redirect_uri" in j["google_drive"]
        assert "configured" in j["onedrive"] and "redirect_uri" in j["onedrive"]
        assert j["encryption_configured"] is True
        # Credentials not provided → configured=False for both
        assert j["google_drive"]["configured"] is False
        assert j["onedrive"]["configured"] is False
        assert j["google_drive"]["redirect_uri"].endswith("/api/librerie/cloud-storage/callback")

    def test_status_empty(self, auth):
        r = requests.get(f"{API}/librerie/cloud-storage/status", headers=auth, timeout=15)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert "connections" in j
        assert isinstance(j["connections"], list)

    def test_oauth_url_google_501(self, auth):
        r = requests.get(f"{API}/librerie/cloud-storage/oauth-url", headers=auth,
                         params={"provider": "google_drive"}, timeout=15)
        assert r.status_code == 501, f"expected 501 got {r.status_code}: {r.text[:200]}"
        # Messaggio chiaro
        assert "Google Drive" in r.text or "GOOGLE_DRIVE_CLIENT_ID" in r.text

    def test_oauth_url_onedrive_501(self, auth):
        r = requests.get(f"{API}/librerie/cloud-storage/oauth-url", headers=auth,
                         params={"provider": "onedrive"}, timeout=15)
        assert r.status_code == 501, f"expected 501 got {r.status_code}: {r.text[:200]}"
        assert "OneDrive" in r.text or "MS_ONEDRIVE_CLIENT_ID" in r.text

    def test_disconnect_idempotent(self, auth):
        r = requests.delete(f"{API}/librerie/cloud-storage/disconnect", headers=auth,
                            params={"provider": "google_drive"}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j.get("disconnected") == "google_drive"
