# Iter 111: Agenzie partner - dati mandato, documenti (card) e config visibilità 5 entità
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    if r.status_code != 200:
        pytest.skip("login failed")
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return sess


def _body_from_cfg(cfg):
    body = {}
    for ent, row in cfg.items():
        body[ent] = {**{c["key"]: c["visibile_cliente"] for c in row},
                     "_ordine": [c["key"] for c in row],
                     "_meta": {c["key"]: {"icon": c["icon"], "obbligatoria": c["obbligatoria"]} for c in row}}
    return body


@pytest.fixture(scope="module")
def cfg_snapshot(s):
    snap = s.get(f"{API}/config/card-visibilita").json()
    yield snap
    # restore config
    s.put(f"{API}/config/card-visibilita", json=_body_from_cfg(snap))


@pytest.fixture(scope="module")
def agenzia(s):
    payload = {"ragione_sociale": "TEST_Agenzia Mandato", "tipo": "partner",
               "tipo_rapporto": "lettera_incarico", "autorizzato_incasso": "si",
               "denominazione_sociale": "TEST Denominazione SRL", "rui_ivass": "A000123456",
               "email": "test_age@example.com"}
    r = s.post(f"{API}/agenzie", json=payload)
    assert r.status_code == 201, r.text
    a = r.json()
    yield a
    s.delete(f"{API}/agenzie/{a['id']}")


# ---- Config card visibilità ----
class TestCardConfig:
    def test_five_entities(self, s, cfg_snapshot):
        cfg = s.get(f"{API}/config/card-visibilita").json()
        for ent in ["anagrafica", "polizza", "sinistro", "collaboratore", "agenzia_partner"]:
            assert ent in cfg and len(cfg[ent]) > 0
        labels_ag = [c["label"] for c in cfg["agenzia_partner"]]
        for l in ["Contratto di mandato", "Lettera di incarico", "Visura camerale",
                  "Iscrizione RUI/IVASS", "Documento IBAN", "Altro"]:
            assert l in labels_ag
        labels_co = [c["label"] for c in cfg["collaboratore"]]
        for l in ["Carta d'identità", "Codice fiscale", "Casellario giudiziale", "Altro"]:
            assert l in labels_co

    @pytest.mark.parametrize("ent", ["agenzia_partner", "collaboratore"])
    def test_custom_card_create_delete(self, s, cfg_snapshot, ent):
        r = s.post(f"{API}/config/card-custom", json={"entita": ent, "label": "TEST Custom Doc", "icon": "🧪"})
        assert r.status_code == 201, r.text
        key = r.json()["card"]["key"]
        assert key.startswith("custom_test_custom_doc")
        cfg = s.get(f"{API}/config/card-visibilita").json()
        found = [c for c in cfg[ent] if c["key"] == key]
        assert found and found[0]["custom"] is True and found[0]["label"] == "TEST Custom Doc"
        # other entity untouched
        other = "collaboratore" if ent == "agenzia_partner" else "agenzia_partner"
        assert not any(c["key"] == key for c in cfg[other])
        d = s.delete(f"{API}/config/card-custom/{ent}/{key}")
        assert d.status_code == 200
        cfg = s.get(f"{API}/config/card-visibilita").json()
        assert not any(c["key"] == key for c in cfg[ent])

    def test_invalid_entity(self, s):
        r = s.post(f"{API}/config/card-custom", json={"entita": "foo", "label": "x"})
        assert r.status_code == 400

    def test_put_meta_and_order_persist(self, s, cfg_snapshot):
        cfg = s.get(f"{API}/config/card-visibilita").json()
        body = _body_from_cfg(cfg)
        ag = cfg["agenzia_partner"]
        new_order = [c["key"] for c in reversed(ag)]
        body["agenzia_partner"]["_ordine"] = new_order
        body["agenzia_partner"]["_meta"]["Visura camerale"] = {"icon": "🧪", "obbligatoria": True}
        co = cfg["collaboratore"]
        body["collaboratore"]["_meta"]["Codice fiscale"] = {"icon": "🔬", "obbligatoria": True}
        r = s.put(f"{API}/config/card-visibilita", json=body)
        assert r.status_code == 200, r.text
        cfg2 = s.get(f"{API}/config/card-visibilita").json()
        assert [c["key"] for c in cfg2["agenzia_partner"]] == new_order
        vc = [c for c in cfg2["agenzia_partner"] if c["key"] == "Visura camerale"][0]
        assert vc["icon"] == "🧪" and vc["obbligatoria"] is True
        cf = [c for c in cfg2["collaboratore"] if c["key"] == "Codice fiscale"][0]
        assert cf["icon"] == "🔬" and cf["obbligatoria"] is True
        # other entities preserved
        assert [c["key"] for c in cfg2["anagrafica"]] == [c["key"] for c in cfg["anagrafica"]]


# ---- Agenzia: dati mandato + documenti ----
class TestAgenziaMandatoDocumenti:
    def test_mandato_fields_persist(self, s, agenzia):
        g = s.get(f"{API}/agenzie/{agenzia['id']}").json()
        assert g["tipo_rapporto"] == "lettera_incarico"
        assert g["autorizzato_incasso"] == "si"
        assert g["denominazione_sociale"] == "TEST Denominazione SRL"
        assert g["rui_ivass"] == "A000123456"

    def test_upload_multiple_same_tipologia_and_put_preserves(self, s, agenzia):
        aid = agenzia["id"]
        ids = []
        for i in range(2):
            r = s.post(f"{API}/agenzie/{aid}/documenti",
                       files={"file": (f"test{i}.pdf", b"%PDF-1.4 test content", "application/pdf")},
                       data={"tipologia": "Visura camerale", "descrizione": f"TEST desc {i}",
                             "data_rilascio": "2025-01-01", "data_scadenza": "2026-02-10"})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["tipologia"] == "Visura camerale" and d["data_scadenza"] == "2026-02-10"
            assert d["url"] and d["nome_file"] == f"test{i}.pdf"
            ids.append(d["id"])
        g = s.get(f"{API}/agenzie/{aid}").json()
        docs = [x for x in g.get("documenti", []) if x["id"] in ids]
        assert len(docs) == 2
        # file downloadable
        f = s.get(f"{BASE_URL}{docs[0]['url']}")
        assert f.status_code == 200
        # PUT update must not wipe documenti
        upd = {"ragione_sociale": "TEST_Agenzia Mandato UPD", "tipo": "partner",
               "tipo_rapporto": "mandato_diretto", "autorizzato_incasso": "no",
               "denominazione_sociale": "TEST Den 2", "rui_ivass": "B999"}
        u = s.put(f"{API}/agenzie/{aid}", json=upd)
        assert u.status_code == 200, u.text
        g = s.get(f"{API}/agenzie/{aid}").json()
        assert g["ragione_sociale"] == "TEST_Agenzia Mandato UPD"
        assert g["tipo_rapporto"] == "mandato_diretto" and g["autorizzato_incasso"] == "no"
        assert len([x for x in g.get("documenti", []) if x["id"] in ids]) == 2
        # list endpoint also exposes documenti
        lst = s.get(f"{API}/agenzie").json()
        me = [a for a in lst if a["id"] == aid][0]
        assert len(me.get("documenti", [])) == 2
        # delete one
        d = s.delete(f"{API}/agenzie/{aid}/documenti/{ids[0]}")
        assert d.status_code == 200
        g = s.get(f"{API}/agenzie/{aid}").json()
        rem = [x["id"] for x in g.get("documenti", [])]
        assert ids[0] not in rem and ids[1] in rem

    def test_upload_404_unknown_agency(self, s):
        r = s.post(f"{API}/agenzie/nonexistent-xyz/documenti", data={"tipologia": "Altro"})
        assert r.status_code == 404

    def test_upload_requires_admin(self):
        r = requests.post(f"{API}/auth/login", json={"email": "collaboratore@assicura.it", "password": "Collab123!"})
        if r.status_code != 200:
            pytest.skip("collab login failed")
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        x = requests.post(f"{API}/agenzie/whatever/documenti", data={"tipologia": "Altro"}, headers=h)
        assert x.status_code in (401, 403)
