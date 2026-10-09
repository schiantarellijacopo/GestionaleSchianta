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
    ProdottoLibreria, RamoLibreria,
)


_MESI_FRAZIONAMENTO = {
    "mensile": 1, "bimestrale": 2, "trimestrale": 3, "quadrimestrale": 4,
    "semestrale": 6, "annuale": 12, "unica": 12,
}


def _scadenza_da_effetto(effetto: Optional[str], frazionamento: Optional[str]) -> Optional[str]:
    """Scadenza rata = effetto + periodo del frazionamento (il flusso OMNIA non
    valorizza sempre la scadenza del titolo: mai usare la data odierna)."""
    if not effetto:
        return None
    import calendar
    mesi = _MESI_FRAZIONAMENTO.get((frazionamento or "annuale").lower(), 12)
    try:
        d = datetime.strptime(effetto, "%Y-%m-%d").date()
    except ValueError:
        return None
    tot = d.month - 1 + mesi
    anno = d.year + tot // 12
    mese = tot % 12 + 1
    giorno = min(d.day, calendar.monthrange(anno, mese)[1])
    return d.replace(year=anno, month=mese, day=giorno).isoformat()


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


async def _register_import_mapping(db, import_mappings, tipo: str, codice: str,
                                   entita_id: str, label: str = "",
                                   flusso: str = "omnia") -> None:
    """Segna un valore di flusso come MAPPATO a un'entità creata dall'import
    (aggiorna la cache in-memory + persiste in import_mappings).

    NB: rispetta i mapping BLOCCATI (impostati manualmente dall'admin o già
    collegati a un'entità reale): non li sovrascrive mai (vedi `_mapping_is_locked`).
    """
    codice = (codice or "").strip()
    if not codice or not entita_id:
        return
    if await _mapping_is_locked(db, tipo, codice, flusso):
        return
    if import_mappings is not None:
        import_mappings.setdefault(tipo, {})[codice] = entita_id
    await db.import_mappings.update_one(
        {"tipo": tipo, "flusso": flusso, "valore_flusso": codice},
        {"$setOnInsert": {"id": _uid(), "tipo": tipo, "flusso": flusso,
                          "valore_flusso": codice, "created_at": _now_iso()},
         "$set": {"entita_id": entita_id, "label_flusso": label or codice,
                  "updated_at": _now_iso()},
         "$inc": {"occorrenze": 1}},
        upsert=True,
    )


async def _mapping_is_locked(db, tipo: str, codice: str, flusso: str = "omnia") -> bool:
    """Un mapping è BLOCCATO (intoccabile dall'import) quando:
      - è stato impostato manualmente dall'admin (`manual=True`), OPPURE
      - il suo `entita_id` punta a un'entità REALE (per i collaboratori: un
        utente NON auto-creato).
    In tal caso l'import non deve più cambiarlo: "una volta impostato resta".
    """
    codice = (codice or "").strip()
    if not codice:
        return False
    m = await db.import_mappings.find_one(
        {"tipo": tipo, "flusso": flusso, "valore_flusso": codice},
        {"_id": 0, "entita_id": 1, "manual": 1},
    )
    if not m:
        return False
    if m.get("manual"):
        return True
    eid = m.get("entita_id")
    if not eid:
        return False
    if tipo == "collaboratore":
        u = await db.users.find_one({"id": eid}, {"_id": 0, "auto_created": 1})
        return bool(u and not u.get("auto_created"))
    # Altri tipi: la sola presenza di un entita_id valido è sufficiente a bloccarlo
    return True


async def _get_or_create_prodotto(db, codice: str, descr: str,
                                  comp_id: Optional[str], ramo: Optional[str],
                                  cache: Dict[str, str]) -> Optional[str]:
    """Crea (o riusa) un Prodotto nella libreria Prodotti dal dizionario rec100."""
    nome = (descr or codice or "").strip()
    if not nome:
        return None
    key = nome.upper()
    if key in cache:
        return cache[key]
    existing = await db.prodotti.find_one({"nome": nome}, {"_id": 0, "id": 1})
    if existing:
        cache[key] = existing["id"]
        return existing["id"]
    obj = ProdottoLibreria(nome=nome, compagnia_id=comp_id or None, ramo=(ramo or None))
    await db.prodotti.insert_one(obj.model_dump())
    cache[key] = obj.id
    return obj.id


async def _get_or_create_ramo(db, ramo_raw: str, cache: Dict[str, str]) -> Optional[str]:
    """Crea (o riusa) un Ramo nella libreria globale Rami e ritorna il NOME di
    destinazione (rispetta la libreria del tenant, seguendo eventuali unioni)."""
    code = (ramo_raw or "").strip().upper()
    if not code or code == "VARIE":
        return None
    if code in cache:
        return cache[code]
    existing = await db.rami.find_one(
        {"codice": code},
        {"_id": 0, "id": 1, "codice": 1, "nome": 1, "unito_in_ramo_id": 1},
    )
    if existing:
        # Segui l'eventuale unione verso il ramo master
        if existing.get("unito_in_ramo_id"):
            master = await db.rami.find_one(
                {"id": existing["unito_in_ramo_id"]},
                {"_id": 0, "codice": 1, "nome": 1},
            )
            if master:
                existing = master
        val = (existing.get("nome") or existing.get("codice") or code).strip()
        cache[code] = val
        return val
    obj = RamoLibreria(codice=code, nome=(ramo_raw or code).strip())
    await db.rami.insert_one(obj.model_dump())
    cache[code] = obj.nome
    return obj.nome


async def _get_or_create_tipologia_sinistro(db, ramo: Optional[str],
                                            cache: Dict[str, str]) -> Optional[str]:
    """Crea (o riusa) una Tipologia Sinistro dal ramo del sinistro importato."""
    nome = (ramo or "").strip()
    if not nome:
        return None
    key = nome.upper()
    if key in cache:
        return cache[key]
    existing = await db.tipologie_sinistri.find_one({"nome": nome}, {"_id": 0, "id": 1})
    if existing:
        cache[key] = existing["id"]
        return existing["id"]
    doc = {
        "id": _uid(), "nome": nome, "categoria": "Import ANIA",
        "richiede_cai": False, "richiede_denuncia": True,
        "attivo": True, "ordine": 100, "fonte": "import_ania",
        "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await db.tipologie_sinistri.insert_one(doc)
    cache[key] = doc["id"]
    return doc["id"]


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
    # Codici tracciato OWEB/SHARE (cod_stato_share)
    "at": "attiva",       # ATtiva
    "st": "annullata",    # STornata / annullata
    "so": "sospesa",      # SOspesa / sostituita
    "sp": "sospesa",      # SosPesa
    "an": "annullata",    # ANnullata
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
    # Regola: ogni anagrafica con Partita IVA è una persona giuridica (azienda),
    # a prescindere dalla presenza del codice fiscale.
    tipo = "persona_giuridica" if (row.get("partita_iva") or "").strip() else "persona_fisica"
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
            piva = (data.get("partita_iva") or "").strip() or None

            query = [{"id_anagrafica_exp": id_exp}]
            if cf:
                query.append({"codice_fiscale": cf})
            if piva:
                query.append({"partita_iva": piva})
            existing = await db.anagrafiche.find_one({"$or": query})

            if existing:
                # Import OMNIA: NON sovrascrivere contatti e collaboratore già presenti
                # (email, PEC, telefono, cellulare, collaboratore). Vengono inseriti solo se mancanti.
                upd = dict(data)
                for _k in ("email", "pec", "telefono", "cellulare", "telefono2", "collaboratore_id"):
                    _ev = existing.get(_k)
                    if (_ev.strip() if isinstance(_ev, str) else _ev):
                        upd.pop(_k, None)
                await db.anagrafiche.update_one({"id": existing["id"]}, {"$set": upd})
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


async def _auto_create_stub_user(db, operatore_codice: str, label: str) -> Optional[str]:
    """Crea uno stub 'collaboratore' in db.users (attivo=False) e ritorna il suo id.

    Usato dall'import quando trova un codice operatore mai visto: al posto di
    chiedere all'admin di mappare manualmente, creiamo subito l'utente
    placeholder — l'admin lo completerà (email/password/attivo) in
    Librerie → Utenti / Collaboratori.
    """
    if not operatore_codice:
        return None
    codice = operatore_codice.strip()
    from database import get_current_user
    from tenant import user_tenant_id
    tid = user_tenant_id(get_current_user())
    # dedup PER TENANT: gli stub sono per-agenzia, non globali.
    existing = await db.users.find_one(
        {"auto_created_from_codice": codice, "agenzia_tenant_id": tid},
        {"_id": 0, "id": 1},
    )
    if existing:
        return existing["id"]
    # slug email placeholder — include il tenant per non collidere con l'indice
    # unique su email quando lo stesso codice esiste in più agenzie.
    slug = "".join(ch if ch.isalnum() else "-" for ch in codice.lower()).strip("-") or "op"
    tid_slug = (tid or "notenant").replace("-", "")[:12]
    email = f"operatore.{slug}.{tid_slug}@import-auto.local"
    # Nome leggibile: label dal flusso o "Operatore <codice>"
    nome_display = (label or "").strip() or f"Operatore {codice}"
    # password_hash con valore fittizio non usabile (l'utente non può loggare
    # finché admin non gli assegna una password vera dal form Utenti).
    user_id = _uid()
    doc = {
        "id": user_id,
        "email": email,
        "name": nome_display,
        "role": "collaboratore",
        "attivo": False,
        "auto_created": True,
        "auto_created_from_codice": codice,
        "accesso_software": False,
        "password_hash": "!DISABLED-IMPORT-AUTO",  # bcrypt-invalid → login impossibile
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    # users NON è tenant-scoped dal wrapper: assegna esplicitamente il tenant.
    if tid:
        doc["agenzia_tenant_id"] = tid
    await db.users.insert_one(doc)
    return user_id


async def _resolve_operatore_codice(db, row: dict,
                                   mapping_operatori: dict,
                                   tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                                   import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> tuple[Optional[str], Optional[str]]:
    """Estrae l'operatore_codice dalla riga e risolve il collaboratore_id.

    Risolve sia via mapping_operatori (legacy) che via import_mappings (nuovo).
    Se non risolto → AUTO-CREA uno stub user (attivo=false) e salva il mapping.
    L'admin poi va in Librerie → Utenti a completare/attivare.
    Ritorna (operatore_codice, collaboratore_id).
    """
    operatore_codice = (row.get("collaboratore_1")
                        or row.get("cod_operatore")
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
        # 🆕 Auto-crea stub user (invece di lasciare la scelta manuale)
        new_user_id = await _auto_create_stub_user(db, operatore_codice, label)
        if new_user_id:
            collaboratore_id = new_user_id
            # Salva subito il mapping così i prossimi import lo risolvono senza
            # ricreare utenti duplicati.
            await db.import_mappings.update_one(
                {"tipo": "collaboratore", "flusso": "omnia", "valore_flusso": operatore_codice},
                {
                    "$setOnInsert": {
                        "id": _uid(),
                        "tipo": "collaboratore", "flusso": "omnia",
                        "valore_flusso": operatore_codice,
                        "created_at": _now_iso(),
                    },
                    "$set": {
                        "entita_id": new_user_id,
                        "label_flusso": label or operatore_codice,
                        "label_programma": label or f"Operatore {operatore_codice}",
                        "auto_created": True,
                        "updated_at": _now_iso(),
                    },
                    "$inc": {"occorrenze": 1},
                },
                upsert=True,
            )
        # Mantiene lo stub legacy per la UI Librerie mapping_operatori
        await _ensure_stub_mapping(db, "mapping_operatori", operatore_codice, label)
    return operatore_codice, collaboratore_id


def _col_at(row: dict, index: int) -> str:
    """Valore della colonna in posizione `index` (0-based) mantenendo l'ordine
    del CSV: usato per le colonne rec20 individuate per lettera (AG, BP)."""
    try:
        keys = list(row.keys())
        return (row.get(keys[index]) or "").strip()
    except (IndexError, AttributeError):
        return ""


def _build_polizza_payload(row: dict, *, numero: str, comp_id: Optional[str],
                           contraente_id: Optional[str], stato: str,
                           operatore_codice: Optional[str], id_exp: str,
                           ramo_mapped: Optional[str] = None,
                           prodotto_mapped: Optional[str] = None) -> dict:
    """Costruisce il dict di payload polizza da una riga rec20."""
    ramo_raw = row.get("ramo_share") or row.get("ramo_cmp") or "VARIE"
    prodotto_raw = row.get("prodotto_cmp") or None
    # rec20 col AG (33ª, index 32) = data annullo → polizza annullata
    data_annullo = _parse_date(row.get("data_annullamento") or row.get("data_annullo")
                               or _col_at(row, 32))
    # rec20 col BP (68ª, index 67) = numero polizza sostituita
    sostituisce = (row.get("numero_polizza_sostituita_1") or row.get("polizza_sostituita")
                   or _col_at(row, 67) or "").strip() or None
    if data_annullo:
        stato = "annullata"
    # rec20 col DK (115ª, index 114) = data emissione
    data_emissione = _parse_date(row.get("data_emissione") or _col_at(row, 114))
    effetto = (_parse_date(row.get("effetto", "")) or data_emissione or _now_iso()[:10])
    frazionamento = _parse_frazionamento(row.get("frazionamento_share", ""))
    payload = {
        "numero_polizza": numero,
        "compagnia_id": comp_id or "",
        "compagnia_codice_exp": (row.get("compagnia_exp") or "").strip() or None,
        "contraente_id": contraente_id or "",
        "ramo": ramo_mapped or ramo_raw,
        "ramo_originale": ramo_raw if ramo_raw and ramo_raw != "VARIE" else None,
        "prodotto": prodotto_mapped or prodotto_raw,
        "prodotto_originale": prodotto_raw,
        "stato": stato,
        "effetto": effetto,
        "data_emissione": data_emissione,
        # Scadenza contratto: rec20 col AK = scadenza_effettiva. Se risulta più
        # vecchia dell'ultimo titolo pagato viene poi allineata da
        # `_aggiorna_scadenza_da_titoli` (post-pass).
        "scadenza": (_parse_date(row.get("scadenza_effettiva", ""))
                     or _parse_date(row.get("scadenza_originale", ""))
                     or _scadenza_da_effetto(effetto, frazionamento)
                     or _now_iso()[:10]),
        # Frazionamento (rec20 col AN — frazionamento_share)
        "frazionamento": frazionamento,
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
    if data_annullo:
        payload["data_annullamento"] = data_annullo
    if sostituisce:
        payload["sostituisce_polizza"] = sostituisce
    return payload


async def _upsert_polizza(db, data: dict, log: ImportLog,
                          polizza_id_map: Dict[str, str], id_exp: str) -> None:
    """Esegue insert o update di una polizza. Matching robusto: prima per
    id_polizza_exp, poi (fallback) per numero_polizza nello stesso tenant — così
    non si creano doppioni quando id_polizza_exp manca o cambia tra import."""
    existing = None
    if id_exp:
        existing = await db.polizze.find_one({"id_polizza_exp": id_exp})
    if not existing and data.get("numero_polizza"):
        # db è già tenant-scoped dal wrapper -> match per numero polizza
        existing = await db.polizze.find_one({"numero_polizza": data["numero_polizza"]})
    if existing:
        # Polizza già presente: sovrascrivi SOLO i dati MANCANTI, senza toccare
        # (né azzerare) i valori già presenti/rettificati manualmente.
        def _vuoto(v):
            return v is None or v == "" or v == [] or v == {}
        # `ramo` e `prodotto` sono guidati dai mapping: se l'import risolve un valore
        # (es. mapping "3N" → "RC AUTO") va aggiornato anche se già presente, così la
        # correzione del mapping si propaga alle polizze già importate.
        _sempre = {"ramo", "prodotto"}
        upd = {}
        for k, v in data.items():
            if k in ("id", "created_at") or _vuoto(v):
                continue
            if _vuoto(existing.get(k)) or (k in _sempre and v != existing.get(k)):
                upd[k] = v
        upd["updated_at"] = _now_iso()
        await db.polizze.update_one({"id": existing["id"]}, {"$set": upd})
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
    rami_cache: Dict[str, str] = {}
    nome_cache_pol: Dict[str, str] = {}
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec20":
            continue
        rows = _read_csv_text(content)
        counts["rec20"] = counts.get("rec20", 0) + len(rows)
        if rows:
            _k = list(rows[0].keys())
            print(f"[OMNIA rec20] col AG (33ª) = '{_k[32] if len(_k) > 32 else '?'}' · "
                  f"col BP (68ª) = '{_k[67] if len(_k) > 67 else '?'}' · tot colonne {len(_k)}", flush=True)
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
            # Se presente una data di annullamento, la polizza NON è attiva:
            # il tracciato OWEB valorizza data_annullamento per storni/sostituzioni/annulli.
            if (row.get("data_annullamento") or "").strip() and stato == "attiva":
                stato = "annullata"
            operatore_codice, collaboratore_id = await _resolve_operatore_codice(
                db, row, mapping_operatori, tracker=tracker, import_mappings=import_mappings,
            )
            # Ramo: derivato PRIMARIAMENTE dal prodotto mappato (i prodotti in
            # libreria hanno già il ramo di appartenenza — collegamento bidirezionale
            # prodotto ↔ ramo). In assenza di prodotto mappato si usa il ramo del
            # tracciato (mapping "ramo" o, come fallback, auto-create in libreria).
            ramo_raw = (row.get("ramo_share") or row.get("ramo_cmp") or "").strip()
            ramo_mapped = None
            if ramo_raw and ramo_raw != "VARIE":
                mapped_ramo_id = (import_mappings or {}).get("ramo", {}).get(ramo_raw)
                if mapped_ramo_id:
                    ramo_doc = await db.rami.find_one(
                        {"id": mapped_ramo_id}, {"_id": 0, "nome": 1, "codice": 1},
                    )
                    if ramo_doc:
                        # Usa il NOME del ramo di destinazione (es. "RC AUTO"),
                        # non il codice grezzo Omnia (es. "3N").
                        ramo_mapped = ramo_doc.get("nome") or ramo_doc.get("codice")
                else:
                    # Ramo non mappato → crea il ramo nella libreria e assegnalo
                    ramo_mapped = await _get_or_create_ramo(db, ramo_raw, rami_cache)
            # Prodotto: se mappato a un prodotto di libreria, usa il suo NOME e
            # DERIVA il ramo della polizza dal ramo assegnato al prodotto
            # (collegamento bidirezionale prodotto → ramo, priorità sul ramo del tracciato).
            prodotto_raw = (row.get("prodotto_cmp") or "").strip()
            prodotto_mapped = None
            if prodotto_raw:
                prodotto_mapped_id = (import_mappings or {}).get("prodotto", {}).get(prodotto_raw)
                if prodotto_mapped_id:
                    prod_doc = await db.prodotti.find_one(
                        {"id": prodotto_mapped_id}, {"_id": 0, "nome": 1, "ramo": 1},
                    )
                    if prod_doc:
                        if prod_doc.get("nome"):
                            prodotto_mapped = prod_doc["nome"]
                        # Ramo dal prodotto → aggancio automatico (priorità).
                        ramo_da_prodotto = (prod_doc.get("ramo") or "").strip()
                        if ramo_da_prodotto:
                            ramo_mapped = ramo_da_prodotto
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
                # Provv. COLLABORATORE calcolata con lo SCHEMA (libreria Sistema provvigionale)
                prov_ops = await _ripartizione_collaboratore(
                    db, collaboratore_id, round(float(data.get("provvigioni") or 0), 2),
                    comp_id, data.get("ramo"),
                    data.get("premio_netto"), data.get("premio_lordo"), nome_cache_pol,
                )
                if prov_ops:
                    data["provvigioni_operatori"] = prov_ops
            await _upsert_polizza(db, data, log, polizza_id_map, id_exp)
            # 🆕 Se l'anagrafica del contraente non ha un collaboratore
            # responsabile, ereditalo dalla polizza appena importata.
            if collaboratore_id and contraente_id:
                await db.anagrafiche.update_one(
                    {
                        "id": contraente_id,
                        "$or": [{"collaboratore_id": None}, {"collaboratore_id": ""},
                                {"collaboratore_id": {"$exists": False}}],
                    },
                    {"$set": {"collaboratore_id": collaboratore_id, "updated_at": _now_iso()}},
                )


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
    """Campi valori economici del veicolo + massimali.

    Massimali dal rec21: col AO = massimale_cose, col AP = massimale_persone.
    Vengono salvati in due campi separati e sovrascritti ad ogni re-import.
    """
    mass_cose = _parse_float(row.get("massimale_cose", ""))
    mass_persone = _parse_float(row.get("massimale_persone", ""))
    # `massimali` (campo legacy usato come fallback per i massimali di garanzia):
    # manteniamo il valore più alto tra cose/persone, con fallback sui massimali
    # unico/sinistro quando i due specifici non sono valorizzati.
    massimale = (max(mass_cose, mass_persone)
                 or _parse_float(row.get("massimale_unico", ""))
                 or _parse_float(row.get("massimale_sinistro", "")))
    return {
        "valore_veicolo": _parse_float(row.get("valore_veicolo", "")),
        "valore_residuo_veicolo": _parse_float(row.get("valore_residuo", "")),
        "valore_accessori": _parse_float(row.get("valore_accessori", "")),
        "massimale_cose": mass_cose or None,
        "massimale_persone": mass_persone or None,
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
        if not pol:
            # I numeri OMNIA hanno zeri iniziali assenti nel gestionale (000585 = 585)
            stripped = numero.lstrip("0")
            if stripped and stripped != numero:
                pol = await db.polizze.find_one({"numero_polizza": stripped}, {"_id": 0, "id": 1})
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
    # ═══ REGOLA UTENTE (import OMNIA) ═══
    # Il flusso OMNIA mette l'SSN DENTRO le imposte della garanzia. L'imposta
    # corretta da mostrare è quindi: imposte_flusso - SSN (es. 41,61 - 19 = 22,61).
    _imp_raw = _parse_float(row.get("imposte") or row.get("tasse", ""))
    _ssn = _parse_float(row.get("ssn", ""))
    return {
        "garanzia": nome_finale,
        "garanzia_originale": descr,
        "codice_ania": codice,
        "netto": _parse_float(row.get("netto_garanzia") or row.get("netto", "")),
        "accessori": _parse_float(row.get("accessori", "")),
        "imposte": round(_imp_raw - _ssn, 2),
        "ssn": _ssn,
        "lordo": _parse_float(row.get("lordo_garanzia") or row.get("lordo", "")),
        "diritti": _parse_float(row.get("diritti", "")),
        "provvigione": _parse_float(row.get("provvigione_garanzia")
                                    or row.get("provvigioni_totali")
                                    or row.get("provvigione", "")),
        "capitale_assicurato": capitale,
    }


def _row_rec42_a_garanzia(g: dict, codice: str, descr: str,
                          nome_finale: Optional[str]) -> dict:
    """Mappa una riga-garanzia rec42 in un dict garanzia, con la STESSA formula
    del titolo:  netto=Y(24), imposte=AA(26)-AC(28), ssn=AC(28), lordo=AB(27),
    provvigione=AF(31). La garanzia 'CIA' (Contributo Imposte Ramo) sposta il suo
    imponibile dal netto alle imposte (come nel calcolo del titolo)."""
    Y = _parse_float(_col_at(g, 24))   # imponibile
    AA = _parse_float(_col_at(g, 26))  # tasse
    AC = _parse_float(_col_at(g, 28))  # ssn
    AB = _parse_float(_col_at(g, 27))  # lordo
    AF = _parse_float(_col_at(g, 31))  # provvigioni_totali
    if (codice or "").strip().upper() == "CIA":
        netto = 0.0
        imposte = round((AA - AC) + Y, 2)
    else:
        netto = round(Y, 2)
        imposte = round(AA - AC, 2)
    return {
        "garanzia": nome_finale,
        "garanzia_originale": descr,
        "codice_ania": codice,
        "netto": netto,
        "accessori": 0.0,
        "imposte": imposte,
        "ssn": round(AC, 2),
        "lordo": round(AB, 2),
        "diritti": 0.0,
        "provvigione": round(AF, 2),
        "capitale_assicurato": 0.0,
    }


async def _processa_garanzie(db, files_data: Dict[str, str],
                             polizza_id_map: Dict[str, str],
                             mapping_garanzie: dict,
                             counts: Dict[str, int],
                             tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                             import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
    """Mappa delle garanzie di polizza — REGOLA UTENTE:
    gli IMPORTI (netto/imposte/ssn/lordo/provvigione) vengono costruiti dal rec42
    (stessa fonte del titolo), prendendo le righe del TITOLO PIÙ RECENTE della
    polizza (annualità corrente). Così il totale garanzie == totale titolo sempre.
    Il rec30 resta usato solo per: massimali/capitali (per codice garanzia),
    diritti, e come FALLBACK per le polizze che in questo flusso non hanno rec42.
    """
    from collections import defaultdict as _dd

    # cache numero_polizza -> pol_id (il rec42 non ha id_polizza_exp)
    num_cache: Dict[str, Optional[str]] = {}

    async def _pol_for(row: dict) -> Optional[str]:
        num = (row.get("numero_polizza_cmp") or "").strip()
        if num in num_cache:
            return num_cache[num]
        pid = await _resolve_polizza_id(db, row, polizza_id_map)
        num_cache[num] = pid
        return pid

    async def _traccia(row: dict):
        """Tracking compagnia + garanzia non mappata; ritorna nome_finale/codice."""
        if tracker is not None and import_mappings is not None:
            await _track_compagnia_da_riga(db, row, tracker, import_mappings)
        codice, descr, key = _estrai_codici_garanzia(row)
        nome_finale = _risolvi_nome_garanzia(key, descr, import_mappings, mapping_garanzie)
        already_mapped = (import_mappings or {}).get("garanzia", {}).get(key)
        if key and key not in mapping_garanzie and not already_mapped:
            await _ensure_stub_mapping(db, "mapping_garanzie", codice or key, descr)
            if tracker is not None:
                await _track_unmapped(db, tracker, "garanzia", key,
                                      label=descr or key, import_mappings=import_mappings)
        return codice, descr, nome_finale

    # ── 1) rec30: capitali/massimali per (pol, codice) + diritti + garanzie fallback ──
    rec30_cap: dict[str, dict[str, float]] = _dd(dict)
    rec30_diritti: dict[str, float] = _dd(float)
    rec30_garanzie: dict[str, list[dict]] = _dd(list)
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec30":
            continue
        rows = _read_csv_text(content)
        counts["rec30"] = counts.get("rec30", 0) + len(rows)
        for row in rows:
            pol_id = await _pol_for(row)
            if not pol_id:
                continue
            codice, descr, nome_finale = await _traccia(row)
            g30 = _row_a_garanzia(row, codice, descr, nome_finale)
            rec30_garanzie[pol_id].append(g30)
            rec30_diritti[pol_id] += g30.get("diritti", 0.0) or 0.0
            cap = g30.get("capitale_assicurato", 0.0) or 0.0
            if codice and cap:
                rec30_cap[pol_id][codice.strip().upper()] = cap

    # ── 2) rec42: righe-garanzia raggruppate per polizza e per titolo ──
    # pol_id -> { id_titolo -> {"eff": "YYYY-MM-DD", "rows": [(g, codice, descr, nome)]} }
    rec42_tit: dict[str, dict[str, dict]] = _dd(dict)
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec42":
            continue
        rows = _read_csv_text(content)
        counts["rec42"] = counts.get("rec42", 0) + len(rows)
        for g in rows:
            pol_id = await _pol_for(g)
            if not pol_id:
                continue
            tid = (_col_at(g, 2) or "").strip()        # id_titolo_exp (col C)
            eff = _parse_date(_col_at(g, 12)) or ""     # effetto_titolo (col M)
            codice, descr, nome_finale = await _traccia(g)
            slot = rec42_tit[pol_id].setdefault(tid, {"eff": "", "rows": []})
            if eff > slot["eff"]:
                slot["eff"] = eff
            slot["rows"].append((g, codice, descr, nome_finale))

    # ── 3) aggiorna le polizze con garanzie del TITOLO PIÙ RECENTE (rec42) ──
    pols_con_rec42: set[str] = set()
    for pol_id, titoli in rec42_tit.items():
        best_tid = max(titoli.keys(), key=lambda t: (titoli[t]["eff"], t))
        garanzie: list[dict] = []
        for g, codice, descr, nome_finale in titoli[best_tid]["rows"]:
            gd = _row_rec42_a_garanzia(g, codice, descr, nome_finale)
            cap = rec30_cap.get(pol_id, {}).get((codice or "").strip().upper(), 0.0)
            if cap:
                gd["capitale_assicurato"] = cap
            garanzie.append(gd)
        netto = round(sum(x["netto"] for x in garanzie), 2)
        imposte = round(sum(x["imposte"] for x in garanzie), 2)
        ssn = round(sum(x["ssn"] for x in garanzie), 2)
        lordo = round(sum(x["lordo"] for x in garanzie), 2)
        provv = round(sum(x["provvigione"] for x in garanzie), 2)
        diritti_tot = rec30_diritti.get(pol_id, 0.0)
        capitale_pol = max((x.get("capitale_assicurato", 0.0) for x in garanzie), default=0.0)
        upd = {
            "garanzie": garanzie,
            "premio_netto": netto, "premio_imposte": imposte, "premio_ssn": ssn,
            "premio_tasse": round(imposte + ssn, 2), "premio_lordo": lordo,
            "provvigioni": provv, "diritti": diritti_tot,
            "garanzie_imposte_scorporate": True, "updated_at": _now_iso(),
        }
        if capitale_pol > 0:
            upd["capitale_assicurato"] = capitale_pol
        await db.polizze.update_one({"id": pol_id}, {"$set": upd})
        pols_con_rec42.add(pol_id)

    # ── 4) FALLBACK rec30 per polizze SENZA rec42 (non perdere garanzie/massimali) ──
    for pol_id, garanzie in rec30_garanzie.items():
        if pol_id in pols_con_rec42:
            continue
        diritti_tot = rec30_diritti.get(pol_id, 0.0)
        capitale_pol = max((g.get("capitale_assicurato", 0.0) for g in garanzie), default=0.0)
        upd = {"garanzie": garanzie, "diritti": diritti_tot,
               "garanzie_imposte_scorporate": True, "updated_at": _now_iso()}
        if capitale_pol > 0:
            upd["capitale_assicurato"] = capitale_pol
        await db.polizze.update_one({"id": pol_id}, {"$set": upd})


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helper: ripartizione provvigione collaboratore via libreria "Sistema provvigionale"
# ---------------------------------------------------------------------------
async def _ripartizione_collaboratore(db, coll_id, provv_totale, compagnia_id,
                                      ramo, premio_netto, premio_lordo, nome_cache):
    """Calcola la quota del collaboratore applicando lo SCHEMA provvigionale della
    libreria (STESSA logica di /provvigioni/riassegna: `_quota_collab_da_schema`).

    IMPORTANTE: per gli schemi "sul premio netto" (es. BS BROKER 4,5% sul netto)
    la quota = netto × % ed è INDIPENDENTE dalla provvigione di agenzia (ΣAF del
    rec42): va calcolata anche quando la provvigione di agenzia è 0.
    Per gli schemi di sola ripartizione (%collaboratore) la quota = % della
    provvigione totale già presente sul titolo.
    Ritorna [] se nessuna quota applicabile."""
    if not coll_id:
        return []
    try:
        import server as _srv  # lazy: evita import circolare (server importa ania_importer)
        schema = await _srv._risolvi_schema_provvigionale(coll_id, compagnia_id, ramo)
        if not schema:
            return []
        quota = _srv._quota_collab_da_schema(
            schema, round(float(provv_totale or 0), 2),
            float(premio_netto or 0), float(premio_lordo or 0))
        quota = round(float(quota or 0), 2)
    except Exception:
        return []
    if quota <= 0:
        return []
    nome = nome_cache.get(coll_id)
    if nome is None:
        u = await db.users.find_one(
            {"id": coll_id}, {"_id": 0, "name": 1, "nome": 1, "cognome": 1}) or {}
        nome = (u.get("name")
                or f"{u.get('cognome', '')} {u.get('nome', '')}".strip()
                or "")
        nome_cache[coll_id] = nome
    return [{"operatore_id": coll_id, "operatore_nome": nome, "provvigione": quota}]


# Processor: rec40 (titoli)
# ---------------------------------------------------------------------------
async def _processa_titoli(db, files_data: Dict[str, str], log: ImportLog,
                           polizza_id_map: Dict[str, str],
                           counts: Dict[str, int],
                           mapping_operatori: Optional[dict] = None,
                           tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                           import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
    fraz_cache: Dict[str, str] = {}
    pol_meta_cache: Dict[str, dict] = {}
    nome_cache: Dict[str, str] = {}
    # ═══ REGOLA UTENTE (import OMNIA) — IMPORTI SOLO DAL rec42 ═══
    # Netto/Tasse/SSN/Lordo/Provvigioni derivano ESCLUSIVAMENTE dal rec42
    # (somma delle righe-garanzia del titolo, collegate per id_titolo_exp, col C/idx 2):
    #   PROVVIGIONI = Σ AF (idx 31, provvigioni_totali)
    #   SSN         = Σ AC (idx 28, ssn)
    #   LORDO       = Σ AB (idx 27, lordo)
    #   NETTO       = Σ Y  (idx 24, imponibile) − Σ(Y della garanzia 'CIA')
    #   TASSE/IMP   = Σ AA (idx 26, tasse) − Σ AC (idx 28, ssn) + Σ(Y 'CIA')
    # La garanzia 'CIA' (col P/idx 15 = cod_garanzia_cmp = "Contributo Imposte Ramo"):
    # il suo imponibile va spostato dal Netto alle Imposte.
    # Se un titolo NON ha righe rec42 → tutti gli importi a 0 (verranno popolati da
    # un re-import successivo quando il rec42 avrà i dati). NESSUN altro rec usato.
    rec42_by_titolo: Dict[str, dict] = {}
    for _fn, _ct in files_data.items():
        if _detect_record_type(_fn) != "rec42":
            continue
        for _g in _read_csv_text(_ct):
            _tid = (_col_at(_g, 2) or "").strip()
            if not _tid:
                continue
            _acc = rec42_by_titolo.setdefault(
                _tid, {"netto": 0.0, "tasse": 0.0, "ssn": 0.0,
                       "lordo": 0.0, "provv": 0.0, "cia": 0.0})
            _acc["netto"] += _parse_float(_col_at(_g, 24))   # Y  imponibile
            _acc["tasse"] += _parse_float(_col_at(_g, 26))   # AA tasse
            _acc["ssn"]   += _parse_float(_col_at(_g, 28))   # AC ssn
            _acc["lordo"] += _parse_float(_col_at(_g, 27))   # AB lordo
            _acc["provv"] += _parse_float(_col_at(_g, 31))   # AF provvigioni_totali
            if (_col_at(_g, 15) or "").strip().upper() == "CIA":
                _acc["cia"] += _parse_float(_col_at(_g, 24))  # Y della riga 'CIA'
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
            # ═══ Importi SOLO dal rec42 (vedi regola in testa alla funzione) ═══
            # Accessori: campo separato, non tra i 5 parametri → resta dal rec40.
            accessori_titolo = _parse_float(_col_at(row, 46))
            _r42 = rec42_by_titolo.get((id_t or "").strip())
            if _r42:
                netto_calc = round(_r42["netto"] - _r42["cia"], 2)
                imposte_eff = round(_r42["tasse"] - _r42["ssn"] + _r42["cia"], 2)
                ssn_eff = round(_r42["ssn"], 2)
                lordo = round(_r42["lordo"], 2)
                provv_agenzia = round(_r42["provv"], 2)
            else:
                # Nessuna riga rec42 per questo titolo → importi a 0.
                # Un re-import successivo li popolerà (titolo resta "da_incassare").
                netto_calc = 0.0
                imposte_eff = 0.0
                ssn_eff = 0.0
                lordo = 0.0
                provv_agenzia = 0.0
            # 🆕 Collaboratore/operatore del titolo: leggi da rec40 (collaboratore_1)
            # o eredita dalla polizza (fallback).
            _op_codice, coll_id_titolo = await _resolve_operatore_codice(
                db, row, mapping_operatori or {},
                tracker=tracker, import_mappings=import_mappings,
            )
            if not coll_id_titolo:
                # Fallback: eredita dalla polizza già importata
                pol_ref = await db.polizze.find_one(
                    {"id": pol_id}, {"_id": 0, "collaboratore_id": 1},
                )
                coll_id_titolo = (pol_ref or {}).get("collaboratore_id") or None
            # Meta polizza (compagnia/ramo) per il calcolo provvigionale da libreria
            if pol_id not in pol_meta_cache:
                pol_meta_cache[pol_id] = await db.polizze.find_one(
                    {"id": pol_id}, {"_id": 0, "compagnia_id": 1, "ramo": 1},
                ) or {}
            _pmeta = pol_meta_cache[pol_id]
            eff_titolo = _parse_date(row.get("effetto_titolo", "")) or _now_iso()[:10]
            if pol_id not in fraz_cache:
                _p = await db.polizze.find_one({"id": pol_id}, {"_id": 0, "frazionamento": 1})
                fraz_cache[pol_id] = (_p or {}).get("frazionamento") or "annuale"
            # Scadenza titolo: il flusso OMNIA, per i rinnovi futuri, mette in
            # `data_scadenza_emesso` la data di emissione dell'avviso (precedente
            # all'effetto). In quel caso è errata → calcola effetto+frazionamento.
            _scad_emesso = _parse_date(row.get("data_scadenza_emesso", ""))
            if _scad_emesso and eff_titolo and _scad_emesso <= eff_titolo:
                # Scadenza valida solo se STRETTAMENTE successiva all'effetto.
                # (OMNIA a volte mette la data di emissione avviso == effetto → errata)
                _scad_emesso = None
            _scadenza_val = (_scad_emesso
                             or _scadenza_da_effetto(eff_titolo, fraz_cache[pol_id])
                             or eff_titolo)

            # ═══ REGOLA IMPORT (richiesta utente) ═══
            # 1) Verifica se il titolo ESISTE già:
            #      - per id_titolo_exp, oppure (fallback) per chiave naturale
            #        polizza + effetto (NON includere la scadenza: se una scadenza
            #        errata è stata poi corretta, la chiave combacia comunque e si
            #        evita di creare un DOPPIONE).
            #    Se esiste → NON fare NULLA (incasso/pagamento/copertura sono
            #    operazioni SEMPRE manuali: non vanno mai toccate dall'import).
            # 2) Se MANCA → crealo SEMPRE come "da_incassare" (mai
            #    incassato/coperto/pagato).
            existing = await db.titoli.find_one({"id_titolo_exp": id_t})
            if not existing:
                existing = await db.titoli.find_one({
                    "polizza_id": pol_id,
                    "effetto": eff_titolo,
                })
            if existing:
                # Titolo già presente. Per NON toccare incassi/pagamenti/versamenti
                # né prime note chiuse o estratti pagati: aggiorna gli IMPORTI solo
                # se il titolo è ancora "da_incassare". Negli altri stati → salta.
                if existing.get("stato") == "da_incassare":
                    upd = {
                        "importo_lordo": lordo,
                        "importo_netto": netto_calc,
                        "imposte": round(imposte_eff, 2),
                        "ssn": round(ssn_eff, 2),
                        "accessori": round(accessori_titolo, 2),
                        "provvigioni": round(provv_agenzia, 2),
                        "updated_at": _now_iso(),
                    }
                    if coll_id_titolo:
                        upd["collaboratore_id"] = coll_id_titolo
                        prov_ops = await _ripartizione_collaboratore(
                            db, coll_id_titolo, round(provv_agenzia, 2),
                            _pmeta.get("compagnia_id"), _pmeta.get("ramo"),
                            netto_calc, lordo, nome_cache,
                        )
                        if prov_ops:
                            upd["provvigioni_operatori"] = prov_ops
                    await db.titoli.update_one({"id": existing["id"]}, {"$set": upd})
                    counts["titoli_aggiornati"] = counts.get("titoli_aggiornati", 0) + 1
                continue

            data = {
                "polizza_id": pol_id,
                "effetto": eff_titolo,
                "scadenza": _scadenza_val,
                "stato": "da_incassare",  # MAI incassato/coperto/pagato: operazione manuale
                "importo_lordo": lordo,
                "importo_netto": netto_calc,
                "imposte": round(imposte_eff, 2),
                "ssn": round(ssn_eff, 2),
                "accessori": round(accessori_titolo, 2),
                "provvigioni": round(provv_agenzia, 2),
                "id_titolo_exp": id_t,
                "fonte": "import_ania",
                "updated_at": _now_iso(),
            }
            if coll_id_titolo:
                data["collaboratore_id"] = coll_id_titolo
                # ═══ Provv. COLLABORATORE calcolata con lo SCHEMA (libreria Sistema provvigionale) ═══
                # La provvigione totale (BD) va in `provvigioni` (agenzia); la quota del
                # collaboratore è derivata dallo schema applicabile e salvata nella ripartizione.
                prov_ops = await _ripartizione_collaboratore(
                    db, coll_id_titolo, round(provv_agenzia, 2),
                    _pmeta.get("compagnia_id"), _pmeta.get("ramo"),
                    netto_calc, lordo, nome_cache,
                )
                if prov_ops:
                    data["provvigioni_operatori"] = prov_ops
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
    tip_cache: Dict[str, str] = {}
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
            # Crea/riusa la tipologia sinistro dal ramo del sinistro
            await _get_or_create_tipologia_sinistro(
                db, row.get("ramo_sinistro_share"), tip_cache)
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


async def _processa_liquidazioni(db, files_data: Dict[str, str],
                                 counts: Dict[str, int]) -> int:
    """rec52 → liquidazioni dei sinistri: col Y (index 24) = data liquidazione,
    col Z (index 25) = importo liquidato. Somma per sinistro e valorizza
    `liquidazione` + `data_liquidazione` (stato → liquidato)."""
    agg: Dict[str, Dict[str, object]] = {}
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec52":
            continue
        rows = _read_csv_text(content)
        counts["rec52"] = counts.get("rec52", 0) + len(rows)
        for row in rows:
            id_s = (row.get("id_sinistro_exp") or "").strip()
            if not id_s:
                continue
            data_liq = _parse_date(_col_at(row, 24))
            importo = _parse_float(_col_at(row, 25))
            cur = agg.setdefault(id_s, {"importo": 0.0, "data": None})
            cur["importo"] = float(cur["importo"]) + (importo or 0.0)
            if data_liq and (not cur["data"] or data_liq > str(cur["data"])):
                cur["data"] = data_liq
    aggiornati = 0
    for id_s, v in agg.items():
        importo = round(float(v["importo"]), 2)
        if not importo and not v["data"]:
            continue
        _set = {"liquidazione": importo, "updated_at": _now_iso()}
        if v["data"]:
            _set["data_liquidazione"] = v["data"]
            _set["stato"] = "liquidato"
        res = await db.sinistri.update_one({"id_sinistro_exp": id_s}, {"$set": _set})
        aggiornati += res.modified_count
    counts["sinistri_liquidati"] = aggiornati
    return aggiornati


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
                             compagnie_cache: Optional[Dict[str, str]] = None,
                             tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                             import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
    """Legge il dizionario prodotti (rec100) e CREA l'entità Prodotto nella
    libreria Prodotti (dedup per nome), mappando il codice di flusso al prodotto
    creato così le polizze vi si agganciano automaticamente."""
    prod_cache: Dict[str, str] = {}
    if compagnie_cache is None:
        compagnie_cache = {}
    for fname, content in files_data.items():
        if _detect_record_type(fname) != "rec100":
            continue
        rows = _read_csv_text(content)
        counts["rec100"] = counts.get("rec100", 0) + len(rows)
        for row in rows:
            # Traccia compagnia anche da rec100 (colonna B compagnia_exp)
            if import_mappings is not None:
                await _track_compagnia_da_riga(db, row, tracker, import_mappings)
            codice = (row.get("codice_prodotto") or "").strip()
            descr = (row.get("descrizione_prodotto") or "").strip()
            if not (codice or descr):
                continue
            comp_id = await _get_or_create_compagnia(
                db, row.get("compagnia_exp", ""), row.get("compagnia_ania", ""),
                compagnie_cache, tracker=tracker, import_mappings=import_mappings,
            )
            prod_id = await _get_or_create_prodotto(db, codice, descr, comp_id, None, prod_cache)
            if prod_id:
                await _register_import_mapping(
                    db, import_mappings, "prodotto", codice or descr, prod_id,
                    label=(descr or codice))


def _collab_tokens(name) -> set:
    """Token normalizzati di un nome collaboratore per confronto fuzzy.
    Uppercase, senza punteggiatura, ignora token corti (iniziali/titoli)."""
    import re as _re
    if not name:
        return set()
    toks = _re.sub(r"[^A-Za-zÀ-ÿ]+", " ", str(name)).upper().split()
    return {t for t in toks if len(t) >= 3}


async def _processa_collaboratori(db, files_data: Dict[str, str],
                                  counts: Dict[str, int],
                                  tracker: Optional[Dict[str, Dict[str, dict]]] = None,
                                  import_mappings: Optional[Dict[str, Dict[str, Optional[str]]]] = None) -> None:
    """Legge il dizionario collaboratori (rec101) e li traccia come "da
    associare" alla libreria Collaboratori (utenti). Se il nome è simile a un
    collaboratore GIÀ esistente (anche scritto in modo diverso), lo UNIFICA
    agganciandolo a quell'utente invece di creare un doppione.
    """
    # Indice collaboratori esistenti: nome normalizzato (set di token) -> user id
    # Ristretto al tenant corrente (users NON è auto-filtrato dal wrapper).
    from database import get_current_user
    from tenant import user_tenant_id
    _tid = user_tenant_id(get_current_user())
    _uflt: dict = {"role": {"$in": ["admin", "collaboratore", "dipendente"]}}
    if _tid:
        _uflt["agenzia_tenant_id"] = _tid
    user_index: list[tuple[set, str]] = []
    async for u in db.users.find(_uflt, {"_id": 0, "id": 1, "name": 1}):
        toks = _collab_tokens(u.get("name"))
        if toks:
            user_index.append((toks, u["id"]))

    async def _match_collaboratore(descr: str) -> Optional[str]:
        toks = _collab_tokens(descr)
        if len(toks) < 2:
            return None
        for utoks, uid in user_index:
            # uguali, oppure uno è sottoinsieme dell'altro (>=2 token in comune)
            if toks == utoks or (len(toks & utoks) >= 2 and (toks <= utoks or utoks <= toks)):
                return uid
        return None

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
            # UNIFICAZIONE: se il nome combacia con un collaboratore esistente,
            # aggancia il codice a quell'utente (niente doppione, niente stub unmapped).
            uid = await _match_collaboratore(descr)
            if uid:
                # Rispetta i mapping bloccati manualmente: l'import non deve
                # sovrascrivere la scelta dell'admin ad ogni re-import.
                if await _mapping_is_locked(db, "collaboratore", codice):
                    continue
                if import_mappings is not None:
                    import_mappings.setdefault("collaboratore", {})[codice] = uid
                await db.import_mappings.update_one(
                    {"tipo": "collaboratore", "flusso": "omnia", "valore_flusso": codice},
                    {"$setOnInsert": {"id": _uid(), "tipo": "collaboratore", "flusso": "omnia",
                                      "valore_flusso": codice, "created_at": _now_iso()},
                     "$set": {"entita_id": uid, "label_flusso": descr or codice, "updated_at": _now_iso()},
                     "$inc": {"occorrenze": 1}},
                    upsert=True,
                )
                continue
            label_parts = [descr or codice]
            if rui:
                label_parts.append(f"RUI: {rui}")
            if cf:
                label_parts.append(f"CF: {cf}")
            label = " · ".join(label_parts)
            # Nessun match con utenti esistenti → CREA il collaboratore (utente
            # stub, ruolo collaboratore, non attivo) e mappalo al codice flusso.
            new_uid = await _auto_create_stub_user(db, codice, descr or codice)
            if new_uid:
                toks = _collab_tokens(descr)
                if toks:
                    user_index.append((toks, new_uid))
                await _register_import_mapping(
                    db, import_mappings, "collaboratore", codice, new_uid, label=label)
            else:
                await _track_unmapped(
                    db, tracker, "collaboratore", codice,
                    label=label, import_mappings=import_mappings,
                )


# ---------------------------------------------------------------------------
# Entrypoint pubblico
# ---------------------------------------------------------------------------
async def _aggiorna_scadenza_da_titoli(db) -> int:
    """Se la scadenza contratto (col AK) è più vecchia dell'ultimo titolo pagato,
    la allinea: cliente che ha pagato nel 2025 → scadenza 2026."""
    scad_max: Dict[str, str] = {}
    async for t in db.titoli.find(
        {"stato": "incassato"},
        {"_id": 0, "polizza_id": 1, "scadenza": 1},
    ):
        pid, sc = t.get("polizza_id"), t.get("scadenza")
        if pid and sc and sc > scad_max.get(pid, ""):
            scad_max[pid] = sc
    n = 0
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "scadenza": 1}):
        sc = scad_max.get(p["id"])
        if sc and sc > (p.get("scadenza") or ""):
            res = await db.polizze.update_one(
                {"id": p["id"]}, {"$set": {"scadenza": sc, "updated_at": _now_iso()}})
            n += res.modified_count
    return n


def _norm_num(s: str) -> str:
    import re as _re
    return _re.sub(r"\D", "", (s or "").strip()).lstrip("0")


async def _riattiva_titoli_sostituenti(db) -> int:
    """PRIMA del processamento titoli, per le catene di sostituzione:
    1) EREDITÀ OPERATORE: se la polizza sostituente non ha collaboratore/operatore,
       lo eredita dalla polizza che sostituisce (così i titoli ricevono la provvigione).
    2) RIATTIVAZIONE: le polizze "testa" della catena (che sostituiscono un'altra e
       non sono a loro volta sostituite) devono avere il proprio titolo ATTIVO: se un
       loro titolo di origine import è 'stornato', lo riporta a 'da_incassare' così il
       passo rec42 lo rivalorizza. (La polizza sostituita verrà stornata dopo.)"""
    docs = []
    sostituiti: set[str] = set()
    num2doc: Dict[str, dict] = {}
    async for p in db.polizze.find(
        {}, {"_id": 0, "id": 1, "numero_polizza": 1, "sostituisce_polizza": 1,
             "collaboratore_id": 1}):
        docs.append(p)
        for k in {(p.get("numero_polizza") or "").strip(), _norm_num(p.get("numero_polizza"))}:
            if k:
                num2doc.setdefault(k, p)
        sp = (p.get("sostituisce_polizza") or "").strip()
        if sp:
            sostituiti.add(sp)
            sostituiti.add(_norm_num(sp))
    n = 0
    for p in docs:
        sp = (p.get("sostituisce_polizza") or "").strip()
        if not sp:
            continue
        # 1) Eredità operatore dalla polizza sostituita (solo se manca)
        if not (p.get("collaboratore_id") or "").strip():
            a = num2doc.get(sp) or num2doc.get(_norm_num(sp))
            if a and (a.get("collaboratore_id") or "").strip():
                await db.polizze.update_one(
                    {"id": p["id"]},
                    {"$set": {"collaboratore_id": a["collaboratore_id"],
                              "updated_at": _now_iso()}})
                p["collaboratore_id"] = a["collaboratore_id"]
        # 2) Riattivazione titoli stornati se è la testa della catena
        numero = (p.get("numero_polizza") or "").strip()
        if numero in sostituiti or _norm_num(numero) in sostituiti:
            continue  # è a sua volta sostituita → NON è la testa della catena
        res = await db.titoli.update_many(
            {"polizza_id": p["id"], "stato": "stornato", "fonte": "import_ania"},
            {"$set": {"stato": "da_incassare", "updated_at": _now_iso()},
             "$unset": {"nota_storno": ""}})
        n += res.modified_count
    return n


async def _marca_polizze_sostituite(db) -> tuple[int, int]:
    """Le polizze citate nel campo `sostituisce_polizza` passano a stato
    'sostituita', con backlink alla polizza che le ha rimpiazzate. Inoltre i loro
    titoli ancora 'da_incassare' vengono STORNATI (il premio della nuova polizza li
    sostituisce). I titoli già incassati/coperti/pagati NON vengono toccati.
    Ritorna (polizze_sostituite, titoli_stornati)."""
    import re as _re
    idx: Dict[str, str] = {}
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1}):
        raw = (p.get("numero_polizza") or "").strip()
        for k in {raw, _re.sub(r"\D", "", raw).lstrip("0")}:
            if k:
                idx.setdefault(k, p["id"])
    n = 0
    stornati = 0
    async for p in db.polizze.find({"sostituisce_polizza": {"$nin": [None, ""]}},
                                   {"_id": 0, "id": 1, "sostituisce_polizza": 1,
                                    "numero_polizza": 1}):
        num = (p.get("sostituisce_polizza") or "").strip()
        old_id = idx.get(num) or idx.get(_re.sub(r"\D", "", num).lstrip("0"))
        if not old_id or old_id == p["id"]:
            continue
        res = await db.polizze.update_one(
            {"id": old_id, "stato": {"$ne": "sostituita"}},
            {"$set": {"stato": "sostituita", "sostituita_da_polizza_id": p["id"],
                      "updated_at": _now_iso()}})
        n += res.modified_count
        nuovo_num = (p.get("numero_polizza") or "").strip()
        res_t = await db.titoli.update_many(
            {"polizza_id": old_id, "stato": "da_incassare"},
            {"$set": {"stato": "stornato",
                      "nota_storno": f"Stornato automaticamente: polizza sostituita da N. {nuovo_num}".strip(),
                      "updated_at": _now_iso()}})
        stornati += res_t.modified_count
    return n, stornati



async def _applica_regola_stato_da_titoli(db, polizza_id_map: Dict[str, str], log: "ImportLog") -> None:
    """Passo 1 (post-import Omnia): ultimo titolo pagato >= 01/01/2025 -> ATTIVA;
    altrimenti ANNULLATA solo se compagnia CATTOLICA. Versione efficiente:
    poche query aggregate invece di N+1."""
    SOGLIA = "2025-01-01"
    pids = list(set(polizza_id_map.values()))
    if not pids:
        return
    # 1) max data_incasso per polizza (titoli incassati) in un'unica aggregazione
    ultimo_map: Dict[str, str] = {}
    async for r in db.titoli.aggregate([
        {"$match": {"polizza_id": {"$in": pids}, "stato": "incassato"}},
        {"$group": {"_id": "$polizza_id", "ultimo": {"$max": "$data_incasso"}}},
    ]):
        if r.get("ultimo"):
            ultimo_map[r["_id"]] = r["ultimo"]
    # 2) id compagnie CATTOLICA (una sola query)
    cattolica_ids = set()
    async for c in db.compagnie.find({"ragione_sociale": {"$regex": "cattolica", "$options": "i"}}, {"_id": 0, "id": 1}):
        cattolica_ids.add(c["id"])
    # 3) polizze da valutare (una query, solo campi utili)
    to_attiva, to_annulla = [], []
    async for p in db.polizze.find({"id": {"$in": pids}}, {"_id": 0, "id": 1, "compagnia_id": 1, "stato": 1}):
        ultimo = ultimo_map.get(p["id"])
        if ultimo and ultimo >= SOGLIA:
            if p.get("stato") != "attiva":
                to_attiva.append(p["id"])
        elif p.get("compagnia_id") in cattolica_ids and p.get("stato") != "annullata":
            to_annulla.append(p["id"])
    if to_attiva:
        await db.polizze.update_many({"id": {"$in": to_attiva}}, {"$set": {"stato": "attiva", "updated_at": _now_iso()}})
    if to_annulla:
        await db.polizze.update_many({"id": {"$in": to_annulla}}, {"$set": {"stato": "annullata", "updated_at": _now_iso()}})



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
    await _processa_prodotti(db, files_data, counts, compagnie_cache=compagnie_cache,
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
    # Sostituzioni (PRIMA dei titoli): riattiva i titoli stornati delle polizze
    # "testa" della catena di sostituzione, così il passo rec42 li rivalorizza.
    counts["titoli_riattivati_sostituzione"] = await _riattiva_titoli_sostituenti(db)
    await _processa_titoli(db, files_data, log, polizza_id_map, counts,
                           mapping_operatori=mapping_operatori,
                           tracker=tracker, import_mappings=import_mappings)
    # Passo 1 (RIMOSSO): la regola che impostava lo stato polizza in base ai titoli
    # (annullamento automatico CATTOLICA / riattivazione da incasso >= 2025) è stata
    # disattivata su richiesta. Gli import non modificano più lo stato della polizza
    # in base ai titoli; resta lo stato del tracciato / quello già presente.
    # (funzione `_applica_regola_stato_da_titoli` mantenuta ma non più invocata)
    _sost_n, _sost_st = await _marca_polizze_sostituite(db)
    counts["polizze_sostituite"] = _sost_n
    counts["titoli_stornati_sostituzione"] = _sost_st
    counts["scadenze_allineate"] = await _aggiorna_scadenza_da_titoli(db)
    await _processa_sinistri(db, files_data, log, polizza_id_map, ana_id_map,
                             compagnie_cache, counts,
                             tracker=tracker, import_mappings=import_mappings)
    await _processa_liquidazioni(db, files_data, counts)
    _conta_record_residui(files_data, counts)

    # Entità non mappate raccolte durante l'import (NB: rami NON sono tracciati:
    # il ramo della polizza deriva dal prodotto mappato — vedi _processa_polizze)
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
