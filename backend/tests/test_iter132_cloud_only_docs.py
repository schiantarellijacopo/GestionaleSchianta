# Iter 132 — Cloud-only document storage (Google Drive) for anagrafica cards, allegati, custom cards, sync-pending
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
AID = "42a86341-50d5-4c65-b2aa-bc28c352dfb8"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\nTEST_CLOUD_" + str(time.time()).encode()


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": "admin@assicura.it", "password": "Admin123!"}, timeout=20)
    if r.status_code != 200:
        pytest.skip("login failed")
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        sess.headers["Authorization"] = f"Bearer {tok}"
    return sess


@pytest.fixture(scope="module")
def anag_name(s):
    a = s.get(f"{API}/anagrafiche/{AID}", timeout=20).json()
    return (a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}").strip()


# Anagrafica card: upload -> download -> replace -> delete
class TestAnagCard:
    state = {}

    def test_upload_cloud_only(self, s, anag_name):
        r = s.post(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd",
                   files={"file": ("TEST_mandato.pdf", PDF, "application/pdf")}, timeout=120)
        assert r.status_code == 200, r.text
        e = r.json()["mandato_sdd"]
        assert e["doc_id"]
        assert e["storage_provider"] == "google_drive"
        assert e["pending_sync"] is False
        assert "storage_path" not in e
        cs = e["cloud_sync"]
        assert cs["file_id"]
        assert cs["path"].startswith("Assicura CRM/Anagrafiche/")
        assert cs["path"].endswith("/Mandato SDD")
        assert anag_name.split()[0] in cs["path"]
        assert f"[{e['doc_id']}]" in cs["name"]
        TestAnagCard.state["first"] = e
        # persisted
        a = s.get(f"{API}/anagrafiche/{AID}", timeout=20).json()
        pe = a["documenti"]["mandato_sdd"]
        assert pe["doc_id"] == e["doc_id"] and "storage_path" not in pe

    def test_download_from_cloud(self, s):
        r = s.get(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd/download", timeout=120)
        assert r.status_code == 200, r.text[:200]
        assert r.content == PDF

    def test_replace(self, s):
        first = TestAnagCard.state["first"]
        r = s.post(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd",
                   files={"file": ("TEST_mandato2.pdf", PDF + b"v2", "application/pdf")}, timeout=120)
        assert r.status_code == 200
        e = r.json()["mandato_sdd"]
        assert e["doc_id"] != first["doc_id"]
        assert e["cloud_sync"]["file_id"] != first["cloud_sync"]["file_id"]
        TestAnagCard.state["second"] = e
        d = s.get(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd/download", timeout=120)
        assert d.status_code == 200 and d.content == PDF + b"v2"

    def test_delete(self, s):
        r = s.delete(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd", timeout=60)
        assert r.status_code == 200 and r.json().get("ok") is True
        a = s.get(f"{API}/anagrafiche/{AID}", timeout=20).json()
        assert "mandato_sdd" not in (a.get("documenti") or {})
        d = s.get(f"{API}/anagrafiche/{AID}/documenti/mandato_sdd/download", timeout=30)
        assert d.status_code == 404


# Allegato polizza -> Drive
class TestAllegatoPolizza:
    def test_polizza_allegato(self, s):
        pol = s.get(f"{API}/polizze?page=1&page_size=1", timeout=30).json()
        pol = pol[0] if isinstance(pol, list) else (pol.get("items") or pol.get("data"))[0]
        pid, num = pol["id"], pol["numero_polizza"]
        r = s.post(f"{API}/allegati", params={"entita_tipo": "polizza", "entita_id": pid, "categoria": "condizioni"},
                   files={"file": ("TEST_cond.pdf", PDF, "application/pdf")}, timeout=120)
        assert r.status_code == 201, r.text
        al = r.json()
        try:
            assert al["storage_provider"] == "google_drive"
            assert al["pending_sync"] is False
            assert not al.get("storage_path")
            assert al["cloud_sync"]["path"] == f"Assicura CRM/Polizze/{num}/Condizioni"  # real card label from CARD_DEFS
            d = s.get(f"{API}/allegati/{al['id']}/download", timeout=120)
            assert d.status_code == 200 and d.content == PDF
        finally:
            x = s.delete(f"{API}/allegati/{al['id']}", timeout=60)
            assert x.status_code == 200 and x.json().get("ok") is True
        d2 = s.get(f"{API}/allegati/{al['id']}/download", timeout=30)
        assert d2.status_code == 404


# Custom card -> real label subfolder
class TestCustomCard:
    def test_custom_card_subfolder(self, s):
        r = s.post(f"{API}/config/card-custom", json={"entita": "anagrafica", "label": "Bonus Malus"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        key = body.get("key") or (body.get("card") or {}).get("key") or "custom_bonus_malus"
        assert key == "custom_bonus_malus", body
        al_id = None
        try:
            u = s.post(f"{API}/allegati", params={"entita_tipo": "anagrafica", "entita_id": AID, "categoria": key},
                       files={"file": ("TEST_bm.pdf", PDF, "application/pdf")}, timeout=120)
            assert u.status_code == 201, u.text
            al = u.json()
            al_id = al["id"]
            assert al["storage_provider"] == "google_drive"
            assert al["cloud_sync"]["path"].endswith("/Bonus Malus"), al["cloud_sync"]["path"]
            assert "Anagrafiche/" in al["cloud_sync"]["path"]
        finally:
            if al_id:
                s.delete(f"{API}/allegati/{al_id}", timeout=60)
            d = s.delete(f"{API}/config/card-custom/anagrafica/custom_bonus_malus", timeout=30)
            assert d.status_code in (200, 204)


# Sync pending
class TestSyncPending:
    def test_sync_pending(self, s):
        r = s.post(f"{API}/librerie/cloud-storage/sync-pending", timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True and "moved" in j and "failed" in j
        print("sync-pending:", j)
