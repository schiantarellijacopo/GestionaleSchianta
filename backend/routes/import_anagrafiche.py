"""Excel/CSV smart importer per Anagrafiche.

Endpoint:
  POST /api/import/anagrafiche/preview  → analizza file, autodetect mapping
  POST /api/import/anagrafiche/execute  → esegue import con mapping confermato

Auto-mapping intelligente:
  Riconosce varianti IT/EN degli header (es "Codice Fiscale", "CF", "cod.fisc")
  e li mappa ai campi canonici di Anagrafica (codice_fiscale, ragione_sociale, ...).
  Usa fuzzy scoring (rapidfuzz-like, senza dipendenze) su string normalizzata.
"""
import io
import re
import unicodedata
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import pandas as pd

from database import db
from auth import require_user
from shared import log_attivita

router = APIRouter(prefix="/import/anagrafiche", tags=["import-anagrafiche"])

# ============================================================
# Dizionario campi canonici Anagrafica + varianti header comuni
# ============================================================
# Ordine importante: primo match vince. Le varianti sono normalizzate (lower, no
# accenti, no punteggiatura) prima del confronto.
FIELD_ALIASES: dict = {
    # tipo (persona_fisica / persona_giuridica)
    "tipo": ["tipo", "tipologia", "tipo cliente", "tipo anagrafica"],
    # ragione sociale
    "ragione_sociale": [
        "ragione sociale", "ragionesociale", "rag soc", "rag.soc.", "rag sociale",
        "denominazione", "azienda", "nominativo", "cliente", "cliente/azienda",
        "intestatario", "descrizione",
    ],
    # nome / cognome
    "nome": ["nome", "first name", "given name"],
    "cognome": ["cognome", "surname", "last name", "family name"],
    # CF
    "codice_fiscale": [
        "codice fiscale", "cod fiscale", "cod. fiscale", "cod fisc", "cod.fisc",
        "cf", "c.f.", "codicefiscale", "fiscal code", "tax code",
    ],
    # P.IVA
    "partita_iva": [
        "partita iva", "part iva", "part. iva", "piva", "p.iva", "p iva", "vat",
        "vat number", "partitaiva", "iva",
    ],
    # data nascita
    "data_nascita": [
        "data di nascita", "data nascita", "datadi nascita", "birth date",
        "date of birth", "dob", "nato il", "nata il", "nato/a il",
    ],
    "sesso": ["sesso", "genere", "sex", "gender", "m/f"],
    # nascita
    "comune_nascita": [
        "comune di nascita", "comune nascita", "luogo di nascita", "luogo nascita",
        "citta di nascita", "citta nascita", "nato a", "nata a",
    ],
    "provincia_nascita": ["provincia di nascita", "provincia nascita", "prov nascita"],
    # contatti
    "email": ["email", "e-mail", "e mail", "posta elettronica", "mail"],
    "cellulare": ["cellulare", "cell", "mobile", "cell.", "telefono cellulare", "numero cellulare"],
    "telefono": ["telefono", "tel", "tel.", "numero telefono", "phone", "fisso", "telefono fisso"],
    # residenza
    "indirizzo": [
        "indirizzo", "via", "residenza", "indirizzo residenza", "indirizzo di residenza",
        "address", "street", "via/piazza",
    ],
    "comune": [
        "comune", "citta", "città", "comune residenza", "comune di residenza",
        "city", "località", "localita",
    ],
    "provincia": ["provincia", "prov", "prov.", "province"],
    "cap": ["cap", "codice postale", "postal code", "zip", "zip code"],
    "nazione": ["nazione", "stato", "country", "paese"],
    # documento
    "numero_documento": [
        "numero documento", "n documento", "n. documento", "numero doc", "n doc",
        "documento", "num documento", "id document number",
    ],
    "data_rilascio": ["data rilascio", "rilascio", "data di rilascio", "issue date"],
    "data_scadenza": ["data scadenza", "scadenza", "data di scadenza", "expiry date", "scadenza doc"],
    "comune_emissione": ["comune emissione", "luogo emissione", "rilasciato da", "rilasciato a"],
    # professione
    "professione": ["professione", "occupazione", "job", "profession", "attivita", "attività"],
    "tipologia_lavoratore": [
        "tipologia lavoratore", "tipo lavoratore", "categoria lavoratore",
        "dipendente/autonomo", "lavoratore",
    ],
    # note
    "note": ["note", "notes", "annotazioni", "commenti", "memo"],
    # IBAN (verrà messo in conti_correnti[0].iban se presente)
    "iban": ["iban", "iban conto corrente", "coordinate bancarie"],
}


def _normalize_header(s: str) -> str:
    """Normalizza un header: lowercase, no accenti, no punteggiatura, spazi singoli."""
    if not s:
        return ""
    s = str(s).strip().lower()
    # rimuovi accenti (à → a, è → e, ...)
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    # rimuovi punteggiatura e caratteri non alfanumerici (sostituisci con spazio)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    # comprimi spazi
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _similarity(a: str, b: str) -> float:
    """Similarity ratio semplice basato su token overlap + prefix match.
    Ritorna score 0..1.
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.85
    tok_a = set(a.split())
    tok_b = set(b.split())
    if not tok_a or not tok_b:
        return 0.0
    inter = tok_a & tok_b
    if not inter:
        return 0.0
    union = tok_a | tok_b
    return len(inter) / len(union)


def _detect_mapping(headers: List[str]) -> dict:
    """Per ogni header input, trova il campo canonico più simile (o None se sotto soglia).

    Ritorna:
      {
        "detected": [{"header": str, "index": int, "canonical": str|None, "confidence": float}],
        "reverse": {"canonical_field": header_originale}  # solo campi trovati
      }
    """
    detected = []
    reverse: dict = {}
    used_canonical: set = set()  # evita di mappare due colonne allo stesso campo

    for idx, h in enumerate(headers):
        norm = _normalize_header(h)
        best: Optional[str] = None
        best_score = 0.0
        for canonical, aliases in FIELD_ALIASES.items():
            if canonical in used_canonical:
                continue
            for alias in aliases:
                score = _similarity(norm, _normalize_header(alias))
                if score > best_score:
                    best_score = score
                    best = canonical
        # soglia minima: 0.6 (evita false positive)
        if best and best_score >= 0.6:
            detected.append({
                "header": str(h), "index": idx,
                "canonical": best, "confidence": round(best_score, 2),
            })
            used_canonical.add(best)
            reverse[best] = str(h)
        else:
            detected.append({
                "header": str(h), "index": idx,
                "canonical": None, "confidence": 0.0,
            })
    return {"detected": detected, "reverse": reverse}


def _read_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Legge un file .xlsx/.xls/.csv e ritorna un DataFrame."""
    fn = (filename or "").lower()
    buf = io.BytesIO(file_bytes)
    if fn.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(buf, dtype=str, keep_default_na=False)
    # CSV: prova encoding utf-8 poi latin-1, delimiter autodetect
    try:
        return pd.read_csv(buf, sep=None, engine="python", dtype=str, keep_default_na=False)
    except UnicodeDecodeError:
        buf.seek(0)
        try:
            return pd.read_csv(buf, sep=None, engine="python", dtype=str,
                               keep_default_na=False, encoding="latin-1")
        except Exception as e:
            raise HTTPException(400, f"Impossibile leggere CSV: {e}")


def _sanitize_value(v) -> Optional[str]:
    """Pulisce un valore letto dal foglio."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    return s


def _row_to_anagrafica(row_values: dict, mapping: dict) -> dict:
    """Data una riga (dict header→value) e mapping {header: canonical},
    ritorna un dict Anagrafica pulito.
    """
    ana: dict = {}
    for header, canonical in mapping.items():
        if not canonical:
            continue
        raw = row_values.get(header)
        val = _sanitize_value(raw)
        if val is None:
            continue
        # normalizzazioni per campo
        if canonical in ("codice_fiscale", "partita_iva"):
            val = val.upper().replace(" ", "")
        elif canonical in ("email",):
            val = val.lower()
        elif canonical in ("nome", "cognome", "ragione_sociale", "indirizzo",
                            "comune", "provincia", "comune_nascita",
                            "comune_emissione", "provincia_nascita"):
            val = val.upper()
        elif canonical in ("data_nascita", "data_rilascio", "data_scadenza"):
            val = _parse_date_flexible(val)
            if val is None:
                continue
        elif canonical == "sesso":
            v0 = val.upper()[:1]
            val = "M" if v0 == "M" else ("F" if v0 == "F" else None)
            if val is None:
                continue
        elif canonical == "cap":
            val = re.sub(r"\D", "", val)[:5] or None
            if not val:
                continue
        elif canonical == "iban":
            # IBAN va in conti_correnti[0], non è direttamente un campo top-level
            val = val.upper().replace(" ", "")
            ana.setdefault("conti_correnti", []).append({
                "iban": val, "principale": True,
                "intestazione": None, "banca_ragione_sociale": None,
                "banca_abi": None, "banca_cab": None, "banca_bic": None,
                "note": "Importato da Excel",
            })
            continue
        ana[canonical] = val

    # Se manca tipo, deducilo: se P.IVA presente e no CF di persona fisica → giuridica
    if "tipo" not in ana or ana["tipo"] not in ("persona_fisica", "persona_giuridica"):
        piva = ana.get("partita_iva")
        cf = ana.get("codice_fiscale") or ""
        if piva and len(cf) != 16:
            ana["tipo"] = "persona_giuridica"
        else:
            ana["tipo"] = "persona_fisica"

    # Ragione sociale: se manca ed è PF, componi da nome+cognome
    if not ana.get("ragione_sociale"):
        rs = f"{ana.get('cognome') or ''} {ana.get('nome') or ''}".strip()
        if rs:
            ana["ragione_sociale"] = rs
    return ana


def _parse_date_flexible(s: str) -> Optional[str]:
    """Prova diversi formati date italiani/inglesi. Ritorna ISO yyyy-mm-dd."""
    if not s:
        return None
    s = str(s).strip()
    # gia' ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y",
        "%m/%d/%Y", "%m-%d-%Y",
        "%Y/%m/%d", "%Y.%m.%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s.split(" ")[0], fmt).date().isoformat()
        except Exception:
            continue
    return None


# ============================================================
# ENDPOINTS
# ============================================================
@router.post("/preview")
async def preview_import_anagrafiche(
    file: UploadFile = File(...),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Analizza un file Excel/CSV e restituisce:
      - headers rilevati (con auto-mapping suggerito)
      - prime 10 righe di anteprima (dict con dati grezzi + dati normalizzati)
      - conteggi duplicati stimati (via CF/P.IVA)
    """
    content = await file.read()
    if not content:
        raise HTTPException(400, "File vuoto")
    df = _read_dataframe(content, file.filename)
    if df.empty:
        return {"headers": [], "detected": [], "rows": [], "total_rows": 0, "duplicates_stimati": 0}

    headers = [str(h) for h in df.columns]
    mapping = _detect_mapping(headers)

    # Prime 10 righe (dict header→value grezzo + campo normalizzato)
    map_headers = {d["header"]: d["canonical"] for d in mapping["detected"]}
    preview_rows = []
    for _, row in df.head(10).iterrows():
        row_dict = {h: _sanitize_value(row[h]) for h in headers}
        normalized = _row_to_anagrafica(row_dict, map_headers)
        preview_rows.append({"raw": row_dict, "normalized": normalized})

    # Conta duplicati stimati (persone con CF/P.IVA già presenti)
    dup_count = 0
    cfs = set()
    pivas = set()
    for _, row in df.iterrows():
        row_dict = {h: _sanitize_value(row[h]) for h in headers}
        norm = _row_to_anagrafica(row_dict, map_headers)
        if norm.get("codice_fiscale"):
            cfs.add(norm["codice_fiscale"])
        if norm.get("partita_iva"):
            pivas.add(norm["partita_iva"])
    if cfs:
        dup_count += await db.anagrafiche.count_documents({"codice_fiscale": {"$in": list(cfs)}})
    if pivas:
        dup_count += await db.anagrafiche.count_documents({
            "partita_iva": {"$in": list(pivas)},
            "codice_fiscale": {"$nin": list(cfs)} if cfs else {"$exists": True},
        })

    return {
        "filename": file.filename,
        "headers": headers,
        "detected": mapping["detected"],
        "reverse_mapping": mapping["reverse"],
        "rows": preview_rows,
        "total_rows": int(len(df)),
        "duplicates_stimati": dup_count,
        "available_fields": list(FIELD_ALIASES.keys()),
    }


@router.post("/execute")
async def execute_import_anagrafiche(
    file: UploadFile = File(...),
    mapping_json: str = Form(...),   # JSON: {"header_originale": "canonical_field", ...}
    policy: str = Form("skip"),      # "skip" | "overwrite" | "create_only"
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Esegue l'import con il mapping confermato dall'utente.

    Policy:
      - "skip": se esiste duplicato (per CF o P.IVA), salta la riga.
      - "overwrite": se esiste, aggiorna (UPDATE); altrimenti crea.
      - "create_only": crea SEMPRE (anche in presenza di duplicati) — sconsigliato.
    """
    import json as _json
    try:
        mapping = _json.loads(mapping_json)
    except Exception:
        raise HTTPException(400, "mapping_json non valido")
    if not isinstance(mapping, dict):
        raise HTTPException(400, "mapping_json deve essere un oggetto {header: campo}")

    if policy not in ("skip", "overwrite", "create_only"):
        raise HTTPException(400, "policy non valida")

    content = await file.read()
    df = _read_dataframe(content, file.filename)
    if df.empty:
        return {"created": 0, "updated": 0, "skipped": 0, "errors": [], "total_rows": 0}

    headers = [str(h) for h in df.columns]
    created = 0
    updated = 0
    skipped = 0
    errors: List[dict] = []
    ids_toccati: List[str] = []

    from db_models import Anagrafica

    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            row_dict = {h: _sanitize_value(row[h]) for h in headers}
            ana = _row_to_anagrafica(row_dict, mapping)
            if not ana.get("ragione_sociale") and not ana.get("codice_fiscale") and not ana.get("partita_iva"):
                skipped += 1
                errors.append({"row": int(idx) + 2, "reason": "riga vuota (no ragione_sociale/CF/P.IVA)"})
                continue

            # Cerca duplicato
            existing = None
            if ana.get("tipo") == "persona_giuridica" and ana.get("partita_iva"):
                existing = await db.anagrafiche.find_one({"partita_iva": ana["partita_iva"]}, {"_id": 0, "id": 1})
            if not existing and ana.get("codice_fiscale"):
                existing = await db.anagrafiche.find_one({"codice_fiscale": ana["codice_fiscale"]}, {"_id": 0, "id": 1})

            if existing:
                if policy == "skip":
                    skipped += 1
                    continue
                if policy == "overwrite":
                    ana_upd = {k: v for k, v in ana.items() if k not in ("id", "created_at")}
                    ana_upd["updated_at"] = now_iso
                    # Merge conti_correnti: appendi solo IBAN nuovi
                    if "conti_correnti" in ana_upd:
                        existing_full = await db.anagrafiche.find_one(
                            {"id": existing["id"]}, {"_id": 0, "conti_correnti": 1}
                        )
                        old_ibans = {(c or {}).get("iban") for c in (existing_full or {}).get("conti_correnti", [])}
                        new_ccs = [c for c in ana_upd["conti_correnti"] if c.get("iban") not in old_ibans]
                        if new_ccs:
                            ana_upd["conti_correnti"] = list((existing_full or {}).get("conti_correnti", [])) + new_ccs
                        else:
                            ana_upd.pop("conti_correnti")
                    await db.anagrafiche.update_one({"id": existing["id"]}, {"$set": ana_upd})
                    updated += 1
                    ids_toccati.append(existing["id"])
                elif policy == "create_only":
                    ana["collaboratore_id"] = user.get("id")
                    obj = Anagrafica(**ana)
                    await db.anagrafiche.insert_one(obj.model_dump())
                    created += 1
                    ids_toccati.append(obj.id)
            else:
                # crea nuova
                ana["collaboratore_id"] = user.get("id")
                obj = Anagrafica(**ana)
                await db.anagrafiche.insert_one(obj.model_dump())
                created += 1
                ids_toccati.append(obj.id)
        except Exception as e:
            errors.append({"row": int(idx) + 2, "reason": str(e)[:200]})
            skipped += 1

    await log_attivita(
        user, "import", "anagrafiche", "batch",
        f"Import Excel/CSV '{file.filename}': +{created} nuove, {updated} aggiornate, "
        f"{skipped} saltate (policy={policy})"
    )
    return {
        "filename": file.filename,
        "total_rows": int(len(df)),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:50],  # limita a prime 50
        "policy": policy,
    }
