"""Generatore PDF Informativa Privacy GDPR completa con checkbox consensi e firma digitale.

Replica il modello "Assicurazioni Schiantarelli Marco Andrea SAS" (Informativa Cliente -
Prospect, formato 202207.docx) ai sensi degli artt. 13 e 14 del GDPR 679/2016.

Il PDF contiene:
- Header con dati azienda (nome, indirizzo)
- Tabella dati cliente precompilati
- Testo informativa completo su 4 pagine
- 4 caselle di consenso con checkbox (X o vuoto) basati sui flag dell'anagrafica
- Spazio firma con immagine firma digitale (se presente)
"""
from __future__ import annotations
import io
import base64
from datetime import datetime, date
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Image as RLImage, KeepTogether, HRFlowable,
)


DARK = colors.HexColor("#0F172A")
PRIMARY = colors.HexColor("#0369A1")
MID = colors.HexColor("#475569")
LIGHT = colors.HexColor("#F1F5F9")


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=12, leading=14, alignment=TA_CENTER, textColor=DARK, spaceAfter=4, spaceBefore=4, fontName="Helvetica-Bold"),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=10, leading=12, alignment=TA_CENTER, textColor=DARK, spaceAfter=4, fontName="Helvetica-Bold"),
        "section": ParagraphStyle("sec", parent=base["Normal"], fontSize=9, leading=11, alignment=TA_CENTER, textColor=DARK, spaceAfter=4, spaceBefore=8, fontName="Helvetica-Bold"),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=8, leading=10.5, alignment=TA_JUSTIFY, textColor=DARK, spaceAfter=4),
        "body_left": ParagraphStyle("bl", parent=base["Normal"], fontSize=8, leading=10.5, alignment=TA_LEFT, textColor=DARK, spaceAfter=4),
        "bullet": ParagraphStyle("bul", parent=base["Normal"], fontSize=8, leading=10.5, alignment=TA_JUSTIFY, textColor=DARK, leftIndent=12, bulletIndent=4, spaceAfter=2),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=7, textColor=MID),
        "consenso": ParagraphStyle("cons", parent=base["Normal"], fontSize=8, leading=10, alignment=TA_JUSTIFY, textColor=DARK, leftIndent=4),
        "footer_logo": ParagraphStyle("fl", parent=base["Normal"], fontSize=7, textColor=MID, alignment=TA_LEFT),
    }


def _checkbox(checked: bool, size: int = 9) -> str:
    """Restituisce un quadratino Unicode pieno/vuoto."""
    return "☒" if checked else "☐"


def _make_header(azienda_nome: str, indirizzo: str):
    def _draw(canvas, doc):
        canvas.saveState()
        w, h = A4
        # Header
        canvas.setFillColor(DARK)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(15 * mm, h - 15 * mm, azienda_nome.upper())
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MID)
        canvas.drawString(15 * mm, h - 19 * mm, "INFORMATIVA CLIENTE - PROSPECT")
        canvas.drawString(15 * mm, h - 23 * mm, indirizzo)
        canvas.setStrokeColor(PRIMARY)
        canvas.setLineWidth(0.6)
        canvas.line(15 * mm, h - 25 * mm, w - 15 * mm, h - 25 * mm)
        # Footer
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MID)
        canvas.drawString(15 * mm, 10 * mm, "INFORMATIVA PRIVACY CLIENTE 202207")
        canvas.drawRightString(w - 15 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()
    return _draw


def _datacliente_table(ana: dict):
    """Tabella dati cliente in apertura (cognome/nome, CF, indirizzo, contatti)."""
    s = _styles()
    nome = (f"{ana.get('nome', '') or ''} {ana.get('cognome', '') or ''}").strip() or ana.get("ragione_sociale", "")
    cf = ana.get("codice_fiscale") or ana.get("partita_iva") or ""
    indirizzo = ana.get("indirizzo") or ""
    cap = ana.get("cap") or ""
    comune = ana.get("comune") or ""
    prov = ana.get("provincia") or ""
    email = ana.get("email") or ""
    cell = ana.get("cellulare") or ""
    tel = ana.get("telefono") or ""

    data = [
        ["COGNOME E NOME / RAGIONE SOCIALE", "CODICE FISCALE / PARTITA IVA"],
        [nome, cf],
        ["INDIRIZZO", ""],
        [indirizzo, ""],
        ["CAP", "LOCALITÀ", "PROVINCIA"],
        [cap, comune, prov],
        ["E-MAIL", "CELLULARE", "TELEFONO"],
        [email, cell, tel],
    ]
    # Rendi 3-cols tutto
    rows3 = [
        [data[0][0], "", data[0][1]],
        [data[1][0], "", data[1][1]],
        [data[2][0], "", ""],
        [data[3][0], "", ""],
        [data[4][0], data[4][1], data[4][2]],
        [data[5][0], data[5][1], data[5][2]],
        [data[6][0], data[6][1], data[6][2]],
        [data[7][0], data[7][1], data[7][2]],
    ]
    t = Table(rows3, colWidths=[60 * mm, 60 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), MID),
        ("TEXTCOLOR", (0, 2), (-1, 2), MID),
        ("TEXTCOLOR", (0, 4), (-1, 4), MID),
        ("TEXTCOLOR", (0, 6), (-1, 6), MID),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
        ("FONTNAME", (0, 6), (-1, 6), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.5),
        ("FONTSIZE", (0, 2), (-1, 2), 6.5),
        ("FONTSIZE", (0, 4), (-1, 4), 6.5),
        ("FONTSIZE", (0, 6), (-1, 6), 6.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, 1), 0.3, MID),
        ("LINEBELOW", (0, 3), (-1, 3), 0.3, MID),
        ("LINEBELOW", (0, 5), (-1, 5), 0.3, MID),
        ("LINEBELOW", (0, 7), (-1, 7), 0.3, MID),
        ("SPAN", (0, 2), (-1, 2)),
        ("SPAN", (0, 3), (-1, 3)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _bullet_li(txt: str, s) -> Paragraph:
    return Paragraph(f"• {txt}", s["bullet"])


def _consenso_row(checked: bool, text: str, styles) -> Table:
    """Riga con due checkbox (acconsento / non acconsento) + testo."""
    ck_si = _checkbox(checked)
    ck_no = _checkbox(not checked)
    cont = Paragraph(
        f"<font name='Helvetica-Bold' size=9>{ck_si} acconsento &nbsp;&nbsp; {ck_no} non acconsento</font> "
        f"al trattamento {text}",
        styles["consenso"],
    )
    t = Table([[cont]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.3, MID),
    ]))
    return t


def _decode_storage_url(url: str | None) -> bytes | None:
    """Recupera bytes da uno storage path /api/storage/... (filesystem locale o S3)."""
    if not url:
        return None
    try:
        import storage as obj_storage
        # url shape: /api/storage/{path}
        path = url.split("/api/storage/", 1)[-1] if "/api/storage/" in url else url
        result = obj_storage.get_object(path)
        if isinstance(result, tuple):
            return result[0]
        return result
    except Exception:
        return None


def genera_privacy_pdf(ana: dict, azienda: dict, dipendente_nome: str = "") -> bytes:
    """Genera l'informativa privacy completa, con checkbox e firma immagine."""
    s = _styles()
    buf = io.BytesIO()

    ragione_az = (azienda.get("ragione_sociale") or "Assicurazioni").upper()
    indirizzo_az_full = " - ".join(filter(None, [
        azienda.get("indirizzo") or "",
        " ".join(filter(None, [azienda.get("cap") or "", azienda.get("comune") or ""])),
        f"({azienda.get('provincia')})" if azienda.get("provincia") else "",
    ])).strip(" -")
    if not indirizzo_az_full:
        indirizzo_az_full = "—"

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=28 * mm, bottomMargin=15 * mm,
    )

    el = []
    # --- Tabella dati cliente ---
    el.append(_datacliente_table(ana))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph("Informativa sulla tutela dei dati personali", s["h1"]))
    el.append(Paragraph(
        f"Ai sensi degli artt. 13 e 14 del GDPR 679/2016 – Regolamento europeo sulla protezione dei dati personali "
        f"e in relazione ai dati personali che La riguardano e che formeranno oggetto del trattamento, La informiamo che:",
        s["body"]))
    el.append(Paragraph(
        f"Qualora in intestazione siano riportati dati di una persona giuridica, i dati oggetto della presente saranno "
        f"quelli riferiti alle persone fisiche operanti nella stessa, di cui <b>{ragione_az}</b> verrà a conoscenza.",
        s["body"]))
    el.append(Paragraph(
        f"<b>{ragione_az}</b> in qualità di Titolare del trattamento intende acquisire, anche verbalmente, direttamente "
        f"o tramite terzi, o già detiene, alcuni Suoi dati, qualificati come personali, il cui trattamento viene effettuato "
        f"nel rispetto dei diritti e delle libertà fondamentali, nonché della dignità dell'interessato, con particolare "
        f"riferimento alla riservatezza, all'identità personale, al diritto ed alla protezione dei dati personali.",
        s["body"]))
    el.append(Paragraph(
        f"Saranno inoltre trattate anche categorie particolari di dati, che devono essere forniti da Lei in qualità "
        f"di soggetto interessato o da terzi, ad esempio da contraenti di polizze collettive o individuali che La "
        f"qualificano come assicurato, beneficiario, proprietario dei beni assicurati o danneggiato (come nel caso di "
        f"polizze di responsabilità civile) oppure da banche dati che vengono consultate in fase pre assuntiva, "
        f"assuntiva o liquidativa.", s["body"]))
    el.append(Paragraph(
        f"Ciò premesso, <b>{ragione_az}</b> La informa riguardo le finalità e le modalità del trattamento dei dati "
        f"personali raccolti e il loro ambito di comunicazione e diffusione, oltre alla natura del loro conferimento, "
        f"premettendo che i trattamenti avvengono nel contesto delle analisi obbligatorie per legge o regolamento, "
        f"dell'instaurazione ed esecuzione dei rapporti commerciali in essere o in divenire e dei rapporti consulenziali "
        f"da Lei richiesti come previsti da leggi o regolamenti di settore.", s["body"]))

    # --- Finalità ---
    el.append(Paragraph("FINALITÀ DI TRATTAMENTO E BASE GIURIDICA", s["section"]))
    el.append(Paragraph(
        f"Tutti i dati personali e sensibili da Lei conferiti, o già detenuti da <b>{ragione_az}</b>, oppure raccolti "
        f"presso altri soggetti e presso altre banche dati, la cui consultazione è prevista per legge o per regolamento, "
        f"costituiscono oggetto di trattamento. <b>{ragione_az}</b> non dispone di mezzi illeciti per ottenere queste "
        f"informazioni, che saranno utilizzate:", s["body"]))
    el.append(Paragraph(
        f"<b>1.</b> per la gestione delle attività specifiche di <b>{ragione_az}</b>, quale intermediario assicurativo, "
        f"e degli adempimenti obbligatori quali:", s["body"]))
    el.append(_bullet_li(
        "adempimento degli obblighi previsti da leggi, regolamenti o normative comunitarie, nonché da disposizioni "
        "impartite da Autorità a ciò legittimate dalla legge o da organi di vigilanza e di controllo;", s))
    el.append(_bullet_li(
        "realizzazione dell'attività di consulenza comprendente l'analisi dei Suoi bisogni e le valutazioni delle Sue "
        "esigenze assicurative e previdenziali, secondo quanto stabilito dalla normativa CEE 2002/92, dal Codice delle "
        "Assicurazioni (D.lgs. n. 209 del 7/9/2005), nonché dal Regolamento IVASS 40/2018;", s))
    el.append(_bullet_li(
        "erogazione di consulenza e supporto finalizzate alla proposta di prodotti e servizi adeguati alle Sue esigenze;", s))
    el.append(_bullet_li(
        "gestione, consulenza e supporto in merito alle pratiche di sinistro con le Compagnie di Assicurazioni;", s))
    el.append(_bullet_li(
        "gestione, consulenza e supporto in merito alle pratiche di reclamo intentate dagli assicurati.", s))
    el.append(Paragraph(
        "<b>2.</b> per attività di marketing, di promozione commerciale propria o di terzi e di analisi (per cui saranno "
        "trattati esclusivamente i dati personali particolari, previo rilascio di opportuno consenso) quali:", s["body"]))
    el.append(_bullet_li(
        "<b>a)</b> informazione e/o promozione commerciale, per illustrare nuove opportunità di Suo possibile interesse, "
        "a mezzo posta, telefono o mediante comunicazioni elettroniche come e-mail, fax, messaggi Sms o MMS e altri "
        "sistemi automatizzati disponibili allo scopo, volte a far conoscere i nuovi servizi e prodotti assicurativi "
        "adeguati al Suo profilo di rischio e a migliorare prodotti e servizi offerti;", s))
    el.append(_bullet_li(
        f"<b>b)</b> informazione e/o promozione commerciale per illustrare nuovi servizi e prodotti, anche di terzi, "
        f"di cui <b>{ragione_az}</b> è autorizzato da leggi, normative o appositi mandati e/o contratti, a curare la "
        f"commercializzazione;", s))
    el.append(_bullet_li(
        "<b>c)</b> ricerche di mercato ed indagini sulla qualità dei servizi e sulla Sua soddisfazione, anche "
        "avvalendosi di società specializzate, con l'obiettivo di migliorare l'offerta di prodotti e servizi;", s))
    el.append(_bullet_li(
        "<b>d)</b> comunicazione dei Suoi dati personali verso soggetti terzi, operanti nel settore indicato nella "
        "relativa richiesta di consenso, per finalità di informazione e promozione commerciale di prodotti o servizi "
        "da parte degli stessi;", s))
    el.append(_bullet_li(
        "<b>e)</b> profilazione volta ad analizzare i Suoi bisogni e le Sue esigenze assicurative per l'individuazione, "
        "anche attraverso elaborazioni elettroniche, dei possibili prodotti o servizi in linea con le Sue preferenze e "
        "i Suoi interessi. I dati oggetto di profilazione, da cui sono rigorosamente esclusi i dati idonei a rivelare "
        "lo stato di salute e la vita sessuale, con riferimento a clienti individuabili, potranno essere conservati per "
        "finalità di profilazione per un periodo non superiore a dodici mesi dalla loro registrazione;", s))
    el.append(_bullet_li(
        "<b>f)</b> informazione e/o promozione commerciale, per illustrare nuovi prodotti e/o servizi analoghi a quelli "
        "già contrattualizzati (soft spam), a mezzo posta, telefono o mediante comunicazioni elettroniche.", s))
    el.append(Paragraph(
        "<b>3.</b> per attività investigative difensive o per far valere o difendere un diritto in sede giudiziaria.",
        s["body"]))
    el.append(Paragraph(
        f"Tutti i dati da Lei conferiti sono trattati esclusivamente per adempimenti connessi all'attività di "
        f"<b>{ragione_az}</b>, le cui basi giuridiche sono rinvenibili nel consenso e/o nell'esecuzione di un contratto "
        f"di nostra gestione di cui Lei è parte o nell'esecuzione di misure precontrattuali adottate su Sua richiesta "
        f"e/o nell'adempiere a obblighi legali ai quali è soggetto lo scrivente Titolare e/o nel legittimo interesse "
        f"dello stesso.", s["body"]))

    # --- Natura obbligatoria ---
    el.append(Paragraph("NATURA OBBLIGATORIA E FACOLTATIVA DEL CONFERIMENTO DEI DATI", s["section"]))
    el.append(Paragraph(
        f"Il conferimento dei dati personali ed il conseguente trattamento da parte di <b>{ragione_az}</b>, per le "
        f"finalità di cui al punto 1, sono necessari per l'instaurazione, per la prosecuzione e per la corretta gestione "
        f"del rapporto tra Titolare ed Interessato: tale conferimento deve pertanto intendersi come obbligatorio in base "
        f"a legge, regolamento o normativa comunitaria (a titolo esemplificativo e non limitativo, la normativa "
        f"antiriciclaggio): l'eventuale rifiuto a fornire i dati personali richiesti potrà causare l'impossibilità di "
        f"perfezionare e di gestire il rapporto consulenziale. Il conferimento per le finalità di cui al punto 2 è "
        f"facoltativo.", s["body"]))

    # --- Modalità ---
    el.append(Paragraph("MODALITÀ DI TRATTAMENTO", s["section"]))
    el.append(Paragraph(
        f"Il trattamento dei dati personali sarà effettuato sia su supporti cartacei, mediante strumenti manuali, sia "
        f"con l'ausilio di strumenti elettronici mediante idonee procedure informatiche e telematiche. <b>{ragione_az}</b> "
        f"garantisce che i dati trattati saranno sempre pertinenti, completi e non eccedenti rispetto alle finalità per "
        f"le quali sono raccolti.", s["body"]))

    # --- Tempi ---
    el.append(Paragraph("TEMPI DI CONSERVAZIONE", s["section"]))
    el.append(Paragraph(
        "I dati personali saranno trattati per il tempo strettamente necessario a conseguire gli scopi descritti, per "
        "adempiere ad obblighi contrattuali, di legge e di regolamento. Con riferimento ai dati raccolti per finalità "
        "commerciali, i tempi di conservazione sono limitati a 1 anno per la profilazione e 2 anni per il marketing "
        "diretto (dalla raccolta per i prospect o dal termine del rapporto per i clienti).", s["body"]))

    # --- Ambito ---
    el.append(Paragraph("AMBITO DI CONOSCENZA E COMUNICAZIONE", s["section"]))
    el.append(Paragraph(
        f"Il trattamento dei dati personali sarà effettuato da soggetti espressamente e specificamente designati dal "
        f"Titolare, in qualità di responsabili o incaricati. I dati potranno altresì essere trattati da soggetti terzi "
        f"(outsourcer) e potranno essere comunicati a soggetti, pubblici e privati, che possono accedere ai dati in "
        f"forza di disposizione di legge, a soggetti esterni appartenenti al settore assicurativo e finanziario "
        f"(imprese di assicurazione, agenti, subagenti, produttori, centri peritali, broker, promotori finanziari, "
        f"banche, sim, ecc.), e a soggetti esterni consulenti di <b>{ragione_az}</b>. I dati non verranno diffusi.",
        s["body"]))

    # --- Diritti ---
    el.append(Paragraph("DIRITTI DELL'INTERESSATO", s["section"]))
    pec = azienda.get("pec") or azienda.get("email") or "—"
    el.append(Paragraph(
        f"Con riferimento agli artt. 15 (accesso), 16 (rettifica), 17 (cancellazione), 18 (limitazione), 20 "
        f"(portabilità), 21 (opposizione), 22 (decisione automatizzata) del GDPR 679/16, il soggetto interessato potrà "
        f"rivolgere le proprie richieste alla scrivente Società o attraverso la casella di posta elettronica: "
        f"<b>{pec}</b>.", s["body"]))
    el.append(Paragraph(
        "I soggetti interessati hanno il diritto di opposizione al trattamento dei propri dati personali per le "
        "finalità di marketing (indicate al punto 2), anche se effettuato con modalità automatizzate di contatto.",
        s["body"]))

    # --- Titolare ---
    el.append(Paragraph("TITOLARE DEL TRATTAMENTO", s["section"]))
    el.append(Paragraph(
        f"Il Titolare del trattamento dei dati personali è <b>{ragione_az}</b> con sede in <b>{indirizzo_az_full}</b>. "
        f"Il Titolare conserva una lista aggiornata dei responsabili nominati, e ne garantisce la presa visione "
        f"all'interessato presso la sede sopra indicata.", s["body"]))

    # --- CONSENSI ---
    el.append(Spacer(1, 5 * mm))
    el.append(HRFlowable(width="100%", color=PRIMARY, thickness=1, spaceAfter=4))
    el.append(Paragraph("CONSENSO AL TRATTAMENTO DEI DATI PERSONALI", s["section"]))
    nome_cliente = (f"{ana.get('nome', '') or ''} {ana.get('cognome', '') or ''}").strip() or ana.get("ragione_sociale", "")
    el.append(Paragraph(
        f"Preso atto dell'informativa, io sottoscritto/a <b>{nome_cliente or '_______________________________'}</b>",
        s["body_left"]))
    el.append(Spacer(1, 3 * mm))

    # 4 consensi
    el.append(_consenso_row(
        ana.get("consenso_dati_particolari", False),
        "<b>dei dati personali particolari</b> per le finalità indicate al <b>punto 1</b> dell'informativa consegnatami.",
        s))
    el.append(Spacer(1, 2 * mm))
    el.append(_consenso_row(
        ana.get("consenso_commerciale", False),
        "dei miei dati personali di natura comune per finalità di <b>informazione e promozione commerciale</b> di "
        "prodotti e/o servizi, a mezzo posta o telefono e/o mediante comunicazioni elettroniche quali e-mail, fax, "
        "messaggi del tipo Sms o MMS ovvero con sistemi automatizzati, come specificato ai <b>punti 2a, 2b e 2c</b> "
        "dell'informativa.", s))
    el.append(Spacer(1, 2 * mm))
    el.append(_consenso_row(
        ana.get("consenso_comunicazione_terzi", False),
        "dei miei dati personali di natura comune per finalità di <b>comunicazione dei dati a soggetti terzi</b>, "
        "operanti nel settore assicurativo, e nei settori complementari a quello assicurativo, ai fini di informazione "
        "e promozione commerciale di prodotti e/o servizi, anche mediante tecniche di comunicazione a distanza, "
        "come specificato al <b>punto 2d</b> dell'informativa.", s))
    el.append(Spacer(1, 2 * mm))
    el.append(_consenso_row(
        ana.get("consenso_profilazione", False),
        "dei miei dati personali di natura comune per finalità di <b>profilazione</b> volta ad analizzare i bisogni e "
        "le esigenze assicurative del cliente per l'individuazione, anche attraverso elaborazioni elettroniche, dei "
        "possibili prodotti e/o servizi in linea con le preferenze e gli interessi della clientela come specificato al "
        "<b>punto 2e</b> dell'informativa.", s))
    el.append(Spacer(1, 6 * mm))

    # --- Firma + data ---
    today = (
        ana.get("data_consenso_privacy")
        or ana.get("privacy_firmata_il", "")[:10]
        or date.today().isoformat()
    )
    try:
        d = date.fromisoformat(today)
        data_str = d.strftime("%d/%m/%Y")
    except Exception:
        data_str = today

    firma_bytes = _decode_storage_url(ana.get("firma_cliente_url"))
    if firma_bytes:
        try:
            firma_img = RLImage(io.BytesIO(firma_bytes), width=60 * mm, height=18 * mm, kind="proportional")
        except Exception:
            firma_img = Paragraph("_______________________________", s["body_left"])
    else:
        firma_img = Paragraph("_______________________________", s["body_left"])

    # Tabella data + firma
    fdata = [
        [Paragraph(f"<b>Data:</b> {data_str}", s["body_left"]),
         Paragraph("<b>L'interessato (firma):</b>", s["body_left"])],
        ["", firma_img],
    ]
    t = Table(fdata, colWidths=[60 * mm, 110 * mm], rowHeights=[8 * mm, 22 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (1, 1), (1, 1), 0.5, MID),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(KeepTogether(t))

    if dipendente_nome:
        el.append(Spacer(1, 4 * mm))
        el.append(Paragraph(
            f"<font size=7 color='{MID.hexval()}'>Documento generato da: <b>{dipendente_nome}</b> "
            f"il {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
            s["small"]))

    doc.build(
        el,
        onFirstPage=_make_header(ragione_az, indirizzo_az_full),
        onLaterPages=_make_header(ragione_az, indirizzo_az_full),
    )
    return buf.getvalue()
