# Assicura CRM — PRD / Memory

## Prodotto
CRM assicurativo multi-tenant. Stack: React + FastAPI + MongoDB.
Multi-tenancy: scoping automatico via `agenzia_tenant_id` (ContextVar in `database.py`, mai `tenant_id`).

## Credenziali test
Vedi `/app/memory/test_credentials.md` (admin@assicura.it / Admin123!).

## Modulo Carichi Mensili
- Backend: `/app/backend/routes/carichi_mensili.py` (`GET /api/carichi-mensili`).
- Frontend: `/app/frontend/src/pages/CarichiMensili.jsx`.
- Titoli importati → `stato_carico=in_attesa`; validati → `validato` (visibili nello Storico).
- Pagina Carichi Mensili usa `stato_carico=attivi` (tutto tranne i validati).
- Storico: riuso di `CarichiMensili.jsx` con prop `storico` (sola lettura), `stato_carico=validato`.

### Ricerca & filtri
- `q` cerca numero polizza, targa, cliente, compagnia; si combina con date/compagnia/operatore.
- Senza date → ricerca globale; con date → limitata al range decorrenza/effetto.
- Totali calcolati sull'intero set filtrato (lordo, netto, provvigioni, margine, provvigioni collaboratore).

### Import CSV/XLS
- Dedup carichi in_attesa per `polizza + scadenza`.
- Date a due cifre normalizzate in ISO (`_to_iso_date`).

## Implementato (changelog recente)
- 2026-06: **Editor visivo segnaposto per Word fedele + operatore derivato dal collaboratore.**
  - Backend `routes/modelli.py`:
    - `GET /api/librerie/modelli/{mid}/struttura-word` → ritorna i blocchi del documento (paragrafi body + celle tabella) con `p_index`, `segments` (testo + grassetto/corsivo/sottolineato) e `style`, preservando l'impaginazione originale del .docx caricato.
    - `POST /api/librerie/modelli/{mid}/inserisci-segnaposto` body `{insertions:[{p_index, offset, token}]}` → inserisce i token nel .docx originale rispettando la formattazione del run ospitante (split del run via XML, `addnext`), ri-estrae i placeholder e aggiorna `placeholders`/`richiede_firma`. Inserimenti sullo stesso paragrafo applicati per offset decrescente.
    - Helper: `_iter_block_items`, `_enumerate_paragraphs` (DFS body→tabelle→righe→celle, ordine deterministico condiviso tra struttura e salvataggio), `_set_run_text`, `_insert_token_into_paragraph`.
    - **Operatore/intermediario** in `build_context`: se `operatore_id` non è passato esplicitamente, viene derivato dal collaboratore collegato (`polizza.collaboratore_id` → fallback `anagrafica.collaboratore_id`). La polizza non ha campo collaboratore nel modello attuale → in pratica si usa `anagrafica.collaboratore_id`. NON si usa più l'utente connesso.
  - Frontend `pages/Librerie.jsx`: nuovo componente `WordVisualEditor` (dialog). Mostra il documento impaginato; l'utente clicca nel punto esatto (calcolo offset plain-text via `getSelection` + `data-ostart` sugli span), sceglie un segnaposto dalla palette `SegnapostoSezione` (riuso, `onInsert`), vede un chip violetto rimovibile, poi "Salva segnaposto". Pulsante "✏️ Segnaposto visivo" sulle card dei modelli `word`/word fedele (`data-testid="modello-visivo-{id}"`). Token esistenti evidenziati in azzurro.
  - Verificato E2E via HTTP sul tenant reale c5ae2d0e (jacopo): upload fedele → struttura → inserimento 5 token (incl. cella tabella) → `genera-fedele` senza `operatore_id` → `{operatore_nome}` risolto dal collaboratore dell'anagrafica. Smoke test UI OK (chip inserito, "1 segnaposto da salvare").

- 2026-06: **Storico Carichi spostato dalla sidebar a un pulsante dentro Carichi Mensili.** Rimossa la voce `carichi-storico` da `Sidebar.jsx`; aggiunto pulsante "Storico Carichi" (icona Archive) nell'header di Carichi Mensili e pulsante "Carichi Mensili" per tornare indietro dall'header Storico. Confermato che Storico Carichi mostra solo `stato_carico=validato` (sola lettura) — frontend invia `stato_carico=validato`, backend filtra correttamente (admin tenant: validato 43, in_attesa 0; tenant reale validato scad. 2026-10 = 98).
- 2026-06: **Isolamento tenant rafforzato (regola critica: i dati di ogni tenant restano separati)**. Rimossi 645 titoli corrotti che puntavano a polizze di un altro tenant. L'import ora lega esplicitamente il titolo al tenant della sua polizza (`agenzia_tenant_id` dalla polizza) in entrambi i percorsi (import automatico + abbinamento manuale). Verificato: import nel tenant c5ae2d0e crea il titolo nello stesso tenant.
- 2026-06: Dedup carichi per `polizza_id + effetto` (decorrenza) invece di `scadenza` — la scadenza poteva divergere (colonna "Scad. copertura" vs calcolata) causando falsi doppioni. Il re-import ora sovrascrive i dati (provvigioni comprese) e collassa i duplicati residui. Puliti i doppioni storici.
- 2026-06: Colonna **Metodo Pagamento** mostra SOLO il tipo pagamento preferito della polizza (`mezzo_pagamento_preferito`).
- Ricerca combinata q + date + compagnia + operatore.
- Filtro compagnia + totali full-set.
- Sezione Storico (sola lettura) per titoli validati.
- 2026-06: **Titoli storici (/titoli-storici) resi archivio sola lettura.** In `Titoli.jsx` con `storicoMode`: `buildParams` forza sempre `stato=incassato` (titoli passati in prima nota), rimosse colonne selezione+azione e barra bulk INCASSO, disabilitati edit/delete. Filtro periodo default su **Data incasso** (prima era "scadenza" → i filtri date non restituivano risultati). "Azzera filtri" ora ripristina il preset storico (storico_anno) invece di "sospesi" (che mostrava titoli da incassare col pulsante Incasso). Verificato UI + curl (data_incasso 2026→9, 2020→0).

## Note tenant
- Dati reali nel tenant `c5ae2d0e-...` (26k polizze, 57k titoli, 23 utenti).
- Account test admin@assicura.it = tenant `tenant-principale-schiantarelli` (dati minimi, NON il tenant reale).
- Un titolo deve SEMPRE avere lo stesso `agenzia_tenant_id` della sua polizza.

## Backlog / Da verificare
- E2E Storico: validare titolo → sparisce da Carichi Mensili → appare in Storico (sola lettura).
- Verifica route/sidebar Storico dopo ultime modifiche.

## [2026-10-23] FIX Storico Carichi mostrava "In Attesa" (causa reale individuata)
- Sintomo: navigando dal pulsante "Storico Carichi" dentro Carichi Mensili comparivano righe stato "In Attesa".
- Causa reale: /carichi-mensili e /carichi-storico rendono entrambe <CarichiMensili>. React Router riusava la stessa istanza senza rimontare → la prop `storico` passava a true (sottotitolo corretto) ma lo stato `statoCarico` restava "attivi" dalla vista precedente, quindi il backend riceveva `attivi` (include in_attesa). L'apertura diretta dell'URL invece montava da zero (validato) → da qui la discrepanza coi test precedenti.
- Fix: aggiunte `key` distinte ("carichi-mensili" / "carichi-storico") alle due Route in App.js → forzano il rimontaggio e il reset di stato.
- Verifica: flusso reale (click pulsante) sul tenant schianta91 (c5ae2d0e) → In Attesa: 0, Validato: 98.

## [2026-10-23] FIX doppione import (titolo già validato)
- Segnalazione (produzione, tenant jacopo@schiantarelli.it / c5ae2d0e): polizza 731121243 con doppione — titolo effetto 19/10/2026 presente due volte (uno "coperto" validato + uno "da incassare" validato).
- Causa: `_insert_or_replace_carico` sovrascriveva SOLO i titoli esistenti `in_attesa`. Se per stessa polizza+decorrenza esisteva già un titolo VALIDATO (coperto/incassato), creava un NUOVO carico in_attesa → dopo validazione = doppione ufficiale.
- Fix (backend routes/carichi_mensili.py): se esiste già un titolo `stato_carico=validato` per stessa polizza+effetto → `_insert_or_replace_carico` ritorna `skipped_duplicate` e NON inserisce. Contatore `duplicati` aggiunto a import/apply, import/match-manual, import. Frontend mostra "Duplicati saltati" nel toast e nel riepilogo step 3.
- Verificato in preview su polizza 731121243: esistente validato → skipped_duplicate (nessun insert); esistente in_attesa → replaced (sovrascrive).
- NOTA: il doppione già presente in PRODUZIONE va rimosso a mano (cestino sul titolo "da incassare" errato). Il fix va in produzione solo dopo un nuovo deploy.

## [2026-10-23] FIX incoerenza import/validazione (doppioni + stato "annullato")
- Segnalazione (produzione, polizza 184643498 DE MARCO LOREDANA): titolo "incassato" + "da incassare" stessa decorrenza 01/10/2026; in Carichi Mensili il carico risultava "ANNULLATO".
- Causa radice: l'IMPORT deduplica per `effetto` (decorrenza), ma la VALIDAZIONE cercava i titoli esistenti per `scadenza`. Poiché i titoli storici/incassati hanno spesso scadenza vuota o diversa da quella calcolata, la validazione NON trovava il titolo già presente e promuoveva il carico a "da_incassare" → doppione. In altri casi (scadenza combaciante) lo marcava `annullato_carico` "Già presente (protetto)" → di qui lo stato ANNULLATO visto dall'utente (comportamento anti-doppione corretto, ma incoerente).
- Fix (routes/carichi_mensili.py, valida_carichi): confronto allineato all'import → per `effetto` (fallback scadenza per titoli senza effetto). Ora se esiste già un titolo protetto per stessa polizza+decorrenza il carico viene scartato (annullato_carico) e NON duplicato.
- Verificato in preview: carico con effetto uguale a un incassato (scadenza diversa) → `protetti=1`, stato_carico=annullato_carico, nessun doppione.
- NOTA: i doppioni "da incassare" già presenti in produzione (polizze 731121243 e 184643498) vanno eliminati a mano col cestino. Fix attivo in produzione solo dopo nuovo deploy.

## [2026-10-23] Validazione carichi: guardia polizza sostituita/annullata
- `valida_carichi` ora controlla lo stato della polizza prima di promuovere il carico.
- Se la polizza è `sostituita` o `annullata`, il carico NON diventa titolo ufficiale: viene marcato `annullato_carico` con motivo `Polizza <stato>`.
- Restituisce anche `scartati_polizza`; toast frontend aggiornato.
- Risolve: creazione di titoli "da incassare" su polizze sostituite (es. 183629512).
- Verificato con test diretto su tenant produzione. Richiede deploy per attivazione in produzione.

## [2026-10-23] Tabelle ad altezza-contenuto (no scroll interno)
- Rimosso il limite di altezza (`max-height`) da `.tbl-scroll` e `.tbl-scroll.has-footer` in index.css.
- `useFillHeight` non impone più un'altezza in pixel (hook semplificato).
- Ora tutte le tabelle crescono per mostrare tutte le righe della pagina (50/100/200); a scorrere è la pagina. Scroll orizzontale mantenuto per tabelle larghe / colonne congelate.

## [2026-10-23] Cronologia sostituzioni, unifica Quietanze, export per colonne
- PolizzaDetail: nuova card "Cronologia sostituzioni" (catena_sostituzioni da GET /polizze/{id}), dal piu recente al meno recente, con polizza ATTUALE evidenziata e link alle altre.
- Statistiche per operatore e premi: rimossa la voce "Rinnovi"; "Quietanze" ora include anche i vecchi tipo="rinnovo" (nessuna migrazione dati storici, solo query/filtri).
- Export (CSV/XLSX/PDF) ora rispettano SIA i filtri attivi SIA le colonne scelte nel menu "Colonne", in ordine: Titoli, Polizze, Sinistri, Anagrafiche. Schemi colonne lato backend: *_EXPORT_SCHEMA + _resolve_export_cols.
- Primo titolo: confermata regola esistente "nuova" (nuova polizza) / "sostituzione" (sostituzione); nessuna modifica necessaria.

## [2026-10-26] Firma digitale Yousign: Data firma + MUP + produzione
- Yousign: config centralizzata sandbox/produzione con chiave unica condivisa (env YOUSIGN_ENVIRONMENT, YOUSIGN_SANDBOX_API_KEY, YOUSIGN_PRODUCTION_API_KEY) in routes/firma_modelli.py::_yousign_cfg.
- Campo DATA firma: _invia_yousign ora aggiunge un campo Yousign "mention" ("Firmato il %date%") accanto alla firma. Segnaposto {data_firma} supportato in Gestione modelli e MUP.
- Gestione modelli: checkbox "Firma digitale" (già esistente come richiede_firma) + hint {firma}/{data_firma}; invio Yousign con firma+data.
- MUP: nuovo flag firma_digitale sul modello MUP (Librerie); _build genera i segnaposto {firma}/{data_firma} nell'area firma; nuovo endpoint POST /polizze/{pid}/mup/firma che genera il MUP, posiziona firma+data e invia a Yousign al contraente, recapitando il link via WhatsApp/Email. In PolizzaDetail il pulsante firma MUP usa questo flusso quando il modello ha firma_digitale, altrimenti resta il flusso OpenAPI OTP SMS esistente.
- Loghi per agenzia: già isolati per tenant (azienda_config), inseriti automaticamente nei moduli e nel MUP.
- Verificato end-to-end in sandbox: POST /mup/firma → ok=True, signing_url generato, campo firma+data accettati da Yousign (status ongoing), MUP archiviato come allegato.
- TODO go-live: impostare YOUSIGN_ENVIRONMENT=production dopo aver salvato YOUSIGN_PRODUCTION_API_KEY.

## [2026-10-26] Libreria "Tipi titolo (riferimento)"
- Nuova libreria condivisa (collezione tipi_titolo, non tenant-scoped come tipologie_sinistri) in Librerie → "Tipi titolo (riferimento)".
- CRUD backend /librerie/tipi-titolo (GET con solo_attivi, POST, PUT, DELETE) + seed idempotente dei 9 tipi di sistema (quietanza, nuova, appendice, inclusione, esclusione, annullo, sostituzione, regolazione, storno) con sistema=True.
- Tipi di SISTEMA: chiave non modificabile e non eliminabili (solo disattivabili) perché usati da statistiche/logiche. Tipi personalizzati: chiave auto-slug dal nome, modificabili ed eliminabili.
- Il menù "Tipo (riferimento)" in TitoloDialog ora legge da /librerie/tipi-titolo?solo_attivi, con fallback ai 9 tipi di sistema se la libreria è vuota/offline.
- Verificato: seed 9, create custom (slug), delete sistema→400, delete custom→200, solo_attivi; tab frontend mostra 9 righe con colonne Nome/Chiave/Ordine/Tipo/Attivo.

## [2026-10-26] Tipi titolo: blocco eliminazione se usato + filtri statistiche dinamici
- DELETE /librerie/tipi-titolo: oltre ai tipi di sistema, un tipo personalizzato GIÀ USATO in almeno un titolo (conteggio globale via raw_db.titoli) non è eliminabile (400) → si può solo disattivare. Verificato 400 se usato, 200 se non più usato.
- Filtri "Tipo titolo" in Statistiche (Per Operatore + Premi/Provvigioni) ora leggono l'elenco da /librerie/tipi-titolo?solo_attivi, così i tipi personalizzati appaiono nei report. Quietanza continua a includere i legacy 'rinnovo' lato backend. Verificato con screenshot (dropdown mostra tutti i tipi della libreria).

## [2026-10-26] Fix: errore salvataggio titolo con tipo personalizzato + provvigioni broker
- CAUSA errore "Errore" al salvataggio: Titolo.tipo era un Literal con lista fissa → i tipi personalizzati della libreria (es. "Franchigia") venivano rifiutati (500). Fix: db_models.Titolo.tipo ora è str libera (default "rinnovo"). Verificato: POST /titoli tipo=franchigia → 201 (prima falliva).
- Messaggio errore form titolo (TitoloDialog.save) ora mostra il dettaglio reale (incl. errori di validazione 422) invece del generico "Errore".
- Provvigioni broker errate (mostrava la quota ANNUALE ereditata 40,96 invece del 4,5% sul netto del titolo = 22,50): il backend calcola correttamente (quota-collaboratore con premio_netto=500 → 22,50; con netto=0 → 0, da cui il vecchio fallback alla quota polizza). Fix frontend: nuovo useEffect in TitoloDialog ricalcola le quote dallo schema quando cambia premio netto/lordo o quando gli operatori vengono ereditati, e allinea il totale provvigioni alla somma ripartita. Non tocca i titoli già incassati.
- NB: fix nel codebase preview; per vederli in produzione (Railway) serve un nuovo deploy.

## [2026-10-26] (RCA approfondita) Provvigioni broker 4,5% sul netto
- Causa reale: _provv_breakdown azzera tutto se la provvigione totale ~0 (abs(tot)<0.005). Nel form "Provvigioni totale" è 0 → la quota-collaboratore tornava 0 → fallback alla quota ANNUALE della polizza (40,96).
- Fix backend: quota_collaboratore_endpoint ora, per schemi con percentuale_su_premio_netto>0 e premio_netto presente, calcola la quota direttamente dal netto (via _quota_collab_da_schema) anche con totale=0, senza passare dal corto-circuito. _provv_breakdown (stats/E-C) invariato.
- Verificato via API: totale=0+netto=500 → 22,50; schema ripartizione 70% con totale=0 → 0 (invariato), totale=100 → 70.
- Verificato E2E nel form (screenshot): netto 500 → riga collaboratore 22,50 e Totale ripartito 22,50 € (prima 40,96).

## [2026-10-26] Regolazione Premio: ricerca + filtri (collaboratore, compagnia, date)
- Backend /regolazione-premio ora include collaboratore_id e collaboratore_nome (enrich da users).
- Frontend RegolazionePremio: barra filtri con ricerca testo (cliente/polizza/compagnia/ramo/prodotto/collaboratore), select Compagnia, select Collaboratore, intervallo date Scadenza (dal/al), "Pulisci filtri" e conteggio "X di Y". Filtri client-side (la lista è già caricata), si combinano con i pill di stato. Collaboratore mostrato come sottotitolo nella colonna Compagnia.
- Verificato E2E (tenant Schiantarelli preview): ricerca "730" → 1 di 2; opzioni collaboratore popolate; filtri render corretti.

## [2026-10-26] Sezione "Segnaposto {…}" + placeholder firma
- Aggiunto {data_firma} e documentato {firma} in _PLACEHOLDER_DISPONIBILI (routes/modelli.py).
- Nuovo endpoint GET /librerie/placeholders: catalogo raggruppato (_PLACEHOLDER_CATALOGO) con key/label/token. 52 segnaposto in 6 gruppi.
- Nuova scheda Librerie "Segnaposto {…}" (SegnapostoSezione in Librerie.jsx): istruzioni d'uso, ricerca, griglia raggruppata con copia-al-clic. Spiega che i segnaposto vanno scritti nel modello o nel Word/PDF e vengono sostituiti coi dati reali in generazione; {firma}/{data_firma} per la firma digitale.
- Verificato: endpoint 52 voci; scheda mostra 52 item, copia funzionante. NB: la sostituzione testuale piena avviene sul corpo del modello/Word; per i PDF caricati la posizione firma/data viene localizzata ({firma}/{data_firma}).

## [2026-10-26] Word fedele (mail-merge con layout preservato)
- Nuovo upload "Carica Word fedele" (Librerie → Modelli, scheda Word): il .docx resta identico (font/tabelle/logo). Endpoint POST /librerie/modelli/importa-word-fedele (tipo=word, word_fedele=True, word_storage_path, placeholders auto-rilevati). NIENTE trasformazione AI.
- Generazione: POST /librerie/modelli/{id}/genera-fedele. _fill_docx sostituisce i {segnaposto} run-aware mantenendo l'impaginazione; _docx_to_pdf converte via LibreOffice headless (soffice). formato=docx → Word compilato; formato=pdf → PDF identico; invia_firma → mantiene {firma}/{data_firma}, converte in PDF, localizza i marcatori e invia a Yousign (riuso _invia_yousign con data_fields).
- Segnaposto conosciuti senza valore → stringa vuota (niente {token} grezzi in stampa). In modalità firma {firma}/{data_firma} restano come marcatori per il posizionamento.
- Frontend: pulsante verde "Carica Word fedele", badge "Word fedele" sulle card, UsaModelloDialog instrada a genera-fedele (PDF/Word/Invia a firma) quando word_fedele.
- Verificato E2E: upload docx con {cliente}/{numero_polizza}/{firma}/{data_firma} → DOCX compilato senza token grezzi (layout ok), PDF 200, firma Yousign ok=True signing_url status ongoing.

## [2026-10-26] Tabelle: dato completo nelle colonne congelate (no troncamento)
- index.css: le frozen cells (.tbl-scroll .freeze-2/3 prime colonne) non troncano più con ellissi ma vanno a capo (white-space: normal, overflow-wrap: anywhere, vertical-align: top), mantenendo la larghezza fissa per l'allineamento delle colonne bloccate. Modifica globale → vale per tutte le tabelle. Override singolo ancora possibile con classe wrap-cell.
- Verificato su Titoli (tenant Schiantarelli): nomi contraente lunghi ora interamente visibili su più righe.

## [2026-10-26] Riordino colonne: frecce su/giù oltre al drag
- ColumnManager (componente condiviso di tutte le tabelle): il drag&drop per riordinare esisteva già e funziona; aggiunte frecce ▲▼ su ogni colonna come alternativa affidabile (funziona anche su touch/tablet dove il drag HTML5 non va). Maniglia grip resa più visibile; etichetta "Trascina o usa ▲▼ per riordinare". move(idx,delta) salva l'ordine come il drag.
- Verificato E2E su Titoli: freccia giù su "Contratto" lo sposta sotto "Targa" e la tabella si aggiorna; drag già verificato. Vale per tutte le tabelle (Titoli, Polizze, Sinistri, Anagrafiche…).

## Segnaposto — enhancement (26/10/2026)
- Aggiunti valori d'esempio a tutti i 126 segnaposto in /librerie/placeholders (backend `_PLACEHOLDER_ESEMPI`).
- `SegnapostoSezione` ora: inserimento diretto nel corpo (prop onInsert), preferiti persistenti (localStorage), anteprima valori, filtri rapidi per gruppo. Riusato in dialog standalone (copia) e nell editor modelli (inserisce). In modalità `compact` usa 1 colonna così i token non si tagliano.

## [2026-06] Editor Word visivo (fix persistenza) + segnaposto multi-canale + tabella da PDF
- **FIX CRITICO persistenza editor Word** (`Librerie.jsx`): il `WordVisualEditor` resettava l'innerHTML dei paragrafi ad ogni re-render React 19 (dangerouslySetInnerHTML con nuovo oggetto `{__html}`). Introdotto componente memoizzato `EditablePara` che imposta l'innerHTML UNA SOLA VOLTA nel useEffect di mount e registra il nodo via `onRegister`; i re-render del parent (toggle elimina/ripristina) non sovrascrivono più il contenuto digitato. Callback stabili (`useCallback`): registerRef, markDirty, rememberSel, toggleDelete. Verificato da testing agent (iteration_120): testo digitato, grassetto, colore ed eliminazione riga sopravvivono a Salva+chiudi+riapri.
- Fix grassetto sui titoli: `serialize()` ora tratta `font-weight: normal/400/lighter` come bold=false (prima lo ignorava, quindi il toggle di execCommand sui titoli già semibold via CSS non registrava).
- **Segnaposto visivo su tutti i canali**: aggiunto pulsante "✏️ Segnaposto visivo" sulle card dei modelli NON word-fedele (email/sms/whatsapp/pdf) → apre il form `ModelloFormDialog` che ha già la palette segnaposto con inserimento al cursore nel corpo. I word-fedele mantengono "✏️ Modifica documento" (WordVisualEditor). testid `modello-visivo-<id>` per entrambi.
- **Importa tabella da PDF** (TabelleManager): pulsante "Importa da PDF" (`tabella-importa-pdf`) → POST `/api/librerie/tabelle/estrai-da-pdf` (backend `modelli.py`): `pdfplumber.extract_tables()` con fallback AI (`_ai_estrai_tabella`, Claude via EMERGENT_LLM_KEY) → ritorna `{nome,tipo:griglia,colonne,righe}` SENZA salvare → precompila `TabellaEditor`. Verificato via curl (4 colonne, 3 righe estratte correttamente).
- Fix allineamento colonne `TabellaEditor` griglia: header-cell ora `relative w-40` con icona rimozione (x) sovrapposta all'angolo (assoluta) invece che inline → header e celle dati condividono la stessa larghezza. Verificato con screenshot.

## [2026-06] Tabelle righe-sezione + segnaposto celle + anteprima impaginata + Editor PDF visivo
- **Righe-sezione nelle tabelle a griglia** (stile tabella RC Auto): nuovo campo `righe_sezione` (lista indici riga) su POST/PUT `/api/librerie/tabelle`. Backend `modelli.py`: `_tabella_righe_render` ora ritorna `(headers, rows, sezioni)`; `_docx_build_tabella` fonde la riga-sezione su tutte le colonne (grassetto, sfondo grigio), `_pdf_build_tabella` usa SPAN colSpan=tutte le colonne. `_docx_insert_tabella_before` propaga le sezioni. Verificato via unit test diretto (DOCX merged cell, PDF build) + API (righe_sezione [0,2] persistite).
- **TabellaEditor** (`Librerie.jsx`): aggiunta/conversione righe DATI ↔ righe-SEZIONE (icona Layers, input a tutta larghezza, visivamente distinte slate-200), inserimento SEGNAPOSTO nelle CELLE al cursore (palette SegnapostoSezione), ANTEPRIMA con header scuro + righe dati + sezioni colSpan. Verificato (iteration_121): PASS completo + persistenza dopo reload.
- **Editor PDF visivo** (nuovo `PdfVisualEditor`, bottone `modello-pdfvisivo-{id}` su card pdf_*): due modalità —
  1. **Segnaposto sul PDF (overlay)**: pagine del PDF originale renderizzate come PNG (PyMuPDF/fitz), click per posizionare token a coordinate normalizzate, pannello X%/Y%/dimensione, rimozione, salvataggio, anteprima PDF compilato.
  2. **Documento impaginato**: editor testo del corpo con palette segnaposto, salvataggio corpo.
- **Backend PDF overlay** (`modelli.py`): `da-pdf` ora salva anche il PDF originale su object storage (`pdf_storage_path`); endpoint `GET /pdf-pagine` (render pagine base64), `POST /pdf-origine` (collega/sostituisce PDF), `POST /pdf-overlay` (salva disposizione), `POST /genera-pdf-overlay` (stampa i segnaposto risolti con build_context sul PDF originale via `_pdf_stamp_overlay`). Verificato E2E via API (render 2 pagine, overlay persistito, genera 200 application/pdf con valori stampati).
- **FIX #1 (HIGH)** WordVisualEditor: il segnaposto dalla palette veniva inserito a inizio paragrafo invece che al cursore — `restoreSel` ora cattura `savedRange` in locale PRIMA di `focus()` (che faceva scattare onFocus→rememberSel sovrascrivendo la selezione). Verificato iteration_122.
- **FIX #2 (MEDIUM)** PdfVisualEditor modalità testo: dopo "Salva testo", chiudi+riapri mostrava il testo vecchio — aggiunto `savedRef` + `close()` che chiama `onClose(true)` così il parent ricarica la lista. Verificato iteration_122.
- Test finale: iteration_121 (~88% → bug corretti) e iteration_122 (100%, entrambi i fix verificati).

## [2026-06] PDF/Tabelle enhancement: Anteprima A4+stampa, segnaposto immagine, drag segnaposto
- **Anteprima A4 + Stampa (TabellaEditor)**: l'anteprima tabella è ora un foglio A4 (210×297mm, verificato ratio 1.414) con impaginazione serif; pulsante "Stampa" (`tabella-stampa-btn`) apre una finestra con CSS `@page A4`, header/righe/sezioni e zebra, poi `window.print()`. Verificato iteration_123.
- **Segnaposto IMMAGINE sul PDF (PdfVisualEditor overlay)**: palette con sezione "Immagini" → `Logo agenzia` (key `logo`) e `Firma operatore` (key `firma_operatore`); posizionati come riquadri ridimensionabili (campi Largh.%/Alt.% nel pannello proprietà). Backend: `PdfOverlayItem` esteso con `kind` (text|image) + `w`/`h`; `_pdf_stamp_overlay(..., images)` inserisce le immagini via `page.insert_image` (logo da azienda_config/logo_url, firma da ctx `_firma_operatore_url`). Verificato via API (immagine embeddata nel PDF) + UI (iteration_123). NB: se l'agenzia non ha logo/firma impostati, vengono saltati silenziosamente (generazione comunque 200).
- **Trascina segnaposto (drag)**: gli elementi overlay si spostano col mouse (pointer events + listener window su `dragRef`), con offset di presa per evitare lo scatto e `clampItem` che mantiene l'intero riquadro dentro la pagina (x ≤ 1−w, y ≤ 1−h per le immagini). `touch-action: none` per i dispositivi touch. Verificato iteration_123 (X/Y aggiornati, nessun duplicato creato durante il drag).
- Test: iteration_123 = 100% dei flussi richiesti; fix clamp off-page + grab offset applicati dopo il report.

## [2026-06] Stampa multi-pagina A4 + set completo segnaposto operatore
- **Interruzioni di pagina intelligenti (stampa A4 tabelle)** `Librerie.jsx` `stampaTabella`: l'header della tabella è ora in `<thead>` così si ripete su ogni pagina (`thead{display:table-header-group}`); le righe non si spezzano tra pagine (`tr{break-inside:avoid}`) e le righe-sezione restano attaccate al contenuto sotto (`tr.sez{break-after:avoid}`). Verificato: compila con 1 warning preesistente.
- **Set completo segnaposto Collaboratore/Operatore** `modelli.py`: gruppo esteso da 8 a 28 segnaposto. Nuovi: `{operatore_cognome}`, `{operatore_nome_proprio}`, `{operatore_luogo_nascita}`, `{operatore_data_nascita}`, `{operatore_indirizzo}`, `{operatore_cap}`, `{operatore_comune}`, `{operatore_residenza}` (completa), `{operatore_sede_legale}`, `{operatore_ufficio}`, `{operatore_pec}`, `{operatore_telefono_ufficio}`, `{operatore_fax}`, `{operatore_codice_gestionale}`, `{operatore_mansione}`, `{operatore_carica}`, `{operatore_tipologia}`, `{operatore_rui_albo}`, `{operatore_rui_qualifica}`, `{operatore_rui_data_iscrizione}`. Risolti in `build_context` dal record `users` (mapping 1:1 col form Utente → anagrafica/RUI); date formattate con `_fmt_date_doc`. Aggiunti esempi in `_PLACEHOLDER_ESEMPI` e fallback d'esempio nell'anteprima quando nessun operatore è collegato. Verificato via curl (endpoint placeholders = 28 voci; preview risolve tutti i token con dati d'esempio).

## [2026-06] Diario per attività + tasto Incasso compatto
- **Diario suddiviso per attività** `AnagraficaDetail.jsx` (DiarioTab): aggiunte categorie-attività (Incassi, Comunicazione avvisi, Email, WhatsApp, Chat, Documenti, Telefonate/Incontri, Note) derivate da `diarioCategoria(v)` (priorità: avvisi con `storico_avvisi_id` → incassi per keyword → canale/tipo). Chip filtro in alto (`diario-filtro-*`) con conteggi + lista raggruppata con intestazioni di sezione (`diario-gruppo-*`). Verificato via screenshot (gruppi "Comunicazione avvisi" e "WhatsApp" renderizzati con conteggi).
- **Tasto Incasso/Copertura compatto** `Titoli.jsx`: il bottone azione è ora icona-only (Wallet, `h-7 w-7`, tooltip "Incasso / Copertura"), colonna Azione ridotta da `w-[110px]` a `w-[48px]`; colonna Contraente allargata (`min-w-[220px]`). Verificato via screenshot.

## [2026-06] Fix Firma Moduli: segnaposto non compilati + colonna Contratto storici
- **Firma Moduli — segnaposto compilati** `routes/firma_modelli.py`: `_valori_dato()` usava solo il vocabolario `CAMPI_DATO` (nome_cliente, codice_fiscale, indirizzo, collab_*). I token del vocabolario "Modelli" (`{cliente_via}`, `{operatore_nome}`, `{operatore_sezione}`, ecc.) restavano come testo. Aggiunti alias cliente_* e operatore_* (mappati a indirizzo/comune/collab_*). In `_compila_pdf()` gestiti i token immagine/strutturali: `{logo}` e `{firma_operatore}` rimossi (blank), `{data_firma}` rimosso + posizione raccolta come data_field Yousign (mention "Firmato il %date%"); firma: `(bytes, firma_fields, data_fields)`. `compila_modello` passa `data_fields` a `_invia_yousign`. Verificato: PDF di prova con tutti i token → 0 token residui, firma_fields=1, data_fields=1. NOTA: i segnaposto tabella (`{tabella:slug}`) NON sono supportati in Firma Moduli (appartengono al generatore "Modelli").
- **Colonna Contratto in Titoli storici** `Titoli.jsx`: in `storicoMode` la colonna checkbox è rimossa ma le larghezze fisse delle colonne congelate (`--c1-w/c2-w/c3-w`) restavano mappate per posizione → "Contratto" ereditava i 36px della checkbox e si spezzava carattere per carattere. Larghezze ora condizionate a `storicoMode` (Contratto 150px, Targa 90px, Compagnia 140px). Verificato via screenshot.

## [2026-06] Genera Documento: tabelle dinamiche + segnaposto completi + firma
- **Flusso corretto individuato**: `GeneraDocumentoButton.jsx` → `POST /documenti/genera` (`routes/documenti_genera.py`), NON firma_modelli. Pulsanti: Anteprima PDF (salva=false, blob), Firma (genera+archivia → /esignature/invia), Genera e archivia.
- **`_context` esteso**: aggiunti `cliente_via`, `cliente_citta` e blocco operatore/intermediario (collaboratore da polizza/anagrafica): `operatore_nome`, `operatore_cognome`, `operatore_codice_fiscale`, `operatore_email`, `operatore_telefono`, `operatore_rui`, `operatore_sezione`/`operatore_rui_sezione`, `agenzia_rui*`, `_firma_operatore_url`.
- **Tabelle dinamiche `{tabella:slug}`**: `_build_pdf` ora rende le tabelle della libreria (`modelli_tabelle`) come tabelle visive reali, riusando `_tabella_righe_render`/`_pdf_build_tabella` di `modelli.py`. Slug caricati con `_load_tabelle_map`. NOTA: lo slug deve esistere in Librerie→Tabelle (es. `rapporti_con_le_compagnie`; `rapporti_con_le_compagnie_copia` NON esiste → va creato o corretto).
- **Token speciali**: `{logo}` rimosso (logo già in intestazione), `{firma_operatore}` → immagine firma operatore se presente altrimenti riga, `{firma}` → "Firma del Contraente ___", `{data_firma}` → "Data: __/__/__".
- **Verificato**: curl `POST /documenti/genera` HTTP 200, 0 token residui, tabelle+firma renderizzate; conferma visiva PDF (header, tabella rapporti compagnie con 2 righe, checklist dichiarazioni con 7 X, blocchi firma).
- Anteprima: il pulsante "Anteprima PDF" esisteva già e ora mostra il documento interamente compilato.

## [2026-06] Posizione firma dinamica (dove compare {firma})
- `routes/documenti_genera.py`: nuovo `_find_firma_pos(pdf_bytes)` che cerca l'àncora "Firma del Contraente" nel PDF generato e la converte in coordinate OpenAPI (punti, origine bottom-left: `y = page_height - rect.y1`). In `genera_documento` (salva=true) la posizione viene salvata sull'allegato come `firma_pos: {page,x,y}` e ritornata nella risposta.
- `routes/esignature_it.py` (`invia_per_firma`): se l'allegato ha `firma_pos`, passa page/x/y a `esvc.create_signature` invece dei default fissi (x=331, y=45).
- Verificato: `/documenti/genera` ritorna `firma_pos` corretto (es. page1,x162,y674); allegato aggiornato.
