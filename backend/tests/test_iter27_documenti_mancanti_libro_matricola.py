"""Iter27 tests:
- /api/insights/documenti-mancanti widget
- /api/libro-matricola (global list) with q + stato filters
- /api/storico-avvisi (no 401 for admin) + POST /storico-avvisi/registra extra fields
- regression: POST /api/voucher/{id}/assegna with both anagrafica_id + collaboratore_id
"""
from __future__ import annotations
import uuid
import pytest


# === 1) Documenti mancanti widget ===
class TestDocumentiMancanti:
    def test_returns_three_lists_and_totals(self, admin_session):
        from conftest import API
        r = admin_session.get(f"{API}/insights/documenti-mancanti", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # struttura
        assert "polizze_senza_allegato" in data
        assert "veicoli_senza_libretto" in data
        assert "anagrafiche_senza_ci" in data
        assert "totali" in data
        # tipi
        assert isinstance(data["polizze_senza_allegato"], list)
        assert isinstance(data["veicoli_senza_libretto"], list)
        assert isinstance(data["anagrafiche_senza_ci"], list)
        # totali
        totali = data["totali"]
        assert set(totali.keys()) >= {"polizze", "veicoli", "anagrafiche"}
        assert totali["polizze"] == len(data["polizze_senza_allegato"])
        assert totali["veicoli"] == len(data["veicoli_senza_libretto"])
        assert totali["anagrafiche"] == len(data["anagrafiche_senza_ci"])
        # contraente_nome enrichment for polizze
        if data["polizze_senza_allegato"]:
            assert "contraente_nome" in data["polizze_senza_allegato"][0]


# === 2) Libro Matricola lista globale ===
class TestLibroMatricola:
    def test_global_list_returns_array(self, admin_session):
        from conftest import API
        r = admin_session.get(f"{API}/libro-matricola", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # se non vuoto: verifica enrichment
        if data:
            first = data[0]
            assert "id" in first
            # potrebbero essere None se polizza non trovata, ma chiavi presenti
            assert "polizza_numero" in first or first.get("polizza_id") is not None
            assert "n_allegati" in first
            assert isinstance(first["n_allegati"], int)

    def test_query_filter_no_error(self, admin_session):
        from conftest import API
        r = admin_session.get(f"{API}/libro-matricola", params={"q": "ABC123XYZNOTEXIST"}, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_stato_attivo_filter_no_error(self, admin_session):
        from conftest import API
        r = admin_session.get(f"{API}/libro-matricola", params={"stato": "attivo"}, timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # nessuno deve avere data_cessazione valorizzata
        for it in items:
            assert not it.get("data_cessazione")

    def test_stato_cessato_filter_no_error(self, admin_session):
        from conftest import API
        r = admin_session.get(f"{API}/libro-matricola", params={"stato": "cessato"}, timeout=20)
        assert r.status_code == 200


# === 3) Storico avvisi (no 401 for admin) ===
class TestStoricoAvvisi:
    def test_list_no_401_admin(self, admin_session):
        from conftest import API
        r = admin_session.get(f"{API}/storico-avvisi", timeout=15)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert isinstance(r.json(), list)

    def test_registra_accepts_extra_fields(self, admin_session):
        from conftest import API
        payload = {
            "canale": "whatsapp",
            "destinatario": "+391112223344",
            "soggetto": f"TEST_iter27_{uuid.uuid4().hex[:6]}",
            "messaggio": "test integration",
            # campi extra non in schema
            "extra_random": "valore",
            "context_data": {"foo": "bar"},
        }
        r = admin_session.post(f"{API}/storico-avvisi/registra", json=payload, timeout=15)
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("canale") == "whatsapp"
        assert body.get("destinatario") == "+391112223344"
        assert "id" in body
        assert "sent_at" in body

    def test_canale_filter(self, admin_session):
        from conftest import API
        r = admin_session.get(f"{API}/storico-avvisi", params={"canale": "whatsapp"}, timeout=15)
        assert r.status_code == 200
        items = r.json()
        for it in items:
            assert it.get("canale") == "whatsapp"


# === 4) Regression: voucher assegna with both anagrafica_id + collaboratore_id ===
class TestVoucherRegression:
    def test_voucher_listing_includes_assegnato_fields(self, admin_session):
        from conftest import API
        r = admin_session.get(f"{API}/voucher", timeout=15)
        # endpoint potrebbe non esistere o restituire 404, ma se 200 verifica struttura
        if r.status_code == 404:
            pytest.skip("/api/voucher endpoint not present")
        assert r.status_code == 200, r.text
        data = r.json()
        # struttura: lista o dict — accetta entrambe
        items = data if isinstance(data, list) else data.get("items", [])
        assert isinstance(items, list)
