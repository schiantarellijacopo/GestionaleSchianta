"""AI Copilot service — LLM con accesso in READ ai dati del CRM.

Permette all'utente di fare domande in linguaggio naturale sui dati storici
(polizze, pagamenti, sinistri, veicoli, anagrafiche, ecc.) e ricevere risposte
contestualizzate. Le query MongoDB sono sempre in READ-ONLY (safety by design).

Uso via /api/copilot/chat: POST {message, session_id?, use_tts?}.
"""
from __future__ import annotations
import logging
import os
import re
from typing import Optional
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Query helpers (READ-ONLY) ----------
# Ogni funzione ritorna un dict "summary + rows" per contesto LLM.

async def search_anagrafiche(q: str, limit: int = 10) -> list[dict]:
    """Cerca clienti per nome/cognome/CF/P.IVA/email/telefono."""
    q = (q or "").strip()
    if not q:
        return []
    regex = {"$regex": re.escape(q), "$options": "i"}
    filt = {"$or": [
        {"ragione_sociale": regex}, {"cognome": regex}, {"nome": regex},
        {"codice_fiscale": q.upper()}, {"partita_iva": q},
        {"email": regex}, {"cellulare": regex},
    ]}
    proj = {"_id": 0, "id": 1, "ragione_sociale": 1, "codice_fiscale": 1,
            "partita_iva": 1, "email": 1, "cellulare": 1, "tipo": 1}
    docs = await db.anagrafiche.find(filt, proj).limit(limit).to_list(limit)
    return docs


async def find_polizze(anagrafica_id: Optional[str] = None, ramo: Optional[str] = None,
                       anno_scadenza: Optional[int] = None, stato: Optional[str] = None,
                       limit: int = 20) -> list[dict]:
    filt = {}
    if anagrafica_id: filt["contraente_id"] = anagrafica_id
    if ramo: filt["ramo"] = {"$regex": ramo, "$options": "i"}
    if stato: filt["stato"] = stato
    if anno_scadenza:
        filt["scadenza"] = {"$regex": f"^{anno_scadenza}"}
    proj = {"_id": 0, "id": 1, "numero_polizza": 1, "compagnia_nome": 1, "ramo": 1,
            "stato": 1, "effetto": 1, "scadenza": 1, "premio_lordo": 1, "contraente_id": 1}
    return await db.polizze.find(filt, proj).sort("scadenza", -1).limit(limit).to_list(limit)


async def find_titoli(anagrafica_id: Optional[str] = None, anno: Optional[int] = None,
                      solo_incassati: bool = False, limit: int = 30) -> list[dict]:
    """Cerca titoli (quietanze/pagamenti) per anagrafica o anno."""
    filt = {}
    if anno:
        filt["data_scadenza"] = {"$regex": f"^{anno}"}
    if solo_incassati:
        filt["stato"] = "incassato"
    if anagrafica_id:
        # Titoli su polizze del contraente
        polizze_ids = await db.polizze.find({"contraente_id": anagrafica_id}, {"_id": 0, "id": 1}).to_list(1000)
        ids = [p["id"] for p in polizze_ids]
        if ids:
            filt["polizza_id"] = {"$in": ids}
        else:
            return []
    proj = {"_id": 0, "polizza_id": 1, "numero_polizza": 1, "importo_lordo": 1,
            "importo_netto": 1, "data_scadenza": 1, "data_incasso": 1, "stato": 1,
            "compagnia_nome": 1}
    return await db.titoli.find(filt, proj).sort("data_scadenza", -1).limit(limit).to_list(limit)


async def find_sinistri(anagrafica_id: Optional[str] = None, anno: Optional[int] = None,
                        limit: int = 20) -> list[dict]:
    filt = {}
    if anagrafica_id: filt["anagrafica_id"] = anagrafica_id
    if anno:
        filt["data_sinistro"] = {"$regex": f"^{anno}"}
    proj = {"_id": 0, "id": 1, "numero_sinistro": 1, "data_sinistro": 1, "stato": 1,
            "tipo_sinistro": 1, "importo_richiesto": 1, "importo_liquidato": 1}
    return await db.sinistri.find(filt, proj).sort("data_sinistro", -1).limit(limit).to_list(limit)


async def find_veicoli(targa: Optional[str] = None, proprietario_id: Optional[str] = None,
                       limit: int = 20) -> list[dict]:
    filt = {}
    if targa: filt["targa"] = targa.upper().replace(" ", "")
    if proprietario_id: filt["proprietario_id"] = proprietario_id
    proj = {"_id": 0, "id": 1, "targa": 1, "marca": 1, "modello": 1, "telaio": 1,
            "anno_immatricolazione": 1, "alimentazione": 1, "proprietario": 1}
    return await db.veicoli.find(filt, proj).limit(limit).to_list(limit)


async def db_summary_counts() -> dict:
    """Riepilogo generico: quanti record per collezione."""
    out = {}
    for coll in ["anagrafiche", "polizze", "titoli", "sinistri", "veicoli", "allegati"]:
        try:
            out[coll] = await db[coll].count_documents({})
        except Exception:
            out[coll] = "n/d"
    return out


# ---------- LLM chat con function calling manuale ----------
SYSTEM_PROMPT = """Sei l'AI Copilot di un CRM assicurativo italiano ("Programma Assicurativo").
Aiuti l'agente/collaboratore a interrogare i dati storici del CRM: anagrafiche clienti,
polizze, titoli/quietanze/pagamenti, sinistri, veicoli, allegati/documenti.

REGOLE:
- Rispondi sempre in ITALIANO, in modo conciso e professionale.
- Se l'utente cerca un cliente, chiama search_anagrafiche.
- Se cerca polizze/titoli/sinistri/veicoli, chiama la funzione dedicata con filtri appropriati.
- Se serve un dato aggregato, spiega cosa hai trovato e mostralo in una tabella compatta.
- Se non trovi nulla, dillo chiaramente e proponi filtri alternativi.
- NON inventare mai dati: se non hai il dato, rispondi "Non trovato nel database".
- Rispondi in Markdown con tabelle quando ci sono più record.
"""


async def copilot_answer(user_message: str, ctx_data: dict) -> str:
    """Chiama Claude/GPT tramite emergentintegrations passando i dati raccolti."""
    if not EMERGENT_LLM_KEY:
        return "⚠️ Emergent LLM Key non configurata. Contatta l'amministratore."
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"copilot_{_now()[:10]}",
            system_message=SYSTEM_PROMPT,
        ).with_model("openai", "gpt-5.4")
        ctx_str = "\n".join([f"### {k}\n{v}" for k, v in ctx_data.items() if v])
        prompt = f"Domanda utente: {user_message}\n\nDati recuperati dal DB:\n{ctx_str or '(nessun dato pertinente trovato)'}"
        resp = await chat.send_message(UserMessage(text=prompt))
        return resp if isinstance(resp, str) else str(resp)
    except Exception as e:
        logger.error("Copilot LLM error: %s", e)
        return f"⚠️ Errore Copilot: {str(e)[:200]}"


async def dispatch_query(user_message: str) -> dict:
    """Heuristics: capisce l'intent e recupera dati pertinenti dal DB.

    Non usa LLM per il routing (per velocità/costi); usa regex + parole chiave.
    """
    msg = user_message.lower()
    ctx = {}

    # Anno menzionato (es "2021", "5 anni fa")
    anno = None
    m = re.search(r"\b(20\d{2}|19\d{2})\b", msg)
    if m:
        anno = int(m.group(1))
    m2 = re.search(r"(\d+)\s+anni\s+fa", msg)
    if m2:
        anno = datetime.now().year - int(m2.group(1))

    # Nome/cognome/CF (nome proprio con maiuscola)
    nome_match = re.findall(r"\b([A-Z][a-zà-ù]{2,}(?:\s+[A-Z][a-zà-ù]{2,})?)\b", user_message)
    anagrafica_id = None
    if nome_match:
        # Cerca il primo nome che sembra un cliente
        for candidate in nome_match:
            found = await search_anagrafiche(candidate, limit=3)
            if found:
                ctx[f"Anagrafiche trovate per '{candidate}'"] = found
                if len(found) == 1:
                    anagrafica_id = found[0]["id"]
                break

    # Targa: 5-7 caratteri alfanumerici in mezzo alla frase
    targa_match = re.search(r"\b([A-Z]{2}\s?\d{3}\s?[A-Z]{2})\b", user_message.upper())
    if targa_match:
        targa = targa_match.group(1).replace(" ", "")
        v = await find_veicoli(targa=targa, limit=5)
        ctx[f"Veicoli con targa '{targa}'"] = v

    # Keywords
    if any(k in msg for k in ["pagament", "titol", "quietanz", "incass"]):
        titoli = await find_titoli(anagrafica_id=anagrafica_id, anno=anno, limit=30)
        ctx[f"Titoli/pagamenti trovati"] = titoli
    if any(k in msg for k in ["polizz", "scadenz", "contratt"]):
        pol = await find_polizze(anagrafica_id=anagrafica_id, anno_scadenza=anno, limit=20)
        ctx["Polizze trovate"] = pol
    if any(k in msg for k in ["sinistr", "denunc"]):
        sin = await find_sinistri(anagrafica_id=anagrafica_id, anno=anno, limit=15)
        ctx["Sinistri trovati"] = sin
    if any(k in msg for k in ["veicol", "auto", "macchin", "moto"]) and not targa_match:
        v = await find_veicoli(proprietario_id=anagrafica_id, limit=15)
        ctx["Veicoli"] = v
    if any(k in msg for k in ["riepilog", "quanti", "totale", "conta"]):
        ctx["Riepilogo DB"] = await db_summary_counts()

    return ctx
