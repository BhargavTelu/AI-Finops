from fastapi import APIRouter, HTTPException
import structlog

from api.deps import OrgDep
from api.schemas.tags import (
    PreviewMatch,
    TagCreate,
    TagRead,
    TagRuleCreate,
    TagRulePreview,
    TagRuleRead,
)
from api.services.db import get_supabase
from api.services.tag_engine import CompiledRule, _matches

log = structlog.get_logger()

router = APIRouter(prefix="/tags", tags=["tags"])
tag_rules_router = APIRouter(prefix="/tag-rules", tags=["tags"])


def _get_supabase():
    return get_supabase()


# ── Tags CRUD ─────────────────────────────────────────────────────────────────

@router.get("")
def list_tags(org: OrgDep) -> list[TagRead]:
    db = _get_supabase()
    result = (
        db.table("tags")
        .select("*")
        .eq("org_id", org.org_id)
        .order("type")
        .order("name")
        .execute()
    )
    return [TagRead(**row) for row in result.data]


@router.post("", status_code=201)
def create_tag(body: TagCreate, org: OrgDep) -> TagRead:
    db = _get_supabase()
    try:
        result = (
            db.table("tags")
            .insert(
                {
                    "org_id": org.org_id,
                    "type": body.type,
                    "name": body.name,
                    "color": body.color,
                }
            )
            .execute()
        )
    except Exception as exc:
        err_msg = str(exc)
        if "unique" in err_msg.lower() or "duplicate" in err_msg.lower():
            raise HTTPException(
                status_code=409,
                detail=f"Tag of type '{body.type}' with name '{body.name}' already exists",
            ) from exc
        log.error("tag_insert_failed", org_id=org.org_id, error=err_msg)
        raise HTTPException(status_code=500, detail="Failed to create tag") from exc

    return TagRead(**result.data[0])


@router.patch("/{tag_id}")
def update_tag(tag_id: str, body: TagCreate, org: OrgDep) -> TagRead:
    db = _get_supabase()
    result = (
        db.table("tags")
        .update({"name": body.name, "color": body.color})
        .eq("id", tag_id)
        .eq("org_id", org.org_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Tag not found")
    return TagRead(**result.data[0])


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: str, org: OrgDep) -> None:
    db = _get_supabase()
    # tag_rules cascade-delete via FK ON DELETE CASCADE
    result = (
        db.table("tags")
        .delete()
        .eq("id", tag_id)
        .eq("org_id", org.org_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Tag not found")


# ── Tag rules ─────────────────────────────────────────────────────────────────

@tag_rules_router.get("")
def list_tag_rules(org: OrgDep) -> list[TagRuleRead]:
    db = _get_supabase()
    result = (
        db.table("tag_rules")
        .select("*, tags(type, name)")
        .eq("org_id", org.org_id)
        .order("priority")
        .execute()
    )
    return [TagRuleRead(**row) for row in result.data]


@tag_rules_router.post("", status_code=201)
def create_tag_rule(body: TagRuleCreate, org: OrgDep) -> TagRuleRead:
    db = _get_supabase()

    # Verify tag_id belongs to this org before creating the rule
    tag_check = (
        db.table("tags")
        .select("id")
        .eq("id", body.tag_id)
        .eq("org_id", org.org_id)
        .execute()
    )
    if not tag_check.data:
        raise HTTPException(status_code=404, detail="Tag not found")

    result = (
        db.table("tag_rules")
        .insert(
            {
                "org_id": org.org_id,
                "tag_id": body.tag_id,
                "match_type": body.match_type,
                "match_pattern": body.match_pattern,
                "priority": body.priority,
                "enabled": body.enabled,
            }
        )
        .execute()
    )
    return TagRuleRead(**result.data[0])


@tag_rules_router.patch("/{rule_id}")
def update_tag_rule(rule_id: str, body: TagRuleCreate, org: OrgDep) -> TagRuleRead:
    db = _get_supabase()
    result = (
        db.table("tag_rules")
        .update(
            {
                "match_type": body.match_type,
                "match_pattern": body.match_pattern,
                "priority": body.priority,
                "enabled": body.enabled,
            }
        )
        .eq("id", rule_id)
        .eq("org_id", org.org_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Tag rule not found")
    return TagRuleRead(**result.data[0])


@tag_rules_router.delete("/{rule_id}", status_code=204)
def delete_tag_rule(rule_id: str, org: OrgDep) -> None:
    db = _get_supabase()
    result = (
        db.table("tag_rules")
        .delete()
        .eq("id", rule_id)
        .eq("org_id", org.org_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Tag rule not found")


@tag_rules_router.post("/preview")
def preview_tag_rule(body: TagRulePreview, org: OrgDep) -> list[PreviewMatch]:
    """
    Dry-run a tag rule against recent usage_events without persisting.
    Returns up to 20 matching (api_key_label, provider, model) tuples from the
    last 7 days of this org's usage events.
    """
    from datetime import datetime, timedelta, timezone

    db = _get_supabase()

    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows_result = (
        db.table("usage_events")
        .select("api_key_label, provider, model")
        .eq("org_id", org.org_id)
        .gte("bucket_hour", since)
        .limit(200)
        .execute()
    )

    # Deduplicate by (label, provider, model) and test match
    seen: set[tuple[str, str, str]] = set()
    matches: list[PreviewMatch] = []

    # Build a single fake rule to reuse the engine's _matches function
    fake_rule = CompiledRule(
        tag_type="feature",  # type is irrelevant for match testing
        tag_name="preview",
        match_type=body.match_type,
        match_pattern=body.match_pattern,
        priority=0,
    )

    for row in rows_result.data:
        label = row.get("api_key_label") or ""
        provider = row.get("provider", "")
        model = row.get("model", "")
        key = (label, provider, model)
        if key in seen:
            continue
        seen.add(key)

        if _matches(fake_rule, label):
            matches.append(PreviewMatch(api_key_label=label, provider=provider, model=model))
            if len(matches) >= 20:
                break

    return matches
