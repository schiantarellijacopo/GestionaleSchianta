"""Iteration 51 tests: Portale Cliente + Chat Portale + Dashboard tasks + Alert preset welcome + credenziali + Archivio Targhe upload public + sollecito veicoli."""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"
PORTALE_EMAIL = "marco.rossi@demo.it"
PORTALE_PASSWORD = "RSSMRC75H10F205X"
MARCO_AID = "93b73085-100f-4c78-883a-e6cefea49c72"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def portale_token():
    r = requests.post(f"{API}/portale/auth/login", json={"email": PORTALE_EMAIL, "password": PORTALE_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"portale login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert "access_token" in data
    assert data["cliente"]["id"] == MARCO_AID
    return data["access_token"]


@pytest.fixture(scope="session")
def portale_headers(portale_token):
    return {"Authorization": f"Bearer {portale_token}"}


# ------- Portale endpoints --------
class TestPortaleCliente:
    def test_login_returns_token_and_cliente(self, portale_token):
        assert portale_token

    def test_me(self, portale_headers):
        r = requests.get(f"{API}/portale/me", headers=portale_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        # tollerante a shape: cerchiamo id o email in root o dentro 'cliente'
        payload = j.get("cliente") if isinstance(j, dict) and "cliente" in j else j
        assert payload.get("id") == MARCO_AID or payload.get("anagrafica_id") == MARCO_AID or payload.get("email") == PORTALE_EMAIL, j

    def test_polizze(self, portale_headers):
        r = requests.get(f"{API}/portale/polizze?includi_storiche=true", headers=portale_headers, timeout=20)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(r.json(), (list, dict))

    def test_titoli(self, portale_headers):
        r = requests.get(f"{API}/portale/titoli", headers=portale_headers, timeout=20)
        assert r.status_code == 200, r.text[:300]

    def test_documenti_only_visible(self, portale_headers):
        r = requests.get(f"{API}/portale/documenti", headers=portale_headers, timeout=20)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        items = data if isinstance(data, list) else data.get("documenti") or data.get("items") or []
        for d in items:
            # se il campo esiste deve essere True
            if "visibile_cliente" in d:
                assert d["visibile_cliente"] is True

    def test_richiesta_modifica_anagrafica(self, portale_headers, admin_headers):
        payload = {"campo": "telefono", "valore_richiesto": "3339998877", "note": "TEST_iter51"}
        r = requests.put(f"{API}/portale/anagrafica/richiesta", headers=portale_headers, json=payload, timeout=15)
        # 200 o 201
        assert r.status_code in (200, 201), r.text[:400]
        # admin vede la richiesta
        r2 = requests.get(f"{API}/richieste-cliente", headers=admin_headers, timeout=15)
        assert r2.status_code == 200, r2.text[:300]
        lst = r2.json()
        items = lst if isinstance(lst, list) else lst.get("items") or []
        found = any(
            (it.get("anagrafica_id") == MARCO_AID or it.get("aid") == MARCO_AID or it.get("cliente_id") == MARCO_AID)
            and it.get("stato") in ("da_verificare", "pending", "nuova")
            for it in items
        )
        assert found, f"richiesta non trovata tra {len(items)} items"


# ------- Chat portale --------
class TestChatPortale:
    def test_client_send_message(self, portale_headers):
        r = requests.post(f"{API}/portale/chat/messaggi", headers=portale_headers,
                          json={"testo": "TEST_iter51 messaggio dal cliente"}, timeout=15)
        assert r.status_code in (200, 201), r.text[:400]

    def test_client_list_messages(self, portale_headers):
        r = requests.get(f"{API}/portale/chat/messaggi", headers=portale_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        items = data if isinstance(data, list) else data.get("messaggi") or data.get("items") or []
        assert any("TEST_iter51" in (m.get("testo") or "") for m in items), f"messaggio non trovato: {items[:3]}"

    def test_admin_list_clienti_with_unread(self, admin_headers):
        r = requests.get(f"{API}/chat-portale/clienti", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        items = data if isinstance(data, list) else data.get("clienti") or data.get("items") or []
        marco = next((c for c in items if c.get("anagrafica_id") == MARCO_AID or c.get("id") == MARCO_AID), None)
        assert marco is not None, f"Marco non presente. items sample: {items[:3]}"
        assert (marco.get("unread") or marco.get("non_letti") or 0) >= 1

    def test_admin_reply(self, admin_headers):
        r = requests.post(f"{API}/chat-portale/{MARCO_AID}/messaggi", headers=admin_headers,
                          json={"testo": "TEST_iter51 risposta admin"}, timeout=15)
        assert r.status_code in (200, 201), r.text[:400]

    def test_client_sees_admin_reply_and_unread_zero(self, portale_headers):
        r = requests.get(f"{API}/portale/chat/messaggi", headers=portale_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("messaggi") or data.get("items") or []
        assert any("TEST_iter51 risposta admin" in (m.get("testo") or "") for m in items)
        # unread zero dopo la GET
        r2 = requests.get(f"{API}/portale/chat/unread", headers=portale_headers, timeout=15)
        assert r2.status_code == 200, r2.text[:300]
        val = r2.json()
        n = val.get("unread") if isinstance(val, dict) else val
        assert n == 0, f"expected 0 unread, got {val}"


# ------- Alert preset welcome_portale --------
class TestAlertPresetWelcomePortale:
    def test_catalog_has_welcome(self, admin_headers):
        r = requests.get(f"{API}/alert-presets/catalog", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        items = data if isinstance(data, list) else data.get("presets") or data.get("items") or []
        wp = next((p for p in items if p.get("preset_key") == "welcome_portale" or p.get("key") == "welcome_portale"), None)
        assert wp is not None, f"welcome_portale non trovato tra {[p.get('preset_key') or p.get('key') for p in items]}"
        canali = wp.get("canali") or []
        dest = wp.get("destinatari") or []
        assert "email" in canali and "whatsapp" in canali
        assert "cliente" in dest


# ------- Invio credenziali portale --------
class TestInviaCredenziali:
    def test_endpoint_does_not_crash(self, admin_headers):
        r = requests.post(f"{API}/anagrafiche/{MARCO_AID}/invia-credenziali-portale",
                          headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text[:400]
        j = r.json()
        assert "ok" in j
        # deve avere info per email e whatsapp
        assert "email_inviata" in j or "email_errore" in j
        assert "whatsapp_inviato" in j or "whatsapp_errore" in j


# ------- Dashboard tasks --------
class TestDashboardTasks:
    def test_tasks_has_richieste_portale(self, admin_headers):
        r = requests.get(f"{API}/dashboard/tasks", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        items = data if isinstance(data, list) else data.get("tasks") or data.get("items") or []
        t = next((x for x in items if x.get("key") == "richieste_portale"), None)
        assert t is not None, f"richieste_portale non trovato. keys: {[x.get('key') for x in items]}"
        assert t.get("color") == "violet"
        assert t.get("url") == "/richieste-cliente"
        assert "count" in t


# ------- Archivio Targhe upload public --------
class TestArchivioTargheUpload:
    def test_info_without_token_401(self):
        r = requests.get(f"{API}/public/upload-doc/info", timeout=15)
        assert r.status_code in (401, 403, 422), r.status_code

    def test_info_invalid_token_401(self):
        r = requests.get(f"{API}/public/upload-doc/info?token=invalid_xxx", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_info_with_valid_token(self):
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            # carica JWT_SECRET da backend/.env
            from dotenv import load_dotenv
            load_dotenv("/app/backend/.env", override=False)
            from sollecito_veicoli import build_upload_token  # type: ignore
        except Exception as e:
            pytest.skip(f"impossibile importare build_upload_token: {e}")
        try:
            token = build_upload_token("test-app-1")
        except Exception as e:
            pytest.skip(f"firma build_upload_token: {e}")
        r = requests.get(f"{API}/public/upload-doc/info?token={token}", timeout=15)
        # con token firmato correttamente ma applicazione fake, l'endpoint può ritornare 404/400 (non 401 signature)
        assert r.status_code != 401 or "Signature" not in r.text, r.text[:300]


# ------- Sollecito veicoli --------
class TestSollecitoVeicoli:
    def test_run_sollecito_documento_veicolo_importable(self):
        try:
            import sys
            sys.path.insert(0, "/app/backend")
            from sollecito_veicoli import run_sollecito_documento_veicolo  # type: ignore
            assert callable(run_sollecito_documento_veicolo)
        except Exception as e:
            pytest.skip(f"impossibile importare run_sollecito_documento_veicolo: {e}")
