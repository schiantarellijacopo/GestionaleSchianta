# Migrazione Produzione → Railway — Gestionale Schianta

Guida specifica per il progetto Railway **"Gestionale Schianta + API Whatsapp"**
(servizi già presenti: GestionaleSchianta · MongoDB · API Evolution · Redis · Postgres).

L'obiettivo è portare su Railway: **(1) il codice aggiornato**, **(2) le variabili d'ambiente**,
**(3) i dati di MongoDB**. I file/allegati restano (per ora) sull'object storage Emergent — vedi §5.

---

## 1. Codice → repo GitHub di Railway
Railway distribuisce dal repo `gestionaleschianta-production`.
1. In Emergent: **Save → Save to GitHub** → invia al repo collegato a Railway.
2. Railway rileva il push e **ri-distribuisce** automaticamente il servizio *GestionaleSchianta*.
   (Così arrivano anche le ultime correzioni: prima nota sincronizzata + provvigioni negative.)

> ⚠️ Verifica che il servizio GestionaleSchianta su Railway abbia **due processi** o due servizi:
> backend (FastAPI, porta 8001) e frontend (React build servita staticamente). Se è un monoservizio,
> usa i Dockerfile in `deploy/` (vedi §6).

---

## 2. Variabili d'ambiente — servizio BACKEND (GestionaleSchianta)
Imposta in Railway → GestionaleSchianta → **Variables**. Usa i *reference* Railway dove indicato.

### Obbligatorie (core)
| Variabile | Valore |
|---|---|
| `MONGO_URL` | `${{MongoDB.MONGO_URL}}` (reference al servizio MongoDB) |
| `DB_NAME` | `gestionale_schianta` (o il nome che preferisci) |
| `JWT_SECRET` | una stringa random lunga (usa `openssl rand -hex 32`) |
| `SECRET_KEY` | altra stringa random |
| `APP_NAME` | `assicura` (⚠️ deve restare `assicura`: è il prefisso dei path file già salvati) |
| `CORS_ORIGINS` | URL pubblico del frontend, es. `https://<frontend>.up.railway.app` |
| `PUBLIC_BASE_URL` / `BACKEND_PUBLIC_URL` | URL pubblico del backend |
| `FRONTEND_URL` | URL pubblico del frontend |
| `ADMIN_EMAIL` | `jacopo@schiantarelli.it` |
| `ADMIN_PASSWORD` | (solo per il primo seed; poi puoi rimuoverla) |

### File / Object storage  → vedi §5
| `EMERGENT_LLM_KEY` | la chiave Emergent (necessaria per allegati + funzioni AI/OCR) |

### WhatsApp (collega alla tua API Evolution su Railway)
| Variabile | Valore |
|---|---|
| `WHATSAPP_API_URL` | URL dell'API Evolution, es. `https://evolution-api-production-44….up.railway.app` (o interno `http://${{API Evolution.RAILWAY_PRIVATE_DOMAIN}}:8080`) |
| `WHATSAPP_API_KEY` | la `AUTHENTICATION_API_KEY` configurata nel servizio API Evolution |
| `WHATSAPP_INSTANCE` | il nome dell'istanza WhatsApp creata in Evolution |
| `WA_ANTISPAM_MIN_SEC` | es. `3` |
| `WA_ANTISPAM_MAX_SEC` | es. `8` |

### Email (scegli Resend OPPURE SMTP)
`RESEND_API_KEY`, `SENDER_EMAIL` — oppure — `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_FROM`.

### SMS (opzionale, Twilio)
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`.

### Firma elettronica FES (OpenAPI.it) — se la usi
`OPENAPI_IT_CLIENT_ID`, `OPENAPI_IT_CLIENT_SECRET`, `OPENAPI_IT_BEARER_TOKEN`,
`OPENAPI_IT_ENV` (`sandbox`/`production`), `OPENAPI_ESIGNATURE_SANDBOX`.

### Voce / altre integrazioni (opzionali)
`ELEVENLABS_API_KEY`, `GOOGLE_DRIVE_*`, `GOOGLE_CONTACTS_*`, `MS_ONEDRIVE_*`,
`CLOUD_STORAGE_ENCRYPTION_KEY`, `GOOGLE_TOKEN_KEY`.

> Recupera i valori attuali da Emergent: **Republish → Secrets** e **System keys**.

---

## 3. Variabili d'ambiente — servizio FRONTEND
| Variabile | Valore |
|---|---|
| `REACT_APP_BACKEND_URL` | URL pubblico del **backend** su Railway (senza `/api` finale) |

> Il frontend va **ri-buildato** dopo aver impostato questa variabile (è letta al build-time).

---

## 4. Copia dei dati MongoDB (Emergent → Railway)
Serve la connessione del Mongo **di produzione Emergent** (da Republish → Database)
e quella del **MongoDB Railway** (Variables → `MONGO_URL`, usa la *public* connection).

Usa lo script `scripts/migrate_data_emergent_to_railway.sh` (vedi file). In sintesi:
```bash
export SRC_MONGO_URL="mongodb+srv://...emergent-atlas..."   # da Republish → Database
export DST_MONGO_URL="mongodb://...railway-public..."        # da Railway → MongoDB → Variables
export SRC_DB="<nome_db_emergent>"                           # da System keys (DB_NAME)
export DST_DB="gestionale_schianta"
bash scripts/migrate_data_emergent_to_railway.sh
```
Esegui la copia **quando nessuno sta lavorando**, per non perdere modifiche.
Dopo il restore, verifica i conteggi (lo script li stampa) e fai login su Railway.

---

## 5. File / allegati (object storage)
Oggi i file stanno sull'**object storage Emergent** (`storage.py` → `integrations.emergentagent.com`),
e in MongoDB c'è solo il **percorso** (`allegati.storage_path`, prefisso `assicura/...`).

Due scenari:
- **Minimo (consigliato per il primo avvio):** imposta `EMERGENT_LLM_KEY` anche su Railway.
  Gli upload/download continueranno a funzionare usando lo storage Emergent. **Non serve copiare i file.**
  Resti però dipendente da Emergent per i documenti.
- **Indipendenza totale (futuro):** aggiungi un servizio **S3/MinIO** su Railway, sostituisci
  `backend/storage.py` con un adattatore S3 e copia i file dal vecchio storage. Oggi nel tuo stack
  Railway non c'è un servizio storage, quindi questo passo è opzionale e successivo.
  (Posso prepararti adattatore S3 + script di travaso quando vorrai.)

---

## 6. Dockerfile (se GestionaleSchianta è un monoservizio)
Vedi cartella `deploy/`:
- `deploy/Dockerfile.backend` — FastAPI su `uvicorn ... --port 8001`
- `deploy/Dockerfile.frontend` — build React servita con `serve`/nginx
Su Railway puoi creare due servizi dal repo puntando ai rispettivi Dockerfile,
oppure usare il Nixpacks di default se i comandi di start sono corretti.

> **Build context = radice del repo.** I Dockerfile fanno `COPY backend/` e `COPY frontend/`,
> quindi vanno buildati dalla root: `docker build -f deploy/Dockerfile.backend .`
> Per il frontend passa l'URL backend come build-arg:
> `docker build -f deploy/Dockerfile.frontend --build-arg REACT_APP_BACKEND_URL=https://<backend> .`
> Su Railway: imposta il *Root Directory* del servizio sulla radice e il *Dockerfile Path* su
> `deploy/Dockerfile.backend` (o `.frontend`); per il frontend aggiungi `REACT_APP_BACKEND_URL`
> tra le variabili (viene usata anche come build arg).

---

## 7. Checklist finale
- [ ] Codice pushato sul repo Railway (Save to GitHub) e deploy GestionaleSchianta andato a buon fine
- [ ] Variabili backend + frontend impostate (specie `MONGO_URL`, `REACT_APP_BACKEND_URL`, WhatsApp)
- [ ] Dati MongoDB copiati e conteggi verificati
- [ ] Login `jacopo@schiantarelli.it` OK su Railway
- [ ] Titoli/contabilità presenti e corretti; allegati apribili
- [ ] Istanza WhatsApp (Evolution) connessa e invio messaggio di test OK
- [ ] Deciso quale ambiente è la produzione UNICA (per evitare dati doppi)
