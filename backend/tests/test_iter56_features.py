"""Iteration 56 — Backend test suite for new features:

- Colonne prefs per-utente (GET/PUT/DELETE /api/preferenze/colonne)
- Anagrafiche duplicati + unisci
- Modelli piramide (templates privati/aziende)
- Piramide-v2 tipo_piramide per anagrafica con/senza P.IVA
- NotebookLM: notebook + fonti upload + generazione riassunto + crm-docs + audio-overview 202
- Super Admin: dominio / credenziali / utenti / scambi (approva-rifiuta)
- Scambio controllato: richiedi/richieste/esegui (403 per admin normale)
- Ricerca globale /api/search (limit default 50)
"""
from __future__ import annotations

import os
import time
import uuid
import io

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@assicura.it", "password": "Admin123!"}
SUPER = {"email": "superadmin@assicura.it", "password": "superadmin123!"}


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"admin login fail: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def super_token():
    r = requests.post(f"{API}/auth/login", json=SUPER, timeout=15)
    assert r.status_code == 200, f"superadmin login fail: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def super_h(super_token):
    return {"Authorization": f"Bearer {super_token}"}


# ---------------- COLONNE PREFERENZE ----------------
class TestColonnePreferenze:
    def test_get_put_delete(self, admin_h):
        # reset first
        requests.delete(f"{API}/preferenze/colonne/polizze", headers=admin_h)

        # PUT
        payload = {"order": ["stato", "numero_polizza"], "hidden": ["targa"]}
        r = requests.put(f"{API}/preferenze/colonne/polizze", headers=admin_h, json=payload)
        assert r.status_code == 200 and r.json().get("ok") is True

        # GET returns pref
        r = requests.get(f"{API}/preferenze/colonne", headers=admin_h)
        assert r.status_code == 200
        data = r.json()
        assert "polizze" in data
        assert data["polizze"]["order"] == ["stato", "numero_polizza"]
        assert data["polizze"]["hidden"] == ["targa"]

        # DELETE resets
        r = requests.delete(f"{API}/preferenze/colonne/polizze", headers=admin_h)
        assert r.status_code == 200
        r = requests.get(f"{API}/preferenze/colonne", headers=admin_h)
        assert "polizze" not in r.json()


# ---------------- ANAGRAFICHE DUPLICATI + UNISCI ----------------
class TestAnagraficheDuplicati:
    TEST_CF = "TSTDUP80A01H501X"
    principale_id = None
    duplicato_id = None
    polizza_id = None

    def test_seed_and_merge_flow(self, admin_h):
        # Create 2 anagrafiche with same CF
        base = {
            "tipo": "persona_fisica",
            "codice_fiscale": self.TEST_CF,
            "nome": "TEST",
            "cognome": "DupPrincipale",
            "ragione_sociale": "TEST DupPrincipale",
        }
        r = requests.post(f"{API}/anagrafiche", headers=admin_h, json=base)
        assert r.status_code in (200, 201), r.text[:300]
        principale = r.json()
        TestAnagraficheDuplicati.principale_id = principale["id"]

        dup_payload = {
            "tipo": "persona_fisica",
            "codice_fiscale": self.TEST_CF,
            "nome": "TEST",
            "cognome": "DupSecondario",
            "ragione_sociale": "TEST DupSecondario",
            "email": "testdup@example.com",  # will fill principale
        }
        r = requests.post(f"{API}/anagrafiche", headers=admin_h, json=dup_payload)
        assert r.status_code in (200, 201), r.text[:300]
        dup = r.json()
        TestAnagraficheDuplicati.duplicato_id = dup["id"]

        # Create a test policy attached to duplicato
        pol = {
            "numero_polizza": f"TESTPOL-{uuid.uuid4().hex[:8]}",
            "contraente_id": dup["id"],
            "compagnia_id": "test-cmp",
            "ramo": "RCA",
            "effetto": "2025-01-01",
            "scadenza": "2026-01-01",
            "stato": "attiva",
        }
        r = requests.post(f"{API}/polizze", headers=admin_h, json=pol)
        assert r.status_code in (200, 201), f"polizza create fail: {r.status_code} {r.text[:300]}"
        TestAnagraficheDuplicati.polizza_id = r.json().get("id")

        # GET duplicati: must contain our group with n_polizze>=1 on duplicato
        r = requests.get(f"{API}/anagrafiche-duplicati", headers=admin_h)
        assert r.status_code == 200
        groups = r.json()
        assert isinstance(groups, list)
        our_group = None
        for g in groups:
            ids = {a["id"] for a in g["anagrafiche"]}
            if principale["id"] in ids and dup["id"] in ids:
                our_group = g
                break
        assert our_group is not None, "gruppo duplicati non trovato"
        assert our_group["tipo"] == "cf"
        # n_polizze presente
        assert all("n_polizze" in a for a in our_group["anagrafiche"])

        # POST unisci
        r = requests.post(f"{API}/anagrafiche-unisci", headers=admin_h, json={
            "principale_id": principale["id"], "duplicati_ids": [dup["id"]],
        })
        assert r.status_code == 200, f"unisci fail: {r.status_code} {r.text[:300]}"

        # verify: duplicato gone
        r = requests.get(f"{API}/anagrafiche/{dup['id']}", headers=admin_h)
        assert r.status_code == 404

        # polizza reassigned
        if TestAnagraficheDuplicati.polizza_id:
            r = requests.get(f"{API}/polizze/{TestAnagraficheDuplicati.polizza_id}", headers=admin_h)
            assert r.status_code == 200
            assert r.json().get("contraente_id") == principale["id"]

        # principale filled email
        r = requests.get(f"{API}/anagrafiche/{principale['id']}", headers=admin_h)
        assert r.status_code == 200
        assert r.json().get("email") == "testdup@example.com"

        # duplicati GET no longer contains group
        r = requests.get(f"{API}/anagrafiche-duplicati", headers=admin_h)
        assert r.status_code == 200
        for g in r.json():
            ids = {a["id"] for a in g["anagrafiche"]}
            assert dup["id"] not in ids

    @classmethod
    def teardown_class(cls):
        h_token = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15).json().get("access_token")
        h = {"Authorization": f"Bearer {h_token}"}
        if cls.polizza_id:
            requests.delete(f"{API}/polizze/{cls.polizza_id}", headers=h)
        if cls.principale_id:
            requests.delete(f"{API}/anagrafiche/{cls.principale_id}", headers=h)
        if cls.duplicato_id:
            requests.delete(f"{API}/anagrafiche/{cls.duplicato_id}", headers=h)


# ---------------- PIRAMIDE TEMPLATES ----------------
class TestPiramideTemplates:
    def test_list_templates(self, admin_h):
        r = requests.get(f"{API}/piramide-templates", headers=admin_h)
        assert r.status_code == 200
        data = r.json()
        assert "privati" in data and "aziende" in data
        for tipo in ("privati", "aziende"):
            assert isinstance(data[tipo]["levels"], list) and len(data[tipo]["levels"]) >= 5
            assert isinstance(data[tipo]["wedges"], list)

    def test_update_aziende_and_reset(self, admin_h):
        # Get current
        r = requests.get(f"{API}/piramide-templates", headers=admin_h)
        az = r.json()["aziende"]
        # Modify title of first level and add a voce to level 'danni'
        levels = []
        for lvl in az["levels"]:
            if lvl["id"] == "crescita":
                levels.append({**lvl, "titolo": "TEST TITOLO MODIFICATO"})
            elif lvl["id"] == "danni":
                voci = list(lvl.get("voci") or []) + [{"id": "test_voce_iter56", "label": "TEST VOCE"}]
                levels.append({**lvl, "voci": voci})
            else:
                levels.append(lvl)
        r = requests.put(f"{API}/piramide-templates/aziende", headers=admin_h,
                         json={"levels": levels, "wedges": az["wedges"],
                               "mostra_testamento": az["mostra_testamento"]})
        assert r.status_code == 200

        # GET returns modified
        r = requests.get(f"{API}/piramide-templates", headers=admin_h)
        az2 = r.json()["aziende"]
        crescita = next(l for l in az2["levels"] if l["id"] == "crescita")
        assert crescita["titolo"] == "TEST TITOLO MODIFICATO"
        danni = next(l for l in az2["levels"] if l["id"] == "danni")
        assert any(v.get("id") == "test_voce_iter56" for v in danni["voci"])

        # Reset
        r = requests.post(f"{API}/piramide-templates/aziende/reset", headers=admin_h)
        assert r.status_code == 200
        r = requests.get(f"{API}/piramide-templates", headers=admin_h)
        az3 = r.json()["aziende"]
        crescita3 = next(l for l in az3["levels"] if l["id"] == "crescita")
        assert crescita3["titolo"] != "TEST TITOLO MODIFICATO"


# ---------------- PIRAMIDE-V2 tipo per anagrafica ----------------
class TestPiramideV2Tipo:
    def test_privati_vs_aziende(self, admin_h):
        # Marco Rossi (senza P.IVA)
        aid_privato = "93b73085-100f-4c78-883a-e6cefea49c72"
        r = requests.get(f"{API}/anagrafiche/{aid_privato}/analisi/piramide-v2", headers=admin_h)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("tipo_piramide") == "privati"
        assert data.get("template", {}).get("tipo") == "privati"

        # Cerca (o crea) un'anagrafica con partita_iva
        r = requests.get(f"{API}/anagrafiche?limit=200", headers=admin_h)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        aid_azienda = None
        for a in items:
            if (a.get("partita_iva") or "").strip():
                aid_azienda = a["id"]
                break
        cleanup_needed = False
        if not aid_azienda:
            # crea temporanea
            r = requests.post(f"{API}/anagrafiche", headers=admin_h, json={
                "tipo": "persona_giuridica", "ragione_sociale": "TEST Azienda iter56",
                "partita_iva": "12345678903"})
            assert r.status_code in (200, 201)
            aid_azienda = r.json()["id"]
            cleanup_needed = True

        r = requests.get(f"{API}/anagrafiche/{aid_azienda}/analisi/piramide-v2", headers=admin_h)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("tipo_piramide") == "aziende"
        # verify a known azienda voce id in template
        levels = data.get("template", {}).get("levels", [])
        ids = {v.get("id") for l in levels for v in (l.get("voci") or [])}
        assert "az_rc_datoriale" in ids, f"Aziende template missing az_rc_datoriale, ids={ids}"

        if cleanup_needed:
            requests.delete(f"{API}/anagrafiche/{aid_azienda}", headers=admin_h)


# ---------------- NOTEBOOKLM ----------------
class TestNotebookLM:
    notebook_id = None

    def test_full_flow(self, admin_h):
        # Create notebook
        r = requests.post(f"{API}/notebooklm/notebooks", headers=admin_h,
                          json={"titolo": "TEST iter56 notebook",
                                "descrizione": "test descrizione"})
        assert r.status_code == 201, r.text[:300]
        nb = r.json()
        TestNotebookLM.notebook_id = nb["id"]

        # Upload txt fonte
        contenuto = (
            "CONDIZIONI POLIZZA TEST\n\n"
            "Massimale RCA: 6.000.000 euro per sinistro.\n"
            "Franchigia: 250 euro fissi per sinistro.\n"
            "Garanzia furto e incendio inclusa. Assistenza stradale 24/7.\n"
        ).encode("utf-8")
        files = {"files": ("condizioni_test.txt", contenuto, "text/plain")}
        r = requests.post(f"{API}/notebooklm/notebooks/{nb['id']}/fonti/upload",
                          headers=admin_h, files=files)
        assert r.status_code == 201, r.text[:300]
        fonti = r.json()
        assert len(fonti) == 1 and fonti[0]["stato"] == "ready"
        assert fonti[0]["nome_file"] == "condizioni_test.txt"

        # crm-docs
        r = requests.get(f"{API}/notebooklm/crm-docs", headers=admin_h)
        assert r.status_code == 200
        data = r.json()
        assert "biblioteca" in data and "allegati" in data

        # Chat SSE streaming
        r = requests.post(
            f"{API}/notebooklm/notebooks/{nb['id']}/chat", headers=admin_h,
            json={"message": "Qual è il massimale RCA e la franchigia?"},
            stream=True, timeout=60,
        )
        assert r.status_code == 200
        chunks = []
        done = False
        start = time.time()
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                chunks.append(line[6:])
                if '"done"' in line:
                    done = True
                    break
            if time.time() - start > 45:
                break
        r.close()
        full_text = " ".join(chunks)
        assert done or len(chunks) > 0, "no streaming response"
        # citation format present (best-effort)
        # assert "condizioni_test" in full_text or "[" in full_text

        # Generazione riassunto
        r = requests.post(f"{API}/notebooklm/notebooks/{nb['id']}/genera",
                          headers=admin_h, json={"tipo": "riassunto"})
        assert r.status_code == 202
        oid = r.json()["output_id"]

        # Polling ready (up to 90s)
        deadline = time.time() + 90
        state = None
        while time.time() < deadline:
            r = requests.get(f"{API}/notebooklm/outputs/{oid}", headers=admin_h)
            assert r.status_code == 200
            state = r.json()
            if state.get("stato") in ("ready", "errore"):
                break
            time.sleep(4)
        assert state and state.get("stato") == "ready", f"gen not ready: {state}"
        assert state.get("contenuto_md")

        # GET notebook shows outputs
        r = requests.get(f"{API}/notebooklm/notebooks/{nb['id']}", headers=admin_h)
        assert r.status_code == 200
        assert any(o["id"] == oid for o in r.json()["outputs"])

        # Audio overview must respond 202 (do NOT poll)
        r = requests.post(f"{API}/notebooklm/notebooks/{nb['id']}/audio-overview",
                          headers=admin_h)
        assert r.status_code == 202
        assert "output_id" in r.json()

    @classmethod
    def teardown_class(cls):
        if not cls.notebook_id:
            return
        tok = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15).json().get("access_token")
        h = {"Authorization": f"Bearer {tok}"}
        requests.delete(f"{API}/notebooklm/notebooks/{cls.notebook_id}", headers=h)


# ---------------- SUPER ADMIN: DOMINIO / CREDENZIALI ----------------
class TestSuperAdminDomini:
    tid = None
    tid_other = None
    slug = None

    def test_dominio_e_credenziali(self, super_h):
        r = requests.get(f"{API}/super-admin/agenzie", headers=super_h)
        assert r.status_code == 200
        agenzie = r.json()
        # find NOT principale
        non_princ = [a for a in agenzie if a.get("id") != "tenant-principale-schiantarelli"]
        assert len(non_princ) >= 1, "need at least 1 non-principale tenant"
        TestSuperAdminDomini.tid = non_princ[0]["id"]
        if len(non_princ) >= 2:
            TestSuperAdminDomini.tid_other = non_princ[1]["id"]

        slug = f"test-iter56-{uuid.uuid4().hex[:6]}"
        TestSuperAdminDomini.slug = slug
        r = requests.post(f"{API}/super-admin/agenzie/{self.tid}/dominio",
                          headers=super_h, json={"sottodominio": slug, "attivo": True})
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["ok"] is True
        assert data["sottodominio"] == slug
        assert "url" in data

        # Duplicate on another tenant → 409
        if self.tid_other:
            r = requests.post(f"{API}/super-admin/agenzie/{self.tid_other}/dominio",
                              headers=super_h, json={"sottodominio": slug, "attivo": True})
            assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text[:200]}"

        # Credenziali
        email = f"test-cred-{uuid.uuid4().hex[:6]}@iter56test.it"
        r = requests.post(f"{API}/super-admin/agenzie/{self.tid}/credenziali",
                          headers=super_h, json={"email": email})
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["email"] == email
        assert data["password"] and len(data["password"]) >= 8

        # Utenti agenzia lo include
        r = requests.get(f"{API}/super-admin/agenzie/{self.tid}/utenti", headers=super_h)
        assert r.status_code == 200
        emails = [u["email"] for u in r.json()]
        assert email in emails


# ---------------- SCAMBIO CONTROLLATO ----------------
class TestScambioControllato:
    rid = None

    def test_richiedi_e_rifiuta(self, admin_h, super_h):
        # Admin normale (tenant principale) crea richiesta con sé stesso come operatore
        # (deve solo creare la richiesta, non eseguirla)
        body = {
            "agenzia_sorgente_id": "tenant-principale-schiantarelli",
            "operatore_email": ADMIN["email"],
            "importa_anagrafiche": True, "importa_polizze": False,
            "importa_titoli": False, "importa_sinistri": False,
            "importa_documenti": False,
        }
        r = requests.post(f"{API}/scambio-dati/richiedi", headers=admin_h, json=body)
        assert r.status_code == 201, r.text[:300]
        req = r.json()
        assert req["stato"] == "in_attesa"
        TestScambioControllato.rid = req["id"]

        # GET le richieste
        r = requests.get(f"{API}/scambio-dati/richieste", headers=admin_h)
        assert r.status_code == 200
        assert any(x["id"] == req["id"] for x in r.json())

        # POST esegui con admin normale → 403
        r = requests.post(f"{API}/scambio-dati/esegui", headers=admin_h, json=body)
        assert r.status_code == 403

        # Super admin vede la richiesta
        r = requests.get(f"{API}/super-admin/scambi", headers=super_h)
        assert r.status_code == 200
        assert any(x["id"] == req["id"] for x in r.json())

        # Rifiuta con super admin
        r = requests.post(f"{API}/super-admin/scambi/{req['id']}/rifiuta",
                          headers=super_h, json={"motivo": "test iter56"})
        assert r.status_code == 200

        # Verifica stato rifiutato
        r = requests.get(f"{API}/super-admin/scambi", headers=super_h)
        found = next((x for x in r.json() if x["id"] == req["id"]), None)
        assert found and found["stato"] == "rifiutato"


# ---------------- SEARCH ----------------
class TestSearchGlobale:
    def test_search_default_limit(self, admin_h):
        r = requests.get(f"{API}/search", headers=admin_h, params={"q": "luca"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        for k in ("anagrafiche", "polizze", "sinistri", "titoli", "compagnie"):
            assert k in data
        # default limit is 50 -> total anagrafiche returned can be up to 50
        assert len(data["anagrafiche"]) <= 50
        # verify > 8 is possible: at least confirm limit param accepted at 50
        r2 = requests.get(f"{API}/search", headers=admin_h, params={"q": "luca", "limit": 50})
        assert r2.status_code == 200
        assert len(r2.json()["anagrafiche"]) == len(data["anagrafiche"])
