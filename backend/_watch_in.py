import asyncio
from database import db

async def main():
    n = await db.whatsapp_messages.count_documents({"instance_name":"agenzia-03425"})
    print("TOTALE messaggi agenzia-03425 nel preview DB:", n)
    cur = db.whatsapp_messages.find({"instance_name":"agenzia-03425"}).sort([("_id",-1)]).limit(3)
    for m in await cur.to_list(3):
        print(" -", str(m.get("_id")), "| dir:", m.get("direction"), "| text:", (m.get("text") or m.get("body") or "")[:50])

asyncio.run(main())
