-- Phase 2: Stripe webhook idempotency.
-- One row per processed Stripe event id - INSERT acts as a claim; a conflict
-- means the event was already handled (Stripe retries deliveries, and replays
-- must not double-process billing transitions).
-- Not org-scoped: RLS enabled with NO policies so only the service-role
-- client (which bypasses RLS) can touch it.

CREATE TABLE stripe_events (
    id          TEXT PRIMARY KEY,           -- Stripe event id (evt_...)
    type        TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE stripe_events ENABLE ROW LEVEL SECURITY;
