# Direttiva permanente — PRESTAZIONI / VELOCITÀ (richiesta dall'utente, 01/10/2026)

La velocità e la fluidità del software sono una **prerogativa sempre**. Vale per
tutte le sezioni, i campi di ricerca, i filtri e i caricamenti, e per OGNI futura
implementazione.

## Regole operative (da seguire SEMPRE)

1. **Indici MongoDB automatici**: tutti gli indici sono definiti in
   `backend/indexes.py` (dict `INDEXES`) e creati in modo idempotente allo startup
   via `ensure_indexes()` (chiamata in `server.py` `@app.on_event("startup")`).
   → Quando aggiungi un nuovo campo usato per **ricerca, filtro, sort o join**
     (equality/range), AGGIUNGI subito l'indice corrispondente in `indexes.py`
     (preferire indici composti con `agenzia_tenant_id` come primo campo, perché
     il DB è tenant-scoped). Non serve migrazione: si creano al riavvio.

2. **Query in parallelo**: quando un endpoint esegue più query indipendenti,
   usarle in parallelo con `asyncio.gather` (vedi `/api/search` in server.py)
   invece che in sequenza.

3. **Upload non bloccanti**:
   - Backend: le chiamate sincrone `obj_storage.put_object` (usano `requests`)
     vanno eseguite in `run_in_threadpool` dentro gli endpoint async per non
     bloccare l'event loop (già fatto in `upload_allegato`).
   - Frontend: dove il file è un ACCESSORIO di un'operazione principale
     (es. incasso/copertura), caricare in BACKGROUND con toast di esito, così
     l'operazione si conferma subito (vedi `DialogIncassoCopertura`).

4. **Ricerche server-side + debounce**: i campi di ricerca filtrano su Mongo
   (non caricano tutto client-side) con debounce ~250-300ms e `limit`.

5. **Proiezioni**: nelle find usare sempre la projection (`{"_id":0, campo:1,...}`)
   per ridurre il payload; evitare `to_list(None)` su collezioni enormi senza filtro.

## AGGIORNAMENTO 01/10/2026 — DIRETTIVA RAFFORZATA

L'utente richiede esplicitamente: **ottimizzare TUTTO il programma in automatico** (indici o altri mezzi),
senza chiedere ogni volta quali sezioni. Regola operativa per OGNI nuova funzione/endpoint/pagina:
- Aggiungere SEMPRE gli indici necessari in `backend/indexes.py` per i campi di ricerca/filtro/sort/join.
- Usare projection a INCLUSIONE nelle liste (mai documenti "grassi").
- Query indipendenti in parallelo (`asyncio.gather`).
- Liste grandi → paginazione lato server (pattern Anagrafiche/Polizze: `paged/page/page_size/sort/dir` → `{items,total,pages,totali}`).
- Non chiedere conferma per ottimizzare: farlo di default.

### Stato 01/10/2026
- Polizze: paginazione server attiva (50/pagina, totali via aggregation, pager UI). Verificato: pagina 1 di 101, 5048 attive, totali server corretti.
- Titoli: "carica tutto" su richiesta utente, alleggerito con projection + gzip.
- Statistiche/report (`/statistiche/*`, `/cervello/*`): già veloci (0,12–0,24s) con aggregazioni + indici.
- GZip attivo (risposte ~10x più leggere nel browser).


- `ensure_indexes()` garantisce ~143 indici (log: "Indici DB garantiti: N").
- Warning innocuo: `users.email` (indice unique già esistente con stesso nome).
