"""Incentivazioni routes — calcolo incentivo per collaboratore sulla nuova produzione.

MVP configurabile basato sulle Iniziative Cattolica (Vita Investimento, Vita
Protezione, DNA Danni). Le fasce/aliquote sono le tabelle dei PDF; l'obiettivo è
di Agenzia e viene ripartito tra i collaboratori in proporzione alla produzione.
Prefisso completo: /api/incentivazioni/...
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from database import db
from db_models import _now_iso
from auth import current_user, require_user

router = APIRouter()

# Annualizzazione del premio netto in base al frazionamento (premio_netto è per rata)
FRAZ_MULT = {
    "annuale": 1, "semestrale": 2, "quadrimestrale": 3,
    "trimestrale": 4, "mensile": 12, "unica": 1,
}

# ------------------------------------------------------------------ FASCE
# Ogni fascia: (min%, max% incluso, {colonna: aliquota%}). max=None => >= min.
CAMPAGNE = {
    "vita_investimento": {
        "nome": "Vita — Bisogno Investimento",
        "tipo_colonna": "rnt",  # colonna scelta dall'utente = incidenza RNT/NP
        "colonne": [
            {"key": "neg", "label": "RNT/NP < 0%"},
            {"key": "c0_20", "label": "RNT/NP 0–20%"},
            {"key": "c20_40", "label": "RNT/NP 20–40%"},
            {"key": "c40_70", "label": "RNT/NP 40–70%"},
            {"key": "c70", "label": "RNT/NP ≥ 70%"},
        ],
        "fasce": [
            {"min": 85, "max": 99, "al": {"neg": None, "c0_20": 0.4, "c20_40": 0.8, "c40_70": 1.1, "c70": 1.5}},
            {"min": 100, "max": 124, "al": {"neg": None, "c0_20": 0.7, "c20_40": 1.5, "c40_70": 2.2, "c70": 3.0}},
            {"min": 125, "max": 149, "al": {"neg": None, "c0_20": 1.0, "c20_40": 2.3, "c40_70": 3.3, "c70": 4.5}},
            {"min": 150, "max": 174, "al": {"neg": 0.2, "c0_20": 1.3, "c20_40": 3.1, "c40_70": 4.4, "c70": 6.0}},
            {"min": 175, "max": 199, "al": {"neg": 1.6, "c0_20": 3.9, "c20_40": 5.5, "c40_70": 7.5, "c70": None}},
            {"min": 200, "max": None, "al": {"neg": 2.1, "c0_20": 5.0, "c20_40": 7.0, "c40_70": 10.0, "c70": None}},
        ],
        "bonus": [],
    },
    "vita_protezione": {
        "nome": "Vita — Bisogno Protezione",
        "tipo_colonna": "livello",  # BASE / TOP
        "colonne": [
            {"key": "base", "label": "Aliquota BASE"},
            {"key": "top", "label": "Aliquota TOP (≥115% rif.)"},
        ],
        "fasce": [
            {"min": 85, "max": 99, "al": {"base": 5.0, "top": 5.0}},
            {"min": 100, "max": 119, "al": {"base": 8.0, "top": 8.0}},
            {"min": 120, "max": 139, "al": {"base": 9.0, "top": 11.0}},
            {"min": 140, "max": 159, "al": {"base": 11.0, "top": 13.0}},
            {"min": 160, "max": 169, "al": {"base": 12.0, "top": 15.0}},
            {"min": 170, "max": 179, "al": {"base": 14.0, "top": 19.0}},
            {"min": 180, "max": 199, "al": {"base": 16.0, "top": 20.0}},
            {"min": 200, "max": None, "al": {"base": 18.0, "top": 22.0}},
        ],
        # Bonus/Malus persistenza (punti % sull'incentivo maturato)
        "bonus": [-10, -7, -5, 0, 5, 7, 10],
    },
    "dna_danni": {
        "nome": "DNA — Danni",
        "tipo_colonna": "livello",  # BASE / PERSONA
        "colonne": [
            {"key": "base", "label": "Aliquota BASE"},
            {"key": "persona", "label": "Aliquota PERSONA (≥110% rif.)"},
        ],
        "fasce": [
            {"min": 85, "max": 99, "al": {"base": 4.0, "persona": 7.0}},
            {"min": 100, "max": 119, "al": {"base": 9.0, "persona": 12.0}},
            {"min": 120, "max": 139, "al": {"base": 11.0, "persona": 14.0}},
            {"min": 140, "max": 159, "al": {"base": 12.0, "persona": 16.0}},
            {"min": 160, "max": 179, "al": {"base": 13.0, "persona": 18.0}},
            {"min": 180, "max": None, "al": {"base": 14.0, "persona": 20.0}},
        ],
        # Bonus attivazione PTF Protezione Beni (punti % sull'incentivo maturato)
        "bonus": [0, 5, 15, 20],
    },
}

REALIZZO_MIN = 85  # soglia minima di accesso all'incentivo (comune a tutte)


def _aliquota(camp_key: str, realizzo: float, colonna: str):
    """Ritorna l'aliquota % per la campagna, in base al realizzo arrotondato e colonna."""
    r = round(realizzo)
    if r < REALIZZO_MIN:
        return 0.0
    for f in CAMPAGNE[camp_key]["fasce"]:
        if r >= f["min"] and (f["max"] is None or r <= f["max"]):
            val = f["al"].get(colonna)
            return float(val) if val is not None else 0.0
    # oltre l'ultima fascia (max None già coperto) → 0
    return 0.0


async def _config_doc():
    doc = await db.incentivazioni_config.find_one({"chiave": "default"}, {"_id": 0})
    return doc or {}


@router.get("/incentivazioni/config")
async def get_config(user: dict = Depends(current_user)) -> dict:
    """Definizioni campagne (fasce/aliquote) + impostazioni salvate (obiettivi, selettori)."""
    saved = await _config_doc()
    return {
        "campagne": CAMPAGNE,
        "realizzo_min": REALIZZO_MIN,
        "settings": saved.get("settings", {}),
    }


@router.put("/incentivazioni/config")
async def put_config(body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    """Salva le impostazioni per campagna: obiettivo, colonna, bonus."""
    settings = body.get("settings") or {}
    await db.incentivazioni_config.update_one(
        {"chiave": "default"},
        {"$set": {"chiave": "default", "settings": settings, "updated_at": _now_iso()}},
        upsert=True,
    )
    return {"ok": True, "settings": settings}


@router.get("/incentivazioni/calcola")
async def calcola(
    data_inizio: str,
    data_fine: str,
    user: dict = Depends(current_user),
) -> dict:
    """Calcola l'incentivo per collaboratore sulla nuova produzione del periodo."""
    if not data_inizio or not data_fine:
        raise HTTPException(400, "data_inizio e data_fine obbligatorie")

    # 1) Mappa prodotto(nome lower) -> campagna dalla libreria prodotti flaggata
    prodmap: dict[str, str] = {}
    persona_names: set[str] = set()   # prodotti DNA "di cui Persona"
    async for p in db.prodotti.find(
        {"incentivazione_campagna": {"$in": list(CAMPAGNE.keys())}},
        {"_id": 0, "nome": 1, "incentivazione_campagna": 1, "incentivazione_persona": 1},
    ):
        if p.get("nome"):
            nm = p["nome"].strip().lower()
            prodmap[nm] = p["incentivazione_campagna"]
            if p.get("incentivazione_persona") and p["incentivazione_campagna"] == "dna_danni":
                persona_names.add(nm)

    # 2) Nuova produzione: polizze con effetto nel periodo, non annullate.
    #    Base incentivabile = premio_netto annualizzato per frazionamento.
    #    Per le polizze SOSTITUITE conta solo la DIFFERENZA di premio netto
    #    (nuovo − sostituito), entrambi annualizzati (può essere negativa).
    def _annuo(pnet, fraz) -> float:
        return round(float(pnet or 0) * FRAZ_MULT.get(fraz or "annuale", 1), 2)

    candidate = []
    refs: set[str] = set()
    async for pol in db.polizze.find(
        {"effetto": {"$gte": data_inizio, "$lte": data_fine}, "stato": {"$ne": "annullata"}},
        {"_id": 0, "id": 1, "prodotto": 1, "premio_netto": 1, "frazionamento": 1,
         "collaboratore_id": 1, "sostituisce_polizza": 1},
    ):
        nome = (pol.get("prodotto") or "").strip().lower()
        if not prodmap.get(nome):
            continue
        candidate.append(pol)
        if pol.get("sostituisce_polizza"):
            refs.add(pol["sostituisce_polizza"])

    # Risolvi in blocco il premio netto annualizzato delle polizze sostituite
    # (il riferimento può essere un id OPPURE un numero polizza).
    sost_annuo: dict[str, float] = {}
    if refs:
        async for sp in db.polizze.find(
            {"$or": [{"id": {"$in": list(refs)}}, {"numero_polizza": {"$in": list(refs)}}]},
            {"_id": 0, "id": 1, "numero_polizza": 1, "premio_netto": 1, "frazionamento": 1},
        ):
            a = _annuo(sp.get("premio_netto"), sp.get("frazionamento"))
            if sp.get("id"):
                sost_annuo[sp["id"]] = a
            if sp.get("numero_polizza"):
                sost_annuo[sp["numero_polizza"]] = a

    #    prod[camp][collab] = base totale campagna; prod_persona[collab] = quota Persona (solo DNA).
    prod: dict[str, dict[str, float]] = {k: {} for k in CAMPAGNE}
    prod_persona: dict[str, float] = {}
    polizze_incluse = 0
    polizze_sostituzioni = 0
    for pol in candidate:
        nome = (pol.get("prodotto") or "").strip().lower()
        camp = prodmap[nome]
        base = _annuo(pol.get("premio_netto"), pol.get("frazionamento"))
        rif = pol.get("sostituisce_polizza")
        if rif:
            base = round(base - sost_annuo.get(rif, 0.0), 2)  # differenza (può essere negativa)
            polizze_sostituzioni += 1
        if base == 0:
            continue
        cid = pol.get("collaboratore_id") or "__nessuno__"
        prod[camp][cid] = round(prod[camp].get(cid, 0.0) + base, 2)
        if camp == "dna_danni" and nome in persona_names:
            prod_persona[cid] = round(prod_persona.get(cid, 0.0) + base, 2)
        polizze_incluse += 1

    # 3) Nomi collaboratori (utenti operatori; fallback libreria collaboratori)
    collab_ids = {cid for camp in prod.values() for cid in camp if cid != "__nessuno__"}
    nomi: dict[str, str] = {}
    if collab_ids:
        async for u in db.users.find({"id": {"$in": list(collab_ids)}}, {"_id": 0, "id": 1, "name": 1}):
            nomi[u["id"]] = u.get("name") or u["id"]
        mancanti = [c for c in collab_ids if c not in nomi]
        if mancanti:
            async for c in db.collaboratori.find({"id": {"$in": mancanti}}, {"_id": 0, "id": 1, "nome": 1}):
                nomi[c["id"]] = c.get("nome") or c["id"]

    # 4) Impostazioni salvate (obiettivo, colonna, bonus per campagna)
    settings = (await _config_doc()).get("settings", {})

    # 5) Calcolo per campagna
    risultato = []
    for camp_key, camp in CAMPAGNE.items():
        st = settings.get(camp_key, {})
        obiettivo = float(st.get("obiettivo") or 0)
        colonna = st.get("colonna") or camp["colonne"][0]["key"]
        bonus = float(st.get("bonus") or 0)
        collab_bases = prod[camp_key]
        totale_base = round(sum(collab_bases.values()), 2)
        realizzo = round(totale_base / obiettivo * 100, 1) if obiettivo > 0 else 0.0
        # Incentivo REALE incassato dall'agenzia (opzionale): se valorizzato viene
        # ripartito tra i collaboratori in proporzione alla loro produzione.
        incentivo_reale = float(st.get("incentivo_reale") or 0)

        def _ripartito(base_val: float) -> float:
            if not incentivo_reale or totale_base == 0:
                return 0.0
            return round(incentivo_reale * base_val / totale_base, 2)

        if camp_key == "dna_danni":
            # DNA: BASE su tutta la produzione + PERSONA (additivo) sulla quota "di cui Persona".
            # Le aliquote sono AUTOMATICHE dalle fasce, in base ai rispettivi realizzo.
            obiettivo_persona = float(st.get("obiettivo_persona") or 0)
            totale_persona = round(sum(prod_persona.get(cid, 0.0) for cid in collab_bases), 2)
            realizzo_persona = round(totale_persona / obiettivo_persona * 100, 1) if obiettivo_persona > 0 else 0.0
            aliquota_base = _aliquota("dna_danni", realizzo, "base")
            aliquota_persona = _aliquota("dna_danni", realizzo_persona, "persona")
            accede = realizzo >= REALIZZO_MIN and aliquota_base > 0
            accede_persona = realizzo_persona >= REALIZZO_MIN and aliquota_persona > 0
            righe = []
            for cid, base in sorted(collab_bases.items(), key=lambda x: -x[1]):
                bp = prod_persona.get(cid, 0.0)
                inc_base = base * aliquota_base / 100.0 if accede else 0.0
                inc_pers = bp * aliquota_persona / 100.0 if accede_persona else 0.0
                incentivo = round((inc_base + inc_pers) * (1 + bonus / 100.0), 2)
                righe.append({
                    "collaboratore_id": None if cid == "__nessuno__" else cid,
                    "collaboratore": "— senza collaboratore —" if cid == "__nessuno__" else nomi.get(cid, cid),
                    "produzione": base,
                    "produzione_persona": bp,
                    "incentivo": incentivo,
                    "incentivo_ripartito": _ripartito(base),
                })
            risultato.append({
                "campagna": camp_key, "nome": camp["nome"], "colonne": camp["colonne"],
                "bonus": bonus, "bonus_opzioni": camp["bonus"],
                "obiettivo": obiettivo, "produzione_totale": totale_base,
                "realizzo": realizzo, "aliquota": aliquota_base, "accede": accede,
                "ha_persona": True,
                "obiettivo_persona": obiettivo_persona, "produzione_persona_totale": totale_persona,
                "realizzo_persona": realizzo_persona, "aliquota_persona": aliquota_persona,
                "accede_persona": accede_persona,
                "incentivo_totale": round(sum(r["incentivo"] for r in righe), 2),
                "incentivo_reale": incentivo_reale,
                "incentivo_ripartito_totale": round(sum(r["incentivo_ripartito"] for r in righe), 2),
                "righe": righe,
            })
            continue

        aliquota = _aliquota(camp_key, realizzo, colonna)
        accede = realizzo >= REALIZZO_MIN and aliquota > 0
        righe = []
        for cid, base in sorted(collab_bases.items(), key=lambda x: -x[1]):
            incentivo = round(base * aliquota / 100.0 * (1 + bonus / 100.0), 2) if accede else 0.0
            righe.append({
                "collaboratore_id": None if cid == "__nessuno__" else cid,
                "collaboratore": "— senza collaboratore —" if cid == "__nessuno__" else nomi.get(cid, cid),
                "produzione": base,
                "incentivo": incentivo,
                "incentivo_ripartito": _ripartito(base),
            })
        risultato.append({
            "campagna": camp_key, "nome": camp["nome"], "colonna": colonna,
            "colonne": camp["colonne"], "bonus": bonus, "bonus_opzioni": camp["bonus"],
            "obiettivo": obiettivo, "produzione_totale": totale_base,
            "realizzo": realizzo, "aliquota": aliquota, "accede": accede, "ha_persona": False,
            "incentivo_totale": round(sum(r["incentivo"] for r in righe), 2),
            "incentivo_reale": incentivo_reale,
            "incentivo_ripartito_totale": round(sum(r["incentivo_ripartito"] for r in righe), 2),
            "righe": righe,
        })

    # 6) Riepilogo consolidato per collaboratore (produzione netta + incentivo su tutte le campagne)
    collab_map: dict[str, dict] = {}
    for c in risultato:
        ck = c["campagna"]
        for row in c["righe"]:
            cid = row["collaboratore_id"] or "__nessuno__"
            e = collab_map.setdefault(cid, {
                "collaboratore_id": row["collaboratore_id"],
                "collaboratore": row["collaboratore"],
                "per_campagna": {},
                "produzione_totale": 0.0,
                "incentivo_totale": 0.0,
                "incentivo_ripartito_totale": 0.0,
            })
            e["per_campagna"][ck] = {
                "produzione": row["produzione"],
                "incentivo": row["incentivo"],
                "incentivo_ripartito": row.get("incentivo_ripartito", 0.0),
            }
            e["produzione_totale"] = round(e["produzione_totale"] + row["produzione"], 2)
            e["incentivo_totale"] = round(e["incentivo_totale"] + row["incentivo"], 2)
            e["incentivo_ripartito_totale"] = round(
                e["incentivo_ripartito_totale"] + row.get("incentivo_ripartito", 0.0), 2)
    grand_prod = round(sum(e["produzione_totale"] for e in collab_map.values()), 2)
    collaboratori = []
    for e in sorted(collab_map.values(), key=lambda x: -x["produzione_totale"]):
        e["quota_pct"] = round(e["produzione_totale"] / grand_prod * 100, 1) if grand_prod else 0.0
        collaboratori.append(e)

    return {
        "data_inizio": data_inizio,
        "data_fine": data_fine,
        "polizze_incluse": polizze_incluse,
        "polizze_sostituzioni": polizze_sostituzioni,
        "prodotti_mappati": len(prodmap),
        "campagne": risultato,
        "collaboratori": collaboratori,
        "produzione_grand_total": grand_prod,
    }
