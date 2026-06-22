"""Calcolatore Reddito Netto / IRPEF / Contributi Previdenziali (Italia 2026).

Implementa una stima dell'IRPEF e dei contributi previdenziali a partire dal
reddito lordo e dal tipo di lavoratore. Replica il riepilogo "Approfondimento
Redditi" mostrato dal CRM SatorCRM (contributi, IRPEF lorda/netta, detrazioni).

ATTENZIONE: stime indicative. Aliquote e detrazioni 2026 sono valori medi.
"""
from typing import Optional


# === Aliquote contributive medie (lavoratore, anno 2026) ===
ALIQUOTE_CONTRIBUTIVE = {
    "dipendente": 0.0919,        # 9,19% c/dipendente (azienda 23,81%)
    "autonomo": 0.24,            # gestione separata 24%
    "commerciante": 0.24,        # IVS commercianti ~24% (semplificato)
    "artigiano": 0.24,           # IVS artigiani ~24%
    "professionista": 0.16,      # casse professionali medie 14-18%
    "parasubordinato": 0.24,     # gestione separata 24% (no altre coperture)
    "imprenditore": 0.24,
    "pensionato": 0.0,
    "disoccupato": 0.0,
    "studente": 0.0,
    "casalinga": 0.0,
    "altro": 0.0,
}

# Quota a carico azienda (solo per dipendente)
ALIQUOTA_AZIENDA = {
    "dipendente": 0.2381,
}


# === Scaglioni IRPEF 2026 (3 aliquote dal 2024) ===
SCAGLIONI_IRPEF = [
    (28000, 0.23),
    (50000, 0.35),
    (float("inf"), 0.43),
]


def calcola_irpef_lorda(reddito_imponibile: float) -> tuple[float, float]:
    """Calcola IRPEF lorda e aliquota marginale effettiva."""
    if reddito_imponibile <= 0:
        return 0.0, 0.0
    imposta = 0.0
    base = 0.0
    aliquota_marg = 0.0
    for soglia, aliquota in SCAGLIONI_IRPEF:
        if reddito_imponibile <= soglia:
            imposta += (reddito_imponibile - base) * aliquota
            aliquota_marg = aliquota
            break
        else:
            imposta += (soglia - base) * aliquota
            base = soglia
            aliquota_marg = aliquota
    return round(imposta, 2), aliquota_marg


def detrazione_lavoro_dipendente(reddito: float) -> float:
    """Detrazione lavoro dipendente (art. 13 TUIR semplificato 2026)."""
    if reddito <= 15000:
        return max(1955.0, 690.0)  # min 690 / fino 1955
    elif reddito <= 28000:
        return 1910.0 + (1190.0 * (28000 - reddito) / 13000)
    elif reddito <= 50000:
        return 1910.0 * (50000 - reddito) / 22000
    return 0.0


def detrazione_coniuge_a_carico(reddito: float, ha_coniuge: bool) -> float:
    """Detrazione coniuge a carico (semplificato)."""
    if not ha_coniuge:
        return 0.0
    if reddito <= 15000:
        return 800.0 - (110.0 * reddito / 15000)
    elif reddito <= 40000:
        return 690.0
    elif reddito <= 80000:
        return 690.0 * (80000 - reddito) / 40000
    return 0.0


def calcola_redditi(
    reddito_lordo: float,
    tipo_lavoratore: str = "dipendente",
    altri_redditi: float = 0.0,
    oneri_deducibili: float = 0.0,
    oneri_fondo_pensione: float = 0.0,
    altre_detrazioni: float = 0.0,
    ha_coniuge_a_carico: bool = False,
    numero_figli_a_carico: int = 0,
    regime_forfettario: bool = False,
) -> dict:
    """Calcolo completo: contributi, IRPEF, reddito netto."""
    tipo = (tipo_lavoratore or "altro").lower()
    aliquota_lav = ALIQUOTE_CONTRIBUTIVE.get(tipo, 0.0)
    aliquota_az = ALIQUOTA_AZIENDA.get(tipo, 0.0)

    reddito_totale = reddito_lordo + altri_redditi

    if regime_forfettario:
        # Forfettario: imposta sostitutiva 15% (5% startup) - semplificato 15%
        contributi_lav = round(reddito_lordo * 0.2598, 2)  # Gestione separata se prof
        contributi_az = 0.0
        coefficiente_redditività = 0.78  # commerciante
        reddito_imponibile = reddito_lordo * coefficiente_redditività - contributi_lav
        irpef_lorda = round(max(reddito_imponibile, 0) * 0.15, 2)
        irpef_netta = irpef_lorda
        reddito_netto = round(reddito_lordo - contributi_lav - irpef_netta, 2)
        return {
            "tipo_lavoratore": tipo,
            "regime_forfettario": True,
            "reddito_lordo": round(reddito_lordo, 2),
            "altri_redditi": round(altri_redditi, 2),
            "contributi_lavoratore": contributi_lav,
            "contributi_azienda": 0.0,
            "aliquota_contributiva_lavoratore_pct": round(0.2598 * 100, 2),
            "aliquota_contributiva_azienda_pct": 0.0,
            "reddito_imponibile": round(reddito_imponibile, 2),
            "irpef_lorda": irpef_lorda,
            "irpef_netta": irpef_netta,
            "aliquota_irpef_marginale_pct": 15.0,
            "detrazione_lavoro_dipendente": 0.0,
            "detrazione_coniuge": 0.0,
            "detrazione_figli": 0.0,
            "altre_detrazioni": 0.0,
            "reddito_netto": reddito_netto,
        }

    # Regime ordinario
    contributi_lav = round(reddito_lordo * aliquota_lav, 2)
    contributi_az = round(reddito_lordo * aliquota_az, 2)

    # Base imponibile IRPEF
    reddito_imponibile = max(0.0, reddito_totale - contributi_lav - oneri_deducibili - oneri_fondo_pensione)
    irpef_lorda, aliquota_marg = calcola_irpef_lorda(reddito_imponibile)

    # Detrazioni
    det_lav_dip = detrazione_lavoro_dipendente(reddito_imponibile) if tipo == "dipendente" else 0.0
    det_coniuge = detrazione_coniuge_a_carico(reddito_imponibile, ha_coniuge_a_carico)
    # Detrazioni figli a carico: dal 2022 sostituite da Assegno Unico (NON deducibili)
    det_figli = 0.0  # nota: "DA 2022 ASSEGNO UNICO NON CALCOLABILE"

    detrazioni_totali = round(det_lav_dip + det_coniuge + det_figli + altre_detrazioni, 2)
    irpef_netta = round(max(0.0, irpef_lorda - detrazioni_totali), 2)
    reddito_netto = round(reddito_lordo + altri_redditi - contributi_lav - irpef_netta, 2)

    return {
        "tipo_lavoratore": tipo,
        "regime_forfettario": False,
        "reddito_lordo": round(reddito_lordo, 2),
        "altri_redditi": round(altri_redditi, 2),
        "contributi_lavoratore": contributi_lav,
        "contributi_azienda": contributi_az,
        "aliquota_contributiva_lavoratore_pct": round(aliquota_lav * 100, 2),
        "aliquota_contributiva_azienda_pct": round(aliquota_az * 100, 2),
        "reddito_imponibile": round(reddito_imponibile, 2),
        "irpef_lorda": irpef_lorda,
        "irpef_netta": irpef_netta,
        "aliquota_irpef_marginale_pct": round(aliquota_marg * 100, 2),
        "detrazione_lavoro_dipendente": round(det_lav_dip, 2),
        "detrazione_coniuge": round(det_coniuge, 2),
        "detrazione_figli": det_figli,
        "altre_detrazioni": round(altre_detrazioni, 2),
        "reddito_netto": reddito_netto,
    }


def calcola_scoperture_pensionistiche(
    reddito_lordo: float,
    altri_redditi: float,
    dividendi: float,
    pensione_invalidita_annua: float,
    pensione_inabilita_annua: float,
    pensione_superstite_annua: float,
    pensione_vecchiaia_annua: float,
    eta_attuale: int,
    eta_pensionamento: int = 67,
    eta_max_target: int = 70,
    eta_coniuge: Optional[int] = None,
    eta_figlio_piu_piccolo: Optional[int] = None,
    debiti: float = 0.0,
    has_coniuge: bool = False,
    has_convivente: bool = False,
    has_figli: bool = False,
) -> dict:
    """Calcola le scoperture pensionistiche (problema di oggi / del futuro)
    e il capitale da assicurare per coprirle.

    Replica la logica del CRM SatorCRM (Riepilogo Pensionistico).
    """
    reddito_complessivo = reddito_lordo + altri_redditi + dividendi
    reddito_mensile = reddito_complessivo / 13.0

    def mensile(annuo): return annuo / 13.0

    anni_a_70 = max(0, eta_max_target - eta_attuale)

    # --- Invalidità (problema di oggi) ---
    invalid_scop_annua = max(0.0, reddito_complessivo - pensione_invalidita_annua)
    invalid_capitale = round(invalid_scop_annua * anni_a_70, 2)

    # --- Inabilità (problema di oggi) ---
    inabil_scop_annua = max(0.0, reddito_complessivo - pensione_inabilita_annua)
    inabil_capitale = round(inabil_scop_annua * anni_a_70, 2)

    # --- Superstiti (premorienza) ---
    if has_coniuge:
        sup_scop_annua = max(0.0, reddito_lordo - pensione_superstite_annua)
        anni_coniuge_70 = max(0, eta_max_target - (eta_coniuge or eta_attuale))
        anni_figlio_25 = max(0, 25 - (eta_figlio_piu_piccolo or 0)) if has_figli else 0
        # Massimo tra i due scenari
        c_coniuge = sup_scop_annua * anni_coniuge_70
        c_figlio = sup_scop_annua * anni_figlio_25
        sup_capitale = round(max(c_coniuge, c_figlio) + debiti, 2)
    elif has_convivente:
        sup_scop_annua = max(0.0, reddito_lordo - pensione_superstite_annua)
        anni_conv_70 = max(0, eta_max_target - (eta_coniuge or eta_attuale))
        anni_figlio_25 = max(0, 25 - (eta_figlio_piu_piccolo or 0)) if has_figli else 0
        c_conv = reddito_lordo * anni_conv_70
        c_figlio = sup_scop_annua * anni_figlio_25
        sup_capitale = round(max(c_conv, c_figlio) + debiti, 2)
    else:
        # Single senza figli: minimo 500.000 + debiti, oppure 20.000 minimo
        sup_scop_annua = max(0.0, reddito_lordo - pensione_superstite_annua)
        sup_capitale = round(max(500000.0, 20000.0) + debiti, 2)

    # --- Vecchiaia (problema del futuro) ---
    vecchiaia_scop_annua = max(0.0, reddito_complessivo - pensione_vecchiaia_annua)
    vecchiaia_scop_mensile = mensile(vecchiaia_scop_annua)

    return {
        "reddito_complessivo_annuo": round(reddito_complessivo, 2),
        "reddito_mensile": round(reddito_mensile, 2),
        "anni_a_70": anni_a_70,
        "invalidita": {
            "pensione_annua": round(pensione_invalidita_annua, 2),
            "pensione_mensile": round(mensile(pensione_invalidita_annua), 2),
            "scopertura_annua": round(invalid_scop_annua, 2),
            "scopertura_mensile": round(mensile(invalid_scop_annua), 2),
            "capitale_da_assicurare": invalid_capitale,
            "copertura_pct": round((pensione_invalidita_annua / reddito_complessivo * 100) if reddito_complessivo else 0, 1),
        },
        "inabilita": {
            "pensione_annua": round(pensione_inabilita_annua, 2),
            "pensione_mensile": round(mensile(pensione_inabilita_annua), 2),
            "scopertura_annua": round(inabil_scop_annua, 2),
            "scopertura_mensile": round(mensile(inabil_scop_annua), 2),
            "capitale_da_assicurare": inabil_capitale,
            "copertura_pct": round((pensione_inabilita_annua / reddito_complessivo * 100) if reddito_complessivo else 0, 1),
        },
        "superstiti": {
            "pensione_annua": round(pensione_superstite_annua, 2),
            "pensione_mensile": round(mensile(pensione_superstite_annua), 2),
            "scopertura_annua": round(sup_scop_annua, 2),
            "scopertura_mensile": round(mensile(sup_scop_annua), 2),
            "capitale_da_assicurare": sup_capitale,
            "copertura_pct": round((pensione_superstite_annua / reddito_lordo * 100) if reddito_lordo else 0, 1),
            "debiti_inclusi": round(debiti, 2),
        },
        "vecchiaia": {
            "pensione_annua": round(pensione_vecchiaia_annua, 2),
            "pensione_mensile": round(mensile(pensione_vecchiaia_annua), 2),
            "scopertura_annua": round(vecchiaia_scop_annua, 2),
            "scopertura_mensile": round(vecchiaia_scop_mensile, 2),
            "eta_pensionamento": eta_pensionamento,
            "copertura_pct": round((pensione_vecchiaia_annua / reddito_complessivo * 100) if reddito_complessivo else 0, 1),
        },
    }
