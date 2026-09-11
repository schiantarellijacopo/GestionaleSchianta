"""Import portafoglio polizze CSV nel tenant Axicura (jacopo@schiantarelli.it),
riusando la pipeline import_massivo (_run_commit_inner): collega/crea contraenti
per CF/P.IVA, compagnie, operatori. Policy fill-missing sui contraenti esistenti.

Uso: ADMIN_EMAIL=jacopo@schiantarelli.it CSV=/tmp/portafoglio.csv python3 import_polizze_axicura.py
"""
import asyncio, os, sys, uuid
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")

from database import db, set_current_user
from routes.import_massivo import (
    _read_df, _count_rows, _detect_mapping_heuristic, _gridfs, _run_commit_inner,
)

EMAIL = os.environ.get("ADMIN_EMAIL", "jacopo@schiantarelli.it")
CSVPATH = os.environ.get("CSV", "/tmp/portafoglio.csv")
FNAME = os.environ.get("FNAME", "portafoglio_attivo.csv")


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await raw.users.find_one({"email": EMAIL}, {"_id": 0})
    if not user:
        print("Utente non trovato:", EMAIL); return
    print(f"utente={EMAIL} tenant={user.get('agenzia_tenant_id')}", flush=True)
    set_current_user(user)

    with open(CSVPATH, "rb") as f:
        content = f.read()
    df = _read_df(content, FNAME)
    headers = [str(h) for h in df.columns]
    mapping = _detect_mapping_heuristic("polizza", headers)
    total = _count_rows(content, FNAME)
    print("righe:", total, "| entity: polizza", flush=True)

    gid = await _gridfs().upload_from_stream(f"axicura_{uuid.uuid4().hex}_{FNAME}", content)
    sid = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    await db.import_massivo_sessioni.insert_one({
        "id": sid, "created_at": now, "user_id": user.get("id"), "status": "in_corso",
        "files": [{"file_index": 0, "filename": FNAME, "gridfs_id": str(gid),
                   "entity": "polizza", "mapping": mapping, "total_rows": total}],
        "progress": {"fase": "avvio", "totale": total, "elaborate": 0,
                     "creati": 0, "aggiornati": 0, "saltati": 0, "errori": 0},
        "result": None,
    })
    plan = [{"file_index": 0, "entity": "polizza", "mapping": mapping}]
    await _run_commit_inner(sid, plan, user)

    sess = await db.import_massivo_sessioni.find_one({"id": sid}, {"_id": 0, "result": 1, "progress": 1})
    print("RISULTATO:", sess.get("result", {}).get("creati"), "creati |",
          sess.get("result", {}).get("aggiornati"), "aggiornati |",
          sess.get("result", {}).get("saltati"), "saltati |",
          sess.get("result", {}).get("errori"), "errori", flush=True)
    ac = (sess.get("result") or {}).get("auto_creati_totali") or {}
    print("auto-creati:", ac, flush=True)
    for e in (sess.get("result") or {}).get("errori_dettaglio", [])[:8]:
        print("  err:", e, flush=True)


asyncio.run(main())
