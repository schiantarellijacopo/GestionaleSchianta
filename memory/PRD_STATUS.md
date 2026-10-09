# Axicura CRM — Stato lavori (aggiornato 2026-10-09)

## MAPPA GARANZIE dal rec42 (2026-10-09) — DEPLOY LANCIATO
Richiesta utente: garanzie e titolo devono aggiornarsi "di pari passo". Prima la mappa Garanzie veniva dal rec30 (per-polizza, premio vecchio) mentre il titolo dal rec42 (per-titolo, rinnovo) → divergevano (es. 183629455: garanzie 690 vs titolo 714,50).
Fix in ania_importer.py `_processa_garanzie` (riscritta) + nuovo helper `_row_rec42_a_garanzia`:
- `polizza.garanzie` ora costruita dal rec42, prendendo le righe del TITOLO PIÙ RECENTE della polizza (max effetto_titolo idx12). Per garanzia: netto=Y(24), imposte=AA(26)-AC(28), ssn=AC(28), lordo=AB(27), provv=AF(31); garanzia 'CIA' → netto=0, imposte=(AA-AC)+Y (come nel titolo).
- Aggiorna anche premio_netto/premio_imposte/premio_ssn/premio_tasse/premio_lordo/provvigioni della polizza col totale del titolo corrente (così la riga TOTALE Lordo, che legge pol.premio_lordo, mostra il valore giusto).
- rec30 resta per massimali/capitali (merge per codice garanzia), diritti, e come FALLBACK per polizze senza rec42 in quel flusso.
- Cache numero_polizza->pol_id (il rec42 non ha id_polizza_exp) per performance.
VERIFICA E2E (vero importer, tenant temp, ZIP reali):
- 183629455 (rinnovo): garanzie TOT = titolo = premio = netto 581,67 / imposte 72,80 / ssn 60,03 / lordo 714,50 / provv 46,14 ✓
- 184643537 (con CIA): garanzie TOT = titolo = premio = 276,14 / 34,86 / 19,00 / 330,00 / 34,86 ✓ (riga CIA: netto 0, imposte -0,38)

## REGOLA IMPORT OMNIA — importi SOLO dal rec42 (2026-10-09) — DEPLOY LANCIATO
Richiesta utente (definitiva, SOSTITUISCE le regole precedenti rec20/rec40): gli importi dei titoli (Netto, Tasse/Imposte, SSN, Lordo, Provvigioni) si prendono ESCLUSIVAMENTE dal rec42, sommando le righe-garanzia del titolo (collegate per id_titolo_exp, col C/idx 2). Nessun altro rec per questi 5 parametri.
Formula (ania_importer.py `_processa_titoli`, blocco `rec42_by_titolo`):
- PROVVIGIONI = Σ AF (idx 31, provvigioni_totali)
- SSN         = Σ AC (idx 28, ssn)
- LORDO       = Σ AB (idx 27, lordo)
- NETTO       = Σ Y (idx 24, imponibile) − Σ(Y della garanzia 'CIA')
- TASSE/IMP   = Σ AA (idx 26, tasse) − Σ AC (idx 28, ssn) + Σ(Y 'CIA')
- La garanzia 'CIA' (col P/idx 15 = cod_garanzia_cmp = "Contributo Imposte Ramo"): il suo imponibile va spostato dal Netto alle Imposte.
TITOLI SENZA rec42: tutti gli importi a 0 (scelta utente). Verranno popolati da un re-import successivo quando il rec42 avrà i dati (il re-import aggiorna gli importi SOLO sui titoli `stato=="da_incassare"`, quindi non tocca incassi/pagamenti/prime note chiuse).
Rimosso: `premi_rec20` e il fallback rec40 per i 5 parametri. `accessori` resta dal rec40 (idx 46), non è tra i 5.
VERIFICA E2E (vero codice importer, tenant temporaneo isolato poi ripulito, ZIP 112):
- 184643537 (PS, con rec42) → netto 276,14 / imposte 34,86 / ssn 19,00 / lordo 330,00 / provv 34,86 ✓ (== rec20 di riferimento)
- 180024200 (QZ, senza rec42) → tutti 0 ✓
- 141 titoli importati, 39 senza rec42 nati a 0.

## Axicura CRM — Stato lavori (precedente: 2026-10-08)

## Colonna "Provvigione" = quota collaboratore (2026-10-08) — DA DEPLOYARE
- Richiesta: nell'Estratto conto collaboratori la colonna "Provvigione" (e tutti i totali/pagamenti) deve mostrare la quota SPETTANTE AL COLLABORATORE, non la provvigione totale di agenzia.
- Fix backend `estratto_provvigioni`: ogni riga calcola la quota collaboratore con `_provv_breakdown` (stesso motore schema provvigionale usato negli altri elenchi), usando compagnia_id/ramo/premio netto-lordo del titolo. `provvigione` = quota collab; aggiunti `provvigione_totale` e `provvigione_pct_collab` per riferimento. Totali (lorde/da pagare/netto) ora sul collab.
- Fix backend `paga_provvigioni` (riga ~1197): `lordo` = somma delle quote collaboratore (non più `sum(t.provvigioni)` totale agenzia). Verificato: pagamento registra 59,30 (=70% di 84,71), non 84,71.
- Il PDF stampa provvigioni eredita automaticamente (usa estratto). Frontend invariato (legge `r.provvigione`).
- Nota: collaboratori senza schema provvigionale applicabile → quota 0 (coerente col motore usato ovunque).
- RICHIEDE REDEPLOY + hard refresh.

## Regole import OMNIA + correzioni massive (2026-10-09) — DA DEPLOYARE
NUOVE REGOLE IMPORT (ania_importer.py), tutte verificate sul file reale:
- Titoli: premio dalla POLIZZA rec20 → netto=CP(93, imponibile_totale), ssn=CR(95), imposte=CS(96)-CR, lordo=CT(97); provvigioni agenzia da rec40 BD(55). Fallback a rec40 se la polizza non è nel rec20.
- Garanzie (rec30): imposte scorporate dall'SSN → imposte = imposte_flusso - ssn (es. 41,61-19=22,61). Marker polizza `garanzie_imposte_scorporate=True`.
- Re-import: un titolo GIÀ esistente viene aggiornato negli IMPORTI solo se stato=="da_incassare" (altrimenti saltato) → protegge incassi/versamenti/pagamenti/prime note chiuse/estratti pagati. Counter counts["titoli_aggiornati"].
VERIFICA (184643537): netto 276,14 / imposte 34,86 / ssn 19 / lordo 330 / provv 34,86. (732958169): 778,16/172,34/0/950,50/178,97. Garanzie RC AUTOVETTURE imposte 22,61. ✓

ENDPOINT CORREZIONE MASSIVA GARANZIE: POST /api/import/fix-garanzie-imposte?dry_run=true|false (admin). Scorpora SSN dalle garanzie di TUTTE le polizze del tenant, una sola volta (guard marker). Dry-run testato su preview: ~15.979 polizze / 16.696 garanzie.

PIANO PRODUZIONE (confermato dall'utente):
1. DEPLOY di queste modifiche.
2. GARANZIE: eseguo dry-run su produzione → mostro numeri → applico (dry_run=false).
3. TITOLI: l'utente ricarica gli ZIP OMNIA precedenti uno alla volta; il re-import corregge gli importi dei soli titoli "da_incassare".
Nota: produzione (whatsapp-crm-146.emergent.host) ha DB separato dal preview; accesso API possibile con token admin (stesso JWT_SECRET).

## Estratto conto collaboratori + Brogliaccio (2026-10-08) — DA DEPLOYARE
Tre richieste utente, tutte implementate e testate (testing agent 100%):
1. **Brogliaccio pagamento provvigioni**: la riga "Pagamento provvigioni a ..." ora valorizza SOLO colonne SPESE e BANCA (uscita); colonna RITENUTA VUOTA. Fix in `_compute_brogliaccio` ramo `cat=="provvigioni"` uscita: `c_ritenuta=0.0`, `c_spese=importo` (server.py ~8282). La banca si valorizza via per_conto (conto risolto da tipo pagamento).
2. **Paga lista salvata**: nella card "Liste salvate da pagare" ogni bozza ha ora un pulsante verde **Paga** (oltre a Carica/elimina). Apre il PagaDialog precompilato coi titoli/voci della lista; a pagamento riuscito la bozza viene **eliminata** automaticamente (Provvigioni.jsx `pagaLista`/`payBozza`/PagaDialog `bozzaId`).
3. **Nascondi righe in bozza**: salvando una lista, i titoli/voci che ne fanno parte spariscono dalle tabelle "Provvigioni maturate" e "Voci manuali" (flag `in_bozza`/`bozza_id` aggiunti da `estratto_provvigioni` in server.py; frontend filtra `!r.in_bozza`/`!v.in_bozza`). Eliminando la lista ricompaiono.
- Extra: lo Storico pagamenti ora si aggiorna subito dopo "Paga lista" (prop `refreshKey`).
- HARDENING post code-review: (a) `paga_provvigioni` ora rifiuta titoli/voci già pagati (HTTPException 400) → niente doppi pagamenti; (b) il "Paga lista" passa SOLO i titoli/voci validi e non pagati (anteprima == importo addebitato anche con filtro date attivo); (c) `provvigioni_bozze` aggiunta a TENANT_SCOPED_COLLECTIONS (isolamento multi-tenant); (d) bottone "Registra pagamento" con guardia anti doppio-click. Tutto verificato via API.
- Credenziali test preview: qa.tester@schiantarelli.it / QaTest123! (tenant c5ae2d0e, dati reali collaboratori).
- RICHIEDE REDEPLOY su whatsapp-crm-146 + hard refresh.

## FIX chiusure Prima Nota (2026-10-08) — DEPLOY IN CORSO
- Sintomo utente: giornata con tasto verde "Chiudi giornata" (sembra aperta) ma alla chiusura dice "Giornata già chiusa"; manca il tasto "Riapri".
- Root cause: `_compute_brogliaccio` (server.py ~riga 8587) faceva `db.chiusure_giorno.find_one({"data": data})` SENZA filtro `riaperta_at`. Con record DUPLICATI per lo stesso giorno (una riaperta + una richiusa, es. 2026-09-30 su prod) la find_one poteva restituire quella RIAPERTA → `chiusa=False` → pulsante verde, ma `chiudi_giorno` trovava la chiusura ATTIVA → errore "già chiusa".
- FIX: ora cerca prima la chiusura ATTIVA `{"data": data, "riaperta_at": None}`, fallback alla riaperta solo per display. Verificato su preview: brogliaccio ritorna `chiusa=True` → compaiono "Invia commercialista" + "Riapri".
- NB: `shared.giornata_chiusa`, `/giornate-chiuse`, `/giornata-stato` erano già corretti (filtravano riaperta_at=None).
- RICHIEDE REDEPLOY su whatsapp-crm-146 (l'utente testa in produzione) + hard refresh.
- Data fix preview: richiuse 11/09, 15/09, 24/09 del tenant c5ae2d0e (prod ha DB separato: lì la correzione è automatica col fix del codice, nessun intervento dati necessario grazie alla query corretta).

## Completati e in produzione
- Import Omnia: controllo duplicati anagrafiche anche su Partita IVA.
- Geocoding Nominatim vincolato all'Italia + fallback a cascata.
- FIX creazione anagrafica: 500 da `sesso=""` → enum vuoti coerciti a None (routes/anagrafiche.py `_normalize_upper`).
- Feature pagamento PARZIALE estratto conto compagnie: `importo_versato` + partita residua (collezione `residui_compagnia`), ricorsivo.
- FIX regression: bottone "Conferma versamento" bloccato quando il totale è <= 0 (es. versamento rappel/credito negativo). Ora la logica parziale si applica solo a totali positivi (EstrattoContoCompagnie.jsx PagamentoDialog). [redeploy 2026-10-08]

## Caso rappel 32,07 CATTOLICA (tenant jacopo@schiantarelli.it)
- Diagnosi: il +32,07 su BPER SONDRIO e SALDO CASSA CMP derivava dalla rimessa del 01/10 dove il rappel era scalato dal versamento (Scenario B). Scenario A corretto = rappel credito, banca paga pieno (212.513,53 / 40.949,81).
- Verificato empiricamente: riaprire+richiudere tutte le 14 giornate chiuse NON cambia i saldi (brogliaccio ricalcola live). Il problema NON erano gli snapshot congelati.
- RISOLTO DALL'UTENTE: ha corretto lui la rimessa. Nessun intervento richiesto.

## TODO futuri (approvati ma non ancora fatti)
- Logica rappel: idealmente il rappel non dovrebbe mai essere scalato dal versamento (deve restare credito). Valutare fix in paga-titoli se il caso si ripresenta.
- "Incassa rappel" non dovrebbe creare un secondo movimento in Prima Nota (decisione utente precedente) — da implementare se riemerge il doppio conteggio.

## Verifiche ancora utili
- Smoke test UI del dialog pagamento parziale (finora verificato backend via curl + logica frontend).
