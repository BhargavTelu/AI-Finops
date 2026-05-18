from fastapi import APIRouter

from api.deps import OrgDep

router = APIRouter(prefix="/slack", tags=["slack"])


@router.post("/oauth/callback")
async def slack_oauth_callback(org: OrgDep) -> dict:
    """Exchange Slack OAuth code for bot token, encrypt, and store."""
    raise NotImplementedError


@router.post("/disconnect", status_code=204)
async def slack_disconnect(org: OrgDep) -> None:
    """Revoke and remove the Slack integration."""
    raise NotImplementedError
