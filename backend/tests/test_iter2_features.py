"""Tests for iteration 2 new features:
- Voci manuali collaboratori (estratto conto)
- Relazioni familiari attributi (lavoratore/a_carico/handicap)
- Polizze filters + exports (CSV/XLSX/PDF)
"""
import os
import io
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip())
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin": (os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")),
    "collaboratore": (os.environ.get("TEST_COLLAB_EMAIL", "collaboratore@assicura.it"), os.environ.get("TEST_COLLAB_PASSWORD", "Collab123!")),
    "dipendente": (os.environ.get("TEST_DIP_EMAIL", "dipendente@assicura.it"), os.environ.get("TEST_DIP_PASSWORD", "Dipendente123!")),
}


def login(role):
    email, pw = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"Login {role}: {r.status_code} {r.text}"
    j = r.json()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {j['access_token']}", "Content-Type": "application/json"})
    # also keep cookies set by server
    s.cookies.update(r.cookies)
    return s, j["user"]


@pytest.fixture(scope="module")
def admin_session():
    s, u = login("admin")
    return s


@pytest.fixture(scope="module")
def collab_id(admin_session):
    """Get a collaboratore id (Sara is seeded)."""
    r = admin_session.get(f"{API}/collaboratori")
    assert r.status_code == 200, r.text
    users = r.json()
    assert isinstance(users, list) and len(users) > 0, "Nessun collaboratore trovato"
    return users[0]["id"]


# =============================================================
# VOCI MANUALI COLLABORATORI
# =============================================================
class TestVociManuali:

    def test_create_voce_bonus(self, admin_session, collab_id):
        r = admin_session.post(f"{API}/collaboratori/{collab_id}/voci-manuali", json={
            "data": "2026-01-15",
            "causale": "TEST_Bonus QA",
            "importo": 150.50,
            "note": "Bonus per obiettivo Q4",
        })
        assert r.status_code == 201, r.text
        j = r.json()
        assert j["causale"] == "TEST_Bonus QA"
        assert j["importo"] == 150.50
        assert j["collaboratore_id"] == collab_id
        assert j.get("pagata") is False
        assert "id" in j
        pytest.bonus_id = j["id"]

    def test_create_voce_trattenuta_negative(self, admin_session, collab_id):
        r = admin_session.post(f"{API}/collaboratori/{collab_id}/voci-manuali", json={
            "data": "2026-01-16",
            "causale": "TEST_Trattenuta QA",
            "importo": -50.0,
        })
        assert r.status_code == 201, r.text
        assert r.json()["importo"] == -50.0
        pytest.trattenuta_id = r.json()["id"]

    def test_create_voce_missing_causale(self, admin_session, collab_id):
        r = admin_session.post(f"{API}/collaboratori/{collab_id}/voci-manuali",
                               json={"importo": 10})
        assert r.status_code == 400

    def test_create_voce_missing_importo(self, admin_session, collab_id):
        r = admin_session.post(f"{API}/collaboratori/{collab_id}/voci-manuali",
                               json={"causale": "x"})
        assert r.status_code == 400

    def test_create_voce_collab_not_found(self, admin_session):
        r = admin_session.post(f"{API}/collaboratori/nope-xyz/voci-manuali",
                               json={"causale": "x", "importo": 1})
        assert r.status_code == 404

    def test_list_voci_manuali(self, admin_session, collab_id):
        r = admin_session.get(f"{API}/collaboratori/{collab_id}/voci-manuali")
        assert r.status_code == 200
        items = r.json()
        ids = [v["id"] for v in items]
        assert pytest.bonus_id in ids
        assert pytest.trattenuta_id in ids

    def test_list_voci_manuali_date_filter(self, admin_session, collab_id):
        r = admin_session.get(f"{API}/collaboratori/{collab_id}/voci-manuali",
                              params={"dal": "2026-01-16", "al": "2026-01-16"})
        assert r.status_code == 200
        items = r.json()
        for v in items:
            assert v["data"] == "2026-01-16"

    def test_estratto_provvigioni_includes_voci(self, admin_session, collab_id):
        r = admin_session.get(f"{API}/collaboratori/{collab_id}/estratto-provvigioni",
                              params={"dal": "2026-01-01", "al": "2026-12-31"})
        assert r.status_code == 200
        j = r.json()
        assert "voci_manuali" in j, f"Missing voci_manuali in {j.keys()}"
        ids = [v["id"] for v in j["voci_manuali"]]
        assert pytest.bonus_id in ids
        assert pytest.trattenuta_id in ids
        tot = j.get("totali", {})
        assert "voci_manuali_periodo" in tot
        assert "voci_manuali_da_pagare" in tot
        assert "netto_da_pagare" in tot
        # Sanity: voci_manuali_da_pagare >= 100.5 (150.5 - 50)
        assert abs(tot["voci_manuali_da_pagare"] - 100.50) < 0.01, \
            f"voci_manuali_da_pagare={tot['voci_manuali_da_pagare']}"

    def test_paga_provvigioni_only_voci(self, admin_session, collab_id):
        # Pay only the bonus voce (positive)
        r = admin_session.post(f"{API}/collaboratori/{collab_id}/paga-provvigioni", json={
            "titoli_ids": [],
            "voci_manuali_ids": [pytest.bonus_id],
            "data_pagamento": "2026-01-20",
            "mezzo_pagamento": "bonifico",
            "note": "TEST pagamento solo voce",
        })
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert "pagamento" in j
        assert "movimento" in j
        assert j["pagamento"]["voci_manuali_ids"] == [pytest.bonus_id]
        # netto should equal the bonus importo since no titoli
        assert abs(j["pagamento"]["netto_pagato"] - 150.50) < 0.01
        pytest.movimento_id = j["movimento"]["id"]

    def test_voce_marked_paid_after_payment(self, admin_session, collab_id):
        r = admin_session.get(f"{API}/collaboratori/{collab_id}/voci-manuali")
        items = r.json()
        bonus = next(v for v in items if v["id"] == pytest.bonus_id)
        assert bonus.get("pagata") is True
        assert bonus.get("pagamento_id")

    def test_cannot_delete_paid_voce(self, admin_session, collab_id):
        r = admin_session.delete(f"{API}/collaboratori/{collab_id}/voci-manuali/{pytest.bonus_id}")
        assert r.status_code == 400

    def test_paga_provvigioni_empty_body_400(self, admin_session, collab_id):
        r = admin_session.post(f"{API}/collaboratori/{collab_id}/paga-provvigioni",
                               json={"titoli_ids": [], "voci_manuali_ids": []})
        assert r.status_code == 400

    def test_delete_unpaid_voce(self, admin_session, collab_id):
        r = admin_session.delete(f"{API}/collaboratori/{collab_id}/voci-manuali/{pytest.trattenuta_id}")
        assert r.status_code == 200
        # verify not found
        r = admin_session.get(f"{API}/collaboratori/{collab_id}/voci-manuali")
        ids = [v["id"] for v in r.json()]
        assert pytest.trattenuta_id not in ids

    def test_delete_voce_not_found(self, admin_session, collab_id):
        r = admin_session.delete(f"{API}/collaboratori/{collab_id}/voci-manuali/nope-xyz")
        assert r.status_code == 404


# =============================================================
# RELAZIONI FAMILIARI - lavoratore / a_carico / handicap
# =============================================================
@pytest.fixture(scope="module")
def two_anagrafiche(admin_session):
    # Create marito + moglie + figlio
    r1 = admin_session.post(f"{API}/anagrafiche", json={
        "tipo": "persona_fisica",
        "ragione_sociale": "TEST_Marito QA",
        "nome": "Marito",
        "cognome": "QA",
    })
    assert r1.status_code in (200, 201), r1.text
    marito = r1.json()["id"]
    r2 = admin_session.post(f"{API}/anagrafiche", json={
        "tipo": "persona_fisica",
        "ragione_sociale": "TEST_Moglie QA",
        "nome": "Moglie", "cognome": "QA",
    })
    moglie = r2.json()["id"]
    r3 = admin_session.post(f"{API}/anagrafiche", json={
        "tipo": "persona_fisica",
        "ragione_sociale": "TEST_Figlio QA",
        "nome": "Figlio", "cognome": "QA",
    })
    figlio = r3.json()["id"]
    yield marito, moglie, figlio
    # cleanup
    for aid in (marito, moglie, figlio):
        admin_session.delete(f"{API}/anagrafiche/{aid}")


class TestRelazioni:

    def test_add_coniuge_with_lavoratore(self, admin_session, two_anagrafiche):
        marito, moglie, _ = two_anagrafiche
        r = admin_session.post(f"{API}/anagrafiche/{marito}/relazioni", json={
            "anagrafica_id": moglie,
            "relazione": "coniuge",
            "relazione_inversa": "coniuge",
            "lavoratore": True,
            "a_carico": False,
            "lavoratore_inverso": False,
            "a_carico_inverso": True,
        })
        assert r.status_code == 200, r.text

        # GET marito -> verify relazioni_risolte includes lavoratore=True
        r2 = admin_session.get(f"{API}/anagrafiche/{marito}")
        assert r2.status_code == 200
        rel = next((x for x in r2.json().get("relazioni_risolte", [])
                    if x.get("id") == moglie), None)
        assert rel is not None, f"relazione non risolta: {r2.json().get('relazioni_risolte')}"
        assert rel.get("lavoratore") is True
        assert rel.get("a_carico") is False

        # Inverse on moglie
        r3 = admin_session.get(f"{API}/anagrafiche/{moglie}")
        rel_inv = next((x for x in r3.json().get("relazioni_risolte", [])
                        if x.get("id") == marito), None)
        assert rel_inv is not None
        assert rel_inv.get("lavoratore") is False
        assert rel_inv.get("a_carico") is True

    def test_add_figlio_with_carico_handicap(self, admin_session, two_anagrafiche):
        marito, _, figlio = two_anagrafiche
        r = admin_session.post(f"{API}/anagrafiche/{marito}/relazioni", json={
            "anagrafica_id": figlio,
            "relazione": "figlio",
            "relazione_inversa": "padre",
            "a_carico": True,
            "handicap": True,
        })
        assert r.status_code == 200, r.text
        r2 = admin_session.get(f"{API}/anagrafiche/{marito}")
        rel = next((x for x in r2.json()["relazioni_risolte"]
                    if x.get("id") == figlio), None)
        assert rel is not None
        assert rel.get("a_carico") is True
        assert rel.get("handicap") is True

    def test_patch_relazione_update_attrs(self, admin_session, two_anagrafiche):
        marito, moglie, _ = two_anagrafiche
        r = admin_session.patch(f"{API}/anagrafiche/{marito}/relazioni/{moglie}", json={
            "lavoratore": False,
            "a_carico": True,
        })
        assert r.status_code == 200, r.text
        r2 = admin_session.get(f"{API}/anagrafiche/{marito}")
        rel = next(x for x in r2.json()["relazioni_risolte"]
                   if x["id"] == moglie)
        assert rel.get("lavoratore") is False
        assert rel.get("a_carico") is True

    def test_patch_relazione_not_found(self, admin_session, two_anagrafiche):
        marito, _, _ = two_anagrafiche
        r = admin_session.patch(f"{API}/anagrafiche/{marito}/relazioni/nope-xyz",
                                json={"lavoratore": True})
        assert r.status_code == 404


# =============================================================
# POLIZZE filters + exports
# =============================================================
class TestPolizze:
    def test_list_polizze_basic(self, admin_session):
        r = admin_session.get(f"{API}/polizze", params={"limit": 50})
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        if items:
            assert "collaboratore_nome" in items[0] or items[0].get("collaboratore_id") is None
            assert "compagnia_nome" in items[0]
            assert "contraente_nome" in items[0]

    def test_list_polizze_filter_stato(self, admin_session):
        r = admin_session.get(f"{API}/polizze", params={"stato": "attiva", "limit": 50})
        assert r.status_code == 200
        for p in r.json():
            assert p.get("stato") == "attiva"

    def test_list_polizze_in_scadenza(self, admin_session):
        r = admin_session.get(f"{API}/polizze", params={"in_scadenza_giorni": 60})
        assert r.status_code == 200

    def test_list_polizze_scadute_da_range(self, admin_session):
        r = admin_session.get(f"{API}/polizze",
                              params={"scadute_da_min": 1, "scadute_da_max": 365})
        assert r.status_code == 200

    def test_list_polizze_filter_compagnia_collab(self, admin_session):
        # get a compagnia & collaboratore
        comps = admin_session.get(f"{API}/compagnie").json()
        if comps:
            r = admin_session.get(f"{API}/polizze",
                                  params={"compagnia_id": comps[0]["id"], "limit": 10})
            assert r.status_code == 200
            for p in r.json():
                assert p.get("compagnia_id") == comps[0]["id"]

    def test_export_polizze_csv(self, admin_session):
        r = admin_session.get(f"{API}/export/polizze.csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        body = r.content.decode("utf-8-sig")
        assert "Numero polizza" in body
        assert "Collaboratore" in body
        # at least header + likely rows
        assert len(body.splitlines()) >= 1

    def test_export_polizze_csv_with_filter(self, admin_session):
        r = admin_session.get(f"{API}/export/polizze.csv",
                              params={"stato": "attiva"})
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    def test_export_polizze_xlsx(self, admin_session):
        r = admin_session.get(f"{API}/export/polizze.xlsx")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "spreadsheetml" in ct or "officedocument" in ct
        # XLSX is a zip - signature PK
        assert r.content[:2] == b"PK"

    def test_stampa_polizze_pdf(self, admin_session):
        r = admin_session.get(f"{API}/stampa/polizze")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "pdf" in ct.lower()
        assert r.content[:4] == b"%PDF"

    def test_stampa_polizze_pdf_with_filters(self, admin_session):
        r = admin_session.get(f"{API}/stampa/polizze",
                              params={"stato": "attiva", "in_scadenza_giorni": 90})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
