"""Unifica automaticamente i rami doppioni (stesso codice normalizzato).
Master = ramo con più riferimenti (polizze+sinistri+prodotti); tie-break: codice==nome, poi più vecchio.
DRY-RUN di default; passa --apply per eseguire.
"""
import asyncio
import os
import sys
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient

APPLY = "--apply" in sys.argv


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def norm(s):
    return (s or "").strip().upper()


async def _refs(db, valori):
    flt = {"ramo": {"$in": valori}}
    return {
        "polizze": await db.polizze.count_documents(flt),
        "sinistri": await db.sinistri.count_documents(flt),
        "prodotti": await db.prodotti.count_documents(flt),
    }


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    rami = await db.rami.find({}, {"_id": 0}).to_list(1000)
    attivi = [r for r in rami if r.get("attivo") is not False and not r.get("unito_in_ramo_id")]

    # raggruppa per codice normalizzato
    gruppi = {}
    for r in attivi:
        gruppi.setdefault(norm(r.get("codice")), []).append(r)
    dup_groups = {k: v for k, v in gruppi.items() if k and len(v) > 1}

    print(f"Rami attivi: {len(attivi)} | Gruppi con doppioni: {len(dup_groups)}")
    print(f"MODALITA: {'APPLY' if APPLY else 'DRY-RUN'}")
    print("=" * 70)

    tot_archiviati = 0
    tot_refs = {"polizze": 0, "sinistri": 0, "prodotti": 0}
    for codice, membri in sorted(dup_groups.items()):
        # calcola riferimenti per ciascun membro
        scored = []
        for m in membri:
            valori = list({(m.get("codice") or "").strip(), (m.get("nome") or "").strip()} - {""})
            refs = await _refs(db, valori)
            tot = refs["polizze"] + refs["sinistri"] + refs["prodotti"]
            same = 1 if norm(m.get("codice")) == norm(m.get("nome")) else 0
            scored.append((m, tot, same, m.get("created_at") or "", refs))
        # master: più riferimenti, poi codice==nome, poi più vecchio
        scored.sort(key=lambda x: (-x[1], -x[2], x[3]))
        master = scored[0][0]
        dups = [s[0] for s in scored[1:]]
        master_codice = (master.get("codice") or "").strip()

        print(f"\n[{codice}] {len(membri)} voci → MASTER: '{master.get('nome')}' (codice '{master_codice}', id {master['id'][:8]}, refs {scored[0][1]})")
        for m, tot, _, _, refs in scored[1:]:
            print(f"   - archivio '{m.get('nome')}' (codice '{m.get('codice')}', id {m['id'][:8]}) refs={refs}")

        if APPLY:
            for d in dups:
                valori = list({(d.get("codice") or "").strip(), (d.get("nome") or "").strip()} - {""})
                flt = {"ramo": {"$in": valori}}
                upd = {"$set": {"ramo": master_codice, "updated_at": _now_iso()}}
                tot_refs["polizze"] += (await db.polizze.update_many(flt, upd)).modified_count
                tot_refs["sinistri"] += (await db.sinistri.update_many(flt, upd)).modified_count
                tot_refs["prodotti"] += (await db.prodotti.update_many(flt, upd)).modified_count
                # ripunta eventuali import_mappings ramo → id master
                await db.import_mappings.update_many(
                    {"tipo": "ramo", "entita_id": d["id"]},
                    {"$set": {"entita_id": master["id"]}})
                await db.rami.update_one({"id": d["id"]}, {"$set": {
                    "attivo": False, "unito_in_ramo_id": master["id"],
                    "unito_in_codice": master_codice, "unito_at": _now_iso(),
                    "updated_at": _now_iso()}})
                tot_archiviati += 1

    print("\n" + "=" * 70)
    if APPLY:
        print(f"FATTO. Archiviati {tot_archiviati} doppioni. Riferimenti spostati: {tot_refs}")
    else:
        print("DRY-RUN: nessuna modifica. Rilancia con --apply per eseguire.")
    db.client.close() if hasattr(db, "client") else None


asyncio.run(main())
