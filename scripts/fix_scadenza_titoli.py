"""Corregge la scadenza dei titoli con scadenza < effetto.

Causa: il flusso OMNIA, per i rinnovi futuri, mette in `data_scadenza_emesso`
la data di emissione dell'avviso (precedente all'effetto). Regola corretta:
scadenza = effetto + periodo del frazionamento della polizza.

Uso:  DRY=1 python3 fix_scadenza_titoli.py   (solo report)
      DRY=0 python3 fix_scadenza_titoli.py   (applica)
"""
import asyncio, os, sys
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
from ania_importer import _scadenza_da_effetto

DRY = os.environ.get("DRY", "1") == "1"


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    # frazionamento per polizza
    fraz = {}
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "frazionamento": 1}):
        fraz[p["id"]] = p.get("frazionamento") or "annuale"

    ops, esempi, skip = [], [], 0
    cur = db.titoli.find(
        {"$expr": {"$lt": ["$scadenza", "$effetto"]}},
        {"_id": 0, "id": 1, "polizza_id": 1, "effetto": 1, "scadenza": 1},
    )
    async for t in cur:
        eff = t.get("effetto")
        nuova = _scadenza_da_effetto(eff, fraz.get(t.get("polizza_id"), "annuale")) or eff
        if not nuova or nuova == t.get("scadenza"):
            skip += 1
            continue
        ops.append(UpdateOne({"id": t["id"]}, {"$set": {
            "scadenza": nuova,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}))
        if len(esempi) < 12:
            esempi.append((t.get("effetto"), t.get("scadenza"), "->", nuova))

    print("titoli da correggere:", len(ops), "| skip:", skip, "| dry:", DRY, flush=True)
    for e in esempi:
        print("  ", e, flush=True)
    if ops and not DRY:
        tot = 0
        for i in range(0, len(ops), 1000):
            r = await db.titoli.bulk_write(ops[i:i + 1000], ordered=False)
            tot += r.modified_count
        print("titoli aggiornati:", tot, flush=True)


asyncio.run(main())
