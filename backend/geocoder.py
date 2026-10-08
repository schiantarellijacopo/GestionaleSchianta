"""Geolocalizzazione indirizzi tramite Nominatim (OpenStreetMap).

Servizio gratuito senza chiave API. Limit: max 1 req/sec per fair use.

Refactor: ridotta la complessità di `cerca_suggerimenti` separando
chiamata HTTP, parsing del singolo item e composizione del risultato.
"""
from __future__ import annotations
import httpx
from typing import Optional


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AssicuraCRM/1.0 (Italian Insurance CRM)"
_HTTP_TIMEOUT_SEC = 10


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------
async def _nominatim_get(params: dict) -> list[dict]:
    """Esegue una chiamata GET a Nominatim. Ritorna [] in caso di errore."""
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEC) as client:
            r = await client.get(
                NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT},
            )
    except Exception:
        return []
    if r.status_code != 200:
        return []
    try:
        return r.json() or []
    except ValueError:
        return []


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _estrai_comune(addr: dict) -> str:
    """Risolve il nome comune testando i campi Nominatim in ordine di preferenza."""
    for key in ("city", "town", "village", "municipality", "hamlet"):
        v = addr.get(key)
        if v:
            return v
    return ""


def _estrai_indirizzo(item: dict, addr: dict) -> str:
    """Combina via + civico, con fallback al `name`."""
    via = (addr.get("road") or addr.get("pedestrian") or addr.get("path") or "").strip()
    civico = (addr.get("house_number") or "").strip()
    if via:
        return f"{via} {civico}".strip()
    return item.get("name") or ""


def _parse_item(item: dict) -> dict:
    """Trasforma un singolo risultato Nominatim nel nostro schema suggerimento."""
    addr = item.get("address", {}) or {}
    return {
        "display_name": item.get("display_name"),
        "lat": float(item["lat"]),
        "lng": float(item["lon"]),
        "indirizzo": _estrai_indirizzo(item, addr),
        "comune": _estrai_comune(addr),
        "cap": addr.get("postcode") or "",
        "provincia": addr.get("county") or addr.get("state_district") or "",
        "regione": addr.get("state") or "",
        "nazione": addr.get("country") or "Italia",
        "name": item.get("name") or "",
    }


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------
def _solo_via(indirizzo: str) -> str:
    """Rimuove il numero civico finale dall'indirizzo (es. 'VIA ROMA 201' -> 'VIA ROMA').

    Nominatim in ricerca free-form fallisce spesso quando il civico non è
    mappato: riprovare con la sola via migliora il recall.
    """
    import re
    s = (indirizzo or "").strip()
    return re.sub(r"[,\s]+\d+[A-Za-z/]*\s*$", "", s).strip() or s


async def geocoda_indirizzo(
    indirizzo: str,
    comune: Optional[str] = None,
    cap: Optional[str] = None,
    provincia: Optional[str] = None,
    nazione: str = "Italia",
) -> dict:
    """Restituisce {lat, lng, display_name} oppure {} se non trovato.

    Ricerca vincolata all'Italia (countrycodes=it) in lingua italiana.
    Strategia a cascata: indirizzo completo -> senza civico -> solo comune,
    così da restituire sempre una posizione ragionevole (centro paese) invece
    di un falso match in un'altra nazione.
    """
    base = {
        "format": "json", "limit": 1, "addressdetails": 1,
        "countrycodes": "it", "accept-language": "it",
    }

    # Tentativi in ordine di precisione decrescente.
    tentativi: list[str] = []
    if indirizzo:
        full = ", ".join(p for p in (indirizzo, cap, comune, provincia) if p)
        tentativi.append(full)
        via = _solo_via(indirizzo)
        if via and via != indirizzo:
            tentativi.append(", ".join(p for p in (via, comune, provincia) if p))
        else:
            tentativi.append(", ".join(p for p in (via, comune, provincia) if p))
    comune_q = ", ".join(p for p in (comune, provincia) if p)
    if comune_q:
        tentativi.append(comune_q)

    # Dedup mantenendo l'ordine.
    seen = set()
    tentativi = [t for t in tentativi if t and not (t in seen or seen.add(t))]

    for query in tentativi:
        data = await _nominatim_get({**base, "q": query})
        if not data:
            continue
        first = data[0]
        try:
            return {
                "lat": float(first["lat"]),
                "lng": float(first["lon"]),
                "display_name": first.get("display_name"),
                "query": query,
            }
        except (KeyError, ValueError):
            continue
    return {}


async def cerca_suggerimenti(
    query: str,
    paese: str = "it",
    limit: int = 6,
) -> list[dict]:
    """Ritorna una lista di suggerimenti per autocomplete indirizzo.

    Ogni elemento contiene: display_name, lat, lng, indirizzo, comune, cap,
    provincia, regione, nazione, name.
    """
    if not query or len(query.strip()) < 3:
        return []
    data = await _nominatim_get({
        "q": query.strip(),
        "format": "json",
        "limit": max(1, min(limit, 10)),
        "addressdetails": 1,
        "countrycodes": paese,
        "accept-language": "it",
    })
    out: list[dict] = []
    for item in data:
        try:
            out.append(_parse_item(item))
        except (KeyError, ValueError):
            continue
    return out
