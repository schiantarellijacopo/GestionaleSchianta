"""Sovrascrive i sospesi/anticipi (tenant c5ae2d0e) dal file /tmp/sospesi_new.csv.
Colonne: Num.Contratto; Rata del(dd/mm/yy); Contraente; Targa; Frazionamento; Rata(da pagare)
"""
import asyncio
import csv
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
TID = "c5ae2d0e-283e-4513-aaf2-cbd97ef62d78"
NOW = datetime.now(timezone.utc).isoformat()
CSV = "/tmp/sospesi_new.csv"


def d(dmy):
    g, m, y = dmy.strip().split("/")
    return f"20{y}-{m.zfill(2)}-{g.zfill(2)}"


def num(n):
    return n.split(" - ")[0].strip().lstrip("0")


def amt(s):
    return round(float(s.strip().replace(".", "").replace(",", ".")), 2) if s.strip() else 0.0


def plus1y(iso):
    y, m, g = iso.split("-")
    return f"{int(y)+1}-{m}-{g}"


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    rows = []
    with open(CSV, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            nc = (r.get("Num.Contratto") or "").strip()
            rd = (r.get("Rata del") or "").strip()
            if not nc or "/" not in rd:
                continue
            rows.append((nc, d(rd), amt(r["Rata"])))
    print(f"Righe CSV valide: {len(rows)}")

    pol_exact, pol_strip = {}, {}
    async for p in db.polizze.find({"agenzia_tenant_id": TID}, {"_id": 0, "id": 1, "numero_polizza": 1, "collaboratore_id": 1}):
        n = (p.get("numero_polizza") or "").strip()
        pol_exact[n] = p
        pol_strip[n.lstrip("0")] = p

    matched = set()
    upd = created = 0
    no_pol = []
    for raw_num, eff, rata in rows:
        p = pol_exact.get(raw_num.split(" - ")[0].strip()) or pol_strip.get(num(raw_num))
        if not p:
            no_pol.append(raw_num)
            continue
        t = await db.titoli.find_one({"polizza_id": p["id"], "agenzia_tenant_id": TID, "effetto": eff}, {"_id": 0, "id": 1})
        if not t:
            t = await db.titoli.find_one({"polizza_id": p["id"], "agenzia_tenant_id": TID, "importo_lordo": rata}, {"_id": 0, "id": 1})
        if not t:
            t = await db.titoli.find_one({"polizza_id": p["id"], "agenzia_tenant_id": TID, "importo_da_pagare": rata}, {"_id": 0, "id": 1})
        if t:
            await db.titoli.update_one({"id": t["id"]}, {"$set": {
                "titolo_coperto": True, "stato": "da_incassare", "data_incasso": None,
                "data_copertura": eff, "importo_da_pagare": rata, "pregresso": False,
                "updated_at": NOW}})
            matched.add(t["id"])
            upd += 1
        else:
            nid = str(uuid.uuid4())
            await db.titoli.insert_one({
                "id": nid, "polizza_id": p["id"], "agenzia_tenant_id": TID,
                "tipo": "rinnovo", "effetto": eff, "scadenza": plus1y(eff),
                "stato": "da_incassare", "titolo_coperto": True, "data_copertura": eff,
                "importo_lordo": rata, "importo_netto": rata, "importo_da_pagare": rata,
                "provvigioni": 0.0, "provvigione_collaboratore": 0.0, "pregresso": False,
                "collaboratore_id": p.get("collaboratore_id"),
                "fonte": "manuale", "stato_carico": "validato",
                "note_carico": "Sospeso da CSV", "created_at": NOW, "updated_at": NOW})
            matched.add(nid)
            created += 1

    # Sospesi correnti non nel CSV -> incassati
    incassati = 0
    async for t in db.titoli.find({"agenzia_tenant_id": TID, "titolo_coperto": True,
                                   "stato": {"$in": ["da_incassare", "insoluto"]}},
                                  {"_id": 0, "id": 1, "data_copertura": 1, "effetto": 1}):
        if t["id"] in matched:
            continue
        await db.titoli.update_one({"id": t["id"]}, {"$set": {
            "stato": "incassato", "data_incasso": t.get("data_copertura") or t.get("effetto") or NOW[:10],
            "titolo_coperto": False, "pregresso": True, "updated_at": NOW}})
        incassati += 1

    print(f"Aggiornati: {upd} | Creati: {created} | Polizza non trovata: {len(no_pol)} -> {no_pol}")
    print(f"Ex-sospesi non nel CSV -> incassati: {incassati}")


if __name__ == "__main__":
    asyncio.run(main())
