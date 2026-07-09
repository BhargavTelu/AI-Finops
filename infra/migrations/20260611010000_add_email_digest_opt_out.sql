-- Phase 3: weekly email digest opt-out.
-- Orgs with Slack connected never receive the email digest (Slack-first
-- principle - no double-notification); this flag silences it for the rest.
-- Opt-out is handled manually at current scale (reply to the email);
-- a settings toggle ships when there is more than one request for it.

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS email_digest_opt_out BOOLEAN NOT NULL DEFAULT FALSE;
