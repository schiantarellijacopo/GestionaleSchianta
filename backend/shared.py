"""Helper condivisi usati da server.py e dai router modulari in routes/.

Estratti da server.py per consentire l'import senza dipendere dal monolite.
"""
from __future__ import annotations
import calendar as _cal
from datetime import datetime
from typing import Optional

from database import db
from db_models import AttivitaLog, DiarioVoce, _now_iso  # noqa: F401


# ---------------------------------------------------------------------------
# Costanti business
# ---------------------------------------------------------------------------
_MESI_PER_FRAZIONAMENTO = {
    "annuale": 12,
    "semestrale": 6,
    "quadrimestrale": 4,
    "trimestrale": 3,
    "mensile": 1,
    "unica": 12,
}

# Mapping mezzo_pagamento -> tipo ContoCassa (fallback statico).
_MEZZO_TO_TIPO = {
    "contanti": "cassa",
    "bonifico": "banca",
    "assegno": "banca",
    "pos": "carta",
    "carta": "carta",
    "rid": "rid",
    "online": "online",
    "altro": "altro",
}

_CORPO_LETTERA_DEFAULT = (
    "Gentile {cliente},\n\n"
    "le ricordiamo che il/i seguente/i titolo/i risulta/risultano in scadenza e in attesa di pagamento.\n"
    "La invitiamo a regolarizzare la posizione il prima possibile presso i nostri uffici "
    "oppure tramite i mezzi di pagamento da Lei abituali.\n\n"
    "Per qualsiasi informazione, restiamo a Sua completa disposizione.\n\n"
    "Cordiali saluti,\n"
    "{agenzia}"
)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
def calcola_scadenza_titolo(effetto: Optional[str], frazionamento: str) -> Optional[str]:
    """Calcola la scadenza del titolo aggiungendo all'effetto i mesi del frazionamento."""
    if not effetto:
        return None
    try:
        d = datetime.strptime(effetto, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    mesi = _MESI_PER_FRAZIONAMENTO.get(frazionamento, 12)
    nuovo_anno = d.year + (d.month - 1 + mesi) // 12
    nuovo_mese = (d.month - 1 + mesi) % 12 + 1
    giorno = min(d.day, _cal.monthrange(nuovo_anno, nuovo_mese)[1])
    return f"{nuovo_anno:04d}-{nuovo_mese:02d}-{giorno:02d}"


# ---------------------------------------------------------------------------
# Premio ANNUO di polizza (da titolo rata × numero rate/anno)
# ---------------------------------------------------------------------------
# Numero di rate che compongono l'annualità per ciascun frazionamento.
_RATE_PER_ANNO = {
    "annuale": 1,
    "semestrale": 2,
    "quadrimestrale": 3,
    "trimestrale": 4,
    "mensile": 12,
    "unica": 1,
}

# Solo questi tipi di titolo aggiornano il Premio Annuo di polizza.
# I titoli di sospensione/regolazione (e gli altri) NON toccano la scheda polizza.
TIPI_TITOLO_ANNUALIZZA = {"nuova", "rinnovo", "quietanza"}


async def ricalcola_premio_annuo_polizza(db, polizza_id: Optional[str]) -> None:
    """Allinea i premi/provvigioni della SCHEDA POLIZZA al Premio ANNUO calcolato
    dall'ultimo titolo valido (rata × numero rate dell'anno).

    Regole (richiesta utente):
      - vale SOLO per i titoli di tipo nuova / rinnovo / quietanza;
      - i titoli di sospensione / regolazione (e altri) non aggiornano la polizza;
      - Premio Annuo = importo della rata × rate/anno (es. semestrale ×2, mensile ×12);
      - sovrascrive i campi premio_* / diritti / provvigioni della polizza;
      - le quote collaboratore/margine sono ricalcolate in lettura dallo schema.
    """
    if not polizza_id:
        return
    pol = await db.polizze.find_one(
        {"id": polizza_id}, {"_id": 0, "frazionamento": 1})
    if not pol:
        return
    t = await db.titoli.find(
        {"polizza_id": polizza_id, "tipo": {"$in": list(TIPI_TITOLO_ANNUALIZZA)}},
        {"_id": 0, "importo_netto": 1, "imposte": 1, "ssn": 1, "accessori": 1,
         "diritti": 1, "importo_lordo": 1, "provvigioni": 1, "effetto": 1,
         "scadenza": 1},
    ).sort([("effetto", -1), ("scadenza", -1)]).limit(1).to_list(1)
    if not t:
        return
    tit = t[0]
    fraz = (pol.get("frazionamento") or "annuale").strip().lower()
    f = _RATE_PER_ANNO.get(fraz, 1)

    def _a(v):
        return round(float(v or 0.0) * f, 2)

    upd = {
        "premio_netto": _a(tit.get("importo_netto")),
        "premio_imposte": _a(tit.get("imposte")),
        "premio_ssn": _a(tit.get("ssn")),
        "premio_accessori": _a(tit.get("accessori")),
        "diritti": _a(tit.get("diritti")),
        "premio_lordo": _a(tit.get("importo_lordo")),
        "provvigioni": _a(tit.get("provvigioni")),
        "updated_at": _now_iso(),
    }
    await db.polizze.update_one({"id": polizza_id}, {"$set": upd})



# ---------------------------------------------------------------------------
# Mongo helpers
# ---------------------------------------------------------------------------
def strip_mongo_id(doc: dict | None) -> dict | None:
    """Rimuove `_id` (BSON ObjectId non-JSON-serializable) da un documento."""
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Logging applicativo
# ---------------------------------------------------------------------------
async def log_attivita(utente: dict, azione: str, entita: str,
                       entita_id: str | None = None, descrizione: str | None = None,
                       payload: dict | None = None) -> None:
    log = AttivitaLog(
        utente_id=utente.get("id") if utente else None,
        utente_email=utente.get("email") if utente else None,
        utente_nome=(utente.get("name") or utente.get("email")) if utente else None,
        azione=azione, entita=entita, entita_id=entita_id,
        descrizione=descrizione, payload=payload,
    )
    await db.attivita_log.insert_one(log.model_dump())


async def log_diario_cliente(anagrafica_id: str, tipo: str, titolo: str,
                             descrizione: str | None = None,
                             autore: dict | None = None,
                             payload: dict | None = None) -> None:
    """Crea automaticamente una voce di diario sull'anagrafica cliente.

    ``payload`` (opzionale) collega la voce a un record esterno (storico avvisi,
    sinistro, ecc.) così l'UI può offrire "Visualizza contenuto" e "Rimanda"
    sulla stessa voce senza duplicare i dati.
    """
    if not anagrafica_id:
        return
    voce = DiarioVoce(
        anagrafica_id=anagrafica_id,
        data_evento=_now_iso()[:10],
        tipo=tipo, titolo=titolo, descrizione=descrizione,
        autore_id=autore.get("id") if autore else None,
        autore_nome=autore.get("name") if autore else "Sistema",
        payload=payload or {},
    )
    await db.diario.insert_one(voce.model_dump())


async def log_storico_e_diario(
    *, canale: str, contraente_id: Optional[str], contraente_nome: Optional[str],
    destinatario: str, messaggio: str, oggetto: Optional[str] = None,
    titoli_ids: Optional[list] = None, tipo_avviso: str = "comunicazione",
    importo: float = 0.0, esito: str = "inviato",
    operatore: Optional[dict] = None,
    diario_tipo: str = "whatsapp", diario_titolo: Optional[str] = None,
) -> str:
    """Salva la comunicazione in ``db.storico_avvisi`` E in ``db.diario`` del
    cliente, con link bidirezionale (il payload del diario contiene ``storico_id``).

    Ritorna l'id del record di storico creato (usabile per "Visualizza/Rimanda").
    """
    import uuid
    storico_id = str(uuid.uuid4())
    await db.storico_avvisi.insert_one({
        "id": storico_id, "canale": canale, "contraente_id": contraente_id,
        "contraente_nome": contraente_nome, "destinatario": destinatario,
        "target": destinatario, "titoli_ids": titoli_ids or [],
        "oggetto": oggetto or diario_titolo or "Comunicazione",
        "soggetto": oggetto or diario_titolo or "Comunicazione",
        "messaggio": messaggio, "tipo": tipo_avviso, "importo": importo,
        "esito": esito, "sent_at": _now_iso(),
        "operatore_id": (operatore or {}).get("id"),
        "operatore_nome": (operatore or {}).get("name") or (operatore or {}).get("email"),
    })
    if contraente_id:
        # Descrizione breve per la timeline (max ~200 char di anteprima messaggio)
        preview = (messaggio or "")[:200]
        if len(messaggio or "") > 200:
            preview += "…"
        await log_diario_cliente(
            anagrafica_id=contraente_id,
            tipo=diario_tipo,
            titolo=diario_titolo or f"{canale.upper()}: {oggetto or 'Comunicazione'}",
            descrizione=preview,
            autore=operatore,
            payload={
                "storico_avvisi_id": storico_id,
                "canale": canale,
                "destinatario": destinatario,
                "esito": esito,
                "tipo_avviso": tipo_avviso,
            },
        )
    return storico_id


# ---------------------------------------------------------------------------
# ContoCassa resolution
# ---------------------------------------------------------------------------
async def resolve_conto_cassa(mezzo: str | None, fallback_any: bool = True) -> str | None:
    """Risolve un conto_cassa_id a partire dal mezzo di pagamento.

    Strategia:
    1. Match diretto per NOME conto_cassa (i dropdown ora inviano il nome del conto).
    2. Legacy: label `tipi_pagamento` → conto_id.
    3. Libreria `mezzi_pagamento` (codice match) → `conto_default_id` o `tipo_conto`.
    4. Mappatura statica `_MEZZO_TO_TIPO`.
    5. Fallback al primo ContoCassa attivo.
    """
    if mezzo:
        import re as _re
        rx = {"$regex": f"^{_re.escape(mezzo.strip())}$", "$options": "i"}
        c = await db.conti_cassa.find_one({"nome": rx, "attivo": True}, {"_id": 0, "id": 1})
        if c:
            return c["id"]
        tp = await db.tipi_pagamento.find_one({"label": rx}, {"_id": 0, "conto_id": 1})
        if tp and tp.get("conto_id"):
            c = await db.conti_cassa.find_one(
                {"id": tp["conto_id"], "attivo": True}, {"_id": 0, "id": 1},
            )
            if c:
                return c["id"]
        m_low = mezzo.lower()
        mz = await db.mezzi_pagamento.find_one(
            {"codice": m_low, "attivo": True}, {"_id": 0},
        )
        if mz:
            if mz.get("conto_default_id"):
                c = await db.conti_cassa.find_one(
                    {"id": mz["conto_default_id"], "attivo": True}, {"_id": 0, "id": 1},
                )
                if c:
                    return c["id"]
            tipo = mz.get("tipo_conto")
            if tipo:
                c = await db.conti_cassa.find_one(
                    {"tipo": tipo, "attivo": True}, {"_id": 0, "id": 1},
                    sort=[("ordine", 1)],
                )
                if c:
                    return c["id"]
        tipo = _MEZZO_TO_TIPO.get(m_low)
        if tipo:
            c = await db.conti_cassa.find_one(
                {"tipo": tipo, "attivo": True}, {"_id": 0, "id": 1},
                sort=[("ordine", 1)],
            )
            if c:
                return c["id"]
    if fallback_any:
        c = await db.conti_cassa.find_one(
            {"attivo": True}, {"_id": 0, "id": 1}, sort=[("ordine", 1)],
        )
        if c:
            return c["id"]
    return None


# ---------------------------------------------------------------------------
# PDF intestazione (azienda)
# ---------------------------------------------------------------------------
async def intestazione_pdf() -> dict:
    """Ritorna kwargs (ragione_sociale, logo_bytes, indirizzo, contatti, note_footer)
    per `pdf_report.stampa_elenco`. Ritorna {} se la config azienda non è disponibile.
    """
    try:
        import pdf_report
        return await pdf_report.get_intestazione_azienda(db)
    except Exception:
        return {}


async def visibility_filter(user: dict, base_filter: dict | None = None) -> dict:
    """Applica filtro per ruolo:
    - admin: vede tutto
    - collaboratore: vede SOLO i propri record (filtro su collaboratore_id == user.id).
      I documenti senza collaboratore_id sono visibili (es. anagrafiche storiche)
      a meno che l'utente abbia ``solo_miei_obbligatorio: True`` nel profilo.
    - dipendente: vede tutto (come admin per i propri compiti)
    - cliente: vede solo le proprie polizze/anagrafica
    """
    base_filter = dict(base_filter or {})
    if user["role"] == "cliente" and user.get("anagrafica_id"):
        base_filter["contraente_id"] = user["anagrafica_id"]
    elif user["role"] == "collaboratore" and user.get("id"):
        # Filtro su collaboratore_id (record assegnati). Compat: $or per accettare
        # record privi del campo (legacy) — disabilitabile in futuro tramite flag.
        base_filter["$or"] = [
            {"collaboratore_id": user["id"]},
            {"collaboratore_id": {"$exists": False}},
            {"collaboratore_id": None},
        ]
    return base_filter


# ---------------------------------------------------------------------------
# Prima Nota — lock su giornata chiusa
# ---------------------------------------------------------------------------
async def giornata_chiusa(data: str | None) -> dict | None:
    """Ritorna la ChiusuraGiorno ATTIVA (riaperta_at == None) per la data indicata,
    oppure None se la giornata è aperta / dato non valido.

    `data` può essere YYYY-MM-DD (tipicamente data_movimento, data_incasso, ecc.).
    """
    if not data:
        return None
    # accetta anche datetime ISO con timezone — prendo i primi 10 caratteri
    giorno = str(data)[:10]
    if len(giorno) != 10 or giorno[4] != "-" or giorno[7] != "-":
        return None
    return await db.chiusure_giorno.find_one(
        {"data": giorno, "riaperta_at": None}, {"_id": 0, "id": 1, "data": 1},
    )


async def assert_giornata_aperta(data: str | None, azione: str = "modificare") -> None:
    """Solleva HTTPException 400 se la prima nota del giorno è chiusa.

    Da chiamare PRIMA di update/delete su entità che impattano la Prima Nota:
    movimenti, titoli (per data_incasso), rappel, voci_manuali_collab,
    pagamenti_provvigioni, ecc.
    """
    from fastapi import HTTPException
    ch = await giornata_chiusa(data)
    if ch:
        raise HTTPException(
            400,
            f"Prima Nota del {ch['data']} chiusa — riaprire la chiusura per {azione}.",
        )
