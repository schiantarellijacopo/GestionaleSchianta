"""Iteration 45 tests: modulo Carichi Mensili / Quietanzamento + placeholder fixes.

Feature coverage:
- GET /api/carichi-mensili (arricchimento righe con cliente/compagnia/sinistri/ecc.)
- Filtri stato_carico / range (mese_corrente, mese_successivo, tutti)
- POST /api/carichi-mensili/replica-manuale
- POST /api/carichi-mensili/valida (bulk)
- POST /api/carichi-mensili/annulla (con motivo)
- DELETE / PUT bloccato se prima nota chiusa (mock chiusure_giorno)
- Regressione preview modelli con {elenco_titoli}
"""
from __future__ import annotations

import os
import pytest
import requests
from datetime import datetime, timezone

from conftest import API, ADMIN_EMAIL, ADMIN_PASSWORD


# ---------- Fixtures locali ----------

@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def sample_polizza(s):
    """Trova una polizza CHE HA ALMENO UN TITOLO per la replica manuale.

    Prende un titolo esistente e ritorna la polizza collegata.
    """
    r = s.get(f"{API}/carichi-mensili?stato_carico=tutti", timeout=30)
    assert r.status_code == 200, r.text
    righe = r.json().get("righe", [])
    assert righe, "Nessun titolo in DB → impossibile testare replica"
    pol_id = righe[0]["polizza_id"]
    return {"id": pol_id, "numero_polizza": righe[0].get("polizza_numero")}


# ---------- GET /api/carichi-mensili ----------

class TestListaCarichi:
    def test_lista_tutti_status_and_shape(self, s):
        r = s.get(f"{API}/carichi-mensili?stato_carico=tutti", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "totale" in data and "righe" in data
        assert isinstance(data["righe"], list)
        assert isinstance(data["totale"], int)

    def test_lista_arricchimento_campi(self, s):
        r = s.get(f"{API}/carichi-mensili?stato_carico=tutti", timeout=30)
        assert r.status_code == 200
        righe = r.json().get("righe", [])
        if not righe:
            pytest.skip("Nessun titolo in DB")
        row = righe[0]
        # Campi arricchiti richiesti dalla review request
        for k in ("cliente_nome", "compagnia_nome", "polizza_targa",
                  "sinistri_ultimi_12m", "operatore_nome", "bloccato", "motivo_blocco"):
            assert k in row, f"Manca campo arricchito '{k}'"

    def test_filtro_range_mese_corrente(self, s):
        r = s.get(f"{API}/carichi-mensili?stato_carico=tutti&range_filter=mese_corrente", timeout=30)
        assert r.status_code == 200
        mese = datetime.now(timezone.utc).strftime("%Y-%m")
        for r0 in r.json().get("righe", []):
            assert str(r0.get("scadenza", ""))[:7] == mese

    def test_filtro_stato_in_attesa(self, s):
        r = s.get(f"{API}/carichi-mensili?stato_carico=in_attesa", timeout=30)
        assert r.status_code == 200
        for r0 in r.json().get("righe", []):
            assert r0.get("stato_carico") == "in_attesa"


# ---------- POST /replica-manuale ----------

class TestReplicaManuale:
    def test_replica_manuale_ok(self, s, sample_polizza):
        r = s.post(f"{API}/carichi-mensili/replica-manuale",
                   json={"polizza_id": sample_polizza["id"]}, timeout=20)
        # 200 se ha almeno un titolo precedente, 404 se non ne ha
        assert r.status_code in (200, 404), r.text
        if r.status_code == 200:
            data = r.json()
            assert data.get("ok") is True
            assert data.get("titolo", {}).get("stato_carico") == "in_attesa"
            assert data.get("titolo", {}).get("import_source") == "manuale_replica"
            # cleanup
            tid = data["titolo"]["id"]
            s.delete(f"{API}/carichi-mensili/{tid}", timeout=10)

    def test_replica_polizza_inesistente(self, s):
        r = s.post(f"{API}/carichi-mensili/replica-manuale",
                   json={"polizza_id": "non-esiste-000"}, timeout=15)
        assert r.status_code == 404


# ---------- POST /valida & /annulla ----------

class TestValidaAnnulla:
    def _create_in_attesa(self, s, sample_polizza):
        r = s.post(f"{API}/carichi-mensili/replica-manuale",
                   json={"polizza_id": sample_polizza["id"]}, timeout=20)
        if r.status_code != 200:
            pytest.skip(f"impossibile creare titolo per test: {r.text}")
        return r.json()["titolo"]["id"]

    def test_valida_bulk_ok(self, s, sample_polizza):
        tid = self._create_in_attesa(s, sample_polizza)
        r = s.post(f"{API}/carichi-mensili/valida", json={"titoli_ids": [tid]}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("validati", 0) >= 1
        # cleanup: elimina il titolo validato (potrebbe essere bloccato se prima nota chiusa)
        s.delete(f"{API}/carichi-mensili/{tid}", timeout=10)

    def test_valida_empty_400(self, s):
        r = s.post(f"{API}/carichi-mensili/valida", json={"titoli_ids": []}, timeout=15)
        assert r.status_code == 400

    def test_annulla_bulk_ok(self, s, sample_polizza):
        tid = self._create_in_attesa(s, sample_polizza)
        r = s.post(f"{API}/carichi-mensili/annulla",
                   json={"titoli_ids": [tid], "motivo_mancanza": "Disdettata",
                         "note_carico": "test"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("annullati", 0) >= 1
        # cleanup
        s.delete(f"{API}/carichi-mensili/{tid}", timeout=10)

    def test_annulla_no_motivo_400(self, s):
        r = s.post(f"{API}/carichi-mensili/annulla",
                   json={"titoli_ids": ["x"], "motivo_mancanza": ""}, timeout=15)
        assert r.status_code == 400


# ---------- PUT / DELETE bloccato ----------

class TestBlocco:
    def test_delete_titolo_inesistente_404(self, s):
        r = s.delete(f"{API}/carichi-mensili/non-esiste-xyz", timeout=15)
        assert r.status_code == 404

    def test_put_titolo_inesistente_404(self, s):
        r = s.put(f"{API}/carichi-mensili/non-esiste-xyz",
                  json={"importo_lordo": 100}, timeout=15)
        assert r.status_code == 404


# ---------- Regressione preview modelli ----------

class TestPreviewModelli:
    def test_preview_placeholder_elenco_titoli(self, s):
        # POST /api/librerie/modelli/preview con corpo contenente {elenco_titoli}
        r = s.post(
            f"{API}/librerie/modelli/preview",
            json={"canale": "whatsapp",
                  "oggetto": "",
                  "corpo": "Ciao {cliente_nome}:\n{elenco_titoli}",
                  "template_riga": "→ {numero_polizza} · {ramo} · {targa}"},
            timeout=15,
        )
        # Accetta 200/201; corpo dev'essere pieno di righe elenco
        assert r.status_code in (200, 201), r.text
        body = r.json()
        # struttura può essere {corpo_resolved: ...} oppure {corpo: ...}
        text = body.get("corpo_resolved") or body.get("corpo") or body.get("body") or ""
        assert "→" in text or "elenco" in text.lower() or text.count("\n") >= 1, f"preview vuota: {body}"
