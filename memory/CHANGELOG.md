# Changelog — Axicura CRM

## 2026-11-13 — Disdette: collega polizza sostitutiva (chiudi promemoria con un clic)
- Nuovo endpoint `POST /api/disdette/{id}/collega-polizza`: imposta `polizza_emessa=true` (chiude il promemoria di emissione) e, se passata, collega `polizza_nuova_id`/`polizza_nuova_numero`. Chiamabile anche senza body per la chiusura rapida dalla lista.
- Campi disdetta `polizza_nuova_id` / `polizza_nuova_numero`.
- UI lista: pulsante ✓ "Segna emessa" (un clic) sulle righe non ancora emesse; badge verde "emessa" (con tooltip n. polizza) su quelle collegate.
- UI dialog: riquadro "Polizza sostitutiva emessa" con Select delle polizze del cliente (o numero a mano) che collega la polizza e spunta automaticamente "emessa".
- Verificato via curl: chiusura rapida e collegamento con numero. Frontend compila.


## 2026-11-13 — Modulo Disdette potenziato
- Nuovi campi disdetta: destinatario (nome assicurazione/agenzia, indirizzo, PEC), scadenza polizza, flag "nuova polizza emessa".
- Rubrica destinatari gestita a mano: CRUD `/api/disdette-destinatari`; nel form un Select carica i dati salvati (nome/indirizzo/PEC) e li ripropone.
- Sezione allegati per disdetta (upload/download/delete) — `entita_tipo="disdetta"` abilitato (server.py + db_models Literal).
- Generazione PDF lettera di disdetta/recesso (solo testo, reportlab) via `GET /api/disdette/{id}/pdf`, con escaping dei campi utente.
- Promemoria: oltre all'avviso "invia disdetta in tempo", aggiunto avviso "emetti la nuova polizza" alcuni giorni prima della scadenza polizza (cron giornaliero esistente esteso; env DISDETTE_EMISSIONE_DAYS, default 10; dedup `ultimo_promemoria_emissione`).
- `disdette` e `disdette_destinatari` aggiunte a TENANT_SCOPED_COLLECTIONS (isolamento + auto-assegnazione tenant, necessario al cron).
- Tabella: nuova colonna "Scad. polizza".
- Fix critico UI (post-test): il dialog ora si rimonta ad ogni apertura (key+seq) → niente più campi vuoti/stale in modifica né sovrascrittura del record.
- Testato (testing agent): backend 100%, frontend 100% — create/edit senza data-loss, rubrica, allegati, PDF.


## 2026-11-13 (refine) — Libro Matricola: documenti nel riquadro del veicolo
- La polizza master del Libro Matricola NON ha targa a livello polizza (la targa è sulle applicazioni). Lo scanner ora, se un documento porta una targa (OCR o nome file), cerca l'APPLICAZIONE del tenant per targa, adotta la sua polizza master come entità e imposta `applicazione_matricola_id` → il file appare nei riquadri del veicolo (dialog "Documenti veicolo").
- Cartelle Drive "Libro Matricola applicazioni" / "Certificati assicurativi" ora mappate a `quietanza` → i certificati assicurativi finiscono nella card "Quietanze" del veicolo.
- Regex targa da nome file estesa ai formati Libro Matricola (es. AB00313, AA91159).
- Lookup applicazione scoperto per `agenzia_tenant_id` (lo scanner gira senza contesto-tenant di request).
- Back-fill avvio aggiornato: collega i libretti già importati all'applicazione confrontando la targa del nome file con le targhe reali delle applicazioni della polizza (gestisce anche targhe speciali).
- Verificato con insert reale (tenant c5ae2d0e, targa AA41979): libretto→card Libretto veicolo, certificato→card Quietanze, entrambi collegati all'applicazione d5f6735c.


## 2026-11-13 — Fix libretti/quietanze da Drive + nuova Libreria Targhe
### Bug fix OCR scanner (Drive)
- `cloud_ocr_scanner.py`: i libretti importati da Drive venivano salvati con categoria `libretto_circolazione` → finivano in "Documenti altri" e non nel riquadro "Libretto veicolo". Corretto in `libretto_veicolo` (CAT_MAP + lista visibile_cliente).
- Aggiunto fallback targa dal nome file (es. "LIBRETTO - GY308AK.pdf") per abbinare polizza/applicazione Libro Matricola anche quando l'OCR non legge la targa → risolve anche le quietanze "non archiviate".
- `server.py`: back-fill all'avvio che migra gli allegati legacy `libretto_circolazione` → `libretto_veicolo` e li collega all'applicazione del veicolo (match per targa). Sistema i record esistenti in produzione al prossimo deploy.

### Nuova feature: Libreria Targhe
- Pagina dedicata `/libreria-targhe` (voce menu sezione Assicurazione, icona auto). Ricerca per targa; card con proprietario, dati veicolo, badge Libro Matricola/Libretto.
- Dialog di dettaglio: proprietari (contraente + intestatario), dati veicolo, libretto scaricabile, storico polizze collegate (con compagnia/stato/date) e applicazioni Libro Matricola. Click su polizza → naviga alla scheda.
- Backend `routes/libreria_targhe.py`: `GET /api/librerie/targhe` (lista+ricerca), `/{targa}` (dettaglio), `/lookup/{targa}` (suggerimento rapido). Tenant-isolato via TenantAwareDB. Campi data corretti (`effetto`/`scadenza`), limit max 200, include la polizza master Libro Matricola.
- Suggerimento in creazione polizza: digitando una targa già in libreria compare un banner "Libretto già in archivio" con link al libretto, così non va ricaricato.
- Testato (testing agent, tenant reale jacopo@schiantarelli.it): 8289 targhe, ricerca, dettaglio, download libretto (200 PDF), banner suggerimento su FB828CV. Fix post-test: date polizze, link SPA, clamp limit, polizza master LM.


## 2026-11-12 — Documenti collaboratori: filtro "Mostra disattivati"
- **Richiesta**: nascondere di default i collaboratori disattivati, con un interruttore per mostrarli.
- **Backend** (`GET /api/collaboratori/documenti-annuali`): nuovo parametro `includi_inattivi` (default false). Di default la query admin esclude `attivo == False`; con `includi_inattivi=true` li include. Il campo `attivo` è ora restituito per ogni collaboratore.
- **Frontend** (`DocumentiAnnualiCollab.jsx`): interruttore "Mostra collaboratori disattivati" (`data-testid="toggle-inattivi"`) accanto alla ricerca; i disattivati mostrano un badge grigio "Disattivato".
- **Verifica API**: default 3 collaboratori (nasconde Sara disattivata di test), con toggle 4 (Sara con `attivo=false`); stato ripristinato dopo il test.


## 2026-11-12 — Documenti collaboratori: isolamento per tenant
- **Bug**: la sezione "Documenti collaboratori" (Librerie → documenti annuali) elencava i collaboratori di TUTTI i tenant, perché la collezione `users` è condivisa (non tenant-scoped) e l'endpoint non filtrava per agenzia.
- **Fix** (`server.py` · `GET /api/collaboratori/documenti-annuali`): la query admin ora filtra `is_super_admin != True` e `agenzia_tenant_id == user_tenant_id(user)`, come `GET /auth/users`. Il super-admin continua a vedere tutti i tenant.
- **Verifica**: admin tenant-principale ora vede 4 collaboratori del proprio tenant (prima comparivano anche utenti di altri tenant).


## 2026-11-12 — Documenti veicolo (libro matricola): card per categoria + routing Drive/inbox corretto
- **Richiesta utente**: nel modale "Documenti veicolo" i documenti non venivano mostrati DENTRO le card (come nelle altre sezioni) e i file smistati da Drive/inbox (libretto, quietanze…) finivano in "altro" invece che nella card giusta.
- **Frontend** (`components/LibroMatricolaTab.jsx` · `DocsAppDialog`, `pages/LibroMatricolaPage.jsx` · `DocsApplicazioneDialog`): il modale ora usa `layout="quadrotti"` di `DocumentiSezioneSplit` con chiavi categoria canoniche (`libretto_veicolo, quietanza, atto_vendita, polizza, condizioni, appendici, mup, questionario, regolazione, preventivo, appunti, altri`). I file sono mostrati dentro ogni card, come in PolizzaDetail.
- **Backend** (`routes/documenti_inbox.py` · `DOC_ROUTING`): aggiunti alias per i `tipo_documento` prodotti dal cloud OCR scanner — `libretto_circolazione → libretto_veicolo`, `denuncia_sinistro → denuncia`, `privacy → privacy_firmata`, `rid → mandato_sdd`. I nuovi documenti smistati finiscono nella card corretta.
- **Back-fill idempotente** (`server.py` startup, cross-tenant via `raw_db`): ricategorizza gli allegati già smistati da inbox finiti in `altro`/`altri` leggendo il tipo dalla descrizione `Documenti inbox (<tipo>)`. In preview: 49 allegati ricategorizzati. In produzione viene eseguito automaticamente al prossimo publish/deploy.


## 2026-11-12 — Compagnie: dati anagrafici/fiscali completi + sezione allegati · 4 sezioni spostate in Librerie
- **Richiesta utente**: (1) nella scheda Compagnie (editor dentro Librerie) poter inserire TUTTI i dati compagnia + una sezione Allegati come per Agenzia Partner; (2) spostare dentro la pagina Librerie le sezioni WhatsApp Agenzie, Agenzie (partner), Setup iniziale, Scambio dati agenzie, rimuovendole dal menù a sinistra.
- **Backend** (`db_models.py` · modello `Compagnia`): aggiunti campi `indirizzo, cap, citta, provincia, partita_iva, codice_fiscale, iban, pec, note`. POST/PUT `/compagnie` li persistono; allegati via endpoint esistenti `POST/DELETE /compagnie/{cid}/documenti`.
- **Frontend `Librerie.jsx`** — `CompagniaForm`: nuovi campi anagrafici/fiscali + sezione "Documenti / Allegati" (componente `DocumentiCompagnia`, `DocCardsScadenza` cardKey="compagnia", come agenzia partner), con `omitOnSave=["documenti","logo_storage_path","logo_mime"]`.
- **Frontend `Librerie.jsx`** — `EXTRA_SECTIONS` role-gated: 4 nuove schede (`agenzie-partner`, `setup-iniziale`, `scambio-dati` solo admin; `whatsapp-agenzie` admin+collaboratore) che renderizzano i componenti pagina esistenti `Agenzie`, `SetupIniziale`, `ScambioDati`, `WhatsAppInstances`.
- **`Sidebar.jsx`**: rimosse le 4 voci (agenzie, setup_iniziale, scambio_dati, whatsapp). Rotte originali mantenute in `App.js` per i deep-link.
- **Fix**: `Sezione` dialog `onOpenChange` ora chiama `load()` anche alla chiusura con X/Escape, così la lista allegati non resta stale al riapri.
- **Test**: testing agent (iteration_135) — 6/6 scenari frontend PASS; backend nuovi campi verificati via curl.


## 2026-11-09 — Titoli: i titoli arretrati/coperti della polizza ora compaiono sempre nell'elenco Titoli
- **Problema utente**: un titolo "da incassare" presente nella polizza non compariva cercandolo nella sezione Titoli ("Nessun risultato"). Richiesta: TUTTI i titoli con stato arretrato/coperto presenti in polizza devono essere visibili in Titoli (indipendentemente dai Carichi).
- **Causa**: quei titoli erano carichi mensili con `stato_carico="in_attesa"`; l'endpoint `/titoli` li escludeva (`stato_carico $nin [in_attesa, annullato_carico]`), quindi non comparivano nell'elenco né nella ricerca.
- **Fix** (`server.py`):
  - `list_titoli`: esclusione cambiata in `stato_carico != "annullato_carico"` → i carichi mensili `in_attesa` (importi reali da incassare) ora compaiono tra i Titoli; restano nascosti solo i carichi esplicitamente annullati.
  - `get_polizza`: rimossa l'esclusione dei titoli `in_attesa` dal dettaglio polizza (ora anch'esso esclude solo gli annullati) → piena coerenza tra polizza e Titoli.
- **Verifica (preview, polizza 730105336)**: ricerca "730105336" in Titoli (tutti da incassare) → prima 0, ora **2** titoli da_incassare; dettaglio polizza continua a mostrare tutti i 16 titoli (14 incassati + 2 da incassare).
- **Nota**: i carichi `in_attesa` restano visibili anche in "Carichi mensili"; la validazione resta disponibile ma non è più un prerequisito per vederli in Titoli.
- **Deploy**: attivo in produzione dopo "Save to Github".



## 2026-11-09 — Fix: errore "Configurazione automatica cartelle non riuscita" (provider gmail)
- **Sintomo (produzione)**: toast "Configurazione automatica cartelle non riuscita: String should match pattern '^(google_drive|onedrive)$'" nella pagina Librerie → Cloud Storage.
- **Causa**: dopo l'aggiunta della connessione Gmail OAuth dedicata, l'endpoint `status` restituisce anche una connessione `provider="gmail"`. Il frontend `CloudStorageSezione.maybeAutoInit` iterava su TUTTE le connessioni collegate e chiamava `/cloud-storage/init-structure` anche per `gmail`, ma l'endpoint accetta solo `google_drive|onedrive` → errore di validazione. Il Drive era comunque collegato correttamente (nessun problema di credenziali).
- **Fix** (`Librerie.jsx`): l'auto-init della struttura cartelle ora gira SOLO per i provider di archiviazione (`google_drive`, `onedrive`); la connessione Gmail viene ignorata.
- **Nota deploy**: fix in preview; attivo in produzione dopo "Save to Github".



## 2026-11-09 — Avvisi "Invia in AUTOMATICO": invio MULTICANALE a tutti i canali preferiti
- **Richiesta utente**: se in anagrafica sono spuntati più "Canali preferiti avvisi" (es. Email + WhatsApp), l'invio automatico deve partire su TUTTI, non solo sul primo.
- **Prima**: `/avvisi/invia-bulk-auto` sceglieva UN SOLO canale per cliente (il primo attivo secondo la priorità) e si fermava lì.
- **Fix** (`server.py`): ora costruisce la lista di TUTTI i canali attivi con recapito (`canale_whatsapp`/`canale_email`/`canale_sms` + cell/email presenti) e invia su ciascuno; esito/errori tracciati per canale.
  - Email: passa prima da **Gmail API (OAuth agenzia)** via `gmail_send.send_tenant_email`, con fallback SMTP; rimosso il gate `smtp_host` che impediva l'email ai tenant che usano solo Gmail OAuth.
- **Frontend** (`Avvisi.jsx`): messaggio di conferma aggiornato ("verranno usati TUTTI i canali preferiti attivi … riceverà l'avviso su ciascuno").
- **Verifica (preview)**: contraente di test con Email+WhatsApp → entrambi i canali tentati (CANALI TENTATI: ['email','whatsapp']); prima ne partiva uno solo. Gli errori di consegna sono dovuti a Evolution/Gmail non collegati in preview per il destinatario fittizio; in produzione (canali collegati) partono realmente. Dati di test rimossi.
- **Nota deploy**: attivo in produzione dopo "Save to Github".



## 2026-11-09 — Avvisi di scadenza: filtro per data rata, titoli in arrivo e filtro stato (arretrati/coperti/tutti)
- **Problema utente**: (a) il filtro Dal/Al doveva mostrare solo i titoli con la DATA RATA nel range; (b) un titolo RC Auto (polizza 183629579, rata 29/11, "da incassare") non compariva negli Avvisi nemmeno senza date; (c) serviva un filtro stato (tutti / solo coperti / solo arretrati).
- **Causa**: la query titoli (`avvisi_scadenze._query_titoli_arretrati`) includeva SOLO titoli con `effetto < oggi` (già scaduti). I titoli "da incassare" con data rata **futura** (es. 29/11) venivano esclusi a monte, quindi nessun filtro poteva mostrarli. Il filtro Dal/Al già agiva sulla data rata (il record formatta `scadenza = effetto`), ma su un dataset incompleto.
- **Fix backend** (`avvisi_scadenze.py` + `server.py`):
  - Nuova query `_query_titoli_avvisi` con finestra sulla **data rata (effetto)**: se `dal`/`al` → effetto nel range; altrimenti effetto ≤ oggi+giorni (scaduti + prossime rate nel periodo).
  - Filtro stato a 3 vie (`_filtro_stato_titoli`): `arretrati` (da incassare/insoluto, non coperti), `coperti` (titolo_coperto, non incassati/stornati), `tutti` (tutti i pendenti).
  - `cerca_scadenze(..., dal, al, stato)` parametrizzata; il job email resta invariato (stato=None → solo scaduti).
  - Endpoint `/avvisi-scadenze/preview`: nuovo param `stato_titoli` (default `arretrati`); il filtro data rata è applicato nella query.
- **Fix frontend** (`Avvisi.jsx`): aggiunto select **"Stato titoli"** (Solo arretrati / Solo coperti / Tutti) nei filtri, inviato come `stato_titoli`.
- **Verifica (preview)**: inserito un titolo di prova analogo (effetto futuro 29/11/2026, da incassare, 906,50) → compare sia nella vista default (60gg) sia nel range 01–30/11; filtro `coperti` lo esclude, `tutti` lo include; poi rimosso. Il titolo reale dell'utente esiste solo in produzione (in preview c'è la quietanza 2025 incassata), quindi dopo il deploy comparirà.
- **Nota deploy**: attivo in produzione dopo "Save to Github".



## 2026-11-09 — Tutte le date su fuso Europe/Rome + formato gg/mm/aaaa
- **Richiesta**: tutte le date in ora di Roma e visualizzate come gg/mm/aaaa, in tutto il programma.
- **Backend**: nuovo helper centrale `tzutil.py` (`oggi_italia()` = data odierna Roma, `adesso_italia()` = datetime Roma naive, `fmt_it()` = gg/mm/aaaa). Sostituiti ~60 usi di `date.today()` / `_date.today()` / `datetime.now()` (server.py + routes dashboard/kpi/anagrafiche/cumulativa/mup/modelli/firma/regolazione/comunicazioni/documenti + tutti i `pdf_*` + inps_calculator + sollecito_veicoli) con le versioni in ora italiana. `avvisi_scadenze` e lo `scheduler_alert` erano già su Roma.
  - Nota tecnica: le funzioni sono state nominate `oggi_italia`/`adesso_italia` per evitare lo shadowing con la variabile locale `oggi` usata in molte funzioni (sarebbe stato UnboundLocalError).
- **Formato stampa**: nei PDF/export le date stampate passano da `gg-mm-aaaa` a **gg/mm/aaaa** (pdf_avviso/avvisi/brogliaccio/lettera_abbuono, brogliaccio, libro_matricola, server, cumulativa, import_*).
  - **Attenzione preservata**: i parser input (`strptime`) in import_massivo/import_anagrafiche/cumulativa/libro_matricola continuano ad accettare sia `gg-mm-aaaa` sia `gg/mm/aaaa` (ripristinato `%d-%m-%Y` nelle liste formati — regressione verificata).
- **Frontend**: già conforme — patch globale `lib/timezone.js` forza `it-IT` + `Europe/Rome` su tutte le `toLocaleDateString/Time/String` (→ gg/mm/aaaa in ora di Roma) e `lib/api.js fmtDate` idem. Nessuna modifica necessaria.
- **Verifica (preview)**: avvio backend pulito; endpoint dashboard/titoli/anagrafiche + PDF saldi-cassa + export CSV = 200; `oggi_italia()` = data Roma, `fmt_it` = gg/mm/aaaa; parsing `09-11-2026` e `09/11/2026` entrambi OK.
- **Nota deploy**: attivo in produzione dopo "Save to Github".



## 2026-11-09 — Alert: fix segnaposto {cliente}, riarmo scheduler al cambio orario, ora Roma
- **Bug segnaposto `{cliente}`** (WhatsApp/email mostravano "Gentile {cliente}," letterale): il context di rendering esponeva solo `nome`/`cliente_nome`, non `cliente`. Fix in `alert_dispatcher.dispatch_rule`: aggiunti alias `cliente`, `nome_cliente` (= nome cliente) prima di `render_template`. Verificato: corpo → "Gentile Mario Rossi, …".
- **Bug "Esegui ora funziona ma col solo orario no"**: il tick imposta `last_run_date=oggi` alla prima esecuzione giornaliera (idempotenza 1 run/giorno), quindi cambiando l'orario per ritestare la regola veniva saltata fino al giorno dopo; "Esegui ora" invece bypassa `last_run_date`. Fix in `routes/alert.py`: al salvataggio dell'orario (`cron`) e alla riattivazione (toggle ON) si azzera `last_run_date` → la regola si ri-arma e può scattare al nuovo orario anche in giornata. Verificato.
- **Ora Roma**: lo scheduler avvisi era già `Europe/Rome`; allineato anche `avvisi_scadenze._today()` (prima `date.today()` = UTC in produzione) a `Europe/Rome`. Restano `date.today()`/`datetime.now()` in alcuni endpoint dashboard e nei PDF (data stampata): impattano solo nella fascia a cavallo di mezzanotte; sweep completo disponibile su richiesta.
- **Nota deploy**: fix attivi in produzione dopo il prossimo "Save to Github".



## 2026-11-09 — Import OMNIA: crea il titolo in ARRETRATO per polizze nuove/sostituenti
- **Richiesta utente**: all'import del flusso OMNIA, per le polizze NUOVE o SOSTITUENTI, oltre a popolare Premi e Provvigioni creare anche il TITOLO con gli stessi dati, lasciato in arretrato; date del titolo = esattamente quelle della polizza.
- **Contesto**: dal 2026-10 l'import OMNIA era stato disattivato dal creare titoli (nascono dai Carichi mensili); unica eccezione lo storno del titolo della polizza vecchia in sostituzione.
- **Implementazione** (`ania_importer.py`):
  - `_upsert_polizza` ora raccoglie gli id delle polizze INSERITE in questo import (`created_ids`) → identifica il new business.
  - Nuova `_crea_titoli_import(...)` chiamata in `importa_zip` dopo l'allineamento scadenze: per ogni polizza NUOVA o con `sostituisce_polizza`, operativa e con lordo>0, crea 1 titolo `stato="da_incassare"`, `titolo_coperto=False`, `tipo` = "sostituzione"/"nuova", **effetto/scadenza = date della polizza**, importi (lordo/netto/imposte/SSN/provvigioni) e `provvigioni_operatori`/`collaboratore_id` identici alla polizza, `fonte="import_ania"`.
  - **Idempotente**: salta se esiste già un titolo per quella polizza alla stessa data di effetto (nessun doppione al re-import). I rinnovi (polizze aggiornate, non nuove) restano esclusi.
- **Verifica (preview, tenant isolato, 6/6 PASS)**: titolo creato solo per nuova+sostituente (rinnovo escluso); date=polizza (09/11/2026→09/11/2027), stato arretrato, non coperto; importi/provvigioni/ripartizione = polizza; tipo nuova/sostituzione corretto; re-import senza doppioni; polizza annullata → nessun titolo.
- **Nota deploy**: attivo in produzione dopo il prossimo "Save to Github".



## 2026-11-09 — UX: scroll con rotellina del mouse nei dropdown con ricerca (globale)
- **Richiesta utente**: oltre alla ricerca, poter scorrere TUTTE le voci col mouse in ogni menù a tendina del programma (es. "Tipo pagamento" in Incasso/Copertura).
- **Causa**: i dropdown (`Select` e `SearchableSelect`) sono basati su `cmdk` e, quando aperti dentro un modale (Dialog con blocco-scroll `react-remove-scroll`), la rotellina veniva bloccata perché il popover è in un portale esterno al Dialog. Ricerca e click funzionavano, lo scroll col mouse no.
- **Fix (1 solo punto, `components/ui/command.jsx` → `CommandList`)**: aggiunto un listener `wheel` NON passivo sull'elemento lista che fa `preventDefault` + scroll manuale (`scrollTop += deltaY`), con guardie a inizio/fine corsa per non "rubare" lo scroll alla pagina. Vale ovunque (Select, SearchableSelect, command palette).
- **Verifica (preview, modale Incasso/Copertura, tenant reale)**: dropdown "Tipo pagamento" con `scrollHeight 608 > clientHeight 300` → eventi wheel spostano la lista `scrollTop 0 → 150 → 300`. PASS.
- **Nota deploy**: attivo in produzione dopo il prossimo "Save to Github".



## 2026-11-09 — FIX: "Documento d'identità in scadenza" non inviava (match esatto → range)
- **Sintomo utente**: documento (CI) in scadenza OGGI, regola ATTIVA, ma nessun invio email/WhatsApp (né con "Esegui ora").
- **Root cause** (`scheduler_alert._res_documento_id_in_scadenza`): il resolver cercava `ci_data_scadenza == oggi + soglia_giorni` (match ESATTO; soglia vuota → default 30). Un documento che scade OGGI (0 giorni) non combaciava mai con "oggi+30" → 0 destinatari → niente in coda. La dashboard invece usava già un range `$gte oggi / $lte +30`, da cui il documento appariva "in scadenza" ma l'alert non partiva.
- **Fix**: match su finestra `[oggi … oggi+soglia]` (default 30gg), con **idempotenza per-documento** (`ci_avviso_scad_inviato_per` = data scadenza): avvisa UNA sola volta per quella scadenza, niente spam quotidiano finché il documento resta nella finestra; si riavvisa solo al rinnovo. Marker scritto in `_esegui_rule` solo se qualcosa è stato inviato/accodato.
- **Verifica (preview, tenant isolato, 5/5 PASS)**: doc che scade oggi → accodati email+whatsapp; marker scritto; seconda esecuzione non riaccoda; doc a +10gg dentro finestra (accodato); doc a +60gg fuori finestra (niente).
- **Nota deploy**: attivo in produzione solo dopo deploy. Per la consegna reale servono comunque Gmail OAuth collegato e istanza WhatsApp aperta (segnalati dalla Diagnostica avvisi).



## 2026-11-09 — Alert & Automazioni: validazione conformità (controllo rigido attivo:true + per-regola)
- **Richiesta**: validazione finale + rilascio del controllo rigoroso degli alert.
- **Test di conformità eseguiti su DB locale (tenant isolato, con cleanup) — 7/7 PASS**:
  1. Regola `active:false` → `dispatch_rule` esce subito (`not rule.attivo`), stats tutti 0, **comm_queue resta VUOTA**.
  2. Regola `active:true` → accodati 2 item (email+whatsapp) in `comm_queue` stato `pending`, con `rule_id`+`rule_nome` tracciati correttamente.
  3. `dispatch_evento` su regola spenta → `matched=0`, nessun accodamento.
  4. Scheduler: regola `schedule` ATTIVA ma **senza cron resta in attesa** (non eseguibile); `_cron_due` TRUE per l'orario corrente e FALSE per +40min.
  5. Scheduler usa fuso `Europe/Rome` (verificato `ROME_TZ.key` + `_now_rome()`).
- **Rate-limiting**: enqueue confermato; il throttling 5-10s/tenant e retry/backoff restano in `comm_queue._drain_tenant` (worker per-agenzia).
- **Commit locale pronto al deploy**: `477609e`. Push su GitHub/Railway via "Save to Github" (azione utente).



## 2026-11-05 — Fix VISION360: set-folder ora auto-adotta la connessione legacy (split-tenant) + logging stdout/stderr
- **Sintomo utente**: "jacopo@schiantarelli.it collegato al Drive, ho scelto la cartella VISION360 ma non si popola con INBOX e Archivio".
- **RCA produzione (deployer)**: in `cloud_connections` esisteva UN SOLO doc `google_drive` intestato al tenant legacy `tenant-principale-schiantarelli` (folder_name "Assicura CRM"); per il tenant attivo `c5ae2d0e-283e-4513-aaf2-cbd97ef62d78` NESSUNA connessione (count 0). Lo switch a VISION360 non è mai stato persistito.
- **Root cause nel codice**: `set_folder` (pulsante "Scegli cartella") faceva `update_one({tenant_attivo})` → `matched_count==0` → HTTPException 404 "Account non collegato". Il self-heal (`_adopt_legacy_connection`) era invocato SOLO dentro `_init_structure_for_tenant` (endpoint init-structure / "Riorganizza"), MAI in `set_folder`. Quindi scegliendo la cartella custom l'utente otteneva un 404 silenzioso e la struttura non veniva creata.
- **Fix** (`routes/cloud_storage.py` → `set_folder`): prima dell'update, se non esiste connessione per il tenant attivo, chiama `_adopt_legacy_connection(provider, tenant)` per re-intestare la connessione legacy (connessione + cache + scan history + inbox) al tenant attivo. Dopo l'adozione, l'update imposta `folder_id`=VISION360, `root_is_custom=True`, invalida la cache e crea INBOX+Archivio nella cartella custom.
- **Verifica (preview, Drive reale)**: simulato lo stato di produzione (connessione solo su legacy, 0 per tenant attivo) → creata cartella test "VISION360 TEST" nel Drive → `set_folder` come tenant attivo → connessione adottata su c5ae2d0e con folder=VISION360, e nel Drive sono comparse `INBOX` + `Archivio` dentro la cartella custom. Cleanup: cartella test cestinata, DB preview ripristinato.
- **Logging** (`server.py`): root logger con handler separati — DEBUG/INFO → `sys.stdout` (azzurri su Railway), WARNING/ERROR → `sys.stderr` (rossi). Aggiunto import `sys`. Verificato in preview.
- **Nota deploy**: entrambi i fix sono attivi in produzione SOLO dopo nuovo deploy. Dopo il deploy, jacopo deve rifare Librerie → Cloud Storage → "Scegli cartella" → VISION360 per popolarla.


## 2026-11 — Drive = archivio digitale COMPLETO del CRM (INBOX + ARCHIVIO)
- **Richiesta utente**: "IL DRIVE DEVE ESSERE IL MIO ARCHIVIO DIGITALE DI TUTTI I DOCUMENTI DEL CRM", con cartella principale INBOX (ingresso OCR) + cartella principale ARCHIVIO (documenti lavorati, con Contabilità). Archiviare anche i PDF firmati digitalmente e i documenti di trattative/titoli/disdette.
- **Struttura cartelle** (`routes/cloud_storage.py` → `STANDARD_FOLDER_STRUCTURE`): tutte le destinazioni d'archivio spostate sotto `Assicura CRM/Archivio/...` (Anagrafiche, Polizze, Sinistri, Trattative, Titoli, Disdette, Documenti Firmati, Altri documenti, Quietanze, Contabilità). `INBOX` resta dedicata al solo ingresso. `Contabilità` con sottocartelle Prima Nota, Estratti Conto Compagnie, Estratti Conto Collaboratori (create al setup). `INIT_CATEGORIES` aggiornato.
- **Mirror universale** (`cloud_doc_sync.py`): `_ENTITY_CATEGORY` esteso (trattativa, titolo, disdetta, applicazione_matricola) + fallback `_DEFAULT_ENTITY_CATEGORY` → qualsiasi entità non mappata finisce in "Altri documenti": nessun documento viene mai saltato. Backfill e `sync-status` ora includono TUTTI i tipi di entità (rimosso filtro `_entita`).
- **PDF firmati** (`routes/esignature_it.py` → `_finalizza`): il documento firmato viene mirrorato subito su Drive (best-effort) e marcato `pending_sync` come rete di sicurezza.
- **Sweep periodico** (`server.py` + `.emergent/crons.yml`): nuovo cron `POST /api/cron/cloud-archive-sweep` ogni 30 min → backfill `include_all` per ogni tenant collegato, così ogni documento creato da QUALSIASI flusso raggiunge il Drive.
- **Migrazione tenant** (`routes/cloud_storage.py` → `POST /migrate-tenant`): consolida il collegamento Drive/OCR da un tenant legacy (default `tenant-principale-schiantarelli`) al tenant ATTIVO dell'admin, aggiornando `tenant_id` + `agenzia_tenant_id` su cloud_connections/cloud_folder_cache/cloud_scan_history/documenti_inbox. Idempotente, con dry_run; rifiuta se il tenant attivo ha già una connessione. Pulsante frontend "Recupera collegamento" (`Librerie.jsx`) visibile solo quando l'agenzia non ha Drive collegato.
- **Test**: 35 categorie risolvono tutte sotto Archivio; entity mapping+fallback validi; logica migrazione verificata su dati sintetici; endpoint sync-status/migrate-tenant testati via curl; pagina Cloud Storage renderizza senza errori.
- **Nota produzione**: la migrazione effettiva dello split tenant va eseguita sull'app LIVE (il preview è un mirror) — jacopo@schiantarelli.it: Librerie → Cloud Storage → "Recupera collegamento". I documenti già archiviati nelle vecchie cartelle in radice restano dove sono (scelta utente "defaults"); i nuovi vanno sotto ARCHIVIO.


## 2026-06 — Voci manuali collaboratore: CRUD libero a Prima Nota chiusa
- **Richiesta utente**: creare/modificare/eliminare una voce manuale nell'Estratto conto collaboratore anche con Prima Nota chiusa (la voce entra in Prima Nota solo col pagamento dell'estratto).
- **Backend** (`server.py`): rimosso `assert_giornata_aperta` da `delete_voce_manuale_collab`; nuovo endpoint `PUT /collaboratori/{cid}/voci-manuali/{vid}` (data/causale/importo/note) senza blocco giornata. Entrambi restano bloccati solo se la voce è già `pagata`.
- **Frontend** (`Provvigioni.jsx`): pulsante Modifica (matita, `edit-voce-{id}`) accanto a Elimina; `NuovaVoceDialog` ora supporta la modalità modifica (prefill + PUT).
- **Verifica**: API create/edit/delete su data 2026-11-03 (Prima Nota chiusa) OK; smoke UI → dialog "Modifica voce manuale" precompilato correttamente.

- **Bug utente**: modificando la provvigione del collaboratore nel titolo (ripartizione `provvigioni_operatori`), l'Estratto conto collaboratore NON la mostrava: ricalcolava sempre la quota dallo schema provvigionale (es. 4,5%), ignorando il valore salvato sul titolo.
- **Scelta utente**: l'estratto deve mostrare ESATTAMENTE la provvigione riportata sul titolo (a mano o da schema, non cambia), **ma solo per i titoli modificati d'ora in avanti** (lo storico importato resta calcolato da schema).
- **Fix** (`server.py`, `db_models.py`):
  - nuovo campo `Titolo.provv_collab_override: bool` (default False).
  - `create_titolo`/`update_titolo` impostano `provv_collab_override=True` quando il body porta `provvigioni_operatori` non vuoto (ogni salvataggio dalla scheda titolo).
  - helper `_titolo_override_quota(t, cid)`: se il titolo ha l'override, ritorna la quota del collaboratore da `provvigioni_operatori`; altrimenti None → fallback schema `_provv_breakdown`.
  - `estratto_provvigioni` (colonna Provvigione, totale e % del collaboratore) e l'endpoint di **pagamento provvigioni** (calcolo del lordo da pagare) usano l'override quando presente. L'export estratto usa la stessa funzione → coperto.
- **Verifica** (in-process, tenant reale c5ae2d0e): titolo con override → estratto mostra il valore del titolo (100,80) invece dello schema (1,84); titoli senza flag → invariati (schema). Smoke test API endpoint 200, 30 righe. Retrocompatibile sui ~51k titoli storici (nessun flag).


## 2026-11 — Ritenute/PNC/Rappel solo mandato diretto, descrizione auto + promemoria disdette + titolo import multi-operatore
- **Filtro mandato diretto** in Ritenute Compagnia, PNC e **Rappel**: helper condiviso `isCompagniaDiretta` (`lib/api.js`). Una compagnia è "diretta" (quindi visibile) SOLO se mandato diretto e NON collegata ad agenzie partner (`agenzia_partner_id`/`agenzie_partner_ids` vuoti). Le compagnie in **collaborazione o legate a un'agenzia partner (es. REDION) spariscono automaticamente**, senza interruttori manuali — gestito dal collegamento agenzia partner. Verificato su dati reali (8 dirette visibili, 5 collaborazione/partner escluse).
- **Descrizione ritenuta auto-compilata**: "RITENUTA <COMPAGNIA> DEL <GG-MM-AAAA>" da compagnia+data selezionate, ma **sempre modificabile** (una volta editata a mano non viene più sovrascritta). `RitenuteCompagnia.jsx`.
- **Promemoria disdette (solo agenzia)**: cron `POST /api/cron/disdette-reminder` (protetto WEBHOOK_CRON_SECRET) + `.emergent/crons.yml` daily 08:00. Avvisa SOLO gli utenti admin del tenant (mai il cliente) per le disdette da_inviare in scadenza entro 5 gg (notifica in-app, dedup giornaliero via `ultimo_promemoria`).
- **Titolo da import, multi-operatore**: il titolo auto-generato in import eredita anche `provvigioni_operatori` dalla polizza (prima solo totale).
- Testing iteration_128: 4/4 feature PASS (banner Trattative, auto-titolo update/import, descrizione auto+editabile, filtro mandato diretto).


- **Trattative board, riepilogo valore**: la board Trattative in /pipeline mostra in cima due card "Trattative aperte" (somma premio_proposto di aperta/proposta_inviata/in_attesa) e "Trattative vinte". Backend: `riepilogo` nel branch trattative di `pipeline_data`; frontend: banner in `Pipeline.jsx` (data-testid trattative-riepilogo).
- **Titolo automatico con gli stessi importi**:
  - `update_polizza` (`server.py`): se si compilano Premi/Provvigioni su una polizza SENZA titolo (tipico di polizze importate o di sostituzione i cui dati economici si inseriscono dopo), genera il primo titolo con gli stessi importi (lordo/netto/imposte=tasse+imposte/ssn/accessori/provvigioni + ripartizione operatori). Guardie: premio_lordo>0, nessun titolo esistente, stato attivo. Verificato via API.
  - Import massivo (`routes/import_massivo.py`): pass post-import che, per le polizze del batch con premi ma ZERO titoli (file con sole righe polizza), genera il titolo con gli stessi importi. Se il file conteneva già righe titolo → nessun duplicato. (`stats.titoli_auto_generati`).


- **Pipeline**: aggiunte board builtin **Trattative** e **Disdette** (kanban drag per stato). Move via `/pipeline/{trattative|disdette}/{id}/move`; branches in `pipeline_data`. Testato (iteration_127, 5/5).
- **Modulo Disdette** (`/disdette` + sidebar): CRUD in `routes/commerciale.py` (collection `disdette`) + pagina `Disdette.jsx` con KPI, badge avviso scadenza (≤15gg / scaduta), create/edit/delete.
- **Sinistri opt-in**: board Sinistri parte vuota con gate + pulsante "Popola automaticamente" (conferma), scelta persistita in localStorage (`pipeline_sinistri_attiva`).
- **Diario chat**: voci WhatsApp aprono vista chat a bolle (`WhatsAppChatPreview`) via "Apri chat" (diario-chat-dialog).
- **FIX Tipo titolo** (`DialogIncassoCopertura.jsx` + `TitoloDialog.jsx`): aggiunti "Sospensione" e "Sostituzione".
- **FIX barra OCR** (`Polizze.jsx` "Riconoscimento polizza"): `OcrProgressBar` spostato fuori dalla toolbar flex su riga full-width così torna visibile durante l'OCR.
- **NON implementato (prossimo task)**: alla creazione di polizza NUOVA da importazione o di SOSTITUZIONE, generare automaticamente il titolo con gli stessi importi di Premi (netto/imposte/ssn/lordo) e Provvigioni.

## 2026-11 — Prima Nota (manuale), Diario documenti, Pipeline cards & Trattative↔Polizza
- **Prima Nota — registrazione manuale (FIX)**: un nuovo movimento manuale in ENTRATA con categoria "Incasso premio" e NESSUNA polizza/titolo collegato ora popola SOLO la colonna banca/cassa/assegni corrispondente al tipo di pagamento. Prima l'importo compariva duplicato anche in "Totale" e "Saldo". Fix in `server.py::_compute_brogliaccio` (nuovo ramo per entrata/incasso_premio senza polizza/titolo).
  - Aggiunto inoltre un resolver NON distruttivo (`_resolve_conto`) che, se il `conto_cassa_id` del movimento non appartiene al tenant (es. tipo-pagamento con conto_id stantio), rimappa in visualizzazione sul conto del tenant il cui nome compare nell'etichetta del mezzo (es. "BONIFICO BPER SONDRIO" → "BPER Sondrio", "CONTANTI" → "Cassa Contanti"). Risolve il caso in cui l'importo finiva in una colonna invisibile.
- **Diario cliente — documenti scaricabili/visualizzabili**: le voci del diario ora espongono `v.documenti[]` (nome, url, content_type, size, fonte) da 3 fonti: allegati manuali, allegati EMAIL (`email_inbox.attachments` via `/storage/...`), media WHATSAPP (`/whatsapp-evo/messages/{id}/media`). Frontend: componente `DiarioDocLink` in `AnagraficaDetail.jsx` (riga diario + dialog dettaglio). `imap_poller` ora salva `payload.email_inbox_id` nella voce diario email.
- **Pipeline — card ricche** (`server.py` + `Pipeline.jsx` + `db_models.PipelineCard`): le card delle pipeline custom supportano ora collegamenti a Polizza/Sinistro/Cliente (ricerca), checklist (aggiungi/spunta/rimuovi), note e allegati (object storage, `entita_tipo="pipeline_card"`). Badge checklist e indicatori pol./sin. sulla board. Nuovo endpoint `GET /pipelines/{pid}/cards/{card_id}`.
- **Trattative ↔ Polizza** (`routes/commerciale.py` + `Trattative.jsx` + `PolizzaDetail.jsx`): la trattativa ha ora `polizza_id`, allegati (`entita_tipo="trattativa"`) e invio preventivo via Email/WhatsApp (`POST /trattative/{tid}/invia`). La PolizzaDetail (tab Documenti) mostra la sezione "Trattative collegate" con note + documenti scaricabili.
- **Fix collaterali (testing agent)**: `db_models.Allegato` Literal esteso con `pipeline_card`/`trattativa`; rimosso `<SelectItem value="">` (crash Radix) nel dialog Trattativa.
- **Testing**: brogliaccio verificato via API (manuale → solo colonna banca; remap BPER/Contanti OK); testing_agent iteration_126: Trattative, Polizza trattative collegate, Diario chips, Pipeline cards OK.
- **NON ancora implementato (richieste pipeline da completare)**: modulo DISDETTE con avviso; Trattative/Preventivi come board kanban dentro Pipeline; Sinistri pipeline con popolamento automatico opt-in (pulsante di conferma); rimozione/disattivazione delle pipeline automatiche builtin; restyling "bello" del Diario e vista chat.


## 2026-06 — Ripartizione provvigioni: scende automaticamente nel titolo
- **Richiesta utente**: la ripartizione provvigioni per collaboratore impostata sulla polizza (secondo il profilo provvigionale) deve comparire automaticamente anche nel titolo, senza aprire il dialog e premere "Eredita da polizza".
- **Backend** (`server.py`):
  - Nuovo helper `_ripartizione_titolo_da_polizza(pol, provv_tot)` che mappa `provvigioni_operatori` della polizza (`collaboratore_id`/`provvigione`) nel formato titolo (`operatore_id`/`operatore_nome`/`provvigione`).
  - `create_polizza`: il primo titolo automatico eredita la ripartizione della polizza.
  - `update_polizza`: aggiunto `provvigioni_operatori` ai campi economici che riallineano il titolo iniziale `da_incassare`; la ripartizione viene ricopiata ad ogni salvataggio dei dati economici della polizza.
- **Flusso**: crea polizza → inserisci dati economici/ripartizione nella scheda polizza → al salvataggio il titolo `da_incassare` riceve la stessa ripartizione.
- **Verifica**: curl + query MongoDB — titolo con `provvigioni_operatori=[JACOPO:120, Mario:80]` ereditati correttamente dalla polizza.



## 2026-06 — Picker collaboratori WhatsApp: inclusi anche gli admin
- **Bug utente**: SCHIANTARELLI MARCO (collaboratore attivo in libreria) non compariva nel selettore "Chi può vedere questo WhatsApp". Causa reale: Marco ha ruolo **Amministratore** (`role: admin`), mentre il picker filtrava solo `collaboratore` e `dipendente`, escludendo gli admin.
- **Fix** (`WhatsAppInstances.jsx`): il filtro ora include `["admin","collaboratore","dipendente"]` — tutti gli operatori dell'agenzia del tenant (l'endpoint `/auth/users` restituisce già tutti gli utenti del tenant, escluso solo il super_admin). I `cliente` restano esclusi.
- **Verifica** (curl, tenant di test): `/auth/users` ritorna anche gli admin (es. SCHIANTARELLI JACOPO) che ora rientrano nella lista. Richiede publish per la produzione.



## 2026-06 — OCR: imposte dedotte dal lordo + barra di avanzamento
- **Richiesta/bug utente**: (1) durante l'OCR (creazione polizza / salvataggio documenti) mostrare una barra di caricamento per sapere che è in lavorazione; (2) l'OCR creava il titolo con i dati corretti ma i campi economici della polizza (tab Economici) nascevano con **imposte a 0** pur avendo il lordo corretto — es. netto 1205,86 + ssn 44,89 ≠ lordo 1410 (mancavano 159,25 di imposte).
- **Fix barra** (`components/OcrProgressBar.jsx`, nuovo): barra di avanzamento simulata (fluida, si ferma al 92% e scatta al 100% a fine elaborazione). Integrata in `Polizze.jsx` (OCR "Carica PDF polizza") e `DocumentiInbox.jsx` (dropzone "Carica documenti").
- **Fix imposte** (`ocr_polizza.py` → `_riconcilia_premi`): quando il LORDO è noto ma le imposte sono assenti/0 (PDF che riporta il totale ma non itemizza le imposte riga per riga), le imposte vengono dedotte come residuo `lordo − netto − ssn − diritti`. Così la scomposizione quadra sempre e sia la **polizza** sia il **titolo** nascono con i dati corretti (il titolo è generato dai campi economici della polizza in `create_polizza`). Non inventa imposte per le polizze realmente esenti (lordo == netto+ssn).
- **Verifica**: unit test su 3 scenari (residuo 159,25 che quadra a 1410; vita esente resta 0; garanzie itemizzate sommano correttamente). Dialog nuova polizza renderizza senza regressioni (screenshot). Backend riparte OK. Fix attivo per OCR manuale (`/utility/ocr-polizza`) ed email automatico (`polizze_email.py`); entrambi usano `estrai_dati_polizza`.
- **Nota**: la polizza già esistente 184643591 va corretta a mano (o ri-passata in OCR); il fix agisce sui NUOVI OCR. Richiede publish per andare in produzione.



## 2026-06 — Prima Nota: la ricerca trova anche per importo
- **Richiesta/bug utente**: nel tab "Movimenti (elenco)" il campo Cerca non trovava nulla digitando un importo (cercava solo descrizione/categoria/mezzo/n. documento). L'export Excel per intervallo date esiste già nello stesso tab (pulsante Excel).
- **Fix** (`server.py`): aggiunto helper `_q_importo` che interpreta la query come numero accettando sia il formato italiano `1.234,56` sia `1234.56`. La ricerca per importo (con tolleranza di 1 centesimo) è stata aggiunta a tutti gli endpoint Prima Nota: elenco `/contabilita/prima-nota`, stampa PDF `/stampa/prima-nota`, export `/stampa/prima-nota.xlsx`.
- **Verifica** (curl, dati reali): `q=505.0` e `q=505,0` trovano entrambi il movimento da 505,00 €; i risultati rispettano l'importo richiesto. Backend compila e riparte correttamente.
- **Nota**: così puoi cercare direttamente `131,95` in Movimenti (elenco) per individuare data e conto di quel movimento.


## 2026-06 — Saldo cassa storico: non cambia più alla riapertura (conti disattivati inclusi)
- **Bug utente** (produzione): riaprendo una giornata chiusa SENZA modifiche, il "saldo cassa" cambiava di un importo COSTANTE di 131,95 su più giorni (23, 26, 27, 28, 29, 30 ottobre). Es. 26/10 corretto 101.345,70 → mostrato 101.213,75.
- **Meccanica**: giornata CHIUSA → mostra lo snapshot congelato (corretto); RIAPERTA → ricalcolo live. Lo scarto COSTANTE su tutti i giorni indicava un unico elemento escluso dal live.
- **Causa** (`server.py`, calcolo `sum_conti` in `_compute_brogliaccio` ~10159 e nell'endpoint situazione cassa ~10554): la somma dei conti usava solo i conti `attivo:True`. Un conto cassa DISATTIVATO dopo la chiusura (ma con saldo residuo, es. 131,95) veniva escluso dal ricalcolo live, mentre lo snapshot lo includeva → saldo più basso di 131,95 su tutti i giorni successivi. Disattivare un conto cambiava retroattivamente i saldi storici.
- **Fix**: entrambi i calcoli ora includono TUTTI i conti (anche disattivati). Un conto azzerato contribuisce 0; un conto disattivato con saldo residuo viene correttamente conteggiato. Nell'elenco conti dell'endpoint situazione cassa i conti disattivati e azzerati restano nascosti.
- **Verifica**: impostando saldo 131,95 su un conto DISATTIVATO, `sum_conti` passa da 283.739,21 a 283.871,16 (prima lo ignorava). In preview (conti disattivati vuoti) il valore resta invariato → nessuna regressione.
- **Effetto**: fix di solo CODICE, nessuna riparazione dati necessaria. Dopo il publish/deploy, riaprendo i giorni 23 e 26–30/10 il saldo cassa tornerà corretto (col conto disattivato incluso). Se dopo il deploy lo scarto persistesse, la causa sarebbe un movimento datato ≤23/10 rimosso/spostato → in tal caso serve una diagnostica mirata.


## 2026-06 — Incasso di titolo coperto in giorno diverso: niente più doppia registrazione
- **Bug utente** (produzione): titoli messi a SOSPESO (copertura) il 30/10 e incassati il 02/11. Il 02/11 la Prima Nota mostrava registrazioni SBAGLIATE: incasso pieno con TOTALE/PROVVIGIONI/SALDO ricontabilizzati + banca, invece del solo spostamento SOSPESO→BANCA. (Giornata del 30/10 NON chiusa.)
- **Causa** (`server.py` → `incassa_titolo`): con `merge_copertura=true` (passato dal frontend) la copertura di un GIORNO PRECEDENTE ancora APERTO veniva "unificata" → la riga di copertura del 30/10 veniva CANCELLATA e l'incasso del 02/11 diventava un `incasso_premio` pieno (effective_coperto=False), ricontabilizzando entrate/provvigioni/saldo.
- **Fix**: l'unificazione copertura+incasso ora avviene SOLO se la copertura è dello STESSO giorno dell'incasso (rimosso il merge cross-day basato su `merge_copertura`). Una copertura di un giorno precedente resta intatta e l'incasso successivo è un `incasso_coperto` (SOSPESI −lordo, banca +importo, nessun ricalcolo di TOTALE/PROVVIGIONI/SALDO).
- **Verifica** (API + DB): copertura 30/10 (copertura_titolo, 1020,50) RESTA; incasso 02/11 → `incasso_coperto` (provv=0, su conto banca). Nessun doppio conteggio. Il flusso same-day (dialog copertura+incasso, incasso rapido) continua a unificare in una riga.
- **Effetto**: il fix previene nuove registrazioni errate dal prossimo publish/deploy. Le registrazioni GIÀ errate in produzione (coperture 30/10 cancellate + incasso pieno 02/11) vanno corrette separatamente (serve una ripulitura dati in produzione, non accessibile da qui).


## 2026-06 — Brogliaccio: KPI Sospesi fedele alla data della videata (fix riapertura/richiusura)
- **Bug utente** (produzione, tenant jacopo@schiantarelli): riaprendo e richiudendo una Prima Nota chiusa — anche senza registrare nulla — il KPI "Sospesi" cambiava/era errato (es. al 26/10/2026 atteso 71.046,59, mostrato 99.194,89). I KPI della videata devono riferirsi SEMPRE alla data del brogliaccio visualizzato.
- **Causa**: il KPI Sospesi (`_total_sospesi_as_of`, usato da `_compute_brogliaccio` → `riepilogo_kpi.crediti`) sommava i titoli coperti ancora da incassare SENZA filtrare `data_copertura <= data_giorno` (pur dichiarandolo nel docstring). Così conteggiava anche le coperture fatte DOPO la data della videata (attività dei giorni/mesi successivi) → valore gonfiato e che "deriva" nel tempo. Le altre voci KPI (entrate/provvigioni/rimesse/sconti/spese/saldo) sono invece ricostruite dai movimenti immutabili `<= data_giorno`, quindi già fedeli alla data.
- **Fix** (`server.py` → `_total_sospesi_as_of`): aggiunto il filtro `data_copertura <= data_giorno` alla pipeline. Ora il KPI Sospesi riflette esattamente lo stato alla data della videata e non è più influenzato da coperture successive; riapertura+richiusura senza modifiche non altera il valore.
- **Nota approccio**: valutato e scartato il ricalcolo dei sospesi dai soli movimenti (cum_sospesi) — su questi dati non riconcilia col totale titoli (coperture storiche senza movimento), quindi inaffidabile. Mantenuta la fonte sui titoli, resa fedele alla data.
- **Verifica**: test diretto — copertura datata 28/10 → "as of 26/10" invariato (delta 0), "as of 28/10" +5.000 (conta dalla sua data). Il fix avrà effetto in produzione dopo il publish/deploy (in preview il dataset è diverso).


## 2026-06 — Polizze a frazionamento UNICA: annullata solo alla scadenza
- **Richiesta utente**: quando il frazionamento è "unica", la polizza deve diventare "annullata" SOLO alla scadenza del contratto, non prima (es. VIAGGI GIRAMONDO M00118537 mostrava stato "annullata" con scadenza 17/11/2026 futura).
- **Causa**: per le polizze unica OMNIA valorizza la "data annullo" (rec20 col AG) con la SCADENZA naturale del contratto (polizza una tantum). L'import (`_build_polizza_payload`, riga 731) marcava `annullata` appena presente la data annullo, anche se futura.
- **Fix import** (`ania_importer.py` → `_build_polizza_payload`): se `frazionamento == "unica"` e la scadenza è > oggi → stato resta `attiva`; diventa `annullata` solo quando la scadenza è stata raggiunta (<= oggi). Invariato per gli altri frazionamenti e per le sostituzioni.
- **Correzione dati** (tenant jacopo@schiantarelli): 4 polizze unica erano `annullata` con scadenza futura (2028/2030/2032, data_annullamento = scadenza) → riportate ad `attiva`. Nota: `_upsert_polizza` aggiorna solo i campi mancanti, quindi lo stato già presente non si corregge da solo al re-import — per questo la correzione è stata applicata direttamente.
- **Verifica**: test diretto di `_build_polizza_payload` — unica+scad futura→attiva, unica+scad passata→annullata, annuale+annullo→annullata (invariato), unica senza annullo→attiva. Correzione dati verificata (0 residui).
- **Gap noto**: non c'è un ricalcolo automatico che marca `annullata` una polizza unica quando la scadenza viene superata (il re-import riempie solo i campi mancanti). Se serve, si può aggiungere un controllo schedulato.


## 2026-06 — Incasso in direzione MULTIPLO: arretrato→direzione diretto (niente copertura/sospesi)
- **Bug utente**: incassando in direzione più titoli ARRETRATI, il flusso multiplo creava prima una COPERTURA (due righe SOSPESI nel Brogliaccio) e poi le righe DIREZIONE → doppia registrazione. Atteso: comportarsi come l'incasso SINGOLO (arretrato → incasso in direzione in un'unica riga, senza copertura/sospesi).
- **Causa**: nel bulk dialog la checkbox "Pagamento in direzione" era sotto "Copertura" e chiamava `bulk-copertura` + PUT `pagamento_in_direzione`. Inoltre nell'endpoint singolo, per un incasso in direzione `is_coperto` era forzato a False → l'eventuale copertura NON veniva assorbita.
- **Fix frontend** (`pages/Titoli.jsx`, `BulkActionDialog.submit`): se "in direzione", per ogni titolo chiama direttamente `POST /titoli/{id}/incassa` con un mezzo 'direzione' + `merge_copertura=true`, SENZA `bulk-copertura`. Gate su `doCopertura && inDirezione`; `inDirezione` resettato quando si deseleziona Copertura; toast d'errore se alcuni falliscono.
- **Fix backend** (`server.py` → `incassa_titolo`): `_assorbe_copertura = is_coperto or is_direzione` → una copertura dello stesso giorno (o con `merge_copertura` su giornate aperte) viene assorbita/eliminata anche nel caso direzione (snapshot in `coperture_assorbite` per il revert). Resta un solo movimento `incasso_premio_direzione`.
- **Verifica**: testing agent — backend 5/5 pytest; E2E: 2 arretrati selezionati → "2/2 titoli incassati in direzione", nessuna chiamata `bulk-copertura`, 1 movimento per titolo (`incasso_premio_direzione`, is_direzione, conto=null), Brogliaccio con 1 sola riga direzione per titolo e nessuna riga copertura. Dati di test ripuliti.


## 2026-06 — Import OMNIA: anagrafica esistente, nome mai sovrascritto
- **Richiesta**: in import OMNIA non sovrascrivere mai nome/cognome o denominazione sociale (`ragione_sociale`) di un'anagrafica già presente nel gestionale; se l'anagrafica non esiste, crearla.
- **Fix** (`ania_importer.py` → `_processa_anagrafiche`, riga ~539): aggiunto `ragione_sociale` ai campi preservati per le anagrafiche esistenti (insieme a email/pec/telefono/cellulare/collaboratore). Le anagrafiche nuove vengono create normalmente (ramo else). Nessun altro update anagrafiche tocca i nomi (riga 956 aggiorna solo `collaboratore_id` se mancante).
- **Verifica**: test logico — esistente `ragione_sociale='MARIO ROSSI'` + import `'ROSSI SPA'` → nome preservato; campi vuoti (telefono/indirizzo) comunque valorizzati. Modulo importa senza errori.


## 2026-06 — Import Carichi: tutto in "in attesa" + dashboard esclude i non validati
- **Richiesta utente**: importando ~500 righe comparivano solo 3 "in attesa". Timore che l'import sovrascrivesse i Titoli ufficiali senza validazione.
- **Diagnosi**: nessuna sovrascrittura dei titoli ufficiali (impossibile nel codice). Le righe venivano SALTATE come duplicati perché esisteva già un titolo "validato" con stessa polizza+decorrenza. Il tenant ha ~56.199 titoli "validato", di cui ~56.085 da una migrazione iniziale (11/09/2026) marcati validati direttamente (non via validazione manuale).
- **Decisione utente**: l'import deve portare SEMPRE tutte le righe in "in attesa" (sovrascrivendo l'eventuale carico in attesa esistente, senza duplicare). La promozione a Titolo ufficiale avviene solo in validazione.
- **Fix backend** (`routes/carichi_mensili.py` → `_insert_or_replace_carico`): rimosso lo skip `skipped_duplicate` quando esiste un titolo validato. Ora: carico in attesa esistente → sovrascritto; altrimenti → creato nuovo in attesa. Mai tocca i titoli validati. La validazione (`valida_carichi`) resta invariata: sovrascrive il titolo `da_incassare` libero / crea nuovo, protegge incassati/coperti/in Prima Nota (`_carico_overwritable`).
- **Fix dashboard** (`server.py` → `statistiche_incassi_situazione`, `base_flt`): esclude `stato_carico ∈ {in_attesa, annullato_carico}` dai KPI (arretrati/sospesi/incassi), coerente con le liste titoli ufficiali. Necessario perché ora i carichi in attesa crescono molto.
- **Verifica** (curl, tenant reale): 1° import file Nov → creati 3, sovrascritti 493, duplicati 0; 2° import stesso file → creati 0, sovrascritti 496, duplicati 0 (nessun doppione). Dashboard: arretrati_scaduto 16.443,66 (non più gonfiato dagli in_attesa). Dati di test ripuliti (0 Nov in_attesa).


## 2026-06 — Fix: dati non visibili dopo import Carichi Mensili
- **Problema**: dopo un import CSV/Excel ("ho importato il file ma non ci sono i dati"), i titoli venivano creati correttamente (es. 493) ma NON apparivano in griglia: il filtro di default ("Preset mese attivo") mostra i titoli per scadenza del mese corrente, mentre i titoli importati hanno effetto/scadenza nel periodo importato → risultavano nascosti.
- **Fix backend** (`routes/carichi_mensili.py` → `import_apply`): la risposta include ora `effetto_min` / `effetto_max` calcolati sui titoli effettivamente caricati/sovrascritti.
- **Fix frontend** (`pages/CarichiMensili.jsx`): al termine dell'import il callback `onImported` imposta automaticamente il range date decorrenza (`dal`/`al`) sul periodo importato, così i titoli appena caricati sono subito visibili.
- **Verifica**: riprodotto in UI reale sul tenant con dati reali — dopo import la griglia passa automaticamente a 01/11/2026–30/11/2026 e mostra i 493 titoli. Dati di test ripuliti.


## 2026-06 — Ciclo di vita documento firmato + Provider di firma per agenzia
### Modelli: "Card Documentale di Riferimento"
- `TemplateModello.document_target_card` (db_models.py) + `ModelloBody.document_target_card` (routes/modelli.py).
- Librerie.jsx: dropdown "Card Documentale di Riferimento" (data-testid `modello-target-card`) raggruppato per Anagrafica/Polizza/Sinistro (costante `CARD_TARGET_GROUPS`). Salvato sul modello.
- documenti_genera.py: la categoria dell'allegato generato eredita `document_target_card` del modello (fallback su categoria esplicita → `documento_generato`). Così il PDF firmato finisce nella card giusta.

### Webhook YouSign + archiviazione automatica
- `POST /api/esignature/webhook/yousign` (pubblico, SENZA verifica firma, scelta utente). All'evento `signature_request.done`/`signer.done` conferma lo stato via YouSign, scarica il PDF firmato e chiama `_finalizza`. Poller ogni 2 min resta come backup.
- `_finalizza` ora propaga `agenzia_tenant_id` (dal rec o dall'allegato originale) all'allegato firmato: fondamentale perché poller/webhook girano SENZA contesto utente.
- DocumentiSezioneSplit.jsx `FirmaBadge`: badge "🟢 Firmato con YouSign/eSignature OpenAPI · data/ora" (data-testid `firma-done-badge-*`), mappa `firmeBySigned`.

### Provider di firma per agenzia (Super Admin)
- `firma_provider` ('yousign' | 'openapi') per-tenant in `azienda_config`. Esposto in GET/PATCH `/super-admin/agenzie` e `/super-admin/agenzie/{tid}`; normalizzato (`_norm_firma_provider`, valori legacy tipo 'namirial' → yousign); rimosso da `_CHIAVI_AZIENDA` globale.
- SuperAdminPanel.jsx EditAgenzia: selettore "Provider di firma" (data-testid `ea-firma-provider`).
- esignature_it.py `invia_per_firma`: dispatch per provider (`_firma_provider()`); OpenAPI → `esvc.create_signature` (provider rec `openapi_esignature`), altrimenti YouSign.
- Fix: in `update_agenzia` il check 404 tenant avviene PRIMA dell'upsert azienda_config (niente config orfane).
- Testato (iteration_124 + curl): persistenza firma_provider/document_target_card, webhook robusto, selettori UI. NON testabile e2e il signing reale (sandbox YouSign limita i destinatari; OpenAPI richiede credenziali live).



## 2026-06 — Richiesta documento PER CARD + Notifica "Nuovo Accesso"
### Caricamento documenti direttamente nella card corretta (ogni entità)
- `backend/routes/upload_link.py` generalizzato: il link pubblico ora è legato a
  `(entita_tipo, entita_id, categoria)` — anagrafica | polizza | sinistro | titolo.
  Alla ricezione il file viene archiviato DIRETTAMENTE nella card giusta:
  - card a storage fisso dell'anagrafica (ANAG_CARD_KEYS) → `anagrafiche.documenti[categoria]`;
  - polizza/sinistro/titolo → `allegati` con `categoria`=card key e `visibile_cliente` da config.
  Il cliente può caricare PIÙ file sullo stesso link. Retro-compat mantenuta per `anagrafica_id`.
  `GET /upload-links` filtra per `entita_tipo/entita_id/categoria`.
- Nuovo componente riutilizzabile `frontend/src/components/RichiediDocCard.jsx`
  (pulsante "Richiedi al cliente" + dialog: genera link, copia, WhatsApp, elimina) montato
  su OGNI card: in `DocumentiSezioneSplit` (polizza/sinistro/titolo/libro-matricola) e nelle
  card documenti di `AnagraficaDetail` (DocumentiTab). `anagrafica` passata da Polizza/Sinistro.
- Dashboard "documenti mancanti": si svuota automaticamente al caricamento (ricalcolo da
  allegati + dict documenti). Aggiunto `libretto_veicolo` al check libretto (`extras_p1p2.py`).
- Testato via API: upload su card anagrafica (dict) e su card polizza (allegato) OK; cleanup eseguito.

### Notifica di sicurezza "Nuovo Accesso" (nuovo dispositivo)
- `backend/auth_device_alert.py`: fingerprint a bassa invasività (HMAC-SHA256 di UA + rete
  coarse /24-/64; nessun IP/UA grezzo salvato). Collection `known_login_devices` con indice
  unique `(agenzia_tenant_id,user_id,device_hash)` + TTL 365gg. Segreto HMAC auto-generato e
  persistito in `app_settings` (nessuna modifica .env).
- `POST /api/auth/login` (server.py): `$inc login_count` atomico → `register_login_device`.
  Email SOLO se dispositivo nuovo E non è il primo accesso (login_count_before>0). Invio in
  background (asyncio), non blocca il login. Dedup/cooldown 24h via `last_alerted_at`.
- `resend_service.send_new_login_alert` (usa fallback SMTP→Resend→MOCK esistente).
- Testato: login A (no email, 1° accesso) → A ripetuto (no email) → B nuovo device (1 email MOCK)
  → B ripetuto (nessuna 2ª email). Verificato in MOCK mode, nessuna email reale. Cleanup eseguito.


## 2026-10-22 — Auth batch (auto-logout 10 min, email credenziali agenzia/operatore, recupero password + invalidazione sessioni) + chiavi OpenAPI.it/Gemini AI Studio
### Chiavi API (Super Admin)
- `backend/routes/super_admin.py`: aggiunto `openapi_it_bearer_token` a `_CHIAVI_AZIENDA` + sync env `OPENAPI_IT_BEARER_TOKEN` (`_CHIAVI_EXTRA_ENV`). `frontend/src/pages/SuperAdminPanel.jsx` (`ChiaviApiTab`): nuova sezione "OpenAPI.it". Chiave OpenAPI.it salvata nel vault e caricata allo startup (log `OPENAPI_IT_BEARER_TOKEN caricato dal vault`).
- Gemini AI Studio: salvata chiave `ai_studio_api_key` (formato `AQ.`) nel vault → `GEMINI_API_KEY` ri-idratata allo startup. Verificata reale (list_models 200 + generateContent "OK"). Tutte le funzioni AI testuali passano da `llm_compat` → Gemini.

### Auto-logout inattività (10 min)
- `frontend/src/contexts/AuthContext.jsx`: `logout()` ora `useCallback` con opzione `{idle}`; nuovo effetto che, solo da autenticati, traccia attività (mousemove/mousedown/keydown/scroll/touchstart/click) e dopo 10 min idle esegue logout + toast "Sessione terminata". Cleanup listener/timer su unmount. Nota: per-tab (non sincronizzato tra schede).

### Email credenziali di accesso (agenzia + operatore)
- `backend/resend_service.py`: `_send()` ora preferisce **SMTP admin** (azienda_config `smtp_host`/`smtp_user`, es. Gmail configurato in Librerie › Comunicazioni) → invio reale; fallback Resend → MOCK (log `[EMAIL MOCK]`). Nuovi template `send_user_credentials` (operatore) e `send_password_reset`; `send_agency_credentials`/login_url ora usano `_app_base()` (env `APP_BASE_URL`, default gestionaleschianta.it).
- `backend/server.py` `create_user` (POST /api/auth/users): invia email credenziali operatore (email + password temporanea + link) quando `accesso_software=true` e password presente. Agenzia: `create_agenzia` già invia `send_agency_credentials`.

### Recupero password + invalidazione sessioni (playbook integration_expert)
- `backend/auth.py`: token access/refresh ora includono `iat`; `require_user` rifiuta token con `iat < user.token_valid_after` (401) → tutte le sessioni precedenti cadono dopo un reset.
- `backend/server.py`: `POST /api/auth/password-reset/request` (non-enumerabile, risposta identica, email inviata in **background** via `asyncio.create_task` per eliminare la differenza di timing; token `secrets.token_urlsafe(32)`, salvato solo hash SHA-256 in `password_reset_tokens`, TTL 45 min, monouso) e `POST /api/auth/password-reset/confirm` (claim atomico `find_one_and_update`, nuova password bcrypt, `token_valid_after=now+1s`).
- `frontend`: nuove pagine `ForgotPassword.jsx` + `ResetPassword.jsx`, route `/forgot-password` e `/reset-password` in `App.js`, link "Password dimenticata?" in `Login.jsx`.
- Verifica: backend e2e (confirm 200, login nuova pwd 200, vecchia pwd 401, token monouso, vecchio access token→401). Testing agent iteration_113: backend 5/5, frontend 4/4, 0 bug critici. Email SMTP non configurato → tutto in MOCK (nessun invio reale). Dati temporanei ripuliti.


## 2026-10-22 — Documenti Compagnie + Avvisi scadenza documentali (app+email) + verifica Visibilità
### 1) Documenti Compagnie (come Azienda)
- `backend/db_models.py` `Compagnia`: aggiunto campo `documenti: list = []`.
- `backend/server.py`: nuovi endpoint `POST /api/compagnie/{cid}/documenti` (upload multiplo per tipologia su object storage, max 10MB) e `DELETE /api/compagnie/{cid}/documenti/{item_id}`. `PUT /api/compagnie/{cid}` ora fa `pop('documenti')` per non sovrascrivere i documenti col salvataggio del form.
- `backend/server.py` CARD_DEFS: aggiunta entità `compagnia` (Convenzione/Mandato, Accordo provvigionale, Circolari, Listini, Altro) → appare nel pannello Librerie → Visibilità documenti.
- `frontend/src/pages/Compagnie.jsx`: sezione "Documenti" (`comp-documenti-sezione`) nel dialog modifica (DocumentiCompagnia + CompDocFolderCard): upload multiplo, tipologia, descrizione, date rilascio/scadenza, eliminazione. In creazione mostra hint (`comp-documenti-hint`). Fix stato dialog: `key` su CompagniaDialog + `load()` alla chiusura.
- `frontend/src/pages/Librerie.jsx`: `compagnia` aggiunta a `ENTITA_LABEL`, `ENTITA_ORDINE` e stato newCard.

### 2) Avvisi scadenza documentali (opt-in per singolo documento, app + email)
- `frontend/src/components/AvvisoScadenzaControl.jsx` (nuovo): pulsante "Attiva avviso" su ogni documento con `data_scadenza`; giorni di preavviso configurabili (default 15, range 1-365). Usato in Compagnie, Agenzie partner e Azienda.
- `backend/server.py` `PUT /api/documenti/avviso`: persiste `avviso_attivo`/`avviso_giorni` sul documento (entità compagnia | agenzia_partner | azienda); 404 se item inesistente; all'attivazione crea/riattiva automaticamente la regola alert `documento_aziendale_scaduto` (`_ensure_regola_avviso_documenti`).
- `backend/alert_models.py`: nuovo `schedule_kind` `documento_aziendale_scaduto`.
- `backend/alert_presets.py`: nuovo preset template "Avviso scadenza documento aziendale" (canali app+email).
- `backend/scheduler_alert.py`: resolver `_res_documenti_aziendali_in_scadenza` → rileva i documenti con avviso attivo la cui scadenza cade ESATTAMENTE tra `avviso_giorni` giorni (preavviso per-documento, fallback al default della regola). Verificato: match a 15gg, nessun match a 3gg.

### 3) Verifica Visibilità documenti (end-to-end)
- Pannelli Visibilità per collaboratore, agenzia_partner, azienda e compagnia verificati via testing agent (toggle visibile/interno, obbligatoria, card custom, salvataggio + persistenza). 100% dopo fix Compagnie.jsx.

Note: nessuna email reale inviata nei test; tutti i dati di test rimossi.


## 2026-06 — Portale Cliente: isolamento multi-tenant del login (P0 sicurezza)
Problema: il login del portale cercava l'anagrafica globalmente per email+CF e prendeva la PRIMA corrispondenza, il token non salvava il tenant (leggeva `tenant_id` inesistente invece di `agenzia_tenant_id`) e nessuna query filtrava per tenant. Un cliente presente in più agenzie poteva vedere le polizze dell'agenzia sbagliata.
- `backend/portale_cliente.py`:
  - `_issue_token` ora riceve il tenant autorevole `agenzia_tenant_id`.
  - `current_cliente` ricava il tenant SEMPRE dal DB (`ana.agenzia_tenant_id`), lo espone come `cliente["_tenant_id"]` e rifiuta (401) i token il cui `tid` non coincide col DB.
  - `POST /api/portale/auth/login`: accetta `slug` opzionale → con il link personale `/c/{slug}` il login è vincolato a QUELLA anagrafica/tenant (verifica email+CF/PIVA). Senza slug: se le credenziali valide esistono in più agenzie risponde `{status:"tenant_selection_required", challenge, agencies:[{aid,label}]}`.
  - Nuovo `POST /api/portale/auth/login/select-tenant`: completa il login con challenge monouso (TTL 5 min, collection `portale_login_challenges`).
  - Filtro `agenzia_tenant_id` aggiunto (defense-in-depth) alle query portale: polizze, titoli, polizza/titoli, documenti (pol_ids/sin_ids), nuclei collegati.
- Frontend:
  - `PortaleLanding.jsx`: salva anche `portale_slug` in sessionStorage prima di `/portale`.
  - `PortaleCliente.jsx` `LoginScreen`: invia `slug`, gestisce la schermata "Scegli l'agenzia" (`portale-agency-select`, `portale-agency-option-{aid}`) e chiama select-tenant; pulisce sessionStorage al successo.
- Test API (dati temporanei su 2 tenant, poi rimossi): slug A→solo polizza tenant A, slug B→solo tenant B, login generico→disambiguazione con 2 agenzie, select-tenant→solo tenant scelto, riuso challenge→401, password errata→401. Tutti superati.


## 2026-06 — Librerie → Utenti/Collaboratori: nuova "Gestione utente" a 6 tab
- Riorganizzato il dialog `UtenteForm` (`frontend/src/pages/Librerie.jsx`) secondo le schermate del gestionale, con 6 tab:
  **Generale** (tipologia_utente, mansione, carica, Amministratore?/Ruolo sincronizzati, responsabile/svolge/addetto intermediazione, deleghe_poteri, data_cessazione_account + blocco provvigioni/sottorete/note interne conservato),
  **Anagrafica** (cognome_ragione_sociale, nome_proprio, luogo/data nascita, 3 indirizzi via/CAP/città residenza-sede-ufficio, CF, P.IVA, cellulare, tel/fax ufficio, PEC, codice gestionale, IBAN, avatar),
  **RUI / IVASS** (albo, sezione A/B/C/D/E/F, n° iscrizione, qualifica, data iscrizione),
  **Contratti** (lista contratti + lista dichiarazioni via `AllegatoManager` + 2 campi dichiarazione sintetica),
  **Certificati** (lista certificati + slot "Documenti personali" esistenti),
  **Formazione** (`CorsiCollaboratore` potenziato: titolo, argomento, data, ore/minuti, attestato, filtro per anno).
- Backend (`server.py`): nuovi endpoint `POST/DELETE /api/auth/users/{uid}/allegati/{categoria}` (categoria ∈ contratti|dichiarazioni|certificati), estesi `POST /corsi` e `/corsi/upload` con argomento/data/ore/minuti/anno.
- Modello `UserPublic` (`db_models.py`) esteso con i nuovi campi scalari + array `contratti_collab`, `dichiarazioni_collab`, `certificati_collab`.
- FIX dataloss (HIGH da testing): `GenericForm` ora accetta `omitOnSave` e NON reinvia nel PUT gli array/URL gestiti da endpoint dedicati (contratti/dichiarazioni/certificati/corsi + *_url); rimossa anche la password vuota dal payload. Legenda "Livelli di visibilità" spostata nel solo tab Generale; reset input file dopo l'aggiunta; conferma su eliminazione corso.
- Verificato: backend via curl (PUT persiste nuovi campi; allegati add/list/delete OK) e frontend via testing_agent (9/9 flussi) + screenshot.

## 2026-06 — Prima Nota: tutte le compagnie attive nel "Saldo cassa per compagnia"
- La tabella "Saldo cassa per compagnia" (brogliaccio) ora elenca **tutte le compagnie attive**,
  anche quelle a **saldo 0,00 € senza movimenti** (prima venivano saltate con `continue`).
- Filtro compagnie allineato: `attiva ≠ false` (prima `attiva == True` stretto, escludeva quelle
  col campo `attiva` assente). Coerente con `/compagnie` e col conteggio Agenzie.
- File: `server.py::_compute_saldi_compagnie`. Verificato: tenant admin 13 attive → 13 righe.

## 2026-06 — Agenzie: conteggio "mandato diretto" solo compagnie attive
- `routes/agenzie.py` ora conta nel badge solo le compagnie **attive** (sia principale che
  partner). Prima includeva anche compagnie dirette disattivate → conteggio gonfiato (es. 3 vs 2).


## 2026-06 — Premio Annuo automatico sulla scheda polizza (da titolo)
- Nuovi titoli (import Omnia/ANIA, OCR polizza, creazione manuale, creazione polizza) ora
  **annualizzano** i premi e le provvigioni della scheda polizza: **rata × n. rate/anno**
  (annuale×1, semestrale×2, quadrimestrale×3, trimestrale×4, mensile×12, unica×1).
- Si applica **solo** ai titoli tipo `nuova`, `rinnovo`, `quietanza`. **Esclusi** `sospensione` e
  `regolazione` (non modificano la polizza).
- Campi sovrascritti sulla polizza: `premio_netto`, `premio_imposte`, `premio_ssn`,
  `premio_accessori`, `diritti`, `premio_lordo`, `provvigioni`. Le quote **collaboratore/margine**
  si derivano a lettura dallo schema provvigionale (tab Provvigioni).
- Nessuna bonifica retroattiva: effetto solo dai **prossimi** titoli/import. La riconciliazione
  prende sempre il **titolo valido più recente** (per effetto/scadenza) → l'ultimo vince.
- Implementazione: `shared.ricalcola_premio_annuo_polizza(db, polizza_id)` + `_RATE_PER_ANNO`,
  `TIPI_TITOLO_ANNUALIZZA`. Hook in `server.py` (create polizza, create/update titolo) e
  `ania_importer._processa_titoli` (riconcilia le polizze toccate a fine import, dopo le garanzie).
- UI: tab **Premi** e **Provvigioni** della scheda polizza etichettate "· valori annui".
- Verificato: polizza semestrale rata 100/80/18/2 provv10 → annui 200/160/36/4 provv20; titolo
  sospensione più recente ignorato. Test API end-to-end + test unit motor.


## 2026-10-22 — Modelli Firma: modalità {placeholder} + Word + Librerie
- Aggiunto segnaposto `{x}` per **sbarrare una casella** (scrive una X nel punto). Verificato.
- **Pivot a segnaposto `{...}`** (niente più riquadri da trascinare): nel Word/PDF si scrivono
  `{nome_cliente}`, `{agenzia_rui}`, `{collab_rui_sezione}`, `{firma}` ecc.; in compilazione
  l'app sostituisce i segnaposto coi valori reali (pymupdf redaction) e rileva `{firma}` per
  posizionare il campo firma Yousign. Verificato con unit test (sostituzione + rilevamento firma).
- **Nuovi gruppi dati**: Cliente, Polizza, **Collaboratore** (nome, CF, email, RUI, sezione RUI),
  **Agenzia** (ragione sociale, P.IVA, RUI, sezione RUI), data odierna. Collaboratore risolto da
  polizza o utente corrente; agenzia da `azienda_config`.
- **Supporto Word**: .docx/.doc convertiti in PDF via LibreOffice headless (installato; va
  aggiunto anche al Dockerfile Railway). Upload anche via **drag & drop**.
- **Spostato in Librerie → "Modelli Firma (PDF/Word)"** (rimossa voce di menu dedicata).
  UI: spiegazione, segnaposto cliccabili (copia), "Compila per un cliente", anteprima PDF.
- Backend: `/api/firma/modelli` (upload/list/detail/delete/compila); compila salva il PDF come
  allegato del cliente/polizza e, se c'è `{firma}`, crea la richiesta Yousign (sandbox).

## 2026-10-22 — Firma Yousign/YouTrust sandbox — TESTATA OK
- Flusso e2e verificato (crea→carica→firmatario→attiva `ongoing`). Key: `YOUSIGN_SANDBOX_API_KEY`.

## 2026-10-22 — Firma digitale Yousign/YouTrust + Designer modelli (MVP)
- **Integrazione Yousign v3 (brand YouTrust)** testata e FUNZIONANTE in sandbox
  (`https://api-sandbox.yousign.app/v3`, Bearer): crea richiesta → carica PDF → aggiunge
  firmatario (firma elettronica) → attiva (status `ongoing`). Key in `YOUSIGN_SANDBOX_API_KEY`.
  Note: livello "simple" richiede `signature_authentication_mode` ∈ otp_email/otp_sms/no_otp;
  in sandbox l'email firmatario deve appartenere all'organizzazione Yousign.
- **Designer modelli firma** (`routes/firma_modelli.py` + `pages/ModelliFirma.jsx`):
  - L'agenzia carica un PDF; il backend renderizza le pagine come immagini (pymupdf).
  - Editor visivo: trascini sulle pagine i campi **Dato** (nome cliente, CF, P.IVA, indirizzo,
    comune, CAP, provincia, email, telefono, data, n° polizza, compagnia) e il campo **Firma**;
    coordinate salvate come frazioni sul modello (riusate finché non le modifichi).
  - "Compila per cliente": scrive i dati reali dentro il PDF, lo salva come allegato, e (se
    presente campo firma) crea la richiesta Yousign con il campo firma nel punto salvato.
  - Scoping per agenzia (tenant). Endpoint sotto `/api/firma/modelli`. Voce menu "Modelli Firma".
  - Endpoint diagnostico Super Admin `POST /super-admin/chiavi-api/test-yousign`.
- Test: flusso e2e via API OK (nome scritto nel PDF verificato con estrazione testo; firma
  Yousign status `ongoing`); editor verificato nel browser sul PDF IVASS reale.
- **Pendente**: supporto Word (.docx) richiede LibreOffice (da aggiungere anche al Dockerfile
  Railway); per ora caricare PDF. Sostituzione provider Namirial/OpenAPI non ancora effettuata
  (Yousign affiancato, da promuovere a default quando confermi).

## 2026-10-22 — Verifica completa anti-doppia-registrazione (centralizzata nel backend)
- Verificati TUTTI i flussi di incasso del codice:
  - Frontend multiplo: `Titoli.jsx` e `TitoliSospesi.jsx` → `merge_copertura:true` ripristinato.
  - Frontend singolo: `DialogIncassoCopertura.jsx`, `DialogIncasso.jsx`, `PolizzaDetail.jsx`
    (incasso rapido) → NON inviano il flag, ma ora sono protetti dalla rete di sicurezza backend.
  - Backend `/titoli/bulk-incassa` (non usato dal frontend) → reso coerente (gestisce coperto
    + merge stesso giorno).
- **Rete di sicurezza centralizzata** in `incassa_titolo` (server.py): una copertura dello
  STESSO giorno dell'incasso (giornata aperta) viene SEMPRE unificata in un'unica riga
  `incasso_premio`, a prescindere dal flag → nessun flusso può più generare la doppia riga.
  Coperture di altri giorni aperti unificate solo con `merge_copertura:true`; coperture su
  giornate CHIUSE restano invariate.
- Test (DB, giornata aperta) tutti PASS:
  - singolo/bulk, copertura+incasso STESSO giorno (senza flag) → 1 riga `incasso_premio`.
  - copertura giorno precedente → 2 righe corrette su 2 giorni (storico preservato).
  - `/titoli/bulk-incassa` coperto stesso giorno → 1 riga. Dati di test rimossi.

## 2026-10-22 — FIX regressione: doppia registrazione in incasso multiplo
- Causa: `eade615` aveva rimosso `merge_copertura:true` dai flussi multipli, annullando
  la correzione `052602c`. Ripristinato.

## 2026-10-17 — Statistiche: nuova tab "Incassi" (replica cruscotto)
- Nuova tab **Statistiche → Incassi** (`StatisticheIncassi.jsx`) che replica il layout dello
  screenshot richiesto: snapshot mese (Titoli arretrati/scaduto, Sospesi Rete Vendita, Sospesi
  cliente), KPI rolling 12 mesi (Velocità di incasso / recupero cliente / recupero rete, con
  tooltip che spiegano la formula), 3 donut (provvigioni per compagnia, provvigioni per ramo,
  premi per modalità incasso) e tabella "Incassi: situazione di <Mese>" con confronto
  anno corrente / precedente / Var. %.
- **Aggiunte righe Premi Lordi e Premi Netti** (oltre a Provvigioni Attive e Nette) come
  richiesto.
- Backend: nuovo endpoint `GET /api/statistiche/incassi-situazione?anno=&mese=` (server.py)
  che aggrega i titoli (scoped per operatore se non admin). Provvigioni Nette = Attive meno le
  quote girate alla rete vendita (`provvigioni_operatori`). Premi = importo_lordo/importo_netto
  dei titoli incassati nel mese.
- Nota: il modello dati non ha i concetti proprietari esatti del gestionale di riferimento
  ("sospesi rete vendita", "velocità di recupero"): sono calcolati dagli stati titolo
  (incassato/da_incassare/insoluto) e documentati nei tooltip.
- Verificato: endpoint via curl (mese 10/2026 → Provvigioni 267,23 / Premi Lordi 1237,00,
  donut Generali/RCA/bonifico) e screenshot browser della tab.

## 2026-10-17 — Ora di Roma (Europe/Rome) con cambio ora automatico
- Aggiunto `frontend/src/lib/timezone.js` (import in `index.js`) che forza `timeZone:"Europe/Rome"`
  su tutte le formattazioni data/ora. DST automatico. Verificato: UTC 23:01 → "17/10/2026, 01:01".

## 2026-10-16 — OCR: salvataggio automatico documento nella card (robusto)
- Card "Libretto veicolo": upload unico con OCR automatico; il file è SEMPRE salvato via
  `/allegati` (categoria libretto_veicolo) prima dell'OCR. Causa radice del "non salva":
  polizza_id inviato in query string ma letto da Form() nel backend.
- Nuova polizza da OCR: PDF salvato come allegato nella card "polizza".
- `/utility/ocr-polizza`: corretto Allegato (campi errati) → categoria="polizza".

> NB: da pubblicare su Railway via **Save to GitHub**.

## 2026-06 — Vault chiavi AI Super Admin (priorità al pannello)
- Pannello Chiavi API: aggiunta chiave **OpenAI** (`openai_api_key`) oltre ad AI Studio/Gemini.
- Priorità invertita: la chiave inserita nel pannello ha SEMPRE priorità;
  `EMERGENT_LLM_KEY` resta solo fallback quando il campo è vuoto.
  - Gemini: già gestito dal shim `llm_compat` (GEMINI_API_KEY → Gemini diretto).
  - OpenAI: nuovo helper `backend/ai_keys.py` (`openai_key()`/`gemini_key()`);
    usato nei siti TTS OpenAI (`marketing_studio.py`, `notebooklm.py`).
- Sync env dal vault: `PUT /super-admin/chiavi-api` e startup `server.py`
  caricano `ai_studio_api_key→GEMINI_API_KEY` e `openai_api_key→OPENAI_API_KEY`.
- Nuovi endpoint test (non espongono la chiave): `POST /super-admin/chiavi-api/test-aistudio`,
  `POST /super-admin/chiavi-api/test-openai`. UI: pulsanti "Test AI Studio" / "Test OpenAI".
- Verificato: GET espone entrambi i campi, roundtrip salva/pulisce, test-openai con chiave
  invalida → HTTP 401, UI renderizza sezioni e pulsanti.
> NB: da pubblicare su Railway via **Save to GitHub**.

## 2026-06 — Spia provider AI attivo
- Nuovo endpoint `GET /super-admin/chiavi-api/ai-status`: riporta per Gemini e OpenAI
  se è attiva la chiave `pannello`, `emergent` (fallback) o `nessuna`. Non espone valori.
- UI pannello Chiavi API: badge colorato accanto a ogni sezione AI (verde=pannello,
  ambra=Emergent fallback, rosso=nessuna). Si aggiorna dopo ogni salvataggio.

## 2026-10-22 — Documenti personali collaboratore a card multi-documento
- Librerie → Utenti/Collaboratori → tab Certificati → "Documenti personali" ristrutturata:
  - Firma digitale resta slot dedicato (alimenta la firma dei moduli, campo `firma_digitale_url`).
  - Gli altri documenti ora sono multipli, raggruppati in card per tipologia
    (Carta d'identità, Codice fiscale, Casellario giudiziale, Carichi pendenti, Documento IBAN, Altro).
- Backend: aggiunta categoria `documenti` a `_ALLEGATO_CATEGORIE`; nuovo array `documenti_collab`
  in UserPublic (db_models). Riusa gli endpoint `/auth/users/{uid}/allegati/{categoria}` (POST/DELETE).
- Frontend (Librerie.jsx): riscritto `DocumentiCollaboratore` + nuovo `DocFolderCard`;
  rimosso `DOC_TIPI` (slot fissi); `documenti_collab` aggiunto a `omitOnSave` di UtenteForm.
- Verificato: upload con tipologia → raggruppamento in card → eliminazione (curl admin) + smoke UI.

## 2026-10-22 — Documenti Azienda (sezione Librerie → Azienda) + pannello Visibilità documenti
**Richiesta:** regola generale confermata dall'utente — ogni volta che si chiede una "sezione documenti", va creata come CARD con più allegati e va SEMPRE creato anche il relativo pannello in «Visibilità documenti».

**Backend**
- `server.py` CARD_DEFS: aggiunta entità `"azienda"` (Visura camerale, Iscrizione RUI/IVASS, Certificazioni, Polizza RC professionale, Documento IBAN, Altro). Appare automaticamente in GET/PUT `/config/card-visibilita` e in `/config/card-custom/{entita}`.
- `routes/librerie.py`:
  - `POST /librerie/azienda/documenti` (multipart: file, tipologia, descrizione, data_rilascio, data_scadenza) → upload su object storage, `$push` in `azienda_config.documenti`. Richiede file (400 se vuoto), max 10MB.
  - `DELETE /librerie/azienda/documenti/{item_id}` → elimina oggetto storage + `$pull` (404 se non trovato).
  - `PUT /librerie/azienda`: aggiunto `body.pop("documenti")` così il salvataggio generale NON sovrascrive i documenti (gestiti da endpoint dedicati).
- `db_models.py` AziendaConfig: aggiunto campo `documenti: List[dict]`.

**Frontend**
- `pages/Librerie.jsx`: nuova card `DocumentiAzienda` (data-testid `azienda-documenti-card`/`documenti-azienda`) nel tab Azienda, sotto Dati Azienda. Form aggiungi (tipologia da card-visibilita, descrizione, date rilascio/scadenza, file) + card raggruppate per tipologia via `DocFolderCard` con badge scadenza. `ENTITA_ORDINE`/`ENTITA_LABEL` estesi con `azienda`.

**Fix da test precedente (agenzie partner):**
- `pages/Agenzie.jsx`: refresh lista alla chiusura del dialog (fix stato stale dei documenti); pluralizzazione "1 documento"; sezione "Dati del mandato" mostrata solo per agenzie `tipo === partner`.
- `server.py` endpoint documenti agenzie: require file + eliminazione oggetto storage su delete.

**Verifiche:** card-visibilita espone 6 entità incl. `azienda` ✓; upload/lista/delete documento azienda via curl ✓; UI card "Documenti azienda" renderizzata ✓; pannelli Collaboratori/Azienda presenti in Visibilità documenti ✓. Deploy via Save to GitHub → Railway.

## 2026-06 — Export/stampa rispettano i filtri attivi
- Titoli: CSV, Excel e Stampa PDF ora inviano TUTTI i filtri attivi (ricerca, compagnia, ramo, tag, collaboratore, conto, prodotto, tipo pagamento, periodo su data_campo, preset arretrati/sospesi/scaduti, stato) + ordinamento colonna corrente. Backend `/export/titoli.csv|.xlsx` e `/stampa/titoli` ora passano per `list_titoli` tramite dependency `titoli_filter_params`.
- Frontend Titoli: export CSV/XLSX passano da `window.open` senza parametri a `downloadFile(...)` autenticato con `exportParams()` (filtri + sort/dir).
- Polizze: export CSV/XLSX e `/stampa/polizze` ora accettano anche `tag` ed `escludi_annullate` (prima ignorati).
- Verificato via curl: Titoli 45→11 (incassato), 31 (arretrati), range data effetto ok; Polizze 31→26 (escludi_annullate), 22 (stato=attiva).
- Nota: PDF Titoli mostra `rinnovo` come `quietanza` (coerente con unificazione terminologia).

## 2026-06 — Catalogo segnaposto completo (tutto il programma)
- `routes/modelli.py`: `_PLACEHOLDER_CATALOGO` esteso da 52 a **126 segnaposto** in 8 gruppi ordinati: Agenzia (22), Anagrafica/Cliente/Contraente (27), Polizza (28), Titolo/Quietanza (16), Sinistro (14), Compagnia (7), Collaboratore/Operatore (8), Grafica e firma (4). `_PLACEHOLDER_DISPONIBILI` ora derivato dal catalogo (nessun duplicato).
- `build_context()`: nuovi parametri `titolo_id` e `sinistro_id` con risoluzione a cascata (sinistro→polizza/cliente, titolo→polizza→cliente). Popola tutti i nuovi segnaposto: agenzia estesa (forma giuridica, p.iva, cf, rui+sezione+data, comune/prov/cap/nazione, fax, sito, banca, capitale, rea), cliente esteso (pec, sesso, stato civile, titolo studio, tipo, amministratore, prov. nascita), polizza estesa (frazionamento, netto/imposte/ssn/accessori/provvigioni, veicolo, massimali, franchigia, capitale, mandato), titolo completo, sinistro completo, compagnia estesa (codice/email/telefono/sito/referente), operatore esteso (cf/piva/iban).
- `GeneraDocBody` + endpoint `/genera` e `/genera-fedele`: passano `titolo_id`/`sinistro_id`. `_resolve_contatti` e `/comunica/render` propagano titolo/sinistro.
- Verificato: endpoint `/api/librerie/placeholders` → totale 126, gruppi corretti, sinistro con numero/data/descrizione ecc.; UI "Segnaposto {…}" renderizza tutti i gruppi ordinati.

## 2026-06 — Contabilità: Fase 1 (performance) + Fase 2 (snapshot concatenati) Prima Nota
**Problema:** il calcolo Prima Nota/brogliaccio risommava TUTTI i movimenti dall'inizio vita ad ogni apertura giornata (`cum_movs = find({data<=giorno}).to_list(50000)` + loop Python), con rischio di rallentamento negli anni e tetto a 50k (troncamento silenzioso). Inoltre riaprire/richiudere una giornata poteva disallineare i saldi (snapshot congelati vs ricalcolo live) e lo strumento "Riallinea saldi" non rilevava mai differenze.

**Fase 1 — performance & correttezza (server.py `_compute_brogliaccio`, indexes.py):**
- Nuovi indici compound su `movimenti`: `[tenant, conto_cassa_id, data_movimento]`, `[tenant, is_direzione, data_movimento]`, `[tenant, data_movimento, updated_at]` (covered per il guard).
- Rimosso tetto 50k: finestra delta con `.to_list(None)`.
- Liquidità (`sum_conti`) ora riusa i cumulativi già calcolati (`per_conto_cum_out`) — eliminata 1 aggregazione per conto.
- Conti DISATTIVATI con saldo residuo ora inclusi nei saldi (iterazione su `conti_all`, non solo attivi); la lista conti per data-entry resta solo-attivi.

**Fase 2 — snapshot giornalieri concatenati (carry-forward):**
- Ogni giornata CHIUSA salva un `checkpoint` nello snapshot (`riepilogo.checkpoint`): cumulativi KPI, saldo per conto (`per_conto_cum`), `rid_cum`, + guard (`src_count`, `src_maxupd` su movimenti con data<=giorno).
- `_compute_brogliaccio` riparte dall'ultimo checkpoint CHIUSO valido < giorno e somma SOLO i movimenti successivi (finestra delta), invece di risommare da inizio vita.
- **Guard auto-verificante:** `_checkpoint_valido` riconteggia `count`+`max(updated_at)` su data<=D0; se cambiati (insert/update/delete in passato) il checkpoint è scartato → fallback al checkpoint valido precedente o ricalcolo completo. Nessuna istrumentazione delle scritture richiesta, self-healing.
- **Cascade:** riaprire una giornata la esclude dal resume (`riaperta_at` filtro); i checkpoint a valle si auto-invalidano via guard. "Riallinea saldi" ricostruisce i checkpoint (backfill su TUTTE le giornate valutate, anche diff=0).
- **Fix riconciliazione:** `_compute_brogliaccio(..., apply_snapshot=False)` per il confronto del riallineo → ora rileva davvero gli snapshot stantii (prima confrontava snapshot vs snapshot = sempre 0 differenze).

**Verifiche (curl su tenant admin reale):**
- Invariante chiave: ricalcolo via checkpoint == full-scan, identico al centesimo (sum_conti 1078.5, KPI invariati).
- Guard: insert movimento passato (+50 su 2026-10-10) → oggi 1078.5→1128.5 (checkpoint stantio scartato, fallback a checkpoint precedente); dopo delete → ripristino 1078.5.
- Riallineo: rilevata e corretta differenza reale −200 su 2026-10-15; idempotente (0 da correggere dopo apply). Chiamate frontend senza parametri OK.
- 3 indici compound creati e verificati.

**Nota:** `_compute_saldi_compagnie` resta ricalcolo completo (non checkpointato) — possibile ottimizzazione futura se diventa collo di bottiglia.

### 2026-06 — Pannello Riconciliazione saldi (Storico Prima Nota)
- Il dialog "Riallinea saldi" → ribattezzato "Riconciliazione saldi": mostra, in sola lettura, le giornate chiuse che divergono dal ricalcolo live (saldo attuale vs corretto vs differenza) prima di applicare.
- Anteprima backend ora espone `differenza_totale` (scostamento netto) e flag `ricostruire=True` per gli snapshot vecchi/incompleti (saldo_attuale null), prima silenziosamente nascosti e mai riconciliati. Ora sono conteggiati in `giornate_da_correggere` e corretti dall'apply.
- UI: badge "snapshot vecchio"/"da ricostruire", scostamento netto in testata, plurale corretto. Verificato via curl + screenshot (giornata 2026-09-09 ora visibile come da ricostruire).

### 2026-06 — Separatore migliaia su tutti i numeri (sempre, anche 4 cifre)
- Causa: per la lingua italiana il browser (regola CLDR `minimumGroupingDigits=2`) NON raggruppa i numeri a 4 cifre → "1078,50" senza punto, mentre "2.675.241,89" sì. Incoerenza percepita dall'utente.
- Fix: aggiunto `useGrouping: "always"` ai formatter centrali in `lib/api.js` (`fmtEur`, `fmtNum`, nuovo `fmtImporto`) e agli helper di valuta locali (MiniBilancioTab, PatrimonioTab, PiramidePrivati, Incentivazioni, EstrattoContoContraente, AnagraficaDetail, SaluteFiscaleTab, AzioniPolizzaTab, PortaleCliente). Ora ogni importo mostra sempre il separatore (es. 1.078,50 €).
- Nuovo helper `fmtImporto(n)` = separatore + 2 decimali senza simbolo €; usato per sostituire i `toFixed(2)` manuali di visualizzazione in Librerie, Provvigioni (input disabilitati + voci), FattureAgenziaPartner, TitoloDialog. Lasciati intatti: campi input editabili, percentuali, dimensioni file e le stringhe di ricerca importo.
- Solo visualizzazione (dati DB invariati). Verificato in preview: Contabilità → "1.078,50 €", "1.441,27 €". Richiede deploy per vederlo su Railway.

### 2026-06 — Estratto Conto Compagnie: residui in bozza + filtro collaboratore
- Bug: salvare una lista da pagare con solo una riga "residuo parziale" dava 400 ("Selezionare almeno un titolo o una voce"). Fix backend `compagnia_distinta_bozza_crea`: accetta/salva `residui`, li conta in `n_righe`/`importo`; `versaBozza` e `inBozza` (frontend) ora gestiscono i residui.
- UX: menu a tendina "Collaboratore" (EstrattoContoCompagnie) ora con campo di ricerca, più largo (w-72) e righe più spaziose/clickabili.
- Filtro: selezionando uno o più collaboratori specifici, le voci di compagnia non attribuibili al collaboratore (rappel, ritenuta_compagnia, pnc) e i residui NON compaiono più nella lista. Verificato in preview.

## 2026-06 — Fix: associazione collaboratori su Persone Giuridiche
- Bug: nella modifica anagrafica la sezione "Collaboratori / Operatori di riferimento" era racchiusa nel blocco `{f.tipo !== "persona_giuridica" && (...)}`, quindi per le aziende/persone giuridiche NON appariva e non era possibile associare il collaboratore.
- Fix: spostata la sezione collaboratori FUORI dal blocco condizionale in `AnagraficaDetail.jsx` → ora visibile per tutti i tipi di anagrafica (persona fisica e giuridica).
- Verificato in preview su tenant jacopo@schiantarelli.it (azienda +39 ITALIA S.R.L.): selettore collaboratori presente e popolato.

## 2026-06 — Titolo iniziale sincronizzato con i dati economici della polizza
- Bug: creando una polizza nuova il titolo restava a 0 anche inserendo premi/provvigioni dopo, perché il titolo viene creato solo alla nascita della polizza e `PUT /polizze/{id}` non lo riallineava.
- Fix: in `update_polizza` (server.py), se cambiano i campi economici (premio_lordo/netto/tasse/imposte/ssn/accessori/provvigioni/collaboratore_id) si riallinea il titolo iniziale ancora `da_incassare` con stesso effetto della polizza (importi, imposte=tasse+imposte, ssn, accessori, provvigioni, collaboratore) e si ricalcola il premio annuo. I titoli già in Prima Nota (coperti/sospesi/incassati) NON vengono toccati.
- Verificato in preview via curl: premi 100/8/2/5 lordo 115 provv 25 → titolo importo_lordo 115, netto 100, imposte 10, ssn 5, provv 25.

## 2026-06 — Visibilità istanze WhatsApp per collaboratore
- Richiesta: l'admin, nella pagina Istanze WhatsApp, sceglie da una tendina quali collaboratori possono vedere ciascuna istanza; il collaboratore nella chat vede solo le istanze a lui assegnate.
- Backend (routes/whatsapp_evo.py): nuovo campo `collaboratori_visibili` sulle istanze; endpoint `PUT /whatsapp-evo/instances/{name}/collaboratori` (solo admin); `GET /whatsapp-evo/instances` ora filtra per i non-admin (vede solo le istanze in cui il suo id è presente). Nessuna selezione = visibile solo all'admin.
- Frontend (WhatsAppInstances.jsx): nuova colonna "Collaboratori" (solo admin) con tendina a checkbox `CollaboratoriVisibiliCell` (Popover) per selezionare i collaboratori; etichetta "Solo admin" / "N collaboratori". La Chat WhatsApp usa lo stesso endpoint istanze, quindi il filtro si applica automaticamente.
- Verificato: PUT set/reset vis OK via curl (tenant jacopo); tendina renderizzata e funzionante (screenshot admin). NB: il filtro lato collaboratore non è stato testato con login collaboratore reale (password non disponibili nel tenant mirror) ma è una semplice list-comprehension.

## 2026-11-03 — Eliminazione polizza sostituzione + allegati Diario
- **Eliminazione polizza (sostituzione)**: il tasto Elimina ora si blocca SOLO se la polizza ATTIVA (corrente) ha un titolo proprio incassato o coperto. I titoli delle polizze precedenti sostituite (polizza_origine_id) NON bloccano più l'eliminazione. Fix frontend `PolizzaDetail.jsx` (haTitoliBloccanti) + backend `DELETE /polizze/{pid}`.
- **Ripristino polizza precedente**: eliminando l'ultima polizza attiva della catena, la polizza precedente (stato "sostituita") torna automaticamente "attiva" (clear sostituita_da_id/data_sostituzione).
- **Allegati scaricabili nel Diario cliente**: GET `/anagrafiche/{aid}/diario` arricchisce ogni voce con l'allegato collegato (via payload.allegato_id o match per nome file su anagrafica/polizze/titoli/sinistri). Frontend `AnagraficaDetail.jsx` mostra "📎 Scarica allegato" nelle voci Incassi/Email/WhatsApp/Documenti e nel dialog. Download via `/api/allegati/{id}/download`.
- Test: API DELETE 200+restore e 409 su titolo proprio incassato; diario VETTRICI MICHELE con 2 allegati risolti + download PDF 200.

## 2026-11-03 (pt.2) — Collaboratore rif. in testata + premio rete attivo + imposte polizza/titolo
- **Collaboratore di riferimento in testata**: la scheda anagrafica mostra il/i collaboratore/i di riferimento in alto a destra, sopra la foto del cliente (badge sky). GET `/anagrafiche/{aid}` ora arricchisce `collaboratore_nome` e `collaboratori_nomi`. Frontend `AnagraficaDetail.jsx` (badge `hdr-collaboratore-rif`).
- **Premio rete = solo polizze attive**: nella card "Posizione assicurativa del network" (tab Relazione) il PREMIO e le PROVVIGIONI per anagrafica ora sommano SOLO le polizze attive/in_emissione (prima includevano scadute/sostituite/annullate, gonfiando il totale). Fix `routes/anagrafiche.py` `_stats`.
- **Imposte polizza allineate al titolo (OCR)**: se il premio LORDO è noto ma le imposte sono 0, vengono dedotte come residuo (lordo−netto−ssn−accessori−addizionale) sia alla creazione sia alla modifica polizza (`_fill_imposte_residuo` in `create_polizza`/`update_polizza`). Così la scheda polizza non nasce con "Imposte: 0" e resta coerente col titolo (già derivato dalla polizza).
- Test: POST /polizze con lordo 1410/netto 1205,86/ssn 44,89/imposte 0 → polizza premio_tasse=159,25 e titolo imposte=159,25 (coerenti). GET anagrafica → collaboratori_nomi popolati.

## 2026-11-03 (pt.3) — Operatore rif. editabile in testata + fix sync IMAP "sganciata"
- **Operatore di riferimento SOTTO il nome + editabile**: in `AnagraficaDetail.jsx` il collaboratore di riferimento è ora mostrato sotto il nome cliente (non più badge in alto a destra) come dropdown stile polizze (`CollaboratoreRifSelect`, testid `hdr-collaboratore-select`). Cambio immediato: PUT `/anagrafiche/{aid}` con `collaboratore_id` + `collaboratori_ids`. Lista operatori da `/auth/users` (role != cliente, attivo). Verificato: set/none persistono e GET riflette `collaboratore_nome`/`collaboratori_nomi`.
- **Fix email collaboratore senza accesso**: cancellando l'email di un operatore `accesso_software:false` ora viene rimossa davvero (indice email migrato a partial-unique su stringhe). Verificato DB email=None dopo PUT email:"".
- **Fix sync automatica email che si "sganciava"**: root cause = scheduler APScheduler in-memory (muore ad ogni riavvio/deploy) + `azienda_config.find_one({})` non deterministico su 5 doc multi-tenant (startup rileggeva un tenant con poller disabilitato → FERMO). Fix: `imap_poller.get_active_config()` seleziona deterministicamente la casella IMAP realmente configurata (host+user+password); usata in `poll_once`, status/start/stop e re-arm allo startup. Aggiunto watchdog cron piattaforma `/api/cron/imap-poll` (`.emergent/crons.yml`, ogni 15 min, auth `WEBHOOK_CRON_SECRET`) che ri-arma lo scheduler se abilitato ma spento ed esegue un poll → la sincronizzazione si ri-aggancia da sola dopo ogni riavvio. Verificato: 401 senza/wrong token, 200 con token valido.

## 2026-06 — Batch Trattative/Pipeline/Diario + fix immagini
- Trattative: ricerca cliente digitabile, checklist (persistita), premio preventivo, totali premi per colonna nella board kanban.
- Trattative: invio preventivo via Email/WhatsApp dai dettagli.
- Pipeline: board builtin che rispecchiano dati (polizze, sinistri, titoli, regolazione, clienti) partono VUOTE con gate opt-in "Popola automaticamente"; checklist nelle card.
- Diario: download documenti allegati (manuali, email, whatsapp, pdf_storage_path); fix "NaN KB"; chat WhatsApp apre la conversazione del numero esatto della voce diario.
- FIX immagini rotte: le <img> (logo agenzia, avatar) andavano in 401 quando il cookie di sessione scadeva mentre l'app restava attiva via token Bearer. Aggiunto supporto auth via query param ?token= (auth.py) + helper imgUrl() applicato a logo/avatar. Documenti privati restano protetti (401 senza token).

## 2026-06 — Collaudo + fix post-testing (iter 129/130)
- Confermato: invio preventivo Trattative usa servizi REALI (SMTP via smtplib + WhatsApp Evolution API /message/sendText), nessun mock.
- FIX kanban Trattative: i totali per colonna e il riepilogo si aggiornano subito dopo il drag-move (load() post-move).
- FIX ricerca cliente Trattative: ora server-side (GET /anagrafiche?q=... con debounce 300ms) → tutti i 5600+ clienti ricercabili; q-search estesa a cognome/nome; cliente selezionato sempre mostrato in modifica.
- FIX dialog Modifica trattativa: ora carica i dati esistenti (key di remount) — eliminato rischio perdita dati su PUT.
- Aggiunta conferma destinatario prima dell'invio reale Email/WhatsApp.
- Allineato formato valuta totali colonna (2 decimali it-IT).
- Backend 13/13, frontend fix 3/3 + dialog modifica verificato a video.

## 2026-06 — Date picker IT + allegato al preventivo
- Trattative: campo "Scadenza polizza concorrente" ora usa DateInputIt (gg/mm/aaaa) invece del date picker nativo US — verificato a video (15/09/2026).
- Trattative: all'invio preventivo via Email/WhatsApp vengono allegati automaticamente i documenti caricati sulla trattativa (sezione DOCUMENTI/PREVENTIVO → AllegatiCell). Email via msg.add_attachment; WhatsApp via nuovo helper send_media_via_evolution (/message/sendMedia). Il caricamento del PDF è già disponibile nel dialog; aggiunta nota esplicativa.
- NB: l'invio reale con allegato non è stato lanciato a video per non messaggiare un cliente reale; path verificato sintatticamente e basato sull'endpoint send-media già funzionante.

## 2026-06 — Modello preventivo personalizzabile (Gestione Modelli)
- Creati 2 modelli in Librerie → Gestione Modelli (categoria "preventivo"): "Preventivo / Proposta (Email)" e "(WhatsApp)", seedati automaticamente e modificabili dall'utente (saluto + firma agenzia).
- Placeholder supportati: {cliente} {titolo} {premio} {ramo} {note} {compagnia_provenienza} {agenzia}.
- invia_preventivo (routes/commerciale.py) ora usa il modello preventivo del canale (email/whatsapp) con sostituzione placeholder + nome agenzia da azienda_config; fallback al testo di default se il modello manca; body.messaggio esplicito ha priorità.
- Seed modelli (_seed_modelli_default) esteso per includere il campo "oggetto".
- Verificato a video: modello visibile e popolato nella sezione Email di Gestione Modelli.

## 2026-06 — Fix DEFINITIVO immagini (loghi/avatar non saltano più)
- Causa radice: i tag <img> di logo agenzia e avatar si autenticavano solo con cookie/token; a sessione scaduta davano 401 → immagini rotte.
- Soluzione: endpoint /api/storage ora serve PUBBLICAMENTE (senza auth) solo le immagini di branding/profilo — loghi (path /azienda/) e avatar (file avatar_*) — con Cache-Control 1 giorno. Tutto il resto (documenti, scansioni, PDF) resta protetto: 401 senza auth.
- Aggiunto auth.optional_current_user (non solleva, ritorna None).
- Verificato: avatar/logo 200 senza token, documento privato 401 senza token; header mostra le immagini a video.

## 2026-06 — Fix "Visualizza firma" (Non autenticato)
- Il link "Visualizza firma" e le anteprime firma aprivano l'URL storage senza token → 401.
- Fix: avvolti con imgUrl() (aggiunge ?token=) i link/immagini firma in Librerie.jsx (Visualizza firma utente), AnagraficaDetail.jsx e PrivacyConsensiDialog.jsx (firma_cliente_url). La firma resta PRIVATA (non pubblica): si apre solo con token valido, 401 senza auth, 403 se non proprietario/non admin.
- Verificato: firma 200 con ?token (admin), 401 senza auth.

## 2026-06 — Fix OCR imposte raddoppiate (polizza es. 184643597)
- Bug: l'OCR polizza poteva restituire imposte errate (es. 50,86 = 2×25,43, conteggio doppio); la riconciliazione correggeva solo se garanzie itemizzate o imposte a 0, non verificando l'identità netto+imposte+SSN=lordo.
- Fix in ocr_polizza.py _riconcilia_premi: guardia di coerenza finale — se netto+imposte+SSN+diritti ≠ lordo (scarto >0,50€), imposte ricalcolate come residuo dal lordo. Verificato: 205,43/25,43/19,14/250,00.
- Nota: vale per i nuovi OCR; le polizze già salvate con valore errato vanno corrette a mano nel campo Imposte.

## 2026-06 — Fix OCR imposte reso DETERMINISTICO (non-determinismo LLM)
- La correzione precedente dipendeva dallo scarto col lordo; con letture non deterministiche di Gemini poteva ancora passare un valore doppio (50,86).
- Riscritto _riconcilia_premi con priorità deterministica per le imposte: (1) somma imposte per-garanzia − contributo forzoso se itemizzato; (2) altrimenti RESIDUO dal totale letto (lordo − netto − SSN − diritti), ignorando il valore singolo (inaffidabile/raddoppiato); (3) altrimenti valore letto − forzoso. Quadratura finale di sicurezza se scarto > 0,50 €.
- Testato: 6 scenari (itemizzato, doppio-no-garanzie, netto-sì/imposte-no, coerente, zero, no-lordo) → tutti 25,43. OCR live del PDF reale: 205,43 / 25,43 / 19,14 / 250,00.
- Nota: polizza 184643597 già salvata col vecchio 50,86 NON presente nel DB preview → va corretta a mano o re-importata (ora corregge da sola).

## 2026-06 — OCR targa dall'intestazione
- L'OCR leggeva una targa sbagliata (es. EN376ZF) presa da sezioni interne; la targa corretta è nell'intestazione "Polizza n. ... Targa / Telaio n. XXXX".
- Aggiunta regola nel prompt ocr_polizza.py: la targa va letta SEMPRE dall'intestazione in alto (riga "Targa / Telaio n."), con priorità assoluta su ogni altra targa/codice nel documento.
- Verificato live sul PDF reale: targa = VA164193 (corretta), imposte 25,43.

## 2026-06 — Imposte OCR: regola PRIMARIA Lordo−Netto−SSN + redeploy produzione
- Su richiesta esplicita utente: imposte = premio_lordo − premio_netto − contributo_ssn − diritti come REGOLA PRIMARIA in _riconcilia_premi (quando lordo+netto presenti), prima di garanzie/valore letto. Immune al non-determinismo LLM (niente più 50,86).
- Verificato preview end-to-end sul PDF reale: targa VA164193, netto 205,43, imposte 25,43, SSN 19,14, lordo 250,00.
- Confermato che il salvataggio (create/update_polizza + _fill_imposte_residuo) NON raddoppia: memorizza il valore ricevuto; _fill_imposte_residuo deduce solo se imposte 0/mancanti.
- Causa del problema in produzione: runtime con build precedente alla fix imposte (targa ok, imposte no) → avviata ripubblicazione (deploy) per allineare il backend.

## 2026-06 — Blocco anti-doppione import OCR polizza
- In Polizze → "Riconoscimento polizza": se il numero polizza riconosciuto esiste già nel portafoglio (backend già restituisce polizza_esistente), l'import viene BLOCCATO: nessun form precompilato, toast rosso "Polizza GIÀ ESISTENTE: n° ... (stato ...). Importazione annullata per evitare un doppione".
- File: frontend/src/pages/Polizze.jsx onOcrPolizza — early return su d.polizza_esistente.
- Verificato e2e in preview: inserita polizza fittizia 184643597 → OCR restituisce polizza_esistente → blocco; dummy poi rimossa.
- NB: va pubblicato in produzione per essere attivo lì.

## 2026-06 — RCA deployer: causa vera imposte 50,86 = righe garanzie DUPLICATE + lordo mancante
- Produzione eseguiva il codice giusto, ma quando Gemini NON leggeva premio_lordo_totale, _riconcilia sommava righe garanzie DUPLICATE dall'LLM → imposte doppie (50,86); la guardia non scattava perché il lordo ricalcolato era coerente col doppio.
- Fix in ocr_polizza.py: (1) DE-DUPLICA le righe garanzia prima di sommare; (2) se manca il lordo, lo ricostruisce dalle garanzie de-duplicate come ancoraggio; (3) regola primaria Imposte = Lordo − Netto − SSN − Diritti sempre; (4) collapse di sicurezza su scarto >0,50€. Prompt: premio_lordo_totale OBBLIGATORIO + niente righe duplicate.
- Regressione: /app/backend/tests/test_ocr_imposte.py (6 test, incluso duplicate+no-lordo) → PASS. OCR live 3× consecutivi → sempre 25,43.
- Richiede redeploy (il codice deployato precedente aveva ancora il bug del path no-lordo).

## 2026-11-05 — Imposte polizza allineate al titolo (OCR righe doppie)
Problema: polizza importata da OCR con imposte GONFIATE (50,86 invece di 25,43) —
il titolo mostrava il valore corretto ma le sezioni "Premi" ed "Economici" della
scheda polizza restavano a 50,86.
Causa: `premio_tasse/premio_imposte` memorizzati col doppio (righe garanzia duplicate
dall'LLM) e nessuna riconciliazione a livello di scheda polizza (solo il caso
"imposte mancanti" era gestito da `_fill_imposte_residuo`).
Fix:
- backend `server.py` `_fill_imposte_residuo`: ora riconcilia anche le imposte GONFIATE
  (quando netto+imposte+ssn+acc+add SUPERA il lordo di >0,50 €) → imposte = lordo−netto−ssn−acc−add,
  azzerando `premio_imposte` per evitare doppio conteggio. `update_polizza` persiste
  entrambi i campi (tasse + imposte).
- frontend `PolizzaDetail.jsx`: helper `impostePolizza(pol)` riconcilia l'imposta
  mostrata in tab Premi, form "Modifica premi", "Modifica polizza > Economici" e builder nuovo titolo.
Verifica E2E (preview): POST /api/polizze con imposte 50,86/lordo 250 → persistite tasse 25,43,
imposte 0, lordo 250; titolo auto-creato imposte 25,43. Unit: 6 scenari (gonfiate, mancanti, Vita, no-op) OK.
Nota: per la polizza 184643597 su Railway, dopo il redeploy le sezioni mostrano subito 25,43;
un salvataggio da "Modifica premi" rende permanente la correzione sul record legacy.

## 2026-11-05 — Catasto: diagnosi "vie/rendita/titolo mancanti" (CAUSA = credito OpenAPI.it)
- Causa trovata con cattura diagnostica reale (CF VVNLSN75M08L175V): il POST /visura_catastale (visura SOGGETTO, €1,90) torna **402 Pagamento richiesto** perché il saldo reale OpenAPI.it è €0,79 → l'app ripiegava SILENZIOSAMENTE sul riepilogo ricerca_nazionale (solo comune+conteggi), da cui mancano vie, rendita e titolo.
- Chiarimento business: il costo CRM "catasto" €0,30 (openapi_credito DEFAULT_LISTINO) è l'addebito INTERNO all'agenzia e copre solo /richiesta (€0,30 reali). Vie/rendita/titolo richiedono la visura soggetto (€1,90 reali su OpenAPI.it) → mismatch: il CRM addebita 0,30 ma consuma 1,90 di saldo reale.
- FIX codice (non silenzioso): openapi_it_service.fetch_cadastre_detailed usa ora _call_api_status e intercetta il 402 → ritorna credito_insufficiente/saldo_openapi/dettaglio_disponibile + messaggio chiaro. routes/openapi_it.fetch_cadastre_for_anagrafica li espone. OpenApiActions.jsx mostra toast.warning esplicito.
- NON VERIFICATO: la correttezza del parser _parse_visura_json (struttura VisuraSoggettoAttuale/GruppoUnitaImmobiliari/@attributes) NON è stata validata perché la visura non è mai stata generata (402). Da ri-verificare con cattura reale appena il saldo OpenAPI.it sarà ricaricato (≥ €1,90).
- AZIONE UTENTE: ricaricare il wallet OpenAPI.it su console.openapi.com (prezzo visura soggetto = €1,90/chiamata). Valutare se allineare il listino CRM "catasto" al costo reale.

## 2026-11-05 (2) — Catasto RISOLTO dopo ricarica credito OpenAPI.it
- COSTI REALI MISURATI (delta saldo, CF VVNLSN75M08L175V): ricerca_nazionale €0,30 + visura soggetto JSON €1,90 + visura soggetto PDF €1,90.
  → SENZA PDF (dati: vie/rendita/titolo) = €2,20 · CON PDF = €4,10.
- Listino CRM aggiornato (openapi_credito.DEFAULT_LISTINO): catasto 0,30→2,20 ; catasto_pdf 1,90→4,10. (openapi_config a DB: nessun override.)
- Parser _parse_visura_json VALIDATO su JSON reale (root VisuraSoggettoAttuale → GruppoUnitaImmobiliari → ImmobileFabbricatiS/ImmobileTerreniS). Fabbricati OK: via, rendita (A/10=418,33 C/6=336,73 A/7=662,36), superficie, titolo (DirittiReali per CF), quota.
- FIX BUG terreni: la classamento terreni è annidata in DatiClassamentoT.ClassamentoT[].@attributes (non @attributes diretto). Ora estrae Qualita (SEMINATIVO/BOSCO), RedditoDominicaleEuro (0,27/0,13/3,43) e SuperficieMQ, sommando le porzioni. Aggiunto helper _euro_to_float.
- 10/10 immobili estratti correttamente con tutti i campi.

## 2026-11-05 (3) — Drive: FIX "le cartelle non si generano" + deploy produzione
- CAUSA: cancellando le cartelle direttamente dentro Google Drive, la cache `cloud_folder_cache` continuava a puntare agli id delle cartelle eliminate → `_ensure_folder_path` le credeva esistenti e NON le ricreava.
- FIX (`backend/routes/cloud_storage.py`):
  1. OAuth callback: al (ri)collegamento reset pulito della connessione (folder_id=None, root_is_custom=False, folder_name=None, structure_initialized_at=None) + `cloud_folder_cache.delete_many` per tenant+provider.
  2. `_init_structure_for_tenant`: svuota SEMPRE la cache all'inizio, così la (ri)creazione riflette lo stato reale del Drive.
- `_find_folder` esclude già i cestinati (trashed=false) → non ritrova cartelle eliminate.
- VERIFICA E2E su Drive reale (preview, tenant-principale-schiantarelli): init rigenera tutte le cartelle/sottocartelle — INBOX (18 sottocartelle) + Archivio (Anagrafiche, Polizze, Sinistri, Trattative, Titoli, Disdette, Documenti Firmati, Altri documenti, Quietanze, Contabilità/{Prima Nota, Estratti Conto Compagnie, Estratti Conto Collaboratori}).
- DEPLOY in produzione avviato (utente ha confermato). Dopo il deploy: Librerie → Cloud Storage → "Riorganizza (INBOX + ARCHIVIO)" oppure scollega/ricollega per rigenerare sul Drive reale.

## 2026-11-05 — Fix scheduler Railway + firme 404
- **Firma 404 loop**: in `finalizza_pending()` (routes/esignature_it.py) una firma che risponde 404 sul provider viene ora chiusa come `stato="ERROR"` (+ campo `errore`), così esce dal filtro pending e non viene più interrogata all'infinito. Verificato end-to-end con record sintetico + mock.
- **Firma 200 OK ri-interrogata**: comportamento corretto (polling finché non è DONE). Quando è DONE, `_finalizza` imposta `allegato_firmato_id` e `stato=DONE`, uscendo dal filtro. Nessuna modifica necessaria.
- **Scheduler duplicati su Railway**: introdotto lock distribuito MongoDB (`scheduler_leader.py`, collection `scheduler_locks`, leader election con heartbeat/TTL). Gli scheduler di background (avvisi scadenze, avvisi programmati, face_crop, Cloud OCR, poller eSignature, IMAP poller) ora partono SOLO sull'istanza leader in `server.py` startup, evitando esecuzioni doppie con più worker/replica Uvicorn. Rilascio del lock allo shutdown per takeover immediato. Verificata elezione e takeover.

## 2026-11-05 — Pulizia istanze WhatsApp orfane (auto-repair webhook)
- **Istanze orfane 404**: in `auto_repair_webhooks()` (routes/whatsapp_evo.py), quando `/webhook/set/{name}` risponde 404 (istanza non più esistente su Evolution, es. `agenzia-prova-0342706000`, `agenzia-jacopoooo`), il record locale in `whatsapp_instances` viene ora eliminato automaticamente così non viene più richiamato a vuoto a ogni avvio. Aggiunto `removed[]` all'output e log dedicato in server.py. Verificato con istanze sintetiche + mock 404 (orfane rimosse, istanza valida mantenuta).

## 2026-11-05 — Fix GENERALE multi-tenant Google Drive (ogni agenzia collega il proprio Drive)
- **Root cause**: il callback OAuth (`routes/cloud_storage.py` `oauth_callback`) salvava solo `tenant_id` nel doc `cloud_connections`, MAI `agenzia_tenant_id`. Poiché `cloud_connections`/`cloud_folder_cache` sono tenant-scoped e il wrapper Mongo filtra per `agenzia_tenant_id`, una connessione creata da un'agenzia NON-principale risultava invisibile a `status`, `set-folder` e alle sincronizzazioni → root non salvabile ("resta Assicura CRM") e INBOX non elaborata.
- **Fix**:
  1. `oauth_callback` ora imposta ESPLICITAMENTE `tenant_id` + `agenzia_tenant_id = st["tenant_id"]` (il tenant dell'agenzia che collega, da `_tenant_id(user)`).
  2. Nuovo helper idempotente `_backfill_agenzia_label(provider, tenant)` che etichetta le connessioni/cache/scan già esistenti prive di `agenzia_tenant_id` — SEMPRE intra-tenant, mai cross-tenant. Chiamato all'inizio di `status`, `set_folder` e `_init_structure_for_tenant`.
  3. Tutte le scritture rilevanti (`set_folder`, cache path, update struttura/root) ora persistono `agenzia_tenant_id`.
  4. Mantenuto il self-heal `_adopt_legacy_connection` per la migrazione split-tenant di Jacopo (tenant legacy → c5ae2d0e).
- **Verificato in preview**: bug riprodotto (scoped find NON trova la connessione senza `agenzia_tenant_id`) → dopo backfill la connessione dell'agenzia non-principale diventa visibile. Self-heal legacy già verificato end-to-end in precedenza (VISION360 salvata + INBOX/Archivio creati).
- **IMPORTANTE deploy**: la produzione reale è **Railway** (`gestionaleschianta-production.up.railway.app`), che builda dal repo GitHub. Questo fix è nel codebase preview/Emergent: va pubblicato su GitHub perché Railway lo ricompili. Nessuna migrazione manuale DB necessaria — backfill/adopt riparano i dati esistenti al primo accesso.

## 2026-11-05 — Scan INBOX asincrono + verifica diretta DB produzione Railway
- **Verifica Railway (sola lettura, DB `assicura`)**: la connessione Drive dell'agenzia di Jacopo (`c5ae2d0e`) risulta GIÀ corretta — `folder_name="VISION360 - GESTIONALE"`, `root_is_custom=true`, struttura inizializzata; la cartella root salvata funziona. Esiste anche una connessione legacy separata (`tenant-principale-schiantarelli` → "Assicura CRM"): con lo status filtrato per `agenzia_tenant_id` (fix precedente) Jacopo vede solo VISION360 una volta deployato il nuovo codice. Lo schermo "Assicura CRM" derivava dal codice vecchio ancora live su Railway che mostrava la connessione legacy.
- **Causa "errore scan"**: `scan-now` eseguiva `scan_tenant_inbox` in modo SINCRONO attendendo l'intero report. Con molti file (OCR+LLM per ciascuno) il proxy ingress chiude la richiesta (~30-60s) → toast "Errore scan". Prova in DB: 1 documento creato dallo scan (LEVI, fonte cloud_ocr_scan) ma 0 record in `cloud_scan_history` per c5ae2d0e → lo scan non arrivava a scrivere la cronologia.
- **Fix**: `scan-now` (routes/cloud_storage.py) ora lancia lo scan in BACKGROUND (`asyncio.create_task`, con `set_current_user` per mantenere il contesto tenant) e risponde subito `{"started": true}`. Pre-check leggero (backfill + adopt + connessione) prima di avviare, con 409 chiaro se il Drive non è collegato. Frontend `OcrScanWidget.jsx`: su `started` mostra "avviata in background" e fa polling di `/scan-summary` ogni 5s (max ~5 min) per mostrare l'esito appena pronto; mantenuta compatibilità con la vecchia risposta sincrona.
- **Non testato live**: lo scan non è stato eseguito in preview perché la connessione punta al Google Drive REALE dell'utente (sposterebbe file veri). Backend e frontend compilano e ripartono correttamente.
- **DEPLOY**: entrambe le correzioni (multi-tenant OAuth/backfill + scan asincrono) vanno pubblicate su Railway via "Save to GitHub" → rebuild Railway, e su Emergent produzione se usata.

## 2026-11-05 — Scan INBOX: fallback errore → Inbox CRM (nessun file perso)
- **Richiesta utente**: se un documento non viene trovato/abbinato, metterlo comunque nella Inbox del CRM da associare manualmente e passare al file successivo.
- Caso "non abbinato" già gestito (`_process_file` → `da_smistare` → `_push_to_manual_inbox`, loop prosegue).
- **Nuovo**: nel loop di `scan_tenant_inbox` (cloud_ocr_scanner.py), quando `_process_file` solleva eccezione (OCR/download falliti, ecc.) il file viene ora inserito comunque in `documenti_inbox` (Inbox CRM, stato pending) via nuovo helper `_push_failed_to_manual_inbox` (download best-effort, classification "altro/bassa" con `scan_error`, dedup su `cloud_file_id` pending), poi lo scan continua col file successivo. Nessun file resta bloccato/perso.

## 2026-11-05 — Sincronizzazione email (IMAP) sempre attiva + fix blocco UIDVALIDITY
- **Problema utente**: "la posta stacca il sincro da solo, deve essere sempre attivo; si è fermata al 3 novembre".
- **Causa 1 (sempre attivo)**: il poller IMAP gira con APScheduler in-memory; il watchdog che lo riarma è su `.emergent/crons.yml`, eseguito SOLO sull'host Emergent → su Railway nessun cron esterno lo riaccende dopo riavvio/stallo.
  - Fix: self-healing in-process. `scheduler_leader.run_leader` accetta ora `heartbeat_callback` eseguito ad ogni heartbeat (~50s) mentre l'istanza è leader. `imap_poller.ensure_scheduler(db)` ri-arma lo scheduler se abilitato+configurato ma non in esecuzione. Non dipende da cron esterni → vale anche su Railway.
- **Causa 2 (blocco al 3 nov)**: classico cambio UIDVALIDITY lato server IMAP → `last_uid` resta più alto di tutti gli UID reali e `UID last_uid+1:*` non trova mai più nulla.
  - Fix: `poll_once` legge UIDVALIDITY dopo la SELECT, lo confronta con `imap_uidvalidity` salvato in `azienda_config`; se cambiato azzera `last_uid` e ri-bootstrappa. Persiste `imap_uidvalidity` ad ogni ciclo.
- File: `backend/imap_poller.py`, `backend/scheduler_leader.py`, `backend/server.py` (lifespan).
- Verifica: sintassi OK, backend riparte, loop leader gira senza errori, `/api/email/poller/status` risponde. Non testabile end-to-end in preview (credenziali IMAP solo sul tenant Railway). Da pubblicare su Railway via "Save to GitHub".

## 2026-11-05 · Visura camerale auto-compile + Bilanci riclassificati stampabili (3/5 anni)
Richiesta: caricare la visura camerale e compilare in automatico i dati aziendali; quando si scaricano gli ultimi bilanci via OpenAPI, generare due pagine stampabili di bilancio riclassificato (comparazione 3 e 5 anni) nella sezione Salute Fiscale. Scelte utente: pag.1=3 anni / pag.2=5 anni (bilancio riclassificato completo in entrambe); usare i dati disponibili con voci mancanti come "n.d."; la visura aggiorna anche i campi già compilati.
- Backend `openapi_it_service.company_financials`: ora ritorna anche `bilanci_riclassificati` (max 5 anni). L'ultimo anno (IT-full) ha il dettaglio completo; gli anni precedenti usano le voci leggere di IT-advanced balanceSheets.all (ricavi, costo personale, totale attivo, PN, capitale sociale, dipendenti), il resto = None → "n.d.".
- `routes/extras_p1p2.py` endpoint `POST /anagrafiche/{aid}/salute-fiscale/da-openapi`: salva `bilanci_riclassificati` dentro `salute_fiscale_dati`.
- Nuovo endpoint `POST /anagrafiche/{aid}/applica-visura` (admin/collaboratore): mappa il JSON OCR visura sui campi anagrafica (ragione_sociale, partita_iva, codice_fiscale, indirizzo/comune/provincia/cap, telefono, email, pec, amministratore=legale rappr.) e su `corporate_profile` (ateco, capitale_sociale, numero_dipendenti, pec, legale_rappresentante); salva il raw in `visura_camerale_dati`; forza tipo=persona_giuridica se forma societaria. Aggiorna anche campi già compilati.
- Frontend `SaluteFiscaleTab.jsx`: pulsante "Carica visura camerale" (usa OCR esistente `/utility/ocr-visura-camerale` poi `applica-visura`); pulsanti "Anteprima 3 anni"/"Anteprima 5 anni" (gated su `bilanci_riclassificati`). `buildRiclassHTML()` apre una finestra stampabile (CE riclassificato a valore aggiunto + SP riclassificato finanziario, colonne per anno + Var.%, voci mancanti = "n.d.", bottone Stampa/Salva PDF).
- Test: `applica-visura` verificato via curl (mapping + persistenza corretti). UI verificata via screenshot (bottoni presenti, tab carica). Anteprima stampabile verificata: contiene VALORE DELLA PRODUZIONE, VALORE AGGIUNTO, EBITDA, TOTALE ATTIVO, 5 colonne anno (2024..2020), "n.d." per voci storiche mancanti. NB: flusso OpenAPI reale e OCR visura reale non testabili in preview (credenziali/documenti solo su Railway) — da validare dopo "Save to GitHub".

## 2026-06 — Report riclassificato PDF server-side
- Nuovo endpoint GET /api/anagrafiche/{aid}/report-azienda/riclassificato?anni=3|5 (routes/report_azienda.py)
  genera PDF A4 landscape del bilancio riclassificato (CE a valore aggiunto + SP finanziario),
  comparazione 3 o 5 anni, Var.% colorata, "n.d." per voci storiche non disponibili. Logo/note legali inclusi.
- SaluteFiscaleTab.jsx: aggiunti pulsanti "PDF riclass. 3 anni" / "PDF riclass. 5 anni"
  (data-testid sf-riclass-pdf-3-btn / sf-riclass-pdf-5-btn) accanto alle anteprime stampabili.
- Testato e2e con login admin + anagrafica seed: HTTP 200, application/pdf valido (3 e 5 anni). Record temp rimosso.

## 2026-06 — Visura: estrazione soci con percentuali
- ocr_visura.py: il prompt Gemini ora estrae anche l'array `soci` (denominazione/nome/cognome, codice_fiscale, quota_percentuale, tipo accomandatario/accomandante/unico...).
- applica_visura (extras_p1p2.py): i soci estratti vengono mappati in openapi_data.company.soci come {nome, quota, tipo, codice_fiscale}; la scheda Info Azienda → Soci/Azionisti li mostra con torta e percentuali. Nessuna modifica frontend necessaria.
- Testato e2e: applica-visura con 2 soci (90%/10%) → persistiti correttamente in company.soci, ragione_sociale preservata.

## 2026-06 — Calcolo INPS per gestione previdenziale
- inps_calculator.py: nuova mappa GESTIONI_INPS (aliquote di computo del montante) + helper gestione_info()/aliquota_computo(). calcola_pensione() ora accetta `gestione` e usa l'aliquota corretta (33% dipendenti, 24% artigiani, 24,48% commercianti, 26,07% GS professionista, 35,03% GS co.co.co, 16% prof. con cassa [stima], 19,5% medico ENPAM [stima], 24% coltivatore [stima]). Alias retro-compatibili per i vecchi tipo_lavoratore.
- Output calcolo arricchito con gestione/gestione_label/aliquota_computo_pct/stima_cassa.
- server.py: endpoint calcolo-pensione/preview, /calcola, /pensioni/calcola e analisi/calcola-pensioni-future ora derivano la gestione dal campo professione dell'anagrafica (o override body) e applicano l'aliquota corretta (eliminato lo 0.33 hardcoded nelle proiezioni e nel totale versato).
- Frontend AnagraficaDetail.jsx: campo "Professione" trasformato in menù a tendina "Professione / Gestione INPS" (GESTIONI_INPS + gestioneLabel); display read-only e preview calcolo mostrano la label + aliquota/stima.
- Testato e2e (anagrafica seed commerciante): preview, calcola e pensioni-future applicano 24,48% correttamente; stato civile + figli a carico già usati per i superstiti (numero_familiari).

## 2026-06 — Fix: Drive inbox OCR non allegava i documenti di polizza senza anagrafica
- Bug: in cloud_ocr_scanner._process_file l'allegato CRM veniva creato solo se c'era un'anagrafica abbinata (`if category != "da_smistare" and ana`). Un libretto di circolazione abbinato alla polizza per numero (senza anagrafica) veniva spostato nella cartella Drive (Polizze/{numero}/Libretto di circolazione/) ma NON allegato nel CRM. Esempio reale: polizza 184643314.
- Fix: condizione cambiata in `(ana or pol or sin)` — l'allegato ora viene creato per qualsiasi entità abbinata (polizza/sinistro anche senza anagrafica). _create_crm_attachment già gestiva correttamente entita_tipo=polizza.
- Testato: _create_crm_attachment con pol e ana=None crea l'allegato (entita_tipo=polizza, categoria=libretto_circolazione, visibile_cliente=True).
- NB produzione Railway: pubblicare con "Save to GitHub". I file già spostati fuori dall'inbox non vengono ri-scansionati: per la polizza 184643314 occorre ricaricare il libretto nell'inbox o allegarlo manualmente.

## 2026-06 — Fix: cancellazione registrazione Prima Nota non riportava il titolo ad arretrato
- Bug: eliminando da Prima Nota la copertura/incasso di un titolo, se non restavano altri movimenti il codice usava l'euristica (caricato_da_import AND data_copertura) che lasciava COPERTI i titoli importati anche quando la copertura derivava proprio dal movimento eliminato. Caso reale: polizza 732224551, titolo rimasto "coperto" invece di tornare arretrato.
- Fix (server.py):
  - _revert_entita_da_movimento: nel ramo "nessun movimento rimasto" ora usa lo SNAPSHOT dello stato pre-registrazione salvato sul movimento (titolo_coperto_pre / data_copertura_pre). Se manca lo snapshot e si elimina una copertura esplicita (copertura_titolo/anticipo) → ARRETRATO; fallback legacy import/setup solo per gli incassi.
  - Snapshot dello stato titolo (titolo_coperto_pre, data_copertura_pre) salvato alla creazione dei movimenti in: bulk_incassa, bulk copertura, marca-sospeso singolo, incasso singolo.
- Regole soddisfatte: (1) arretrato→coperto→del=arretrato; (2) arretrato→coperto+incasso→del=arretrato; (3) coperto(import)→incasso→del=coperto. Testati tutti e 4 i casi (incluso legacy senza snapshot) via _revert_entita_da_movimento.
- NB: il titolo 732224551 GIÀ cancellato resta coperto (il movimento non esiste più): usare l'azione "rimetti arretrato / storna copertura". Pubblicare su Railway con "Save to GitHub".

## 2026-06 — Documenti card: apertura/download + messaggio ripristino titolo
- Fix apertura documenti card anagrafica (es. Carta d'identità "Su Drive"): il link usava doc.url RELATIVO (/api/...). In produzione (frontend e backend su domini diversi) puntava al dominio del frontend → 404, non scaricava né visualizzava. Aggiunto helper fileHref() in AnagraficaDetail.jsx che rende l'url assoluto verso REACT_APP_BACKEND_URL e vi aggancia ?token= (un <a> non invia l'header Authorization). Applicato al link della card documenti.
  - Testato: /api/anagrafiche/{aid}/documenti/{tipo}/download?token= e /api/storage/...?token= → 200 application/pdf (401 senza token). download_cloud_file dal Drive funziona.
- Conferma ripristino: BrogliaccioTab ora mostra nel toast di eliminazione movimento lo stato a cui è tornato il titolo (es. "titolo ripristinato ad arretrato / a coperto (sospeso) / rimane incassato"), leggendo il campo `revert` già restituito da DELETE /contabilita/movimenti/{id}.

## 2026-06 — Documenti card: anteprima in-CRM + pulsante Scarica
- AnagraficaDetail.jsx (card "Documenti del cliente"): sostituito il semplice link con due pulsanti "Anteprima" e "Scarica" per ogni documento.
  - Anteprima: apre un Dialog con visualizzatore in-CRM (iframe per PDF, <img> per immagini) usando l'endpoint /api/anagrafiche/{aid}/documenti/{tipo}/download (Content-Disposition: inline) reso assoluto con token via fileHref(). Nessun download forzato.
  - Scarica: scarica il file via axios (responseType blob) + object URL, così porta l'header Authorization. Pulsante presente sia nella card sia dentro il dialog.
  - Nuovi data-testid: doc-preview-{tipo}, doc-download-{tipo}, doc-preview-dialog, doc-preview-frame/image, doc-preview-download.
- Testato e2e (login jacopo@schiantarelli.it, anagrafica 99b2fdc0): dialog anteprima si apre con l'iframe del PDF e il pulsante Scarica. Endpoint download inline → 200 application/pdf.

## 2026-06 — Visualizzatore documenti condiviso con zoom e rotazione
- Nuovo componente riutilizzabile DocumentPreviewDialog.jsx: anteprima in-CRM (iframe per PDF, <img> per immagini) con controlli Zoom +/- (30%–400%), Rotazione sx/dx (90°), Reimposta e pulsante Scarica.
- AnagraficaDetail.jsx: la card documenti ora usa il componente condiviso (rimpiazzato il dialog inline).
- DocumentiSezioneSplit.jsx (allegati di polizze, sinistri, titoli, libro matricola): sostituito il link <a> con AllegatoFileLink → nome cliccabile apre l'anteprima + pulsanti Anteprima/Scarica. URL allegato reso con ?token= per l'iframe; download via blob (porta l'auth).
- Testato: endpoint /allegati/{id}/download?token= → 200 PDF (su allegato con agenzia_tenant_id corretto); UI anteprima con zoom 120% e rotazione verificata. NB: 57 allegati polizza/sinistro nel tenant c5ae2d0e hanno agenzia_tenant_id='tenant-principale-schiantarelli' (disallineati) e non sono visibili a quel tenant — dato preesistente da sistemare a parte.

## 2026-06 — Card documenti anagrafica: Anteprima/Scarica spostati in alto a destra
- AnagraficaDetail.jsx: i pulsanti Anteprima/Scarica ora sono nella riga in alto a destra della card (accanto a RichiediDocCard, sotto il badge "caricato"), sempre visibili quando il documento esiste anche a card chiusa. Rimossi dal corpo espanso. Testato via screenshot.

## 2026-06 — Visura: soci S.a.s. e calcolo % quote dal valore in euro
- Bug: nel grafico Soci/Azionisti compariva un solo socio al 100%. Nella visura le quote sono espresse in euro (es. 6.000 / 4.000 su capitale 10.000) e un solo accomandatario veniva estratto.
- ocr_visura.py: prompt soci aggiornato → estrae SEMPRE tutti i soci (accomandatari + accomandanti) con codice fiscale, nuovo campo quota_valore (euro) oltre a quota_percentuale; abbinamento quota↔socio tramite CF.
- extras_p1p2.py applica-visura: _num robusto per formato italiano (6.000,00); calcolo percentuale = quota_valore / capitale_sociale * 100 (fallback: somma quote). company.soci ora include quota (%) e quota_valore.
- Testato e2e: Vanoli 6.000 → 60%, Schiantarelli 4.000 → 40% su capitale 10.000. Il grafico e la tabella già usano company.soci. NB: ricaricare la visura in Salute Fiscale per aggiornare i soci esistenti.

## 2026-06 — Visura OCR multi-pagina (fix soci mancanti/quote)
- Causa reale del "1 solo socio senza quote": ocr_visura inviava il PDF a Gemini come IMMAGINE SINGOLA → veniva letta solo la prima pagina. I soci accomandanti e le quote (euro) sono nelle pagine 3-4 della visura, quindi persi; inoltre alcuni PDF davano errore Gemini "Unable to process input image".
- Fix: aggiunta _pdf_to_images() (PyMuPDF) che converte il PDF in un PNG per pagina (max 12, zoom 2x); estrai_dati_visura invia TUTTE le pagine come lista di ImageContent.
- Testato sul PDF reale: estratti Vanoli (quota_valore 6000) + Schiantarelli (4000) + capitale 10.000,00 + 1 amministratore. applica-visura calcola 60%/40%.
- CAVEAT: "Aggiorna dati" (OpenAPI LIVE) può sovrascrivere openapi_data.company.soci con i dati OpenAPI (che per questa SAS hanno 1 solo socio). Dopo aver caricato la visura NON premere Aggiorna dati, oppure proteggere i soci visura (next action).

## 2026-06 — Bilancio riclassificato: sempre visibile + opzione "Ultimo anno"
- Problema: i pulsanti del bilancio riclassificato comparivano SOLO se esisteva bilanci_riclassificati, assente nelle aziende elaborate prima della feature → utente non li trovava.
- SaluteFiscaleTab.jsx: nuovo riclassEff = bilanci_riclassificati se presenti, altrimenti ricostruito dall'ultimo anno (bilancio_estratto). Pulsanti ora visibili con qualsiasi bilancio. Aggiunta opzione "Ultimo anno" (anni=1) oltre a 3 e 5, sia anteprima sia PDF. Gruppo etichettato "BILANCIO RICLASSIFICATO". buildRiclassHTML: colonna Var nascosta per anno singolo, titolo corretto.
- report_azienda.py /report-azienda/riclassificato: accetta anni=1; se bilanci_riclassificati vuoto ricostruisce l'ultimo anno da bilancio_estratto; colonna Var nel PDF nascosta per anno singolo.
- Testato: PDF anni 1/3/5 → 200 PDF valido anche da solo bilancio_estratto; UI verificata su AUTOTRASPORTI VIVIANI (riclass vuoto) → i 6 pulsanti compaiono.
- NB: per il confronto reale 3/5 anni serve "Compila da OpenAPI" (recupera balanceSheets.all e salva i bilanci multi-anno).

## 2026-06 — Riclassificato: esclusione anni senza dati (ultimi N disponibili)
- Problema: la colonna dell'anno più recente (es. 2026, bilancio non ancora depositato) era tutta "n.d.".
- Fix: sia buildRiclassHTML (SaluteFiscaleTab.jsx) sia _build_riclass_pdf/endpoint (report_azienda.py) filtrano gli anni tenendo solo quelli con dati (almeno uno tra ricavi/valore_produzione/totale_attivo/patrimonio_netto/utile_netto/costi_personale/ebitda/totale_debiti) PRIMA di prendere gli ultimi N. Così "3 anni" = ultimi 3 esercizi disponibili (es. 2025-2024-2023).
- Testato: riclass con 2026 vuoto + 2025/2024/2023/2022 → "3 anni" mostra 2025-2024-2023; "5 anni" mostra 2025-2024-2023-2022.

## 2026-06 — Margine di Contribuzione: scenari multipli per anno
- MargineContribuzione (SaluteFiscaleTab.jsx): da un solo scenario a GESTIONE MULTI-SCENARIO salvati per cliente in anagrafiche.salute_fiscale_scenari_list (array {id, nome, anno, rows, giorni, gScen, riskTol, riskApp, updated_at}).
- Barra scenari: selettore (+ Nuovo), nome, anno, pulsanti Salva (crea/aggiorna per id), Copia, Elimina, Stampa (apre finestra stampabile con tabella MDC + KPI). data-testid: mdc-scenario-select/nome/anno, sf-salva-scenari, mdc-copia/elimina/stampa.
- Persistenza via PUT /anagrafiche/{id} (campo libero, già supportato). Testato: round-trip salute_fiscale_scenari_list 200 e riletto; UI verificata su AUTOTRASPORTI VIVIANI.
- NB: resta aperta la richiesta "riclassificato con TUTTE le voci CEE di dettaglio" (schema completo OpenAPI) — grande, non ancora implementata.

## 2026-06 — Riclassificato CEE completo (tutte le voci di dettaglio)
- openapi_it_service.py: nuova _cee_detail(d) estrae TUTTE le voci dello schema CEE dall'IT-full (productionValue, productionCosts, revenuesFinancialCharges, annualResult, assets, inventory, credits, financialAssets, cashEquivalents, netWorth, debts, liabilities) come lista ordinata [{section, code, label, value}] usando le descrizioni fornite dall'API. company_financials ora ritorna bilancio_dettaglio_cee {anno, voci}.
- extras_p1p2 da-openapi: persiste salute_fiscale_dati.bilancio_dettaglio_cee.
- SaluteFiscaleTab.jsx: nuovo buildDettaglioCeeHTML; il pulsante "Completo ultimo anno" apre l'anteprima stampabile con TUTTE le voci CEE (sezioni + codici + importi, n.d. se mancanti).
- report_azienda.py: endpoint riclassificato anni=1 → se esiste bilancio_dettaglio_cee genera _build_cee_detail_pdf (PDF A4 con tutte le voci). 3/5 anni restano aggregati.
- Testato: _cee_detail su schema mock (11 voci, sezioni+label corretti); PDF completo endpoint anni=1 → 200.
- LIMITE: il dettaglio completo è disponibile solo per l'ULTIMO bilancio depositato (IT-full); gli anni storici (3/5) restano aggregati. Serve ri-premere "Compila da OpenAPI" per popolare bilancio_dettaglio_cee.

## 2026-11-06 — Alert: fuso Roma, orologio UI, template digest/veicolo, diagnosi mancati invii
- **Root cause mancati avvisi (tenant reale c5ae2d0e)**: (1) scheduler avvisi SOSPESO (switch off) → nessun invio automatico; (2) nessuna regola "Documento d'identità" attiva salvata; (3) WhatsApp senza istanza connessa → canale sempre saltato; (4) bug latente fuso: scheduler girava in UTC, orari slittati di 1h vs Roma.
- **Fix fuso orario** (`scheduler_alert.py`): nuovo `ROME_TZ=Europe/Rome`, `_now_rome()`, `_today()` ora in Roma; `_tick`, `_tick_copertura` e APScheduler (`AsyncIOScheduler(timezone=ROME_TZ)`) usano l'ora italiana. Gli orari cron delle regole e l'orario globale sono ora valutati in ora italiana.
- **Template digest implementati** (`scheduler_alert.py`): `sospesi_settimanali` e `arretrati_settimanali` ora producono 1 payload per collaboratore con totali (`n_titoli`/`totale_sospesi`, `n_arretrati`/`totale_arretrati`). Prima `resolve_payloads` tornava [] → non inviavano nulla.
- **Veicolo**: `documento_veicolo_mancante` ora è collegato allo scheduler (`_esegui_rule` chiama `run_sollecito_documento_veicolo`). Prima non partiva dal tick.
- **Frontend** (`Alert.jsx`): nuovo `RomeClock` (data calendario + ora Italia Europe/Rome live, aggiornamento 1s, timeZoneName); etichette orari regole con "(ora it.)"; label "Ora (Italia)" nella card scheduler; banner giallo quando lo scheduler è "Sospeso".
- **Audit template (tenant reale, read-only)**: polizza_scaduta_* + polizza_in_scadenza ✅; compleanno ✅ (9); titolo_scaduto_oltre ✅ (14); documento_id_scaduto ✅ (campo `ci_data_scadenza` corretto, popolato solo su clienti con data inserita); documento_aziendale ✅ (0 oggi); sospesi/arretrati ✅ (8+8 dopo fix); veicolo ✅ (dopo wiring).
- **Verificato**: orologio Roma 18:53 CET in UI; recipient resolution (digest→collaboratore email, cliente Jacopo→email+whatsapp, whatsapp saltato no istanza). NESSUN invio reale innescato in test (evitato run-now su dati reali).

## 2026-11-06 (2) — Pannello Diagnostica avvisi (per produzione Railway)
- NB AMBIENTE: la preview Emergent usa MongoDB LOCALE (localhost/test_database), NON il DB di produzione Railway. Da qui non si leggono i dati live di Railway.
- **Backend** (`routes/alert.py`): nuovo endpoint sola-lettura `GET /api/alert-diagnostica?cognome=` (admin). Ritorna: ora server UTC + ora Italia, scheduler attivo/orario globale, n. regole totali/attive/programmate-attive, dettaglio regola documento_id, provider email/sms/whatsapp, istanze WhatsApp totali/connesse, lookup cliente (ci_data_scadenza, canali) e lista `problemi_rilevati` + `tutto_ok`.
- **Frontend** (`Alert.jsx`): `DiagnosticaCard` con input cognome + bottone "Esegui diagnostica" e report a checklist (verde/ambra) + box problemi. Verificato in UI sul tenant locale c5ae2d0e: scheduler SOSPESO, 0/2 regole attive, regola documento identità assente, email configurata, WhatsApp 0/1 connesse.
- **Per Railway**: le modifiche vanno deployate su Railway (push su GitHub → redeploy) per poter aprire la Diagnostica direttamente in produzione.

## 2026-11-07 — Diagnostica: esposto il MESSAGGIO D'ERRORE reale degli invii
- PRODUZIONE Railway: dopo attivazione, la regola documento_id parte e trova i destinatari, ma EMAIL→errore e WHATSAPP→skipped. Test email: errori:1.
- **Backend** (`routes/alert.py` `/alert-diagnostica`): aggiunti `ultimi_errori` (ultimi 12 eventi status errore/skipped con `error_message`, canale, destinatario, data), `whatsapp_server_ok` (presenza server_url Evolution) e relativo problema in checklist.
- **Frontend** (`Alert.jsx`): DiagnosticaCard mostra box rosso "Ultimi invii non riusciti (motivo reale)"; Storico invii mostra il testo errore inline sotto l'esito (prima era solo tooltip title, invisibile su mobile).
- STATO: NON risolto finché non si leggono i messaggi d'errore reali da produzione. Ipotesi: email = auth/relay SMTP; whatsapp = numero destinatario assente o api_key Evolution mancante.
- Prossimo: utente redeploy su Railway → esegue Diagnostica → invia screenshot del box "Ultimi invii non riusciti" → fix mirato.

## 2026-11-07 (2) — FIX cause reali: email SMTP SSL/465 + WhatsApp prefisso +39
- Errori reali da produzione: EMAIL "Connection unexpectedly closed" (server SMTP su porta 465 SSL implicito, ma il codice faceva sempre SMTP+STARTTLS); WHATSAPP Evolution API 400 {"exists":false,"number":"3402934389"} (numero inviato senza prefisso internazionale).
- **Fix email** (`alert_dispatcher.py` send_email): se `smtp_port==465` o `smtp_ssl` true → usa `smtplib.SMTP_SSL`; altrimenti SMTP+STARTTLS come prima. (Tipico caso Aruba smtps.aruba.it:465.)
- **Fix whatsapp** (`alert_dispatcher.py` send_whatsapp): normalizzazione numero → strip non-cifre, rimuove `00` iniziale, se <=10 cifre antepone prefisso `WHATSAPP_DEFAULT_CC` (default "39"). Verificato: 3402934389/00393402934389/+39.../393402934389 → 393402934389.
- NOTA: alcune righe whatsapp "saltato: destinatario assente" = quel record anagrafica non ha cellulare/whatsapp salvato.
- STATO: fix applicati e logica verificata in locale; consegna reale SMTP/Evolution NON verificabile dalla preview (serve redeploy Railway + retest). Se email ancora KO dopo redeploy: confermare host/porta SMTP (465 vs 587).

## 2026-11-09 — Email avvisi via GMAIL API (OAuth per-agenzia) + IMAP allegati solo su Drive
- VERIFICA richiesta: la tab Librerie → Comunicazioni ha già Email = Google (Gmail/Workspace) via App Password = SMTP (smtp.gmail.com:587). È ATTIVA ma SMTP è bloccato da Railway → "Connection unexpectedly closed". Resend scartato su richiesta utente.
- **Nuovo invio email = Gmail API ufficiale, token per-agenzia** (direttiva utente):
  - `routes/cloud_storage.py`: scope esteso `drive + gmail.send + userinfo.email`; client OAuth globale ora legge `GOOGLE_CLIENT_ID/SECRET` con fallback a `GOOGLE_DRIVE_CLIENT_ID/SECRET`; al callback OAuth salva `account_email` (mittente) nella connessione del tenant.
  - `gmail_send.py` (NUOVO): `send_gmail()` (POST gmail.googleapis.com users/me/messages/send, MIME base64url, rileva 403 insufficientPermissions → GmailNeedsReconsent) e `send_tenant_email(tenant_id,...)` che usa il refresh_token dell'agenzia (cloud_connections) e `_fresh_access_token`.
  - `alert_dispatcher.send_email`: PRIMA Gmail API col token del tenant (se Google collegato); FALLBACK legacy SMTP; Resend rimosso. Errori azionabili (ricollega Google / configura SMTP).
  - `routes/alert.py` /alert-diagnostica: campi `email_gmail_api_ok`, `email_gmail_account`, `email_smtp_ok`; problema "Google collegato ma senza gmail.send → ricollega". Frontend Alert.jsx: riga "Email (invio): Gmail API · account / SMTP".
- AZIONE UTENTE per attivare: redeploy Railway → Librerie → Cloud Storage → **ricollega Google** (grant gmail.send + userinfo.email; serve anche aggiungere lo scope gmail.send nella OAuth consent screen del progetto Google Cloud). Poi gli avvisi email partono via Gmail API (HTTPS, non bloccato).
- IMAP→Drive (sessione precedente): allegati email archiviati SOLO su Google Drive via `_store_email_doc`; bypass objstore/GridFS; fallback inline b64 pending→Drive; download/backfill gestiscono inline. Verificato: allegato email → provider google_drive, cloud:True.
- Verificato in preview (mirror tenant c5ae2d0e): diagnostica mostra Google connesso solo-Drive → email_gmail_api_ok False, messaggio ricollega; import OK, backend sano.

## 2026-11-09 (3) — Gmail = integrazione OAuth AUTONOMA (separata da Drive e Contatti)
- Direttiva utente: separazione totale dei servizi Google, chiavi indipendenti per agenzia.
- **Drive**: scope ripristinato a SOLO `auth/drive` (rimosso gmail.send dalla connessione Drive).
- **Gmail (nuovo provider "gmail")** riusa l'infra OAuth di cloud_storage:
  - `routes/cloud_storage.py`: `GMAIL_SCOPE = gmail.send + userinfo.email`; `_provider_cfg_async`/`_load_tenant_config` gestiscono provider "gmail" (chiavi per-agenzia in `cloud_oauth_configs` provider=gmail, fallback ENV globale GOOGLE_CLIENT_ID/SECRET con retrocompat GOOGLE_DRIVE_*); regex endpoint admin-config/oauth-url/delete estese a `gmail`; `prompt=consent`; callback salva refresh_token in `cloud_connections` provider=gmail + `account_email` (mittente); callback salta init-cartelle/backfill per gmail. Nuovi endpoint `GET /gmail/status`, `DELETE /gmail/disconnect`.
  - `gmail_send.send_tenant_email`: usa connessione provider="gmail" (`_fresh_access_token("gmail",...)`).
  - `alert_dispatcher.send_email`: Gmail API via connessione dedicata "gmail"; fallback SMTP solo per Microsoft/custom.
  - `routes/librerie.py` comunicazioni/test email: instrada via Gmail API se connessione gmail presente, altrimenti SMTP.
  - `routes/alert.py` diagnostica: legge connessione provider="gmail" per `email_gmail_api_ok`/`email_gmail_account`.
- **Frontend** `Librerie.jsx`: sezione Comunicazioni → Email, provider Google ora mostra card `GmailOAuthCard` (stato connesso + mittente, credenziali proprie/globali, Connetti/Ricollega/Scollega); App Password nascosta per Google (resta per Microsoft/SMTP).
- Verificato preview: gmail/status source=env configured; oauth-url scope = SOLO gmail.send+userinfo.email, prompt=consent; UI card renderizza; import+backend OK.
- AZIONE UTENTE: redeploy Railway → Comunicazioni → Email (Google) → "Connetti Gmail" (serve Gmail API abilitata + scope gmail.send nella OAuth consent screen del progetto Google). Drive e Contatti restano collegamenti separati.

## 2026-11-09 (4) — Coda di invio asincrona con throttling per-agenzia (anti-spam / anti rate-limit)
- NUOVO `comm_queue.py`: collezione `comm_queue`; worker asincrono in background per-tenant (isolamento: 1 drain task per agenzia, parallelo tra agenzie; `_active_tenants` evita doppioni).
  - Delay 5-10s tra invii della STESSA agenzia (`asyncio.sleep(random.uniform(5,10))`), non blocca il thread principale.
  - Retry con exponential backoff (30s·2^n + jitter) su errori retryable (429/rate/timeout/disconnect/5xx), max 3 tentativi → poi `failed`. Errori permanenti (es. auth 535) → subito failed. Verificato offline: ok→sent, 429→retry attempts=1.
  - Stati: pending→sending→sent|failed|retry. Aggiorna anche l'AlertEvent collegato (storico).
  - `queue_status(tenant)` per dashboard.
- `alert_dispatcher.dispatch_rule`: email e whatsapp NON più inline → `comm_queue.enqueue(...)` + AlertEvent status "queued" (stats["queued"]); inapp/sms restano inline. Rimosso il throttle inline (il delay lo dà la coda).
- `alert_dispatcher.send_whatsapp`: prima dell'invio chiama Evolution `/chat/sendPresence/{instance}` presence "composing" + `asyncio.sleep(2)` (anti-bot Meta), best-effort.
- `server.py` startup: `comm_queue.start_comm_queue()` accanto allo scheduler avvisi.
- `routes/librerie.py`: `GET /librerie/comunicazioni/queue-status` (admin).
- Frontend `Librerie.jsx`: `CodeInvioCard` in cima a Comunicazioni → contatori (in attesa/in invio/inviati/falliti) per canale + ultimi falliti, polling 5s.
- Verificato: worker avviato nei log, endpoint OK, transizioni coda OK (test offline, nessun invio reale), UI renderizza.

## 2026-11-09 (5) — Controllo rigoroso Alert & Automazioni (toggle + orario per-regola)
- SCHEDULER (`scheduler_alert._tick`): RIMOSSA l'ereditarietà dell'orario master. Una regola schedule/soglia senza `cron` proprio NON parte (log debug "in attesa di configurazione"). Solo regole `attivo:True` elaborate; interruttore generale spento → nessun invio. Fuso sempre Europe/Rome (_now_rome). Log esecuzione ora include id regola + ora.
- GATING ATTIVO: già garantito — `dispatch_rule` esce subito se `attivo` è falso; `dispatch_evento` filtra `attivo:True` (evento spento → nessun accodamento). Quindi nessun messaggio entra in `comm_queue` da regola non attiva.
- TOGGLE (`routes/alert.toggle_alert_rule`): all'attivazione di una regola schedule/soglia SENZA cron, assegna un orario esplicito di default (dalla config globale) e restituisce `warning`; così la regola diventa subito operativa senza ereditare runtime.
- UI (`Alert.jsx`): card "Avvisi programmati" ora spiega che l'orario è solo un default PROPOSTO per le nuove regole e che una regola senza orario/disattivata NON parte. `cronLabel(null)` → "⚠ Orario non impostato". Modal regola: rimosso il check "usa orario globale"; selettore "Quando eseguire" SEMPRE esplicito (Ripeti giorno/settimana/mese + ora) con anteprima; al salvataggio il cron è sempre valorizzato (buildCron). Toggle mostra il warning. Storico invii: mostra data+ora in Europe/Rome, nome regola + id (#8char), tooltip id completo.
- Verificato: toggle su regola senza cron → cron "0 11 * * *" + warning; ripristinato compleanno 09:00; frontend compila; pagina Alert render OK.

## 2026-11-11 — Titoli: visibilità per stato_carico
- Lista globale **Titoli** mostra solo titoli UFFICIALI: validati + creati a mano (default `validato`) + legacy senza stato_carico.
- I Carichi mensili ancora **da validare** (`in_attesa`) restano nei Carichi e compaiono in Titoli solo dopo la validazione. Annullati sempre esclusi.
- Dettaglio polizza continua a mostrare tutti i titoli non annullati (incl. in_attesa).
- Verificato (polizza 730105336): Titoli=14 validati, 2 in_attesa nascosti.

## 2026-11-11 — Azzera accessori/diritti: ricalcolo premio (fix) + conferme import Omnia
- **Fix bug #1**: lendpoint POST /admin/azzera-accessori-diritti ora RICALCOLA il premio.
  - Titoli (da_incassare, non in prima nota, accessori>0): importo_lordo = netto+imposte+ssn, accessori=0 (toglie accessori sia inclusi che separati). Validato: 132->122.
  - Polizze (accessori/diritti POSITIVI, anche su garanzie): premio_lordo -= (premio_accessori+diritti); garanzie lordo -= (accessori+diritti); azzera entrambi.
  - Filtro corretto da $ne:0 (matchava anche campi assenti) a $gt:0.
  - Protezione: titoli con solo lordo senza scomposizione (netto=0) NON vengono toccati.
  - LIMITE noto: i record gia azzerati in un run precedente (accessori=0) non sono recuperabili (importo perso); il premio resta quello attuale.
- **Conferma #2**: import Omnia NON importa accessori/diritti (forzati a 0 in ania_importer).
- **Conferma #3**: import Omnia NON riscrive i titoli validati; crea arretrati solo per polizze nuove/sostituenti in modo idempotente (anti-doppione su effetto); storna solo i da_incassare non coperti delle sostituite.

## 2026-11-12 — Import Omnia: titolo mancante su sostituzione con premio negativo (fix)
- Causa: _crea_titoli_import saltava i titoli con premio_lordo <= 0. Le sostituzioni con conguaglio NEGATIVO (rimborso, es. -96,50) non generavano il titolo.
- Fix: per is_sost crea comunque il titolo (anche premio negativo); salta solo lo zero esatto. New business puro invariato (lordo>0).
- Testato: sostituente premio -96,50 -> titolo tipo sostituzione, da_incassare, stato_carico validato (visibile nei Titoli).
- Per recuperare la polizza gia importata in produzione: ri-eseguire lo stesso flusso Omnia (idempotente, anti-doppione) dopo il deploy.

## 2026-11-12 — Inbox documenti: cliente errato (compagnia) + selezione polizza
- OCR polizze: il prompt ora distingue COMPAGNIA (assicuratore) dal CONTRAENTE (cliente); estrae contraente_cognome/nome/ragione_sociale e NON mette piu la compagnia nel cognome.
- Nuovo helper _infer_targets (routes/documenti_inbox.py): per i documenti di polizza il cliente autorevole e il CONTRAENTE della polizza (trovata per numero/targa), NON il nome OCR (spesso la compagnia). Aggiunto parsing del NOME FILE (numero polizza, targa, nome cliente) come fallback. Usato sia in /analyze sia in retry-auto-archive.
- Frontend DocumentiInbox.jsx: selettore Polizza ora ricercabile (numero/targa/cliente), non piu vincolato alla scelta del cliente; selezionando la polizza si auto-compila il cliente.
- Testato: doc polizza con OCR=GROUPAMA -> cliente ANGELINI via numero da filename; libretto -> polizza per targa; nome-solo da filename -> anagrafica.
- NB: i documenti pending gia salvati con cliente errato non si auto-correggono; nella modale si puo togliere il cliente (X) e cercare la polizza corretta (auto-compila il cliente). I nuovi scan matchano corretti.

## 2026-11-12 — Inbox: match targhe libretti piu accurato (meno scarti)
- OCR prompt libretto: targa senza spazi/trattini, formati IT (nuove/vecchie/moto), avviso confusione O/0 I/1 B/8 S/5 Z/2, distinzione targa vs telaio.
- _guess_from_filename riscritto (per-token): estrae targa (nuove AA000AA + vecchie/moto alfanumeriche) senza prendere le cifre della targa come numero polizza.
- _norm_targa + match regex ^0*TARGA$ (case-insensitive): ignora spazi/trattini e zeri di padding iniziali (targhe salvate zero-padded).
- Auto-archiviazione: un match DETERMINISTICO su polizza (numero/targa) auto-archivia anche a confidenza media/bassa (riduce gli scarti dei libretti). Vale in /analyze e in retry-auto-archive.
- retry-auto-archive ora ri-matcha e PERSISTE i target per TUTTI i pending polizza/anagrafica (anche bassa confidenza) -> la modale di revisione si pre-compila.
- Testato: parsing filename (6 casi), match targhe padded/normali/con spazi.

## 2026-11-12 — Inbox polizze: match per CF/P.IVA del contraente
- OCR polizza: estrae contraente_codice_fiscale e contraente_partita_iva (del CLIENTE, mai della compagnia).
- _infer_targets: nuovo match anagrafica per CF e P.IVA del contraente (chiavi forti), dopo il contraente della polizza. Per i doc di polizza la P.IVA generica (spesso = compagnia) NON viene usata.
- Cosi un documento di polizza aggancia il cliente anche se il numero polizza non e ancora nel DB -> meno scarti.
- Testato: CF contraente, P.IVA contraente, e P.IVA compagnia (correttamente non associata).

## 2026-11-12 — Sospesi: pulsante Incassa tagliato (fix layout tabella)
- TitoliSospesi.jsx: tabella avvolta in <div overflow-x-auto>; colonna azioni resa sticky a destra (classe col-azioni) -> il pulsante Incassa resta sempre visibile (prima la Card overflow-hidden lo tagliava per header nowrap che eccedevano la larghezza).
- Aggiunto min-w-[980px] cosi su schermi stretti la tabella scorre invece di comprimere le colonne.
- Pattern identico a BrogliaccioTab/DatiCompagnieTab (gia funzionanti).
- NB: verifica visiva via screenshot non riuscita per race di login nel tool; frontend compila senza errori.

## 2026-11-12 — Regolazione premio (tab polizza): Crea/Modifica/Elimina + ordinamento
- Dialog RegolazionePremioDialog ora RENDERIZZATO in PolizzaDetail (prima il bottone non apriva nulla nel tab).
- Crea regolazione: apre il dialog vuoto per inserire i dati.
- Modifica regolazione: abilitato solo con UNA riga selezionata; riapre il dialog pre-compilato (initial) e al salvataggio SOSTITUISCE la riga (elimina la vecchia).
- Elimina regolazione: funziona solo su righe selezionate; backend BLOCCA (400) se la regolazione ha un titolo collegato coperto/incassato.
- Regolazioni calcolate ordinate per periodo (anno) decrescente, poi per data.
- Testato backend: elimina coperto->400, non-coperto->ok. Frontend compila.

## 2026-11-12 — Storico Prima Nota + KPI dashboard prima nota aperte
- Storico Prima Nota (Contabilita.jsx): rimossa colonna ID; aggiunta colonna STATO (badge "Chiusa") come prima colonna e colonna "Chiusa il" (data+ora, fuso Europe/Rome) subito dopo.
- Backend list_chiusure_giorno: filtra riaperta_at=None -> le chiusure RIAPERTE spariscono dallo storico finche non ri-chiuse (match richiesta "togliere momentaneamente").
- Nuovo endpoint GET /contabilita/prima-nota-aperte: giorni passati con movimenti ma senza chiusura attiva. Testato: count=4.
- Dashboard: nuova KPI "Prima Nota aperte" (rossa/allerta se >0, verde se tutto chiuso), link a /contabilita, solo non-client.
- Verificato via curl: storico esclude riaperte e include created_at; endpoint aperte ok. Frontend compila. (Screenshot UI non riuscito per login tool nel browser isolato.)

## 2026-11-12 — Sospesi: griglia ottimizzata (gap rimosso)
- TitoliSospesi.jsx: colonna Cliente resa "greedy" (w-full) per assorbire lo spazio extra; altre colonne whitespace-nowrap/compatte -> eliminato il gap tra Ramo/Targa e Coperto il. Frontend compila.

## 2026-11-12 — Sospesi: riepilogo collaboratore come filtro rapido
- Righe "Riepilogo per collaboratore" cliccabili: filtrano istantaneamente la tabella sottostante (toggle on/off), con riga attiva evidenziata e link "Mostra tutti".
- Filtro collaboratore spostato lato CLIENT: il riepilogo e i KPI in alto restano sempre completi (si puo passare da un collaboratore all altro al volo); la tabella e il suo totale riflettono il filtro.
- Il select "Filtra per collaboratore" e sincronizzato e include l opzione "Senza collaboratore".
- Backend /titoli/sospesi e /titoli/sospesi-storico: gestito collaboratore_id="__none__" (titoli senza collaboratore) per export/stampa. Verificato via curl.

## 2026-11-12 — Inbox: retry auto-archivio anche sui documenti "ALTRO"
- Causa: i libretti erano classificati tipo=ALTRO (OCR fallito su file 0 kB) e il retry saltava gli "altro" -> sembrava non fare nulla.
- Fix: _guess_tipo_from_filename deduce il tipo dal NOME FILE (es. "LIBRETTO FR798LT.pdf" -> libretto) quando OCR=altro; il retry ora li processa, aggancia la polizza dalla targa/numero del nome file, corregge la classificazione (tipo_documento) e auto-archivia se c è match deterministico.
- Messaggio del pulsante piu chiaro: toast info quando nessun abbinamento trovato (prima mostrava 0/0/0 e sembrava rotto).
- Testato: inferenza tipo + match polizza da targa nel nome file.

## 2026-11-12 — Retry auto-archivio: frontespizio/ALTRO ora vanno in Polizza
- CAUSA: tipo "polizza_frontespizio" NON era in DOC_ROUTING -> instradato per default su ANAGRAFICA; i doc "ALTRO" senza parola chiave nel nome venivano saltati anche con polizza trovata.
- FIX: mappato polizza_frontespizio/frontespizio -> card Polizza. Retry ora decide la destinazione con priorita: tipo riconosciuto (incl. varianti polizza_*) -> cartella di upload (scope) -> target trovato (una polizza trovata vince sull anagrafica). Passato entita_tipo esplicito a _do_save.
- Fallback: se routed=polizza ma polizza non trovata, ripiega su anagrafica se presente.
- Fix display card: "Polizza trovata" mostrava vuoto (usava .numero invece di .numero_polizza).
- Testato: polizza_frontespizio -> Polizza (match per numero da nome file); retry gira senza errori.

## 2026-11-12 — Inbox: avanzamento per-card su "Riprova auto" + ordinamento pending
- Backend: estratto `_retry_one_pending()`; nuovi endpoint `GET /documenti-inbox/pending-ids` e `POST /documenti-inbox/{iid}/retry-auto-archive` (singolo doc). Bulk retry invariato nel comportamento.
- Frontend (DocumentiInbox.jsx): "Riprova auto-archivio" ora riprocessa i pending UNO alla volta; ogni card mostra la barra OcrProgressBar mentre viene elaborata, poi esito (Archiviato / Nessun abbinamento / Errore).
- Le card pending ("Da rivedere") sono ordinate in alto, i documenti salvati sotto.

## 2026-11-12 — Fix routing OCR: "C.I." finiva in "Altri documenti"
- cloud_ocr_scanner.py: `_norm_folder_key` reso robusto ad accenti/apostrofi (dritti e tipografici) e punti → il nome cartella Drive "Carta d'Identità" ora matcha sempre l'hint carta_identita (prima falliva con apostrofo tipografico o accento).
- Aggiunto fallback deterministico filename→tipo in `_classify_document`: se l'AI è incerta (tipo 'altro'/confidenza bassa) ma il nome file è chiaro (es. "C.I. ...", "patente", "polizza"), il tipo viene forzato.
- documenti_inbox.py: `_guess_tipo_from_filename` ora riconosce anche il prefisso "C.I.".
- Testato a livello unitario (hint_from_folder_name + _tipo_from_filename + _guess_tipo_from_filename). E2e Drive-scan non riproducibile in preview (dati in produzione + connessione Drive live).

## 2026-11-12 — Libro Matricola: ricerca targa veicolo + allegato al veicolo corretto
- RICERCA GLOBALE (server.py /api/search): ora cerca le targhe anche in db.applicazioni (Libro Matricola) e restituisce la polizza flotta correlata con campo `matricola_targa`. TopBar.jsx mostra un badge Truck con la targa veicolo abbinata (data-testid search-matricola-targa). Verificato: q=AA41979 → polizza 153000736 (MAGANETTI SPEDIZIONI SPA) con matricola_targa=AA41979.
- ROUTING OCR LIBRETTO (routes/documenti_inbox.py _infer_targets): matching per targa esteso a db.applicazioni. Se la targa esiste solo in un'applicazione, aggancia la polizza flotta correlata e usa l'INTESTATARIO dell'applicazione (proprietario) come anagrafica, non il contraente/leasing. La targa diretta su polizza mantiene priorità. Prompt OCR libretto aggiornato per distinguere proprietario vs ente leasing.
- INBOX — SELETTORE VEICOLO MANUALE (DocumentiInbox.jsx ReviewDialog): quando entità=polizza e la polizza ha applicazioni, appare un selettore "Veicolo / Applicazione" ricercabile per targa/numero (454 veicoli → combobox con filtro). Il save invia `applicazione_matricola_id`; Allegato.applicazione_matricola_id lega il doc al veicolo.
- FIX backend _do_save: rispetta la scelta ESPLICITA dell'utente (anche "nessun veicolo"=null) via `'applicazione_matricola_id' in body`, non ripiega più silenziosamente sull'OCR target; VALIDA che l'applicazione appartenga alla polizza scelta (db.applicazioni {id, polizza_id}) → evita libretto sul veicolo di un'altra polizza.
- FIX minori frontend: checkbox "Salva come avatar" mostrata solo se destinazione=anagrafica; clear anagrafica ora resetta anche polLabel/appId.
- NB: la targa GY308AK del PDF segnalato NON esiste in polizze/applicazioni/veicoli del tenant → non associabile automaticamente finché il record veicolo non esiste (limite dati, non bug). Resta possibile l'allegato manuale.
- Testato: testing_agent iteration_133 (backend 6/6 pytest, frontend e2e) + screenshot e2e del selettore veicolo ricercabile sul tenant reale.

## 2026-06-12 — Documenti annuali collaboratori (checklist conformità)
- Nuova pagina sidebar "Documenti Collaboratori" (/documenti-collaboratori, pages/DocumentiAnnualiCollab.jsx).
  - Admin: panoramica immediata di tutti i collaboratori con pallini stato + badge "Completo"/"N da sistemare", espansione riga, upload/replace/delete per voce, selettore anno (2027..2023).
  - Collaboratore/dipendente: vede SOLO la propria checklist, upload via /api/me/documenti-annuali.
- Checklist annuale configurabile (admin): GET/PUT /api/config/documenti-annuali-collab. Default: Casellario giudiziale, Carichi pendenti, Attestato corso IVASS (30h, stato auto dalle ore), Visura/iscrizione RUI, Autocertificazione antiriciclaggio. Possibile aggiungere/rimuovere card.
- Stato per anno: Presente / In scadenza (<=30gg) / Scaduto / Mancante / Parziale (IVASS).
- Documenti salvati in users.documenti_collab (campi req_key, anno, tipologia, data_scadenza). I certificati gia' presenti (users.certificati_collab, match per tipologia+anno) sono COLLEGATI alla checklist in sola lettura (etichetta "da Certificati").
- Editor Librerie > tab Certificati: pannello inline "Checklist documenti annuali" (ChecklistAnnualeInline) che riusa CollabCard, con selettore anno e link "Apri vista completa".
- Endpoint: GET /api/collaboratori/documenti-annuali (anno, uid opz.; admin=tutti, altri=solo se stessi, uid altrui=403), POST/DELETE /api/me/documenti-annuali, POST/DELETE /api/auth/users/{uid}/documenti-annuali (admin).
- Sicurezza: GET /api/corsi-ivass/{id}/storico ora blocca (403) i non-admin che richiedono lo storico di un altro utente.
- Bugfix Corsi IVASS: salvataggio corso con Crediti IVASS vuoto -> null (no piu' 422); campo crediti puo' restare vuoto; toast errori gestiscono detail array.
- Link "Corsi IVASS" dalla checklist naviga a /corsi-ivass?uid=<id> e preseleziona il collaboratore; CorsiIvass limita la selezione ai non-admin al proprio profilo.
- Testing: backend 14/14 pytest, frontend 100% flussi richiesti (iteration_134.json). Fix aggiuntivi verificati via curl.
