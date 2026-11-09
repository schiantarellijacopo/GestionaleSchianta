"""Utility fuso orario ITALIA (Europe/Rome).

Tutte le date/ora "oggi" e "adesso" del programma devono essere calcolate in ora
italiana, anche quando il server di produzione gira in UTC (evita slittamenti di
un giorno a cavallo della mezzanotte). La formattazione utente è sempre gg/mm/aaaa.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")


def adesso_italia() -> datetime:
    """Datetime corrente in ora di Roma (naive: wall-clock, senza offset) così è
    compatibile con gli ISO naive già presenti nel DB, ma allineato a Roma."""
    return datetime.now(ROME).replace(tzinfo=None)


def oggi_italia() -> date:
    """Data odierna in ora italiana (Europe/Rome)."""
    return datetime.now(ROME).date()


def fmt_it(d) -> str:
    """Formatta una data/datetime/stringa ISO come gg/mm/aaaa. '-' se vuoto."""
    if not d:
        return "-"
    try:
        if isinstance(d, datetime):
            return d.strftime("%d/%m/%Y")
        if isinstance(d, date):
            return d.strftime("%d/%m/%Y")
        return date.fromisoformat(str(d)[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(d)
