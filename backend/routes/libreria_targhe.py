"""Libreria Targhe — registro veicoli interrogabile per targa.

Aggrega, per ogni targa presente nel tenant:
  - le polizze collegate (storico) con contraente, compagnia, stato, date
  - le applicazioni Libro Matricola (intestatario del veicolo)
  - il libretto di circolazione allegato (categoria `libretto_veicolo`)
  - i dati veicolo (marca, modello, telaio, immatricolazione)

Serve per non ricaricare il libretto ad ogni nuova polizza/sostituzione:
l'endpoint `lookup` suggerisce i dati già presenti quando si digita una targa.

Isolamento multi-tenant: usa `db` (TenantAwareDB) che filtra automaticamente
polizze/applicazioni/allegati/anagrafiche per `agenzia_tenant_id`.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends

from auth import current_user
from database import db

router = APIRouter(prefix="/librerie/targhe", tags=["libreria-targhe"])

_TARGA_CLEAN = re.compile(r"[^A-Z0-9]")


def _norm_targa(t: str | None) -> str:
    if not t:
        return ""
    return _TARGA_CLEAN.sub("", str(t).upper())


def _is_valid_targa(t: str) -> bool:
    # 5-10 caratteri alfanumerici, almeno una lettera (esclude targhe fittizie
    # tutte-zero tipo "00000000000010702").
    return 5 <= len(t) <= 10 and bool(re.search(r"[A-Z]", t))


def _anag_name(a: dict | None) -> str | None:
    if not a:
        return None
    rs = (a.get("ragione_sociale") or "").strip()
    if rs:
        return rs
    full = f"{a.get('cognome', '') or ''} {a.get('nome', '') or ''}".strip()
    return full or None


async def _resolve_anagrafiche(ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    out: dict[str, str] = {}
    async for a in db.anagrafiche.find(
        {"id": {"$in": list(ids)}},
        {"_id": 0, "id": 1, "cognome": 1, "nome": 1, "ragione_sociale": 1},
    ):
        out[a["id"]] = _anag_name(a) or ""
    return out


async def _resolve_compagnie(ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    out: dict[str, str] = {}
    async for c in db.compagnie.find(
        {"id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "ragione_sociale": 1}
    ):
        out[c["id"]] = (c.get("ragione_sociale") or "").strip()
    return out


async def _libretti_for(polizza_ids: set[str], app_ids: set[str]) -> list[dict]:
    """Allegati libretto_veicolo collegati a queste polizze/applicazioni."""
    ors = []
    if polizza_ids:
        ors.append({"entita_tipo": "polizza", "entita_id": {"$in": list(polizza_ids)}})
    if app_ids:
        ors.append({"applicazione_matricola_id": {"$in": list(app_ids)}})
    if not ors:
        return []
    out = []
    async for a in db.allegati.find(
        {"categoria": "libretto_veicolo", "is_deleted": {"$ne": True}, "$or": ors},
        {"_id": 0, "id": 1, "nome_file": 1, "created_at": 1,
         "entita_id": 1, "applicazione_matricola_id": 1},
    ):
        out.append(a)
    return out


# ---------------------------------------------------------------------------
#  Aggregazione targhe (polizze + applicazioni libro matricola)
# ---------------------------------------------------------------------------
async def _aggrega_targhe() -> dict[str, dict]:
    """Ritorna {targa_norm: {...}} con contraenti, compagnie, veicolo, ids."""
    reg: dict[str, dict] = {}

    # 1) Polizze
    async for p in db.polizze.find(
        {"targa": {"$nin": [None, ""]}, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "targa": 1, "contraente_id": 1, "compagnia_id": 1,
         "veicolo_marca": 1, "veicolo_modello": 1, "veicolo_data_immatricolazione": 1,
         "telaio": 1, "veicolo_telaio": 1, "data_effetto": 1, "is_libro_matricola": 1},
    ):
        tn = _norm_targa(p.get("targa"))
        if not _is_valid_targa(tn):
            continue
        r = reg.setdefault(tn, {
            "targa": tn, "n_polizze": 0, "n_applicazioni": 0,
            "contraente_ids": set(), "compagnia_ids": set(),
            "intestatari": set(), "polizza_ids": set(), "app_ids": set(),
            "is_libro_matricola": False, "veicolo": {},
            "_ultima": "",
        })
        r["n_polizze"] += 1
        r["polizza_ids"].add(p["id"])
        if p.get("contraente_id"):
            r["contraente_ids"].add(p["contraente_id"])
        if p.get("compagnia_id"):
            r["compagnia_ids"].add(p["compagnia_id"])
        if p.get("is_libro_matricola"):
            r["is_libro_matricola"] = True
        de = p.get("data_effetto") or ""
        if de >= r["_ultima"]:
            r["_ultima"] = de
            v = r["veicolo"]
            v.setdefault("marca", p.get("veicolo_marca"))
            v.setdefault("modello", p.get("veicolo_modello"))
            v.setdefault("immatricolazione", p.get("veicolo_data_immatricolazione"))
            v.setdefault("telaio", p.get("telaio") or p.get("veicolo_telaio"))
        # fill missing veicolo fields da qualunque polizza
        v = r["veicolo"]
        for k, val in (("marca", p.get("veicolo_marca")),
                       ("modello", p.get("veicolo_modello")),
                       ("immatricolazione", p.get("veicolo_data_immatricolazione")),
                       ("telaio", p.get("telaio") or p.get("veicolo_telaio"))):
            if not v.get(k) and val:
                v[k] = val

    # 2) Applicazioni Libro Matricola
    async for ap in db.applicazioni.find(
        {"targa": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "targa": 1, "polizza_id": 1, "intestatario": 1,
         "intestatario_anagrafica_id": 1, "marca": 1, "modello": 1,
         "data_immatricolazione": 1},
    ):
        tn = _norm_targa(ap.get("targa"))
        if not _is_valid_targa(tn):
            continue
        r = reg.setdefault(tn, {
            "targa": tn, "n_polizze": 0, "n_applicazioni": 0,
            "contraente_ids": set(), "compagnia_ids": set(),
            "intestatari": set(), "polizza_ids": set(), "app_ids": set(),
            "is_libro_matricola": True, "veicolo": {},
            "_ultima": "",
        })
        r["n_applicazioni"] += 1
        r["app_ids"].add(ap["id"])
        r["is_libro_matricola"] = True
        if ap.get("polizza_id"):
            r["polizza_ids"].add(ap["polizza_id"])
        if ap.get("intestatario"):
            r["intestatari"].add(ap["intestatario"].strip())
        if ap.get("intestatario_anagrafica_id"):
            r["contraente_ids"].add(ap["intestatario_anagrafica_id"])
        v = r["veicolo"]
        for k, val in (("marca", ap.get("marca")),
                       ("modello", ap.get("modello")),
                       ("immatricolazione", ap.get("data_immatricolazione"))):
            if not v.get(k) and val:
                v[k] = val

    return reg


@router.get("")
async def list_targhe(q: str = "", limit: int = 60, offset: int = 0,
                      user=Depends(current_user)):
    """Elenco targhe del tenant, con ricerca per targa (`q`)."""
    reg = await _aggrega_targhe()
    qn = _norm_targa(q)
    targhe = [r for r in reg.values() if (not qn or qn in r["targa"])]
    targhe.sort(key=lambda r: r["targa"])
    total = len(targhe)
    page = targhe[offset:offset + limit]

    # Enrichment solo per la pagina corrente
    anag_ids: set[str] = set()
    pol_ids: set[str] = set()
    app_ids: set[str] = set()
    for r in page:
        anag_ids |= r["contraente_ids"]
        pol_ids |= r["polizza_ids"]
        app_ids |= r["app_ids"]
    names = await _resolve_anagrafiche(anag_ids)
    libretti = await _libretti_for(pol_ids, app_ids)
    # mappa targa → ha libretto
    lib_by_pol = {l["entita_id"] for l in libretti if l.get("entita_id")}
    lib_by_app = {l["applicazione_matricola_id"] for l in libretti
                  if l.get("applicazione_matricola_id")}

    items = []
    for r in page:
        proprietari = sorted({names.get(i) for i in r["contraente_ids"] if names.get(i)}
                             | set(r["intestatari"]))
        has_lib = bool(r["polizza_ids"] & lib_by_pol or r["app_ids"] & lib_by_app)
        items.append({
            "targa": r["targa"],
            "proprietari": proprietari,
            "proprietario": proprietari[0] if proprietari else None,
            "n_polizze": r["n_polizze"],
            "n_applicazioni": r["n_applicazioni"],
            "is_libro_matricola": r["is_libro_matricola"],
            "has_libretto": has_lib,
            "veicolo": r["veicolo"],
        })
    return {"items": items, "total": total, "offset": offset, "limit": limit}


def _targa_regex(targa_norm: str) -> str:
    """Pattern che ignora spazi fra i caratteri (es. 'GY 308 AK' == 'GY308AK')."""
    return "^" + r"\s*".join(re.escape(c) for c in targa_norm) + "$"


async def _dettaglio(targa_norm: str) -> dict:
    if not _is_valid_targa(targa_norm):
        return {"targa": targa_norm, "trovata": False}
    rx = {"$regex": _targa_regex(targa_norm), "$options": "i"}

    polizze_docs = [p async for p in db.polizze.find(
        {"targa": rx, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "compagnia_id": 1, "contraente_id": 1,
         "ramo": 1, "prodotto": 1, "stato": 1, "data_effetto": 1, "data_scadenza": 1,
         "is_libro_matricola": 1, "veicolo_marca": 1, "veicolo_modello": 1,
         "veicolo_data_immatricolazione": 1, "telaio": 1, "veicolo_telaio": 1})]
    app_docs = [a async for a in db.applicazioni.find(
        {"targa": rx},
        {"_id": 0, "id": 1, "numero": 1, "polizza_id": 1, "intestatario": 1,
         "intestatario_anagrafica_id": 1, "stato": 1, "data_inclusione": 1,
         "data_esclusione": 1, "marca": 1, "modello": 1, "data_immatricolazione": 1})]

    if not polizze_docs and not app_docs:
        return {"targa": targa_norm, "trovata": False}

    pol_ids = {p["id"] for p in polizze_docs}
    pol_ids |= {a["polizza_id"] for a in app_docs if a.get("polizza_id")}
    app_ids = {a["id"] for a in app_docs}
    anag_ids = {p.get("contraente_id") for p in polizze_docs if p.get("contraente_id")}
    anag_ids |= {a.get("intestatario_anagrafica_id") for a in app_docs if a.get("intestatario_anagrafica_id")}
    comp_ids = {p.get("compagnia_id") for p in polizze_docs if p.get("compagnia_id")}
    intestatari = {a["intestatario"].strip() for a in app_docs if a.get("intestatario")}
    is_lm = any(p.get("is_libro_matricola") for p in polizze_docs) or bool(app_docs)

    names = await _resolve_anagrafiche(anag_ids)
    comps = await _resolve_compagnie(comp_ids)
    libretti_raw = await _libretti_for(pol_ids, app_ids)
    libretti = sorted(libretti_raw, key=lambda a: a.get("created_at") or "", reverse=True)

    # Dati veicolo: primo valore non-nullo (polizza più recente prima)
    veicolo: dict = {}
    for p in sorted(polizze_docs, key=lambda x: x.get("data_effetto") or "", reverse=True):
        for k, val in (("marca", p.get("veicolo_marca")), ("modello", p.get("veicolo_modello")),
                       ("immatricolazione", p.get("veicolo_data_immatricolazione")),
                       ("telaio", p.get("telaio") or p.get("veicolo_telaio"))):
            if not veicolo.get(k) and val:
                veicolo[k] = val
    for a in app_docs:
        for k, val in (("marca", a.get("marca")), ("modello", a.get("modello")),
                       ("immatricolazione", a.get("data_immatricolazione"))):
            if not veicolo.get(k) and val:
                veicolo[k] = val

    polizze = [{
        "id": p["id"], "numero_polizza": p.get("numero_polizza"),
        "compagnia": comps.get(p.get("compagnia_id")),
        "contraente": names.get(p.get("contraente_id")),
        "ramo": p.get("ramo"), "prodotto": p.get("prodotto"), "stato": p.get("stato"),
        "data_effetto": p.get("data_effetto"), "data_scadenza": p.get("data_scadenza"),
        "is_libro_matricola": bool(p.get("is_libro_matricola")),
    } for p in polizze_docs]
    polizze.sort(key=lambda x: x.get("data_effetto") or "", reverse=True)

    applicazioni = [{
        "id": a["id"], "numero": a.get("numero"), "polizza_id": a.get("polizza_id"),
        "intestatario": a.get("intestatario"), "stato": a.get("stato"),
        "data_inclusione": a.get("data_inclusione"), "data_esclusione": a.get("data_esclusione"),
    } for a in app_docs]

    proprietari = sorted({names.get(i) for i in anag_ids if names.get(i)} | intestatari)
    return {
        "targa": targa_norm,
        "trovata": True,
        "proprietari": proprietari,
        "is_libro_matricola": is_lm,
        "veicolo": veicolo,
        "libretti": [{
            "id": l["id"], "nome_file": l.get("nome_file"),
            "created_at": l.get("created_at"),
            "download_url": f"/allegati/{l['id']}/download",
        } for l in libretti],
        "polizze": polizze,
        "applicazioni": applicazioni,
    }


@router.get("/lookup/{targa}")
async def lookup_targa(targa: str, user=Depends(current_user)):
    """Suggerimento rapido quando si digita una targa in una nuova polizza:
    ritorna se la targa esiste già, i dati veicolo, il proprietario e il
    libretto da riutilizzare (così non va ricaricato)."""
    d = await _dettaglio(_norm_targa(targa))
    if not d.get("trovata"):
        return {"targa": d["targa"], "trovata": False}
    libretto = d["libretti"][0] if d["libretti"] else None
    return {
        "targa": d["targa"],
        "trovata": True,
        "proprietario": d["proprietari"][0] if d["proprietari"] else None,
        "proprietari": d["proprietari"],
        "veicolo": d["veicolo"],
        "libretto": libretto,
        "n_polizze": len(d["polizze"]),
    }


@router.get("/{targa}")
async def dettaglio_targa(targa: str, user=Depends(current_user)):
    return await _dettaglio(_norm_targa(targa))
