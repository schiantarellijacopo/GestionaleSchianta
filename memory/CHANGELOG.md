# Programma Assicurativo - CHANGELOG


## 2026-09-01 — Regolazione Premio · Cumulativa Assicurati · Automazioni Dashboard · Anagrafiche paginate

### 🟣 Regolazione Premio (sezione dedicata) — NUOVO
- Modello `Polizza`: aggiunti `regolazione_giorni_invio` (default 30, modificabile), `regolazione_stato` (workflow), `regolazione_lettera_inviata_data`, `regolazione_titolo_id`, `regolazione_note`.
- `backend/routes/regolazione_premio.py`: `GET /regolazione-premio` (lista con data_invio_prevista=scadenza+giorni, stato, da_inviare), `/stats`, `POST /{id}/lettera-pdf` (PDF), `POST /{id}/invia-lettera` (manuale o email SMTP con allegato), `POST /{id}/stato`, `POST /{id}/genera-titolo` (crea Titolo tipo=regolazione), `GET /{id}/eventi`.
- `backend/pdf_regolazione.py`: lettera richiesta dati al contraente.
- Calcolo esistente (`extras_p1p2.py`) ora imposta stato `calcolata`.
- Frontend: pagina `/regolazione-premio` (sidebar "Regolazione Premio"), config flag+base+tasso+minima+giorni nel form polizza (tab Altri), dialoghi lettera/calcolo/genera-titolo.
- Testato: 18/18 backend + frontend (iteration_59).

### 🟦 Cumulativa Assicurati (polizze non-RCA es. Ritiro Patente) — NUOVO
- Modello `Polizza`: `is_cumulativa_assicurati`.
- `backend/routes/cumulativa.py`: CRUD `/polizze/{id}/assicurati` (+stats), `PUT/DELETE /assicurati/{id}`, `POST /polizze/{id}/assicurati/import` (Excel/CSV con auto-detect header COGNOME/NOME/DITTA/ENTRATA/USCITA; import reale 145 righe verificato). Stato attivo/uscito calcolato da data_uscita.
- Frontend: `components/AssicuratiTab.jsx` (tab "Assicurati" nel dettaglio polizza), flag nel form polizza.

### ⚡ Dashboard "Automazioni di oggi" — NUOVO
- `GET /dashboard/automazioni-oggi`: aggrega `alert_events` di oggi + sinistri aperti/liquidati, raggruppati per categoria (compleanni/scadenze/solleciti/sinistri) con drill-down invii.
- Frontend: widget `AutomazioniOggiWidget` nella Dashboard con contatori e drill-down espandibile.

### 🚀 Anagrafiche — paginazione server-side (scalabilità 10k+ / multi-utente)
- `GET /anagrafiche?paged=true`: paginazione + filtri server-side (q, tag, categoria con_polizze/senza_polizze/condominio, compleanno, doc), proiezione LEGGERA (esclude `documenti`), conteggi categoria globali. Ritorna `{items,total,page,pages,conteggi}`. Legacy array preservato per gli altri consumer.
- Frontend `Anagrafiche.jsx`: rimossi filtri/sort client-side, ora tutto server-side con controlli di paginazione. Perf: pagina 50 in ~0.2s / 28KB su 3188 anagrafiche (prima caricava tutti i doc completi).



## 2026-02-11 (parte 2) — Firma Elettronica Namirial + Estensioni Portale

### 🖊 Firma Elettronica Avanzata (Namirial eSignAnyWhere v6)
Adapter provider-neutrale con supporto 4 modalità: **OTP SMS · OTP Email · Grafometrica tablet FEA · Link remoto (WhatsApp/SMS/Email)**.
- `backend/firma_provider.py`: SDK client eSAW v6 (`upload_pdf`, `create_envelope`, `get_status`, `download_signed_pdf`, `verify_webhook_signature`). Credenziali da `azienda_config.firma_*`.
- `backend/firma_router.py`: endpoint `/api/firma/*` (crea/lista/dettaglio/scarica/webhook). Webhook dedup via SHA256, refresh status ufficiale, auto-download PDF firmato + audit trail come `allegato` (visibile cliente nel Portale).
- `frontend/pages/ImpostazioniFirme.jsx`: pannello admin (sidebar "Amministrazione → Firma Elettronica").
- Verificato: chiamata reale a `demo.esignanywhere.net/Api/v6/file/upload` risponde 401 con token fake (conferma client ben formato).

### 🐛 Fix Portale Cliente
- Documenti veicolo: lettura accetta sia `entita_tipo=applicazione_matricola` sia `entita_tipo=polizza+applicazione_matricola_id`
- Login multi-anagrafica stessa email: itera anagrafiche e trova quella con CF/P.IVA che matcha
- Storico Titoli/Quietanze inline nella PolizzaCard con quietanze scaricabili
- Icona ramo automatica (Car/Home/Heart/Building2/Shield) condivisa fra Portale e gestionale principale

### 📁 Storico Avvisi
- Bottone **Rimanda** su ogni riga: reinvia email/WhatsApp con lo stesso testo, clone record con `rimandato_da_avviso_id`



## 2026-02-11 — Portale Cliente completato + Notifiche + Chat integrata

### Feature "Portale Cliente" — configurazione multi-canale
- **Helper unificati** `notification_helpers.py` con `send_email()` e `send_whatsapp_message()`:
  - SMTP: legge config da `db.azienda_config` (Librerie → Azienda) o env fallback (`SMTP_HOST/PORT/USER/PASSWORD/FROM`)
  - WhatsApp: legge Evolution API da `db.whatsapp_server_config` + prima istanza connessa in `db.whatsapp_instances`, env fallback `WHATSAPP_API_URL/API_KEY/INSTANCE`
  - Entrambe non sollevano eccezioni: ritornano `{ok, error?}` così il chiamante può loggare in `notifiche_portale`
  - Fix bug: gli endpoint di sollecito veicoli e credenziali portale importavano `send_email/send_whatsapp_message` da `server.py` che NON esistevano al livello modulo (era il motivo per cui l'invio credenziali fallisce sempre silenziosamente)

### Dashboard: widget "Richieste dal Portale Cliente"
- Nuovo task in `/api/dashboard/tasks` con `key="richieste_portale"` che conta `db.richieste_cliente` con `stato=da_verificare`
- Link diretto a `/richieste-cliente`
- Palette violet + icona `Inbox` (lucide-react)

### Subdomain routing per Portale
- Componente `PortaleSubdomainRedirect` in `App.js`: se hostname inizia con `portale.` / `clienti.` / `portal.` o compare in `REACT_APP_PORTALE_HOSTS`, redirige automaticamente tutte le route diverse da `/upload-doc` verso `/portale`

### Template Welcome + Chat interna ↔ cliente
- Nuovo preset `welcome_portale` in `alert_presets.PRESETS` (evento `portale.benvenuto`, canali email+whatsapp) → visibile e importabile dal catalogo Alert
- Endpoint `POST /api/anagrafiche/{aid}/invia-credenziali-portale` ora carica il template personalizzato da `db.alert_rules` se esiste con `preset_key="welcome_portale"`, sostituisce `{nome}`, `{link}`, `{email}`, `{tipo_credenziale}`, `{password}` e ritorna anche gli errori dettagliati per SMTP/WA
- **Chat Portale ↔ Agenzia** (collection `db.chat_portale`):
  - Cliente (Portale): `GET/POST /api/portale/chat/messaggi`, `GET /api/portale/chat/unread` — nuova sezione "Chat con l'agenzia" in `PortaleCliente.jsx`
  - Admin (CRM): `GET /api/chat-portale/clienti`, `GET/POST /api/chat-portale/{aid}/messaggi`, `GET /api/chat-portale/unread` — nuovo tab "Portale Clienti" in `Chat.jsx`
  - Aggregate MongoDB permissivo su tenant_id null per compatibilità dati legacy/demo

### File toccati
- Backend: `notification_helpers.py` (nuovo), `server.py`, `portale_cliente.py`, `sollecito_veicoli.py`, `alert_presets.py`, `routes/dashboard.py`
- Frontend: `App.js`, `pages/Dashboard.jsx`, `pages/Chat.jsx`, `pages/PortaleCliente.jsx`


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
