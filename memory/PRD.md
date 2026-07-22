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

### Sessione 04/02/2026 (iter29)
- ✅ **ANIA Importer · Colonne mancanti (P0)**: aggiunto mapping colonne `frazionamento_share` (rec20 col AN → codici 1=annuale, 2=semestrale, 3=quadrimestrale, 4=trimestrale, 12=mensile, U/0/9=unica), `valore_ass_1/2/3` (rec30 col W → nuovo campo `capitale_assicurato` su Polizza + per-garanzia), `accessori_totale` (rec40 col AU → nuovo campo `accessori` su Titolo). Test unitario `test_ania_import.py` esteso con assert su tutti i nuovi campi. Modelli Pydantic aggiornati: `Polizza.capitale_assicurato`, `Titolo.accessori`.
- ✅ **ANIA Importer · Scadenza contratto**: usato `scadenza_effettiva` (rec20 col AK) come scadenza contratto della Polizza, con fallback su `scadenza_originale` (col AJ). Test aggiornato.
- ✅ **Multi-Tenant Foundation (Fase 1)**:
  - Nuovo modello `Tenant` (collezione `tenants`) — distinto dalla libreria `agenzie` (partner esterni).
  - Seed idempotente di 3 tenant: `principale` (Schiantarelli — dati reali), `demo` (staging con dati fittizi), `clean` (master pulito per onboarding nuove agenzie).
  - Campo `agenzia_tenant_id` aggiunto a `BaseDoc` → ereditato da tutte le entità (Anagrafica, Polizza, Titolo, Sinistro, Allegato, Movimento, Diario, ecc.).
  - `UserPublic.is_super_admin` — bypassa il filtro tenant per l'owner.
  - JWT include `agenzia_tenant_id` + `is_super_admin`.
  - Helper `tenant.py`: `tenant_filter(user)`, `assign_tenant(user, doc)`, `user_tenant_id(user)`, `is_super_admin(user)`, `migrate_existing_data_to_principale()`.
  - Startup automatico: seed tenants + migrate legacy → tutti i record esistenti assegnati al `tenant-principale-schiantarelli`. Migrazione idempotente.
  - Nuovo router `/api/tenants` (list/create/patch/delete/switch/migrate-legacy). Endpoint solo per super_admin. Utenti normali vedono solo il proprio.
  - **Migrazione eseguita in preview**: 862 anagrafiche + 851 polizze + 629 titoli + 44 sinistri + 33 allegati + 5 utenti + 12 compagnie + 248 mapping garanzie + tutti gli altri record → tutti al tenant principale. **Zero perdite dati**.
- ✅ **Storage Engine Abstraction (Fase 2)**:
  - Nuovo `StorageService` (`storage_service.py`) con driver pluggable: `emergent` (attivo), `s3` / `google_drive` / `onedrive` (placeholder in attesa credenziali).
  - Path canonico multi-tenant: `agencies/{tenant_id}/{clients|policies|claims|titles|companies}/{entita_id}/{filename}`.
  - `Allegato.storage_provider` traccia il provider usato per ogni file (recupero corretto in fase di download).
  - Fallback automatico su Emergent se un driver esterno non è configurato.

### Sessione 01/07 (iter28)
- ✅ **Libro Matricola · Annulla applicazione**: nuovo `POST /polizze/{pid}/applicazioni/{aid}/annulla` con motivo obbligatorio + data. Dialog frontend con preset motivi (Vendita/Demolizione/Furto/Restituzione leasing/Cessazione uso/Errore/Altro) + note libere.
- ✅ **Libro Matricola · Documenti per singolo veicolo**: dialog "Documenti veicolo" per applicazione con categorie predefinite (Libretto, Certificato assicurativo, Quietanza, Foto, Atto vendita, Altro). Filtro `applicazione_matricola_id` aggiunto a `GET /allegati`. Documenti restano collegati alla polizza ma filtrabili per veicolo/targa.

### P0 — In valutazione utente
- Test end-to-end auto-archiviazione Documenti Inbox con file reali.
- Test end-to-end nuovi dialog Annulla/Documenti veicolo in Libro Matricola.

### P1 — Prossime sessioni
- **Refactor `server.py`** (>10k righe) in router modulari per anagrafiche/polizze/titoli/sinistri/movimenti.
- **Storico Avvisi UI**: tab dedicato nella sezione Avvisi (backend già pronto).
- Chiarimenti PDF variazioni: #6 setup agenziale, #9 sezione regolazione, #10 elenco documenti, #21 pipeline email.
- Variazione PDF #3 Mappa anagrafica cliente (Leaflet + Nominatim).
- Variazione PDF #4 CRUD Raccolta Dati + Potenti Domande in Librerie.
- Variazione PDF #16 Associazione 3D Ramo→Prodotto→Garanzie.
- Variazione PDF #17 Diario cliente da invio avvisi.
- Variazione PDF #19+#20 Pagina "Alert Studio" per invio manuale bulk.

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
