# Programma Assicurativo - PRD

## Problem Statement (originale)
Programma Assicurativo che comprende la gestione di tutti i documenti e le fasi dell'assicurazione, anagrafica polizze titoli sinistri statistiche contabilità prima nota estratti conto integrazione con whatsapp 3 cx google drive google calendar google contact one drive office 365 integrazione con email pipline gestione banca email avvisi clienti livelli di visibilità per admin collaboratori dipendenti, possibilità di caricare corsi e renderli visibili solo a chi voglio sia lato dipendenti sia lato clienti, con possibilità di tracciatura quanto ha visto di video. registrare tutte le attività che vengono fatte sul sistema intervista al cliente con una bella raccolta dati con possibilità di collegamento anagrafiche e sviluppo albero genealogico. calcolo delle pensioni di invalidità inablità superstite con caricamento di estratto conto contributivo inps. voglio alimentare i miei dati ogni giorno con questa importazione gestione di più compagnie

## User choices (iter 1, 22 giu 2026)
- Auth: JWT custom (no Google)
- Lingua: Italiano
- Modulo corsi: rimandato a fase 2
- Importazione: tracciato ANIA giornaliero (16 record types: rec00, rec10, rec20, rec21, rec24, rec30, rec40, rec41, rec42, rec43, rec50, rec51, rec52, rec70, rec100, rec101)

## User personas
- **Admin**: accesso completo al sistema (gestione utenti, compagnie, importazione, log)
- **Collaboratore**: come admin tranne cancellazioni
- **Dipendente**: vede tutto il portafoglio, crea/modifica, no cancellazioni, no compagnie/import/log
- **Cliente**: vede solo le proprie polizze, sinistri, estratto conto, calcola pensione

## Architettura
- Backend: FastAPI (Python 3.11) + Motor (MongoDB async) + JWT (bcrypt + cookie httpOnly)
- Frontend: React 19 + Vite/CRA + Tailwind + shadcn/ui + Recharts + Lucide
- Storage: MongoDB (`test_database`)
- Auth: httpOnly cookie + Authorization Bearer fallback

## Funzionalità implementate (22 giu 2026 - MVP iter 1)
- [x] Auth multi-ruolo (4 ruoli) + seed automatico admin/collaboratore/dipendente/cliente
- [x] Multi-compagnia (CRUD compagnie + collegamento polizze)
- [x] Anagrafiche clienti (persona fisica/giuridica) con ricerca CF/email/nome
- [x] Albero genealogico: relazioni bidirezionali tra anagrafiche
- [x] Intervista cliente (raccolta dati strutturata: familiare/lavorativa/patrimoniale/coperture/obiettivi)
- [x] Polizze (CRUD, filtri stato/ramo, dettaglio con titoli+sinistri)
- [x] Titoli (CRUD, filtri stato, incasso → crea movimento contabile automatico)
- [x] Sinistri (CRUD denunce, riserva/liquidazione, filtri stato)
- [x] Contabilità: Prima nota (entrate/uscite/saldo) + Estratto conto cliente con saldo progressivo
- [x] Importazione ANIA giornaliera: upload ZIP/CSV, parser di tutti i 16 record types, log storico
- [x] Calcolo pensioni INPS: invalidità / inabilità / superstite (coefficienti trasformazione 2025)
- [x] Parser semplice estratto contributivo INPS (.txt)
- [x] Pipeline email: bozza/coda/inviata + generazione automatica avvisi scadenze polizze
- [x] Log attività utenti (login, CRUD, import, calcoli)
- [x] Dashboard con statistiche multi-ruolo (cliente vede solo i propri dati)
- [x] Role-based visibility nel backend e route guard frontend

## API Endpoints principali (tutti sotto /api)
- POST /auth/login, /auth/logout, GET /auth/me, POST /auth/users (admin)
- /anagrafiche (+ /relazioni), /anagrafiche/{id}/interviste
- /compagnie, /polizze, /polizze/{id}, /titoli, /titoli/{id}/incassa
- /sinistri, /contabilita/movimenti, /contabilita/prima-nota, /contabilita/estratto-conto/{ana_id}
- /import/ania, /import/storico
- /pensioni/calcola, /pensioni/parse-estratto, /pensioni/storico
- /email, /email/{id}/invia, /email/avvisi-scadenze
- /attivita, /stats/dashboard

## Backlog (P0 fase 2)
- [ ] **Modulo Corsi**: upload video, assegnazione per ruolo/utente, tracciamento progresso visualizzazione
- [ ] **Integrazione SMTP reale** (Resend o SendGrid) per invio email (oggi mock)
- [ ] **Integrazione WhatsApp** (Twilio/Meta Business Cloud API) per avvisi
- [ ] **Integrazione 3CX** (centralino) - click-to-call su anagrafica
- [ ] **Google Drive / OneDrive / Office 365** - sync allegati polizze
- [ ] **Google Calendar / Contacts** - sync appuntamenti e rubrica
- [ ] **Allegati documenti** (storage S3-like) per polizze, sinistri, anagrafiche
- [ ] **Pipeline email avanzata**: template engine, scheduling cron, batch send
- [ ] **Statistiche compagnia/agente/ramo**: report PDF, esportazioni Excel

## Backlog (P1)
- [ ] Validation Pydantic dedicata su POST (oggi ritorna 500 invece di 422 su errori)
- [ ] Refactor server.py → router per dominio (anagrafiche, polizze, contabilita)
- [ ] Filtro/paginazione lato server più ricco per liste >500 records
- [ ] Notifiche realtime (WebSocket) per nuovi sinistri/titoli da incassare
- [ ] Dashboard customizzabile per ruolo
- [ ] Audit log immutabile + esportazione

## Test credentials (auto-seeded)
| Ruolo | Email | Password |
|---|---|---|
| admin | admin@assicura.it | Admin123! |
| collaboratore | collaboratore@assicura.it | Collab123! |
| dipendente | dipendente@assicura.it | Dipendente123! |
| cliente | cliente@assicura.it | Cliente123! |

## Test risultati (iter 1 - 22 giu 2026)
- Backend: 26/26 test pytest passati (100%)
- Frontend: tutti i flussi testati passati (100%)
- Fix applicati post-test: visibility filter su /stats/dashboard pipeline (premi/incassi mensili per cliente), route guard frontend con redirect, card "Crescita" nascosta al cliente.
