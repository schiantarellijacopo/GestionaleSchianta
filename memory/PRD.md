# Assicura CRM — PRD / Memory

## Prodotto
CRM assicurativo multi-tenant. Stack: React + FastAPI + MongoDB.
Multi-tenancy: scoping automatico via `agenzia_tenant_id` (ContextVar in `database.py`, mai `tenant_id`).

## Credenziali test
Vedi `/app/memory/test_credentials.md` (admin@assicura.it / Admin123!).

## Modulo Carichi Mensili
- Backend: `/app/backend/routes/carichi_mensili.py` (`GET /api/carichi-mensili`).
- Frontend: `/app/frontend/src/pages/CarichiMensili.jsx`.
- Titoli importati → `stato_carico=in_attesa`; validati → `validato` (visibili nello Storico).
- Pagina Carichi Mensili usa `stato_carico=attivi` (tutto tranne i validati).
- Storico: riuso di `CarichiMensili.jsx` con prop `storico` (sola lettura), `stato_carico=validato`.

### Ricerca & filtri
- `q` cerca numero polizza, targa, cliente, compagnia; si combina con date/compagnia/operatore.
- Senza date → ricerca globale; con date → limitata al range decorrenza/effetto.
- Totali calcolati sull'intero set filtrato (lordo, netto, provvigioni, margine, provvigioni collaboratore).

### Import CSV/XLS
- Dedup carichi in_attesa per `polizza + scadenza`.
- Date a due cifre normalizzate in ISO (`_to_iso_date`).

## Implementato (changelog recente)
- 2026-06: Colonna **Metodo Pagamento** eredita dalla polizza (`mezzo_pagamento_preferito` → `ultimo_mezzo_pagamento`) quando il titolo non ha valore proprio. Backend `carichi_mensili.py` (proiezione polizze + build riga).
- Ricerca combinata q + date + compagnia + operatore.
- Dedup import + normalizzazione date.
- Filtro compagnia + totali full-set.
- Sezione Storico (sola lettura) per titoli validati.

## Backlog / Da verificare
- E2E Storico: validare titolo → sparisce da Carichi Mensili → appare in Storico (sola lettura).
- Verifica route/sidebar Storico dopo ultime modifiche.
