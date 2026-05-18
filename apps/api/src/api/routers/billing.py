from fastapi import APIRouter

from api.deps import OrgDep

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("")
async def get_billing(org: OrgDep) -> dict:
    """Return current plan and subscription status."""
    raise NotImplementedError


@router.post("/checkout")
async def create_checkout(org: OrgDep) -> dict:
    """Create a Stripe Checkout session and return the URL."""
    raise NotImplementedError


@router.get("/portal")
async def billing_portal(org: OrgDep) -> dict:
    """Return a Stripe Customer Portal redirect URL."""
    raise NotImplementedError
