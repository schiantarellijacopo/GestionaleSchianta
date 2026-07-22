"""Super Admin Audit Logs router.

Endpoints (SOLO super_admin):
  GET  /super-admin/logs                → lista log con filtri
  GET  /super-admin/logs/export/csv     → esporta in CSV
  GET  /super-admin/logs/action-types   → catalogo action_type disponibili
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from io import StringIO
import csv

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from auth import require_user
from database import raw_db
from tenant import is_super_admin
from audit_super_admin import ACTION_TYPES


router = APIRouter(prefix="/super-admin/logs", tags=["super-admin-logs"])


def _ensure_super_admin(user):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Accesso negato: solo super_admin")


@router.get("/action-types")
async def list_action_types(user=Depends(require_user("admin"))) -> list[dict]:
    _ensure_super_admin(user)
    return [{"code": k, "label": v} for k, v in ACTION_TYPES.items()]


@router.get("")
async def list_logs(
    agency_id: Optional[str] = None,
    action_type: Optional[str] = None,
    q: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = Query(200, le=1000),
    user=Depends(require_user("admin")),
) -> list[dict]:
    """Lista log con filtri. Il super_admin è l'unico che può interrogare."""
    _ensure_super_admin(user)
    filt: dict = {}
    if agency_id:
        filt["target_agency_id"] = agency_id
    if action_type:
        filt["action_type"] = action_type
    if from_date or to_date:
        filt["timestamp"] = {}
        if from_date:
            filt["timestamp"]["$gte"] = from_date
        if to_date:
            filt["timestamp"]["$lte"] = to_date + "T23:59:59"
    if q:
        filt["$or"] = [
            {"super_admin_email": {"$regex": q, "$options": "i"}},
            {"target_agency_name": {"$regex": q, "$options": "i"}},
            {"details": {"$regex": q, "$options": "i"}},
        ]
    return await raw_db.super_admin_logs.find(
        filt, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)


@router.get("/export/csv")
async def export_csv(
    agency_id: Optional[str] = None,
    action_type: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(require_user("admin")),
):
    """Esporta i log filtrati in CSV."""
    _ensure_super_admin(user)
    logs = await list_logs(
        agency_id=agency_id, action_type=action_type,
        from_date=from_date, to_date=to_date, q=None, limit=1000, user=user,
    )
    buf = StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "timestamp", "super_admin_email", "action_type", "action_label",
        "target_agency_id", "target_agency_name", "ip_address", "details",
    ])
    for l in logs:
        writer.writerow([
            l.get("timestamp") or "", l.get("super_admin_email") or "",
            l.get("action_type") or "", l.get("action_label") or "",
            l.get("target_agency_id") or "", l.get("target_agency_name") or "",
            l.get("ip_address") or "", l.get("details") or "",
        ])
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"super_admin_logs_{ts}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
