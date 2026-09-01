"""Iter59 — Backend E2E tests per le 3 nuove feature P0:
   1) Regolazione Premio (list/stats/lettera-pdf/invia-lettera/calcola/genera-titolo/stato)
   2) Cumulativa Assicurati (CRUD + stats + flag polizza)
   3) Dashboard Automazioni-oggi

Preservare i dati: al termine ogni titolo di regolazione creato viene eliminato,
il flag regolazione_premio riportato a false, gli assicurati eliminati e il
flag is_cumulativa_assicurati riportato a false.
"""
import os
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def polizza_id(client):
    r = client.get(f"{BASE_URL}/api/polizze?limit=1", timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("data") or []
    assert items, "Nessuna polizza esistente per il test"
    return items[0]["id"]


# ============================================================================
# 1) REGOLAZIONE PREMIO
# ============================================================================
class TestRegolazionePremio:
    _titolo_id = None

    def test_01_flag_regolazione(self, client, polizza_id):
        payload = {
            "regolazione_premio": True,
            "regolazione_base": "fatturato",
            "regolazione_tasso": 1.5,
            "regolazione_minima": 500,
            "regolazione_giorni_invio": 30,
        }
        r = client.put(f"{BASE_URL}/api/polizze/{polizza_id}", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        # Verifica persistenza
        rp = client.get(f"{BASE_URL}/api/polizze/{polizza_id}", timeout=30)
        assert rp.status_code == 200
        d = rp.json()
        assert d.get("regolazione_premio") is True
        assert d.get("regolazione_tasso") == 1.5
        assert d.get("regolazione_giorni_invio") == 30

    def test_02_list_regolazioni(self, client, polizza_id):
        r = client.get(f"{BASE_URL}/api/regolazione-premio", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        row = next((x for x in rows if x["polizza_id"] == polizza_id), None)
        assert row is not None, f"Polizza flaggata non presente nella lista regolazione-premio ({len(rows)} righe)"
        # data_invio_prevista = scadenza + 30gg (se scadenza presente)
        if row.get("scadenza"):
            expected = (date.fromisoformat(row["scadenza"][:10]) + timedelta(days=30)).isoformat()
            assert row.get("data_invio_prevista") == expected
        assert row.get("stato") == "da_richiedere"
        assert isinstance(row.get("da_inviare"), bool)

    def test_03_stats(self, client):
        r = client.get(f"{BASE_URL}/api/regolazione-premio/stats", timeout=30)
        assert r.status_code == 200
        s = r.json()
        assert "totale" in s and "da_inviare" in s and "per_stato" in s
        assert s["totale"] >= 1

    def test_04_lettera_pdf(self, client, polizza_id):
        r = client.post(f"{BASE_URL}/api/regolazione-premio/{polizza_id}/lettera-pdf",
                        json={"invia_email": False, "periodo": "2024"}, timeout=45)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"content-type inatteso: {ct}"
        assert r.content[:4] == b"%PDF", "risposta non è un PDF"

    def test_05_invia_lettera_manuale(self, client, polizza_id):
        r = client.post(f"{BASE_URL}/api/regolazione-premio/{polizza_id}/invia-lettera",
                        json={"invia_email": False}, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("stato") == "lettera_inviata"
        # Verifica stato persistito
        rp = client.get(f"{BASE_URL}/api/polizze/{polizza_id}", timeout=30)
        assert rp.json().get("regolazione_stato") == "lettera_inviata"

    def test_06_calcola(self, client, polizza_id):
        r = client.post(f"{BASE_URL}/api/polizze/{polizza_id}/regolazione-premio/calcola",
                        json={"base_imponibile": 100000, "periodo": "2024", "salva": True}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # 100000 * 1.5% = 1500 (> minima 500)
        assert d.get("dovuto") == 1500, d
        assert d.get("premio_calcolato") == 1500
        rp = client.get(f"{BASE_URL}/api/polizze/{polizza_id}", timeout=30).json()
        assert rp.get("regolazione_stato") == "calcolata"
        assert rp.get("regolazione_dovuto") == 1500

    def test_07_genera_titolo(self, client, polizza_id):
        r = client.post(f"{BASE_URL}/api/regolazione-premio/{polizza_id}/genera-titolo",
                        json={"imposte": 100}, timeout=30)
        assert r.status_code == 201, r.text
        t = r.json()
        assert t.get("tipo") == "regolazione"
        assert t.get("importo_lordo") == 1500
        assert t.get("imposte") == 100
        assert t.get("importo_netto") == 1400
        TestRegolazionePremio._titolo_id = t["id"]
        rp = client.get(f"{BASE_URL}/api/polizze/{polizza_id}", timeout=30).json()
        assert rp.get("regolazione_stato") == "titolo_generato"
        assert rp.get("regolazione_titolo_id") == t["id"]

    def test_08_cambio_stato_manuale(self, client, polizza_id):
        r = client.post(f"{BASE_URL}/api/regolazione-premio/{polizza_id}/stato",
                        json={"stato": "chiusa", "note": "TEST_iter59"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("stato") == "chiusa"

    def test_09_stato_invalido(self, client, polizza_id):
        r = client.post(f"{BASE_URL}/api/regolazione-premio/{polizza_id}/stato",
                        json={"stato": "invalido_xyz"}, timeout=30)
        assert r.status_code == 400

    def test_99_cleanup(self, client, polizza_id):
        # Elimina titolo di regolazione creato
        if TestRegolazionePremio._titolo_id:
            r = client.delete(f"{BASE_URL}/api/titoli/{TestRegolazionePremio._titolo_id}?force=true", timeout=30)
            # accettiamo 200/204/404 (idempotente)
            assert r.status_code in (200, 204, 404), f"delete titolo: {r.status_code} {r.text}"
        # Ripristina flag
        r = client.put(f"{BASE_URL}/api/polizze/{polizza_id}", json={
            "regolazione_premio": False,
            "regolazione_stato": None,
            "regolazione_dovuto": 0,
            "regolazione_titolo_id": None,
            "regolazione_ultimo_calcolo": None,
            "regolazione_lettera_inviata_data": None,
        }, timeout=30)
        assert r.status_code == 200


# ============================================================================
# 2) CUMULATIVA ASSICURATI
# ============================================================================
class TestCumulativaAssicurati:
    _created_ids: list = []

    def test_01_create(self, client, polizza_id):
        payload = {
            "cognome": "TESTITER59",
            "nome": "Mario",
            "ditta": "ACME SRL",
            "data_entrata": "2024-01-01",
            "data_uscita": None,
        }
        r = client.post(f"{BASE_URL}/api/polizze/{polizza_id}/assicurati",
                        json=payload, timeout=30)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["cognome"] == "TESTITER59"
        assert d["nome"] == "MARIO"
        assert d["stato"] == "attivo"
        assert d["numero"] >= 1
        TestCumulativaAssicurati._created_ids.append(d["id"])
        # flag polizza aggiornato
        p = client.get(f"{BASE_URL}/api/polizze/{polizza_id}", timeout=30).json()
        assert p.get("is_cumulativa_assicurati") is True

    def test_02_create_uscito(self, client, polizza_id):
        past = (date.today() - timedelta(days=10)).isoformat()
        r = client.post(f"{BASE_URL}/api/polizze/{polizza_id}/assicurati",
                        json={"cognome": "TESTITER59B", "nome": "Luca",
                              "data_entrata": "2023-01-01", "data_uscita": past}, timeout=30)
        assert r.status_code == 201
        d = r.json()
        assert d["stato"] == "uscito"
        TestCumulativaAssicurati._created_ids.append(d["id"])

    def test_03_list(self, client, polizza_id):
        r = client.get(f"{BASE_URL}/api/polizze/{polizza_id}/assicurati", timeout=30)
        assert r.status_code == 200
        lst = r.json()
        assert isinstance(lst, list)
        ids = {a["id"] for a in lst}
        for aid in TestCumulativaAssicurati._created_ids:
            assert aid in ids

    def test_04_stats(self, client, polizza_id):
        r = client.get(f"{BASE_URL}/api/polizze/{polizza_id}/assicurati/stats", timeout=30)
        assert r.status_code == 200
        s = r.json()
        assert s["totale"] >= 2
        assert s["attivi"] >= 1
        assert s["usciti"] >= 1

    def test_05_update(self, client):
        aid = TestCumulativaAssicurati._created_ids[0]
        r = client.put(f"{BASE_URL}/api/assicurati/{aid}",
                       json={"cognome": "TESTITER59", "nome": "Marione", "ditta": "NEWDITTA"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nome"] == "MARIONE"
        assert d["ditta"] == "NEWDITTA"

    def test_06_delete_404(self, client):
        r = client.delete(f"{BASE_URL}/api/assicurati/non-esiste-xxx", timeout=30)
        assert r.status_code == 404

    def test_99_cleanup(self, client, polizza_id):
        for aid in TestCumulativaAssicurati._created_ids:
            r = client.delete(f"{BASE_URL}/api/assicurati/{aid}", timeout=30)
            assert r.status_code in (200, 204, 404)
        # rimetti flag polizza
        r = client.put(f"{BASE_URL}/api/polizze/{polizza_id}",
                       json={"is_cumulativa_assicurati": False}, timeout=30)
        assert r.status_code == 200


# ============================================================================
# 3) DASHBOARD AUTOMAZIONI-OGGI
# ============================================================================
class TestDashboardAutomazioni:
    def test_01_endpoint_ok(self, client):
        r = client.get(f"{BASE_URL}/api/dashboard/automazioni-oggi", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "data" in d
        assert "totale_invii" in d
        assert "totale_inviati" in d
        assert "totale_errori" in d
        assert "categorie" in d
        assert isinstance(d["categorie"], list)
        # tipi
        assert isinstance(d["totale_invii"], int)
        assert isinstance(d["totale_inviati"], int)
        assert isinstance(d["totale_errori"], int)
