"""Iter18 - Regression tests for the cyclomatic-complexity refactor.

Verifies (a) backend import OK after refactor, (b) refactored helpers exist in
their modules, (c) HTTP endpoints still return the same contract for:
  * brogliaccio (PDF stampa)
  * avvisi-scadenze (preview + esegui)
  * geo/suggest
  * calcola-pensioni-future (uses inps_calculator.calcola_pensione)
  * ANIA import (HTTP)
  * regression smokes: auth, anagrafiche, polizze, dashboard tasks

Refactored functions (no behaviour change expected):
  - brogliaccio.py             : _classifica_movimento, _descrizione_movimento, _build_righe_dettaglio,
                                 _calcola_col_widths, _build_tabella_principale, _build_tabella_riepilogo,
                                 _load_movimenti_arricchiti
  - avvisi_scadenze.py         : _query_polizze_in_scadenza, _query_titoli_arretrati,
                                 _carica_anagrafiche, _carica_compagnie, _format_polizza_record,
                                 _format_titolo_record, _giorni_da_oggi,
                                 _build_log_entry, _resolve_destinatario, _persist_log
  - geocoder.py                : _nominatim_get, _estrai_comune, _estrai_indirizzo, _parse_item
  - inps_calculator.py         : _calcola_invalidita, _calcola_inabilita, _calcola_superstite,
                                 _aliquota_superstite
  - ania_importer.py           : _extract_zip_contents, _processa_anagrafiche, _processa_polizze,
                                 _processa_dettagli_veicolo, _processa_garanzie, _processa_titoli,
                                 _processa_sinistri, _conta_record_residui, _build_anagrafica_payload,
                                 _build_dettagli_veicolo, _get_or_create_compagnia
"""
import io
import os
import sys
import zipfile
from datetime import date, timedelta

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import API, ADMIN_EMAIL, ADMIN_PASSWORD  # noqa: E402


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_sess():
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# ----------------------------------------------------------------------------
# Module: refactored helper presence (white-box)
# ----------------------------------------------------------------------------
class TestRefactoredHelpersPresence:
    """Verify all helpers extracted by the refactor are present as importable symbols."""

    def test_brogliaccio_helpers_present(self):
        import brogliaccio  # noqa: F401
        for name in (
            "_classifica_movimento",
            "_descrizione_movimento",
            "_build_righe_dettaglio",
            "_calcola_col_widths",
            "_build_tabella_principale",
            "_build_tabella_riepilogo",
            "_load_movimenti_arricchiti",
        ):
            assert hasattr(brogliaccio, name), f"brogliaccio.{name} missing"

    def test_avvisi_scadenze_helpers_present(self):
        import avvisi_scadenze  # noqa: F401
        for name in (
            "_query_polizze_in_scadenza",
            "_query_titoli_arretrati",
            "_carica_anagrafiche",
            "_carica_compagnie",
            "_format_polizza_record",
            "_format_titolo_record",
            "_giorni_da_oggi",
            "_build_log_entry",
            "_persist_log",
        ):
            assert hasattr(avvisi_scadenze, name), f"avvisi_scadenze.{name} missing"

    def test_geocoder_helpers_present(self):
        import geocoder  # noqa: F401
        for name in ("_nominatim_get", "_estrai_comune", "_estrai_indirizzo", "_parse_item"):
            assert hasattr(geocoder, name), f"geocoder.{name} missing"

    def test_inps_calculator_helpers_present(self):
        import inps_calculator  # noqa: F401
        for name in (
            "_calcola_invalidita",
            "_calcola_inabilita",
            "_calcola_superstite",
            "_aliquota_superstite",
        ):
            assert hasattr(inps_calculator, name), f"inps_calculator.{name} missing"

    def test_ania_importer_helpers_present(self):
        import ania_importer  # noqa: F401
        for name in (
            "_extract_zip_contents",
            "_build_anagrafica_payload",
            "_build_dettagli_veicolo",
            "_get_or_create_compagnia",
            "_conta_record_residui",
        ):
            assert hasattr(ania_importer, name), f"ania_importer.{name} missing"


# ----------------------------------------------------------------------------
# Module: pure helper unit tests
# ----------------------------------------------------------------------------
class TestInpsCalculatorRefactor:
    """Unit tests on inps_calculator.calcola_pensione (refactored)."""

    def test_invalidita_basic(self):
        import inps_calculator
        out = inps_calculator.calcola_pensione(
            tipo="invalidita",
            settimane_contributive=520,  # 10 anni
            retribuzione_media_annua=20000.0,
            eta=50,
            percentuale_invalidita=75,
            numero_familiari=1,
        )
        assert "pensione_lorda_mensile" in out
        assert "pensione_lorda_annua" in out
        assert out["pensione_lorda_annua"] > 0
        assert out["pensione_lorda_mensile"] > 0

    def test_inabilita_basic(self):
        import inps_calculator
        out = inps_calculator.calcola_pensione(
            tipo="inabilita",
            settimane_contributive=520,
            retribuzione_media_annua=20000.0,
            eta=50,
            numero_familiari=1,
        )
        assert out["pensione_lorda_annua"] > 0
        assert out["pensione_lorda_mensile"] > 0

    def test_superstite_basic(self):
        import inps_calculator
        out = inps_calculator.calcola_pensione(
            tipo="superstite",
            settimane_contributive=520,
            retribuzione_media_annua=20000.0,
            eta=50,
            numero_familiari=2,
        )
        assert out["pensione_lorda_annua"] > 0

    def test_aliquota_superstite(self):
        import inps_calculator
        # Refactor extracts the survivor coefficient lookup. Returns (aliquota, note).
        v = inps_calculator._aliquota_superstite(numero_familiari=1)
        if isinstance(v, tuple):
            aliquota = v[0]
        else:
            aliquota = v
        assert 0 < aliquota <= 1, f"aliquota out of range: {aliquota}"
        v2 = inps_calculator._aliquota_superstite(numero_familiari=3)
        a2 = v2[0] if isinstance(v2, tuple) else v2
        assert 0 < a2 <= 1


class TestBrogliaccioHelpers:
    """White-box on brogliaccio refactor helpers."""

    def test_classifica_movimento_returns_dict(self):
        import brogliaccio
        # Refactor: _classifica_movimento returns a dict of totals (totale/prov/saldo/...)
        out = brogliaccio._classifica_movimento({"tipo": "titolo_incassato", "importo": 100.0})
        assert isinstance(out, dict), f"expected dict, got {type(out)}"
        for k in ("totale", "prov", "saldo", "crediti", "spese"):
            assert k in out, f"key {k} missing in classifica result"

    def test_calcola_col_widths_int_input(self):
        import brogliaccio
        # n_bank is an int, returns list of column widths
        ws = brogliaccio._calcola_col_widths(0)
        assert isinstance(ws, list) and len(ws) == 6
        ws3 = brogliaccio._calcola_col_widths(3)
        assert isinstance(ws3, list) and len(ws3) == 9


# ----------------------------------------------------------------------------
# Module: HTTP endpoint regression
# ----------------------------------------------------------------------------
class TestBrogliaccioEndpoint:
    def test_brogliaccio_stampa_pdf(self, admin_sess):
        oggi = date.today().isoformat()
        r = admin_sess.get(f"{API}/contabilita/brogliaccio/stampa", params={"data": oggi}, timeout=30)
        assert r.status_code == 200, f"Status {r.status_code} body={r.text[:300]}"
        ct = r.headers.get("content-type", "")
        assert "pdf" in ct.lower() or r.content[:4] == b"%PDF", f"Not a PDF response (ct={ct})"
        assert r.content[:4] == b"%PDF", "Body does not start with %PDF magic bytes"
        assert len(r.content) > 500, "PDF too small to be valid"

    def test_brogliaccio_json(self, admin_sess):
        oggi = date.today().isoformat()
        r = admin_sess.get(f"{API}/contabilita/brogliaccio", params={"data": oggi}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        # contract preserved
        assert isinstance(data, dict)


class TestAvvisiScadenzeEndpoint:
    def test_preview_returns_polizze_and_titoli(self, admin_sess):
        r = admin_sess.get(f"{API}/avvisi-scadenze/preview", params={"giorni": 30}, timeout=30)
        assert r.status_code == 200, f"Status {r.status_code} body={r.text[:300]}"
        data = r.json()
        assert "polizze" in data and isinstance(data["polizze"], list), "polizze key missing or not list"
        assert "titoli" in data and isinstance(data["titoli"], list), "titoli key missing or not list"
        assert "n_polizze" in data and "n_titoli" in data
        assert data["giorni"] == 30

    def test_preview_clamps_giorni(self, admin_sess):
        # 0 → clamped to 1
        r = admin_sess.get(f"{API}/avvisi-scadenze/preview", params={"giorni": 0}, timeout=15)
        assert r.status_code == 200
        assert r.json()["giorni"] >= 1

    def test_esegui_avvisi_scadenze(self, admin_sess):
        r = admin_sess.post(f"{API}/avvisi-scadenze/esegui", timeout=60)
        assert r.status_code == 200, f"Status {r.status_code} body={r.text[:300]}"
        data = r.json()
        # contract: must contain counters and either email_inviata or ok
        assert "n_polizze" in data or "n_titoli" in data or "ok" in data or "email_inviata" in data


class TestGeoSuggest:
    def test_geo_suggest_milano(self, admin_sess):
        # tolerant: external Nominatim can be flaky → only require 200 + array
        try:
            r = admin_sess.get(f"{API}/geo/suggest", params={"q": "Milano"}, timeout=20)
        except requests.RequestException as e:
            pytest.skip(f"Network error to Nominatim: {e}")
        assert r.status_code == 200, f"Status {r.status_code} body={r.text[:300]}"
        data = r.json()
        assert isinstance(data, list), "geo/suggest must return an array"
        # If Nominatim returned items, validate parse contract
        if data:
            item = data[0]
            assert isinstance(item, dict)
            # We only check that no exception in mapping; keys may vary.

    def test_geo_suggest_short_query(self, admin_sess):
        r = admin_sess.get(f"{API}/geo/suggest", params={"q": "M"}, timeout=15)
        # short queries should still be 200 (empty list) or 400 — both acceptable
        assert r.status_code in (200, 400), f"Unexpected status {r.status_code}"


class TestPensioniFuture:
    def test_calcola_pensioni_future_returns_pensioni_oggi(self, admin_sess):
        # pick first anagrafica
        ra = admin_sess.get(f"{API}/anagrafiche", params={"limit": 1}, timeout=15)
        assert ra.status_code == 200
        anag = ra.json()
        if isinstance(anag, dict):
            anag = anag.get("items") or anag.get("data") or []
        if not anag:
            pytest.skip("No anagrafiche in DB")
        aid = anag[0]["id"]
        r = admin_sess.post(f"{API}/anagrafiche/{aid}/analisi/calcola-pensioni-future", timeout=30)
        assert r.status_code == 200, f"Status {r.status_code} body={r.text[:300]}"
        data = r.json()
        assert "pensioni_oggi" in data, "pensioni_oggi key missing"
        po = data["pensioni_oggi"]
        for tipo in ("invalidita", "inabilita", "superstite"):
            assert tipo in po, f"{tipo} missing in pensioni_oggi"
            assert "pensione_lorda_mensile" in po[tipo]
            assert "pensione_lorda_annua" in po[tipo]


# ----------------------------------------------------------------------------
# Module: ANIA import (HTTP)
# ----------------------------------------------------------------------------
REC10 = (
    "id_anagrafica_exp;ragione_sociale;codice_fiscale;partita_iva;data_nascita;"
    "comune_nascita;provincia_nascita;sesso_share;indirizzo;comune;provincia;"
    "cap;nazione;numero_telefono;cellulare;email;iban;consenso_privacy;"
    "data_consenso_privacy;compagnia_exp;compagnia_ania\n"
    "ITER18A;TEST ITER18;TST18A80A01H501Z;;01/01/1980;ROMA;RM;M;VIA TEST 1;"
    "ROMA;RM;00100;ITALIA;06000000;3330000000;iter18@example.com;;S;01/01/2024;CATTOLICA;001\n"
)
REC20 = (
    "id_polizza_exp;numero_polizza_cmp;id_anagrafica_exp;compagnia_exp;compagnia_ania;"
    "ramo_share;ramo_cmp;prodotto_cmp;cod_stato_share;effetto;scadenza_originale;"
    "lordo_totale;netto_totale;provvigioni_totali\n"
    "ITER18POL;99999991;ITER18A;CATTOLICA;001;INF;040;TEST;A;01/06/2024;01/06/2025;"
    "100,00;80,00;10,00\n"
)
REC40 = (
    "id_titolo_exp;id_polizza_exp;effetto_titolo;data_scadenza_emesso;stato_share;"
    "lordo_totale;netto_totale;tasse_totale;provvigioni_totale;dt_pag_cliente;mezzo_pag_share\n"
    "ITER18T;ITER18POL;01/06/2024;01/06/2025;I;100,00;80,00;20,00;10,00;05/06/2024;BON\n"
)


def _build_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("rec10oweb.csv", REC10)
        zf.writestr("rec20oweb.csv", REC20)
        zf.writestr("rec40oweb.csv", REC40)
    return buf.getvalue()


class TestAniaImportHttp:
    def test_import_ania_zip_200(self, admin_sess):
        zb = _build_zip()
        files = {"file": ("iter18.zip", zb, "application/zip")}
        r = admin_sess.post(f"{API}/import/ania", files=files, timeout=60)
        assert r.status_code == 200, f"Status {r.status_code} body={r.text[:400]}"
        log = r.json()
        # contract: must contain counters
        for key in (
            "anagrafiche_create",
            "anagrafiche_aggiornate",
            "polizze_create",
            "polizze_aggiornate",
            "titoli_creati",
            "stato",
        ):
            assert key in log, f"{key} missing from import log"
        # At least one new or updated record
        assert (log["anagrafiche_create"] + log["anagrafiche_aggiornate"]) >= 1
        assert (log["polizze_create"] + log["polizze_aggiornate"]) >= 1


# ----------------------------------------------------------------------------
# Module: regression smokes
# ----------------------------------------------------------------------------
class TestSmoke:
    def test_admin_login(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10,
        )
        assert r.status_code == 200

    def test_anagrafiche_list(self, admin_sess):
        r = admin_sess.get(f"{API}/anagrafiche", timeout=15)
        assert r.status_code == 200

    def test_polizze_list(self, admin_sess):
        r = admin_sess.get(f"{API}/polizze", timeout=15)
        assert r.status_code == 200

    def test_dashboard_tasks(self, admin_sess):
        r = admin_sess.get(f"{API}/dashboard/tasks", timeout=15)
        assert r.status_code == 200
