# Changelog — Axicura CRM

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
