# Always-on cloud API for the mobile app — reads Supabase (the cloud backup DB),
# so the phones work 24/7 even when the office PC is off.
#
# Build from the REPO ROOT:
#   docker build -f deploy/cloud-api/Dockerfile -t asw-api .
# Run:
#   docker run -p 8000:8000 --env-file deploy/cloud-api/cloud-api.env asw-api
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Deps first (better layer caching).
COPY deploy/cloud-api/requirements-api.txt /app/requirements-api.txt
RUN pip install --no-cache-dir -r requirements-api.txt

# Only the Python package is needed (no PyQt UI, no mobile/).
COPY timber /app/timber

EXPOSE 8000
# Cloud hosts inject $PORT; default to 8000 locally. Always bind 0.0.0.0.
CMD ["sh", "-c", "uvicorn timber.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
