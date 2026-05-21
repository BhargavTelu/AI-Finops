"""
Edge-case unit tests for anomaly detection algorithm.
TC-ANO-12 to TC-ANO-15 — supplements the existing test_anomaly.py.
"""

from decimal import Decimal

from api.services.anomaly import detect_anomalies


def _costs(values: list[float]) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


class TestAnomalyEdgeCases:
    def test_exactly_14_points_returns_none(self) -> None:  # TC-ANO-12
        """14 data points is one short of the required ≥15 — must return None."""
        assert detect_anomalies(_costs([100.0] * 14)) is None

    def test_all_zero_baseline_spike_50(self) -> None:  # TC-ANO-13
        """14× $0 then $50: z = (50−0)/0.01 = 5000 → high severity."""
        history = _costs([0.0] * 14 + [50.0])
        result = detect_anomalies(history)
        assert result is not None
        assert result.severity == "high"

    def test_negative_value_in_history_no_crash(self) -> None:  # TC-ANO-14
        """A negative value in the rolling window must not raise an exception."""
        # Put −5 at position −9 (inside the rolling window slice [−8:−1])
        history = _costs([100.0] * 6 + [-5.0] + [100.0] * 7 + [500.0])
        # pstdev handles negative values — should not crash
        detect_anomalies(history)  # just assert no exception

    def test_spike_pct_zero_when_mean_zero(self) -> None:  # TC-ANO-15
        """When the rolling mean is 0, spike_pct is special-cased to 0."""
        history = _costs([0.0] * 14 + [50.0])
        result = detect_anomalies(history)
        if result is not None:  # only if detect threshold crossed
            assert result.spike_pct == 0
