"""Annulla le polizze attive/sospese senza incasso dal 2025, distinguendo i casi.

Regole (tenant utente):
  A) con titoli e max scadenza < oggi  -> annulla + storna titoli aperti
  B) senza alcun titolo                -> annulla (tranne compagnia UCA)
  C) con titoli e scadenza futura      -> NON tocca (nuova/in attesa)
Le polizze con incasso/copertura dal 2025 restano attive.

Uso:  DRY=1 python3 annulla_lapsed_2025.py   (report)
      DRY=0 python3 annulla_lapsed_2025.py   (applica)
"""
import asyncio, os, sys
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

TENANT = os.environ.get("TENANT_ID", "31b4950e-85c2-4232-a31f-ba226b7923fe")
DRY = os.environ.get("DRY", "1") == "1"
TODAY = datetime.now(timezone.utc).date().isoformat()
NOW = datetime.now(timezone.utc).isoformat()
APERTI = ["da_incassare", "insoluto", "sospeso"]


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    comp = {}
    async for x in db.compagnie.find({}, {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1}):
        comp[x["id"]] = (x.get("ragione_sociale") or x.get("codice") or "").upper()

    ok, has_tit, maxsc = {}, set(), {}
    async for t in db.titoli.find(
        {"agenzia_tenant_id": TENANT},
        {"_id": 0, "polizza_id": 1, "stato": 1, "titolo_coperto": 1,
         "data_incasso": 1, "data_copertura": 1, "scadenza": 1},
    ):
        pid = t.get("polizza_id")
        if not pid:
            continue
        has_tit.add(pid)
        if t.get("stato") == "incassato" or t.get("titolo_coperto"):
            d = t.get("data_incasso") or t.get("data_copertura") or ""
            if d > ok.get(pid, ""):
                ok[pid] = d
        sc = t.get("scadenza") or ""
        if sc > maxsc.get(pid, ""):
            maxsc[pid] = sc

    ops, ids_storno, a, b, cc, uca_keep, esA, esB = [], [], 0, 0, 0, 0, [], []
    async for p in db.polizze.find(
        {"agenzia_tenant_id": TENANT, "stato": {"$in": ["attiva", "sospesa"]}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "scadenza": 1, "compagnia_id": 1},
    ):
        pid = p["id"]
        if ok.get(pid, "") >= "2025-01-01":
            continue
        if pid in has_tit:
            ms = maxsc.get(pid, "") or (p.get("scadenza") or "")
            if ms >= TODAY:
                cc += 1
                continue                                  # C: futura → skip
            a += 1
            fine = ms or p.get("scadenza") or TODAY
            motivo = "Scaduta senza incasso dal 2025"
            ids_storno.append(pid)
            if len(esA) < 8: esA.append((p.get("numero_polizza"), fine))
        else:
            if "UCA" in comp.get(p.get("compagnia_id"), ""):
                uca_keep += 1
                continue                                  # B-UCA: skip
            b += 1
            fine = p.get("scadenza") or TODAY
            motivo = "Polizza senza titoli nel flusso (compagnia non UCA)"
            if len(esB) < 8: esB.append((p.get("numero_polizza"), fine))
        ops.append(UpdateOne({"id": pid}, {"$set": {
            "stato": "annullata", "data_annullamento": fine,
            "motivo_annullamento": motivo, "updated_at": NOW}}))

    print(f"today={TODAY} dry={DRY}", flush=True)
    print(f"A scadute con titoli: {a} | B senza titoli (non UCA): {b} | "
          f"C future skip: {cc} | UCA tenute: {uca_keep}", flush=True)
    print(f"TOTALE da annullare: {len(ops)}", flush=True)
    print("es A:", esA, flush=True)
    print("es B:", esB, flush=True)

    if not ops or DRY:
        return
    for i in range(0, len(ops), 1000):
        r = await db.polizze.bulk_write(ops[i:i + 1000], ordered=False)
        print("annullate batch:", r.modified_count, flush=True)
    tot = 0
    for i in range(0, len(ids_storno), 500):
        chunk = ids_storno[i:i + 500]
        rr = await db.titoli.update_many(
            {"polizza_id": {"$in": chunk}, "stato": {"$in": APERTI}},
            {"$set": {"stato": "stornato",
                      "nota": "Stornato: polizza scaduta senza incasso dal 2025",
                      "updated_at": NOW}})
        tot += rr.modified_count
    print("titoli stornati:", tot, flush=True)


asyncio.run(main())
