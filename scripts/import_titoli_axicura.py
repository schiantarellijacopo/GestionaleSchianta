"""Import titoli incassati CSV nel tenant Axicura, mapping ESPLICITO, entità titolo.
Collega alle polizze per NumPolizza, imposta data_copertura, mezzo_pagamento,
stato incassato. Incassato senza tipo pagamento → pagamento in direzione.
"""
import asyncio, os, sys, uuid
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")

from database import db, set_current_user
from routes.import_massivo import _read_df, _count_rows, _gridfs, _run_commit_inner

EMAIL = os.environ.get("ADMIN_EMAIL", "jacopo@schiantarelli.it")
CSVPATH = os.environ.get("CSV", "/tmp/titoli.csv")
FNAME = os.environ.get("FNAME", "titoli_incassati.csv")

MAPPING = {
    "NumPolizza": "numero_polizza", "Ramo": "ramo", "Contraente": "contraente_nome",
    "Piva": "contraente_piva", "CodFiscale": "contraente_cf", "Compagnia": "compagnia_nome",
    "Agenzia": "mandato", "RataDel": "effetto", "Copertura": "data_copertura",
    "Netto": "importo_netto", "Imposte": "imposte", "Totale": "importo_lordo",
    "Provvigioni": "provvigioni", "TipoPag": "mezzo_pagamento", "DataPagam": "data_incasso",
    "PagTitolo": "importo_pagato",
    "Operatore 1": "operatore_nome", "Operatore 1 Provv": "operatore_provv", "Operatore 1 Rit": "operatore_rit",
    "Operatore 2": "operatore_2_nome", "Operatore 2 Provv": "operatore_2_provv", "Operatore 2 Rit": "operatore_2_rit",
    "Operatore 3": "operatore_3_nome", "Operatore 3 Provv": "operatore_3_provv", "Operatore 3 Rit": "operatore_3_rit",
    "Operatore 4": "operatore_4_nome", "Operatore 4 Provv": "operatore_4_provv", "Operatore 4 Rit": "operatore_4_rit",
}


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await raw.users.find_one({"email": EMAIL}, {"_id": 0})
    print(f"utente={EMAIL} tenant={user.get('agenzia_tenant_id')}", flush=True)
    set_current_user(user)

    with open(CSVPATH, "rb") as f:
        content = f.read()
    df = _read_df(content, FNAME)
    mapping = {h: MAPPING.get(str(h)) for h in df.columns}
    total = _count_rows(content, FNAME)
    print("righe:", total, "| entity: titolo", flush=True)

    gid = await _gridfs().upload_from_stream(f"axicura_{uuid.uuid4().hex}_{FNAME}", content)
    sid = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    await db.import_massivo_sessioni.insert_one({
        "id": sid, "created_at": now, "user_id": user.get("id"), "status": "in_corso",
        "files": [{"file_index": 0, "filename": FNAME, "gridfs_id": str(gid),
                   "entity": "titolo", "mapping": mapping, "total_rows": total}],
        "progress": {"fase": "avvio", "totale": total, "elaborate": 0,
                     "creati": 0, "aggiornati": 0, "saltati": 0, "errori": 0},
        "result": None,
    })
    plan = [{"file_index": 0, "entity": "titolo", "mapping": mapping}]
    await _run_commit_inner(sid, plan, user)

    sess = await db.import_massivo_sessioni.find_one({"id": sid}, {"_id": 0, "result": 1})
    r = sess.get("result") or {}
    print("RISULTATO:", r.get("creati"), "creati |", r.get("aggiornati"), "aggiornati |",
          r.get("saltati"), "saltati |", r.get("errori"), "errori", flush=True)
    print("auto-creati:", r.get("auto_creati_totali"), flush=True)
    for e in (r.get("errori_dettaglio") or [])[:6]:
        print("  err:", e, flush=True)


asyncio.run(main())
