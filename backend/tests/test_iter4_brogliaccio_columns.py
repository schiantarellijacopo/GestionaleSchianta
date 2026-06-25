"""Iteration 4 - Brogliaccio adjustments:
- Conti cassa: 'PayPal / Online' nascosto (attivo=false), 'RID Direzione' rinominato in 'Pagamento Direzione'.
- Saldo per incassi premio quando compagnia.trattiene_provvigioni=False -> saldo = -provv (negativo).
- totali_giornata mantiene comunque sconti/rimesse (mostrati nei KPI).
- PDF stampa non contiene piu' colonne 'Sconti'/'Rimesse' nella tabella principale.
"""
import os
import io
import uuid
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip())
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = (os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!"))
TEST_DAY = "2025-12-30"  # day with no seeded data

def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login: {r.status_code} {r.text}"
    j = r.json()
    if j.get("access_token"):
        s.headers.update({"Authorization": f"Bearer {j['access_token']}"})
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


# ===== 1) Conti cassa list filtering / rename =====
class TestContiCassaRename:
    def test_brogliaccio_conti_cassa_excludes_paypal_and_includes_pagamento_direzione(self, admin):
        r = admin.get(f"{API}/contabilita/brogliaccio")
        assert r.status_code == 200, r.text
        data = r.json()
        nomi = [c["nome"] for c in data.get("conti_cassa", [])]
        # negative checks
        assert "PayPal / Online" not in nomi, f"PayPal/Online should be hidden, got: {nomi}"
        assert "RID Direzione" not in nomi, f"RID Direzione should be renamed, got: {nomi}"
        # positive checks
        assert "Pagamento Direzione" in nomi, f"Pagamento Direzione missing: {nomi}"
        for n in ("Cassa Contanti", "Assegni", "BPER Sondrio", "Intesa Sanpaolo", "Credit Agricole"):
            assert n in nomi, f"{n} missing from conti_cassa: {nomi}"

    def test_librerie_conti_cassa_lists_pagamento_direzione_active(self, admin):
        """The endpoint /api/librerie/conti-cassa is the source for dropdowns."""
        r = admin.get(f"{API}/librerie/conti-cassa")
        assert r.status_code == 200, r.text
        items = r.json()
        # All returned items should be active when no filter; pagamento direzione present
        attivi = [c for c in items if c.get("attivo", True)]
        nomi_attivi = [c["nome"] for c in attivi]
        assert "Pagamento Direzione" in nomi_attivi, f"missing Pagamento Direzione among attivi: {nomi_attivi}"
        # PayPal may still exist in DB but must be attivo=false
        paypal = [c for c in items if c["nome"] == "PayPal / Online"]
        if paypal:
            assert paypal[0].get("attivo") is False, "PayPal/Online must have attivo=false"
        # RID Direzione should not exist (renamed)
        assert not [c for c in items if c["nome"] == "RID Direzione"], "RID Direzione must be renamed"


# ===== 2) Saldo calculation for incasso_premio =====
class TestSaldoTrattiene:
    """Create two compagnie (trattiene=true / trattiene=false), two polizze, two movimenti
    on the same TEST_DAY and verify the riga.saldo computed by _compute_brogliaccio.
    """
    cleanup = {"movimenti": [], "polizze": [], "compagnie": [], "anagrafiche": []}

    @pytest.fixture(scope="class", autouse=True)
    def teardown(self, admin, request):
        yield
        for mid in self.cleanup["movimenti"]:
            admin.delete(f"{API}/contabilita/movimenti/{mid}")
        for pid in self.cleanup["polizze"]:
            admin.delete(f"{API}/polizze/{pid}")
        for cid in self.cleanup["compagnie"]:
            admin.delete(f"{API}/compagnie/{cid}")
        for aid in self.cleanup["anagrafiche"]:
            admin.delete(f"{API}/anagrafiche/{aid}")

    def _create_anagrafica(self, admin, suffix):
        body = {
            "tipo": "persona_fisica",
            "ragione_sociale": f"TEST Iter4 Cliente {suffix}",
            "codice_fiscale": f"TST{uuid.uuid4().hex[:8].upper()}",
            "email": f"test_iter4_{suffix}@example.com",
        }
        r = admin.post(f"{API}/anagrafiche", json=body)
        assert r.status_code in (200, 201), r.text
        aid = r.json()["id"]
        self.cleanup["anagrafiche"].append(aid)
        return aid

    def _create_compagnia(self, admin, trattiene: bool, suffix: str):
        body = {
            "codice": f"TST{uuid.uuid4().hex[:6].upper()}",
            "ragione_sociale": f"TEST Iter4 Comp {'TRAT' if trattiene else 'NOTRAT'} {suffix}",
            "trattiene_provvigioni": trattiene,
            "attiva": True,
        }
        r = admin.post(f"{API}/compagnie", json=body)
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]
        self.cleanup["compagnie"].append(cid)
        return cid

    def _create_polizza(self, admin, anag_id, comp_id, suffix):
        body = {
            "numero_polizza": f"TST-IT4-{suffix}-{uuid.uuid4().hex[:6]}",
            "contraente_id": anag_id,
            "compagnia_id": comp_id,
            "ramo": "RCA",
            "effetto": TEST_DAY,
            "scadenza": "2026-12-31",
            "data_decorrenza": TEST_DAY,
            "data_scadenza": "2026-12-31",
            "premio_lordo": 100.0,
            "frazionamento": "annuale",
            "stato": "attiva",
        }
        r = admin.post(f"{API}/polizze", json=body)
        assert r.status_code in (200, 201), f"polizza create: {r.status_code} {r.text}"
        pid = r.json()["id"]
        self.cleanup["polizze"].append(pid)
        return pid

    def _create_movimento(self, admin, polizza_id, compagnia_id, importo, provv):
        body = {
            "data_movimento": TEST_DAY,
            "tipo": "entrata",
            "categoria": "incasso_premio",
            "importo": importo,
            "descrizione": "TEST Iter4 incasso premio",
            "polizza_id": polizza_id,
            "compagnia_id": compagnia_id,
            "provvigioni": provv,
            "quota_provvigione": provv,
        }
        r = admin.post(f"{API}/contabilita/movimenti", json=body)
        assert r.status_code in (200, 201), r.text
        mid = r.json()["id"]
        self.cleanup["movimenti"].append(mid)
        return mid

    def test_saldo_trattiene_true_positive_and_false_negative(self, admin):
        # ---- Setup ----
        anag_id = self._create_anagrafica(admin, "A")
        comp_trat = self._create_compagnia(admin, trattiene=True, suffix="T")
        comp_notrat = self._create_compagnia(admin, trattiene=False, suffix="N")
        pol_trat = self._create_polizza(admin, anag_id, comp_trat, "T")
        pol_notrat = self._create_polizza(admin, anag_id, comp_notrat, "N")

        m_trat = self._create_movimento(admin, pol_trat, comp_trat, importo=100.0, provv=10.0)
        m_notrat = self._create_movimento(admin, pol_notrat, comp_notrat, importo=100.0, provv=10.0)

        # ---- Verify via brogliaccio ----
        r = admin.get(f"{API}/contabilita/brogliaccio", params={"data": TEST_DAY})
        assert r.status_code == 200, r.text
        payload = r.json()
        righe = {rg["id"]: rg for rg in payload.get("righe", [])}
        assert m_trat in righe, f"movimento trattiene=true not in righe: {list(righe.keys())}"
        assert m_notrat in righe, f"movimento trattiene=false not in righe: {list(righe.keys())}"

        r_trat = righe[m_trat]
        r_notrat = righe[m_notrat]

        # Case A: trattiene=true -> saldo = totale - provv = 100 - 10 = 90 (positive)
        assert r_trat["totale"] == pytest.approx(100.0)
        assert r_trat["provv"] == pytest.approx(10.0)
        assert r_trat["saldo"] == pytest.approx(90.0), f"trattiene=true expected 90, got {r_trat['saldo']}"
        assert r_trat["trattiene_provvigioni"] is True

        # Case B: trattiene=false -> saldo = -provv = -10 (negative)
        assert r_notrat["totale"] == pytest.approx(100.0)
        assert r_notrat["provv"] == pytest.approx(10.0)
        assert r_notrat["saldo"] == pytest.approx(-10.0), f"trattiene=false expected -10, got {r_notrat['saldo']}"
        assert r_notrat["trattiene_provvigioni"] is False

        # ---- Totali_giornata must still include sconti/rimesse keys ----
        tg = payload.get("totali_giornata", {})
        assert "sconti" in tg, f"totali_giornata missing 'sconti': {tg}"
        assert "rimesse" in tg, f"totali_giornata missing 'rimesse': {tg}"

        # KPI must still include sconti/rimesse
        kpi = payload.get("riepilogo_kpi", {})
        assert "sconti" in kpi
        assert "rimesse" in kpi


# ===== 3) PDF stampa - no Sconti/Rimesse in main table =====
class TestPdfNoSontiRimesse:
    def test_pdf_returns_bytes(self, admin):
        r = admin.get(f"{API}/contabilita/brogliaccio/stampa", params={"data": TEST_DAY})
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "pdf" in ct.lower(), f"expected pdf, got {ct}"
        assert len(r.content) > 1000, "pdf too small"
        # Try to extract text and verify columns
        try:
            import pdfplumber
        except ImportError:
            pytest.skip("pdfplumber not installed - skipping PDF text scan")
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            page1_text = pdf.pages[0].extract_text() or ""
        # On page1 (main table) Sconti/Rimesse columns must NOT appear as column headers
        for line in page1_text.splitlines():
            if "Provv" in line and "Saldo" in line and "Totale" in line:
                assert "Sconti" not in line, f"Header line still contains Sconti: {line}"
                assert "Rimesse" not in line, f"Header line still contains Rimesse: {line}"
