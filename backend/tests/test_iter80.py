"""Iterazione 80: report azienda PDF/Word, salva estratto conto, mezzo pagamento, delete diario."""
import os
import uuid
import requests
import pytest
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

AZIENDA_ID = "abe0cbf1-52a7-4d4b-b703-9a49ca89d924"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------ Report Azienda
def test_report_azienda_pdf(H):
    r = requests.get(f"{API}/anagrafiche/{AZIENDA_ID}/report-azienda/pdf", headers=H)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 4000
    assert r.content[:4] == b"%PDF"


def test_report_azienda_docx(H):
    r = requests.get(f"{API}/anagrafiche/{AZIENDA_ID}/report-azienda/docx", headers=H)
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "openxmlformats-officedocument.wordprocessingml" in ct
    # DOCX is a ZIP file starting with PK
    assert r.content[:2] == b"PK"


def test_report_azienda_pdf_400_su_persona_fisica(H):
    # Trova un'anagrafica persona fisica
    r = requests.get(f"{API}/anagrafiche?tipo=persona_fisica&limit=5", headers=H)
    if r.status_code != 200:
        r = requests.get(f"{API}/anagrafiche?limit=100", headers=H)
    lst = r.json()
    items = lst if isinstance(lst, list) else lst.get("items", [])
    pf = next((a for a in items if a.get("tipo") == "persona_fisica" or (not a.get("partita_iva") and a.get("codice_fiscale"))), None)
    assert pf, "Nessuna persona fisica trovata"
    r2 = requests.get(f"{API}/anagrafiche/{pf['id']}/report-azienda/pdf", headers=H)
    assert r2.status_code == 400, f"Atteso 400, ricevuto {r2.status_code}: {r2.text}"


# ------------------------------------------------------------ Estratto conto salva
def test_estratto_conto_salva_crea_allegato(H):
    r = requests.post(
        f"{API}/estratto-conto-contraente/salva",
        params={"contraente_id": AZIENDA_ID, "dal": "2026-05-01", "al": "2026-09-08"},
        headers=H,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("allegato_id")
    assert body.get("nome_file")

    # verifica allegato con categoria 'estratto_conto'
    r2 = requests.get(
        f"{API}/allegati",
        params={"entita_tipo": "anagrafica", "entita_id": AZIENDA_ID},
        headers=H,
    )
    assert r2.status_code == 200, r2.text
    allegs = r2.json() if isinstance(r2.json(), list) else r2.json().get("items", [])
    ec = [a for a in allegs if a.get("categoria") == "estratto_conto"]
    assert ec, "Nessun allegato categoria 'estratto_conto' trovato"


# ------------------------------------------------------------ Mezzo pagamento nella preview
def test_estratto_conto_preview_include_mezzo(H):
    r = requests.get(
        f"{API}/estratto-conto-contraente",
        params={"contraente_id": AZIENDA_ID, "dal": "2020-01-01", "al": "2030-12-31",
                "includi_pagamenti": "true"},
        headers=H,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    righe_pag = [r for r in data.get("righe", []) if r.get("pagamento")]
    # Almeno una riga con pagamento deve esistere per validare il campo mezzo
    if not righe_pag:
        pytest.skip("Nessuna riga con pagamento in questo range - test skip")
    # Il campo 'mezzo' deve essere presente (anche stringa vuota è tollerato ma
    # dovrebbe essere valorizzato se il titolo ha mezzo_pagamento o conto_cassa)
    for r0 in righe_pag:
        assert "mezzo" in r0["pagamento"], f"campo mezzo mancante: {r0['pagamento']}"


# ------------------------------------------------------------ DELETE diario
def test_delete_diario_cliente(H):
    # Inserisci una voce nel db.diario via API interna se disponibile;
    # in mancanza, si usa endpoint /api/diario POST se esiste per creare nota,
    # poi si prova a inserire direttamente in db attraverso l'endpoint di test.
    # Cerchiamo una voce già esistente nel diario dell'azienda.
    r = requests.get(f"{API}/anagrafiche/{AZIENDA_ID}/diario", headers=H)
    assert r.status_code == 200, r.text
    voci = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    # separa nota vs voce diario cliente (tipo != 'nota')
    voci_diario = [v for v in voci if v.get("tipo") != "nota" and v.get("id")]
    if not voci_diario:
        pytest.skip("Nessuna voce db.diario disponibile per il test")
    target = voci_diario[0]
    nid = target["id"]
    r2 = requests.delete(f"{API}/diario/{nid}", headers=H)
    assert r2.status_code == 200, f"DELETE /diario/{nid} fallita: {r2.status_code} {r2.text}"
    assert r2.json().get("ok") is True


def test_delete_diario_nota_personale(H):
    # Crea nota personale poi cancellala
    r = requests.post(
        f"{API}/diario",
        json={"titolo": "TEST_iter80 nota", "contenuto": "test",
              "anagrafica_id": AZIENDA_ID},
        headers=H,
    )
    assert r.status_code in (200, 201), r.text
    nid = r.json().get("id")
    assert nid
    r2 = requests.delete(f"{API}/diario/{nid}", headers=H)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("ok") is True
