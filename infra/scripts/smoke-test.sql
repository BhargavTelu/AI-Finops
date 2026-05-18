-- =============================================================================
-- Smoke test: two-tenant RLS isolation probe.
-- Run as a Supabase service-role client BEFORE every deploy.
-- The test itself uses SET LOCAL to simulate JWT org claims.
-- =============================================================================

BEGIN;

-- Insert two isolated orgs
INSERT INTO organizations (id, name) VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001', 'Smoke Org A'),
    ('bbbbbbbb-0000-0000-0000-000000000002', 'Smoke Org B');

-- Insert daily cost data for each
INSERT INTO daily_cost_summaries (org_id, day, provider, model, total_cost_usd, total_requests, total_tokens)
VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001', CURRENT_DATE, 'openai', 'gpt-4o', 100.00, 1000, 500000),
    ('bbbbbbbb-0000-0000-0000-000000000002', CURRENT_DATE, 'openai', 'gpt-4o', 200.00, 2000, 900000);

-- ── Probe as Org A ────────────────────────────────────────────────────────────
-- Simulate JWT claim for Org A
SET LOCAL "request.jwt.claims" = '{"org_id": "aaaaaaaa-0000-0000-0000-000000000001"}';

DO $$
DECLARE
    row_count INT;
BEGIN
    SELECT COUNT(*) INTO row_count
    FROM daily_cost_summaries
    WHERE day = CURRENT_DATE;

    -- Org A should only see its own 1 row, never Org B's
    IF row_count != 1 THEN
        RAISE EXCEPTION 'RLS ISOLATION FAILURE: Org A sees % rows, expected 1', row_count;
    END IF;
    RAISE NOTICE 'RLS probe PASSED: Org A sees exactly 1 row';
END $$;

-- ── Probe as Org B ────────────────────────────────────────────────────────────
SET LOCAL "request.jwt.claims" = '{"org_id": "bbbbbbbb-0000-0000-0000-000000000002"}';

DO $$
DECLARE
    row_count INT;
BEGIN
    SELECT COUNT(*) INTO row_count
    FROM daily_cost_summaries
    WHERE day = CURRENT_DATE;

    IF row_count != 1 THEN
        RAISE EXCEPTION 'RLS ISOLATION FAILURE: Org B sees % rows, expected 1', row_count;
    END IF;
    RAISE NOTICE 'RLS probe PASSED: Org B sees exactly 1 row';
END $$;

ROLLBACK;  -- Clean up test data
