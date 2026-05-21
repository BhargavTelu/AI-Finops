-- Migration: 20260521000000_fix_budgets_schema
-- Fix budgets.scope_type CHECK constraint to match full spec enum.
-- Add notified_80_at / notified_100_at for once-per-threshold-per-month idempotency.

BEGIN;

-- 1. Drop the old constraint that only allowed ('global', 'tag', 'model')
ALTER TABLE budgets
    DROP CONSTRAINT IF EXISTS budgets_scope_type_check;

-- 2. Re-add with the full enum from project spec
ALTER TABLE budgets
    ADD CONSTRAINT budgets_scope_type_check
    CHECK (scope_type IN (
        'global',
        'provider',
        'model',
        'feature_tag',
        'team_tag',
        'customer_tag',
        'env_tag'
    ));

-- 3. Add notification timestamp columns (NULL = never notified this threshold)
ALTER TABLE budgets
    ADD COLUMN IF NOT EXISTS notified_80_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS notified_100_at TIMESTAMPTZ;

COMMIT;
