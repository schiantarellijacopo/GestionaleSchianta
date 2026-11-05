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
    "trattativa": ("trattativa_specifica", "cliente"),
    "titolo": ("titolo_specifico", "polizza"),
    "disdetta": ("disdetta_specifica", "polizza"),
    "applicazione_matricola": ("polizza_cliente", "polizza"),
}

# Qualunque entità non mappata finisce comunque sul Drive, sotto
# "Archivio/Altri documenti/{entità}": il Drive è l'archivio COMPLETO del CRM,
# nessun documento viene mai saltato.
_DEFAULT_ENTITY_CATEGORY = ("altro_specifico", "cliente")

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
    file_label: Optional[str] = None,
) -> Optional[dict]:
    """Carica un documento sul cloud nella sottocartella del tipo. Best-effort.

    `doc_label_text` nomina la SOTTOCARTELLA (tipo card); `file_label`, se passato,
    nomina il FILE (per varianti nella stessa cartella, es. retro CI). Default: usa
    `doc_label_text` anche per il file.

    Ritorna {provider, file_id, name, link, path, doc_id, synced_at} oppure None se
    nessun cloud è collegato / in caso di errore (non solleva mai).
    """
    try:
        from routes.cloud_storage import (
            _ensure_folder_path, _resolve_category_path, _sanitize_folder_name, _now,
        )

        cat_info = _ENTITY_CATEGORY.get(entita_tipo)
        if not cat_info:
            cat_info = _DEFAULT_ENTITY_CATEGORY
            logger.info("Mirror: entità '%s' non mappata → archivio in 'Altri documenti'", entita_tipo)
        category, ctx_key = cat_info

        entity_name = await resolve_entity_name(entita_tipo, entita_id)
        if not entity_name:
            # Fallback: non perdiamo mai il documento. Usiamo l'id entità o una
            # cartella generica così il file sale comunque sul Drive.
            entity_name = entita_id or "Senza riferimento"
            logger.info("Mirror fallback: nome entità assente, uso '%s' (entita=%s)",
                        entity_name, entita_tipo)

        providers = [provider] if provider else await connected_providers(tenant_id)
        if not providers:
            logger.warning("Mirror skip: nessun cloud per tenant=%s", tenant_id)
            return None
        prov = providers[0]
        token = await _token_for(tenant_id, prov)
        if not token:
            logger.warning("Mirror skip: token assente tenant=%s prov=%s", tenant_id, prov)
            return None

        label = _sanitize_folder_name(doc_label_text or filename or "documento")
        file_lbl = _sanitize_folder_name(file_label) if file_label else label
        # Cartella: Sezione/{entità}/{Tipo documento} (dal label cartella)
        segments = await _resolve_category_path(category, {ctx_key: entity_name})
        segments = segments + [label]
        folder_id = await _ensure_folder_path(prov, token, segments, tenant_id)
        if not folder_id:
            return None

        # Sostituzione: NON eliminiamo subito la versione precedente. Prima carichiamo
        # la nuova, poi (solo se l'upload riesce) eliminiamo la vecchia → niente perdita dati.
        ext = _ext(filename)
        name = f"{file_lbl} [{doc_id}].{ext}"
        res = await _put_file(prov, token, folder_id, name, data, mime)
        if replace_file_id and res.get("id") and res["id"] != replace_file_id:
            await delete_cloud_file(tenant_id, prov, replace_file_id)
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


async def sync_pending_for_tenant(tenant_id: str, limit: int = 500,
                                  include_all: bool = False) -> dict:
    """Sposta sul cloud i documenti rimasti nel CRM in attesa.

    - default: solo i documenti con `pending_sync=True` (caricati dopo il collegamento
      ma non ancora saliti, o in attesa perché il cloud non era collegato).
    - include_all=True: BACKFILL completo — include anche i documenti "storici" caricati
      PRIMA del collegamento del cloud (storage interno, senza `cloud_sync`), anche se
      non hanno il flag `pending_sync`.

    Best-effort: ogni documento che riesce a salire viene rimosso dallo storage interno.
    Ritorna anche `remaining` (quanti ne restano oltre il limite di questa passata).
    """
    import storage as obj_storage

    providers = await connected_providers(tenant_id)
    if not providers:
        return {"ok": False, "reason": "nessun cloud collegato"}

    moved = 0
    failed = 0

    # Il Drive è l'archivio COMPLETO del CRM: includiamo TUTTI i tipi di entità
    # (polizze, anagrafiche, sinistri, trattative, titoli, disdette, firme, ...).
    if include_all:
        al_filter = {
            "is_deleted": {"$ne": True},
            "cloud_sync.file_id": {"$exists": False},
            "storage_path": {"$exists": True, "$nin": ["", None]},
        }
    else:
        al_filter = {"pending_sync": True, "is_deleted": {"$ne": True}}

    total_al = await db.allegati.count_documents(al_filter)

    # 1) Allegati generici (polizze/sinistri/anagrafica). Lo scope per-agenzia è
    # applicato automaticamente dal wrapper DB in base all'utente corrente.
    cur = db.allegati.find(al_filter, {"_id": 0}).limit(limit)
    async for al in cur:
        if not al.get("storage_path"):
            failed += 1
            continue
        try:
            data, mime = obj_storage.get_object(al["storage_path"])
        except Exception as e:
            logger.warning("Backfill: file interno mancante (allegato id=%s, path=%s): %s",
                           al.get("id"), al.get("storage_path"), str(e)[:160])
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
            if not isinstance(entry, dict):
                continue
            has_cloud = bool((entry.get("cloud_sync") or {}).get("file_id"))
            eligible = entry.get("pending_sync") or (include_all and not has_cloud)
            if not eligible or has_cloud:
                continue
            sp = entry.get("storage_path")
            if not sp:
                continue
            try:
                data, mime = obj_storage.get_object(sp)
            except Exception as e:
                logger.warning("Backfill: file card mancante (anag=%s tipo=%s path=%s): %s",
                               ana.get("id"), tipo, sp, str(e)[:160])
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

    remaining = max(0, total_al - min(total_al, limit))
    return {"ok": True, "moved": moved, "failed": failed, "remaining": remaining}


async def sync_status_for_tenant(tenant_id: str) -> dict:
    """Riepilogo sincronizzazione: quanti documenti sono sul cloud e quanti restano
    nello storage interno (da sincronizzare). Conta allegati + documenti delle card
    anagrafica. Lo scope per-agenzia è applicato dal wrapper DB in base all'utente."""
    synced = await db.allegati.count_documents({
        "is_deleted": {"$ne": True},
        "cloud_sync.file_id": {"$exists": True},
    })
    pending = await db.allegati.count_documents({
        "is_deleted": {"$ne": True},
        "cloud_sync.file_id": {"$exists": False},
        "storage_path": {"$exists": True, "$nin": ["", None]},
    })

    # Documenti embedded nelle card anagrafica
    async for ana in db.anagrafiche.find(
        {"documenti": {"$exists": True}}, {"_id": 0, "documenti": 1}
    ):
        for entry in (ana.get("documenti") or {}).values():
            items = entry if isinstance(entry, list) else [entry]
            for e in items:
                if not isinstance(e, dict):
                    continue
                if (e.get("cloud_sync") or {}).get("file_id"):
                    synced += 1
                elif e.get("storage_path"):
                    pending += 1

    total = synced + pending
    return {"ok": True, "synced": synced, "pending": pending, "total": total}


# Evita backfill automatici concorrenti sullo stesso tenant
_auto_backfill_running: set[str] = set()


async def auto_backfill_tenant(tenant_id: str, max_batches: int = 80) -> None:
    """Backfill automatico in BACKGROUND dei documenti storici dopo il collegamento
    del cloud, senza che l'utente prema alcun pulsante.

    IMPORTANTE: il wrapper DB filtra per tenant in base al ContextVar dell'utente
    corrente; in un task di background non c'è utente → impostiamo un utente
    sintetico con `agenzia_tenant_id=tenant_id` per garantire l'isolamento tenant
    (senza questo, le query colpirebbero TUTTI i tenant)."""
    import asyncio
    from database import set_current_user, reset_current_user

    if tenant_id in _auto_backfill_running:
        logger.info("Auto-backfill già in corso per tenant=%s, skip", tenant_id)
        return
    _auto_backfill_running.add(tenant_id)
    synthetic_user = {
        "id": f"__auto_backfill__{tenant_id}",
        "agenzia_tenant_id": tenant_id,
        "role": "admin",
        "is_super_admin": False,
    }
    ctx_token = set_current_user(synthetic_user)
    try:
        providers = await connected_providers(tenant_id)
        if not providers:
            return
        total_moved = 0
        for _ in range(max_batches):
            res = await sync_pending_for_tenant(tenant_id, include_all=True)
            if not res.get("ok"):
                break
            total_moved += res.get("moved", 0)
            if (res.get("remaining") or 0) <= 0:
                break
            await asyncio.sleep(0.3)
        logger.info("Auto-backfill tenant=%s completato: %d documenti caricati",
                    tenant_id, total_moved)
    except Exception as e:
        logger.warning("Auto-backfill tenant=%s errore: %s", tenant_id, str(e)[:200])
    finally:
        reset_current_user(ctx_token)
        _auto_backfill_running.discard(tenant_id)




async def read_allegato_bytes(al: dict) -> tuple[bytes, str]:
    """Legge i byte di un allegato: dal cloud se cloud-only, altrimenti dallo storage interno.

    Usato da portale cliente, firma elettronica e altri punti di download.
    """
    import storage as obj_storage
    cloud = (al or {}).get("cloud_sync") or {}
    if cloud.get("file_id") and not al.get("pending_sync"):
        tenant_id = al.get("agenzia_tenant_id") or al.get("tenant_id") or "default"
        res = await download_cloud_file(tenant_id, cloud.get("provider", "google_drive"),
                                        cloud["file_id"])
        if res:
            return res
    return obj_storage.get_object(al["storage_path"])


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
