"""Multi-tenant helpers.

Ogni utente appartiene a un `Tenant` (agenzia principale, demo o clean master).
Le query DB devono essere filtrate automaticamente per `agenzia_tenant_id` in
modo che l'agenzia A non veda mai i dati dell'agenzia B.

Il super-admin (utente con `role='admin'` E `is_super_admin=True`) può vedere
tutti i tenant.

Naming convention: usiamo `agenzia_tenant_id` (non `agency_id`) per rispettare
la lingua del dominio (Italiano) e distinguerlo dalla libreria `agenzie`
esistente che rappresenta invece le agenzie **partner** con cui l'agenzia
principale ha rapporti di collaborazione.
"""
from __future__ import annotations
from typing import Any, Optional
from fastapi import HTTPException

from database import db
from db_models import _now_iso, _uid


# ---------------------------------------------------------------------------
# Tenant seed IDs (idempotenti). Usiamo ID deterministici per referenziarli
# nel codice/frontend/scripts di migrazione senza doverli cercare per nome.
# ---------------------------------------------------------------------------
TENANT_PRINCIPALE_ID = "tenant-principale-schiantarelli"
TENANT_DEMO_ID = "tenant-demo-staging"
TENANT_CLEAN_ID = "tenant-clean-master"


DEFAULT_TENANTS = [
    {
        "id": TENANT_PRINCIPALE_ID,
        "ragione_sociale": "Agenzia Schiantarelli",
        "codice": "SCHIANT",
        "tipo": "principale",
        "attivo": True,
        "storage_provider": "emergent",  # emergent | s3 | google_drive | onedrive
        "storage_config": {},
        "note": "Tenant produzione con dati reali dell'agenzia principale.",
    },
    {
        "id": TENANT_DEMO_ID,
        "ragione_sociale": "Agenzia Demo (Staging)",
        "codice": "DEMO",
        "tipo": "demo",
        "attivo": True,
        "storage_provider": "emergent",
        "storage_config": {},
        "note": "Ambiente demo popolato con dati fittizi per dimostrazioni commerciali.",
    },
    {
        "id": TENANT_CLEAN_ID,
        "ragione_sociale": "Agenzia Clean Master",
        "codice": "CLEAN",
        "tipo": "clean",
        "attivo": True,
        "storage_provider": "emergent",
        "storage_config": {},
        "note": "Ambiente pulito pronto per l'onboarding di nuove agenzie.",
    },
]


async def seed_tenants() -> None:
    """Idempotent seed dei tenant di sistema."""
    for t in DEFAULT_TENANTS:
        doc = {
            **t,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await db.tenants.update_one(
            {"id": t["id"]},
            {"$setOnInsert": doc},
            upsert=True,
        )


# ---------------------------------------------------------------------------
# Collections a cui applichiamo l'isolamento multi-tenant.
# NB: librerie condivise (rami, mezzi_pagamento, tipi_pagamento) NON sono
# filtrate per tenant — sono cataloghi globali di sistema.
# ---------------------------------------------------------------------------
TENANT_SCOPED_COLLECTIONS = [
    "anagrafiche",
    "polizze",
    "titoli",
    "sinistri",
    "movimenti_contabili",
    "allegati",
    "diario_cliente",
    "diario_voci",
    "trattative",
    "voucher",
    "pagamenti_provvigioni",
    "voci_manuali_collab",
    "voci_ricorsive_collab",
    "chiusure_giorno",
    "email_inbox",
    "email_messaggi",
    "documenti_inbox",
    "leads",
    "avvisi_storico",
    "avvisi_regole",
    "avvisi_schedule",
    "attivita_log",
    "compagnie",
    "prodotti",
    "collaboratori_esterni",
    "conti_cassa",
    "banche",
    "agenzie",  # agenzie partner (una per tenant)
    "import_logs",
    "import_mappings",
    "mapping_operatori",
    "mapping_garanzie",
    "modelli_pdf",
    "profili_permessi",
    "messaggi_chat",
    "conversazioni_chat",
    "whatsapp_instances",
    "whatsapp_messages",
    "whatsapp_chats",
    "interviste",
    "calcoli_pensione",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def is_super_admin(user: dict[str, Any] | None) -> bool:
    """Un super_admin può vedere/gestire tutti i tenant."""
    if not user:
        return False
    return bool(user.get("is_super_admin")) and user.get("role") == "admin"


def user_tenant_id(user: dict[str, Any] | None) -> Optional[str]:
    """Ritorna il tenant_id dell'utente (None per super_admin senza filtro)."""
    if not user or is_super_admin(user):
        return None
    return user.get("agenzia_tenant_id") or TENANT_PRINCIPALE_ID


def tenant_filter(user: dict[str, Any] | None) -> dict[str, Any] | None:
    """Ritorna un filtro MongoDB per isolare i dati per tenant.

    - **Super admin** (owner della piattaforma SaaS): per motivi di **privacy/GDPR**
      NON deve poter accedere ai dati clienti delle agenzie tenant. Ritorna un
      filtro impossibile (`{"__super_admin_blocked__": True}`) su collezioni
      tenant-scoped → 0 risultati.
    - **Utenti normali**: filtro `{"agenzia_tenant_id": <tid>}`.

    Retro-compat: per il tenant principale include anche i doc pre-migrazione
    (senza il campo `agenzia_tenant_id`).

    NB: questa funzione è chiamata dal wrapper `TenantAwareCollection` SOLO su
    collezioni tenant-scoped (`TENANT_SCOPED_COLLECTIONS`). Per collezioni non
    scoped (tenants, subscriptions, transactions, users, librerie) il wrapper
    ritorna None → nessun filtro applicato.
    """
    if is_super_admin(user):
        # GDPR: super_admin non vede clienti/polizze/incassi/allegati delle agenzie
        return {"__super_admin_blocked__": True}
    tid = user_tenant_id(user)
    if tid == TENANT_PRINCIPALE_ID:
        return {"$or": [
            {"agenzia_tenant_id": tid},
            {"agenzia_tenant_id": {"$exists": False}},
            {"agenzia_tenant_id": None},
        ]}
    return {"agenzia_tenant_id": tid}


def assign_tenant(user: dict[str, Any] | None, doc: dict[str, Any]) -> dict[str, Any]:
    """Assegna `agenzia_tenant_id` a un documento in creazione.

    Il tenant dell'utente prevale. Il super_admin senza contesto scelto
    ricade sul tenant principale (safety).
    """
    tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
    doc = dict(doc)
    doc["agenzia_tenant_id"] = tid
    return doc


def combine_filter(user: dict[str, Any] | None, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Combina un filtro utente con il filtro tenant senza rompere gli `$or`.

    Se il tenant filter contiene un `$or` (retro-compat) e il filtro base ne
    contiene già uno, li combiniamo con `$and`.
    """
    base = dict(base or {})
    tf = tenant_filter(user)
    if not tf:
        return base
    if "$or" in tf and "$or" in base:
        return {"$and": [base, tf]}
    return {**base, **tf}


async def get_tenant(tenant_id: str) -> Optional[dict]:
    return await db.tenants.find_one({"id": tenant_id}, {"_id": 0})


async def require_tenant(tenant_id: str) -> dict:
    t = await get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} non trovato")
    return t


async def migrate_existing_data_to_principale() -> dict[str, int]:
    """Migrazione idempotente: assegna `agenzia_tenant_id=TENANT_PRINCIPALE_ID`
    a tutti i documenti pre-esistenti senza tenant.

    Ritorna un report {collection: n_docs_updated}.
    """
    report: dict[str, int] = {}
    for coll_name in TENANT_SCOPED_COLLECTIONS:
        try:
            res = await db[coll_name].update_many(
                {"agenzia_tenant_id": {"$in": [None, ""]}},
                {"$set": {"agenzia_tenant_id": TENANT_PRINCIPALE_ID}},
            )
            # dedup: anche i doc senza il campo devono essere aggiornati
            res2 = await db[coll_name].update_many(
                {"agenzia_tenant_id": {"$exists": False}},
                {"$set": {"agenzia_tenant_id": TENANT_PRINCIPALE_ID}},
            )
            report[coll_name] = int(res.modified_count) + int(res2.modified_count)
        except Exception as e:
            report[coll_name] = -1
            report[f"{coll_name}__error"] = str(e)  # type: ignore[assignment]
    # utenti: assegna tenant principale se mancante
    res_u = await db.users.update_many(
        {"$or": [{"agenzia_tenant_id": {"$exists": False}},
                 {"agenzia_tenant_id": None}, {"agenzia_tenant_id": ""}]},
        {"$set": {"agenzia_tenant_id": TENANT_PRINCIPALE_ID}},
    )
    report["users"] = int(res_u.modified_count)
    return report
