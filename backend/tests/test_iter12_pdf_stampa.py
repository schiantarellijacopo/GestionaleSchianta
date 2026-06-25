"""Iter12 tests:
- 3 new PDF endpoints
  * GET /api/stampa/pagamento-provvigioni/{pid}
  * GET /api/stampa/rimessa/{mov_id}
  * POST /api/stampa/compagnie/{cid}/titoli-selezionati
- Enrichment of GET /api/collaboratori/{cid}/pagamenti and /compagnie/{cid}/rimesse-storico
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def setup_data(client):
    """Create a complete chain: polizza + 2 titoli da_incassare → incassati → pagati collaboratore → pagati compagnia."""
    collabs = client.get(f"{API}/collaboratori").json()
    assert collabs, "no collaboratori seeded"
    collab = collabs[0]

    comps = client.get(f"{API}/compagnie").json()
    assert comps, "no compagnie seeded"
    comp = comps[0]

    anas = client.get(f"{API}/anagrafiche").json()
    assert anas, "no anagrafiche seeded"
    ana = anas[0]

    ts = int(time.time())
    pol = client.post(f"{API}/polizze", json={
        "numero_polizza": f"TEST_iter12_{ts}",
        "compagnia_id": comp["id"],
        "contraente_id": ana["id"],
        "ramo": "RCA",
        "effetto": "2025-01-01",
        "scadenza": "2026-01-01",
        "premio_lordo": 800.0,
        "collaboratore_id": collab["id"],
    }).json()

    # Two titoli
    titoli_ids = []
    for i in range(2):
        t = client.post(f"{API}/titoli", json={
            "polizza_id": pol["id"],
            "tipo": "nuova",
            "stato": "da_incassare",
            "data_emissione": "2025-01-01",
            "data_copertura": "2025-01-01",
            "effetto": "2025-01-01",
            "scadenza": "2026-01-01",
            "importo_lordo": 100.0 + i * 50,
            "provvigioni": 15.0 + i * 5,
        }).json()
        # incassa
        r = client.post(f"{API}/titoli/{t['id']}/incassa", json={
            "mezzo_pagamento": "bonifico", "data_incasso": "2025-02-01",
        })
        assert r.status_code == 200, r.text
        titoli_ids.append(t["id"])

    # paga collaboratore
    r = client.post(f"{API}/collaboratori/{collab['id']}/paga-provvigioni", json={
        "titoli_ids": titoli_ids,
        "mezzo_pagamento": "bonifico",
        "data_pagamento": "2025-02-10",
        "note": "TEST_iter12",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    pag_id = body["pagamento"]["id"]

    # paga compagnia
    r = client.post(f"{API}/compagnie/{comp['id']}/paga-titoli", json={
        "titoli_ids": titoli_ids,
        "mezzo_pagamento": "bonifico",
        "data_movimento": "2025-02-15",
        "descrizione": "TEST_iter12 rimessa",
    })
    assert r.status_code == 200, r.text
    rimessa_mov_id = r.json()["movimento_id"]

    return {
        "collab_id": collab["id"], "comp_id": comp["id"],
        "polizza_id": pol["id"], "titoli_ids": titoli_ids,
        "pagamento_id": pag_id, "rimessa_mov_id": rimessa_mov_id,
    }


# ---- PDF endpoints ----

def _assert_pdf(resp):
    assert resp.status_code == 200, f"expected 200, got {resp.status_code} {resp.text[:200]}"
    ct = resp.headers.get("content-type", "")
    assert "pdf" in ct.lower(), f"content-type not pdf: {ct}"
    assert resp.content[:4] == b"%PDF", f"not a PDF, first bytes: {resp.content[:20]!r}"
    assert len(resp.content) > 500, "PDF suspiciously small"


def test_stampa_pagamento_provvigioni_ok(client, setup_data):
    pid = setup_data["pagamento_id"]
    r = client.get(f"{API}/stampa/pagamento-provvigioni/{pid}")
    _assert_pdf(r)


def test_stampa_pagamento_provvigioni_404(client):
    r = client.get(f"{API}/stampa/pagamento-provvigioni/non-existent-pid")
    assert r.status_code == 404


def test_stampa_rimessa_ok(client, setup_data):
    mov_id = setup_data["rimessa_mov_id"]
    r = client.get(f"{API}/stampa/rimessa/{mov_id}")
    _assert_pdf(r)


def test_stampa_rimessa_404_wrong_id(client):
    r = client.get(f"{API}/stampa/rimessa/non-existent-mov")
    assert r.status_code == 404


def test_stampa_rimessa_404_wrong_categoria(client, setup_data):
    """A movimento that exists but is not pagamento_compagnia should return 404."""
    # The pagamento_provvigioni created a movimento of categoria=provvigioni; use it to check
    cid = setup_data["collab_id"]
    pags = client.get(f"{API}/collaboratori/{cid}/pagamenti").json()
    our = next((p for p in pags if p["id"] == setup_data["pagamento_id"]), None)
    assert our is not None
    other_mov_id = our.get("movimento_id")
    assert other_mov_id, "movimento_id missing from pagamento list (enrichment)"
    r = client.get(f"{API}/stampa/rimessa/{other_mov_id}")
    assert r.status_code == 404, "Should 404: movimento exists but is not pagamento_compagnia"


def test_stampa_titoli_selezionati_ok(client, setup_data):
    comp_id = setup_data["comp_id"]
    tids = setup_data["titoli_ids"]
    r = client.post(f"{API}/stampa/compagnie/{comp_id}/titoli-selezionati",
                    json={"titoli_ids": tids})
    _assert_pdf(r)


def test_stampa_titoli_selezionati_empty_400(client, setup_data):
    comp_id = setup_data["comp_id"]
    r = client.post(f"{API}/stampa/compagnie/{comp_id}/titoli-selezionati",
                    json={"titoli_ids": []})
    assert r.status_code == 400


def test_stampa_titoli_selezionati_unknown_comp_404(client):
    r = client.post(f"{API}/stampa/compagnie/non-existent-cid/titoli-selezionati",
                    json={"titoli_ids": ["x"]})
    assert r.status_code == 404


# ---- Enriched list endpoints ----

def test_list_pagamenti_includes_movimento_id_and_counts(client, setup_data):
    cid = setup_data["collab_id"]
    r = client.get(f"{API}/collaboratori/{cid}/pagamenti")
    assert r.status_code == 200
    our = next((p for p in r.json() if p["id"] == setup_data["pagamento_id"]), None)
    assert our is not None
    for k in ("movimento_id", "n_titoli", "n_voci_manuali", "n_allegati", "conto_cassa_nome"):
        assert k in our, f"missing key {k}"
    assert our["n_titoli"] == 2
    assert isinstance(our["movimento_id"], str) and len(our["movimento_id"]) > 0


def test_rimesse_storico_enriched(client, setup_data):
    comp_id = setup_data["comp_id"]
    r = client.get(f"{API}/compagnie/{comp_id}/rimesse-storico")
    assert r.status_code == 200, r.text
    data = r.json()
    rimesse = data.get("rimesse") or data  # tolerate dict or list
    if isinstance(rimesse, dict):
        rimesse = rimesse.get("rimesse", [])
    our = next((m for m in rimesse if m.get("id") == setup_data["rimessa_mov_id"]), None)
    assert our is not None, f"rimessa {setup_data['rimessa_mov_id']} not in storico"
    assert our.get("n_titoli") == 2
    assert "n_allegati" in our
    assert "titoli" in our and len(our["titoli"]) == 2
    t0 = our["titoli"][0]
    assert "numero_polizza" in t0
    assert "ramo" in t0
    assert "contraente_nome" in t0


# ---- Regression: gia_pagato flag should mark paid titoli ----

def test_provvigioni_endpoint_marks_titoli_as_gia_pagato(client, setup_data):
    """The /api/collaboratori/{cid}/provvigioni endpoint must return gia_pagato=true
    for titoli already paid via paga-provvigioni. The frontend uses this flag to
    filter them out of the active 'Provvigioni maturate' list."""
    cid = setup_data["collab_id"]
    r = client.get(f"{API}/collaboratori/{cid}/estratto-provvigioni")
    assert r.status_code == 200, r.text
    data = r.json()
    # response has "righe" key with rows
    righe = data.get("righe") if isinstance(data, dict) else data
    assert righe is not None, f"no righe in response: {data}"
    our_rows = [r for r in righe if r.get("titolo_id") in setup_data["titoli_ids"]]
    assert len(our_rows) == 2, f"expected 2 rows, got {len(our_rows)}"
    for r in our_rows:
        assert r.get("gia_pagato") is True, f"titolo {r['titolo_id']} should be gia_pagato=True, got {r.get('gia_pagato')}"


def test_titoli_marked_pagato_alla_compagnia(client, setup_data):
    """After /compagnie/{cid}/paga-titoli, the titoli should have pagato_alla_compagnia=True
    on the raw /api/titoli endpoint. The frontend filters with this to remove them from
    the active 'Movimenti & versamenti' tab."""
    pol_id = setup_data["polizza_id"]
    titoli = client.get(f"{API}/titoli", params={"polizza_id": pol_id}).json()
    assert len(titoli) >= 2
    for t in titoli:
        assert (
            t.get("pagato_alla_compagnia") is True
            or t.get("stato_pagamento") == "pagato"
            or t.get("data_pagamento_compagnia")
        ), f"titolo {t['id']} missing 'pagato alla compagnia' marker"
