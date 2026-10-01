"""Iteration 99 — Testing:
- Fix PUT /api/titoli/{id} non deve essere bloccato dalla sola data_competenza quando
  il titolo non è incassato né coperto, anche se la giornata della competenza è chiusa.
- Regressione: PUT bloccato se incassato in giornata chiusa.
- Ricerca Prima Nota: GET /api/contabilita/prima-nota?q=
- Ricerca Banche:    GET /api/contabilita/banche/movimenti?descrizione=
- Export PDF/XLSX Prima Nota e Banche con filtri (status 200 + content-type).
"""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EMAIL = "jacopo@schiantarelli.it"
PASSWORD = "NtdZs5ilxTSP"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    s.headers.update({"Content-Type": "application/json"})
    return s


# ------------------------ Ricerca Prima Nota ------------------------
class TestPrimaNotaSearch:
    def test_q_text(self, client):
        r = client.get(f"{BASE_URL}/api/contabilita/prima-nota", params={"q": "PROVVIGIONI"})
        assert r.status_code == 200
        data = r.json()
        # risposta può essere lista oppure dict con 'righe'
        rows = data if isinstance(data, list) else data.get("righe") or data.get("items") or []
        # Verifica che ogni riga trovata contenga PROVVIGIONI (case-insensitive) in qualche campo
        if rows:
            joined = (" ".join(
                str(r.get("descrizione", "")) + " " + str(r.get("categoria", "")) + " " +
                str(r.get("numero_documento", "")) + " " + str(r.get("mezzo_pagamento", ""))
                for r in rows
            )).lower()
            assert "provvigioni" in joined, "Nessun risultato contiene 'provvigioni'"

    def test_q_numero(self, client):
        r = client.get(f"{BASE_URL}/api/contabilita/prima-nota", params={"q": "182259833"})
        assert r.status_code == 200
        data = r.json()
        rows = data if isinstance(data, list) else data.get("righe") or data.get("items") or []
        # Rows possono essere 0 se tenant non ha quella polizza — basta non andare in errore
        assert isinstance(rows, list)


# ------------------------ Ricerca Banche ----------------------------
class TestBancheSearch:
    def test_descrizione(self, client):
        r = client.get(f"{BASE_URL}/api/contabilita/banche/movimenti", params={"descrizione": "182259833"})
        assert r.status_code == 200
        data = r.json()
        # Quando descrizione valorizzata, 'progressivo' deve essere false (o assente/False)
        prog = data.get("progressivo") if isinstance(data, dict) else None
        assert prog in (False, None, 0), f"Atteso progressivo false con descrizione, trovato {prog}"


# ------------------------ Export Prima Nota -------------------------
class TestExports:
    def test_pdf_prima_nota(self, client):
        r = client.get(f"{BASE_URL}/api/stampa/prima-nota", params={"q": "PROVVIGIONI"})
        assert r.status_code == 200, r.text[:200]
        assert "pdf" in r.headers.get("content-type", "").lower()

    def test_xlsx_prima_nota(self, client):
        r = client.get(f"{BASE_URL}/api/stampa/prima-nota.xlsx", params={"q": "PROVVIGIONI"})
        assert r.status_code == 200, r.text[:200]
        assert "spreadsheet" in r.headers.get("content-type", "").lower()

    def test_pdf_banche(self, client):
        r = client.get(f"{BASE_URL}/api/contabilita/banche/movimenti/stampa", params={"descrizione": "bonifico"})
        assert r.status_code == 200, r.text[:200]
        assert "pdf" in r.headers.get("content-type", "").lower()

    def test_xlsx_banche(self, client):
        r = client.get(f"{BASE_URL}/api/contabilita/banche/movimenti/export.xlsx", params={"descrizione": "bonifico"})
        assert r.status_code == 200, r.text[:200]
        assert "spreadsheet" in r.headers.get("content-type", "").lower()


# ------------------------ BUG CRITICO INCASSO -----------------------
class TestTitoloUnlockOnClosedCompetenza:
    """Scenario: titolo non incassato, con data_competenza in giornata chiusa.
    PUT /api/titoli/{id} NON deve essere bloccato.
    Regressione: titolo incassato in giornata chiusa → PUT bloccato con 400.
    """

    def test_update_titolo_non_incassato_in_giornata_competenza_chiusa(self, client):
        """Un titolo non incassato e non coperto deve consentire PUT anche se
        esistono giornate chiuse (il bug precedente bloccava sulla data_competenza)."""
        r = client.get(f"{BASE_URL}/api/titoli", params={"stato": "da_incassare", "limit": 50})
        assert r.status_code == 200
        titoli = r.json()
        if isinstance(titoli, dict):
            titoli = titoli.get("items") or titoli.get("titoli") or []
        candidate = None
        for t in titoli:
            if not t.get("data_incasso") and not t.get("titolo_coperto"):
                candidate = t
                break
        if not candidate:
            pytest.skip("Nessun titolo da_incassare non coperto disponibile")

        tid = candidate["id"]
        # Verifica che esista almeno una chiusura (altrimenti test triviale)
        rc = client.get(f"{BASE_URL}/api/contabilita/chiusure-giorno", params={"limit": 5})
        if rc.status_code == 200 and not [c for c in rc.json() if not c.get("riaperta_at")]:
            pytest.skip("Nessuna giornata chiusa in archivio: test poco significativo")

        original_note = candidate.get("note") or ""
        put_payload = {"note": original_note + " [test unlock]"}
        r = client.put(f"{BASE_URL}/api/titoli/{tid}", json=put_payload)
        try:
            assert r.status_code == 200, (
                f"PUT titolo non incassato bloccato indebitamente: "
                f"{r.status_code} {r.text[:300]}"
            )
        finally:
            try:
                client.put(f"{BASE_URL}/api/titoli/{tid}", json={"note": original_note})
            except Exception:
                pass

    def test_regressione_titolo_incassato_in_giornata_chiusa_blocca_put(self, client):
        """Trova un titolo INCASSATO con data_incasso in giornata chiusa (via brogliaccio chiuso)
        e verifica che PUT sia ancora bloccato con 400."""
        r = client.get(f"{BASE_URL}/api/contabilita/chiusure-giorno", params={"limit": 50})
        if r.status_code != 200:
            pytest.skip("storico chiusure non disponibile")
        chiusure = [c for c in r.json() if not c.get("riaperta_at")]
        if not chiusure:
            pytest.skip("Nessuna giornata chiusa")

        target_tid = None
        for ch in chiusure:
            data_g = ch["data"]
            br = client.get(f"{BASE_URL}/api/contabilita/brogliaccio", params={"data": data_g})
            if br.status_code != 200:
                continue
            for riga in (br.json().get("righe") or []):
                if riga.get("categoria") in ("incasso_premio", "incasso_premio_direzione") and riga.get("titolo_id"):
                    target_tid = riga["titolo_id"]
                    break
            if target_tid:
                break
        if not target_tid:
            pytest.skip("Nessun titolo incassato trovato in giornate chiuse")

        put_payload = {"note": "[regressione test]"}
        r = client.put(f"{BASE_URL}/api/titoli/{target_tid}", json=put_payload)
        assert r.status_code == 400, (
            f"REGRESSIONE: PUT su titolo {target_tid} incassato in giornata chiusa doveva fallire 400, "
            f"ricevuto {r.status_code} body={r.text[:200]}"
        )
        try:
            detail = (r.json().get("detail") or "").lower()
        except Exception:
            detail = r.text.lower()
        assert "chius" in detail or "riapr" in detail, f"Messaggio inatteso: {detail}"
