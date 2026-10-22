# Cross-tenant isolation check for comunicazioni copertura (creates & removes a temp user)
import os, asyncio, uuid, bcrypt, requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
for l in open("/app/frontend/.env"):
    if l.startswith("REACT_APP_BACKEND_URL="):
        U = l.split("=", 1)[1].strip().rstrip("/")
API = f"{U}/api/comunicazioni-copertura"
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def main():
    tpl = await db.users.find_one({"email": "admin@assicura.it"}, {"_id": 0})
    uid = str(uuid.uuid4()); email = f"test-cc-{uid[:6]}@cctest.it"
    u = dict(tpl); u.update(id=uid, email=email, agenzia_tenant_id="tenant-clean-master",
                            password_hash=bcrypt.hashpw(b"TestCC123!", bcrypt.gensalt()).decode(), name="TEST CC")
    for k in ("failed_login_attempts", "locked_until"): u.pop(k, None)
    await db.users.insert_one(u)
    try:
        a = requests.Session()
        a.post(f"{U}/api/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
        gen = a.get(f"{API}/genera", params={"giorno": "2026-06-22"}).json()
        c = a.post(f"{API}/salva", json={"giorno": "2026-06-22", "gruppi": gen["gruppi"], "invia": False}).json()["comunicazioni"][0]
        raw = await db.comunicazioni_copertura.find_one({"id": c["id"]}, {"_id": 0, "agenzia_tenant_id": 1})
        print("stored tenant:", raw)
        o = requests.Session()
        r = o.post(f"{U}/api/auth/login", json={"email": email, "password": "TestCC123!"})
        print("other login:", r.status_code)
        print("other genera n_titoli:", o.get(f"{API}/genera", params={"giorno": "2026-10-05"}).json().get("n_titoli"))
        st = o.get(API).json()
        print("other storico sees it:", any(x["id"] == c["id"] for x in st), "len", len(st))
        print("other dettaglio:", o.get(f"{API}/{c['id']}").status_code)
        print("other pdf:", o.get(f"{API}/{c['id']}/pdf").status_code)
        print("other delete:", o.delete(f"{API}/{c['id']}").status_code)
        print("admin delete:", a.delete(f"{API}/{c['id']}").status_code)
    finally:
        await db.users.delete_one({"id": uid})

asyncio.run(main())
