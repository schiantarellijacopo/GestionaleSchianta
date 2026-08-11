# Programma Assicurativo — PRD (aggiornato 12/02/2026)

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
- **🐛 BUG CRITICO risolto (fix successivo)**: i cunei laterali (INVESTIMENTO/RISPARMIO/PROTEZIONE), pur avendo `clip-path` che li rende visualmente triangolari, geometricamente sono div rettangolari che coprivano metà destra del triangolo — intercettavano tutti i click a destra (pallini, input, tasto +). Aggiunto `pointer-events: none` ai wedge (decorativi puri). Verificato E2E con Playwright: click + → nuova voce, click pallino → cambia colore, input → scrive.
- **Layout compatto**: `PYR_W=720` (era 1040), `WEDGE_AREA=105` (era 250), totale 825px stampabile in A4.
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

