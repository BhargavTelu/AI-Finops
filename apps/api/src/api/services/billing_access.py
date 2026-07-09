"""
Single source of truth for "does this org have access right now?".

Pure function over pre-fetched rows - used by the gating dependency
(deps._require_active_org), GET /billing, and tests. Keeping the rule in one
place means the web paywall and the API 402 can never disagree.

Rule: an org has access while its Stripe subscription is active/trialing,
OR while the built-in 14-day trial (organizations.trial_ends_at) is running.
Everything else is blocked.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Stripe subscription statuses that grant access. 'past_due' is deliberately
# excluded: Stripe retries cards for ~2 weeks before cancelling, and a
# past-due org seeing the paywall is the nudge that fixes the card.
_ACTIVE_STATUSES = frozenset({"active", "trialing"})


@dataclass(frozen=True)
class AccessState:
    plan: str
    status: str
    has_subscription: bool
    current_period_end: str | None
    trial_ends_at: str | None
    trial_days_left: int | None
    access_blocked: bool


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def filter_accessible_org_ids(db: Any, org_ids: list[str]) -> set[str]:
    """
    Bulk version of the access rule for worker fan-outs: outbound email
    (weekly digests, monthly report mails) must not keep landing in the
    inboxes of orgs whose trial lapsed months ago. Two queries total,
    regardless of org count.
    """
    if not org_ids:
        return set()

    org_rows = (
        db.table("organizations").select("id, trial_ends_at").in_("id", org_ids).execute()
    ).data
    billing_rows = (
        db.table("billing")
        .select("org_id, status, stripe_subscription_id, plan, current_period_end")
        .in_("org_id", org_ids)
        .execute()
    ).data
    billing_by_org = {row["org_id"]: row for row in billing_rows}

    now = datetime.now(UTC)
    return {
        row["id"]
        for row in org_rows
        if not evaluate_access(row, billing_by_org.get(row["id"]), now=now).access_blocked
    }


def evaluate_access(
    org_row: dict[str, Any] | None,
    billing_row: dict[str, Any] | None,
    now: datetime | None = None,
) -> AccessState:
    now = now or datetime.now(UTC)

    sub_status = (billing_row or {}).get("status") or ""
    sub_id = (billing_row or {}).get("stripe_subscription_id")
    has_subscription = bool(sub_id)
    trial_ends_at = (org_row or {}).get("trial_ends_at")
    trial_end = _parse_ts(trial_ends_at)

    if has_subscription and sub_status in _ACTIVE_STATUSES:
        return AccessState(
            plan=(billing_row or {}).get("plan") or "starter",
            status=sub_status,
            has_subscription=True,
            current_period_end=(billing_row or {}).get("current_period_end"),
            trial_ends_at=trial_ends_at,
            trial_days_left=None,
            access_blocked=False,
        )

    # No (active) subscription - fall back to the built-in trial window.
    if trial_end is not None and trial_end > now:
        trial_active = True
        days_left: int | None = max((trial_end - now).days, 0)
    else:
        trial_active = False
        days_left = None
    return AccessState(
        plan="trial",
        status="trialing" if trial_active else (sub_status or "expired"),
        has_subscription=has_subscription,
        current_period_end=(billing_row or {}).get("current_period_end"),
        trial_ends_at=trial_ends_at,
        trial_days_left=days_left,
        access_blocked=not trial_active,
    )
