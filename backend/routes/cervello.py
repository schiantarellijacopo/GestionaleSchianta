"""Cervello — Controllo di gestione economico-finanziario dell'agenzia.

Funzionalità:
- Configurazione costi struttura (affitti, utenze, stipendi, marketing, ecc.)
- Analisi P&L per comparto (AUTO, PERSONE, AZIENDE, VITA)
- Top 100 clienti per provvigioni (Pareto 80/20)
- Analisi clientela (mono/multi-comparto, churn rate)
- Upload bilancio annuale (Excel/CSV)
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter(prefix="/cervello", tags=["cervello"])

# Comparti standard agenzia assicurativa
COMPARTI = ["auto", "persone", "aziende", "vita"]
COMPARTO_LABEL = {
    "auto": "Auto", "persone": "Persone (Rami Elementari)",
    "aziende": "Aziende", "vita": "Vita",
}


# Mappa ramo → comparto (semplice classificazione)
def _ramo_to_comparto(ramo: str, prodotto: str = "", contraente_tipo: str = "") -> str:
    r = (ramo or "").upper() + " " + (prodotto or "").upper()
    if "VITA" in r or "INVEST" in r or "TFR" in r:
        return "vita"
    if "AUTO" in r or "RCA" in r or "ARD" in r or "TARGA" in r:
        return "auto"
    if contraente_tipo == "persona_giuridica":
        return "aziende"
    # rami elementari (casa, infortuni, malattia, RC, tutela, viaggio)
    return "persone"


# ============= COSTI AGENZIA =============
class CostiAgenziaBody(BaseModel):
    anno: int
    # Costi fissi annuali
    costi_struttura: float = 0   # affitti, utenze, manutenzione
    stipendi_fissi: float = 0    # dipendenti
    spese_marketing: float = 0
    spese_amministrative: float = 0
    altri_costi: float = 0
    # Ripartizione % costi sui comparti (devono sommare a 100)
    ripartizione: dict = Field(default_factory=lambda: {
        "auto": 40.0, "persone": 30.0, "aziende": 20.0, "vita": 10.0,
    })
    note: Optional[str] = None


@router.get("/costi/{anno}")
async def get_costi(anno: int, user=Depends(current_user)) -> dict:
    doc = await db.cervello_costi.find_one({"anno": anno}, {"_id": 0})
    if not doc:
        return {
            "anno": anno, "costi_struttura": 0, "stipendi_fissi": 0,
            "spese_marketing": 0, "spese_amministrative": 0, "altri_costi": 0,
            "ripartizione": {"auto": 40.0, "persone": 30.0, "aziende": 20.0, "vita": 10.0},
            "totale_costi": 0,
        }
    doc["totale_costi"] = (
        doc.get("costi_struttura", 0) + doc.get("stipendi_fissi", 0)
        + doc.get("spese_marketing", 0) + doc.get("spese_amministrative", 0)
        + doc.get("altri_costi", 0)
    )
    return doc


@router.put("/costi/{anno}")
async def upsert_costi(anno: int, body: CostiAgenziaBody,
                       user=Depends(require_user("admin"))) -> dict:
    data = body.model_dump()
    data["anno"] = anno
    data["updated_at"] = _now_iso()
    rip = data.get("ripartizione") or {}
    tot_rip = sum(float(v) for v in rip.values())
    if tot_rip and abs(tot_rip - 100) > 0.5:
        raise HTTPException(400, f"La ripartizione % deve sommare a 100 (attuale: {tot_rip:.1f})")
    await db.cervello_costi.update_one({"anno": anno}, {"$set": data}, upsert=True)
    return await get_costi(anno, user)


# ============= ANALISI P&L PER COMPARTO =============
@router.get("/analisi-pl")
async def analisi_pl(
    anno: Optional[int] = None,
    user=Depends(current_user),
) -> dict:
    """Conto economico per comparto.

    Per ogni comparto calcola:
        - n_polizze
        - premi_totali
        - provvigioni_totali (dai movimenti contabili categoria=provvigioni)
        - incidenza_perc (su totale provvigioni)
        - resa_media_pezzo (provvigioni / n_polizze)
        - costi_ripartiti
        - utile_netto
        - utile_netto_pezzo
    """
    now = datetime.now(timezone.utc)
    anno = anno or now.year
    inizio = f"{anno}-01-01"
    fine = f"{anno}-12-31"

    # Polizze attive nell'anno + arricchimento tipo anagrafica
    flt = {"$or": [
        {"decorrenza": {"$lte": fine}, "scadenza": {"$gte": inizio}},
        {"stato": {"$in": ["attiva", "in_emissione"]}},
    ]}
    pols = await db.polizze.find(flt, {"_id": 0, "id": 1, "ramo": 1, "prodotto": 1,
                                       "contraente_id": 1, "premio_lordo": 1}).to_list(50000)
    ana_ids = list({p.get("contraente_id") for p in pols if p.get("contraente_id")})
    anag_tipo = {a["id"]: (a.get("tipo") or "persona_fisica")
                 async for a in db.anagrafiche.find(
                     {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "tipo": 1, "tags": 1})}
    async for a in db.anagrafiche.find(
            {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "tags": 1}):
        if any(t.lower() in ("azienda", "condominio") for t in (a.get("tags") or [])):
            anag_tipo[a["id"]] = "persona_giuridica"

    stat = {c: {"n": 0, "premi": 0.0, "provv": 0.0, "polizze_ids": set()} for c in COMPARTI}
    for p in pols:
        c = _ramo_to_comparto(p.get("ramo", ""), p.get("prodotto", ""),
                              anag_tipo.get(p.get("contraente_id"), "persona_fisica"))
        stat[c]["n"] += 1
        stat[c]["premi"] += float(p.get("premio_lordo") or 0)
        stat[c]["polizze_ids"].add(p["id"])

    # Provvigioni reali dai movimenti contabili dell'anno
    pol_to_comp = {p["id"]: _ramo_to_comparto(
        p.get("ramo", ""), p.get("prodotto", ""),
        anag_tipo.get(p.get("contraente_id"), "persona_fisica")) for p in pols}
    async for m in db.movimenti_contabili.find({
        "categoria": "provvigioni",
        "tipo": "entrata",
        "data": {"$gte": inizio, "$lte": fine},
    }, {"_id": 0, "polizza_id": 1, "importo": 1}):
        comp = pol_to_comp.get(m.get("polizza_id"))
        if comp:
            stat[comp]["provv"] += float(m.get("importo") or 0)

    # Se zero provvigioni reali, fallback su stima (5% premio AUTO/PERSONE, 8% AZIENDE/VITA)
    for c, s in stat.items():
        if s["provv"] == 0 and s["premi"] > 0:
            s["provv"] = s["premi"] * (0.08 if c in ("aziende", "vita") else 0.05)

    # Costi
    costi = await get_costi(anno, user)
    totale_costi = float(costi.get("totale_costi") or 0)
    rip = costi.get("ripartizione") or {}
    totale_provv = sum(s["provv"] for s in stat.values())

    out = []
    tot_n = sum(s["n"] for s in stat.values())
    for c in COMPARTI:
        s = stat[c]
        costi_rip = totale_costi * (float(rip.get(c, 0)) / 100.0)
        utile = s["provv"] - costi_rip
        out.append({
            "comparto": c,
            "comparto_label": COMPARTO_LABEL[c],
            "n_polizze": s["n"],
            "incidenza_pezzi_pct": round(100.0 * s["n"] / tot_n, 1) if tot_n else 0,
            "premi_totali": round(s["premi"], 2),
            "provvigioni_totali": round(s["provv"], 2),
            "incidenza_provv_pct": round(100.0 * s["provv"] / totale_provv, 1) if totale_provv else 0,
            "resa_media_pezzo": round(s["provv"] / s["n"], 2) if s["n"] else 0,
            "costi_ripartiti": round(costi_rip, 2),
            "utile_netto": round(utile, 2),
            "utile_pezzo": round(utile / s["n"], 2) if s["n"] else 0,
        })
    return {
        "anno": anno,
        "totale_costi": totale_costi,
        "totale_provvigioni": round(totale_provv, 2),
        "totale_polizze": tot_n,
        "utile_netto_agenzia": round(totale_provv - totale_costi, 2),
        "comparti": out,
    }


# ============= TOP 100 CLIENTI (PARETO) =============
@router.get("/top-clienti")
async def top_clienti(limit: int = 100, anno: Optional[int] = None,
                       user=Depends(current_user)) -> dict:
    """Classifica clienti per provvigioni generate (Pareto 80/20)."""
    now = datetime.now(timezone.utc)
    anno = anno or now.year
    inizio = f"{anno}-01-01"
    fine = f"{anno}-12-31"
    # Map polizza→contraente
    pols = await db.polizze.find({}, {"_id": 0, "id": 1, "contraente_id": 1}).to_list(50000)
    pol_to_ana = {p["id"]: p.get("contraente_id") for p in pols}
    # Aggrega provvigioni per cliente
    bucket: dict[str, float] = {}
    n_per_cli: dict[str, int] = {}
    async for m in db.movimenti_contabili.find({
        "categoria": "provvigioni",
        "data": {"$gte": inizio, "$lte": fine},
    }, {"_id": 0, "polizza_id": 1, "importo": 1, "tipo": 1}):
        ana_id = pol_to_ana.get(m.get("polizza_id"))
        if not ana_id:
            continue
        delta = float(m.get("importo") or 0)
        if m.get("tipo") == "uscita":
            delta = -delta
        bucket[ana_id] = bucket.get(ana_id, 0) + delta
        n_per_cli[ana_id] = n_per_cli.get(ana_id, 0) + 1
    if not bucket:
        # fallback: aggrega per premio polizza (proxy)
        for p in pols:
            ana_id = p.get("contraente_id")
            if ana_id:
                bucket[ana_id] = bucket.get(ana_id, 0) + 0
                n_per_cli[ana_id] = n_per_cli.get(ana_id, 0) + 1
    # Top N
    ranked = sorted(bucket.items(), key=lambda x: x[1], reverse=True)[:limit]
    ids = [r[0] for r in ranked]
    anas = {a["id"]: a async for a in db.anagrafiche.find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1,
         "tipo": 1, "created_at": 1})}
    # Conta polizze attive per cliente
    n_pol_attive: dict[str, int] = {}
    async for p in db.polizze.find(
            {"contraente_id": {"$in": ids}, "stato": {"$in": ["attiva", "in_emissione"]}},
            {"_id": 0, "contraente_id": 1}):
        cid = p["contraente_id"]
        n_pol_attive[cid] = n_pol_attive.get(cid, 0) + 1

    total_all = sum(bucket.values()) or 1
    cum = 0.0
    rows = []
    for i, (ana_id, prov) in enumerate(ranked):
        cum += prov
        a = anas.get(ana_id, {})
        rows.append({
            "rank": i + 1,
            "anagrafica_id": ana_id,
            "nome": a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip(),
            "tipo": a.get("tipo"),
            "provvigioni_anno": round(prov, 2),
            "incidenza_pct": round(100 * prov / total_all, 2),
            "incidenza_cumulata_pct": round(100 * cum / total_all, 2),
            "n_polizze_attive": n_pol_attive.get(ana_id, 0),
            "cliente_da": a.get("created_at"),
        })

    # Calcolo soglia Pareto (80/20)
    pareto_idx = next(
        (i for i, r in enumerate(rows) if r["incidenza_cumulata_pct"] >= 80), len(rows) - 1,
    ) + 1
    return {
        "anno": anno,
        "totale_provvigioni": round(total_all, 2),
        "n_clienti_top": len(rows),
        "pareto_80_idx": pareto_idx,
        "items": rows,
    }


# ============= ANALISI CLIENTELA (mono/multi-comparto) =============
@router.get("/segmentazione")
async def segmentazione_clienti(user=Depends(current_user)) -> dict:
    """Quanti clienti hanno solo 1 comparto vs 2/3/4 comparti."""
    pols = await db.polizze.find({"stato": {"$in": ["attiva", "in_emissione"]}},
                                  {"_id": 0, "contraente_id": 1, "ramo": 1, "prodotto": 1}).to_list(50000)
    ana_ids = list({p.get("contraente_id") for p in pols if p.get("contraente_id")})
    anag_tipo = {a["id"]: (a.get("tipo") or "persona_fisica")
                 async for a in db.anagrafiche.find(
                     {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "tipo": 1, "tags": 1})}

    comparti_per_cliente: dict[str, set[str]] = {}
    for p in pols:
        cid = p.get("contraente_id")
        if not cid:
            continue
        c = _ramo_to_comparto(p.get("ramo", ""), p.get("prodotto", ""),
                              anag_tipo.get(cid, "persona_fisica"))
        comparti_per_cliente.setdefault(cid, set()).add(c)

    breakdown = {"mono_auto": 0, "mono_persone": 0, "mono_aziende": 0, "mono_vita": 0,
                 "due_comparti": 0, "tre_comparti": 0, "quattro_comparti": 0}
    for cid, cset in comparti_per_cliente.items():
        if len(cset) == 1:
            single = next(iter(cset))
            breakdown[f"mono_{single}"] += 1
        elif len(cset) == 2:
            breakdown["due_comparti"] += 1
        elif len(cset) == 3:
            breakdown["tre_comparti"] += 1
        else:
            breakdown["quattro_comparti"] += 1
    return {
        "totale_clienti_con_polizze": len(comparti_per_cliente),
        "breakdown": breakdown,
        "tasso_multi_comparto_pct": round(100.0 * (breakdown["due_comparti"]
                                                    + breakdown["tre_comparti"]
                                                    + breakdown["quattro_comparti"])
                                          / max(1, len(comparti_per_cliente)), 1),
    }


# ============= UPLOAD BILANCIO =============
@router.post("/bilancio/upload")
async def upload_bilancio(
    anno: int, file: UploadFile = File(...),
    user=Depends(require_user("admin")),
) -> dict:
    """Carica un bilancio annuale (CSV: ``voce,importo`` o JSON ``{voce: importo}``).

    Le voci riconosciute popolano automaticamente i costi:
    affitti/utenze→costi_struttura, stipendi/personale→stipendi_fissi,
    marketing/pubblicità→spese_marketing, amministrazione→spese_amministrative.
    """
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 2 MB)")
    text = raw.decode("utf-8", errors="ignore")
    voci: dict[str, float] = {}
    try:
        if text.lstrip().startswith("{"):
            import json
            voci = {k: float(v) for k, v in (json.loads(text) or {}).items()}
        else:
            reader = csv.reader(io.StringIO(text))
            for row in reader:
                if not row or len(row) < 2: continue
                key = row[0].strip().lower()
                try:
                    val = float(row[1].replace(",", "."))
                    voci[key] = val
                except Exception:
                    continue
    except Exception as e:
        raise HTTPException(400, f"Formato bilancio non valido: {e}")

    cs = sum(v for k, v in voci.items() if any(w in k for w in ("affitt", "utenz", "manuten", "ufficio")))
    st = sum(v for k, v in voci.items() if any(w in k for w in ("stipend", "personal", "salar", "contribut")))
    mk = sum(v for k, v in voci.items() if any(w in k for w in ("marketing", "pubblic", "advertis", "promoz")))
    am = sum(v for k, v in voci.items() if any(w in k for w in ("amminist", "consulen", "software", "telefon")))
    altri = sum(v for k, v in voci.items()) - (cs + st + mk + am)

    snap = {
        "id": str(uuid.uuid4()),
        "anno": anno, "raw": voci,
        "totali_estratti": {
            "costi_struttura": cs, "stipendi_fissi": st,
            "spese_marketing": mk, "spese_amministrative": am, "altri_costi": altri,
        },
        "uploaded_at": _now_iso(),
        "uploaded_by": user.get("id"),
    }
    await db.cervello_bilanci.insert_one(snap)

    # Aggiorna costi anno
    body = {
        "anno": anno,
        "costi_struttura": cs, "stipendi_fissi": st,
        "spese_marketing": mk, "spese_amministrative": am, "altri_costi": altri,
        "ripartizione": (await get_costi(anno, user)).get("ripartizione") or {
            "auto": 40.0, "persone": 30.0, "aziende": 20.0, "vita": 10.0,
        },
    }
    await db.cervello_costi.update_one({"anno": anno}, {"$set": body}, upsert=True)
    return {"ok": True, "anno": anno, "voci_lette": len(voci),
            "totali_estratti": snap["totali_estratti"]}


@router.get("/bilanci")
async def list_bilanci(user=Depends(require_user("admin"))) -> list[dict]:
    items = await db.cervello_bilanci.find(
        {}, {"_id": 0, "raw": 0},
    ).sort("uploaded_at", -1).to_list(50)
    return items
