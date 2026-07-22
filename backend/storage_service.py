"""StorageService — astrazione multi-provider per l'archiviazione file.

Driver supportati (attivi/pianificati):
- `emergent`  → attivo. Wrapper attorno a storage.py (Emergent Object Storage).
- `s3`         → stub. Sarà `boto3` + Presigned URL quando l'utente fornirà le
                  credenziali AWS.
- `google_drive` → stub. OAuth2 tramite Google API.
- `onedrive`  → stub. Microsoft Graph API.

Ogni file salvato include SEMPRE il prefisso di tenant:
    /agencies/{tenant_id}/clients/{client_id}/...
    /agencies/{tenant_id}/policies/{policy_id}/...

Il tenant è determinato dall'utente loggato via `tenant.user_tenant_id(user)`.

`StorageService.put(...)` ritorna un dict {storage_path, provider, size, ...}
che va salvato su `Allegato.storage_path` + `Allegato.storage_provider`.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

import storage as _emergent_storage
from tenant import user_tenant_id, TENANT_PRINCIPALE_ID

logger = logging.getLogger(__name__)


SUPPORTED_PROVIDERS = ("emergent", "s3", "google_drive", "onedrive")
DEFAULT_PROVIDER = "emergent"


def _sanitize(segment: str) -> str:
    """Sanifica un segmento path (no slash iniziali/finali, no dot leading)."""
    s = (segment or "").strip().strip("/").replace("..", "_")
    return s or "misc"


def build_path(*, tenant_id: str, entita_tipo: str, entita_id: str,
               filename: str) -> str:
    """Costruisce il path canonico gerarchico multi-tenant.

    Esempi:
        /agencies/{tid}/clients/{aid}/foto.jpg
        /agencies/{tid}/policies/{pid}/scan.pdf
    """
    tid = _sanitize(tenant_id) or TENANT_PRINCIPALE_ID
    entita_map = {
        "anagrafica": "clients",
        "polizza": "policies",
        "sinistro": "claims",
        "titolo": "titles",
        "compagnia": "companies",
        "corso": "courses",
        "movimento": "movements",
    }
    folder = entita_map.get(entita_tipo, entita_tipo)
    return f"agencies/{tid}/{folder}/{_sanitize(entita_id)}/{_sanitize(filename)}"


class StorageDriver:
    """Interfaccia base — ogni driver implementa put/get/delete/get_signed_url."""

    name: str = "base"

    def put(self, path: str, data: bytes, content_type: str) -> dict[str, Any]:
        raise NotImplementedError

    def get(self, path: str) -> tuple[bytes, str]:
        raise NotImplementedError

    def delete(self, path: str) -> bool:
        raise NotImplementedError

    def get_signed_url(self, path: str, expires_sec: int = 3600) -> Optional[str]:
        """Ritorna un URL firmato temporaneo (per S3/Drive/OneDrive).
        Emergent non li supporta → None."""
        return None


class EmergentDriver(StorageDriver):
    name = "emergent"

    def put(self, path: str, data: bytes, content_type: str) -> dict[str, Any]:
        res = _emergent_storage.put_object(path, data, content_type)
        return {"provider": self.name, "storage_path": path, "meta": res}

    def get(self, path: str) -> tuple[bytes, str]:
        return _emergent_storage.get_object(path)

    def delete(self, path: str) -> bool:
        return _emergent_storage.delete_object(path)


class S3Driver(StorageDriver):
    """Placeholder — implementazione completa quando arriveranno le credenziali AWS."""
    name = "s3"

    def put(self, path: str, data: bytes, content_type: str) -> dict[str, Any]:
        raise NotImplementedError(
            "Driver S3 non ancora configurato. Contatta l'amministratore per fornire "
            "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_S3_BUCKET.",
        )

    def get(self, path: str) -> tuple[bytes, str]:
        raise NotImplementedError("Driver S3 non ancora configurato.")

    def delete(self, path: str) -> bool:
        raise NotImplementedError("Driver S3 non ancora configurato.")


class GoogleDriveDriver(StorageDriver):
    """Placeholder — implementazione completa quando l'agenzia farà OAuth2 con Google."""
    name = "google_drive"

    def put(self, path: str, data: bytes, content_type: str) -> dict[str, Any]:
        raise NotImplementedError(
            "Driver Google Drive non ancora collegato. Vai in Impostazioni Agenzia → "
            "Cloud Storage → Collega Google Drive.",
        )

    def get(self, path: str) -> tuple[bytes, str]:
        raise NotImplementedError("Driver Google Drive non ancora collegato.")

    def delete(self, path: str) -> bool:
        raise NotImplementedError("Driver Google Drive non ancora collegato.")


class OneDriveDriver(StorageDriver):
    """Placeholder — implementazione completa quando l'agenzia farà OAuth2 con Microsoft."""
    name = "onedrive"

    def put(self, path: str, data: bytes, content_type: str) -> dict[str, Any]:
        raise NotImplementedError(
            "Driver Microsoft OneDrive non ancora collegato. Vai in Impostazioni Agenzia → "
            "Cloud Storage → Collega OneDrive.",
        )

    def get(self, path: str) -> tuple[bytes, str]:
        raise NotImplementedError("Driver Microsoft OneDrive non ancora collegato.")

    def delete(self, path: str) -> bool:
        raise NotImplementedError("Driver Microsoft OneDrive non ancora collegato.")


DRIVERS: dict[str, StorageDriver] = {
    "emergent": EmergentDriver(),
    "s3": S3Driver(),
    "google_drive": GoogleDriveDriver(),
    "onedrive": OneDriveDriver(),
}


def get_driver(provider: str) -> StorageDriver:
    """Ritorna il driver per il provider indicato, con fallback su emergent."""
    return DRIVERS.get(provider) or DRIVERS["emergent"]


class StorageService:
    """Servizio principale — usato dalle route per salvare/recuperare file.

    Nota: async solo per uniformità con FastAPI. Le call verso i driver
    (requests) sono sincrone ma veloci.
    """

    @staticmethod
    async def _resolve_provider(tenant_id: Optional[str]) -> str:
        """Ritorna il provider attivo del tenant (default: emergent)."""
        if not tenant_id:
            return DEFAULT_PROVIDER
        try:
            from database import db
            t = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "storage_provider": 1})
            return (t or {}).get("storage_provider") or DEFAULT_PROVIDER
        except Exception as e:
            logger.warning("StorageService: cannot resolve tenant provider (%s)", e)
            return DEFAULT_PROVIDER

    @staticmethod
    async def put(*, user: dict[str, Any], entita_tipo: str, entita_id: str,
                  filename: str, data: bytes, content_type: str) -> dict[str, Any]:
        tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
        provider = await StorageService._resolve_provider(tid)
        path = build_path(tenant_id=tid, entita_tipo=entita_tipo,
                          entita_id=entita_id, filename=filename)
        drv = get_driver(provider)
        try:
            res = drv.put(path, data, content_type)
        except NotImplementedError:
            # Fallback su emergent se il driver primario non è pronto
            logger.info("Provider %s non pronto per tenant %s → fallback su emergent", provider, tid)
            res = DRIVERS["emergent"].put(path, data, content_type)
            provider = "emergent"
        return {
            "storage_path": path,
            "storage_provider": provider,
            "size": len(data),
            "content_type": content_type,
            "agenzia_tenant_id": tid,
            **({k: v for k, v in res.items() if k not in {"storage_path", "provider"}}),
        }

    @staticmethod
    async def get(*, storage_path: str, storage_provider: str | None = None,
                  tenant_id: str | None = None) -> tuple[bytes, str]:
        provider = storage_provider or await StorageService._resolve_provider(tenant_id)
        drv = get_driver(provider)
        try:
            return drv.get(storage_path)
        except NotImplementedError:
            # Fallback: prova con emergent (se il file era stato salvato lì)
            return DRIVERS["emergent"].get(storage_path)

    @staticmethod
    async def delete(*, storage_path: str, storage_provider: str | None = None,
                     tenant_id: str | None = None) -> bool:
        provider = storage_provider or await StorageService._resolve_provider(tenant_id)
        drv = get_driver(provider)
        try:
            return drv.delete(storage_path)
        except NotImplementedError:
            return DRIVERS["emergent"].delete(storage_path)

    @staticmethod
    def mime_for(filename: str) -> str:
        return _emergent_storage.mime_for(filename)
