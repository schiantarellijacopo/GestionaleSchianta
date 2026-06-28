"""Catalogo regole preset.

Caricate via seed_alert_presets() in startup. Idempotente:
- crea le regole mancanti
- aggiorna i campi "descrittivi" se cambiati nel codice (descrizione, default template)
- NON tocca attivo/canali/template se l'utente li ha già modificati (lo
  riconosciamo da updated_by_user=True).
"""
from __future__ import annotations
from database import db
from alert_models import AlertRule
from db_models import _now_iso


PRESETS: list[dict] = [
    # ============ EVENTI ============
    {
        "preset_key": "sinistro_aperto",
        "nome": "Sinistro aperto",
        "descrizione": "Notifica al cliente e al collaboratore quando viene aperto un sinistro.",
        "tipo": "evento", "evento": "sinistro.aperto",
        "canali": ["inapp", "email"], "destinatari": ["cliente", "collaboratore"],
        "template_oggetto": "Apertura sinistro {numero_sinistro}",
        "template_corpo": "Gentile {nome},\n\nLe confermiamo l'apertura del sinistro n° {numero_sinistro} relativo alla polizza {numero_polizza} ({ramo}).\n\nLa terremo aggiornata sui prossimi passi.\n\nUn cordiale saluto",
    },
    {
        "preset_key": "sinistro_chiuso",
        "nome": "Sinistro chiuso",
        "descrizione": "Notifica al cliente e al collaboratore quando il sinistro viene chiuso.",
        "tipo": "evento", "evento": "sinistro.chiuso",
        "canali": ["inapp", "email"], "destinatari": ["cliente", "collaboratore"],
        "template_oggetto": "Chiusura sinistro {numero_sinistro}",
        "template_corpo": "Gentile {nome},\n\nLe confermiamo la chiusura del sinistro n° {numero_sinistro}.\n\nPer qualsiasi chiarimento ci contatti.\n\nUn cordiale saluto",
    },
    {
        "preset_key": "sinistro_pagato",
        "nome": "Sinistro liquidato",
        "descrizione": "Notifica al cliente e al collaboratore quando il sinistro viene liquidato.",
        "tipo": "evento", "evento": "sinistro.pagato",
        "canali": ["inapp", "email"], "destinatari": ["cliente", "collaboratore"],
        "template_oggetto": "Liquidazione sinistro {numero_sinistro}",
        "template_corpo": "Gentile {nome},\n\nLe confermiamo la liquidazione del sinistro n° {numero_sinistro} per un importo di {importo_liquidato} €.\n\nUn cordiale saluto",
    },
    {
        "preset_key": "sinistro_importato_ania",
        "nome": "Sinistro importato da ANIA",
        "descrizione": "Quando un import ZIP/flusso ANIA carica nuovi sinistri, notifica il collaboratore sinistri.",
        "tipo": "evento", "evento": "sinistro.importato_ania",
        "canali": ["inapp", "email"], "destinatari": ["altri_collaboratori", "collaboratore"],
        "template_oggetto": "Nuovo sinistro da ANIA: {numero_sinistro}",
        "template_corpo": "Importato automaticamente nuovo sinistro {numero_sinistro} polizza {numero_polizza}. Verifica e prendi in carico.",
    },
    {
        "preset_key": "polizza_emessa",
        "nome": "Polizza emessa",
        "descrizione": "Notifica al cliente all'emissione di una nuova polizza.",
        "tipo": "evento", "evento": "polizza.emessa",
        "canali": ["inapp", "email"], "destinatari": ["cliente"],
        "template_oggetto": "Polizza {numero_polizza} attiva",
        "template_corpo": "Gentile {nome},\n\nLa polizza {numero_polizza} ({ramo}) è ora attiva.\nEffetto: {data_effetto}\nPremio: {premio_totale} €\n\nLa ringraziamo per la fiducia.",
    },
    # ============ SCHEDULE ============
    {
        "preset_key": "compleanno_cliente",
        "nome": "Auguri di compleanno",
        "descrizione": "Invia auguri al cliente nel giorno del compleanno.",
        "tipo": "schedule", "schedule_kind": "compleanno_cliente",
        "cron": "0 9 * * *",            # ogni giorno alle 09:00
        "canali": ["email"], "destinatari": ["cliente"],
        "template_oggetto": "Tantissimi auguri di buon compleanno!",
        "template_corpo": "Gentile {nome},\n\nle inviamo i nostri più sinceri auguri di buon compleanno! 🎂\n\nUn cordiale saluto",
    },
    {
        "preset_key": "documento_id_scaduto",
        "nome": "Documento d'identità in scadenza",
        "descrizione": "Avviso al cliente quando la sua CI/Patente sta per scadere (30gg).",
        "tipo": "schedule", "schedule_kind": "documento_id_scaduto",
        "cron": "0 8 * * 1",            # ogni lunedì alle 08:00
        "soglia_giorni": 30,
        "canali": ["inapp", "email"], "destinatari": ["cliente", "collaboratore"],
        "template_oggetto": "Il tuo documento sta per scadere",
        "template_corpo": "Gentile {nome},\n\nle ricordiamo che il documento {tipo_documento} risulta in scadenza il {data_scadenza}.\n\nProvveda al rinnovo prima della data indicata.\n\nUn cordiale saluto",
    },
    {
        "preset_key": "titolo_scaduto_oltre",
        "nome": "Titolo scaduto oltre soglia",
        "descrizione": "Sollecito automatico al cliente se un titolo è scaduto da N giorni (default 5).",
        "tipo": "soglia", "schedule_kind": "titolo_scaduto_oltre",
        "cron": "0 9 * * *",
        "soglia_giorni": 5,
        "canali": ["inapp", "email"], "destinatari": ["cliente", "collaboratore"],
        "template_oggetto": "Sollecito pagamento polizza {numero_polizza}",
        "template_corpo": "Gentile {nome},\n\nrisulta non ancora pagato il titolo della polizza {numero_polizza} scaduto il {scadenza} di importo {importo_lordo} €.\n\nLa preghiamo di provvedere al pagamento.\n\nUn cordiale saluto",
    },
    {
        "preset_key": "sospesi_settimanali",
        "nome": "Digest sospesi settimanale al collaboratore",
        "descrizione": "Ogni lunedì invia al collaboratore l'elenco dei suoi titoli sospesi.",
        "tipo": "schedule", "schedule_kind": "sospesi_settimanali",
        "cron": "0 8 * * 1",
        "canali": ["inapp", "email"], "destinatari": ["collaboratore"],
        "template_oggetto": "I tuoi sospesi della settimana",
        "template_corpo": "Ciao {nome},\n\necco il riepilogo dei titoli sospesi dei tuoi clienti.\nDettaglio in piattaforma: /titoli?preset=sospesi\n\nTotale: {totale_sospesi} € su {n_titoli} titoli.",
    },
    {
        "preset_key": "arretrati_settimanali",
        "nome": "Digest arretrati settimanale al collaboratore",
        "descrizione": "Ogni lunedì invia al collaboratore l'elenco delle polizze in arretrato dei suoi clienti.",
        "tipo": "schedule", "schedule_kind": "arretrati_settimanali",
        "cron": "0 8 * * 1",
        "canali": ["inapp", "email"], "destinatari": ["collaboratore"],
        "template_oggetto": "Arretrati settimanali",
        "template_corpo": "Ciao {nome},\n\nrisultano {n_arretrati} titoli in arretrato dei tuoi clienti per un totale di {totale_arretrati} €.\nDettaglio: /titoli?preset=scad_oltre15",
    },
    {
        "preset_key": "polizza_in_scadenza",
        "nome": "Polizza in scadenza senza rinnovo",
        "descrizione": "30 giorni prima della scadenza polizza, se non è stato emesso preventivo di rinnovo, avvisa cliente e collaboratore.",
        "tipo": "soglia", "schedule_kind": "polizza_in_scadenza",
        "cron": "0 8 * * *",
        "soglia_giorni": 30,
        "canali": ["inapp", "email"], "destinatari": ["collaboratore"],
        "template_oggetto": "Polizza {numero_polizza} in scadenza",
        "template_corpo": "La polizza {numero_polizza} del cliente {cliente_nome} scade il {scadenza} e non risulta ancora preventivo di rinnovo.",
    },
]


async def seed_alert_presets() -> None:
    """Seed disabilitato: i preset sono ora un CATALOGO TEMPLATE (vedi
    /alert-presets/catalog). L'utente li importa esplicitamente.

    Per popolare automaticamente i preset come regole, settare
    `ALERT_AUTO_SEED_PRESETS=1` nell'env.
    """
    import os
    if os.environ.get("ALERT_AUTO_SEED_PRESETS") != "1":
        return
    for p in PRESETS:
        existing = await db.alert_rules.find_one({"preset_key": p["preset_key"]}, {"_id": 0})
        if existing:
            continue
        rule = AlertRule(**p, is_preset=True, attivo=False)
        await db.alert_rules.insert_one(rule.model_dump())
