"""Regressione: _riconcilia_premi deve dare imposte = lordo − netto − ssn (= 25,43)
anche con letture non deterministiche dell'LLM (lordo mancante, righe duplicate)."""
import ocr_polizza as o

G = [
    {"descrizione": "RCA", "premio_netto": 182.25, "imposte": 22.78},
    {"descrizione": "Ricorso Terzi", "premio_netto": 5.00, "imposte": 0.68},
    {"descrizione": "Assistenza", "premio_netto": 18.18, "imposte": 2.27},
]


def run(d):
    o._riconcilia_premi(d)
    return round(d.get("imposte_totali") or 0, 2)


def test_itemizzato_con_lordo():
    assert run({"contributo_ssn": 19.14, "contributo_forzoso": 0.30,
                "premio_lordo_totale": 250.00, "garanzie": [dict(g) for g in G]}) == 25.43


def test_no_lordo_solo_garanzie():
    assert run({"contributo_ssn": 19.14, "contributo_forzoso": 0.30,
                "premio_lordo_totale": None, "garanzie": [dict(g) for g in G]}) == 25.43


def test_garanzie_duplicate_no_lordo():
    # l'LLM ripete le stesse righe → senza dedup darebbe 50,86
    dup = [dict(g) for g in G] + [dict(g) for g in G]
    assert run({"contributo_ssn": 19.14, "contributo_forzoso": 0.30,
                "premio_lordo_totale": None, "premio_netto_totale": 205.43, "garanzie": dup}) == 25.43


def test_imposte_doppie_toplevel_con_lordo():
    assert run({"premio_netto_totale": 205.43, "imposte_totali": 50.86,
                "contributo_ssn": 19.14, "premio_lordo_totale": 250.00, "garanzie": []}) == 25.43


def test_gia_coerente():
    assert run({"premio_netto_totale": 205.43, "imposte_totali": 25.43,
                "contributo_ssn": 19.14, "premio_lordo_totale": 250.00, "garanzie": []}) == 25.43


def test_imposte_zero():
    assert run({"premio_netto_totale": 205.43, "imposte_totali": 0,
                "contributo_ssn": 19.14, "premio_lordo_totale": 250.00, "garanzie": []}) == 25.43
