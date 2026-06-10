# Build context is the REPO ROOT (see docker-compose.yml), not apps/api -
# the image needs packages/pricing/pricing.yaml from outside this directory.
FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps needed by cryptography and psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# hatchling editable builds need the package sources present at install time
COPY apps/api/pyproject.toml .
COPY apps/api/src/ src/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Shared pricing table - resolved at runtime by walking up from src/
COPY packages/pricing/ packages/pricing/

# ── Dev stage (mounts src via volume) ────────────────────────────────────────
FROM base AS dev
RUN pip install --no-cache-dir -e ".[dev]"
COPY apps/api/ .

# ── Production stage ─────────────────────────────────────────────────────────
FROM base AS production
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
