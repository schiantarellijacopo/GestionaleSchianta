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
### 2026-06-25 (sessione corrente)
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
- **Piramide Soluzioni Redesign** (Release B) — blocchi impilati Adeguata/Non Adeguata + PDF
- **Refactoring `server.py`** (>7000 righe) → split in `/app/backend/routes/`
- **Refactoring `ania_importer.py`, `inps_calculator.py`** (parser complessi)

### P2
- **OCR allegati** (Fatture/Ricevute) con Gemini 3 Flash per auto-compilare data/importo/numero documento
- **Refactor `Anagrafiche.jsx`** componenti (perf)

### P3 (alla fine — esplicita richiesta utente)
- Integrazioni 3rd party: Google Calendar OAuth, Microsoft 365, WhatsApp, 3CX, Office 365

## Note importanti
- UI in **italiano**
- Download blob: usare `downloadFile` da `/app/frontend/src/lib/pdf.js`, MAI `window.open`
- Backend port 8001 (interno), frontend port 3000; tutto via `REACT_APP_BACKEND_URL` + prefisso `/api`
- KPI Brogliaccio sono **cumulativi** alla data selezionata
- Giorni chiusi non sono modificabili senza riaprire la chiusura
