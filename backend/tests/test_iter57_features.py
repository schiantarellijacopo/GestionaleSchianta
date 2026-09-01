"""
Iteration 57 tests:
- Redazione segreti in /librerie/comunicazioni e /librerie/azienda per admin
- Super Admin /chiavi-api (403 admin, 200 super, persistenza PUT)
- /whatsapp-evo/config 403 admin
- Anagrafica overwrite merge conservativo
- Marketing presentazioni (genera brand 3 slide + poll + download pptx/pdf + delete)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"
SUPER_EMAIL = "superadmin@assicura.it"
SUPER_PASSWORD = "superadmin123!"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def super_token():
    return _login(SUPER_EMAIL, SUPER_PASSWORD)


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def super_h(super_token):
    return {"Authorization": f"Bearer {super_token}"}


# --- Redazione segreti per admin normale ---
class TestRedazioneSegreti:
    def test_librerie_comunicazioni_admin_no_twilio_spoki(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/librerie/comunicazioni", headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in list(data.keys()):
            assert not k.startswith("twilio_"), f"twilio_* exposto: {k}"
            assert not k.startswith("spoki_"), f"spoki_* exposto: {k}"
        assert "whatsapp_provider" in data, "whatsapp_provider deve essere presente"

    def test_librerie_azienda_admin_no_secrets(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/librerie/azienda", headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        forbidden = [
            "firma_api_token", "firma_base_url", "firma_environment", "firma_provider",
            "firma_webhook_secret", "smtp_password", "imap_password",
            "twilio_account_sid", "twilio_auth_token", "spoki_api_key",
        ]
        for f in forbidden:
            assert f not in data, f"campo segreto esposto ad admin: {f}"
        # Deve contenere dati azienda normali
        assert "ragione_sociale" in data


# --- Chiavi API super admin ---
class TestChiaviApi:
    def test_admin_403_chiavi_api(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/super-admin/chiavi-api", headers=admin_h, timeout=15)
        assert r.status_code == 403

    def test_super_admin_200_chiavi_api(self, super_h):
        r = requests.get(f"{BASE_URL}/api/super-admin/chiavi-api", headers=super_h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Campi previsti presenti (anche se vuoti)
        expected_keys = [
            "firma_api_token", "firma_base_url", "firma_environment", "firma_provider",
            "twilio_account_sid", "twilio_auth_token", "twilio_sms_from",
            "spoki_api_key", "whatsapp_provider",
            "evolution_server_url", "evolution_api_key", "evolution_source",
        ]
        for k in expected_keys:
            assert k in data, f"chiave mancante: {k}"

    def test_put_chiavi_api_persistenza_e_ripristino(self, super_h):
        # snapshot
        r = requests.get(f"{BASE_URL}/api/super-admin/chiavi-api", headers=super_h, timeout=15)
        assert r.status_code == 200
        original = r.json()
        original_sms_from = original.get("twilio_sms_from", "") or ""

        test_value = "+390000000000"
        # PUT test value
        r2 = requests.put(
            f"{BASE_URL}/api/super-admin/chiavi-api",
            headers=super_h,
            json={"twilio_sms_from": test_value},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text

        # Verify persisted
        r3 = requests.get(f"{BASE_URL}/api/super-admin/chiavi-api", headers=super_h, timeout=15)
        assert r3.status_code == 200
        assert r3.json().get("twilio_sms_from") == test_value

        # Ripristina
        r4 = requests.put(
            f"{BASE_URL}/api/super-admin/chiavi-api",
            headers=super_h,
            json={"twilio_sms_from": original_sms_from},
            timeout=15,
        )
        assert r4.status_code == 200

        r5 = requests.get(f"{BASE_URL}/api/super-admin/chiavi-api", headers=super_h, timeout=15)
        assert r5.json().get("twilio_sms_from", "") == original_sms_from

    def test_admin_put_comunicazioni_non_modifica_twilio(self, admin_h, super_h):
        # snapshot da super admin
        r = requests.get(f"{BASE_URL}/api/super-admin/chiavi-api", headers=super_h, timeout=15)
        assert r.status_code == 200
        before = r.json()

        # admin tenta di modificare
        payload = {
            "twilio_account_sid": "HACKED_SID",
            "twilio_auth_token": "HACKED_TOKEN",
            "whatsapp_provider": "twilio",  # anche whatsapp_provider dovrebbe essere super-only
        }
        r2 = requests.put(f"{BASE_URL}/api/librerie/comunicazioni", headers=admin_h, json=payload, timeout=15)
        # Non deve dare errore ma nemmeno persistere i segreti
        assert r2.status_code in (200, 204), r2.text

        # verifica valori invariati via super admin
        r3 = requests.get(f"{BASE_URL}/api/super-admin/chiavi-api", headers=super_h, timeout=15)
        after = r3.json()
        assert after.get("twilio_account_sid") == before.get("twilio_account_sid"), "twilio_account_sid modificato da admin!"
        assert after.get("twilio_auth_token") == before.get("twilio_auth_token"), "twilio_auth_token modificato da admin!"


# --- WhatsApp Evo config ---
class TestWhatsappEvoConfig:
    def test_admin_put_config_403(self, admin_h):
        # Non modifico nulla, mando payload minimo, mi aspetto 403
        r = requests.put(
            f"{BASE_URL}/api/whatsapp-evo/config",
            headers=admin_h,
            json={"server_url": "http://noop.local", "api_key": "noop", "source": "self_hosted"},
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"


# --- Anagrafica merge conservativo overwrite ---
class TestAnagraficaMerge:
    def test_overwrite_merge_conservativo(self, admin_h):
        # Creazione anagrafica base
        payload = {
            "nominativo": "TEST_MERGE Iter57",
            "ragione_sociale": "TEST_MERGE Iter57",
            "tipo_soggetto": "privato",
            "email": "test_merge_iter57@example.com",
            "professione": "Ingegnere",
            "tags": ["tagA"],
        }
        r = requests.post(f"{BASE_URL}/api/anagrafiche", headers=admin_h, json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        anag_id = created.get("id") or created.get("_id")
        assert anag_id

        try:
            # Overwrite: email vuota, professione vuota, aggiungiamo iban + tag nuovo
            overwrite_payload = {
                "nominativo": "TEST_MERGE Iter57",
                "ragione_sociale": "TEST_MERGE Iter57",
                "tipo_soggetto": "privato",
                "email": "",
                "professione": "",
                "iban": "IT60X0542811101000000123456",
                "tags": ["tagB"],
                "overwrite_id": anag_id,
            }
            r2 = requests.post(f"{BASE_URL}/api/anagrafiche", headers=admin_h, json=overwrite_payload, timeout=20)
            assert r2.status_code in (200, 201), r2.text

            # GET verifica
            r3 = requests.get(f"{BASE_URL}/api/anagrafiche/{anag_id}", headers=admin_h, timeout=15)
            assert r3.status_code == 200, r3.text
            data = r3.json()
            assert data.get("email") == "test_merge_iter57@example.com", f"email persa: {data.get('email')}"
            assert (data.get("professione") or "").lower() == "ingegnere", f"professione persa: {data.get('professione')}"
            assert data.get("iban") == "IT60X0542811101000000123456", f"iban non aggiunto: {data.get('iban')}"
            tags = data.get("tags") or []
            assert "tagA" in tags and "tagB" in tags, f"tags non uniti: {tags}"
        finally:
            requests.delete(f"{BASE_URL}/api/anagrafiche/{anag_id}?force=true", headers=admin_h, timeout=15)


# --- Marketing presentazioni ---
class TestMarketingPresentazioni:
    def test_genera_brand_poll_download_delete(self, admin_h):
        # Genera
        payload = {
            "modalita": "punti",
            "contenuto": "1) garanzia A 2) garanzia B 3) assistenza",
            "stile": "brand",
            "n_slides": 3,
        }
        r = requests.post(f"{BASE_URL}/api/marketing/presentazioni/genera", headers=admin_h, json=payload, timeout=30)
        assert r.status_code == 202, f"expected 202, got {r.status_code}: {r.text[:300]}"
        job = r.json()
        pid = job.get("id")
        assert pid, f"no id in response: {job}"

        # Poll
        ready = False
        state = None
        for _ in range(30):  # ~90s
            time.sleep(3)
            rl = requests.get(f"{BASE_URL}/api/marketing/presentazioni", headers=admin_h, timeout=15)
            assert rl.status_code == 200
            items = rl.json()
            if isinstance(items, dict):
                items = items.get("items", [])
            match = next((x for x in items if x.get("id") == pid), None)
            if match:
                state = match.get("stato") or match.get("status")
                if state in ("ready", "completed", "done"):
                    ready = True
                    break
                if state in ("error", "failed"):
                    pytest.fail(f"generation failed: {match}")
        assert ready, f"presentation not ready in time, last state: {state}"

        try:
            # Download pptx
            rp = requests.get(f"{BASE_URL}/api/marketing/presentazioni/{pid}/file?fmt=pptx", headers=admin_h, timeout=30)
            assert rp.status_code == 200, rp.text[:200]
            ct = rp.headers.get("content-type", "")
            assert "presentation" in ct or "pptx" in ct or "octet-stream" in ct, f"content-type inatteso: {ct}"
            assert len(rp.content) > 1000, "pptx troppo piccolo"

            # Download pdf
            rpdf = requests.get(f"{BASE_URL}/api/marketing/presentazioni/{pid}/file?fmt=pdf", headers=admin_h, timeout=30)
            assert rpdf.status_code == 200, rpdf.text[:200]
            ctpdf = rpdf.headers.get("content-type", "")
            assert "pdf" in ctpdf or "octet-stream" in ctpdf, f"content-type pdf inatteso: {ctpdf}"
            assert rpdf.content[:4] == b"%PDF" or len(rpdf.content) > 1000
        finally:
            rd = requests.delete(f"{BASE_URL}/api/marketing/presentazioni/{pid}", headers=admin_h, timeout=15)
            assert rd.status_code in (200, 204), rd.text
