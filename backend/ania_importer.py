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


async def importa_zip(db, file_bytes: bytes, filename: str, utente: dict) -> ImportLog:
    """Importa un file ZIP contenente i record ANIA."""
    log = ImportLog(
        utente_id=utente.get("id"),
        nome_file=filename,
        stato="in_corso",
    )
    start = time.time()
    counts: Dict[str, int] = {}
    errors: List[str] = []

    files_data: Dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            for member in zf.namelist():
                if not member.lower().endswith(".csv"):
                    continue
                with zf.open(member) as f:
                    raw = f.read()
                    # ANIA è in UTF-8, fallback latin-1
                    try:
                        text = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        text = raw.decode("latin-1")
                    files_data[member] = text
    except zipfile.BadZipFile:
        # potrebbe essere un singolo CSV
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")
        files_data[filename] = text

    # 1) Compagnie da rec00 / rec100 / inferite dai rec20
    compagnie_cache: Dict[str, str] = {}  # codice_compagnia_exp -> compagnia_id

    async def get_or_create_compagnia(codice_exp: str, codice_ania: str = "") -> str | None:
        if not codice_exp:
            return None
        if codice_exp in compagnie_cache:
            return compagnie_cache[codice_exp]
        existing = await db.compagnie.find_one({"codice": codice_exp})
        if existing:
            compagnie_cache[codice_exp] = existing["id"]
            return existing["id"]
        comp = Compagnia(
            codice=codice_exp,
            ragione_sociale=codice_exp or f"Compagnia {codice_ania}",
            descrizione=f"Compagnia ANIA {codice_ania}" if codice_ania else None,
        )
        doc = comp.model_dump()
        await db.compagnie.insert_one(doc)
        compagnie_cache[codice_exp] = comp.id
        return comp.id

    # 2) Anagrafiche (rec10)
    ana_id_map: Dict[str, str] = {}  # id_anagrafica_exp -> anagrafica.id

    for fname, content in files_data.items():
        rec = _detect_record_type(fname)
        if rec != "rec10":
            continue
        rows = _read_csv_text(content)
        counts["rec10"] = counts.get("rec10", 0) + len(rows)
        for row in rows:
            id_exp = row.get("id_anagrafica_exp") or row.get("id_anag_inviante") or _uid()
            ragione = row.get("ragione_sociale") or f"Anagrafica {id_exp}"
            cf = row.get("codice_fiscale") or None
            existing = await db.anagrafiche.find_one(
                {"$or": [
                    {"id_anagrafica_exp": id_exp},
                    {"codice_fiscale": cf} if cf else {"_id": "__none__"},
                ]}
            )
            comp_id = await get_or_create_compagnia(
                row.get("compagnia_exp", ""), row.get("compagnia_ania", "")
            )
            tipo = "persona_giuridica" if row.get("partita_iva") and not cf else "persona_fisica"
            data_consenso = _parse_date(row.get("data_consenso_privacy", ""))
            data = {
                "tipo": tipo,
                "ragione_sociale": ragione,
                "codice_fiscale": cf,
                "partita_iva": row.get("partita_iva") or None,
                "data_nascita": _parse_date(row.get("data_nascita", "")),
                "comune_nascita": row.get("comune_nascita") or None,
                "provincia_nascita": row.get("provincia_nascita") or None,
                "sesso": (row.get("sesso_share") or "").upper()[:1] if row.get("sesso_share") in ("M", "F") else None,
                "indirizzo": row.get("indirizzo") or None,
                "comune": row.get("comune") or None,
                "provincia": row.get("provincia") or None,
                "cap": row.get("cap") or None,
                "nazione": row.get("nazione") or "ITALIA",
                "telefono": row.get("numero_telefono") or None,
                "cellulare": row.get("cellulare") or None,
                "email": row.get("email") or None,
                "iban": row.get("iban") or None,
                "consenso_privacy": (row.get("consenso_privacy") or "").upper() in ("S", "SI", "Y", "1"),
                "data_consenso_privacy": data_consenso,
                "id_anagrafica_exp": id_exp,
                "compagnia_id": comp_id,
                "fonte": "import_ania",
                "updated_at": _now_iso(),
            }
            if existing:
                await db.anagrafiche.update_one({"id": existing["id"]}, {"$set": data})
                ana_id_map[id_exp] = existing["id"]
                log.anagrafiche_aggiornate += 1
            else:
                obj = Anagrafica(**data)
                await db.anagrafiche.insert_one(obj.model_dump())
                ana_id_map[id_exp] = obj.id
                log.anagrafiche_create += 1

    # 3) Polizze (rec20)
    polizza_id_map: Dict[str, str] = {}

    for fname, content in files_data.items():
        rec = _detect_record_type(fname)
        if rec != "rec20":
            continue
        rows = _read_csv_text(content)
        counts["rec20"] = counts.get("rec20", 0) + len(rows)
        for row in rows:
            id_exp = row.get("id_polizza_exp") or _uid()
            numero = row.get("numero_polizza_cmp") or id_exp
            contraente_exp = row.get("id_anagrafica_exp")
            contraente_id = ana_id_map.get(contraente_exp) if contraente_exp else None
            if not contraente_id and contraente_exp:
                # crea anagrafica placeholder
                ph = Anagrafica(
                    ragione_sociale=f"Anagrafica {contraente_exp}",
                    id_anagrafica_exp=contraente_exp,
                    fonte="import_ania",
                )
                await db.anagrafiche.insert_one(ph.model_dump())
                ana_id_map[contraente_exp] = ph.id
                contraente_id = ph.id
                log.anagrafiche_create += 1
            comp_id = await get_or_create_compagnia(row.get("compagnia_exp", ""), row.get("compagnia_ania", ""))
            stato_raw = (row.get("cod_stato_share") or "").lower()
            stato = {
                "a": "attiva", "attiva": "attiva",
                "s": "sospesa", "sospesa": "sospesa",
                "x": "annullata", "annullata": "annullata",
                "e": "scaduta", "scaduta": "scaduta",
            }.get(stato_raw, "attiva")
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
                "provvigioni": _parse_float(row.get("provvigioni_totali", "")),
                "id_polizza_exp": id_exp,
                "fonte": "import_ania",
                "updated_at": _now_iso(),
            }
            if existing:
                await db.polizze.update_one({"id": existing["id"]}, {"$set": data})
                polizza_id_map[id_exp] = existing["id"]
                log.polizze_aggiornate += 1
            else:
                obj = Polizza(**data)
                await db.polizze.insert_one(obj.model_dump())
                polizza_id_map[id_exp] = obj.id
                log.polizze_create += 1

    # rec21 -> aggiorna targa su polizze RCA
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
            targa = row.get("targa") or None
            if targa:
                await db.polizze.update_one({"id": pol_id}, {"$set": {"targa": targa, "updated_at": _now_iso()}})

    # 4) Titoli (rec40)
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
            stato_raw = (row.get("stato_share") or "").lower()
            stato = {
                "i": "incassato", "incassato": "incassato",
                "d": "da_incassare", "da_incassare": "da_incassare",
                "n": "insoluto", "insoluto": "insoluto",
                "s": "stornato", "stornato": "stornato",
            }.get(stato_raw, "da_incassare")
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

    # 5) Sinistri (rec50)
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
            comp_id = await get_or_create_compagnia(row.get("compagnia_exp", ""), row.get("compagnia_ania", ""))
            stato_raw = (row.get("stato_sinistro") or "").lower()
            stato = {
                "a": "aperto", "aperto": "aperto",
                "i": "in_istruttoria", "in_istruttoria": "in_istruttoria",
                "l": "liquidato", "liquidato": "liquidato",
                "c": "chiuso_senza_seguito", "chiuso": "chiuso_senza_seguito",
                "r": "respinto", "respinto": "respinto",
            }.get(stato_raw, "aperto")
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

    # conta tutti gli altri record types (informativo)
    for fname, content in files_data.items():
        rec = _detect_record_type(fname)
        if rec and rec not in counts:
            rows = _read_csv_text(content)
            counts[rec] = len(rows)

    log.record_types_processati = counts
    log.errori = errors
    log.durata_ms = int((time.time() - start) * 1000)
    log.stato = "completato"
    await db.import_logs.insert_one(log.model_dump())
    return log
