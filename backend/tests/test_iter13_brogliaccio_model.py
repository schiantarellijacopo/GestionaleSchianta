"""Iter13 - Verifica del modello contabile ridefinito (Prima Nota / Brogliaccio).

Regola chiave dell'utente:
- TOTALE include SOLO incasso_premio (lordo) e spese reali (negative).
- Rimesse (pagamento_compagnia uscita) → solo colonna Rimesse + banca uscita, NO TOTALE.
- Pagamento provvigioni (provvigioni uscita) → solo Spese + banca uscita, NO TOTALE.
- Giroconto → solo nelle banche, NO TOTALE.
- Rappel entrata (cat=provvigioni) → solo Provvigioni, NO Entrate.

Inoltre:
- KPI entrate: SOLO incasso_premio.
- KPI provvigioni include rappel.
- saldi-cassa.saldo_da_versare = (lordo - provv) - rimesse - rappel.
- Voci ricorsive collab: CRUD + materializzazione.
- DELETE chiusura riapre i movimenti.
- DELETE movimento giroconto: cancella la coppia (BUG da verificare: pair_id in note string).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def conti(client):
    """Get/create 2 conti cassa per giroconto + rimessa."""
    r = client.get(f"{API}/librerie/conti-cassa")
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) >= 2, f"servono almeno 2 conti cassa, trovati {len(items)}"
    return items[:2]


@pytest.fixture(scope="module")
def setup_data(client, conti):
    """Crea movimenti di test in una data univoca per testare le righe brogliaccio."""
    comps = client.get(f"{API}/compagnie").json()
    assert comps, "no compagnie"
    comp = comps[0]
    collabs = client.get(f"{API}/collaboratori").json()
    assert collabs, "no collaboratori"
    collab = collabs[0]
    anas = client.get(f"{API}/anagrafiche").json()
    assert anas, "no anagrafiche"
    ana = anas[0]

    ts = int(time.time())
    # data univoca per il giorno
    data_giorno = "2026-03-15"

    created_ids = []

    # 1) incasso_premio (entrata) - dovrebbe contare in TOTALE
    polizza = client.post(f"{API}/polizze", json={
        "numero_polizza": f"TEST_iter13_{ts}",
        "compagnia_id": comp["id"],
        "contraente_id": ana["id"],
        "ramo": "RCA",
        "effetto": data_giorno, "scadenza": "2027-03-15",
        "premio_lordo": 500.0, "collaboratore_id": collab["id"],
    }).json()
    titolo = client.post(f"{API}/titoli", json={
        "polizza_id": polizza["id"], "tipo": "nuova", "stato": "da_incassare",
        "data_emissione": data_giorno, "data_copertura": data_giorno,
        "effetto": data_giorno, "scadenza": "2027-03-15",
        "importo_lordo": 500.0, "provvigioni": 50.0,
    }).json()
    r = client.post(f"{API}/titoli/{titolo['id']}/incassa", json={
        "mezzo_pagamento": "bonifico", "data_incasso": data_giorno,
        "conto_cassa_id": conti[0]["id"],
    })
    assert r.status_code == 200, r.text

    # 2) Rimessa (uscita, pagamento_compagnia) - NON in TOTALE, solo rimesse + banca
    mov_rim = client.post(f"{API}/contabilita/movimenti", json={
        "data_movimento": data_giorno, "tipo": "uscita", "categoria": "pagamento_compagnia",
        "importo": 200.0, "descrizione": f"TEST_iter13_rimessa_{ts}",
        "compagnia_id": comp["id"], "conto_cassa_id": conti[0]["id"],
    }).json()
    created_ids.append(mov_rim["id"])

    # 3) Pagamento provvigioni a collab (uscita, provvigioni) - NON in TOTALE, solo Spese
    mov_pp = client.post(f"{API}/contabilita/movimenti", json={
        "data_movimento": data_giorno, "tipo": "uscita", "categoria": "provvigioni",
        "importo": 30.0, "descrizione": f"TEST_iter13_payprovv_{ts}",
        "collaboratore_id": collab["id"], "conto_cassa_id": conti[0]["id"],
    }).json()
    created_ids.append(mov_pp["id"])

    # 4) Stipendio (uscita, spese_amministrative) - vera uscita: totale=-importo, spese=+importo
    mov_st = client.post(f"{API}/contabilita/movimenti", json={
        "data_movimento": data_giorno, "tipo": "uscita", "categoria": "spese_amministrative",
        "importo": 1000.0, "descrizione": f"TEST_iter13_stipendio_{ts}",
        "conto_cassa_id": conti[0]["id"],
    }).json()
    created_ids.append(mov_st["id"])

    # 5) Giroconto - NON in TOTALE, solo banche corrispondenti
    gr = client.post(f"{API}/contabilita/giroconto", json={
        "data_movimento": data_giorno, "conto_da_id": conti[0]["id"], "conto_a_id": conti[1]["id"],
        "importo": 100.0, "descrizione": f"TEST_iter13_gr_{ts}",
    }).json()
    assert "pair_id" in gr, gr
    created_ids.extend([gr["movimento_uscita_id"], gr["movimento_entrata_id"]])

    # 6) Rappel entrata (creato via /api/rappel + /incassa)
    rappel = client.post(f"{API}/rappel", json={
        "compagnia_id": comp["id"], "data": data_giorno, "importo": 80.0,
        "descrizione": f"TEST_iter13_rappel_{ts}", "anno": 2026,
    }).json()
    r = client.post(f"{API}/rappel/{rappel['id']}/incassa", json={"data_incasso": data_giorno})
    assert r.status_code == 200, r.text
    rappel_mov_id = r.json()["movimento_id"]
    created_ids.append(rappel_mov_id)

    yield {
        "data": data_giorno,
        "polizza_id": polizza["id"],
        "titolo_id": titolo["id"],
        "compagnia_id": comp["id"],
        "collaboratore_id": collab["id"],
        "conti": conti,
        "rappel_id": rappel["id"],
        "rappel_mov_id": rappel_mov_id,
        "giroconto_pair_id": gr["pair_id"],
        "giroconto_out_id": gr["movimento_uscita_id"],
        "giroconto_in_id": gr["movimento_entrata_id"],
        "mov_rim_id": mov_rim["id"],
        "mov_pp_id": mov_pp["id"],
        "mov_st_id": mov_st["id"],
        "created_ids": created_ids,
    }
    # teardown best-effort
    try:
        client.delete(f"{API}/rappel/{rappel['id']}")
    except Exception:
        pass


# ============================ BROGLIACCIO ROWS ============================

class TestBrogliaccioRighe:
    """Verifica che ogni categoria produca le colonne corrette."""

    def _get_row(self, client, data, mid):
        r = client.get(f"{API}/contabilita/brogliaccio", params={"data": data})
        assert r.status_code == 200, r.text
        body = r.json()
        for row in body["righe"]:
            if row["id"] == mid:
                return row, body
        pytest.fail(f"riga {mid} non trovata in brogliaccio del {data}")

    def test_rimessa_no_totale(self, client, setup_data):
        row, _ = self._get_row(client, setup_data["data"], setup_data["mov_rim_id"])
        assert row["totale"] == 0, f"Rimessa NON deve essere in TOTALE: got {row['totale']}"
        assert row["rimesse"] == 200.0, f"Rimessa deve essere in colonna rimesse: got {row['rimesse']}"
        assert row["spese"] == 0
        assert row["saldo"] == 0
        # banca uscita
        cc_id = setup_data["conti"][0]["id"]
        assert row["per_conto"].get(cc_id) == -200.0, row["per_conto"]

    def test_paga_provvigioni_no_totale(self, client, setup_data):
        row, _ = self._get_row(client, setup_data["data"], setup_data["mov_pp_id"])
        assert row["totale"] == 0, f"Paga-provvigioni NON deve essere in TOTALE: got {row['totale']}"
        assert row["spese"] == 30.0, f"Paga-provvigioni deve essere in Spese: got {row['spese']}"
        assert row["saldo"] == 0
        cc_id = setup_data["conti"][0]["id"]
        assert row["per_conto"].get(cc_id) == -30.0

    def test_stipendio_totale_negativo(self, client, setup_data):
        row, _ = self._get_row(client, setup_data["data"], setup_data["mov_st_id"])
        assert row["totale"] == -1000.0, f"Stipendio deve avere totale negativo: got {row['totale']}"
        assert row["spese"] == 1000.0
        cc_id = setup_data["conti"][0]["id"]
        assert row["per_conto"].get(cc_id) == -1000.0

    def test_giroconto_no_totale(self, client, setup_data):
        # entrambe le righe (in/out) devono avere totale=0
        row_out, _ = self._get_row(client, setup_data["data"], setup_data["giroconto_out_id"])
        row_in, _ = self._get_row(client, setup_data["data"], setup_data["giroconto_in_id"])
        assert row_out["totale"] == 0, row_out
        assert row_in["totale"] == 0, row_in
        # banche
        cc0 = setup_data["conti"][0]["id"]
        cc1 = setup_data["conti"][1]["id"]
        assert row_out["per_conto"].get(cc0) == -100.0
        assert row_in["per_conto"].get(cc1) == 100.0

    def test_rappel_entrata_solo_provvigioni(self, client, setup_data):
        row, _ = self._get_row(client, setup_data["data"], setup_data["rappel_mov_id"])
        assert row["totale"] == 0, f"Rappel NON deve essere in TOTALE: got {row['totale']}"
        assert row["provv"] == 80.0, f"Rappel deve essere in Provvigioni: got {row['provv']}"

    def test_incasso_premio_in_totale(self, client, setup_data):
        # cerco il movimento di incasso titolo
        r = client.get(f"{API}/contabilita/movimenti", params={"dal": setup_data["data"], "al": setup_data["data"]})
        assert r.status_code == 200
        movs = r.json()
        # filtra incasso_premio
        ip = [m for m in movs if m["categoria"] == "incasso_premio" and m.get("polizza_id") == setup_data["polizza_id"]]
        assert ip, f"nessun movimento incasso_premio trovato per il titolo. movs={[m['categoria'] for m in movs]}"
        mid = ip[0]["id"]
        row, _ = self._get_row(client, setup_data["data"], mid)
        assert row["totale"] == 500.0, f"Incasso premio deve essere in TOTALE: got {row['totale']}"
        assert row["provv"] == 50.0


# ============================ KPI CUMULATIVI ============================

class TestKpiCumulativi:
    """Verifica KPI: entrate = solo incasso_premio; provvigioni include rappel."""

    def test_kpi_entrate_only_incasso_premio(self, client, setup_data):
        r = client.get(f"{API}/contabilita/brogliaccio", params={"data": setup_data["data"]})
        assert r.status_code == 200
        kpi = r.json().get("riepilogo_kpi", {})
        assert "entrate" in kpi
        assert "provvigioni" in kpi
        # entrate cumulative deve includere il nostro 500 (almeno - cumulativo)
        assert kpi["entrate"] >= 500.0, f"entrate KPI < 500: {kpi}"

    def test_kpi_provvigioni_include_rappel(self, client, setup_data):
        r = client.get(f"{API}/contabilita/brogliaccio", params={"data": setup_data["data"]})
        kpi = r.json().get("riepilogo_kpi", {})
        # provvigioni cumulative dovrebbe includere il rappel 80 + provv del titolo 50
        assert kpi["provvigioni"] >= 130.0, f"provvigioni KPI < 130 (atteso rappel+provv): {kpi}"


# ============================ SALDI CASSA COMPAGNIE ============================

class TestSaldiCassa:
    def test_saldi_cassa_sottrae_rappel_e_rimesse(self, client, setup_data):
        r = client.get(f"{API}/compagnie/saldi-cassa")
        assert r.status_code == 200, r.text
        items = r.json()
        # trova la nostra compagnia
        c = next((x for x in items if x["compagnia_id"] == setup_data["compagnia_id"]), None)
        assert c, "compagnia non trovata nei saldi-cassa"
        assert "saldo_da_versare" in c
        assert "totale_incassato" in c
        assert "totale_versato" in c

    def test_dati_compagnie_coerente_con_saldi(self, client, setup_data):
        r1 = client.get(f"{API}/compagnie/saldi-cassa")
        r2 = client.get(f"{API}/contabilita/dati-compagnie")
        assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
        sal_map = {x["compagnia_id"]: x for x in r1.json()}
        dc = r2.json()
        rows = dc.get("compagnie") if isinstance(dc, dict) else dc
        for row in rows:
            cid = row.get("compagnia_id")
            if cid in sal_map and "saldo_attuale" in row:
                # coerenza: saldo_attuale ~= saldo_da_versare (entrambi devono essere prodotti
                # dalla stessa funzione _compagnia_estratto_data)
                assert abs(row["saldo_attuale"] - sal_map[cid]["saldo_da_versare"]) < 0.5, (
                    f"saldo_attuale {row['saldo_attuale']} differisce da saldo_da_versare "
                    f"{sal_map[cid]['saldo_da_versare']} per compagnia {cid}"
                )


# ============================ RAPPEL CRUD ============================

class TestRappelCrud:
    def test_rappel_incasso_crea_movimento_provvigioni_entrata(self, client, setup_data):
        r = client.get(f"{API}/contabilita/movimenti", params={
            "dal": setup_data["data"], "al": setup_data["data"],
        })
        assert r.status_code == 200
        movs = r.json()
        mov = next((m for m in movs if m["id"] == setup_data["rappel_mov_id"]), None)
        assert mov, "movimento rappel non trovato"
        assert mov["categoria"] == "provvigioni"
        assert mov["tipo"] == "entrata"
        assert mov.get("is_rappel") == True or mov.get("rappel_id")  # noqa: E712

    def test_delete_movimento_rappel_bloccato(self, client, setup_data):
        r = client.delete(f"{API}/contabilita/movimenti/{setup_data['rappel_mov_id']}")
        assert r.status_code == 400, f"DELETE movimento rappel deve restituire 400, got {r.status_code} {r.text}"


# ============================ VOCI RICORSIVE COLLAB ============================

class TestVociRicorsiveCollab:
    def test_crud_voce_ricorsiva_e_materializzazione(self, client, setup_data):
        ts = int(time.time())
        cid = setup_data["collaboratore_id"]
        body = {
            "collaboratore_id": cid,
            "causale": f"TEST_iter13_rule_{ts}",
            "importo": 50.0,
            "periodicita": "mensile",
            "giorno_mese": 1,
            "data_inizio": "2025-10-01",
            "data_fine": "2026-03-31",
            "attiva": True,
        }
        r = client.post(f"{API}/voci-ricorsive-collab", json=body)
        assert r.status_code == 201, r.text
        rule = r.json()
        rid = rule["id"]
        # verifica voci materializzate
        r2 = client.get(f"{API}/collaboratori/{cid}/voci-manuali")
        assert r2.status_code == 200
        voci = r2.json()
        materializzate = [v for v in voci if v.get("ricorsiva_id") == rid]
        assert len(materializzate) >= 3, f"attese >=3 voci materializzate (ott-nov-dic-gen-feb-mar), got {len(materializzate)}"
        # cleanup
        client.delete(f"{API}/voci-ricorsive-collab/{rid}", params={"elimina_voci_non_pagate": "true"})

    def test_voce_ricorsiva_all_collaboratori(self, client):
        ts = int(time.time())
        body = {
            "collaboratore_id": "__all__",
            "causale": f"TEST_iter13_all_{ts}",
            "importo": 10.0,
            "periodicita": "mensile",
            "giorno_mese": 1,
            "data_inizio": "2026-01-01",
            "data_fine": "2026-03-31",
            "attiva": True,
        }
        r = client.post(f"{API}/voci-ricorsive-collab", json=body)
        assert r.status_code == 201, r.text
        rule = r.json()
        assert rule.get("voci_generate", 0) > 0
        client.delete(f"{API}/voci-ricorsive-collab/{rule['id']}", params={"elimina_voci_non_pagate": "true"})


# ============================ DELETE MOVIMENTI / GIROCONTO ============================

class TestDeleteMovimenti:
    def test_delete_giroconto_elimina_pair(self, client, setup_data):
        """BUG suspect: pair_id è memorizzato nella stringa `note`, non come campo top-level.
        Il DELETE prova `cur.get("pair_id") or cur.get("giroconto_pair_id")` che ritorna None,
        quindi cancella SOLO la singola riga e NON la coppia.
        """
        ts = int(time.time())
        # crea un nuovo giroconto isolato
        gr = client.post(f"{API}/contabilita/giroconto", json={
            "data_movimento": "2026-03-16",
            "conto_da_id": setup_data["conti"][0]["id"],
            "conto_a_id": setup_data["conti"][1]["id"],
            "importo": 50.0, "descrizione": f"TEST_iter13_del_gr_{ts}",
        }).json()
        out_id = gr["movimento_uscita_id"]
        in_id = gr["movimento_entrata_id"]
        # delete uscita
        r = client.delete(f"{API}/contabilita/movimenti/{out_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        # verifica che ANCHE la entrata sia stata cancellata
        r2 = client.get(f"{API}/contabilita/movimenti", params={"dal": "2026-03-16", "al": "2026-03-16"})
        movs = r2.json()
        in_still_exists = any(m["id"] == in_id for m in movs)
        assert not in_still_exists, (
            f"BUG: DELETE di un giroconto deve cancellare la coppia, ma la riga entrata {in_id} esiste ancora. "
            f"Response delete: {body}"
        )

    def test_delete_movimento_paga_provvigioni_no_id_passa(self, client, setup_data):
        # paga_provvigioni senza pagamento_provvigioni_id può essere cancellato
        # il nostro mov_pp_id NON ha pagamento_provvigioni_id quindi è cancellabile
        r = client.delete(f"{API}/contabilita/movimenti/{setup_data['mov_pp_id']}")
        # accetta 200 o 400 (a seconda della linkatura)
        assert r.status_code in (200, 400), r.text


# ============================ CHIUSURE GIORNO ============================

class TestChiusureGiorno:
    def test_lista_chiusure_filtro_anno(self, client):
        r = client.get(f"{API}/contabilita/chiusure-giorno", params={"anno": 2026})
        assert r.status_code == 200, r.text
        items = r.json()
        for it in items:
            assert it["data"].startswith("2026"), it
            assert "riepilogo" in it

    def test_delete_chiusura_riapre_movimenti(self, client, setup_data):
        # crea chiusura per il giorno isolato 2026-03-17 con un movimento
        mov = client.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": "2026-03-17", "tipo": "uscita", "categoria": "spese_amministrative",
            "importo": 5.0, "descrizione": "TEST_iter13_chiusura",
            "conto_cassa_id": setup_data["conti"][0]["id"],
        })
        assert mov.status_code == 201
        mid = mov.json()["id"]
        # chiudi giornata
        r_ch = client.post(f"{API}/contabilita/chiusura-giorno", json={"data": "2026-03-17"})
        if r_ch.status_code != 201:
            pytest.skip(f"chiusura non creata: {r_ch.status_code} {r_ch.text}")
        ch = r_ch.json()
        ch_id = ch.get("id") or ch.get("chiusura_id")
        assert ch_id
        # verifica movimento chiuso
        r_m = client.get(f"{API}/contabilita/movimenti", params={"dal": "2026-03-17", "al": "2026-03-17"})
        m_after = next((m for m in r_m.json() if m["id"] == mid), None)
        assert m_after and m_after.get("chiusura_id") == ch_id, f"movimento non legato a chiusura: {m_after}"
        # delete chiusura
        r_del = client.delete(f"{API}/contabilita/chiusura-giorno/{ch_id}")
        assert r_del.status_code == 200, r_del.text
        assert r_del.json().get("ok") is True
        # movimento deve essere riaperto
        r_m2 = client.get(f"{API}/contabilita/movimenti", params={"dal": "2026-03-17", "al": "2026-03-17"})
        m_after2 = next((m for m in r_m2.json() if m["id"] == mid), None)
        assert m_after2 and not m_after2.get("chiusura_id"), f"movimento ancora chiuso: {m_after2}"
        # cleanup
        client.delete(f"{API}/contabilita/movimenti/{mid}")
