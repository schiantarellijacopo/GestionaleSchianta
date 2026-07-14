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
from typing import Dict, List, Optional, Tuple
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


async def _load_import_mappings(db, flusso: str = "omnia") -> Dict[str, Dict[str, Optional[str]]]:
    """Carica i mapping unificati `import_mappings` raggruppati per tipo.

    Ritorna: {tipo: {valore_flusso: entita_id}}.
    """
    out: Dict[str, Dict[str, Optional[str]]] = {
        "compagnia": {}, "ramo": {}, "prodotto": {},
        "collaboratore": {}, "garanzia": {},
    }
    async for m in db.import_mappings.find({"flusso": flusso}, {"_id": 0}):
        tipo = m.get("tipo")
        valore = (m.get("valore_flusso") or "").strip()
        if tipo in out and valore:
            out[tipo][valore] = m.get("entita_id")
    return out


async def _track_unmapped(db, tracker: Dict[str, Dict[str, dict]], tipo: str,
                          valore: str, label: str = "",
                          import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
                          flusso: str = "omnia") -> None:
    """Registra un valore come "non mappato" se non presente in import_mappings.

    `tracker` è un dict {tipo: {valore: {label, count}}} popolato durante l'import.
    Crea uno stub in `import_mappings` con `entita_id=None` per renderlo visibile nel wizard.

    NB: se chiamato più volte con label diverse per lo stesso (tipo, valore), prevale la
    label *più ricca* (più lunga di quella già registrata) per favorire descrizioni
    estese trovate in flussi successivi (es. rec100 ha la descrizione completa del
    prodotto, mentre rec20 ha solo il codice).
    """
    if not valore:
        return
    valore = valore.strip()
    if not valore:
        return
    mapped = (import_mappings or {}).get(tipo, {})
    if mapped.get(valore):
        return  # già mappato a un'entità
    bucket = tracker.setdefault(tipo, {})
    rec = bucket.setdefault(valore, {"label": label, "count": 0})
    rec["count"] += 1
    # Preferisci la label più lunga (descrizione completa > codice nudo)
    if label and len(label) > len(rec.get("label") or ""):
        rec["label"] = label
    # Crea voce stub in import_mappings (idempotente) così appare nel wizard.
    # Aggiorna label_flusso al valore più lungo finora.
    await db.import_mappings.update_one(
        {"tipo": tipo, "flusso": flusso, "valore_flusso": valore},
        {
            "$setOnInsert": {
                "id": _uid(),
                "tipo": tipo, "flusso": flusso, "valore_flusso": valore,
                "entita_id": None,
                "label_programma": None,
                "created_at": _now_iso(),
            },
            "$set": {
                "label_flusso": rec["label"] or valore,
                "updated_at": _now_iso(),
            },
            "$inc": {"occorrenze": 1},
        },
        upsert=True,
    )


async def _ensure_stub_mapping(db, collection: str, codice: str, descrizione: str = "") -> None:
    """Crea voce stub nella libreria di mapping legacy se non esiste."""
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
    """Esempio: 'rec10oweb.csv' -> 'rec10'. I prefissi più lunghi devono essere
    controllati prima per evitare che 'rec10' matchi anche 'rec100' (idem rec20/rec21).
    """
    name = filename.lower()
    for prefix in ("rec100", "rec101",
                   "rec00", "rec10", "rec21", "rec24", "rec20",
                   "rec40", "rec41", "rec42", "rec43",
                   "rec50", "rec51", "rec52", "rec70",
                   "rec30"):
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


async def _track_compagnia_da_riga(db, row: dict, tracker: Dict[str, Dict[str, dict]],
                                   import_mappings: Dict[str, Dict[str, Optional[str]]]) -> None:
    """Traccia la compagnia di una riga (rec20/30/50/100/101) se non già mappata
    esplicitamente in import_mappings.

    NB: non basta verificare la presenza in `db.compagnie` perché potrebbero esserci
    compagnie "spurie" auto-create da import precedenti che non rappresentano la vera
    libreria. Il vero criterio è "l'utente ha esplicitamente mappato questo codice?".
    """
    codice = (row.get("compagnia_exp") or "").strip()
    if not codice:
        return
    # Salta SOLO se c'è già un mapping esplicito utente (entita_id valorizzato)
    if (import_mappings or {}).get("compagnia", {}).get(codice):
        return
    ania = (row.get("compagnia_ania") or "").strip()
    label = f"{codice} (ANIA {ania})" if ania else codice
    await _track_unmapped(
        db, tracker, "compagnia", codice,
        label=label, import_mappings=import_mappings,
    )



async def _get_or_create_compagnia(db, codice_exp: str, codice_ania: str,
                                   cache: Dict[str, str],
                                   tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                                   import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> str | None:
    if not codice_exp:
        return None
    if codice_exp in cache:
        return cache[codice_exp]
    # Prima: prova a risolvere via import_mappings
    if import_mappings:
        mapped_id = import_mappings.get("compagnia", {}).get(codice_exp)
        if mapped_id:
            cache[codice_exp] = mapped_id
            return mapped_id
    existing = await db.compagnie.find_one({"codice": codice_exp})
    if existing:
        cache[codice_exp] = existing["id"]
        return existing["id"]
    # Non c'è ancora la compagnia: la traccio come "non mappata" (no auto-create)
    if tracker is not None:
        await _track_unmapped(
            db, tracker, "compagnia", codice_exp,
            label=codice_ania or codice_exp,
            import_mappings=import_mappings,
        )
    return None


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

# Mapping frazionamento_share ANIA (rec20 col AN) → valore Polizza.frazionamento
# Codici numerici del flusso ANIA:
#   1 = annuale, 2 = semestrale, 3 = quadrimestrale, 4 = trimestrale,
#   12 = mensile, U/0/9 = unica (una tantum)
_MAP_FRAZIONAMENTO_ANIA = {
    "1": "annuale",
    "2": "semestrale",
    "3": "quadrimestrale",
    "4": "trimestrale",
    "12": "mensile",
    "U": "unica",
    "u": "unica",
    "0": "unica",
    "9": "unica",
    "annuale": "annuale",
    "semestrale": "semestrale",
    "quadrimestrale": "quadrimestrale",
    "trimestrale": "trimestrale",
    "mensile": "mensile",
    "unica": "unica",
}


def _parse_frazionamento(value: str) -> str:
    """Converte frazionamento_share (codice ANIA o testo) in valore normalizzato."""
    v = (value or "").strip()
    return _MAP_FRAZIONAMENTO_ANIA.get(v, _MAP_FRAZIONAMENTO_ANIA.get(v.lower(), "annuale"))


# ---------------------------------------------------------------------------
# Processor: rec10 (anagrafiche)
# ---------------------------------------------------------------------------
async def _build_anagrafica_payload(db, row: dict,
                                    compagnie_cache: Dict[str, str],
                                    tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                                    import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> dict:
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
            tracker=tracker, import_mappings=import_mappings,
        ),
        "fonte": "import_ania",
        "updated_at": _now_iso(),
    }


async def _processa_anagrafiche(db, files_data: Dict[str, str], log: ImportLog,
                                ana_id_map: Dict[str, str],
                                compagnie_cache: Dict[str, str],
                                counts: Dict[str, int],
                                tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                                import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec10":
            continue
        rows = _read_csv_text(content)
        counts["rec10"] = counts.get("rec10", 0) + len(rows)
        for row in rows:
            id_exp = (row.get("id_anagrafica_exp")
                      or row.get("id_anag_inviante")
                      or _uid())
            data = await _build_anagrafica_payload(db, row, compagnie_cache, tracker, import_mappings)
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


async def _resolve_operatore_codice(db, row: dict,
                                   mapping_operatori: dict,
                                   tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                                   import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> tuple[Optional[str], Optional[str]]:
    """Estrae l'operatore_codice dalla riga e risolve il collaboratore_id.

    Risolve sia via mapping_operatori (legacy) che via import_mappings (nuovo).
    Traccia l'operatore come "non mappato" se non risolto.
    Ritorna (operatore_codice, collaboratore_id).
    """
    operatore_codice = (row.get("cod_operatore")
                        or row.get("operatore_share")
                        or row.get("cod_collaboratore")
                        or "").strip() or None
    if not operatore_codice:
        return None, None
    label = row.get("nome_operatore") or row.get("descrizione_operatore") or ""
    # 1) prova import_mappings (nuovo sistema unificato)
    collaboratore_id: Optional[str] = None
    if import_mappings:
        collaboratore_id = import_mappings.get("collaboratore", {}).get(operatore_codice)
    # 2) fallback su mapping_operatori legacy
    if not collaboratore_id:
        collaboratore_id = mapping_operatori.get(operatore_codice)
    if not collaboratore_id:
        # tracking + stub legacy per compatibilità con UI Librerie esistente
        await _ensure_stub_mapping(db, "mapping_operatori", operatore_codice, label)
        if tracker is not None:
            await _track_unmapped(
                db, tracker, "collaboratore", operatore_codice,
                label=label, import_mappings=import_mappings,
            )
    return operatore_codice, collaboratore_id


def _build_polizza_payload(row: dict, *, numero: str, comp_id: Optional[str],
                           contraente_id: Optional[str], stato: str,
                           operatore_codice: Optional[str], id_exp: str,
                           ramo_mapped: Optional[str] = None,
                           prodotto_mapped: Optional[str] = None) -> dict:
    """Costruisce il dict di payload polizza da una riga rec20."""
    ramo_raw = row.get("ramo_share") or row.get("ramo_cmp") or "VARIE"
    prodotto_raw = row.get("prodotto_cmp") or None
    return {
        "numero_polizza": numero,
        "compagnia_id": comp_id or "",
        "compagnia_codice_exp": (row.get("compagnia_exp") or "").strip() or None,
        "contraente_id": contraente_id or "",
        "ramo": ramo_mapped or ramo_raw,
        "ramo_originale": ramo_raw if ramo_raw and ramo_raw != "VARIE" else None,
        "prodotto": prodotto_mapped or prodotto_raw,
        "prodotto_originale": prodotto_raw,
        "stato": stato,
        "effetto": _parse_date(row.get("effetto", "")) or _now_iso()[:10],
        "scadenza": _parse_date(row.get("scadenza_originale", "")) or _now_iso()[:10],
        # Frazionamento (rec20 col AN — frazionamento_share)
        "frazionamento": _parse_frazionamento(row.get("frazionamento_share", "")),
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


async def _upsert_polizza(db, data: dict, log: ImportLog,
                          polizza_id_map: Dict[str, str], id_exp: str) -> None:
    """Esegue insert o update di una polizza in base al matching id_polizza_exp."""
    existing = await db.polizze.find_one({"id_polizza_exp": id_exp})
    if existing:
        await db.polizze.update_one({"id": existing["id"]}, {"$set": data})
        polizza_id_map[id_exp] = existing["id"]
        log.polizze_aggiornate += 1
    else:
        obj = Polizza(**data)
        await db.polizze.insert_one(obj.model_dump())
        polizza_id_map[id_exp] = obj.id
        log.polizze_create += 1


async def _processa_polizze(db, files_data: Dict[str, str], log: ImportLog,
                            ana_id_map: Dict[str, str],
                            polizza_id_map: Dict[str, str],
                            compagnie_cache: Dict[str, str],
                            mapping_operatori: dict,
                            counts: Dict[str, int],
                            tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                            import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
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
                tracker=tracker, import_mappings=import_mappings,
            )
            stato = _MAP_STATO_POLIZZA.get((row.get("cod_stato_share") or "").lower(), "attiva")
            operatore_codice, collaboratore_id = await _resolve_operatore_codice(
                db, row, mapping_operatori, tracker=tracker, import_mappings=import_mappings,
            )
            # Ramo: traccia come entità da mappare nel wizard (Ramo → RamoLibreria).
            # Se già mappato, applica il codice del ramo (es. "3D" → "INFORTUNI").
            ramo_raw = (row.get("ramo_share") or row.get("ramo_cmp") or "").strip()
            ramo_mapped = None
            if ramo_raw and ramo_raw != "VARIE":
                mapped_ramo_id = (import_mappings or {}).get("ramo", {}).get(ramo_raw)
                if mapped_ramo_id:
                    ramo_doc = await db.rami.find_one(
                        {"id": mapped_ramo_id}, {"_id": 0, "codice": 1},
                    )
                    if ramo_doc and ramo_doc.get("codice"):
                        ramo_mapped = ramo_doc["codice"]
                elif tracker is not None:
                    await _track_unmapped(
                        db, tracker, "ramo", ramo_raw,
                        label=ramo_raw, import_mappings=import_mappings,
                    )
            # Traccia prodotto come non mappato (verrà associato manualmente dalla libreria Prodotti)
            prodotto_raw = (row.get("prodotto_cmp") or "").strip()
            prodotto_mapped = None
            if prodotto_raw:
                prodotto_mapped_id = (import_mappings or {}).get("prodotto", {}).get(prodotto_raw)
                if prodotto_mapped_id:
                    # 🔧 FIX: risolvi il NOME del prodotto (non l'UUID)
                    prod_doc = await db.prodotti.find_one(
                        {"id": prodotto_mapped_id}, {"_id": 0, "nome": 1},
                    )
                    if prod_doc and prod_doc.get("nome"):
                        prodotto_mapped = prod_doc["nome"]
                if not prodotto_mapped and tracker is not None:
                    await _track_unmapped(
                        db, tracker, "prodotto", prodotto_raw,
                        label=prodotto_raw, import_mappings=import_mappings,
                    )
            data = _build_polizza_payload(
                row, numero=numero, comp_id=comp_id, contraente_id=contraente_id,
                stato=stato, operatore_codice=operatore_codice, id_exp=id_exp,
                ramo_mapped=ramo_mapped, prodotto_mapped=prodotto_mapped,
            )
            if collaboratore_id:
                data["collaboratore_id"] = collaboratore_id
            await _upsert_polizza(db, data, log, polizza_id_map, id_exp)


# ---------------------------------------------------------------------------
# Processor: rec21 (dettagli veicolo) — funzioni pure di mapping
# ---------------------------------------------------------------------------
def _veicolo_anagrafica(row: dict) -> dict:
    """Identificativi del veicolo: targa, marca, modello, settore, telaio."""
    return {
        "targa": (row.get("targa") or "").strip() or None,
        "veicolo_marca": (row.get("marca") or row.get("marca_veicolo") or "").upper().strip() or None,
        "veicolo_modello": (row.get("modello") or row.get("modello_veicolo") or "").upper().strip() or None,
        "veicolo_settore": (row.get("settore_rca_share") or row.get("tipo_veicolo") or "").strip() or None,
    }


def _veicolo_motorizzazione(row: dict) -> dict:
    """Caratteristiche tecniche motore + corpo: alimentazione, uso, cilindrata, kw, ecc."""
    return {
        "veicolo_alimentazione": (row.get("tp_alimentazione_share") or row.get("alimentazione") or "").strip() or None,
        "veicolo_uso": row.get("uso_rca_share") or row.get("uso_veicolo") or None,
        "veicolo_data_immatricolazione": _parse_date(row.get("data_immatricolazione", "")),
        "veicolo_cilindrata": int(_parse_float(row.get("cilindrata", "")) or 0) or None,
        "veicolo_cv_fiscali": int(_parse_float(row.get("cavalli_fiscali") or row.get("cv_fiscali", "")) or 0) or None,
        "veicolo_kw": _parse_float(row.get("kw", "")),
        "veicolo_quintali": _parse_float(row.get("quintali") or row.get("portata") or ""),
        "veicolo_posti": int(_parse_float(row.get("posti") or row.get("numero_posti", "")) or 0) or None,
    }


def _veicolo_accessori(row: dict) -> dict:
    """Accessori: gancio traino, rimorchio."""
    return {
        "veicolo_gancio_traino": _parse_flag_si(row.get("gancio_traino", "")),
        "veicolo_targa_rimorchio": row.get("targa_rimorchio") or None,
    }


def _campi_veicolo_base(row: dict) -> dict:
    """Campi veicolo: anagrafica + motorizzazione + accessori (vedi rec21 OWEB)."""
    return {**_veicolo_anagrafica(row), **_veicolo_motorizzazione(row), **_veicolo_accessori(row)}


def _campi_tariffa_bm(row: dict) -> dict:
    """Campi tariffa + bonus/malus (classe di merito)."""
    return {
        "tipo_tariffa": row.get("tipo_tariffa_rca_share") or row.get("tipo_tariffa") or None,
        # AC bonus_malus_universale = classe di merito universale (1..18)
        "bm_assegnata": row.get("bonus_malus_universale") or row.get("bm_assegnata") or None,
        "bm_assegnata_cu": row.get("bonus_malus_interna") or row.get("bm_assegnata_cu") or None,
        "bm_provenienza": row.get("bm_provenienza") or None,
        "pejus": _parse_float(row.get("pejus", "")),
        "franchigia": _parse_float(row.get("franchigia_bm") or row.get("franchigia", "")),
    }


def _campi_valori(row: dict) -> dict:
    """Campi valori economici del veicolo + massimale."""
    massimale = (_parse_float(row.get("massimale_unico", ""))
                 or _parse_float(row.get("massimale_sinistro", ""))
                 or _parse_float(row.get("massimale_persone", ""))
                 or _parse_float(row.get("massimale_cose", "")))
    return {
        "valore_veicolo": _parse_float(row.get("valore_veicolo", "")),
        "valore_residuo_veicolo": _parse_float(row.get("valore_residuo", "")),
        "valore_accessori": _parse_float(row.get("valore_accessori", "")),
        "massimali": str(massimale) if massimale else (row.get("massimali") or None),
    }


def _campi_guida(row: dict) -> dict:
    """Campi modalità di guida."""
    return {
        "guida_esperta": _parse_flag_si(row.get("guida_esperta", "")),
        "guida_esclusiva": _parse_flag_si(row.get("guida_esclusiva", "")),
        "rinuncia_rivalsa": _parse_flag_si(row.get("rinuncia_rivalsa", "")),
    }


def _build_dettagli_veicolo(row: dict) -> dict:
    """Compone l'update dei dettagli veicolo aggregando i 4 gruppi di campi.

    Filtra valori "vuoti" (None/""/0) tranne `targa` che è sempre conservato.
    """
    upd = {
        **_campi_veicolo_base(row),
        **_campi_tariffa_bm(row),
        **_campi_valori(row),
        **_campi_guida(row),
        "updated_at": _now_iso(),
    }
    return {k: v for k, v in upd.items() if v not in (None, "", 0, 0.0) or k == "targa"}


async def _resolve_polizza_id(db, row: dict, polizza_id_map: Dict[str, str]) -> Optional[str]:
    """Risolve l'id polizza con fallback su numero_polizza_cmp.

    Logica:
      1. polizza_id_map[id_polizza_exp]  (match della stessa import)
      2. db.polizze.find_one({"numero_polizza": numero_polizza_cmp})  (polizza già in DB)
    """
    pol_exp = (row.get("id_polizza_exp") or "").strip()
    if pol_exp and polizza_id_map.get(pol_exp):
        return polizza_id_map[pol_exp]
    numero = (row.get("numero_polizza_cmp") or "").strip()
    if numero:
        pol = await db.polizze.find_one({"numero_polizza": numero}, {"_id": 0, "id": 1})
        if pol:
            # cache it per le righe successive
            if pol_exp:
                polizza_id_map[pol_exp] = pol["id"]
            return pol["id"]
    return None


async def _processa_dettagli_veicolo(db, files_data: Dict[str, str],
                                     polizza_id_map: Dict[str, str],
                                     counts: Dict[str, int]) -> None:
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec21":
            continue
        rows = _read_csv_text(content)
        counts["rec21"] = counts.get("rec21", 0) + len(rows)
        for row in rows:
            pol_id = await _resolve_polizza_id(db, row, polizza_id_map)
            if not pol_id:
                continue
            upd = _build_dettagli_veicolo(row)
            if upd:
                await db.polizze.update_one({"id": pol_id}, {"$set": upd})


# ---------------------------------------------------------------------------
# Processor: rec30 (garanzie)
# ---------------------------------------------------------------------------
def _estrai_codici_garanzia(row: dict) -> tuple[str, str, str]:
    """Ritorna (codice, descrizione, key) della garanzia dalla riga rec30."""
    codice = (row.get("codice_garanzia")
              or row.get("cod_garanzia_cmp")
              or row.get("codice_garanzia_art20")
              or "").strip().upper()
    descr = (row.get("descrizione_garanzia")
             or row.get("descrizione_garanzia_cmp")
             or row.get("descrizione_garanzia_art20")
             or row.get("garanzia")
             or codice or "").strip()
    key = codice or descr.strip().upper()
    return codice, descr, key


def _risolvi_nome_garanzia(key: str, descr: str,
                           import_mappings: Optional[dict],
                           mapping_garanzie: dict) -> Optional[str]:
    """Risolve il nome finale della garanzia: mappatura utente > nome legacy > descrizione."""
    if import_mappings:
        nome = (import_mappings.get("garanzia") or {}).get(key)
        if nome:
            return nome
    return mapping_garanzie.get(key) or descr


def _row_a_garanzia(row: dict, codice: str, descr: str, nome_finale: Optional[str]) -> dict:
    """Mappa una riga rec30 nel dict garanzia da salvare in polizza.garanzie[]."""
    # Capitale assicurato: rec30 col W = valore_ass_1 (principale). Il flusso ANIA fornisce
    # fino a 3 valori assicurati (valore_ass_1/2/3): prendiamo il max non-zero.
    cap_1 = _parse_float(row.get("valore_ass_1", ""))
    cap_2 = _parse_float(row.get("valore_ass_2", ""))
    cap_3 = _parse_float(row.get("valore_ass_3", ""))
    capitale = max(cap_1, cap_2, cap_3)
    return {
        "garanzia": nome_finale,
        "garanzia_originale": descr,
        "codice_ania": codice,
        "netto": _parse_float(row.get("netto_garanzia") or row.get("netto", "")),
        "accessori": _parse_float(row.get("accessori", "")),
        "imposte": _parse_float(row.get("imposte") or row.get("tasse", "")),
        "ssn": _parse_float(row.get("ssn", "")),
        "lordo": _parse_float(row.get("lordo_garanzia") or row.get("lordo", "")),
        "diritti": _parse_float(row.get("diritti", "")),
        "provvigione": _parse_float(row.get("provvigione_garanzia")
                                    or row.get("provvigioni_totali")
                                    or row.get("provvigione", "")),
        "capitale_assicurato": capitale,
    }


async def _processa_garanzie(db, files_data: Dict[str, str],
                             polizza_id_map: Dict[str, str],
                             mapping_garanzie: dict,
                             counts: Dict[str, int],
                             tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                             import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
    """Processa rec30 (garanzie di polizza). Per ogni riga:
      - traccia compagnia se non mappata
      - risolve la polizza (id_polizza_exp -> map; fallback numero_polizza_cmp)
      - traccia la garanzia non mappata
      - appende al gar_per_pol per la polizza, poi update bulk
    """
    from collections import defaultdict as _dd
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec30":
            continue
        rows = _read_csv_text(content)
        counts["rec30"] = counts.get("rec30", 0) + len(rows)
        gar_per_pol: dict[str, list[dict]] = _dd(list)

        for row in rows:
            if tracker is not None and import_mappings is not None:
                await _track_compagnia_da_riga(db, row, tracker, import_mappings)
            pol_id = await _resolve_polizza_id(db, row, polizza_id_map)
            if not pol_id:
                continue
            codice, descr, key = _estrai_codici_garanzia(row)
            nome_finale = _risolvi_nome_garanzia(key, descr, import_mappings, mapping_garanzie)
            # Stub + tracking se la garanzia non è ancora mappata
            already_mapped = (import_mappings or {}).get("garanzia", {}).get(key)
            if key and key not in mapping_garanzie and not already_mapped:
                await _ensure_stub_mapping(db, "mapping_garanzie", codice or key, descr)
                if tracker is not None:
                    await _track_unmapped(db, tracker, "garanzia", key,
                                          label=descr or key, import_mappings=import_mappings)
            gar_per_pol[pol_id].append(_row_a_garanzia(row, codice, descr, nome_finale))

        # Bulk update per polizza
        for pol_id, garanzie in gar_per_pol.items():
            diritti_tot = sum(g.get("diritti", 0.0) for g in garanzie)
            # Capitale assicurato di polizza = max dei capitali per garanzia
            capitale_pol = max((g.get("capitale_assicurato", 0.0) for g in garanzie), default=0.0)
            update_fields = {"garanzie": garanzie, "diritti": diritti_tot, "updated_at": _now_iso()}
            if capitale_pol > 0:
                update_fields["capitale_assicurato"] = capitale_pol
            await db.polizze.update_one(
                {"id": pol_id},
                {"$set": update_fields},
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
            # 🔧 FIX titoli import ANIA:
            # Il flusso fornisce netto_totale (netto tecnico) + tasse_totale + accessori.
            # L'utente si aspetta: `netto commerciale = lordo - tasse` (visibile in fattura).
            # Ricalcoliamo il netto come lordo - imposte per garantire coerenza al display
            # (netto + imposte = lordo). Le imposte sono le "tasse assicurative" del flusso.
            lordo = _parse_float(row.get("lordo_totale", ""))
            tasse = _parse_float(row.get("tasse_totale") or "")
            imposte_eff = tasse if tasse > 0 else _parse_float(row.get("imposte", ""))
            netto_calc = round(lordo - imposte_eff, 2) if lordo > 0 else 0.0
            # Accessori titolo: rec40 col AU = accessori_totale
            accessori_titolo = _parse_float(row.get("accessori_totale", ""))
            data = {
                "polizza_id": pol_id,
                "effetto": _parse_date(row.get("effetto_titolo", "")) or _now_iso()[:10],
                "scadenza": _parse_date(row.get("data_scadenza_emesso", "")) or _now_iso()[:10],
                "stato": stato,
                "importo_lordo": lordo,
                "importo_netto": netto_calc,
                "imposte": round(imposte_eff, 2),
                "accessori": round(accessori_titolo, 2),
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
                             counts: Dict[str, int],
                             tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                             import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
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
                tracker=tracker, import_mappings=import_mappings,
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
# Processor: rec100 (dizionario prodotti) e rec101 (dizionario collaboratori)
# ---------------------------------------------------------------------------
async def _processa_prodotti(db, files_data: Dict[str, str],
                             counts: Dict[str, int],
                             tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                             import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
    """Legge il dizionario prodotti (rec100) e traccia ciascun prodotto come "da
    associare" alla libreria Prodotti del programma. NON crea entità Prodotto.
    """
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec100":
            continue
        rows = _read_csv_text(content)
        counts["rec100"] = counts.get("rec100", 0) + len(rows)
        if tracker is None:
            continue
        for row in rows:
            # Traccia compagnia anche da rec100 (colonna B compagnia_exp)
            if import_mappings is not None:
                await _track_compagnia_da_riga(db, row, tracker, import_mappings)
            codice = (row.get("codice_prodotto") or "").strip()
            descr = (row.get("descrizione_prodotto") or "").strip()
            if not (codice or descr):
                continue
            valore = codice or descr
            # Label con compagnia se disponibile (es. "Guidamica - Veicoli Autovettura (GPM)")
            comp = (row.get("compagnia_exp") or "").strip()
            label = descr or codice
            if comp and label:
                label = f"{label} ({comp})"
            await _track_unmapped(
                db, tracker, "prodotto", valore,
                label=label, import_mappings=import_mappings,
            )


async def _processa_collaboratori(db, files_data: Dict[str, str],
                                  counts: Dict[str, int],
                                  tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                                  import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
    """Legge il dizionario collaboratori (rec101) e li traccia come "da
    associare" alla libreria Collaboratori (utenti). NON crea utenti.
    """
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec101":
            continue
        rows = _read_csv_text(content)
        counts["rec101"] = counts.get("rec101", 0) + len(rows)
        if tracker is None:
            continue
        for row in rows:
            # Traccia compagnia anche da rec101 (colonna C compagnia_exp)
            if import_mappings is not None:
                await _track_compagnia_da_riga(db, row, tracker, import_mappings)
            codice = (row.get("codice_produttore") or "").strip()
            if not codice:
                continue
            descr = (row.get("descrizione_collaboratore") or "").strip()
            rui = (row.get("cod_rui") or "").strip()
            cf = (row.get("codice_fiscale") or "").strip()
            label_parts = [descr or codice]
            if rui:
                label_parts.append(f"RUI: {rui}")
            if cf:
                label_parts.append(f"CF: {cf}")
            label = " · ".join(label_parts)
            await _track_unmapped(
                db, tracker, "collaboratore", codice,
                label=label, import_mappings=import_mappings,
            )


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
    import_mappings = await _load_import_mappings(db, "omnia")

    files_data = _extract_zip_contents(file_bytes, filename)
    compagnie_cache: Dict[str, str] = {}
    ana_id_map: Dict[str, str] = {}
    polizza_id_map: Dict[str, str] = {}
    # Tracker delle entità incontrate senza un mapping verso un'entità DB
    tracker: Dict[str, Dict[str, dict]] = {}

    # Pipeline ordinata: l'ordine è significativo perché ogni step può
    # riferirsi alle entità create dagli step precedenti.
    # rec100/101 (dizionari) vengono processati PRIMA delle polizze in modo che,
    # quando le polizze tracciano un codice prodotto/collaboratore, la descrizione
    # completa sia già disponibile (rec100 colonna J descrizione_prodotto).
    await _processa_prodotti(db, files_data, counts,
                             tracker=tracker, import_mappings=import_mappings)
    await _processa_collaboratori(db, files_data, counts,
                                  tracker=tracker, import_mappings=import_mappings)
    await _processa_anagrafiche(db, files_data, log, ana_id_map, compagnie_cache, counts,
                                tracker=tracker, import_mappings=import_mappings)
    await _processa_polizze(db, files_data, log, ana_id_map, polizza_id_map,
                            compagnie_cache, mapping_operatori, counts,
                            tracker=tracker, import_mappings=import_mappings)
    await _processa_dettagli_veicolo(db, files_data, polizza_id_map, counts)
    await _processa_garanzie(db, files_data, polizza_id_map, mapping_garanzie, counts,
                             tracker=tracker, import_mappings=import_mappings)
    await _processa_titoli(db, files_data, log, polizza_id_map, counts)
    await _processa_sinistri(db, files_data, log, polizza_id_map, ana_id_map,
                             compagnie_cache, counts,
                             tracker=tracker, import_mappings=import_mappings)
    _conta_record_residui(files_data, counts)

    # Entità non mappate raccolte durante l'import (NB: rami NON sono tracciati per scelta utente)
    plural = {
        "compagnia": "compagnie", "prodotto": "prodotti",
        "collaboratore": "collaboratori", "garanzia": "garanzie",
    }
    entita_non_mappate: dict = {}
    for tipo, items in tracker.items():
        if not items:
            continue
        key = plural.get(tipo, tipo)
        entita_non_mappate[key] = [
            {"valore": v, "label": rec.get("label") or v, "count": rec.get("count", 0)}
            for v, rec in sorted(items.items())
        ]
    log.entita_non_mappate = entita_non_mappate
    log.record_types_processati = counts
    log.errori = errors
    log.durata_ms = int((time.time() - start) * 1000)
    log.stato = "completato"
    await db.import_logs.insert_one(log.model_dump())
    return log
