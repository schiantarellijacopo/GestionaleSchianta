"""Ricalcola provvigione_collaboratore su TUTTO il portafoglio (tenant c5ae2d0e)
in base allo schema provvigionale, con risoluzione gerarchica identica al backend.

Regola per schema risolto:
  - percentuale_su_premio_netto > 0  -> collab = premio_netto * %
  - percentuale_su_premio      > 0  -> collab = premio_lordo * %
  - percentuale_collaboratore  > 0  -> collab = provvigione_agenzia_reale * %
"""
import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

load_dotenv("/app/backend/.env")
TID = "c5ae2d0e-283e-4513-aaf2-cbd97ef62d78"
NOW = datetime.now(timezone.utc).isoformat()


def build_resolver(schemas):
    idx = {}
    for s in schemas:
        if not s.get("attivo", True):
            continue
        key = (s.get("collaboratore_id"), s.get("compagnia_id"), s.get("ramo"))
        idx[key] = s

    def resolve(collab, comp, ramo):
        for key in [
            (collab, comp, ramo), (collab, comp, None), (collab, None, ramo),
            (collab, None, None), (None, comp, ramo), (None, comp, None),
            (None, None, ramo), (None, None, None),
        ]:
            if all(v is None for v in key):
                continue
            if key in idx:
                return idx[key]
        return None
    return resolve


def calc_collab(schema, provv_ag, netto, lordo):
    if not schema:
        return 0.0
    pn = float(schema.get("percentuale_su_premio_netto") or 0)
    pp = float(schema.get("percentuale_su_premio") or 0)
    pc = float(schema.get("percentuale_collaboratore") or 0)
    if pn > 0 and netto:
        return round(float(netto) * pn / 100.0, 2)
    if pp > 0 and lordo:
        return round(float(lordo) * pp / 100.0, 2)
    if pc > 0:
        return round(float(provv_ag or 0) * pc / 100.0, 2)
    return 0.0


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    schemas = await db.schema_provvigionale.find({"agenzia_tenant_id": TID}, {"_id": 0}).to_list(1000)
    resolve = build_resolver(schemas)
    print(f"Schemi caricati: {len(schemas)}")

    # Polizze del tenant: mappa id -> (collab, compagnia, ramo)
    pol = {}
    async for p in db.polizze.find({"agenzia_tenant_id": TID},
                                   {"_id": 0, "id": 1, "collaboratore_id": 1, "compagnia_id": 1,
                                    "ramo": 1, "provvigioni": 1, "premio_netto": 1, "premio_lordo": 1}):
        pol[p["id"]] = p
    print(f"Polizze: {len(pol)}")

    # ---- POLIZZE ----
    ops = []
    agg_p = 0
    for pid, p in pol.items():
        sch = resolve(p.get("collaboratore_id"), p.get("compagnia_id"), p.get("ramo"))
        collab = calc_collab(sch, p.get("provvigioni"), p.get("premio_netto"), p.get("premio_lordo"))
        ops.append(UpdateOne({"id": pid}, {"$set": {
            "provvigione_collaboratore": collab,
            "schema_provvigionale_id": (sch or {}).get("id"),
            "updated_at": NOW}}))
        if collab > 0:
            agg_p += 1
        if len(ops) >= 1000:
            await db.polizze.bulk_write(ops, ordered=False)
            ops = []
    if ops:
        await db.polizze.bulk_write(ops, ordered=False)
    print(f"Polizze aggiornate (con provv.collab>0): {agg_p}")

    # ---- TITOLI ----
    ops = []
    tot_t = agg_t = 0
    cur = db.titoli.find({"agenzia_tenant_id": TID},
                         {"_id": 0, "id": 1, "polizza_id": 1, "collaboratore_id": 1,
                          "provvigioni": 1, "importo_netto": 1, "importo_lordo": 1})
    async for t in cur:
        tot_t += 1
        p = pol.get(t.get("polizza_id"), {})
        collab_id = p.get("collaboratore_id") or t.get("collaboratore_id")
        sch = resolve(collab_id, p.get("compagnia_id"), p.get("ramo"))
        collab = calc_collab(sch, t.get("provvigioni"), t.get("importo_netto"), t.get("importo_lordo"))
        ops.append(UpdateOne({"id": t["id"]}, {"$set": {
            "provvigione_collaboratore": collab,
            "schema_provvigionale_id": (sch or {}).get("id"),
            "updated_at": NOW}}))
        if collab > 0:
            agg_t += 1
        if len(ops) >= 2000:
            await db.titoli.bulk_write(ops, ordered=False)
            ops = []
    if ops:
        await db.titoli.bulk_write(ops, ordered=False)
    print(f"Titoli totali: {tot_t} | aggiornati (con provv.collab>0): {agg_t}")


if __name__ == "__main__":
    asyncio.run(main())
