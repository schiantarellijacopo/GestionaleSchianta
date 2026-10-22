# Changelog — Axicura CRM

## 2026-10-22 — FIX regressione: doppia registrazione in incasso multiplo
- Sintomo: incassando più titoli COPERTI in blocco, nel brogliaccio comparivano 2 righe
  per titolo (copertura + incasso) = doppia registrazione.
- Causa: il commit `eade615` aveva RIMOSSO `merge_copertura: true` dai flussi di incasso
  multiplo (`Titoli.jsx` dialog "Incasso/Copertura — N titoli" e `TitoliSospesi.jsx`),
  annullando la correzione corretta `052602c`.
- Fix: ripristinato `merge_copertura: true` in entrambi i flussi. Il backend
  (`incassa_titolo`) unifica copertura+incasso in UNA riga `incasso_premio` (giornate aperte),
  salvando lo snapshot `coperture_assorbite` (eliminando l'incasso il titolo torna a sospeso).
- Verificato (DB, giornata aperta): senza merge = 2 movimenti; con merge = 1 movimento
  `incasso_premio` (200€, provv 40). Dati di test rimossi.

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
