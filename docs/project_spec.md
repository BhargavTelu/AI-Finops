# Project Spec — AI FinOps Platform

## What

SaaS that gives AI startups per-feature/team/customer cost attribution, anomaly alerts, and savings recommendations for LLM API spend. Customers connect Admin API keys → we pull billing data → slice it by tags → alert + recommend.

**ICP:** CTO at AI-native SaaS, $1M–$50M ARR, spends $5K–$80K/mo on LLM APIs.
**Pricing:** Starter $299 · Growth $599 · Enterprise $1,500+
**Wedge:** Finance-first (CFO PDF, per-customer attribution) at mid-market pricing. Competitors are either dev-first (Helicone, Langfuse) or enterprise-priced (Vantage, Finout).

## Principles (decision filters)

1. No customer traffic through our servers in MVP — pull from Admin APIs only.
2. Time-to-first-chart < 10 min from signup.
3. CFO is a hidden buyer — every screen defensible to finance.
4. Statistics before ML (anomalies = rolling mean + 2σ).
5. No-code where possible: Clerk, Stripe Checkout, Resend, Supabase.
6. Slack is mobile. No native app.

## Functional Requirements

| ID | Requirement | M |
|---|---|---|
| FR-1 | Google/GitHub OAuth signup via Clerk | M0 |
| FR-2 | Org creation + teammate invites | M0 |
| FR-3 | Connect OpenAI Admin key (AES-256 at rest) | M1 |
| FR-4 | Pull 30d historical cost+usage on key connect (≤5 min) | M1 |
| FR-5 | Refresh every 4h via background job | M1 |
| FR-6 | Dashboard: total spend (today/7d/30d) + daily line chart | M1 |
| FR-7 | Spend grouped by model | M1 |
| FR-8 | Anthropic Admin key support | M2 |
| FR-9 | Gemini billing key support | M2 |
| FR-10 | Unified multi-provider view (USD normalized) | M2 |
| FR-11 | Tag system (feature/team/customer/env) | M2 |
| FR-12 | Tag rules (regex/substring match on API key label → auto-tag) | M2 |
| FR-13 | Cost Explorer: pivot by {provider, model, tag, date} | M2 |
| FR-14 | Anomaly detection (>2σ vs 7d rolling, >$10 floor) | M3 |
| FR-15 | Anomaly log with severity | M3 |
| FR-16 | Budgets at {global/tag/model} scope, monthly threshold | M3 |
| FR-17 | Email alerts at 80% and 100% of budget | M3 |
| FR-18 | Slack OAuth + daily digest + real-time alerts | M3 |
| FR-19 | Recommendations (rule-based: model swap, caching, batch) with $ savings | M3 |
| FR-20 | Mark recs applied/dismissed | M3 |
| FR-21 | Stripe Checkout (3 plans), access gated by active sub | M4 |
| FR-22 | Monthly CFO PDF auto-emailed on 1st | M4 |
| FR-23 | CSV export from Cost Explorer | M4 |
| FR-24 | Month-end forecast (linear regression) on dashboard | M4 |
| FR-25 | Onboarding wizard + empty states + error handling | M4 |

## Non-Functional

- **Security:** Admin keys encrypted AES-256-GCM (pgcrypto). Never logged, never sent to frontend. RLS on every org-scoped table.
- **Perf:** Dashboard p95 ≤ 800ms. API p95 ≤ 300ms. Aggregation < 5 min/org/night at 100K events.
- **AI cost cap:** ≤ $0.05/org/day. Hard rate-limit: 3 AI calls/org/day in Redis.
- **Infra cost ceiling:** < $250/mo total at 50 customers.
- **Compliance:** SOC 2 deferred until $50K MRR or enterprise asks. GDPR export/delete by end of M4.

## Milestones

Each milestone ends with a working, demoable slice. Don't skip ahead.

### M0 · Foundation (4 days) ✅ COMPLETE (2026-05-19)

- Next.js 14 + Supabase + Clerk scaffolded
- `users`, `organizations`, `organization_members` tables with RLS
- Two-tenant SQL probe confirms isolation
- Empty `/dashboard` route gated by auth

**Done:** Two users sign up to separate orgs, can't read each other's rows.

### M1 · First Integration + First Chart (7 days) ✅ COMPLETE (2026-05-19)

- `/settings/integrations` form: connect OpenAI Admin key (validate → encrypt → store)
- Celery worker on Railway: backfill 30d on connect, refresh every 4h
- Ingestion: `/v1/organization/costs` + `/v1/organization/usage/completions` → `usage_events`
- Nightly aggregation → `daily_cost_summaries`
- Dashboard (Tremor): MTD/yesterday totals, 30d line chart, by-model bar chart

**Done:** Connect your own OpenAI key. Numbers match OpenAI dashboard. Show one design partner → they want access.

**Out of scope:** Anthropic, Gemini, tagging, anomalies, Slack, payment.

### M2 · Multi-Provider + Attribution Wedge (11 days) ✅ COMPLETE (2026-05-20)

- Anthropic adapter — `/v1/organizations/usage_report/messages` with cursor pagination; cost computed from `pricing.yaml`; `cache_read_input_tokens` mapped to `cached_tokens`
- Gemini adapter — key validation only (`/v1beta/models?key=`); `fetch_costs()` is a no-op (AI Studio has no billing endpoint; Cloud Billing API requires OAuth2 — deferred to V1)
- Tag CRUD + tag-rules engine (`services/tag_engine.py`) — pure functions; exact/substring/regex match on `api_key_label`; rules applied at ingestion time; denormalized into `usage_events` columns
- `POST /tag-rules/preview` — dry-run a rule against last 7 days of events
- `GET /usage/explore` — pivot data for Cost Explorer grouped by provider/model/tag, with `pct_of_total`
- Cost Explorer UI (`/cost-explorer`) — TanStack Table; group_by + range + provider filter dropdowns
- `/settings/tags` UI — tag CRUD + rule CRUD + preview
- Fixed: `integrations.py` `_ADAPTERS` missing Anthropic and Gemini entries
- **117 tests passing, 2 skipped. 0 TypeScript errors.**

**Done:** Design partner with 2+ providers sees Cost Explorer and says "I had no idea X was that expensive."

### M3 · Intelligence Layer (11 days)
- Anomaly detection (statistical, nightly job)
- Budget CRUD + threshold alerts via Resend
- Slack OAuth + daily digest (9am org-local) + real-time alerts
- Rule-based recommendations engine + `/recommendations` screen

**Done:** Test org with synthetic spike fires anomaly, Slack alert lands in <10 min, recs list shows 3+ items with savings estimates.

### M4 · Monetize + Polish (9 days)
- Stripe Checkout (3 plans) + webhook handler + access gating + 14-day trial
- CFO PDF (Puppeteer or @react-pdf/renderer) → R2 → emailed on 1st
- Linear forecast on dashboard
- CSV export
- Onboarding wizard (connect → tag → Slack → budget)
- Landing page at `/` with pricing + signup

**Done:** Stranger lands on `/`, signs up, connects OpenAI, sets budget, gets Slack alert, pays $299 — without you touching anything.

## Post-MVP (don't build now)

**V1 (after 5 paying customers):** AI-powered recommendations (Claude Haiku), SDK for per-request attribution, Anthropic Enterprise Analytics API (per-user), Azure OpenAI + Bedrock, RBAC.

**V2 (after $5K MRR):** Proxy mode + hard budget caps, benchmark library, SAML SSO, SOC 2.

**Never:** Custom dashboard builder, white-label, mobile app, multi-cloud cost (we're not Vantage), self-hosted.

## Gates

**Pre-build (don't open Cursor without this):**
- [ ] 10 founder calls done
- [ ] 5+ described the same pain unprompted
- [ ] 2+ committed as design partners with real keys

**MVP done:**
- [ ] 1 real (non-friend) customer paid $299
- [ ] Connected ≥1 provider, set ≥1 budget, got ≥1 Slack alert
- [ ] Their data tagged across ≥2 dimensions
- [ ] CFO PDF generated for them

## Top Risks

| Risk | Mitigation |
|---|---|
| Scope creep into proxy mode | Hard rule: principle #1. Re-read weekly. |
| AI Vyuh FinOps / Helicone close gap | Differentiate on CFO PDF + per-customer + finance-first language |
| Provider Admin API changes | Adapter pattern (one file per provider), 48h SLA on fixes |
| Stale pricing tables (20–40% drift) | Use provider Cost API where available; monthly review of `pricing.yaml` |
| Over-engineer M0 | Time-box: M0 = 4 days. Cut scope, not time. |

## Open Questions

**Resolved:**
1. ~~Anthropic Enterprise Analytics API — Enterprise-tier-gated?~~ → Standard Admin API, not Enterprise-gated. Shipped in M2.
2. ~~Gemini billing granularity — verify in week 1~~ → AI Studio API has no usage-reporting endpoint; Cloud Billing API requires OAuth2/service account. Key validation ships M2, cost collection deferred to V1.

**Active (resolve before M4):**
3. Stripe trial: 14 days vs none? Decide after first 5 design partner pricing conversations. (M4)
4. Pricing test: $299 entry or $99 thinner Starter for top-of-funnel? (M4)
5. ~~Budget reset cycle: calendar month vs rolling 30 days?~~ → **resolved**: calendar month; implemented as `date_trunc('month')` comparison (M3-B)
6. ~~Slack app registration: create in dev workspace before starting M3 Group C~~ → **resolved**: Slack OAuth flow complete; set `SLACK_CLIENT_ID` + `SLACK_CLIENT_SECRET` + `SLACK_REDIRECT_URI` in env (M3-C)
