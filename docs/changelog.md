# Changelog

All notable changes to the AI FinOps Platform.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [Unreleased]

### Added
- Initial project scaffold: monorepo structure, all config files, dependency manifests
- `apps/web` — Next.js 14 App Router skeleton with Clerk auth, Tailwind, shadcn/ui
- `apps/api` — FastAPI + Celery skeleton with all routers, schemas, services, and workers stubbed
- `packages/types` — Shared TypeScript types (API + DB)
- `packages/pricing` — `pricing.yaml` fallback table (Jan 2025 prices)
- `infra/migrations/20240101000000_initial_schema.sql` — Full schema with RLS
- `infra/scripts/` — smoke-test.sql, seed.sql, bootstrap.sh
- Python venv at `apps/api/.venv`
- `docker-compose.yml` for local Redis + api + worker

---
