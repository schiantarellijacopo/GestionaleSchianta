# PRD — Programma Assicurativo (Italian Insurance CRM)

## Stack
React + Shadcn UI + Tailwind | FastAPI + Motor (Async MongoDB) | Gemini 3 Flash (Emergent LLM) | Twilio (SMS/WhatsApp)

## Implementato (28 Feb 2026 - sessione attuale)

### Comunicazioni & Email
- **Configurazione UNICA in Librerie → Comunicazioni**: SMTP con preset Google/Microsoft/Custom, IMAP con stessi preset + pulsante Test Connessione che ritorna anteprima ultime 5 email, Twilio (SMS+WhatsApp) + Test invio per ogni canale.
- **Rimossa tab "Configurazione canali"** dalla pagina Alert (era duplicata): ora redirige a Librerie › Comunicazioni.
- **Modelli backend pronti per IMAP smistamento**:
  - `User.email_aliases: list[str]` (supporta sia alias personali che di reparto)
  - `EmailInbox` (smistato_a, categoria, anagrafica_id, allegati, letta_da)
  - `DiarioCliente` (collegamento auto email→cliente)
- **Endpoint Posta**: `GET /api/email/inbox`, `GET /api/email/inbox/stats`, `GET /api/email/inbox/{id}`, `POST /api/email/inbox/{id}/leggi`
- **Pagina /posta**: infografica con 4 KPI (Personali, Condivise, Non lette, Totale), 2 tab (Personale / Condivisa), ricerca testo, lista + dettaglio con allegati e link automatico a anagrafica. Banner "configura per attivare polling".

### UI/UX miglioramenti
- **Sort cliccabile** sugli header di Titoli, Polizze, Sinistri, Anagrafiche (componente `<SortHeader />` riusabile)
- **Sticky tables**: header in alto + prime 3 colonne congelate a sinistra su tutte le tabelle principali
- **Righe compatte**: ridotto padding `.tbl tbody td` da 10px a 6px (recupero spazio verticale)
- **Polizze default = "Attive"** preset; Titoli default = "Tutti da incassare"
- **Colonne Contratto/Targa SEPARATE** in Titoli + Polizze
- **Avvisi**: aggiunta barra di ricerca rapida (oltre pannello Filtri)
- **Diario personale** `/diario` (note + storico avvisi + chat)
- **Modulo Veicolo dinamico** per RCAUTO + lookup auto-targa

### Funzionalità precedenti
- Libreria 3-tier Pagamenti (Conti+Modalità+Tipi) con `<SelectTipoPagamento />` unificato
- Lettera di Abbuono + doppia firma digitale (operatore dal profilo + cliente canvas)
- No pagination (limite backend 50k record)
- Mobile/tablet responsive sidebar drawer
- OMNIA + Libro Matricola XLSX import

## Backlog (priorità)

### P0 — IMAP Polling Step 2 (modelli pronti, manca implementazione)
- **UI campo `email_aliases`** nel form profilo collaboratore (Librerie → Utenti → tab Email)
- **Job APScheduler 5 min** che legge IMAP, salva EmailInbox, applica smistamento:
  - Match `To/Cc` con alias collaboratori → `smistato_a[user_id]` + `categoria=personale`
  - Match `From` con anagrafica.email → `anagrafica_id` + voce in `DiarioCliente`
  - Default → `categoria=condivisa`
- **Endpoint POST `/api/email/sync`** (trigger manuale dal frontend)
- **Send-as alias** in uscita: `From:` = alias del collaboratore loggato

### P1
- Filtri per colonna (popover su click intestazione)
- Sort + sticky sulle tabelle minori (Movimenti, EstrattoConto, Provvigioni, Marketing, Pipeline Email)
- Hook automatici Diario per tutti i punti di invio email
- OCR Fatture via Gemini 3 Flash
- "Verifica polizza vs libretto" UI

### P2
- Redesign Piramide Soluzioni
- Refactor server.py (~9400 righe) in moduli routes/
- OAuth Google Calendar + M365

## File principali
- Backend: `server.py` (~9500 righe), `routes/librerie.py`, `pdf_lettera_abbuono.py`, `db_models.py`
- Frontend: `pages/Posta.jsx`, `Diario.jsx`, `Librerie.jsx`, `components/SortHeader.jsx`, `DialogLetteraAbbuono.jsx`, `SignaturePad.jsx`, `SelectTipoPagamento.jsx`

## Credenziali test
`/app/memory/test_credentials.md` (admin@assicura.it / Admin123!)
