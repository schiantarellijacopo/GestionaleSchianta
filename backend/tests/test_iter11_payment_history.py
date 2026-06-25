"""Tests for iter11 features:
- Auto-resolved conto_cassa on payment endpoints
- Storico pagamenti (collaboratori) and storico rimesse (compagnie)
- Allegati on movimento
"""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


# ---- fixtures ----
@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def ctx(client):
    """Pre-creates polizza+titolo da_incassare, collaboratore reference, compagnia.
    Returns dict with collab_id, comp_id, ana_id, titolo_id (da_incassare).
    """
    # find a collaboratore user (admin can also be one)
    collabs = client.get(f"{API}/collaboratori").json()
    assert isinstance(collabs, list) and len(collabs) > 0, f"no collaboratori in db: {collabs}"
    collab = collabs[0]

    # compagnia
    comps = client.get(f"{API}/compagnie").json()
    assert comps, "no compagnie seeded"
    comp = comps[0]

    # anagrafica
    anas = client.get(f"{API}/anagrafiche").json()
    assert anas, "no anagrafiche seeded"
    ana = anas[0]

    # create polizza + titolo da_incassare for tests
    ts = int(time.time())
    pol_payload = {
        "numero_polizza": f"TEST_iter11_{ts}",
        "compagnia_id": comp["id"],
        "contraente_id": ana["id"],
        "ramo": "RCA",
        "effetto": "2025-01-01",
        "scadenza": "2026-01-01",
        "premio_lordo": 500.0,
        "collaboratore_id": collab["id"],
    }
    r = client.post(f"{API}/polizze", json=pol_payload)
    assert r.status_code in (200, 201), f"polizza create failed: {r.status_code} {r.text}"
    pol = r.json()

    # create a titolo on that polizza
    tit_payload = {
        "polizza_id": pol["id"],
        "tipo": "nuova",
        "stato": "da_incassare",
        "data_emissione": "2025-01-01",
        "data_copertura": "2025-01-01",
        "effetto": "2025-01-01",
        "scadenza": "2026-01-01",
        "importo_lordo": 200.0,
        "provvigioni": 30.0,
    }
    r = client.post(f"{API}/titoli", json=tit_payload)
    assert r.status_code in (200, 201), f"titolo create failed: {r.status_code} {r.text}"
    tit = r.json()

    return {
        "collab_id": collab["id"],
        "comp_id": comp["id"],
        "ana_id": ana["id"],
        "polizza_id": pol["id"],
        "titolo_id": tit["id"],
    }


# ---- TESTS ----

def test_incassa_without_conto_cassa(client, ctx):
    """POST /titoli/{tid}/incassa should auto-resolve conto_cassa from mezzo."""
    tid = ctx["titolo_id"]
    r = client.post(
        f"{API}/titoli/{tid}/incassa",
        json={"mezzo_pagamento": "bonifico", "data_incasso": "2025-02-01"},
    )
    assert r.status_code == 200, f"incassa failed: {r.status_code} {r.text}"
    body = r.json()
    # check titolo via list endpoint
    titoli_list = client.get(f"{API}/titoli", params={"polizza_id": ctx["polizza_id"]}).json()
    t = next((x for x in titoli_list if x["id"] == tid), None)
    assert t is not None, "titolo not found in /titoli list"
    assert t["stato"] == "incassato"
    assert t.get("conto_cassa_id"), "conto_cassa_id should be auto-resolved and set"
    assert t.get("mezzo_pagamento") == "bonifico"


def test_paga_provvigioni_without_conto_cassa(client, ctx):
    """POST /collaboratori/{cid}/paga-provvigioni auto-resolves conto and creates pagamento + movimento."""
    cid = ctx["collab_id"]
    # use the same titolo that was incassed (must be incassato to be 'da pagare')
    tids = [ctx["titolo_id"]]
    r = client.post(
        f"{API}/collaboratori/{cid}/paga-provvigioni",
        json={
            "titoli_ids": tids,
            "mezzo_pagamento": "bonifico",
            "data_pagamento": "2025-02-10",
            "note": "TEST_iter11 pagamento",
        },
    )
    assert r.status_code == 200, f"paga-provvigioni failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("ok") is True
    pag = body["pagamento"]
    mov = body["movimento"]
    assert pag.get("conto_cassa_id"), "conto_cassa_id should be auto-resolved"
    assert mov.get("tipo") == "uscita"
    assert mov.get("categoria") == "provvigioni"
    # store for later tests
    ctx["pagamento_id"] = pag["id"]
    ctx["movimento_id"] = mov["id"]


def test_list_pagamenti_enriched(client, ctx):
    cid = ctx["collab_id"]
    r = client.get(f"{API}/collaboratori/{cid}/pagamenti")
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    # find our created pagamento
    our = next((p for p in items if p["id"] == ctx["pagamento_id"]), None)
    assert our is not None, "created pagamento not in list"
    # Enriched fields
    for k in ("n_titoli", "n_voci_manuali", "n_allegati", "conto_cassa_nome"):
        assert k in our, f"missing key: {k}"
    assert our["n_titoli"] == 1
    assert our["n_voci_manuali"] == 0
    assert our["n_allegati"] == 0  # no allegati yet


def test_get_pagamento_dettaglio(client, ctx):
    cid = ctx["collab_id"]
    pid = ctx["pagamento_id"]
    r = client.get(f"{API}/collaboratori/{cid}/pagamenti/{pid}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "titoli" in d and isinstance(d["titoli"], list)
    assert "voci_manuali" in d and isinstance(d["voci_manuali"], list)
    assert "conto_cassa_nome" in d
    assert "n_allegati" in d
    assert len(d["titoli"]) == 1
    t0 = d["titoli"][0]
    # enrichment present
    assert "numero_polizza" in t0
    assert "ramo" in t0
    assert "contraente_nome" in t0
    assert t0["numero_polizza"].startswith("TEST_iter11_")


def test_get_pagamento_dettaglio_404(client, ctx):
    cid = ctx["collab_id"]
    r = client.get(f"{API}/collaboratori/{cid}/pagamenti/non-existent-pid")
    assert r.status_code == 404


def test_allegato_upload_to_movimento(client, ctx):
    mov_id = ctx["movimento_id"]
    # upload a small PDF-like file
    files = {"file": ("invoice.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
    params = {"entita_tipo": "movimento", "entita_id": mov_id, "descrizione": "TEST_iter11 fattura"}
    r = client.post(f"{API}/allegati", params=params, files=files)
    assert r.status_code in (200, 201), f"allegato upload failed: {r.status_code} {r.text}"
    a = r.json()
    assert a.get("entita_tipo") == "movimento"
    assert a.get("entita_id") == mov_id

    # list allegati for movimento
    r = client.get(f"{API}/allegati", params={"entita_tipo": "movimento", "entita_id": mov_id})
    assert r.status_code == 200
    items = r.json()
    assert any(x.get("id") == a["id"] for x in items)

    # n_allegati now reflected in list_pagamenti
    cid = ctx["collab_id"]
    r = client.get(f"{API}/collaboratori/{cid}/pagamenti")
    pag = next((p for p in r.json() if p["id"] == ctx["pagamento_id"]), None)
    assert pag and pag["n_allegati"] >= 1


def test_paga_compagnia_without_conto_cassa(client, ctx):
    """POST /compagnie/{cid}/paga-titoli should auto-resolve conto_cassa."""
    comp_id = ctx["comp_id"]
    tid = ctx["titolo_id"]  # already incassato
    r = client.post(
        f"{API}/compagnie/{comp_id}/paga-titoli",
        json={
            "titoli_ids": [tid],
            "mezzo_pagamento": "bonifico",
            "data_movimento": "2025-02-15",
            "descrizione": "TEST_iter11 versamento compagnia",
        },
    )
    assert r.status_code == 200, f"paga compagnia failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("ok") is True
    assert body.get("titoli_pagati") == 1
    ctx["rimessa_mov_id"] = body["movimento_id"]


def test_rimesse_storico(client, ctx):
    comp_id = ctx["comp_id"]
    r = client.get(f"{API}/compagnie/{comp_id}/rimesse-storico")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "rimesse" in data
    our = next((m for m in data["rimesse"] if m.get("id") == ctx.get("rimessa_mov_id")), None)
    assert our is not None, "rimessa not in storico"
    assert our.get("n_titoli") == 1
    assert "n_allegati" in our
    assert "titoli" in our and len(our["titoli"]) == 1
    t0 = our["titoli"][0]
    assert t0.get("numero_polizza", "").startswith("TEST_iter11_")
    assert "contraente_nome" in t0
