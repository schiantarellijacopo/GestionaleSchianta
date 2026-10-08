# Axicura CRM — Stato lavori (aggiornato 2026-10-08)

## Estratto conto collaboratori + Brogliaccio (2026-10-08) — DA DEPLOYARE
Tre richieste utente, tutte implementate e testate (testing agent 100%):
1. **Brogliaccio pagamento provvigioni**: la riga "Pagamento provvigioni a ..." ora valorizza SOLO colonne SPESE e BANCA (uscita); colonna RITENUTA VUOTA. Fix in `_compute_brogliaccio` ramo `cat=="provvigioni"` uscita: `c_ritenuta=0.0`, `c_spese=importo` (server.py ~8282). La banca si valorizza via per_conto (conto risolto da tipo pagamento).
2. **Paga lista salvata**: nella card "Liste salvate da pagare" ogni bozza ha ora un pulsante verde **Paga** (oltre a Carica/elimina). Apre il PagaDialog precompilato coi titoli/voci della lista; a pagamento riuscito la bozza viene **eliminata** automaticamente (Provvigioni.jsx `pagaLista`/`payBozza`/PagaDialog `bozzaId`).
3. **Nascondi righe in bozza**: salvando una lista, i titoli/voci che ne fanno parte spariscono dalle tabelle "Provvigioni maturate" e "Voci manuali" (flag `in_bozza`/`bozza_id` aggiunti da `estratto_provvigioni` in server.py; frontend filtra `!r.in_bozza`/`!v.in_bozza`). Eliminando la lista ricompaiono.
- Extra: lo Storico pagamenti ora si aggiorna subito dopo "Paga lista" (prop `refreshKey`).
- HARDENING post code-review: (a) `paga_provvigioni` ora rifiuta titoli/voci già pagati (HTTPException 400) → niente doppi pagamenti; (b) il "Paga lista" passa SOLO i titoli/voci validi e non pagati (anteprima == importo addebitato anche con filtro date attivo); (c) `provvigioni_bozze` aggiunta a TENANT_SCOPED_COLLECTIONS (isolamento multi-tenant); (d) bottone "Registra pagamento" con guardia anti doppio-click. Tutto verificato via API.
- Credenziali test preview: qa.tester@schiantarelli.it / QaTest123! (tenant c5ae2d0e, dati reali collaboratori).
- RICHIEDE REDEPLOY su whatsapp-crm-146 + hard refresh.

## FIX chiusure Prima Nota (2026-10-08) — DEPLOY IN CORSO
- Sintomo utente: giornata con tasto verde "Chiudi giornata" (sembra aperta) ma alla chiusura dice "Giornata già chiusa"; manca il tasto "Riapri".
- Root cause: `_compute_brogliaccio` (server.py ~riga 8587) faceva `db.chiusure_giorno.find_one({"data": data})` SENZA filtro `riaperta_at`. Con record DUPLICATI per lo stesso giorno (una riaperta + una richiusa, es. 2026-09-30 su prod) la find_one poteva restituire quella RIAPERTA → `chiusa=False` → pulsante verde, ma `chiudi_giorno` trovava la chiusura ATTIVA → errore "già chiusa".
- FIX: ora cerca prima la chiusura ATTIVA `{"data": data, "riaperta_at": None}`, fallback alla riaperta solo per display. Verificato su preview: brogliaccio ritorna `chiusa=True` → compaiono "Invia commercialista" + "Riapri".
- NB: `shared.giornata_chiusa`, `/giornate-chiuse`, `/giornata-stato` erano già corretti (filtravano riaperta_at=None).
- RICHIEDE REDEPLOY su whatsapp-crm-146 (l'utente testa in produzione) + hard refresh.
- Data fix preview: richiuse 11/09, 15/09, 24/09 del tenant c5ae2d0e (prod ha DB separato: lì la correzione è automatica col fix del codice, nessun intervento dati necessario grazie alla query corretta).

## Completati e in produzione
- Import Omnia: controllo duplicati anagrafiche anche su Partita IVA.
- Geocoding Nominatim vincolato all'Italia + fallback a cascata.
- FIX creazione anagrafica: 500 da `sesso=""` → enum vuoti coerciti a None (routes/anagrafiche.py `_normalize_upper`).
- Feature pagamento PARZIALE estratto conto compagnie: `importo_versato` + partita residua (collezione `residui_compagnia`), ricorsivo.
- FIX regression: bottone "Conferma versamento" bloccato quando il totale è <= 0 (es. versamento rappel/credito negativo). Ora la logica parziale si applica solo a totali positivi (EstrattoContoCompagnie.jsx PagamentoDialog). [redeploy 2026-10-08]

## Caso rappel 32,07 CATTOLICA (tenant jacopo@schiantarelli.it)
- Diagnosi: il +32,07 su BPER SONDRIO e SALDO CASSA CMP derivava dalla rimessa del 01/10 dove il rappel era scalato dal versamento (Scenario B). Scenario A corretto = rappel credito, banca paga pieno (212.513,53 / 40.949,81).
- Verificato empiricamente: riaprire+richiudere tutte le 14 giornate chiuse NON cambia i saldi (brogliaccio ricalcola live). Il problema NON erano gli snapshot congelati.
- RISOLTO DALL'UTENTE: ha corretto lui la rimessa. Nessun intervento richiesto.

## TODO futuri (approvati ma non ancora fatti)
- Logica rappel: idealmente il rappel non dovrebbe mai essere scalato dal versamento (deve restare credito). Valutare fix in paga-titoli se il caso si ripresenta.
- "Incassa rappel" non dovrebbe creare un secondo movimento in Prima Nota (decisione utente precedente) — da implementare se riemerge il doppio conteggio.

## Verifiche ancora utili
- Smoke test UI del dialog pagamento parziale (finora verificato backend via curl + logica frontend).
