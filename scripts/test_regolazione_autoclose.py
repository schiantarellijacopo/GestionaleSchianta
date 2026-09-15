"""Test: auto-chiusura + filtro Tutte/Chiuse + riproposizione annuale."""
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

    pol = await db.polizze.find_one({"numero_polizza": "732864759", "regolazione_premio": True})
    assert pol, "polizza test non trovata"
    pid = pol["id"]
    tit_id = pol.get("regolazione_titolo_id")
    print("polizza", pid, "titolo", tit_id, "scadenza", pol.get("scadenza"))

    from routes.regolazione_premio import list_regolazioni
    U = {"role": "admin", "id": "x"}

    # --- SCENARIO 1: titolo_generato + titolo incassato -> chiusa + sparisce da "Tutte"
    await db.polizze.update_one({"id": pid}, {"$set": {"regolazione_stato": "titolo_generato", "scadenza": "2026-12-31"}, "$unset": {"regolazione_chiusa_scadenza_rif": "", "regolazione_chiusa_il": ""}})
    await db.titoli.update_one({"id": tit_id}, {"$set": {"stato": "incassato"}})

    tutte = await list_regolazioni(user=U)
    in_tutte = any(r["polizza_id"] == pid for r in tutte)
    chiuse = await list_regolazioni(stato="chiusa", user=U)
    row_chiusa = next((r for r in chiuse if r["polizza_id"] == pid), None)
    db_pol = await db.polizze.find_one({"id": pid}, {"_id": 0, "regolazione_stato": 1, "regolazione_chiusa_scadenza_rif": 1})
    print("1) in Tutte?", in_tutte, "| in Chiuse?", bool(row_chiusa), "| stato db:", db_pol.get("regolazione_stato"), "| rif:", db_pol.get("regolazione_chiusa_scadenza_rif"))
    ok1 = (not in_tutte) and row_chiusa and db_pol.get("regolazione_stato") == "chiusa" and db_pol.get("regolazione_chiusa_scadenza_rif") == "2026-12-31"

    # --- SCENARIO 2: rif nel passato (>1 anno fa) -> riproposta a da_richiedere
    await db.polizze.update_one({"id": pid}, {"$set": {"regolazione_stato": "chiusa", "regolazione_chiusa_scadenza_rif": "2020-12-31", "regolazione_dovuto": 999}})
    tutte2 = await list_regolazioni(user=U)
    row2 = next((r for r in tutte2 if r["polizza_id"] == pid), None)
    db_pol2 = await db.polizze.find_one({"id": pid}, {"_id": 0})
    print("2) riproposta stato:", row2["stato"] if row2 else None, "| titolo_id azzerato:", db_pol2.get("regolazione_titolo_id"), "| dovuto:", db_pol2.get("regolazione_dovuto"))
    ok2 = row2 and row2["stato"] == "da_richiedere" and not db_pol2.get("regolazione_titolo_id")

    # --- SCENARIO 3: chiusa ma rif NON ancora superato -> resta chiusa
    from datetime import date
    anno_corrente = f"{date.today().year}-12-31"
    await db.polizze.update_one({"id": pid}, {"$set": {"regolazione_stato": "chiusa", "regolazione_chiusa_scadenza_rif": anno_corrente, "regolazione_titolo_id": tit_id}})
    await db.titoli.update_one({"id": tit_id}, {"$set": {"stato": "incassato"}})
    tutte3 = await list_regolazioni(user=U)
    in_tutte3 = any(r["polizza_id"] == pid for r in tutte3)
    db_pol3 = await db.polizze.find_one({"id": pid}, {"_id": 0, "regolazione_stato": 1})
    print("3) rif futuro -> in Tutte?", in_tutte3, "| stato:", db_pol3.get("regolazione_stato"))
    ok3 = (not in_tutte3) and db_pol3.get("regolazione_stato") == "chiusa"

    # RIPRISTINO
    await db.polizze.update_one({"id": pid}, {"$set": {"regolazione_stato": "dati_ricevuti", "scadenza": pol.get("scadenza"), "regolazione_titolo_id": tit_id, "regolazione_dovuto": 0}, "$unset": {"regolazione_chiusa_scadenza_rif": "", "regolazione_chiusa_il": ""}})
    await db.titoli.update_one({"id": tit_id}, {"$set": {"stato": "da_incassare"}})
    await db.regolazione_storico.delete_many({"polizza_id": pid, "evento": "riproposta_nuovo_anno"})

    print("RESULT:", "PASS" if (ok1 and ok2 and ok3) else f"FAIL ok1={ok1} ok2={ok2} ok3={ok3}")
    client.close()


asyncio.run(main())
