import requests, sys
BASE = [l.split("=",1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0]
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
tok = r.json().get("access_token") or r.json().get("token")
if tok: s.headers["Authorization"] = f"Bearer {tok}"
if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
    for mid in sys.argv[2:]:
        print(mid, s.delete(f"{BASE}/api/librerie/modelli/{mid}").status_code)
elif len(sys.argv) > 1 and sys.argv[1] == "get":
    print(repr(s.get(f"{BASE}/api/librerie/modelli/{sys.argv[2]}").json().get("corpo")))
else:
    r = s.post(f"{BASE}/api/librerie/modelli", json={"tipo": "pdf_altro", "nome": "TEST_PDF_corpo", "corpo": "TEST_ORIGINAL body text"})
    print(r.status_code, r.text[:200])
