"""
Anomaly detection — statistical, not ML.
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
    stdev = statistics.pstdev(rolling) or 0.01
    z = (actual - mean) / stdev

    if z < 2.0:
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
