"""
Iteration 103 — Incasso multiplo con merge (feature #1), colonna data incasso (feature #2),
e verifica incasso singolo invariato.

Scope:
- POST /api/titoli/{id}/incassa con merge_copertura=true dopo bulk-copertura:
  deve eliminare la riga 'copertura_titolo' e creare UNA riga 'incasso_premio' con provvigioni>0.
- POST /api/titoli/{id}/incassa SENZA merge_copertura: comportamento storico 'incasso_coperto' preservato.
- GET /api/pnc, /api/ritenute-compagnia, /api/rappel espongono data_versamento / data_incasso.
"""
import os
from datetime import date
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"
TODAY = date.today().isoformat()


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def compagnia_id(session):
    r = session.get(f"{BASE_URL}/api/compagnie", timeout=30)
    assert r.status_code == 200, r.text
    comps = r.json()
    # cerco una compagnia che trattiene provvigioni
    for c in comps:
        if c.get("trattiene_provvigioni"):
            return c["id"]
    # fallback: prendo la prima e la aggiorno
    assert comps, "Nessuna compagnia presente"
    cid = comps[0]["id"]
    session.put(f"{BASE_URL}/api/compagnie/{cid}", json={"trattiene_provvigioni": True}, timeout=30)
    return cid


@pytest.fixture(scope="module")
def anagrafica_id(session):
    payload = {
        "tipo": "persona_fisica",
        "nome": "TESTMERGE",
        "cognome": "Iter103",
        "codice_fiscale": "TSTMRG80A01H501Z",
    }
    r = session.post(f"{BASE_URL}/api/anagrafiche", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _crea_polizza_e_titolo(session, compagnia_id, anagrafica_id, numero_polizza):
    pol_payload = {
        "contraente_id": anagrafica_id,
        "compagnia_id": compagnia_id,
        "numero_polizza": numero_polizza,
        "ramo": "RCA",
        "effetto": TODAY,
        "scadenza": TODAY,
        "frazionamento": "annuale",
    }
    r = session.post(f"{BASE_URL}/api/polizze", json=pol_payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    polizza_id = r.json()["id"]
    tit_payload = {
        "polizza_id": polizza_id,
        "stato": "da_incassare",
        "importo_lordo": 158.50,
        "provvigioni": 34.05,
        "data_scadenza": TODAY,
        "data_decorrenza": TODAY,
        "effetto": TODAY,
        "scadenza": TODAY,
    }
    r = session.post(f"{BASE_URL}/api/titoli", json=tit_payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return polizza_id, r.json()["id"]


def _get_mov_for_titolo(session, titolo_id, categoria=None):
    r = session.get(f"{BASE_URL}/api/contabilita/brogliaccio", params={"data": TODAY}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    movs = []
    # Cerco anche in movimenti grezzi se disponibili
    r2 = session.get(f"{BASE_URL}/api/contabilita/movimenti", params={"titolo_id": titolo_id}, timeout=30)
    if r2.status_code == 200:
        for m in r2.json():
            if (categoria is None or m.get("categoria") == categoria):
                movs.append(m)
    return movs, data


def test_1_merge_incasso_multiplo(session, compagnia_id, anagrafica_id):
    """Feature #1: merge_copertura=true -> una sola riga incasso_premio, no copertura_titolo."""
    _, titolo_id = _crea_polizza_e_titolo(session, compagnia_id, anagrafica_id, f"TESTMERGE-{TODAY}-M1")

    # Bulk copertura oggi
    r = session.post(
        f"{BASE_URL}/api/titoli/bulk-copertura",
        json={"ids": [titolo_id], "data_copertura": TODAY},
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text

    # verifica che esista il movimento di copertura
    movs_cop, _ = _get_mov_for_titolo(session, titolo_id, "copertura_titolo")
    assert len(movs_cop) >= 1, "Movimento copertura_titolo non creato dopo bulk-copertura"

    # Incasso con merge_copertura=true
    r = session.post(
        f"{BASE_URL}/api/titoli/{titolo_id}/incassa",
        json={
            "data_incasso": TODAY,
            "mezzo_pagamento": "bonifico",
            "importo_pagato": 158.50,
            "tipo_chiusura": "sconto",
            "merge_copertura": True,
        },
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text

    # Dopo incasso: nessun movimento copertura_titolo, uno incasso_premio con provvigioni>0
    movs_cop_after, _ = _get_mov_for_titolo(session, titolo_id, "copertura_titolo")
    assert len(movs_cop_after) == 0, f"copertura_titolo non rimossa dopo merge: {movs_cop_after}"

    movs_premio, _ = _get_mov_for_titolo(session, titolo_id, "incasso_premio")
    movs_coperto, _ = _get_mov_for_titolo(session, titolo_id, "incasso_coperto")
    assert len(movs_coperto) == 0, "Non deve esistere 'incasso_coperto' con merge"
    assert len(movs_premio) == 1, f"Deve esistere UN movimento incasso_premio, trovati: {len(movs_premio)}"
    assert float(movs_premio[0].get("provvigioni") or 0) > 0, "Provvigioni devono essere > 0 nel merge"
    assert float(movs_premio[0].get("importo") or 0) == pytest.approx(158.50, rel=1e-3)


def test_2_incasso_singolo_invariato(session, compagnia_id, anagrafica_id):
    """Senza merge_copertura: comportamento storico (incasso_coperto, provvigioni=0, copertura resta)."""
    _, titolo_id = _crea_polizza_e_titolo(session, compagnia_id, anagrafica_id, f"TESTMERGE-{TODAY}-S1")

    r = session.post(
        f"{BASE_URL}/api/titoli/bulk-copertura",
        json={"ids": [titolo_id], "data_copertura": TODAY},
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text

    r = session.post(
        f"{BASE_URL}/api/titoli/{titolo_id}/incassa",
        json={
            "data_incasso": TODAY,
            "mezzo_pagamento": "bonifico",
            "importo_pagato": 158.50,
            "tipo_chiusura": "sconto",
        },
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text

    movs_cop, _ = _get_mov_for_titolo(session, titolo_id, "copertura_titolo")
    assert len(movs_cop) >= 1, "La riga di copertura deve restare nel flusso storico senza merge"

    movs_coperto, _ = _get_mov_for_titolo(session, titolo_id, "incasso_coperto")
    assert len(movs_coperto) == 1, f"Deve esistere UN incasso_coperto, trovati: {len(movs_coperto)}"
    assert float(movs_coperto[0].get("provvigioni") or 0) == 0.0, "Provvigioni devono essere 0 (storico)"


def test_3_data_incasso_fields_present(session):
    """Feature #2: /api/pnc e /api/ritenute-compagnia hanno data_versamento;
    /api/rappel ha data_incasso sui record versati/incassati."""
    # pnc
    r = session.get(f"{BASE_URL}/api/pnc", timeout=30)
    assert r.status_code == 200, r.text
    pnc = r.json()
    versati = [p for p in pnc if p.get("stato") == "versata"]
    if versati:
        assert "data_versamento" in versati[0], "campo data_versamento mancante in /api/pnc"

    # ritenute-compagnia
    r = session.get(f"{BASE_URL}/api/ritenute-compagnia", timeout=30)
    assert r.status_code == 200, r.text
    rit = r.json()
    rit_vers = [x for x in rit if x.get("stato") == "versata"]
    if rit_vers:
        assert "data_versamento" in rit_vers[0], "campo data_versamento mancante in /api/ritenute-compagnia"

    # rappel
    r = session.get(f"{BASE_URL}/api/rappel", timeout=30)
    assert r.status_code == 200, r.text
    rap = r.json()
    rap_inc = [x for x in rap if x.get("stato") == "incassato"]
    if rap_inc:
        assert "data_incasso" in rap_inc[0], "campo data_incasso mancante in /api/rappel"
    # Se nessuno è in stato versato/incassato, questo test diventa informativo (non fallisce)
    print(f"PNC versati:{len(versati) if 'versati' in dir() else '?'}, "
          f"Ritenute versate:{len(rit_vers)}, Rappel incassati:{len(rap_inc)}")
