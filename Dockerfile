# ---------- Dockerfile per Railway ----------
# Costruisce SOLO il backend Python del gestionale.
# Il frontend è servito separatamente (o come static bundle).
FROM python:3.11-slim

# Dipendenze di sistema minime (Pillow, WeasyPrint/reportlab, psycopg2 opz.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 \
    libjpeg-dev zlib1g-dev libfreetype6-dev \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia SOLO il backend (via .dockerignore escludiamo il frontend)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
    -r /app/requirements.txt

COPY backend/ /app/

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8001

EXPOSE 8001

# Railway inietta la variabile $PORT — la usiamo se presente, altrimenti 8001.
CMD sh -c "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001} --workers 2"
