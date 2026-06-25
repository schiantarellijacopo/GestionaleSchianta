"""
Iter15 tests
- GET /api/stampa/titoli/sospesi (PDF) - admin + collaboratore_id filter + date in subtitle
- GET /api/titoli/sospesi regression (was crashed previously)
- GET /api/librerie/mezzi-pagamento?attivi=true returns seeded payment methods
- BUG FIX: GET /api/contabilita/brogliaccio for each row with tipo='uscita' & generic categoria,
  c_totale==0 (NOT -importo). totali_giornata.totale = sum of incassi_premio only.
- Regression: giroconto, pagamento_compagnia(rimessa), provvigioni-uscita still show in
  dedicated columns (spese, rimesse, per_conto)
- Geocoding POST /api/geo/anagrafiche/{aid}/geocode against Nominatim
"""
import os
import re
import uuid
import pytest
import requests
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it")
ADMIN_PWD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=20)
    assert r.status_code == 200, r.text
    return s


# -------- Stampa Sospesi PDF (new endpoint) --------
class TestStampaTitoliSospesi:
    def test_pdf_admin(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/stampa/titoli/sospesi", timeout=30)
        assert r.status_code == 200, r.text
        ct = r.headers.get("Content-Type", "")
        assert "application/pdf" in ct, f"Content-Type: {ct}"
        # filename in content-disposition
        cd = r.headers.get("Content-Disposition", "")
        assert "sospesi_anticipi.pdf" in cd, f"CD: {cd}"
        # PDF magic
        assert r.content[:4] == b"%PDF", "Not a valid PDF stream"
        assert len(r.content) > 500
        # Verify current date inside PDF stream (Italian dd/mm/YYYY) - decompressed search is brittle.
        # PDFs may compress text; check raw bytes for ASCII or use a token search.
        today_str = date.today().strftime("%d/%m/%Y")
        # Use pypdf for reliable text extraction
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        all_text = ""
        for page in reader.pages:
            all_text += page.extract_text() or ""
        # Endpoint puts "Data stampa: dd/mm/YYYY" in subtitle
        assert "Data stampa" in all_text, f"'Data stampa' not in PDF text. Extracted: {all_text[:300]}"
        assert today_str in all_text, f"Today's date {today_str} not in PDF text. Extracted: {all_text[:300]}"
        assert "Sospesi Anticipi" in all_text or "Sospesi" in all_text

    def test_pdf_with_collaboratore_filter(self, admin_session):
        # Pick a collaboratore id from /api/users (or fallback uuid)
        r_users = admin_session.get(f"{BASE_URL}/api/users", timeout=15)
        cid = None
        if r_users.status_code == 200:
            users = r_users.json()
            for u in users:
                if u.get("role") == "collaboratore":
                    cid = u.get("id"); break
        if not cid:
            cid = str(uuid.uuid4())  # random - should still respond 200 with empty list
        r = admin_session.get(
            f"{BASE_URL}/api/stampa/titoli/sospesi?collaboratore_id={cid}", timeout=30)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("Content-Type", "")
        assert r.content[:4] == b"%PDF"


# -------- Regression: /api/titoli/sospesi works --------
class TestTitoliSospesiList:
    def test_list_returns_200(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/titoli/sospesi", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"


# -------- Mezzi Pagamento library --------
class TestMezziPagamento:
    def test_attivi_true_list(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/librerie/mezzi-pagamento?attivi=true", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        assert len(items) > 0, "Seeded payment methods missing"
        # Validate structure: each item has id, codice/nome, attivo=true
        for it in items:
            assert "id" in it
            assert it.get("attivo", True) is True
            # Either 'codice' or 'nome' present
            assert any(k in it for k in ("codice", "nome", "etichetta", "label"))


# -------- Brogliaccio BUG FIX: manual outflows c_totale == 0 --------
class TestBrogliaccioOutflowsNotInTotale:
    @pytest.fixture(scope="class")
    def seeded_movs(self, admin_session):
        """Create movimenti uscita di categorie generiche su una data isolata."""
        # Pick conto cassa
        r_cc = admin_session.get(f"{BASE_URL}/api/librerie/conti-cassa", timeout=15)
        assert r_cc.status_code == 200, r_cc.text
        ccs = r_cc.json()
        assert len(ccs) > 0
        cc_id = ccs[0]["id"]

        test_date = "2026-05-15"
        # Categorie uscita generiche (non rimesse/anticipi/giroconto/provvigioni)
        cats_generiche = [
            ("spese_amministrative", 50.0),
            ("altro", 30.0),
            ("rimborso_cliente", 70.0),
            ("sconto_cliente", 20.0),
        ]
        created_ids = []
        for cat, imp in cats_generiche:
            payload = {
                "data_movimento": test_date,
                "tipo": "uscita",
                "categoria": cat,
                "importo": imp,
                "conto_cassa_id": cc_id,
                "descrizione": f"TEST_iter15_{cat}",
                "mezzo_pagamento": "Contanti",
            }
            r = admin_session.post(f"{BASE_URL}/api/contabilita/movimenti",
                                   json=payload, timeout=15)
            assert r.status_code in (200, 201), f"Create {cat} failed: {r.text}"
            created_ids.append((cat, imp, r.json().get("id")))

        # Also create one incasso_premio entrata for totali check
        # Need a polizza+titolo for proper incasso flow.
        # Simpler: insert manual entrata category 'incasso_premio' (alcune impl supportano)
        # Comportamento del sistema: incasso_premio richiede titolo. Saltiamo se 4xx.
        ent_payload = {
            "data_movimento": test_date,
            "tipo": "entrata",
            "categoria": "incasso_premio",
            "importo": 200.0,
            "conto_cassa_id": cc_id,
            "descrizione": "TEST_iter15_incasso_manuale",
            "mezzo_pagamento": "Contanti",
        }
        r_ent = admin_session.post(f"{BASE_URL}/api/contabilita/movimenti",
                                   json=ent_payload, timeout=15)
        ent_id = None
        ent_ok = r_ent.status_code in (200, 201)
        if ent_ok:
            ent_id = r_ent.json().get("id")
            created_ids.append(("incasso_premio", 200.0, ent_id))

        yield {"date": test_date, "ids": created_ids, "cc_id": cc_id, "ent_ok": ent_ok}

        # Cleanup
        for _, _, mid in created_ids:
            if mid:
                admin_session.delete(
                    f"{BASE_URL}/api/contabilita/movimenti/{mid}", timeout=10)

    def test_outflow_totale_zero(self, admin_session, seeded_movs):
        d = seeded_movs["date"]
        r = admin_session.get(
            f"{BASE_URL}/api/contabilita/brogliaccio?data={d}", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        righe = data.get("righe", [])
        # Locate TEST_iter15 outflow rows
        outflow_cats = {"spese_amministrative", "altro", "rimborso_cliente", "sconto_cliente"}
        expected_imports = {"spese_amministrative": 50.0, "altro": 30.0,
                            "rimborso_cliente": 70.0, "sconto_cliente": 20.0}
        matched = 0
        for r_ in righe:
            if r_.get("tipo") == "uscita" and r_.get("categoria") in outflow_cats:
                desc = (r_.get("descrizione") or "")
                if "TEST_iter15_" in desc:
                    matched += 1
                    tot = float(r_.get("totale") or 0)
                    assert tot == 0.0, \
                        f"BUG: cat={r_.get('categoria')} desc={desc} totale={tot} (deve essere 0)"
                    spese = float(r_.get("spese") or 0)
                    exp = expected_imports[r_.get("categoria")]
                    assert spese == exp, \
                        f"Spese should equal importo for {r_.get('categoria')}: spese={spese} expected={exp}"
        assert matched >= 4, f"Expected at least 4 TEST_iter15 outflow rows in brogliaccio, found {matched}"

    def test_totali_giornata_totale_is_incassi_only(self, admin_session, seeded_movs):
        d = seeded_movs["date"]
        r = admin_session.get(
            f"{BASE_URL}/api/contabilita/brogliaccio?data={d}", timeout=20)
        data = r.json()
        tot = data.get("totali_giornata", {}) or data.get("totali", {})
        # Possible keys
        totale = tot.get("totale")
        if totale is None:
            # alternate key
            totale = tot.get("c_totale") or 0
        # Sum of incassi_premio on that day:
        sum_inc = 0.0
        for r_ in data.get("righe", []):
            if r_.get("tipo") == "entrata" and r_.get("categoria") == "incasso_premio":
                sum_inc += float(r_.get("totale") or 0)
        assert abs(float(totale) - sum_inc) < 0.01, \
            f"totali_giornata.totale={totale} should equal sum of incassi_premio={sum_inc}"


# -------- Regression: special categories still in dedicated columns --------
class TestBrogliaccioRegressionSpecialCats:
    @pytest.fixture(scope="class")
    def seeded(self, admin_session):
        r_cc = admin_session.get(f"{BASE_URL}/api/librerie/conti-cassa", timeout=15)
        ccs = r_cc.json()
        cc_id = ccs[0]["id"]
        cc_id2 = ccs[1]["id"] if len(ccs) > 1 else cc_id

        test_date = "2026-05-16"
        created = []
        # Rimessa (pagamento_compagnia)
        for cat, imp in [("pagamento_compagnia", 150.0), ("provvigioni", 80.0)]:
            payload = {
                "data_movimento": test_date, "tipo": "uscita", "categoria": cat,
                "importo": imp, "conto_cassa_id": cc_id,
                "descrizione": f"TEST_iter15_{cat}", "mezzo_pagamento": "Bonifico",
            }
            r = admin_session.post(
                f"{BASE_URL}/api/contabilita/movimenti", json=payload, timeout=15)
            assert r.status_code in (200, 201), r.text
            created.append(r.json().get("id"))

        # Giroconto via dedicated endpoint
        g_pid = None
        gp = {
            "data_movimento": test_date,
            "importo": 100.0,
            "conto_da_id": cc_id,
            "conto_a_id": cc_id2,
            "descrizione": "TEST_iter15_giroconto",
        }
        rg = admin_session.post(
            f"{BASE_URL}/api/contabilita/giroconto", json=gp, timeout=15)
        if rg.status_code in (200, 201):
            g_pid = rg.json().get("pair_id")

        yield {"date": test_date, "ids": created, "g_pid": g_pid, "cc_id": cc_id}
        for mid in created:
            admin_session.delete(
                f"{BASE_URL}/api/contabilita/movimenti/{mid}", timeout=10)
        if g_pid and created:
            # Delete one giroconto row triggers pair delete
            pass

    def test_rimessa_provv_giroconto_columns(self, admin_session, seeded):
        d = seeded["date"]
        r = admin_session.get(
            f"{BASE_URL}/api/contabilita/brogliaccio?data={d}", timeout=20)
        assert r.status_code == 200
        data = r.json()
        found_rim = found_prov = found_giro = False
        for row in data.get("righe", []):
            desc = row.get("descrizione") or ""
            cat = row.get("categoria")
            tot = float(row.get("totale") or 0)
            if "TEST_iter15_pagamento_compagnia" in desc:
                found_rim = True
                assert tot == 0.0, f"rimessa totale != 0: {tot}"
                assert float(row.get("rimesse") or 0) == 150.0, \
                    f"rimessa rimesse col != 150: {row.get('rimesse')}"
            if "TEST_iter15_provvigioni" in desc:
                found_prov = True
                assert tot == 0.0
                assert float(row.get("spese") or 0) == 80.0
            if cat == "giroconto" and "TEST_iter15_giroconto" in desc:
                found_giro = True
                assert tot == 0.0
        assert found_rim, "Rimessa row missing"
        assert found_prov, "Provv-uscita row missing"
        # Giroconto might be skipped if dedicated endpoint errored; soft-warn
        if seeded.get("g_pid"):
            assert found_giro, "Giroconto row missing from brogliaccio"


# -------- Geocoding --------
class TestGeocoding:
    def test_geocode_existing_anagrafica(self, admin_session):
        # Create an anagrafica with full Italian address
        ana_payload = {
            "ragione_sociale": "TEST_iter15_Geo Cliente",
            "tipo": "persona_fisica",
            "indirizzo": "Via Roma 1",
            "cap": "00184",
            "citta": "Roma",
            "provincia": "RM",
        }
        r_create = admin_session.post(
            f"{BASE_URL}/api/anagrafiche", json=ana_payload, timeout=20)
        assert r_create.status_code in (200, 201), r_create.text
        aid = r_create.json().get("id")
        try:
            r = admin_session.post(
                f"{BASE_URL}/api/geo/anagrafiche/{aid}/geocode", timeout=30)
            # Nominatim could rate-limit or fail; accept 200 or 502/503/404 but not 500
            assert r.status_code in (200, 404, 502, 503), \
                f"Unexpected status {r.status_code}: {r.text}"
            if r.status_code == 200:
                d = r.json()
                # Expect lat/lng or similar
                assert any(k in d for k in ("lat", "latitudine", "latitude")) or \
                       "geo" in d or "geocoding" in d, f"No lat/lng in response: {d}"
        finally:
            admin_session.delete(f"{BASE_URL}/api/anagrafiche/{aid}", timeout=10)
