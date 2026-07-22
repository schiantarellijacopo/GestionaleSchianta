"""Seed di dati fittizi per il tenant `demo`.

Popolamento idempotente: cancella e reinserisce anagrafiche/polizze/titoli/
sinistri del tenant demo. Usa nomi/dati inventati esclusivamente per demo
commerciali (nessun cliente reale).

Uso via API: POST /api/super-admin/demo/seed  (solo super_admin)
Uso CLI:     cd /app/backend && python -c "import asyncio; from demo_seed import seed_demo_tenant; print(asyncio.run(seed_demo_tenant()))"
"""
from __future__ import annotations
import random
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from database import raw_db
from tenant import TENANT_DEMO_ID


DEMO_TID = TENANT_DEMO_ID


NOMI = ["Mario", "Luca", "Giulia", "Anna", "Roberto", "Elena", "Marco", "Sofia",
        "Andrea", "Chiara", "Paolo", "Francesca", "Davide", "Martina", "Fabio", "Alessia"]
COGNOMI = ["Rossi", "Bianchi", "Verdi", "Ferrari", "Russo", "Esposito", "Romano",
           "Colombo", "Bruno", "Ricci", "Marino", "Greco", "Costa", "Gallo", "Conti", "De Luca"]
CITTA = [("Milano", "MI"), ("Roma", "RM"), ("Torino", "TO"), ("Bologna", "BO"),
         ("Firenze", "FI"), ("Napoli", "NA"), ("Bergamo", "BG"), ("Verona", "VR")]
COMPAGNIE_DEMO = [
    ("CTL", "Cattolica Assicurazioni"),
    ("UNI", "UnipolSai"),
    ("GEN", "Generali Italia"),
    ("ALL", "Allianz"),
    ("AXA", "AXA Assicurazioni"),
]
RAMI_ELE = ["RCA", "INF", "ABI", "MAL", "VIT"]  # RC Auto, Infortuni, Abitazione, Malattia, Vita
PRODOTTI_ELE = ["AUTO PLUS", "MOTOR TOP", "CASA SICURA", "SALUTE FAMILY", "VITA CAPITAL"]


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).isoformat()


def _iso_date(dt: datetime) -> str:
    return dt.date().isoformat()


def _random_cf() -> str:
    """Fake CF codice fiscale (formato valido, dati random)."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"
    return (
        "".join(random.choices(letters, k=6))
        + "".join(random.choices(digits, k=2))
        + random.choice("ABCDEHLMPRST")
        + "".join(random.choices(digits, k=2))
        + random.choice(letters)
        + "".join(random.choices(digits, k=3))
        + random.choice(letters)
    )


def _random_piva() -> str:
    return "".join(random.choices("0123456789", k=11))


async def _wipe_demo():
    """Rimuove tutti i doc demo pre-esistenti (idempotenza)."""
    for coll in ("anagrafiche", "polizze", "titoli", "sinistri",
                 "movimenti_contabili", "compagnie", "diario_cliente"):
        await raw_db[coll].delete_many({"agenzia_tenant_id": DEMO_TID})


async def seed_demo_tenant() -> dict[str, int]:
    """Popola tenant demo con ~15 clienti, ~20 polizze, ~30 titoli, ~5 sinistri."""
    await _wipe_demo()
    now = datetime.now(timezone.utc)
    report = {"anagrafiche": 0, "polizze": 0, "titoli": 0, "sinistri": 0, "compagnie": 0}

    # 1. Compagnie
    compagnie_ids: dict[str, str] = {}
    compagnie_docs = []
    for cod, ragione in COMPAGNIE_DEMO:
        cid = str(uuid4())
        compagnie_ids[cod] = cid
        compagnie_docs.append({
            "id": cid,
            "codice": cod,
            "ragione_sociale": ragione,
            "attiva": True,
            "agenzia_tenant_id": DEMO_TID,
            "created_at": _iso(now), "updated_at": _iso(now),
        })
    await raw_db.compagnie.insert_many(compagnie_docs)
    report["compagnie"] = len(compagnie_docs)

    # 2. Anagrafiche (15 persone fisiche + 3 società)
    anag_ids: list[str] = []
    anag_docs = []
    random.seed(42)  # deterministico
    for i in range(15):
        nome, cognome = random.choice(NOMI), random.choice(COGNOMI)
        citta, prov = random.choice(CITTA)
        aid = str(uuid4())
        anag_ids.append(aid)
        anag_docs.append({
            "id": aid,
            "tipo_soggetto": "persona_fisica",
            "nome": nome,
            "cognome": cognome,
            "ragione_sociale": f"{cognome} {nome}",
            "codice_fiscale": _random_cf(),
            "email": f"{nome.lower()}.{cognome.lower()}@example.com",
            "telefono": f"+39 3{random.randint(10,99)} {random.randint(1000000,9999999)}",
            "indirizzo": f"Via Demo {random.randint(1,200)}",
            "citta": citta,
            "provincia": prov,
            "data_nascita": _iso_date(now - timedelta(days=365 * random.randint(25, 65))),
            "agenzia_tenant_id": DEMO_TID,
            "created_at": _iso(now), "updated_at": _iso(now),
        })
    for i in range(3):
        aid = str(uuid4())
        anag_ids.append(aid)
        rs = f"Demo Company {i+1} S.r.l."
        anag_docs.append({
            "id": aid,
            "tipo_soggetto": "societa",
            "ragione_sociale": rs,
            "partita_iva": _random_piva(),
            "email": f"info@democompany{i+1}.example.com",
            "telefono": f"+39 02 {random.randint(1000000,9999999)}",
            "indirizzo": f"Via Aziendale {random.randint(1,50)}",
            "citta": "Milano", "provincia": "MI",
            "agenzia_tenant_id": DEMO_TID,
            "created_at": _iso(now), "updated_at": _iso(now),
        })
    await raw_db.anagrafiche.insert_many(anag_docs)
    report["anagrafiche"] = len(anag_docs)

    # 3. Polizze (25) — 1-2 per cliente
    pol_docs = []
    for _ in range(25):
        aid = random.choice(anag_ids)
        ramo = random.choice(RAMI_ELE)
        cod_comp = random.choice(list(compagnie_ids.keys()))
        effetto = now - timedelta(days=random.randint(30, 500))
        scadenza = effetto + timedelta(days=365)
        premio = round(random.uniform(250, 1800), 2)
        pol_docs.append({
            "id": str(uuid4()),
            "numero_polizza": f"DEMO-{random.randint(100000,999999)}",
            "compagnia_id": compagnie_ids[cod_comp],
            "compagnia_codice_exp": cod_comp,
            "contraente_id": aid,
            "ramo": ramo,
            "prodotto": random.choice(PRODOTTI_ELE),
            "stato": random.choice(["attiva", "attiva", "attiva", "scaduta"]),
            "effetto": _iso_date(effetto),
            "scadenza": _iso_date(scadenza),
            "frazionamento": random.choice(["annuale", "semestrale", "mensile"]),
            "premio_lordo": premio,
            "premio_netto": round(premio * 0.82, 2),
            "premio_tasse": round(premio * 0.18, 2),
            "provvigioni": round(premio * 0.12, 2),
            "capitale_assicurato": random.choice([0, 50000, 100000, 500000, 1000000]),
            "fonte": "demo_seed",
            "agenzia_tenant_id": DEMO_TID,
            "created_at": _iso(now), "updated_at": _iso(now),
        })
    await raw_db.polizze.insert_many(pol_docs)
    report["polizze"] = len(pol_docs)

    # 4. Titoli (~40) — 1-2 per polizza
    titoli_docs = []
    for pol in pol_docs:
        for _ in range(random.randint(1, 2)):
            lordo = pol["premio_lordo"] / random.choice([1, 2])
            titoli_docs.append({
                "id": str(uuid4()),
                "polizza_id": pol["id"],
                "effetto": pol["effetto"],
                "scadenza": pol["scadenza"],
                "stato": random.choice(["incassato", "incassato", "pendente"]),
                "importo_lordo": round(lordo, 2),
                "importo_netto": round(lordo * 0.82, 2),
                "imposte": round(lordo * 0.18, 2),
                "accessori": round(lordo * 0.03, 2),
                "provvigioni": round(lordo * 0.12, 2),
                "data_incasso": pol["effetto"] if random.random() < 0.6 else None,
                "mezzo_pagamento": random.choice(["BON", "CC", "SDD"]),
                "fonte": "demo_seed",
                "agenzia_tenant_id": DEMO_TID,
                "created_at": _iso(now), "updated_at": _iso(now),
            })
    await raw_db.titoli.insert_many(titoli_docs)
    report["titoli"] = len(titoli_docs)

    # 5. Sinistri (5)
    sin_docs = []
    for _ in range(5):
        pol = random.choice(pol_docs)
        data_sin = now - timedelta(days=random.randint(10, 300))
        sin_docs.append({
            "id": str(uuid4()),
            "numero_sinistro": f"SIN-DEMO-{random.randint(1000,9999)}",
            "polizza_id": pol["id"],
            "contraente_id": pol["contraente_id"],
            "compagnia_id": pol["compagnia_id"],
            "data_sinistro": _iso_date(data_sin),
            "descrizione": random.choice([
                "Tamponamento in coda", "Furto smartphone in auto",
                "Danno acqua condominiale", "Vetro laterale rotto",
                "Grandine su carrozzeria",
            ]),
            "stato": random.choice(["aperto", "in_istruttoria", "liquidato"]),
            "importo_richiesto": round(random.uniform(200, 8000), 2),
            "importo_liquidato": 0,
            "agenzia_tenant_id": DEMO_TID,
            "created_at": _iso(now), "updated_at": _iso(now),
        })
    await raw_db.sinistri.insert_many(sin_docs)
    report["sinistri"] = len(sin_docs)

    return {"tenant": DEMO_TID, "created": report}
