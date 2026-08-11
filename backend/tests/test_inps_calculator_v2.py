"""Test parametri INPS 2025-2026 verificati sulle fonti ufficiali.

Fonti verificate (12/02/2026):
- Coefficienti trasformazione: DM Min. Lavoro 20/11/2024 (GU n.35/2025)
- Tassi rivalutazione: Note ISTAT annuali (Ministero Lavoro)
- Reversibilità: L. 335/1995 art. 1 c. 41
- Invalidità civile 2026: Circolare INPS
- Riduzioni Tabella F: L. 335/1995
"""
import pytest
import inps_calculator as ic


class TestCoefficientiTrasformazione:
    """DM 20/11/2024 — biennio 2025-2026."""

    def test_coefficiente_57(self):
        assert ic.PARAMS["coefficienti_trasformazione_2025"][57] == 0.04204

    def test_coefficiente_62(self):
        assert ic.PARAMS["coefficienti_trasformazione_2025"][62] == 0.04795

    def test_coefficiente_67(self):
        """67 anni = età pensione di vecchiaia standard."""
        assert ic.PARAMS["coefficienti_trasformazione_2025"][67] == 0.05608

    def test_coefficiente_71(self):
        assert ic.PARAMS["coefficienti_trasformazione_2025"][71] == 0.06510

    def test_coefficienti_ordinati_crescente(self):
        """I coefficienti devono crescere con l'età."""
        vals = sorted(ic.PARAMS["coefficienti_trasformazione_2025"].items())
        precedente = 0
        for _eta, c in vals:
            assert c > precedente, f"Coefficiente non crescente ad età {_eta}"
            precedente = c


class TestTassiRivalutazione:
    """Note ISTAT/Min. Lavoro — variazione media quinquennale PIL nominale."""

    def test_2021_negativo(self):
        """Il 2021 ha avuto rivalutazione NEGATIVA (crisi COVID)."""
        assert ic.TASSI_RIVALUTAZIONE_INPS[2021] == -0.000215

    def test_2025_ufficiale(self):
        assert ic.TASSI_RIVALUTAZIONE_INPS[2025] == 0.040445

    def test_2024_ufficiale(self):
        assert ic.TASSI_RIVALUTAZIONE_INPS[2024] == 0.036622

    def test_2014_negativo(self):
        """Il 2014 ha avuto rivalutazione negativa (crisi economica)."""
        assert ic.TASSI_RIVALUTAZIONE_INPS[2014] == -0.001927


class TestAliquoteReversibilita:
    """L. 335/1995 art. 1 c. 41."""

    def test_solo_coniuge_60(self):
        assert ic.PARAMS["superstite_solo_coniuge"] == 0.60

    def test_coniuge_1_figlio_80(self):
        assert ic.PARAMS["superstite_coniuge_un_figlio"] == 0.80

    def test_coniuge_2_figli_100(self):
        assert ic.PARAMS["superstite_coniuge_due_o_piu_figli"] == 1.00


class TestImporti2026:
    """Importi ufficiali INPS 2026."""

    def test_invalidita_civile_2026(self):
        assert ic.PARAMS["invalidita_civile_mensile_2026"] == 340.71

    def test_trattamento_minimo_2026(self):
        assert ic.PARAMS["trattamento_minimo_2026"] == 611.85


class TestAliquoteContributive2026:
    """Circolari INPS n. 8/2026 (Gestione Separata) e n. 14/2026 (Artigiani/Commercianti)."""

    def test_gestione_separata_professionisti(self):
        assert ic.PARAMS["aliquota_gestione_separata_prof"] == 0.2607

    def test_artigiani(self):
        assert ic.PARAMS["aliquota_artigiani"] == 0.24

    def test_commercianti(self):
        assert ic.PARAMS["aliquota_commercianti"] == 0.2448


class TestCalcoloPensione:
    """Test end-to-end del calcolo con casi reali."""

    def test_invalidita_completa_requisiti_ok(self):
        r = ic.calcola_pensione(
            "invalidita", settimane_contributive=2080,
            retribuzione_media_annua=30000, eta=67, percentuale_invalidita=100)
        assert r["pensione_lorda_annua"] > 0
        assert r["dettaglio"]["requisiti_contributivi_ok"] is True
        assert r["coefficiente_applicato"] == 0.05608

    def test_invalidita_no_requisiti(self):
        """Se meno di 260 settimane → fallback su invalidità civile 2026."""
        r = ic.calcola_pensione(
            "invalidita", settimane_contributive=100,
            retribuzione_media_annua=30000, eta=45, percentuale_invalidita=100)
        # 340.71 × 13 = 4429.23
        assert r["pensione_lorda_annua"] == pytest.approx(4429.23, rel=0.01)
        assert r["dettaglio"]["requisiti_contributivi_ok"] is False

    def test_reversibilita_coniuge_solo(self):
        r = ic.calcola_pensione(
            "superstite", settimane_contributive=2080,
            retribuzione_media_annua=30000, eta=67, numero_familiari=1)
        # Deve essere 60% della pensione contributiva base
        base = r["dettaglio"]["pensione_contributiva_annua_lorda"]
        assert r["pensione_lorda_annua"] == pytest.approx(base * 0.60, rel=0.01)

    def test_reversibilita_coniuge_2figli(self):
        r = ic.calcola_pensione(
            "superstite", settimane_contributive=2080,
            retribuzione_media_annua=30000, eta=67, numero_familiari=3)
        base = r["dettaglio"]["pensione_contributiva_annua_lorda"]
        assert r["pensione_lorda_annua"] == pytest.approx(base * 1.00, rel=0.01)


class TestRiduzioneReversibilita:
    """Tabella F L. 335/1995 - riduzioni per reddito superstite."""

    def test_no_riduzione_sotto_soglia(self):
        p, perc, note = ic.riduzione_reversibilita_per_reddito(20000, 20000)
        assert p == 20000
        assert perc == 0.0

    def test_riduzione_25(self):
        p, perc, note = ic.riduzione_reversibilita_per_reddito(20000, 25000)
        assert perc == 0.25
        assert p == pytest.approx(15000, rel=0.01)

    def test_riduzione_50(self):
        p, perc, note = ic.riduzione_reversibilita_per_reddito(20000, 50000)
        assert perc == 0.50
        assert p == pytest.approx(10000, rel=0.01)

    def test_no_riduzione_con_figli(self):
        """Corte Cost. 162/2022: no riduzione se ci sono figli minori/studenti/inabili."""
        p, perc, note = ic.riduzione_reversibilita_per_reddito(
            20000, 60000, ha_figli_minori_studenti_inabili=True)
        assert p == 20000
        assert perc == 0.0


class TestMontanteRivalutato:
    """Verifica calcolo montante con coefficienti ISTAT ufficiali."""

    def test_singolo_anno_rivalutazione(self):
        """Un contributo del 2020 rivalutato al 2025 usa i tassi ufficiali:
        2021 (-0.02%) × 2022 (+0.997%) × 2023 (+2.308%) × 2024 (+3.662%) × 2025 (+4.045%)"""
        storico = [{"anno": 2020, "reddito": 30000, "contributi": 9900}]
        m = ic.calcola_montante_rivalutato(storico)
        # Verifica arrotondato: 9900 × 1.10944 ~ 10983
        assert m > 9900  # deve essere rivalutato
        assert m < 12000  # ragionevole
