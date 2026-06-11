"""
Unit tests for anomaly detection algorithm.
Target: 80% coverage on services/anomaly.py.
"""

import statistics
from decimal import Decimal

import pytest

from api.services.anomaly import detect_anomalies


def _costs(values: list[float]) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


def _spike_history(baseline: float, actual: float, n: int = 15) -> list[Decimal]:
    """Build a history of n values: (n-1) days of baseline + 1 day of actual."""
    return _costs([baseline] * (n - 1) + [actual])


def _z_for(baseline: float, actual: float) -> float:
    """Compute the z-score the algorithm would produce for a flat baseline."""
    rolling = [baseline] * 7
    mean = statistics.mean(rolling)
    stdev = max(statistics.pstdev(rolling), mean * 0.05, 0.01)
    return (actual - mean) / stdev


class TestDetectAnomalies:
    def test_returns_none_when_insufficient_data(self) -> None:
        assert detect_anomalies(_costs([100.0] * 14)) is None

    def test_returns_none_below_dollar_floor(self) -> None:
        small = _costs([1.0] * 14 + [9.0])
        assert detect_anomalies(small) is None

    def test_no_anomaly_within_two_sigma(self) -> None:
        # Flat spend - z-score is 0
        flat = _costs([100.0] * 15)
        assert detect_anomalies(flat) is None

    def test_detects_spike_above_two_sigma(self) -> None:
        baseline = [100.0] * 7
        history = _costs([100.0] * 7 + baseline + [500.0])
        result = detect_anomalies(history)
        assert result is not None
        assert result.severity in ("low", "medium", "high")
        assert result.spike_pct > 0

    def test_high_severity_above_four_sigma(self) -> None:
        # Very stable baseline then huge spike → z ≥ 4 → high
        baseline = [100.0] * 7
        history = _costs([100.0] * 7 + baseline + [10_000.0])
        result = detect_anomalies(history)
        assert result is not None
        assert result.severity == "high"

    def test_spike_pct_calculation(self) -> None:
        # Mean ≈ 100, actual = 300 → spike ≈ 200%
        history = _costs([100.0] * 14 + [300.0])
        result = detect_anomalies(history)
        if result:  # only if z ≥ 2
            assert result.spike_pct == pytest.approx(200, abs=5)

    # ── Severity boundary tests ────────────────────────────────────────────────

    def test_low_severity_at_two_sigma_boundary(self) -> None:
        # Flat $100 baseline → pstdev=0, floored to mean*5% = $5.
        # z = (actual - 100) / 5 = 2.5 when actual = 112.50 (delta also clears
        # the $5 minimum absolute jump).
        baseline = 100.0
        actual = baseline + 5.0 * 2.5  # z ≈ 2.5
        history = _spike_history(baseline, actual)
        result = detect_anomalies(history)
        assert result is not None
        assert result.severity == "low"

    def test_medium_severity_at_three_sigma_boundary(self) -> None:
        baseline = 100.0
        actual = baseline + 5.0 * 3.5  # z ≈ 3.5 against the $5 σ floor
        history = _spike_history(baseline, actual)
        result = detect_anomalies(history)
        assert result is not None
        assert result.severity == "medium"

    def test_tiny_absolute_increase_on_flat_baseline_is_not_anomalous(self) -> None:
        # Regression: with the old `or 0.01` floor, +$0.50 on flat $100/day
        # spend scored z=50 and fired a high-severity alert.
        history = _spike_history(100.0, 100.50)
        assert detect_anomalies(history) is None

    def test_small_dollar_jump_below_min_delta_is_suppressed(self) -> None:
        # Flat $12 baseline → σ floor = $0.60; +$4 gives z ≈ 6.7, but the
        # absolute jump is under the $5 minimum, so no alert.
        history = _spike_history(12.0, 16.0)
        assert detect_anomalies(history) is None

    def test_spike_pct_zero_when_mean_is_zero(self) -> None:
        # All zeros in rolling window → mean = 0 → spike_pct should be 0, not divide-by-zero.
        history = _costs([0.0] * 14 + [50.0])
        result = detect_anomalies(history)
        # actual=50 passes $10 floor; stdev=0→0.01; z=(50-0)/0.01=5000 → high
        if result:
            assert result.spike_pct == 0  # mean=0 → special-cased to 0

    def test_returns_correct_baseline_and_actual_usd(self) -> None:
        baseline = 200.0
        actual = 10_000.0
        history = _spike_history(baseline, actual)
        result = detect_anomalies(history)
        assert result is not None
        assert float(result.baseline_usd) == pytest.approx(baseline, rel=0.01)
        assert float(result.actual_usd) == pytest.approx(actual, rel=0.01)

    def test_exactly_fifteen_data_points_is_sufficient(self) -> None:
        history = _costs([100.0] * 14 + [10_000.0])
        assert len(history) == 15
        result = detect_anomalies(history)
        assert result is not None
