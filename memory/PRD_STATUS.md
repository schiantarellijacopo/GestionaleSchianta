# Axicura CRM — Stato lavori (aggiornato 2026-10-08)

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
