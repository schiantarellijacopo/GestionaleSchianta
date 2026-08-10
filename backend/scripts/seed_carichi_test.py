"""Seed titoli test per il modulo "Carichi Mensili / Quietanzamento".

Genera due gruppi di titoli su un set di polizze reali:

1. Titoli STORICI (anno scorso, stesso mese) → alimentano ``premio_precedente``
   confrontato dallo scadenzario del carico mensile.
2. Titoli in SCADENZA questo mese (anno corrente) → riga da vagliare in
   Carichi Mensili con premio variato (o invariato) rispetto al 2025.

Uso:
    python -m backend.scripts.seed_carichi_test  --n 15
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

# Assicura che la cartella backend sia nel PYTHONPATH quando eseguito standalone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


PREFIX = "TEST_CARICHI"


def _last_day_of_month(y: int, m: int) -> int:
    if m == 12:
        return 31
    from calendar import monthrange
    return monthrange(y, m)[1]


async def seed(n_polizze: int = 15) -> dict:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    today = date.today()
    year_now = today.year
    year_prev = year_now - 1
    month = today.month
    last_day_now = _last_day_of_month(year_now, month)
    last_day_prev = _last_day_of_month(year_prev, month)

    # Scegli n polizze attive con contraente valido
    pols = await db.polizze.find(
        {"stato": {"$in": ["attiva", "sospesa"]},
         "contraente_id": {"$ne": None},
         "premio_lordo": {"$gt": 0}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1,
         "compagnia_id": 1, "premio_lordo": 1, "premio_netto": 1,
         "imposte": 1, "provvigioni": 1, "collaboratore_id": 1, "ramo": 1,
         "frazionamento": 1, "tenant_id": 1},
    ).limit(n_polizze).to_list(n_polizze)

    if not pols:
        return {"ok": False, "error": "Nessuna polizza attiva trovata"}

    creati_prev = creati_now = 0
    titoli_ids: list[str] = []

    for i, p in enumerate(pols):
        # Data scadenza distribuita nel mese
        giorno = min(1 + (i % 27), last_day_prev)
        scad_prev = f"{year_prev}-{month:02d}-{giorno:02d}"
        scad_now = f"{year_now}-{month:02d}-{min(giorno, last_day_now):02d}"

        premio_prev = round(float(p.get("premio_lordo") or 500) *
                             random.uniform(0.9, 1.05), 2)
        # Simuliamo variazioni: 40% aumento, 30% invariato, 20% ribasso, 10% mancante
        pick = random.random()
        if pick < 0.4:
            premio_now = round(premio_prev * random.uniform(1.05, 1.25), 2)
            variazione = "aumento"
        elif pick < 0.7:
            premio_now = premio_prev
            variazione = "invariato"
        elif pick < 0.9:
            premio_now = round(premio_prev * random.uniform(0.70, 0.95), 2)
            variazione = "ribasso"
        else:
            premio_now = None  # niente titolo anno corrente → "mancante"
            variazione = "mancante"

        # Netto/imposte proporzionali
        def _breakdown(lordo: float) -> dict:
            netto = round(lordo * 0.78, 2)
            imp = round(lordo - netto, 2)
            provv = round(netto * 0.12, 2)
            return {"lordo": lordo, "netto": netto, "imp": imp, "provv": provv}

        # === Titolo STORICO (anno precedente) ===
        b = _breakdown(premio_prev)
        tid_prev = str(uuid.uuid4())
        titolo_prev = {
            "id": tid_prev,
            "polizza_id": p["id"],
            "numero_titolo": f"{PREFIX}-{year_prev}-{i+1:03d}",
            "tipo": "rinnovo",
            "effetto": scad_prev,
            "scadenza": scad_prev,
            "stato": "incassato",
            "importo_lordo": b["lordo"],
            "importo_netto": b["netto"],
            "imposte": b["imp"],
            "provvigioni": b["provv"],
            "accessori": 0.0,
            "data_incasso": scad_prev,
            "importo_pagato": b["lordo"],
            "sconto_applicato": 0.0,
            "titolo_coperto": True,
            "data_copertura": scad_prev,
            "mezzo_pagamento": random.choice(["contanti", "bonifico", "assegno", "pos"]),
            "collaboratore_id": p.get("collaboratore_id"),
            "pagamento_in_direzione": False,
            "fonte": "manuale",
            "stato_carico": "validato",
            "caricato_da_import": False,
            "note_carico": f"{PREFIX} storico test",
            "premio_precedente": None,
            "tenant_id": p.get("tenant_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.titoli.insert_one(titolo_prev)
        creati_prev += 1
        titoli_ids.append(tid_prev)

        # === Titolo CORRENTE (anno in corso) — se non "mancante" ===
        if premio_now is not None:
            b = _breakdown(premio_now)
            tid_now = str(uuid.uuid4())
            # Stato di carico: casuale in_attesa / validato per testare filtri
            stato_carico = random.choice(["in_attesa", "in_attesa", "validato"])
            titolo_now = {
                "id": tid_now,
                "polizza_id": p["id"],
                "numero_titolo": f"{PREFIX}-{year_now}-{i+1:03d}",
                "tipo": "rinnovo",
                "effetto": scad_now,
                "scadenza": scad_now,
                "stato": "da_incassare",
                "importo_lordo": b["lordo"],
                "importo_netto": b["netto"],
                "imposte": b["imp"],
                "provvigioni": b["provv"],
                "accessori": 0.0,
                "sconto_applicato": 0.0,
                "titolo_coperto": False,
                "mezzo_pagamento": random.choice(["contanti", "bonifico", "assegno", "pos", "rid"]),
                "collaboratore_id": p.get("collaboratore_id"),
                "pagamento_in_direzione": False,
                "fonte": "import_ania",
                "stato_carico": stato_carico,
                "caricato_da_import": True,
                "import_batch_id": f"{PREFIX}_batch_{year_now}{month:02d}",
                "import_source": f"{PREFIX}_seed",
                "note_carico": f"{PREFIX} corrente — {variazione}",
                "premio_precedente": premio_prev,
                "tenant_id": p.get("tenant_id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.titoli.insert_one(titolo_now)
            creati_now += 1
            titoli_ids.append(tid_now)

    client.close()
    return {
        "ok": True,
        "polizze_toccate": len(pols),
        "titoli_storici_creati": creati_prev,
        "titoli_correnti_creati": creati_now,
        "totale": creati_prev + creati_now,
        "batch_id": f"{PREFIX}_batch_{year_now}{month:02d}",
        "prefisso_num_titolo": PREFIX,
    }


async def cleanup() -> dict:
    """Rimuove tutti i titoli di test (prefisso TEST_CARICHI)."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    r = await db.titoli.delete_many({"numero_titolo": {"$regex": f"^{PREFIX}-"}})
    client.close()
    return {"ok": True, "cancellati": r.deleted_count}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=15,
                        help="numero polizze da usare (default 15)")
    parser.add_argument("--cleanup", action="store_true",
                        help="cancella i titoli di test invece di crearli")
    args = parser.parse_args()

    if args.cleanup:
        out = asyncio.run(cleanup())
    else:
        out = asyncio.run(seed(n_polizze=args.n))
    import json
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
