# Launch Setup Guide - Founder Ops (No Code)

The MVP is **code-complete** (Phases 0-3 done 2026-06-11). Everything in this
doc is dashboard clicks, account creation, and env var values - zero code.
Work through it top to bottom and you can take a real payment at the end.

**Estimated total time: 2-4 hours** (most of it is waiting for DNS/domain
verification at Resend; do that step early).

> Already done during M0 dev setup (skip unless deploying to a brand-new
> environment): Clerk app + JWT template, Supabase project + JWT secret,
> base migrations. See [setup.md](setup.md) for the Clerk ↔ Supabase JWT
> bridge details.

---

## At-a-glance checklist

| # | Service | What you create | Env vars it fills | Status |
|---|---------|-----------------|-------------------|--------|
| 0 | (local) | Encryption key | `ENCRYPTION_KEY` | ✅ done in dev (regenerate per env) |
| 1 | Supabase | Project + apply 2 pending migrations | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` | ⚠️ project exists; **2 migrations pending** |
| 2 | Clerk | App + JWT template + webhook | `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`, `CLERK_ISSUER`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | ✅ done for dev; redo webhook URL for prod |
| 3 | Upstash | Redis database | `REDIS_URL` | ⚠️ needed for prod (localhost in dev) |
| 4 | **Stripe** | **3 products + webhook** | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*` (×3), `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | ❌ **launch blocker** |
| 5 | Resend | API key + verified domain | `RESEND_API_KEY`, `FROM_EMAIL` | ⚠️ key exists; verify prod sender domain |
| 6 | **Cloudflare R2** | **Bucket + API token** | `R2_BUCKET_NAME`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | ❌ **launch blocker** (CFO PDF storage) |
| 7 | Slack | Slack app (OAuth) | `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI` | ⚠️ exists for dev; add prod redirect URI |
| 8 | PostHog | Project | `POSTHOG_API_KEY`, `NEXT_PUBLIC_POSTHOG_KEY`, `*_HOST` | optional but recommended (funnel) |
| 9 | Sentry | 2 projects (web + api) | `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN` | optional |
| 10 | Anthropic | Platform API key | `ANTHROPIC_API_KEY` | optional (recs are rule-based in MVP) |
| 11 | Railway + Vercel | Deploy + env vars | `API_INTERNAL_URL`, `APP_URL`, `CORS_ORIGINS` | ❌ before launch |

❌ items are the critical path. Everything the code needs is listed in
`apps/api/.env.example` and `apps/web/.env.local.example` - this guide tells
you where each value comes from.

---

## Step 0 - Generate the encryption key

Customer Admin API keys are encrypted with AES-256-GCM before they touch the
DB. Generate a fresh 32-byte key **per environment** (never reuse dev's key
in prod):

```bash
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Set it as `ENCRYPTION_KEY` in `apps/api/.env` (dev) / Railway (prod).

> ⚠️ If you rotate this key, every stored integration key becomes
> undecryptable - customers must reconnect. Store a copy in a password
> manager.

---

## Step 1 - Supabase (database)

**Dev project already exists.** For prod you can reuse it or create a
separate project (recommended: separate, free tier is fine to start).

1. Go to <https://supabase.com/dashboard> → **New project** (or open existing).
2. Collect the values from **Settings → API**:
   - **Project URL** → `SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_URL`
   - **anon public key** → `SUPABASE_ANON_KEY` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - **service_role key** → `SUPABASE_SERVICE_ROLE_KEY` (API only - never in the web app)
3. **Settings → Database** → connection string → `DATABASE_URL`
   (format: `postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres`).
4. **Apply the 2 pending migrations** (SQL Editor → paste file contents → Run,
   in timestamp order):
   - `infra/migrations/20260611000000_add_email_digest_opt_out.sql`
   - `infra/migrations/20260611120000_add_stripe_events.sql`

   For a brand-new project, run **all** files in `infra/migrations/` in
   timestamp order instead. Verify nothing is missing by comparing tables in
   the Dashboard against the migration files.
5. **Set the JWT secret** so RLS works: paste the Clerk `supabase` JWT
   template signing secret into **Settings → API → JWT Settings → JWT Secret**.
   Full walkthrough: [setup.md](setup.md) Steps 1-2.

---

## Step 2 - Clerk (auth)

**Done for dev.** For a new/prod environment:

1. <https://dashboard.clerk.com> → **Create application**. Enable
   **Organizations** (Settings → Organizations → enable).
2. **API Keys** page:
   - **Publishable key** → `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
   - **Secret key** → `CLERK_SECRET_KEY` (both api and web envs)
   - **Frontend API URL** → `CLERK_ISSUER` (e.g. `https://your-instance.clerk.accounts.dev`)
3. **JWT template** named exactly `supabase`, HS256, with the claims from
   [setup.md](setup.md) Step 1. Copy its signing secret into Supabase (Step 1.5 above).
4. **Webhooks → Add endpoint**:
   - URL: `https://<your-api-domain>/api/webhooks/clerk`
     (dev: use `ngrok http 8000` or the Clerk CLI to tunnel)
   - Subscribe to exactly these events (that's all the handler processes):
     - `user.created`
     - `organization.created`
     - `organizationMembership.created`
   - Copy the **Signing secret** (`whsec_...`) → `CLERK_WEBHOOK_SECRET`.
5. Production instance only: add your real domain under **Domains** and
   switch to the `pk_live_` / `sk_live_` keys.

---

## Step 3 - Upstash Redis (Celery broker + rate limits)

Local dev uses `redis://localhost:6379/0`. For prod:

1. <https://console.upstash.com> → **Create database**.
   - Name: `spendops-prod`. Region: pick the same region as Railway
     (latency matters - Celery polls the broker constantly).
   - Type: **Regional** (cheaper, sufficient). TLS: enabled.
2. Copy the **Redis connect URL** (the `rediss://default:<password>@...` one,
   note the double `s` = TLS) → `REDIS_URL` on Railway.

Used for: Celery broker/results, AI rate limit (3 calls/org/day), report
generation rate limit (3/day/org).

---

## Step 4 - Stripe (billing) ← launch blocker

Do everything in **Test mode** first (toggle top-right of the Stripe
dashboard), run one end-to-end checkout, then repeat in Live mode.

### 4.1 Account + keys

1. <https://dashboard.stripe.com> → create/activate account.
2. **Developers → API keys**:
   - **Secret key** (`sk_test_...`) → `STRIPE_SECRET_KEY`
   - **Publishable key** (`pk_test_...`) → `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`

### 4.2 Create the 3 products

**Product catalog → Add product**, one per plan. Each gets a single
**recurring monthly USD** price:

| Product name | Price | Maps to env var |
|---|---|---|
| SpendOps Starter | $299.00 / month | `STRIPE_PRICE_STARTER` |
| SpendOps Growth | $599.00 / month | `STRIPE_PRICE_GROWTH` |
| SpendOps Enterprise | $1,500.00 / month | `STRIPE_PRICE_ENTERPRISE` |

After saving each product, open it and copy the **Price ID** (`price_...`,
NOT the product `prod_...` ID) into the matching env var.

> The 14-day trial is handled in our code (trial bootstrap on org creation),
> not via Stripe trial settings - don't configure a trial on the Stripe price.
> If any `STRIPE_PRICE_*` is empty, checkout returns 503 by design.

### 4.3 Register the webhook

1. **Developers → Webhooks → Add endpoint**.
   - URL: `https://<your-api-domain>/api/webhooks/stripe`
   - Events - select exactly these three:
     - `checkout.session.completed`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
2. Copy the **Signing secret** (`whsec_...`) → `STRIPE_WEBHOOK_SECRET`.

For local testing use the Stripe CLI instead:

```bash
stripe listen --forward-to localhost:8000/api/webhooks/stripe
# prints a whsec_... - put that in apps/api/.env while testing locally
```

### 4.4 Test-mode verification

1. Sign up a test org → Settings → Billing → pick a plan → checkout with
   card `4242 4242 4242 4242` (any future expiry, any CVC).
2. Confirm: webhook shows 200 in Stripe dashboard, `/settings/billing` shows
   the active plan (no stale paywall), a row landed in `billing` and
   `stripe_events` tables.
3. Cancel via the customer portal → confirm access gates after period end.

When this passes, flip to **Live mode** and repeat 4.1-4.3 with live keys
(`sk_live_`, `pk_live_`, new live-mode products + webhook + secret).

---

## Step 5 - Resend (transactional email)

Budget alerts, weekly digests, and report-ready emails all go through Resend.

1. <https://resend.com> → create account → **API Keys → Create API key**
   (Full access or Sending access) → `RESEND_API_KEY`.
2. **Domains → Add domain** → enter your sending domain (e.g.
   `spendopsai.com`) → add the DKIM/SPF DNS records it shows at your DNS
   provider → wait for **Verified** status (minutes to hours - start early).
3. Set `FROM_EMAIL` to an address on that domain, e.g.
   `alerts@spendopsai.com`.

> Without a verified domain Resend only delivers to your own account email -
> fine for dev, useless for customers.

---

## Step 6 - Cloudflare R2 (CFO PDF storage) ← launch blocker

The SigV4 client is unit-tested but has **never hit a live R2 endpoint** -
sanity-check one real upload/download after configuring.

1. <https://dash.cloudflare.com> → **R2 Object Storage** (requires adding a
   payment method; free tier: 10 GB - PDFs won't dent it).
2. **Create bucket**: name `spendops-ai-reports` (must match
   `R2_BUCKET_NAME`), location automatic, **no public access** (downloads are
   presigned).
3. Your **Account ID** is shown on the R2 overview page (also in the
   dashboard URL) → `R2_ACCOUNT_ID`.
4. **R2 → Manage R2 API Tokens → Create API token**:
   - Permissions: **Object Read & Write**, scoped to the
     `spendops-ai-reports` bucket only.
   - Copy **Access Key ID** → `R2_ACCESS_KEY_ID` and
     **Secret Access Key** → `R2_SECRET_ACCESS_KEY` (shown once).
5. **Sanity check** (with the API + worker running and env set): hit
   `POST /reports/generate` for a test org, then download from `/reports` in
   the web app. Upload + presigned download both working = done.

> R2 unconfigured is a soft fallback (reports fail gracefully), so a typo
> here won't crash the app - but no PDFs either. Verify the live round-trip.

---

## Step 7 - Slack app (alerts + digests)

Dev app exists. For prod (or first-time):

1. <https://api.slack.com/apps> → **Create New App → From scratch** →
   name `SpendOps AI`, pick your dev workspace.
2. **OAuth & Permissions**:
   - **Redirect URLs**: add `https://<your-web-domain>/settings/slack/callback`
     (and `http://localhost:3000/settings/slack/callback` for dev).
     Must match `SLACK_REDIRECT_URI` **exactly**.
   - **Bot Token Scopes**: `incoming-webhook`, `chat:write`.
3. **Basic Information → App Credentials**:
   - **Client ID** → `SLACK_CLIENT_ID` (both api and web envs)
   - **Client Secret** → `SLACK_CLIENT_SECRET` (api only)
4. To let customer workspaces install it, enable **Manage Distribution →
   Public Distribution** (no Slack App Directory review needed for direct
   OAuth installs).

---

## Step 8 - PostHog (product analytics - recommended)

The activation funnel (signup → provider_connected → tag_created →
budget_created → pdf_downloaded → checkout_completed) is already wired.

1. <https://us.posthog.com/signup> (or EU cloud) → create project.
2. **Settings → Project → Project API key** (`phc_...`). It's write-only, so
   the same key goes in both:
   - `NEXT_PUBLIC_POSTHOG_KEY` (web) and `POSTHOG_API_KEY` (api)
   - Hosts: `NEXT_PUBLIC_POSTHOG_HOST` / `POSTHOG_HOST` =
     `https://us.i.posthog.com` (or whatever your instance shows).

Empty key = capture silently disabled. No code change either way.

---

## Step 9 - Sentry (error tracking - optional)

1. <https://sentry.io> → create org → create **two projects**: one
   **Next.js**, one **FastAPI/Python**.
2. Copy each project's DSN:
   - Python project DSN → `SENTRY_DSN` (api)
   - Next.js project DSN → `NEXT_PUBLIC_SENTRY_DSN` (web)

Empty DSN = disabled. Skippable for day one, cheap insurance after.

---

## Step 10 - Anthropic API key (optional in MVP)

`ANTHROPIC_API_KEY` is the **platform's own** key for future AI-generated
narratives (V1). MVP recommendations are rule-based and don't call it -
leave empty for launch, or create one at <https://console.anthropic.com> →
API Keys. The $0.05/org/day cap and 3-calls/org/day Redis limit are already
enforced in code.

(Not to be confused with **customer** OpenAI/Anthropic Admin keys - those are
entered by customers in the app and stored encrypted.)

---

## Step 11 - Deploy (Railway + Vercel)

### Railway (FastAPI + Celery)

Create one Railway project with **three services** from the same repo
(root: `apps/api`):

| Service | Start command |
|---|---|
| api | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| celery-worker | `celery -A api.celery_app worker --loglevel=info` |
| celery-beat | `celery -A api.celery_app beat --loglevel=info` |

Set **all** `apps/api/.env.example` vars on each service (Railway shared
variables make this easy). Differences from dev:

- `ENV=production`
- `REDIS_URL` = Upstash `rediss://` URL (Step 3)
- `APP_URL` = `https://<your-web-domain>` (used in email CTAs)
- `CORS_ORIGINS=["https://<your-web-domain>"]`
- Live Stripe/Clerk keys, prod `ENCRYPTION_KEY`

Note the public URL of the **api** service (e.g.
`https://spendops-api.up.railway.app`) - you need it for the Clerk + Stripe
webhook URLs (Steps 2.4, 4.3) and Vercel's `API_INTERNAL_URL`.

### Vercel (Next.js)

1. <https://vercel.com> → **Import** the repo. Root directory: `apps/web`.
   Framework preset: Next.js. Build is already green (`pnpm build`).
2. Set every var from `apps/web/.env.local.example` in **Settings →
   Environment Variables**, with:
   - `API_INTERNAL_URL` = Railway api service URL
   - live Clerk publishable key, live Stripe publishable key
3. Add your custom domain (e.g. `spendopsai.com`) and point DNS at Vercel.
4. Update Clerk (allowed domain), Slack (redirect URI), and `APP_URL` /
   `CORS_ORIGINS` on Railway to the final domain.

---

## Pre-launch smoke checklist (hard gate)

Run all of these against the deployed environment before announcing:

- [ ] **RLS two-tenant probe** - run `infra/scripts/smoke-test.sql` with two
      real org UUIDs; both cross-tenant counts must be 0
      ([setup.md](setup.md) Step 5)
- [ ] **Signup → chart**: fresh signup → create org → connect a real OpenAI
      Admin key → backfill runs → dashboard chart renders
- [ ] **Clerk webhook**: new user/org appear in Supabase `users` /
      `organizations` with `db_id` written back to Clerk metadata
- [ ] **Stripe test checkout end-to-end** (Step 4.4) - then repeat once in
      live mode with a real card and immediately refund
- [ ] **R2 round-trip**: `POST /reports/generate` → download PDF from
      `/reports` (Step 6.5)
- [ ] **Email**: trigger a budget alert (set a $1 budget) → email arrives
      from your verified domain
- [ ] **Slack**: connect a workspace → digest/alert posts to the channel
- [ ] **Celery beat** is running: check Railway logs for the nightly
      schedule registering (aggregation 00:30, anomalies 01:00, budgets
      02:00, recommendations 02:30 UTC, weekly digest Mon 09:00 UTC,
      monthly report 1st 06:00 UTC)

When the checklist is green, you are live. Next code work is Phase 4 of
[STRATEGIC_IMPLEMENTATION_PLAN.md](STRATEGIC_IMPLEMENTATION_PLAN.md) -
done-condition: 3 paying customers.
