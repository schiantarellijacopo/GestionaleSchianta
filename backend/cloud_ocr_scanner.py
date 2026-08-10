"""Cloud OCR Scanner — pipeline notturna che legge la cartella INBOX del cloud
storage collegato, esegue OCR con Gemini Vision, classifica i documenti e li
smista automaticamente nelle sotto-cartelle corrette + collega al gestionale.

Flusso per ogni file trovato in INBOX:
  1) Download → Gemini Vision → JSON classificato con tipo documento e dati chiave
  2) Match anagrafica/polizza/sinistro nel CRM (per codice_fiscale, targa, numero)
  3) Se match trovato:
       - Sposta file nella cartella specifica corretta
       - Crea record in `documenti_inbox_processed` collegato all'entità
       - Log nel Diario Cliente
  4) Se NON match:
       - Sposta file in "Da smistare manualmente"
       - Crea alert per l'admin dell'agenzia

Scheduler: cron ogni ora dalle 22:00 alle 06:00 UTC (finestra notturna).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("cloud_ocr_scanner")

_scheduler: Optional[AsyncIOScheduler] = None


# ============================================================
# MAPPA sottocartelle INBOX → tipo_documento (HINT FORTE)
# ============================================================
# Il nome della sottocartella dentro INBOX/ è la "categoria pre-classificata".
# Se il file cade in una di queste cartelle, salta la classificazione AI
# (o comunque la sovrascrive) e passa direttamente alla fase di estrazione dati.
#
# Nomi canonici (creati automaticamente da init-structure). Il matching è
# case-insensitive e ignora spazi/apostrofi.
INBOX_SUBFOLDERS_MAP = {
    # ── Anagrafica ────────────────────────────────────────────────────
    "carta d'identita":     "carta_identita",
    "carta d'identità":     "carta_identita",
    "carta identita":       "carta_identita",
    "ci":                   "carta_identita",
    "patente":              "patente",
    "passaporto":           "passaporto",
    "codice fiscale":       "codice_fiscale",
    "cf":                   "codice_fiscale",
    "tessera sanitaria":    "tessera_sanitaria",  # trattata come cf ai fini OCR
    "visura camerale":      "visura_camerale",
    "visura":               "visura_camerale",
    "mandato sdd":          "rid",
    "rid":                  "rid",
    "privacy":              "privacy",
    # ── Polizza ───────────────────────────────────────────────────────
    "polizze":              "polizza_frontespizio",
    "polizza":              "polizza_frontespizio",
    "condizioni":           "condizioni",
    "libretti":             "libretto_circolazione",
    "libretto":             "libretto_circolazione",
    "libretto circolazione": "libretto_circolazione",
    "libretto pagamento":   "libretto_pagamento",
    "atto di vendita":      "atto_vendita",
    "atto vendita":         "atto_vendita",
    "quietanze":            "quietanza",
    "quietanza":            "quietanza",
    # ── Sinistri / Contabilità ────────────────────────────────────────
    "denunce sinistro":     "denuncia_sinistro",
    "denunce":              "denuncia_sinistro",
    "sinistri":             "denuncia_sinistro",
    "estratti conto":       "estratto_conto_compagnia",
    "estratto conto":       "estratto_conto_compagnia",
    "bonifici":             "bonifico",
    "bonifico":             "bonifico",
}

# Elenco delle sottocartelle da creare automaticamente dentro INBOX
# (nomi canonici visualizzati all'utente)
INBOX_SUBFOLDERS_TO_CREATE = [
    "Carta d'Identità", "Patente", "Passaporto",
    "Codice Fiscale", "Tessera Sanitaria",
    "Visura Camerale", "Mandato SDD", "Privacy",
    "Polizze", "Condizioni", "Quietanze",
    "Libretti", "Atto di Vendita",
    "Denunce Sinistro", "Estratti Conto", "Bonifici",
]


def _norm_folder_key(name: str) -> str:
    """Normalizza un nome cartella per il match nella mappa (lower, no accenti extra)."""
    return (name or "").strip().lower().replace("_", " ")


def hint_from_folder_name(folder_name: Optional[str]) -> Optional[str]:
    """Ritorna il tipo_documento se il nome cartella è mappato, altrimenti None."""
    if not folder_name:
        return None
    return INBOX_SUBFOLDERS_MAP.get(_norm_folder_key(folder_name))


# ============================================================
# PROMPT Gemini per classificazione documento
# ============================================================
CLASSIFY_PROMPT = """Sei un classificatore esperto di documenti per un CRM assicurativo italiano.
Analizza l'immagine e restituisci ESCLUSIVAMENTE un JSON valido con questa struttura:

{
  "tipo_documento": "carta_identita | patente | passaporto | codice_fiscale | privacy | polizza_frontespizio | quietanza | denuncia_sinistro | estratto_conto_compagnia | bonifico | rid | libretto_circolazione | visura_camerale | altro",
  "confidenza": "alta | media | bassa",
  "dati_estratti": {
    "codice_fiscale": "16 caratteri uppercase o null",
    "partita_iva": "11 cifre o null",
    "cognome": "stringa MAIUSCOLA o null",
    "nome": "stringa MAIUSCOLA o null",
    "numero_polizza": "stringa o null",
    "numero_titolo": "stringa quietanza o null",
    "numero_sinistro": "stringa o null",
    "targa": "AA000AA uppercase o null",
    "compagnia": "nome compagnia o null",
    "data_avvenimento": "YYYY-MM-DD o null",
    "data_effetto": "YYYY-MM-DD o null",
    "data_scadenza": "YYYY-MM-DD o null",
    "data_pagamento": "YYYY-MM-DD o null",
    "importo": "numero decimale o null",
    "anno_riferimento": "YYYY o null",
    "mese_riferimento": "1-12 o null"
  }
}

===================================================================
REGOLE DI CLASSIFICAZIONE (PRIORITÀ ALTA — LEGGERE CON ATTENZIONE):

★ CARTA D'IDENTITÀ ITALIANA (tipo_documento="carta_identita"):
Segnali INEQUIVOCABILI:
  - Testo "REPUBBLICA ITALIANA" o "CARTA D'IDENTITÀ" o "COMUNE DI ..."
  - Foto tessera del titolare visibile
  - Campi: COGNOME, NOME, LUOGO E DATA DI NASCITA, RESIDENZA, STATURA, PROFESSIONE
  - Codice tipo "CA00000AA" o simile in alto
  - Formato carta elettronica (CIE) o cartaceo verde

★ PATENTE DI GUIDA (tipo_documento="patente"):
Segnali:
  - "PATENTE DI GUIDA" o "DRIVING LICENCE"
  - Categorie (A, B, C, ...) in tabella con date
  - Numero patente formato "UA1234567A" o "MI1234567A"
  - Bandiera UE + "ITALIA"

★ POLIZZA_FRONTESPIZIO (tipo_documento="polizza_frontespizio"):
Solo se il documento è CHIARAMENTE una polizza assicurativa:
  - Titolo "POLIZZA" / "CONTRATTO ASSICURATIVO" / "CERTIFICATO ASSICURAZIONE"
  - Compagnia (UNIPOL, GENERALI, CATTOLICA, ALLIANZ...) in EVIDENZA
  - Numero polizza chiaramente indicato (es. "N. 1234567890" o "Polizza n. ...")
  - Premio, effetto, scadenza in EURO
  - **ATTENZIONE**: se vedi P.IVA di una ditta E una foto tessera personale → NON è polizza, è carta d'identità di un dipendente. Classifica "carta_identita".

★ QUIETANZA (tipo_documento="quietanza"):
  - "QUIETANZA" o "RICEVUTA DI PAGAMENTO"
  - Riferimento a una polizza esistente
  - Importo pagato
  - Data pagamento

★ DENUNCIA SINISTRO (tipo_documento="denuncia_sinistro"):
  - "DENUNCIA DI SINISTRO" o "CONSTATAZIONE AMICHEVOLE" o "CAI"
  - Numero sinistro
  - Data avvenimento, luogo, dinamica

★ ESTRATTO CONTO COMPAGNIA (tipo_documento="estratto_conto_compagnia"):
  - "ESTRATTO CONTO" con logo compagnia
  - Elenco titoli/polizze con provvigioni
  - Totale a debito/credito

★ BONIFICO (tipo_documento="bonifico"):
  - "BONIFICO BANCARIO" o CRO/TRN
  - IBAN mittente + IBAN destinatario
  - Importo, data valuta

★ RID / SDD (tipo_documento="rid"):
  - "SEPA DIRECT DEBIT" o "RID" o "MANDATO ADDEBITO"

★ MODULO PRIVACY (tipo_documento="privacy"):
  - "INFORMATIVA PRIVACY" / "TRATTAMENTO DATI PERSONALI" / "GDPR"
  - Firma richiesta

★ LIBRETTO DI CIRCOLAZIONE (tipo_documento="libretto_circolazione"):
  - "CARTA DI CIRCOLAZIONE" / "LIBRETTO"
  - Ministero delle Infrastrutture / Motorizzazione
  - Dati veicolo: targa, telaio, marca, modello, potenza, cilindrata
  - Dati intestatario

★ VISURA CAMERALE (tipo_documento="visura_camerale"):
  - "CAMERA DI COMMERCIO" / "VISURA" / "REGISTRO IMPRESE"
  - Denominazione azienda, P.IVA, codice REA
  - Data iscrizione, sede legale, capitale sociale
  - Elenco soci/amministratori

===================================================================
REGOLE DI ESTRAZIONE DATI:

1. **codice_fiscale**: 16 caratteri (SCHJCP91M18I829O), MAI confondere con P.IVA (11 cifre).
2. **partita_iva**: SOLO 11 CIFRE PURE (04796220160). Se vedi CF-persona-fisica NON metterla qui.
3. **cognome/nome**: SEMPRE MAIUSCOLO. Per persone fisiche (C.I., patente). Per aziende usa il campo "cognome" con la ragione sociale SOLO se non c'è persona fisica.
4. **numero_polizza**: SOLO se documento è polizza/quietanza. Le C.I. NON hanno numero_polizza.
5. **targa**: SOLO se documento è polizza auto o denuncia sinistro. Formato AA000AA (2 lettere, 3 cifre, 2 lettere).
6. **data_scadenza**: su C.I./patente è la scadenza DEL DOCUMENTO stesso; su polizza è la scadenza POLIZZA.
7. Se un campo è illeggibile o non presente → `null`. NON inventare mai valori.

===================================================================
ESEMPIO 1 — Carta d'identità cartacea:
Input: documento verde con "COMUNE DI SONDRIO", foto, "COGNOME: ROSSI, NOME: MARIO", CF "RSSMRA80A01H501U"
Output:
{
  "tipo_documento": "carta_identita",
  "confidenza": "alta",
  "dati_estratti": {
    "codice_fiscale": "RSSMRA80A01H501U",
    "partita_iva": null,
    "cognome": "ROSSI",
    "nome": "MARIO",
    "numero_polizza": null,
    "targa": null,
    "data_scadenza": "2028-05-15",
    "data_avvenimento": null, "data_effetto": null, "data_pagamento": null,
    "numero_titolo": null, "numero_sinistro": null, "compagnia": null,
    "importo": null, "anno_riferimento": null, "mese_riferimento": null
  }
}

ESEMPIO 2 — Polizza RCA auto:
Input: "CATTOLICA ASSICURAZIONI", "Polizza n. 184643261", contraente "MTS SRL P.IVA 04796220160", targa "HE161EE"
Output:
{
  "tipo_documento": "polizza_frontespizio",
  "confidenza": "alta",
  "dati_estratti": {
    "codice_fiscale": null,
    "partita_iva": "04796220160",
    "cognome": "MTS SRL",
    "nome": null,
    "numero_polizza": "184643261",
    "targa": "HE161EE",
    "compagnia": "CATTOLICA ASSICURAZIONI",
    "data_effetto": "2026-06-30", "data_scadenza": "2027-12-31",
    "data_avvenimento": null, "data_pagamento": null,
    "numero_titolo": null, "numero_sinistro": null,
    "importo": null, "anno_riferimento": null, "mese_riferimento": null
  }
}

===================================================================
Rispondi SOLO con il JSON. Nessun markdown, nessun testo prima o dopo.
"""


async def _pdf_to_image_bytes(pdf_bytes: bytes) -> bytes:
    """Converte la PRIMA PAGINA di un PDF in un PNG (da passare a Gemini Vision).

    Uso pypdfium2 perché è già installato e non richiede poppler-utils.
    """
    import pypdfium2 as pdfium
    from io import BytesIO
    pdf = pdfium.PdfDocument(pdf_bytes)
    if len(pdf) == 0:
        raise ValueError("PDF vuoto")
    page = pdf[0]
    # Renderizza a 200 DPI (compromesso qualità/dimensione per Gemini)
    pil_image = page.render(scale=200 / 72).to_pil()
    # Se pagina troppo grande, ridimensiona (Gemini accetta max ~4MB)
    max_dim = 2000
    if max(pil_image.size) > max_dim:
        ratio = max_dim / max(pil_image.size)
        new_size = (int(pil_image.size[0] * ratio), int(pil_image.size[1] * ratio))
        pil_image = pil_image.resize(new_size)
    buf = BytesIO()
    pil_image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def _classify_document(file_bytes: bytes, mime: str, filename: str = "") -> dict:
    """Chiama Gemini Vision per classificare + estrarre dati.

    Se il file è PDF, converte la prima pagina in PNG (Gemini Vision accetta
    solo immagini). File multi-pagina: viene classificata solo la prima.
    Il filename è usato come HINT nel prompt per aumentare la precisione.
    """
    from emergentintegrations.llm.chat import (
        LlmChat, UserMessage, ImageContent, TextDelta, StreamDone,
    )
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise RuntimeError("EMERGENT_LLM_KEY non configurata")

    # Conversione PDF → immagine se necessario
    if mime == "application/pdf" or file_bytes[:4] == b"%PDF":
        try:
            file_bytes = await _pdf_to_image_bytes(file_bytes)
        except Exception as e:
            logger.warning("Conversione PDF→image fallita (%s): fallback su bytes originali", e)

    # HINT dal filename per guidare il classificatore
    fname_lower = filename.lower()
    hint = ""
    if any(k in fname_lower for k in ["c.i.", "ci ", "carta ident", "carta_ident", "id_", "cie"]):
        hint = "\n\n💡 HINT: il nome file suggerisce che si tratti di una CARTA D'IDENTITÀ. Verifica e privilegia questa classificazione se coerente con l'immagine."
    elif any(k in fname_lower for k in ["patent", "driving"]):
        hint = "\n\n💡 HINT: il nome file suggerisce che si tratti di una PATENTE DI GUIDA. Verifica e privilegia questa classificazione."
    elif any(k in fname_lower for k in ["polizza", "policy", "contratto assic"]):
        hint = "\n\n💡 HINT: il nome file suggerisce POLIZZA_FRONTESPIZIO."
    elif any(k in fname_lower for k in ["quietanza", "ricevut"]):
        hint = "\n\n💡 HINT: il nome file suggerisce QUIETANZA."
    elif any(k in fname_lower for k in ["sinistro", "denuncia", "cai_"]):
        hint = "\n\n💡 HINT: il nome file suggerisce DENUNCIA_SINISTRO."
    elif any(k in fname_lower for k in ["estratto", "ec_", "e_c_", "extract"]):
        hint = "\n\n💡 HINT: il nome file suggerisce ESTRATTO_CONTO_COMPAGNIA."
    elif any(k in fname_lower for k in ["bonifico", "sepa", "wire"]):
        hint = "\n\n💡 HINT: il nome file suggerisce BONIFICO."
    elif any(k in fname_lower for k in ["privacy", "gdpr", "consenso"]):
        hint = "\n\n💡 HINT: il nome file suggerisce MODULO PRIVACY."
    elif any(k in fname_lower for k in ["cf_", "codice_fisc", "tesserino"]):
        hint = "\n\n💡 HINT: il nome file suggerisce TESSERINO CODICE FISCALE."
    elif any(k in fname_lower for k in ["libretto", "carta_circ", "circolazione"]):
        hint = "\n\n💡 HINT: il nome file suggerisce LIBRETTO DI CIRCOLAZIONE."
    elif any(k in fname_lower for k in ["visura", "camera_comm", "camerale", "cciaa"]):
        hint = "\n\n💡 HINT: il nome file suggerisce VISURA CAMERALE."

    prompt_final = CLASSIFY_PROMPT + hint + f"\n\nNome file per contesto: '{filename}'"

    b64 = base64.b64encode(file_bytes).decode("ascii")
    img = ImageContent(image_base64=b64)
    chat = LlmChat(
        api_key=key,
        session_id=f"cloud-ocr-{os.urandom(4).hex()}",
        system_message="Classifica documenti assicurativi italiani con MASSIMA precisione. Rispondi solo JSON.",
    ).with_model("gemini", "gemini-3-flash-preview")
    msg = UserMessage(text=prompt_final, file_contents=[img])
    text = ""
    async for ev in chat.stream_message(msg):
        if isinstance(ev, TextDelta):
            text += ev.content
        elif isinstance(ev, StreamDone):
            break
    raw = re.sub(r"^```(?:json)?", "", text.strip(),
                 flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        logger.warning("Gemini classify: risposta senza JSON: %s", raw[:200])
        return {"tipo_documento": "altro", "confidenza": "bassa", "dati_estratti": {}}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"tipo_documento": "altro", "confidenza": "bassa", "dati_estratti": {}}
    parsed.setdefault("tipo_documento", "altro")
    parsed.setdefault("confidenza", "bassa")
    parsed.setdefault("dati_estratti", {})
    return parsed


# ============================================================
# MATCHING nel CRM
# ============================================================
async def _find_anagrafica(db, tenant_id: str, data: dict) -> Optional[dict]:
    """Cerca l'anagrafica per CF/P.IVA (tenant-safe: matcha anche legacy senza tenant_id)."""
    cf = (data.get("codice_fiscale") or "").upper().strip()
    piva = (data.get("partita_iva") or "").strip()
    tenant_q = {"$or": [{"tenant_id": tenant_id}, {"tenant_id": {"$exists": False}}, {"tenant_id": None}]}
    if cf:
        a = await db.anagrafiche.find_one(
            {**tenant_q, "codice_fiscale": cf},
            {"_id": 0, "id": 1, "cognome_nome": 1, "cognome": 1, "nome": 1,
             "ragione_sociale": 1, "codice_fiscale": 1},
        )
        if a:
            a["cognome_nome"] = (a.get("cognome_nome")
                                  or a.get("ragione_sociale")
                                  or f"{a.get('cognome','')} {a.get('nome','')}".strip())
            return a
    if piva:
        a = await db.anagrafiche.find_one(
            {**tenant_q, "partita_iva": piva},
            {"_id": 0, "id": 1, "cognome_nome": 1, "cognome": 1, "nome": 1,
             "ragione_sociale": 1, "partita_iva": 1},
        )
        if a:
            a["cognome_nome"] = (a.get("cognome_nome")
                                  or a.get("ragione_sociale")
                                  or f"{a.get('cognome','')} {a.get('nome','')}".strip())
            return a
    return None


async def _find_polizza(db, tenant_id: str, data: dict) -> Optional[dict]:
    """Cerca la polizza per numero_polizza o per targa."""
    num = (data.get("numero_polizza") or "").strip()
    targa = (data.get("targa") or "").upper().strip()
    tenant_q = {"$or": [{"tenant_id": tenant_id}, {"tenant_id": {"$exists": False}}, {"tenant_id": None}]}
    if num:
        p = await db.polizze.find_one(
            {**tenant_q, "numero_polizza": num},
            {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "targa": 1},
        )
        if p:
            return p
    if targa:
        p = await db.polizze.find_one(
            {**tenant_q, "targa": targa, "stato": {"$in": ["attiva", "sospesa"]}},
            {"_id": 0, "id": 1, "numero_polizza": 1, "contraente_id": 1, "targa": 1},
        )
        if p:
            return p
    return None


async def _find_or_create_anagrafica(db, tenant_id: str, data: dict) -> tuple:
    """Cerca anagrafica per CF/P.IVA. Se non trovata E ci sono dati sufficienti,
    la crea automaticamente e ritorna (anagrafica, was_created).

    Ritorna: (ana | None, bool_created)
    """
    ana = await _find_anagrafica(db, tenant_id, data)
    if ana:
        return ana, False

    cf = (data.get("codice_fiscale") or "").upper().strip()
    piva = (data.get("partita_iva") or "").strip()
    cognome = (data.get("cognome") or "").strip().upper()
    nome = (data.get("nome") or "").strip().upper()

    # Servono almeno CF (persona fisica) o P.IVA (giuridica) + un nome/ragione
    if not (cf or piva):
        return None, False
    if not (cognome or nome):
        return None, False

    from uuid import uuid4
    now = datetime.now(timezone.utc).isoformat()
    is_persona_giuridica = bool(piva) and not cf
    ana_id = str(uuid4())
    doc = {
        "id": ana_id,
        "tenant_id": tenant_id if tenant_id != "default" else None,
        "tipo": "persona_giuridica" if is_persona_giuridica else "persona_fisica",
        "created_at": now, "updated_at": now,
        "fonte": "ocr_cloud_drive",
        "note_interne": "Anagrafica creata automaticamente dallo scan OCR notturno del Google Drive/OneDrive",
    }
    if is_persona_giuridica:
        doc["ragione_sociale"] = cognome or nome  # in questo caso "cognome" è il nome ditta
        doc["partita_iva"] = piva
        doc["cognome_nome"] = doc["ragione_sociale"]
        if cf:
            doc["codice_fiscale"] = cf
    else:
        doc["cognome"] = cognome or "SCONOSCIUTO"
        doc["nome"] = nome or ""
        doc["cognome_nome"] = f"{doc['cognome']} {doc['nome']}".strip()
        if cf:
            doc["codice_fiscale"] = cf
        if piva:
            doc["partita_iva"] = piva
        # Aggiungi data scadenza documento se estratta (per calendar reminder)
        scad = data.get("data_scadenza")
        if scad:
            doc["scadenza_documento_identita"] = scad

    try:
        await db.anagrafiche.insert_one(doc)
        # Rimuovi _id per output pulito
        doc.pop("_id", None)
        return doc, True
    except Exception as e:
        logger.warning("Impossibile creare anagrafica auto (CF=%s): %s", cf, e)
        return None, False


async def _find_sinistro(db, tenant_id: str, data: dict) -> Optional[dict]:
    """Cerca il sinistro per numero_sinistro."""
    num = (data.get("numero_sinistro") or "").strip()
    if not num:
        return None
    return await db.sinistri.find_one(
        {"$or": [{"tenant_id": tenant_id}, {"tenant_id": {"$exists": False}}, {"tenant_id": None}],
         "numero_sinistro": num},
        {"_id": 0, "id": 1, "polizza_id": 1, "contraente_id": 1, "numero_sinistro": 1},
    )


# ============================================================
# ROUTING: mappa tipo_documento → (category, context builder)
# ============================================================
def _route_document(classification: dict, ana: Optional[dict],
                    pol: Optional[dict], sin: Optional[dict]) -> tuple:
    """Ritorna (category, context_dict, related_entity) per il routing.

    related_entity: {"kind": "anagrafica|polizza|sinistro", "id": "..."} o None
    """
    tipo = (classification.get("tipo_documento") or "altro").lower()
    data = classification.get("dati_estratti") or {}
    now = datetime.now(timezone.utc)

    ana_name = (ana or {}).get("cognome_nome", "").strip() or None
    pol_num = (pol or {}).get("numero_polizza", "").strip() or None
    sin_num = (sin or {}).get("numero_sinistro", "").strip() or None

    # Ogni categoria di doc → (folder_category, ha_bisogno_di_cliente)
    ROUTING = {
        "carta_identita": ("contraente_identita", "cliente"),
        "patente": ("contraente_identita", "cliente"),
        "passaporto": ("contraente_identita", "cliente"),
        "codice_fiscale": ("contraente_codice_fiscale", "cliente"),
        "privacy": ("contraente_privacy", "cliente"),
        "visura_camerale": ("contraente_altri", "cliente"),
        "libretto_circolazione": ("polizza_documenti", "polizza"),
        "polizza_frontespizio": ("polizza_documenti", "polizza"),
        "quietanza": ("quietanze_anno", "anno"),
        "denuncia_sinistro": ("sinistro_specifico", "sinistro"),
        "estratto_conto_compagnia": ("contabilita_estratti", "anno"),
        "bonifico": ("contabilita_prima_nota", "anno_mese"),
        "rid": ("contabilita_prima_nota", "anno_mese"),
    }
    routing_info = ROUTING.get(tipo)
    if not routing_info:
        return ("da_smistare", {}, None)

    category, requirement = routing_info
    if requirement == "cliente":
        if not ana_name:
            return ("da_smistare", {}, None)
        return (category, {"cliente": ana_name}, {"kind": "anagrafica", "id": ana["id"]})
    if requirement == "polizza":
        if not pol_num:
            return ("da_smistare", {}, None)
        return (category, {"polizza": pol_num}, {"kind": "polizza", "id": pol["id"]})
    if requirement == "sinistro":
        if not sin_num:
            return ("da_smistare", {}, None)
        return (category, {"sinistro": sin_num}, {"kind": "sinistro", "id": sin["id"]})
    if requirement == "anno":
        anno = data.get("anno_riferimento") or now.year
        return (category, {"anno": anno}, None)
    if requirement == "anno_mese":
        anno = data.get("anno_riferimento") or now.year
        mese = data.get("mese_riferimento") or now.month
        return (category, {"anno": anno, "mese": mese}, None)
    return ("da_smistare", {}, None)


# ============================================================
# PIPELINE MAIN
# ============================================================
async def scan_tenant_inbox(db, tenant_id: str, provider: str,
                            manual: bool = False) -> dict:
    """Scansiona la cartella INBOX di un tenant/provider ed elabora ogni file.

    Ritorna un report {letti, abbinati, in_attesa, errori: [...], entries: [...]}.
    """
    from routes.cloud_storage import (
        _fresh_access_token, _find_folder, _ensure_folder_path,
        _resolve_category_path,
    )
    conn = await db.cloud_connections.find_one({
        "tenant_id": tenant_id, "provider": provider,
    })
    if not conn:
        return {"skipped": True, "reason": "Nessuna connessione cloud", "letti": 0}

    try:
        token = await _fresh_access_token(provider, conn)
    except Exception as e:
        return {"skipped": True, "reason": f"Token refresh fallito: {e}", "letti": 0}

    # 1) Trova la cartella INBOX
    inbox_segments = await _resolve_category_path("inbox", {})
    parent = None
    for seg in inbox_segments:
        fid = await _find_folder(provider, token, seg, parent)
        if not fid:
            return {"skipped": True, "reason": "Cartella INBOX non ancora creata",
                    "letti": 0}
        parent = fid
    inbox_id = parent

    # 1b) Assicura le sottocartelle canoniche (Polizze, Quietanze, ecc.).
    # Le creiamo sempre per rendere l'inserimento file più guidato all'utente.
    try:
        await _ensure_inbox_subfolders(provider, token, inbox_id)
    except Exception as e:
        logger.warning("Errore auto-creazione sottocartelle INBOX: %s", e)

    # 2) Lista file in INBOX (root + sottocartelle di 1° livello, con hint categoria)
    files = await _list_inbox_all_files(provider, token, inbox_id)
    if not files:
        return {"letti": 0, "abbinati": 0, "in_attesa": 0, "entries": [],
                "provider": provider}

    report = {
        "letti": len(files), "abbinati": 0, "in_attesa": 0,
        "anagrafiche_create": 0,
        "errori": [], "entries": [], "provider": provider,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    for f in files:
        try:
            entry = await _process_file(db, provider, token, tenant_id, f)
            report["entries"].append(entry)
            if entry.get("routed_to") and entry.get("routed_to") != "da_smistare":
                report["abbinati"] += 1
            else:
                report["in_attesa"] += 1
            if entry.get("anagrafica_creata"):
                report["anagrafiche_create"] += 1
        except Exception as e:
            logger.exception("Errore processing file %s", f.get("name"))
            report["errori"].append({"file": f.get("name"), "error": str(e)[:200]})
            report["in_attesa"] += 1

    report["ended_at"] = datetime.now(timezone.utc).isoformat()
    report["manual"] = manual

    # Salva report in DB per la history
    await db.cloud_scan_history.insert_one({
        "tenant_id": tenant_id,
        **{k: v for k, v in report.items() if k != "entries"},
        "entries_summary": report["entries"][:50],  # limita per non gonfiare
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return report


async def _list_files_in_folder(provider: str, token: str, folder_id: str) -> list:
    """Lista i file (non cartelle) dentro folder_id."""
    if provider == "google_drive":
        q = (f"'{folder_id}' in parents and trashed=false "
             f"and mimeType != 'application/vnd.google-apps.folder'")
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": q, "fields": "files(id,name,mimeType,size)", "pageSize": 100},
            )
        r.raise_for_status()
        return r.json().get("files", [])
    # OneDrive
    url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}/children"
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.get(url, headers={"Authorization": f"Bearer {token}"},
                        params={"$filter": "file ne null",
                                "$select": "id,name,file,size"})
    r.raise_for_status()
    return [
        {"id": it["id"], "name": it["name"],
         "mimeType": (it.get("file") or {}).get("mimeType", "application/octet-stream"),
         "size": it.get("size", 0)}
        for it in r.json().get("value", [])
    ]


async def _list_subfolders(provider: str, token: str, folder_id: str) -> list:
    """Lista le sottocartelle dentro folder_id → [{id, name}, ...]."""
    if provider == "google_drive":
        q = (f"'{folder_id}' in parents and trashed=false "
             f"and mimeType = 'application/vnd.google-apps.folder'")
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": q, "fields": "files(id,name)", "pageSize": 100},
            )
        r.raise_for_status()
        return r.json().get("files", [])
    # OneDrive
    url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}/children"
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.get(url, headers={"Authorization": f"Bearer {token}"},
                        params={"$filter": "folder ne null",
                                "$select": "id,name,folder"})
    r.raise_for_status()
    return [{"id": it["id"], "name": it["name"]} for it in r.json().get("value", [])]


async def _list_inbox_all_files(provider: str, token: str, inbox_id: str) -> list:
    """Ritorna TUTTI i file nell'INBOX (root + tutte le sottocartelle di 1° livello).

    Ogni file è arricchito con:
      - `_parent_folder_id`: id della cartella dove risiede (root INBOX o subfolder)
      - `_parent_folder_name`: nome della cartella (None se root INBOX)
      - `_hint_tipo`: tipo_documento suggerito dal nome cartella (o None)
    """
    all_files: list = []
    # Root INBOX
    root_files = await _list_files_in_folder(provider, token, inbox_id)
    for f in root_files:
        f["_parent_folder_id"] = inbox_id
        f["_parent_folder_name"] = None
        f["_hint_tipo"] = None
        all_files.append(f)
    # Sottocartelle 1° livello
    subs = await _list_subfolders(provider, token, inbox_id)
    for sub in subs:
        sub_files = await _list_files_in_folder(provider, token, sub["id"])
        hint = hint_from_folder_name(sub["name"])
        for f in sub_files:
            f["_parent_folder_id"] = sub["id"]
            f["_parent_folder_name"] = sub["name"]
            f["_hint_tipo"] = hint
            all_files.append(f)
    return all_files


async def _ensure_inbox_subfolders(provider: str, token: str,
                                    inbox_id: str) -> dict:
    """Crea (se mancanti) le sottocartelle canoniche dentro INBOX.

    Ritorna mappa {nome_canonico: folder_id}.
    """
    from routes.cloud_storage import _find_folder, _create_folder
    created: dict = {}
    for name in INBOX_SUBFOLDERS_TO_CREATE:
        fid = await _find_folder(provider, token, name, inbox_id)
        if not fid:
            try:
                fid = await _create_folder(provider, token, name, inbox_id)
                logger.info("INBOX subfolder created: %s (%s)", name, fid)
            except Exception as e:
                logger.warning("Errore creazione sottocartella INBOX '%s': %s", name, e)
                continue
        created[name] = fid
    return created


async def _download_file(provider: str, token: str, file_id: str) -> bytes:
    """Scarica il contenuto del file."""
    if provider == "google_drive":
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    else:
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as x:
        r = await x.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.content


async def _move_file(provider: str, token: str, file_id: str,
                     new_parent_id: str, old_parent_id: str) -> None:
    """Sposta il file dalla cartella old_parent alla new_parent."""
    if provider == "google_drive":
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.patch(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"addParents": new_parent_id, "removeParents": old_parent_id},
            )
        r.raise_for_status()
    else:
        # OneDrive: PATCH per cambiare parentReference
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
        async with httpx.AsyncClient(timeout=30) as x:
            r = await x.patch(
                url,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"parentReference": {"id": new_parent_id}},
            )
        r.raise_for_status()


async def _process_file(db, provider: str, token: str, tenant_id: str,
                        f: dict) -> dict:
    """Elabora un singolo file: download → OCR → match → sposta → log.

    Se `f` proviene da una sottocartella INBOX mappata (es. "Polizze",
    "Quietanze", "Libretti"), il tipo_documento viene FORZATO dal nome
    della cartella, saltando la classificazione AI (l'OCR estrae solo i
    dati anagrafici/polizza necessari al matching).
    """
    from routes.cloud_storage import _ensure_folder_path, _resolve_category_path

    file_id = f["id"]
    name = f.get("name", "unknown")
    mime = f.get("mimeType", "application/octet-stream")
    # Hint della sottocartella INBOX (es. "Polizze" → tipo "polizza_frontespizio")
    hint_tipo = f.get("_hint_tipo")
    src_parent_id = f.get("_parent_folder_id")  # cartella origine per _move_file
    src_folder_name = f.get("_parent_folder_name")

    # Skip file troppo grandi (>15MB)
    size = int(f.get("size") or 0)
    if size > 15 * 1024 * 1024:
        return {"file_id": file_id, "name": name,
                "routed_to": "da_smistare", "reason": "File >15MB, saltato"}

    # Solo PDF/immagini
    if not (mime.startswith("image/") or mime == "application/pdf"):
        # Sposta comunque in "da smistare" e prosegui
        try:
            segments = await _resolve_category_path("da_smistare", {})
            parent = await _ensure_folder_path(provider, token, segments, tenant_id)
            src_id = src_parent_id
            if not src_id:
                inbox_segments = await _resolve_category_path("inbox", {})
                src_id = await _ensure_folder_path(provider, token, inbox_segments, tenant_id)
            await _move_file(provider, token, file_id, parent, src_id)
        except Exception as e:
            logger.warning("Errore spostamento file non-supportato %s: %s", name, e)
        return {"file_id": file_id, "name": name,
                "routed_to": "da_smistare", "reason": f"MIME non supportato ({mime})"}

    # Download + OCR (passiamo il filename come hint al classifier)
    file_bytes = await _download_file(provider, token, file_id)
    try:
        classification = await _classify_document(file_bytes, mime, filename=name)
    except Exception as e:
        classification = {"tipo_documento": "altro", "confidenza": "bassa",
                          "dati_estratti": {}, "ocr_error": str(e)[:200]}

    # 🎯 Se il file è in una sottocartella INBOX mappata, SOVRASCRIVI il tipo
    # (folder-name = fonte di verità). Manteniamo dati_estratti dell'OCR.
    if hint_tipo:
        classification["tipo_documento"] = hint_tipo
        classification.setdefault("confidenza", "alta")
        classification["hint_source"] = f"inbox_subfolder:{src_folder_name}"

    data = classification.get("dati_estratti") or {}

    # Match nel CRM (crea anagrafica automaticamente se manca e ci sono dati sufficienti)
    ana, anagrafica_creata = await _find_or_create_anagrafica(db, tenant_id, data)
    pol = await _find_polizza(db, tenant_id, data)
    sin = await _find_sinistro(db, tenant_id, data)

    # Routing
    category, ctx, related = _route_document(classification, ana, pol, sin)

    # Origine per il move: se il file veniva da una sottocartella, usiamo quella.
    # Altrimenti la root INBOX.
    if src_parent_id:
        src_id = src_parent_id
    else:
        inbox_segments = await _resolve_category_path("inbox", {})
        src_id = await _ensure_folder_path(provider, token, inbox_segments, tenant_id)
    dest_segments = await _resolve_category_path(category, ctx)
    dest_id = await _ensure_folder_path(provider, token, dest_segments, tenant_id)

    try:
        await _move_file(provider, token, file_id, dest_id, src_id)
    except Exception as e:
        logger.warning("Errore move file %s: %s", name, e)

    # Log nella collection dei documenti smistati
    doc_record = {
        "tenant_id": tenant_id,
        "provider": provider,
        "file_id": file_id,
        "file_name": name,
        "mime_type": mime,
        "size": size,
        "classification": classification,
        "matched_anagrafica_id": (ana or {}).get("id"),
        "matched_polizza_id": (pol or {}).get("id"),
        "matched_sinistro_id": (sin or {}).get("id"),
        "routed_to": category,
        "routed_path": " / ".join(dest_segments),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.cloud_documents.insert_one(doc_record)

    # ★ Se abbinato → crea ANCHE l'allegato nel CRM così il file compare in
    # Anagrafiche → tab Documenti (categoria carta_identita/patente/ecc.)
    if category != "da_smistare" and ana:
        try:
            await _create_crm_attachment(
                db, tenant_id, name, file_bytes, mime,
                classification, ana, pol, sin,
            )
        except Exception as e:
            logger.warning("Creazione allegato CRM fallita per %s: %s", name, e)


    # Se NON abbinato → porta il file anche nella pagina Documenti Inbox del CRM
    # in modo che l'utente lo trovi ed possa smistarlo manualmente decidendo il target.
    inbox_id: Optional[str] = None
    if category == "da_smistare":
        try:
            inbox_id = await _push_to_manual_inbox(
                db, tenant_id, name, file_bytes, mime,
                classification, ana, pol, sin, file_id, provider,
            )
        except Exception as e:
            logger.warning("Push to manual inbox fallito per %s: %s", name, e)

    # Se abbinato ad anagrafica → log nel Diario Cliente
    if ana:
        try:
            titolo_diario = (f"👤 Anagrafica creata da OCR: {classification.get('tipo_documento', 'documento')}"
                             if anagrafica_creata
                             else f"📄 OCR notturno: {classification.get('tipo_documento', 'documento')}")
            await db.diario_voci.insert_one({
                "tenant_id": tenant_id,
                "anagrafica_id": ana["id"],
                "tipo": "documento_ocr",
                "titolo": titolo_diario,
                "descrizione": (f"File '{name}' letto e archiviato in {' / '.join(dest_segments)}."
                                + (" Anagrafica creata automaticamente dai dati estratti." if anagrafica_creata else "")),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "autore": "OCR Automatico",
                "meta": {"file_id": file_id, "provider": provider,
                         "anagrafica_creata": anagrafica_creata},
            })
        except Exception as e:
            logger.debug("Skip log diario: %s", e)

    # Se non abbinato → crea alert
    if category == "da_smistare":
        try:
            await db.avvisi.insert_one({
                "tenant_id": tenant_id,
                "tipo": "documento_non_smistato",
                "priorita": "media",
                "titolo": f"Documento da smistare: {name}",
                "descrizione": (
                    f"Il documento '{name}' è stato analizzato ma non è stato possibile "
                    f"abbinarlo automaticamente. Tipo rilevato: "
                    f"{classification.get('tipo_documento', 'sconosciuto')}."
                ),
                "stato": "aperto",
                "meta": {"cloud_file_id": file_id, "provider": provider,
                         "classification": classification},
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.debug("Skip alert: %s", e)

    return {
        "file_id": file_id, "name": name,
        "tipo_documento": classification.get("tipo_documento"),
        "confidenza": classification.get("confidenza"),
        "routed_to": category,
        "routed_path": " / ".join(dest_segments),
        "matched_anagrafica": (ana or {}).get("cognome_nome"),
        "anagrafica_creata": anagrafica_creata,
        "anagrafica_id": (ana or {}).get("id") if anagrafica_creata else None,
        "matched_polizza": (pol or {}).get("numero_polizza"),
        "matched_sinistro": (sin or {}).get("numero_sinistro"),
        "inbox_id": inbox_id,   # se presente, l'utente lo troverà in Documenti Inbox
    }


async def _create_crm_attachment(
    db, tenant_id: str, filename: str, file_bytes: bytes, mime: str,
    classification: dict, ana: Optional[dict], pol: Optional[dict],
    sin: Optional[dict],
) -> None:
    """Crea record `allegati` nel CRM collegato all'entità corretta così il file
    appare nella tab Documenti dell'anagrafica/polizza/sinistro.
    """
    import uuid, os as _os
    import storage as obj_storage

    tipo_doc = (classification.get("tipo_documento") or "altro").lower()
    CAT_MAP = {
        "carta_identita": ("anagrafica", "carta_identita"),
        "patente": ("anagrafica", "patente"),
        "passaporto": ("anagrafica", "passaporto"),
        "codice_fiscale": ("anagrafica", "codice_fiscale"),
        "privacy": ("anagrafica", "privacy"),
        "visura_camerale": ("anagrafica", "visura_camerale"),
        "libretto_circolazione": ("polizza", "libretto_circolazione"),
        "polizza_frontespizio": ("polizza", "polizza"),
        "quietanza": ("polizza", "quietanza"),
        "denuncia_sinistro": ("sinistro", "denuncia"),
        "estratto_conto_compagnia": ("compagnia", "estratto_conto"),
        "bonifico": ("anagrafica", "bonifico"),
        "rid": ("anagrafica", "rid"),
    }
    entita_tipo, categoria = CAT_MAP.get(tipo_doc, ("anagrafica", "altro"))
    entita_id = None
    if entita_tipo == "anagrafica" and ana:
        entita_id = ana["id"]
    elif entita_tipo == "polizza" and pol:
        entita_id = pol["id"]
    elif entita_tipo == "sinistro" and sin:
        entita_id = sin["id"]
    if not entita_id and ana:
        entita_id = ana["id"]
        entita_tipo = "anagrafica"
    if not entita_id:
        return

    # ── Enrichment: applicazione_matricola_id (per polizze Libro Matricola)
    # e titolo_id (per quietanze).
    data_ocr = classification.get("dati_estratti") or {}
    applicazione_matricola_id = None
    titolo_id_for_quietanza = None
    titolo_periodo_desc = None  # es. "Quietanza · periodo 17/07/2026 → 29/07/2026"

    # 1) Se la polizza è Libro Matricola e c'è una targa → match applicazione
    if pol and pol.get("is_libro_matricola") and data_ocr.get("targa"):
        targa_up = data_ocr["targa"].upper().strip()
        app = await db.applicazioni.find_one(
            {"polizza_id": pol["id"], "targa": {"$regex": f"^{targa_up}$", "$options": "i"}},
            {"_id": 0, "id": 1},
        )
        if app:
            applicazione_matricola_id = app["id"]
            logger.info("Libro Matricola: allegato collegato all'applicazione %s (targa %s)",
                       app["id"], targa_up)

    # 2) Se è una quietanza e la polizza è nota → trova il TITOLO di riferimento
    # (creerò un secondo allegato collegato al titolo per l'icona 📎 nella lista Titoli)
    if tipo_doc == "quietanza" and pol:
        num_titolo = (data_ocr.get("numero_titolo") or "").strip()
        data_pag = (data_ocr.get("data_pagamento") or "").strip()
        VALID_STATI = ["da_incassare", "incassato", "pendente"]
        titolo = None
        if num_titolo:
            titolo = await db.titoli.find_one(
                {"polizza_id": pol["id"], "numero_titolo": num_titolo,
                 "stato": {"$in": VALID_STATI}},
                {"_id": 0, "id": 1, "stato": 1, "data_effetto": 1, "data_scadenza": 1,
                 "numero_titolo": 1},
            )
        if not titolo and data_pag:
            titolo = await db.titoli.find_one(
                {"polizza_id": pol["id"],
                 "data_effetto": {"$lte": data_pag},
                 "data_scadenza": {"$gte": data_pag},
                 "stato": {"$in": VALID_STATI}},
                {"_id": 0, "id": 1, "stato": 1, "data_effetto": 1, "data_scadenza": 1,
                 "numero_titolo": 1},
            )
        if not titolo:
            # Fallback: se la polizza ha UN SOLO titolo valido, prendi quello
            candidates = await db.titoli.find(
                {"polizza_id": pol["id"], "stato": {"$in": VALID_STATI}},
                {"_id": 0, "id": 1, "stato": 1, "data_effetto": 1, "data_scadenza": 1,
                 "numero_titolo": 1},
            ).to_list(5)
            if len(candidates) == 1:
                titolo = candidates[0]
        if titolo:
            titolo_id_for_quietanza = titolo["id"]
            # Costruisci descrizione "Quietanza · periodo dd/mm/yyyy → dd/mm/yyyy"
            def _fmt(d):
                try:
                    return f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if d and len(d) >= 10 else d
                except Exception:
                    return d
            periodo = ""
            if titolo.get("data_effetto") and titolo.get("data_scadenza"):
                periodo = f" · periodo {_fmt(titolo['data_effetto'])} → {_fmt(titolo['data_scadenza'])}"
            num = titolo.get("numero_titolo")
            titolo_periodo_desc = f"Quietanza{' n°' + num if num else ''}{periodo}"
            logger.info("Quietanza: verrà collegata anche al titolo %s (%s)",
                       titolo["id"], titolo_periodo_desc)

    allegato_id = str(uuid.uuid4())
    # Deduplica: se esiste già lo stesso allegato (entità + nome + fonte), skip
    existing = await db.allegati.find_one({
        "entita_tipo": entita_tipo,
        "entita_id": entita_id,
        "nome_file": filename,
        "fonte": "cloud_ocr_scan",
        "is_deleted": {"$ne": True},
    }, {"_id": 0, "id": 1})
    if existing:
        logger.info("Allegato già presente, skip duplicato: %s", filename)
        return
    ext = (filename or "doc").rsplit(".", 1)[-1].lower() or "bin"
    storage_path = f"{_os.environ.get('APP_NAME', 'assicura')}/allegati/{allegato_id}.{ext}"
    try:
        obj_storage.put_object(storage_path, file_bytes, mime)
    except Exception as e:
        logger.warning("put_object per allegato %s fallito: %s", allegato_id, e)
        return

    allegato = {
        "id": allegato_id,
        "tenant_id": tenant_id if tenant_id != "default" else None,
        "entita_tipo": entita_tipo,
        "entita_id": entita_id,
        "categoria": categoria,
        "nome_file": filename,
        "content_type": mime,
        "size": len(file_bytes),
        "storage_path": storage_path,
        "descrizione": f"Importato automaticamente da Google Drive OCR ({tipo_doc})",
        "fonte": "cloud_ocr_scan",
        # Se il file è collegato a una specifica applicazione di libro matricola
        # (matching per targa), lo colleghiamo qui così appare nella tab del veicolo.
        "applicazione_matricola_id": applicazione_matricola_id,
        # Categorie visibili al cliente (allineato al banner UI PolizzaDetail/AnagraficaDetail):
        #  - Documenti identità/anagrafica (banner Anagrafica: "sempre visibili al cliente"):
        #    carta_identita, patente, passaporto, codice_fiscale, privacy,
        #    tessera_sanitaria, visura_camerale, rid (Mandato SDD)
        #  - Documenti polizza (banner Polizza):
        #    polizza, condizioni, quietanza, libretto_pagamento,
        #    libretto_circolazione, atto_vendita
        # Restano interni allo staff:
        #    bonifico (accounting), estratto_conto, denuncia, altro,
        #    preventivo, appunti
        "visibile_cliente": categoria in (
            # Anagrafica
            "carta_identita", "patente", "passaporto", "codice_fiscale", "privacy",
            "tessera_sanitaria", "visura_camerale", "rid",
            # Polizza
            "polizza", "condizioni", "quietanza", "libretto_pagamento",
            "libretto_circolazione", "atto_vendita",
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "is_deleted": False,
    }
    await db.allegati.insert_one(allegato)

    # ── Se è una quietanza collegabile a un titolo, DUPLICA l'allegato sul titolo
    # (stesso storage_path, così l'utente lo vede sia nella tab Documenti della
    # polizza sia con l'icona 📎 sulla riga del titolo nella lista Titoli).
    # Skip se sul titolo esiste GIÀ un qualsiasi allegato (rispetta upload manuale).
    if titolo_id_for_quietanza:
        any_existing = await db.allegati.find_one({
            "entita_tipo": "titolo",
            "entita_id": titolo_id_for_quietanza,
            "is_deleted": {"$ne": True},
        }, {"_id": 0, "id": 1, "fonte": 1})
        if any_existing:
            logger.info("Titolo %s ha già un allegato (fonte=%s), skip duplicazione",
                       titolo_id_for_quietanza, any_existing.get("fonte"))
        else:
            allegato_titolo = {
                **allegato,
                "id": str(uuid.uuid4()),
                "entita_tipo": "titolo",
                "entita_id": titolo_id_for_quietanza,
                "descrizione": f"Quietanza (collegata al titolo) — OCR automatico",
            }
            await db.allegati.insert_one(allegato_titolo)


async def _push_to_manual_inbox(
    db, tenant_id: str, filename: str, file_bytes: bytes, mime: str,
    classification: dict, ana: Optional[dict], pol: Optional[dict],
    sin: Optional[dict], drive_file_id: str, provider: str,
) -> str:
    """Salva il file (che non è stato smistato automaticamente) nella pagina
    'Documenti Inbox · OCR' del CRM. L'utente potrà poi decidere manualmente
    l'anagrafica/polizza di destinazione dal frontend.
    """
    import uuid, os as _os
    import storage as obj_storage

    inbox_id = str(uuid.uuid4())
    ext = (filename or "doc").rsplit(".", 1)[-1].lower() or "bin"
    path = f"{_os.environ.get('APP_NAME', 'assicura')}/inbox/{inbox_id}.{ext}"
    try:
        obj_storage.put_object(path, file_bytes, mime)
    except Exception as e:
        logger.warning("put_object storage fallito: %s", e)
        path = None

    doc_inbox = {
        "id": inbox_id,
        "tenant_id": tenant_id if tenant_id != "default" else None,
        "filename": filename,
        "content_type": mime,
        "size": len(file_bytes),
        "storage_path": path,
        "tipo_documento": classification.get("tipo_documento"),
        "confidenza": classification.get("confidenza"),
        "dati": classification.get("dati_estratti") or {},
        "target_anagrafica": ana,
        "target_polizza": pol,
        "target_sinistro": sin,
        "stato": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fonte": "cloud_ocr_scan",
        "cloud_file_id": drive_file_id,
        "cloud_provider": provider,
    }
    await db.documenti_inbox.insert_one(doc_inbox)
    return inbox_id


# ============================================================
# SCHEDULER
# ============================================================
async def _scan_all_tenants_job(db):
    """Job periodico: scansiona INBOX di TUTTI i tenant con cloud collegato."""
    logger.info("[Cloud OCR] Job notturno avviato")
    connections = db.cloud_connections.find({}, {"_id": 0, "tenant_id": 1, "provider": 1})
    tenants_seen = set()
    async for c in connections:
        key = (c["tenant_id"], c["provider"])
        if key in tenants_seen:
            continue
        tenants_seen.add(key)
        try:
            report = await scan_tenant_inbox(db, c["tenant_id"], c["provider"])
            logger.info("[Cloud OCR] tenant=%s provider=%s: %s",
                        c["tenant_id"], c["provider"],
                        {k: v for k, v in report.items()
                         if k in ("letti", "abbinati", "in_attesa")})
        except Exception:
            logger.exception("[Cloud OCR] Errore su tenant %s", c["tenant_id"])


def start_scheduler(db):
    """Avvia lo scheduler: ogni ora dalle 22:00 alle 06:00 UTC."""
    global _scheduler
    if _scheduler:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _scan_all_tenants_job,
        CronTrigger(hour="22-23,0-5", minute="0"),  # ogni ora dalle 22 alle 05
        args=[db],
        id="cloud_ocr_nightly",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("[Cloud OCR] Scheduler avviato (cron 22-23,0-5, tz=UTC)")


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
