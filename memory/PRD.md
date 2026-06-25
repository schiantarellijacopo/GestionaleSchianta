# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Full-stack: anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), analisi cliente, avvisi scadenze.

## Personas
- Admin / Collaboratore / Dipendente / Cliente

## Latest Session (Feb 2026)

### A) PACCHETTO MAPPA & INDIRIZZI — DONE
- ✅ `GET /api/geo/suggest?q=` → Nominatim autocomplete (limit 6, IT)
- ✅ Componente `<AddressAutocomplete>` riusato in: NuovaAnagrafica + AnagraficaDetail. Al click suggerisce e geolocalizza in automatico (lat/lng/comune/cap/provincia precompilati)
- ✅ Pagina Mappa clienti potenziata: cluster marker (leaflet.markercluster), 3 layer (Standard / Consumatore CartoDB Voyager / Satellitare ESRI), toggle Clienti (blu) / Prospect (rosso), ricerca, filtro tag, popup ricco con "Apri scheda"
- ✅ Backend `/geo/anagrafiche` arricchito con `is_cliente` (ha ≥ 1 polizza attiva)

### B) PACCHETTO COLLEGAMENTI ANAGRAFICHE — DONE
- ✅ Nuove relazioni in `parente_di` bidirezionali: legale_rappresentante / rappresenta, socio, dipendente_di / datore_lavoro_di — oltre alle preesistenti (genitore/figlio/coniuge/fratello/nonno/...)
- ✅ Inverse Map auto-suggerite in UI quando si sceglie la relazione
- ✅ Backend `GET /anagrafiche/{aid}/network` → restituisce root + collegati con per ognuno: n_polizze_attive, n_preventivi, n_polizze_totali, premio_totale, provvigioni_totale + totali aggregati network
- ✅ Frontend in Tab "Albero genealogico": Card "Posizione assicurativa del network" mostra tabella con totali per collegato + riga "Totale network"
- ✅ Frontend in lista Anagrafiche: righe espandibili (chevron) che mostrano network

### C) DASHBOARD ANAGRAFICHE — DONE
- ✅ Backend `GET /anagrafiche/stats` → 4 categorie (privati / aziende / condomini / parrocchie) con conteggi e premi
- ✅ 4 KPI cards in cima alla pagina /anagrafiche (Privati, Aziende, Condomini, Parrocchie) con totale Premi
- ✅ Categorizzazione automatica: euristica su ragione_sociale (CONDOMINIO, PARROCCHIA) + tipo (persona_fisica/giuridica)

### D) BUG FIX & FEATURE PRECEDENTI (iter15) — DONE
- ✅ Bug Brogliaccio: uscite generiche (PRELIEVO, spese, anticipi out) NON più in colonna TOTALE → totali_giornata.totale = solo incassi_premio
- ✅ Dashboard: 15 elementi cliccabili (6 Stat + 2 chart + 4 KPI + 3 subcard) navigano alle relative sezioni
- ✅ PDF "Sospesi Anticipi" con data di stampa odierna (endpoint + pulsante)
- ✅ Centralizzazione `useMezziPagamento` in 5 dialog (Provvigioni, EstrattoContoCompagnie, Titoli, AnagraficaDetail, PolizzaDetail)
- ✅ Backend syntax error in `titoli_sospesi()` riparato

## Architecture
- `/app/backend/server.py` (~9700 righe — refactor pendente)
- `/app/backend/db_models.py` — Anagrafica con `parente_di: List[dict]`
- `/app/backend/geocoder.py` — Nominatim wrapper + `cerca_suggerimenti()`
- `/app/frontend/src/pages/Anagrafiche.jsx` — lista con KPI + righe espandibili
- `/app/frontend/src/pages/AnagraficaDetail.jsx` — Tab Albero + NetworkPositionCard
- `/app/frontend/src/pages/MappaClienti.jsx` — mappa cluster + layer switcher
- `/app/frontend/src/components/AddressAutocomplete.jsx` — componente riusabile

## Endpoints Aggiunti
- `GET /api/geo/suggest?q=` — Nominatim autocomplete
- `GET /api/anagrafiche/stats` — 4 KPI categorie + premi
- `GET /api/anagrafiche/{aid}/network` — root + collegati con totali
- `GET /api/stampa/titoli/sospesi` — PDF (creato iter precedente)

## Backlog / Roadmap
### P1
- Visualizzazione albero genealogico più visiva (svg ramificato)
- Bottone "Aggiungi LR" rapido dalla scheda Azienda (shortcut)
- Filtri categoria su KPI cards cliccabili (al click filtra la tabella)
- OCR Libretto/Fatture con Gemini 3 Flash su Documenti polizza
- Piramide Soluzioni Redesign (Release B)

### P2
- Integrazioni: Google Calendar / Microsoft 365 / WhatsApp / SMS
- Refactor server.py (>9700 righe) in `/backend/routes/`
- Risoluzione import circolare in auth.py
- Estrazione form sections AnagraficaDetail per perf

## Credenziali test
Vedi `/app/memory/test_credentials.md` (admin@assicura.it / Admin123!)
