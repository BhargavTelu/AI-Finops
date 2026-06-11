"""
Unit tests for services/forecast.py - CFO-facing regression math.
Pure functions, no mocks.
"""

from decimal import Decimal

from api.services.forecast import forecast_month_end


def _d(values: list[float]) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


class TestLinearRegression:
    def test_flat_spend_projects_flat(self) -> None:
        # $10/day for 10 days of a 30-day month -> $300 +/- 0.
        result = forecast_month_end(_d([10.0] * 10), [], 30)
        assert result is not None
        assert result.method == "linear_regression"
        assert result.projected_month_end_usd == Decimal("300.00")
        assert result.confidence_low == Decimal("300.00")
        assert result.confidence_high == Decimal("300.00")

    def test_increasing_trend_extrapolates(self) -> None:
        # $1, $2, ... $10 over 10 days; slope=1 -> days 11..30 predict 11..30.
        # Total = 55 (actual) + sum(11..30) = 55 + 410 = 465.
        result = forecast_month_end(_d([float(i) for i in range(1, 11)]), [], 30)
        assert result is not None
        assert result.projected_month_end_usd == Decimal("465.00")

    def test_decreasing_trend_clamps_at_zero(self) -> None:
        # Steep decline: predictions go negative without clamping.
        result = forecast_month_end(_d([100, 80, 60, 40, 20]), [], 30)
        assert result is not None
        # Actual spent = 300; projections clamp at 0, never subtract.
        assert result.projected_month_end_usd >= Decimal("300.00")

    def test_low_bound_never_below_actual_spend(self) -> None:
        result = forecast_month_end(_d([50, 10, 90, 20, 80, 15]), [], 30)
        assert result is not None
        actual = Decimal("265")  # sum of the series
        assert result.confidence_low >= actual

    def test_band_ordering(self) -> None:
        result = forecast_month_end(_d([5, 9, 4, 12, 7, 11]), [], 30)
        assert result is not None
        assert result.confidence_low <= result.projected_month_end_usd
        assert result.projected_month_end_usd <= result.confidence_high

    def test_complete_month_returns_actual(self) -> None:
        result = forecast_month_end(_d([10.0] * 30), [], 30)
        assert result is not None
        assert result.projected_month_end_usd == Decimal("300.00")
        assert result.confidence_low == result.confidence_high == Decimal("300.00")


class TestTrailingFallback:
    def test_under_five_days_uses_trailing_average(self) -> None:
        # 2 days MTD at $50; trailing 30d at $10/day -> 50*2 + 10*28 = 380.
        result = forecast_month_end(_d([50, 50]), _d([10.0] * 30), 30)
        assert result is not None
        assert result.method == "trailing_30d_average"
        assert result.projected_month_end_usd == Decimal("380.00")

    def test_no_trailing_falls_back_to_mtd_mean(self) -> None:
        # 2 days at $20, no trailing history -> 40 + 20*28 = 600.
        result = forecast_month_end(_d([20, 20]), [], 30)
        assert result is not None
        assert result.method == "trailing_30d_average"
        assert result.projected_month_end_usd == Decimal("600.00")

    def test_first_of_month_uses_trailing_only(self) -> None:
        # Zero complete days this month - project entirely from trailing.
        result = forecast_month_end([], _d([10.0] * 30), 31)
        assert result is not None
        assert result.projected_month_end_usd == Decimal("310.00")

    def test_no_data_at_all_returns_none(self) -> None:
        assert forecast_month_end([], [], 30) is None
