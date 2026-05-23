-- =============================================================================
-- Migration: 20260523000001_usage_events_manual_override
-- Adds manual tag override support to usage_events.
--
-- Admins can pin specific tag values on a usage_events row. The ingestion
-- worker checks manual_override before re-applying tag rules so that
-- pinned assignments survive delete-before-insert re-ingestion cycles.
-- =============================================================================

ALTER TABLE usage_events
    ADD COLUMN manual_override      BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN manual_override_by   UUID        REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN manual_override_at   TIMESTAMPTZ;

-- Lets the ingestion worker fetch all overridden rows for a time window
-- in one query before executing its delete-before-insert.
CREATE INDEX idx_usage_events_manual_override
    ON usage_events (org_id, manual_override)
    WHERE manual_override = TRUE;
