from fastapi import APIRouter, HTTPException

from api.deps import OrgDep

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("")
def get_billing(org: OrgDep) -> dict:
    """Return current plan and subscription status."""
    raise HTTPException(status_code=501, detail="Not yet implemented - available in M4")


@router.post("/checkout")
def create_checkout(org: OrgDep) -> dict:
    """Create a Stripe Checkout session and return the URL."""
    raise HTTPException(status_code=501, detail="Not yet implemented - available in M4")


@router.get("/portal")
def billing_portal(org: OrgDep) -> dict:
    """Return a Stripe Customer Portal redirect URL."""
    raise HTTPException(status_code=501, detail="Not yet implemented - available in M4")
