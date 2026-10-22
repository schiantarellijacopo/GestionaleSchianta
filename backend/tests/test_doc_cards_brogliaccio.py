# Iteration 117: DocCardsScadenza document endpoints (compagnie / agenzie / azienda / collaboratori) + Brogliaccio REDION/CONAP
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        ss.headers["Authorization"] = f"Bearer {tok}"
    return ss


def _comp(s, cid):
    comps = s.get(f"{BASE_URL}/api/compagnie").json()
    comps = comps if isinstance(comps, list) else comps.get("items", [])
    return next(c for c in comps if c["id"] == cid)


def _upload(s, url, tip="Altro", scad="2026-12-31"):
    return s.post(url, files={"file": ("TEST_doc.pdf", PDF, "application/pdf")},
                  data={"tipologia": tip, "descrizione": "TEST_descr", "data_rilascio": "2026-01-01", "data_scadenza": scad})


# --- Brogliaccio REDION / CONAP ---
class TestBrogliaccio:
    def test_redion_linked_conap_today(self, s):
        r = s.get(f"{BASE_URL}/api/contabilita/brogliaccio")
        assert r.status_code == 200
        saldi = r.json()["saldi_compagnie"]
        red = [x for x in saldi if "REDION" in (x["compagnia"] or "").upper()]
        if not red:
            pytest.skip("REDION not present in preview DB (data-dependent)")
        print("REDION:", {k: red[0].get(k) for k in ("tipo_mandato", "agenzia_partner_nome", "agenzia_partner_id")})
        assert red[0]["tipo_mandato"] == "collaborazione"
        assert "CONAP" in (red[0]["agenzia_partner_nome"] or "").upper()

    def test_direct_companies_no_partner(self, s):
        saldi = s.get(f"{BASE_URL}/api/contabilita/brogliaccio").json()["saldi_compagnie"]
        for nm in ("CATTOLICA", "UCA"):
            m = [x for x in saldi if (x["compagnia"] or "").upper().startswith(nm)]
            for x in m:
                print(nm, x["compagnia"], x["tipo_mandato"], x["agenzia_partner_nome"])
            assert m, f"{nm} missing"
            assert all(x["agenzia_partner_nome"] is None and x["tipo_mandato"] == "diretto" for x in m)


# --- Compagnie documenti ---
class TestCompagnieDocs:
    def test_upload_get_delete(self, s):
        comps = s.get(f"{BASE_URL}/api/compagnie").json()
        comps = comps if isinstance(comps, list) else comps.get("items", [])
        cid = comps[0]["id"]
        r = _upload(s, f"{BASE_URL}/api/compagnie/{cid}/documenti", "Circolari")
        assert r.status_code == 200, r.text
        it = r.json()
        assert it["tipologia"] == "Circolari" and it["data_scadenza"] == "2026-12-31" and it["url"]
        # avviso
        a = s.put(f"{BASE_URL}/api/documenti/avviso", json={"entita": "compagnia", "entita_id": cid, "item_id": it["id"], "attivo": True, "giorni": 20})
        assert a.status_code == 200, a.text
        g = _comp(s, cid)
        d = [x for x in g.get("documenti", []) if x["id"] == it["id"]]
        assert d and d[0]["avviso_attivo"] is True and d[0]["avviso_giorni"] == 20
        # file served
        f = s.get(f"{BASE_URL}{it['url']}")
        assert f.status_code == 200
        dr = s.delete(f"{BASE_URL}/api/compagnie/{cid}/documenti/{it['id']}")
        assert dr.status_code == 200
        g = _comp(s, cid)
        assert not [x for x in g.get("documenti", []) if x["id"] == it["id"]]
        assert s.delete(f"{BASE_URL}/api/compagnie/{cid}/documenti/{it['id']}").status_code == 404

    def test_empty_file_rejected(self, s):
        comps = s.get(f"{BASE_URL}/api/compagnie").json()
        comps = comps if isinstance(comps, list) else comps.get("items", [])
        r = s.post(f"{BASE_URL}/api/compagnie/{comps[0]['id']}/documenti", files={"file": ("e.pdf", b"", "application/pdf")})
        assert r.status_code == 400

    def test_unknown_compagnia_404(self, s):
        assert _upload(s, f"{BASE_URL}/api/compagnie/nonexist/documenti").status_code == 404


# --- Agenzie partner documenti ---
class TestAgenzieDocs:
    def test_upload_get_delete(self, s):
        ags = s.get(f"{BASE_URL}/api/agenzie").json()
        ags = ags if isinstance(ags, list) else ags.get("items", [])
        aid = ags[0]["id"]
        r = _upload(s, f"{BASE_URL}/api/agenzie/{aid}/documenti", "Visura camerale")
        assert r.status_code == 200, r.text
        it = r.json()
        assert it["tipologia"] == "Visura camerale" and it["data_scadenza"] == "2026-12-31"
        a = s.put(f"{BASE_URL}/api/documenti/avviso", json={"entita": "agenzia_partner", "entita_id": aid, "item_id": it["id"], "attivo": True, "giorni": 10})
        assert a.status_code == 200, a.text
        dr = s.delete(f"{BASE_URL}/api/agenzie/{aid}/documenti/{it['id']}")
        assert dr.status_code == 200
        ags2 = s.get(f"{BASE_URL}/api/agenzie").json()
        ags2 = ags2 if isinstance(ags2, list) else ags2.get("items", [])
        ag = next(x for x in ags2 if x["id"] == aid)
        assert not [x for x in (ag.get("documenti") or []) if x["id"] == it["id"]]


# --- Azienda documenti ---
class TestAziendaDocs:
    def test_upload_delete(self, s):
        r = _upload(s, f"{BASE_URL}/api/librerie/azienda/documenti", "Altro")
        assert r.status_code == 200, r.text
        it = r.json()
        assert it.get("data_scadenza") == "2026-12-31"
        dr = s.delete(f"{BASE_URL}/api/librerie/azienda/documenti/{it['id']}")
        assert dr.status_code == 200


# --- Collaboratore documenti ---
class TestCollabDocs:
    def test_upload_delete(self, s):
        users = s.get(f"{BASE_URL}/api/auth/users").json()
        users = users if isinstance(users, list) else users.get("items", [])
        u = next(x for x in users if x.get("email") == "collaboratore@assicura.it")
        uid = u["id"]
        r = _upload(s, f"{BASE_URL}/api/auth/users/{uid}/allegati/documenti", "Carta d'identità")
        assert r.status_code == 200, r.text
        it = r.json()
        assert it["data_scadenza"] == "2026-12-31" and it["url"]
        dr = s.delete(f"{BASE_URL}/api/auth/users/{uid}/allegati/documenti/{it['id']}")
        assert dr.status_code == 200
        users = s.get(f"{BASE_URL}/api/auth/users").json()
        users = users if isinstance(users, list) else users.get("items", [])
        u = next(x for x in users if x["id"] == uid)
        assert not [x for x in (u.get("documenti_collab") or []) if x["id"] == it["id"]]
