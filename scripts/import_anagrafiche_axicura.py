"""Import anagrafiche CSV nel tenant dell'agenzia 'Importazione Axicura'
(admin jacopo@schiantarelli.it). Policy: fill-missing (aggiorna solo campi vuoti).
P.IVA normalizzata a 11 cifre. Delimiter ';', encoding latin-1.

Uso:  DRY=1 CSV=/tmp/contraenti.csv python3 import_anagrafiche_axicura.py
      DRY=0 CSV=/tmp/contraenti.csv python3 import_anagrafiche_axicura.py
"""
import asyncio, os, sys, csv
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")

from database import db, set_current_user
from routes.import_anagrafiche import _row_to_anagrafica, _sanitize_value
from routes.import_massivo import _detect_mapping_heuristic, _enrich_anagrafica, _fill_missing

EMAIL = os.environ.get("ADMIN_EMAIL", "jacopo@schiantarelli.it")
CSVPATH = os.environ.get("CSV", "/tmp/contraenti.csv")
DRY = os.environ.get("DRY", "1") == "1"
NOW = datetime.now(timezone.utc).isoformat()


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await raw.users.find_one({"email": EMAIL}, {"_id": 0})
    if not user:
        print("Utente non trovato:", EMAIL); return
    tid = user.get("agenzia_tenant_id")
    print(f"utente={EMAIL} tenant={tid} dry={DRY}", flush=True)
    set_current_user(user)  # rende db tenant-scoped + insert auto-assegna il tenant

    from db_models import Anagrafica

    # Indici anagrafiche esistenti NEL TENANT (per dedup + fill-missing)
    by_cf, by_piva = {}, {}
    async for a in db.anagrafiche.find({}, {"_id": 0}):
        if a.get("codice_fiscale"):
            by_cf[a["codice_fiscale"]] = a
        if a.get("partita_iva"):
            by_piva[a["partita_iva"]] = a
    print("anagrafiche esistenti nel tenant:", len(by_cf), "CF +", len(by_piva), "PIVA", flush=True)

    with open(CSVPATH, encoding="latin-1") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    headers = list(rows[0].keys()) if rows else []
    mapping = _detect_mapping_heuristic("anagrafica", headers)
    print("colonne mappate:", {h: v for h, v in mapping.items() if v}, flush=True)

    created = updated = skipped = errors = 0
    buffer = []
    ex_err = []

    async def flush():
        if buffer and not DRY:
            await db.anagrafiche.insert_many(buffer, ordered=False)
        buffer.clear()

    for i, row in enumerate(rows):
        try:
            rd = {h: _sanitize_value(row.get(h)) for h in headers}
            ana = _row_to_anagrafica(rd, mapping)
            if not (ana.get("ragione_sociale") or ana.get("codice_fiscale") or ana.get("partita_iva")):
                skipped += 1; continue
            _enrich_anagrafica(ana)
            cf, piva = ana.get("codice_fiscale"), ana.get("partita_iva")
            existing = (by_cf.get(cf) if cf else None) or (by_piva.get(piva) if piva else None)
            if existing:
                upd = _fill_missing(existing, {k: v for k, v in ana.items() if k in Anagrafica.model_fields})
                if upd:
                    upd["updated_at"] = NOW
                    if not DRY:
                        await db.anagrafiche.update_one({"id": existing["id"]}, {"$set": upd})
                    existing.update(upd)
                    updated += 1
                else:
                    skipped += 1
                continue
            ana["collaboratore_id"] = user.get("id")
            obj = Anagrafica(**{k: v for k, v in ana.items() if k in Anagrafica.model_fields})
            doc = obj.model_dump()
            # aggiorna indici per dedup intra-file
            if cf: by_cf[cf] = doc
            if piva: by_piva[piva] = doc
            buffer.append(doc)
            created += 1
            if len(buffer) >= 500:
                await flush()
        except Exception as e:
            errors += 1
            if len(ex_err) < 10:
                ex_err.append((i + 2, str(e)[:160]))
    await flush()

    print(f"RISULTATO: creati={created} aggiornati={updated} saltati={skipped} errori={errors}", flush=True)
    for e in ex_err:
        print("  err:", e, flush=True)


asyncio.run(main())
