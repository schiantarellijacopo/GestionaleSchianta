"""
Iteration 107 — Revert titolo on DELETE movimento (Prima Nota).

Business rules (new):
A) copertura_titolo deleted => titolo torna ARRETRATO (stato=da_incassare, titolo_coperto=false, data_copertura cleared)
B) incasso_premio (merged covered) deleted => titolo torna SOSPESO (coperto=true) + copertura ripristinata in Prima Nota
B2) legacy incasso_premio (no coperture_assorbite snapshot) ma titolo.titolo_coperto=true => fallback: ricostruzione copertura
C) incasso_premio di titolo ARRETRATO (non coperto) deleted => torna ARRETRATO (coperto=false)
Regression) incasso_coperto deleted => torna coperto senza duplicare copertura
"""
import os
from datetime import date
import uuid
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
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def compagnia_id(session):
    r = session.get(f"{BASE_URL}/api/compagnie", timeout=30)
    assert r.status_code == 200
    comps = r.json()
    for c in comps:
        if c.get("trattiene_provvigioni"):
            return c["id"]
    assert comps
    cid = comps[0]["id"]
    session.put(f"{BASE_URL}/api/compagnie/{cid}", json={"trattiene_provvigioni": True}, timeout=30)
    return cid


@pytest.fixture(scope="module")
def anagrafica_id(session):
    suf = uuid.uuid4().hex[:6].upper()
    payload = {
        "tipo": "persona_fisica",
        "nome": "TESTREVERT",
        "cognome": f"Iter107{suf}",
        "codice_fiscale": f"TSTRV{suf}80A01H501",
    }
    r = session.post(f"{BASE_URL}/api/anagrafiche", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _crea_polizza_titolo(session, compagnia_id, anagrafica_id, suffix):
    pol = {
        "contraente_id": anagrafica_id,
        "compagnia_id": compagnia_id,
        "numero_polizza": f"TESTREV-{TODAY}-{suffix}-{uuid.uuid4().hex[:4]}",
        "ramo": "RCA",
        "effetto": TODAY,
        "scadenza": TODAY,
        "frazionamento": "annuale",
    }
    r = session.post(f"{BASE_URL}/api/polizze", json=pol, timeout=30)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    tit = {
        "polizza_id": pid,
        "stato": "da_incassare",
        "importo_lordo": 200.00,
        "provvigioni": 40.00,
        "data_scadenza": TODAY,
        "data_decorrenza": TODAY,
        "effetto": TODAY,
        "scadenza": TODAY,
    }
    r = session.post(f"{BASE_URL}/api/titoli", json=tit, timeout=30)
    assert r.status_code in (200, 201), r.text
    return pid, r.json()["id"]


def _movs(session, tid, categoria=None):
    r = session.get(f"{BASE_URL}/api/contabilita/movimenti", params={"titolo_id": tid}, timeout=30)
    assert r.status_code == 200, r.text
    out = r.json()
    if categoria:
        out = [m for m in out if m.get("categoria") == categoria]
    return out


def _get_titolo(session, tid):
    r = session.get(f"{BASE_URL}/api/titoli/{tid}", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _cover(session, tid):
    r = session.post(f"{BASE_URL}/api/titoli/bulk-copertura",
                     json={"ids": [tid], "data_copertura": TODAY}, timeout=30)
    assert r.status_code in (200, 201), r.text


def _delete_mov(session, mid):
    r = session.delete(f"{BASE_URL}/api/contabilita/movimenti/{mid}", timeout=30)
    assert r.status_code in (200, 204), f"DELETE mov failed: {r.status_code} {r.text}"


# ---------------- Scenario A ----------------
def test_A_copertura_delete_reverts_to_arretrato(session, compagnia_id, anagrafica_id):
    _, tid = _crea_polizza_titolo(session, compagnia_id, anagrafica_id, "A")
    _cover(session, tid)
    t = _get_titolo(session, tid)
    assert t.get("titolo_coperto") is True, "Titolo deve essere coperto dopo bulk-copertura"
    cop = _movs(session, tid, "copertura_titolo")
    assert len(cop) == 1, f"Attesa 1 copertura, trovate {len(cop)}"
    _delete_mov(session, cop[0]["id"])
    t = _get_titolo(session, tid)
    assert t.get("stato") == "da_incassare"
    assert t.get("titolo_coperto") in (False, None), f"titolo_coperto deve essere false, got {t.get('titolo_coperto')}"
    assert not t.get("data_copertura"), f"data_copertura deve essere cleared, got {t.get('data_copertura')}"
    cop_after = _movs(session, tid, "copertura_titolo")
    assert len(cop_after) == 0


# ---------------- Scenario B (merge path) ----------------
def test_B_merge_incasso_delete_restores_sospeso_and_copertura(session, compagnia_id, anagrafica_id):
    _, tid = _crea_polizza_titolo(session, compagnia_id, anagrafica_id, "B")
    _cover(session, tid)
    # Incasso con merge
    r = session.post(f"{BASE_URL}/api/titoli/{tid}/incassa", json={
        "data_incasso": TODAY,
        "mezzo_pagamento": "bonifico",
        "importo_pagato": 200.00,
        "tipo_chiusura": "sconto",
        "merge_copertura": True,
    }, timeout=30)
    assert r.status_code in (200, 201), r.text

    cop = _movs(session, tid, "copertura_titolo")
    assert len(cop) == 0, f"copertura deve essere rimossa dopo merge: {cop}"
    premio = _movs(session, tid, "incasso_premio")
    assert len(premio) == 1, f"Atteso 1 incasso_premio, trovati {len(premio)}"
    inc_mov = premio[0]
    # Verifica snapshot presente (nuovo flusso)
    assert inc_mov.get("coperture_assorbite"), "coperture_assorbite snapshot deve esistere nel merge path"

    # DELETE incasso
    _delete_mov(session, inc_mov["id"])

    t = _get_titolo(session, tid)
    assert t.get("stato") == "da_incassare", f"stato errato: {t.get('stato')}"
    assert t.get("titolo_coperto") is True, f"titolo deve tornare coperto, got {t.get('titolo_coperto')}"

    premio_after = _movs(session, tid, "incasso_premio")
    assert len(premio_after) == 0, f"nessun incasso_premio deve restare: {premio_after}"

    cop_after = _movs(session, tid, "copertura_titolo")
    assert len(cop_after) == 1, f"copertura_titolo deve essere ripristinata, trovate {len(cop_after)}"


# ---------------- Scenario B2 (legacy fallback) ----------------
def test_B2_legacy_merge_without_snapshot_reconstructs_copertura(session, compagnia_id, anagrafica_id):
    """Simula caso legacy: incasso_premio senza coperture_assorbite ma titolo.titolo_coperto=true.
    Usa l'update endpoint del movimento per rimuovere lo snapshot, se possibile. Altrimenti test skippato."""
    _, tid = _crea_polizza_titolo(session, compagnia_id, anagrafica_id, "B2")
    _cover(session, tid)
    r = session.post(f"{BASE_URL}/api/titoli/{tid}/incassa", json={
        "data_incasso": TODAY,
        "mezzo_pagamento": "bonifico",
        "importo_pagato": 200.00,
        "tipo_chiusura": "sconto",
        "merge_copertura": True,
    }, timeout=30)
    assert r.status_code in (200, 201), r.text
    premio = _movs(session, tid, "incasso_premio")
    assert len(premio) == 1
    inc_mov = premio[0]
    mid = inc_mov["id"]

    # Prova a rimuovere lo snapshot con PUT. Se non supportato, saltiamo.
    r = session.put(f"{BASE_URL}/api/contabilita/movimenti/{mid}",
                    json={"coperture_assorbite": []}, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"PUT movimento non consente clear snapshot (status={r.status_code}); fallback non testabile via API")

    # Verifica che lo snapshot sia stato rimosso/svuotato
    cur = [m for m in _movs(session, tid, "incasso_premio") if m["id"] == mid][0]
    if cur.get("coperture_assorbite"):
        pytest.skip("Snapshot ancora presente dopo PUT; fallback non testabile")

    # DELETE: fallback ricostruzione copertura dai dati del titolo
    _delete_mov(session, mid)
    t = _get_titolo(session, tid)
    assert t.get("stato") == "da_incassare"
    assert t.get("titolo_coperto") is True
    cop_after = _movs(session, tid, "copertura_titolo")
    assert len(cop_after) == 1, f"Fallback deve ricostruire 1 copertura, trovate {len(cop_after)}"
    assert float(cop_after[0].get("importo") or 0) == pytest.approx(200.00, rel=1e-3)


# ---------------- Scenario C (arretrato collected -> delete -> arretrato) ----------------
def test_C_incasso_of_arretrato_delete_reverts_to_arretrato(session, compagnia_id, anagrafica_id):
    _, tid = _crea_polizza_titolo(session, compagnia_id, anagrafica_id, "C")
    # Nessuna copertura: titolo è arretrato
    r = session.post(f"{BASE_URL}/api/titoli/{tid}/incassa", json={
        "data_incasso": TODAY,
        "mezzo_pagamento": "bonifico",
        "importo_pagato": 200.00,
        "tipo_chiusura": "sconto",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text

    premio = _movs(session, tid, "incasso_premio")
    assert len(premio) == 1, f"Atteso 1 incasso_premio: {premio}"
    assert not premio[0].get("coperture_assorbite"), "non deve esserci snapshot su arretrato"
    t_before = _get_titolo(session, tid)
    assert t_before.get("titolo_coperto") in (False, None)

    _delete_mov(session, premio[0]["id"])
    t = _get_titolo(session, tid)
    assert t.get("stato") == "da_incassare"
    assert t.get("titolo_coperto") in (False, None), f"deve restare non coperto, got {t.get('titolo_coperto')}"
    assert len(_movs(session, tid, "incasso_premio")) == 0
    assert len(_movs(session, tid, "copertura_titolo")) == 0, "nessuna copertura spuria"


# ---------------- Regression: incasso_coperto (no merge) ----------------
def test_R_incasso_coperto_delete_keeps_single_copertura(session, compagnia_id, anagrafica_id):
    _, tid = _crea_polizza_titolo(session, compagnia_id, anagrafica_id, "R")
    _cover(session, tid)
    # Incasso SENZA merge -> crea incasso_coperto, mantiene copertura
    r = session.post(f"{BASE_URL}/api/titoli/{tid}/incassa", json={
        "data_incasso": TODAY,
        "mezzo_pagamento": "bonifico",
        "importo_pagato": 200.00,
        "tipo_chiusura": "sconto",
    }, timeout=30)
    assert r.status_code in (200, 201), r.text

    cop = _movs(session, tid, "copertura_titolo")
    assert len(cop) == 1, f"copertura unica deve esistere: {cop}"
    coperto_rows = _movs(session, tid, "incasso_coperto")
    assert len(coperto_rows) == 1, f"atteso 1 incasso_coperto: {coperto_rows}"

    _delete_mov(session, coperto_rows[0]["id"])
    t = _get_titolo(session, tid)
    assert t.get("stato") == "da_incassare"
    assert t.get("titolo_coperto") is True, f"deve tornare coperto, got {t.get('titolo_coperto')}"
    # La copertura non deve essere duplicata
    cop_after = _movs(session, tid, "copertura_titolo")
    assert len(cop_after) == 1, f"copertura NON deve essere duplicata, trovate {len(cop_after)}"
    assert len(_movs(session, tid, "incasso_coperto")) == 0
