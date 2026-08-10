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
    creati_annullati = creati_sostituite = creati_sospese = 0
    polizze_nuove_sostituzione: list[dict] = []
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

    # =============================================================
    # SCENARI EDGE — per testare il comportamento del Carichi Mensili
    # Prendo altre polizze e simulo:
    #   A) 3 polizze ANNULLATE nel 2025 (Disdettata / Mezzo Venduto / Voltura)
    #   B) 3 polizze SOSTITUITE nel 2025 (creo la coppia old→new)
    #   C) 3 polizze SOSPESE con titolo 2025 e nessun rinnovo 2026
    # =============================================================
    pol_extra = await db.polizze.find(
        {"stato": {"$in": ["attiva", "sospesa"]},
         "contraente_id": {"$ne": None},
         "premio_lordo": {"$gt": 0},
         "id": {"$nin": [p["id"] for p in pols]}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1,
         "compagnia_id": 1, "premio_lordo": 1, "collaboratore_id": 1,
         "ramo": 1, "prodotto": 1, "frazionamento": 1, "targa": 1,
         "assicurato_ids": 1, "tenant_id": 1},
    ).limit(9).to_list(9)

    async def _crea_titolo_prev(p, motivo_ann=None, stato_carico_v="validato", stato_titolo="incassato"):
        """Crea un titolo 2025 per una polizza."""
        giorno = 1 + (random.randint(0, 26))
        scad = f"{year_prev}-{month:02d}-{min(giorno, last_day_prev):02d}"
        lordo = round(float(p.get("premio_lordo") or 500) * random.uniform(0.9, 1.05), 2)
        netto = round(lordo * 0.78, 2)
        tid = str(uuid.uuid4())
        rec = {
            "id": tid, "polizza_id": p["id"],
            "numero_titolo": f"{PREFIX}-{year_prev}-EDGE-{tid[:6]}",
            "tipo": "rinnovo", "effetto": scad, "scadenza": scad,
            "stato": stato_titolo,
            "importo_lordo": lordo, "importo_netto": netto,
            "imposte": round(lordo - netto, 2),
            "provvigioni": round(netto * 0.12, 2), "accessori": 0.0,
            "data_incasso": scad if stato_titolo == "incassato" else None,
            "importo_pagato": lordo if stato_titolo == "incassato" else None,
            "sconto_applicato": 0.0,
            "titolo_coperto": stato_titolo == "incassato",
            "data_copertura": scad if stato_titolo == "incassato" else None,
            "mezzo_pagamento": random.choice(["contanti", "bonifico", "assegno", "pos"]),
            "collaboratore_id": p.get("collaboratore_id"),
            "pagamento_in_direzione": False, "fonte": "manuale",
            "stato_carico": stato_carico_v,
            "caricato_da_import": False,
            "note_carico": f"{PREFIX} edge — {motivo_ann or 'ok'}",
            "motivo_mancanza": motivo_ann,
            "premio_precedente": None,
            "tenant_id": p.get("tenant_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.titoli.insert_one(rec)
        return tid

    # --- A) Polizze annullate nel 2025 ---
    motivi_annullamento = ["Disdettata", "Mezzo Venduto", "Voltura"]
    for i, p in enumerate(pol_extra[0:3]):
        motivo = motivi_annullamento[i % 3]
        data_ann_2025 = f"{year_prev}-{random.randint(6, 11):02d}-{random.randint(1, 28):02d}"
        # aggiorna polizza → annullata
        await db.polizze.update_one({"id": p["id"]}, {"$set": {
            "stato": "annullata",
            "data_annullamento": data_ann_2025,
            "motivo_annullamento": motivo,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }})
        # titolo storico 2025 con motivo di annullamento
        tid = await _crea_titolo_prev(p, motivo_ann=motivo,
                                        stato_carico_v="annullato_carico",
                                        stato_titolo="incassato")
        titoli_ids.append(tid)
        creati_annullati += 1

    # --- B) Polizze sostituite (crea polizza NUOVA che sostituisce la vecchia) ---
    for i, p in enumerate(pol_extra[3:6]):
        data_sost_2025 = f"{year_prev}-{random.randint(3, 10):02d}-{random.randint(1, 28):02d}"
        # 1) marca la vecchia come sostituita
        nuova_pol_id = str(uuid.uuid4())
        await db.polizze.update_one({"id": p["id"]}, {"$set": {
            "stato": "sostituita",
            "sostituita_da_polizza_id": nuova_pol_id,
            "data_annullamento": data_sost_2025,
            "motivo_annullamento": "Sostituita",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }})
        # 2) crea la NUOVA polizza (rinnovata con lo stesso contraente)
        premio_new = round(float(p.get("premio_lordo") or 500) * random.uniform(0.95, 1.15), 2)
        nuova = {
            "id": nuova_pol_id, "numero_polizza": f"{PREFIX}-NEW-{i+1:02d}",
            "compagnia_id": p["compagnia_id"], "contraente_id": p["contraente_id"],
            "assicurato_ids": p.get("assicurato_ids") or [p["contraente_id"]],
            "ramo": p.get("ramo") or "RCA", "prodotto": p.get("prodotto"),
            "stato": "attiva",
            "effetto": data_sost_2025,
            "scadenza": f"{year_now}-{month:02d}-{last_day_now:02d}",
            "frazionamento": p.get("frazionamento") or "annuale",
            "premio_lordo": premio_new,
            "premio_netto": round(premio_new * 0.78, 2),
            "premio_imposte": round(premio_new * 0.22, 2),
            "provvigioni": round(premio_new * 0.10, 2),
            "targa": p.get("targa"),
            "sostituisce_polizza": p["id"],
            "tenant_id": p.get("tenant_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "fonte": "manuale",
        }
        await db.polizze.insert_one(nuova)
        polizze_nuove_sostituzione.append({"vecchia_id": p["id"], "nuova_id": nuova_pol_id,
                                            "numero_polizza": nuova["numero_polizza"]})
        # 3) titolo storico 2025 sulla vecchia (annullato per sostituzione)
        tid_prev = await _crea_titolo_prev(p, motivo_ann="Sostituita",
                                             stato_carico_v="annullato_carico",
                                             stato_titolo="incassato")
        titoli_ids.append(tid_prev)
        # 4) titolo corrente 2026 sulla NUOVA polizza — in attesa
        giorno = min(1 + (i % 27), last_day_now)
        scad_now = f"{year_now}-{month:02d}-{giorno:02d}"
        tid_now = str(uuid.uuid4())
        lordo = round(premio_new * random.uniform(1.0, 1.10), 2)
        netto = round(lordo * 0.78, 2)
        await db.titoli.insert_one({
            "id": tid_now, "polizza_id": nuova_pol_id,
            "numero_titolo": f"{PREFIX}-{year_now}-SOST-{i+1:02d}",
            "tipo": "rinnovo", "effetto": scad_now, "scadenza": scad_now,
            "stato": "da_incassare",
            "importo_lordo": lordo, "importo_netto": netto,
            "imposte": round(lordo - netto, 2),
            "provvigioni": round(netto * 0.12, 2), "accessori": 0.0,
            "sconto_applicato": 0.0, "titolo_coperto": False,
            "mezzo_pagamento": "bonifico",
            "collaboratore_id": p.get("collaboratore_id"),
            "pagamento_in_direzione": False, "fonte": "import_ania",
            "stato_carico": "in_attesa",
            "caricato_da_import": True,
            "import_batch_id": f"{PREFIX}_batch_{year_now}{month:02d}",
            "import_source": f"{PREFIX}_seed_sostituzione",
            "note_carico": f"{PREFIX} — rinnovo su polizza sostituita",
            "premio_precedente": p.get("premio_lordo"),
            "tenant_id": p.get("tenant_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        titoli_ids.append(tid_now)
        creati_sostituite += 1

    # --- C) Polizze sospese ---
    for i, p in enumerate(pol_extra[6:9]):
        data_sosp = f"{year_prev}-{random.randint(9, 12):02d}-{random.randint(1, 28):02d}"
        riatt = f"{year_now}-{month:02d}-{random.randint(15, 28):02d}"
        await db.polizze.update_one({"id": p["id"]}, {"$set": {
            "stato": "sospesa",
            "data_sospensione": data_sosp,
            "riattivazione_prevista": riatt,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }})
        # titolo storico 2025 (incassato, prima della sospensione)
        tid_prev = await _crea_titolo_prev(p, motivo_ann=None,
                                             stato_carico_v="validato",
                                             stato_titolo="incassato")
        titoli_ids.append(tid_prev)
        # titolo 2026 → pending/da_incassare in stato_carico=in_attesa
        # (nessun premio corrente ancora perché in sospensione)
        giorno = min(1 + (i % 27), last_day_now)
        scad_now = f"{year_now}-{month:02d}-{giorno:02d}"
        tid_now = str(uuid.uuid4())
        lordo = round(float(p.get("premio_lordo") or 500) * random.uniform(0.95, 1.05), 2)
        netto = round(lordo * 0.78, 2)
        await db.titoli.insert_one({
            "id": tid_now, "polizza_id": p["id"],
            "numero_titolo": f"{PREFIX}-{year_now}-SOSP-{i+1:02d}",
            "tipo": "rinnovo", "effetto": scad_now, "scadenza": scad_now,
            "stato": "da_incassare",
            "importo_lordo": lordo, "importo_netto": netto,
            "imposte": round(lordo - netto, 2),
            "provvigioni": round(netto * 0.12, 2), "accessori": 0.0,
            "sconto_applicato": 0.0, "titolo_coperto": False,
            "mezzo_pagamento": None,
            "collaboratore_id": p.get("collaboratore_id"),
            "pagamento_in_direzione": False, "fonte": "import_ania",
            "stato_carico": "in_attesa",
            "caricato_da_import": True,
            "import_batch_id": f"{PREFIX}_batch_{year_now}{month:02d}",
            "import_source": f"{PREFIX}_seed_sospesa",
            "note_carico": f"{PREFIX} — polizza sospesa, rinnovo pendente",
            "premio_precedente": p.get("premio_lordo"),
            "tenant_id": p.get("tenant_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        titoli_ids.append(tid_now)
        creati_sospese += 1

    client.close()
    return {
        "ok": True,
        "polizze_toccate": len(pols) + len(pol_extra),
        "titoli_storici_creati": creati_prev,
        "titoli_correnti_creati": creati_now,
        "edge_case_annullate_2025": creati_annullati,
        "edge_case_sostituite_2025": creati_sostituite,
        "edge_case_sospese": creati_sospese,
        "polizze_nuove_da_sostituzione": polizze_nuove_sostituzione,
        "totale_titoli_creati": len(titoli_ids),
        "batch_id": f"{PREFIX}_batch_{year_now}{month:02d}",
        "prefisso_num_titolo": PREFIX,
    }


async def cleanup() -> dict:
    """Rimuove tutti i dati di test:
    - titoli con prefisso TEST_CARICHI-
    - polizze nuove create dalle sostituzioni (prefisso TEST_CARICHI-NEW-)
    - ripristina stato delle polizze edge (annullata/sostituita/sospesa) ad "attiva"
    """
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    # 1) Ripristina polizze modificate dal seed (individua tramite motivo_annullamento)
    #    - Le annullate: stato attiva, cancella data_annullamento e motivo
    #    - Le sostituite: idem, cancella sostituita_da_polizza_id
    #    - Le sospese: stato attiva, cancella data_sospensione
    #    Individuazione euristica: cercare polizze che hanno un titolo TEST_CARICHI
    titoli_test = await db.titoli.find(
        {"numero_titolo": {"$regex": f"^{PREFIX}-"}},
        {"_id": 0, "polizza_id": 1},
    ).to_list(10000)
    pol_ids = list({t["polizza_id"] for t in titoli_test if t.get("polizza_id")})
    ripristinate = 0
    if pol_ids:
        r = await db.polizze.update_many(
            {"id": {"$in": pol_ids},
             "stato": {"$in": ["annullata", "sostituita", "sospesa"]}},
            {"$set": {"stato": "attiva"},
             "$unset": {"data_annullamento": "", "motivo_annullamento": "",
                        "sostituita_da_polizza_id": "", "data_sospensione": "",
                        "riattivazione_prevista": ""}},
        )
        ripristinate = r.modified_count

    # 2) Elimina le polizze NUOVE create dalle sostituzioni
    pol_new = await db.polizze.delete_many({"numero_polizza": {"$regex": f"^{PREFIX}-NEW-"}})

    # 3) Elimina i titoli di test
    tit = await db.titoli.delete_many({"numero_titolo": {"$regex": f"^{PREFIX}-"}})

    client.close()
    return {"ok": True,
            "titoli_cancellati": tit.deleted_count,
            "polizze_nuove_cancellate": pol_new.deleted_count,
            "polizze_ripristinate_ad_attiva": ripristinate}


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
