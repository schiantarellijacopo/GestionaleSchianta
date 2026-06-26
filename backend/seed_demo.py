"""Seed data demo per test."""
from datetime import datetime, date, timedelta
from db_models import (
    UserPublic, Compagnia, Anagrafica, Polizza, Titolo, Sinistro,
    MovimentoContabile, _now_iso,
)
from auth import hash_password


async def seed_demo(db):
    # User demo: sempre idempotente (anche se i dati demo sono già presenti).
    # Garantisce che gli account di test esistano e abbiano la password corretta.
    await _seed_demo_users(db, anagrafica_cliente_id=None)

    # Salta se ci sono già compagnie demo
    if await db.compagnie.find_one({"codice": "DEMO-GEN"}):
        return

    # Compagnie
    compagnie_data = [
        {"codice": "DEMO-GEN", "ragione_sociale": "Generali Italia S.p.A.", "referente": "Mario Rossi", "email": "info@generali.demo"},
        {"codice": "DEMO-ALL", "ragione_sociale": "Allianz S.p.A.", "referente": "Lucia Bianchi", "email": "info@allianz.demo"},
        {"codice": "DEMO-UNI", "ragione_sociale": "UnipolSai Assicurazioni", "referente": "Carlo Verdi", "email": "info@unipol.demo"},
    ]
    compagnie = []
    for c in compagnie_data:
        obj = Compagnia(**c)
        await db.compagnie.insert_one(obj.model_dump())
        compagnie.append(obj)

    # Anagrafiche
    anagrafiche_data = [
        {"ragione_sociale": "Rossi Marco", "codice_fiscale": "RSSMRC75H10F205X", "data_nascita": "1975-06-10",
         "comune": "Milano", "provincia": "MI", "cap": "20100", "email": "marco.rossi@demo.it",
         "telefono": "0212345678", "cellulare": "3331234567", "sesso": "M",
         "indirizzo": "Via Dante 12", "professione": "Ingegnere", "stato_civile": "coniugato"},
        {"ragione_sociale": "Bianchi Anna", "codice_fiscale": "BNCNNA80M50F205Z", "data_nascita": "1980-08-10",
         "comune": "Milano", "provincia": "MI", "cap": "20121", "email": "anna.bianchi@demo.it",
         "cellulare": "3334567890", "sesso": "F", "indirizzo": "Via Dante 12",
         "professione": "Avvocato", "stato_civile": "coniugata"},
        {"ragione_sociale": "Verdi Luca", "codice_fiscale": "VRDLCU90A10F205A", "data_nascita": "1990-01-10",
         "comune": "Roma", "provincia": "RM", "cap": "00100", "email": "luca.verdi@demo.it",
         "cellulare": "3409876543", "sesso": "M", "indirizzo": "Via Roma 5",
         "professione": "Commerciante", "stato_civile": "celibe"},
        {"ragione_sociale": "Studio Legale Ferrari S.r.l.", "tipo": "persona_giuridica",
         "partita_iva": "12345678901", "comune": "Torino", "provincia": "TO", "cap": "10100",
         "email": "info@studioferrari.demo", "telefono": "0117654321",
         "indirizzo": "Corso Vittorio Emanuele 88"},
        {"ragione_sociale": "Esposito Giovanni", "codice_fiscale": "SPSGNN65T10F839L",
         "data_nascita": "1965-12-10", "comune": "Napoli", "provincia": "NA", "cap": "80100",
         "email": "giovanni.esposito@demo.it", "cellulare": "3387654321", "sesso": "M",
         "indirizzo": "Via Toledo 100", "professione": "Pensionato"},
    ]
    anagrafiche = []
    for a in anagrafiche_data:
        obj = Anagrafica(**a)
        await db.anagrafiche.insert_one(obj.model_dump())
        anagrafiche.append(obj)

    # Relazione genealogica: Marco Rossi <-> Anna Bianchi (coniugi)
    await db.anagrafiche.update_one(
        {"id": anagrafiche[0].id},
        {"$set": {"parente_di": [{"anagrafica_id": anagrafiche[1].id, "relazione": "coniuge"}]}},
    )
    await db.anagrafiche.update_one(
        {"id": anagrafiche[1].id},
        {"$set": {"parente_di": [{"anagrafica_id": anagrafiche[0].id, "relazione": "coniuge"}]}},
    )

    # Polizze
    today = date.today()
    polizze_data = [
        {"numero_polizza": "POL-2026-00001", "compagnia_id": compagnie[0].id,
         "contraente_id": anagrafiche[0].id, "assicurato_ids": [anagrafiche[0].id],
         "ramo": "RCA", "prodotto": "Auto Premium",
         "stato": "attiva", "effetto": (today - timedelta(days=180)).isoformat(),
         "scadenza": (today + timedelta(days=185)).isoformat(),
         "premio_lordo": 850.00, "premio_netto": 700.00, "provvigioni": 85.00, "targa": "AB123CD"},
        {"numero_polizza": "POL-2026-00002", "compagnia_id": compagnie[1].id,
         "contraente_id": anagrafiche[0].id, "ramo": "INCENDIO", "prodotto": "Casa Sicura",
         "stato": "attiva", "effetto": (today - timedelta(days=90)).isoformat(),
         "scadenza": (today + timedelta(days=275)).isoformat(),
         "premio_lordo": 320.00, "premio_netto": 270.00, "provvigioni": 35.00},
        {"numero_polizza": "POL-2026-00003", "compagnia_id": compagnie[0].id,
         "contraente_id": anagrafiche[1].id, "ramo": "VITA", "prodotto": "Vita Sicura Plus",
         "stato": "attiva", "effetto": (today - timedelta(days=365)).isoformat(),
         "scadenza": (today + timedelta(days=15)).isoformat(),
         "premio_lordo": 1200.00, "premio_netto": 1100.00, "provvigioni": 120.00},
        {"numero_polizza": "POL-2026-00004", "compagnia_id": compagnie[2].id,
         "contraente_id": anagrafiche[2].id, "ramo": "RCA", "prodotto": "Moto Plus",
         "stato": "attiva", "effetto": (today - timedelta(days=200)).isoformat(),
         "scadenza": (today + timedelta(days=20)).isoformat(),
         "premio_lordo": 480.00, "premio_netto": 410.00, "provvigioni": 48.00, "targa": "XY99ZZ"},
        {"numero_polizza": "POL-2026-00005", "compagnia_id": compagnie[1].id,
         "contraente_id": anagrafiche[3].id, "ramo": "RC PROFESSIONALE", "prodotto": "Studi Legali",
         "stato": "attiva", "effetto": (today - timedelta(days=60)).isoformat(),
         "scadenza": (today + timedelta(days=305)).isoformat(),
         "premio_lordo": 2500.00, "premio_netto": 2200.00, "provvigioni": 250.00},
        {"numero_polizza": "POL-2026-00006", "compagnia_id": compagnie[2].id,
         "contraente_id": anagrafiche[4].id, "ramo": "MALATTIA", "prodotto": "Salute Senior",
         "stato": "sospesa", "effetto": (today - timedelta(days=400)).isoformat(),
         "scadenza": (today - timedelta(days=35)).isoformat(),
         "premio_lordo": 980.00, "premio_netto": 850.00, "provvigioni": 98.00},
    ]
    polizze = []
    for p in polizze_data:
        obj = Polizza(**p)
        await db.polizze.insert_one(obj.model_dump())
        polizze.append(obj)

    # Titoli (premi pagati ultimi mesi)
    for i, p in enumerate(polizze[:4]):
        for k in range(2):
            t = Titolo(
                polizza_id=p.id, tipo="rinnovo" if k > 0 else "nuova",
                effetto=(today - timedelta(days=180 - 90 * k)).isoformat(),
                scadenza=(today - timedelta(days=150 - 90 * k)).isoformat(),
                stato="incassato" if k == 0 else "da_incassare",
                importo_lordo=p.premio_lordo,
                importo_netto=p.premio_netto,
                imposte=p.premio_lordo - p.premio_netto,
                provvigioni=p.provvigioni,
                data_incasso=(today - timedelta(days=120 - 60 * k)).isoformat() if k == 0 else None,
                mezzo_pagamento="bonifico" if k == 0 else None,
            )
            await db.titoli.insert_one(t.model_dump())
            if k == 0:
                mov = MovimentoContabile(
                    data_movimento=t.data_incasso,
                    tipo="entrata", categoria="incasso_premio",
                    importo=t.importo_lordo,
                    descrizione=f"Incasso premio polizza {p.numero_polizza}",
                    polizza_id=p.id, titolo_id=t.id,
                    anagrafica_id=p.contraente_id, compagnia_id=p.compagnia_id,
                    mezzo_pagamento="bonifico",
                )
                await db.movimenti.insert_one(mov.model_dump())

    # Sinistri
    sin = Sinistro(
        numero_sinistro="SIN-2026-0001", polizza_id=polizze[0].id,
        compagnia_id=polizze[0].compagnia_id, contraente_id=polizze[0].contraente_id,
        data_avvenimento=(today - timedelta(days=45)).isoformat(),
        data_denuncia=(today - timedelta(days=44)).isoformat(),
        luogo="Milano (MI)", ramo="RCA", stato="in_istruttoria",
        descrizione="Tamponamento incrocio - lievi danni paraurti",
        riserva=2500.00, liquidazione=0.0,
    )
    await db.sinistri.insert_one(sin.model_dump())

    sin2 = Sinistro(
        numero_sinistro="SIN-2026-0002", polizza_id=polizze[1].id,
        compagnia_id=polizze[1].compagnia_id, contraente_id=polizze[1].contraente_id,
        data_avvenimento=(today - timedelta(days=10)).isoformat(),
        data_denuncia=(today - timedelta(days=9)).isoformat(),
        luogo="Milano (MI)", ramo="INCENDIO", stato="aperto",
        descrizione="Allagamento per perdita idraulica - danni a pavimentazione",
        riserva=4800.00, liquidazione=0.0,
    )
    await db.sinistri.insert_one(sin2.model_dump())

    # Demo users: dipendente + cliente collegato a Marco Rossi
    await _seed_demo_users(db, anagrafica_cliente_id=anagrafiche[0].id)


async def _seed_demo_users(db, anagrafica_cliente_id):
    """Crea/ripristina utenti demo. Idempotente.

    Se `anagrafica_cliente_id` è None, il cliente verrà comunque creato
    ma senza link all'anagrafica (verrà collegato al successivo run con
    dati demo presenti).
    """
    users_data = [
        {"email": "dipendente@assicura.it", "password": "Dipendente123!", "name": "Mario Dipendente",
         "role": "dipendente", "anagrafica_id": None},
        {"email": "collaboratore@assicura.it", "password": "Collab123!", "name": "Sara Collaboratrice",
         "role": "collaboratore", "anagrafica_id": None},
        {"email": "cliente@assicura.it", "password": "Cliente123!", "name": "Marco Rossi (Cliente)",
         "role": "cliente", "anagrafica_id": anagrafica_cliente_id},
    ]
    for u in users_data:
        existing = await db.users.find_one({"email": u["email"]})
        if existing:
            # Ripristina password e ruolo (idempotente, evita drift dei test)
            updates = {
                "password_hash": hash_password(u["password"]),
                "role": u["role"],
                "name": u["name"],
                "email": u["email"],
            }
            if u["anagrafica_id"] and not existing.get("anagrafica_id"):
                updates["anagrafica_id"] = u["anagrafica_id"]
            await db.users.update_one({"_id": existing["_id"]}, {"$set": updates})
            continue
        doc = UserPublic(email=u["email"], name=u["name"], role=u["role"],
                         anagrafica_id=u["anagrafica_id"]).model_dump()
        doc["password_hash"] = hash_password(u["password"])
        await db.users.insert_one(doc)
