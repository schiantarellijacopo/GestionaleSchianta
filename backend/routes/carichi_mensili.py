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
        # Badge variazione: confronto premio precedente vs attuale
        prev = t.get("premio_precedente")
        curr = float(t.get("importo_lordo") or 0)
        variazione_badge = None
        variazione_delta_euro = None
        variazione_delta_pct = None
        if prev is not None and prev > 0:
            delta = curr - prev
            pct = (delta / prev) * 100
            variazione_delta_euro = round(delta, 2)
            variazione_delta_pct = round(pct, 1)
            if abs(delta) < 0.01:
                variazione_badge = "🟢 Regolare"
            elif delta > 0:
                variazione_badge = f"🛑 Aumento (+€{delta:.2f})"
            else:
                variazione_badge = f"🔻 Riduzione ({delta:.2f}€)"
        elif prev is None:
            variazione_badge = "🆕 Nuova"

        rows.append({
            **t,
            "polizza_numero": p.get("numero_polizza"),
            "polizza_ramo": p.get("ramo"),
            "polizza_prodotto": p.get("prodotto"),
            "polizza_targa": p.get("targa"),
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
            "variazione_delta_euro": variazione_delta_euro,
            "variazione_delta_pct": variazione_delta_pct,
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


# ============================================================================
# IMPORT EXCEL/CSV con auto-mapping colonne
# ============================================================================

# Mapping fuzzy: intestazioni comuni dei file di compagnia → campi CRM
_HEADER_ALIASES = {
    "polizza_numero": ["polizza", "numero polizza", "n. polizza", "num polizza",
                       "poliz n.", "n polizza", "policy", "policy number", "contratto"],
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
    "importo_netto": ["premio netto", "netto", "net"],
    "imposte": ["imposte", "tasse", "tax"],
    "provvigioni": ["provvigioni", "commissioni", "provv", "commission",
                    "provvigione", "provv. attiva"],
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

    for i, r in enumerate(rows, start=2):  # start=2: riga 1 = header
        try:
            pol_num_raw = r.get(mapping.get("polizza_numero", ""))
            if not pol_num_raw:
                saltati += 1
                continue
            pol_num = str(pol_num_raw).strip()
            pol = await db.polizze.find_one(
                {"numero_polizza": pol_num},
                {"_id": 0, "id": 1, "collaboratore_id": 1},
            )
            if not pol:
                errori.append({"riga": i, "polizza": pol_num, "errore": "Polizza non trovata nel CRM"})
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
        except Exception as e:
            errori.append({"riga": i, "errore": str(e)})

    await log_attivita(user, "import_excel_csv", "titoli", batch_id,
                       f"creati={creati} saltati={saltati} errori={len(errori)}")
    return {"ok": True, "batch_id": batch_id, "creati": creati,
            "saltati": saltati, "errori": errori,
            "totale_letti": len(rows)}


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
