# Programma Assicurativo — PRD

## Visione
CRM completo per agenzie assicurative italiane. Gestisce anagrafiche, polizze, titoli, sinistri, P&L, marketing, AI insights, OCR documenti, ritenute, calcoli pensione INPS, chat AI conversazionale con accesso RBAC al DB.

## Stack
- **Backend**: FastAPI + MongoDB (Motor). Multi-tenant via ContextVar.
- **Frontend**: React + Tailwind + Shadcn UI.
- **AI**: Emergent LLM Key. Claude Sonnet 4.6 come motore Copilot/Assistente. Gemini 3 Flash per OCR bilanci/documenti.
- **Integrazioni**: OpenAPI.it (Visengine/Automotive/Risk/Catasto/Imprese in PROD), ElevenLabs (TTS), WhatsApp Evolution API, Emergent Object Storage.

## Persona
Agente assicurativo italiano + collaboratori + dipendenti + clienti.

## Implementato — Sessione corrente (22/07)

### ✅ AI Copilot Conversazionale (Claude Sonnet 4.6)
- **Riscrittura backend** `ai_copilot_service.py`:
  - Multi-turno con storia persistente in `db.copilot_sessions` + `db.copilot_messages`.
  - Dispatcher esteso: 8 keyword clusters (pagamenti/sospesi, polizze, scadenze, sinistri, veicoli, cross-sell, riepilogo, ricerca cliente).
  - 10 tool READ-ONLY: `search_clienti`, `polizze`, `polizze_in_scadenza`, `titoli`, `titoli_sospesi`, `sinistri`, `veicoli`, `cross_sell`, `portafoglio_summary`.
  - **RBAC filter**: role="cliente" forza `contraente_id=user.anagrafica_id`; "collaboratore/dipendente" filtra `collaboratore_id=user.id`; "admin" nessun filtro.
  - Risposte con **link Markdown cliccabili** (es. `[Cliente](/anagrafiche/xxx)`, `[Polizza](/polizze/xxx)`).
- **Endpoint API** (`routes/copilot.py`):
  - `POST /api/copilot/chat` (multi-turno con session_id opzionale).
  - `GET /api/copilot/sessions` (cronologia utente).
  - `GET /api/copilot/sessions/{sid}/messages`.
  - `DELETE /api/copilot/sessions/{sid}`.
- **Frontend** `ChatCopilotPanel.jsx` sostituisce il vecchio form statico in AssistentePersonale:
  - Chat piena con sidebar cronologia sessioni (apri/nuova/elimina).
  - Chip suggerimenti iniziali (6) + follow-up dinamici (5) dopo primo scambio.
  - Voice input (Web Speech API it-IT).
  - Rendering Markdown con `remark-gfm` (tabelle GFM), link `/anagrafiche/*` come React Router Link.
  - Badge context summary (es. "Riepilogo portafoglio: 1").
- **Verificato**: Claude risponde in Live con dati reali del DB (832 polizze attive, 403 titoli sospesi, 41 sinistri aperti).

### ✅ OpenAPI.it — passaggio a PROD LIVE
- **`OPENAPI_IT_ENV="prod"`** attivato.
- **Riscrittura service** con domini corretti verificati account per account:
  - ✅ **Visengine** (`visengine2.altravia.com`): fix flow `GET /visure` → estrae `hash_visura` per Camera Commercio PF/PG → POST `/richiesta` con `json_visura` proper.
  - ✅ **Catasto** (`catasto.openapi.it/richiesta/ricerca_nazionale`): endpoint come **path parameter** (non body field), scoperto via web docs.
  - 🟡 **Risk** (`risk.openapi.com` — NON `.it`): flow POST con `taxCode + name/surname` per PF, `taxCode + companyName` per PG. **Richiede credito** account (402 error).
  - 🟡 **Automotive** (`automotive.openapi.com` — NON `.it`): token OK ma richiede **"Codice Cliente"** configurato lato account.
  - ❌ **Imprese/Company**: 406 "API not enabled" — richiede **attivazione prodotto sulla console** OpenAPI.it.
- **Diagnostics endpoint** `GET /api/openapi-it/status` restituisce `mode=live, env=prod`.

### 🔧 Configurazioni richieste all'utente (per attivare gli scope mancanti):
1. **Imprese/Company** → https://console.openapi.com/it/apis/company → clic "Attiva".
2. **Automotive** → console prodotto Automotive → configurare "Codice Cliente" nella sezione impostazioni.
3. **Risk** → verificare/topup credito sull'account (attualmente 402 billing).

## Backlog priorità

### P0 — Prossime sessioni
- Completamento visura live (json_visura schema esatto — response 412 su primo tentativo, forse serve `json_visura` con nome/cognome esplici per PF).
- Fix Assistente Personale: dropdown "Tutti i collaboratori" nel widget Documenti Mancanti.
- Bottone "📎 Allega Documento" inline nel widget Documenti Mancanti.
- RCA sostituzione business logic: stessa targa eredita libretto | targa diversa richiede 2 nuovi documenti (libretto nuovo + atto vendita).
- Modulo Asset/Patrimonio Cliente: mappa Leaflet + geocoding + PDF reporting.

### P1
- Tool call ReAct multi-step per Copilot (es. auto-follow-up: cerca cliente → poi polizze → poi sinistri).
- Streaming SSE risposta Claude (attualmente non-streaming, 3-5s attesa).
- Salvataggio consiglio AI nel Diario cliente (compatibilità con vecchia `assistente-personale/genera-consiglio`).

### P2
- Refactor `server.py` (>10.700 righe) in router modulari.
- Seed CAP italiani (~7.900) + ABI/CAB completi Banca d'Italia.
- Face-detection avatar automatico da CI via Gemini Vision.
- Google Drive Integration per PDF sync automatico.

## Credenziali test
File: `/app/memory/test_credentials.md`
- admin@assicura.it / Admin123!
- collaboratore@assicura.it / Collab123!
- dipendente@assicura.it / Dipendente123!
- cliente@assicura.it / Cliente123!
- superadmin@assicura.it / Superadmin123!
