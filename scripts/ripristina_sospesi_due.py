"""Ripristina in SOSPESI/ANTICIPI i titoli correnti delle polizze 182259867 e 184642872
(tenant Axicura c5ae2d0e). Riporta stato='da_incassare', titolo_coperto=True, rimuove
data_incasso (non più incassato). Mantiene data_copertura e importo_da_pagare.
"""
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
TID = "c5ae2d0e-283e-4513-aaf2-cbd97ef62d78"
NOW = datetime.now(timezone.utc).isoformat()
TITOLI = ["6c741594", "04668b0e"]  # prefissi id dei titoli correnti


async def main():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    for num in ["182259867", "184642872"]:
        p = await db.polizze.find_one({"agenzia_tenant_id": TID, "numero_polizza": num}, {"_id": 0, "id": 1})
        if not p:
            print(f"polizza {num} NON trovata in {TID}")
            continue
        # titolo corrente = non pregresso
        t = await db.titoli.find_one({"polizza_id": p["id"], "pregresso": {"$ne": True}}, {"_id": 0})
        if not t:
            print(f"polizza {num}: nessun titolo corrente (non pregresso)")
            continue
        res = await db.titoli.update_one(
            {"id": t["id"]},
            {"$set": {
                "stato": "da_incassare",
                "titolo_coperto": True,
                "data_incasso": None,
                "data_copertura": t.get("data_copertura") or NOW[:10],
                "importo_da_pagare": t.get("importo_da_pagare") if t.get("importo_da_pagare") is not None else t.get("importo_lordo", 0.0),
                "updated_at": NOW,
            }},
        )
        print(f"polizza {num} titolo {t['id'][:8]}: modificati={res.modified_count} "
              f"(lordo={t.get('importo_lordo')} da_pagare={t.get('importo_da_pagare')} cop={t.get('data_copertura')})")

    # Verifica: compaiono nei sospesi?
    print("\n--- Verifica sospesi (titolo_coperto=True, stato in da_incassare/insoluto) ---")
    for num in ["182259867", "184642872"]:
        p = await db.polizze.find_one({"agenzia_tenant_id": TID, "numero_polizza": num}, {"_id": 0, "id": 1})
        cur = await db.titoli.find_one({"polizza_id": p["id"], "pregresso": {"$ne": True}}, {"_id": 0})
        is_sosp = cur.get("titolo_coperto") is True and cur.get("stato") in ("da_incassare", "insoluto")
        print(f"  {num}: stato={cur.get('stato')} coperto={cur.get('titolo_coperto')} data_incasso={cur.get('data_incasso')} -> SOSPESO={is_sosp}")
    cli.close()


asyncio.run(main())
