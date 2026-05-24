"""
Health endpoint tests — Section G.

TC-HLTH-01  GET /health — returns 200 {\"status\": \"ok\"} with no auth (public).
TC-HLTH-02  GET /health — not mounted under /api/v1 prefix.

Railway and any load balancer probe this endpoint. If it requires auth or is
behind the versioned prefix, the app is removed from rotation.
"""

from fastapi.testclient import TestClient

from api.main import app

# Use a plain client — NO auth header; health must be public.
client = TestClient(app)


class TestHealthEndpoint:
    """TC-HLTH-01 and TC-HLTH-02."""

    def test_health_returns_200_no_auth(self) -> None:
        """TC-HLTH-01 — GET /health with no auth token must return 200 ok."""
        resp = client.get("/health")
        assert resp.status_code == 200, (
            f"Expected 200 from /health (public endpoint), got {resp.status_code}. "
            "Railway health probes hit this without auth — a non-200 removes the app from rotation."
        )
        body = resp.json()
        assert body == {"status": "ok"}, f"Expected {{\"status\": \"ok\"}}, got {body}"

    def test_health_not_under_api_v1_prefix(self) -> None:
        """TC-HLTH-02 — /health must NOT be prefixed with /api/v1."""
        # The route registered in main.py is at the root, not under /api/v1.
        resp_root = client.get("/health")
        assert resp_root.status_code == 200, (
            "/health must be accessible at the root path, not /api/v1/health"
        )

        # Verify /api/v1/health does NOT exist (should 404 or 405, not 200).
        resp_prefixed = client.get("/api/v1/health")
        assert resp_prefixed.status_code != 200, (
            "/api/v1/health must not return 200 — the health endpoint must remain "
            "accessible at the root path even if the API prefix changes."
        )
