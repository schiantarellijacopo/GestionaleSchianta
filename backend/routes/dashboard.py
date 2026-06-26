"""Dashboard routes — task widget e quick-links.

Estratto da server.py. Tutti gli endpoint sono prefissati `/api/dashboard`
quando il router viene incluso nell'app principale.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from db_models import _now_iso, _uid
from auth import require_user


router = APIRouter()


class DashboardLinkBody(BaseModel):
    label: str
    url: str
    icon: Optional[str] = None
    color: Optional[str] = None
    ordine: int = 0


# ---------------------------------------------------------------------------
# Tasks (widget azionabili)
# ---------------------------------------------------------------------------
async def _conta_compleanni(today: date) -> tuple[int, int]:
    """Restituisce (oggi, prossimi_7gg)."""
    md_today = today.strftime("%m-%d")
    week_md = [(today + timedelta(days=i)).strftime("%m-%d") for i in range(0, 7)]
    n_oggi = 0
    n_sett = 0
    async for a in db.anagrafiche.find(
        {"data_nascita": {"$ne": None}}, {"_id": 0, "data_nascita": 1},
    ):
        dn = (a.get("data_nascita") or "")
        if len(dn) >= 10:
            md = dn[5:10]
            if md == md_today:
                n_oggi += 1
            if md in week_md:
                n_sett += 1
    return n_oggi, n_sett


async def _conta_documenti(today_iso: str, in_30: str) -> tuple[int, int]:
    """Restituisce (scaduti, in_scadenza_30gg)."""
    n_scaduti = 0
    n_scad = 0
    async for a in db.anagrafiche.find(
        {"documenti": {"$exists": True, "$ne": {}}},
        {"_id": 0, "documenti": 1},
    ):
        scaduto_trovato = False
        for doc in (a.get("documenti") or {}).values():
            if not isinstance(doc, dict):
                continue
            sc = doc.get("scadenza")
            if sc and sc < today_iso:
                n_scaduti += 1
                scaduto_trovato = True
                break
        if scaduto_trovato:
            continue
        for doc in (a.get("documenti") or {}).values():
            if not isinstance(doc, dict):
                continue
            sc = doc.get("scadenza")
            if sc and today_iso <= sc <= in_30:
                n_scad += 1
                break
    return n_scaduti, n_scad


def _build_task_list(*, n_comp_oggi: int, n_comp_sett: int,
                     n_doc_scaduti: int, n_doc_scad: int,
                     n_sospesi_old: int, n_pol_scad: int,
                     n_sin_old: int, n_provv: int) -> list[dict]:
    """Compone la lista dei task per la dashboard."""
    return [
        {"key": "compleanno_oggi", "label": "Compleanni di oggi",
         "icon": "Cake", "color": "rose", "count": n_comp_oggi,
         "url": "/anagrafiche?compleanno=oggi",
         "descrizione": "Clienti che compiono gli anni oggi"},
        {"key": "compleanno_settimana", "label": "Compleanni nei prossimi 7 giorni",
         "icon": "Gift", "color": "pink", "count": n_comp_sett,
         "url": "/anagrafiche?compleanno=settimana",
         "descrizione": "Da contattare per gli auguri"},
        {"key": "documenti_scaduti", "label": "Documenti di riconoscimento scaduti",
         "icon": "FileWarning", "color": "red", "count": n_doc_scaduti,
         "url": "/anagrafiche?doc=scaduti",
         "descrizione": "CI / patente / passaporto da rinnovare"},
        {"key": "documenti_scadenza", "label": "Documenti in scadenza (30gg)",
         "icon": "FileClock", "color": "amber", "count": n_doc_scad,
         "url": "/anagrafiche?doc=in_scadenza",
         "descrizione": "Da aggiornare nei prossimi 30 giorni"},
        {"key": "titoli_sospesi_old", "label": "Titoli sospesi da oltre 5 giorni",
         "icon": "AlertTriangle", "color": "orange", "count": n_sospesi_old,
         "url": "/sospesi?gg_min=5",
         "descrizione": "Anticipati dall'agenzia, da incassare"},
        {"key": "polizze_in_scadenza_30", "label": "Polizze in scadenza (30gg)",
         "icon": "CalendarClock", "color": "blue", "count": n_pol_scad,
         "url": "/avvisi", "descrizione": "Prossime al rinnovo"},
        {"key": "sinistri_aperti_old", "label": "Sinistri aperti da oltre 30 giorni",
         "icon": "AlertOctagon", "color": "red", "count": n_sin_old,
         "url": "/sinistri?stato=aperto&gg_min=30",
         "descrizione": "Da sollecitare alla compagnia"},
        {"key": "provvigioni_da_pagare", "label": "Provvigioni da liquidare",
         "icon": "Wallet", "color": "emerald", "count": n_provv,
         "url": "/provvigioni", "descrizione": "Collaboratori in attesa"},
    ]


@router.get("/dashboard/tasks")
async def dashboard_tasks(user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))) -> list[dict]:
    """Task azionabili sulla dashboard."""
    today = date.today()
    today_iso = today.isoformat()
    in_30 = (today + timedelta(days=30)).isoformat()
    days_5_ago = (today - timedelta(days=5)).isoformat()
    cutoff_30 = (today - timedelta(days=30)).isoformat()

    n_comp_oggi, n_comp_sett = await _conta_compleanni(today)
    n_doc_scaduti, n_doc_scad = await _conta_documenti(today_iso, in_30)

    n_sospesi_old = await db.titoli.count_documents({
        "titolo_coperto": True,
        "stato": {"$in": ["da_incassare", "insoluto"]},
        "data_copertura": {"$lt": days_5_ago},
    })
    n_sin_old = await db.sinistri.count_documents({
        "stato": {"$in": ["aperto", "in_lavorazione", "denunciato"]},
        "data_sinistro": {"$lt": cutoff_30},
    })
    n_pol_scad = await db.polizze.count_documents({
        "stato": {"$in": ["attiva", "in_emissione"]},
        "scadenza": {"$gte": today_iso, "$lte": in_30},
    })
    n_provv = await db.titoli.count_documents({
        "stato": {"$in": ["incassato"]},
        "provvigione_pagata": {"$ne": True},
        "collaboratore_id": {"$ne": None},
    })

    return _build_task_list(
        n_comp_oggi=n_comp_oggi, n_comp_sett=n_comp_sett,
        n_doc_scaduti=n_doc_scaduti, n_doc_scad=n_doc_scad,
        n_sospesi_old=n_sospesi_old, n_pol_scad=n_pol_scad,
        n_sin_old=n_sin_old, n_provv=n_provv,
    )


# ---------------------------------------------------------------------------
# Quick links
# ---------------------------------------------------------------------------
def _normalize_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


@router.get("/dashboard/links")
async def list_dashboard_links(user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))) -> list[dict]:
    """Link rapidi mostrati sulla dashboard."""
    return await db.dashboard_links.find({}, {"_id": 0}).sort(
        [("ordine", 1), ("created_at", -1)],
    ).to_list(200)


@router.post("/dashboard/links", status_code=201)
async def create_dashboard_link(
    body: DashboardLinkBody,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    if not body.label or not body.url:
        raise HTTPException(400, "Label e URL obbligatori")
    item = {
        "id": _uid(),
        "label": body.label.strip(),
        "url": _normalize_url(body.url),
        "icon": body.icon,
        "color": body.color,
        "ordine": body.ordine or 0,
        "created_at": _now_iso(),
        "created_by": user.get("id"),
    }
    await db.dashboard_links.insert_one(item)
    item.pop("_id", None)
    return item


@router.put("/dashboard/links/{lid}")
async def update_dashboard_link(
    lid: str, body: DashboardLinkBody,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    existing = await db.dashboard_links.find_one({"id": lid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Link non trovato")
    upd = {
        "label": body.label.strip(),
        "url": _normalize_url(body.url),
        "icon": body.icon,
        "color": body.color,
        "ordine": body.ordine or 0,
        "updated_at": _now_iso(),
    }
    await db.dashboard_links.update_one({"id": lid}, {"$set": upd})
    return {**existing, **upd}


@router.delete("/dashboard/links/{lid}")
async def delete_dashboard_link(
    lid: str,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    res = await db.dashboard_links.delete_one({"id": lid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Link non trovato")
    return {"ok": True}
