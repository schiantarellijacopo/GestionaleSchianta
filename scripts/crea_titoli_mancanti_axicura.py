"""Crea i titoli mancanti richiesti:
- 3 negativi (lasciati come sospesi negativi nella sezione anticipi/sospesi)
- 184643448 (nuovo, coperto 11/09/2026) con provvigione collaboratore BS = netto*4,5%.
Copia agenzia_tenant_id dalla polizza per rispettare lo scoping.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
NOW = datetime.now(timezone.utc).isoformat()


def _plus1y(iso):
    y, m, g = iso.split("-")
    return f"{int(y)+1}-{m}-{g}"


# (numero_polizza, effetto, copertura, lordo, tipo)
NEG = [
    ("180992240", "2024-12-27", "2024-12-27", -116.50, "appendice"),
    ("183629179", "2025-06-03", "2025-06-03", -30.00, "rinnovo"),
    ("184643403", "2026-09-03", "2026-09-03", -65.00, "appendice"),
]


async def _base_titolo(db, num):
    p = await db.polizze.find_one({"numero_polizza": num}, {"_id": 0})
    return p


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    for num, eff, cop, lordo, tipo in NEG:
        p = await _base_titolo(db, num)
        doc = {
            "id": str(uuid.uuid4()), "polizza_id": p["id"],
            "agenzia_tenant_id": p.get("agenzia_tenant_id"),
            "tipo": tipo, "effetto": eff, "scadenza": _plus1y(eff),
            "stato": "da_incassare", "titolo_coperto": True, "data_copertura": cop,
            "importo_lordo": lordo, "importo_netto": lordo, "imposte": 0.0,
            "provvigioni": 0.0, "provvigione_collaboratore": 0.0,
            "importo_da_pagare": lordo,
            "collaboratore_id": p.get("collaboratore_id"),
            "fonte": "manuale", "stato_carico": "validato",
            "note_carico": "Sospeso negativo (riconciliazione PDF)",
            "created_at": NOW, "updated_at": NOW,
        }
        await db.titoli.insert_one(doc)
        print(f"NEG {num}: creato titolo {lordo}")

    # 184643448
    p = await _base_titolo(db, "184643448")
    netto = 1222.66
    collab = round(netto * 4.5 / 100.0, 2)  # BS BROKER: 4,5% su netto
    collab_u = await db.users.find_one({"id": p.get("collaboratore_id")}, {"_id": 0, "name": 1})
    doc = {
        "id": str(uuid.uuid4()), "polizza_id": p["id"],
        "agenzia_tenant_id": p.get("agenzia_tenant_id"),
        "tipo": "rinnovo", "effetto": "2026-09-11", "scadenza": "2027-09-11",
        "stato": "da_incassare", "titolo_coperto": True, "data_copertura": "2026-09-11",
        "importo_lordo": 1400.00, "importo_netto": netto,
        "imposte": 162.83, "accessori": 14.51,
        "provvigioni": 130.29, "provvigione_collaboratore": collab,
        "importo_da_pagare": 1400.00,
        "collaboratore_id": p.get("collaboratore_id"),
        "provvigioni_operatori": [{
            "operatore_id": p.get("collaboratore_id"),
            "operatore_nome": (collab_u or {}).get("name") or "",
            "provvigione": collab,
        }],
        "fonte": "manuale", "stato_carico": "validato",
        "note_carico": "Creato manualmente (riconciliazione PDF)",
        "created_at": NOW, "updated_at": NOW,
    }
    await db.titoli.insert_one(doc)
    print(f"184643448: creato titolo lordo 1400 netto {netto} prov.agenzia 130.29 prov.collab {collab} ({(collab_u or {}).get('name')})")


if __name__ == "__main__":
    asyncio.run(main())
