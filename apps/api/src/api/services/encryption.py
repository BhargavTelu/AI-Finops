"""
AES-256-GCM encryption for Admin API keys stored in Postgres (bytea column).

The encryption key comes from Supabase Vault in production.
For local dev, set ENCRYPTION_KEY to a base64-encoded 32-byte value.

Usage:
    cipher = EncryptionService(settings.encryption_key)
    encrypted = cipher.encrypt(b"sk-admin-...")
    original  = cipher.decrypt(encrypted)
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptionService:
    _NONCE_BYTES = 12  # 96-bit nonce for GCM

    def __init__(self, key_b64: str) -> None:
        # Key must be exactly 32 bytes (256 bits) for AES-256
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise ValueError("Encryption key must be 32 bytes (base64-encoded)")
        self._aes = AESGCM(key)

    def encrypt(self, plaintext: bytes) -> bytes:
        """Return nonce || ciphertext (stored as bytea)."""
        nonce = os.urandom(self._NONCE_BYTES)
        ciphertext = self._aes.encrypt(nonce, plaintext, associated_data=None)
        return nonce + ciphertext

    def decrypt(self, blob: bytes) -> bytes:
        """Split nonce || ciphertext and decrypt."""
        nonce = blob[: self._NONCE_BYTES]
        ciphertext = blob[self._NONCE_BYTES :]
        return self._aes.decrypt(nonce, ciphertext, associated_data=None)
