"""Emergent object storage helpers."""
from __future__ import annotations
import os
import logging
import requests

logger = logging.getLogger(__name__)

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = os.environ.get("APP_NAME", "assicura")

_storage_key: str | None = None


def init_storage() -> str | None:
    """Initialize storage session once. Returns storage_key or None if failure."""
    global _storage_key
    if _storage_key:
        return _storage_key
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        logger.warning("EMERGENT_LLM_KEY not set; storage disabled")
        return None
    try:
        r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": key}, timeout=20)
        r.raise_for_status()
        _storage_key = r.json()["storage_key"]
        logger.info("Storage initialized OK")
        return _storage_key
    except Exception as e:
        logger.error("Storage init failed: %s", e)
        return None


def _reset():
    global _storage_key
    _storage_key = None


def put_object(path: str, data: bytes, content_type: str) -> dict:
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
        r = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120,
        )
    r.raise_for_status()
    return r.json()


def get_object(path: str) -> tuple[bytes, str]:
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
        r = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key}, timeout=60,
        )
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")


def delete_object(path: str) -> bool:
    key = init_storage()
    if not key:
        return False
    try:
        r = requests.delete(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key}, timeout=30,
        )
        return r.status_code in (200, 204, 404)
    except Exception:
        return False



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
