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
    anagrafica_id: Optional[str] = None
    # Dati collaboratore (per ruoli collaboratore/dipendente)
    codice_fiscale: Optional[str] = None
    partita_iva: Optional[str] = None
    iban: Optional[str] = None
    indirizzo: Optional[str] = None
    telefono: Optional[str] = None
    # Settaggi provvigioni e ritenute
    perc_provvigione_default: float = 0.0  # % provvigione standard sui titoli
    perc_ritenuta_acconto: float = 0.0     # % ritenuta d'acconto su provvigione pagata
    perc_inps_inarcassa: float = 0.0       # % contributi previdenziali
    note_fiscali: Optional[str] = None
    attivo: bool = True
    # Documenti collaboratore (URL di storage)
    firma_digitale_url: Optional[str] = None
    carta_identita_url: Optional[str] = None
    casellario_url: Optional[str] = None
    carichi_pendenti_url: Optional[str] = None
    documento_iban_url: Optional[str] = None
    # Corsi completati: [{titolo, ente, data_scadenza, url_attestato}]
    corsi: List[dict] = Field(default_factory=list)
    # Note interne (visibile solo admin)
    note_interne: Optional[str] = None


class PagamentoProvvigioni(BaseDoc):
    collaboratore_id: str
    collaboratore_nome: str
    periodo_dal: str  # YYYY-MM-DD
    periodo_al: str
    provvigioni_lorde: float = 0.0
    ritenuta_acconto: float = 0.0
    contributi: float = 0.0
    netto_pagato: float = 0.0
    conto_cassa_id: Optional[str] = None
    mezzo_pagamento: Optional[str] = "bonifico"
    data_pagamento: str
    movimento_id: Optional[str] = None
    titoli_ids: List[str] = Field(default_factory=list)
    note: Optional[str] = None


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
    ragione_sociale: str  # auto-composta da nome+cognome se persona fisica
    nome: Optional[str] = None
    cognome: Optional[str] = None
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
    lat: Optional[float] = None
    lng: Optional[float] = None
    indirizzo_geocoded: Optional[str] = None
    professione: Optional[str] = None
    stato_civile: Optional[str] = None
    titolo_studio: Optional[str] = None
    # dati previdenziali (per calcolo INPS automatico)
    tipo_lavoratore: Optional[Literal["dipendente", "autonomo", "parasubordinato", "pensionato", "altro"]] = None
    reddito_annuo_lordo: Optional[float] = None
    numero_figli: int = 0
    numero_figli_a_carico: int = 0
    data_inizio_contribuzione: Optional[str] = None
    settimane_contributive: Optional[int] = None
    note: Optional[str] = None
    # albero genealogico
    parente_di: List[dict] = Field(default_factory=list)  # [{"anagrafica_id":..., "relazione":"figlio|coniuge|..."}]
    # consensi privacy
    consenso_privacy: bool = False
    data_consenso_privacy: Optional[str] = None
    consenso_commerciale: bool = False
    consenso_profilazione: bool = False
    # tag automatici/manuali per segmentazione e newsletter
    tags: List[str] = Field(default_factory=list)
    # collegamenti esterni dall'import
    id_anagrafica_exp: Optional[str] = None
    compagnia_id: Optional[str] = None
    collaboratore_id: Optional[str] = None  # operatore/sub-agente assegnato
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
    collaboratore_id: Optional[str] = None
    # estensione campi (richiesta utente - dettaglio polizza completo)
    sostituisce_polizza: Optional[str] = None
    presa_in_carico: Optional[str] = None
    prossima_quietanza: Optional[str] = None
    scadenza_copertura: Optional[str] = None
    termini_mora_giorni: Optional[int] = 15
    termini_disdetta_giorni: Optional[int] = 0
    tacito_rinnovo: bool = False
    mandato: Optional[str] = None
    iter_status: Optional[str] = None
    documenti_inviati: bool = False
    oggetto_assicurato: Optional[str] = None
    assicurato_oggetto_nome: Optional[str] = None  # es. "BLUE DREAM SPA"
    # dati veicolo (per polizze RCA)
    veicolo_marca: Optional[str] = None
    veicolo_modello: Optional[str] = None
    veicolo_tipo: Optional[str] = None
    veicolo_alimentazione: Optional[str] = None
    veicolo_uso: Optional[str] = None
    veicolo_data_immatricolazione: Optional[str] = None
    veicolo_cilindrata: Optional[int] = None
    veicolo_cv_fiscali: Optional[int] = None
    veicolo_kw: Optional[float] = None
    veicolo_quintali: Optional[float] = None
    veicolo_posti: Optional[int] = None
    veicolo_gancio_traino: bool = False
    veicolo_targa_rimorchio: Optional[str] = None
    # dati polizza/contratto
    tipo_tariffa: Optional[str] = None
    bm_provenienza: Optional[str] = None
    bm_assegnata: Optional[str] = None
    bm_assegnata_cu: Optional[str] = None
    pejus: Optional[float] = None
    franchigia: float = 0.0
    valore_veicolo: float = 0.0
    valore_residuo_veicolo: float = 0.0
    valore_accessori: float = 0.0
    guida_esperta: bool = False
    guida_esclusiva: bool = False
    rinuncia_rivalsa: bool = False
    intestatario: Optional[str] = None
    provincia_intestatario: Optional[str] = None
    massimali: Optional[str] = None
    # garanzie e premi (struttura semplice JSON)
    garanzie: List[dict] = Field(default_factory=list)
    # [{garanzia, netto, accessori, imposte, ssn, lordo}]
    addizionali: List[dict] = Field(default_factory=list)
    diritti: float = 0.0
    # provvigioni dettagliate
    provv_struttura: float = 0.0
    provvigioni_operatori: List[dict] = Field(default_factory=list)
    # [{operatore_id, operatore_nome, provvigione, provvigione_addizionali}]
    note_interne: Optional[str] = None
    da_restituire: Optional[str] = None
    caratteristiche: Optional[str] = None
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
    importo_pagato: Optional[float] = None       # se diverso dal lordo → sconto applicato
    sconto_applicato: float = 0.0                # importo dello sconto (positivo)
    motivo_sconto: Optional[str] = None
    titolo_coperto: bool = False
    data_copertura: Optional[str] = None
    data_competenza: Optional[str] = None
    data_contabile: Optional[str] = None
    scadenza_mora: Optional[str] = None
    mezzo_pagamento: Optional[str] = None
    conto_cassa_id: Optional[str] = None
    collaboratore_id: Optional[str] = None  # operatore/sub-agente assegnato
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
    collaboratore_id: Optional[str] = None  # operatore/sub-agente assegnato
    id_sinistro_exp: Optional[str] = None
    fonte: Literal["manuale", "import_ania"] = "manuale"


# =============== CONTABILITA ===============
MovimentoTipo = Literal["entrata", "uscita"]
MovimentoCategoria = Literal[
    "incasso_premio", "pagamento_compagnia", "provvigioni",
    "rimborso_cliente", "spese_amministrative", "anticipo", "giroconto",
    "sconto_cliente", "altro",
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
    conto_cassa_id: Optional[str] = None
    mezzo_pagamento: Optional[str] = None
    numero_documento: Optional[str] = None
    provvigioni: float = 0.0
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


# =============== LIBRERIE / ANAGRAFICHE DI SERVIZIO ===============
class Banca(BaseDoc):
    nome: str
    codice_abi: Optional[str] = None
    iban_agenzia: Optional[str] = None
    referente: Optional[str] = None
    note: Optional[str] = None
    attiva: bool = True


class ContoCassa(BaseDoc):
    """Conto cassa / canale incasso (es. CONTANTI, ASSEGNI, BPER SONDRIO, RID DIREZIONE)."""
    nome: str
    tipo: Literal["cassa", "banca", "carta", "rid", "online", "altro"] = "banca"
    banca_id: Optional[str] = None
    iban: Optional[str] = None
    saldo_iniziale: float = 0.0
    descrizione: Optional[str] = None
    attivo: bool = True
    ordine: int = 0


class ProdottoLibreria(BaseDoc):
    """Prodotto assicurativo (catalogo interno per dropdown polizze)."""
    nome: str
    compagnia_id: Optional[str] = None
    ramo: Optional[str] = None
    descrizione: Optional[str] = None
    attivo: bool = True


class RamoLibreria(BaseDoc):
    """Ramo assicurativo (es. RCA, INCENDIO, VITA)."""
    codice: str
    nome: str
    descrizione: Optional[str] = None
    attivo: bool = True


# =============== ALLEGATI / DOCUMENTI ===============
class Allegato(BaseDoc):
    """Allegato collegato a una entità (anagrafica/polizza/sinistro/cliente/corso)."""
    entita_tipo: Literal["anagrafica", "polizza", "sinistro", "compagnia", "corso", "movimento"]
    entita_id: str
    nome_file: str
    storage_path: str
    content_type: str
    size: int = 0
    descrizione: Optional[str] = None
    autore_id: Optional[str] = None
    is_deleted: bool = False


# =============== DIARIO CLIENTE ===============
class DiarioVoce(BaseDoc):
    anagrafica_id: str
    data_evento: str  # YYYY-MM-DD
    tipo: Literal["telefonata", "incontro", "email", "whatsapp", "chat", "documento", "nota", "altro"] = "nota"
    titolo: str
    descrizione: Optional[str] = None
    autore_id: Optional[str] = None
    autore_nome: Optional[str] = None


# =============== CHAT INTERNA ===============
class MessaggioChat(BaseDoc):
    mittente_id: str
    mittente_nome: str
    destinatario_id: str
    destinatario_nome: str
    testo: str
    allegato_id: Optional[str] = None
    allegato_nome: Optional[str] = None
    allegato_content_type: Optional[str] = None
    letto: bool = False
    letto_at: Optional[str] = None


# =============== CORSI / FORMAZIONE ===============
class Corso(BaseDoc):
    titolo: str
    descrizione: Optional[str] = None
    categoria: Optional[str] = None
    durata_minuti: int = 0
    # link video esterno (YouTube/Vimeo) o storage_path se caricato
    video_url: Optional[str] = None
    video_storage_path: Optional[str] = None
    thumbnail_url: Optional[str] = None
    visibile_ruoli: List[str] = Field(default_factory=lambda: ["dipendente", "collaboratore"])
    visibile_utenti: List[str] = Field(default_factory=list)  # user_ids specifici
    autore_id: Optional[str] = None
    pubblicato: bool = True


class ProgressoCorso(BaseDoc):
    corso_id: str
    utente_id: str
    secondi_visti: int = 0
    durata_totale_sec: int = 0
    percentuale: float = 0.0  # 0-100
    completato: bool = False
    ultima_posizione_sec: int = 0
    ultima_visualizzazione: str = Field(default_factory=_now_iso)


# =============== AZIENDA (DATI INTESTAZIONE / STAMPE) ===============
class AziendaConfig(BaseDoc):
    """Dati dell'agenzia: ragione sociale, P.IVA, indirizzo, contatti, logo (singleton)."""
    ragione_sociale: str = ""
    forma_giuridica: Optional[str] = None  # SRL, SAS, SNC, ditta individuale...
    partita_iva: Optional[str] = None
    codice_fiscale: Optional[str] = None
    rui: Optional[str] = None              # numero iscrizione RUI/IVASS
    rui_sezione: Optional[str] = None
    data_iscrizione_rui: Optional[str] = None
    indirizzo: Optional[str] = None
    comune: Optional[str] = None
    provincia: Optional[str] = None
    cap: Optional[str] = None
    nazione: str = "ITALIA"
    telefono: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    pec: Optional[str] = None
    sito_web: Optional[str] = None
    iban: Optional[str] = None
    banca: Optional[str] = None
    capitale_sociale: Optional[str] = None
    rea: Optional[str] = None
    logo_url: Optional[str] = None         # URL logo per stampe
    logo_storage_path: Optional[str] = None
    note_footer_stampe: Optional[str] = None


# =============== SCHEMA / SISTEMA PROVVIGIONALE ===============
class SchemaProvvigionale(BaseDoc):
    """Regola di calcolo provvigione: applicata per collaboratore + (compagnia/ramo opzionali).

    Risoluzione gerarchica (la più specifica vince):
      1. collaboratore_id + compagnia_id + ramo
      2. collaboratore_id + compagnia_id
      3. collaboratore_id + ramo
      4. collaboratore_id
      5. compagnia_id + ramo            (regola agenzia)
      6. compagnia_id                   (regola agenzia)
      7. ramo                           (regola agenzia)
      8. default (collaboratore_id=null, compagnia_id=null, ramo=null)
    """
    nome: str
    collaboratore_id: Optional[str] = None
    compagnia_id: Optional[str] = None
    ramo: Optional[str] = None
    # percentuale che spetta al collaboratore sulla PROVVIGIONE INCASSATA dalla polizza
    percentuale_collaboratore: float = 0.0
    # percentuale di provvigione applicata sul PREMIO LORDO (se l'agenzia non ha già il dato)
    percentuale_su_premio: float = 0.0
    descrizione: Optional[str] = None
    attivo: bool = True


class ImportLog(BaseDoc):
    utente_id: Optional[str] = None
    nome_file: str
    record_types_processati: dict = Field(default_factory=dict)
    anagrafiche_create: int = 0
    anagrafiche_aggiornate: int = 0
    polizze_create: int = 0
    polizze_aggiornate: int = 0
    titoli_creati: int = 0
    sinistri_creati: int = 0
    errori: List[str] = Field(default_factory=list)
    durata_ms: int = 0
    stato: Literal["completato", "errore", "in_corso"] = "in_corso"


# =============== CALENDARIO ===============
class EventoCalendario(BaseDoc):
    titolo: str
    descrizione: Optional[str] = None
    inizio: str                  # YYYY-MM-DDTHH:MM
    fine: Optional[str] = None
    tutto_il_giorno: bool = False
    luogo: Optional[str] = None
    tipo: Literal[
        "appuntamento", "scadenza_polizza", "scadenza_titolo",
        "sinistro", "promemoria", "altro"
    ] = "appuntamento"
    colore: Optional[str] = None
    # destinatari / visibilità
    operatore_id: Optional[str] = None       # collaboratore principale (proprietario evento)
    partecipanti_user_ids: List[str] = Field(default_factory=list)
    anagrafica_id: Optional[str] = None
    polizza_id: Optional[str] = None
    sinistro_id: Optional[str] = None
    # external sync (Google Calendar / Outlook)
    google_event_id: Optional[str] = None
    outlook_event_id: Optional[str] = None
    stato: Literal["confermato", "tentativo", "annullato"] = "confermato"
