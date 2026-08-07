"""Excel/CSV smart importer per Polizze (portafoglio).

Endpoint:
  POST /api/import/polizze/preview  → analizza file, autodetect mapping
  POST /api/import/polizze/execute  → esegue import con mapping confermato

Riusa gli helper di import_anagrafiche (_normalize_header, _similarity,
_read_dataframe, _sanitize_value, _parse_date_flexible) per non duplicare logica.
Aggiunge risoluzione automatica di:
- contraente_id (via codice_fiscale / partita_iva)
- compagnia_id (via nome/codice compagnia)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from auth import require_user
from database import db
from shared import log_attivita
from routes.import_anagrafiche import (
    _normalize_header, _similarity, _read_dataframe,
    _sanitize_value, _parse_date_flexible,
)

router = APIRouter(prefix="/import/polizze", tags=["import-polizze"])

# ============================================================
# Alias campi Polizza (header → campo canonico)
# ============================================================
FIELD_ALIASES: dict = {
    "numero_polizza": ["numero polizza", "n. polizza", "n polizza", "num polizza",
                       "polizza", "policy", "policy number", "contratto",
                       "num contratto", "n contratto"],
    "compagnia_nome": ["compagnia", "impresa", "società", "insurer", "carrier",
                       "compagnia assicurativa", "assicuratore"],
    "codice_fiscale": ["codice fiscale contraente", "cf contraente", "cf",
                       "codice fiscale", "cod fiscale", "c.f.", "cod.fisc."],
    "partita_iva": ["partita iva", "p.iva", "piva", "vat", "p iva"],
    "cliente_nome": ["cliente", "contraente", "assicurato", "ragione sociale",
                     "denominazione", "nominativo"],
    "ramo": ["ramo", "ramo assicurativo", "line", "linea", "branch"],
    "prodotto": ["prodotto", "product", "tariffa", "descrizione prodotto"],
    "effetto": ["effetto", "data effetto", "decorrenza", "data decorrenza",
                "inizio", "start", "from", "dal"],
    "scadenza": ["scadenza", "data scadenza", "expires", "expiry", "al",
                 "fine", "to"],
    "frazionamento": ["frazionamento", "rateazione", "rata", "periodicità",
                      "split", "frequency"],
    "premio_lordo": ["premio lordo", "lordo", "premio", "totale premio",
                     "importo", "gross"],
    "premio_netto": ["premio netto", "netto", "net"],
    "premio_tasse": ["imposte", "tasse", "tax"],
    "premio_ssn": ["ssn", "servizio sanitario", "contributo ssn"],
    "provvigioni": ["provvigioni", "provvigione", "commissioni", "commission"],
    "targa": ["targa", "veicolo", "plate", "identificativo veicolo"],
    "note": ["note", "annotazioni", "notes"],
    "stato": ["stato", "stato polizza", "status"],
    "tipo_tariffa": ["tipo tariffa", "tariffa"],
    "bm_assegnata": ["classe bm", "classe cu", "bm", "cu", "bonus malus"],
    "franchigia": ["franchigia", "deductible"],
    "capitale_assicurato": ["capitale", "capitale assicurato", "massimale"],
}


def _detect_mapping(headers: List[str]) -> dict:
    detected = []
    reverse: dict = {}
    used_canonical: set = set()
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


def _row_to_polizza(row_values: dict, mapping: dict) -> dict:
    pol: dict = {}
    for header, canonical in mapping.items():
        if not canonical:
            continue
        raw = row_values.get(header)
        val = _sanitize_value(raw)
        if val is None:
            continue
        if canonical in ("codice_fiscale", "partita_iva"):
            val = val.upper().replace(" ", "")
        elif canonical in ("effetto", "scadenza"):
            val = _parse_date_flexible(val)
            if val is None:
                continue
        elif canonical in ("premio_lordo", "premio_netto", "premio_tasse",
                            "premio_ssn", "provvigioni", "franchigia",
                            "capitale_assicurato"):
            val = _to_float(val)
        elif canonical == "frazionamento":
            v = val.lower().strip()
            if v in ("annuale", "annuo", "annua", "yearly", "annuale"):
                val = "annuale"
            elif v in ("semestrale", "semiannual", "semestrale"):
                val = "semestrale"
            elif v in ("trimestrale", "quarterly"):
                val = "trimestrale"
            elif v in ("mensile", "monthly", "mensile"):
                val = "mensile"
            elif v in ("quadrimestrale",):
                val = "quadrimestrale"
            elif v in ("unica", "unico", "one-shot"):
                val = "unica"
            else:
                continue
        elif canonical == "targa":
            val = val.upper().replace(" ", "").replace("-", "")
        elif canonical == "ramo":
            val = val.upper()
        elif canonical == "stato":
            v = val.lower().strip()
            if "annul" in v or "disdett" in v:
                val = "annullata"
            elif "sospes" in v:
                val = "sospesa"
            elif "scad" in v:
                val = "scaduta"
            else:
                val = "attiva"
        pol[canonical] = val
    return pol


def _to_float(s: str) -> float:
    if s is None or s == "":
        return 0.0
    x = str(s).strip().replace("€", "").replace(" ", "").replace("\xa0", "")
    if "," in x and "." in x:
        x = x.replace(".", "").replace(",", ".")
    elif "," in x:
        x = x.replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return 0.0


async def _resolve_contraente_id(pol: dict) -> Optional[str]:
    """Cerca l'anagrafica del contraente per CF o P.IVA."""
    if pol.get("codice_fiscale"):
        a = await db.anagrafiche.find_one(
            {"codice_fiscale": pol["codice_fiscale"]}, {"_id": 0, "id": 1},
        )
        if a:
            return a["id"]
    if pol.get("partita_iva"):
        a = await db.anagrafiche.find_one(
            {"partita_iva": pol["partita_iva"]}, {"_id": 0, "id": 1},
        )
        if a:
            return a["id"]
    return None


async def _resolve_compagnia_id(pol: dict) -> Optional[str]:
    """Cerca la compagnia per nome (case-insensitive) o per codice."""
    nome = pol.get("compagnia_nome")
    if not nome:
        return None
    q = re.escape(str(nome).strip())
    c = await db.compagnie.find_one(
        {"$or": [
            {"ragione_sociale": {"$regex": f"^{q}$", "$options": "i"}},
            {"codice": {"$regex": f"^{q}$", "$options": "i"}},
        ]},
        {"_id": 0, "id": 1},
    )
    return c["id"] if c else None


@router.post("/preview")
async def preview_import_polizze(
    file: UploadFile = File(...),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    content = await file.read()
    if not content:
        raise HTTPException(400, "File vuoto")
    df = _read_dataframe(content, file.filename)
    if df.empty:
        return {"headers": [], "detected": [], "rows": [], "total_rows": 0}
    headers = [str(h) for h in df.columns]
    mapping = _detect_mapping(headers)
    map_headers = {d["header"]: d["canonical"] for d in mapping["detected"]}
    preview_rows = []
    for _, row in df.head(10).iterrows():
        row_dict = {h: _sanitize_value(row[h]) for h in headers}
        normalized = _row_to_polizza(row_dict, map_headers)
        preview_rows.append({"raw": row_dict, "normalized": normalized})
    # Stima quante polizze esistono già (numero_polizza già presente)
    dup_count = 0
    numeri = set()
    for _, row in df.iterrows():
        row_dict = {h: _sanitize_value(row[h]) for h in headers}
        norm = _row_to_polizza(row_dict, map_headers)
        if norm.get("numero_polizza"):
            numeri.add(norm["numero_polizza"])
    if numeri:
        dup_count = await db.polizze.count_documents(
            {"numero_polizza": {"$in": list(numeri)}},
        )
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
async def execute_import_polizze(
    file: UploadFile = File(...),
    mapping_json: str = Form(...),
    policy: str = Form("skip"),  # skip / overwrite / create_only
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    import json as _json
    try:
        mapping = _json.loads(mapping_json)
    except Exception:
        raise HTTPException(400, "mapping_json non valido")
    if not isinstance(mapping, dict):
        raise HTTPException(400, "mapping_json deve essere un oggetto")
    if policy not in ("skip", "overwrite", "create_only"):
        raise HTTPException(400, "policy non valida")

    content = await file.read()
    df = _read_dataframe(content, file.filename)
    if df.empty:
        return {"created": 0, "updated": 0, "skipped": 0, "errors": [], "total_rows": 0}

    from db_models import Polizza

    headers = [str(h) for h in df.columns]
    created = 0
    updated = 0
    skipped = 0
    errors: List[dict] = []

    for idx, row in df.iterrows():
        try:
            row_dict = {h: _sanitize_value(row[h]) for h in headers}
            pol = _row_to_polizza(row_dict, mapping)
            if not pol.get("numero_polizza"):
                skipped += 1
                errors.append({"row": int(idx) + 2, "reason": "numero_polizza mancante"})
                continue
            # Risolvi contraente
            contraente_id = await _resolve_contraente_id(pol)
            if not contraente_id:
                skipped += 1
                errors.append({
                    "row": int(idx) + 2,
                    "reason": f"contraente non trovato (CF={pol.get('codice_fiscale')} P.IVA={pol.get('partita_iva')})",
                })
                continue
            compagnia_id = await _resolve_compagnia_id(pol)
            if not compagnia_id:
                skipped += 1
                errors.append({
                    "row": int(idx) + 2,
                    "reason": f"compagnia '{pol.get('compagnia_nome', '?')}' non trovata (creala prima da Librerie)",
                })
                continue
            # Duplicato per numero_polizza
            existing = await db.polizze.find_one(
                {"numero_polizza": pol["numero_polizza"]},
                {"_id": 0, "id": 1},
            )
            if existing:
                if policy == "skip":
                    skipped += 1
                    continue
                if policy == "overwrite":
                    upd = {k: v for k, v in pol.items()
                           if k not in ("codice_fiscale", "partita_iva",
                                        "cliente_nome", "compagnia_nome")}
                    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
                    await db.polizze.update_one({"id": existing["id"]}, {"$set": upd})
                    updated += 1
                    continue
            # Crea
            pol_data = {k: v for k, v in pol.items()
                        if k not in ("codice_fiscale", "partita_iva",
                                     "cliente_nome", "compagnia_nome")}
            pol_data["contraente_id"] = contraente_id
            pol_data["compagnia_id"] = compagnia_id
            pol_data.setdefault("effetto", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            pol_data.setdefault("scadenza", pol_data["effetto"])
            pol_data.setdefault("ramo", "GENERALE")
            pol_data.setdefault("collaboratore_id", user.get("id"))
            pol_data.setdefault("fonte", "import_ania")
            obj = Polizza(**pol_data)
            await db.polizze.insert_one(obj.model_dump())
            created += 1
        except Exception as e:
            errors.append({"row": int(idx) + 2, "reason": str(e)[:200]})
            skipped += 1

    await log_attivita(
        user, "import", "polizze", "batch",
        f"Import Excel/CSV '{file.filename}': +{created} nuove, {updated} aggiornate, "
        f"{skipped} saltate (policy={policy})",
    )
    return {
        "filename": file.filename,
        "total_rows": int(len(df)),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:50],
        "policy": policy,
    }
