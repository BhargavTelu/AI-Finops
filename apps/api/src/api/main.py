import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routers import (
    anomalies,
    billing,
    budgets,
    integrations,
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
        title="AI FinOps API",
        version="0.1.0",
        # Disable interactive docs in production — no dev tool exposure
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

    # All business routes under /api/v1
    for router in [
        integrations.router,
        usage.router,
        tags.router,
        tags.tag_rules_router,
        budgets.router,
        anomalies.router,
        recommendations.router,
        slack.router,
        reports.router,
        billing.router,
    ]:
        app.include_router(router, prefix="/api/v1")

    # Webhooks at /api (no auth — verified by signature)
    app.include_router(webhooks.router, prefix="/api")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
