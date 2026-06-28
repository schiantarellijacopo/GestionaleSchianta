"""Utility per normalizzare credenziali email (SMTP/IMAP).

Google App Password viene visualizzata come "xxxx yyyy zzzz wwww" (con spazi
ogni 4 caratteri per leggibilità). Quando l'utente copia-incolla la stringa,
spesso include:
  - spazi normali (\\x20)
  - non-breaking spaces (\\xa0) <-- causa "ascii codec can't encode" su imaplib
  - tab, newline, ecc.

Inoltre, anche l'indirizzo email può contenere whitespace o doppia
concatenazione (es. "user@host.itusEr@host.it").

Queste funzioni ripuliscono i valori prima dell'uso.
"""
from __future__ import annotations

import re


def clean_password(pwd: str | None) -> str:
    """Rimuove tutti i caratteri whitespace (inclusi NBSP) dalla password.

    Google App Passwords sono 16 caratteri alfanumerici, formattati visualmente
    "xxxx yyyy zzzz wwww". Sia gli spazi normali sia gli NBSP (\\xa0) devono
    essere rimossi prima di passarli a IMAP/SMTP, che richiedono ASCII puro.
    """
    if not pwd:
        return ""
    # rimuove spazi normali, NBSP, tab, newline, ZWSP, ecc.
    cleaned = re.sub(r"[\s\u00a0\u200b\u200c\u200d\ufeff]+", "", pwd)
    return cleaned


def clean_email(addr: str | None) -> str:
    """Normalizza un indirizzo email.

    - rimuove whitespace
    - tronca a una singola istanza se contiene una duplicazione visibile
      (es. "a@b.ita@b.it" → "a@b.it"), tipico errore di copy-paste o di
      pulsante che concatena invece di sostituire.
    """
    if not addr:
        return ""
    s = re.sub(r"\s+", "", addr).lower()
    # detect duplicazione: stringa che contiene esattamente 2 volte se stessa
    if s.count("@") >= 2:
        # prova a tagliare alla prima email valida
        m = re.match(r"^([^\s@]+@[^\s@]+\.[a-z]{2,})", s)
        if m:
            first = m.group(1)
            # se la stringa è esattamente first + first, ritorna first
            if s == first + first:
                return first
            # altrimenti ritorna comunque la prima email valida
            return first
    return s
