# Programma Assicurativo — PRD

## Vision
CRM full-stack in italiano per agenzie assicurative, vendibile come prodotto
modulare. Ogni cliente accende solo i servizi che gli servono.

## Stack
- Backend: FastAPI + MongoDB (Motor async) + APScheduler
- Frontend: React + Shadcn/UI + Tailwind
- PDF: ReportLab (con logo agenzia incluso)
- LLM/OCR: Gemini 3 Flash (via Emergent LLM Key)
- Comunicazioni: SMTP/IMAP, Twilio, wa.me, **Spoki** (BSP italiano)

## Personas
1. Admin agente — vede tutto, gestisce librerie
2. Collaboratore — gestisce clienti propri
3. Dipendente — opera senza eliminazioni
4. Cliente — vede solo i propri dati

## Moduli implementati
- Anagrafiche / Mappa / Portafoglio polizze (Veicolo dinamico)
- Titoli / Sospesi / Avvisi scadenze (con 🖨 PDF + logo)
- Sinistri / Pipeline / Calendario / Chat / Corsi / **Diario** / **Posta**
- Prima Nota / E/C Collaboratori / Compagnie / Rappel
- **Gestioni Modelli** redesignato a tabs (Email/WhatsApp/SMS/PDF)
- **Alert & Automazioni** con destinatari "altri collaboratori" checkbox
- Notifiche in-app → diario automatico
- **WhatsApp dispatch dual**: wa.me / Twilio / **Spoki**
- IMAP Poller + CTA "Attiva con email SMTP" one-click
- TopBar: avatar utente + nome (sx), logo agenzia (dx)
- `email_utils.py` per invio SMTP robusto con `From` ben formattato

## Backlog
### P1
- Visibility filter Librerie (collaboratore vede solo se stesso)
- Upload avatar in UtenteForm
- Logo + ragione sociale in TUTTI gli altri PDF (lettera abbuono, brogliaccio, diagnosi, prima nota)
- Dashboard componibile per operatore (widget drag&drop)
- Google Contacts / MS 365 / 3CX (richiedono credenziali)

### P2
- Refactoring `server.py` (>9700 righe)
- Dashboard "Stato integrazioni" per vendita modulare

## Changelog (29/06/2026 — completamento sezione strumenti AI)
- **Libreria Tipologie Sinistri**: nuova collection `tipologie_sinistri` con seed di 39 tipologie standard italiane (RC Auto/ARD/Vita/Casa/Azienda/Infortuni/Malattie/Tutela/Viaggio). Ogni tipologia ha flag `richiede_cai`, `richiede_denuncia`, `categoria`, `attivo`. Sezione "Tipologie sinistri" in Librerie con CRUD completo. Form Sinistri (Nuova + Detail) ora usa Select dropdown con badge informativo "📌 Richiede CAI / modulo denuncia"
- **Endpoint `/auth/me/permissions`**: ritorna `effective_permissions` dell'utente loggato + `is_full_admin` (per admin senza profilo) → il frontend può ora nascondere/disabilitare pulsanti in base ai reali permessi del profilo
- **Tag Catastrofale auto-detect**: helper `_detect_catastrofale()` rileva garanzie catastrofali (terremoto/alluvione/inondazione/sisma/sovraccarico) da campi `garanzie` + `ramo` + `prodotto` + `note`. Endpoint `POST /api/polizze/check-catastrofale-bulk` aggiorna flag su tutte le polizze. `GET /polizze/{id}/check-catastrofale` per singola
- **Customer Insights**: `GET /api/anagrafiche/{id}/insights` ritorna: cliente_da_mesi/giorni, sinistri (totali/ultimo anno/aperti), ultima interazione marketing+qualsiasi, polizze attive/ferme oltre 12 mesi, premio totale attivo, suggerimenti automatici (upsell, richiamo, check-up sanitario)
- **Sezione Statistiche** (`/statistiche`): KPI globali agenzia (clienti privati/aziende, nuovi 30g, polizze attive/scadute/in scadenza, premio attivo totale, sinistri aperti/ultimo anno) + Top 5 compagnie per premio + Top 5 rami per premio
- **Sezione Il Cervello** (`/cervello`): agente AI con regole automatiche → suggerimenti per: rinnovi imminenti (≤30g), sinistri fermi da oltre 90g, upsell catastrofale CASA privati, OBBLIGO LEGGE catastrofale aziende (D.Lgs ICAT). Filtro per priorità (Alta/Media), click su card naviga al record (polizza/sinistro/cliente)
- **Sezione Ritenute** (`/ritenute`): CRUD ritenute d'acconto collaboratori con calcolo automatico imponibile×aliquota, totali per anno/collaboratore, flag versata + data versamento, causale F24
- **Sidebar**: aggiunte 3 voci (Statistiche, Il Cervello, Ritenute) con icone Brain/Activity/Coins. Visibili a admin+collaboratore (Ritenute solo admin)

## Changelog (28/06/2026 — sera)
- **Permessi granulari per area (P0)**: esteso `ProfiloPermessi` con `area_permissions: Dict[area, Dict[azione, bool]]` oltre ai preset `area_levels`. Aggiunte azioni granulari per area: Sinistri (read/write/delete/upload_docs/edit_cid/liquida/print), Comunicazioni (read/send_email/send_sms/send_wa/template_edit), Polizze (read/write/delete/upload_docs/export/print/transfer), Titoli (incassa), Contabilità (chiusura_giorno), Dashboard (customize), ecc. Endpoint `GET /api/permessi-aree` ora ritorna `azioni_per_area`. Endpoint profili ritornano `effective_permissions` calcolate
- Dialog "Modifica profilo" rinnovato: matrice con preset rapido (3 radio Non gestito/Lettura/Scrittura) + colonna "Permessi specifici" con button espandibile per area che mostra checkbox per ogni azione granulare (es. "▸ Avanzati (4)" per Sinistri → Upload Docs · Edit Cid · Liquida · Print)
- **Filtri Titoli dropdown (P1)**: `Prodotto` e `Mezzo pag.` ora sono Select con opzioni caricate da `/api/librerie/prodotti` e `useMezziPagamento`. Voci "Tutti i prodotti" / "Tutti i mezzi" per reset
- **Avatar collaboratore nelle liste**: nuovo componente `<CollaboratoreCell />` con avatar tondo 20px + nome. Usato in Polizze, Titoli, Sinistri (colonna Collaboratore). Backend list arricchito con `collaboratore_avatar_url`. Fallback: iniziali del nome su gradiente sky→indigo

## Changelog (28/06/2026 — pomeriggio)
- **Avatar upload utenti**: aggiunto endpoint `POST /api/auth/users/{uid}/avatar` (admin oppure utente stesso, max 4 MB JPG/PNG/WEBP, salvataggio su object storage). Nuovo componente `AvatarUploader` nella tab Anagrafica del form Modifica utenti con preview, cambio e rimozione. Avatar disponibile per TopBar/Diario/Chat
- Voce **Corsi** già presente in sidebar (`/corsi`); tab Corsi nel form utenti già funzionante per gestione attestati IVASS con upload PDF/IMG

## Changelog (28/06/2026)
- **KPI cliccabili + dropdown filtro**: ogni KPI ora porta alla lista filtrata (es. "Auto privati" → /polizze?categoria=auto_priv). Il dialog "Personalizza KPI" ha "Valore filtro" come dropdown dinamico via `/api/kpi/options`. Aggiunto filtro `categoria` su `/api/polizze` (auto_priv, auto_az, altri_priv, altri_az, vita_inv, vita_prot)
- **Fix KPI Polizze backend**: risolto `JSONDecodeError` (`$group does not support inclusion-style expressions`). Riscritta `_stats_polizze` con classificazione Python (tipo anagrafica via tag azienda/condominio override)
- **Sinistri Release C**: modello esteso con `numero_interno`, `tipologia_sinistro`, `garanzie_colpite`, `soggetti_coinvolti`, `anagrafiche_associate`, `note`, `liquidazione_dettaglio`, `costatazione_amichevole`. Endpoint nuovi: `GET /api/sinistri/{id}` (singolo enriched), `PUT /api/sinistri/{id}/cid`, `GET /api/stampa/sinistro/{id}`, `GET /api/stampa/sinistro/{id}/cid`. Lista estesa con filtri `q/compagnia/ramo/tipologia/dal/al`
- **SinistroDetail page nuova** con tabs (Dati Generali · Soggetti · Anagrafiche · Note · Liquidazione · Documenti · Costatazione Amichevole RC Auto). Layout ispirato a gestionali italiani: header con riepilogo + tabs in basso
- **Costatazione Amichevole** (CID art. 143 D.Lgs. 209/2005): form compilabile con sezione data/luogo/feriti/danni, blocchi Veicolo A/B (precompilati da polizza/contraente), 17 circostanze checkbox, PDF stampabile a colori
- **Sinistri list redesign**: 13 colonne (Num.Int / N.Sinistro / Contratto / Data / Contraente / Compagnia / Tipologia / Danneggiato / Targa / Collaboratore / Riserva / Liquidato / Stato), totali in footer, click riga → detail
- **Fix MappaClienti**: la mappa Leaflet non si inizializzava perché l'effect partiva prima che il div `#anag-map` fosse nel DOM. Aggiunta dipendenza su `items` + `map.invalidateSize()` post-render

## Backlog
### P0
- **Permessi granulari per area** (richiesto via screenshot): estendere `ProfiloPermessi.area_permissions` con flag specifici per area (es. `read/write/upload_docs/delete/export/send_email` etc). Mantenere quick preset "Non gestito/Lettura/Scrittura"

### P1
- Filtri Titoli: convertire `Prodotto` e `Mezzo pag.` da Input a Dropdown (rami/prodotti/mezzi_pagamento già esistenti backend)
- Dashboard componibile per operatore (widget drag&drop) **per livello di visibilità/profilo**
- Edit collaboratore inline sulla riga sinistro / azioni bulk
- Visibility filter Librerie (collaboratore vede solo se stesso)

### P2
- Refactoring `server.py` (>9700 righe)
- Dashboard "Stato integrazioni" per vendita modulare
- Verifica polizza vs libretto
- Migrazione retroattiva MovimentiContabili per Titoli coperti storici

## Changelog (precedente)
- IMAP Poller + CTA "Attiva con email SMTP"
- Gestioni Modelli redesign (tabs canale + card visive)
- PDF Avviso: logo agenzia + nome + fix placeholder `{cliente_nome}` + lookup nome prodotto (no più UUID) + colonna "Rata del" popolata correttamente
- WhatsApp dual-provider: wame / twilio / **spoki** (API `https://api.spoki.com/api/1/messages/send`)
- Alert: `altri_collaboratori` con checkbox multi-select utenti
- Notifiche in-app → loggate nel Diario
- `email_utils.py`: helper centralizzato SMTP con `From` RFC-compliant
- Bug fix: rimosso decoratore orfano `@api.post("/email/avvisi-scadenze")` che rompeva una route
- TopBar redesign: avatar utente + ruolo (sx), logo agenzia (dx)
- Error handler robusto: `errMsg()` evita crash React su detail Pydantic array
- Fix CSS globale `tbl thead th { white-space: nowrap }` + frozen max-width
- Aggiunto `User.avatar_url`

## Credenziali test
Vedi `/app/memory/test_credentials.md`.

## Provider WhatsApp
- **wame**: link gratis, click manuale
- **twilio**: automatico ~€0.005/msg
- **spoki**: italiano BSP, X-Spoki-Api-Key + REST API
