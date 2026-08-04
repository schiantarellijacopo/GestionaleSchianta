"""Iteration 38 backend tests:

1. POST /api/titoli/{id}/incassa with mezzo_pagamento='PAGAMENTO IN DIREZIONE'
2. GET /api/contabilita/brogliaccio → direzione/ritenuta/rappel + no duplicate rows
3. POST /api/contabilita/chiusura-giorno with is_direzione movements
4. GET /api/librerie/banche → is_incassi_direzione field
5. POST /api/super-admin/agenzie/{tid}/reset-dati (with password custode + backup)
6. GET /api/super-admin/backups (list + download)
7. POST /api/copilot/chat with lowercase multi-word Italian name
"""

import os
import pytest
import requests
from datetime import datetime, timedelta

from conftest import API, ADMIN_EMAIL, ADMIN_PASSWORD

SUPER_ADMIN_EMAIL = os.environ.get("TEST_SUPERADMIN_EMAIL", "superadmin@assicura.it")
SUPER_ADMIN_PASSWORD = os.environ.get("TEST_SUPERADMIN_PASSWORD", "Superadmin123!")


# ---------- helpers ----------
def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def super_admin_token():
    # Try both spellings noted in review request vs test_credentials.md
    for pw in [SUPER_ADMIN_PASSWORD, "superadmin123!", "Superadmin123!"]:
        r = requests.post(f"{API}/auth/login",
                          json={"email": SUPER_ADMIN_EMAIL, "password": pw}, timeout=15)
        if r.status_code == 200:
            return r.json()["access_token"]
    pytest.skip(f"Super admin login failed with all candidates")


# =====================================================================
# 1) INCASSA titolo con PAGAMENTO IN DIREZIONE
# =====================================================================
class TestIncassaDirezione:
    def _get_or_create_titolo(self, tok):
        """Find any titolo da_incassare, else create a full anagrafica+polizza+titolo."""
        h = _hdr(tok)
        # First: try to find existing da_incassare
        r = requests.get(f"{API}/titoli?stato=da_incassare&limit=5", headers=h, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            if items:
                return items[0]

        # Fallback: create everything
        # anagrafica
        an = requests.post(f"{API}/anagrafiche", headers=h, json={
            "tipo": "privato",
            "nome": "TEST_DIR", "cognome": "Cliente",
            "codice_fiscale": "TESTDR90A01H501Z"
        }, timeout=15)
        assert an.status_code in (200, 201), f"anagrafica: {an.status_code} {an.text}"
        ana_id = an.json()["id"]

        # compagnia (pick any)
        cs = requests.get(f"{API}/compagnie", headers=h, timeout=15).json()
        cs = cs if isinstance(cs, list) else cs.get("items", [])
        assert cs, "No compagnie in system"
        comp_id = cs[0]["id"]

        # polizza
        oggi = datetime.utcnow().strftime("%Y-%m-%d")
        fine = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%d")
        pol = requests.post(f"{API}/polizze", headers=h, json={
            "numero_polizza": f"TEST-DIR-{int(datetime.utcnow().timestamp())}",
            "contraente_id": ana_id,
            "compagnia_id": comp_id,
            "ramo": "auto",
            "data_effetto": oggi,
            "data_scadenza": fine,
            "premio_lordo": 500.0,
            "provvigioni": 50.0,
        }, timeout=15)
        assert pol.status_code in (200, 201), f"polizza: {pol.status_code} {pol.text}"
        pol_id = pol.json()["id"]

        # titolo
        tit = requests.post(f"{API}/titoli", headers=h, json={
            "polizza_id": pol_id,
            "tipo": "nuova",
            "data_effetto": oggi,
            "data_scadenza": fine,
            "importo_lordo": 500.0,
            "provvigioni": 50.0,
        }, timeout=15)
        assert tit.status_code in (200, 201), f"titolo: {tit.status_code} {tit.text}"
        return tit.json()

    def test_incassa_direzione_creates_single_movimento(self, admin_token):
        h = _hdr(admin_token)
        titolo = self._get_or_create_titolo(admin_token)
        tid = titolo["id"]
        data_incasso = datetime.utcnow().strftime("%Y-%m-%d")

        # Ensure the day is not closed
        requests.post(f"{API}/contabilita/chiusura-giorno/riapri", headers=h,
                      json={"data": data_incasso}, timeout=15)

        r = requests.post(f"{API}/titoli/{tid}/incassa", headers=h, json={
            "data_incasso": data_incasso,
            "mezzo_pagamento": "PAGAMENTO IN DIREZIONE",
        }, timeout=30)
        assert r.status_code == 200, f"incassa: {r.status_code} {r.text}"

        # Verify: EXACTLY ONE movimento for this titolo, with expected values
        # Query all movimenti of that day for that titolo via brogliaccio
        b = requests.get(f"{API}/contabilita/brogliaccio?data={data_incasso}",
                         headers=h, timeout=30)
        assert b.status_code == 200, f"brogliaccio: {b.status_code} {b.text}"
        payload = b.json()
        righe = [r for r in payload["righe"] if r.get("descrizione", "").find(tid[:8]) >= 0
                 or r.get("numero_polizza") == titolo.get("numero_polizza")]
        # More reliable: get movimenti for titolo_id via admin endpoint
        # try /api/contabilita/movimenti?titolo_id=
        mv = requests.get(f"{API}/contabilita/movimenti?titolo_id={tid}",
                          headers=h, timeout=15)
        if mv.status_code == 200:
            movs = mv.json() if isinstance(mv.json(), list) else mv.json().get("items", [])
            movs = [m for m in movs if m.get("titolo_id") == tid]
            assert len(movs) == 1, f"Expected 1 movimento, got {len(movs)}: {movs}"
            m = movs[0]
            assert m["is_direzione"] is True, f"is_direzione flag not set: {m}"
            assert m["categoria"] == "incasso_premio_direzione", m.get("categoria")
            assert m["importo"] == 0.0, f"importo must be 0, got {m['importo']}"
            assert m.get("conto_cassa_id") in (None, ""), f"conto_cassa_id must be None: {m.get('conto_cassa_id')}"
            assert float(m.get("provvigioni") or 0) > 0, "provvigioni must be preserved"


# =====================================================================
# 2) BROGLIACCIO: verify no duplicate rows for direzione titolo
# =====================================================================
class TestBrogliaccioDirezione:
    def test_brogliaccio_has_direzione_fields(self, admin_token):
        h = _hdr(admin_token)
        data = datetime.utcnow().strftime("%Y-%m-%d")
        r = requests.get(f"{API}/contabilita/brogliaccio?data={data}", headers=h, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        payload = r.json()
        tot = payload["totali_giornata"]
        # New fields
        for k in ("direzione", "ritenuta", "rappel"):
            assert k in tot, f"totali_giornata missing '{k}': {list(tot.keys())}"

        # Every riga should have direzione/ritenuta/rappel keys
        for riga in payload["righe"]:
            for k in ("direzione", "ritenuta", "rappel", "is_direzione", "per_conto"):
                assert k in riga, f"riga missing '{k}': {list(riga.keys())}"

    def test_brogliaccio_no_duplicate_for_direzione_titolo(self, admin_token):
        """For each titolo that has is_direzione, expect exactly one riga."""
        h = _hdr(admin_token)
        data = datetime.utcnow().strftime("%Y-%m-%d")
        payload = requests.get(f"{API}/contabilita/brogliaccio?data={data}",
                               headers=h, timeout=30).json()
        # group by numero_polizza + categoria on rows where is_direzione=True
        by_key = {}
        for riga in payload["righe"]:
            if riga.get("is_direzione"):
                key = (riga.get("numero_polizza"), riga.get("categoria"))
                by_key.setdefault(key, []).append(riga)
        for key, group in by_key.items():
            assert len(group) == 1, f"Duplicate direzione rows for {key}: {len(group)} rows"

    def test_direzione_row_semantics(self, admin_token):
        """Direzione rows: totale=0, spese=0, per_conto={}, provv==direzione, saldo=-provv."""
        h = _hdr(admin_token)
        data = datetime.utcnow().strftime("%Y-%m-%d")
        payload = requests.get(f"{API}/contabilita/brogliaccio?data={data}",
                               headers=h, timeout=30).json()
        found = False
        for riga in payload["righe"]:
            if not riga.get("is_direzione"):
                continue
            found = True
            assert riga["totale"] == 0, f"totale must be 0: {riga}"
            assert riga["spese"] == 0, f"spese must be 0: {riga}"
            assert riga["per_conto"] == {} or all(v == 0 for v in riga["per_conto"].values()), \
                f"per_conto must be empty: {riga['per_conto']}"
            assert abs(riga["provv"] - riga["direzione"]) < 1e-6, \
                f"provv({riga['provv']}) must equal direzione({riga['direzione']})"
            assert abs(riga["saldo"] + riga["provv"]) < 1e-6, \
                f"saldo must equal -provv: saldo={riga['saldo']} provv={riga['provv']}"
        if not found:
            pytest.skip("No direzione row on today (skip semantics check)")


# =====================================================================
# 3) CHIUSURA GIORNO with direzione movements
# =====================================================================
class TestChiusuraDirezione:
    def test_chiusura_giorno_with_direzione(self, admin_token):
        h = _hdr(admin_token)
        data = datetime.utcnow().strftime("%Y-%m-%d")
        # Try to close current day (may already be closed)
        # First: reopen if closed
        requests.post(f"{API}/contabilita/chiusura-giorno/riapri", headers=h,
                      json={"data": data}, timeout=15)

        r = requests.post(f"{API}/contabilita/chiusura-giorno", headers=h,
                          json={"data": data}, timeout=60)
        # Accept: 201 close ok, 400 "no movimenti" if nothing to close
        assert r.status_code in (200, 201, 400), f"{r.status_code} {r.text}"
        if r.status_code == 400:
            assert "Nessun movimento" in r.text or "già chiusa" in r.text
        else:
            j = r.json()
            assert j.get("data") == data
            # Reopen it after
            cid = j.get("id")
            if cid:
                requests.post(f"{API}/contabilita/chiusura-giorno/riapri", headers=h,
                              json={"data": data}, timeout=15)


# =====================================================================
# 4) LIBRERIE BANCHE with is_incassi_direzione
# =====================================================================
class TestBancheDirezione:
    def test_create_banca_with_is_incassi_direzione(self, admin_token):
        h = _hdr(admin_token)
        payload = {
            "nome": f"TEST_BANCA_DIR_{int(datetime.utcnow().timestamp())}",
            "is_incassi_direzione": True,
        }
        r = requests.post(f"{API}/librerie/banche", headers=h, json=payload, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        created = r.json()
        assert created.get("is_incassi_direzione") is True, created
        bid = created["id"]

        # List → verify present
        rl = requests.get(f"{API}/librerie/banche", headers=h, timeout=15)
        assert rl.status_code == 200
        found = next((b for b in rl.json() if b.get("id") == bid), None)
        assert found is not None, "Created banca not in list"
        assert found.get("is_incassi_direzione") is True

        # Cleanup
        requests.delete(f"{API}/librerie/banche/{bid}", headers=h, timeout=15)


# =====================================================================
# 5) SUPER ADMIN reset-dati + backup
# =====================================================================
class TestSuperAdminResetBackup:
    @pytest.fixture(scope="class")
    def throwaway_tenant_id(self, super_admin_token):
        """Create a throwaway tenant for reset tests."""
        h = _hdr(super_admin_token)
        payload = {
            "ragione_sociale": f"TEST_RESET_TENANT_{int(datetime.utcnow().timestamp())}",
            "email_admin": f"reset_{int(datetime.utcnow().timestamp())}@test.example.com",
            "seed_type": "clean",
        }
        r = requests.post(f"{API}/super-admin/agenzie", headers=h, json=payload, timeout=30)
        if r.status_code not in (200, 201):
            pytest.skip(f"Cannot create throwaway tenant: {r.status_code} {r.text}")
        j = r.json()
        tid = j.get("tenant", {}).get("id") or j.get("id") or j.get("tenant_id")
        assert tid, f"No tenant id in response: {j}"
        yield tid, payload["ragione_sociale"]
        # cleanup: delete tenant (soft-delete)
        try:
            requests.delete(f"{API}/super-admin/agenzie/{tid}", headers=h, timeout=15)
        except Exception:
            pass

    def test_reset_wrong_password(self, super_admin_token, throwaway_tenant_id):
        tid, rs = throwaway_tenant_id
        h = _hdr(super_admin_token)
        r = requests.post(f"{API}/super-admin/agenzie/{tid}/reset-dati", headers=h, json={
            "password_custode": "WRONG_PASSWORD",
            "conferma_ragione_sociale": rs,
        }, timeout=30)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_reset_wrong_ragione_sociale(self, super_admin_token, throwaway_tenant_id):
        tid, _ = throwaway_tenant_id
        h = _hdr(super_admin_token)
        r = requests.post(f"{API}/super-admin/agenzie/{tid}/reset-dati", headers=h, json={
            "password_custode": "Cazzimiei91!",
            "conferma_ragione_sociale": "WRONG_NAME_MISMATCH",
        }, timeout=30)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"

    def test_reset_success_with_backup(self, super_admin_token, throwaway_tenant_id):
        tid, rs = throwaway_tenant_id
        h = _hdr(super_admin_token)
        r = requests.post(f"{API}/super-admin/agenzie/{tid}/reset-dati", headers=h, json={
            "password_custode": "Cazzimiei91!",
            "conferma_ragione_sociale": rs,
        }, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        j = r.json()
        assert j.get("ok") is True
        assert "backup" in j
        bak = j["backup"]
        assert "filename" in bak and bak["filename"].endswith(".json.gz")
        assert isinstance(bak.get("size_kb"), (int, float))
        assert bak.get("download_url", "").startswith("/api/super-admin/backups/")

    def test_list_backups(self, super_admin_token):
        h = _hdr(super_admin_token)
        r = requests.get(f"{API}/super-admin/backups", headers=h, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        files = r.json()
        assert isinstance(files, list)
        # If any backups exist, verify structure
        if files:
            f0 = files[0]
            for k in ("filename", "size_kb", "created_at", "download_url"):
                assert k in f0, f"backup missing key {k}: {f0}"

    def test_download_backup(self, super_admin_token):
        h = _hdr(super_admin_token)
        files = requests.get(f"{API}/super-admin/backups", headers=h, timeout=15).json()
        if not files:
            pytest.skip("No backups to download")
        fn = files[0]["filename"]
        r = requests.get(f"{API}/super-admin/backups/{fn}", headers=h, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        # Should be gzipped content
        assert r.content[:2] == b"\x1f\x8b", "Response is not gzipped"


# =====================================================================
# 6) COPILOT with lowercase multi-word name
# =====================================================================
class TestCopilotLowercaseName:
    def test_copilot_lowercase_multiword_name(self, admin_token):
        h = _hdr(admin_token)
        # Pick any existing anagrafica to build a realistic query
        an = requests.get(f"{API}/anagrafiche?limit=5", headers=h, timeout=15).json()
        items = an if isinstance(an, list) else an.get("items", [])
        if not items:
            pytest.skip("No anagrafiche in system")
        # Use the first PF (with nome + cognome) if any
        target = next((a for a in items if a.get("nome") and a.get("cognome")), None)
        if not target:
            pytest.skip("No PF anagrafica available for lowercase-multiword test")
        cognome = target["cognome"].lower()
        nome = target["nome"].lower()
        msg = f"mi trovi la polizza di {cognome} {nome}"

        r = requests.post(f"{API}/copilot/chat", headers=h,
                          json={"message": msg}, timeout=90)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        j = r.json()
        assert "answer" in j
        # The answer or context should reference the client — accept either
        answer = (j.get("answer") or "").lower()
        # Should NOT be an "non trovato" style error at minimum for existing name
        # (we can't guarantee polizza exists — but at least anagrafica found)
        # Ensure no crash: dispatcher processed the message
        assert len(answer) > 0
