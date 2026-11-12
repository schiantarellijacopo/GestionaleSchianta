"""One-shot back-fill: re-categorizza gli allegati smistati da Drive/inbox che
erano finiti in 'altro'/'altri' perché il tipo_documento dello scanner
(es. libretto_circolazione) non era mappato in DOC_ROUTING.
Deriva la categoria corretta dal tipo salvato in descrizione: 'Documenti inbox (<tipo>)'.
"""
import asyncio
import os
import re
from motor.motor_asyncio import AsyncIOMotorClient

from routes.documenti_inbox import DOC_ROUTING

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

RX = re.compile(r"Documenti inbox \(([^)]+)\)")


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    cur = db.allegati.find({
        "categoria": {"$in": ["altro", "altri", None]},
        "descrizione": {"$regex": "^Documenti inbox \\("},
    }, {"_id": 0, "id": 1, "descrizione": 1, "categoria": 1, "entita_tipo": 1})
    fixed = 0
    async for a in cur:
        m = RX.search(a.get("descrizione") or "")
        if not m:
            continue
        tipo = m.group(1).strip().lower()
        route = DOC_ROUTING.get(tipo)
        if not route:
            continue
        _, new_cat = route
        if not new_cat or new_cat in ("altro", "altri"):
            continue
        await db.allegati.update_one({"id": a["id"]}, {"$set": {"categoria": new_cat}})
        fixed += 1
        print(f"  {a['id']}  {a.get('categoria')} -> {new_cat}  ({tipo})")
    print(f"Back-fill completato: {fixed} allegati ricategorizzati.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
