# Programma Assicurativo - CHANGELOG

## 2026-06-22 — fork 2 (sessione corrente)

### Backend
- **ANIA importer** end-to-end testato (`/app/backend/tests/test_ania_import.py`): veicolo, garanzie, diritti, BM, franchigia, massimali, rinuncia rivalsa. Re-import idempotente.
- **Modelli nuovi**: `AziendaConfig`, `SchemaProvvigionale`, `EventoCalendario`. Estensione `UserPublic` (firma digitale, CI, casellario, carichi pendenti, IBAN, corsi/attestati). Aggiunta `collaboratore_id` su `Anagrafica/Titolo/Sinistro`. Aggiunti `importo_pagato/sconto_applicato/motivo_sconto` su `Titolo`. Categoria `sconto_cliente` aggiunta a `MovimentoContabile`.
- **Librerie/Azienda**: GET/PUT `/api/librerie/azienda` + upload logo. Usato in **TUTTE le stampe PDF** (intestazione+logo+RUI+footer).
- **Sistema provvigionale**: CRUD `/api/librerie/schema-provvigionale` con risoluzione gerarchica.
- **Documenti collaboratori**: `/api/auth/users/{uid}/documenti/{tipo}`, `/api/auth/users/{uid}/corsi`.
- **Storage ACL**: `/api/storage/{path}` (admin/proprietario only per /users/).
- **Utility**:
  - `POST /api/utility/codice-fiscale/calcola` e `.../decodifica` (libreria `python-codicefiscale` con dataset ISTAT)
  - `POST /api/utility/geocoding` via Nominatim/OSM gratuito
  - `POST /api/utility/ocr-carta-identita` (Gemini 3 Flash via Emergent Universal Key, PDF+JPG+PNG)
- **Compagnie**: `GET /api/compagnie/{cid}/estratto-conto`, `/api/compagnie/saldi-cassa` + stampe PDF.
- **Calendario**: CRUD `/api/calendario` con auto-eventi scadenze polizze. Filtro per operatore.
- **List anagrafiche arricchita**: `polizze_attive_count`, `categoria_ui`, `collaboratore_nome`, filtro per tag.
- **Sospesi / titoli anticipati**: `GET /api/titoli/sospesi` arricchito (cliente, collaboratore, data copertura, scadenza, importo, giorni anticipo).
- **Copertura titoli**: ora default = OGGI (data_copertura), significato "agenzia anticipa al cliente". Titolo resta da_incassare finché cliente non paga.
- **Incasso con sconto**: endpoint `POST /api/titoli/{tid}/incassa` accetta `importo_pagato` e `motivo_sconto`. Se importo_pagato < lordo → crea automaticamente movimento entrata (importo pagato) + movimento uscita (categoria `sconto_cliente`) in prima nota. Tracciamento automatico nel diario cliente.

### Frontend
- **Anagrafiche.jsx** riscritto: dot colorati 🔵🔴🟢, filtri categoria, chip tag cliccabili, colonna operatore. Form con OCR CI, Calcola CF / Decodifica CF, Geocoding auto al blur.
- **Librerie.jsx** esteso: tab Azienda, Sistema provvigionale, Utenti/Collaboratori con sotto-tab Anagrafica/Fiscale/Documenti/Corsi.
- **Calendario.jsx** nuovo: vista mensile, eventi colorati per tipo, scadenze polizze auto, filtro operatore.
- **EstrattoContoCompagnie.jsx** nuovo: KPI cards + tabella saldi + dettaglio con filtri data + stampa PDF.
- **TitoliSospesi.jsx** nuovo: lista clienti anticipati dall'agenzia, KPI (count, importo totale, anticipo più vecchio), pulsante "Incassa" con dialog che gestisce **sconto automatico**: se importo pagato < lordo, mostra il delta in giallo e spiega che verrà registrato come uscita "sconto_cliente" in prima nota.
- **Titoli.jsx**: dialog copertura semplificato (data copertura = oggi, no più "fino al"), colonna mostra `data_copertura`.
- **Sidebar.jsx**: nuove voci Titoli (incassi), Sospesi, E/C compagnie, Calendario.

### Test credentials
Admin: `admin@assicura.it / Admin123!`
