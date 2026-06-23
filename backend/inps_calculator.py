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
    """Parser estratti contributivi INPS in testo libero.

    Estrae: anagrafica, settimane/giorni totali, retribuzione media, anni stimati,
    PERIODI contributivi dettagliati, STORICO redditi raggruppato per anno,
    TOTALI versati e montante stimato.
    """
    import re

    result: dict = {
        "settimane_contributive": 0,
        "giorni_contributivi": 0,
        "retribuzione_media_annua": 0.0,
        "anni_stimati": 0,
        "righe_contributive": 0,
        "periodi_contributivi": [],   # [{fondo, inizio_periodo, fine_periodo, settimane, retribuzione, contributi}]
        "storico_redditi": [],         # [{anno, reddito, contributi, cassa}]
        "totale_versato": 0.0,
        "totale_retribuzioni": 0.0,
        "montante_stimato": 0.0,
    }

    # === Header anagrafico ===
    m = re.search(r"Estratto\s+Conto\s+Previdenziale\s+([A-ZÀ-Ÿ' ]+?)(?:\n|\s+nato)", testo)
    if m:
        full = m.group(1).strip()
        parts = full.split()
        if len(parts) >= 2:
            result["cognome"] = parts[0]
            result["nome"] = " ".join(parts[1:]).strip()
        else:
            result["cognome"] = full

    m = re.search(r"\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b", testo)
    if m:
        result["codice_fiscale"] = m.group(1)

    m = re.search(r"nato\s+a\s+([A-ZÀ-Ÿ' ]+?)\s+\(([A-Z]{2})\)", testo, re.IGNORECASE)
    if m:
        result["comune_nascita"] = m.group(1).strip().title()
        result["provincia_nascita"] = m.group(2)

    m = re.search(r"\bil\s+(\d{2}/\d{2}/\d{4})\b", testo)
    if m:
        gg, mm, aa = m.group(1).split("/")
        result["data_nascita"] = f"{aa}-{mm}-{gg}"

    if result.get("codice_fiscale"):
        try:
            mese_cf = result["codice_fiscale"][9:11]
            result["sesso"] = "F" if int(mese_cf) > 31 else "M"
        except Exception:
            pass

    m = re.search(r"residente\s+in\s+(.+?)\n\s*(\d{5})\s+([A-ZÀ-Ÿ' ]+?)\s+\(([A-Z]{2})\)",
                  testo, re.IGNORECASE)
    if m:
        result["indirizzo"] = m.group(1).strip()
        result["cap"] = m.group(2)
        result["comune"] = m.group(3).strip().title()
        result["provincia"] = m.group(4)

    # === Periodi contributivi ===
    # Parser multi-formato:
    # - Formato INPS classico: "01/01/2020 31/12/2020 sett. 52 ... 25000,00 6500,00"
    # - Formato SatorCRM/HubSicura: "Commerciante 01/01/2020 31/12/2020"
    # - Formato compatto: "Dipendente 01/2020 12/2020 ..."
    # - Riga senza retribuzione: "01/01/2020 31/12/2020"
    settimane_tot = 0
    giorni_tot = 0
    retribuzioni = []
    primo_inizio = None
    fondi_noti = (
        "Commerciante", "Artigiano", "Dipendente", "Autonomo", "Parasubordinato",
        "Professionista", "Imprenditore", "Coltivatore", "Lavoratore",
        "Gestione separata", "Lavoro dipendente", "Inps", "Inpgi", "Enasarco",
        "Enpacl", "Enpam", "Inarcassa", "Cassa Forense", "Casagit",
    )
    redditi_per_anno: dict = {}
    periodi_seen: set = set()

    def _add_periodo(dal_iso, al_iso, fondo, sett, retrib, contrib):
        nonlocal primo_inizio, settimane_tot
        key = (dal_iso, al_iso, fondo)
        if key in periodi_seen:
            return
        periodi_seen.add(key)
        if primo_inizio is None or dal_iso < primo_inizio:
            primo_inizio = dal_iso
        settimane_tot += sett
        if retrib > 0:
            retribuzioni.append(retrib)
        result["periodi_contributivi"].append({
            "fondo": (fondo or "Lavoratore dipendente")[:80],
            "inizio_periodo": dal_iso,
            "fine_periodo": al_iso,
            "settimane": sett,
            "retribuzione": round(retrib, 2),
            "contributi": round(contrib, 2),
            "riscattato": False,
        })
        anno = dal_iso[:4]
        slot = redditi_per_anno.setdefault(anno, {"reddito": 0.0, "contributi": 0.0, "cassa": (fondo or "")[:40]})
        slot["reddito"] += retrib
        slot["contributi"] += contrib
        result["righe_contributive"] += 1

    def _to_iso(dmy: str) -> str:
        gg, mm, aa = dmy.split("/")
        return f"{aa}-{mm}-{gg}"

    # FORMATO 1 - INPS classico con settimane/giorni + retribuzione
    re_full = re.compile(
        r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(.+?)(sett\.?|giorni)\s+(\d+)\s+(\d+)?\s*([\d.,]+)\s+([\d.,]+)?",
        re.IGNORECASE,
    )
    for m in re_full.finditer(testo):
        dal, al, fondo_raw, unita, qty, _utili, retrib, contrib = m.groups()
        try:
            n = int(qty)
            sett = n if unita.lower().startswith("sett") else n // 7
            if not unita.lower().startswith("sett"):
                giorni_tot += n
            fondo = re.sub(r"\s+", " ", (fondo_raw or "")).strip()
            # taglia "fondo" se contiene numeri (errori di parse)
            fondo = re.sub(r"\d+", "", fondo).strip() or "Lavoratore dipendente"
            r = _parse_num(retrib)
            c = _parse_num(contrib) if contrib else 0.0
            _add_periodo(_to_iso(dal), _to_iso(al), fondo[:60], sett, r, c)
        except Exception:
            continue

    # FORMATO 2 - SatorCRM / layout senza settimane/retribuzione:
    # "FONDO  DD/MM/YYYY  DD/MM/YYYY  ..."
    re_fondo_date = re.compile(
        r"(?:^|\n)\s*(" + "|".join(fondi_noti) + r")[^\n\d]*?(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4}|\(nessun valore\)|in corso|ancora aperto)",
        re.IGNORECASE,
    )
    today = "2099-12-31"
    for m in re_fondo_date.finditer(testo):
        fondo, dal, al = m.groups()
        try:
            dal_iso = _to_iso(dal)
            if al in ("(nessun valore)", "in corso", "ancora aperto"):
                al_iso = None
            else:
                al_iso = _to_iso(al)
            # stima settimane: 52 se anno completo
            if al_iso and al_iso[:4] == dal_iso[:4]:
                sett = 52
            elif al_iso:
                from datetime import date
                d1 = date.fromisoformat(dal_iso)
                d2 = date.fromisoformat(al_iso)
                sett = ((d2 - d1).days + 1) // 7
            else:
                sett = 52  # periodo aperto, stima
            _add_periodo(dal_iso, al_iso or today, fondo.title(), sett, 0.0, 0.0)
        except Exception:
            continue

    # FORMATO 3 - Solo coppie "DD/MM/YYYY DD/MM/YYYY" su righe orfane (fallback)
    if not result["periodi_contributivi"]:
        re_only_dates = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})")
        for m in re_only_dates.finditer(testo):
            dal, al = m.groups()
            try:
                _add_periodo(_to_iso(dal), _to_iso(al), "Lavoratore dipendente", 52, 0.0, 0.0)
            except Exception:
                continue

    # FORMATO 4 - Tabella STORICO REDDITI separata (pattern "ANNO ... importo")
    # es: "2023  Commerciante  35.000,00"
    re_redd_anno = re.compile(
        r"(?:^|\n)\s*(20\d{2}|19\d{2})\s+(?:(" + "|".join(fondi_noti) + r")\s+)?([\d.]{3,}(?:[.,]\d{1,2})?)\s+([\d.]{1,}(?:[.,]\d{1,2})?)?",
        re.IGNORECASE,
    )
    for m in re_redd_anno.finditer(testo):
        anno, cassa, redd_raw, contrib_raw = m.groups()
        try:
            r = _parse_num(redd_raw)
            c = _parse_num(contrib_raw) if contrib_raw else 0.0
            # filtra valori che non sono redditi (troppo piccoli o troppo grandi)
            if r < 1000 or r > 500000:
                continue
            slot = redditi_per_anno.setdefault(anno, {"reddito": 0.0, "contributi": 0.0, "cassa": (cassa or "").title()})
            # Se già aggregato dai periodi non sovrascrivere
            if slot["reddito"] == 0:
                slot["reddito"] = r
                slot["contributi"] = c
                if cassa:
                    slot["cassa"] = cassa.title()
                if r > 0:
                    retribuzioni.append(r)
        except Exception:
            continue

    settimane_tot += giorni_tot // 7
    result["settimane_contributive"] = settimane_tot
    result["giorni_contributivi"] = giorni_tot
    result["anni_stimati"] = settimane_tot // 52 if settimane_tot else 0
    if retribuzioni:
        result["retribuzione_media_annua"] = round(sum(retribuzioni) / len(retribuzioni), 2)
    if primo_inizio:
        result["data_inizio_contribuzione"] = primo_inizio

    # === Storico redditi annuale (ordinato decrescente) ===
    storico = []
    for anno, dati in sorted(redditi_per_anno.items(), reverse=True):
        storico.append({
            "anno": int(anno),
            "reddito": round(dati["reddito"], 2),
            "contributi": round(dati["contributi"], 2),
            "cassa": dati["cassa"],
        })
    result["storico_redditi"] = storico

    # === Totali ===
    result["totale_retribuzioni"] = round(sum(retribuzioni), 2)
    result["totale_versato"] = round(sum(p["contributi"] for p in result["periodi_contributivi"]), 2)
    # Montante stimato: 33% medio della retribuzione totale (aliquota commerciante)
    if result["totale_versato"] > 0:
        result["montante_stimato"] = result["totale_versato"]
    else:
        result["montante_stimato"] = round(result["totale_retribuzioni"] * 0.33, 2)

    return result


def _parse_num(s: str) -> float:
    """Parser di numeri italiani (es. '12.345,67' o '12345.67' o '12345,67')."""
    if not s:
        return 0.0
    s = s.strip()
    # Caso 1.234,56 (italiano) -> rimuovi '.', sostituisci ',' con '.'
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_estratto_contributivo(pdf_bytes: bytes) -> dict:
    """Estrae testo da PDF dell'estratto contributivo INPS e ritorna i dati strutturati."""
    import pdfplumber
    from io import BytesIO
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return parse_estratto_conto_inps(text)
