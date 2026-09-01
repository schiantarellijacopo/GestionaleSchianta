# Piano — Ottimizzazione massima, isolamento agenzie, nessun limite di ricerca

Obiettivo dichiarato: programma leggero e fluido anche con più agenzie collegate contemporaneamente, ogni agenzia vede SOLO i propri dati, e le ricerche coprono TUTTO l'archivio senza limiti di righe.

## 1. Velocità e leggerezza (subito)

1. **Indici MongoDB su tutte le collezioni calde** (clienti, polizze, titoli, sinistri, movimenti, allegati, diario, utenti, chat/notebook) — ricerche e ordinamenti 10-50x più veloci su archivi grandi; creati automaticamente all'avvio.
2. **Nessun limite di ricerca — garanzia assoluta**: la ricerca viene eseguita dal SERVER su TUTTO l'archivio, sempre. Se cerchi "Rossi" e ci sono 300 Rossi su 50.000 clienti, li trova TUTTI e 300 — nessuno viene mai escluso. Il blocco da 50 riguarda solo quante righe il browser disegna alla volta (scorrendo o cliccando "carica altri" compaiono le successive, già trovate): è un accorgimento di visualizzazione, non un taglio dei risultati. In più il contatore mostra sempre il totale reale ("300 risultati trovati"), così vedi subito che ci sono e nessun nome può sfuggire. Oggi invece il taglio avviene PRIMA della ricerca (scarica solo i primi 200-2000 record e cerca lì dentro): è questo che verrà eliminato.
3. **Paginazione server delle schermate pesanti** (Documenti Mancanti, Prima Nota, Carichi Mensili, e liste principali): il browser non scarica mai migliaia di righe in un colpo.
4. **App più leggera al primo avvio**: il programma si divide per pagina (oggi si scarica tutto in un blocco unico) — login e prima schermata immediati, il resto si carica solo quando serve.
5. **Fluidità in uso simultaneo**: query database non bloccanti e in parallelo, niente ricalcoli riga-per-riga nelle liste (eliminazione query N+1), dati già noti mostrati subito con aggiornamento in sottofondo.
6. **Misurazione prima/dopo** sulle pagine più usate, con report dei tempi.

## 2. Isolamento totale tra agenzie (subito, insieme al punto 1)

1. **Controllo centralizzato per tenant**: ogni lettura/scrittura viene filtrata automaticamente per agenzia a livello di infrastruttura, non endpoint per endpoint — anche un bug futuro in una singola schermata non può far vedere dati di un'altra agenzia.
2. **Indici composti con tenant**: gli indici includono l'agenzia come primo campo, così le query di un'agenzia non rallentano mai per colpa dei dati delle altre.
3. **Verifica di tenuta**: test automatico che prova ad accedere ai dati di un'altra agenzia da ogni endpoint principale e deve ricevere sempre "vietato/vuoto".

## 3. Protezione login (subito) — SENZA blocchi

Niente blocco a tempo: nessun utente resta mai chiuso fuori. La protezione contro i bot funziona così:
- **Rallentamento progressivo**: dopo 5 tentativi falliti (per IP+email) ogni nuovo tentativo attende qualche secondo in più (2s, poi 4s, 8s... fino a max 30s). Un bot che prova migliaia di password diventa inutilizzabile; una persona vera che al sesto tentativo ricorda la password giusta aspetta solo pochi secondi ed entra normalmente.
- Contatore azzerato al login riuscito.

## 4. Onboarding nuova agenzia: credenziali proprie + sottodominio proprio

Quando una nuova agenzia compra il software, dal pannello super admin la crei e il sistema genera automaticamente:
1. **Credenziali di accesso dedicate** — utente amministratore dell'agenzia (email + password provvisoria da cambiare al primo accesso), separato da tutte le altre agenzie.
2. **Sottodominio dedicato** — scegli il nome breve (es. "bottoni") e l'agenzia accede da `bottoni.tuodominio.it`: pagina di login con il SUO logo e nome, e una volta dentro vede esclusivamente i propri dati.
3. **Riepilogo consegna** — schermata/email con indirizzo e credenziali pronte da inviare al cliente.
- Requisito una tantum: un tuo dominio con record DNS wildcard (`*.tuodominio.it`) puntato all'app pubblicata (guida passo-passo fornita). Dal dominio principale continui ad accedere tu come super admin.

## 5. Scambio dati tra agenzie SOLO con approvazione del super admin

Regola di base: isolamento totale (nessuna agenzia vede nulla delle altre). Unica eccezione: lo scambio autorizzato.
1. **Richiesta di scambio** — un'agenzia può chiedere di condividere dati specifici (es. un cliente con le sue polizze) con un'altra agenzia; la richiesta indica cosa, verso chi e perché.
2. **Approvazione nella console super admin** — le richieste arrivano in una sezione dedicata della console del proprietario del software: solo il super admin può approvare o rifiutare. Nessuno scambio avviene senza il suo sì.
3. **Trasferimento tracciato** — all'approvazione i dati indicati diventano visibili/copiati all'agenzia destinataria; ogni scambio resta registrato (chi ha chiesto, chi ha approvato, cosa è passato, quando).
4. **Revoca** — il super admin può revocare una condivisione concessa.

## Dopo questo blocco (già pianificato, in ordine)
Test funzioni recenti (Notebook AI, Modelli Piramide, colonne, doppioni) → Copilot veloce → Priorità 2 sicurezza (2FA, cifratura AES-256, audit log) → Priorità 3 pre-rilascio (Atlas, Cloudflare, Sentry, pentest).

## Assunzioni
- La ricerca non perde MAI un risultato: interroga tutto l'archivio lato server e mostra il totale reale dei trovati; il blocco da 50 è solo il ritmo con cui il browser disegna le righe già trovate.
- Protezione login senza alcun blocco a tempo: solo rallentamento progressivo anti-bot (mai lock-out per gli utenti).
- L'isolamento agenzie viene applicato a tutte le collezioni con dati di portafoglio; le tabelle di sistema (modelli piramide, librerie condivise) restano globali salvo tua diversa indicazione.
