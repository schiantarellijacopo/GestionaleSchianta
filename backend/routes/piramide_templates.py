"""Modelli Piramide — template globali (privati / aziende) modificabili dall'agenzia.

Le modifiche al modello si propagano a TUTTI i clienti:
- privati  → anagrafiche persona_fisica senza partita IVA
- aziende  → anagrafiche persona_giuridica o con partita IVA
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from auth import current_user, require_user
from database import db
from db_models import _now_iso

router = APIRouter(prefix="/piramide-templates")

DEFAULT_PRIVATI = {
    "tipo": "privati",
    "mostra_testamento": True,
    "levels": [
        {"id": "crescita", "modo": "input", "input_voce": "crescita_capitale",
         "titolo": "CRESCITA DEL CAPITALE"},
        {"id": "cassa_grandi", "modo": "input", "input_voce": "cassa_grandi",
         "titolo": "CASSA PER LE GRANDI ESIGENZE"},
        {"id": "cassa_lievi", "modo": "input", "input_voce": "cassa_lievi",
         "titolo": "CASSA PER LE LIEVI ESIGENZE"},
        {"id": "liquidita", "modo": "input", "input_voce": "liquidita_giornaliera",
         "titolo": "LIQUIDITÀ GIORNALIERA - CONTO CORRENTE -"},
        {"id": "perdita", "modo": "voci",
         "titolo": "PERDITA DEI BENI DOVUTA DA INCENDI/ EVENTI ATMOSFERICI/ ALLUVIONI/TERREMOTI:",
         "voci": [
             {"id": "perdita_beni_immobili", "label": "IMMOBILI, sei protetto fino a"},
             {"id": "perdita_beni_aziende", "label": "AZIENDE, sei protetto fino a"},
         ]},
        {"id": "danni", "modo": "voci",
         "titolo": "IN CASO DI DANNI PROVOCATI AD ALTRI, DOVUTI A:",
         "voci": [
             {"id": "danni_veicoli", "label": "VEICOLI, sei protetto fino a"},
             {"id": "danni_immobili", "label": "IMMOBILI, sei protetto fino a"},
             {"id": "danni_professioni", "label": "PROFESSIONI, sei protetto fino a"},
             {"id": "danni_vita_privata", "label": "VITA PRIVATA, sei protetto fino a"},
         ]},
        {"id": "premorienza", "modo": "voci",
         "titolo": "IN CASO DI PREMORIENZA DOVUTA A:",
         "voci": [
             {"id": "premorienza_malattia", "label": "MALATTIA, sei protetto fino a"},
             {"id": "premorienza_infortunio", "label": "INFORTUNIO, sei protetto fino a"},
         ]},
        {"id": "invalidita", "modo": "voci",
         "titolo": "IN CASO DI INVALIDITÀ DOVUTA A:",
         "voci": [
             {"id": "invalidita_malattia", "label": "MALATTIA, sei protetto fino a"},
             {"id": "invalidita_infortunio", "label": "INFORTUNIO, sei protetto fino a"},
             {"id": "invalidita_non_autosufficienza", "label": "NON AUTOSUFFICIENZA, sei protetto fino a"},
         ]},
    ],
    "wedges": [
        {"label": "INVESTIMENTO", "from": "crescita", "to": "crescita"},
        {"label": "RISPARMIO", "from": "cassa_grandi", "to": "liquidita"},
        {"label": "PROTEZIONE DEL PATRIMONIO", "from": "perdita", "to": "danni"},
        {"label": "PROTEZIONE DEL REDDITO", "from": "premorienza", "to": "invalidita"},
    ],
}

DEFAULT_AZIENDE = {
    "tipo": "aziende",
    "mostra_testamento": False,
    "levels": [
        {"id": "crescita", "modo": "input", "input_voce": "crescita_capitale",
         "titolo": "CRESCITA DEL PATRIMONIO AZIENDALE"},
        {"id": "cassa_grandi", "modo": "input", "input_voce": "cassa_grandi",
         "titolo": "CASSA PER LE GRANDI ESIGENZE"},
        {"id": "cassa_lievi", "modo": "input", "input_voce": "cassa_lievi",
         "titolo": "CASSA PER LE LIEVI ESIGENZE"},
        {"id": "liquidita", "modo": "input", "input_voce": "liquidita_giornaliera",
         "titolo": "LIQUIDITÀ AZIENDALE - CONTO CORRENTE -"},
        {"id": "perdita", "modo": "voci",
         "titolo": "PERDITA DEI BENI AZIENDALI DOVUTA DA INCENDI/ EVENTI ATMOSFERICI/ TERREMOTI:",
         "voci": [
             {"id": "az_perdita_fabbricati", "label": "FABBRICATI, sei protetto fino a"},
             {"id": "az_perdita_macchinari", "label": "MACCHINARI E ATTREZZATURE, fino a"},
             {"id": "az_perdita_merci", "label": "MERCI E SCORTE, fino a"},
         ]},
        {"id": "danni", "modo": "voci",
         "titolo": "RESPONSABILITÀ CIVILE VERSO TERZI:",
         "voci": [
             {"id": "az_rc_datoriale", "label": "RC DATORIALE (RCO), fino a"},
             {"id": "az_rc_prodotti", "label": "RC PRODOTTI, fino a"},
             {"id": "az_rc_ambientale", "label": "RC AMBIENTALE, fino a"},
             {"id": "az_rc_veicoli", "label": "VEICOLI AZIENDALI, fino a"},
         ]},
        {"id": "premorienza", "modo": "voci",
         "titolo": "TUTELA PERSONE CHIAVE (KEYMAN):",
         "voci": [
             {"id": "az_keyman_premorienza", "label": "PREMORIENZA UOMINI CHIAVE, fino a"},
             {"id": "az_keyman_soci", "label": "TUTELA SOCI / TITOLARE, fino a"},
         ]},
        {"id": "invalidita", "modo": "voci",
         "titolo": "CONTINUITÀ AZIENDALE:",
         "voci": [
             {"id": "az_invalidita_titolare", "label": "INVALIDITÀ TITOLARE/SOCI, fino a"},
             {"id": "az_infortuni_dipendenti", "label": "INFORTUNI DIPENDENTI, fino a"},
             {"id": "az_cyber_blocco", "label": "CYBER / BLOCCO ATTIVITÀ, fino a"},
         ]},
    ],
    "wedges": [
        {"label": "INVESTIMENTO", "from": "crescita", "to": "crescita"},
        {"label": "RISPARMIO", "from": "cassa_grandi", "to": "liquidita"},
        {"label": "PROTEZIONE DEL PATRIMONIO AZIENDALE", "from": "perdita", "to": "danni"},
        {"label": "CONTINUITÀ D'IMPRESA", "from": "premorienza", "to": "invalidita"},
    ],
}

DEFAULTS = {"privati": DEFAULT_PRIVATI, "aziende": DEFAULT_AZIENDE}


async def get_template(tipo: str) -> dict:
    base = DEFAULTS[tipo]
    stored = await db.piramide_templates.find_one({"tipo": tipo}, {"_id": 0})
    if not stored:
        return {**base}
    return {**base, **{k: stored[k] for k in ("mostra_testamento", "levels", "wedges") if k in stored},
            "tipo": tipo}


def tipo_for_anagrafica(ana: dict) -> str:
    if (ana or {}).get("tipo") == "persona_giuridica" or ((ana or {}).get("partita_iva") or "").strip():
        return "aziende"
    return "privati"


async def template_for_anagrafica(ana: dict) -> tuple[str, dict]:
    t = tipo_for_anagrafica(ana)
    return t, await get_template(t)


def _sanitize(tipo: str, body: dict) -> dict:
    """Mantiene la struttura (id/modo dei livelli fissi), accetta titoli/voci/wedge label."""
    base = DEFAULTS[tipo]
    by_id = {l["id"]: l for l in (body.get("levels") or []) if isinstance(l, dict)}
    levels = []
    for dl in base["levels"]:
        sub = by_id.get(dl["id"]) or {}
        lvl = {"id": dl["id"], "modo": dl["modo"],
               "titolo": (str(sub.get("titolo") or dl["titolo"])).strip()[:160] or dl["titolo"]}
        if dl["modo"] == "input":
            lvl["input_voce"] = dl["input_voce"]
        else:
            voci = []
            for v in (sub.get("voci") if isinstance(sub.get("voci"), list) else dl["voci"]):
                if not isinstance(v, dict):
                    continue
                label = str(v.get("label") or "").strip()[:90]
                vid = re.sub(r"[^\w]", "_", str(v.get("id") or ""))[:60]
                if label and vid:
                    voci.append({"id": vid, "label": label})
            lvl["voci"] = voci or dl["voci"]
        levels.append(lvl)
    wedges = []
    body_w = body.get("wedges") if isinstance(body.get("wedges"), list) else []
    for i, dw in enumerate(base["wedges"]):
        lbl = ""
        if i < len(body_w) and isinstance(body_w[i], dict):
            lbl = str(body_w[i].get("label") or "").strip()[:60]
        wedges.append({"label": lbl or dw["label"], "from": dw["from"], "to": dw["to"]})
    return {
        "tipo": tipo,
        "mostra_testamento": bool(body.get("mostra_testamento", base["mostra_testamento"])),
        "levels": levels,
        "wedges": wedges,
    }


@router.get("")
async def list_templates(user=Depends(current_user)):
    return {"privati": await get_template("privati"), "aziende": await get_template("aziende")}


@router.put("/{tipo}")
async def save_template(tipo: str, body: dict, user=Depends(require_user("admin", "collaboratore"))):
    if tipo not in DEFAULTS:
        raise HTTPException(400, "Tipo non valido (privati|aziende)")
    doc = _sanitize(tipo, body or {})
    doc["updated_at"] = _now_iso()
    doc["updated_by"] = user.get("name") or user.get("email")
    await db.piramide_templates.update_one({"tipo": tipo}, {"$set": doc}, upsert=True)
    return doc


@router.post("/{tipo}/reset")
async def reset_template(tipo: str, user=Depends(require_user("admin", "collaboratore"))):
    if tipo not in DEFAULTS:
        raise HTTPException(400, "Tipo non valido")
    await db.piramide_templates.delete_one({"tipo": tipo})
    return {**DEFAULTS[tipo]}
