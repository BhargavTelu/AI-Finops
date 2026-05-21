from datetime import datetime

from pydantic import BaseModel


class SlackOAuthCallbackBody(BaseModel):
    code: str
    state: str  # CSRF token — validated against the org_id in the JWT


class SlackStatusResponse(BaseModel):
    connected: bool
    workspace_id: str | None = None
    channel_name: str | None = None
    channel_id: str | None = None
    installed_at: datetime | None = None
