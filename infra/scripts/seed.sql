-- =============================================================================
-- Seed data for local development.
-- Run AFTER migrations in a local Supabase instance.
-- Do NOT run against staging or production.
-- =============================================================================

-- Dev org and user
INSERT INTO organizations (id, name, plan) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Dev Org', 'growth')
ON CONFLICT (id) DO NOTHING;

INSERT INTO users (id, email, full_name) VALUES
    ('22222222-2222-2222-2222-222222222222', 'dev@example.com', 'Dev User')
ON CONFLICT (id) DO NOTHING;

INSERT INTO organization_members (org_id, user_id, role) VALUES
    ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'admin')
ON CONFLICT DO NOTHING;

-- Billing record
INSERT INTO billing (org_id, plan, status) VALUES
    ('11111111-1111-1111-1111-111111111111', 'growth', 'active')
ON CONFLICT (org_id) DO NOTHING;

-- Sample daily cost data (last 30 days, openai/gpt-4o)
INSERT INTO daily_cost_summaries (org_id, day, provider, model, feature_tag, total_cost_usd, total_requests, total_tokens)
SELECT
    '11111111-1111-1111-1111-111111111111',
    CURRENT_DATE - (n || ' days')::INTERVAL,
    'openai',
    'gpt-4o',
    CASE WHEN n % 3 = 0 THEN 'search' WHEN n % 3 = 1 THEN 'chat' ELSE 'summarize' END,
    (50 + random() * 150)::NUMERIC(14,6),
    (500 + (random() * 2000)::INT),
    (200000 + (random() * 800000)::BIGINT)
FROM generate_series(1, 30) AS n
ON CONFLICT DO NOTHING;
