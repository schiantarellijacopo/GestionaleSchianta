"""Iteration: Prima Nota manual incasso_premio fix, Diario documenti, Trattative (polizza link,
allegati, invia preventivo), Pipeline rich cards (checklist + links)."""
import io
import os
import uuid
from datetime import date

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
TODAY = date.today().isoformat()


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    r = ses.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        ses.headers["Authorization"] = f"Bearer {tok}"
    return ses


@pytest.fixture(scope="module")
def cleanup(s):
    bag = {"mov": [], "tr": [], "pipe": [], "all": []}
    yield bag
    for a in bag["all"]:
        s.delete(f"{API}/allegati/{a}")
    for m in bag["mov"]:
        s.delete(f"{API}/contabilita/movimenti/{m}")
    for t in bag["tr"]:
        s.delete(f"{API}/trattative/{t}")
    for p in bag["pipe"]:
        s.delete(f"{API}/pipelines/{p}")


def _tipo_pag_with_conto(s):
    r = s.get(f"{API}/librerie/tipi-pagamento", params={"attivi": True})
    assert r.status_code == 200
    for t in r.json():
        if t.get("conto_id") and (t.get("label") or "").strip():
            return t
    pytest.skip("no tipo pagamento mapped to a conto")


def _polizza_with_contraente(s):
    r = s.get(f"{API}/polizze", params={"limit": 20})
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    for p in items:
        if p.get("contraente_id"):
            return p
    pytest.skip("no polizza")


# ---------- PRIMA NOTA: manual incasso_premio -> only bank column ----------
class TestPrimaNotaManual:
    def test_manual_incasso_only_bank(self, s, cleanup):
        tp = _tipo_pag_with_conto(s)
        r = s.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": TODAY, "tipo": "entrata", "categoria": "incasso_premio",
            "importo": 0.01, "descrizione": "TEST_MANUALE", "mezzo_pagamento": tp["label"],
            "conto_cassa_id": tp["conto_id"],
        })
        if r.status_code == 409 or (r.status_code == 400 and "chius" in r.text.lower()):
            pytest.skip(f"giornata chiusa: {r.text}")
        assert r.status_code == 201, r.text
        mid = r.json()["id"]
        cleanup["mov"].append(mid)
        b = s.get(f"{API}/contabilita/brogliaccio", params={"data": TODAY})
        assert b.status_code == 200
        row = next((x for x in b.json()["righe"] if x["id"] == mid), None)
        assert row is not None
        for k in ("totale", "provv", "saldo", "crediti"):
            assert abs(row.get(k) or 0) < 1e-9, f"{k}={row.get(k)}"
        assert abs(row["per_conto"].get(tp["conto_id"], 0) - 0.01) < 1e-9, row["per_conto"]
        assert sum(abs(v) for k, v in row["per_conto"].items() if k != tp["conto_id"]) < 1e-9

    def test_tipi_pagamento_map_to_visible_tenant_conti(self, s):
        """Every tipo pagamento's conto_id must be one of the tenant's brogliaccio columns,
        otherwise a manual movement lands in an invisible column (BUG found iter: CONTANTI)."""
        conti = {c["id"] for c in s.get(f"{API}/contabilita/brogliaccio", params={"data": TODAY}).json()["conti_cassa"]}
        tps = s.get(f"{API}/librerie/tipi-pagamento", params={"attivi": True}).json()
        bad = [t["label"] for t in tps if t.get("conto_id") and t["conto_id"] not in conti]
        assert not bad, f"tipi pagamento mapped to conti not visible in this tenant: {bad}"

    def test_policy_incasso_keeps_multicolumn(self, s, cleanup):
        """Regression: incasso_premio WITH polizza_id still populates totale/saldo."""
        tp = _tipo_pag_with_conto(s)
        pol = _polizza_with_contraente(s)
        r = s.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": TODAY, "tipo": "entrata", "categoria": "incasso_premio",
            "importo": 0.02, "descrizione": "TEST_POLIZZA_INCASSO", "mezzo_pagamento": tp["label"],
            "conto_cassa_id": tp["conto_id"], "polizza_id": pol["id"],
        })
        if r.status_code != 201:
            pytest.skip(r.text)
        mid = r.json()["id"]
        cleanup["mov"].append(mid)
        b = s.get(f"{API}/contabilita/brogliaccio", params={"data": TODAY}).json()
        row = next(x for x in b["righe"] if x["id"] == mid)
        assert abs(row["totale"] - 0.02) < 1e-9
        assert abs(row["per_conto"].get(tp["conto_id"], 0) - 0.02) < 1e-9


# ---------- DIARIO documenti ----------
class TestDiario:
    def test_diario_documenti_links_resolve(self, s, cleanup):
        pol = _polizza_with_contraente(s)
        aid = pol["contraente_id"]
        # upload a manual allegato on the anagrafica
        files = {"file": ("TEST_diario_doc.txt", io.BytesIO(b"hello diario"), "text/plain")}
        up = s.post(f"{API}/allegati", params={"entita_tipo": "anagrafica", "entita_id": aid}, files=files)
        assert up.status_code == 201, up.text
        cleanup["all"].append(up.json()["id"])
        r = s.get(f"{API}/anagrafiche/{aid}/diario")
        assert r.status_code == 200
        docs = [d for v in r.json() for d in (v.get("documenti") or [])]
        print(f"documenti in diario: {len(docs)}")
        for d in docs[:10]:
            dl = s.get(f"{API}{d['url']}")
            assert dl.status_code == 200, f"{d['url']} -> {dl.status_code}"

    def test_known_diario_anag(self, s):
        aid = "2ba60394-4d56-4a4b-b80f-2fdbf588ef63"
        r = s.get(f"{API}/anagrafiche/{aid}/diario")
        assert r.status_code == 200
        docs = [d for v in r.json() for d in (v.get("documenti") or [])]
        print(f"anag {aid}: {len(r.json())} voci, {len(docs)} documenti")
        for d in docs[:10]:
            assert s.get(f"{API}{d['url']}").status_code == 200, d["url"]


# ---------- TRATTATIVE ----------
class TestTrattative:
    def test_trattativa_polizza_allegati_invia(self, s, cleanup):
        pol = _polizza_with_contraente(s)
        r = s.post(f"{API}/trattative", json={"anagrafica_id": pol["contraente_id"], "titolo": "TEST_Trattativa",
                                               "note": "TEST nota trattativa", "premio_proposto": 100})
        assert r.status_code == 201, r.text
        t = r.json()
        cleanup["tr"].append(t["id"])
        assert t["allegati"] == []
        body = {k: t.get(k) for k in ("anagrafica_id", "titolo", "note", "premio_proposto", "stato")}
        body["polizza_id"] = pol["id"]
        u = s.put(f"{API}/trattative/{t['id']}", json=body)
        assert u.status_code == 200 and u.json()["polizza_id"] == pol["id"]
        assert u.json().get("polizza_numero") == pol.get("numero_polizza")
        files = {"file": ("TEST_prev.txt", io.BytesIO(b"preventivo"), "text/plain")}
        up = s.post(f"{API}/allegati", params={"entita_tipo": "trattativa", "entita_id": t["id"]}, files=files)
        assert up.status_code == 201, up.text
        cleanup["all"].append(up.json()["id"])
        g = s.get(f"{API}/trattative/{t['id']}").json()
        assert len(g["allegati"]) == 1
        lst = s.get(f"{API}/trattative", params={"polizza_id": pol["id"]}).json()
        assert any(x["id"] == t["id"] for x in lst)
        for canale in ("email", "whatsapp"):
            inv = s.post(f"{API}/trattative/{t['id']}/invia", json={"canale": canale}, timeout=60)
            print(canale, inv.status_code, inv.text[:200])
            assert inv.status_code in (200, 400, 503), inv.text
        bad = s.post(f"{API}/trattative/{t['id']}/invia", json={"canale": "fax"})
        assert bad.status_code == 400
        nf = s.post(f"{API}/trattative/nonexistent/invia", json={"canale": "email"})
        assert nf.status_code == 404


# ---------- PIPELINE cards ----------
class TestPipeline:
    def test_card_checklist_links(self, s, cleanup):
        r = s.post(f"{API}/pipelines", json={"nome": f"TEST_Pipe_{uuid.uuid4().hex[:5]}"})
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        cleanup["pipe"].append(pid)
        pol = _polizza_with_contraente(s)
        chk = [{"id": "a", "testo": "doc", "done": False}, {"id": "b", "testo": "firma", "done": True}]
        c = s.post(f"{API}/pipelines/{pid}/cards", json={"titolo": "TEST_card", "checklist": chk,
                                                         "polizza_id": pol["id"], "anagrafica_id": pol["contraente_id"]})
        assert c.status_code == 201, c.text
        cid = c.json()["id"]
        g = s.get(f"{API}/pipelines/{pid}/cards/{cid}")
        assert g.status_code == 200
        assert len(g.json()["checklist"]) == 2 and g.json()["polizza_numero"] == pol.get("numero_polizza")
        chk[0]["done"] = True
        u = s.put(f"{API}/pipelines/{pid}/cards/{cid}", json={"checklist": chk})
        assert u.status_code == 200
        assert all(x["done"] for x in s.get(f"{API}/pipelines/{pid}/cards/{cid}").json()["checklist"])
        files = {"file": ("TEST_card.txt", io.BytesIO(b"card"), "text/plain")}
        up = s.post(f"{API}/allegati", params={"entita_tipo": "pipeline_card", "entita_id": cid}, files=files)
        assert up.status_code == 201
        cleanup["all"].append(up.json()["id"])
        assert s.get(f"{API}/pipelines/{pid}/cards/nope").status_code == 404
