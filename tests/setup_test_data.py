"""Create test anagrafica + polizza for E2E frontend tests. Prints IDs to stdout."""
import os, requests, json, sys, uuid, datetime as dt

BASE = "https://whatsapp-crm-146.preview.emergentagent.com"
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"email":"admin@assicura.it","password":"Admin123!"})
r.raise_for_status()
token = r.json()["access_token"]
s.headers.update({"Authorization": f"Bearer {token}"})

# List compagnie & prodotti auto
comps = s.get(f"{BASE}/api/compagnie").json()
comp = next((c for c in comps if c.get("attiva")), comps[0])
comp_id = comp["id"]
print(f"compagnia: {comp.get('ragione_sociale')} ({comp_id})", file=sys.stderr)

prods = s.get(f"{BASE}/api/librerie/prodotti").json()
# find auto ramo
prod = next((p for p in prods if p.get('mostra_sezione_veicolo')), None) or next((p for p in prods if 'auto' in (p.get('ramo','')+p.get('nome','')).lower()), prods[0])
prod_id = prod["id"]
print(f"prodotto: {prod.get('nome')} ({prod_id}) ramo={prod.get('ramo')}", file=sys.stderr)

# Create anagrafica
anag_payload = {
    "tipo": "persona_fisica",
    "nome": "TESTE2E",
    "cognome": f"Iter58_{uuid.uuid4().hex[:6]}",
    "ragione_sociale": f"TESTE2E Iter58 {uuid.uuid4().hex[:6]}",
    "codice_fiscale": f"TSTITR{uuid.uuid4().hex[:10].upper()}",
    "email": "teste2e@test.local",
    "cellulare": "3331234567"
}
r = s.post(f"{BASE}/api/anagrafiche", json=anag_payload)
print("anag POST", r.status_code, r.text[:200], file=sys.stderr)
r.raise_for_status()
anag = r.json()
anag_id = anag["id"]
print(f"ANAG_ID={anag_id}")

# Create polizza with veicolo/targa + garanzie + titolo da_incassare
oggi = dt.date.today()
scad = oggi + dt.timedelta(days=180)
pol_payload = {
    "anagrafica_id": anag_id,
    "contraente_id": anag_id,
    "compagnia_id": comp_id,
    "prodotto_id": prod_id,
    "numero_polizza": f"TEST-{uuid.uuid4().hex[:8].upper()}",
    "ramo": "AUTO",
    "stato": "attiva",
    "effetto": oggi.isoformat(),
    "scadenza": scad.isoformat(),
    "data_decorrenza": oggi.isoformat(),
    "data_scadenza": scad.isoformat(),
    "premio_netto": 100.0,
    "premio_lordo": 130.0,
    "ssn": 10.0,
    "imposte": 20.0,
    "frazionamento": "annuale",
    "mezzo_pagamento": "bonifico",
    "veicolo": {"targa": "AA000AA", "marca": "FIAT", "modello": "PANDA"},
    "garanzie": [{"descrizione": "RCA", "massimale": "6.000.000", "premio": 100.0}],
    "provvigioni_operatori": []
}
r = s.post(f"{BASE}/api/polizze", json=pol_payload)
print("pol POST", r.status_code, r.text[:300], file=sys.stderr)
r.raise_for_status()
pol = r.json()
pol_id = pol["id"]
pol_num = pol.get("numero_polizza")
print(f"POL_ID={pol_id}")
print(f"POL_NUM={pol_num}")

# Create titolo da_incassare (arretrato) for storno test
tit_payload = {
    "anagrafica_id": anag_id,
    "polizza_id": pol_id,
    "tipo": "quietanza",
    "importo": 130.0,
    "data_scadenza": (oggi - dt.timedelta(days=30)).isoformat(),
    "stato": "da_incassare"
}
r = s.post(f"{BASE}/api/titoli", json=tit_payload)
print("tit POST", r.status_code, r.text[:300], file=sys.stderr)
if r.status_code < 300:
    print(f"TIT_ID={r.json().get('id')}")
