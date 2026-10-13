#!/usr/bin/env bash
# Copia i dati MongoDB da Emergent (produzione) a Railway.
# Richiede mongodump/mongorestore (MongoDB Database Tools).
#
# USO:
#   export SRC_MONGO_URL="mongodb+srv://...emergent-atlas..."   # Republish -> Database
#   export DST_MONGO_URL="mongodb://...railway-public..."        # Railway -> MongoDB -> Variables (public)
#   export SRC_DB="nome_db_emergent"                             # System keys -> DB_NAME
#   export DST_DB="gestionale_schianta"
#   bash scripts/migrate_data_emergent_to_railway.sh
#
# Opzionale:
#   export DROP_DEST=1   # svuota le collezioni di destinazione prima del restore (restore --drop)
#
set -euo pipefail

: "${SRC_MONGO_URL:?Imposta SRC_MONGO_URL (Mongo produzione Emergent)}"
: "${DST_MONGO_URL:?Imposta DST_MONGO_URL (Mongo Railway)}"
: "${SRC_DB:?Imposta SRC_DB (nome database sorgente)}"
: "${DST_DB:?Imposta DST_DB (nome database destinazione)}"

DUMP_DIR="$(mktemp -d)/dump"
echo "==> Dump da Emergent: db='$SRC_DB' -> $DUMP_DIR"
mongodump --uri="$SRC_MONGO_URL" --db="$SRC_DB" --out="$DUMP_DIR"

RESTORE_FLAGS=(--nsFrom="${SRC_DB}.*" --nsTo="${DST_DB}.*")
if [[ "${DROP_DEST:-0}" == "1" ]]; then
  echo "==> DROP_DEST=1: le collezioni di destinazione verranno svuotate prima del restore"
  RESTORE_FLAGS+=(--drop)
fi

echo "==> Restore su Railway: db='$DST_DB'"
mongorestore --uri="$DST_MONGO_URL" "${RESTORE_FLAGS[@]}" "$DUMP_DIR"

echo "==> Verifica conteggi collezioni principali su destinazione"
for COLL in titoli polizze movimenti anagrafiche compagnie collaboratori utenti allegati ritenute_compagnia pnc rappel; do
  CNT=$(mongosh "$DST_MONGO_URL/$DST_DB" --quiet --eval "db.getCollection('$COLL').countDocuments({})" 2>/dev/null || echo "n/d")
  printf "   %-22s %s\n" "$COLL" "$CNT"
done

echo "==> Fatto. Esegui login su Railway e verifica i dati."
echo "    Pulisci il dump temporaneo: rm -rf $(dirname "$DUMP_DIR")"
