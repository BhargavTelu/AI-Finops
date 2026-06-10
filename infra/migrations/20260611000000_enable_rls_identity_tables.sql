-- =============================================================================
-- Migration: 20260611000000_enable_rls_identity_tables
-- Enables RLS on users and organizations.
--
-- Both tables were created in 20240101000000_initial_schema WITHOUT RLS.
-- On Supabase, public-schema tables are granted to the anon/authenticated
-- roles by default, so any holder of the anon key could enumerate every
-- user's email/full_name and every organization's name/plan/trial dates
-- across all tenants.
--
-- The backend uses the service-role key and is unaffected (service role
-- bypasses RLS). The Clerk "supabase" JWT template provides org_id and
-- user_id claims (Supabase UUIDs) - see docs/setup.md.
-- =============================================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

-- A user can see their own row, plus the rows of members of their active org
-- (needed for any future member-list UI). The subquery runs under the caller's
-- privileges, so the organization_members RLS policy applies to it as well.
CREATE POLICY users_self_or_org_member ON users
    USING (
        id = (auth.jwt()->>'user_id')::uuid
        OR id IN (
            SELECT user_id FROM organization_members
            WHERE org_id = (auth.jwt()->>'org_id')::uuid
        )
    );

-- Only the active org from the JWT is visible.
CREATE POLICY organizations_active_org ON organizations
    USING (id = (auth.jwt()->>'org_id')::uuid);
