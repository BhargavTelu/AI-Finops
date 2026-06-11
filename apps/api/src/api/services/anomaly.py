"""
Anomaly detection - statistical, not ML.
Algorithm from architecture.md § Anomaly Algorithm.

Explainable to a CFO, runs in milliseconds, sufficient for < 50 customers.
"""

import statistics
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass
class AnomalyResult:
    scope_kind: str
    scope_value: str | None
    baseline_usd: Decimal
    actual_usd: Decimal
    spike_pct: int
    severity: Literal["low", "medium", "high"]


# A near-flat baseline has σ≈0. Clipping only to a tiny absolute floor (the old
# `or 0.01`) made a $0.50 increase on $100/day spend score z=50 and fire a
# high-severity alert. Treat day-to-day noise as at least this fraction of the
# mean so the z-score stays meaningful on stable spend.
_MIN_REL_STDEV = 0.05  # 5% of the mean
_ABS_STDEV_FLOOR = 0.01  # keeps z finite when the mean is ~0

# Require a minimum absolute jump on top of the z-score, so a few dollars on a
# small-but-above-$10 baseline can't trip an alert on its own.
_MIN_ABS_DELTA_USD = 5.0


def detect_anomalies(
    history: list[Decimal],  # daily costs, oldest first, len >= 15
) -> AnomalyResult | None:
    """
    Rolling mean + 2σ over the previous 7 days.
    Returns None if data is insufficient or spend is below the $10 floor.

    Args:
        history: At least 15 daily cost values (oldest → newest).
                 The last element is "today"; [−8:−1] is the rolling window.
    """
    if len(history) < 15:
        return None

    rolling = [float(v) for v in history[-8:-1]]
    actual = float(history[-1])

    if actual < 10.0:
        return None

    mean = statistics.mean(rolling)
    # Floor σ at both an absolute value and a fraction of the mean. The
    # relative floor is what stops flat baselines from inflating z.
    stdev = max(statistics.pstdev(rolling), mean * _MIN_REL_STDEV, _ABS_STDEV_FLOOR)
    z = (actual - mean) / stdev

    if z < 2.0:
        return None

    # Suppress trivially small absolute increases even when z clears the bar.
    if (actual - mean) < _MIN_ABS_DELTA_USD:
        return None

    severity: Literal["low", "medium", "high"] = (
        "high" if z >= 4 else "medium" if z >= 3 else "low"
    )

    spike_pct = int((actual - mean) / mean * 100) if mean > 0 else 0

    return AnomalyResult(
        scope_kind="",  # caller fills in scope
        scope_value=None,
        baseline_usd=Decimal(str(round(mean, 6))),
        actual_usd=Decimal(str(round(actual, 6))),
        spike_pct=spike_pct,
        severity=severity,
    )
