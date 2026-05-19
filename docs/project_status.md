# Project Status

## Current Milestone: M1 — First Integration + First Chart

**Status:** Starting M1. M0 verified complete 2026-05-19.

---

## M1 Tasks

- [ ] `POST /integrations` route — validate OpenAI Admin key, AES-256 encrypt, insert row, enqueue backfill
- [ ] `GET /integrations` route — list integrations (redacted keys)
- [ ] `DELETE /integrations/:id` route — revoke + delete
- [ ] OpenAI adapter (`adapters/openai.py`) — `/v1/organization/costs` + `/v1/organization/usage/completions`, cursor pagination
- [ ] Celery `backfill_integration` task — pull 30d history on key connect (target < 5 min)
- [ ] Celery `refresh_integration` task — incremental fetch since `last_synced_at`, every 4h
- [ ] Celery `aggregate_org` task — GROUP BY (day, provider, model, tags) → UPSERT `daily_cost_summaries`
- [ ] `GET /usage/summary` — MTD, yesterday, 7d, 30d totals from `daily_cost_summaries`
- [ ] `GET /usage/timeseries` — daily points for 30d line chart, grouped by model
- [ ] Settings/integrations page — connect OpenAI key form + list connected keys
- [ ] Dashboard page — MTD/yesterday stat cards + 30d line chart (Tremor) + by-model bar chart
- [ ] Pydantic schemas for integrations + usage routes

**M1 done-condition:** Connect your own OpenAI key. Numbers match OpenAI dashboard. Show one design partner → they want access.

**Out of scope for M1:** Anthropic, Gemini, tagging, anomalies, Slack, payment.

---

## Completed Milestones

### M0 — Foundation ✅ (verified 2026-05-19)

- [x] Full monorepo scaffold (Next.js 14 + FastAPI + packages + infra)
- [x] All config files, dependency manifests, folder structure
- [x] Python venv + Node.js dependencies installed
- [x] Initial DB migration — all tables, indexes, RLS policies
- [x] `pricing.yaml` with current model prices
- [x] Clerk JWT verification in `deps.py` (`_require_org`) — RS256 JWKS, extracts user_id + org_id
- [x] Clerk webhook handler (`/api/webhooks/clerk`) — user, org, membership sync + `db_id` write-back to Clerk metadata
- [x] `clerk_id` columns migration applied to Supabase (`infra/migrations/20260519000000_add_clerk_id_to_identity_tables.sql`)
- [x] Clerk middleware at `apps/web/src/middleware.ts` — route protection active
- [x] `/sign-in` and `/sign-up` pages (Clerk components)
- [x] `/create-org` page — org creation flow (`<CreateOrganization />`)
- [x] `/dashboard` gated by auth + org — redirects to `/create-org` if no active org
- [x] Dashboard sidebar (nav links + `<OrganizationSwitcher />`) and header (`<UserButton />`)
- [x] Supabase server client injects Clerk HS256 JWT for RLS
- [x] Two-tenant SQL probe passes (`infra/scripts/smoke-test.sql` — requires `SET LOCAL ROLE authenticated`)
- [x] End-to-end verified: two real users, two real orgs, RLS isolation confirmed

---

## Upcoming Milestones

| Milestone | Focus | Days |
|---|---|---|
| M2 | Multi-provider + tagging + Cost Explorer | 11 |
| M3 | Anomaly detection + budgets + Slack | 11 |
| M4 | Billing + CFO PDF + polish + landing page | 9 |

---

## Open Questions (resolve before M1 ships)

1. Anthropic Enterprise Analytics API — is it Enterprise-gated? → affects M2 timeline
2. Gemini billing granularity — verify in M2 week 1
3. Stripe trial: 14 days vs none?
4. Entry price: $299 vs $99 for top-of-funnel experiment?

---

## Known Debt

See `architecture.md` § Known V1 debt.
