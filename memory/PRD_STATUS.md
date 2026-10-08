# Axicura CRM — Stato lavori (aggiornato 2026-10-08)

## Fix/feature completati in questa sessione (in PREVIEW, redeploy in corso)
- Import Omnia: controllo duplicati anagrafiche anche su Partita IVA (no doppioni aziende).
- Geocoding Nominatim vincolato all'Italia + fallback a cascata (GIÀ in produzione).
- FIX CRITICO creazione anagrafica: 500 da `sesso=""` → ora enum vuoti coerciti a None (routes/anagrafiche.py `_normalize_upper`).
- Feature pagamento PARZIALE estratto conto compagnie: `importo_versato` + partita residua (collezione `residui_compagnia`), ricorsivo. Backend verificato E2E (568.43 → 300+100+168.43, saldo 0).

## TODO prioritario (approvato dall'utente)
- FIX RAPPEL doppio conteggio saldo cassa:
  - Decisione utente: il rappel si chiude SOLO tramite l'estratto conto (incluso nella rimessa). L'azione "Incassa rappel" NON deve creare un secondo movimento in Prima Nota.
  - Correggere i dati tenant jacopo@schiantarelli.it: rappel CATTOLICA settembre 2026 registrati 2 volte (hanno sia `movimento_id` da incassa sia `movimento_pagamento_id` da rimessa). Rimuovere il movimento duplicato (quello da incassa) mantenendo la rimessa come fonte unica.
  - Rappel esempio: id bcf1700c-... 32,07€ del 17/09, compagnia CATTOLICA (95f7d1fa-...).

## Verifiche da fare
- Smoke test UI del dialog pagamento parziale (finora verificato solo backend via curl; webpack compila senza errori).
