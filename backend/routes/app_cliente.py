"""App Cliente — configurazione del Portale Cliente dal CRM.

Permette all'agenzia di modificare i dati mostrati nell'app del cliente:
orari di apertura, team, numeri assistenza per compagnia, link utili,
slogan e contatti. Il video motivazionale usa gli endpoint
/librerie/azienda/video-analisi già esistenti.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import current_user, require_user
from database import db
from db_models import _now_iso, _uid

router = APIRouter(prefix="/app-cliente")


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
    if "team" in body:
        upd["portale_team"] = [
            {k: (r.get(k) or "").strip() for k in ("nome", "ruolo", "telefono", "email")}
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
