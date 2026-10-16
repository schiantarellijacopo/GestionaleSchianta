# Changelog — Axicura CRM

## 2026-10-16 — OCR: salvataggio automatico documento nella card (robusto)
- **Causa radice del "non salva"**: dalla card, il frontend inviava `polizza_id` come
  query string mentre il backend lo leggeva da `Form()` (body) → `None` → allegato mai salvato.
  Inoltre, se l'OCR Gemini falliva/timeout, la card non si aggiornava.
- **Fix definitivo (disaccoppiato)**: nella card "Libretto veicolo" l'upload ora:
  1. salva SEMPRE il file nella card via `/allegati` (categoria `libretto_veicolo`) — affidabile;
  2. poi esegue l'OCR solo per estrarre/applicare i dati veicolo (se fallisce, il file resta).
  Un solo upload, OCR automatico, nessun bottone separato.
- **Nuova polizza da OCR** (`Polizze.jsx` save): dopo la creazione il PDF viene salvato come
  allegato nella card "polizza" via `/allegati` (categoria `polizza`), senza secondo OCR.
- **OCR polizza** `/utility/ocr-polizza`: corretto `Allegato` (campi errati url/mime/size_kb)
  → ora usa storage_path/content_type/size/autore_id + categoria="polizza".
- Flussi già corretti: anagrafica (CI/visura → `anagrafiche.documenti.{tipo}`), posta/inbox
  (`documenti-inbox/save` → allegato con categoria = card key per anagrafica/polizza/sinistro).
- **Test**: curl `/ocr/libretto` con polizza_id in FormData → HTTP 200 + allegato salvato;
  test browser reale (login → polizza → tab Documenti → upload libretto) → documento compare
  nella card "Libretto veicolo" (badge 1). File di test rimossi.

> NB: da pubblicare su Railway via **Save to GitHub**.
