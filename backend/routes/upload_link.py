"""Link pubblico per caricamento documenti dal cliente.

Quando un alert (o un operatore) chiede al cliente un documento mancante/scaduto
(es. libretto veicolo, CID, quietanza, carta d'identità), si genera un LINK sicuro
con token legato a una SPECIFICA CARD di una specifica entità (anagrafica, polizza,
sinistro, titolo). Il cliente apre il link, carica uno o più file SENZA login e i
documenti finiscono DIRETTAMENTE nella card corretta (e spariscono dai "documenti
mancanti" della dashboard).

- Endpoint autenticati: creazione/lista/eliminazione link.
- Endpoint PUBBLICI (no auth): info link + upload. Il tenant viene risolto dal
  token (collection `upload_links` GLOBALE via raw_db) e il file viene scritto
  impostando il ContextVar sul tenant del link.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from database import db, raw_db, set_current_user, reset_current_user
from auth import require_user
from db_models import _now_iso, _uid, Allegato
from tenant import user_tenant_id, TENANT_PRINCIPALE_ID
from routes.documenti_inbox import ANAG_CARD_KEYS, _default_visibile
import storage as obj_storage

router = APIRouter(tags=["upload-link"])

_ROLES = ("admin", "collaboratore", "dipendente")
_MAX = 20 * 1024 * 1024
_ENTITA_VALIDE = ("anagrafica", "polizza", "sinistro", "titolo")


def _public_base() -> str:
    return (os.environ.get("BACKEND_PUBLIC_URL") or "").rstrip("/")


def _full_url(token: str) -> str:
    base = _public_base()
    return f"{base}/carica/{token}" if base else f"/carica/{token}"


async def _risolvi_entita(entita_tipo: str, entita_id: str) -> dict:
    """Valida l'entità e ne ricava anagrafica di riferimento + nome descrittivo."""
    if entita_tipo == "anagrafica":
        ana = await db.anagrafiche.find_one({"id": entita_id}, {"_id": 0, "id": 1, "ragione_sociale": 1})
        if not ana:
            raise HTTPException(404, "Anagrafica non trovata")
        return {"anagrafica_id": entita_id, "nome": ana.get("ragione_sociale")}
    if entita_tipo == "polizza":
        pol = await db.polizze.find_one({"id": entita_id}, {"_id": 0, "id": 1, "contraente_id": 1, "numero_polizza": 1})
        if not pol:
            raise HTTPException(404, "Polizza non trovata")
        return {"anagrafica_id": pol.get("contraente_id"), "nome": f"Polizza {pol.get('numero_polizza') or ''}".strip()}
    if entita_tipo == "sinistro":
        sin = await db.sinistri.find_one({"id": entita_id}, {"_id": 0, "id": 1, "contraente_id": 1, "numero_sinistro": 1})
        if not sin:
            raise HTTPException(404, "Sinistro non trovato")
        return {"anagrafica_id": sin.get("contraente_id"), "nome": f"Sinistro {sin.get('numero_sinistro') or ''}".strip()}
    if entita_tipo == "titolo":
        tit = await db.titoli.find_one({"id": entita_id}, {"_id": 0, "id": 1, "contraente_id": 1, "polizza_id": 1, "numero_polizza": 1})
        if not tit:
            raise HTTPException(404, "Titolo non trovato")
        aid = tit.get("contraente_id")
        if not aid and tit.get("polizza_id"):
            pol = await db.polizze.find_one({"id": tit["polizza_id"]}, {"_id": 0, "contraente_id": 1})
            aid = (pol or {}).get("contraente_id")
        return {"anagrafica_id": aid, "nome": f"Titolo polizza {tit.get('numero_polizza') or ''}".strip()}
    raise HTTPException(400, "Tipo entità non valido")


class CreateLinkBody(BaseModel):
    # Nuovo modello generico: entità + card. `anagrafica_id` resta per retro-compat.
    entita_tipo: Optional[str] = None
    entita_id: Optional[str] = None
    categoria: Optional[str] = None
    anagrafica_id: Optional[str] = None
    descrizione: str = ""
    polizza_id: Optional[str] = None
    giorni_validita: int = 30
    reminder_giorni: int = 3


@router.post("/upload-links")
async def create_upload_link(body: CreateLinkBody, user: dict = Depends(require_user(*_ROLES))) -> dict:
    entita_tipo = body.entita_tipo or ("anagrafica" if body.anagrafica_id else None)
    entita_id = body.entita_id or body.anagrafica_id
    if not entita_tipo or not entita_id:
        raise HTTPException(400, "Specificare l'entità di destinazione")
    if entita_tipo not in _ENTITA_VALIDE:
        raise HTTPException(400, "Tipo entità non valido")

    info = await _risolvi_entita(entita_tipo, entita_id)
    tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    doc = {
        "id": _uid(),
        "token": token,
        "agenzia_tenant_id": tid,
        "entita_tipo": entita_tipo,
        "entita_id": entita_id,
        "categoria": (body.categoria or None),
        # anagrafica di riferimento: per contatto/WhatsApp e per retro-compat
        "anagrafica_id": info.get("anagrafica_id") or (entita_id if entita_tipo == "anagrafica" else None),
        "anagrafica_nome": info.get("nome"),
        "polizza_id": body.polizza_id,
        "descrizione": (body.descrizione or "").strip() or "Documento richiesto",
        "created_by": user.get("id"),
        "created_at": _now_iso(),
        "expires_at": (now + timedelta(days=max(1, body.giorni_validita))).isoformat(),
        "used": False,
        "uploads": [],
        "reminder_giorni": max(0, body.reminder_giorni),
        "reminder_count": 0,
        "last_reminder_at": None,
    }
    await raw_db.upload_links.insert_one(doc.copy())
    return {"token": token, "url": _full_url(token), "descrizione": doc["descrizione"], "expires_at": doc["expires_at"]}


@router.get("/upload-links")
async def list_upload_links(
    anagrafica_id: Optional[str] = None,
    entita_tipo: Optional[str] = None,
    entita_id: Optional[str] = None,
    categoria: Optional[str] = None,
    user: dict = Depends(require_user(*_ROLES)),
) -> list[dict]:
    tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
    flt: dict = {"agenzia_tenant_id": tid}
    if entita_tipo and entita_id:
        flt["entita_tipo"] = entita_tipo
        flt["entita_id"] = entita_id
    elif anagrafica_id:
        # retro-compat: tutti i link legati a questa anagrafica
        flt["$or"] = [
            {"anagrafica_id": anagrafica_id},
            {"entita_tipo": "anagrafica", "entita_id": anagrafica_id},
        ]
    if categoria:
        flt["categoria"] = categoria
    items = await raw_db.upload_links.find(flt, {"_id": 0}).sort("created_at", -1).to_list(100)
    for it in items:
        it["url"] = _full_url(it["token"])
    return items


@router.delete("/upload-links/{lid}")
async def delete_upload_link(lid: str, user: dict = Depends(require_user(*_ROLES))) -> dict:
    tid = user_tenant_id(user) or TENANT_PRINCIPALE_ID
    await raw_db.upload_links.delete_one({"id": lid, "agenzia_tenant_id": tid})
    return {"ok": True}


# ============================================================
# PUBBLICI — nessuna autenticazione
# ============================================================
async def _get_link(token: str) -> dict:
    link = await raw_db.upload_links.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(404, "Link non valido")
    return link


@router.get("/public/upload/{token}")
async def public_link_info(token: str) -> dict:
    link = await _get_link(token)
    scaduto = bool(link.get("expires_at") and link["expires_at"] < _now_iso())
    tenant = await raw_db.tenants.find_one({"id": link["agenzia_tenant_id"]}, {"_id": 0, "ragione_sociale": 1, "nome": 1})
    return {
        "descrizione": link.get("descrizione"),
        "cliente_nome": link.get("anagrafica_nome"),
        "agenzia_nome": (tenant or {}).get("ragione_sociale") or (tenant or {}).get("nome") or "La tua agenzia",
        "scaduto": scaduto,
        "n_caricati": len(link.get("uploads") or []),
    }


async def _archivia_nella_card(link: dict, filename: str, data: bytes, content_type: str) -> str:
    """Salva il file caricato dal cliente DIRETTAMENTE nella card corretta
    (allegato con `categoria` per polizza/sinistro/titolo, dict `documenti[card]`
    per le card a storage fisso dell'anagrafica)."""
    entita_tipo = link.get("entita_tipo") or "anagrafica"
    entita_id = link.get("entita_id") or link.get("anagrafica_id")
    categoria = link.get("categoria")
    ext = (filename or "documento.bin").rsplit(".", 1)[-1].lower() or "bin"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/{entita_tipo}/{entita_id}/richiesta_{_uid()}.{ext}"
    result = obj_storage.put_object(path, data, content_type)
    sp = result["path"]

    # Card a storage fisso dell'anagrafica → scrive nel dict `documenti[categoria]`
    if entita_tipo == "anagrafica" and categoria in ANAG_CARD_KEYS:
        entry = {
            "url": f"/api/storage/{sp}",
            "storage_path": sp,
            "nome_file": filename or f"documento.{ext}",
            "mime": content_type,
            "size_kb": round(len(data) / 1024, 1),
            "data_caricamento": _now_iso(),
            "caricato_da": "cliente",
        }
        await db.anagrafiche.update_one(
            {"id": entita_id},
            {"$set": {f"documenti.{categoria}": entry, "updated_at": _now_iso()}},
        )
        return sp

    # Altrimenti allegato con categoria = card key (visibile secondo config card)
    visibile = await _default_visibile(entita_tipo, categoria) if categoria else False
    alleg = Allegato(
        entita_tipo=entita_tipo, entita_id=entita_id,
        nome_file=filename or f"documento.{ext}",
        storage_path=sp, content_type=content_type, size=len(data),
        descrizione=f"Caricato dal cliente via link — {link.get('descrizione')}",
        categoria=categoria or "richiesta_cliente",
        visibile_cliente=visibile,
    )
    await db.allegati.insert_one(alleg.model_dump())
    return sp


@router.post("/public/upload/{token}")
async def public_upload(token: str, file: UploadFile = File(...)) -> dict:
    link = await _get_link(token)
    if link.get("expires_at") and link["expires_at"] < _now_iso():
        raise HTTPException(410, "Link scaduto: contatta la tua agenzia")
    data = await file.read()
    if len(data) > _MAX:
        raise HTTPException(413, "File troppo grande (max 20 MB)")
    if len(data) == 0:
        raise HTTPException(400, "File vuoto")
    tid = link["agenzia_tenant_id"]
    ctx = set_current_user({"id": "public-upload", "role": "admin", "agenzia_tenant_id": tid, "is_super_admin": False})
    try:
        ct = file.content_type or obj_storage.mime_for(file.filename or "")
        sp = await _archivia_nella_card(link, file.filename or "", data, ct)
    finally:
        reset_current_user(ctx)
    up = {"nome_file": file.filename, "storage_path": sp, "at": _now_iso()}
    await raw_db.upload_links.update_one(
        {"token": token}, {"$push": {"uploads": up}, "$set": {"used": True, "used_at": _now_iso()}})
    return {"ok": True, "nome_file": file.filename}
