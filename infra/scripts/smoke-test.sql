-- =============================================================================
-- Smoke test: two-tenant RLS isolation probe.
-- Run as a Supabase service-role client BEFORE every deploy.
--
-- How it works:
--   1. INSERTs run as postgres (service role) - bypasses RLS intentionally
--      so we can seed test data without needing INSERT policies.
--   2. SET LOCAL ROLE authenticated - switches to the non-superuser role
--      that RLS policies actually apply to. Without this step the postgres
--      superuser bypasses every USING clause and sees all rows.
--   3. SET LOCAL "request.jwt.claims" - populates auth.jwt() so the policy
--      expression (org_id = (auth.jwt()->>'org_id')::uuid) can evaluate.
--   4. ROLLBACK - discards all test data; safe to re-run at any time.
-- =============================================================================

BEGIN;

-- Insert two isolated orgs
INSERT INTO organizations (id, name) VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001', 'Smoke Org A'),
    ('bbbbbbbb-0000-0000-0000-000000000002', 'Smoke Org B');

-- Insert one user per org (RLS probe for identity tables)
INSERT INTO users (id, email) VALUES
    ('aaaaaaaa-1111-0000-0000-000000000001', 'smoke-a@example.com'),
    ('bbbbbbbb-1111-0000-0000-000000000002', 'smoke-b@example.com');
INSERT INTO organization_members (org_id, user_id) VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-1111-0000-0000-000000000001'),
    ('bbbbbbbb-0000-0000-0000-000000000002', 'bbbbbbbb-1111-0000-0000-000000000002');

-- Insert daily cost data for each
INSERT INTO daily_cost_summaries (org_id, day, provider, model, total_cost_usd, total_requests, total_tokens)
VALUES
    ('aaaaaaaa-0000-0000-0000-000000000001', CURRENT_DATE, 'openai', 'gpt-4o', 100.00, 1000, 500000),
    ('bbbbbbbb-0000-0000-0000-000000000002', CURRENT_DATE, 'openai', 'gpt-4o', 200.00, 2000, 900000);

-- Switch to the authenticated role so RLS policies are enforced.
-- The postgres superuser skips all USING clauses - this line is mandatory.
SET LOCAL ROLE authenticated;

-- ── Probe as Org A ────────────────────────────────────────────────────────────
-- Simulate JWT claim for Org A
SET LOCAL "request.jwt.claims" = '{"org_id": "aaaaaaaa-0000-0000-0000-000000000001", "user_id": "aaaaaaaa-1111-0000-0000-000000000001", "role": "authenticated"}';

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

-- ── Identity-table probe as Org A ─────────────────────────────────────────────
DO $$
DECLARE
    row_count INT;
BEGIN
    -- Org A must not see Org B's user row (email enumeration guard)
    SELECT COUNT(*) INTO row_count FROM users
    WHERE email = 'smoke-b@example.com';
    IF row_count != 0 THEN
        RAISE EXCEPTION 'RLS ISOLATION FAILURE: Org A can read Org B user emails';
    END IF;

    -- Org A must see its own user row
    SELECT COUNT(*) INTO row_count FROM users
    WHERE email = 'smoke-a@example.com';
    IF row_count != 1 THEN
        RAISE EXCEPTION 'RLS FAILURE: Org A cannot read its own user row (% rows)', row_count;
    END IF;

    -- Org A must not see Org B's organization row
    SELECT COUNT(*) INTO row_count FROM organizations
    WHERE id = 'bbbbbbbb-0000-0000-0000-000000000002';
    IF row_count != 0 THEN
        RAISE EXCEPTION 'RLS ISOLATION FAILURE: Org A can read Org B organization row';
    END IF;

    RAISE NOTICE 'RLS probe PASSED: identity tables isolated for Org A';
END $$;

-- ── Probe as Org B ────────────────────────────────────────────────────────────
SET LOCAL "request.jwt.claims" = '{"org_id": "bbbbbbbb-0000-0000-0000-000000000002", "user_id": "bbbbbbbb-1111-0000-0000-000000000002", "role": "authenticated"}';

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
