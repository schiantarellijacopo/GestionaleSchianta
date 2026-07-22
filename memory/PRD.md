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
- ✅ ANIA importer + Multi-tenant + Storage abstraction + Query auto-filter + Super Admin Panel + Marketplace + Ticket + Audit Log + Resend Mock.
- ✅ **Super Admin dedicato & isolato dal frontend agenzia**:
  - Nuova login page dedicata `/admin-login` (dark theme viola con Shield icon) con credenziali pre-caricate.
  - Nuovo `SuperAdminLayout.jsx` (no sidebar clienti, solo header viola con logout).
  - `ProtectedRoute` esteso con `superAdminOnly` (route riservate) e `blockSuperAdmin` (redirect super_admin fuori dalle route client).
  - Login normale (`/login`) reindirizza super_admin a `/super-admin` invece di dashboard.
  - Utente dedicato `superadmin@assicura.it / Superadmin123!` creato via startup seed idempotente (aggiuntivo rispetto a `admin@assicura.it` che resta admin del tenant principale).
  - Test end-to-end: login OK, 4 endpoint super_admin HTTP 200, 0 anagrafiche/polizze visibili (GDPR).
- ✅ **Marketplace CRUD moduli (core + estensioni)**:
  - Nuovo campo `tipo_modulo: "core" | "estensione"` su `MarketplaceModule`.
  - Seed automatico di 23 moduli: **14 CORE** (Portafoglio, Anagrafica, Sinistri, Prima Nota, Provvigioni, ANIA Import, Statistiche, Alert, Chat Interna, WhatsApp Base, OCR, AI Assistente, Corsi IVASS, Marketing) + **9 ESTENSIONI** (Risk 3D, Firma Digitale, SMS 1000, WhatsApp Illimitato, Google Drive, OneDrive, S3, Stripe Pay, Pensioni INPS).
  - Endpoint PATCH/DELETE super_admin per catalog CRUD.
  - Tab Marketplace del pannello ora ha 2 sotto-tab: **Richieste** (attivazione dalle agenzie) + **Catalogo** (CRUD moduli) con filtri Core/Estensioni e form completo per creazione/modifica.

### Sessione 01/07 (iter28)
- ✅ **Multi-Tenant Foundation + Query Auto-Filter**: `Tenant` model, `TenantAwareDB` wrapper, migrazione ~2500 record al principale, isolamento reale attivo su tutti i router. Script `migrate_to_multitenant.py` per Railway prod.
- ✅ **Super Admin Panel (Platform Owner)** 🔒 GDPR-safe con 6 tab: Agenzie, Abbonamenti, Transazioni, Marketplace, Ticket Helpdesk, **Log Piattaforma**.
- ✅ **Storage Engine Abstraction**: driver `emergent` attivo, `s3`/`google_drive`/`onedrive` placeholder.
- ✅ **Marketplace + Ticket Helpdesk**: TopBar button + drawer per agenzie, gestione admin cross-tenant + email notifiche.
- ✅ **Resend Email Integration (MOCK MODE)**:
  - `/app/backend/resend_service.py` con toggle automatico mock/prod: se `RESEND_API_KEY` inizia con `re_test_mock` o vuota → log invece di invio reale.
  - 4 casi d'uso implementati: `send_ticket_reply`, `send_marketplace_activation`, `send_welcome_user`, `send_policy_expiring`.
  - Template HTML email-safe con inline CSS + CTA button.
  - Wire su endpoint `POST /super-admin/tickets/{id}/rispondi` (email all'agenzia), `PATCH /super-admin/marketplace/richieste/{id}/toggle` (attivazione modulo), `POST /super-admin/agenzie` (welcome admin iniziale).
  - `RESEND_API_KEY=re_test_mock_123` e `SENDER_EMAIL=onboarding@resend.dev` in `.env`. `resend==2.34.0` installato + in requirements.txt.
  - Per attivare invio reale: sostituire API key in `.env` con quella vera di Resend (`re_...`) + verificare dominio custom.
- ✅ **Super Admin Audit Log** (`super_admin_logs` collection):
  - Nuovo modulo `/app/backend/audit_super_admin.py` con helper `log_action(user, action_type, target_agency_id, details, request)`.
  - Registra automaticamente: timestamp, super_admin_id/email/name, action_type, target_agency_id/name, ip_address (con X-Forwarded-For), user_agent, details, meta.
  - 13 action_type catalogati: SUPER_ADMIN_LOGIN, AGENCY_CREATED/UPDATED/DELETED, TENANT_ACTIVATED/SUSPENDED/TRIAL_EXTENDED, MARKETPLACE_MODULE_TOGGLED/CREATED, TICKET_REPLIED/STATUS_CHANGED, DEMO_SEEDED, SUBSCRIPTION_UPDATED.
  - Nuovo router `/api/super-admin/logs` con filtri (agency_id, action_type, from/to date, search q) + `GET /export/csv`.
  - **Isolamento verificato**: utente non super_admin → HTTP 403 su `/api/super-admin/logs`. **Nessun utente tenant può accedere**.
  - Frontend: 6° tab "Log Piattaforma" in `/super-admin` con tabella, ricerca full-text, filtri combinati (agenzia + tipologia + date), export CSV con un click.

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
