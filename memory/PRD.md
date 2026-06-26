# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), avvisi scadenze, analisi cliente.

## Latest Session (Iter 24 — Wizard Mapping OMNIA)

### Done — Wizard Mapping Importazioni OMNIA (P0)
- ✅ **Tracking unificato** (`ania_importer.py`): durante l'import ogni codice flusso (compagnia / ramo / collaboratore / prodotto / garanzia) non riconducibile a un'entità DB viene tracciato in `db.import_mappings` con stub `entita_id=None` e contatore `occorrenze`.
- ✅ **Risoluzione automatica via mapping**: l'importatore ora carica `import_mappings` all'inizio e durante la creazione/aggiornamento delle polizze applica già il mapping ramo/prodotto/compagnia/operatore se presente (no back-fill necessario per i nuovi import).
- ✅ **Campi tracking sulla polizza** (`db_models.py`): `compagnia_codice_exp`, `ramo_originale`, `prodotto_originale` — conservano il valore originale del flusso per back-fill preciso.
- ✅ **Nuovi endpoint backend**:
  - `GET /api/import/unmapped` — entità non mappate raggruppate per tipo + lista `candidates` (compagnie/rami/users/prodotti/garanzie DB).
  - `POST /api/import/mappings/apply` — back-fill esegue update su `polizze.compagnia_id` (match `compagnia_codice_exp`), `polizze.ramo` (match `ramo_originale`), `polizze.prodotto` (match `prodotto_originale`), `polizze.collaboratore_id` (match `operatore_ania_codice`), e rinomina `garanzie[]` per codice ANIA. Ritorna summary numerico.
- ✅ **Frontend Wizard Dialog** (`Importazione.jsx`):
  - Bottone "Wizard Mapping" sempre disponibile in alto a destra.
  - Dialog con tab per tipo (compagnia/ramo/collaboratore/prodotto/garanzia), contatore per tab, righe con select del candidato DB.
  - Empty-state: "Tutte le entità sono mappate" + bottone "Applica back-fill" comunque disponibile.
  - Footer con "Salva mappature" e "Salva e applica" (back-fill immediato sui record esistenti).
  - Bottone "Apri Wizard" all'interno del report post-import quando `entita_non_mappate.length > 0`.
- ✅ **Fix routing**: aggiunto alias `/importazioni` (la sidebar usava il plurale, la route esisteva solo al singolare `/importazione`).
- ✅ **Test passati**: BE 6/6 pytest (`/app/backend/tests/test_iter22_wizard_mapping_omnia.py`), FE E2E Playwright (wizard dialog + tabs + righe + salvataggio + back-fill).

### Pending / In progress
- 🟡 **Targhe / Libri Matricola** (P0 — non avviato): tab UI stub presente, parser CSV generico con mapping colonne manuale da implementare (backend `/api/import/targhe/*` + dialog FE).
- 🟡 Refactor `server.py` (continuazione estrazione `routes/`): polizze/titoli/brogliaccio/sinistri.
- 🟡 Email/SMS/WhatsApp provider config (UI fatta, SMTP/Twilio da finalizzare).

### Latest Session (Iter 23 — Estrazione anagrafiche + Lock Prima Nota + Banner UX + Documenti Titoli + Alert & Automazioni)

### Done — Alert & Automazioni (NUOVA SEZIONE)
- ✅ **Modelli backend** (`alert_models.py`): `AlertRule`, `AlertEvent`, `Notification`.
- ✅ **Dispatcher multi-canale** (`alert_dispatcher.py`): adapter in-app (attivo), email SMTP (attivo se configurato), SMS Twilio (predisposto), WhatsApp Twilio (predisposto). Template con placeholder `{nome}`, `{numero_polizza}`, `{importo}`, ecc. Lookup destinatari (cliente/collaboratore/collaboratore_sinistri/admin).
- ✅ **Catalogo 11 regole preset** (`alert_presets.py`) seedate idempotenti: sinistro aperto/chiuso/pagato, sinistro importato ANIA, polizza emessa, compleanno cliente, documento ID scaduto, titolo scaduto >5gg, sospesi/arretrati settimanali al collaboratore, polizza in scadenza senza rinnovo.
- ✅ **Router** `routes/alert.py`: CRUD regole, toggle, test (invia a me), storico eventi, centro notifiche utente (`/notifications/me`, unread-count, mark-read, archivia).
- ✅ **Hook eventi**: `POST /polizze` → `polizza.emessa`. `POST /sinistri` → `sinistro.aperto`. `PUT /sinistri` (cambio stato chiuso/pagato) → `sinistro.chiuso` o `sinistro.pagato`.
- ✅ **Frontend** pagina `/alert` (`Alert.jsx`): tabella regole + filtri tipo + toggle + editor template (canali, destinatari, soglia, oggetto/corpo) + tab storico invii.
- ✅ **Campanella notifiche in TopBar** (`NotificheBell.jsx`): badge counter unread, polling 30s, dropdown ultime 20 notifiche, "Segna tutte come lette", archiviazione singola, click → naviga al link entità.
- ✅ Sidebar: nuova voce "Alert & Automazioni" sotto Assicurazione.
- ✅ Test live: regola "Sinistro aperto" attivata → test invia notifica in-app all'admin, badge campanella → 1, dropdown mostra notifica.

### Configurazione canali (env vars opzionali)
- Email Gmail: `SMTP_HOST=smtp.gmail.com SMTP_PORT=587 SMTP_USER=tuomail@domain SMTP_PASSWORD=app_password SMTP_FROM=tuomail@domain`
- Twilio SMS: `TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_SMS_FROM`
- Twilio WhatsApp: `TWILIO_WA_FROM=whatsapp:+...`



### Done — Estrazione `routes/anagrafiche.py` (P0)
- ✅ Estratto blocco 1 (25 endpoint, ~727 righe): KPI custom, tags, stats, CRUD, network, relazioni, documenti, privacy GDPR, firma digitale, INPS auto, interviste.
- ✅ `server.py`: 9.164 → **8.437 righe** (-727).
- ✅ Helper `_normalize_upper`, `_auto_geocode`, `UPPER_FIELDS`, `ANAGRAFICA_DOC_TIPI` migrati al nuovo router.
- ✅ Smoke test verde su `/anagrafiche`, `/anagrafiche/stats`, `/anagrafiche/tags`.

### Done — Lock Prima Nota chiusa (P1 — bug critico)
- ✅ Helper `shared.assert_giornata_aperta(data)` introdotto.
- ✅ Check applicato in: `PUT/DELETE /titoli/{tid}`, `PUT/DELETE /rappel/{rid}`, `DELETE /collaboratori/.../voci-manuali/{vid}`.
- ✅ Movimenti già coperti via `chiusura_id`. Sospesi sono Titoli (coperti dal check titoli). Estratti conto sono view aggregati (no lock necessario).
- ✅ Test live: tentativo modifica/delete titolo in giornata chiusa → 400 "Prima Nota del 2026-06-23 chiusa — riaprire la chiusura per modificare il titolo."

### Done — Documenti multipli sui Titoli (P1)
- ✅ Fix bug `bulk-azione-allegato`: l'allegato veniva linkato solo a "anagrafica" — ora viene creato un record `Allegato(entita_tipo="titolo", entita_id=tid)` per OGNI titolo selezionato + 1 sulla anagrafica per visibilità diario.
- ✅ `GET /polizze/{pid}` ora include `allegati_count` per ogni titolo (visibile in PolizzaDetail → tab Titoli).
- ✅ Frontend: aggiunta colonna "Allegati" con `AllegatiCell` in PolizzaDetail tab Titoli. `Titoli.jsx` già usa AllegatiCell.
- ✅ Allegati supportano upload multipli (più chiamate a `/allegati POST` con stesso `entita_id`).

### Done — Titoli vs Titoli Storici (UX split)
- ✅ **Pagina Titoli** (`/titoli`): solo titoli **da incassare / sospesi**. Preset: Sospesi, Scadute oggi/5gg/10gg/15gg/Oltre 15gg, Tutti (da incassare). Default escluso `incassato/stornato`.
- ✅ **Pagina Titoli Storici** (`/titoli-storici` — nuova route): solo titoli **incassati**. Preset: Tutti incassati, Anno corrente, Mese corrente. Colonne extra "Incassato il" + "Pagato con".
- ✅ Backend: nuovo param `stato_not` su `GET /titoli` (CSV di stati esclusi).
- ✅ Sidebar aggiornata: "Titoli" sotto Assicurazione, "Titoli storici" sotto Contabilità.
- ✅ Wrapper `TitoliStorici.jsx` = `<Titoli storicoMode />` (zero duplicazione codice).

### Done — Banner UX "Prima Nota chiusa"
- ✅ Nuovo endpoint `GET /contabilita/giornata-stato/{data}` (compatto + `can_riapri` per admin).
- ✅ Nuovo endpoint `GET /contabilita/giornate-chiuse?dal=&al=`.
- ✅ Componente riusabile `<ChiusuraGiornoBanner data={...} />`: banner giallo con icona, messaggio + pulsante "Riapri Prima Nota" (solo admin) che linka direttamente a Contabilità → Storico.
- ✅ Integrato in: `DialogIncasso` (data_incasso), `DialogIncassoCopertura` (incasso + copertura), `NuovoMovimentoDialog`, `GirocontoDialog`. Banner appare dinamicamente quando l'utente sceglie una data in giornata chiusa.

### Mypy gate
- ✅ Continua a passare (9 file core type-safe). `routes.anagrafiche` con relaxed rules pending Pydantic response models (P2).
- ✅ Script CI: `/app/backend/scripts/check_mypy.sh`.



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
- mypy strict-mode in CI sui core modules. ✅ DONE in iter23
- Test data drift fixes (9 test pre-esistenti falliscono per state DB / behaviour change su ragione_sociale uppercase, brogliaccio close_day, statistiche endpoint).

## Credenziali test
admin@assicura.it / Admin123!
