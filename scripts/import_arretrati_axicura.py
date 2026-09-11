"""Import titoli ARRETRATI (file 'stampa') nel tenant Axicura come da_incassare.
Il file ha solo l'importo Rata (lordo): ricostruisce netto/imposte/provvigioni
dalle proporzioni di un titolo esistente della stessa polizza (imposte include SSN);
fallback sui premi di polizza.
"""
import asyncio, os, sys, csv
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from database import db, set_current_user
from db_models import Titolo
import ania_importer as A
from routes.import_anagrafiche import _parse_date_flexible as _pdate

EMAIL = os.environ.get("ADMIN_EMAIL", "jacopo@schiantarelli.it")
CSVPATH = os.environ.get("CSV", "/tmp/stampa.csv")
DRY = os.environ.get("DRY", "0") == "1"
NOW = datetime.now(timezone.utc).isoformat()


def _f(v):
    return A._parse_float(v) or 0.0


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await raw.users.find_one({"email": EMAIL}, {"_id": 0})
    set_current_user(user)
    T = user.get("agenzia_tenant_id")
    norm = lambda n: (n or "").strip().lstrip("0")

    pol_by, pol_prem = {}, {}
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1,
                                        "premio_lordo": 1, "premio_netto": 1,
                                        "collaboratore_id": 1}):
        if p.get("numero_polizza"):
            pol_by.setdefault(norm(p["numero_polizza"]), p)

    rows = list(csv.DictReader(open(CSVPATH, encoding="latin-1"), delimiter=";"))
    created = skip_nopol = skip_dup = 0
    buf = []
    for r in rows:
        num = norm(r.get("Num.Contratto"))
        pol = pol_by.get(num)
        if not pol:
            skip_nopol += 1
            continue
        lordo = round(_f(r.get("Rata")), 2)
        if lordo <= 0:
            skip_nopol += 1
            continue
        scad = _pdate(r.get("Rata del")) or NOW[:10]
        # dedup: titolo aperto già presente per pol+scadenza+lordo
        dup = await db.titoli.find_one({"polizza_id": pol["id"], "scadenza": scad,
                                        "importo_lordo": lordo})
        if dup:
            skip_dup += 1
            continue
        # proporzioni da un titolo di riferimento (preferisci incassato, lordo>0)
        ref = await db.titoli.find_one(
            {"polizza_id": pol["id"], "importo_lordo": {"$gt": 0}},
            {"_id": 0, "importo_lordo": 1, "importo_netto": 1, "provvigioni": 1},
            sort=[("stato", 1)])
        if ref and ref.get("importo_lordo"):
            rl = ref["importo_lordo"]
            netto = round(lordo * (ref.get("importo_netto", 0.0) / rl), 2)
            provv = round(lordo * (ref.get("provvigioni", 0.0) / rl), 2)
        elif pol.get("premio_lordo"):
            netto = round(lordo * (pol.get("premio_netto", 0.0) / pol["premio_lordo"]), 2)
            provv = 0.0
        else:
            netto, provv = lordo, 0.0
        imposte = round(lordo - netto, 2)
        doc = Titolo(
            polizza_id=pol["id"], effetto=scad, scadenza=scad, stato="da_incassare",
            importo_lordo=lordo, importo_netto=netto, imposte=imposte, provvigioni=provv,
            collaboratore_id=pol.get("collaboratore_id") or user.get("id"),
            caricato_da_import=True, note="Arretrato (stampa)",
        ).model_dump()
        buf.append(doc)
        created += 1
        if len(buf) >= 500 and not DRY:
            await db.titoli.insert_many(buf); buf.clear()
    if buf and not DRY:
        await db.titoli.insert_many(buf)
    print(f"dry={DRY} | creati(da_incassare)={created} | senza_polizza={skip_nopol} | dup_saltati={skip_dup}", flush=True)


asyncio.run(main())
