# Programma Assicurativo — PRD

## Vision
CRM full-stack in italiano per agenzie assicurative italiane. Prodotto destinato
alla vendita modulare a clienti finali (ogni servizio/modulo a pagamento).

## Stack
- Backend: FastAPI + MongoDB (Motor async) + APScheduler
- Frontend: React + Shadcn/UI + Tailwind
- PDF: ReportLab
- LLM/OCR: Gemini 3 Flash (via Emergent LLM Key)
- Comunicazioni: SMTP/IMAP, Twilio (SMS/WA), wa.me (WhatsApp link), Spoki (WhatsApp BSP IT)

## Personas
1. Admin, Collaboratore, Dipendente, Cliente.

## Moduli implementati
- Anagrafiche / Mappa clienti / Portafoglio polizze (con dynamic Veicolo)
- Titoli / Titoli storici / Sospesi / Avvisi scadenze
- Sinistri / Pipeline / Calendario / Chat / Corsi
- Prima Nota / E/C Collaboratori / E/C Compagnie / Rappel
- **Posta** (IMAP smistamento alias) — completata 28/06/2026
- **Diario Collaboratore** — completato
- **Gestioni Modelli** (Email/WhatsApp/SMS/PDF + sezioni dinamiche) — completata
- **Alert & Automazioni** con destinatari multipli e "altri collaboratori" custom — completata
- Lettera di Abbuono con doppia firma digitale
- PDF Avviso scadenza generato da template + 🖨 quick-print
- WhatsApp dispatch dual: wa.me / Twilio / **Spoki** — completato

## Backlog prioritario
### P0 (in progress)
- [ ] Test end-to-end IMAP poller con casella reale
- [ ] Test PDF Avviso con dati reali

### P1
- [ ] Sync Google Contacts (OAuth) — push anagrafiche → Google
- [ ] Sync Microsoft 365 Contacts (Azure AD app) — push anagrafiche → MS
- [ ] Integrazione 3CX: click-to-call + popup chiamate + log diario
- [ ] OCR Fatture via Gemini 3 Flash
- [ ] Tool "Verifica polizza vs libretto"

### P2
- [ ] Dashboard "Stato integrazioni" per vendita modulare
- [ ] Redesign Piramide Soluzioni (Release B)
- [ ] Refactoring `server.py` (>9700 righe) in moduli `routes/`

## Changelog ultimo (28/06/2026)
- IMAP Poller (`imap_poller.py`) con APScheduler + toggle UI + esecuzione manuale + auto-start.
- Smistamento automatico via `User.email_aliases`; log automatico in `DiarioCliente` per mittenti noti.
- `EmailAliasesEditor` in UtenteForm + pulsante "Usa email principale" come shortcut.
- "Gestioni Modelli" — libreria CRUD template Email/WhatsApp/SMS/PDF con placeholder auto-detect e sezioni dinamiche per PDF Avviso.
- `pdf_avviso.py` con layout configurabile da template.
- Endpoint `POST /api/avvisi/pdf` + pulsante 🖨 "Stampantina" in Avvisi.
- Endpoint `POST /api/comunicazioni/whatsapp/invia` con scelta `wame` / `twilio` / `spoki` (Spoki API: `https://api.spoki.com/api/1/messages/send`).
- Alert: rinominato `collaboratore_sinistri` → `altri_collaboratori` (con backward-compat).
- AlertRule: nuovo campo `altri_collaboratori_user_ids` → UI con multi-select utenti quando il destinatario è "altri_collaboratori".
- Notifiche in-app degli Alert ora finiscono anche nel Diario (collaboratore → `diario_note`, cliente → `diario_cliente`).
- Pulsante CTA "Attiva con email SMTP" nell'header Posta in arrivo — IMAP (one-click setup se SMTP già configurato).
- Fix CSS globale `tbl thead th { white-space: nowrap }` + max-width frozen columns → eliminato whitespace tabelle.

## Architettura file
```
/app/backend/
├── server.py              # >9700 righe (refactor pendente)
├── imap_poller.py         # NEW: APScheduler IMAP
├── pdf_avviso.py          # NEW: PDF Avviso
├── alert_dispatcher.py    # in-app → diario, altri_collaboratori
├── alert_models.py        # +altri_collaboratori_user_ids
└── routes/
    ├── librerie.py        # +spoki_api_key fields
    ├── modelli.py         # NEW: CRUD modelli
    └── alert.py           # +AlertRulePatch field
/app/frontend/src/pages/
├── Librerie.jsx           # +Modelli +ImapPollerControl +Attiva-SMTP-CTA
├── Avvisi.jsx             # +Printer icon + PDF dispatch
└── Alert.jsx              # +Altri collaboratori multi-select
```

## Credenziali test
Vedi `/app/memory/test_credentials.md`.

## Provider WhatsApp supportati
- **wame** (default): link `https://wa.me/...?text=...` — gratis, semi-manuale
- **twilio**: invio automatico via Twilio (a pagamento, ~€0.005/msg)
- **spoki**: provider italiano BSP Meta — `X-Spoki-Api-Key` + `POST /api/1/messages/send`
