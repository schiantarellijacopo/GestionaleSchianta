import asyncio, io, zipfile, sys
sys.path.insert(0, "/app/backend")
from database import set_current_user, raw_db, db as tdb
import ania_importer

TID = "c942fe2a-8919-48ea-9dc6-a2bf0e51b6ed"  # sandbox
USER = {"id": "test-omnia-user", "role": "admin", "agenzia_tenant_id": TID, "name": "Tester"}

def csv(headers, rows):
    out = ";".join(headers) + "\n"
    for r in rows:
        out += ";".join(str(r.get(h, "")) for h in headers) + "\n"
    return out

def build_zip():
    files = {}
    files["rec100.csv"] = csv(
        ["codice_prodotto", "descrizione_prodotto", "compagnia_exp", "compagnia_ania"],
        [{"codice_prodotto": "ZTESTPRD1", "descrizione_prodotto": "ZTEST Polizza Auto", "compagnia_exp": "ZTESTC", "compagnia_ania": "999"}],
    )
    files["rec101.csv"] = csv(
        ["codice_produttore", "descrizione_collaboratore", "cod_rui", "codice_fiscale"],
        [{"codice_produttore": "ZTESTCOL1", "descrizione_collaboratore": "ZTEST MARIO ROSSI", "cod_rui": "R000", "codice_fiscale": ""}],
    )
    files["rec10.csv"] = csv(
        ["id_anagrafica_exp", "ragione_sociale", "codice_fiscale", "partita_iva", "compagnia_exp", "compagnia_ania"],
        [{"id_anagrafica_exp": "ZTESTANA1", "ragione_sociale": "ZTEST AZIENDA SRL", "codice_fiscale": "", "partita_iva": "12345678901"}],
    )
    files["rec20.csv"] = csv(
        ["id_polizza_exp", "numero_polizza_cmp", "id_anagrafica_exp", "compagnia_exp", "compagnia_ania",
         "cod_stato_share", "ramo_share", "prodotto_cmp"],
        [{"id_polizza_exp": "ZTESTPOL1", "numero_polizza_cmp": "ZTESTNUM1", "id_anagrafica_exp": "ZTESTANA1",
          "compagnia_exp": "ZTESTC", "compagnia_ania": "999", "cod_stato_share": "1",
          "ramo_share": "ZTESTRAMO", "prodotto_cmp": "ZTESTPRD1"}],
    )
    files["rec50.csv"] = csv(
        ["id_polizza_exp", "id_sinistro_exp", "id_contraente_exp", "compagnia_exp",
         "stato_sinistro", "ramo_sinistro_share", "numero_sinistro_cmp",
         "data_avvenimento", "data_denuncia", "dinamica_sinistro", "riserva_totale", "liquidazione_totale"],
        [{"id_polizza_exp": "ZTESTPOL1", "id_sinistro_exp": "ZTESTSIN1", "id_contraente_exp": "ZTESTANA1",
          "compagnia_exp": "ZTESTC", "stato_sinistro": "aperto", "ramo_sinistro_share": "ZTESTRAMO",
          "numero_sinistro_cmp": "ZTESTSNUM1", "data_avvenimento": "01/06/2025", "data_denuncia": "02/06/2025",
          "dinamica_sinistro": "Tamponamento di prova", "riserva_totale": "100,00", "liquidazione_totale": "0"}],
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


async def cleanup():
    await raw_db.prodotti.delete_many({"nome": {"$regex": "ZTEST"}})
    await raw_db.rami.delete_many({"codice": {"$regex": "ZTEST"}})
    await raw_db.tipologie_sinistri.delete_many({"nome": {"$regex": "ZTEST"}})
    await raw_db.users.delete_many({"auto_created_from_codice": {"$regex": "ZTESTCOL"}})
    await raw_db.anagrafiche.delete_many({"id_anagrafica_exp": {"$regex": "ZTEST"}})
    await raw_db.polizze.delete_many({"id_polizza_exp": {"$regex": "ZTEST"}})
    await raw_db.sinistri.delete_many({"id_sinistro_exp": {"$regex": "ZTEST"}})
    await raw_db.import_mappings.delete_many({"valore_flusso": {"$regex": "ZTEST"}})


async def main():
    set_current_user(USER)
    await cleanup()
    log = await ania_importer.importa_zip(tdb, build_zip(), "ztest.zip", USER)
    print("== IMPORT LOG ==")
    print("  record_types:", log.record_types_processati)
    print("  anagrafiche_create:", log.anagrafiche_create, "sinistri_creati:", log.sinistri_creati)

    prod = await raw_db.prodotti.find_one({"nome": "ZTEST Polizza Auto"})
    ramo = await raw_db.rami.find_one({"codice": "ZTESTRAMO"})
    tip = await raw_db.tipologie_sinistri.find_one({"nome": "ZTESTRAMO"})
    collab = await raw_db.users.find_one({"auto_created_from_codice": "ZTESTCOL1"})
    pol = await raw_db.polizze.find_one({"id_polizza_exp": "ZTESTPOL1"})
    ana = await raw_db.anagrafiche.find_one({"id_anagrafica_exp": "ZTESTANA1"})

    print("\n== VERIFICHE ==")
    print("  Prodotto creato:", bool(prod), "| compagnia_id:", prod.get("compagnia_id") if prod else None, "| tenant:", prod.get("agenzia_tenant_id") if prod else None)
    print("  Ramo creato (globale):", bool(ramo), "| nome:", ramo.get("nome") if ramo else None)
    print("  Tipologia sinistro creata:", bool(tip), "| categoria:", tip.get("categoria") if tip else None, "| tenant:", tip.get("agenzia_tenant_id") if tip else None)
    print("  Collaboratore creato:", bool(collab), "| name:", collab.get("name") if collab else None, "| tenant:", collab.get("agenzia_tenant_id") if collab else None, "| role:", collab.get("role") if collab else None)
    print("  Anagrafica azienda (P.IVA):", bool(ana), "| tipo:", ana.get("tipo") if ana else None)
    print("  Polizza creata:", bool(pol), "| ramo:", pol.get("ramo") if pol else None, "| tenant:", pol.get("agenzia_tenant_id") if pol else None)

    ok = all([prod, ramo, tip, collab, pol, ana]) and (ana or {}).get("tipo") == "persona_giuridica"
    print("\nRESULT:", "PASS" if ok else "FAIL")
    await cleanup()
    print("cleanup done")

asyncio.run(main())
