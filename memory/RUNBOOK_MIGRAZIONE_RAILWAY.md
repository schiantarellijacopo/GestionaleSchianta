# Runbook — Copia DB produzione (Atlas Emergent) → MongoDB Railway

## Problema
Atlas Emergent accetta connessioni SOLO dalla rete interna Emergent (IP allowlist non
modificabile). Quindi `mongodump` dall'ambiente agente/preview o da un PC esterno è
IMPOSSIBILE. L'unico componente che può leggere Atlas è il backend di PRODUZIONE
(gira dentro Emergent): `https://whatsapp-crm-146.emergent.host`.

## Soluzione implementata
Endpoint una-tantum, guardato (super_admin + confirm token), in:
`/app/backend/routes/migrate_railway.py` → `POST /api/migrate/to-railway`

Gira sul backend di produzione: legge TUTTE le collezioni dalla sorgente
(MONGO_URL/DB_NAME del pod = Atlas in prod) e le scrive sul MongoDB Railway passato
nel body. Sulla sorgente fa SOLO letture. Supporta `drop` per collezione, `dry_run`,
e filtro `collections`.

Testato in preview (2026-10-13):
- dry-run: 134 collezioni, 115.605 doc letti dal DB, connessione Railway OK.
- write-test reale su db throwaway `migrate_selftest` (1 collezione) → verificato count su
  Railway → db throwaway eliminato. Path drop+bulk_write OK.

## Procedura per la copia reale
1. Save to GitHub (porta l'endpoint nel repo).
2. REPUBLISH l'app di PRODUZIONE Emergent (whatsapp-crm-146) — NON Railway — così
   l'endpoint è live DOVE Atlas è raggiungibile.
3. Login come super_admin sul dominio di produzione e chiamare:
   ```
   curl -s -X POST "https://whatsapp-crm-146.emergent.host/api/migrate/to-railway" \
     -H "Authorization: Bearer <TOKEN_SUPERADMIN_PROD>" \
     -H "Content-Type: application/json" \
     -d '{
       "dst_mongo_url":"mongodb://mongo:<PWD>@reseau.proxy.rlwy.net:20671",
       "dst_db":"assicura",
       "confirm":"MIGRATE-TO-RAILWAY",
       "drop":true,
       "dry_run":false
     }'
   ```
   - Prima passata consigliata con `"dry_run":true` per vedere i conteggi.
   - `drop:true` SOVRASCRIVE il seed attuale di `assicura` su Railway.
4. Verificare la risposta: `collections` (read/written) e `dest_db_after`.
5. Assicurarsi che il servizio GestionaleSchianta Railway abbia `DB_NAME=assicura`.
6. Deploy/accesso Railway → login `jacopo@schiantarelli.it` → smoke test
   (titoli, polizze, Prima Nota, ritenute/PNT/rappel).

## ESITO — Migrazione DB eseguita (2026-10-13)
- Republish produzione fatto dall'utente; endpoint live su whatsapp-crm-146.emergent.host.
- Login super_admin PROD: superadmin@assicura.it (is_super_admin=true).
- Copia eseguita collezione-per-collezione (per evitare timeout): tutte HTTP=200.
- Sorgente DB prod reale: `whatsapp-crm-146-test_database`.
- Letti = Scritti = 190.541 doc. Railway `assicura` verificato: users 64, agenzie 5,
  anagrafiche 16387, polizze 75756, titoli 64156, compagnie 30, movimenti 1558,
  allegati 426, sinistri 6623. 120 collezioni (10 vuote non ricreate).
- FILE: Opzione A (zero-copy). Railway deve avere EMERGENT_LLM_KEY + APP_NAME = prod.
- TODO sicurezza: rimuovere l'endpoint /api/migrate/to-railway (one-time) e ri-deploy.

## Note
- Gli ALLEGATI non sono in Mongo: restano su Object Storage Emergent. Copiando solo il
  DB i metadati arrivano su Railway ma i file restano serviti da Emergent finché non si
  migra a S3/MinIO. (Attività futura.)
- Token di conferma: `MIGRATE-TO-RAILWAY`.
