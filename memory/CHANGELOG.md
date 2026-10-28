# Changelog — Axicura CRM


## 2026-06 — Fix: dati non visibili dopo import Carichi Mensili
- **Problema**: dopo un import CSV/Excel ("ho importato il file ma non ci sono i dati"), i titoli venivano creati correttamente (es. 493) ma NON apparivano in griglia: il filtro di default ("Preset mese attivo") mostra i titoli per scadenza del mese corrente, mentre i titoli importati hanno effetto/scadenza nel periodo importato → risultavano nascosti.
- **Fix backend** (`routes/carichi_mensili.py` → `import_apply`): la risposta include ora `effetto_min` / `effetto_max` calcolati sui titoli effettivamente caricati/sovrascritti.
- **Fix frontend** (`pages/CarichiMensili.jsx`): al termine dell'import il callback `onImported` imposta automaticamente il range date decorrenza (`dal`/`al`) sul periodo importato, così i titoli appena caricati sono subito visibili.
- **Verifica**: riprodotto in UI reale sul tenant con dati reali — dopo import la griglia passa automaticamente a 01/11/2026–30/11/2026 e mostra i 493 titoli. Dati di test ripuliti.


## 2026-06 — Ciclo di vita documento firmato + Provider di firma per agenzia
### Modelli: "Card Documentale di Riferimento"
- `TemplateModello.document_target_card` (db_models.py) + `ModelloBody.document_target_card` (routes/modelli.py).
- Librerie.jsx: dropdown "Card Documentale di Riferimento" (data-testid `modello-target-card`) raggruppato per Anagrafica/Polizza/Sinistro (costante `CARD_TARGET_GROUPS`). Salvato sul modello.
- documenti_genera.py: la categoria dell'allegato generato eredita `document_target_card` del modello (fallback su categoria esplicita → `documento_generato`). Così il PDF firmato finisce nella card giusta.

### Webhook YouSign + archiviazione automatica
- `POST /api/esignature/webhook/yousign` (pubblico, SENZA verifica firma, scelta utente). All'evento `signature_request.done`/`signer.done` conferma lo stato via YouSign, scarica il PDF firmato e chiama `_finalizza`. Poller ogni 2 min resta come backup.
- `_finalizza` ora propaga `agenzia_tenant_id` (dal rec o dall'allegato originale) all'allegato firmato: fondamentale perché poller/webhook girano SENZA contesto utente.
- DocumentiSezioneSplit.jsx `FirmaBadge`: badge "🟢 Firmato con YouSign/eSignature OpenAPI · data/ora" (data-testid `firma-done-badge-*`), mappa `firmeBySigned`.

### Provider di firma per agenzia (Super Admin)
- `firma_provider` ('yousign' | 'openapi') per-tenant in `azienda_config`. Esposto in GET/PATCH `/super-admin/agenzie` e `/super-admin/agenzie/{tid}`; normalizzato (`_norm_firma_provider`, valori legacy tipo 'namirial' → yousign); rimosso da `_CHIAVI_AZIENDA` globale.
- SuperAdminPanel.jsx EditAgenzia: selettore "Provider di firma" (data-testid `ea-firma-provider`).
- esignature_it.py `invia_per_firma`: dispatch per provider (`_firma_provider()`); OpenAPI → `esvc.create_signature` (provider rec `openapi_esignature`), altrimenti YouSign.
- Fix: in `update_agenzia` il check 404 tenant avviene PRIMA dell'upsert azienda_config (niente config orfane).
- Testato (iteration_124 + curl): persistenza firma_provider/document_target_card, webhook robusto, selettori UI. NON testabile e2e il signing reale (sandbox YouSign limita i destinatari; OpenAPI richiede credenziali live).



## 2026-06 — Richiesta documento PER CARD + Notifica "Nuovo Accesso"
### Caricamento documenti direttamente nella card corretta (ogni entità)
- `backend/routes/upload_link.py` generalizzato: il link pubblico ora è legato a
  `(entita_tipo, entita_id, categoria)` — anagrafica | polizza | sinistro | titolo.
  Alla ricezione il file viene archiviato DIRETTAMENTE nella card giusta:
  - card a storage fisso dell'anagrafica (ANAG_CARD_KEYS) → `anagrafiche.documenti[categoria]`;
  - polizza/sinistro/titolo → `allegati` con `categoria`=card key e `visibile_cliente` da config.
  Il cliente può caricare PIÙ file sullo stesso link. Retro-compat mantenuta per `anagrafica_id`.
  `GET /upload-links` filtra per `entita_tipo/entita_id/categoria`.
- Nuovo componente riutilizzabile `frontend/src/components/RichiediDocCard.jsx`
  (pulsante "Richiedi al cliente" + dialog: genera link, copia, WhatsApp, elimina) montato
  su OGNI card: in `DocumentiSezioneSplit` (polizza/sinistro/titolo/libro-matricola) e nelle
  card documenti di `AnagraficaDetail` (DocumentiTab). `anagrafica` passata da Polizza/Sinistro.
- Dashboard "documenti mancanti": si svuota automaticamente al caricamento (ricalcolo da
  allegati + dict documenti). Aggiunto `libretto_veicolo` al check libretto (`extras_p1p2.py`).
- Testato via API: upload su card anagrafica (dict) e su card polizza (allegato) OK; cleanup eseguito.

### Notifica di sicurezza "Nuovo Accesso" (nuovo dispositivo)
- `backend/auth_device_alert.py`: fingerprint a bassa invasività (HMAC-SHA256 di UA + rete
  coarse /24-/64; nessun IP/UA grezzo salvato). Collection `known_login_devices` con indice
  unique `(agenzia_tenant_id,user_id,device_hash)` + TTL 365gg. Segreto HMAC auto-generato e
  persistito in `app_settings` (nessuna modifica .env).
- `POST /api/auth/login` (server.py): `$inc login_count` atomico → `register_login_device`.
  Email SOLO se dispositivo nuovo E non è il primo accesso (login_count_before>0). Invio in
  background (asyncio), non blocca il login. Dedup/cooldown 24h via `last_alerted_at`.
- `resend_service.send_new_login_alert` (usa fallback SMTP→Resend→MOCK esistente).
- Testato: login A (no email, 1° accesso) → A ripetuto (no email) → B nuovo device (1 email MOCK)
  → B ripetuto (nessuna 2ª email). Verificato in MOCK mode, nessuna email reale. Cleanup eseguito.


## 2026-10-22 — Auth batch (auto-logout 10 min, email credenziali agenzia/operatore, recupero password + invalidazione sessioni) + chiavi OpenAPI.it/Gemini AI Studio
### Chiavi API (Super Admin)
- `backend/routes/super_admin.py`: aggiunto `openapi_it_bearer_token` a `_CHIAVI_AZIENDA` + sync env `OPENAPI_IT_BEARER_TOKEN` (`_CHIAVI_EXTRA_ENV`). `frontend/src/pages/SuperAdminPanel.jsx` (`ChiaviApiTab`): nuova sezione "OpenAPI.it". Chiave OpenAPI.it salvata nel vault e caricata allo startup (log `OPENAPI_IT_BEARER_TOKEN caricato dal vault`).
- Gemini AI Studio: salvata chiave `ai_studio_api_key` (formato `AQ.`) nel vault → `GEMINI_API_KEY` ri-idratata allo startup. Verificata reale (list_models 200 + generateContent "OK"). Tutte le funzioni AI testuali passano da `llm_compat` → Gemini.

### Auto-logout inattività (10 min)
- `frontend/src/contexts/AuthContext.jsx`: `logout()` ora `useCallback` con opzione `{idle}`; nuovo effetto che, solo da autenticati, traccia attività (mousemove/mousedown/keydown/scroll/touchstart/click) e dopo 10 min idle esegue logout + toast "Sessione terminata". Cleanup listener/timer su unmount. Nota: per-tab (non sincronizzato tra schede).

### Email credenziali di accesso (agenzia + operatore)
- `backend/resend_service.py`: `_send()` ora preferisce **SMTP admin** (azienda_config `smtp_host`/`smtp_user`, es. Gmail configurato in Librerie › Comunicazioni) → invio reale; fallback Resend → MOCK (log `[EMAIL MOCK]`). Nuovi template `send_user_credentials` (operatore) e `send_password_reset`; `send_agency_credentials`/login_url ora usano `_app_base()` (env `APP_BASE_URL`, default gestionaleschianta.it).
- `backend/server.py` `create_user` (POST /api/auth/users): invia email credenziali operatore (email + password temporanea + link) quando `accesso_software=true` e password presente. Agenzia: `create_agenzia` già invia `send_agency_credentials`.

### Recupero password + invalidazione sessioni (playbook integration_expert)
- `backend/auth.py`: token access/refresh ora includono `iat`; `require_user` rifiuta token con `iat < user.token_valid_after` (401) → tutte le sessioni precedenti cadono dopo un reset.
- `backend/server.py`: `POST /api/auth/password-reset/request` (non-enumerabile, risposta identica, email inviata in **background** via `asyncio.create_task` per eliminare la differenza di timing; token `secrets.token_urlsafe(32)`, salvato solo hash SHA-256 in `password_reset_tokens`, TTL 45 min, monouso) e `POST /api/auth/password-reset/confirm` (claim atomico `find_one_and_update`, nuova password bcrypt, `token_valid_after=now+1s`).
- `frontend`: nuove pagine `ForgotPassword.jsx` + `ResetPassword.jsx`, route `/forgot-password` e `/reset-password` in `App.js`, link "Password dimenticata?" in `Login.jsx`.
- Verifica: backend e2e (confirm 200, login nuova pwd 200, vecchia pwd 401, token monouso, vecchio access token→401). Testing agent iteration_113: backend 5/5, frontend 4/4, 0 bug critici. Email SMTP non configurato → tutto in MOCK (nessun invio reale). Dati temporanei ripuliti.


## 2026-10-22 — Documenti Compagnie + Avvisi scadenza documentali (app+email) + verifica Visibilità
### 1) Documenti Compagnie (come Azienda)
- `backend/db_models.py` `Compagnia`: aggiunto campo `documenti: list = []`.
- `backend/server.py`: nuovi endpoint `POST /api/compagnie/{cid}/documenti` (upload multiplo per tipologia su object storage, max 10MB) e `DELETE /api/compagnie/{cid}/documenti/{item_id}`. `PUT /api/compagnie/{cid}` ora fa `pop('documenti')` per non sovrascrivere i documenti col salvataggio del form.
- `backend/server.py` CARD_DEFS: aggiunta entità `compagnia` (Convenzione/Mandato, Accordo provvigionale, Circolari, Listini, Altro) → appare nel pannello Librerie → Visibilità documenti.
- `frontend/src/pages/Compagnie.jsx`: sezione "Documenti" (`comp-documenti-sezione`) nel dialog modifica (DocumentiCompagnia + CompDocFolderCard): upload multiplo, tipologia, descrizione, date rilascio/scadenza, eliminazione. In creazione mostra hint (`comp-documenti-hint`). Fix stato dialog: `key` su CompagniaDialog + `load()` alla chiusura.
- `frontend/src/pages/Librerie.jsx`: `compagnia` aggiunta a `ENTITA_LABEL`, `ENTITA_ORDINE` e stato newCard.

### 2) Avvisi scadenza documentali (opt-in per singolo documento, app + email)
- `frontend/src/components/AvvisoScadenzaControl.jsx` (nuovo): pulsante "Attiva avviso" su ogni documento con `data_scadenza`; giorni di preavviso configurabili (default 15, range 1-365). Usato in Compagnie, Agenzie partner e Azienda.
- `backend/server.py` `PUT /api/documenti/avviso`: persiste `avviso_attivo`/`avviso_giorni` sul documento (entità compagnia | agenzia_partner | azienda); 404 se item inesistente; all'attivazione crea/riattiva automaticamente la regola alert `documento_aziendale_scaduto` (`_ensure_regola_avviso_documenti`).
- `backend/alert_models.py`: nuovo `schedule_kind` `documento_aziendale_scaduto`.
- `backend/alert_presets.py`: nuovo preset template "Avviso scadenza documento aziendale" (canali app+email).
- `backend/scheduler_alert.py`: resolver `_res_documenti_aziendali_in_scadenza` → rileva i documenti con avviso attivo la cui scadenza cade ESATTAMENTE tra `avviso_giorni` giorni (preavviso per-documento, fallback al default della regola). Verificato: match a 15gg, nessun match a 3gg.

### 3) Verifica Visibilità documenti (end-to-end)
- Pannelli Visibilità per collaboratore, agenzia_partner, azienda e compagnia verificati via testing agent (toggle visibile/interno, obbligatoria, card custom, salvataggio + persistenza). 100% dopo fix Compagnie.jsx.

Note: nessuna email reale inviata nei test; tutti i dati di test rimossi.


## 2026-06 — Portale Cliente: isolamento multi-tenant del login (P0 sicurezza)
Problema: il login del portale cercava l'anagrafica globalmente per email+CF e prendeva la PRIMA corrispondenza, il token non salvava il tenant (leggeva `tenant_id` inesistente invece di `agenzia_tenant_id`) e nessuna query filtrava per tenant. Un cliente presente in più agenzie poteva vedere le polizze dell'agenzia sbagliata.
- `backend/portale_cliente.py`:
  - `_issue_token` ora riceve il tenant autorevole `agenzia_tenant_id`.
  - `current_cliente` ricava il tenant SEMPRE dal DB (`ana.agenzia_tenant_id`), lo espone come `cliente["_tenant_id"]` e rifiuta (401) i token il cui `tid` non coincide col DB.
  - `POST /api/portale/auth/login`: accetta `slug` opzionale → con il link personale `/c/{slug}` il login è vincolato a QUELLA anagrafica/tenant (verifica email+CF/PIVA). Senza slug: se le credenziali valide esistono in più agenzie risponde `{status:"tenant_selection_required", challenge, agencies:[{aid,label}]}`.
  - Nuovo `POST /api/portale/auth/login/select-tenant`: completa il login con challenge monouso (TTL 5 min, collection `portale_login_challenges`).
  - Filtro `agenzia_tenant_id` aggiunto (defense-in-depth) alle query portale: polizze, titoli, polizza/titoli, documenti (pol_ids/sin_ids), nuclei collegati.
- Frontend:
  - `PortaleLanding.jsx`: salva anche `portale_slug` in sessionStorage prima di `/portale`.
  - `PortaleCliente.jsx` `LoginScreen`: invia `slug`, gestisce la schermata "Scegli l'agenzia" (`portale-agency-select`, `portale-agency-option-{aid}`) e chiama select-tenant; pulisce sessionStorage al successo.
- Test API (dati temporanei su 2 tenant, poi rimossi): slug A→solo polizza tenant A, slug B→solo tenant B, login generico→disambiguazione con 2 agenzie, select-tenant→solo tenant scelto, riuso challenge→401, password errata→401. Tutti superati.


## 2026-06 — Librerie → Utenti/Collaboratori: nuova "Gestione utente" a 6 tab
- Riorganizzato il dialog `UtenteForm` (`frontend/src/pages/Librerie.jsx`) secondo le schermate del gestionale, con 6 tab:
  **Generale** (tipologia_utente, mansione, carica, Amministratore?/Ruolo sincronizzati, responsabile/svolge/addetto intermediazione, deleghe_poteri, data_cessazione_account + blocco provvigioni/sottorete/note interne conservato),
  **Anagrafica** (cognome_ragione_sociale, nome_proprio, luogo/data nascita, 3 indirizzi via/CAP/città residenza-sede-ufficio, CF, P.IVA, cellulare, tel/fax ufficio, PEC, codice gestionale, IBAN, avatar),
  **RUI / IVASS** (albo, sezione A/B/C/D/E/F, n° iscrizione, qualifica, data iscrizione),
  **Contratti** (lista contratti + lista dichiarazioni via `AllegatoManager` + 2 campi dichiarazione sintetica),
  **Certificati** (lista certificati + slot "Documenti personali" esistenti),
  **Formazione** (`CorsiCollaboratore` potenziato: titolo, argomento, data, ore/minuti, attestato, filtro per anno).
- Backend (`server.py`): nuovi endpoint `POST/DELETE /api/auth/users/{uid}/allegati/{categoria}` (categoria ∈ contratti|dichiarazioni|certificati), estesi `POST /corsi` e `/corsi/upload` con argomento/data/ore/minuti/anno.
- Modello `UserPublic` (`db_models.py`) esteso con i nuovi campi scalari + array `contratti_collab`, `dichiarazioni_collab`, `certificati_collab`.
- FIX dataloss (HIGH da testing): `GenericForm` ora accetta `omitOnSave` e NON reinvia nel PUT gli array/URL gestiti da endpoint dedicati (contratti/dichiarazioni/certificati/corsi + *_url); rimossa anche la password vuota dal payload. Legenda "Livelli di visibilità" spostata nel solo tab Generale; reset input file dopo l'aggiunta; conferma su eliminazione corso.
- Verificato: backend via curl (PUT persiste nuovi campi; allegati add/list/delete OK) e frontend via testing_agent (9/9 flussi) + screenshot.

## 2026-06 — Prima Nota: tutte le compagnie attive nel "Saldo cassa per compagnia"
- La tabella "Saldo cassa per compagnia" (brogliaccio) ora elenca **tutte le compagnie attive**,
  anche quelle a **saldo 0,00 € senza movimenti** (prima venivano saltate con `continue`).
- Filtro compagnie allineato: `attiva ≠ false` (prima `attiva == True` stretto, escludeva quelle
  col campo `attiva` assente). Coerente con `/compagnie` e col conteggio Agenzie.
- File: `server.py::_compute_saldi_compagnie`. Verificato: tenant admin 13 attive → 13 righe.

## 2026-06 — Agenzie: conteggio "mandato diretto" solo compagnie attive
- `routes/agenzie.py` ora conta nel badge solo le compagnie **attive** (sia principale che
  partner). Prima includeva anche compagnie dirette disattivate → conteggio gonfiato (es. 3 vs 2).


## 2026-06 — Premio Annuo automatico sulla scheda polizza (da titolo)
- Nuovi titoli (import Omnia/ANIA, OCR polizza, creazione manuale, creazione polizza) ora
  **annualizzano** i premi e le provvigioni della scheda polizza: **rata × n. rate/anno**
  (annuale×1, semestrale×2, quadrimestrale×3, trimestrale×4, mensile×12, unica×1).
- Si applica **solo** ai titoli tipo `nuova`, `rinnovo`, `quietanza`. **Esclusi** `sospensione` e
  `regolazione` (non modificano la polizza).
- Campi sovrascritti sulla polizza: `premio_netto`, `premio_imposte`, `premio_ssn`,
  `premio_accessori`, `diritti`, `premio_lordo`, `provvigioni`. Le quote **collaboratore/margine**
  si derivano a lettura dallo schema provvigionale (tab Provvigioni).
- Nessuna bonifica retroattiva: effetto solo dai **prossimi** titoli/import. La riconciliazione
  prende sempre il **titolo valido più recente** (per effetto/scadenza) → l'ultimo vince.
- Implementazione: `shared.ricalcola_premio_annuo_polizza(db, polizza_id)` + `_RATE_PER_ANNO`,
  `TIPI_TITOLO_ANNUALIZZA`. Hook in `server.py` (create polizza, create/update titolo) e
  `ania_importer._processa_titoli` (riconcilia le polizze toccate a fine import, dopo le garanzie).
- UI: tab **Premi** e **Provvigioni** della scheda polizza etichettate "· valori annui".
- Verificato: polizza semestrale rata 100/80/18/2 provv10 → annui 200/160/36/4 provv20; titolo
  sospensione più recente ignorato. Test API end-to-end + test unit motor.


## 2026-10-22 — Modelli Firma: modalità {placeholder} + Word + Librerie
- Aggiunto segnaposto `{x}` per **sbarrare una casella** (scrive una X nel punto). Verificato.
- **Pivot a segnaposto `{...}`** (niente più riquadri da trascinare): nel Word/PDF si scrivono
  `{nome_cliente}`, `{agenzia_rui}`, `{collab_rui_sezione}`, `{firma}` ecc.; in compilazione
  l'app sostituisce i segnaposto coi valori reali (pymupdf redaction) e rileva `{firma}` per
  posizionare il campo firma Yousign. Verificato con unit test (sostituzione + rilevamento firma).
- **Nuovi gruppi dati**: Cliente, Polizza, **Collaboratore** (nome, CF, email, RUI, sezione RUI),
  **Agenzia** (ragione sociale, P.IVA, RUI, sezione RUI), data odierna. Collaboratore risolto da
  polizza o utente corrente; agenzia da `azienda_config`.
- **Supporto Word**: .docx/.doc convertiti in PDF via LibreOffice headless (installato; va
  aggiunto anche al Dockerfile Railway). Upload anche via **drag & drop**.
- **Spostato in Librerie → "Modelli Firma (PDF/Word)"** (rimossa voce di menu dedicata).
  UI: spiegazione, segnaposto cliccabili (copia), "Compila per un cliente", anteprima PDF.
- Backend: `/api/firma/modelli` (upload/list/detail/delete/compila); compila salva il PDF come
  allegato del cliente/polizza e, se c'è `{firma}`, crea la richiesta Yousign (sandbox).

## 2026-10-22 — Firma Yousign/YouTrust sandbox — TESTATA OK
- Flusso e2e verificato (crea→carica→firmatario→attiva `ongoing`). Key: `YOUSIGN_SANDBOX_API_KEY`.

## 2026-10-22 — Firma digitale Yousign/YouTrust + Designer modelli (MVP)
- **Integrazione Yousign v3 (brand YouTrust)** testata e FUNZIONANTE in sandbox
  (`https://api-sandbox.yousign.app/v3`, Bearer): crea richiesta → carica PDF → aggiunge
  firmatario (firma elettronica) → attiva (status `ongoing`). Key in `YOUSIGN_SANDBOX_API_KEY`.
  Note: livello "simple" richiede `signature_authentication_mode` ∈ otp_email/otp_sms/no_otp;
  in sandbox l'email firmatario deve appartenere all'organizzazione Yousign.
- **Designer modelli firma** (`routes/firma_modelli.py` + `pages/ModelliFirma.jsx`):
  - L'agenzia carica un PDF; il backend renderizza le pagine come immagini (pymupdf).
  - Editor visivo: trascini sulle pagine i campi **Dato** (nome cliente, CF, P.IVA, indirizzo,
    comune, CAP, provincia, email, telefono, data, n° polizza, compagnia) e il campo **Firma**;
    coordinate salvate come frazioni sul modello (riusate finché non le modifichi).
  - "Compila per cliente": scrive i dati reali dentro il PDF, lo salva come allegato, e (se
    presente campo firma) crea la richiesta Yousign con il campo firma nel punto salvato.
  - Scoping per agenzia (tenant). Endpoint sotto `/api/firma/modelli`. Voce menu "Modelli Firma".
  - Endpoint diagnostico Super Admin `POST /super-admin/chiavi-api/test-yousign`.
- Test: flusso e2e via API OK (nome scritto nel PDF verificato con estrazione testo; firma
  Yousign status `ongoing`); editor verificato nel browser sul PDF IVASS reale.
- **Pendente**: supporto Word (.docx) richiede LibreOffice (da aggiungere anche al Dockerfile
  Railway); per ora caricare PDF. Sostituzione provider Namirial/OpenAPI non ancora effettuata
  (Yousign affiancato, da promuovere a default quando confermi).

## 2026-10-22 — Verifica completa anti-doppia-registrazione (centralizzata nel backend)
- Verificati TUTTI i flussi di incasso del codice:
  - Frontend multiplo: `Titoli.jsx` e `TitoliSospesi.jsx` → `merge_copertura:true` ripristinato.
  - Frontend singolo: `DialogIncassoCopertura.jsx`, `DialogIncasso.jsx`, `PolizzaDetail.jsx`
    (incasso rapido) → NON inviano il flag, ma ora sono protetti dalla rete di sicurezza backend.
  - Backend `/titoli/bulk-incassa` (non usato dal frontend) → reso coerente (gestisce coperto
    + merge stesso giorno).
- **Rete di sicurezza centralizzata** in `incassa_titolo` (server.py): una copertura dello
  STESSO giorno dell'incasso (giornata aperta) viene SEMPRE unificata in un'unica riga
  `incasso_premio`, a prescindere dal flag → nessun flusso può più generare la doppia riga.
  Coperture di altri giorni aperti unificate solo con `merge_copertura:true`; coperture su
  giornate CHIUSE restano invariate.
- Test (DB, giornata aperta) tutti PASS:
  - singolo/bulk, copertura+incasso STESSO giorno (senza flag) → 1 riga `incasso_premio`.
  - copertura giorno precedente → 2 righe corrette su 2 giorni (storico preservato).
  - `/titoli/bulk-incassa` coperto stesso giorno → 1 riga. Dati di test rimossi.

## 2026-10-22 — FIX regressione: doppia registrazione in incasso multiplo
- Causa: `eade615` aveva rimosso `merge_copertura:true` dai flussi multipli, annullando
  la correzione `052602c`. Ripristinato.

## 2026-10-17 — Statistiche: nuova tab "Incassi" (replica cruscotto)
- Nuova tab **Statistiche → Incassi** (`StatisticheIncassi.jsx`) che replica il layout dello
  screenshot richiesto: snapshot mese (Titoli arretrati/scaduto, Sospesi Rete Vendita, Sospesi
  cliente), KPI rolling 12 mesi (Velocità di incasso / recupero cliente / recupero rete, con
  tooltip che spiegano la formula), 3 donut (provvigioni per compagnia, provvigioni per ramo,
  premi per modalità incasso) e tabella "Incassi: situazione di <Mese>" con confronto
  anno corrente / precedente / Var. %.
- **Aggiunte righe Premi Lordi e Premi Netti** (oltre a Provvigioni Attive e Nette) come
  richiesto.
- Backend: nuovo endpoint `GET /api/statistiche/incassi-situazione?anno=&mese=` (server.py)
  che aggrega i titoli (scoped per operatore se non admin). Provvigioni Nette = Attive meno le
  quote girate alla rete vendita (`provvigioni_operatori`). Premi = importo_lordo/importo_netto
  dei titoli incassati nel mese.
- Nota: il modello dati non ha i concetti proprietari esatti del gestionale di riferimento
  ("sospesi rete vendita", "velocità di recupero"): sono calcolati dagli stati titolo
  (incassato/da_incassare/insoluto) e documentati nei tooltip.
- Verificato: endpoint via curl (mese 10/2026 → Provvigioni 267,23 / Premi Lordi 1237,00,
  donut Generali/RCA/bonifico) e screenshot browser della tab.

## 2026-10-17 — Ora di Roma (Europe/Rome) con cambio ora automatico
- Aggiunto `frontend/src/lib/timezone.js` (import in `index.js`) che forza `timeZone:"Europe/Rome"`
  su tutte le formattazioni data/ora. DST automatico. Verificato: UTC 23:01 → "17/10/2026, 01:01".

## 2026-10-16 — OCR: salvataggio automatico documento nella card (robusto)
- Card "Libretto veicolo": upload unico con OCR automatico; il file è SEMPRE salvato via
  `/allegati` (categoria libretto_veicolo) prima dell'OCR. Causa radice del "non salva":
  polizza_id inviato in query string ma letto da Form() nel backend.
- Nuova polizza da OCR: PDF salvato come allegato nella card "polizza".
- `/utility/ocr-polizza`: corretto Allegato (campi errati) → categoria="polizza".

> NB: da pubblicare su Railway via **Save to GitHub**.

## 2026-06 — Vault chiavi AI Super Admin (priorità al pannello)
- Pannello Chiavi API: aggiunta chiave **OpenAI** (`openai_api_key`) oltre ad AI Studio/Gemini.
- Priorità invertita: la chiave inserita nel pannello ha SEMPRE priorità;
  `EMERGENT_LLM_KEY` resta solo fallback quando il campo è vuoto.
  - Gemini: già gestito dal shim `llm_compat` (GEMINI_API_KEY → Gemini diretto).
  - OpenAI: nuovo helper `backend/ai_keys.py` (`openai_key()`/`gemini_key()`);
    usato nei siti TTS OpenAI (`marketing_studio.py`, `notebooklm.py`).
- Sync env dal vault: `PUT /super-admin/chiavi-api` e startup `server.py`
  caricano `ai_studio_api_key→GEMINI_API_KEY` e `openai_api_key→OPENAI_API_KEY`.
- Nuovi endpoint test (non espongono la chiave): `POST /super-admin/chiavi-api/test-aistudio`,
  `POST /super-admin/chiavi-api/test-openai`. UI: pulsanti "Test AI Studio" / "Test OpenAI".
- Verificato: GET espone entrambi i campi, roundtrip salva/pulisce, test-openai con chiave
  invalida → HTTP 401, UI renderizza sezioni e pulsanti.
> NB: da pubblicare su Railway via **Save to GitHub**.

## 2026-06 — Spia provider AI attivo
- Nuovo endpoint `GET /super-admin/chiavi-api/ai-status`: riporta per Gemini e OpenAI
  se è attiva la chiave `pannello`, `emergent` (fallback) o `nessuna`. Non espone valori.
- UI pannello Chiavi API: badge colorato accanto a ogni sezione AI (verde=pannello,
  ambra=Emergent fallback, rosso=nessuna). Si aggiorna dopo ogni salvataggio.

## 2026-10-22 — Documenti personali collaboratore a card multi-documento
- Librerie → Utenti/Collaboratori → tab Certificati → "Documenti personali" ristrutturata:
  - Firma digitale resta slot dedicato (alimenta la firma dei moduli, campo `firma_digitale_url`).
  - Gli altri documenti ora sono multipli, raggruppati in card per tipologia
    (Carta d'identità, Codice fiscale, Casellario giudiziale, Carichi pendenti, Documento IBAN, Altro).
- Backend: aggiunta categoria `documenti` a `_ALLEGATO_CATEGORIE`; nuovo array `documenti_collab`
  in UserPublic (db_models). Riusa gli endpoint `/auth/users/{uid}/allegati/{categoria}` (POST/DELETE).
- Frontend (Librerie.jsx): riscritto `DocumentiCollaboratore` + nuovo `DocFolderCard`;
  rimosso `DOC_TIPI` (slot fissi); `documenti_collab` aggiunto a `omitOnSave` di UtenteForm.
- Verificato: upload con tipologia → raggruppamento in card → eliminazione (curl admin) + smoke UI.

## 2026-10-22 — Documenti Azienda (sezione Librerie → Azienda) + pannello Visibilità documenti
**Richiesta:** regola generale confermata dall'utente — ogni volta che si chiede una "sezione documenti", va creata come CARD con più allegati e va SEMPRE creato anche il relativo pannello in «Visibilità documenti».

**Backend**
- `server.py` CARD_DEFS: aggiunta entità `"azienda"` (Visura camerale, Iscrizione RUI/IVASS, Certificazioni, Polizza RC professionale, Documento IBAN, Altro). Appare automaticamente in GET/PUT `/config/card-visibilita` e in `/config/card-custom/{entita}`.
- `routes/librerie.py`:
  - `POST /librerie/azienda/documenti` (multipart: file, tipologia, descrizione, data_rilascio, data_scadenza) → upload su object storage, `$push` in `azienda_config.documenti`. Richiede file (400 se vuoto), max 10MB.
  - `DELETE /librerie/azienda/documenti/{item_id}` → elimina oggetto storage + `$pull` (404 se non trovato).
  - `PUT /librerie/azienda`: aggiunto `body.pop("documenti")` così il salvataggio generale NON sovrascrive i documenti (gestiti da endpoint dedicati).
- `db_models.py` AziendaConfig: aggiunto campo `documenti: List[dict]`.

**Frontend**
- `pages/Librerie.jsx`: nuova card `DocumentiAzienda` (data-testid `azienda-documenti-card`/`documenti-azienda`) nel tab Azienda, sotto Dati Azienda. Form aggiungi (tipologia da card-visibilita, descrizione, date rilascio/scadenza, file) + card raggruppate per tipologia via `DocFolderCard` con badge scadenza. `ENTITA_ORDINE`/`ENTITA_LABEL` estesi con `azienda`.

**Fix da test precedente (agenzie partner):**
- `pages/Agenzie.jsx`: refresh lista alla chiusura del dialog (fix stato stale dei documenti); pluralizzazione "1 documento"; sezione "Dati del mandato" mostrata solo per agenzie `tipo === partner`.
- `server.py` endpoint documenti agenzie: require file + eliminazione oggetto storage su delete.

**Verifiche:** card-visibilita espone 6 entità incl. `azienda` ✓; upload/lista/delete documento azienda via curl ✓; UI card "Documenti azienda" renderizzata ✓; pannelli Collaboratori/Azienda presenti in Visibilità documenti ✓. Deploy via Save to GitHub → Railway.

## 2026-06 — Export/stampa rispettano i filtri attivi
- Titoli: CSV, Excel e Stampa PDF ora inviano TUTTI i filtri attivi (ricerca, compagnia, ramo, tag, collaboratore, conto, prodotto, tipo pagamento, periodo su data_campo, preset arretrati/sospesi/scaduti, stato) + ordinamento colonna corrente. Backend `/export/titoli.csv|.xlsx` e `/stampa/titoli` ora passano per `list_titoli` tramite dependency `titoli_filter_params`.
- Frontend Titoli: export CSV/XLSX passano da `window.open` senza parametri a `downloadFile(...)` autenticato con `exportParams()` (filtri + sort/dir).
- Polizze: export CSV/XLSX e `/stampa/polizze` ora accettano anche `tag` ed `escludi_annullate` (prima ignorati).
- Verificato via curl: Titoli 45→11 (incassato), 31 (arretrati), range data effetto ok; Polizze 31→26 (escludi_annullate), 22 (stato=attiva).
- Nota: PDF Titoli mostra `rinnovo` come `quietanza` (coerente con unificazione terminologia).

## 2026-06 — Catalogo segnaposto completo (tutto il programma)
- `routes/modelli.py`: `_PLACEHOLDER_CATALOGO` esteso da 52 a **126 segnaposto** in 8 gruppi ordinati: Agenzia (22), Anagrafica/Cliente/Contraente (27), Polizza (28), Titolo/Quietanza (16), Sinistro (14), Compagnia (7), Collaboratore/Operatore (8), Grafica e firma (4). `_PLACEHOLDER_DISPONIBILI` ora derivato dal catalogo (nessun duplicato).
- `build_context()`: nuovi parametri `titolo_id` e `sinistro_id` con risoluzione a cascata (sinistro→polizza/cliente, titolo→polizza→cliente). Popola tutti i nuovi segnaposto: agenzia estesa (forma giuridica, p.iva, cf, rui+sezione+data, comune/prov/cap/nazione, fax, sito, banca, capitale, rea), cliente esteso (pec, sesso, stato civile, titolo studio, tipo, amministratore, prov. nascita), polizza estesa (frazionamento, netto/imposte/ssn/accessori/provvigioni, veicolo, massimali, franchigia, capitale, mandato), titolo completo, sinistro completo, compagnia estesa (codice/email/telefono/sito/referente), operatore esteso (cf/piva/iban).
- `GeneraDocBody` + endpoint `/genera` e `/genera-fedele`: passano `titolo_id`/`sinistro_id`. `_resolve_contatti` e `/comunica/render` propagano titolo/sinistro.
- Verificato: endpoint `/api/librerie/placeholders` → totale 126, gruppi corretti, sinistro con numero/data/descrizione ecc.; UI "Segnaposto {…}" renderizza tutti i gruppi ordinati.
