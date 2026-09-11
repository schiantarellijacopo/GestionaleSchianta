"""Chiude polizze e storna titoli quando l'ultimo incasso/copertura non è del 2025-2026."""
import asyncio, os, sys
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

TENANT = os.environ.get("TENANT_ID", "31b4950e-85c2-4232-a31f-ba226b7923fe")
DRY = os.environ.get("DRY", "1") == "1"
APERTI = ["da_incassare", "insoluto", "sospeso"]
SOGLIA = "2025-01-01"


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    ultimo_ok, scad_recente, con_titoli = {}, set(), set()
    async for t in db.titoli.find(
        {"agenzia_tenant_id": TENANT},
        {"_id": 0, "polizza_id": 1, "stato": 1, "titolo_coperto": 1,
         "data_incasso": 1, "data_copertura": 1, "scadenza": 1},
    ):
        pid = t.get("polizza_id")
        if not pid:
            continue
        con_titoli.add(pid)
        if t.get("stato") == "incassato" or t.get("titolo_coperto"):
            d = max([x for x in (t.get("data_incasso"), t.get("data_copertura"),
                                 t.get("scadenza")) if x] or [""])
            if d > ultimo_ok.get(pid, ""):
                ultimo_ok[pid] = d
        if (t.get("scadenza") or "") >= SOGLIA:
            scad_recente.add(pid)

    ops_pol, ids_da_stornare, esempi, senza_titoli = [], [], [], 0
    async for p in db.polizze.find({"agenzia_tenant_id": TENANT},
                                   {"_id": 0, "id": 1, "numero_polizza": 1, "scadenza": 1, "stato": 1}):
        u = ultimo_ok.get(p["id"], "")
        if u >= SOGLIA:
            continue                      # incasso/copertura nel 2025-2026 → resta attiva
        if not u and p["id"] in scad_recente:
            continue                      # nuova polizza in attesa del primo incasso
        # titoli aperti da stornare: su qualsiasi stato polizza
        ids_da_stornare.append(p["id"])
        if p.get("stato") not in ("attiva", "sospesa"):
            continue
        if p["id"] not in con_titoli:
            senza_titoli += 1
            continue                      # nessun titolo: non la tocco
        fine = u or p.get("scadenza") or datetime.now(timezone.utc).date().isoformat()
        ops_pol.append(UpdateOne({"id": p["id"]}, {"$set": {
            "stato": "annullata", "data_annullamento": fine,
            "motivo_annullamento": f"Nessun incasso/copertura dal {fine}",
            "updated_at": datetime.now(timezone.utc).isoformat()}}))
        if len(esempi) < 8:
            esempi.append((p.get("numero_polizza"), u or "mai incassato"))
    print("polizze attive senza alcun titolo (non toccate):", senza_titoli, flush=True)

    n_tit = await db.titoli.count_documents({"agenzia_tenant_id": TENANT,
                                             "polizza_id": {"$in": ids_da_stornare},
                                             "stato": {"$in": APERTI}})
    print("polizze da annullare:", len(ops_pol), "| titoli aperti da stornare:", n_tit, flush=True)
    print("esempi:", esempi, flush=True)
    if DRY or not ops_pol:
        return
    r = await db.polizze.bulk_write(ops_pol, ordered=False)
    print("polizze annullate:", r.modified_count, flush=True)
    tot = 0
    for i in range(0, len(ids_da_stornare), 500):
        chunk = ids_da_stornare[i:i + 500]
        rr = await db.titoli.update_many(
            {"polizza_id": {"$in": chunk}, "stato": {"$in": APERTI}},
            {"$set": {"stato": "stornato",
                      "nota": "Stornato: polizza senza incassi dal 2025",
                      "updated_at": datetime.now(timezone.utc).isoformat()}})
        tot += rr.modified_count
    print("titoli stornati:", tot, flush=True)

    # Polizze attive senza alcun titolo: UCA resta attiva, le altre compagnie si annullano
    comp = {c["id"]: (c.get("ragione_sociale") or c.get("codice") or "") async for c in
            db.compagnie.find({}, {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1})}
    ops2, tenute = [], 0
    async for p in db.polizze.find({"agenzia_tenant_id": TENANT,
                                    "stato": {"$in": ["attiva", "sospesa"]}},
                                   {"_id": 0, "id": 1, "compagnia_id": 1, "scadenza": 1}):
        if p["id"] in con_titoli:
            continue
        nome = comp.get(p.get("compagnia_id"), "").upper()
        if "UCA" in nome:
            tenute += 1
            continue
        fine = p.get("scadenza") or datetime.now(timezone.utc).date().isoformat()
        ops2.append(UpdateOne({"id": p["id"]}, {"$set": {
            "stato": "annullata", "data_annullamento": fine,
            "motivo_annullamento": "Polizza senza titoli nel flusso (compagnia non UCA)",
            "updated_at": datetime.now(timezone.utc).isoformat()}}))
    print("senza titoli: UCA tenute attive", tenute, "| da annullare", len(ops2), flush=True)
    if ops2:
        r2 = await db.polizze.bulk_write(ops2, ordered=False)
        print("annullate (senza titoli, non UCA):", r2.modified_count, flush=True)

asyncio.run(main())
