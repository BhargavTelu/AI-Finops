# Implementation Guide - SpendOps AI

Companion to `project_spec.md` (what + scope) and `architecture.md` (how).
This file is the **build checklist**: per milestone, the tasks to complete and the
gate that proves the milestone is actually done.

**How to use this with Claude Code:**
- Work milestones in order. Do not start a milestone until the previous one's
  **Done gate** passes.
- A task is checked only when it works end to end on `staging`, not when it compiles.
- FR-IDs (e.g. FR-3) refer to the functional requirements table in `project_spec.md`.
  This guide does not restate them - it tracks completion.
- No calendar dates. Milestones are relative: each begins when the prior gate passes.
- Security, code-quality, and infra rules live in `architecture.md`. They are
  **not** duplicated here; the Cross-Cutting section below only points to them.

---

## Milestone M0 · Foundation

Goal: a multi-tenant skeleton with proven row isolation. No product features yet.

- [ ] Next.js 14 (App Router, TS strict) scaffolded in `/apps/web`
- [ ] FastAPI + Celery scaffolded in `/apps/api`, deploys to Railway
- [ ] Supabase project created; `users`, `organizations`, `organization_members`
      tables migrated (FR-1, FR-2 backing tables)
- [ ] Clerk wired for Google/GitHub OAuth + org primitive
- [ ] RLS policy applied to every org-scoped table (template in `architecture.md`)
- [ ] `/dashboard` route exists, empty, gated by auth

**Done gate (must all be true to start M1):**
- [ ] Two users sign up to two separate orgs.
- [ ] A two-tenant SQL probe confirms neither org can read the other's rows.
- [ ] Unauthenticated request to `/dashboard` redirects to sign-in.

---

## Milestone M1 · First Integration + First Chart

Goal: connect one real OpenAI key and see accurate spend. This is the first demoable slice.

- [ ] `/settings/integrations` form accepts an OpenAI Admin key (FR-3)
- [ ] Key validated with a live test call before storing
- [ ] Key encrypted AES-256-GCM at rest; never logged, never returned to frontend
- [ ] On connect, enqueue Celery backfill of 30d cost + usage (FR-4)
      via `/v1/organization/costs` + `/v1/organization/usage/completions`
- [ ] Backfill writes to `usage_events`
- [ ] Celery refresh job runs every 4h (FR-5)
- [ ] Nightly aggregation rebuilds `daily_cost_summaries`
- [ ] Dashboard renders from `daily_cost_summaries` (not raw events): total spend
      today / 7d / 30d / MTD with sparklines, 30d daily line chart, top-10 by-model
      bar chart, MoM comparison (% change vs last month) (FR-6, FR-7)
- [ ] Spend-by-provider donut chart (shows once multi-provider connects in M2; stub OK now)
- [ ] Dashboard color coding: red over-budget, yellow warning, green healthy
- [ ] Dashboard is mobile-friendly (team members check on phones)
- [ ] Charts built with Tremor (blocks) + Recharts (custom)

**Done gate:**
- [ ] Connect a real OpenAI key; dashboard numbers match the OpenAI dashboard.
- [ ] Time from key-connect to first chart is under 5 minutes for a ~$20K/mo org.
- [ ] Dashboard p95 latency ≤ 800ms.
- [ ] One design partner is shown the dashboard and asks for access.

**Out of scope for M1:** Anthropic, Gemini, tagging, anomalies, Slack, payment.

---

## Milestone M2 · Multi-Provider + Attribution Wedge

Goal: prove the per-feature attribution wedge with a multi-provider design partner.

- [ ] Anthropic ingestion (FR-8) via `/v1/organizations/usage_report/messages`
      + `/cost_report`, through the same adapter protocol
- [ ] Gemini ingestion (FR-9) - verify billing granularity first; if weak, defer to V1
- [ ] Unified multi-provider view, USD-normalized (FR-10)
- [ ] Tag CRUD: feature / team / customer / env, assignable colors (FR-11)
- [ ] Tag-rule engine: regex/substring match on API key label, runs at ingestion,
      denormalizes tags into `usage_events`; multiple priority-ordered rules per tag (FR-12)
- [ ] Tag-rule dry-run preview before activation
- [ ] Manual tag override on usage events (admin-only)
- [ ] Cost Explorer pivot table (TanStack): pivot by provider/model/tag/date,
      sortable, filterable, subtotals, % of total (FR-13)
- [ ] Cost Explorer metrics: total cost, request count, input tokens, output tokens
- [ ] Cost Explorer drill-down: click a row → filtered view of that dimension
- [ ] CSV export hook present (full export polished in M4 / FR-23)

**Done gate:**
- [ ] A design partner with 2+ providers connected opens Cost Explorer and can
      see which feature/model/team is most expensive.
- [ ] At least one partner reacts with a "I had no idea X cost that much" moment.
- [ ] Tag rules correctly classify their real keys across ≥2 dimensions.

**Scope guard:** `customer` exists as a tag dimension here, but full per-customer
*attribution / chargeback* is a V1 feature - do not build the chargeback dashboard now.

---

## Milestone M3 · Intelligence Layer

Goal: automated detection + alerting so the product works while the customer sleeps.

- [ ] Anomaly detection (FR-14): rolling mean + 2σ over 7d window, $10 floor,
      nightly job. Algorithm is fixed in `architecture.md` - implement as specified.
- [ ] Anomaly log fields: timestamp, scope, baseline cost, actual cost, spike %,
      severity low/medium/high by z-score; status open → acknowledged → resolved (FR-15)
- [ ] Anomaly explainer: 1–2 sentence plain-English cause (Claude Haiku, 24h cached)
- [ ] Budget CRUD at global / tag / model scope, monthly threshold (FR-16)
- [ ] Budget status display: % of budget used, days remaining, projected EOM spend
- [ ] Email alerts via Resend at 80% and 100% of budget (FR-17)
- [ ] Slack OAuth + bot token encrypted; daily digest at 09:00 org-local;
      real-time alerts on high-severity anomaly + budget threshold (FR-18)
- [ ] Slack daily digest contents: yesterday spend + MoM %, 7d average,
      top 3 cost drivers, open anomalies, budget status
- [ ] Slack manage: disconnect, mute alerts, change channel
- [ ] Rule-based recommendations engine (FR-19): model swap, caching, batching,
      input compression - each with a $ savings estimate, confidence (0–100%), evidence
- [ ] `/recommendations` screen; mark applied / dismissed (FR-20)

**Done gate:**
- [ ] A test org with a synthetic spend spike fires an anomaly.
- [ ] The corresponding Slack alert lands in under 10 minutes.
- [ ] The recommendations list shows 3+ items with savings estimates.
- [ ] A budget set to a low threshold produces an 80% and a 100% email.

---

## Milestone M4 · Monetize + Polish

Goal: a stranger can self-serve from landing page to paid without you touching anything.

- [ ] Stripe Checkout (Stripe-hosted, no custom form), 3 plans (Starter $299 /
      Growth $599 / Enterprise custom), 14-day trial, access gated by active sub (FR-21)
- [ ] Stripe webhook handler verifies signature → upserts `billing` row
- [ ] Stripe Customer Portal link for subscription management (no custom portal)
- [ ] Per-tier feature gating (Starter / Growth / Enterprise unlock different features)
- [ ] CFO PDF (FR-22): cover (org/period/total), exec summary (Sonnet narrative),
      spend overview (MTD vs last month + 12-month trend), top drivers (feature/model/team
      charts), anomalies + status, recommendations + savings, linear forecast.
      Generated on the 1st, stored in R2 (1-year retention), emailed via signed URL.
- [ ] Month-end linear-regression forecast on dashboard (FR-24): projected EOM +
      confidence interval; <14 days data → "not enough data"
- [ ] Forecast display: "Projected $X/month" with on-track green / over-pace red,
      plus a "assumes linear trend" accuracy caveat
- [ ] CSV export finalized from Cost Explorer: clear non-technical headers,
      dated filename (FR-23)
- [ ] Onboarding wizard: welcome → connect → tag → budget → Slack, with progress bar,
      every step skippable, completion message (FR-25)
- [ ] Landing page at `/` with pricing table + signup button
- [ ] Global error handling: every error path has a user-friendly message

**Done gate (this is also the MVP-complete gate):**
- [ ] A non-friend stranger lands on `/`, signs up, connects OpenAI, sets a budget,
      receives a Slack alert, and pays $299 - with no manual intervention.
- [ ] That customer has data tagged across ≥2 dimensions.
- [ ] A CFO PDF has been generated for them.

---

## Pre-Build Gate (before opening Cursor at all)

From `project_spec.md` - repeated here as a hard checklist because it blocks M0:

- [ ] 10 founder calls done
- [ ] 5+ described the same pain unprompted
- [ ] 2+ committed as design partners with real API keys

If these are not all checked, do more customer calls. Do not start M0.

---

## Pre-Deploy Smoke (run before every deploy)

Mirror of `architecture.md` - kept here as the operational checklist:

- [ ] RLS two-tenant isolation probe passes
- [ ] Signup → org → connect → chart works on staging
- [ ] Stripe test checkout completes; webhook updates `billing`
- [ ] CFO PDF generates + emails correctly (once M4 shipped)
- [ ] No new Sentry errors in the last hour
- [ ] `pricing.yaml` version committed

---

## Cross-Cutting Requirements (do not duplicate - see source of truth)

These are **defined in `architecture.md`**. Verify against that file; do not
re-specify them here, so there is exactly one place to update each:

- Code quality (TS strict / ruff / mypy / black / CI) → `architecture.md` › Engineering Reqs
- Security (key encryption, RLS, audit_events, rate limiting, CORS, Vault) → `architecture.md` › Security
- Test targets (pricing math, anomaly logic, tag-rule engine; one e2e per milestone) → `architecture.md` › Engineering Reqs
- PostHog activation events → `architecture.md` › Engineering Reqs
- DB schema, API surface, adapter protocol, anomaly algorithm → `architecture.md`

## Out of MVP (do not build now - see source of truth)

Full lists with repay-triggers live in `project_spec.md` › Post-MVP and
`architecture.md` › Known V1 debt. Headline "never in MVP": proxy mode,
per-request SDK, multi-cloud cost, custom dashboard builder, white-label,
mobile app, self-hosted, ClickHouse.
