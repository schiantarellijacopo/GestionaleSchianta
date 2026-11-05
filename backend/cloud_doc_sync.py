"""Archiviazione documenti sul cloud dell'agenzia (cloud-only con fallback).

Modello scelto dall'utente:
- I documenti vivono SOLO sul cloud collegato al tenant (Google Drive oggi; S3/OneDrive
  in futuro con le stesse firme). Il CRM non conserva una copia fisica: mostra e scarica
  il file dal cloud tramite l'ID del documento.
- Se al momento dell'upload NON c'è un cloud collegato, il file resta temporaneamente nel
  CRM (storage interno) con `pending_sync=True` e verrà spostato sul cloud appena l'agenzia
  collega un account (vedi `sync_pending_for_tenant`).

Struttura cartelle sul cloud:

    Assicura CRM/
    ├── Anagrafiche/{NOME CLIENTE}/{Tipo documento}/<file>
    ├── Polizze/{N° POLIZZA}/{Tipo documento}/<file>
    └── Sinistri/{N° SINISTRO}/{Tipo documento}/<file>

Ogni file sul cloud ha l'ID del documento nel nome: "Carta d'identità [ab12cd].pdf".

Sicurezza: il tenant è SEMPRE passato dal chiamante (ricavato dal JWT), mai da input client;
si salva solo sul cloud di quel tenant (isolamento multi-tenant).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

from database import db

logger = logging.getLogger("cloud_doc_sync")

# Etichette leggibili per i tipi di documento della card anagrafica.
DOC_LABELS = {
    "carta_identita": "Carta d'identità",
    "patente": "Patente di guida",
    "passaporto": "Passaporto",
    "codice_fiscale_doc": "Tessera codice fiscale",
    "tessera_sanitaria": "Tessera sanitaria",
    "visura_camerale": "Visura camerale",
    "estratto_contributivo": "Estratto contributivo",
    "privacy_firmata": "Privacy firmata",
    "mandato_sdd": "Mandato SDD",
    "autocertificazione_stato_famiglia": "Autocertificazione stato famiglia",
    "altro": "Altro documento",
}

# entita_tipo → (categoria cartella sezione, chiave di contesto)
_ENTITY_CATEGORY = {
    "anagrafica": ("anagrafica_cliente", "cliente"),
    "polizza": ("polizza_cliente", "polizza"),
    "sinistro": ("sinistro_specifico", "sinistro"),
}

PROVIDER_PRIORITY = ("google_drive", "onedrive")


def doc_label(tipo: str) -> str:
    """Etichetta leggibile per un tipo di card (fallback: il tipo stesso)."""
    return DOC_LABELS.get(tipo, (tipo or "documento").replace("_", " ").capitalize())


# Etichette sottocartella per le categorie degli allegati (polizze/sinistri/…).
ALLEGATO_LABELS = {
    "polizza": "Polizza",
    "condizioni": "Condizioni di polizza",
    "privacy_compagnia": "Privacy compagnia",
    "libretto": "Libretto di circolazione",
    "libretto_circolazione": "Libretto di circolazione",
    "quietanza": "Quietanze",
    "foto": "Foto",
    "ricevuta": "Ricevute",
    "denuncia": "Denuncia sinistro",
    "perizia": "Perizia",
    "altro": "Altri documenti",
}


def alleg_label(categoria: Optional[str]) -> str:
    """Etichetta sottocartella per un allegato in base alla sua categoria."""
    if not categoria:
        return "Documenti"
    return ALLEGATO_LABELS.get(categoria, categoria.replace("_", " ").capitalize())


async def connected_providers(tenant_id: str) -> list[str]:
    """Provider cloud collegati per questo tenant (in ordine di priorità)."""
    out: list[str] = []
    for prov in PROVIDER_PRIORITY:
        conn = await db.cloud_connections.find_one(
            {"tenant_id": tenant_id, "provider": prov}, {"_id": 0, "provider": 1}
        )
        if conn:
            out.append(prov)
    return out


async def resolve_entity_name(entita_tipo: str, entita_id: str) -> Optional[str]:
    """Nome usato come cartella sul cloud per l'entità."""
    if entita_tipo == "anagrafica":
        a = await db.anagrafiche.find_one(
            {"id": entita_id}, {"_id": 0, "ragione_sociale": 1, "cognome": 1, "nome": 1}
        )
        if not a:
            return None
        nome = (a.get("ragione_sociale") or "").strip()
        if not nome:
            nome = f"{a.get('cognome', '')} {a.get('nome', '')}".strip()
        return nome or None
    if entita_tipo == "polizza":
        p = await db.polizze.find_one({"id": entita_id}, {"_id": 0, "numero_polizza": 1})
        return (p or {}).get("numero_polizza") if p else None
    if entita_tipo == "sinistro":
        s = await db.sinistri.find_one({"id": entita_id}, {"_id": 0, "numero_sinistro": 1})
        return (s or {}).get("numero_sinistro") if s else None
    return None


def _ext(filename: str) -> str:
    return (filename or "doc.bin").rsplit(".", 1)[-1].lower() if "." in (filename or "") else "bin"


async def _token_for(tenant_id: str, provider: str):
    from routes.cloud_storage import _fresh_access_token
    conn = await db.cloud_connections.find_one({"tenant_id": tenant_id, "provider": provider})
    if not conn:
        return None
    return await _fresh_access_token(provider, conn)


async def _put_file(provider: str, token: str, folder_id: str, name: str,
                    data: bytes, mime: str) -> dict:
    """Carica un nuovo file nella cartella. Ritorna {id, name, link}."""
    if provider == "google_drive":
        metadata = {"name": name, "mimeType": mime, "parents": [folder_id]}
        async with httpx.AsyncClient(timeout=120) as x:
            r = await x.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink",
                headers={"Authorization": f"Bearer {token}"},
                files={
                    "metadata": ("metadata", json.dumps(metadata), "application/json"),
                    "file": (name, data, mime),
                },
            )
        r.raise_for_status()
        info = r.json()
        fid = info.get("id")
        return {"id": fid, "name": name,
                "link": info.get("webViewLink") or f"https://drive.google.com/file/d/{fid}/view"}
    # OneDrive (PUT by path)
    url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}:/{name}:/content"
    async with httpx.AsyncClient(timeout=120) as x:
        r = await x.put(url, headers={"Authorization": f"Bearer {token}",
                                      "Content-Type": mime}, content=data)
    r.raise_for_status()
    info = r.json()
    return {"id": info.get("id"), "name": name, "link": info.get("webUrl")}


async def mirror_document(
    *, tenant_id: str, entita_tipo: str, entita_id: str,
    doc_label_text: str, doc_id: str, data: bytes, mime: str, filename: str,
    replace_file_id: Optional[str] = None, provider: Optional[str] = None,
) -> Optional[dict]:
    """Carica un documento sul cloud nella sottocartella del tipo. Best-effort.

    Ritorna {provider, file_id, name, link, path, doc_id, synced_at} oppure None se
    nessun cloud è collegato / in caso di errore (non solleva mai).
    """
    try:
        from routes.cloud_storage import (
            _ensure_folder_path, _resolve_category_path, _sanitize_folder_name, _now,
        )

        cat_info = _ENTITY_CATEGORY.get(entita_tipo)
        if not cat_info:
            return None
        category, ctx_key = cat_info

        entity_name = await resolve_entity_name(entita_tipo, entita_id)
        if not entity_name:
            return None

        providers = [provider] if provider else await connected_providers(tenant_id)
        if not providers:
            return None
        prov = providers[0]
        token = await _token_for(tenant_id, prov)
        if not token:
            return None

        label = _sanitize_folder_name(doc_label_text or filename or "documento")
        # Cartella: Sezione/{entità}/{Tipo documento}
        segments = await _resolve_category_path(category, {ctx_key: entity_name})
        segments = segments + [label]
        folder_id = await _ensure_folder_path(prov, token, segments, tenant_id)
        if not folder_id:
            return None

        # Sostituzione: elimina la versione precedente (stesso documento della card).
        if replace_file_id:
            await delete_cloud_file(tenant_id, prov, replace_file_id)

        ext = _ext(filename)
        name = f"{label} [{doc_id}].{ext}"
        res = await _put_file(prov, token, folder_id, name, data, mime)
        out = {
            "provider": prov,
            "file_id": res.get("id"),
            "name": res.get("name"),
            "link": res.get("link"),
            "path": "/".join(segments),
            "doc_id": doc_id,
            "synced_at": _now().isoformat(),
        }
        logger.info("Cloud OK: %s → %s/%s (%s)", doc_id, "/".join(segments), name, prov)
        return out
    except Exception as e:
        logger.warning("Upload cloud fallito (entita=%s id=%s): %s",
                       entita_tipo, entita_id, str(e)[:200])
        return None


async def delete_cloud_file(tenant_id: str, provider: str, file_id: str) -> bool:
    """Elimina un file dal cloud. Best-effort."""
    if not file_id:
        return False
    try:
        token = await _token_for(tenant_id, provider)
        if not token:
            return False
        if provider == "google_drive":
            async with httpx.AsyncClient(timeout=30) as x:
                r = await x.delete(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            return r.status_code in (200, 204, 404)
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.delete(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        return r.status_code in (200, 204, 404)
    except Exception as e:
        logger.warning("Delete cloud file %s fallito: %s", file_id, str(e)[:160])
        return False


async def download_cloud_file(tenant_id: str, provider: str,
                              file_id: str) -> Optional[tuple[bytes, str]]:
    """Scarica il contenuto di un file dal cloud. Ritorna (bytes, mime) o None."""
    try:
        token = await _token_for(tenant_id, provider)
        if not token:
            return None
        if provider == "google_drive":
            async with httpx.AsyncClient(timeout=120) as x:
                r = await x.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                    headers={"Authorization": f"Bearer {token}"},
                )
            r.raise_for_status()
            mime = r.headers.get("Content-Type", "application/octet-stream")
            return (r.content, mime)
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as x:
            r = await x.get(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content",
                headers={"Authorization": f"Bearer {token}"},
            )
        r.raise_for_status()
        mime = r.headers.get("Content-Type", "application/octet-stream")
        return (r.content, mime)
    except Exception as e:
        logger.warning("Download cloud file %s fallito: %s", file_id, str(e)[:160])
        return None


async def sync_pending_for_tenant(tenant_id: str, limit: int = 500) -> dict:
    """Sposta sul cloud i documenti rimasti nel CRM in attesa (pending_sync).

    Chiamata quando l'agenzia collega un cloud. Best-effort: ogni documento che
    riesce a salire viene rimosso dallo storage interno.
    """
    import storage as obj_storage

    providers = await connected_providers(tenant_id)
    if not providers:
        return {"ok": False, "reason": "nessun cloud collegato"}

    moved = 0
    failed = 0

    # 1) Allegati generici (polizze/sinistri/anagrafica). Lo scope per-agenzia è
    # applicato automaticamente dal wrapper DB in base all'utente corrente.
    cur = db.allegati.find(
        {"pending_sync": True, "is_deleted": {"$ne": True}},
        {"_id": 0},
    ).limit(limit)
    async for al in cur:
        try:
            data, mime = obj_storage.get_object(al["storage_path"])
        except Exception:
            failed += 1
            continue
        sync = await mirror_document(
            tenant_id=tenant_id, entita_tipo=al["entita_tipo"], entita_id=al["entita_id"],
            doc_label_text=al.get("categoria") or al.get("nome_file") or "Documento",
            doc_id=al["id"], data=data, mime=mime, filename=al.get("nome_file") or "doc.bin",
        )
        if sync:
            await db.allegati.update_one(
                {"id": al["id"]},
                {"$set": {"storage_provider": sync["provider"], "cloud_sync": sync,
                          "pending_sync": False},
                 "$unset": {"storage_path": ""}},
            )
            try:
                obj_storage.delete_object(al["storage_path"])
            except Exception:
                pass
            moved += 1
        else:
            failed += 1

    # 2) Documenti delle card anagrafica (documenti.{tipo})
    cur2 = db.anagrafiche.find(
        {"documenti": {"$exists": True}},
        {"_id": 0, "id": 1, "documenti": 1},
    ).limit(limit)
    async for ana in cur2:
        docs = ana.get("documenti") or {}
        for tipo, entry in list(docs.items()):
            if not isinstance(entry, dict) or not entry.get("pending_sync"):
                continue
            sp = entry.get("storage_path")
            if not sp:
                continue
            try:
                data, mime = obj_storage.get_object(sp)
            except Exception:
                failed += 1
                continue
            sync = await mirror_document(
                tenant_id=tenant_id, entita_tipo="anagrafica", entita_id=ana["id"],
                doc_label_text=doc_label(tipo), doc_id=entry.get("doc_id") or al_id_fallback(),
                data=data, mime=mime, filename=entry.get("nome_file") or f"{tipo}.bin",
            )
            if sync:
                await db.anagrafiche.update_one(
                    {"id": ana["id"]},
                    {"$set": {f"documenti.{tipo}.cloud_sync": sync,
                              f"documenti.{tipo}.storage_provider": sync["provider"],
                              f"documenti.{tipo}.pending_sync": False},
                     "$unset": {f"documenti.{tipo}.storage_path": "",
                                f"documenti.{tipo}.url": ""}},
                )
                try:
                    obj_storage.delete_object(sp)
                except Exception:
                    pass
                moved += 1
            else:
                failed += 1

    return {"ok": True, "moved": moved, "failed": failed}


def al_id_fallback() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


async def save_anag_card_document(
    *, tenant_id: str, aid: str, tipo: str, data: bytes, mime: str,
    filename: str, scadenza: Optional[str] = None, user_id: Optional[str] = None,
) -> dict:
    """Costruisce il doc_entry di una card anagrafica col modello cloud-only + fallback.

    NON scrive sul DB: ritorna il dict `doc_entry` pronto da salvare in
    `anagrafiche.documenti.{tipo}`. Usato dagli endpoint OCR (CI/patente/passaporto).
    """
    import uuid
    import storage as obj_storage
    from routes.cloud_storage import _now

    doc_id = uuid.uuid4().hex
    ext = (filename or "doc.bin").rsplit(".", 1)[-1].lower() or "bin"

    # Entry precedente (per sostituire il file sul cloud alla ri-upload)
    prev = await db.anagrafiche.find_one({"id": aid}, {"_id": 0, f"documenti.{tipo}": 1})
    prev_cloud = (((prev or {}).get("documenti") or {}).get(tipo) or {}).get("cloud_sync") or {}

    doc_entry: dict = {
        "doc_id": doc_id,
        "nome_file": filename, "mime": mime,
        "size_kb": round(len(data) / 1024, 1),
        "data_caricamento": _now().isoformat(),
        "scadenza": scadenza,
        "caricato_da": user_id,
    }

    sync = None
    providers = await connected_providers(tenant_id)
    if providers:
        sync = await mirror_document(
            tenant_id=tenant_id, entita_tipo="anagrafica", entita_id=aid,
            doc_label_text=doc_label(tipo), doc_id=doc_id,
            data=data, mime=mime, filename=filename or f"{tipo}.{ext}",
            replace_file_id=prev_cloud.get("file_id"),
        )

    if sync:
        doc_entry["cloud_sync"] = sync
        doc_entry["storage_provider"] = sync["provider"]
        doc_entry["pending_sync"] = False
        doc_entry["url"] = f"/api/anagrafiche/{aid}/documenti/{tipo}/download"
    else:
        import os as _os
        path = f"{_os.environ.get('APP_NAME', 'assicura')}/anagrafiche/{aid}/{tipo}_{doc_id}.{ext}"
        result = obj_storage.put_object(path, data, mime)
        doc_entry["url"] = f"/api/storage/{result['path']}"
        doc_entry["storage_path"] = result["path"]
        doc_entry["storage_provider"] = "emergent"
        doc_entry["pending_sync"] = True
        if prev_cloud.get("file_id"):
            await delete_cloud_file(tenant_id, prev_cloud.get("provider", "google_drive"),
                                    prev_cloud["file_id"])
    return doc_entry
