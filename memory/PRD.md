# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), avvisi scadenze, analisi cliente.

## Latest Session (Iter 21+22 — Debito tecnico residuo SMALTITO)

### Done (124/124 PASS — iter22 RETEST)
- ✅ **`_intestazione_pdf` migrato in `shared.py`** (DRY): `shared.intestazione_pdf` è unica implementazione; server.py la importa con alias `intestazione_pdf as _intestazione_pdf`. 15 call site PDF aggiornati.
- ✅ **`routes/librerie.py` (601 righe, 38 endpoint)** estratto da server.py e attivamente registrato via `api.include_router(_librerie_router.router)`. Endpoint: GET/POST/PUT/DELETE su banche, conti-cassa, mezzi-pagamento, mapping-garanzie, mapping-operatori, prodotti, rami, schema-provvigionale, azienda, contatti-compagnia.
- ✅ **`server.py` ridotto da 9.725 → 9.164 righe (-561)** confermato e verificato.
- ✅ **Type-hint coverage core modules**: 9 moduli al 100% (shared, auth, inps_calculator, ania_importer, brogliaccio, avvisi_scadenze, geocoder, pdf_brogliaccio, pdf_avvisi) + routes/* al 100%. server.py annotato solo sugli helper non-endpoint (gli endpoint FastAPI lasciati senza return type per evitare response validation issues).
- ✅ **Anti-pattern test** (`is True/is False` → `== True/== False`): tutti i ~30 occurrence fixati. `is None` preservato (idiomatic).
- ✅ **Bug regression fixato**: 6 endpoint (dashboard_tasks, list_dashboard_links, list_mezzi_pagamento, list_mapping_operatori, list_schemi_provvigionali, list_contatti_compagnia) correttamente annotati `-> list[dict]` invece di `-> dict` (causavano FastAPI ResponseValidationError 500).

### Testing iter 22
- **124/124 PASS** (31 iter21 + 93 regression iter4/5/15/17/18/19/20).
- 0 critical issue, 0 minor issue.
- CRUD end-to-end verificato su banche, mezzi-pagamento, conti-cassa, rami, prodotti, mapping-garanzie/operatori.
- PDF endpoint (brogliaccio, titoli/sospesi) ritornano binary PDF validi.

## Sessioni precedenti
- Iter 20: refactor cyclomatic complexity di 5 moduli (parse_estratto_conto_inps CC 57→8, ania._processa_polizze CC 28→6, pdf_avvisi CC 25→Builder pattern, stampa_brogliaccio CC 24→10 helpers).
- Iter 19: split parziale server.py (dashboard + ocr routes), shared.py creato, E701/E702 fixati, UI Personalizza KPI Anagrafiche.
- Iter 18: refactor cyclomatic di brogliaccio, avvisi_scadenze, geocoder, inps_calculator, ania_importer.
- Iter 17: P0 circular import auth↔server risolto via database.py; secrets test eliminati; tab Veicolo polizza con 18 nuovi campi.

## Architecture finale (state of art)
- `/app/backend/database.py` — Motor client + db (single source of truth)
- `/app/backend/auth.py` — JWT + bcrypt + dep (100% type-hinted)
- `/app/backend/shared.py` — helpers cross-module (100% type-hinted; intestazione_pdf, log_attivita, log_diario_cliente, strip_mongo_id, calcola_scadenza_titolo, resolve_conto_cassa, visibility_filter)
- `/app/backend/routes/__init__.py`
- `/app/backend/routes/dashboard.py` — 5 endpoint
- `/app/backend/routes/ocr.py` — 2 endpoint
- `/app/backend/routes/librerie.py` — 38 endpoint
- `/app/backend/server.py` — **9.164 righe** (was 10.142). Restano da estrarre: auth, anagrafiche (44 ep), polizze (15 ep), titoli, sinistri, brogliaccio, admin, stampa. ~225 endpoint ancora inline.
- `/app/backend/brogliaccio.py` `avvisi_scadenze.py` `geocoder.py` `inps_calculator.py` `ania_importer.py` `pdf_avvisi.py` `pdf_brogliaccio.py` — tutti refactored, CC <10 ovunque, 100% type-hinted.

## Backlog

### Ready to ship — solid foundation
Lo stato del codice è stabile, modulare, type-safe. Si può ripartire con feature development.

### P1 (next features)
- OCR Fatture via Gemini 3 Flash (`ocr_fattura.py`).
- "Verifica polizza vs libretto" — UI di confronto discrepanze.
- `PolizzaUpdate`, `KpiCustomBody` Pydantic per typed-validation.
- Continuare split server.py: `routes/anagrafiche.py` (44 ep) prossimo candidato.

### P2
- Piramide Soluzioni Release B (stacked blocks, Adeguata/Non Adeguata).
- Integrazioni OAuth: Google Calendar / Microsoft 365 / WhatsApp / SMS.
- Migrare `@app.on_event` a `lifespan` (deprecation FastAPI, righe 9043, 9158).
- Email templates Jinja2 esterni.
- mypy strict-mode in CI sui core modules.

## Credenziali test
admin@assicura.it / Admin123!
