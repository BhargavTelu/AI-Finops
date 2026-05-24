-- Add AI-generated explanation fields to anomalies.
-- explanation_generated_at enables the 24-hour cache check in the worker.

ALTER TABLE anomalies
    ADD COLUMN IF NOT EXISTS explanation TEXT,
    ADD COLUMN IF NOT EXISTS explanation_generated_at TIMESTAMPTZ;
