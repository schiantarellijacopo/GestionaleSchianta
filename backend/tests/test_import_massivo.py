"""Test end-to-end Import Massivo Intelligente (multi-file, mapping AI, dedup)."""
import os
import time
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASSWORD = "Admin123!"

# Prefissi test univoci
ANAG_CSV = (
    "Ragione Sociale,Codice Fiscale,Partita IVA,Email,Cellulare\n"
    "ZZTEST ALFA SPA,,99000000011,,3331112222\n"
    "ZZTEST ROSSI TIZIO,ZZTTZO80A01H501Z,,,3339998877\n"
)
ANAG_CSV_FILL = (
    "Ragione Sociale,Codice Fiscale,Partita IVA,Email,Cellulare\n"
    "ZZTEST ALFA SPA,,99000000011,zztest.alfa@example.com,3331112222\n"
    "ZZTEST ROSSI TIZIO,ZZTTZO80A01H501Z,,zztest.rossi@example.com,3339998877\n"
)
POL_CSV = (
    "Numero Polizza,Compagnia,Contraente,Ramo,Effetto,Scadenza,Premio Lordo,Metodo Pagamento\n"
    "ZZTESTPOL001,Generali,ZZTEST ALFA SPA,RCA,2026-01-01,2027-01-01,1200.50,Bonifico\n"
    "ZZTESTPOL002,AXA,ZZTEST ROSSI TIZIO,Infortuni,2026-01-15,2027-01-15,450.00,RID\n"
)
TIT_CSV = (
    "Numero Polizza,Numero Titolo,Tipo,Effetto,Importo Lordo,Metodo Pagamento,Data Incasso\n"
    "ZZTESTPOL001,ZZTIT001,quietanza,2026-01-01,1200.50,Bonifico,2026-01-05\n"
)
SIN_CSV = (
    "Numero Sinistro,Numero Polizza,Data Avvenimento,Descrizione,Stato\n"
    "ZZSIN001,ZZTESTPOL001,2026-02-10,ZZTEST tamponamento,aperto\n"
)


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Login fallito: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


def _upload(headers, csvs):
    """csvs: list of (filename, csv_text). Ritorna JSON di sessione."""
    files = [("files", (fn, io.BytesIO(txt.encode("utf-8")), "text/csv")) for fn, txt in csvs]
    r = requests.post(f"{BASE_URL}/api/import-massivo/upload",
                      files=files, headers=headers, timeout=120)
    assert r.status_code == 200, f"upload fallito: {r.status_code} {r.text[:300]}"
    return r.json()


def _commit_and_wait(headers, sid, plan, timeout=180):
    r = requests.post(f"{BASE_URL}/api/import-massivo/{sid}/commit",
                      json={"plan": plan}, headers=headers, timeout=30)
    assert r.status_code == 200, f"commit fallito: {r.status_code} {r.text[:300]}"
    assert r.json().get("started") is True
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        s = requests.get(f"{BASE_URL}/api/import-massivo/{sid}/status",
                         headers=headers, timeout=15)
        assert s.status_code == 200
        last = s.json()
        if last.get("status") == "completato":
            return last
        time.sleep(1.5)
    pytest.fail(f"Timeout status: {last}")


# ------------------------------------------------------------------
# 1. UPLOAD multi-file (anagrafica + polizza)
# ------------------------------------------------------------------
def test_upload_multifile_ai_mapping(headers):
    sess = _upload(headers, [("zzanag.csv", ANAG_CSV), ("zzpol.csv", POL_CSV)])
    assert "id" in sess and len(sess["id"]) > 10
    assert len(sess["files"]) == 2
    by_name = {f["filename"]: f for f in sess["files"]}
    a = by_name["zzanag.csv"]
    p = by_name["zzpol.csv"]
    # entità rilevate
    assert a["entity"] == "anagrafica", f"anagrafica non rilevata: {a}"
    assert p["entity"] == "polizza", f"polizza non rilevata: {p}"
    # sorgente ai o euristica
    assert a["mapping_source"] in ("ai", "euristica")
    assert p["mapping_source"] in ("ai", "euristica")
    # mapping usa header ESATTI
    assert a["mapping"].get("Codice Fiscale") == "codice_fiscale"
    assert a["mapping"].get("Partita IVA") == "partita_iva"
    assert a["mapping"].get("Ragione Sociale") == "ragione_sociale"
    assert p["mapping"].get("Numero Polizza") == "numero_polizza"
    assert p["mapping"].get("Metodo Pagamento") == "mezzo_pagamento_preferito"
    assert a["total_rows"] == 2
    assert p["total_rows"] == 2
    assert a.get("preview") and p.get("preview")
    # salvo sid per il test successivo
    pytest.import_massivo_sid = sess["id"]
    pytest.import_massivo_files = sess["files"]


# ------------------------------------------------------------------
# 2. COMMIT + linking + dedup base
# ------------------------------------------------------------------
def test_commit_creates_and_links(headers):
    sid = pytest.import_massivo_sid
    plan = [{"file_index": f["file_index"], "entity": f["entity"], "mapping": f["mapping"]}
            for f in pytest.import_massivo_files]
    res = _commit_and_wait(headers, sid, plan)
    r = res.get("result") or {}
    assert (r.get("creati") or 0) >= 2, f"creati insufficienti: {r}"
    # verifica polizza collegata
    q = requests.get(f"{BASE_URL}/api/polizze?q=ZZTESTPOL", headers=headers, timeout=30)
    assert q.status_code == 200
    polizze = q.json() if isinstance(q.json(), list) else q.json().get("items") or []
    zz = [p for p in polizze if str(p.get("numero_polizza", "")).startswith("ZZTESTPOL")]
    assert len(zz) >= 2, f"polizze ZZTEST non trovate: {[p.get('numero_polizza') for p in polizze]}"
    for p in zz:
        assert p.get("contraente_id"), f"polizza {p.get('numero_polizza')} senza contraente_id"
        assert p.get("mezzo_pagamento_preferito"), f"polizza {p.get('numero_polizza')} senza mezzo_pagamento"
    # memorizza polizza id per il test titoli
    pol001 = next((p for p in zz if p.get("numero_polizza") == "ZZTESTPOL001"), None)
    assert pol001
    pytest.zz_polizza_id = pol001["id"]


# ------------------------------------------------------------------
# 3. DEDUP fill-missing (stessi CF/PIVA con Email aggiunta)
# ------------------------------------------------------------------
def test_dedup_fill_missing(headers):
    sess = _upload(headers, [("zzanag_fill.csv", ANAG_CSV_FILL)])
    f = sess["files"][0]
    assert f["entity"] == "anagrafica"
    plan = [{"file_index": f["file_index"], "entity": "anagrafica", "mapping": f["mapping"]}]
    res = _commit_and_wait(headers, sess["id"], plan)
    r = res.get("result") or {}
    # zero creati (dedup), almeno 1 aggiornato (email era vuota)
    assert (r.get("creati") or 0) == 0, f"attesi 0 creati (dedup), invece: {r}"
    assert (r.get("aggiornati") or 0) >= 1, f"atteso >=1 aggiornato: {r}"


# ------------------------------------------------------------------
# 4. TITOLI: collegamento polizza + mezzo_pagamento
# ------------------------------------------------------------------
def test_titoli_import(headers):
    sess = _upload(headers, [("zztit.csv", TIT_CSV)])
    f = sess["files"][0]
    assert f["entity"] == "titolo", f"entità titolo non rilevata: {f['entity']}"
    assert f["mapping"].get("Numero Polizza") == "numero_polizza"
    assert f["mapping"].get("Metodo Pagamento") == "mezzo_pagamento"
    plan = [{"file_index": f["file_index"], "entity": "titolo", "mapping": f["mapping"]}]
    res = _commit_and_wait(headers, sess["id"], plan)
    r = res.get("result") or {}
    assert (r.get("creati") or 0) >= 1, f"titolo non creato: {r}"
    # verifica titolo collegato
    pol_id = pytest.zz_polizza_id
    q = requests.get(f"{BASE_URL}/api/titoli?polizza_id={pol_id}", headers=headers, timeout=30)
    assert q.status_code == 200
    titoli = q.json() if isinstance(q.json(), list) else q.json().get("items") or []
    zz = [t for t in titoli if str(t.get("numero_titolo", "")).startswith("ZZTIT")]
    assert zz, f"nessun titolo ZZTIT: {titoli[:3]}"
    assert zz[0].get("polizza_id") == pol_id
    assert zz[0].get("mezzo_pagamento"), f"titolo senza mezzo_pagamento: {zz[0]}"


# ------------------------------------------------------------------
# 5. SINISTRI
# ------------------------------------------------------------------
def test_sinistro_import(headers):
    sess = _upload(headers, [("zzsin.csv", SIN_CSV)])
    f = sess["files"][0]
    assert f["entity"] == "sinistro", f"entità sinistro non rilevata: {f['entity']}"
    plan = [{"file_index": f["file_index"], "entity": "sinistro", "mapping": f["mapping"]}]
    res = _commit_and_wait(headers, sess["id"], plan)
    r = res.get("result") or {}
    assert (r.get("creati") or 0) >= 1, f"sinistro non creato: {r}"
    # verifica esistenza
    q = requests.get(f"{BASE_URL}/api/sinistri?q=ZZSIN", headers=headers, timeout=30)
    if q.status_code == 200:
        data = q.json() if isinstance(q.json(), list) else q.json().get("items") or []
        found = [s for s in data if s.get("numero_sinistro") == "ZZSIN001"]
        if found:
            assert found[0].get("polizza_id") == pytest.zz_polizza_id
