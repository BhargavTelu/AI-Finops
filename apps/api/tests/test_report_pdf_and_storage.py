"""
Unit tests for services/report_pdf.py (renders valid PDF bytes) and
services/storage.py (SigV4 request shape; httpx mocked, no network).
"""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from api.services import storage
from api.services.report_builder import build_report_data
from api.services.report_pdf import render_pdf

FROZEN_NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


def _data(current_rows: list[dict] | None = None):
    rows = current_rows if current_rows is not None else [
        {"total_cost_usd": "100.00", "total_requests": 10, "total_tokens": 1000,
         "provider": "openai", "model": "gpt-4o", "feature_tag": "chat",
         "team_tag": "core", "customer_tag": "acme"}
    ]
    return build_report_data(
        org_name="Acme",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        generated_on=date(2026, 6, 1),
        current_rows=rows,
        prev_month_rows=[],
        anomaly_rows=[],
        applied_rec_rows=[],
    )


class TestRenderPdf:
    def test_returns_valid_pdf_bytes(self) -> None:
        pdf = render_pdf(_data())
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000

    def test_renders_with_empty_sections(self) -> None:
        # An org with one summary row, no tags, no anomalies, no recs must
        # still produce a valid document (empty-state strings per section).
        pdf = render_pdf(
            _data([{"total_cost_usd": "5.00", "total_requests": 1, "total_tokens": 10,
                    "provider": "openai", "model": "gpt-4o", "feature_tag": None,
                    "team_tag": None, "customer_tag": None}])
        )
        assert pdf.startswith(b"%PDF")

    def test_latin1_safe_org_name(self) -> None:
        data = build_report_data(
            org_name="Café Müller",  # latin-1 representable - must not raise
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            generated_on=date(2026, 6, 1),
            current_rows=[{"total_cost_usd": "1.00", "provider": "openai", "model": "m"}],
            prev_month_rows=[],
            anomaly_rows=[],
            applied_rec_rows=[],
        )
        assert render_pdf(data).startswith(b"%PDF")


@pytest.fixture(autouse=True)
def _r2_settings():
    with (
        patch.object(storage.settings, "r2_account_id", "acct123"),
        patch.object(storage.settings, "r2_bucket_name", "spendops-reports"),
        patch.object(storage.settings, "r2_access_key_id", "AKIAEXAMPLE"),
        patch.object(storage.settings, "r2_secret_access_key", "secretexample"),
    ):
        yield


class TestIsConfigured:
    def test_configured(self) -> None:
        assert storage.is_configured() is True

    def test_not_configured_when_account_missing(self) -> None:
        with patch.object(storage.settings, "r2_account_id", ""):
            assert storage.is_configured() is False


class TestUploadPdf:
    def test_puts_to_bucket_url_with_sigv4_header(self) -> None:
        resp = MagicMock(status_code=200)
        with patch("api.services.storage.httpx.put", return_value=resp) as mock_put:
            storage.upload_pdf("reports/org1/2026-05-01.pdf", b"%PDF-fake", now=FROZEN_NOW)

        url = mock_put.call_args.args[0]
        headers = mock_put.call_args.kwargs["headers"]
        assert url == (
            "https://acct123.r2.cloudflarestorage.com"
            "/spendops-reports/reports/org1/2026-05-01.pdf"
        )
        assert headers["Authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE/20260611/auto/s3/aws4_request"
        )
        assert "Signature=" in headers["Authorization"]
        assert headers["x-amz-date"] == "20260611T120000Z"
        assert mock_put.call_args.kwargs["content"] == b"%PDF-fake"

    def test_signature_is_deterministic(self) -> None:
        resp = MagicMock(status_code=200)
        sigs = []
        for _ in range(2):
            with patch("api.services.storage.httpx.put", return_value=resp) as mock_put:
                storage.upload_pdf("k.pdf", b"body", now=FROZEN_NOW)
            sigs.append(mock_put.call_args.kwargs["headers"]["Authorization"])
        assert sigs[0] == sigs[1]

    def test_non_2xx_raises_value_error(self) -> None:
        resp = MagicMock(status_code=403)
        with patch("api.services.storage.httpx.put", return_value=resp):
            with pytest.raises(ValueError, match="403"):
                storage.upload_pdf("k.pdf", b"body", now=FROZEN_NOW)

    def test_network_error_raises_value_error(self) -> None:
        import httpx

        with patch(
            "api.services.storage.httpx.put",
            side_effect=httpx.ConnectError("refused"),
        ):
            with pytest.raises(ValueError, match="network error"):
                storage.upload_pdf("k.pdf", b"body", now=FROZEN_NOW)


class TestPresignDownload:
    def test_url_shape_and_query_params(self) -> None:
        url = storage.presign_download(
            "reports/org1/2026-05-01.pdf", expires_seconds=600, now=FROZEN_NOW
        )
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert parsed.scheme == "https"
        assert parsed.netloc == "acct123.r2.cloudflarestorage.com"
        assert parsed.path == "/spendops-reports/reports/org1/2026-05-01.pdf"
        assert params["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
        assert params["X-Amz-Credential"] == ["AKIAEXAMPLE/20260611/auto/s3/aws4_request"]
        assert params["X-Amz-Date"] == ["20260611T120000Z"]
        assert params["X-Amz-Expires"] == ["600"]
        assert params["X-Amz-SignedHeaders"] == ["host"]
        assert len(params["X-Amz-Signature"][0]) == 64  # hex SHA-256

    def test_presign_is_deterministic_for_same_instant(self) -> None:
        a = storage.presign_download("k.pdf", now=FROZEN_NOW)
        b = storage.presign_download("k.pdf", now=FROZEN_NOW)
        assert a == b

    def test_different_keys_different_signatures(self) -> None:
        a = storage.presign_download("a.pdf", now=FROZEN_NOW)
        b = storage.presign_download("b.pdf", now=FROZEN_NOW)
        assert a.split("X-Amz-Signature=")[1] != b.split("X-Amz-Signature=")[1]
