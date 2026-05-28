#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh - First-time local dev environment setup.
# Run from the repo root: bash infra/scripts/bootstrap.sh
# =============================================================================
set -euo pipefail

echo "==> Checking prerequisites..."
command -v node   >/dev/null 2>&1 || { echo "node not found - install v20+"; exit 1; }
command -v pnpm   >/dev/null 2>&1 || { echo "pnpm not found - run: npm install -g pnpm"; exit 1; }
command -v python >/dev/null 2>&1 || { echo "python not found - install Python 3.11+"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "docker not found - install Docker Desktop"; exit 1; }

echo "==> Installing Node.js dependencies..."
pnpm install

echo "==> Creating Python virtual environment..."
cd apps/api
python -m venv .venv
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -e ".[dev]"
cd ../..

echo "==> Copying env examples (won't overwrite existing)..."
cp -n .env.example .env.local 2>/dev/null || true
cp -n apps/web/.env.local.example apps/web/.env.local 2>/dev/null || true
cp -n apps/api/.env.example apps/api/.env 2>/dev/null || true

echo ""
echo "==> Done! Next steps:"
echo "  1. Fill in apps/web/.env.local and apps/api/.env"
echo "  2. docker compose up -d redis"
echo "  3. pnpm dev          (Next.js)"
echo "  4. cd apps/api && uvicorn api.main:app --reload"
