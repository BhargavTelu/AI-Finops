-- Add scope_value to recommendations for per-rule deduplication.
-- scope_value stores the key that identifies what the recommendation is about
-- (e.g. model name for model_swap/batch, "model:tag" for caching).
-- The partial unique index prevents re-inserting an identical open recommendation.

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS scope_value TEXT;

-- Partial unique index: one open recommendation per (org, type, scope_value).
-- Does NOT block re-generating a rec for a scope that was previously applied/dismissed.
CREATE UNIQUE INDEX IF NOT EXISTS idx_recommendations_unique_open
    ON recommendations (org_id, type, scope_value)
    WHERE status = 'new';
