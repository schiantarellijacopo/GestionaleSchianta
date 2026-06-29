# Programma Assicurativo — PRD

## Visione
CRM completo per agenzie assicurative italiane. Gestisce anagrafiche, polizze, titoli, sinistri, P&L, marketing, AI insights, OCR documenti, ritenute compagnia/collaboratori/agenzie partner, calcoli pensione INPS.

## Stack
- **Backend**: FastAPI + MongoDB (Motor). Server.py >10.000 righe (refactor backlog).
- **Frontend**: React + Tailwind + Shadcn UI.
- **Integrazioni**: Emergent LLM Key (Claude 4.5 Sonnet text, Gemini 3 Flash OCR), IMAP/SMTP nativo, Twilio/Spoki (backlog), Stripe (backlog).

## Persona
Agente assicurativo italiano + collaboratori + dipendenti + clienti.

## Implementato

### Sessioni precedenti
- Anagrafiche multi-ruolo, Polizze, Titoli, Sinistri, Movimenti, Conti contabili.
- ANIA import, scadenzario, P&L, dashboard collaboratori, statistiche con Indice ISA.
- Trattative, Voucher, RitenuteHub (compagnia/collaboratori/agenzie partner).
- Documenti Inbox OCR (Gemini) → auto-extract avatar carta d'identità.
- Setup Iniziale, Scambio Dati, Documenti Inbox.
- Alert automatici T+0 → T+15.
- Backend P1/P2: Libro matricola, OCR bilancio, corsi IVASS, customer insights, dropzone visibile/nascosto, storico avvisi.

### Sessione 29/06 (iter26)
- ✅ **Search globale espansa**: ricerca per ramo, prodotto, telefono, email, cellulare, comune, indirizzo, professione, tags, targa, oggetto_assicurato, contraente. Aggiunte sezioni Titoli e Compagnie nei risultati.
- ✅ **Voucher dual-assignment**: nuovo dialog (sostituisce `window.prompt`) per assegnare il voucher contemporaneamente a Collaboratore E Cliente. Backend `POST /api/voucher/{id}/assegna` accetta entrambi.
- ✅ **Anagrafica · Raccolta Dati**: nuovo tab strutturato (motivazioni, appetito rischio, famiglia, lavoro, aziende, risparmi, immobili, hobby, bilancio familiare, obiettivi, gestione rischi). Schema dal PDF "RACCOLTA DATI".
- ✅ **Anagrafica · 30 Potenti Domande**: tab onboarding con elenco numerato e progress %. Schema dal PDF "Le potenti domande del primo appuntamento".
- ✅ **Anagrafica · Salute Fiscale** (solo aziende): OCR bilancio Gemini → KPI (ROE, ROS, leva, oneri/ricavi, pressione fiscale), score rischio default 0-10, cross-sell AI (D&O, Cyber, Key Man…).
- ✅ **Customer Insights widget**: snapshot KPI cliente in cima al tab Anagrafica.
- ✅ **Polizza · Regolazione Premio dialog**: calcolatore con storico per polizze con flag `regolazione_premio`.
- ✅ **Cervello · OCR Bilancio**: pulsante caricamento PDF/JPG bilancio → estrazione automatica voci di costo.
- ✅ **Avvisi · Storico registrazione**: WhatsApp/PDF/Email ora chiamano `/storico-avvisi/registra` e mostrano toast di conferma.
- ✅ **Librerie · Modelli PDF placeholder**: tabella raggruppata per categoria (Cliente, Polizza, Veicolo, Compagnia, Titolo, Sinistro, Operatore, Agenzia, Totali, Sistema, Marketing) con +70 placeholder cliccabili.
- ✅ **Lead Liste · Parser RHX**: supporto multi-foglio (AutoConvenienTe + DNA senza RCA), normalizzazione indirizzo `VIA X N-CAP-CITTA-PROV`, privacy S/N → boolean, alias colonna IDContatto, Profilo Cliente, Esito Direzionale, Stato Ultimo PUC, Aggiorna Attivazione.
- ✅ **Documenti Inbox · Auto-archiviazione**: quando OCR ha confidenza alta + anagrafica trovata, il documento viene AUTOMATICAMENTE archiviato nella sezione corretta (carta_identita → documento_identita, libretto → libretto_circolazione, ecc.) senza intervento utente. Drag&drop attivo. Fallback a "Rivedi e archivia" se confidenza media/bassa.
- ✅ **Bugfix**: salute-fiscale 404 errato con projection (fix `if ana is None`), Gemini OCR errors 500→502, React key warning in TitoliByContraente (Fragment con key), label "CARTA D&RSQUO;IDENTITÀ" → apostrofo corretto.

## Backlog priorità

### P0 — In valutazione utente
- Test end-to-end auto-archiviazione Documenti Inbox con file reali.

### P1 — Prossime sessioni
- **Twilio/Spoki**: integrazione SMS/WhatsApp reale (credenziali utente).
- **Refactor `server.py`** (>10k righe) in router modulari per anagrafiche/polizze/titoli/sinistri/movimenti.
- **Storico Avvisi UI**: tab dedicato nella sezione Avvisi (backend già pronto).
- **Libro Matricola pagina standalone** (oltre al tab in PolizzaDetail).

### P2 — Future
- Stripe billing.
- Dashboard collaboratore con report mensile auto.
- Migrazione storica MovimentiContabili per "Titoli coperti".
- Cron job notifica IVASS quando un collaboratore < 50% delle 30 ore annuali.

## Credenziali test
File: `/app/memory/test_credentials.md`
- admin@assicura.it / Admin123!
- collaboratore@assicura.it / Collab123!
- dipendente@assicura.it / Dipendente123!
- cliente@assicura.it / Cliente123!
