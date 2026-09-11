"""Riprende l'import OMNIA dalle fasi titoli/sinistri (polizze e garanzie già fatte).

Uso: cd /app/backend && set -a && . ./.env && set +a && python /app/scripts/omnia_resume.py
"""
import asyncio, os, sys, urllib.request, json
sys.path.insert(0, "/app/backend")
from database import db, raw_db, _current_user_ctx
import ania_importer as ai
from db_models import ImportLog

TENANT = "31b4950e-85c2-4232-a31f-ba226b7923fe"
URL = ("https://customer-assets-wrfwihn1.emergentagent.net/job_24ad771c-c3b3-4e05-9e82-ecb09db00768/"
       "artifacts/g9oqo5qz_A_OW8_23774_20260902222300_83_P_S.zip")
FNAME = "A_OW8_23774_20260902222300_83_P_S.zip"


async def main():
    u = await raw_db.users.find_one({"agenzia_tenant_id": TENANT, "role": "admin"})
    print("utente:", u.get("email"), flush=True)
    _current_user_ctx.set(u)

    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    contents = urllib.request.urlopen(req).read()
    print("zip", len(contents), flush=True)
    files_data = ai._extract_zip_contents(contents, FNAME)

    # mappe ricostruite dal DB (le polizze/anagrafiche sono già importate)
    polizza_id_map = {}
    async for p in db.polizze.find({"id_polizza_exp": {"$nin": [None, ""]}},
                                   {"_id": 0, "id": 1, "id_polizza_exp": 1}):
        polizza_id_map[str(p["id_polizza_exp"])] = p["id"]
    ana_id_map = {}
    async for a in db.anagrafiche.find({"id_anagrafica_exp": {"$nin": [None, ""]}},
                                       {"_id": 0, "id": 1, "id_anagrafica_exp": 1}):
        ana_id_map[str(a["id_anagrafica_exp"])] = a["id"]
    print("mappe:", len(polizza_id_map), "polizze,", len(ana_id_map), "anagrafiche", flush=True)

    counts, tracker = {}, {}
    log = ImportLog(nome_file=FNAME, flusso="omnia")
    mapping_operatori = await ai._load_mapping_operatori(db)
    import_mappings = await ai._load_import_mappings(db, "omnia")

    print("FASE titoli…", flush=True)
    await ai._processa_titoli(db, files_data, log, polizza_id_map, counts,
                              mapping_operatori=mapping_operatori,
                              tracker=tracker, import_mappings=import_mappings)
    print("titoli fatti:", counts, flush=True)

    print("FASE sinistri…", flush=True)
    await ai._processa_sinistri(db, files_data, log, polizza_id_map, ana_id_map, {},
                                counts, tracker=tracker, import_mappings=import_mappings)
    print("sinistri fatti:", counts, flush=True)

    print("FASE liquidazioni (rec52)…", flush=True)
    n_liq = await ai._processa_liquidazioni(db, files_data, counts)
    print("sinistri con liquidazione aggiornata:", n_liq, flush=True)

    n = await ai._marca_polizze_sostituite(db)
    print("polizze marcate sostituite:", n, flush=True)
    n2 = await ai._aggiorna_scadenza_da_titoli(db)
    print("scadenze contratto allineate all'ultimo titolo pagato:", n2, flush=True)

    # titoli a premio zero → incassati
    r = await db.titoli.update_many({"importo_lordo": {"$lte": 0}, "stato": {"$ne": "incassato"}},
                                    {"$set": {"stato": "incassato"}})
    print("titoli premio 0 incassati:", r.modified_count, flush=True)
    print("FINE", json.dumps(counts, default=str)[:800], flush=True)

asyncio.run(main())
