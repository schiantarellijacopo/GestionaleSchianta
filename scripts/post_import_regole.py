"""Post-import leggero: rec52 liquidazioni + regole DB (no fase titoli).

La fase titoli non serve: i titoli erano già stati importati; le nuove regole
sono applicabili direttamente sul database.
"""
import asyncio, os, sys, io, zipfile, urllib.request
sys.path.insert(0, "/app/backend")
from datetime import datetime, timezone
from database import db, raw_db, _current_user_ctx
import ania_importer as ai

TENANT = "31b4950e-85c2-4232-a31f-ba226b7923fe"
URL = ("https://customer-assets-wrfwihn1.emergentagent.net/job_24ad771c-c3b3-4e05-9e82-ecb09db00768/"
       "artifacts/g9oqo5qz_A_OW8_23774_20260902222300_83_P_S.zip")


async def main():
    u = await raw_db.users.find_one({"agenzia_tenant_id": TENANT, "role": "admin"})
    _current_user_ctx.set(u)
    print("utente:", u.get("email"), flush=True)

    # 1) solo il rec52 dallo ZIP (memoria minima)
    raw = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "M"})).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    files_data = {}
    for n in z.namelist():
        if ai._detect_record_type(n) == "rec52":
            files_data[n] = z.read(n).decode("utf-8-sig", errors="replace")
            print("rec52:", n, len(files_data[n]), "bytes", flush=True)
    del raw, z

    counts = {}
    n_liq = await ai._processa_liquidazioni(db, files_data, counts)
    print("sinistri con liquidazione aggiornata:", n_liq, counts, flush=True)
    del files_data

    # 2) regole solo-DB
    print("polizze sostituite:", await ai._marca_polizze_sostituite(db), flush=True)
    print("scadenze allineate:", await ai._aggiorna_scadenza_da_titoli(db), flush=True)

    r1 = await db.titoli.update_many(
        {"importo_lordo": {"$lte": 0}, "stato": {"$ne": "incassato"}},
        {"$set": {"stato": "incassato"}})
    print("titoli premio 0 → incassati:", r1.modified_count, flush=True)

    r2 = await db.titoli.update_many(
        {"stato": "incassato", "$or": [{"mezzo_pagamento": None}, {"mezzo_pagamento": ""}]},
        {"$set": {"mezzo_pagamento": "Pagamento in direzione",
                  "pagamento_in_direzione": True,
                  "updated_at": datetime.now(timezone.utc).isoformat()}})
    print("titoli incassati senza metodo → in direzione:", r2.modified_count, flush=True)
    print("FINE", flush=True)

asyncio.run(main())
