# PRD — Programma Assicurativo (Italian Insurance CRM)

## Problem Statement
CRM full-stack su misura per agenzie assicurative italiane: gestione anagrafiche, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), analisi cliente, avvisi scadenze, sistema provvigionale, mapping ANIA, importazione flussi (OMNIA, Libro Matricola).

## Stack
- Frontend: React + Shadcn UI + Tailwind + lucide-react
- Backend: FastAPI + Motor (Async MongoDB) + Pydantic
- LLM: Gemini 3 Flash via Emergent LLM Key (OCR polizze)
- Storage: object_storage interno (firma, allegati, PDF)
- Comunicazioni: SMTP+IMAP (email), Twilio (SMS + WhatsApp Business)

## Implementato (al 28 Feb 2026)
### Sessione corrente
- ✅ Lettera di Abbuono con doppia firma digitale (auto-trigger su sconto, firma operatore dal profilo, PDF firmato come allegato)
- ✅ Libreria 3-tier "Tipi pagamento" (Conti+Modalità+Tipi) con selettore unificato in tutti i dialoghi accounting
- ✅ Configurazione Comunicazioni unica in Librerie (Email SMTP con preset Google/Microsoft, IMAP con preset, Twilio SMS+WhatsApp, test invio per ogni canale)
- ✅ **IMAP backend**: endpoint `/api/librerie/comunicazioni/test-imap` connette + valida + ritorna ultime 5 email per anteprima. Preset Gmail/Workspace + Office365.
- ✅ Diario personale collaboratore (`/diario`)
- ✅ No pagination (Polizze=Attive default, Titoli=Tutti da incassare default)
- ✅ Colonne Contratto/Targa separate in Titoli + Polizze
- ✅ Sticky tables (header + prime 3 colonne) su Titoli/Polizze/Sinistri/Anagrafiche/EC Compagnie/Prima Nota/Avvisi
- ✅ Modulo Veicolo dinamico per ramo/prodotto RCAUTO + lookup targa
- ✅ Rimosse tab legacy Mapping ANIA

## Backlog priorità

### P0 — Email integrata (smistamento per alias)
**Step 1** (alias send-as): aggiungere campo `email_alias` al profilo collaboratore. Quando l'operatore invia email dal programma, header `From:` = alias del collaboratore loggato + reply-to = stesso alias. SMTP rimane uno solo (assicurazioni@…).

**Step 2** (IMAP smistamento automatico):
- Job APScheduler ogni 5 min legge la cassetta principale IMAP
- Per ogni nuova email controlla `To:` + `Cc:`:
  - se contiene un alias di un user → categoria=`personale`, `smistato_a=[user_id]`
  - altrimenti → categoria=`condivisa`, visibile a tutti
- Modello `EmailInbox` (db.email_inbox) con campi: from, to[], cc[], subject, body_text, body_html, date, attachments[], smistato_a[user_id], letta_da[user_id], categoria
- Endpoint `/api/email/inbox`, `/api/email/inbox/{id}`, `/api/email/inbox/{id}/leggi`
- Pagina `/posta` con 2 tab (Personale / Condivisa), lista + dettaglio + risposta + allegati

### P1
- Filtri/sort per colonna su table headers
- OCR Fatture via Gemini 3 Flash
- "Verifica polizza vs libretto" UI di confronto

### P2
- Redesign Piramide Soluzioni
- OAuth Google Calendar + M365
- Refactor server.py (9300 righe) in moduli routes/

## File principali
- `/app/backend/server.py` (~9400 righe)
- `/app/backend/routes/librerie.py` (Comunicazioni SMTP+IMAP+Twilio, Tipi pagamento, Mezzi)
- `/app/backend/pdf_lettera_abbuono.py`
- `/app/backend/db_models.py` (TipoPagamento, LetteraAbbuono, DiarioNota, AziendaConfig esteso con IMAP)
- `/app/frontend/src/pages/Librerie.jsx` (sezione Comunicazioni con preset Google/Microsoft per SMTP **e** IMAP)
- `/app/frontend/src/pages/Diario.jsx`
- `/app/frontend/src/components/DialogLetteraAbbuono.jsx`, `SignaturePad.jsx`, `SelectTipoPagamento.jsx`

## Credenziali test
Vedi `/app/memory/test_credentials.md`
