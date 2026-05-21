# CLAUDE.md

Read this first. Then read the doc linked under §Documentation that's relevant to the task.

## Project

**AI FinOps Platform** — SaaS that gives AI startups per-feature/team/customer cost attribution, anomaly alerts, and savings recommendations for LLM API spend (OpenAI, Anthropic, Gemini).

**ICP:** CTO at AI-native SaaS, $1M–$50M ARR, $5K–$80K/mo LLM spend.
**Wedge:** Finance-first (CFO PDF, per-customer attribution) at mid-market pricing ($299–$1,500/mo).

## Architecture (one-liner)

Next.js (Vercel) → FastAPI (Railway) → Supabase Postgres. Celery + Upstash Redis for ingestion + nightly aggregation + anomaly detection + budget alerts. Clerk auth. Stripe billing. No customer traffic flows through us — we pull from provider Admin APIs.

**Current milestone: M3 (Intelligence Layer)** — M0, M1, M2, M3-A (Anomaly Detection), M3-B (Budgets + Email Alerts), M3-C (Slack Integration) complete. Starting M3-D (Recommendations Engine).

Full stack table and schema → [docs/architecture.md](docs/architecture.md).

## Code Style

- **TypeScript:** strict mode, no `any` without a comment. Use server components by default in `/apps/web`.
- **Python:** 3.11+, `ruff` + `mypy` + `black`. Type everything. Async by default in FastAPI.
- **Naming:** snake_case in Python, camelCase in TS, kebab-case for file/route names, UPPER_SNAKE for env vars.
- **No barrel files.** Import from full paths.
- **Imports:** stdlib → third-party → local, separated by blank line.
- **No comments that restate the code.** Comment the *why*, not the *what*.
- **Pure functions where possible.** Side effects belong in workers, route handlers, or explicitly named `*_service` modules.

## UI Style

**Component library:** shadcn/ui + Tailwind. No custom CSS unless shadcn can't do it.
**Charts:** Tremor first, Recharts for custom shapes.
**Tables:** TanStack Table (required for Cost Explorer pivot).
**Motion:** Framer Motion installed. Use for:
  - Page/route transitions (fade + slide, 200ms)
  - Dashboard number counters (animate on load)
  - Empty state illustrations entering
  - Alert/toast entrance (slide-in from top-right)
  - DO NOT use for table rows, chart renders, or anything in a list > 10 items (perf)

**Design tokens (use consistently):**
  - Font: Inter (already in shadcn)
  - Radius: rounded-xl for cards, rounded-lg for buttons, rounded-md for inputs
  - Spacing: 4px base grid (Tailwind default)
  - Dashboard bg: bg-background, cards: bg-card with border
  - Accent: use your primary color from shadcn theme

**Every screen needs:**
  - Empty state (with a clear CTA, not just "no data")
  - Loading skeleton (not a spinner — use shadcn Skeleton)
  - Error state with a retry action

## Constraints & Policies

**Hard rules (don't break, don't ask):**

1. **No customer traffic through our servers.** Pull from Admin APIs only. No proxy mode in MVP.
2. **Admin API keys never reach the frontend.** Server action encrypts via pgcrypto AES-256-GCM, form resets, key is never returned.
3. **RLS on every org-scoped table.** Policy: `org_id = (auth.jwt()->>'org_id')::uuid`. Two-tenant probe before deploy.
4. **No PII in logs.** Logs contain `org_id`, `request_id`, `actor_user_id` — never emails, names, or key material.
5. **AI cost cap:** ≤ $0.05/org/day. Hard rate limit (3 calls/org/day) enforced in Redis. Only aggregated summaries in prompts, never raw events.
6. **No new dependencies without checking weight.** Justify anything > 50KB or anything with > 5 transitive deps. Prefer stdlib + existing stack.
7. **No SOC 2 / SAML / white-label / mobile app / multi-cloud cost work.** All deferred. If asked, push back.

**Soft rules (default behavior unless told otherwise):**

- Build the smallest thing that proves the milestone done-condition. Cut scope before cutting time.
- Statistics before ML. Linear regression for forecasts, rolling mean + 2σ for anomalies.
- One good dashboard beats five mediocre ones. Resist scope creep into custom dashboards.
- Slack > email > in-app notification, in that order of stickiness.
- If a feature can ship as a rule-based version first and an AI version later, ship rule-based first.

## Repository Etiquette

- **Branches:** `feat/<short>`, `fix/<short>`, `chore/<short>`. No work directly on `main`.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`). Imperative mood. One logical change per commit.
- **PRs:** must pass lint + typecheck + tests. Squash-merge to `main`. Title in Conventional Commit format.
- **Migrations:** forward-only. Rollbacks happen via a new migration. Migration files in `/infra/migrations`, prefixed with UTC timestamp.
- **Secrets:** never committed. `.env.example` only. Actual values in Vercel/Railway dashboards or Supabase Vault.
- **Generated files** (`.next`, `__pycache__`, `dist`, coverage) are gitignored. Never commit them.
- **One issue / task → one PR.** Don't bundle unrelated changes.

## Testing

- Unit-test the math: pricing calc, anomaly detection, tag-rule engine. Target 80% on these modules.
- One e2e happy path per milestone (mocked provider APIs).
- No frontend tests in MVP — visual review is faster than maintaining Playwright at this stage.
- Run `pnpm test` (web) and `pytest` (api) before pushing.

## Documentation

- [Project Spec](docs/project_spec.md) — Full requirements, FRs, milestones
- [Architecture](docs/architecture.md) — System design, schema, API, data flow
- [Setup](docs/setup.md) — Clerk JWT template + Supabase JWT secret (completed for M0; re-read before deploying to a new environment)
- [Changelog](docs/changelog.md) — Version history
- [Project Status](docs/project_status.md) — Current milestone, what's done, what's next
- Update files in the `docs/` folder after major milestones and major additions to the project.
- Use the `/update-docs-and-commit` slash command when making git commits.

## Keep This File Updated

CLAUDE.md is the source of truth for project context. Update it whenever:

- A hard rule changes (e.g., proxy mode unlocked in V2).
- The stack changes (DB swap, framework change, new core service).
- A new doc is added under `docs/` — link it in §Documentation.
- A constraint is lifted (e.g., SOC 2 work begins, mobile app reconsidered).
- A milestone completes — refresh §Architecture one-liner if topology shifted.

Edit this file in the same PR as the change. Don't leave stale instructions.
