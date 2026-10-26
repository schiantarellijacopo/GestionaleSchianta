# Creates a TEST_ pdf_altro model with an original PDF attached (for overlay editor tests)
import requests, sys, fitz
BASE = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0]
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"})
tok = r.json().get("access_token") or r.json().get("token")
if tok:
    s.headers["Authorization"] = f"Bearer {tok}"
if len(sys.argv) > 1 and sys.argv[1] == "overlay":
    r = s.get(f"{BASE}/api/librerie/modelli/{sys.argv[2]}/pdf-pagine")
    print(r.status_code, r.json().get("overlay"))
    sys.exit()
doc = fitz.open(); p = doc.new_page(); p.insert_text((72, 100), "TEST_ PDF overlay document", fontsize=16)
pdf = doc.tobytes()
r = s.post(f"{BASE}/api/librerie/modelli", json={"tipo": "pdf_altro", "nome": "TEST_PDF_overlay_drag", "corpo": "TEST body"})
mid = r.json()["id"]
r2 = s.post(f"{BASE}/api/librerie/modelli/{mid}/pdf-origine", files={"file": ("t.pdf", pdf, "application/pdf")})
print(mid, r2.status_code, r2.text[:150])
