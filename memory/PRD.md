## Programma Assicurativo - PRD (FastAPI + React + MongoDB)

### Original problem statement
CRM Assicurativo per agenzie italiane. Gestione completa di anagrafiche (con albero familiare + intervista), polizze, titoli (quietanze), sinistri, contabilità (prima nota, brogliaccio, estratti conto), statistiche. Multi-compagnia. Calcolo pensione INPS (vecchiaia, invalidità, reversibilità) con import PDF estratto contributivo. Import ZIP ANIA giornaliero. Ruoli: admin, collaboratore, dipendente, cliente. Stampe PDF complete con intestazione agenzia.

Integrazioni richieste: WhatsApp, 3CX, Google Drive, Google Calendar, Google Contacts, OneDrive, Office 365, pipeline email.

UI in italiano, Shadcn/Tailwind.

---

### Implementato (cronologia)
- 2026-06-22 (fork 2):
  - **Importer ANIA testato**: ZIP completo (rec10, rec20, rec21, rec30, rec40, rec50) - parsing veicolo + garanzie + diritti + BM + franchigia + massimali + rinuncia rivalsa. Idempotente su re-import.
  - **Librerie / Sezione Azienda** (nuova): dati intestazione agenzia (P.IVA, RUI, IBAN, indirizzo, contatti, logo). Endpoint `/api/librerie/azienda` (GET/PUT) + `/api/librerie/azienda/logo`.
  - **Stampe PDF con intestazione**: tutte le stampe (anagrafiche/polizze/titoli/sinistri/prima nota/estratto conto/provvigioni) ora mostrano logo + ragione sociale + indirizzo + RUI + footer.
  - **Sistema provvigionale** (nuovo): collection `schema_provvigionale` con risoluzione gerarchica (collaboratore + compagnia + ramo). Endpoint CRUD `/api/librerie/schema-provvigionale` + endpoint risoluzione.
  - **Utenti/Collaboratori esteso**: dati fiscali (CF, P.IVA, IBAN), provvigione default, ritenuta acconto, INPS. Documenti: firma digitale, carta identità, casellario, carichi pendenti, IBAN (upload via `/api/auth/users/{uid}/documenti/{tipo}`). Corsi/attestati (`/api/auth/users/{uid}/corsi`).
  - **Storage endpoint generico**: `/api/storage/{path}` con ACL (solo proprietario o admin per file in /users/).
- Fork precedente:
  - Base CRUD: anagrafiche, polizze, titoli, sinistri, compagnie, accounting
  - JWT auth + RBAC (admin/collaboratore/dipendente/cliente)
  - INPS pension calculator con pdfplumber
  - Titoli: rich filters, bulk incasso/copertura con allegato + email
  - Diario cliente automatico (chat, email, doc)
  - Auto-tag clienti + Newsletter backend queue
  - Global Search TopBar
  - Brogliaccio + estratti conto PDF
  - Object storage Emergent
  - UpperInput normalizzazione

### Pending / In progress (NUOVE richieste dell'utente 2026-06-22)

#### P0 - User Experience (richieste hot)
1. **Geolocalizzazione automatica anagrafiche**: appena si inserisce indirizzo → calcolo lat/lng (usare Nominatim/OpenStreetMap gratuito).
2. **Colorazione anagrafiche in lista**: BLU=con polizze, ROSSO=senza polizze, VERDE=condomini.
3. **Tag cliccabili in lista anagrafiche** che filtrano e portano alla scheda cliente.
4. **Operatore assegnato per riga**: in anagrafiche, polizze, titoli, sinistri permettere assegnazione collaboratore/sub-agente con dropdown; mostrare nome collaboratore (non solo id).
5. **Pensione INPS - ripristinare**: upload PDF estratto conto contributivo + modificabilità di tutti i campi del calcolo (regressione segnalata).
6. **Cross-navigation completa**: da sinistri/polizze/titoli si naviga tra entità correlate; tutto modificabile.

#### P0 - Contabilità (nuove voci)
7. **Sezione Contabilità: aggiungere "Titoli" link**.
8. **Estratto conto compagnie**: per ogni compagnia, dare/avere periodico.
9. **Saldo cassa compagnie**: vista riassuntiva dei saldi compagnie (premio - provvigioni se trattenute).
10. **Stampe per ogni sezione** (PDF) - già fatto per anagrafiche/polizze/titoli/sinistri/prima nota, manca: estratto conto compagnie, saldo cassa compagnie, sinistri singoli, scheda polizza completa, brogliaccio (già fatto).

#### P1 - Integrazioni Calendario / Contatti
11. **Calendario agenzia** + **calendario per operatore** con eventi (scadenze polizze, appuntamenti, sinistri).
12. **Sync Google Calendar** (eventi).
13. **Sync Microsoft 365 / Outlook Calendar**.
14. **Sync Google Contacts** / Outlook Contacts.

#### P1 - OCR / AI
15. **OCR carta d'identità**: caricamento CI → auto-compila campi anagrafici (CF, scadenza, numero, comune emissione, data nascita) → usare LLM con visione (Gemini Nano Banana o Claude Vision).

#### P1 - Backlog precedenti non chiusi
16. Card "Premi e Provvigioni" (privato/azienda/totale) in `AnagraficaDetail` (backend pronto: `GET /api/anagrafiche/{id}/riepilogo`).
17. Pagina Newsletter UI (multi-select tag, preview destinatari) + filtri tag chip cliccabili in lista clienti + bottone "Auto-genera tag".
18. Payout Provvigioni Collaboratore → movimento "uscita" nel Brogliaccio/Banca.
19. Refactor `server.py` (~3200 righe) in router per dominio.

#### P2 - Integrazioni storiche
20. WhatsApp, 3CX (centralino), Google Drive / OneDrive (per Corsi).
21. Pipeline email (gestione casella).
22. Mappa clienti con geolocalizzazione reale.

---

### Architettura
```
/app/backend/
  server.py         (~3200 righe - DA REFACTORIZZARE in router/)
  db_models.py      (Pydantic + UUID)
  ania_importer.py
  inps_calculator.py
  brogliaccio.py
  pdf_report.py     (con intestazione azienda + logo)
  storage.py        (Emergent Object Storage)
  auth.py           (JWT bcrypt)
  tests/test_ania_import.py
/app/frontend/src/
  pages/Librerie.jsx (Azienda, Banche, Conti, Prodotti, Rami, Compagnie, Utenti, Schema Provv)
  pages/PolizzaDetail.jsx (tabbed Cattolica style)
  pages/Titoli.jsx (bulk actions)
  pages/Anagrafiche.jsx
  ...
```

### Test credentials
File `/app/memory/test_credentials.md`. Admin: `admin@assicura.it / Admin123!`

### Backend health
✅ Up. ANIA importer testato end-to-end. Endpoints Azienda/Schema Provv/Doc Utenti testati con curl. Stampe PDF generano correttamente (28KB+ con header).
