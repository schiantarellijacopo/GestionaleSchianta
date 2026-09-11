"""Aggiorna termini_mora_giorni su polizze e libreria Prodotti dai dati OMNIA (rec20 giorni_mora).

Regole:
- Match polizza per numero_polizza (senza zeri iniziali).
- Aggiorna solo dove OMNIA ha giorni_mora > 0 (non azzera i default esistenti).
- Non tocca la disdetta (assente in OMNIA).
- Libreria Prodotti: imposta termini_mora_giorni al valore PREVALENTE per prodotto.
"""
import csv
import os
import asyncio
from collections import defaultdict, Counter
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
OMNIA = "/tmp/omnia_zip/rec20oweb.csv"


def _now():
    return datetime.now(timezone.utc).isoformat()


def carica_mora_omnia():
    mora = {}
    with open(OMNIA, newline="", encoding="latin-1") as f:
        r = csv.reader(f, delimiter=";")
        hdr = next(r)
        ip = hdr.index("numero_polizza_cmp")
        im = hdr.index("giorni_mora")
        for row in r:
            if len(row) <= max(ip, im):
                continue
            num = row[ip].strip().lstrip("0")
            try:
                g = int(row[im])
            except ValueError:
                g = 0
            if num and g > 0:
                mora[num] = g
    return mora


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    mora = carica_mora_omnia()
    print(f"OMNIA: {len(mora)} numeri polizza con giorni_mora>0")

    # 1) Polizze
    aggiornate = 0
    gia_ok = 0
    perprod = defaultdict(Counter)
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1,
                                        "prodotto": 1, "termini_mora_giorni": 1}):
        n = (p.get("numero_polizza") or "").strip().lstrip("0")
        if n not in mora:
            continue
        g = mora[n]
        if p.get("prodotto"):
            perprod[p["prodotto"]][g] += 1
        if p.get("termini_mora_giorni") == g:
            gia_ok += 1
            continue
        await db.polizze.update_one(
            {"id": p["id"]},
            {"$set": {"termini_mora_giorni": g, "updated_at": _now()}},
        )
        aggiornate += 1
    print(f"Polizze aggiornate: {aggiornate} (gia corrette: {gia_ok})")

    # 2) Libreria Prodotti — valore prevalente per prodotto
    prod_agg = 0
    for prod_nome, cnt in perprod.items():
        prevalente = cnt.most_common(1)[0][0]
        res = await db.prodotti.update_many(
            {"nome": prod_nome},
            {"$set": {"termini_mora_giorni": prevalente, "updated_at": _now()}},
        )
        if res.modified_count:
            prod_agg += res.modified_count
            print(f"  Prodotto '{prod_nome}' -> {prevalente} gg ({res.modified_count} record)")
    print(f"Prodotti libreria aggiornati: {prod_agg}")


if __name__ == "__main__":
    asyncio.run(main())
