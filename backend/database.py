"""Shared MongoDB connection with **multi-tenant query wrapper**.

Ogni collection tenant-scoped viene automaticamente filtrata per
`agenzia_tenant_id` in base al `ContextVar` `_current_user_ctx` che il
middleware imposta per ogni request HTTP.

- `client`   → Motor client (per shutdown).
- `raw_db`   → connessione grezza senza filtro (usare in startup/migrazioni/webhook).
- `db`       → `TenantAwareDB` — auto-filtra le query dei router.

Le operazioni `insert_*` NON iniettano il tenant automaticamente: chi crea un
documento deve invocare `tenant.assign_tenant(user, payload)` prima di
`insert_one/insert_many` (o passare per modelli che lo fanno).
"""
import os
from contextvars import ContextVar
from motor.motor_asyncio import AsyncIOMotorClient


mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
raw_db = client[os.environ["DB_NAME"]]

# ContextVar con l'utente corrente (o None se anonimo/startup/webhook)
_current_user_ctx: ContextVar = ContextVar("_current_user_ctx", default=None)


def set_current_user(user):
    return _current_user_ctx.set(user)


def get_current_user():
    return _current_user_ctx.get()


def reset_current_user(token) -> None:
    try:
        _current_user_ctx.reset(token)
    except (ValueError, LookupError):
        pass


class TenantAwareCollection:
    """Wraps a Motor collection, iniettando il filtro tenant nelle query."""

    __slots__ = ("_coll", "_coll_name")

    def __init__(self, coll, coll_name: str):
        self._coll = coll
        self._coll_name = coll_name

    def _tenant_filter(self):
        # Import lazy per evitare cicli (tenant.py importa da database)
        from tenant import tenant_filter, TENANT_SCOPED_COLLECTIONS
        if self._coll_name not in TENANT_SCOPED_COLLECTIONS:
            return None
        user = _current_user_ctx.get()
        if user is None:
            return None
        tf = tenant_filter(user)
        return tf or None

    def _inject(self, filter_dict):
        tf = self._tenant_filter()
        if tf is None:
            return filter_dict or {}
        base = dict(filter_dict or {})
        if not base:
            return tf
        if "$or" in tf and "$or" in base:
            return {"$and": [base, tf]}
        # Merge senza sovrascrivere le chiavi base
        merged = {**base}
        for k, v in tf.items():
            if k not in merged:
                merged[k] = v
            else:
                # collisione di chiave → wrap in $and
                merged = {"$and": [base, tf]}
                break
        return merged

    # ---- Query methods (filter injection) --------------------------------
    def find(self, filter=None, *args, **kwargs):
        return self._coll.find(self._inject(filter), *args, **kwargs)

    async def find_one(self, filter=None, *args, **kwargs):
        return await self._coll.find_one(self._inject(filter), *args, **kwargs)

    async def count_documents(self, filter=None, *args, **kwargs):
        return await self._coll.count_documents(self._inject(filter or {}), *args, **kwargs)

    async def update_one(self, filter, update, *args, **kwargs):
        return await self._coll.update_one(self._inject(filter), update, *args, **kwargs)

    async def update_many(self, filter, update, *args, **kwargs):
        return await self._coll.update_many(self._inject(filter), update, *args, **kwargs)

    async def delete_one(self, filter, *args, **kwargs):
        return await self._coll.delete_one(self._inject(filter), *args, **kwargs)

    async def delete_many(self, filter, *args, **kwargs):
        return await self._coll.delete_many(self._inject(filter), *args, **kwargs)

    async def distinct(self, key, filter=None, *args, **kwargs):
        return await self._coll.distinct(key, self._inject(filter or {}), *args, **kwargs)

    async def find_one_and_update(self, filter, update, *args, **kwargs):
        return await self._coll.find_one_and_update(self._inject(filter), update, *args, **kwargs)

    async def find_one_and_delete(self, filter, *args, **kwargs):
        return await self._coll.find_one_and_delete(self._inject(filter), *args, **kwargs)

    async def find_one_and_replace(self, filter, replacement, *args, **kwargs):
        return await self._coll.find_one_and_replace(self._inject(filter), replacement, *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        """Prepende `$match: {tenant}` alla pipeline per collezioni scoped."""
        tf = self._tenant_filter()
        if tf is not None:
            pipeline = [{"$match": tf}, *list(pipeline or [])]
        return self._coll.aggregate(pipeline, *args, **kwargs)

    async def replace_one(self, filter, replacement, *args, **kwargs):
        return await self._coll.replace_one(self._inject(filter), replacement, *args, **kwargs)

    # ---- Passthrough per insert_*, create_index, drop, watch, ecc. -------
    def __getattr__(self, name):
        return getattr(self._coll, name)


class TenantAwareDB:
    __slots__ = ("_db",)

    def __init__(self, real_db):
        self._db = real_db

    def __getattr__(self, name):
        return TenantAwareCollection(getattr(self._db, name), name)

    def __getitem__(self, name):
        return TenantAwareCollection(self._db[name], name)


db = TenantAwareDB(raw_db)
