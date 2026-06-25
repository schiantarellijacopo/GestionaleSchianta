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


async def cerca_suggerimenti(
    query: str,
    paese: str = "it",
    limit: int = 6,
) -> list[dict]:
    """Ritorna una lista di suggerimenti per autocomplete indirizzo.

    Ogni elemento contiene: display_name, lat, lng, address (dict con
    road, house_number, postcode, town/city/village, state, county, country).
    """
    if not query or len(query.strip()) < 3:
        return []
    params = {
        "q": query.strip(),
        "format": "json",
        "limit": max(1, min(limit, 10)),
        "addressdetails": 1,
        "countrycodes": paese,
        "accept-language": "it",
    }
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(NOMINATIM_URL, params=params, headers=headers)
        if r.status_code != 200:
            return []
        data = r.json()
        out = []
        for item in data:
            addr = item.get("address", {}) or {}
            comune = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("municipality")
                or addr.get("hamlet")
                or ""
            )
            via = (addr.get("road") or addr.get("pedestrian") or addr.get("path") or "").strip()
            civico = (addr.get("house_number") or "").strip()
            indirizzo = f"{via} {civico}".strip() if via else (item.get("name") or "")
            out.append({
                "display_name": item.get("display_name"),
                "lat": float(item["lat"]),
                "lng": float(item["lon"]),
                "indirizzo": indirizzo,
                "comune": comune,
                "cap": addr.get("postcode") or "",
                "provincia": addr.get("county") or addr.get("state_district") or "",
                "regione": addr.get("state") or "",
                "nazione": addr.get("country") or "Italia",
                "name": item.get("name") or "",
            })
        return out
    except Exception:
        return []
