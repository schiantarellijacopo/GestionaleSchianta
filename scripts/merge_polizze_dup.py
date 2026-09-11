"""Unisce SOLO i doppioni "veri" (gruppi da 2-3 copie) nel tenant utente.

- Salta le polizze collettive/libro matricola (gruppi con >=4 copie).
- Mantiene la polizza con PIU' titoli (primaria), sposta gli altri titoli su di essa.
- Deduplica i titoli: se per stessa (effetto, scadenza, lordo) esiste un titolo
  INCASSATO/COPERTO e anche uno APERTO, elimina l'aperto (residuo non pagato).
- Elimina le polizze rimaste senza titoli.

Uso:  DRY=1 python3 merge_polizze_dup.py   (report)
      DRY=0 python3 merge_polizze_dup.py   (applica)
"""
import asyncio, os, sys
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient

TENANT = os.environ.get("TENANT_ID", "31b4950e-85c2-4232-a31f-ba226b7923fe")
DRY = os.environ.get("DRY", "1") == "1"
MAX_COPIE = int(os.environ.get("MAX_COPIE", "3"))   # oltre = collettiva, si salta
APERTI = {"da_incassare", "insoluto", "sospeso"}
CHIUSI = {"incassato"}


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    groups = await db.polizze.aggregate([
        {"$match": {"agenzia_tenant_id": TENANT, "numero_polizza": {"$ne": None}}},
        {"$group": {"_id": "$numero_polizza", "ids": {"$push": "$id"}, "cnt": {"$sum": 1}}},
        {"$match": {"cnt": {"$gt": 1, "$lte": MAX_COPIE}}},
    ]).to_list(100000)

    n_grp = tot_moved = tot_deleted = tot_pol_removed = 0
    esempi = []
    for g in groups:
        ids = g["ids"]
        counts = {pid: await db.titoli.count_documents({"polizza_id": pid}) for pid in ids}
        primary = max(ids, key=lambda x: counts[x])
        others = [x for x in ids if x != primary]
        n_grp += 1

        for pid in others:
            if counts[pid] and not DRY:
                await db.titoli.update_many({"polizza_id": pid}, {"$set": {"polizza_id": primary}})
            tot_moved += counts[pid]

        # dedup sulla primaria (post-spostamento). In DRY simuliamo unendo le liste.
        if DRY:
            tit = []
            for pid in ids:
                tit += await db.titoli.find({"polizza_id": pid}, {"_id": 0}).to_list(10000)
        else:
            tit = await db.titoli.find({"polizza_id": primary}, {"_id": 0}).to_list(10000)
        buckets = {}
        for t in tit:
            k = (t.get("effetto"), t.get("scadenza"), round(float(t.get("importo_lordo") or 0), 2))
            buckets.setdefault(k, []).append(t)
        to_del = []
        for arr in buckets.values():
            if len(arr) < 2:
                continue
            if not any((t.get("stato") in CHIUSI or t.get("titolo_coperto")) for t in arr):
                continue
            for t in arr:
                if t.get("stato") in APERTI and not t.get("titolo_coperto"):
                    to_del.append(t["id"])
        if to_del:
            tot_deleted += len(to_del)
            if not DRY:
                await db.titoli.delete_many({"id": {"$in": to_del}})

        for pid in others:
            rem = (await db.titoli.count_documents({"polizza_id": pid})) if not DRY else \
                  (counts[pid] if pid not in [] else 0)
            # in DRY: dopo lo (simulato) spostamento gli 'others' restano vuoti
            rem = 0 if DRY else rem
            if rem == 0:
                tot_pol_removed += 1
                if not DRY:
                    await db.polizze.delete_one({"id": pid})

        if len(esempi) < 12:
            esempi.append((g["_id"], f"copie={g['cnt']}", f"primaria_titoli={counts[primary]}",
                           f"del_aperti={len(to_del)}"))

    print(f"tenant={TENANT[:12]} dry={DRY} max_copie={MAX_COPIE}", flush=True)
    print(f"gruppi trattati: {n_grp} | titoli spostati: {tot_moved} | "
          f"titoli aperti eliminati: {tot_deleted} | polizze eliminate: {tot_pol_removed}", flush=True)
    for e in esempi:
        print("  ", e, flush=True)


asyncio.run(main())
