"""Lookup router — IBAN → banca, CAP → comune/provincia.

Endpoints:
  GET  /lookup/iban?iban=IT60X...        → parsa IBAN + risolve banca
  GET  /lookup/cap?cap=20100             → risolve comune/provincia da CAP italiano
                                            (usa `postal_codes` collection popolata via seed)
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException

from auth import current_user
from database import raw_db
from bank_lookup import lookup_bank_from_iban, parse_iban


router = APIRouter(prefix="/lookup", tags=["lookup"])


@router.get("/iban")
async def lookup_iban(iban: str, user=Depends(current_user)) -> dict:
    """Risoluzione IBAN → banca (ABI+CAB). Usato dal form Conti Correnti."""
    return await lookup_bank_from_iban(iban, raw_db=raw_db)


@router.get("/iban/validate")
async def validate_iban(iban: str, user=Depends(current_user)) -> dict:
    """Solo parsing IBAN (senza lookup banca) — validazione lato client."""
    parsed = parse_iban(iban)
    if not parsed:
        return {"valid": False, "error": "IBAN non valido"}
    return {"valid": True, **parsed}


@router.get("/cap")
async def lookup_cap(cap: str, user=Depends(current_user)) -> dict:
    """Risoluzione CAP → comune/provincia/regione.
    Usa collection `postal_codes` (popolata via `postal_codes_seed`).
    """
    if not cap or not cap.isdigit() or len(cap) != 5:
        raise HTTPException(status_code=400, detail="CAP deve essere di 5 cifre")
    doc = await raw_db.postal_codes.find_one({"cap": cap}, {"_id": 0})
    if not doc:
        return {"cap": cap, "found": False,
                "note": "CAP non presente nel registro locale. Usa il campo indirizzo con autocomplete Photon."}
    return {"cap": cap, "found": True, **doc}


@router.get("/banks")
async def list_banks(user=Depends(current_user)) -> list[dict]:
    """Lista banche registrate (DB + tabella statica)."""
    from bank_lookup import ABI_TO_BANK
    static_banks = [{"abi": abi, **data, "source": "static"} for abi, data in ABI_TO_BANK.items()]
    db_banks = await raw_db.banks_registry.find({}, {"_id": 0}).to_list(2000)
    # Merge: DB prevale su static per stesso ABI
    db_abi = {b["abi"] for b in db_banks}
    merged = [b for b in static_banks if b["abi"] not in db_abi] + db_banks
    return sorted(merged, key=lambda b: b.get("ragione_sociale", ""))
