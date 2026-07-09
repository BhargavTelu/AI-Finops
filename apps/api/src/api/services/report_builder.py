"""
Assemble the data for a monthly CFO report from pre-fetched DB rows.

Pure functions - no DB access, no I/O. The Celery task in workers/reports.py
fetches the rows; this module only does the arithmetic, so every number that
lands in front of a CFO is unit-testable in isolation.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


@dataclass(frozen=True)
class SpendLine:
    label: str
    cost_usd: Decimal
    requests: int
    pct_of_total: float


@dataclass(frozen=True)
class AnomalyLine:
    detected_on: str
    scope_value: str
    baseline_usd: Decimal
    actual_usd: Decimal
    spike_pct: int
    severity: str


@dataclass(frozen=True)
class MonthlyReportData:
    org_name: str
    period_start: date
    period_end: date
    generated_on: date
    is_partial: bool
    total_cost_usd: Decimal
    total_requests: int
    total_tokens: int
    prev_month_cost_usd: Decimal | None
    mom_delta_pct: float | None
    projected_month_cost_usd: Decimal
    by_provider: list[SpendLine]
    top_models: list[SpendLine]
    by_feature: list[SpendLine]
    by_team: list[SpendLine]
    by_customer: list[SpendLine]
    anomaly_count: int
    top_anomalies: list[AnomalyLine]
    applied_recs_count: int
    applied_savings_usd: Decimal


_CENTS = Decimal("0.01")
_UNTAGGED = "(untagged)"
_TOP_N = 10


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value or "0"))


def _group_spend(rows: list[dict[str, Any]], key: str, total: Decimal) -> list[SpendLine]:
    """Group summary rows by a column, sorted by cost desc, top N + pct of total."""
    costs: dict[str, Decimal] = {}
    requests: dict[str, int] = {}
    for row in rows:
        label = row.get(key) or _UNTAGGED
        costs[label] = costs.get(label, Decimal("0")) + _to_decimal(row.get("total_cost_usd"))
        requests[label] = requests.get(label, 0) + int(row.get("total_requests") or 0)

    lines = [
        SpendLine(
            label=label,
            cost_usd=cost.quantize(_CENTS, rounding=ROUND_HALF_UP),
            requests=requests[label],
            pct_of_total=float(cost / total * 100) if total else 0.0,
        )
        for label, cost in costs.items()
    ]
    lines.sort(key=lambda line: line.cost_usd, reverse=True)
    return lines[:_TOP_N]


def _project_month_total(total: Decimal, period_start: date, period_end: date) -> Decimal:
    """
    Flat extrapolation to month end (Phase 3 replaces this with the linear
    regression forecast). A complete month projects to itself.
    """
    days_in_month = calendar.monthrange(period_start.year, period_start.month)[1]
    days_elapsed = (period_end - period_start).days + 1
    if days_elapsed <= 0:
        return Decimal("0.00")
    if days_elapsed >= days_in_month:
        return total.quantize(_CENTS, rounding=ROUND_HALF_UP)
    projected = total / Decimal(days_elapsed) * Decimal(days_in_month)
    return projected.quantize(_CENTS, rounding=ROUND_HALF_UP)


def build_report_data(
    *,
    org_name: str,
    period_start: date,
    period_end: date,
    generated_on: date,
    current_rows: list[dict[str, Any]],
    prev_month_rows: list[dict[str, Any]],
    anomaly_rows: list[dict[str, Any]],
    applied_rec_rows: list[dict[str, Any]],
) -> MonthlyReportData:
    """
    current_rows / prev_month_rows: daily_cost_summaries dicts.
    anomaly_rows: anomalies detected within the period.
    applied_rec_rows: recommendations with status=applied resolved in the period.
    """
    total = sum((_to_decimal(r.get("total_cost_usd")) for r in current_rows), Decimal("0"))
    total_requests = sum(int(r.get("total_requests") or 0) for r in current_rows)
    total_tokens = sum(int(r.get("total_tokens") or 0) for r in current_rows)

    prev_total = sum((_to_decimal(r.get("total_cost_usd")) for r in prev_month_rows), Decimal("0"))
    has_prev = bool(prev_month_rows) and prev_total > 0
    mom_delta_pct = float((total - prev_total) / prev_total * 100) if has_prev else None

    last_day = calendar.monthrange(period_start.year, period_start.month)[1]
    is_partial = period_end < period_start.replace(day=last_day)

    top_anomalies = [
        AnomalyLine(
            detected_on=str(row.get("detected_at") or "")[:10],
            scope_value=str(row.get("scope_value") or "unknown"),
            baseline_usd=_to_decimal(row.get("baseline_usd")).quantize(_CENTS),
            actual_usd=_to_decimal(row.get("actual_usd")).quantize(_CENTS),
            spike_pct=int(row.get("spike_pct") or 0),
            severity=str(row.get("severity") or "low"),
        )
        for row in sorted(anomaly_rows, key=lambda r: int(r.get("spike_pct") or 0), reverse=True)[
            :3
        ]
    ]

    applied_savings = sum(
        (_to_decimal(r.get("projected_savings_usd")) for r in applied_rec_rows), Decimal("0")
    )

    return MonthlyReportData(
        org_name=org_name,
        period_start=period_start,
        period_end=period_end,
        generated_on=generated_on,
        is_partial=is_partial,
        total_cost_usd=total.quantize(_CENTS, rounding=ROUND_HALF_UP),
        total_requests=total_requests,
        total_tokens=total_tokens,
        prev_month_cost_usd=(
            prev_total.quantize(_CENTS, rounding=ROUND_HALF_UP) if has_prev else None
        ),
        mom_delta_pct=mom_delta_pct,
        projected_month_cost_usd=_project_month_total(total, period_start, period_end),
        by_provider=_group_spend(current_rows, "provider", total),
        top_models=_group_spend(current_rows, "model", total),
        by_feature=_group_spend(current_rows, "feature_tag", total),
        by_team=_group_spend(current_rows, "team_tag", total),
        by_customer=_group_spend(current_rows, "customer_tag", total),
        anomaly_count=len(anomaly_rows),
        top_anomalies=top_anomalies,
        applied_recs_count=len(applied_rec_rows),
        applied_savings_usd=applied_savings.quantize(_CENTS, rounding=ROUND_HALF_UP),
    )
