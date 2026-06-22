"""Pydantic models for all collections.

All documents use a string `id` (uuid4). datetime is stored as ISO string.
"""
from datetime import datetime, timezone
from typing import Optional, List, Literal, Any
from pydantic import BaseModel, Field, ConfigDict, EmailStr
import uuid


def _uid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseDoc(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    id: str = Field(default_factory=_uid)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


# =============== USERS ===============
Role = Literal["admin", "collaboratore", "dipendente", "cliente"]


class UserPublic(BaseDoc):
    email: EmailStr
    name: str
    role: Role
    anagrafica_id: Optional[str] = None  # se il ruolo è "cliente", collega all'anagrafica


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Role = "dipendente"
    anagrafica_id: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# =============== COMPAGNIE ===============
class Compagnia(BaseDoc):
    codice: str  # codice compagnia ANIA o interno
    ragione_sociale: str
    descrizione: Optional[str] = None
    sito_web: Optional[str] = None
    referente: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    attiva: bool = True


# =============== ANAGRAFICHE ===============
class Anagrafica(BaseDoc):
    tipo: Literal["persona_fisica", "persona_giuridica"] = "persona_fisica"
    ragione_sociale: str  # cognome nome o nome azienda
    codice_fiscale: Optional[str] = None
    partita_iva: Optional[str] = None
    data_nascita: Optional[str] = None  # YYYY-MM-DD
    comune_nascita: Optional[str] = None
    provincia_nascita: Optional[str] = None
    sesso: Optional[Literal["M", "F"]] = None
    indirizzo: Optional[str] = None
    comune: Optional[str] = None
    provincia: Optional[str] = None
    cap: Optional[str] = None
    nazione: Optional[str] = "ITALIA"
    telefono: Optional[str] = None
    cellulare: Optional[str] = None
    email: Optional[str] = None
    iban: Optional[str] = None
    professione: Optional[str] = None
    stato_civile: Optional[str] = None
    titolo_studio: Optional[str] = None
    note: Optional[str] = None
    # albero genealogico
    parente_di: List[dict] = Field(default_factory=list)  # [{"anagrafica_id":..., "relazione":"figlio|coniuge|..."}]
    # consensi privacy
    consenso_privacy: bool = False
    data_consenso_privacy: Optional[str] = None
    consenso_commerciale: bool = False
    consenso_profilazione: bool = False
    # collegamenti esterni dall'import
    id_anagrafica_exp: Optional[str] = None
    compagnia_id: Optional[str] = None
    fonte: Literal["manuale", "import_ania"] = "manuale"


# =============== POLIZZE ===============
PolizzaStato = Literal["attiva", "sospesa", "annullata", "scaduta", "in_emissione"]


class Polizza(BaseDoc):
    numero_polizza: str
    compagnia_id: str
    contraente_id: str  # anagrafica_id del contraente
    assicurato_ids: List[str] = Field(default_factory=list)  # anagrafica_id assicurati
    ramo: str  # RCA, INCENDIO, VITA, ecc.
    prodotto: Optional[str] = None
    stato: PolizzaStato = "attiva"
    effetto: str  # YYYY-MM-DD
    scadenza: str  # YYYY-MM-DD
    frazionamento: Literal["annuale", "semestrale", "quadrimestrale", "trimestrale", "mensile", "unica"] = "annuale"
    premio_lordo: float = 0.0
    premio_netto: float = 0.0
    provvigioni: float = 0.0
    note: Optional[str] = None
    targa: Optional[str] = None
    # collegamenti import
    id_polizza_exp: Optional[str] = None
    fonte: Literal["manuale", "import_ania"] = "manuale"


# =============== TITOLI (premi/quietanze) ===============
TitoloStato = Literal["incassato", "da_incassare", "insoluto", "stornato"]


class Titolo(BaseDoc):
    polizza_id: str
    numero_titolo: Optional[str] = None
    tipo: Literal["nuova", "rinnovo", "appendice", "regolazione", "storno"] = "rinnovo"
    effetto: str
    scadenza: str
    stato: TitoloStato = "da_incassare"
    importo_lordo: float = 0.0
    importo_netto: float = 0.0
    imposte: float = 0.0
    provvigioni: float = 0.0
    data_incasso: Optional[str] = None
    mezzo_pagamento: Optional[str] = None
    id_titolo_exp: Optional[str] = None
    fonte: Literal["manuale", "import_ania"] = "manuale"


# =============== SINISTRI ===============
SinistroStato = Literal["aperto", "in_istruttoria", "liquidato", "chiuso_senza_seguito", "respinto"]


class Sinistro(BaseDoc):
    numero_sinistro: str
    polizza_id: str
    compagnia_id: str
    contraente_id: str
    data_avvenimento: str
    data_denuncia: str
    luogo: Optional[str] = None
    ramo: Optional[str] = None
    stato: SinistroStato = "aperto"
    descrizione: Optional[str] = None
    riserva: float = 0.0
    liquidazione: float = 0.0
    danneggiati: List[dict] = Field(default_factory=list)
    id_sinistro_exp: Optional[str] = None
    fonte: Literal["manuale", "import_ania"] = "manuale"


# =============== CONTABILITA ===============
MovimentoTipo = Literal["entrata", "uscita"]
MovimentoCategoria = Literal[
    "incasso_premio", "pagamento_compagnia", "provvigioni",
    "rimborso_cliente", "spese_amministrative", "anticipo", "altro"
]


class MovimentoContabile(BaseDoc):
    data_movimento: str  # YYYY-MM-DD
    data_registrazione: str = Field(default_factory=lambda: _now_iso()[:10])
    tipo: MovimentoTipo
    categoria: MovimentoCategoria
    importo: float
    descrizione: str
    anagrafica_id: Optional[str] = None
    polizza_id: Optional[str] = None
    titolo_id: Optional[str] = None
    compagnia_id: Optional[str] = None
    mezzo_pagamento: Optional[str] = None
    numero_documento: Optional[str] = None
    note: Optional[str] = None


# =============== INTERVISTA CLIENTE ===============
class Intervista(BaseDoc):
    anagrafica_id: str
    data_intervista: str = Field(default_factory=lambda: _now_iso()[:10])
    operatore_id: Optional[str] = None
    # dati strutturati
    situazione_familiare: dict = Field(default_factory=dict)
    situazione_lavorativa: dict = Field(default_factory=dict)
    situazione_patrimoniale: dict = Field(default_factory=dict)
    coperture_attuali: dict = Field(default_factory=dict)
    obiettivi: dict = Field(default_factory=dict)
    note: Optional[str] = None


# =============== CALCOLO PENSIONI INPS ===============
class CalcoloPensione(BaseDoc):
    anagrafica_id: Optional[str] = None
    tipo_pensione: Literal["invalidita", "inabilita", "superstite"]
    data_inizio_contribuzione: str  # YYYY-MM-DD
    settimane_contributive: int = 0
    retribuzione_media_annua: float = 0.0
    eta_richiedente: int = 0
    percentuale_invalidita: Optional[float] = None
    numero_familiari: int = 0
    # risultato
    pensione_lorda_mensile: float = 0.0
    pensione_lorda_annua: float = 0.0
    pensione_netta_stimata: float = 0.0
    coefficiente_applicato: float = 0.0
    metodologia: Optional[str] = None
    dettaglio: dict = Field(default_factory=dict)


# =============== EMAIL PIPELINE ===============
EmailStato = Literal["bozza", "in_coda", "inviata", "errore"]


class EmailMessaggio(BaseDoc):
    destinatario_anagrafica_id: Optional[str] = None
    destinatario_email: str
    oggetto: str
    corpo: str
    template: Optional[str] = None
    stato: EmailStato = "bozza"
    data_invio: Optional[str] = None
    errore: Optional[str] = None
    polizza_id: Optional[str] = None
    autore_id: Optional[str] = None


# =============== ACTIVITY LOG ===============
class AttivitaLog(BaseDoc):
    utente_id: Optional[str] = None
    utente_email: Optional[str] = None
    azione: str  # e.g. "create", "update", "delete", "login", "import", "calc_pensione"
    entita: str  # e.g. "anagrafica", "polizza", "sinistro"
    entita_id: Optional[str] = None
    descrizione: Optional[str] = None
    payload: Optional[dict] = None


# =============== IMPORT LOG ===============
class ImportLog(BaseDoc):
    utente_id: Optional[str] = None
    nome_file: str
    record_types_processati: dict = Field(default_factory=dict)  # {"rec10": 12, ...}
    anagrafiche_create: int = 0
    anagrafiche_aggiornate: int = 0
    polizze_create: int = 0
    polizze_aggiornate: int = 0
    titoli_creati: int = 0
    sinistri_creati: int = 0
    errori: List[str] = Field(default_factory=list)
    durata_ms: int = 0
    stato: Literal["completato", "errore", "in_corso"] = "in_corso"
