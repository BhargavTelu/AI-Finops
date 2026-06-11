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

## Phase 1 — CFO PDF Report (3–4 days) · FR-22 ✅ COMPLETE (2026-06-11)

Goal: the differentiator exists and can be generated on demand for any org — including a design partner mid-sales-call.

**Decision D1 (amended 2026-06-11) — PDF engine: fpdf2.** WeasyPrint was tried first per the original decision and failed exactly as the fallback clause anticipated: it requires Pango/GTK native libraries that are unavailable on Windows dev (`OSError: cannot load library 'libgobject-2.0-0'`) and add weight on Railway. fpdf2 is pure Python (~1MB, transitive deps: pillow, fonttools, defusedxml), renders the branded layout directly in Python (no Jinja2 HTML step), and was smoke-verified to produce a CFO-presentable PDF.

- [x] **Report data service** — `api/services/report_builder.py`, pure functions, no DB: `MonthlyReportData` dataclass with month totals + MoM delta, spend by provider, top-10 models, spend by feature/team/customer tag, anomaly count + top 3 by spike, applied-recommendation savings, flat-extrapolation projection (Phase 3 forecast replaces it). Unit-tested.
- [x] **PDF rendering** — `api/services/report_pdf.py` (replaces the Jinja2+WeasyPrint task per amended D1): branded navy header band, summary stat row with color-coded MoM, per-dimension tables with alternating rows, severity-colored anomaly lines, realized-savings section, honest data-source footnote.
- [x] **R2 storage service** — `api/services/storage.py`: hand-rolled SigV4 over httpx (boto3 is ~80MB for two operations); `upload_pdf` + `presign_download`; injectable clock for deterministic signature tests. Object key: `reports/{org_id}/{period_start}.pdf` (stable per month — fuller regenerations overwrite partials). Fails soft when R2 is unconfigured (row recorded with `has_file=false`).
- [x] **Worker** — `api/workers/reports.py`: `generate_monthly_reports()` beat (1st, 06:00 UTC) fans out `generate_org_report`; Resend email with link to `/reports` (best-effort). Idempotency: one row per (org, type, period_start); regenerates only when the new run covers more days or `force=True`, so an on-demand partial never blocks the month-end report.
- [x] **Routes** — `GET /reports`, `GET /reports/:id/download` (presigned URL, ownership-checked, object key never exposed), `POST /reports/generate` (202, month-to-date, force=True; Redis rate limit 3/day/org, fail-open).
- [x] **Web** — `/reports` page: report cards with period + month-to-date badge + download button; "Generate current month" button; empty state; loading skeleton; error state; Reports nav link.
- [x] **Env/config:** R2 vars were already present; added `APP_URL` (email CTAs) to `config.py` + `.env.example`; `fpdf2>=2.8.0` added to `pyproject.toml` with weight justification.
- [x] Tests: 48 new (report_builder math, PDF render, SigV4 shape/determinism, worker fan-out + idempotency + email, route ownership/404/429). TC-STUB-06 retired.

**Done:** `POST /reports/generate` on a real org produces a PDF a CFO could be handed unedited; the 1st-of-month email fires for a test org.

---

## Phase 2 — Stripe Billing + Gating (2.5–3 days) · FR-21 ✅ COMPLETE (2026-06-11)

**Decision D2 — 14-day trial: yes.** Self-serve product with no sales motion needs a trial; the activation flow (Phase 3) exists to make those 14 days count. `organizations.trial_ends_at` already exists.
**Decision D3 — keep $299 entry.** No $99 tier until ≥10 paying customers give pricing signal. Revisit then.

- [x] **Stripe products:** 3 env-configured price IDs (`STRIPE_PRICE_STARTER/GROWTH/ENTERPRISE`); unconfigured → checkout 503. No custom billing UI — Checkout + Customer Portal only.
- [x] **Routes** — `POST /billing/checkout` (subscription-mode session, `client_reference_id=org_id`, plan in session+subscription metadata, reuses existing `stripe_customer_id` on re-subscribe), `GET /billing/portal` (404 until a customer exists), `GET /billing` (plan/status/period-end/trial state plus the server's own `access_blocked` verdict so the web shell never re-implements the rule).
- [x] **Webhook** — implemented in `webhooks.py`: `stripe.Webhook.construct_event` signature check (400 on bad sig); **idempotency via `stripe_events` claim table** (migration `20260611120000`; INSERT-as-claim, duplicate → 200 ack without re-processing); `checkout.session.completed` / `customer.subscription.updated` (org resolved from metadata or billing-table lookup, plan from price-id map with metadata fallback) / `customer.subscription.deleted` → billing upsert + `organizations.plan` mirror + best-effort `audit_events` row.
- [x] **Access gating** — `evaluate_access()` in `services/billing_access.py` is the single source of truth (active/trialing subscription OR running built-in trial; `past_due` deliberately blocked — the paywall is the nudge that fixes the card; NULL/malformed `trial_ends_at` blocks rather than granting infinite access). `_require_active_org` (402) applied router-level in `main.py` to usage/anomalies/recommendations/reports; billing/integrations/tags/slack/budgets/onboarding stay reachable. Web: trial banner from day 7 in the dashboard shell; expired → `Paywall` with `PlanPicker` CTAs (nav intact — a door, not a dead end); both read `/billing` with `noStore` so a fresh payment is never hidden behind the 2-min cache.
- [x] **Trial bootstrap** — verified pre-existing: `_handle_org_created` has set `trial_ends_at = now+14d` since M0.
- [x] **PostHog** — server-side `services/analytics.py` (httpx → /capture, fail-soft, ids only): `signup` + `org_created` from the Clerk webhook, `checkout_completed` from the Stripe webhook; client-side capture on the checkout-success redirect as well. Audit events on every plan change.
- [x] **Tests: 31 new** — `test_billing_gating.py` (access rule × 11 incl. canceled-inside-trial, Z-suffix timestamps; 402 dependency × 3), `test_billing_routes.py` (status/checkout/portal × 10), `test_stripe_webhook.py` (signature, idempotency, lifecycle × 10). Route tests bypass the gate via conftest override; TC-STUB-04/05/TC-WH-20 retired.

**Done (code-side):** expired-trial org is paywalled, paid org is not, webhook lifecycle covered by tests. **Remaining (founder, ~30 min):** create the 3 Products/Prices in Stripe test mode, set the price-ID env vars + webhook endpoint secret, apply the `stripe_events` migration, run one live test-mode checkout (pre-deploy smoke #3).

---

## Phase 3 — Forecast, Activation, Landing, Weekly Email (3 days) · FR-24, FR-25 ✅ COMPLETE (2026-06-11)

**Executed before Phase 2 at founder's direction.** The done-condition's "…and pay" clause stays open until Phase 2 (Stripe) ships; everything else delivered.

- [x] **Forecast** — `api/services/forecast.py`: pure least-squares regression over current-month daily totals (gap-filled $0 days); per-day predictions clamped ≥ 0; confidence band from residual std × √(remaining days); low bound never below actual MTD spend; trailing-30d-average fallback under 5 elapsed days. `/usage/forecast` implemented (404 distinguishes "no history" from a genuine $0 month); `ForecastResult` extended with `method`, `last_month_cost_usd`, `delta_vs_last_month_pct`. Dashboard "Projected month-end" card in the stat row (5-col grid when present) with delta badge + range line. 10 math tests + route tests; TC-STUB-02 retired.
- [x] **Activation checklist** — `GET /onboarding/status` (4 existence queries, org-scoped, no new tables) + dismissible `ActivationChecklist` card (localStorage, hydration-safe, auto-hides at 4/4) rendered on the dashboard **including the empty state**, where a fresh org needs it most.
- [x] **Landing page** — `/` redirect stub replaced: "audited ledger" concept within the shadcn system — cost-statement hero vignette with dot leaders and a flagged anomaly row, numbered section rules, 3 features, 3 steps, spend-tiered pricing ($299/$599/$1,500, all-features-on-every-plan, 14-day trial no card), navy security band → `/security`, native-`details` FAQ, footer. Clerk sign-up is the only CTA; signed-in visitors get "Open dashboard".
- [x] **Weekly email digest** — `send_weekly_email_digests` beat (Mon 09:00 UTC): reuses `_fetch_digest_data()`; targets orgs with active integrations, minus Slack-connected (no double-notify), minus opted-out; migration `20260611000000_add_email_digest_opt_out.sql` adds `organizations.email_digest_opt_out` (manual opt-out via email reply at current scale). 9 tests (fan-out exclusions, send paths, HTML content).
- [x] **PostHog funnel** — events were typed stubs with zero call sites; now wired: `provider_connected` (connect success), `tag_created`, `budget_created` (signature widened to 7 scope types), `pdf_downloaded`, plus `identify(user.id)` + org `group()` in the provider (ids only, no PII). `signup`/`org_created` deferred to server-side capture via the Clerk webhook (more reliable than client heuristics — wire in Phase 2 alongside `checkout_completed`).

**Done:** A stranger can land on `/`, understand the product, sign up, follow the checklist to first chart in <10 min, and see a forecast. ~~and pay~~ ← unblocked by Phase 2.

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

- **D1 (amended 2026-06-11):** PDF engine = fpdf2. WeasyPrint's Pango native deps fail on Windows dev and weigh on Railway; the documented fallback was exercised. Python-side because the trigger is Celery.
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
