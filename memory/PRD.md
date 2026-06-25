# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), avvisi scadenze, analisi cliente.

## Latest Session (Iter 20 — Code Quality complexity refactor)

### Done (93/93 PASS)
- ✅ **`parse_estratto_conto_inps`** (was CC=57, 276 righe, 33 local vars) refactored in `inps_calculator.py` con orchestrator + 7 helpers specializzati (`_parse_anagrafica`, `_parse_periodi_formato_inps`, `_parse_periodi_parasubordinati`, `_parse_periodi_satorcrm`, `_parse_periodi_fallback_date`, `_parse_storico_redditi_tabella`, `_consolida_totali`) + `_EstrattoState` class che incapsula lo stato condiviso. CC stimato ~5-8.
- ✅ **`_processa_polizze`** (was CC=28, 63 righe, 8 params) refactored in `ania_importer.py` con `_resolve_operatore_codice`, `_build_polizza_payload`, `_upsert_polizza`.
- ✅ **`_build_dettagli_veicolo`** (was CC=25) refactored in 4 sezioni: `_campi_veicolo_base`, `_campi_tariffa_bm`, `_campi_valori`, `_campi_guida`.
- ✅ **`genera_pdf_avvisi`** (was CC=25, 112 righe) rewritten in `pdf_avvisi.py` con 8 helpers (Builder pattern).
- ✅ **`stampa_brogliaccio`** (was CC=24) rewritten in `pdf_brogliaccio.py` con 10 helpers estratti.
- ✅ **Anti-pattern `is True/is False`**: ~30 occorrenze sostituite con `== True/== False` in tutti `test_iter*.py`. `is None`/`is not None` preservato (16 file - idiomatic Python).
- ✅ **Lint**: 0 errori sui 5 moduli refactored.

### Testing iter 20
- **93/93 PASS** (25 nuovi + 68 regression iter4/5/15/17/18/19).
- PDF endpoint manuale: `/api/contabilita/brogliaccio/stampa?data=YYYY-MM-DD` ritorna 4932 byte PDF.
- INPS parser su testo realistico: estrae cognome/nome/CF/sesso/comune_nascita/data_nascita/residenza/periodi/storico/montante_stimato corretti.
- Smoke 8 endpoint: tutti 200.

## Sessioni precedenti
- Iter 19: split parziale di server.py in routes/ (dashboard + ocr), shared.py creato, E701/E702 fixati, UI Personalizza KPI Anagrafiche.
- Iter 18: refactor cyclomatic di 5 moduli (brogliaccio, avvisi_scadenze, geocoder, inps_calculator.calcola_pensione, ania_importer.importa_zip).
- Iter 17: P0 circular import auth↔server risolto via database.py; secrets test eliminati; tab Veicolo polizza con 18 nuovi campi; rimossa colonna "Collegati".

## Architecture (state of art)
- `/app/backend/database.py` — Motor client + db (single source of truth)
- `/app/backend/auth.py` — JWT + bcrypt + `require_user` dep
- `/app/backend/shared.py` — helpers cross-module (log_attivita, log_diario_cliente, strip_mongo_id, calcola_scadenza_titolo, resolve_conto_cassa, visibility_filter, costanti)
- `/app/backend/routes/dashboard.py` — 5 endpoint dashboard (tasks, links CRUD)
- `/app/backend/routes/ocr.py` — 2 endpoint OCR libretto Gemini
- `/app/backend/server.py` — ~9.700 righe (was 10.142). Restano da estrarre: auth, anagrafiche, librerie, polizze, titoli, sinistri, brogliaccio (routes), admin.
- `/app/backend/brogliaccio.py` `avvisi_scadenze.py` `geocoder.py` `inps_calculator.py` `ania_importer.py` `pdf_avvisi.py` `pdf_brogliaccio.py` — tutti refactored, CC sotto soglia 10.
- `/app/backend/tests/test_iter*.py` — 93 test passing al 100%, anti-pattern free.

## Backlog

### P0 (next session)
- **Continuare split server.py**: estrarre `routes/librerie.py` (38 endpoint, isolato), `routes/auth.py`, `routes/anagrafiche.py` (44 endpoint), `routes/polizze.py`, `routes/titoli.py`, `routes/sinistri.py`, `routes/admin.py`, `routes/stampa.py`.
- Spostare `_intestazione_pdf` in `shared.py` (usato da 15 endpoint PDF, ancora in server.py).

### P1
- OCR Fatture via Gemini 3 Flash (`ocr_fattura.py`).
- "Verifica polizza vs libretto" — UI di confronto discrepanze.
- `PolizzaUpdate`, `KpiCustomBody` Pydantic per typed-validation.
- Type hints più stringenti su `_campi_*` (oggi `dict -> dict`).

### P2
- Piramide Soluzioni Release B.
- Integrazioni: Google Calendar / Microsoft 365 / WhatsApp / SMS.
- Type hint coverage 46% → 80% (mypy in CI).
- Email templates a Jinja2 esterni.

## Credenziali test
admin@assicura.it / Admin123!
