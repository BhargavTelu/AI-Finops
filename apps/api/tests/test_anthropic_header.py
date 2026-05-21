"""
Test that AnthropicAdapter._headers() includes the required Anthropic beta header.
TC-ANT-11 / BUG-01.

BUG-01 (Critical): _headers() missing "anthropic-beta: usage-report-2024-07-01"
which is required by the Anthropic usage-report API.
"""

from api.adapters.anthropic import AnthropicAdapter


class TestAnthropicHeaders:
    def test_headers_include_anthropic_beta(self) -> None:  # TC-ANT-11 / TC-BUG-01
        adapter = AnthropicAdapter()
        headers = adapter._headers(b"sk-ant-test-key")
        assert "anthropic-beta" in headers, (
            "BUG-01: _headers() is missing 'anthropic-beta' key. "
            "Anthropic usage-report API requires this header."
        )
        assert headers["anthropic-beta"] == "usage-report-2024-07-01", (
            f"Expected 'usage-report-2024-07-01', got {headers['anthropic-beta']!r}"
        )

    def test_headers_include_api_key(self) -> None:
        """Sanity check that existing headers still present after bug fix."""
        adapter = AnthropicAdapter()
        headers = adapter._headers(b"sk-ant-test-key")
        assert headers["x-api-key"] == "sk-ant-test-key"
        assert "anthropic-version" in headers
