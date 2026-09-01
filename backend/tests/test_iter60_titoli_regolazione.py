"""
Iter60 — Test P0 features su TITOLI e REGOLAZIONE PREMIO differenziale.
Covers:
 - POST/PUT /api/titoli con tipo='annullo' (bug Literal fix)
 - Tutti i tipi ammessi (nuova, rinnovo, appendice, regolazione, storno, quietanza, sostituzione, annullo)
 - provvigioni_operatori (persist array)
 - POST /api/polizze/{id}/regolazione-premio/calcola differenziale
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

# Polizza di test già flaggata regolazione_premio (contesto agent-to-agent)
POLIZZA_ID = "027c7a90-6965-4476-9004-c44e2c87575c"

TIPI_AMMESSI = [
    "nuova", "rinnovo", "appendice", "regolazione",
    "storno", "quietanza", "sostituzione", "annullo",
]


@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{API}/auth/login", json={
        "email": "admin@assicura.it", "password": "Admin123!",
    })
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, r.json()
    return tok


@pytest.fixture(scope="session")
def H(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def polizza_ok(H):
    r = requests.get(f"{API}/polizze/{POLIZZA_ID}", headers=H)
    if r.status_code != 200:
        pytest.skip(f"Polizza test non trovata: {r.status_code}")
    return r.json()


created_ids: list[str] = []


def _cleanup_titoli(H):
    for tid in list(created_ids):
        try:
            requests.delete(f"{API}/titoli/{tid}", headers=H)
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def _teardown(H):
    yield
    _cleanup_titoli(H)


# =============== TITOLI ===============

class TestTitoliTipi:
    """Verifica che ogni tipo (incl. 'annullo') sia accettato dal Literal del modello."""

    @pytest.mark.parametrize("tipo", TIPI_AMMESSI)
    def test_create_titolo_tipo(self, H, polizza_ok, tipo):
        payload = {
            "polizza_id": POLIZZA_ID,
            "tipo": tipo,
            "effetto": "2026-01-15",
            "scadenza": "2026-07-15",
            "importo_lordo": 250.0,
            "provvigioni": 25.0,
            "stato": "da_incassare",
        }
        r = requests.post(f"{API}/titoli", json=payload, headers=H)
        assert r.status_code == 201, f"tipo={tipo} → {r.status_code} {r.text}"
        d = r.json()
        assert d["tipo"] == tipo
        assert d["polizza_id"] == POLIZZA_ID
        assert "id" in d
        created_ids.append(d["id"])

        # GET verify persist via lista polizza
        lst = requests.get(f"{API}/titoli", headers=H, params={"polizza_id": POLIZZA_ID}).json()
        assert isinstance(lst, list)
        assert any(t.get("id") == d["id"] and t.get("tipo") == tipo for t in lst)


class TestTitoloUpdate:
    def test_put_titolo(self, H):
        # crea
        payload = {
            "polizza_id": POLIZZA_ID, "tipo": "appendice",
            "effetto": "2026-02-01", "scadenza": "2026-08-01",
            "importo_lordo": 100.0, "provvigioni": 10.0, "stato": "da_incassare",
        }
        r = requests.post(f"{API}/titoli", json=payload, headers=H)
        assert r.status_code == 201, r.text
        tid = r.json()["id"]
        created_ids.append(tid)

        # update
        r = requests.put(f"{API}/titoli/{tid}", json={
            "importo_lordo": 150.0, "provvigioni": 15.0, "note": "TEST_ITER60",
        }, headers=H)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["importo_lordo"] == 150.0
        assert d["provvigioni"] == 15.0
        assert d.get("note") == "TEST_ITER60"


class TestProvvigioniOperatori:
    """provvigioni_operatori: array di {operatore_id, operatore_nome, provvigione}"""

    def test_create_con_provvigioni_operatori(self, H):
        prov_op = [
            {"operatore_id": "op-1", "operatore_nome": "Mario Rossi", "provvigione": 30.0},
            {"operatore_id": "op-2", "operatore_nome": "Luigi Verdi", "provvigione": 20.0},
        ]
        r = requests.post(f"{API}/titoli", json={
            "polizza_id": POLIZZA_ID, "tipo": "nuova",
            "effetto": "2026-03-01", "scadenza": "2026-09-01",
            "importo_lordo": 500.0, "provvigioni": 50.0,
            "provvigioni_operatori": prov_op,
        }, headers=H)
        assert r.status_code == 201, r.text
        d = r.json()
        created_ids.append(d["id"])
        assert isinstance(d.get("provvigioni_operatori"), list)
        assert len(d["provvigioni_operatori"]) == 2
        assert d["provvigioni_operatori"][0]["operatore_nome"] == "Mario Rossi"
        assert d["provvigioni_operatori"][0]["provvigione"] == 30.0

    def test_put_aggiorna_provvigioni_operatori(self, H):
        r = requests.post(f"{API}/titoli", json={
            "polizza_id": POLIZZA_ID, "tipo": "rinnovo",
            "effetto": "2026-04-01", "scadenza": "2026-10-01",
            "importo_lordo": 200.0, "provvigioni": 20.0,
        }, headers=H)
        assert r.status_code == 201
        tid = r.json()["id"]
        created_ids.append(tid)

        new_ops = [{"operatore_id": "op-3", "operatore_nome": "Anna Bianchi", "provvigione": 40.0}]
        r = requests.put(f"{API}/titoli/{tid}", json={
            "provvigioni_operatori": new_ops, "provvigioni": 40.0,
        }, headers=H)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["provvigioni"] == 40.0
        assert len(d["provvigioni_operatori"]) == 1
        assert d["provvigioni_operatori"][0]["operatore_nome"] == "Anna Bianchi"


# =============== REGOLAZIONE DIFFERENZIALE ===============

class TestRegolazioneDifferenziale:
    def test_calcola_differenziale(self, H, polizza_ok):
        r = requests.post(
            f"{API}/polizze/{POLIZZA_ID}/regolazione-premio/calcola",
            json={
                "base_preventivo": 100000,
                "base_effettiva": 120000,
                "tasso_override": 2,
                "base_tipo": "fatturato",
                "periodo": "2025",
                "salva": False,
            },
            headers=H,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # differenza = 120000-100000 = 20000; premio = 20000*2/100 = 400
        assert d["differenza"] == 20000
        assert d["premio_calcolato"] == 400.0
        assert d["base_preventivo"] == 100000.0
        assert d["base_effettiva"] == 120000.0
        assert d["tasso_applicato_pct"] == 2
        # dovuto >= minima
        assert d["dovuto"] >= d["premio_calcolato"] or d["dovuto"] == d["premio_calcolato"]

    def test_calcola_negativo_a_credito(self, H):
        r = requests.post(
            f"{API}/polizze/{POLIZZA_ID}/regolazione-premio/calcola",
            json={
                "base_preventivo": 100000,
                "base_effettiva": 80000,
                "tasso_override": 1.5,
                "salva": False,
            },
            headers=H,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["differenza"] == -20000
        assert d["premio_calcolato"] == -300.0
        # regolazione a credito: dovuto NON deve applicare minima
        assert d["dovuto"] == -300.0

    def test_calcola_polizza_non_flaggata(self, H):
        # trova una polizza non flaggata
        pols = requests.get(f"{API}/polizze", headers=H).json()
        pol_nof = None
        for p in pols[:50] if isinstance(pols, list) else []:
            if not p.get("regolazione_premio") and p.get("id") != POLIZZA_ID:
                pol_nof = p["id"]
                break
        if not pol_nof:
            pytest.skip("Nessuna polizza non-flaggata trovata")
        r = requests.post(
            f"{API}/polizze/{pol_nof}/regolazione-premio/calcola",
            json={"base_preventivo": 100, "base_effettiva": 200, "tasso_override": 1, "salva": False},
            headers=H,
        )
        assert r.status_code == 400
