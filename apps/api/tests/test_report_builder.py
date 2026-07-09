"""
Unit tests for services/report_builder.py - CFO-facing arithmetic.
Pure functions, no mocks needed.
"""

from datetime import date
from decimal import Decimal

from api.services.report_builder import build_report_data

MAY_START = date(2026, 5, 1)
MAY_END = date(2026, 5, 31)
GENERATED = date(2026, 6, 1)


def _row(
    cost: str = "100.00",
    requests: int = 10,
    tokens: int = 1000,
    provider: str = "openai",
    model: str = "gpt-4o",
    feature: str | None = "chat",
    team: str | None = "core",
    customer: str | None = "acme",
) -> dict:
    return {
        "total_cost_usd": cost,
        "total_requests": requests,
        "total_tokens": tokens,
        "provider": provider,
        "model": model,
        "feature_tag": feature,
        "team_tag": team,
        "customer_tag": customer,
    }


def _build(**overrides):
    defaults = {
        "org_name": "Acme",
        "period_start": MAY_START,
        "period_end": MAY_END,
        "generated_on": GENERATED,
        "current_rows": [_row()],
        "prev_month_rows": [],
        "anomaly_rows": [],
        "applied_rec_rows": [],
    }
    defaults.update(overrides)
    return build_report_data(**defaults)


class TestTotals:
    def test_sums_cost_requests_tokens(self) -> None:
        data = _build(current_rows=[_row("10.50", 5, 100), _row("4.50", 3, 200)])
        assert data.total_cost_usd == Decimal("15.00")
        assert data.total_requests == 8
        assert data.total_tokens == 300

    def test_handles_null_fields(self) -> None:
        data = _build(current_rows=[{"total_cost_usd": None, "provider": "openai"}])
        assert data.total_cost_usd == Decimal("0.00")
        assert data.total_requests == 0


class TestMoM:
    def test_mom_delta_positive(self) -> None:
        data = _build(
            current_rows=[_row("120.00")],
            prev_month_rows=[_row("100.00")],
        )
        assert data.prev_month_cost_usd == Decimal("100.00")
        assert data.mom_delta_pct is not None
        assert abs(data.mom_delta_pct - 20.0) < 0.001

    def test_mom_delta_negative(self) -> None:
        data = _build(current_rows=[_row("50.00")], prev_month_rows=[_row("100.00")])
        assert data.mom_delta_pct is not None
        assert abs(data.mom_delta_pct + 50.0) < 0.001

    def test_no_prev_month_yields_none(self) -> None:
        data = _build(prev_month_rows=[])
        assert data.mom_delta_pct is None
        assert data.prev_month_cost_usd is None

    def test_zero_prev_month_yields_none(self) -> None:
        # Avoids division by zero AND a misleading "+inf%" headline.
        data = _build(prev_month_rows=[_row("0.00")])
        assert data.mom_delta_pct is None


class TestGrouping:
    def test_groups_by_provider_sorted_desc(self) -> None:
        data = _build(
            current_rows=[
                _row("10.00", provider="anthropic"),
                _row("90.00", provider="openai"),
            ]
        )
        assert [line.label for line in data.by_provider] == ["openai", "anthropic"]
        assert data.by_provider[0].pct_of_total == 90.0

    def test_untagged_bucket(self) -> None:
        data = _build(current_rows=[_row(feature=None), _row(feature="")])
        assert len(data.by_feature) == 1
        assert data.by_feature[0].label == "(untagged)"

    def test_top_models_capped_at_ten(self) -> None:
        rows = [_row("1.00", model=f"model-{i}") for i in range(15)]
        data = _build(current_rows=rows)
        assert len(data.top_models) == 10

    def test_pct_of_total_sums_to_100(self) -> None:
        data = _build(
            current_rows=[_row("33.33"), _row("33.33", model="b"), _row("33.34", model="c")]
        )
        assert abs(sum(line.pct_of_total for line in data.top_models) - 100.0) < 0.01


class TestProjection:
    def test_complete_month_projects_to_itself(self) -> None:
        data = _build(current_rows=[_row("310.00")])
        assert data.is_partial is False
        assert data.projected_month_cost_usd == Decimal("310.00")

    def test_partial_month_extrapolates_flat(self) -> None:
        # 10 days elapsed of a 31-day month at $100 total -> $310 projected
        data = _build(period_end=date(2026, 5, 10), current_rows=[_row("100.00")])
        assert data.is_partial is True
        assert data.projected_month_cost_usd == Decimal("310.00")

    def test_single_day_partial(self) -> None:
        data = _build(period_end=MAY_START, current_rows=[_row("10.00")])
        assert data.projected_month_cost_usd == Decimal("310.00")


class TestAnomalies:
    def test_top_three_by_spike_pct(self) -> None:
        anomalies = [
            {
                "detected_at": "2026-05-01",
                "scope_value": f"m{i}",
                "baseline_usd": "10",
                "actual_usd": "50",
                "spike_pct": pct,
                "severity": "low",
            }
            for i, pct in enumerate([150, 400, 250, 300])
        ]
        data = _build(anomaly_rows=anomalies)
        assert data.anomaly_count == 4
        assert [a.spike_pct for a in data.top_anomalies] == [400, 300, 250]

    def test_detected_on_truncated_to_date(self) -> None:
        data = _build(
            anomaly_rows=[
                {
                    "detected_at": "2026-05-14T01:00:00+00:00",
                    "scope_value": "gpt-4o",
                    "baseline_usd": "1",
                    "actual_usd": "5",
                    "spike_pct": 400,
                    "severity": "high",
                }
            ]
        )
        assert data.top_anomalies[0].detected_on == "2026-05-14"


class TestAppliedSavings:
    def test_sums_applied_recommendation_savings(self) -> None:
        data = _build(
            applied_rec_rows=[
                {"projected_savings_usd": "100.50"},
                {"projected_savings_usd": "49.50"},
            ]
        )
        assert data.applied_recs_count == 2
        assert data.applied_savings_usd == Decimal("150.00")

    def test_no_applied_recs(self) -> None:
        data = _build()
        assert data.applied_recs_count == 0
        assert data.applied_savings_usd == Decimal("0.00")
