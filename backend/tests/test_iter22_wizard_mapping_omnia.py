"""Iter22 - Wizard Mapping OMNIA: backend coverage for unmapped tracking, save & apply."""
import io
import os
import time
import zipfile
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

# Unique markers so tests can run repeatedly without colliding
SUFFIX = str(int(time.time()))
COMP_CODE = f"TST{SUFFIX[-5:]}"        # unknown compagnia_exp
OP_CODE = f"OP{SUFFIX[-5:]}"           # unknown cod_operatore
RAMO_VAL = f"RamoTest{SUFFIX[-4:]}"    # unknown ramo
PROD_VAL = f"ProdTest{SUFFIX[-4:]}"    # unknown prodotto
ID_ANA = f"TESTANA{SUFFIX}"
ID_POL = f"TESTPOL{SUFFIX}"


def _csv(headers: list[str], rows: list[list[str]]) -> str:
    out = [";".join(headers)]
    for r in rows:
        out.append(";".join(r))
    return "\n".join(out) + "\n"


def _build_test_zip() -> bytes:
    rec10_headers = [
        "id_anagrafica_exp", "id_anag_inviante", "ragione_sociale",
        "codice_fiscale", "compagnia_exp", "compagnia_ania",
    ]
    rec10_rows = [[
        ID_ANA, ID_ANA, f"Cliente Test {SUFFIX}",
        f"CFTST{SUFFIX[-7:].upper()}", COMP_CODE, "999",
    ]]
    rec20_headers = [
        "id_polizza_exp", "numero_polizza_cmp", "id_anagrafica_exp",
        "compagnia_exp", "compagnia_ania", "ramo_share", "prodotto_cmp",
        "cod_operatore", "nome_operatore", "cod_stato_share",
        "effetto", "scadenza_originale", "lordo_totale", "netto_totale",
    ]
    rec20_rows = [[
        ID_POL, f"POL-{SUFFIX}", ID_ANA,
        COMP_CODE, "999", RAMO_VAL, PROD_VAL,
        OP_CODE, "Operatore Test", "A",
        "01/01/2026", "31/12/2026", "1000,00", "800,00",
    ]]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("rec10oweb.csv", _csv(rec10_headers, rec10_rows))
        zf.writestr("rec20oweb.csv", _csv(rec20_headers, rec20_rows))
    return buf.getvalue()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "admin@assicura.it", "password": "Admin123!"})
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text}")
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def import_log(admin_session):
    files = {"file": ("test.zip", _build_test_zip(), "application/zip")}
    r = admin_session.post(f"{API}/import/omnia", files=files)
    assert r.status_code == 200, f"import failed: {r.status_code} {r.text}"
    log = r.json()
    return log


# === Test 1: import returns ImportLog with entita_non_mappate populated ===
def test_import_omnia_returns_unmapped(import_log):
    assert import_log.get("stato") == "completato"
    enm = import_log.get("entita_non_mappate") or {}
    assert any(k in enm for k in ("compagnie", "rami", "prodotti", "collaboratori")), \
        f"no unmapped entities tracked: {enm}"
    flat = {item["valore"] for cat in enm.values() for item in cat}
    assert COMP_CODE in flat or OP_CODE in flat or RAMO_VAL in flat or PROD_VAL in flat, \
        f"none of the test markers tracked: {flat}"


# === Test 2: GET /api/import/unmapped returns groups + candidates ===
def test_get_unmapped_groups_and_candidates(import_log, admin_session):
    r = admin_session.get(f"{API}/import/unmapped")
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("compagnia", "ramo", "prodotto", "collaboratore", "garanzia"):
        assert k in body, f"missing group {k}"
    assert "candidates" in body
    for k in ("compagnia", "ramo", "prodotto", "collaboratore"):
        assert k in body["candidates"]
    # Our test values should appear
    comp_vals = {x["valore_flusso"] for x in body["compagnia"]}
    ramo_vals = {x["valore_flusso"] for x in body["ramo"]}
    coll_vals = {x["valore_flusso"] for x in body["collaboratore"]}
    prod_vals = {x["valore_flusso"] for x in body["prodotto"]}
    assert COMP_CODE in comp_vals, comp_vals
    assert RAMO_VAL in ramo_vals, ramo_vals
    assert OP_CODE in coll_vals, coll_vals
    assert PROD_VAL in prod_vals, prod_vals


# === Test 3: POST /api/import/mappings persists mapping ===
def test_save_mapping_persists(admin_session):
    # Get a compagnia candidate id
    body = admin_session.get(f"{API}/import/unmapped").json()
    comp_cands = body["candidates"]["compagnia"]
    if not comp_cands:
        pytest.skip("no compagnia candidates in DB")
    comp_id = comp_cands[0]["id"]
    r = admin_session.post(f"{API}/import/mappings", json={
        "tipo": "compagnia", "flusso": "omnia",
        "valore_flusso": COMP_CODE, "entita_id": comp_id,
    })
    assert r.status_code in (200, 201), r.text
    # Verify list now contains it with entita_id set
    lst = admin_session.get(f"{API}/import/mappings",
                            params={"tipo": "compagnia"}).json()
    found = [m for m in lst if m.get("valore_flusso") == COMP_CODE]
    assert found, "saved mapping not retrievable"
    assert found[0]["entita_id"] == comp_id


# === Test 4: POST /api/import/mappings/apply does back-fill ===
def test_apply_mappings_backfill(admin_session, import_log):
    # Ensure mappings for ramo (use first candidate ramo, or fallback string)
    body = admin_session.get(f"{API}/import/unmapped").json()
    ramo_cands = body["candidates"]["ramo"]
    coll_cands = body["candidates"]["collaboratore"]
    prod_cands = body["candidates"]["prodotto"]

    ramo_target = ramo_cands[0]["id"] if ramo_cands else "RC Auto"
    # Save ramo + collaboratore + prodotto mappings (compagnia saved in prior test)
    if not ramo_cands:
        # Create the ramo "RC Auto" so apply works
        admin_session.post(f"{API}/rami", json={"nome": "RC Auto"})
        ramo_target = "RC Auto"
    admin_session.post(f"{API}/import/mappings", json={
        "tipo": "ramo", "flusso": "omnia",
        "valore_flusso": RAMO_VAL, "entita_id": ramo_target,
    })
    if coll_cands:
        admin_session.post(f"{API}/import/mappings", json={
            "tipo": "collaboratore", "flusso": "omnia",
            "valore_flusso": OP_CODE, "entita_id": coll_cands[0]["id"],
        })
    if prod_cands:
        admin_session.post(f"{API}/import/mappings", json={
            "tipo": "prodotto", "flusso": "omnia",
            "valore_flusso": PROD_VAL, "entita_id": prod_cands[0]["id"],
        })

    r = admin_session.post(f"{API}/import/mappings/apply")
    assert r.status_code == 200, r.text
    summary = r.json()
    # Either summary or wrapped under "summary"
    s = summary.get("summary", summary)
    assert isinstance(s, dict)
    assert s.get("polizze_ramo", 0) >= 1 or s.get("polizze_compagnia", 0) >= 1, \
        f"back-fill did not update polizze: {s}"


# === Test 5: Re-import applies ramo mapping during import (not just back-fill) ===
def test_reimport_applies_ramo_mapping(admin_session):
    # Now re-import the same ZIP; the new polizza for ID_POL should already have ramo applied
    files = {"file": ("test.zip", _build_test_zip(), "application/zip")}
    r = admin_session.post(f"{API}/import/omnia", files=files)
    assert r.status_code == 200, r.text
    # Lookup polizza by id_polizza_exp via list (search filter)
    # Use /api/polizze with a query to find by numero
    found = None
    for params in (
        {"q": f"POL-{SUFFIX}"}, {"search": f"POL-{SUFFIX}"},
        {"numero_polizza": f"POL-{SUFFIX}"}, {},
    ):
        resp = admin_session.get(f"{API}/polizze", params=params)
        if resp.status_code != 200:
            continue
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items") or data.get("data") or []
        for p in items:
            if p.get("id_polizza_exp") == ID_POL or p.get("numero_polizza") == f"POL-{SUFFIX}":
                found = p
                break
        if found:
            break
    assert found, "polizza non trovata dopo re-import"
    # Ramo should have been mapped during import
    assert found.get("ramo") not in (None, RAMO_VAL, "VARIE"), \
        f"ramo non mappato durante import: {found.get('ramo')}"


# === Cleanup test data ===
def test_zz_cleanup(admin_session):
    # Best-effort cleanup of test mappings + polizza/anagrafica
    for tipo, val in [
        ("compagnia", COMP_CODE), ("ramo", RAMO_VAL),
        ("prodotto", PROD_VAL), ("collaboratore", OP_CODE),
    ]:
        try:
            lst = admin_session.get(f"{API}/import/mappings",
                                    params={"tipo": tipo}).json()
            for m in lst:
                if m.get("valore_flusso") == val and m.get("id"):
                    admin_session.delete(f"{API}/import/mappings/{m['id']}")
        except Exception:
            pass
