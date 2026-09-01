"""Indici MongoDB — creati (idempotenti) allo startup per ricerche veloci."""
from __future__ import annotations

import logging

from database import db

logger = logging.getLogger(__name__)

INDEXES: dict[str, list[list[str]]] = {
    "anagrafiche": [["ragione_sociale"], ["codice_fiscale"], ["partita_iva"], ["email"],
                    ["collaboratore_id"], ["agenzia_tenant_id"], ["tags"], ["created_at"]],
    "polizze": [["numero_polizza"], ["contraente_id"], ["compagnia_id"], ["collaboratore_id"],
                ["stato"], ["scadenza"], ["targa"], ["agenzia_tenant_id"]],
    "titoli": [["polizza_id"], ["stato"], ["scadenza"], ["data_incasso"], ["agenzia_tenant_id"]],
    "sinistri": [["polizza_id"], ["contraente_id"], ["stato"], ["data_avvenimento"],
                 ["numero_sinistro"], ["numero_interno"]],
    "allegati": [["entita_tipo", "entita_id"], ["created_at"]],
    "diario_note": [["anagrafica_id", "created_at"]],
    "users": [["email"], ["agenzia_tenant_id"], ["anagrafica_id"]],
    "veicoli": [["targa"], ["proprietario_id"]],
    "compagnie": [["ragione_sociale"]],
    "copilot_messages": [["session_id", "created_at"]],
    "copilot_sessions": [["user_id"]],
    "nb_fonti": [["notebook_id"]],
    "nb_messages": [["notebook_id", "created_at"]],
    "nb_outputs": [["notebook_id"]],
    "biblioteca_previdenza": [["cartella"], ["sezione"], ["testo_ok"]],
    "user_column_prefs": [["user_id", "table_key"]],
    "movimenti": [["data"], ["conto_id"]],
    "scambi_richieste": [["stato"], ["agenzia_richiedente_id"]],
    "tenants": [["sottodominio"]],
    "chat_portale": [["anagrafica_id"]],
    "attivita": [["created_at"]],
    "analisi_cliente": [["anagrafica_id"]],
    "piramide_templates": [["tipo"]],
}


async def ensure_indexes() -> int:
    n = 0
    for coll, idxs in INDEXES.items():
        for fields in idxs:
            try:
                await db[coll].create_index([(f, 1) for f in fields], background=True)
                n += 1
            except Exception as e:
                logger.warning("Indice %s.%s non creato: %s", coll, fields, e)
    logger.info("Indici DB garantiti: %d", n)
    return n
