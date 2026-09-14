"""Librerie routes — endpoint CRUD per le tabelle di lookup.

Estratto da server.py (~570 righe). Tutti gli endpoint sono prefissati
`/api/librerie` (oltre a quelli `/api/...` non-librerie del modulo come
banche / mapping-garanzie / mapping-operatori / azienda — che restano
sotto il prefisso /librerie nei loro path completi).
"""
from __future__ import annotations
import os
import re
from typing import Literal, Optional
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict

from database import db
from db_models import (
    _now_iso, _uid,
    AziendaConfig, Banca, ContattoCompagnia, ContoCassa, MezzoPagamento,
    ProdottoLibreria, RamoLibreria, SchemaProvvigionale, TipoPagamento,
    VoceBilancio,
    default_mora_for_ramo,
)
from auth import current_user, require_user
from shared import log_attivita, strip_mongo_id
from tenant import is_super_admin
import storage as obj_storage

router = APIRouter()


def _libreria_routes(coll_name: str, model_cls: type, ruoli_modifica: tuple[str, ...] = ("admin", "collaboratore")) -> None:
    """Crea endpoint CRUD standard per una collezione di libreria."""
    # implementato direttamente sotto per ogni risorsa
    return None


async def _usi_pagamento(conto_id: Optional[str] = None, labels: Optional[list[str]] = None) -> int:
    """Conta i movimenti/titoli che usano un conto (per id) o un'etichetta di pagamento."""
    ors: list[dict] = []
    if conto_id:
        ors.append({"conto_cassa_id": conto_id})
    for lbl in labels or []:
        if lbl:
            ors.append({"mezzo_pagamento": {"$regex": f"^{re.escape(lbl)}$", "$options": "i"}})
    if not ors:
        return 0
    return (await db.movimenti.count_documents({"$or": ors})
            + await db.titoli.count_documents({"$or": ors}))


# --- BANCHE ---
@router.get("/librerie/banche")
async def list_banche(user: dict = Depends(current_user)) -> list[dict]:
    return await db.banche.find({}, {"_id": 0}).sort("nome", 1).to_list(500)


@router.post("/librerie/banche", status_code=201)
async def create_banca(body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    obj = Banca(**body)
    await db.banche.insert_one(obj.model_dump())
    await log_attivita(user, "create", "banca", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/banche/{bid}")
async def update_banca(bid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    body["updated_at"] = _now_iso()
    res = await db.banche.update_one({"id": bid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Banca non trovata")
    await log_attivita(user, "update", "banca", bid)
    return strip_mongo_id(await db.banche.find_one({"id": bid}, {"_id": 0}))


@router.delete("/librerie/banche/{bid}")
async def delete_banca(bid: str, user: dict = Depends(require_user("admin"))) -> dict:
    banca = await db.banche.find_one({"id": bid}, {"_id": 0})
    if not banca:
        raise HTTPException(404, "Banca non trovata")
    usi = await _usi_pagamento(labels=[banca.get("nome")])
    if usi > 0:
        raise HTTPException(400, f"'{banca.get('nome')}' è usata in {usi} movimenti/titoli dello storico: "
                                 "non può essere eliminata. Archiviala disattivandola.")
    await db.banche.delete_one({"id": bid})
    await log_attivita(user, "delete", "banca", bid)
    return {"ok": True}


# --- CONTI CASSA ---
@router.get("/librerie/conti-cassa")
async def list_conti(attivi: Optional[bool] = None, user: dict = Depends(current_user)) -> list[dict]:
    flt = {}
    if attivi is not None:
        flt["attivo"] = attivi
    return await db.conti_cassa.find(flt, {"_id": 0}).sort("ordine", 1).to_list(500)


# --- MAPPING GARANZIE ANIA → nome personalizzato ---
@router.get("/librerie/mapping-garanzie")
async def list_mapping_garanzie(user: dict = Depends(current_user)) -> list[dict]:
    return await db.mapping_garanzie.find({}, {"_id": 0}).sort("codice_ania", 1).to_list(2000)


@router.post("/librerie/mapping-garanzie", status_code=201)
async def create_mapping_garanzia(body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    if not body.get("codice_ania"):
        raise HTTPException(400, "Codice ANIA obbligatorio")
    body["id"] = body.get("id") or _uid()
    body["created_at"] = _now_iso()
    body["updated_at"] = _now_iso()
    body["is_deleted"] = False
    await db.mapping_garanzie.insert_one(body)
    return strip_mongo_id(body)


@router.put("/librerie/mapping-garanzie/{mid}")
async def update_mapping_garanzia(mid: str, body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    body["updated_at"] = _now_iso()
    r = await db.mapping_garanzie.update_one({"id": mid}, {"$set": body})
    if r.matched_count == 0:
        raise HTTPException(404, "Mapping non trovato")
    return strip_mongo_id(await db.mapping_garanzie.find_one({"id": mid}, {"_id": 0}))


@router.delete("/librerie/mapping-garanzie/{mid}")
async def delete_mapping_garanzia(mid: str, user: dict = Depends(require_user("admin"))) -> dict:
    await db.mapping_garanzie.delete_one({"id": mid})
    return {"ok": True}


# --- MAPPING OPERATORI ANIA → user_id applicativo ---
@router.get("/librerie/mapping-operatori")
async def list_mapping_operatori(user: dict = Depends(current_user)) -> list[dict]:
    items = await db.mapping_operatori.find({}, {"_id": 0}).sort("codice_ania", 1).to_list(2000)
    # arricchimento user
    uids = [i["user_id"] for i in items if i.get("user_id")]
    users = {u["id"]: u async for u in db.users.find(
        {"id": {"$in": uids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1},
    )}
    for i in items:
        if i.get("user_id"):
            i["user"] = users.get(i["user_id"])
    return items


@router.post("/librerie/mapping-operatori", status_code=201)
async def create_mapping_operatore(body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    if not body.get("codice_ania"):
        raise HTTPException(400, "Codice operatore obbligatorio")
    body["id"] = body.get("id") or _uid()
    body["created_at"] = _now_iso()
    body["updated_at"] = _now_iso()
    body["is_deleted"] = False
    await db.mapping_operatori.insert_one(body)
    return strip_mongo_id(body)


@router.put("/librerie/mapping-operatori/{mid}")
async def update_mapping_operatore(mid: str, body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    body["updated_at"] = _now_iso()
    r = await db.mapping_operatori.update_one({"id": mid}, {"$set": body})
    if r.matched_count == 0:
        raise HTTPException(404, "Mapping non trovato")
    return strip_mongo_id(await db.mapping_operatori.find_one({"id": mid}, {"_id": 0}))


@router.delete("/librerie/mapping-operatori/{mid}")
async def delete_mapping_operatore(mid: str, user: dict = Depends(require_user("admin"))) -> dict:
    await db.mapping_operatori.delete_one({"id": mid})
    return {"ok": True}


@router.post("/librerie/mapping-operatori/applica-a-polizze")
async def applica_mapping_operatori(user: dict = Depends(require_user("admin"))) -> dict:
    """Riapplica il mapping operatori a TUTTE le polizze esistenti (utile dopo aver mappato gli operatori)."""
    aggiornate = 0
    async for m in db.mapping_operatori.find({"user_id": {"$ne": None}}, {"_id": 0}):
        if not m.get("user_id"):
            continue
        r = await db.polizze.update_many(
            {"operatore_ania_codice": m["codice_ania"]},
            {"$set": {"collaboratore_id": m["user_id"], "updated_at": _now_iso()}},
        )
        aggiornate += r.modified_count
    return {"polizze_aggiornate": aggiornate}


@router.post("/librerie/mapping-garanzie/applica-a-polizze")
async def applica_mapping_garanzie(user: dict = Depends(require_user("admin"))) -> dict:
    """Riapplica il mapping garanzie alle polizze esistenti (rinomina garanzia.garanzia con nome_personalizzato)."""
    aggiornate = 0
    map_dict = {}
    async for m in db.mapping_garanzie.find({}, {"_id": 0}):
        if not m.get("nome_personalizzato"):
            continue
        k = (m.get("codice_ania") or "").strip().upper()
        if k:
            map_dict[k] = m["nome_personalizzato"]
    async for p in db.polizze.find({"garanzie": {"$exists": True, "$ne": []}}, {"_id": 0, "id": 1, "garanzie": 1}):
        changed = False
        for g in p.get("garanzie") or []:
            codice = (g.get("codice_ania") or "").strip().upper()
            if codice and codice in map_dict and g.get("garanzia") != map_dict[codice]:
                g["garanzia"] = map_dict[codice]
                changed = True
        if changed:
            await db.polizze.update_one({"id": p["id"]}, {"$set": {"garanzie": p["garanzie"], "updated_at": _now_iso()}})
            aggiornate += 1
    return {"polizze_aggiornate": aggiornate}


@router.post("/librerie/conti-cassa", status_code=201)
async def create_conto(body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    if not (body.get("nome") or "").strip():
        raise HTTPException(400, "Nome conto obbligatorio")
    obj = ContoCassa(**body)
    await db.conti_cassa.insert_one(obj.model_dump())
    await log_attivita(user, "create", "conto_cassa", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/conti-cassa/{cid}")
async def update_conto(cid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    if "nome" in body and not (body.get("nome") or "").strip():
        raise HTTPException(400, "Nome conto obbligatorio")
    body["updated_at"] = _now_iso()
    res = await db.conti_cassa.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Conto non trovato")
    await log_attivita(user, "update", "conto_cassa", cid)
    return strip_mongo_id(await db.conti_cassa.find_one({"id": cid}, {"_id": 0}))


@router.delete("/librerie/conti-cassa/{cid}")
async def delete_conto(cid: str, user: dict = Depends(require_user("admin"))) -> dict:
    conto = await db.conti_cassa.find_one({"id": cid}, {"_id": 0})
    if not conto:
        raise HTTPException(404, "Conto non trovato")
    usi = await _usi_pagamento(conto_id=cid, labels=[conto.get("nome")])
    if usi > 0:
        raise HTTPException(400, f"'{conto.get('nome')}' è usato in {usi} movimenti/titoli dello storico: "
                                 "non può essere eliminato. Archivialo impostando Attivo = no.")
    await db.conti_cassa.delete_one({"id": cid})
    await log_attivita(user, "delete", "conto_cassa", cid)
    return {"ok": True}



# --- MEZZI DI PAGAMENTO (libreria unificata) ---
class MezzoPagamentoBody(BaseModel):
    codice: str
    label: str
    tipo_conto: Literal["cassa", "banca", "carta", "rid", "online", "altro"] = "altro"
    conto_default_id: Optional[str] = None
    icona: Optional[str] = None
    ordine: int = 0
    attivo: bool = True


@router.get("/librerie/mezzi-pagamento")
async def list_mezzi_pagamento(
    attivi: bool = False,
    user: dict = Depends(current_user),
) -> list[dict]:
    flt = {}
    if attivi:
        flt["attivo"] = True
    items = await db.mezzi_pagamento.find(flt, {"_id": 0}).sort([("ordine", 1), ("label", 1)]).to_list(200)
    return items


@router.post("/librerie/mezzi-pagamento", status_code=201)
async def create_mezzo_pagamento(body: MezzoPagamentoBody, user: dict = Depends(require_user("admin"))) -> dict:
    codice = body.codice.strip().lower()
    if not codice or not body.label:
        raise HTTPException(400, "Codice e label obbligatori")
    existing = await db.mezzi_pagamento.find_one({"codice": codice}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(400, f"Codice '{codice}' già presente")
    item = MezzoPagamento(
        codice=codice, label=body.label, tipo_conto=body.tipo_conto,
        conto_default_id=body.conto_default_id, icona=body.icona,
        ordine=body.ordine, attivo=body.attivo,
    )
    await db.mezzi_pagamento.insert_one(item.model_dump())
    return item.model_dump()


@router.put("/librerie/mezzi-pagamento/{mid}")
async def update_mezzo_pagamento(mid: str, body: MezzoPagamentoBody, user: dict = Depends(require_user("admin"))) -> dict:
    existing = await db.mezzi_pagamento.find_one({"id": mid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Mezzo non trovato")
    upd = {**body.model_dump(), "updated_at": _now_iso()}
    upd["codice"] = upd["codice"].strip().lower()
    await db.mezzi_pagamento.update_one({"id": mid}, {"$set": upd})
    return {**existing, **upd}


@router.delete("/librerie/mezzi-pagamento/{mid}")
async def delete_mezzo_pagamento(mid: str, user: dict = Depends(require_user("admin"))) -> dict:
    mezzo = await db.mezzi_pagamento.find_one({"id": mid}, {"_id": 0})
    if not mezzo:
        raise HTTPException(404, "Mezzo non trovato")
    usi = await _usi_pagamento(labels=[mezzo.get("codice"), mezzo.get("label")])
    if usi > 0:
        raise HTTPException(400, f"'{mezzo.get('label')}' è usato in {usi} movimenti/titoli dello storico: "
                                 "non può essere eliminato. Disattivalo per archiviarlo.")
    await db.mezzi_pagamento.delete_one({"id": mid})
    return {"ok": True}


# === COMUNICAZIONI (Email SMTP + Twilio SMS/WhatsApp) ===
# Sottoinsieme di AziendaConfig esposto come endpoint dedicato per la nuova
# tab "Configurazione comunicazioni" in Librerie. Mantiene piena compatibilità
# con il flusso esistente che legge da `azienda_config`.

_COMUNICAZIONI_FIELDS = [
    "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from", "smtp_use_tls",
    "imap_host", "imap_port", "imap_user", "imap_password", "imap_use_ssl", "imap_folder",
    "twilio_account_sid", "twilio_auth_token", "twilio_sms_from", "twilio_whatsapp_from",
    "spoki_api_key", "spoki_sender_name", "whatsapp_provider",
]

# Campi gestibili SOLO dal super admin (chiavi API / provider a pagamento)
_CAMPI_SOLO_SUPER_ADMIN = (
    "twilio_account_sid", "twilio_auth_token", "twilio_sms_from", "twilio_whatsapp_from",
    "spoki_api_key", "spoki_sender_name", "whatsapp_provider",
)

# Segreti mai esposti agli utenti dell'agenzia (visibili solo in console super admin)
_SEGRETI_AZIENDA = (
    "firma_api_token", "firma_webhook_secret", "firma_base_url", "firma_environment",
    "firma_provider", "smtp_password", "imap_password",
    "twilio_account_sid", "twilio_auth_token", "spoki_api_key",
)


class ComunicazioniBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: bool = True
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: bool = True
    imap_folder: str = "INBOX"
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_sms_from: Optional[str] = None
    twilio_whatsapp_from: Optional[str] = None
    spoki_api_key: Optional[str] = None
    spoki_sender_name: Optional[str] = None
    whatsapp_provider: Optional[str] = "wame"  # wame | twilio | spoki


@router.get("/librerie/comunicazioni")
async def get_comunicazioni(user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    out = {k: az.get(k) for k in _COMUNICAZIONI_FIELDS}
    if out.get("smtp_password"):
        out["smtp_password_set"] = True
        out["smtp_password"] = "••••••••"
    else:
        out["smtp_password_set"] = False
    if out.get("imap_password"):
        out["imap_password_set"] = True
        out["imap_password"] = "••••••••"
    else:
        out["imap_password_set"] = False
    if out.get("twilio_auth_token"):
        out["twilio_auth_token_set"] = True
        out["twilio_auth_token"] = "••••••••"
    else:
        out["twilio_auth_token_set"] = False
    if out.get("spoki_api_key"):
        out["spoki_api_key_set"] = True
        out["spoki_api_key"] = "••••••••"
    else:
        out["spoki_api_key_set"] = False
    if not is_super_admin(user):
        # Le chiavi/config dei provider a pagamento sono riservate al super admin.
        for k in ("twilio_account_sid", "twilio_auth_token", "twilio_sms_from",
                  "twilio_whatsapp_from", "spoki_api_key", "spoki_sender_name"):
            out.pop(k, None)
        out.pop("twilio_auth_token_set", None)
        out.pop("spoki_api_key_set", None)
    return out


@router.put("/librerie/comunicazioni")
async def update_comunicazioni(body: ComunicazioniBody,
                                user: dict = Depends(require_user("admin"))) -> dict:
    from credentials_utils import clean_password, clean_email
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    upd: dict = {k: getattr(body, k) for k in _COMUNICAZIONI_FIELDS}
    if not is_super_admin(user):
        # Gli admin agenzia non possono vedere né modificare chiavi/provider a pagamento
        for k in _CAMPI_SOLO_SUPER_ADMIN:
            upd.pop(k, None)
    # Normalizza email e password (rimuove NBSP, doppia concatenazione, ecc.)
    if upd.get("smtp_user"):
        upd["smtp_user"] = clean_email(upd["smtp_user"])
    if upd.get("imap_user"):
        upd["imap_user"] = clean_email(upd["imap_user"])
    if upd.get("smtp_password") and upd["smtp_password"] != "••••••••":
        upd["smtp_password"] = clean_password(upd["smtp_password"])
    if upd.get("imap_password") and upd["imap_password"] != "••••••••":
        upd["imap_password"] = clean_password(upd["imap_password"])
    if upd.get("smtp_password") in (None, "", "••••••••"):
        upd.pop("smtp_password", None)
    if upd.get("imap_password") in (None, "", "••••••••"):
        upd.pop("imap_password", None)
    if upd.get("twilio_auth_token") in (None, "", "••••••••"):
        upd.pop("twilio_auth_token", None)
    if upd.get("spoki_api_key") in (None, "", "••••••••"):
        upd.pop("spoki_api_key", None)
    upd["updated_at"] = _now_iso()
    if az:
        await db.azienda_config.update_one({"id": az["id"]}, {"$set": upd})
    else:
        new_doc = AziendaConfig(**upd)
        await db.azienda_config.insert_one(new_doc.model_dump())
    await log_attivita(user, "update", "comunicazioni", "azienda")
    return await get_comunicazioni(user)


@router.post("/librerie/comunicazioni/test")
async def test_comunicazioni(body: dict,
                               user: dict = Depends(require_user("admin"))) -> dict:
    """body: { canale: 'email'|'sms'|'whatsapp', destinatario: str, messaggio?: str }"""
    canale = (body.get("canale") or "").lower()
    dest = (body.get("destinatario") or "").strip()
    msg = body.get("messaggio") or "Test di invio dalla configurazione Comunicazioni del programma Assicura."
    if not dest:
        raise HTTPException(400, "Destinatario obbligatorio")
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}

    if canale == "email":
        if not (az.get("smtp_host") and az.get("smtp_user")):
            raise HTTPException(400, "SMTP non configurato (host/user mancanti)")
        from email_utils import smtp_send
        try:
            smtp_send(
                az, to_addrs=dest,
                subject="Test invio email — Assicura",
                text=msg,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(503, f"Errore invio email: {e}")
        return {"ok": True, "canale": "email", "destinatario": dest, "from": az.get("smtp_user")}

    if canale in ("sms", "whatsapp"):
        if not (az.get("twilio_account_sid") and az.get("twilio_auth_token")):
            raise HTTPException(400, "Twilio non configurato (SID/Token mancanti)")
        try:
            from twilio.rest import Client  # type: ignore[import-untyped]
        except ImportError:
            raise HTTPException(503, "Libreria Twilio non installata sul server. Installare 'twilio'.")
        try:
            client = Client(az["twilio_account_sid"], az["twilio_auth_token"])
            if canale == "sms":
                from_ = az.get("twilio_sms_from")
                if not from_:
                    raise HTTPException(400, "twilio_sms_from non configurato")
                client.messages.create(body=msg, from_=from_, to=dest)
            else:
                from_ = az.get("twilio_whatsapp_from")
                if not from_:
                    raise HTTPException(400, "twilio_whatsapp_from non configurato")
                to_ = dest if dest.startswith("whatsapp:") else f"whatsapp:{dest}"
                client.messages.create(body=msg, from_=from_, to=to_)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(503, f"Errore invio {canale}: {e}")
        return {"ok": True, "canale": canale, "destinatario": dest}

    raise HTTPException(400, "Canale non valido: email|sms|whatsapp")


@router.post("/librerie/comunicazioni/test-imap")
async def test_imap(user: dict = Depends(require_user("admin"))) -> dict:
    """Verifica la connessione IMAP corrente:
    - login con credenziali salvate
    - apertura cartella INBOX
    - conta messaggi totali + ultimi 5 (subject + From)
    """
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    from credentials_utils import clean_password, clean_email
    host = az.get("imap_host")
    port = int(az.get("imap_port") or 993)
    user_ = clean_email(az.get("imap_user"))
    pwd = clean_password(az.get("imap_password"))
    folder = az.get("imap_folder") or "INBOX"
    if not (host and user_ and pwd):
        raise HTTPException(400, "IMAP non configurato (host/user/password mancanti)")
    import imaplib
    import email as _emaillib
    from email.header import decode_header
    try:
        if az.get("imap_use_ssl", True):
            M = imaplib.IMAP4_SSL(host, port, timeout=20)
        else:
            M = imaplib.IMAP4(host, port, timeout=20)
        M.login(user_, pwd)
        typ, data = M.select(folder, readonly=True)
        if typ != "OK":
            M.logout()
            raise HTTPException(400, f"Impossibile aprire cartella '{folder}'")
        totale = int(data[0]) if data and data[0] else 0
        # Ultime 5 email
        typ, data = M.search(None, "ALL")
        ids = data[0].split() if data and data[0] else []
        last_ids = ids[-5:][::-1]
        sample = []
        for mid in last_ids:
            try:
                typ, msg_data = M.fetch(mid, "(RFC822.HEADER)")
                raw = msg_data[0][1] if msg_data and msg_data[0] else b""
                msg = _emaillib.message_from_bytes(raw)
                def _dec(h):
                    if not h:
                        return ""
                    parts = decode_header(h)
                    return "".join(
                        (p.decode(enc or "utf-8", errors="replace") if isinstance(p, bytes) else p)
                        for p, enc in parts
                    )
                sample.append({
                    "subject": _dec(msg.get("Subject"))[:120],
                    "from": _dec(msg.get("From"))[:120],
                    "date": msg.get("Date") or "",
                    "to": _dec(msg.get("To"))[:120],
                })
            except Exception:
                continue
        M.close()
        M.logout()
        return {
            "ok": True,
            "host": host, "user": user_, "folder": folder,
            "messaggi_totali": totale,
            "ultimi": sample,
        }
    except imaplib.IMAP4.error as e:
        raise HTTPException(401, f"Login IMAP fallito: {e}")
    except Exception as e:
        raise HTTPException(503, f"Errore connessione IMAP: {e}")


async def _seed_mezzi_pagamento() -> None:
    """Idempotente: crea le MODALITÀ di pagamento di default se mancano.

    Nota: a partire dalla v2 della libreria pagamenti la collezione
    `mezzi_pagamento` rappresenta la **modalità** (Bonifico, Assegno, Contanti,
    POS, RID, ecc.). La combinazione modalità+conto è gestita da
    `tipi_pagamento` (vedi `_seed_tipi_pagamento`).
    """
    defaults = [
        {"codice": "contanti", "label": "Contanti", "tipo_conto": "cassa", "ordine": 1, "icona": "Banknote"},
        {"codice": "bonifico", "label": "Bonifico bancario", "tipo_conto": "banca", "ordine": 2, "icona": "Building2"},
        {"codice": "assegno", "label": "Assegno", "tipo_conto": "banca", "ordine": 3, "icona": "FileCheck"},
        {"codice": "pos", "label": "POS / Carta", "tipo_conto": "carta", "ordine": 4, "icona": "CreditCard"},
        {"codice": "bancomat", "label": "Bancomat", "tipo_conto": "carta", "ordine": 5, "icona": "CreditCard"},
        {"codice": "rid", "label": "RID / SDD", "tipo_conto": "rid", "ordine": 6, "icona": "Repeat"},
        {"codice": "altro", "label": "Altro", "tipo_conto": "altro", "ordine": 99, "icona": "MoreHorizontal"},
    ]
    for d in defaults:
        existing = await db.mezzi_pagamento.find_one({"codice": d["codice"]}, {"_id": 0, "id": 1})
        if existing:
            continue
        item = MezzoPagamento(**d)
        await db.mezzi_pagamento.insert_one(item.model_dump())


# --- TIPI PAGAMENTO (combinazione modalità + conto deposito) ---
class TipoPagamentoBody(BaseModel):
    label: str
    modalita_codice: str
    conto_id: Optional[str] = None
    ordine: int = 0
    attivo: bool = True
    note: Optional[str] = None


@router.get("/librerie/tipi-pagamento")
async def list_tipi_pagamento(
    attivi: bool = False,
    user: dict = Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if attivi:
        flt["attivo"] = True
    items = await db.tipi_pagamento.find(flt, {"_id": 0}).sort([("ordine", 1), ("label", 1)]).to_list(500)
    conto_ids = list({i.get("conto_id") for i in items if i.get("conto_id")})
    if conto_ids:
        conti = {c["id"]: c["nome"] async for c in db.conti_cassa.find(
            {"id": {"$in": conto_ids}}, {"_id": 0, "id": 1, "nome": 1},
        )}
        for i in items:
            if i.get("conto_id"):
                i["conto_nome"] = conti.get(i["conto_id"])
    return items


@router.post("/librerie/tipi-pagamento", status_code=201)
async def create_tipo_pagamento(body: TipoPagamentoBody, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    label = (body.label or "").strip()
    if not label or not body.modalita_codice:
        raise HTTPException(400, "Label e modalità sono obbligatori")
    existing = await db.tipi_pagamento.find_one({"label": label}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(400, f"Tipo pagamento '{label}' già presente")
    item = TipoPagamento(
        label=label.upper(),
        modalita_codice=body.modalita_codice.strip().lower(),
        conto_id=body.conto_id or None,
        ordine=body.ordine,
        attivo=body.attivo,
        note=body.note,
    )
    await db.tipi_pagamento.insert_one(item.model_dump())
    await log_attivita(user, "create", "tipo_pagamento", item.id, item.label)
    return item.model_dump()


@router.put("/librerie/tipi-pagamento/{tid}")
async def update_tipo_pagamento(tid: str, body: TipoPagamentoBody,
                                 user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    existing = await db.tipi_pagamento.find_one({"id": tid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Tipo pagamento non trovato")
    upd = {
        "label": body.label.strip().upper(),
        "modalita_codice": body.modalita_codice.strip().lower(),
        "conto_id": body.conto_id or None,
        "ordine": body.ordine,
        "attivo": body.attivo,
        "note": body.note,
        "updated_at": _now_iso(),
    }
    await db.tipi_pagamento.update_one({"id": tid}, {"$set": upd})
    await log_attivita(user, "update", "tipo_pagamento", tid)
    return {**existing, **upd}


@router.delete("/librerie/tipi-pagamento/{tid}")
async def delete_tipo_pagamento(tid: str, user: dict = Depends(require_user("admin"))) -> dict:
    tipo = await db.tipi_pagamento.find_one({"id": tid}, {"_id": 0})
    if not tipo:
        raise HTTPException(404, "Tipo pagamento non trovato")
    usi = await _usi_pagamento(labels=[tipo.get("label")])
    if usi > 0:
        raise HTTPException(400, f"'{tipo.get('label')}' è usato in {usi} movimenti/titoli dello storico: "
                                 "non può essere eliminato. Disattivalo per archiviarlo.")
    await db.tipi_pagamento.delete_one({"id": tid})
    await log_attivita(user, "delete", "tipo_pagamento", tid)
    return {"ok": True}


# --- VOCI DI BILANCIO (mini-bilancio Cervello) ---
@router.get("/librerie/voci-bilancio")
async def list_voci_bilancio(
    attivi: bool = False,
    user: dict = Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if attivi:
        flt["attivo"] = True
    return await db.voci_bilancio.find(flt, {"_id": 0}).sort([("tipo", 1), ("ordine", 1), ("nome", 1)]).to_list(500)


@router.post("/librerie/voci-bilancio", status_code=201)
async def create_voce_bilancio(body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    if not (body.get("nome") or "").strip():
        raise HTTPException(400, "Nome voce obbligatorio")
    obj = VoceBilancio(**body)
    await db.voci_bilancio.insert_one(obj.model_dump())
    await log_attivita(user, "create", "voce_bilancio", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/voci-bilancio/{vid}")
async def update_voce_bilancio(vid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    if "nome" in body and not (body.get("nome") or "").strip():
        raise HTTPException(400, "Nome voce obbligatorio")
    body["updated_at"] = _now_iso()
    res = await db.voci_bilancio.update_one({"id": vid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Voce non trovata")
    await log_attivita(user, "update", "voce_bilancio", vid)
    return strip_mongo_id(await db.voci_bilancio.find_one({"id": vid}, {"_id": 0}))


@router.delete("/librerie/voci-bilancio/{vid}")
async def delete_voce_bilancio(vid: str, user: dict = Depends(require_user("admin"))) -> dict:
    res = await db.voci_bilancio.delete_one({"id": vid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Voce non trovata")
    await log_attivita(user, "delete", "voce_bilancio", vid)
    return {"ok": True}


async def _seed_voci_bilancio() -> None:
    """Idempotente: crea le voci di bilancio di default se la collezione è vuota."""
    if await db.voci_bilancio.count_documents({}) > 0:
        return
    costi = [
        "Stipendi", "Contributi / INPS", "Affitto", "Utenze", "Marketing",
        "Consulenze", "Tasse e imposte", "Software / Gestionali", "Cancelleria",
        "Carburante / Trasferte", "Altro costo",
    ]
    ricavi = ["Consulenze attive", "Altro ricavo"]
    for i, nome in enumerate(costi):
        await db.voci_bilancio.insert_one(VoceBilancio(nome=nome, tipo="costo", ordine=i + 1).model_dump())
    for i, nome in enumerate(ricavi):
        await db.voci_bilancio.insert_one(VoceBilancio(nome=nome, tipo="ricavo", ordine=i + 1).model_dump())


async def _seed_conti_deposito_estesi() -> None:
    """Aggiunge conti deposito ESTESI alla `LibreriaConti` (idempotente).

    Voci richieste dal cliente: BPER VILLA, INTESA, CREDIT AGRICOLE,
    PRELIEVO SOCI, ASSEGNI, CONTANTI, PAGAMENTI IN DIREZIONE oltre alle banche.
    """
    voci = [
        {"nome": "CONTANTI", "tipo": "cassa", "ordine": 10},
        {"nome": "ASSEGNI", "tipo": "cassa", "ordine": 11},
        {"nome": "BPER SONDRIO", "tipo": "banca", "ordine": 20},
        {"nome": "BPER VILLA", "tipo": "banca", "ordine": 21},
        {"nome": "INTESA SANPAOLO", "tipo": "banca", "ordine": 22},
        {"nome": "CREDIT AGRICOLE", "tipo": "banca", "ordine": 23},
        {"nome": "PAGAMENTI IN DIREZIONE", "tipo": "rid", "ordine": 30},
        {"nome": "PRELIEVO SOCI", "tipo": "altro", "ordine": 40},
        {"nome": "AGOS", "tipo": "altro", "ordine": 41},
    ]
    for v in voci:
        existing = await db.conti_cassa.find_one(
            {"nome": {"$regex": f"^{re.escape(v['nome'])}$", "$options": "i"}},
            {"_id": 0, "id": 1},
        )
        if existing:
            continue
        obj = ContoCassa(**v)
        await db.conti_cassa.insert_one(obj.model_dump())


async def _seed_tipi_pagamento() -> None:
    """Idempotente: crea la libreria iniziale `tipi_pagamento` combinando
    modalità × conti deposito (es. "BONIFICO BPER SONDRIO", "ASSEGNO BPER VILLA").

    Eseguito DOPO `_seed_mezzi_pagamento` e `_seed_conti_deposito_estesi`.
    """
    # Se già presenti voci, skip (admin gestisce manualmente da qui in poi).
    if await db.tipi_pagamento.count_documents({}) > 0:
        return

    modalita = {m["codice"]: m async for m in db.mezzi_pagamento.find({}, {"_id": 0})}
    conti = await db.conti_cassa.find({"attivo": True}, {"_id": 0}).sort("ordine", 1).to_list(200)

    # Mapping conti per nome upper-case
    def _conto_per_nome(nome_re: str) -> Optional[dict]:
        nome_re = nome_re.upper()
        for c in conti:
            if c["nome"].upper() == nome_re:
                return c
        return None

    # Combinazioni rilevanti per le agenzie italiane
    combinazioni: list[tuple[str, str, str]] = [
        # (modalita_codice, conto_nome, label)
        ("contanti", "CONTANTI", "CONTANTI"),
        ("contanti", "BPER SONDRIO", "CONTANTI BPER SONDRIO"),
        ("contanti", "CREDIT AGRICOLE", "CONTANTI CREDIT AGRICOLE"),
        ("assegno", "ASSEGNI", "ASSEGNO BANCARIO"),
        ("assegno", "BPER SONDRIO", "ASSEGNO BPER SONDRIO"),
        ("assegno", "BPER VILLA", "ASSEGNO BPER VILLA"),
        ("assegno", "CREDIT AGRICOLE", "ASSEGNO CREDIT AGRICOLE"),
        ("bonifico", "BPER SONDRIO", "BONIFICO BPER SONDRIO"),
        ("bonifico", "BPER VILLA", "BONIFICO BPER VILLA"),
        ("bonifico", "INTESA SANPAOLO", "BONIFICO INTESA"),
        ("bonifico", "CREDIT AGRICOLE", "BONIFICO CREDIT AGRICOLE"),
        ("rid", "BPER SONDRIO", "RID BPER SONDRIO"),
        ("rid", "PAGAMENTI IN DIREZIONE", "RID DIREZIONE"),
        ("pos", "BPER SONDRIO", "POS BPER SONDRIO"),
        ("bancomat", "BPER SONDRIO", "BANCOMAT"),
        ("altro", "AGOS", "AGOS"),
        ("altro", "PRELIEVO SOCI", "PRELIEVO SOCI"),
        ("altro", "PAGAMENTI IN DIREZIONE", "PAGAMENTO IN DIREZIONE"),
    ]
    ord_n = 0
    for mod_cod, conto_nome, label in combinazioni:
        if mod_cod not in modalita:
            continue
        conto = _conto_per_nome(conto_nome)
        # Se conto non esiste (es. caso "Altro" puro) skippiamo
        item = TipoPagamento(
            label=label,
            modalita_codice=mod_cod,
            conto_id=conto["id"] if conto else None,
            ordine=ord_n,
            attivo=True,
        )
        await db.tipi_pagamento.insert_one(item.model_dump())
        ord_n += 1
    # voce "Altro" universale
    if "altro" in modalita:
        await db.tipi_pagamento.insert_one(TipoPagamento(
            label="ALTRO", modalita_codice="altro", ordine=ord_n + 1, attivo=True,
        ).model_dump())


# --- PRODOTTI ---
def _ramo_aliases(ramo: str) -> list[str]:
    """Restituisce gli alias possibili di un ramo (case-insensitive, con/senza spazi/underscore).
    Es: 'RC Auto' -> ['RC Auto', 'RCAuto', 'RC_AUTO', 'RCAUTO', 'RCA', 'RC AUTO']
    """
    if not ramo:
        return []
    base = ramo.strip()
    normalized = base.upper().replace("_", " ").replace("-", " ")
    no_space = normalized.replace(" ", "")
    aliases = {base, base.upper(), base.lower(), normalized, no_space, normalized.replace(" ", "_")}
    # Map noti
    rca_aliases = {"RC AUTO", "RCAUTO", "RCA", "RC_AUTO"}
    if no_space in rca_aliases or normalized in rca_aliases:
        aliases |= rca_aliases
    return [a for a in aliases if a]


@router.get("/librerie/prodotti")
async def list_prodotti(
    compagnia_id: Optional[str] = None,
    ramo: Optional[str] = None,
    con_polizze: bool = False,
    user: dict = Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if compagnia_id:
        flt["compagnia_id"] = compagnia_id
    if ramo:
        # Match fuzzy: cerca tutti gli alias del ramo (case-insensitive con/senza spazi)
        aliases = _ramo_aliases(ramo)
        flt["$or"] = [{"ramo": {"$regex": f"^{re.escape(a)}$", "$options": "i"}} for a in aliases]
    docs = await db.prodotti.find(flt, {"_id": 0}).sort("nome", 1).to_list(1000)
    if con_polizze:
        usati = {(p or "").strip().lower() for p in await db.polizze.distinct("prodotto") if p}
        docs = [d for d in docs if (d.get("nome") or "").strip().lower() in usati]
    return docs


@router.post("/librerie/prodotti", status_code=201)
async def create_prodotto(body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    # Default termini_mora_giorni in base al ramo se non specificato
    if not body.get("termini_mora_giorni"):
        from db_models import default_mora_for_ramo
        body["termini_mora_giorni"] = default_mora_for_ramo(body.get("ramo"))
    obj = ProdottoLibreria(**body)
    await db.prodotti.insert_one(obj.model_dump())
    await log_attivita(user, "create", "prodotto", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/prodotti/{pid}")
async def update_prodotto(pid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    body["updated_at"] = _now_iso()
    res = await db.prodotti.update_one({"id": pid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    await log_attivita(user, "update", "prodotto", pid)
    return strip_mongo_id(await db.prodotti.find_one({"id": pid}, {"_id": 0}))


@router.delete("/librerie/prodotti/{pid}")
async def delete_prodotto(pid: str, user: dict = Depends(require_user("admin"))) -> dict:
    await db.prodotti.delete_one({"id": pid})
    await log_attivita(user, "delete", "prodotto", pid)
    return {"ok": True}


@router.post("/librerie/prodotti/bulk-rename")
async def bulk_rename_prodotti(
    body: dict, user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Rinomina in massa più prodotti in un'unica chiamata.

    Body: {"items": [{"id": "...", "nome": "Nuovo Nome"}, ...]}
    Ritorna: {"rinominati": N, "saltati": M, "conflitti": [...]}
    """
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "items richiesto: lista di {id, nome}")
    rinominati, saltati, conflitti = 0, 0, []
    now = _now_iso()
    for it in items:
        pid = (it.get("id") or "").strip()
        nuovo_nome = (it.get("nome") or "").strip()
        if not pid or not nuovo_nome:
            saltati += 1
            continue
        current = await db.prodotti.find_one({"id": pid}, {"_id": 0, "nome": 1})
        if not current:
            saltati += 1
            continue
        if current.get("nome") == nuovo_nome:
            saltati += 1
            continue
        # Verifica conflitto: esiste già un prodotto (diverso) con lo stesso nome?
        existing = await db.prodotti.find_one(
            {"nome": nuovo_nome, "id": {"$ne": pid}}, {"_id": 0, "id": 1, "nome": 1},
        )
        if existing:
            conflitti.append({"id": pid, "nome_nuovo": nuovo_nome, "gia_esiste_id": existing["id"]})
            saltati += 1
            continue
        await db.prodotti.update_one(
            {"id": pid},
            {"$set": {"nome": nuovo_nome, "updated_at": now}},
        )
        rinominati += 1
    await log_attivita(user, "bulk_rename", "prodotti", None,
                       f"Rinominati {rinominati} prodotti", payload={"conflitti": conflitti})
    return {"rinominati": rinominati, "saltati": saltati, "conflitti": conflitti}


# --- TIPOLOGIE SINISTRI ---
@router.get("/librerie/tipologie-sinistri")
async def list_tipologie_sinistri(user: dict = Depends(current_user)) -> list[dict]:
    return await db.tipologie_sinistri.find({}, {"_id": 0}).sort("nome", 1).to_list(500)


@router.post("/librerie/tipologie-sinistri", status_code=201)
async def create_tipologia_sinistro(
    body: dict, user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    nome = (body.get("nome") or "").strip()
    if not nome:
        raise HTTPException(400, "Nome obbligatorio")
    doc = {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "categoria": body.get("categoria") or "Generale",
        "descrizione": body.get("descrizione"),
        "richiede_cai": bool(body.get("richiede_cai")),  # se True, doc obbligatorio "CAI"
        "richiede_denuncia": bool(body.get("richiede_denuncia", True)),
        "attivo": body.get("attivo", True),
        "ordine": body.get("ordine", 100),
        "created_at": _now_iso(),
    }
    await db.tipologie_sinistri.insert_one(doc)
    doc.pop("_id", None)
    await log_attivita(user, "create", "tipologia_sinistro", doc["id"], nome)
    return doc


@router.put("/librerie/tipologie-sinistri/{tid}")
async def update_tipologia_sinistro(
    tid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    body["updated_at"] = _now_iso()
    res = await db.tipologie_sinistri.update_one({"id": tid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Tipologia non trovata")
    return strip_mongo_id(await db.tipologie_sinistri.find_one({"id": tid}, {"_id": 0}))


@router.delete("/librerie/tipologie-sinistri/{tid}")
async def delete_tipologia_sinistro(tid: str, user: dict = Depends(require_user("admin"))) -> dict:
    await db.tipologie_sinistri.delete_one({"id": tid})
    return {"ok": True}


async def seed_default_tipologie_sinistri() -> None:
    """Crea tipologie sinistri standard se non esistono (idempotente)."""
    if await db.tipologie_sinistri.count_documents({}) > 0:
        return
    defaults = [
        ("RC AUTO - Collisione tra veicoli", "Auto", True, True),
        ("RC AUTO - Investimento pedone", "Auto", False, True),
        ("RC AUTO - Urto contro ostacolo fisso", "Auto", False, True),
        ("ARD AUTO - Furto totale", "Auto", False, True),
        ("ARD AUTO - Furto parziale", "Auto", False, True),
        ("ARD AUTO - Incendio", "Auto", False, True),
        ("ARD AUTO - Atti vandalici", "Auto", False, True),
        ("ARD AUTO - Eventi atmosferici (grandine)", "Auto", False, True),
        ("ARD AUTO - Kasko / Collisione", "Auto", False, True),
        ("ARD AUTO - Cristalli", "Auto", False, True),
        ("INFORTUNI - Conducente", "Persona", False, True),
        ("INFORTUNI - Lavoro", "Persona", False, True),
        ("INFORTUNI - Extraprofessionali", "Persona", False, True),
        ("MALATTIE - Ricovero", "Persona", False, True),
        ("MALATTIE - Day Hospital", "Persona", False, True),
        ("MALATTIE - Visite specialistiche", "Persona", False, True),
        ("VITA - Decesso", "Vita", False, True),
        ("VITA - Invalidità permanente", "Vita", False, True),
        ("CASA - Furto contenuto", "Casa", False, True),
        ("CASA - Furto fabbricato", "Casa", False, True),
        ("CASA - Incendio", "Casa", False, True),
        ("CASA - Danni d'acqua", "Casa", False, True),
        ("CASA - Eventi atmosferici", "Casa", False, True),
        ("CASA - Eventi catastrofali (terremoto)", "Casa", False, True),
        ("CASA - Eventi catastrofali (alluvione)", "Casa", False, True),
        ("CASA - Responsabilità civile", "Casa", False, True),
        ("AZIENDA - Incendio fabbricato/contenuto", "Azienda", False, True),
        ("AZIENDA - Furto", "Azienda", False, True),
        ("AZIENDA - Danni elettrici", "Azienda", False, True),
        ("AZIENDA - Eventi catastrofali", "Azienda", False, True),
        ("AZIENDA - RC verso terzi", "Azienda", False, True),
        ("AZIENDA - RC prodotti", "Azienda", False, True),
        ("AZIENDA - All Risks", "Azienda", False, True),
        ("TUTELA LEGALE - Penale", "Tutela", False, True),
        ("TUTELA LEGALE - Civile", "Tutela", False, True),
        ("VIAGGIO - Annullamento", "Viaggio", False, True),
        ("VIAGGIO - Bagaglio", "Viaggio", False, True),
        ("VIAGGIO - Spese mediche", "Viaggio", False, True),
        ("ALTRO", "Generale", False, True),
    ]
    docs = []
    for i, (nome, cat, cai, denuncia) in enumerate(defaults):
        docs.append({
            "id": str(uuid.uuid4()), "nome": nome, "categoria": cat,
            "richiede_cai": cai, "richiede_denuncia": denuncia,
            "attivo": True, "ordine": i * 10, "created_at": _now_iso(),
        })
    await db.tipologie_sinistri.insert_many(docs)





# --- RAMI ---
@router.get("/librerie/rami")
async def list_rami(dedup: bool = False, con_polizze: bool = False, user: dict = Depends(current_user)) -> list[dict]:
    """`dedup=1` (per le tendine): esclude archiviati e doppioni con stesso codice.
    `con_polizze=1` (filtri): mostra solo i rami effettivamente usati da almeno una polizza."""
    docs = await db.rami.find({}, {"_id": 0}).sort("nome", 1).to_list(300)
    docs = [d for d in docs if not d.get("unito_in_ramo_id")]
    if dedup:
        visti: set[str] = set()
        out = []
        for d in docs:
            if d.get("attivo") is False:
                continue
            k = (d.get("codice") or "").strip().upper()
            if k in visti:
                continue
            visti.add(k)
            out.append(d)
        docs = out
    if con_polizze:
        usati = {(r or "").strip().lower() for r in await db.polizze.distinct("ramo") if r}
        docs = [d for d in docs if (d.get("nome") or "").strip().lower() in usati]
    return docs


@router.post("/librerie/rami", status_code=201)
async def create_ramo(body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    obj = RamoLibreria(**body)
    await db.rami.insert_one(obj.model_dump())
    await log_attivita(user, "create", "ramo", obj.id, obj.nome)
    return obj.model_dump()


@router.put("/librerie/rami/{rid}")
async def update_ramo(rid: str, body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    body["updated_at"] = _now_iso()
    res = await db.rami.update_one({"id": rid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Ramo non trovato")
    return strip_mongo_id(await db.rami.find_one({"id": rid}, {"_id": 0}))


@router.delete("/librerie/rami/{rid}")
async def delete_ramo(rid: str, user: dict = Depends(require_user("admin"))) -> dict:
    await db.rami.delete_one({"id": rid})
    return {"ok": True}


@router.get("/librerie/rami/codici-usati")
async def rami_codici_usati(user: dict = Depends(current_user)) -> list[dict]:
    """Codici ramo realmente presenti nelle polizze (es. codici OMNIA 3N, 45, 60)
    con conteggi e flag `in_libreria`: servono per mapparli al ramo corretto."""
    rami = await db.rami.find({}, {"_id": 0, "codice": 1, "nome": 1, "attivo": 1, "unito_in_ramo_id": 1}).to_list(500)
    noti = {(r.get("codice") or "").strip().upper() for r in rami
            if r.get("attivo") is not False and not r.get("unito_in_ramo_id")}
    out: list[dict] = []
    async for g in db.polizze.aggregate([
        {"$group": {"_id": "$ramo", "polizze": {"$sum": 1}}},
        {"$sort": {"polizze": -1}},
    ]):
        cod = (g["_id"] or "").strip()
        if not cod:
            continue
        out.append({
            "codice": cod,
            "polizze": g["polizze"],
            "in_libreria": cod.upper() in noti,
        })
    return out


class RiassegnaCodiciBody(BaseModel):
    codici: list[str]
    master_id: str


@router.post("/librerie/rami/riassegna-codici")
async def rami_riassegna_codici(body: RiassegnaCodiciBody,
                                user: dict = Depends(require_user("admin"))) -> dict:
    """Riassegna al ramo master i codici ramo grezzi usati in polizze/sinistri/prodotti."""
    codici = [c.strip() for c in body.codici if c and c.strip()]
    if not codici:
        raise HTTPException(400, "Nessun codice selezionato")
    master = await db.rami.find_one({"id": body.master_id}, {"_id": 0})
    if not master:
        raise HTTPException(404, "Ramo master non trovato")
    master_codice = (master.get("codice") or "").strip()
    if not master_codice:
        raise HTTPException(400, "Il ramo master non ha un codice valido")
    flt = {"ramo": {"$in": codici}}
    upd = {"$set": {"ramo": master_codice, "updated_at": _now_iso()}}
    tot = {
        "polizze": (await db.polizze.update_many(flt, upd)).modified_count,
        "sinistri": (await db.sinistri.update_many(flt, upd)).modified_count,
        "prodotti": (await db.prodotti.update_many(flt, upd)).modified_count,
    }
    await log_attivita(user, "merge", "ramo", master["id"],
                       f"{', '.join(codici)} → {master.get('nome')}")
    return {"ok": True, "master": master_codice, "codici": codici, "riferimenti_spostati": tot}


# --- RAMI: unione doppioni -------------------------------------------------
def _ramo_valori(r: dict) -> list[str]:
    """Valori testuali con cui un ramo può essere referenziato in polizze/sinistri."""
    vals = {(r.get("codice") or "").strip(), (r.get("nome") or "").strip()}
    return [v for v in vals if v]


async def _conta_riferimenti_ramo(valori: list[str]) -> dict:
    flt = {"$in": valori}
    return {
        "polizze": await db.polizze.count_documents({"ramo": flt}),
        "sinistri": await db.sinistri.count_documents({"ramo": flt}),
        "prodotti": await db.prodotti.count_documents({"ramo": flt}),
    }


async def _carica_master_e_doppioni(body: dict) -> tuple[dict, list[dict]]:
    master_id = body.get("master_id")
    dup_ids = [d for d in (body.get("duplicati_ids") or []) if d and d != master_id]
    if not master_id or not dup_ids:
        raise HTTPException(400, "Seleziona un ramo master e almeno un doppione")
    master = await db.rami.find_one({"id": master_id}, {"_id": 0})
    if not master:
        raise HTTPException(404, "Ramo master non trovato")
    dups = await db.rami.find({"id": {"$in": dup_ids}}, {"_id": 0}).to_list(100)
    if len(dups) != len(dup_ids):
        raise HTTPException(404, "Uno o più doppioni non trovati")
    return master, dups


@router.post("/librerie/rami/merge-preview")
async def merge_rami_preview(body: dict, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    """Anteprima: quanti riferimenti verranno spostati sul ramo master."""
    master, dups = await _carica_master_e_doppioni(body)
    dettaglio = []
    valori_tutti: set[str] = set()
    for d in dups:
        valori = _ramo_valori(d)
        valori_tutti.update(valori)
        cnt = await _conta_riferimenti_ramo(valori)
        dettaglio.append({"id": d["id"], "codice": d.get("codice"), "nome": d.get("nome"), **cnt})
    # totale su unione dei valori: evita doppi conteggi tra doppioni con stesso codice
    tot = await _conta_riferimenti_ramo(sorted(valori_tutti))
    return {
        "master": {"id": master["id"], "codice": master.get("codice"), "nome": master.get("nome")},
        "doppioni": dettaglio,
        "totali": tot,
    }


@router.post("/librerie/rami/merge")
async def merge_rami(body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    """Riassegna i riferimenti dei doppioni al ramo master e li archivia."""
    master, dups = await _carica_master_e_doppioni(body)
    master_codice = (master.get("codice") or "").strip()
    if not master_codice:
        raise HTTPException(400, "Il ramo master non ha un codice valido")

    tot = {"polizze": 0, "sinistri": 0, "prodotti": 0}
    for d in dups:
        valori = _ramo_valori(d)
        flt = {"ramo": {"$in": valori}}
        upd = {"$set": {"ramo": master_codice, "updated_at": _now_iso()}}
        tot["polizze"] += (await db.polizze.update_many(flt, upd)).modified_count
        tot["sinistri"] += (await db.sinistri.update_many(flt, upd)).modified_count
        tot["prodotti"] += (await db.prodotti.update_many(flt, upd)).modified_count
        await db.rami.update_one({"id": d["id"]}, {"$set": {
            "attivo": False,
            "unito_in_ramo_id": master["id"],
            "unito_in_codice": master_codice,
            "unito_at": _now_iso(),
            "updated_at": _now_iso(),
        }})
        await log_attivita(user, "merge", "ramo", d["id"], f"{d.get('nome')} → {master.get('nome')}")

    return {"ok": True, "master": master_codice, "archiviati": len(dups), "riferimenti_spostati": tot}


# ============================================================
# LIBRERIE — AZIENDA (DATI INTESTAZIONE / STAMPE)
# ============================================================
@router.get("/librerie/azienda")
async def get_azienda(user: dict = Depends(current_user)) -> dict:
    """Singleton: dati dell'agenzia (usati nelle stampe)."""
    doc = await db.azienda_config.find_one({}, {"_id": 0})
    if not doc:
        # crea record vuoto al primo accesso (solo se admin)
        cfg = AziendaConfig()
        await db.azienda_config.insert_one(cfg.model_dump())
        doc = cfg.model_dump()
    if not is_super_admin(user):
        for k in _SEGRETI_AZIENDA:
            doc.pop(k, None)
    return doc


@router.put("/librerie/azienda")
async def update_azienda(body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    body.pop("id", None)
    if not is_super_admin(user):
        for k in _SEGRETI_AZIENDA:
            body.pop(k, None)
    body["updated_at"] = _now_iso()
    existing = await db.azienda_config.find_one({})
    if not existing:
        cfg = AziendaConfig(**body)
        await db.azienda_config.insert_one(cfg.model_dump())
    else:
        await db.azienda_config.update_one({"id": existing["id"]}, {"$set": body})
    await log_attivita(user, "update", "azienda", existing["id"] if existing else None,
                       "Aggiornamento dati azienda")
    return await db.azienda_config.find_one({}, {"_id": 0})


@router.post("/librerie/azienda/logo")
async def upload_logo_azienda(file: UploadFile = File(...),
                               user: dict = Depends(require_user("admin"))) -> dict:
    """Carica/sostituisce il logo dell'agenzia (usato in tutte le stampe PDF)."""
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Logo troppo grande (max 5 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    if not ct.startswith("image/"):
        raise HTTPException(400, "Il logo deve essere un'immagine (PNG/JPG/SVG)")
    ext = (file.filename or "logo.png").rsplit(".", 1)[-1].lower() or "png"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/azienda/logo_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, ct)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    url = f"/api/storage/{result['path']}"
    existing = await db.azienda_config.find_one({})
    set_fields = {"logo_url": url, "logo_storage_path": result["path"], "updated_at": _now_iso()}
    if not existing:
        cfg = AziendaConfig(**set_fields)
        await db.azienda_config.insert_one(cfg.model_dump())
    else:
        await db.azienda_config.update_one({"id": existing["id"]}, {"$set": set_fields})
    return {"logo_url": url}


@router.post("/librerie/azienda/privacy-modello")
async def upload_privacy_modello(file: UploadFile = File(...),
                                 user: dict = Depends(require_user("admin"))) -> dict:
    """Carica il MODELLO privacy dell'agenzia (PDF o Word) usato come base."""
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 15 MB)")
    fname = file.filename or "privacy.pdf"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "pdf"
    if ext not in ("pdf", "doc", "docx"):
        raise HTTPException(400, "Formato non valido: usa PDF o Word (.doc/.docx)")
    ct = file.content_type or obj_storage.mime_for(fname)
    path = f"{os.environ.get('APP_NAME', 'assicura')}/azienda/privacy_modello_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, ct)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    existing = await db.azienda_config.find_one({})
    set_fields = {"privacy_modello": {"storage_path": result["path"], "nome_file": fname,
                                      "content_type": ct, "ext": ext, "caricato_il": _now_iso()},
                  "updated_at": _now_iso()}
    if not existing:
        await db.azienda_config.insert_one(AziendaConfig(**set_fields).model_dump())
    else:
        await db.azienda_config.update_one({"id": existing["id"]}, {"$set": set_fields})
    return {"ok": True, "nome_file": fname, "ext": ext}


@router.get("/librerie/azienda/privacy-modello")
async def download_privacy_modello(user: dict = Depends(current_user)):
    """Scarica il modello privacy dell'agenzia, se caricato."""
    az = await db.azienda_config.find_one({}, {"_id": 0, "privacy_modello": 1}) or {}
    pm = az.get("privacy_modello")
    if not pm or not pm.get("storage_path"):
        raise HTTPException(404, "Nessun modello privacy caricato")
    try:
        data, ct = obj_storage.get_object(pm["storage_path"])
    except Exception:
        raise HTTPException(404, "File modello non trovato")
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    disp = "inline" if pm.get("ext") == "pdf" else "attachment"
    return StreamingResponse(BytesIO(data), media_type=pm.get("content_type") or ct,
                             headers={"Content-Disposition": f'{disp}; filename="{pm.get("nome_file", "privacy")}"'})


@router.post("/librerie/azienda/video-analisi")
async def upload_video_analisi(file: UploadFile = File(...),
                                user: dict = Depends(require_user("admin"))) -> dict:
    """Carica il video motivazionale mostrato nella CTA 'Analisi Personalizzata' del portale cliente."""
    data = await file.read()
    if len(data) > 80 * 1024 * 1024:
        raise HTTPException(400, "Video troppo grande (max 80 MB)")
    ct = file.content_type or obj_storage.mime_for(file.filename or "")
    if not (ct or "").startswith("video/"):
        raise HTTPException(400, "Il file deve essere un video (MP4/WebM)")
    ext = (file.filename or "video.mp4").rsplit(".", 1)[-1].lower() or "mp4"
    path = f"{os.environ.get('APP_NAME', 'assicura')}/azienda/video_analisi_{_uid()}.{ext}"
    try:
        result = obj_storage.put_object(path, data, ct)
    except Exception as e:
        raise HTTPException(503, f"Errore upload: {e}")
    existing = await db.azienda_config.find_one({})
    set_fields = {"video_analisi_storage_path": result["path"],
                  "video_analisi_filename": file.filename,
                  "updated_at": _now_iso()}
    if not existing:
        cfg = AziendaConfig(**set_fields)
        await db.azienda_config.insert_one(cfg.model_dump())
    else:
        await db.azienda_config.update_one({"id": existing["id"]}, {"$set": set_fields})
    return {"ok": True, "filename": file.filename}


@router.delete("/librerie/azienda/video-analisi")
async def delete_video_analisi(user: dict = Depends(require_user("admin"))) -> dict:
    """Rimuove il video motivazionale (file caricato e/o URL esterno)."""
    existing = await db.azienda_config.find_one({})
    if existing:
        await db.azienda_config.update_one(
            {"id": existing["id"]},
            {"$set": {"video_analisi_storage_path": None,
                      "video_analisi_filename": None,
                      "video_analisi_url": None,
                      "updated_at": _now_iso()}},
        )
    return {"ok": True}


# ============================================================
# LIBRERIE — SCHEMA PROVVIGIONALE
# ============================================================
@router.get("/librerie/schema-provvigionale")
async def list_schemi_provvigionali(
    collaboratore_id: Optional[str] = None,
    compagnia_id: Optional[str] = None,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> list[dict]:
    """Elenco regole provvigionali, opzionalmente filtrate per collaboratore o compagnia."""
    q = {}
    if collaboratore_id:
        q["collaboratore_id"] = collaboratore_id
    if compagnia_id:
        q["compagnia_id"] = compagnia_id
    items = await db.schema_provvigionale.find(q, {"_id": 0}).sort("nome", 1).to_list(500)
    # arricchisci con nomi
    for it in items:
        if it.get("collaboratore_id"):
            u = await db.users.find_one({"id": it["collaboratore_id"]}, {"_id": 0, "name": 1})
            it["collaboratore_nome"] = u.get("name") if u else None
        if it.get("compagnia_id"):
            c = await db.compagnie.find_one({"id": it["compagnia_id"]}, {"_id": 0, "ragione_sociale": 1})
            it["compagnia_nome"] = c.get("ragione_sociale") if c else None
    return items


@router.post("/librerie/schema-provvigionale", status_code=201)
async def create_schema_provvigionale(body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    body = {k: (v if v != "" else None) for k, v in body.items()}
    obj = SchemaProvvigionale(**body)
    await db.schema_provvigionale.insert_one(obj.model_dump())
    await log_attivita(user, "create", "schema_provvigionale", obj.id, f"Schema '{obj.nome}'")
    return obj.model_dump()


@router.put("/librerie/schema-provvigionale/{sid}")
async def update_schema_provvigionale(sid: str, body: dict, user: dict = Depends(require_user("admin"))) -> dict:
    body = {k: (v if v != "" else None) for k, v in body.items()}
    body.pop("id", None)
    body["updated_at"] = _now_iso()
    res = await db.schema_provvigionale.update_one({"id": sid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Schema non trovato")
    await log_attivita(user, "update", "schema_provvigionale", sid)
    return await db.schema_provvigionale.find_one({"id": sid}, {"_id": 0})


@router.delete("/librerie/schema-provvigionale/{sid}")
async def delete_schema_provvigionale(sid: str, user: dict = Depends(require_user("admin"))) -> dict:
    res = await db.schema_provvigionale.delete_one({"id": sid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Schema non trovato")
    return {"ok": True}


# ============================================================
# RUBRICA CONTATTI COMPAGNIA
# ============================================================
@router.get("/contatti-compagnia")
async def list_contatti_compagnia(
    compagnia_id: Optional[str] = None,
    q: Optional[str] = None,
    attivo: Optional[bool] = None,
    user: dict = Depends(current_user),
) -> list[dict]:
    flt: dict = {}
    if compagnia_id:
        flt["compagnia_id"] = compagnia_id
    if attivo is not None:
        flt["attivo"] = attivo
    if q:
        qrx = {"$regex": q, "$options": "i"}
        flt["$or"] = [
            {"nome": qrx}, {"cognome": qrx}, {"ruolo": qrx},
            {"email": qrx}, {"telefono": qrx}, {"cellulare": qrx},
            {"ufficio": qrx},
        ]
    items = await db.contatti_compagnia.find(flt, {"_id": 0}).sort([("cognome", 1), ("nome", 1)]).to_list(2000)
    # arricchimento ragione sociale compagnia
    cmp_ids = list({c.get("compagnia_id") for c in items if c.get("compagnia_id")})
    cmps = {c["id"]: c async for c in db.compagnie.find(
        {"id": {"$in": cmp_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "codice": 1},
    )}
    for c in items:
        cm = cmps.get(c.get("compagnia_id"), {})
        c["compagnia_nome"] = cm.get("ragione_sociale")
        c["compagnia_codice"] = cm.get("codice")
    return items


@router.post("/contatti-compagnia", status_code=201)
async def create_contatto_compagnia(body: dict, user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))) -> dict:
    if not body.get("compagnia_id") or not body.get("nome"):
        raise HTTPException(400, "compagnia_id e nome obbligatori")
    obj = ContattoCompagnia(**body)
    await db.contatti_compagnia.insert_one(obj.model_dump())
    await log_attivita(user, "create", "contatto_compagnia", obj.id,
                       f"Contatto '{obj.nome} {obj.cognome or ''}'")
    return obj.model_dump()


@router.put("/contatti-compagnia/{cid}")
async def update_contatto_compagnia(
    cid: str, body: dict,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    body.pop("id", None)
    body["updated_at"] = _now_iso()
    res = await db.contatti_compagnia.update_one({"id": cid}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Contatto non trovato")
    await log_attivita(user, "update", "contatto_compagnia", cid)
    return await db.contatti_compagnia.find_one({"id": cid}, {"_id": 0})


@router.delete("/contatti-compagnia/{cid}")
async def delete_contatto_compagnia(cid: str, user: dict = Depends(require_user("admin", "collaboratore"))) -> dict:
    res = await db.contatti_compagnia.delete_one({"id": cid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Contatto non trovato")
    await log_attivita(user, "delete", "contatto_compagnia", cid)
    return {"ok": True}


async def risolvi_provvigione_collaboratore(
    collaboratore_id: str, compagnia_id: Optional[str], ramo: Optional[str],
) -> float:
    """Ritorna la % di provvigione spettante al collaboratore per la combinazione data.

    Cerca la regola più specifica (collaboratore+compagnia+ramo) e ricade su default agenzia / utente.
    """
    # 1) regole specifiche del collaboratore (ordine di specificità decrescente)
    candidati: list[dict] = [
        {"collaboratore_id": collaboratore_id, "compagnia_id": compagnia_id, "ramo": ramo},
        {"collaboratore_id": collaboratore_id, "compagnia_id": compagnia_id, "ramo": None},
        {"collaboratore_id": collaboratore_id, "compagnia_id": None, "ramo": ramo},
        {"collaboratore_id": collaboratore_id, "compagnia_id": None, "ramo": None},
        {"collaboratore_id": None, "compagnia_id": compagnia_id, "ramo": ramo},
        {"collaboratore_id": None, "compagnia_id": compagnia_id, "ramo": None},
        {"collaboratore_id": None, "compagnia_id": None, "ramo": ramo},
        {"collaboratore_id": None, "compagnia_id": None, "ramo": None},
    ]
    for q in candidati:
        # rimuovi chiavi None tranne quelle che vogliamo esplicitamente None
        q["attivo"] = True
        doc = await db.schema_provvigionale.find_one(q, {"_id": 0})
        if doc:
            return float(doc.get("percentuale_collaboratore") or 0.0)
    # fallback: percentuale di default sull'utente
    u: dict = await db.users.find_one({"id": collaboratore_id}, {"_id": 0, "perc_provvigione_default": 1}) or {}
    return float(u.get("perc_provvigione_default") or 0.0)


@router.get("/librerie/schema-provvigionale/risolvi")
async def api_risolvi_provvigione(
    collaboratore_id: str,
    compagnia_id: Optional[str] = None,
    ramo: Optional[str] = None,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
) -> dict:
    perc = await risolvi_provvigione_collaboratore(collaboratore_id, compagnia_id, ramo)
    return {"percentuale_collaboratore": perc}