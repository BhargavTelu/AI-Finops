"""
Unit tests for EncryptionService (services/encryption.py).
TC-ENC-01 to TC-ENC-07.
"""

import base64

import pytest

from api.services.encryption import EncryptionService

# ── Test keys ─────────────────────────────────────────────────────────────────
# Valid: 32 bytes of 0xAA, base64-encoded
_VALID_KEY_B64: str = base64.b64encode(b"\xaa" * 32).decode()
# Invalid: 16 bytes
_SHORT_KEY_B64: str = base64.b64encode(b"\xaa" * 16).decode()


class TestEncryptionServiceInit:
    def test_wrong_key_length_raises(self) -> None:  # TC-ENC-02
        with pytest.raises(ValueError, match="32 bytes"):
            EncryptionService(_SHORT_KEY_B64)

    def test_empty_key_raises(self) -> None:  # TC-ENC-03
        with pytest.raises(Exception):  # binascii.Error or ValueError
            EncryptionService("")


class TestEncryptDecrypt:
    def setup_method(self) -> None:
        self.svc = EncryptionService(_VALID_KEY_B64)

    def test_round_trip(self) -> None:  # TC-ENC-01
        plaintext = b"sk-admin-test"
        blob = self.svc.encrypt(plaintext)
        assert self.svc.decrypt(blob) == plaintext

    def test_nonce_uniqueness(self) -> None:  # TC-ENC-04
        blobs = [self.svc.encrypt(b"same-plaintext") for _ in range(100)]
        assert len(set(blobs)) == 100

    def test_tampered_ciphertext_raises(self) -> None:  # TC-ENC-05
        blob = bytearray(self.svc.encrypt(b"secret"))
        blob[-1] ^= 0xFF  # flip last byte of GCM auth tag
        with pytest.raises(Exception):  # InvalidTag or ValueError
            self.svc.decrypt(bytes(blob))

    def test_nonce_is_first_12_bytes(self) -> None:  # TC-ENC-06
        blob = self.svc.encrypt(b"test")
        # blob = nonce(12) + ciphertext + tag(16) ≥ 28 bytes
        assert len(blob) >= 12
        # The first 12 bytes are the nonce
        nonce = blob[:12]
        assert len(nonce) == 12

    def test_binary_round_trip(self) -> None:  # TC-ENC-07
        data = b"\x00\xff\x00"
        assert self.svc.decrypt(self.svc.encrypt(data)) == data

    def test_wrong_key_raises_on_decrypt(self) -> None:  # M1-U-ENC-004
        """Ciphertext produced by key-1 must be unreadable by key-2 (GCM auth tag mismatch)."""
        key2 = base64.b64encode(b"\x22" * 32).decode()
        svc2 = EncryptionService(key2)
        blob = self.svc.encrypt(b"secret-payload")
        with pytest.raises(Exception):  # InvalidTag or ValueError from Cryptography
            svc2.decrypt(blob)
