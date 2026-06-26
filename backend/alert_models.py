"""Alert / Notifications models.

Schema:
- AlertRule: regola configurabile (trigger evento o schedule)
- AlertEvent: storico di OGNI invio (audit + retry/debug)
- Notification: notifica in-app destinata a un utente (campanella)

Trigger types:
- evento:    si attiva sulla pubblicazione di un evento (es. "sinistro.aperto")
- schedule:  job ricorrente (cron daily/weekly/monthly) con condizioni dinamiche
            (es. compleanno cliente → cerca clienti con data_nascita oggi).
- soglia:    schedule + soglia su una metrica (es. titolo scaduto da X giorni).

Channels: inapp, email, sms, whatsapp. SMS e WhatsApp sono PREDISPOSTI
(adapter funziona ma serve provider configurato).

Recipients:
- cliente:               anagrafica oggetto dell'evento (contraente/assicurato)
- collaboratore:         collaboratore_id sulla polizza/cliente
- collaboratore_sinistri: utente con flag "gestisce_sinistri"
- admin:                 tutti gli admin
- utente_specifico:      lista user_id custom
"""
from __future__ import annotations
from typing import Optional, Literal
from pydantic import Field
from db_models import BaseDoc, _now_iso, _uid


ALERT_EVENT_TYPES = [
    "sinistro.aperto",
    "sinistro.chiuso",
    "sinistro.pagato",
    "sinistro.importato_ania",
    "polizza.emessa",
    "polizza.rinnovata",
    "titolo.incassato",
    "pagamento.collaboratore",
]

ALERT_SCHEDULE_TYPES = [
    "compleanno_cliente",
    "documento_id_scaduto",
    "titolo_scaduto_oltre",        # parametro: giorni
    "sospesi_settimanali",          # digest collaboratore
    "arretrati_settimanali",        # digest collaboratore
    "polizza_in_scadenza",          # senza preventivo rinnovo
]

CANALI = ["inapp", "email", "sms", "whatsapp"]
DESTINATARI = ["cliente", "collaboratore", "collaboratore_sinistri", "admin", "utente_specifico"]


class AlertRule(BaseDoc):
    """Regola di alert configurabile."""
    id: str = Field(default_factory=_uid)
    nome: str
    descrizione: Optional[str] = None
    # tipo: "evento" oppure "schedule" / "soglia"
    tipo: Literal["evento", "schedule", "soglia"] = "evento"
    # se tipo=evento → nome evento (uno di ALERT_EVENT_TYPES)
    evento: Optional[str] = None
    # se tipo=schedule/soglia → tipo schedule (uno di ALERT_SCHEDULE_TYPES) + cron
    schedule_kind: Optional[str] = None
    cron: Optional[str] = None              # es. "0 8 * * *"  (every day at 08:00)
    soglia_giorni: Optional[int] = None     # per soglie tipo "titolo_scaduto_oltre"
    # canali e destinatari
    canali: list[str] = Field(default_factory=lambda: ["inapp"])
    destinatari: list[str] = Field(default_factory=lambda: ["cliente"])
    destinatari_user_ids: list[str] = Field(default_factory=list)   # per "utente_specifico"
    # template
    template_oggetto: Optional[str] = None
    template_corpo: Optional[str] = None
    # filtri condizionali (es. {"ramo": "Auto", "min_importo": 1000})
    condizioni: dict = Field(default_factory=dict)
    # stato
    attivo: bool = False
    # statistiche
    last_run_at: Optional[str] = None
    last_event_at: Optional[str] = None
    invii_totali: int = 0
    errori_totali: int = 0
    # metadata
    is_preset: bool = False              # creata dal seed catalogo (non eliminabile, modificabile)
    preset_key: Optional[str] = None     # identificatore preset (sinistro_aperto, compleanno, ...)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class AlertEvent(BaseDoc):
    """Storico esecuzioni — un record per OGNI tentativo di invio."""
    id: str = Field(default_factory=_uid)
    rule_id: str
    rule_nome: str
    canale: str                         # inapp | email | sms | whatsapp
    destinatario_tipo: str              # cliente | collaboratore | ...
    destinatario_user_id: Optional[str] = None
    destinatario_anagrafica_id: Optional[str] = None
    destinatario_label: Optional[str] = None     # nome leggibile (per UI storico)
    destinatario_indirizzo: Optional[str] = None # email/cellulare/whatsapp number
    oggetto: Optional[str] = None
    corpo: Optional[str] = None
    # contesto evento
    entita_tipo: Optional[str] = None    # sinistro | polizza | titolo | anagrafica
    entita_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    # esito
    status: Literal["ok", "skipped", "errore", "pending"] = "pending"
    error_message: Optional[str] = None
    sent_at: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)


class Notification(BaseDoc):
    """Notifica in-app letta dal centro notifiche dell'utente."""
    id: str = Field(default_factory=_uid)
    user_id: str
    titolo: str
    messaggio: str
    tipo: str = "info"                  # info | warning | success | danger
    icona: Optional[str] = None         # nome lucide-react icon (es. "AlertTriangle")
    # link opzionale alla risorsa (es. /sinistri/{id})
    link: Optional[str] = None
    # collegamenti
    rule_id: Optional[str] = None
    entita_tipo: Optional[str] = None
    entita_id: Optional[str] = None
    # stato
    letta: bool = False
    letta_at: Optional[str] = None
    archiviata: bool = False
    created_at: str = Field(default_factory=_now_iso)


# ============================================================
# PROVIDER CONFIG — configurazione canali (email/sms/whatsapp)
# ============================================================
EMAIL_PRESETS = {
    "gmail":      {"host": "smtp.gmail.com",      "port": 587, "starttls": True,
                   "label": "Google (Gmail / Workspace)",
                   "hint": "Email aziendale Google. Crea una App Password su myaccount.google.com → Security → 2-Step → App passwords."},
    "microsoft":  {"host": "smtp.office365.com",  "port": 587, "starttls": True,
                   "label": "Microsoft (Outlook / Office 365)",
                   "hint": "Email Microsoft 365 o Outlook.com. Admin deve abilitare SMTP AUTH. Se 2FA attivo, crea App Password."},
    "custom":     {"host": "",  "port": 587, "starttls": True,
                   "label": "SMTP personalizzato",
                   "hint": "Altri provider (Aruba, Register, ecc.). Inserisci manualmente host, porta, credenziali."},
}

WHATSAPP_PRESETS = {
    "twilio":     {"label": "Twilio WhatsApp Business",
                   "hint": "Account Twilio + sandbox o numero WhatsApp Business verificato. Servono: Account SID, Auth Token, numero From (whatsapp:+...)."},
    "meta":       {"label": "Meta Cloud API (futuro)",
                   "hint": "Meta WhatsApp Business Cloud API. Predisposto, integrazione in fase 2."},
}


class AlertProviderConfig(BaseDoc):
    """Configurazione di un canale di invio (email, sms, whatsapp).

    Un record per canale. `tipo` è la chiave univoca.
    Le credenziali sensibili (password, token) sono salvate in chiaro nel DB
    locale Mongo — assicurarsi che il backend non sia esposto in rete.
    """
    id: str = Field(default_factory=_uid)
    tipo: Literal["email", "sms", "whatsapp"]
    provider: str = "gmail"             # gmail | microsoft | custom | twilio | meta
    # email: SMTP
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None     # se None usa smtp_user
    smtp_from_name: Optional[str] = None  # display name "Studio Rossi"
    # sms/whatsapp: Twilio
    twilio_sid: Optional[str] = None
    twilio_token: Optional[str] = None
    twilio_from: Optional[str] = None   # numero From (whatsapp:+ per WA)
    # meta
    meta_phone_id: Optional[str] = None
    meta_token: Optional[str] = None
    # stato
    enabled: bool = False
    last_test_at: Optional[str] = None
    last_test_status: Optional[str] = None   # ok | errore
    last_test_error: Optional[str] = None
    updated_at: str = Field(default_factory=_now_iso)
