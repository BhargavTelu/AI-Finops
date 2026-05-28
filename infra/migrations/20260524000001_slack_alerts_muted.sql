-- Add alerts_muted flag to slack_integrations.
-- When true, anomaly alerts and budget Slack notifications are suppressed.
-- The daily digest is unaffected - it is informational, not an alert.

ALTER TABLE slack_integrations
    ADD COLUMN IF NOT EXISTS alerts_muted BOOLEAN NOT NULL DEFAULT FALSE;
