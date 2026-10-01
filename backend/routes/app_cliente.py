"""App Cliente — configurazione del Portale Cliente dal CRM.

Permette all'agenzia di modificare i dati mostrati nell'app del cliente:
orari di apertura, team, numeri assistenza per compagnia, link utili,
slogan e contatti. Il video motivazionale usa gli endpoint
/librerie/azienda/video-analisi già esistenti.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from auth import current_user, require_user
from database import db
from db_models import _now_iso, _uid
import os
import storage as obj_storage

router = APIRouter(prefix="/app-cliente")


@router.post("/team-foto")
async def upload_team_foto(
    file: UploadFile = File(...),
    tid: str = Form(...),
    user=Depends(require_user("admin", "collaboratore")),
):
    """Carica la foto di un membro del team (max 5MB, jpg/png/webp)."""
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(400, "Foto oltre 5 MB")
    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        raise HTTPException(400, "Formato non valido: usa jpg/png/webp")
    ext = (file.filename or "foto.jpg").rsplit(".", 1)[-1].lower() or "jpg"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/team/{tid}_{_uid()[:8]}.{ext}"
    res = obj_storage.put_object(path, contents, ct)
    # aggiorna il membro se già salvato in config
    await db.azienda_config.update_one(
        {"portale_team.id": tid},
        {"$set": {"portale_team.$.foto_path": res["path"], "updated_at": _now_iso()}})
    return {"foto_path": res["path"]}


@router.get("/config")
async def get_config(user=Depends(current_user)):
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    servizi = await db.portale_servizi.find({}, {"_id": 0}).sort("ordine", 1).to_list(50)
    return {
        "contatti": {
            "ragione_sociale": az.get("ragione_sociale"),
            "telefono": az.get("telefono"),
            "email": az.get("email"),
            "indirizzo": az.get("indirizzo"),
            "comune": az.get("comune"),
            "provincia": az.get("provincia"),
            "sito_web": az.get("sito_web"),
        },
        "slogan_portale": az.get("slogan_portale"),
        "orari": az.get("portale_orari") or [],
        "sedi": az.get("portale_sedi") or [],
        "team": az.get("portale_team") or [],
        "assistenza_compagnie": az.get("assistenza_compagnie") or [],
        "servizi": servizi,
        "video": {
            "url": az.get("video_analisi_url"),
            "filename": az.get("video_analisi_filename"),
            "has_file": bool(az.get("video_analisi_storage_path")),
        },
    }


@router.put("/config")
async def update_config(body: dict, user=Depends(require_user("admin", "collaboratore"))):
    upd = {"updated_at": _now_iso()}
    if "orari" in body:
        upd["portale_orari"] = [
            {"giorni": (r.get("giorni") or "").strip(), "orario": (r.get("orario") or "").strip()}
            for r in (body.get("orari") or []) if (r.get("giorni") or r.get("orario"))
        ]
    if "sedi" in body:
        upd["portale_sedi"] = [
            {
                "id": s.get("id") or _uid(),
                "nome": (s.get("nome") or "").strip(),
                "indirizzo": (s.get("indirizzo") or "").strip(),
                "comune": (s.get("comune") or "").strip(),
                "provincia": (s.get("provincia") or "").strip(),
                "telefono": (s.get("telefono") or "").strip(),
                "orari": [
                    {"giorni": (o.get("giorni") or "").strip(), "orario": (o.get("orario") or "").strip()}
                    for o in (s.get("orari") or []) if (o.get("giorni") or o.get("orario"))
                ],
            }
            for s in (body.get("sedi") or []) if (s.get("nome") or s.get("indirizzo"))
        ]
    if "team" in body:
        upd["portale_team"] = [
            {
                "id": r.get("id") or _uid(),
                "nome": (r.get("nome") or "").strip(),
                "ruolo": (r.get("ruolo") or "").strip(),
                "descrizione": (r.get("descrizione") or "").strip(),
                "telefono": (r.get("telefono") or "").strip(),
                "email": (r.get("email") or "").strip(),
                "sede_id": (r.get("sede_id") or "").strip() or None,
                "foto_path": r.get("foto_path") or None,
            }
            for r in (body.get("team") or []) if (r.get("nome") or "").strip()
        ]
    if "assistenza_compagnie" in body:
        upd["assistenza_compagnie"] = [
            {k: (r.get(k) or "").strip() for k in ("compagnia", "numero", "note")}
            for r in (body.get("assistenza_compagnie") or []) if (r.get("compagnia") or r.get("numero"))
        ]
    if "slogan_portale" in body:
        upd["slogan_portale"] = (body.get("slogan_portale") or "").strip()
    if "contatti" in body and isinstance(body["contatti"], dict):
        for k in ("telefono", "email", "indirizzo", "comune", "provincia", "sito_web"):
            if k in body["contatti"]:
                upd[k] = (body["contatti"].get(k) or "").strip()
    await db.azienda_config.update_one({}, {"$set": upd}, upsert=True)

    if "servizi" in body:
        items = []
        for i, s in enumerate(body.get("servizi") or []):
            if not (s.get("nome") or "").strip():
                continue
            items.append({
                "id": s.get("id") or _uid(),
                "tenant_id": None,
                "nome": s["nome"].strip(),
                "descrizione": (s.get("descrizione") or "").strip(),
                "url": (s.get("url") or "").strip(),
                "categoria": s.get("categoria") or "contatto",
                "ordine": i,
            })
        await db.portale_servizi.delete_many({})
        if items:
            await db.portale_servizi.insert_many([dict(x) for x in items])

    return {"ok": True}
