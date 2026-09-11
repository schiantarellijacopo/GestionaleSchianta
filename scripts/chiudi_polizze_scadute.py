"""Chiude (annulla) le polizze attive/sospese senza copertura da oltre 1 anno.

Data annullamento = ultima scadenza di copertura conosciuta (titoli o polizza).
"""
import asyncio, os, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

TENANT = os.environ.get("TENANT_ID", "31b4950e-85c2-4232-a31f-ba226b7923fe")
DRY = os.environ.get("DRY", "0") == "1"


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    limite = (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()
    print("soglia:", limite, "| dry-run:", DRY, flush=True)

    ultima = {}
    async for t in db.titoli.find({"agenzia_tenant_id": TENANT},
                                  {"_id": 0, "polizza_id": 1, "scadenza": 1}):
        pid, sc = t.get("polizza_id"), t.get("scadenza")
        if pid and sc and sc > ultima.get(pid, ""):
            ultima[pid] = sc

    ops, esempi = [], []
    async for p in db.polizze.find({"agenzia_tenant_id": TENANT,
                                    "stato": {"$in": ["attiva", "sospesa"]}},
                                   {"_id": 0, "id": 1, "numero_polizza": 1, "scadenza": 1}):
        fine = ultima.get(p["id"]) or p.get("scadenza") or ""
        if not fine or fine >= limite:
            continue
        ops.append(UpdateOne({"id": p["id"]}, {"$set": {
            "stato": "annullata",
            "data_annullamento": fine,
            "motivo_annullamento": f"Nessuna copertura/pagamento dal {fine}",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}))
        if len(esempi) < 10:
            esempi.append((p.get("numero_polizza"), fine))

    print("polizze da chiudere:", len(ops), flush=True)
    print("esempi:", esempi, flush=True)
    if ops and not DRY:
        r = await db.polizze.bulk_write(ops, ordered=False)
        print("annullate:", r.modified_count, flush=True)

asyncio.run(main())
