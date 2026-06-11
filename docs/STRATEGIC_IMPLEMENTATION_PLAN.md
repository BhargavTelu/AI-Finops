# Strategic Implementation Plan

**Source of truth for feature implementation order.** Derived from `docs/strategic_review_2026-06-11.docx`, then corrected against the actual codebase (2026-06-11). Supersedes the M4 task ordering in `docs/project_spec.md` where they conflict; does not change any hard rule in `CLAUDE.md`.

**North star:** first real paying customer, then three. Every phase below either shortens the path to that or removes a reason a prospect says no.

---

## Corrections applied to the strategic review

The review was written before a code-level audit. Four findings changed it:

| Review claim | Reality in code | Plan impact |
|---|---|---|
| "Cut the AI anomaly explainer" | Already implemented (`api/services/anomaly_explainer.py` + worker, Redis-capped) | Keep as-is. Zero further investment. Not cut — sunk and harmless. |
| "M4: build CSV export" | Already shipped client-side (`cost-explorer/export-button.tsx`) | FR-23 done. Delete the dead 501 `/usage/export.csv` stub. |
| "Hide Gemini connect" | Confirmed: Gemini selectable in `components/integrations-page.tsx` while `fetch_costs()` ingests nothing | Phase 0 quick win. |
| "Pricing drift risk unmanaged" | `pricing.yaml` versioned `2026-06`, updated today; Usage Events admin page allows manual tag fixes | Risk is managed-by-process. Reconciliation (Phase 4) still valuable but less urgent. |

All other review conclusions stand: CFO PDF first, Stripe second, SDK + per-customer margin promoted to top of V1, trust features added, AI narratives / full RBAC / benchmark library / per-user Slack DMs cut or deferred.

---

## Priority stack (what gets built, in order)

| # | Feature | Why this position | Est. effort |
|---|---|---|---|
| 0 | Trust quick wins (Gemini hide, security page, key-scoping guide, dead-stub cleanup) | Removes funnel blockers; near-zero cost | 1–1.5 d |
| 1 | CFO PDF report | The wedge + doubles as sales collateral for design partners | 3–4 d |
| 2 | Stripe billing + trial + gating | Revenue path; nothing converts without it | 2.5–3 d |
| 3 | Forecast + activation checklist + landing page + weekly email digest | Activation + top-of-funnel + retention touchpoint | 3 d |
| 4 | Trust & traction: reconciliation, Slack ack buttons, CFO viewer seat, worker locks | Converts trials; deliberately code-light so founder time goes to sales | 4–5 d code |
| 5 | V1 (gated on 3+ paying customers): telemetry SDK → per-customer margin → Azure OpenAI | The real moat; built only against paying demand | — |

Phases 0–3 ≈ 10–11 working days to a fully sellable product.

---

## Phase 0 — Trust Quick Wins (1–1.5 days) ✅ COMPLETE (2026-06-11)

Goal: nothing in the product lies, and the scariest onboarding moment (handing over an Admin key) has an answer.

- [x] **Hide Gemini connect.** In `apps/web/src/components/integrations-page.tsx`: remove `gemini` from the provider `<SelectItem>` list; render a disabled "Gemini — coming soon" row instead. Keep the backend adapter (validation logic is fine, harmless). Do NOT delete existing Gemini integrations rows for orgs that already connected.
- [x] **Read-only key guidance in the connect flow.** Add a collapsible "How to create a least-privilege key" panel per provider in the connect form: OpenAI (Admin key with read-only scopes), Anthropic (Admin key usage-report scope). Verify exact scope names against current provider docs before writing copy — do not guess.
- [x] **Security page.** Static `/security` route (public, linked from settings + future landing page): AES-256-GCM at rest, keys never returned to client, RLS isolation, no customer traffic through our servers, data deletion on request. This is sales collateral, not legal text.
- [x] **Dead code cleanup.** Delete the 501 `/usage/export.csv` stub from `api/routers/usage.py` (client-side export covers FR-23). Leave `/usage/forecast` stub — implemented in Phase 3.
- [x] Update `docs/project_status.md` + changelog.

**Done:** A skeptical CTO can read why the key ask is safe; no UI path leads to a provider that silently ingests $0.

---

## Phase 1 — CFO PDF Report (3–4 days) · FR-22

Goal: the differentiator exists and can be generated on demand for any org — including a design partner mid-sales-call.

**Decision D1 — PDF engine: WeasyPrint** (HTML/CSS → PDF, pure Python, no headless browser). Justification under the dependency rule: the alternative (Puppeteer/Chromium on the worker) is ~300MB and a separate runtime; @react-pdf/renderer would put report generation in the Next.js layer, but the trigger is a Celery beat task — keeping it in Python avoids a cross-service call. If WeasyPrint's native deps (Pango) fight Railway, fall back to `fpdf2` (zero native deps, more layout work).

- [ ] **Report data service** — `api/services/report_builder.py`, pure functions, no DB: takes pre-fetched rows, returns a `MonthlyReportData` dataclass: month totals + MoM delta, spend by provider, top-10 models, spend by feature/team/customer tag, anomaly count + top 3 by spike, applied-recommendation savings, next-month figure (reuse Phase 3 forecast once it exists; flat extrapolation until then). Unit-test the math (this is CFO-facing arithmetic — 80% target per CLAUDE.md).
- [ ] **HTML template** — Jinja2 (already a FastAPI transitive dep), branded, one page summary + breakdown pages. Render with WeasyPrint.
- [ ] **R2 storage service** — `api/services/storage.py`: S3-compatible upload + presigned GET (boto3 or httpx+sigv4; prefer httpx if boto3 weight is objectionable). Object key: `reports/{org_id}/{period}.pdf`. Insert `reports` row (table already in schema).
- [ ] **Worker** — `api/workers/reports.py`: `generate_monthly_reports()` beat task (1st of month, 06:00 UTC) fanning out `generate_org_report(org_id, period)`; on success email the org admin via Resend with a download link (reuse admin-email lookup from `notifications.py`). Idempotency: skip if `reports` row exists for (org, period) unless `force=True`.
- [ ] **Routes** — implement the three 501 stubs in `api/routers/reports.py`: `GET /reports` (list), `GET /reports/:id/download` (presigned URL, ownership-checked), `POST /reports/generate` (202; current-month-to-date on demand — this is the sales-demo path, rate-limit 3/day/org in Redis).
- [ ] **Web** — `/reports` page: list with period + generated date + download button; "Generate current month" button; empty state ("Your first report arrives on the 1st — or generate one now"); loading skeleton; error state.
- [ ] **Env/config:** `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` in `config.py` + `.env.example`.
- [ ] Tests: report_builder math, R2 service (mocked), worker idempotency, route ownership/404s.

**Done:** `POST /reports/generate` on a real org produces a PDF a CFO could be handed unedited; the 1st-of-month email fires for a test org.

---

## Phase 2 — Stripe Billing + Gating (2.5–3 days) · FR-21

**Decision D2 — 14-day trial: yes.** Self-serve product with no sales motion needs a trial; the activation flow (Phase 3) exists to make those 14 days count. `organizations.trial_ends_at` already exists.
**Decision D3 — keep $299 entry.** No $99 tier until ≥10 paying customers give pricing signal. Revisit then.

- [ ] **Stripe products:** 3 plans (Starter $299 / Growth $599 / Enterprise $1,500) as env-configured price IDs. No custom billing UI (hard architecture decision — Checkout + Customer Portal only).
- [ ] **Routes** — implement `api/routers/billing.py` stubs: `POST /billing/checkout` (Checkout session, `client_reference_id=org_id`), `GET /billing/portal` (Customer Portal URL from `billing.stripe_customer_id`), `GET /billing` (plan, status, `current_period_end`, trial state).
- [ ] **Webhook** — add Stripe handler to `api/routers/webhooks.py` (or new `webhooks_stripe.py`): verify signature; handle `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted` → upsert `billing` row + mirror plan onto `organizations.plan`. **Idempotency by Stripe event id** (dedupe table or `audit_events` check) — webhook retries must not double-process.
- [ ] **Access gating** — `require_active_org` dependency in `deps.py`: allow if active subscription OR `trial_ends_at` in future; 402 otherwise. Apply to data routes (usage, explorer, reports, recs); never gate `/billing`, `/slack/status`, settings, or webhooks. Web: trial-countdown banner from day 7; expired state renders a paywall page with Checkout CTAs, not a dead end.
- [ ] **Trial bootstrap:** set `trial_ends_at = now() + 14d` on org creation (Clerk webhook handler).
- [ ] PostHog `checkout_completed`; audit event on plan changes.
- [ ] Tests: webhook signature + idempotency + lifecycle transitions, gating dep (trial active / expired / subscribed / canceled), checkout route.

**Done:** Stripe test-mode checkout completes → `billing` row updates → expired-trial org is paywalled, paid org is not. Pre-deploy smoke item #3 passes.

---

## Phase 3 — Forecast, Activation, Landing, Weekly Email (3 days) · FR-24, FR-25

- [ ] **Forecast** — `api/services/forecast.py`: pure least-squares linear regression over current-month daily totals from `daily_cost_summaries` (fallback: trailing 30d trend when <5 days elapsed); returns projected month-end ± simple confidence band. Implement the `/usage/forecast` stub. Unit-test the regression math hard (CFO-facing). Dashboard: "Projected month-end" stat card with delta vs. last month, wired into the existing stat-card row.
- [ ] **Activation checklist** (replaces the spec's onboarding wizard — 90% of the value, 20% of the effort): dismissible dashboard card with 4 server-computed checks — provider connected → tag rule created → Slack connected → budget set — each linking to its page. State: existence queries, no new tables; dismissal in `localStorage`.
- [ ] **Landing page** — replace the `/` redirect stub: hero ("Know which feature, team, and customer burns your LLM budget"), product shots, pricing table (3 plans + trial), security section linking `/security`, FAQ, sign-up CTA. Use the existing design system; keep Clerk sign-up as the only CTA. (Use the `frontend-design` skill when building.)
- [ ] **Weekly email digest** — `send_weekly_email_digests` beat (Mondays 09:00 UTC) in `notifications.py`: reuse `_fetch_digest_data()`, render HTML via Resend to org admins **without Slack connected** (Slack-first principle: don't double-notify Slack orgs). Unsubscribe flag on `organizations` (simple boolean, honored in the fan-out).
- [ ] PostHog funnel events verified end-to-end: signup → provider_connected → budget_created → checkout_completed.

**Done:** A stranger can land on `/`, understand the product, sign up, follow the checklist to first chart in <10 min, see a forecast, and pay — untouched. (= the spec's MVP done-condition.)

---

## Phase 4 — Trust & Traction (4–5 days code, founder time on sales)

Deliberately code-light. The done-condition for this phase is **3 paying customers**, not features. Build in this order, stop when sales pipeline demands attention:

- [ ] **Invoice reconciliation (v1, manual-entry)** — the highest-trust feature. New table `invoice_reconciliations (id, org_id, provider, period, our_total_usd, invoice_total_usd, delta_pct, note)`. View on `/reports`: per provider per month, our ingested total (computed from `daily_cost_summaries`), an input for the user's actual invoice amount, computed delta with an honest legend ("OpenAI: pulled from provider Cost API — should match. Anthropic: computed from list pricing — small drift possible."). No provider-invoice API integration in v1 — manual entry is enough to build trust and surfaces our accuracy.
- [ ] **Slack interactive ack/dismiss** — add buttons to anomaly alert blocks; new `POST /slack/interactions` endpoint with Slack signing-secret verification (timing-safe); maps `action_id` → existing `PATCH /anomalies/:id` logic; updates the Slack message in place. Closes the loop on the stickiest surface.
- [ ] **CFO viewer seat** — Clerk org role `viewer` (read-only): `require_admin` dependency on all mutating routes (integrations, budgets, tags, slack, billing); web hides mutating controls for viewers; "Invite your CFO" CTA on `/reports`. Not full RBAC — exactly two roles.
- [ ] **Worker concurrency locks** — pay down Gap-02/05/08/10 before customer count makes races real: Redis `SET NX EX` lock decorator applied to `aggregate_org`, `refresh_integration`, `detect_org`, `check_org`. Tests already document the races; flip them to assert the lock.

---

## Phase 5 — V1 (gate: 3+ paying customers — do not start early)

1. **Telemetry SDK** (the moat; promoted from V1-list bottom to top). Design constraints settled now, build later: async fire-and-forget metadata events (`model, tokens, customer_id, feature, env, ts`) — **not** in the request path, so hard rule #1 holds. Server: `POST /v1/ingest/events` authenticated by per-org ingest key; events land in `usage_events` with `source='sdk'`; reconciled against provider-pulled totals (provider numbers stay authoritative for $; SDK provides attribution split). Client: Python + TS packages, batched, fail-open. This unlocks *real* per-customer attribution — until it ships, sell the wedge as per-feature/per-team.
2. **Per-customer margin module** — depends on SDK for customer-level cost. CSV upload of customer→MRR (Stripe import later), join against customer-tagged cost, gross-margin-per-customer view. The board-meeting feature; justifies the $1,500 tier.
3. **Azure OpenAI adapter** — build when (and only when) a paying customer asks. Bedrock further behind.
4. **SOC 2 Type 1 prep** — trigger: first enterprise security questionnaire, not $50K MRR.

---

## Explicitly cut / not doing

| Item | Status |
|---|---|
| AI recommendation narratives (Haiku) | Cut — rule-based $ math is the value |
| Anomaly explainer expansion | Frozen — keep what exists, invest nothing |
| Onboarding wizard (multi-step) | Replaced by activation checklist |
| Full RBAC | Replaced by two-role viewer seat |
| Per-user Slack DMs | Cut |
| Benchmark library | Deferred until ~30 orgs (needs data mass) |
| Proxy mode | Deferred per hard rule #1; investigate Admin-API "kill switch" (provider-side key disable at hard cap) as a V2 spike *before* ever revisiting proxy |
| Gemini cost ingestion (Cloud Billing OAuth) | Deferred — connect UI hidden in Phase 0 until this ships |
| $99 pricing tier | Deferred until 10 paying customers |

## Decision log

- **D1:** PDF engine = WeasyPrint (fallback fpdf2). Python-side because the trigger is Celery.
- **D2:** 14-day trial = yes (resolves spec open question #3).
- **D3:** Entry price stays $299 (resolves spec open question #4 for now).
- **D4:** Reconciliation v1 = manual invoice entry, no invoice-API integration.
- **D5:** Wedge messaging until SDK ships = per-feature/per-team attribution; per-customer is roadmap, not promise.

## Working agreement

- One phase group = one branch (`feat/<short>`) = one PR, per repo etiquette. Conventional Commits, squash-merge.
- `pnpm test` + `pytest` green before every push; unit-test all money math (report builder, forecast, reconciliation deltas).
- Update `docs/project_status.md`, `docs/changelog.md`, and CLAUDE.md milestone line at each phase completion (`/update-docs-and-commit`).
- Engineering bar: hold it on money-and-keys paths (billing, encryption, ingestion); elsewhere, smallest thing that proves the done-condition. No new gap-analysis-scale test passes until customers exist.

## Phase done-conditions (the only ones that count)

| Phase | Done when |
|---|---|
| 0 | Security page live; Gemini connect hidden; key-scoping guide in connect flow |
| 1 | On-demand CFO PDF generated for a real org, unedited-presentable |
| 2 | Test-mode checkout → billing row → gating verified both directions |
| 3 | Stranger: `/` → signup → chart in <10 min → forecast visible → can pay |
| 4 | **3 paying customers** (features above are servants of this) |
| 5 | Gated on Phase 4's customer count — not started before |
