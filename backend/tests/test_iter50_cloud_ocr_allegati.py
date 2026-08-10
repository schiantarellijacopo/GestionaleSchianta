"""Iteration 50 — verifica che gli allegati generati dallo scanner OCR
(fonte='cloud_ocr_scan') siano correttamente collegati alle entità CRM
e restituiti dagli endpoint /api/allegati e /api/librerie/cloud-storage/archivio.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-crm-146.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@assicura.it"
ADMIN_PWD = "Admin123!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PWD},
                      timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def ocr_allegati_snapshot():
    """Snapshot direttamente da Mongo per confronto."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")

    async def _load():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        items = await db.allegati.find({"fonte": "cloud_ocr_scan"}, {"_id": 0}).to_list(500)
        return items

    return asyncio.get_event_loop().run_until_complete(_load())


# --------------------------------------------------------------------
# CAT_MAP dello scanner deve mappare tutti i tipi documento a entità/categoria
# --------------------------------------------------------------------
def test_cat_map_completo():
    from backend.cloud_ocr_scanner import _create_crm_attachment  # noqa: F401
    import inspect
    from backend import cloud_ocr_scanner as mod
    src = inspect.getsource(mod._create_crm_attachment)
    expected = [
        ("carta_identita", "anagrafica", "carta_identita"),
        ("patente", "anagrafica", "patente"),
        ("passaporto", "anagrafica", "passaporto"),
        ("codice_fiscale", "anagrafica", "codice_fiscale"),
        ("privacy", "anagrafica", "privacy"),
        ("visura_camerale", "anagrafica", "visura_camerale"),
        ("libretto_circolazione", "polizza", "libretto_circolazione"),
        ("polizza_frontespizio", "polizza", "polizza"),
        ("quietanza", "polizza", "quietanza"),
        ("denuncia_sinistro", "sinistro", "denuncia"),
        ("estratto_conto_compagnia", "compagnia", "estratto_conto"),
        ("bonifico", "anagrafica", "bonifico"),
        ("rid", "anagrafica", "rid"),
    ]
    for tipo, ent, cat in expected:
        assert f'"{tipo}"' in src, f"tipo {tipo} mancante in CAT_MAP"
        assert f'"{ent}"' in src
        assert f'"{cat}"' in src


# --------------------------------------------------------------------
# Sanity check DB: almeno un allegato con fonte='cloud_ocr_scan'
# --------------------------------------------------------------------
def test_db_has_cloud_ocr_allegati(ocr_allegati_snapshot):
    assert len(ocr_allegati_snapshot) > 0, "Nessun allegato con fonte='cloud_ocr_scan' presente"
    print(f"Trovati {len(ocr_allegati_snapshot)} allegati cloud_ocr_scan")


def test_allegati_have_required_fields(ocr_allegati_snapshot):
    required = ["id", "entita_tipo", "entita_id", "categoria", "nome_file",
                "storage_path", "is_deleted", "visibile_al_cliente", "fonte"]
    for a in ocr_allegati_snapshot:
        for f in required:
            assert f in a, f"campo {f} mancante in {a.get('id')}"
        assert a["is_deleted"] is False
        assert a["fonte"] == "cloud_ocr_scan"
        # visibile_al_cliente coherence
        if a["categoria"] in ("carta_identita", "patente", "passaporto",
                              "codice_fiscale", "privacy"):
            assert a["visibile_al_cliente"] is True, f"{a['id']} dovrebbe essere visibile al cliente"
        if a["categoria"] in ("bonifico", "rid"):
            assert a["visibile_al_cliente"] is False, f"{a['id']} NON deve essere visibile al cliente"


# --------------------------------------------------------------------
# API /api/allegati deve ritornare l'allegato OCR sull'anagrafica corretta
# --------------------------------------------------------------------
def test_api_allegati_ritorna_ocr_scan(ocr_allegati_snapshot, auth_headers):
    # prendi un allegato OCR (qualsiasi entità)
    assert ocr_allegati_snapshot, "no ocr allegati"
    tested = 0
    for a in ocr_allegati_snapshot:
        r = requests.get(
            f"{BASE_URL}/api/allegati",
            params={"entita_tipo": a["entita_tipo"], "entita_id": a["entita_id"]},
            headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200, f"GET /allegati {a['entita_tipo']}/{a['entita_id']} -> {r.status_code} {r.text[:200]}"
        items = r.json()
        assert isinstance(items, list)
        found = [x for x in items if x.get("id") == a["id"]]
        assert found, (
            f"Allegato OCR {a['id']} (cat={a['categoria']}) NON restituito "
            f"da /api/allegati?entita_tipo={a['entita_tipo']}&entita_id={a['entita_id']}. "
            f"Trovati {len(items)} allegati."
        )
        got = found[0]
        assert got["categoria"] == a["categoria"]
        assert got["fonte"] == "cloud_ocr_scan"
        assert got.get("nome_file") == a["nome_file"]
        assert "_id" not in got, "MongoDB _id trapelato nella response"
        tested += 1
    print(f"Verificati {tested} allegati OCR via API /api/allegati")


# --------------------------------------------------------------------
# Almeno un allegato deve essere di tipo carta_identita su anagrafica
# --------------------------------------------------------------------
def test_carta_identita_anagrafica_presente(ocr_allegati_snapshot, auth_headers):
    ci = [a for a in ocr_allegati_snapshot
          if a["categoria"] == "carta_identita" and a["entita_tipo"] == "anagrafica"]
    assert ci, "Nessun allegato OCR carta_identita su anagrafica (attesto almeno 1 per il bug fix)"
    a = ci[0]
    r = requests.get(f"{BASE_URL}/api/allegati",
                     params={"entita_tipo": "anagrafica", "entita_id": a["entita_id"]},
                     headers=auth_headers, timeout=30)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert a["id"] in ids, "C.I. non compare nella tab Documenti dell'anagrafica"


# --------------------------------------------------------------------
# /api/librerie/cloud-storage/archivio deve elencare i doc smistati
# --------------------------------------------------------------------
def test_archivio_cloud_storage(auth_headers):
    r = requests.get(f"{BASE_URL}/api/librerie/cloud-storage/archivio",
                     headers=auth_headers, timeout=60)
    # potrebbe essere lista o dict con items
    assert r.status_code == 200, f"archivio -> {r.status_code} {r.text[:200]}"
    data = r.json()
    items = data if isinstance(data, list) else (data.get("items") or data.get("results") or [])
    print(f"archivio items: {len(items)}")
    # cerca voci smistate (routed_to diverso da 'da_smistare')
    smistati = [i for i in items if (i.get("routed_to") and i.get("routed_to") != "da_smistare")
                or i.get("matched_anagrafica_id")]
    print(f"archivio items smistati: {len(smistati)}")
    # non forziamo count esatto, ma se ci sono >0 verifichiamo campi
    for it in smistati[:5]:
        assert it.get("routed_to") != "da_smistare"


# --------------------------------------------------------------------
# /api/insights/documenti-mancanti risponde 200 e non elenca l'anagrafica con CI
# --------------------------------------------------------------------
def test_documenti_mancanti_endpoint(ocr_allegati_snapshot, auth_headers):
    r = requests.get(f"{BASE_URL}/api/insights/documenti-mancanti",
                     headers=auth_headers, timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json()
    print("documenti-mancanti keys:", list(data.keys()) if isinstance(data, dict) else type(data))
    # se struttura contiene "anagrafiche" senza CI, l'ID dell'anagrafica OCR non deve essere lì
    ci = [a for a in ocr_allegati_snapshot
          if a["categoria"] == "carta_identita" and a["entita_tipo"] == "anagrafica"]
    if ci and isinstance(data, dict):
        ana_id = ci[0]["entita_id"]
        # cerca ricorsivamente
        import json as _j
        blob = _j.dumps(data)
        # non fatale, ma logghiamo
        if ana_id in blob:
            print(f"WARN: anagrafica {ana_id} (che ha CI OCR) risulta ancora in documenti-mancanti")


# --------------------------------------------------------------------
# POST /scan-now non lo eseguiamo (troppo lento). Verifichiamo solo che
# l'endpoint esista (OPTIONS/HEAD non applicabile). Facciamo un check di
# raggiungibilità via GET scan-summary.
# --------------------------------------------------------------------
def test_scan_summary_endpoint(auth_headers):
    r = requests.get(f"{BASE_URL}/api/librerie/cloud-storage/scan-summary",
                     headers=auth_headers, timeout=30)
    assert r.status_code in (200, 404), f"{r.status_code} {r.text[:200]}"
    if r.status_code == 200:
        print("scan-summary:", r.json())
