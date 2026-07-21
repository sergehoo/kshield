FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Libs natives :
#   - GDAL/GEOS/PROJ : PostGIS + django.contrib.gis
#   - Cairo/Pango : rendu PDF badges
#   - OpenCV/SM/XRender : pipeline face recognition (InsightFace + SilentFace)
#   - poppler/tesseract : OCR pièces identité visiteurs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    curl \
    gettext \
    libpq-dev \
    binutils \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libglib2.0-0 \
    libsm6 libxext6 libxrender1 libgl1 \
    shared-mime-info \
    fonts-dejavu-core \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# Pré-télécharge buffalo_s (~16 Mo) au build pour éviter le cold-start prod.
# Si /root/.insightface est monté en volume au runtime, sera écrasé.
RUN python -c "import insightface; insightface.app.FaceAnalysis(name='buffalo_s').prepare(ctx_id=-1, det_size=(640,640))" \
    || echo "WARN: pré-téléchargement buffalo_s ignoré (offline build)."

COPY . /app/

RUN mkdir -p /app/staticfiles /app/media /app/logs /app/models/silentface

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
  CMD curl -fsS -o /dev/null \
        -H "Host: ${BASE_DOMAIN:-localhost}" \
        -H "X-Forwarded-Proto: https" \
        http://127.0.0.1:8000/healthz || exit 1

CMD ["gunicorn", "kshield.asgi:application", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "120"]
