"""Importatore CSV formato ANIA (scambio dati assicurativo italiano).

Supporta i record types:
  rec10  -> Anagrafiche
  rec20  -> Polizze
  rec21  -> Dettagli polizze (RCA / vita)
  rec40  -> Titoli (quietanze)
  rec50  -> Sinistri
  rec100 -> Prodotti (informativo)
  rec101 -> Collaboratori (informativo)

Altri record vengono solo contati e tracciati.
"""
from __future__ import annotations
import csv
import io
import zipfile
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from db_models import (
    Anagrafica, Polizza, Titolo, Sinistro, Compagnia, ImportLog, _uid, _now_iso,
)


async def _load_mapping_garanzie(db) -> dict:
    """Carica mapping {codice_ania: nome_personalizzato} dalle librerie."""
    out = {}
    async for m in db.mapping_garanzie.find({}, {"_id": 0}):
        key = (m.get("codice_ania") or m.get("descrizione_ania") or "").strip().upper()
        if key:
            out[key] = m.get("nome_personalizzato") or m.get("descrizione_ania")
    return out


async def _load_mapping_operatori(db) -> dict:
    """Carica mapping {codice_ania: user_id}."""
    out = {}
    async for m in db.mapping_operatori.find({}, {"_id": 0}):
        key = (m.get("codice_ania") or "").strip()
        if key and m.get("user_id"):
            out[key] = m["user_id"]
    return out


async def _ensure_stub_mapping(db, collection: str, codice: str, descrizione: str = ""):
    """Crea voce stub nella libreria di mapping se non esiste (per permettere all'utente di mapparla)."""
    if not codice:
        return
    existing = await db[collection].find_one({"codice_ania": codice}, {"_id": 0, "id": 1})
    if not existing:
        await db[collection].insert_one({
            "id": _uid(), "codice_ania": codice, "descrizione_ania": descrizione,
            "created_at": _now_iso(), "updated_at": _now_iso(), "is_deleted": False,
        })


def _parse_date(value: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    # formato ANIA: DD/MM/YYYY HH:MM:SS o DD/MM/YYYY
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_float(value: str) -> float:
    if not value:
        return 0.0
    try:
        return float(value.replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


def _read_csv_text(text: str) -> List[Dict[str, str]]:
    """Parse semicolon-delimited CSV with header row."""
    if not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]


def _detect_record_type(filename: str) -> str | None:
    """Esempio: 'rec10oweb.csv' -> 'rec10'"""
    name = filename.lower()
    for prefix in ("rec00", "rec10", "rec20", "rec21", "rec24", "rec30",
                   "rec40", "rec41", "rec42", "rec43", "rec50", "rec51",
                   "rec52", "rec70", "rec100", "rec101"):
        if prefix in name:
            return prefix
    return None



def _parse_flag_si(value: str) -> bool:
    return (value or "").upper() in ("S", "SI", "Y", "1")


def _extract_zip_contents(file_bytes: bytes, filename: str) -> Dict[str, str]:
    """Decomprime lo zip e ritorna {filename: text_utf8}. In caso di non-zip
    interpreta il payload come singolo CSV."""
    files_data: Dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            for member in zf.namelist():
                if not member.lower().endswith(".csv"):
                    continue
                with zf.open(member) as f:
                    raw = f.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                files_data[member] = text
    except zipfile.BadZipFile:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")
        files_data[filename] = text
    return files_data


async def _get_or_create_compagnia(db, codice_exp: str, codice_ania: str,
                                   cache: Dict[str, str]) -> str | None:
    if not codice_exp:
        return None
    if codice_exp in cache:
        return cache[codice_exp]
    existing = await db.compagnie.find_one({"codice": codice_exp})
    if existing:
        cache[codice_exp] = existing["id"]
        return existing["id"]
    comp = Compagnia(
        codice=codice_exp,
        ragione_sociale=codice_exp or f"Compagnia {codice_ania}",
        descrizione=f"Compagnia ANIA {codice_ania}" if codice_ania else None,
    )
    await db.compagnie.insert_one(comp.model_dump())
    cache[codice_exp] = comp.id
    return comp.id


# ---------------------------------------------------------------------------
# Mapping di valori (stati polizza/titolo/sinistro)
# ---------------------------------------------------------------------------
_MAP_STATO_POLIZZA = {
    "a": "attiva", "attiva": "attiva",
    "s": "sospesa", "sospesa": "sospesa",
    "x": "annullata", "annullata": "annullata",
    "e": "scaduta", "scaduta": "scaduta",
}
_MAP_STATO_TITOLO = {
    "i": "incassato", "incassato": "incassato",
    "d": "da_incassare", "da_incassare": "da_incassare",
    "n": "insoluto", "insoluto": "insoluto",
    "s": "stornato", "stornato": "stornato",
}
_MAP_STATO_SINISTRO = {
    "a": "aperto", "aperto": "aperto",
    "i": "in_istruttoria", "in_istruttoria": "in_istruttoria",
    "l": "liquidato", "liquidato": "liquidato",
    "c": "chiuso_senza_seguito", "chiuso": "chiuso_senza_seguito",
    "r": "respinto", "respinto": "respinto",
}


# ---------------------------------------------------------------------------
# Processor: rec10 (anagrafiche)
# ---------------------------------------------------------------------------
async def _build_anagrafica_payload(db, row: dict,
                                    compagnie_cache: Dict[str, str]) -> dict:
    cf = row.get("codice_fiscale") or None
    tipo = "persona_giuridica" if row.get("partita_iva") and not cf else "persona_fisica"
    sesso_raw = (row.get("sesso_share") or "").upper()
    return {
        "tipo": tipo,
        "ragione_sociale": row.get("ragione_sociale") or "Anagrafica",
        "codice_fiscale": cf,
        "partita_iva": row.get("partita_iva") or None,
        "data_nascita": _parse_date(row.get("data_nascita", "")),
        "comune_nascita": row.get("comune_nascita") or None,
        "provincia_nascita": row.get("provincia_nascita") or None,
        "sesso": sesso_raw[:1] if sesso_raw in ("M", "F") else None,
        "indirizzo": row.get("indirizzo") or None,
        "comune": row.get("comune") or None,
        "provincia": row.get("provincia") or None,
        "cap": row.get("cap") or None,
        "nazione": row.get("nazione") or "ITALIA",
        "telefono": row.get("numero_telefono") or None,
        "cellulare": row.get("cellulare") or None,
        "email": row.get("email") or None,
        "iban": row.get("iban") or None,
        "consenso_privacy": _parse_flag_si(row.get("consenso_privacy", "")),
        "data_consenso_privacy": _parse_date(row.get("data_consenso_privacy", "")),
        "compagnia_id": await _get_or_create_compagnia(
            db, row.get("compagnia_exp", ""), row.get("compagnia_ania", ""), compagnie_cache,
        ),
        "fonte": "import_ania",
        "updated_at": _now_iso(),
    }


async def _processa_anagrafiche(db, files_data: Dict[str, str], log: ImportLog,
                                ana_id_map: Dict[str, str],
                                compagnie_cache: Dict[str, str],
                                counts: Dict[str, int]) -> None:
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec10":
            continue
        rows = _read_csv_text(content)
        counts["rec10"] = counts.get("rec10", 0) + len(rows)
        for row in rows:
            id_exp = (row.get("id_anagrafica_exp")
                      or row.get("id_anag_inviante")
                      or _uid())
            data = await _build_anagrafica_payload(db, row, compagnie_cache)
            data["ragione_sociale"] = data["ragione_sociale"] or f"Anagrafica {id_exp}"
            data["id_anagrafica_exp"] = id_exp
            cf = data["codice_fiscale"]

            query = [{"id_anagrafica_exp": id_exp}]
            if cf:
                query.append({"codice_fiscale": cf})
            existing = await db.anagrafiche.find_one({"$or": query})

            if existing:
                await db.anagrafiche.update_one({"id": existing["id"]}, {"$set": data})
                ana_id_map[id_exp] = existing["id"]
                log.anagrafiche_aggiornate += 1
            else:
                obj = Anagrafica(**data)
                await db.anagrafiche.insert_one(obj.model_dump())
                ana_id_map[id_exp] = obj.id
                log.anagrafiche_create += 1


# ---------------------------------------------------------------------------
# Processor: rec20 (polizze)
# ---------------------------------------------------------------------------
async def _risolvi_contraente(db, contraente_exp: str | None,
                              ana_id_map: Dict[str, str], log: ImportLog) -> str | None:
    """Risolve l'id contraente (eventualmente creando un placeholder)."""
    if not contraente_exp:
        return None
    if contraente_exp in ana_id_map:
        return ana_id_map[contraente_exp]
    ph = Anagrafica(
        ragione_sociale=f"Anagrafica {contraente_exp}",
        id_anagrafica_exp=contraente_exp,
        fonte="import_ania",
    )
    await db.anagrafiche.insert_one(ph.model_dump())
    ana_id_map[contraente_exp] = ph.id
    log.anagrafiche_create += 1
    return ph.id


async def _processa_polizze(db, files_data: Dict[str, str], log: ImportLog,
                            ana_id_map: Dict[str, str],
                            polizza_id_map: Dict[str, str],
                            compagnie_cache: Dict[str, str],
                            mapping_operatori: dict,
                            counts: Dict[str, int]) -> None:
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec20":
            continue
        rows = _read_csv_text(content)
        counts["rec20"] = counts.get("rec20", 0) + len(rows)
        for row in rows:
            id_exp = row.get("id_polizza_exp") or _uid()
            numero = row.get("numero_polizza_cmp") or id_exp
            contraente_id = await _risolvi_contraente(
                db, row.get("id_anagrafica_exp"), ana_id_map, log,
            )
            comp_id = await _get_or_create_compagnia(
                db, row.get("compagnia_exp", ""), row.get("compagnia_ania", ""), compagnie_cache,
            )
            stato = _MAP_STATO_POLIZZA.get((row.get("cod_stato_share") or "").lower(), "attiva")
            operatore_codice = (row.get("cod_operatore")
                                or row.get("operatore_share")
                                or row.get("cod_collaboratore")
                                or "").strip() or None
            collaboratore_id = mapping_operatori.get(operatore_codice) if operatore_codice else None
            if operatore_codice and not collaboratore_id:
                await _ensure_stub_mapping(
                    db, "mapping_operatori", operatore_codice,
                    row.get("nome_operatore") or row.get("descrizione_operatore") or "",
                )

            existing = await db.polizze.find_one({"id_polizza_exp": id_exp})
            data = {
                "numero_polizza": numero,
                "compagnia_id": comp_id or "",
                "contraente_id": contraente_id or "",
                "ramo": row.get("ramo_share") or row.get("ramo_cmp") or "VARIE",
                "prodotto": row.get("prodotto_cmp") or None,
                "stato": stato,
                "effetto": _parse_date(row.get("effetto", "")) or _now_iso()[:10],
                "scadenza": _parse_date(row.get("scadenza_originale", "")) or _now_iso()[:10],
                "premio_lordo": _parse_float(row.get("lordo_totale", "")),
                "premio_netto": _parse_float(row.get("netto_totale", "")),
                "premio_tasse": _parse_float(row.get("tasse_totale") or row.get("imposte_totali", "")),
                "premio_imposte": _parse_float(row.get("imposte_totali") or row.get("imposte", "")),
                "premio_ssn": _parse_float(row.get("ssn_totale") or row.get("ssn", "")),
                "provvigioni": _parse_float(row.get("provvigioni_totali", "")),
                "operatore_ania_codice": operatore_codice,
                "id_polizza_exp": id_exp,
                "fonte": "import_ania",
                "updated_at": _now_iso(),
            }
            if collaboratore_id:
                data["collaboratore_id"] = collaboratore_id
            if existing:
                await db.polizze.update_one({"id": existing["id"]}, {"$set": data})
                polizza_id_map[id_exp] = existing["id"]
                log.polizze_aggiornate += 1
            else:
                obj = Polizza(**data)
                await db.polizze.insert_one(obj.model_dump())
                polizza_id_map[id_exp] = obj.id
                log.polizze_create += 1


# ---------------------------------------------------------------------------
# Processor: rec21 (dettagli veicolo) — funzioni pure di mapping
# ---------------------------------------------------------------------------
def _build_dettagli_veicolo(row: dict) -> dict:
    upd = {
        "targa": row.get("targa") or None,
        "veicolo_marca": (row.get("marca_veicolo") or "").upper() or None,
        "veicolo_modello": (row.get("modello_veicolo") or "").upper() or None,
        "veicolo_tipo": row.get("tipo_veicolo") or None,
        "veicolo_alimentazione": row.get("alimentazione") or None,
        "veicolo_uso": row.get("uso_veicolo") or None,
        "veicolo_data_immatricolazione": _parse_date(row.get("data_immatricolazione", "")),
        "veicolo_cilindrata": int(row.get("cilindrata") or 0) or None,
        "veicolo_cv_fiscali": int(row.get("cv_fiscali") or 0) or None,
        "veicolo_kw": _parse_float(row.get("kw", "")),
        "veicolo_quintali": _parse_float(row.get("quintali") or row.get("portata") or ""),
        "veicolo_posti": int(row.get("numero_posti") or 0) or None,
        "veicolo_gancio_traino": _parse_flag_si(row.get("gancio_traino", "")),
        "veicolo_targa_rimorchio": row.get("targa_rimorchio") or None,
        "tipo_tariffa": row.get("tipo_tariffa") or None,
        "bm_provenienza": row.get("bm_provenienza") or None,
        "bm_assegnata": row.get("bm_assegnata") or None,
        "bm_assegnata_cu": row.get("bm_assegnata_cu") or None,
        "pejus": _parse_float(row.get("pejus", "")),
        "franchigia": _parse_float(row.get("franchigia", "")),
        "valore_veicolo": _parse_float(row.get("valore_veicolo", "")),
        "valore_residuo_veicolo": _parse_float(row.get("valore_residuo", "")),
        "valore_accessori": _parse_float(row.get("valore_accessori", "")),
        "guida_esperta": _parse_flag_si(row.get("guida_esperta", "")),
        "guida_esclusiva": _parse_flag_si(row.get("guida_esclusiva", "")),
        "rinuncia_rivalsa": _parse_flag_si(row.get("rinuncia_rivalsa", "")),
        "massimali": row.get("massimali") or None,
        "updated_at": _now_iso(),
    }
    return {k: v for k, v in upd.items() if v not in (None, "", 0, 0.0) or k == "targa"}


async def _processa_dettagli_veicolo(db, files_data: Dict[str, str],
                                     polizza_id_map: Dict[str, str],
                                     counts: Dict[str, int]) -> None:
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec21":
            continue
        rows = _read_csv_text(content)
        counts["rec21"] = counts.get("rec21", 0) + len(rows)
        for row in rows:
            pol_exp = row.get("id_polizza_exp")
            pol_id = polizza_id_map.get(pol_exp) if pol_exp else None
            if not pol_id:
                continue
            upd = _build_dettagli_veicolo(row)
            if upd:
                await db.polizze.update_one({"id": pol_id}, {"$set": upd})


# ---------------------------------------------------------------------------
# Processor: rec30 (garanzie)
# ---------------------------------------------------------------------------
async def _processa_garanzie(db, files_data: Dict[str, str],
                             polizza_id_map: Dict[str, str],
                             mapping_garanzie: dict,
                             counts: Dict[str, int]) -> None:
    from collections import defaultdict as _dd
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec30":
            continue
        rows = _read_csv_text(content)
        counts["rec30"] = counts.get("rec30", 0) + len(rows)
        gar_per_pol: dict[str, list[dict]] = _dd(list)
        for row in rows:
            pol_exp = row.get("id_polizza_exp")
            pol_id = polizza_id_map.get(pol_exp) if pol_exp else None
            if not pol_id:
                continue
            codice = (row.get("codice_garanzia") or "").strip().upper()
            descr = row.get("descrizione_garanzia") or row.get("garanzia") or codice or ""
            key = codice or descr.strip().upper()
            nome_finale = mapping_garanzie.get(key) or descr
            if key and key not in mapping_garanzie:
                await _ensure_stub_mapping(db, "mapping_garanzie", codice or key, descr)
            gar_per_pol[pol_id].append({
                "garanzia": nome_finale,
                "garanzia_originale": descr,
                "codice_ania": codice,
                "netto": _parse_float(row.get("netto_garanzia", "")),
                "accessori": _parse_float(row.get("accessori", "")),
                "imposte": _parse_float(row.get("imposte", "")),
                "ssn": _parse_float(row.get("ssn", "")),
                "lordo": _parse_float(row.get("lordo_garanzia") or row.get("lordo", "")),
                "diritti": _parse_float(row.get("diritti", "")),
                "provvigione": _parse_float(row.get("provvigione_garanzia") or row.get("provvigione", "")),
            })
        for pol_id, garanzie in gar_per_pol.items():
            diritti_tot = sum(g.get("diritti", 0.0) for g in garanzie)
            await db.polizze.update_one(
                {"id": pol_id},
                {"$set": {"garanzie": garanzie, "diritti": diritti_tot, "updated_at": _now_iso()}},
            )


# ---------------------------------------------------------------------------
# Processor: rec40 (titoli)
# ---------------------------------------------------------------------------
async def _processa_titoli(db, files_data: Dict[str, str], log: ImportLog,
                           polizza_id_map: Dict[str, str],
                           counts: Dict[str, int]) -> None:
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec40":
            continue
        rows = _read_csv_text(content)
        counts["rec40"] = counts.get("rec40", 0) + len(rows)
        for row in rows:
            pol_exp = row.get("id_polizza_exp")
            pol_id = polizza_id_map.get(pol_exp) if pol_exp else None
            if not pol_id:
                continue
            id_t = row.get("id_titolo_exp") or _uid()
            stato = _MAP_STATO_TITOLO.get((row.get("stato_share") or "").lower(), "da_incassare")
            existing = await db.titoli.find_one({"id_titolo_exp": id_t})
            data = {
                "polizza_id": pol_id,
                "effetto": _parse_date(row.get("effetto_titolo", "")) or _now_iso()[:10],
                "scadenza": _parse_date(row.get("data_scadenza_emesso", "")) or _now_iso()[:10],
                "stato": stato,
                "importo_lordo": _parse_float(row.get("lordo_totale", "")),
                "importo_netto": _parse_float(row.get("netto_totale", "")),
                "imposte": _parse_float(row.get("tasse_totale", "")),
                "provvigioni": _parse_float(row.get("provvigioni_totale", "")),
                "data_incasso": _parse_date(row.get("dt_pag_cliente", "")),
                "mezzo_pagamento": row.get("mezzo_pag_share") or None,
                "id_titolo_exp": id_t,
                "fonte": "import_ania",
                "updated_at": _now_iso(),
            }
            if existing:
                await db.titoli.update_one({"id": existing["id"]}, {"$set": data})
            else:
                obj = Titolo(**data)
                await db.titoli.insert_one(obj.model_dump())
                log.titoli_creati += 1

            # back-fill provvigione su polizza se vuota
            titolo_provv = data.get("provvigioni", 0) or 0
            if titolo_provv > 0:
                pol = await db.polizze.find_one({"id": pol_id}, {"_id": 0, "provvigioni": 1})
                if pol and not (pol.get("provvigioni") or 0):
                    await db.polizze.update_one(
                        {"id": pol_id},
                        {"$set": {"provvigioni": titolo_provv, "updated_at": _now_iso()}},
                    )


# ---------------------------------------------------------------------------
# Processor: rec50 (sinistri)
# ---------------------------------------------------------------------------
async def _processa_sinistri(db, files_data: Dict[str, str], log: ImportLog,
                             polizza_id_map: Dict[str, str],
                             ana_id_map: Dict[str, str],
                             compagnie_cache: Dict[str, str],
                             counts: Dict[str, int]) -> None:
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec50":
            continue
        rows = _read_csv_text(content)
        counts["rec50"] = counts.get("rec50", 0) + len(rows)
        for row in rows:
            pol_exp = row.get("id_polizza_exp")
            pol_id = polizza_id_map.get(pol_exp) if pol_exp else None
            if not pol_id:
                continue
            id_s = row.get("id_sinistro_exp") or _uid()
            contraente_exp = row.get("id_contraente_exp")
            contraente_id = ana_id_map.get(contraente_exp) if contraente_exp else None
            comp_id = await _get_or_create_compagnia(
                db, row.get("compagnia_exp", ""), row.get("compagnia_ania", ""), compagnie_cache,
            )
            stato = _MAP_STATO_SINISTRO.get((row.get("stato_sinistro") or "").lower(), "aperto")
            existing = await db.sinistri.find_one({"id_sinistro_exp": id_s})
            data = {
                "numero_sinistro": row.get("numero_sinistro_cmp") or id_s,
                "polizza_id": pol_id,
                "compagnia_id": comp_id or "",
                "contraente_id": contraente_id or "",
                "data_avvenimento": _parse_date(row.get("data_avvenimento", "")) or _now_iso()[:10],
                "data_denuncia": _parse_date(row.get("data_denuncia", "")) or _now_iso()[:10],
                "luogo": f"{row.get('comune_avvenimento','')} ({row.get('provincia_avvenimento','')})".strip(),
                "ramo": row.get("ramo_sinistro_share") or None,
                "stato": stato,
                "descrizione": row.get("dinamica_sinistro") or None,
                "riserva": _parse_float(row.get("riserva_totale", "")),
                "liquidazione": _parse_float(row.get("liquidazione_totale", "")),
                "id_sinistro_exp": id_s,
                "fonte": "import_ania",
                "updated_at": _now_iso(),
            }
            if existing:
                await db.sinistri.update_one({"id": existing["id"]}, {"$set": data})
            else:
                obj = Sinistro(**data)
                await db.sinistri.insert_one(obj.model_dump())
                log.sinistri_creati += 1


def _conta_record_residui(files_data: Dict[str, str], counts: Dict[str, int]) -> None:
    for fname, content in files_data.items():
        rec = _detect_record_type(fname)
        if rec and rec not in counts:
            counts[rec] = len(_read_csv_text(content))


# ---------------------------------------------------------------------------
# Entrypoint pubblico
# ---------------------------------------------------------------------------
async def importa_zip(db, file_bytes: bytes, filename: str, utente: dict) -> ImportLog:
    """Importa un file ZIP contenente i record ANIA (rec10/20/21/30/40/50)."""
    log = ImportLog(
        utente_id=utente.get("id"),
        nome_file=filename,
        stato="in_corso",
    )
    start = time.time()
    counts: Dict[str, int] = {}
    errors: List[str] = []

    mapping_garanzie = await _load_mapping_garanzie(db)
    mapping_operatori = await _load_mapping_operatori(db)

    files_data = _extract_zip_contents(file_bytes, filename)
    compagnie_cache: Dict[str, str] = {}
    ana_id_map: Dict[str, str] = {}
    polizza_id_map: Dict[str, str] = {}

    # Pipeline ordinata: l'ordine è significativo perché ogni step può
    # riferirsi alle entità create dagli step precedenti.
    await _processa_anagrafiche(db, files_data, log, ana_id_map, compagnie_cache, counts)
    await _processa_polizze(db, files_data, log, ana_id_map, polizza_id_map,
                            compagnie_cache, mapping_operatori, counts)
    await _processa_dettagli_veicolo(db, files_data, polizza_id_map, counts)
    await _processa_garanzie(db, files_data, polizza_id_map, mapping_garanzie, counts)
    await _processa_titoli(db, files_data, log, polizza_id_map, counts)
    await _processa_sinistri(db, files_data, log, polizza_id_map, ana_id_map,
                             compagnie_cache, counts)
    _conta_record_residui(files_data, counts)

    log.record_types_processati = counts
    log.errori = errors
    log.durata_ms = int((time.time() - start) * 1000)
    log.stato = "completato"
    await db.import_logs.insert_one(log.model_dump())
    return log
