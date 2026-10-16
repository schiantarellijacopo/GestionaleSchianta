import asyncio, os, httpx
from database import db

PROD = "https://gestionaleschianta-production.up.railway.app"
WH = f"{PROD}/api/whatsapp-evo/webhook/agenzia-03425"
EVENTS = ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "MESSAGES_UPDATE"]

async def main():
    doc = await db.whatsapp_server_config.find_one({}, {"_id":0,"server_url":1,"api_key":1})
    url, key = doc["server_url"].rstrip("/"), doc["api_key"]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{url}/webhook/set/agenzia-03425",
            headers={"apikey": key, "Content-Type":"application/json"},
            json={"webhook":{"enabled":True,"url":WH,"byEvents":False,"base64":False,"events":EVENTS}})
        print("set:", r.status_code, r.text[:300])
        r2 = await c.get(f"{url}/webhook/find/agenzia-03425", headers={"apikey": key})
        print("verify:", r2.status_code, r2.text[:300])

asyncio.run(main())
