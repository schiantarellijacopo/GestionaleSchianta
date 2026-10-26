"""Routes per la libreria "Gestioni Modelli".

Permette CRUD sui ``TemplateModello`` (testi/HTML editabili per Email,
WhatsApp, SMS e PDF). I modelli sono usati dai flussi di invio (avvisi
scadenze, sollecitazioni, lettera abbuono, ecc.) tramite il helper
``get_template_or_default``.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from auth import current_user, require_user
from database import db
from db_models import TemplateModello, _now_iso
from shared import log_attivita


router = APIRouter()


_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
# Segnaposto tabella: {tabella:slug}
_TABELLA_RE = re.compile(r"\{tabella:([a-zA-Z0-9_-]+)\}")


class ModelloBody(BaseModel):
    tipo: str
    nome: str
    oggetto: Optional[str] = None
    corpo: str = ""
    sezioni: list[dict] = []
    sezioni_visibili: list[str] = []
    template_riga: Optional[str] = None
    categoria: Optional[str] = None
    default: bool = False
    attivo: bool = True
    note: Optional[str] = None
    richiede_firma: bool = False
    logo_url: Optional[str] = None


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


import os as _os_seed
import json as _json_seed

_MODELLI_DEFAULT_DIR = _os_seed.path.join(_os_seed.path.dirname(_os_seed.path.dirname(__file__)), "assets", "modelli_default")


async def _seed_modelli_default() -> None:
    """Importa i modelli PDF predefiniti per sezione (idempotente per nome+categoria)."""
    if not _os_seed.path.isdir(_MODELLI_DEFAULT_DIR):
        return
    for fn in sorted(_os_seed.listdir(_MODELLI_DEFAULT_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(_os_seed.path.join(_MODELLI_DEFAULT_DIR, fn), encoding="utf-8") as fh:
                spec = _json_seed.load(fh)
        except Exception:
            continue
        exists = await db.template_modelli.find_one(
            {"nome": spec["nome"], "categoria": spec.get("categoria", "default_sezione")}, {"_id": 1},
        )
        if exists:
            continue
        body = ModelloBody(
            tipo=spec.get("tipo", "pdf_altro"), nome=spec["nome"], corpo=spec.get("corpo", ""),
            sezioni_visibili=spec.get("sezioni_visibili", []), categoria=spec.get("categoria", "default_sezione"),
            default=spec.get("default", False),
        )
        doc = TemplateModello(
            tipo=body.tipo, nome=body.nome, corpo=body.corpo, sezioni=body.sezioni,
            sezioni_visibili=body.sezioni_visibili, categoria=body.categoria, default=body.default,
            placeholders=_autodetect_placeholders(body),
        ).model_dump()
        await db.template_modelli.insert_one(doc)


@router.get("/librerie/modelli")
async def list_modelli(
    tipo: Optional[str] = None,
    categoria: Optional[str] = None,
    sezione: Optional[str] = None,
    user: dict = Depends(current_user),
) -> list[dict]:
    await _seed_modelli_default()
    flt: dict = {}
    if tipo:
        flt["tipo"] = tipo
    if categoria:
        flt["categoria"] = categoria
    if sezione:
        flt["sezioni_visibili"] = sezione
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
        sezioni_visibili=body.sezioni_visibili,
        categoria=body.categoria,
        default=body.default,
        attivo=body.attivo,
        note=body.note,
        richiede_firma=body.richiede_firma,
        logo_url=body.logo_url,
        placeholders=placeholders,
    ).model_dump()
    # Se default=True, sbianca altri default dello stesso tipo
    if body.default:
        await db.template_modelli.update_many(
            {"tipo": body.tipo, "default": True},
            {"$set": {"default": False}},
        )
    await db.template_modelli.insert_one(doc)
    doc.pop("_id", None)
    await log_attivita(user, "create", "modello", doc["id"], doc["nome"])
    return doc


# Catalogo segnaposto raggruppato per la sezione "Segnaposto" (Librerie).
# Ogni voce: (chiave, etichetta leggibile). I gruppi sono mostrati in ordine.
# Fonte unica di verità: popolata da build_context() con i dati reali di
# agenzia + anagrafica + polizza + titolo + sinistro + compagnia + collaboratore.
_PLACEHOLDER_CATALOGO = [
    ("Agenzia", [
        ("azienda_nome", "Ragione sociale agenzia"),
        ("azienda_forma_giuridica", "Forma giuridica"),
        ("azienda_partita_iva", "Partita IVA agenzia"),
        ("azienda_codice_fiscale", "Codice fiscale agenzia"),
        ("agenzia_rui", "N. iscrizione RUI agenzia"),
        ("agenzia_rui_sezione", "Sezione RUI agenzia"),
        ("agenzia_data_iscrizione_rui", "Data iscrizione RUI"),
        ("azienda_indirizzo", "Indirizzo agenzia"),
        ("azienda_comune", "Comune agenzia"),
        ("azienda_provincia", "Provincia agenzia"),
        ("azienda_cap", "CAP agenzia"),
        ("azienda_nazione", "Nazione agenzia"),
        ("azienda_telefono", "Telefono agenzia"),
        ("azienda_fax", "Fax agenzia"),
        ("azienda_email", "Email agenzia"),
        ("azienda_pec", "PEC agenzia"),
        ("azienda_sito_web", "Sito web agenzia"),
        ("azienda_iban", "IBAN agenzia"),
        ("azienda_banca", "Banca agenzia"),
        ("azienda_capitale_sociale", "Capitale sociale"),
        ("azienda_rea", "N. REA"),
        ("data_oggi", "Data di oggi"),
    ]),
    ("Anagrafica / Cliente / Contraente", [
        ("cliente", "Cliente (nome completo o ragione sociale)"),
        ("cliente_nome", "Nome"),
        ("cliente_cognome", "Cognome"),
        ("cliente_ragione_sociale", "Ragione sociale"),
        ("cliente_tipo", "Tipo (persona fisica/giuridica)"),
        ("cliente_indirizzo", "Indirizzo completo"),
        ("cliente_via", "Via/indirizzo"),
        ("cliente_comune", "Comune"),
        ("cliente_cap", "CAP"),
        ("cliente_provincia", "Provincia"),
        ("cliente_nazione", "Nazione"),
        ("cliente_cf", "Codice fiscale"),
        ("cliente_codice_fiscale", "Codice fiscale (alt.)"),
        ("cliente_partita_iva", "Partita IVA"),
        ("cliente_email", "Email"),
        ("cliente_pec", "PEC"),
        ("cliente_telefono", "Telefono"),
        ("cliente_cellulare", "Cellulare"),
        ("cliente_data_nascita", "Data di nascita"),
        ("cliente_luogo_nascita", "Luogo di nascita"),
        ("cliente_provincia_nascita", "Provincia di nascita"),
        ("cliente_sesso", "Sesso"),
        ("cliente_stato_civile", "Stato civile"),
        ("cliente_titolo_studio", "Titolo di studio"),
        ("cliente_professione", "Professione"),
        ("cliente_iban", "IBAN cliente"),
        ("cliente_amministratore", "Legale rappresentante / amministratore"),
    ]),
    ("Polizza", [
        ("numero_polizza", "Numero polizza"),
        ("ramo", "Ramo"),
        ("prodotto", "Prodotto"),
        ("stato_polizza", "Stato polizza"),
        ("frazionamento", "Frazionamento"),
        ("effetto", "Data effetto"),
        ("data_effetto", "Data effetto (alt.)"),
        ("scadenza", "Data scadenza"),
        ("data_scadenza", "Data scadenza (alt.)"),
        ("premio", "Premio (lordo)"),
        ("premio_lordo", "Premio lordo"),
        ("premio_netto", "Premio netto"),
        ("premio_imposte", "Imposte"),
        ("premio_tasse", "Tasse"),
        ("premio_ssn", "Contributo SSN"),
        ("premio_accessori", "Accessori"),
        ("provvigioni_polizza", "Provvigioni polizza"),
        ("importo", "Importo (premio lordo)"),
        ("mandato", "Mandato"),
        ("targa", "Targa veicolo"),
        ("veicolo_marca", "Veicolo - marca"),
        ("veicolo_modello", "Veicolo - modello"),
        ("veicolo_tipo", "Veicolo - tipo"),
        ("veicolo_immatricolazione", "Veicolo - immatricolazione"),
        ("massimali", "Massimali"),
        ("franchigia", "Franchigia"),
        ("capitale_assicurato", "Capitale assicurato"),
        ("oggetto_assicurato", "Oggetto assicurato"),
    ]),
    ("Titolo / Quietanza", [
        ("numero_titolo", "Numero titolo"),
        ("titolo_tipo", "Tipo titolo"),
        ("titolo_effetto", "Data effetto titolo"),
        ("titolo_scadenza", "Data scadenza titolo"),
        ("titolo_stato", "Stato titolo"),
        ("titolo_importo_lordo", "Importo lordo titolo"),
        ("titolo_importo_netto", "Importo netto titolo"),
        ("titolo_imposte", "Imposte titolo"),
        ("titolo_ssn", "SSN titolo"),
        ("titolo_accessori", "Accessori titolo"),
        ("titolo_provvigioni", "Provvigioni titolo"),
        ("titolo_descrizione", "Descrizione titolo"),
        ("titolo_data_incasso", "Data incasso"),
        ("titolo_importo_pagato", "Importo pagato"),
        ("titolo_sconto", "Sconto applicato"),
        ("titolo_mezzo_pagamento", "Mezzo di pagamento"),
    ]),
    ("Sinistro", [
        ("numero_sinistro", "Numero sinistro"),
        ("numero_sinistro_interno", "Numero sinistro interno"),
        ("data_sinistro", "Data sinistro (avvenimento)"),
        ("data_denuncia", "Data denuncia"),
        ("data_apertura_sinistro", "Data apertura"),
        ("anno_sinistro", "Anno sinistro"),
        ("tipologia_sinistro", "Tipologia sinistro"),
        ("luogo_sinistro", "Luogo sinistro"),
        ("ramo_sinistro", "Ramo sinistro"),
        ("stato_sinistro", "Stato sinistro"),
        ("descrizione_sinistro", "Descrizione sinistro"),
        ("riserva_sinistro", "Riserva"),
        ("liquidazione_sinistro", "Liquidazione"),
        ("data_liquidazione_sinistro", "Data liquidazione"),
    ]),
    ("Compagnia", [
        ("compagnia", "Compagnia (nome)"),
        ("compagnia_nome", "Compagnia (nome esteso)"),
        ("compagnia_codice", "Codice compagnia"),
        ("compagnia_email", "Email compagnia"),
        ("compagnia_telefono", "Telefono compagnia"),
        ("compagnia_sito_web", "Sito web compagnia"),
        ("compagnia_referente", "Referente compagnia"),
    ]),
    ("Collaboratore / Operatore", [
        ("operatore_nome", "Nome collaboratore"),
        ("operatore_email", "Email collaboratore"),
        ("operatore_telefono", "Telefono collaboratore"),
        ("operatore_codice_fiscale", "Codice fiscale collaboratore"),
        ("operatore_partita_iva", "Partita IVA collaboratore"),
        ("operatore_iban", "IBAN collaboratore"),
        ("operatore_rui", "N. RUI collaboratore"),
        ("operatore_sezione", "Sezione RUI collaboratore"),
    ]),
    ("Grafica e firma", [
        ("logo", "Logo dell'agenzia (immagine)"),
        ("firma_operatore", "Firma dell'operatore (immagine)"),
        ("firma", "DOVE firma il cliente (campo firma digitale)"),
        ("data_firma", "Data della firma del cliente"),
    ]),
]

# Elenco piatto di tutte le chiavi (derivato dal catalogo) — usato dall'AI e
# per azzerare i segnaposto non valorizzati in fase di stampa.
_PLACEHOLDER_DISPONIBILI = [k for _grp, _voci in _PLACEHOLDER_CATALOGO for k, _lbl in _voci]

# Valori d'esempio mostrati nell'interfaccia accanto a ogni segnaposto, così
# l'operatore capisce al volo cosa produrrà il segnaposto nel documento finale.
_PLACEHOLDER_ESEMPI = {
    # Agenzia
    "azienda_nome": "Rossi Assicurazioni S.r.l.",
    "azienda_forma_giuridica": "S.r.l.",
    "azienda_partita_iva": "01234567890",
    "azienda_codice_fiscale": "01234567890",
    "agenzia_rui": "A000123456",
    "agenzia_rui_sezione": "A",
    "agenzia_data_iscrizione_rui": "15/03/2007",
    "azienda_indirizzo": "Via Roma 12",
    "azienda_comune": "Milano",
    "azienda_provincia": "MI",
    "azienda_cap": "20121",
    "azienda_nazione": "Italia",
    "azienda_telefono": "02 1234567",
    "azienda_fax": "02 7654321",
    "azienda_email": "info@rossiassicurazioni.it",
    "azienda_pec": "rossiassicurazioni@pec.it",
    "azienda_sito_web": "www.rossiassicurazioni.it",
    "azienda_iban": "IT60X0542811101000000123456",
    "azienda_banca": "Intesa Sanpaolo",
    "azienda_capitale_sociale": "€ 10.000,00",
    "azienda_rea": "MI-1234567",
    "data_oggi": "26/10/2026",
    # Anagrafica
    "cliente": "Mario Rossi",
    "cliente_nome": "Mario",
    "cliente_cognome": "Rossi",
    "cliente_ragione_sociale": "Rossi S.r.l.",
    "cliente_tipo": "Persona fisica",
    "cliente_indirizzo": "Via Garibaldi 5, 20121 Milano (MI)",
    "cliente_via": "Via Garibaldi 5",
    "cliente_comune": "Milano",
    "cliente_cap": "20121",
    "cliente_provincia": "MI",
    "cliente_nazione": "Italia",
    "cliente_cf": "RSSMRA80A01F205X",
    "cliente_codice_fiscale": "RSSMRA80A01F205X",
    "cliente_partita_iva": "01234567890",
    "cliente_email": "mario.rossi@email.it",
    "cliente_pec": "mario.rossi@pec.it",
    "cliente_telefono": "02 9876543",
    "cliente_cellulare": "333 1234567",
    "cliente_data_nascita": "01/01/1980",
    "cliente_luogo_nascita": "Milano",
    "cliente_provincia_nascita": "MI",
    "cliente_sesso": "M",
    "cliente_stato_civile": "Coniugato",
    "cliente_titolo_studio": "Laurea",
    "cliente_professione": "Impiegato",
    "cliente_iban": "IT60X0542811101000000654321",
    "cliente_amministratore": "Mario Rossi",
    # Polizza
    "numero_polizza": "123456789",
    "ramo": "RC Auto",
    "prodotto": "Auto Protetta",
    "stato_polizza": "In vigore",
    "frazionamento": "Annuale",
    "effetto": "01/01/2026",
    "data_effetto": "01/01/2026",
    "scadenza": "31/12/2026",
    "data_scadenza": "31/12/2026",
    "premio": "€ 650,00",
    "premio_lordo": "€ 650,00",
    "premio_netto": "€ 520,00",
    "premio_imposte": "€ 130,00",
    "premio_tasse": "€ 130,00",
    "premio_ssn": "€ 10,50",
    "premio_accessori": "€ 15,00",
    "provvigioni_polizza": "€ 78,00",
    "importo": "€ 650,00",
    "mandato": "Mandato n. 4521",
    "targa": "AB123CD",
    "veicolo_marca": "Fiat",
    "veicolo_modello": "Panda",
    "veicolo_tipo": "Autovettura",
    "veicolo_immatricolazione": "03/2019",
    "massimali": "€ 6.450.000",
    "franchigia": "€ 250,00",
    "capitale_assicurato": "€ 150.000,00",
    "oggetto_assicurato": "Abitazione Via Garibaldi 5",
    # Titolo / Quietanza
    "numero_titolo": "T-2026-00123",
    "titolo_tipo": "Quietanza",
    "titolo_effetto": "01/01/2026",
    "titolo_scadenza": "31/12/2026",
    "titolo_stato": "Incassato",
    "titolo_importo_lordo": "€ 650,00",
    "titolo_importo_netto": "€ 520,00",
    "titolo_imposte": "€ 130,00",
    "titolo_ssn": "€ 10,50",
    "titolo_accessori": "€ 15,00",
    "titolo_provvigioni": "€ 78,00",
    "titolo_descrizione": "Quietanza annuale RC Auto",
    "titolo_data_incasso": "02/01/2026",
    "titolo_importo_pagato": "€ 650,00",
    "titolo_sconto": "€ 0,00",
    "titolo_mezzo_pagamento": "Bonifico bancario",
    # Sinistro
    "numero_sinistro": "SIN-2026-0456",
    "numero_sinistro_interno": "INT-0456",
    "data_sinistro": "10/05/2026",
    "data_denuncia": "12/05/2026",
    "data_apertura_sinistro": "12/05/2026",
    "anno_sinistro": "2026",
    "tipologia_sinistro": "Collisione",
    "luogo_sinistro": "Via Milano, Torino",
    "ramo_sinistro": "RC Auto",
    "stato_sinistro": "Aperto",
    "descrizione_sinistro": "Tamponamento a un incrocio con danni al paraurti posteriore",
    "riserva_sinistro": "€ 3.500,00",
    "liquidazione_sinistro": "€ 2.800,00",
    "data_liquidazione_sinistro": "20/06/2026",
    # Compagnia
    "compagnia": "Generali",
    "compagnia_nome": "Generali Italia S.p.A.",
    "compagnia_codice": "GEN",
    "compagnia_email": "sinistri@generali.it",
    "compagnia_telefono": "800 123456",
    "compagnia_sito_web": "www.generali.it",
    "compagnia_referente": "Dott. Bianchi",
    # Collaboratore / Operatore
    "operatore_nome": "Luca Verdi",
    "operatore_email": "luca.verdi@rossiassicurazioni.it",
    "operatore_telefono": "02 1234500",
    "operatore_codice_fiscale": "VRDLCU85M01F205Y",
    "operatore_partita_iva": "09876543210",
    "operatore_iban": "IT60X0542811101000000999888",
    "operatore_rui": "E000654321",
    "operatore_sezione": "E",
    # Grafica e firma
    "logo": "[logo agenzia]",
    "firma_operatore": "[firma operatore]",
    "firma": "[campo firma cliente]",
    "data_firma": "26/10/2026",
}


@router.get("/librerie/placeholders")
async def lista_placeholders(user: dict = Depends(current_user)) -> dict:
    """Elenco di TUTTI i segnaposto {...} supportati, raggruppati per categoria.
    Vanno inseriti nel testo del modello (o nel Word/PDF caricato): in fase di
    generazione vengono sostituiti con i dati reali di polizza/cliente/agenzia."""
    gruppi = [
        {"gruppo": nome, "items": [
            {"key": k, "label": lbl, "token": "{" + k + "}", "esempio": _PLACEHOLDER_ESEMPI.get(k, "")}
            for k, lbl in voci
        ]}
        for nome, voci in _PLACEHOLDER_CATALOGO
    ]
    # Gruppo dinamico: tabelle create dall'utente
    tab_items = []
    async for t in db.modelli_tabelle.find({}).sort("nome", 1):
        slug = t.get("slug")
        if not slug:
            continue
        tab_items.append({
            "key": f"tabella:{slug}",
            "label": t.get("nome") or slug,
            "token": "{tabella:" + slug + "}",
            "esempio": t.get("descrizione") or "Tabella riutilizzabile",
        })
    if tab_items:
        gruppi.append({"gruppo": "Tabelle", "items": tab_items})
    return {"gruppi": gruppi, "totale": sum(len(g["items"]) for g in gruppi)}


# ---------------------------------------------------------------------------
# Tabelle riutilizzabili (griglia / checklist) — segnaposto {tabella:slug}
# ---------------------------------------------------------------------------
class VoceChecklist(BaseModel):
    testo: str = ""
    spunte: List[bool] = Field(default_factory=list)


class TabellaBody(BaseModel):
    nome: str
    descrizione: Optional[str] = None
    tipo: str = "griglia"  # "griglia" | "checklist"
    mostra_intestazione: bool = True
    colonne: List[str] = Field(default_factory=list)
    # griglia
    righe: List[List[str]] = Field(default_factory=list)
    # checklist
    prima_colonna: Optional[str] = None
    voci: List[VoceChecklist] = Field(default_factory=list)


def _tabella_out(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "slug": t.get("slug"),
        "nome": t.get("nome"),
        "descrizione": t.get("descrizione"),
        "tipo": t.get("tipo") or "griglia",
        "mostra_intestazione": t.get("mostra_intestazione", True),
        "colonne": t.get("colonne") or [],
        "righe": t.get("righe") or [],
        "prima_colonna": t.get("prima_colonna"),
        "voci": t.get("voci") or [],
        "token": "{tabella:" + (t.get("slug") or "") + "}",
    }


async def _slug_unico(base: str, escludi_id: Optional[str] = None) -> str:
    slug = base
    i = 2
    while True:
        q = {"slug": slug}
        existing = await db.modelli_tabelle.find_one(q)
        if not existing or existing.get("id") == escludi_id:
            return slug
        slug = f"{base}_{i}"
        i += 1


_TABELLE_DEFAULT = [
    {
        "nome": "Dichiarazioni di ricevuta",
        "descrizione": "Dichiarazioni ex art. 56 Reg. IVASS 40/2018",
        "tipo": "checklist",
        "mostra_intestazione": False,
        "prima_colonna": "Il contraente dichiara",
        "colonne": ["✔"],
        "voci": [
            {"testo": "di aver preso visione e ricevuto l'Allegato 3 – Modulo unico precontrattuale (MUP) per i prodotti assicurativi non d'investimento", "spunte": [True]},
            {"testo": "di aver ricevuto il questionario delle richieste ed esigenze e la valutazione della coerenza del contratto offerto", "spunte": [True]},
            {"testo": "di aver ricevuto la proposta assicurativa nonché tutta la documentazione precontrattuale", "spunte": [True]},
            {"testo": "di aver ricevuto l'informativa sul trattamento dei dati personali (privacy)", "spunte": [True]},
            {"testo": "di accettare la trasmissione della documentazione precontrattuale e contrattuale in formato elettronico, consapevole di poter modificare la preferenza e richiedere la documentazione su supporto cartaceo o altro supporto durevole", "spunte": [True]},
            {"testo": "di aver ricevuto il testo contrattuale della polizza/appendice", "spunte": [True]},
            {"testo": "di autorizzare l'intermediario a conservare presso le proprie strutture copia della documentazione contrattuale firmata", "spunte": [True]},
        ],
    },
    {
        "nome": "Valutazione del prodotto",
        "descrizione": "Garanzie richieste / proposte / confermate",
        "tipo": "checklist",
        "mostra_intestazione": True,
        "prima_colonna": "Garanzia",
        "colonne": ["Richiesta", "Proposta", "Confermata"],
        "voci": [
            {"testo": "Responsabilità Civile Auto (RCA)", "spunte": [False, False, False]},
            {"testo": "Rinuncia alla Rivalsa", "spunte": [False, False, False]},
            {"testo": "Ricorso Terzi da Incendio", "spunte": [False, False, False]},
            {"testo": "Cristalli", "spunte": [False, False, False]},
            {"testo": "Assistenza Stradale", "spunte": [False, False, False]},
            {"testo": "Incendio", "spunte": [False, False, False]},
            {"testo": "Furto", "spunte": [False, False, False]},
            {"testo": "Atti Vandalici / Eventi Sociopolitici", "spunte": [False, False, False]},
            {"testo": "Eventi Atmosferici", "spunte": [False, False, False]},
            {"testo": "Kasko / Collisione", "spunte": [False, False, False]},
            {"testo": "Tutela Legale", "spunte": [False, False, False]},
            {"testo": "Infortuni del Conducente", "spunte": [False, False, False]},
        ],
    },
    {
        "nome": "Rapporti con le compagnie",
        "descrizione": "Imprese di assicurazione e tipologia di rapporto",
        "tipo": "griglia",
        "mostra_intestazione": True,
        "colonne": ["Impresa di assicurazione", "Tipologia di rapporto"],
        "righe": [
            ["GENERALI ITALIA S.P.A.", "Mandato diretto con Compagnia di assicurazione"],
            ["UCA ASSICURAZIONE SPESE LEGALI E PERITALI S.P.A.", "Mandato diretto con Compagnia di assicurazione"],
        ],
    },
]


async def _seed_tabelle_default(user: dict) -> None:
    """Crea le tabelle di partenza se il tenant non ne ha ancora."""
    from tenant import assign_tenant
    for d in _TABELLE_DEFAULT:
        base = _slugify_tabella(d["nome"])
        slug = await _slug_unico(base)
        doc = {
            "id": str(uuid.uuid4()),
            "slug": slug,
            "nome": d["nome"],
            "descrizione": d.get("descrizione"),
            "tipo": d.get("tipo", "griglia"),
            "mostra_intestazione": d.get("mostra_intestazione", True),
            "colonne": d.get("colonne", []),
            "righe": d.get("righe", []),
            "prima_colonna": d.get("prima_colonna"),
            "voci": d.get("voci", []),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        doc = assign_tenant(user, doc)
        await db.modelli_tabelle.insert_one(doc)


@router.get("/librerie/tabelle")
async def lista_tabelle(user: dict = Depends(current_user)) -> List[dict]:
    n = await db.modelli_tabelle.count_documents({})
    if n == 0:
        await _seed_tabelle_default(user)
    out = []
    async for t in db.modelli_tabelle.find({}).sort("nome", 1):
        out.append(_tabella_out(t))
    return out


@router.post("/librerie/tabelle")
async def crea_tabella(body: TabellaBody, user: dict = Depends(current_user)) -> dict:
    from tenant import assign_tenant
    slug = await _slug_unico(_slugify_tabella(body.nome))
    doc = {
        "id": str(uuid.uuid4()),
        "slug": slug,
        "nome": body.nome,
        "descrizione": body.descrizione,
        "tipo": body.tipo,
        "mostra_intestazione": body.mostra_intestazione,
        "colonne": body.colonne,
        "righe": body.righe,
        "prima_colonna": body.prima_colonna,
        "voci": [v.model_dump() for v in body.voci],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc = assign_tenant(user, doc)
    await db.modelli_tabelle.insert_one(doc)
    return _tabella_out(doc)


@router.put("/librerie/tabelle/{tid}")
async def aggiorna_tabella(tid: str, body: TabellaBody, user: dict = Depends(current_user)) -> dict:
    t = await db.modelli_tabelle.find_one({"id": tid})
    if not t:
        raise HTTPException(404, "Tabella non trovata")
    upd = {
        "nome": body.nome,
        "descrizione": body.descrizione,
        "tipo": body.tipo,
        "mostra_intestazione": body.mostra_intestazione,
        "colonne": body.colonne,
        "righe": body.righe,
        "prima_colonna": body.prima_colonna,
        "voci": [v.model_dump() for v in body.voci],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.modelli_tabelle.update_one({"id": tid}, {"$set": upd})
    t = await db.modelli_tabelle.find_one({"id": tid})
    return _tabella_out(t)


@router.delete("/librerie/tabelle/{tid}")
async def elimina_tabella(tid: str, user: dict = Depends(current_user)) -> dict:
    r = await db.modelli_tabelle.delete_one({"id": tid})
    if r.deleted_count == 0:
        raise HTTPException(404, "Tabella non trovata")
    return {"ok": True}


def _estrai_testo_pdf(raw: bytes) -> str:
    """Estrae il testo da un PDF (pdfplumber)."""
    import io
    import pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            pagine = [(pg.extract_text() or "") for pg in pdf.pages]
        return "\n\n".join(pagine).strip()
    except Exception as e:  # noqa
        raise HTTPException(400, f"Impossibile leggere il PDF: {str(e)[:150]}")


def _estrai_testo_docx(raw: bytes) -> str:
    """Estrae il testo da un file Word .docx (paragrafi + tabelle)."""
    import io
    from docx import Document
    try:
        doc = Document(io.BytesIO(raw))
    except Exception as e:  # noqa
        raise HTTPException(400, f"Impossibile leggere il Word: {str(e)[:150]}")
    parti: list[str] = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            celle = [c.text.strip() for c in row.cells if c.text.strip()]
            if celle:
                parti.append(" | ".join(celle))
    return "\n".join(x for x in parti if x is not None).strip()


async def _ai_trasforma_in_modello(testo: str, user: dict) -> str:
    """Trasforma il testo grezzo di un documento in un modello con {segnaposto}."""
    import os
    ph_list = ", ".join("{" + p + "}" for p in _PLACEHOLDER_DISPONIBILI)
    prompt = (
        "Trasforma il seguente documento in un MODELLO riutilizzabile per un CRM assicurativo italiano.\n"
        "Sostituisci i dati specifici (nome cliente, indirizzo, codice fiscale/P.IVA, numero polizza, "
        "compagnia, importi, date, contatti dell'agenzia e del collaboratore, ecc.) con i SEGNAPOSTO "
        "tra parentesi graffe SOLO da questo elenco disponibile:\n"
        f"{ph_list}\n\n"
        "Regole:\n"
        "- Usa esclusivamente i segnaposto elencati; se un dato non ha un segnaposto adatto, lascia il testo generico.\n"
        "- Dove nel documento c'è lo spazio per la FIRMA del cliente, inserisci il segnaposto {firma}.\n"
        "- Dove va la firma/timbro del collaboratore/intermediario, usa {firma_operatore}.\n"
        "- Mantieni la struttura e i paragrafi del documento (intestazioni, articoli, elenchi).\n"
        "- NON aggiungere commenti, spiegazioni o markdown: restituisci solo il testo del modello.\n"
        "- Conserva la lingua originale (italiano).\n\n"
        "DOCUMENTO:\n" + testo[:20000]
    )
    try:
        from llm_compat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"modello_doc_{user.get('id')}",
            system_message="Sei un assistente che converte documenti assicurativi in modelli con segnaposto. Rispondi solo con il testo del modello.",
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        corpo = str(resp).strip() if resp else ""
    except Exception as e:  # noqa
        raise HTTPException(502, f"Errore AI durante la trasformazione: {str(e)[:200]}")
    return corpo or testo


@router.post("/librerie/modelli/da-pdf", status_code=201)
async def crea_modello_da_pdf(
    file: UploadFile = File(...),
    tipo: str = Form("pdf_altro"),
    nome: Optional[str] = Form(None),
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Carica un PDF, ne estrae il testo con l'AI e lo trasforma in un modello
    editabile con i {segnaposto} del CRM, poi lo salva come TemplateModello."""
    if file is None:
        raise HTTPException(400, "Nessun file caricato")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "File vuoto")
    testo = _estrai_testo_pdf(raw)
    if not testo:
        raise HTTPException(422, "Il PDF non contiene testo estraibile (potrebbe essere una scansione immagine)")
    corpo = await _ai_trasforma_in_modello(testo, user)
    nome_finale = (nome or "").strip() or (file.filename or "Modello da PDF").rsplit(".", 1)[0]
    body = ModelloBody(tipo=tipo, nome=nome_finale, corpo=corpo)
    doc = TemplateModello(
        tipo=body.tipo,                 # type: ignore[arg-type]
        nome=body.nome.strip(),
        corpo=body.corpo,
        categoria="da_pdf",
        note=f"Generato da PDF: {file.filename}",
        placeholders=_autodetect_placeholders(body),
    ).model_dump()
    await db.template_modelli.insert_one(doc)
    doc.pop("_id", None)
    await log_attivita(user, "create", "modello", doc["id"], doc["nome"])
    return doc


@router.post("/librerie/modelli/da-word", status_code=201)
async def crea_modello_da_word(
    file: UploadFile = File(...),
    tipo: str = Form("word"),
    nome: Optional[str] = Form(None),
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Carica un file Word (.docx), ne estrae il testo con l'AI e lo trasforma in
    un modello editabile con i {segnaposto} del CRM."""
    if file is None:
        raise HTTPException(400, "Nessun file caricato")
    fname = (file.filename or "").lower()
    if not fname.endswith((".docx", ".doc")):
        raise HTTPException(400, "Carica un file Word (.docx)")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "File vuoto")
    testo = _estrai_testo_docx(raw)
    if not testo:
        raise HTTPException(422, "Il Word non contiene testo leggibile")
    corpo = await _ai_trasforma_in_modello(testo, user)
    nome_finale = (nome or "").strip() or (file.filename or "Modello da Word").rsplit(".", 1)[0]
    body = ModelloBody(tipo=tipo, nome=nome_finale, corpo=corpo)
    doc = TemplateModello(
        tipo=body.tipo,                 # type: ignore[arg-type]
        nome=body.nome.strip(),
        corpo=body.corpo,
        categoria="da_word",
        note=f"Generato da Word: {file.filename}",
        placeholders=_autodetect_placeholders(body),
    ).model_dump()
    await db.template_modelli.insert_one(doc)
    doc.pop("_id", None)
    await log_attivita(user, "create", "modello", doc["id"], doc["nome"])
    return doc


@router.post("/librerie/modelli/estrai-testo")
async def estrai_testo_documento(
    file: UploadFile = File(...),
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Estrae e trasforma in {segnaposto} il testo di un PDF o Word, SENZA salvare.
    Usato dai Modelli MUP per importare un documento e renderlo compilabile."""
    if file is None:
        raise HTTPException(400, "Nessun file caricato")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "File vuoto")
    fname = (file.filename or "").lower()
    if fname.endswith((".docx", ".doc")):
        testo = _estrai_testo_docx(raw)
    elif fname.endswith(".pdf"):
        testo = _estrai_testo_pdf(raw)
    else:
        raise HTTPException(400, "Formato non supportato: carica un PDF o un Word (.docx)")
    if not testo:
        raise HTTPException(422, "Nessun testo estraibile dal documento")
    corpo = await _ai_trasforma_in_modello(testo, user)
    return {"corpo": corpo, "nome": (file.filename or "Modello").rsplit(".", 1)[0]}



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


# ============================================================
# Rendering + generazione documenti (PDF / Word) + invio WhatsApp
# ============================================================
def render_text(text: str, ctx: dict) -> str:
    """Sostituisce i placeholder {nome} in modo sicuro (mancanti → lasciati)."""
    return _PLACEHOLDER_RE.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), text or "")


def _slugify_tabella(nome: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s[:40] or "tabella"


def _tabella_righe_render(tab: dict, ctx: dict):
    """Risolve una tabella in (headers, rows) con i segnaposto sostituiti.

    headers è ``None`` quando l'intestazione non va mostrata.
    """
    tipo = tab.get("tipo") or "griglia"
    mostra = tab.get("mostra_intestazione", True)
    if tipo == "checklist":
        cols = tab.get("colonne") or []
        prima = tab.get("prima_colonna") or ""
        headers = ([render_text(prima, ctx)] + [render_text(c, ctx) for c in cols]) if mostra else None
        rows = []
        for v in tab.get("voci") or []:
            testo = render_text(v.get("testo") or "", ctx)
            spunte = v.get("spunte") or []
            cells = [testo]
            for i in range(len(cols)):
                checked = spunte[i] if i < len(spunte) else False
                cells.append("X" if checked else "")
            rows.append(cells)
        return headers, rows
    # griglia
    cols = tab.get("colonne") or []
    headers = [render_text(c, ctx) for c in cols] if (cols and mostra) else None
    rows = [[render_text(str(c if c is not None else ""), ctx) for c in row]
            for row in (tab.get("righe") or [])]
    return headers, rows


async def _load_tabelle_map(slugs) -> dict:
    """Carica le tabelle (tenant-scoped) indicizzate per slug."""
    slugs = [s for s in set(slugs) if s]
    if not slugs:
        return {}
    out: dict[str, dict] = {}
    async for t in db.modelli_tabelle.find({"slug": {"$in": slugs}}):
        out[t.get("slug")] = t
    return out


def _isolate_tabelle(text: str) -> str:
    """Mette ogni segnaposto tabella su un paragrafo isolato."""
    return _TABELLA_RE.sub(lambda m: "\n\n" + m.group(0) + "\n\n", text or "")


def _esc_html(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _docx_build_tabella(doc, headers, rows) -> None:
    """Costruisce e appende una tabella Word (python-docx) al documento."""
    ncols = len(headers) if headers else (len(rows[0]) if rows else 1)
    if ncols < 1:
        ncols = 1
    table = doc.add_table(rows=0, cols=ncols)
    try:
        table.style = "Table Grid"
    except Exception:
        pass
    if headers:
        cells = table.add_row().cells
        for i, h in enumerate(headers):
            if i >= ncols:
                break
            cells[i].text = str(h)
            for p in cells[i].paragraphs:
                for run in p.runs:
                    run.bold = True
    for r in rows:
        cells = table.add_row().cells
        for i, c in enumerate(r):
            if i >= ncols:
                break
            cells[i].text = str(c if c is not None else "")
    doc.add_paragraph("")


def _pdf_build_tabella(tab, headers, rows, styles, mm, Paragraph, Table, TableStyle, rl_colors):
    """Costruisce un flowable Table (reportlab) per una tabella riutilizzabile."""
    from reportlab.lib.styles import ParagraphStyle
    hstyle = ParagraphStyle("tab_hdr", parent=styles["Normal"],
                            textColor=rl_colors.white, fontName="Helvetica-Bold", fontSize=9)
    cstyle = ParagraphStyle("tab_cell", parent=styles["Normal"], fontSize=9, leading=11)
    checklist = (tab.get("tipo") == "checklist")
    data = []
    if headers:
        data.append([Paragraph(_esc_html(h).replace("\n", "<br/>"), hstyle) for h in headers])
    for r in rows:
        data.append([Paragraph(_esc_html(c).replace("\n", "<br/>"), cstyle) for c in r])
    if not data:
        return None
    ncols = len(data[0])
    usable = 170 * mm
    if checklist and ncols > 1:
        first = usable * 0.55
        rest = (usable - first) / (ncols - 1)
        colw = [first] + [rest] * (ncols - 1)
    else:
        colw = [usable / ncols] * ncols
    t = Table(data, colWidths=colw, repeatRows=1 if headers else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.HexColor("#94a3b8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if headers:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1e293b")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#f1f5f9")]),
        ]
    if checklist and ncols > 1:
        style += [("ALIGN", (1, 0), (-1, -1), "CENTER")]
    t.setStyle(TableStyle(style))
    return t


def _fmt_eur_doc(v) -> str:
    try:
        return f"{float(v):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "-"


def _fmt_date_doc(s) -> str:
    if not s:
        return "-"
    s = str(s)[:10]
    parts = s.split("-")
    return f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else s


async def _load_logo_bytes(az: dict) -> Optional[bytes]:
    """Carica il logo dell'agenzia come bytes.

    Prova prima da ``logo_storage_path`` (file locale), poi da ``logo_url``
    (data URL base64 o URL remoto). Ritorna None se non esiste o è illeggibile.
    """
    import base64
    import pathlib
    # 1) file locale
    p = az.get("logo_storage_path")
    if p:
        try:
            path = pathlib.Path(p)
            if path.exists() and path.is_file():
                return path.read_bytes()
        except OSError:
            pass
    # 2) URL: data:image/...;base64,XXX oppure http(s)
    url = az.get("logo_url") or ""
    if url.startswith("data:"):
        try:
            b64 = url.split(",", 1)[1]
            return base64.b64decode(b64)
        except (ValueError, IndexError):
            return None
    if url.startswith(("http://", "https://")):
        try:
            import httpx  # type: ignore
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.content
        except Exception:
            return None
    return None


async def build_context(cliente_id: Optional[str] = None,
                         polizza_id: Optional[str] = None,
                         extra: Optional[dict] = None,
                         operatore_id: Optional[str] = None,
                         titolo_id: Optional[str] = None,
                         sinistro_id: Optional[str] = None) -> dict:
    """Contesto placeholder standard: agenzia + cliente + polizza + titolo +
    sinistro + compagnia + collaboratore. Risolve a cascata le entità mancanti
    (es. da titolo/sinistro ricava polizza e cliente)."""
    from datetime import date
    az = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    ctx: dict = {
        "azienda_nome": az.get("ragione_sociale") or az.get("nome") or "",
        "azienda_forma_giuridica": az.get("forma_giuridica") or "",
        "azienda_partita_iva": az.get("partita_iva") or "",
        "azienda_codice_fiscale": az.get("codice_fiscale") or "",
        "agenzia_rui": az.get("rui") or "",
        "agenzia_rui_sezione": az.get("rui_sezione") or "",
        "agenzia_data_iscrizione_rui": _fmt_date_doc(az.get("data_iscrizione_rui")) if az.get("data_iscrizione_rui") else "",
        "azienda_indirizzo": az.get("indirizzo") or "",
        "azienda_comune": az.get("comune") or "",
        "azienda_provincia": az.get("provincia") or "",
        "azienda_cap": az.get("cap") or "",
        "azienda_nazione": az.get("nazione") or "",
        "azienda_telefono": az.get("telefono") or "",
        "azienda_fax": az.get("fax") or "",
        "azienda_email": az.get("email") or "",
        "azienda_pec": az.get("pec") or "",
        "azienda_sito_web": az.get("sito_web") or "",
        "azienda_iban": az.get("iban") or "",
        "azienda_banca": az.get("banca") or "",
        "azienda_capitale_sociale": az.get("capitale_sociale") or "",
        "azienda_rea": az.get("rea") or "",
        "data_oggi": date.today().strftime("%d/%m/%Y"),
    }
    # Risoluzione a cascata: sinistro → polizza/cliente; titolo → polizza → cliente
    sin = None
    if sinistro_id:
        sin = await db.sinistri.find_one({"id": sinistro_id}, {"_id": 0})
        if sin:
            polizza_id = polizza_id or sin.get("polizza_id")
            cliente_id = cliente_id or sin.get("contraente_id")
    tit = None
    if titolo_id:
        tit = await db.titoli.find_one({"id": titolo_id}, {"_id": 0})
        if tit:
            polizza_id = polizza_id or tit.get("polizza_id")
    p = None
    if polizza_id:
        p = await db.polizze.find_one({"id": polizza_id}, {"_id": 0})
    if p:
        comp = await db.compagnie.find_one({"id": p.get("compagnia_id")}, {"_id": 0}) or {}
        comp_nome = comp.get("ragione_sociale") or comp.get("nome") or "-"
        ctx.update({
            "numero_polizza": p.get("numero_polizza") or "-",
            "ramo": p.get("ramo") or "-",
            "prodotto": p.get("prodotto") or "-",
            "stato_polizza": p.get("stato") or "-",
            "frazionamento": p.get("frazionamento") or "-",
            "scadenza": _fmt_date_doc(p.get("scadenza")),
            "data_scadenza": _fmt_date_doc(p.get("scadenza")),
            "effetto": _fmt_date_doc(p.get("effetto")),
            "data_effetto": _fmt_date_doc(p.get("effetto")),
            "premio": _fmt_eur_doc(p.get("premio_lordo")),
            "premio_lordo": _fmt_eur_doc(p.get("premio_lordo")),
            "premio_netto": _fmt_eur_doc(p.get("premio_netto")),
            "premio_imposte": _fmt_eur_doc(p.get("premio_imposte")),
            "premio_tasse": _fmt_eur_doc(p.get("premio_tasse")),
            "premio_ssn": _fmt_eur_doc(p.get("premio_ssn")),
            "premio_accessori": _fmt_eur_doc(p.get("premio_accessori")),
            "provvigioni_polizza": _fmt_eur_doc(p.get("provvigioni")),
            "importo": _fmt_eur_doc(p.get("premio_lordo")),
            "mandato": p.get("mandato") or "-",
            "targa": p.get("targa") or "-",
            "veicolo_marca": p.get("veicolo_marca") or "-",
            "veicolo_modello": p.get("veicolo_modello") or "-",
            "veicolo_tipo": p.get("veicolo_tipo") or "-",
            "veicolo_immatricolazione": _fmt_date_doc(p.get("veicolo_data_immatricolazione")) if p.get("veicolo_data_immatricolazione") else "-",
            "massimali": p.get("massimali") or "-",
            "franchigia": _fmt_eur_doc(p.get("franchigia")),
            "capitale_assicurato": _fmt_eur_doc(p.get("capitale_assicurato")),
            "oggetto_assicurato": p.get("oggetto_assicurato") or p.get("assicurato_oggetto_nome") or "-",
            "compagnia": comp_nome,
            "compagnia_nome": comp_nome,
            "compagnia_codice": comp.get("codice") or "-",
            "compagnia_email": comp.get("email") or "-",
            "compagnia_telefono": comp.get("telefono") or "-",
            "compagnia_sito_web": comp.get("sito_web") or "-",
            "compagnia_referente": comp.get("referente") or "-",
        })
        cliente_id = cliente_id or p.get("contraente_id")
    if tit:
        ctx.update({
            "numero_titolo": tit.get("numero_titolo") or "-",
            "titolo_tipo": tit.get("tipo") or "-",
            "titolo_effetto": _fmt_date_doc(tit.get("effetto")),
            "titolo_scadenza": _fmt_date_doc(tit.get("scadenza")),
            "titolo_stato": tit.get("stato") or "-",
            "titolo_importo_lordo": _fmt_eur_doc(tit.get("importo_lordo")),
            "titolo_importo_netto": _fmt_eur_doc(tit.get("importo_netto")),
            "titolo_imposte": _fmt_eur_doc(tit.get("imposte")),
            "titolo_ssn": _fmt_eur_doc(tit.get("ssn")),
            "titolo_accessori": _fmt_eur_doc(tit.get("accessori")),
            "titolo_provvigioni": _fmt_eur_doc(tit.get("provvigioni")),
            "titolo_descrizione": tit.get("descrizione") or "-",
            "titolo_data_incasso": _fmt_date_doc(tit.get("data_incasso")) if tit.get("data_incasso") else "-",
            "titolo_importo_pagato": _fmt_eur_doc(tit.get("importo_pagato")) if tit.get("importo_pagato") is not None else "-",
            "titolo_sconto": _fmt_eur_doc(tit.get("sconto_applicato")),
            "titolo_mezzo_pagamento": tit.get("mezzo_pagamento") or "-",
        })
    if sin:
        ctx.update({
            "numero_sinistro": sin.get("numero_sinistro") or "-",
            "numero_sinistro_interno": sin.get("numero_interno") or "-",
            "data_sinistro": _fmt_date_doc(sin.get("data_avvenimento")) if sin.get("data_avvenimento") else "-",
            "data_denuncia": _fmt_date_doc(sin.get("data_denuncia")) if sin.get("data_denuncia") else "-",
            "data_apertura_sinistro": _fmt_date_doc(sin.get("data_apertura")) if sin.get("data_apertura") else "-",
            "anno_sinistro": str(sin.get("anno") or "-"),
            "tipologia_sinistro": sin.get("tipologia_sinistro") or "-",
            "luogo_sinistro": sin.get("luogo") or "-",
            "ramo_sinistro": sin.get("ramo") or "-",
            "stato_sinistro": sin.get("stato") or "-",
            "descrizione_sinistro": sin.get("descrizione") or "-",
            "riserva_sinistro": _fmt_eur_doc(sin.get("riserva")),
            "liquidazione_sinistro": _fmt_eur_doc(sin.get("liquidazione")),
            "data_liquidazione_sinistro": _fmt_date_doc(sin.get("data_liquidazione")) if sin.get("data_liquidazione") else "-",
        })
    if cliente_id:
        a = await db.anagrafiche.find_one({"id": cliente_id}, {"_id": 0})
        if a:
            nome = a.get("ragione_sociale") or f"{a.get('nome') or ''} {a.get('cognome') or ''}".strip()
            indirizzo = ", ".join(x for x in [a.get("indirizzo"), a.get("cap"), a.get("citta") or a.get("comune")] if x)
            ctx.update({
                "cliente": nome, "cliente_nome": nome,
                "cliente_cognome": a.get("cognome") or "",
                "cliente_ragione_sociale": a.get("ragione_sociale") or nome,
                "cliente_tipo": "Persona giuridica" if a.get("tipo") == "persona_giuridica" else "Persona fisica",
                "cliente_indirizzo": indirizzo,
                "cliente_via": a.get("indirizzo") or "-",
                "cliente_comune": a.get("comune") or a.get("citta") or "-",
                "cliente_cap": a.get("cap") or "-",
                "cliente_provincia": a.get("provincia") or "-",
                "cliente_nazione": a.get("nazione") or "-",
                "cliente_cf": a.get("codice_fiscale") or a.get("partita_iva") or "-",
                "cliente_codice_fiscale": a.get("codice_fiscale") or "-",
                "cliente_partita_iva": a.get("partita_iva") or "-",
                "cliente_email": a.get("email") or "-",
                "cliente_pec": a.get("pec") or "-",
                "cliente_telefono": a.get("telefono") or "-",
                "cliente_cellulare": a.get("cellulare") or a.get("telefono") or "-",
                "cliente_data_nascita": _fmt_date_doc(a.get("data_nascita")),
                "cliente_luogo_nascita": a.get("comune_nascita") or a.get("luogo_nascita") or "-",
                "cliente_provincia_nascita": a.get("provincia_nascita") or "-",
                "cliente_sesso": a.get("sesso") or "-",
                "cliente_stato_civile": a.get("stato_civile") or "-",
                "cliente_titolo_studio": a.get("titolo_studio") or "-",
                "cliente_professione": a.get("professione") or a.get("attivita") or "-",
                "cliente_iban": a.get("iban") or "-",
                "cliente_amministratore": a.get("amministratore") or "-",
            })
    if operatore_id:
        u = await db.users.find_one({"id": operatore_id}, {"_id": 0}) or {}
        if u:
            ctx.update({
                "operatore_nome": u.get("name") or u.get("nome") or "",
                "operatore_email": u.get("email") or "",
                "operatore_telefono": u.get("telefono") or "",
                "operatore_codice_fiscale": u.get("codice_fiscale") or "",
                "operatore_partita_iva": u.get("partita_iva") or "",
                "operatore_iban": u.get("iban") or "",
                "operatore_rui": u.get("rui") or u.get("rui_numero_iscrizione") or az.get("rui") or "",
                "operatore_sezione": u.get("rui_sezione") or az.get("rui_sezione") or "",
            })
            # URL firma collaboratore (interno: usato per inserire l'immagine, non come testo)
            ctx["_firma_operatore_url"] = u.get("firma_digitale_url")
    ctx.update(extra or {})
    return ctx


async def _load_image_from_url(url: Optional[str]) -> Optional[bytes]:
    """Carica i bytes di un'immagine da un URL interno /api/storage/... , data URL o http(s)."""
    if not url:
        return None
    import base64
    if url.startswith("/api/storage/"):
        path = url[len("/api/storage/"):]
        try:
            import storage as obj_storage
            data, _ = obj_storage.get_object(path)
            return data
        except Exception:
            return None
    if url.startswith("data:"):
        try:
            return base64.b64decode(url.split(",", 1)[1])
        except (ValueError, IndexError):
            return None
    if url.startswith(("http://", "https://")):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.content
        except Exception:
            return None
    return None


class GeneraDocBody(BaseModel):
    cliente_id: Optional[str] = None
    polizza_id: Optional[str] = None
    operatore_id: Optional[str] = None
    titolo_id: Optional[str] = None
    sinistro_id: Optional[str] = None
    extra: dict = {}
    formato: str = "pdf"  # pdf | docx
    invia_firma: bool = False               # invia a firma digitale Yousign
    email_firmatario: Optional[str] = None  # email del firmatario (override cliente)
    auth_mode: Optional[str] = None         # otp_email | otp_sms | no_otp


class PreviewBody(BaseModel):
    tipo: str = "email"
    oggetto: Optional[str] = None
    corpo: str = ""
    sezioni: list[dict] = []
    template_riga: Optional[str] = None
    cliente_id: Optional[str] = None
    polizza_id: Optional[str] = None
    extra: dict = {}


@router.post("/librerie/modelli/preview")
async def preview_modello(body: PreviewBody, user: dict = Depends(current_user)) -> dict:
    """Rende un modello con placeholder → testo compilato (senza salvare).

    Usato dall'editor "Gestioni Modelli" per l'anteprima live durante la
    modifica del template. Se ``cliente_id``/``polizza_id`` non sono forniti,
    usa dati di esempio così l'utente vede come apparirà il messaggio finale.
    """
    ctx = await build_context(body.cliente_id, body.polizza_id, body.extra)
    # Se non abbiamo cliente reale, popoliamo con dati di esempio realistici
    # per rendere l'anteprima più utile durante la creazione del modello.
    if not body.cliente_id:
        ctx.setdefault("cliente_nome", "Mario Rossi")
        ctx.setdefault("cliente_cellulare", "+39 333 1234567")
        ctx.setdefault("cliente_email", "mario.rossi@example.com")
        ctx.setdefault("cliente_indirizzo", "Via Roma 12, 23100 Sondrio")
    if not body.polizza_id:
        ctx.setdefault("numero_polizza", "POL-2026-000123")
        ctx.setdefault("ramo", "RCA")
        ctx.setdefault("data_scadenza", "31/12/2026")
        ctx.setdefault("premio_lordo", "1.240,50 €")
        ctx.setdefault("compagnia_nome", "AXA Assicurazioni")
    ctx.setdefault("numero_titoli", "1")
    ctx.setdefault("totale", "1.240,50 €")
    ctx.setdefault("importo_abbuono", "50,00 €")
    ctx.setdefault("numero_titolo", "T-2026-4587")
    ctx.setdefault("targa", "AB123CD")
    # Se l'utente ha definito un template_riga custom, lo applichiamo a 3 titoli fittizi
    if body.template_riga:
        _rows_data = [
            {"numero_polizza": "184643240", "ramo": "RC Auto", "prodotto": "Active Auto",
             "targa": "AB123CD", "scadenza": "27/07/2026", "importo": "1.240,50"},
            {"numero_polizza": "1001797290", "ramo": "TUTELA_LEGALE", "prodotto": "Tutela Legale",
             "targa": "", "scadenza": "23/06/2026", "importo": "10,00"},
            {"numero_polizza": "182260076", "ramo": "RCA", "prodotto": "Active Auto Business",
             "targa": "CD456EF", "scadenza": "29/07/2026", "importo": "637,50"},
        ]
        ctx["elenco_titoli"] = "\n".join(render_text(body.template_riga, r) for r in _rows_data)
    else:
        ctx.setdefault("elenco_titoli",
            "• Polizza 184643240 (RC Auto) [AB123CD] — scad. 27/07/2026 — € 1.240,50\n"
            "• Polizza 1001797290 (TUTELA_LEGALE) — scad. 23/06/2026 — € 10,00\n"
            "• Polizza 182260076 (RCA) [CD456EF] — scad. 29/07/2026 — € 637,50")
    # Placeholder agenzia (letti dalla config)
    az_cfg = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    ctx.setdefault("azienda_iban", az_cfg.get("iban") or "IT00 X 00000 00000 000000000000")
    ctx.setdefault("azienda_telefono", az_cfg.get("telefono") or "+39 0342 000000")
    ctx.setdefault("azienda_email", az_cfg.get("email") or "info@agenzia.it")
    ctx.setdefault("azienda_indirizzo", az_cfg.get("indirizzo") or "Via Roma 1, 23100 Sondrio")

    return {
        "tipo": body.tipo,
        "oggetto": render_text(body.oggetto or "", ctx),
        "corpo": render_text(body.corpo or "", ctx),
        "sezioni": [
            {
                "titolo": render_text(str(s.get("titolo") or ""), ctx),
                "contenuto": render_text(str(s.get("contenuto") or ""), ctx),
                "attiva": s.get("attiva", True),
            }
            for s in (body.sezioni or [])
        ],
        "context_sample": {k: v for k, v in ctx.items() if k in (
            "cliente_nome", "numero_polizza", "ramo", "data_scadenza",
            "premio_lordo", "totale", "azienda_nome",
        )},
    }


@router.post("/librerie/modelli/{mid}/genera")
async def genera_documento(mid: str, body: GeneraDocBody,
                           user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))):
    """Genera un documento PDF o Word dal modello, compilato coi dati reali.

    Supporta i segnaposto immagine ``{logo}`` (logo agenzia) e ``{firma_operatore}``
    (firma del collaboratore selezionato). Se il modello richiede firma e
    ``invia_firma`` è attivo, il PDF viene inviato a firma digitale Yousign nella
    posizione del segnaposto ``{firma}``.
    """
    from fastapi.responses import Response
    m = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Modello non trovato")
    ctx = await build_context(body.cliente_id, body.polizza_id, body.extra, body.operatore_id,
                              body.titolo_id, body.sinistro_id)
    titolo = render_text(m.get("oggetto") or m.get("nome") or "Documento", ctx)
    corpo = render_text(m.get("corpo") or "", ctx)
    sezioni = [
        {"titolo": render_text(str(s.get("titolo") or ""), ctx),
         "contenuto": render_text(str(s.get("contenuto") or ""), ctx)}
        for s in (m.get("sezioni") or []) if s.get("attiva", True)
    ]
    # Tabelle riutilizzabili {tabella:slug}: carica e isola i segnaposto
    _tab_slugs = _TABELLA_RE.findall(corpo) + [
        sl for s in sezioni for sl in _TABELLA_RE.findall(s["contenuto"])
    ]
    tabelle_map = await _load_tabelle_map(_tab_slugs)
    corpo = _isolate_tabelle(corpo)
    for s in sezioni:
        s["contenuto"] = _isolate_tabelle(s["contenuto"])
    az_nome = ctx.get("azienda_nome") or ""
    fname = re.sub(r"[^a-zA-Z0-9_-]+", "_", m.get("nome") or "documento")[:50]

    # Logo: specifico del modello se impostato, altrimenti logo agenzia
    az_full = await db.azienda_config.find_one({}, {"_id": 0}) or {}
    if m.get("logo_url"):
        logo_bytes: Optional[bytes] = await _load_logo_bytes({"logo_url": m.get("logo_url")})
    else:
        logo_bytes = await _load_logo_bytes(az_full)
    firma_op_bytes: Optional[bytes] = await _load_image_from_url(ctx.get("_firma_operatore_url"))

    richiede_firma = bool(m.get("richiede_firma")) or "{firma}" in (m.get("corpo") or "")
    fai_firma = bool(body.invia_firma and richiede_firma and body.formato != "docx")

    if body.formato == "docx":
        import io
        from docx import Document
        from docx.shared import Pt, Inches
        doc = Document()
        if logo_bytes:
            try:
                run = doc.add_paragraph().add_run()
                run.add_picture(io.BytesIO(logo_bytes), width=Inches(1.6))
            except Exception:
                pass
        if az_nome:
            h = doc.add_paragraph(az_nome)
            h.runs[0].bold = True
            h.runs[0].font.size = Pt(14)
        contatti = " · ".join(x for x in [
            ctx.get("azienda_indirizzo"), ctx.get("azienda_telefono"), ctx.get("azienda_email"),
        ] if x)
        if contatti:
            doc.add_paragraph(contatti).runs[0].font.size = Pt(9)
        doc.add_paragraph(ctx.get("data_oggi") or "")
        doc.add_heading(titolo, level=1)

        def _docx_para(testo: str):
            """Aggiunge un paragrafo gestendo i segnaposto immagine/firma."""
            t = testo.strip()
            mtab = _TABELLA_RE.fullmatch(t)
            if mtab:
                tab = tabelle_map.get(mtab.group(1))
                if tab:
                    headers, rows = _tabella_righe_render(tab, ctx)
                    _docx_build_tabella(doc, headers, rows)
                return
            if t == "{logo}":
                if logo_bytes:
                    try:
                        doc.add_paragraph().add_run().add_picture(io.BytesIO(logo_bytes), width=Inches(1.6))
                    except Exception:
                        pass
                return
            if t == "{firma_operatore}":
                if firma_op_bytes:
                    try:
                        doc.add_paragraph().add_run().add_picture(io.BytesIO(firma_op_bytes), width=Inches(1.8))
                    except Exception:
                        pass
                else:
                    doc.add_paragraph("_______________________________")
                return
            t = t.replace("{logo}", "").replace("{firma_operatore}", "")
            t = t.replace("{firma}", "_______________________________")
            doc.add_paragraph(t)

        for para in corpo.split("\n\n"):
            _docx_para(para)
        for s in sezioni:
            if s["titolo"]:
                doc.add_heading(s["titolo"], level=2)
            for para in s["contenuto"].split("\n\n"):
                _docx_para(para)
        buf = io.BytesIO()
        doc.save(buf)
        return Response(
            buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={fname}.docx"},
        )

    # PDF
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors as rl_colors
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=18 * mm)
    el = []
    contatti = "<br/>".join(x for x in [
        ctx.get("azienda_indirizzo"), ctx.get("azienda_telefono"), ctx.get("azienda_email"),
    ] if x)
    header_right = f"<para align='right'><b>{az_nome}</b><br/><font size='8'>{contatti}</font></para>"
    if logo_bytes:
        try:
            img = Image(io.BytesIO(logo_bytes), width=40 * mm, height=20 * mm, kind="proportional")
            head_tbl = Table([[img, Paragraph(header_right, styles["Normal"])]], colWidths=[45 * mm, 135 * mm])
            head_tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#5b21b6")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            el.append(head_tbl)
        except Exception:
            if az_nome:
                el.append(Paragraph(f"<b>{az_nome}</b>", styles["Heading2"]))
    elif az_nome:
        el.append(Paragraph(f"<b>{az_nome}</b>", styles["Heading2"]))
        if contatti:
            el.append(Paragraph(f"<font size='8'>{contatti}</font>", styles["Normal"]))
    el.append(Spacer(1, 6))
    el.append(Paragraph(ctx.get("data_oggi") or "", styles["Normal"]))
    el.append(Spacer(1, 10))
    el.append(Paragraph(f"<b>{titolo}</b>", styles["Heading1"]))
    el.append(Spacer(1, 6))

    def _pdf_para(testo: str):
        """Aggiunge flowable(s) gestendo i segnaposto immagine/firma."""
        t = testo.strip()
        mtab = _TABELLA_RE.fullmatch(t)
        if mtab:
            tab = tabelle_map.get(mtab.group(1))
            if tab:
                headers, rows = _tabella_righe_render(tab, ctx)
                flow = _pdf_build_tabella(tab, headers, rows, styles, mm, Paragraph, Table, TableStyle, rl_colors)
                if flow is not None:
                    el.append(Spacer(1, 4))
                    el.append(flow)
                    el.append(Spacer(1, 8))
            return
        if t == "{logo}":
            if logo_bytes:
                try:
                    el.append(Image(io.BytesIO(logo_bytes), width=40 * mm, height=20 * mm, kind="proportional"))
                    el.append(Spacer(1, 6))
                except Exception:
                    pass
            return
        if t == "{firma_operatore}":
            if firma_op_bytes:
                try:
                    el.append(Image(io.BytesIO(firma_op_bytes), width=45 * mm, height=20 * mm, kind="proportional"))
                    el.append(Spacer(1, 6))
                except Exception:
                    pass
            else:
                el.append(Paragraph("_______________________________", styles["Normal"]))
                el.append(Spacer(1, 6))
            return
        t = t.replace("{logo}", "").replace("{firma_operatore}", "")
        if fai_firma:
            # mantiene il marcatore {firma} nel PDF per il posizionamento Yousign
            t_html = t.replace("\n", "<br/>")
        else:
            t_html = t.replace("{firma}", "_______________________________").replace("{data_firma}", "Data: ______________").replace("\n", "<br/>")
        el.append(Paragraph(t_html, styles["Normal"]))
        el.append(Spacer(1, 6))

    for para in corpo.split("\n\n"):
        _pdf_para(para)
    for s in sezioni:
        if s["titolo"]:
            el.append(Spacer(1, 8))
            el.append(Paragraph(f"<b>{s['titolo']}</b>", styles["Heading3"]))
        for para in s["contenuto"].split("\n\n"):
            _pdf_para(para)
    pdf.build(el)
    pdf_bytes = buf.getvalue()

    # Invio a firma digitale Yousign (posizione del segnaposto {firma})
    if fai_firma:
        import uuid as _uuid
        import os as _os
        import fitz  # pymupdf
        import storage as obj_storage
        from routes.firma_modelli import _invia_yousign
        doc_f = fitz.open(stream=pdf_bytes, filetype="pdf")
        firma_fields = []
        data_fields = []
        for page in doc_f:
            for r in page.search_for("{firma}"):
                page.add_redact_annot(r, text="", fill=(1, 1, 1))
                firma_fields.append({
                    "page": page.number, "x": round(r.x0), "y": round(r.y0),
                    "width": max(120, round(r.width)), "height": max(40, round(r.height * 2.2)),
                })
            for r in page.search_for("{data_firma}"):
                page.add_redact_annot(r, text="", fill=(1, 1, 1))
                data_fields.append({
                    "page": page.number, "x": round(r.x0), "y": round(r.y0),
                    "width": max(90, round(r.width)), "height": max(24, round(r.height * 1.6)),
                })
            page.apply_redactions()
        pdf_bytes = doc_f.tobytes()
        doc_f.close()
        if not firma_fields:
            raise HTTPException(422, "Nessun segnaposto {firma} trovato nel documento")
        cliente_email = ctx.get("cliente_email") if ctx.get("cliente_email") not in (None, "-", "") else ""
        valori = {"nome_cliente": ctx.get("cliente_nome") or "Cliente", "email": cliente_email}
        body_y = {"email_firmatario": body.email_firmatario,
                  "auth_mode": body.auth_mode or "otp_email", "invia_firma": True}
        signing = await _invia_yousign(db, {"nome": m.get("nome")}, pdf_bytes, firma_fields, valori, body_y, data_fields=data_fields)
        fr = (signing or {}).get("firma") or {}
        if not fr.get("ok"):
            raise HTTPException(400, f"Invio a firma non riuscito: {fr.get('error') or 'errore sconosciuto'}")
        # salva il PDF come allegato del cliente/polizza
        aid = str(_uuid.uuid4())
        path = f"{_os.environ.get('APP_NAME', 'assicura')}/documenti_firma/{aid}.pdf"
        obj_storage.put_object(path, pdf_bytes, "application/pdf")
        nome_file = f"{m.get('nome') or 'documento'} - {valori['nome_cliente']}.pdf"
        await db.allegati.insert_one({
            "id": aid, "entita_tipo": "polizza" if body.polizza_id else "anagrafica",
            "entita_id": body.polizza_id or body.cliente_id, "nome_file": nome_file,
            "storage_path": path, "content_type": "application/pdf",
            "size": len(pdf_bytes), "categoria": "documento_firma", "visibile_cliente": True,
            "descrizione": f"Generato da modello {m.get('nome')}",
            "autore_id": user.get("id"), "created_at": _now_iso(), "updated_at": _now_iso(),
        })
        await log_attivita(user, "genera_firma", "modello", mid, nome_file)
        return {"ok": True, "allegato_id": aid, "nome_file": nome_file, "firma_presente": True,
                "signing_url": fr.get("signing_url"), "request_id": fr.get("request_id"),
                "status": fr.get("status"), "firma": fr}

    return Response(pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={fname}.pdf"})


# =====================================================================
# WORD FEDELE — carica un .docx, mantieni l'impaginazione e compila i {segnaposto}
# =====================================================================
def _docx_replace_paragraph(p, mapping: dict) -> None:
    full = "".join(r.text for r in p.runs)
    if "{" not in full:
        return
    new = _PLACEHOLDER_RE.sub(lambda m: str(mapping.get(m.group(1), m.group(0))), full)
    if new == full:
        return
    if p.runs:
        p.runs[0].text = new
        for r in p.runs[1:]:
            r.text = ""


def _docx_iter_tables(tables, mapping: dict) -> None:
    for tbl in tables:
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _docx_replace_paragraph(p, mapping)
                if cell.tables:
                    _docx_iter_tables(cell.tables, mapping)


def _docx_insert_tabella_before(doc, para, headers, rows) -> None:
    """Inserisce una vera tabella Word prima del paragrafo ``para``."""
    ncols = len(headers) if headers else (len(rows[0]) if rows else 1)
    if ncols < 1:
        ncols = 1
    table = doc.add_table(rows=0, cols=ncols)
    try:
        table.style = "Table Grid"
    except Exception:
        pass
    if headers:
        cells = table.add_row().cells
        for i, h in enumerate(headers):
            if i >= ncols:
                break
            cells[i].text = str(h)
            for p in cells[i].paragraphs:
                for run in p.runs:
                    run.bold = True
    for r in rows:
        cells = table.add_row().cells
        for i, c in enumerate(r):
            if i >= ncols:
                break
            cells[i].text = str(c if c is not None else "")
    para._p.addprevious(table._tbl)


def _fill_docx(raw: bytes, mapping: dict, tabelle_rendered: dict | None = None) -> bytes:
    """Sostituisce i {segnaposto} in un .docx mantenendo l'impaginazione originale.

    ``tabelle_rendered`` (slug → (headers, rows)) inserisce vere tabelle Word al
    posto dei segnaposto ``{tabella:slug}``.
    """
    import io
    from docx import Document
    doc = Document(io.BytesIO(raw))
    for p in doc.paragraphs:
        _docx_replace_paragraph(p, mapping)
    _docx_iter_tables(doc.tables, mapping)
    for sec in doc.sections:
        for hf in (sec.header, sec.footer, sec.first_page_header,
                   sec.first_page_footer, sec.even_page_header, sec.even_page_footer):
            try:
                for p in hf.paragraphs:
                    _docx_replace_paragraph(p, mapping)
                _docx_iter_tables(hf.tables, mapping)
            except Exception:
                pass
    if tabelle_rendered:
        for p in list(doc.paragraphs):
            full = "".join(r.text for r in p.runs)
            m = _TABELLA_RE.search(full)
            if not m or m.group(1) not in tabelle_rendered:
                continue
            headers, rows = tabelle_rendered[m.group(1)]
            _docx_insert_tabella_before(doc, p, headers, rows)
            remaining = _TABELLA_RE.sub("", full)
            if remaining.strip():
                if p.runs:
                    p.runs[0].text = remaining
                    for r in p.runs[1:]:
                        r.text = ""
            else:
                p._p.getparent().remove(p._p)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Converte un .docx in PDF mantenendo il layout (LibreOffice headless)."""
    import tempfile
    import subprocess
    import os as _os
    import pathlib
    with tempfile.TemporaryDirectory() as d:
        src = _os.path.join(d, "doc.docx")
        pathlib.Path(src).write_bytes(docx_bytes)
        env = {**_os.environ, "HOME": d}
        try:
            subprocess.run(
                ["soffice", "--headless", "--nologo", "--nofirststartwizard",
                 "--convert-to", "pdf", "--outdir", d, src],
                check=True, timeout=90, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:  # noqa
            raise HTTPException(500, f"Conversione Word→PDF non riuscita: {str(e)[:120]}")
        out = _os.path.join(d, "doc.pdf")
        if not _os.path.exists(out):
            raise HTTPException(500, "Conversione Word→PDF non riuscita")
        return pathlib.Path(out).read_bytes()


@router.post("/librerie/modelli/importa-word-fedele")
async def importa_word_fedele(
    file: UploadFile = File(...),
    nome: str = Form(...),
    categoria: Optional[str] = Form(None),
    user: dict = Depends(require_user("admin", "collaboratore")),
) -> dict:
    """Carica un .docx che resta IDENTICO (layout, font, tabelle, logo). I
    {segnaposto} inseriti nel testo vengono compilati in fase di stampa."""
    import uuid as _uuid
    import os as _os
    import storage as obj_storage
    fname = (file.filename or "").lower()
    if not fname.endswith(".docx"):
        raise HTTPException(400, "Carica un file Word .docx")
    raw = await file.read()
    testo = _estrai_testo_docx(raw)
    placeholders = sorted(set(_PLACEHOLDER_RE.findall(testo)))
    mid = str(_uuid.uuid4())
    path = f"{_os.environ.get('APP_NAME', 'assicura')}/modelli_word/{mid}.docx"
    obj_storage.put_object(
        path, raw,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    doc = TemplateModello(
        tipo="word", nome=nome.strip(), categoria=categoria, corpo="",
        placeholders=placeholders, richiede_firma=("firma" in placeholders),
    ).model_dump()
    doc["id"] = mid
    doc["word_fedele"] = True
    doc["word_storage_path"] = path
    doc["word_filename"] = file.filename
    await db.template_modelli.insert_one(doc)
    doc.pop("_id", None)
    await log_attivita(user, "importa_word_fedele", "modello", mid, nome)
    return doc


@router.post("/librerie/modelli/{mid}/genera-fedele")
async def genera_word_fedele(
    mid: str, body: GeneraDocBody,
    user: dict = Depends(require_user("admin", "collaboratore", "dipendente")),
):
    """Compila un modello 'Word fedele' coi dati reali mantenendo il layout.
    formato=docx → scarica Word; formato=pdf → PDF; invia_firma → firma Yousign."""
    from fastapi.responses import Response
    import storage as obj_storage
    m = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Modello non trovato")
    if not m.get("word_fedele") or not m.get("word_storage_path"):
        raise HTTPException(400, "Questo modello non è un Word fedele")
    raw, _ct = obj_storage.get_object(m["word_storage_path"])
    ctx = await build_context(body.cliente_id, body.polizza_id, body.extra, body.operatore_id,
                              body.titolo_id, body.sinistro_id)
    richiede_firma = bool(m.get("richiede_firma")) or ("firma" in (m.get("placeholders") or []))
    fai_firma = bool(body.invia_firma and richiede_firma)
    mapping = {k: v for k, v in ctx.items() if not k.startswith("_")}
    # Ogni segnaposto conosciuto senza valore → stringa vuota (niente {token} grezzi in stampa)
    for _k in _PLACEHOLDER_DISPONIBILI:
        mapping.setdefault(_k, "")
    mapping["logo"] = ""
    mapping["firma_operatore"] = "______________________________"
    if fai_firma:
        # mantiene i marcatori {firma}/{data_firma} per il posizionamento nel PDF
        mapping.pop("firma", None)
        mapping.pop("data_firma", None)
    else:
        mapping["firma"] = "______________________________"
        mapping["data_firma"] = "Data: ______________"
    # Tabelle riutilizzabili: rende tutte le tabelle del tenant (solo quelle
    # effettivamente richiamate nel documento verranno inserite da _fill_docx)
    tabelle_rendered: dict = {}
    async for t in db.modelli_tabelle.find({}):
        if t.get("slug"):
            tabelle_rendered[t["slug"]] = _tabella_righe_render(t, ctx)
    filled_docx = _fill_docx(raw, mapping, tabelle_rendered)
    fname = re.sub(r"[^a-zA-Z0-9_-]+", "_", m.get("nome") or "documento")[:50]

    if body.formato == "docx" and not fai_firma:
        return Response(
            filled_docx,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={fname}.docx"})

    pdf_bytes = _docx_to_pdf(filled_docx)

    if fai_firma:
        import uuid as _uuid
        import os as _os
        import fitz  # pymupdf
        from routes.firma_modelli import _invia_yousign
        doc_f = fitz.open(stream=pdf_bytes, filetype="pdf")
        firma_fields, data_fields = [], []
        for page in doc_f:
            for r in page.search_for("{firma}"):
                page.add_redact_annot(r, text="", fill=(1, 1, 1))
                firma_fields.append({"page": page.number, "x": round(r.x0), "y": round(r.y0),
                                     "width": max(120, round(r.width)), "height": max(40, round(r.height * 2.2))})
            for r in page.search_for("{data_firma}"):
                page.add_redact_annot(r, text="", fill=(1, 1, 1))
                data_fields.append({"page": page.number, "x": round(r.x0), "y": round(r.y0),
                                    "width": max(90, round(r.width)), "height": max(24, round(r.height * 1.6))})
            page.apply_redactions()
        pdf_bytes = doc_f.tobytes()
        doc_f.close()
        if not firma_fields:
            raise HTTPException(422, "Nessun segnaposto {firma} trovato nel Word")
        cliente_email = ctx.get("cliente_email") if ctx.get("cliente_email") not in (None, "-", "") else ""
        valori = {"nome_cliente": ctx.get("cliente_nome") or "Cliente", "email": cliente_email}
        body_y = {"email_firmatario": body.email_firmatario,
                  "auth_mode": body.auth_mode or "otp_email", "invia_firma": True}
        signing = await _invia_yousign(db, {"nome": m.get("nome")}, pdf_bytes, firma_fields, valori, body_y, data_fields=data_fields)
        fr = (signing or {}).get("firma") or {}
        if not fr.get("ok"):
            raise HTTPException(400, f"Invio a firma non riuscito: {fr.get('error') or 'errore sconosciuto'}")
        aid = str(_uuid.uuid4())
        path = f"{_os.environ.get('APP_NAME', 'assicura')}/documenti_firma/{aid}.pdf"
        obj_storage.put_object(path, pdf_bytes, "application/pdf")
        nome_file = f"{m.get('nome') or 'documento'} - {valori['nome_cliente']}.pdf"
        await db.allegati.insert_one({
            "id": aid, "entita_tipo": "polizza" if body.polizza_id else "anagrafica",
            "entita_id": body.polizza_id or body.cliente_id, "nome_file": nome_file,
            "storage_path": path, "content_type": "application/pdf", "size": len(pdf_bytes),
            "categoria": "documento_firma", "visibile_cliente": True,
            "descrizione": f"Generato da Word fedele {m.get('nome')}",
            "autore_id": user.get("id"), "created_at": _now_iso(), "updated_at": _now_iso(),
        })
        await log_attivita(user, "genera_firma_word", "modello", mid, nome_file)
        return {"ok": True, "allegato_id": aid, "nome_file": nome_file, "firma_presente": True,
                "signing_url": fr.get("signing_url"), "request_id": fr.get("request_id"),
                "status": fr.get("status"), "firma": fr}

    return Response(pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={fname}.pdf"})



class InviaWaModelloBody(BaseModel):
    cliente_id: Optional[str] = None
    numero: Optional[str] = None
    polizza_id: Optional[str] = None
    extra: dict = {}


@router.post("/librerie/modelli/{mid}/invia-whatsapp")
async def invia_modello_whatsapp(mid: str, body: InviaWaModelloBody,
                                 user: dict = Depends(require_user("admin", "collaboratore", "dipendente"))) -> dict:
    """Invia il modello via WhatsApp (Evolution API) al cliente/numero indicato."""
    import uuid as _uuid
    m = await db.template_modelli.find_one({"id": mid}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Modello non trovato")
    ctx = await build_context(body.cliente_id, body.polizza_id, body.extra)
    dest = (body.numero or ctx.get("cliente_cellulare") or "").strip()
    if not dest or dest == "-":
        raise HTTPException(400, "Nessun numero: il cliente non ha cellulare in anagrafica")
    msg = render_text(m.get("corpo") or "", ctx)
    from routes.whatsapp_evo import send_text_via_evolution
    r = await send_text_via_evolution(dest, msg)
    await db.storico_avvisi.insert_one({
        "id": str(_uuid.uuid4()), "canale": "whatsapp",
        "contraente_id": body.cliente_id, "contraente_nome": ctx.get("cliente_nome"),
        "polizza_id": body.polizza_id, "destinatario": dest, "target": dest,
        "oggetto": m.get("nome"), "soggetto": m.get("nome"), "messaggio": msg,
        "tipo": "modello_whatsapp",
        "esito": "inviato" if r.get("ok") else f"errore: {r.get('error')}",
        "sent_at": _now_iso(), "operatore_id": user.get("id"),
        "operatore_nome": user.get("name") or user.get("email"),
    })
    if not r.get("ok"):
        raise HTTPException(400, f"Invio WhatsApp fallito: {r.get('error')}")
    await log_attivita(user, "whatsapp_modello", "modello", mid, f"→ {dest}")
    return {"ok": True, "instance": r.get("instance_name"), "anteprima": msg[:200]}


# =====================================================================
# Comunicazioni unificate (Email / WhatsApp) da anagrafica/polizza/titolo/sinistro
# =====================================================================

async def _resolve_contatti(entita_tipo: str, entita_id: str) -> dict:
    """Risolve cliente_id + polizza_id + titolo_id + sinistro_id + contatti per anagrafica/polizza/titolo/sinistro."""
    cliente_id = None
    polizza_id = None
    titolo_id = None
    sinistro_id = None
    et = (entita_tipo or "").lower()
    if et in ("anagrafica", "cliente"):
        cliente_id = entita_id
    elif et == "polizza":
        polizza_id = entita_id
        p = await db.polizze.find_one({"id": entita_id}, {"_id": 0, "contraente_id": 1})
        cliente_id = (p or {}).get("contraente_id")
    elif et == "titolo":
        titolo_id = entita_id
        t = await db.titoli.find_one({"id": entita_id}, {"_id": 0, "polizza_id": 1})
        polizza_id = (t or {}).get("polizza_id")
        if polizza_id:
            p = await db.polizze.find_one({"id": polizza_id}, {"_id": 0, "contraente_id": 1})
            cliente_id = (p or {}).get("contraente_id")
    elif et == "sinistro":
        sinistro_id = entita_id
        s = await db.sinistri.find_one(
            {"id": entita_id}, {"_id": 0, "polizza_id": 1, "contraente_id": 1})
        polizza_id = (s or {}).get("polizza_id")
        cliente_id = (s or {}).get("contraente_id")
        if not cliente_id and polizza_id:
            p = await db.polizze.find_one({"id": polizza_id}, {"_id": 0, "contraente_id": 1})
            cliente_id = (p or {}).get("contraente_id")
    email = cellulare = nome = ""
    if cliente_id:
        a = await db.anagrafiche.find_one({"id": cliente_id}, {"_id": 0}) or {}
        email = a.get("email") or ""
        cellulare = a.get("cellulare") or a.get("telefono") or ""
        nome = a.get("ragione_sociale") or f"{a.get('nome') or ''} {a.get('cognome') or ''}".strip()
    return {"cliente_id": cliente_id, "polizza_id": polizza_id,
            "titolo_id": titolo_id, "sinistro_id": sinistro_id,
            "email": email, "cellulare": cellulare, "cliente_nome": nome}


class ComunicaRenderBody(BaseModel):
    entita_tipo: str
    entita_id: str
    modello_id: Optional[str] = None


@router.post("/librerie/comunica/contesto")
async def comunica_contesto(body: ComunicaRenderBody, user: dict = Depends(current_user)) -> dict:
    """Ritorna contatti (email/cellulare/nome) e id risolti per l'entità."""
    return await _resolve_contatti(body.entita_tipo, body.entita_id)


@router.post("/librerie/comunica/render")
async def comunica_render(body: ComunicaRenderBody, user: dict = Depends(current_user)) -> dict:
    """Compila un modello (oggetto+corpo) coi dati reali dell'entità."""
    c = await _resolve_contatti(body.entita_tipo, body.entita_id)
    out = {**c, "oggetto": "", "corpo": ""}
    if body.modello_id:
        m = await db.template_modelli.find_one({"id": body.modello_id}, {"_id": 0})
        if not m:
            raise HTTPException(404, "Modello non trovato")
        ctx = await build_context(c.get("cliente_id"), c.get("polizza_id"),
                                  operatore_id=user.get("id"),
                                  titolo_id=c.get("titolo_id"), sinistro_id=c.get("sinistro_id"))
        out["oggetto"] = render_text(m.get("oggetto") or m.get("nome") or "", ctx)
        out["corpo"] = render_text(m.get("corpo") or "", ctx)
    return out


class ComunicaInviaBody(BaseModel):
    entita_tipo: str
    entita_id: str
    canale: str  # "email" | "whatsapp"
    destinatario: Optional[str] = None
    oggetto: Optional[str] = None
    corpo: str = ""


@router.post("/librerie/comunica/invia")
async def comunica_invia(body: ComunicaInviaBody, user: dict = Depends(current_user)) -> dict:
    """Invia realmente Email o WhatsApp al cliente usando i canali configurati."""
    import uuid as _uuid
    c = await _resolve_contatti(body.entita_tipo, body.entita_id)
    canale = (body.canale or "").lower()
    if not (body.corpo or "").strip():
        raise HTTPException(400, "Il messaggio è vuoto")

    if canale == "email":
        dest = (body.destinatario or c.get("email") or "").strip()
        if not dest or dest == "-":
            raise HTTPException(400, "Nessuna email del destinatario")
        from notification_helpers import send_email
        html = body.corpo if "<" in body.corpo else body.corpo.replace("\n", "<br>")
        r = await send_email(dest, body.oggetto or "Comunicazione", body.corpo, html=html)
    elif canale == "whatsapp":
        dest = (body.destinatario or c.get("cellulare") or "").strip()
        if not dest or dest == "-":
            raise HTTPException(400, "Nessun cellulare del destinatario")
        from notification_helpers import send_whatsapp_message
        r = await send_whatsapp_message(dest, body.corpo)
    else:
        raise HTTPException(400, "Canale non supportato")

    await db.storico_avvisi.insert_one({
        "id": str(_uuid.uuid4()), "canale": canale,
        "contraente_id": c.get("cliente_id"), "contraente_nome": c.get("cliente_nome"),
        "polizza_id": c.get("polizza_id"), "destinatario": dest, "target": dest,
        "oggetto": body.oggetto, "soggetto": body.oggetto,
        "messaggio": body.corpo[:4000], "tipo": f"comunica_{canale}",
        "esito": "inviato" if r.get("ok") else f"errore: {r.get('error')}",
        "sent_at": _now_iso(), "operatore_id": user.get("id"),
        "operatore_nome": user.get("name") or user.get("email"),
    })
    if not r.get("ok"):
        raise HTTPException(400, r.get("error") or f"Invio {canale} fallito")
    await log_attivita(user, f"comunica_{canale}", body.entita_tipo, body.entita_id, dest)
    return {"ok": True, "canale": canale, "destinatario": dest}
