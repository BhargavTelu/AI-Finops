from fastapi import APIRouter

from api.deps import OrgDep

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("")
async def list_tags(org: OrgDep) -> list:
    raise NotImplementedError


@router.post("", status_code=201)
async def create_tag(org: OrgDep) -> dict:
    raise NotImplementedError


@router.patch("/{tag_id}")
async def update_tag(tag_id: str, org: OrgDep) -> dict:
    raise NotImplementedError


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(tag_id: str, org: OrgDep) -> None:
    raise NotImplementedError


# ── Tag rules ────────────────────────────────────────────────────────────────
tag_rules_router = APIRouter(prefix="/tag-rules", tags=["tags"])


@tag_rules_router.get("")
async def list_tag_rules(org: OrgDep) -> list:
    raise NotImplementedError


@tag_rules_router.post("", status_code=201)
async def create_tag_rule(org: OrgDep) -> dict:
    raise NotImplementedError


@tag_rules_router.patch("/{rule_id}")
async def update_tag_rule(rule_id: str, org: OrgDep) -> dict:
    raise NotImplementedError


@tag_rules_router.delete("/{rule_id}", status_code=204)
async def delete_tag_rule(rule_id: str, org: OrgDep) -> None:
    raise NotImplementedError


@tag_rules_router.post("/preview")
async def preview_tag_rule(org: OrgDep) -> dict:
    """Dry-run a tag rule against recent usage_events without persisting."""
    raise NotImplementedError
