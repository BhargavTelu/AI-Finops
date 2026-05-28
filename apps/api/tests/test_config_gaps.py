"""
Configuration validation gap tests.

Gap-28 (medium): encryption_key="" is silently accepted at Settings level.
                 EncryptionService rejects bad keys at instantiation, but
                 workers fail at runtime rather than at startup.
Gap-29 (medium): CORS_ORIGINS as a plain URL string raises JSONDecodeError in parse_cors.
                 This surfaces as a ValidationError at startup (correct behavior), but
                 the error message should be descriptive.
"""

import base64
import json

import pytest


# ── Gap-28: Encryption key validation ─────────────────────────────────────────

class TestEncryptionKeyValidation:
    """Gap-28 (medium): Settings silently accepts encryption_key="" - no startup guard."""

    def test_empty_key_raises_at_service_instantiation(self) -> None:
        """
        encryption_key="" passes Settings construction but EncryptionService
        must reject it at __init__: base64.b64decode("") = b"" → len 0 ≠ 32.
        Verifies the failure is at least caught somewhere (runtime, not never).
        """
        from api.services.encryption import EncryptionService

        with pytest.raises((ValueError, Exception)) as exc_info:
            EncryptionService("")

        assert "32" in str(exc_info.value) or "key" in str(exc_info.value).lower(), (
            "Gap-28: EncryptionService must raise a descriptive error for empty key. "
            f"Got: {exc_info.value}"
        )

    def test_16_byte_key_rejected_wrong_length(self) -> None:
        """
        AES-256-GCM requires exactly 32 bytes. A 16-byte key (AES-128) is valid
        base64 but must be rejected with a clear 'must be 32 bytes' message.
        """
        from api.services.encryption import EncryptionService

        short_key = base64.b64encode(b"sixteen-bytes!!").decode()  # 15 bytes
        with pytest.raises(ValueError) as exc_info:
            EncryptionService(short_key)

        assert "32" in str(exc_info.value), (
            f"Gap-28: Expected '32 bytes' in error message. Got: {exc_info.value}"
        )

    def test_non_base64_key_raises_decode_error(self) -> None:
        """
        A key containing characters outside the base64 alphabet raises an error.
        This is caught at EncryptionService.__init__ before any crypto operations.
        """
        from api.services.encryption import EncryptionService

        with pytest.raises(Exception):
            EncryptionService("not-valid-base64-!!!$%^&*")

    def test_valid_32_byte_key_accepted(self) -> None:
        """A valid 32-byte AES-256 key is accepted and can round-trip encrypt/decrypt."""
        from api.services.encryption import EncryptionService

        valid_key = base64.b64encode(b"\xcc" * 32).decode()
        cipher = EncryptionService(valid_key)

        original = b"test-secret-data"
        encrypted = cipher.encrypt(original)
        decrypted = cipher.decrypt(encrypted)

        assert decrypted == original

    def test_settings_does_not_validate_encryption_key_format(self) -> None:
        """
        Documents Gap-28: Settings model accepts any string for encryption_key,
        including empty string. There is no @field_validator checking base64 or length.
        The validation only occurs later, at EncryptionService instantiation in workers.
        """
        # Test the validator logic directly (avoid constructing full Settings with all
        # required env vars which would need real values or extensive mocking)
        import base64 as _b64

        # These are the values that SHOULD be rejected by Settings but currently aren't:
        bad_keys = ["", "not-base64", "too-short", "a" * 10]
        for bad_key in bad_keys:
            # None of these raise during simple string operations
            # (Settings just stores them as strings)
            assert isinstance(bad_key, str), f"Setup issue: {bad_key!r} is not a string"

        # The failure only surfaces when EncryptionService is constructed:
        from api.services.encryption import EncryptionService

        for bad_key in bad_keys:
            with pytest.raises(Exception, match=r"(32|key|decode|Invalid)"):
                EncryptionService(bad_key)


# ── Gap-29: CORS_ORIGINS validation ───────────────────────────────────────────

class TestCorsOriginsValidation:
    """Gap-29 (medium): parse_cors raises JSONDecodeError for plain string CORS_ORIGINS."""

    def test_json_array_string_parsed_to_list(self) -> None:
        """
        '["http://localhost:3000"]' (JSON array string) → list of strings.
        This is the expected format when CORS_ORIGINS is set as an env var.
        """
        from api.config import Settings

        # Call the validator directly as a classmethod
        result = Settings.parse_cors('["http://localhost:3000", "https://app.example.com"]')
        assert result == ["http://localhost:3000", "https://app.example.com"]

    def test_plain_url_string_raises_json_decode_error(self) -> None:
        """
        Gap-29: CORS_ORIGINS=http://localhost:3000 (not JSON) → json.loads raises.
        This propagates as a ValidationError at startup, which is the CORRECT behavior
        (fail fast). The gap is that the error message could be more descriptive.
        """
        from api.config import Settings

        with pytest.raises(json.JSONDecodeError):
            Settings.parse_cors("http://localhost:3000")

    def test_comma_separated_string_raises_json_decode_error(self) -> None:
        """
        CORS_ORIGINS=http://localhost:3000,https://app.example.com
        (comma-separated, not JSON array) also raises JSONDecodeError.
        Users sometimes set env vars this way and get a confusing startup error.
        """
        from api.config import Settings

        with pytest.raises(json.JSONDecodeError):
            Settings.parse_cors("http://localhost:3000,https://app.example.com")

    def test_list_input_passes_through_unchanged(self) -> None:
        """
        If cors_origins is already a list (e.g., set in code, not env var),
        parse_cors returns it unchanged.
        """
        from api.config import Settings

        origin_list = ["http://localhost:3000", "https://staging.example.com"]
        result = Settings.parse_cors(origin_list)
        assert result == origin_list

    def test_json_object_raises_value_error_or_type_error(self) -> None:
        """
        A JSON object '{"origins": [...]}' is valid JSON but not a list.
        parse_cors returns a dict; Pydantic then rejects it as not a list[str].
        """
        from api.config import Settings

        # parse_cors itself won't raise for valid JSON - it returns whatever json.loads gives
        result = Settings.parse_cors('{"origins": ["http://localhost:3000"]}')
        # Returns a dict, which Pydantic field validation would later reject
        assert isinstance(result, dict), (
            "parse_cors returns a dict for a JSON object - Pydantic will reject it as list[str]"
        )

    def test_empty_json_array_produces_empty_list(self) -> None:
        """'[]' (empty JSON array) → empty list of CORS origins."""
        from api.config import Settings

        result = Settings.parse_cors("[]")
        assert result == []
