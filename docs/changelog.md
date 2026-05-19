# Changelog

All notable changes to the AI FinOps Platform.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [Unreleased] — M1 in progress

---

## [0.1.0] — M0 Foundation (2026-05-19)

### Added

**Infrastructure & scaffold**
- Initial monorepo structure: `apps/web`, `apps/api`, `packages/types`, `packages/pricing`, `infra/`
- `apps/web` — Next.js 14 App Router skeleton with Clerk, Tailwind, shadcn/ui, Tremor, TanStack Table
- `apps/api` — FastAPI + Celery skeleton; all routers, schemas, services, and workers stubbed
- `packages/types` — shared TypeScript types (API responses + DB rows)
- `packages/pricing` — `pricing.yaml` fallback table (Jan 2025 prices for OpenAI, Anthropic, Gemini)
- `infra/migrations/20240101000000_initial_schema.sql` — full schema with RLS on all org-scoped tables
- `infra/migrations/20260518000000_add_slack_digests.sql` — `slack_digests` idempotency table
- `infra/migrations/20260518000001_add_updated_at_to_users_and_orgs.sql` — `updated_at` on identity tables
- `infra/migrations/20260519000000_add_clerk_id_to_identity_tables.sql` — `clerk_id TEXT UNIQUE` on `users` and `organizations` for webhook upsert idempotency
- `infra/scripts/smoke-test.sql` — two-tenant RLS isolation probe
- `infra/scripts/seed.sql` and `bootstrap.sh`
- `docker-compose.yml` for local Redis + api + worker
- Python venv at `apps/api/.venv`

**Auth**
- `apps/web/src/middleware.ts` — `clerkMiddleware` protecting all non-public routes
- `apps/web/src/app/(auth)/sign-in/` and `sign-up/` — Clerk-hosted auth UI
- `apps/web/src/app/create-org/page.tsx` — org creation page using `<CreateOrganization />`
- `apps/web/src/app/(dashboard)/layout.tsx` — auth + org guard, sidebar with `<OrganizationSwitcher />`, header with `<UserButton />`
- `apps/web/src/components/nav-links.tsx` — active-link nav client component
- `apps/web/src/lib/supabase/server.ts` — injects Clerk HS256 "supabase" template JWT so Supabase RLS reads `org_id` claim
- `apps/api/src/api/deps.py` — `_require_org()`: RS256 JWKS verification, `OrgDep` dependency
- `apps/api/src/api/routers/webhooks.py` — Clerk webhook handler: Svix signature verification, user/org/membership upsert, `db_id` write-back to Clerk `public_metadata`

### Fixed
- `infra/scripts/smoke-test.sql` — added `SET LOCAL ROLE authenticated` before SELECT probes; the `postgres` superuser bypasses all RLS `USING` clauses, making the probe always pass regardless of policy correctness

---
