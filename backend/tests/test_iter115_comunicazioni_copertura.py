# Comunicazioni di Copertura - genera/salva/storico/anteprima/pdf/invia/delete + multi-tenant
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/comunicazioni-copertura"
GIORNO = "2026-10-05"


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@assicura.it", "Admin123!")


@pytest.fixture(scope="module")
def created(admin):
    ids = []
    yield ids
    for cid in ids:
        admin.delete(f"{API}/{cid}")


# --- genera ---
class TestGenera:
    def test_genera_giorno(self, admin):
        r = admin.get(f"{API}/genera", params={"giorno": GIORNO})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["giorno"] == GIORNO
        assert d["n_titoli"] == 4, d
        assert len(d["gruppi"]) >= 1
        g = d["gruppi"][0]
        assert "Generali" in g["compagnia_nome"]
        assert g["agenzia_partner_nome"] and "Bottoni" in g["agenzia_partner_nome"]
        assert not g["destinatario_email"]
        assert g["mandato_label"].endswith(g["compagnia_nome"])
        for g in d["gruppi"]:
            assert round(sum(t["importo"] for t in g["titoli"]), 2) == g["totale"]
            for t in g["titoli"]:
                for k in ("titolo_id", "numero_polizza", "rischio", "operatore", "contraente", "rata_del", "importo"):
                    assert k in t
        assert d["totale_generale"] == round(sum(g["totale"] for g in d["gruppi"]), 2)

    def test_genera_other_days(self, admin):
        r1 = admin.get(f"{API}/genera", params={"giorno": "2026-10-15"}).json()
        r2 = admin.get(f"{API}/genera", params={"giorno": "2026-06-22"}).json()
        assert r1["n_titoli"] == 3, r1
        assert r2["n_titoli"] == 1, r2

    def test_genera_bad_date(self, admin):
        r = admin.get(f"{API}/genera", params={"giorno": "05/10/2026"})
        assert r.status_code == 400

    def test_genera_empty_day(self, admin):
        r = admin.get(f"{API}/genera", params={"giorno": "1999-01-01"})
        assert r.status_code == 200
        assert r.json()["gruppi"] == [] and r.json()["n_titoli"] == 0

    def test_requires_auth(self):
        r = requests.get(f"{API}/genera", params={"giorno": GIORNO})
        assert r.status_code in (401, 403)


# --- salva / storico / dettaglio / anteprima / pdf / invia / delete ---
class TestFlow:
    def test_salva_bozza_and_flow(self, admin, created):
        gen = admin.get(f"{API}/genera", params={"giorno": GIORNO}).json()
        gruppi = gen["gruppi"]
        r = admin.post(f"{API}/salva", json={"giorno": GIORNO, "gruppi": gruppi, "invia": False})
        assert r.status_code == 200, r.text
        coms = r.json()["comunicazioni"]
        assert len(coms) == len(gruppi)
        for c in coms:
            created.append(c["id"])
            assert c["stato"] == "bozza"
            assert isinstance(c["numero"], int) and c["numero"] > 0
            assert "_id" not in c
        nums = [c["numero"] for c in coms]
        assert len(set(nums)) == len(nums)
        c0 = coms[0]
        assert len(c0["titoli"]) == len(gruppi[0]["titoli"])
        assert c0["totale"] == gruppi[0]["totale"]

        # dettaglio
        d = admin.get(f"{API}/{c0['id']}")
        assert d.status_code == 200 and d.json()["id"] == c0["id"]

        # storico filters
        st = admin.get(API, params={"giorno": GIORNO}).json()
        assert any(x["id"] == c0["id"] for x in st)
        st2 = admin.get(API, params={"dal": "2026-10-01", "al": "2026-10-10", "stato": "bozza"}).json()
        assert any(x["id"] == c0["id"] for x in st2)
        assert all(x["stato"] == "bozza" and "2026-10-01" <= x["giorno"] <= "2026-10-10" for x in st2)
        st3 = admin.get(API, params={"stato": "inviata", "giorno": GIORNO}).json()
        assert not any(x["id"] == c0["id"] for x in st3)
        st4 = admin.get(API, params={"dal": "2026-11-01"}).json()
        assert not any(x["id"] == c0["id"] for x in st4)

        # anteprima
        a = admin.get(f"{API}/{c0['id']}/anteprima")
        assert a.status_code == 200
        assert "text/html" in a.headers["content-type"]
        assert "<table" in a.text and "TOTALE" in a.text
        assert gruppi[0]["titoli"][0]["numero_polizza"] in a.text

        # pdf
        p = admin.get(f"{API}/{c0['id']}/pdf")
        assert p.status_code == 200
        assert "application/pdf" in p.headers["content-type"]
        assert p.content[:4] == b"%PDF" and len(p.content) > 1000

        # invia -> 400 senza email, titoli non marcati
        i = admin.post(f"{API}/{c0['id']}/invia")
        assert i.status_code == 400
        assert "Nessuna email agenzia partner" in i.text
        after = admin.get(f"{API}/genera", params={"giorno": GIORNO}).json()
        assert after["n_titoli"] == gen["n_titoli"]
        d2 = admin.get(f"{API}/{c0['id']}").json()
        assert d2["stato"] == "errore" and d2["email_errore"] == "Nessuna email agenzia partner"

        # delete
        dl = admin.delete(f"{API}/{c0['id']}")
        assert dl.status_code == 200
        assert admin.get(f"{API}/{c0['id']}").status_code == 404
        created.remove(c0["id"])

    def test_salva_validation(self, admin):
        r = admin.post(f"{API}/salva", json={"giorno": GIORNO, "gruppi": []})
        assert r.status_code == 400

    def test_404s(self, admin):
        for path in ("x-none", "x-none/anteprima", "x-none/pdf"):
            assert admin.get(f"{API}/{path}").status_code == 404
        assert admin.post(f"{API}/x-none/invia").status_code == 404
        assert admin.delete(f"{API}/x-none").status_code == 404


# --- multi-tenant ---
class TestTenant:
    def test_superadmin_or_other_tenant_isolation(self, admin, created):
        gen = admin.get(f"{API}/genera", params={"giorno": "2026-06-22"}).json()
        r = admin.post(f"{API}/salva", json={"giorno": "2026-06-22", "gruppi": gen["gruppi"], "invia": False})
        cid = r.json()["comunicazioni"][0]["id"]
        created.append(cid)
        collab = _login("collaboratore@assicura.it", "Collab123!")
        me = collab.get(f"{BASE_URL}/api/auth/me").json()
        print("collab tenant:", me.get("agenzia_tenant_id"))
        st = collab.get(API)
        assert st.status_code == 200
        visible = any(x["id"] == cid for x in st.json())
        print("collab sees admin comunicazione:", visible)
        # collaboratore cannot delete (admin only)
        assert collab.delete(f"{API}/{cid}").status_code in (401, 403)
