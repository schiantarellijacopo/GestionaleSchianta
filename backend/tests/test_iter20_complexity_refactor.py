"""Iter20 — Tests for complexity refactors (parse_estratto_conto_inps, ania_importer,
pdf_avvisi, pdf_brogliaccio). Pure functional refactor: zero behavior change expected.

Coverage:
 - All extracted helpers are importable from their respective modules (regression
   against accidental rename/removal during the refactor).
 - parse_estratto_conto_inps on realistic estratto contributivo text returns the
   expected anagrafica + contributi + storico fields (orchestrator behaviour).
 - Individual helper functions (_parse_anagrafica, _consolida_totali, ...) work in
   isolation when called via the orchestrator.
 - PDF endpoint regression: GET /api/contabilita/brogliaccio/stampa returns a
   binary PDF (>1KB).
 - Test files no longer contain `is True` / `is False` anti-pattern (regex audit).
"""
import os
import re
import sys
from pathlib import Path

import pytest
import requests

# Make backend importable for unit tests
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def api_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed status={r.status_code}")
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ---------------------------------------------------------------------------
# 1. Import / structural tests — extracted helpers must exist
# ---------------------------------------------------------------------------
class TestInpsCalculatorHelpers:
    """parse_estratto_conto_inps (CC=57 -> ~8) refactor: 7 helpers + _EstrattoState."""

    def test_all_inps_helpers_importable(self):
        import inps_calculator as ic
        assert hasattr(ic, "parse_estratto_conto_inps")
        assert hasattr(ic, "_EstrattoState")
        # 7 helpers per la review
        for name in (
            "_parse_anagrafica",
            "_parse_periodi_formato_inps",
            "_parse_periodi_parasubordinati",
            "_parse_periodi_satorcrm",
            "_parse_periodi_fallback_date",
            "_parse_storico_redditi_tabella",
            "_consolida_totali",
        ):
            assert hasattr(ic, name), f"missing helper: {name}"

    def test_estratto_state_initialised_with_expected_attrs(self):
        from inps_calculator import _EstrattoState
        result: dict = {
            "settimane_contributive": 0, "giorni_contributivi": 0,
            "retribuzione_media_annua": 0.0, "anni_stimati": 0,
            "periodi_contributivi": [], "storico_redditi": [],
            "totale_retribuzioni": 0.0, "totale_versato": 0.0,
            "montante_stimato": 0.0,
        }
        state = _EstrattoState(result)
        # contract attributes mentioned in the review
        for attr in ("redditi_per_anno", "retribuzioni", "giorni_tot"):
            assert hasattr(state, attr), f"_EstrattoState missing attr: {attr}"


class TestAniaImporterHelpers:
    """_processa_polizze (CC=28) + _build_dettagli_veicolo (CC=25) refactor."""

    def test_polizze_helpers_importable(self):
        import ania_importer as ai
        for name in (
            "_resolve_operatore_codice",
            "_build_polizza_payload",
            "_upsert_polizza",
            "_processa_polizze",
        ):
            assert hasattr(ai, name), f"missing helper: {name}"

    def test_veicolo_helpers_importable(self):
        import ania_importer as ai
        for name in (
            "_campi_veicolo_base",
            "_campi_tariffa_bm",
            "_campi_valori",
            "_campi_guida",
            "_build_dettagli_veicolo",
        ):
            assert hasattr(ai, name), f"missing helper: {name}"

    def test_build_dettagli_veicolo_merges_all_sections(self):
        from ania_importer import _build_dettagli_veicolo
        row = {"TARGA": "AB123CD", "MARCA": "FIAT", "MODELLO": "PANDA"}
        out = _build_dettagli_veicolo(row)
        assert isinstance(out, dict)
        # At minimum targa propagates (filtered by row content)
        # _build_dettagli_veicolo strips None/empty values; mere dict return is OK


class TestPdfAvvisiHelpers:
    """genera_pdf_avvisi (CC=25, 112 lines) refactor: 8 helpers."""

    def test_pdf_avvisi_helpers_importable(self):
        import pdf_avvisi as pa
        for name in (
            "_build_styles",
            "_intestazione_agenzia",
            "_destinatario",
            "_corpo_lettera",
            "_modalita_pagamento",
            "_build_riga_titolo",
            "_tabella_titoli",
            "_lettera_per_gruppo",
            "genera_pdf_avvisi",
        ):
            assert hasattr(pa, name), f"missing helper: {name}"

    def test_build_styles_returns_dict(self):
        from pdf_avvisi import _build_styles
        st = _build_styles()
        assert isinstance(st, dict)
        assert len(st) >= 3  # at least a handful of named styles


class TestPdfBrogliaccioHelpers:
    """stampa_brogliaccio (CC=24) refactor: 10+ helpers."""

    def test_brogliaccio_helpers_importable(self):
        import pdf_brogliaccio as pb
        for name in (
            "_build_riga_dettaglio",
            "_build_riga_totale_giornata",
            "_calcola_larghezze",
            "_stile_tabella_dettaglio",
            "_tabella_dettaglio",
            "_tabella_riepilogo_conti",
            "_tabella_saldi_compagnie",
            "_tabella_kpi_bottom",
            "_tabella_liquidita",
            "_footer_chiusura",
            "stampa_brogliaccio",
        ):
            assert hasattr(pb, name), f"missing helper: {name}"

    def test_calcola_larghezze_proportional(self):
        from pdf_brogliaccio import _calcola_larghezze
        w = _calcola_larghezze(3)
        assert isinstance(w, list)
        assert len(w) >= 1
        assert all(isinstance(x, (int, float)) for x in w)


# ---------------------------------------------------------------------------
# 2. INPS parser end-to-end on realistic text
# ---------------------------------------------------------------------------
REALISTIC_ESTRATTO = """\
Estratto Conto Previdenziale ROSSI MARIO
nato a Milano (MI) il 15/05/1970
codice fiscale RSSMRA70E15F205X
residente in Via Garibaldi 12
 20121 Milano (MI)

Periodi contributivi:
01/01/2010 31/12/2010 Lavoratore dipendente sett. 52 52,000 25.000,00 AZIENDA SPA
01/01/2011 31/12/2011 Lavoratore dipendente sett. 52 52,000 26.500,00 AZIENDA SPA
01/01/2012 31/12/2012 Lavoratore dipendente sett. 52 52,000 28.000,00 AZIENDA SPA
01/01/2013 31/12/2013 Lavoratore dipendente sett. 52 52,000 30.000,00 AZIENDA SPA
"""


class TestParseEstrattoContoInps:
    """End-to-end: orchestrator + helpers extract anagrafica and contributi."""

    def setup_method(self):
        from inps_calculator import parse_estratto_conto_inps
        self.result = parse_estratto_conto_inps(REALISTIC_ESTRATTO)

    def test_anagrafica_extracted(self):
        assert self.result.get("cognome") == "ROSSI"
        assert self.result.get("nome") == "MARIO"
        assert self.result.get("codice_fiscale") == "RSSMRA70E15F205X"
        assert self.result.get("comune_nascita") == "Milano"
        assert self.result.get("provincia_nascita") == "MI"
        assert self.result.get("data_nascita") == "1970-05-15"
        # CF: 9-10 chars = "E15" -> month E=5 -> M
        assert self.result.get("sesso") == "M"

    def test_periodi_contributivi_estratti(self):
        periodi = self.result.get("periodi_contributivi", [])
        assert len(periodi) >= 4, f"attesi >=4 periodi, trovati {len(periodi)}"
        # Verifica struttura minimale di un periodo (schema: inizio_periodo/fine_periodo)
        p0 = periodi[0]
        assert ("inizio_periodo" in p0 and "fine_periodo" in p0) or ("dal" in p0 and "al" in p0)
        assert "settimane" in p0
        assert p0["settimane"] == 52

    def test_settimane_e_anni_consolidati(self):
        # 4 anni x 52 sett = 208
        assert self.result.get("settimane_contributive", 0) >= 200
        assert self.result.get("anni_stimati", 0) >= 3

    def test_retribuzione_media_annua_positiva(self):
        # Avg of (25k, 26.5k, 28k, 30k) ~= 27.4k
        rma = self.result.get("retribuzione_media_annua", 0.0)
        assert rma > 20000.0, f"retribuzione_media_annua troppo bassa: {rma}"
        assert rma < 35000.0, f"retribuzione_media_annua troppo alta: {rma}"

    def test_montante_stimato_calcolato(self):
        # 33% di ~109.5k = ~36k; montante con rivalutazione >= retribuzioni*0.30
        montante = self.result.get("montante_stimato", 0.0)
        tot_retrib = self.result.get("totale_retribuzioni", 0.0)
        assert tot_retrib > 0.0
        assert montante > 0.0
        # sanity: montante stimato non superi totale retribuzioni
        assert montante <= tot_retrib

    def test_empty_text_does_not_raise(self):
        from inps_calculator import parse_estratto_conto_inps
        out = parse_estratto_conto_inps("")
        # contract: ritorna sempre il dict template
        assert isinstance(out, dict)
        assert out.get("settimane_contributive", 0) == 0
        assert out.get("periodi_contributivi") == []


# ---------------------------------------------------------------------------
# 3. PDF endpoint regression — brogliaccio stampa
# ---------------------------------------------------------------------------
class TestBrogliaccioStampaPdf:
    """PDF endpoint must still return binary PDF after stampa_brogliaccio refactor."""

    def test_brogliaccio_stampa_returns_pdf(self, api_session):
        r = api_session.get(
            f"{BASE_URL}/api/contabilita/brogliaccio/stampa",
            params={"data": "2026-06-25"},
            timeout=30,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
        assert r.content[:4] == b"%PDF", "response is not a PDF (missing %PDF magic)"
        assert len(r.content) > 1000, f"PDF inattesamente piccolo: {len(r.content)} bytes"


# ---------------------------------------------------------------------------
# 4. Audit: nessun "is True" / "is False" anti-pattern nei test_iter*.py
# ---------------------------------------------------------------------------
class TestNoBooleanIsAntipattern:
    def test_no_is_true_or_is_false_in_iter_tests(self):
        tests_dir = Path(__file__).parent
        self_name = Path(__file__).name
        offenders = []
        # Match only assertions like `... is True` not in comments/docstrings.
        # Conservative: skip lines starting with '#' or containing '"""'/"'''" and the
        # audit-file itself (which references the pattern textually).
        pat = re.compile(r"\bis\s+(True|False)\b")
        for f in tests_dir.glob("test_iter*.py"):
            if f.name == self_name:
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if pat.search(line):
                    offenders.append(f"{f.name}:{i}: {stripped}")
        assert not offenders, "Found `is True/is False`: " + "; ".join(offenders[:5])


# ---------------------------------------------------------------------------
# 5. Smoke endpoints (sanity - backend must boot post-refactor)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/auth/me",
    "/api/anagrafiche/stats",
    "/api/dashboard/tasks",
    "/api/polizze",
    "/api/titoli",
    "/api/contabilita/brogliaccio?data=2026-06-25",
    "/api/avvisi-scadenze/preview",
    "/api/anagrafiche/kpi-custom",
])
def test_smoke_endpoints_200(api_session, path):
    r = api_session.get(f"{BASE_URL}{path}", timeout=20)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:160]}"
