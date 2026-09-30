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
                     n_sin_old: int, n_provv: int,
                     n_richieste: int = 0, n_ci_scad: int = 0) -> list[dict]:
    """Compone la lista dei task per la dashboard."""
    return [
        {"key": "richieste_portale", "label": "Richieste dal Portale Cliente",
         "icon": "Inbox", "color": "violet", "count": n_richieste,
         "url": "/richieste-cliente",
         "descrizione": "Modifiche anagrafica / documenti da approvare"},
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
        {"key": "carta_identita_scadenza", "label": "Carte d'identità in scadenza (30gg)",
         "icon": "IdCard", "color": "amber", "count": n_ci_scad,
         "url": "/anagrafiche?doc=ci_in_scadenza",
         "descrizione": "Clienti con carta d'identità prossima alla scadenza"},
        {"key": "titoli_sospesi_old", "label": "Titoli sospesi da oltre 5 giorni",
         "icon": "AlertTriangle", "color": "orange", "count": n_sospesi_old,
         "url": "/sospesi?gg_min=5",
         "descrizione": "Anticipati dall'agenzia, da incassare"},
        {"key": "polizze_in_scadenza_30", "label": "Polizze in scadenza (30gg)",
         "icon": "CalendarClock", "color": "blue", "count": n_pol_scad,
         "url": "/titoli?preset=tutti_aperti", "descrizione": "Prossime al rinnovo — apri i titoli"},
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
    n_ci_scad = await db.anagrafiche.count_documents({
        "ci_data_scadenza": {"$gte": today_iso, "$lte": in_30},
    })
    n_provv = await db.titoli.count_documents({
        "stato": {"$in": ["incassato"]},
        "provvigione_pagata": {"$ne": True},
        "collaboratore_id": {"$ne": None},
    })

    # Richieste dal Portale Cliente da verificare
    n_richieste = await db.richieste_cliente.count_documents({"stato": "da_verificare"})

    return _build_task_list(
        n_comp_oggi=n_comp_oggi, n_comp_sett=n_comp_sett,
        n_doc_scaduti=n_doc_scaduti, n_doc_scad=n_doc_scad,
        n_sospesi_old=n_sospesi_old, n_pol_scad=n_pol_scad,
        n_sin_old=n_sin_old, n_provv=n_provv,
        n_richieste=n_richieste, n_ci_scad=n_ci_scad,
    )


# ---------------------------------------------------------------------------
# Automazioni di oggi (feed con drill-down invii)
# ---------------------------------------------------------------------------
def _categoria_automazione(preset_key: str, rule_nome: str) -> tuple[str, str, str]:
    """Ritorna (categoria_key, label, icona) in base al preset/nome regola."""
    pk = (preset_key or "").lower()
    nm = (rule_nome or "").lower()
    blob = f"{pk} {nm}"
    if "compleanno" in blob or "auguri" in blob:
        return ("compleanni", "Compleanni", "Cake")
    if "sollecito" in blob or "insoluto" in blob or "scaduta" in blob or "scaduto" in blob:
        return ("solleciti", "Solleciti", "AlarmClock")
    if "scadenza" in blob or "rinnovo" in blob or "identita" in blob or "veicolo" in blob:
        return ("scadenze", "Avvisi scadenza", "CalendarClock")
    if "sinistro" in blob:
        return ("sinistri", "Sinistri", "AlertTriangle")
    return ("altro", "Altre automazioni", "Zap")


@router.get("/dashboard/automazioni-oggi")
async def dashboard_automazioni_oggi(
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Feed delle automazioni eseguite oggi (invii alert + sinistri aperti/liquidati),
    raggruppate per categoria con drill-down degli invii."""
    today_iso = date.today().isoformat()

    # 1) Eventi alert di oggi
    events = await db.alert_events.find(
        {"created_at": {"$gte": today_iso}},
        {"_id": 0, "corpo": 0, "payload": 0},
    ).sort("created_at", -1).to_list(1000)

    rule_ids = list({e.get("rule_id") for e in events if e.get("rule_id")})
    rules = {}
    if rule_ids:
        async for r in db.alert_rules.find(
            {"id": {"$in": rule_ids}}, {"_id": 0, "id": 1, "preset_key": 1, "nome": 1},
        ):
            rules[r["id"]] = r

    cats: dict[str, dict] = {}

    def _bucket(key, label, icona):
        if key not in cats:
            cats[key] = {"key": key, "label": label, "icona": icona,
                         "totale": 0, "inviati": 0, "errori": 0, "items": []}
        return cats[key]

    for e in events:
        rule = rules.get(e.get("rule_id"), {})
        ck, label, icona = _categoria_automazione(rule.get("preset_key"), e.get("rule_nome"))
        b = _bucket(ck, label, icona)
        b["totale"] += 1
        if e.get("status") == "ok":
            b["inviati"] += 1
        elif e.get("status") == "errore":
            b["errori"] += 1
        b["items"].append({
            "id": e.get("id"),
            "destinatario": e.get("destinatario_label") or e.get("destinatario_indirizzo") or "—",
            "canale": e.get("canale"),
            "oggetto": e.get("oggetto"),
            "status": e.get("status"),
            "ora": (e.get("sent_at") or e.get("created_at") or "")[11:16],
            "entita_tipo": e.get("entita_tipo"),
            "entita_id": e.get("entita_id"),
            "errore": e.get("error_message"),
        })

    # 2) Sinistri aperti/liquidati oggi
    sin_aperti = await db.sinistri.find(
        {"$or": [{"data_apertura": today_iso}, {"data_denuncia": today_iso}]},
        {"_id": 0, "id": 1, "numero_sinistro": 1, "data_apertura": 1, "data_denuncia": 1, "created_at": 1},
    ).to_list(200)
    sin_liq = await db.sinistri.find(
        {"data_liquidazione": today_iso},
        {"_id": 0, "id": 1, "numero_sinistro": 1, "liquidazione": 1, "created_at": 1},
    ).to_list(200)
    if sin_aperti or sin_liq:
        b = _bucket("sinistri", "Sinistri", "AlertTriangle")
        for s in sin_aperti:
            b["totale"] += 1; b["inviati"] += 1
            b["items"].append({
                "id": s.get("id"), "destinatario": f"Sinistro {s.get('numero_sinistro') or ''}".strip(),
                "canale": "sistema", "oggetto": "Sinistro aperto", "status": "ok",
                "ora": (s.get("created_at") or "")[11:16], "entita_tipo": "sinistro", "entita_id": s.get("id"),
            })
        for s in sin_liq:
            b["totale"] += 1; b["inviati"] += 1
            b["items"].append({
                "id": s.get("id"), "destinatario": f"Sinistro {s.get('numero_sinistro') or ''}".strip(),
                "canale": "sistema", "oggetto": f"Liquidato € {s.get('liquidazione') or 0:,.2f}",
                "status": "ok", "ora": "", "entita_tipo": "sinistro", "entita_id": s.get("id"),
            })

    ordine = ["compleanni", "scadenze", "solleciti", "sinistri", "altro"]
    categorie = sorted(cats.values(), key=lambda c: ordine.index(c["key"]) if c["key"] in ordine else 99)
    return {
        "data": today_iso,
        "totale_invii": sum(c["totale"] for c in categorie),
        "totale_inviati": sum(c["inviati"] for c in categorie),
        "totale_errori": sum(c["errori"] for c in categorie),
        "categorie": categorie,
    }



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



# ---------------------------------------------------------------------------
# Attività recenti dei clienti (upload da link, regolazione premio, upload app)
# ---------------------------------------------------------------------------
@router.get("/dashboard/attivita-clienti")
async def dashboard_attivita_clienti(
    giorni: int = 30, limit: int = 20,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    """Elenca gli ultimi eventi generati dai clienti:
    - caricamento documento dal link 'Richiedi documento'
    - risposta alla regolazione premio
    - caricamento documento dall'App/Portale
    Il tenant è risolto tramite le entità collegate (robusto anche per gli
    endpoint pubblici che non impostano il contesto tenant)."""
    from datetime import datetime, timezone
    from database import raw_db
    from tenant import user_tenant_id

    tid = user_tenant_id(user)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, giorni))).isoformat()
    eventi: list[dict] = []

    def _anag_nome(a: dict) -> str:
        return (a.get("ragione_sociale")
                or f"{a.get('cognome', '')} {a.get('nome', '')}".strip()
                or "Cliente")

    # 1) Upload dal link "Richiedi documento" (upload_links: già con agenzia_tenant_id)
    async for l in raw_db.upload_links.find(
        {"agenzia_tenant_id": tid, "uploads.0": {"$exists": True}}, {"_id": 0},
    ):
        for up in (l.get("uploads") or []):
            if (up.get("at") or "") >= cutoff:
                eventi.append({
                    "tipo": "doc_link", "icona": "Paperclip",
                    "cliente": l.get("anagrafica_nome") or "Cliente",
                    "descrizione": f"Ha caricato «{up.get('nome_file') or 'documento'}» — {l.get('descrizione') or 'documento richiesto'}",
                    "data": up.get("at"),
                    "link": f"/anagrafiche/{l.get('anagrafica_id')}" if l.get("anagrafica_id") else None,
                })

    # 2) Regolazione premio: dato ricevuto (risolvo tenant via polizza)
    reg = await raw_db.regolazione_storico.find(
        {"evento": "dato_cliente_ricevuto", "created_at": {"$gte": cutoff}}, {"_id": 0},
    ).to_list(500)
    pol_ids = list({r.get("polizza_id") for r in reg if r.get("polizza_id")})
    pol_map = {}
    if pol_ids:
        async for p in raw_db.polizze.find(
            {"id": {"$in": pol_ids}, "agenzia_tenant_id": tid},
            {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1},
        ):
            pol_map[p["id"]] = p
    ana_ids_reg = list({p.get("contraente_id") for p in pol_map.values() if p.get("contraente_id")})
    ana_map = {}
    if ana_ids_reg:
        async for a in raw_db.anagrafiche.find(
            {"id": {"$in": ana_ids_reg}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "nome": 1, "cognome": 1},
        ):
            ana_map[a["id"]] = _anag_nome(a)
    for r in reg:
        pol = pol_map.get(r.get("polizza_id"))
        if not pol:
            continue  # polizza di un altro tenant → salta
        eventi.append({
            "tipo": "regolazione", "icona": "Euro",
            "cliente": ana_map.get(pol.get("contraente_id")) or "Cliente",
            "descrizione": f"Ha risposto alla regolazione premio (dato dichiarato: {r.get('base_dichiarata')}) — polizza {pol.get('numero_polizza') or '?'}",
            "data": r.get("created_at") or r.get("data"),
            "link": f"/polizze/{r.get('polizza_id')}" if r.get("polizza_id") else None,
        })

    # 3) Upload dall'App/Portale (risolvo tenant via anagrafica del cliente)
    ric = await raw_db.richieste_cliente.find(
        {"tipo": "upload_documento", "created_at": {"$gte": cutoff}}, {"_id": 0},
    ).to_list(500)
    cli_ids = list({r.get("cliente_id") for r in ric if r.get("cliente_id")})
    cli_map = {}
    if cli_ids:
        async for a in raw_db.anagrafiche.find(
            {"id": {"$in": cli_ids}, "agenzia_tenant_id": tid},
            {"_id": 0, "id": 1, "ragione_sociale": 1, "nome": 1, "cognome": 1},
        ):
            cli_map[a["id"]] = _anag_nome(a)
    for r in ric:
        if r.get("cliente_id") not in cli_map:
            continue  # cliente di un altro tenant → salta
        eventi.append({
            "tipo": "app_upload", "icona": "Smartphone",
            "cliente": r.get("cliente_nome") or cli_map.get(r.get("cliente_id")) or "Cliente",
            "descrizione": "Ha caricato un documento dall'App/Portale",
            "data": r.get("created_at"),
            "link": f"/anagrafiche/{r.get('cliente_id')}" if r.get("cliente_id") else None,
        })

    eventi.sort(key=lambda x: x.get("data") or "", reverse=True)
    return {"eventi": eventi[:limit], "totale": len(eventi)}
