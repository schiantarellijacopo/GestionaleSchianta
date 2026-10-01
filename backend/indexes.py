"""Indici MongoDB — creati (idempotenti) allo startup per ricerche veloci."""
from __future__ import annotations

import logging

from database import db

logger = logging.getLogger(__name__)

INDEXES: dict[str, list[list[str]]] = {
    "anagrafiche": [["ragione_sociale"], ["codice_fiscale"], ["partita_iva"], ["email"],
                    ["cognome"], ["nome"], ["cellulare"], ["telefono"], ["comune"],
                    ["collaboratore_id"], ["agenzia_tenant_id"], ["tags"], ["created_at"], ["id"],
                    ["agenzia_tenant_id", "ragione_sociale"], ["agenzia_tenant_id", "cognome"],
                    ["agenzia_tenant_id", "codice_fiscale"], ["agenzia_tenant_id", "partita_iva"],
                    ["agenzia_tenant_id", "created_at"], ["agenzia_tenant_id", "collaboratore_id"]],
    "polizze": [["numero_polizza"], ["contraente_id"], ["compagnia_id"], ["collaboratore_id"],
                ["stato"], ["scadenza"], ["targa"], ["agenzia_tenant_id"], ["id"], ["ramo"],
                ["prodotto"], ["oggetto_assicurato"], ["veicoli_ids"], ["id_polizza_exp"],
                ["agenzia_tenant_id", "numero_polizza"], ["agenzia_tenant_id", "contraente_id"],
                ["agenzia_tenant_id", "scadenza"], ["agenzia_tenant_id", "stato"],
                ["agenzia_tenant_id", "compagnia_id"], ["agenzia_tenant_id", "collaboratore_id"],
                ["agenzia_tenant_id", "ramo"], ["agenzia_tenant_id", "created_at"],
                ["agenzia_tenant_id", "targa"]],
    "titoli": [["polizza_id"], ["stato"], ["scadenza"], ["data_incasso"], ["agenzia_tenant_id"],
               ["id"], ["effetto"], ["titolo_coperto"], ["numero_polizza"], ["contraente_id"],
               ["data_scadenza"], ["data_copertura"],
               ["agenzia_tenant_id", "effetto"], ["agenzia_tenant_id", "scadenza"],
               ["agenzia_tenant_id", "stato"], ["agenzia_tenant_id", "polizza_id"],
               ["agenzia_tenant_id", "data_incasso"],
               ["agenzia_tenant_id", "stato", "titolo_coperto"]],
    "sinistri": [["polizza_id"], ["contraente_id"], ["stato"], ["data_sinistro"],
                 ["numero_sinistro"], ["numero_interno"], ["agenzia_tenant_id"], ["id"],
                 ["agenzia_tenant_id", "stato"], ["agenzia_tenant_id", "data_sinistro"],
                 ["agenzia_tenant_id", "contraente_id"], ["agenzia_tenant_id", "compagnia_id"],
                 ["agenzia_tenant_id", "created_at"]],
    "allegati": [["entita_tipo", "entita_id"], ["created_at"], ["id"], ["categoria"],
                 ["applicazione_matricola_id"], ["entita_tipo", "entita_id", "categoria"],
                 ["agenzia_tenant_id", "entita_tipo", "entita_id"], ["agenzia_tenant_id", "categoria"]],
    "firma_requests": [["provider", "allegato_firmato_id"], ["entita_tipo", "entita_id"],
                       ["created_at"], ["agenzia_tenant_id", "created_at"]],
    "applicazioni": [["polizza_id"], ["stato"], ["tipo_cessazione"], ["agenzia_tenant_id"],
                     ["agenzia_tenant_id", "polizza_id"]],
    "documenti_inbox": [["agenzia_tenant_id", "stato"], ["created_at"]],
    "diario_note": [["anagrafica_id", "created_at"]],
    "users": [["email"], ["agenzia_tenant_id"], ["anagrafica_id"], ["role"],
              ["agenzia_tenant_id", "role"]],
    "veicoli": [["targa"], ["proprietario_id"], ["agenzia_tenant_id", "targa"]],
    "compagnie": [["ragione_sociale"], ["agenzia_tenant_id"]],
    "copilot_messages": [["session_id", "created_at"]],
    "copilot_sessions": [["user_id"]],
    "nb_fonti": [["notebook_id"]],
    "nb_messages": [["notebook_id", "created_at"]],
    "nb_outputs": [["notebook_id"]],
    "biblioteca_previdenza": [["cartella"], ["sezione"], ["testo_ok"]],
    "user_column_prefs": [["user_id", "table_key"]],
    "movimenti": [["data"], ["conto_id"], ["titolo_id"], ["id"], ["polizza_id"],
                  ["anagrafica_id"], ["compagnia_id"], ["conto_cassa_id"], ["chiusura_id"],
                  ["agenzia_tenant_id", "data_movimento"], ["agenzia_tenant_id", "categoria"],
                  ["agenzia_tenant_id", "tipo"], ["agenzia_tenant_id", "conto_cassa_id"],
                  ["agenzia_tenant_id", "titolo_id"]],
    "allegati_extra": [],
    "storico_avvisi": [["agenzia_tenant_id", "canale"], ["agenzia_tenant_id", "contraente_id"],
                       ["titoli_ids"], ["agenzia_tenant_id", "created_at"]],
    "conti_cassa": [["agenzia_tenant_id"], ["banca_id"], ["id"]],
    "whatsapp_messages": [["agenzia_tenant_id", "created_at"], ["anagrafica_id"], ["archived"]],
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
