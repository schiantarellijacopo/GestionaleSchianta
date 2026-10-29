"""Incasso IN DIREZIONE (singolo + multiplo con merge_copertura) — nessuna riga copertura_titolo.

Tenant reale Schiantarelli (jacopo@schiantarelli.it). Crea polizza/titoli TEST_ e pulisce alla fine.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EMAIL = "jacopo@schiantarelli.it"
PASSWORD = "NtdZs5ilxTSP"
CATTOLICA = "95f7d1fa-d81d-4658-b87c-164e2459da86"
ARRETRATO_SCAD = "2026-09-15"

_created = {"titoli": [], "polizze": [], "anagrafiche": []}


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    r = ses.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    ses.headers.update({"Authorization": f"Bearer {tok}"})
    yield ses
    # Cleanup
    for tid in _created["titoli"]:
        ses.delete(f"{BASE_URL}/api/titoli/{tid}", timeout=30)
    for pid in _created["polizze"]:
        # anche i titoli auto-generati dalla creazione polizza (DELETE polizza non fa cascade)
        r = ses.get(f"{BASE_URL}/api/titoli", params={"polizza_id": pid}, timeout=30)
        if r.status_code == 200:
            items = r.json() if isinstance(r.json(), list) else (r.json().get("items") or [])
            for t in items:
                ses.delete(f"{BASE_URL}/api/titoli/{t['id']}", timeout=30)
        ses.delete(f"{BASE_URL}/api/polizze/{pid}", timeout=30)
    for aid in _created["anagrafiche"]:
        ses.delete(f"{BASE_URL}/api/anagrafiche/{aid}", params={"force": True}, timeout=30)


@pytest.fixture(scope="module")
def today(s):
    # data server
    r = s.get(f"{BASE_URL}/api/contabilita/brogliaccio", timeout=60)
    d = (r.json() or {}).get("data") if r.status_code == 200 else None
    from datetime import date
    return d or date.today().isoformat()


@pytest.fixture(scope="module")
def anag(s):
    r = s.post(f"{BASE_URL}/api/anagrafiche", json={
        "tipo": "persona_fisica", "nome": "TEST_DIR", "cognome": "Multiplo",
        "codice_fiscale": "TSTDRZ80A01H501Z"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    _created["anagrafiche"].append(r.json()["id"])
    return r.json()["id"]


def _mk_titolo(s, anag, lordo=200.0, provv=30.0):
    num = f"TEST_DIR_{uuid.uuid4().hex[:8]}"
    r = s.post(f"{BASE_URL}/api/polizze", json={
        "contraente_id": anag, "compagnia_id": CATTOLICA, "numero_polizza": num,
        "ramo": "RCA", "effetto": "2025-09-15", "scadenza": "2027-09-15",
        "frazionamento": "annuale"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    _created["polizze"].append(pid)
    # rimuovi eventuali titoli auto-generati e crea titolo arretrato pulito
    r = s.post(f"{BASE_URL}/api/titoli", json={
        "polizza_id": pid, "stato": "da_incassare", "importo_lordo": lordo,
        "provvigioni": provv, "data_scadenza": ARRETRATO_SCAD, "effetto": ARRETRATO_SCAD,
        "scadenza": ARRETRATO_SCAD, "data_decorrenza": ARRETRATO_SCAD}, timeout=30)
    assert r.status_code in (200, 201), r.text
    tid = r.json()["id"]
    _created["titoli"].append(tid)
    return pid, tid


def _movs(s, tid):
    r = s.get(f"{BASE_URL}/api/contabilita/movimenti", params={"titolo_id": tid}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _get_tit(s, tid):
    r = s.get(f"{BASE_URL}/api/titoli/{tid}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _assert_direzione_only(s, tid, lordo, provv):
    movs = _movs(s, tid)
    cats = [m["categoria"] for m in movs]
    assert cats == ["incasso_premio_direzione"], f"movimenti attesi 1 direzione, trovati {cats}"
    m = movs[0]
    assert m["is_direzione"] is True
    assert m.get("conto_cassa_id") is None
    assert abs(float(m["importo"]) - lordo) < 0.01
    assert abs(float(m["provvigioni"]) - provv) < 0.01
    t = _get_tit(s, tid)
    t = t.get("titolo", t)
    assert t["stato"] == "incassato"
    assert t.get("pagamento_in_direzione") is True
    return m


# Singolo in direzione su arretrato non coperto
def test_singolo_direzione_arretrato(s, anag, today):
    _, tid = _mk_titolo(s, anag, 200.0, 30.0)
    assert _movs(s, tid) == []
    r = s.post(f"{BASE_URL}/api/titoli/{tid}/incassa",
               json={"data_incasso": today, "mezzo_pagamento": "DIREZIONE"}, timeout=30)
    assert r.status_code == 200, r.text
    _assert_direzione_only(s, tid, 200.0, 30.0)


# Multiplo (flusso frontend): per ogni titolo incassa con direzione + merge_copertura=true
def test_multiplo_direzione_no_copertura(s, anag, today):
    tids = [_mk_titolo(s, anag, 150.0, 20.0)[1], _mk_titolo(s, anag, 250.0, 40.0)[1]]
    for tid, lordo in zip(tids, (150.0, 250.0)):
        r = s.post(f"{BASE_URL}/api/titoli/{tid}/incassa", json={
            "data_incasso": today, "mezzo_pagamento": "DIREZIONE", "conto_cassa_id": None,
            "importo_pagato": lordo, "tipo_chiusura": "sconto", "merge_copertura": True}, timeout=30)
        assert r.status_code == 200, r.text
    _assert_direzione_only(s, tids[0], 150.0, 20.0)
    _assert_direzione_only(s, tids[1], 250.0, 40.0)
    # Brogliaccio del giorno: 1 riga direzione per titolo, 0 copertura
    r = s.get(f"{BASE_URL}/api/contabilita/brogliaccio", params={"data": today}, timeout=120)
    assert r.status_code == 200, r.text
    body = r.json()
    rows = body.get("righe") or body.get("rows") or body.get("movimenti") or []
    assert rows, f"brogliaccio senza righe; keys={list(body.keys())}"
    for tid in tids:
        mine = [x for x in rows if x.get("titolo_id") == tid]
        assert len(mine) == 1, f"titolo {tid}: righe brogliaccio {len(mine)}: {mine}"
        assert mine[0].get("categoria") == "incasso_premio_direzione"
        assert mine[0].get("is_direzione") is True


# Copertura già presente stesso giorno + direzione merge -> copertura assorbita
def test_direzione_assorbe_copertura_stesso_giorno(s, anag, today):
    _, tid = _mk_titolo(s, anag, 180.0, 25.0)
    r = s.post(f"{BASE_URL}/api/titoli/bulk-copertura", json={"ids": [tid], "data_copertura": today}, timeout=30)
    assert r.status_code in (200, 201), r.text
    cats = [m["categoria"] for m in _movs(s, tid)]
    assert "copertura_titolo" in cats, f"copertura non creata: {cats}"
    r = s.post(f"{BASE_URL}/api/titoli/{tid}/incassa", json={
        "data_incasso": today, "mezzo_pagamento": "DIREZIONE", "importo_pagato": 180.0,
        "merge_copertura": True}, timeout=30)
    assert r.status_code == 200, r.text
    m = _assert_direzione_only(s, tid, 180.0, 25.0)
    assert m.get("coperture_assorbite"), "snapshot coperture_assorbite mancante"
    assert m["coperture_assorbite"][0]["categoria"] == "copertura_titolo"


# Copertura stesso giorno + direzione SENZA merge flag -> safety net same-day
def test_direzione_assorbe_copertura_senza_flag(s, anag, today):
    _, tid = _mk_titolo(s, anag, 120.0, 15.0)
    r = s.post(f"{BASE_URL}/api/titoli/bulk-copertura", json={"ids": [tid], "data_copertura": today}, timeout=30)
    assert r.status_code in (200, 201), r.text
    r = s.post(f"{BASE_URL}/api/titoli/{tid}/incassa", json={
        "data_incasso": today, "mezzo_pagamento": "DIREZIONE"}, timeout=30)
    assert r.status_code == 200, r.text
    _assert_direzione_only(s, tid, 120.0, 15.0)


# Regressione: incasso normale (non direzione) su arretrato -> 1 riga incasso_premio
def test_incasso_normale_regressione(s, anag, today):
    _, tid = _mk_titolo(s, anag, 100.0, 10.0)
    r = s.post(f"{BASE_URL}/api/titoli/{tid}/incassa", json={
        "data_incasso": today, "mezzo_pagamento": "contanti", "merge_copertura": True}, timeout=30)
    assert r.status_code == 200, r.text
    cats = [m["categoria"] for m in _movs(s, tid)]
    assert cats == ["incasso_premio"], cats
