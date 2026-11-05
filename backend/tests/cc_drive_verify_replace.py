# Verifies on real Google Drive that replace/delete removes the old file (helper, not pytest)
import asyncio, os, sys, requests, httpx
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
API = "https://whatsapp-crm-146.preview.emergentagent.com/api"
AID = "42a86341-50d5-4c65-b2aa-bc28c352dfb8"
TENANT = "tenant-principale-schiantarelli"


async def drive_status(fid):
    from database import db
    from routes.cloud_storage import _fresh_access_token
    conn = await db.cloud_connections.find_one({"tenant_id": TENANT, "provider": "google_drive"})
    tok = await _fresh_access_token("google_drive", conn)
    async with httpx.AsyncClient() as x:
        r = await x.get(f"https://www.googleapis.com/drive/v3/files/{fid}?fields=id,name,trashed",
                        headers={"Authorization": f"Bearer {tok}"})
    return r.status_code, r.text[:150]


LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


def main():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers["Authorization"] = f"Bearer {tok}"
    a = s.post(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd", files={"file": ("TEST_a.pdf", b"%PDF-1.4 A", "application/pdf")}).json()["mandato_sdd"]
    f1 = a["cloud_sync"]["file_id"]
    print("first", f1, LOOP.run_until_complete(drive_status(f1)))
    b = s.post(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd", files={"file": ("TEST_b.pdf", b"%PDF-1.4 B", "application/pdf")}).json()["mandato_sdd"]
    f2 = b["cloud_sync"]["file_id"]
    print("after replace old:", LOOP.run_until_complete(drive_status(f1)))
    print("after replace new:", LOOP.run_until_complete(drive_status(f2)))
    print("delete:", s.delete(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd").json())
    print("after delete new:", LOOP.run_until_complete(drive_status(f2)))


main()
