import asyncio, os, httpx
from database import db

async def main():
    doc = await db.whatsapp_server_config.find_one({}, {"_id":0,"server_url":1,"api_key":1})
    if doc and doc.get("server_url"):
        url, key = doc["server_url"].rstrip("/"), doc["api_key"]
        src = "DB whatsapp_server_config"
    else:
        url, key = (os.environ.get("WHATSAPP_API_URL") or "").rstrip("/"), os.environ.get("WHATSAPP_API_KEY") or ""
        src = "env"
    print("Evolution source:", src, "| base:", url[:40], "...")
    inst = await db.whatsapp_instances.find_one({"instance_name":"agenzia-03425"}, {"_id":0})
    print("Istanza in DB:", bool(inst), "| webhook_url salvato:", (inst or {}).get("webhook_url"))
    token = (inst or {}).get("token")
    async with httpx.AsyncClient(timeout=10) as c:
        # stato connessione
        try:
            r = await c.get(f"{url}/instance/connectionState/agenzia-03425", headers={"apikey":key})
            print("connectionState:", r.status_code, r.text[:200])
        except Exception as e:
            print("connectionState ERR:", e)
        # webhook corrente
        try:
            r = await c.get(f"{url}/webhook/find/agenzia-03425", headers={"apikey": token or key})
            print("webhook/find:", r.status_code, r.text[:400])
        except Exception as e:
            print("webhook/find ERR:", e)
    # ultimi messaggi inbound salvati in questo DB (preview)
    cur = db.whatsapp_messages.find({"instance_name":"agenzia-03425"}).sort("timestamp",-1).limit(5)
    msgs = await cur.to_list(5)
    print("--- ultimi 5 messaggi in QUESTO db (preview) ---")
    for m in msgs:
        print(m.get("timestamp"), "| dir:", m.get("direction"), "| from:", m.get("from_number") or m.get("number"), "| text:", (m.get("text") or "")[:40])

asyncio.run(main())
