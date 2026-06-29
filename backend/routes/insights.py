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


# ---------------------------- TAG CATASTROFALE AUTO ----------------------------
def _detect_catastrofale(polizza: dict) -> bool:
    """Rileva automaticamente se una polizza include garanzie catastrofali
    (terremoto, alluvione, inondazione, eventi catastrofali, sovraccarico neve)."""
    keywords = ["TERREMOT", "ALLUVION", "INONDAZ", "CATASTROF", "SISMA",
                "FRAN", "SOVRACCAR", "EVENTI_NATUR"]
    haystacks = []
    if polizza.get("garanzie"):
        for g in polizza["garanzie"]:
            if isinstance(g, dict):
                haystacks.append((g.get("nome") or "") + " " + (g.get("descrizione") or ""))
            else:
                haystacks.append(str(g))
    if polizza.get("ramo"): haystacks.append(polizza["ramo"])
    if polizza.get("prodotto"): haystacks.append(polizza["prodotto"])
    if polizza.get("note"): haystacks.append(polizza.get("note") or "")
    text = " ".join(haystacks).upper()
    return any(k in text for k in keywords)


@router.get("/polizze/{pid}/check-catastrofale")
async def check_catastrofale(pid: str, user=Depends(current_user)) -> dict:
    p = await db.polizze.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Polizza non trovata")
    has = _detect_catastrofale(p)
    if p.get("catastrofale") != has:
        await db.polizze.update_one({"id": pid}, {"$set": {"catastrofale": has}})
    return {"polizza_id": pid, "catastrofale": has}


@router.post("/polizze/check-catastrofale-bulk")
async def check_catastrofale_bulk(user=Depends(require_user("admin", "collaboratore"))) -> dict:
    """Scansiona TUTTE le polizze attive e aggiorna il flag ``catastrofale``."""
    updated = 0
    total = 0
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "ramo": 1, "prodotto": 1,
                                        "garanzie": 1, "note": 1, "catastrofale": 1}):
        total += 1
        has = _detect_catastrofale(p)
        if p.get("catastrofale") != has:
            await db.polizze.update_one({"id": p["id"]}, {"$set": {"catastrofale": has}})
            updated += 1
    return {"total": total, "updated": updated}


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


# ---------------------------- IL CERVELLO (AI) ----------------------------
@router.get("/cervello/suggerimenti")
async def cervello_suggerimenti(
    limit: int = 30, user=Depends(current_user),
) -> list[dict]:
    """Suggerimenti di attività generati da regole deterministiche su
    polizze ferme, clienti senza interazioni, sinistri aperti vecchi,
    rinnovi imminenti, catastrofali mancanti.
    """
    now = datetime.now(timezone.utc)
    items: list[dict] = []

    # 1) Polizze scadute non rinnovate (≤30gg)
    soon = (now + timedelta(days=30)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    async for p in db.polizze.find({
        "stato": {"$in": ["attiva", "in_emissione"]},
        "scadenza": {"$gte": today, "$lte": soon},
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


# ============= TRATTATIVE =============
class TrattativaBody(BaseModel):
    anagrafica_id: str
    titolo: str
    descrizione: Optional[str] = None
    ramo: Optional[str] = None
    compagnia_di_provenienza: Optional[str] = None
    compagnia_target_id: Optional[str] = None
    data_scadenza_corrente: Optional[str] = None  # scadenza polizza concorrente
    premio_corrente: float = 0
    premio_proposto: float = 0
    stato: str = "aperta"  # aperta | proposta_inviata | in_attesa | vinta | persa
    note: Optional[str] = None
    visibili_cliente: bool = False
    collaboratore_id: Optional[str] = None


@router.get("/trattative")
async def list_trattative(
    stato: Optional[str] = None, anagrafica_id: Optional[str] = None,
    user=Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if stato: flt["stato"] = stato
    if anagrafica_id: flt["anagrafica_id"] = anagrafica_id
    items = await db.trattative.find(flt, {"_id": 0}).sort("created_at", -1).to_list(2000)
    ana_ids = list({t["anagrafica_id"] for t in items})
    anas = {a["id"]: a async for a in db.anagrafiche.find(
        {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1})}
    for t in items:
        a = anas.get(t["anagrafica_id"], {})
        t["anagrafica_nome"] = a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip()
    return items


@router.post("/trattative", status_code=201)
async def create_trattativa(body: TrattativaBody,
                            user=Depends(require_user("admin", "collaboratore", "dipendente"))) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        **body.model_dump(),
        "collaboratore_id": body.collaboratore_id or user.get("id"),
        "created_at": _now_iso(),
    }
    await db.trattative.insert_one(doc)
    return doc


@router.put("/trattative/{tid}")
async def update_trattativa(tid: str, body: TrattativaBody,
                            user=Depends(require_user("admin", "collaboratore", "dipendente"))) -> dict:
    data = body.model_dump()
    data["updated_at"] = _now_iso()
    res = await db.trattative.update_one({"id": tid}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Trattativa non trovata")
    return await db.trattative.find_one({"id": tid}, {"_id": 0})


@router.delete("/trattative/{tid}")
async def delete_trattativa(tid: str, user=Depends(require_user("admin", "collaboratore"))) -> dict:
    res = await db.trattative.delete_one({"id": tid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Trattativa non trovata")
    return {"ok": True}
