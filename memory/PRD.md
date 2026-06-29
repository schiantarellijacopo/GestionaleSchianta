# Programma Assicurativo — PRD

## Problem statement
CRM full-stack per agenzie assicurative italiane (Schiantarelli & affiliate).
Stack: React + FastAPI + MongoDB + Emergent LLM key (Claude 4.5, Gemini 3 Flash).

## Architettura backend modulare
`/app/backend/`
- `server.py` (~10k righe — refactor P3)
- `routes/`:
  - `anagrafiche.py` · `permessi.py` · `librerie.py` · `kpi.py` · `alert.py`
  - `insights.py` (AI Assistente + Statistiche + ISA con filtri)
  - `cervello.py` (P&L / costi annuali)
  - `marketing_pro.py` (Voucher · Newsletter · Liste Lead import/dispatch)
  - `commerciale.py` (Trattative · Ritenute collab · Ritenute Compagnia · Fatture Agenzia Partner)
  - `agenzie.py` (Libreria agenzia principale + partner)
  - `setup_scambio.py` (Setup iniziale + Scambio dati tra agenzie)
  - `documenti_inbox.py` (OCR universale via Gemini + crop avatar)
  - `ocr.py` (OCR libretto specifico)

## Modelli chiave aggiornati
- `Compagnia`: `tipo_mandato` (diretto|collaborazione) + `agenzia_partner_id` (→ db.agenzie)
- `Agenzia`: tipo (principale|partner) + `perc_ritenuta_acconto`
- `RitenutaCompagnia`: importo positivo che AUMENTA il dare verso compagnia (solo mandato diretto)
- `FatturaAgenziaPartner`: `compagnie_ids[]` (multi) + importo lordo + ritenuta auto da agenzia + netto
- `DocumentiInbox`: tipo_documento auto-classificato + foto_volto_bbox per avatar

## CHANGELOG · 29/06/2026 — Sessione massive features (14 features, tutte testate)

### Backend
1. **FIX P0 Trattative**: rimosso router duplicato in insights.py → `/api/trattative` CRUD ora 200 OK
2. **FIX P0 Voucher/Lead import**: parser Excel/CSV + matching CF/Email/Tel + dispatch WhatsApp/Email (**MOCKED**)
3. **Tipo mandato compagnia** + libreria `Agenzie` partner separata; saldo cassa differenziato per mandato
4. **Ritenute Compagnia** (negativa del Rappel, va in estratto conto + Prima Nota al versamento, solo mandato diretto, dialog data registrazione)
5. **Fatture Agenzia Partner** flow: agenzia → compagnie multi → lordo + ritenuta auto da agenzia + netto
6. **Ritenute Hub** unificato (`/ritenute`) con 3 tab: Compagnia · Collaboratori · Agenzia Partner
7. **Auto-ritenute collaboratori**: pagamento provvigioni con `perc_ritenuta` crea record F24 in `db.ritenute`
8. **Setup iniziale wizard** (banche/compagnie/sospesi/voci pregresse). Sospesi salvati come titoli virtuali (visibili in `/api/titoli/sospesi`)
9. **Scambio dati tra agenzie** (super-admin): preview + import. Titoli importati = sempre "da_pagare arretrato"
10. **Indice ISA** con filtri data_copertura/data_incasso e anno
11. **Documenti Inbox · OCR universale** (Gemini 3 Flash): classifica + estrae dati + crop foto → avatar anagrafica
12. **Statistiche multi-modulo** con tabs (Overview, ISA, futuri)
13. **Avvisi automatici scadenza polizza**: preset T+0/+5/+10/+14/+15 in alert_presets.py
14. **Collega compagnie ad agenzia partner**: dialog multi-select da AgenziaCard

### Frontend
Pagine nuove: `RitenuteHub`, `Agenzie`, `RitenuteCompagnia`, `FattureAgenziaPartner`, `LeadListe`, `SetupIniziale`, `ScambioDati`, `DocumentiInbox`. Aggiornati: `Compagnie`, `Provvigioni`, `Statistiche`, `Sidebar`, `App.js`, `EstrattoContoCompagnie` (gestione righe rappel/ritenuta/partner).

### Testing (Iter 25)
- Backend pytest: **17/18 PASS** (1 skip atteso). Fixed: ObjectId leak in setup-iniziale.
- Frontend Playwright: **7/7 pagine OK**.
- Report: `/app/test_reports/iteration_25.json`

## Backlog (P1-P3)

### P1
- Documenti visibili/non al cliente (dropzone doppia)
- Documenti pre-impostati per ramo polizza
- Libro matricola allegati per applicazione
- Regolazione premio
- OCR bilancio nel Cervello
- Storico avvisi: spostare primo avviso inviato → sezione storico (db.storico_avvisi)
- Spoki/Twilio real dispatch (richiede API key utente)

### P2
- OCR corsi + grafico 30h IVASS per collaboratore
- Customer Insights widget in AnagraficaDetail
- Dashboard componibile drag&drop
- Grafico storico provvigioni/utile in Cervello
- Indice MongoDB su ritenute_compagnia.compagnia_id

### P3
- Refactor server.py >10k righe

## Test credentials
Admin: `admin@assicura.it` / `Admin123!`

## Integrazioni
- **Emergent LLM Key** (configured): Claude 4.5 (Assistente Personale), Gemini 3 Flash (OCR libretto + Documenti Inbox)
- **Twilio/Spoki/SMTP**: dispatch lead-liste in MOCK (logga in `db.dispatch_log`). In attesa credenziali utente.
