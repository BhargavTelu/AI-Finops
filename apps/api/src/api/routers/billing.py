"""
Billing endpoints (Phase 2 / FR-21). No custom billing UI - Stripe Checkout
for purchase, Stripe Customer Portal for everything after (card, cancel,
invoices). These routes only mint redirect URLs and report state.
"""

from fastapi import APIRouter, HTTPException
import stripe
import structlog

from api.config import settings
from api.deps import OrgDep
from api.schemas.billing import (
    BillingStatus,
    CheckoutRequest,
    CheckoutResponse,
    PlanName,
    PortalResponse,
)
from api.services.billing_access import evaluate_access
from api.services.db import get_supabase

log = structlog.get_logger()

router = APIRouter(prefix="/billing", tags=["billing"])


def _get_supabase():
    return get_supabase()


def _price_id(plan: PlanName) -> str:
    return {
        "starter": settings.stripe_price_starter,
        "growth": settings.stripe_price_growth,
        "enterprise": settings.stripe_price_enterprise,
    }[plan]


def _billing_row(db, org_id: str) -> dict | None:
    result = (
        db.table("billing")
        .select("plan, status, stripe_customer_id, stripe_subscription_id, current_period_end")
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


@router.get("")
def get_billing(org: OrgDep) -> BillingStatus:
    """Current plan, subscription status, and the gating verdict."""
    db = _get_supabase()
    org_result = (
        db.table("organizations")
        .select("trial_ends_at, plan")
        .eq("id", org.org_id)
        .limit(1)
        .execute()
    )
    state = evaluate_access(
        org_result.data[0] if org_result.data else None,
        _billing_row(db, org.org_id),
    )
    return BillingStatus(
        plan=state.plan,
        status=state.status,
        has_subscription=state.has_subscription,
        current_period_end=state.current_period_end,
        trial_ends_at=state.trial_ends_at,
        trial_days_left=state.trial_days_left,
        access_blocked=state.access_blocked,
    )


@router.post("/checkout")
def create_checkout(body: CheckoutRequest, org: OrgDep) -> CheckoutResponse:
    """Create a Stripe Checkout session and return its URL."""
    price_id = _price_id(body.plan)
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured for this environment.",
        )

    db = _get_supabase()
    existing = _billing_row(db, org.org_id)
    customer_id = existing.get("stripe_customer_id") if existing else None

    stripe.api_key = settings.stripe_secret_key
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=org.org_id,
            # Reuse the customer on re-subscribe so Stripe history stays whole.
            customer=customer_id or None,
            success_url=f"{settings.app_url}/settings/billing?checkout=success",
            cancel_url=f"{settings.app_url}/settings/billing?checkout=cancelled",
            metadata={"org_id": org.org_id, "plan": body.plan},
            subscription_data={"metadata": {"org_id": org.org_id, "plan": body.plan}},
        )
    except stripe.StripeError as exc:
        log.error("checkout_session_failed", org_id=org.org_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Could not start checkout.") from exc

    log.info("checkout_session_created", org_id=org.org_id, plan=body.plan)
    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe returned no checkout URL.")
    return CheckoutResponse(url=session.url)


@router.get("/portal")
def billing_portal(org: OrgDep) -> PortalResponse:
    """Stripe Customer Portal redirect - card changes, cancellation, invoices."""
    db = _get_supabase()
    existing = _billing_row(db, org.org_id)
    customer_id = existing.get("stripe_customer_id") if existing else None
    if not customer_id:
        raise HTTPException(
            status_code=404,
            detail="No billing account yet - subscribe to a plan first.",
        )

    stripe.api_key = settings.stripe_secret_key
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{settings.app_url}/settings/billing",
        )
    except stripe.StripeError as exc:
        log.error("portal_session_failed", org_id=org.org_id, error=str(exc))
        raise HTTPException(status_code=502, detail="Could not open the billing portal.") from exc

    return PortalResponse(url=session.url)
