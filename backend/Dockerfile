# The API for Google Cloud Run (see ../DEPLOY.md). Build context is this folder.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    NBA_SOURCE=live \
    NBA_SNAPSHOT=1 \
    NBA_DB=/tmp/nba.db

WORKDIR /app
COPY pyproject.toml ./
COPY nbadash ./nbadash
RUN pip install --no-cache-dir ".[cloud]"

# Cloud Run sets $PORT. The database is downloaded from R2 at start-up (nbadash.snapshot) into /tmp.
CMD exec uvicorn nbadash.app:app --host 0.0.0.0 --port ${PORT:-8080}
