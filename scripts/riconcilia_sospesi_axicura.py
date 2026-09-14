"""Riconcilia i titoli SOSPESI/anticipati del tenant Axicura con il PDF ufficiale.

- Titoli presenti nel PDF -> coperti: titolo_coperto=True, stato='da_incassare',
  data_copertura = colonna Copertura del PDF, importo_lordo = Totale,
  importo_da_pagare = colonna 'Da Pagare'.
- Titoli attualmente sospesi nel CRM ma NON nel PDF -> incassati (erano già saldati):
  stato='incassato', data_incasso = data_copertura/effetto, titolo_coperto=False.

DRY=1 per anteprima senza scrivere.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
from database import db, set_current_user  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

DRY = os.environ.get("DRY", "0") == "1"
EMAIL = "jacopo@schiantarelli.it"
NOW = datetime.now(timezone.utc).isoformat()


def _d(dmy):
    g, m2, y = dmy.split("-")
    return f"{y}-{m2}-{g}"


def _norm(n):
    return (n or "").split(" - ")[0].strip().lstrip("0")


# (contratto, rata_del, copertura, totale, da_pagare)
PDF = [
    ("32202217", "13-08-2026", "24-08-2026", 689.50, 689.50),
    ("730019297", "01-09-2026", "01-09-2026", 114.00, 114.00),
    ("180024557", "17-11-2022", "02-12-2022", 356.50, 19.38),
    ("183629775", "30-01-2026", "30-01-2026", 46.00, 46.00),
    ("182259573", "02-06-2026", "10-06-2026", 35.00, 35.00),
    ("730782111", "23-06-2026", "03-07-2026", 145.00, 145.00),
    ("730859789", "23-06-2026", "03-07-2026", 215.00, 215.00),
    ("730814301", "01-06-2026", "17-06-2026", 56.00, 56.00),
    ("180992571", "22-12-2023", "22-12-2023", 15.00, 15.00),
    ("180394255", "17-03-2023", "17-03-2023", 415.00, 230.00),
    ("180992397", "27-10-2023", "13-11-2023", 600.00, 600.00),
    ("180992397", "27-10-2024", "22-10-2024", 660.50, 660.50),
    ("180992434", "17-11-2024", "18-11-2024", 34.50, 34.50),
    ("183628941", "20-03-2025", "20-03-2025", 200.00, 200.00),
    ("183629529", "27-10-2025", "27-10-2025", 600.00, 600.00),
    ("184643059", "04-07-2026", "03-07-2026", 224.00, 224.00),
    ("1001009499", "07-07-2026", "08-07-2026", 50.00, 50.00),
    ("182259483", "30-04-2025", "30-04-2025", 222.00, 222.00),
    ("184643228", "24-06-2026", "24-06-2026", 1245.00, 1245.00),
    ("975218000", "09-09-2026", "09-09-2026", 48.00, 48.00),
    ("58550700024", "09-09-2021", "20-09-2021", 52.00, 52.00),
    ("1001004878", "02-09-2026", "07-09-2026", 26.00, 26.00),
    ("1000124310", "06-09-2026", "04-09-2026", 47.00, 47.00),
    ("1000946659", "04-09-2026", "08-09-2026", 58.00, 58.00),
    ("180992065", "10-09-2026", "11-09-2026", 338.50, 338.50),
    ("183629406", "05-09-2026", "11-09-2026", 1222.00, 1222.00),
    ("184643448", "07-09-2026", "11-09-2026", 1400.00, 1400.00),
    ("1001856670", "04-09-2026", "04-09-2026", 32.00, 32.00),
    ("975217000", "09-09-2026", "09-09-2026", 48.00, 48.00),
    ("730043728", "07-09-2026", "11-09-2026", 181.50, 181.50),
    ("184643452", "11-09-2026", "11-09-2026", 75.00, 75.00),
    ("182259854", "11-09-2026", "11-09-2026", 967.00, 967.00),
    ("1001616709", "11-09-2026", "11-09-2026", 81.00, 81.00),
    ("1001494291", "11-09-2026", "10-09-2026", 26.00, 26.00),
    ("1001267878", "10-09-2026", "07-09-2026", 38.00, 38.00),
    ("180992240 - 1", "27-12-2024", "27-12-2024", -116.50, -116.50),
    ("183629179", "03-06-2025", "03-06-2025", -30.00, -30.00),
    ("184643403 - 1", "03-09-2026", "03-09-2026", -65.00, -65.00),
    ("180991931", "09-02-2025", "25-03-2025", 1559.00, 1559.00),
    ("184643415", "31-08-2026", "31-08-2026", 22.50, 22.50),
]


async def main():
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    u = await raw.users.find_one({"email": EMAIL}, {"_id": 0})
    set_current_user(u)

    # mappa numero_polizza(norm) -> [polizza_id]
    pol_by = {}
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1}):
        pol_by.setdefault(_norm(p.get("numero_polizza")), []).append(p["id"])

    matched_ids = set()
    coperti = 0
    no_pol = []
    no_titolo = []
    for contratto, rata, cop, tot, dap in PDF:
        pids = pol_by.get(_norm(contratto))
        if not pids:
            no_pol.append(contratto)
            continue
        eff = _d(rata)
        cop_iso = _d(cop)
        t = await db.titoli.find_one({"polizza_id": {"$in": pids}, "effetto": eff}, {"_id": 0, "id": 1})
        if not t:
            # fallback: match per importo lordo sulla polizza
            t = await db.titoli.find_one({"polizza_id": {"$in": pids}, "importo_lordo": tot}, {"_id": 0, "id": 1})
        if not t:
            no_titolo.append(f"{contratto}@{eff}")
            continue
        matched_ids.add(t["id"])
        coperti += 1
        if not DRY:
            await db.titoli.update_one({"id": t["id"]}, {"$set": {
                "titolo_coperto": True, "stato": "da_incassare",
                "data_copertura": cop_iso, "data_incasso": None,
                "importo_lordo": tot, "importo_da_pagare": dap, "updated_at": NOW,
            }})

    # Sospesi correnti NON nel PDF -> incassati
    cur = db.titoli.find({"titolo_coperto": True, "stato": {"$in": ["da_incassare", "insoluto"]}},
                         {"_id": 0, "id": 1, "data_copertura": 1, "effetto": 1})
    da_incassare = 0
    async for t in cur:
        if t["id"] in matched_ids:
            continue
        da_incassare += 1
        if not DRY:
            dinc = t.get("data_copertura") or t.get("effetto") or NOW[:10]
            await db.titoli.update_one({"id": t["id"]}, {"$set": {
                "stato": "incassato", "data_incasso": dinc, "titolo_coperto": False, "updated_at": NOW,
            }})

    print(f"DRY={DRY}")
    print(f"PDF righe: {len(PDF)} | coperti (match): {coperti}")
    print(f"  senza polizza: {len(no_pol)} -> {no_pol}")
    print(f"  polizza trovata ma titolo no: {len(no_titolo)} -> {no_titolo}")
    print(f"Sospesi correnti NON nel PDF -> incassati: {da_incassare}")


if __name__ == "__main__":
    asyncio.run(main())
