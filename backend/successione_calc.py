"""Calcolatore quote di successione secondo il Codice Civile italiano.

Implementa le regole di successione legittima (artt. 565-586 c.c.) per i casi
più comuni: coniuge da solo, coniuge + figli, coniuge + ascendenti/fratelli,
solo figli, solo ascendenti, solo fratelli.

NOTA: questo modulo fornisce una stima indicativa. Le quote variano in caso
di legati, donazioni in vita o testamento. Per casi complessi consultare
un notaio.
"""
from typing import Optional


def calcola_successione(
    coniuge: bool,
    numero_figli: int,
    genitori_vivi: int = 0,
    fratelli: int = 0,
    patrimonio: float = 0.0,
) -> dict:
    """Restituisce due scenari di successione: senza testamento (intestata)
    e con testamento (quote di legittima).

    Args:
        coniuge: True se presente coniuge superstite
        numero_figli: figli legittimi/naturali
        genitori_vivi: numero genitori in vita (0, 1, 2)
        fratelli: numero fratelli/sorelle
        patrimonio: valore patrimoniale per calcolare le quote in euro

    Returns:
        {
            "senza_testamento": {"label": [str], "quota_pct": [float], "quota_eur": [float], "note": str},
            "quote_legittima": {"label": [str], "quota_pct": [float], "quota_eur": [float], "disponibile_pct": float, "disponibile_eur": float, "note": str}
        }
    """
    # SENZA TESTAMENTO (successione legittima - art. 565+)
    senza = _successione_legittima(coniuge, numero_figli, genitori_vivi, fratelli)
    # CON TESTAMENTO (quote di legittima - art. 536+)
    legittima = _quote_di_legittima(coniuge, numero_figli, genitori_vivi)

    def to_eur(scenario):
        scenario["quota_eur"] = [round(p / 100.0 * patrimonio, 2) for p in scenario["quota_pct"]]
        if "disponibile_pct" in scenario:
            scenario["disponibile_eur"] = round(scenario["disponibile_pct"] / 100.0 * patrimonio, 2)
        return scenario

    return {
        "patrimonio": round(patrimonio, 2),
        "senza_testamento": to_eur(senza),
        "quote_legittima": to_eur(legittima),
    }


def _successione_legittima(coniuge: bool, figli: int, genitori: int, fratelli: int) -> dict:
    """Art. 565+ c.c. - successione legittima (senza testamento)."""
    label, quota = [], []
    note = ""

    if coniuge and figli == 0 and genitori == 0 and fratelli == 0:
        # Solo coniuge: 100%
        label = ["Coniuge"]
        quota = [100.0]
        note = "Coniuge unico erede (art. 583 c.c.)."
    elif coniuge and figli == 1:
        # Coniuge + 1 figlio: 1/2 - 1/2
        label = ["Coniuge", "Figlio"]
        quota = [50.0, 50.0]
        note = "Coniuge 1/2, unico figlio 1/2 (art. 581 c.c.)."
    elif coniuge and figli >= 2:
        # Coniuge 1/3, figli 2/3 in parti uguali
        f_quota = (200.0 / 3.0) / figli
        label = ["Coniuge"] + [f"Figlio {i+1}" for i in range(figli)]
        quota = [100.0 / 3.0] + [f_quota] * figli
        note = f"Coniuge 1/3, i {figli} figli si dividono 2/3 in parti uguali (art. 581 c.c.)."
    elif not coniuge and figli >= 1:
        # Solo figli in parti uguali
        f_quota = 100.0 / figli
        label = [f"Figlio {i+1}" for i in range(figli)]
        quota = [f_quota] * figli
        note = f"I {figli} figli ereditano in parti uguali (art. 566 c.c.)."
    elif coniuge and figli == 0 and (genitori > 0 or fratelli > 0):
        # Coniuge + ascendenti/fratelli: coniuge 2/3, ascendenti+fratelli 1/3
        label = ["Coniuge"]
        quota = [200.0 / 3.0]
        remaining_pct = 100.0 - 200.0 / 3.0
        # 1/3 ripartito tra genitori e fratelli (genitori almeno 1/4 del totale)
        if genitori > 0 and fratelli == 0:
            g_quota = remaining_pct / genitori
            label += [f"Genitore {i+1}" for i in range(genitori)]
            quota += [g_quota] * genitori
            note = f"Coniuge 2/3, {genitori} genitore/i 1/3 (art. 582 c.c.)."
        elif genitori == 0 and fratelli > 0:
            fr_quota = remaining_pct / fratelli
            label += [f"Fratello/Sorella {i+1}" for i in range(fratelli)]
            quota += [fr_quota] * fratelli
            note = f"Coniuge 2/3, {fratelli} fratello/i 1/3 (art. 582 c.c.)."
        else:
            # Misto: 1/4 totale ai genitori, resto ai fratelli (art. 582)
            ascen_quota = 25.0
            fr_remaining = remaining_pct - ascen_quota
            g_quota = ascen_quota / genitori if genitori > 0 else 0
            fr_quota = fr_remaining / fratelli if fratelli > 0 else 0
            label += [f"Genitore {i+1}" for i in range(genitori)] + [f"Fratello/Sorella {i+1}" for i in range(fratelli)]
            quota += [g_quota] * genitori + [fr_quota] * fratelli
            note = "Coniuge 2/3, 1/4 ai genitori, resto ai fratelli (art. 582 c.c.)."
    elif not coniuge and figli == 0 and genitori > 0:
        # Solo genitori in parti uguali
        g_quota = 100.0 / genitori
        label = [f"Genitore {i+1}" for i in range(genitori)]
        quota = [g_quota] * genitori
        note = f"In assenza di coniuge e figli, i {genitori} genitore/i ereditano in parti uguali (art. 568 c.c.)."
    elif not coniuge and figli == 0 and fratelli > 0:
        # Solo fratelli
        fr_quota = 100.0 / fratelli
        label = [f"Fratello/Sorella {i+1}" for i in range(fratelli)]
        quota = [fr_quota] * fratelli
        note = f"I {fratelli} fratello/i ereditano in parti uguali (art. 570 c.c.)."
    else:
        # Nessun erede legittimo → eredità allo Stato (art. 586)
        label = ["Stato Italiano"]
        quota = [100.0]
        note = "In assenza di eredi entro il 6° grado, l'eredità è devoluta allo Stato (art. 586 c.c.)."

    return {"label": label, "quota_pct": [round(q, 2) for q in quota], "note": note}


def _quote_di_legittima(coniuge: bool, figli: int, genitori: int) -> dict:
    """Art. 536+ c.c. - quote indisponibili (legittima) e disponibile."""
    label, quota = [], []
    disponibile_pct = 100.0
    note = ""

    if coniuge and figli == 0 and genitori == 0:
        # Solo coniuge: 1/2 legittima
        label = ["Coniuge"]
        quota = [50.0]
        disponibile_pct = 50.0
        note = "Coniuge: legittima 1/2, disponibile 1/2 (art. 540 c.c.)."
    elif coniuge and figli == 1:
        # Coniuge 1/4, figlio 1/2
        label = ["Coniuge", "Figlio"]
        quota = [25.0, 50.0]
        disponibile_pct = 25.0
        note = "Coniuge 1/4, unico figlio 1/2, disponibile 1/4 (art. 542 c.c.)."
    elif coniuge and figli >= 2:
        # Coniuge 1/4, figli 1/2 totale ripartito
        f_quota = 50.0 / figli
        label = ["Coniuge"] + [f"Figlio {i+1}" for i in range(figli)]
        quota = [25.0] + [f_quota] * figli
        disponibile_pct = 25.0
        note = f"Coniuge 1/4, {figli} figli si dividono 1/2, disponibile 1/4 (art. 542 c.c.)."
    elif not coniuge and figli == 1:
        # Unico figlio: 1/2 legittima
        label = ["Figlio"]
        quota = [50.0]
        disponibile_pct = 50.0
        note = "Unico figlio: legittima 1/2, disponibile 1/2 (art. 537 c.c.)."
    elif not coniuge and figli >= 2:
        # Più figli: 2/3 ripartito
        f_quota = (200.0 / 3.0) / figli
        label = [f"Figlio {i+1}" for i in range(figli)]
        quota = [f_quota] * figli
        disponibile_pct = 100.0 / 3.0
        note = f"{figli} figli si dividono 2/3, disponibile 1/3 (art. 537 c.c.)."
    elif coniuge and figli == 0 and genitori > 0:
        # Coniuge 1/2, ascendenti 1/4
        ascen_total = 25.0
        g_quota = ascen_total / genitori
        label = ["Coniuge"] + [f"Genitore {i+1}" for i in range(genitori)]
        quota = [50.0] + [g_quota] * genitori
        disponibile_pct = 25.0
        note = f"Coniuge 1/2, ascendenti 1/4, disponibile 1/4 (art. 544 c.c.)."
    elif not coniuge and figli == 0 and genitori > 0:
        # Solo ascendenti: 1/3 legittima
        g_quota = (100.0 / 3.0) / genitori
        label = [f"Genitore {i+1}" for i in range(genitori)]
        quota = [g_quota] * genitori
        disponibile_pct = 200.0 / 3.0
        note = f"Ascendenti: legittima 1/3, disponibile 2/3 (art. 538 c.c.)."
    else:
        # Nessun legittimario: totalmente disponibile
        label = []
        quota = []
        disponibile_pct = 100.0
        note = "Nessun legittimario: il testatore può disporre liberamente di tutto il patrimonio."

    return {
        "label": label,
        "quota_pct": [round(q, 2) for q in quota],
        "disponibile_pct": round(disponibile_pct, 2),
        "note": note,
    }
