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

## Backlog priorità

### P0 — Prossime sessioni
- Fix widget Documenti Mancanti: dropdown "Tutti i collaboratori" + bottone "📎 Allega" inline + campo Note/Sollecito.
- RCA sostituzione: stessa targa eredita libretto | targa diversa richiede libretto+atto vendita mancanti.
- Modulo Asset/Patrimonio Cliente: mappa Leaflet + geocoding + PDF reporting.

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
