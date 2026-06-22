# Programma Assicurativo - CHANGELOG

## 2026-06-22 — fork 2 (sessione corrente)

### OCR polizza + estensione patente/passaporto + tag lavoratore
- **OCR Polizza** (`ocr_polizza.py` + `/api/utility/ocr-polizza`) via Gemini Vision: PDF polizza italiana → JSON con numero_polizza, compagnia, ramo, prodotto, date (decorrenza/scadenza/emissione), frazionamento, premi (lordo/netto/imposte/provvigioni/diritti), contraente (CF/P.IVA/indirizzo), assicurato, veicolo completo (targa/marca/modello/cilindrata/alimentazione), bonus_malus, garanzie con massimali/franchigie/premio, valore veicolo, guida esperta/esclusiva, rinuncia rivalsa
- Per i PDF processa **prime 2 pagine** (frontespizio + dettagli) combinate verticalmente
- Form Nuova Polizza con toolbar OCR: carica PDF → auto-match compagnia per nome + contraente per CF/P.IVA + popola tutti i campi; warning per match mancanti; il file viene anche salvato come allegato della polizza
- **OCR esteso a patente e passaporto** (`/api/utility/ocr-documento-identita`): prompt unificato CI/patente/passaporto, restituisce tipo_documento, dati anagrafici, scadenza, numero, categorie patente (lista B/BE/A1...)
- `DocumentiTab` di AnagraficaDetail: caricando CI/patente/passaporto → OCR automatico, propone aggiornamento campi anagrafica via conferma utente, file salvato come documento del tipo corretto

### Tag automatici estesi
- Aggiunto campo `tipologia_lavoratore` su Anagrafica (dipendente/autonomo/professionista/imprenditore/pensionato/disoccupato/studente/casalinga) + `professione` + `datore_lavoro`
- Auto-genera tag include ora: `dipendente`, `autonomo`, `professionista`, `imprenditore`, `pensionato`, ecc. (dal campo tipologia)
- Tag `figli_minori` (alias di `genitore_con_figli_minori`) per più clarità
- Form anagrafica (sia nuova creazione che modifica) include sezione "Lavoro" con dropdown tipologia + professione



### Marketing + OCR visura camerale + CI in documenti
- **OCR Carta Identità** ora accetta param opzionale `anagrafica_id`: se passato, salva il file originale come documento `carta_identita` nella scheda cliente (insieme all'estrazione dati)
- **Nuovo OCR Visura Camerale** (`ocr_visura.py` + `/api/utility/ocr-visura-camerale`) via Gemini Vision: estrae ragione sociale, P.IVA, CF ditta, REA, capitale sociale, sede, oggetto sociale, codice ATECO, stato attività, codice ateco, telefono, PEC, email, + array completo `amministratori` con cognome/nome/CF/data nascita/comune nascita/indirizzo/ruolo/poteri/data nomina
- **Form Nuova Anagrafica**: toolbar OCR dinamica — su persona fisica carica CI, su persona giuridica carica visura camerale. Sul submit:
  - File CI → salvato come documento anagrafica
  - File visura → salvato come documento anagrafica
  - Per ogni amministratore estratto → crea automaticamente la sua anagrafica persona fisica con nota "Ruolo nella ditta X: amministratore"
- **Pagina Marketing** (`/marketing`) con 3 tab:
  - **Newsletter**: editor email + selezione multi-tag (chip cliccabili) + preview destinatari count + invio
  - **Campagne (Pipeline)**: griglia pipeline marketing con badge counts (fasi/lead)
  - **Tag clienti**: bottone "Auto-genera tag su tutti i clienti" + statistiche tag con conteggi
- **Sidebar**: nuova voce "Marketing" sotto Strumenti



### Pipeline custom + sezione marketing
- Modelli `PipelineCustom` + `PipelineCard` + `PipelineColonna`
- CRUD pipeline: `/api/pipelines`, `/api/pipelines/{pid}` (PUT/DELETE) + colonne (add/edit/delete con spostamento card) + cards
- Endpoint `pipeline/{entita}/{id}/move` esteso a supporto pipeline custom
- Template pronti per: marketing, vendita, onboarding, supporto, generico
- Frontend Pipeline.jsx con tab dinamiche, "+ Nuova pipeline" wizard, "Gestisci colonne" (rinomina/colore/elimina), Dialog nuova/edit card con anagrafica/operatore/valore/priorità/scadenza
- Drag&drop card tra colonne (HTML5 native, no librerie)

### Documenti anagrafica + INPS auto + sidebar drag&drop + preferenza pagamento
- **Backend**:
  - Modello Anagrafica esteso: `documenti` dict, `firma_cliente_url`, `privacy_firmata_url`, `preferenza_pagamento`, `ultimo_mezzo_pagamento`
  - `POST/DELETE /api/anagrafiche/{aid}/documenti/{tipo}` per CI, patente, passaporto, CF, tessera sanitaria, visura, privacy firmata
  - `POST /api/anagrafiche/{aid}/firma-digitale` (canvas base64 → PNG)
  - `GET /api/anagrafiche/{aid}/privacy/genera-pdf` PDF informativa GDPR precompilata con dati cliente + intestazione agenzia
  - `POST /api/anagrafiche/{aid}/calcolo-pensione/auto-da-estratto` parser PDF estratto INPS → settimane (988), anni, dati anagrafici (CF, comune nascita, residenza, retribuzione media)
  - Parser INPS completamente riscritto (`inps_calculator.parse_estratto_contributivo`): regex per header anagrafico + righe contributive (sett./giorni)
  - Endpoint incasso aggiorna automaticamente `ultimo_mezzo_pagamento` sull'anagrafica del cliente
- **Frontend**:
  - Tab "Documenti" su AnagraficaDetail con 7 card (CI/patente/passaporto/CF/tessera sanitaria/visura/privacy) + click-to-upload + bottone "Genera PDF privacy"
  - Tab "Pensione INPS" con banner sky "Carica estratto INPS" → upload PDF → auto-popolamento
  - Form anagrafica: campo "Preferenza pagamento" + display ultimo mezzo usato
  - **Sidebar.jsx riscritta**: bottone engranaggio attiva edit mode, voci diventano draggable con grip handle, ordine salvato in localStorage, "Ripristina predefinito"
  - DialogIncasso (Sospesi) precompila il mezzo pagamento con preferenza/ultimo del cliente + chip "★ Preferenza cliente" visibile



### Code Quality fixes (review report)
- **Sicurezza XSS** in `MappaClienti.jsx`: aggiunta funzione `esc()` che sanifica i dati utente nei popup Leaflet (HTML entity escape su `&<>"'`)
- **Empty error handlers** sostituiti con `console.warn` in: `MappaClienti.jsx` (geocoding), `Corsi.jsx` (progresso), `Chat.jsx` (polling), `Anagrafiche.jsx` (geocoding)
- **Undefined variables**: rimosso codice morto post-`return` in `server.py` (newsletter endpoint), variabili `ana_match_ids` / `res` non usate eliminate, `data` in `ocr_ci.py` inizializzata
- **Hook dependencies**: refactor di `load` con `useCallback` in `Anagrafiche.jsx`, `Calendario.jsx`, `TitoliSospesi.jsx`, `EstrattoContoCompagnie.jsx` (rimossi eslint-disable + dep array corretto)
- **Array index keys**: sostituiti con id stabili in `Calendario.jsx` (giorno → `dayStr`) e `EstrattoContoCompagnie.jsx` (movimento → `_movimento_id`)

### Note refactoring (non bloccanti)
- E701/E702 ruff style (`if x: y` su una riga) in server.py: lasciato — è una scelta di brevità in 47 controlli condizionali; nessun bug runtime
- Circular import auth↔seed_demo↔server: **falso positivo** — `auth.py` non importa nessuno dei due
- localStorage per JWT: mantenuto — è il pattern standard per SPA JWT-based; migrazione a httpOnly cookies richiederebbe revisione architetturale completa del flusso auth
- Complessità ciclomatica `importa_zip` (131) e altre funzioni grandi: tech debt registrato per refactor futuro in router/moduli

### Implementato (cumulativo della sessione)


### Backend
- **ANIA importer** end-to-end testato (`/app/backend/tests/test_ania_import.py`): veicolo, garanzie, diritti, BM, franchigia, massimali, rinuncia rivalsa. Re-import idempotente.
- **Modelli nuovi**: `AziendaConfig`, `SchemaProvvigionale`, `EventoCalendario`. Estensione `UserPublic` (firma digitale, CI, casellario, carichi pendenti, IBAN, corsi/attestati). Aggiunta `collaboratore_id` su `Anagrafica/Titolo/Sinistro`. Aggiunti `importo_pagato/sconto_applicato/motivo_sconto` su `Titolo`. Categoria `sconto_cliente` aggiunta a `MovimentoContabile`.
- **Librerie/Azienda**: GET/PUT `/api/librerie/azienda` + upload logo. Usato in **TUTTE le stampe PDF** (intestazione+logo+RUI+footer).
- **Sistema provvigionale**: CRUD `/api/librerie/schema-provvigionale` con risoluzione gerarchica.
- **Documenti collaboratori**: `/api/auth/users/{uid}/documenti/{tipo}`, `/api/auth/users/{uid}/corsi`.
- **Storage ACL**: `/api/storage/{path}` (admin/proprietario only per /users/).
- **Utility**:
  - `POST /api/utility/codice-fiscale/calcola` e `.../decodifica` (libreria `python-codicefiscale` con dataset ISTAT)
  - `POST /api/utility/geocoding` via Nominatim/OSM gratuito
  - `POST /api/utility/ocr-carta-identita` (Gemini 3 Flash via Emergent Universal Key, PDF+JPG+PNG)
- **Compagnie**: `GET /api/compagnie/{cid}/estratto-conto`, `/api/compagnie/saldi-cassa` + stampe PDF.
- **Calendario**: CRUD `/api/calendario` con auto-eventi scadenze polizze. Filtro per operatore.
- **List anagrafiche arricchita**: `polizze_attive_count`, `categoria_ui`, `collaboratore_nome`, filtro per tag.
- **Sospesi / titoli anticipati**: `GET /api/titoli/sospesi` arricchito (cliente, collaboratore, data copertura, scadenza, importo, giorni anticipo).
- **Copertura titoli**: ora default = OGGI (data_copertura), significato "agenzia anticipa al cliente". Titolo resta da_incassare finché cliente non paga.
- **Incasso con sconto**: endpoint `POST /api/titoli/{tid}/incassa` accetta `importo_pagato` e `motivo_sconto`. Se importo_pagato < lordo → crea automaticamente movimento entrata (importo pagato) + movimento uscita (categoria `sconto_cliente`) in prima nota. Tracciamento automatico nel diario cliente.

### Frontend
- **Anagrafiche.jsx** riscritto: dot colorati 🔵🔴🟢, filtri categoria, chip tag cliccabili, colonna operatore. Form con OCR CI, Calcola CF / Decodifica CF, Geocoding auto al blur.
- **Librerie.jsx** esteso: tab Azienda, Sistema provvigionale, Utenti/Collaboratori con sotto-tab Anagrafica/Fiscale/Documenti/Corsi.
- **Calendario.jsx** nuovo: vista mensile, eventi colorati per tipo, scadenze polizze auto, filtro operatore.
- **EstrattoContoCompagnie.jsx** nuovo: KPI cards + tabella saldi + dettaglio con filtri data + stampa PDF.
- **TitoliSospesi.jsx** nuovo: lista clienti anticipati dall'agenzia, KPI (count, importo totale, anticipo più vecchio), pulsante "Incassa" con dialog che gestisce **sconto automatico**: se importo pagato < lordo, mostra il delta in giallo e spiega che verrà registrato come uscita "sconto_cliente" in prima nota.
- **Titoli.jsx**: dialog copertura semplificato (data copertura = oggi, no più "fino al"), colonna mostra `data_copertura`.
- **Sidebar.jsx**: nuove voci Titoli (incassi), Sospesi, E/C compagnie, Calendario.

### Test credentials
Admin: `admin@assicura.it / Admin123!`
