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

## Stato indici
- `ensure_indexes()` garantisce ~143 indici (log: "Indici DB garantiti: N").
- Warning innocuo: `users.email` (indice unique già esistente con stesso nome).
