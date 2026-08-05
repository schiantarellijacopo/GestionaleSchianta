"""Iter42 - Test integrazione Gestione Modelli con Alert & Automazioni + Avvisi.

Verifica:
- CRUD /api/librerie/modelli con auto-detect placeholders
- Endpoint /preview (rendering con dati fittizi)
- Endpoint /genera formato pdf/docx (con logo agenzia)
- AlertRule/AlertRulePatch accettano template_modello_id
- dispatch_rule usa modello_libreria con precedenza sui template_oggetto/corpo
- /avvisi/whatsapp-invia-bulk-titoli accetta modello_id (senza inviare WA reali)
- send_text_via_evolution normalizza numero IT 10 cifre → prefisso 39
- Regressione endpoints esistenti
"""
import os
import re
import uuid
import pytest
import requests

# Load backend/.env so in-process imports of `database` find MONGO_URL
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env", override=False)
except Exception:
    pass

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PWD = "Admin123!"


# --------------- fixtures ---------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=15)
    assert r.status_code == 200, f"Login admin fallito: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"Token mancante: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def created_ids():
    ids = {"modelli": [], "rules": []}
    yield ids
    # teardown - cleanup
    hdrs = {}
    try:
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=15)
        if r.status_code == 200:
            tok = r.json().get("token") or r.json().get("access_token")
            hdrs = {"Authorization": f"Bearer {tok}"}
    except Exception:
        pass
    for mid in ids["modelli"]:
        try:
            requests.delete(f"{API}/librerie/modelli/{mid}", headers=hdrs, timeout=10)
        except Exception:
            pass
    for rid in ids["rules"]:
        try:
            requests.delete(f"{API}/alert-rules/{rid}", headers=hdrs, timeout=10)
        except Exception:
            pass


# --------------- Modelli CRUD ---------------
class TestModelliCRUD:
    def test_list_default_seed(self, admin_headers):
        r = requests.get(f"{API}/librerie/modelli", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        tipi = {m.get("tipo") for m in data}
        # seed_default_models deve avere creato almeno questi
        for expected in ("email", "whatsapp", "sms", "pdf_avviso", "pdf_lettera_abbuono"):
            assert expected in tipi, f"Modello seed '{expected}' mancante. Trovati: {tipi}"

    def test_create_with_autodetect_placeholders(self, admin_headers, created_ids):
        payload = {
            "tipo": "email",
            "nome": "TEST_iter42_autodetect",
            "oggetto": "Ciao {cliente_nome} — polizza {numero_polizza}",
            "corpo": "Il tuo premio è {premio_lordo}, scadenza {data_scadenza}.",
            "categoria": "test",
            "default": False,
            "attivo": True,
        }
        r = requests.post(f"{API}/librerie/modelli", headers=admin_headers, json=payload, timeout=15)
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["nome"] == payload["nome"]
        assert doc["tipo"] == "email"
        # auto-detect deve contenere i 4 placeholder
        phs = set(doc.get("placeholders") or [])
        for expected in {"cliente_nome", "numero_polizza", "premio_lordo", "data_scadenza"}:
            assert expected in phs, f"placeholder {expected} non rilevato: {phs}"
        assert "id" in doc
        created_ids["modelli"].append(doc["id"])

    def test_update_recalcs_placeholders(self, admin_headers, created_ids):
        # crea modello base
        r = requests.post(
            f"{API}/librerie/modelli", headers=admin_headers,
            json={"tipo": "sms", "nome": "TEST_iter42_upd", "corpo": "Hi {cliente_nome}"}, timeout=15,
        )
        assert r.status_code == 201, r.text
        mid = r.json()["id"]
        created_ids["modelli"].append(mid)
        # update con nuovi placeholders
        upd = {"tipo": "sms", "nome": "TEST_iter42_upd", "corpo": "Nuovo {ramo} {totale}"}
        r2 = requests.put(f"{API}/librerie/modelli/{mid}", headers=admin_headers, json=upd, timeout=15)
        assert r2.status_code == 200, r2.text
        phs = set(r2.json().get("placeholders") or [])
        assert phs == {"ramo", "totale"}, f"Placeholders non ricalcolati: {phs}"

    def test_delete_admin_only(self, admin_headers, created_ids):
        r = requests.post(
            f"{API}/librerie/modelli", headers=admin_headers,
            json={"tipo": "email", "nome": "TEST_iter42_del", "corpo": "x"}, timeout=15,
        )
        assert r.status_code == 201
        mid = r.json()["id"]
        rd = requests.delete(f"{API}/librerie/modelli/{mid}", headers=admin_headers, timeout=15)
        assert rd.status_code == 200
        assert rd.json().get("ok") is True
        # verifica 404 dopo delete
        r404 = requests.get(f"{API}/librerie/modelli/{mid}", headers=admin_headers, timeout=15)
        assert r404.status_code == 404


# --------------- Preview ---------------
class TestPreview:
    def test_preview_with_default_sample(self, admin_headers):
        body = {
            "tipo": "email",
            "oggetto": "Scadenza {numero_polizza} — {cliente_nome}",
            "corpo": "Gentile {cliente_nome}, la polizza {numero_polizza} scade il {data_scadenza}.",
        }
        r = requests.post(f"{API}/librerie/modelli/preview", headers=admin_headers, json=body, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "oggetto" in data and "corpo" in data
        # Placeholder devono essere sostituiti coi dati fittizi
        assert "Mario Rossi" in data["corpo"]
        assert "POL-2026-000123" in data["corpo"]
        assert "31/12/2026" in data["corpo"]
        # nessun placeholder residuo non risolto {xxx}
        assert not re.search(r"\{cliente_nome\}|\{numero_polizza\}|\{data_scadenza\}", data["corpo"])
        # oggetto anch'esso compilato
        assert "POL-2026-000123" in data["oggetto"]
        assert "Mario Rossi" in data["oggetto"]


# --------------- Genera PDF / DOCX ---------------
class TestGeneraDocumento:
    @pytest.fixture(scope="class")
    def modello_id(self, admin_headers):
        # trova un modello pdf_avviso (seed default)
        r = requests.get(f"{API}/librerie/modelli?tipo=pdf_avviso", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) > 0
        return items[0]["id"]

    def test_genera_pdf(self, admin_headers, modello_id):
        r = requests.post(
            f"{API}/librerie/modelli/{modello_id}/genera",
            headers=admin_headers, json={"formato": "pdf", "extra": {}}, timeout=30,
        )
        assert r.status_code == 200, r.text[:500]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert len(r.content) > 1000, f"PDF troppo piccolo: {len(r.content)}"
        assert r.content[:4] == b"%PDF", "Non è un PDF valido"

    def test_genera_docx(self, admin_headers, modello_id):
        r = requests.post(
            f"{API}/librerie/modelli/{modello_id}/genera",
            headers=admin_headers, json={"formato": "docx", "extra": {}}, timeout=30,
        )
        assert r.status_code == 200, r.text[:500]
        ct = r.headers.get("content-type", "")
        assert "wordprocessingml" in ct or "officedocument" in ct, f"CT inatteso: {ct}"
        assert len(r.content) > 1000, f"DOCX troppo piccolo: {len(r.content)}"
        # docx è un file ZIP → magic bytes PK
        assert r.content[:2] == b"PK", "Non è un docx (ZIP) valido"


# --------------- Alert Rules con template_modello_id ---------------
class TestAlertRulesTemplateModello:
    def test_post_alert_rule_persists_template_modello_id(self, admin_headers, created_ids):
        # prima creiamo un modello dedicato
        m = requests.post(
            f"{API}/librerie/modelli", headers=admin_headers,
            json={"tipo": "email", "nome": "TEST_iter42_rulemod",
                  "oggetto": "TESTMOD_OGG {cliente_nome}",
                  "corpo": "TESTMOD_CORPO {cliente_nome} {numero_polizza}"}, timeout=15,
        )
        assert m.status_code == 201
        mid = m.json()["id"]
        created_ids["modelli"].append(mid)

        rule_payload = {
            "nome": "TEST_iter42_rule",
            "tipo": "evento",
            "evento": "polizza.emessa",
            "attivo": True,
            "canali": ["inapp"],
            "destinatari": ["admin"],
            "template_oggetto": "INLINE_OGG",
            "template_corpo": "INLINE_CORPO",
            "template_modello_id": mid,
        }
        r = requests.post(f"{API}/alert-rules", headers=admin_headers, json=rule_payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        rule = r.json()
        assert rule.get("template_modello_id") == mid, f"template_modello_id non persistito: {rule}"
        rid = rule["id"]
        created_ids["rules"].append(rid)

        # GET verifica persistenza
        rg = requests.get(f"{API}/alert-rules/{rid}", headers=admin_headers, timeout=15)
        assert rg.status_code == 200
        assert rg.json().get("template_modello_id") == mid

    def test_patch_updates_template_modello_id(self, admin_headers, created_ids):
        # crea rule senza template_modello_id
        m = requests.post(
            f"{API}/librerie/modelli", headers=admin_headers,
            json={"tipo": "email", "nome": "TEST_iter42_patchmod", "corpo": "X {cliente_nome}"}, timeout=15,
        )
        mid = m.json()["id"]
        created_ids["modelli"].append(mid)

        r = requests.post(
            f"{API}/alert-rules", headers=admin_headers,
            json={"nome": "TEST_iter42_patch", "tipo": "evento", "evento": "polizza.emessa",
                  "attivo": True, "canali": ["inapp"], "destinatari": ["admin"]}, timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        rid = r.json()["id"]
        created_ids["rules"].append(rid)
        assert r.json().get("template_modello_id") in (None, "")

        # PATCH/PUT (endpoint alert-rules uses PATCH-style body)
        rp = requests.put(
            f"{API}/alert-rules/{rid}", headers=admin_headers,
            json={"template_modello_id": mid}, timeout=15,
        )
        assert rp.status_code in (200, 204), rp.text
        rg = requests.get(f"{API}/alert-rules/{rid}", headers=admin_headers, timeout=15)
        assert rg.status_code == 200
        assert rg.json().get("template_modello_id") == mid


# --------------- dispatch_rule: modello libreria ha precedenza ---------------
class TestDispatchWithModello:
    @pytest.mark.asyncio
    async def test_dispatch_uses_modello_libreria(self, admin_headers, created_ids):
        """Chiama dispatch_rule con una rule che ha template_modello_id.
        Verifica che l'alert_event abbia oggetto/corpo dal modello (non da template inline).
        """
        # crea modello con oggetto/corpo unici e placeholder
        marker = uuid.uuid4().hex[:8]
        m = requests.post(
            f"{API}/librerie/modelli", headers=admin_headers,
            json={"tipo": "email", "nome": f"TEST_iter42_disp_{marker}",
                  "oggetto": f"MOD_OGG_{marker} {{cliente_nome}}",
                  "corpo": f"MOD_CORPO_{marker} per {{cliente_nome}}"}, timeout=15,
        )
        assert m.status_code == 201
        mid = m.json()["id"]
        created_ids["modelli"].append(mid)

        r = requests.post(
            f"{API}/alert-rules", headers=admin_headers,
            json={
                "nome": f"TEST_iter42_disp_{marker}",
                "tipo": "evento",
                "evento": f"polizza.emessa_test_{marker}",
                "attivo": True,
                "canali": ["inapp"],
                "destinatari": ["admin"],
                "template_oggetto": "INLINE_OGG_SHOULD_NOT_APPEAR",
                "template_corpo": "INLINE_CORPO_SHOULD_NOT_APPEAR",
                "template_modello_id": mid,
            }, timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        rid = r.json()["id"]
        created_ids["rules"].append(rid)

        # chiamiamo dispatch_rule direttamente via module (in-process)
        import sys
        sys.path.insert(0, "/app/backend")
        from alert_dispatcher import dispatch_rule
        from database import db as _db

        rule_doc = await _db.alert_rules.find_one({"id": rid}, {"_id": 0})
        assert rule_doc is not None
        stats = await dispatch_rule(rule_doc, {
            "entita_tipo": "polizza", "entita_id": "test-pol-123",
            "cliente_nome": "TEST_CLIENTE_ITER42",
        })
        # deve aver generato almeno un evento (destinatario=admin)
        assert stats["sent"] + stats["errors"] + stats["skipped"] >= 1, f"nessun evento: {stats}"
        # verifica gli eventi generati
        events = await _db.alert_events.find({"rule_id": rid}, {"_id": 0}).to_list(20)
        assert len(events) >= 1, "nessun alert_event trovato"
        e = events[0]
        assert f"MOD_OGG_{marker}" in (e.get("oggetto") or ""), \
            f"Oggetto deve venire dal modello libreria, non da template inline. Got: {e.get('oggetto')}"
        assert f"MOD_CORPO_{marker}" in (e.get("corpo") or ""), \
            f"Corpo deve venire dal modello libreria. Got: {e.get('corpo')}"
        assert "INLINE_OGG_SHOULD_NOT_APPEAR" not in (e.get("oggetto") or "")
        assert "INLINE_CORPO_SHOULD_NOT_APPEAR" not in (e.get("corpo") or "")
        # cleanup events
        await _db.alert_events.delete_many({"rule_id": rid})


# --------------- Bulk WhatsApp con modello_id (senza invio reale) ---------------
class TestBulkWhatsAppModelloId:
    def test_bulk_accepts_modello_id_field(self, admin_headers, created_ids):
        """Verifica che il campo modello_id sia accettato dall'endpoint.
        Usiamo titoli_ids fittizi → risposta 404 (Nessun titolo trovato),
        confermando che il body/campo è stato parsato correttamente (no 422).
        """
        m = requests.post(
            f"{API}/librerie/modelli", headers=admin_headers,
            json={"tipo": "whatsapp", "nome": "TEST_iter42_bulkwa",
                  "corpo": "Ciao {cliente_nome}, hai {numero_titoli} titoli tot {totale}"}, timeout=15,
        )
        mid = m.json()["id"]
        created_ids["modelli"].append(mid)

        r = requests.post(
            f"{API}/avvisi/whatsapp-invia-bulk-titoli", headers=admin_headers,
            json={"titoli_ids": ["NON_ESISTE_XYZ_123"], "modello_id": mid}, timeout=20,
        )
        # Deve rispondere 404 "Nessun titolo trovato", non 422 (validation error)
        assert r.status_code == 404, f"expected 404 (titoli inesistenti), got {r.status_code}: {r.text}"

    def test_bulk_empty_titoli_ids_returns_400(self, admin_headers):
        r = requests.post(
            f"{API}/avvisi/whatsapp-invia-bulk-titoli", headers=admin_headers,
            json={"titoli_ids": [], "modello_id": "irrelevant"}, timeout=15,
        )
        assert r.status_code == 400


# --------------- Numero normalization ---------------
class TestNumeroNormalization:
    @pytest.mark.asyncio
    async def test_send_text_normalizza_numero_10_cifre(self, monkeypatch):
        """send_text_via_evolution deve normalizzare 10 cifre inizia con 3 → 39XXXXXXXXXX."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import whatsapp_evo as we
        from database import TenantAwareCollection

        captured = {}

        async def fake_call(method, path, json=None, **kw):
            captured["json"] = json
            return {"status": "PENDING", "key": {"id": "fake"}}

        async def fake_find_one(self, *a, **kw):
            if self._coll_name == "whatsapp_instances":
                return {"instance_name": "fake-inst", "state": "open"}
            # fallback to original
            return await self._coll.find_one(self._inject(a[0] if a else {}), **kw)

        monkeypatch.setattr(we, "_call", fake_call)
        monkeypatch.setattr(TenantAwareCollection, "find_one", fake_find_one)

        r = await we.send_text_via_evolution("3465708351", "test")
        assert captured.get("json", {}).get("number") == "393465708351", \
            f"numero non normalizzato: {captured.get('json')}"
        assert r.get("ok") is True

    @pytest.mark.asyncio
    async def test_send_text_lascia_numero_con_prefisso(self, monkeypatch):
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import whatsapp_evo as we
        from database import TenantAwareCollection

        captured = {}

        async def fake_call(method, path, json=None, **kw):
            captured["json"] = json
            return {"status": "PENDING"}

        async def fake_find_one(self, *a, **kw):
            if self._coll_name == "whatsapp_instances":
                return {"instance_name": "fake-inst", "state": "open"}
            return None

        monkeypatch.setattr(we, "_call", fake_call)
        monkeypatch.setattr(TenantAwareCollection, "find_one", fake_find_one)

        await we.send_text_via_evolution("393465708351", "test")
        assert captured.get("json", {}).get("number") == "393465708351"

    @pytest.mark.asyncio
    async def test_send_text_numero_vuoto(self, monkeypatch):
        """Edge case: numero vuoto/invalido → ok=False, no chiamata Evolution."""
        import sys
        sys.path.insert(0, "/app/backend")
        from routes import whatsapp_evo as we

        called = {"count": 0}

        async def fake_call(*a, **kw):
            called["count"] += 1
            return {}

        monkeypatch.setattr(we, "_call", fake_call)
        r = await we.send_text_via_evolution("", "test")
        assert r.get("ok") is False
        assert called["count"] == 0


# --------------- Regressione ---------------
class TestRegressione:
    def test_list_alert_rules_ok(self, admin_headers):
        r = requests.get(f"{API}/alert-rules", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_preset_rules_backward_compat(self, admin_headers, created_ids):
        """Regole con solo template_oggetto/template_corpo (no modello_id) funzionano."""
        r = requests.post(
            f"{API}/alert-rules", headers=admin_headers,
            json={
                "nome": "TEST_iter42_backcompat",
                "tipo": "evento", "evento": "polizza.emessa",
                "attivo": True, "canali": ["inapp"], "destinatari": ["admin"],
                "template_oggetto": "Oggetto legacy {cliente_nome}",
                "template_corpo": "Corpo legacy {cliente_nome}",
            }, timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        rid = r.json()["id"]
        created_ids["rules"].append(rid)
        assert r.json().get("template_modello_id") in (None, "")
        # GET conferma
        rg = requests.get(f"{API}/alert-rules/{rid}", headers=admin_headers, timeout=15)
        assert rg.json().get("template_oggetto") == "Oggetto legacy {cliente_nome}"

    def test_avvisi_whatsapp_invia_senza_modello_id(self, admin_headers):
        """/api/avvisi/whatsapp-invia singolo continua a funzionare senza modello_id.
        Con numero fittizio dovrebbe fallire a livello Evolution ma non a validation.
        """
        r = requests.post(
            f"{API}/avvisi/whatsapp-invia", headers=admin_headers,
            json={"cellulare": "0000000000", "messaggio": "test"}, timeout=20,
        )
        # accettiamo 400 (numero non valido) o 200/500 (send fallito) ma NON 422
        assert r.status_code != 422, f"Regressione validation: {r.status_code} {r.text}"


# --------------- pytest-asyncio config ---------------
@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
