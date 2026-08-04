"""Iter40 tests — Mini bilancio, voci di bilancio, cleanup anticipi orfani, movimenti.

Testing scope (from review_request):
 - Brogliaccio classification rules (rappel column, versamento -saldo, ritenuta no spese)
 - Cleanup anticipo orfano on titolo incassa (bulk-copertura + incassa sequence)
 - Movimento manuale con risoluzione conto da mezzo_pagamento (CONTANTI, BONIFICO INTESA)
 - Mini bilancio periodico + drill-down + export
 - Voci di bilancio CRUD + validazione nome vuoto
 - Movimento con voce_bilancio_id impatta mini-bilancio

Data safety: creates dedicated anagrafica/polizza/titolo TEST_* and cleans up.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, date

import pytest
import requests

try:
    from dotenv import load_dotenv
    if not os.environ.get("REACT_APP_BACKEND_URL"):
        load_dotenv("/app/frontend/.env", override=False)
except Exception:
    pass

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PASS = "Admin123!"

TODAY = date.today().isoformat()  # e.g. 2026-08-04
YEAR_START = f"{date.today().year}-01-01"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code != 200:
        return None
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def admin_token():
    tok = _login(ADMIN_EMAIL, ADMIN_PASS)
    if not tok:
        pytest.skip("Login admin fallito")
    return tok


@pytest.fixture(scope="module")
def s(admin_token):
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return sess


# ============ 1. BROGLIACCIO ============
class TestBrogliaccio:
    def test_brogliaccio_status_and_shape(self, s):
        r = s.get(f"{API}/contabilita/brogliaccio", params={"data": TODAY})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "righe" in data
        assert "conti_cassa" in data
        assert "totali_giornata" in data or "riepilogo_kpi" in data

    def test_rappel_column_and_versamento_rimesse_saldo_and_ritenuta_no_spese(self, s):
        """Verifica regole di classificazione per data 2026-08-04.

        Tollerante: se la data indicata dal PS (2026-08-04) non contiene tali righe,
        cerca le stesse regole su TUTTE le righe restituite.
        """
        # Prova data specifica dal problem statement
        target = "2026-08-04"
        r = s.get(f"{API}/contabilita/brogliaccio", params={"data": target})
        assert r.status_code == 200
        data = r.json()
        righe = data.get("righe", [])

        found_versamento = False
        found_rappel = False
        found_ritenuta = False
        errors = []
        for row in righe:
            desc = (row.get("descrizione") or "").lower()
            cat = (row.get("categoria") or "").lower()
            # Versamento compagnia (categoria pagamento_compagnia)
            if cat == "pagamento_compagnia" or "versamento" in desc:
                found_versamento = True
                saldo = row.get("saldo") or row.get("c_saldo") or 0
                rimesse = row.get("rimesse") or 0
                # regola: saldo negativo, rimesse positivo
                if saldo >= 0:
                    errors.append(f"Versamento saldo non negativo: {saldo} - riga {desc}")
                if rimesse <= 0:
                    errors.append(f"Versamento rimesse non positivo: {rimesse} - riga {desc}")
            if "rappel" in desc or cat == "provvigioni" and (row.get("tipo") == "entrata"):
                # regola: rappel colonna popolata, provvigioni = 0
                prov = row.get("provvigioni") or 0
                rappel_val = row.get("rappel") or 0
                if "rappel" in desc:
                    found_rappel = True
                    if prov and abs(prov) > 0.001:
                        errors.append(f"Rappel ha provv != 0: {prov}")
                    if not rappel_val:
                        errors.append(f"Rappel colonna vuota per riga {desc}")
            if cat == "ritenuta_compagnia" or "ritenuta" in desc:
                found_ritenuta = True
                spese = row.get("spese") or 0
                if spese and abs(spese) > 0.001:
                    errors.append(f"Ritenuta con spese != 0: {spese} - riga {desc}")

        # Anticipi orfani: nessuna riga 'Copertura anticipata' per titoli incassati
        # (verifichiamo che se c'è una riga anticipo, il titolo non risulta incassato)
        # -> qui basta accertare che non esplodano; test dedicato più sotto.
        print(f"[brogliaccio {target}] versamento={found_versamento} rappel={found_rappel} ritenuta={found_ritenuta}")
        if errors:
            pytest.fail("; ".join(errors))


# ============ 2. INCASSO CON CLEANUP ANTICIPO ============
def _find_or_create_test_polizza(s):
    """Cerca polizza esistente TEST_ oppure crea nuova anagrafica+polizza."""
    # cerca compagnia esistente
    r = s.get(f"{API}/compagnie")
    assert r.status_code == 200
    comps = r.json()
    if not comps:
        pytest.skip("Nessuna compagnia in db")
    comp_id = comps[0]["id"]

    # cerca anagrafica esistente per non creare/toccare dati
    r = s.get(f"{API}/anagrafiche", params={"limit": 5})
    if r.status_code == 200 and r.json():
        # struttura potrebbe essere lista o dict
        js = r.json()
        items = js if isinstance(js, list) else js.get("items", [])
        if items:
            anag_id = items[0]["id"]
        else:
            anag_id = None
    else:
        anag_id = None

    # Crea anagrafica dedicata
    uniq = uuid.uuid4().hex[:8]
    r = s.post(f"{API}/anagrafiche", json={
        "tipo_soggetto": "persona_fisica",
        "cognome": f"TEST_ITER40_{uniq}",
        "nome": "TEST",
        "email": f"test_iter40_{uniq}@test.local",
        "codice_fiscale": f"TSTTST80A01H501{uniq[:1].upper()}",
    })
    if r.status_code not in (200, 201):
        # fallback: usa una esistente
        if not anag_id:
            pytest.skip(f"Impossibile creare anagrafica: {r.status_code} {r.text}")
    else:
        anag_id = r.json()["id"]

    # Crea polizza test
    r = s.post(f"{API}/polizze", json={
        "numero_polizza": f"TEST_ITER40_{uniq}",
        "compagnia_id": comp_id,
        "contraente_id": anag_id,
        "ramo": "RCA",
        "prodotto": "TEST",
        "effetto": TODAY,
        "scadenza": TODAY,
        "premio_lordo": 100.0,
    })
    if r.status_code not in (200, 201):
        pytest.skip(f"POST /polizze fallito ({r.status_code}): {r.text[:300]}")
    pol = r.json()
    return anag_id, pol["id"], comp_id


class TestIncassoCleanupAnticipo:
    def test_bulk_copertura_then_incassa_deletes_anticipo(self, s):
        anag_id, pol_id, comp_id = _find_or_create_test_polizza(s)
        # Crea titolo
        r = s.post(f"{API}/titoli", json={
            "polizza_id": pol_id,
            "tipo": "nuova",
            "effetto": TODAY,
            "scadenza": TODAY,
            "importo_lordo": 100.0,
            "provvigioni": 10.0,
            "stato": "da_incassare",
        })
        assert r.status_code in (200, 201), f"POST /titoli: {r.status_code} {r.text[:300]}"
        tid = r.json()["id"]

        movimenti_ids_da_pulire = []
        try:
            # 1) bulk-copertura -> crea anticipo
            r = s.post(f"{API}/titoli/bulk-copertura", json={"ids": [tid]})
            assert r.status_code in (200, 201), f"bulk-copertura: {r.status_code} {r.text}"

            # verifica anticipo creato
            r = s.get(f"{API}/contabilita/movimenti", params={"dal": TODAY, "al": TODAY})
            assert r.status_code == 200
            movs = r.json()
            items = movs if isinstance(movs, list) else movs.get("items", [])
            anticipo_pre = [m for m in items if m.get("titolo_id") == tid and m.get("categoria") == "anticipo"]
            assert len(anticipo_pre) >= 1, f"Anticipo non creato dopo bulk-copertura per {tid}"
            for m in anticipo_pre:
                movimenti_ids_da_pulire.append(m["id"])

            # 2) incassa
            r = s.post(f"{API}/titoli/{tid}/incassa", json={
                "data_incasso": TODAY,
                "mezzo_pagamento": "CONTANTI",
            })
            assert r.status_code in (200, 201), f"incassa: {r.status_code} {r.text}"

            # 3) verifica: nessun movimento anticipo per questo titolo
            r = s.get(f"{API}/contabilita/movimenti", params={"dal": TODAY, "al": TODAY})
            items2 = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            anticipo_post = [m for m in items2 if m.get("titolo_id") == tid and m.get("categoria") == "anticipo"]
            assert len(anticipo_post) == 0, f"Anticipo NON pulito dopo incasso: {anticipo_post}"

            # 4) brogliaccio: nessuna riga 'Copertura anticipata' per il titolo
            r = s.get(f"{API}/contabilita/brogliaccio", params={"data": TODAY})
            righe = r.json().get("righe", [])
            copertura_orfane = [row for row in righe
                                if row.get("titolo_id") == tid and (row.get("categoria") == "anticipo")]
            assert len(copertura_orfane) == 0, f"Righe copertura orfane nel brogliaccio: {copertura_orfane}"
        finally:
            # cleanup: elimina movimenti creati + titolo + polizza
            r = s.get(f"{API}/contabilita/movimenti", params={"dal": TODAY, "al": TODAY})
            try:
                items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
                for m in items:
                    if m.get("titolo_id") == tid:
                        s.delete(f"{API}/contabilita/movimenti/{m['id']}")
            except Exception:
                pass
            s.delete(f"{API}/titoli/{tid}")
            s.delete(f"{API}/polizze/{pol_id}")
            # anagrafica: lascia (potrebbe essere referenziata)
            s.delete(f"{API}/anagrafiche/{anag_id}")


# ============ 3. MOVIMENTO CON RISOLUZIONE CONTO DA MEZZO ============
class TestMovimentoRisoluzioneConto:
    def test_create_contanti_no_conto_id_resolves(self, s):
        r = s.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": TODAY,
            "tipo": "uscita",
            "categoria": "spese_amministrative",
            "importo": 5.55,
            "descrizione": "TEST_ITER40_CONTANTI",
            "mezzo_pagamento": "CONTANTI",
        })
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        mov = r.json()
        mid = mov["id"]
        try:
            assert mov.get("conto_cassa_id"), "conto_cassa_id non risolto da CONTANTI"
            # verifica conto: deve essere Cassa Contanti
            cid = mov["conto_cassa_id"]
            r2 = s.get(f"{API}/librerie/conti-cassa")
            names = {c["id"]: (c.get("nome") or "").upper() for c in r2.json()}
            assert "CONTANTI" in names.get(cid, ""), f"Conto risolto NON contanti: {names.get(cid)}"

            # PUT: cambia mezzo_pagamento a BONIFICO INTESA senza conto_id
            r3 = s.put(f"{API}/contabilita/movimenti/{mid}", json={
                "mezzo_pagamento": "BONIFICO INTESA",
                "conto_cassa_id": None,
            })
            assert r3.status_code == 200, f"PUT: {r3.status_code} {r3.text}"
            mov2 = r3.json()
            cid2 = mov2.get("conto_cassa_id")
            assert cid2, "conto_cassa_id non riallineato dopo PUT"
            # dovrebbe risolvere a Intesa
            resolved_name = names.get(cid2, "")
            if not resolved_name:
                # ricarica lista
                r2b = s.get(f"{API}/librerie/conti-cassa")
                names.update({c["id"]: (c.get("nome") or "").upper() for c in r2b.json()})
                resolved_name = names.get(cid2, "")
            assert "INTESA" in resolved_name, f"Conto post-PUT non Intesa: {resolved_name}"
        finally:
            s.delete(f"{API}/contabilita/movimenti/{mid}")


# ============ 4. MINI BILANCIO ============
class TestMiniBilancio:
    def test_mini_bilancio_shape_and_totali(self, s):
        r = s.get(f"{API}/cervello/mini-bilancio", params={"dal": YEAR_START, "al": TODAY})
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("ricavi", "costi", "totale_ricavi", "totale_costi", "risultato",
                  "saldi_conti", "debiti_compagnie", "ritenute_erario"):
            assert k in data, f"campo mancante: {k}"

        # risultato = ricavi - costi (arrotondamento tollerato)
        diff = round(data["totale_ricavi"] - data["totale_costi"], 2)
        assert abs(diff - data["risultato"]) < 0.02, f"risultato incoerente: {diff} vs {data['risultato']}"

        # ritenute compagnia NON come costo
        keys_costi = {r["key"] for r in data["costi"]}
        assert "ritenuta_compagnia" not in keys_costi

        # saldi_conti presenti
        assert isinstance(data["saldi_conti"], list)
        for sc in data["saldi_conti"]:
            assert isinstance(sc.get("saldo"), (int, float))

    def test_mini_bilancio_dettaglio_provvigioni_attive(self, s):
        # totale in mini-bilancio
        r = s.get(f"{API}/cervello/mini-bilancio", params={"dal": YEAR_START, "al": TODAY})
        totale_voce = next((r["totale"] for r in r.json()["ricavi"] if r["key"] == "provvigioni_attive"), 0.0)

        r = s.get(f"{API}/cervello/mini-bilancio/dettaglio",
                  params={"key": "provvigioni_attive", "dal": YEAR_START, "al": TODAY})
        assert r.status_code == 200
        det = r.json()
        assert det["key"] == "provvigioni_attive"
        assert "rows" in det and "totale" in det
        # somma rows == totale
        somma = round(sum(row["importo"] for row in det["rows"]), 2)
        assert abs(somma - det["totale"]) < 0.02
        # coerente col mini-bilancio (tollerato ±0.05)
        assert abs(det["totale"] - round(totale_voce, 2)) < 0.05, \
            f"dettaglio {det['totale']} != mini-bilancio {totale_voce}"

    def test_mini_bilancio_export_pdf(self, s):
        r = s.get(f"{API}/cervello/mini-bilancio/export",
                  params={"dal": YEAR_START, "al": TODAY, "formato": "pdf"})
        assert r.status_code == 200
        assert "pdf" in r.headers.get("content-type", "").lower()
        assert len(r.content) > 1024, f"PDF troppo piccolo: {len(r.content)} bytes"
        assert r.content[:4] == b"%PDF"

    def test_mini_bilancio_export_xlsx(self, s):
        r = s.get(f"{API}/cervello/mini-bilancio/export",
                  params={"dal": YEAR_START, "al": TODAY, "formato": "xlsx"})
        assert r.status_code == 200
        ct = r.headers.get("content-type", "").lower()
        assert "spreadsheet" in ct or "xlsx" in ct or "openxml" in ct
        assert len(r.content) > 1024


# ============ 5. VOCI DI BILANCIO ============
class TestVociBilancio:
    def test_list_seeded(self, s):
        r = s.get(f"{API}/librerie/voci-bilancio")
        assert r.status_code == 200
        items = r.json()
        assert len(items) > 0, "voci_bilancio vuoto"
        names = {(i.get("nome") or "").upper() for i in items}
        # almeno alcuni seed attesi
        attesi = ["STIPENDI", "AFFITTO", "UTENZE"]
        found = [n for n in attesi if n in names]
        assert len(found) >= 1, f"Nessuna voce seed trovata. Presenti: {names}"

    def test_crud_and_validation(self, s):
        uniq = uuid.uuid4().hex[:6]
        # POST empty name -> 400
        r = s.post(f"{API}/librerie/voci-bilancio", json={"nome": "", "tipo": "costo"})
        assert r.status_code == 400

        # POST valido
        r = s.post(f"{API}/librerie/voci-bilancio", json={"nome": f"TEST_VOCE_{uniq}", "tipo": "costo"})
        assert r.status_code in (200, 201), r.text
        vid = r.json()["id"]

        try:
            # PUT rename
            r = s.put(f"{API}/librerie/voci-bilancio/{vid}",
                      json={"nome": f"TEST_VOCE_{uniq}_UPD"})
            assert r.status_code == 200
            assert r.json()["nome"] == f"TEST_VOCE_{uniq}_UPD"

            # PUT empty name -> 400
            r = s.put(f"{API}/librerie/voci-bilancio/{vid}", json={"nome": ""})
            assert r.status_code == 400
        finally:
            r = s.delete(f"{API}/librerie/voci-bilancio/{vid}")
            assert r.status_code == 200


# ============ 6. MOVIMENTO CON VOCE BILANCIO -> mini bilancio ============
class TestMovimentoVoceBilancio:
    def test_movimento_uses_voce_and_shows_in_minibilancio(self, s):
        uniq = uuid.uuid4().hex[:6]
        # crea voce costo
        r = s.post(f"{API}/librerie/voci-bilancio",
                   json={"nome": f"TEST_STIP_{uniq}", "tipo": "costo"})
        assert r.status_code in (200, 201)
        vid = r.json()["id"]

        # baseline mini-bilancio
        r = s.get(f"{API}/cervello/mini-bilancio", params={"dal": YEAR_START, "al": TODAY})
        base = r.json()
        base_voce = next((c for c in base["costi"] if c["key"] == vid), None)
        base_val = base_voce["totale"] if base_voce else 0.0
        base_costi = base["totale_costi"]

        # movimento con voce
        r = s.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": TODAY,
            "tipo": "uscita",
            "categoria": "spese_amministrative",
            "importo": 500.0,
            "descrizione": f"TEST_STIP_MOV_{uniq}",
            "mezzo_pagamento": "CONTANTI",
            "voce_bilancio_id": vid,
        })
        assert r.status_code in (200, 201), r.text
        mid = r.json()["id"]

        try:
            r = s.get(f"{API}/cervello/mini-bilancio", params={"dal": YEAR_START, "al": TODAY})
            mb = r.json()
            voce = next((c for c in mb["costi"] if c["key"] == vid), None)
            assert voce is not None, f"voce {vid} non presente in mini-bilancio costi"
            assert abs(voce["totale"] - (base_val + 500.0)) < 0.02, \
                f"voce totale atteso {base_val + 500} got {voce['totale']}"

            # drill-down
            r = s.get(f"{API}/cervello/mini-bilancio/dettaglio",
                      params={"key": vid, "dal": YEAR_START, "al": TODAY})
            det = r.json()
            assert any(row.get("id") == mid for row in det["rows"]), \
                "movimento non presente nel drill-down della voce"
        finally:
            s.delete(f"{API}/contabilita/movimenti/{mid}")
            s.delete(f"{API}/librerie/voci-bilancio/{vid}")

        # dopo delete → mini bilancio torna al valore precedente
        r = s.get(f"{API}/cervello/mini-bilancio", params={"dal": YEAR_START, "al": TODAY})
        post = r.json()
        assert abs(post["totale_costi"] - base_costi) < 0.02, \
            f"totale_costi non ripristinato: base={base_costi} post={post['totale_costi']}"


# ============ 7. REGRESSIONE TIPI PAGAMENTO ============
class TestRegressioneTipiPagamento:
    def test_lista_conti_cassa_has_expected(self, s):
        r = s.get(f"{API}/librerie/conti-cassa")
        assert r.status_code == 200
        names = {(c.get("nome") or "").upper() for c in r.json()}
        # dal problem statement: CONTANTI, BONIFICO INTESA, PAGAMENTO IN DIREZIONE ...
        assert any("CONTANTI" in n for n in names)
        assert any("INTESA" in n for n in names)
        assert any("DIREZIONE" in n for n in names)
