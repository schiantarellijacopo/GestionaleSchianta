"""Migration script — MULTI-TENANT bootstrap for a fresh MongoDB.

Uso locale (preview / staging):
    cd /app/backend && python migrate_to_multitenant.py

Uso Railway (produzione):
    railway run python migrate_to_multitenant.py
    # oppure impostare MONGO_URL/DB_NAME e lanciare in remoto.

Cosa fa (idempotente, safe da rieseguire più volte):
  1. Crea/aggiorna i 3 tenant di sistema (principale, demo, clean).
  2. Assegna `agenzia_tenant_id = tenant-principale-schiantarelli` a TUTTI i
     documenti pre-esistenti privi del campo, per tutte le collezioni
     tenant-scoped (anagrafiche, polizze, titoli, sinistri, allegati, ecc.).
  3. Promuove l'utente ADMIN_EMAIL (default `admin@assicura.it`) a
     `is_super_admin=True` — l'unico che può vedere/gestire tutti i tenant.
  4. Crea l'indice unico su `tenants.id`.
  5. Stampa un report finale con il conteggio dei documenti migrati.
"""
from __future__ import annotations
import asyncio
import os
import sys

# Aggiungi la cartella corrente al path (serve se lanciato da fuori)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


async def _run() -> int:
    from database import raw_db
    from tenant import (
        seed_tenants, migrate_existing_data_to_principale,
        TENANT_PRINCIPALE_ID, TENANT_SCOPED_COLLECTIONS,
    )

    print("=" * 60)
    print("MULTI-TENANT MIGRATION")
    print("=" * 60)
    print(f"MongoDB: {os.environ.get('MONGO_URL','?')[:40]}…")
    print(f"DB name: {os.environ.get('DB_NAME','?')}")
    print()

    # 1. Seed tenants
    print("[1/5] Seed tenants di sistema…")
    await seed_tenants()
    tenants = await raw_db.tenants.find({}, {"_id": 0, "id": 1, "ragione_sociale": 1, "tipo": 1}).to_list(20)
    for t in tenants:
        print(f"       ✓ {t['id']}: {t['ragione_sociale']} ({t['tipo']})")

    # 2. Migrate legacy data → tenant principale
    print("\n[2/5] Migrazione dati legacy → tenant principale…")
    report = await migrate_existing_data_to_principale()
    total = 0
    for coll, n in sorted(report.items()):
        if coll.endswith("__error"):
            print(f"       ✗ ERROR {coll}: {n}")
            continue
        if n > 0:
            print(f"       ✓ {coll}: {n} documenti aggiornati")
            total += n
    print(f"       TOTALE: {total} documenti riassegnati al tenant principale")

    # 3. Promote admin to super_admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@assicura.it").lower()
    print(f"\n[3/5] Promozione admin ({admin_email}) a super_admin…")
    res_admin = await raw_db.users.update_one(
        {"email": admin_email},
        {"$set": {"is_super_admin": True,
                  "agenzia_tenant_id": TENANT_PRINCIPALE_ID}},
    )
    if res_admin.matched_count == 0:
        print(f"       ⚠ Admin {admin_email} non trovato — verrà creato al primo startup")
    else:
        print(f"       ✓ Admin promosso (modified={res_admin.modified_count})")

    # 4. Indice unico su tenants.id
    print("\n[4/5] Indice unico tenants.id…")
    await raw_db.tenants.create_index("id", unique=True)
    print("       ✓ ok")

    # 5. Verifica finale
    print("\n[5/5] Verifica finale…")
    n_missing = 0
    for coll in TENANT_SCOPED_COLLECTIONS:
        m = await raw_db[coll].count_documents({"agenzia_tenant_id": {"$in": [None, ""]}})
        m += await raw_db[coll].count_documents({"agenzia_tenant_id": {"$exists": False}})
        if m > 0:
            print(f"       ⚠ {coll}: {m} documenti ancora SENZA tenant_id!")
            n_missing += m

    print()
    if n_missing == 0:
        print("✅ MIGRAZIONE COMPLETATA — ZERO doc senza tenant_id")
        return 0
    print(f"⚠ MIGRAZIONE PARZIALE — {n_missing} doc ancora senza tenant_id")
    return 1


if __name__ == "__main__":
    rc = asyncio.run(_run())
    sys.exit(rc)
