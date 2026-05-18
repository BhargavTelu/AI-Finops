from fastapi import APIRouter, Header, Request

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="stripe-signature"),
) -> dict:
    """
    Verify Stripe signature and process billing lifecycle events.
    Updates the billing table on checkout.session.completed,
    customer.subscription.updated, and customer.subscription.deleted.
    """
    raise NotImplementedError


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    svix_id: str = Header(alias="svix-id"),
    svix_timestamp: str = Header(alias="svix-timestamp"),
    svix_signature: str = Header(alias="svix-signature"),
) -> dict:
    """
    Verify Clerk webhook signature (Svix) and sync user/org data.
    Handles: user.created, organization.created, organizationMembership.created.
    """
    raise NotImplementedError
