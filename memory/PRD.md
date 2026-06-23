## Programma Assicurativo - PRD (FastAPI + React + MongoDB)

### Original problem statement
CRM Assicurativo per agenzie italiane. Gestione completa anagrafiche (albero familiare, intervista), polizze, titoli, sinistri, contabilità, statistiche. Multi-compagnia. INPS pension calculator con import PDF. Import ZIP ANIA giornaliero (eccetto data incasso/copertura che sono manuali). Ruoli: admin, collaboratore, dipendente, cliente. Stampe PDF con intestazione agenzia (logo).

Integrazioni richieste: WhatsApp, 3CX, Google Drive, Google Calendar, Google Contacts, OneDrive, Office 365.

UI italiano, Shadcn/Tailwind.

---

### Implementato — Sessione corrente (2026-06-23 fork 3)

#### Brogliaccio Prima Nota (replica facsimile)
- **Nuovo modulo PDF** `/app/backend/pdf_brogliaccio.py` - landscape A4, page 1 tabella con colonne dinamiche (Descrizione/Totale/Provv/Saldo/Crediti/Spese + colonna per ogni Conto Cassa attivo), page 2 RIEPILOGO CONTI (Imp.Precedente/Imp.Giornata/Totale Periodo) e KPI bottom (ENTRATE/PROVVIGIONI/CREDITI/RIMESSE/SCONTI/SPESE/SALDO CASSA).
- **Endpoint backend**: `GET /api/contabilita/brogliaccio?data=YYYY-MM-DD` calcola in tempo reale tutti i totali; `GET /api/contabilita/brogliaccio/stampa` ritorna il PDF. Colonne conti **generate dinamicamente** da `conti_cassa.attivo=true` (aggiungere una banca in Librerie → appare automaticamente).
- **KPI giornalieri** (coerenti con il totale giornata): Saldo Cassa = somma entrate − somma uscite del giorno.
- **Frontend `BrogliaccioTab.jsx`** in `/contabilita`: tab di default, date picker + Oggi shortcut, banner stato chiusura, tabella scrollabile, riga gialla TOTALE GIORNATA, riepilogo conti, 7 KPI cards.

#### Chiusura giornaliera + invio commercialista
- **Nuovo modello** `ChiusuraGiorno` (data, closed_by, riepilogo snapshot, pdf_storage_path, email_inviata_a/at, riaperta_at/by/motivo).
- **Endpoints**: `POST /api/contabilita/chiusura-giorno` (chiude + salva snapshot PDF in object storage + opzionale invio email), `POST .../{id}/invia` (invia email), `POST .../{id}/riapri` (admin only, richiede motivo), `GET /api/contabilita/chiusure-giorno` (storico), `GET /api/contabilita/chiusura-giorno/{id}/pdf` (scarica snapshot).
- **Lock movimenti chiusi**: PUT/DELETE su movimento con `chiusura_id` ritorna 400 con messaggio chiaro.
- **SMTP commercialista**: nuovi campi su `AziendaConfig` (`email_commercialista`, `nome_commercialista`, `invio_automatico_chiusura`, `smtp_host/port/user/password/from/use_tls`). UI in **Librerie → Azienda** con due sezioni dedicate (Commercialista + SMTP).
- **Invio email**: usa `smtplib` con SSL/STARTTLS, allega PDF al messaggio. Se SMTP/email non configurati, ritorna `{ok:false, errore:"..."}` senza eccezioni.

#### Modelli estesi
- `MovimentoContabile` ora ha `quota_provvigione`, `quota_saldo`, `quota_credito`, `quota_spesa`, `quota_sconto`, `chiusura_id` per supportare il brogliaccio.

#### Allegati su Movimenti Contabili e Titoli
- Il modello `Allegato` ora accetta `entita_tipo="titolo"` (oltre a "movimento" già esistente). Endpoint generico `POST /api/allegati?entita_tipo=movimento|titolo&entita_id=...` (multipart upload, max 25MB). `GET /api/allegati`, `GET /api/allegati/{aid}/download`, `DELETE /api/allegati/{aid}`. Le liste `/contabilita/prima-nota`, `/contabilita/movimenti` e `/titoli` ora restituiscono `allegati_count` per ogni record.
- **Voci manuali Estratto Conto Collaboratori**: nuovo modello `VoceManualeCollab` (bonus positivi / trattenute negative). Endpoints `GET/POST /api/collaboratori/{cid}/voci-manuali` e `DELETE .../{vid}`. Aggiornato `estratto-provvigioni` con totali `voci_manuali_da_pagare` e netto includente le voci. Aggiornato `paga-provvigioni` per pagare anche voci manuali; al pagamento le voci sono marcate `pagata=true` con `pagamento_id`.
- **ACL collaboratori**: il ruolo `collaboratore` può accedere solo al proprio `cid` su `estratto-provvigioni`, `voci-manuali`, `paga-provvigioni` (403 altrimenti).
- **Relazioni familiari estese**: `POST/PATCH /api/anagrafiche/{aid}/relazioni` accettano `lavoratore` (per coniuge), `a_carico` (coniuge/figlio), `handicap` (figlio). `GET /anagrafiche/{aid}.relazioni_risolte` espone i tre attributi.
- **Polizze - filtri completi**: `GET /api/polizze` aggiunti filtri `q`, `compagnia_id`, `collaboratore_id`, `prodotto`, `dal/al` (scadenza), `in_scadenza_giorni`, `scadenza_oltre_giorni`, `scadute_oggi`, `scadute_da_min`, `scadute_da_max`. Enrichment con `collaboratore_nome`. Esportazioni nuove: `GET /api/export/polizze.csv`, `GET /api/export/polizze.xlsx`. Aggiornato `/stampa/polizze` con tutti i filtri + colonna collaboratore.

#### Frontend
- **AllegatiCell (componente riusabile)**: `/app/frontend/src/components/AllegatiCell.jsx`. Popover con icona graffetta che mostra l'elenco allegati, permette upload (multipart), download (apre in nuova tab) e delete. Usata in Prima Nota e Titoli.
- **Prima Nota (`/contabilita`)**: nuova colonna **Allegati** con graffetta + contatore. Suggerimento contestuale: "Allega ricevuta / assegno" per entrate, "Allega fattura / busta paga" per uscite.
- **Titoli (`/titoli`)**: nuova colonna **Allegati** con graffetta + contatore. Suggerimento "Allega ricevuta bonifico / assegno".
- **Pagina Estratto Conto Collaboratori (`/provvigioni`)**: nuova sezione "Voci manuali" con dialog "Nuova voce" (data, causale, importo +/-, note). Riga voci selezionabili e pagabili insieme ai titoli. Card "Voci manuali" nel set di 6 stat cards.
- **Pagina Polizze (`/polizze`)**: rinnovata con preset chips (tutte / attive / in scadenza 15gg / oltre 15gg / scadute oggi / scadute da 5-10-14gg / scadute / sospese / annullate), search box, filtri avanzati toggleable (stato, compagnia, ramo, collaboratore, prodotto, dal/al). Toolbar export: **Stampa PDF**, **CSV**, **Excel**. Footer con totali premio e provvigioni.
- **AnagraficaDetail - Albero genealogico**: dialog "Aggiungi relazione" ora mostra blocco "Dati per assegno familiare / nucleo" con checkbox condizionali (lavoratore per coniuge, a_carico per coniuge/figlio, handicap per figlio). Badge colorati sulle card relazioni (verde "a carico", ambra "L.104", sky "lavoratore"). Dialog "modifica" per aggiornare gli attributi su relazioni esistenti.

### Implementato — Sessione precedente (2026-06-22 fork 2)

#### Backend
- **ANIA importer**: test E2E completo con ZIP sintetico (rec10/20/21/30/40/50). Veicolo, garanzie, diritti, BM, franchigia, massimali, rinuncia rivalsa, valore veicolo. Idempotente. `/app/backend/tests/test_ania_import.py`.
- **Modelli nuovi**: `AziendaConfig`, `SchemaProvvigionale`, `EventoCalendario`. Estensione `UserPublic` con documenti (firma/CI/casellario/carichi pendenti/IBAN) e corsi/attestati. Estensione `Anagrafica/Titolo/Sinistro` con `collaboratore_id`.
- **Librerie/Azienda**: `GET/PUT /api/librerie/azienda` (singleton) + `POST /api/librerie/azienda/logo`.
- **Sistema provvigionale**: CRUD `/api/librerie/schema-provvigionale` con risoluzione gerarchica (collaboratore+compagnia+ramo). Endpoint `risolvi`.
- **Documenti collaboratore**: `POST/DELETE /api/auth/users/{uid}/documenti/{tipo}`, `POST /api/auth/users/{uid}/corsi`, `POST .../corsi/upload`.
- **Storage generico ACL**: `/api/storage/{path}` con ACL (solo proprietario/admin per /users/).
- **PDF stampe**: intestazione con logo + ragione sociale + RUI + indirizzo + footer. Funzione `pdf_report.get_intestazione_azienda(db)`.
- **Estratto conto compagnie + Saldi cassa**: `GET /api/compagnie/{cid}/estratto-conto`, `/api/compagnie/saldi-cassa`, stampe PDF.
- **Utility Codice Fiscale**: `POST /api/utility/codice-fiscale/calcola` e `.../decodifica` (libreria `python-codicefiscale` con dataset ISTAT).
- **Geocoding automatico**: `POST /api/utility/geocoding` via Nominatim/OpenStreetMap (gratis, senza chiave).
- **OCR Carta d'Identità**: `POST /api/utility/ocr-carta-identita` (Gemini 3 Flash via Emergent Universal Key). Supporta PDF (prima pagina) + JPG/PNG. Estrae: cognome, nome, sesso, data nascita, comune nascita, CF, numero doc, scadenza, comune emissione.
- **Calendario**: CRUD `/api/calendario` con auto-eventi scadenze polizze (rosso). Filtro per operatore.
- **List anagrafiche arricchita**: ritorna `polizze_attive_count`, `categoria_ui` (con_polizze/senza_polizze/condominio), `collaboratore_nome`. Filtro per tag.

#### Frontend
- **Librerie**: tab Azienda (intestazione + upload logo), Sistema provvigionale, Utenti/Collaboratori esteso (tabs anagrafica/fiscale/documenti/corsi).
- **Anagrafiche**: lista con dot colorati 🔵🔴🟢 + chip filtri categoria + chip tag univoci cliccabili che filtrano. Colonna Operatore.
- **Form Nuova Anagrafica**: toolbar OCR CI (auto-compila tutti i campi), pulsanti Calcola CF / Decodifica CF, geocoding al blur (lat/lng), assegnazione Collaboratore.
- **Estratto Conto Compagnie**: pagina dedicata `/compagnie-estratto` con KPI cards (totale da versare, a credito), tabella saldi, dettaglio per compagnia con filtri data e stampa PDF.
- **Calendario**: vista mensile con 7 colonne + 6 settimane. Eventi colorati per tipo (appuntamento/scadenza polizza/titolo/sinistro/promemoria). Filtro per operatore. Doppio click su giorno → nuovo evento. Click su evento → modifica/elimina.
- **Sidebar**: nuove voci sotto Contabilità: Titoli (incassi), E/C compagnie, Calendario.

### Backlog / Pending (per prossima sessione)

#### P0 — Operatività residua
- Aggiungere campo "Operatore" (collaboratore_id) anche in form di Polizze, Titoli, Sinistri
- Card "Premi e Provvigioni" (privato/azienda/totale) in AnagraficaDetail (backend pronto)
- Newsletter UI con tag multi-select
- Payout Provvigioni Collaboratore → uscita negativa nel Brogliaccio

#### P1 — Integrazioni Calendar/Contacts (richiedono OAuth)
- **Google Calendar sync**: OAuth Google + integrazione gcal
- **Microsoft 365 Calendar sync**: Azure App registration + Graph API
- **Google Contacts / Outlook Contacts sync**
- Per attivarle: chiedere all'utente di creare le App OAuth (Client ID/Secret)

#### P1 — Misc
- INPS regressione: verificare flusso completo (parsing PDF, modifica campi, salvataggio)
- Mappa clienti integrare lat/lng da geocoding
- OneDrive/Google Drive per Corsi

#### P2 — Integrazioni avanzate
- WhatsApp, 3CX (centralino), Pipeline email gestita

#### Tech debt
- Refactor `server.py` (~3500 righe) in router per dominio
- Test unitari pytest sulle utility (CF, geo, OCR)

---

### Architettura
```
/app/backend/
  server.py            (~3500 righe - DA REFACTORIZZARE)
  db_models.py
  ania_importer.py
  inps_calculator.py
  brogliaccio.py
  pdf_report.py        (con intestazione + logo)
  storage.py
  auth.py
  cf_calc.py           NEW - Codice Fiscale (calcola + decodifica)
  geocoder.py          NEW - Nominatim OSM
  ocr_ci.py            NEW - OCR Carta Identità via Gemini Vision
  tests/test_ania_import.py
/app/frontend/src/
  pages/Anagrafiche.jsx        REWRITTEN - colori, tag chip, OCR, CF, geo
  pages/Librerie.jsx           ESTESO - Azienda, Sistema Provv, Documenti utenti
  pages/Calendario.jsx         NEW
  pages/EstrattoContoCompagnie.jsx  NEW
  pages/PolizzaDetail.jsx, Titoli.jsx, ...
  components/Sidebar.jsx       Aggiornato con E/C compagnie, Calendario
```

### Test credentials
File `/app/memory/test_credentials.md`. Admin: `admin@assicura.it / Admin123!`

### Backend health
✅ UP. Tutti i nuovi endpoint testati con curl: CF calcola/decodifica, Geocoding, Saldi compagnie, Calendario CRUD.

---

## 2026-06-22 — Tab "Analisi Cliente" completa (SatorCRM-like)

### Aggiunto
- **Tab "Analisi Cliente"** in scheda anagrafica con **7 sotto-tab**:
  1. **Situazione Finanziaria** — reddito lordo, dividendi, altri redditi, affitti, regime forfettario, TFR, liquidità, debiti, oneri deducibili/fondo pensione, capacità risparmio, appetito al rischio (entrate/patrimonio)
  2. **Patrimonio** — Immobili (tipo, titolo, %, valore, cat. catastale, rendita), Veicoli, Beni, Aziende (formula EBITDA×7 ± PFN)
  3. **Contesto & Obiettivi** — 3 box contesto + 4 domande aspirazionali (felicità, carriera, eredità, pensione)
  4. **Approfondimento Redditi** — calcolo automatico contributi previdenziali, IRPEF lorda/netta con scaglioni 2026, detrazioni coniuge/lavoro dipendente, reddito netto
  5. **Pensione INPS** — carriera contributiva, storico redditi multi-anno, pensioni di **OGGI** (Invalidità grave 66-99%, Inabilità totale 100%, Superstiti — calcolate **sempre tutte e tre**), pensioni del **DOMANI** (proiezione 64-71 anni con modalità Anticipata/Vecchiaia, montante)
  6. **Riepilogo Pensionistico** — scoperture mensili/annuali, capitale da assicurare per Invalidità/Inabilità/Premorienza/Vecchiaia, copertura percentuale con KPI colorati
  7. **Successione** — calcolo automatico quote senza testamento (artt. 565-586 c.c.) e quote di legittima (artt. 536-553 c.c.) con grafico a barre + tabella euro

- **Generazione PDF** professionali:
  - `GET /api/anagrafiche/{id}/analisi/pdf-diagnosi-reddito` — "**Diagnosi del Reddito**" (17 pagine: situazione famigliare, contributiva, prestazioni maturate, riserve, fabbisogno, raccomandazione, checklist controlli)
  - `GET /api/anagrafiche/{id}/analisi/pdf-progetto-azzob` — "**Progetto Futuro Senza Sorprese**" (metodo AZZOB ISO 31000: Contesto, Obiettivi, Appetito al rischio con scaglioni, Mappatura 4 rischi, Valutazione)

### Nuovi moduli backend
- `/app/backend/successione_calc.py` — calcolo quote successione legittima e legittima per i casi standard del Codice Civile italiano
- `/app/backend/reddito_calc.py` — calcolo contributi/IRPEF/netto + funzione `calcola_scoperture_pensionistiche`
- `/app/backend/pdf_diagnosi.py` — generatore reportlab dei due PDF
- Estensione `db_models.py` con `AnalisiCliente`, `ImmobileItem`, `VeicoloItem`, `BeneItem`, `AziendaItem`, `RedditoStoricoItem`, `PeriodoContributivoItem`
- 8 nuovi endpoint API sotto `/api/anagrafiche/{aid}/analisi/*`

### Nuovo componente frontend
- `/app/frontend/src/components/AnalisiClienteTab.jsx` (700+ righe) — composto con sotto-tab, infografica KPI, grafici a barre per successione, tabelle interattive

### Mantenuto
- Vecchio tab "Pensione INPS" preservato per retrocompatibilità (richiesta utente)

---

## 2026-06-22 — Privacy & Consensi GDPR (template Schiantarelli)

### Aggiunto
- **PDF Informativa Privacy GDPR** professionale ispirato al template "Assicurazioni Schiantarelli Marco Andrea SAS" (artt. 13-14 Reg. UE 2016/679):
  - Header con ragione sociale azienda + indirizzo + "INFORMATIVA CLIENTE - PROSPECT"
  - Tabella dati cliente precompilati (cognome/nome, CF/P.IVA, indirizzo, CAP, comune, provincia, email, cellulare, telefono)
  - Testo informativa completo: Finalità, Natura conferimento, Modalità, Tempi, Ambito, Diritti, Titolare
  - **4 caselle di consenso flaggabili** (☒/☐) con base giuridica per ciascuna:
    - Trattamento dati particolari (punto 1)
    - Marketing diretto (punti 2a, 2b, 2c)
    - Comunicazione dati a terzi (punto 2d)
    - Profilazione (punto 2e)
  - **Firma digitale** del cliente (immagine PNG estratta dallo storage) integrata nel PDF
- **Dialog "Privacy & Consensi"** nel tab Documenti: toggle dei 4 consensi, canvas per firma touch/mouse, salvataggio, generazione PDF

### Backend
- Nuovo `/app/backend/pdf_privacy.py` (450+ righe) — generatore reportlab con header/footer paginati
- `PUT /api/anagrafiche/{aid}/consensi-privacy` — aggiorna i 4 flag di consenso
- `GET /api/anagrafiche/{aid}/privacy/genera-pdf` — riscritto per usare nuovo template
- 2 nuovi campi in `Anagrafica`: `consenso_dati_particolari`, `consenso_comunicazione_terzi`

### Frontend
- `/app/frontend/src/components/PrivacyConsensiDialog.jsx` — modale completa con consensi + firma + PDF
