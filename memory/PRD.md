# Programma Assicurativo — PRD

## Problem statement
CRM full-stack per agenzie assicurative italiane (Schiantarelli & affiliate).
Stack: React + FastAPI + MongoDB + Emergent LLM key (Claude 4.5, Gemini 3 Flash).

## Architettura backend modulare
`/app/backend/`
- `server.py` (~10k righe — refactor P3)
- `routes/`:
  - `anagrafiche.py` · `permessi.py` · `librerie.py` · `kpi.py` · `alert.py`
  - `insights.py` (AI Assistente + Statistiche + ISA)
  - `cervello.py` (P&L / costi annuali)
  - `marketing_pro.py` (Voucher · Newsletter · Liste Lead · Import Excel)
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

## CHANGELOG · Feb 2026

### 29/06/2026 — Sessione massive features
1. **FIX P0 Trattative**: rimosso router duplicato in insights.py, ora `/api/trattative` CRUD via `commerciale.py` (200 OK).
2. **FIX P0 Voucher import**: aggiunto parser Excel/CSV `/api/lead-liste/import` con matching CF/Email/Tel + dispatch WhatsApp/Email simulato.
3. **Tipo mandato compagnia**: aggiunto `tipo_mandato` (diretto/collaborazione) + libreria `Agenzie` separata. Logica saldo cassa differenziata: mandato diretto = premi-provv, collaborazione = premi puri.
4. **Ritenute Compagnia**: nuovo modulo gemello negativo del Rappel. Va in estratto conto + crea movimento USCITA in Prima Nota al versamento. Solo mandato diretto. Dialog data registrazione.
5. **Fatture Agenzia Partner**: dialog rinnovato 1) agenzia 2) compagnie multi-select 3) importo lordo + ritenuta % auto da agenzia + importo definitivo netto. Endpoint `/api/partite-agenzia-partner` per partite aperte.
6. **Ritenute Hub**: pagina unica con 3 tab (Compagnia · Collaboratori · Agenzia Partner) → `/ritenute`.
7. **Ritenute Collaboratori auto-genera**: quando si paga collaboratore con `perc_ritenuta`, il record di ritenuta viene auto-creato in `db.ritenute` (causale 1040).
8. **Setup iniziale wizard**: `/setup-iniziale` admin-only. Saldi banche / compagnie (dare-avere) / sospesi manuali / voci pregresse facoltative. Idempotente, con reset.
9. **Scambio dati agenzie**: `/scambio-dati` super-admin. Preview + esegui import anagrafiche/polizze/titoli/sinistri/allegati di un operatore da agenzia partner. Titoli importati = stato "da_pagare arretrato" senza metodo pagamento.
10. **Indice ISA stimato**: `/api/statistiche/isa` calcola punteggio 1-10 da redditività/densità/diversificazione/continuità/crescita. Visualizzato in Statistiche con barra colorata e indicatori.
11. **Documenti Inbox · OCR**: `/documenti-inbox` upload PDF/foto → Gemini 3 Flash classifica (CI/patente/CF/libretto/polizza/fattura) + estrae dati + bbox foto volto. Save: archivia allegato, applica campi su anagrafica/polizza, croppa foto e setta come avatar.
12. **Avvisi scaduti**: aggiunti preset `polizza_scaduta_giorno`/5g/10g/14g/15g in `alert_presets.py`.

## Backlog (P1-P3)

### P1
- Documenti visibili/non al cliente (dropzone doppia)
- Documenti pre-impostati polizze per ramo (RC Auto: libretto/polizza/condizioni; altri: polizza/condizioni/foto)
- Libro matricola con allegati per applicazione
- Regolazione premio (flag + calcolo Fatturato/Mercedi/Addetti × Tasso)
- OCR bilancio nel Cervello (autofill via AI)
- Storico avvisi: spostare primo avviso inviato dalla sezione attiva → storico

### P2
- OCR corsi + grafico 30h IVASS per collaboratore
- Customer Insights widget in AnagraficaDetail
- Dashboard componibile drag&drop
- Grafico storico provvigioni/utile in Cervello
- Spoki/Twilio real dispatch (richiede API key utente)

### P3
- Refactor server.py >10k righe in moduli

## Test credentials
Admin: `admin@assicura.it` / `Admin123!`

## Integrazioni
- **Emergent LLM Key** (configured): Claude 4.5 (Assistente Personale), Gemini 3 Flash (OCR libretto + Documenti Inbox)
- **Twilio/Spoki/SMTP**: dispatch lead-liste in MOCK (logga in `db.dispatch_log`). In attesa credenziali utente.
