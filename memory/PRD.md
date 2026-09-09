# Programma Assicurativo — PRD (aggiornato 09/09/2026)

- **Form Nuova polizza — ordine invertito Agenzia → Compagnia** (Polizze.jsx): il campo "Agenzia (mandato)" è ora la **prima scelta** (elenca principale=diretto + tutte le partner). La tendina "Compagnia" è disabilitata finché non si sceglie l'agenzia e mostra **solo le compagnie collegate a quell'agenzia** (principale → compagnie a mandato diretto; partner → compagnie con quel `agenzia_partner_id`). Cambiando agenzia si azzera la compagnia. Risolve l'ambiguità delle compagnie omonime con partner diversi. Verificato e2e (Bottoni → UnipolSai/TEST/GROUPAMA).

## Sessione 09/09/2026 (fork) — Batch 9: Fix Estratto Conto Compagnie + header polizza

- **Colonna "Agenzia partner" in Estratto conto compagnie** (EstrattoContoCompagnie.jsx): l'endpoint `/compagnie/saldi-cassa` ora restituisce `tipo_mandato` + `agenzia_partner_id` + `agenzia_partner_nome`. La tabella mostra, per i mandati in collaborazione, l'agenzia partner a cui versare (icona Handshake, viola); per i diretti "Diretto (compagnia)". Se collaborazione senza partner impostato → "partner non impostato" (ambra). Verificato via API + screenshot.
- **Colonna "Agenzia partner" anche nel widget "Saldo cassa per compagnia"** (BrogliaccioTab.jsx / Prima nota): `_compute_saldi_compagnie` ora include `tipo_mandato`/`agenzia_partner_id`/`agenzia_partner_nome`. Stessa resa (partner viola / "Diretto (compagnia)"). Verificato via API + screenshot.
- **NOTA modello dati (chiarita all'utente)**: stessa compagnia con DUE agenzie partner diverse (es. GROUPAMA·Bottoni e GROUPAMA·Pozzi) = due record compagnia distinti con lo stesso nome ma `agenzia_partner_id` diverso; la colonna "Agenzia partner" li distingue. Diverso dal doppione vuoto rimosso.

- **🔴 FIX P0 — Compagnia mancante dall'Estratto Conto Compagnie**: `_compagnia_estratto_data` (server.py ~riga 936) faceva `contr_map[c["id"]] = c["ragione_sociale"]` con accesso diretto alla chiave → per un contraente **persona fisica** (senza `ragione_sociale`) lanciava `KeyError`, l'intera funzione andava in eccezione e `saldi_cassa_compagnie` la scartava in silenzio (`try/except: continue`) → la compagnia (GROUPAMA GPM) spariva dall'estratto. Corretto con `c.get("ragione_sociale") or "{cognome} {nome}"`.
- **🔴 FIX P0 — Coerenza "trattiene provvigioni"**: l'estratto conto **forzava** `trattiene=False` per i mandati `collaborazione`, mostrando il DARE al lordo (es. 489€) mentre Brogliaccio/Saldo cassa usavano il flag della compagnia. Rimossa la forzatura: ora l'unica fonte di verità è `compagnia.trattiene_provvigioni`. GROUPAMA (trattiene=sì) → DARE al netto provvigioni = 443,41€ (489 − 35,59 − 10). La polizza 1212 dà 90€ come nel Brogliaccio.
- **Data cleanup**: eliminato il doppione compagnia vuoto "groupama" (cod. 005, 0 polizze/titoli/movimenti) nel tenant `tenant-principale-schiantarelli`. Resta la sola "GROUPAMA" (cod. GPM, 22 polizze).
- **PolizzaDetail header**: ripristinato il **nome dell'agenzia partner** sotto il numero polizza (`pol-header-agenzia-partner`), mostrato solo se presente (`pol.mandato`). Nella modifica precedente era stato rimosso del tutto per errore.
- Verificato via API autenticata + screenshot UI (E/C compagnie: GROUPAMA 443,41€, 11 compagnie, doppione sparito).



## Sessione 09/09/2026 (fork) — Batch 8: Modelli PDF per sezione, generazione documenti, unione Documenti, Task collegabili

- **5 modelli PDF predefiniti per sezione** (auto-seed da `/app/backend/assets/modelli_default/*.json`, idempotente): Scheda anagrafica cliente, Modulo RID/SEPA, Autocertificazione stato di famiglia (contraente); Documento di polizza (polizza); Documento di sinistro (sinistro). Corpi generati via AI (Claude) con segnaposto.
- **Motore generazione documenti** (`routes/documenti_genera.py`): `GET /api/documenti/modelli-sezione?sezione=`, `POST /api/documenti/genera` (compila i segnaposto coi dati reali di contraente/polizza/sinistro, PDF reportlab, salva=true → allegato categoria `documento_generato`, opzione firma eSAW). Segnaposto speciale `{stato_famiglia}` espande i familiari del cliente (campo `parente_di`).
- **Pulsante "Genera documento"** (`components/GeneraDocumentoButton.jsx`) in AnagraficaDetail (Documenti), PolizzaDetail (accanto a MUP), SinistroDetail (Documenti): seleziona modello → testo editabile → Anteprima/Firma/Genera e archivia. Verificato e2e (12/12 backend iter 83, frontend OK).
- **Unione blocchi Documenti (AnagraficaDetail)**: caselle fisse (CI/patente/CF/…) + allegati caricati ora in UN unico blocco "Documenti" con griglia uniforme. Rimossi i doppioni "Visura camerale" e "Documenti identità" dalle cartelle allegati (i file confluiscono in "Altri documenti").
- **CarichiMensili**: colonna Note non più troncata (va a capo).
- **Task collegabili** (`routes/tasks.py`): campi `collegamento_tipo` (anagrafica|polizza|titolo) + `collegamento_id` + `collegamento_label`; `GET /api/tasks/collegati?entita_tipo=&entita_id=` (default solo attivi). Dialog Task con selettore "Collega a" + ricerca (cliente/polizza). Pannello "Attività aperte collegate" (`components/TaskCollegati.jsx`) in scheda cliente e polizza, con completamento rapido. Verificato via curl + screenshot.

## Sessione 09/09/2026 (fork) — Batch 7
: MUP libreria + testo + flag sezione, bug PDF, campo agenzia partner, provv. collaboratore, unisci doppioni

- **MUP → libreria (Librerie → "Modelli MUP")**: nuova collezione `mup_modelli` tenant-scoped (backend `routes/mup.py`): CRUD `/librerie/mup-modelli`, seed 5 modelli predefiniti per ramo (Auto/RC Auto, Beni, Infortuni, Vita, Generica). Il MUP di polizza usa il modello con l'area corrispondente (o quello scelto nel selettore). Componente `ModelliMupSezione`/`ModelloMupDialog` in `Librerie.jsx`.
- **MUP → modale editabile in polizza (era MANCANTE dal fork)**: `PolizzaDetail.jsx` ora renderizza `mup-dialog` con selettore modello, tabella garanzie con checkbox richiesta/proposta/confermata, Anteprima PDF, Genera+archivia (allegato categoria `mup`), Firma eSAW. Quadrato "MUP" aggiunto nella sezione Documenti.
- **MUP → testo precontrattuale con aggancio dati**: campo `corpo` sul modello MUP con segnaposto ({contraente},{cliente_cf},{compagnia},{collaboratore},{agenzia_nome},{agenzia_rui},{numero_polizza},{ramo},{prodotto},{premio_lordo},{data_oggi}), sostituiti coi dati reali nel PDF (`_ph_context`/`_sub`).
- **BUG FIX MUP PDF**: le garanzie non spuntate apparivano tutte "piene" (glifi ☑/☐ non supportati da Helvetica). Ora: spuntata = "SÌ", non spuntata = "—". Verificato via pdfplumber.
- **Flag visibilità per sezione (contraente/polizza/sinistro/preventivo)** su ENTRAMBI i tipi di modello (`TemplateModello.sezioni_visibili`, `MupModello.sezioni_visibili`). List endpoints accettano `?sezione=`; nessun flag = non visibile (backfill dei modelli esistenti a tutte le sezioni). UI: `SezioniVisibiliPicker` in entrambi i dialog. Consumatore LIVE: selettore MUP in polizza filtra a `sezione=polizza`. NOTA: per contraente/sinistro/preventivo i picker "genera documento da modello" non esistono ancora → follow-up per consumare i flag lì.
- **Polizze (form nuova polizza)**: campo "Collaboratore (Operatore)" spostato SOPRA "Contraente"; nuovo select "Agenzia partner" accanto a Compagnia, precompilato in base alla compagnia (diretto→principale, collaborazione→agenzia partner).
- **PolizzaDetail → Provvigioni**: accanto al nome collaboratore mostrato l'importo "Provv. collaboratore" (`pol-collab-provv-inline`).
- **BUG FIX Anagrafiche**: pulsante "Unisci doppioni" non apriva nulla (dialog non montato) → montato `UnisciDoppioniDialog`.
- **Utenti/Collaboratori**: solo personale di agenzia (no clienti, no super_admin, solo tenant proprio). `list_users` in server.py.
- **Agenzie**: l'agenzia principale collega compagnie a mandato diretto (dialog dedicato + conteggio backend).
- **Modelli → Carica PDF (tab PDF)**: `POST /librerie/modelli/da-pdf` estrae testo (pdfplumber) e crea modello con segnaposto via Claude (Emergent LLM Key).

## Sessione 09/09/2026 (fork) — Batch 6
: Utenti solo staff, Agenzia partner label, Principale mandato diretto, Modelli da PDF (AI)

- **Librerie → Utenti / Collaboratori: solo personale di agenzia**. La lista `/auth/users` ora filtra i `role === "cliente"` (i clienti si gestiscono in Anagrafiche). Rimossa l'opzione ruolo "Cliente" dal form utente e il relativo blocco "Anagrafica cliente collegata". Verificato a schermo (15 elementi: admin/collaboratori/dipendenti, nessun cliente). `Librerie.jsx` (`load`, `UtenteForm`).
- **PolizzaDetail: "Mandato" → "Agenzia partner"** (header blu + form modifica). Il valore `pol.mandato` rappresenta l'agenzia partner (terminologia utente). Solo label.
- **Agenzie → l'agenzia PRINCIPALE può collegare le compagnie a mandato diretto**. Prima il pulsante "Collega compagnie" era solo per le partner. Ora la card principale mostra "Compagnie con mandato diretto: N" + pulsante. `CollegaCompagnieDialog` è tenant/tipo-aware: per la principale pre-seleziona le compagnie senza `agenzia_partner_id` (=diretto), selezionandone una collegata a partner la riporta a `tipo_mandato=diretto, agenzia_partner_id=null`. Backend `routes/agenzie.py`: `n_compagnie_collegate` per la principale = `count(agenzia_partner_id=None)`. Verificato UI + curl (principale=7).
- **Librerie → Gestioni Modelli: "Carica PDF" (tab PDF)**. Nuovo endpoint `POST /api/librerie/modelli/da-pdf` (`routes/modelli.py`): estrae il testo con pdfplumber, lo trasforma via **Claude (claude-sonnet-4-6, Emergent LLM Key)** in un modello con i `{segnaposto}` del CRM (whitelist `_PLACEHOLDER_DISPONIBILI`), lo salva come `TemplateModello` (categoria `da_pdf`) e lo apre nel form per la revisione. UI: pulsante `modelli-carica-pdf` visibile solo nella tab PDF. Verificato e2e via curl (lettera → template con cliente_nome/numero_polizza/compagnia_nome/data_scadenza/premio_lordo/azienda_*).
- **MUP**: backend (`routes/mup.py`) + modale editabile in `PolizzaDetail.jsx` (checkbox garanzie per ramo, genera/anteprima/archivia tra gli allegati polizza categoria `mup`, firma eSAW) già completi. In attesa di test lato utente.


## Sessione 08/09/2026 (fork) — Batch 5: Estratto conto, Report Azienda, Immobili, Documenti, eSign

- **Report di gruppo** (`?gruppo=true` su report-azienda pdf/docx): sezione "Società del gruppo — quadro consolidato" con capogruppo + collegate (da `parente_di`) e riga TOTALE GRUPPO. Il frontend chiede conferma se ci sono collegate. Estratto conto già supporta il gruppo via `includi_collegati`. Verificato via curl.

- **Estratto conto contraente** (nuova pagina `/contraente-estratto`, sidebar contabilità): elenco titoli di un contraente in un periodo con filtri (rata/emissione/copertura), dati di pagamento (metodo con fallback conto cassa), totali (premi/addizionali/già pagato/DA PAGARE), preview + PDF. Pulsante **"Salva in anagrafica"** → allegato categoria `estratto_conto` (nuova cartella "Estratti conto" nei Documenti). Include contraenti collegati opzionale. `routes/estratto_conto_contraente.py`. Testato iter 79/80.
- **Report Analisi Azienda PDF + Word** (`routes/report_azienda.py`, pulsanti in Salute Fiscale `sf-report-pdf-btn`/`sf-report-word-btn`): prende dati reali da `salute_fiscale_dati` (bilancio, storico, indicatori), amministratori, MDC/impatto e include la **Piramide Azienda**. Struttura ispirata al modello "insurance advisor" (intro Studio, dati anagrafici, soggetti, analisi economica, indici, note legali + disclosure AI). Testato iter 80.
- **Sezione Immobili per aziende** (`ImmobiliSection.jsx` in Salute Fiscale): import Catasto + Geolocalizza + mappa Leaflet con **4 livelli** (Stradale/Satellite/Ibrida/Topografica), tasto **Mappa**. Opzione **"In affitto (preso in locazione)"** aggiunta al Titolo per privati e aziende. Campo **Piano** separato dall'indirizzo (split automatico all'import per non rompere il geocoding). Colori marker più visibili. `ImmobiliMap`/`ImmobileRow` resi export riutilizzabili.
- **Piramide**: tasto **Stampa** (`piramide-stampa-btn`) che apre finestra di stampa con gli stili applicati.
- **Tab Documenti ristrutturato**: sezione "Documenti per categoria" comprimibile con conteggio (`doc-cards-toggle`), ogni card comprimibile singolarmente (`doc-card-toggle-*`), sezione allegati integrata (rimossa Card/titolo duplicato, "Carica file" in alto), cartelle allegati comprimibili con conteggio. Testato iter 81 (100%, nessuna regressione).
- **Firma Privacy con eSignAnyWhere (Namirial)**: collegato il dialog Privacy & Consensi al flusso firma esistente (`POST /api/firma/richieste`) — pulsante `cons-firma-esign`. Richiede config eSign in azienda_config (presente in produzione, assente in preview → errore gestito).
- **Fix**: errore cancellazione voce Diario (conflitto di due route `DELETE /diario/{id}` → unificata con fallback su db.diario; duplicato spostato su `/diario-cliente/{id}`). Tab "Profilazione & GDPR" rinominato "**Privacy / GDPR**", rimossa sezione "Profilo aziendale".
- **Edit visivi PolizzaDetail/Sinistri**: Ultimo premio pagato nell'header blu; riga N.polizza sotto il prodotto; Sinistri lista senza link polizza; SinistroDetail con link polizza.
- ⏸️ **Rimandato dall'utente**: integrazione eSignAnyWhere con credenziali proprie (skippato "defaults for now").


## Sessione 08/09/2026 (fork) — Batch 4: FIX IMAP allegati, Piramide Azienda dati reali, Contratto PDF/Word

- **🔴 FIX P0 IMAP allegati mancanti (polizza 184643415)**: root cause reale — il modello `Allegato` richiede `content_type`/`size`, ma `imap_poller.py` costruiva `Allegato(...)` con i vecchi campi `mime`/`size_kb` → `ValidationError` ingoiata dal `try/except` → gli allegati non venivano MAI salvati. Corretto in `_copia_allegato_su_entita` e `_auto_allega_polizza` (ora `content_type=`, `size=`; `url` aggiunto come extra al dict). Aggiunto **backfill** `POST /api/email/poller/retry-allegati` (+ `retry_auto_allega` in imap_poller) che ri-processa gli allegati delle email GIÀ ingerite senza match (l'email era arrivata prima che la polizza esistesse; il re-polling salta le email già ingerite). Idempotente. Eseguito su Schiantarelli: con_match=49, allegati_polizza=37. Verificato: polizza 184643415 (bacebe55, tenant schiantarelli) ora ha l'allegato 'Contratto Active Veicoli AUTOCARRI 184643415.pdf'; la stessa polizza nell'altro tenant (31b4950e) NON è stata toccata (isolamento tenant OK).
- **🔴 Piramide Azienda popolata con dati REALI**: `prepopola_piramide_v2` (ramo persona_giuridica, server.py) ora legge da `salute_fiscale_dati.bilancio_estratto` + governance OpenAPI: Fatturato=valore produzione, Utile=utile netto reale, EBITDA=ebitda reale, N. dipendenti=dipendenti reali, N. soci=len(company.soci), Patrimonio netto. Fonte='salute_fiscale_azienda'. Prima erano stime derivate dal fatturato (r*0.5, r*0.8...). Sidebar `PiramidePrivati.jsx` (aziende): rinominata la 6ª voce da 'Perdita beni' a 'Patrimonio netto'. Verificato su AUTOTRASPORTI VIVIANI.
- **📄 Contratto di Consulenza PDF+Word ben impaginato**: nuovo modulo `contratto_render.py` (`build_pdf` ReportLab Platypus + `build_docx` python-docx). Impagina il campo `testo` come documento legale: header logo agenzia + ragione sociale/P.IVA/RUI, titolo centrato, premesse, articoli giustificati con 'Art. N (...)' in grassetto, blocco firme a 2 colonne, clausola approvazione ex art. 1341/1342 c.c., note legali + disclosure AI a piè pagina, numero pagina. Endpoint `GET /anagrafiche/{aid}/contratto-consulenza/pdf` e `/docx`. La firma OTP ora genera il PDF impaginato (non più `_pdf_da_testo` grezzo). UI: pulsanti 'Anteprima PDF' + 'Scarica Word' in `ContrattoConsulenzaTab.jsx` (con fallback download se popup bloccato). Base per futuri modelli PDF/gestione email avvisi.
- **Modifiche UI (agentic edit)**: PolizzaDetail — 'Ultimo premio pagato' spostato nell'header blu in alto a destra (rimosso dalla griglia bianca); riga 'N. polizza · Mandato' ingrandita (text-lg) e allineata a sinistra sotto il nome prodotto. Sinistri lista — colonna 'Contratto' non più link alla polizza (solo testo). SinistroDetail — riga 'Contratto' resa link cliccabile alla polizza (data-testid sinistro-polizza-link).
- Testato: iter 78 PASS 100% (backend 6/6, frontend 100%). Nessun issue critico.


## Sessione 08/09/2026 (fork) — Batch 3: Chat WhatsApp, Avatar, Documenti polizza da Drive

- **💬 Tab "Chat WhatsApp"** (scheda cliente): anteprima conversazione stile WhatsApp (bolle verdi in uscita a destra, bianche in entrata a sinistra), orari, nome mittente e foto/media caricati on-demand (`/whatsapp-evo/messages/{id}/media` come blob). Backend `GET /anagrafiche/{aid}/whatsapp-chat` (match sulle ultime 9 cifre del cellulare su `whatsapp_messages`). Testato: BALZAROLO ALESSIA 51 messaggi (28 out/23 in, 3 media). `WhatsAppChatPreview.jsx`.
- **Avatar auto-crop volto**: `face_crop.crop_volto_bytes` ora prova le rotazioni 0/90/180/270 (i documenti scansionati sono spesso ruotati) + validazione tono-pelle per evitare ritagli errati. Verificato sulla C.I. reale caricata dall'utente (volto ritagliato correttamente). Applicato anche all'upload manuale dell'avatar.
- **Documenti polizza da Google Drive**: pulsante "🔍 Cerca su Google Drive" nel tab Documenti della polizza → `POST /librerie/cloud-storage/cerca-documenti-polizza/{id}` cerca i PDF (fullText + nome) contenenti il numero polizza nella cartella collegata e li allega alla polizza (categoria "polizza", visibile_cliente). Batch `POST /cerca-documenti-tutte-polizze` abbina per numero-nel-nome su tutte le polizze del tenant (cap download). Riusa l'integrazione Drive OAuth esistente (`_fresh_access_token`, StorageService). Testato: auth Drive OK, ricerca eseguita. NB: la cartella collegata "Assicura CRM" è al momento SENZA PDF → 0 risultati finché non ci si caricano i file. La polizza 184643409 è in un tenant SENZA Drive collegato.
- **Import**: toast di fine importazione in ImportMassivo ora con conteggi (creati/aggiornati/saltati/errori).
- Testato: iter 76 PASS 100%.

### ⏳ In sospeso — serve input utente
- **Fonte IMAP** per i documenti polizza: da configurare (serve host IMAP + utente + password/app-password). Integrazione da fare via integration_expert una volta ricevute le credenziali.



## Sessione 08/09/2026 (fork) — Batch 2: Piramide tab, Documenti unificati, scenari, avatar

- **Tab "🔺 Piramide Azienda"** (persone giuridiche): nuovo tab dedicato (`tab-piramide-azienda`) con pulsante "Precompila da bilancio" che riempie la piramide coperture (modello aziende) dai dati di bilancio (valore produzione) + polizze attive. Backend `prepopola_piramide_v2` reso azienda-aware. `PiramideCopertureNuova` esportata. (Il pulsante resta anche dentro Salute Fiscale.)
- **Documenti unificati**: un solo tab "Documenti" con i documenti fissi del cliente in alto + sezione "Documenti raccolti" con cartelle per categoria (Visura Camerale/Catastale/Bilancio/…). Rimosso il tab "Altri allegati". Smistamento migliorato: file con "bilancio" nel nome finiscono nella cartella Bilancio anche se categoria=visura_camerale.
- **Andamento fatturato**: grafico a barre multi-anno (Recharts) nella card storico della Salute Fiscale.
- **Salva scenari per cliente**: pulsante "💾 Salva scenari" nel Margine di Contribuzione → salva rows/%/giorni/scenari/risk in `anagrafica.salute_fiscale_scenari` (via PUT /anagrafiche) e li ricarica all'apertura. Persistenza verificata.
- **Avatar auto-crop volto**: migliorato `face_crop._detect_face_opencv` con validazione tono-pelle (YCrCb) + minNeighbors=7 per eliminare i falsi positivi ("ritagliava zone non pertinenti"); se incerto NON ritaglia (fallback icona). Il crop volto ora si applica anche all'upload manuale dell'avatar (se trova un volto sicuro). NON testato via UI (euristica backend).
- Testato: iter 75 PASS 100% (Piramide tab, unificazione Documenti, grafico fatturato, salva scenari, smistamento Bilancio).

### ⏳ In sospeso
- "Anteprima chat": scelta modalità (riga/bolle/pulsante dedicato) ancora da definire.



## Sessione 08/09/2026 (fork) — Cruscotto Salute Fiscale azienda + rifiniture

### ✅ Salute Fiscale unificata (fusa con Analisi Azienda) — tab-salute-fiscale
- Rimosso il tab separato "Analisi Azienda"; ora `SaluteFiscaleTab` renderizza in cima la Panoramica azienda + Soci/Governance/Forza lavoro (AnalisiAziendaTab) e sotto i blocchi finanziari.
- Conto economico dettagliato + Stato patrimoniale + Storico bilanci + Indicatori (già in sessione precedente).
- **Margine di Contribuzione** (`sf-mdc-card`): auto-import dal bilancio OpenAPI. Formula verificata sul PDF ufficiale VIVIANI: MDC 2025 = 3.830.606,90 € (Ricavi di vendita = Valore produzione IIC130 6.889.188; Rimanenze finali = rimanenze totali IIC045 42.000; % non assicurata default Servizi 70% / Amministrativi 30%). Voci e % editabili, ricalcolo live.
- **Metriche di impatto** (`sf-impatto-card`): MDC giornaliero × giorni scenario; scenari Trascurabile/Gestibile/Grave/Critico con giorni configurabili (default 20/58/115/189); Risk Tolerance/Appetite configurabili; grafico a barre Recharts.
- **Studio di bilancio** (`sf-studio-card`): Ciclo circolante, MOL/OF, Val.agg/immobilizzi, Ricavi/crediti — barra colorata con marker STATICO (l'utente ha chiesto NON modificabile). + "Altri indici utili": Margine di tesoreria e Indice di disponibilità.
- **🔺 Piramide Azienda** (`sf-piramide-btn`): apre la Piramide delle Coperture (modello "aziende") e la precompila con i dati di bilancio (endpoint `POST /anagrafiche/{id}/analisi/piramide-v2/prepopola` reso azienda-aware: base = valore produzione/fatturato). `PiramideCopertureNuova` ora esportata da AnalisiClienteTab.
- Backend `company_financials()` in openapi_it_service arricchito (rimanenze, crediti clienti, debiti fornitori/breve, immobilizzazioni, attivo circolante). Endpoint `salute-fiscale/da-openapi` corregge PN vs perdita e ritorna ~30 voci.

### ✅ Governance & rifiniture
- Campi Amministratore/Referente azienda (+ email/telefono) con "Compila da OpenAPI" (`POST /openapi-it/governance/{aid}`) — auto-fill legale rappresentante.
- Traduzioni IT (`_trad_it`): ruoli governance, dimensione impresa; descrizione ATECO ora in italiano (usa campo RAE); forma giuridica IT.
- IBAN salvato nei Conti Correnti riportato nel campo IBAN Anagrafica (sync in save + fallback in visualizzazione).
- Tab Polizze mostra solo le ATTIVE con toggle "Mostra tutte"; conteggio tab = attive.
- Documenti allegati raggruppati in CARTELLE per categoria (Visura Camerale/Catastale/Bilancio/…) — `AllegatiCartella` collassabili.
- Conferma AlertDialog prima di ogni download OpenAPI (tutti i pulsanti). Rimosso il pulsante "Visura" singolo da OpenApiActions.
- Testato: iter 71/72/73/74 tutti PASS 100%.

### ⏳ In sospeso (richiesta utente in pausa)
- "Anteprima chat" nel Diario/anagrafica: da chiarire l'opzione desiderata (a/b/c) prima di implementare.



## Sessione 08/09/2026 (fork) — Salute Fiscale ricca da OpenAPI + Conferma download OpenAPI

### ✅ Salute Fiscale (P0) — dati "più corposi" e KPI corretti da company.openapi.com
- Nuova funzione `openapi_it_service.company_financials(cf_piva)`: legge company.openapi.com **IT-full** e ricostruisce il conto economico dettagliato dalle voci codificate IIC/IPL (subset productionValue/productionCosts/revenuesFinancialCharges/annualResult/incomeStatementAggregateValues + assetsAggregateValues/liabilitiesAggregateValues/netWorth/debts). Aggiunge `operatingResults` (EBITDA/EBIT/cash flow), `ecofin` (netWorth reale, turnover, trend), `employees`, tutti gli indici ufficiali (redditività, liquidità, leva, kpi, struttura, indebitamento, copertura) e lo **storico fatturato** (IT-advanced balanceSheets.all, ultimi 6 anni).
- `POST /anagrafiche/{aid}/salute-fiscale/da-openapi` (routes/extras_p1p2.py) riscritto: bilancio_estratto ora contiene ~24 voci (Ricavi, Valore produzione, Costi produzione/materie/servizi/godimento beni/personale, Ammortamenti, Oneri diversi, EBITDA/EBIT, Proventi/Oneri finanziari, Utile lordo, Imposte, Utile netto, Cash flow, Totale attivo/debiti, PN, Capitale sociale, dipendenti, trend). **BUG CORRETTO**: prima metteva come patrimonio_netto la perdita d'esercizio (-8.052) e ricostruiva l'utile da ROE; ora PN=451.553 (IIC084/ecofin) e utile netto=IIC179 reale. Indicatori estesi: ROE/ROI/ROS, EBITDA margin, Leva (Att/PN), PFN/EBITDA, Oneri fin./Ricavi, Pressione fiscale, Incidenza personale. Verificato via curl su AUTOTRASPORTI VIVIANI (00920050143, LIVE).
- Frontend `SaluteFiscaleTab.jsx`: al click di "⚡ Compila da OpenAPI" ora fa `setDati(r.data)` immediato (UI si aggiorna all'istante, niente più "non aggiorna"); rendering arricchito con sezioni Conto economico + Stato patrimoniale + Storico bilanci (`sf-storico-card`) + Indicatori. Testato e2e (iter 71): score 7, nessun campo vuoto.

### ✅ Conferma download OpenAPI (richiesta agentic-edit) — `OpenApiActions.jsx`
- Prima di scaricare/aprire QUALSIASI servizio OpenAPI (tutti e 5 i pulsanti: Camerale, Catasto, Veicoli, Visure & Doc., Visura) compare un **AlertDialog** (`openapi-confirm-dialog`) "Scaricare i dati da OpenAPI.it?" con avviso consumo credito + bottoni Annulla (`openapi-confirm-cancel`) / Scarica (`openapi-confirm-ok`). Helper `guard(label, fn)`. Testato e2e (iter 71) su persona fisica: dialog compare su tutti i 5, Annulla chiude senza chiamata.
- NB: `OpenApiActions` è renderizzato nel tab "Dati" per le persone fisiche e nel tab "Analisi Azienda" (AnalisiAziendaTab.jsx) per le persone giuridiche — il gate a riga 211 di AnagraficaDetail.jsx è INTENZIONALE (evita duplicati), NON un bug.



## Sessione 02/09/2026 (fork) — parte 6: Biblioteca Centralizzata (globale) + note Veicolo

### ✅ Biblioteca Centralizzata (opzione A — libreria unica globale)
- `database.py` (TenantAwareCollection): `schede_calcolo` e `biblioteca_jobs` sono ora FULLY_SHARED (una sola libreria globale, tenant `__global_library__`). `biblioteca_previdenza` e `_cartelle` sono MIXED: lettura = tenant corrente OPPURE globale (così le agenzie vedono le proprie Condizioni + la Previdenza globale); super-admin (senza tenant) → solo globale.
- `biblioteca_previdenza.py`: gli upload/cartelle/delete della sezione **previdenza** sono consentiti SOLO al super-admin (403 per le agenzie); gli insert previdenza vanno su tenant globale. Le agenzie leggono (per i calcoli INPS/pensione via RAG/AI) ma non gestiscono.
- Frontend: le agenzie NON vedono i tab Previdenza/Schede (già nascosti). Super-admin: nuovo link "Biblioteca" → `/super-admin/biblioteca` (pagina con Previdenza + Schede + gestione). 
- Verificato via API: super-admin carica previdenza (cartella INPS) → l'agenzia TEST la legge; upload previdenza da agenzia → HTTP 403.

### ℹ️ Veicolo in polizza (già presente)
- Il tab "Veicolo" nel form di Modifica polizza usa già `TargaSearchWithLentina`: si digita la targa (editabile), ricerca live in archivio; se manca → "Crea nuova targa" con dati manuali + upload libretto. Nessuna modifica necessaria.



## Sessione 02/09/2026 (fork) — parte 5: Auto-quietanza + Promemoria upload

### ✅ Data prima quietanza calcolata automaticamente (Polizze.jsx)
- Nel modale nuova polizza la "Data prima quietanza" si compila da sola = effetto + periodo del frazionamento (annuale +12m, semestrale +6m, quadrimestrale +4m, trimestrale +3m, mensile +1m). Resta modificabile a mano (se toccata non viene più ricalcolata). Helper `addPeriodo`.

### ✅ Promemoria Upload documenti (scheduler_alert.py + upload_link.py)
- I link documento non ancora caricati vengono ri-sollecitati automaticamente ogni `reminder_giorni` (default 3, impostabile alla creazione), max 3 solleciti, sul canale scelto dal cliente in anagrafica (email/whatsapp/sms). Job cron 07:00. Riusa i sender di alert_dispatcher (CHANNEL_ADAPTERS). Smoke test OK (invio saltato in TEST perché provider non configurato, nessun crash).

### ⏳ Biblioteca Centralizzata (#2) — NON ancora implementata: serve scelta di approccio
- Le sezioni Previdenza + Schede sono lette dalla knowledge base AI (notebooklm RAG, ai_copilot schede). Renderle globali richiede una scelta:
  - A) **Libreria globale condivisa** (una sola copia; super-admin scrive, tutte le agenzie leggono la stessa): modifica dell'isolamento per previdenza/schede + adeguamento dei percorsi di lettura AI. Più pulito ma tocca l'isolamento.
  - B) **Propagazione a copie**: super-admin gestisce una libreria master e un pulsante "Propaga" copia i documenti su tutte le agenzie. Sicuro, nessun cambio isolamento, ma va ri-propagato ad ogni modifica.



## Sessione 02/09/2026 (fork) — parte 4: Categorie documenti + Modifica premi rapida

### ✅ Categorie documenti polizza (PolizzaDetail → DocumentiSezioneSplit)
- Visibili al cliente: Polizza, Condizioni, **Appendici** (nuova), **Libretto veicolo** (rinominata da "Libretto pagam."), Atto di vendita, **Quietanze** (documenti di pagamento rilasciati al cliente).
- NON visibili (interni): Preventivi, Appunti, **Documenti altri (foto)** (nuova).
- Multi-file per categoria: il selettore accetta più file in una volta (`multiple`), upload in ciclo. Testato: 2 appendici caricate (visibile_cliente=true).

### ✅ Modifica Premi Rapida (Polizze.jsx + PolizzaDetail.jsx)
- Dopo la creazione (snella) la polizza si apre in dettaglio con `?edit=1` → si apre automaticamente il dialog di modifica per inserire subito premi/provvigioni/veicolo.

### 🔜 Backlog rimanente
- Biblioteca Centralizzata (super-admin globale) — vedi nota parte 3.
- Promemoria Upload: rinvio automatico del link documento se il cliente non carica entro X giorni.
- Report Provvigioni: vista riepilogo totali agenzia / quote collaboratori / margine per periodo.



## Sessione 02/09/2026 (fork) — parte 3: Auto-diario, Link upload, Condizioni 2 livelli, Creazione polizza snella

### ✅ Auto-diario WhatsApp (dedup) — `whatsapp_evo.py` + `scheduler_alert.py`
- Salvataggio conversazione reso idempotente (UPSERT per `whatsapp_conv_key = instance:number`): niente doppioni.
- Job giornaliero 06:30 multi-tenant che salva/aggiorna nel diario le conversazioni collegate a un'anagrafica. Endpoint manuale `POST /api/whatsapp-evo/auto-diario/run`. Testato: 2 run → 1 sola voce.
- FIX Diario "Apri": aggiunto dialog `diario-voce-dialog` (prima non si apriva nulla).

### ✅ Link Upload Documenti — `routes/upload_link.py` + `pages/CaricaDocumento.jsx`
- `POST /api/upload-links` crea link sicuro (token) per un'anagrafica; pubblici (no auth): `GET/POST /api/public/upload/{token}`. Il file caricato dal cliente finisce negli allegati dell'anagrafica (tenant risolto dal token). Testato e2e.
- Placeholder `{link_carica_documenti}` negli alert: genera il link al volo per il cliente destinatario.
- UI: pagina pubblica `/carica/:token` + box "Richiedi documento" nel tab Documenti anagrafica (copia link + invia WhatsApp).

### ✅ Condizioni di Polizza a 2 livelli (compagnia → ramo) — `biblioteca_previdenza.py` + `BibliotecaPrevidenza.jsx`
- Nuovo campo `sottocartella` (ramo) + endpoint `GET /sottocartelle`. Upload accetta compagnia+ramo. UI condizioni: naviga compagnia → riga rami → documenti filtrati. Testato via API.

### ✅ Creazione polizza SNELLA — `Polizze.jsx`
- Il modale "Nuova polizza" ora chiede solo i dati base (numero, stato, compagnia, contraente, ramo/prodotto, effetto/scadenza) + **Frazionamento**, **Data prima quietanza**, **Collaboratore**. Premi/provvigioni/veicolo rimossi dal modale (nota informativa): si inseriscono/modificano nella scheda polizza (tab Modifica → premi header, Veicolo con TargaSearch, Provvigioni). Testato: creazione ok.

### ✅ Provvigioni terminologia (PolizzaDetail)
- Rimosso il doppione "Provv. struttura rata" (uguale a totali). Ora: **Provv. totali (agenzia)**, **Provv. collaboratore**, **Provv. margine (agenzia netto) = totali − collaboratore**. Editor: label "Provv. totali rata (agenzia)".

### ⏳ Ancora da fare (concordato)
- **Biblioteca Centralizzata (super-admin globale)**: spostare Previdenza+Schede nella console super-admin con dati GLOBALI propagati a tutte le agenzie. NON ancora implementato: richiede rendere globali (fuori tenant) le sezioni previdenza/schede toccando anche i percorsi di lettura AI (RAG, calcolo pensione) — va fatto con attenzione per non rompere l'isolamento delle condizioni (che restano per-agenzia). Da affrontare in un passo dedicato.



## Sessione 02/09/2026 (fork) — parte 2: Tasks, Duplica regole, Preset pagamento, Fix tabelle, Archivio chat, Diario

### ✅ Modulo TASK (stile Google Tasks) — `routes/tasks.py` + `pages/Tasks.jsx`
- Bacheca a colonne per operatore. **Isolamento**: di default ognuno vede SOLO le proprie attività + quelle condivise con lui; l'ADMIN ha una checkbox "Vedi tutti gli operatori" (scelta esplicita, default OFF).
- Condivisione con 1+ operatori, allegati documenti (object storage), priorità, scadenza, completamento, "Mostra completate", STAMPA (window.print con CSS print-friendly).
- Endpoint `/api/tasks` (GET con `?tutti=true` solo admin), POST/PUT/DELETE, `/toggle`, `/allegati` (upload/download/delete), `/operatori`. Collection `tasks` tenant-scoped.
- Rotta `/tasks` + voce menu "Attività (Tasks)" (sezione Strumenti). Verificato e2e (iter 64/65).

### ✅ Alert & Automazioni: Duplica + Preset pagamento
- `POST /api/alert-rules/{id}/duplica`: copia una regola (attivo=false, "(copia)") per modificarla senza rifarla. Pulsante "Duplica" in UI.
- Nuovi preset evento `titolo.incassato`: "Ringraziamento pagamento polizza" e "Questionario di soddisfazione". Dispatch `titolo.incassato` cablato nell'endpoint incasso (`server.py`). Quando il cliente paga parte il messaggio (sul canale scelto in anagrafica).
- Chiarito: l'esecutore avvisi programmati (parte 1) È la parte automatica di Alert & Automazioni (nessun doppione); la card orario vive in /alert.

### ✅ FIX BUG TABELLE (colonne congelate sovrapposte) — `index.css`
- Le colonne sticky (`.freeze-1/2/3`) avevano solo `max-width` → larghezza reale non coincideva con gli offset `left` → sovrapposizione con la colonna adiacente (illeggibile). Ora larghezza FISSA (`width`+`min-width`+`max-width` = var --cN-w), come già faceva `freeze-5`. Verificato su Contabilità con 500+ movimenti (desktop+tablet, scroll orizzontale): nessuna sovrapposizione. Vale per TUTTE le tabelle del programma.

### ✅ Archivio chat WhatsApp — `whatsapp_evo.py` + `Chat.jsx`
- Pulsante "Archivia/Ripristina" sulla conversazione + toggle "Archiviate" nella lista (non intasa le conversazioni in arrivo). Registra e mostra il TAG "Archiviata da {nome}" (chi ha archiviato). Backend `meta` salva `archived_by_name`.

### ✅ FIX Diario "Apri" — `AnagraficaDetail.jsx`
- Cliccando "👁 Apri" su una voce di diario (es. conversazione salvata) lo stato `viewVoce` veniva impostato ma NESSUN dialog lo renderizzava → non si apriva nulla. Aggiunto il dialog `diario-voce-dialog` che mostra il contenuto completo. Verificato e2e.

### ✅ Tag anagrafiche + Biblioteca visibilità (parte 1, già fatte)

### 🔜 Backlog concordato (da discutere al "punto della situazione")
- **Auto-salvataggio conversazione WhatsApp nel diario cliente** (con dedup per evitare doppioni). Oggi è manuale ("Salva nel diario").
- **Link pubblico upload documenti**: quando un alert chiede al cliente un documento mancante/scaduto (libretto ecc.), il cliente lo allega via link sicuro e lo ritroviamo nel gestionale sul cliente/polizza.
- **Biblioteca super-admin globale** (Previdenza + Schede propagate a tutte le agenzie; dati oggi tenant-scoped).
- **Condizioni di Polizza per compagnia → ramo** (navigazione a cartelle a due livelli).



## Sessione 02/09/2026 (fork) — Avvisi programmati + Import Excel estratto conto + Tag KPI + Biblioteca visibilità

### ✅ P0 — Esecutore AVVISI PROGRAMMATI (schedule/soglia) — nuovo `scheduler_alert.py`
- Prima le regole `tipo=schedule/soglia` (compleanno, polizza scaduta 0/5/10/14/15gg, polizza in scadenza, titolo scaduto oltre soglia) NON venivano mai eseguite: mancava il loop giornaliero.
- Nuovo tick ogni 10 min multi-tenant: per ogni tenant legge orario configurabile (`azienda_config.alert_scheduler_hour/minute/attivo`, default 08:00) e, all'ora impostata, esegue le regole (una sola volta al giorno via `alert_scheduler_state`).
- **Canale in base alla scelta del cliente in anagrafica**: `alert_dispatcher._dest_cliente` espone `canali_cliente` (da flag `canale_email/whatsapp/sms`); `dispatch_rule` filtra i canali per il destinatario cliente (inapp sempre).
- Rotte: `GET/PUT /api/alert-scheduler/config` (orario), `POST /api/alert-rules/{id}/run-now` (esecuzione immediata).
- Frontend `Alert.jsx`: card "Avvisi programmati" con ora:minuti + toggle attivo + Salva; pulsante "Esegui ora" per regole schedule/soglia.
- **Testato e2e** sull'agenzia TEST: polizza scaduta da 5gg → regola trova 1 entità, canale email ESCLUSO (cliente ha scelto solo WhatsApp), inapp ok.

### ✅ P0 — Import Massivo: Excel ESTRATTI CONTO COMPAGNIA → MovimentoContabile
- `_read_df` ora rileva la riga di intestazione reale saltando le righe di preambolo (Excel export con 6 righe vuote). Vale per CSV ed Excel.
- Nuovi campi movimento: `compagnia_nome` (Mandato), `numero_estratto`, `data_estratto`. Entity detection → movimento.
- Ramo movimento: estratto conto compagnia = VERSAMENTO → tipo `uscita`, categoria `pagamento_compagnia`, descrizione "Versamento compagnia — {mandato} · Estratto n. {n}", compagnia_id risolto.
- **BUG FIX**: importo con separatore decimale "." (2897.03) veniva moltiplicato x100 → aggiunto `importo` a `_NUM_FIELDS` (usa `_to_float`).
- **Testato e2e**: 596 movimenti importati, 0 errori, importi corretti (2897.03, 317.71…).

### ✅ Provvigioni su premio netto (Librerie → Sistema provvigionale)
- Input `% premio netto` già presente nel form; aggiunta colonna "% Netto" nella lista + default. Logica backend `_calcola_provvigione` già usa `percentuale_su_premio_netto` + piramide (100€→50%→10%).

### ✅ Tag anagrafiche: suggerimento canonico + KPI robuste
- `GET /anagrafiche/tags` include sempre i tag canonici `condominio/parrocchia/azienda` (autocomplete propone anche in agenzie nuove → niente doppioni CONDOMINI/CONDOMINIO). TagsEditor normalizza già a minuscolo.
- KPI `/anagrafiche/stats` ora confronta i tag case-insensitive. Testato: creata anagrafica CONDOMINIO → KPI condomini +1.

### ✅ Biblioteca: visibilità
- `BibliotecaPrevidenza.jsx`: tab "Biblioteca Previdenza" e "Schede di Calcolo" ora `superAdminOnly` (nascosti alle agenzie). Le agenzie vedono SOLO "Condizioni di Polizza". Default tab agenzia = condizioni.

### 🔜 Prossimi task richiesti dall'utente (da costruire)
- **Modulo TASK stile Google Tasks** (P0): bacheca per operatore (ognuno vede il suo), condivisione task con 1+ operatori, allegati documenti, STAMPA. Nuovo modulo (collection `tasks`, CRUD, sharing, object storage, print view, board UI).
- **Biblioteca super-admin globale** (P1): gestione centralizzata di Biblioteca Previdenza + Schede di Calcolo nella console super-admin con propagazione a tutte le agenzie (richiede rendere GLOBALI i dati sezione previdenza/schede, oggi tenant-scoped) + Condizioni per compagnia→ramo.



## Sessione 12/02/2026 — VERIFICA UFFICIALE PARAMETRI INPS + PIRAMIDE COMPATTA + JOB ASYNC SCHEDE + IMAP AUTO-ALLEGA

### 🔴 P0 — Parametri INPS 2025-2026 VERIFICATI E CORRETTI su fonti ufficiali
**Discrepanze critiche rilevate e sistemate in `/app/backend/inps_calculator.py`:**
- **Coefficienti di trasformazione**: erano OBSOLETI (biennio 2023-2024). Aggiornati con DM 20/11/2024 (biennio 2025-2026, in vigore fino al 31/12/2026). Esempi: 57→4,204%; 67→5,608%; 71→6,510%.
- **Tassi di rivalutazione montante**: 12 di 16 anni erano ERRATI o con segno invertito. Aggiornati con Note ISTAT ufficiali (ministero lavoro). Esempi corretti: 2021=-0,02%, 2022=+0,997%, 2023=+2,31%, 2025=+4,04%.
- **Invalidità civile 2026**: aggiornato da 333,33 (2025) → 340,71 €/mese.
- **Aggiunti**: `trattamento_minimo_2026` (611,85€), Tabella F L.335/1995 (riduzioni reversibilità 0/25/40/50%), aliquote contributive 2026 (dipendenti 33%, gestione separata 26,07%, artigiani 24%, commercianti 24,48%), funzione `riduzione_reversibilita_per_reddito` con eccezione figli minori (Corte Cost. 162/2022).
- **Test pytest**: `/app/backend/tests/test_inps_calculator_v2.py` — 26/26 PASS su tutti i parametri ufficiali.
- **Fonte AI**: `_crm_params_summary()` in biblioteca_previdenza.py aggiornato per riportare all'AI i nuovi parametri e la data di verifica.

### 🔴 P0 — Piramide delle Coperture: fix UX + layout stampabile A4
- **Bug fix**: pulsante "+", input reddito, pallini stato ora funzionano in modalità agenzia (canEdit propagato correttamente).
- **🐛 BUG CRITICO risolto (fix successivo)**: i cunei laterali (INVESTIMENTO/RISPARMIO/PROTEZIONE), pur avendo `clip-path` che li rende visualmente triangolari, geometricamente sono div rettangolari che coprivano metà destra del triangolo — intercettavano tutti i click a destra (pallini, input, tasto +). Aggiunto `pointer-events: none` ai wedge (decorativi puri).
- **🐛 BUG DEFINITIVO risolto (refactor strutturale)**: nonostante il fix wedge, il triangolo padre con `clip-path` bloccava ancora eventi mouse in alcuni casi. Ristrutturato in **4 layer**:
  1. LAYER 1 (bg triangolo bianco clippato) — `pointer-events: none` — solo `LevelBackground` (strip colorate decorative)
  2. LAYER 2 (SVG contorno) — `pointer-events: none`
  3. LAYER 3 (wedge cunei laterali) — `pointer-events: none`
  4. LAYER 4 (z-20, SENZA clip) — `LevelForeground`: input, pallini, tasto "+", pulsanti custom → click SEMPRE funzionanti indipendentemente dal clip-path
  Verificato E2E: click + → nuova voce, click pallino → cambia colore verde/giallo/rosso, input → scrive 500.000 €.
- **Sidebar dati_reddito**: spostata sopra il triangolo in griglia orizzontale 4 colonne (era absolute overlay sinistro, occupava spazio triangolo).
- **Cunei laterali**: font ridotto a 9px, padding minimizzato.
- **Auto-populate GET piramide-v2**: se `dati_reddito` è vuoto, backend lo popola da `reddito_annuo_lordo` anagrafica + `estratti_conto_inps` presenti.
- **Nuovo endpoint `POST /piramide-v2/prepopola`**: calcola valori suggeriti da estratto INPS/reddito (reddito_invalidita_66_99=50%, reddito_inabilita_100=80%, reddito_superstiti=60%). Bottone verde "⚡ Prepopola dati" nella sidebar della piramide.

### 🔴 P0 — Schede di Calcolo AI: fix JSON parse + BACKGROUND JOB
- **Fix errore `Expecting value: line 1 column 1`**: nuova funzione `_parse_json_ai()` con multiple fallback (rimuove markdown fence ```json, estrae il primo blocco `{…}` valido, fallback a `_ai_raw_unparsed`).
- **Spostato in background job** (`biblioteca_jobs` collection già esistente): `POST /schede-calcolo/genera` ora ritorna immediatamente `{job_id}` — il frontend polla `GET /jobs/{jid}` ogni 2s fino a `stato=done`. Elimina timeout del proxy sulle chiamate AI (Claude ~90-110s reali).
- **Confronto AI schede annuali** invariato: `_confronto_scheda` distingue vere modifiche normative da riformulazioni testuali.

### 🟡 P0 — IMAP Poller: auto-collega polizze firmate
- `_candidati_numeri_polizza`: regex robusta per estrarre numeri polizza da oggetto/body/nome file (formato compagnie italiane).
- `_auto_allega_polizza`: se mittente email = anagrafica cliente + numero polizza nel testo → copia PDF in `polizze/{id}/firmata_email_...pdf`, crea record `Allegato` (entita_tipo=polizza, fonte=email_imap, visibile_cliente=false, categoria=polizza_firmata). Match SICURO: filtra su `contraente_id` per evitare falsi positivi.
- Log nel diario cliente: `"📎 auto-collegata a polizza {numero}"`.

### 🟢 P1 — Ricerca Web Condizioni di Polizza (nuovo)
- **Endpoint `POST /biblioteca-previdenza/cerca-condizioni`** (manuale, singola compagnia): AI (Claude) suggerisce fino a 5 URL PDF condizioni, il backend scarica + valida (min 3 parole-chiave assicurative + magic-bytes PDF + dedup). AI istruito a NON inventare URL se non ne conosce di affidabili.
- **Endpoint `POST /cerca-condizioni-bulk`** (job async): itera su tutte le compagnie del CRM (solo_mancanti=true), rate-limit 1s tra chiamate LLM.
- **UI Biblioteca > tab Condizioni di Polizza**: 2 nuovi bottoni "Cerca dal Web (manuale)" + "Cerca dal Web (bulk)" con dialog + progress live del job.

### 🎯 Testing report (iter 55)
- 35/35 test PASS (100% backend); nessun issue critico; testing agent skipped frontend come richiesto.
- Cleanup dati test su Marco Rossi (testamento, voci_custom TEST) eseguito.

---

### 🎯 Piramide delle Coperture — implementata come vera piramide 3D
- **Layout definitivo**: SVG polygon triangolo esterno + bande stepped con `width%` decrescente dal basso all'apice
- Widths: `[100, 92, 82, 72, 62, 52, 40, 22]` con `min-heights` per livelli vuoti
- Titolo banda + sfondo colorato + voci con input + pallino stato
- Zone label DX (Investimento/Risparmio/Protezione Patrimonio/Protezione Reddito) come piramide di gradini dentro il container
- Formato numeri: `1.000.000 €` (toLocaleString it-IT)
- Header con solo logo agenzia (rimosso cerchio Futuro Senza Sorprese)
- Legenda 🟢🟡🔴 + Footer Testamento + 4 Eredi legittimi
- Componente unico riusabile `PiramidePrivati.jsx` (editabile in agenzia + read-only nel portale cliente)

### ✅ Verificato end-to-end
Screenshot cliente Jacopo: piramide renderizzata perfettamente con 8 livelli, contorno diagonale visibile, tutti i testi leggibili, zone label allineate.

## 🎯 TASK PROSSIMA SESSIONE (richiesti da utente)

### 1. CTA "Analisi Personalizzata" nel portale cliente
- Sezione dedicata in `PortaleCliente.jsx` (nuovo tab o inline nella piramide)
- Testo motivazionale: "Vuoi un'analisi personalizzata? Contattaci"
- **Upload PDF Estratto Conto Contributivo** (INPS) direttamente dall'app cliente
  - Endpoint POST già esistente in software agenzia (Archivio INPS)
  - Aggiungere l'accesso client-side + salvare `owner_type=cliente`
- **Video motivazionale**: 
  - Nuovo campo `agenzia_config.video_analisi_url` (upload MP4 o URL YouTube)
  - Player embed nella sezione CTA lato cliente
  - Pannello agenzia per caricare/aggiornare il video

### 2. Sezione "Estratti INPS caricati dai clienti"
- Nel software agenzia in `AnalisiClienteTab` → Archivio Estratto Conto INPS
- Mostrare badge "caricato dal cliente" per PDF caricati via portale
- Notifica dashboard quando un cliente carica un nuovo estratto

### 3. Toggle Notifiche Piramide Mensili (Impostazioni)
- Aggiungere in `Impostazioni.jsx` un pannello "Notifiche automatiche clienti"
- Toggle ON/OFF: "Invia mensilmente al cliente riepilogo copertura"
- Se ON: cron job mensile invia email con "La tua protezione è al X%" + link portale
- Salvato in `agenzia_config.notifiche_piramide_attive`

### 4. Piramide Aziende
- Variante per `Anagrafica.tipo == "persona_giuridica"`
- 7-8 livelli: RC veicoli/terzi/dipendenti/prodotti/ambientale/amministratori/datoriale → Uomini chiave → Liquidità+TFM → Patrimonio netto
- Nuovo componente `PiramideAziende.jsx` gemello a `PiramidePrivati.jsx`

### 5. PDF Export Piramide
- Endpoint `/anagrafiche/{aid}/analisi/piramide-v2/pdf` con weasyprint
- Layout identico allo screenshot Schiantarelli originale
- QR code sul PDF che apre il portale cliente sulla piramide interattiva
- Bottone "Stampa" e "Invia via email" in AnalisiClienteTab

## Sessione 11/02/2026 (fork) — Import fixes + Piramide preparazione

### 🎯 Piramide delle Coperture (schema Schiantarelli) — implementata pixel-perfect
- **Componente riusabile** `/app/frontend/src/components/PiramidePrivati.jsx` (~400 righe)
  - 8 bande dal basso all'apice: Invalidità → Premorienza → Danni Ad Altri → Perdita Beni → Liquidità → Cassa Lievi → Cassa Grandi → Crescita Capitale
  - Header logo agenzia + "Futuro Senza Sorprese"
  - Legenda 🟢 ADEGUATO / 🟡 NON ADEGUATO / 🔴 ASSENTE
  - Sidebar sinistra con 7 campi dati reddito editabili
  - Footer: Testamento (Sì/No) + 4 caselle Eredi legittimi
  - Modalità editabile (agenzia) o read-only (cliente) via prop `onSave`
  - CTA "richiedi preventivo" sui pallini rossi/gialli
- **Backend** `server.py`:
  - `GET /api/anagrafiche/{aid}/analisi/piramide-v2` — ritorna voci auto-popolate + dati salvati
  - `PUT /api/anagrafiche/{aid}/analisi/piramide-v2` — salva reddito/testamento/eredi/override
  - Helper `_piramide_v2_calcola_voci` legge polizze attive, aggrega per categoria via matcher (keyword per ramo/prodotto/garanzia), calcola stato in base a soglie configurabili (`_PIRAMIDE_V2_SOGLIE`)
- **Backend** `portale_cliente.py`:
  - `GET /api/portale/protezione` — versione read-only per il cliente (stesso schema)
  - `POST /api/portale/protezione/richiedi-preventivo` — crea richiesta admin + msg chat
- **Integrazione UI**:
  - Portale cliente: nuova sezione "La mia protezione" in `PortaleCliente.jsx` (menu con icona Shield, gradient fucsia-rosa)
  - Software agenzia: nuovo componente `PiramideCopertureNuova` nel sub-tab "Piramide" in `AnalisiClienteTab.jsx`. La piramide legacy resta accessibile in collapsible "details"
- **Test end-to-end verificato**: 
  - Portale cliente (screenshot): piramide renderizzata identica allo schema Schiantarelli con 8 livelli, 11 pallini, tutte le voci correttamente popolate
  - Backend restituisce 3 polizze RCA di Jacopo per la voce `danni_veicoli` con stato "assente" (capitale 0 in DB → pallino rosso corretto)

## Sessione 11/02/2026 (fork) — Import fixes + Piramide preparazione

### 🔴 Bug fix critici P0
1. **Duplicati in `import_mappings`** (75 righe orfane): dedup effettuato + fix preventivo nell'endpoint POST `/api/import/mappings` (delete_many extras prima dell'upsert)
2. **Import ANIA non associava operatori alle polizze/titoli**: campo giusto era `collaboratore_1` (non `cod_operatore`). Fix in `_resolve_operatore_codice` (ania_importer.py) + esteso `_processa_titoli` per estrarre collaboratore da rec40 o ereditarlo dalla polizza.
3. **Anagrafiche non ricevevano collaboratore_id**: aggiunto back-fill in `_processa_polizze` (setta collaboratore su anagrafica se assente) e nel `/api/import/mappings/apply` (back-fill retroattivo anagrafiche + titoli).
4. **AnagraficaDetail lint fix** (`InlineEditField`/`InlineChannelsField` non definiti, componenti nested instabili)
5. **PolizzaDetail bug** `ContraenteFilter is not defined` → import mancante ripristinato
6. **PolizzaDetail** tab default = `garanzie` (per polizze non-RCA) + totale colonna Massimali/Capitali rimosso + fallback intelligente per RCA (usa `pol.massimali` se garanzia vuota)

### ✅ Wizard Mapping Entità — semplificato
- **Tab Garanzia rimossa**: garanzie auto-create in libreria durante import
- **Tab Prodotto**: sceglie solo il Ramo, prodotto viene auto-creato in libreria con nome del flusso + `auto_created=True`
- **Tab Operatore/Collaboratore**: auto-crea utenti stub (attivo=false, password disabilitata) per codici mai visti; badge giallo "AUTO-CREATO" in wizard; utente completa in Librerie → Utenti
- **Auto-suggerisci Ramo** dai keyword del nome prodotto (AUTOPIU'→Auto, ABITAZIONE→Casa, VITA/TCM→Vita, IMPRESA→Multirischio, ecc.) — pre-selezione sfondo azzurro

### ✅ Bulk Rename Prodotti
- Endpoint `POST /librerie/prodotti/bulk-rename` (idempotente, dedup nome)
- Dialog in Librerie → Prodotti → pulsante "Rinomina in massa" con filtri (auto-creati / tutti) + ricerca

### ✅ Endpoint Piramide Base (portale cliente) — draft
- `GET /api/portale/protezione` con 6 livelli semplici (RCA/Casa/Vita&Salute/Impresa/Previdenza/Tutela Legale)
- `POST /api/portale/protezione/richiedi-preventivo` (crea richiesta admin + messaggio chat)
- **NB**: da riprogettare secondo il modello richiesto (vedi sotto).

## 🎯 TASK PRIORITARIO PROSSIMA SESSIONE — Piramide Coperture Ricca

### Design PIRAMIDE PRIVATI (esattamente come screenshot utente Schiantarelli)

SVG triangolo con 8 bande dal basso (rossa larga) all'alto (verde acqua stretta).
Header: Logo "Futuro Senza Sorprese" (sx) + Logo Assicurazioni Schiantarelli (dx).
Legenda: 🟢 ADEGUATO · 🟡 NON ADEGUATO · 🔴 ASSENTE.

**Zone (etichette a destra):**
- **PROTEZIONE DEL REDDITO** (livelli 1-2)
- **PROTEZIONE DEL PATRIMONIO** (livelli 3-4)
- **RISPARMIO** (livelli 5-7)
- **INVESTIMENTO** (livello 8 apice)

**Livelli dal basso all'apice:**
1. IN CASO DI INVALIDITÀ DOVUTA A (rossa): Malattia / Infortunio / Non autosufficienza
2. IN CASO DI PREMORIENZA DOVUTA A (rossa): Malattia / Infortunio
3. IN CASO DI DANNI PROVOCATI AD ALTRI, DOVUTI A (rossa): Veicoli / Immobili / Professioni / Vita privata
4. PERDITA DEI BENI DOVUTA DA Incendi/Eventi/Alluvioni/Terremoti (verde): Immobili / Aziende
5. LIQUIDITÀ GIORNALIERA – Conto Corrente (azzurro)
6. CASSA PER LE LIEVI ESIGENZE (azzurro)
7. CASSA PER LE GRANDI ESIGENZE (azzurro)
8. CRESCITA DEL CAPITALE (verde acqua apice)

Ogni voce ha: campo "sei protetto fino a €___" + pallino colore.

**Sidebar sinistra — dati editabili:**
- reddito_attuale
- estratto_conto_contributivo (Sì/No)
- reddito_lordo_annuale in caso di: invalidita_66_99, inabilita_100, superstiti, responsabilita, perdita_beni

**Footer:** testamento (Sì/No), eredi_legittimi[4]

### Auto-popolamento valori dalle polizze attive del cliente
Mappatura ramo/garanzia → livello piramide (config in Impostazioni):
- Veicoli → max(massimale_rca) polizze RCA
- Immobili → max(capitale_incendio) polizze Casa/Multirischi
- Aziende → max(capitale) polizze Impresa
- Malattia (invalidità/premorienza) → polizze Vita/Infortuni/Salute
- Ecc.

Regole colore pallino (soglie in Impostazioni):
- 🔴 ASSENTE: nessuna polizza copre
- 🟡 NON ADEGUATO: capitale < soglia_minima (es. RCA < €6M)
- 🟢 ADEGUATO: capitale ≥ soglia_ottimale

### Design PIRAMIDE AZIENDE (per persona_giuridica) — da confermare
Struttura base (7-8 livelli): RC veicoli/terzi/dipendenti/prodotti/ambientale/amministratori/datoriale → Guasti/Merci/Crediti/Cyber/Tutela legale → Uomini chiave → Liquidità+TFM → Patrimonio netto (apice)

### Implementazione stimata (~6h)

**Backend (2h):**
1. Model `AnalisiCliente.piramide_v2 = {tipo, dati_reddito, testamento, eredi_legittimi, livelli:[{id,nome,voci:[{label,capitale_attuale,stato}]}]}`
2. `POST /anagrafiche/{aid}/analisi/piramide-v2/auto-popola` — legge polizze attive, aggrega per categoria, calcola stato colore
3. `GET /portale/piramide` — versione read-only
4. `POST /portale/piramide/richiedi-preventivo` (adatta esistente)
5. `PUT /impostazioni/piramide/soglie` — admin config colori

**Frontend Agenzia (2h):**
- Nuovo `PiramideRicca.jsx` con SVG pixel-perfect
- Editing sidebar + footer
- Sub-tab Privato/Aziendale (auto in base a ana.tipo)
- Retrocompatibilità con `PiramideTab` esistente in AnalisiClienteTab

**Frontend Portale (1.5h):**
- Sezione "La mia protezione" (sostituisce endpoint semplice appena creato)
- SVG identica al software agenzia (read-only)
- CTA "Richiedi preventivo" per righe rosse/gialle

**PDF Export (0.5h):** endpoint `/anagrafiche/{aid}/analisi/piramide-v2/pdf` identico allo screenshot

## Sessione 11/02/2026 — Portale Cliente completato + 4 punti finali utente (iter_51: 18/18 PASS)

### Cosa è stato costruito/testato
1. **Notifiche SMTP + WhatsApp — auto-collegate alle config esistenti** (`notification_helpers.py`)
   - `send_email` usa `db.azienda_config.smtp_*` (già configurato: Gmail assicurazioni@schiantarelli.it)
   - `send_whatsapp_message` delega a `routes.whatsapp_evo.send_text_via_evolution` (istanza di default letta da `azienda_config.notifica_scadenze_whatsapp_instance = "agenzia-jacopoooo"`)
   - **Verificato end-to-end**: `invia-credenziali-portale` per Marco Rossi ritorna `email_inviata:true, whatsapp_inviato:true`
   - Fix bug critico: server.py chiamava `send_email`/`send_whatsapp_message` che NON esistevano
2. **Widget Dashboard "Richieste dal Portale Cliente"** (violet, primo task) → link `/richieste-cliente`, count = `db.richieste_cliente.count_documents({stato:'da_verificare'})`
3. **Subdomain routing** (`PortaleSubdomainRedirect` in App.js): hostname `portale.` / `clienti.` / `portal.` o `REACT_APP_PORTALE_HOSTS` → auto-redirect a `/portale`
4. **Template Welcome + Chat bidirezionale Portale ↔ Agenzia**
   - Preset `welcome_portale` in catalogo Alert & Automazioni (personalizzabile)
   - `invia-credenziali-portale` carica template da `db.alert_rules` con substitution `{nome}{link}{email}{tipo_credenziale}{password}`
   - Chat: collection `db.chat_portale`, endpoint cliente `/api/portale/chat/messaggi`, admin `/api/chat-portale/{clienti,{aid}/messaggi,unread}`
   - UI: nuovo tab "Portale Clienti" in `Chat.jsx` + sezione "Chat con l'agenzia" in `PortaleCliente.jsx`

### Test iter_51: 18/18 backend pytest + tutti i flow frontend verificati
Credenziali test: `marco.rossi@demo.it` / `RSSMRC75H10F205X` (CF) — anagrafica `93b73085-100f-4c78-883a-e6cefea49c72`



## Visione
CRM completo per agenzie assicurative italiane multi-tenant: anagrafiche, polizze, titoli,
Prima Nota/Brogliaccio con regole contabili rigorose, AI Copilot (Claude), OCR Gemini,
OpenAPI.it, controllo di gestione (Cervello).

## Stack
React (Shadcn) + FastAPI + MongoDB. Multi-tenant via agenzia_tenant_id (ContextVar).

## Sessione 04/08 — Completato e TESTATO (iter_39 + iter_40, tutti PASS)

### Migrazione Tipi Pagamento (iter_39: 11/11 PASS)
- Movimenti CONTANTI BPER (81) + BONIFICO (41) + PayPal (1) → conto BPER Sondrio; dup eliminati.
- Tab Librerie "Conti / Banche" → conti_cassa; "Tipi pagamento" RIPRISTINATO su richiesta utente
  (etichette combinate modalità+conto es. CONTANTI BPER SONDRIO, 19 voci, colonna conto_nome).
- `shared.resolve_conto_cassa`: nome conto → label tipi_pagamento → mezzi → fallback.
- Nuovi tenant: seed 4 conti default (super_admin.create_agenzia).

### Fix regole contabili Brogliaccio (verificati)
- POST/PUT /contabilita/movimenti risolve conto_cassa_id dal mezzo_pagamento (bug "saldo non si muove").
- BrogliaccioTab + KpiBar si ricaricano dopo registrazione (refreshTick in Contabilita.jsx).
- KPI prima_nota (routes/kpi.py): collezione movimenti + campo data_movimento (era rotto, sempre 0).
- Versamento compagnia (pagamento_compagnia): colonna SALDO -importo + RIMESSE + banca.
- Ritenuta compagnia: NON è spesa → solo SALDO -importo, nessun cash flow; anche in
  _compute_saldi_compagnie (campo ritenute) e KPI cumulativi (cum_ritenute_comp).
- Rappel: NON in Provvigioni → solo colonna RAPPEL, saldo -importo (entrambi i segni);
  KPI: cum_rappel separato, saldo_cassa -= rappel.
- Cleanup anticipi orfani: incassa_titolo elimina righe categoria 'anticipo' del titolo
  (skip giornate chiuse). Sanati 15 movimenti storici.
- POST /polizze fix premio_totale → premio_lordo.

### Mini Bilancio Periodico (iter_40: 12/12 PASS, frontend 100%)
- Tab Cervello "Mini Bilancio" (`MiniBilancioTab.jsx`): CE Ricavi/Costi riclassificati
  automaticamente dalla Prima Nota + SP (saldi conti real-time, debiti v/compagnia, ritenute erario).
- Filtri: Oggi/Mese/Trimestre/Anno/Custom. Drill-down per voce (righe di Prima Nota). Export PDF + Excel.
- Backend: routes/cervello.py `_mb_classify`/`_mb_compute`, GET /cervello/mini-bilancio,
  /dettaglio?key=, /export?formato=pdf|xlsx.
- Voci auto: Provvigioni Attive, Rappel, Storni Ricavi (ricavi); Storni/Rivalse, Provvigioni
  Passive, Spese Varie (costi). Ritenute compagnia ESCLUSE dal CE (partita di giro).
- Libreria "Voci di bilancio" (voci_bilancio, seed 14 voci) + campo voce_bilancio_id nel
  Nuovo movimento (mov-voce-bilancio-select).

### AZZERAMENTO CONTEGGI (richiesto dall'utente per prove — 04/08 17:15)
- ELIMINATI: tutti i movimenti (230), chiusure giornaliere (6), rappel (13).
- AZZERATI: saldo_iniziale di tutti i conti; 444 titoli incassati → da_incassare; 52 coperture reset.
- BACKUP COMPLETO: /app/memory/backups/reset_20260804/*.json (movimenti, chiusure_giorno,
  rappel, titoli, conti_cassa). Per ripristino: reinserire i JSON nelle collezioni.
- Verificato: KPI, liquidità, saldi compagnie, estratti conto, mini-bilancio tutti = 0.

## PROSSIMO TASK (P0) — WhatsApp via Evolution API
Collegare WhatsApp a: Alert & Automazioni + Avvisi di Scadenza.
IN ATTESA dall'utente: URL server Evolution API, API Key globale, nome istanza.
Usare integration_expert prima di implementare.

## Backlog P1
- Widget Documenti Mancanti: bottone Allega inline + note sollecito + filtro collaboratori.
- RCA sostituzione: stessa targa eredita libretto | targa diversa richiede libretto+atto vendita.
- Modulo Asset/Patrimonio Cliente: mappa Leaflet + geocoding + PDF.
- Avatar auto-crop bypass su upload da "Sostituisci Documento".
- Categorie setup_iniziale_* nel Literal MovimentoCategoria (db_models.py).
- Saldi live accanto ai conti nel tab Conti/Banche.

## Backlog P2/P3
- Google Drive sync PDF per tenant.
- Refactor server.py (>10.900 righe) in router modulari.

## Regole critiche
- PAGAMENTO IN DIREZIONE: is_direzione=True → NESSUN cash flow su banche (conto_cassa_id=None).
- Non alterare _RESET_CUSTODE_PASSWORD in routes/super_admin.py.
- Rispondere SEMPRE in italiano.

## Credenziali test
- Admin: admin@assicura.it / Admin123! — Demo tenant: jacopo@admin.it / Admin123!

## 🆕 Sessione 05/08/2026 — Integrazione Modelli + Fix Cassa Sospesi

### ✅ Completato
- **Gestione Modelli ↔ Alert/Automazioni**: `AlertRule.template_modello_id` (backend `alert_models.py`, `routes/alert.py`, `alert_dispatcher.py`) + selettore in `Alert.jsx` che disabilita i template inline quando è selezionato un modello dalla libreria.
- **Gestione Modelli ↔ Avvisi bulk WhatsApp**: `POST /api/avvisi/whatsapp-invia-bulk-titoli` accetta `modello_id` opzionale; UI `BulkAvvisoDialog` con select modelli WhatsApp + preselezione default.
- **Anteprima live**: nuovo endpoint `POST /api/librerie/modelli/preview` (render placeholder con dati fittizi: Mario Rossi, POL-2026-000123). Pannello anteprima live nel `ModelloFormDialog` (Librerie) con toggle.
- **Logo agenzia nei PDF/Word**: helper `_load_logo_bytes(azienda_config)` supporta `logo_storage_path` (file), `logo_url` (data-URL o http). PDF con intestazione a bande (logo + ragione sociale + contatti). DOCX con logo in alto.
- **Numero WhatsApp normalizzato**: `send_text_via_evolution` aggiunge automaticamente prefisso `39` se il numero ha 10 cifre e inizia con `3` (cellulari italiani).
- **TEST WhatsApp REALE inviato** al `+39 346 570 8351` via istanza `agenzia-jacopoooo` — 2 messaggi consegnati con successo (uno con prefisso, uno con normalizzazione).
- **Backend testing_agent**: 18/18 PASS (iter 42).

### 🔴 FIX critico Prima Nota — Cassa contanti con sospesi
- **Bug**: per movimento `incasso_premio` con `quota_credito > 0` (sospeso), la colonna Cassa Contanti mostrava l'importo intero (es. 300€) anziché il netto realmente incassato (280€).
- **Fix** in `_compute_brogliaccio` (server.py):
  - Per movimenti `incasso_premio` in entrata: `cash_reale = importo - quota_credito` prima di aggiornare `per_conto`/`per_conto_tot`.
  - Riepilogo conti cassa: `imp_precedente` ora sottrae `sum(quota_credito)` dei movimenti storici incasso_premio (aggregation MongoDB con `$cond`).
- **Verificato** sullo screenshot: Rossi Marco 300€ → Cassa 280€, Sospesi 20€. Totale giornata Cassa -840€ (era -820€).

### 📌 Prossimi task backlog
- P1: Avatar auto-crop bypass su upload alternativi (routes/documenti_inbox.py)
- P1: `setup_iniziale_*` in `MovimentoCategoria` (db_models.py) per Setup Iniziale
- P1: RCA sostituzione logica (extras_p1p2.py)
- P1: Widget Documenti Mancanti — inline attach + filtro collaboratori
- P1: Modulo Asset/Patrimonio (Leaflet + PDF)
- P2: Google Drive integration
- P3: Refactor server.py (>11k righe → routers modulari)


---

## Iterazione 48 (Feb 2026) — Carichi Mensili smart + Import multi-sezione + Cloud Storage

### ✅ P0 Carichi Mensili — Celle dinamiche + Deduzione AI variazioni
- **Frontend** (`CarichiMensili.jsx`): `TitoloRow` refactorato con dizionario `CELL_RENDERERS`. Le celle ora seguono l'ordine di `orderedColumns` (drag&drop delle colonne funzionante).
- **Backend** (`carichi_mensili.py`): logica di deduzione **deterministica** basata su dati CRM. Nuovi campi risposta per ogni riga:
  - `variazione_badge`: "🔄 Sostituita", "🛑 Disdettata", "⏸ Sospesa" oltre a Aumento/Riduzione/Nuova
  - `variazione_dettaglio`: spiegazione (es. "Sostituita da polizza XYZ effetto 2026-03-01")
  - `note_carico`: preserva manuale + appende deduzione automatica prefissata da 🤖
  - `note_storiche`: nomi dei collaboratori storici dai `provvigioni_operatori`
  - `servizio_sanitario`: da `polizza.premio_ssn`
  - `provvigioni_collab`: somma quote destinate agli operatori
  - `polizza_stato`, `motivo_mancanza` dedotto

### ✅ Import Excel/CSV multi-sezione
- Nuovi router `routes/import_polizze.py` e `routes/import_sinistri.py` con:
  - `POST /api/import/{polizze|sinistri}/preview` (auto-mapping degli header con similarity ≥0.6)
  - `POST /api/import/{polizze|sinistri}/execute` (policy skip/overwrite/create_only)
  - Risoluzione automatica di `contraente_id` (via CF/P.IVA), `compagnia_id`, `polizza_id`
  - Default intelligente: se manca la scadenza, calcola +1 anno dall'effetto
- Nuovo componente frontend `ImportExcelDialog.jsx` riusabile (wizard 3 step: upload → mapping → risultato)
- Pulsanti "Importa Excel/CSV" aggiunti in `/anagrafiche`, `/polizze`, `/sinistri`
- Testato con auto-mapping al 100% di confidence su header italiani standard

### ✅ Cloud Storage: Google Drive + Microsoft OneDrive
- Nuovo router `routes/cloud_storage.py` con OAuth 2.0 authorization code flow:
  - `GET /api/librerie/cloud-storage/config-status`
  - `GET /api/librerie/cloud-storage/oauth-url?provider=...`
  - `GET /api/librerie/cloud-storage/callback` (redirect al frontend)
  - `GET /api/librerie/cloud-storage/status`
  - `GET /api/librerie/cloud-storage/folders?provider=...&parent_id=...`
  - `POST /api/librerie/cloud-storage/set-folder`
  - `POST /api/librerie/cloud-storage/upload` (multipart Google Drive, upload session OneDrive per file >4MB)
  - `DELETE /api/librerie/cloud-storage/disconnect`
- **Sicurezza multi-tenant**: refresh token cifrati con Fernet (AES-128), isolamento per `tenant_id` in tutte le query.
- Nuova sezione **"Cloud Storage (Drive/OneDrive)"** in `/librerie` con:
  - Card Google Drive e Microsoft OneDrive
  - Folder picker (breadcrumb-based navigation)
  - Setup instructions per admin (Google Cloud Console + Microsoft Entra + Redirect URI)
- ENV richieste (in `backend/.env`): `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, `MS_ONEDRIVE_CLIENT_ID`, `MS_ONEDRIVE_CLIENT_SECRET`, `CLOUD_STORAGE_ENCRYPTION_KEY` (auto-generata), `BACKEND_PUBLIC_URL`
- **Testing**: 10/10 backend + frontend 100% (iter 48 pytest). Il flow OAuth reale sarà attivabile appena l'utente fornirà i Client ID/Secret dei provider.

### 📌 Backlog aggiornato
- P0: Attivazione reale Google Drive/OneDrive (attesa credenziali OAuth utente)
- P1: Avatar auto-crop bypass su upload alternativi (routes/documenti_inbox.py)
- P1: `setup_iniziale_*` in `MovimentoCategoria`
- P1: RCA sostituzione logica (extras_p1p2.py)
- P1: Modulo Asset/Patrimonio (Leaflet + PDF)
- P2: Sincronizzazione automatica PDF polizze → Cloud collegato
- P3: Refactor server.py (>11k righe)


---

## Iterazione 54 (Giu 2026) — Piramide VERA + pallini cliccabili + CTA Analisi Personalizzata

### ✅ Piramide Coperture — forma triangolare reale
- `PiramidePrivati.jsx` riscritto: triangolo unico 1040×800px con clip-path sul wrapper — tutto il contenuto (strip, label, input, pallini) resta SEMPRE dentro i bordi. Base larga + scroll orizzontale su mobile.
- **Logo agenzia in alto a SINISTRA** (helper `resolveLogo` gestisce path relativi/data-url/http) + box "PIRAMIDE DELLA PROTEZIONE DI: {cliente}" a destra.
- **Pallini CLICCABILI** (lato agenzia): ciclo verde → giallo → rosso → automatico. Persistiti in `piramide_v2.stato_voci` (nuovo campo su GET/PUT `/api/anagrafiche/{aid}/analisi/piramide-v2` e su `GET /api/portale/protezione`). Nel portale (read-only) il click su pallino ≠ verde invia richiesta preventivo.
- GET piramide-v2 e /portale/protezione ora ritornano `cliente_nome`.
- Fix HIGH (da testing iter 54): `eredi_legittimi` non-stringa causava crash "trim is not a function" al salvataggio → normalizzazione sia frontend (`normEredi`) sia backend (PUT converte dict→nome, scarta vuoti). Verificato via curl.

### ✅ CTA "Analisi Personalizzata" nel Portale Cliente
- Sezione "La mia protezione": card CTA sotto la piramide con:
  - **Upload PDF INPS estratto conto contributivo** → `POST /api/portale/analisi-personalizzata/upload-inps`: parsing pdfplumber+inps_calculator, archiviazione in `analisi_cliente.estratti_conto_inps` con `fonte: portale_cliente`, merge non distruttivo storico redditi/periodi, notifica in `db.richieste_cliente` (tipo `upload_estratto_inps`).
  - **Player video motivazionale**: YouTube embed (auto-convert watch→embed) o `<video>` da file MP4 caricato dall'agenzia.
  - Lista "Documenti già inviati".
- `GET /api/portale/analisi-personalizzata`: {video_url, video_file, estratti}.
- Endpoint pubblici (senza auth, per tag img/video): `GET /api/portale/public/logo` (fix logo rotto nel portale) e `GET /api/portale/public/video-analisi`.
- Badge viola **"dal portale"** sugli estratti INPS caricati dal cliente nell'Archivio INPS di `AnalisiClienteTab.jsx`.

### ✅ Pannello video in Librerie → Azienda
- Nuova sezione "Video Analisi Personalizzata (Portale Cliente)": input URL YouTube (salvato con Salva via PUT /librerie/azienda), upload MP4 max 80MB (`POST /librerie/azienda/video-analisi`), Rimuovi (`DELETE`).
- Demo attivo: video_analisi_url YouTube di test configurato.

### 🧪 Testing iter 54: backend 12/12 pytest, frontend 90%→100% dopo fix eredi. Regressione ANIA import OK (mappings senza duplicati, apply 200, /importazione senza errori JS).

### 📌 Backlog aggiornato
- P1: Piramide PDF Export pixel-perfect (weasyprint) per stampa/email
- P1: Piramide Aziende (variante persona_giuridica: RC datoriale/prodotti/ambientale, uomini chiave, patrimonio netto)
- P2: Notifica Piramide mensile via email con toggle per agenzia
- P2: Importer storico 3 CSV (Anagrafiche, Portafoglio veicoli, Prima nota) con merge intelligente
- P2: Pannello personalizzazione portale (slogan, colori)
- P0 (tech debt): Refactor server.py (>12k righe)


## Sessione 2026-06 (fork) — Fix definitivo interattività Piramide
### ✅ Piramide Privati: root cause REALE trovata e risolta
- Il problema NON era il clip-path (già sistemato): era un **reset dello stato React**. I default prop `= {}` di `PiramidePrivati.jsx` creavano una nuova referenza ad ogni render; gli `useEffect` con dipendenza sull'oggetto si ri-attivavano e azzeravano `custom`/`overrides`/`stati` subito dopo ogni modifica (il "+" aggiungeva la riga ma spariva, il testo digitato veniva cancellato, il colore tornava indietro).
- Fix: sync dalle prop solo su cambio di CONTENUTO (firma JSON.stringify come dipendenza degli effect).
- Fix secondario: `cycleStato` ora parte dallo stato attualmente visualizzato (prima il primo click su un pallino già "adeguato" non cambiava colore).
- Testato via browser automation: + aggiunge riga ✓, digitazione label/capitale/input standard ✓, ciclo pallino rosso→verde→giallo→rosso ✓, salvataggio + persistenza dopo reload ✓.

## Sessione 2026-09 (fork) — Implementato
- Fix Piramide: stato non si resetta più (useEffect firma JSON); pallino cambia colore al 1° click
- Fix crash Assistente Personale: CopilotWidget spostato dentro BrowserRouter
- NotebookLM assicurativo (/notebook-ai): notebook + fonti (upload/CRM) + chat streaming con citazioni + riassunti/FAQ/guide + Audio Overview podcast 2 voci (routes/notebooklm.py)
- Modelli Piramide (/modelli-piramide): template globali Privati/Aziende modificabili (righe custom) propagati a tutti; Aziende auto per P.IVA/persona_giuridica (routes/piramide_templates.py)
- Sistema colonne tabelle: useTableColumns + ColumnPicker (drag&drop, salvataggio per utente su DB) applicato a Polizze/Anagrafiche/Titoli/Sinistri (components/ColumnManager.jsx, routes/preferenze.py)
- Unisci doppioni anagrafiche (stesso CF/P.IVA) con riassegnazione polizze/sinistri/allegati/utenti (routes/anagrafiche.py: /anagrafiche-duplicati, /anagrafiche-unisci)
- Indici DB allo startup (indexes.py); /api/search limit default 50
- Super Admin: Domini Agenzia (sottodominio + credenziali dedicate) + console Scambi Dati con approvazione (super_admin.py, setup_scambio.py richiedi/richieste)
- Link portale personalizzato /c/{slug} formato https://{sottodominio-agenzia}.{dominio}/c/{cliente} (server.py _portale_link_per_ana, pages/PortaleLanding.jsx) + bottone copia in AnagraficaDetail
- Avatar automatico da documento identità: OpenCV face crop al caricamento OCR + batch notturno 02:30 + POST /api/avatar-batch/esegui (face_crop.py)
- Tabella Anagrafiche compattata (righe 45px, badge inline)
- Test: iteration_56.json 9/9 backend PASS + frontend OK; avatar e2e verificato manualmente

## Backlog (scelte utente già confermate)
- P0: Copilot ibrido (Haiku semplici/Sonnet complesse) + streaming SSE + query DB parallele (scelta c+d)
- P1: Studio Marketing: reel slideshow MP4 (ffmpeg da installare), caroselli IG, sito web AI + ZIP export (dominio esterno), piano editoriale con calendario; fal.ai quando utente fornirà key
- P1: Confronto Preventivi (2-4+ PDF → estrazione garanzie/massimali/franchigie → tabella + giudizio AI)
- P1: Carichi Mensili YoY (validare UI), Compagnia logo (UI Librerie), Piramide PDF export (weasyprint)
- P2: Notifica piramide mensile con toggle per agenzia; doppio passaggio OCR polizze (Flash→Sonnet); split server.py (>12.9k righe)
- Immagini AI (/immagini-ai): generazione immagini marketing con Gemini Nano Banana via Emergent LLM Key; formati 1:1/9:16/16:9, stili, galleria su object storage (routes/immagini_ai.py, pages/ImmaginiAI.jsx). Testato e2e (11s/immagine)

## Sessione 2026-06 (fork 2) — Implementato
- Studio Marketing → tab Presentazioni: generazione AI (argomento o punti chiave), stile brand/sfondi AI 16:9, output PPTX editabile (python-pptx) + PDF + anteprime JPEG, slide contatti auto da azienda_config (routes/marketing_presentazioni.py, StudioMarketing.jsx PresentazioniTab). Testato e2e (iter57)
- Sfondi AI orizzontali: _genera_sfondo(orizzontale=True) in marketing_studio.py
- Fix anagrafiche: flag Preferenze canale sempre cliccabili (non più disabled senza email/cellulare); auto-flag WhatsApp al blur cellulare, Email al blur email (niente più auto-SMS); sovrascrittura anagrafica (overwrite_id) ora MERGE conservativo: mantiene dati esistenti, integra solo campi vuoti, tags in unione (routes/anagrafiche.py ~380)
- SICUREZZA CHIAVI API: chiavi firma Namirial/Twilio/Spoki/server Evolution visibili SOLO al super admin. Nuovo tab "Chiavi API" in /super-admin (GET/PUT /super-admin/chiavi-api + test-whatsapp). Redazione segreti in GET/PUT /librerie/azienda e /librerie/comunicazioni per non-super-admin (_SEGRETI_AZIENDA, _CAMPI_SOLO_SUPER_ADMIN in librerie.py). Pagina Firma Elettronica rimossa dal menu agenzia (ImpostazioniFirme.jsx eliminata), sezione Twilio rimossa da Comunicazioni, provider WhatsApp read-only per agenzia (badge wa-provider-attivo), ServerConfigCard rimossa da /whatsapp, PUT/DELETE/test /whatsapp-evo/config → 403 non-super-admin. Email SMTP/IMAP e Google Drive invariati per agenzia (scelta utente). wa.me mantenuto come fallback attivabile dal super admin per agenzie senza Evolution
- Test: iteration_57.json — backend 9/9 PASS, frontend 100%

## Sessione 2026-06 (fork continuazione) — PolizzaDetail
- Scheda "Premi" ora modificabile INLINE (nessun popup): pulsante "Modifica premi" mostra input per premio_netto/tasse/imposte/ssn/lordo/provvigioni + Salva/Annulla, resta sulla stessa scheda (PUT /polizze/{id})
- Rimossi "Frazionamento" e "Ultimo premio pagato" dalla scheda Premi (già presenti nel riquadro in alto con le date)
- Ordine tab invertito: Garanzie prima di Premi
- Garanzie → riga TOTALE: cella Provvigioni ora modificabile inline (ProvvigioniTotaleCell, PUT /polizze/{id} {provvigioni}); valore preso dal campo provvigioni della polizza
- Completato task in sospeso: uploadLibretto nella tab Veicolo (era crash "librettoUp is not defined"). Usa POST /ocr/libretto + /ocr/libretto/apply; allegato salvato con categoria "libretto_veicolo" e visibile_cliente=true (routes/ocr.py _salva_allegato_libretto)
- Bugfix: GET /polizze/{id} andava in 500 (KeyError compagnia_id) per polizze senza compagnia/contraente → ora usa .get() (server.py get_polizza ~2415)
- Bugfix: riquadro in alto mostrava "undefined" per Frazionamento nullo → ora "—"
- Verificato via screenshot su agenzia test (test@sandbox.it): modifica premi inline OK, toast "Premi aggiornati", ordine tab OK

## Sessione 2026-06 (fork continuazione, parte 2) — PolizzaDetail + Titoli + Provvigioni
- Premi: aggiunti campi Accessori (premio_accessori) e Diritti (diritti); premio_lordo AUTO = netto+tasse+imposte+ssn+accessori+diritti (readonly); rimosso campo Provvigioni dalla scheda Premi. Aggiunto premio_accessori al db_model Polizza.
- Veicolo (tab): modifica INLINE (nessun popup). Ricerca Targa con TargaSearchWithLentina; alla selezione di una targa TUTTI i campi veicolo vengono RESETtati e riempiti dai dati dell'archivio (chiavi multiple: kw/potenza_kw, cv/cv_fiscali/potenza_cv, tipo_veicolo/tipo/categoria/codice_oggetto, uso/codice_uso). Massimali con separatore migliaia it-IT.
- Veicolo archivio SYNC: nuovo endpoint PUT /veicoli/by-targa/{targa} (server.py ~6590) che aggiorna/crea il veicolo in archivio con i dati corretti dal dettaglio polizza (così una ricerca successiva non ripropone dati errati es. openapi_mock). Chiamato da saveVeicolo.
- Provvigioni (tab): pulsante Modifica per editing inline del totale (PUT /polizze provvigioni). Auto-calcolo quota collaboratore da SistemaProvvigionale VERIFICATO funzionante (es. Sara 70% → 8,53€ su 12,18€). Ripartizione: alla selezione di un collaboratore vengono proposti anche i livelli superiori (upline) dallo schema, con provvigione = % sul totale (badge 'livello superiore').
- TitoloDialog: rimossi i campi 'Data incasso' e 'Copertura fino al' (auto-generati a incasso/copertura). Tipo pagamento ereditato dal mezzo_pagamento_preferito della polizza. Fix 'Eredita da polizza': leggeva o.operatore_id ma la polizza salva o.collaboratore_id → ora legge entrambi.
- CollaboratoreInlineSelect: fix testo bianco-su-bianco nel <select> (aggiunto text-slate-800).
- Verifiche: screenshot su agenzia test (Premi lordo=128, tab order, Provvigioni edit, Veicolo inline+targa search+massimali, TitoloDialog senza campi rimossi); curl PUT /veicoli/by-targa OK; get_polizza provvigione_collaboratore OK. NOTA: autofill archivio + upline richiedono dati reali (archivio veicoli / schema con upline) presenti solo sull'agenzia principale; l'upline si attiva quando l'utente configura la 'Rete piramidale' nello schema.

## Sessione 2026-06 (fork continuazione, parte 3) — Titoli
- Primo titolo auto-precompilato: quando la polizza NON ha titoli, "+ Nuovo titolo" precompila tipo="nuova" (Polizza nuova), effetto, scadenza, importo_lordo, importo_netto, imposte, provvigioni dalla polizza (PolizzaDetail new-titolo-btn onClick). Verificato su sandbox (lordo 128, netto 100, provvigioni 50).
- Titolo auto-provvigioni: alla selezione del collaboratore nella ripartizione operatori del titolo, la quota € viene calcolata automaticamente dallo schema (percentuale_collaboratore × totale provvigioni titolo) via GET /librerie/schema-provvigionale. Rimosso il vecchio effetto che sovrascriveva f.provvigioni con la somma operatori (il totale resta indipendente, coerente col breakdown a lettura). Fix ereditarietà: legge o.collaboratore_id||o.operatore_id. Tipo pagamento ereditato dal preferito polizza.
- NON fatti (scelta utente): Report Provvigioni (NO); Storico Veicolo elenco polizze (NO, lasciata solo la segnalazione TargaConflictWidget di polizza collegata ad altra attiva).

## Sessione 2026-06 (fork continuazione, parte 4) — Import storico OWEB/Cattolica
- Ricevuto ZIP export OWEB/SHARE (compagnia CAT/Cattolica, ANIA 57): rec00/10/20/21/24/30/40/41/42/43/50/51/52/70/100/101, semicolon-separated, ~1M righe (~500MB). rec40 contiene netto_totale/tasse_totale/lordo_totale/provvigioni_totale.
- VERIFICATO: il tracciato è GIÀ pienamente supportato da ania_importer.importa_zip (endpoint POST /api/import/ania e alias /api/import/omnia). Nessuna modifica di codice necessaria.
- Test reale su agenzia sandbox: campione allineato → 5 polizze, 20 titoli con premi corretti (lordo=netto+imposte, provvigioni), anagrafiche collegate; entità non mappate tracciate (compagnia CAT, 41 prodotti, 12 collaboratori, rami). Wizard di mappatura disponibile in pagina /importazioni tab OMNIA.
- CAVEAT: file completo molto grande (~500MB); l'upload via browser potrebbe essere lento/pesante e l'endpoint è sincrono → valutare upload chunked/import in background se l'upload fallisce.

## Sessione 2026-06 (fork continuazione, parte 5) — Recupero Biblioteca Previdenza Super Admin
- PROBLEMA: dopo lo spostamento della Biblioteca Previdenza al tenant globale (__global_library__), i ~1011 PDF caricati in precedenza (sotto tenant-principale-schiantarelli) non erano più visibili nella console Super Admin (che legge solo il globale). biblioteca_previdenza è MIXED_SHARED.
- FIX (migrazione dati): spostati 1011 documenti previdenza (sezione None/previdenza) + 1 cartella custom da tenant-principale-schiantarelli → __global_library__ (sezione impostata a 'previdenza'). Le 40 "Condizioni di Polizza" restano per-agenzia (corretto). L'agenzia principale continua a vederli (MIXED legge tenant+globale).
- Consolidata categoria duplicata: 'PENSIONE INTEGRATIVE' (6) → 'PENSIONE INTEGRATIVA' (default). Totale previdenza globale: 1012.
- Discoverability: aggiunto tab "Biblioteca & Schede Calcolo" nel pannello Super Admin (SuperAdminPanel.jsx) che naviga a /super-admin/biblioteca (prima raggiungibile solo dal pulsante header). Verificato via screenshot: categorie e Schede di Calcolo tutte presenti.

- CONFERMA collegamento calcoli: verificato via API che l'agenzia principale (admin@assicura.it) legge i 1012 PDF previdenza dal globale (cartelle con conteggi corretti). Il widget "Consulto AI · Biblioteca Previdenza" nelle schermate di analisi cliente (Pensione INPS, Approfondimento Redditi, Successione, Riepilogo Pensionistico) usa questi PDF per categoria. Gestione centralizzata Super Admin → propagata a tutte le agenzie.

## Sessione 2026-06 (fork continuazione, parte 6) — Stato polizze import OWEB + protezione metodi di calcolo
- BUG stato polizze: il tracciato OWEB usa cod_stato_share con codici AT/ST/SO/SP, ma _MAP_STATO_POLIZZA in ania_importer.py mappava solo a/s/x → TUTTE le polizze importate finivano "attiva" (incl. 28k stornate). FIX: aggiunti codici at→attiva, st→annullata, so/sp→sospesa, an→annullata; inoltre se data_annullamento è valorizzata e lo stato calcolato è attiva → annullata.
- Correzione dati esistenti: l'import di questo file era già stato eseguito oggi sull'agenzia principale (49.219 polizze tutte "attiva"). Script di correzione mirata via id_polizza_exp incrociato col rec20: aggiornate 43.389 polizze → distribuzione reale annullata 28.156, sospesa 15.232, attiva 5.758. Verificate le polizze dello screenshot utente: ora "annullata".
- Protezione metodi di calcolo (richiesta utente: nessuna manomissione dalle agenzie, propagazione dal Super Admin):
  * genera_scheda (POST /schede-calcolo/genera): aggiunto _guard_libreria_globale("previdenza") → agenzia 403, super admin 200.
  * sync_drive: la sezione previdenza viene sincronizzata SOLO dal super admin (le agenzie sincronizzano solo le proprie Condizioni).
  * upload/delete/create_cartella previdenza già protetti. Docs previdenza vivono nel tenant globale (__global_library__) → un'unica copia, ogni modifica del super admin è propagata a tutte le agenzie in lettura (MIXED_SHARED).
  * Verificato via curl: agenzia upload/genera previdenza = 403; super admin = 200/consentito.

## Sessione 2026-06 (fork continuazione, parte 7) — Stato scadute, filtri conteggi, import duplicati
- Stato "scaduta": nuovo endpoint POST /polizze/ricalcola-scadute (admin) → marca 'scaduta' le polizze attive con scadenza passata (scadenza > "" e < oggi) e SENZA rinnovo attivo (nessun titolo con coperto_fino_a >= oggi). Eseguito su agenzia principale: 1746 marcate → attive 5826→4080, scadute →1747. Pulsante "Segna scadute" in Polizze.jsx (admin).
- Filtri rapidi con conteggi: nuovo endpoint GET /polizze/conteggi-stato (aggregazione per stato, rispetta visibility_filter). Chip preset in Polizze.jsx (Tutte/Attive/Scadute/Sospese/Annullate) mostrano il conteggio.
- Import duplicati: l'import ANIA/OMNIA fa già upsert (_upsert_polizza per id_polizza_exp) → i doppioni vengono SOVRASCRITTI/aggiornati, mai duplicati. Aggiunto banner nel report import (Importazione.jsx) "Doppioni rilevati e sovrascritti: N polizze e M anagrafiche già presenti aggiornate".
- Nota: endpoint statici /polizze/conteggi-stato e /polizze/ricalcola-scadute inseriti PRIMA di /polizze/{pid} per evitare cattura del path param.

## Sessione 2026-06 (fork continuazione, parte 8) — Situazione Patrimoniale + attivazione Visura/Catasto
- Fix UI Analisi Cliente (AnalisiClienteTab.jsx): barra Salva resa STICKY (top-0 z-30) + aggiunto pulsante "Salva situazione patrimoniale" in fondo alla tab Patrimonio (props save/dirty/saving a PatrimonioTab). Messaggio auto-popola veicoli ora accurato (aggiunti / già aggiornati con polizze_trovate / nessuna polizza — attenzione duplicati).
- Backend auto_popola_veicoli (server.py): ora considera anche anagrafiche duplicate con stesso codice_fiscale/partita_iva, esclude stato 'scaduta', ritorna polizze_trovate.
- Caso Schiantarelli: la polizza auto 183629579 (attiva, targa FB828CV) è intestata all'anagrafica duplicata adf21a7f (ragione_sociale, CF SCHJCP91M18I829O), diversa da quella su cui era l'utente → auto-popola non la trovava. Servirebbe merge anagrafiche duplicate (da confermare con utente).
- OpenAPI.it Visura Camerale (imprese) + Catasto: integrazione GIÀ presente (openapi_it_service.py, routes/openapi_it.py). Credenziali OAuth VALIDE (mode live, credito €99,40). MA il token per GET:imprese.openapi.it/advance e catasto → HTTP 406 "invalid scopes specified or API not enabled": i due prodotti NON sono attivati sull'account OpenAPI.it (schiantarelli.jacopo@gmail.com). AZIONE UTENTE: attivare le API "Imprese/Visura Camerale" e "Catasto" su console.openapi.com. Nessuna modifica codice necessaria; passerà da mock a live in automatico.

## Sessione 2026-06 (parte 9) — Attivazione OpenAPI.it (Catasto/Visengine)
- Il token statico "Lista Token Produzione" (6a99...) NON è un Bearer valido → API risponde 401 "Wrong Token". OPENAPI_IT_BEARER_TOKEN rimesso a "" (l'app usa OAuth client_credentials).
- OAuth client_credentials (client_id/secret già in .env) ORA ottiene token 200 per: Visengine (visengine2.altravia.com/visure,richiesta,documento) e Catasto (catasto.openapi.it/richiesta,visura_catastale). "Imprese" (imprese.openapi.it) resta 406 "API not enabled" → non attivato (ma Visengine copre CCIAA).
- MA fetch_cadastre / fetch_company nel service ricadono ancora su MOCK: i flussi LIVE async (POST richiesta → polling GET → documento) NON sono implementati davvero, restituiscono dati simulati. Da implementare: flusso Visengine (unico motore documenti CCIAA/INPS/Agenzia Entrate) create→poll→download PDF su object storage.
- Servizi attivati lato account: Visengine (Attivo), Catasto (scope selezionati). Credito €99.

## Sessione 2026-06 (parte 10) — Catasto LIVE ok, Visura Camerale da costruire con selettore
- CATASTO: FIX applicato e testato LIVE. fetch_cadastre ora legge il formato reale (data.stato="evasa", data.risultato.soggetti[].catasti[].comuni[]) invece del vecchio res.get("success"). Nuovo _normalize_cadastre_nazionale. Test: CF SCHJCP91M18I829O → TIRANO (SO) 3 fabbricati (LIVE). Endpoint POST /openapi-it/cadastre/{aid}.
- OPENAPI_IT_BEARER_TOKEN rimesso a "" (il token "Lista Produzione" 6a99.. non è un Bearer valido → "Wrong Token"). L'app usa OAuth client_credentials: token 200 per Catasto e Visengine; "imprese.openapi.it" ancora 406 "API not enabled".
- VISURA CAMERALE: da fare come richiesto dall'utente → cliccando "Camerale" mostrare SELETTORE documenti (Visura ordinaria imprese individuali / società capitali / società persone; Visura storica x3; Bilancio Aziendale; Certificato Camerale iscrizione; Certificato con vigenza; Elenco Soci Attivi) con opzione "tutti / seleziona alcuni". API = "Visure Camerali" (imprese/visurecamerali.openapi.it). RICHIEDE che l'utente ATTIVI l'API "Visure Camerali/Imprese" su console.openapi.com (ora 406). Poi implementare: lista prodotti + POST richiesta con json per tipo + polling + salvataggio PDF/dati.
- Anche i doc Visengine (Estratto Contributivo, ISEE, 730, pensioni, Visura PRA) richiedono json_visura per-prodotto (HTTP 412 "insufficient data" se mancano campi): da costruire con schema per prodotto.

## Sessione 2026-06 (parte 11) — Catasto dettaglio bloccato su endpoint
- Catasto: ricerca_nazionale LIVE OK (comune+conteggio: TIRANO 3 fabbricati). Ma il DETTAGLIO (foglio/particella/categoria/rendita) richiede un secondo endpoint non ancora individuato: provati POST /richiesta/{ricerca|ricerca_immobili|immobili|visura_catastale|ricerca_immobili_soggetto} → tutti HTTP 400 "wrong endpoint". Lo scope GET:catasto.openapi.it/visura_catastale esiste → probabile endpoint GET top-level (non sotto /richiesta) con id_soggetto/provincia. DA CONFERMARE da doc OpenAPI.it Catasto.
- Widget UI "Autocompilazione OpenAPI.it" mostra colonne foglio/particella/cat/sup/rendita → attualmente vuote perché ricerca_nazionale non le fornisce.

## Sessione 2026-06 (parte 12) — Catasto estrazione REALE + Selettore Visengine (COMPLETATO)
- CATASTO (LIVE, testato end-to-end): implementato `fetch_cadastre_detailed` in openapi_it_service.py.
  Flusso: POST /richiesta/ricerca_nazionale (id_soggetto) → POST /visura_catastale {entita:"soggetto",tipo_visura:"ordinaria",tipo_formato:"json",tipo_dettaglio:"analitica"} → polling GET /visura_catastale/{id} → download JSON strutturato → parsing immobili (foglio/particella/sub/categoria/rendita/superficie/indirizzo/comune/titolo/quota). In parallelo genera anche la visura PDF ufficiale (ordinaria) salvata negli Allegati.
  Parser `_parse_visura_json` legge VisuraSoggettoAttuale.GruppoUnitaImmobiliari[].ImmobileFabbricatiS/ImmobileTerreniS. Titolo/quota dal match CF su IntestazioneGruppo.
  Endpoint: POST /openapi-it/cadastre/{aid} (estrae + salva PDF, ritorna immobili) e POST /openapi-it/cadastre/{aid}/importa-immobili (aggiunge gli immobili selezionati a analisi_cliente.immobili, dedup foglio+particella+comune, usa `db` tenant-aware).
  UI: pulsante "Catasto" → CatastoImportDialog.jsx (selettore "tutti o alcuni") → import in Analisi Cliente > Patrimonio > Immobili.
  Test LIVE: P.IVA 12485671007 (ALTRAVIA) → 1 ufficio ROMA A/10 Fg872 Part405 rendita 2566.79, PDF salvato, import OK.
- VISENGINE / VISURE & DOCUMENTI (LIVE plumbing testato): nuovo pulsante "Visure & Doc." → VisengineDialog.jsx.
  Lista FISSA di 16 documenti (Camerali 3 + Patronato 13) con hash reali (VISENGINE_CATALOG in openapi_it_service.py).
  Flusso: step "select" (checkbox + Seleziona tutti) → step "compile" (GET /visengine/schema/{hash} carica json_struttura, campi precompilati dai dati anagrafica, input file per documenti che richiedono allegati identità/tessera/mandato) → POST /visengine/request/{aid} (crea pratica, se sincrona scarica subito il PDF in Allegati) + storico richieste con refresh (POST /visengine/refresh/{aid}/{rid}).
  Endpoint: GET /visengine/catalog, GET /visengine/schema/{hash}, POST /visengine/request/{aid}, POST /visengine/refresh/{aid}/{rid}.
  NOTA COSTI: ogni documento Visengine e ogni visura catastale è a pagamento (POST /richiesta). Il POST live è stato validato solo su error-path (HTTP 412 su dati incompleti, nessun addebito). L'invio reale di documenti Visengine NON è stato test-fired per non addebitare crediti: da testare dall'utente.
  Allegati salvati via obj_storage + modello Allegato standard (is_deleted=False) così compaiono nel tab "Altri allegati" e sono scaricabili.
- Test: testing_agent frontend 100% (iteration_68.json). Credito OpenAPI.it residuo ~€76.
- Dati di test creati nel tenant sandbox: anagrafica 931835cd-... "ALTRAVIA TEST CATASTO" (P.IVA 12485671007) con 1 immobile importato + PDF visura.

## Sessione 2026-06 (parte 13) — Camerale/Bilancio + Mappa Immobili + Riuso gratuito (COMPLETATO)
- KPI Anagrafiche (routes/anagrafiche.py /anagrafiche/stats): 'n' ora conta SOLO i contraenti distinti con almeno una polizza attiva/in_emissione (via $addToSet contraente_id); premi già solo da polizze attive. Etichetta card "tot." → "con pol." (Anagrafiche.jsx). Vale anche per KPI custom.
- CAMERALE / VISURE CAMERALI (visurecamerali.openapi.it — ATTIVO): pulsante "Camerale" apre CameraleDialog.jsx ("Dati Azienda & Bilancio").
  - Ricerca GRATUITA: GET /impresa/{cf_piva} → denominazione, comune, natura giuridica, elenco documenti richiedibili con prezzi. Endpoint: GET /openapi-it/camerale/{aid}/search.
  - Documenti ufficiali PDF (a pagamento): POST /{doc_type} → poll stato_richiesta (In ricerca→In erogazione→Dati disponibili→Visura evasa) → download /{id}/allegati → salva Allegato. Endpoint: POST /openapi-it/camerale/{aid}/documento {doc_type, anno?}. Tipi: ordinaria/storica società capitali/persone/impresa individuale, bilancio-ottico, certificato-iscrizione(-vigenza), soci-attivi.
  - RIUSO GRATUITO: prima di pagare, vc_find_existing() usa la GET gratuita /{doc_type} per trovare una richiesta già pronta della stessa azienda e la riscarica GRATIS (prezzo=0, riusato=true). Testato: 1ª soci-attivi a pagamento, 2ª riusata gratis.
- BILANCIO strutturato (company.openapi.com — ATTIVO, imprese.openapi.it invece è 406/non attivo):
  - IT-advanced: dati camerali + bilanci sintetici (anno, fatturato/turnover, patrimonio_netto, dipendenti, capitale, ecc.). Endpoint: GET /openapi-it/camerale/{aid}/bilancio.
  - IT-full: + indici (redditività roe/roi/ros/roa, liquidità, leva, kpi), amministratori (con LR), soci. Endpoint: GET /openapi-it/camerale/{aid}/bilancio?full=true.
  - Servizio: openapi_it_service.company_dati(), _normalize_company_co().
- MAPPA IMMOBILI (AnalisiClienteTab.jsx → PatrimonioTab): componente ImmobiliMap (Leaflet via CDN) mostra i pin degli immobili geolocalizzati. Pulsante "Geolocalizza immobili" → POST /openapi-it/analisi/{aid}/geocode-immobili (Nominatim, gratuito). Geocoding automatico anche all'import Catasto (con pulizia indirizzo catastale + fallback su comune). Helper: routes/openapi_it.py _clean_catasto_address(), _geocode_immobile().
- SPIEGAZIONE ENDPOINT GRATUITI (per l'utente): i GET gratuiti (0.001€, 1440/gg) o elencano/riscaricano richieste GIÀ generate (riuso senza ripagare) o fanno ricerca commerciale gratuita (visurecamerali /impresa). Non esiste modo gratuito per generare NUOVE visure catastali/camerali.
- Test: testing_agent frontend iteration_69 (Camerale dialog + mappa) 100%. Backend validato via curl (search/bilancio/documento/riuso/geocode).
- Anagrafica test società capitali: 931835cd-... (OPENAPI/ALTRAVIA P.IVA 12485671007) con 1 immobile geolocalizzato + soci-attivi PDF salvato.

## Sessione 2026-06 (parte 14) — Fix download documenti camerali + test Bilancio Ottico
- BUG FIX (openapi_it_service.vc_download): l'endpoint visurecamerali /{doc_type}/{id}/allegati NON restituisce il PDF diretto ma JSON {data:{nome:"*.zip", file:"<base64 ZIP>"}}. Ora vc_download: rileva JSON → base64-decode → estrae il primo .pdf dallo ZIP → salva il PDF corretto (con nome/content_type reali). Gestisce anche PDF diretto e ZIP senza pdf. Firma cambiata: ritorna (status, bytes, content_type, filename). Aggiornati camerale_documento e camerale_refresh.
- TEST REALE Bilancio Ottico su AUTOTRASPORTI VIVIANI SRL (P.IVA 00920050143, BIANZONE SO, SRL): PDF ufficiale 27 pagine, chiusura 31/12/2025 (Ricavi 6.444.977, perdita -8.052), salvato in Allegati e scaricabile. Riuso 2ª volta a €0 confermato.
- Nota: allegati salvati PRIMA del fix (es. soci-attivi ALTRAVIA, 1° bilancio VIVIANI) contengono il JSON grezzo (artefatti di test, non critici).

## Sessione 2026-06 (parte 15) — Predisposta API Report Aziende (api.reportaziende.it)
- Integrata "API Dettaglio Azienda" di Reportaziende.it (manuale utente v3.0). Host: api.reportaziende.it, auth Bearer OAuth oauth.openapi.it (stesso wallet). Endpoint GET /dettaglioazienda/visualizza/{CF}/{SCHEDE}. 1 credito per scheda.
- 13 schede: ANA anagrafica, 05 quadro, 10 conto economico, 20/30 SP attivo/passivo, 40 indici, 50 redditività, 60 produttività, 70 crescita, 85 soci/esponenti/CEO, 95 gruppo/holding, PROT protesti&pregiudizievoli, CR credit score&rating.
- Backend: openapi_it_service.report_azienda()/report_schede_catalog() (scope GET:api.reportaziende.it/dettaglioazienda/visualizza). Route: GET /openapi-it/report-azienda/catalog, POST /openapi-it/report-azienda/{aid} {schede:[...]}. Salva in openapi_data.report_azienda.
- Frontend: sezione "Report Azienda (schede avanzate)" dentro CameraleDialog con checkbox schede (default ANA,40,CR,PROT) + "Genera report" + renderer generico (flat=key/value, per_anno=tabella).
- STATO: il prodotto NON è attivo sul token OAuth attuale (nessuno scope reportaziende → HTTP 400 "Prodotto non attivo, attivalo su console.openapi.com"). Appena attivato, funziona senza modifiche. Response attesa: {status, cf, crediti_utilizzati, schede:{CODE:{nome,tipo,dati}}}.

## Sessione 2026-06 (parte 16) — Info Azienda + autocomplete P.IVA + visibilità tab
- VISIBILITÀ TAB (AnagraficaDetail.jsx): "Raccolta Dati", "Potenti Domande", "Analisi Cliente", "Pensione INPS" ora SOLO per persone fisiche (ana.tipo !== persona_giuridica), trigger + content. Azienda vede "🏢 Analisi Azienda" + "💼 Salute Fiscale".
- AUTOCOMPLETE NUOVO CLIENTE (Anagrafiche.jsx importaAzienda): GET /openapi-it/company?piva= ora usa company.openapi.com (IT-advanced) via svc.company_lookup() → ragione_sociale, indirizzo, comune, provincia, cap, pec, ateco, forma_giuridica, rea, cciaa, stato. (imprese.openapi.it era 406). Fallback ricerca gratuita visurecamerali.
- SCHEDA INFO AZIENDA (AnalisiAziendaTab.jsx riscritto, recharts): panoramica (rag. sociale, ATECO, indirizzo, dipendenti, forma giuridica, fatturato ultimo bilancio) + 4 sotto-tab con torte: Soci/Azionisti (quote%), Governance (torta + tabella amministratori con Rappr. legale), Forza lavoro (dipendenti/costo/trend), Commercio estero (placeholder: dati non in company.openapi.com, arriveranno con Report Aziende). Pulsante "Carica/Aggiorna dati" → POST /openapi-it/company/{aid}.
- Backend: svc.company_lookup(), svc.company_full_completo() (merge IT-full soci/governance/indici + IT-advanced ragione_sociale/indirizzo/bilanci). _normalize_company_co ora espone comune/provincia/cap. POST /company/{aid} salva dati merged in openapi_data.company; backfill ragione_sociale dall'anagrafica.
- "Analisi Azienda approfondita" = da sviluppare in seguito (contenitore esistente).
- Test: testing_agent frontend iteration_70 = 100% (Info Azienda render, visibilità tab PG/PF, autocomplete presente). Backend via curl OK.

## Sessione 2026-06 (parte 17) — Fix pulsante Estrai dati P.IVA + nota tipo azienda
- FIX (Anagrafiche.jsx form nuovo cliente): il pulsante di autocompilazione P.IVA prima era una piccola pill in alto visibile solo dopo 11 cifre → non evidente. Ora: campo P.IVA + pulsante verde "⚡ Estrai dati" sempre visibile per aziende (tipo persona_giuridica), disabilitato finché la P.IVA non ha 11 cifre, con testo di aiuto. Chiama importaAzienda() → GET /openapi-it/company (company.openapi.com).
- NOTA: AUTOTRASPORTI VIVIANI risulta "Persona fisica" perché il record è stato salvato con tipo=persona_fisica (probabile ditta individuale o import). Va corretto manualmente (modifica anagrafica → Tipo → Azienda) oppure valutare estrazione dati anche per persone fisiche con P.IVA (ditte individuali) in futuro.

## Sessione 2026-06 (parte 18) — Regola "P.IVA = persona giuridica" + campi personali nascosti
- REGOLA: ogni anagrafica con Partita IVA è persona_giuridica. Forzata in create_anagrafica e update_anagrafica (routes/anagrafiche.py). Migrazione one-time (tutti i tenant): 681 record con P.IVA convertiti a persona_giuridica (su 1934 totali con P.IVA); backfill ragione_sociale dove mancante (0 necessari). VIVIANI ora persona_giuridica.
- CAMPI PERSONALI NASCOSTI per persona_giuridica (AnagraficaDetail.jsx): vista dettaglio (Data nascita, Sesso, Comune nascita, Professione, Tipo lavoratore, Stato civile, N.figli, Figli a carico, Reddito annuo lordo, Inizio contribuzione, Settimane contributive) filtrati; form modifica: stessi campi + Tipologia lavoratore/Professione/Datore lavoro avvolti in {f.tipo!=="persona_giuridica"}.
- Pulsante "⚡ Estrai dati" ora sempre visibile per aziende accanto al campo P.IVA (disabilitato finché non 11 cifre) con testo di aiuto.

## Sessione 2026-06 (parte 19) — Salute Fiscale da OpenAPI + card OpenAPI in Analisi Azienda + Tipo/PEC
- SALUTE FISCALE da dati strutturati: nuovo POST /anagrafiche/{aid}/salute-fiscale/da-openapi (extras_p1p2.py) → usa company_full_completo (ultimo bilancio con fatturato>0) per compilare ricavi/PN/attivo/costi personale + indicatori (roe/ros da indici, leva=attivo/PN) + score rischio + cross-sell. Pulsante "⚡ Compila da OpenAPI" in SaluteFiscaleTab accanto a "Carica bilancio (OCR)". Testato: OPENAPI SPA 2025 ricavi 5.696.858, PN 1.037.925, leva 2.31.
- Card OpenApiActions SPOSTATA in Analisi Azienda (AnalisiAziendaTab, in cima) per le aziende; nascosta nel tab dati per persona_giuridica.
- Form modifica anagrafica: aggiunto selettore "Tipo anagrafica" (fisica/giuridica) + campo PEC.
- I PDF scaricati (bilancio ottico, visure) restano salvati in allegati con categoria (visura_camerale/bilancio/visura_catastale), visibili in "Altri allegati" con data e multipli file per categoria.
- PENDING (agentic edits da fare): campi Amministratore + Referente azienda (con email/cellulare, autocompilati da import); mostrare solo tab attive; categoria "bilancio" per bilancio-ottico.
