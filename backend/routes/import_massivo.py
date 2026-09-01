"""Importatore Massivo Intelligente multi-file (Excel/CSV).

Migrazione storici agenzie: Anagrafiche + Polizze + Titoli/Quietanze + Sinistri.
- Multi-file: un file per entità OPPURE file "misto" (una riga = contraente+polizza+titolo).
- Rilevamento entità + mapping colonne via AI (Claude Sonnet, Emergent LLM key) con
  fallback euristico su alias header.
- Deduplica: Anagrafiche per CF/P.IVA (+ fuzzy su ragione sociale); Polizze per numero
  polizza; Titoli per (polizza+numero/effetto); Sinistri per numero sinistro.
- Policy default: aggiorna SOLO i campi vuoti/mancanti dell'esistente ("fill").

Flusso:
  POST /api/import-massivo/upload        (multipart, più file) → sessione + preview + mapping AI
  POST /api/import-massivo/{sid}/commit  (JSON plan) → avvia import in background
  GET  /api/import-massivo/{sid}/status  → progresso + risultato
"""
import os
import io
import re
import json
import base64
import asyncio
import uuid
from difflib import SequenceMatcher
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body
import pandas as pd

from database import db
from auth import require_user
from shared import log_attivita
from routes.import_anagrafiche import (
    _normalize_header, _read_dataframe, _sanitize_value, _parse_date_flexible,
    _similarity, FIELD_ALIASES as ANAG_ALIASES,
)

router = APIRouter(prefix="/import-massivo", tags=["import-massivo"])

# ============================================================
# Campi canonici per entità (per prompt AI e mapping manuale)
# ============================================================
ENTITY_FIELDS = {
    "anagrafica": {
        "tipo": "persona_fisica o persona_giuridica",
        "ragione_sociale": "nome completo o ragione sociale azienda",
        "nome": "nome (persona fisica)",
        "cognome": "cognome (persona fisica)",
        "codice_fiscale": "codice fiscale",
        "partita_iva": "partita IVA",
        "data_nascita": "data di nascita",
        "sesso": "M o F",
        "indirizzo": "via/indirizzo",
        "comune": "comune/città",
        "provincia": "provincia (sigla)",
        "cap": "CAP",
        "telefono": "telefono fisso",
        "cellulare": "cellulare",
        "email": "email",
        "iban": "IBAN",
        "professione": "professione",
        "note": "note",
        "preferenza_pagamento": "metodo pagamento preferito",
    },
    "polizza": {
        "numero_polizza": "numero della polizza (CHIAVE)",
        "compagnia_nome": "nome compagnia assicurativa",
        "contraente_cf": "codice fiscale/P.IVA del contraente (per collegamento)",
        "contraente_nome": "nome/ragione sociale del contraente (per collegamento)",
        "ramo": "ramo (RCA, Infortuni, Vita, ...)",
        "prodotto": "nome prodotto",
        "stato": "stato polizza (attiva/annullata/sospesa)",
        "effetto": "data effetto/decorrenza",
        "scadenza": "data scadenza",
        "frazionamento": "frazionamento (annuale/semestrale/...)",
        "premio_lordo": "premio lordo",
        "premio_netto": "premio netto",
        "premio_tasse": "imposte/tasse",
        "premio_ssn": "SSN",
        "provvigioni": "provvigioni",
        "targa": "targa veicolo (RCA)",
        "mezzo_pagamento_preferito": "metodo di pagamento",
        "note": "note",
    },
    "titolo": {
        "numero_polizza": "numero polizza a cui appartiene il titolo (CHIAVE collegamento)",
        "numero_titolo": "numero del titolo/quietanza",
        "tipo": "tipo titolo (quietanza/rinnovo/appendice/...)",
        "effetto": "data effetto/decorrenza del titolo",
        "scadenza": "data scadenza del titolo",
        "stato": "stato (incassato/da_incassare/insoluto/...)",
        "importo_lordo": "importo lordo",
        "importo_netto": "importo netto",
        "imposte": "imposte",
        "provvigioni": "provvigioni",
        "data_incasso": "data incasso",
        "mezzo_pagamento": "METODO DI PAGAMENTO del titolo (contanti/assegno/bonifico/RID/...)",
        "note": "note",
    },
    "sinistro": {
        "numero_sinistro": "numero sinistro (CHIAVE)",
        "numero_polizza": "numero polizza collegata",
        "contraente_cf": "CF/P.IVA contraente",
        "contraente_nome": "nome contraente",
        "compagnia_nome": "compagnia",
        "data_avvenimento": "data avvenimento",
        "data_denuncia": "data denuncia",
        "ramo": "ramo",
        "stato": "stato sinistro (aperto/chiuso/liquidato/...)",
        "descrizione": "descrizione/dinamica",
        "riserva": "importo a riserva",
        "liquidazione": "importo liquidato",
        "note": "note",
    },
}

# Alias euristici (fallback quando AI non disponibile) — riuso anagrafica dal modulo esistente
_POL_ALIASES = {
    "numero_polizza": ["numero polizza", "n polizza", "polizza", "num polizza", "nr polizza", "policy number", "contratto"],
    "compagnia_nome": ["compagnia", "compagnia assicurativa", "company", "impresa"],
    "contraente_cf": ["cf contraente", "codice fiscale contraente", "piva contraente", "cf", "piva"],
    "contraente_nome": ["contraente", "cliente", "intestatario", "assicurato", "nominativo"],
    "ramo": ["ramo", "ramo assicurativo", "branch"],
    "prodotto": ["prodotto", "descrizione prodotto", "garanzia", "tipo polizza"],
    "stato": ["stato", "stato polizza", "status"],
    "effetto": ["effetto", "decorrenza", "data effetto", "data decorrenza", "inizio", "data inizio"],
    "scadenza": ["scadenza", "data scadenza", "fine", "data fine"],
    "frazionamento": ["frazionamento", "rateazione", "frazionam"],
    "premio_lordo": ["premio lordo", "premio", "lordo", "importo lordo", "premio totale"],
    "premio_netto": ["premio netto", "netto", "imponibile"],
    "premio_tasse": ["imposte", "tasse", "imposta"],
    "premio_ssn": ["ssn", "servizio sanitario"],
    "provvigioni": ["provvigioni", "provvigione", "commissioni"],
    "targa": ["targa", "plate", "targa veicolo"],
    "mezzo_pagamento_preferito": ["mezzo pagamento", "metodo pagamento", "pagamento", "modalita pagamento"],
    "note": ["note", "annotazioni", "note polizza"],
}
_TIT_ALIASES = {
    "numero_polizza": ["numero polizza", "n polizza", "polizza", "policy number"],
    "numero_titolo": ["numero titolo", "n titolo", "titolo", "numero quietanza", "quietanza", "rata"],
    "tipo": ["tipo", "tipo titolo", "tipo quietanza", "tipologia"],
    "effetto": ["effetto", "decorrenza", "data effetto", "data decorrenza"],
    "scadenza": ["scadenza", "data scadenza"],
    "stato": ["stato", "stato titolo", "stato incasso"],
    "importo_lordo": ["importo lordo", "lordo", "premio lordo", "importo", "premio"],
    "importo_netto": ["importo netto", "netto", "imponibile"],
    "imposte": ["imposte", "tasse", "imposta"],
    "provvigioni": ["provvigioni", "provvigione"],
    "data_incasso": ["data incasso", "incasso", "data pagamento", "pagato il"],
    "mezzo_pagamento": ["mezzo pagamento", "metodo pagamento", "pagamento", "modalita pagamento", "forma pagamento", "tipo pagamento"],
    "note": ["note", "annotazioni"],
}
_SIN_ALIASES = {
    "numero_sinistro": ["numero sinistro", "n sinistro", "sinistro", "nr sinistro", "claim number"],
    "numero_polizza": ["numero polizza", "polizza"],
    "contraente_cf": ["cf contraente", "codice fiscale", "piva"],
    "contraente_nome": ["contraente", "cliente", "assicurato", "nominativo"],
    "compagnia_nome": ["compagnia", "impresa"],
    "data_avvenimento": ["data avvenimento", "data sinistro", "avvenimento", "data evento"],
    "data_denuncia": ["data denuncia", "denuncia", "data apertura"],
    "ramo": ["ramo"],
    "stato": ["stato", "stato sinistro"],
    "descrizione": ["descrizione", "dinamica", "descrizione sinistro"],
    "riserva": ["riserva", "importo riserva", "a riserva"],
    "liquidazione": ["liquidazione", "liquidato", "importo liquidato"],
    "note": ["note"],
}
_ALIAS_BY_ENTITY = {
    "anagrafica": ANAG_ALIASES,
    "polizza": _POL_ALIASES,
    "titolo": _TIT_ALIASES,
    "sinistro": _SIN_ALIASES,
}
ENTITY_ORDER = ["anagrafica", "polizza", "titolo", "sinistro"]

# Valori ammessi per i campi enum (Literal) — usati per scartare valori non validi dai CSV
_ENUM_VALUES = {
    "polizza": {
        "stato": {"attiva", "sospesa", "annullata", "scaduta", "in_emissione"},
        "frazionamento": {"annuale", "semestrale", "quadrimestrale", "trimestrale", "mensile", "unica"},
    },
    "titolo": {
        "tipo": {"nuova", "rinnovo", "appendice", "regolazione", "storno", "quietanza", "sostituzione", "annullo"},
        "stato": {"incassato", "da_incassare", "insoluto", "stornato"},
    },
    "sinistro": {
        "stato": {"aperto", "in_istruttoria", "liquidato", "chiuso_senza_seguito", "respinto"},
    },
}


def _coerce_enums(entity: str, doc: dict):
    """Normalizza (lowercase) i campi enum e scarta i valori non ammessi."""
    for field, allowed in _ENUM_VALUES.get(entity, {}).items():
        v = doc.get(field)
        if v is None:
            continue
        lv = str(v).strip().lower()
        if lv in allowed:
            doc[field] = lv
        else:
            doc.pop(field, None)


# ============================================================
# Rilevamento entità + mapping
# ============================================================
def _detect_entity_heuristic(headers: List[str]) -> str:
    norm = [_normalize_header(h) for h in headers]
    blob = " | ".join(norm)
    has = lambda *ks: any(k in blob for k in ks)
    if has("numero sinistro", "sinistro", "data avvenimento", "denuncia"):
        return "sinistro"
    # titolo: quietanza/rata + importo/incasso, spesso con polizza
    if has("quietanza", "titolo", "rata") and has("importo", "incasso", "premio", "pagamento"):
        return "titolo"
    if has("numero polizza", "polizza", "contratto") and not has("quietanza", "rata"):
        return "polizza"
    if has("quietanza", "rata"):
        return "titolo"
    return "anagrafica"


def _detect_mapping_heuristic(entity: str, headers: List[str]) -> dict:
    aliases = _ALIAS_BY_ENTITY.get(entity, {})
    mapping: dict = {}
    used: set = set()
    for h in headers:
        norm = _normalize_header(h)
        best, best_score = None, 0.0
        for canonical, al in aliases.items():
            if canonical in used:
                continue
            for a in al:
                sc = _similarity(norm, _normalize_header(a))
                if sc > best_score:
                    best_score, best = sc, canonical
        mapping[str(h)] = best if (best and best_score >= 0.6) else None
        if mapping[str(h)]:
            used.add(best)
    return mapping


async def _ai_detect(headers: List[str], samples: List[dict]) -> Optional[dict]:
    """Usa Claude Sonnet per rilevare entità + mapping. Ritorna {entity, mapping, confidence} o None."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        campi_desc = {ent: {f: d for f, d in flds.items()} for ent, flds in ENTITY_FIELDS.items()}
        prompt = (
            "Sei un esperto di migrazione dati per CRM assicurativi italiani. "
            "Analizza le colonne di un file e determina:\n"
            "1) A quale ENTITÀ appartiene il file tra: anagrafica, polizza, titolo, sinistro.\n"
            "2) Il MAPPING di ogni colonna verso i campi canonici dell'entità (o null se nessuno).\n\n"
            f"CAMPI CANONICI PER ENTITÀ (nome_campo: descrizione):\n{json.dumps(campi_desc, ensure_ascii=False, indent=1)}\n\n"
            f"COLONNE DEL FILE: {json.dumps(headers, ensure_ascii=False)}\n\n"
            f"RIGHE DI ESEMPIO (prime {len(samples)}): {json.dumps(samples, ensure_ascii=False, default=str)}\n\n"
            "Rispondi SOLO con JSON valido, nessun testo attorno, nel formato:\n"
            '{\"entity\": \"<anagrafica|polizza|titolo|sinistro>\", \"confidence\": <0..1>, '
            '\"mapping\": {\"<header esatto>\": \"<campo_canonico o null>\"}}\n'
            "Usa gli header ESATTI come chiavi del mapping. Mappa solo colonne di cui sei ragionevolmente sicuro."
        )
        chat = LlmChat(
            api_key=key,
            session_id=f"import-massivo-{uuid.uuid4().hex[:8]}",
            system_message="Rispondi esclusivamente con JSON valido.",
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        txt = resp if isinstance(resp, str) else str(resp)
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        ent = data.get("entity")
        if ent not in ENTITY_FIELDS:
            return None
        raw_map = data.get("mapping") or {}
        valid_fields = set(ENTITY_FIELDS[ent].keys())
        mapping = {str(h): (v if v in valid_fields else None) for h, v in raw_map.items()}
        # assicura tutte le colonne presenti
        for h in headers:
            mapping.setdefault(str(h), None)
        return {"entity": ent, "confidence": float(data.get("confidence") or 0.7), "mapping": mapping}
    except Exception:
        return None


# ============================================================
# Normalizzazione valori
# ============================================================
_DATE_FIELDS = {"data_nascita", "effetto", "scadenza", "data_incasso", "data_avvenimento", "data_denuncia"}
_NUM_FIELDS = {"premio_lordo", "premio_netto", "premio_tasse", "premio_ssn", "provvigioni",
               "importo_lordo", "importo_netto", "imposte", "riserva", "liquidazione"}


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace("€", "").replace(" ", "")
    if not s:
        return None
    # gestione separatori IT: 1.234,56 → 1234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return round(float(re.sub(r"[^0-9.\-]", "", s)), 2)
    except Exception:
        return None


def _row_to_record(entity: str, row_values: dict, mapping: dict) -> dict:
    rec: dict = {}
    for header, canonical in mapping.items():
        if not canonical:
            continue
        val = _sanitize_value(row_values.get(header))
        if val is None:
            continue
        if canonical in _DATE_FIELDS:
            val = _parse_date_flexible(val)
            if val is None:
                continue
        elif canonical in _NUM_FIELDS:
            val = _to_float(val)
            if val is None:
                continue
        elif canonical in ("codice_fiscale", "partita_iva", "contraente_cf", "targa"):
            val = val.upper().replace(" ", "")
        elif canonical == "email":
            val = val.lower()
        elif canonical in ("ragione_sociale", "nome", "cognome", "contraente_nome",
                           "compagnia_nome", "comune", "indirizzo"):
            val = val.upper()
        rec[canonical] = val
    return rec


def _norm_name(s: Optional[str]) -> str:
    if not s:
        return ""
    s = _normalize_header(s)
    # rimuovi acronimi societari comuni
    for tok in ["srl", "s r l", "spa", "s p a", "snc", "s n c", "sas", "s a s", "sc", "societa", "ditta"]:
        s = re.sub(rf"\b{tok}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_similarity(a: str, b: str) -> float:
    a, b = _norm_name(a), _norm_name(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ============================================================
# UPLOAD
# ============================================================
@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    if not files:
        raise HTTPException(400, "Nessun file caricato")
    sid = uuid.uuid4().hex
    now_iso = datetime.now(timezone.utc).isoformat()
    file_summaries = []

    for fi, uf in enumerate(files):
        content = await uf.read()
        if not content:
            continue
        try:
            df = _read_dataframe(content, uf.filename)
        except HTTPException:
            file_summaries.append({"file_index": fi, "filename": uf.filename, "error": "Formato non leggibile"})
            continue
        if df.empty:
            file_summaries.append({"file_index": fi, "filename": uf.filename, "error": "File vuoto", "total_rows": 0})
            continue
        headers = [str(h) for h in df.columns]
        samples = []
        for _, r in df.head(3).iterrows():
            samples.append({h: _sanitize_value(r[h]) for h in headers})

        ai = await _ai_detect(headers, samples)
        if ai:
            entity, mapping, conf, source = ai["entity"], ai["mapping"], ai["confidence"], "ai"
        else:
            entity = _detect_entity_heuristic(headers)
            mapping = _detect_mapping_heuristic(entity, headers)
            conf, source = 0.5, "euristica"

        # preview: prime 8 righe normalizzate
        preview = []
        for _, r in df.head(8).iterrows():
            rd = {h: _sanitize_value(r[h]) for h in headers}
            preview.append({"raw": rd, "normalized": _row_to_record(entity, rd, mapping)})

        # salva bytes del file per il commit
        await db.import_massivo_files.insert_one({
            "id": uuid.uuid4().hex, "sid": sid, "file_index": fi,
            "filename": uf.filename, "content_b64": base64.b64encode(content).decode(),
            "created_at": now_iso,
        })
        file_summaries.append({
            "file_index": fi, "filename": uf.filename,
            "entity": entity, "entity_confidence": round(conf, 2), "mapping_source": source,
            "headers": headers, "mapping": mapping, "total_rows": int(len(df)),
            "available_fields": ENTITY_FIELDS[entity], "preview": preview,
        })

    session = {
        "id": sid, "created_at": now_iso, "user_id": user.get("id"),
        "status": "pronto", "files": file_summaries,
        "progress": None, "result": None,
    }
    await db.import_massivo_sessioni.insert_one(dict(session))
    session.pop("_id", None)
    return session


# ============================================================
# COMMIT (background)
# ============================================================
@router.post("/{sid}/commit")
async def commit_import(
    sid: str,
    plan: List[dict] = Body(..., embed=True),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """plan = [{file_index, entity, mapping:{header:canonical}}]. Avvia import in background."""
    sess = await db.import_massivo_sessioni.find_one({"id": sid}, {"_id": 0})
    if not sess:
        raise HTTPException(404, "Sessione non trovata")
    total = 0
    for p in plan:
        f = next((x for x in sess["files"] if x.get("file_index") == p.get("file_index")), None)
        if f:
            total += int(f.get("total_rows") or 0)
    await db.import_massivo_sessioni.update_one({"id": sid}, {"$set": {
        "status": "in_corso",
        "progress": {"fase": "avvio", "totale": total, "elaborate": 0,
                     "creati": 0, "aggiornati": 0, "saltati": 0, "errori": 0},
        "result": None,
    }})
    asyncio.create_task(_run_commit(sid, plan, user))
    return {"started": True, "sid": sid, "totale_righe": total}


@router.get("/{sid}/status")
async def import_status(sid: str, user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    sess = await db.import_massivo_sessioni.find_one({"id": sid}, {"_id": 0, "files.preview": 0})
    if not sess:
        raise HTTPException(404, "Sessione non trovata")
    return {"id": sid, "status": sess.get("status"), "progress": sess.get("progress"), "result": sess.get("result")}


async def _df_for_file(sid: str, file_index: int) -> Optional[pd.DataFrame]:
    doc = await db.import_massivo_files.find_one({"sid": sid, "file_index": file_index}, {"_id": 0})
    if not doc:
        return None
    content = base64.b64decode(doc["content_b64"])
    return _read_dataframe(content, doc["filename"])


async def _bump(sid: str, **inc):
    if inc:
        await db.import_massivo_sessioni.update_one(
            {"id": sid}, {"$inc": {f"progress.{k}": v for k, v in inc.items()}})


def _fill_missing(existing: dict, new: dict) -> dict:
    """Ritorna solo i campi da settare: quelli assenti/vuoti nell'esistente."""
    upd = {}
    for k, v in new.items():
        if v in (None, "", []):
            continue
        cur = existing.get(k)
        if cur in (None, "", []) or (isinstance(cur, (int, float)) and cur == 0 and isinstance(v, (int, float)) and v != 0):
            upd[k] = v
    return upd


async def _run_commit(sid: str, plan: List[dict], user: dict):
    from db_models import Anagrafica, Polizza, Titolo, Sinistro
    now_iso = datetime.now(timezone.utc).isoformat()
    stats = {"creati": 0, "aggiornati": 0, "saltati": 0, "errori": 0}
    errori_dett: List[dict] = []

    # cache compagnie: nome→id
    comp_cache: dict = {}
    async def _compagnia_id(nome: Optional[str]) -> Optional[str]:
        if not nome:
            return None
        key = _norm_name(nome)
        if key in comp_cache:
            return comp_cache[key]
        # 1) match esatto (case-insensitive) su ragione_sociale/nome
        doc = await db.compagnie.find_one({"$or": [
            {"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
            {"ragione_sociale": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
        ]}, {"_id": 0, "id": 1})
        # 2) fuzzy su tutte le compagnie
        if not doc:
            allc = await db.compagnie.find({}, {"_id": 0, "id": 1, "ragione_sociale": 1, "nome": 1}).to_list(1000)
            best, bsc = None, 0.0
            for c in allc:
                sc = max(_name_similarity(nome, c.get("ragione_sociale")),
                         _name_similarity(nome, c.get("nome") or ""))
                if sc > bsc:
                    bsc, best = sc, c
            if best and bsc >= 0.88:
                doc = {"id": best["id"]}
        # 3) auto-crea la compagnia (migrazione: nome libero dal CSV)
        if not doc:
            from db_models import Compagnia
            codice = (re.sub(r"[^A-Z0-9]", "", nome.upper())[:8] or "IMP") + "-" + uuid.uuid4().hex[:4].upper()
            obj = Compagnia(codice=codice, ragione_sociale=nome.upper(),
                            descrizione="Creata automaticamente da Import Massivo")
            newdoc = obj.model_dump()
            await db.compagnie.insert_one(newdoc)
            doc = {"id": newdoc["id"]}
        cid = doc["id"] if doc else None
        comp_cache[key] = cid
        return cid

    async def _find_anagrafica(cf, piva, nome) -> Optional[dict]:
        if cf:
            d = await db.anagrafiche.find_one({"codice_fiscale": cf}, {"_id": 0, "id": 1})
            if d:
                return d
        if piva:
            d = await db.anagrafiche.find_one({"partita_iva": piva}, {"_id": 0, "id": 1})
            if d:
                return d
        # fuzzy sul nome
        if nome:
            cand = await db.anagrafiche.find(
                {"ragione_sociale": {"$regex": _norm_name(nome).split(" ")[0], "$options": "i"}},
                {"_id": 0, "id": 1, "ragione_sociale": 1}).to_list(30)
            best, best_sc = None, 0.0
            for c in cand:
                sc = _name_similarity(nome, c.get("ragione_sociale"))
                if sc > best_sc:
                    best_sc, best = sc, c
            if best and best_sc >= 0.9:
                return {"id": best["id"]}
        return None

    # ordina il plan per dipendenze
    plan_sorted = sorted(plan, key=lambda p: ENTITY_ORDER.index(p["entity"]) if p.get("entity") in ENTITY_ORDER else 99)

    for p in plan_sorted:
        entity = p.get("entity")
        mapping = p.get("mapping") or {}
        df = await _df_for_file(sid, p.get("file_index"))
        if df is None or df.empty or entity not in ENTITY_FIELDS:
            continue
        await db.import_massivo_sessioni.update_one({"id": sid}, {"$set": {"progress.fase": f"import {entity}"}})
        headers = [str(h) for h in df.columns]

        for idx, row in df.iterrows():
            try:
                rd = {h: _sanitize_value(row[h]) for h in headers}
                rec = _row_to_record(entity, rd, mapping)

                if entity == "anagrafica":
                    cf = rec.get("codice_fiscale")
                    piva = rec.get("partita_iva")
                    if not rec.get("ragione_sociale"):
                        rs = f"{rec.get('cognome') or ''} {rec.get('nome') or ''}".strip()
                        if rs:
                            rec["ragione_sociale"] = rs
                    if not (cf or piva or rec.get("ragione_sociale")):
                        stats["saltati"] += 1; await _bump(sid, saltati=1, elaborate=1); continue
                    if "tipo" not in rec:
                        rec["tipo"] = "persona_giuridica" if (piva and len(cf or "") != 16) else "persona_fisica"
                    if rec.get("iban"):
                        rec["conti_correnti"] = [{"iban": rec.pop("iban"), "principale": True,
                                                  "note": "Import massivo"}]
                    existing = await _find_anagrafica(cf, piva, rec.get("ragione_sociale"))
                    if existing:
                        full = await db.anagrafiche.find_one({"id": existing["id"]}, {"_id": 0})
                        upd = _fill_missing(full, rec)
                        upd.pop("conti_correnti", None)
                        if upd:
                            upd["updated_at"] = now_iso
                            await db.anagrafiche.update_one({"id": existing["id"]}, {"$set": upd})
                            stats["aggiornati"] += 1; await _bump(sid, aggiornati=1)
                        else:
                            stats["saltati"] += 1; await _bump(sid, saltati=1)
                    else:
                        rec["collaboratore_id"] = rec.get("collaboratore_id") or user.get("id")
                        obj = Anagrafica(**{k: v for k, v in rec.items() if k in Anagrafica.model_fields})
                        await db.anagrafiche.insert_one(obj.model_dump())
                        stats["creati"] += 1; await _bump(sid, creati=1)

                elif entity == "polizza":
                    num = rec.get("numero_polizza")
                    if not num:
                        stats["saltati"] += 1; await _bump(sid, saltati=1, elaborate=1); continue
                    contr = await _find_anagrafica(rec.pop("contraente_cf", None), None, rec.pop("contraente_nome", None))
                    comp_id = await _compagnia_id(rec.pop("compagnia_nome", None))
                    doc = {k: v for k, v in rec.items() if k in Polizza.model_fields}
                    if contr:
                        doc["contraente_id"] = contr["id"]
                    if comp_id:
                        doc["compagnia_id"] = comp_id
                    _coerce_enums("polizza", doc)
                    existing = await db.polizze.find_one({"numero_polizza": num}, {"_id": 0})
                    if existing:
                        upd = _fill_missing(existing, doc)
                        if upd:
                            upd["updated_at"] = now_iso
                            await db.polizze.update_one({"id": existing["id"]}, {"$set": upd})
                            stats["aggiornati"] += 1; await _bump(sid, aggiornati=1)
                        else:
                            stats["saltati"] += 1; await _bump(sid, saltati=1)
                    else:
                        # default per campi obbligatori mancanti (migrazione storica)
                        if not doc.get("compagnia_id"):
                            doc["compagnia_id"] = await _compagnia_id("SCONOSCIUTA")
                        doc["ramo"] = doc.get("ramo") or "N/D"
                        doc["effetto"] = doc.get("effetto") or ""
                        doc["scadenza"] = doc.get("scadenza") or ""
                        if not doc.get("contraente_id"):
                            stats["saltati"] += 1
                            errori_dett.append({"row": int(idx) + 2, "entity": "polizza",
                                                "reason": f"contraente non trovato per polizza '{num}'"})
                            await _bump(sid, saltati=1, elaborate=1); continue
                        doc.setdefault("collaboratore_id", user.get("id"))
                        obj = Polizza(**doc)
                        await db.polizze.insert_one(obj.model_dump())
                        stats["creati"] += 1; await _bump(sid, creati=1)

                elif entity == "titolo":
                    num_pol = rec.pop("numero_polizza", None)
                    pol = await db.polizze.find_one({"numero_polizza": num_pol}, {"_id": 0, "id": 1, "collaboratore_id": 1}) if num_pol else None
                    if not pol:
                        stats["saltati"] += 1
                        errori_dett.append({"row": int(idx) + 2, "entity": "titolo",
                                            "reason": f"polizza '{num_pol}' non trovata"})
                        await _bump(sid, saltati=1, elaborate=1, errori=1); continue
                    doc = {k: v for k, v in rec.items() if k in Titolo.model_fields}
                    doc["polizza_id"] = pol["id"]
                    doc.setdefault("collaboratore_id", pol.get("collaboratore_id") or user.get("id"))
                    doc["caricato_da_import"] = True
                    _coerce_enums("titolo", doc)
                    q = {"polizza_id": pol["id"]}
                    if doc.get("numero_titolo"):
                        q["numero_titolo"] = doc["numero_titolo"]
                    elif doc.get("effetto"):
                        q["effetto"] = doc["effetto"]
                    existing = await db.titoli.find_one(q, {"_id": 0}) if len(q) > 1 else None
                    if existing:
                        upd = _fill_missing(existing, doc)
                        if upd:
                            upd["updated_at"] = now_iso
                            await db.titoli.update_one({"id": existing["id"]}, {"$set": upd})
                            stats["aggiornati"] += 1; await _bump(sid, aggiornati=1)
                        else:
                            stats["saltati"] += 1; await _bump(sid, saltati=1)
                    else:
                        doc["effetto"] = doc.get("effetto") or ""
                        doc["scadenza"] = doc.get("scadenza") or ""
                        obj = Titolo(**doc)
                        await db.titoli.insert_one(obj.model_dump())
                        stats["creati"] += 1; await _bump(sid, creati=1)

                elif entity == "sinistro":
                    num = rec.get("numero_sinistro")
                    if not num:
                        stats["saltati"] += 1; await _bump(sid, saltati=1, elaborate=1); continue
                    num_pol = rec.pop("numero_polizza", None)
                    contr = await _find_anagrafica(rec.pop("contraente_cf", None), None, rec.pop("contraente_nome", None))
                    comp_id = await _compagnia_id(rec.pop("compagnia_nome", None))
                    doc = {k: v for k, v in rec.items() if k in Sinistro.model_fields}
                    if num_pol:
                        pol = await db.polizze.find_one({"numero_polizza": num_pol}, {"_id": 0, "id": 1})
                        if pol:
                            doc["polizza_id"] = pol["id"]
                    if contr:
                        doc["contraente_id"] = contr["id"]
                    if comp_id:
                        doc["compagnia_id"] = comp_id
                    _coerce_enums("sinistro", doc)
                    existing = await db.sinistri.find_one({"numero_sinistro": num}, {"_id": 0}) if num else None
                    if existing:
                        upd = _fill_missing(existing, doc)
                        if upd:
                            upd["updated_at"] = now_iso
                            await db.sinistri.update_one({"id": existing["id"]}, {"$set": upd})
                            stats["aggiornati"] += 1; await _bump(sid, aggiornati=1)
                        else:
                            stats["saltati"] += 1; await _bump(sid, saltati=1)
                    else:
                        doc.setdefault("collaboratore_id", user.get("id"))
                        obj = Sinistro(**doc)
                        await db.sinistri.insert_one(obj.model_dump())
                        stats["creati"] += 1; await _bump(sid, creati=1)

                await _bump(sid, elaborate=1)
            except Exception as e:
                stats["errori"] += 1
                errori_dett.append({"row": int(idx) + 2, "entity": entity, "reason": str(e)[:200]})
                await _bump(sid, errori=1, elaborate=1)

    await db.import_massivo_sessioni.update_one({"id": sid}, {"$set": {
        "status": "completato",
        "progress.fase": "completato",
        "result": {**stats, "errori_dettaglio": errori_dett[:100]},
        "completed_at": now_iso,
    }})
    # cleanup file bytes
    await db.import_massivo_files.delete_many({"sid": sid})
    try:
        await log_attivita(user, "import", "massivo", sid,
                           f"Import massivo: +{stats['creati']} creati, {stats['aggiornati']} aggiornati, "
                           f"{stats['saltati']} saltati, {stats['errori']} errori")
    except Exception:
        pass
