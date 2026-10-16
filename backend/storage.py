"""Object storage helpers con fallback automatico su MongoDB (GridFS).

Strategia (vale per TUTTO il programma):
  1. Se l'Emergent Object Storage è disponibile e raggiungibile → usa quello.
  2. Altrimenti (es. Railway, dove l'object storage non è raggiungibile) →
     salva/leggi i byte da MongoDB GridFS (collection ``object_store``),
     in modo totalmente trasparente per i chiamanti.

In questo modo loghi, allegati email, PDF di prima nota, documenti, firme,
attestati, ecc. continuano a funzionare anche senza object storage.
"""
from __future__ import annotations
import os
import logging
import requests

logger = logging.getLogger(__name__)

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = os.environ.get("APP_NAME", "assicura")

_storage_key: str | None = None

# ---- GridFS (fallback MongoDB) -------------------------------------------
_fs = None  # gridfs.GridFS


def _gridfs():
    """Bucket GridFS lazy (client pymongo sincrono, separato da Motor)."""
    global _fs
    if _fs is None:
        import pymongo
        import gridfs
        url = os.environ["MONGO_URL"]
        dbname = os.environ["DB_NAME"]
        client = pymongo.MongoClient(url, serverSelectionTimeoutMS=8000)
        _fs = gridfs.GridFS(client[dbname], collection="object_store")
    return _fs


def _gridfs_put(path: str, data: bytes, content_type: str) -> None:
    fs = _gridfs()
    # Sovrascrivi: rimuovi eventuali versioni precedenti con lo stesso path
    for old in fs.find({"filename": path}):
        try:
            fs.delete(old._id)
        except Exception:  # noqa: BLE001
            pass
    fs.put(data, filename=path, contentType=content_type or "application/octet-stream")


def _gridfs_get(path: str) -> tuple[bytes, str] | None:
    fs = _gridfs()
    f = fs.find_one({"filename": path}, sort=[("uploadDate", -1)])
    if not f:
        return None
    return f.read(), (getattr(f, "content_type", None) or "application/octet-stream")


def _gridfs_delete(path: str) -> bool:
    try:
        fs = _gridfs()
        found = False
        for old in fs.find({"filename": path}):
            fs.delete(old._id)
            found = True
        return found
    except Exception:  # noqa: BLE001
        return False


# ---- Emergent object storage ---------------------------------------------
def init_storage() -> str | None:
    """Initialize storage session once. Returns storage_key or None if failure."""
    global _storage_key
    if _storage_key:
        return _storage_key
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": key}, timeout=20)
        r.raise_for_status()
        _storage_key = r.json()["storage_key"]
        logger.info("Storage initialized OK")
        return _storage_key
    except Exception as e:
        logger.warning("Storage init failed (%s); uso fallback GridFS", e)
        return None


def _reset():
    global _storage_key
    _storage_key = None


def _emergent_put(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage non configurato")
    r = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    if r.status_code == 403:
        _reset()
        key = init_storage()
        if not key:
            raise RuntimeError("Object storage non configurato")
        r = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120,
        )
    r.raise_for_status()
    return r.json()


def _emergent_get(path: str) -> tuple[bytes, str] | None:
    """Ritorna (data, ctype) o None se non presente. Solleva su errori di rete."""
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage non configurato")
    r = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60,
    )
    if r.status_code == 403:
        _reset()
        key = init_storage()
        if not key:
            raise RuntimeError("Object storage non configurato")
        r = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key}, timeout=60,
        )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")


# ---- API pubblica (con fallback trasparente) ------------------------------
def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Salva un oggetto. Prova Emergent object storage, altrimenti GridFS."""
    try:
        return _emergent_put(path, data, content_type)
    except Exception as e:  # noqa: BLE001
        logger.warning("put_object: object storage non disponibile (%s); salvo in GridFS: %s", e, path)
        _gridfs_put(path, data, content_type)
        return {"path": path, "storage": "gridfs"}


def get_object(path: str) -> tuple[bytes, str]:
    """Legge un oggetto. Prova Emergent object storage, altrimenti GridFS."""
    try:
        got = _emergent_get(path)
        if got is not None:
            return got
    except Exception as e:  # noqa: BLE001
        logger.warning("get_object: object storage non disponibile (%s); leggo da GridFS: %s", e, path)
    got = _gridfs_get(path)
    if got is not None:
        return got
    raise RuntimeError(f"Oggetto non trovato: {path}")


def delete_object(path: str) -> bool:
    ok_gridfs = _gridfs_delete(path)
    key = init_storage()
    if not key:
        return ok_gridfs
    try:
        r = requests.delete(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key}, timeout=30,
        )
        return r.status_code in (200, 204, 404) or ok_gridfs
    except Exception:  # noqa: BLE001
        return ok_gridfs


MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    "json": "application/json", "csv": "text/csv", "txt": "text/plain",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm",
    "mp3": "audio/mpeg",
}


def mime_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return MIME_TYPES.get(ext, "application/octet-stream")
