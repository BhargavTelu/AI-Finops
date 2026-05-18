from fastapi import APIRouter

from api.deps import OrgDep

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post("", status_code=201)
async def create_integration(org: OrgDep) -> dict:
    """
    Add a provider Admin API key.
    Validates the key, AES-256-GCM encrypts it, stores it, and enqueues backfill.
    Key is never returned after this call.
    """
    raise NotImplementedError


@router.get("")
async def list_integrations(org: OrgDep) -> list:
    """List all integrations for the org (key redacted)."""
    raise NotImplementedError


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(integration_id: str, org: OrgDep) -> None:
    """Revoke and delete a provider integration. Logs to audit_events."""
    raise NotImplementedError


@router.post("/{integration_id}/test")
async def test_integration(integration_id: str, org: OrgDep) -> dict:
    """Revalidate the stored key and trigger a fresh backfill job."""
    raise NotImplementedError
