"""Geolocalizzazione indirizzi tramite Nominatim (OpenStreetMap).

Servizio gratuito senza chiave API. Limit: max 1 req/sec per fair use.
"""
from __future__ import annotations
import httpx
from typing import Optional


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AssicuraCRM/1.0 (Italian Insurance CRM)"


async def geocoda_indirizzo(
    indirizzo: str,
    comune: Optional[str] = None,
    cap: Optional[str] = None,
    provincia: Optional[str] = None,
    nazione: str = "Italia",
) -> dict:
    """Restituisce {lat, lng, display_name} oppure {} se non trovato."""
    parts = []
    if indirizzo:
        parts.append(indirizzo)
    if cap:
        parts.append(cap)
    if comune:
        parts.append(comune)
    if provincia:
        parts.append(provincia)
    if nazione:
        parts.append(nazione)
    if not parts:
        return {}
    query = ", ".join(parts)
    params = {"q": query, "format": "json", "limit": 1, "addressdetails": 1}
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(NOMINATIM_URL, params=params, headers=headers)
        if r.status_code != 200:
            return {}
        data = r.json()
        if not data:
            return {}
        first = data[0]
        return {
            "lat": float(first["lat"]),
            "lng": float(first["lon"]),
            "display_name": first.get("display_name"),
            "query": query,
        }
    except Exception:
        return {}
