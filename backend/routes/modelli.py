"""Routes per la libreria "Gestioni Modelli".

Permette CRUD sui ``TemplateModello`` (testi/HTML editabili per Email,
WhatsApp, SMS e PDF). I modelli sono usati dai flussi di invio (avvisi
scadenze, sollecitazioni, lettera abbuono, ecc.) tramite il helper
``get_template_or_default``.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_user
from database import db
from db_models import TemplateModello, _now_iso
from shared import log_attivita


router = APIRouter()


_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class ModelloBody(BaseModel):
    tipo: str
    nome: str
    oggetto: Optional[str] = None
    corpo: str = ""
    sezioni: list[dict] = []
    categoria: Optional[str] = None
    default: bool = False
    attivo: bool = True
    note: Optional[str] = None


def _autodetect_placeholders(body: ModelloBody) -> list[str]:
    """Estrae i placeholder ``{nome}`` da corpo + oggetto + sezioni."""
    texts: list[str] = [body.corpo or "", body.oggetto or ""]
    for s in (body.sezioni or []):
        texts.append(str(s.get("titolo") or ""))
        texts.append(str(s.get("contenuto") or ""))
    out: list[str] = []
    seen: set[str] = set()
    for t in texts:
        for m in _PLACEHOLDER_RE.findall(t):
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


@router.get("/librerie/modelli")
async def list_modelli(
    tipo: Optional[str] = None,
    categoria: Optional[str] = None,
    user: dict = Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if tipo:
        flt["tipo"] = tipo
    if categoria:
        flt["categoria"] = categoria
    items = await db.template_modelli.find(flt, {"_id": 0}).sort([
        ("tipo", 1), ("nome", 1),
    ]).to_list(500)
    return items


@router.get("/librerie/modelli/{mid}")
async def get_modello(mid: str, user: dict = Depends(current_user)) -> dict:
    m = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Modello non trovato")
    return m


@router.post("/librerie/modelli", status_code=201)
async def create_modello(
    body: ModelloBody,
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    placeholders = _autodetect_placeholders(body)
    doc = TemplateModello(
        tipo=body.tipo,                 # type: ignore[arg-type]
        nome=body.nome.strip(),
        oggetto=body.oggetto,
        corpo=body.corpo,
        sezioni=body.sezioni,
        categoria=body.categoria,
        default=body.default,
        attivo=body.attivo,
        note=body.note,
        placeholders=placeholders,
    ).model_dump()
    # Se default=True, sbianca altri default dello stesso tipo
    if body.default:
        await db.template_modelli.update_many(
            {"tipo": body.tipo, "default": True},
            {"$set": {"default": False}},
        )
    await db.template_modelli.insert_one(doc)
    await log_attivita(user, "create", "modello", doc["id"], doc["nome"])
    return doc


@router.put("/librerie/modelli/{mid}")
async def update_modello(
    mid: str,
    body: ModelloBody,
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    existing = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Modello non trovato")
    placeholders = _autodetect_placeholders(body)
    upd = body.model_dump()
    upd["placeholders"] = placeholders
    upd["updated_at"] = _now_iso()
    if body.default:
        await db.template_modelli.update_many(
            {"tipo": body.tipo, "default": True, "id": {"$ne": mid}},
            {"$set": {"default": False}},
        )
    await db.template_modelli.update_one({"id": mid}, {"$set": upd})
    await log_attivita(user, "update", "modello", mid, upd["nome"])
    out = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    return out  # type: ignore[return-value]


@router.delete("/librerie/modelli/{mid}")
async def delete_modello(
    mid: str,
    user: dict = Depends(require_user("admin")),
) -> dict:
    res = await db.template_modelli.delete_one({"id": mid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Modello non trovato")
    await log_attivita(user, "delete", "modello", mid)
    return {"ok": True}


# ============================================================
# Helper riutilizzato da altri moduli (avvisi, lettera abbuono, ecc.)
# ============================================================
async def get_default_template(tipo: str) -> Optional[dict]:
    """Ritorna il modello marcato come default per il tipo, oppure None."""
    return await db.template_modelli.find_one(
        {"tipo": tipo, "default": True, "attivo": True}, {"_id": 0},
    )


async def seed_default_models() -> None:
    """Crea modelli di esempio se la collezione è vuota (idempotente)."""
    if await db.template_modelli.count_documents({}) > 0:
        return

    defaults = [
        {
            "tipo": "email",
            "nome": "Avviso scadenza - Email",
            "oggetto": "Promemoria scadenza polizza/e — {azienda_nome}",
            "corpo": (
                "Gentile {cliente_nome},\n\n"
                "riteniamo opportuno ricordarLe la scadenza delle rate di premio "
                "relative alle coperture assicurative i cui termini risultano sotto evidenziati.\n\n"
                "Per il rinnovo e per verificare insieme che tutte le garanzie corrispondano "
                "alle Sue attuali esigenze, La aspettiamo in Agenzia.\n\n"
                "La ringraziamo per l'attenzione e Le inviamo i nostri migliori saluti.\n\n"
                "{azienda_nome}"
            ),
            "categoria": "scadenze",
            "default": True,
        },
        {
            "tipo": "whatsapp",
            "nome": "Avviso scadenza - WhatsApp",
            "corpo": (
                "Buongiorno {cliente_nome}, le ricordiamo che ha {numero_titoli} titolo/i in scadenza "
                "per un totale di {totale} €. La invitiamo a contattarci in Agenzia. "
                "Grazie, {azienda_nome}."
            ),
            "categoria": "scadenze",
            "default": True,
        },
        {
            "tipo": "sms",
            "nome": "Avviso scadenza - SMS",
            "corpo": (
                "{azienda_nome}: gentile {cliente_nome}, titoli in scadenza totale {totale} €. "
                "Contattaci per il rinnovo."
            ),
            "categoria": "scadenze",
            "default": True,
        },
        {
            "tipo": "pdf_avviso",
            "nome": "Avviso scadenza - PDF (default)",
            "oggetto": "Gentile {cliente_nome},",
            "corpo": (
                "riteniamo opportuno ricordarLe la scadenza delle rate di premio relative alle "
                "coperture assicurative i cui termini risultano sotto evidenziati.\n\n"
                "Per il rinnovo e per verificare insieme che tutte le garanzie corrispondano alle "
                "Sue attuali esigenze, La aspettiamo in Agenzia, dove continuerà a godere "
                "dell'attenzione e del servizio che dedichiamo ai nostri Clienti.\n\n"
                "La ringraziamo per l'attenzione e Le inviamo i nostri migliori saluti."
            ),
            "sezioni": [
                {
                    "ordine": 1,
                    "attiva": True,
                    "titolo": "QUANTO COSTA IN MEDIA UNA CAUSA O UNA CONTROVERSIA IN ITALIA? CIRCA 3.500 €",
                    "contenuto": (
                        "La polizza di Tutela Legale dovrebbe essere una polizza obbligatoria. "
                        "Quali garanzie ci fornisce?\n\n"
                        "• Libera scelta del proprio legale di fiducia\n"
                        "• Libera scelta di un perito di parte\n"
                        "• Controversie con compagnie di assicurazione\n"
                        "• Assicurati tutti i componenti del nucleo familiare nello stato di famiglia\n\n"
                        "E QUANTO COSTA ALL'ANNO ? 15 €"
                    ),
                },
            ],
            "categoria": "scadenze",
            "default": True,
        },
        {
            "tipo": "pdf_lettera_abbuono",
            "nome": "Lettera di Abbuono (default)",
            "corpo": (
                "Con la presente si attesta che, in occasione del pagamento del titolo "
                "n. {numero_titolo} relativo alla polizza n. {numero_polizza}, è stato "
                "concesso un abbuono di € {importo_abbuono} per i motivi sotto indicati."
            ),
            "categoria": "fiscale",
            "default": True,
        },
    ]
    for d in defaults:
        doc = TemplateModello(**d).model_dump()
        # Auto-detect placeholders
        body = ModelloBody(**{k: v for k, v in d.items() if k in ModelloBody.model_fields})
        doc["placeholders"] = _autodetect_placeholders(body)
        await db.template_modelli.insert_one(doc)
