"""Post-import: titoli incassati senza metodo → "Pagamento in direzione"."""
import asyncio, os, sys
sys.path.insert(0, "/app/backend")
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    q = {"stato": "incassato", "$or": [{"mezzo_pagamento": None}, {"mezzo_pagamento": ""}]}
    print("da aggiornare:", await db.titoli.count_documents(q), flush=True)
    r = await db.titoli.update_many(q, {"$set": {
        "mezzo_pagamento": "Pagamento in direzione",
        "pagamento_in_direzione": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    print("aggiornati:", r.modified_count, "| residui:", await db.titoli.count_documents(q))

asyncio.run(main())
