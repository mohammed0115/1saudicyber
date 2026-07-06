# CyberTrust KSA — production-style image (Django + Gunicorn).
# Single-stage, slim Python base. Heavy OCR system packages (tesseract/poppler)
# are intentionally NOT installed: OCR is not used by the MVP workflow and the
# advisory analysis is text-based. Add them only if/when OCR is enabled.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=cybertrust_ksa.settings

WORKDIR /app

# gosu lets the entrypoint start as root (to self-heal mounted-volume ownership)
# and then drop to the unprivileged app user before launching the app.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# psycopg[binary] ships its own libpq, so no extra apt packages are required for
# PostgreSQL. Keep the image lean.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Application code (build context is filtered by .dockerignore: no .env, db, media).
COPY . .

# Create the unprivileged app user. NOTE: we intentionally do NOT `USER appuser`
# here — the entrypoint starts as root to fix ownership of mounted named volumes
# (which keep their first-create uid/gid), then drops to appuser via gosu. Running
# the app itself as root is still avoided.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app

EXPOSE 8000

ENTRYPOINT ["/app/deployment/docker/entrypoint.sh"]
CMD ["gunicorn", "cybertrust_ksa.wsgi:application", \
     "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
