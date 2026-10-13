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

## Note
- Gli ALLEGATI non sono in Mongo: restano su Object Storage Emergent. Copiando solo il
  DB i metadati arrivano su Railway ma i file restano serviti da Emergent finché non si
  migra a S3/MinIO. (Attività futura.)
- Token di conferma: `MIGRATE-TO-RAILWAY`.
