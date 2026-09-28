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
                       tutti: bool = False, user=Depends(current_user)) -> dict:
    """Classifica clienti per provvigioni generate nell'anno (Pareto 80/20).

    Fonte reale: titoli con data_incasso nell'anno (stessa base della sezione
    Premi/Provvigioni). `tutti=true` → carica TUTTI i clienti attivi (no limite).
    """
    now = datetime.now(timezone.utc)
    anno = anno or now.year
    inizio = f"{anno}-01-01"
    fine = f"{anno}-12-31"

    # Polizze: mappa polizza→contraente, prima decorrenza e conteggio attive per cliente
    pols = await db.polizze.find(
        {}, {"_id": 0, "id": 1, "contraente_id": 1, "stato": 1, "decorrenza": 1, "effetto": 1},
    ).to_list(80000)
    pol_to_ana: dict[str, str] = {}
    n_pol_attive: dict[str, int] = {}
    prima_decorrenza: dict[str, str] = {}
    active_clients: set[str] = set()
    for p in pols:
        pid = p["id"]
        cid = p.get("contraente_id")
        pol_to_ana[pid] = cid
        if not cid:
            continue
        if p.get("stato") in ("attiva", "in_emissione"):
            n_pol_attive[cid] = n_pol_attive.get(cid, 0) + 1
            active_clients.add(cid)
        dec = (p.get("decorrenza") or p.get("effetto") or "")[:10]
        if dec and (cid not in prima_decorrenza or dec < prima_decorrenza[cid]):
            prima_decorrenza[cid] = dec

    # Aggrega provvigioni e premi netti REALI dai titoli incassati nell'anno
    bucket_prov: dict[str, float] = {}
    bucket_netto: dict[str, float] = {}
    async for t in db.titoli.find({
        "data_incasso": {"$gte": inizio, "$lte": fine},
        "stato": {"$ne": "stornato"},
    }, {"_id": 0, "polizza_id": 1, "provvigioni": 1, "importo_netto": 1}):
        cid = pol_to_ana.get(t.get("polizza_id"))
        if not cid:
            continue
        bucket_prov[cid] = bucket_prov.get(cid, 0) + float(t.get("provvigioni") or 0)
        bucket_netto[cid] = bucket_netto.get(cid, 0) + float(t.get("importo_netto") or 0)

    # SOLO clienti con polizze attive (esclude RAPPEL e simili senza portafoglio attivo)
    all_ids = set(active_clients)
    ranked_ids = sorted(all_ids, key=lambda c: bucket_prov.get(c, 0.0), reverse=True)
    if not tutti:
        ranked_ids = ranked_ids[:limit]

    anas = {a["id"]: a async for a in db.anagrafiche.find(
        {"id": {"$in": ranked_ids}},
        {"_id": 0, "id": 1, "ragione_sociale": 1, "cognome": 1, "nome": 1,
         "tipo": 1, "created_at": 1})}

    total_all = sum(bucket_prov.get(c, 0.0) for c in active_clients) or 1
    cum = 0.0
    rows = []
    for i, cid in enumerate(ranked_ids):
        prov = bucket_prov.get(cid, 0.0)
        cum += prov
        a = anas.get(cid, {})
        # Anni da cliente: da prima decorrenza polizza (fallback created_at)
        anni_cliente = None
        base_date = prima_decorrenza.get(cid) or (a.get("created_at") or "")[:10]
        if base_date and len(base_date) >= 4:
            try:
                anni_cliente = max(0, now.year - int(base_date[:4]))
            except ValueError:
                anni_cliente = None
        rows.append({
            "rank": i + 1,
            "anagrafica_id": cid,
            "nome": a.get("ragione_sociale") or f"{a.get('cognome','')} {a.get('nome','')}".strip(),
            "tipo": a.get("tipo"),
            "provvigioni_anno": round(prov, 2),
            "premi_netti_anno": round(bucket_netto.get(cid, 0.0), 2),
            "incidenza_pct": round(100 * prov / total_all, 2),
            "incidenza_cumulata_pct": round(100 * cum / total_all, 2),
            "n_polizze_attive": n_pol_attive.get(cid, 0),
            "anni_cliente": anni_cliente,
            "cliente_dal": prima_decorrenza.get(cid),
        })

    # Calcolo soglia Pareto (80/20)
    pareto_idx = next(
        (i for i, r in enumerate(rows) if r["incidenza_cumulata_pct"] >= 80), len(rows) - 1,
    ) + 1
    return {
        "anno": anno,
        "totale_provvigioni": round(total_all if bucket_prov else 0.0, 2),
        "n_clienti_top": len(rows),
        "pareto_80_idx": pareto_idx,
        "tutti": tutti,
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


# ============= MINI BILANCIO PERIODICO =============
_MB_AUTO_RICAVI = [
    ("provvigioni_attive", "Provvigioni Attive"),
    ("rappel", "Rappel / Incentivi Direzione"),
    ("storni_ricavi", "Spese Istruttoria / Storni Ricavi"),
]
_MB_AUTO_COSTI = [
    ("storni_rivalse", "Storni Provvigionali / Rivalse"),
    ("provvigioni_passive", "Provvigioni Passive Collaboratori"),
    ("spese_varie", "Spese Generali / Varie"),
    ("prelievo_soci", "Prelievo Soci"),
    ("compenso_amministratore", "Compenso Amministratore"),
    ("imposte", "Imposte"),
    ("stipendi", "Stipendi"),
    ("ritenute_versate", "Ritenute Versate"),
]
_MB_EXCLUDE = {
    "giroconto", "anticipo", "pagamento_compagnia",
    "setup_iniziale_banca", "setup_iniziale_compagnia_dare", "setup_iniziale_compagnia_avere",
}


def _mb_classify(m: dict, voci_map: dict) -> list[tuple[str, str, float]]:
    """Riclassifica un movimento di Prima Nota -> [(sezione, key, importo)]."""
    vid = m.get("voce_bilancio_id")
    imp = float(m.get("importo") or 0)
    if vid and vid in voci_map:
        return [(voci_map[vid]["tipo"], vid, imp)]
    cat = m.get("categoria") or ""
    tipo = m.get("tipo") or ""
    if cat in _MB_EXCLUDE:
        return []
    out: list[tuple[str, str, float]] = []
    if cat in ("incasso_premio", "incasso_premio_direzione"):
        prov = float(m.get("provvigioni") or 0)
        if prov:
            out.append(("ricavo", "provvigioni_attive", prov))
        sconto = float(m.get("quota_sconto") or 0)
        if sconto:
            out.append(("costo", "storni_rivalse", sconto))
        return out
    if cat == "provvigioni":
        if tipo == "entrata":
            return [("ricavo", "rappel", imp)]
        return [("costo", "provvigioni_passive", imp)]
    if cat in ("ritenuta_compagnia",):
        # Partita di giro col saldo compagnia: non è costo del CE
        return []
    if cat == "pnc":
        # Versamento PNC: la Rivalsa è un costo di storno provvigionale;
        # gli altri tipi (cassa agenti, fondo pensione, gruppo agenti) restano
        # tra le spese generali.
        if (m.get("tipo_pnc") or "") == "rivalsa":
            return [("costo", "storni_rivalse", imp)]
        return [("costo", "spese_varie", imp)]
    if cat in ("sconto_cliente", "rimborso_cliente"):
        return [("costo", "storni_rivalse", imp)]
    if cat == "spese_amministrative":
        return [("costo", "spese_varie", imp)]
    if cat in ("prelievo_soci", "compenso_amministratore", "imposte", "stipendi", "ritenute_versate"):
        return [("costo", cat, imp)]
    # generiche
    if tipo == "entrata":
        return [("ricavo", "storni_ricavi", imp)]
    if tipo == "uscita":
        return [("costo", "spese_varie", imp)]
    return []


async def _mb_compute(dal: str, al: str) -> dict:
    voci = await db.voci_bilancio.find({}, {"_id": 0}).sort([("ordine", 1), ("nome", 1)]).to_list(300)
    voci_map = {v["id"]: v for v in voci}
    righe: dict[str, dict] = {}
    for key, nome in _MB_AUTO_RICAVI:
        righe[key] = {"key": key, "voce": nome, "sezione": "ricavo", "auto": True, "totale": 0.0, "mensile": {}}
    for key, nome in _MB_AUTO_COSTI:
        righe[key] = {"key": key, "voce": nome, "sezione": "costo", "auto": True, "totale": 0.0, "mensile": {}}
    for v in voci:
        if v.get("categoria_sistema"):
            continue  # rappresentata dalle righe automatiche (via categoria)
        righe[v["id"]] = {"key": v["id"], "voce": v["nome"], "sezione": v["tipo"], "auto": False, "totale": 0.0, "mensile": {}}

    cur = db.movimenti.find(
        {"data_movimento": {"$gte": dal, "$lte": al}},
        {"_id": 0, "tipo": 1, "categoria": 1, "importo": 1, "provvigioni": 1,
         "quota_sconto": 1, "voce_bilancio_id": 1, "data_movimento": 1, "tipo_pnc": 1},
    )
    async for m in cur:
        mese = (m.get("data_movimento") or "")[:7]
        for sez, key, amount in _mb_classify(m, voci_map):
            if not amount or key not in righe:
                continue
            r = righe[key]
            r["totale"] += amount
            r["mensile"][mese] = r["mensile"].get(mese, 0.0) + amount

    ricavi = [r for r in righe.values() if r["sezione"] == "ricavo"]
    costi = [r for r in righe.values() if r["sezione"] == "costo"]
    tot_r = sum(r["totale"] for r in ricavi)
    tot_c = sum(r["totale"] for r in costi)

    # --- Stato patrimoniale: saldi conti in tempo reale (cumulato fino ad `al`)
    saldi_conti = []
    async for cc in db.conti_cassa.find({"attivo": True}, {"_id": 0, "id": 1, "nome": 1, "tipo": 1, "saldo_iniziale": 1, "ordine": 1}).sort("ordine", 1):
        agg = await db.movimenti.aggregate([
            {"$match": {"conto_cassa_id": cc["id"], "data_movimento": {"$lte": al}, "is_direzione": {"$ne": True}}},
            {"$group": {"_id": None, "e": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
                        "u": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}}},
        ]).to_list(1)
        e = agg[0]["e"] if agg else 0.0
        u = agg[0]["u"] if agg else 0.0
        saldi_conti.append({"id": cc["id"], "nome": cc["nome"], "tipo": cc.get("tipo"),
                            "saldo": round(float(cc.get("saldo_iniziale") or 0) + e - u, 2)})

    # --- Debiti v/compagnia: premi incassati (netto provvigioni) - versamenti, cumulato
    comp_map = {c["id"]: c.get("nome") or "?" async for c in db.compagnie.find({}, {"_id": 0, "id": 1, "nome": 1})}
    deb_agg = await db.movimenti.aggregate([
        {"$match": {"data_movimento": {"$lte": al}, "categoria": {"$in": ["incasso_premio", "incasso_premio_direzione", "pagamento_compagnia", "ritenuta_compagnia"]}}},
        {"$group": {"_id": "$compagnia_id",
                    "incassato_netto": {"$sum": {"$cond": [
                        {"$in": ["$categoria", ["incasso_premio", "incasso_premio_direzione"]]},
                        {"$subtract": [{"$ifNull": ["$importo", 0]}, {"$ifNull": ["$provvigioni", 0]}]},
                        {"$cond": [{"$eq": ["$categoria", "ritenuta_compagnia"]}, {"$ifNull": ["$importo", 0]}, 0]}]}},
                    "versato": {"$sum": {"$cond": [{"$eq": ["$categoria", "pagamento_compagnia"]}, {"$ifNull": ["$importo", 0]}, 0]}}}},
    ]).to_list(100)
    debiti = []
    for d in deb_agg:
        saldo = round(float(d["incassato_netto"]) - float(d["versato"]), 2)
        if abs(saldo) < 0.005 and not d["_id"]:
            continue
        debiti.append({"compagnia_id": d["_id"], "compagnia": comp_map.get(d["_id"], "Senza compagnia"), "saldo": saldo})
    debiti.sort(key=lambda x: -abs(x["saldo"]))

    rit_agg = await db.movimenti.aggregate([
        {"$match": {"data_movimento": {"$lte": al}, "ritenuta_acconto": {"$gt": 0}}},
        {"$group": {"_id": None, "tot": {"$sum": "$ritenuta_acconto"}}},
    ]).to_list(1)
    ritenute_erario = round(float(rit_agg[0]["tot"]) if rit_agg else 0.0, 2)
    # Ritenute d'acconto versate PER I COLLABORATORI (movimenti dedicati) — voce distinta
    vers_agg = await db.movimenti.aggregate([
        {"$match": {"data_movimento": {"$lte": al}, "categoria": "ritenute_versate"}},
        {"$group": {"_id": None, "tot": {"$sum": {"$ifNull": ["$importo", 0]}}}},
    ]).to_list(1)
    ritenute_collaboratori = round(float(vers_agg[0]["tot"]) if vers_agg else 0.0, 2)

    return {
        "dal": dal, "al": al,
        "ricavi": ricavi, "costi": costi,
        "totale_ricavi": round(tot_r, 2), "totale_costi": round(tot_c, 2),
        "risultato": round(tot_r - tot_c, 2),
        "saldi_conti": saldi_conti,
        "totale_liquidita": round(sum(s["saldo"] for s in saldi_conti), 2),
        "debiti_compagnie": debiti,
        "totale_debiti_compagnie": round(sum(d["saldo"] for d in debiti), 2),
        "ritenute_erario": ritenute_erario,
        "ritenute_collaboratori": ritenute_collaboratori,
    }


@router.get("/mini-bilancio")
async def mini_bilancio(dal: str, al: str, user=Depends(current_user)) -> dict:
    return await _mb_compute(dal, al)


@router.get("/mini-bilancio/dettaglio")
async def mini_bilancio_dettaglio(key: str, dal: str, al: str, user=Depends(current_user)) -> dict:
    voci_map = {v["id"]: v async for v in db.voci_bilancio.find({}, {"_id": 0})}
    rows = []
    cur = db.movimenti.find(
        {"data_movimento": {"$gte": dal, "$lte": al}},
        {"_id": 0, "id": 1, "data_movimento": 1, "tipo": 1, "categoria": 1, "importo": 1,
         "provvigioni": 1, "quota_sconto": 1, "voce_bilancio_id": 1, "descrizione": 1, "mezzo_pagamento": 1, "tipo_pnc": 1},
    ).sort("data_movimento", -1)
    async for m in cur:
        for sez, k, amount in _mb_classify(m, voci_map):
            if k == key and amount:
                rows.append({
                    "id": m.get("id"), "data": m.get("data_movimento"),
                    "descrizione": m.get("descrizione"), "categoria": m.get("categoria"),
                    "mezzo_pagamento": m.get("mezzo_pagamento"), "importo": round(amount, 2),
                })
    return {"key": key, "rows": rows, "totale": round(sum(r["importo"] for r in rows), 2)}


@router.get("/mini-bilancio/export")
async def mini_bilancio_export(dal: str, al: str, formato: str = "pdf", user=Depends(current_user)):
    from fastapi.responses import Response
    data = await _mb_compute(dal, al)
    if formato == "xlsx":
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Conto Economico"
        ws.append([f"MINI BILANCIO {dal} → {al}"]); ws["A1"].font = Font(bold=True, size=13)
        ws.append([])
        ws.append(["RICAVI", "Importo €"]); ws[f"A{ws.max_row}"].font = Font(bold=True)
        for r in data["ricavi"]:
            if r["totale"]: ws.append([r["voce"], round(r["totale"], 2)])
        ws.append(["TOTALE RICAVI", data["totale_ricavi"]]); ws[f"A{ws.max_row}"].font = Font(bold=True)
        ws.append([])
        ws.append(["COSTI", "Importo €"]); ws[f"A{ws.max_row}"].font = Font(bold=True)
        for r in data["costi"]:
            if r["totale"]: ws.append([r["voce"], round(r["totale"], 2)])
        ws.append(["TOTALE COSTI", data["totale_costi"]]); ws[f"A{ws.max_row}"].font = Font(bold=True)
        ws.append([])
        ws.append(["RISULTATO ECONOMICO", data["risultato"]]); ws[f"A{ws.max_row}"].font = Font(bold=True, size=12)
        ws.column_dimensions["A"].width = 42; ws.column_dimensions["B"].width = 16
        ws2 = wb.create_sheet("Stato Patrimoniale")
        ws2.append(["SALDI FINANZIARI (al " + al + ")", "Saldo €"]); ws2["A1"].font = Font(bold=True)
        for s in data["saldi_conti"]: ws2.append([s["nome"], s["saldo"]])
        ws2.append(["TOTALE LIQUIDITÀ", data["totale_liquidita"]]); ws2[f"A{ws2.max_row}"].font = Font(bold=True)
        ws2.append([])
        ws2.append(["DEBITI V/COMPAGNIA", "Saldo €"]); ws2[f"A{ws2.max_row}"].font = Font(bold=True)
        for d in data["debiti_compagnie"]: ws2.append([d["compagnia"], d["saldo"]])
        ws2.append(["TOTALE DA VERSARE", data["totale_debiti_compagnie"]]); ws2[f"A{ws2.max_row}"].font = Font(bold=True)
        ws2.append(["Ritenute d'Acconto & Erario", data["ritenute_erario"]])
        ws2.column_dimensions["A"].width = 42; ws2.column_dimensions["B"].width = 16
        buf = io.BytesIO(); wb.save(buf)
        return Response(buf.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=mini_bilancio_{dal}_{al}.xlsx"})
    # PDF
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm)
    fe = lambda v: f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    el = [Paragraph(f"<b>MINI BILANCIO PERIODICO</b> — {dal} → {al}", styles["Title"]), Spacer(1, 6)]

    def tbl(title, rows, tot_label, tot, color):
        data_rows = [[title, "Importo"]] + [[r["voce"], fe(r["totale"])] for r in rows if r["totale"]]
        data_rows.append([tot_label, fe(tot)])
        t = Table(data_rows, colWidths=[120 * mm, 45 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, -1), (-1, -1), colors.whitesmoke),
        ]))
        return t

    el.append(tbl("RICAVI", data["ricavi"], "TOTALE RICAVI", data["totale_ricavi"], colors.HexColor("#047857")))
    el.append(Spacer(1, 8))
    el.append(tbl("COSTI", data["costi"], "TOTALE COSTI", data["totale_costi"], colors.HexColor("#b91c1c")))
    el.append(Spacer(1, 8))
    ris = Table([[f"RISULTATO ECONOMICO (Utile/Perdita)", fe(data["risultato"])]], colWidths=[120 * mm, 45 * mm])
    ris.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 10),
                             ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                             ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e0f2fe"))]))
    el.append(ris)
    el.append(Spacer(1, 12))
    el.append(Paragraph("<b>STATO PATRIMONIALE & RECAP FINANZIARIO</b>", styles["Heading2"]))
    sp_rows = [{"voce": s["nome"], "totale": s["saldo"]} for s in data["saldi_conti"]]
    el.append(tbl(f"SALDI FINANZIARI (al {al})", sp_rows, "TOTALE LIQUIDITÀ", data["totale_liquidita"], colors.HexColor("#0369a1")))
    el.append(Spacer(1, 8))
    deb_rows = [{"voce": d["compagnia"], "totale": d["saldo"]} for d in data["debiti_compagnie"]]
    deb_rows.append({"voce": "Ritenute d'Acconto & Erario", "totale": data["ritenute_erario"]})
    el.append(tbl("DEBITI V/COMPAGNIA (Partite di giro)", deb_rows, "TOTALE DA VERSARE",
                  data["totale_debiti_compagnie"] + data["ritenute_erario"], colors.HexColor("#7c3aed")))
    doc.build(el)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=mini_bilancio_{dal}_{al}.pdf"})
