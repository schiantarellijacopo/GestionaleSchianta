# Changelog — Axicura CRM

## 2026-10-17 — Ora di Roma (Europe/Rome) con cambio ora automatico
- Il backend salva già tutto in UTC (`datetime.now(timezone.utc)`, ISO con offset +00:00).
- **Fix display**: aggiunto `/app/frontend/src/lib/timezone.js` importato in `index.js` che
  forza globalmente `timeZone: "Europe/Rome"` su `toLocaleString/toLocaleDateString/
  toLocaleTimeString`. Intl gestisce automaticamente CET/CEST (ora legale/solare).
  Chi passa già un `timeZone` esplicito lo mantiene. Niente modifiche ai 63 file.
- Verificato in browser: UTC 23:01 → "17/10/2026, 01:01" (CEST +2); dicembre → CET +1.

## 2026-10-16 — OCR: salvataggio automatico documento nella card (robusto)
- Causa radice "non salva": la card inviava `polizza_id` in query string mentre il backend
  lo leggeva da `Form()` (body) → None → allegato mai salvato. Inoltre su OCR fallito la card
  non si aggiornava.
- Fix (disaccoppiato): la card "Libretto veicolo" salva SEMPRE il file via `/allegati`
  (categoria `libretto_veicolo`) e poi esegue l'OCR per i dati veicolo. Un solo upload, OCR auto.
- Nuova polizza da OCR: il PDF viene salvato come allegato nella card "polizza" dopo la creazione.
- `/utility/ocr-polizza`: corretto Allegato (campi errati) → categoria="polizza".
- Verificato in browser reale: documento compare nella card dopo upload.

> NB: da pubblicare su Railway via **Save to GitHub**.
