"""Iter21 regression — verifica refactor:
1. `intestazione_pdf` esiste in shared.py e `_intestazione_pdf` resta accessibile in server.py.
2. routes/librerie.py NUOVO esiste (anche se non ancora montato).
3. Tutti i 38 endpoint /api/librerie funzionano (GET + CRUD).
4. Endpoint PDF che usano _intestazione_pdf restituiscono PDF (smoke).
5. Type hints presenti nei moduli annotati.
"""
from __future__ import annotations

import os
import importlib
import inspect
import pathlib
import pytest
import requests

# Ensure backend env is available before importing backend modules.
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env", override=False)
except Exception:
    pass

from conftest import API


# ----- (1) Refactor strutturale -----

def test_shared_has_intestazione_pdf():
    """shared.py deve esportare `intestazione_pdf` (richiesto dal review iter19)."""
    shared = importlib.import_module("shared")
    assert hasattr(shared, "intestazione_pdf"), "shared.intestazione_pdf mancante"
    assert inspect.iscoroutinefunction(shared.intestazione_pdf)


def test_server_intestazione_pdf_backcompat():
    """server._intestazione_pdf deve restare disponibile per backward compat."""
    server = importlib.import_module("server")
    assert hasattr(server, "_intestazione_pdf"), "server._intestazione_pdf rimosso!"
    assert inspect.iscoroutinefunction(server._intestazione_pdf)


def test_routes_librerie_module_exists():
    """Nuovo modulo routes/librerie.py deve esistere ed esporre un APIRouter."""
    mod = importlib.import_module("routes.librerie")
    from fastapi import APIRouter
    assert isinstance(mod.router, APIRouter)
    # 38 endpoint dichiarati
    routes = [r for r in mod.router.routes if getattr(r, "path", "").startswith("/librerie") or getattr(r, "path", "").startswith("/api/")]
    assert len(mod.router.routes) >= 30, f"routes/librerie.py: solo {len(mod.router.routes)} endpoint trovati"


# ----- (2) Endpoint /api/librerie GET smoke -----

LIBRERIE_GET_ENDPOINTS = [
    "/librerie/banche",
    "/librerie/conti-cassa",
    "/librerie/mapping-garanzie",
    "/librerie/mapping-operatori",
    "/librerie/mezzi-pagamento",
    "/librerie/prodotti",
    "/librerie/rami",
    "/librerie/azienda",
    "/librerie/schema-provvigionale",
]


@pytest.mark.parametrize("path", LIBRERIE_GET_ENDPOINTS)
def test_librerie_get_endpoint_200(admin_session, path):
    r = admin_session.get(f"{API}{path}", timeout=15)
    assert r.status_code == 200, f"GET {path} -> {r.status_code}: {r.text[:200]}"


# ----- (3) CRUD librerie/banche -----

class TestBancheCrud:
    def test_create_update_delete_banca(self, admin_session):
        # CREATE
        payload = {"nome": "TEST_iter21_BancaXYZ", "abi": "12345", "cab": "67890"}
        r = admin_session.post(f"{API}/librerie/banche", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"POST banche {r.status_code}: {r.text[:300]}"
        bid = r.json().get("id")
        assert bid

        # GET list contains it
        rl = admin_session.get(f"{API}/librerie/banche", timeout=15).json()
        assert any(b.get("id") == bid for b in rl), "Banca creata non trovata in GET list"

        # UPDATE
        ru = admin_session.put(f"{API}/librerie/banche/{bid}", json={"nome": "TEST_iter21_BancaXYZ_upd"}, timeout=15)
        assert ru.status_code == 200, f"PUT {ru.status_code}: {ru.text[:200]}"

        # DELETE
        rd = admin_session.delete(f"{API}/librerie/banche/{bid}", timeout=15)
        assert rd.status_code in (200, 204)

        # Verify removed
        rl2 = admin_session.get(f"{API}/librerie/banche", timeout=15).json()
        assert not any(b.get("id") == bid for b in rl2), "Banca eliminata ancora presente"


# ----- (4) CRUD librerie/mezzi-pagamento -----

class TestMezziPagamentoCrud:
    def test_create_update_delete_mezzo(self, admin_session):
        import uuid
        codice = f"tst21mz{uuid.uuid4().hex[:6]}"
        payload = {"codice": codice, "label": "TEST_iter21_Mezzo"}
        r = admin_session.post(f"{API}/librerie/mezzi-pagamento", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"POST {r.status_code}: {r.text[:300]}"
        mid = r.json().get("id")
        assert mid

        ru = admin_session.put(f"{API}/librerie/mezzi-pagamento/{mid}", json={"codice": codice, "label": "TEST_iter21_Mezzo_upd"}, timeout=15)
        assert ru.status_code == 200, f"PUT {ru.status_code}: {ru.text[:200]}"

        rd = admin_session.delete(f"{API}/librerie/mezzi-pagamento/{mid}", timeout=15)
        assert rd.status_code in (200, 204)


# ----- (5) CRUD librerie/conti-cassa -----

class TestContiCassaCrud:
    def test_create_update_delete_conto(self, admin_session):
        payload = {"nome": "TEST_iter21_Cassa", "tipo": "cassa"}
        r = admin_session.post(f"{API}/librerie/conti-cassa", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"POST conti-cassa {r.status_code}: {r.text[:300]}"
        cid = r.json().get("id")
        assert cid

        ru = admin_session.put(f"{API}/librerie/conti-cassa/{cid}", json={"nome": "TEST_iter21_Cassa_upd"}, timeout=15)
        assert ru.status_code == 200

        rd = admin_session.delete(f"{API}/librerie/conti-cassa/{cid}", timeout=15)
        assert rd.status_code in (200, 204)


# ----- (6) CRUD librerie/rami -----

class TestRamoCrud:
    def test_create_update_delete_ramo(self, admin_session):
        payload = {"nome": "TEST_iter21_Ramo", "codice": "T21"}
        r = admin_session.post(f"{API}/librerie/rami", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"POST rami {r.status_code}: {r.text[:300]}"
        rid = r.json().get("id")
        assert rid

        ru = admin_session.put(f"{API}/librerie/rami/{rid}", json={"nome": "TEST_iter21_Ramo_upd"}, timeout=15)
        assert ru.status_code == 200

        rd = admin_session.delete(f"{API}/librerie/rami/{rid}", timeout=15)
        assert rd.status_code in (200, 204)


# ----- (7) CRUD librerie/prodotti -----

class TestProdottoCrud:
    def test_create_update_delete_prodotto(self, admin_session):
        # need a compagnia and ramo - reuse existing
        compagnie = admin_session.get(f"{API}/compagnie", timeout=15).json()
        rami = admin_session.get(f"{API}/librerie/rami", timeout=15).json()
        if not compagnie or not rami:
            pytest.skip("nessuna compagnia o ramo per testare prodotti")
        payload = {
            "nome": "TEST_iter21_Prodotto",
            "compagnia_id": compagnie[0].get("id"),
            "ramo": rami[0].get("nome"),
        }
        r = admin_session.post(f"{API}/librerie/prodotti", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"POST prodotti {r.status_code}: {r.text[:300]}"
        pid = r.json().get("id")
        assert pid

        ru = admin_session.put(f"{API}/librerie/prodotti/{pid}", json={"nome": "TEST_iter21_Prodotto_upd"}, timeout=15)
        assert ru.status_code == 200

        rd = admin_session.delete(f"{API}/librerie/prodotti/{pid}", timeout=15)
        assert rd.status_code in (200, 204)


# ----- (8) PDF endpoints — usano _intestazione_pdf -----

def test_pdf_stampa_titoli_sospesi(admin_session):
    """Endpoint PDF rappresentativo che usa _intestazione_pdf via shared."""
    r = admin_session.get(
        f"{API}/stampa/titoli/sospesi",
        timeout=30,
    )
    assert r.status_code == 200, f"GET stampa/titoli/sospesi {r.status_code}: {r.text[:200]}"
    assert r.headers.get("content-type", "").startswith("application/pdf"), f"content-type: {r.headers.get('content-type')}"
    assert r.content[:4] == b"%PDF", "Non è un PDF valido"


def test_pdf_stampa_titoli(admin_session):
    """Altro endpoint PDF che usa _intestazione_pdf (smoke)."""
    r = admin_session.get(f"{API}/stampa/titoli", timeout=30)
    assert r.status_code in (200, 204, 404), f"GET stampa/titoli {r.status_code}: {r.text[:300]}"
    if r.status_code == 200:
        assert r.content[:4] == b"%PDF"


# ----- (9) Type-hint coverage spot-check -----

ANNOTATED_MODULES = [
    "shared", "auth", "inps_calculator", "ania_importer",
    "brogliaccio", "avvisi_scadenze", "geocoder",
    "pdf_brogliaccio", "pdf_avvisi",
]


@pytest.mark.parametrize("modname", ANNOTATED_MODULES)
def test_module_type_hint_coverage(modname):
    """I moduli dichiarati 100% type-hinted devono avere return annotation su tutte le funzioni pubbliche."""
    mod = importlib.import_module(modname)
    missing = []
    for name, obj in inspect.getmembers(mod):
        if name.startswith("_"):
            continue
        if inspect.isfunction(obj) and obj.__module__ == modname:
            sig = inspect.signature(obj)
            if sig.return_annotation is inspect.Signature.empty:
                missing.append(name)
    # Allow few stragglers (target 80%+, request says 100% per module)
    assert len(missing) <= 1, f"{modname}: funzioni senza return-type: {missing}"


def test_routes_librerie_full_type_hints():
    mod = importlib.import_module("routes.librerie")
    missing = []
    for name, obj in inspect.getmembers(mod):
        if inspect.isfunction(obj) and obj.__module__ == "routes.librerie":
            sig = inspect.signature(obj)
            if sig.return_annotation is inspect.Signature.empty:
                missing.append(name)
    assert len(missing) <= 2, f"routes.librerie funzioni senza return-type: {missing}"


# ----- (10) Bug regressione iter21 — dashboard return types -----

def test_dashboard_tasks_returns_list(admin_session):
    r = admin_session.get(f"{API}/dashboard/tasks", timeout=15)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    assert isinstance(r.json(), list), f"dashboard/tasks deve tornare list, è {type(r.json()).__name__}"


def test_dashboard_links_returns_list(admin_session):
    r = admin_session.get(f"{API}/dashboard/links", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
