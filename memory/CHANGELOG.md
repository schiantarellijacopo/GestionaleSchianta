# Changelog — Axicura CRM

## 2026-10-22 — Modelli Firma: modalità {placeholder} + Word + Librerie
- Aggiunto segnaposto `{x}` per **sbarrare una casella** (scrive una X nel punto). Verificato.
- **Pivot a segnaposto `{...}`** (niente più riquadri da trascinare): nel Word/PDF si scrivono
  `{nome_cliente}`, `{agenzia_rui}`, `{collab_rui_sezione}`, `{firma}` ecc.; in compilazione
  l'app sostituisce i segnaposto coi valori reali (pymupdf redaction) e rileva `{firma}` per
  posizionare il campo firma Yousign. Verificato con unit test (sostituzione + rilevamento firma).
- **Nuovi gruppi dati**: Cliente, Polizza, **Collaboratore** (nome, CF, email, RUI, sezione RUI),
  **Agenzia** (ragione sociale, P.IVA, RUI, sezione RUI), data odierna. Collaboratore risolto da
  polizza o utente corrente; agenzia da `azienda_config`.
- **Supporto Word**: .docx/.doc convertiti in PDF via LibreOffice headless (installato; va
  aggiunto anche al Dockerfile Railway). Upload anche via **drag & drop**.
- **Spostato in Librerie → "Modelli Firma (PDF/Word)"** (rimossa voce di menu dedicata).
  UI: spiegazione, segnaposto cliccabili (copia), "Compila per un cliente", anteprima PDF.
- Backend: `/api/firma/modelli` (upload/list/detail/delete/compila); compila salva il PDF come
  allegato del cliente/polizza e, se c'è `{firma}`, crea la richiesta Yousign (sandbox).

## 2026-10-22 — Firma Yousign/YouTrust sandbox — TESTATA OK
- Flusso e2e verificato (crea→carica→firmatario→attiva `ongoing`). Key: `YOUSIGN_SANDBOX_API_KEY`.

## 2026-10-22 — Firma digitale Yousign/YouTrust + Designer modelli (MVP)
- **Integrazione Yousign v3 (brand YouTrust)** testata e FUNZIONANTE in sandbox
  (`https://api-sandbox.yousign.app/v3`, Bearer): crea richiesta → carica PDF → aggiunge
  firmatario (firma elettronica) → attiva (status `ongoing`). Key in `YOUSIGN_SANDBOX_API_KEY`.
  Note: livello "simple" richiede `signature_authentication_mode` ∈ otp_email/otp_sms/no_otp;
  in sandbox l'email firmatario deve appartenere all'organizzazione Yousign.
- **Designer modelli firma** (`routes/firma_modelli.py` + `pages/ModelliFirma.jsx`):
  - L'agenzia carica un PDF; il backend renderizza le pagine come immagini (pymupdf).
  - Editor visivo: trascini sulle pagine i campi **Dato** (nome cliente, CF, P.IVA, indirizzo,
    comune, CAP, provincia, email, telefono, data, n° polizza, compagnia) e il campo **Firma**;
    coordinate salvate come frazioni sul modello (riusate finché non le modifichi).
  - "Compila per cliente": scrive i dati reali dentro il PDF, lo salva come allegato, e (se
    presente campo firma) crea la richiesta Yousign con il campo firma nel punto salvato.
  - Scoping per agenzia (tenant). Endpoint sotto `/api/firma/modelli`. Voce menu "Modelli Firma".
  - Endpoint diagnostico Super Admin `POST /super-admin/chiavi-api/test-yousign`.
- Test: flusso e2e via API OK (nome scritto nel PDF verificato con estrazione testo; firma
  Yousign status `ongoing`); editor verificato nel browser sul PDF IVASS reale.
- **Pendente**: supporto Word (.docx) richiede LibreOffice (da aggiungere anche al Dockerfile
  Railway); per ora caricare PDF. Sostituzione provider Namirial/OpenAPI non ancora effettuata
  (Yousign affiancato, da promuovere a default quando confermi).

## 2026-10-22 — Verifica completa anti-doppia-registrazione (centralizzata nel backend)
- Verificati TUTTI i flussi di incasso del codice:
  - Frontend multiplo: `Titoli.jsx` e `TitoliSospesi.jsx` → `merge_copertura:true` ripristinato.
  - Frontend singolo: `DialogIncassoCopertura.jsx`, `DialogIncasso.jsx`, `PolizzaDetail.jsx`
    (incasso rapido) → NON inviano il flag, ma ora sono protetti dalla rete di sicurezza backend.
  - Backend `/titoli/bulk-incassa` (non usato dal frontend) → reso coerente (gestisce coperto
    + merge stesso giorno).
- **Rete di sicurezza centralizzata** in `incassa_titolo` (server.py): una copertura dello
  STESSO giorno dell'incasso (giornata aperta) viene SEMPRE unificata in un'unica riga
  `incasso_premio`, a prescindere dal flag → nessun flusso può più generare la doppia riga.
  Coperture di altri giorni aperti unificate solo con `merge_copertura:true`; coperture su
  giornate CHIUSE restano invariate.
- Test (DB, giornata aperta) tutti PASS:
  - singolo/bulk, copertura+incasso STESSO giorno (senza flag) → 1 riga `incasso_premio`.
  - copertura giorno precedente → 2 righe corrette su 2 giorni (storico preservato).
  - `/titoli/bulk-incassa` coperto stesso giorno → 1 riga. Dati di test rimossi.

## 2026-10-22 — FIX regressione: doppia registrazione in incasso multiplo
- Causa: `eade615` aveva rimosso `merge_copertura:true` dai flussi multipli, annullando
  la correzione `052602c`. Ripristinato.

## 2026-10-17 — Statistiche: nuova tab "Incassi" (replica cruscotto)
- Nuova tab **Statistiche → Incassi** (`StatisticheIncassi.jsx`) che replica il layout dello
  screenshot richiesto: snapshot mese (Titoli arretrati/scaduto, Sospesi Rete Vendita, Sospesi
  cliente), KPI rolling 12 mesi (Velocità di incasso / recupero cliente / recupero rete, con
  tooltip che spiegano la formula), 3 donut (provvigioni per compagnia, provvigioni per ramo,
  premi per modalità incasso) e tabella "Incassi: situazione di <Mese>" con confronto
  anno corrente / precedente / Var. %.
- **Aggiunte righe Premi Lordi e Premi Netti** (oltre a Provvigioni Attive e Nette) come
  richiesto.
- Backend: nuovo endpoint `GET /api/statistiche/incassi-situazione?anno=&mese=` (server.py)
  che aggrega i titoli (scoped per operatore se non admin). Provvigioni Nette = Attive meno le
  quote girate alla rete vendita (`provvigioni_operatori`). Premi = importo_lordo/importo_netto
  dei titoli incassati nel mese.
- Nota: il modello dati non ha i concetti proprietari esatti del gestionale di riferimento
  ("sospesi rete vendita", "velocità di recupero"): sono calcolati dagli stati titolo
  (incassato/da_incassare/insoluto) e documentati nei tooltip.
- Verificato: endpoint via curl (mese 10/2026 → Provvigioni 267,23 / Premi Lordi 1237,00,
  donut Generali/RCA/bonifico) e screenshot browser della tab.

## 2026-10-17 — Ora di Roma (Europe/Rome) con cambio ora automatico
- Aggiunto `frontend/src/lib/timezone.js` (import in `index.js`) che forza `timeZone:"Europe/Rome"`
  su tutte le formattazioni data/ora. DST automatico. Verificato: UTC 23:01 → "17/10/2026, 01:01".

## 2026-10-16 — OCR: salvataggio automatico documento nella card (robusto)
- Card "Libretto veicolo": upload unico con OCR automatico; il file è SEMPRE salvato via
  `/allegati` (categoria libretto_veicolo) prima dell'OCR. Causa radice del "non salva":
  polizza_id inviato in query string ma letto da Form() nel backend.
- Nuova polizza da OCR: PDF salvato come allegato nella card "polizza".
- `/utility/ocr-polizza`: corretto Allegato (campi errati) → categoria="polizza".

> NB: da pubblicare su Railway via **Save to GitHub**.
