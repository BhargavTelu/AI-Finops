from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sentry_sdk
import structlog

from api.config import settings

# isort: off
# Must be imported before any router that calls .delay() so that @shared_task
# binds to the configured Celery app (Redis broker) rather than the default app
# (AMQP / no broker). The isort guard keeps formatters from sorting this back
# below the router imports - that exact regression shipped once in M1.
import api.workers.celery_app  # noqa: F401

# isort: on
from api.routers import (
    anomalies,
    billing,
    budgets,
    integrations,
    onboarding,
    recommendations,
    reports,
    slack,
    tags,
    usage,
    webhooks,
)

log = structlog.get_logger()


def create_app() -> FastAPI:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment=settings.env,
        )

    app = FastAPI(
        title="SpendOps AI API",
        version="0.1.0",
        # Disable interactive docs in production - no dev tool exposure
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url="/redoc" if settings.env != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    # Data routers gated behind an active subscription or running trial
    # (Phase 2). Config-class routers stay reachable when the trial lapses:
    # billing (the way out of the paywall), integrations/tags/slack/budgets
    # (settings), onboarding (checklist on the paywalled dashboard shell).
    from api.deps import require_active_org

    for router in [
        usage.router,
        anomalies.router,
        recommendations.router,
        reports.router,
    ]:
        app.include_router(router, prefix="/api/v1", dependencies=[require_active_org])

    for router in [
        integrations.router,
        tags.router,
        tags.tag_rules_router,
        budgets.router,
        slack.router,
        billing.router,
        onboarding.router,
    ]:
        app.include_router(router, prefix="/api/v1")

    # Webhooks at /api (no auth - verified by signature)
    app.include_router(webhooks.router, prefix="/api")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
