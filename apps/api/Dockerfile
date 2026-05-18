FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps needed by cryptography and psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# ── Dev stage (mounts src via volume) ────────────────────────────────────────
FROM base AS dev
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .

# ── Production stage ─────────────────────────────────────────────────────────
FROM base AS production
COPY src/ src/
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
