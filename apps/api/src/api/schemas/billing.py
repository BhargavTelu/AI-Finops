from datetime import datetime
from typing import Literal

from pydantic import BaseModel

PlanName = Literal["starter", "growth", "enterprise"]


class CheckoutRequest(BaseModel):
    plan: PlanName


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


class BillingStatus(BaseModel):
    # 'trial' until the first successful checkout, then the Stripe plan name.
    plan: str
    # Stripe subscription status ('active', 'past_due', ...) or 'trialing'
    # while on the built-in 14-day trial with no subscription yet.
    status: str
    has_subscription: bool
    current_period_end: datetime | None
    trial_ends_at: datetime | None
    trial_days_left: int | None  # None once subscribed or after trial ends
    # The gating verdict the API will apply - lets the web shell render the
    # paywall without duplicating the rule client-side.
    access_blocked: bool
