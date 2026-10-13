# Programma Assicurativo — PRD (aggiornato 30/09/2026)
# CHANGELOG 2026-10-13 — Polizze da Email (whitelist + OCR auto-create)
- Nuovo campo azienda_config `polizze_mittenti` (whitelist email mittenti PDF polizze).
  UI in Librerie → Comunicazioni (`PolizzeMittentiSection`, data-testid `com-polizze-mittenti`).
  Salvato/normalizzato (lowercase, dedupe) via PUT /api/librerie/comunicazioni.
- Posta: nuova scheda "Polizze" (`posta-tab-polizze`) → GET /api/email/polizze-inbox
  mostra SOLO email dei mittenti whitelist CON allegato PDF. Visibilità: admin+dipendente
  (NO collaboratori).
- Estrazione automatica: POST /api/email/polizze-inbox/{eid}/estrai (routes/polizze_email.py)
  → per ogni PDF: storage.get_object → _convert_pdf_to_jpeg → ocr_polizza.estrai_dati_polizza
  (Gemini) → crea Anagrafica (se non esiste, match CF/PIVA/ragione sociale) + Compagnia
  (match/crea) + Polizza (se non esiste per numero; altrimenti allega PDF). Allegati copiati
  su polizza e anagrafica via imap_poller._copia_allegato_su_entita. Creazione AUTOMATICA
  (scelta utente; dati modificabili). No duplicati polizza.
- Riusa create_polizza (server.py) e create_anagrafica (routes/anagrafiche.py).
- Testato: endpoint whitelist (save/read/normalizza), polizze-inbox (lista/filtro),
  estrai 404 su id errato, e _estrai_una end-to-end offline (compagnia+anagrafica+polizza
  create correttamente). OCR reale + storage fetch = funzioni preesistenti provate.
- DEPLOY: richiede Save to GitHub + redeploy Railway. OCR usa EMERGENT_LLM_KEY (già su Railway).



## Sessione 12/10/2026 (fork) — Prima Nota: modifica/elimina sincronizzate + provvigioni negative
- **Modifica movimento in Prima Nota pre-compila la data REALE di registrazione** (prima proponeva oggi). Backend: `_compute_brogliaccio` ora include `data` nella riga; frontend `EditMovimentoDialog` la legge.
- **Propagazione in modifica** (solo giornata APERTA/riaperta): `PUT /api/contabilita/movimenti/{id}` → `_propaga_modifica_movimento`. Allinea il record collegato nella sua sezione:
  - ritenuta_compagnia → `ritenute_compagnia` (data + data_versamento, allineate)
  - pnc → `pnc` (data + data_versamento)
  - rappel (cat 'provvigioni' con rappel_id/is_rappel) → `rappel` (data + data_incasso)
  - titoli (incasso/incasso_coperto/incasso_direzione/copertura) → `titoli` (data_incasso o data_copertura + mezzo_pagamento + conto_cassa_id)
- **Eliminazione da Prima Nota ripristina lo stato precedente** (`_revert_entita_da_movimento`): ritenuta/PNT → stato 'da_versare'; rappel → 'da_incassare'; movimento_id/data_versamento|data_incasso azzerati. **Rimosso il blocco** che impediva di eliminare un rappel dalla Prima Nota (ora consentito come ritenute/PNT).
- **Provvigioni su titoli a premio NEGATIVO (rimborsi/storni) ora corrette** (le provvigioni collaboratore possono essere negative):
  - `_provv_breakdown`: azzera solo se `abs(tot) < 0.005` (prima `tot <= 0` azzerava anche i negativi → lista mostrava 0,00).
  - `_quota_collab_da_schema`: accetta `premio_netto` negativo (prima richiedeva `>0`).
  - Frontend `TitoloDialog.jsx`: rimossi i guard `>0` (ora `abs(q)>0.0001`); su "Eredita da polizza" la quota viene RICALCOLATA sul premio del titolo (prima copiava l'importo annuale → 21,33 errato su un titolo −49).
  - Verificato: BS BROKER su netto −49 → −2,21; su +474 → 21,33.
- Verificato end-to-end su backend preview (ritenuta/PNT/rappel: crea→versa→modifica data→allineamento→elimina→ripristino). Frontend si avvia regolarmente.
- **NB: modifiche solo in PREVIEW** — la produzione gira ancora il codice precedente: serve deploy per applicarle. (Deploy Emergent lanciato il 12/10.)
- **Pacchetto migrazione Railway creato** (l'utente valuta lo spostamento su Railway): `MIGRATION_RAILWAY.md` (guida + elenco completo variabili d'ambiente, WhatsApp/Evolution API, storage), `scripts/migrate_data_emergent_to_railway.sh` (mongodump/mongorestore Emergent→Railway), `scripts/duplicate_tenant_to_railway.py` (duplicazione filtrata per tenant `c5ae2d0e-…`, sola lettura su sorgente), `deploy/Dockerfile.backend` + `deploy/Dockerfile.frontend` + **`deploy/Dockerfile.railway`** (monoservizio: UI+API su un solo URL). Allegati restano su object storage Emergent (storage.py via EMERGENT_LLM_KEY) salvo futura migrazione a S3/MinIO. Il dump dati va eseguito dall'utente: l'Atlas di produzione Emergent ha **IP allowlist** che blocca il pod preview → usare **Republish → Database → Dump DB** e poi `mongorestore` su Railway.
- **Servizio UI statica dal backend** (`backend/server.py`, fine file): se esiste `FRONTEND_BUILD_DIR` (default `backend/frontend_build`) il backend serve la SPA React con fallback su index.html, mantenendo prioritarie le rotte `/api`. CONDIZIONALE: su Emergent la cartella non esiste → disattivato, nessun impatto. Verificato: `/`,`/dashboard`→index.html; `/static/*`→file; `/api/`→200; `/api/inesistente`→404 JSON. Architettura target utente: **Emergent=sviluppo, Railway=produzione** (utenti dal link Railway + Mongo Railway); deploy via Save to GitHub → repo `schiantarellijacopo/GestionaleSchianta` (branch main, auto-deploy).


## Sessione 12/10/2026 (fork) — Fix titoli: vista /titoli, protezione Prima Nota, ripristino coperti
- Wizard Mapping OMNIA: salvataggio collaboratori reso affidabile (endpoint BULK) + back-fill in background (no timeout 120s). Verificato.
- "Modifica titolo" dalla pagina /titoli ora carica il titolo COMPLETO (GET /api/titoli/{id}) → mostra imposte/SSN/tipo/lordo come la vista Polizza (prima erano a 0 per la projection ridotta). Verificato.
- BUG PRODUZIONE risolto: l'import OMNIA azzerava i titoli COPERTI (registrati in Prima Nota) perché la copertura lascia stato='da_incassare'. Ora l'importer salta ogni titolo in Prima Nota (titolo_coperto/data_copertura/data_incasso/importo_pagato/chiusura_id) e non azzera importi senza rec42.
- Nuovo strumento admin "Ripristina coperti" (GET/POST /api/titoli/(coperti-azzerati|ripristina-coperti-azzerati)) per riportare gli importi dei coperti azzerati al valore salvato in copertura (importo_da_pagare).
- Dettagli completi in CHANGELOG.md. Deploy in produzione lanciato il 12/10/2026.


## Sessione 01/10/2026 (fork) — Paginazione Polizze + direttiva "ottimizza tutto in automatico"

- **Polizze: paginazione lato server attiva** (FATTO, testato): `Polizze.jsx` ora carica 50 polizze/pagina (`paged/page/page_size/sort/dir`), con pager UI, ordinamento server (campi nativi) e **totali da aggregation server** (su tutti i record filtrati, non solo la pagina). Export/stampa restano su tutti i record. Verificato in preview con dati reali (jacopo): "Pagina 1 di 101 · 5048 attive", totali corretti, cambio pagina ok.
- **Statistiche/report già veloci**: `/statistiche/overview|premi-provvigioni|per-operatore`, `/cervello/*` = 0,12–0,24s (aggregazioni + nuovi indici). Nessun intervento necessario.
- **DIRETTIVA PERMANENTE rafforzata** (`/app/memory/performance_guidelines.md`): ottimizzare TUTTO in automatico (indici/projection/parallelo/paginazione) senza chiedere. Da applicare a ogni nuova funzione.



- **Incasso titolo coperto in giornata chiusa** (FATTO): nel dialog `DialogIncassoCopertura` il passo 1 faceva SEMPRE un `PUT /titoli/{id}`; il PUT (server.py:5184) controlla `data_incasso || data_competenza` → se la competenza del titolo cade in una Prima Nota chiusa (es. 23/09), bloccava con "Prima Nota del ... chiusa — riaprire la chiusura per modificare il titolo", impedendo l'incasso (data pagamento 24/09, aperta). Ora il PUT viene inviato SOLO se l'utente modifica davvero i dati base (snapshot iniziale via useRef). L'endpoint `/incassa` controlla solo `data_incasso` (giorno aperto) → l'incasso del coperto passa.



- **Payload liste ridotto** (FATTO): `/polizze` e `/titoli` usano projection a INCLUSIONE (solo campi lista) → payload da ~82/86MB a ~21/47MB (grezzo); con gzip il browser riceve ~10x meno. GZip middleware già attivo.
- **Paginazione lato server opt-in** (FATTO backend): `/polizze` supporta `paged/page/page_size/sort/dir` → `{items,total,pages,totali}` (totali via aggregation). Titoli lasciato "carica tutto" su richiesta utente.
- **/api/search parallelo + prefisso indicizzato** (FATTO): query in `asyncio.gather`; numeri/targa/CF in prefisso ancorato (usa indici). Indici DB ampliati (143).
- **Fix barra nera totali sovrapposta** (FATTO): `.tbl-scroll.has-footer` riserva spazio; applicato a Polizze e Titoli.
- **Fix elenco "Anagrafiche senza C.I." vuoto** (FATTO): DocumentiMancantiWidget leggeva male la lista.
- **Ordinamento colonne (frecce) rollout** (IN CORSO): FATTE → Polizze, Titoli (già prima), Anagrafiche (paginata), Sospesi/Anticipi (attivi+storico), Rappel, Ritenute, Pnc, RitenuteCompagnia, Voucher. Banche ESCLUSA di proposito (saldo progressivo richiede ordine cronologico). RIMANENTI: Provvigioni (tabelle da-pagare + pagati), EstrattoContoContraente, EstrattoContoCompagnie, Contabilita, CarichiMensili, Corsi, CorsiIvass, Statistiche/StatisticheClienti/PerOperatore/Premi, SinistroDetail, PolizzaDetail, AnagraficaDetail (tabelle interne), pannelli admin. Nota: le frecce compaiono solo quando la tabella ha dati.
- **Team portale: "Sede di riferimento"** (FATTO): editor `AppCliente.jsx` (tendina da sedi configurate, salvato `sede_id` in `app_cliente.py`) E visualizzazione nel **Portale Cliente pubblico** (`PortaleCliente.jsx` TeamView, badge con Building2; `portale_cliente.py` espone `sede_id`).
- **Direttiva permanente prestazioni** in `/app/memory/performance_guidelines.md`.


- **DIRETTIVA PERMANENTE**: velocità/fluidità sono priorità per TUTTE le sezioni, ricerche, filtri, caricamenti e per ogni implementazione futura. Regole operative in `/app/memory/performance_guidelines.md` (indici auto in `backend/indexes.py`, query in parallelo, upload non bloccanti, ricerche server-side+debounce, proiezioni).
- **Indici DB ampliati** (FATTO, attivi): `backend/indexes.py` esteso — anagrafiche (cognome/nome/cellulare/telefono/comune/CF/PIVA + composti tenant), polizze (prodotto/oggetto_assicurato/veicoli_ids/targa tenant), titoli (numero_polizza/contraente_id/data_scadenza/data_copertura + composti), allegati (categoria/applicazione_matricola_id), firma_requests, applicazioni, documenti_inbox, users(role). Startup: "Indici DB garantiti: 143". Creazione idempotente ad ogni avvio.
- **/api/search parallelizzato** (FATTO): le 5 query base (anagrafiche/polizze/sinistri/titoli/compagnie) ora in `asyncio.gather` invece che in sequenza → latenza molto minore.
- **Upload allegati più veloci** (FATTO): `upload_allegato` usa `run_in_threadpool` per `put_object` (non blocca l'event loop); `DialogIncassoCopertura` carica l'allegato in background.
- **🔴 FIX elenco "Anagrafiche senza C.I." vuoto** (FATTO, testato): in `DocumentiMancantiWidget.jsx` il branch `else` (tipo="anagrafiche") non assegnava `items` → dialog "Nessun risultato" nonostante il conteggio (es. 4609). Ora `items = data.anagrafiche_senza_ci`. Backend verificato: ritorna la lista correttamente.



- **OCR CI fronte/retro** (FATTO, testato): il PDF della carta d'identità ha 2 pagine (fronte + retro) ma `_convert_pdf_to_jpeg` (documenti_inbox.py) convertiva solo la pagina 0 → `data_emissione` e `comune_emissione` (sul retro) risultavano null. Ora impila fino a 3 pagine in un'unica immagine e il prompt è stato rafforzato per i campi CIE (COMUNE DI EMISSIONE, DATA DI RILASCIO/EMISSIONE, formato GG.MM.AAAA→YYYY-MM-DD). Verificato su C.I. DORMIA: comune=TIRANO, data_emissione=2026-03-12, scadenza=2036-02-16.
- **Avatar da CI affidabile** (FATTO, testato): l'avatar non veniva inserito perché il crop leggeva solo `bbox.w/.h` mentre il modello a volte ritorna `width/height` (o bbox nullo). Ora: (1) `_norm_bbox` normalizza le chiavi; (2) l'avatar usa PRIMA il **rilevamento volto OpenCV** (Haar cascade `haarcascade_frontalface_default.xml`, sceglie il volto più grande = ritratto) con fallback sul bbox OCR. Verificato: `avatar_url` popolato dal save inbox; detection sceglie il volto 192×192.
- **Upload allegato più veloce** (FATTO): in `DialogIncassoCopertura` l'upload dell'allegato ora avviene in BACKGROUND (l'operazione incasso/copertura si salva e il dialog si chiude subito; toast di esito a fine caricamento). Backend `upload_allegato`: `obj_storage.put_object` (requests sincrono) eseguito in `run_in_threadpool` per non bloccare l'event loop.



- **Selezione collaboratori per i dipendenti** (FATTO, testato via API): `GET /auth/users` (server.py) restringeva la lista ai soli non-admin verso "se stessi", quindi un DIPENDENTE non poteva selezionare altri collaboratori nelle tendine (es. ripartizione provvigioni in TitoloDialog). Nuova regola: **admin e dipendenti** vedono tutti gli utenti del proprio tenant; i **collaboratori** vedono solo se stessi. Cambiata la condizione da `if role != "admin"` a `if role == "collaboratore"`. Vale in tutto il programma perché tutte le tendine collaboratore leggono da `/auth/users`. Verificato: admin=5, dipendente=5, collaboratore=1.



- **Ricerca targa estesa alle polizze** (FATTO, testato via API): la ricerca targa (`TargaSearchWithLentina`) trovava solo i record della collezione `veicoli` (Libro Matricola). Ora `GET /veicoli?q=` e `GET /veicoli/by-targa/{targa}` cercano in fallback anche le POLIZZE con quella targa (`targa`/`oggetto_assicurato`) e ricostruiscono un record veicolo "sintetico" dai campi `veicolo_*` della polizza (helper `_veicolo_da_polizza`). Così una targa già usata su un'altra polizza (es. FA816HA MERCEDES CLA su una RCA) viene trovata e i dati riutilizzati anche su una nuova polizza. Verificato: q=ZZ999 → trova targa da polizza; by-targa → marca/modello/kw/cilindrata + polizze_collegate.
- **Regola CATTOLICA import RIMOSSA** (FATTO): rimossa la chiamata a `_applica_regola_stato_da_titoli` nella pipeline import ZIP Omnia (`ania_importer.py`). Gli import non modificano più lo stato polizza in base ai titoli (né annullamento automatico CATTOLICA né riattivazione). Nessuna correzione retroattiva.



- **Endpoint diagnostica annullamento** (FATTO, testato): nuovo `GET /api/polizze/diagnostica-annullamento?numero=<n>` (o `?pid=`), admin-only, inserito PRIMA di `/polizze/{pid}` in server.py. Cerca la polizza nel tenant e restituisce stato, data_annullamento, motivo, compagnia (flag is_cattolica), titoli incassati + ultimo_incasso, `cause_probabili` (data_annullamento→annullata, motivo, sostituzione, regola CATTOLICA senza incassi ≥2025-01-01, fallback disdetta/annul da tracciato) e `attivita_log`. Verificato via curl: path "attiva" e path "annullata" (data_annullamento + motivo Disdetta) con ripristino. Per la 184643490 (produzione) va usato dopo il deploy.
- **Sezione Dati veicolo in CREAZIONE polizza** (FATTO, testato screenshot): in `Polizze.jsx` NuovaPolizzaDialog aggiunta la sezione "Dati veicolo" (Targa+lookup Libro Matricola/polizza precedente, Marca, Modello, Tipo, Alimentazione, Uso, Immatricolazione, CV fiscali, KW, Cilindrata, Posti). Mostrata quando `showVeicolo` = ramo/prodotto matcha regex RCA/veicoli OPPURE il prodotto scelto ha `mostra_sezione_veicolo`. La targa (onBlur/Cerca) richiama `lookupTarga` che auto-compila i dati se la targa esiste. Payload pulito dai campi veicolo vuoti (i numerici del modello Polizza non accettano stringa vuota). Verificato: selezionando ramo "RC Auto" la sezione compare con tutti i campi.



## Sessione 30/09/2026 (fork) — Sezione Dati veicolo da flag prodotto

- **Fix sezione veicolo** (FATTO, testato 100%): la sezione/tab "Dati veicolo" nella scheda polizza compariva solo per ramo RCAuto. Ora compare anche quando il PRODOTTO ha il flag `mostra_sezione_veicolo=true`. Backend: `GET /polizze/{id}` risolve `doc["prodotto_mostra_veicolo"]` dal prodotto in libreria. Frontend `PolizzaDetail`: `isVeicoloPol` (view) e `isRCA` (edit) includono il flag (`_selProd.mostra_sezione_veicolo` in modifica, reattivo al cambio prodotto). Verificato: su polizza ramo "Tutela Legale" con prodotto flaggato il tab Veicolo appare e i dati (marca/modello) si salvano.
- **APERTO**: diagnosi polizza annullata 184643490 (produzione) — endpoint diagnostico admin NON ancora aggiunto (utente ha cambiato priorità sul tema veicolo). Da riprendere se richiesto: aggiungere `GET /polizze/diagnostica-annullamento` e deploy.


## Sessione 30/09/2026 (fork) — Sospesi: export Excel/PDF storico + storico autonomo in alto

- **Export Excel** (FATTO, testato): nuovi endpoint `GET /api/export/sospesi.xlsx` e `GET /api/export/sospesi-storico.xlsx` (openpyxl, helper `_xlsx_response`). Pulsante "Excel" nella toolbar dei sospesi attivi e nella toolbar dello storico.
- **Stampa PDF storico** (FATTO, testato): `GET /api/stampa/titoli/sospesi-storico` (filtro collaboratore + dal/al su data_incasso). Pulsante "Stampa PDF" nello storico.
- **Storico autonomo in alto** (FATTO, testato 100%): lo storico è ora una sezione autonoma `StoricoSospesi` collocata IN ALTO (dopo i KPI, prima del riepilogo) con toolbar propria: Cerca, Filtra per collaboratore, Incasso dal/al, Stampa PDF, Excel. Stato/filtri indipendenti dai sospesi attivi.


## Sessione 30/09/2026 (fork) — Sospesi: filtro date + storico + toolbar riordinata

- **Filtro per date** (FATTO, testato): nella pagina /sospesi due campi "Copertura dal / al" filtrano i sospesi attivi per `data_copertura` (client-side) e alimentano lo storico (server, per `data_incasso`).
- **Storico sospesi** (FATTO, testato): nuovo endpoint `GET /api/titoli/sospesi-storico` (`titolo_coperto=true` + `stato=incassato`, filtro `dal/al` su `data_incasso`, calcolo `giorni_anticipo` = copertura→incasso). Nuova card collassabile "Storico sospesi (anticipi già incassati)" in fondo alla pagina con totale incassato.
- **Toolbar riordinata** (FATTO): la barra strumenti (Cerca / Filtra collaboratore / date / Stampa PDF / Incassa selezionati) è ora SOTTO la tabella "Riepilogo per collaboratore". Ordine: KPI → Riepilogo collaboratore → toolbar → tabella sospesi → storico.


## Sessione 30/09/2026 (fork) — Badge stato firma sulle card

- **Badge stato firma** (FATTO, testato 100%): sulle card documento dell'anagrafica compare il badge "⏳ In attesa di firma" (amber) o "✓ Firmato" (verde) con la data. Backend: `esignature_it.invia_per_firma` setta `firma_stato="in_attesa"` + `firma_richiesta_at` sul dict card; `_finalizza` setta `firma_stato="firmato"` + `firma_completata_at`. Frontend `AnagraficaDetail` DocumentiTab: badge nell'header card + riga info con data; aggiornamento ottimistico dopo l'invio.


## Sessione 30/09/2026 (fork) — Firma diretta su card + Contatore CI dashboard + Inbox 3 cartelle

- **Firma diretta sulle card anagrafica** (FATTO, testato 4/4): nel tab Documenti dell'anagrafica, ogni card con un PDF mostra il pulsante "Firma" (`doc-firma-<tipo>`) → popup canale (WhatsApp/Email) → invia via OpenAPI. Nuovo endpoint `POST /anagrafiche/{aid}/documenti/{tipo}/prepara-firma` che crea (o riusa) l'allegato dal file del dict card e ritorna `allegato_id` per `/esignature/invia`.
- **Contatore Carte d'identità in scadenza (Dashboard)** (FATTO, testato): nuovo task `carta_identita_scadenza` in `dashboard_tasks` che conta le anagrafiche con `ci_data_scadenza` nei prossimi 30 giorni. `_conta_documenti` invariato per i documenti dict.
- **Inbox · 3 cartelle per entità** (FATTO, testato): la pagina Documenti Inbox ora ha 3 dropzone-cartella (Anagrafiche/Polizze/Sinistri) + la dropzone generica. Il file caricato in una cartella passa `scope` al backend (`analyze`): l'OCR classifica e archivia nella card corretta dell'entità dello scope; l'auto-archivio non esce mai dallo scope scelto. Il ReviewDialog preseleziona l'entità dallo scope.
- **Upload multiplo per card**: confermato già attivo per le card polizza/sinistro (`DocumentiSezioneSplit`, input `multiple` + loop) e per gli "Altri documenti" dell'anagrafica (`AllegatiTab` esteso).
- **Fix**: i toast di errore firma non mostrano più HTML grezzo del proxy (messaggio localizzato).


## Sessione 30/09/2026 (fork) — Firmato in card dedicata + Promemoria scadenza CI + Upload multiplo

- **Task 1 — Firmato nella card dedicata** (FATTO, testato backend): `documenti_genera` accetta `categoria`; se il documento è di una card anagrafica (`ANAG_DICT_CARDS`) viene mirrorato in `anagrafiche.documenti[categoria]` (helper `_mirror_anagrafica_card`). Idem in `esignature_it._finalizza`: il PDF firmato viene salvato come allegato E mirrorato nella card dedicata dell'anagrafica. `GeneraDocumentoButton` assegna `categoria="autocertificazione_stato_famiglia"` quando genera l'autocertificazione stato famiglia. Verificato: genera→allegato+card dict popolata.
- **Task 2 — Promemoria scadenza carta d'identità** (FATTO, testato): il preset `documento_id_scaduto` ("Documento d'identità in scadenza") esisteva già nel catalogo ma mancava il resolver. Aggiunto `_res_documento_id_in_scadenza(giorni)` in `scheduler_alert.py` (match `ci_data_scadenza == oggi+soglia_giorni`) + wiring in `resolve_payloads`. L'utente crea la regola dal catalogo Avvisi (soglia default 30gg); parte dallo scheduler giornaliero. Verificato: resolver individua l'anagrafica con CI in scadenza.
- **Task 3 — Upload multiplo per card** (FATTO): `DocumentiSezioneSplit` (card polizza/sinistro, es. quietanze) già supportava il multi-upload (input `multiple` + loop). Esteso anche l'`AllegatiTab` dell'anagrafica ("Altri documenti") al caricamento multiplo.


## Sessione 30/09/2026 (fork) — Documenti Inbox smistamento + Firme OpenAPI + Visibilità card

**Gruppo 1 — Documenti Inbox → card corretta + OCR CI + celle anagrafica** (FATTO, testato)
- `Anagrafica` (db_models): nuovi campi `numero_carta_identita`, `ci_comune_emissione`, `ci_data_emissione`, `ci_data_scadenza`. Mostrati/modificabili nel tab Anagrafica (riquadro "Documento d'identità").
- `documenti_inbox.py`: classificatore OCR esteso (CI/patente/passaporto/CF/tessera/visura/mandato_sdd/libretto/polizza/condizioni/appendice/atto/quietanza/mup/questionario/preventivo/fattura/cid/perizia/denuncia) + estrae `comune_emissione`. Nuova mappa `DOC_ROUTING` + `ANAG_CARD_KEYS`: salvataggio nella CARD corretta — anagrafica → dict `documenti[card]`; polizza/sinistro → allegato `categoria=card`. CI popola i 4 campi anagrafica. Auto-archivio solo se l'entità della card è trovata; sinistri SOLO manuali.
- `DocumentiInbox.jsx` ReviewDialog: selettore entità (anagrafica/polizza/sinistro) + card + ricerca cliente/polizza/sinistro. Doc non abbinabili restano in "Da rivedere".
- Verificato via curl: CI→card carta_identita + campi; quietanza→allegato polizza; cid→allegato sinistro.

**Gruppo 2 — Firme unificate su OpenAPI** (FATTO, testato)
- Rimosso eSignAnyWhere (`/api/firma`) da `GeneraDocumentoButton` e `ContrattoConsulenzaTab`: generano+archiviano PDF e inviano via `/api/esignature/invia` con popup scelta canale (WhatsApp/Email). Firmato salvato nella stessa categoria (`/esignature/stato`). MUP e Privacy già su `/esignature`.

**Gruppo 3 — Card Autocertificazione stato di famiglia** (FATTO)
- Card `autocertificazione_stato_famiglia` aggiunta (frontend `DOC_TIPI_ANAG` + backend `ANAGRAFICA_DOC_TIPI` + `ANAG_CARD_KEYS`).

**Gruppo 4 — Librerie: visibilità card** (FATTO, testato)
- `GET/PUT /api/config/card-visibilita` (azienda_config.card_visibilita). Librerie → tab "Visibilità documenti": 3 pannelli con toggle Visibile/Interno. `DocumentiSezioneSplit` usa la config come default all'upload.

**Osservazioni minori aperte**: (1) archiviando CI dall'Inbox i campi CI vengono aggiornati con i dati OCR selezionati ("ultima estrazione vince"). (2) toast di conferma pannello Visibilità appare duplicato (cosmetico).



## Sessione 23/09/2026 (fork) — Fix da Code Review

- **HIGH — `update_titolo` write parziale**: su titolo coperto con giornata di copertura CHIUSA, il titolo veniva salvato ma il movimento di copertura no (errore dopo la write) → titolo ed E/C compagnia disallineati. FIX: il controllo `assert_giornata_aperta` sulla data copertura ora avviene PRIMA della write del titolo; se il giorno è chiuso l'intera modifica è rifiutata (nessuna write parziale). Verificato: aperta→sincronizza, chiusa→400 e titolo invariato.
- **MEDIUM — riassegna schema senza collaboratore**: se lo schema non ha `collaboratore_id` (cid=None) si sarebbe creata una voce ripartizione con `operatore_id=None`. FIX: `HTTPException 400` se schema senza collaboratore.
- **MEDIUM — `_compute_saldi_compagnie` saldo_iniziale senza filtro data**: aggiunto `pregresso!=True` e filtro `data_movimento`/`_cutoff` coerente con gli altri aggregati (no conteggio di saldi datati nel futuro / prima del cutoff).
- **MEDIUM — nome collaboratore inattivo**: in `TitoloDialog` il salvataggio preserva `operatore_nome` esistente quando il collaboratore assegnato è inattivo (non più stringa vuota).



- **Richiesta**: dopo l'invio dell'avviso di scadenza, il titolo deve passare in "Storico avvisi inviati" e non comparire più fra i "Titoli arretrati".
- **Fix** (`preview_avvisi_scadenze`, server.py ~11236): la preview arretrati ora ESCLUDE i titoli che hanno già una voce in `storico_avvisi` (via `titolo_id` o `titoli_ids`). Tutti i canali (email/whatsapp/sms/pdf bulk) registrano già i `titoli_ids` nello storico.
- **Verificato e2e** (curl): registrato un avviso per un titolo → sparisce dagli arretrati (1989→1988) e compare in `/storico-avvisi`. Voce di test rimossa.

## Sessione 23/09/2026 (fork) — Immobili su mappa (già disponibile)

- Verificato che `PatrimonioTab` (AnalisiClienteTab) mostra già la mappa Leaflet degli immobili con coordinate (`ImmobiliMap`, toggle "Mappa" attivo di default) e il pulsante "Geolocalizza immobili". L'import Catasto già geocodifica (`_geocode_immobile`): gli immobili importati risultano con lat/lng e compaiono sulla mappa.



- **Problema**: gli immobili scaricati dal Catasto (OpenAPI.it) restavano nel pannello Anagrafica ma non comparivano in Analisi Cliente → Patrimonio → Immobili (0).
- **Causa**: l'import in `analisi_cliente.immobili` avveniva solo dal modale `CatastoImportDialog`; il pannello inline `CadastrePanel` (quello mostrato dopo lo scarico) era di sola lettura, senza pulsante di import.
- **Fix**: aggiunto pulsante **"Importa nel Patrimonio (N)"** in `CadastrePanel` (`OpenApiActions.jsx`) che chiama `POST /openapi-it/cadastre/{aid}/importa-immobili` (endpoint già esistente e funzionante, dedup su foglio+particella+comune, geocoding). Passati `aid`, `canEdit`, `onImported` al pannello.
- **Nota**: gli immobili da catasto hanno `rendita_catastale` ma non `valore_commerciale`, quindi il totale € IMMOBILI resta 0 finché l'utente non inserisce il valore commerciale; l'elenco/conteggio però ora si popola.
- Verificato: endpoint import provato (anagrafica con 15 immobili allineati catasto↔analisi_cliente); frontend compila senza errori.



- **Fix `update_titolo` (server.py ~4491)**: modificando un titolo COPERTO, ora ri-sincronizza il movimento `copertura_titolo` (importo=lordo, provvigioni) da cui derivano SIA il Brogliaccio SIA l'E/C Compagnia (che legge importo/provvigioni del movimento, righe 1297-1303). Guardia `assert_giornata_aperta` sulla data copertura. Verificato e2e: E/C DARE 927,53→700,00 al variare di lordo/provv.
- **Resync storico**: i coperti modificati PRIMA del fix erano disallineati. In Axicura risincronizzati 3 su giornate APERTE (es. GAGETTI eebefeaa: provv movimento 37,47→225,76). Restano 9 su giornata CHIUSA 14/09/2026 (non toccati: modificherebbero contabilità chiusa) — in attesa di decisione utente (riaprire il giorno o lasciare).
- **Riassegna provvigioni per collaboratore (`/provvigioni/riassegna`)**: i tasti "Arretrati"/"Tutti" ora cambiano SOLO la quota del collaboratore dello schema (nel titolo e in polizza), MAI la provvigione totale di titolo/polizza. Nuovo helper `_quota_collab_da_schema` (schema %netto → netto×%; schema %collab → % della provvigione già presente sul titolo). Altri operatori invariati. Verificato dry-run + write con snapshot/restore: quota = 70%×provv_titolo, totale invariato.



- **Bug**: incassando un titolo GIÀ coperto con sconto (es. BRUNA MARINELLA, pol. 730043034: lordo 78,50 / pagato 77,67 / sconto 0,83), il brogliaccio riduceva i SOSPESI solo del contante (−77,67) lasciando 0,83 "appeso" e NON registrava lo sconto in SCONTI/SPESE né nel KPI Sconti.
- **Cause**: (1) `incassa` (server.py:4608) forzava `quota_sconto=0` per i titoli coperti (`is_coperto`); (2) il ramo `incasso_coperto` in `_compute_brogliaccio` riduceva i SOSPESI di `importo` invece del LORDO e ignorava lo sconto; (3) il loop KPI cumulativo non sommava lo sconto dei coperti.
- **Fix**: (1) `quota_sconto=0.0 if is_direzione else sconto_applicato` (lo sconto resta sul movimento anche per i coperti); (2) `incasso_coperto`: `c_crediti = -(importo+sconto)` (SOSPESI −LORDO), `c_spese=c_sconti=sconto`; BANCA +importo invariato, SALDO/ENTRATE/PROVV invariati (già alla copertura); (3) KPI: `cum_sconti/cum_spese += quota_sconto` per `incasso_coperto`. **Backfill** del movimento esistente (`quota_sconto` da `titolo.sconto_applicato`).
- **Verificato** (Axicura, `_compute_brogliaccio` 2026-09-15): riga BRUNA → crediti −78,50 · sconti 0,83 · spese 0,83 · banca 77,67; totali giornata sconti/spese 0,83; KPI Sconti 0,83.



- **Chiarito: NESSUN leak tra tenant.** Verificato a DB: i 23 utenti nella tendina di ripartizione provvigioni appartengono TUTTI al tenant `c5ae2d0e` (ASSICURAZIONI SCHIANTARELLI). Erano artefatti da import OMNIA (`@import.assicurapro.it` / `@import-auto.local`). Il tenant separato `tenant-principale-schiantarelli` (19 utenti) NON compariva.
- **Fix (scelta utente)**: nascondere dalle tendine di SELEZIONE collaboratore gli utenti `attivo=false` (che includono già "ERR", "Produttore - 021 - FILIALE CHIURO", "Produttore - 024 - BS BROKER SAS", "ASSICURAZIONI SCHIANTARELLI MARCO ANDREA SAS"). Le agenzie/broker partner attive (BS BROKER, MIDA, UNIVALT) RESTANO. Filtro `u.attivo !== false` applicato in: `TitoloDialog.jsx` (ripartizione provvigioni — fonte dello screenshot), `PolizzaDetail.jsx` EditPolizzaDialog, `Polizze.jsx` NuovaPolizzaDialog. `CollaboratoreInlineSelect.jsx`: opzioni filtrate mantenendo però l'eventuale operatore già assegnato. (`ProvvigioniOperatoriEditor` già filtrava.) La pagina Librerie > Utenti continua a mostrarli per riattivarli.
- Verificato: build OK (nessun errore, 4269 polizze). Le 4 voci target sono `attivo=false` → escluse dal filtro.



- **🔴 Contabilità non più rotta**: `Contabilita.jsx` referenziava `saldoCassaOpen` e `SaldoCassaCompagnieDialog` mai definiti (pagina in crash). Aggiunto lo state e creato il componente `SaldoCassaCompagnieDialog` (accanto a Giroconto/Nuovo movimento nella toolbar).
- **Dialog Saldo Cassa Compagnie**: elenca tutte le compagnie attive del tenant con campo importo (positivo=debito / negativo=credito verso compagnia) + data + ricerca; precarica i saldi già registrati (`GET /contabilita/saldo-cassa-compagnie`); salva via `POST` (idempotente, sostituisce i saldi iniziali precedenti). Ogni riga scrive un movimento Prima Nota `saldo_iniziale_compagnia` (solo colonna SALDO) + una voce "Saldo iniziale" nell'E/C compagnia. Backend già presente (server.py:637-690).
- **🔴 Fix isolamento tenant**: `voci_manuali_compagnia` NON era in `TENANT_SCOPED_COLLECTIONS` → il `set_saldo_cassa` avrebbe cancellato/mescolato le voci di TUTTI i tenant. Aggiunta alla lista (collezione era vuota, nessuna migrazione necessaria). Verificato e2e: admin scrive Allianz 1500€ → visibile solo al suo tenant; login sandbox → `[]` (isolato). Cleanup effettuato.
- **STATO**: verificato via curl (POST/GET/isolamento) + screenshot dialog. Rami tenant-aware e verifica leak collaboratori: RINVIATI su richiesta utente ("assuming defaults for now").
- **🔄 Saldo Cassa Compagnie → registrazioni MANUALI ripetibili** (su richiesta utente, come le Ritenute): da setup idempotente "tutto in una volta" a form che aggiunge UNA voce alla volta (compagnia + data + segno +debito/−credito + importo + **descrizione libera**). Backend: `POST /contabilita/saldo-cassa-compagnie` ora crea una singola riga `saldo_iniziale_compagnia` (colonna SALDO con la descrizione) + voce E/C (origine `saldo_cassa`, collegata via `movimento_id`); nuovo `DELETE /{mid}` (rimuove riga PN + voce); `GET` ritorna l'elenco arricchito col nome compagnia. Frontend `SaldoCassaCompagnieDialog`: form + tabella registrazioni con elimina + totale. Migrate le 2 voci legacy (collegato `movimento_id`). Verificato e2e: 2 voci Allianz (+500/−200) → KPI 2898,83→3198,83, widget Allianz 265→565; delete OK; screenshot UI.
- **🔴 Fix KPI + widget "Saldo Cassa per Compagnia" non aggiornati** (`_compute_saldi_compagnie`, server.py:6683): il nuovo saldo iniziale (categoria `saldo_iniziale_compagnia`) alimentava solo le righe Brogliaccio ma NON il saldo cumulativo per compagnia né il KPI `SALDO CASSA CMP.` (che usavano solo `setup_iniziale_compagnia_dare/avere`). Aggiunta la somma di `saldo_iniziale_compagnia` al `saldo_dovuto` (positivo=debito, negativo=credito), indipendente dal cutoff setup; incluso nella skip-check. Nessun doppio conteggio (0 movimenti setup_iniziale legacy). Verificato e2e: +2000€ → KPI 2898,83→4898,83 e Allianz widget 265→2265.

## Fix rapidi (15/09/2026, sessione fork)

- **Contatore "Anagrafiche senza C.I."**: ora riconosce anche la CI salvata in `anagrafiche.documenti.{carta_identita|patente|passaporto|documento_identita}` (embedded), non solo in `db.allegati`. (`routes/extras_p1p2.py` documenti-mancanti). Verificato: Schiantarelli Andrea non più tra i "senza C.I." (+15 anagrafiche).
- **Brogliaccio (Prima Nota) → filtro Collaboratore**: aggiunto dropdown "Collaboratore" (`brogliaccio-collab`). Backend `_compute_brogliaccio` (server.py) aggiunge `collaboratore_id`/`collaboratore` a ogni riga (dalla polizza o dal movimento). Filtro client-side + riga TOTALE ricalcolata sul filtro. Riepilogo conti/KPI/liquidità restano globali.
- **OCR Libretto → solo nel quadro "Libretto veicolo"**: la lista piatta "Documenti" (`DocumentiPolizzaTab`) ora nasconde i documenti già categorizzati (polizza/condizioni/libretto_veicolo/quietanza/…), evitando la duplicazione. L'OCR libretto salva già `categoria=libretto_veicolo`.
- **Estratto Conto Collaboratori**: lista COLLABORATORI mostra ora SOLO utenti con ruolo `collaboratore` (esclusi admin/dipendente). Filtro client-side in `Provvigioni.jsx`.

## eSignature (OpenAPI.it) — IN PRODUZIONE dal 15/09/2026
- **LIVE**: `OPENAPI_ESIGNATURE_SANDBOX="false"` in backend/.env → host `esignature.openapi.com`. Verificato che lo scope EU-AES è attivo in prod con le credenziali OPENAPI_IT esistenti (token prod ottenuto). Ogni firma consuma credito OpenAPI e invia SMS/email reali.
## eSignature (OpenAPI.it) — IMPLEMENTATO (15/09/2026)
- **Estensioni (iter 92, verde)**: tasto firma su **polizza, sinistro E anagrafica** (FirmaButton esportato da DocumentiSezioneSplit, aggiunto anche in AnagraficaDetail/AllegatiCartella); **badge stato** accanto a ogni PDF ("In firma"/"Firmato") leggendo `/esignature/richieste`; **promemoria WhatsApp dopo 48h** nel poller (`finalizza_pending`, campo `reminder_sent`); **contatore Dashboard** "Firme in attesa" (widget DocumentiMancantiWidget, 5ª card + dialog tipo='firme') alimentato da `/insights/documenti-mancanti` (`totali.firme_in_attesa` + array).

- **Backend**: `esignature_openapi.py` (service EU-AES OTP SMS, token OAuth dedicato, sandbox via env `OPENAPI_ESIGNATURE_SANDBOX` default true, riusa OPENAPI_IT_CLIENT_ID/SECRET) + `routes/esignature_it.py` (prefix `/api/esignature`):
  - `POST /esignature/invia` {allegato_id, firmatario?, invia_whatsapp?, invia_email?} → crea richiesta EU-AES da un allegato PDF, salva in `db.firma_requests` (provider=openapi_esignature) con entità+categoria del documento, invia il `signing_url` via **WhatsApp** (Evolution) + **Email**.
  - `GET /esignature/richieste?entita_tipo&entita_id` → lista/badge.
  - `GET /esignature/stato/{req_id}` → aggiorna stato; se DONE scarica il PDF firmato e lo salva come Allegato nella STESSA entità e STESSA categoria (stesso quadro), `visibile_cliente=true`.
  - **Poller** `finalizza_pending` (AsyncIOScheduler ogni 2 min, avviato in startup) → salvataggio AUTOMATICO del firmato appena il cliente firma.
- **Frontend**: `DocumentiSezioneSplit.jsx` → componente `FirmaButton` (icona penna viola, `doc-firma-{id}`) su ogni allegato PDF nei quadrotti; dialog per firmatario (default = contraente), invio e "Controlla stato / scarica firmato".
- **Verificato in SANDBOX** (admin@assicura.it): richiesta creata (signature_id, `signing_url` https://test.esign.openapi.com/...), stato → WAIT_SIGNERS. Lo scope EU-AES sandbox è attivo con le credenziali esistenti.
- **Per andare LIVE**: impostare `OPENAPI_ESIGNATURE_SANDBOX=false` dopo aver confermato con OpenAPI.it l'entitlement dello scope EU-AES in produzione.

## eSignature (OpenAPI.it) — DA IMPLEMENTARE (requisiti + playbook pronti)
- Requisiti: FEA/AES OTP via SMS; invio link firma via **WhatsApp** (Evolution) + email; avvio dagli **Allegati/Documenti** (polizza/sinistro/anagrafica) tasto "Invia per firma" su PDF esistente; firmatario = contraente (email+cellulare da anagrafica); documento firmato torna in Allegati come "firmato"; riuso OPENAPI_IT_CLIENT_ID/SECRET + scope eSignature.
- API: `POST https://esignature.openapi.com/EU-AES` (sandbox test.esignature...); risposta `data.signers[].url` + `data.id`; stato `GET /signatures/{id}/detail` (WAIT_VALIDATION/WAIT_SIGN/WAIT_SIGNER/DONE/ERROR); download `GET /signatures/{id}/signedDocument`; scope OAuth `POST:esignature.openapi.com/EU-AES`, `GET:esignature.openapi.com/signatures`. Callback opzionale. Verificare entitlement scope EU-AES in prod con OpenAPI.it.


## Sessione 15/09/2026 (fork) — Statistiche Premi/Provvigioni (tab nell'hub Statistiche)

- **Hub Statistiche** (`/statistiche`, `Statistiche.jsx`) ora ha 5 tab: Overview, Indice ISA, **Premi / Provvigioni**, **Top Clienti**, **Segmentazione**.
- **Top Clienti + Segmentazione SPOSTATI** da "Il Cervello" all'hub Statistiche (richiesta utente). Nuovo file `pages/StatisticheClienti.jsx` con `TopClientiModulo` (selettore anno interno) e `SegmentazioneModulo`. Rimossi da `Cervello.jsx` (restano: Conto Economico, Costi & Bilancio, Mini Bilancio).
- **Premi / Provvigioni** (`StatistichePremi.jsx` + backend `GET /api/statistiche/premi-provvigioni` ~server.py:3109):
  - Tabella mensile con **metriche selezionabili** (Premio Netto · Provvigioni · Premio Lordo, chip toggle, min 1).
  - **Filtro periodo (mesi)**: Da → A (mese singolo, intervallo, o anno intero Gen–Dic). Totale + Δ% calcolati sul periodo scelto.
  - Multi-selezione anni (ultimi 5), confronto 2 anni con Δ%.
  - Filtri: Data (incasso/rata/copertura), Tipo titolo, Compagnia, Operatore (solo admin).
  - **Scoping per ruolo**: un collaboratore vede SOLO i propri premi/provvigioni (backend forza `operatore_id=user.id`, provvigioni = sua quota da `provvigioni_operatori`; filtro Operatore nascosto in UI). Flag `scoped_operatore` nella risposta. Verificato via curl (collaboratore scoped=True) + screenshot.
- **STATO: in attesa di verifica utente** prima di procedere con "Statistiche per Operatore" e "Rami tenant-aware".

### Statistiche — estensioni + fix vari (15/09/2026, iter 91 verde)
- **Premi/Provvigioni**: metriche selezionabili (netto/provvigioni/lordo), filtro periodo mesi (Da→A), **grafico a barre** (recharts) sopra la tabella, **selezione anno libera** (dropdown `stat-add-anno` → qualsiasi anno fino al 2005, es. 2019). Scoping collaboratore (vede solo i suoi, filtro operatore nascosto).
- **Nuovo tab "Per Operatore"** (`StatistichePerOperatore.jsx` + `GET /api/statistiche/per-operatore`): tabella per operatore, premi (netto/lordo, ripartiti pro-quota) e provvigioni (quota effettiva), confronto anni, stessi filtri. Nomi operatori risolti da `db.users`.
- **Top Clienti**: dati reali dai titoli, colonne Cliente da / Premi netti / Provvigioni / Regalo(%) impostabile, toggle Primi 100 / Tutti gli attivi. **Solo clienti con polizze attive** (RAPPEL escluso).
- **Overview → Top 5 Compagnie**: aggiunta colonna **Premio netto** (oltre al lordo). Backend `statistiche_overview` ritorna `premio_netto`.
- **Helpers condivisi** `pages/statsShared.jsx` (YearPicker, MeseRange, FSel, costanti).

### Altri fix (15/09/2026, iter 91 verde)
- **Agenzie**: fix tasto Modifica che apriva form vuoto/creava duplicato → `AgenziaDialog key={editing?.id||'new'}` (remount con prefill). Aggiunti testid `age-edit-{id}`/`age-del-{id}`.
- **Libro Matricola / Cumulative**: rinominata voce sidebar + titolo pagina; `list_libro_matricola_polizze` (extras_p1p2.py) ora include sia `is_libro_matricola` sia `is_cumulativa_assicurati`; badge "Libro matricola"/"Cumulativa" sulle card. NB: la polizza cumulativa vive nel tenant che la possiede (scoping per-tenant).
- **Assicurati (tab cumulativa)**: badge Totale/Attivi/Usciti resi filtri cliccabili (`assicurati-filter-*`), default = solo Attivi.
- **Mappa clienti**: voce nascosta dal menu (rimossa da `ALL_MENU_ITEMS`), route `/mappa` ancora attiva.

### Top Clienti — dati reali + nuove colonne (15/09/2026)
- **Fix "non prende i dati"**: `GET /api/cervello/top-clienti` (`routes/cervello.py`) prendeva le provvigioni da `movimenti_contabili` (categoria=provvigioni) che è VUOTA in questo tenant → tutto 0. Riscritto per aggregare i **dati reali dai titoli** (`data_incasso` nell'anno, esclusi stornato): `provvigioni` + `importo_netto` per contraente. Ora 2026 tot provv 101.218 (coerente con tab Premi).
- **Nuove colonne**: "Cliente da" (anni da prima decorrenza polizza, fallback created_at → `anni_cliente`), "Premi netti" (`premi_netti_anno`), "Regalo (X%)" = provvigioni × % impostabile in UI (default 5%, input `topcli-pct-regalo`).
- **Primi 100 / Tutti gli attivi**: param `tutti=true` → carica TUTTI i clienti attivi (attiva/in_emissione) senza limite (toggle `topcli-primi100`/`topcli-tutti`). Verificato: tutti=2317 clienti.


### Prossimi (concordati con l'utente)
- **Statistiche per Operatore** (P0): tabella per operatore con Premi/Provvigioni + confronto anni, stessi toggle.
- **Rami tenant-aware** (P1): ministeriali globali, custom solo al tenant creatore.



- **Compagnie: cella "Mandato" → "Agenzia partner" multi-selezione** (`Librerie.jsx` CompagniaForm + `db_models.py` + `routes/agenzie.py`): rinominata la cella e trasformata in multi-select delle agenzie partner (checkbox), salvata nel nuovo campo array `agenzie_partner_ids` sul modello Compagnia (una compagnia può avere PIÙ agenzie partner). Il conteggio/elenco "compagnie collegate" in Agenzie usa `$or` tra `agenzia_partner_id` (legacy) e `agenzie_partner_ids`. Persistenza verificata via API.
- **Ramo import su re-import** (`ania_importer.py` `_upsert_polizza`): `ramo` e `prodotto` ora si aggiornano anche sulle polizze già presenti quando il mapping risolve un valore diverso (es. "3N" → "RC AUTO"), così la correzione del mapping si propaga (prima la regola "solo dati mancanti" li lasciava invariati).

### Pendenti
- **Quadrotti documenti polizza in stile anagrafica** (UI, `DocumentiSezioneSplit` vs `DocumentiTab`).
- **Rami tenant-aware**: ministeriali visibili a tutti, custom solo al tenant creatore. I rami sono attualmente GLOBALI; serve schema (`agenzia_tenant_id`/`ministeriale`) + migrazione + filtro in `list_rami`. Non ancora implementato.
- Se il mapping "3N→RC AUTO" non fosse configurato in `import_mappings` (tipo=ramo), l'import continua a creare "3N": verificare la presenza del mapping.


## Sessione 15/09/2026 (fork) — Allegato incasso visibile al cliente sotto Quietanze

- **Allegato Incasso/Copertura → visibile al cliente + Quietanze** (`DialogIncassoCopertura.jsx`): l'upload ora passa `visibile_cliente: true` (le quietanze sono visibili al cliente). Prima finiva in "Interni · solo staff". Verificato via API (categoria=quietanza, visibile_cliente=True).
- **PENDENTE**: rifare i quadrotti dei documenti della POLIZZA con lo stesso formato di quelli dell'ANAGRAFICA. La polizza usa `DocumentiPolizzaTab`+`DocumentiSezioneSplit`; l'anagrafica usa `DocumentiTab` (layout quadrotti dedicato, `pages/AnagraficaDetail.jsx` ~riga 1944). Da allineare come task UI dedicato.


## Sessione 15/09/2026 (fork) — Fix logo/save compagnie (405), ramo mappato, stampa saldo cassa, allegato→Quietanze

- **🔴 Fix "Method Not Allowed" salvataggio compagnie** (`Librerie.jsx`): avevo impostato l'endpoint sezione a `/compagnie?tutte=true`; il CRUD generico costruisce `${endpoint}/${id}` → URL corrotto `/compagnie?tutte=true/ID` → PUT senza id → 405. Ripristinato `endpoint: "/compagnie"` + `listParams: { tutte: true }` (lista mostra tutte, CRUD usa il path base). PUT /compagnie/{id} verificato 200.
- **Ramo import mostra il NOME di destinazione** (`ania_importer.py`): per i rami mappati usava il `codice` (es. "3N"); ora usa il `nome` del ramo di destinazione (es. "RC AUTO"), come già per i prodotti. Vale per le importazioni successive.
- **Stampa Brogliaccio saldo cassa** (`server.py` `_generate_brogliaccio_pdf` + `pdf_brogliaccio.py`): l'ultimo KPI del PDF mostrava `riepilogo_kpi.saldo_cassa` (non presente a schermo); ora mostra `saldo_cassa_compagnie` ("SALDO CASSA CMP.") coerente con lo schermo + box Liquidità.
- **Allegato Incasso/Copertura → Quietanze** (`DialogIncassoCopertura.jsx`): l'upload era dentro il blocco copertura (saltato in incasso) e in categoria "copertura"; ora è sempre eseguito e salvato sulla POLIZZA in categoria `quietanza` → compare nei Documenti > Quietanze. Verificato via API.

### Pendenti / prossimi passi
- **Cella "Mandato" compagnie → collega agenzie partner**: NON ancora implementato (feature nuova).
- **Cancellare rami senza polizze**: i rami sono GLOBALI (condivisi tra tutti i tenant, nessun campo tenant). Rimosso l'endpoint per-tenant (non sicuro: cancellerebbe rami usati da altri tenant). Serve decidere una pulizia GLOBALE (uso su TUTTI i tenant) prima di eliminare. Nel frattempo i rami senza polizze sono già NASCOSTI dai filtri (`con_polizze`).


## Sessione 15/09/2026 (fork) — Libro Matricola: elimina tutte, header ordinabili, sezione Escluse, cambio intestatario

- **Elimina tutte le applicazioni** (per polizza): nuovo pulsante "Elimina tutte" su ogni card + endpoint `DELETE /api/libro-matricola/polizze/{pid}/applicazioni` (`extras_p1p2.py`). Conferma richiesta.
- **Header tabella ordinabili**: le intestazioni (Numero, Veicolo/targa, Stato, Inclusione, Esclusione, Valore, Intestatario) sono ora cliccabili per ordinare (asc/desc), con indicatore ▲/▼ (`ApplicazioniTable` in `LibroMatricolaTab.jsx` + `changeSort` in `LibroMatricolaPage.jsx`).
- **Sezione "Escluse" separata**: la card mostra di default solo le applicazioni ATTIVE; quelle escluse/cessate/annullate/sostituite sono in una sezione "Escluse (n)" collassabile a parte.
- **Cambio intestatario manuale**: pulsante UserCog su ogni riga → dialog `EditIntestatarioDialog` con `IntestatarioAutocomplete` (nome libero o collegamento anagrafica), salva via `PUT /api/libro-matricola/applicazioni/{aid}`.
- Verificato via screenshot (admin@assicura.it, 4 polizze/423 applicazioni): header ordinabili funzionanti, 2 pulsanti intestatario per riga, "Elimina tutte" su tutte le card.


## Sessione 15/09/2026 (fork) — Import Omnia: regole polizze/titoli (mai stati automatici)

- **Import Omnia/ANIA** (`ania_importer.py`), su richiesta utente:
  - **Polizza esistente** (dedup per `id_polizza_exp` → fallback `numero_polizza`): non si sovrascrive più tutto; ora si compilano SOLO i dati MANCANTI (campi vuoti), preservando i valori già presenti/rettificati manualmente (`_upsert_polizza`).
  - **Titolo esistente** (dedup per `id_titolo_exp` → fallback chiave naturale polizza+effetto+scadenza): NON si fa NULLA (nessun update).
  - **Titolo mancante**: creato SEMPRE come `da_incassare`. **Mai** impostato a incassato/coperto/pagato (rimossi: mapping stato_share→incassato, dt_pag→incassato, premio-0→incassato, `data_incasso`, `mezzo_pagamento`, "pagamento in direzione"). Incasso/copertura sono operazioni SOLO manuali.
  - Verificato e2e con lo ZIP reale (`A_OW8_23774...zip`) nel sandbox: import #1 → 158 polizze, 138 titoli tutti `da_incassare` (0 coperti, 0 con data_incasso); re-import → 0 polizze nuove, 158 aggiornate (solo dati mancanti), 0 titoli nuovi, 0 duplicati id_titolo_exp.
- Nota: i titoli già importati in passato con stati coperto/incassato (pre-fix) restano tali; per correggerli manualmente usare il pulsante ↩ "Rimetti in arretrato" sul titolo.


## Sessione 14/09/2026 (fork) — KPI reali, tag età automatici, filtri nascondono disabilitati/senza-polizze, saldo direzione

- **Fix KPI Contabilità (prima_nota)** (`routes/kpi.py` `_stats_prima_nota`): Entrate/Uscite/Saldo mostravano "0" come valore grande con l'importo reale relegato in `sub`. Ora il valore principale è l'importo in euro. Verificato via curl (es. Uscite value="€ 31.219,95").
- **Fix critico KPI custom** (trovato dal testing agent, `_resolve_custom_kpi`): la funzione non aveva `return` → qualsiasi KPI custom mandava in crash `/kpi/{sezione}/stats`. Ora ritorna `{value:count, sub:euro, link:deep-link}`. 12/12 pytest verdi.
- **Tag età AUTOMATICI** (`routes/anagrafiche.py` `_age_tags`/`_apply_age_tags`): su create/update anagrafica, dalla `data_nascita` si applicano automaticamente `gen_anni_XX` + `anziano_over_65`/`giovane_under_30`, preservando i tag manuali. Verificato via curl (1955→over_65; update 2005→under_30; "vip" preservato). Coerente con l'endpoint bulk `/anagrafiche/tags/auto-genera`.
- **Filtri nascondono elementi disabilitati/vuoti**:
  - Conti/Banche disabilitate: le tendine filtro passano `attivi=true` (Titoli, TitoliSospesi, Contabilita, EstrattoContoCompagnie, PolizzaDetail). La gestione Librerie continua a mostrare gli archiviati.
  - Compagnie disabilitate: `/compagnie` default esclude TUTTE le `attiva=False`; Librerie > Compagnie usa `?tutte=true`.
  - Rami/Prodotti senza polizze: nuovi param `con_polizze=1` su `/librerie/rami` e `/librerie/prodotti`, applicati ai filtri di Polizze e Titoli (non ai form di creazione). Verificato (rami 49→3).
- **Saldo direzione nei cumulativi** (`_compute_brogliaccio` KPI cumulativi, `_compute_saldi_compagnie`, `_compagnia_estratto_data`): un incasso IN DIREZIONE ora riduce il saldo verso compagnia delle SOLE provvigioni (−provv), coerente giorno/cumulativo/E-C. Verificato: CATTOLICA E/C=widget=43.183,72 (DELTA=0).
- **Fix "incasso registrato due volte"** (`DialogIncassoCopertura.jsx`): la copertura separata parte solo se NON si incassa contemporaneamente → un incasso diretto = una sola riga `incasso_premio` (Entrate/Provv/Saldo/Banca).

### Limiti noti / prossimi passi
- I deep-link generati dalle card KPI (es. `/polizze?tag=`, `/contabilita?tipo=entrata`) NON vengono ancora applicati come filtro dalle pagine di destinazione (Polizze non ha un filtro "tag"; la lista Contabilità non filtra per `tipo`). Da implementare se si vuole il click-through filtrato.
- KPI custom con filtro "tag" su sezioni polizze/titoli: i tag sono sulle anagrafiche, non su polizze/titoli → il conteggio richiederebbe un join contraente→polizze (attualmente conterebbe 0).
- Pagina /sinistri: in test headless la barra KPI tarda a comparire (>20s) per lentezza di caricamento della pagina, non del KPI (backend <1s). Da investigare.


## Sessione 14/09/2026 (fork) — Fix incasso "registrato due volte" (copertura + incasso_coperto)

- **🔴 Fix doppia riga in Prima Nota all'incasso** (`DialogIncassoCopertura.jsx`): la checkbox "Copertura" è attiva di default; se l'utente incassava anche (checkbox Incasso), venivano create DUE righe — `copertura_titolo` (Entrate/Provv/Saldo/Sospesi) + `incasso_coperto` (−Sospesi/+Banca). L'utente vuole un unico incasso. Ora la copertura separata (`bulk-copertura`) viene eseguita SOLO se NON si sta incassando nello stesso momento (`copertura && !giaCoperto && !incasso`). Incassando direttamente su un titolo non coperto, l'endpoint `incassa` registra una SOLA riga `incasso_premio` = Entrate + Provvigioni + Saldo + Banca. Verificato e2e (1 solo movimento incasso_premio con provv e conto). Per correggere i titoli già sdoppiati: usare il nuovo pulsante ↩ "Rimetti in arretrato" e re-incassare.


## Sessione 14/09/2026 (fork) — Form premi polizza, colonna Ritenuta, E/C compagnie = widget, pulsanti stato titolo

- **Form premi polizza (dialog "Modifica polizza" tab Economici + tab "Premi")** (`PolizzaDetail.jsx`): rimosso il campo **Tasse**; aggiunti **Accessori** e **Addizionale**; il **Premio lordo è ora AUTOMATICO** (readonly) = Netto + Imposte + SSN + Accessori + Addizionale. `Diritti` resta come voce separata (non entra nel lordo). Aggiunto `premio_addizionale` al modello `Polizza` (db_models). Verificato via screenshot (tab Economici mostra i 5 campi + lordo auto, niente Tasse).
- **Colonna RITENUTA nel Brogliaccio/Prima Nota** (`_compute_brogliaccio`): quando si registra una `ritenuta_compagnia` l'importo ora popola ANCHE la colonna dedicata "Ritenuta" (oltre a Saldo). Verificato via API (riga ritenuta: saldo=138,71 e ritenuta=138,71).
- **🔴 E/C Compagnie allineato al widget "Saldo cassa"** (`_compagnia_estratto_data`): il DARE era gonfiato perché contava tutti i titoli `stato=incassato` (incl. i coperti PRIMA del go-live poi incassati via `incasso_coperto`, il cui ricavo è già nel saldo di apertura → doppio conteggio, es. CATTOLICA 50.220 vs 43.195). Ora il DARE = ricavi reali dei movimenti `incasso_premio` + `copertura_titolo` post-cutoff (al netto provvigioni), STESSA fonte del widget → coincidono al centesimo. Dettaglio righe ricostruito dai movimenti (contraente/polizza/ramo/collaboratore). Verificato: CATTOLICA e UCA DELTA=0,00 vs widget. `polizze.to_list(None)` (niente più cap 20000).
- **Pulsanti stato titolo (PolizzaDetail tab Titoli)**: sui titoli **incassati** ora compaiono **⏸ "Rimetti coperto"** (marca-sospeso: annulla incasso e torna sospeso) e **↩ "Rimetti in arretrato"** (nuovo endpoint `POST /api/titoli/{tid}/rimetti-arretrato`: annulla incasso + storna copertura + reset a da_incassare, rimuove i movimenti Prima Nota su giornate aperte). Verificato e2e (incassa→coperto→incassa→arretrato, stato pulito) + screenshot pulsanti.


## Sessione 14/09/2026 (fork) — Tipo Inclusione/Esclusione + fix provvigioni BS BROKER

- **Tipo titolo**: aggiunte le opzioni **Inclusione** ed **Esclusione** al dropdown "Tipo (riferimento)" (TitoloDialog) e al Literal `Titolo.tipo`. Verificato via screenshot.
- **Provvigioni BS BROKER**: gli schemi "diretti sul premio netto" (es. BS BROKER 4,5% del netto) con `percentuale_collaboratore=0` ora assegnano al collaboratore l'INTERO importo (netto×%), non 0. Corretti `_calcola_provvigione` e `_provv_breakdown`; l'endpoint `/provvigioni/calcola` e il pulsante "Auto" del dialog ora passano anche `premio_netto` (e compagnia_id). NB: non testabile live via API perché BS BROKER è sul tenant Axicura (no login jacopo); logica verificata su dati schema confermati (netto 496,99 × 4,5% = 22,36).



- **Primo titolo automatico** (`create_polizza`): alla creazione della polizza viene generato il primo titolo (tipo "nuova") con effetto/scadenza/premi/provvigioni/imposte della polizza. Verificato e2e.
- **Scadenze da frazionamento** (`create_polizza` + helper `add_months` in db_models): da effetto+frazionamento calcola in automatico `scadenza` (contratto = +12 mesi), `prossima_quietanza` (+intervallo frazionamento) e `scadenza_copertura`. Es. effetto 14/09/2026 semestrale → scad 2027-09-14, prox quietanza 2027-03-14.
- **Imposte automatiche in Regolazione Premio** (`GeneraTitoloDialog`): il campo "di cui imposte €" si compila in automatico in proporzione all'aliquota della polizza (`imposte_ratio` = (tasse+imposte+ssn)/lordo, aggiunto alla riga backend), ricalcolato al variare dell'importo finché l'utente non lo modifica manualmente.



**Completato e verificato:**
- **Provvigione BS BROKER**: `quotaCollaboratore` (TitoloDialog) ora gestisce anche lo schema "% su premio netto" (BS BROKER = 4,5% del netto), non solo `percentuale_collaboratore`.
- **Campi titolo**: aggiunti al modello `Titolo` e al dialog i campi **SSN**, **Diritti**, **Accessori**, **Descrizione libera**; arrotondamento a 2 decimali (frontend + backend create/update).
- **Tab Libro Matricola / Cumulativa**: il dettaglio polizza risolve `is_libro_matricola`/`is_cumulativa_assicurati` dal PRODOTTO (anche per polizze importate prima del flag) e mostra la tab giusta nascondendo la singola "Veicolo".
- **Date polizza automatiche**: quando un titolo diventa coperto/incassato, la polizza aggiorna `scadenza_copertura`, `prossima_quietanza`, `scadenza` (solo in avanti) — helper `_aggiorna_scadenze_polizza_da_titolo` in incassa/bulk-copertura/marca-sospeso.
- **Ultimo premio pagato**: include ora anche i titoli **coperti** (non solo incassati).
- **Ricerca polizze in scheda anagrafica** (PolizzeTab AnagraficaDetail): campo di ricerca per numero/compagnia/ramo/prodotto.
- **Copia titolo**: pulsante ⧉ in scheda polizza che apre il dialog precompilato con gli stessi dati (nuovo titolo da_incassare).
- **Performance lista Polizze**: le polizze **annullate** sono escluse da tutte le viste/ricerche (param `escludi_annullate`) tranne quando si sceglie esplicitamente lo stato "annullata" → default 49.276→21.102 polizze caricate.

**Da completare / da chiarire (aperti):**
- Auto-creazione del PRIMO titolo alla creazione polizza (con gli stessi dati) — NON ancora implementato.
- Auto-calcolo scadenza polizza + prossima quietanza da effetto+frazionamento (nuova/sostituzione/titolo) — NON ancora implementato.
- Visual-edit "togli cella" (PolizzaDetail riga 2011, componente `F`): ambigua, chiesto quale campo.
- Visual-edit "aggiungi inclusione/esclusione" su un select: ambigua, da chiarire quale select.



- Aggiunti al modello `Titolo` i campi `ssn` (float, contributo SSN) e `descrizione` (nota libera). Nel dialog `TitoloDialog.jsx`: nuovo input **SSN €** (accanto a Imposte) e textarea **Descrizione (nota libera)** a tutta larghezza. Salvataggio + arrotondamento a 2 decimali (SSN) in create/update titolo. Verificato: SSN 12.345→12.35 e descrizione persistiti via API.



- La colonna "Azioni" della tabella titoli in PolizzaDetail è ora **ancorata a destra** (position sticky) tramite classe `.col-azioni` (index.css) su `<th>`/`<td>`: resta sempre visibile senza scorrere, con ombra di separazione e background coerente (righe pari/hover). Verificato a 1280px: la tabella scorre ma i pulsanti Azioni restano fissi.

## Sessione 14/09/2026 (fork) — Fix colonna "Azioni" tagliata nella tabella Titoli (PolizzaDetail)

- **Causa**: la Card della tabella titoli aveva `overflow-hidden`; quando la tabella (14 colonne) superava la larghezza del contenitore, l'ultima colonna "Azioni" (✎ modifica, 🗑 elimina, €, ⏸, ↺) veniva tagliata senza scrollbar. La colonna era comunque sempre nel markup.
- **Fix** (`PolizzaDetail.jsx`): tabella titoli avvolta in `div.overflow-x-auto` + `min-w-[1100px]` → la colonna Azioni è sempre raggiungibile (scroll orizzontale sugli schermi stretti). Verificato via screenshot: Azioni visibile con tutti i pulsanti.


## Sessione 14/09/2026 (fork) — Doppioni polizze da import OMNIA incrementale (diagnosi + pulizia + fix)

- **Causa**: l'import OMNIA incrementale del 14/09 (`A_OW8_23774_20260914161500_88_P_I.zip`, job 14:16) ha creato 255 polizze duplicate. `_upsert_polizza` deduplicava SOLO su `id_polizza_exp`; le polizze dell'import iniziale (11/09) avevano `id_polizza_exp=None`, quindi nessun match → nuove polizze (con codici ramo grezzi 3N/01/3S… non mappati).
- **Fix importer** (`ania_importer.py` `_upsert_polizza`): match robusto — prima `id_polizza_exp`, poi fallback su `numero_polizza` (db già tenant-scoped) → niente più doppioni anche se l'id OMNIA manca/cambia.
- **Pulizia** (`scripts/pulisci_doppioni_omnia_14092026.py`): eliminati **253 doppioni** del 14/09 (+ 181 titoli, **0 movimenti** = nessun impatto contabile), copiato il loro `id_polizza_exp` sull'originale 11/09 (per i futuri import), tenute le 2 polizze senza gemello. Backup CSV in `/app/doppioni_omnia_14092026.csv`. Risultato: 0 numeri polizza duplicati. Es. COGO ENRICA 730021025 → 1 sola polizza MULTIRISCHIO con 4 titoli.


## Sessione 14/09/2026 (fork) — Fix arrotondamento importi titolo (float)

- **🔴 Fix Lordo 686,9999… → 687,00**: il dialog "Nuovo/Modifica titolo" mostrava artefatti float. Ora `TitoloDialog.jsx` arrotonda a 2 decimali sia il prefill (importo_lordo/netto/imposte/provvigioni) sia i valori salvati. Lato backend `create_titolo`/`update_titolo` arrotondano gli stessi campi (+ importo_da_pagare) a 2 decimali per prevenire futuri artefatti.


## Sessione 14/09/2026 (fork) — Fix copertura già-coperti, giroconto, storno/sospeso, ricerca sospesi

- **🔴 Fix doppia registrazione copertura**: se un titolo era GIÀ coperto (`titolo_coperto=True` da prima), `bulk-copertura`/`marca-sospeso` NON ricreano più la riga di copertura (ENTRATE/PROVV/SALDO/SOSPESI) — la copertura era già contabilizzata. All'incasso di un già-coperto viene registrata SOLO la riga incasso (−SOSPESI +BANCA). Rimossi i 2 movimenti copertura errati sui titoli reali 184642872 (€485) e 182259867 (€382). Verificato: copertura ripetuta → 0 movimenti.
- **🔴 Giroconto NON è una spesa**: escluso dal totale SPESE sia nel Brogliaccio (`_compute_brogliaccio`, cum loop) sia in `statistiche_contabilita` (esclusi anche anticipo/ritenuta_compagnia).
- **Endpoint + pulsanti Storno copertura** (`POST /titoli/{id}/storna-copertura`): rimuove i movimenti di copertura dalla Prima Nota (giornate aperte) e riporta il titolo a da_incassare. Pulsante ↺ in PolizzaDetail.
- **Endpoint + pulsante Marca/Ripristina sospeso** (`POST /titoli/{id}/marca-sospeso`): marca un titolo come sospeso/coperto; se era incassato annulla prima l'incasso. Pulsante ⏸ in PolizzaDetail. Verificato round-trip marca→storna (titolo torna pulito).
- **Ricerca in Sospesi/Anticipi**: campo di ricerca testuale (contraente, n° polizza, collaboratore, ramo, targa, telefono) in `TitoliSospesi.jsx`. Verificato via screenshot.
- **Metodi di calcolo globali**: tutte le logiche contabili (liquidità, saldo cassa da setup, copertura/incasso, giroconto) sono in funzioni condivise di server.py, NON tenant-specifiche → valgono per TUTTE le agenzie; i dati restano persistiti per-tenant nel DB.


## Sessione 14/09/2026 (fork) — Contabilità copertura/incasso titoli coperti (Prima Nota)

- **Copertura titolo (solo coperto)**: `bulk_copertura` ora crea un movimento `entrata/copertura_titolo` (importo=lordo, nessun conto cassa, provvigioni dal titolo) invece del vecchio `uscita/anticipo`. Riga Prima Nota: **ENTRATE=lordo · PROVVIGIONI · SALDO=lordo−provv (debito vs compagnia) · SOSPESI=+lordo · Banca=0**. Verificato: titolo €850/€85 → 850/85/765/850.
- **Incasso di titolo GIÀ coperto**: `incassa_titolo` per i titoli `titolo_coperto=True` crea `entrata/incasso_coperto` (provvigioni 0, sconto 0). Riga Prima Nota: **SOSPESI=−importo · BANCA=+importo**, nessun movimento su ENTRATE/PROVVIGIONI/SALDO (già contabilizzati alla copertura → niente doppioni). Segni invertiti per titoli negativi. Verificato: sospesi −850, banca +850, totale giornata sospesi netto 0.
- **KPI cumulativi** (`_compute_brogliaccio`): ENTRATE/PROVVIGIONI/SALDO includono le coperture (una sola volta, alla copertura); l'incasso del coperto non li riconta. SOSPESI KPI resta da `_total_sospesi_as_of` (titoli).
- **Saldo compagnie** (`_compute_saldi_compagnie`): incassi = `incasso_premio` + `copertura_titolo` → il debito verso la compagnia aumenta già alla copertura; `incasso_coperto` escluso (non cambia il debito).
- **Modello**: aggiunte le categorie `copertura_titolo` e `incasso_coperto` a `MovimentoCategoria` (db_models.py). Comportamento applicato solo ai movimenti futuri (storico invariato).


## Sessione 14/09/2026 (fork) — Fix Anagrafiche (premi/ricerca/collegati) + ripristino 2 sospesi

- **Ripristino sospesi** (tenant Axicura): i titoli correnti delle polizze **182259867** (€ 382,00) e **184642872** (€ 485,00), erroneamente `incassato`, riportati a SOSPESO (`titolo_coperto=True`, `stato=da_incassare`, `data_incasso=None`). Script `scripts/ripristina_sospesi_due.py`. Verificato a DB (compaiono in /titoli/sospesi; esclusi dall'E/C compagnia perché non più incassati).
- **🔴 Fix "premi e provvigioni a 0" nel network** (`routes/anagrafiche.py` `_stats`): leggeva solo `premio_totale`/`provvigione_totale`; le polizze Axicura usano `premio_lordo`/`provvigioni`. Aggiunto fallback → network SCHIANTARELLI JACOPO ora premio 56.399,85 / provv 4.749,80. Vale per lista Anagrafiche e card "Posizione assicurativa del network".
- **🔴 Fix ricerca "Aggiungi relazione"** (`AnagraficaDetail.jsx` AlberoGenealogico): caricava max 5000 anagrafiche lato client e filtrava → su tenant con >5000 anagrafiche (Axicura 5580, principale 10607) i nomi in fondo (es. VANOLI LUCIA) non si trovavano. Ora **ricerca server-side** `/anagrafiche?q=` (debounce 250ms, min 2 caratteri). Verificato: "bott" → 29 risultati dal server.
- **🔴 Fix nomi collegati troncati** (`index.css`): le regole CSS delle colonne congelate (`.tbl-scroll .freeze-*`) si propagavano via selettore discendente alla tabella annidata "Collegati" della riga espansa → prima colonna a 32px con ellissi ("B...", "SC..."). Aggiunto override `.tbl-scroll table table td/th` (width auto, no sticky/ellissi).


## Sessione 14/09/2026 (fork) — Brogliaccio: formule liquidità + KPI da Setup agenzia

- **Nuove formule liquidità** (`_compute_brogliaccio` + `statistiche_contabilita`): **Liquidità Disponibile = conti − debito compagnie** (non sottrae più i sospesi); **Liquidità Postera = conti + sospesi − debito compagnie** (ora somma i sospesi come incassi futuri). Descrizioni aggiornate anche in `BrogliaccioTab.jsx` e `StatisticheTab.jsx`. Verificato su tenant principale (disponibile −2305,32 / postera 750,68) e su Axicura (disponibile 221.615,68 / postera 253.401,96).
- **KPI cumulativi dai valori del Setup agenzia**: i KPI Entrate/Provvigioni/Spese/Rimesse ora includono i saldi di apertura del setup (`setup_iniziale_entrata/provvigione/spesa/rimessa`), prima esclusi dal `continue`. Per Axicura: Entrate 2.428.563,95 · Provvigioni 502.735,72 · Spese 483.506,91 · Rimesse 1.899.248,30. Il saldo dei **conti cassa resta invariato** (i valori setup sono solo KPI storici, non toccano i conti) e il `saldo_cassa` KPI non è influenzato dalle rimesse setup (accumulatori separati).


## Sessione 14/09/2026 (fork) — Voci manuali E/C Compagnie + fix Saldo Cassa Brogliaccio

- **Voci manuali su Estratto Conto Compagnie** (come per i collaboratori): CRUD backend già presente (`GET/POST/DELETE /api/compagnie/{cid}/voci-manuali`, collezione `voci_manuali_compagnia`, tenant-scoped). Completata l'**integrazione nel calcolo** (`_compagnia_estratto_data`): le voci con `tipo=dare` aumentano il dovuto alla compagnia, `tipo=avere` lo riducono; aggiunte come righe (`tipo=voce_manuale`) e nei totali (`totale_voci_manuali_dare/avere`, saldo). **UI** in `EstrattoContoCompagnie.jsx` (DettaglioEstratto): pulsante "+ Voce manuale" → dialog `VoceManualeDialog` (data, causale, tipo Dare/Avere, importo, note); le voci compaiono nella tab "Movimenti & versamenti" con badge "voce manuale" e ✕ per eliminarle. Verificato e2e (curl + UI: save +55€ → dare 257.489,60→257.544,60, delete → ripristinato).
- **🔴 FIX Saldo Cassa Compagnie nel Brogliaccio** (`_compute_saldi_compagnie`): prima aggregava TUTTI i movimenti `incasso_premio` senza escludere il pregresso e senza il saldo di apertura del setup → numero gonfiato (utente segnalava 248.916,11 vs atteso 27.300,43). Ora **coerente con l'estratto conto compagnia**: esclude `pregresso=True`, filtra dalla data di cutoff setup (go-live), e aggiunge il **saldo di apertura da setup iniziale** (`setup_iniziale_compagnia_dare/avere`). Per tenant Axicura `c5ae2d0e` il totale ora è **27.300,43 €** (CATTOLICA 26.732,00 + UCA 568,43), esattamente il valore atteso. Retrocompatibile: se il tenant non ha setup (cutoff None) mantiene la logica operativa precedente (verificato tenant principale: 5 compagnie, somma 2.913,83, nessun errore).


## Sessione 09/09/2026 (fork) — Batch 11: Storico credito, Catasto flag PDF, Camerale gratis, Anagrafica ricercabile, Anti-spam WhatsApp

- **Anti-spam WhatsApp** (alert_dispatcher.py): ritardo casuale **20–35s tra un messaggio WhatsApp e il successivo, per tenant**, su TUTTI gli invii automatici/massivi (schedule, soglia, evento, solleciti — tutti passano da `dispatch_rule`). Tecnica "prenota lo slot" (calcolo finestra sotto lock, sleep fuori dal lock) → invii concorrenti si accodano, il primo messaggio parte subito, gli invii singoli sporadici non subiscono ritardi. Guardia: throttle solo se c'è un numero WhatsApp. Config via env `WA_ANTISPAM_MIN_SEC`/`WA_ANTISPAM_MAX_SEC` (default 20/35). Verificato con unit test (spacing corretto, tenant indipendenti).
- **Catasto: base dati 0,30€ + flag "PDF ufficiale (1,90€)"** — `POST /openapi-it/cadastre/{aid}?pdf=bool`: senza pdf usa la `richiesta` (dati per riempire i campi, addebito "catasto" 0,30€); con pdf genera la visura PDF ufficiale (addebito "catasto_pdf" 1,90€). Flag/checkbox in OpenApiActions. Verificato via curl (100→99,70→97,80).
- **Camerale base GRATIS** — la ricerca/dati azienda (GET /impresa) è gratuita: listino `camerale`=0. I documenti PDF ufficiali (visure ordinaria/storica/bilancio ottico/certificati) ora **scalano dal credito il loro prezzo reale** (`meta["prezzo"]` da VC_DOC_META, es. ord. SdC 4,90 / storica 5,90 / bilancio ottico 4,50 / certificati 13,70) via `addebita_importo`. Nota UI "Dati gratis · PDF a pagamento".
- **Storico ricariche/consumi credito** (Super Admin) — `GET /super-admin/agenzie/{tid}/openapi-storico` (ricariche + movimenti + totali). Sezione Storico nel `CreditoOpenApiDialog` (ricariche a sinistra, consumi/estrazioni a destra, totali ricaricato/consumato). Verificato via curl.
- **Anagrafica ricercabile in "Aggiungi relazione"** (AnagraficaDetail.jsx, AlberoGenealogico) — sostituita la tendina lunga con un campo **ricercabile digitabile** (filtra per ragione sociale / CF / P.IVA, max 50 risultati, chip con ✕ per deselezionare). Frontend compila.
- **NOTA**: la Risk API (`POST /openapi-it/risk/{aid}`) esiste a backend ma NON è esposta nella UI (nessun pulsante). L'affidabilità aziende usata oggi è il "Report Azienda" dentro Camerale.

### ⏳ Import in background (09/09/2026) — fix timeout 520 su ZIP grandi
- Causa: l'import ZIP Omnia girava in un'unica richiesta sincrona → su file grandi superava il timeout del gateway (errore Cloudflare 520). Ottimizzata anche la regola stato (da N+1 a 4 query aggregate).
- **Soluzione job asincrono** (server.py): nuovo `POST /api/import/omnia-async` → crea un job in `import_jobs`, lancia `asyncio.create_task(_run_ania_job)` (il contextvar tenant viene copiato nel task → isolamento ok) e ritorna subito `{job_id}`. `GET /api/import/job/{job_id}` per lo stato (running/done/error + result/error). Il vecchio `/import/omnia` sincrono resta per compatibilità.
- Frontend (Importazione.jsx, ImportOmnia): l'upload usa l'endpoint async e fa **polling** ogni 2,5s fino a done/error, mostrando il risultato. Verificato ciclo job end-to-end (running→done).
- **TODO (richiesto dall'utente)**: estendere lo stesso pattern job async agli ALTRI import (Metodo Pagamento, Libro Matricola, Anagrafiche Excel) — pattern riutilizzabile già pronto.


- **Passo 1 — regola stato polizza** (`ania_importer._applica_regola_stato_da_titoli`, chiamata dopo i titoli): per ogni polizza importata, se l'ultimo titolo pagato ha `data_incasso ≥ 2025-01-01` → **attiva**; altrimenti → **annullata SOLO se la compagnia è CATTOLICA** (le altre restano come da tracciato Omnia).
- **Titoli con data pagamento → incassato**: in `_processa_titoli`, se il titolo ha `dt_pag_cliente` viene forzato `stato="incassato"` così finisce nei **Titoli storici** (idem nel Passo 2 se c'è DataPagam).
- **Collaboratori — unificazione fuzzy** (`_processa_collaboratori`): i collaboratori del flusso con nome simile a un collaboratore/utente già esistente (match su token del nome, ordine indifferente + subset ≥2 token) vengono **agganciati allo stesso utente** invece di creare doppioni/stub. Helper `_collab_tokens`.
- **Passo 2 — secondo file "Metodo Pagamento"** (`POST /api/import-massivo/metodo-pagamento`, `dry_run` opzionale): CSV `;` con più righe per polizza. Match polizza per `NumPolizza`; su ogni titolo corrispondente (match per Copertura→effetto/scadenza o DataPagam→data_incasso) scrive `data_copertura` ("Coperto il") + `mezzo_pagamento` (testo originale es. "RID BPER SONDRIO") + se c'è DataPagam `stato=incassato`; sulla polizza imposta `metodo_pagamento` (categoria: RID/SDD→sepa, BONIFICO→bonifico, CONTANTI→contanti, ASSEGNO→assegno, CARTA/POS→carta) + `metodo_pagamento_desc` (testo ultima rata). Nuovo tab UI "Metodo Pagamento" in Importazione.jsx (Seleziona CSV / Anteprima / Applica). Verificato via curl dry-run (166 righe, 66/66 polizze).


- Nuovo endpoint `POST /super-admin/agenzie/{tid}/elimina-definitiva` (body: `password_custode` + `conferma_ragione_sociale`): rimuove IRREVERSIBILMENTE dati + config tenant-scoped + TUTTI gli utenti (admin inclusi) + il record `tenants`. Crea un **backup gzip** in /app/backups prima di cancellare. Protezioni: solo super admin, password custode, match ragione sociale, blocco tenant di sistema (principale/demo/clean).
- Frontend SuperAdminPanel: pulsante 🗑️ (Trash2) per riga (`sa-elimina-{id}`) → `EliminaDefinitivaDialog` a 3 step (digita ELIMINA + ragione sociale + password custode; testid `elimina-*`). Distinto dalla cancellazione soft (`DELETE /agenzie/{tid}` = solo marca "cancellata") e dal reset dati (🔥 svuota dati ma tiene tenant+admin).
- Verificato via curl (403 pass errata / 400 nome errato / 200 + tenant sparito 404) e screenshot dialog.

### 🧩 Edit UI (09/09/2026) — AzioniPolizzaTab

- **Motivo annullamento** → da input libero a **Select** con opzioni predefinite (Disdetta, Mancato pagamento, Sinistro, Vendita veicolo, Demolizione, Furto, Esportazione, Sostituzione, Passaggio ad altra compagnia, Recesso, Altro).
- **Sospensione — limite di legge**: sotto "Riattivazione prevista" mostra nota "Massimo di legge: 10 mesi per annualità"; con le due date calcola durata (mesi) + residuo su 10 e avvisa se si superano i 10 mesi (`sosp-durata-info`). Calcolo client-side sulle date correnti (non traccia ancora lo storico cumulativo di annualità).

### 🔒 Code review (09/09/2026) — fix applicati + falsi positivi
- **FIX** `routes/contratto_extra.py`: OTP firma contratto ora usa `secrets.randbelow(1000000)` invece di `random.randint` (crittograficamente sicuro).
- **FIX** `routes/super_admin.py`: password custode reset tenant spostata da hardcoded a env `RESET_CUSTODE_PASSWORD` (+ guardia: rifiuta se env vuota). Valore in backend/.env.
- **FALSO POSITIVO** marketing_studio.py:376/387 "exec() injection" → è `asyncio.create_subprocess_exec` (chiamata ffmpeg sicura con lista argomenti, nessuno shell). Nessun `exec()`. Nessuna azione.
- **NON applicati (di proposito, alto rischio / nessun beneficio su app in produzione)**: split server.py (229 import), refactor complessità dispatch_query/send_whatsapp, "circular import" database↔tenant (app funzionante, refactor rischioso), "65 undefined variables" (vaghi, probabili falsi positivi del linter), dynamic imports (lazy import intenzionali), `random` in demo_seed/openapi_it_service/seed (dati mock/demo, non security-sensitive).


### ❌ Decisioni dell'utente — NON FARE (09/09/2026)
- **Paga Agenzia Partner** (versamento premi collaborazione su IBAN partner) → l'utente ha deciso di NON farlo. Rimosso dal backlog.
- **Attiva CAP + Geocoding** → NON fare (l'utente non lo vuole).
- **Pulsante Affidabilità (Risk)** in scheda cliente → NON fare (l'utente non lo vuole).



- **Portafoglio credito OpenAPI per agenzia** (nuovo `openapi_credito.py`): credito prepagato salvato sul documento `tenants` (`openapi_credito_eur`), gestito dal Super Admin. Ogni estrazione OpenAPI (Camerale/Catasto/Veicoli/Visure/Visura/Report) ha un costo (listino) e viene addebitata prima dell'esecuzione; se il credito è insufficiente → **HTTP 402 bloccato** con messaggio chiaro. **Nessuna regressione**: se il tenant non ha credito configurato (`None`) il wallet è "non attivo" → nessun blocco/addebito (le agenzie esistenti continuano come prima).
- **Listino costi configurabile dal Super Admin** (`raw_db.openapi_config`): default = prezzi base singola richiesta OpenAPI.it (camerale 0,30 / catasto 1,90 / veicoli 0,30 / visura 4,90 / visure 4,90 / report 5,00). Endpoint `GET/PUT /super-admin/openapi-listino`.
- **Super Admin UI** (SuperAdminPanel.jsx): colonna "Credito API" per agenzia, pulsante 🪙 per **impostare/ricaricare** (`CreditoOpenApiDialog`, modo add/set → `POST /super-admin/agenzie/{tid}/openapi-credito`), pulsante "Listino OpenAPI" (`ListinoOpenApiDialog`).
- **OpenApiActions.jsx**: badge mostra ora il **credito dell'agenzia** (non più il credito account OpenAPI.it), ogni pulsante mostra il **costo** dell'estrazione, e viene **disabilitato** se il credito è insufficiente. `/openapi-it/status` arricchito con `tenant_credito_eur` + `account_credit_eur` + `listino`.
- Endpoint strumentati con addebito: `POST /openapi-it/{company,cadastre,vehicles,visura,visengine/request,report-azienda}`.
- Verificato e2e: set credito 100€ → catasto scala a 98,10€; credito 1€ → catasto bloccato 402; ricarica OK; UI card mostra "Credito agenzia €100" + costi per pulsante; pannello Super Admin con colonna + dialog.
- **Form Nuova polizza — ordine invertito Agenzia → Compagnia** (Polizze.jsx): il campo "Agenzia (mandato)" è ora la **prima scelta** (elenca principale=diretto + tutte le partner). La tendina "Compagnia" è disabilitata finché non si sceglie l'agenzia e mostra **solo le compagnie collegate a quell'agenzia** (principale → compagnie a mandato diretto; partner → compagnie con quel `agenzia_partner_id`). Cambiando agenzia si azzera la compagnia. Risolve l'ambiguità delle compagnie omonime con partner diversi. Verificato e2e (Bottoni → UnipolSai/TEST/GROUPAMA).

## Sessione 09/09/2026 (fork) — Batch 9: Fix Estratto Conto Compagnie + header polizza

- **Colonna "Agenzia partner" in Estratto conto compagnie** (EstrattoContoCompagnie.jsx): l'endpoint `/compagnie/saldi-cassa` ora restituisce `tipo_mandato` + `agenzia_partner_id` + `agenzia_partner_nome`. La tabella mostra, per i mandati in collaborazione, l'agenzia partner a cui versare (icona Handshake, viola); per i diretti "Diretto (compagnia)". Se collaborazione senza partner impostato → "partner non impostato" (ambra). Verificato via API + screenshot.
- **Colonna "Agenzia partner" anche nel widget "Saldo cassa per compagnia"** (BrogliaccioTab.jsx / Prima nota): `_compute_saldi_compagnie` ora include `tipo_mandato`/`agenzia_partner_id`/`agenzia_partner_nome`. Stessa resa (partner viola / "Diretto (compagnia)"). Verificato via API + screenshot.
- **NOTA modello dati (chiarita all'utente)**: stessa compagnia con DUE agenzie partner diverse (es. GROUPAMA·Bottoni e GROUPAMA·Pozzi) = due record compagnia distinti con lo stesso nome ma `agenzia_partner_id` diverso; la colonna "Agenzia partner" li distingue. Diverso dal doppione vuoto rimosso.

- **🔴 FIX P0 — Compagnia mancante dall'Estratto Conto Compagnie**: `_compagnia_estratto_data` (server.py ~riga 936) faceva `contr_map[c["id"]] = c["ragione_sociale"]` con accesso diretto alla chiave → per un contraente **persona fisica** (senza `ragione_sociale`) lanciava `KeyError`, l'intera funzione andava in eccezione e `saldi_cassa_compagnie` la scartava in silenzio (`try/except: continue`) → la compagnia (GROUPAMA GPM) spariva dall'estratto. Corretto con `c.get("ragione_sociale") or "{cognome} {nome}"`.
- **🔴 FIX P0 — Coerenza "trattiene provvigioni"**: l'estratto conto **forzava** `trattiene=False` per i mandati `collaborazione`, mostrando il DARE al lordo (es. 489€) mentre Brogliaccio/Saldo cassa usavano il flag della compagnia. Rimossa la forzatura: ora l'unica fonte di verità è `compagnia.trattiene_provvigioni`. GROUPAMA (trattiene=sì) → DARE al netto provvigioni = 443,41€ (489 − 35,59 − 10). La polizza 1212 dà 90€ come nel Brogliaccio.
- **Data cleanup**: eliminato il doppione compagnia vuoto "groupama" (cod. 005, 0 polizze/titoli/movimenti) nel tenant `tenant-principale-schiantarelli`. Resta la sola "GROUPAMA" (cod. GPM, 22 polizze).
- **PolizzaDetail header**: ripristinato il **nome dell'agenzia partner** sotto il numero polizza (`pol-header-agenzia-partner`), mostrato solo se presente (`pol.mandato`). Nella modifica precedente era stato rimosso del tutto per errore.
- Verificato via API autenticata + screenshot UI (E/C compagnie: GROUPAMA 443,41€, 11 compagnie, doppione sparito).



## Sessione 09/09/2026 (fork) — Batch 8: Modelli PDF per sezione, generazione documenti, unione Documenti, Task collegabili

- **5 modelli PDF predefiniti per sezione** (auto-seed da `/app/backend/assets/modelli_default/*.json`, idempotente): Scheda anagrafica cliente, Modulo RID/SEPA, Autocertificazione stato di famiglia (contraente); Documento di polizza (polizza); Documento di sinistro (sinistro). Corpi generati via AI (Claude) con segnaposto.
- **Motore generazione documenti** (`routes/documenti_genera.py`): `GET /api/documenti/modelli-sezione?sezione=`, `POST /api/documenti/genera` (compila i segnaposto coi dati reali di contraente/polizza/sinistro, PDF reportlab, salva=true → allegato categoria `documento_generato`, opzione firma eSAW). Segnaposto speciale `{stato_famiglia}` espande i familiari del cliente (campo `parente_di`).
- **Pulsante "Genera documento"** (`components/GeneraDocumentoButton.jsx`) in AnagraficaDetail (Documenti), PolizzaDetail (accanto a MUP), SinistroDetail (Documenti): seleziona modello → testo editabile → Anteprima/Firma/Genera e archivia. Verificato e2e (12/12 backend iter 83, frontend OK).
- **Unione blocchi Documenti (AnagraficaDetail)**: caselle fisse (CI/patente/CF/…) + allegati caricati ora in UN unico blocco "Documenti" con griglia uniforme. Rimossi i doppioni "Visura camerale" e "Documenti identità" dalle cartelle allegati (i file confluiscono in "Altri documenti").
- **CarichiMensili**: colonna Note non più troncata (va a capo).
- **Task collegabili** (`routes/tasks.py`): campi `collegamento_tipo` (anagrafica|polizza|titolo) + `collegamento_id` + `collegamento_label`; `GET /api/tasks/collegati?entita_tipo=&entita_id=` (default solo attivi). Dialog Task con selettore "Collega a" + ricerca (cliente/polizza). Pannello "Attività aperte collegate" (`components/TaskCollegati.jsx`) in scheda cliente e polizza, con completamento rapido. Verificato via curl + screenshot.

## Sessione 09/09/2026 (fork) — Batch 7
: MUP libreria + testo + flag sezione, bug PDF, campo agenzia partner, provv. collaboratore, unisci doppioni

- **MUP → libreria (Librerie → "Modelli MUP")**: nuova collezione `mup_modelli` tenant-scoped (backend `routes/mup.py`): CRUD `/librerie/mup-modelli`, seed 5 modelli predefiniti per ramo (Auto/RC Auto, Beni, Infortuni, Vita, Generica). Il MUP di polizza usa il modello con l'area corrispondente (o quello scelto nel selettore). Componente `ModelliMupSezione`/`ModelloMupDialog` in `Librerie.jsx`.
- **MUP → modale editabile in polizza (era MANCANTE dal fork)**: `PolizzaDetail.jsx` ora renderizza `mup-dialog` con selettore modello, tabella garanzie con checkbox richiesta/proposta/confermata, Anteprima PDF, Genera+archivia (allegato categoria `mup`), Firma eSAW. Quadrato "MUP" aggiunto nella sezione Documenti.
- **MUP → testo precontrattuale con aggancio dati**: campo `corpo` sul modello MUP con segnaposto ({contraente},{cliente_cf},{compagnia},{collaboratore},{agenzia_nome},{agenzia_rui},{numero_polizza},{ramo},{prodotto},{premio_lordo},{data_oggi}), sostituiti coi dati reali nel PDF (`_ph_context`/`_sub`).
- **BUG FIX MUP PDF**: le garanzie non spuntate apparivano tutte "piene" (glifi ☑/☐ non supportati da Helvetica). Ora: spuntata = "SÌ", non spuntata = "—". Verificato via pdfplumber.
- **Flag visibilità per sezione (contraente/polizza/sinistro/preventivo)** su ENTRAMBI i tipi di modello (`TemplateModello.sezioni_visibili`, `MupModello.sezioni_visibili`). List endpoints accettano `?sezione=`; nessun flag = non visibile (backfill dei modelli esistenti a tutte le sezioni). UI: `SezioniVisibiliPicker` in entrambi i dialog. Consumatore LIVE: selettore MUP in polizza filtra a `sezione=polizza`. NOTA: per contraente/sinistro/preventivo i picker "genera documento da modello" non esistono ancora → follow-up per consumare i flag lì.
- **Polizze (form nuova polizza)**: campo "Collaboratore (Operatore)" spostato SOPRA "Contraente"; nuovo select "Agenzia partner" accanto a Compagnia, precompilato in base alla compagnia (diretto→principale, collaborazione→agenzia partner).
- **PolizzaDetail → Provvigioni**: accanto al nome collaboratore mostrato l'importo "Provv. collaboratore" (`pol-collab-provv-inline`).
- **BUG FIX Anagrafiche**: pulsante "Unisci doppioni" non apriva nulla (dialog non montato) → montato `UnisciDoppioniDialog`.
- **Utenti/Collaboratori**: solo personale di agenzia (no clienti, no super_admin, solo tenant proprio). `list_users` in server.py.
- **Agenzie**: l'agenzia principale collega compagnie a mandato diretto (dialog dedicato + conteggio backend).
- **Modelli → Carica PDF (tab PDF)**: `POST /librerie/modelli/da-pdf` estrae testo (pdfplumber) e crea modello con segnaposto via Claude (Emergent LLM Key).

## Sessione 09/09/2026 (fork) — Batch 6
: Utenti solo staff, Agenzia partner label, Principale mandato diretto, Modelli da PDF (AI)

- **Librerie → Utenti / Collaboratori: solo personale di agenzia**. La lista `/auth/users` ora filtra i `role === "cliente"` (i clienti si gestiscono in Anagrafiche). Rimossa l'opzione ruolo "Cliente" dal form utente e il relativo blocco "Anagrafica cliente collegata". Verificato a schermo (15 elementi: admin/collaboratori/dipendenti, nessun cliente). `Librerie.jsx` (`load`, `UtenteForm`).
- **PolizzaDetail: "Mandato" → "Agenzia partner"** (header blu + form modifica). Il valore `pol.mandato` rappresenta l'agenzia partner (terminologia utente). Solo label.
- **Agenzie → l'agenzia PRINCIPALE può collegare le compagnie a mandato diretto**. Prima il pulsante "Collega compagnie" era solo per le partner. Ora la card principale mostra "Compagnie con mandato diretto: N" + pulsante. `CollegaCompagnieDialog` è tenant/tipo-aware: per la principale pre-seleziona le compagnie senza `agenzia_partner_id` (=diretto), selezionandone una collegata a partner la riporta a `tipo_mandato=diretto, agenzia_partner_id=null`. Backend `routes/agenzie.py`: `n_compagnie_collegate` per la principale = `count(agenzia_partner_id=None)`. Verificato UI + curl (principale=7).
- **Librerie → Gestioni Modelli: "Carica PDF" (tab PDF)**. Nuovo endpoint `POST /api/librerie/modelli/da-pdf` (`routes/modelli.py`): estrae il testo con pdfplumber, lo trasforma via **Claude (claude-sonnet-4-6, Emergent LLM Key)** in un modello con i `{segnaposto}` del CRM (whitelist `_PLACEHOLDER_DISPONIBILI`), lo salva come `TemplateModello` (categoria `da_pdf`) e lo apre nel form per la revisione. UI: pulsante `modelli-carica-pdf` visibile solo nella tab PDF. Verificato e2e via curl (lettera → template con cliente_nome/numero_polizza/compagnia_nome/data_scadenza/premio_lordo/azienda_*).
- **MUP**: backend (`routes/mup.py`) + modale editabile in `PolizzaDetail.jsx` (checkbox garanzie per ramo, genera/anteprima/archivia tra gli allegati polizza categoria `mup`, firma eSAW) già completi. In attesa di test lato utente.


## Sessione 08/09/2026 (fork) — Batch 5: Estratto conto, Report Azienda, Immobili, Documenti, eSign

- **Report di gruppo** (`?gruppo=true` su report-azienda pdf/docx): sezione "Società del gruppo — quadro consolidato" con capogruppo + collegate (da `parente_di`) e riga TOTALE GRUPPO. Il frontend chiede conferma se ci sono collegate. Estratto conto già supporta il gruppo via `includi_collegati`. Verificato via curl.

- **Estratto conto contraente** (nuova pagina `/contraente-estratto`, sidebar contabilità): elenco titoli di un contraente in un periodo con filtri (rata/emissione/copertura), dati di pagamento (metodo con fallback conto cassa), totali (premi/addizionali/già pagato/DA PAGARE), preview + PDF. Pulsante **"Salva in anagrafica"** → allegato categoria `estratto_conto` (nuova cartella "Estratti conto" nei Documenti). Include contraenti collegati opzionale. `routes/estratto_conto_contraente.py`. Testato iter 79/80.
- **Report Analisi Azienda PDF + Word** (`routes/report_azienda.py`, pulsanti in Salute Fiscale `sf-report-pdf-btn`/`sf-report-word-btn`): prende dati reali da `salute_fiscale_dati` (bilancio, storico, indicatori), amministratori, MDC/impatto e include la **Piramide Azienda**. Struttura ispirata al modello "insurance advisor" (intro Studio, dati anagrafici, soggetti, analisi economica, indici, note legali + disclosure AI). Testato iter 80.
- **Sezione Immobili per aziende** (`ImmobiliSection.jsx` in Salute Fiscale): import Catasto + Geolocalizza + mappa Leaflet con **4 livelli** (Stradale/Satellite/Ibrida/Topografica), tasto **Mappa**. Opzione **"In affitto (preso in locazione)"** aggiunta al Titolo per privati e aziende. Campo **Piano** separato dall'indirizzo (split automatico all'import per non rompere il geocoding). Colori marker più visibili. `ImmobiliMap`/`ImmobileRow` resi export riutilizzabili.
- **Piramide**: tasto **Stampa** (`piramide-stampa-btn`) che apre finestra di stampa con gli stili applicati.
- **Tab Documenti ristrutturato**: sezione "Documenti per categoria" comprimibile con conteggio (`doc-cards-toggle`), ogni card comprimibile singolarmente (`doc-card-toggle-*`), sezione allegati integrata (rimossa Card/titolo duplicato, "Carica file" in alto), cartelle allegati comprimibili con conteggio. Testato iter 81 (100%, nessuna regressione).
- **Firma Privacy con eSignAnyWhere (Namirial)**: collegato il dialog Privacy & Consensi al flusso firma esistente (`POST /api/firma/richieste`) — pulsante `cons-firma-esign`. Richiede config eSign in azienda_config (presente in produzione, assente in preview → errore gestito).
- **Fix**: errore cancellazione voce Diario (conflitto di due route `DELETE /diario/{id}` → unificata con fallback su db.diario; duplicato spostato su `/diario-cliente/{id}`). Tab "Profilazione & GDPR" rinominato "**Privacy / GDPR**", rimossa sezione "Profilo aziendale".
- **Edit visivi PolizzaDetail/Sinistri**: Ultimo premio pagato nell'header blu; riga N.polizza sotto il prodotto; Sinistri lista senza link polizza; SinistroDetail con link polizza.
- ⏸️ **Rimandato dall'utente**: integrazione eSignAnyWhere con credenziali proprie (skippato "defaults for now").


## Sessione 08/09/2026 (fork) — Batch 4: FIX IMAP allegati, Piramide Azienda dati reali, Contratto PDF/Word

- **🔴 FIX P0 IMAP allegati mancanti (polizza 184643415)**: root cause reale — il modello `Allegato` richiede `content_type`/`size`, ma `imap_poller.py` costruiva `Allegato(...)` con i vecchi campi `mime`/`size_kb` → `ValidationError` ingoiata dal `try/except` → gli allegati non venivano MAI salvati. Corretto in `_copia_allegato_su_entita` e `_auto_allega_polizza` (ora `content_type=`, `size=`; `url` aggiunto come extra al dict). Aggiunto **backfill** `POST /api/email/poller/retry-allegati` (+ `retry_auto_allega` in imap_poller) che ri-processa gli allegati delle email GIÀ ingerite senza match (l'email era arrivata prima che la polizza esistesse; il re-polling salta le email già ingerite). Idempotente. Eseguito su Schiantarelli: con_match=49, allegati_polizza=37. Verificato: polizza 184643415 (bacebe55, tenant schiantarelli) ora ha l'allegato 'Contratto Active Veicoli AUTOCARRI 184643415.pdf'; la stessa polizza nell'altro tenant (31b4950e) NON è stata toccata (isolamento tenant OK).
- **🔴 Piramide Azienda popolata con dati REALI**: `prepopola_piramide_v2` (ramo persona_giuridica, server.py) ora legge da `salute_fiscale_dati.bilancio_estratto` + governance OpenAPI: Fatturato=valore produzione, Utile=utile netto reale, EBITDA=ebitda reale, N. dipendenti=dipendenti reali, N. soci=len(company.soci), Patrimonio netto. Fonte='salute_fiscale_azienda'. Prima erano stime derivate dal fatturato (r*0.5, r*0.8...). Sidebar `PiramidePrivati.jsx` (aziende): rinominata la 6ª voce da 'Perdita beni' a 'Patrimonio netto'. Verificato su AUTOTRASPORTI VIVIANI.
- **📄 Contratto di Consulenza PDF+Word ben impaginato**: nuovo modulo `contratto_render.py` (`build_pdf` ReportLab Platypus + `build_docx` python-docx). Impagina il campo `testo` come documento legale: header logo agenzia + ragione sociale/P.IVA/RUI, titolo centrato, premesse, articoli giustificati con 'Art. N (...)' in grassetto, blocco firme a 2 colonne, clausola approvazione ex art. 1341/1342 c.c., note legali + disclosure AI a piè pagina, numero pagina. Endpoint `GET /anagrafiche/{aid}/contratto-consulenza/pdf` e `/docx`. La firma OTP ora genera il PDF impaginato (non più `_pdf_da_testo` grezzo). UI: pulsanti 'Anteprima PDF' + 'Scarica Word' in `ContrattoConsulenzaTab.jsx` (con fallback download se popup bloccato). Base per futuri modelli PDF/gestione email avvisi.
- **Modifiche UI (agentic edit)**: PolizzaDetail — 'Ultimo premio pagato' spostato nell'header blu in alto a destra (rimosso dalla griglia bianca); riga 'N. polizza · Mandato' ingrandita (text-lg) e allineata a sinistra sotto il nome prodotto. Sinistri lista — colonna 'Contratto' non più link alla polizza (solo testo). SinistroDetail — riga 'Contratto' resa link cliccabile alla polizza (data-testid sinistro-polizza-link).
- Testato: iter 78 PASS 100% (backend 6/6, frontend 100%). Nessun issue critico.


## Sessione 08/09/2026 (fork) — Batch 3: Chat WhatsApp, Avatar, Documenti polizza da Drive

- **💬 Tab "Chat WhatsApp"** (scheda cliente): anteprima conversazione stile WhatsApp (bolle verdi in uscita a destra, bianche in entrata a sinistra), orari, nome mittente e foto/media caricati on-demand (`/whatsapp-evo/messages/{id}/media` come blob). Backend `GET /anagrafiche/{aid}/whatsapp-chat` (match sulle ultime 9 cifre del cellulare su `whatsapp_messages`). Testato: BALZAROLO ALESSIA 51 messaggi (28 out/23 in, 3 media). `WhatsAppChatPreview.jsx`.
- **Avatar auto-crop volto**: `face_crop.crop_volto_bytes` ora prova le rotazioni 0/90/180/270 (i documenti scansionati sono spesso ruotati) + validazione tono-pelle per evitare ritagli errati. Verificato sulla C.I. reale caricata dall'utente (volto ritagliato correttamente). Applicato anche all'upload manuale dell'avatar.
- **Documenti polizza da Google Drive**: pulsante "🔍 Cerca su Google Drive" nel tab Documenti della polizza → `POST /librerie/cloud-storage/cerca-documenti-polizza/{id}` cerca i PDF (fullText + nome) contenenti il numero polizza nella cartella collegata e li allega alla polizza (categoria "polizza", visibile_cliente). Batch `POST /cerca-documenti-tutte-polizze` abbina per numero-nel-nome su tutte le polizze del tenant (cap download). Riusa l'integrazione Drive OAuth esistente (`_fresh_access_token`, StorageService). Testato: auth Drive OK, ricerca eseguita. NB: la cartella collegata "Assicura CRM" è al momento SENZA PDF → 0 risultati finché non ci si caricano i file. La polizza 184643409 è in un tenant SENZA Drive collegato.
- **Import**: toast di fine importazione in ImportMassivo ora con conteggi (creati/aggiornati/saltati/errori).
- Testato: iter 76 PASS 100%.

### ⏳ In sospeso — serve input utente
- **Fonte IMAP** per i documenti polizza: da configurare (serve host IMAP + utente + password/app-password). Integrazione da fare via integration_expert una volta ricevute le credenziali.



## Sessione 08/09/2026 (fork) — Batch 2: Piramide tab, Documenti unificati, scenari, avatar

- **Tab "🔺 Piramide Azienda"** (persone giuridiche): nuovo tab dedicato (`tab-piramide-azienda`) con pulsante "Precompila da bilancio" che riempie la piramide coperture (modello aziende) dai dati di bilancio (valore produzione) + polizze attive. Backend `prepopola_piramide_v2` reso azienda-aware. `PiramideCopertureNuova` esportata. (Il pulsante resta anche dentro Salute Fiscale.)
- **Documenti unificati**: un solo tab "Documenti" con i documenti fissi del cliente in alto + sezione "Documenti raccolti" con cartelle per categoria (Visura Camerale/Catastale/Bilancio/…). Rimosso il tab "Altri allegati". Smistamento migliorato: file con "bilancio" nel nome finiscono nella cartella Bilancio anche se categoria=visura_camerale.
- **Andamento fatturato**: grafico a barre multi-anno (Recharts) nella card storico della Salute Fiscale.
- **Salva scenari per cliente**: pulsante "💾 Salva scenari" nel Margine di Contribuzione → salva rows/%/giorni/scenari/risk in `anagrafica.salute_fiscale_scenari` (via PUT /anagrafiche) e li ricarica all'apertura. Persistenza verificata.
- **Avatar auto-crop volto**: migliorato `face_crop._detect_face_opencv` con validazione tono-pelle (YCrCb) + minNeighbors=7 per eliminare i falsi positivi ("ritagliava zone non pertinenti"); se incerto NON ritaglia (fallback icona). Il crop volto ora si applica anche all'upload manuale dell'avatar (se trova un volto sicuro). NON testato via UI (euristica backend).
- Testato: iter 75 PASS 100% (Piramide tab, unificazione Documenti, grafico fatturato, salva scenari, smistamento Bilancio).

### ⏳ In sospeso
- "Anteprima chat": scelta modalità (riga/bolle/pulsante dedicato) ancora da definire.



## Sessione 08/09/2026 (fork) — Cruscotto Salute Fiscale azienda + rifiniture

### ✅ Salute Fiscale unificata (fusa con Analisi Azienda) — tab-salute-fiscale
- Rimosso il tab separato "Analisi Azienda"; ora `SaluteFiscaleTab` renderizza in cima la Panoramica azienda + Soci/Governance/Forza lavoro (AnalisiAziendaTab) e sotto i blocchi finanziari.
- Conto economico dettagliato + Stato patrimoniale + Storico bilanci + Indicatori (già in sessione precedente).
- **Margine di Contribuzione** (`sf-mdc-card`): auto-import dal bilancio OpenAPI. Formula verificata sul PDF ufficiale VIVIANI: MDC 2025 = 3.830.606,90 € (Ricavi di vendita = Valore produzione IIC130 6.889.188; Rimanenze finali = rimanenze totali IIC045 42.000; % non assicurata default Servizi 70% / Amministrativi 30%). Voci e % editabili, ricalcolo live.
- **Metriche di impatto** (`sf-impatto-card`): MDC giornaliero × giorni scenario; scenari Trascurabile/Gestibile/Grave/Critico con giorni configurabili (default 20/58/115/189); Risk Tolerance/Appetite configurabili; grafico a barre Recharts.
- **Studio di bilancio** (`sf-studio-card`): Ciclo circolante, MOL/OF, Val.agg/immobilizzi, Ricavi/crediti — barra colorata con marker STATICO (l'utente ha chiesto NON modificabile). + "Altri indici utili": Margine di tesoreria e Indice di disponibilità.
- **🔺 Piramide Azienda** (`sf-piramide-btn`): apre la Piramide delle Coperture (modello "aziende") e la precompila con i dati di bilancio (endpoint `POST /anagrafiche/{id}/analisi/piramide-v2/prepopola` reso azienda-aware: base = valore produzione/fatturato). `PiramideCopertureNuova` ora esportata da AnalisiClienteTab.
- Backend `company_financials()` in openapi_it_service arricchito (rimanenze, crediti clienti, debiti fornitori/breve, immobilizzazioni, attivo circolante). Endpoint `salute-fiscale/da-openapi` corregge PN vs perdita e ritorna ~30 voci.

### ✅ Governance & rifiniture
- Campi Amministratore/Referente azienda (+ email/telefono) con "Compila da OpenAPI" (`POST /openapi-it/governance/{aid}`) — auto-fill legale rappresentante.
- Traduzioni IT (`_trad_it`): ruoli governance, dimensione impresa; descrizione ATECO ora in italiano (usa campo RAE); forma giuridica IT.
- IBAN salvato nei Conti Correnti riportato nel campo IBAN Anagrafica (sync in save + fallback in visualizzazione).
- Tab Polizze mostra solo le ATTIVE con toggle "Mostra tutte"; conteggio tab = attive.
- Documenti allegati raggruppati in CARTELLE per categoria (Visura Camerale/Catastale/Bilancio/…) — `AllegatiCartella` collassabili.
- Conferma AlertDialog prima di ogni download OpenAPI (tutti i pulsanti). Rimosso il pulsante "Visura" singolo da OpenApiActions.
- Testato: iter 71/72/73/74 tutti PASS 100%.

### ⏳ In sospeso (richiesta utente in pausa)
- "Anteprima chat" nel Diario/anagrafica: da chiarire l'opzione desiderata (a/b/c) prima di implementare.



## Sessione 08/09/2026 (fork) — Salute Fiscale ricca da OpenAPI + Conferma download OpenAPI

### ✅ Salute Fiscale (P0) — dati "più corposi" e KPI corretti da company.openapi.com
- Nuova funzione `openapi_it_service.company_financials(cf_piva)`: legge company.openapi.com **IT-full** e ricostruisce il conto economico dettagliato dalle voci codificate IIC/IPL (subset productionValue/productionCosts/revenuesFinancialCharges/annualResult/incomeStatementAggregateValues + assetsAggregateValues/liabilitiesAggregateValues/netWorth/debts). Aggiunge `operatingResults` (EBITDA/EBIT/cash flow), `ecofin` (netWorth reale, turnover, trend), `employees`, tutti gli indici ufficiali (redditività, liquidità, leva, kpi, struttura, indebitamento, copertura) e lo **storico fatturato** (IT-advanced balanceSheets.all, ultimi 6 anni).
- `POST /anagrafiche/{aid}/salute-fiscale/da-openapi` (routes/extras_p1p2.py) riscritto: bilancio_estratto ora contiene ~24 voci (Ricavi, Valore produzione, Costi produzione/materie/servizi/godimento beni/personale, Ammortamenti, Oneri diversi, EBITDA/EBIT, Proventi/Oneri finanziari, Utile lordo, Imposte, Utile netto, Cash flow, Totale attivo/debiti, PN, Capitale sociale, dipendenti, trend). **BUG CORRETTO**: prima metteva come patrimonio_netto la perdita d'esercizio (-8.052) e ricostruiva l'utile da ROE; ora PN=451.553 (IIC084/ecofin) e utile netto=IIC179 reale. Indicatori estesi: ROE/ROI/ROS, EBITDA margin, Leva (Att/PN), PFN/EBITDA, Oneri fin./Ricavi, Pressione fiscale, Incidenza personale. Verificato via curl su AUTOTRASPORTI VIVIANI (00920050143, LIVE).
- Frontend `SaluteFiscaleTab.jsx`: al click di "⚡ Compila da OpenAPI" ora fa `setDati(r.data)` immediato (UI si aggiorna all'istante, niente più "non aggiorna"); rendering arricchito con sezioni Conto economico + Stato patrimoniale + Storico bilanci (`sf-storico-card`) + Indicatori. Testato e2e (iter 71): score 7, nessun campo vuoto.

### ✅ Conferma download OpenAPI (richiesta agentic-edit) — `OpenApiActions.jsx`
- Prima di scaricare/aprire QUALSIASI servizio OpenAPI (tutti e 5 i pulsanti: Camerale, Catasto, Veicoli, Visure & Doc., Visura) compare un **AlertDialog** (`openapi-confirm-dialog`) "Scaricare i dati da OpenAPI.it?" con avviso consumo credito + bottoni Annulla (`openapi-confirm-cancel`) / Scarica (`openapi-confirm-ok`). Helper `guard(label, fn)`. Testato e2e (iter 71) su persona fisica: dialog compare su tutti i 5, Annulla chiude senza chiamata.
- NB: `OpenApiActions` è renderizzato nel tab "Dati" per le persone fisiche e nel tab "Analisi Azienda" (AnalisiAziendaTab.jsx) per le persone giuridiche — il gate a riga 211 di AnagraficaDetail.jsx è INTENZIONALE (evita duplicati), NON un bug.



## Sessione 02/09/2026 (fork) — parte 6: Biblioteca Centralizzata (globale) + note Veicolo

### ✅ Biblioteca Centralizzata (opzione A — libreria unica globale)
- `database.py` (TenantAwareCollection): `schede_calcolo` e `biblioteca_jobs` sono ora FULLY_SHARED (una sola libreria globale, tenant `__global_library__`). `biblioteca_previdenza` e `_cartelle` sono MIXED: lettura = tenant corrente OPPURE globale (così le agenzie vedono le proprie Condizioni + la Previdenza globale); super-admin (senza tenant) → solo globale.
- `biblioteca_previdenza.py`: gli upload/cartelle/delete della sezione **previdenza** sono consentiti SOLO al super-admin (403 per le agenzie); gli insert previdenza vanno su tenant globale. Le agenzie leggono (per i calcoli INPS/pensione via RAG/AI) ma non gestiscono.
- Frontend: le agenzie NON vedono i tab Previdenza/Schede (già nascosti). Super-admin: nuovo link "Biblioteca" → `/super-admin/biblioteca` (pagina con Previdenza + Schede + gestione). 
- Verificato via API: super-admin carica previdenza (cartella INPS) → l'agenzia TEST la legge; upload previdenza da agenzia → HTTP 403.

### ℹ️ Veicolo in polizza (già presente)
- Il tab "Veicolo" nel form di Modifica polizza usa già `TargaSearchWithLentina`: si digita la targa (editabile), ricerca live in archivio; se manca → "Crea nuova targa" con dati manuali + upload libretto. Nessuna modifica necessaria.



## Sessione 02/09/2026 (fork) — parte 5: Auto-quietanza + Promemoria upload

### ✅ Data prima quietanza calcolata automaticamente (Polizze.jsx)
- Nel modale nuova polizza la "Data prima quietanza" si compila da sola = effetto + periodo del frazionamento (annuale +12m, semestrale +6m, quadrimestrale +4m, trimestrale +3m, mensile +1m). Resta modificabile a mano (se toccata non viene più ricalcolata). Helper `addPeriodo`.

### ✅ Promemoria Upload documenti (scheduler_alert.py + upload_link.py)
- I link documento non ancora caricati vengono ri-sollecitati automaticamente ogni `reminder_giorni` (default 3, impostabile alla creazione), max 3 solleciti, sul canale scelto dal cliente in anagrafica (email/whatsapp/sms). Job cron 07:00. Riusa i sender di alert_dispatcher (CHANNEL_ADAPTERS). Smoke test OK (invio saltato in TEST perché provider non configurato, nessun crash).

### ⏳ Biblioteca Centralizzata (#2) — NON ancora implementata: serve scelta di approccio
- Le sezioni Previdenza + Schede sono lette dalla knowledge base AI (notebooklm RAG, ai_copilot schede). Renderle globali richiede una scelta:
  - A) **Libreria globale condivisa** (una sola copia; super-admin scrive, tutte le agenzie leggono la stessa): modifica dell'isolamento per previdenza/schede + adeguamento dei percorsi di lettura AI. Più pulito ma tocca l'isolamento.
  - B) **Propagazione a copie**: super-admin gestisce una libreria master e un pulsante "Propaga" copia i documenti su tutte le agenzie. Sicuro, nessun cambio isolamento, ma va ri-propagato ad ogni modifica.



## Sessione 02/09/2026 (fork) — parte 4: Categorie documenti + Modifica premi rapida

### ✅ Categorie documenti polizza (PolizzaDetail → DocumentiSezioneSplit)
- Visibili al cliente: Polizza, Condizioni, **Appendici** (nuova), **Libretto veicolo** (rinominata da "Libretto pagam."), Atto di vendita, **Quietanze** (documenti di pagamento rilasciati al cliente).
- NON visibili (interni): Preventivi, Appunti, **Documenti altri (foto)** (nuova).
- Multi-file per categoria: il selettore accetta più file in una volta (`multiple`), upload in ciclo. Testato: 2 appendici caricate (visibile_cliente=true).

### ✅ Modifica Premi Rapida (Polizze.jsx + PolizzaDetail.jsx)
- Dopo la creazione (snella) la polizza si apre in dettaglio con `?edit=1` → si apre automaticamente il dialog di modifica per inserire subito premi/provvigioni/veicolo.

### 🔜 Backlog rimanente
- Biblioteca Centralizzata (super-admin globale) — vedi nota parte 3.
- Promemoria Upload: rinvio automatico del link documento se il cliente non carica entro X giorni.
- Report Provvigioni: vista riepilogo totali agenzia / quote collaboratori / margine per periodo.



## Sessione 02/09/2026 (fork) — parte 3: Auto-diario, Link upload, Condizioni 2 livelli, Creazione polizza snella

### ✅ Auto-diario WhatsApp (dedup) — `whatsapp_evo.py` + `scheduler_alert.py`
- Salvataggio conversazione reso idempotente (UPSERT per `whatsapp_conv_key = instance:number`): niente doppioni.
- Job giornaliero 06:30 multi-tenant che salva/aggiorna nel diario le conversazioni collegate a un'anagrafica. Endpoint manuale `POST /api/whatsapp-evo/auto-diario/run`. Testato: 2 run → 1 sola voce.
- FIX Diario "Apri": aggiunto dialog `diario-voce-dialog` (prima non si apriva nulla).

### ✅ Link Upload Documenti — `routes/upload_link.py` + `pages/CaricaDocumento.jsx`
- `POST /api/upload-links` crea link sicuro (token) per un'anagrafica; pubblici (no auth): `GET/POST /api/public/upload/{token}`. Il file caricato dal cliente finisce negli allegati dell'anagrafica (tenant risolto dal token). Testato e2e.
- Placeholder `{link_carica_documenti}` negli alert: genera il link al volo per il cliente destinatario.
- UI: pagina pubblica `/carica/:token` + box "Richiedi documento" nel tab Documenti anagrafica (copia link + invia WhatsApp).

### ✅ Condizioni di Polizza a 2 livelli (compagnia → ramo) — `biblioteca_previdenza.py` + `BibliotecaPrevidenza.jsx`
- Nuovo campo `sottocartella` (ramo) + endpoint `GET /sottocartelle`. Upload accetta compagnia+ramo. UI condizioni: naviga compagnia → riga rami → documenti filtrati. Testato via API.

### ✅ Creazione polizza SNELLA — `Polizze.jsx`
- Il modale "Nuova polizza" ora chiede solo i dati base (numero, stato, compagnia, contraente, ramo/prodotto, effetto/scadenza) + **Frazionamento**, **Data prima quietanza**, **Collaboratore**. Premi/provvigioni/veicolo rimossi dal modale (nota informativa): si inseriscono/modificano nella scheda polizza (tab Modifica → premi header, Veicolo con TargaSearch, Provvigioni). Testato: creazione ok.

### ✅ Provvigioni terminologia (PolizzaDetail)
- Rimosso il doppione "Provv. struttura rata" (uguale a totali). Ora: **Provv. totali (agenzia)**, **Provv. collaboratore**, **Provv. margine (agenzia netto) = totali − collaboratore**. Editor: label "Provv. totali rata (agenzia)".

### ⏳ Ancora da fare (concordato)
- **Biblioteca Centralizzata (super-admin globale)**: spostare Previdenza+Schede nella console super-admin con dati GLOBALI propagati a tutte le agenzie. NON ancora implementato: richiede rendere globali (fuori tenant) le sezioni previdenza/schede toccando anche i percorsi di lettura AI (RAG, calcolo pensione) — va fatto con attenzione per non rompere l'isolamento delle condizioni (che restano per-agenzia). Da affrontare in un passo dedicato.



## Sessione 02/09/2026 (fork) — parte 2: Tasks, Duplica regole, Preset pagamento, Fix tabelle, Archivio chat, Diario

### ✅ Modulo TASK (stile Google Tasks) — `routes/tasks.py` + `pages/Tasks.jsx`
- Bacheca a colonne per operatore. **Isolamento**: di default ognuno vede SOLO le proprie attività + quelle condivise con lui; l'ADMIN ha una checkbox "Vedi tutti gli operatori" (scelta esplicita, default OFF).
- Condivisione con 1+ operatori, allegati documenti (object storage), priorità, scadenza, completamento, "Mostra completate", STAMPA (window.print con CSS print-friendly).
- Endpoint `/api/tasks` (GET con `?tutti=true` solo admin), POST/PUT/DELETE, `/toggle`, `/allegati` (upload/download/delete), `/operatori`. Collection `tasks` tenant-scoped.
- Rotta `/tasks` + voce menu "Attività (Tasks)" (sezione Strumenti). Verificato e2e (iter 64/65).

### ✅ Alert & Automazioni: Duplica + Preset pagamento
- `POST /api/alert-rules/{id}/duplica`: copia una regola (attivo=false, "(copia)") per modificarla senza rifarla. Pulsante "Duplica" in UI.
- Nuovi preset evento `titolo.incassato`: "Ringraziamento pagamento polizza" e "Questionario di soddisfazione". Dispatch `titolo.incassato` cablato nell'endpoint incasso (`server.py`). Quando il cliente paga parte il messaggio (sul canale scelto in anagrafica).
- Chiarito: l'esecutore avvisi programmati (parte 1) È la parte automatica di Alert & Automazioni (nessun doppione); la card orario vive in /alert.

### ✅ FIX BUG TABELLE (colonne congelate sovrapposte) — `index.css`
- Le colonne sticky (`.freeze-1/2/3`) avevano solo `max-width` → larghezza reale non coincideva con gli offset `left` → sovrapposizione con la colonna adiacente (illeggibile). Ora larghezza FISSA (`width`+`min-width`+`max-width` = var --cN-w), come già faceva `freeze-5`. Verificato su Contabilità con 500+ movimenti (desktop+tablet, scroll orizzontale): nessuna sovrapposizione. Vale per TUTTE le tabelle del programma.

### ✅ Archivio chat WhatsApp — `whatsapp_evo.py` + `Chat.jsx`
- Pulsante "Archivia/Ripristina" sulla conversazione + toggle "Archiviate" nella lista (non intasa le conversazioni in arrivo). Registra e mostra il TAG "Archiviata da {nome}" (chi ha archiviato). Backend `meta` salva `archived_by_name`.

### ✅ FIX Diario "Apri" — `AnagraficaDetail.jsx`
- Cliccando "👁 Apri" su una voce di diario (es. conversazione salvata) lo stato `viewVoce` veniva impostato ma NESSUN dialog lo renderizzava → non si apriva nulla. Aggiunto il dialog `diario-voce-dialog` che mostra il contenuto completo. Verificato e2e.

### ✅ Tag anagrafiche + Biblioteca visibilità (parte 1, già fatte)

### 🔜 Backlog concordato (da discutere al "punto della situazione")
- **Auto-salvataggio conversazione WhatsApp nel diario cliente** (con dedup per evitare doppioni). Oggi è manuale ("Salva nel diario").
- **Link pubblico upload documenti**: quando un alert chiede al cliente un documento mancante/scaduto (libretto ecc.), il cliente lo allega via link sicuro e lo ritroviamo nel gestionale sul cliente/polizza.
- **Biblioteca super-admin globale** (Previdenza + Schede propagate a tutte le agenzie; dati oggi tenant-scoped).
- **Condizioni di Polizza per compagnia → ramo** (navigazione a cartelle a due livelli).



## Sessione 02/09/2026 (fork) — Avvisi programmati + Import Excel estratto conto + Tag KPI + Biblioteca visibilità

### ✅ P0 — Esecutore AVVISI PROGRAMMATI (schedule/soglia) — nuovo `scheduler_alert.py`
- Prima le regole `tipo=schedule/soglia` (compleanno, polizza scaduta 0/5/10/14/15gg, polizza in scadenza, titolo scaduto oltre soglia) NON venivano mai eseguite: mancava il loop giornaliero.
- Nuovo tick ogni 10 min multi-tenant: per ogni tenant legge orario configurabile (`azienda_config.alert_scheduler_hour/minute/attivo`, default 08:00) e, all'ora impostata, esegue le regole (una sola volta al giorno via `alert_scheduler_state`).
- **Canale in base alla scelta del cliente in anagrafica**: `alert_dispatcher._dest_cliente` espone `canali_cliente` (da flag `canale_email/whatsapp/sms`); `dispatch_rule` filtra i canali per il destinatario cliente (inapp sempre).
- Rotte: `GET/PUT /api/alert-scheduler/config` (orario), `POST /api/alert-rules/{id}/run-now` (esecuzione immediata).
- Frontend `Alert.jsx`: card "Avvisi programmati" con ora:minuti + toggle attivo + Salva; pulsante "Esegui ora" per regole schedule/soglia.
- **Testato e2e** sull'agenzia TEST: polizza scaduta da 5gg → regola trova 1 entità, canale email ESCLUSO (cliente ha scelto solo WhatsApp), inapp ok.

### ✅ P0 — Import Massivo: Excel ESTRATTI CONTO COMPAGNIA → MovimentoContabile
- `_read_df` ora rileva la riga di intestazione reale saltando le righe di preambolo (Excel export con 6 righe vuote). Vale per CSV ed Excel.
- Nuovi campi movimento: `compagnia_nome` (Mandato), `numero_estratto`, `data_estratto`. Entity detection → movimento.
- Ramo movimento: estratto conto compagnia = VERSAMENTO → tipo `uscita`, categoria `pagamento_compagnia`, descrizione "Versamento compagnia — {mandato} · Estratto n. {n}", compagnia_id risolto.
- **BUG FIX**: importo con separatore decimale "." (2897.03) veniva moltiplicato x100 → aggiunto `importo` a `_NUM_FIELDS` (usa `_to_float`).
- **Testato e2e**: 596 movimenti importati, 0 errori, importi corretti (2897.03, 317.71…).

### ✅ Provvigioni su premio netto (Librerie → Sistema provvigionale)
- Input `% premio netto` già presente nel form; aggiunta colonna "% Netto" nella lista + default. Logica backend `_calcola_provvigione` già usa `percentuale_su_premio_netto` + piramide (100€→50%→10%).

### ✅ Tag anagrafiche: suggerimento canonico + KPI robuste
- `GET /anagrafiche/tags` include sempre i tag canonici `condominio/parrocchia/azienda` (autocomplete propone anche in agenzie nuove → niente doppioni CONDOMINI/CONDOMINIO). TagsEditor normalizza già a minuscolo.
- KPI `/anagrafiche/stats` ora confronta i tag case-insensitive. Testato: creata anagrafica CONDOMINIO → KPI condomini +1.

### ✅ Biblioteca: visibilità
- `BibliotecaPrevidenza.jsx`: tab "Biblioteca Previdenza" e "Schede di Calcolo" ora `superAdminOnly` (nascosti alle agenzie). Le agenzie vedono SOLO "Condizioni di Polizza". Default tab agenzia = condizioni.

### 🔜 Prossimi task richiesti dall'utente (da costruire)
- **Modulo TASK stile Google Tasks** (P0): bacheca per operatore (ognuno vede il suo), condivisione task con 1+ operatori, allegati documenti, STAMPA. Nuovo modulo (collection `tasks`, CRUD, sharing, object storage, print view, board UI).
- **Biblioteca super-admin globale** (P1): gestione centralizzata di Biblioteca Previdenza + Schede di Calcolo nella console super-admin con propagazione a tutte le agenzie (richiede rendere GLOBALI i dati sezione previdenza/schede, oggi tenant-scoped) + Condizioni per compagnia→ramo.



## Sessione 12/02/2026 — VERIFICA UFFICIALE PARAMETRI INPS + PIRAMIDE COMPATTA + JOB ASYNC SCHEDE + IMAP AUTO-ALLEGA

### 🔴 P0 — Parametri INPS 2025-2026 VERIFICATI E CORRETTI su fonti ufficiali
**Discrepanze critiche rilevate e sistemate in `/app/backend/inps_calculator.py`:**
- **Coefficienti di trasformazione**: erano OBSOLETI (biennio 2023-2024). Aggiornati con DM 20/11/2024 (biennio 2025-2026, in vigore fino al 31/12/2026). Esempi: 57→4,204%; 67→5,608%; 71→6,510%.
- **Tassi di rivalutazione montante**: 12 di 16 anni erano ERRATI o con segno invertito. Aggiornati con Note ISTAT ufficiali (ministero lavoro). Esempi corretti: 2021=-0,02%, 2022=+0,997%, 2023=+2,31%, 2025=+4,04%.
- **Invalidità civile 2026**: aggiornato da 333,33 (2025) → 340,71 €/mese.
- **Aggiunti**: `trattamento_minimo_2026` (611,85€), Tabella F L.335/1995 (riduzioni reversibilità 0/25/40/50%), aliquote contributive 2026 (dipendenti 33%, gestione separata 26,07%, artigiani 24%, commercianti 24,48%), funzione `riduzione_reversibilita_per_reddito` con eccezione figli minori (Corte Cost. 162/2022).
- **Test pytest**: `/app/backend/tests/test_inps_calculator_v2.py` — 26/26 PASS su tutti i parametri ufficiali.
- **Fonte AI**: `_crm_params_summary()` in biblioteca_previdenza.py aggiornato per riportare all'AI i nuovi parametri e la data di verifica.

### 🔴 P0 — Piramide delle Coperture: fix UX + layout stampabile A4
- **Bug fix**: pulsante "+", input reddito, pallini stato ora funzionano in modalità agenzia (canEdit propagato correttamente).
- **🐛 BUG CRITICO risolto (fix successivo)**: i cunei laterali (INVESTIMENTO/RISPARMIO/PROTEZIONE), pur avendo `clip-path` che li rende visualmente triangolari, geometricamente sono div rettangolari che coprivano metà destra del triangolo — intercettavano tutti i click a destra (pallini, input, tasto +). Aggiunto `pointer-events: none` ai wedge (decorativi puri).
- **🐛 BUG DEFINITIVO risolto (refactor strutturale)**: nonostante il fix wedge, il triangolo padre con `clip-path` bloccava ancora eventi mouse in alcuni casi. Ristrutturato in **4 layer**:
  1. LAYER 1 (bg triangolo bianco clippato) — `pointer-events: none` — solo `LevelBackground` (strip colorate decorative)
  2. LAYER 2 (SVG contorno) — `pointer-events: none`
  3. LAYER 3 (wedge cunei laterali) — `pointer-events: none`
  4. LAYER 4 (z-20, SENZA clip) — `LevelForeground`: input, pallini, tasto "+", pulsanti custom → click SEMPRE funzionanti indipendentemente dal clip-path
  Verificato E2E: click + → nuova voce, click pallino → cambia colore verde/giallo/rosso, input → scrive 500.000 €.
- **Sidebar dati_reddito**: spostata sopra il triangolo in griglia orizzontale 4 colonne (era absolute overlay sinistro, occupava spazio triangolo).
- **Cunei laterali**: font ridotto a 9px, padding minimizzato.
- **Auto-populate GET piramide-v2**: se `dati_reddito` è vuoto, backend lo popola da `reddito_annuo_lordo` anagrafica + `estratti_conto_inps` presenti.
- **Nuovo endpoint `POST /piramide-v2/prepopola`**: calcola valori suggeriti da estratto INPS/reddito (reddito_invalidita_66_99=50%, reddito_inabilita_100=80%, reddito_superstiti=60%). Bottone verde "⚡ Prepopola dati" nella sidebar della piramide.

### 🔴 P0 — Schede di Calcolo AI: fix JSON parse + BACKGROUND JOB
- **Fix errore `Expecting value: line 1 column 1`**: nuova funzione `_parse_json_ai()` con multiple fallback (rimuove markdown fence ```json, estrae il primo blocco `{…}` valido, fallback a `_ai_raw_unparsed`).
- **Spostato in background job** (`biblioteca_jobs` collection già esistente): `POST /schede-calcolo/genera` ora ritorna immediatamente `{job_id}` — il frontend polla `GET /jobs/{jid}` ogni 2s fino a `stato=done`. Elimina timeout del proxy sulle chiamate AI (Claude ~90-110s reali).
- **Confronto AI schede annuali** invariato: `_confronto_scheda` distingue vere modifiche normative da riformulazioni testuali.

### 🟡 P0 — IMAP Poller: auto-collega polizze firmate
- `_candidati_numeri_polizza`: regex robusta per estrarre numeri polizza da oggetto/body/nome file (formato compagnie italiane).
- `_auto_allega_polizza`: se mittente email = anagrafica cliente + numero polizza nel testo → copia PDF in `polizze/{id}/firmata_email_...pdf`, crea record `Allegato` (entita_tipo=polizza, fonte=email_imap, visibile_cliente=false, categoria=polizza_firmata). Match SICURO: filtra su `contraente_id` per evitare falsi positivi.
- Log nel diario cliente: `"📎 auto-collegata a polizza {numero}"`.

### 🟢 P1 — Ricerca Web Condizioni di Polizza (nuovo)
- **Endpoint `POST /biblioteca-previdenza/cerca-condizioni`** (manuale, singola compagnia): AI (Claude) suggerisce fino a 5 URL PDF condizioni, il backend scarica + valida (min 3 parole-chiave assicurative + magic-bytes PDF + dedup). AI istruito a NON inventare URL se non ne conosce di affidabili.
- **Endpoint `POST /cerca-condizioni-bulk`** (job async): itera su tutte le compagnie del CRM (solo_mancanti=true), rate-limit 1s tra chiamate LLM.
- **UI Biblioteca > tab Condizioni di Polizza**: 2 nuovi bottoni "Cerca dal Web (manuale)" + "Cerca dal Web (bulk)" con dialog + progress live del job.

### 🎯 Testing report (iter 55)
- 35/35 test PASS (100% backend); nessun issue critico; testing agent skipped frontend come richiesto.
- Cleanup dati test su Marco Rossi (testamento, voci_custom TEST) eseguito.

---

### 🎯 Piramide delle Coperture — implementata come vera piramide 3D
- **Layout definitivo**: SVG polygon triangolo esterno + bande stepped con `width%` decrescente dal basso all'apice
- Widths: `[100, 92, 82, 72, 62, 52, 40, 22]` con `min-heights` per livelli vuoti
- Titolo banda + sfondo colorato + voci con input + pallino stato
- Zone label DX (Investimento/Risparmio/Protezione Patrimonio/Protezione Reddito) come piramide di gradini dentro il container
- Formato numeri: `1.000.000 €` (toLocaleString it-IT)
- Header con solo logo agenzia (rimosso cerchio Futuro Senza Sorprese)
- Legenda 🟢🟡🔴 + Footer Testamento + 4 Eredi legittimi
- Componente unico riusabile `PiramidePrivati.jsx` (editabile in agenzia + read-only nel portale cliente)

### ✅ Verificato end-to-end
Screenshot cliente Jacopo: piramide renderizzata perfettamente con 8 livelli, contorno diagonale visibile, tutti i testi leggibili, zone label allineate.

## 🎯 TASK PROSSIMA SESSIONE (richiesti da utente)

### 1. CTA "Analisi Personalizzata" nel portale cliente
- Sezione dedicata in `PortaleCliente.jsx` (nuovo tab o inline nella piramide)
- Testo motivazionale: "Vuoi un'analisi personalizzata? Contattaci"
- **Upload PDF Estratto Conto Contributivo** (INPS) direttamente dall'app cliente
  - Endpoint POST già esistente in software agenzia (Archivio INPS)
  - Aggiungere l'accesso client-side + salvare `owner_type=cliente`
- **Video motivazionale**: 
  - Nuovo campo `agenzia_config.video_analisi_url` (upload MP4 o URL YouTube)
  - Player embed nella sezione CTA lato cliente
  - Pannello agenzia per caricare/aggiornare il video

### 2. Sezione "Estratti INPS caricati dai clienti"
- Nel software agenzia in `AnalisiClienteTab` → Archivio Estratto Conto INPS
- Mostrare badge "caricato dal cliente" per PDF caricati via portale
- Notifica dashboard quando un cliente carica un nuovo estratto

### 3. Toggle Notifiche Piramide Mensili (Impostazioni)
- Aggiungere in `Impostazioni.jsx` un pannello "Notifiche automatiche clienti"
- Toggle ON/OFF: "Invia mensilmente al cliente riepilogo copertura"
- Se ON: cron job mensile invia email con "La tua protezione è al X%" + link portale
- Salvato in `agenzia_config.notifiche_piramide_attive`

### 4. Piramide Aziende
- Variante per `Anagrafica.tipo == "persona_giuridica"`
- 7-8 livelli: RC veicoli/terzi/dipendenti/prodotti/ambientale/amministratori/datoriale → Uomini chiave → Liquidità+TFM → Patrimonio netto
- Nuovo componente `PiramideAziende.jsx` gemello a `PiramidePrivati.jsx`

### 5. PDF Export Piramide
- Endpoint `/anagrafiche/{aid}/analisi/piramide-v2/pdf` con weasyprint
- Layout identico allo screenshot Schiantarelli originale
- QR code sul PDF che apre il portale cliente sulla piramide interattiva
- Bottone "Stampa" e "Invia via email" in AnalisiClienteTab

## Sessione 11/02/2026 (fork) — Import fixes + Piramide preparazione

### 🎯 Piramide delle Coperture (schema Schiantarelli) — implementata pixel-perfect
- **Componente riusabile** `/app/frontend/src/components/PiramidePrivati.jsx` (~400 righe)
  - 8 bande dal basso all'apice: Invalidità → Premorienza → Danni Ad Altri → Perdita Beni → Liquidità → Cassa Lievi → Cassa Grandi → Crescita Capitale
  - Header logo agenzia + "Futuro Senza Sorprese"
  - Legenda 🟢 ADEGUATO / 🟡 NON ADEGUATO / 🔴 ASSENTE
  - Sidebar sinistra con 7 campi dati reddito editabili
  - Footer: Testamento (Sì/No) + 4 caselle Eredi legittimi
  - Modalità editabile (agenzia) o read-only (cliente) via prop `onSave`
  - CTA "richiedi preventivo" sui pallini rossi/gialli
- **Backend** `server.py`:
  - `GET /api/anagrafiche/{aid}/analisi/piramide-v2` — ritorna voci auto-popolate + dati salvati
  - `PUT /api/anagrafiche/{aid}/analisi/piramide-v2` — salva reddito/testamento/eredi/override
  - Helper `_piramide_v2_calcola_voci` legge polizze attive, aggrega per categoria via matcher (keyword per ramo/prodotto/garanzia), calcola stato in base a soglie configurabili (`_PIRAMIDE_V2_SOGLIE`)
- **Backend** `portale_cliente.py`:
  - `GET /api/portale/protezione` — versione read-only per il cliente (stesso schema)
  - `POST /api/portale/protezione/richiedi-preventivo` — crea richiesta admin + msg chat
- **Integrazione UI**:
  - Portale cliente: nuova sezione "La mia protezione" in `PortaleCliente.jsx` (menu con icona Shield, gradient fucsia-rosa)
  - Software agenzia: nuovo componente `PiramideCopertureNuova` nel sub-tab "Piramide" in `AnalisiClienteTab.jsx`. La piramide legacy resta accessibile in collapsible "details"
- **Test end-to-end verificato**: 
  - Portale cliente (screenshot): piramide renderizzata identica allo schema Schiantarelli con 8 livelli, 11 pallini, tutte le voci correttamente popolate
  - Backend restituisce 3 polizze RCA di Jacopo per la voce `danni_veicoli` con stato "assente" (capitale 0 in DB → pallino rosso corretto)

## Sessione 11/02/2026 (fork) — Import fixes + Piramide preparazione

### 🔴 Bug fix critici P0
1. **Duplicati in `import_mappings`** (75 righe orfane): dedup effettuato + fix preventivo nell'endpoint POST `/api/import/mappings` (delete_many extras prima dell'upsert)
2. **Import ANIA non associava operatori alle polizze/titoli**: campo giusto era `collaboratore_1` (non `cod_operatore`). Fix in `_resolve_operatore_codice` (ania_importer.py) + esteso `_processa_titoli` per estrarre collaboratore da rec40 o ereditarlo dalla polizza.
3. **Anagrafiche non ricevevano collaboratore_id**: aggiunto back-fill in `_processa_polizze` (setta collaboratore su anagrafica se assente) e nel `/api/import/mappings/apply` (back-fill retroattivo anagrafiche + titoli).
4. **AnagraficaDetail lint fix** (`InlineEditField`/`InlineChannelsField` non definiti, componenti nested instabili)
5. **PolizzaDetail bug** `ContraenteFilter is not defined` → import mancante ripristinato
6. **PolizzaDetail** tab default = `garanzie` (per polizze non-RCA) + totale colonna Massimali/Capitali rimosso + fallback intelligente per RCA (usa `pol.massimali` se garanzia vuota)

### ✅ Wizard Mapping Entità — semplificato
- **Tab Garanzia rimossa**: garanzie auto-create in libreria durante import
- **Tab Prodotto**: sceglie solo il Ramo, prodotto viene auto-creato in libreria con nome del flusso + `auto_created=True`
- **Tab Operatore/Collaboratore**: auto-crea utenti stub (attivo=false, password disabilitata) per codici mai visti; badge giallo "AUTO-CREATO" in wizard; utente completa in Librerie → Utenti
- **Auto-suggerisci Ramo** dai keyword del nome prodotto (AUTOPIU'→Auto, ABITAZIONE→Casa, VITA/TCM→Vita, IMPRESA→Multirischio, ecc.) — pre-selezione sfondo azzurro

### ✅ Bulk Rename Prodotti
- Endpoint `POST /librerie/prodotti/bulk-rename` (idempotente, dedup nome)
- Dialog in Librerie → Prodotti → pulsante "Rinomina in massa" con filtri (auto-creati / tutti) + ricerca

### ✅ Endpoint Piramide Base (portale cliente) — draft
- `GET /api/portale/protezione` con 6 livelli semplici (RCA/Casa/Vita&Salute/Impresa/Previdenza/Tutela Legale)
- `POST /api/portale/protezione/richiedi-preventivo` (crea richiesta admin + messaggio chat)
- **NB**: da riprogettare secondo il modello richiesto (vedi sotto).

## 🎯 TASK PRIORITARIO PROSSIMA SESSIONE — Piramide Coperture Ricca

### Design PIRAMIDE PRIVATI (esattamente come screenshot utente Schiantarelli)

SVG triangolo con 8 bande dal basso (rossa larga) all'alto (verde acqua stretta).
Header: Logo "Futuro Senza Sorprese" (sx) + Logo Assicurazioni Schiantarelli (dx).
Legenda: 🟢 ADEGUATO · 🟡 NON ADEGUATO · 🔴 ASSENTE.

**Zone (etichette a destra):**
- **PROTEZIONE DEL REDDITO** (livelli 1-2)
- **PROTEZIONE DEL PATRIMONIO** (livelli 3-4)
- **RISPARMIO** (livelli 5-7)
- **INVESTIMENTO** (livello 8 apice)

**Livelli dal basso all'apice:**
1. IN CASO DI INVALIDITÀ DOVUTA A (rossa): Malattia / Infortunio / Non autosufficienza
2. IN CASO DI PREMORIENZA DOVUTA A (rossa): Malattia / Infortunio
3. IN CASO DI DANNI PROVOCATI AD ALTRI, DOVUTI A (rossa): Veicoli / Immobili / Professioni / Vita privata
4. PERDITA DEI BENI DOVUTA DA Incendi/Eventi/Alluvioni/Terremoti (verde): Immobili / Aziende
5. LIQUIDITÀ GIORNALIERA – Conto Corrente (azzurro)
6. CASSA PER LE LIEVI ESIGENZE (azzurro)
7. CASSA PER LE GRANDI ESIGENZE (azzurro)
8. CRESCITA DEL CAPITALE (verde acqua apice)

Ogni voce ha: campo "sei protetto fino a €___" + pallino colore.

**Sidebar sinistra — dati editabili:**
- reddito_attuale
- estratto_conto_contributivo (Sì/No)
- reddito_lordo_annuale in caso di: invalidita_66_99, inabilita_100, superstiti, responsabilita, perdita_beni

**Footer:** testamento (Sì/No), eredi_legittimi[4]

### Auto-popolamento valori dalle polizze attive del cliente
Mappatura ramo/garanzia → livello piramide (config in Impostazioni):
- Veicoli → max(massimale_rca) polizze RCA
- Immobili → max(capitale_incendio) polizze Casa/Multirischi
- Aziende → max(capitale) polizze Impresa
- Malattia (invalidità/premorienza) → polizze Vita/Infortuni/Salute
- Ecc.

Regole colore pallino (soglie in Impostazioni):
- 🔴 ASSENTE: nessuna polizza copre
- 🟡 NON ADEGUATO: capitale < soglia_minima (es. RCA < €6M)
- 🟢 ADEGUATO: capitale ≥ soglia_ottimale

### Design PIRAMIDE AZIENDE (per persona_giuridica) — da confermare
Struttura base (7-8 livelli): RC veicoli/terzi/dipendenti/prodotti/ambientale/amministratori/datoriale → Guasti/Merci/Crediti/Cyber/Tutela legale → Uomini chiave → Liquidità+TFM → Patrimonio netto (apice)

### Implementazione stimata (~6h)

**Backend (2h):**
1. Model `AnalisiCliente.piramide_v2 = {tipo, dati_reddito, testamento, eredi_legittimi, livelli:[{id,nome,voci:[{label,capitale_attuale,stato}]}]}`
2. `POST /anagrafiche/{aid}/analisi/piramide-v2/auto-popola` — legge polizze attive, aggrega per categoria, calcola stato colore
3. `GET /portale/piramide` — versione read-only
4. `POST /portale/piramide/richiedi-preventivo` (adatta esistente)
5. `PUT /impostazioni/piramide/soglie` — admin config colori

**Frontend Agenzia (2h):**
- Nuovo `PiramideRicca.jsx` con SVG pixel-perfect
- Editing sidebar + footer
- Sub-tab Privato/Aziendale (auto in base a ana.tipo)
- Retrocompatibilità con `PiramideTab` esistente in AnalisiClienteTab

**Frontend Portale (1.5h):**
- Sezione "La mia protezione" (sostituisce endpoint semplice appena creato)
- SVG identica al software agenzia (read-only)
- CTA "Richiedi preventivo" per righe rosse/gialle

**PDF Export (0.5h):** endpoint `/anagrafiche/{aid}/analisi/piramide-v2/pdf` identico allo screenshot

## Sessione 11/02/2026 — Portale Cliente completato + 4 punti finali utente (iter_51: 18/18 PASS)

### Cosa è stato costruito/testato
1. **Notifiche SMTP + WhatsApp — auto-collegate alle config esistenti** (`notification_helpers.py`)
   - `send_email` usa `db.azienda_config.smtp_*` (già configurato: Gmail assicurazioni@schiantarelli.it)
   - `send_whatsapp_message` delega a `routes.whatsapp_evo.send_text_via_evolution` (istanza di default letta da `azienda_config.notifica_scadenze_whatsapp_instance = "agenzia-jacopoooo"`)
   - **Verificato end-to-end**: `invia-credenziali-portale` per Marco Rossi ritorna `email_inviata:true, whatsapp_inviato:true`
   - Fix bug critico: server.py chiamava `send_email`/`send_whatsapp_message` che NON esistevano
2. **Widget Dashboard "Richieste dal Portale Cliente"** (violet, primo task) → link `/richieste-cliente`, count = `db.richieste_cliente.count_documents({stato:'da_verificare'})`
3. **Subdomain routing** (`PortaleSubdomainRedirect` in App.js): hostname `portale.` / `clienti.` / `portal.` o `REACT_APP_PORTALE_HOSTS` → auto-redirect a `/portale`
4. **Template Welcome + Chat bidirezionale Portale ↔ Agenzia**
   - Preset `welcome_portale` in catalogo Alert & Automazioni (personalizzabile)
   - `invia-credenziali-portale` carica template da `db.alert_rules` con substitution `{nome}{link}{email}{tipo_credenziale}{password}`
   - Chat: collection `db.chat_portale`, endpoint cliente `/api/portale/chat/messaggi`, admin `/api/chat-portale/{clienti,{aid}/messaggi,unread}`
   - UI: nuovo tab "Portale Clienti" in `Chat.jsx` + sezione "Chat con l'agenzia" in `PortaleCliente.jsx`

### Test iter_51: 18/18 backend pytest + tutti i flow frontend verificati
Credenziali test: `marco.rossi@demo.it` / `RSSMRC75H10F205X` (CF) — anagrafica `93b73085-100f-4c78-883a-e6cefea49c72`



## Visione
CRM completo per agenzie assicurative italiane multi-tenant: anagrafiche, polizze, titoli,
Prima Nota/Brogliaccio con regole contabili rigorose, AI Copilot (Claude), OCR Gemini,
OpenAPI.it, controllo di gestione (Cervello).

## Stack
React (Shadcn) + FastAPI + MongoDB. Multi-tenant via agenzia_tenant_id (ContextVar).

## Sessione 04/08 — Completato e TESTATO (iter_39 + iter_40, tutti PASS)

### Migrazione Tipi Pagamento (iter_39: 11/11 PASS)
- Movimenti CONTANTI BPER (81) + BONIFICO (41) + PayPal (1) → conto BPER Sondrio; dup eliminati.
- Tab Librerie "Conti / Banche" → conti_cassa; "Tipi pagamento" RIPRISTINATO su richiesta utente
  (etichette combinate modalità+conto es. CONTANTI BPER SONDRIO, 19 voci, colonna conto_nome).
- `shared.resolve_conto_cassa`: nome conto → label tipi_pagamento → mezzi → fallback.
- Nuovi tenant: seed 4 conti default (super_admin.create_agenzia).

### Fix regole contabili Brogliaccio (verificati)
- POST/PUT /contabilita/movimenti risolve conto_cassa_id dal mezzo_pagamento (bug "saldo non si muove").
- BrogliaccioTab + KpiBar si ricaricano dopo registrazione (refreshTick in Contabilita.jsx).
- KPI prima_nota (routes/kpi.py): collezione movimenti + campo data_movimento (era rotto, sempre 0).
- Versamento compagnia (pagamento_compagnia): colonna SALDO -importo + RIMESSE + banca.
- Ritenuta compagnia: NON è spesa → solo SALDO -importo, nessun cash flow; anche in
  _compute_saldi_compagnie (campo ritenute) e KPI cumulativi (cum_ritenute_comp).
- Rappel: NON in Provvigioni → solo colonna RAPPEL, saldo -importo (entrambi i segni);
  KPI: cum_rappel separato, saldo_cassa -= rappel.
- Cleanup anticipi orfani: incassa_titolo elimina righe categoria 'anticipo' del titolo
  (skip giornate chiuse). Sanati 15 movimenti storici.
- POST /polizze fix premio_totale → premio_lordo.

### Mini Bilancio Periodico (iter_40: 12/12 PASS, frontend 100%)
- Tab Cervello "Mini Bilancio" (`MiniBilancioTab.jsx`): CE Ricavi/Costi riclassificati
  automaticamente dalla Prima Nota + SP (saldi conti real-time, debiti v/compagnia, ritenute erario).
- Filtri: Oggi/Mese/Trimestre/Anno/Custom. Drill-down per voce (righe di Prima Nota). Export PDF + Excel.
- Backend: routes/cervello.py `_mb_classify`/`_mb_compute`, GET /cervello/mini-bilancio,
  /dettaglio?key=, /export?formato=pdf|xlsx.
- Voci auto: Provvigioni Attive, Rappel, Storni Ricavi (ricavi); Storni/Rivalse, Provvigioni
  Passive, Spese Varie (costi). Ritenute compagnia ESCLUSE dal CE (partita di giro).
- Libreria "Voci di bilancio" (voci_bilancio, seed 14 voci) + campo voce_bilancio_id nel
  Nuovo movimento (mov-voce-bilancio-select).

### AZZERAMENTO CONTEGGI (richiesto dall'utente per prove — 04/08 17:15)
- ELIMINATI: tutti i movimenti (230), chiusure giornaliere (6), rappel (13).
- AZZERATI: saldo_iniziale di tutti i conti; 444 titoli incassati → da_incassare; 52 coperture reset.
- BACKUP COMPLETO: /app/memory/backups/reset_20260804/*.json (movimenti, chiusure_giorno,
  rappel, titoli, conti_cassa). Per ripristino: reinserire i JSON nelle collezioni.
- Verificato: KPI, liquidità, saldi compagnie, estratti conto, mini-bilancio tutti = 0.

## PROSSIMO TASK (P0) — WhatsApp via Evolution API
Collegare WhatsApp a: Alert & Automazioni + Avvisi di Scadenza.
IN ATTESA dall'utente: URL server Evolution API, API Key globale, nome istanza.
Usare integration_expert prima di implementare.

## Backlog P1
- Widget Documenti Mancanti: bottone Allega inline + note sollecito + filtro collaboratori.
- RCA sostituzione: stessa targa eredita libretto | targa diversa richiede libretto+atto vendita.
- Modulo Asset/Patrimonio Cliente: mappa Leaflet + geocoding + PDF.
- Avatar auto-crop bypass su upload da "Sostituisci Documento".
- Categorie setup_iniziale_* nel Literal MovimentoCategoria (db_models.py).
- Saldi live accanto ai conti nel tab Conti/Banche.

## Backlog P2/P3
- Google Drive sync PDF per tenant.
- Refactor server.py (>10.900 righe) in router modulari.

## Regole critiche
- PAGAMENTO IN DIREZIONE: is_direzione=True → NESSUN cash flow su banche (conto_cassa_id=None).
- Non alterare _RESET_CUSTODE_PASSWORD in routes/super_admin.py.
- Rispondere SEMPRE in italiano.

## Credenziali test
- Admin: admin@assicura.it / Admin123! — Demo tenant: jacopo@admin.it / Admin123!

## 🆕 Sessione 05/08/2026 — Integrazione Modelli + Fix Cassa Sospesi

### ✅ Completato
- **Gestione Modelli ↔ Alert/Automazioni**: `AlertRule.template_modello_id` (backend `alert_models.py`, `routes/alert.py`, `alert_dispatcher.py`) + selettore in `Alert.jsx` che disabilita i template inline quando è selezionato un modello dalla libreria.
- **Gestione Modelli ↔ Avvisi bulk WhatsApp**: `POST /api/avvisi/whatsapp-invia-bulk-titoli` accetta `modello_id` opzionale; UI `BulkAvvisoDialog` con select modelli WhatsApp + preselezione default.
- **Anteprima live**: nuovo endpoint `POST /api/librerie/modelli/preview` (render placeholder con dati fittizi: Mario Rossi, POL-2026-000123). Pannello anteprima live nel `ModelloFormDialog` (Librerie) con toggle.
- **Logo agenzia nei PDF/Word**: helper `_load_logo_bytes(azienda_config)` supporta `logo_storage_path` (file), `logo_url` (data-URL o http). PDF con intestazione a bande (logo + ragione sociale + contatti). DOCX con logo in alto.
- **Numero WhatsApp normalizzato**: `send_text_via_evolution` aggiunge automaticamente prefisso `39` se il numero ha 10 cifre e inizia con `3` (cellulari italiani).
- **TEST WhatsApp REALE inviato** al `+39 346 570 8351` via istanza `agenzia-jacopoooo` — 2 messaggi consegnati con successo (uno con prefisso, uno con normalizzazione).
- **Backend testing_agent**: 18/18 PASS (iter 42).

### 🔴 FIX critico Prima Nota — Cassa contanti con sospesi
- **Bug**: per movimento `incasso_premio` con `quota_credito > 0` (sospeso), la colonna Cassa Contanti mostrava l'importo intero (es. 300€) anziché il netto realmente incassato (280€).
- **Fix** in `_compute_brogliaccio` (server.py):
  - Per movimenti `incasso_premio` in entrata: `cash_reale = importo - quota_credito` prima di aggiornare `per_conto`/`per_conto_tot`.
  - Riepilogo conti cassa: `imp_precedente` ora sottrae `sum(quota_credito)` dei movimenti storici incasso_premio (aggregation MongoDB con `$cond`).
- **Verificato** sullo screenshot: Rossi Marco 300€ → Cassa 280€, Sospesi 20€. Totale giornata Cassa -840€ (era -820€).

### 📌 Prossimi task backlog
- P1: Avatar auto-crop bypass su upload alternativi (routes/documenti_inbox.py)
- P1: `setup_iniziale_*` in `MovimentoCategoria` (db_models.py) per Setup Iniziale
- P1: RCA sostituzione logica (extras_p1p2.py)
- P1: Widget Documenti Mancanti — inline attach + filtro collaboratori
- P1: Modulo Asset/Patrimonio (Leaflet + PDF)
- P2: Google Drive integration
- P3: Refactor server.py (>11k righe → routers modulari)


---

## Iterazione 48 (Feb 2026) — Carichi Mensili smart + Import multi-sezione + Cloud Storage

### ✅ P0 Carichi Mensili — Celle dinamiche + Deduzione AI variazioni
- **Frontend** (`CarichiMensili.jsx`): `TitoloRow` refactorato con dizionario `CELL_RENDERERS`. Le celle ora seguono l'ordine di `orderedColumns` (drag&drop delle colonne funzionante).
- **Backend** (`carichi_mensili.py`): logica di deduzione **deterministica** basata su dati CRM. Nuovi campi risposta per ogni riga:
  - `variazione_badge`: "🔄 Sostituita", "🛑 Disdettata", "⏸ Sospesa" oltre a Aumento/Riduzione/Nuova
  - `variazione_dettaglio`: spiegazione (es. "Sostituita da polizza XYZ effetto 2026-03-01")
  - `note_carico`: preserva manuale + appende deduzione automatica prefissata da 🤖
  - `note_storiche`: nomi dei collaboratori storici dai `provvigioni_operatori`
  - `servizio_sanitario`: da `polizza.premio_ssn`
  - `provvigioni_collab`: somma quote destinate agli operatori
  - `polizza_stato`, `motivo_mancanza` dedotto

### ✅ Import Excel/CSV multi-sezione
- Nuovi router `routes/import_polizze.py` e `routes/import_sinistri.py` con:
  - `POST /api/import/{polizze|sinistri}/preview` (auto-mapping degli header con similarity ≥0.6)
  - `POST /api/import/{polizze|sinistri}/execute` (policy skip/overwrite/create_only)
  - Risoluzione automatica di `contraente_id` (via CF/P.IVA), `compagnia_id`, `polizza_id`
  - Default intelligente: se manca la scadenza, calcola +1 anno dall'effetto
- Nuovo componente frontend `ImportExcelDialog.jsx` riusabile (wizard 3 step: upload → mapping → risultato)
- Pulsanti "Importa Excel/CSV" aggiunti in `/anagrafiche`, `/polizze`, `/sinistri`
- Testato con auto-mapping al 100% di confidence su header italiani standard

### ✅ Cloud Storage: Google Drive + Microsoft OneDrive
- Nuovo router `routes/cloud_storage.py` con OAuth 2.0 authorization code flow:
  - `GET /api/librerie/cloud-storage/config-status`
  - `GET /api/librerie/cloud-storage/oauth-url?provider=...`
  - `GET /api/librerie/cloud-storage/callback` (redirect al frontend)
  - `GET /api/librerie/cloud-storage/status`
  - `GET /api/librerie/cloud-storage/folders?provider=...&parent_id=...`
  - `POST /api/librerie/cloud-storage/set-folder`
  - `POST /api/librerie/cloud-storage/upload` (multipart Google Drive, upload session OneDrive per file >4MB)
  - `DELETE /api/librerie/cloud-storage/disconnect`
- **Sicurezza multi-tenant**: refresh token cifrati con Fernet (AES-128), isolamento per `tenant_id` in tutte le query.
- Nuova sezione **"Cloud Storage (Drive/OneDrive)"** in `/librerie` con:
  - Card Google Drive e Microsoft OneDrive
  - Folder picker (breadcrumb-based navigation)
  - Setup instructions per admin (Google Cloud Console + Microsoft Entra + Redirect URI)
- ENV richieste (in `backend/.env`): `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, `MS_ONEDRIVE_CLIENT_ID`, `MS_ONEDRIVE_CLIENT_SECRET`, `CLOUD_STORAGE_ENCRYPTION_KEY` (auto-generata), `BACKEND_PUBLIC_URL`
- **Testing**: 10/10 backend + frontend 100% (iter 48 pytest). Il flow OAuth reale sarà attivabile appena l'utente fornirà i Client ID/Secret dei provider.

### 📌 Backlog aggiornato
- P0: Attivazione reale Google Drive/OneDrive (attesa credenziali OAuth utente)
- P1: Avatar auto-crop bypass su upload alternativi (routes/documenti_inbox.py)
- P1: `setup_iniziale_*` in `MovimentoCategoria`
- P1: RCA sostituzione logica (extras_p1p2.py)
- P1: Modulo Asset/Patrimonio (Leaflet + PDF)
- P2: Sincronizzazione automatica PDF polizze → Cloud collegato
- P3: Refactor server.py (>11k righe)


---

## Iterazione 54 (Giu 2026) — Piramide VERA + pallini cliccabili + CTA Analisi Personalizzata

### ✅ Piramide Coperture — forma triangolare reale
- `PiramidePrivati.jsx` riscritto: triangolo unico 1040×800px con clip-path sul wrapper — tutto il contenuto (strip, label, input, pallini) resta SEMPRE dentro i bordi. Base larga + scroll orizzontale su mobile.
- **Logo agenzia in alto a SINISTRA** (helper `resolveLogo` gestisce path relativi/data-url/http) + box "PIRAMIDE DELLA PROTEZIONE DI: {cliente}" a destra.
- **Pallini CLICCABILI** (lato agenzia): ciclo verde → giallo → rosso → automatico. Persistiti in `piramide_v2.stato_voci` (nuovo campo su GET/PUT `/api/anagrafiche/{aid}/analisi/piramide-v2` e su `GET /api/portale/protezione`). Nel portale (read-only) il click su pallino ≠ verde invia richiesta preventivo.
- GET piramide-v2 e /portale/protezione ora ritornano `cliente_nome`.
- Fix HIGH (da testing iter 54): `eredi_legittimi` non-stringa causava crash "trim is not a function" al salvataggio → normalizzazione sia frontend (`normEredi`) sia backend (PUT converte dict→nome, scarta vuoti). Verificato via curl.

### ✅ CTA "Analisi Personalizzata" nel Portale Cliente
- Sezione "La mia protezione": card CTA sotto la piramide con:
  - **Upload PDF INPS estratto conto contributivo** → `POST /api/portale/analisi-personalizzata/upload-inps`: parsing pdfplumber+inps_calculator, archiviazione in `analisi_cliente.estratti_conto_inps` con `fonte: portale_cliente`, merge non distruttivo storico redditi/periodi, notifica in `db.richieste_cliente` (tipo `upload_estratto_inps`).
  - **Player video motivazionale**: YouTube embed (auto-convert watch→embed) o `<video>` da file MP4 caricato dall'agenzia.
  - Lista "Documenti già inviati".
- `GET /api/portale/analisi-personalizzata`: {video_url, video_file, estratti}.
- Endpoint pubblici (senza auth, per tag img/video): `GET /api/portale/public/logo` (fix logo rotto nel portale) e `GET /api/portale/public/video-analisi`.
- Badge viola **"dal portale"** sugli estratti INPS caricati dal cliente nell'Archivio INPS di `AnalisiClienteTab.jsx`.

### ✅ Pannello video in Librerie → Azienda
- Nuova sezione "Video Analisi Personalizzata (Portale Cliente)": input URL YouTube (salvato con Salva via PUT /librerie/azienda), upload MP4 max 80MB (`POST /librerie/azienda/video-analisi`), Rimuovi (`DELETE`).
- Demo attivo: video_analisi_url YouTube di test configurato.

### 🧪 Testing iter 54: backend 12/12 pytest, frontend 90%→100% dopo fix eredi. Regressione ANIA import OK (mappings senza duplicati, apply 200, /importazione senza errori JS).

### 📌 Backlog aggiornato
- P1: Piramide PDF Export pixel-perfect (weasyprint) per stampa/email
- P1: Piramide Aziende (variante persona_giuridica: RC datoriale/prodotti/ambientale, uomini chiave, patrimonio netto)
- P2: Notifica Piramide mensile via email con toggle per agenzia
- P2: Importer storico 3 CSV (Anagrafiche, Portafoglio veicoli, Prima nota) con merge intelligente
- P2: Pannello personalizzazione portale (slogan, colori)
- P0 (tech debt): Refactor server.py (>12k righe)


## Sessione 2026-06 (fork) — Fix definitivo interattività Piramide
### ✅ Piramide Privati: root cause REALE trovata e risolta
- Il problema NON era il clip-path (già sistemato): era un **reset dello stato React**. I default prop `= {}` di `PiramidePrivati.jsx` creavano una nuova referenza ad ogni render; gli `useEffect` con dipendenza sull'oggetto si ri-attivavano e azzeravano `custom`/`overrides`/`stati` subito dopo ogni modifica (il "+" aggiungeva la riga ma spariva, il testo digitato veniva cancellato, il colore tornava indietro).
- Fix: sync dalle prop solo su cambio di CONTENUTO (firma JSON.stringify come dipendenza degli effect).
- Fix secondario: `cycleStato` ora parte dallo stato attualmente visualizzato (prima il primo click su un pallino già "adeguato" non cambiava colore).
- Testato via browser automation: + aggiunge riga ✓, digitazione label/capitale/input standard ✓, ciclo pallino rosso→verde→giallo→rosso ✓, salvataggio + persistenza dopo reload ✓.

## Sessione 2026-09 (fork) — Implementato
- Fix Piramide: stato non si resetta più (useEffect firma JSON); pallino cambia colore al 1° click
- Fix crash Assistente Personale: CopilotWidget spostato dentro BrowserRouter
- NotebookLM assicurativo (/notebook-ai): notebook + fonti (upload/CRM) + chat streaming con citazioni + riassunti/FAQ/guide + Audio Overview podcast 2 voci (routes/notebooklm.py)
- Modelli Piramide (/modelli-piramide): template globali Privati/Aziende modificabili (righe custom) propagati a tutti; Aziende auto per P.IVA/persona_giuridica (routes/piramide_templates.py)
- Sistema colonne tabelle: useTableColumns + ColumnPicker (drag&drop, salvataggio per utente su DB) applicato a Polizze/Anagrafiche/Titoli/Sinistri (components/ColumnManager.jsx, routes/preferenze.py)
- Unisci doppioni anagrafiche (stesso CF/P.IVA) con riassegnazione polizze/sinistri/allegati/utenti (routes/anagrafiche.py: /anagrafiche-duplicati, /anagrafiche-unisci)
- Indici DB allo startup (indexes.py); /api/search limit default 50
- Super Admin: Domini Agenzia (sottodominio + credenziali dedicate) + console Scambi Dati con approvazione (super_admin.py, setup_scambio.py richiedi/richieste)
- Link portale personalizzato /c/{slug} formato https://{sottodominio-agenzia}.{dominio}/c/{cliente} (server.py _portale_link_per_ana, pages/PortaleLanding.jsx) + bottone copia in AnagraficaDetail
- Avatar automatico da documento identità: OpenCV face crop al caricamento OCR + batch notturno 02:30 + POST /api/avatar-batch/esegui (face_crop.py)
- Tabella Anagrafiche compattata (righe 45px, badge inline)
- Test: iteration_56.json 9/9 backend PASS + frontend OK; avatar e2e verificato manualmente

## Backlog (scelte utente già confermate)
- P0: Copilot ibrido (Haiku semplici/Sonnet complesse) + streaming SSE + query DB parallele (scelta c+d)
- P1: Studio Marketing: reel slideshow MP4 (ffmpeg da installare), caroselli IG, sito web AI + ZIP export (dominio esterno), piano editoriale con calendario; fal.ai quando utente fornirà key
- P1: Confronto Preventivi (2-4+ PDF → estrazione garanzie/massimali/franchigie → tabella + giudizio AI)
- P1: Carichi Mensili YoY (validare UI), Compagnia logo (UI Librerie), Piramide PDF export (weasyprint)
- P2: Notifica piramide mensile con toggle per agenzia; doppio passaggio OCR polizze (Flash→Sonnet); split server.py (>12.9k righe)
- Immagini AI (/immagini-ai): generazione immagini marketing con Gemini Nano Banana via Emergent LLM Key; formati 1:1/9:16/16:9, stili, galleria su object storage (routes/immagini_ai.py, pages/ImmaginiAI.jsx). Testato e2e (11s/immagine)

## Sessione 2026-06 (fork 2) — Implementato
- Studio Marketing → tab Presentazioni: generazione AI (argomento o punti chiave), stile brand/sfondi AI 16:9, output PPTX editabile (python-pptx) + PDF + anteprime JPEG, slide contatti auto da azienda_config (routes/marketing_presentazioni.py, StudioMarketing.jsx PresentazioniTab). Testato e2e (iter57)
- Sfondi AI orizzontali: _genera_sfondo(orizzontale=True) in marketing_studio.py
- Fix anagrafiche: flag Preferenze canale sempre cliccabili (non più disabled senza email/cellulare); auto-flag WhatsApp al blur cellulare, Email al blur email (niente più auto-SMS); sovrascrittura anagrafica (overwrite_id) ora MERGE conservativo: mantiene dati esistenti, integra solo campi vuoti, tags in unione (routes/anagrafiche.py ~380)
- SICUREZZA CHIAVI API: chiavi firma Namirial/Twilio/Spoki/server Evolution visibili SOLO al super admin. Nuovo tab "Chiavi API" in /super-admin (GET/PUT /super-admin/chiavi-api + test-whatsapp). Redazione segreti in GET/PUT /librerie/azienda e /librerie/comunicazioni per non-super-admin (_SEGRETI_AZIENDA, _CAMPI_SOLO_SUPER_ADMIN in librerie.py). Pagina Firma Elettronica rimossa dal menu agenzia (ImpostazioniFirme.jsx eliminata), sezione Twilio rimossa da Comunicazioni, provider WhatsApp read-only per agenzia (badge wa-provider-attivo), ServerConfigCard rimossa da /whatsapp, PUT/DELETE/test /whatsapp-evo/config → 403 non-super-admin. Email SMTP/IMAP e Google Drive invariati per agenzia (scelta utente). wa.me mantenuto come fallback attivabile dal super admin per agenzie senza Evolution
- Test: iteration_57.json — backend 9/9 PASS, frontend 100%

## Sessione 2026-06 (fork continuazione) — PolizzaDetail
- Scheda "Premi" ora modificabile INLINE (nessun popup): pulsante "Modifica premi" mostra input per premio_netto/tasse/imposte/ssn/lordo/provvigioni + Salva/Annulla, resta sulla stessa scheda (PUT /polizze/{id})
- Rimossi "Frazionamento" e "Ultimo premio pagato" dalla scheda Premi (già presenti nel riquadro in alto con le date)
- Ordine tab invertito: Garanzie prima di Premi
- Garanzie → riga TOTALE: cella Provvigioni ora modificabile inline (ProvvigioniTotaleCell, PUT /polizze/{id} {provvigioni}); valore preso dal campo provvigioni della polizza
- Completato task in sospeso: uploadLibretto nella tab Veicolo (era crash "librettoUp is not defined"). Usa POST /ocr/libretto + /ocr/libretto/apply; allegato salvato con categoria "libretto_veicolo" e visibile_cliente=true (routes/ocr.py _salva_allegato_libretto)
- Bugfix: GET /polizze/{id} andava in 500 (KeyError compagnia_id) per polizze senza compagnia/contraente → ora usa .get() (server.py get_polizza ~2415)
- Bugfix: riquadro in alto mostrava "undefined" per Frazionamento nullo → ora "—"
- Verificato via screenshot su agenzia test (test@sandbox.it): modifica premi inline OK, toast "Premi aggiornati", ordine tab OK

## Sessione 2026-06 (fork continuazione, parte 2) — PolizzaDetail + Titoli + Provvigioni
- Premi: aggiunti campi Accessori (premio_accessori) e Diritti (diritti); premio_lordo AUTO = netto+tasse+imposte+ssn+accessori+diritti (readonly); rimosso campo Provvigioni dalla scheda Premi. Aggiunto premio_accessori al db_model Polizza.
- Veicolo (tab): modifica INLINE (nessun popup). Ricerca Targa con TargaSearchWithLentina; alla selezione di una targa TUTTI i campi veicolo vengono RESETtati e riempiti dai dati dell'archivio (chiavi multiple: kw/potenza_kw, cv/cv_fiscali/potenza_cv, tipo_veicolo/tipo/categoria/codice_oggetto, uso/codice_uso). Massimali con separatore migliaia it-IT.
- Veicolo archivio SYNC: nuovo endpoint PUT /veicoli/by-targa/{targa} (server.py ~6590) che aggiorna/crea il veicolo in archivio con i dati corretti dal dettaglio polizza (così una ricerca successiva non ripropone dati errati es. openapi_mock). Chiamato da saveVeicolo.
- Provvigioni (tab): pulsante Modifica per editing inline del totale (PUT /polizze provvigioni). Auto-calcolo quota collaboratore da SistemaProvvigionale VERIFICATO funzionante (es. Sara 70% → 8,53€ su 12,18€). Ripartizione: alla selezione di un collaboratore vengono proposti anche i livelli superiori (upline) dallo schema, con provvigione = % sul totale (badge 'livello superiore').
- TitoloDialog: rimossi i campi 'Data incasso' e 'Copertura fino al' (auto-generati a incasso/copertura). Tipo pagamento ereditato dal mezzo_pagamento_preferito della polizza. Fix 'Eredita da polizza': leggeva o.operatore_id ma la polizza salva o.collaboratore_id → ora legge entrambi.
- CollaboratoreInlineSelect: fix testo bianco-su-bianco nel <select> (aggiunto text-slate-800).
- Verifiche: screenshot su agenzia test (Premi lordo=128, tab order, Provvigioni edit, Veicolo inline+targa search+massimali, TitoloDialog senza campi rimossi); curl PUT /veicoli/by-targa OK; get_polizza provvigione_collaboratore OK. NOTA: autofill archivio + upline richiedono dati reali (archivio veicoli / schema con upline) presenti solo sull'agenzia principale; l'upline si attiva quando l'utente configura la 'Rete piramidale' nello schema.

## Sessione 2026-06 (fork continuazione, parte 3) — Titoli
- Primo titolo auto-precompilato: quando la polizza NON ha titoli, "+ Nuovo titolo" precompila tipo="nuova" (Polizza nuova), effetto, scadenza, importo_lordo, importo_netto, imposte, provvigioni dalla polizza (PolizzaDetail new-titolo-btn onClick). Verificato su sandbox (lordo 128, netto 100, provvigioni 50).
- Titolo auto-provvigioni: alla selezione del collaboratore nella ripartizione operatori del titolo, la quota € viene calcolata automaticamente dallo schema (percentuale_collaboratore × totale provvigioni titolo) via GET /librerie/schema-provvigionale. Rimosso il vecchio effetto che sovrascriveva f.provvigioni con la somma operatori (il totale resta indipendente, coerente col breakdown a lettura). Fix ereditarietà: legge o.collaboratore_id||o.operatore_id. Tipo pagamento ereditato dal preferito polizza.
- NON fatti (scelta utente): Report Provvigioni (NO); Storico Veicolo elenco polizze (NO, lasciata solo la segnalazione TargaConflictWidget di polizza collegata ad altra attiva).

## Sessione 2026-06 (fork continuazione, parte 4) — Import storico OWEB/Cattolica
- Ricevuto ZIP export OWEB/SHARE (compagnia CAT/Cattolica, ANIA 57): rec00/10/20/21/24/30/40/41/42/43/50/51/52/70/100/101, semicolon-separated, ~1M righe (~500MB). rec40 contiene netto_totale/tasse_totale/lordo_totale/provvigioni_totale.
- VERIFICATO: il tracciato è GIÀ pienamente supportato da ania_importer.importa_zip (endpoint POST /api/import/ania e alias /api/import/omnia). Nessuna modifica di codice necessaria.
- Test reale su agenzia sandbox: campione allineato → 5 polizze, 20 titoli con premi corretti (lordo=netto+imposte, provvigioni), anagrafiche collegate; entità non mappate tracciate (compagnia CAT, 41 prodotti, 12 collaboratori, rami). Wizard di mappatura disponibile in pagina /importazioni tab OMNIA.
- CAVEAT: file completo molto grande (~500MB); l'upload via browser potrebbe essere lento/pesante e l'endpoint è sincrono → valutare upload chunked/import in background se l'upload fallisce.

## Sessione 2026-06 (fork continuazione, parte 5) — Recupero Biblioteca Previdenza Super Admin
- PROBLEMA: dopo lo spostamento della Biblioteca Previdenza al tenant globale (__global_library__), i ~1011 PDF caricati in precedenza (sotto tenant-principale-schiantarelli) non erano più visibili nella console Super Admin (che legge solo il globale). biblioteca_previdenza è MIXED_SHARED.
- FIX (migrazione dati): spostati 1011 documenti previdenza (sezione None/previdenza) + 1 cartella custom da tenant-principale-schiantarelli → __global_library__ (sezione impostata a 'previdenza'). Le 40 "Condizioni di Polizza" restano per-agenzia (corretto). L'agenzia principale continua a vederli (MIXED legge tenant+globale).
- Consolidata categoria duplicata: 'PENSIONE INTEGRATIVE' (6) → 'PENSIONE INTEGRATIVA' (default). Totale previdenza globale: 1012.
- Discoverability: aggiunto tab "Biblioteca & Schede Calcolo" nel pannello Super Admin (SuperAdminPanel.jsx) che naviga a /super-admin/biblioteca (prima raggiungibile solo dal pulsante header). Verificato via screenshot: categorie e Schede di Calcolo tutte presenti.

- CONFERMA collegamento calcoli: verificato via API che l'agenzia principale (admin@assicura.it) legge i 1012 PDF previdenza dal globale (cartelle con conteggi corretti). Il widget "Consulto AI · Biblioteca Previdenza" nelle schermate di analisi cliente (Pensione INPS, Approfondimento Redditi, Successione, Riepilogo Pensionistico) usa questi PDF per categoria. Gestione centralizzata Super Admin → propagata a tutte le agenzie.

## Sessione 2026-06 (fork continuazione, parte 6) — Stato polizze import OWEB + protezione metodi di calcolo
- BUG stato polizze: il tracciato OWEB usa cod_stato_share con codici AT/ST/SO/SP, ma _MAP_STATO_POLIZZA in ania_importer.py mappava solo a/s/x → TUTTE le polizze importate finivano "attiva" (incl. 28k stornate). FIX: aggiunti codici at→attiva, st→annullata, so/sp→sospesa, an→annullata; inoltre se data_annullamento è valorizzata e lo stato calcolato è attiva → annullata.
- Correzione dati esistenti: l'import di questo file era già stato eseguito oggi sull'agenzia principale (49.219 polizze tutte "attiva"). Script di correzione mirata via id_polizza_exp incrociato col rec20: aggiornate 43.389 polizze → distribuzione reale annullata 28.156, sospesa 15.232, attiva 5.758. Verificate le polizze dello screenshot utente: ora "annullata".
- Protezione metodi di calcolo (richiesta utente: nessuna manomissione dalle agenzie, propagazione dal Super Admin):
  * genera_scheda (POST /schede-calcolo/genera): aggiunto _guard_libreria_globale("previdenza") → agenzia 403, super admin 200.
  * sync_drive: la sezione previdenza viene sincronizzata SOLO dal super admin (le agenzie sincronizzano solo le proprie Condizioni).
  * upload/delete/create_cartella previdenza già protetti. Docs previdenza vivono nel tenant globale (__global_library__) → un'unica copia, ogni modifica del super admin è propagata a tutte le agenzie in lettura (MIXED_SHARED).
  * Verificato via curl: agenzia upload/genera previdenza = 403; super admin = 200/consentito.

## Sessione 2026-06 (fork continuazione, parte 7) — Stato scadute, filtri conteggi, import duplicati
- Stato "scaduta": nuovo endpoint POST /polizze/ricalcola-scadute (admin) → marca 'scaduta' le polizze attive con scadenza passata (scadenza > "" e < oggi) e SENZA rinnovo attivo (nessun titolo con coperto_fino_a >= oggi). Eseguito su agenzia principale: 1746 marcate → attive 5826→4080, scadute →1747. Pulsante "Segna scadute" in Polizze.jsx (admin).
- Filtri rapidi con conteggi: nuovo endpoint GET /polizze/conteggi-stato (aggregazione per stato, rispetta visibility_filter). Chip preset in Polizze.jsx (Tutte/Attive/Scadute/Sospese/Annullate) mostrano il conteggio.
- Import duplicati: l'import ANIA/OMNIA fa già upsert (_upsert_polizza per id_polizza_exp) → i doppioni vengono SOVRASCRITTI/aggiornati, mai duplicati. Aggiunto banner nel report import (Importazione.jsx) "Doppioni rilevati e sovrascritti: N polizze e M anagrafiche già presenti aggiornate".
- Nota: endpoint statici /polizze/conteggi-stato e /polizze/ricalcola-scadute inseriti PRIMA di /polizze/{pid} per evitare cattura del path param.

## Sessione 2026-06 (fork continuazione, parte 8) — Situazione Patrimoniale + attivazione Visura/Catasto
- Fix UI Analisi Cliente (AnalisiClienteTab.jsx): barra Salva resa STICKY (top-0 z-30) + aggiunto pulsante "Salva situazione patrimoniale" in fondo alla tab Patrimonio (props save/dirty/saving a PatrimonioTab). Messaggio auto-popola veicoli ora accurato (aggiunti / già aggiornati con polizze_trovate / nessuna polizza — attenzione duplicati).
- Backend auto_popola_veicoli (server.py): ora considera anche anagrafiche duplicate con stesso codice_fiscale/partita_iva, esclude stato 'scaduta', ritorna polizze_trovate.
- Caso Schiantarelli: la polizza auto 183629579 (attiva, targa FB828CV) è intestata all'anagrafica duplicata adf21a7f (ragione_sociale, CF SCHJCP91M18I829O), diversa da quella su cui era l'utente → auto-popola non la trovava. Servirebbe merge anagrafiche duplicate (da confermare con utente).
- OpenAPI.it Visura Camerale (imprese) + Catasto: integrazione GIÀ presente (openapi_it_service.py, routes/openapi_it.py). Credenziali OAuth VALIDE (mode live, credito €99,40). MA il token per GET:imprese.openapi.it/advance e catasto → HTTP 406 "invalid scopes specified or API not enabled": i due prodotti NON sono attivati sull'account OpenAPI.it (schiantarelli.jacopo@gmail.com). AZIONE UTENTE: attivare le API "Imprese/Visura Camerale" e "Catasto" su console.openapi.com. Nessuna modifica codice necessaria; passerà da mock a live in automatico.

## Sessione 2026-06 (parte 9) — Attivazione OpenAPI.it (Catasto/Visengine)
- Il token statico "Lista Token Produzione" (6a99...) NON è un Bearer valido → API risponde 401 "Wrong Token". OPENAPI_IT_BEARER_TOKEN rimesso a "" (l'app usa OAuth client_credentials).
- OAuth client_credentials (client_id/secret già in .env) ORA ottiene token 200 per: Visengine (visengine2.altravia.com/visure,richiesta,documento) e Catasto (catasto.openapi.it/richiesta,visura_catastale). "Imprese" (imprese.openapi.it) resta 406 "API not enabled" → non attivato (ma Visengine copre CCIAA).
- MA fetch_cadastre / fetch_company nel service ricadono ancora su MOCK: i flussi LIVE async (POST richiesta → polling GET → documento) NON sono implementati davvero, restituiscono dati simulati. Da implementare: flusso Visengine (unico motore documenti CCIAA/INPS/Agenzia Entrate) create→poll→download PDF su object storage.
- Servizi attivati lato account: Visengine (Attivo), Catasto (scope selezionati). Credito €99.

## Sessione 2026-06 (parte 10) — Catasto LIVE ok, Visura Camerale da costruire con selettore
- CATASTO: FIX applicato e testato LIVE. fetch_cadastre ora legge il formato reale (data.stato="evasa", data.risultato.soggetti[].catasti[].comuni[]) invece del vecchio res.get("success"). Nuovo _normalize_cadastre_nazionale. Test: CF SCHJCP91M18I829O → TIRANO (SO) 3 fabbricati (LIVE). Endpoint POST /openapi-it/cadastre/{aid}.
- OPENAPI_IT_BEARER_TOKEN rimesso a "" (il token "Lista Produzione" 6a99.. non è un Bearer valido → "Wrong Token"). L'app usa OAuth client_credentials: token 200 per Catasto e Visengine; "imprese.openapi.it" ancora 406 "API not enabled".
- VISURA CAMERALE: da fare come richiesto dall'utente → cliccando "Camerale" mostrare SELETTORE documenti (Visura ordinaria imprese individuali / società capitali / società persone; Visura storica x3; Bilancio Aziendale; Certificato Camerale iscrizione; Certificato con vigenza; Elenco Soci Attivi) con opzione "tutti / seleziona alcuni". API = "Visure Camerali" (imprese/visurecamerali.openapi.it). RICHIEDE che l'utente ATTIVI l'API "Visure Camerali/Imprese" su console.openapi.com (ora 406). Poi implementare: lista prodotti + POST richiesta con json per tipo + polling + salvataggio PDF/dati.
- Anche i doc Visengine (Estratto Contributivo, ISEE, 730, pensioni, Visura PRA) richiedono json_visura per-prodotto (HTTP 412 "insufficient data" se mancano campi): da costruire con schema per prodotto.

## Sessione 2026-06 (parte 11) — Catasto dettaglio bloccato su endpoint
- Catasto: ricerca_nazionale LIVE OK (comune+conteggio: TIRANO 3 fabbricati). Ma il DETTAGLIO (foglio/particella/categoria/rendita) richiede un secondo endpoint non ancora individuato: provati POST /richiesta/{ricerca|ricerca_immobili|immobili|visura_catastale|ricerca_immobili_soggetto} → tutti HTTP 400 "wrong endpoint". Lo scope GET:catasto.openapi.it/visura_catastale esiste → probabile endpoint GET top-level (non sotto /richiesta) con id_soggetto/provincia. DA CONFERMARE da doc OpenAPI.it Catasto.
- Widget UI "Autocompilazione OpenAPI.it" mostra colonne foglio/particella/cat/sup/rendita → attualmente vuote perché ricerca_nazionale non le fornisce.

## Sessione 2026-06 (parte 12) — Catasto estrazione REALE + Selettore Visengine (COMPLETATO)
- CATASTO (LIVE, testato end-to-end): implementato `fetch_cadastre_detailed` in openapi_it_service.py.
  Flusso: POST /richiesta/ricerca_nazionale (id_soggetto) → POST /visura_catastale {entita:"soggetto",tipo_visura:"ordinaria",tipo_formato:"json",tipo_dettaglio:"analitica"} → polling GET /visura_catastale/{id} → download JSON strutturato → parsing immobili (foglio/particella/sub/categoria/rendita/superficie/indirizzo/comune/titolo/quota). In parallelo genera anche la visura PDF ufficiale (ordinaria) salvata negli Allegati.
  Parser `_parse_visura_json` legge VisuraSoggettoAttuale.GruppoUnitaImmobiliari[].ImmobileFabbricatiS/ImmobileTerreniS. Titolo/quota dal match CF su IntestazioneGruppo.
  Endpoint: POST /openapi-it/cadastre/{aid} (estrae + salva PDF, ritorna immobili) e POST /openapi-it/cadastre/{aid}/importa-immobili (aggiunge gli immobili selezionati a analisi_cliente.immobili, dedup foglio+particella+comune, usa `db` tenant-aware).
  UI: pulsante "Catasto" → CatastoImportDialog.jsx (selettore "tutti o alcuni") → import in Analisi Cliente > Patrimonio > Immobili.
  Test LIVE: P.IVA 12485671007 (ALTRAVIA) → 1 ufficio ROMA A/10 Fg872 Part405 rendita 2566.79, PDF salvato, import OK.
- VISENGINE / VISURE & DOCUMENTI (LIVE plumbing testato): nuovo pulsante "Visure & Doc." → VisengineDialog.jsx.
  Lista FISSA di 16 documenti (Camerali 3 + Patronato 13) con hash reali (VISENGINE_CATALOG in openapi_it_service.py).
  Flusso: step "select" (checkbox + Seleziona tutti) → step "compile" (GET /visengine/schema/{hash} carica json_struttura, campi precompilati dai dati anagrafica, input file per documenti che richiedono allegati identità/tessera/mandato) → POST /visengine/request/{aid} (crea pratica, se sincrona scarica subito il PDF in Allegati) + storico richieste con refresh (POST /visengine/refresh/{aid}/{rid}).
  Endpoint: GET /visengine/catalog, GET /visengine/schema/{hash}, POST /visengine/request/{aid}, POST /visengine/refresh/{aid}/{rid}.
  NOTA COSTI: ogni documento Visengine e ogni visura catastale è a pagamento (POST /richiesta). Il POST live è stato validato solo su error-path (HTTP 412 su dati incompleti, nessun addebito). L'invio reale di documenti Visengine NON è stato test-fired per non addebitare crediti: da testare dall'utente.
  Allegati salvati via obj_storage + modello Allegato standard (is_deleted=False) così compaiono nel tab "Altri allegati" e sono scaricabili.
- Test: testing_agent frontend 100% (iteration_68.json). Credito OpenAPI.it residuo ~€76.
- Dati di test creati nel tenant sandbox: anagrafica 931835cd-... "ALTRAVIA TEST CATASTO" (P.IVA 12485671007) con 1 immobile importato + PDF visura.

## Sessione 2026-06 (parte 13) — Camerale/Bilancio + Mappa Immobili + Riuso gratuito (COMPLETATO)
- KPI Anagrafiche (routes/anagrafiche.py /anagrafiche/stats): 'n' ora conta SOLO i contraenti distinti con almeno una polizza attiva/in_emissione (via $addToSet contraente_id); premi già solo da polizze attive. Etichetta card "tot." → "con pol." (Anagrafiche.jsx). Vale anche per KPI custom.
- CAMERALE / VISURE CAMERALI (visurecamerali.openapi.it — ATTIVO): pulsante "Camerale" apre CameraleDialog.jsx ("Dati Azienda & Bilancio").
  - Ricerca GRATUITA: GET /impresa/{cf_piva} → denominazione, comune, natura giuridica, elenco documenti richiedibili con prezzi. Endpoint: GET /openapi-it/camerale/{aid}/search.
  - Documenti ufficiali PDF (a pagamento): POST /{doc_type} → poll stato_richiesta (In ricerca→In erogazione→Dati disponibili→Visura evasa) → download /{id}/allegati → salva Allegato. Endpoint: POST /openapi-it/camerale/{aid}/documento {doc_type, anno?}. Tipi: ordinaria/storica società capitali/persone/impresa individuale, bilancio-ottico, certificato-iscrizione(-vigenza), soci-attivi.
  - RIUSO GRATUITO: prima di pagare, vc_find_existing() usa la GET gratuita /{doc_type} per trovare una richiesta già pronta della stessa azienda e la riscarica GRATIS (prezzo=0, riusato=true). Testato: 1ª soci-attivi a pagamento, 2ª riusata gratis.
- BILANCIO strutturato (company.openapi.com — ATTIVO, imprese.openapi.it invece è 406/non attivo):
  - IT-advanced: dati camerali + bilanci sintetici (anno, fatturato/turnover, patrimonio_netto, dipendenti, capitale, ecc.). Endpoint: GET /openapi-it/camerale/{aid}/bilancio.
  - IT-full: + indici (redditività roe/roi/ros/roa, liquidità, leva, kpi), amministratori (con LR), soci. Endpoint: GET /openapi-it/camerale/{aid}/bilancio?full=true.
  - Servizio: openapi_it_service.company_dati(), _normalize_company_co().
- MAPPA IMMOBILI (AnalisiClienteTab.jsx → PatrimonioTab): componente ImmobiliMap (Leaflet via CDN) mostra i pin degli immobili geolocalizzati. Pulsante "Geolocalizza immobili" → POST /openapi-it/analisi/{aid}/geocode-immobili (Nominatim, gratuito). Geocoding automatico anche all'import Catasto (con pulizia indirizzo catastale + fallback su comune). Helper: routes/openapi_it.py _clean_catasto_address(), _geocode_immobile().
- SPIEGAZIONE ENDPOINT GRATUITI (per l'utente): i GET gratuiti (0.001€, 1440/gg) o elencano/riscaricano richieste GIÀ generate (riuso senza ripagare) o fanno ricerca commerciale gratuita (visurecamerali /impresa). Non esiste modo gratuito per generare NUOVE visure catastali/camerali.
- Test: testing_agent frontend iteration_69 (Camerale dialog + mappa) 100%. Backend validato via curl (search/bilancio/documento/riuso/geocode).
- Anagrafica test società capitali: 931835cd-... (OPENAPI/ALTRAVIA P.IVA 12485671007) con 1 immobile geolocalizzato + soci-attivi PDF salvato.

## Sessione 2026-06 (parte 14) — Fix download documenti camerali + test Bilancio Ottico
- BUG FIX (openapi_it_service.vc_download): l'endpoint visurecamerali /{doc_type}/{id}/allegati NON restituisce il PDF diretto ma JSON {data:{nome:"*.zip", file:"<base64 ZIP>"}}. Ora vc_download: rileva JSON → base64-decode → estrae il primo .pdf dallo ZIP → salva il PDF corretto (con nome/content_type reali). Gestisce anche PDF diretto e ZIP senza pdf. Firma cambiata: ritorna (status, bytes, content_type, filename). Aggiornati camerale_documento e camerale_refresh.
- TEST REALE Bilancio Ottico su AUTOTRASPORTI VIVIANI SRL (P.IVA 00920050143, BIANZONE SO, SRL): PDF ufficiale 27 pagine, chiusura 31/12/2025 (Ricavi 6.444.977, perdita -8.052), salvato in Allegati e scaricabile. Riuso 2ª volta a €0 confermato.
- Nota: allegati salvati PRIMA del fix (es. soci-attivi ALTRAVIA, 1° bilancio VIVIANI) contengono il JSON grezzo (artefatti di test, non critici).

## Sessione 2026-06 (parte 15) — Predisposta API Report Aziende (api.reportaziende.it)
- Integrata "API Dettaglio Azienda" di Reportaziende.it (manuale utente v3.0). Host: api.reportaziende.it, auth Bearer OAuth oauth.openapi.it (stesso wallet). Endpoint GET /dettaglioazienda/visualizza/{CF}/{SCHEDE}. 1 credito per scheda.
- 13 schede: ANA anagrafica, 05 quadro, 10 conto economico, 20/30 SP attivo/passivo, 40 indici, 50 redditività, 60 produttività, 70 crescita, 85 soci/esponenti/CEO, 95 gruppo/holding, PROT protesti&pregiudizievoli, CR credit score&rating.
- Backend: openapi_it_service.report_azienda()/report_schede_catalog() (scope GET:api.reportaziende.it/dettaglioazienda/visualizza). Route: GET /openapi-it/report-azienda/catalog, POST /openapi-it/report-azienda/{aid} {schede:[...]}. Salva in openapi_data.report_azienda.
- Frontend: sezione "Report Azienda (schede avanzate)" dentro CameraleDialog con checkbox schede (default ANA,40,CR,PROT) + "Genera report" + renderer generico (flat=key/value, per_anno=tabella).
- STATO: il prodotto NON è attivo sul token OAuth attuale (nessuno scope reportaziende → HTTP 400 "Prodotto non attivo, attivalo su console.openapi.com"). Appena attivato, funziona senza modifiche. Response attesa: {status, cf, crediti_utilizzati, schede:{CODE:{nome,tipo,dati}}}.

## Sessione 2026-06 (parte 16) — Info Azienda + autocomplete P.IVA + visibilità tab
- VISIBILITÀ TAB (AnagraficaDetail.jsx): "Raccolta Dati", "Potenti Domande", "Analisi Cliente", "Pensione INPS" ora SOLO per persone fisiche (ana.tipo !== persona_giuridica), trigger + content. Azienda vede "🏢 Analisi Azienda" + "💼 Salute Fiscale".
- AUTOCOMPLETE NUOVO CLIENTE (Anagrafiche.jsx importaAzienda): GET /openapi-it/company?piva= ora usa company.openapi.com (IT-advanced) via svc.company_lookup() → ragione_sociale, indirizzo, comune, provincia, cap, pec, ateco, forma_giuridica, rea, cciaa, stato. (imprese.openapi.it era 406). Fallback ricerca gratuita visurecamerali.
- SCHEDA INFO AZIENDA (AnalisiAziendaTab.jsx riscritto, recharts): panoramica (rag. sociale, ATECO, indirizzo, dipendenti, forma giuridica, fatturato ultimo bilancio) + 4 sotto-tab con torte: Soci/Azionisti (quote%), Governance (torta + tabella amministratori con Rappr. legale), Forza lavoro (dipendenti/costo/trend), Commercio estero (placeholder: dati non in company.openapi.com, arriveranno con Report Aziende). Pulsante "Carica/Aggiorna dati" → POST /openapi-it/company/{aid}.
- Backend: svc.company_lookup(), svc.company_full_completo() (merge IT-full soci/governance/indici + IT-advanced ragione_sociale/indirizzo/bilanci). _normalize_company_co ora espone comune/provincia/cap. POST /company/{aid} salva dati merged in openapi_data.company; backfill ragione_sociale dall'anagrafica.
- "Analisi Azienda approfondita" = da sviluppare in seguito (contenitore esistente).
- Test: testing_agent frontend iteration_70 = 100% (Info Azienda render, visibilità tab PG/PF, autocomplete presente). Backend via curl OK.

## Sessione 2026-06 (parte 17) — Fix pulsante Estrai dati P.IVA + nota tipo azienda
- FIX (Anagrafiche.jsx form nuovo cliente): il pulsante di autocompilazione P.IVA prima era una piccola pill in alto visibile solo dopo 11 cifre → non evidente. Ora: campo P.IVA + pulsante verde "⚡ Estrai dati" sempre visibile per aziende (tipo persona_giuridica), disabilitato finché la P.IVA non ha 11 cifre, con testo di aiuto. Chiama importaAzienda() → GET /openapi-it/company (company.openapi.com).
- NOTA: AUTOTRASPORTI VIVIANI risulta "Persona fisica" perché il record è stato salvato con tipo=persona_fisica (probabile ditta individuale o import). Va corretto manualmente (modifica anagrafica → Tipo → Azienda) oppure valutare estrazione dati anche per persone fisiche con P.IVA (ditte individuali) in futuro.

## Sessione 2026-06 (parte 18) — Regola "P.IVA = persona giuridica" + campi personali nascosti
- REGOLA: ogni anagrafica con Partita IVA è persona_giuridica. Forzata in create_anagrafica e update_anagrafica (routes/anagrafiche.py). Migrazione one-time (tutti i tenant): 681 record con P.IVA convertiti a persona_giuridica (su 1934 totali con P.IVA); backfill ragione_sociale dove mancante (0 necessari). VIVIANI ora persona_giuridica.
- CAMPI PERSONALI NASCOSTI per persona_giuridica (AnagraficaDetail.jsx): vista dettaglio (Data nascita, Sesso, Comune nascita, Professione, Tipo lavoratore, Stato civile, N.figli, Figli a carico, Reddito annuo lordo, Inizio contribuzione, Settimane contributive) filtrati; form modifica: stessi campi + Tipologia lavoratore/Professione/Datore lavoro avvolti in {f.tipo!=="persona_giuridica"}.
- Pulsante "⚡ Estrai dati" ora sempre visibile per aziende accanto al campo P.IVA (disabilitato finché non 11 cifre) con testo di aiuto.

## Sessione 2026-06 (parte 19) — Salute Fiscale da OpenAPI + card OpenAPI in Analisi Azienda + Tipo/PEC
- SALUTE FISCALE da dati strutturati: nuovo POST /anagrafiche/{aid}/salute-fiscale/da-openapi (extras_p1p2.py) → usa company_full_completo (ultimo bilancio con fatturato>0) per compilare ricavi/PN/attivo/costi personale + indicatori (roe/ros da indici, leva=attivo/PN) + score rischio + cross-sell. Pulsante "⚡ Compila da OpenAPI" in SaluteFiscaleTab accanto a "Carica bilancio (OCR)". Testato: OPENAPI SPA 2025 ricavi 5.696.858, PN 1.037.925, leva 2.31.
- Card OpenApiActions SPOSTATA in Analisi Azienda (AnalisiAziendaTab, in cima) per le aziende; nascosta nel tab dati per persona_giuridica.
- Form modifica anagrafica: aggiunto selettore "Tipo anagrafica" (fisica/giuridica) + campo PEC.
- I PDF scaricati (bilancio ottico, visure) restano salvati in allegati con categoria (visura_camerale/bilancio/visura_catastale), visibili in "Altri allegati" con data e multipli file per categoria.
- PENDING (agentic edits da fare): campi Amministratore + Referente azienda (con email/cellulare, autocompilati da import); mostrare solo tab attive; categoria "bilancio" per bilancio-ottico.

## Sessione 2026-09 (parte 20) — Import OMNIA completato + Unisci doppioni Rami
- IMPORT OMNIA (tenant 31b4950e, job b78fb2e5) COMPLETATO 09/09 21:10, 0 errori: 9.895 anagrafiche (+34 agg.), 49.039 polizze (6.802 attive), 187.953 titoli (176.145 incassati / 11.808 da incassare), 7.718 sinistri, 5 compagnie, 342 prodotti, 10 collaboratori (19.659 polizze collegate).
- PENDING: import CSV "Metodo di Pagamento" per popolare mezzo_pagamento / data_copertura sui titoli (endpoint async già pronto: POST /api/import-massivo/metodo-pagamento).
- NUOVA FEATURE "Unisci doppioni" (solo libreria Rami, richiesta utente):
  - Backend routes/librerie.py: POST /api/librerie/rami/merge-preview (anteprima conteggi riferimenti: polizze, sinistri, prodotti — totale su unione valori per evitare doppi conteggi) e POST /api/librerie/rami/merge (admin): riassegna ramo dei doc al codice master e ARCHIVIA i doppioni (attivo=false + unito_in_ramo_id / unito_in_codice / unito_at), log_attivita "merge".
  - Match riferimenti su {codice, nome} del doppione; le collezioni polizze/sinistri/prodotti sono tenant-scoped (wrapper DB) → riassegnazione limitata all'agenzia corrente. NB: la collezione `rami` è globale/condivisa, l'archiviazione ha effetto su tutti i tenant.
  - Frontend Librerie.jsx: pulsante "Unisci doppioni" nel tab Rami → MergeRamiDialog con rilevamento automatico gruppi (nome/codice normalizzati), scelta master (radio) + doppioni (checkbox), anteprima conteggi, conferma. Tabella Rami ora mostra colonna Stato (attivo / archiviato / "unito → CODICE").
  - Testato: curl (create/preview/merge/archiviazione/errori + cleanup) e screenshot UI con gruppo RC AUTO (38 polizze).


## Sessione 2026-09-10 — Metodo pagamento: fix match numero polizza + dedup tendine Ramo
- IMPORT metodo pagamento (job 2fa1c316) terminato: 16.973 polizze nel file, 7.405 aggiornate, 6.204 titoli, ma **9.568 polizze "non trovate"**.
- ROOT CAUSE: `_process_metodo_pagamento` cercava `numero_polizza` esatto (`58531300240`) mentre le polizze OMNIA sono zero-padded a 14 cifre (`00058531300240`).
- FIX (routes/import_massivo.py): costruito indice in memoria numero→id (chiavi = numero raw + solo-cifre senza zeri iniziali, 86.969 chiavi su 49.070 polizze) usato al posto della find_one per polizza (anche molto più veloce). Verificato che i numeri prima falliti ora risolvono. **Richiede ri-upload del CSV** (il file non viene conservato).
- FIX tendine Ramo (bug "RC AutoRC AutoRC Auto" nel form Prodotti): rami globali con lo stesso `codice` → Radix concatenava le label. `GET /librerie/rami?dedup=1` esclude uniti/archiviati e deduplica per codice; usato in Prodotti/Collaboratori (Librerie), Polizze, PolizzaDetail, Titoli, Sinistri, AzioniPolizzaTab. La sezione Librerie→Rami continua a ricevere la lista completa (serve per l'unione doppioni) e nasconde i rami uniti.


- RIELABORAZIONE ESEGUITA (10/09, in-process con ctx utente schianta91): usato l'export `pagamenti.csv` già in GridFS (51.140 righe, 17.385 polizze) → **16.922 polizze aggiornate, 19.342 titoli, solo 463 non trovate** (prima 9.568). Stato finale tenant: 16.956 polizze con metodo_pagamento (bonifico 11.378 · contanti 2.580 · sepa 1.418 · assegno 914 · carta 523 · altro 143), 21.339 titoli con mezzo_pagamento, 19.392 con data_copertura/titolo_coperto.
- Aggiunti alias colonne CSV in `_process_metodo_pagamento` (Copertura|DataCopertura, DataPagam|DataPagamento, TipoPag|ModalitaPagamento) e formati data `%d-%m-%Y`/`%d-%m-%y`.

## Sessione 2026-09-11 — Correzione titoli da titoli.csv, mapping rec20 AG/BP, Google Contatti
- BACKUP: `/app/backups/pre_massivo` (mongodump gz di anagrafiche/polizze/titoli/sinistri tenant 31b4950e) — azzerato e RIPRISTINATO su richiesta utente (si continua con OMNIA per l'import giornaliero).
- CORREZIONE TITOLI (script one-off /tmp/fix_titoli_da_csv.py su titoli.csv in GridFS): fase 1 → 71.265 titoli con scadenza reale (ProssimaScadenza), data copertura, ModalitaPagamento, PagatoInCom; fase 2 → 32.038 titoli con scadenza calcolata effetto+frazionamento. Residui con scadenza errata: 21 (titoli senza effetto). Stato: mezzo_pagamento 65.641 · data_copertura 72.655 · pagamento_in_direzione 5.151.
- ania_importer.py: `_scadenza_da_effetto()` (mai più data odierna come scadenza titolo); rec20 letto per POSIZIONE → col AG (index 32) = data annullo (forza stato "annullata"), col BP (index 67) = `sostituisce_polizza`; log dei nomi header col AG/BP al prossimo import; i re-import NON sovrascrivono scadenza/mezzo_pagamento già rettificati.
- import_massivo.py: match numero polizza con zeri, alias colonne, `operatore_nome` su polizza→collaboratore_id, provvigioni per 4 operatori sul titolo, PagatoInCom→pagamento_in_direzione. ImportMassivo.jsx: elenco campi allineato al backend (contraente_*, data_annullamento, operatori, movimento).
- GOOGLE CONTATTI (nuovo, routes/google_contacts.py + sezione Librerie→Google Contatti): OAuth People API con **Client ID/Secret per agenzia** salvati da UI (secret cifrato Fernet, `GOOGLE_TOKEN_KEY` in .env), refresh token cifrato, sync automatico su create/update anagrafica (background), pulsante "Sincronizza tutti i clienti" (job con avanzamento, 1 contatto/sec, backoff su 429), login_hint + prompt=select_account. PKCE DISABILITATO (autogenerate_code_verifier=False) altrimenti "Missing code verifier" nel callback. Testato end-to-end: contatti creati realmente sull'account assicurazioni@schiantarelli.it.
- UI: Titoli storici default "Anno corrente" (rimosso "Tutti incassati"); Polizze footer con premio totale lordo + netto; badge "Cliente da X anni · dal GG/MM/AAAA" in anagrafica (prima stipula incl. annullate, solo se ha polizze attive); Librerie→Rami "Mappa codici polizze" (riassegna codici OMNIA 3N/33/45 al ramo corretto).


## Sessione 2026-09-11 (parte 2) — Import OMNIA completo + regole portafoglio
- Import OMNIA (ZIP _P_S 02/09) eseguito lato server. La fase titoli è stata interrotta 2 volte (processo in /tmp cancellato dal pod + OOM): NON serviva, i titoli erano già importati. Sostituita da `/app/scripts/post_import_regole.py` (leggero: estrae solo rec52 + regole DB).
- RISULTATO FINALE tenant 31b4950e: 49.070 polizze (5.634 attive · 25.436 annullate · **18.000 sostituite** · 19.532 con campo Sostituisce), 188.409 titoli (181.796 con metodo di pagamento, **118.768 "Pagamento in direzione"**), 7.744 sinistri (**5.377 liquidati** da rec52), 4.366 scadenze contratto allineate all'ultimo titolo pagato.
- MAPPATURE rec20 confermate dall'header reale: col AG=`data_annullamento` (forza stato annullata), col BP=`numero_polizza_sostituita_1`, col AN=`frazionamento_share`, col DK=`data_emissione` (nuovo campo mostrato in testata; effetto resta col AI), col AK=`scadenza_effettiva` per la scadenza contratto + regola di allineamento all'ultimo titolo pagato (`_aggiorna_scadenza_da_titoli`).
- rec52: nuova fase `_processa_liquidazioni` (col Y=data liquidazione, col Z=importo) → `liquidazione`, `data_liquidazione`, stato `liquidato`.
- REGOLE TITOLI: premio 0 → incassato; incassato senza metodo → "Pagamento in direzione" (+flag), sia nell'importer sia via script.
- POLIZZE SENZA COPERTURA: `/app/scripts/chiudi_polizze_scadute.py` — 51 polizze attive/sospese senza copertura da oltre 1 anno annullate (data annullamento = ultima scadenza copertura, motivo "Nessuna copertura/pagamento dal ...").
- NUOVO stato polizza `sostituita` + preset/filtro "Sostituite" in Polizze; storno titoli arretrati su annulla/sostituisci ORA CHIESTO all'utente (endpoint GET /api/polizze/{pid}/titoli-arretrati + flag storna_titoli); DELETE polizza bloccato (409) se esistono titoli incassati/coperti.
- POLIZZA UI: campo `ultimo_premio_pagato` calcolato dal titolo incassato più recente; sezione "Vita / Previdenza" con `Rendita annua` editabile inline (solo rami vita/previdenza); "Data emissione" in testata.
- REGOLAZIONE PREMIO: imposta di polizza % (default **22,25**, modificabile e memorizzata in `regolazione_imposta_pct`) → premio netto + imposta = dovuto cliente.
- SINISTRI: KPI e elenco limitati all'anno in corso (filtro `dal` precompilato, modificabile).
- Test: iteration_85/86/87.json tutti PASS (backend+frontend).



## Sessione 2026-06 (fork) — KPI Titoli storici + correzioni dati OMNIA
- **KPI Titoli storici** (routes/kpi.py `_stats_titoli(storico=True)`): mostra SOLO incassati anno corrente → Incassati {anno} (n+€ lordo), Incassati mese (n+€), Premio netto {anno} (€), Provvigioni {anno} (€). Rimosse Da incassare/Scaduti/Sospesi/Totale. Filtro anno/mese su `data_copertura` (coalesce `data_incasso`, via `$ifNull`). KpiBar.jsx accetta prop `params`; Titoli.jsx passa `{storico:true}` in storicoMode. Testato via API + screenshot.
- **KPI Titoli correnti** (storico=False): Da incassare/Incassati/Scaduti/Sospesi/Totale limitati all'ANNO IN CORSO sulla `scadenza`.
- **Griglia KPI in basso (Titoli.jsx)**: in storicoMode "Da pagare" sostituito da "Premio netto" (t_netto).
- **Filtro periodo Titoli**: nuovo selettore campo data (`data_campo`: scadenza|data_copertura|data_incasso) in list_titoli (server.py) + Select UI in Titoli.jsx. Default scadenza.
- **FIX SCADENZA titoli** (`/app/scripts/fix_scadenza_titoli.py`): 1.712 titoli con scadenza < effetto ricalcolati = effetto + frazionamento (OMNIA metteva in `data_scadenza_emesso` la data avviso). Importer ania_importer.py: ignora `data_scadenza_emesso` se precedente all'effetto.
- **ANNULLAMENTO lapsed** (`/app/scripts/annulla_lapsed_2025.py`): 8 polizze attive scadute senza incasso dal 2025 annullate (+1 titolo stornato). Le 660 senza titoli sono tutte UCA → tenute; 56 con scadenza futura → non toccate. (Precedente cleanup: 0 attive con scadenza<2025 residue.)
- **MERGE doppioni** (`/app/scripts/merge_polizze_dup.py`, MAX_COPIE=3): uniti 5 gruppi da 2 copie nel tenant 31b4950e (3 titoli spostati, 1 aperto duplicato eliminato, 5 polizze vuote rimosse). NON toccate le collettive/libro matricola (numeri 00058533412xxx con 59-391 copie).
- **DUE TENANT**: 31b4950e (produzione utente schianta91@gmail.com, 49k polizze) e tenant-principale-schiantarelli (demo/test, admin@assicura.it) — isolati, il doppione cross-tenant 180992191 NON è un errore.
- **CarichiMensili.jsx**: numero polizza ora cliccabile (Link a /polizze/:polizza_id).
- **APERTO / da decidere**: 938 titoli "incassato" senza data incasso con effetto futuro. In OMNIA `stato_share`="incassato" MA `dt_pag_cliente` vuoto (nessuna data pagamento). Dato NON modificato in attesa di decisione utente (rispettato il flusso SHARE).

### Follow-up: storno titoli aperti "morti" (2026-06 fork)
- CAUSA "titoli 2003 ancora presenti": polizze morte (annullata/sostituita/scaduta) conservavano titoli in stato `da_incassare` mai stornati; la correzione scadenza li aveva riportati alle date reali (es. 2003/2004) rendendoli visibili nel preset "Tutti (da incassare)".
- `/app/scripts/storna_titoli_aperti_morti.py`: stornati 3.218 titoli aperti (3.174 su polizze annullata/sostituita/scaduta + 44 residui pre-2025 su polizze attive). Tenant 31b4950e. Residui: 0.
- NOTA: un re-import OMNIA potrebbe re-introdurli; valutare safeguard nell'importer (storno automatico titoli aperti su polizze morte in post-pass).

### Import anagrafiche Axicura + normalizzazione P.IVA (2026-06 fork)
- **P.IVA a 11 cifre**: nuova funzione `_norm_piva()` in routes/import_anagrafiche.py (solo cifre, strip zeri iniziali se >11 / padding zeri se <11 / fallback ultime 11). Applicata in Import Anagrafiche (`_row_to_anagrafica`) e Import Massivo AI (`_row_to_record` per partita_iva/contraente_piva).
- **Import Massivo AI**: mappa `Tipo` (Privato→persona_fisica; Azienda/Condominio/Altro/PA→persona_giuridica) sia in `_row_to_anagrafica` sia in `_upsert_anagrafica`; aggiunti alias `pec`, `datanascita`, `luogonascita`; campo `pec` aggiunto a ENTITY_FIELDS anagrafica + lowercase.
- **Import eseguito** (`/app/scripts/import_anagrafiche_axicura.py`, policy fill-missing, contesto tenant via `set_current_user`): 2.656 anagrafiche create nel tenant `c5ae2d0e-283e-4513-aaf2-cbd97ef62d78` (agenzia "Importazione Axicura", admin jacopo@schiantarelli.it) da contraenti.csv (latin-1, ';'). 520 P.IVA tutte a 11 cifre, 0 errori. ATTENZIONE: il backend/.env definisce ADMIN_EMAIL=admin@assicura.it → passare sempre ADMIN_EMAIL esplicito agli script.

### Import portafoglio polizze Axicura + fix Import Massivo AI (2026-06 fork)
- **Fix rilevamento entità** (`_detect_entity_heuristic`): rimosso "mandato"/"tipo pagam"/"rata" dai trigger movimento/titolo (causavano falsi positivi sui portafogli); aggiunto rilevamento polizza per (ramo + contraente + data) oltre a numero polizza esplicito.
- **Fix mapping** (`_detect_mapping_heuristic`): ignora le colonne con token "firma" (Lordo_firma/Netto_firma/Provv_firma = valori "alla firma") così Lordo/Netto/Provvigioni vincono; rimosso alias "prov"/"prov." da provincia (Provvigioni_annue non mappa più a provincia; "Prov" resta gestito via substring di "provincia").
- **Prompt AI** aggiornato con le stesse regole (portafoglio→polizza, ignora _firma, Provv_firma≠provincia).
- **Import eseguito** (`/app/scripts/import_polizze_axicura.py`, riusa `_run_commit_inner` con `set_current_user`): da portafoglio_attivo.csv → 5.311 polizze nel tenant c5ae2d0e (5.058 attive, 222 sospese, 31 annullate), tutte collegate al contraente; +46 anagrafiche nuove, +12 collaboratori bozza. 0 errori.
- **Anagrafiche.jsx**: auto-switch a "Tutte" quando `con_polizze==0` ma esistono anagrafiche (evita schermata vuota post-import senza polizze).

### Import portafoglio ANNULLATE Axicura (2026-06 fork)
- `portafoglio_annullato.csv` (21.169 righe, 60 colonne) importato nel tenant c5ae2d0e via `import_polizze_axicura.py`. Solo ~12k avevano Data_annul → post-step forza stato "annullata" (8.125 righe senza data, data_annullamento=scadenza) sui numeri esclusivi del file annullato (esclusi i 44 presenti anche nell'attivo, per non annullare polizze attive).
- Stati finali tenant Axicura: 5.058 attiva, 1.047 sospesa, 20.179 annullata (tot 26.284 polizze, tutte con contraente). Anagrafiche: 5.579.
- FIX bug import_massivo (polizza): guardia su `existing` None in `_fill_missing` (i duplicati intra-file causavano 149 errori "'NoneType' has no attribute 'get'").

### Import TITOLI incassati Axicura (2026-06 fork)
- `titoli_incassati_periodo.csv` (51.320 righe) importato nel tenant c5ae2d0e via `import_titoli_axicura.py` (mapping ESPLICITO, entità titolo forzata). Tutti incassati, con data_copertura, mezzo_pagamento, collegati alla polizza (17.435/17.436 numeri trovati, 1 polizza auto-creata). 13 metodi pagamento auto-creati. 0 errori.
- Mapping chiave: NumPolizza→numero_polizza, Copertura→data_copertura, TipoPag→mezzo_pagamento, DataPagam→data_incasso, Totale→importo_lordo, Netto→importo_netto, Imposte→imposte, Provvigioni→provvigioni, RataDel→effetto, Operatore 1..4→ripartizione provvigioni.
- **NUOVA REGOLA** (import_massivo titolo): titolo INCASSATO senza mezzo_pagamento → `pagamento_in_direzione=True`.
- **Fix Import Massivo AI titoli**: rilevamento entità titolo aggiunto (copertura/tipopag/datapagam); alias mezzo_pagamento estesi con "tipopag"/"tipo pag".

### Import OMNIA ZIP (A_OW8) + arretrati/sospesi Axicura (2026-06 fork)
- ZIP OMNIA arricchimento (vincolato) via `import_omnia_axicura.py` (fasi: iban/polizze_dettagli/prodotti/sinistri/sostituzioni). Matching numero polizza con NORMALIZZAZIONE zeri iniziali (000585=585) → 26.351 match. Fix in ania_importer `_resolve_polizza_id` (fallback lstrip '0').
  - IBAN: 486 aggiunti a conti_correnti (no email/cellulare/operatore toccati).
  - Veicoli (rec21) + Garanzie (rec30 163k): 25.378 polizze con garanzie, 16.396 con targa/massimali. Nessuna modifica a date/operatore/ramo/titoli.
  - Prodotti (rec100): nome prodotto aggiornato su 25.556 polizze (prodotto_originale=codice).
  - Sinistri (rec50/52): 6.410 creati + 5.169 liquidazioni.
  - Sostituzioni: 7.395 vecchie collegate (stato sostituita + sostituita_da_polizza_id); frazionamento OMNIA vince; 734 annullate a scadenza (frazionamento unico/temporaneo scaduto).
- Indici creati: polizze.id, polizze.numero_polizza, titoli.polizza_id, titoli.id_titolo_exp, anagrafiche.id, sinistri.id_sinistro_exp (velocizzano bulk).
- Arretrati (`import_arretrati_axicura.py`, file 'stampa', 447): 398 titoli da_incassare; netto/imposte/provvigioni ricostruiti dalle proporzioni di un titolo di riferimento della polizza; date parse via `_parse_date_flexible` (gestisce DD-MM-YYYY e DD/MM/YY).
- Sospesi/anticipi (`import_sospesi_axicura.py`, 76): 62 titoli da_incassare + titolo_coperto=True + data_copertura dalle date file. NB: Titolo NON ha stato 'sospeso' → anticipo = da_incassare+coperto.
- Annullate su richiesta: 72 polizze sospese con numero prefisso 58533. Prefissi '0'/'2015' → 0 match (numeri in DB senza zeri iniziali).
- APERTO (utente ha detto NON toccare ora): garanzie mappate 'FAMIGLIA' (codici D21/T04/E07) che dovrebbero essere 'I.P. Infortunio' su alcune polizze.

### Correzione arretrati con valori esatti rec40 (2026-06 fork)
- `fix_arretrati_da_rec40.py`: match arretrati (file stampa) ↔ rec40 OMNIA per (numero polizza normalizzato + effetto_titolo == 'Rata del'). Applica valori ESATTI: importo_netto=netto_totale, imposte=tasse_totale (netto+tasse=lordo), accessori, importo_lordo=lordo_totale, provvigioni=provvigioni_totale. 397/447 titoli aggiornati; 10 senza corrispondenza nel rec40 (mantengono il calcolo proporzionale). Nota: Titolo non ha campo SSN (ssn è componente delle tasse).

### Import titoli PS (pagamento in direzione) da rec40 (2026-06 fork)
- `import_ps_direzione_axicura.py`: importati dal rec40 OMNIA 2.466 titoli con mezzo_pagamento_cmp='PS' non ancora presenti (dedup per polizza+effetto+lordo). mezzo_pagamento="Pagamento in direzione", pagamento_in_direzione=True, valori esatti (netto/tasse/accessori/lordo/provv), stato incassato se dt_pag_cliente presente (2.464), data_incasso/data_copertura=dt_pag_cliente. note_carico='OMNIA PS - pagamento in direzione'. 187 dup saltati, 2 senza polizza.
- Codici pagamento OMNIA titoli: mezzo_pag_share SEC=SDD Compagnia, ID=direzione; mezzo_pagamento_cmp RD=RID/SDD, PS=pagamento sportello/diretto, BN=bonifico, AS=assegno, CO=contanti.

### Import titoli SDD (SEC/RD) da rec40 come pagamento in direzione (2026-06 fork)
- `import_sdd_direzione_axicura.py`: 1.845 titoli con mezzo_pag_share='SEC' o mezzo_pagamento_cmp='RD' importati (dedup polizza+effetto+lordo, 16 saltati), mezzo_pagamento="Pagamento in direzione", valori esatti. Titoli tenant Axicura tot: 56.091.

### Sessione fork 2026-06 — Mora/Disdetta, RID Direzione, Provvigioni, Filtro compagnie, Riprendi contratto
- **Verifica termini OMNIA rec20**: `disdetta_share`=0 ovunque (assente); `giorni_mora` presente per 938 polizze (15/30). Script `update_mora_da_omnia.py`: aggiornate 1.030 polizze (mora>0) + 32 record libreria Prodotti (valore prevalente per prodotto). Non azzera i default.
- **RID DIREZIONE (SDD)**: `set_rid_direzione_sdd.py` — 1.845 titoli SDD (note_carico='OMNIA SDD - pagamento in direzione') → mezzo_pagamento='RID DIREZIONE'; 127 polizze → mezzo_pagamento_preferito='RID DIREZIONE'. PS e preesistenti non toccati.
- **Provvigioni da titoli**: `fill_provvigioni_da_titoli.py` — 21.261 polizze senza provvigione valorizzate con la provvigione del titolo PIU' RECENTE (annualità corrente). Solo dove >0.
- **Filtro compagnie disabilitate**: `GET /api/compagnie` ora nasconde di default le compagnie `attiva=False` senza polizze attive; param `?tutte=true` per gestione (Compagnie.jsx, Librerie.jsx). Filtri/form usano il default filtrato.
- **Riprendi contratto**: nuovo `POST /api/polizze/{pid}/riprendi` (annullata→attiva, pulisce data/motivo, opz. ripristina titoli stornati) + `GET /api/polizze/{pid}/titoli-stornati-annullamento`. UI: pulsante verde "Riprendi Contratto" nel banner del tab Azioni (`AzioniPolizzaTab.jsx`) solo per polizze annullate, con popup ripristino titoli. Testato e2e (curl) + screenshot UI.

### Sessione fork 2026-06 — Unione utenti/collaboratori (merge)
- **Backend**: `POST /api/auth/users/merge-preview` (conteggi polizze/titoli/anagrafiche/trattative per sorgente) e `POST /api/auth/users/merge` (body {target_id, source_ids}). Riassegna `collaboratore_id` su 8 collezioni (anagrafiche, polizze, titoli, trattative, voci_manuali_collab, voci_ricorsive_collab, pagamenti_provvigioni, schema_provvigionale), aggiorna `collaboratore_nome` denormalizzato, riassegna `provvigioni_operatori[].operatore_id/operatore_nome` (arrayFilters) su polizze/titoli, riassegna `parent_collaboratore_id` (rete piramidale). Le sorgenti restano DISATTIVATE (`attivo=False`, `merged_into=target_id`), non eliminate. Nessun cliente ammesso. Tenant-scoped via wrapper.
- **Frontend**: Librerie → Utenti/Collaboratori → pulsante "Unisci utenti" apre `MergeUtentiDialog` (radio destinazione + checkbox da unire + Anteprima conteggi + conferma). testid: lib-merge-utenti, merge-utenti-dialog, merge-utente-target-{id}, merge-utente-source-{id}, merge-utenti-preview-btn, merge-utenti-conferma.
- Testato e2e via curl (anagrafica+titolo+provvigioni_operatori riassegnati al target, sorgente disattivata) + screenshot UI dialog.

### Sessione fork 2026-06 — Nuove causali contabili
- Aggiunte 4 causali al movimento contabile: `prelievo_soci`, `compenso_amministratore`, `imposte`, `stipendi` (enum `MovimentoCategoria` in db_models.py).
- Cervello Mini Bilancio: nuove righe di COSTO distinte (Prelievo Soci, Compenso Amministratore, Imposte, Stipendi) in `_MB_AUTO_COSTI` + mapping in `_mb_classify` (routes/cervello.py).
- Frontend: SelectItem aggiunti in "Causali standard" (Contabilita.jsx). Testato via API (movimento stipendi/imposte → righe costo Mini Bilancio).

### Sessione fork 2026-06 — Ripristino unione utenti + Filtro attivi
- **Merge con provenienza**: il merge ora stampa `merged_from_user_id` sui documenti riassegnati, `merged_from_operatore_id` sugli elementi di provvigioni_operatori, `merged_parent_from` sugli utenti della rete, e `merged_at` sulla sorgente. (server.py)
- **Unmerge**: `POST /api/auth/users/{uid}/unmerge` riporta alla sorgente i dati tracciati, rimuove gli stamp, riattiva l'utente (attivo=True, unset merged_into/merged_at). Le unioni precedenti al tracciamento riattivano soltanto l'utente.
- **Filtro Attivi (frontend Librerie.jsx)**: la tab Utenti nasconde di default gli utenti `attivo===false`; toggle "Mostra anche disattivati (N)" (testid lib-toggle-inactive-utenti). Badge "unito"/"disattivato" sulle righe; azione "Ripristina unione" nel menu ⋮ (testid utente-unmerge-{id}) solo per utenti con merged_into.
- Testato: ciclo merge→unmerge via API (anagrafica/titolo/provvigioni_operatori riportati alla sorgente, utente riattivato) + smoke test UI.

### Sessione fork 2026-06 — Collaboratori uniti esclusi dai filtri
- `GET /api/collaboratori`: param `tutti` (default False). Di default esclude `attivo=False` (collaboratori disattivati/uniti) così non compaiono nei filtri "Filtra per collaboratore" in tutto il programma. `?tutti=true` per la gestione.
- Frontend: filtri basati su `/auth/users` ora escludono `attivo!==false` (Titoli, Sinistri, Polizze, Ritenute, Alert già ok, DocumentiMancantiWidget). CollaboratoreInlineSelect lasciato invariato (mostra "(inattivo)" per risolvere i nomi storici, non è un filtro).
- Verificato via endpoint (admin: default 6 senza disattivati vs tutti=true 17 con 11 disattivati) e via wrapper tenant Axicura (collaboratore unito escluso: 19 su 20).

### Sessione fork 2026-06 — Riconciliazione Sospesi/Anticipi Axicura (da PDF)
- Titolo 730801946 → incassato 01/09/2026, mezzo "BONIFICO BPER SONDRIO".
- Script `scripts/riconcilia_sospesi_axicura.py` (DRY env var): dal PDF ufficiale 40 righe → 34 titoli impostati coperti (titolo_coperto=True, stato=da_incassare, data_copertura da PDF, importo_da_pagare da colonna "Da Pagare") +2 stragglers cross-tenant via client diretto. 35 sospesi NON nel PDF → incassati (erano già saldati).
- Non applicabili: 3 note di credito (importi negativi, nessun titolo) e 184643448 (titolo inesistente in DB).
- Endpoint `/api/titoli/sospesi` ora ritorna `importo_da_pagare`; pagina TitoliSospesi mostra colonna "Da Pagare €" (fallback importo_lordo) su totali, riepilogo collaboratori e righe.

### Sessione fork 2026-06 — Sovrascrittura Sospesi da PDF (tenant c5ae2d0e)
- SCOPERTA: dati Axicura DUPLICATI su due tenant (c5ae2d0e=jacopo@schiantarelli.it "Importazione Axicura", 56k titoli; tenant-principale-schiantarelli). Il tenant operativo dell'utente è c5ae2d0e (la fusione collaboratori è avvenuta lì).
- Script `scripts/riconcilia_sospesi_c5ae2d0e.py`: sovrascrive i sospesi in c5ae2d0e col PDF 'Sospesi.pdf' (48 righe): 41 titoli aggiornati + 7 creati (coperti, data_copertura + importo_da_pagare da PDF). Totale sospesi = 21.455,88 € (match esatto). Altri sospesi -> incassati. 730801946 -> incassato 01/09/2026 BONIFICO BPER SONDRIO. Puliti 3 negativi stray su tenant-principale.
- Aperto: differenza 74€ attribuzione BS Broker vs Importazione Axicura. Aperto: ricalcolo provvigione collaboratore su TUTTO il portafoglio (schema: 70% su provvigione agenzia / BS 4,5% su netto) non ancora eseguito.

### Sessione fork 2026-06 — Ricalcolo provvigioni + Estratti conto dal setup
- Ricalcolo provvigione_collaboratore su tutto il portafoglio c5ae2d0e (script ricalcola_provvigioni_portafoglio.py): 11.453 polizze e 25.590 titoli valorizzati. Regola: pct_su_premio_netto>0 -> netto*%; pct_su_premio>0 -> lordo*%; pct_collaboratore>0 -> provvigione_agenzia*% (es. BS 4,5% netto=55,02; altri 70% su provv agenzia). Resolver gerarchico identico al backend.
- Fix attribuzione 74€: titoli 975218000 (48) e 1001004878 (26) riassegnati da BS Broker a Importazione Axicura (come da PDF). Totali per collaboratore ora esatti.
- Estratti conto (compagnia `_compagnia_estratto_data` e collaboratori `estratto_provvigioni`): nuovo `_setup_cutoff_date()` = min data movimenti setup iniziale (go-live). Sotto il cutoff = pregresso escluso; l'estratto parte dal saldo di apertura del setup (righe tipo 'saldo_iniziale'). Tenant tenuti DISTINTI (nessuna fusione, richiesta utente).

### Sessione fork 2026-06 — Reset estratti conto (solo setup)
- Aggiunto flag `pregresso` sui dati migrati. Estratti conto (compagnia + collaboratori) escludono `pregresso=True`: mostrano solo il saldo iniziale del setup + operazioni future.
- Reset c5ae2d0e: 55.644 titoli incassato -> pregresso=True (sospesi da_incassare e movimenti di setup NON toccati). Endpoints `_compagnia_estratto_data` (titoli/mov/rappel/ritenute) e `estratto_provvigioni` (titolo_filter) filtrano pregresso!=True.
- Verificato: estratto compagnia = solo 4 righe saldo_iniziale setup; estratto collaboratori = 0 incassi pregressi.

### Sessione fork 2026-06 — Modifica setup iniziale
- Backend (routes/setup_scambio.py): `POST /setup-iniziale?forza=true` ora ELIMINA gli artefatti del setup precedente (movimenti/sospesi/titoli is_setup_iniziale) e li ricrea con i nuovi dati (= modifica). Nuovo `GET /setup-iniziale/dati` ricostruisce i valori correnti (una riga per movimento, nessun raggruppamento -> no perdita dati) per precompilare il form.
- Frontend (SetupIniziale.jsx): nella card "completato" pulsante "Modifica setup" (carica i dati e apre il form in editMode) + banner "stai modificando" con "Annulla modifica"; submit usa ?forza=true e mostra "Salva modifiche". Reset invariato.
- Verificato round-trip (dati->forza) senza perdita: totali dare/avere e n. movimenti identici.

### Sessione fork 2026-06 — Sovrascrittura sospesi da CSV
- Script sovrascrivi_sospesi_csv.py: legge /tmp/sospesi_new.csv (col: Num.Contratto;Rata del;Contraente;Targa;Frazionamento;Rata=da pagare). Tenant c5ae2d0e: 76 righe valide -> 72 titoli aggiornati coperti + 4 creati, importo_da_pagare=Rata, data_copertura=Rata del, pregresso=False. Ex-sospesi non nel CSV -> incassati. Totale sospesi = 31.786,28 € (match footer CSV). Skippate righe footer/totale vuote.

### Sessione fork 2026-06 — Paga compagnia estesa a ritenute/rappel/PNC/voci manuali
- Richiesta utente: in Estratto Conto Compagnie le voci ritenuta/rappel/PNC/voce manuale (incl. saldo iniziale) formano il Saldo e devono rientrare nel "Paga compagnia" (selezionando tutto l'importo = Saldo, e dopo il versamento il Saldo va a 0).
- Backend server.py `_compagnia_estratto_data`: aggiunto flag `saldata` (da `saldata_compagnia`) e `movimento_pagamento_id` a righe rappel/ritenute/pnc/fatture_partner/voci_manuali; righe incasso ora espongono `stato_pagamento` reale (pagato/da_versare) dal titolo.
- Backend `paga-titoli`: accetta `voci:[{tipo,id}]` oltre a `titoli_ids`; importo = somma (Dare−Avere) delle righe selezionate calcolata dall'estratto (coerenza al centesimo, gestisce direzione/sconti); marca titoli `pagato_alla_compagnia` e voci `saldata_compagnia` con `movimento_pagamento_id`.
- Frontend EstrattoContoCompagnie.jsx: checkbox su tutte le righe versabili (titoli+voci non saldate), importoSel=Σ(dare-avere), toggleAll estende a tutte, PagamentoDialog invia titoli_ids+voci. Colonna "Dare €" rinominata "Saldo €".
- Voci saldate e titoli pagati spariscono dalla lista attiva (visibili solo se ancora aperti). Test E2E reversibile su CATTOLICA (tenant c5ae2d0e): saldo 51.501,22 → pagamento 51.501,22 (66 titoli+3 voci) → saldo 0,00 → rollback a 51.501,22. Nessun dato reale modificato.

### Sessione fork 2026-06 — Ricerca Brogliaccio + Stampa/Storico voci E/C
- Task1 Brogliaccio (BrogliaccioTab.jsx): aggiunto campo "Cerca contraente" (data-testid brogliaccio-search) che filtra righeView client-side per nome/cognome o descrizione; filtroAttivo e totali ricalcolati.
- Task2 Stampa selezionati (server.py stampa_compagnia_titoli_selezionati): TitoliSelectionBody ora accetta voci[]; il PDF include sezione "ALTRE VOCI" (ritenute/rappel/pnc/voci manuali) con importo net (Dare-Avere) dall'E/C e nel totale. Frontend EstrattoContoCompagnie.stampaSelezionati invia titoli_ids+voci. Direzione gestita (dovuto=-provv).
- Task3 Storico rimesse (server.py rimesse-storico + stampa_rimessa): risolve mov.voci_versate in righe leggibili (label/descrizione/importo net) -> campo `voci` e `n_voci`; PDF rimessa con sezione "ALTRE VOCI". Frontend RowRimessa mostra tabella "Altre voci versate" e conteggio "n_titoli + n_voci".
- Test E2E reversibile CATTOLICA: stampa selezionati ok, rimessa storico n_titoli=66/n_voci=3 (138,71+26.732,00+80,19=26.950,90), PDF rimessa ok, rollback saldo 51.501,22. Nessun dato reale modificato.

### Sessione fork 2026-06 — Ripristino entità all'eliminazione movimento Prima Nota
- Verifica utente: prima l'eliminazione di un movimento NON ripristinava titolo/regolazione (restavano incassato/coperto/versato) -> disallineamento.
- server.py: nuova `_revert_entita_da_movimento(mov,user)` chiamata da DELETE /contabilita/movimenti/{id} dopo la delete. Ripristino per categoria:
  * incasso_coperto -> titolo torna COPERTO (stato da_incassare, titolo_coperto=True, data_copertura mantenuta, unset dati incasso)
  * incasso_premio / incasso_premio_direzione -> titolo torna ARRETRATO (da_incassare, titolo_coperto=False, unset dati incasso + pagamento_in_direzione)
  * copertura_titolo -> copertura annullata, titolo torna ARRETRATO (unset data_copertura/note_copertura)
  * pagamento_compagnia -> titoli e voci (ritenute/rappel/pnc/voci manuali) tornano NON saldati
  * regolazione: se titolo di regolazione e polizza.regolazione_stato=="chiusa" -> riportata a "titolo_generato"
  * riallinea scadenze polizza via _aggiorna_scadenze_polizza_da_titolo
- brogliaccio row: aggiunto titolo_id. BrogliaccioTab.elimina mostra avviso esplicito ("il titolo tornerà COPERTO/ARRETRATO" o "titoli/voci NON saldati") prima di confermare.
- Test diretto helper (titoli temporanei, poi rimossi): 5/5 scenari OK (arretrato/coperto/copertura/direzione/pagamento compagnia). Nessun dato reale toccato.

### Sessione fork 2026-06 — Sezione Banche + verifica propagazione eliminazione
- Nuova voce menu "Banche" (/banche, section contabilita) — Sidebar.jsx + App.js route + pages/Banche.jsx.
- Backend server.py:
  * GET /contabilita/banche/saldi -> saldo attuale per ogni conto_cassa (saldo_iniziale + entrate - uscite), + saldo_totale (solo conti attivi).
  * GET /contabilita/banche/movimenti -> filtri conto_cassa_id, dal/al, cliente (regex nome/cognome/ragione_sociale), numero_polizza (regex), collaboratore_id. Enrichment contraente/polizza/collaboratore/conto. Saldo progressivo (con saldo di apertura periodo) SOLO se banca singola e nessun filtro entità.
- Frontend Banche.jsx: card saldo cliccabili (selezionano la banca), filtri, tabella movimenti con Entrata/Uscita e Saldo progressivo, riga "Saldo di apertura periodo".
- Punto 2 (elimina da "Movimenti elenco"): NON implementato su richiesta utente.
- Punto 3 VERIFICATO con test: eliminando un movimento sparisce da banche/elenco/prima-nota (0/0/0); giroconto -> delete di una gamba elimina entrambe (2->0). Stessa fonte dati `movimenti`.
- Test reale (tenant Axicura): 9 conti, totale 283.400,69; BPER SONDRIO saldo 249.085,92 con saldo progressivo coerente. Nessun dato reale modificato (insert/delete temporanei ripuliti).

### Sessione fork 2026-06 — Export Banche + Task collegato a Titolo/Rata + verifica IBAN
- Export Banche (server.py): GET /contabilita/banche/movimenti/stampa (PDF landscape) e /export.xlsx (openpyxl) — stessi filtri di banche_movimenti; PDF valido, XLSX ~10KB (PK). Frontend Banche.jsx: pulsanti PDF/Excel in header che aprono l'URL con i filtri correnti.
- Task collegato a Titolo/Rata (Tasks.jsx): dialog "Collega a" ora ha opzione "Titolo / Rata": cerca la polizza -> carica /titoli?polizza_id -> scegli la rata (scadenza + importo + stato). collegamento_tipo=titolo (già supportato dal backend routes/tasks.py). label es. "Pol. N... · rata gg/mm/aaaa · € importo (stato)".
- IBAN: GIA' implementato in AnagraficaDetail.jsx (righe ~432-443): campo IBAN nel riepilogo con fallback all'IBAN del conto corrente principale (ana.conti_correnti principale/primo); ContiCorrentiTab sincronizza ana.iban quando si imposta il conto principale. Solo verifica, nessuna nuova modifica.
- "Titoli storici disallineati": nessuna azione (richiesta utente).

### Sessione fork 2026-06 — WhatsApp: ripristino automatico chat archiviate + rename PNC->PNT
- Sidebar.jsx: label voce menu "PNC" rinominata in "PNT".
- WhatsApp (routes/whatsapp_evo.py): nuova _unarchive_chat(instance, number) che azzera whatsapp_chat_meta.archived quando arriva/parte un messaggio. Chiamata in: webhook (in/out), send_text, send_media, send_text_via_evolution (avvisi automatici). La vista "Archiviate" (toggle in Chat.jsx già esistente) resta il posto dove consultarle.
- Comportamento: chat archiviata torna tra le attive se il cliente scrive o l'agenzia scrive al cliente. Testato (no-ctx webhook + con-ctx invio) -> archived False in entrambi i casi. Reversibile, nessun dato reale toccato.

### Sessione fork 2026-06 — Dashboard: card "Attività recenti dei clienti"
- Backend routes/dashboard.py: GET /dashboard/attivita-clienti (giorni=30, limit=20). Aggrega 3 fonti risolvendo il tenant via entità collegate (robusto anche per endpoint pubblici senza contesto tenant):
  * doc_link: upload_links.uploads (filtro agenzia_tenant_id) — cliente carica da link "Richiedi documento".
  * regolazione: regolazione_storico evento=dato_cliente_ricevuto -> tenant via polizza.agenzia_tenant_id.
  * app_upload: richieste_cliente tipo=upload_documento -> tenant via anagrafica.agenzia_tenant_id.
  Ordina per data desc, ritorna {eventi, totale}.
- Frontend Dashboard.jsx: nuovo componente ClientiAttivitaCard (dopo DashboardTasks, solo staff) con icona per tipo (Paperclip/Euro/Smartphone), cliente, descrizione, tempo relativo e link a scheda cliente/polizza. Empty-state se nessun evento.
- Nessuna notifica campanella aggiunta (scelta utente). La regolazione premio continua a creare la sua notifica in-app come prima.
- Test: endpoint verificato end-to-end su dati reali (evento doc_link "MARIO TEST · libretto.pdf" con link a /anagrafiche/...). Card renderizzata in Dashboard.

### Sessione fork 2026-06 — Fix eSignature OpenAPI (invio MUP per firma)
- Sintomo: "Genera e invia per firma" mostrava errore Cloudflare (520). Causa reale nei log: OpenAPI EU-AES risponde HTTP 422 {"message":"invalid signer 'mobile'"} perché il cellulare veniva inviato grezzo, mentre OpenAPI richiede E.164 (+39...). Il backend rilanciava 502 -> Cloudflare mostrava errore origin.
- Fix: esignature_openapi.py nuova _normalize_mobile() -> E.164 (gestisce spazi/trattini/punti, 00, +39, numero nazionale). Applicata in create_signature (campo signer.mobile). routes/esignature_it.py: errore creazione firma ora HTTPException(400) con messaggio chiaro invece di 502.
- SANDBOX: OPENAPI_ESIGNATURE_SANDBOX risulta disattivo -> chiamate verso PRODUZIONE esignature.openapi.com (token OK). Flusso: /polizze/{id}/mup/genera (salva) -> /esignature/invia -> create EU-AES -> link firma via WA/email in background + OTP SMS.
- Test: _normalize_mobile verificato su 7 formati -> tutti +393402934389. Verifica live end-to-end NON eseguita (invia SMS reale + consuma crediti): da fare con numero di test dell'agenzia.
- IN PAUSA (richiesta precedente non completata): wa.me -> invio via API Evolution quando l'agenzia ha WhatsApp API attiva. Esiste già provider wame|evolution; alcune UI forzano ancora wa.me (AnagraficaDetail 2234, ContrattoConsulenzaTab 178, upload-link "Invia via WhatsApp", ecc.). Da unificare su un helper che rispetti az.whatsapp_provider.

### Sessione fork 2026-06 — eSignature: passaggio a FES (EU-SES) + wa.me/API (parziale)
- Firma cambiata da EU-AES (Avanzata) a FES/SES (Semplice) con OTP SMS, SENZA documento d'identità (richiesta utente).
  * esignature_openapi.py: endpoint POST /EU-SES (era /EU-AES), scope token POST:{host}/EU-SES, aggiunto signer.authentication=["sms"]. Mantiene _normalize_mobile E.164 e email obbligatoria.
  * routes/esignature_it.py: email firmatario ora obbligatoria (OpenAPI la richiede, err 815).
  * Test LIVE ok su 3402934389: EU-SES HTTP 200, state WAIT_VALIDATION, signing_url generato e inviato via WhatsApp (istanza agenzia-0342706000). OTP arriva via SMS quando il firmatario apre il link.
- wa.me -> invio provider-aware (parziale):
  * lib/api.js: nuovo helper sendWhatsApp(numero,messaggio,extra) che chiama POST /comunicazioni/whatsapp/invia (già esistente: rispetta azienda_config.whatsapp_provider — evolution=invio API, wame=apre link).
  * AnagraficaDetail.jsx "Richiedi documento": pulsante WhatsApp ora usa sendWhatsApp (provider-aware) invece di wa.me hardcoded.
  * DA COMPLETARE: ContrattoConsulenzaTab.jsx (usa firma legacy eSignAnyWhere, wa.me senza numero) e RubricaCompagnie.jsx (contatto compagnie). Non modificati per non rischiare.

### Sessione fork 2026-06 (3) — Firma FES: no anteprima link + wa.me/API completato + avviso contatti + badge
- Anteprima link WhatsApp (bandiera/immagine sul link firma): aggiunto "linkPreview": false su TUTTI gli invii sendText Evolution:
  * routes/whatsapp_evo.py (send_text riga ~324, send_text_via_evolution ~950)
  * server.py whatsapp_invia (~12507)
  * alert_dispatcher.py (~394)
  Ora i messaggi mostrano solo testo + link, senza preview.
- wa.me -> API completato (provider-aware):
  * ContrattoConsulenzaTab.jsx: firmaEsignContratto(link_whatsapp) ora usa sendWhatsApp(cellulare, testo, {anagrafica_id}). Cellulare/email cliente aggiunti alla GET /anagrafiche/{id}/contratto-consulenza (campo "cliente").
  * RubricaCompagnie.jsx: pulsante WhatsApp ora chiede il messaggio (prompt) e invia via sendWhatsApp invece di aprire wa.me/{cell}.
  (AnagraficaDetail già fatto in sessione precedente.)
- Avviso email/cellulare firma (FES richiede entrambi):
  * Nuovo endpoint GET /api/esignature/firmatario?entita_tipo=&entita_id= -> {email,mobile,email_ok,mobile_ok,ok}. Validatori _mobile_valido (>=8 cifre) e _email_valida.
  * FirmaButton (DocumentiSezioneSplit.jsx): al apertura dialog verifica il contraente; se email/cellulare non validi mostra banner rosso e DISABILITA "Invia richiesta firma" finché non si compilano i campi manuali.
- Badge stato firma: label fallback cambiata da "In firma" a "In attesa firma" sul documento (dettaglio polizza). La dashboard "Documenti mancanti" ha già la card "Firme in attesa" (extras_p1p2.py firme_in_attesa) — nessuna modifica necessaria lì.
- Test: backend endpoint /esignature/firmatario + resolver/validatori verificati su dati reali (anagrafica con cell+email -> ok True). Frontend compila senza errori (risolto uso condizionale di useEffect in FirmaButton). Invio WhatsApp reale non testato e2e (consuma crediti/SMS).

### Sessione fork 2026-06 (4) — Fix: WhatsApp apriva ancora wa.me nonostante API attiva
- Sintomo (agenzia c5ae2d0e... jacopo@schiantarelli.it): attivata WhatsApp API dal marketplace super console, ma il pulsante WhatsApp ("Richiedi documento", ecc.) apriva ancora wa.me.
- Causa: azienda_config.whatsapp_provider dell'agenzia era ancora "wame". L'attivazione marketplace connette l'istanza Evolution (whatsapp_instances state=open) ma NON flippa whatsapp_provider. L'endpoint POST /comunicazioni/whatsapp/invia sceglieva il provider solo da whatsapp_provider -> wame -> link wa.me.
- Fix (server.py whatsapp_invia): auto-rilevamento. Se il tenant ha un'istanza whatsapp connessa (state open/connected) e non c'è provider esplicito nel body, il provider diventa "evolution" (invio via API, tracciato). Rispetta sempre body.provider se passato. Entrambe le collezioni (azienda_config, whatsapp_instances) sono tenant-scoped, quindi la scelta è per-agenzia.
- Test: simulato il contesto tenant di jacopo -> az.whatsapp_provider="wame" + istanza "agenzia-0342706000" connessa -> PROVIDER FINALE = evolution. Backend riavviato ok.

### Sessione fork 2026-06 (5) — TitoloDialog: automazioni nuovo titolo
File: frontend/src/components/TitoloDialog.jsx
1. Premio LORDO auto-calcolato = netto+imposte+SSN+diritti+accessori (useEffect reattivo). Campo Lordo ora read-only/disabled con hint.
2. Date effetto/scadenza da frazionamento polizza: al caricamento polizza si legge frazionamento (MESI_FRAZ annuale12/semestrale6/quadrimestrale4/trimestrale3/bimestrale2/mensile1/unica12). Per nuovo titolo effetto default = scadenza polizza (o prossima_quietanza/effetto), scadenza = effetto + N mesi. setEffetto ricalcola scadenza al cambio effetto. Gestione fine-mese (31/01 mensile -> 28/02).
3. Ricalcolo automatico quote collaboratori quando cambia il totale provvigioni: onBlur del campo "Provvigioni € (totale)" chiama recalcOperatoriDaTotale() che ricomputa ogni quota via quotaCollaboratore(operatore_id, total) usando lo schema provvigionale (% compenso o % netto).
Verifica: logica date/somma testata via node (ok). Compile frontend ok. NON testato in UI end-to-end: admin@assicura.it ha tenant vuoto, i dati reali sono in tenant c5ae2d0e (jacopo, pwd non disponibile), sandbox user inesistente. test_credentials.md risulta STALE.

### Sessione fork 2026-06 (6) — Fix: ricerca Titoli mostrava risultati non pertinenti
File: frontend/src/pages/Titoli.jsx
- Sintomo: digitando un numero polizza/nominativo completo, la lista mostrava polizze/contraenti non corrispondenti.
- Causa: nessun debounce né guardia sulle risposte. La useEffect [filters] lanciava una GET /titoli ad ogni tasto. Le query con prefisso più corto matchano molte più polizze e sono più lente (enrichment provvigioni N titoli), quindi la loro risposta arrivava DOPO quella della query completa (2 risultati, veloce) e sovrascriveva la lista con risultati stale/non pertinenti (race condition out-of-order).
- Fix: (1) loadSeq ref -> in load() si applica setList solo se seq === loadSeq.current (ignora risposte fuori-ordine); (2) debounce 300ms sull'effetto [filters] per non interrogare ad ogni tasto.
- Verifica backend: con q=731040585 nel tenant di jacopo la query filtra correttamente 1 polizza / 2 titoli (backend OK, il problema era solo lato frontend). Compile frontend OK. NON testato in UI e2e (mancano credenziali con dati).

### Sessione fork 2026-06 (7) — Coperto il, fix importazioni/scadenze/dedup, bonifica, KPI Prima Nota
- COPERTO IL: /titoli/{id}/incassa ora accetta e salva data_copertura (distinta da data_incasso). DialogIncassoCopertura passa data_copertura quando copertura+incasso contestuali. Verificato via HTTP: incasso con date diverse -> data_copertura e data_incasso salvate separatamente. Colonna "Coperto il" legge data_copertura.
- Import scadenza (fix codice, vale al prossimo deploy):
  * ania_importer.py: data_scadenza_emesso valida solo se STRETTAMENTE > effetto (era `< `, ora `<= ` scarta), altrimenti scadenza=effetto+frazionamento.
  * import_massivo.py: se scadenza sorgente vuota o <= effetto -> calcola da effetto+frazionamento (shared.calcola_scadenza_titolo, cache per polizza).
- Dedup import ZIP: chiave naturale ora (polizza+effetto) invece di (polizza+effetto+scadenza) -> niente doppioni quando la scadenza viene corretta.
- Endpoint bonifica dati (admin): POST /api/manutenzione/correggi-scadenze-titoli?dry_run= . (1) elimina doppioni (stesso polizza+effetto): tiene il titolo pagato/coperto o con scadenza valida, elimina i 'da incassare' non pagati e senza movimenti; (2) ricalcola scadenza=effetto+frazionamento sui da_incassare con scadenza mancante o <= effetto. Bottone UI "Correggi scadenze" (solo admin) nell'header pagina Titoli (dry-run+conferma).
- KPI Prima Nota (routes/kpi.py _stats_prima_nota): escludeva nulla -> sommava i movimenti di setup/migrazione (setup_iniziale_*, saldo_iniziale_*) e pregresso, gonfiando Entrate a ~4,9M. Ora esclude pregresso=true e categorie ^(setup_iniziale|saldo_iniziale). Verificato: Entrate € 64.103,55 (era € 4.931.920,88), Uscite € 20.796,34, Saldo € 43.307,21.
- IMPORTANTE: la bonifica dati eseguita in questa sessione ha agito solo sul DB PREVIEW (MONGO locale). In PRODUZIONE va lanciata dal bottone "Correggi scadenze" DOPO il deploy del nuovo codice.

### Sessione fork 2026-06 (8) — Bonifica globale + modalità super admin
- Bonifica eseguita sul DB PREVIEW per TUTTI i tenant: 0 titoli 'da incassare' con scadenza <= effetto rimasti. I ~476 gruppi (polizza+effetto) ancora duplicati sono record contabili LEGITTIMI (titoli incassati, storni positivo+negativo o pagamenti su date diverse) e NON vengono toccati.
- Endpoint /manutenzione/correggi-scadenze-titoli esteso: param tutti_tenant=true (solo is_super_admin) esegue su tutte le agenzie via raw_db. Bottone "Correggi scadenze" in Titoli passa tutti_tenant=true automaticamente se l'utente è super admin.
- NOTA PRODUZIONE: il DB scrivibile da questo ambiente è solo il PREVIEW (Mongo locale). Per la PRODUZIONE il super admin deve, DOPO il deploy, cliccare "Correggi scadenze" (esegue su tutte le agenzie).

### Sessione fork 2026-06 (9) — Fix KPI Titoli (Scaduti/Sospesi mostravano 0)
- routes/kpi.py _stats_titoli: prima raggruppava per stato e cercava stato=="scaduto"/"sospeso" (inesistenti) -> sempre 0.
  * SCADUTI = titoli stato da_incassare/insoluto, NON coperti (titolo_coperto!=true), con scadenza < oggi. Verificato jacopo: 9 (€2.037,05).
  * SOSPESI = titoli titolo_coperto=true non ancora incassati (anticipati dall'agenzia). Verificato: 67 (€26.554,48). Aggiunto anche il sub in €.
- Frontend Titoli: aggiunto preset "scaduti" ({stato:da_incassare, titolo_coperto:false, scaduta_giorni_oltre:0}) e rinominato "Sospesi (coperti)"; KPI Scaduti/Sospesi ora linkano ai preset corrispondenti. ACCEPTED_PRESETS aggiornato.

### Sessione fork 2026-06 (10) — Avvisi: calcolo su EFFETTO + KPI cliccabili (chi/quando)
- avvisi_scadenze.py: i "titoli arretrati" ora si basano sulla data EFFETTO (non scadenza):
  * _query_titoli_arretrati: match effetto < oggi (era scadenza < oggi), stato da_incassare/insoluto.
  * _format_titolo_record: campo "scadenza" mostrato = effetto; giorni calcolati su effetto.
- routes/kpi.py _stats_avvisi: KPI "Titoli scaduti"/"Clienti da contattare" ora basati su effetto<oggi (prima usavano stato=="scaduto" inesistente -> 0). Distinct contraenti via $lookup polizze. Verificato jacopo: Clienti 206, Titoli scaduti 264 (€85.588,42), WhatsApp inviati 5. Preview arretrati usa date effetto.
- Frontend Avvisi.jsx: KPI cliccabili -> /avvisi?storico=<canale> apre il tab "Storico avvisi inviati" filtrato per canale (mostra chi/destinatario + quando/sent_at). useSearchParams legge ?storico; StoricoAvvisiTab accetta initialCanale.

### Sessione fork 2026-06 (11) — Titoli: colonna Effetto + tutti i calcoli/filtri su DATA EFFETTO
- Frontend Titoli.jsx: aggiunta colonna "Effetto" (t.effetto) prima di Scadenza (selezionabile via "Colonne").
- KPI Titoli (routes/kpi.py _stats_titoli correnti): filtro anno + Scaduti ora su DATA EFFETTO (era scadenza). Verificato jacopo: da_incassare 481, incassati 4619, scaduti 199, sospesi 67, totale 5103.
- Preset lista /titoli ora su effetto: scaduti (scaduta_effetto=true -> effetto<oggi), scadute_oggi (effetto==oggi), scad_5g/10g/15 (scaduta_giorni_esatti -> effetto==oggi-N), scad_oltre15 (scaduta_giorni_oltre -> effetto<oggi-N), scadute_da_min/max. Aggiunto param scaduta_effetto all'endpoint. Questi param /titoli sono usati SOLO dalla pagina Titoli (Polizze usa /polizze).

### Sessione fork 2026-06 (12) — Avvisi: doppia data + fasce scaduto (effetto) + solo arretrati non inviati
- avvisi_scadenze._format_titolo_record: aggiunti campi data_effetto (=effetto) e data_scadenza (=scadenza reale). Frontend riga arretrato mostra "eff. <effetto> (Ngg fa) · scad. <scadenza>".
- Avvisi.jsx: barra di fasce (chip) su DATA EFFETTO con conteggi: Tutti / Scaduti oggi (0gg) / 5gg (1-5) / 10gg (6-10) / 15gg (11-15) / Oltre 15gg. Cliccando si filtra la lista arretrati; i pulsanti di invio esistenti (Invia avvisi + icone per riga) consentono l'invio. Card "Titoli arretrati" e conteggi ora riflettono la fascia selezionata.
- Solo arretrati NON ancora inviati: già garantito dal preview (server.py ~11848 esclude titoli presenti in storico_avvisi). Confermato: 261 non inviati.
- NOTA: implementate come chip interattive (non card KPI di navigazione) perché la KpiBar naviga via link e non filtra in-page; le chip mostrano conteggi tipo-KPI + filtrano + consentono invio.

### Sessione fork 2026-06 (13) — Performance sezione Titoli (caricamento + ricerca)
- Causa lentezza: mancavano indici su titoli.effetto (ora usatissimo per KPI/preset), titoli.id, e indici compositi tenant-scoped; la ricerca faceva regex case-insensitive NON ancorata su polizze/anagrafiche (full scan 26k/56k).
- indexes.py: aggiunti indici titoli [id],[effetto],[titolo_coperto] + compositi [agenzia_tenant_id+effetto/scadenza/stato/polizza_id]; polizze [agenzia_tenant_id+numero_polizza/contraente_id]; movimenti [titolo_id],[agenzia_tenant_id+data_movimento]. Creati in DB (ensure_indexes, 64 indici).
- server.py list_titoli ricerca: numero_polizza/targa ora regex ANCORATA a prefisso ^ SENZA case-insensitive (usa l'indice) → num polizza 1ms; ragione_sociale resta "contiene" case-insensitive (limit 500); pol_ids limit 5000.
- Risultati (tenant jacopo, 56k titoli): count effetto anno 2ms (era full-scan), search polizza 1ms. HTTP: lista 0,36s, ricerca 0,15s, KPI 0,15s.
- Tradeoff: ricerca numero polizza ora per PREFISSO (non frammento centrale) — coerente con l'uso reale (numero completo/iniziale).

### Sessione fork 2026-06 (14) — Indici globali su tutte le sezioni
- indexes.py esteso con indici compositi tenant-scoped per: anagrafiche (ragione_sociale/cognome/created_at/collaboratore), polizze (numero/contraente/scadenza/stato/compagnia/collaboratore/ramo/created_at), sinistri (stato/data_sinistro/contraente/compagnia; CORRETTO data_avvenimento->data_sinistro), movimenti/prima nota (data_movimento/categoria/tipo/conto_cassa_id/titolo_id + singoli id/polizza/anagrafica/compagnia/chiusura), allegati (entita+tenant/categoria), storico_avvisi (canale/contraente/titoli_ids), conti_cassa, whatsapp_messages, + id su tutte le collezioni principali.
- ensure_indexes: 107 indici garantiti (idempotenti, background). Creati anche in preview.
- Tempi misurati (tenant jacopo, dati reali): clienti 3ms, portafoglio 119ms, sinistri 2ms, prima nota 2ms, titoli storici 8ms, sospesi 6ms.
- In PRODUZIONE gli indici vengono creati automaticamente allo startup (ensure_indexes) dopo il deploy.

### Sessione fork 2026-06 (15) — Pulsante "Correggi scadenze (tutte le agenzie)" nel Pannello Super Admin
- Problema utente: dopo login super admin non trovava la sezione "Correggi scadenze" (esisteva solo in pagina Titoli di singola agenzia, non raggiungibile dal Pannello Super Admin per vincolo GDPR).
- Fix: SuperAdminPanel.jsx (AgenzieTab) — aggiunto pulsante "Correggi scadenze (tutte le agenzie)" accanto a Listino OpenAPI/Nuova Agenzia. Chiama POST /manutenzione/correggi-scadenze-titoli con dry_run=true&tutti_tenant=true (anteprima) → confirm → esecuzione tutti_tenant=true → toast report. data-testid=sa-bonifica-scadenze-btn. Import icona Wrench.
- Endpoint backend invariato (già supportava tutti_tenant per super admin, usa raw_db su tutte le agenzie). Verificato via curl: risponde tutti_tenant:True. In preview 0/0 (già bonificato); in PRODUZIONE mostrerà i conteggi reali.
- Flusso produzione: deploy → login super admin → click "Correggi scadenze (tutte le agenzie)" → conferma anteprima → bonifica su tutte le 7 agenzie.

### Sessione fork 2026-06 (16) — Avvisi (tabella + filtri data esatta), Import ramo/collaboratori per-tenant
**Avvisi (frontend Avvisi.jsx + backend avvisi_scadenze.py):**
- Tabella espansa per contraente ridisegnata (come da screen utente): colonne Contratto · Collaboratore (ex "Mandato", = collaboratore/agente polizza) · Compagnia · Rischio (prodotto) · Rata del (effetto) · Scad mora (effetto + termini_mora_giorni) · Copertura (data_copertura) · Ultimo avviso · Rata (importo_lordo). data-testid: titoli-table-{k}.
- Filtri a fascia ora a DATA ESATTA sulla data effetto ("Rata del"): oggi = d==0, 5gg = d==5, 10gg = d==10, 15gg = d==15, oltre15 = d>15 (prima erano intervalli).
- Filtro "Tipo pagamento" ora popolato dalla libreria Mezzi di pagamento del tenant (GET /librerie/mezzi-pagamento?attivi=true), non più lista fissa.
- Backend: _format_titolo_record arricchito (prodotto, mandato=collaboratore, collaboratore_id, mezzo_pagamento, scadenza_mora, data_copertura, ultimo_avviso). cerca_scadenze ora carica cache users + campi polizza (prodotto, collaboratore_id, termini_mora_giorni). Fix latente: i filtri collaboratore_id/mezzo_pagamento del preview ora funzionano (prima i campi mancavano nel record).
- Verificato su tenant Axicura (264 arretrati): mandato/prodotto/scad mora popolati; chip 261/0/14/12/8/98; tabella espansa OK (screenshot).

**Import ramo per-tenant (ania_importer.py + routes/librerie.py):**
- POST /librerie/rami/riassegna-codici ora: (1) riassegna polizze/sinistri/prodotti al NOME del ramo master (elimina doppioni tipo "RC AUTO"/"RC Auto"); (2) PERSISTE un import_mapping per-tenant (tipo=ramo, flusso=omnia, valore_flusso=codice → entita_id=master) così gli import OMNIA futuri convertono in automatico i codici grezzi (3D, 3N, TUT…). Verificato: mapping creato e tenant-scoped.
- _get_or_create_ramo ora ritorna il NOME del ramo di destinazione (seguendo unito_in_ramo_id) invece del codice grezzo.
- /librerie/rami/codici-usati: in_libreria ora fa match su codice O nome.

**Collaboratori importati (server.py merge_users):**
- Lo strumento esistente "Unisci utenti / collaboratori" (Librerie → tab Utenti) ora, quando la sorgente è uno stub importato (auto_created_from_codice), PERSISTE un import_mapping (tipo=collaboratore, flusso=omnia, codice → collaboratore reale) + aggiorna mapping_operatori legacy. Così i prossimi import OMNIA usano il collaboratore reale invece di ricreare "Produttore - 0xx". Le referenze (polizze/titoli/movimenti/clienti) sono già riassegnate dal merge esistente e lo stub viene disattivato.
- L'utente esegue le unificazioni (024→BS BROKER, 021, er) dal dialog scegliendo destinazione.

Nota preview DB: password di jacopo@schiantarelli.it impostata temporaneamente per test UI e RIPRISTINATA all'originale.

### Sessione fork 2026-06 (17) — Regolazione Premio: dovuto a 0 se consuntivo < preventivo
- Regola richiesta: se il "Dato aggiornato cliente (consuntivo)" è INFERIORE al "Dato di polizza (base preventivo)" → differenza negativa → il Dovuto cliente = 0 (la regolazione premio non genera rimborsi a credito).
- Backend routes/extras_p1p2.py calcola_regolazione: quando differenza < 0 (modalità differenziale) azzera premio_calcolato, premio_netto, imposta, dovuto. La differenza resta visibile (negativa, informativa).
- Frontend RegolazionePremioDialog.jsx: anteprima live premioLive=0 quando differenza<0 (coerente con backend).
- Verificato via curl su polizza reale: consuntivo inferiore (140000→69558) → diff -70442, premio 0, DOVUTO 0; consuntivo superiore (140000→200000) → diff +60000, DOVUTO 605,87.

### Sessione fork 2026-06 (18) — Regolazione a credito (flag) + titolo a importo 0/negativo + redeploy
- Titolo regolazione generabile anche con importo 0 (backend regolazione_premio.py genera_titolo: blocca solo importo None; negativo consentito solo se polizza.regolazione_a_credito=True). Frontend RegolazionePremio.jsx: validazione permissiva (blocca solo vuoto/NaN).
- Nuovo flag per-polizza regolazione_a_credito: nel calcolo (extras_p1p2.py) se attivo NON azzera gli importi negativi (dovuto negativo = rimborso al cliente); se non attivo resta la regola "consuntivo<preventivo → dovuto 0". Body calcola accetta a_credito, persistito su polizza al salvataggio; risultato include a_credito.
- Frontend RegolazionePremioDialog.jsx: checkbox "Consenti regolazione a credito" (init da polizza.regolazione_a_credito, data-testid reg-a-credito), anteprima live rispetta il flag, invia a_credito.
- Verificato via curl: a_credito=true + consuntivo inferiore → dovuto -711,31; genera-titolo importo -711,31 → 201. Dati di test ripuliti; password preview di jacopo ripristinata.
- REDEPLOY avviato (job c34290d2) per pubblicare sessioni 16/17/18.

### Sessione fork 2026-06 (19) — Eliminazione singola regolazione calcolata
- Nella tab Regolazione della polizza (RegolazionePolizzaTab.jsx), tabella "Regolazioni calcolate": aggiunte checkbox per riga + "seleziona tutte" + pulsante "Elimina selezionate (N)" per eliminare singoli calcoli dallo storico (non più solo "Elimina regolazione" che azzera tutto). data-testid: reg-calcoli-check-all, reg-calcolo-check-{i}, reg-elimina-selezionate.
- Backend extras_p1p2.py: nuovo DELETE /polizze/{pid}/regolazione-premio/storico/{sid} (require admin/collaboratore) — elimina una singola voce di regolazione_storico. Verificato via curl (2→elimina 1→1, HTTP 200). Il pulsante "Elimina regolazione" (azzera tutta la regolazione + eventuale titolo) resta disponibile.
- NB: richiede un nuovo deploy per andare online.

### Sessione fork 2026-06 (20) — Sostituzione polizza (tipo titolo + cronologia + link) e titolo di sospensione
**Sostituzione (server.py, PolizzaDetail.jsx):**
- create_polizza: il PRIMO titolo automatico è tipo="sostituzione" se la polizza ha sostituisce_polizza (prima "nuova"). Verificato via curl.
- Cronologia titoli catena: GET /polizze/{id} già caricava i titoli delle polizze sostituite, ma la risoluzione della catena e sostituisce_numero usavano solo l'ID; i dati reali salvano il NUMERO polizza in sostituisce_polizza → catena rotta. Fix: risoluzione per id O numero (find_one $or id/numero_polizza) sia per sostituisce_numero sia per il chain-walk. Aggiunto doc.sostituisce_polizza_id (id risolto). I titoli storici hanno polizza_origine_numero (colonne invariate, riga evidenziata ambra). Verificato: catena 183629775→183629412 mostra 3 titoli con origine corretta.
- Link "Sostituisce" ora punta a /polizze/{sostituisce_polizza_id||sostituisce_polizza}.

**Sospensione (server.py sospendi_polizza, AzioniPolizzaTab.jsx):**
- Alla sospensione il frontend chiede (window.confirm) se creare in automatico il "titolo di sospensione". Se sì passa crea_titolo=true.
- Backend crea Titolo tipo="sospensione" (nuovo valore aggiunto al Literal in db_models.py), effetto=scadenza=data_sospensione, importo 0, stato="incassato" (fuori da avvisi/arretrati), nota "Sospensione dal {data}". Verificato via curl.
- _TIPO_COD estratto conto: aggiunto "sospensione":"SP".

### Sessione fork 2026-06 (21) — Ritenute da versare + causali standard in libreria con toggle attivo
- Mini bilancio: nuova voce di COSTO "Ritenute Versate" (cervello.py _MB_AUTO_COSTI + _mb_classify categoria 'ritenute_versate'). Verificato: movimento categoria=ritenute_versate → mini bilancio "Ritenute Versate".
- MovimentoContabile.categoria (db_models.py): aggiunte "ritenuta_compagnia" e "ritenute_versate" al Literal.
- Causali STANDARD ora in libreria "Voci di bilancio": VoceBilancio ha nuovi campi categoria_sistema + is_sistema. _ensure_causali_sistema() (librerie.py) le semina lazy per-tenant alla list (idempotente, tenant-scoped; NB: NON usare model_dump con agenzia_tenant_id nel $setOnInsert, va poppato per lasciar iniettare il tenant). 13 causali di sistema.
- Contabilita.jsx "Nuovo movimento contabile": dropdown Categoria/Voce di bilancio ora guidato dalla libreria (solo voci attive), raggruppato RICAVI/COSTI. Le causali di sistema si salvano su `categoria` (cat:{categoria_sistema}) preservando la logica contabile; le custom su voce_bilancio_id. Disattivando una voce in Librerie→Voci di bilancio sparisce dal dropdown.
- _mb_compute: esclude le voci con categoria_sistema dalle righe custom (evita duplicati vuoti). Verificato via screenshot dropdown + curl.

Sessione (20) aggiunta: badge colorato tipo titolo (sostituzione/sospensione/ripresa/storno) in PolizzaDetail Titoli; riattivazione polizza chiede se creare "titolo di ripresa" (tipo=ripresa, importo 0, data ripresa). Verificati via curl.

### Sessione fork 2026-06 (22) — "Ritenute da versare" collegate al riquadro DEBITI
- cervello.py mini-bilancio: il riquadro DEBITI ora mostra Ritenute d'Acconto MATURATE (somma movimenti.ritenuta_acconto) − VERSATE (somma movimenti categoria=ritenute_versate) = DA VERSARE all'Erario (residuo, clamp a 0). Nuovi campi restituiti: ritenute_maturate, ritenute_versate, ritenute_erario(=residuo).
- MiniBilancioTab.jsx: 3 righe nel pannello DEBITI (maturate, − di cui versate, = Ritenute da versare Erario in grassetto). data-testid: mb-ritenute-maturate, mb-ritenute-versate, mb-ritenute-erario.
- Verificato via curl: versamento ritenute_versate 40 → versate 40, residuo netto.

### Sessione fork 2026-06 (22b) — Correzione: ritenute versate = COLLABORATORI, non compagnia
- L'utente ha chiarito: i movimenti "Ritenute da versare" sono ritenute d'acconto versate PER I COLLABORATORI, non verso la compagnia.
- cervello.py: annullato il netting errato sulle ritenute compagnia. Ora ritenute_erario = solo ritenuta_acconto (compagnia, invariato) + nuovo campo separato ritenute_collaboratori = somma movimenti categoria=ritenute_versate.
- MiniBilancioTab.jsx pannello DEBITI: due righe distinte — "Ritenute d'Acconto & Erario (compagnia)" e "Ritenute d'Acconto v/Collaboratori" (data-testid mb-ritenute-collaboratori). Verificato via curl: compagnia 0, collaboratori 55.

### Sessione fork 2026-06 (23) — % Sistema Provvigionale visibile in Estratto Conto Collaboratori
- Problema: le % caricate in Librerie→Sistema provvigionale (schema_provvigionale) non comparivano nell'estratto conto (mostrava 0%) perché header/sidebar leggevano solo users.perc_provvigione_default (a 0).
- Fix (server.py): nuovo helper _perc_provv_effettiva(cid) che risolve la % dallo schema generico del collaboratore (fallback: qualsiasi suo schema attivo; ordine percentuale_collaboratore → su_premio_netto → su_premio). Arricchisce sia GET /collaboratori (sidebar) sia /collaboratori/{cid}/estratto-provvigioni (header) quando il profilo utente è a 0.
- Verificato su tenant Axicura: sidebar mostra BS BROKER 4.5%, SALVADORI 50%, MARCHESI/BUZZETTI/MOIOLA/OREGIONI/PRUNERI 70%; header estratto MARCHESI = 70%. (MIDA BROKER resta 0% perché non ha schema configurato.)
- Nessuna modifica frontend (Provvigioni.jsx già legge perc_provvigione_default).

### Sessione fork 2026-06 (24) — Titolo di sospensione = da_incassare (non auto-incassato)
- server.py sospendi_polizza: il titolo di sospensione ora nasce stato="da_incassare" (rimosso stato="incassato" + data_incasso). Resta nei Titoli arretrati per registrazione manuale. Verificato via curl (stato da_incassare, data_incasso None, lordo 0).
- Il titolo di ripresa (riattivazione) resta invariato per ora.

### Sessione fork 2026-06 (25) — Incasso: gestione ECCEDENZA (cliente paga più del premio)
- server.py incassa_titolo: nuovo calcolo eccedenza = max(0, importo_pagato − lordo); l'entrata "incasso_premio" ora registra min(pagato, lordo) (premio), e l'eccedenza è gestita a parte via body.gestione_eccedenza:
  - "maggiorazione" (default): movimento entrata separato categoria "altro" per l'eccedenza (entra in Prima Nota).
  - "credito": movimento "altro" con quota_credito + nuovo Titolo credito (importo_lordo negativo, da_incassare) a favore del cliente.
- DialogIncasso.jsx: sezione "Eccedenza" (simmetrica a Residuo) con RadioGroup maggiorazione/credito, visibile quando importo_pagato > premio. data-testid: eccedenza-section, ecc-maggiorazione, ecc-credito, dlg-eccedenza.
- Verificato via curl: pagato 124 su premio 122 → incasso_premio 122 + movimento altro 2 (maggiorazione).

### 2026-06-15 — FIX Margine provvigioni (server.py `_provv_breakdown`)
- Regola confermata utente: "margine = provvigioni totali − provvigione collaboratore SEMPRE".
- Bug precedente: per schemi "% su premio netto" (es. BS BROKER 4,5%) con percentuale_collaboratore=0 il codice impostava pct_collab=100 → collab prendeva il 100% del totale → margine 0.
- FIX: `_provv_breakdown` ora calcola la quota collaboratore tramite `_quota_collab_da_schema` (netto × %netto per schemi sul netto; %collab × totale per schemi di ripartizione). Aggiunti parametri `premio_netto`/`premio_lordo` propagati dai 3 chiamanti (dettaglio polizza, titoli catena polizza, lista titoli). margine = tot − collab sempre. La % mostrata (provvigione_pct_collab) espone la %netto (4,5) invece di 100.
- Verificato con l'esempio utente: netto 100, tot 10, BS 4,5% → collab 4,50, margine 5,50 ✅.
- ATTENZIONE: sui titoli reali BS il campo `provvigioni` (totale) è ancora quello vecchio/basso (es. 6,37) < quota collab (netto×4,5%), quindi margine risulta negativo finché non si esegue il RICALCOLO titoli esistenti (endpoint `/provvigioni/riassegna`) — step dedicato già previsto.

## 2026-09-28 — Tabella Polizze anagrafica: nuove colonne + ordinamento
- Aggiunte colonne "Prodotto", "Targa" e "Oggetto assicurato" alla tabella Polizze in `AnagraficaDetail.jsx` (PolizzeTab). Targa/Oggetto in fondo dopo Premio.
- Header cliccabili con freccetta per ordinare per qualsiasi colonna (asc/desc), niente persistenza.
- Ricerca estesa anche a targa/oggetto. I campi arrivano già dal backend /polizze (projection non li esclude).
- Verificato via seed temporaneo + screenshot (poi rimosso).

## 2026-09-28 — Fix utenti multi-tenant + Rivalsa contabile + rename PNT
- BUG create utenti (`server.py` create_user): ora assegna `agenzia_tenant_id` dell admin (assign_tenant) e ADOTTA nella propria agenzia un account con stessa email rimasto orfano nel tenant principale (recupero account tipo marco@schiantarelli.it). Testato via API.
- Brogliaccio: colonna "PNC" rinominata in "PNT" (`BrogliaccioTab.jsx`, label; key resta pnc).
- Rivalsa (movimento categoria=pnc, tipo_pnc=rivalsa): ora mostrata anche in colonna SPESE del Brogliaccio (`_compute_brogliaccio`) e riclassificata in Mini Bilancio sotto "Storni Provvigionali / Rivalse" invece di Spese Generali (`routes/cervello.py` _mb_classify + projections). Altri tipi PNC restano in Spese Generali. Testato via API.
- NB: fix backend richiedono nuova pubblicazione per essere attivi in produzione.

## 2026-09-28 — Incentivazioni: sostituzioni + Riepilogo Collaboratori
- Sostituzioni (`incentivazioni.py` calcola): per una polizza con campo `sostituisce_polizza` la base incentivabile = premio netto nuovo annualizzato − premio netto sostituito annualizzato (delta anche negativo). Risoluzione riferimento per id o numero_polizza. Aggiunto `polizze_sostituzioni` in risposta.
- Riepilogo Collaboratori: nuova sezione consolidata (produzione netta per campagna + totale, quota % sul totale, incentivo, incentivo ripartito) in `Incentivazioni.jsx`. Backend restituisce `collaboratori` e `produzione_grand_total`.
- Ripartizione manuale: campo per campagna `incentivo_reale` (incentivo realmente incassato dall agenzia) ripartito tra collaboratori in proporzione alla produzione; mostrato accanto all incentivo automatico (produzione x aliquota).
- Testato via API+screenshot: sostituzione delta 400, DNA additivo BASE+PERSONA=680, ripartizione 1000 -> 416,67/583,33, riepilogo quota 68.2%/31.8%.

## 2026-09-29 — Titoli sostituzione/storno + Import operatore agenzia
- Import (import_massivo.py): polizze/titoli senza operatore nel flusso ora attribuiti allagenzia (admin agenzia, preferenza email jacopo@schiantarelli.it, fallback admin del tenant). Solo nuovi record in import.
- Import: se la polizza ha sostituisce_polizza, il titolo importato diventa tipo=SOSTITUZIONE; i titoli in arretrato (da_incassare/insoluto/sospeso) della polizza sostituita vengono stornati (stato=stornato) in un pass finale. Aggiunto stat titoli_stornati_sostituzione.
- Nuovo endpoint POST /titoli/{tid}/storna: storno manuale solo per titoli in arretrato -> stato stornato (nessun movimento Prima Nota). 400 se incassato/stornato.
- Frontend PolizzaDetail: pulsante storno manuale (icona ⊘) accanto ai titoli in arretrato.
- Testato: endpoint storna (arretrato ok / incassato 400), import in tenant reale c5ae2d0e (operatore=jacopo, titolo=sostituzione, arretrato precedente stornato), UI storno end-to-end.

## 2026-09-29 — Brogliaccio: rappel in SALDO negativo
- _compute_brogliaccio (server.py): i movimenti rappel (categoria "rappel" o flag is_rappel) ora vanno in colonna SALDO in negativo (-importo) e colonna Rappel (+importo), NON piu tra le Spese/"avere". Coerente con lincasso rappel standard.
- KPI cumulativo: categoria "rappel" conteggiata in cum_rappel (riduce saldo cassa), non piu come spesa.
- Testato via API: rappel 32,07 -> saldo -32,07 / rappel 32,07 / spese 0.

## 2026-09-29 — Fix Saldo Cassa Compagnie: eccedenza inclusa (gap 1,99)
- Causa: incasso con eccedenza a credito salva quota_credito NEGATIVO (-ecc). _compute_saldi_compagnie (Brogliaccio/Riepilogo) sottraeva quota_credito -> escludeva leccedenza (saldo piu basso), mentre lestratto (_compagnia_estratto_data) la includeva. Gap = eccedenza (es. 1,99).
- Fix (server.py _compute_saldi_compagnie): la somma incassi ora usa max(quota_credito,0): i residui (quota_credito positivo) restano normalizzati al premio, le eccedenze (negativo) NON vengono piu sottratte -> incluse nel saldo cassa. Ora Brogliaccio == Estratto.
- Testato: eccedenza inclusa (91,99), residuo invariato (90), nessuna regressione.

## 2026-09-29 — Statistiche: filtro Ramo (uno/piu/tutti)
- Aggiunto multi-select "Ramo" in Premi/Provvigioni e Per Operatore (statsShared.jsx RamoMulti; popover con checkbox + "Tutti i rami"). Rami da /librerie/rami?dedup=1&con_polizze=1.
- Frontend passa ramo=comma-list agli endpoint /statistiche/premi-provvigioni e /statistiche/per-operatore.
- Backend: match ramo reso case-insensitive/trim (rami_norm) in entrambi gli endpoint.
- Testato: no ramo=1500, RC AUTO=1000, multi=1500, case-insensitive ok; UI dropdown verificata.

## 2026-06 — Card documenti: icona, riordino drag&drop, obbligatorietà
- Librerie → tab "Visibilità documenti" (VisibilitaDocSezione): per ogni card documento (default + custom) ora si può: scegliere un'ICONA emoji (EmojiPicker: griglia + carattere libero), contrassegnarla OBBLIGATORIA (toggle AlertTriangle), e RIORDINARE le card via drag&drop (framer-motion Reorder.Group/Item + dragControls/GripVertical). Vale per tutte e 3 le sezioni: anagrafica, polizza, sinistro.
- Backend (server.py): CARD_DEFS arricchito con `icon`; nuovo helper `_build_card_list` (merge default+custom, applica override icon/obbligatoria/ordine, ordina). GET /api/config/card-visibilita ritorna icon/obbligatoria in ordine. PUT /api/config/card-visibilita accetta per entità {key:bool} + chiavi speciali `_meta`:{key:{icon,obbligatoria}} e `_ordine`:[keys] → salva card_meta e card_ordine in azienda_config (tenant-scoped). POST /api/config/card-custom accetta icon+obbligatoria. DELETE pulisce anche meta/ordine.
- Dettagli: DocumentiSezioneSplit (Polizza/Sinistro, layout quadrotti) ora guidato dalla config per ordine/icona/obbligatorietà; QuadrottoCategoria evidenzia in ROSSO (bordo + banner "Documento obbligatorio mancante", data-testid quadrotto-manca-<key>) le card obbligatorie senza file. AnagraficaDetail DocumentiTab applica config a DOC_TIPI_ANAG (icona/ordine) ed evidenzia red + badge "obbligatorio mancante" (doc-manca-<key>).
- Fix UX: addCard non ricarica più tutta la cfg (perdita modifiche non salvate) ma fa merge locale del nuovo item dalla risposta POST; delCard rimuove localmente.
- Testato (iteration_101): tutti i flussi UI OK su admin (polizza) e jacopo@schiantarelli.it (sinistro/anagrafica); icona/obbligatoria/ordine persistono; evidenziazione rossa nei 3 dettagli verificata.

## 2026-06 — Fix multipli (date, riepilogo mancanti, ricerca sospesi, provvigionale per compagnia)
- Date collegate Incasso/Copertura (DialogIncassoCopertura.jsx): "Data Copertura" è la data GUIDA; modificandola si aggiornano a cascata Comunicazione incasso, Data Contabile, Data Pagamento, Data Co.Ge. Le singole restano modificabili dopo. onChangeDataCopertura.
- Riepilogo documenti obbligatori mancanti: banner rosso in cima alla sezione Documenti (DocumentiSezioneSplit → componente RiepilogoMancanti per polizza/sinistro; AnagraficaDetail DocumentiTab per anagrafica) con conteggio + elenco card obbligatorie senza file (data-testid riepilogo-mancanti / riepilogo-mancante-<key>).
- Ricerca per importo nei Sospesi (TitoliSospesi.jsx): la barra Cerca ora filtra anche per importo da pagare (formati '1302' e '1302,00'), oltre al testo. Placeholder aggiornato.
- FIX provvigionale per compagnia (BUG importante): la ripartizione nel TitoloDialog usava sempre il PRIMO schema del collaboratore ignorando la compagnia (quotaCollaboratore faceva GET /librerie/schema-provvigionale?collaboratore_id=... e prendeva schemi[0]). Inoltre i titoli NON portano compagnia_id (solo compagnia_nome), quindi il parametro compagnia non era passato. Fix: nuovo endpoint GET /api/provvigioni/quota-collaboratore (usa _provv_breakdown, risoluzione schema compagnia-aware); TitoloDialog ora cattura compagnia_id/ramo dalla POLIZZA (stato provvCtx) e li passa. Provato via curl: BS BROKER su CATTOLICA → 29.04 (4.5% netto), su UCA → 159.99 (98% provv). Testato UI iteration_102 (100%).
- PENDING (non ancora implementati): (a) PNC/partite (rappel/ritenute_compagnia/pnc) NON versate non devono influire sul saldo Estratto Conto Compagnie ma restare visibili/selezionabili ("in arretrato"); l'effetto sul saldo arriva al versamento — logica contabile delicata, da implementare con cautela in _compagnia_estratto_data (righe 1472-1560 server.py). (b) Upload in Background su Documenti dettagli + Regolazione Premio + Libro Matricola. (c) Alert Documenti automatici (digest). 

## NOTA TERMINOLOGIA (2026-06) — "PNC" → "PNT"
- L'utente ha comunicato che "PNC" è diventato "PNT". Nel menu "PARTITE" le partite sono: Rappel, Ritenute, PNT (ex PNC).
- A livello DATI/codice resta la collection `pnc` e i tipi (rivalsa/cassa_agenti/fondo_pensione/gruppo_agenti); la ridenominazione riguarda l'ETICHETTA utente (PNC → PNT). Da confermare se applicare il rename anche nelle label UI.
- Pending correlato: le partite PNC/PNT NON versate non devono influire sul saldo Estratto Conto Compagnie (restano "in arretrato"), effetto al versamento.

## 2026-06 — Rename UI PNC → PNT (FATTO)
- Rinominate TUTTE le etichette visibili "PNC" → "PNT": pagina Pnc.jsx (titolo "Partite PNT", "Nuova PNT", "Totale PNT", dialog, toast, messaggi), badge Estratto Conto (EstrattoContoCompagnie.jsx), Sidebar (sezione "Partite PNT"), descrizioni backend in _compagnia_estratto_data e _voce_net_descr (server.py), label _VOCE_LBL, messaggi errore e descrizione movimento in routes/commerciale.py ("Tipo PNT non valido", "PNT non trovata", descrizione Prima Nota "PNT ..."). BrogliaccioTab mostrava già "PNT".
- INVARIATI (interni): collection `pnc`, route `/pnc`, chiave sezione `partite_pnc`, campo `tipo`/`tipo_pnc`, categoria movimento `pnc`, identificatori PNC_TIPI/PNC_TIPO_LABEL/_PNC_LBL.
- Verificato via screenshot: pagina /pnc mostra "Partite PNT", nessun "PNC" visibile.

## 2026-06 — Partite PNT/Rappel/Ritenute "in arretrato" (FATTO)
- In _compagnia_estratto_data (server.py): una partita (rappel / ritenuta_compagnia / pnc) incide sul SALDO Estratto Conto Compagnie SOLO quando è VERSATA. Finché è in arretrato resta in `righe` (visibile/selezionabile) ma NON tocca totale_dare/avere/saldo. Helper `_voce_versata(x)` = saldata_compagnia OR stato in (versata/versato/incassato/saldato/pagato) OR movimento_pagamento_id OR movimento_id. Il campo riga "saldata" ora riflette lo stesso check (coerenza con frontend EstrattoContoCompagnie: altreVoci = !saldata).
- Effetto al versamento: rappel incassa → stato=incassato+movimento_id → conteggiato; pnc versa_pnc → stato=versata+movimento_id; bulk E/C paga_compagnia → saldata_compagnia+movimento_pagamento_id. Nessun doppio conteggio (i movimenti "provvigioni"/"pnc" generati non sono nella sezione pagamenti dell'E/C che conta solo categoria 'pagamento_compagnia').
- Verificato via curl (tenant jacopo, CATTOLICA): rappel 300€ non versato → saldo invariato 51501.22, riga visibile saldata=False; dopo /rappel/incassa → saldo 51201.22, saldata=True. Baseline ripristinato dopo cleanup.
- NB: ritenute_compagnia e pnc compaiono in E/C solo per compagnie con tipo_mandato="diretto" (comportamento preesistente, non modificato).

## 2026-06 — KPI Brogliaccio congelate alla chiusura giorno (FATTO)
- PROBLEMA: le KPI del Brogliaccio/Prima Nota (barra ENTRATE/PROVVIGIONI/SOSPESI/RIMESSE/SCONTI/SPESE/SALDO CASSA CMP, RIEPILOGO CONTI, LIQUIDITÀ, SALDO CASSA PER COMPAGNIA) erano ricalcolate live → guardando un giorno passato mostravano valori attuali e "cambiavano" (es. sospesi).
- ROOT CAUSE: `chiudi_giorno` salvava lo snapshot in chiusure_giorno.riepilogo, ma `_compute_brogliaccio` lo IGNORAVA e ricalcolava sempre live.
- FIX (server.py): (A) `chiudi_giorno` ora salva nel riepilogo anche `liquidita` e `saldi_compagnie` (oltre a totali_giornata/riepilogo_kpi/conti_riepilogo già presenti). (B) `_compute_brogliaccio`: se la giornata è CHIUSA (non riaperta) e ha snapshot, OVERRIDE di riepilogo_kpi/conti_riepilogo/totali_giornata/liquidita/saldi_compagnie con i valori salvati; aggiunto campo risposta `snapshot: true`.
- Verificato via curl (giornata chiusa 2026-09-14): snapshot=True, KPI mostrato = KPI salvato (crediti 25120.44 congelato). Le giornate già chiuse beneficiano subito del freeze KPI/conti; liquidità e saldo cassa compagnie si congelano dalle nuove chiusure in poi (gli snapshot vecchi non li contengono → fallback live solo per quelle storiche). Nessuna modifica frontend necessaria.

## 2026-06 — Fix filtro "Rata / decorrenza" nelle Statistiche (FATTO)
- PROBLEMA: nelle Statistiche (tab Per Operatore e Premi/Provvigioni) il filtro data "Rata / decorrenza" (data_field="rata") usava il campo titolo `scadenza`, che nei dati reali è quasi sempre VUOTO → i titoli venivano scartati e i totali risultavano incompleti.
- FIX (server.py, endpoint /statistiche/per-operatore e /statistiche/premi-provvigioni): mapping "rata" ora → `effetto` (la decorrenza del titolo), che è il campo valorizzato e corretto. ("incasso"→data_incasso, "copertura"→data_copertura invariati.)
- Verificato via curl (tenant jacopo, 2025): data_field=rata ora dà tot_netto≈3.783.841 / provv≈202.885, coerente con incasso/copertura (prima ~0). Backend-only, nessuna modifica frontend.

## 2026-06 — Cambio contraente della polizza (FATTO)
- EditPolizzaDialog (PolizzaDetail.jsx) tab Anagrafica: aggiunto campo "Contraente" con IntestatarioAutocomplete (cerca anagrafiche, collega/scollega, crea al volo). Al salvataggio invia contraente_id (contraente_nome escluso dal payload perché è un campo display derivato).
- Backend: nessuna modifica necessaria — update_polizza fa $set di contraente_id; contraente/contraente_nome sono sempre derivati a runtime da contraente_id (join anagrafiche) in tutte le viste (polizza, titoli, estratto conto), quindi il cambio si propaga ovunque senza denormalizzazione.
- Verificato: PUT contraente_id → GET riflette nuovo contraente; UI dialog mostra campo con badge "collegato". Testato su tenant jacopo.

## 2026-06 — Chat interna: nascondere stub "Produttore" inattivi (FATTO)
- PROBLEMA: in Centro Comunicazioni → Chat interna comparivano i "Produttore - XXX - ..." (utenti stub auto-creati all'import, attivo=False, auto_created=True, email @import-auto.local), anche dopo averli associati/mappati a un collaboratore reale. Lo stub resta in db.users dopo la mappatura.
- FIX (server.py, GET /chat/utenti): aggiunto filtro `attivo: {$ne: False}` a entrambi i rami (cliente e staff) → esclude stub import e qualunque account disattivato dai contatti chat (utenti senza campo attivo o attivo=True restano visibili).
- Verificato via curl (tenant jacopo): 0 stub Produttore e 0 inattivi nella lista chat (18 contatti reali). Backend-only, nessuna modifica frontend.

## 2026-06 — Ricerca + filtro date in Ritenute/Rappel/PNT (FATTO)
- Nuovo componente riutilizzabile /app/frontend/src/components/RicercaDateBar.jsx (campo Cerca + Dal/Al con DateInputIt GG/MM/AAAA) + helper applyRicercaData(items,{q,dal,al}) che filtra per testo (compagnia/descrizione/note/tipo/anno/importo) e intervallo date sul campo `data`.
- Collegato a: Pnc.jsx (PNT), Rappel.jsx, RitenuteCompagnia.jsx (tab Ritenute Compagnia). Filtro client-side applicato prima di sort e totali KPI. data-testid: pnc-/rappel-/ritc- + -search/-dal/-al/-clear.
- Verificato via screenshot su Ritenute Compagnia: barra presente e funzionante (ricerca azzera lista/totali). Rappel e PNT usano lo stesso componente (compile OK).
- NON incluso: tab "Ritenute Collaboratori" (Ritenute.jsx) e "Ritenute Agenzia Partner" (FattureAgenziaPartner.jsx) hanno strutture dati diverse — da aggiungere se richiesto.

## 2026-06 — Ricerca negli altri tab Ritenute + Pulizia stub Produttore (FATTO)
- RICERCA+DATE estesa a: Ritenute Collaboratori (Ritenute.jsx, testid rit-collab-*) e Fatture Agenzia Partner (FattureAgenziaPartner.jsx, filtra lista `fatture`, testid fat-part-*). Helper applyRicercaData esteso con campi agenzia_partner_nome/fornitore_nome/partner_nome/ragione_sociale/causale/numero/numero_fattura. Ora tutti e 3 i tab Ritenute + Rappel + PNT hanno Cerca + Dal/Al.
- PULIZIA STUB PRODUTTORE: nuovo endpoint POST /api/librerie/stub-operatori/pulisci (admin, param dry_run). Elimina SOLO gli stub auto_created già mappati (merged_into impostato, oppure mapping_operatori per auto_created_from_codice che punta a un collaboratore reale non-stub). Prima di eliminare ri-punta i riferimenti residui (collaboratore_id su _MERGE_USER_COLLECTIONS, provvigioni_operatori annidati in polizze/titoli, rete parent) sul target — stessa logica di /auth/users/merge. Gli stub NON mappati vengono saltati (nessuna cancellazione accidentale). Pulsante in Librerie → Mapping Operatori: "Pulizia stub Produttore" (testid lib-pulisci-stub) con anteprima (dry_run) + conferma.
- Verificato: dry-run su jacopo → 3 stub, 0 eliminabili (non mappati), 3 saltati → safety OK. Deletion reuse della logica merge collaudata.


## 2026-10-13 — Link portale cliente canonico (Railway dominio unico)
- FIX portale cliente: `_portale_link_per_ana` (server.py ~17196) usa il ramo
  sottodominio SOLO se `BASE_APP_DOMAIN` è impostato (vero wildcard). Altrimenti usa
  `PUBLIC_BASE_URL` → link canonico `https://<host>/c/{slug}`. Evita link con
  sottodominio inesistente quando non c'è un dominio custom. MANTENUTO.
- Login per-agenzia path-based (`/{slug}/login` + branding + endpoint
  public/agenzia-branding + dialog super-admin path-based): IMPLEMENTATO e poi
  RIMOSSO su richiesta utente — Railway non ha ancora un dominio privato. Login resta
  INVARIATO per tutti. Da riprendere quando l'utente acquisterà il dominio privato
  (allora: DNS wildcard o path-based + BASE_APP_DOMAIN).
- Nota: per link portale ASSOLUTI serve `PUBLIC_BASE_URL` su Railway; senza, il link
  resta relativo `/c/{slug}` (comportamento attuale).


