# Programma Assicurativo — PRD

## Problem statement
CRM full-stack per agenzie assicurative italiane. Stack React + FastAPI + MongoDB + Emergent LLM (Claude 4.5, Gemini 3 Flash).

## Architettura backend
`/app/backend/routes/`: anagrafiche, permessi, librerie, kpi, alert, insights (statistiche + ISA), cervello, marketing_pro, **commerciale** (Trattative · Ritenute · Fatture Partner), **agenzie**, **setup_scambio**, **documenti_inbox** (OCR), **extras_p1p2** (Documenti template ramo · Libro matricola · Regolazione premio · OCR bilancio · OCR corsi IVASS · Customer Insights widget · Storico avvisi).

## Modelli chiave aggiornati
- `Compagnia`: tipo_mandato (diretto|collaborazione) + agenzia_partner_id
- `Agenzia`: tipo (principale|partner) + **perc_ritenuta_acconto** (% auto-applicata su fatture)
- `Allegato`: + **visibile_cliente**, **categoria**, **applicazione_matricola_id**
- `Polizza`: + **regolazione_premio** (flag) + base/tasso/periodicità/minima/ultimo_calcolo/dovuto
- `RitenutaCompagnia`: positiva → aumenta dare compagnia (solo mandato diretto)
- `FatturaAgenziaPartner`: compagnie_ids[] + lordo + ritenuta auto + netto
- `DocumentiInbox`: tipo_documento + foto_volto_bbox per avatar
- `ApplicazioneMatricola`: targa/telaio/marca/modello + allegati
- `RegolazioneStorico`: storico calcoli per polizza

## CHANGELOG · 29/06/2026

### Massive features sessione (22 features totali implementate)
**P0 fix**:
1. Trattative router duplicato (insights→commerciale)
2. Voucher/Lead import parser + dispatch MOCKED

**P0 nuovi**:
3. Tipo mandato compagnia + libreria Agenzie partner
4. Ritenute Compagnia (gemella Rappel negativa, in estratto conto + Prima Nota)
5. Fatture Agenzia Partner (multi-compagnia + ritenuta auto da perc_ritenuta_acconto agenzia + netto)
6. Ritenute Hub unificato (3 tab)
7. Auto-ritenute collaboratori al pagamento
8. Setup iniziale wizard + sospesi come titoli virtuali
9. Scambio dati tra agenzie (super-admin)
10. Indice ISA con filtri data_copertura/data_incasso
11. Statistiche multi-modulo (tabs)
12. Documenti Inbox OCR + crop foto → avatar
13. Avvisi automatici T+0/+5/+10/+14/+15
14. Collega compagnie ad agenzia partner (dialog multi-select)
15. Campo perc_ritenuta_acconto nel form Agenzia (auto su fatture)

**P1/P2 (questa sessione)**:
16. **Documenti pre-impostati per ramo** (`/polizze/{id}/documenti-template`) — RC Auto: libretto+polizza+condizioni; default: polizza+condizioni+foto
17. **Visibilità documenti** (campo `visibile_cliente` su Allegato + categoria)
18. **Libro matricola applicazioni** CRUD con allegati per applicazione
19. **Regolazione premio**: flag polizza + endpoint calcolo (`base × tasso% = dovuto`, min non rimborsabile) + storico
20. **OCR Bilancio** nel Cervello (`/cervello/ocr-bilancio`) — autofill costi annuali via Gemini
21. **OCR Corsi IVASS** + grafico 30h annuali per collaboratore
22. **Customer Insights Widget** (`/anagrafiche/{id}/customer-insights-widget`) — KPI, cross-selling opportunità, rischio score
23. **Storico avvisi** auto-move (`/storico-avvisi`)

### Testing (Iter 25)
- Backend: 17/18 PASS (1 skip atteso) — auto-fixato ObjectId leak in setup-iniziale
- Frontend: 7/7 pagine OK

## Backlog rimanente

### P3
- Refactor server.py (>10k righe) in moduli
- UI frontend per: Regolazione premio dialog · Libro matricola applicazioni page · OCR Bilancio button · OCR Corsi IVASS upload · Customer Insights widget in AnagraficaDetail · Documenti dropzone doppia (visibile/nascosto)
- Spoki/Twilio real dispatch (richiede API key utente)
- Indice MongoDB su ritenute_compagnia.compagnia_id

## Test credentials
Admin: `admin@assicura.it` / `Admin123!`

## Integrazioni
- **Emergent LLM Key**: Claude 4.5 (Assistente), Gemini 3 Flash (OCR libretto, Documenti Inbox, Bilancio, Corsi IVASS)
- **Twilio/Spoki/SMTP**: dispatch lead-liste in MOCK (logga `db.dispatch_log`)
