# Project Status

## Current Milestone: M0 — Foundation

**Status:** Feature implementation complete. Pending: apply DB migration to Supabase + run smoke test.

---

## What's done

- [x] Full monorepo scaffold (Next.js 14 + FastAPI + packages + infra)
- [x] All config files, dependency manifests, folder structure
- [x] Python venv created and dependencies installed (`apps/api/.venv`)
- [x] Node.js dependencies installed (`pnpm install`)
- [x] Initial DB migration with all tables and RLS policies
- [x] `pricing.yaml` with current model prices
- [x] Clerk JWT verification in `deps.py` (`_require_org`) — RS256 JWKS, extracts user_id + org_id
- [x] Clerk webhook handler (`/api/webhooks/clerk`) — user, org, membership sync + metadata write-back
- [x] `clerk_id` migration written and tracked (`infra/migrations/20260519000000_add_clerk_id_to_identity_tables.sql`)
- [x] Clerk middleware at `apps/web/src/middleware.ts` — route protection active
- [x] `/sign-in` and `/sign-up` pages
- [x] `/create-org` page — org creation flow using Clerk `<CreateOrganization />`
- [x] `/dashboard` route gated by auth + org (redirects to `/create-org` if no active org)
- [x] Dashboard sidebar with nav links + `<OrganizationSwitcher />`
- [x] Dashboard header with `<UserButton />`
- [x] Supabase server client updated to inject Clerk HS256 JWT for RLS

## M0 Remaining (operational — no more code changes)

- [ ] Apply migration to Supabase: `ALTER TABLE users ADD COLUMN clerk_id TEXT UNIQUE; ALTER TABLE organizations ADD COLUMN clerk_id TEXT UNIQUE;`
- [ ] Configure Clerk + Supabase per `docs/setup.md` (JWT template, JWT secret, env vars)
- [ ] Two-tenant SQL probe passes (run `infra/scripts/smoke-test.sql`)

**M0 done-condition:** Two users sign up to separate orgs, can't read each other's rows.

---

## Upcoming Milestones

| Milestone | Focus | Days |
|---|---|---|
| M1 | OpenAI integration + first chart | 7 |
| M2 | Multi-provider + tagging + Cost Explorer | 11 |
| M3 | Anomaly detection + budgets + Slack | 11 |
| M4 | Billing + CFO PDF + polish + landing page | 9 |

---

## Open Questions (resolve before M1)

1. Anthropic Enterprise Analytics API — is it Enterprise-gated? → affects M2 timeline
2. Gemini billing granularity — verify in M2 week 1
3. Stripe trial: 14 days vs none?
4. Entry price: $299 vs $99 for top-of-funnel experiment?

---

## Known Debt

See `architecture.md` § Known V1 debt.
