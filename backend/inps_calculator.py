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


# Coefficienti di rivalutazione INPS annuali (variazione media quinquennale PIL nominale)
# Fonte: Ministero del Lavoro - Comunicati ufficiali
TASSI_RIVALUTAZIONE_INPS = {
    2009: 0.033147, 2010: 0.017935, 2011: 0.016244, 2012: 0.037935,
    2013: 0.016126, 2014: 0.010676, 2015: 0.005063, 2016: -0.001927,
    2017: -0.002155, 2018: 0.007549, 2019: 0.013500, 2020: 0.018294,
    2021: 0.017270, 2022: 0.047770, 2023: 0.063275, 2024: 0.038666,
    2025: 0.020000, 2026: 0.020000,  # stima
}


def calcola_montante_rivalutato(storico_redditi: list, aliquota: float = 0.33) -> float:
    """Calcola il montante contributivo rivalutato anno per anno usando i tassi
    INPS ufficiali (variazione media quinquennale del PIL nominale).

    Formula INPS (semplificata):
      Per ogni anno: contributo[anno] = reddito[anno] × aliquota
      Montante[anno_corrente] = somma(contributo[anno] × ∏(1 + tasso[t])
                                       per t da anno+1 ad anno_corrente)
    """
    if not storico_redditi:
        return 0.0
    anno_corrente = datetime.now().year
    montante = 0.0
    for r in storico_redditi:
        anno = int(r.get("anno", 0))
        reddito = float(r.get("reddito") or 0)
        # Usa contributi reali se disponibili, altrimenti reddito × aliquota
        contributo = float(r.get("contributi") or 0) or (reddito * aliquota)
        # Rivaluta dall'anno+1 fino all'anno corrente
        coeff = 1.0
        for y in range(anno + 1, anno_corrente + 1):
            tasso = TASSI_RIVALUTAZIONE_INPS.get(y, 0.02)  # 2% default per anni mancanti
            coeff *= (1 + tasso)
        montante += contributo * coeff
    return round(montante, 2)



def _calcola_invalidita(
    *, settimane_contributive: int, montante: float,
    pensione_contributiva_annua: float, percentuale_invalidita: Optional[float],
) -> tuple[float, str, bool, list[str]]:
    """Branch invalidità — ritorna (pensione_annua, metodologia, requisiti_ok, note)."""
    note: list[str] = []
    requisiti_ok = settimane_contributive >= PARAMS["settimane_min_invalidita"]
    if not requisiti_ok:
        note.append(
            f"Settimane contributive insufficienti: minimo richiesto "
            f"{PARAMS['settimane_min_invalidita']}, presenti {settimane_contributive}."
        )
        pensione_annua = PARAMS["invalidita_civile_mensile_2025"] * 13
        return pensione_annua, "Pensione di invalidità civile (importo base 2025)", False, note
    perc = (percentuale_invalidita or 100) / 100.0
    pensione_annua = pensione_contributiva_annua * perc
    return pensione_annua, "Assegno ordinario di invalidità (calcolo contributivo)", True, note


def _calcola_inabilita(
    *, settimane_contributive: int, montante: float, retribuzione_media_annua: float,
    eta: int, coeff: float,
) -> tuple[float, str, bool, list[str]]:
    """Branch inabilità — integra contributi figurativi fino a 60 anni."""
    note: list[str] = []
    requisiti_ok = settimane_contributive >= PARAMS["settimane_min_invalidita"]
    if not requisiti_ok:
        note.append(
            f"Settimane contributive insufficienti per pensione di inabilità: "
            f"minimo {PARAMS['settimane_min_invalidita']} settimane."
        )
    anni_mancanti_60 = max(0, 60 - eta)
    if anni_mancanti_60:
        note.append(f"Integrazione contributi figurativi: +{anni_mancanti_60} anni fino a 60.")
    montante_maggiorato = montante + (retribuzione_media_annua * 0.33 * anni_mancanti_60)
    pensione_annua = montante_maggiorato * coeff if requisiti_ok else 0.0
    return pensione_annua, "Pensione di inabilità (calcolo contributivo + maggiorazione)", requisiti_ok, note


def _aliquota_superstite(numero_familiari: int) -> tuple[float, Optional[str]]:
    """Ritorna (aliquota, note_msg) in base al numero di familiari."""
    if numero_familiari <= 0:
        return 0.0, "Nessun familiare avente diritto: pensione = 0."
    if numero_familiari == 1:
        return PARAMS["superstite_solo_coniuge"], None
    if numero_familiari == 2:
        return PARAMS["superstite_coniuge_un_figlio"], None
    return PARAMS["superstite_coniuge_due_o_piu_figli"], None


def _calcola_superstite(
    *, pensione_contributiva_annua: float, numero_familiari: int,
) -> tuple[float, str, bool, list[str]]:
    """Branch reversibilità ai superstiti."""
    note: list[str] = []
    aliquota, note_msg = _aliquota_superstite(numero_familiari)
    if note_msg:
        note.append(note_msg)
    note.append(f"Aliquota di reversibilità applicata: {aliquota*100:.0f}%")
    return pensione_contributiva_annua * aliquota, "Pensione ai superstiti (reversibilità)", True, note


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
    - Delega a `_calcola_invalidita` / `_calcola_inabilita` / `_calcola_superstite`
      la logica specifica del singolo tipo di pensione.
    """
    anni = settimane_contributive / 52.0
    montante = retribuzione_media_annua * 0.33 * anni
    coeff = _coefficiente_trasformazione(eta)
    pensione_contributiva_annua = montante * coeff

    if tipo == "invalidita":
        pensione_annua, metodologia, requisiti_ok, note = _calcola_invalidita(
            settimane_contributive=settimane_contributive,
            montante=montante,
            pensione_contributiva_annua=pensione_contributiva_annua,
            percentuale_invalidita=percentuale_invalidita,
        )
    elif tipo == "inabilita":
        pensione_annua, metodologia, requisiti_ok, note = _calcola_inabilita(
            settimane_contributive=settimane_contributive,
            montante=montante,
            retribuzione_media_annua=retribuzione_media_annua,
            eta=eta,
            coeff=coeff,
        )
    elif tipo == "superstite":
        pensione_annua, metodologia, requisiti_ok, note = _calcola_superstite(
            pensione_contributiva_annua=pensione_contributiva_annua,
            numero_familiari=numero_familiari,
        )
    else:
        pensione_annua, metodologia, requisiti_ok, note = 0.0, "", False, [f"Tipo pensione non gestito: {tipo}"]

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
    result: dict = {
        "settimane_contributive": 0,
        "giorni_contributivi": 0,
        "retribuzione_media_annua": 0.0,
        "anni_stimati": 0,
        "righe_contributive": 0,
        "periodi_contributivi": [],
        "storico_redditi": [],
        "totale_versato": 0.0,
        "totale_retribuzioni": 0.0,
        "montante_stimato": 0.0,
    }

    _parse_anagrafica(testo, result)
    state = _EstrattoState(result)
    _parse_periodi_formato_inps(testo, state)
    _parse_periodi_parasubordinati(testo, state)
    _parse_periodi_satorcrm(testo, state)
    _parse_periodi_fallback_date(testo, state)
    _parse_storico_redditi_tabella(testo, state)
    _consolida_totali(state)
    return result


def parse_estratto_contributivo(pdf_bytes: bytes) -> dict:
    """Estrae testo da PDF dell'estratto contributivo INPS e ritorna i dati strutturati."""
    import pdfplumber
    from io import BytesIO
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return parse_estratto_conto_inps(text)


# ---------------------------------------------------------------------------
# Helpers di supporto al parsing
# ---------------------------------------------------------------------------
_FONDI_NOTI = (
    "Commerciante", "Artigiano", "Dipendente", "Autonomo", "Parasubordinato",
    "Professionista", "Imprenditore", "Coltivatore", "Lavoratore",
    "Gestione separata", "Lavoro dipendente", "Inps", "Inpgi", "Enasarco",
    "Enpacl", "Enpam", "Inarcassa", "Cassa Forense", "Casagit",
)


def _to_iso(dmy: str) -> str:
    gg, mm, aa = dmy.split("/")
    return f"{aa}-{mm}-{gg}"


def _parse_num(s: str) -> float:
    """Parser di numeri italiani (es. '12.345,67' o '12345.67' o '12345,67')."""
    if not s:
        return 0.0
    s = s.strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


class _EstrattoState:
    """Mutable state condivisa tra le funzioni di parsing del singolo estratto."""

    def __init__(self, result: dict):
        self.result = result
        self.settimane_tot = 0
        self.giorni_tot = 0
        self.retribuzioni: list[float] = []
        self.primo_inizio: Optional[str] = None
        self.redditi_per_anno: dict[str, dict] = {}
        self.periodi_seen: set = set()

    def add_periodo(self, dal_iso: str, al_iso: str, fondo: str,
                    sett: int, retrib: float, contrib: float) -> None:
        key = (dal_iso, al_iso, fondo)
        if key in self.periodi_seen:
            return
        self.periodi_seen.add(key)
        if self.primo_inizio is None or dal_iso < self.primo_inizio:
            self.primo_inizio = dal_iso
        self.settimane_tot += sett
        if retrib > 0:
            self.retribuzioni.append(retrib)
        self.result["periodi_contributivi"].append({
            "fondo": (fondo or "Lavoratore dipendente")[:80],
            "inizio_periodo": dal_iso,
            "fine_periodo": al_iso,
            "settimane": sett,
            "retribuzione": round(retrib, 2),
            "contributi": round(contrib, 2),
            "riscattato": False,
        })
        anno = dal_iso[:4]
        slot = self.redditi_per_anno.setdefault(
            anno,
            {"reddito": 0.0, "contributi": 0.0, "settimane": 0, "cassa": (fondo or "")[:40]},
        )
        slot["reddito"] += retrib
        slot["contributi"] += contrib
        slot["settimane"] += sett
        self.result["righe_contributive"] += 1


# ---------------------------------------------------------------------------
# 1. Header anagrafico
# ---------------------------------------------------------------------------
def _parse_anagrafica(testo: str, result: dict) -> None:
    import re
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
        except (ValueError, IndexError):
            pass

    m = re.search(
        r"residente\s+in\s+(.+?)\n\s*(\d{5})\s+([A-ZÀ-Ÿ' ]+?)\s+\(([A-Z]{2})\)",
        testo, re.IGNORECASE,
    )
    if m:
        result["indirizzo"] = m.group(1).strip()
        result["cap"] = m.group(2)
        result["comune"] = m.group(3).strip().title()
        result["provincia"] = m.group(4)


# ---------------------------------------------------------------------------
# 2. Periodi - formato INPS classico
# ---------------------------------------------------------------------------
def _unita_a_settimane(qty: int, unita: str, state: _EstrattoState) -> int:
    """Converte la quantità nella sua espressione in settimane.
    Aggiorna giorni_tot in state se l'unità è 'giorni'."""
    u = unita.lower().rstrip(".")
    if u.startswith("sett"):
        return qty
    if u == "mesi":
        return int(round(qty * 52 / 12))
    state.giorni_tot += qty
    return qty // 7


def _parse_periodi_formato_inps(testo: str, state: _EstrattoState) -> None:
    """Formato INPS reale: 'DD/MM/YYYY DD/MM/YYYY <fondo> (sett.|mesi|giorni) N N,000 X.XXX,XX [AZIENDA]'."""
    import re
    re_full = re.compile(
        r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+([A-Za-zÀ-ÿ'\. ]+?)\s+"
        r"(sett\.?|mesi|giorni)\s+(\d+)\s+([\d.,]+)(?:\s+([\d.,]+))?(?:\s+(.+?))?(?=\n|$)",
        re.IGNORECASE | re.MULTILINE,
    )
    for m in re_full.finditer(testo):
        dal, al, fondo_raw, unita, qty, _utili, retrib, _azienda = m.groups()
        try:
            sett = _unita_a_settimane(int(qty), unita, state)
            fondo = re.sub(r"\s+", " ", (fondo_raw or "")).strip()[:80] or "Lavoratore dipendente"
            r = _parse_num(retrib) if retrib else 0.0
            if r > 200000:  # filtro: parse errato
                r = 0.0
            state.add_periodo(_to_iso(dal), _to_iso(al), fondo, sett, r, 0.0)
        except (ValueError, IndexError):
            continue


# ---------------------------------------------------------------------------
# 3. Parasubordinati
# ---------------------------------------------------------------------------
def _parse_periodi_parasubordinati(testo: str, state: _EstrattoState) -> None:
    """Formato Parasubordinati: 'ANNO REDDITO COMMITTENTE Attivita' di collaborazione CONTRIB ALIQ'."""
    import re
    re_paras = re.compile(
        r"(?:^|\n)\s*(20\d{2}|19\d{2})\s+([\d.]+,\d{2})\s+(.+?)\s+"
        r"(Attivita['\s]*di\s+collaborazione|Collaborazione|Prestazione)\s+([\d.]+,\d{2})\s+([\d,]+)",
        re.IGNORECASE,
    )
    for m in re_paras.finditer(testo):
        anno, redd_raw, _committente, _tipo, contrib_raw, _aliq = m.groups()
        try:
            r = _parse_num(redd_raw)
            c = _parse_num(contrib_raw)
            if not (1000 <= r <= 500000):
                continue
            slot = state.redditi_per_anno.setdefault(
                anno, {"reddito": 0.0, "contributi": 0.0, "cassa": "Gestione separata"},
            )
            slot["reddito"] += r
            slot["contributi"] += c
            slot["cassa"] = "Gestione separata"
            state.retribuzioni.append(r)
            state.add_periodo(f"{anno}-01-01", f"{anno}-12-31",
                              "Gestione separata", 52, r, c)
        except (ValueError, KeyError):
            continue


# ---------------------------------------------------------------------------
# 4. SatorCRM (fondo+date, niente settimane esplicite)
# ---------------------------------------------------------------------------
def _stima_settimane(dal_iso: str, al_iso: Optional[str]) -> int:
    """Stima settimane fra due date ISO. Anno aperto → 52, single-year → 52."""
    if al_iso is None:
        return 52
    if al_iso[:4] == dal_iso[:4]:
        return 52
    from datetime import date
    try:
        d1 = date.fromisoformat(dal_iso)
        d2 = date.fromisoformat(al_iso)
        return max(0, ((d2 - d1).days + 1) // 7)
    except ValueError:
        return 52


def _parse_periodi_satorcrm(testo: str, state: _EstrattoState) -> None:
    """Formato SatorCRM senza retribuzione: 'FONDO  DD/MM/YYYY  DD/MM/YYYY'."""
    import re
    re_fondo_date = re.compile(
        r"(?:^|\n)\s*(" + "|".join(_FONDI_NOTI) + r")[^\n\d]*?"
        r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4}|\(nessun valore\)|in corso|ancora aperto)",
        re.IGNORECASE,
    )
    today = "2099-12-31"
    for m in re_fondo_date.finditer(testo):
        fondo, dal, al = m.groups()
        try:
            dal_iso = _to_iso(dal)
            al_iso = None if al in ("(nessun valore)", "in corso", "ancora aperto") else _to_iso(al)
            sett = _stima_settimane(dal_iso, al_iso)
            state.add_periodo(dal_iso, al_iso or today, fondo.title(), sett, 0.0, 0.0)
        except (ValueError, IndexError):
            continue


# ---------------------------------------------------------------------------
# 5. Solo coppie di date (fallback)
# ---------------------------------------------------------------------------
def _parse_periodi_fallback_date(testo: str, state: _EstrattoState) -> None:
    """Fallback: due date consecutive su una riga, nessun altro pattern matchato."""
    import re
    if state.result["periodi_contributivi"]:
        return
    re_only_dates = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})")
    for m in re_only_dates.finditer(testo):
        dal, al = m.groups()
        try:
            state.add_periodo(_to_iso(dal), _to_iso(al),
                              "Lavoratore dipendente", 52, 0.0, 0.0)
        except (ValueError, IndexError):
            continue


# ---------------------------------------------------------------------------
# 6. Storico redditi tabellare
# ---------------------------------------------------------------------------
def _parse_storico_redditi_tabella(testo: str, state: _EstrattoState) -> None:
    """Formato tabella separata: 'ANNO [FONDO] REDDITO [CONTRIB]'."""
    import re
    re_redd_anno = re.compile(
        r"(?:^|\n)\s*(20\d{2}|19\d{2})\s+(?:(" + "|".join(_FONDI_NOTI) + r")\s+)?"
        r"([\d.]{3,}(?:[.,]\d{1,2})?)\s+([\d.]{1,}(?:[.,]\d{1,2})?)?",
        re.IGNORECASE,
    )
    for m in re_redd_anno.finditer(testo):
        anno, cassa, redd_raw, contrib_raw = m.groups()
        try:
            r = _parse_num(redd_raw)
            c = _parse_num(contrib_raw) if contrib_raw else 0.0
            if not (1000 <= r <= 500000):
                continue
            slot = state.redditi_per_anno.setdefault(
                anno, {"reddito": 0.0, "contributi": 0.0, "cassa": (cassa or "").title()},
            )
            if slot["reddito"] == 0:
                slot["reddito"] = r
                slot["contributi"] = c
                if cassa:
                    slot["cassa"] = cassa.title()
                if r > 0:
                    state.retribuzioni.append(r)
        except (ValueError, KeyError):
            continue


# ---------------------------------------------------------------------------
# 7. Consolidamento totali
# ---------------------------------------------------------------------------
def _consolida_totali(state: _EstrattoState) -> None:
    """Calcola settimane totali, anni stimati, media retribuzione, storico ordinato,
    reddito annuo lordo annualizzato, totale versato e montante stimato."""
    result = state.result
    state.settimane_tot += state.giorni_tot // 7
    result["settimane_contributive"] = state.settimane_tot
    result["giorni_contributivi"] = state.giorni_tot
    result["anni_stimati"] = state.settimane_tot // 52 if state.settimane_tot else 0
    if state.retribuzioni:
        result["retribuzione_media_annua"] = round(
            sum(state.retribuzioni) / len(state.retribuzioni), 2,
        )
    if state.primo_inizio:
        result["data_inizio_contribuzione"] = state.primo_inizio

    # Storico annuale (decrescente)
    storico = [
        {
            "anno": int(anno),
            "reddito": round(dati["reddito"], 2),
            "contributi": round(dati["contributi"], 2),
            "settimane": dati.get("settimane", 52),
            "cassa": dati["cassa"],
        }
        for anno, dati in sorted(state.redditi_per_anno.items(), reverse=True)
    ]
    result["storico_redditi"] = storico

    # Reddito ultimo anno annualizzato
    if storico:
        ultimo = storico[0]
        sett = ultimo.get("settimane") or 52
        annualizzato = 0 < sett < 52
        result["reddito_annuo_lordo"] = (
            round(ultimo["reddito"] * 52 / sett, 2) if annualizzato else ultimo["reddito"]
        )
        result["reddito_annuo_lordo_annualizzato"] = annualizzato
        result["ultimo_anno_riferimento"] = ultimo["anno"]

    result["totale_retribuzioni"] = round(sum(state.retribuzioni), 2)
    result["totale_versato"] = round(
        sum(p["contributi"] for p in result["periodi_contributivi"]), 2,
    )
    # Montante stimato: contributi versati se > 0 altrimenti 33% delle retribuzioni
    result["montante_stimato"] = (
        result["totale_versato"]
        if result["totale_versato"] > 0
        else round(result["totale_retribuzioni"] * 0.33, 2)
    )
