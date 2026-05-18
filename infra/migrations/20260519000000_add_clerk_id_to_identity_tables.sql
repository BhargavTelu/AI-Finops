-- =============================================================================
-- Migration: 20260519000000_add_clerk_id_to_identity_tables
-- Adds clerk_id columns to users and organizations so the webhook handler can:
--   1. Upsert rows idempotently on Clerk events.
--   2. Look up DB UUIDs by Clerk ID when creating memberships.
--   3. Write those UUIDs back to Clerk public_metadata so the Supabase JWT
--      template can embed a real UUID as org_id — required for the ::uuid cast
--      in every RLS policy.
--
-- NULL is allowed so existing rows (if any) aren't blocked; the webhook sets
-- clerk_id on every row it creates. UNIQUE enforces no two rows share a
-- Clerk ID (Postgres allows multiple NULLs in a UNIQUE column per SQL standard).
-- =============================================================================

ALTER TABLE users
    ADD COLUMN clerk_id TEXT UNIQUE;

ALTER TABLE organizations
    ADD COLUMN clerk_id TEXT UNIQUE;
