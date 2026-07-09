from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import status as http_status
import structlog

from api.deps import OrgDep
from api.schemas.budgets import BudgetCreate, BudgetRead, BudgetUpdate
from api.services.db import fetch_all_pages, get_supabase

log = structlog.get_logger()

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _get_supabase() -> Any:
    return get_supabase()


def _mtd_date_range() -> tuple[str, str]:
    """Return ISO date strings for the first day of the current month through today."""
    today = datetime.now(UTC).date()
    first_day = today.replace(day=1)
    return first_day.isoformat(), today.isoformat()


def _compute_mtd_spend(db: Any, org_id: str, scope_type: str, scope_value: str | None) -> Decimal:
    """
    Sum daily_cost_summaries for the current calendar month scoped to this budget.
    Tag columns use empty string for unset - treat NULL and '' as 'unset'.
    """
    first_day, today = _mtd_date_range()

    def build_query() -> Any:
        q = (
            db.table("daily_cost_summaries")
            .select("total_cost_usd")
            .eq("org_id", org_id)
            .gte("day", first_day)
            .lte("day", today)
        )
        if scope_type == "global":
            pass  # no additional filter - sum everything
        elif scope_type == "provider":
            q = q.eq("provider", scope_value)
        elif scope_type == "model":
            q = q.eq("model", scope_value)
        elif scope_type == "feature_tag":
            q = q.eq("feature_tag", scope_value)
        elif scope_type == "team_tag":
            q = q.eq("team_tag", scope_value)
        elif scope_type == "customer_tag":
            q = q.eq("customer_tag", scope_value)
        elif scope_type == "env_tag":
            q = q.eq("env_tag", scope_value)
        return q

    # Paged: an unpaged sum under-reports MTD spend (and spent_pct) once the
    # month's summary rows exceed the PostgREST max-rows cap.
    rows = fetch_all_pages(build_query)
    return sum((Decimal(str(row["total_cost_usd"])) for row in rows), Decimal("0"))


def _to_budget_read(row: dict[str, Any], mtd_spend: Decimal) -> BudgetRead:
    limit = Decimal(str(row["monthly_limit"]))
    spent_pct = int((mtd_spend / limit * 100).to_integral_value()) if limit else 0
    return BudgetRead(
        id=row["id"],
        org_id=row["org_id"],
        scope_type=row["scope_type"],
        scope_value=row.get("scope_value"),
        monthly_limit=limit,
        alert_at_pct=row["alert_at_pct"],
        hard_cap=row["hard_cap"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        current_spend_mtd=mtd_spend,
        spent_pct=spent_pct,
    )


@router.get("", response_model=list[BudgetRead])
def list_budgets(org: OrgDep) -> list[BudgetRead]:
    db = _get_supabase()
    result = (
        db.table("budgets")
        .select(
            "id, org_id, scope_type, scope_value, monthly_limit, alert_at_pct,"
            " hard_cap, created_at, updated_at"
        )
        .eq("org_id", org.org_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [
        _to_budget_read(
            row, _compute_mtd_spend(db, org.org_id, row["scope_type"], row.get("scope_value"))
        )
        for row in result.data
    ]


@router.post("", status_code=201, response_model=BudgetRead)
def create_budget(body: BudgetCreate, org: OrgDep) -> BudgetRead:
    # scope_value must be set for every scope_type except 'global'
    if body.scope_type != "global" and not body.scope_value:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"scope_value is required for scope_type '{body.scope_type}'",
        )
    if body.scope_type == "global":
        body = body.model_copy(update={"scope_value": None})

    db = _get_supabase()

    # Uniqueness: one active budget per (org_id, scope_type, scope_value).
    # The DB has no UNIQUE constraint for this - enforced in application layer.
    dupe_q = (
        db.table("budgets").select("id").eq("org_id", org.org_id).eq("scope_type", body.scope_type)
    )
    if body.scope_value is None:
        dupe_q = dupe_q.is_("scope_value", "null")
    else:
        dupe_q = dupe_q.eq("scope_value", body.scope_value)

    if dupe_q.limit(1).execute().data:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="A budget with this scope already exists",
        )

    # org.user_id is the Clerk sub claim (not a UUID). Resolve the Supabase
    # users.id UUID so the FK constraint on created_by is satisfied.
    user_row = db.table("users").select("id").eq("clerk_id", org.user_id).limit(1).execute()
    created_by: str | None = user_row.data[0]["id"] if user_row.data else None

    insert_result = (
        db.table("budgets")
        .insert(
            {
                "org_id": org.org_id,
                "scope_type": body.scope_type,
                "scope_value": body.scope_value,
                "monthly_limit": str(body.monthly_limit),
                "alert_at_pct": body.alert_at_pct,
                "hard_cap": body.hard_cap,
                "created_by": created_by,
            }
        )
        .execute()
    )

    row = insert_result.data[0]
    mtd = _compute_mtd_spend(db, org.org_id, row["scope_type"], row.get("scope_value"))
    log.info("budget_created", org_id=org.org_id, budget_id=row["id"], scope_type=row["scope_type"])
    return _to_budget_read(row, mtd)


@router.patch("/{budget_id}", response_model=BudgetRead)
def update_budget(budget_id: str, body: BudgetUpdate, org: OrgDep) -> BudgetRead:
    db = _get_supabase()

    existing = (
        db.table("budgets")
        .select("id")
        .eq("id", budget_id)
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Budget not found")

    patch: dict[str, Any] = {}
    if body.monthly_limit is not None:
        patch["monthly_limit"] = str(body.monthly_limit)
    if body.alert_at_pct is not None:
        patch["alert_at_pct"] = body.alert_at_pct

    if not patch:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )

    updated = (
        db.table("budgets").update(patch).eq("id", budget_id).eq("org_id", org.org_id).execute()
    )

    if not updated.data:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Update failed"
        )

    row = updated.data[0]
    mtd = _compute_mtd_spend(db, org.org_id, row["scope_type"], row.get("scope_value"))
    log.info("budget_updated", org_id=org.org_id, budget_id=budget_id)
    return _to_budget_read(row, mtd)


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: str, org: OrgDep) -> None:
    db = _get_supabase()

    existing = (
        db.table("budgets")
        .select("id")
        .eq("id", budget_id)
        .eq("org_id", org.org_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Budget not found")

    db.table("budgets").delete().eq("id", budget_id).eq("org_id", org.org_id).execute()
    log.info("budget_deleted", org_id=org.org_id, budget_id=budget_id)
