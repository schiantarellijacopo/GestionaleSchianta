"""Import OMNIA ZIP nel tenant Axicura con VINCOLI specifici (arricchimento):
  - anagrafiche: SOLO esistenti; aggiunge IBAN a conti_correnti; NON tocca
    email/cellulare/operatore.
  - polizze: SOLO esistenti; aggiunge garanzie/veicolo(targa,modello,massimali);
    aggiorna il NOME prodotto; NON tocca operatore/date/ramo/titoli.
  - sinistri: aggiunge tutti (collegati a polizze esistenti).
Non importa titoli (rec40/41/42/43).

Uso: DIR=/tmp/omnia_zip PHASE=all python3 import_omnia_axicura.py
     PHASE ∈ {iban, polizze_dettagli, prodotti, sinistri, all}
"""
import asyncio, os, sys
from datetime import datetime, timezone
sys.path.insert(0, "/app/backend")

from database import db, set_current_user
import ania_importer as A
from db_models import ImportLog

EMAIL = os.environ.get("ADMIN_EMAIL", "jacopo@schiantarelli.it")
DIR = os.environ.get("DIR", "/tmp/omnia_zip")
PHASE = os.environ.get("PHASE", "all")
NOW = datetime.now(timezone.utc).isoformat()


def _read(rec):
    path = os.path.join(DIR, f"{rec}oweb.csv")
    if not os.path.exists(path):
        return None
    with open(path, encoding="latin-1") as f:
        return f.read()


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await raw.users.find_one({"email": EMAIL}, {"_id": 0})
    T = user.get("agenzia_tenant_id")
    print(f"utente={EMAIL} tenant={T} phase={PHASE}", flush=True)
    set_current_user(user)

    # Preload indici del tenant
    pol_by_num, pol_by_norm, ana_by_cf, ana_by_piva = {}, {}, {}, {}
    _norm = lambda n: (n or "").strip().lstrip("0")
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1}):
        if p.get("numero_polizza"):
            k = p["numero_polizza"].strip()
            pol_by_num[k] = p["id"]
            pol_by_norm.setdefault(_norm(k), p["id"])
    async for a in db.anagrafiche.find({}, {"_id": 0, "id": 1, "codice_fiscale": 1, "partita_iva": 1}):
        if a.get("codice_fiscale"):
            ana_by_cf[a["codice_fiscale"].strip().upper()] = a["id"]
        if a.get("partita_iva"):
            ana_by_piva[a["partita_iva"].strip()] = a["id"]
    print(f"indici: polizze={len(pol_by_num)} ana_cf={len(ana_by_cf)} ana_piva={len(ana_by_piva)}", flush=True)

    # Mappe id_exp -> id DB (per sinistri) + IBAN + prodotto
    polizza_id_map, ana_id_map = {}, {}
    counts = {}

    # ---- costruzione mappe da rec10 / rec20 ----
    rec10 = _read("rec10")
    ibans = []  # (ana_id, iban)
    if rec10:
        for row in A._read_csv_text(rec10):
            cf = (row.get("codice_fiscale") or "").strip().upper()
            piva = (row.get("partita_iva") or "").strip()
            aid = ana_by_cf.get(cf) or ana_by_piva.get(piva)
            exp = (row.get("id_anagrafica_exp") or "").strip()
            if aid and exp:
                ana_id_map[exp] = aid
            iban = (row.get("iban") or "").strip()
            if aid and iban:
                ibans.append((aid, iban))
        print(f"rec10: match anagrafiche={len(ana_id_map)} | con IBAN={len(ibans)}", flush=True)

    rec20 = _read("rec20")
    prod_updates = []  # (pol_id, codice_prodotto)
    if rec20:
        for row in A._read_csv_text(rec20):
            num = (row.get("numero_polizza_cmp") or "").strip()
            exp = (row.get("id_polizza_exp") or "").strip()
            pid = pol_by_num.get(num) or pol_by_norm.get(_norm(num))
            if pid and exp:
                polizza_id_map[exp] = pid
            if pid:
                cod = (row.get("prodotto_cmp") or "").strip()
                if cod:
                    prod_updates.append((pid, cod))
        print(f"rec20: match polizze={len(polizza_id_map)} | prodotto da aggiornare={len(prod_updates)}", flush=True)

    # ===== FASE IBAN =====
    if PHASE in ("all", "iban") and ibans:
        added = 0
        # raggruppa per anagrafica
        per_ana = {}
        for aid, iban in ibans:
            per_ana.setdefault(aid, [])
            if iban not in per_ana[aid]:
                per_ana[aid].append(iban)
        for aid, ib_list in per_ana.items():
            doc = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, "conti_correnti": 1})
            cc = list((doc or {}).get("conti_correnti") or [])
            esistenti = {(c.get("iban") or "").strip() for c in cc}
            nuovi = [ib for ib in ib_list if ib not in esistenti]
            if not nuovi:
                continue
            for ib in nuovi:
                cc.append({"iban": ib, "principale": not cc, "note": "Import OMNIA"})
            await db.anagrafiche.update_one({"id": aid}, {"$set": {"conti_correnti": cc, "updated_at": NOW}})
            added += len(nuovi)
        print(f"[IBAN] IBAN aggiunti: {added} su {len(per_ana)} anagrafiche", flush=True)

    # ===== FASE POLIZZE DETTAGLI (veicoli + garanzie) =====
    if PHASE in ("all", "polizze_dettagli"):
        rec21 = _read("rec21")
        if rec21:
            await A._processa_dettagli_veicolo(db, {"rec21oweb.csv": rec21}, polizza_id_map, counts)
            print(f"[VEICOLI] righe rec21: {counts.get('rec21', 0)}", flush=True)
        rec30 = _read("rec30")
        if rec30:
            mg = await A._load_mapping_garanzie(db)
            await A._processa_garanzie(db, {"rec30oweb.csv": rec30}, polizza_id_map, mg, counts)
            print(f"[GARANZIE] righe rec30: {counts.get('rec30', 0)}", flush=True)

    # ===== FASE PRODOTTI (nome) =====
    if PHASE in ("all", "prodotti"):
        rec100 = _read("rec100")
        prod_map = {}
        if rec100:
            for row in A._read_csv_text(rec100):
                cod = (row.get("codice_prodotto") or "").strip()
                descr = (row.get("descrizione_prodotto") or "").strip()
                if cod and descr:
                    prod_map[cod] = descr
            # popola libreria Prodotti
            await A._processa_prodotti(db, {"rec100oweb.csv": rec100}, counts)
        upd = 0
        from pymongo import UpdateOne
        ops = []
        seen = set()
        for pid, cod in prod_updates:
            if pid in seen:
                continue
            seen.add(pid)
            nome = prod_map.get(cod)
            if not nome:
                continue
            ops.append(UpdateOne({"id": pid}, {"$set": {
                "prodotto": nome, "prodotto_originale": cod, "updated_at": NOW}}))
        for i in range(0, len(ops), 1000):
            r = await db.polizze.bulk_write(ops[i:i + 1000], ordered=False)
            upd += r.modified_count
        print(f"[PRODOTTI] dizionario={len(prod_map)} | polizze aggiornate nome prodotto: {upd}", flush=True)

    # ===== FASE SINISTRI =====
    if PHASE in ("all", "sinistri"):
        log = ImportLog(nome_file="omnia.zip")
        comp_cache = {}
        rec50 = _read("rec50")
        if rec50:
            await A._processa_sinistri(db, {"rec50oweb.csv": rec50}, log,
                                       polizza_id_map, ana_id_map, comp_cache, counts)
            print(f"[SINISTRI] righe rec50: {counts.get('rec50', 0)} | creati: {log.sinistri_creati}", flush=True)
        rec52 = _read("rec52")
        if rec52:
            liq = await A._processa_liquidazioni(db, {"rec52oweb.csv": rec52}, counts)
            print(f"[SINISTRI] liquidazioni aggiornate: {liq}", flush=True)

    # ===== FASE SOSTITUZIONI + FRAZIONAMENTO (OMNIA vince) =====
    if PHASE in ("all", "sostituzioni") and rec20:
        from pymongo import UpdateOne
        TODAY = datetime.now(timezone.utc).date().isoformat()
        ops = []
        linked = 0
        annul_scad = 0
        for row in A._read_csv_text(rec20):
            new_num = (row.get("numero_polizza_cmp") or "").strip()
            new_id = pol_by_num.get(new_num) or pol_by_norm.get(_norm(new_num))
            if not new_id:
                continue
            # Frazionamento OMNIA vince
            fr_raw = (row.get("frazionamento_share") or "").strip()
            fr = A._parse_frazionamento(fr_raw) if fr_raw else None
            set_new = {"updated_at": NOW}
            if fr:
                set_new["frazionamento"] = fr
            # Sostituzione: col BP
            old_num = (row.get("numero_polizza_sostituita_1") or row.get("polizza_sostituita")
                       or A._col_at(row, 67) or "").strip()
            if old_num:
                set_new["sostituisce_polizza"] = old_num
                old_id = pol_by_num.get(old_num) or pol_by_norm.get(_norm(old_num))
                if old_id:
                    ops.append(UpdateOne({"id": old_id, "stato": {"$ne": "annullata"}},
                                         {"$set": {"sostituita_da_polizza_id": new_id,
                                                   "stato": "sostituita", "updated_at": NOW}}))
                    linked += 1
            ops.append(UpdateOne({"id": new_id}, {"$set": set_new}))
            # Frazionamento unico/temporaneo → alla scadenza la polizza si annulla
            if fr in ("unica", "temporanea"):
                scad = (row.get("scadenza_effettiva") or A._col_at(row, 36) or "").strip()
                scad = A._parse_date(scad) if scad else None
                if scad and scad <= TODAY:
                    ops.append(UpdateOne({"id": new_id, "stato": {"$in": ["attiva", "sospesa"]}},
                                         {"$set": {"stato": "annullata",
                                                   "data_annullamento": scad,
                                                   "motivo_annullamento": "Frazionamento unico/temporaneo scaduto",
                                                   "updated_at": NOW}}))
                    annul_scad += 1
        done = 0
        for i in range(0, len(ops), 1000):
            r = await db.polizze.bulk_write(ops[i:i + 1000], ordered=False)
            done += r.modified_count
        print(f"[SOSTITUZIONI] op: {len(ops)} | vecchie collegate: {linked} | "
              f"annullate a scadenza (unico/temp): {annul_scad} | modificate: {done}", flush=True)

    print("FATTO. counts:", counts, flush=True)


asyncio.run(main())
