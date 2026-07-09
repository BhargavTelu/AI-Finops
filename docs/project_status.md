# Project Status

**Last updated: 2026-07-09.** This doc holds the *current* state only. Full
per-milestone detail (every task, bug, and test count) lives in
[changelog.md](changelog.md); feature order lives in
[STRATEGIC_IMPLEMENTATION_PLAN.md](STRATEGIC_IMPLEMENTATION_PLAN.md).

## Where we are

**The MVP is code-complete** (Phases 0–3 of the strategic plan, shipped
2026-06-11). Every code-side piece of the spec's done-condition exists:
landing → signup → connect → checklist → chart → forecast → budget/Slack
alert → CFO PDF → checkout → gating. 750 tests passing, 0 TypeScript errors,
production build green.

**The product is not launched.** Remaining before a real customer can pay is
founder ops, not code (~1-2 hours + DNS wait) — the full walkthrough is
[launch_setup_guide.md](launch_setup_guide.md):

1. Create the 3 Products/Prices in Stripe (test mode first) and set `STRIPE_PRICE_*` env vars
2. Register the Stripe webhook endpoint (`/api/webhooks/stripe`) and set `STRIPE_WEBHOOK_SECRET`
3. Apply pending migrations to Supabase: `20260611000000_add_email_digest_opt_out.sql`, `20260611120000_add_stripe_events.sql`
4. Set R2 credentials in Railway and sanity-check one report upload/download (SigV4 is unit-tested, never live-tested)
5. Run pre-deploy smoke: RLS probe, signup→chart on staging, one test-mode checkout end to end

**Next code work: Phase 4** (invoice reconciliation, Slack ack buttons, CFO
viewer seat, worker locks) — deliberately code-light; its done-condition is
**3 paying customers**, not features.

## Milestone history

| Milestone | Shipped | Changelog |
|---|---|---|
| M0 Foundation (Clerk + Supabase + RLS) | 2026-05-19 | [0.1.0](changelog.md) |
| M1 First integration + first chart (OpenAI) | 2026-05-19 | [0.2.0](changelog.md) |
| M2 Multi-provider + attribution wedge (Anthropic, Gemini validate-only, tags, Cost Explorer) | 2026-05-20 | [0.3.0](changelog.md) |
| M3 Intelligence layer (anomalies, budgets, Slack, recommendations) | 2026-05-21 → 06-10 | [0.4.0–0.6.0](changelog.md) |
| Gap analysis + test hardening (29 gaps, 103 tests, 4 prod bugs) | 2026-05-22 | [0.5.1](changelog.md) |
| UI redesign (M-DS → M-PREMIUM) + critical-audit fixes | 2026-06-11 | [Unreleased](changelog.md) |
| Plan Phases 0–3: trust wins, CFO PDF, Stripe billing + gating, forecast/landing/activation/weekly email — **MVP code-complete** | 2026-06-11 | [Unreleased](changelog.md) |

## Known debt

See [architecture.md](architecture.md) § Known V1 debt for the strategic
items. Documented-but-unfixed gaps (tests assert current behavior; Phase 4
pays down the first one):

- **Gap-02/05/08/10** — no distributed Redis lock on concurrent `aggregate_org`, `refresh_integration`, `detect_org`, `check_org`. Fix: `SET NX EX` lock decorator (planned in Phase 4).
- **Gap-11/12/13/14** — JWKS concurrent-refresh race and unknown-kid forced-refresh edge cases (`alg:none` is rejected). Fix: thread-safe JWKS cache.
- **Gap-23** — `send_slack_digest` TOCTOU: Slack post can succeed while the `slack_digests` idempotency INSERT fails. Fix: wrap both in a transaction.
- **mypy strict + black are aspirational, not enforced** — 199 mypy-strict errors / 78 files black would reformat (recorded 2026-06-11). De-facto gates: pytest + tsc + ESLint + targeted ruff. Schedule as deliberate hardening or amend CLAUDE.md's claim.
