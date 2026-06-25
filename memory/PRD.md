# Programma Assicurativo — PRD

## Problem Statement
CRM full-stack per agenzie assicurative italiane: anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), Analisi Cliente con calcolo INPS, importer ANIA, generazione PDF modulare.

## Stack
- Frontend: React + Tailwind + Shadcn UI
- Backend: FastAPI + MongoDB
- Integrazioni: Gemini 3 Flash (OCR), pdfplumber, ReportLab, APScheduler, Nominatim

## Architettura
- `/app/backend/server.py` (monolite ~7000 righe — refactor pendente)
- `/app/backend/avvisi_scadenze.py` (nuovo) — cron giornaliero scadenze
- `/app/backend/ania_importer.py`, `inps_calculator.py` (parser)
- `/app/backend/pdf_brogliaccio.py`, `pdf_sezioni.py` (ReportLab)
- `/app/frontend/src/components/DialogIncasso.jsx` — incasso semplice (TitoliSospesi)
- `/app/frontend/src/components/DialogIncassoCopertura.jsx` — flusso unificato per Titoli (replica facsimile)

## Cosa è stato implementato
### 2026-06-25 (sessione corrente, parte 2)
- ✅ **Breakdown provvigioni a 3 valori** (Totale / Collaboratore / Margine) in Polizza e Titoli, applicato sulla provvigione REALE della polizza/titolo + % schema collaboratore
- ✅ Helper backend `_provv_breakdown()` riusabile
- ✅ **Tab Sinistri** in `PolizzaDetail.jsx` con lista sinistri e link Apri elenco completo
- ✅ Filtro `polizza_id` + auto-focus su Sinistri.jsx
- ✅ **Pagina Avvisi** (`/avvisi`) con KPI (polizze in scadenza, titoli, premio a rischio, importi da incassare), tab Polizze/Titoli, pulsanti per riga: Email (dialog precompilato + invio SMTP / fallback mailto), WhatsApp (wa.me deeplink), SMS (placeholder Twilio fine progetto)
- ✅ **Rubrica Compagnie** (`/rubrica-compagnie`) con CRUD: ContattoCompagnia (nome, cognome, ruolo, ufficio, email, telefono, cellulare, interno, note). Endpoints `/api/contatti-compagnia`. Vista raggruppata per compagnia.
- ✅ **Titoli storici** (preset `?preset=storico`) — voce dedicata in sidebar che filtra solo titoli `incassato`
- ✅ Dialog "Modifica titolo" semplificato: rimossi Stato (auto), Conto/Banca; Mezzo pagamento ora **dropdown** (bonifico, RID/SDD, contanti, assegno, POS, bollettino, carta_credito, compagnia, altro)
- ✅ Sidebar pulita: rimossi doppioni (`Titoli (incassi)` ridotto a `Titoli storici`, `Compagnie` rimossa a favore della tab nelle Librerie + nuova Rubrica)
- ✅ Click su riga in Titoli ora apre Dialog Modifica (estratto in componente condiviso `/app/frontend/src/components/TitoloDialog.jsx`)

### 2026-06-25 (sessione corrente, parte 1)
- ✅ KPI **Sospesi** in Brogliaccio mirror esatto del totale `/titoli/sospesi` (`_total_sospesi_as_of`)
- ✅ **Riepilogo per collaboratore** nella pagina Titoli Sospesi (groupBy + totale)
- ✅ **Avvisi di Scadenza**: cron 08:00 (APScheduler) + `GET /avvisi-scadenze/preview`, `POST /esegui`, `GET /log` + email HTML
- ✅ **Flusso incasso con residuo**: opzione "sconto" (uscita in Prima Nota) OPPURE "sospeso" (genera titolo residuo da_incassare)
- ✅ **Dialog "Incasso / Copertura" unificato** replica facsimile cliente: tabella cyan, checkbox Copertura + Incasso, sub-opzioni email, "Pagamento in direzione"
- ✅ Aggiunti campi Titolo: `data_emissione`, `ora_effetto`, `pagamento_in_direzione`; tipo "quietanza"
- ✅ Endpoint `POST /titoli/notifica-copertura` (email a operatori/contraenti)

### Sessioni precedenti
- Voci manuali estratto conto collaboratori
- Coniuge/figli attributi + Albero genealogico
- Filtri e export CSV/XLSX/PDF Polizze
- Allegati su Prima Nota e Titoli
- Brogliaccio redesign + Daily Closure + PDF + KPI cumulativi
- Logica contabile avanzata (premi, provvigioni, sconti, rimesse)
- Dati Compagnie tab
- ANIA importer (Garanzie, Operatori, premio_netto, tasse, ssn)
- Polizza Modifica/Elimina
- Global fix download PDF (downloadFile)

## Backlog
### P1
- **Tab "Documenti" in PolizzaDetail** (allegati polizza, da implementare)
- **OCR Libretto veicolo** (Gemini 3 Flash) → auto-fill targa/marca/modello/immatricolazione + auto-save PDF in polizza
- **OCR Fattura / Busta paga** (Gemini 3 Flash) → estrazione dati per Analisi Cliente
- **Piramide Soluzioni Redesign** (Release B) — blocchi impilati Adeguata/Non Adeguata + PDF
- **Refactoring `server.py`** (>7000 righe) → split in `/app/backend/routes/`
- **Refactoring `ania_importer.py`, `inps_calculator.py`** (parser complessi)
- **Librerie · collegamento Metodi pagamento ↔ Banche** (refactor lib `conti-cassa`)

### P2
- **Refactor `Anagrafiche.jsx`** componenti (perf)
- **Avviso SMS** via Twilio (collegamento già predisposto in pagina Avvisi)
- **Avviso WhatsApp Business API** (al momento usa `wa.me` deeplink)

### P3 (alla fine — esplicita richiesta utente)
- Integrazioni 3rd party: Google Calendar OAuth, Microsoft 365, WhatsApp, 3CX, Office 365

## Note importanti
- UI in **italiano**
- Download blob: usare `downloadFile` da `/app/frontend/src/lib/pdf.js`, MAI `window.open`
- Backend port 8001 (interno), frontend port 3000; tutto via `REACT_APP_BACKEND_URL` + prefisso `/api`
- KPI Brogliaccio sono **cumulativi** alla data selezionata
- Giorni chiusi non sono modificabili senza riaprire la chiusura
