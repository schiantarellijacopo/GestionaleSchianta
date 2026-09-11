"""Corregge i titoli ARRETRATI (file stampa) usando i valori ESATTI del rec40 OMNIA
per lo stesso titolo (stessa polizza + stessa data = effetto_titolo).
Aggiorna netto/imposte/accessori/lordo/provvigioni con i dati reali OMNIA.
"""
import asyncio, os, sys, csv
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from database import db, set_current_user
import ania_importer as A
from routes.import_anagrafiche import _parse_date_flexible as _pdate

EMAIL = "jacopo@schiantarelli.it"
STAMPA = os.environ.get("CSV", "/tmp/stampa2.csv")
REC40 = "/tmp/omnia_zip/rec40oweb.csv"
DRY = os.environ.get("DRY", "0") == "1"
NOW = datetime.now(timezone.utc).isoformat()
_norm = lambda n: (n or "").strip().lstrip("0")
_f = lambda v: round(A._parse_float(v) or 0.0, 2)


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await raw.users.find_one({"email": EMAIL}, {"_id": 0})
    set_current_user(user)

    pol_by = {}
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1}):
        if p.get("numero_polizza"):
            pol_by.setdefault(_norm(p["numero_polizza"]), p["id"])

    # target: (norm_num, data_iso)
    arr = list(csv.DictReader(open(STAMPA, encoding="latin-1"), delimiter=";"))
    targets = {}
    for r in arr:
        num = _norm(r.get("Num.Contratto"))
        d = _pdate(r.get("Rata del"))
        if num and d:
            targets[(num, d)] = _f(r.get("Rata"))
    target_nums = {k[0] for k in targets}
    print("arretrati con chiave valida:", len(targets), flush=True)

    # scan rec40 → valori esatti per (norm_num, effetto_titolo)
    idx = {}
    rd = csv.DictReader(open(REC40, encoding="latin-1"), delimiter=";")
    for row in rd:
        num = _norm(row.get("numero_polizza_cmp"))
        if num not in target_nums:
            continue
        d = A._parse_date(row.get("effetto_titolo"))
        if not d or (num, d) not in targets:
            continue
        netto = _f(row.get("netto_totale"))
        vals = {
            "importo_netto": netto,
            "imposte": _f(row.get("tasse_totale")),
            "accessori": _f(row.get("accessori_totale")),
            "importo_lordo": _f(row.get("lordo_totale")),
            "provvigioni": _f(row.get("provvigioni_totale")),
        }
        # se doppioni, preferisci la riga con netto valorizzato
        if (num, d) not in idx or (netto > 0 and idx[(num, d)]["importo_netto"] == 0):
            idx[(num, d)] = vals
    print("match trovati nel rec40:", len(idx), flush=True)

    upd = notfound = 0
    for (num, d), lordo in targets.items():
        vals = idx.get((num, d))
        pid = pol_by.get(num)
        if not vals or not pid:
            notfound += 1
            continue
        set_v = dict(vals); set_v["updated_at"] = NOW
        if not DRY:
            r = await db.titoli.update_many(
                {"polizza_id": pid, "scadenza": d, "stato": "da_incassare", "caricato_da_import": True},
                {"$set": set_v})
            upd += r.modified_count
    print(f"dry={DRY} | titoli aggiornati con valori OMNIA: {upd} | senza match rec40: {notfound}", flush=True)


asyncio.run(main())
