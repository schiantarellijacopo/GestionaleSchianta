"""OpenAPI.it router — endpoint per autocompilazione/scaricamento dati.

Endpoints (utenti tenant, salvano risultato su Anagrafica.openapi_data):
  POST /openapi-it/company/{aid}       → lookup camerale + salva
  POST /openapi-it/cadastre/{aid}      → immobili + salva
  POST /openapi-it/vehicles/{aid}      → veicoli + salva
  POST /openapi-it/visura/{aid}        → visura ordinaria + salva
  GET  /openapi-it/company?piva=...    → lookup diretto senza salvare (usato in autocomplete)
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from auth import current_user
from database import db, raw_db
from db_models import _now_iso
import openapi_it_service as svc


router = APIRouter(prefix="/openapi-it", tags=["openapi-it"])


async def _get_anagrafica(aid: str, user):
    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not ana:
        raise HTTPException(status_code=404, detail="Anagrafica non trovata")
    return ana


async def _update_openapi_field(aid: str, key: str, data) -> None:
    """Salva il risultato in Anagrafica.openapi_data.{key} (patch idempotente)."""
    await raw_db.anagrafiche.update_one(
        {"id": aid},
        {"$set": {
            f"openapi_data.{key}": data,
            "openapi_data.last_sync": _now_iso(),
            "updated_at": _now_iso(),
        }},
    )


@router.get("/company")
async def lookup_company(piva: str, user=Depends(current_user)) -> dict:
    """Lookup diretto per autocomplete P.IVA/CF (non salva su anagrafica)."""
    if not piva or len(piva) < 8:
        raise HTTPException(status_code=400, detail="P.IVA/CF non valido")
    return await svc.fetch_company(piva.strip())


@router.post("/company/{aid}")
async def fetch_company_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    ana = await _get_anagrafica(aid, user)
    key = ana.get("partita_iva") or ana.get("codice_fiscale")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza P.IVA/CF")
    data = await svc.fetch_company(key)
    await _update_openapi_field(aid, "company", data)
    return data


@router.post("/cadastre/{aid}")
async def fetch_cadastre_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    ana = await _get_anagrafica(aid, user)
    key = ana.get("codice_fiscale") or ana.get("partita_iva")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza CF/P.IVA")
    data = await svc.fetch_cadastre(key)
    await _update_openapi_field(aid, "cadastre", data)
    return {"count": len(data), "immobili": data}


@router.post("/vehicles/{aid}")
async def fetch_vehicles_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    ana = await _get_anagrafica(aid, user)
    key = ana.get("codice_fiscale") or ana.get("partita_iva")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza CF/P.IVA")
    data = await svc.fetch_vehicles(key)
    await _update_openapi_field(aid, "automotive", data)
    return {"count": len(data), "veicoli": data}


@router.post("/visura/{aid}")
async def fetch_visura_for_anagrafica(aid: str, user=Depends(current_user)) -> dict:
    ana = await _get_anagrafica(aid, user)
    key = ana.get("partita_iva")
    if not key:
        raise HTTPException(status_code=400, detail="Anagrafica senza P.IVA")
    data = await svc.fetch_visura(key)
    await _update_openapi_field(aid, "visura", data)
    return data


@router.get("/status")
async def status(user=Depends(current_user)) -> dict:
    """Diagnostica per il frontend: modalità + credito residuo + env.

    Ritorna:
      {
        "mode": "live" | "mock",
        "has_credentials": bool,
        "env": "prod" | "sandbox",
        "credit_eur": float | null    # None se non disponibile
      }
    """
    from os import environ
    has_creds = svc.has_credentials()
    credit = None
    if has_creds:
        credit = await svc.get_credit()
    return {
        "mode": "live" if has_creds else "mock",
        "has_credentials": has_creds,
        "env": (environ.get("OPENAPI_IT_ENV") or "prod").lower(),
        "credit_eur": credit,
    }
