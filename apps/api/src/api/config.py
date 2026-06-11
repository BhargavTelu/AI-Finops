from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str

    # ── Clerk ─────────────────────────────────────────────────────────────────
    clerk_secret_key: str
    clerk_webhook_secret: str
    # Frontend API URL shown in Clerk Dashboard → API Keys.
    # Example: https://your-instance.clerk.accounts.dev
    # Used to derive the JWKS endpoint for JWT verification.
    clerk_issuer: str

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Stripe ────────────────────────────────────────────────────────────────
    stripe_secret_key: str
    stripe_webhook_secret: str
    # Price IDs for the three plans (Stripe Dashboard → Products). Empty in
    # environments where billing is not configured - checkout returns 503.
    stripe_price_starter: str = ""
    stripe_price_growth: str = ""
    stripe_price_enterprise: str = ""

    # ── Resend ────────────────────────────────────────────────────────────────
    resend_api_key: str
    from_email: str = "noreply@yourdomain.com"

    # ── App ───────────────────────────────────────────────────────────────────
    # Public URL of the web app - used in email CTAs (e.g. report-ready links).
    app_url: str = "http://localhost:3000"

    # ── Slack ──────────────────────────────────────────────────────────────────
    # Create a Slack app at api.slack.com/apps, request scopes:
    #   incoming-webhook, chat:write
    # Set redirect URI to: <NEXT_PUBLIC_APP_URL>/settings/slack/callback
    slack_client_id: str = ""
    slack_client_secret: str = ""
    # Must match exactly what's registered in the Slack app settings.
    slack_redirect_uri: str = "http://localhost:3000/settings/slack/callback"

    # ── Cloudflare R2 ─────────────────────────────────────────────────────────
    r2_bucket_name: str = ""
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    # ── Sentry ────────────────────────────────────────────────────────────────
    sentry_dsn: str = ""

    # ── PostHog (server-side capture) ─────────────────────────────────────────
    # Project API key for server-side funnel events (signup, org_created,
    # checkout_completed). Empty = capture disabled. Same key as
    # NEXT_PUBLIC_POSTHOG_KEY - PostHog project keys are write-only.
    posthog_api_key: str = ""
    posthog_host: str = "https://app.posthog.com"

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Encryption ────────────────────────────────────────────────────────────
    # 32-byte AES-256-GCM key, base64-encoded.
    # Generated via Supabase Vault in production - never in env vars.
    encryption_key: str = ""

    # ── Internal AI (platform's own key - not customer keys) ──────────────────
    # Used by Celery workers for rule-based → AI recommendation upgrade (V1),
    # anomaly explainer narratives, and the monthly CFO narrative (M4).
    # Empty in M0–M2 while recommendations are rule-based.
    anthropic_api_key: str = ""

    # ── AI rate-limit ─────────────────────────────────────────────────────────
    ai_calls_per_org_per_day: int = 3

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            import json

            return json.loads(v)
        return v


# Singleton - import this everywhere.
settings = Settings()
