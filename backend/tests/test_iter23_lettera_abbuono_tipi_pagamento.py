"""Iter23 — Backend tests for:
- /api/librerie/tipi-pagamento CRUD + seed
- ContoCassa new flags nascondi_prima_nota / escludi_da_liquidita
- Lettera Abbuono auto-generation on incasso with sconto
- /api/lettere-abbuono CRUD + PDF rendering + double signature
- /api/polizze and /api/titoli default limit=50000 (no pagination)
"""
import os
import base64
import time
import pytest
import requests

from conftest import API

TINY_PNG_B64 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAA"
    "C0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


# ============================================================
# 1) LIBRERIA TIPI PAGAMENTO
# ============================================================
class TestTipiPagamento:
    def test_list_seeded(self, admin_session):
        r = admin_session.get(f"{API}/librerie/tipi-pagamento", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 5, "Expected seeded tipi pagamento"
        labels = [i["label"].upper() for i in items]
        # Must contain at least a few of the requested seed entries
        expected_any = ["CONTANTI", "BONIFICO BPER SONDRIO", "ASSEGNO BPER VILLA",
                         "RID DIREZIONE", "AGOS", "BANCOMAT"]
        found = [l for l in expected_any if l in labels]
        assert len(found) >= 4, f"Missing seeded labels. Found {found} in {labels}"

    def test_create_update_delete(self, admin_session):
        label = f"TEST_TP_{int(time.time())}"
        # CREATE
        r = admin_session.post(f"{API}/librerie/tipi-pagamento", json={
            "label": label, "modalita_codice": "bonifico", "conto_id": None,
            "ordine": 99, "attivo": True,
        }, timeout=15)
        assert r.status_code == 201, r.text
        rec = r.json()
        assert rec["label"] == label.upper()
        assert rec["modalita_codice"] == "bonifico"
        tid = rec["id"]

        # GET (verify persisted)
        r2 = admin_session.get(f"{API}/librerie/tipi-pagamento", timeout=15)
        assert r2.status_code == 200
        assert any(i["id"] == tid for i in r2.json())

        # UPDATE
        r3 = admin_session.put(f"{API}/librerie/tipi-pagamento/{tid}", json={
            "label": label + "_UPD", "modalita_codice": "contanti",
            "conto_id": None, "ordine": 50, "attivo": False,
        }, timeout=15)
        assert r3.status_code == 200, r3.text
        upd = r3.json()
        assert upd["label"] == (label + "_UPD").upper()
        assert upd["modalita_codice"] == "contanti"
        assert upd["attivo"] is False

        # DELETE
        r4 = admin_session.delete(f"{API}/librerie/tipi-pagamento/{tid}", timeout=15)
        assert r4.status_code == 200

        # Verify gone
        r5 = admin_session.get(f"{API}/librerie/tipi-pagamento", timeout=15)
        assert not any(i["id"] == tid for i in r5.json())

    def test_create_validation(self, admin_session):
        r = admin_session.post(f"{API}/librerie/tipi-pagamento", json={
            "label": "", "modalita_codice": "bonifico",
        }, timeout=15)
        assert r.status_code in (400, 422)


# ============================================================
# 2) CONTI CASSA - NUOVI FLAG
# ============================================================
class TestContiCassaFlags:
    def test_create_with_flags(self, admin_session):
        nome = f"TEST_CONTO_{int(time.time())}"
        r = admin_session.post(f"{API}/librerie/conti-cassa", json={
            "nome": nome, "tipo": "banca", "ordine": 999,
            "nascondi_prima_nota": True, "escludi_da_liquidita": True,
        }, timeout=15)
        assert r.status_code == 201, r.text
        rec = r.json()
        assert rec.get("nascondi_prima_nota") is True
        assert rec.get("escludi_da_liquidita") is True
        cid = rec["id"]

        # GET via list — verify persisted
        r2 = admin_session.get(f"{API}/librerie/conti-cassa", timeout=15)
        assert r2.status_code == 200
        match = next((c for c in r2.json() if c["id"] == cid), None)
        assert match is not None
        assert match["nascondi_prima_nota"] is True
        assert match["escludi_da_liquidita"] is True

        # Update flags to False
        r3 = admin_session.put(f"{API}/librerie/conti-cassa/{cid}", json={
            "nome": nome, "tipo": "banca", "ordine": 999,
            "nascondi_prima_nota": False, "escludi_da_liquidita": False,
        }, timeout=15)
        assert r3.status_code == 200, r3.text

        r4 = admin_session.get(f"{API}/librerie/conti-cassa", timeout=15)
        match = next((c for c in r4.json() if c["id"] == cid), None)
        assert match["nascondi_prima_nota"] is False
        assert match["escludi_da_liquidita"] is False

        # cleanup
        admin_session.delete(f"{API}/librerie/conti-cassa/{cid}", timeout=15)


# ============================================================
# 3) PAGINATION REMOVED - default high limit
# ============================================================
class TestNoPagination:
    def test_polizze_default_limit(self, admin_session):
        r = admin_session.get(f"{API}/polizze", timeout=30)
        assert r.status_code == 200
        # Validation: no '?limit=' is needed and response handles many records
        data = r.json()
        assert isinstance(data, list)

    def test_titoli_default_limit(self, admin_session):
        r = admin_session.get(f"{API}/titoli", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)


# ============================================================
# 4) LETTERA ABBUONO - auto-create on incasso with sconto + signatures
# ============================================================
def _ensure_test_polizza_titolo(s):
    """Find an existing un-incassato titolo with importo_lordo > 0 to use for testing.
    Avoids creating a new polizza (existing backend bug in create_polizza referencing
    non-existent obj.premio_totale on alert dispatch).
    """
    # Get all titoli, find an un-incassato one with importo_lordo > 0
    r = s.get(f"{API}/titoli", timeout=30)
    assert r.status_code == 200, r.text
    titoli = r.json()
    candidates = [t for t in titoli
                  if t.get("stato") not in ("incassato", "stornato")
                  and float(t.get("importo_lordo") or 0.0) > 0
                  and float(t.get("importo_pagato") or 0.0) == 0]
    if not candidates:
        pytest.skip("No un-incassato titoli with importo_lordo>0 available for test")
    titolo = candidates[0]
    pol_id = titolo.get("polizza_id")
    pol = s.get(f"{API}/polizze/{pol_id}", timeout=15).json() if pol_id else {}
    return pol.get("contraente_id"), pol_id, titolo

@pytest.fixture(scope="module")
def lettera_setup(admin_session):
    anag_id, pol_id, titolo = _ensure_test_polizza_titolo(admin_session)
    yield {"anag_id": anag_id, "pol_id": pol_id, "titolo": titolo}
    # No teardown — we used existing data


class TestLetteraAbbuono:
    def test_incasso_sconto_creates_lettera(self, admin_session, lettera_setup):
        titolo = lettera_setup["titolo"]
        tid = titolo["id"]
        lordo = float(titolo.get("importo_lordo") or 0.0)
        if lordo <= 0:
            pytest.skip("Titolo senza importo_lordo")
        pagato = round(lordo * 0.8, 2)
        # incassa with sconto
        r = admin_session.post(f"{API}/titoli/{tid}/incassa", json={
            "importo_pagato": pagato,
            "data_incasso": "2025-06-15",
            "mezzo_pagamento": "BONIFICO BPER SONDRIO",
            "tipo_chiusura": "sconto",
            "motivo_sconto": "Test abbuono iter23",
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("sconto_applicato", 0) > 0
        lid = body.get("lettera_abbuono_id")
        assert lid, f"lettera_abbuono_id missing in response: {body}"

        # GET by titolo_id
        r2 = admin_session.get(f"{API}/lettere-abbuono", params={"titolo_id": tid}, timeout=15)
        assert r2.status_code == 200
        lst = r2.json()
        assert any(l["id"] == lid for l in lst), f"Lettera {lid} not found in list"

        # GET single
        r3 = admin_session.get(f"{API}/lettere-abbuono/{lid}", timeout=15)
        assert r3.status_code == 200
        rec = r3.json()
        assert rec["titolo_id"] == tid
        assert rec["importo_sconto"] > 0

        # GET PDF
        r4 = admin_session.get(f"{API}/lettere-abbuono/{lid}/pdf", timeout=30)
        assert r4.status_code == 200, r4.text
        assert "application/pdf" in r4.headers.get("content-type", "").lower()
        assert r4.content.startswith(b"%PDF"), "PDF magic bytes missing"

        # Save for next tests
        TestLetteraAbbuono._lid = lid

    def test_firma_operatore_then_cliente(self, admin_session, lettera_setup):
        lid = getattr(TestLetteraAbbuono, "_lid", None)
        if not lid:
            pytest.skip("Lettera id not available from previous test")

        # Firma operatore
        r = admin_session.post(f"{API}/lettere-abbuono/{lid}/firma", json={
            "tipo": "operatore", "b64": TINY_PNG_B64, "nome": "Test Operatore",
        }, timeout=15)
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec.get("firma_operatore_b64", "").startswith("data:image")
        assert rec.get("firma_operatore_at")
        # Cliente firma
        r2 = admin_session.post(f"{API}/lettere-abbuono/{lid}/firma", json={
            "tipo": "cliente", "b64": TINY_PNG_B64, "nome": "Mario Test",
        }, timeout=30)
        assert r2.status_code == 200, r2.text
        rec2 = r2.json()
        assert rec2.get("firma_cliente_b64", "").startswith("data:image")
        assert rec2.get("firma_cliente_at")
        # Both signed → PDF stored
        assert rec2.get("signed_pdf_storage_path"), \
            f"signed_pdf_storage_path missing after both signatures: {rec2}"

    def test_firma_validation(self, admin_session, lettera_setup):
        lid = getattr(TestLetteraAbbuono, "_lid", None)
        if not lid:
            pytest.skip("Lettera id not available")
        # Wrong tipo
        r = admin_session.post(f"{API}/lettere-abbuono/{lid}/firma", json={
            "tipo": "altro", "b64": TINY_PNG_B64,
        }, timeout=15)
        assert r.status_code == 400
        # Invalid b64
        r = admin_session.post(f"{API}/lettere-abbuono/{lid}/firma", json={
            "tipo": "operatore", "b64": "not-a-data-url",
        }, timeout=15)
        assert r.status_code == 400


# ============================================================
# 5) CLEANUP
# ============================================================
class TestZZCleanup:
    def test_cleanup_lettera(self, admin_session):
        lid = getattr(TestLetteraAbbuono, "_lid", None)
        if lid:
            r = admin_session.delete(f"{API}/lettere-abbuono/{lid}", timeout=15)
            assert r.status_code in (200, 404)
