"""Inserisce polizza.provvigioni (dove mancante/0) usando la provvigione del
titolo PIU' RECENTE della polizza (annualita corrente). Applica solo se >0.
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _prov(t):
    v = t.get("provvigione_totale")
    if v in (None, 0, 0.0):
        v = t.get("provvigioni")
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    # Polizze che mancano di provvigione
    missing = set()
    async for p in db.polizze.find(
        {"$or": [{"provvigioni": {"$in": [None, 0, 0.0]}}, {"provvigioni": {"$exists": False}}]},
        {"_id": 0, "id": 1},
    ):
        missing.add(p["id"])
    print(f"Polizze senza provvigione: {len(missing)}")

    # Titolo piu' recente (per effetto) di ciascuna polizza mancante
    best = {}  # polizza_id -> (effetto, provvigione)
    async for t in db.titoli.find(
        {"polizza_id": {"$in": list(missing)}},
        {"_id": 0, "polizza_id": 1, "effetto": 1, "provvigioni": 1, "provvigione_totale": 1},
    ):
        pid = t.get("polizza_id")
        if pid not in missing:
            continue
        eff = t.get("effetto") or ""
        cur = best.get(pid)
        if cur is None or eff >= cur[0]:
            best[pid] = (eff, _prov(t))

    aggiornate = 0
    zero = 0
    for pid, (eff, prov) in best.items():
        if prov > 0:
            await db.polizze.update_one(
                {"id": pid}, {"$set": {"provvigioni": prov, "updated_at": _now()}}
            )
            aggiornate += 1
        else:
            zero += 1
    print(f"Polizze aggiornate con provvigione: {aggiornate}")
    print(f"Polizze con titolo recente a provvigione 0 (lasciate): {zero}")
    print(f"Polizze senza alcun titolo (lasciate): {len(missing) - len(best)}")


if __name__ == "__main__":
    asyncio.run(main())
