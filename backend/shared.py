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
                       payload: dict | None = None) -> dict:
    log = AttivitaLog(
        utente_id=utente.get("id") if utente else None,
        utente_email=utente.get("email") if utente else None,
        azione=azione, entita=entita, entita_id=entita_id,
        descrizione=descrizione, payload=payload,
    )
    await db.attivita_log.insert_one(log.model_dump())


async def log_diario_cliente(anagrafica_id: str, tipo: str, titolo: str,
                             descrizione: str | None = None, autore: dict | None = None) -> None:
    """Crea automaticamente una voce di diario sull'anagrafica cliente."""
    if not anagrafica_id:
        return
    voce = DiarioVoce(
        anagrafica_id=anagrafica_id,
        data_evento=_now_iso()[:10],
        tipo=tipo, titolo=titolo, descrizione=descrizione,
        autore_id=autore.get("id") if autore else None,
        autore_nome=autore.get("name") if autore else "Sistema",
    )
    await db.diario.insert_one(voce.model_dump())


# ---------------------------------------------------------------------------
# ContoCassa resolution
# ---------------------------------------------------------------------------
async def resolve_conto_cassa(mezzo: str | None, fallback_any: bool = True) -> str | None:
    """Risolve un conto_cassa_id a partire dal mezzo di pagamento.

    Strategia:
    1. Libreria `mezzi_pagamento` (codice match) → `conto_default_id` o `tipo_conto`.
    2. Mappatura statica `_MEZZO_TO_TIPO`.
    3. Fallback al primo ContoCassa attivo.
    """
    if mezzo:
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
    - admin/collaboratore/dipendente: vede tutto (con restrizioni a livello azione)
    - cliente: vede solo le proprie polizze/anagrafica
    """
    base_filter = dict(base_filter or {})
    if user["role"] == "cliente" and user.get("anagrafica_id"):
        base_filter["contraente_id"] = user["anagrafica_id"]
    return base_filter
