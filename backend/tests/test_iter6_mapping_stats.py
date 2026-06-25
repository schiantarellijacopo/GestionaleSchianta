"""Iter6 backend tests:
- Mapping Garanzie ANIA CRUD + applica-a-polizze
- Mapping Operatori ANIA CRUD (with user enrichment) + applica-a-polizze
- /contabilita/statistiche with kpi/liquidita
- Polizza PUT with new fields premio_tasse/imposte/ssn/operatore_ania_codice
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

ADMIN = {"email": os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")}


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# -------------------- Mapping Garanzie --------------------
class TestMappingGaranzie:
    def test_crud_and_validation(self, admin_session):
        # missing codice_ania -> 400
        r = admin_session.post(f"{BASE_URL}/api/librerie/mapping-garanzie", json={"nome_personalizzato": "x"})
        assert r.status_code == 400

        codice = f"TEST_G_{uuid.uuid4().hex[:6].upper()}"
        # CREATE
        r = admin_session.post(
            f"{BASE_URL}/api/librerie/mapping-garanzie",
            json={"codice_ania": codice, "descrizione_originale": "RCA Originale",
                  "nome_personalizzato": "Responsabilita Civile", "note": "test"},
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["codice_ania"] == codice
        assert "_id" not in created
        mid = created["id"]

        # GET list contains it
        r = admin_session.get(f"{BASE_URL}/api/librerie/mapping-garanzie")
        assert r.status_code == 200
        codes = [m["codice_ania"] for m in r.json()]
        assert codice in codes

        # UPDATE
        r = admin_session.put(
            f"{BASE_URL}/api/librerie/mapping-garanzie/{mid}",
            json={"nome_personalizzato": "RCA Renamed"},
        )
        assert r.status_code == 200
        assert r.json()["nome_personalizzato"] == "RCA Renamed"

        # DELETE
        r = admin_session.delete(f"{BASE_URL}/api/librerie/mapping-garanzie/{mid}")
        assert r.status_code == 200

    def test_applica_a_polizze(self, admin_session):
        codice = f"TEST_GA_{uuid.uuid4().hex[:6].upper()}"
        nome_new = "Garanzia Mappata Test"
        # create mapping
        r = admin_session.post(
            f"{BASE_URL}/api/librerie/mapping-garanzie",
            json={"codice_ania": codice, "nome_personalizzato": nome_new},
        )
        assert r.status_code == 201
        mid = r.json()["id"]

        # find first anagrafica + create a polizza with a garanzia matching codice
        cli = admin_session.get(f"{BASE_URL}/api/anagrafiche").json()
        assert isinstance(cli, list) and len(cli) > 0, f"anagrafiche empty: {cli}"
        cliente_id = cli[0]["id"]
        comp = admin_session.get(f"{BASE_URL}/api/compagnie").json()
        assert isinstance(comp, list) and len(comp) > 0
        compagnia_id = comp[0]["id"]

        pol_payload = {
            "numero_polizza": f"TEST-{uuid.uuid4().hex[:8]}",
            "contraente_id": cliente_id,
            "compagnia_id": compagnia_id,
            "ramo": "RCA",
            "effetto": "2026-01-01",
            "scadenza": "2027-01-01",
            "premio_lordo": 500,
            "garanzie": [{"garanzia": "Garanzia Vecchio Nome", "codice_ania": codice, "premio": 100}],
        }
        r = admin_session.post(f"{BASE_URL}/api/polizze", json=pol_payload)
        assert r.status_code in (200, 201), r.text
        pol = r.json()
        pol_id = pol["id"]

        # apply
        r = admin_session.post(f"{BASE_URL}/api/librerie/mapping-garanzie/applica-a-polizze")
        assert r.status_code == 200
        body = r.json()
        assert "polizze_aggiornate" in body
        assert body["polizze_aggiornate"] >= 1

        # verify rename
        r = admin_session.get(f"{BASE_URL}/api/polizze/{pol_id}")
        assert r.status_code == 200
        garanzie = r.json().get("garanzie") or []
        assert any(g.get("garanzia") == nome_new for g in garanzie), f"got: {garanzie}"

        # cleanup
        admin_session.delete(f"{BASE_URL}/api/polizze/{pol_id}")
        admin_session.delete(f"{BASE_URL}/api/librerie/mapping-garanzie/{mid}")


# -------------------- Mapping Operatori --------------------
class TestMappingOperatori:
    def test_crud_user_enrichment(self, admin_session):
        # find a non-cliente user to bind
        users = admin_session.get(f"{BASE_URL}/api/auth/users").json()
        target_user = next((u for u in users if u.get("role") in ("admin", "collaboratore", "dipendente")), None)
        assert target_user is not None
        user_id = target_user["id"]

        # missing codice_ania
        r = admin_session.post(f"{BASE_URL}/api/librerie/mapping-operatori", json={"user_id": user_id})
        assert r.status_code == 400

        codice = f"TEST_OP_{uuid.uuid4().hex[:6].upper()}"
        r = admin_session.post(
            f"{BASE_URL}/api/librerie/mapping-operatori",
            json={"codice_ania": codice, "nome_operatore": "Mario Rossi", "user_id": user_id},
        )
        assert r.status_code == 201, r.text
        mid = r.json()["id"]

        # GET list enrichment
        items = admin_session.get(f"{BASE_URL}/api/librerie/mapping-operatori").json()
        ours = next((i for i in items if i.get("codice_ania") == codice), None)
        assert ours is not None
        assert ours.get("user") is not None
        assert ours["user"]["id"] == user_id
        assert ours["user"]["email"] == target_user["email"]

        # cleanup
        admin_session.delete(f"{BASE_URL}/api/librerie/mapping-operatori/{mid}")

    def test_applica_a_polizze(self, admin_session):
        users = admin_session.get(f"{BASE_URL}/api/auth/users").json()
        target = next((u for u in users if u.get("role") in ("collaboratore", "dipendente")), None) or \
                 next((u for u in users if u.get("role") == "admin"), None)
        assert target is not None
        user_id = target["id"]

        codice = f"TEST_OP_{uuid.uuid4().hex[:6].upper()}"
        r = admin_session.post(
            f"{BASE_URL}/api/librerie/mapping-operatori",
            json={"codice_ania": codice, "nome_operatore": "Test Op", "user_id": user_id},
        )
        mid = r.json()["id"]

        # create polizza with operatore_ania_codice
        cli = admin_session.get(f"{BASE_URL}/api/anagrafiche").json()[0]
        comp = admin_session.get(f"{BASE_URL}/api/compagnie").json()[0]
        r = admin_session.post(f"{BASE_URL}/api/polizze", json={
            "numero_polizza": f"TST-{uuid.uuid4().hex[:8]}",
            "contraente_id": cli["id"], "compagnia_id": comp["id"], "ramo": "RCA",
            "effetto": "2026-01-01", "scadenza": "2027-01-01",
            "premio_lordo": 100, "operatore_ania_codice": codice,
        })
        assert r.status_code in (200, 201), r.text
        pol_id = r.json()["id"]

        # apply
        r = admin_session.post(f"{BASE_URL}/api/librerie/mapping-operatori/applica-a-polizze")
        assert r.status_code == 200
        assert r.json().get("polizze_aggiornate", 0) >= 1

        # verify collaboratore_id is set
        pol = admin_session.get(f"{BASE_URL}/api/polizze/{pol_id}").json()
        assert pol.get("collaboratore_id") == user_id

        # cleanup
        admin_session.delete(f"{BASE_URL}/api/polizze/{pol_id}")
        admin_session.delete(f"{BASE_URL}/api/librerie/mapping-operatori/{mid}")


# -------------------- Statistiche --------------------
class TestStatistiche:
    def test_shape(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/contabilita/statistiche")
        assert r.status_code == 200, r.text
        data = r.json()
        # KPI structure
        assert "kpi" in data
        for k in ["entrate", "provvigioni", "crediti", "rimesse", "sconti", "spese", "saldo_cassa_compagnie"]:
            assert k in data["kpi"], f"missing kpi.{k}"
        # liquidita
        assert "sum_conti" in data
        assert "crediti_attivi" in data
        assert "liquidita_disponibile" in data
        assert "liquidita_postera" in data
        assert "saldi_conti" in data and isinstance(data["saldi_conti"], list)
        assert "saldi_compagnie" in data and isinstance(data["saldi_compagnie"], list)
        # numeric check: liquidita_postera = sum_conti - saldo_cassa_compagnie
        assert abs(data["liquidita_postera"] - (data["sum_conti"] - data["kpi"]["saldo_cassa_compagnie"])) < 0.05
        # liquidita_disponibile = sum_conti - crediti_attivi - saldo_cassa_compagnie
        expected = data["sum_conti"] - data["crediti_attivi"] - data["kpi"]["saldo_cassa_compagnie"]
        assert abs(data["liquidita_disponibile"] - expected) < 0.05

    def test_period_filter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/contabilita/statistiche?dal=2026-01-01&al=2026-01-31")
        assert r.status_code == 200
        d = r.json()
        assert d["periodo"]["dal"] == "2026-01-01"
        assert d["periodo"]["al"] == "2026-01-31"
        # cumulative fields still present
        assert "sum_conti" in d and "liquidita_disponibile" in d


# -------------------- Polizza PUT new fields --------------------
class TestPolizzaPUTFields:
    def test_persist_new_economic_fields(self, admin_session):
        cli = admin_session.get(f"{BASE_URL}/api/anagrafiche").json()[0]
        comp = admin_session.get(f"{BASE_URL}/api/compagnie").json()[0]
        r = admin_session.post(f"{BASE_URL}/api/polizze", json={
            "numero_polizza": f"TST-{uuid.uuid4().hex[:8]}",
            "contraente_id": cli["id"], "compagnia_id": comp["id"], "ramo": "RCA",
            "effetto": "2026-01-01", "scadenza": "2027-01-01",
            "premio_lordo": 100,
        })
        assert r.status_code in (200, 201), r.text
        pol_id = r.json()["id"]

        # PUT with new fields
        payload = {
            "premio_netto": 350.55,
            "premio_tasse": 50.10,
            "premio_imposte": 20.30,
            "premio_ssn": 10.40,
            "premio_lordo": 431.35,
            "operatore_ania_codice": "OP123",
        }
        r = admin_session.put(f"{BASE_URL}/api/polizze/{pol_id}", json=payload)
        assert r.status_code == 200, r.text

        # GET verify persistence
        pol = admin_session.get(f"{BASE_URL}/api/polizze/{pol_id}").json()
        assert abs(pol.get("premio_netto", 0) - 350.55) < 0.01
        assert abs(pol.get("premio_tasse", 0) - 50.10) < 0.01
        assert abs(pol.get("premio_imposte", 0) - 20.30) < 0.01
        assert abs(pol.get("premio_ssn", 0) - 10.40) < 0.01
        assert abs(pol.get("premio_lordo", 0) - 431.35) < 0.01
        assert pol.get("operatore_ania_codice") == "OP123"

        # cleanup
        admin_session.delete(f"{BASE_URL}/api/polizze/{pol_id}")
