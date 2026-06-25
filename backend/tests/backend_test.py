"""End-to-end backend tests for Programma Assicurativo."""
import os
import io
import zipfile
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin": (os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")),
    "collaboratore": (os.environ.get("TEST_COLLAB_EMAIL", "collaboratore@assicura.it"), os.environ.get("TEST_COLLAB_PASSWORD", "Collab123!")),
    "dipendente": (os.environ.get("TEST_DIP_EMAIL", "dipendente@assicura.it"), os.environ.get("TEST_DIP_PASSWORD", "Dipendente123!")),
    "cliente": (os.environ.get("TEST_CLIENT_EMAIL", "cliente@assicura.it"), os.environ.get("TEST_CLIENT_PASSWORD", "Cliente123!")),
}


def login(role):
    email, pw = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"Login failed {role}: {r.status_code} {r.text}"
    j = r.json()
    token = j["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s, j["user"]


# ---------- AUTH ----------
@pytest.mark.parametrize("role", ["admin", "collaboratore", "dipendente", "cliente"])
def test_login_each_role(role):
    s, user = login(role)
    assert user["role"] == role
    r = s.get(f"{API}/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == CREDS[role][0]


def test_login_invalid():
    r = requests.post(f"{API}/auth/login", json={"email": "x@x.com", "password": "wrong"})
    assert r.status_code == 401


# ---------- DASHBOARD STATS ----------
def test_stats_dashboard_admin():
    s, _ = login("admin")
    r = s.get(f"{API}/stats/dashboard")
    assert r.status_code == 200
    d = r.json()
    for k in ["anagrafiche", "polizze_totali", "polizze_attive", "polizze_in_scadenza",
              "sinistri_aperti", "premi_anno_corrente", "polizze_per_ramo", "incassi_mensili"]:
        assert k in d, f"Missing key {k}"
    assert isinstance(d["polizze_per_ramo"], list)
    assert isinstance(d["incassi_mensili"], list)
    assert len(d["incassi_mensili"]) == 6


def test_stats_dashboard_cliente_restricted():
    s, user = login("cliente")
    r = s.get(f"{API}/stats/dashboard")
    assert r.status_code == 200
    d = r.json()
    # cliente vede solo se stesso/polizze proprie
    assert d["anagrafiche"] <= 1


# ---------- ANAGRAFICHE ----------
created = {}


def test_anagrafica_crud():
    s, _ = login("admin")
    payload = {"tipo_soggetto": "PF", "ragione_sociale": "TEST_Anagrafica QA",
               "codice_fiscale": "TSTQAA80A01H501Z", "email": "test_qa@example.com"}
    r = s.post(f"{API}/anagrafiche", json=payload)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    created["anagrafica_id"] = aid

    # GET single
    r2 = s.get(f"{API}/anagrafiche/{aid}")
    assert r2.status_code == 200
    assert r2.json()["ragione_sociale"] == "TEST_Anagrafica QA"

    # LIST with search
    r3 = s.get(f"{API}/anagrafiche", params={"q": "TEST_Anagrafica"})
    assert r3.status_code == 200
    assert any(a["id"] == aid for a in r3.json())


def test_anagrafica_relazioni_bidirezionali():
    s, _ = login("admin")
    aid = created["anagrafica_id"]
    # crea una seconda anagrafica
    r = s.post(f"{API}/anagrafiche", json={"tipo_soggetto": "PF",
               "ragione_sociale": "TEST_Parente QA", "codice_fiscale": "TSTQAP80A01H501Z"})
    assert r.status_code == 201
    bid = r.json()["id"]

    r = s.post(f"{API}/anagrafiche/{aid}/relazioni",
               json={"anagrafica_id": bid, "relazione": "coniuge", "relazione_inversa": "coniuge"})
    assert r.status_code == 200

    # verifica bidirezionale
    a = s.get(f"{API}/anagrafiche/{aid}").json()
    b = s.get(f"{API}/anagrafiche/{bid}").json()
    assert any(r["anagrafica_id"] == bid for r in a.get("parente_di", []))
    assert any(r["anagrafica_id"] == aid for r in b.get("parente_di", []))
    created["parente_id"] = bid


def test_intervista_save():
    s, _ = login("admin")
    aid = created["anagrafica_id"]
    r = s.post(f"{API}/anagrafiche/{aid}/interviste",
               json={"data_intervista": "2026-01-15", "note": "Test intervista",
                     "rischi_identificati": ["rc_auto"], "esigenze": {"famiglia": True}})
    assert r.status_code == 201, r.text
    r2 = s.get(f"{API}/anagrafiche/{aid}/interviste")
    assert r2.status_code == 200
    assert len(r2.json()) >= 1


# ---------- COMPAGNIE ----------
def test_compagnia_crud():
    s, _ = login("admin")
    r = s.post(f"{API}/compagnie",
               json={"codice": "TST", "ragione_sociale": "TEST_Compagnia QA"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    created["compagnia_id"] = cid
    r2 = s.get(f"{API}/compagnie")
    assert r2.status_code == 200
    assert any(c["id"] == cid for c in r2.json())


# ---------- POLIZZE + TITOLI + INCASSO ----------
def test_polizza_titolo_incasso_flow():
    s, _ = login("admin")
    aid = created["anagrafica_id"]
    cid = created["compagnia_id"]
    r = s.post(f"{API}/polizze", json={
        "numero_polizza": "TEST-POL-001", "ramo": "rc_auto",
        "contraente_id": aid, "compagnia_id": cid,
        "effetto": "2026-01-01", "scadenza": "2027-01-01",
        "premio_lordo": 600.0, "stato": "attiva",
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    created["polizza_id"] = pid

    # Titolo
    r = s.post(f"{API}/titoli", json={
        "polizza_id": pid, "tipo": "nuova",
        "effetto": "2026-01-01", "scadenza": "2027-01-01",
        "importo_lordo": 600.0, "stato": "da_incassare",
    })
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # Filtra titoli per stato
    r = s.get(f"{API}/titoli", params={"stato": "da_incassare"})
    assert r.status_code == 200
    assert any(t["id"] == tid for t in r.json())

    # Incassa
    r = s.post(f"{API}/titoli/{tid}/incassa",
               json={"data_incasso": "2026-01-15", "mezzo_pagamento": "bonifico"})
    assert r.status_code == 200, r.text
    mov = r.json()["movimento"]
    assert mov["tipo"] == "entrata"
    assert mov["importo"] == 600.0
    assert mov["polizza_id"] == pid

    # Verifica titolo incassato
    r = s.get(f"{API}/titoli", params={"polizza_id": pid})
    titolo = next(t for t in r.json() if t["id"] == tid)
    assert titolo["stato"] == "incassato"

    # Verifica movimento in prima nota
    r = s.get(f"{API}/contabilita/prima-nota")
    assert r.status_code == 200
    pn = r.json()
    assert pn["totale_entrate"] >= 600.0
    assert any(m["titolo_id"] == tid for m in pn["movimenti"])


# ---------- SINISTRI ----------
def test_sinistro_crud():
    s, _ = login("admin")
    pid = created["polizza_id"]
    r = s.post(f"{API}/sinistri", json={
        "numero_sinistro": "TEST-SIN-001", "polizza_id": pid,
        "compagnia_id": created["compagnia_id"], "contraente_id": created["anagrafica_id"],
        "data_avvenimento": "2026-01-10", "data_denuncia": "2026-01-11",
        "descrizione": "Test sinistro", "stato": "aperto", "riserva": 1500.0,
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r2 = s.get(f"{API}/sinistri", params={"polizza_id": pid})
    assert any(x["id"] == sid for x in r2.json())


# ---------- CONTABILITA ----------
def test_movimento_create_and_estratto_conto():
    s, _ = login("admin")
    aid = created["anagrafica_id"]
    r = s.post(f"{API}/contabilita/movimenti", json={
        "data_movimento": "2026-01-12", "tipo": "uscita", "categoria": "altro",
        "importo": 100.0, "descrizione": "TEST_Movimento", "anagrafica_id": aid,
    })
    assert r.status_code == 201, r.text
    r2 = s.get(f"{API}/contabilita/estratto-conto/{aid}")
    assert r2.status_code == 200
    ec = r2.json()
    assert ec["anagrafica"]["id"] == aid
    # saldo progressivo per ultimo movimento dovrebbe essere presente
    assert "saldo_finale" in ec


# ---------- IMPORT ANIA ----------
def test_import_ania_zip():
    s, _ = login("admin")
    zip_path = "/tmp/zip_extract/data.zip"
    if not os.path.exists(zip_path):
        pytest.skip("File ZIP ANIA non disponibile")
    # use multipart - need separate session without JSON content-type
    headers = {"Authorization": s.headers["Authorization"]}
    with open(zip_path, "rb") as f:
        r = requests.post(f"{API}/import/ania", files={"file": ("data.zip", f, "application/zip")},
                          headers=headers, timeout=60)
    assert r.status_code == 200, r.text
    log = r.json()
    assert log.get("stato") in ("completato", "completato_con_errori")
    assert "record_types_processati" in log

    # storico
    r = s.get(f"{API}/import/storico")
    assert r.status_code == 200
    assert any(x["id"] == log["id"] for x in r.json())


# ---------- INPS PENSIONI ----------
@pytest.mark.parametrize("tipo", ["invalidita", "inabilita", "superstite"])
def test_calcolo_pensione(tipo):
    s, _ = login("admin")
    payload = {
        "tipo_pensione": tipo,
        "settimane_contributive": 1500,
        "retribuzione_media_annua": 25000.0,
        "eta": 55,
        "percentuale_invalidita": 75.0 if tipo == "invalidita" else None,
        "numero_familiari": 2 if tipo == "superstite" else 0,
    }
    r = s.post(f"{API}/pensioni/calcola", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("pensione_lorda_mensile", 0) > 0, f"{tipo}: {d}"


# ---------- EMAIL ----------
def test_email_create_and_avvisi():
    s, _ = login("admin")
    r = s.post(f"{API}/email", json={
        "destinatario_email": "test@example.com",
        "oggetto": "TEST_Email", "corpo": "test", "stato": "bozza",
    })
    assert r.status_code == 201, r.text
    eid = r.json()["id"]

    # Invia (mock)
    r = s.post(f"{API}/email/{eid}/invia")
    assert r.status_code == 200

    # Genera avvisi scadenze (180 days range so it captures demo polizze)
    r = s.post(f"{API}/email/avvisi-scadenze", params={"giorni": 365})
    assert r.status_code == 200, r.text
    # may or may not create depending on demo data; just check structure
    assert "avvisi_creati" in r.json()


# ---------- ATTIVITA LOG ----------
def test_attivita_log_admin():
    s, _ = login("admin")
    r = s.get(f"{API}/attivita")
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    actions = {i["azione"] for i in items}
    assert "login" in actions or "create" in actions


def test_attivita_log_cliente_forbidden():
    s, _ = login("cliente")
    r = s.get(f"{API}/attivita")
    assert r.status_code == 403


# ---------- ROLE-BASED ACCESS ----------
def test_cliente_polizze_filtered():
    s, user = login("cliente")
    r = s.get(f"{API}/polizze")
    assert r.status_code == 200
    pols = r.json()
    # Tutte le polizze del cliente devono avere contraente_id = anagrafica_id del cliente
    if user.get("anagrafica_id"):
        for p in pols:
            assert p["contraente_id"] == user["anagrafica_id"], f"Polizza vista non sua: {p}"


def test_cliente_no_compagnie_create():
    s, _ = login("cliente")
    r = s.post(f"{API}/compagnie", json={"codice": "X", "ragione_sociale": "X"})
    assert r.status_code == 403


def test_cliente_no_importazione():
    s, _ = login("cliente")
    r = s.get(f"{API}/import/storico")
    assert r.status_code == 403


def test_dipendente_can_access_email_and_contabilita():
    s, _ = login("dipendente")
    assert s.get(f"{API}/email").status_code == 200
    assert s.get(f"{API}/contabilita/prima-nota").status_code == 200
    # ma non puo' importare
    assert s.get(f"{API}/import/storico").status_code == 403


# ---------- CLEANUP ----------
def test_cleanup():
    """Best effort cleanup. Non-critical."""
    s, _ = login("admin")
    for key in ["polizza_id", "compagnia_id"]:
        pass  # leave for now; not all endpoints have delete by id for new entities
    assert True
