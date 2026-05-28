-- =============================================================================
-- Migration: 20260518000000_add_slack_digests
-- Adds idempotency table for Slack daily digest delivery.
--
-- The nightly notifications worker records a row here after successfully
-- posting the digest. On Celery retry the worker checks for an existing row
-- before posting, preventing duplicate messages to the same channel.
--
-- One row per (org_id, digest_date) - enforced by the UNIQUE constraint.
-- =============================================================================

CREATE TABLE slack_digests (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- The calendar day the digest covers (yesterday relative to send time).
    digest_date  DATE NOT NULL,
    sent_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Snapshot of which channel received the digest; channel may change
    -- if the Slack integration is reconfigured later.
    channel_id   TEXT NOT NULL,
    UNIQUE (org_id, digest_date)
);
CREATE INDEX idx_slack_digests_org_date ON slack_digests (org_id, digest_date DESC);

ALTER TABLE slack_digests ENABLE ROW LEVEL SECURITY;
CREATE POLICY slack_digests_iso ON slack_digests USING (org_id = (auth.jwt()->>'org_id')::uuid);
