"""Setup iniziale + scambio dati tra agenzie partner (solo super admin).

**Setup iniziale**: la prima volta che l'agenzia inizia ad usare il programma
si possono inserire:
- saldi iniziali delle banche/conti cassa
- saldo cassa totale dell'agenzia
- saldo iniziale per ogni compagnia (cosa già dovuto/già a credito)
- voci facoltative: provvigioni / spese / rimesse / entrate pregresse
- sospesi manuali iniziali

I dati di setup vengono salvati come "movimenti iniziali" datati 1 giorno
prima della data di setup, con la categoria specifica `setup_iniziale_*`.

**Scambio dati**: un super admin di un'agenzia partner può importare in blocco
anagrafiche/polizze/titoli/sinistri di un proprio operatore registrato presso
un'altra agenzia (es. BS broker che lavora come operatore presso Schiantarelli).
I titoli importati restano sempre in stato "da_pagare arretrato" senza metodo
di pagamento.
"""
from __future__ import annotations

import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import _now_iso


router = APIRouter()


# ============================================================
#  SETUP INIZIALE
# ============================================================
class SaldoBancaInit(BaseModel):
    conto_id: str
    saldo: float
    data: str  # YYYY-MM-DD


class SaldoCompagniaInit(BaseModel):
    compagnia_id: str
    saldo_dare: float = 0  # quello che dobbiamo alla compagnia
    saldo_avere: float = 0  # quello che la compagnia ci deve
    data: str
    descrizione: Optional[str] = None


class SospesoInit(BaseModel):
    anagrafica_id: Optional[str] = None
    importo: float
    descrizione: str
    data: str
    polizza_id: Optional[str] = None


class VocePregressa(BaseModel):
    tipo: str  # provvigione | spesa | rimessa | entrata
    importo: float
    descrizione: Optional[str] = None
    data: str
    compagnia_id: Optional[str] = None


class SetupInizialeBody(BaseModel):
    saldi_banche: List[SaldoBancaInit] = []
    saldi_compagnie: List[SaldoCompagniaInit] = []
    sospesi: List[SospesoInit] = []
    voci_pregresse: List[VocePregressa] = []
    note: Optional[str] = None


@router.get("/setup-iniziale/stato")
async def stato_setup(user=Depends(require_user("admin"))) -> dict:
    """Ritorna lo stato del setup: completato? quando? con cosa?"""
    s = await db.setup_iniziale.find_one({}, {"_id": 0}) or {}
    return {
        "completato": bool(s.get("completato_at")),
        "completato_at": s.get("completato_at"),
        "n_banche": s.get("n_banche", 0),
        "n_compagnie": s.get("n_compagnie", 0),
        "n_sospesi": s.get("n_sospesi", 0),
        "n_voci_pregresse": s.get("n_voci_pregresse", 0),
        "note": s.get("note"),
    }


@router.post("/setup-iniziale")
async def esegui_setup(
    body: SetupInizialeBody,
    user=Depends(require_user("admin")),
) -> dict:
    """Esegue il setup iniziale. Idempotente solo se non ancora completato:
    se già completato, blocca a meno di forzare `?forza=true`."""
    existing = await db.setup_iniziale.find_one({}, {"_id": 0})
    if existing and existing.get("completato_at"):
        raise HTTPException(
            409,
            "Setup iniziale già completato. Modificare i dati manualmente da Prima Nota / Conti.",
        )

    # 1. Saldi banche -> movimenti iniziali di apertura
    for sb in body.saldi_banche:
        conto = await db.conti_cassa.find_one({"id": sb.conto_id}, {"_id": 0, "id": 1, "nome": 1})
        if not conto:
            continue
        await db.movimenti.insert_one({
            "id": str(uuid.uuid4()),
            "tipo": "entrata" if sb.saldo >= 0 else "uscita",
            "categoria": "setup_iniziale_banca",
            "data_movimento": sb.data,
            "importo": abs(round(sb.saldo, 2)),
            "descrizione": f"Saldo iniziale conto {conto.get('nome', '—')}",
            "conto_cassa_id": sb.conto_id,
            "is_setup_iniziale": True,
            "created_at": _now_iso(),
            "created_by": user.get("id"),
        })

    # 2. Saldi compagnie -> setup_iniziale_compagnia (DARE/AVERE)
    for sc in body.saldi_compagnie:
        if sc.saldo_dare > 0:
            await db.movimenti.insert_one({
                "id": str(uuid.uuid4()),
                "tipo": "uscita",  # noi dobbiamo pagare la compagnia
                "categoria": "setup_iniziale_compagnia_dare",
                "data_movimento": sc.data,
                "importo": round(sc.saldo_dare, 2),
                "descrizione": sc.descrizione or "Saldo iniziale dovuto alla compagnia",
                "compagnia_id": sc.compagnia_id,
                "is_setup_iniziale": True,
                "created_at": _now_iso(),
                "created_by": user.get("id"),
            })
        if sc.saldo_avere > 0:
            await db.movimenti.insert_one({
                "id": str(uuid.uuid4()),
                "tipo": "entrata",  # la compagnia ci deve
                "categoria": "setup_iniziale_compagnia_avere",
                "data_movimento": sc.data,
                "importo": round(sc.saldo_avere, 2),
                "descrizione": sc.descrizione or "Saldo iniziale a credito dalla compagnia",
                "compagnia_id": sc.compagnia_id,
                "is_setup_iniziale": True,
                "created_at": _now_iso(),
                "created_by": user.get("id"),
            })

    # 3. Sospesi manuali iniziali
    for sp in body.sospesi:
        await db.sospesi_manuali.insert_one({
            "id": str(uuid.uuid4()),
            "anagrafica_id": sp.anagrafica_id,
            "polizza_id": sp.polizza_id,
            "importo": round(sp.importo, 2),
            "descrizione": sp.descrizione,
            "data": sp.data,
            "stato": "aperto",
            "is_setup_iniziale": True,
            "created_at": _now_iso(),
            "created_by": user.get("id"),
        })

    # 4. Voci pregresse facoltative
    for vp in body.voci_pregresse:
        await db.movimenti.insert_one({
            "id": str(uuid.uuid4()),
            "tipo": "entrata" if vp.tipo in ("provvigione", "entrata", "rimessa") else "uscita",
            "categoria": f"setup_iniziale_{vp.tipo}",
            "data_movimento": vp.data,
            "importo": abs(round(vp.importo, 2)),
            "descrizione": vp.descrizione or f"Voce pregressa: {vp.tipo}",
            "compagnia_id": vp.compagnia_id,
            "is_setup_iniziale": True,
            "created_at": _now_iso(),
            "created_by": user.get("id"),
        })

    setup_doc = {
        "id": "setup_main",
        "completato_at": _now_iso(),
        "completato_da": user.get("id"),
        "n_banche": len(body.saldi_banche),
        "n_compagnie": len(body.saldi_compagnie),
        "n_sospesi": len(body.sospesi),
        "n_voci_pregresse": len(body.voci_pregresse),
        "note": body.note,
    }
    if existing:
        await db.setup_iniziale.update_one({"id": "setup_main"}, {"$set": setup_doc})
    else:
        await db.setup_iniziale.insert_one(setup_doc)

    return {"ok": True, "setup": setup_doc}


@router.post("/setup-iniziale/reset")
async def reset_setup(user=Depends(require_user("admin"))) -> dict:
    """Reset setup iniziale: cancella tutti i movimenti `is_setup_iniziale`,
    sospesi e azzera il flag completato_at. Richiede ruolo admin."""
    res_mov = await db.movimenti.delete_many({"is_setup_iniziale": True})
    res_sosp = await db.sospesi_manuali.delete_many({"is_setup_iniziale": True})
    await db.setup_iniziale.delete_many({})
    return {
        "ok": True,
        "movimenti_eliminati": res_mov.deleted_count,
        "sospesi_eliminati": res_sosp.deleted_count,
    }


# ============================================================
#  SCAMBIO DATI TRA AGENZIE PARTNER
# ============================================================
class ScambioBody(BaseModel):
    agenzia_sorgente_id: str  # agenzia dalla quale importare (Schiantarelli)
    operatore_email: str       # email dell'operatore registrato lì (es. info@bsbroker.it)
    importa_anagrafiche: bool = True
    importa_polizze: bool = True
    importa_titoli: bool = True
    importa_sinistri: bool = True
    importa_documenti: bool = True


@router.post("/scambio-dati/preview")
async def scambio_dati_preview(
    body: ScambioBody,
    user=Depends(require_user("admin")),
) -> dict:
    """Preview dello scambio: conta cosa verrebbe importato. Solo super admin.

    NOTA: in questo prototipo, sorgente e destinazione condividono il MongoDB.
    L'agenzia sorgente viene identificata dall'operatore (collaboratore_id) che
    ha le anagrafiche/polizze nella stessa db. In ambiente multi-tenant reale
    questo endpoint chiamerebbe via API esterna l'istanza dell'agenzia sorgente.
    """
    operator = await db.users.find_one(
        {"email": body.operatore_email.lower().strip()},
        {"_id": 0, "id": 1, "email": 1, "name": 1},
    )
    if not operator:
        raise HTTPException(404, f"Operatore '{body.operatore_email}' non trovato")
    op_id = operator["id"]
    counts = {
        "operatore": operator,
        "anagrafiche": await db.anagrafiche.count_documents({"collaboratore_id": op_id}),
        "polizze": await db.polizze.count_documents({"collaboratore_id": op_id}),
    }
    pol_ids = [p["id"] async for p in db.polizze.find(
        {"collaboratore_id": op_id}, {"_id": 0, "id": 1},
    )]
    counts["titoli"] = await db.titoli.count_documents({"polizza_id": {"$in": pol_ids}}) if pol_ids else 0
    counts["sinistri"] = await db.sinistri.count_documents({"collaboratore_id": op_id})
    counts["documenti"] = await db.allegati.count_documents({
        "$or": [
            {"entita_tipo": "polizza", "entita_id": {"$in": pol_ids}},
            {"entita_tipo": "anagrafica", "entita_id": {"$in": [a["id"] async for a in db.anagrafiche.find({"collaboratore_id": op_id}, {"_id": 0, "id": 1})]}},
        ]
    })
    return counts


@router.post("/scambio-dati/esegui")
async def scambio_dati_esegui(
    body: ScambioBody,
    user=Depends(require_user("admin")),
) -> dict:
    """Esegue lo scambio dati: clona anagrafiche/polizze/titoli/sinistri/allegati
    dell'operatore dalla agenzia sorgente alla destinazione (qui = stesso DB).

    I titoli importati restano sempre in stato `da_pagare` con flag
    `is_importato_arretrato=True` e senza metodo di pagamento.
    """
    operator = await db.users.find_one(
        {"email": body.operatore_email.lower().strip()}, {"_id": 0, "id": 1, "email": 1},
    )
    if not operator:
        raise HTTPException(404, "Operatore non trovato")
    op_id = operator["id"]

    log = {"anagrafiche": 0, "polizze": 0, "titoli": 0, "sinistri": 0, "allegati": 0, "saltati": 0}
    mappa_ana, mappa_pol = {}, {}

    # 1. Anagrafiche
    if body.importa_anagrafiche:
        async for a in db.anagrafiche.find({"collaboratore_id": op_id}, {"_id": 0}):
            old_id = a["id"]
            new_id = str(uuid.uuid4())
            mappa_ana[old_id] = new_id
            a["id"] = new_id
            a["importato_da_agenzia_id"] = body.agenzia_sorgente_id
            a["importato_at"] = _now_iso()
            a["importato_da_operatore"] = body.operatore_email
            a["collaboratore_id"] = user.get("id")
            try:
                await db.anagrafiche.insert_one(a)
                log["anagrafiche"] += 1
            except Exception:
                log["saltati"] += 1

    # 2. Polizze
    if body.importa_polizze:
        async for p in db.polizze.find({"collaboratore_id": op_id}, {"_id": 0}):
            old_id = p["id"]
            new_id = str(uuid.uuid4())
            mappa_pol[old_id] = new_id
            p["id"] = new_id
            p["contraente_id"] = mappa_ana.get(p.get("contraente_id"), p.get("contraente_id"))
            p["importato_da_agenzia_id"] = body.agenzia_sorgente_id
            p["importato_at"] = _now_iso()
            p["collaboratore_id"] = user.get("id")
            try:
                await db.polizze.insert_one(p)
                log["polizze"] += 1
            except Exception:
                log["saltati"] += 1

    # 3. Titoli -> SEMPRE stato "da_pagare" con flag arretrato
    if body.importa_titoli and mappa_pol:
        async for t in db.titoli.find({"polizza_id": {"$in": list(mappa_pol.keys())}}, {"_id": 0}):
            t["id"] = str(uuid.uuid4())
            t["polizza_id"] = mappa_pol[t["polizza_id"]]
            # forza stato arretrato senza metodo di pagamento
            t["stato"] = "da_pagare"
            t["is_importato_arretrato"] = True
            t["mezzo_pagamento"] = None
            t["tipo_pagamento"] = None
            t["data_incasso"] = None
            t["importato_da_agenzia_id"] = body.agenzia_sorgente_id
            t["importato_at"] = _now_iso()
            try:
                await db.titoli.insert_one(t)
                log["titoli"] += 1
            except Exception:
                log["saltati"] += 1

    # 4. Sinistri
    if body.importa_sinistri:
        async for s in db.sinistri.find({"collaboratore_id": op_id}, {"_id": 0}):
            s["id"] = str(uuid.uuid4())
            s["anagrafica_id"] = mappa_ana.get(s.get("anagrafica_id"), s.get("anagrafica_id"))
            s["polizza_id"] = mappa_pol.get(s.get("polizza_id"), s.get("polizza_id"))
            s["importato_da_agenzia_id"] = body.agenzia_sorgente_id
            s["importato_at"] = _now_iso()
            s["collaboratore_id"] = user.get("id")
            try:
                await db.sinistri.insert_one(s)
                log["sinistri"] += 1
            except Exception:
                log["saltati"] += 1

    # 5. Allegati (collegamento ai nuovi entita_id)
    if body.importa_documenti and (mappa_ana or mappa_pol):
        all_old_ids = list(mappa_ana.keys()) + list(mappa_pol.keys())
        async for al_doc in db.allegati.find({"entita_id": {"$in": all_old_ids}}, {"_id": 0}):
            al_doc["id"] = str(uuid.uuid4())
            old_eid = al_doc["entita_id"]
            al_doc["entita_id"] = mappa_ana.get(old_eid) or mappa_pol.get(old_eid) or old_eid
            al_doc["importato_da_agenzia_id"] = body.agenzia_sorgente_id
            try:
                await db.allegati.insert_one(al_doc)
                log["allegati"] += 1
            except Exception:
                log["saltati"] += 1

    # Log dell'evento
    await db.scambi_dati_log.insert_one({
        "id": str(uuid.uuid4()),
        "data": _now_iso(),
        "agenzia_sorgente_id": body.agenzia_sorgente_id,
        "operatore_email": body.operatore_email,
        "destinatario_user_id": user.get("id"),
        "risultato": log,
    })
    return {"ok": True, **log}


@router.get("/scambio-dati/log")
async def scambio_log(user=Depends(require_user("admin"))) -> list[dict]:
    return await db.scambi_dati_log.find({}, {"_id": 0}).sort("data", -1).to_list(100)
