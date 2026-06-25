# PRD - Programma Assicurativo (Insurance CRM)

## Original Problem Statement
Italian Insurance Agency CRM (FastAPI + React + MongoDB). Anagrafica clienti, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), avvisi scadenze.

## Latest Session (Iter 20-22)

### Done
- ✅ Fix "Sospesi (da incassare)" preset Titoli: ora richiede `stato=da_incassare` AND `titolo_coperto=true` AND `data_copertura` valorizzata (backend param `titolo_coperto` aggiunto)
- ✅ Chat con allegati: bottone Paperclip, anteprima file, upload max 25MB, immagini inline, PDF/doc come bottone download
- ✅ Notifiche chat: badge nel Bell della topbar (sistema preesistente con `/notifiche/sommario` arricchito)
- ✅ OCR Libretto via Gemini 3 Flash: endpoint `/api/ocr/libretto` + `/api/ocr/libretto/apply`, `ocr_libretto.py` con prompt strutturato, EMERGENT_LLM_KEY configurato. Frontend già pronto in `DocumentiPolizzaTab.jsx` (era già implementato ma chiamava endpoint mancante)
- ✅ KPI Anagrafiche custom per Tag: endpoint `/api/anagrafiche/kpi-custom` (CRUD per utente)
- ✅ Sidebar "Polizze" rinominata in "Portafoglio"
- ✅ Cascata Ramo→Prodotto in PolizzaDetail (EditDialog): dropdown Ramo carica `/librerie/rami`, cambio ramo → reset prodotto + fetch `/librerie/prodotti?ramo=X`
- ✅ Spunta "Mostra sezione Dati veicolo" nel prodotto Libreria (campo `mostra_sezione_veicolo` nel ProdottoLibreria)

### Frontend lib aggiunte
- `/app/frontend/src/lib/phone.js` — formattazione `+39 347 000 9438`
- `/app/frontend/src/components/AddressAutocomplete.jsx`
- `/app/frontend/src/components/TagsEditor.jsx`
- `/app/frontend/src/pages/Chat.jsx` — riscritto con allegati

### Backend aggiunto
- `/app/backend/ocr_libretto.py`
- Endpoints: `/api/geo/suggest`, `/api/anagrafiche/stats`, `/api/anagrafiche/{aid}/network`, `/api/anagrafiche/tags`, `/api/dashboard/tasks`, `/api/ocr/libretto`, `/api/ocr/libretto/apply`, `/api/anagrafiche/kpi-custom` (CRUD), `/api/stampa/titoli/sospesi`
- Backend param `titolo_coperto` su `GET /titoli`

## Backlog
### P1
- UI "Personalizza KPI" (dialog + bottone ⚙️) per usare la API kpi-custom — backend pronto
- Sezione "Dati veicolo" completa visibile in PolizzaDetail quando: ramo=RCAuto OR targa esiste OR prodotto.mostra_sezione_veicolo=true — tutti i campi già nel modello (veicolo_*, tipo_tariffa, bm_*, valore_*, guida_*, rinuncia_rivalsa, intestatario, massimali)
- Replicare cascata Ramo→Prodotto anche in altri form di creazione polizza
- Personalizzazione KPI Anagrafiche custom basata sui TAG (UI frontend)

### P2
- Refactor server.py (>10000 righe) in /backend/routes/
- Risoluzione import circolare in auth.py
- Piramide Soluzioni — Release B
- Integrazioni Google Calendar / Microsoft 365 / WhatsApp / SMS

## Credenziali test
admin@assicura.it / Admin123!
