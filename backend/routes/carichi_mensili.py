"""Modulo 'Carichi Mensili / Quietanzamento'.

Gestisce l'import selettivo dei titoli in scadenza, il vaglio con validazione
selettiva, la replica manuale da storico polizza e le regole stringenti di
modifica/cancellazione basate sulla chiusura giornaliera della Prima Nota.

Regole chiave:
- I titoli caricati (via import o replica) partono in stato ``stato_carico=in_attesa``
  e appaiono SOLO nella sezione "Carichi Mensili". Non vengono ancora conteggiati
  nello scadenziario ufficiale.
- La validazione selettiva promuove ``in_attesa → validato``: da quel momento
  entrano nel normale flusso di scadenziario/incasso.
- Non si può eliminare un titolo se il giorno di scadenza (o data_incasso) è
  coperto da una chiusura di Prima Nota (collezione ``chiusure_giorno``) NON
  riaperta. L'amministratore può forzare l'annullamento contabile con lo storno.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import Titolo
from shared import log_attivita

router = APIRouter()


# ============================================================================
# Helpers
# ============================================================================

async def _prima_nota_chiusa(data_iso: str) -> bool:
    """Ritorna True se la Prima Nota del giorno ``data_iso`` è CHIUSA (e non riaperta)."""
    if not data_iso:
        return False
    ch = await db.chiusure_giorno.find_one(
        {"data": str(data_iso)[:10]},
        {"_id": 0, "riaperta_at": 1, "stato": 1},
    )
    if not ch:
        return False
    if ch.get("riaperta_at"):
        return False
    return ch.get("stato") in (None, "chiusa", "confermata")


async def _is_titolo_bloccato(t: dict) -> tuple[bool, str]:
    """Un titolo è bloccato per modifica/cancellazione se è consolidato in
    prima nota chiusa. Ritorna (bloccato, motivo).
    """
    # 1) Se il titolo NON è ancora incassato/coperto, non è bloccato
    stato = t.get("stato")
    if stato not in ("incassato", "coperto", "stornato"):
        # non consolidato → sempre modificabile
        return False, ""
    # 2) Se è incassato/coperto: verifica se la prima nota del giorno è chiusa
    data_rif = t.get("data_incasso") or t.get("data_copertura") or t.get("scadenza")
    chiusa = await _prima_nota_chiusa(str(data_rif or "")[:10])
    if chiusa:
        return True, f"Titolo registrato in Prima Nota chiusa del {data_rif}"
    return False, ""


def _mese_iso(dt_str: str) -> str:
    """Estrae YYYY-MM da una data YYYY-MM-DD."""
    return str(dt_str or "")[:7]


def _mese_corrente() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _mese_offset(offset: int) -> str:
    """Restituisce il mese YYYY-MM con offset (es. +1 = mese successivo)."""
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month + offset
    while m > 12:
        y += 1
        m -= 12
    while m < 1:
        y -= 1
        m += 12
    return f"{y:04d}-{m:02d}"


def _add_period(effetto_iso: str, freq: str) -> str:
    """Aggiunge il periodo del frazionamento a una data ISO.

    freq: annuale/semestrale/quadrimestrale/trimestrale/mensile.
    Ritorna la nuova data in formato YYYY-MM-DD.
    """
    if not effetto_iso:
        return effetto_iso
    try:
        y, m, d = str(effetto_iso)[:10].split("-")
        y, m, d = int(y), int(m), int(d)
    except (ValueError, IndexError):
        return effetto_iso
    months_map = {
        "annuale": 12, "semestrale": 6, "quadrimestrale": 4,
        "trimestrale": 3, "mensile": 1, "bimestrale": 2,
    }
    add = months_map.get((freq or "annuale").lower().strip(), 12)
    m2 = m + add
    y2 = y
    while m2 > 12:
        y2 += 1
        m2 -= 12
    # Gestione fine mese: se il giorno originale non esiste nel mese target, usa l'ultimo giorno
    import calendar
    last_day = calendar.monthrange(y2, m2)[1]
    d2 = min(d, last_day)
    return f"{y2:04d}-{m2:02d}-{d2:02d}"


# ============================================================================
# Endpoint principali
# ============================================================================

@router.get("/carichi-mensili")
async def lista_carichi_mensili(
    stato_carico: str = Query("in_attesa", regex="^(in_attesa|validato|annullato_carico|tutti)$"),
    mese: Optional[str] = Query(None, description="YYYY-MM per filtrare per scadenza"),
    range_filter: Optional[str] = Query(None, regex="^(mese_corrente|mese_successivo|tutti)$"),
    dal: Optional[str] = Query(None), al: Optional[str] = Query(None),
    collaboratore_id: Optional[str] = None,
    user=Depends(current_user),
):
    """Elenco titoli con informazioni arricchite per il modulo Carichi Mensili.

    Ritorna per ogni titolo: dati base + polizza + cliente + compagnia +
    premio precedente stessa polizza + badge sinistri (12 mesi) + operatore.
    """
    match: dict = {}
    if stato_carico != "tutti":
        match["stato_carico"] = stato_carico
    if collaboratore_id:
        match["collaboratore_id"] = collaboratore_id

    # Filtro data scadenza
    if range_filter == "mese_corrente":
        match["scadenza"] = {"$regex": f"^{_mese_corrente()}"}
    elif range_filter == "mese_successivo":
        match["scadenza"] = {"$regex": f"^{_mese_offset(1)}"}
    elif mese:
        match["scadenza"] = {"$regex": f"^{mese}"}
    elif dal and al:
        match["scadenza"] = {"$gte": dal, "$lte": al}

    titoli = await db.titoli.find(match, {"_id": 0}).sort("scadenza", 1).limit(1000).to_list(1000)

    # Batch lookup: polizze + clienti + compagnie
    pol_ids = list({t.get("polizza_id") for t in titoli if t.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find(
        {"id": {"$in": pol_ids}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "prodotto": 1,
         "targa": 1, "frazionamento": 1, "contraente_id": 1, "compagnia_id": 1,
         "premio_lordo": 1},
    )}
    ana_ids = list({p.get("contraente_id") for p in pols.values()})
    anas = {a["id"]: a["ragione_sociale"] async for a in db.anagrafiche.find(
        {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1},
    )}
    cmp_ids = list({p.get("compagnia_id") for p in pols.values() if p.get("compagnia_id")})
    cmps = {c["id"]: c.get("ragione_sociale") or c.get("codice") or "-"
            async for c in db.compagnie.find(
                {"id": {"$in": cmp_ids}},
                {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1})}

    # Sinistri ultimi 12 mesi per polizza
    from dateutil.relativedelta import relativedelta
    da_data = (datetime.now(timezone.utc) - relativedelta(months=12)).strftime("%Y-%m-%d")
    sin_agg = await db.sinistri.aggregate([
        {"$match": {"polizza_id": {"$in": pol_ids}, "data_avvenimento": {"$gte": da_data}}},
        {"$group": {"_id": "$polizza_id", "n": {"$sum": 1}}},
    ]).to_list(1000)
    sin_map = {s["_id"]: s["n"] for s in sin_agg}

    # Utenti (per campo operatore)
    coll_ids = list({t.get("collaboratore_id") for t in titoli if t.get("collaboratore_id")})
    users = {u["id"]: (u.get("name") or u.get("email") or "-")
             async for u in db.users.find(
                 {"id": {"$in": coll_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1})}

    rows = []
    for t in titoli:
        p = pols.get(t.get("polizza_id"), {})
        bloccato, motivo = await _is_titolo_bloccato(t)
        rows.append({
            **t,
            "polizza_numero": p.get("numero_polizza"),
            "polizza_ramo": p.get("ramo"),
            "polizza_prodotto": p.get("prodotto"),
            "polizza_targa": p.get("targa"),
            "frazionamento": p.get("frazionamento") or "annuale",
            "cliente_nome": anas.get(p.get("contraente_id"), ""),
            "compagnia_nome": cmps.get(p.get("compagnia_id"), ""),
            "sinistri_ultimi_12m": sin_map.get(p.get("id"), 0),
            "operatore_nome": users.get(t.get("collaboratore_id"), ""),
            "bloccato": bloccato,
            "motivo_blocco": motivo,
        })
    return {"totale": len(rows), "righe": rows}


class ValidaBody(BaseModel):
    titoli_ids: list[str]


@router.post("/carichi-mensili/valida")
async def valida_carichi(
    body: ValidaBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Promuove i titoli selezionati da 'in_attesa' → 'validato'."""
    if not body.titoli_ids:
        raise HTTPException(400, "Nessun titolo selezionato")
    r = await db.titoli.update_many(
        {"id": {"$in": body.titoli_ids}, "stato_carico": "in_attesa"},
        {"$set": {"stato_carico": "validato",
                  "validato_at": datetime.now(timezone.utc).isoformat(),
                  "validato_da": user.get("id")}},
    )
    await log_attivita(user, "valida_carichi", "titoli", None,
                       f"validati={r.modified_count}")
    return {"ok": True, "validati": r.modified_count}


class AnnullaBody(BaseModel):
    titoli_ids: list[str]
    motivo_mancanza: str  # "Disdettata", "Mezzo Venduto", "Voltura", "Sostituita", "Cliente Trasferito"
    note_carico: Optional[str] = None


@router.post("/carichi-mensili/annulla")
async def annulla_carichi(
    body: AnnullaBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Marca i titoli come 'annullato_carico' (non entrano nello scadenziario)."""
    if not body.titoli_ids or not body.motivo_mancanza:
        raise HTTPException(400, "titoli_ids e motivo_mancanza obbligatori")
    r = await db.titoli.update_many(
        {"id": {"$in": body.titoli_ids}, "stato_carico": "in_attesa"},
        {"$set": {"stato_carico": "annullato_carico",
                  "motivo_mancanza": body.motivo_mancanza,
                  "note_carico": body.note_carico}},
    )
    return {"ok": True, "annullati": r.modified_count}


class ReplicaBody(BaseModel):
    polizza_id: str
    scadenza: Optional[str] = None  # se non fornita, calcolata da ultimo titolo + frazionamento


@router.post("/carichi-mensili/replica-manuale")
async def replica_manuale_titolo(
    body: ReplicaBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Replica l'ultimo titolo della polizza aggiornando data effetto/scadenza."""
    pol = await db.polizze.find_one({"id": body.polizza_id}, {"_id": 0})
    if not pol:
        raise HTTPException(404, "Polizza non trovata")
    # Ultimo titolo di quella polizza (sort per scadenza desc)
    last = await db.titoli.find_one(
        {"polizza_id": body.polizza_id},
        {"_id": 0},
        sort=[("scadenza", -1)],
    )
    if not last:
        raise HTTPException(404, "Nessun titolo precedente su questa polizza — usa creazione manuale standard")

    freq = pol.get("frazionamento") or "annuale"
    old_scad = last.get("scadenza")
    new_scad = body.scadenza or _add_period(old_scad, freq)
    new_effetto = _add_period(last.get("effetto") or old_scad, freq)

    new_titolo = Titolo(
        polizza_id=body.polizza_id,
        numero_titolo=None,
        tipo="rinnovo",
        effetto=new_effetto,
        scadenza=new_scad,
        stato="da_incassare",
        importo_lordo=float(last.get("importo_lordo") or 0),
        importo_netto=float(last.get("importo_netto") or 0),
        imposte=float(last.get("imposte") or 0),
        accessori=float(last.get("accessori") or 0),
        provvigioni=float(last.get("provvigioni") or 0),
        collaboratore_id=last.get("collaboratore_id") or user.get("id"),
        stato_carico="in_attesa",  # va in vaglio
        caricato_da_import=False,
        import_source="manuale_replica",
        premio_precedente=float(last.get("importo_lordo") or 0),
        fonte="manuale",
    )
    await db.titoli.insert_one(new_titolo.model_dump())
    await log_attivita(user, "replica_titolo", "titolo", new_titolo.id,
                       f"da {last.get('id')[:8]} → scad {new_scad}")
    return {"ok": True, "titolo": new_titolo.model_dump(), "premio_precedente": last.get("importo_lordo")}


class UpdateCaricoBody(BaseModel):
    importo_lordo: Optional[float] = None
    importo_netto: Optional[float] = None
    provvigioni: Optional[float] = None
    scadenza: Optional[str] = None
    effetto: Optional[str] = None
    mezzo_pagamento: Optional[str] = None
    note_carico: Optional[str] = None
    motivo_mancanza: Optional[str] = None


@router.put("/carichi-mensili/{titolo_id}")
async def update_carico(
    titolo_id: str, body: UpdateCaricoBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Modifica un titolo. BLOCCATO se prima nota chiusa e titolo consolidato."""
    t = await db.titoli.find_one({"id": titolo_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Titolo non trovato")
    bloccato, motivo = await _is_titolo_bloccato(t)
    if bloccato:
        raise HTTPException(403, f"Modifica bloccata: {motivo}")
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not patch:
        return {"ok": True, "no_op": True}
    await db.titoli.update_one({"id": titolo_id}, {"$set": patch})
    await log_attivita(user, "update_carico", "titolo", titolo_id, str(list(patch.keys())))
    return {"ok": True}


@router.delete("/carichi-mensili/{titolo_id}")
async def delete_carico(
    titolo_id: str,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Elimina un titolo. BLOCCATO se prima nota chiusa e titolo consolidato."""
    t = await db.titoli.find_one({"id": titolo_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Titolo non trovato")
    bloccato, motivo = await _is_titolo_bloccato(t)
    if bloccato:
        raise HTTPException(403, f"Cancellazione bloccata: {motivo}")
    await db.titoli.delete_one({"id": titolo_id})
    await log_attivita(user, "delete_carico", "titolo", titolo_id, "eliminato")
    return {"ok": True}


class ImportManualeBody(BaseModel):
    """Import 'manuale' di una lista di titoli (utile per test o per operatore che
    incolla dati da un file). Ogni titolo entra in ``stato_carico=in_attesa``.
    """
    titoli: list[dict]
    import_source: str = "manuale"


@router.post("/carichi-mensili/import")
async def import_carichi(
    body: ImportManualeBody,
    user=Depends(require_user("admin", "collaboratore")),
):
    """Crea N titoli in stato 'in_attesa'. Ogni item deve avere almeno
    polizza_id, effetto, scadenza, importo_lordo.
    """
    if not body.titoli:
        raise HTTPException(400, "Nessun titolo fornito")
    batch_id = str(uuid.uuid4())
    creati = 0
    errori = []
    for row in body.titoli:
        try:
            # Snapshot premio precedente
            last = await db.titoli.find_one(
                {"polizza_id": row.get("polizza_id"), "stato_carico": "validato"},
                {"_id": 0, "importo_lordo": 1},
                sort=[("scadenza", -1)],
            )
            t = Titolo(
                polizza_id=row["polizza_id"],
                effetto=row.get("effetto") or row.get("scadenza"),
                scadenza=row["scadenza"],
                importo_lordo=float(row.get("importo_lordo") or 0),
                importo_netto=float(row.get("importo_netto") or 0),
                imposte=float(row.get("imposte") or 0),
                provvigioni=float(row.get("provvigioni") or 0),
                collaboratore_id=row.get("collaboratore_id") or user.get("id"),
                stato_carico="in_attesa",
                caricato_da_import=True,
                import_batch_id=batch_id,
                import_source=body.import_source,
                premio_precedente=float(last["importo_lordo"]) if last else None,
                fonte="import_ania" if body.import_source != "manuale" else "manuale",
            )
            await db.titoli.insert_one(t.model_dump())
            creati += 1
        except Exception as e:
            errori.append({"row": row.get("polizza_id"), "errore": str(e)})
    await log_attivita(user, "import_carichi", "titoli", batch_id,
                       f"creati={creati} errori={len(errori)}")
    return {"ok": True, "batch_id": batch_id, "creati": creati, "errori": errori}
