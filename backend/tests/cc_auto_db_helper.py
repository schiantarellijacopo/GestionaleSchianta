# Helper: DB inspection for copertura auto-invio tests (iter116). Usage: python cc_auto_db_helper.py <cmd>
import os, sys, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PRINC = "tenant-principale-schiantarelli"
SANDBOX = "c942fe2a-8919-48ea-9dc6-a2bf0e51b6ed"


async def main():
    cmd = sys.argv[1]
    if cmd == "info":
        coms = await db.comunicazioni_copertura.find({}, {"_id": 0, "id": 1, "numero": 1, "giorno": 1, "stato": 1, "agenzia_tenant_id": 1, "email_errore": 1}).to_list(100)
        for c in coms: print("COM", c)
        for cfg in await db.azienda_config.find({}, {"_id": 0, "id": 1, "agenzia_tenant_id": 1, "copertura_auto_attivo": 1, "copertura_auto_hour": 1, "copertura_auto_minute": 1, "smtp_host": 1, "alert_scheduler_hour": 1}).to_list(50):
            print("CFG", cfg)
        print("STATE", await db.copertura_auto_state.find({}, {"_id": 0}).to_list(50))
        pipeline = [{"$match": {"copertura_comunicata": {"$ne": True}, "stato": "incassato", "data_incasso": {"$type": "string"}}},
                    {"$group": {"_id": {"t": "$agenzia_tenant_id", "d": "$data_incasso"}, "n": {"$sum": 1}}},
                    {"$sort": {"_id.d": -1}}, {"$limit": 15}]
        async for r in db.titoli.aggregate(pipeline): print("DAY", r)
        print("COUNTERS", await db.counters.find({"_key": "comunicazioni_copertura"}, {"_id": 0}).to_list(10))
    elif cmd == "users":
        for u in await db.users.find({"role": {"$in": ["admin", "collaboratore", "dipendente"]}}, {"_id": 0, "email": 1, "agenzia_tenant_id": 1, "role": 1}).to_list(200):
            print(u)
    elif cmd == "delcom":
        r = await db.comunicazioni_copertura.delete_many({"id": {"$in": sys.argv[2:]}})
        print("deleted", r.deleted_count)

asyncio.run(main())
