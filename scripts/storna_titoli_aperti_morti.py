"""Storna i titoli APERTI che non verranno mai incassati:
  - su polizze morte (annullata / sostituita / scaduta), oppure
  - con scadenza precedente al 2025 (residui storici su qualsiasi polizza).

Non tocca i titoli aperti recenti su polizze attive.

Uso:  DRY=1 python3 storna_titoli_aperti_morti.py   (report)
      DRY=0 python3 storna_titoli_aperti_morti.py   (applica)
"""
import asyncio, os, sys
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient

TENANT = os.environ.get("TENANT_ID", "31b4950e-85c2-4232-a31f-ba226b7923fe")
DRY = os.environ.get("DRY", "1") == "1"
NOW = datetime.now(timezone.utc).isoformat()
APERTI = ["da_incassare", "insoluto", "sospeso"]
DEAD = {"annullata", "sostituita", "scaduta"}
SOGLIA = "2025-01-01"


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    pol_stato = {}
    async for p in db.polizze.find({"agenzia_tenant_id": TENANT}, {"_id": 0, "id": 1, "stato": 1}):
        pol_stato[p["id"]] = p.get("stato")

    ids_dead, ids_old, ex = [], [], []
    async for t in db.titoli.find(
        {"agenzia_tenant_id": TENANT, "stato": {"$in": APERTI}},
        {"_id": 0, "id": 1, "polizza_id": 1, "scadenza": 1},
    ):
        st = pol_stato.get(t.get("polizza_id"))
        old = (t.get("scadenza") or "") < SOGLIA
        if st in DEAD:
            ids_dead.append(t["id"])
        elif old:
            ids_old.append(t["id"])
        if (st in DEAD or old) and len(ex) < 8:
            ex.append((t.get("scadenza"), st))

    allids = ids_dead + ids_old
    print(f"tenant={TENANT[:12]} dry={DRY}", flush=True)
    print(f"aperti su polizze morte: {len(ids_dead)} | aperti pre-2025 su attive: {len(ids_old)} "
          f"| TOTALE da stornare: {len(allids)}", flush=True)
    print("esempi:", ex, flush=True)
    if not allids or DRY:
        return
    tot = 0
    for i in range(0, len(allids), 1000):
        chunk = allids[i:i + 1000]
        r = await db.titoli.update_many(
            {"id": {"$in": chunk}},
            {"$set": {"stato": "stornato",
                      "nota": "Stornato: titolo aperto su polizza chiusa / residuo storico",
                      "updated_at": NOW}})
        tot += r.modified_count
    print("titoli stornati:", tot, flush=True)


asyncio.run(main())
