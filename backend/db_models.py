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
    # Alias email aziendali per smistamento posta in arrivo (es.
    # "alessia.balzarolo@schiantarelli.it"). Possono includere alias di
    # reparto condivisi (es. "sinistri@…" su più collaboratori).
    email_aliases: List[str] = Field(default_factory=list)
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
    voci_manuali_ids: List[str] = Field(default_factory=list)
    note: Optional[str] = None


class VoceManualeCollab(BaseDoc):
    """Voce manuale (bonus / trattenuta / acconto / nota di credito) sull'estratto conto collaboratore.

    importo positivo = aumenta il dovuto al collaboratore (es. bonus)
    importo negativo = riduce il dovuto (es. acconto già dato, storno)
    """
    collaboratore_id: str
    data: str  # YYYY-MM-DD
    causale: str
    importo: float  # può essere negativo
    note: Optional[str] = None
    pagata: bool = False
    pagamento_id: Optional[str] = None  # set when included in a payment
    # se generata automaticamente da una regola ricorsiva, riferimento alla regola
    ricorsiva_id: Optional[str] = None


class VoceRicorsivaCollab(BaseDoc):
    """Regola di voce ricorsiva per un collaboratore (o per TUTTI i collaboratori).

    Ogni mese/anno la regola genera una `VoceManualeCollab` corrispondente, che
    poi può essere modificata/eliminata individualmente o pagata insieme alle
    provvigioni del periodo.
    """
    # __all__ per applicare la regola a TUTTI i collaboratori attivi
    collaboratore_id: str
    causale: str
    importo: float  # positivo = bonus, negativo = trattenuta
    periodicita: Literal["mensile", "annuale"] = "mensile"
    giorno_mese: int = 1  # 1..28 (mensile) — usato anche per annuale come "giorno"
    mese_anno: Optional[int] = None  # 1..12 — solo per "annuale"
    data_inizio: str  # YYYY-MM-DD, prima generazione possibile
    data_fine: Optional[str] = None  # YYYY-MM-DD, dopo questa data smette
    note: Optional[str] = None
    attiva: bool = True
    created_by: Optional[str] = None


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
    # Gestione contabile prima nota:
    # - True (default): "tratteniamo le provvigioni" → saldo = premio - provvigioni
    # - False: dobbiamo versare il premio intero alla compagnia, le provvigioni le
    #          riceveremo separatamente → saldo = premio intero
    trattiene_provvigioni: bool = True


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
    consenso_dati_particolari: bool = False       # punto 1 - categorie particolari
    consenso_commerciale: bool = False             # punti 2a/2b/2c - marketing diretto
    consenso_comunicazione_terzi: bool = False     # punto 2d - comunicazione dati a terzi
    consenso_profilazione: bool = False            # punto 2e - profilazione
    # documenti allegati alla scheda cliente (URL storage)
    documenti: dict = Field(default_factory=dict)
    # struttura: {"carta_identita": {"url":..., "nome_file":..., "data_caricamento":..., "scadenza":...}, ...}
    # tipi supportati: carta_identita, patente, passaporto, codice_fiscale, privacy_firmata,
    #                  tessera_sanitaria, visura_camerale, estratto_contributivo, altro
    firma_cliente_url: Optional[str] = None   # firma digitale tracciata su canvas
    privacy_firmata_url: Optional[str] = None # PDF privacy firmato
    privacy_firmata_il: Optional[str] = None
    # preferenza pagamento del cliente (default per nuovi titoli)
    preferenza_pagamento: Optional[Literal["contanti", "bonifico", "assegno", "pos", "rid", "altro"]] = None
    ultimo_mezzo_pagamento: Optional[str] = None
    ultimo_mezzo_pagamento_data: Optional[str] = None
    # tipologia lavoratore (per tagging marketing + INPS)
    tipologia_lavoratore: Optional[Literal[
        "dipendente", "autonomo", "professionista", "imprenditore",
        "pensionato", "disoccupato", "studente", "casalinga", "altro"
    ]] = None
    datore_lavoro: Optional[str] = None
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
    premio_tasse: float = 0.0      # imposte assicurative
    premio_imposte: float = 0.0    # altre imposte/oneri
    premio_ssn: float = 0.0        # contributo SSN
    provvigioni: float = 0.0
    note: Optional[str] = None
    targa: Optional[str] = None
    collaboratore_id: Optional[str] = None
    operatore_ania_codice: Optional[str] = None  # codice operatore da importazione ANIA (per mapping)
    # Codici "originali" provenienti dal flusso esterno, conservati per back-fill mapping
    compagnia_codice_exp: Optional[str] = None
    ramo_originale: Optional[str] = None
    prodotto_originale: Optional[str] = None
    # Metodo di pagamento preferito su questa polizza (può differire da quello dell'anagrafica).
    # Se vuoto, viene auto-aggiornato con il mezzo usato all'ultimo incasso.
    mezzo_pagamento_preferito: Optional[Literal["contanti", "bonifico", "assegno", "pos", "rid", "altro"]] = None
    ultimo_mezzo_pagamento: Optional[str] = None
    ultimo_mezzo_pagamento_data: Optional[str] = None
    is_libro_matricola: bool = False  # se True → polizza con applicazioni veicoli (libro matricola RCA)
    # estensione campi (richiesta utente - dettaglio polizza completo)
    sostituisce_polizza: Optional[str] = None
    sostituita_da_polizza_id: Optional[str] = None  # backlink dopo sostituzione
    data_annullamento: Optional[str] = None
    motivo_annullamento: Optional[str] = None
    data_sospensione: Optional[str] = None
    riattivazione_prevista: Optional[str] = None
    coassicurazione: bool = False
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
    veicolo_settore: Optional[str] = None   # settore RCA (es. autocarri, autovetture)
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
    tipo: Literal["nuova", "rinnovo", "appendice", "regolazione", "storno", "quietanza", "sostituzione"] = "rinnovo"
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
    data_emissione: Optional[str] = None
    ora_effetto: Optional[str] = None
    data_competenza: Optional[str] = None
    data_contabile: Optional[str] = None
    scadenza_mora: Optional[str] = None
    mezzo_pagamento: Optional[str] = None
    conto_cassa_id: Optional[str] = None
    collaboratore_id: Optional[str] = None  # operatore/sub-agente assegnato
    id_titolo_exp: Optional[str] = None
    pagamento_in_direzione: bool = False   # premio pagato direttamente in compagnia (no cassa)
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
    # Split brogliaccio per incassi premio: quota_provvigione = parte agenzia,
    # quota_saldo = parte da versare alla compagnia. Calcolato automaticamente al
    # momento dell'incasso (provvigione del titolo) ma override manuale possibile.
    quota_provvigione: float = 0.0
    quota_saldo: float = 0.0
    quota_credito: float = 0.0  # quando il movimento rappresenta una rata a credito
    quota_spesa: float = 0.0    # spese specifiche (es. bolli, oneri)
    quota_sconto: float = 0.0   # eventuale sconto applicato
    note: Optional[str] = None
    # chiusura giornaliera prima nota
    chiusura_id: Optional[str] = None


class ChiusuraGiorno(BaseDoc):
    """Snapshot di una giornata di prima nota chiusa.

    Una volta chiusa, i movimenti del giorno sono congelati (no modifiche/cancellazioni)
    e il PDF brogliaccio è archiviato come storage. Opzionalmente inviata via email
    al commercialista.
    """
    data: str  # YYYY-MM-DD - data del brogliaccio chiuso
    closed_by: Optional[str] = None  # user_id che ha chiuso
    closed_by_name: Optional[str] = None
    riepilogo: dict = Field(default_factory=dict)
    # struttura riepilogo: {totale, provv, saldo, crediti, spese, sconti,
    #   per_conto: {conto_id: importo}, saldi_conti_finali: {conto_id: saldo}}
    pdf_storage_path: Optional[str] = None
    pdf_url: Optional[str] = None
    email_inviata_a: Optional[str] = None
    email_inviata_at: Optional[str] = None
    email_errore: Optional[str] = None
    riaperta_at: Optional[str] = None
    riaperta_by: Optional[str] = None
    riaperta_motivo: Optional[str] = None


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
    """Conto cassa / canale incasso (es. CONTANTI, ASSEGNI, BPER SONDRIO, RID DIREZIONE).

    Voci usate come "Conti Deposito" nella nuova architettura `TipoPagamento`.
    """
    nome: str
    tipo: Literal["cassa", "banca", "carta", "rid", "online", "altro"] = "banca"
    banca_id: Optional[str] = None
    iban: Optional[str] = None
    saldo_iniziale: float = 0.0
    descrizione: Optional[str] = None
    attivo: bool = True
    ordine: int = 0
    # Flag operativi richiesti dalla "libreriaconti deposito"
    # - nascondi_prima_nota: se True il conto NON compare più nei dropdown della
    #   Prima Nota (utile per conti dismessi senza eliminarli).
    # - escludi_da_liquidita: se True il conto è ignorato nel calcolo della
    #   liquidità (immediata e postera).
    nascondi_prima_nota: bool = False
    escludi_da_liquidita: bool = False


class TipoPagamento(BaseDoc):
    """Voce della libreria UNIFICATA "Tipi pagamento" — combinazione di una
    `MezzoPagamento` (modalità: bonifico/assegno/contanti/POS/RID) con un
    `ContoCassa` (conto deposito: banca specifica, cassa, direzione).

    È l'UNICO dropdown mostrato in:
    Titoli (Incasso/Copertura), Movimenti Prima Nota, Estratti Conto
    Compagnie/Collaboratori, Giroconti.

    `label` viene auto-generato dalla combinazione (es. "BONIFICO BPER SONDRIO")
    ma è modificabile manualmente.
    """
    label: str                          # testo visualizzato nel dropdown
    modalita_codice: str                # FK soft → MezzoPagamento.codice
    conto_id: Optional[str] = None      # FK → ContoCassa.id (None per voci speciali tipo "AGOS", "Altro")
    ordine: int = 0
    attivo: bool = True
    note: Optional[str] = None


class EmailInbox(BaseDoc):
    """Email ricevute via IMAP (cassetta aziendale principale).

    Il poller le smista automaticamente in base agli alias dei collaboratori
    (lista `User.email_aliases`):
      - se almeno un alias di un collaboratore compare nei destinatari
        (`To:` + `Cc:`) → categoria='personale', `smistato_a` contiene gli
        id dei collaboratori interessati;
      - se più collaboratori condividono uno stesso alias (es. `sinistri@`)
        ricevono tutti la stessa email;
      - se nessun alias matcha → categoria='condivisa', visibile a tutti.

    Inoltre, se il mittente è registrato come anagrafica, viene popolato
    `anagrafica_id` per visualizzazione nel diario cliente.
    """
    message_id: Optional[str] = None
    uid: Optional[str] = None
    folder: str = "INBOX"
    from_address: str
    from_name: Optional[str] = None
    to_addresses: list[str] = []
    cc_addresses: list[str] = []
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    date: Optional[str] = None
    has_attachments: bool = False
    attachments: list[dict] = []   # [{filename, content_type, size, storage_path}]
    # Smistamento
    categoria: str = "condivisa"   # "condivisa" | "personale"
    smistato_a: list[str] = []     # user_ids
    letta_da: list[str] = []       # user_ids che hanno letto
    # Collegamento anagrafica
    anagrafica_id: Optional[str] = None
    polizza_id: Optional[str] = None


class DiarioCliente(BaseDoc):
    """Voce del diario CLIENTE (anagrafica). Già usata dal sistema per le
    interazioni manuali; ora viene popolata anche automaticamente da:
      • email ricevute via IMAP da indirizzi conosciuti
      • email inviate (da storico_avvisi)
    """
    anagrafica_id: str
    tipo: str = "nota"   # nota|email_in|email_out|sms|whatsapp|chiamata|incontro
    titolo: str
    contenuto: Optional[str] = None
    autore_id: Optional[str] = None
    email_inbox_id: Optional[str] = None


class DiarioNota(BaseDoc):
    user_id: str
    titolo: str
    contenuto: Optional[str] = None
    anagrafica_id: Optional[str] = None
    polizza_id: Optional[str] = None
    tags: list[str] = []


class LetteraAbbuono(BaseDoc):
    """Lettera di abbuono generata quando viene applicato uno sconto in incasso.

    Contiene PDF non firmato (creato al volo) + slot per firme digitali
    (operatore + cliente). Quando entrambe le firme sono presenti, si rigenera
    il PDF "signed" e lo si salva su storage.
    """
    titolo_id: str
    polizza_id: Optional[str] = None
    anagrafica_id: Optional[str] = None
    compagnia_id: Optional[str] = None
    importo_lordo: float = 0.0
    importo_pagato: float = 0.0
    importo_sconto: float = 0.0
    motivo_sconto: Optional[str] = None
    data_incasso: Optional[str] = None
    # Storage paths
    pdf_storage_path: Optional[str] = None         # PDF base (non firmato)
    signed_pdf_storage_path: Optional[str] = None  # PDF con firme inserite
    # Firme (PNG base64 → "data:image/png;base64,...")
    firma_operatore_b64: Optional[str] = None
    firma_operatore_user_id: Optional[str] = None
    firma_operatore_nome: Optional[str] = None
    firma_operatore_at: Optional[str] = None
    firma_cliente_b64: Optional[str] = None
    firma_cliente_nome: Optional[str] = None
    firma_cliente_at: Optional[str] = None
    created_by: Optional[str] = None


class ProdottoLibreria(BaseDoc):
    """Prodotto assicurativo (catalogo interno per dropdown polizze)."""
    nome: str
    compagnia_id: Optional[str] = None
    ramo: Optional[str] = None
    descrizione: Optional[str] = None
    termini_mora_giorni: int = 15  # default 15gg; per Vita usare 30gg (vedi DEFAULT_MORA_BY_RAMO)
    is_libro_matricola: bool = False  # se True (solo per RC_AUTO/flotte) → polizza con applicazioni veicoli
    mostra_sezione_veicolo: bool = False  # se True, mostra la sezione "Dati veicolo" nelle polizze di questo prodotto (RCAuto è sempre attivo)
    attivo: bool = True


class ApplicazioneLibroMatricola(BaseDoc):
    """Applicazione (sub-polizza) di un Libro Matricola RCA — un veicolo per riga."""
    polizza_id: str
    numero: int  # progressivo applicazione
    targa: str
    stato: Literal["attiva", "annullata", "sospesa", "sostituita"] = "attiva"
    data_inclusione: str  # YYYY-MM-DD
    data_esclusione: Optional[str] = None
    # Sostituzione (per cambio veicolo)
    sostituita_da_id: Optional[str] = None  # id dell'applicazione che ha sostituito questa
    sostituisce_id: Optional[str] = None  # id dell'applicazione sostituita da questa
    data_sostituzione: Optional[str] = None
    motivo_annullamento: Optional[str] = None
    note: Optional[str] = None
    # Dati veicolo
    marca: Optional[str] = None
    modello: Optional[str] = None
    tipo_veicolo: Optional[str] = None  # Autovettura, Autocarro, Motociclo, ecc.
    tipo_alimentazione: Optional[str] = None
    tipo_uso: Optional[str] = None
    data_immatricolazione: Optional[str] = None
    data_acquisto: Optional[str] = None
    cv_fiscali: Optional[int] = None
    kw: Optional[float] = None
    quintali: Optional[float] = None
    cilindrata: Optional[int] = None
    posti: Optional[int] = None
    targa_rimorchio: Optional[str] = None
    quintali_rimorchio: Optional[float] = None
    gancio_traino: bool = False
    # Leasing
    leasing: Optional[str] = None  # società di leasing
    data_leasing: Optional[str] = None
    scadenza_leasing: Optional[str] = None
    # Tariffa
    tipo_tariffa: Optional[str] = None
    bm_provenienza: Optional[str] = None
    bm_assegnata: Optional[str] = None
    bm_assegnata_cu: Optional[str] = None
    pejus: float = 0.0
    franchigia: float = 0.0
    valore_veicolo: float = 0.0
    valore_residuo: float = 0.0
    valore_accessori: float = 0.0
    guida_esperta: bool = False
    guida_esclusiva: bool = False
    rinuncia_rivalsa: bool = False
    intestatario: Optional[str] = None
    provincia_intestatario: Optional[str] = None
    massimali: Optional[str] = None


# Default termini di mora per ramo (giorni) — usato quando il prodotto non
# specifica il proprio termine. Le polizze Vita hanno mora più lunga (30gg).
DEFAULT_MORA_BY_RAMO: dict = {
    "VITA": 30,
    "vita": 30,
    "VITA_RC": 30,
    "PREVIDENZA": 30,
}


def default_mora_for_ramo(ramo: Optional[str]) -> int:
    if not ramo:
        return 15
    r = ramo.strip()
    return DEFAULT_MORA_BY_RAMO.get(r, DEFAULT_MORA_BY_RAMO.get(r.upper(), 15))


class RamoLibreria(BaseDoc):
    """Ramo assicurativo (es. RCA, INCENDIO, VITA)."""
    codice: str
    nome: str
    descrizione: Optional[str] = None
    attivo: bool = True


# =============== ALLEGATI / DOCUMENTI ===============
class Allegato(BaseDoc):
    """Allegato collegato a una entità (anagrafica/polizza/sinistro/cliente/corso)."""
    entita_tipo: Literal["anagrafica", "polizza", "sinistro", "compagnia", "corso", "movimento", "titolo"]
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
    # Commercialista (per invio prima nota chiusa)
    email_commercialista: Optional[str] = None
    nome_commercialista: Optional[str] = None
    invio_automatico_chiusura: bool = False  # se true: alla chiusura giorno invia subito
    # SMTP per invio email (Prima Nota chiusa, ecc.)
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None      # es. "Assicura <noreply@assicura.it>"
    smtp_use_tls: bool = True
    # IMAP per lettura cassetta principale (smistamento automatico per alias)
    imap_host: Optional[str] = None
    imap_port: Optional[int] = 993
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: bool = True
    imap_folder: str = "INBOX"
    # Twilio per SMS + WhatsApp Business (libreria comunicazioni unica)
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_sms_from: Optional[str] = None        # numero verificato es. +391234567890
    twilio_whatsapp_from: Optional[str] = None   # numero WA Business es. whatsapp:+14155238886
    # Notifica scadenze giornaliera (cron 08:00)
    notifica_scadenze_attiva: bool = True
    notifica_scadenze_giorni: int = 15
    notifica_scadenze_email_admin: Optional[str] = None  # se vuoto usa email_commercialista o admin


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


# =============== RUBRICA CONTATTI COMPAGNIA ===============
class ContattoCompagnia(BaseDoc):
    """Persona di riferimento di una compagnia (rubrica)."""
    compagnia_id: str
    nome: str
    cognome: Optional[str] = None
    ruolo: Optional[str] = None  # es. "Ufficio sinistri", "Ufficio incassi", "Direzione"
    ufficio: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    cellulare: Optional[str] = None
    interno: Optional[str] = None
    note: Optional[str] = None
    attivo: bool = True


class ImportLog(BaseDoc):
    utente_id: Optional[str] = None
    nome_file: str
    flusso: str = "omnia"           # iter23: tipo flusso (omnia | targhe | libro_matricola | ...)
    record_types_processati: dict = Field(default_factory=dict)
    anagrafiche_create: int = 0
    anagrafiche_aggiornate: int = 0
    polizze_create: int = 0
    polizze_aggiornate: int = 0
    titoli_creati: int = 0
    sinistri_creati: int = 0
    errori: List[str] = Field(default_factory=list)
    # iter23: dettaglio record NON importati / parzialmente importati
    record_skipped: List[dict] = Field(default_factory=list)
    # iter23: entità presenti nel flusso ma NON mappate verso il catalogo programma
    # struttura: {"compagnie": ["UCA", "..."], "rami": ["TutelAuto", ...],
    #             "collaboratori": ["MARIO ROSSI"], "prodotti": [...]}
    entita_non_mappate: dict = Field(default_factory=dict)
    durata_ms: int = 0
    stato: Literal["completato", "errore", "in_corso"] = "in_corso"


class MappingFlusso(BaseDoc):
    """Mappatura tra valori nel flusso esterno e entità del programma.

    Esempi:
      tipo='compagnia', flusso='omnia', valore_flusso='UCA',
            entita_id='<compagnia_id>', label_programma='UCA Assicurazioni'
      tipo='ramo',     flusso='omnia', valore_flusso='TutelAuto',
            entita_id='Tutela Legale',  label_programma='Tutela Legale'
      tipo='collaboratore', flusso='omnia', valore_flusso='SCHIANTARELLI',
            entita_id='<user_id>',     label_programma='Schiantarelli Marco'
    """
    tipo: Literal["compagnia", "ramo", "prodotto", "collaboratore", "garanzia"]
    flusso: str = "omnia"
    valore_flusso: str               # come appare nel flusso (es. "UCA", "TutelAuto")
    entita_id: Optional[str] = None  # id (compagnia/user) o valore normalizzato (ramo)
    label_programma: Optional[str] = None
    note: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


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


# =============== PIPELINE CUSTOM (Kanban configurabili) ===============
class PipelineColonna(BaseModel):
    key: str                    # slug univoco nella pipeline (es. 'lead', 'trattativa')
    label: str                  # nome visualizzato
    colore: Optional[str] = None  # hex es. '#0EA5E9'
    ordine: int = 0
    descrizione: Optional[str] = None


class PipelineCustom(BaseDoc):
    """Pipeline configurabile dall'utente: marketing, onboarding, lead, ecc."""
    nome: str
    descrizione: Optional[str] = None
    tipo: Literal["marketing", "vendita", "onboarding", "supporto", "generico"] = "generico"
    icona: Optional[str] = None        # nome icona lucide (es. 'Megaphone')
    colore: Optional[str] = None       # hex del badge pipeline
    colonne: List[PipelineColonna] = Field(default_factory=list)
    operatore_id: Optional[str] = None  # proprietario / visibilità
    attiva: bool = True


class PipelineCard(BaseDoc):
    """Card all'interno di una PipelineCustom."""
    pipeline_id: str
    colonna_key: str
    titolo: str
    descrizione: Optional[str] = None
    valore_stimato: float = 0.0       # es. budget o premio atteso
    scadenza: Optional[str] = None
    # collegamenti opzionali a entità esistenti
    anagrafica_id: Optional[str] = None
    polizza_id: Optional[str] = None
    sinistro_id: Optional[str] = None
    # assegnazione
    operatore_id: Optional[str] = None
    # ordinamento all'interno della colonna
    ordine: int = 0
    # tag e priorità
    tags: List[str] = Field(default_factory=list)
    priorita: Literal["bassa", "media", "alta"] = "media"
    archiviata: bool = False



# =============== ANALISI CLIENTE (Diagnosi completa) ===============
class ImmobileItem(BaseModel):
    tipo: Literal["abitativo", "commerciale", "ufficio", "garage", "terreno", "altro"] = "abitativo"
    indirizzo: Optional[str] = None
    comune: Optional[str] = None
    foglio: Optional[str] = None
    particella: Optional[str] = None
    sub: Optional[str] = None
    categoria_catastale: Optional[str] = None
    rendita_catastale: float = 0.0
    valore_commerciale: float = 0.0
    titolo: Literal["proprieta", "comproprieta", "usufrutto", "nuda_proprieta", "locazione"] = "proprieta"
    percentuale_proprieta: float = 100.0
    targa_immobile: Optional[str] = None
    note: Optional[str] = None


class VeicoloItem(BaseModel):
    tipo: Literal["auto", "moto", "furgone", "camper", "barca", "altro"] = "auto"
    marca: Optional[str] = None
    modello: Optional[str] = None
    targa: Optional[str] = None
    anno: Optional[int] = None
    valore_commerciale: float = 0.0
    note: Optional[str] = None


class BeneItem(BaseModel):
    descrizione: str
    valore: float = 0.0
    note: Optional[str] = None


class AziendaItem(BaseModel):
    tipo: Literal["srl", "snc", "sas", "spa", "ditta_individuale", "altro"] = "srl"
    ragione_sociale: str
    partita_iva: Optional[str] = None
    percentuale_partecipazione: float = 100.0
    ebitda: float = 0.0
    posizione_finanziaria_netta: float = 0.0
    valore_ipotetico: float = 0.0
    note: Optional[str] = None


class RedditoStoricoItem(BaseModel):
    anno: int
    reddito: float = 0.0
    contributi: float = 0.0
    cassa: Optional[str] = "Commerciante"


class PeriodoContributivoItem(BaseModel):
    fondo: str = "Commerciante"
    inizio_periodo: str  # YYYY-MM-DD
    fine_periodo: Optional[str] = None
    riscattato: bool = False


class AnalisiCliente(BaseDoc):
    """Analisi completa del cliente (situazione finanziaria, patrimonio, contesto,
    redditi, pensioni, scoperture, successione). Una sola per anagrafica."""
    anagrafica_id: str

    # --- 1. Situazione finanziaria ---
    reddito_lordo_annuo: float = 0.0
    dividendi_partecipazioni: float = 0.0
    altri_redditi_annuali: float = 0.0
    reddito_da_affitti: float = 0.0
    reddito_estero: bool = False
    regime_forfettario: bool = False
    tfr_maturato: float = 0.0
    liquidita: float = 0.0  # conto corrente + investimenti liquidi
    debiti: float = 0.0  # mutui, finanziamenti, residui
    oneri_deducibili: float = 0.0
    oneri_fondo_pensione: float = 0.0
    altre_detrazioni: float = 0.0
    capacita_risparmio_annuale: float = 0.0

    # --- 1b. Appetito al rischio ---
    danno_devastante_entrate_mensili: float = 0.0  # €/mese soglia
    danno_devastante_patrimonio: float = 0.0  # € soglia

    # --- 2. Patrimonio ---
    immobili: List[ImmobileItem] = Field(default_factory=list)
    veicoli: List[VeicoloItem] = Field(default_factory=list)
    beni: List[BeneItem] = Field(default_factory=list)
    aziende: List[AziendaItem] = Field(default_factory=list)

    # --- 3. Contesto & Obiettivi ---
    contesto_familiare: Optional[str] = None
    contesto_lavorativo: Optional[str] = None
    contesto_patrimoniale: Optional[str] = None
    cosa_renderebbe_felice: Optional[str] = None  # sogni/aspirazioni
    cosa_non_vuoi_carriera: Optional[str] = None
    cosa_non_vuoi_dopo: Optional[str] = None
    cosa_non_vuoi_pensione: Optional[str] = None

    # --- 5. Pensione - storico redditi e periodi (override del calcolo automatico) ---
    storico_redditi: List[RedditoStoricoItem] = Field(default_factory=list)
    periodi_contributivi: List[PeriodoContributivoItem] = Field(default_factory=list)
    # Archivio estratti conto INPS caricati (uno per anno, ma anche più)
    estratti_conto_inps: List[dict] = Field(default_factory=list)
    # ^ [{url, storage_path, nome_file, mime, size_kb, data_caricamento,
    #     anno_riferimento, totale_settimane, totale_versato, montante_stimato,
    #     caricato_da}]

    # --- 8. Trattativa A/B (non fai nulla vs ti affidi a me) ---
    trattativa: dict = Field(default_factory=dict)
    # Schema atteso: {
    #   "scenario_a": {invalidita, importo_pensione, premorienza, responsabilita,
    #                  perdita_beni, prima_data_pensionabile, versamento_fondo,
    #                  risparmio_annuo, vantaggio_fiscale, reddito},
    #   "scenario_b": {...stessi campi...},
    #   "obiettivi": "testo libero",
    #   "perdita_entrate": "testo libero",
    #   "soglie_devastante": {trascurabile, basso, medio, alto, molto_alto}
    # }

    # --- 9. Piramide delle soluzioni ---
    piramide_soluzioni: List[dict] = Field(default_factory=list)
    # ^ [{id, categoria (Reddito|Premorienza|Invalidita|Responsabilita|Beni|Pensione|Risparmio),
    #     titolo, capitale_assicurato, premio_annuo, durata_anni, compagnia, note, ordine}]

    # --- Snapshot risultati (calcolati on-demand) ---
    ultimo_calcolo: Optional[dict] = None
    ultimo_calcolo_data: Optional[str] = None



# =============== RAPPEL (sovraprovvigioni compagnia) ===============
class Rappel(BaseDoc):
    """Rappel = sovraprovvigione accordata dalla compagnia al raggiungimento
    di obiettivi commerciali. È un accredito FITTIZIO (non un vero pagamento)
    che riduce il saldo da versare alla compagnia."""
    compagnia_id: str
    data: str                      # YYYY-MM-DD
    anno: int                      # anno di competenza (per archivio)
    importo: float                 # sempre positivo
    descrizione: Optional[str] = None
    note: Optional[str] = None
    stato: Literal["da_incassare", "incassato"] = "da_incassare"
    data_incasso: Optional[str] = None
    movimento_id: Optional[str] = None  # se incassato, ref al movimento provvigioni in Prima Nota
    created_by: Optional[str] = None  # user id



# =============== MEZZO PAGAMENTO (libreria unificata) ===============
class MezzoPagamento(BaseDoc):
    """Libreria UNICA dei mezzi di pagamento usati in TUTTI i dialoghi
    (incassi, paga-provvigioni, paga-compagnia, nuovo movimento, edit).

    `codice` = chiave stabile usata nei dati esistenti (contanti, bonifico, ...).
    `tipo_conto` = quale tipo di ContoCassa risolvere automaticamente.
    `conto_default_id` = se valorizzato, override esplicito del conto da utilizzare.
    """
    codice: str         # univoco (es. "contanti", "bonifico", "assegno", "pos", "rid", "altro")
    label: str          # testo visualizzato (es. "Contanti", "Bonifico bancario")
    tipo_conto: Literal["cassa", "banca", "carta", "rid", "online", "altro"] = "altro"
    conto_default_id: Optional[str] = None  # forza la mappatura ad uno specifico ContoCassa
    icona: Optional[str] = None
    ordine: int = 0
    attivo: bool = True
