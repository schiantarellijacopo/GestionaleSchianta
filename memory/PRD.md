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
- `SegnapostoSezione` ora: inserimento diretto nel corpo (prop onInsert), preferiti persistenti (localStorage), anteprima valori, filtri rapidi per gruppo. Riusato in dialog standalone (copia) e nell editor modelli (inserisce).
- Verificato end-to-end: insert, filtro gruppo, preferiti, esempi.
