"""Sovrascrive i SOSPESI del tenant jacopo (c5ae2d0e) con il PDF ufficiale 'Sospesi.pdf'.

- Ogni riga del PDF -> titolo coperto: titolo_coperto=True, stato='da_incassare',
  data_copertura da PDF, importo_lordo=totale, importo_da_pagare=da_pagare.
  Se il titolo non esiste in c5ae2d0e viene CREATO.
- Tutti gli altri sospesi c5ae2d0e non presenti nel PDF -> incassati.
- 730801946 -> incassato 01/09/2026 BONIFICO BPER SONDRIO (fix specifico).
- Pulizia: elimina i 3 titoli negativi creati per errore su tenant-principale.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
TID = "c5ae2d0e-283e-4513-aaf2-cbd97ef62d78"
NOW = datetime.now(timezone.utc).isoformat()


def d(dmy):
    g, m, y = dmy.split("-")
    return f"{y}-{m}-{g}"


def norm(n):
    return (n or "").replace(" ", "").split("-")[0].strip().lstrip("0") if " - " not in (n or "") else n.split(" - ")[0].strip().lstrip("0")


def plus1y(iso):
    y, m, g = iso.split("-")
    return f"{int(y)+1}-{m}-{g}"


# (numero, effetto, copertura, totale, da_pagare)
ROWS = [
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
    ("184643451", "14-09-2026", "11-09-2026", 401.00, 401.00),
    ("1000124310", "06-09-2026", "04-09-2026", 47.00, 47.00),
    ("1000946659", "04-09-2026", "08-09-2026", 58.00, 58.00),
    ("180992065", "10-09-2026", "11-09-2026", 338.50, 338.50),
    ("180991990", "12-09-2026", "11-09-2026", 412.50, 412.50),
    ("183629406", "05-09-2026", "11-09-2026", 1222.00, 1222.00),
    ("184643448", "07-09-2026", "11-09-2026", 1400.00, 1400.00),
    ("1001668659", "17-09-2026", "11-09-2026", 58.00, 58.00),
    ("184643442", "17-09-2026", "11-09-2026", 4975.00, 4975.00),
    ("730039889", "15-09-2026", "11-09-2026", 575.00, 575.00),
    ("1000694861", "15-09-2026", "11-09-2026", 255.00, 255.00),
    ("1001856670", "04-09-2026", "04-09-2026", 32.00, 32.00),
    ("975217000", "09-09-2026", "09-09-2026", 48.00, 48.00),
    ("730043728", "07-09-2026", "11-09-2026", 181.50, 181.50),
    ("732225145", "16-09-2026", "11-09-2026", 1076.50, 1076.50),
    ("184643452", "11-09-2026", "11-09-2026", 75.00, 75.00),
    ("182259854", "11-09-2026", "11-09-2026", 967.00, 967.00),
    ("1001616709", "11-09-2026", "11-09-2026", 81.00, 81.00),
    ("1001494291", "11-09-2026", "10-09-2026", 26.00, 26.00),
    ("1001267878", "10-09-2026", "07-09-2026", 38.00, 38.00),
    ("180992240", "27-12-2024", "27-12-2024", -116.50, -116.50),
    ("183629179", "03-06-2025", "03-06-2025", -30.00, -30.00),
    ("184643403", "03-09-2026", "03-09-2026", -65.00, -65.00),
    ("180991931", "09-02-2025", "25-03-2025", 1559.00, 1559.00),
    ("732937512", "12-09-2026", "11-09-2026", 2292.00, 2292.00),
    ("184643415", "31-08-2026", "31-08-2026", 22.50, 22.50),
]


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    # Pulizia: elimina i negativi creati per errore su tenant-principale
    delr = await db.titoli.delete_many({
        "agenzia_tenant_id": "tenant-principale-schiantarelli",
        "note_carico": "Sospeso negativo (riconciliazione PDF)",
    })
    print(f"Puliti negativi stray su tenant-principale: {delr.deleted_count}")

    # mappa numero_polizza -> polizza (solo c5ae2d0e)
    pol_exact, pol_strip = {}, {}
    async for p in db.polizze.find({"agenzia_tenant_id": TID}, {"_id": 0, "id": 1, "numero_polizza": 1, "collaboratore_id": 1}):
        num = (p.get("numero_polizza") or "").strip()
        pol_exact[num] = p
        pol_strip[num.lstrip("0")] = p

    matched = set()
    coperti = created = 0
    no_pol = []
    for num, eff, cop, tot, dap in ROWS:
        p = pol_exact.get(num) or pol_strip.get(num.lstrip("0"))
        if not p:
            no_pol.append(num)
            continue
        eff_i, cop_i = d(eff), d(cop)
        t = await db.titoli.find_one({"polizza_id": p["id"], "agenzia_tenant_id": TID, "effetto": eff_i}, {"_id": 0, "id": 1})
        if not t:
            t = await db.titoli.find_one({"polizza_id": p["id"], "agenzia_tenant_id": TID, "importo_lordo": tot}, {"_id": 0, "id": 1})
        if t:
            await db.titoli.update_one({"id": t["id"]}, {"$set": {
                "titolo_coperto": True, "stato": "da_incassare", "data_incasso": None,
                "data_copertura": cop_i, "importo_lordo": tot, "importo_da_pagare": dap,
                "updated_at": NOW}})
            matched.add(t["id"])
            coperti += 1
        else:
            tid_new = str(uuid.uuid4())
            await db.titoli.insert_one({
                "id": tid_new, "polizza_id": p["id"], "agenzia_tenant_id": TID,
                "tipo": "rinnovo", "effetto": eff_i, "scadenza": plus1y(eff_i),
                "stato": "da_incassare", "titolo_coperto": True, "data_copertura": cop_i,
                "importo_lordo": tot, "importo_netto": tot, "importo_da_pagare": dap,
                "provvigioni": 0.0, "provvigione_collaboratore": 0.0,
                "collaboratore_id": p.get("collaboratore_id"),
                "fonte": "manuale", "stato_carico": "validato",
                "note_carico": "Sospeso da PDF (riconciliazione)",
                "created_at": NOW, "updated_at": NOW})
            matched.add(tid_new)
            created += 1

    # Altri sospesi c5ae2d0e non nel PDF -> incassati
    incassati = 0
    async for t in db.titoli.find({"agenzia_tenant_id": TID, "titolo_coperto": True,
                                   "stato": {"$in": ["da_incassare", "insoluto"]}},
                                  {"_id": 0, "id": 1, "data_copertura": 1, "effetto": 1}):
        if t["id"] in matched:
            continue
        dinc = t.get("data_copertura") or t.get("effetto") or NOW[:10]
        await db.titoli.update_one({"id": t["id"]}, {"$set": {
            "stato": "incassato", "data_incasso": dinc, "titolo_coperto": False, "updated_at": NOW}})
        incassati += 1

    # 730801946 -> incassato specifico (in c5ae2d0e)
    p = await db.polizze.find_one({"numero_polizza": "730801946", "agenzia_tenant_id": TID}, {"_id": 0, "id": 1})
    if p:
        await db.titoli.update_many({"polizza_id": p["id"], "agenzia_tenant_id": TID},
            {"$set": {"stato": "incassato", "data_incasso": "2026-09-01", "data_copertura": "2026-09-01",
                      "mezzo_pagamento": "BONIFICO BPER SONDRIO", "titolo_coperto": False, "updated_at": NOW}})

    print(f"PDF righe: {len(ROWS)} | coperti aggiornati: {coperti} | creati: {created} | non trovati(polizza): {no_pol}")
    print(f"Altri sospesi -> incassati: {incassati}")


if __name__ == "__main__":
    asyncio.run(main())
