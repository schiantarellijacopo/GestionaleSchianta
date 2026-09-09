"""Portafoglio credito OpenAPI per agenzia (tenant).

Il credito è prepagato e gestito dal Super Admin (impostato/ricaricato sul
documento `tenants`). Ogni estrazione OpenAPI ha un costo (listino configurabile
dal Super Admin). Prima di eseguire un'estrazione si addebita il costo: se il
credito è insufficiente l'operazione è bloccata (HTTP 402).

IMPORTANTE (nessuna regressione): se il tenant NON ha un credito configurato
(campo assente = None) il wallet è considerato "non attivo" → nessun blocco e
nessun addebito. L'enforcement scatta solo quando il Super Admin imposta un
credito per quell'agenzia.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from database import raw_db
from db_models import _now_iso

# Listino di default (Prezzo base 1 richiesta, pay-as-you-go OpenAPI.it).
# Modificabile dal Super Admin. Valori in euro per singola estrazione.
DEFAULT_LISTINO: dict[str, float] = {
    "camerale": 0.00,     # ricerca/dati azienda = GRATIS (i PDF si pagano a parte)
    "catasto": 0.30,      # dati catastali (richiesta) - riempimento campi
    "catasto_pdf": 1.90,  # visura catastale PDF ufficiale
    "veicoli": 0.30,      # PRA / automotive
    "visura": 4.90,       # visura camerale ordinaria (visengine/legacy)
    "visure": 4.90,       # Visure & Documenti (visengine)
    "report": 5.00,       # report azienda
}

# Etichette per la UI del listino
LISTINO_LABELS: dict[str, str] = {
    "camerale": "Camerale (dati azienda) — ricerca gratis",
    "catasto": "Catasto (dati / riempimento campi)",
    "catasto_pdf": "Catasto — visura PDF ufficiale",
    "veicoli": "Veicoli (PRA)",
    "visura": "Visura camerale",
    "visure": "Visure & Documenti",
    "report": "Report azienda",
}


async def get_listino() -> dict[str, float]:
    doc = await raw_db.openapi_config.find_one({"id": "listino"}, {"_id": 0}) or {}
    costi = dict(DEFAULT_LISTINO)
    costi.update({k: float(v) for k, v in (doc.get("costi") or {}).items() if v is not None})
    return costi


async def set_listino(costi: dict) -> dict:
    pulito = {}
    for k, v in (costi or {}).items():
        try:
            pulito[k] = round(float(v), 2)
        except (TypeError, ValueError):
            continue
    await raw_db.openapi_config.update_one(
        {"id": "listino"},
        {"$set": {"id": "listino", "costi": pulito, "updated_at": _now_iso()}},
        upsert=True,
    )
    return await get_listino()


async def costo_operazione(operazione: str) -> float:
    return float((await get_listino()).get(operazione) or 0.0)


async def get_credito(tenant_id: Optional[str]) -> Optional[float]:
    """Ritorna il credito residuo del tenant, o None se non configurato."""
    if not tenant_id:
        return None
    t = await raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0, "openapi_credito_eur": 1})
    if not t or t.get("openapi_credito_eur") is None:
        return None
    return round(float(t["openapi_credito_eur"]), 2)


async def imposta_credito(tenant_id: str, importo: float, modo: str = "set", user: dict | None = None) -> dict:
    """Super Admin: imposta ('set') o aggiunge ('add') credito al tenant."""
    importo = round(float(importo), 2)
    attuale = await get_credito(tenant_id)
    if modo == "add":
        nuovo = round((attuale or 0.0) + importo, 2)
        delta = importo
    else:
        nuovo = importo
        delta = round(nuovo - (attuale or 0.0), 2)
    await raw_db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"openapi_credito_eur": nuovo, "updated_at": _now_iso()},
         "$push": {"openapi_credito_ricariche": {
             "$each": [{"data": _now_iso(), "modo": modo, "importo": delta,
                        "saldo": nuovo, "by": (user or {}).get("email") or (user or {}).get("id")}],
             "$slice": -100,
         }}},
    )
    return {"tenant_id": tenant_id, "credito_eur": nuovo}


async def addebita_importo(tenant_id: Optional[str], importo: float, descrizione: str, user: dict | None = None) -> dict:
    """Addebita un importo variabile (es. prezzo reale di un documento PDF)."""
    credito = await get_credito(tenant_id)
    if credito is None:
        return {"addebitato": 0.0, "saldo": None}
    importo = round(float(importo or 0), 2)
    if importo <= 0:
        return {"addebitato": 0.0, "saldo": credito}
    if credito < importo:
        raise HTTPException(
            status_code=402,
            detail=(f"Credito OpenAPI insufficiente: {credito:.2f}€ disponibili, "
                    f"«{descrizione}» costa {importo:.2f}€. Contatta l'amministratore per ricaricare."),
        )
    nuovo = round(credito - importo, 2)
    await raw_db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"openapi_credito_eur": nuovo, "updated_at": _now_iso()},
         "$push": {"openapi_credito_movimenti": {
             "$each": [{"data": _now_iso(), "operazione": descrizione, "importo": -importo,
                        "saldo": nuovo, "by": (user or {}).get("email") or (user or {}).get("id")}],
             "$slice": -200,
         }}},
    )
    return {"addebitato": importo, "saldo": nuovo}


async def addebita(tenant_id: Optional[str], operazione: str, user: dict | None = None) -> dict:
    """Verifica e scala il costo dell'estrazione dal credito del tenant.

    - Wallet non configurato (credito None) → nessun addebito, nessun blocco.
    - Credito insufficiente → HTTPException 402 (bloccato).
    - Altrimenti scala il costo e registra il movimento.
    """
    credito = await get_credito(tenant_id)
    if credito is None:
        return {"addebitato": 0.0, "saldo": None}  # wallet non attivo
    costo = await costo_operazione(operazione)
    if costo <= 0:
        return {"addebitato": 0.0, "saldo": credito}
    if credito < costo:
        raise HTTPException(
            status_code=402,
            detail=(f"Credito OpenAPI insufficiente: {credito:.2f}€ disponibili, "
                    f"l'operazione «{LISTINO_LABELS.get(operazione, operazione)}» costa {costo:.2f}€. "
                    f"Contatta l'amministratore per ricaricare il credito."),
        )
    nuovo = round(credito - costo, 2)
    await raw_db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"openapi_credito_eur": nuovo, "updated_at": _now_iso()},
         "$push": {"openapi_credito_movimenti": {
             "$each": [{"data": _now_iso(), "operazione": operazione, "importo": -costo,
                        "saldo": nuovo, "by": (user or {}).get("email") or (user or {}).get("id")}],
             "$slice": -200,
         }}},
    )
    return {"addebitato": costo, "saldo": nuovo}
