# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), avvisi scadenze, analisi cliente.

## Latest Session (Iter 19 — Split server.py partial + E701/E702 + KPI Anagrafiche custom UI)

### Done in iter 19
- ✅ **E701/E702 (100 occorrenze)** sistemate in server.py via autopep8 automatico.
- ✅ **shared.py creato** (164 righe): helpers comuni estratti da server.py — `log_attivita`, `log_diario_cliente`, `strip_mongo_id`, `visibility_filter`, `calcola_scadenza_titolo`, `resolve_conto_cassa`, costanti `_MESI_PER_FRAZIONAMENTO` / `_MEZZO_TO_TIPO` / `_CORPO_LETTERA_DEFAULT`.
- ✅ **routes/dashboard.py** (225 righe): estratti 5 endpoint (GET /tasks, GET/POST/PUT/DELETE /links) + `DashboardLinkBody` Pydantic. Refactor `dashboard_tasks` con sotto-helper `_conta_compleanni`, `_conta_documenti`, `_build_task_list`.
- ✅ **routes/ocr.py** (144 righe): estratti 2 endpoint OCR libretto + helpers `_convert_pdf_to_jpeg`, `_salva_allegato_libretto`, `_FIELD_MAP`.
- ✅ **server.py**: ridotto da 10.142 → 9.688 righe (-454, ~4.5%). I router modulari sono inclusi via `api.include_router(...)` PRIMA di `app.include_router(api)`.
- ✅ **KPI Anagrafiche custom (P1)** completata:
  - Backend: GET `/api/anagrafiche/stats` ora include `custom: [{id,label,tag,color,icon,n,premio_totale}]` (lettura `db.kpi_anagrafiche_custom`, count `db.anagrafiche` per tag, somma `premio_lordo` polizze attive).
  - Frontend: bottone "Personalizza KPI" sulla pagina /anagrafiche apre dialog `PersonalizzaKpiDialog` con form Etichetta/Tag (datalist con tags esistenti)/Colore (8 opzioni)/Icona (12 opzioni). Lista KPI attive con eliminazione. Max 8.
  - Le KPI create appaiono come card aggiuntive accanto alle 4 standard (privati/aziende/condomini/parrocchie), cliccabili per filtrare la lista per quel tag.
- ✅ **DialogDescription** aggiunto per a11y Radix.

### Regression Bug Trovato e Fixato (durante iter19)
- ⚠️ `async def _intestazione_pdf()` era stato erroneamente rimosso durante l'estrazione degli helper → 15 endpoint PDF in 500. Testing agent T1 ha re-inserito l'helper in server.py righe 78-89 (chiamata `pdf_report.get_intestazione_azienda(db)` con try/except).

### Testing iter 19
- **Backend: 67/68 PASS** (15/16 iter19 nuovi + 52/52 regression iter4/5/15/17/18). L'unico FAIL iniziale era il campo `custom` mancante in `/api/anagrafiche/stats` — risolto in questo turno (verificato manualmente: stats ora ritorna `keys: [privati, aziende, condomini, parrocchie, totale, custom]` con counts e premi corretti).
- Frontend: dialog Personalizza KPI funzionante, tutti i data-testid presenti, creazione mostra toast, eliminazione OK.

## Sessioni precedenti
- Iter 18: refactor cyclomatic complexity di 5 moduli (brogliaccio, avvisi_scadenze, geocoder, inps_calculator, ania_importer). CC riduzione da 157→10 per ania_importer.importa_zip.
- Iter 17: P0 circular import auth↔server risolto via database.py; secrets test eliminati; tab Veicolo polizza con 18 nuovi campi; rimossa colonna "Collegati" da Anagrafiche.

## Architecture
- `/app/backend/database.py` — Motor client + db (single source of truth)
- `/app/backend/auth.py` — JWT + bcrypt + `require_user` dep
- `/app/backend/shared.py` **NEW** — helpers comuni cross-module
- `/app/backend/routes/dashboard.py` **NEW** — 5 endpoint dashboard
- `/app/backend/routes/ocr.py` **NEW** — 2 endpoint OCR libretto
- `/app/backend/routes/__init__.py` **NEW**
- `/app/backend/server.py` — 9.688 righe (ridotto da 10.142). Restano da estrarre: auth (~12 endpoint), anagrafiche (44), librerie (38), polizze (15), titoli (vari), brogliaccio/stampa (15), sinistri, admin.
- `/app/backend/brogliaccio.py` `avvisi_scadenze.py` `geocoder.py` `inps_calculator.py` `ania_importer.py` — tutti refactored (iter18).

## Backlog

### P0 (next session)
- **Continuare lo split server.py**: estrarre `routes/auth.py`, `routes/librerie.py` (38 endpoint, isolato), `routes/anagrafiche.py` (44 endpoint), `routes/polizze.py`, `routes/titoli.py`, `routes/brogliaccio.py`, `routes/sinistri.py`, `routes/admin.py`, `routes/stampa.py`.
- Spostare `_intestazione_pdf` in shared (è usato da 15 endpoint).

### P1
- OCR Fatture via Gemini 3 Flash (`ocr_fattura.py`).
- "Verifica polizza vs libretto" — UI di confronto discrepanze.
- `PolizzaUpdate` Pydantic per typed-validation su PUT.
- `KpiCustomBody` Pydantic per POST `/anagrafiche/kpi-custom` (oggi accetta dict generico).

### P2
- Piramide Soluzioni Release B (stacked blocks, Adeguata/Non Adeguata).
- Integrazioni: Google Calendar / Microsoft 365 / WhatsApp / SMS.
- Type hint coverage 45% → 80%.

## Credenziali test
admin@assicura.it / Admin123!
