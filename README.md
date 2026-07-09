# SpendOps AI

**LLM cost intelligence for AI startups.** Per-feature, per-team, and per-customer cost attribution, anomaly alerts, budgets, and savings recommendations for OpenAI, Anthropic, and Gemini API spend — built for CTOs and CFOs who need to know exactly where the money goes.

> **Status:** MVP code-complete — Phases 0–3 of the [Strategic Implementation Plan](docs/STRATEGIC_IMPLEMENTATION_PLAN.md) shipped (CFO PDF, Stripe billing + gating, forecast, activation checklist, landing page, weekly digest) on top of M0–M3. Remaining before launch is founder ops (see [docs/launch_setup_guide.md](docs/launch_setup_guide.md)); next code work is Phase 4 (trust & traction).

## What it does

- **Cost attribution** — pull usage from provider Admin APIs and break spend down by model, provider, feature, team, customer, or environment via a tag-rule engine. No customer traffic ever flows through our servers.
- **Cost Explorer** — pivot and filter spend across any dimension, with period-over-period comparison and CSV export.
- **Anomaly detection** — nightly rolling 7-day mean + 2σ detection per scope, with severity grading and Slack/email alerts.
- **Budgets** — monthly limits per scope with 80%/100% threshold alerts (idempotent, once per threshold per month).
- **Recommendations** — rule-based savings opportunities (model swaps, caching, batching) with estimated monthly savings.
- **Executive dashboard** — board-ready spend overview: KPI cards, spend trend, provider split, top models, open alerts.

## Architecture

```
Next.js 14 (Vercel) ──► FastAPI (Railway) ──► Supabase Postgres (RLS)
                              │
                              ├── Celery workers + Upstash Redis
                              │     ingestion · nightly aggregation ·
                              │     anomaly detection · budget checks
                              │
                              ├── Clerk (auth + orgs)   · Stripe (billing)
                              └── Resend (email)        · Slack (alerts)
```

Spend data is **pulled** from provider Admin APIs on a schedule — the platform is never in your request path. Admin API keys are encrypted server-side (pgcrypto AES-256-GCM) and never reach the frontend. Every org-scoped table is protected by Postgres row-level security.

Full system design, schema, and data flow: [docs/architecture.md](docs/architecture.md).

## Repository layout

```
apps/
  web/        Next.js 14 App Router · shadcn/ui · Tailwind · Tremor/Recharts
  api/        FastAPI · Celery workers · Pydantic v2 · Python 3.11+
packages/
  pricing/    Provider pricing tables (pricing.yaml)
  types/      Shared type definitions
infra/
  migrations/ Forward-only SQL migrations (UTC-timestamp prefixed)
  scripts/    Smoke tests and ops scripts
docs/         Spec, architecture, setup, status, changelog
```

## Getting started

### Prerequisites

- Node 20+ and pnpm 9
- Python 3.11+
- Docker (for Redis + API + workers)
- Accounts/keys: Supabase, Clerk, Upstash Redis (or local), Resend, Slack app (optional)

### 1. Configure environment

```bash
cp apps/api/.env.example apps/api/.env          # API, workers
cp apps/web/.env.local.example apps/web/.env.local  # Web
```

Fill in Supabase, Clerk, and Redis values. Clerk JWT template + Supabase JWT secret setup is documented in [docs/setup.md](docs/setup.md). Secrets are never committed — real values live in Vercel/Railway dashboards or Supabase Vault.

### 2. Run the backend stack

```bash
docker compose up        # redis + FastAPI (:8000) + celery worker + beat
```

### 3. Run the web app

```bash
pnpm install
pnpm dev                 # Next.js on :3000
```

## Development

| Task | Command |
|------|---------|
| Web dev server | `pnpm dev` |
| Web lint / typecheck | `pnpm lint` · `pnpm typecheck` |
| Web production build | `pnpm build` |
| API tests | `cd apps/api && pytest` |

Before pushing: `pnpm test` (web) and `pytest` (api) must pass. The API suite covers the money math — pricing calc, anomaly detection, tag rules — at 80%+ coverage.

### Conventions

- Branches: `feat/<short>`, `fix/<short>`, `chore/<short>` — no work directly on `main`
- Conventional Commits; PRs squash-merge to `main` and must pass lint + typecheck + tests
- Migrations are forward-only; rollbacks ship as new migrations
- Project rules and hard constraints live in [CLAUDE.md](CLAUDE.md)

## Documentation

| Doc | Contents |
|-----|----------|
| [Project Spec](docs/project_spec.md) | Requirements, FRs, milestones |
| [Architecture](docs/architecture.md) | System design, schema, API, data flow |
| [Strategic Implementation Plan](docs/STRATEGIC_IMPLEMENTATION_PLAN.md) | Source of truth for feature order (Phases 0–5) |
| [Setup](docs/setup.md) | Clerk JWT template + Supabase JWT secret |
| [Launch Setup Guide](docs/launch_setup_guide.md) | Founder ops: accounts, keys, webhooks, env vars to go live |
| [Project Status](docs/project_status.md) | Current milestone, what's done, what's next |
| [Changelog](docs/changelog.md) | Version history |

## Security model

- **No proxy mode** — usage is pulled from provider Admin APIs; customer traffic never transits this platform
- **Key handling** — admin keys are encrypted at rest with AES-256-GCM and are write-only from the frontend's perspective
- **Tenant isolation** — RLS policy `org_id = (auth.jwt()->>'org_id')::uuid` on every org-scoped table, verified by a two-tenant probe before deploy
- **No PII in logs** — logs carry `org_id` / `request_id` / `actor_user_id`, never emails, names, or key material
