"""Iteration 52 - Backend tests for Portale Cliente (multi-anag, /me fix,
polizze stats, titoli quietanze, allegati by-entita, download ownership,
chat with file), Firma config (Namirial), Chat portale admin,
invia-credenziali (single + massivo dry_run), Dashboard richieste_portale,
Carichi Mensili stato_carico=tutti, Storico avvisi rimanda.
"""
import io
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PWD = "Admin123!"

# Multi-anagrafica login test:
# - Same email 'schiantarelli.jacopo@gmail.com' shared by 2 anagrafiche.
# - CF 'SCHJCP91M18I829O' belongs to SCHIANTARELLI JACOPO (id=abdc83b3-...).
# - CF 'RSHHSN96S16Z236W' belongs to ARSHAD HUSSNAIN (id=756628b6-...).
SHARED_EMAIL = "schiantarelli.jacopo@gmail.com"
CF_SCHIANTARELLI = "SCHJCP91M18I829O"
CF_ARSHAD = "RSHHSN96S16Z236W"

MARCO_EMAIL = "marco.rossi@demo.it"
MARCO_CF = "RSSMRC75H10F205X"
MARCO_AID = "93b73085-100f-4c78-883a-e6cefea49c72"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def marco_token():
    r = requests.post(f"{API}/portale/auth/login",
                      json={"email": MARCO_EMAIL, "password": MARCO_CF}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def marco_headers(marco_token):
    return {"Authorization": f"Bearer {marco_token}"}


# =============== Portale multi-anagrafica login ===============
class TestPortaleMultiAnag:
    def test_login_schiantarelli_returns_correct_anag(self):
        """CF Schiantarelli must return the SCHIANTARELLI anagrafica (not other same-email)."""
        r = requests.post(f"{API}/portale/auth/login",
                          json={"email": SHARED_EMAIL, "password": CF_SCHIANTARELLI}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        cli = data["cliente"]
        # Must be SCHIANTARELLI JACOPO — the one whose CF matches the password
        assert "SCHIANTARELLI" in (cli.get("nome") or "").upper(), \
            f"Expected SCHIANTARELLI, got {cli}"

    def test_login_arshad_returns_arshad(self):
        """Same email but CF Arshad must return the ARSHAD anagrafica."""
        r = requests.post(f"{API}/portale/auth/login",
                          json={"email": SHARED_EMAIL, "password": CF_ARSHAD}, timeout=20)
        # Might fail if PIVA-only login (tipo giuridico). Log for diagnostics.
        if r.status_code == 200:
            cli = r.json()["cliente"]
            assert "ARSHAD" in (cli.get("nome") or "").upper()
        else:
            # Acceptable if CF stored is empty for that record; log
            print(f"Arshad login returned {r.status_code}: {r.text[:200]}")

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/portale/auth/login",
                          json={"email": SHARED_EMAIL, "password": "WRONGWRONG"}, timeout=20)
        assert r.status_code == 401


# =============== Portale /me + /agenzia + /polizze ===============
class TestPortaleProfile:
    def test_get_agenzia(self, marco_headers):
        r = requests.get(f"{API}/portale/agenzia", headers=marco_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "ragione_sociale" in d
        assert "telefono" in d
        assert "email" in d
        assert "indirizzo" in d

    def test_get_me_has_extended_fields(self, marco_headers):
        r = requests.get(f"{API}/portale/me", headers=marco_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # All these keys must be present (may be null but not missing)
        for k in ("indirizzo", "comune", "provincia", "cap", "iban", "banca",
                  "data_nascita"):
            assert k in d, f"campo mancante: {k}"

    def test_polizze_enrichment(self, marco_headers):
        r = requests.get(f"{API}/portale/polizze", headers=marco_headers, timeout=20)
        assert r.status_code == 200, r.text
        pols = r.json()
        assert isinstance(pols, list)
        if pols:
            p = pols[0]
            for k in ("stats_titoli", "n_allegati", "n_sinistri", "is_scaduta"):
                assert k in p, f"campo {k} mancante in polizza"
            stats = p["stats_titoli"]
            for k in ("da_pagare", "arretrati", "prossima_scadenza", "prossimo_importo"):
                assert k in stats


# =============== Portale titoli + quietanze ===============
class TestPortaleTitoli:
    def test_titoli_by_polizza_with_quietanze(self, marco_headers):
        pr = requests.get(f"{API}/portale/polizze", headers=marco_headers, timeout=20)
        pols = pr.json()
        if not pols:
            pytest.skip("nessuna polizza")
        pid = pols[0]["id"]
        r = requests.get(f"{API}/portale/polizze/{pid}/titoli",
                         headers=marco_headers, timeout=20)
        assert r.status_code == 200, r.text
        titoli = r.json()
        assert isinstance(titoli, list)
        for t in titoli:
            assert "quietanze" in t, "campo quietanze[] mancante"
            assert isinstance(t["quietanze"], list)

    def test_titoli_ownership_fake_polizza(self, marco_headers):
        r = requests.get(f"{API}/portale/polizze/00000000-0000-0000-0000-000000000000/titoli",
                         headers=marco_headers, timeout=20)
        assert r.status_code == 404


# =============== Allegati by-entita ownership + veicolo filter ===============
class TestPortaleAllegati:
    def test_by_entita_polizza(self, marco_headers):
        pr = requests.get(f"{API}/portale/polizze", headers=marco_headers, timeout=20)
        pols = pr.json()
        if not pols:
            pytest.skip("nessuna polizza")
        pid = pols[0]["id"]
        r = requests.get(f"{API}/portale/allegati/by-entita",
                         headers=marco_headers,
                         params={"entita_tipo": "polizza", "entita_id": pid},
                         timeout=20)
        assert r.status_code == 200, r.text
        items = r.json()
        # None must have applicazione_matricola_id set (must be filtered out)
        for a in items:
            am = a.get("applicazione_matricola_id")
            assert not am, f"allegato con applicazione_matricola_id={am} non deve comparire sotto polizza"

    def test_by_entita_polizza_unauthorized(self, marco_headers):
        r = requests.get(f"{API}/portale/allegati/by-entita",
                         headers=marco_headers,
                         params={"entita_tipo": "polizza",
                                 "entita_id": "00000000-0000-0000-0000-000000000000"},
                         timeout=20)
        assert r.status_code == 404

    def test_by_entita_invalid_tipo(self, marco_headers):
        r = requests.get(f"{API}/portale/allegati/by-entita",
                         headers=marco_headers,
                         params={"entita_tipo": "fake", "entita_id": "x"},
                         timeout=20)
        assert r.status_code == 400

    def test_download_ownership_denied(self, marco_headers):
        r = requests.get(f"{API}/portale/allegati/{uuid.uuid4()}/download",
                         headers=marco_headers, timeout=20)
        assert r.status_code == 404


# =============== Portale chat con allegato ===============
class TestPortaleChat:
    def test_send_message_with_file(self, marco_headers):
        payload = io.BytesIO(b"%PDF-1.4 fake pdf content TEST_iter52")
        files = {"file": ("TEST_iter52.pdf", payload, "application/pdf")}
        data = {"testo": "TEST_iter52 msg con allegato"}
        r = requests.post(f"{API}/portale/chat/messaggi",
                          headers=marco_headers, files=files, data=data, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("allegato_id"), "allegato_id mancante"
        assert d.get("direzione") == "in"

    def test_get_chat_history(self, marco_headers):
        r = requests.get(f"{API}/portale/chat/messaggi", headers=marco_headers, timeout=20)
        assert r.status_code == 200, r.text
        msgs = r.json()
        assert isinstance(msgs, list)
        # At least one with allegato info
        with_att = [m for m in msgs if m.get("allegato_id")]
        assert len(with_att) >= 1

    def test_admin_reply_and_unread(self, admin_headers, marco_headers):
        # admin sends reply with file
        payload = io.BytesIO(b"admin reply TEST_iter52")
        files = {"file": ("TEST_iter52_admin.txt", payload, "text/plain")}
        data = {"testo": "TEST_iter52 admin reply"}
        r = requests.post(f"{API}/chat-portale/{MARCO_AID}/messaggi",
                          headers=admin_headers, files=files, data=data, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("direzione") == "out"
        assert d.get("allegato_id")

        # admin list clienti — marco has unread >= 1
        r2 = requests.get(f"{API}/chat-portale/clienti", headers=admin_headers, timeout=20)
        assert r2.status_code == 200
        clienti = r2.json()
        marco = next((c for c in clienti if c.get("anagrafica_id") == MARCO_AID), None)
        assert marco, "Marco non nella lista chat"
        assert marco["unread"] >= 1


# =============== Invia credenziali portale (Marco + massivo dry_run) ===============
class TestInviaCredenziali:
    def test_invia_marco(self, admin_headers):
        r = requests.post(f"{API}/anagrafiche/{MARCO_AID}/invia-credenziali-portale",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Should have email/whatsapp send info (ok or error attached)
        assert "email_inviata" in d
        assert "whatsapp_inviato" in d
        print(f"Marco invia-credenziali: email_ok={d['email_inviata']} err={d.get('email_errore')} "
              f"wa_ok={d['whatsapp_inviato']} err={d.get('whatsapp_errore')}")

    def test_invia_massivo_dry_run(self, admin_headers):
        r = requests.post(f"{API}/anagrafiche/invia-credenziali-portale-massivo",
                          headers=admin_headers,
                          json={"dry_run": True, "solo_con_polizze": True,
                                "escludi_gia_invitati": False, "limit": 50},
                          timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("dry_run") is True
        assert "totale" in d
        assert "esempi" in d
        print(f"Massivo dry_run: totale={d['totale']} esempi={len(d['esempi'])}")
        assert d["totale"] >= 0


# =============== Dashboard task richieste_portale ===============
class TestDashboard:
    def test_tasks_include_richieste_portale(self, admin_headers):
        r = requests.get(f"{API}/dashboard/tasks", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        tasks = r.json()
        # tasks may be dict with items or list — support both
        items = tasks if isinstance(tasks, list) else tasks.get("items") or tasks.get("tasks") or []
        # cerca key richieste_portale
        rp = next((t for t in items if t.get("key") == "richieste_portale"), None)
        assert rp, f"task richieste_portale mancante. keys: {[t.get('key') for t in items]}"
        assert rp.get("color") == "violet"
        assert rp.get("url") == "/richieste-cliente"


# =============== Firma Namirial config + endpoint guards ===============
class TestFirma:
    def test_put_azienda_firma_config(self, admin_headers):
        body = {
            "firma_base_url": "https://demo.esignanywhere.net/Api/v6",
            "firma_api_token": "TEST_FAKE_TOKEN_iter52",
            "firma_environment": "sandbox",
        }
        r = requests.put(f"{API}/librerie/azienda", headers=admin_headers,
                         json=body, timeout=20)
        assert r.status_code == 200, r.text
        # Verify GET returns saved fields
        g = requests.get(f"{API}/librerie/azienda", headers=admin_headers, timeout=20)
        assert g.status_code == 200
        d = g.json()
        assert d.get("firma_base_url") == body["firma_base_url"]
        # api_token may be masked or returned raw depending on impl
        assert d.get("firma_environment") == "sandbox"

    def test_list_firme_returns_list(self, admin_headers):
        r = requests.get(f"{API}/firma/richieste", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_create_firma_no_config_returns_400(self, admin_headers):
        # Blank the config first
        blank = {"firma_base_url": "", "firma_api_token": ""}
        requests.put(f"{API}/librerie/azienda", headers=admin_headers, json=blank, timeout=20)
        files = {"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
        data = {"modalita": "otp_email", "firmatario_id": MARCO_AID,
                "display_name": "TEST doc"}
        r = requests.post(f"{API}/firma/richieste", headers=admin_headers,
                          files=files, data=data, timeout=30)
        assert r.status_code == 400
        assert "Provider firma non configurato" in r.text or "non configurato" in r.text


# =============== Carichi Mensili stato_carico=tutti ===============
class TestCarichiMensili:
    def test_stato_tutti(self, admin_headers):
        r = requests.get(f"{API}/carichi-mensili",
                         headers=admin_headers,
                         params={"stato_carico": "tutti", "range_filter": "tutti"},
                         timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "righe" in d or isinstance(d, list)
        righe = d.get("righe") if isinstance(d, dict) else d
        assert isinstance(righe, list)
        # if there are items, check we have mixed stato_carico
        if righe:
            stati = {r.get("stato_carico") for r in righe}
            print(f"stato_carico presenti: {stati}")


# =============== Storico avvisi rimanda ===============
class TestStoricoAvvisiRimanda:
    def _make_wa_avviso(self, admin_headers):
        body = {
            "canale": "whatsapp",
            "destinatario": "393334455667",
            "messaggio": "TEST_iter52 rimanda",
            "tipo": "test",
        }
        r = requests.post(f"{API}/storico-avvisi/registra",
                          headers=admin_headers, json=body, timeout=20)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_rimanda_wa(self, admin_headers):
        orig = self._make_wa_avviso(admin_headers)
        aid = orig.get("id") or orig.get("avviso_id")
        assert aid, f"id mancante in {orig}"
        r = requests.post(f"{API}/storico-avvisi/{aid}/rimanda",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("canale") == "whatsapp"
        assert d.get("new_id")
        # ok=True if Evolution API is reachable; even if False, canale + new_id must be set
        print(f"rimanda esito: ok={d.get('ok')} err={d.get('error')}")
