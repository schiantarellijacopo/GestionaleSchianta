"""Comunicazioni di Copertura.

Ogni giorno l'agenzia invia alle rispettive **agenzie partner** una comunicazione
con i titoli incassati/coperti registrati in Prima Nota quel giorno, raggruppati
per Compagnia (mandato), per chiedere/confermare la copertura.

Flusso:
  1. GET /comunicazioni-copertura/genera?giorno=YYYY-MM-DD
     → raggruppa i titoli del giorno per compagnia + agenzia partner destinataria
  2. POST /comunicazioni-copertura/salva {giorno, gruppi, invia}
     → salva le comunicazioni (bozza); se invia=true le spedisce subito
  3. POST /comunicazioni-copertura/{id}/invia → spedisce una bozza
  4. GET /comunicazioni-copertura (storico) + /{id} + /{id}/pdf + /{id}/anteprima

I titoli inviati vengono marcati `copertura_comunicata` e non rientrano nelle
comunicazioni successive. Multi-tenant via wrapper `db`.
"""
from __future__ import annotations

import html
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pymongo import ReturnDocument

import storage as obj_storage
from auth import require_user
from database import db
from db_models import ComunicazioneCopertura, _now_iso
from shared import log_attivita

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comunicazioni-copertura", tags=["comunicazioni-copertura"])

_ROLES = ("admin", "collaboratore", "dipendente")

_MESI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
         "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
_GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]


def _fmt_data_lunga(giorno: str) -> str:
    try:
        import datetime
        d = datetime.date.fromisoformat(giorno[:10])
        return f"{_GIORNI[d.weekday()]} {d.day} {_MESI[d.month]} {d.year}"
    except Exception:
        return giorno or "—"


def _fmt_data_breve(giorno: Optional[str]) -> str:
    if not giorno:
        return "—"
    try:
        y, m, d = giorno[:10].split("-")
        return f"{d}-{m}-{y}"
    except Exception:
        return giorno


def _fmt_eur(v) -> str:
    try:
        return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


async def _azienda() -> dict:
    return await db.azienda_config.find_one({}, {"_id": 0}) or {}


def _partner_id_di_compagnia(com: dict) -> Optional[str]:
    if com.get("agenzia_partner_id"):
        return com["agenzia_partner_id"]
    ids = com.get("agenzie_partner_ids") or []
    return ids[0] if ids else None


async def _build_gruppi(giorno: str) -> list[dict]:
    """Costruisce i gruppi (compagnia → agenzia partner) per il giorno indicato.

    Titoli inclusi: incassati nel giorno (data_incasso) o coperti nel giorno
    (data_copertura), non ancora comunicati, stato != stornato.
    """
    flt = {
        "copertura_comunicata": {"$ne": True},
        "stato": {"$ne": "stornato"},
        "$or": [
            {"data_incasso": giorno, "stato": "incassato"},
            {"data_copertura": giorno, "titolo_coperto": True},
        ],
    }
    titoli = await db.titoli.find(flt, {"_id": 0}).to_list(5000)
    if not titoli:
        return []

    # Escludi titoli già presenti in una comunicazione esistente (bozza/errore/inviata),
    # per evitare doppioni: la gestione prosegue dallo Storico.
    gia_comunicati = await db.comunicazioni_copertura.distinct("titoli.titolo_id")
    if gia_comunicati:
        gset = set(gia_comunicati)
        titoli = [t for t in titoli if t["id"] not in gset]
    if not titoli:
        return []

    pol_ids = list({t.get("polizza_id") for t in titoli if t.get("polizza_id")})
    polizze = await db.polizze.find({"id": {"$in": pol_ids}}, {"_id": 0}).to_list(5000)
    pol_map = {p["id"]: p for p in polizze}

    com_ids = list({p.get("compagnia_id") for p in polizze if p.get("compagnia_id")})
    compagnie = await db.compagnie.find({"id": {"$in": com_ids}}, {"_id": 0}).to_list(2000)
    com_map = {c["id"]: c for c in compagnie}

    ana_ids = list({p.get("contraente_id") for p in polizze if p.get("contraente_id")})
    anag = await db.anagrafiche.find({"id": {"$in": ana_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1}).to_list(5000)
    ana_map = {a["id"]: a.get("ragione_sociale") for a in anag}

    user_ids = list({t.get("collaboratore_id") for t in titoli if t.get("collaboratore_id")}
                    | {p.get("collaboratore_id") for p in polizze if p.get("collaboratore_id")})
    users = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)
    user_map = {u["id"]: u.get("name") for u in users}

    partner_ids = list({_partner_id_di_compagnia(c) for c in compagnie if _partner_id_di_compagnia(c)})
    agenzie = await db.agenzie.find({"id": {"$in": partner_ids}}, {"_id": 0, "id": 1, "ragione_sociale": 1, "email": 1}).to_list(2000)
    age_map = {a["id"]: a for a in agenzie}

    az = await _azienda()
    nostra = az.get("ragione_sociale") or "Agenzia"

    gruppi: dict[str, dict] = {}
    for t in titoli:
        pol = pol_map.get(t.get("polizza_id"))
        if not pol:
            continue
        cid = pol.get("compagnia_id")
        if not cid:
            continue
        com = com_map.get(cid, {})
        if cid not in gruppi:
            partner_id = _partner_id_di_compagnia(com)
            partner = age_map.get(partner_id, {}) if partner_id else {}
            gruppi[cid] = {
                "compagnia_id": cid,
                "compagnia_nome": com.get("ragione_sociale") or "—",
                "mandato_label": f"{nostra} - {com.get('ragione_sociale') or '—'}",
                "agenzia_partner_id": partner_id,
                "agenzia_partner_nome": partner.get("ragione_sociale"),
                "destinatario_email": partner.get("email"),
                "mezzo": "Email" if partner.get("email") else "",
                "titoli": [],
                "totale": 0.0,
            }
        operatore = (t.get("collaboratore_nome")
                     or user_map.get(t.get("collaboratore_id"))
                     or user_map.get(pol.get("collaboratore_id")) or "")
        importo = float(t.get("importo_lordo") or 0)
        gruppi[cid]["titoli"].append({
            "titolo_id": t["id"],
            "numero_polizza": pol.get("numero_polizza"),
            "rischio": pol.get("prodotto") or pol.get("ramo") or "",
            "operatore": operatore,
            "contraente": ana_map.get(pol.get("contraente_id")) or "",
            "rata_del": t.get("scadenza") or t.get("effetto"),
            "importo": importo,
        })
        gruppi[cid]["totale"] += importo

    out = sorted(gruppi.values(), key=lambda g: g["compagnia_nome"])
    for g in out:
        g["totale"] = round(g["totale"], 2)
    return out


def _html_comunicazione(com: dict, az: dict) -> str:
    def esc(v):
        return html.escape(str(v if v is not None else ""))
    righe = ""
    for r in com.get("titoli", []):
        righe += (
            f"<tr>"
            f"<td style='padding:4px 8px;border:1px solid #e2e8f0'>{esc(r.get('numero_polizza') or '—')}</td>"
            f"<td style='padding:4px 8px;border:1px solid #e2e8f0'>{esc(r.get('rischio'))}</td>"
            f"<td style='padding:4px 8px;border:1px solid #e2e8f0'>{esc(r.get('operatore'))}</td>"
            f"<td style='padding:4px 8px;border:1px solid #e2e8f0'>{esc(r.get('contraente'))}</td>"
            f"<td style='padding:4px 8px;border:1px solid #e2e8f0'>{esc(_fmt_data_breve(r.get('rata_del')))}</td>"
            f"<td style='padding:4px 8px;border:1px solid #e2e8f0;text-align:right'>€ {_fmt_eur(r.get('importo'))}</td>"
            f"</tr>"
        )
    nostra = esc(az.get("ragione_sociale") or "Agenzia")
    return f"""<!doctype html><html><body style="font-family:Arial,Helvetica,sans-serif;color:#0f172a;font-size:13px">
<p><b>{nostra}</b></p>
<p>Comunicazione N. {esc(com.get('numero'))} — <b>COMUNICAZIONE DI INCASSO</b></p>
<p>Spett.le <b>{esc(com.get('agenzia_partner_nome') or com.get('compagnia_nome'))}</b><br/>
Mandato: {esc(com.get('mandato_label'))}<br/>
Data: {esc(_fmt_data_lunga(com.get('giorno')))}</p>
<p>Con la presente si comunicano i seguenti titoli incassati, per i quali si richiede/conferma la copertura:</p>
<table style="border-collapse:collapse;width:100%;font-size:12px">
<thead><tr style="background:#0f172a;color:#fff">
<th style="padding:6px 8px;text-align:left">N. Contratto</th>
<th style="padding:6px 8px;text-align:left">Rischio</th>
<th style="padding:6px 8px;text-align:left">Operatore</th>
<th style="padding:6px 8px;text-align:left">Contraente</th>
<th style="padding:6px 8px;text-align:left">Rata del</th>
<th style="padding:6px 8px;text-align:right">Rata</th>
</tr></thead>
<tbody>{righe}</tbody>
<tfoot><tr style="background:#f1f5f9;font-weight:bold">
<td colspan="5" style="padding:6px 8px;text-align:right;border:1px solid #e2e8f0">TOTALE</td>
<td style="padding:6px 8px;text-align:right;border:1px solid #e2e8f0">€ {_fmt_eur(com.get('totale'))}</td>
</tr></tfoot>
</table>
<p>Sulla base degli accordi previsti, vogliate ritenere i premi delle polizze sopra elencate
regolarmente incassati e garantire la relativa copertura.</p>
<p>Cordiali saluti,<br/><b>{nostra}</b></p>
</body></html>"""


async def _pdf_comunicazione(com: dict) -> bytes:
    import pdf_report
    from shared import intestazione_pdf
    inte = await intestazione_pdf()
    headers = ["N. Contratto", "Rischio", "Operatore", "Contraente", "Rata del", "Rata €"]
    rows = []
    for r in com.get("titoli", []):
        rows.append([
            r.get("numero_polizza") or "—",
            r.get("rischio") or "",
            r.get("operatore") or "",
            r.get("contraente") or "",
            _fmt_data_breve(r.get("rata_del")),
            _fmt_eur(r.get("importo")),
        ])
    rows.append(["", "", "", "", "TOTALE", _fmt_eur(com.get("totale"))])
    sotto = f"{com.get('mandato_label')} — {_fmt_data_lunga(com.get('giorno'))}"
    if com.get("inviata_at"):
        sotto += f" — Inviata il {_fmt_data_breve(com['inviata_at'][:10])}"
    return pdf_report.stampa_elenco(
        titolo=f"Comunicazione di Copertura N. {com.get('numero')}",
        sottotitolo=sotto,
        headers=headers,
        rows=rows,
        landscape_mode=True,
        **inte,
    )


async def _next_numero() -> int:
    doc = await db.counters.find_one_and_update(
        {"_key": "comunicazioni_copertura"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


async def _invia_doc(doc: dict, user: dict) -> dict:
    """Invia la comunicazione: email HTML all'agenzia partner, genera PDF, marca titoli."""
    az = await _azienda()
    email = (doc.get("destinatario_email") or "").strip()
    now = _now_iso()

    if not email:
        await db.comunicazioni_copertura.update_one(
            {"id": doc["id"]},
            {"$set": {"stato": "errore", "email_errore": "Nessuna email agenzia partner", "updated_at": now}},
        )
        doc.update(stato="errore", email_errore="Nessuna email agenzia partner")
        return doc

    if not (az.get("smtp_host") and az.get("smtp_user")):
        await db.comunicazioni_copertura.update_one(
            {"id": doc["id"]},
            {"$set": {"stato": "errore", "email_errore": "SMTP non configurato", "updated_at": now}},
        )
        doc.update(stato="errore", email_errore="SMTP non configurato")
        return doc

    body_html = _html_comunicazione(doc, az)
    text = f"Comunicazione di incasso N. {doc.get('numero')} - {doc.get('mandato_label')}. Totale € {_fmt_eur(doc.get('totale'))}."
    try:
        import email_utils
        email_utils.smtp_send(
            az, to_addrs=email,
            subject=f"Comunicazione di copertura N. {doc.get('numero')} - {doc.get('compagnia_nome')} - {_fmt_data_breve(doc.get('giorno'))}",
            text=text, html=body_html,
        )
    except Exception as e:
        await db.comunicazioni_copertura.update_one(
            {"id": doc["id"]},
            {"$set": {"stato": "errore", "email_errore": str(e), "updated_at": now}},
        )
        doc.update(stato="errore", email_errore=str(e))
        return doc

    # Email inviata → genera e archivia PDF con la data di invio
    doc["inviata_at"] = now
    pdf_url = None
    pdf_path = None
    try:
        pdf_bytes = await _pdf_comunicazione(doc)
        pdf_path = f"{os.environ.get('APP_NAME', 'assicura')}/comunicazioni_copertura/{doc['id']}.pdf"
        res = obj_storage.put_object(pdf_path, pdf_bytes, "application/pdf")
        pdf_path = res["path"]
        pdf_url = f"/api/storage/{pdf_path}"
    except Exception as e:
        logger.warning("Errore generazione/archiviazione PDF comunicazione %s: %s", doc.get("id"), e)

    # Marca i titoli come copertura comunicata
    titolo_ids = [r["titolo_id"] for r in doc.get("titoli", [])]
    if titolo_ids:
        await db.titoli.update_many(
            {"id": {"$in": titolo_ids}},
            {"$set": {
                "copertura_comunicata": True,
                "copertura_comunicata_data": doc["giorno"],
                "comunicazione_copertura_id": doc["id"],
                "updated_at": now,
            }},
        )

    patch = {
        "stato": "inviata", "inviata_at": now, "inviata_a": email,
        "email_errore": None, "pdf_storage_path": pdf_path, "pdf_url": pdf_url,
        "updated_at": now,
    }
    await db.comunicazioni_copertura.update_one({"id": doc["id"]}, {"$set": patch})
    doc.update(patch)
    await log_attivita(user, "invia", "comunicazione_copertura", doc["id"],
                       f"N.{doc.get('numero')} → {email} ({len(titolo_ids)} titoli)")
    return doc


async def invia_coperture_giorno(giorno: str, user: dict) -> dict:
    """Servizio riutilizzabile (usato dallo scheduler automazioni): genera le
    comunicazioni di copertura del giorno per il tenant corrente e le INVIA
    subito alle agenzie partner. Idempotente: i titoli già comunicati vengono
    esclusi da `_build_gruppi`, quindi ri-eseguendolo non crea doppioni.
    Richiede che il `current_user` ContextVar sia già impostato sul tenant."""
    gruppi = await _build_gruppi(giorno)
    creati, inviati, errori = 0, 0, 0
    for src in gruppi:
        titoli = src.get("titoli") or []
        if not titoli:
            continue
        numero = await _next_numero()
        com = ComunicazioneCopertura(
            numero=numero,
            giorno=giorno,
            compagnia_id=src.get("compagnia_id"),
            compagnia_nome=src.get("compagnia_nome"),
            mandato_label=src.get("mandato_label"),
            agenzia_partner_id=src.get("agenzia_partner_id"),
            agenzia_partner_nome=src.get("agenzia_partner_nome"),
            destinatario_email=src.get("destinatario_email"),
            titoli=titoli,
            totale=round(sum(float(r.get("importo") or 0) for r in titoli), 2),
            stato="bozza",
            created_by=user.get("id"),
            created_by_name=user.get("name") or "Automazione",
        )
        doc = com.model_dump()
        await db.comunicazioni_copertura.insert_one(doc)
        doc.pop("_id", None)
        creati += 1
        doc = await _invia_doc(doc, user)
        if doc.get("stato") == "inviata":
            inviati += 1
        else:
            errori += 1
    return {"giorno": giorno, "gruppi": creati, "inviati": inviati, "errori": errori}


@router.post("/auto-invia-ora")
async def auto_invia_ora(body: dict | None = None, user=Depends(require_user("admin"))):
    """Esegue SUBITO l'invio automatico delle coperture del giorno (stessa logica
    dello scheduler), utile per test o invio manuale immediato."""
    giorno = (body or {}).get("giorno")
    if not giorno:
        import datetime
        giorno = datetime.date.today().isoformat()
    if not (len(giorno) == 10 and giorno[4] == "-" and giorno[7] == "-"):
        raise HTTPException(400, "Parametro 'giorno' non valido (YYYY-MM-DD)")
    res = await invia_coperture_giorno(giorno, user)
    await log_attivita(user, "auto-invia", "comunicazione_copertura", giorno,
                       f"Invio automatico: {res.get('inviati')} inviate, {res.get('errori')} errori")
    return {"ok": True, **res}


@router.get("/genera")
async def genera(giorno: str, user=Depends(require_user(*_ROLES))):
    if not (len(giorno) == 10 and giorno[4] == "-" and giorno[7] == "-"):
        raise HTTPException(400, "Parametro 'giorno' non valido (YYYY-MM-DD)")
    gruppi = await _build_gruppi(giorno)
    return {
        "giorno": giorno,
        "gruppi": gruppi,
        "totale_generale": round(sum(g["totale"] for g in gruppi), 2),
        "n_titoli": sum(len(g["titoli"]) for g in gruppi),
    }


@router.post("/salva")
async def salva(body: dict, user=Depends(require_user(*_ROLES))):
    giorno = body.get("giorno")
    gruppi_req = body.get("gruppi") or []
    invia = bool(body.get("invia"))
    if not giorno or not gruppi_req:
        raise HTTPException(400, "giorno e gruppi richiesti")

    # Ricostruisco i gruppi autorevoli dal DB (anti-tampering: importi, snapshot,
    # destinatari sono ricalcolati lato server; dal client prendo solo le selezioni).
    autorevoli = {g["compagnia_id"]: g for g in await _build_gruppi(giorno)}

    creati = []
    for gr in gruppi_req:
        cid = gr.get("compagnia_id")
        src = autorevoli.get(cid)
        if not src:
            continue
        sel_ids = {t.get("titolo_id") for t in (gr.get("titoli") or []) if t.get("titolo_id")}
        titoli = [t for t in src["titoli"] if t["titolo_id"] in sel_ids]
        if not titoli:
            continue
        numero = await _next_numero()
        com = ComunicazioneCopertura(
            numero=numero,
            giorno=giorno,
            compagnia_id=cid,
            compagnia_nome=src.get("compagnia_nome"),
            mandato_label=src.get("mandato_label"),
            agenzia_partner_id=src.get("agenzia_partner_id"),
            agenzia_partner_nome=src.get("agenzia_partner_nome"),
            destinatario_email=src.get("destinatario_email"),
            titoli=titoli,
            totale=round(sum(float(r.get("importo") or 0) for r in titoli), 2),
            stato="bozza",
            created_by=user.get("id"),
            created_by_name=user.get("name"),
        )
        doc = com.model_dump()
        await db.comunicazioni_copertura.insert_one(doc)
        doc.pop("_id", None)
        if invia:
            doc = await _invia_doc(doc, user)
        doc.pop("_id", None)
        creati.append(doc)

    if not creati:
        raise HTTPException(400, "Nessun titolo valido da comunicare per il giorno indicato")

    await log_attivita(user, "salva", "comunicazione_copertura", giorno,
                       f"{len(creati)} comunicazioni (invia={invia})")
    return {"ok": True, "comunicazioni": creati}


@router.get("")
async def storico(dal: Optional[str] = None, al: Optional[str] = None,
                  giorno: Optional[str] = None, stato: Optional[str] = None,
                  compagnia_id: Optional[str] = None, limit: int = 300,
                  user=Depends(require_user(*_ROLES))):
    flt: dict = {}
    if giorno:
        flt["giorno"] = giorno
    elif dal or al:
        rng: dict = {}
        if dal:
            rng["$gte"] = dal
        if al:
            rng["$lte"] = al
        flt["giorno"] = rng
    if stato:
        flt["stato"] = stato
    if compagnia_id:
        flt["compagnia_id"] = compagnia_id
    items = await db.comunicazioni_copertura.find(flt, {"_id": 0}).sort([("giorno", -1), ("numero", -1)]).to_list(limit)
    return items


@router.get("/{cid}")
async def dettaglio(cid: str, user=Depends(require_user(*_ROLES))):
    doc = await db.comunicazioni_copertura.find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Comunicazione non trovata")
    return doc


@router.get("/{cid}/anteprima")
async def anteprima(cid: str, user=Depends(require_user(*_ROLES))):
    doc = await db.comunicazioni_copertura.find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Comunicazione non trovata")
    az = await _azienda()
    return Response(content=_html_comunicazione(doc, az), media_type="text/html")


@router.get("/{cid}/pdf")
async def scarica_pdf(cid: str, user=Depends(require_user(*_ROLES))):
    doc = await db.comunicazioni_copertura.find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Comunicazione non trovata")
    pdf_bytes = await _pdf_comunicazione(doc)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="comunicazione_{doc.get("numero")}.pdf"'},
    )


@router.post("/{cid}/invia")
async def invia(cid: str, user=Depends(require_user(*_ROLES))):
    doc = await db.comunicazioni_copertura.find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Comunicazione non trovata")
    if doc.get("stato") == "inviata":
        raise HTTPException(400, "Comunicazione già inviata")
    doc = await _invia_doc(doc, user)
    if doc.get("stato") != "inviata":
        raise HTTPException(400, doc.get("email_errore") or "Invio non riuscito")
    return {"ok": True, "comunicazione": doc}


@router.delete("/{cid}")
async def elimina(cid: str, user=Depends(require_user("admin"))):
    doc = await db.comunicazioni_copertura.find_one({"id": cid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Comunicazione non trovata")
    if doc.get("stato") == "inviata":
        raise HTTPException(400, "Impossibile eliminare una comunicazione già inviata")
    await db.comunicazioni_copertura.delete_one({"id": cid})
    await log_attivita(user, "elimina", "comunicazione_copertura", cid, f"N.{doc.get('numero')}")
    return {"ok": True}
