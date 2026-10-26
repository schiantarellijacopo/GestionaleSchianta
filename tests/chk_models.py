import requests, json
BASE = [l.split("=",1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0]
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
tok = r.json().get("access_token") or r.json().get("token")
if tok: s.headers["Authorization"] = f"Bearer {tok}"
st = s.get(f"{BASE}/api/librerie/modelli/71a50687-f89d-4e8b-9894-68f646fc67b7/struttura-word").json()
print(json.dumps(st)[:600])
ms = s.get(f"{BASE}/api/librerie/modelli").json()
ms = ms if isinstance(ms, list) else ms.get("items", ms)
for m in ms:
    if str(m.get("tipo","")).startswith("pdf"):
        print(m["id"], m["tipo"], m["nome"], repr((m.get("corpo") or "")[:60]))
