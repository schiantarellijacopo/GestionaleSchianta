"""One-off: unifica tipi_pagamento/banche legacy sotto conti_cassa.

- CONTANTI BPER, BONIFICO, PayPal/Online -> BPER Sondrio (movimenti+titoli), poi eliminati
- Dedup: CONTANTI -> Cassa Contanti, PAGAMENTI IN DIREZIONE -> Pagamento Direzione
"""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

BPER = "7742f9b4-df83-4313-9ea0-aafd17d8203b"          # BPER Sondrio
CASSA = "9b4505e8-2e5d-42e5-b257-3f470e341666"         # Cassa Contanti
DIREZIONE = "2ea84f05-e593-45d3-b166-7c2382044e90"     # Pagamento Direzione

MERGE_TO_BPER = {
    "cc1b0283-0498-44df-b8dd-d1b41724dc39": "CONTANTI BPER",
    "70144237-f798-419a-b9e8-86ba3470cf77": "BONIFICO",
    "ce1e817d-2859-4227-b5ac-f781179b2b2c": "PayPal / Online",
}
DEDUP = {
    "1659934f-7247-4adc-82c1-3ca83acfce5c": ("CONTANTI", CASSA),
    "8e24758d-185e-4558-948b-1300db562e9a": ("PAGAMENTI IN DIREZIONE", DIREZIONE),
}


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    saldo_extra = 0.0
    for cid, nome in MERGE_TO_BPER.items():
        r1 = await db.movimenti.update_many({"conto_cassa_id": cid}, {"$set": {"conto_cassa_id": BPER}})
        r2 = await db.titoli.update_many({"conto_cassa_id": cid}, {"$set": {"conto_cassa_id": BPER}})
        r3 = await db.movimenti.update_many({"mezzo_pagamento": nome}, {"$set": {"mezzo_pagamento": "BPER Sondrio"}})
        r4 = await db.titoli.update_many({"mezzo_pagamento": nome}, {"$set": {"mezzo_pagamento": "BPER Sondrio"}})
        doc = await db.conti_cassa.find_one({"id": cid}, {"_id": 0, "saldo_iniziale": 1})
        saldo_extra += float((doc or {}).get("saldo_iniziale") or 0)
        await db.conti_cassa.delete_one({"id": cid})
        print(f"{nome}: mov={r1.modified_count} titoli={r2.modified_count} mezzo_mov={r3.modified_count} mezzo_tit={r4.modified_count} -> BPER Sondrio, conto eliminato")

    if saldo_extra:
        await db.conti_cassa.update_one({"id": BPER}, {"$inc": {"saldo_iniziale": saldo_extra}})
        print(f"saldo_iniziale +{saldo_extra} su BPER Sondrio")

    for cid, (nome, target) in DEDUP.items():
        r1 = await db.movimenti.update_many({"conto_cassa_id": cid}, {"$set": {"conto_cassa_id": target}})
        r2 = await db.titoli.update_many({"conto_cassa_id": cid}, {"$set": {"conto_cassa_id": target}})
        await db.tipi_pagamento.update_many({"conto_id": cid}, {"$set": {"conto_id": target}})
        await db.conti_cassa.delete_one({"id": cid})
        print(f"DEDUP {nome}: mov={r1.modified_count} titoli={r2.modified_count} -> {target}, conto eliminato")

    # remap eventuali tipi_pagamento verso conti fusi in BPER
    for cid in MERGE_TO_BPER:
        await db.tipi_pagamento.update_many({"conto_id": cid}, {"$set": {"conto_id": BPER}})

    print("--- conti_cassa finali ---")
    async for cc in db.conti_cassa.find({}, {"_id": 0, "nome": 1, "tipo": 1, "attivo": 1, "ordine": 1, "saldo_iniziale": 1}).sort("ordine", 1):
        n = await db.movimenti.count_documents({"conto_cassa_id": (await db.conti_cassa.find_one({"nome": cc["nome"]}, {"_id": 0, "id": 1}))["id"]})
        print(cc, "mov:", n)

asyncio.run(main())
