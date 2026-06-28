# Programma Assicurativo — PRD

## Vision
CRM full-stack in italiano per agenzie assicurative, vendibile come prodotto
modulare. Ogni cliente accende solo i servizi che gli servono.

## Stack
- Backend: FastAPI + MongoDB (Motor async) + APScheduler
- Frontend: React + Shadcn/UI + Tailwind
- PDF: ReportLab (con logo agenzia incluso)
- LLM/OCR: Gemini 3 Flash (via Emergent LLM Key)
- Comunicazioni: SMTP/IMAP, Twilio, wa.me, **Spoki** (BSP italiano)

## Personas
1. Admin agente — vede tutto, gestisce librerie
2. Collaboratore — gestisce clienti propri
3. Dipendente — opera senza eliminazioni
4. Cliente — vede solo i propri dati

## Moduli implementati
- Anagrafiche / Mappa / Portafoglio polizze (Veicolo dinamico)
- Titoli / Sospesi / Avvisi scadenze (con 🖨 PDF + logo)
- Sinistri / Pipeline / Calendario / Chat / Corsi / **Diario** / **Posta**
- Prima Nota / E/C Collaboratori / Compagnie / Rappel
- **Gestioni Modelli** redesignato a tabs (Email/WhatsApp/SMS/PDF)
- **Alert & Automazioni** con destinatari "altri collaboratori" checkbox
- Notifiche in-app → diario automatico
- **WhatsApp dispatch dual**: wa.me / Twilio / **Spoki**
- IMAP Poller + CTA "Attiva con email SMTP" one-click
- TopBar: avatar utente + nome (sx), logo agenzia (dx)
- `email_utils.py` per invio SMTP robusto con `From` ben formattato

## Backlog
### P1
- Visibility filter Librerie (collaboratore vede solo se stesso)
- Upload avatar in UtenteForm
- Logo + ragione sociale in TUTTI gli altri PDF (lettera abbuono, brogliaccio, diagnosi, prima nota)
- Dashboard componibile per operatore (widget drag&drop)
- Google Contacts / MS 365 / 3CX (richiedono credenziali)

### P2
- Refactoring `server.py` (>9700 righe)
- Dashboard "Stato integrazioni" per vendita modulare

## Changelog (28/06/2026)
- IMAP Poller + CTA "Attiva con email SMTP"
- Gestioni Modelli redesign (tabs canale + card visive)
- PDF Avviso: logo agenzia + nome + fix placeholder `{cliente_nome}` + lookup nome prodotto (no più UUID) + colonna "Rata del" popolata correttamente
- WhatsApp dual-provider: wame / twilio / **spoki** (API `https://api.spoki.com/api/1/messages/send`)
- Alert: `altri_collaboratori` con checkbox multi-select utenti
- Notifiche in-app → loggate nel Diario
- `email_utils.py`: helper centralizzato SMTP con `From` RFC-compliant
- Bug fix: rimosso decoratore orfano `@api.post("/email/avvisi-scadenze")` che rompeva una route
- TopBar redesign: avatar utente + ruolo (sx), logo agenzia (dx)
- Error handler robusto: `errMsg()` evita crash React su detail Pydantic array
- Fix CSS globale `tbl thead th { white-space: nowrap }` + frozen max-width
- Aggiunto `User.avatar_url`

## Credenziali test
Vedi `/app/memory/test_credentials.md`.

## Provider WhatsApp
- **wame**: link gratis, click manuale
- **twilio**: automatico ~€0.005/msg
- **spoki**: italiano BSP, X-Spoki-Api-Key + REST API
