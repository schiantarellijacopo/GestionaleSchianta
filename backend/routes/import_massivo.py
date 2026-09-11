"""Importatore Massivo Intelligente multi-file (Excel/CSV).

Migrazione storici agenzie: Anagrafiche + Polizze + Titoli/Quietanze + Sinistri.
- Multi-file: un file per entità OPPURE file "misto" (una riga = polizza + contraente).
- Rilevamento entità + mapping colonne via AI (Claude Sonnet, Emergent LLM key) con
  fallback euristico su alias header.
- Deduplica: Anagrafiche per CF/P.IVA (+ fuzzy su ragione sociale); Polizze per numero
  polizza; Titoli per (polizza+numero/effetto); Sinistri per numero sinistro.
- Policy default: aggiorna SOLO i campi vuoti/mancanti dell'esistente ("fill").
- Scala a 100k+ righe: file salvati in GridFS, cache di lookup, insert bufferizzati,
  progresso aggiornato a batch.
- File "portafoglio" (misti): dalla stessa riga crea/aggiorna anche l'ANAGRAFICA del
  contraente (indirizzo, telefono, email, ...) e la collega alla polizza.
"""
import os
import io
import re
import json
import uuid
import asyncio
from difflib import SequenceMatcher
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from bson import ObjectId
import pandas as pd

from database import db
import cf_calc
from auth import require_user
from shared import log_attivita
from routes.import_anagrafiche import (
    _normalize_header, _sanitize_value, _parse_date_flexible,
    _similarity, _norm_piva, FIELD_ALIASES as ANAG_ALIASES,
)

router = APIRouter(prefix="/import-massivo", tags=["import-massivo"])

_BUCKET = "import_massivo_fs"
_FLUSH = 1000
_PROGRESS_EVERY = 200
_ERR_CAP = 500


def _gridfs() -> AsyncIOMotorGridFSBucket:
    # db è TenantAwareDB → GridFS richiede il MotorDatabase raw sottostante
    return AsyncIOMotorGridFSBucket(db._db, bucket_name=_BUCKET)


ENTITY_FIELDS = {
    "anagrafica": {
        "tipo": "persona_fisica o persona_giuridica",
        "ragione_sociale": "nome completo o ragione sociale azienda",
        "nome": "nome (persona fisica)",
        "cognome": "cognome (persona fisica)",
        "codice_fiscale": "codice fiscale",
        "partita_iva": "partita IVA",
        "data_nascita": "data di nascita",
        "indirizzo": "via/indirizzo",
        "comune": "comune/città",
        "provincia": "provincia (sigla)",
        "cap": "CAP",
        "telefono": "telefono fisso",
        "cellulare": "cellulare",
        "email": "email",
        "pec": "PEC (posta certificata)",
        "iban": "IBAN",
        "note": "note",
        "preferenza_pagamento": "metodo pagamento preferito",
    },
    "polizza": {
        "numero_polizza": "numero della polizza (CHIAVE)",
        "compagnia_nome": "nome compagnia assicurativa",
        "ramo": "ramo (RCA, Infortuni, Vita, ...)",
        "prodotto": "prodotto/rischio specifico",
        "stato": "stato polizza (attiva/annullata/sospesa/scaduta)",
        "effetto": "data effetto/decorrenza",
        "scadenza": "data scadenza",
        "data_annullamento": "data di annullamento (se presente → polizza annullata)",
        "data_sospensione": "data di sospensione (se presente → polizza sospesa)",
        "frazionamento": "frazionamento (annuale/semestrale/...)",
        "premio_lordo": "premio LORDO",
        "premio_netto": "premio netto/imponibile",
        "premio_tasse": "imposte/tasse",
        "premio_ssn": "SSN",
        "provvigioni": "provvigioni",
        "targa": "targa veicolo (RCA)",
        "mezzo_pagamento_preferito": "metodo di pagamento",
        "note": "note",
        "contraente_cf": "codice fiscale del contraente (per collegare/creare l'anagrafica)",
        "contraente_piva": "partita IVA del contraente",
        "contraente_nome": "nome/ragione sociale del contraente",
        "contraente_indirizzo": "indirizzo del contraente",
        "contraente_comune": "comune del contraente",
        "contraente_cap": "CAP del contraente",
        "contraente_provincia": "provincia del contraente",
        "contraente_telefono": "telefono fisso del contraente",
        "contraente_cellulare": "cellulare del contraente",
        "contraente_email": "email del contraente",
        "operatore_nome": "operatore/collaboratore della polizza (Operatore 1)",
    },
    "titolo": {
        "numero_polizza": "numero polizza a cui appartiene il titolo (CHIAVE collegamento)",
        "numero_titolo": "numero del titolo/quietanza/appendice",
        "tipo": "tipo titolo (quietanza/rinnovo/appendice/...)",
        "effetto": "data rata / data effetto-decorrenza del titolo (RataDel)",
        "scadenza": "data scadenza del titolo (ProssimaScadenza)",
        "stato": "stato (incassato/da_incassare/insoluto/stornato)",
        "importo_lordo": "importo LORDO totale del titolo (Totale). NON usare ImpRata se c'è Totale",
        "importo_netto": "importo netto/imponibile",
        "imposte": "imposte",
        "importo_pagato": "importo effettivamente incassato/pagato (ImportoIncassato)",
        "provvigioni": "provvigioni",
        "data_incasso": "data incasso/pagamento",
        "mezzo_pagamento": "METODO DI PAGAMENTO del titolo (contanti/assegno/bonifico/RID/...)",
        "data_copertura": "data copertura del titolo (se presente → titolo COPERTO)",
        "compagnia_nome": "compagnia (per collegare/creare la polizza se mancante)",
        "ramo": "ramo (per collegare/creare la polizza se mancante)",
        "operatore_nome": "operatore/collaboratore assegnato al titolo",
        "operatore_provv": "provvigione dell'operatore 1 (Operatore 1 Provv)",
        "operatore_rit": "ritenuta dell'operatore 1 (Operatore 1 Rit)",
        "operatore_2_nome": "secondo operatore/collaboratore",
        "operatore_2_provv": "provvigione del secondo operatore",
        "operatore_2_rit": "ritenuta del secondo operatore",
        "operatore_3_nome": "terzo operatore/collaboratore",
        "operatore_3_provv": "provvigione del terzo operatore",
        "operatore_3_rit": "ritenuta del terzo operatore",
        "operatore_4_nome": "quarto operatore/collaboratore",
        "operatore_4_provv": "provvigione del quarto operatore",
        "operatore_4_rit": "ritenuta del quarto operatore",
        "pagamento_in_direzione": "premio pagato direttamente in compagnia/direzione (PagatoInCom)",
        "mandato": "mandato / agenzia partner",
        "contraente_cf": "CF/P.IVA del contraente (per creare la polizza se mancante)",
        "contraente_piva": "partita IVA del contraente",
        "contraente_nome": "nome/ragione sociale del contraente",
        "note": "note",
    },
    "sinistro": {
        "numero_sinistro": "numero sinistro (CHIAVE, es. 'Numero Interno')",
        "numero_polizza": "numero polizza/contratto collegato",
        "contraente_cf": "CF/P.IVA contraente",
        "contraente_nome": "nome contraente",
        "compagnia_nome": "compagnia",
        "data_avvenimento": "data avvenimento/accadimento",
        "data_denuncia": "data denuncia/apertura",
        "ramo": "ramo",
        "stato": "stato sinistro (aperto/chiuso/liquidato/...)",
        "descrizione": "descrizione/dinamica/tipologia",
        "riserva": "importo a riserva",
        "liquidazione": "importo liquidato",
        "note": "note",
    },
    "movimento": {
        "data_movimento": "data del movimento/pagamento (Data Pagamento o Data CoGe)",
        "tipo": "tipo operazione: Entrata o Uscita",
        "importo": "importo del movimento (€)",
        "descrizione": "descrizione del pagamento/movimento",
        "mezzo_pagamento": "tipo pagamento (contanti/bonifico/assegno...)",
        "categoria": "categoria contabile (opzionale)",
        "numero_documento": "numero documento (opzionale)",
        "compagnia_nome": "compagnia/mandato (estratto conto compagnia → versamento)",
        "numero_estratto": "numero estratto conto compagnia",
        "data_estratto": "data dell'estratto conto",
        "note": "note prima nota",
    },
}

_POL_ALIASES = {
    "numero_polizza": ["numero polizza", "numpolizza", "n polizza", "polizza", "numero", "contratto", "num polizza"],
    "compagnia_nome": ["compagnia", "compagnia assicurativa", "impresa"],
    "ramo": ["ramo", "ramo assicurativo"],
    "prodotto": ["prodotto", "rischio", "descrizione prodotto", "garanzia"],
    "stato": ["stato", "stato polizza"],
    "effetto": ["effetto", "decor", "decorrenza", "data effetto", "data decorrenza", "inizio"],
    "scadenza": ["scadenza", "scad", "data scadenza", "fine"],
    "data_annullamento": ["data annul", "data annullamento", "annullamento"],
    "data_sospensione": ["data sosp", "data sospensione", "sospensione"],
    "frazionamento": ["frazionamento", "rateazione"],
    "premio_lordo": ["lordo", "premio lordo", "premio", "importo lordo"],
    "premio_netto": ["netto", "premio netto", "imponibile"],
    "premio_tasse": ["imposte", "tasse", "imposta"],
    "premio_ssn": ["ssn"],
    "provvigioni": ["provvigioni", "provvigione"],
    "targa": ["targa"],
    "mezzo_pagamento_preferito": ["mezzo pagamento", "metodo pagamento", "modalita pagamento", "modalitapagamento"],
    "note": ["note", "annotazioni", "caratteristiche"],
    "contraente_cf": ["codice fiscale", "cf contraente", "cfcontraente", "cf"],
    "contraente_piva": ["partita iva", "piva contraente", "piva", "p iva"],
    "contraente_nome": ["contraente", "cliente", "intestatario", "nominativo"],
    "contraente_indirizzo": ["indirizzo", "via", "indirizzo contraente"],
    "contraente_comune": ["comune", "citta", "localita"],
    "contraente_cap": ["cap"],
    "contraente_provincia": ["provincia", "province", "provincia contraente"],
    "contraente_telefono": ["tel contr", "telefono", "tel"],
    "contraente_cellulare": ["cel contr", "cellulare", "cell"],
    "contraente_email": ["mail contr", "email", "mail", "e mail"],
    "operatore_nome": ["operatore 1", "operatori", "operatore", "collaboratore", "produttore", "sub agente", "subagente", "agente"],
}
_TIT_ALIASES = {
    "numero_polizza": ["numero polizza", "numpolizza", "n polizza", "polizza"],
    "numero_titolo": ["numero titolo", "numappendice", "appendice", "n titolo", "titolo", "numero quietanza", "quietanza", "rata"],
    "tipo": ["tipo", "tipo titolo", "tipo quietanza", "tipologia"],
    "effetto": ["effetto", "ratadel", "data rata", "datarata", "rata", "decorrenza", "data effetto"],
    "scadenza": ["scadenza", "prossimascadenza", "scadenzacontratto", "data scadenza"],
    "stato": ["stato", "stato titolo", "stato incasso"],
    "importo_lordo": ["totale", "importo lordo", "lordo", "premio lordo"],
    "importo_netto": ["netto", "imponibile", "importo netto"],
    "imposte": ["imposte", "imprata", "tasse", "addnetti"],
    "importo_pagato": ["importoincassato", "importo incassato", "incassato", "pagato"],
    "provvigioni": ["provvigioni", "provvigione"],
    "data_incasso": ["data incasso", "datapagamento", "data pagamento", "datafatture", "pagato il"],
    "mezzo_pagamento": ["modalitapagamento", "modalita pagamento", "mezzo pagamento", "metodo pagamento", "forma pagamento", "tipo pagamento"],
    "data_copertura": ["data copertura", "datacopertura", "copertura", "coperto il"],
    "compagnia_nome": ["compagnia", "impresa", "compagnia assicurativa"],
    "ramo": ["ramo", "rischio", "ramo assicurativo"],
    "operatore_nome": ["operatori", "operatore", "operatore 1", "collaboratore", "produttore", "sub agente", "subagente", "agente"],
    "operatore_provv": ["operatore 1 provv", "operatore provv"],
    "operatore_rit": ["operatore 1 rit", "operatore rit"],
    "operatore_2_nome": ["operatore 2"],
    "operatore_2_provv": ["operatore 2 provv"],
    "operatore_2_rit": ["operatore 2 rit"],
    "operatore_3_nome": ["operatore 3"],
    "operatore_3_provv": ["operatore 3 provv"],
    "operatore_3_rit": ["operatore 3 rit"],
    "operatore_4_nome": ["operatore 4"],
    "operatore_4_provv": ["operatore 4 provv"],
    "operatore_4_rit": ["operatore 4 rit"],
    "pagamento_in_direzione": ["pagatoincom", "pagato in com", "pagato in compagnia", "pagamento in direzione"],
    "mandato": ["mandato", "agenzia partner", "partner"],
    "contraente_cf": ["cfcontraente", "cf contraente", "codice fiscale contraente", "cfclientipaganti"],
    "contraente_piva": ["piva contraente", "partita iva contraente"],
    "contraente_nome": ["contraente", "cliente", "nominativo"],
    "note": ["note", "annotazioni"],
}
_SIN_ALIASES = {
    "numero_sinistro": ["numero interno", "numero sinistro", "n sinistro", "sinistro", "numero esterno"],
    "numero_polizza": ["contratto", "numero polizza", "polizza"],
    "contraente_cf": ["cf contraente", "codice fiscale", "piva"],
    "contraente_nome": ["contraente", "cliente", "assicurato", "nominativo"],
    "compagnia_nome": ["compagnia", "impresa"],
    "data_avvenimento": ["data avvenimento", "data sinistro", "avvenimento", "data evento", "data"],
    "data_denuncia": ["data denuncia", "denuncia", "data apertura", "apertura"],
    "ramo": ["ramo"],
    "stato": ["stato", "stato sinistro"],
    "descrizione": ["descrizione", "dinamica", "tipologia"],
    "riserva": ["riserva", "importo riserva", "a riserva"],
    "liquidazione": ["liquidazione", "liquidato", "importo liquidato"],
    "note": ["note"],
}
_MOV_ALIASES = {
    "data_movimento": ["data pagamento", "data coge", "datapagamento", "data movimento", "data"],
    "tipo": ["tipo operazione", "tipooperazione", "entrata/uscita", "segno", "dare/avere"],
    "importo": ["importo pagato", "importopagato", "importo", "totale"],
    "descrizione": ["descrizione pagamento", "descrizione", "causale"],
    "mezzo_pagamento": ["tipo pagam", "tipo pagamento", "modalita pagamento", "mezzo pagamento"],
    "compagnia_nome": ["mandato", "compagnia", "impresa", "agenzia partner"],
    "numero_estratto": ["num estratto", "numero estratto", "n estratto", "estratto"],
    "data_estratto": ["data estratto"],
    "numero_documento": ["numero documento", "num documento", "documento"],
    "note": ["note prima nota", "note", "annotazioni"],
}
_ALIAS_BY_ENTITY = {
    "anagrafica": ANAG_ALIASES,
    "polizza": _POL_ALIASES,
    "titolo": _TIT_ALIASES,
    "sinistro": _SIN_ALIASES,
    "movimento": _MOV_ALIASES,
}
ENTITY_ORDER = ["anagrafica", "polizza", "titolo", "sinistro", "movimento"]

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

_CONTR_TO_ANAG = {
    "contraente_nome": "ragione_sociale",
    "contraente_cf": "codice_fiscale",
    "contraente_piva": "partita_iva",
    "contraente_indirizzo": "indirizzo",
    "contraente_comune": "comune",
    "contraente_cap": "cap",
    "contraente_provincia": "provincia",
    "contraente_telefono": "telefono",
    "contraente_cellulare": "cellulare",
    "contraente_email": "email",
}


def _coerce_enums(entity: str, doc: dict):
    for field, allowed in _ENUM_VALUES.get(entity, {}).items():
        v = doc.get(field)
        if v is None:
            continue
        lv = str(v).strip().lower()
        if lv in allowed:
            doc[field] = lv
        else:
            doc.pop(field, None)


_HEADER_TOKENS = None


def _all_header_tokens() -> set:
    """Insieme di tutti i token di intestazione noti (per rilevare la riga header)."""
    global _HEADER_TOKENS
    if _HEADER_TOKENS is None:
        toks: set = set()
        for aliases in _ALIAS_BY_ENTITY.values():
            for al in aliases.values():
                for a in al:
                    toks.add(_normalize_header(a))
        _HEADER_TOKENS = toks
    return _HEADER_TOKENS


def _reframe_header(raw: pd.DataFrame) -> pd.DataFrame:
    """Rileva la riga di intestazione reale (salta righe di preambolo vuote,
    tipiche degli export Excel) e ritorna un DataFrame con header corretto."""
    if raw.empty:
        return raw
    toks = _all_header_tokens()
    best_idx, best_score = 0, -1
    scan = min(25, len(raw))
    for i in range(scan):
        cells = [_normalize_header(str(x)) for x in raw.iloc[i].tolist()]
        nonempty = [c for c in cells if c and c != "nan"]
        if len(nonempty) < 2:
            continue
        matches = sum(1 for c in nonempty if c in toks)
        score = matches * 10 + len(nonempty)
        if score > best_score:
            best_score, best_idx = score, i
    header = [str(x).strip() for x in raw.iloc[best_idx].tolist()]
    seen: dict = {}
    cols: List[str] = []
    for j, h in enumerate(header):
        name = h if (h and h.lower() != "nan") else f"col_{j}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        cols.append(name)
    body = raw.iloc[best_idx + 1:].copy()
    body.columns = cols
    # elimina righe completamente vuote (vettoriale)
    nonempty_row = (body != "").any(axis=1)
    body = body[nonempty_row]
    # elimina colonne segnaposto (col_N) completamente vuote
    if len(body):
        nonempty_col = (body != "").any(axis=0)
        keep = [c for c in cols if (not str(c).startswith("col_")) or bool(nonempty_col.get(c, False))]
        body = body[keep]
    return body.reset_index(drop=True)


def _read_df(content: bytes, filename: str, nrows: Optional[int] = None) -> pd.DataFrame:
    fn = (filename or "").lower()
    if fn.endswith((".xlsx", ".xls", ".xlsm")):
        raw = pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False, header=None)
        df = _reframe_header(raw)
        return df.head(nrows) if nrows is not None else df
    raw = None
    for enc in (None, "latin-1"):
        try:
            raw = pd.read_csv(io.BytesIO(content), sep=None, engine="python", dtype=str,
                              keep_default_na=False, header=None, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            raise HTTPException(400, f"Impossibile leggere il file: {e}")
    if raw is None:
        raise HTTPException(400, "Impossibile leggere il file (encoding)")
    df = _reframe_header(raw)
    return df.head(nrows) if nrows is not None else df


def _count_rows(content: bytes, filename: str) -> int:
    fn = (filename or "").lower()
    if fn.endswith((".xlsx", ".xls", ".xlsm")):
        try:
            return int(len(_read_df(content, filename)))
        except Exception:
            return 0
    n = content.count(b"\n")
    if content and not content.endswith(b"\n"):
        n += 1
    return max(0, n - 1)


def _detect_entity_heuristic(headers: List[str]) -> str:
    blob = " | ".join(_normalize_header(h) for h in headers)
    has = lambda *ks: any(k in blob for k in ks)
    # movimento / prima nota / estratto conto: SOLO segnali forti (NON "mandato",
    # che è presente anche nei portafogli polizze)
    if has("tipo operazione", "importo pagato", "descrizione pagamento", "data coge",
           "prima nota", "num estratto", "numero estratto"):
        return "movimento"
    if has("numero sinistro", "numero interno", "avvenimento", "denuncia", "liquidato", "riserva"):
        return "sinistro"
    if has("modalitapagamento", "importoincassato", "datapagamento", "numappendice", "quietanza"):
        return "titolo"
    # polizza / portafoglio: numero polizza esplicito OPPURE (ramo + contraente + data)
    if has("numpolizza", "numero polizza", "polizza", "contratto") or (
        has("ramo") and has("contraente", "codice fiscale", "partita iva")
        and has("decor", "decorrenza", "scad", "scadenza", "effetto")
    ):
        return "polizza"
    return "anagrafica"


def _detect_mapping_heuristic(entity: str, headers: List[str]) -> dict:
    aliases = _ALIAS_BY_ENTITY.get(entity, {})
    mapping, used = {}, set()
    for h in headers:
        norm = _normalize_header(h)
        # Ignora le colonne "alla firma" (premio/provv. iniziale): non sono i
        # valori ricorrenti e rubavano il mapping a Lordo/Netto/Provvigioni.
        if "firma" in norm.split():
            mapping[str(h)] = None
            continue
        best, best_score = None, 0.0
        for canonical, al in aliases.items():
            if canonical in used:
                continue
            for a in al:
                sc = _similarity(norm, _normalize_header(a))
                if sc > best_score:
                    best_score, best = sc, canonical
        mapping[str(h)] = best if (best and best_score >= 0.72) else None
        if mapping[str(h)]:
            used.add(best)
    return mapping


async def _ai_detect(headers: List[str], samples: List[dict]) -> Optional[dict]:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        prompt = (
            "Sei un esperto di migrazione dati per CRM assicurativi italiani. "
            "Analizza le colonne di un file e determina:\n"
            "1) L'ENTITÀ del file tra: anagrafica, polizza, titolo, sinistro.\n"
            "2) Il MAPPING di ogni colonna verso i campi canonici (o null).\n\n"
            f"CAMPI CANONICI PER ENTITÀ:\n{json.dumps(ENTITY_FIELDS, ensure_ascii=False)}\n\n"
            f"COLONNE: {json.dumps(headers, ensure_ascii=False)}\n\n"
            f"ESEMPI (prime {len(samples)} righe): {json.dumps(samples, ensure_ascii=False, default=str)}\n\n"
            "REGOLE IMPORTANTI:\n"
            "- Un file 'portafoglio' con Numero/Ramo/Compagnia/Decorrenza/Contraente è ENTITÀ 'polizza' "
            "(NON 'movimento', anche se contiene la colonna 'Mandato').\n"
            "- IGNORA (mappa a null) le colonne che finiscono con '_firma' o '(firma)' "
            "(es. Lordo_firma, Netto_firma, Provv_firma): sono valori 'alla firma', NON i valori ricorrenti. "
            "Per i premi usa le colonne senza suffisso: Lordo→premio_lordo, Netto→premio_netto, Imposte→premio_tasse, "
            "Provvigioni→provvigioni.\n"
            "- 'Provv_firma' NON è la provincia: non mapparla a contraente_provincia.\n"
            "- Se il file è un PORTAFOGLIO polizze, mappa ANCHE i dati anagrafici del CONTRAENTE "
            "presenti nella stessa riga (indirizzo, comune, cap, provincia, telefono, cellulare, email, "
            "codice fiscale, partita iva) ai campi contraente_*.\n"
            "- NON mappare i dati dell'ASSICURATO se in colonne separate dal contraente (null).\n"
            "- NON mappare DUE colonne diverse allo STESSO campo: scegli la più corretta.\n"
            "- Non mappare colonne di nomi/persone al campo 'note'.\n\n"
            "Rispondi SOLO con JSON valido:\n"
            '{\"entity\": \"<...>\", \"confidence\": <0..1>, \"mapping\": {\"<header esatto>\": \"<campo|null>\"}}'
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
        mapping, used = {}, set()
        for h in headers:
            v = raw_map.get(str(h))
            if v in valid_fields and v not in used:
                mapping[str(h)] = v
                used.add(v)
            else:
                mapping[str(h)] = None
        return {"entity": ent, "confidence": float(data.get("confidence") or 0.7), "mapping": mapping}
    except Exception:
        return None


_DATE_FIELDS = {"data_nascita", "effetto", "scadenza", "data_incasso", "data_avvenimento",
                "data_denuncia", "data_annullamento", "data_sospensione", "contraente_data_nascita",
                "data_movimento", "data_estratto", "data_copertura"}
_NUM_FIELDS = {"premio_lordo", "premio_netto", "premio_tasse", "premio_ssn", "provvigioni",
               "importo_lordo", "importo_netto", "imposte", "importo_pagato", "riserva", "liquidazione",
               "importo"}
_UPPER_FIELDS = {"ragione_sociale", "nome", "cognome", "contraente_nome", "compagnia_nome",
                 "comune", "indirizzo", "contraente_comune", "contraente_indirizzo", "provincia",
                 "contraente_provincia"}
_CODE_FIELDS = {"codice_fiscale", "partita_iva", "contraente_cf", "contraente_piva", "targa"}


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip().replace("€", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return round(float(re.sub(r"[^0-9.\-]", "", s)), 2)
    except Exception:
        return None


def _row_to_record(row_values: dict, mapping: dict) -> dict:
    rec: dict = {}
    for header, canonical in mapping.items():
        if not canonical or canonical in rec:
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
        elif canonical in _CODE_FIELDS:
            if canonical in ("partita_iva", "contraente_piva"):
                val = _norm_piva(val)
                if val is None:
                    continue
            else:
                val = val.upper().replace(" ", "")
        elif canonical in ("email", "contraente_email", "pec"):
            val = val.lower()
        elif canonical in _UPPER_FIELDS:
            val = val.upper()
        rec[canonical] = val
    return rec


def _norm_name(s: Optional[str]) -> str:
    if not s:
        return ""
    s = _normalize_header(s)
    for tok in ["srl", "s r l", "spa", "s p a", "snc", "s n c", "sas", "s a s", "sc", "societa", "ditta"]:
        s = re.sub(rf"\b{tok}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _name_similarity(a: str, b: str) -> float:
    a, b = _norm_name(a), _norm_name(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    if not files:
        raise HTTPException(400, "Nessun file caricato")
    sid = uuid.uuid4().hex
    now_iso = datetime.now(timezone.utc).isoformat()
    bucket = _gridfs()
    file_summaries = []

    for fi, uf in enumerate(files):
        content = await uf.read()
        if not content:
            continue
        try:
            df = _read_df(content, uf.filename, nrows=6)
        except HTTPException:
            file_summaries.append({"file_index": fi, "filename": uf.filename, "error": "Formato non leggibile"})
            continue
        if df.empty:
            file_summaries.append({"file_index": fi, "filename": uf.filename, "error": "File vuoto", "total_rows": 0})
            continue
        headers = [str(h) for h in df.columns]
        samples = [{h: _sanitize_value(r[h]) for h in headers} for _, r in df.head(3).iterrows()]

        ai = await _ai_detect(headers, samples)
        if ai:
            entity, mapping, conf, source = ai["entity"], ai["mapping"], ai["confidence"], "ai"
        else:
            entity = _detect_entity_heuristic(headers)
            mapping = _detect_mapping_heuristic(entity, headers)
            conf, source = 0.5, "euristica"

        preview = [{"raw": s, "normalized": _row_to_record(s, mapping)} for s in samples]
        total = _count_rows(content, uf.filename)

        gid = await bucket.upload_from_stream(f"{sid}_{fi}_{uf.filename}", content)
        file_summaries.append({
            "file_index": fi, "filename": uf.filename, "gridfs_id": str(gid),
            "entity": entity, "entity_confidence": round(conf, 2), "mapping_source": source,
            "headers": headers, "mapping": mapping, "total_rows": total,
            "available_fields": ENTITY_FIELDS[entity], "preview": preview,
        })

    session = {
        "id": sid, "created_at": now_iso, "user_id": user.get("id"),
        "status": "pronto", "files": file_summaries, "progress": None, "result": None,
    }
    await db.import_massivo_sessioni.insert_one(dict(session))
    session.pop("_id", None)
    return session


@router.post("/{sid}/commit")
async def commit_import(
    sid: str,
    plan: List[dict] = Body(..., embed=True),
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
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


async def _df_for_file(fmeta: dict) -> Optional[pd.DataFrame]:
    gid = fmeta.get("gridfs_id")
    if not gid:
        return None
    stream = await _gridfs().open_download_stream(ObjectId(gid))
    content = await stream.read()
    return _read_df(content, fmeta.get("filename") or "file.csv")


def _fill_missing(existing: dict, new: dict) -> dict:
    upd = {}
    for k, v in new.items():
        if v in (None, "", []):
            continue
        cur = existing.get(k)
        if cur in (None, "", []) or (isinstance(cur, (int, float)) and cur == 0 and isinstance(v, (int, float)) and v != 0):
            upd[k] = v
    return upd


def _tag_generazionale(data_nascita: Optional[str]) -> Optional[str]:
    """Ritorna il tag generazionale in base all'anno di nascita (YYYY-MM-DD)."""
    if not data_nascita or len(str(data_nascita)) < 4:
        return None
    try:
        anno = int(str(data_nascita)[:4])
    except ValueError:
        return None
    if anno <= 1945:
        return "Generazione Silenziosa"
    if anno <= 1964:
        return "Baby Boomer"
    if anno <= 1980:
        return "Generazione X"
    if anno <= 1996:
        return "Millennial"
    if anno <= 2012:
        return "Generazione Z"
    return "Generazione Alpha"


def _enrich_anagrafica(ana: dict) -> None:
    """Arricchisce l'anagrafica dai dati inferibili (mutazione in-place):
    - dal CF: sesso, data_nascita, comune_nascita, provincia_nascita
    - canali avvisi: email→email, cellulare→whatsapp+sms
    - tag generazionale dall'anno di nascita
    """
    cf = ana.get("codice_fiscale")
    if cf:
        try:
            dec = cf_calc.decodifica_cf(cf)
            for k in ("sesso", "data_nascita", "comune_nascita", "provincia_nascita"):
                if dec.get(k) and not ana.get(k):
                    ana[k] = dec[k]
        except Exception:
            pass
    if ana.get("email"):
        ana["canale_email"] = True
    if ana.get("cellulare"):
        ana["canale_whatsapp"] = True
        ana["canale_sms"] = True
    tag = _tag_generazionale(ana.get("data_nascita"))
    if tag:
        tags = list(ana.get("tags") or [])
        if tag not in tags:
            tags.append(tag)
        ana["tags"] = tags


async def _run_commit(sid: str, plan: List[dict], user: dict):
    try:
        await _run_commit_inner(sid, plan, user)
    except Exception as e:
        await db.import_massivo_sessioni.update_one({"id": sid}, {"$set": {
            "status": "errore",
            "progress.fase": "errore",
            "result": {"errore": str(e)[:300], "creati": 0, "aggiornati": 0,
                       "saltati": 0, "errori": 0, "errori_dettaglio": []},
        }})


async def _run_commit_inner(sid: str, plan: List[dict], user: dict):
    from db_models import Anagrafica, Polizza, Titolo, Sinistro, Compagnia, MezzoPagamento, Banca, UserPublic, MovimentoContabile
    from auth import hash_password

    sess = await db.import_massivo_sessioni.find_one({"id": sid}, {"_id": 0})
    files_meta = {f["file_index"]: f for f in (sess.get("files") or []) if not f.get("error")}
    now_iso = datetime.now(timezone.utc).isoformat()
    stats = {"creati": 0, "aggiornati": 0, "saltati": 0, "errori": 0}
    errori_dett: List[dict] = []
    processed = 0

    comp_cache: dict = {}
    anag_cache: dict = {}
    pol_cache: dict = {}
    mezzo_cache: dict = {}
    banca_cache: dict = {}
    operatore_cache: dict = {}
    # Elementi auto-creati durante l'import (per il riepilogo finale)
    auto_creati = {"compagnie": [], "mezzi_pagamento": [], "banche": [],
                   "collaboratori": [], "polizze_da_titolo": []}
    geocode_queue: List[str] = []
    buffers = {"anagrafiche": [], "polizze": [], "titoli": [], "sinistri": [], "movimenti": []}

    async def _flush(col: Optional[str] = None):
        for c in ([col] if col else list(buffers.keys())):
            if buffers[c]:
                await db[c].insert_many(buffers[c], ordered=False)
                buffers[c] = []

    async def _progress(force: bool = False):
        if force or processed % _PROGRESS_EVERY == 0:
            await db.import_massivo_sessioni.update_one({"id": sid}, {"$set": {
                "progress.elaborate": processed, **{f"progress.{k}": v for k, v in stats.items()}}})

    async def _compagnia_id(nome: Optional[str]) -> Optional[str]:
        if not nome:
            return None
        key = _norm_name(nome)
        if key in comp_cache:
            return comp_cache[key]
        doc = await db.compagnie.find_one({"$or": [
            {"nome": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
            {"ragione_sociale": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
        ]}, {"_id": 0, "id": 1})
        if not doc:
            allc = await db.compagnie.find({}, {"_id": 0, "id": 1, "ragione_sociale": 1, "nome": 1}).to_list(1000)
            best, bsc = None, 0.0
            for c in allc:
                sc = max(_name_similarity(nome, c.get("ragione_sociale")), _name_similarity(nome, c.get("nome") or ""))
                if sc > bsc:
                    bsc, best = sc, c
            if best and bsc >= 0.9:
                doc = {"id": best["id"]}
        if not doc:
            codice = (re.sub(r"[^A-Z0-9]", "", nome.upper())[:8] or "IMP") + "-" + uuid.uuid4().hex[:4].upper()
            obj = Compagnia(codice=codice, ragione_sociale=nome.upper(),
                            descrizione="Creata automaticamente da Import Massivo")
            newdoc = obj.model_dump()
            await db.compagnie.insert_one(newdoc)
            doc = {"id": newdoc["id"]}
        comp_cache[key] = doc["id"]
        return doc["id"]

    async def _upsert_anagrafica(ana: dict) -> Optional[str]:
        cf = ana.get("codice_fiscale")
        piva = ana.get("partita_iva")
        if not ana.get("ragione_sociale"):
            rs = f"{ana.get('cognome') or ''} {ana.get('nome') or ''}".strip()
            if rs:
                ana["ragione_sociale"] = rs
        nome = ana.get("ragione_sociale")
        if not (cf or piva or nome):
            return None
        _enrich_anagrafica(ana)
        ck = cf or piva or _norm_name(nome)
        if ck in anag_cache:
            return anag_cache[ck]
        existing = None
        if cf:
            existing = await db.anagrafiche.find_one({"codice_fiscale": cf}, {"_id": 0})
        if not existing and piva:
            existing = await db.anagrafiche.find_one({"partita_iva": piva}, {"_id": 0})
        if not existing and nome:
            first = _norm_name(nome).split(' ')[0]
            if first:
                cand = await db.anagrafiche.find(
                    {"ragione_sociale": {"$regex": re.escape(first), "$options": "i"}},
                    {"_id": 0, "id": 1, "ragione_sociale": 1}).to_list(30)
                best, bsc = None, 0.0
                for c in cand:
                    sc = _name_similarity(nome, c.get("ragione_sociale"))
                    if sc > bsc:
                        bsc, best = sc, c
                if best and bsc >= 0.9:
                    existing = await db.anagrafiche.find_one({"id": best["id"]}, {"_id": 0})
        if existing:
            upd = _fill_missing(existing, {k: v for k, v in ana.items() if k in Anagrafica.model_fields})
            if upd:
                upd["updated_at"] = now_iso
                await db.anagrafiche.update_one({"id": existing["id"]}, {"$set": upd})
                stats["aggiornati"] += 1
            anag_cache[ck] = existing["id"]
            return existing["id"]
        if ana.get("iban"):
            ana["conti_correnti"] = [{"iban": ana.pop("iban"), "principale": True, "note": "Import massivo"}]
        tp = str(ana.get("tipo") or "").strip().lower()
        if tp in ("privato", "persona fisica", "pf", "fisica", "privata"):
            ana["tipo"] = "persona_fisica"
        elif tp and tp not in ("persona_fisica", "persona_giuridica"):
            ana["tipo"] = "persona_giuridica"
        if ana.get("tipo") not in ("persona_fisica", "persona_giuridica"):
            ana["tipo"] = "persona_giuridica" if (piva and len(cf or "") != 16) else "persona_fisica"
        # REGOLA FERREA: qualsiasi anagrafica con Partita IVA è persona giuridica
        if (ana.get("partita_iva") or "").strip():
            ana["tipo"] = "persona_giuridica"
        ana.setdefault("collaboratore_id", user.get("id"))
        obj = Anagrafica(**{k: v for k, v in ana.items() if k in Anagrafica.model_fields})
        buffers["anagrafiche"].append(obj.model_dump())
        if len(buffers["anagrafiche"]) >= _FLUSH:
            await _flush("anagrafiche")
        anag_cache[ck] = obj.id
        if ana.get("indirizzo"):
            geocode_queue.append(obj.id)
        stats["creati"] += 1
        return obj.id

    async def _polizza_id(numero: Optional[str]) -> Optional[str]:
        if not numero:
            return None
        if numero in pol_cache:
            return pol_cache[numero]
        doc = await db.polizze.find_one({"numero_polizza": numero}, {"_id": 0, "id": 1})
        pol_cache[numero] = doc["id"] if doc else None
        return pol_cache[numero]

    async def _mezzo_pagamento_codice(nome: Optional[str]) -> Optional[str]:
        """Trova (o crea) un mezzo di pagamento e ritorna il suo codice."""
        if not nome or not str(nome).strip():
            return None
        raw = str(nome).strip()
        key = _norm_name(raw)
        if key in mezzo_cache:
            return mezzo_cache[key]
        doc = await db.mezzi_pagamento.find_one({"$or": [
            {"codice": {"$regex": f"^{re.escape(raw)}$", "$options": "i"}},
            {"label": {"$regex": f"^{re.escape(raw)}$", "$options": "i"}},
        ]}, {"_id": 0, "codice": 1})
        if doc:
            mezzo_cache[key] = doc["codice"]
            return doc["codice"]
        codice = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_") or "altro"
        obj = MezzoPagamento(codice=codice, label=raw, tipo_conto="altro")
        await db.mezzi_pagamento.insert_one(obj.model_dump())
        mezzo_cache[key] = codice
        auto_creati["mezzi_pagamento"].append(raw)
        return codice

    async def _banca_id(nome: Optional[str]) -> Optional[str]:
        """Trova (o crea) una banca e ritorna il suo id."""
        if not nome or not str(nome).strip():
            return None
        raw = str(nome).strip()
        key = _norm_name(raw)
        if key in banca_cache:
            return banca_cache[key]
        doc = await db.banche.find_one(
            {"nome": {"$regex": f"^{re.escape(raw)}$", "$options": "i"}}, {"_id": 0, "id": 1})
        if doc:
            banca_cache[key] = doc["id"]
            return doc["id"]
        obj = Banca(nome=raw.upper(), note="Creata automaticamente da Import Massivo")
        newdoc = obj.model_dump()
        await db.banche.insert_one(newdoc)
        banca_cache[key] = newdoc["id"]
        auto_creati["banche"].append(raw)
        return newdoc["id"]

    async def _operatore_id(nome: Optional[str]) -> Optional[str]:
        """Collega l'operatore a un collaboratore esistente (per nome).
        Se non esiste, crea un collaboratore con solo nome (da completare in Librerie)."""
        if not nome or not str(nome).strip():
            return None
        raw = str(nome).strip()
        key = _norm_name(raw)
        if key in operatore_cache:
            return operatore_cache[key]
        tid = user.get("agenzia_tenant_id")
        # match per nome tra gli utenti della STESSA agenzia
        q = {"role": {"$in": ["collaboratore", "dipendente", "admin"]}}
        if tid:
            q["agenzia_tenant_id"] = tid
        cand = await db.users.find(q, {"_id": 0, "id": 1, "name": 1}).to_list(500)
        for c in cand:
            if _norm_name(c.get("name") or "") == key:
                operatore_cache[key] = c["id"]
                return c["id"]
        # crea collaboratore "bozza" con solo nome (da completare in Librerie)
        slug = re.sub(r"[^a-z0-9]+", ".", raw.lower()).strip(".") or "operatore"
        email = f"{slug}.{uuid.uuid4().hex[:6]}@import.assicurapro.it"
        udoc = UserPublic(email=email, name=raw.upper(), role="collaboratore").model_dump()
        udoc["password_hash"] = hash_password(uuid.uuid4().hex)
        udoc["da_completare"] = True  # flag: creato da import, da ultimare in Librerie
        if tid:
            udoc["agenzia_tenant_id"] = tid
        await db.users.insert_one(udoc)
        operatore_cache[key] = udoc["id"]
        auto_creati["collaboratori"].append(raw)
        return udoc["id"]

    plan_sorted = sorted(plan, key=lambda p: ENTITY_ORDER.index(p["entity"]) if p.get("entity") in ENTITY_ORDER else 99)

    for p in plan_sorted:
        entity = p.get("entity")
        mapping = p.get("mapping") or {}
        fmeta = files_meta.get(p.get("file_index"))
        if not fmeta or entity not in ENTITY_FIELDS:
            continue
        df = await _df_for_file(fmeta)
        if df is None or df.empty:
            continue
        await db.import_massivo_sessioni.update_one({"id": sid}, {"$set": {"progress.fase": f"import {entity}"}})
        headers = [str(h) for h in df.columns]

        for ridx, row in df.iterrows():
            processed += 1
            try:
                rd = {h: _sanitize_value(row[h]) for h in headers}
                rec = _row_to_record(rd, mapping)

                if entity == "anagrafica":
                    await _upsert_anagrafica({k: v for k, v in rec.items() if k in Anagrafica.model_fields or k == "iban"})

                elif entity == "polizza":
                    num = rec.get("numero_polizza")
                    if not num:
                        stats["saltati"] += 1
                        if len(errori_dett) < _ERR_CAP:
                            errori_dett.append({"row": int(ridx) + 2, "entity": "polizza",
                                                "reason": "numero polizza mancante"})
                        await _progress(); continue
                    ana = {ak: rec[ck] for ck, ak in _CONTR_TO_ANAG.items() if rec.get(ck)}
                    contr_id = await _upsert_anagrafica(ana) if ana else None
                    comp_id = await _compagnia_id(rec.get("compagnia_nome"))
                    p_operatore = rec.pop("operatore_nome", None)
                    p_op_id = await _operatore_id(p_operatore)
                    doc = {k: v for k, v in rec.items() if k in Polizza.model_fields}
                    if p_op_id:
                        doc["collaboratore_id"] = p_op_id
                    if rec.get("data_annullamento"):
                        doc["stato"] = "annullata"
                    elif rec.get("data_sospensione"):
                        doc["stato"] = "sospesa"
                    _coerce_enums("polizza", doc)
                    if contr_id:
                        doc["contraente_id"] = contr_id
                    if comp_id:
                        doc["compagnia_id"] = comp_id
                    existing_id = await _polizza_id(num)
                    if existing_id:
                        existing = await db.polizze.find_one({"id": existing_id}, {"_id": 0})
                        upd = _fill_missing(existing, doc)
                        if upd:
                            upd["updated_at"] = now_iso
                            await db.polizze.update_one({"id": existing_id}, {"$set": upd})
                            stats["aggiornati"] += 1
                        else:
                            stats["saltati"] += 1
                    else:
                        if not doc.get("compagnia_id"):
                            doc["compagnia_id"] = await _compagnia_id("SCONOSCIUTA")
                        doc["ramo"] = doc.get("ramo") or "N/D"
                        doc["effetto"] = doc.get("effetto") or ""
                        doc["scadenza"] = doc.get("scadenza") or ""
                        if not doc.get("contraente_id"):
                            stats["saltati"] += 1
                            if len(errori_dett) < _ERR_CAP:
                                errori_dett.append({"row": int(ridx) + 2, "entity": "polizza",
                                                    "reason": f"contraente non trovato per polizza '{num}'"})
                            await _progress(); continue
                        doc.setdefault("collaboratore_id", user.get("id"))
                        obj = Polizza(**doc)
                        buffers["polizze"].append(obj.model_dump())
                        pol_cache[num] = obj.id
                        if len(buffers["polizze"]) >= _FLUSH:
                            await _flush("polizze")
                        stats["creati"] += 1

                elif entity == "titolo":
                    num_pol = rec.pop("numero_polizza", None)
                    # campi extra (non del modello Titolo) per collegamenti/auto-creazione
                    t_compagnia = rec.pop("compagnia_nome", None)
                    t_ramo = rec.pop("ramo", None)
                    t_operatore = rec.pop("operatore_nome", None)
                    t_mandato = rec.pop("mandato", None)
                    t_contr_cf = rec.pop("contraente_cf", None)
                    t_contr_piva = rec.pop("contraente_piva", None)
                    t_contr_nome = rec.pop("contraente_nome", None)
                    # Operatore → collaboratore (crea bozza se manca) — risolto subito
                    op_id = await _operatore_id(t_operatore)
                    if num_pol and num_pol not in pol_cache:
                        await _flush("polizze")
                    pol_id = await _polizza_id(num_pol)
                    if not pol_id:
                        if not num_pol:
                            stats["saltati"] += 1
                            if len(errori_dett) < _ERR_CAP:
                                errori_dett.append({"row": int(ridx) + 2, "entity": "titolo",
                                                    "reason": "numero polizza mancante"})
                            await _progress(); continue
                        # Polizza inesistente → la creo al volo (minima) e la segnalo
                        ana = {}
                        if t_contr_cf:
                            ana["codice_fiscale"] = t_contr_cf
                        if t_contr_piva:
                            ana["partita_iva"] = t_contr_piva
                        if t_contr_nome:
                            ana["ragione_sociale"] = t_contr_nome
                        contr_id = await _upsert_anagrafica(ana) if ana else None
                        if not contr_id:
                            ana = {"ragione_sociale": f"CONTRAENTE POLIZZA {num_pol}"}
                            contr_id = await _upsert_anagrafica(ana)
                        pol_doc = {
                            "numero_polizza": num_pol,
                            "compagnia_id": await _compagnia_id(t_compagnia or "SCONOSCIUTA"),
                            "contraente_id": contr_id,
                            "ramo": (t_ramo or "N/D"),
                            "effetto": rec.get("effetto") or "",
                            "scadenza": rec.get("scadenza") or "",
                            "collaboratore_id": op_id or user.get("id"),
                            "creata_da_import": True,
                        }
                        if t_mandato:
                            pol_doc["mandato"] = t_mandato
                        polobj = Polizza(**{k: v for k, v in pol_doc.items() if k in Polizza.model_fields})
                        buffers["polizze"].append(polobj.model_dump())
                        await _flush("polizze")
                        pol_cache[num_pol] = polobj.id
                        pol_id = polobj.id
                        stats["creati"] += 1
                        if len(auto_creati["polizze_da_titolo"]) < 500:
                            auto_creati["polizze_da_titolo"].append(num_pol)
                    doc = {k: v for k, v in rec.items() if k in Titolo.model_fields}
                    doc["polizza_id"] = pol_id
                    # Ripartizione provvigioni sui 4 operatori del flusso (Operatore N + Provv + Rit)
                    provv_ops = []
                    for idx_op, nome_op in ((1, t_operatore), (2, rec.pop("operatore_2_nome", None)),
                                            (3, rec.pop("operatore_3_nome", None)), (4, rec.pop("operatore_4_nome", None))):
                        pref = "operatore_" if idx_op == 1 else f"operatore_{idx_op}_"
                        p_val = rec.pop(f"{pref}provv", None)
                        r_val = rec.pop(f"{pref}rit", None)
                        if not nome_op and not p_val:
                            continue
                        op_ident = op_id if idx_op == 1 else await _operatore_id(nome_op)
                        provv_ops.append({
                            "operatore_id": op_ident,
                            "operatore_nome": nome_op,
                            "provvigione": _to_float(p_val) or 0.0,
                            "ritenuta": _to_float(r_val) or 0.0,
                        })
                    if provv_ops:
                        doc["provvigioni_operatori"] = provv_ops
                    # PagatoInCom → premio pagato in direzione (no cassa)
                    dir_raw = rec.get("pagamento_in_direzione")
                    if dir_raw is not None:
                        doc["pagamento_in_direzione"] = str(dir_raw).strip().lower() in (
                            "1", "s", "si", "sì", "x", "true", "vero", "y", "yes")
                    # Operatore già risolto sopra → assegnato anche al titolo
                    doc["collaboratore_id"] = op_id or doc.get("collaboratore_id") or user.get("id")
                    # Metodo di pagamento → codice (auto-crea se manca)
                    if rec.get("mezzo_pagamento"):
                        cod = await _mezzo_pagamento_codice(rec.get("mezzo_pagamento"))
                        if cod:
                            doc["mezzo_pagamento"] = cod
                    # Se c'è la data pagamento → titolo INCASSATO (visibile nei Titoli Storici)
                    if doc.get("data_incasso"):
                        doc["stato"] = "incassato"
                        doc.setdefault("importo_pagato", doc.get("importo_lordo"))
                    # Data copertura → titolo COPERTO
                    if doc.get("data_copertura"):
                        doc["titolo_coperto"] = True
                    doc["caricato_da_import"] = True
                    doc["effetto"] = doc.get("effetto") or ""
                    doc["scadenza"] = doc.get("scadenza") or ""
                    _coerce_enums("titolo", doc)
                    obj = Titolo(**doc)
                    buffers["titoli"].append(obj.model_dump())
                    if len(buffers["titoli"]) >= _FLUSH:
                        await _flush("titoli")
                    stats["creati"] += 1

                elif entity == "sinistro":
                    num = rec.get("numero_sinistro")
                    if not num:
                        stats["saltati"] += 1
                        if len(errori_dett) < _ERR_CAP:
                            errori_dett.append({"row": int(ridx) + 2, "entity": "sinistro",
                                                "reason": "numero sinistro mancante"})
                        await _progress(); continue
                    num_pol = rec.pop("numero_polizza", None)
                    if num_pol and num_pol not in pol_cache:
                        await _flush("polizze")
                    pol_id = await _polizza_id(num_pol)
                    ana = {}
                    if rec.get("contraente_cf"):
                        ana["codice_fiscale"] = rec["contraente_cf"]
                    if rec.get("contraente_nome"):
                        ana["ragione_sociale"] = rec["contraente_nome"]
                    contr_id = await _upsert_anagrafica(ana) if ana else None
                    comp_id = await _compagnia_id(rec.get("compagnia_nome"))
                    doc = {k: v for k, v in rec.items() if k in Sinistro.model_fields}
                    if pol_id:
                        doc["polizza_id"] = pol_id
                    if contr_id:
                        doc["contraente_id"] = contr_id
                    if comp_id:
                        doc["compagnia_id"] = comp_id
                    _coerce_enums("sinistro", doc)
                    existing = await db.sinistri.find_one({"numero_sinistro": num}, {"_id": 0})
                    if existing:
                        upd = _fill_missing(existing, doc)
                        if upd:
                            upd["updated_at"] = now_iso
                            await db.sinistri.update_one({"id": existing["id"]}, {"$set": upd})
                            stats["aggiornati"] += 1
                        else:
                            stats["saltati"] += 1
                    else:
                        doc.setdefault("collaboratore_id", user.get("id"))
                        obj = Sinistro(**doc)
                        buffers["sinistri"].append(obj.model_dump())
                        if len(buffers["sinistri"]) >= _FLUSH:
                            await _flush("sinistri")
                        stats["creati"] += 1

                elif entity == "movimento":
                    imp = rec.get("importo")
                    if imp in (None, "", 0):
                        stats["saltati"] += 1
                        if len(errori_dett) < _ERR_CAP:
                            errori_dett.append({"row": int(ridx) + 2, "entity": "movimento", "reason": "importo mancante"})
                        await _progress(); continue
                    t_compagnia = rec.get("compagnia_nome")
                    num_estratto = rec.get("numero_estratto")
                    tipo_raw = str(rec.get("tipo") or "").strip().lower()
                    # Estratto conto compagnia (Mandato + Num. Estratto): è un VERSAMENTO
                    # alla compagnia → uscita, categoria pagamento_compagnia.
                    is_estratto = bool(t_compagnia or num_estratto)
                    if tipo_raw.startswith("u") or "uscit" in tipo_raw or tipo_raw in ("avere", "-"):
                        tipo = "uscita"
                    elif is_estratto:
                        tipo = "uscita"
                    else:
                        tipo = "entrata"
                    comp_id = await _compagnia_id(t_compagnia) if t_compagnia else None
                    descr = rec.get("descrizione")
                    if not descr and is_estratto:
                        parti = []
                        if t_compagnia:
                            parti.append(str(t_compagnia))
                        if num_estratto:
                            parti.append(f"Estratto n. {num_estratto}")
                        descr = "Versamento compagnia — " + " · ".join(parti) if parti else "Versamento compagnia"
                    mdoc = {
                        "data_movimento": rec.get("data_movimento") or rec.get("data_estratto") or now_iso[:10],
                        "tipo": tipo,
                        "categoria": "pagamento_compagnia" if is_estratto else (rec.get("categoria") or "altro"),
                        "importo": abs(float(imp)),
                        "descrizione": descr or "Movimento importato",
                        "mezzo_pagamento": rec.get("mezzo_pagamento"),
                        "numero_documento": rec.get("numero_documento") or num_estratto,
                        "compagnia_id": comp_id,
                        "note": rec.get("note"),
                        "origine_import": True,
                    }
                    _coerce_enums("movimento", mdoc)
                    obj = MovimentoContabile(**{k: v for k, v in mdoc.items() if k in MovimentoContabile.model_fields})
                    buffers["movimenti"].append(obj.model_dump())
                    if len(buffers["movimenti"]) >= _FLUSH:
                        await _flush("movimenti")
                    stats["creati"] += 1

            except Exception as e:
                stats["errori"] += 1
                if len(errori_dett) < _ERR_CAP:
                    errori_dett.append({"row": int(ridx) + 2, "entity": entity, "reason": str(e)[:200]})
                await _progress()

        await _flush()

    await _flush()
    auto_creati_tot = {k: len(v) for k, v in auto_creati.items()}
    await db.import_massivo_sessioni.update_one({"id": sid}, {"$set": {
        "status": "completato",
        "progress.fase": "completato",
        "progress.elaborate": processed,
        **{f"progress.{k}": v for k, v in stats.items()},
        "result": {**stats, "errori_dettaglio": errori_dett[:_ERR_CAP],
                   "errori_dettaglio_totali": len(errori_dett),
                   "auto_creati": {k: v[:200] for k, v in auto_creati.items()},
                   "auto_creati_totali": auto_creati_tot},
        "completed_at": now_iso,
    }})
    try:
        bucket = _gridfs()
        for f in files_meta.values():
            if f.get("gridfs_id"):
                await bucket.delete(ObjectId(f["gridfs_id"]))
    except Exception:
        pass
    try:
        await log_attivita(user, "import", "massivo", sid,
                           f"Import massivo: +{stats['creati']} creati, {stats['aggiornati']} aggiornati, "
                           f"{stats['saltati']} saltati, {stats['errori']} errori")
    except Exception:
        pass
    # Geocoding automatico (best-effort, throttled) delle nuove anagrafiche con indirizzo
    if geocode_queue:
        asyncio.create_task(_geocode_anagrafiche(geocode_queue[:500]))


async def _geocode_anagrafiche(ids: List[str]):
    """Geocoding throttled (~1 req/sec Nominatim) delle anagrafiche appena create."""
    import geocoder as geocoder_svc
    for aid in ids:
        try:
            ana = await db.anagrafiche.find_one({"id": aid}, {"_id": 0})
            if not ana or ana.get("lat") or not ana.get("indirizzo"):
                continue
            res = await geocoder_svc.geocoda_indirizzo(
                indirizzo=ana.get("indirizzo") or "", comune=ana.get("comune"),
                cap=ana.get("cap"), provincia=ana.get("provincia"), nazione="Italia")
            if res and res.get("lat"):
                await db.anagrafiche.update_one({"id": aid}, {"$set": {
                    "lat": res["lat"], "lng": res["lng"],
                    "indirizzo_geocoded": res.get("display_name")}})
        except Exception:
            pass
        await asyncio.sleep(1.1)



# ==========================================================================
# IMPORT "METODO DI PAGAMENTO" (secondo file) — rettifica tipo pagamento +
# data copertura sui TITOLI già importati (match per numero polizza + data)
# e imposta il metodo pagamento della POLIZZA dall'ultima rata.
# ==========================================================================
def _mp_norm_num(s: str) -> str:
    import re as _re
    return _re.sub(r"\D", "", s or "")


def _mp_parse_date(v: str):
    v = (v or "").strip()
    if not v:
        return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y"):
        try:
            d = datetime.strptime(v, fmt)
            if d.year < 100:
                d = d.replace(year=2000 + d.year)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _mp_categoria(t: str) -> str:
    t = (t or "").upper()
    if any(k in t for k in ("RID", "SDD", "SEPA", "ADDEB")):
        return "sepa"
    if "BONIF" in t:
        return "bonifico"
    if "CONTAN" in t:
        return "contanti"
    if "ASSEG" in t:
        return "assegno"
    if "CARTA" in t or "POS" in t:
        return "carta"
    return "altro"


async def _process_metodo_pagamento(content: bytes, dry_run: bool, job_id: Optional[str] = None) -> dict:
    """Logica di rettifica metodo pagamento (usata dal job in background)."""
    import csv as _csv
    text = content.decode("utf-8-sig", errors="replace")
    reader = _csv.DictReader(io.StringIO(text), delimiter=";")
    per_pol: dict[str, list[dict]] = {}
    righe = 0
    for r in reader:
        num = _mp_norm_num(r.get("NumPolizza") or r.get("NumeroPolizza") or "")
        if not num:
            continue
        righe += 1
        per_pol.setdefault(num, []).append(r)

    # Indice numero polizza → id: le polizze OMNIA hanno zeri iniziali di
    # riempimento (00058531300240) mentre il CSV riporta il numero "nudo".
    idx_pol: dict[str, str] = {}
    async for p in db.polizze.find({}, {"_id": 0, "id": 1, "numero_polizza": 1}):
        raw = (p.get("numero_polizza") or "").strip()
        for k in {raw, _mp_norm_num(raw).lstrip("0")}:
            if k:
                idx_pol.setdefault(k, p["id"])

    titoli_aggiornati = 0
    polizze_aggiornate = 0
    non_trovate: list[str] = []
    tot_pol = len(per_pol)
    processate = 0
    for num, rr in per_pol.items():
        pol_id = (idx_pol.get((rr[0].get("NumPolizza") or "").strip())
                  or idx_pol.get(num) or idx_pol.get(num.lstrip("0")))
        if not pol_id:
            non_trovate.append(rr[0].get("NumPolizza"))
            processate += 1
            continue
        pol = {"id": pol_id}
        titoli = await db.titoli.find({"polizza_id": pol["id"]}).to_list(1000)
        tit_by_eff = {t.get("effetto"): t for t in titoli if t.get("effetto")}
        tit_by_scad = {t.get("scadenza"): t for t in titoli if t.get("scadenza")}
        tit_by_incasso = {t.get("data_incasso"): t for t in titoli if t.get("data_incasso")}
        usati: set[str] = set()
        for row in rr:
            rata = _mp_parse_date(row.get("RataDel"))
            cop = _mp_parse_date(row.get("Copertura") or row.get("DataCopertura"))
            pag = _mp_parse_date(row.get("DataPagam") or row.get("DataPagamento"))
            prox = _mp_parse_date(row.get("ProssimaScadenza"))
            tipo_pag = (row.get("TipoPag") or row.get("ModalitaPagamento") or "").strip()
            # chiave primaria di incrocio: RataDel = effetto del titolo
            t = (tit_by_eff.get(rata) or tit_by_eff.get(cop)
                 or tit_by_scad.get(cop) or tit_by_incasso.get(pag))
            if not t or t["id"] in usati:
                continue
            usati.add(t["id"])
            _set = {
                "data_copertura": cop or t.get("data_copertura"),
                "titolo_coperto": bool(cop) or bool(t.get("titolo_coperto")),
                "mezzo_pagamento": tipo_pag or None, "updated_at": _now_iso_mp(),
            }
            # scadenza reale della rata dal file (il flusso OMNIA non la valorizza)
            if prox:
                _set["scadenza"] = prox
            # Se c'è la data di pagamento → titolo incassato (finisce nei titoli storici)
            if pag:
                _set["stato"] = "incassato"
                if not t.get("data_incasso"):
                    _set["data_incasso"] = pag
            if not dry_run:
                await db.titoli.update_one({"id": t["id"]}, {"$set": _set})
            titoli_aggiornati += 1
        # ultima rata (max DataPagam) → metodo pagamento polizza
        def _key(row):
            return (_mp_parse_date(row.get("DataPagam") or row.get("DataPagamento"))
                    or _mp_parse_date(row.get("RataDel")) or "")
        ultima = max(rr, key=_key)
        tipo_ultima = (ultima.get("TipoPag") or ultima.get("ModalitaPagamento") or "").strip()
        cat = _mp_categoria(tipo_ultima)
        if not dry_run:
            await db.polizze.update_one({"id": pol["id"]}, {"$set": {
                "metodo_pagamento": cat,
                "metodo_pagamento_desc": tipo_ultima or None,
                "updated_at": _now_iso_mp(),
            }})
        polizze_aggiornate += 1
        processate += 1
        # progresso ogni 300 polizze
        if job_id and processate % 300 == 0:
            await db.import_jobs.update_one({"id": job_id}, {"$set": {
                "processate": processate, "totali": tot_pol}})

    return {
        "dry_run": dry_run,
        "righe_lette": righe,
        "polizze_nel_file": tot_pol,
        "polizze_aggiornate": polizze_aggiornate,
        "titoli_aggiornati": titoli_aggiornati,
        "polizze_non_trovate": non_trovate[:100],
        "tot_non_trovate": len(non_trovate),
    }


# Riferimenti forti ai task background: evita che il GC cancelli il task a metà.
_MP_BG_TASKS: set = set()


async def _run_metodo_pagamento_job(job_id: str, content: bytes, dry_run: bool):
    try:
        result = await _process_metodo_pagamento(content, dry_run, job_id)
        await db.import_jobs.update_one({"id": job_id}, {"$set": {
            "status": "done", "result": result, "finished_at": _now_iso_mp()}})
    except Exception as e:
        import traceback, logging
        logging.error("Import metodo pagamento job %s fallito: %s", job_id, traceback.format_exc())
        await db.import_jobs.update_one({"id": job_id}, {"$set": {
            "status": "error", "error": str(e)[:800], "finished_at": _now_iso_mp()}})


@router.post("/metodo-pagamento")
async def import_metodo_pagamento(
    file: UploadFile = File(...),
    dry_run: bool = False,
    user: dict = Depends(require_user("admin", "collaboratore")),
):
    """File CSV ';' del metodo pagamento. Gira in BACKGROUND (per file grandi,
    evita il timeout gateway Cloudflare 520). Ritorna subito un `job_id`; lo
    stato si controlla con GET /api/import/job/{job_id}.

    Rettifica su ogni titolo `mezzo_pagamento` + `data_copertura` (colonna
    Copertura) e imposta su ogni polizza `metodo_pagamento` (categoria) e
    `metodo_pagamento_desc` (testo) dell'ultima rata."""
    content = await file.read()
    job_id = str(uuid.uuid4())
    await db.import_jobs.insert_one({
        "id": job_id, "tipo": "metodo_pagamento", "dry_run": dry_run,
        "filename": file.filename, "status": "running", "created_at": _now_iso_mp()})
    task = asyncio.create_task(_run_metodo_pagamento_job(job_id, content, dry_run))
    _MP_BG_TASKS.add(task)
    task.add_done_callback(_MP_BG_TASKS.discard)
    return {"job_id": job_id, "status": "running"}


def _now_iso_mp() -> str:
    return datetime.now(timezone.utc).isoformat()
