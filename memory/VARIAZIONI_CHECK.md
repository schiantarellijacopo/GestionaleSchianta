# ✅ Checklist Variazioni Gestionale (PDF 1/07/2026)

Legenda: ✅ FATTO · 🟡 IN CORSO · ⏳ PIANIFICATO · ⏸ DEFERRED · ❓ DA CHIARIRE

| # | Modifica | Stato | Note |
|---|---|---|---|
| 1 | Annulla applicazione libro matricola (vendita/demolizione/…) | ✅ | Dialog "Annulla" con motivo + data (incl. `POST /polizze/{pid}/applicazioni/{aid}/annulla`) |
| 2 | Cross-targa: cerca stessa targa in altre polizze | ✅ | `TargaConflictWidget` in Libro Matr. + PolizzaDetail |
| 3 | Mappa in anagrafica cliente + immobili + veicoli | ⏳ | Prossima iter — Leaflet + geocode |
| 4 | Raccolta Dati + Potenti Domande gestibili in Librerie (CRUD) | ⏳ | Prossima iter — modello DB `questionari_libreria` |
| 5 | Data scadenza polizza = ultimo titolo incassato/coperto | ✅ | `GET /polizze/{id}` ora ritorna `copertura_fino_a` e `ultimo_titolo_*` |
| 6 | Setup agenziale: estratto conto compagnie non riporta dati | ❓ | Manda screenshot per dettagli |
| 7 | Ritenute in prima nota con segno – + saldo iniziale solo in saldo | ⏳ | Revisione logica movimenti da fare |
| 8 | Rinominare "Mezzo pagamento" → "Tipo pagamento" nelle polizze | ✅ | Label aggiornata in PolizzaDetail |
| 9 | Sezione Regolazione premio mancante | ❓ | Dialog Regolazione Premio esiste già — chiarire dove serve la "sezione" |
| 10 | Elenco documenti | ❓ | Chiarire scopo (lista categorie? tipi doc con conteggi?) |
| 11 | Libretto sempre visibile + N certificati per frazionamento (verdi in Dashboard) | 🟡 | Categorie visibili default OK (#24). Ora libretto/certificato/quietanza/foto allegabili **per singolo veicolo** in Libro Matricola (dialog "Documenti veicolo") — logica N/frazionamento resta da fare |
| 12 | Termini disdetta + tacito rinnovo + periodo mora nella Librerie Prodotto | ✅ | Aggiunti 3 campi al form Prodotto |
| 13 | Sezione "Altri dati" → solo Nota | ✅ | Tab "Altri" ora mostra una nota unificata |
| 14 | Scambio dati: Agenzia Sorgente vs Agenzia Ricevente | ⏳ | Rename ruoli nella pagina Scambio Dati |
| 15 | Libri matricola censiti non visibili altrove | ✅ | Pagina standalone `/libro-matricola` con tabella filtrabile |
| 16 | Libreria Ramo · associazione 3D (Ramo→Prodotto→Garanzie) + fix data/frazionamento/collaboratore | ⏳ | Prossima iter — refactor mapping |
| 17 | Invia avvisi: scegli canale + salva in Storico + Diario cliente | 🟡 | Storico OK; **da aggiungere: dopo invio scrive anche in `db.diario_cliente`** |
| 18 | Modifica messaggio WhatsApp in libreria non salvava | ✅ | Fix stale-state React nel ModelloFormDialog |
| 19 | Alert Automazioni: lista con testi pregenerati + tasto Invia manuale | ⏳ | Prossima iter — pagina Alert Studio con bulk selezionabile |
| 20 | Filtri Eventi cross-entità (polizze/sinistri/titoli) | ⏳ | Legato a #19 |
| 21 | Pipeline email — cosa fanno? | ❓ | Attendo tua descrizione uso previsto |
| 22 | Sposta Liste Leads in sezione Marketing | ✅ | Sidebar: sezione "Marketing" creata; Liste Lead spostate lì |
| 23 | Marketing: import→lista→bottone Invia (email auto, WhatsApp manuale) + diario | ⏳ | Prossima iter — pagina Campagne |
| 24 | Documenti visibili default: polizza+condizioni+quietanze+libretto pagamento; interni: CI+altro | ✅ | Categorie polizza aggiornate: default_visibile=true per doc business |
| 25 | Integrazione Google Drive come storage | ⏸ | Attendo tua decisione (Solo lettura vs bidirezionale) |

## 📊 Stato aggregato
- ✅ **11** completate
- 🟡 **2** in corso (parzialmente)
- ⏳ **8** pianificate per prossime iterazioni
- ❓ **4** in attesa di chiarimento
- ⏸ **1** deferred
- **Tot 26** (25 da PDF + 1 sub)

## 🎯 Prossimo blocco proposto (P0)
1. #17 completare: salvare invio avviso anche nel `diario_cliente`
2. #3 mappa anagrafica (Leaflet + Nominatim geocode)
3. #4 CRUD Raccolta Dati + Potenti Domande in Librerie
4. #16 associazione 3D Ramo→Prodotto→Garanzie
5. #19 + #20 pagina "Alert Studio" per invio manuale bulk WhatsApp/Email/SMS
