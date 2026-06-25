# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), avvisi scadenze, analisi cliente.

## Latest Session (Iter 18 - Cyclomatic Complexity Refactor)

### Done in iter 18 (Code Quality Critical + Important)
- ✅ **`brogliaccio.py`** — `genera_brogliaccio_pdf` (150 righe, CC=36) → 7 helper:
  `_load_movimenti_arricchiti`, `_classifica_movimento`, `_descrizione_movimento`,
  `_celle_conti_cassa`, `_build_righe_dettaglio`, `_calcola_col_widths`,
  `_build_tabella_principale`, `_build_tabella_riepilogo`. CC ridotta a ~6.
- ✅ **`avvisi_scadenze.py`** — `cerca_scadenze` (113 righe, CC=17) → 7 helper
  (`_query_polizze_in_scadenza`, `_query_titoli_arretrati`, `_carica_anagrafiche`,
  `_carica_compagnie`, `_format_polizza_record`, `_format_titolo_record`, `_giorni_da_oggi`).
  `esegui_job_scadenze` → `_build_log_entry`, `_resolve_destinatario`, `_persist_log`, `_invia_email`.
- ✅ **`geocoder.py`** — `cerca_suggerimenti` (55 righe, CC=24) → `_nominatim_get`,
  `_estrai_comune`, `_estrai_indirizzo`, `_parse_item`. CC a ~8.
- ✅ **`inps_calculator.py`** — `calcola_pensione` (93 righe, CC=14) →
  `_calcola_invalidita`, `_calcola_inabilita`, `_calcola_superstite`, `_aliquota_superstite`.
- ✅ **`ania_importer.py`** — `importa_zip` (391 righe, CC=157) → 11 processori:
  `_extract_zip_contents`, `_get_or_create_compagnia`, `_processa_anagrafiche`,
  `_processa_polizze`, `_processa_dettagli_veicolo`, `_processa_garanzie`,
  `_processa_titoli`, `_processa_sinistri`, `_conta_record_residui`,
  `_build_anagrafica_payload`, `_build_dettagli_veicolo`. CC a ~10. Idempotenza preservata.
- ✅ **Unused variables (F841)** rimosse: `smaller` in pdf_brogliaccio, `nucleo` in
  pdf_diagnosi, `s` in pdf_privacy, `body` in test_iter11, `comp` in test_iter13.
- ✅ `is True` → `== True` nel solo test che usava antipattern.

### Testing iter 18
- **Backend: 52/52 PASS** (24 nuovi iter18 + 28 regression iter4/5/15/17).
- ANIA import end-to-end verificato: stessi counts del pre-refactor.
- Lint: 0 errori sui 5 moduli refactored.

## Sessioni precedenti
- Iter 17 (P0 Code Quality): circular import auth↔server risolto via `database.py`;
  secrets test hardcoded sostituiti con env vars; undefined `_calcola_scadenza_titolo` /
  `_CORPO_LETTERA_DEFAULT` implementati; tab Veicolo "Modifica polizza" con 18 nuovi
  campi (Dati associazione contratto); rimossa colonna "Collegati" da Anagrafiche.

## Architecture
- `/app/backend/database.py` — Motor client + db (single source of truth)
- `/app/backend/auth.py` — JWT + bcrypt + `require_user` dep
- `/app/backend/server.py` — monolite 10.143 righe (split P0 prossimo)
- `/app/backend/brogliaccio.py` — PDF (refactored, modulare)
- `/app/backend/avvisi_scadenze.py` — job scadenze (refactored, modulare)
- `/app/backend/ania_importer.py` — import ANIA (refactored, 11 processori)
- `/app/backend/inps_calculator.py` — calcoli pensione (refactored, branch per tipo)
- `/app/backend/geocoder.py` — Nominatim wrapper (refactored)
- `/app/backend/tests/conftest.py` — shared fixtures + env-driven creds

## Backlog

### P0 (next)
- **Split `server.py` (10.143 righe)** in `/app/backend/routes/`:
  auth, anagrafiche, polizze, titoli, sinistri, brogliaccio, dashboard,
  ocr, admin, librerie, importazioni. Mantenere `server.py` come entry point.
- Style fix: ~99 E701/E702 (multi-statement per riga) in `server.py`.

### P1
- UI "Personalizza KPI Anagrafiche" basata sui Tag.
- OCR Fatture via Gemini 3 Flash (`ocr_fattura.py`).
- "Verifica polizza vs libretto" — UI di confronto discrepanze.
- `PolizzaUpdate` Pydantic per typed-validation su PUT.

### P2
- Piramide Soluzioni Release B (stacked blocks, Adeguata/Non Adeguata).
- Integrazioni: Google Calendar / Microsoft 365 / WhatsApp / SMS.
- Type hint coverage 45% → 80% (almeno sui moduli core).
- `DialogDescription` mancante su EditPolizzaDialog (warning Radix a11y).

## Credenziali test
admin@assicura.it / Admin123!
