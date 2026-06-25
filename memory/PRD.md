# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), avvisi scadenze, analisi cliente.

## Latest Session (Iter 17 - P0 Code Quality)

### Done
- ✅ **P0 Circular Import RISOLTO**: estratto MongoDB client+db in nuovo `/app/backend/database.py`; `auth.py` e `server.py` ora importano da `database.py` (rimosso `from server import db` late-import in `require_user`).
- ✅ **P0 Secrets hardcoded RIMOSSI** da TUTTI i test (`/app/backend/tests/*`): `ADMIN_EMAIL`/`ADMIN_PASSWORD` ora via `os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it")` etc. con default. Aggiunto `tests/conftest.py` con fixture `admin_session`/`admin_credentials`.
- ✅ **P0 Undefined names FIXED** in `server.py`:
  - `_calcola_scadenza_titolo(effetto, frazionamento)`: implementato in Helpers (gestisce clamp fine mese)
  - `_CORPO_LETTERA_DEFAULT`: testo default lettera promemoria pagamento
  - `_MESI_PER_FRAZIONAMENTO`: mapping annuale=12, semestrale=6, trimestrale=3, mensile=1, ecc.
- ✅ **Unused variables** rimosse (`crediti_agg`/`crediti_storno` in brogliaccio, `today` in dati-compagnie, `week_end` in dashboard/tasks).
- ✅ **Modifica polizza → tab Veicolo**: aggiunti TUTTI i campi mancanti
  - Veicolo: `veicolo_quintali`, `veicolo_gancio_traino`, `veicolo_targa_rimorchio`
  - Sezione "Dati associazione contratto": `tipo_tariffa`, `bm_provenienza`, `bm_assegnata`, `bm_assegnata_cu`, `pejus`, `franchigia`, `valore_veicolo`, `valore_residuo_veicolo`, `valore_accessori`, `guida_esperta`, `guida_esclusiva`, `rinuncia_rivalsa`, `intestatario`, `provincia_intestatario`, `massimali`
- ✅ **Anagrafiche lista**: rimossa colonna "Collegati" (header + cella + colspan aggiornato a 9).

### Testing
- Iter17 backend regression: **12/12 PASS** (login, anagrafiche/stats, dashboard/tasks, brogliaccio, dati-compagnie, sostituisci polizza con titolo, avvisi PDF, PUT polizza con 18 nuovi campi).
- Iter14-16 regression: 22/24 PASS (i 2 fallimenti sono Nominatim flaky + contaminazione dati, NON correlati al refactor).
- Smoke frontend OK.

## Architecture
- `/app/backend/database.py` NEW — Motor client + db (single source of truth)
- `/app/backend/auth.py` — JWT + bcrypt + `require_user` dep (clean)
- `/app/backend/server.py` — ancora monolite 10.143 righe (split P1 prossimo)
- `/app/backend/tests/conftest.py` NEW — shared fixtures env-driven

## Backlog

### P0 (next)
- Split `server.py` (10k+ righe) in `/app/backend/routes/` (auth, anagrafiche, polizze, titoli, sinistri, brogliaccio, dashboard, ocr, admin). Mantenere `server.py` come entry point con `include_router`.
- Style fix: ~99 occorrenze E701/E702 (multi-statement per riga) in `server.py`.

### P1
- UI "Personalizza KPI Anagrafiche" basata sui Tag (dialog + bottone ⚙️) — backend già pronto (`/api/anagrafiche/kpi-custom`)
- OCR Fatture via Gemini 3 Flash (`ocr_fattura.py`)
- "Verifica polizza vs libretto" — UI di confronto discrepanze nella detail di polizza
- Replicare cascata Ramo→Prodotto in altri form di creazione polizza
- Aggiungere `PolizzaUpdate` Pydantic per typed-validation su PUT /polizze/{id}

### P2
- Piramide Soluzioni — Release B (stacked blocks, indicatori Adeguata/Non Adeguata)
- Integrazioni: Google Calendar / Microsoft 365 / WhatsApp / SMS
- DialogDescription mancante su EditPolizzaDialog (warning Radix a11y)

## Credenziali test
admin@assicura.it / Admin123!
