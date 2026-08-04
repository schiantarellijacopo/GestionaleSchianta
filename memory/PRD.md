# Programma Assicurativo — PRD

## Visione
CRM completo per agenzie assicurative italiane. Gestisce anagrafiche, polizze, titoli, sinistri, P&L, marketing, AI insights, OCR documenti, ritenute, calcoli pensione INPS, chat AI conversazionale con accesso RBAC al DB.

## Stack
- **Backend**: FastAPI + MongoDB (Motor). Multi-tenant via ContextVar.
- **Frontend**: React + Tailwind + Shadcn UI.
- **AI**: Emergent LLM Key. Claude Sonnet 4.6 come motore Copilot/Assistente. Gemini 3 Flash per OCR bilanci/documenti/CI.
- **Integrazioni**: OpenAPI.it (Visengine/Automotive/Risk/Catasto/Imprese in PROD), ElevenLabs (TTS), WhatsApp Evolution API, Emergent Object Storage.

## Persona
Agente assicurativo italiano + collaboratori + dipendenti + clienti.

## Implementato — Sessione corrente (22/07)

### ✅ AI Copilot Conversazionale (Claude Sonnet 4.6)
- Riscrittura `ai_copilot_service.py` con multi-turno persistente in `db.copilot_sessions` + `db.copilot_messages`.
- **10 tool READ-ONLY** con RBAC (cliente vede solo sé, collab solo suo portafoglio, admin tutto).
- **Dispatcher intelligente**: estrae candidati nome case-insensitive (min 3 char), stop-words estese, ricerca AND multi-parola (es. "bottoni cristian" → matcha cognome+nome insieme), keyword "quanto costa" → auto-fetch polizze con premio.
- **Endpoint** `/api/copilot/chat|sessions|sessions/{sid}/messages|sessions/{sid}` (delete).
- **Frontend**:
  - `ChatCopilotPanel.jsx`: chat full-page in `/assistente-personale` (sidebar cronologia, chip iniziali + follow-up, voice input, link Markdown → React Router Link, tabelle GFM via remark-gfm).
  - `CopilotWidget.jsx` (bottom-right floating): stessa esperienza premium, 440px wide.
- **Verificato LIVE**: query "mi trovi la polizza di bottoni cristian e mi dici quanto costa" → trova BOTTONI CRISTIAN con 2 polizze, costo totale € 123,75, link cliccabili, alert "polizze scadute" proattivo.

### ✅ OCR Carta Identità + Auto-Avatar (Gemini Vision)
- `ocr_ci.py` PROMPT esteso con campo **`foto_volto_bbox: {x, y, w, h}`** (coordinate normalizzate 0-1 della fototessera).
- Endpoint `POST /api/utility/ocr-carta-identita` (server.py:2022):
  1. Gemini estrae dati anagrafici + bbox foto volto.
  2. Se `anagrafica_id` presente: salva file come `Allegato` carta_identita.
  3. Se bbox valido: crop quadrato centrato + resize 512px + JPEG 88% → salva come `avatar_xxx.jpg` in Object Storage.
  4. Aggiorna `anagrafiche.avatar_url` automaticamente.
- **Test PASS**: bbox rilevato `{x:0.721, y:0.186, w:0.216, h:0.447}`, avatar 271×271px 5.4 KB salvato, `avatar_url` popolato in DB.

### ✅ OpenAPI.it — PROD LIVE
- `OPENAPI_IT_ENV=prod` attivato. Domini corretti: `.com` per Automotive/Risk, `.it` per Catasto/Imprese/Visengine.
- **Visengine**: flow `GET /visure` → estrae `hash_visura` Camera Commercio PF/PG → POST `/richiesta` con `json_visura` proper (schema `$0..$5` ancora da compilare console).
- **Catasto**: endpoint come path param `/richiesta/ricerca_nazionale` (scoperto via web docs).
- **Risk**: payload `taxCode + companyName` per PG. Richiede credito account (402 attualmente).
- **Automotive**: token OK, richiede "Codice Cliente" configurato lato account (402 attualmente).
- **Imprese/Company**: 406 "API not enabled" → richiede attivazione prodotto sulla console.

## Implementato — Sessione 04/08 (fork)

### ✅ Migrazione "Tipi pagamento" → Conti / Banche (conti_cassa)
- **Dati**: movimenti dei conti legacy `CONTANTI BPER` (81), `BONIFICO` (41), `PayPal/Online` (1) migrati su **BPER Sondrio** (ora 150 mov); duplicati `CONTANTI` e `PAGAMENTI IN DIREZIONE` eliminati (script: `/app/memory/migrate_conti_2026-08-04.py`).
- **Backend**: `shared.resolve_conto_cassa` risolve il conto per NOME (case-insensitive) → fallback label legacy `tipi_pagamento` → mezzi_pagamento → primo attivo. Seed legacy `_seed_tipi_pagamento`/`_seed_conti_deposito_estesi` rimossi dallo startup. Validazione `nome` obbligatorio su POST/PUT conti-cassa. Fix `premio_totale` → `premio_lordo` in POST /polizze (server.py:2545).
- **Frontend**: `SelectTipoPagamento` + `useTipiPagamento` ora elencano i conti_cassa attivi (value = nome conto, filtrati nascondi_prima_nota e nomi vuoti). Librerie: tab "Conti / Banche" punta a `/librerie/conti-cassa` (ContoForm), tab "Tipi pagamento" rimosso, BancaForm/TipoPagamentoForm eliminati. `Contabilita.jsx` NuovoMovimentoDialog deriva conto_cassa_id direttamente dal conto scelto.
- **Multi-tenant**: nuovi tenant ricevono 4 conti default alla creazione (super_admin.create_agenzia); tenant esistenti senza conti seedati (demo jacopo incluso).
- **Testing**: testing_agent iter_39 — backend 11/11 PASS (incasso per nome conto, Pagamento in Direzione is_direzione=true senza cash flow banche, legacy label, multi-tenant isolation, CRUD, brogliaccio). Bug trovati e fixati (SelectItem vuoto, validazione nome, premio_totale). 9 titoli reali incassati dai test ripristinati a `da_incassare` con i relativi movimenti rimossi.
- **NB**: collezioni `tipi_pagamento` e `banche` restano in DB solo come legacy (nessuna UI, endpoint /librerie/banche e /librerie/tipi-pagamento ancora esposti per retrocompatibilità).

## Backlog priorità

### P0 — Prossime sessioni
- Fix widget Documenti Mancanti: dropdown "Tutti i collaboratori" + bottone "📎 Allega" inline + campo Note/Sollecito.
- RCA sostituzione: stessa targa eredita libretto | targa diversa richiede libretto+atto vendita mancanti.
- Modulo Asset/Patrimonio Cliente: mappa Leaflet + geocoding + PDF reporting.
- Avatar auto-crop bypass: upload CI da "Sostituisci Documento" non passa per pipeline OCR volto.
- Setup Iniziale: aggiungere categorie `setup_iniziale_*` a MovimentoCategoria (db_models.py).

### P1
- Tool call ReAct multi-step per Copilot (auto-follow-up query concatenate).
- Streaming SSE risposta Claude (attualmente 3-5s attesa).
- Salvataggio consiglio AI nel Diario cliente.
- Configurazione console OpenAPI.it per attivare Imprese/Automotive + topup credito Risk.

### P2
- Refactor `server.py` (>10.700 righe) in router modulari.
- Seed CAP italiani (~7.900) + ABI/CAB completi Banca d'Italia.
- Google Drive Integration per PDF sync automatico per tenant.

## Credenziali test
File: `/app/memory/test_credentials.md`
- admin@assicura.it / Admin123!
- collaboratore@assicura.it / Collab123!
- dipendente@assicura.it / Dipendente123!
- cliente@assicura.it / Cliente123!
- superadmin@assicura.it / Superadmin123!

## Sessione 2026-08-04 — Unificazione pagamenti sotto conti_cassa (COMPLETATA)
- Migrazione approvata dall'utente: eliminati conti legacy CONTANTI BPER (81 mov) e BONIFICO (41 mov) → BPER Sondrio; PayPal/Online eliminato; duplicati CONTANTI / PAGAMENTI IN DIREZIONE fusi in Cassa Contanti / Pagamento Direzione. Script: /app/backend/scripts/migrazione_conti_unificati.py (mezzo_pagamento normalizzati ai nomi conto; codici import BON/CC/SDD/SEC/giroconto intatti).
- Dropdown pagamenti (SelectTipoPagamento + useTipiPagamento) ora attinge SOLO da /librerie/conti-cassa?attivi=true (valore = nome conto). resolve_conto_cassa risolve per nome (poi legacy tipi_pagamento, mezzi, fallback).
- Librerie: tab "Conti / Banche" unificata su conti_cassa; tab "Tipi pagamento" rimossa; "Modalità pagamento" mantenuta.
- REGOLA UTENTE implementata: conti/banche/tipi/mezzi usati nello storico NON eliminabili (400 con messaggio) → solo archiviazione (pulsante archivia/riattiva in tabella, data-testid conto-toggle-attivo-{id}). Helper _usi_pagamento in routes/librerie.py.
- Fix: validazione nome conto obbligatorio (POST/PUT), filtro FE conti senza nome, pdf_brogliaccio._calcola_larghezze clamp (chiusura-giorno 500 con >12 conti risolto — bug critico iter38), POST /polizze premio_totale→premio_lordo, filtri titolo_id/polizza_id su GET /contabilita/movimenti.
- Test: iteration_39.json — backend 11/11 PASS, frontend OK; fix post-report verificati via curl.
- Nota: is_direzione resta rilevato da "direzione" nel nome conto scelto ("Pagamento Direzione"); NON rinominare quel conto.
- Fuori scope (LOW, non fatto): date picker nativo in NuovoMovimentoDialog.
