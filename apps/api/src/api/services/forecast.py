"""
Month-end spend forecast (FR-24) - least-squares linear regression.

Pure functions, no DB access. Statistics before ML (CLAUDE.md soft rule):
a linear fit over the current month's daily totals is explainable to a CFO,
runs in microseconds, and is sufficient at this scale.

Fallback: with fewer than 5 complete days this month, a regression is noise -
use the trailing-30-day average instead.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
import statistics

_CENTS = Decimal("0.01")
_MIN_DAYS_FOR_REGRESSION = 5


@dataclass(frozen=True)
class Forecast:
    projected_month_end_usd: Decimal
    confidence_low: Decimal
    confidence_high: Decimal
    method: str  # "linear_regression" | "trailing_30d_average"


def _quantize(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _linear_fit(values: list[float]) -> tuple[float, float]:
    """Least-squares fit over (index, value). Returns (slope, intercept)."""
    n = len(values)
    xs = range(n)
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0, mean_y
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=True)) / denom
    return slope, mean_y - slope * mean_x


def forecast_month_end(
    mtd_daily: list[Decimal],
    trailing_daily: list[Decimal],
    days_in_month: int,
) -> Forecast | None:
    """
    mtd_daily: one entry per complete day this month (1st -> yesterday),
               gaps already filled with 0 by the caller.
    trailing_daily: last-30-complete-days totals, used for the early-month
               fallback. May be empty.
    Returns None when there is no data to forecast from.
    """
    actual_total = sum(mtd_daily, Decimal("0"))
    remaining_days = days_in_month - len(mtd_daily)

    if remaining_days <= 0:
        # Month is complete - the forecast IS the actual.
        total = _quantize(actual_total)
        return Forecast(total, total, total, method="linear_regression")

    if len(mtd_daily) >= _MIN_DAYS_FOR_REGRESSION:
        values = [float(v) for v in mtd_daily]
        slope, intercept = _linear_fit(values)
        # Per-day predictions clamped at zero - spend cannot be negative.
        predictions = [
            max(slope * x + intercept, 0.0)
            for x in range(len(values), days_in_month)
        ]
        projected = float(actual_total) + sum(predictions)

        fitted = [slope * x + intercept for x in range(len(values))]
        residuals = [y - f for y, f in zip(values, fitted, strict=True)]
        residual_std = statistics.pstdev(residuals) if len(residuals) > 1 else 0.0
        band = residual_std * (remaining_days**0.5)
        method = "linear_regression"
    else:
        source = trailing_daily or mtd_daily
        if not source:
            return None
        daily = [float(v) for v in source]
        mean_daily = statistics.mean(daily)
        projected = float(actual_total) + mean_daily * remaining_days
        daily_std = statistics.pstdev(daily) if len(daily) > 1 else 0.0
        band = daily_std * (remaining_days**0.5)
        method = "trailing_30d_average"

    # The low bound can never drop below what is already spent.
    low = max(projected - band, float(actual_total))
    return Forecast(
        projected_month_end_usd=_quantize(projected),
        confidence_low=_quantize(low),
        confidence_high=_quantize(projected + band),
        method=method,
    )
