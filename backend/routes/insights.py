"""Insights cliente, statistiche aggregate, "Il Cervello" (AI assistant)
e Ritenute. Endpoint nuovi raggruppati in modulo dedicato per evitare
ulteriore crescita di ``server.py``.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter()


# ---------------------------- INSIGHTS CLIENTE ----------------------------
@router.get("/anagrafiche/{aid}/insights")
async def cliente_insights(aid: str, user=Depends(current_user)) -> dict:
    """Riassunto comportamentale del cliente:
    - cliente_da (mesi)
    - sinistri (totali e ultimi 12 mesi)
    - ultima interazione marketing
    - polizze "ferme" (non modificate da X gg)
    - suggerimenti automatici (es. richiamare/upsell)
    """
    a = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Anagrafica non trovata")

    now = datetime.now(timezone.utc)
    created = a.get("created_at") or a.get("data_creazione") or _now_iso()
    try:
        created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    except Exception:
        created_dt = now
    cliente_da_giorni = max(0, (now - created_dt).days)
    cliente_da_mesi = cliente_da_giorni // 30

    # Sinistri totali e ultimo anno
    one_year_ago_iso = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    sin_tot = await db.sinistri.count_documents({"contraente_id": aid})
    sin_anno = await db.sinistri.count_documents({
        "contraente_id": aid, "data_avvenimento": {"$gte": one_year_ago_iso},
    })
    sin_aperti = await db.sinistri.count_documents({
        "contraente_id": aid, "stato": {"$in": ["aperto", "in_istruttoria"]},
    })

    # Ultima interazione marketing (campagne/comunicazioni dirette)
    last_mkt = await db.comunicazioni.find_one(
        {"anagrafica_id": aid, "categoria": "marketing"},
        {"_id": 0, "data": 1, "tipo": 1, "oggetto": 1},
        sort=[("data", -1)],
    )
    last_comm_any = await db.comunicazioni.find_one(
        {"anagrafica_id": aid},
        {"_id": 0, "data": 1, "tipo": 1, "oggetto": 1},
        sort=[("data", -1)],
    )

    # Polizze attive + tempo da ultima modifica
    polizze = await db.polizze.find(
        {"contraente_id": aid, "stato": {"$in": ["attiva", "in_emissione"]}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "prodotto": 1,
         "premio_lordo": 1, "scadenza": 1, "decorrenza": 1, "updated_at": 1,
         "garanzie": 1, "catastrofale": 1},
    ).to_list(500)
    premio_tot = sum(float(p.get("premio_lordo") or 0) for p in polizze)
    polizze_ferme = []
    for p in polizze:
        upd = p.get("updated_at") or p.get("decorrenza")
        try:
            up_dt = datetime.fromisoformat(str(upd).replace("Z", "+00:00"))
        except Exception:
            up_dt = now
        giorni = (now - up_dt).days
        if giorni > 365:
            polizze_ferme.append({
                "id": p["id"], "numero_polizza": p.get("numero_polizza"),
                "ramo": p.get("ramo"), "giorni_ferma": giorni,
                "premio_lordo": p.get("premio_lordo"),
            })

    # Suggerimenti automatici (regole semplici)
    sugg = []
    if cliente_da_mesi >= 12 and sin_tot == 0:
        sugg.append({
            "priorita": "media",
            "testo": f"Cliente da {cliente_da_mesi} mesi senza sinistri: ottimo candidato per upsell garanzie.",
        })
    if last_mkt is None:
        sugg.append({
            "priorita": "alta",
            "testo": "Nessuna interazione marketing registrata. Inserire in prossima campagna newsletter.",
        })
    elif last_mkt:
        try:
            dt = datetime.fromisoformat(str(last_mkt["data"]).replace("Z", "+00:00"))
            mesi_dall_ultima = (now - dt).days // 30
            if mesi_dall_ultima >= 6:
                sugg.append({
                    "priorita": "alta",
                    "testo": f"Ultima comunicazione marketing {mesi_dall_ultima} mesi fa. Rinnovare contatto.",
                })
        except Exception:
            pass
    if polizze_ferme:
        sugg.append({
            "priorita": "alta",
            "testo": f"{len(polizze_ferme)} polizze ferme da oltre 12 mesi. Pianificare revisione/check-up.",
        })
    if sin_anno >= 2:
        sugg.append({
            "priorita": "media",
            "testo": f"{sin_anno} sinistri nell'ultimo anno. Valutare adeguamento garanzie/franchigie.",
        })

    # Check-up sanitario reminder
    polizze_sanitarie = [p for p in polizze if any(
        k in (p.get("ramo", "") + " " + p.get("prodotto", "")).upper()
        for k in ("SANIT", "MALATTI", "SALUTE", "INFORTUN")
    )]
    if polizze_sanitarie:
        sugg.append({
            "priorita": "media",
            "testo": f"Cliente ha {len(polizze_sanitarie)} polizze sanitarie. Verificare se attivare check-up annuale.",
        })

    return {
        "anagrafica_id": aid,
        "cliente_da_giorni": cliente_da_giorni,
        "cliente_da_mesi": cliente_da_mesi,
        "sinistri_totali": sin_tot,
        "sinistri_ultimo_anno": sin_anno,
        "sinistri_aperti": sin_aperti,
        "ultima_interazione_marketing": last_mkt,
        "ultima_comunicazione_qualsiasi": last_comm_any,
        "polizze_attive": len(polizze),
        "polizze_ferme_oltre_12m": polizze_ferme,
        "premio_attivo_totale": premio_tot,
        "polizze_sanitarie": len(polizze_sanitarie),
        "suggerimenti": sugg,
    }


# ---------------------------- TAG GARANZIE SPECIALI AUTO ----------------------------
def _detect_garanzie_speciali(polizza: dict) -> dict:
    """Rileva automaticamente garanzie speciali dalla descrizione delle garanzie/note.

    Ritorna ``{catastrofale, check_up, inabilita_malattia, tutela_legale, infortuni_conducente}``.
    """
    haystacks = []
    if polizza.get("garanzie"):
        for g in polizza["garanzie"]:
            if isinstance(g, dict):
                haystacks.append((g.get("nome") or "") + " " + (g.get("descrizione") or ""))
            else:
                haystacks.append(str(g))
    for k in ("ramo", "prodotto", "note"):
        if polizza.get(k):
            haystacks.append(polizza[k])
    text = " ".join(haystacks).upper()

    def any_in(words):
        return any(w in text for w in words)

    return {
        "catastrofale": any_in(["TERREMOT", "ALLUVION", "INONDAZ", "CATASTROF",
                                "SISMA", "FRAN", "SOVRACCAR", "EVENTI_NATUR"]),
        "check_up": any_in(["CHECK UP", "CHECK-UP", "CHECKUP", "VISITA PERIODIC",
                            "PREVENZ", "ESAMI DI ROUTINE"]),
        "inabilita_malattia": any_in(["INABILIT", "MALATTI", "GG MALATTI",
                                       "DIARIA MALATTI", "ITT", "INVALIDIT PERMANENTE MALATT"]),
        "tutela_legale": any_in(["TUTELA LEGAL", "ASSISTENZA LEGAL"]),
        "infortuni_conducente": any_in(["INFORTUNI CONDUC", "INFORTUNI DEL CONDUCENTE",
                                          "RC CONDUCENTE"]),
    }


def _detect_catastrofale(polizza: dict) -> bool:
    """Compat: ritorna solo il flag catastrofale (per chiamate legacy)."""
    return _detect_garanzie_speciali(polizza)["catastrofale"]


@router.get("/polizze/{pid}/check-garanzie-speciali")
async def check_garanzie_speciali(pid: str, user=Depends(current_user)) -> dict:
    p = await db.polizze.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Polizza non trovata")
    flags = _detect_garanzie_speciali(p)
    upd = {k: v for k, v in flags.items() if p.get(k) != v}
    if upd:
        await db.polizze.update_one({"id": pid}, {"$set": upd})
    return {"polizza_id": pid, **flags}


@router.get("/polizze/{pid}/check-catastrofale")
async def check_catastrofale(pid: str, user=Depends(current_user)) -> dict:
    """Compat: rileva solo catastrofale."""
    return await check_garanzie_speciali(pid, user)


@router.post("/polizze/check-catastrofale-bulk")
async def check_garanzie_bulk(user=Depends(require_user("admin", "collaboratore"))) -> dict:
    """Scansiona TUTTE le polizze e aggiorna i flag garanzie speciali."""
    updated = 0
    total = 0
    counters = {"catastrofale": 0, "check_up": 0, "inabilita_malattia": 0,
                "tutela_legale": 0, "infortuni_conducente": 0}
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "ramo": 1, "prodotto": 1,
                                        "garanzie": 1, "note": 1, "catastrofale": 1,
                                        "check_up": 1, "inabilita_malattia": 1,
                                        "tutela_legale": 1, "infortuni_conducente": 1}):
        total += 1
        flags = _detect_garanzie_speciali(p)
        diff = {k: v for k, v in flags.items() if p.get(k) != v}
        if diff:
            await db.polizze.update_one({"id": p["id"]}, {"$set": diff})
            updated += 1
        for k, v in flags.items():
            if v:
                counters[k] += 1
    return {"total": total, "updated": updated, "totali_garanzie": counters}


# ---------------------------- ME PERMISSIONS ----------------------------
@router.get("/auth/me/permissions")
async def me_permissions(user=Depends(current_user)) -> dict:
    """Restituisce le ``effective_permissions`` dell'utente loggato.
    Il frontend usa questo endpoint per nascondere/disabilitare pulsanti
    in base alle reali capacità del profilo (non solo al ``role``).
    """
    pid = user.get("profilo_permessi_id")
    if not pid:
        # admin senza profilo → accesso completo (compat)
        return {"role": user["role"], "effective_permissions": {}, "is_full_admin": True}
    profilo = await db.profili_permessi.find_one({"id": pid}, {"_id": 0})
    if not profilo:
        return {"role": user["role"], "effective_permissions": {}, "is_full_admin": False}
    from routes.permessi import _merge_permissions
    eff = _merge_permissions(profilo.get("area_levels") or {}, profilo.get("area_permissions") or {})
    return {
        "role": user["role"],
        "profilo_nome": profilo.get("nome"),
        "effective_permissions": eff,
        "is_full_admin": False,
    }


# ---------------------------- STATISTICHE ----------------------------
@router.get("/statistiche/overview")
async def statistiche_overview(user=Depends(current_user)) -> dict:
    """Aggregati globali per dashboard Statistiche."""
    now = datetime.now(timezone.utc)
    one_year_ago = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    thirty_d_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    n_clienti = await db.anagrafiche.count_documents({"tipo": "persona_fisica"})
    n_aziende = await db.anagrafiche.count_documents({"tipo": "persona_giuridica"})
    n_polizze_attive = await db.polizze.count_documents({"stato": {"$in": ["attiva", "in_emissione"]}})
    n_polizze_scadute = await db.polizze.count_documents({"stato": "scaduta"})
    n_sin_aperti = await db.sinistri.count_documents({"stato": "aperto"})
    n_sin_anno = await db.sinistri.count_documents({"data_avvenimento": {"$gte": one_year_ago}})

    # Premio totale attivo
    agg = await db.polizze.aggregate([
        {"$match": {"stato": {"$in": ["attiva", "in_emissione"]}}},
        {"$group": {"_id": None, "tot": {"$sum": "$premio_lordo"}}},
    ]).to_list(1)
    premio_attivo = float(agg[0]["tot"]) if agg else 0

    # Top 5 compagnie per numero polizze
    agg_comp = await db.polizze.aggregate([
        {"$match": {"stato": {"$in": ["attiva", "in_emissione"]}}},
        {"$group": {"_id": "$compagnia_id", "n": {"$sum": 1}, "premio": {"$sum": "$premio_lordo"}}},
        {"$sort": {"premio": -1}}, {"$limit": 5},
    ]).to_list(5)
    comp_ids = [c["_id"] for c in agg_comp if c["_id"]]
    comp_map = {c["id"]: c["ragione_sociale"] async for c in
                db.compagnie.find({"id": {"$in": comp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    top_compagnie = [{
        "id": c["_id"], "nome": comp_map.get(c["_id"], "—"),
        "n_polizze": c["n"], "premio_totale": c["premio"],
    } for c in agg_comp]

    # Top 5 rami per premio
    agg_ramo = await db.polizze.aggregate([
        {"$match": {"stato": {"$in": ["attiva", "in_emissione"]}}},
        {"$group": {"_id": "$ramo", "n": {"$sum": 1}, "premio": {"$sum": "$premio_lordo"}}},
        {"$sort": {"premio": -1}}, {"$limit": 5},
    ]).to_list(5)
    top_rami = [{"ramo": r["_id"] or "—", "n_polizze": r["n"], "premio_totale": r["premio"]}
                for r in agg_ramo]

    # Polizze in scadenza nei prossimi 30 giorni
    in_scadenza = await db.polizze.count_documents({
        "stato": {"$in": ["attiva", "in_emissione"]},
        "scadenza": {"$gte": now.strftime("%Y-%m-%d"),
                     "$lte": (now + timedelta(days=30)).strftime("%Y-%m-%d")},
    })

    # Nuovi clienti ultimi 30 gg
    nuovi_30g = await db.anagrafiche.count_documents({"created_at": {"$gte": thirty_d_ago}})

    return {
        "clienti_privati": n_clienti, "clienti_aziende": n_aziende,
        "nuovi_clienti_30g": nuovi_30g,
        "polizze_attive": n_polizze_attive, "polizze_scadute": n_polizze_scadute,
        "polizze_in_scadenza_30g": in_scadenza,
        "premio_attivo_totale": premio_attivo,
        "sinistri_aperti": n_sin_aperti,
        "sinistri_ultimo_anno": n_sin_anno,
        "top_compagnie": top_compagnie,
        "top_rami": top_rami,
    }


@router.get("/statistiche/isa")
async def statistiche_isa(anno: int | None = None, user=Depends(current_user)) -> dict:
    """Calcolo Indice ISA (Indici Sintetici di Affidabilità fiscale).

    Per un'agenzia assicurativa il punteggio reale dipende dai dati fiscali
    dell'Agenzia delle Entrate; qui calcoliamo una **stima** 1-10 basata sui
    seguenti indicatori operativi:

    - **Redditività**: utile lordo / ricavi (peso 30%)
    - **Densità clienti**: polizze/clienti attivi (peso 20%)
    - **Diversificazione**: numero rami coperti / 8 (peso 15%)
    - **Continuità**: % polizze non scadute (peso 20%)
    - **Crescita**: nuovi clienti 12 mesi / clienti totali (peso 15%)

    Ogni indicatore è normalizzato 0-1 poi pesato e moltiplicato × 10.
    """
    now = datetime.now(timezone.utc)
    if anno is None:
        anno = now.year
    inizio_anno = f"{anno}-01-01"
    fine_anno = f"{anno}-12-31"

    # Ricavi annuali (provvigioni dai movimenti contabili)
    agg_prov = await db.movimenti.aggregate([
        {"$match": {"tipo": "entrata", "data_movimento": {"$gte": inizio_anno, "$lte": fine_anno}}},
        {"$group": {"_id": None, "tot": {"$sum": "$importo"}}},
    ]).to_list(1)
    ricavi = float(agg_prov[0]["tot"]) if agg_prov else 0

    # Costi struttura (dal cervello)
    costi_doc = await db.costi_annuali.find_one({"anno": anno}, {"_id": 0})
    costi_totali = 0.0
    if costi_doc:
        for v in (costi_doc.get("voci") or []):
            costi_totali += float(v.get("importo") or 0)

    utile = ricavi - costi_totali
    redditivita = (utile / ricavi) if ricavi > 0 else 0
    redditivita_norm = max(0, min(1, redditivita / 0.30))  # 30% = top

    # Clienti attivi e polizze attive
    n_clienti_tot = await db.anagrafiche.count_documents({})
    n_polizze_att = await db.polizze.count_documents({"stato": {"$in": ["attiva", "in_emissione"]}})
    densita = (n_polizze_att / n_clienti_tot) if n_clienti_tot > 0 else 0
    densita_norm = max(0, min(1, densita / 3.0))  # 3 polizze/cliente = top

    # Diversificazione rami
    rami_distinti = await db.polizze.distinct("ramo", {"stato": {"$in": ["attiva", "in_emissione"]}})
    n_rami = len([r for r in rami_distinti if r])
    diversif_norm = max(0, min(1, n_rami / 8.0))

    # Continuità: % polizze non scadute
    n_pol_tot = await db.polizze.count_documents({})
    continuita = (n_polizze_att / n_pol_tot) if n_pol_tot > 0 else 0
    continuita_norm = max(0, min(1, continuita))

    # Crescita: nuovi clienti 12m / clienti totali
    one_year_ago = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    nuovi_12m = await db.anagrafiche.count_documents({"created_at": {"$gte": one_year_ago}})
    crescita = (nuovi_12m / n_clienti_tot) if n_clienti_tot > 0 else 0
    crescita_norm = max(0, min(1, crescita / 0.20))  # 20% crescita = top

    # Punteggio finale 1-10
    score = (
        redditivita_norm * 0.30
        + densita_norm * 0.20
        + diversif_norm * 0.15
        + continuita_norm * 0.20
        + crescita_norm * 0.15
    ) * 10
    score = round(max(1.0, score), 2)

    # Livello descrittivo
    if score >= 9: livello, colore = "Massima affidabilità", "emerald"
    elif score >= 7: livello, colore = "Affidabile", "sky"
    elif score >= 5: livello, colore = "Sufficiente", "amber"
    elif score >= 3: livello, colore = "Inadeguato", "orange"
    else: livello, colore = "Critico", "rose"

    return {
        "anno": anno,
        "punteggio": score,
        "livello": livello,
        "colore": colore,
        "indicatori": [
            {"nome": "Redditività", "valore": round(redditivita * 100, 2),
             "unita": "%", "punteggio": round(redditivita_norm * 10, 2),
             "peso": 30, "soglia": 30, "descrizione": "Utile lordo / Ricavi"},
            {"nome": "Densità clienti", "valore": round(densita, 2),
             "unita": "polizze/cliente", "punteggio": round(densita_norm * 10, 2),
             "peso": 20, "soglia": 3, "descrizione": "Polizze attive / Clienti"},
            {"nome": "Diversificazione", "valore": n_rami,
             "unita": "rami", "punteggio": round(diversif_norm * 10, 2),
             "peso": 15, "soglia": 8, "descrizione": "Rami coperti"},
            {"nome": "Continuità", "valore": round(continuita * 100, 2),
             "unita": "%", "punteggio": round(continuita_norm * 10, 2),
             "peso": 20, "soglia": 100, "descrizione": "% polizze non scadute"},
            {"nome": "Crescita", "valore": round(crescita * 100, 2),
             "unita": "%", "punteggio": round(crescita_norm * 10, 2),
             "peso": 15, "soglia": 20, "descrizione": "Nuovi clienti / Totale (12m)"},
        ],
        "dati_calcolo": {
            "ricavi": round(ricavi, 2),
            "costi": round(costi_totali, 2),
            "utile": round(utile, 2),
            "n_clienti_tot": n_clienti_tot,
            "n_polizze_attive": n_polizze_att,
            "n_polizze_tot": n_pol_tot,
            "nuovi_clienti_12m": nuovi_12m,
        },
        "note": (
            "Stima operativa basata sui dati interni dell'agenzia. Il punteggio "
            "ISA ufficiale viene calcolato dall'Agenzia delle Entrate sulla "
            "dichiarazione fiscale."
        ),
    }


# ---------------------------- IL CERVELLO (AI) ----------------------------
@router.get("/cervello/suggerimenti")
async def cervello_suggerimenti(
    limit: int = 30, solo_miei: bool = False, user=Depends(current_user),
) -> list[dict]:
    """Suggerimenti di attività generati da regole deterministiche.

    Param ``solo_miei=true``: filtra solo i record assegnati al collaboratore
    loggato (polizze/sinistri/anagrafiche con ``collaboratore_id == user.id``).
    """
    now = datetime.now(timezone.utc)
    items: list[dict] = []
    # Pre-filtro per collaboratore loggato
    extra_filter: dict = {}
    if solo_miei and user.get("id"):
        extra_filter["collaboratore_id"] = user["id"]

    # 1) Polizze scadute non rinnovate (≤30gg)
    soon = (now + timedelta(days=30)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    async for p in db.polizze.find({
        "stato": {"$in": ["attiva", "in_emissione"]},
        "scadenza": {"$gte": today, "$lte": soon},
        **extra_filter,
    }, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "scadenza": 1,
        "premio_lordo": 1, "ramo": 1}).limit(15):
        items.append({
            "tipo": "rinnovo_imminente",
            "priorita": "alta",
            "titolo": f"Rinnovo: {p['numero_polizza']}",
            "descrizione": f"Polizza in scadenza il {p['scadenza']} ({p.get('ramo','—')}). Contattare cliente.",
            "anagrafica_id": p.get("contraente_id"),
            "polizza_id": p.get("id"),
            "azione_suggerita": "chiama_o_email",
        })

    # 2) Sinistri aperti da oltre 90 giorni
    ninety = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    async for s in db.sinistri.find({
        "stato": "aperto", "data_denuncia": {"$lte": ninety},
        **extra_filter,
    }, {"_id": 0, "id": 1, "numero_sinistro": 1, "contraente_id": 1, "data_denuncia": 1}).limit(15):
        items.append({
            "tipo": "sinistro_lento",
            "priorita": "alta",
            "titolo": f"Sinistro fermo: {s['numero_sinistro']}",
            "descrizione": f"Aperto dal {s['data_denuncia']} senza progressi. Sollecitare liquidatore.",
            "anagrafica_id": s.get("contraente_id"),
            "sinistro_id": s.get("id"),
            "azione_suggerita": "sollecita_compagnia",
        })

    # 3) Polizze CASA private senza catastrofale
    async for p in db.polizze.find({
        "stato": {"$in": ["attiva", "in_emissione"]},
        "ramo": {"$regex": "CASA|GLOBAL", "$options": "i"},
        "catastrofale": {"$ne": True},
        **extra_filter,
    }, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "ramo": 1}).limit(10):
        items.append({
            "tipo": "upsell_catastrofale",
            "priorita": "media",
            "titolo": f"Upsell catastrofale: {p['numero_polizza']}",
            "descrizione": "Polizza CASA senza garanzia catastrofale. Proporre estensione (terremoto/alluvione).",
            "anagrafica_id": p.get("contraente_id"),
            "polizza_id": p.get("id"),
            "azione_suggerita": "proponi_upgrade",
        })

    # 4) Aziende senza catastrofale di legge (D.Lgs ICAT 2024)
    aziende_ids = []
    async for a in db.anagrafiche.find({"tipo": "persona_giuridica"}, {"_id": 0, "id": 1}):
        aziende_ids.append(a["id"])
    if aziende_ids:
        async for p in db.polizze.find({
            "contraente_id": {"$in": aziende_ids},
            "stato": {"$in": ["attiva", "in_emissione"]},
            "catastrofale": {"$ne": True},
            **extra_filter,
        }, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1}).limit(10):
            items.append({
                "tipo": "obbligo_catastrofale_azienda",
                "priorita": "alta",
                "titolo": f"OBBLIGO LEGGE: {p['numero_polizza']}",
                "descrizione": "Cliente AZIENDA senza polizza catastrofale obbligatoria (D.Lgs ICAT). Adeguare.",
                "anagrafica_id": p.get("contraente_id"),
                "polizza_id": p.get("id"),
                "azione_suggerita": "vendita_catastrofale_legge",
            })

    # 5) Clienti fedeli (≥10 anni con noi) → ringraziare/upgrade
    ten_years_ago = (now - timedelta(days=365 * 10)).isoformat()
    n_fedeli = 0
    async for a in db.anagrafiche.find({
        "created_at": {"$lte": ten_years_ago},
    }, {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1, "created_at": 1}).limit(10):
        nome = a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip()
        # solo se ha almeno una polizza attiva
        if await db.polizze.count_documents({
            "contraente_id": a["id"], "stato": {"$in": ["attiva", "in_emissione"]},
        }) == 0:
            continue
        anni = (now - datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))).days // 365
        items.append({
            "tipo": "cliente_fedele",
            "priorita": "media",
            "titolo": f"Cliente fedele da {anni} anni: {nome}",
            "descrizione": f"Cliente con noi da {anni} anni. Ringraziare con sconto fedeltà o proporre upgrade premium.",
            "anagrafica_id": a["id"],
            "azione_suggerita": "premia_fedelta",
        })
        n_fedeli += 1
        if n_fedeli >= 10:
            break

    # 6) Polizze NON AUTO ferme da oltre 5 anni (casa/infortuni/vita ecc.)
    five_y = (now - timedelta(days=365 * 5)).isoformat()
    async for p in db.polizze.find({
        "stato": {"$in": ["attiva", "in_emissione"]},
        "ramo": {"$not": {"$regex": "AUTO|RCA", "$options": "i"}},
        "$or": [
            {"updated_at": {"$lte": five_y}},
            {"updated_at": {"$exists": False}},
        ],
        **extra_filter,
    }, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "ramo": 1,
        "updated_at": 1, "decorrenza": 1}).limit(10):
        rif = p.get("updated_at") or p.get("decorrenza", "")
        anni_ferma = "5+"
        try:
            dt = datetime.fromisoformat(str(rif).replace("Z", "+00:00"))
            anni_ferma = (now - dt).days // 365
        except Exception:
            pass
        items.append({
            "tipo": "polizza_ferma_5y",
            "priorita": "alta",
            "titolo": f"Polizza ferma {anni_ferma} anni: {p['numero_polizza']}",
            "descrizione": f"{p.get('ramo','—')} non movimentata da oltre 5 anni. Garanzie/massimali probabilmente obsoleti. Check-up urgente.",
            "anagrafica_id": p.get("contraente_id"),
            "polizza_id": p.get("id"),
            "azione_suggerita": "revisione_polizza",
        })

    # 7) Clienti con ≥3 sinistri ultimo anno → revisione tariffa/franchigie
    one_y = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    agg_sin = await db.sinistri.aggregate([
        {"$match": {"data_avvenimento": {"$gte": one_y}}},
        {"$group": {"_id": "$contraente_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gte": 3}}},
        {"$sort": {"n": -1}}, {"$limit": 10},
    ]).to_list(10)
    cid_to_name = {a["id"]: (a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip())
                    async for a in db.anagrafiche.find(
                       {"id": {"$in": [s["_id"] for s in agg_sin if s["_id"]]}},
                       {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    for s in agg_sin:
        items.append({
            "tipo": "molti_sinistri",
            "priorita": "alta",
            "titolo": f"⚠️ {s['n']} sinistri ultimo anno: {cid_to_name.get(s['_id'], '—')}",
            "descrizione": f"Cliente ad alta sinistrosità ({s['n']} sinistri in 12 mesi). Rivedere franchigie/massimali o segmentare il rischio.",
            "anagrafica_id": s["_id"],
            "azione_suggerita": "rivedi_franchigie",
        })

    # 8) Polizze Auto con aumento premio significativo (>50€ rispetto a precedente)
    # Heuristic: confrontiamo premio della polizza con la versione precedente
    # (stesso contraente + stesso veicolo/targa, ordinata per decorrenza).
    auto_by_cli: dict = {}
    async for p in db.polizze.find({
        "ramo": {"$regex": "AUTO|RCA", "$options": "i"},
        "stato": {"$in": ["attiva", "in_emissione", "scaduta"]},
    }, {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "premio_lordo": 1,
        "decorrenza": 1, "targa": 1, "stato": 1, "ramo": 1}):
        if not p.get("contraente_id") or not p.get("premio_lordo"):
            continue
        key = (p["contraente_id"], (p.get("targa") or "").upper())
        auto_by_cli.setdefault(key, []).append(p)
    cnt_aumenti = 0
    for (cid, _), pols in auto_by_cli.items():
        if len(pols) < 2 or cnt_aumenti >= 10:
            continue
        pols.sort(key=lambda x: x.get("decorrenza") or "")
        last, prev = pols[-1], pols[-2]
        if last.get("stato") not in ("attiva", "in_emissione"):
            continue
        delta = float(last.get("premio_lordo") or 0) - float(prev.get("premio_lordo") or 0)
        if delta > 50:
            items.append({
                "tipo": "aumento_premio_auto",
                "priorita": "alta",
                "titolo": f"Aumento premio +{delta:.0f} €: {last['numero_polizza']}",
                "descrizione": f"Auto {last.get('targa') or '—'}: premio +{delta:.2f} € rispetto all'anno scorso. Avvisare cliente prima del rinnovo per evitare disdetta.",
                "anagrafica_id": cid,
                "polizza_id": last.get("id"),
                "azione_suggerita": "anticipa_aumento",
            })
            cnt_aumenti += 1


    return items[:limit]


# ---------------------------- RITENUTE ----------------------------
class RitenutaBody(BaseModel):
    anno: int
    collaboratore_id: str
    descrizione: Optional[str] = None
    imponibile: float = 0
    aliquota: float = 20.0      # default ritenuta d'acconto 20%
    importo_ritenuta: float = 0
    causale: Optional[str] = None
    data: Optional[str] = None
    versata: bool = False
    data_versamento: Optional[str] = None
    note: Optional[str] = None


@router.get("/ritenute")
async def list_ritenute(
    anno: Optional[int] = None, collaboratore_id: Optional[str] = None,
    versata: Optional[bool] = None, user=Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if anno: flt["anno"] = anno
    if collaboratore_id: flt["collaboratore_id"] = collaboratore_id
    if versata is not None: flt["versata"] = versata
    items = await db.ritenute.find(flt, {"_id": 0}).sort([("anno", -1), ("data", -1)]).to_list(2000)
    coll_ids = list({r["collaboratore_id"] for r in items if r.get("collaboratore_id")})
    colls = {u["id"]: u async for u in
             db.users.find({"id": {"$in": coll_ids}}, {"_id": 0, "id": 1, "name": 1})}
    for r in items:
        r["collaboratore_nome"] = colls.get(r.get("collaboratore_id", ""), {}).get("name")
    return items


@router.get("/ritenute/totali")
async def ritenute_totali(anno: Optional[int] = None, user=Depends(current_user)) -> dict:
    """Totali ritenute per anno e collaboratore."""
    match: dict = {}
    if anno: match["anno"] = anno
    pipe = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {
            "_id": "$collaboratore_id",
            "imponibile_tot": {"$sum": "$imponibile"},
            "ritenuta_tot": {"$sum": "$importo_ritenuta"},
            "n": {"$sum": 1},
            "versata_tot": {"$sum": {"$cond": ["$versata", "$importo_ritenuta", 0]}},
        }},
    ]
    agg = await db.ritenute.aggregate(pipe).to_list(500)
    coll_ids = [r["_id"] for r in agg if r["_id"]]
    colls = {u["id"]: u async for u in
             db.users.find({"id": {"$in": coll_ids}}, {"_id": 0, "id": 1, "name": 1})}
    return {"per_collaboratore": [{
        "collaboratore_id": r["_id"],
        "collaboratore_nome": colls.get(r["_id"], {}).get("name"),
        "imponibile_tot": r["imponibile_tot"],
        "ritenuta_tot": r["ritenuta_tot"],
        "versata_tot": r["versata_tot"],
        "n_record": r["n"],
    } for r in agg]}


@router.post("/ritenute", status_code=201)
async def create_ritenuta(body: RitenutaBody,
                          user=Depends(require_user("admin"))) -> dict:
    doc = {"id": str(uuid.uuid4()), **body.model_dump(), "created_at": _now_iso()}
    # Calcolo auto importo_ritenuta se 0
    if not doc.get("importo_ritenuta") and doc.get("imponibile"):
        doc["importo_ritenuta"] = round(
            float(doc["imponibile"]) * float(doc.get("aliquota") or 0) / 100.0, 2,
        )
    await db.ritenute.insert_one(doc)
    return doc


@router.put("/ritenute/{rid}")
async def update_ritenuta(rid: str, body: RitenutaBody,
                          user=Depends(require_user("admin"))) -> dict:
    data = body.model_dump()
    if not data.get("importo_ritenuta") and data.get("imponibile"):
        data["importo_ritenuta"] = round(
            float(data["imponibile"]) * float(data.get("aliquota") or 0) / 100.0, 2,
        )
    data["updated_at"] = _now_iso()
    res = await db.ritenute.update_one({"id": rid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Ritenuta non trovata")
    return await db.ritenute.find_one({"id": rid}, {"_id": 0})


@router.delete("/ritenute/{rid}")
async def delete_ritenuta(rid: str, user=Depends(require_user("admin"))) -> dict:
    res = await db.ritenute.delete_one({"id": rid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Ritenuta non trovata")
    return {"ok": True}



# ============= ASSISTENTE PERSONALE AI (Claude Sonnet 4.6) =============
@router.post("/assistente-personale/genera-consiglio")
async def genera_consiglio_ai(
    body: dict, user=Depends(current_user),
) -> dict:
    """Genera un consiglio narrativo in italiano per un cliente specifico
    usando Claude Sonnet 4.6 via Emergent LLM key.

    Body: ``{anagrafica_id: str, contesto_extra?: str}``
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    aid = body.get("anagrafica_id")
    if not aid:
        raise HTTPException(400, "anagrafica_id obbligatorio")
    # Carico insights del cliente (riusiamo la funzione esistente)
    ins = await cliente_insights(aid, user)

    ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
    nome = ana.get("ragione_sociale") or f"{ana.get('cognome','')} {ana.get('nome','')}".strip()

    # Mini contesto strutturato
    prompt_ctx = f"""Cliente: {nome} ({ana.get('tipo','persona_fisica')})
Cliente da: {ins['cliente_da_mesi']} mesi
Polizze attive: {ins['polizze_attive']}
Premio totale attivo: € {ins['premio_attivo_totale']:.2f}
Sinistri totali: {ins['sinistri_totali']} · ultimo anno: {ins['sinistri_ultimo_anno']} · aperti: {ins['sinistri_aperti']}
Polizze ferme >12 mesi: {len(ins['polizze_ferme_oltre_12m'])}
Polizze sanitarie: {ins['polizze_sanitarie']}
Ultima interazione marketing: {ins.get('ultima_interazione_marketing') or 'mai'}
Suggerimenti automatici già rilevati: {[s['testo'] for s in ins['suggerimenti']]}
Contesto extra dell'operatore: {body.get('contesto_extra','')}"""

    system_msg = (
        "Sei un assistente esperto di vendite assicurative in Italia. "
        "Parli in italiano professionale ma amichevole. "
        "Dato il profilo cliente, scrivi 3-5 frasi che indicano: "
        "(1) come si presenta il cliente in sintesi, "
        "(2) un'azione commerciale concreta da fare (upsell/cross-sell/check-up/contatto), "
        "(3) entro quando agire e con quale canale (telefono/email/whatsapp). "
        "Sii specifico e fattuale. Non inventare dati. Mai più di 100 parole."
    )

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(503, "EMERGENT_LLM_KEY non configurata")

    try:
        chat = LlmChat(
            api_key=key,
            session_id=f"assistente-{aid}-{user.get('id')}",
            system_message=system_msg,
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt_ctx))
        # resp è una stringa col testo della risposta
        testo = str(resp) if resp else "(nessuna risposta dall'AI)"
    except Exception as e:
        raise HTTPException(503, f"Errore Claude: {e}")

    # Log nel diario cliente
    await db.diario_cliente.insert_one({
        "id": str(uuid.uuid4()),
        "anagrafica_id": aid,
        "tipo": "ai_suggerimento",
        "data": _now_iso(),
        "operatore_id": user.get("id"),
        "contenuto": testo,
        "fonte": "assistente_personale",
    })
    return {"anagrafica_id": aid, "consiglio": testo, "contesto": ins}


# NOTE: trattative endpoints moved to routes/commerciale.py
