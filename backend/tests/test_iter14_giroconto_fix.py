"""Iter14 - Verifica dei fix dei 2 bug HIGH dell'iter13.

BUG #1 FIX: Giroconto USCITA (cat=giroconto, tipo=uscita) deve avere totale=0
            nella riga brogliaccio (la regola è: "Giroconto NON in TOTALE").
BUG #2 FIX: DELETE su una riga di giroconto deve eliminare anche la riga
            gemella, sia tramite pair_id top-level (nuovi mov) sia tramite
            estrazione regex da `note` (legacy data).

Inoltre verifica che POST /api/contabilita/giroconto salvi pair_id come
campo top-level in db.movimenti (non solo nella stringa note).
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": os.environ.get("TEST_ADMIN_EMAIL", "admin@assicura.it"), "password": os.environ.get("TEST_ADMIN_PASSWORD", "Admin123!")})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def conti(client):
    r = client.get(f"{API}/librerie/conti-cassa")
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) >= 2, f"servono almeno 2 conti, trovati {len(items)}"
    return items[:2]


@pytest.fixture(scope="module")
def mongo_db():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


# ============================ FIX BUG #1 ============================

class TestGirocontoNoTotale:
    """Giroconto NON deve apparire in TOTALE per nessuna delle due righe."""

    def test_giroconto_uscita_totale_zero(self, client, conti):
        ts = int(time.time())
        data = "2026-04-01"
        gr = client.post(f"{API}/contabilita/giroconto", json={
            "data_movimento": data,
            "conto_da_id": conti[0]["id"],
            "conto_a_id": conti[1]["id"],
            "importo": 250.0,
            "descrizione": f"TEST_iter14_gr_{ts}",
        })
        assert gr.status_code in (200, 201), gr.text
        gr_data = gr.json()
        out_id = gr_data["movimento_uscita_id"]
        in_id = gr_data["movimento_entrata_id"]

        r = client.get(f"{API}/contabilita/brogliaccio", params={"data": data})
        assert r.status_code == 200, r.text
        body = r.json()
        rows_by_id = {row["id"]: row for row in body["righe"]}
        assert out_id in rows_by_id, f"riga uscita non trovata: {list(rows_by_id.keys())}"
        assert in_id in rows_by_id, f"riga entrata non trovata"
        row_out = rows_by_id[out_id]
        row_in = rows_by_id[in_id]

        # FIX BUG #1: totale=0 per entrambe le righe
        assert row_out["totale"] == 0, (
            f"BUG #1 NON RISOLTO: Giroconto USCITA ha totale={row_out['totale']} (atteso 0). "
            f"Riga completa: {row_out}"
        )
        assert row_in["totale"] == 0, (
            f"Giroconto ENTRATA ha totale={row_in['totale']} (atteso 0)"
        )
        # spese deve essere 0 sull'uscita (non è una spesa reale)
        assert row_out.get("spese", 0) == 0, f"Giroconto USCITA non deve essere in Spese: {row_out['spese']}"

        # per_conto: -importo su sorgente, +importo su destinazione
        cc0 = conti[0]["id"]
        cc1 = conti[1]["id"]
        assert row_out["per_conto"].get(cc0) == -250.0, row_out["per_conto"]
        assert row_in["per_conto"].get(cc1) == 250.0, row_in["per_conto"]

        # cleanup
        client.delete(f"{API}/contabilita/movimenti/{out_id}")


# ============================ FIX BUG #2 (top-level pair_id) ============================

class TestGirocontoPairIdTopLevel:
    """POST /contabilita/giroconto deve salvare pair_id come campo top-level."""

    def test_pair_id_present_in_db(self, client, conti, mongo_db):
        ts = int(time.time())
        data = "2026-04-02"
        gr = client.post(f"{API}/contabilita/giroconto", json={
            "data_movimento": data,
            "conto_da_id": conti[0]["id"],
            "conto_a_id": conti[1]["id"],
            "importo": 75.0,
            "descrizione": f"TEST_iter14_pair_{ts}",
        })
        assert gr.status_code in (200, 201), gr.text
        pair_id = gr.json()["pair_id"]
        out_id = gr.json()["movimento_uscita_id"]
        in_id = gr.json()["movimento_entrata_id"]

        docs = list(mongo_db.movimenti.find(
            {"id": {"$in": [out_id, in_id]}}, {"_id": 0, "id": 1, "pair_id": 1, "note": 1}
        ))
        assert len(docs) == 2, f"attesi 2 documenti, trovati {len(docs)}"
        for d in docs:
            assert d.get("pair_id") == pair_id, (
                f"FIX BUG #2 NON COMPLETO: pair_id top-level mancante o errato in doc id={d['id']}. "
                f"Atteso {pair_id}, got {d.get('pair_id')}. doc: {d}"
            )

        # cleanup
        client.delete(f"{API}/contabilita/movimenti/{out_id}")


# ============================ FIX BUG #2 (DELETE pair) ============================

class TestDeleteGirocontoPair:
    def test_delete_giroconto_cancella_coppia(self, client, conti, mongo_db):
        ts = int(time.time())
        data = "2026-04-03"
        gr = client.post(f"{API}/contabilita/giroconto", json={
            "data_movimento": data,
            "conto_da_id": conti[0]["id"],
            "conto_a_id": conti[1]["id"],
            "importo": 33.0,
            "descrizione": f"TEST_iter14_del_{ts}",
        })
        assert gr.status_code in (200, 201), gr.text
        pair_id = gr.json()["pair_id"]
        out_id = gr.json()["movimento_uscita_id"]
        in_id = gr.json()["movimento_entrata_id"]

        # DELETE una riga
        r_del = client.delete(f"{API}/contabilita/movimenti/{out_id}")
        assert r_del.status_code == 200, r_del.text
        body = r_del.json()
        assert body.get("ok") is True
        assert body.get("deleted_pair") is True, f"atteso deleted_pair=True, got {body}"

        # verifica in DB: zero documenti con quel pair_id
        cnt = mongo_db.movimenti.count_documents({"pair_id": pair_id})
        assert cnt == 0, f"FIX BUG #2: dopo DELETE coppia, attesi 0 doc con pair_id={pair_id}, trovati {cnt}"

        # verifica via API GET: la riga gemella non esiste più
        r2 = client.get(f"{API}/contabilita/movimenti", params={"dal": data, "al": data})
        movs = r2.json()
        existing_ids = {m["id"] for m in movs}
        assert out_id not in existing_ids, "out_id ancora presente"
        assert in_id not in existing_ids, f"in_id ancora presente -> coppia NON cancellata: {in_id}"

    def test_delete_giroconto_legacy_via_note_regex(self, client, conti, mongo_db):
        """Caso legacy: documenti con pair_id solo dentro `note`, NO campo top-level.
        Insertion via Mongo diretta. DELETE deve estrarre il pair_id via regex
        e cancellare entrambe le righe."""
        legacy_pair = f"GR-LEGACY-TEST-{int(time.time())}"
        data = "2026-04-04"
        out_id = f"legacy-out-{uuid.uuid4().hex[:8]}"
        in_id = f"legacy-in-{uuid.uuid4().hex[:8]}"
        from datetime import datetime, timezone as _tz
        now_iso = datetime.now(_tz.utc).isoformat()
        legacy_out = {
            "id": out_id,
            "data_movimento": data,
            "tipo": "uscita",
            "categoria": "giroconto",
            "importo": 42.0,
            "descrizione": f"TEST_iter14_legacy_out",
            "conto_cassa_id": conti[0]["id"],
            "mezzo_pagamento": "giroconto",
            "note": f"giroconto_pair_id={legacy_pair}; verso_conto_id={conti[1]['id']}",
            "created_at": now_iso,
            "updated_at": now_iso,
            # NB: nessun campo top-level pair_id (questo è il caso legacy)
        }
        legacy_in = {
            "id": in_id,
            "data_movimento": data,
            "tipo": "entrata",
            "categoria": "giroconto",
            "importo": 42.0,
            "descrizione": f"TEST_iter14_legacy_in",
            "conto_cassa_id": conti[1]["id"],
            "mezzo_pagamento": "giroconto",
            "note": f"giroconto_pair_id={legacy_pair}; da_conto_id={conti[0]['id']}",
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        mongo_db.movimenti.insert_many([legacy_out, legacy_in])

        # ora DELETE su una delle due
        r_del = client.delete(f"{API}/contabilita/movimenti/{out_id}")
        assert r_del.status_code == 200, r_del.text
        body = r_del.json()
        assert body.get("deleted_pair") is True, (
            f"DELETE legacy giroconto deve riconoscere pair_id da note via regex e cancellare coppia. "
            f"Response: {body}"
        )

        # verifica in DB: zero documenti residui con quel legacy_pair (né top-level né in note)
        cnt = mongo_db.movimenti.count_documents({
            "$or": [
                {"pair_id": legacy_pair},
                {"note": {"$regex": f"giroconto_pair_id={legacy_pair}"}},
            ]
        })
        assert cnt == 0, (
            f"BUG legacy: dopo DELETE, attesi 0 doc residui (sia top-level che note-regex), trovati {cnt}"
        )


# ============================ REGRESSIONE altri movimenti ============================

class TestRegressioneAltriMovimenti:
    """Verifica che gli altri tipi di movimento continuino a comportarsi correttamente."""

    @pytest.fixture(scope="class")
    def setup(self, client, conti):
        ts = int(time.time())
        data = "2026-04-05"
        comps = client.get(f"{API}/compagnie").json()
        comp = comps[0]
        collabs = client.get(f"{API}/collaboratori").json()
        collab = collabs[0]
        anas = client.get(f"{API}/anagrafiche").json()
        ana = anas[0]

        # 1) incasso premio
        pol = client.post(f"{API}/polizze", json={
            "numero_polizza": f"TEST_iter14_{ts}",
            "compagnia_id": comp["id"], "contraente_id": ana["id"],
            "ramo": "RCA", "effetto": data, "scadenza": "2027-04-05",
            "premio_lordo": 300.0, "collaboratore_id": collab["id"],
        }).json()
        tit = client.post(f"{API}/titoli", json={
            "polizza_id": pol["id"], "tipo": "nuova", "stato": "da_incassare",
            "data_emissione": data, "data_copertura": data,
            "effetto": data, "scadenza": "2027-04-05",
            "importo_lordo": 300.0, "provvigioni": 30.0,
        }).json()
        client.post(f"{API}/titoli/{tit['id']}/incassa", json={
            "mezzo_pagamento": "bonifico", "data_incasso": data,
            "conto_cassa_id": conti[0]["id"],
        })

        # rimessa
        rim = client.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": data, "tipo": "uscita", "categoria": "pagamento_compagnia",
            "importo": 100.0, "descrizione": f"TEST_iter14_rim_{ts}",
            "compagnia_id": comp["id"], "conto_cassa_id": conti[0]["id"],
        }).json()
        # paga provv
        pp = client.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": data, "tipo": "uscita", "categoria": "provvigioni",
            "importo": 20.0, "descrizione": f"TEST_iter14_pp_{ts}",
            "collaboratore_id": collab["id"], "conto_cassa_id": conti[0]["id"],
        }).json()
        # stipendio
        st = client.post(f"{API}/contabilita/movimenti", json={
            "data_movimento": data, "tipo": "uscita", "categoria": "spese_amministrative",
            "importo": 500.0, "descrizione": f"TEST_iter14_st_{ts}",
            "conto_cassa_id": conti[0]["id"],
        }).json()
        # rappel
        rp = client.post(f"{API}/rappel", json={
            "compagnia_id": comp["id"], "data": data, "importo": 40.0,
            "descrizione": f"TEST_iter14_rappel_{ts}", "anno": 2026,
        }).json()
        ri = client.post(f"{API}/rappel/{rp['id']}/incassa", json={"data_incasso": data})
        rappel_mov_id = ri.json()["movimento_id"]

        return {
            "data": data, "polizza_id": pol["id"],
            "rim_id": rim["id"], "pp_id": pp["id"], "st_id": st["id"],
            "rappel_mov_id": rappel_mov_id, "rappel_id": rp["id"],
            "conti": conti,
        }

    def _rows(self, client, data):
        r = client.get(f"{API}/contabilita/brogliaccio", params={"data": data})
        assert r.status_code == 200
        return {row["id"]: row for row in r.json()["righe"]}, r.json()

    def test_incasso_premio_totale_lordo(self, client, setup):
        rows, _ = self._rows(client, setup["data"])
        ip = [r for r in rows.values() if r.get("categoria") == "incasso_premio"]
        assert ip, "no incasso_premio row"
        assert any(r["totale"] == 300.0 for r in ip), f"incasso_premio totale atteso 300: {[r['totale'] for r in ip]}"

    def test_rimessa_totale_zero(self, client, setup):
        rows, _ = self._rows(client, setup["data"])
        assert rows[setup["rim_id"]]["totale"] == 0

    def test_paga_provv_totale_zero(self, client, setup):
        rows, _ = self._rows(client, setup["data"])
        assert rows[setup["pp_id"]]["totale"] == 0
        assert rows[setup["pp_id"]]["spese"] == 20.0

    def test_stipendio_totale_negativo(self, client, setup):
        rows, _ = self._rows(client, setup["data"])
        assert rows[setup["st_id"]]["totale"] == -500.0

    def test_rappel_entrata_totale_zero(self, client, setup):
        rows, _ = self._rows(client, setup["data"])
        assert rows[setup["rappel_mov_id"]]["totale"] == 0
        assert rows[setup["rappel_mov_id"]].get("provv", 0) == 40.0

    def test_kpi_entrate_solo_incasso_premio(self, client, setup):
        _, body = self._rows(client, setup["data"])
        kpi = body.get("riepilogo_kpi", {})
        # entrate cumulativo deve essere >= 300 (potrebbero esserci altri incassi precedenti)
        assert kpi.get("entrate", 0) >= 300.0, f"entrate KPI < 300: {kpi}"
