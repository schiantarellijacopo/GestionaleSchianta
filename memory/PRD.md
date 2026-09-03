# Programma Assicurativo — PRD (aggiornato 12/02/2026)

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
