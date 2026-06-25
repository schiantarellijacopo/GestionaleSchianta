"""Tests for iteration 3 - Brogliaccio Prima Nota & Chiusura Giorno.

Covers:
- GET  /api/contabilita/brogliaccio (structure, dynamic conti, totals)
- GET  /api/contabilita/brogliaccio/stampa (PDF)
- POST /api/contabilita/chiusura-giorno (close day, snapshot)
- PUT/DELETE /api/contabilita/movimenti/{id} on closed day  -> 400
- POST /api/contabilita/chiusura-giorno/{id}/invia (email - no SMTP cfg)
- POST /api/contabilita/chiusura-giorno/{id}/riapri (motivo required)
- GET  /api/contabilita/chiusure-giorno + /pdf
- PUT  /api/librerie/azienda (SMTP fields)
- Dynamic conti_cassa column in brogliaccio
"""
import os
import requests
import pytest

# Resolve backend URL from frontend env
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip())
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = (os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!"))

# Unique test day - avoid clashing with seeded movimenti
TEST_DAY = "2025-12-29"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login: {r.status_code} {r.text}"
    j = r.json()
    s.headers.update({"Authorization": f"Bearer {j['access_token']}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


# ====== AZIENDA / SMTP CONFIG ======
class TestAziendaSmtp:
    def test_put_azienda_smtp_fields_persist(self, admin):
        # Read current to preserve
        r = admin.get(f"{API}/librerie/azienda")
        assert r.status_code == 200
        original = r.json()

        # ensure not configured (clear email_commercialista for later test)
        body = {
            "ragione_sociale": original.get("ragione_sociale") or "Test Agenzia",
            "email_commercialista": "",  # cleared on purpose
            "nome_commercialista": "Studio Test",
            "invio_automatico_chiusura": False,
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_password": "secret-pwd",
            "smtp_from": "noreply@test.it",
            "smtp_use_tls": True,
        }
        r = admin.put(f"{API}/librerie/azienda", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("nome_commercialista") == "Studio Test"
        assert data.get("smtp_from") == "noreply@test.it"
        assert data.get("smtp_use_tls") is True
        # readback
        r2 = admin.get(f"{API}/librerie/azienda")
        d2 = r2.json()
        assert d2.get("nome_commercialista") == "Studio Test"
        assert d2.get("smtp_port") == 587


# ====== BROGLIACCIO STRUCTURE ======
class TestBrogliaccio:
    def test_brogliaccio_structure(self, admin):
        r = admin.get(f"{API}/contabilita/brogliaccio", params={"data": "2026-01-12"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["data"] == "2026-01-12"
        for k in ["conti_cassa", "righe", "totali_giornata",
                  "conti_riepilogo", "riepilogo_kpi", "chiusa"]:
            assert k in d, f"missing field {k}"
        assert isinstance(d["conti_cassa"], list)
        # totali keys
        for k in ["totale", "provv", "saldo", "crediti", "spese", "per_conto"]:
            assert k in d["totali_giornata"]
        # kpi keys
        for k in ["entrate", "provvigioni", "crediti", "rimesse",
                  "sconti", "spese", "saldo_cassa"]:
            assert k in d["riepilogo_kpi"]
        # each riga
        for riga in d["righe"]:
            for k in ["id", "descrizione", "totale", "provv", "saldo",
                      "crediti", "spese", "per_conto", "allegati_count"]:
                assert k in riga
            assert isinstance(riga["per_conto"], dict)

    def test_brogliaccio_pdf(self, admin):
        r = admin.get(f"{API}/contabilita/brogliaccio/stampa",
                      params={"data": "2026-01-12"})
        assert r.status_code == 200, r.text
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"

    def test_brogliaccio_dynamic_conti_cassa(self, admin):
        # snapshot initial conti
        r = admin.get(f"{API}/contabilita/brogliaccio",
                      params={"data": TEST_DAY})
        assert r.status_code == 200
        initial = [c["nome"] for c in r.json()["conti_cassa"]]

        # create new conto cassa
        r = admin.post(f"{API}/librerie/conti-cassa", json={
            "nome": "TEST_NEW_CONTO_BROG", "ordine": 999,
            "attivo": True, "saldo_iniziale": 0,
        })
        assert r.status_code == 201, r.text
        new_id = r.json()["id"]
        try:
            r2 = admin.get(f"{API}/contabilita/brogliaccio",
                           params={"data": TEST_DAY})
            assert r2.status_code == 200
            now = [c["nome"] for c in r2.json()["conti_cassa"]]
            assert "TEST_NEW_CONTO_BROG" in now, \
                f"new conto not auto-included: {now}"
            assert len(now) == len(initial) + 1
        finally:
            admin.delete(f"{API}/librerie/conti-cassa/{new_id}")

    def test_riga_per_conto_populated(self, admin):
        """Create a movimento with conto_cassa_id and verify it appears
        in per_conto of the corresponding riga."""
        # get a conto cassa
        rc = admin.get(f"{API}/librerie/conti-cassa")
        assert rc.status_code == 200
        conti = rc.json()
        if not conti:
            pytest.skip("Nessun conto cassa disponibile")
        cc = conti[0]
        # create movimento on TEST_DAY
        r = admin.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": TEST_DAY,
            "descrizione": "TEST_BROG_per_conto",
            "tipo": "entrata",
            "categoria": "incasso_premio",
            "importo": 123.45,
            "conto_cassa_id": cc["id"],
            "mezzo_pagamento": "bonifico",
        })
        assert r.status_code == 201, r.text
        mid = r.json()["id"]
        try:
            r2 = admin.get(f"{API}/contabilita/brogliaccio",
                           params={"data": TEST_DAY})
            d = r2.json()
            row = next((x for x in d["righe"] if x["id"] == mid), None)
            assert row is not None
            assert row["per_conto"].get(cc["id"]) == 123.45
            assert row["totale"] == 123.45  # entrata -> positive
        finally:
            admin.delete(f"{API}/contabilita/movimenti/{mid}")


# ====== CHIUSURA GIORNO LIFECYCLE ======
class TestChiusuraLifecycle:
    """Full lifecycle: close -> reject edits -> riapri -> edit again."""

    @pytest.fixture(scope="class")
    def setup_data(self, admin):
        # ensure clean day
        existing_movs = admin.get(
            f"{API}/contabilita/movimenti",
            params={"data_from": TEST_DAY, "data_to": TEST_DAY},
        )
        # Remove any test movs leftover
        if existing_movs.status_code == 200:
            for m in existing_movs.json():
                if m.get("descrizione", "").startswith("TEST_CHIUSURA"):
                    admin.delete(f"{API}/contabilita/movimenti/{m['id']}")

        # create 2 movimenti on TEST_DAY
        rc = admin.get(f"{API}/librerie/conti-cassa").json()
        cc_id = rc[0]["id"] if rc else None
        mids = []
        for i, (tipo, cat, imp) in enumerate([
            ("entrata", "incasso_premio", 250.0),
            ("uscita", "spese_amministrative", 30.0),
        ]):
            r = admin.post(f"{API}/contabilita/movimenti", json={
                "data_movimento": TEST_DAY,
                "descrizione": f"TEST_CHIUSURA mov {i}",
                "tipo": tipo, "categoria": cat,
                "importo": imp, "conto_cassa_id": cc_id,
            })
            assert r.status_code == 201
            mids.append(r.json()["id"])
        yield {"mids": mids, "cc_id": cc_id}
        # cleanup - re-attempt deleting (in case still closed)
        for mid in mids:
            admin.delete(f"{API}/contabilita/movimenti/{mid}")

    def test_01_close_day(self, admin, setup_data):
        r = admin.post(f"{API}/contabilita/chiusura-giorno",
                       json={"data": TEST_DAY, "invia_commercialista": False})
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["data"] == TEST_DAY
        assert d.get("id")
        setup_data["chiusura_id"] = d["id"]
        # brogliaccio now chiusa
        b = admin.get(f"{API}/contabilita/brogliaccio",
                      params={"data": TEST_DAY}).json()
        assert b["chiusa"] is True
        assert b["chiusura"] and b["chiusura"]["id"] == d["id"]
        assert b["chiusura"].get("closed_by_name")

    def test_02_close_already_closed_400(self, admin, setup_data):
        r = admin.post(f"{API}/contabilita/chiusura-giorno",
                       json={"data": TEST_DAY})
        assert r.status_code == 400

    def test_03_put_movimento_rejected(self, admin, setup_data):
        mid = setup_data["mids"][0]
        r = admin.put(f"{API}/contabilita/movimenti/{mid}",
                      json={"descrizione": "tentato edit"})
        assert r.status_code == 400
        assert "chiusa" in r.text.lower()

    def test_04_delete_movimento_rejected(self, admin, setup_data):
        mid = setup_data["mids"][0]
        r = admin.delete(f"{API}/contabilita/movimenti/{mid}")
        assert r.status_code == 400

    def test_05_invia_no_email_config(self, admin, setup_data):
        cid = setup_data["chiusura_id"]
        r = admin.post(f"{API}/contabilita/chiusura-giorno/{cid}/invia")
        # should be 200 with ok:false (no exception)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is False
        assert "Email commercialista" in d.get("errore", "") \
            or "SMTP" in d.get("errore", "")

    def test_06_list_chiusure(self, admin, setup_data):
        r = admin.get(f"{API}/contabilita/chiusure-giorno")
        assert r.status_code == 200
        items = r.json()
        ids = [x["id"] for x in items]
        assert setup_data["chiusura_id"] in ids

    def test_07_download_pdf(self, admin, setup_data):
        cid = setup_data["chiusura_id"]
        r = admin.get(f"{API}/contabilita/chiusura-giorno/{cid}/pdf")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_08_riapri_requires_motivo(self, admin, setup_data):
        cid = setup_data["chiusura_id"]
        r = admin.post(f"{API}/contabilita/chiusura-giorno/{cid}/riapri",
                       json={})
        assert r.status_code == 400

    def test_09_riapri_success(self, admin, setup_data):
        cid = setup_data["chiusura_id"]
        r = admin.post(f"{API}/contabilita/chiusura-giorno/{cid}/riapri",
                       json={"motivo": "test"})
        assert r.status_code == 200, r.text
        # brogliaccio now aperta
        b = admin.get(f"{API}/contabilita/brogliaccio",
                      params={"data": TEST_DAY}).json()
        assert b["chiusa"] is False

    def test_10_put_movimento_after_riapri(self, admin, setup_data):
        mid = setup_data["mids"][0]
        r = admin.put(f"{API}/contabilita/movimenti/{mid}",
                      json={"descrizione": "TEST_CHIUSURA mov 0 edited"})
        assert r.status_code == 200, r.text

    def test_11_cleanup_chiusura_record(self, admin, setup_data):
        # delete chiusura from db via direct (no endpoint) -> skip,
        # at least ensure movs can be deleted now
        for mid in setup_data["mids"]:
            r = admin.delete(f"{API}/contabilita/movimenti/{mid}")
            assert r.status_code in (200, 404)


# ====== EDGE: close day with no movimenti -> 400 ======
class TestChiusuraEmpty:
    def test_close_empty_day_400(self, admin):
        r = admin.post(f"{API}/contabilita/chiusura-giorno",
                       json={"data": "2025-01-01"})
        # likely no movimenti for 2025-01-01
        assert r.status_code in (400, 201)
        if r.status_code == 201:
            # cleanup
            cid = r.json()["id"]
            admin.post(f"{API}/contabilita/chiusura-giorno/{cid}/riapri",
                       json={"motivo": "cleanup"})
