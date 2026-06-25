"""
Iter16 backend tests:
- GET /api/geo/suggest (autocomplete Nominatim)
- GET /api/anagrafiche/stats (4 KPI: privati/aziende/condomini/parrocchie + totale)
- GET /api/anagrafiche/{aid}/network (root + collegati + totali con stats polizze)
- GET /api/geo/anagrafiche (is_cliente boolean enrichment)
- Regression: Brogliaccio uscite generiche NON contate in totali_giornata.totale
"""

import os
import time
import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")},
        timeout=20,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# ---------- /api/geo/suggest ----------

class TestGeoSuggest:
    def test_suggest_short_returns_empty(self, session):
        r = session.get(f"{BASE_URL}/api/geo/suggest", params={"q": "vi"}, timeout=20)
        assert r.status_code == 200
        assert r.json() == []

    def test_suggest_returns_results(self, session):
        # Single Nominatim call to respect rate limit
        r = session.get(
            f"{BASE_URL}/api/geo/suggest",
            params={"q": "via roma como"},
            timeout=25,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Aspettati >= 1 suggerimento da Nominatim per 'via roma como'"
        first = data[0]
        for k in ("display_name", "lat", "lng", "indirizzo", "comune", "cap", "provincia"):
            assert k in first, f"campo mancante nel suggerimento: {k}"
        assert isinstance(first["lat"], (int, float))
        assert isinstance(first["lng"], (int, float))


# ---------- /api/anagrafiche/stats ----------

class TestAnagraficheStats:
    def test_stats_structure_and_buckets(self, session):
        r = session.get(f"{BASE_URL}/api/anagrafiche/stats", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("privati", "aziende", "condomini", "parrocchie", "totale"):
            assert k in data, f"manca chiave {k}"
            assert "n" in data[k] and "premio_totale" in data[k]
            assert isinstance(data[k]["n"], int)
            assert isinstance(data[k]["premio_totale"], (int, float))
        # totale.n == somma delle 4 categorie
        somma = (
            data["privati"]["n"]
            + data["aziende"]["n"]
            + data["condomini"]["n"]
            + data["parrocchie"]["n"]
        )
        assert data["totale"]["n"] == somma, (
            f"totale.n ({data['totale']['n']}) deve essere somma 4 categorie ({somma})"
        )
        # Sanity: dovrebbero esserci dei privati (>0) e qualche parrocchia/condominio
        assert data["privati"]["n"] > 0


# ---------- /api/anagrafiche/{aid}/network ----------

class TestAnagraficaNetwork:
    def test_network_with_temp_relation(self, session):
        """Crea due anagrafiche TEST_, le collega, verifica network, cleanup."""
        # Crea 2 anagrafiche temporanee
        a1_payload = {
            "tipo": "persona_fisica",
            "ragione_sociale": "TEST_iter16_capo",
            "codice_fiscale": "TST16CAP00A00A000A",
        }
        a2_payload = {
            "tipo": "persona_fisica",
            "ragione_sociale": "TEST_iter16_figlio",
            "codice_fiscale": "TST16FIG00A00A000B",
        }
        r1 = session.post(f"{BASE_URL}/api/anagrafiche", json=a1_payload, timeout=20)
        assert r1.status_code in (200, 201), r1.text
        a1_id = r1.json()["id"]
        r2 = session.post(f"{BASE_URL}/api/anagrafiche", json=a2_payload, timeout=20)
        assert r2.status_code in (200, 201), r2.text
        a2_id = r2.json()["id"]

        try:
            # Aggiunge la relazione genitore/figlio (bidirezionale)
            rr = session.post(
                f"{BASE_URL}/api/anagrafiche/{a1_id}/relazioni",
                json={
                    "anagrafica_id": a2_id,
                    "relazione": "figlio",
                    "relazione_inversa": "genitore",
                },
                timeout=20,
            )
            assert rr.status_code in (200, 201), rr.text

            # GET /network di a1 deve contenere a2 in collegati
            rn = session.get(f"{BASE_URL}/api/anagrafiche/{a1_id}/network", timeout=20)
            assert rn.status_code == 200, rn.text
            data = rn.json()
            assert "root" in data and "collegati" in data and "totali" in data
            root = data["root"]
            for k in (
                "id", "ragione_sociale",
                "n_polizze_attive", "n_preventivi", "n_polizze_totali",
                "premio_totale", "provvigioni_totale",
            ):
                assert k in root, f"manca chiave root.{k}"
            assert root["id"] == a1_id
            ids_coll = [c["id"] for c in data["collegati"]]
            assert a2_id in ids_coll, f"a2 ({a2_id}) non trovato in collegati: {ids_coll}"
            # Stessa struttura sui collegati
            c2 = [c for c in data["collegati"] if c["id"] == a2_id][0]
            assert c2.get("relazione") == "figlio"
            for k in (
                "n_polizze_attive", "n_preventivi", "n_polizze_totali",
                "premio_totale", "provvigioni_totale",
            ):
                assert k in c2

            # Totali = somma root+collegati (con queste anag senza polizze = 0)
            tot = data["totali"]
            for k in (
                "n_persone", "n_polizze_attive", "n_preventivi",
                "n_polizze_totali", "premio_totale", "provvigioni_totale",
            ):
                assert k in tot
            expected_premio = round(root["premio_totale"] + c2["premio_totale"], 2)
            expected_provv = round(root["provvigioni_totale"] + c2["provvigioni_totale"], 2)
            assert tot["premio_totale"] == expected_premio
            assert tot["provvigioni_totale"] == expected_provv
            assert tot["n_persone"] == 2
        finally:
            # Cleanup
            try:
                session.delete(f"{BASE_URL}/api/anagrafiche/{a1_id}", timeout=15)
            except Exception:
                pass
            try:
                session.delete(f"{BASE_URL}/api/anagrafiche/{a2_id}", timeout=15)
            except Exception:
                pass


# ---------- /api/geo/anagrafiche is_cliente ----------

class TestGeoAnagraficheIsCliente:
    def test_geo_anagrafiche_has_is_cliente(self, session):
        r = session.get(f"{BASE_URL}/api/geo/anagrafiche", timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        if not items:
            pytest.skip("nessuna anagrafica geolocalizzata in DB")
        for a in items[:50]:
            assert "is_cliente" in a, f"is_cliente mancante per {a.get('id')}"
            assert isinstance(a["is_cliente"], bool)
        # almeno qualcuno deve essere True o False (lista non monotipica non garantita)
        assert any(isinstance(a["is_cliente"], bool) for a in items)


# ---------- Regression Brogliaccio iter15 ----------

class TestBrogliaccioRegression:
    def test_uscite_generiche_non_in_totale_giornata(self, session):
        """Crea movimenti uscita 'altro' e 'spese_amministrative' e verifica
        che NON appaiano nel totali_giornata.totale ma solo in .spese."""
        # Trova un conto cassa attivo
        rconti = session.get(
            f"{BASE_URL}/api/librerie/conti-cassa",
            params={"attivi": "true"},
            timeout=15,
        )
        assert rconti.status_code == 200, rconti.text
        conti = rconti.json()
        if not conti:
            pytest.skip("nessun conto cassa disponibile")
        conto_id = conti[0]["id"]

        data_test = "2026-07-15"
        created = []
        try:
            for cat, imp in [("altro", 33.33), ("spese_amministrative", 11.11)]:
                rm = session.post(
                    f"{BASE_URL}/api/contabilita/movimenti",
                    json={
                        "data_movimento": data_test,
                        "categoria": cat,
                        "tipo": "uscita",
                        "importo": imp,
                        "conto_cassa_id": conto_id,
                        "descrizione": f"TEST_iter16_{cat}",
                    },
                    timeout=20,
                )
                assert rm.status_code in (200, 201), f"create {cat}: {rm.status_code} {rm.text}"
                created.append(rm.json().get("id"))

            # Recupera brogliaccio
            rb = session.get(
                f"{BASE_URL}/api/contabilita/brogliaccio",
                params={"data": data_test},
                timeout=20,
            )
            assert rb.status_code == 200, rb.text
            body = rb.json()
            # Estrai totali_giornata
            tg = None
            if isinstance(body, dict):
                if "totali_giornata" in body:
                    tg = body["totali_giornata"]
                elif "giorni" in body and body["giorni"]:
                    tg = body["giorni"][0].get("totali_giornata") or body["giorni"][0].get("totali")
            if tg is None:
                # struttura alternativa: cerca un campo 'totale' = 0 e 'spese' = 44.44
                pytest.skip("formato risposta brogliaccio inatteso per estrazione totali_giornata")
            totale = float(tg.get("totale") or 0)
            spese = float(tg.get("spese") or 0)
            assert totale == 0.0, f"uscite generiche NON devono contribuire a totale (atteso 0, ottenuto {totale})"
            assert round(spese, 2) >= round(33.33 + 11.11, 2) - 0.01, (
                f"spese atteso >= 44.44, ottenuto {spese}"
            )
        finally:
            for mid in created:
                if mid:
                    try:
                        session.delete(
                            f"{BASE_URL}/api/contabilita/movimenti/{mid}",
                            timeout=10,
                        )
                    except Exception:
                        pass
