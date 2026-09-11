"""Import titoli SOSPESI/ANTICIPI (file 'sospesi') nel tenant Axicura.
stato=sospeso, titolo_coperto=True, data_copertura=data del file (Rata del),
effetto=scadenza=data del file. Ricostruisce netto/imposte/provvigioni dalle
proporzioni di un titolo esistente della polizza. Se un titolo compatibile
esiste già sulla polizza, lo AGGIORNA (date+coperto+sospeso) invece di duplicarlo.
"""
import asyncio, os, sys, csv
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from database import db, set_current_user
from db_models import Titolo
import ania_importer as A
from routes.import_anagrafiche import _parse_date_flexible as _pdate

EMAIL = os.environ.get("ADMIN_EMAIL", "jacopo@schiantarelli.it")
CSVPATH = os.environ.get("CSV", "/tmp/sospesi.csv")
DRY = os.environ.get("DRY", "0") == "1"
NOW = datetime.now(timezone.utc).isoformat()


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await raw.users.find_one({"email": EMAIL}, {"_id": 0})
    set_current_user(user)
    norm = lambda n: (n or "").strip().lstrip("0")

    pol_by = {}
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1,
                                        "premio_lordo": 1, "premio_netto": 1, "collaboratore_id": 1}):
        if p.get("numero_polizza"):
            pol_by.setdefault(norm(p["numero_polizza"]), p)

    rows = list(csv.DictReader(open(CSVPATH, encoding="latin-1"), delimiter=";"))
    created = updated = skip = 0
    for r in rows:
        pol = pol_by.get(norm(r.get("Num.Contratto")))
        if not pol:
            skip += 1
            continue
        lordo = round(A._parse_float(r.get("Rata")) or 0.0, 2)
        scad = _pdate(r.get("Rata del"))
        if lordo <= 0 or not scad:
            skip += 1
            continue
        ref = await db.titoli.find_one({"polizza_id": pol["id"], "importo_lordo": {"$gt": 0}},
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
        common = {"effetto": scad, "scadenza": scad, "stato": "da_incassare",
                  "titolo_coperto": True, "data_copertura": scad,
                  "importo_lordo": lordo, "importo_netto": netto, "imposte": imposte,
                  "provvigioni": provv, "updated_at": NOW, "note_carico": "Sospeso/anticipo (import)"}
        # esiste già un titolo compatibile sulla polizza? (stesso lordo o stessa scadenza)
        exist = await db.titoli.find_one(
            {"polizza_id": pol["id"], "stato": {"$in": ["da_incassare", "insoluto"]},
             "$or": [{"importo_lordo": lordo}, {"scadenza": scad}]},
            {"_id": 0, "id": 1})
        if exist:
            if not DRY:
                await db.titoli.update_one({"id": exist["id"]}, {"$set": common})
            updated += 1
        else:
            doc = Titolo(polizza_id=pol["id"],
                         collaboratore_id=pol.get("collaboratore_id") or user.get("id"),
                         caricato_da_import=True, **common).model_dump()
            if not DRY:
                await db.titoli.insert_one(doc)
            created += 1
    print(f"dry={DRY} | creati={created} | aggiornati(coperti)={updated} | saltati={skip}", flush=True)


asyncio.run(main())
