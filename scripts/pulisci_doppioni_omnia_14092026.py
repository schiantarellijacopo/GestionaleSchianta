"""Pulizia doppioni polizze creati dall'import OMNIA incrementale del 14/09/2026.
- Trova le polizze create il 14/09 con id_polizza_exp valorizzato che hanno un GEMELLO
  precedente (stesso numero_polizza, creato prima del 14/09) nello stesso tenant.
- Backup CSV, poi copia id_polizza_exp sull'originale (se mancante), elimina titoli/movimenti
  del doppione ed elimina il doppione. Tiene le polizze SENZA gemello.
"""
import asyncio
import csv
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
TID = "c5ae2d0e-283e-4513-aaf2-cbd97ef62d78"
CSV_PATH = "/app/doppioni_omnia_14092026.csv"


async def main(apply: bool):
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    dups = await db.polizze.find(
        {"agenzia_tenant_id": TID, "created_at": {"$gte": "2026-09-14", "$lt": "2026-09-15"},
         "id_polizza_exp": {"$ne": None}},
        {"_id": 0},
    ).to_list(2000)

    rows = []
    to_delete = []
    for dp in dups:
        num = dp.get("numero_polizza")
        orig = await db.polizze.find_one(
            {"agenzia_tenant_id": TID, "numero_polizza": num, "created_at": {"$lt": "2026-09-14"}},
            {"_id": 0},
        )
        if not orig:
            continue  # nessun gemello -> tienila
        ntit = await db.titoli.count_documents({"polizza_id": dp["id"]})
        nmov = await db.movimenti.count_documents({"polizza_id": dp["id"]})
        rows.append({
            "numero_polizza": num,
            "dup_id": dp["id"], "dup_ramo": dp.get("ramo"), "dup_id_exp": dp.get("id_polizza_exp"),
            "dup_titoli": ntit, "dup_movimenti": nmov, "dup_created": dp.get("created_at"),
            "orig_id": orig["id"], "orig_ramo": orig.get("ramo"),
            "orig_id_exp": orig.get("id_polizza_exp"), "orig_created": orig.get("created_at"),
        })
        to_delete.append((dp, orig))

    # Backup CSV
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["numero_polizza"])
        w.writeheader()
        w.writerows(rows)
    print(f"CSV backup: {CSV_PATH} ({len(rows)} doppioni)")

    if not apply:
        print("DRY-RUN: nessuna modifica. Rilancia con --apply per eseguire.")
        cli.close()
        return

    n_pol = n_tit = n_mov = n_expcopy = 0
    for dp, orig in to_delete:
        # copia id_polizza_exp sull'originale se mancante (per futuri import)
        if not orig.get("id_polizza_exp") and dp.get("id_polizza_exp"):
            await db.polizze.update_one({"id": orig["id"]}, {"$set": {"id_polizza_exp": dp["id_polizza_exp"]}})
            n_expcopy += 1
        tit_ids = [t["id"] async for t in db.titoli.find({"polizza_id": dp["id"]}, {"_id": 0, "id": 1})]
        if tit_ids:
            r = await db.movimenti.delete_many({"titolo_id": {"$in": tit_ids}})
            n_mov += r.deleted_count
        r = await db.movimenti.delete_many({"polizza_id": dp["id"]})
        n_mov += r.deleted_count
        r = await db.titoli.delete_many({"polizza_id": dp["id"]})
        n_tit += r.deleted_count
        await db.polizze.delete_one({"id": dp["id"]})
        n_pol += 1

    print(f"Eliminati: polizze={n_pol}, titoli={n_tit}, movimenti={n_mov}, id_exp copiati su originale={n_expcopy}")
    # verifica residua
    pipe = [{"$match": {"agenzia_tenant_id": TID}}, {"$group": {"_id": "$numero_polizza", "n": {"$sum": 1}}}, {"$match": {"n": {"$gt": 1}}}]
    resid = await db.polizze.aggregate(pipe).to_list(100000)
    print("Numeri polizza ancora duplicati:", len(resid))
    cli.close()


if __name__ == "__main__":
    import sys
    asyncio.run(main(apply="--apply" in sys.argv))
