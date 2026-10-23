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
- 2026-06: **Storico Carichi spostato dalla sidebar a un pulsante dentro Carichi Mensili.** Rimossa la voce `carichi-storico` da `Sidebar.jsx`; aggiunto pulsante "Storico Carichi" (icona Archive) nell'header di Carichi Mensili e pulsante "Carichi Mensili" per tornare indietro dall'header Storico. Confermato che Storico Carichi mostra solo `stato_carico=validato` (sola lettura) — frontend invia `stato_carico=validato`, backend filtra correttamente (admin tenant: validato 43, in_attesa 0; tenant reale validato scad. 2026-10 = 98).
- 2026-06: **Isolamento tenant rafforzato (regola critica: i dati di ogni tenant restano separati)**. Rimossi 645 titoli corrotti che puntavano a polizze di un altro tenant. L'import ora lega esplicitamente il titolo al tenant della sua polizza (`agenzia_tenant_id` dalla polizza) in entrambi i percorsi (import automatico + abbinamento manuale). Verificato: import nel tenant c5ae2d0e crea il titolo nello stesso tenant.
- 2026-06: Dedup carichi per `polizza_id + effetto` (decorrenza) invece di `scadenza` — la scadenza poteva divergere (colonna "Scad. copertura" vs calcolata) causando falsi doppioni. Il re-import ora sovrascrive i dati (provvigioni comprese) e collassa i duplicati residui. Puliti i doppioni storici.
- 2026-06: Colonna **Metodo Pagamento** mostra SOLO il tipo pagamento preferito della polizza (`mezzo_pagamento_preferito`).
- Ricerca combinata q + date + compagnia + operatore.
- Filtro compagnia + totali full-set.
- Sezione Storico (sola lettura) per titoli validati.
- 2026-06: **Titoli storici (/titoli-storici) resi archivio sola lettura.** In `Titoli.jsx` con `storicoMode`: `buildParams` forza sempre `stato=incassato` (titoli passati in prima nota), rimosse colonne selezione+azione e barra bulk INCASSO, disabilitati edit/delete. Filtro periodo default su **Data incasso** (prima era "scadenza" → i filtri date non restituivano risultati). "Azzera filtri" ora ripristina il preset storico (storico_anno) invece di "sospesi" (che mostrava titoli da incassare col pulsante Incasso). Verificato UI + curl (data_incasso 2026→9, 2020→0).

## Note tenant
- Dati reali nel tenant `c5ae2d0e-...` (26k polizze, 57k titoli, 23 utenti).
- Account test admin@assicura.it = tenant `tenant-principale-schiantarelli` (dati minimi, NON il tenant reale).
- Un titolo deve SEMPRE avere lo stesso `agenzia_tenant_id` della sua polizza.

## Backlog / Da verificare
- E2E Storico: validare titolo → sparisce da Carichi Mensili → appare in Storico (sola lettura).
- Verifica route/sidebar Storico dopo ultime modifiche.
