# Programma Assicurativo — PRD

## Vision
CRM full-stack in italiano per agenzie assicurative italiane: gestione polizze,
titoli, sinistri, contabilità, comunicazioni con clienti, posta e calendario.
Prodotto destinato alla vendita modulare a clienti finali.

## Stack
- Backend: FastAPI + MongoDB (Motor async) + APScheduler
- Frontend: React + Shadcn/UI + Tailwind
- PDF: ReportLab
- LLM/OCR: Gemini 3 Flash (via Emergent LLM Key)
- Comunicazioni: SMTP/IMAP nativi, Twilio (SMS/WA), wa.me (WhatsApp link)

## Personas
1. **Admin agenzia** — vede e modifica tutto.
2. **Collaboratore** — opera su clienti/polizze/sinistri, no cancellazioni.
3. **Dipendente** — opera ma non gestisce compagnie/import.
4. **Cliente** — vede solo i propri dati.

## Moduli implementati
- Anagrafiche / Mappa clienti
- Portafoglio polizze (con dynamic Veicolo per RCAUTO)
- Titoli / Titoli storici / Sospesi / Avvisi scadenze
- Sinistri
- Prima Nota / Estratto Conto Collaboratori / E/C Compagnie / Rappel
- Pipeline / Calendario / Chat / Corsi
- **Posta** (IMAP smistamento per alias) — completata 28/06/2026
- **Diario Collaboratore** — completato
- **Gestioni Modelli** (Email/WhatsApp/SMS/PDF) — completata 28/06/2026
- Lettera di Abbuono con doppia firma digitale
- PDF Avviso scadenza generato da template

## Backlog prioritario
### P0 (in progress)
- [ ] Verifica end-to-end IMAP poller con casella reale
- [ ] Test PDF Avviso con dati reali

### P1
- [ ] Sync Google Contacts (OAuth) — push anagrafiche → Google
- [ ] Sync Microsoft 365 Contacts (Azure AD app) — push anagrafiche → MS
- [ ] Integrazione 3CX: click-to-call + popup chiamate + log diario
- [ ] OCR Fatture via Gemini 3 Flash
- [ ] Tool "Verifica polizza vs libretto"
- [ ] Migrazione MovimentiContabili storici

### P2
- [ ] Redesign Piramide Soluzioni (Release B)
- [ ] Refactoring `server.py` (>9000 righe) in moduli `routes/`
- [ ] Twilio WhatsApp dispatch con allegati PDF nativi

## Changelog ultimo (28/06/2026)
- Aggiunto modello `TemplateModello` + collezione `template_modelli`
- Creata libreria "Gestioni Modelli" (tab in Librerie) con CRUD completo,
  editor placeholder e supporto a sezioni dinamiche per i PDF
- Implementato IMAP Poller (`/app/backend/imap_poller.py`) con APScheduler,
  toggle ON/OFF in UI, esecuzione manuale e auto-start configurabile.
- Smistamento automatico via `User.email_aliases` + log automatico in
  `DiarioCliente` quando il mittente è un'anagrafica nota.
- Aggiunto editor `EmailAliasesEditor` nel form Collaboratore (Librerie → Utenti).
- Generato `pdf_avviso.py` con layout dinamico configurabile da modello.
- Endpoint `POST /api/avvisi/pdf` per generare PDF avviso da contraente+titoli.
- Endpoint `POST /api/comunicazioni/whatsapp/invia` con scelta provider
  (wa.me link / Twilio).
- Aggiunti pulsanti "Stampantina PDF" 🖨 nella tabella Avvisi (titoli + polizze).
- Fix CSS globale `tbl thead th { white-space: nowrap }` + max-width sulle
  frozen columns per eliminare spazio bianco non utilizzato.

## Architettura file
```
/app/
├── backend/
│   ├── server.py              # Main API (>9700 righe)
│   ├── imap_poller.py         # NEW: APScheduler IMAP smistamento
│   ├── pdf_avviso.py          # NEW: PDF Avviso scadenza
│   ├── pdf_lettera_abbuono.py
│   ├── routes/
│   │   ├── librerie.py
│   │   ├── modelli.py         # NEW: CRUD Gestioni Modelli + seed
│   │   ├── anagrafiche.py
│   │   ├── alert.py
│   │   ├── dashboard.py
│   │   └── ocr.py
│   └── db_models.py
└── frontend/src/
    ├── pages/
    │   ├── Librerie.jsx       # +Modelli tab +PollerControl +AliasesEditor
    │   ├── Avvisi.jsx         # +Printer icon + PDF dispatch
    │   ├── Posta.jsx
    │   └── Diario.jsx
    └── components/
        └── SortHeader.jsx
```

## Test credentials
Vedi `/app/memory/test_credentials.md`.
