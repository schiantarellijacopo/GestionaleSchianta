"""Importa dal rec40 OMNIA i titoli con mezzo_pagamento_cmp='PS' NON ancora presenti,
impostando il tipo pagamento = 'Pagamento in direzione'. Valori esatti dal rec40.
Dedup vs titoli esistenti per (polizza, effetto, lordo).
"""
import asyncio, os, sys, csv
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from database import db, set_current_user
from db_models import Titolo
import ania_importer as A

EMAIL = "jacopo@schiantarelli.it"
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
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1, "collaboratore_id": 1}):
        if p.get("numero_polizza"):
            pol_by.setdefault(_norm(p["numero_polizza"]), p)

    existing = set()
    async for t in db.titoli.find({}, {"_id": 0, "polizza_id": 1, "effetto": 1, "importo_lordo": 1}):
        existing.add((t.get("polizza_id"), t.get("effetto"), round(float(t.get("importo_lordo") or 0), 2)))
    print("titoli esistenti indicizzati:", len(existing), flush=True)

    created = skip_nopol = skip_dup = 0
    buf = []
    for row in csv.DictReader(open(REC40, encoding="latin-1"), delimiter=";"):
        if (row.get("mezzo_pag_share") or "").strip() != "SEC" and (row.get("mezzo_pagamento_cmp") or "").strip() != "RD":
            continue
        pol = pol_by.get(_norm(row.get("numero_polizza_cmp")))
        if not pol:
            skip_nopol += 1
            continue
        eff = A._parse_date(row.get("effetto_titolo"))
        lordo = _f(row.get("lordo_totale"))
        key = (pol["id"], eff, lordo)
        if key in existing:
            skip_dup += 1
            continue
        existing.add(key)
        dt_pag = A._parse_date(row.get("dt_pag_cliente"))
        stato = "incassato" if dt_pag else "da_incassare"
        doc = Titolo(
            polizza_id=pol["id"], effetto=eff or NOW[:10], scadenza=eff or NOW[:10],
            stato=stato, importo_lordo=lordo, importo_netto=_f(row.get("netto_totale")),
            imposte=_f(row.get("tasse_totale")), accessori=_f(row.get("accessori_totale")),
            provvigioni=_f(row.get("provvigioni_totale")),
            data_incasso=dt_pag, data_copertura=dt_pag if stato == "incassato" else None,
            mezzo_pagamento="Pagamento in direzione", pagamento_in_direzione=True,
            collaboratore_id=pol.get("collaboratore_id") or user.get("id"),
            caricato_da_import=True, note_carico="OMNIA SDD - pagamento in direzione",
        ).model_dump()
        buf.append(doc)
        created += 1
        if len(buf) >= 1000 and not DRY:
            await db.titoli.insert_many(buf); buf.clear()
    if buf and not DRY:
        await db.titoli.insert_many(buf)
    print(f"dry={DRY} | SDD creati={created} | senza_polizza={skip_nopol} | dup_saltati={skip_dup}", flush=True)


asyncio.run(main())
