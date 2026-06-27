# PRD — Programma Assicurativo (Italian Insurance CRM)

## Problem Statement
CRM full-stack su misura per agenzie assicurative italiane: gestione anagrafiche, polizze, titoli, sinistri, contabilità (Prima Nota / Brogliaccio), analisi cliente, avvisi scadenze, sistema provvigionale, mapping ANIA, importazione flussi (OMNIA, Libro Matricola).

## Stack
- Frontend: React + Shadcn UI + Tailwind + lucide-react
- Backend: FastAPI + Motor (Async MongoDB) + Pydantic
- LLM: Gemini 3 Flash via Emergent LLM Key (OCR polizze)
- Storage: object_storage interno (firma, allegati, PDF)
- Comunicazioni: SMTP (email), Twilio (SMS + WhatsApp Business)

## Implementato (al 27 Feb 2026)
### Recente sessione
- ✅ **Lettera di Abbuono con doppia firma digitale**: auto-trigger su sconto, PDF generato con reportlab, firma operatore pescabile dal profilo collaboratore (`users.firma_digitale_url`) oppure via canvas; firma cliente sempre via canvas; PDF firmato salvato come allegato titolo.
- ✅ **Libreria 3-tier "Tipi pagamento"**: ContoCassa (banche+contanti+assegni+direzione, con flag `nascondi_prima_nota` + `escludi_da_liquidita`) × ModalitàPagamento (bonifico/assegno/contanti/POS/RID/Bancomat) = TipoPagamento. Selettore unificato `<SelectTipoPagamento />` usato in TUTTI i dialoghi di incasso/uscita/giroconti.
- ✅ **Configurazione Comunicazioni unica** (Librerie → tab "Comunicazioni"): SMTP + Twilio SMS + Twilio WhatsApp + pulsante "Test invio" per ogni canale.
- ✅ **Diario personale collaboratore** (`/diario`): aggrega note libere + storico comunicazioni inviate (email/sms/whatsapp) + chat. Filtri per tipo, ricerca testo.
- ✅ **No pagination ovunque**: Polizze/Titoli/Sinistri mostrano TUTTI gli elementi (limite backend bumpato a 50000). Default Polizze=Attive, Titoli=Tutti da incassare.
- ✅ **Colonne tabellari**: "Contratto / Targa" SEPARATA in 2 colonne distinte in Titoli + Polizze.
- ✅ **Sticky tables**: Header in alto + prime 3 colonne congelate a sinistra. Applicato a Titoli, Polizze, Sinistri, Anagrafiche, Estratto Conto Compagnie, Prima Nota, Avvisi.
- ✅ **Modulo Veicolo dinamico**: tab "Veicolo" visibile per ramo=RCAUTO O prodotto contenente "RCA". Lookup automatico nel libro matricola digitando la targa (autocompila marca/modello/immatricolazione/ecc).
- ✅ **Rimossi tab legacy** "Mapping Garanzie/Operatori ANIA" da Librerie (endpoints backend preservati per il wizard OMNIA).

### Sessioni precedenti
- OMNIA mapping wizard, Libro Matricola XLSX parser
- Mobile/Tablet responsive sidebar drawer
- Refactor cyclomatic complexity (ania_importer, alert_dispatcher)
- Bug fix "Titoli in copertura" missing in Prima Nota (bulk_copertura ora genera MovimentoContabile)

## File principali
- `/app/backend/server.py` (~9300 righe — refactor in routes/ in corso)
- `/app/backend/routes/librerie.py` (Tipi pagamento, Comunicazioni, Mezzi pagamento)
- `/app/backend/pdf_lettera_abbuono.py` (PDF reportlab + embedding firme)
- `/app/backend/db_models.py` (TipoPagamento, LetteraAbbuono, DiarioNota, flag ContoCassa)
- `/app/frontend/src/components/DialogLetteraAbbuono.jsx`, `SignaturePad.jsx`, `SelectTipoPagamento.jsx`
- `/app/frontend/src/pages/Diario.jsx`, `Librerie.jsx` (tab Comunicazioni + Tipi pagamento)

## Backlog (P1/P2)
### P1
- **Email integrata IMAP** (rimandata su richiesta utente): mini-mailbox interna per leggere/inviare email del collaboratore.
- **Filtri/sort per colonna** sui table headers (sort cliccabile su ogni colonna + filtri popover).
- **OCR Fatture** via Gemini 3 Flash.
- **Verifica polizza vs libretto** UI di confronto.

### P2
- Configurazione Alert provider (Email/SMS/WhatsApp) — ora c'è la base in Comunicazioni
- Redesign Piramide Soluzioni
- Integrazioni 3rd party (Google Calendar, M365)
- Refactor server.py in moduli routes/

## Credenziali test
Vedi `/app/memory/test_credentials.md`
