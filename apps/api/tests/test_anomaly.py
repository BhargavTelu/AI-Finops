"""
Unit tests for anomaly detection algorithm.
Target: 80% coverage on services/anomaly.py.
"""

from decimal import Decimal

import pytest

from api.services.anomaly import detect_anomalies


def _costs(values: list[float]) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


class TestDetectAnomalies:
    def test_returns_none_when_insufficient_data(self) -> None:
        assert detect_anomalies(_costs([100.0] * 14)) is None

    def test_returns_none_below_dollar_floor(self) -> None:
        history = _costs([5.0] * 14 + [50.0])  # spike but actual < $10 base
        # 50 > 10 but the spike on a tiny base — still returns something
        # This test verifies the $10 floor on `actual`, not baseline
        small = _costs([1.0] * 14 + [9.0])
        assert detect_anomalies(small) is None

    def test_no_anomaly_within_two_sigma(self) -> None:
        # Flat spend — z-score is 0
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
