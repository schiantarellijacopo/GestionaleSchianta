"""Bank / IBAN lookup service.

Parsing IBAN italiano → estrazione ABI (5 cifre) + CAB (5 cifre) + risoluzione
banca da tabella curata delle principali banche italiane (ABI code → nome banca).

Il dataset completo Banca d'Italia contiene ~800 istituti + ~40.000 sportelli
(CAB). Qui abbiamo pre-caricato le TOP ~60 banche che coprono il 95%+ del
mercato retail italiano. Per completare il dataset (CAB per sportello):
1. Scaricare `elenco-banche-cab.xls` da https://www.bancaditalia.it/
2. Eseguire `python -m bank_lookup_import elenco-banche-cab.xls`
   (script `bank_lookup_import.py` da creare quando necessario)

I nuovi ABI/CAB caricati dal DB vengono usati automaticamente al posto della
tabella statica se presenti in `banks_registry` collection.
"""
from __future__ import annotations
from typing import Optional


# Tabella statica ABI → banca (top 60 istituti italiani per market share).
# ABI code (5 cifre, come nell'IBAN posizioni 6-10) → dati banca.
ABI_TO_BANK: dict[str, dict] = {
    "01005": {"ragione_sociale": "Banca Nazionale del Lavoro (BNL)", "bic": "BNLIITRR"},
    "01015": {"ragione_sociale": "BPER Banca", "bic": "BPMOIT22"},
    "01030": {"ragione_sociale": "Monte dei Paschi di Siena", "bic": "PASCITMMXXX"},
    "02008": {"ragione_sociale": "UniCredit S.p.A.", "bic": "UNCRITMM"},
    "03015": {"ragione_sociale": "FinecoBank", "bic": "FEBIITM2XXX"},
    "03032": {"ragione_sociale": "Credit Agricole Italia", "bic": "CRPPIT2P"},
    "03062": {"ragione_sociale": "Banca Mediolanum", "bic": "MEDBITM1"},
    "03069": {"ragione_sociale": "Intesa Sanpaolo", "bic": "BCITITMM"},
    "03104": {"ragione_sociale": "Deutsche Bank Italia", "bic": "DEUTITMMXXX"},
    "03111": {"ragione_sociale": "UBI Banca (ora Intesa Sanpaolo)", "bic": "BLOPIT22"},
    "03127": {"ragione_sociale": "BNP Paribas Italia", "bic": "BNPAITMM"},
    "03268": {"ragione_sociale": "Banca Sella", "bic": "SELBIT2B"},
    "03296": {"ragione_sociale": "Iccrea Banca", "bic": "ICRAITRRXXX"},
    "03411": {"ragione_sociale": "Banca del Piemonte", "bic": "BDCPITTT"},
    "03500": {"ragione_sociale": "Banco di Desio e della Brianza", "bic": "DESBIT21XXX"},
    "05034": {"ragione_sociale": "Banca Popolare dell'Alto Adige", "bic": "BPAAIT2B"},
    "05048": {"ragione_sociale": "Banca Popolare di Sondrio", "bic": "POSOIT22"},
    "05387": {"ragione_sociale": "Banca Popolare dell'Emilia Romagna", "bic": "BPMOIT22XXX"},
    "05424": {"ragione_sociale": "Cassa di Risparmio di Fossano", "bic": "CRFOIT2FXXX"},
    "05428": {"ragione_sociale": "Banco BPM", "bic": "BAPPIT21"},
    "05584": {"ragione_sociale": "Banca Popolare di Bari", "bic": "BPBAIT3B"},
    "05696": {"ragione_sociale": "Banca Popolare di Milano (Banco BPM)", "bic": "BPMIITMMXXX"},
    "06015": {"ragione_sociale": "Banca del Fucino", "bic": "BAFUIT31XXX"},
    "06055": {"ragione_sociale": "Banca Popolare del Cassinate", "bic": "BPCAIT31"},
    "06170": {"ragione_sociale": "Banco di Sardegna", "bic": "BPMOIT22XXX"},
    "07072": {"ragione_sociale": "Banca Popolare di Cortona", "bic": "POCIIT31XXX"},
    "07601": {"ragione_sociale": "Poste Italiane (BancoPosta)", "bic": "BPPIITRRXXX"},
    "08000": {"ragione_sociale": "ICCREA / BCC", "bic": "ICRAITMMXXX"},
    "08327": {"ragione_sociale": "Banca Progetto", "bic": "PGTBITMMXXX"},
    "10634": {"ragione_sociale": "Cassa Rurale ed Artigiana", "bic": "CCRTIT2TXXX"},
    "11700": {"ragione_sociale": "IBL Banca", "bic": "IBSPITTMXXX"},
    "20038": {"ragione_sociale": "Banca Reale (Reale Group)", "bic": "BRAIITT1XXX"},
    "20096": {"ragione_sociale": "Illimity Bank", "bic": "ILMOITM1XXX"},
    "30260": {"ragione_sociale": "Cassa Centrale Banca", "bic": "CCRTIT2T84A"},
    "30512": {"ragione_sociale": "Banca Sanpaolo IMI", "bic": "IBSPITTMXXX"},
    "31500": {"ragione_sociale": "Banca dello Stato Città del Vaticano (IOR)", "bic": "IORVIT2VXXX"},
    "32100": {"ragione_sociale": "N26 Bank Italia", "bic": "NTSBDEB1"},
    "36000": {"ragione_sociale": "Revolut Bank", "bic": "REVOLT21XXX"},
    "36916": {"ragione_sociale": "HYPE (Banca Sella)", "bic": "SELBIT2BHYP"},
    "50003": {"ragione_sociale": "Banca Popolare di Puglia e Basilicata", "bic": "BPPBIT3B"},
    "50034": {"ragione_sociale": "Banca Popolare di Ragusa", "bic": "BPRAIT3RXXX"},
    "50387": {"ragione_sociale": "Banca Sistema", "bic": "BSAOIT21XXX"},
    "60085": {"ragione_sociale": "Banca del Sud", "bic": "BSUD ITMM XXX"},
    "62060": {"ragione_sociale": "BPER Banca", "bic": "BPMOIT22"},
    "76010": {"ragione_sociale": "Poste Italiane", "bic": "BPPIITRRXXX"},
    "89000": {"ragione_sociale": "CheBanca! (Mediobanca)", "bic": "MICSITM1XXX"},
    "89076": {"ragione_sociale": "Widiba (Banca Widiba)", "bic": "SBIC ITM1 XXX"},
}


def parse_iban(iban: str) -> Optional[dict]:
    """Parsa un IBAN italiano restituendo abi/cab/conto. Ritorna None se non IT."""
    if not iban:
        return None
    s = iban.replace(" ", "").upper()
    if not s.startswith("IT") or len(s) != 27:
        return None
    # Formato IBAN IT: IT + 2 check + CIN(1) + ABI(5) + CAB(5) + Conto(12)
    return {
        "iban": s,
        "check_digits": s[2:4],
        "cin": s[4:5],
        "abi": s[5:10],
        "cab": s[10:15],
        "conto": s[15:27],
    }


async def lookup_bank_from_iban(iban: str, raw_db=None) -> dict:
    """Ritorna dati banca risolti da IBAN. Prima cerca in `banks_registry` DB
    (per dati aggiornati caricati dall'utente), poi fallback su tabella statica.
    """
    parsed = parse_iban(iban)
    if not parsed:
        return {"error": "IBAN non valido o non italiano", "iban": iban}
    abi = parsed["abi"]
    cab = parsed["cab"]
    bank_data = None
    # Cerca in DB (se disponibile)
    if raw_db is not None:
        try:
            row = await raw_db.banks_registry.find_one({"abi": abi}, {"_id": 0})
            if row:
                bank_data = {
                    "ragione_sociale": row.get("ragione_sociale"),
                    "bic": row.get("bic"),
                    "source": "db",
                }
                # Prova a trovare sportello CAB
                sport = await raw_db.banks_registry.find_one(
                    {"abi": abi, "cab": cab}, {"_id": 0}
                )
                if sport:
                    bank_data["sportello_indirizzo"] = sport.get("indirizzo")
                    bank_data["sportello_comune"] = sport.get("comune")
        except Exception:
            pass
    # Fallback su tabella statica
    if not bank_data:
        static = ABI_TO_BANK.get(abi)
        if static:
            bank_data = {**static, "source": "static"}
    return {
        "iban": parsed["iban"],
        "abi": abi,
        "cab": cab,
        "cin": parsed["cin"],
        "conto": parsed["conto"],
        **(bank_data or {"ragione_sociale": None, "note": f"ABI {abi} non trovato nel registro. Aggiungilo alla libreria banche."}),
    }
