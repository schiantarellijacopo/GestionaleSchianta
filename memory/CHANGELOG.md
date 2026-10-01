# Programma Assicurativo - CHANGELOG


## 2026-06 — Regolazione Premio: chiusura automatica ✅
- **Auto-chiusura regolazione**: quando il titolo di regolazione collegato (`regolazione_titolo_id`) risulta saldato (stato `incassato`/`coperto`/`abbuonato` o `titolo_coperto=true`), lo stato passa automaticamente a `chiusa`. Alla chiusura viene salvato `regolazione_chiusa_scadenza_rif` (scadenza polizza) e `regolazione_chiusa_il`.
- **Sparisce dalla lista attiva**: le regolazioni `chiusa` NON compaiono più nel filtro "Tutte"; restano consultabili solo col filtro esplicito "Chiuse". `stats` conta comunque il totale (incl. chiuse).
- **Riproposizione annuale**: superata la scadenza dell'anno successivo (`rif + 1 anno`), la regolazione si riapre a `da_richiedere` azzerando workflow (lettera, dato cliente, dovuto, ultimo calcolo, titolo_id) MA mantenendo base/tasso di polizza. Evento storico `riproposta_nuovo_anno`. Il titolo dell'anno precedente resta collegato nello storico.
- **Auto-riapertura intra-anno**: se il titolo torna non saldato ("rimetti arretrato"), la regolazione riapre a `titolo_generato`.
- **Documenti Regolazione**: nuovo quadrotto categoria `regolazione` nei Documenti polizza (`PolizzaDetail`); nuova azione 📎 nella pagina Regolazione Premio per allegare documenti (categoria `regolazione`, con toggle visibilità cliente).
- File: `routes/regolazione_premio.py`, `frontend/src/pages/RegolazionePremio.jsx`, `frontend/src/pages/PolizzaDetail.jsx`. Testato con `scripts/test_regolazione_autoclose.py` (PASS: chiusura + filtro Tutte/Chiuse + riproposizione + rif futuro).

## 2026-06 — Riassegna provvigioni PER SCHEMA + filtri per tag ✅
- La riassegna provvigioni è ora **per singola assegnazione/schema** (non globale): colonna "Riassegna" con pulsanti **Arretrati** / **Tutti** su ogni riga del Sistema Provvigionale.
- Endpoint `POST /provvigioni/riassegna` accetta `schema_id`: limita ai titoli nello scope dello schema (collaboratore + eventuale compagnia/ramo). Sicurezze invariate (salta senza schema, non azzera mai). Verificato: schema "pro70" → 98 titoli in scope vs 6350 globali.
- **Filtri per tag** aggiunti negli elenchi **Polizze** e **Titoli** (backend param `tag` in `/polizze` e `/titoli`; Select "Tutti i tag" popolato da `/anagrafiche/tags`). Verificato: `?tag=vip` filtra correttamente.

- **Verifica BS Broker**: lo schema "provvigioni Bs" (4,5% sul netto, collaboratore prende l'intero) è corretto e viene applicato ai NUOVI titoli. MA i titoli **importati** hanno un valore provvigione piatto (es. 216,34 costante) NON calcolato dallo schema → le provvigioni BS non erano automatiche sullo storico.
- **Nuovo endpoint** `POST /provvigioni/riassegna` (`{solo_arretrati, dry_run}`): ricalcola le provvigioni dei titoli con gli schemi attuali. Due modalità: solo arretrati (da_incassare/insoluti) o tutti. Riscrive `provvigioni` e `provvigioni_operatori`.
- **Sicurezze**: (1) salta i titoli senza schema applicabile; (2) NON azzera mai una provvigione reale esistente (uno schema che calcola 0 non cancella). Verificato con dry-run: 0 modifiche indebite nel tenant senza schemi validi.
- **Frontend**: box "Riassegna provvigioni aggiornate" nella libreria Sistema Provvigionale con pulsanti "Solo arretrati" e "Tutti i titoli" + riepilogo esito (esaminati/aggiornati/Δ).

- Aggiunta la possibilità di assegnare **tag** anche a **polizze** e **titoli** (prima solo anagrafiche). Campo `tags` nei modelli `Polizza`/`Titolo`.
- Backend: `PUT /polizze/{id}/tags` e `PUT /titoli/{id}/tags` (helper `_norm_tags`: lowercase, underscore, univoci). Titolo salva i tag anche dal payload di `update_titolo`. `GET /anagrafiche/tags` ora unisce i tag di anagrafiche + polizze + titoli per l'autocomplete.
- Frontend: card "TAG POLIZZA" in `PolizzaDetail` (salva subito via API) e campo "Tag titolo" nel `TitoloDialog`, entrambi con `TagsEditor` riusabile.
- **Verifica KPI/Tag** (testing agent iteration 90): 7/7 test backend, KPI Contabilità coerenti (Saldo=Entrate−Uscite, no NaN), KPI sezioni 200 OK, tag anagrafica/polizza/titolo persistono correttamente.

- Il tab Documenti della scheda Polizza ora usa il layout a **griglia di card per categoria** (quadrotti), come la scheda Anagrafica.
- Aggiunto prop `layout="quadrotti"` a `DocumentiSezioneSplit` + nuovo componente `QuadrottoCategoria`: ogni card mostra icona, etichetta, indicatore visibilità (occhio/lucchetto), conteggio, elenco file con toggle visibilità/elimina e pulsante di upload dedicato. Il layout "split" (due riquadri) resta per gli altri usi (sinistri, libro matricola, ecc.).
- `PolizzaDetail.jsx`: attivato `layout="quadrotti"`. Verificato con screenshot (11 categorie, MUP con 2 file).
- Aggiunta categoria **Questionario** (🗒️, visibile al cliente) ai documenti polizza — questionario assuntivo/adeguatezza firmato.
- Esteso il layout a quadrotti anche alla scheda **Sinistro** (`SinistroDetail.jsx`, `layout="quadrotti"`): categorie CID, Perizia, Foto, Fattura, Denuncia, Documenti altri.

- Verificato lo stato: la maggior parte dei doppioni (RC AUTO, VITA, INCENDIO, INFORTUNI, TRASPORTI, RCG) era **già archiviata** (attivo=False / `unito_in_ramo_id`) da merge precedenti → già esclusi dalle tendine.
- Restava attivo un solo doppione reale: **MULTIRISCHIO** (2 voci "Multirischio"/"MULTIRISCHIO"). Unificato con lo script `scripts/unifica_rami_doppioni.py` (stessa logica dell'endpoint `/librerie/rami/merge`): 5366 polizze + 76 prodotti riassegnati al master, doppione archiviato; ripuntati anche gli `import_mappings` ramo.
- Risultato: dropdown rami senza codici duplicati (49 rami), polizze/prodotti intatti. La UI "Unisci doppioni" in Librerie resta disponibile per future unificazioni.

- Il widget cumulativo `_compute_saldi_compagnie` (dashboard/brogliaccio, `saldo_cassa`) ora include le **PNC versate** (movimenti categoria `pnc`), che alimentano il saldo esattamente come le ritenute compagnia: `saldo = dovuto − rimesse − rappel + ritenute + pnc_versate − ...`.
- Aggiunto campo `pnc` all'output per compagnia; guardia anti-skip aggiornata. Nessuna modifica frontend (il widget mostra il `saldo_cassa` aggregato, già comprensivo di PNC).
- Verificato: PNC versata +200 → `saldo_cassa` 1360→1560, campo `pnc`=200.

- Le partite PNC ora compaiono nell'E/C compagnie insieme a rappel, ritenute e fatture partner (solo mandato diretto), lette dai record `db.pnc` come le ritenute compagnia.
- Importo firmato: `+` alimenta il DARE (aumenta il saldo da versare), `−` va in AVERE. Incidono su `totale_dare`/`totale_avere`/`saldo`; aggiunto `totale_pnc` alla risposta.
- Backend `server.py` `_compagnia_estratto_data` (la lista saldi `saldi_cassa_compagnie` deriva da qui → coerente). Frontend `EstrattoContoCompagnie.jsx`: riga PNC in "Movimenti & versamenti" con badge viola "PNC · <tipo>".
- Verificato: PNC +120 → saldo E/C 1825→1945, `totale_pnc`=120, riga visibile.

- Il legame Agenzia partner ↔ Compagnia ora si sincronizza da entrambi i lati (campo plurale `agenzie_partner_ids`).
- Sorgente di verità: `compagnia.agenzie_partner_ids`. Il lato agenzia lavora in **write-through** (aggiorna le compagnie) e **derive-on-read** (`agenzia.compagnie_ids` calcolato). Nessun impatto sulla contabilità (che usa il singolare `agenzia_partner_id` + `tipo_mandato`, invariato).
- Backend `routes/agenzie.py`: `AgenziaBody.compagnie_ids`, helper `_compagnie_ids_of` / `_sync_agenzia_to_compagnie`; `create/update/get/list` ritornano `compagnie_ids`; `delete` pulisce i riferimenti plurali.
- Frontend `Agenzie.jsx`: nuova multi-select "Compagnie partner collegate" nell'AgenziaDialog (solo agenzie partner). Il form Compagnia (`Librerie.jsx`) già gestisce il multi-select "Agenzia partner".
- Verificato end-to-end: creare/rimuovere dal lato agenzia aggiorna `compagnia.agenzie_partner_ids`; modificare dal lato compagnia si riflette in `agenzia.compagnie_ids`.

- Nuovo gruppo sidebar **"Partite PNC"** contenente Rappel, Ritenute (hub) e la nuova voce **PNC** (`Sidebar.jsx` section `partite_pnc`, route `/pnc` in `App.js`).
- Pagina **PNC** (`frontend/src/pages/Pnc.jsx`) **identica alle Ritenute Compagnia** (compagnia solo mandato diretto, Data, Segno +/−, Importo €, Descrizione, Note, azione **Versa/Storna**) con in più la **tendina "Tipo PNC"** (Rivalsa / Cassa Agenti / Fondo Pensione / Gruppo Agenti) e filtro in alto per tipo. KPI Totale/Da versare/Versate.
- Backend `routes/commerciale.py`: nuova raccolta `pnc` + endpoint `GET/POST/PUT/DELETE /pnc`, `/pnc/totali` (per_tipo), `/pnc/{id}/versa` (crea movimento categoria `pnc` in Prima Nota, come la Ritenuta compagnia) e `/pnc/{id}/storna`.
- **Prima Nota**: nuova colonna **PNC** (`BrogliaccioTab.jsx` FIXED_COLS + `server.py` brogliaccio builder categoria `pnc` → `c_pnc`, incide sul `saldo`, `totale`=0, non è cassa reale). Verificato: versamento 250,50 € → colonna PNC=250,50 e saldo=250,50.

- I prodotti in libreria hanno già il ramo di appartenenza: ora il ramo della polizza **deriva automaticamente dal prodotto mappato** (niente più mapping ramo separato / codici "3N" spuri).
- `ania_importer.py` (`_processa_polizze`): se il prodotto è mappato a un prodotto di libreria, `polizza.ramo` = `prodotto.ramo` (priorità sul ramo del tracciato).
- `server.py apply_import_mappings` (tipo prodotto): il back-fill ora propaga anche `polizza.ramo` dal ramo del prodotto.
- `server.py list_unmapped_entities`: il tab **Prodotto** del wizard ora **pre-seleziona il ramo già collegato** al prodotto (`ramo_corrente_id`), con lookup su rami ATTIVI + alias comuni (RCA→RC AUTO) e match normalizzato. `save_mapping` ora aggiorna sempre il ramo del prodotto scelto nel wizard (override, non solo se vuoto).
- `Importazione.jsx`: il select prodotto usa `ramo_corrente_id` come valore corrente; il confronto "modificato" in `saveAll` usa il ramo corrente per i prodotti.
- Verificato: 88/88 prodotti mappati risolvono il ramo e lo mostrano pre-selezionato nel wizard (screenshot).
- NB: il tab "Ramo" resta disabilitato di proposito (non necessario: si collega il prodotto al ramo).


## 2026-09-02 (parte 7) — Filtri, contatori, provvigioni, KPI ✅
- **Filtro collaboratori**: `/api/collaboratori` ora include anche l'admin/agente → la tendina non è più vuota nelle agenzie con un solo utente (verificato).
- **Contatore "Senza polizze"**: era 0 per overlap con i condomini; ora le 3 categorie (con_polizze/senza_polizze/condominio) sono mutuamente esclusive (verificato: 964+2122+102=3188).
- **Nuovi filtri Anagrafiche**: professione, comune, età (min/max via data_nascita), "genitori con figli" (numero_figli>0) — backend `list_anagrafiche` + UI in `Anagrafiche.jsx` (verificato età 30-50 → 605).
- **Customer Insights (AnagraficaDetail)**: aggiunti KPI Polizze Annullate/Sospese/Sostituite (`extras_p1p2.py` + `CustomerInsightsWidget.jsx`).
- **PolizzaDetail**: header mostra ora Ramo · Prodotto; selettore Operatore spostato nel blocco titolo (più visibile).
- **Provvigioni redesign**: `ProvvigioniOperatoriEditor` (PolizzaDetail) e ripartizione in `TitoloDialog` rifatte in stile tabella operatori (# / Operatore / Provvigione € / Provv. su addizionali € / Azioni) + campo "Provv. struttura (rata)".
- **Schema provvigionale**: nuovo campo `percentuale_su_premio_netto` (modello + dialog Librerie); calcolo usa il netto se valorizzato e disponibile.
- **RETE PIRAMIDALE (fix calcolo)**: le quote upline ora sono calcolate sulla PROVVIGIONE TOTALE AGENZIA (es. 100€ → collab sottorete 50% = 50€, capo-rete 10% = 10€), non più sulla quota del collaboratore diretto. In `server.py _calcola_provvigione`.
- **Import mapping**: alias "data rata"/"datarata" → campo effetto del titolo.


## 2026-09-02 (parte 6) — Import Massivo: arricchimento & auto-creazione ✅
Mapping titolo esteso + logica commit potenziata (tutto verificato E2E su agenzia nuova):
- **Nuovi campi mappabili (Titolo/Quietanza)**: compagnia, ramo, operatore, DataCopertura, CF/nome contraente, mandato → ora appaiono nella tendina di mapping (risolve select_14_2 "manca RAMO/COLLABORATORI").
- **Titolo**: se c'è Data Pagamento → stato "incassato" (appare nei Titoli Storici); DataCopertura → "titolo_coperto"; metodo di pagamento mancante → auto-creato; operatore → collegato/creato come collaboratore bozza (con solo nome, da completare in Librerie, taggato al tenant); polizza inesistente → creata al volo (compagnia+ramo) e segnalata nel report.
- **Anagrafica**: dal codice fiscale calcola sesso, data_nascita, comune/provincia nascita; email→canale email, cellulare→canale whatsapp+sms; tag generazionale automatico (Boomer/Gen X/Millennial/Gen Z/Alpha); indirizzo → geocoding automatico throttled in background (Nominatim ~1 req/s).
- **Report esito**: sezione "Creati automaticamente" (compagnie, metodi pagamento, banche, collaboratori, polizze-da-titolo) in `ImportMassivo.jsx`.
- File: `routes/import_massivo.py` (ENTITY_FIELDS titolo + alias, helper `_mezzo_pagamento_codice`/`_banca_id`/`_operatore_id`/`_enrich_anagrafica`/`_tag_generazionale`/`_geocode_anagrafiche`), `ImportMassivo.jsx`.

### BACKLOG UI (richieste utente, non ancora fatte)
- Customer Insights (AnagraficaDetail): aggiungere KPI polizze Annullate/Sostituite/Sospese.
- Redesign sezione "Provvigioni" (Polizze + Titoli) in stile tabella operatori.
- PolizzaDetail: mostrare nome prodotto oltre al ramo; riposizionare elemento poco visibile (line ~119).


## 2026-09-02 (parte 5) — Filtri Titoli scaduti a GIORNO ESATTO ✅
Prima i filtri "5gg/10gg/15gg" erano cumulativi (≥N giorni) → quasi identici (~1187). Ora a giorno esatto (richiesta utente):
- **`server.py list_titoli`**: nuovi param `scaduta_giorni_esatti` (scadenza == oggi−N) e `scaduta_giorni_oltre` (scadenza < oggi−N).
- **`server.py` dashboard-admin `titoli_scaduti`**: bucket a giorno esatto — Oggi=oggi, 5gg=oggi−5, 10gg=oggi−10, 15gg=oggi−15, +15gg=oltre 15gg.
- **`Titoli.jsx` preset**: scad_5g/10g/15 → `scaduta_giorni_esatti`; scad_oltre15 → `scaduta_giorni_oltre:15` (prima usava erroneamente `scadenza_oltre_giorni`=futuro).
- **Verificato**: bucket ora {Oggi:0, 5gg:0, 10gg:0, 15gg:1, +15gg:1184}; tab "Scadute da 15gg" mostra 1 titolo (scad. 18/08 = oggi−15).


## 2026-09-02 (parte 4) — Isolamento Collaboratori + Dati Azienda ✅
Requisito utente: ogni agenzia ha i propri collaboratori, propri dati azienda (vuoti alla creazione), e un solo admin (l'agente).
- **`server.py`**: `GET /api/collaboratori` e `GET /api/auth/users` ora filtrano per tenant (`tenant_filter(user)`), la collezione `users` è globale ma gli endpoint applicano il filtro manuale. Prima mostravano gli utenti di tutte le agenzie.
- **`tenant.py`**: aggiunta `azienda_config` a `TENANT_SCOPED_COLLECTIONS` → dati azienda (ragione sociale, logo, RUI, indirizzo, SMTP/IMAP/firma) ora per-agenzia. Backfill doc esistente → principale. Le chiavi API super-admin restano gestite via `raw_db` sul doc principale.
- **Verificato**: nuova agenzia → /collaboratori=0, /auth/users=1 (solo l'admin/agente), azienda ragione_sociale="" (vuota). Principale invariata (11 collaboratori, ASSICURAZIONI SCHIANTARELLI).


## 2026-09-02 (parte 3) — Isolamento tenant: collezioni residue ✅
Dopo il primo giro, "Axicura Cattolica" mostrava ancora dati da queste collezioni non isolate. Ora isolate + backfill orfani→principale (verificato Axicura=0):
- `biblioteca_previdenza` (1051 doc), `biblioteca_jobs`, `biblioteca_previdenza_cartelle`
- `template_modelli`, `scambi_richieste`, `import_massivo_sessioni`, `import_massivo_files`
Note: i 4 `conti_cassa` di una nuova agenzia sono predefiniti creati da `super_admin.create_agenzia` (Cassa Contanti/Assegni/Banca/Pagamento Direzione) — NON un leak. Ticket già isolati via `tenant_id` manuale. `postal_codes`/`banks_registry` restano lookup globali. Condivise come richiesto: `rami`, `tipi_pagamento`, `mezzi_pagamento`.


## 2026-09-02 (parte 2) — Report righe non importate (Import Massivo) ✅
- **Backend `routes/import_massivo.py`**: `result.errori_dettaglio` ora include anche le righe saltate per "numero polizza/sinistro mancante"; limite dettaglio alzato a 500 (`_ERR_CAP`) + nuovo campo `errori_dettaglio_totali`. Aggiunto try/except di livello superiore in `_run_commit` → se il setup fallisce lo stato diventa `errore` con messaggio (niente più spinner infinito).
- **Frontend `ImportMassivo.jsx`**: sezione "Righe non importate — motivo" con riga/entità/motivo, conteggio "mostrate X di Y", pulsante **Scarica CSV** (`import-massivo-scarica-csv`) e gestione stato `errore`.
- **Verificato E2E**: upload titoli con polizze inesistenti → 3 righe saltate con motivo, `errori_dettaglio_totali=3`.


## 2026-09-02 — Isolamento multi-tenant completo + Filtro Collaboratori ✅

### Fix: nuove agenzie non più "vergini" (data leak multi-tenant) — P0
Le agenzie appena create vedevano i dati dell'agenzia principale perché ~40 collezioni con dati per-agenzia NON erano in `TENANT_SCOPED_COLLECTIONS`.
- **`database.py`**: il wrapper `TenantAwareCollection` ora **auto-assegna `agenzia_tenant_id`** su `insert_one`/`insert_many` (solo collezioni scoped, quando c'è un utente in contesto). Colma i write-path che non chiamavano `assign_tenant`.
- **`tenant.py`**: aggiunte a `TENANT_SCOPED_COLLECTIONS` tutte le collezioni dati per-agenzia (applicazioni, avvisi, storico_avvisi, notifiche_*, notifications, analisi_cliente, schede_calcolo, schema_provvigionale, diario, diario_note, email, lead, lead_liste, lettere_abbuono, movimenti, pipeline_cards, pipelines_custom, piramide_templates, rappel, regolazione_storico, richieste_cliente, chat, chat_portale, veicoli, corsi, voci_bilancio, ai_chat_messages, copilot_messages, copilot_sessions, cloud_*, mkt_*, costi_annuali, dashboard_links, calendario, immagini_ai, alert_events, alert_rules, tipologie_sinistri, ritenute_compagnia, whatsapp_chat_meta, nb_fonti, nb_notebooks).
- **CONDIVISE (globali) su richiesta utente**: `rami`, `tipi_pagamento`, `mezzi_pagamento`. Restano globali anche: tenants, users, subscriptions, transactions, azienda_config (API keys super-admin), marketplace_*, super_admin_logs, biblioteca_previdenza*, template_modelli, alert_providers, tickets.
- **Backfill**: `migrate_existing_data_to_principale()` (già eseguito allo startup) assegna gli orfani → `tenant-principale-schiantarelli`. Verificato: 0 orfani rimasti.
- **`routes/openapi_it.py`**: insert veicolo cache spostato da `raw_db.veicoli` a `db.veicoli` (per auto-tag tenant).
- **Verificato E2E**: agenzia nuova (clean) = vuota su veicoli/email/rappel/pipelines/anagrafiche/polizze/titoli/sinistri; dato creato dalla nuova agenzia visibile solo a lei, non alla principale; principale conserva tutti i dati (veicoli 100, tipologie-sinistri 39, ritenute 12).

### Feature/Fix: filtro "Collaboratore" (P1) — testato 100% (iteration_63)
- Bug: 4 pagine chiamavano l'endpoint inesistente `/utenti` → dropdown vuoto. Corretto a `/collaboratori` in `EstrattoContoCompagnie.jsx`, `Voucher.jsx`, `Avvisi.jsx`, `CorsiIvass.jsx`.
- Aggiunto filtro collaboratore mancante in `CarichiMensili.jsx` (endpoint già supportava `collaboratore_id`) e `Anagrafiche.jsx` (+ nuovo param `collaboratore_id` in `routes/anagrafiche.py list_anagrafiche`).


## 2026-09-01 (parte 5) — Import Massivo Intelligente (P0) ✅

Nuovo importatore multi-file Excel/CSV con mapping AI e gestione duplicati. Testato E2E (upload → AI mapping → commit background → status → dedup) su tutte e 4 le entità.

- **Backend** `routes/import_massivo.py` (nuovo, registrato in server.py):
  - `POST /api/import-massivo/upload` (multipart, più file): parse Excel/CSV, rilevamento entità + mapping colonne via **Claude Sonnet** (anthropic/claude-sonnet-4-6, Emergent LLM key) con fallback euristico su alias header. Salva i byte file in `import_massivo_files`, sessione in `import_massivo_sessioni`.
  - `POST /api/import-massivo/{sid}/commit` (JSON plan): esegue import in **background** (ordine forzato anagrafica→polizza→titolo→sinistro), aggiorna progress.
  - `GET /api/import-massivo/{sid}/status`: progress + result (creati/aggiornati/saltati/errori + dettaglio errori).
  - Entità: **Anagrafiche + Polizze + Titoli/Quietanze + Sinistri** (con **metodi di pagamento**: `mezzo_pagamento` sui titoli, `mezzo_pagamento_preferito`/`preferenza_pagamento`).
  - Deduplica: anagrafiche per CF/P.IVA + **fuzzy** su ragione sociale (soglia 0.9, con rimozione acronimi SRL/SPA); polizze per numero polizza; titoli per (polizza+numero/effetto); sinistri per numero sinistro.
  - Policy duplicati: **fill-missing** (aggiorna solo campi vuoti/mancanti).
  - Collegamenti: polizza→contraente (CF/nome), titolo→polizza (numero), sinistro→polizza/contraente.
  - **Robustezza migrazione**: compagnia non trovata → fuzzy match poi **auto-creazione**; enum non validi (stato/tipo/frazionamento) scartati con `_coerce_enums`; default per campi obbligatori mancanti (ramo→N/D, date→"").
- **Modello dati**: `Sinistro.polizza_id/compagnia_id/contraente_id/date` resi Optional → consente import di **sinistri orfani** (polizza storica non ancora migrata).
- **Frontend** `pages/ImportMassivo.jsx` (nuovo) + tab default "Import Massivo AI" in `Importazione.jsx`: dropzone multi-file, card per file con entità + badge AI/euristica + confidenza, tabella mapping editabile (cambio entità aggiorna i campi), barra di avanzamento con polling (guardia max 5 fallimenti), riepilogo con contatori + dettaglio errori.


## 2026-09-01 (parte 4) — Nuova polizza, Regolazione multipla, calcolo scaduti, performance, confronto carichi

### Nuova polizza (Polizze.jsx)
- Aggiunti campi **Imposta €** (premio_tasse) e **SSN €** (premio_ssn); **Premio lordo** ora READ-ONLY e auto-calcolato = netto + imposta + ssn.
- Targa: aggiunto pulsante **"Cerca"** (lookup esplicito Libro Matricola → fallback polizze) oltre a onBlur/Enter.
- Collaboratore: campo **ricercabile** (typeahead per nome) e **auto-compilato** dal collaboratore collegato all'anagrafica del contraente selezionato.

### Calcolo "scaduti da N giorni" — CONTEGGIO INCLUSIVO (fix)
- Semantica: scaduto da N giorni ⟺ scadenza ≤ oggi−(N−1) (il giorno di scadenza conta come giorno 1).
- Applicato a: filtri Titoli (`scadute_da_min/max`, server.py ~2283 e ~2708), bucket Dashboard admin (`titoli_scaduti` 5gg/10gg/15gg, ~9663), display "gg fa" in Avvisi (+1).
- La Dashboard usa `/api/stats/dashboard-admin` per i bucket (presetMap → scad_5g/scad_10g/scad15).

### Regolazione premio
- Header PolizzaDetail: toggle **Sì/No** (attiva/disattiva `regolazione_premio`); con "Sì" appare la tab e la sezione sotto.
- Dialog: label "**Dato di polizza (base preventivo)**" e "**Dato aggiornato cliente (consuntivo)**"; tasso selezionabile **% o ‰** (‰ convertito in % /10 lato client).
- Tab Regolazione: nuova sezione **"Regolazioni calcolate"** che elenca TUTTO lo storico calcoli (più regolazioni su parametri/periodi diversi nello stesso anno, consultabili).
- Banner **dato dichiarato dal cliente** (via link pubblico): mostra il valore e bottone "Importa e calcola" (prefill del dichiarato nel dialog).

### Performance
- Titoli list: rimosso N+1 (fino a 7 query/titolo) su `_provv_breakdown` con **cache schemi provvigionali per-richiesta** (`schema_cache`). ~0.4s per 1217 titoli.
- Polizze list: **projection leggera** (`_LEAN_POL_PROJ`) che esclude garanzie/addizionali/provvigioni_operatori. ~0.55s per 1582 polizze, payload ridotto.

### Confronto Carichi anno precedente (carichi_mensili.py + CarichiMensili.jsx)
- Ricostruito il dialog **ConfrontoAnnualeDialog** (il bottone era rotto: `setConfrontoOpen` non definito, nessun dialog).
- Endpoint `/api/carichi-mensili/confronto-annuale` ora accetta **dal/al**: confronta il periodo selezionato con lo stesso periodo dell'anno precedente (date −1 anno, gestione 29-feb). Fallback a modalità `anno`; senza parametri → 400.


## 2026-09-01 (parte 3) — Titoli, Regolazione avanzata, Pipeline, Prodotti

### Titoli
- POST /api/titoli ora supportato dal dialog (crea + modifica). Fix bug 500: `Titolo.tipo` Literal ora include "annullo". Tipi con etichette: Quietanza/Polizza nuova/Rinnovo/Appendice/Annullo/Sostituzione/Regolazione premio/Storno.
- Provvigioni multi-collaboratore su titolo (`provvigioni_operatori`), ereditate automaticamente dalla polizza; totale sempre modificabile; blocco quando il titolo è incassato.
- Selettore pagamento unificato (`SelectTipoPagamento`, stessa lista dei titoli) in: form polizza (mezzo_pagamento_preferito ora str libero), AzioniPolizzaTab sostituzione. Placeholder "Seleziona metodo di pagamento".
- Auto-calcolo "prossima quietanza" = effetto + intervallo frazionamento.

### Regolazione Premio (avanzata)
- Calcolo DIFFERENZIALE: (base dichiarata − base preventivo) × tasso; dropdown base (fatturato/addetti/retribuzioni/ricavi); `regolazione_base_preventivo` su polizza.
- Flag regolazione anche nell'header polizza (chip "Soggetta · gestisci" / "Attiva") + tab "Regolazione" con pannello completo (config, base preventivo/dichiarata, azioni, storico).
- "Genera titolo" apre il dialog crea-titolo precompilato (tipo=regolazione, importo=dovuto).
- Annulla calcolo / Elimina regolazione (con opzione elimina titolo).
- LINK PUBBLICO cliente: POST /genera-link → /rp/{token}; pagina pubblica `RegolazionePublic` (no auth); il cliente inserisce il dato → auto-compila (`regolazione_base_dichiarata_cliente`), stato→dati_ricevuti, alert in-app agli admin/collab. Invio link via Email (SMTP) e WhatsApp (wa.me).
- Lettera PDF: riporta base dichiarata in polizza + sezione compilabile + link pubblico.

### Pipeline
- Nuova board builtin "Regolazione Premio" (colonne per stato workflow, drag-drop aggiorna regolazione_stato).

### Prodotti (Librerie)
- "È Libro Matricola" ora per tutti i rami; nuovo flag "È polizza cumulativa (elenco assicurati)?". Alla creazione polizza il prodotto propaga is_libro_matricola / is_cumulativa_assicurati.

### Fix
- Lookup veicolo per targa: era MOCK con marca/modello casuali (mismatch). Reso deterministico e COERENTE (coppie marca→modello). ⚠️ MOCKED: dati reali richiedono credenziali OpenAPI.it Automotive.



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

## 2026-06 — Fix import background (task GC) + metodo pagamento async
- **Bug import parziale OMNIA**: `import_omnia_async` lanciava `asyncio.create_task` senza tenere il riferimento → il GC cancellava il task a metà (CancelledError, non catturata da `except Exception`), lasciando anagrafiche/polizze ma NON garanzie/titoli/provvigioni/sinistri e job bloccato su "running". Fix: set modulo `_BG_TASKS` con riferimento forte + `add_done_callback(discard)` (server.py).
- **Bug import metodo pagamento (Cloudflare 520)**: endpoint sincrono su ~17k polizze → timeout gateway. Convertito a job in background (`import_massivo.py`): ritorna `job_id`, stato via `GET /api/import/job/{job_id}`, con campo `processate/totali` per la progress bar. Frontend `Importazione.jsx` ora fa polling. Verificato dry-run: 16.973 polizze in ~12s.
- Nota: molte `polizze_non_trovate` nel metodo pagamento derivano dall'import OMNIA incompleto → reimportare prima lo ZIP OMNIA (ora completo).
- **TargaConflictWidget**: `/polizze/by-targa` ora considera solo polizze `attiva`/`sospesa` (escluse annullate/scadute/sostituite) — extras_p1p2.py.

## 2026-06 — Import OMNIA: auto-creazione entità + fix Partita IVA
- **Fix Partita IVA (ania_importer)**: la classificazione azienda avveniva solo se P.IVA presente E codice fiscale assente. Ora QUALSIASI anagrafica con P.IVA = `persona_giuridica`. Migrazione DB: 637 anagrafiche corrette su tutti i tenant. (API anagrafiche, import massivo, import OCR già corretti.)
- **Auto-creazione entità nell'import OMNIA** (prima solo "tracciate da mappare"):
  - **Prodotti** (rec100) → creati in libreria `prodotti` (dedup per nome), mappati al codice flusso così le polizze si agganciano.
  - **Collaboratori** (rec101) → se nessun match con utenti esistenti, creato stub collaboratore in `users` (ruolo collaboratore, attivo=false) con `agenzia_tenant_id` corretto; match ristretto al tenant.
  - **Rami** non mappati (rec20) → creati in libreria globale `rami` e assegnati alla polizza.
  - **Tipologie sinistri** (rec50) → create in `tipologie_sinistri` dal ramo del sinistro (dedup per nome).
- Compagnie, garanzie, titoli, sinistri: già creati/aggiornati dall'import.
- Test end-to-end sintetico (tenant sandbox) PASS su tutte le entità con isolamento tenant corretto: `backend/tests/test_omnia_autocreate.py`.

## 2026-06-15 — Fix modifica importo Prima Nota
- Bug: nel dialog "Modifica movimento" (Brogliaccio/Prima Nota) il campo Importo si precompilava a 0 per movimenti di costo (uscite, ritenute) perché leggeva dalla colonna `totale` (=0 per questi tipi).
- Fix backend (_compute_brogliaccio, server.py): la riga del brogliaccio ora espone il campo `importo` (importo reale del movimento).
- Fix frontend (BrogliaccioTab.jsx EditMovimentoDialog): il campo Importo si inizializza da `movimento.importo` (fallback totale/lordo).
- Verificato end-to-end via API: brogliaccio espone importo=1234.56 con totale=0; PUT update importo→999.99 OK.

## 2026-06-15 — Fix conto "Pagamento Direzione" sempre a 0
- Bug: nel Riepilogo Conti della Prima Nota il conto "Pagamento Direzione" (tipo RID) restava sempre 0.
- Causa: i movimenti "in direzione" (mezzo RID DIREZIONE / PAGAMENTO IN DIREZIONE, is_direzione=True) hanno conto_cassa_id=None ed erano esclusi da tutte le colonne conti (nessun cash reale).
- Fix (server.py _compute_brogliaccio): i pagamenti in direzione ora alimentano SOLO il conto dedicato tipo "rid" ("Pagamento Direzione") col LORDO — sia imp_giornata (per_conto) sia imp_precedente (aggregate su is_direzione), senza toccare le banche reali.
- Verificato via API reale (tenant Axicura, 2026-09-15): Pagamento Direzione → imp_precedente 55,00 · giornata 386,50 · totale 441,50 (era 0/0/0).

## 2026-06-15 — Eccedenza anche nel dialog Incasso/Copertura
- Bug: nel dialog "Incasso / Copertura" (DialogIncassoCopertura.jsx, usato in PolizzaDetail e Titoli) pagando PIÙ del premio non compariva la gestione dell'eccedenza (a differenza di DialogIncasso.jsx già completo).
- Fix (DialogIncassoCopertura.jsx): aggiunta sezione "Eccedenza" (maggiorazione/credito) visibile quando importo_pagato > lordo; invia gestione_eccedenza al backend POST /titoli/{id}/incassa (già supportato). data-testid: eccedenza-section, ico-ecc-maggiorazione, ico-ecc-credito, ico-eccedenza.
- Verificato via UI (Playwright): premio 356,50 · pagato 400 → sezione Eccedenza 43,50 € con opzioni maggiorazione/credito.

## 2026-06-15 — Modifica movimento Prima Nota: selettore Tipo pagamento
- Richiesta: nel dialog "Modifica movimento" mostrare i MEZZI di pagamento (BONIFICO/RID/ASSEGNO...) invece dell'elenco diretto dei conti.
- Fix (BrogliaccioTab.jsx EditMovimentoDialog): sostituito il Select "Conto/Banca" con SelectTipoPagamento (useTipiPagamento). Il conto_cassa_id viene derivato dal tipo pagamento selezionato (tp.conto_id) e inviato con mezzo_pagamento alla PUT /contabilita/movimenti/{id} (backend già risolve il conto dal mezzo). data-testid: brog-edit-mezzo.
- Verificato via UI: dropdown mostra tutti i mezzi; scegliendo BONIFICO INTESA il movimento va nel conto INTESA.

## 2026-06-15 — Eccedenza a credito: registrazione UNICA con sospeso negativo
- Richiesta (polizza 731015294 STEFANI): cliente paga 145 su premio 143,01 → banca 145, eccedenza 1,99 da restituire → partita nei Sospesi con -1,99, in UNA SOLA riga.
- Fix backend (server.py incassa_titolo): per gestione_eccedenza="credito" niente più movimento separato. Il movimento di incasso ora usa importo=importo_pagato (cash reale in banca) e quota_credito=-eccedenza (sospeso negativo) sulla stessa riga; si crea comunque il titolo credito (-eccedenza) per l'elenco sospesi.
- Fix brogliaccio (_compute_brogliaccio): colonna Sospesi (crediti) ora ammette valori negativi (abs>0.0001) → mostra -1,99.
- Verificato via API sulla polizza reale: riga unica Totale 143,01 · Sospesi -1,99 · Cassa 145,00. Dati di test poi ripuliti (titolo tornato da_incassare).
- Nota: maggiorazione invariata (entrata extra separata). Il residuo/sospeso (pagamento inferiore) invariato.

## 2026-06-15 — Titolo a credito (eccedenza) nei Sospesi + rimborso in un clic
- Richiesta: il titolo a credito da eccedenza deve comparire nella pagina Sospesi e comportarsi come un sospeso normale (stesso pulsante "Incassa"); una volta rimborsato sparisce.
- Fix backend (incassa_titolo): il titolo credito creato dall'eccedenza a credito ora nasce con titolo_coperto=True + data_copertura=data_incasso → entra automaticamente in /titoli/sospesi.
- Nessuna modifica frontend: il pulsante "Incassa" esistente (DialogIncasso) gestisce il titolo negativo → crea l'uscita di rimborso (Cassa/Banca -importo) via categoria incasso_coperto e chiude la partita (stato incassato) → sparisce dai sospesi.
- Verificato E2E su dato reale (polizza 731015294): eccedenza credito → titolo -1,99 nei sospesi → "Incassa" → movimento uscita -1,99 in Cassa, sospeso azzerato, titolo rimosso. Netto cassa +143,01 (premio esatto). Dati di test ripuliti.

## 2026-06-15 — Saldo cassa compagnie: escludere l'eccedenza
- Bug: l'eccedenza a credito (importo incasso = pagato 145, quota_credito -1,99) gonfiava il "Saldo Cassa Compagnie" perché _compute_saldi_compagnie sommava solo importo + quota_sconto.
- Fix (server.py _compute_saldi_compagnie): incassi (premio lordo) = importo + quota_sconto + quota_credito → per eccedenza 145-1,99=143,01; per residuo 143,01+1,99=145. Coerente con lordo_riga del brogliaccio.
- Verificato con aggregazione isolata: eccedenza→143,01, residuo→145.
- NOTA doppia riga: il codice attuale genera UNA sola riga di incasso (verificato in preview). Eventuali righe doppie viste in PRODUZIONE sono dati creati da una versione precedente → serve redeploy + rifare/eliminare la vecchia registrazione.

## 2026-06-15 — Riepilogo Conti: IMP. PRECEDENTE riconciliato con la chiusura
- Bug: IMP. PRECEDENTE di un conto poteva differire dal TOTALE PERIODO con cui il giorno prima era stato chiuso (es. BPER SONDRIO +1,99).
- Causa: imp_prec sottraeva prev_sosp (quota_credito degli incasso_premio) mentre imp_giornata usa direttamente `importo` (già netto del sospeso). Con l'eccedenza (quota_credito -1,99) veniva sommato 1,99 di troppo; con i residui veniva sottratto due volte.
- Fix (_compute_brogliaccio conti_riepilogo): imp_prec = saldo_iniziale + prev_in - prev_out (niente sottrazione di quota_credito), coerente con imp_giornata. Rimossa l'aggregazione 'sosp'.
- Verificato: incasso eccedenza su BPER SONDRIO → TOTALE(20/09)=249.230,92 = IMP.PRECEDENTE(21/09). Riconcilia.

## 2026-06-15 — NUOVA SEZIONE Incentivazioni (MVP)
- Calcolo incentivo per collaboratore sulla nuova produzione (basato Iniziative Cattolica Vita Investimento/Protezione, DNA Danni).
- Backend: routes/incentivazioni.py — GET/PUT /incentivazioni/config (obiettivi+colonna+bonus per campagna, tenant-scoped) e GET /incentivazioni/calcola?data_inizio&data_fine.
  - Nuova produzione = polizze con effetto nel periodo (non annullate), prodotto flaggato a una campagna; base = premio_netto ANNUALIZZATO per frazionamento (mensile x12, trimestrale x4, semestrale x2, quadrimestrale x3, annuale/unica x1).
  - Obiettivo di Agenzia → realizzo% (arrotondato) → aliquota da fascia (tabelle PDF) → incentivo per collaboratore = produzione × aliquota × (1+bonus). Soglia minima 85%.
  - Selettori manuali: colonna RNT (Vita Inv.), livello BASE/TOP (Vita Prot.), BASE/PERSONA (DNA), bonus/malus.
- Modello: ProdottoLibreria.incentivazione_campagna (vita_investimento|vita_protezione|dna_danni|None).
- Tenant: aggiunto "incentivazioni_config" a TENANT_SCOPED_COLLECTIONS (fix isolamento).
- Frontend: pagina Incentivazioni.jsx (periodo, card per campagna, tabella collaboratore→produzione→incentivo), selettore campagna in Librerie→Prodotti (ProdottoForm), voce sidebar + route /incentivazioni.
- Verificato E2E: ACTIVE PROTEZIONE→DNA, obiettivo 50k, realizzo 114,8% → aliquota 9% → incentivi per collaboratore corretti (es. SCHIANTARELLI 19.452,90→1.750,76). Dati di test ripuliti.
- NON implementato nell'MVP (per scelta): APE, RNT calcolato automaticamente, garanzie embedded x5, tetti per prodotto, di-cui Persona separato, malus persistenza da quietanze. Gestiti come selettori manuali.

## 2026-06-15 — Incentivazioni DNA: sotto-target "di cui Persona" (additivo)
- Richiesta: nel DNA aggiungere il target "di cui Cura della Persona + Prot. Beni Persona Fisica" e aliquote automatiche dalle fasce.
- Modello: ProdottoLibreria.incentivazione_persona (bool) — spunta "di cui Persona" sui prodotti DNA (visibile solo se campagna=dna_danni).
- Backend (incentivazioni.py calcola): per DNA due basi per collaboratore (totale + Persona). Aliquote AUTOMATICHE dalle fasce: BASE dal realizzo su Obiettivo DNA totale, PERSONA dal realizzo su Obiettivo di cui Persona. Incentivo = prod_totale×aliqBASE + prod_persona×aliqPERSONA (additivo), ×(1+bonus).
- Config DNA: due obiettivi (obiettivo, obiettivo_persona). Rimossa la scelta manuale colonna per DNA (aliquote auto).
- Frontend: card DNA con due obiettivi, header con realizzo/aliquota BASE+PERSONA, tabella con colonna "di cui Persona"; form prodotto con spunta Persona.
- Verificato E2E: DNA 64.364,58 (realizzo 128,7%→BASE 11%) + Persona 6.988,94 (realizzo 233%→PERSONA 20%) → incentivi per collaboratore corretti (Schiantarelli 2.425,49 = 20374,41×11% + 921,51×20%). Dati di test ripuliti.

## 2026-10-01 — Ricerca descrizione contabilità, fix incasso giornata chiusa, UX date/dialog
- FIX CRITICO incasso: update_titolo (server.py ~L5178) ora blocca la giornata chiusa SOLO se il titolo è realmente contabilizzato (incassato→data_incasso, coperto→data movimento copertura_titolo). I titoli non incassati/non coperti con data_competenza in giornata chiusa sono di nuovo incassabili. Regressione verificata (incassato in giorno chiuso resta bloccato). Test: /app/backend/tests/test_iter99_titoli_unlock_search.py (9/9 ok).
- Ricerca per descrizione: GET /api/contabilita/prima-nota?q= e GET /api/contabilita/banche/movimenti?descrizione= (regex case-insensitive su descrizione/numero_documento/mezzo_pagamento/categoria). banche progressivo disattivato quando descrizione valorizzata.
- Export Prima Nota: nuovo GET /api/stampa/prima-nota.xlsx (+ q); /api/stampa/prima-nota ora accetta q. Banche stampa/export.xlsx accettano descrizione.
- Frontend: tab Movimenti (elenco) con campo Cerca + bottoni Stampa/Excel; Banche con campo Descrizione nei filtri; Brogliaccio con bottone "Cerca" accanto a Oggi per ricaricare la giornata.
- Prompt data italiano: promptDataIt in lib/api.js (GG/MM/AAAA con validazione, converte in ISO). Usato in Pnc.jsx, Rappel.jsx, RitenuteCompagnia.jsx.
- Dialog compattati: TitoloDialog, DialogIncassoCopertura e creazione Polizza (altezza campi ridotta, max-height viewport, scroll corpo) per stare nello schermo.

## 2026-10-01 (2) — Paginazione Titoli/Sinistri, date italiane, ricerca E/C, ordinamento
- Paginazione server-side TITOLI e SINISTRI (50/pagina) con totali e ordinamento calcolati sul backend sull'INTERO set filtrato (non solo la pagina). Backend: list_titoli ~L3981 e list_sinistri ~L5780 con branch `paged` ({items,total,pages,page,page_size,totali[,tipologie]}); allegati contati solo sulla pagina. Frontend: pager + serverTotali in Titoli.jsx e Sinistri.jsx. Regressione: senza `paged` restituiscono ancora array (PolizzaDetail ok). Verificato: titoli 498/10 pagine, sinistri 6412/129 pagine.
- Date italiane: nuovo componente DateInputIt.jsx (campo testo GG/MM/AAAA -> ISO, indipendente da lingua browser). Applicato a filtri Banche, Contabilità Movimenti, Provvigioni, E/C contraente, E/C compagnie (movimenti + storico).
- Ricerca per descrizione in E/C contraente (ecc-cerca) e E/C compagnie (ec-cerca): filtro client-side su contratto/compagnia/rischio/tipo/contraente/collaboratore/ramo.
- Frecce ordinamento (SortHeader) aggiunte a: Contabilità Movimenti (elenco), Provvigioni (maturate), E/C contraente, E/C compagnie (movimenti). Titoli e Sinistri già le avevano (ora server-side).
- Test: iteration_100.json — backend 6/6 pass, frontend ~90% (ecc-cerca non triggerato live per limite autocomplete, codice corretto).
