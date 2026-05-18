# Project Status

## Current Milestone: M0 — Foundation

**Status:** Scaffolding complete. Ready to begin M0 feature implementation.

---

## What's done

- [x] Full monorepo scaffold (Next.js 14 + FastAPI + packages + infra)
- [x] All config files, dependency manifests, folder structure
- [x] Python venv created and dependencies installed (`apps/api/.venv`)
- [x] Node.js dependencies installed (`pnpm install`)
- [x] Initial DB migration with all tables and RLS policies
- [x] `pricing.yaml` with current model prices

## M0 Remaining (4 days)

- [ ] Wire up Clerk JWT verification in `deps.py` (`require_org`)
- [ ] Implement Clerk + Supabase auth flow in `apps/web`
- [ ] Create `users`, `organizations`, `organization_members` via Clerk webhooks
- [ ] Empty `/dashboard` route gated by auth
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
