-- =============================================================================
-- Migration: 20260518000001_add_updated_at_to_users_and_orgs
-- Adds updated_at column to users and organizations.
--
-- Convention: every mutable table carries created_at + updated_at.
-- Both tables were created in 20240101000000_initial_schema without
-- updated_at because they were initially considered append-only mirrors
-- of Clerk data. In practice both are mutated via Clerk webhooks
-- (name changes, plan upgrades) so they need the column.
--
-- The set_updated_at() trigger function is defined in the initial schema
-- migration and is already available.
-- =============================================================================

-- ── users ────────────────────────────────────────────────────────────────────
ALTER TABLE users
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── organizations ─────────────────────────────────────────────────────────────
ALTER TABLE organizations
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TRIGGER trg_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
