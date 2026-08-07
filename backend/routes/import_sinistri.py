"""Excel/CSV smart importer per Sinistri.

Endpoint:
  POST /api/import/sinistri/preview
  POST /api/import/sinistri/execute
"""
from __future__ import annotations

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

router = APIRouter(prefix="/import/sinistri", tags=["import-sinistri"])

FIELD_ALIASES: dict = {
    "numero_sinistro": ["numero sinistro", "n. sinistro", "n sinistro",
                        "num sinistro", "numero", "sinistro", "claim number"],
    "numero_interno": ["numero interno", "n. interno", "num interno", "n int"],
    "numero_polizza": ["numero polizza", "n. polizza", "polizza", "contratto",
                       "num contratto", "policy number"],
    "codice_fiscale": ["codice fiscale", "cf", "cf contraente", "cod fiscale",
                       "c.f."],
    "partita_iva": ["partita iva", "p.iva", "piva", "vat"],
    "data_avvenimento": ["data avvenimento", "data sinistro", "data evento",
                         "data accadimento", "avvenuto il", "date of loss"],
    "data_denuncia": ["data denuncia", "denunciato il", "data comunicazione",
                      "notification date"],
    "data_apertura": ["data apertura", "aperto il", "opened"],
    "data_liquidazione": ["data liquidazione", "liquidato il", "data pagamento"],
    "tipologia_sinistro": ["tipologia", "tipologia sinistro", "tipo sinistro",
                           "categoria sinistro", "loss type"],
    "luogo": ["luogo", "luogo sinistro", "località", "location"],
    "ramo": ["ramo", "ramo assicurativo"],
    "stato": ["stato", "stato sinistro", "status"],
    "descrizione": ["descrizione", "dinamica", "note", "annotazioni", "description"],
    "riserva": ["riserva", "reserve"],
    "liquidazione": ["liquidazione", "importo liquidato", "liquidato",
                     "amount paid", "pagato"],
    "targa": ["targa", "veicolo", "plate"],
}


def _detect_mapping(headers: List[str]) -> dict:
    detected = []
    reverse: dict = {}
    used: set = set()
    for idx, h in enumerate(headers):
        norm = _normalize_header(h)
        best: Optional[str] = None
        best_score = 0.0
        for canonical, aliases in FIELD_ALIASES.items():
            if canonical in used:
                continue
            for alias in aliases:
                score = _similarity(norm, _normalize_header(alias))
                if score > best_score:
                    best_score = score
                    best = canonical
        if best and best_score >= 0.6:
            detected.append({"header": str(h), "index": idx,
                             "canonical": best, "confidence": round(best_score, 2)})
            used.add(best)
            reverse[best] = str(h)
        else:
            detected.append({"header": str(h), "index": idx,
                             "canonical": None, "confidence": 0.0})
    return {"detected": detected, "reverse": reverse}


def _to_float(v) -> float:
    if v is None or v == "":
        return 0.0
    s = str(v).strip().replace("€", "").replace(" ", "").replace("\xa0", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _row_to_sinistro(row_values: dict, mapping: dict) -> dict:
    sin: dict = {}
    for header, canonical in mapping.items():
        if not canonical:
            continue
        val = _sanitize_value(row_values.get(header))
        if val is None:
            continue
        if canonical in ("codice_fiscale", "partita_iva"):
            val = val.upper().replace(" ", "")
        elif canonical in ("data_avvenimento", "data_denuncia", "data_apertura",
                           "data_liquidazione"):
            val = _parse_date_flexible(val)
            if val is None:
                continue
        elif canonical in ("riserva", "liquidazione"):
            val = _to_float(val)
        elif canonical == "stato":
            v = val.lower()
            if "aper" in v:
                val = "aperto"
            elif "istr" in v:
                val = "in_istruttoria"
            elif "liqui" in v:
                val = "liquidato"
            elif "chiu" in v and "seguito" in v:
                val = "chiuso_senza_seguito"
            elif "chiu" in v:
                val = "chiuso"
            elif "resp" in v:
                val = "respinto"
            else:
                val = "aperto"
        elif canonical == "targa":
            val = val.upper().replace(" ", "").replace("-", "")
        elif canonical == "ramo":
            val = val.upper()
        sin[canonical] = val
    return sin


async def _resolve_polizza(sin: dict) -> Optional[dict]:
    """Cerca la polizza per numero_polizza."""
    num = sin.get("numero_polizza")
    if not num:
        return None
    p = await db.polizze.find_one(
        {"numero_polizza": str(num).strip()},
        {"_id": 0, "id": 1, "contraente_id": 1, "compagnia_id": 1,
         "ramo": 1, "collaboratore_id": 1},
    )
    return p


@router.post("/preview")
async def preview_import_sinistri(
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
        normalized = _row_to_sinistro(row_dict, map_headers)
        preview_rows.append({"raw": row_dict, "normalized": normalized})
    dup_count = 0
    numeri = set()
    for _, row in df.iterrows():
        row_dict = {h: _sanitize_value(row[h]) for h in headers}
        norm = _row_to_sinistro(row_dict, map_headers)
        if norm.get("numero_sinistro"):
            numeri.add(norm["numero_sinistro"])
    if numeri:
        dup_count = await db.sinistri.count_documents(
            {"numero_sinistro": {"$in": list(numeri)}},
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
async def execute_import_sinistri(
    file: UploadFile = File(...),
    mapping_json: str = Form(...),
    policy: str = Form("skip"),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    import json as _json
    try:
        mapping = _json.loads(mapping_json)
    except Exception:
        raise HTTPException(400, "mapping_json non valido")
    if policy not in ("skip", "overwrite", "create_only"):
        raise HTTPException(400, "policy non valida")

    content = await file.read()
    df = _read_dataframe(content, file.filename)
    if df.empty:
        return {"created": 0, "updated": 0, "skipped": 0, "errors": [], "total_rows": 0}

    from db_models import Sinistro

    headers = [str(h) for h in df.columns]
    created = 0
    updated = 0
    skipped = 0
    errors: List[dict] = []

    for idx, row in df.iterrows():
        try:
            row_dict = {h: _sanitize_value(row[h]) for h in headers}
            sin = _row_to_sinistro(row_dict, mapping)
            if not sin.get("numero_sinistro"):
                skipped += 1
                errors.append({"row": int(idx) + 2, "reason": "numero_sinistro mancante"})
                continue
            pol = await _resolve_polizza(sin)
            if not pol:
                skipped += 1
                errors.append({
                    "row": int(idx) + 2,
                    "reason": f"polizza '{sin.get('numero_polizza', '?')}' non trovata nel CRM",
                })
                continue
            # Duplicato per numero_sinistro + polizza_id
            existing = await db.sinistri.find_one(
                {"numero_sinistro": sin["numero_sinistro"], "polizza_id": pol["id"]},
                {"_id": 0, "id": 1},
            )
            if existing:
                if policy == "skip":
                    skipped += 1
                    continue
                if policy == "overwrite":
                    upd = {k: v for k, v in sin.items()
                           if k not in ("numero_polizza", "codice_fiscale",
                                        "partita_iva")}
                    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
                    await db.sinistri.update_one({"id": existing["id"]}, {"$set": upd})
                    updated += 1
                    continue
            sin_data = {k: v for k, v in sin.items()
                        if k not in ("numero_polizza", "codice_fiscale", "partita_iva")}
            sin_data["polizza_id"] = pol["id"]
            sin_data["contraente_id"] = pol.get("contraente_id") or ""
            sin_data["compagnia_id"] = pol.get("compagnia_id") or ""
            sin_data.setdefault("ramo", pol.get("ramo") or "GENERALE")
            sin_data.setdefault("data_avvenimento",
                                datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            sin_data.setdefault("data_denuncia", sin_data["data_avvenimento"])
            sin_data.setdefault("collaboratore_id",
                                pol.get("collaboratore_id") or user.get("id"))
            sin_data.setdefault("fonte", "import_ania")
            obj = Sinistro(**sin_data)
            await db.sinistri.insert_one(obj.model_dump())
            created += 1
        except Exception as e:
            errors.append({"row": int(idx) + 2, "reason": str(e)[:200]})
            skipped += 1

    await log_attivita(
        user, "import", "sinistri", "batch",
        f"Import Excel/CSV '{file.filename}': +{created} nuovi, {updated} aggiornati, "
        f"{skipped} saltati (policy={policy})",
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
