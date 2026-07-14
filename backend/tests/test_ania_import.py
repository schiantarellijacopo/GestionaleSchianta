"""Test smoke per ania_importer: genera uno ZIP sintetico e verifica che l'import lavori
correttamente senza crash, popolando anagrafiche/polizze/titoli/sinistri/garanzie/veicolo."""
import asyncio
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from motor.motor_asyncio import AsyncIOMotorClient
import ania_importer


REC10 = "id_anagrafica_exp;ragione_sociale;codice_fiscale;partita_iva;data_nascita;comune_nascita;provincia_nascita;sesso_share;indirizzo;comune;provincia;cap;nazione;numero_telefono;cellulare;email;iban;consenso_privacy;data_consenso_privacy;compagnia_exp;compagnia_ania\n"
REC10 += "ANA001;ROSSI MARIO;RSSMRA80A01H501Z;;01/01/1980;ROMA;RM;M;VIA ROMA 1;ROMA;RM;00100;ITALIA;06123456;3331234567;mario@example.com;IT60X0542811101000000123456;S;01/01/2024;CATTOLICA;001\n"
REC10 += "ANA002;BIANCHI SRL;;01234567890;;;;;VIA MILANO 10;MILANO;MI;20100;ITALIA;0212345;;info@bianchi.it;;S;15/03/2024;CATTOLICA;001\n"

REC20 = "id_polizza_exp;numero_polizza_cmp;id_anagrafica_exp;compagnia_exp;compagnia_ania;ramo_share;ramo_cmp;prodotto_cmp;cod_stato_share;effetto;scadenza_originale;frazionamento_share;lordo_totale;netto_totale;provvigioni_totali\n"
REC20 += "POL001;12345678;ANA001;CATTOLICA;001;RCA;010;AUTO PLUS;A;01/06/2024;01/06/2025;2;850,50;700,00;85,05\n"
REC20 += "POL002;12345679;ANA002;CATTOLICA;001;INF;040;INFORTUNI;A;01/07/2024;01/07/2025;12;500,00;420,00;50,00\n"

REC21 = "id_polizza_exp;targa;marca_veicolo;modello_veicolo;tipo_veicolo;alimentazione;uso_veicolo;data_immatricolazione;cilindrata;cv_fiscali;kw;quintali;numero_posti;gancio_traino;targa_rimorchio;tipo_tariffa;bm_provenienza;bm_assegnata;bm_assegnata_cu;pejus;franchigia;valore_veicolo;valore_residuo;valore_accessori;guida_esperta;guida_esclusiva;rinuncia_rivalsa;massimali\n"
REC21 += "POL001;AB123CD;FIAT;PANDA;AUTOVETTURA;BENZINA;PRIVATO;01/01/2020;1200;14;55;;5;N;;BM;14;9;1;0;250;8500;6000;0;S;N;S;6 MILIONI\n"

REC30 = "id_polizza_exp;codice_garanzia;descrizione_garanzia;valore_ass_1;valore_ass_2;valore_ass_3;netto_garanzia;accessori;imposte;ssn;lordo_garanzia;diritti;provvigione_garanzia\n"
REC30 += "POL001;RCA;Responsabilità Civile Auto;6000000;0;0;500,00;20,00;120,50;30,00;670,50;5,00;50,00\n"
REC30 += "POL001;FUR;Furto e Incendio;15000;0;0;150,00;10,00;15,00;0;175,00;0;15,00\n"

REC40 = "id_titolo_exp;id_polizza_exp;effetto_titolo;data_scadenza_emesso;stato_share;lordo_totale;netto_totale;tasse_totale;accessori_totale;provvigioni_totale;dt_pag_cliente;mezzo_pag_share\n"
REC40 += "T001;POL001;01/06/2024;01/06/2025;I;850,50;700,00;150,50;25,00;85,05;05/06/2024;BON\n"
REC40 += "T002;POL002;01/07/2024;01/07/2025;D;500,00;420,00;80,00;10,00;50,00;;\n"

REC50 = "id_sinistro_exp;numero_sinistro_cmp;id_polizza_exp;id_contraente_exp;compagnia_exp;compagnia_ania;data_avvenimento;data_denuncia;comune_avvenimento;provincia_avvenimento;ramo_sinistro_share;stato_sinistro;dinamica_sinistro;riserva_totale;liquidazione_totale\n"
REC50 += "SIN001;S001;POL001;ANA001;CATTOLICA;001;15/08/2024;16/08/2024;ROMA;RM;RCA;A;Tamponamento;5000,00;0\n"


def _build_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("rec10oweb.csv", REC10)
        zf.writestr("rec20oweb.csv", REC20)
        zf.writestr("rec21oweb.csv", REC21)
        zf.writestr("rec30oweb.csv", REC30)
        zf.writestr("rec40oweb.csv", REC40)
        zf.writestr("rec50oweb.csv", REC50)
    return buf.getvalue()


async def run():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name + "_test"]
    # cleanup
    for c in ("anagrafiche", "polizze", "titoli", "sinistri", "compagnie", "import_logs"):
        await db[c].delete_many({})

    file_bytes = _build_zip()
    log = await ania_importer.importa_zip(db, file_bytes, "test.zip", {"id": "test", "ruolo": "admin"})
    print("STATO:", log.stato)
    print("Anagrafiche create:", log.anagrafiche_create, "aggiornate:", log.anagrafiche_aggiornate)
    print("Polizze create:", log.polizze_create, "aggiornate:", log.polizze_aggiornate)
    print("Titoli creati:", log.titoli_creati)
    print("Sinistri creati:", log.sinistri_creati)
    print("Record types processati:", log.record_types_processati)
    print("Errori:", log.errori)

    # verifica polizza dettagliata
    pol = await db.polizze.find_one({"id_polizza_exp": "POL001"})
    assert pol, "Polizza POL001 non trovata"
    print("\nPOL001:")
    print("  targa:", pol.get("targa"))
    print("  veicolo_marca:", pol.get("veicolo_marca"))
    print("  veicolo_modello:", pol.get("veicolo_modello"))
    print("  veicolo_alimentazione:", pol.get("veicolo_alimentazione"))
    print("  veicolo_cilindrata:", pol.get("veicolo_cilindrata"))
    print("  bm_assegnata:", pol.get("bm_assegnata"))
    print("  franchigia:", pol.get("franchigia"))
    print("  valore_veicolo:", pol.get("valore_veicolo"))
    print("  rinuncia_rivalsa:", pol.get("rinuncia_rivalsa"))
    print("  massimali:", pol.get("massimali"))
    print("  garanzie count:", len(pol.get("garanzie") or []))
    print("  diritti tot:", pol.get("diritti"))
    print("  frazionamento:", pol.get("frazionamento"))
    print("  capitale_assicurato:", pol.get("capitale_assicurato"))

    # Verifiche ANIA importer nuove colonne
    assert pol.get("frazionamento") == "semestrale", (
        f"POL001 frazionamento atteso 'semestrale' (codice ANIA 2), got {pol.get('frazionamento')!r}"
    )
    assert pol.get("capitale_assicurato") == 6000000, (
        f"POL001 capitale_assicurato atteso 6000000 (max valore_ass_1), got {pol.get('capitale_assicurato')!r}"
    )
    # Frazionamento POL002 = 12 → mensile
    pol2 = await db.polizze.find_one({"id_polizza_exp": "POL002"})
    assert pol2 and pol2.get("frazionamento") == "mensile", (
        f"POL002 frazionamento atteso 'mensile' (codice ANIA 12), got {pol2.get('frazionamento') if pol2 else None!r}"
    )
    # Garanzie con capitale_assicurato per riga
    garanzie = pol.get("garanzie") or []
    assert any(g.get("capitale_assicurato") == 6000000 for g in garanzie), (
        "Garanzia RCA POL001 dovrebbe avere capitale_assicurato=6000000"
    )
    # Titolo T001 accessori
    t1 = await db.titoli.find_one({"id_titolo_exp": "T001"})
    assert t1 and t1.get("accessori") == 25.0, (
        f"T001 accessori atteso 25.0 (rec40 accessori_totale), got {t1.get('accessori') if t1 else None!r}"
    )

    # re-import idempotenza
    log2 = await ania_importer.importa_zip(db, file_bytes, "test.zip", {"id": "test", "ruolo": "admin"})
    print("\nRe-import:")
    print("  create:", log2.anagrafiche_create, "aggiornate:", log2.anagrafiche_aggiornate)
    print("  polizze create:", log2.polizze_create, "aggiornate:", log2.polizze_aggiornate)
    assert log2.anagrafiche_create == 0
    assert log2.polizze_create == 0
    assert log2.anagrafiche_aggiornate >= 2
    assert log2.polizze_aggiornate >= 2

    # cleanup test DB
    await client.drop_database(db_name + "_test")
    print("\nOK: import + re-import idempotenti")


if __name__ == "__main__":
    asyncio.run(run())
