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
- Import Excel/CSV: due step (preview → import) per permettere all'operatore
  di **mappare le colonne del file → campi CRM** con suggerimento automatico
  (fuzzy-match sui nomi colonna comuni).
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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


def _carico_overwritable(t: dict) -> bool:
    """Un titolo esistente è SOVRASCRIVIBILE da un import solo se è un semplice
    'da_incassare' non ancora toccato contabilmente.
    PROTETTI (mai sovrascritti): incassato, stornato, insoluto/sospeso,
    coperto (titolo_coperto) o con data_incasso valorizzata.
    """
    if (t.get("stato") or "da_incassare") != "da_incassare":
        return False
    if t.get("titolo_coperto"):
        return False
    if t.get("data_incasso"):
        return False
    return True


async def _dedup_insert(t: "Titolo") -> str:
    """(Deprecato) non più usato: la dedup avviene in validazione, non all'import."""
    await db.titoli.insert_one(t.model_dump())
    return "created"



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
    compagnia_id: Optional[str] = None,
    ramo: Optional[str] = None,
    mezzo_pagamento: Optional[str] = None,
    tipo_rinnovo: Optional[str] = None,
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
    if mezzo_pagamento:
        match["mezzo_pagamento"] = mezzo_pagamento
    if tipo_rinnovo:
        # tipo_rinnovo su Titolo è il campo "tipo" (rinnovo/nuova/appendice/…)
        match["tipo"] = tipo_rinnovo

    # Filtro data scadenza
    if range_filter == "mese_corrente":
        match["scadenza"] = {"$regex": f"^{_mese_corrente()}"}
    elif range_filter == "mese_successivo":
        match["scadenza"] = {"$regex": f"^{_mese_offset(1)}"}
    elif mese:
        match["scadenza"] = {"$regex": f"^{mese}"}
    elif dal and al:
        match["scadenza"] = {"$gte": dal, "$lte": al}

    # Prefiltro polizze se compagnia/ramo → riduce il set titoli
    if compagnia_id or ramo:
        pol_flt = {}
        if compagnia_id:
            pol_flt["compagnia_id"] = compagnia_id
        if ramo:
            pol_flt["ramo"] = ramo
        pol_ids_pre = [p["id"] async for p in db.polizze.find(pol_flt, {"_id": 0, "id": 1})]
        if not pol_ids_pre:
            return {"totale": 0, "righe": []}
        match["polizza_id"] = {"$in": pol_ids_pre}

    titoli = await db.titoli.find(match, {"_id": 0}).sort("scadenza", 1).limit(1000).to_list(1000)

    # Batch lookup: polizze + clienti + compagnie
    pol_ids = list({t.get("polizza_id") for t in titoli if t.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find(
        {"id": {"$in": pol_ids}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "prodotto": 1,
         "targa": 1, "frazionamento": 1, "contraente_id": 1, "compagnia_id": 1,
         "premio_lordo": 1, "premio_ssn": 1, "stato": 1,
         "data_annullamento": 1, "motivo_annullamento": 1,
         "data_sospensione": 1, "riattivazione_prevista": 1,
         "sostituita_da_polizza_id": 1, "sostituisce_polizza": 1,
         "provvigioni_operatori": 1, "collaboratore_id": 1,
         "note_interne": 1},
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

    # Utenti (per campo operatore) - includo anche i collaboratori storici delle polizze
    coll_ids = {t.get("collaboratore_id") for t in titoli if t.get("collaboratore_id")}
    for p in pols.values():
        for op in (p.get("provvigioni_operatori") or []):
            if op.get("operatore_id"):
                coll_ids.add(op["operatore_id"])
        if p.get("collaboratore_id"):
            coll_ids.add(p["collaboratore_id"])
    users = {u["id"]: (u.get("name") or u.get("email") or "-")
             async for u in db.users.find(
                 {"id": {"$in": list(coll_ids)}}, {"_id": 0, "id": 1, "name": 1, "email": 1})}

    # Lookup polizze sostitutive (se una polizza è stata sostituita, mostra il numero della nuova)
    sostit_ids = list({p.get("sostituita_da_polizza_id") for p in pols.values()
                       if p.get("sostituita_da_polizza_id")})
    sostit_map: dict = {}
    if sostit_ids:
        async for sp in db.polizze.find(
            {"id": {"$in": sostit_ids}},
            {"_id": 0, "id": 1, "numero_polizza": 1, "effetto": 1, "premio_lordo": 1},
        ):
            sostit_map[sp["id"]] = sp


    rows = []
    for t in titoli:
        p = pols.get(t.get("polizza_id"), {})
        bloccato, motivo = await _is_titolo_bloccato(t)
        # Badge variazione: confronto premio precedente vs attuale
        prev = t.get("premio_precedente")
        curr = float(t.get("importo_lordo") or 0)
        variazione_badge = None
        variazione_dettaglio = None
        variazione_delta_euro = None
        variazione_delta_pct = None
        note_auto = None      # nota dedotta automaticamente (non sovrascrive note_carico manuali)
        motivo_dedotto = None # motivo_mancanza dedotto (se non già settato manualmente)

        # ============================================================
        # DEDUZIONE INTELLIGENTE (deterministica) - stato polizza
        # ============================================================
        pol_stato = (p.get("stato") or "attiva").lower()

        # 1) Polizza SOSTITUITA (esiste sostituita_da_polizza_id)
        if p.get("sostituita_da_polizza_id"):
            sp = sostit_map.get(p["sostituita_da_polizza_id"], {})
            variazione_badge = "🔄 Sostituita"
            variazione_dettaglio = (
                f"Sostituita da polizza {sp.get('numero_polizza', 'N/A')}"
                + (f" (effetto {sp.get('effetto', '-')})" if sp.get("effetto") else "")
            )
            motivo_dedotto = "Sostituita"
            note_auto = f"Polizza sostituita da {sp.get('numero_polizza', 'nuova polizza')}"

        # 2) Polizza ANNULLATA / DISDETTATA
        elif pol_stato in ("annullata", "disdettata", "cessata"):
            variazione_badge = "🛑 Disdettata"
            motivo_ann = p.get("motivo_annullamento") or "senza motivo specificato"
            data_ann = p.get("data_annullamento") or "-"
            variazione_dettaglio = f"Polizza annullata il {data_ann}: {motivo_ann}"
            motivo_dedotto = "Disdettata"
            note_auto = f"Disdettata dal {data_ann} — {motivo_ann}"

        # 3) Polizza SOSPESA
        elif pol_stato == "sospesa" or p.get("data_sospensione"):
            variazione_badge = "⏸ Sospesa"
            data_sosp = p.get("data_sospensione") or "-"
            riatt = p.get("riattivazione_prevista")
            variazione_dettaglio = (
                f"Sospesa dal {data_sosp}"
                + (f" · riattivazione prevista {riatt}" if riatt else "")
            )
            motivo_dedotto = "Sospesa"
            note_auto = (f"Polizza sospesa dal {data_sosp}"
                         + (f", riatt. {riatt}" if riatt else ""))

        # 4) Variazione premio (solo se polizza attiva → non ha senso mostrare aumenti su disdette)
        elif prev is not None and prev > 0:
            delta = curr - prev
            pct = (delta / prev) * 100
            variazione_delta_euro = round(delta, 2)
            variazione_delta_pct = round(pct, 1)
            if abs(delta) < 0.01:
                variazione_badge = "🟢 Regolare"
            elif delta > 0:
                variazione_badge = f"🛑 Aumento (+€{delta:.2f})"
                variazione_dettaglio = f"Premio aumentato di €{delta:.2f} ({pct:+.1f}%) rispetto al titolo precedente"
                # Deduzione motivo aumento (indizi non certi ma utili)
                if pct >= 30:
                    note_auto = f"⚠️ Aumento significativo (+{pct:.0f}%): verificare cambio classe BM, guida esperta, sinistri o nuove garanzie"
                elif pct >= 10:
                    note_auto = f"Aumento medio (+{pct:.1f}%): possibile ricalcolo BM/CU o adeguamento tariffario"
            else:
                variazione_badge = f"🔻 Riduzione ({delta:.2f}€)"
                variazione_dettaglio = f"Premio ridotto di €{abs(delta):.2f} ({pct:+.1f}%)"
                if pct <= -20:
                    note_auto = f"Riduzione significativa ({pct:.0f}%): possibile rinegoziazione, calo garanzie o BM migliorato"
        elif prev is None:
            variazione_badge = "🆕 Nuova"
            variazione_dettaglio = "Prima quietanza su questa polizza (nessun premio precedente)"

        # ============================================================
        # Collaboratori storici (dai provvigioni_operatori della polizza)
        # ============================================================
        note_storiche = ""
        provv_operatori = p.get("provvigioni_operatori") or []
        if provv_operatori:
            nomi_collab = []
            for op in provv_operatori:
                nome = op.get("operatore_nome") or users.get(op.get("operatore_id"), "")
                if nome and nome not in nomi_collab:
                    nomi_collab.append(nome)
            if nomi_collab:
                note_storiche = " · ".join(nomi_collab[:3])
                if len(nomi_collab) > 3:
                    note_storiche += f" +{len(nomi_collab) - 3}"

        # ============================================================
        # Provvigioni collaboratore (esclude quota agenzia)
        # ============================================================
        provv_collab = None
        if provv_operatori:
            # Somma delle provvigioni destinate agli operatori (non alla struttura)
            try:
                provv_collab = round(sum(float(op.get("provvigione") or 0)
                                         + float(op.get("provvigione_addizionali") or 0)
                                         for op in provv_operatori), 2)
            except (TypeError, ValueError):
                provv_collab = None

        # ============================================================
        # Servizio sanitario (SSN) - dalla polizza
        # ============================================================
        servizio_sanitario = p.get("premio_ssn")

        # ============================================================
        # Note finali: preserva sempre note_carico manuale + append auto
        # ============================================================
        note_manuale = t.get("note_carico")
        note_finale = None
        if note_manuale and note_auto:
            note_finale = f"{note_manuale}  |  🤖 {note_auto}"
        elif note_manuale:
            note_finale = note_manuale
        elif note_auto:
            note_finale = f"🤖 {note_auto}"

        rows.append({
            **t,
            "polizza_numero": p.get("numero_polizza"),
            "polizza_ramo": p.get("ramo"),
            "polizza_prodotto": p.get("prodotto"),
            "polizza_targa": p.get("targa"),
            "polizza_stato": pol_stato,
            "frazionamento": p.get("frazionamento") or "annuale",
            "data_decorrenza": t.get("effetto"),  # alias per la tabella
            "tipo_rinnovo": t.get("tipo") or "rinnovo",
            "cliente_nome": anas.get(p.get("contraente_id"), ""),
            "compagnia_nome": cmps.get(p.get("compagnia_id"), ""),
            "sinistri_ultimi_12m": sin_map.get(p.get("id"), 0),
            "operatore_nome": users.get(t.get("collaboratore_id"), ""),
            "bloccato": bloccato,
            "motivo_blocco": motivo,
            "variazione_badge": variazione_badge,
            "variazione_dettaglio": variazione_dettaglio,
            "variazione_delta_euro": variazione_delta_euro,
            "variazione_delta_pct": variazione_delta_pct,
            # Nuovi campi enrichment richiesti
            "note_carico": note_finale,
            "note_storiche": note_storiche,
            "servizio_sanitario": servizio_sanitario,
            "provvigioni_collab": provv_collab,
            "motivo_mancanza": t.get("motivo_mancanza") or motivo_dedotto,
        })
    return {"totale": len(rows), "righe": rows}


@router.get("/carichi-mensili/confronto-annuale")
async def confronto_annuale(
    anno: Optional[int] = Query(None, description="Anno corrente da confrontare"),
    mese: Optional[str] = Query(None, description="MM 01-12 opzionale per filtrare per mese di decorrenza"),
    dal: Optional[str] = Query(None, description="Data inizio (YYYY-MM-DD) — confronto per intervallo"),
    al: Optional[str] = Query(None, description="Data fine (YYYY-MM-DD) — confronto per intervallo"),
    user=Depends(current_user),
):
    """Confronto anno precedente vs anno corrente **per data DECORRENZA** dei titoli.

    Due modalità:
    - Per INTERVALLO DATE (dal/al): confronta i titoli nell'intervallo selezionato con
      lo stesso intervallo dell'anno precedente (stesse date meno 1 anno).
    - Per ANNO (+ mese opzionale): confronta anno vs anno-1.

    Accoppia per polizza + stesso mese di decorrenza e segnala confermati / mancanti / nuovi.
    """
    from datetime import date as _date

    def _minus_year(iso: str) -> str:
        d = _date.fromisoformat(iso[:10])
        try:
            return d.replace(year=d.year - 1).isoformat()
        except ValueError:  # 29 feb
            return d.replace(year=d.year - 1, day=28).isoformat()

    if dal and al:
        anno = anno or int(dal[:4])
        anno_prec = anno - 1
        curr_q = {"effetto": {"$gte": dal, "$lte": al}}
        prev_q = {"effetto": {"$gte": _minus_year(dal), "$lte": _minus_year(al)}}
    else:
        if not anno:
            raise HTTPException(400, "Specificare 'anno' oppure l'intervallo 'dal'/'al'")
        anno_prec = anno - 1
        prefix_curr = f"{anno}-{mese.zfill(2) if mese else ''}"
        prefix_prev = f"{anno_prec}-{mese.zfill(2) if mese else ''}"
        curr_q = {"effetto": {"$regex": f"^{prefix_curr}"}}
        prev_q = {"effetto": {"$regex": f"^{prefix_prev}"}}

    # Query titoli anno corrente / precedente
    titoli_curr = await db.titoli.find(curr_q, {"_id": 0}).sort("effetto", 1).to_list(5000)
    titoli_prev = await db.titoli.find(prev_q, {"_id": 0}).sort("effetto", 1).to_list(5000)

    # Batch lookup polizze/anagrafiche/compagnie
    all_pol_ids = list({t.get("polizza_id") for t in (titoli_curr + titoli_prev)
                        if t.get("polizza_id")})
    pols = {p["id"]: p async for p in db.polizze.find(
        {"id": {"$in": all_pol_ids}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "contraente_id": 1,
         "compagnia_id": 1, "stato": 1, "data_annullamento": 1,
         "motivo_annullamento": 1, "data_sospensione": 1,
         "riattivazione_prevista": 1, "sostituita_da_polizza_id": 1,
         "premio_lordo": 1, "effetto": 1, "scadenza": 1, "targa": 1},
    )}
    ana_ids = list({p.get("contraente_id") for p in pols.values()})
    anas = {a["id"]: a.get("ragione_sociale") async for a in db.anagrafiche.find(
        {"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1})}
    cmp_ids = list({p.get("compagnia_id") for p in pols.values() if p.get("compagnia_id")})
    cmps = {c["id"]: c.get("ragione_sociale") or c.get("codice") or "-"
            async for c in db.compagnie.find(
                {"id": {"$in": cmp_ids}},
                {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1})}
    # Lookup polizze SOSTITUTIVE (per messaggio "sostituita da polizza XYZ")
    sostit_ids = list({p.get("sostituita_da_polizza_id") for p in pols.values()
                       if p.get("sostituita_da_polizza_id")})
    sostit_map = {sp["id"]: sp async for sp in db.polizze.find(
        {"id": {"$in": sostit_ids}},
        {"_id": 0, "id": 1, "numero_polizza": 1, "effetto": 1, "premio_lordo": 1})}

    def _mese(dt: str) -> str:
        return (dt or "")[:7]

    def _row(t: Optional[dict], polizza_id: str, tipo_row: str, motivo: str = "",
             dettaglio: str = "", nuova_polizza: Optional[str] = None,
             match_prev: Optional[dict] = None, match_curr: Optional[dict] = None) -> dict:
        p = pols.get(polizza_id, {})
        base_t = t or match_curr or match_prev or {}
        curr = float((match_curr or {}).get("importo_lordo") or 0) if match_curr else 0
        prev = float((match_prev or {}).get("importo_lordo") or 0) if match_prev else 0
        delta = curr - prev if (curr and prev) else None
        return {
            "id": base_t.get("id") or f"missing-{polizza_id}-{tipo_row}",
            "tipo_row": tipo_row,   # "confermato" | "mancante" | "nuovo"
            "motivo": motivo,       # "sostituita" | "annullata" | "sospesa" | "scadenza_cambiata" | "nuova_emissione" | "anomalia"
            "motivo_label": {
                "sostituita": "🔄 Polizza sostituita",
                "annullata": "🛑 Polizza annullata",
                "sospesa": "⏸ Polizza sospesa",
                "scadenza_cambiata": "📅 Scadenza cambiata",
                "nuova_emissione": "✨ Nuova emissione",
                "anomalia": "⚠ Anomalia — verificare",
                "": "🟢 Confermata",
            }.get(motivo, motivo),
            "dettaglio": dettaglio,
            "polizza_id": polizza_id,
            "polizza_numero": p.get("numero_polizza"),
            "polizza_ramo": p.get("ramo"),
            "polizza_targa": p.get("targa"),
            "nuova_polizza_numero": nuova_polizza,
            "cliente_nome": anas.get(p.get("contraente_id")),
            "compagnia_nome": cmps.get(p.get("compagnia_id")),
            "effetto_anno_prec": (match_prev or {}).get("effetto") if match_prev else None,
            "effetto_anno_corr": (match_curr or {}).get("effetto") if match_curr else None,
            "scadenza_anno_prec": (match_prev or {}).get("scadenza"),
            "scadenza_anno_corr": (match_curr or {}).get("scadenza"),
            "premio_anno_prec": prev if prev else None,
            "premio_anno_corr": curr if curr else None,
            "delta_euro": round(delta, 2) if delta is not None else None,
            "delta_pct": round((delta / prev) * 100, 1) if delta is not None and prev else None,
        }

    # Indicizzazione per polizza_id + mese
    def _idx(titoli: list[dict]) -> dict:
        idx: dict[tuple, dict] = {}
        for t in titoli:
            key = (t.get("polizza_id"), _mese(t.get("effetto") or ""))
            if key not in idx:
                idx[key] = t
        return idx

    idx_curr = _idx(titoli_curr)
    idx_prev = _idx(titoli_prev)

    rows: list[dict] = []
    keys_visti: set = set()

    # 1) Titoli anno precedente: cerca corrispondente anno corrente
    for (pid, m), t_prev in idx_prev.items():
        # Cerca titolo corrente sulla stessa polizza (anche in mese diverso)
        t_curr = idx_curr.get((pid, m))
        p = pols.get(pid, {})
        stato_pol = (p.get("stato") or "").lower()

        if not t_curr:
            # cerca altrove nell'anno corrente (mese diverso)
            candidati = [tc for (kp, km), tc in idx_curr.items() if kp == pid]
            t_curr_alt = candidati[0] if candidati else None

            if p.get("sostituita_da_polizza_id"):
                sp = sostit_map.get(p["sostituita_da_polizza_id"], {})
                # Se la polizza sostitutiva ha un titolo anno corrente, mostralo
                titolo_sub_curr = None
                for tc in titoli_curr:
                    if tc.get("polizza_id") == p["sostituita_da_polizza_id"]:
                        titolo_sub_curr = tc
                        break
                rows.append(_row(t_prev, pid, "mancante", "sostituita",
                                 dettaglio=f"Sostituita da polizza {sp.get('numero_polizza', 'N/A')}"
                                           + (f" (decorrenza {sp.get('effetto')})" if sp.get('effetto') else ""),
                                 nuova_polizza=sp.get("numero_polizza"),
                                 match_prev=t_prev, match_curr=titolo_sub_curr))
                if titolo_sub_curr:
                    keys_visti.add((p["sostituita_da_polizza_id"], _mese(titolo_sub_curr.get("effetto") or "")))
            elif stato_pol in ("annullata", "disdettata", "cessata"):
                data_ann = p.get("data_annullamento") or "-"
                motivo_ann = p.get("motivo_annullamento") or "senza motivo specificato"
                rows.append(_row(t_prev, pid, "mancante", "annullata",
                                 dettaglio=f"Annullata il {data_ann}: {motivo_ann}",
                                 match_prev=t_prev))
            elif stato_pol == "sospesa" or p.get("data_sospensione"):
                data_sosp = p.get("data_sospensione") or "-"
                riatt = p.get("riattivazione_prevista")
                rows.append(_row(t_prev, pid, "mancante", "sospesa",
                                 dettaglio=f"Sospesa dal {data_sosp}"
                                           + (f" · riattivazione {riatt}" if riatt else ""),
                                 match_prev=t_prev))
            elif t_curr_alt:
                # esiste ma in mese diverso → scadenza cambiata
                rows.append(_row(t_prev, pid, "mancante", "scadenza_cambiata",
                                 dettaglio=f"Decorrenza spostata da {t_prev.get('effetto')} a "
                                           f"{t_curr_alt.get('effetto')} (mese cambiato)",
                                 match_prev=t_prev, match_curr=t_curr_alt))
                keys_visti.add((pid, _mese(t_curr_alt.get("effetto") or "")))
            else:
                # Nessun motivo dedotto → segnala anomalia
                rows.append(_row(t_prev, pid, "mancante", "anomalia",
                                 dettaglio="Nessun titolo trovato per questa polizza nell'anno corrente. "
                                          "Verifica se è stata dimenticata o cessata senza notifica.",
                                 match_prev=t_prev))
        else:
            # confermato — presente in entrambi gli anni
            rows.append(_row(t_curr, pid, "confermato", "",
                             match_prev=t_prev, match_curr=t_curr))
            keys_visti.add((pid, m))

    # 2) Titoli anno corrente NON già processati → nuove emissioni
    for (pid, m), t_curr in idx_curr.items():
        if (pid, m) in keys_visti:
            continue
        # verifica se ci sono OGNI corrispondenza sulla stessa polizza in idx_prev
        # (anche in mese diverso) → se sì è variazione mese, altrimenti nuovo
        prev_stessa_polizza = [tp for (kp, km), tp in idx_prev.items() if kp == pid]
        if prev_stessa_polizza:
            # scadenza cambiata già gestita sopra dal ramo mancante; skip
            continue
        rows.append(_row(t_curr, pid, "nuovo", "nuova_emissione",
                         dettaglio=f"Polizza emessa nell'anno {anno} (nessun premio {anno_prec})",
                         match_curr=t_curr))

    # Ordina: mancanti prima (per attenzione), poi nuovi, poi confermati
    ordine = {"mancante": 0, "nuovo": 1, "confermato": 2}
    rows.sort(key=lambda r: (ordine.get(r["tipo_row"], 9),
                             r.get("cliente_nome") or "",
                             r.get("polizza_numero") or ""))

    stats = {
        "anno_corrente": anno, "anno_precedente": anno_prec,
        "totale": len(rows),
        "confermati": sum(1 for r in rows if r["tipo_row"] == "confermato"),
        "mancanti": sum(1 for r in rows if r["tipo_row"] == "mancante"),
        "nuovi": sum(1 for r in rows if r["tipo_row"] == "nuovo"),
        "premio_totale_prec": round(sum((r["premio_anno_prec"] or 0) for r in rows), 2),
        "premio_totale_corr": round(sum((r["premio_anno_corr"] or 0) for r in rows), 2),
    }
    stats["delta_premio"] = round(stats["premio_totale_corr"] - stats["premio_totale_prec"], 2)
    return {"stats": stats, "righe": rows}


class ValidaBody(BaseModel):
    titoli_ids: list[str]


@router.post("/carichi-mensili/valida")
async def valida_carichi(
    body: ValidaBody,
    user=Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Valida i carichi selezionati ('in_attesa') facendoli entrare nei Titoli
    (e, essendo collegati, nei Titoli di polizza). Per ogni carico, confronto sulla
    chiave polizza + scadenza con i titoli UFFICIALI già esistenti:
      - esiste un titolo PROTETTO (incassato/coperto/stornato/sospeso-insoluto o in
        Prima Nota) → NON lo tocca, il carico viene scartato (contatore 'protetti');
      - esiste un titolo 'da_incassare' libero → lo SOVRASCRIVE con i nuovi importi
        (resta 'da_incassare', già presente nei Titoli) e il carico viene consumato;
      - non esiste → il carico viene promosso a titolo ufficiale 'da_incassare'.
    """
    if not body.titoli_ids:
        raise HTTPException(400, "Nessun titolo selezionato")
    carichi = await db.titoli.find(
        {"id": {"$in": body.titoli_ids}, "stato_carico": "in_attesa"}, {"_id": 0},
    ).to_list(10000)
    now = datetime.now(timezone.utc).isoformat()
    validati = 0
    sovrascritti = 0
    protetti = 0
    for c in carichi:
        existing = await db.titoli.find({
            "polizza_id": c.get("polizza_id"),
            "scadenza": c.get("scadenza"),
            "id": {"$ne": c["id"]},
            "stato_carico": {"$nin": ["in_attesa", "annullato_carico"]},
        }, {"_id": 0}).to_list(50)

        if any(not _carico_overwritable(e) for e in existing):
            # Titolo protetto già presente → non toccare, scarta il carico
            await db.titoli.update_one({"id": c["id"]}, {"$set": {
                "stato_carico": "annullato_carico",
                "motivo_mancanza": "Già presente (protetto)",
                "note_carico": "Scartato in validazione: esiste già un titolo protetto per questa scadenza.",
                "updated_at": now,
            }})
            protetti += 1
            continue

        sovr = [e for e in existing if _carico_overwritable(e)]
        if sovr:
            target = sovr[0]
            await db.titoli.update_one({"id": target["id"]}, {"$set": {
                "importo_lordo": c.get("importo_lordo"),
                "importo_netto": c.get("importo_netto"),
                "imposte": c.get("imposte") or 0,
                "ssn": c.get("ssn") or 0,
                "provvigioni": c.get("provvigioni") or 0,
                "effetto": c.get("effetto"),
                "mezzo_pagamento": c.get("mezzo_pagamento"),
                "stato": "da_incassare",
                "stato_carico": "validato",
                "sovrascritto_da_carico_at": now,
                "updated_at": now,
            }})
            # Consuma il carico in attesa (evita il doppione)
            await db.titoli.delete_one({"id": c["id"]})
            sovrascritti += 1
        else:
            # Nessun titolo ufficiale → promuovi il carico a titolo 'da_incassare'
            await db.titoli.update_one({"id": c["id"]}, {"$set": {
                "stato_carico": "validato",
                "stato": "da_incassare",
                "validato_at": now,
                "validato_da": user.get("id"),
            }})
            validati += 1

    await log_attivita(user, "valida_carichi", "titoli", None,
                       f"validati={validati} sovrascritti={sovrascritti} protetti={protetti}")
    return {"ok": True, "validati": validati, "sovrascritti": sovrascritti,
            "protetti": protetti}


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
    imposte: Optional[float] = None
    ssn: Optional[float] = None
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


# ============================================================================
# IMPORT EXCEL/CSV con auto-mapping colonne
# ============================================================================

# Mapping fuzzy: intestazioni comuni dei file di compagnia → campi CRM
_HEADER_ALIASES = {
    "polizza_numero": ["polizza", "numero polizza", "n. polizza", "num polizza",
                       "poliz n.", "n polizza", "policy", "policy number", "contratto",
                       "num. contratto", "numero contratto", "n. contratto",
                       "n contratto", "num contratto", "nr. contratto"],
    "cliente_nome": ["cliente", "contraente", "nominativo", "assicurato",
                     "ragione sociale", "denominazione", "cliente/contraente"],
    "compagnia": ["compagnia", "impresa", "società", "insurer", "carrier"],
    "ramo": ["ramo", "prodotto", "line", "linea", "branch"],
    "targa": ["targa", "veicolo", "identificativo", "plate"],
    "effetto": ["effetto", "data effetto", "decorrenza", "data decorrenza",
                "inizio", "start", "from", "dal"],
    "scadenza": ["scadenza", "data scadenza", "expires", "expiry", "al", "fine", "to"],
    "importo_lordo": ["premio lordo", "lordo", "premio", "totale", "importo",
                      "gross", "premio totale", "premio_totale"],
    "importo_netto": ["premio netto", "netto", "net", "premio imp.", "premio imp",
                      "imponibile", "premio imponibile", "premio imp"],
    "imposte": ["imposte", "tasse", "tax", "imposta"],
    "ssn": ["ssn", "s.s.n.", "premio ssn", "contributo ssn", "servizio sanitario",
            "servizio sanitario nazionale", "ssn."],
    "provvigioni": ["provvigioni", "commissioni", "provv", "commission",
                    "provvigione", "provv. attiva", "provv.ni", "provv ni",
                    "provvni", "provvigioni attive"],
    "frazionamento": ["frazionamento", "rateazione", "rata", "periodicità",
                      "split", "frequency"],
    "mezzo_pagamento": ["mezzo pagamento", "pagamento", "metodo pagamento",
                        "payment", "modalità pagamento", "modalita pagamento"],
    "codice_fiscale": ["codice fiscale", "cf", "c.f.", "codicefiscale", "tax id"],
    "partita_iva": ["partita iva", "piva", "p.iva", "vat"],
}


def _normalize_header(h: str) -> str:
    """Normalizza un'intestazione per il matching fuzzy."""
    if h is None:
        return ""
    return str(h).strip().lower().replace("  ", " ")


def _suggest_mapping(headers: list[str]) -> dict[str, Optional[str]]:
    """Per ogni campo CRM suggerisce l'header corrispondente nel file.
    Ritorna ``{campo_crm: header_originale_file_o_None}``.
    """
    norm_headers = {_normalize_header(h): h for h in headers}
    mapping: dict[str, Optional[str]] = {}
    for campo, aliases in _HEADER_ALIASES.items():
        found = None
        for alias in aliases:
            alias_n = _normalize_header(alias)
            # match esatto
            if alias_n in norm_headers:
                found = norm_headers[alias_n]
                break
            # match "starts with" per alias corti (es. "cf" in "cf cliente")
            for nh, orig in norm_headers.items():
                if nh.startswith(alias_n + " ") or nh == alias_n:
                    found = orig
                    break
            if found:
                break
        mapping[campo] = found
    return mapping


def _read_upload_to_rows(content: bytes, filename: str) -> tuple[list[str], list[dict]]:
    """Legge un file .xlsx / .xls / .csv e ritorna (headers, righe).

    Prende sempre il primo foglio se Excel. CSV auto-detect separator (,, ;, tab).
    """
    fname_lower = (filename or "").lower()
    if fname_lower.endswith((".xlsx", ".xls")):
        import openpyxl  # type: ignore
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers_row = next(rows_iter, None) or []
        headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(headers_row)]
        rows: list[dict] = []
        for row in rows_iter:
            if all(v is None or str(v).strip() == "" for v in row):
                continue
            rows.append({headers[i]: row[i] if i < len(row) else None
                         for i in range(len(headers))})
        return headers, rows
    # CSV
    import csv as _csv
    text = content.decode("utf-8-sig", errors="ignore")
    # auto-detect separatore
    sep = ";" if text.count(";") > text.count(",") else ","
    reader = _csv.DictReader(io.StringIO(text), delimiter=sep)
    headers = reader.fieldnames or []
    rows = [dict(r) for r in reader]
    return headers, rows


@router.post("/carichi-mensili/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    user=Depends(require_user("admin", "collaboratore")),
):
    """Fase 1 dell'import: legge il file e propone un mapping colonne→campi CRM.

    Ritorna:
      ``{headers, sample_rows, suggested_mapping, total_rows}``

    Il frontend mostra il mapping suggerito e permette all'utente di correggerlo,
    poi invia il file + mapping definitivo a ``/import/apply``.
    """
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File troppo grande (max 10 MB)")
    try:
        headers, rows = _read_upload_to_rows(content, file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"Impossibile leggere il file: {e}")
    if not headers:
        raise HTTPException(400, "Il file non contiene intestazioni")
    suggested = _suggest_mapping(headers)
    # Cache temporanea del file in memoria via GridFS-like? Per semplicità
    # il file va ripassato in /apply. Ritorno solo le prime 5 righe per preview.
    return {
        "headers": headers,
        "sample_rows": rows[:5],
        "suggested_mapping": suggested,
        "total_rows": len(rows),
        "campi_crm_disponibili": list(_HEADER_ALIASES.keys()),
    }


def _to_float(v) -> float:
    """Converte una cella (str/int/float/None) in float robusto.
    Gestisce virgole italiane, simboli €, spazi."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("€", "").replace(" ", "").replace("\xa0", "")
    # Formato italiano "1.234,50" → "1234.50"
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _to_iso_date(v) -> Optional[str]:
    """Converte una data (str o datetime) in ISO YYYY-MM-DD.
    Accetta formati IT ``DD/MM/YYYY`` e ISO."""
    if v is None or v == "":
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()[:10]
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            d, m, y = parts
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    if "-" in s and len(s) == 10:
        return s
    return None


@router.post("/carichi-mensili/import/apply")
async def import_apply(
    file: UploadFile = File(...),
    mapping_json: str = Form(...),
    user=Depends(require_user("admin", "collaboratore")),
):
    """Fase 2 dell'import: applica il mapping e crea i titoli in stato in_attesa.

    ``mapping_json``: JSON con ``{campo_crm: header_file}`` (es.
    ``{"polizza_numero": "N. Polizza", "importo_lordo": "Premio"}``).

    Strategia:
    1. Legge il file (di nuovo — è stateless, l'operatore ha appena visto la preview)
    2. Per ogni riga usa il mapping per estrarre i campi
    3. Cerca la polizza per numero. Se non esiste, crea un titolo "orfano" con nota
       (l'operatore lo sistemerà a mano) — comunque va nel bucket carichi.
    4. Crea il titolo con stato_carico=in_attesa e caricato_da_import=True

    Ritorna ``{creati, saltati, errori, batch_id}``.
    """
    import json as _json
    try:
        mapping = _json.loads(mapping_json)
    except Exception:
        raise HTTPException(400, "mapping_json non valido")
    if not mapping.get("polizza_numero"):
        raise HTTPException(400, "Il mapping deve contenere 'polizza_numero' per identificare la polizza")

    content = await file.read()
    try:
        _, rows = _read_upload_to_rows(content, file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"Impossibile rileggere il file: {e}")

    batch_id = str(uuid.uuid4())
    creati = 0
    saltati = 0
    errori: list[dict] = []
    unmatched: list[dict] = []  # righe con polizza non trovata → step manuale
    totali = {"lordo": 0.0, "netto": 0.0, "imposte": 0.0, "ssn": 0.0, "provvigioni": 0.0}
    header_pol = mapping.get("polizza_numero", "")
    header_cliente = mapping.get("cliente_nome", "")

    for i, r in enumerate(rows, start=2):  # start=2: riga 1 = header
        try:
            pol_num_raw = r.get(header_pol)
            if not pol_num_raw:
                saltati += 1
                continue
            pol_num = str(pol_num_raw).strip()
            pol = await db.polizze.find_one(
                {"numero_polizza": pol_num},
                {"_id": 0, "id": 1, "collaboratore_id": 1},
            )
            if not pol:
                # Polizza non trovata → cerca candidati per abbinamento manuale
                cliente_str = str(r.get(header_cliente) or "").strip()
                suggerimenti: list[dict] = []
                if cliente_str:
                    # Match fuzzy sul nome cliente (case-insensitive)
                    import re as _re
                    q_norm = _re.escape(cliente_str.split()[0]) if cliente_str else ""
                    if q_norm:
                        async for a in db.anagrafiche.find(
                            {"ragione_sociale": {"$regex": q_norm, "$options": "i"}},
                            {"_id": 0, "id": 1, "ragione_sociale": 1},
                        ).limit(5):
                            async for p in db.polizze.find(
                                {"contraente_id": a["id"]},
                                {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "targa": 1},
                            ).limit(5):
                                suggerimenti.append({
                                    **p, "cliente_nome": a["ragione_sociale"],
                                })
                # Match anche per numero simile (contains) come fallback
                if len(suggerimenti) < 3 and len(pol_num) >= 4:
                    async for p in db.polizze.find(
                        {"numero_polizza": {"$regex": pol_num[:6], "$options": "i"}},
                        {"_id": 0, "id": 1, "numero_polizza": 1, "ramo": 1, "targa": 1,
                         "contraente_id": 1},
                    ).limit(5):
                        if p["id"] not in {s["id"] for s in suggerimenti}:
                            a = await db.anagrafiche.find_one(
                                {"id": p.get("contraente_id")},
                                {"_id": 0, "ragione_sociale": 1},
                            )
                            suggerimenti.append({
                                **p, "cliente_nome": (a or {}).get("ragione_sociale") or "-",
                            })
                # Ritorna la riga con dati normalizzati per il match manuale
                imp_lordo = _to_float(r.get(mapping.get("importo_lordo", "")))
                scad = _to_iso_date(r.get(mapping.get("scadenza", "")))
                eff = _to_iso_date(r.get(mapping.get("effetto", ""))) or scad
                unmatched.append({
                    "riga": i,
                    "polizza_numero_file": pol_num,
                    "cliente_file": cliente_str,
                    "scadenza": scad,
                    "effetto": eff,
                    "importo_lordo": imp_lordo,
                    "importo_netto": _to_float(r.get(mapping.get("importo_netto", ""))) or imp_lordo,
                    "imposte": _to_float(r.get(mapping.get("imposte", ""))),
                    "ssn": _to_float(r.get(mapping.get("ssn", ""))),
                    "provvigioni": _to_float(r.get(mapping.get("provvigioni", ""))),
                    "mezzo_pagamento": r.get(mapping.get("mezzo_pagamento", "")) or None,
                    "suggerimenti": suggerimenti[:5],
                })
                continue
            imp_lordo = _to_float(r.get(mapping.get("importo_lordo", "")))
            imp_netto = _to_float(r.get(mapping.get("importo_netto", ""))) or imp_lordo
            scad = _to_iso_date(r.get(mapping.get("scadenza", "")))
            eff = _to_iso_date(r.get(mapping.get("effetto", ""))) or scad
            if not scad:
                errori.append({"riga": i, "polizza": pol_num, "errore": "Scadenza mancante o non valida"})
                continue
            # Snapshot premio precedente
            last = await db.titoli.find_one(
                {"polizza_id": pol["id"], "stato_carico": "validato"},
                {"_id": 0, "importo_lordo": 1}, sort=[("scadenza", -1)],
            )
            t = Titolo(
                polizza_id=pol["id"],
                effetto=eff or scad, scadenza=scad,
                importo_lordo=imp_lordo, importo_netto=imp_netto,
                imposte=_to_float(r.get(mapping.get("imposte", ""))),
                ssn=_to_float(r.get(mapping.get("ssn", ""))),
                provvigioni=_to_float(r.get(mapping.get("provvigioni", ""))),
                mezzo_pagamento=(r.get(mapping.get("mezzo_pagamento", "")) or None),
                collaboratore_id=pol.get("collaboratore_id") or user.get("id"),
                stato_carico="in_attesa",
                caricato_da_import=True,
                import_batch_id=batch_id,
                import_source=file.filename or "excel_csv",
                premio_precedente=float(last["importo_lordo"]) if last else None,
                fonte="import_ania",
            )
            await db.titoli.insert_one(t.model_dump())
            creati += 1
            totali["lordo"] += t.importo_lordo or 0
            totali["netto"] += t.importo_netto or 0
            totali["imposte"] += t.imposte or 0
            totali["ssn"] += t.ssn or 0
            totali["provvigioni"] += t.provvigioni or 0
        except Exception as e:
            errori.append({"riga": i, "errore": str(e)})

    await log_attivita(user, "import_excel_csv", "titoli", batch_id,
                       f"creati={creati} saltati={saltati} unmatched={len(unmatched)} errori={len(errori)}")
    return {"ok": True, "batch_id": batch_id, "creati": creati,
            "saltati": saltati, "unmatched": unmatched, "errori": errori,
            "totali": {k: round(v, 2) for k, v in totali.items()},
            "totale_letti": len(rows)}


class ManualMatchBody(BaseModel):
    """Corpo per il match manuale post-import.

    Per ogni riga rimasta orfana l'operatore sceglie una polizza esistente
    dai suggerimenti (o cerca a mano). Il backend crea il titolo con quella
    polizza + i dati già estratti dal file.
    """
    batch_id: str
    matches: list[dict]  # [{polizza_id, effetto, scadenza, importo_lordo, ...}]


@router.post("/carichi-mensili/import/match-manual")
async def import_match_manual(
    body: ManualMatchBody,
    user=Depends(require_user("admin", "collaboratore")),
):
    """Fase 3 (opzionale) dell'import: crea i titoli per le righe che l'operatore
    ha abbinato manualmente a polizze esistenti."""
    if not body.matches:
        return {"ok": True, "creati": 0}
    creati = 0
    saltati_protetti = 0
    errori = []
    for m in body.matches:
        try:
            pol_id = m.get("polizza_id")
            if not pol_id:
                continue
            pol = await db.polizze.find_one(
                {"id": pol_id}, {"_id": 0, "id": 1, "collaboratore_id": 1},
            )
            if not pol:
                errori.append({"polizza_id": pol_id, "errore": "polizza scomparsa"})
                continue
            last = await db.titoli.find_one(
                {"polizza_id": pol_id, "stato_carico": "validato"},
                {"_id": 0, "importo_lordo": 1}, sort=[("scadenza", -1)],
            )
            imp_lordo = float(m.get("importo_lordo") or 0)
            t = Titolo(
                polizza_id=pol_id,
                effetto=m.get("effetto") or m.get("scadenza"),
                scadenza=m.get("scadenza"),
                importo_lordo=imp_lordo,
                importo_netto=float(m.get("importo_netto") or 0) or imp_lordo,
                imposte=float(m.get("imposte") or 0),
                ssn=float(m.get("ssn") or 0),
                provvigioni=float(m.get("provvigioni") or 0),
                mezzo_pagamento=m.get("mezzo_pagamento") or None,
                collaboratore_id=pol.get("collaboratore_id") or user.get("id"),
                stato_carico="in_attesa",
                caricato_da_import=True,
                import_batch_id=body.batch_id,
                import_source="excel_csv_manual_match",
                premio_precedente=float(last["importo_lordo"]) if last else None,
                fonte="import_ania",
                note_carico=f"Abbinamento manuale post-import (file: {m.get('polizza_numero_file') or 'n/d'})",
            )
            await db.titoli.insert_one(t.model_dump())
            creati += 1
        except Exception as e:
            errori.append({"errore": str(e)})
    await log_attivita(user, "import_manual_match", "titoli", body.batch_id,
                       f"creati={creati} errori={len(errori)}")
    return {"ok": True, "creati": creati, "errori": errori}


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
                ssn=float(row.get("ssn") or 0),
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
