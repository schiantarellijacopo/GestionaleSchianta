"""Iter5 tests:
- Brogliaccio movimento con conto_cassa_id e mezzo_pagamento
- Seed migration: RID Direzione → Pagamento Direzione; PayPal / Online attivo=false
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return s


# --- seed migration on startup ---
class TestSeedMigration:
    def test_no_rid_direzione(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/librerie/conti-cassa")
        assert r.status_code == 200
        items = r.json()
        names = [c["nome"] for c in items]
        assert "RID Direzione" not in names, f"RID Direzione still present: {names}"

    def test_pagamento_direzione_present(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/librerie/conti-cassa")
        items = r.json()
        names = [c["nome"] for c in items]
        assert "Pagamento Direzione" in names, f"Pagamento Direzione missing: {names}"

    def test_paypal_inactive_or_excluded_from_attivi(self, admin_client):
        # If paypal exists, it must be attivo=false (migration deactivates)
        r_all = admin_client.get(f"{BASE_URL}/api/librerie/conti-cassa")
        items = r_all.json()
        paypal = [c for c in items if c["nome"] == "PayPal / Online"]
        if paypal:
            assert paypal[0].get("attivo") == False, f"PayPal should be inactive: {paypal[0]}"

        # /attivi=true must NOT include paypal
        r_attivi = admin_client.get(f"{BASE_URL}/api/librerie/conti-cassa?attivi=true")
        if r_attivi.status_code == 200:
            attivi = r_attivi.json()
            assert all(c["nome"] != "PayPal / Online" for c in attivi)


# --- movimento with conto_cassa_id + mezzo_pagamento ---
class TestMovimentoConContoCassa:
    @pytest.fixture(scope="class")
    def conto(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/librerie/conti-cassa?attivi=true")
        assert r.status_code == 200
        attivi = r.json()
        assert len(attivi) > 0
        # use Pagamento Direzione if present, else first
        pd = [c for c in attivi if c["nome"] == "Pagamento Direzione"]
        return pd[0] if pd else attivi[0]

    def test_create_movimento_with_conto_persists(self, admin_client, conto):
        payload = {
            "data_movimento": "2026-01-15",
            "tipo": "entrata",
            "categoria": "incasso_premio",
            "importo": 123.45,
            "descrizione": "TEST_iter5 movimento con conto",
            "conto_cassa_id": conto["id"],
            "mezzo_pagamento": conto["nome"],
        }
        r = admin_client.post(f"{BASE_URL}/api/contabilita/movimenti", json=payload)
        assert r.status_code in (200, 201), f"Create movimento failed: {r.status_code} {r.text}"
        body = r.json()
        mov_id = body.get("id")
        assert mov_id, f"No id in response: {body}"
        assert body.get("conto_cassa_id") == conto["id"], f"conto_cassa_id not persisted: {body}"
        assert body.get("mezzo_pagamento") == conto["nome"], f"mezzo_pagamento not persisted: {body}"

        # Verify via brogliaccio (per-day endpoint)
        r2 = admin_client.get(f"{BASE_URL}/api/contabilita/brogliaccio",
                              params={"data": "2026-01-15"})
        assert r2.status_code == 200, f"Brogliaccio failed: {r2.status_code} {r2.text}"
        brog = r2.json()
        movs = brog.get("righe") or []
        found = [m for m in movs if m.get("id") == mov_id]
        assert found, f"Movimento {mov_id} not found in brogliaccio (count={len(movs)})"
        m = found[0]
        assert m.get("conto_cassa_id") == conto["id"], f"conto_cassa_id mismatch: {m}"
        assert m.get("mezzo_pagamento") == conto["nome"], f"mezzo_pagamento mismatch: {m}"

        # conti_cassa list in response should exclude PayPal
        conti_in_brog = brog.get("conti_cassa", [])
        assert all(c.get("nome") != "PayPal / Online" for c in conti_in_brog)
        nomi = [c.get("nome") for c in conti_in_brog]
        assert "Pagamento Direzione" in nomi, f"Pagamento Direzione missing from brogliaccio conti_cassa: {nomi}"

        # cleanup
        admin_client.delete(f"{BASE_URL}/api/contabilita/movimenti/{mov_id}")
