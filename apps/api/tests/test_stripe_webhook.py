"""
Unit tests for POST /api/webhooks/stripe - signature handling, event-id
idempotency, and the three lifecycle transitions. Stripe signature
construction and Supabase are mocked.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from api.routers import webhooks

client = TestClient(app)

ORG_ID = "00000000-0000-0000-0000-000000000042"
HEADERS = {"stripe-signature": "t=123,v1=sig"}


def _event(event_type: str, obj: dict) -> dict:
    return {"id": "evt_test_1", "type": event_type, "data": {"object": obj}}


class _RecordingDb:
    """Captures upserts/updates/inserts per table; chainable like supabase-py."""

    def __init__(self, billing_lookup_rows: list[dict] | None = None) -> None:
        self.upserts: dict[str, list[dict]] = {}
        self.updates: dict[str, list[dict]] = {}
        self.inserts: dict[str, list[dict]] = {}
        self._billing_lookup_rows = billing_lookup_rows or []

    def table(self, name: str) -> MagicMock:
        chain = MagicMock()
        for method in ("select", "eq", "limit"):
            getattr(chain, method).return_value = chain
        result = MagicMock()
        result.data = self._billing_lookup_rows if name == "billing" else []
        chain.execute.return_value = result

        def record_upsert(row: dict, **_kw) -> MagicMock:
            self.upserts.setdefault(name, []).append(row)
            return chain

        def record_update(row: dict, **_kw) -> MagicMock:
            self.updates.setdefault(name, []).append(row)
            return chain

        def record_insert(row: dict, **_kw) -> MagicMock:
            self.inserts.setdefault(name, []).append(row)
            return chain

        chain.upsert.side_effect = record_upsert
        chain.update.side_effect = record_update
        chain.insert.side_effect = record_insert
        return chain


def _post(event: dict, db: _RecordingDb):
    with (
        patch.object(webhooks, "_service_db", return_value=db),
        patch("stripe.Webhook.construct_event", return_value=event),
    ):
        return client.post("/api/webhooks/stripe", headers=HEADERS, content=b"{}")


class TestSignature:
    def test_invalid_signature_400(self) -> None:
        import stripe as stripe_lib

        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe_lib.SignatureVerificationError("bad", "sig"),
        ):
            resp = client.post("/api/webhooks/stripe", headers=HEADERS, content=b"{}")
        assert resp.status_code == 400

    def test_missing_signature_header_422(self) -> None:
        resp = client.post("/api/webhooks/stripe", content=b"{}")
        assert resp.status_code == 422


class TestIdempotency:
    def test_duplicate_event_acked_without_processing(self) -> None:
        db = _RecordingDb()
        event = _event("checkout.session.completed", {"client_reference_id": ORG_ID})
        with (
            patch.object(webhooks, "_service_db", return_value=db),
            patch("stripe.Webhook.construct_event", return_value=event),
            patch.object(webhooks, "_claim_stripe_event", return_value=False),
        ):
            resp = client.post("/api/webhooks/stripe", headers=HEADERS, content=b"{}")
        assert resp.status_code == 200
        assert resp.json() == {"received": True}
        assert "billing" not in db.upserts  # no re-processing

    def test_claim_inserts_event_id(self) -> None:
        db = _RecordingDb()
        assert webhooks._claim_stripe_event(db, "evt_x", "some.type") is True
        assert db.inserts["stripe_events"][0]["id"] == "evt_x"


class TestCheckoutCompleted:
    def test_upserts_billing_and_mirrors_plan(self) -> None:
        db = _RecordingDb()
        obj = {
            "id": "cs_1",
            "client_reference_id": ORG_ID,
            "customer": "cus_1",
            "subscription": "sub_1",
            "metadata": {"org_id": ORG_ID, "plan": "growth"},
        }
        resp = _post(_event("checkout.session.completed", obj), db)
        assert resp.status_code == 200

        billing = db.upserts["billing"][0]
        assert billing["org_id"] == ORG_ID
        assert billing["stripe_customer_id"] == "cus_1"
        assert billing["stripe_subscription_id"] == "sub_1"
        assert billing["plan"] == "growth"
        assert billing["status"] == "active"
        assert db.updates["organizations"][0] == {"plan": "growth"}
        # Audit trail written
        assert db.inserts["audit_events"][0]["action"] == "billing.checkout_completed"

    def test_captures_checkout_completed_event(self) -> None:
        db = _RecordingDb()
        obj = {"client_reference_id": ORG_ID, "metadata": {"plan": "starter"}}
        with patch("api.services.analytics.capture") as mock_capture:
            resp = _post(_event("checkout.session.completed", obj), db)
        assert resp.status_code == 200
        mock_capture.assert_called_once_with(ORG_ID, "checkout_completed", {"plan": "starter"})

    def test_missing_org_reference_does_not_crash(self) -> None:
        db = _RecordingDb()
        resp = _post(_event("checkout.session.completed", {"id": "cs_x"}), db)
        assert resp.status_code == 200
        assert "billing" not in db.upserts


class TestSubscriptionLifecycle:
    def test_updated_writes_status_plan_and_period_end(self) -> None:
        db = _RecordingDb()
        obj = {
            "id": "sub_1",
            "customer": "cus_1",
            "status": "active",
            "current_period_end": 1781136000,  # 2026-06-11
            "metadata": {"org_id": ORG_ID, "plan": "growth"},
            "items": {"data": [{"price": {"id": "price_unknown"}}]},
        }
        resp = _post(_event("customer.subscription.updated", obj), db)
        assert resp.status_code == 200
        billing = db.upserts["billing"][0]
        assert billing["status"] == "active"
        assert billing["plan"] == "growth"  # falls back to metadata for unknown price
        assert billing["current_period_end"].startswith("2026-06")

    def test_updated_resolves_org_via_billing_lookup(self) -> None:
        # No metadata on the subscription - resolved from our billing table.
        db = _RecordingDb(billing_lookup_rows=[{"org_id": ORG_ID}])
        obj = {"id": "sub_1", "customer": "cus_1", "status": "past_due", "metadata": {}}
        resp = _post(_event("customer.subscription.updated", obj), db)
        assert resp.status_code == 200
        assert db.upserts["billing"][0]["status"] == "past_due"

    def test_deleted_cancels_and_downgrades_org_plan(self) -> None:
        db = _RecordingDb()
        obj = {"id": "sub_1", "metadata": {"org_id": ORG_ID}}
        resp = _post(_event("customer.subscription.deleted", obj), db)
        assert resp.status_code == 200
        assert db.upserts["billing"][0]["status"] == "canceled"
        assert db.updates["organizations"][0] == {"plan": "trial"}

    def test_unknown_subscription_logged_not_crashed(self) -> None:
        db = _RecordingDb(billing_lookup_rows=[])
        obj = {"id": "sub_ghost", "metadata": {}, "status": "active"}
        resp = _post(_event("customer.subscription.updated", obj), db)
        assert resp.status_code == 200
        assert "billing" not in db.upserts

    def test_unhandled_event_type_acked(self) -> None:
        db = _RecordingDb()
        resp = _post(_event("invoice.finalized", {}), db)
        assert resp.status_code == 200
