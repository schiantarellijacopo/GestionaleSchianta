# Helper: DB checks for comunicazioni copertura (exclusion + tenants). Usage: python cc_db_helper.py <cmd> [args]
import os, sys, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def main():
    cmd = sys.argv[1]
    if cmd == "info":
        ts = await db.titoli.find({"$or": [{"data_incasso": "2026-10-05"}, {"data_copertura": "2026-10-05"}]},
                                  {"_id": 0, "id": 1, "stato": 1, "titolo_coperto": 1, "copertura_comunicata": 1, "agenzia_tenant_id": 1, "data_incasso": 1}).to_list(50)
        for t in ts: print(t)
        print("tenants:", await db.users.distinct("agenzia_tenant_id"))
        for u in await db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "agenzia_tenant_id": 1}).to_list(50): print(u)
        print("com tenants:", await db.comunicazioni_copertura.distinct("agenzia_tenant_id"))
    elif cmd == "set":
        tid, field, val = sys.argv[2], sys.argv[3], sys.argv[4]
        v = True if val == "true" else (None if val == "none" else val)
        r = await db.titoli.update_one({"id": tid}, {"$set": {field: v}})
        print("modified", r.modified_count)
    elif cmd == "unset":
        await db.titoli.update_one({"id": sys.argv[2]}, {"$unset": {sys.argv[3]: ""}})
        print("unset ok")

asyncio.run(main())
