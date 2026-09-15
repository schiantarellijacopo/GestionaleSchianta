"""Test auto-chiusura regolazione premio quando il titolo è saldato."""
import asyncio
import os
import sys
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # trova la polizza di regolazione col titolo collegato
    pol = await db.polizze.find_one({"numero_polizza": "732864759", "regolazione_premio": True})
    assert pol, "polizza test non trovata"
    pid = pol["id"]
    tit_id = pol.get("regolazione_titolo_id")
    print("polizza", pid, "titolo", tit_id, "stato_reg", pol.get("regolazione_stato"))

    # snapshot per ripristino (valori noti originali forzati per sicurezza)
    orig_reg_stato = "dati_ricevuti"
    orig_tit_stato = "da_incassare"

    # SETUP scenario: regolazione titolo_generato + titolo incassato
    await db.polizze.update_one({"id": pid}, {"$set": {"regolazione_stato": "titolo_generato"}})
    await db.titoli.update_one({"id": tit_id}, {"$set": {"stato": "incassato"}})

    # Simula la logica dell'endpoint list_regolazioni
    from routes.regolazione_premio import list_regolazioni

    class _U:  # utente fittizio admin
        pass
    rows = await list_regolazioni(user={"role": "admin", "id": "x"})
    row = next((r for r in rows if r["polizza_id"] == pid), None)
    print("STATO CALCOLATO endpoint:", row["stato"] if row else None)
    reloaded = await db.polizze.find_one({"id": pid}, {"_id": 0, "regolazione_stato": 1})
    print("STATO PERSISTITO in db:", reloaded.get("regolazione_stato"))
    ok_close = row and row["stato"] == "chiusa" and reloaded.get("regolazione_stato") == "chiusa"
    print("AUTO-CHIUSURA OK:", ok_close)

    # SETUP scenario riapertura: titolo torna da_incassare, reg era chiusa
    await db.titoli.update_one({"id": tit_id}, {"$set": {"stato": "da_incassare"}})
    rows2 = await list_regolazioni(user={"role": "admin", "id": "x"})
    row2 = next((r for r in rows2 if r["polizza_id"] == pid), None)
    print("STATO dopo riapertura:", row2["stato"] if row2 else None)
    ok_reopen = row2 and row2["stato"] == "titolo_generato"
    print("AUTO-RIAPERTURA OK:", ok_reopen)

    # RIPRISTINO
    await db.polizze.update_one({"id": pid}, {"$set": {"regolazione_stato": orig_reg_stato}})
    if orig_tit_stato is not None:
        await db.titoli.update_one({"id": tit_id}, {"$set": {"stato": orig_tit_stato}})
    print("Ripristinato. RESULT:", "PASS" if (ok_close and ok_reopen) else "FAIL")
    client.close()


asyncio.run(main())
