# Auth Setup — Clerk + Supabase JWT Bridge

This document covers the one-time infra configuration required for the
Clerk → Supabase → RLS chain to work. Nothing in this doc is code — it is
all dashboard clicks and env var values. Do this before running M0 feature
work.

---

## Why this matters

Supabase RLS policies check `auth.jwt()->>'org_id'`. That function reads
the JWT that the Supabase client presents on each query. By default the
Supabase client uses the **anon key**, which carries no user or org
context — every RLS policy silently returns zero rows.

To fix this, Supabase must be told to accept JWTs issued by Clerk, and the
frontend must present those Clerk-issued JWTs (not the anon key) when
making Supabase queries.

There are two sides to configure: Clerk (JWT template) and Supabase (JWT
secret). They must use the same signing secret.

---

## Step 1 — Create the Supabase JWT template in Clerk

1. Open **Clerk Dashboard** → your application → **JWT Templates**.
2. Click **New template** → choose **Supabase** (or blank).
3. Set the template name to `supabase` (exact — the frontend code uses
   this name when calling `getToken({ template: 'supabase' })`).
4. Set the **Signing algorithm** to `HS256`.
5. Replace the default claims with:

   ```json
   {
     "role": "authenticated",
     "org_id": "{{org.public_metadata.db_id}}",
     "user_id": "{{user.public_metadata.db_id}}"
   }
   ```

   `role: "authenticated"` is required for Supabase to treat the request
   as an authenticated user. `org_id` and `user_id` must be the Supabase
   UUIDs (not Clerk's own string IDs like `org_2...`) because every RLS
   policy casts `auth.jwt()->>'org_id'` to `::uuid`. The Clerk webhook
   handler writes these UUIDs into `public_metadata.db_id` automatically
   when a user or org is first created.

6. Click **Save**. Clerk will show a **Signing secret** — copy it. You
   will paste it into Supabase in the next step.

> **Important:** `{{org.public_metadata.db_id}}` is only populated after
> the Clerk webhook fires and the backend writes the DB UUID back to Clerk
> metadata. The frontend must call `clerk.setActive({ organization: orgId })`
> after org selection, and users must refresh their session (sign out/in or
> wait for token rotation) if they sign up before the webhook completes.
> In practice the webhook completes in well under a second so this race
> window is not user-visible.

---

## Step 2 — Set the JWT secret in Supabase

1. Open **Supabase Dashboard** → your project → **Settings** →
   **API** → scroll to **JWT Settings**.
2. Paste the **Signing secret** from the Clerk template (Step 1) into
   the **JWT Secret** field.
3. Click **Save**. The change takes effect immediately — no restart needed.

Supabase will now accept HS256 tokens signed by Clerk. Any token whose
`org_id` claim matches the `org_id` column passes RLS.

---

## Step 3 — Update the frontend Supabase client

The Supabase client in `apps/web/src/lib/supabase/` must attach the
Clerk-issued Supabase token (HS256, from the `supabase` template) on every
request — **not** the anon key or the Clerk session JWT.

The standard pattern using `@clerk/nextjs` and `@supabase/ssr`:

```ts
// In a Server Component or Route Handler:
import { auth } from "@clerk/nextjs/server";
import { createClient } from "@supabase/ssr";

const { getToken } = await auth();
const supabaseToken = await getToken({ template: "supabase" });

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  {
    global: {
      headers: { Authorization: `Bearer ${supabaseToken}` },
    },
  }
);
```

`apps/web/src/lib/supabase/server.ts` needs to be updated to accept a
token parameter and pass it via the `Authorization` header. This is M0
feature work — the current cookie-based scaffold does not do this.

---

## Step 4 — FastAPI: set `CLERK_ISSUER`

The FastAPI backend (`deps.py`) verifies Clerk session JWTs (RS256) against
Clerk's JWKS endpoint. The issuer URL is required.

1. Open **Clerk Dashboard** → **API Keys**.
2. Copy the **Frontend API URL** (format:
   `https://your-instance.clerk.accounts.dev`).
3. Add it to `apps/api/.env`:

   ```
   CLERK_ISSUER=https://your-instance.clerk.accounts.dev
   ```

The JWKS endpoint used is `{CLERK_ISSUER}/.well-known/jwks.json`. No
other Clerk config is needed for the backend JWT check.

> **Two different JWTs in play:**
>
> | JWT | Algorithm | Used by | Contains |
> |---|---|---|---|
> | Clerk session token | RS256 | FastAPI (`deps.py`) | `sub`, `org_id` |
> | Clerk Supabase template | HS256 | Supabase client | `role`, `org_id` |
>
> They are issued by the same Clerk instance but are different tokens with
> different signing keys. Never pass the session token to Supabase or the
> Supabase token to FastAPI.

---

## Step 5 — Two-tenant smoke test

Before shipping M0, run this against your staging Supabase instance to
confirm RLS is actually isolating orgs:

```sql
-- infra/scripts/smoke-test.sql
-- Call this with two real org UUIDs from your test data.
-- Both queries must return 0 rows for RLS to be working.

-- Attempt to read org_b's integrations while authenticated as org_a:
SET request.jwt.claims = '{"org_id": "<org_a_uuid>", "role": "authenticated"}';
SET role = authenticated;
SELECT count(*) FROM integrations WHERE org_id = '<org_b_uuid>';
-- Expected: 0

SET request.jwt.claims = '{"org_id": "<org_b_uuid>", "role": "authenticated"}';
SELECT count(*) FROM integrations WHERE org_id = '<org_a_uuid>';
-- Expected: 0
```

This probe is a hard gate before every deploy (see `architecture.md`
§ Pre-deploy smoke).

---

## Env var checklist

| Location | Variable | Where to find it |
|---|---|---|
| `apps/api/.env` | `CLERK_ISSUER` | Clerk Dashboard → API Keys → Frontend API URL |
| `apps/api/.env` | `CLERK_SECRET_KEY` | Clerk Dashboard → API Keys |
| `apps/api/.env` | `CLERK_WEBHOOK_SECRET` | Clerk Dashboard → Webhooks → signing secret |
| `apps/web/.env.local` | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk Dashboard → API Keys |
| `apps/web/.env.local` | `NEXT_PUBLIC_SUPABASE_URL` | Supabase Dashboard → Settings → API |
| `apps/web/.env.local` | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API |
| Supabase Dashboard | JWT Secret | Copy from Clerk JWT Template signing secret (Step 1) |
