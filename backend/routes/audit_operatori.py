"""Audit operatori — tracciamento completo delle azioni di ogni operatore.

Due fonti, una sola collezione per la sorveglianza admin:
- `audit_operatori` (tenant-scoped): registrata automaticamente dal middleware
  HTTP per OGNI mutazione (POST/PUT/PATCH/DELETE), stampa/esportazione (GET su
  endpoint di stampa/export) e navigazione (inviata dal frontend). Contiene
  utente, area, azione, metodo, path, stato, entità/entita_id, timestamp.
- `attivita_log` (già esistente): usata da `record-storia` per ricostruire
  "creato da / ultima modifica da" di uno specifico record (anche retroattivo).

Visibilità: le viste di sorveglianza (eventi/stats/percorso) sono SOLO admin.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request

from database import db, raw_db
from auth import require_user
from db_models import _now_iso, _uid
from tenant import user_tenant_id, tenant_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])

# ---------------------------------------------------------------------------
# Mappa area: primo segmento del path → etichetta leggibile
# ---------------------------------------------------------------------------
AREA_MAP = {
    "anagrafiche": "Clienti",
    "polizze": "Portafoglio",
    "titoli": "Titoli",
    "sinistri": "Sinistri",
    "contabilita": "Prima Nota",
    "movimenti": "Prima Nota",
    "rappel": "Rappel",
    "ritenute": "Ritenute",
    "pnc": "PNT",
    "provvigioni": "Provvigioni",
    "banche": "Banche",
    "voucher": "Voucher",
    "sospesi": "Sospesi",
    "chiusure": "Chiusure giornata",
    "libro-matricola": "Libro Matricola",
    "regolazione-premio": "Regolazione Premio",
    "compagnie": "Compagnie",
    "agenzie": "Agenzie partner",
    "librerie": "Librerie",
    "esignature": "Firme",
    "firma": "Firme",
    "documenti-inbox": "Documenti Inbox",
    "docinbox": "Documenti Inbox",
    "upload-link": "Richieste documenti",
    "email": "Email",
    "newsletter": "Newsletter",
    "marketing": "Marketing",
    "lead-liste": "Liste Lead",
    "trattative": "Trattative",
    "tasks": "Attività (Tasks)",
    "corsi": "Corsi",
    "pensioni": "Calcolo INPS",
    "statistiche": "Statistiche",
    "cervello": "Il Cervello",
    "import": "Importazioni",
    "import-anagrafiche": "Importazioni",
    "import-massivo": "Importazioni",
    "carichi-mensili": "Carichi Mensili",
    "users": "Utenti",
    "auth": "Accessi",
    "stampa": "Stampe",
    "export": "Esportazioni",
    "incentivazioni": "Incentivazioni",
    "pipeline": "Pipeline",
    "voci-manuali": "Prima Nota",
    "setup": "Setup iniziale",
}

AZIONE_METODO = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}

# path (contiene) → è una stampa / esportazione
_PRINT_HINT = ("/stampa", "stampa/", "/pdf", "pdf/", ".pdf")
_EXPORT_HINT = ("/export", "export/", ".xlsx", ".csv", "export.", "estrai", "estrazione")

# path da NON tracciare automaticamente (rumore / loop)
_SKIP_PREFIX = ("/api/audit", "/api/auth/refresh", "/api/auth/me", "/api/notifiche",
                "/api/chat", "/api/messaggi", "/api/health", "/api/giornate-chiuse")


def _strip_api(path: str) -> str:
    p = path
    if p.startswith("/api/"):
        p = p[5:]
    elif p.startswith("/api"):
        p = p[4:]
    return p.strip("/")


def _looks_like_id(seg: str) -> bool:
    return bool(seg) and (len(seg) >= 8 or seg.isdigit()) and "." not in seg


def classify_request(method: str, path: str) -> Optional[dict]:
    """Ritorna {azione, area, entita, entita_id} o None se la richiesta va ignorata."""
    for pref in _SKIP_PREFIX:
        if path.startswith(pref):
            return None

    low = path.lower()
    is_print = any(h in low for h in _PRINT_HINT)
    is_export = any(h in low for h in _EXPORT_HINT)

    if method == "GET" and not (is_print or is_export):
        return None  # letture normali non tracciate (solo stampe/export)

    rel = _strip_api(path)
    segs = [s for s in rel.split("/") if s]
    first = segs[0] if segs else ""

    if is_print:
        azione = "stampa"
        area = "Stampe"
    elif is_export:
        azione = "esportazione"
        area = "Esportazioni"
    else:
        azione = AZIONE_METODO.get(method, method.lower())
        area = AREA_MAP.get(first, first.capitalize() if first else "Altro")

    entita = first or None
    entita_id = None
    if len(segs) >= 2 and _looks_like_id(segs[1]):
        entita_id = segs[1]
    elif len(segs) >= 3 and _looks_like_id(segs[2]):
        entita_id = segs[2]

    return {"azione": azione, "area": area, "entita": entita, "entita_id": entita_id}


async def registra_audit(user: Optional[dict], method: str, path: str, status: int) -> None:
    """Inserisce un evento di audit (chiamata dal middleware, in background).

    Usa raw_db + tenant esplicito (il ContextVar può essere già stato resettato).
    Non blocca mai la richiesta: ogni errore è silenziato.
    """
    try:
        if not user:
            return
        if user.get("is_super_admin") or user.get("role") == "super_admin":
            return
        tid = user_tenant_id(user)
        if not tid:
            return
        info = classify_request(method, path)
        if not info:
            return
        doc = {
            "id": _uid(),
            "created_at": _now_iso(),
            "agenzia_tenant_id": tid,
            "utente_id": user.get("id"),
            "utente_email": user.get("email"),
            "utente_nome": user.get("name") or user.get("email"),
            "ruolo": user.get("role"),
            "metodo": method,
            "path": path,
            "status": status,
            **info,
        }
        await raw_db.audit_operatori.insert_one(doc)
    except Exception as e:  # pragma: no cover
        logger.debug("registra_audit failed: %s", e)


# ---------------------------------------------------------------------------
# Navigazione (inviata dal frontend ad ogni cambio pagina)
# ---------------------------------------------------------------------------
@router.post("/navigazione")
async def log_navigazione(request: Request,
                          user=Depends(require_user("admin", "collaboratore", "dipendente"))):
    try:
        body = await request.json()
    except Exception:
        body = {}
    path = (body.get("path") or "").strip()[:300]
    titolo = (body.get("titolo") or "").strip()[:120]
    if not path:
        return {"ok": False}
    tid = user_tenant_id(user)
    doc = {
        "id": _uid(),
        "created_at": _now_iso(),
        "agenzia_tenant_id": tid,
        "utente_id": user.get("id"),
        "utente_email": user.get("email"),
        "utente_nome": user.get("name") or user.get("email"),
        "ruolo": user.get("role"),
        "metodo": "NAV",
        "path": path,
        "status": 200,
        "azione": "navigazione",
        "area": titolo or AREA_MAP.get(path.strip("/").split("/")[0], "Pagina"),
        "entita": "pagina",
        "entita_id": None,
    }
    await raw_db.audit_operatori.insert_one(doc)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Storia di un record: "creato da / ultima modifica da" (da attivita_log)
# ---------------------------------------------------------------------------
_MODIFICA_AZIONI_ESCLUSE = {"create", "navigazione", "login", "logout", "view", "read"}


async def _risolvi_nomi(utente_ids: set[str]) -> dict:
    out: dict = {}
    ids = [u for u in utente_ids if u]
    if not ids:
        return out
    async for u in raw_db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}):
        out[u["id"]] = u.get("name") or u.get("email") or ""
    return out


@router.get("/record-storia")
async def record_storia(entita: str, entita_id: str,
                        user=Depends(require_user("admin", "collaboratore"))):
    """Ricostruisce creazione/ultima modifica di un record dal log attività."""
    logs = await db.attivita_log.find(
        {"entita": entita, "entita_id": entita_id}, {"_id": 0},
    ).sort("created_at", 1).to_list(1000)

    uid_set = {l.get("utente_id") for l in logs if l.get("utente_id")}
    nomi = await _risolvi_nomi(uid_set)

    def _nome(l):
        return (l.get("utente_nome")
                or nomi.get(l.get("utente_id"))
                or l.get("utente_email") or "Sistema")

    creato = None
    modificato = None
    for l in logs:
        az = (l.get("azione") or "").lower()
        if az == "create" and creato is None:
            creato = {"da": _nome(l), "quando": l.get("created_at"),
                      "utente_id": l.get("utente_id")}
        if az not in _MODIFICA_AZIONI_ESCLUSE:
            modificato = {"da": _nome(l), "quando": l.get("created_at"),
                          "azione": az, "utente_id": l.get("utente_id")}

    return {
        "entita": entita,
        "entita_id": entita_id,
        "creato": creato,
        "modificato": modificato,
        "n_eventi": len(logs),
    }


# ---------------------------------------------------------------------------
# Sorveglianza (SOLO admin): eventi, statistiche aree, percorso operatore
# ---------------------------------------------------------------------------
def _range_filter(dal: Optional[str], al: Optional[str]) -> dict:
    f: dict = {}
    if dal:
        f.setdefault("created_at", {})["$gte"] = dal
    if al:
        f.setdefault("created_at", {})["$lte"] = al + "T23:59:59"
    return f


@router.get("/eventi")
async def lista_eventi(
    utente_id: Optional[str] = None,
    area: Optional[str] = None,
    azione: Optional[str] = None,
    dal: Optional[str] = None,
    al: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    user=Depends(require_user("admin")),
):
    flt: dict = {**_range_filter(dal, al)}
    if utente_id:
        flt["utente_id"] = utente_id
    if area:
        flt["area"] = area
    if azione:
        flt["azione"] = azione
    if q:
        flt["path"] = {"$regex": q, "$options": "i"}
    total = await db.audit_operatori.count_documents(flt)
    items = await db.audit_operatori.find(flt, {"_id": 0}).sort(
        "created_at", -1).skip(max(0, skip)).to_list(min(limit, 500))
    return {"items": items, "total": total}


@router.get("/stats")
async def stats_aree(
    dal: Optional[str] = None,
    al: Optional[str] = None,
    user=Depends(require_user("admin")),
):
    """Aggrega per operatore × area (per il grafico delle aree più usate)."""
    match = {**_range_filter(dal, al)}
    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {
            "_id": {"u": "$utente_id", "area": "$area"},
            "n": {"$sum": 1},
            "ultima": {"$max": "$created_at"},
            "nome": {"$last": "$utente_nome"},
            "email": {"$last": "$utente_email"},
        }},
    ]
    rows = await db.audit_operatori.aggregate(pipeline).to_list(5000)

    operatori: dict = {}
    aree_set: set = set()
    for r in rows:
        uid = r["_id"].get("u") or "?"
        area = r["_id"].get("area") or "Altro"
        aree_set.add(area)
        op = operatori.setdefault(uid, {
            "utente_id": uid, "nome": r.get("nome"), "email": r.get("email"),
            "totale": 0, "ultima_attivita": None, "aree": {},
        })
        op["aree"][area] = op["aree"].get(area, 0) + r["n"]
        op["totale"] += r["n"]
        if not op["ultima_attivita"] or (r.get("ultima") or "") > op["ultima_attivita"]:
            op["ultima_attivita"] = r.get("ultima")

    # risolvi nomi mancanti
    missing = {uid for uid, op in operatori.items() if not op.get("nome") and uid != "?"}
    if missing:
        nomi = await _risolvi_nomi(missing)
        for uid in missing:
            operatori[uid]["nome"] = nomi.get(uid) or operatori[uid].get("email") or "?"

    op_list = sorted(operatori.values(), key=lambda o: o["totale"], reverse=True)
    aree_tot: dict = {}
    for op in op_list:
        for a, n in op["aree"].items():
            aree_tot[a] = aree_tot.get(a, 0) + n
    aree_ord = [a for a, _ in sorted(aree_tot.items(), key=lambda x: x[1], reverse=True)]
    return {"operatori": op_list, "aree": aree_ord, "aree_totali": aree_tot}


@router.get("/percorso")
async def percorso_operatore(
    utente_id: str,
    dal: Optional[str] = None,
    al: Optional[str] = None,
    limit: int = 300,
    user=Depends(require_user("admin")),
):
    flt: dict = {"utente_id": utente_id, **_range_filter(dal, al)}
    items = await db.audit_operatori.find(flt, {"_id": 0}).sort(
        "created_at", -1).to_list(min(limit, 1000))
    return {"items": items, "total": len(items)}


@router.get("/operatori")
async def lista_operatori(user=Depends(require_user("admin"))):
    """Elenco operatori del tenant per i filtri. ISOLATO per agenzia: ogni
    admin vede SOLO gli operatori della propria agenzia (users NON è
    tenant-scoped dal wrapper, quindi filtriamo esplicitamente)."""
    flt: dict = {"role": {"$in": ["admin", "collaboratore", "dipendente"]}}
    tf = tenant_filter(user)
    if tf:
        flt.update(tf)
    items = await db.users.find(
        flt,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
    ).sort("name", 1).to_list(500)
    return items
