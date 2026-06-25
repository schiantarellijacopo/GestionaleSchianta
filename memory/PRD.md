# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), avvisi scadenze.

## Personas
- Admin / Collaboratore / Dipendente / Cliente

## Latest Sessions (Feb 2026)

### Iter 16: Mappa, Indirizzi, Network (DONE)
- ✅ `<AddressAutocomplete>` (Nominatim, gratis) usato in NuovaAnagrafica + AnagraficaDetail
- ✅ Pagina Mappa clienti potenziata (cluster, layer Standard/Consumatore/Satellitare, toggle Clienti/Prospect, ricerca, tag)
- ✅ Relazioni network bidirezionali (genitore/figlio/coniuge/... + legale_rappresentante/rappresenta/socio/dipendente_di/datore_lavoro_di)
- ✅ `GET /anagrafiche/{aid}/network` con totali aggregati premi/provvigioni
- ✅ NetworkPositionCard in AnagraficaDetail Tab Albero

### Iter 17: Dashboard Tasks + Filtri + KPI (DONE)
- ✅ Dashboard "Da fare": 8 task azionabili con conteggio + click-to-filter (Compleanni oggi/7gg, Documenti scaduti/in scadenza, Sospesi >5gg, Sinistri >30gg, Polizze in scadenza, Provvigioni da liquidare)
- ✅ Filtri URL ?compleanno=oggi|settimana ?doc=scaduti|in_scadenza ?gg_min=N — la pagina destinazione mostra banner "Filtro attivo" + "Rimuovi filtro"
- ✅ 4 KPI Anagrafiche (Privati/Aziende/Condomini/Parrocchie) con bordo sx colorato
- ✅ Sezione TAG nella scheda Anagrafica (TagsEditor con autocomplete su /api/anagrafiche/tags)

### Iter 18: UX Anagrafiche + LR (DONE)
- ✅ Email cliccabile (mailto:) + Telefono cliccabile (tel:)
- ✅ Formattazione automatica numero "+39 347 000 9438" (helper /app/frontend/src/lib/phone.js)
- ✅ Colonna "Collaboratore" sostituisce "Preventivi" nella lista
- ✅ Pulsante shortcut "Collega azienda (come LR)" nel Tab Albero (con guida flusso)
- ✅ Pulsanti "Modifica" e "Rimuovi" relazione più visibili (bordi + icone)

### Iter 19: Titoli + Sidebar personalizzabile (DONE)
- ✅ Rimosso preset "Storico incassati" e "Coperti non pagati" dai tab Titoli
- ✅ Rinominato "In scadenza 15gg" → "Scadute da 15gg" (logica corretta: titoli scaduti)
- ✅ Link sidebar "Titoli storici" continua a funzionare via ?preset=storico
- ✅ Sidebar personalizzabile: drag-drop ordinamento + hide/show per voce (Eye/EyeOff) + reset predefinito

## Endpoints (selezione recente)
- GET /api/geo/suggest?q=
- GET /api/anagrafiche/stats — 4 KPI categorie
- GET /api/anagrafiche/{aid}/network
- GET /api/anagrafiche/tags
- GET /api/dashboard/tasks — 8 task azionabili
- GET /api/stampa/titoli/sospesi — PDF con data odierna

## Backlog / Roadmap
### P1
- Personalizzazione KPI Anagrafiche basata su TAG dell'agenzia (card custom)
- OCR Libretto/Fatture con Gemini 3 Flash su Documenti polizza
- Piramide Soluzioni Redesign (Release B)

### P2
- Integrazioni Google Calendar / Microsoft 365 / WhatsApp / SMS
- Refactor server.py (>9700 righe) in /backend/routes/
- Risoluzione import circolare in auth.py

## File chiave creati / modificati
- /app/backend/server.py — endpoint stats/network/tags/dashboard-tasks/geo-suggest
- /app/backend/geocoder.py — cerca_suggerimenti()
- /app/frontend/src/components/AddressAutocomplete.jsx — NEW
- /app/frontend/src/components/TagsEditor.jsx — NEW
- /app/frontend/src/lib/phone.js — NEW (formattazione +39)
- /app/frontend/src/pages/MappaClienti.jsx — rewrite (cluster + layer)
- /app/frontend/src/pages/Anagrafiche.jsx — KPI + RigaAnagrafica espandibile + filtri URL
- /app/frontend/src/pages/AnagraficaDetail.jsx — Tab Albero esteso (LR/aziende) + NetworkPositionCard + Tag editor
- /app/frontend/src/pages/Dashboard.jsx — DashboardTasks (8 task)
- /app/frontend/src/pages/Titoli.jsx — preset rinominati
- /app/frontend/src/pages/TitoliSospesi.jsx — filtro gg_min + telefono cliccabile
- /app/frontend/src/components/Sidebar.jsx — hide/show + drag-drop

## Credenziali test
Vedi `/app/memory/test_credentials.md` (admin@assicura.it / Admin123!)
