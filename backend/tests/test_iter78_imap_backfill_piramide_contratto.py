"""Test iter 78 - IMAP backfill allegati, prepopola piramide azienda, contratto consulenza PDF/DOCX."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PWD = "Admin123!"
AID_AZIENDA = "abe0cbf1-52a7-4d4b-b703-9a49ca89d924"
POLIZZA_ID = "bacebe55-a647-4223-baf1-f9dd04d27cd5"
POLIZZA_NUM = "184643415"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# --- IMAP backfill ---
class TestImapBackfill:
    def test_retry_allegati_returns_ok(self, headers):
        r = requests.post(f"{BASE_URL}/api/email/poller/retry-allegati", headers=headers, timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("esaminate", 0) > 0, f"esaminate dovrebbe essere > 0: {data}"
        # NOTA: il backfill è già stato eseguito in precedenza (con_match=49, allegati_polizza=37),
        # quindi ora è idempotente e restituisce 0 nuovi match. Verifichiamo comunque la presenza
        # dell'allegato risultante sulla polizza specifica nel test successivo.

    def test_polizza_184643415_ha_allegato_pdf(self, headers):
        r = requests.get(
            f"{BASE_URL}/api/allegati",
            headers=headers,
            params={"entita_tipo": "polizza", "entita_id": POLIZZA_ID},
        )
        assert r.status_code == 200, r.text
        allegati = r.json()
        assert isinstance(allegati, list) and len(allegati) > 0, "Nessun allegato sulla polizza"
        # Cerchiamo il PDF specifico dal file 'Contratto Active Veicoli AUTOCARRI  184643415.pdf'
        target = [a for a in allegati if POLIZZA_NUM in (a.get("nome_file") or a.get("filename") or "")]
        assert target, f"Manca allegato con {POLIZZA_NUM} nel nome: {[a.get('nome_file') or a.get('filename') for a in allegati]}"
        a = target[0]
        # Verifica fonte email_imap e categoria polizza_firmata
        fonte = a.get("fonte") or a.get("origine")
        categoria = a.get("categoria")
        assert fonte == "email_imap", f"fonte attesa email_imap, trovato {fonte}"
        assert categoria == "polizza_firmata", f"categoria attesa polizza_firmata, trovato {categoria}"

    def test_retry_idempotente(self, headers):
        # Snapshot pre
        r1 = requests.get(
            f"{BASE_URL}/api/allegati", headers=headers,
            params={"entita_tipo": "polizza", "entita_id": POLIZZA_ID},
        )
        assert r1.status_code == 200
        count_before = len(r1.json())
        # Retry
        r2 = requests.post(f"{BASE_URL}/api/email/poller/retry-allegati", headers=headers, timeout=180)
        assert r2.status_code == 200
        # Snapshot post
        r3 = requests.get(
            f"{BASE_URL}/api/allegati", headers=headers,
            params={"entita_tipo": "polizza", "entita_id": POLIZZA_ID},
        )
        assert r3.status_code == 200
        count_after = len(r3.json())
        assert count_after == count_before, f"Duplicazione allegati: prima={count_before} dopo={count_after}"


# --- Prepopola piramide-v2 azienda ---
class TestPrepopolaPiramideAzienda:
    def test_prepopola_azienda_da_salute_fiscale(self, headers):
        r = requests.post(
            f"{BASE_URL}/api/anagrafiche/{AID_AZIENDA}/analisi/piramide-v2/prepopola",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Verifica fonte
        assert data.get("fonte") == "salute_fiscale_azienda", f"fonte inattesa: {data.get('fonte')}"
        # Valori attesi (con tolleranza per arrotondamenti)
        def approx(actual, expected, tol=1.0):
            return abs(float(actual) - float(expected)) <= tol
        assert approx(data.get("reddito_attuale", 0), 6889188, tol=2), f"reddito_attuale={data.get('reddito_attuale')}"
        assert approx(data.get("reddito_invalidita_66_99", 0), -8052, tol=2), f"inv_66={data.get('reddito_invalidita_66_99')}"
        assert approx(data.get("reddito_inabilita_100", 0), 286999, tol=2), f"inab_100={data.get('reddito_inabilita_100')}"
        assert int(data.get("reddito_superstiti", 0)) == 49, f"superstiti={data.get('reddito_superstiti')}"
        assert int(data.get("reddito_responsabilita", 0)) == 2, f"resp={data.get('reddito_responsabilita')}"
        assert approx(data.get("reddito_perdita_beni", 0), 451553, tol=2), f"perdita_beni={data.get('reddito_perdita_beni')}"


# --- Contratto consulenza PDF/DOCX ---
class TestContrattoConsulenza:
    def test_pdf_valido(self, headers):
        r = requests.get(f"{BASE_URL}/api/anagrafiche/{AID_AZIENDA}/contratto-consulenza/pdf", headers=headers)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"content-type: {ct}"
        assert len(r.content) > 2048, f"pdf troppo piccolo: {len(r.content)} bytes"
        assert r.content[:4] == b"%PDF", "signature PDF mancante"

    def test_docx_valido(self, headers):
        r = requests.get(f"{BASE_URL}/api/anagrafiche/{AID_AZIENDA}/contratto-consulenza/docx", headers=headers)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "wordprocessingml" in ct or "openxml" in ct, f"content-type: {ct}"
        # DOCX = zip -> inizia con PK
        assert r.content[:2] == b"PK", "signature ZIP/DOCX mancante"
        assert len(r.content) > 2048
