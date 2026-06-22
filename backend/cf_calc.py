"""Helper per calcolo Codice Fiscale italiano e operazioni inverse.

Usa la libreria `python-codicefiscale` (offline, lista comuni ISTAT inclusa).
"""
from __future__ import annotations
from typing import Optional
from codicefiscale import codicefiscale


def calcola_cf(lastname: str, firstname: str, gender: str,
               birthdate: str, birthplace: str) -> str:
    """Calcola il Codice Fiscale.

    birthdate: 'YYYY-MM-DD' o 'DD/MM/YYYY'
    birthplace: nome comune (es 'Roma') o codice catastale (es 'H501')
    """
    if not all([lastname, firstname, gender, birthdate, birthplace]):
        raise ValueError("Tutti i campi sono obbligatori per il calcolo del CF")
    return codicefiscale.encode(
        lastname=lastname.strip(),
        firstname=firstname.strip(),
        gender=gender.strip().upper(),
        birthdate=birthdate.strip(),
        birthplace=birthplace.strip(),
    )


def decodifica_cf(cf: str) -> dict:
    """Decodifica un CF restituendo dati anagrafici inferibili."""
    cf = (cf or "").strip().upper()
    if not cf or len(cf) != 16:
        raise ValueError("Codice fiscale non valido (16 caratteri richiesti)")
    if not codicefiscale.is_valid(cf):
        raise ValueError("Codice fiscale non valido (CIN errato)")
    d = codicefiscale.decode(cf)
    birthplace = d.get("birthplace") or {}
    bd = d.get("birthdate")
    return {
        "codice_fiscale": cf,
        "valido": True,
        "sesso": d.get("gender"),
        "data_nascita": bd.strftime("%Y-%m-%d") if bd else None,
        "comune_nascita": birthplace.get("name"),
        "provincia_nascita": birthplace.get("province"),
        "codice_catastale": birthplace.get("code"),
    }


def valida_cf(cf: str) -> bool:
    cf = (cf or "").strip().upper()
    try:
        return codicefiscale.is_valid(cf)
    except Exception:
        return False
