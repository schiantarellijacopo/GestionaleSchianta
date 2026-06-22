"""Calcolatore semplificato pensioni INPS (invalidità / inabilità / superstite).

NOTA IMPORTANTE
Questo modulo fornisce stime indicative basate su parametri INPS 2025/2026
e sulle regole generali del calcolo retributivo/contributivo. Non sostituisce
il calcolo ufficiale INPS. Le aliquote, i coefficienti di trasformazione e
i requisiti contributivi sono parametri configurabili.
"""
from datetime import datetime
from typing import Literal, Optional


# Parametri base (INPS 2025/2026 - valori indicativi)
PARAMS = {
    # Pensione di invalidità civile importi mensili 2025 (€)
    "invalidita_civile_mensile_2025": 333.33,
    # Pensione di inabilità INPS: % della retribuzione pensionabile
    "inabilita_perc_retribuzione": 0.80,
    # Pensione superstite (reversibilità) % della pensione del de cuius
    "superstite_solo_coniuge": 0.60,
    "superstite_coniuge_un_figlio": 0.80,
    "superstite_coniuge_due_o_piu_figli": 1.00,
    "superstite_solo_figli_uno": 0.70,
    "superstite_solo_figli_due": 0.80,
    "superstite_solo_figli_tre_o_piu": 1.00,
    # Coefficienti di trasformazione contributivo 2025 (semplificati)
    # Età -> coefficiente
    "coefficienti_trasformazione_2025": {
        57: 0.04475, 58: 0.04594, 59: 0.04719,
        60: 0.04852, 61: 0.04993, 62: 0.05144,
        63: 0.05303, 64: 0.05472, 65: 0.05652,
        66: 0.05846, 67: 0.06055, 68: 0.06281,
        69: 0.06526, 70: 0.06792, 71: 0.07081,
        72: 0.07399,
    },
    # Aliquota IRPEF stimata media
    "irpef_stimata": 0.23,
    # Soglia minima settimane per invalidità (5 anni di cui 3 nell'ultimo quinquennio)
    "settimane_min_invalidita": 260,
    "settimane_min_invalidita_recenti": 156,
}


def _coefficiente_trasformazione(eta: int) -> float:
    table = PARAMS["coefficienti_trasformazione_2025"]
    if eta in table:
        return table[eta]
    if eta < min(table.keys()):
        return table[min(table.keys())]
    return table[max(table.keys())]


def calcola_pensione(
    tipo: Literal["invalidita", "inabilita", "superstite"],
    settimane_contributive: int,
    retribuzione_media_annua: float,
    eta: int,
    percentuale_invalidita: Optional[float] = None,
    numero_familiari: int = 0,
) -> dict:
    """Restituisce un dizionario con il calcolo della pensione.

    L'algoritmo è una stima:
    - Calcola un montante contributivo: 33% * retribuzione * anni contributivi
    - Applica il coefficiente di trasformazione in base all'età
    - Per invalidità/inabilità applica le rispettive percentuali/integrazioni
    - Per la superstite applica la percentuale di reversibilità
    """
    anni = settimane_contributive / 52.0
    montante = retribuzione_media_annua * 0.33 * anni
    coeff = _coefficiente_trasformazione(eta)
    pensione_contributiva_annua = montante * coeff

    requisiti_ok = True
    note = []
    metodologia = ""
    pensione_annua = 0.0

    if tipo == "invalidita":
        metodologia = "Assegno ordinario di invalidità (calcolo contributivo)"
        if settimane_contributive < PARAMS["settimane_min_invalidita"]:
            requisiti_ok = False
            note.append(
                f"Settimane contributive insufficienti: minimo richiesto "
                f"{PARAMS['settimane_min_invalidita']}, presenti {settimane_contributive}."
            )
        # In caso di invalidità civile pura (senza contributi) si usa l'importo base
        if not requisiti_ok:
            pensione_mensile = PARAMS["invalidita_civile_mensile_2025"]
            pensione_annua = pensione_mensile * 13  # 13 mensilità
            metodologia = "Pensione di invalidità civile (importo base 2025)"
        else:
            perc = (percentuale_invalidita or 100) / 100.0
            pensione_annua = pensione_contributiva_annua * perc

    elif tipo == "inabilita":
        metodologia = "Pensione di inabilità (calcolo contributivo + maggiorazione)"
        if settimane_contributive < PARAMS["settimane_min_invalidita"]:
            requisiti_ok = False
            note.append(
                f"Settimane contributive insufficienti per pensione di inabilità: "
                f"minimo {PARAMS['settimane_min_invalidita']} settimane."
            )
        # L'inabilità prevede l'integrazione contributi figurativi fino a 60 anni
        anni_mancanti_60 = max(0, 60 - eta)
        montante_maggiorato = montante + (retribuzione_media_annua * 0.33 * anni_mancanti_60)
        pensione_annua = montante_maggiorato * coeff if requisiti_ok else 0.0
        if anni_mancanti_60:
            note.append(
                f"Integrazione contributi figurativi: +{anni_mancanti_60} anni fino a 60."
            )

    elif tipo == "superstite":
        metodologia = "Pensione ai superstiti (reversibilità)"
        # Stimiamo la pensione di base del de cuius come pensione contributiva
        pensione_base = pensione_contributiva_annua
        # Aliquota in base ai familiari
        if numero_familiari <= 0:
            note.append("Nessun familiare avente diritto: pensione = 0.")
            aliquota = 0.0
        elif numero_familiari == 1:
            aliquota = PARAMS["superstite_solo_coniuge"]
        elif numero_familiari == 2:
            aliquota = PARAMS["superstite_coniuge_un_figlio"]
        else:
            aliquota = PARAMS["superstite_coniuge_due_o_piu_figli"]
        pensione_annua = pensione_base * aliquota
        note.append(f"Aliquota di reversibilità applicata: {aliquota*100:.0f}%")

    pensione_mensile = pensione_annua / 13.0 if pensione_annua else 0.0
    pensione_netta_mensile = pensione_mensile * (1 - PARAMS["irpef_stimata"])

    return {
        "pensione_lorda_mensile": round(pensione_mensile, 2),
        "pensione_lorda_annua": round(pensione_annua, 2),
        "pensione_netta_stimata": round(pensione_netta_mensile, 2),
        "coefficiente_applicato": coeff,
        "metodologia": metodologia,
        "dettaglio": {
            "anni_contributivi": round(anni, 2),
            "montante_contributivo": round(montante, 2),
            "pensione_contributiva_annua_lorda": round(pensione_contributiva_annua, 2),
            "requisiti_contributivi_ok": requisiti_ok,
            "note": note,
        },
    }


def parse_estratto_conto_inps(testo: str) -> dict:
    """Parser semplice per estratti contributivi INPS in testo libero.

    Cerca pattern come "Settimane: 1234" o "Retribuzione: 25000".
    Restituisce {settimane_contributive, retribuzione_media_annua, anni}.
    """
    import re
    settimane = 0
    retribuzione = 0.0
    anni = 0

    # Cerca "Settimane:" o "Settimane utili" o "Totale settimane"
    m = re.search(r"(?:totale\s+)?settimane[^\d]*(\d{2,5})", testo, re.IGNORECASE)
    if m:
        settimane = int(m.group(1))

    # Retribuzione media annua / imponibile
    m = re.search(r"(?:retribuzione|imponibile)[^\d]*([\d.,]{3,})", testo, re.IGNORECASE)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            retribuzione = float(val)
        except ValueError:
            pass

    # Anni
    m = re.search(r"anni\s+(?:contributivi|di\s+contribuzione)[^\d]*(\d{1,2})", testo, re.IGNORECASE)
    if m:
        anni = int(m.group(1))
        if not settimane:
            settimane = anni * 52

    return {
        "settimane_contributive": settimane,
        "retribuzione_media_annua": retribuzione,
        "anni_stimati": anni or (settimane // 52 if settimane else 0),
    }
