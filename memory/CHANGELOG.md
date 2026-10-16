# Changelog — Axicura CRM

## 2026-10-16 — OCR: salvataggio automatico documento nella card
- **Card "Libretto veicolo"**: rimosso il bottone OCR separato. Ora un unico upload esegue
  automaticamente l'OCR all'inserimento del file e salva il documento nella card
  (categoria `libretto_veicolo`). Il file viene salvato anche se l'OCR fallisce (no perdita).
- **OCR polizza**: corretto bug in `/utility/ocr-polizza` (`salva_come_allegato`) — l'`Allegato`
  veniva creato con campi inesistenti (`url/mime/size_kb/caricato_da`) → validazione Pydantic
  falliva silenziosamente e il documento NON veniva mai salvato. Ora usa i campi corretti
  (`storage_path/content_type/size/autore_id`) + `categoria="polizza"`.
- **Form nuova polizza** (`Polizze.jsx` save): dopo la creazione il PDF viene salvato come
  allegato nella card "polizza" via `/allegati` (categoria `polizza`), senza ri-eseguire un
  secondo OCR completo (più veloce, niente rischio 502).
- Flussi già corretti e verificati: **anagrafica** (CI/visura → `anagrafiche.documenti.{tipo}`),
  **posta/inbox** (`documenti-inbox/save` → allegato con categoria = card key per
  anagrafica/polizza/sinistro).
- Test: upload allegato polizza via API → HTTP 200, categoria/content_type/size corretti,
  compare nella lista allegati della polizza.

> NB: da pubblicare su Railway via **Save to GitHub**.
