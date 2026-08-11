"""Test iter55: Piramide v2 auto-popola + prepopola, biblioteca schede-calcolo job async,
cerca-condizioni polizza dal Web."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

MARCO_AID = "93b73085-100f-4c78-883a-e6cefea49c72"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@assicura.it", "password": "Admin123!"},
                      timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- LOGIN ----------
class TestLogin:
    def test_admin_login(self, token):
        assert isinstance(token, str) and len(token) > 20


# ---------- PIRAMIDE V2 ----------
class TestPiramideV2:
    def test_get_piramide_v2_marco_rossi(self, headers):
        r = requests.get(f"{API}/anagrafiche/{MARCO_AID}/analisi/piramide-v2",
                         headers=headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("cliente_nome") == "Rossi Marco", f"nome={data.get('cliente_nome')}"
        assert "dati_reddito" in data
        assert "voci_calcolate" in data
        voci = data["voci_calcolate"]
        # voci_calcolate è un dict {categoria: {...}}
        assert isinstance(voci, dict), f"tipo={type(voci)}"
        assert len(voci) >= 12, f"solo {len(voci)} voci"
        # estratto_conto true perché ha estratti caricati
        assert data["dati_reddito"].get("estratto_conto") is True, \
            f"estratto_conto={data['dati_reddito'].get('estratto_conto')}"

    def test_prepopola_piramide_v2(self, headers):
        r = requests.post(f"{API}/anagrafiche/{MARCO_AID}/analisi/piramide-v2/prepopola",
                          headers=headers, timeout=30)
        # Accetta 200 (ha dati) o 400 (nessun estratto) come da spec
        assert r.status_code in (200, 400), f"status={r.status_code} body={r.text[:300]}"
        if r.status_code == 200:
            data = r.json()
            # attesa dati_reddito o campi diretti
            reddito = data.get("dati_reddito") or data
            assert any(k in reddito for k in
                       ("reddito_attuale", "reddito_invalidita_66_99",
                        "reddito_inabilita_100", "reddito_superstiti")), \
                f"nessun campo reddito atteso: {list(reddito.keys())[:10]}"
        else:
            assert "estratto" in r.text.lower() or "reddito" in r.text.lower()

    def test_put_piramide_roundtrip(self, headers):
        # GET
        r = requests.get(f"{API}/anagrafiche/{MARCO_AID}/analisi/piramide-v2",
                         headers=headers, timeout=30)
        assert r.status_code == 200
        original = r.json()

        # PUT payload (schema reale: testamento=bool, eredi_legittimi=list[str], voci_custom=dict)
        payload = {
            "dati_reddito": {"reddito_attuale": 30000, "estratto_conto": True},
            "testamento": True,
            "eredi_legittimi": ["TEST Erede iter55"],
            "override_voci": {"pensione_vecchiaia": 12345},
            "stato_voci": {"pensione_vecchiaia": "verificato"},
            "voci_custom": {"TEST_voce": {"valore": 999}},
        }
        r2 = requests.put(f"{API}/anagrafiche/{MARCO_AID}/analisi/piramide-v2",
                          headers=headers, json=payload, timeout=30)
        assert r2.status_code in (200, 204), f"PUT status={r2.status_code} body={r2.text[:300]}"

        # GET verify
        r3 = requests.get(f"{API}/anagrafiche/{MARCO_AID}/analisi/piramide-v2",
                          headers=headers, timeout=30)
        assert r3.status_code == 200
        after = r3.json()
        assert after.get("testamento") is True, f"testamento={after.get('testamento')}"
        assert "TEST Erede iter55" in (after.get("eredi_legittimi") or []), \
            f"eredi={after.get('eredi_legittimi')}"
        assert after.get("override_voci", {}).get("pensione_vecchiaia") == 12345
        assert after.get("stato_voci", {}).get("pensione_vecchiaia") == "verificato"
        assert "TEST_voce" in (after.get("voci_custom") or {}), \
            f"voci_custom={after.get('voci_custom')}"
        assert after.get("dati_reddito", {}).get("reddito_attuale") == 30000


# ---------- BIBLIOTECA - SCHEDE CALCOLO JOB ASYNC ----------
class TestBibliotecaSchedeCalcolo:
    def test_genera_scheda_returns_job_fast(self, headers):
        t0 = time.time()
        r = requests.post(f"{API}/biblioteca-previdenza/schede-calcolo/genera",
                          headers=headers, json={"cartella": "DIPENDENTI PRIVATI"},
                          timeout=10)
        elapsed = time.time() - t0
        assert r.status_code in (200, 202), f"status={r.status_code} body={r.text[:300]}"
        assert elapsed < 5, f"Troppo lento: {elapsed:.2f}s (deve tornare in <5s)"
        data = r.json()
        assert "job_id" in data, f"no job_id: {data}"
        assert "categoria" in data or "cartella" in data
        self.__class__.job_id = data["job_id"]

    def test_job_status_polling(self, headers):
        jid = getattr(self.__class__, "job_id", None)
        if not jid:
            pytest.skip("no job_id from previous test")
        # poll fino a 3 min
        deadline = time.time() + 180
        last_status = None
        while time.time() < deadline:
            r = requests.get(f"{API}/biblioteca-previdenza/jobs/{jid}",
                             headers=headers, timeout=15)
            assert r.status_code == 200, r.text[:300]
            j = r.json()
            last_status = j.get("stato") or j.get("status")
            if last_status in ("done", "completato", "completed"):
                # ok
                risultato = j.get("risultato") or j.get("result") or {}
                assert risultato, f"done ma no risultato: {j}"
                return
            if last_status in ("error", "errore", "failed"):
                pytest.fail(f"job in errore: {j}")
            time.sleep(5)
        pytest.fail(f"job non completato in 3min, ultimo stato: {last_status}")


# ---------- BIBLIOTECA - CERCA CONDIZIONI DAL WEB ----------
class TestCercaCondizioni:
    def test_cerca_condizioni_manuale(self, headers):
        t0 = time.time()
        r = requests.post(f"{API}/biblioteca-previdenza/cerca-condizioni",
                          headers=headers,
                          json={"compagnia": "Generali", "ramo": "Auto"},
                          timeout=60)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        assert elapsed < 60, f"troppo lento: {elapsed:.1f}s"
        data = r.json()
        # Le chiavi devono esistere (anche se vuote è ok, l'AI può non trovare nulla)
        for k in ("urls_suggeriti", "urls_tentati", "importati", "messaggio"):
            assert k in data, f"chiave mancante: {k}, keys={list(data.keys())}"

    def test_cerca_condizioni_bulk_returns_job(self, headers):
        t0 = time.time()
        r = requests.post(f"{API}/biblioteca-previdenza/cerca-condizioni-bulk",
                          headers=headers, json={"solo_mancanti": True},
                          timeout=10)
        elapsed = time.time() - t0
        assert r.status_code in (200, 202), f"status={r.status_code} body={r.text[:300]}"
        assert elapsed < 5, f"bulk troppo lento: {elapsed:.2f}s"
        data = r.json()
        assert "job_id" in data, f"no job_id: {data}"
        assert "totale_compagnie" in data or "totale" in data


# ---------- IMAP MODULE IMPORT ----------
class TestImapPollerImport:
    def test_import(self):
        import imap_poller
        assert hasattr(imap_poller, "_candidati_numeri_polizza")
        assert hasattr(imap_poller, "_auto_allega_polizza")
