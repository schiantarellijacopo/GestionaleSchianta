#!/usr/bin/env python3
"""
Duplica (COPIA) i dati di UN SOLO tenant di produzione verso un altro MongoDB (es. Railway).
NON modifica la sorgente: sulla sorgente esegue solo letture (find).
Idempotente: usa upsert per _id, quindi puo' essere rieseguito.

COSA COPIA (per ogni collezione):
  - i documenti del tenant indicato (agenzia_tenant_id == TENANT_ID)
  - i documenti "condivisi/globali" senza tenant (agenzia_tenant_id assente o None)
    -> necessari al corretto funzionamento dell'app (config, template, ecc.)

USO:
  export SRC_MONGO_URL="mongodb+srv://...emergent..."   # Republish -> Database (produzione)
  export SRC_DB="<db_produzione>"                        # System keys -> DB_NAME
  export DST_MONGO_URL="mongodb://...railway-public..."  # Railway MongoDB -> MONGO_PUBLIC_URL
  export DST_DB="gestionale_schianta"                    # DB_NAME scelto per Railway
  export TENANT_ID="c5ae2d0e-283e-4513-aaf2-cbd97ef62d78"
  # opzionale:
  export INCLUDE_SHARED=1     # (default 1) copia anche i documenti senza tenant
  export DRY_RUN=1            # se =1 non scrive, stampa solo cosa farebbe
  python3 scripts/duplicate_tenant_to_railway.py
"""
import os
import sys

try:
    from pymongo import MongoClient, UpdateOne
except ImportError:
    sys.exit("Installa pymongo:  pip install pymongo")

SRC_URL = os.environ["SRC_MONGO_URL"]
DST_URL = os.environ["DST_MONGO_URL"]
SRC_DB = os.environ["SRC_DB"]
DST_DB = os.environ["DST_DB"]
TENANT_ID = os.environ["TENANT_ID"]
INCLUDE_SHARED = os.environ.get("INCLUDE_SHARED", "1") == "1"
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
BATCH = 1000

TENANT_FIELD = "agenzia_tenant_id"


def build_filter():
    conds = [{TENANT_FIELD: TENANT_ID}]
    if INCLUDE_SHARED:
        conds.append({TENANT_FIELD: {"$exists": False}})
        conds.append({TENANT_FIELD: None})
    return {"$or": conds}


def main():
    src = MongoClient(SRC_URL)[SRC_DB]
    dst = MongoClient(DST_URL)[DST_DB]
    flt = build_filter()

    print(f"Sorgente : {SRC_DB}")
    print(f"Dest.    : {DST_DB}  (Railway)")
    print(f"Tenant   : {TENANT_ID}  (condivisi inclusi: {INCLUDE_SHARED})")
    print(f"DRY_RUN  : {DRY_RUN}\n")

    collezioni = [c for c in src.list_collection_names() if not c.startswith("system.")]
    tot_letti = tot_scritti = 0

    for coll in sorted(collezioni):
        cur = src[coll].find(flt, no_cursor_timeout=True)
        ops, letti = [], 0
        for doc in cur:
            letti += 1
            ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True))
            if not DRY_RUN and len(ops) >= BATCH:
                dst[coll].bulk_write(ops, ordered=False)
                ops = []
        cur.close()
        scritti = letti
        if ops and not DRY_RUN:
            dst[coll].bulk_write(ops, ordered=False)
        if letti:
            print(f"  {coll:<32} letti={letti:<7} {'(dry-run)' if DRY_RUN else 'copiati'}")
        tot_letti += letti
        tot_scritti += scritti if not DRY_RUN else 0

    print(f"\nTOTALE documenti letti dal tenant: {tot_letti}")
    if DRY_RUN:
        print("DRY_RUN attivo: nessuna scrittura effettuata.")
    else:
        print(f"TOTALE documenti scritti su Railway: {tot_scritti}")
        print("Fatto. Verifica il login su Railway e i conteggi (titoli/polizze/movimenti).")


if __name__ == "__main__":
    main()
