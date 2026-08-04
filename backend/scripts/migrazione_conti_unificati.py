"""Migrazione one-off: unificazione metodi di pagamento sotto `conti_cassa`.

Approvata dall'utente:
- CONTANTI BPER / BONIFICO / PayPal Online -> BPER Sondrio
- CONTANTI (duplicato)                    -> Cassa Contanti
- PAGAMENTI IN DIREZIONE (duplicato)      -> Pagamento Direzione
- Normalizza `mezzo_pagamento` di movimenti/titoli al nome del conto.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient

MERGE = [
    ("CONTANTI BPER", "BPER Sondrio"),
    ("BONIFICO", "BPER Sondrio"),
    ("PayPal / Online", "BPER Sondrio"),
    ("CONTANTI", "Cassa Contanti"),
    ("PAGAMENTI IN DIREZIONE", "Pagamento Direzione"),
]

MAPPA_MEZZI = {
    "CONTANTI BPER": "BPER Sondrio",
    "CONTANTI BPER SONDRIO": "BPER Sondrio",
    "BONIFICO": "BPER Sondrio",
    "bonifico": "BPER Sondrio",
    "BONIFICO BPER SONDRIO": "BPER Sondrio",
    "ASSEGNO BPER SONDRIO": "BPER Sondrio",
    "RID BPER SONDRIO": "BPER Sondrio",
    "POS BPER SONDRIO": "BPER Sondrio",
    "BANCOMAT": "BPER Sondrio",
    "BONIFICO BPER VILLA": "BPER VILLA",
    "ASSEGNO BPER VILLA": "BPER VILLA",
    "BONIFICO INTESA": "Intesa Sanpaolo",
    "CONTANTI CREDIT AGRICOLE": "Credit Agricole",
    "ASSEGNO CREDIT AGRICOLE": "Credit Agricole",
    "BONIFICO CREDIT AGRICOLE": "Credit Agricole",
    "contanti": "Cassa Contanti",
    "CONTANTI": "Cassa Contanti",
    "assegno": "Assegni",
    "ASSEGNO BANCARIO": "Assegni",
    "PAGAMENTO IN DIREZIONE": "Pagamento Direzione",
    "RID DIREZIONE": "Pagamento Direzione",
}

TENANT_FLT = {"$in": [None, "tenant-principale-schiantarelli"]}


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    conti = {c["nome"]: c async for c in db.conti_cassa.find({}, {"_id": 0})}
    print("== 1) Merge conti duplicati/legacy ==")
    for src_nome, dst_nome in MERGE:
        src, dst = conti.get(src_nome), conti.get(dst_nome)
        if not src or not dst or src["id"] == dst["id"]:
            print(f"  skip: {src_nome} -> {dst_nome}")
            continue
        for coll in ("movimenti", "titoli"):
            r = await db[coll].update_many(
                {"conto_cassa_id": src["id"]}, {"$set": {"conto_cassa_id": dst["id"]}})
            if r.modified_count:
                print(f"  {coll}: {src_nome} -> {dst_nome}: {r.modified_count} righe")
        await db.conti_cassa.delete_one({"id": src["id"]})
        print(f"  conto eliminato: {src_nome}")

    print("== 2) mezzo_pagamento = nome conto (dove conto_cassa_id presente) ==")
    conti_validi = {c["id"]: c["nome"] async for c in db.conti_cassa.find({}, {"_id": 0, "id": 1, "nome": 1})}
    for coll in ("movimenti", "titoli"):
        for cid, nome in conti_validi.items():
            r = await db[coll].update_many(
                {"conto_cassa_id": cid, "categoria": {"$ne": "giroconto"},
                 "mezzo_pagamento": {"$ne": nome}},
                {"$set": {"mezzo_pagamento": nome}},
            )
            if r.modified_count:
                print(f"  {coll}: mezzo -> '{nome}': {r.modified_count}")

    print("== 3a) rinomina mezzi legacy (senza conto) ==")
    for coll in ("movimenti", "titoli"):
        for old, new in MAPPA_MEZZI.items():
            r = await db[coll].update_many(
                {"mezzo_pagamento": old, "agenzia_tenant_id": TENANT_FLT},
                {"$set": {"mezzo_pagamento": new}},
            )
            if r.modified_count:
                print(f"  {coll}: '{old}' -> '{new}': {r.modified_count}")

    print("== 3b) backfill conto_cassa_id da mezzo (esclusi direzione/giroconto) ==")
    for coll in ("movimenti", "titoli"):
        for cid, nome in conti_validi.items():
            if "direzione" in nome.lower():
                continue
            r = await db[coll].update_many(
                {"mezzo_pagamento": nome, "conto_cassa_id": None,
                 "agenzia_tenant_id": TENANT_FLT,
                 "is_direzione": {"$ne": True},
                 "categoria": {"$nin": ["giroconto", "incasso_premio_direzione"]}},
                {"$set": {"conto_cassa_id": cid}},
            )
            if r.modified_count:
                print(f"  {coll}: backfill conto '{nome}': {r.modified_count}")

    print("== Stato finale conti_cassa ==")
    async for c in db.conti_cassa.find({}, {"_id": 0, "nome": 1, "tipo": 1, "attivo": 1, "ordine": 1}).sort("ordine", 1):
        n_mov = await db.movimenti.count_documents({"conto_cassa_id": {"$exists": True}})
        print(" ", c)
    for coll in ("movimenti", "titoli"):
        print(f"  distinct mezzo {coll}:", sorted([str(v) for v in await db[coll].distinct("mezzo_pagamento")]))


if __name__ == "__main__":
    asyncio.run(main())
