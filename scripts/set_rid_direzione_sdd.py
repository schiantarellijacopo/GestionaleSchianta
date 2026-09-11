"""Imposta mezzo_pagamento='RID DIREZIONE' sui titoli SDD (SEC/RD) importati da OMNIA
(note_carico='OMNIA SDD - pagamento in direzione') e imposta il pagamento preferito
'RID DIREZIONE' sulle polizze che li possiedono.
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
NOTE = "OMNIA SDD - pagamento in direzione"
LABEL = "RID DIREZIONE"


def _now():
    return datetime.now(timezone.utc).isoformat()


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    pids = await db.titoli.distinct("polizza_id", {"note_carico": NOTE})
    pids = [p for p in pids if p]
    print(f"Polizze con titoli SDD: {len(pids)}")

    rt = await db.titoli.update_many(
        {"note_carico": NOTE},
        {"$set": {"mezzo_pagamento": LABEL, "updated_at": _now()}},
    )
    print(f"Titoli SDD aggiornati -> '{LABEL}': {rt.modified_count}")

    rp = await db.polizze.update_many(
        {"id": {"$in": pids}},
        {"$set": {"mezzo_pagamento_preferito": LABEL, "updated_at": _now()}},
    )
    print(f"Polizze con pagamento preferito -> '{LABEL}': {rp.modified_count}")


if __name__ == "__main__":
    asyncio.run(main())
