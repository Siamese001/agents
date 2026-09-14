"""Precision cryptography manager with advanced algorithms."""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger(__name__)


class PrecisionCryptographyManager:
    """Precision cryptography manager with advanced algorithms."""

    def __init__(self) -> None:
        self.symmetric_keys: dict[str, bytes] = {}
        self.key_pairs: dict[str, tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]] = {}
        self.key_rotation_interval = timedelta(days=30)
        self.encryption_metrics = {
            "encryptions": 0,
            "decryptions": 0,
            "key_rotations": 0,
            "encryption_failures": 0,
        }

    def generate_symmetric_key(self, key_id: str, key_size: int = 256) -> str:
        """Generate symmetric key with secure random."""
        if key_size not in [128, 192, 256]:
            raise ValueError("Key size must be 128, 192, or 256 bits")

        key = secrets.token_bytes(key_size // 8)
        self.symmetric_keys[key_id] = key

        logger.info(f"Generated symmetric key {key_id} ({key_size} bits)")
        return key_id

    def generate_asymmetric_key_pair(self, key_id: str, key_size: int = 2048) -> str:
        """Generate RSA key pair with secure parameters."""
        if key_size not in [1024, 2048, 4096]:
            raise ValueError("Key size must be 1024, 2048, or 4096 bits")

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend(),
        )
        public_key = private_key.public_key()

        self.key_pairs[key_id] = (private_key, public_key)

        logger.info(f"Generated RSA key pair {key_id} ({key_size} bits)")
        return key_id

    def encrypt_symmetric(self, key_id: str, plaintext: bytes) -> tuple[bytes, bytes]:
        """Encrypt data using AES-GCM with authenticated encryption."""
        if key_id not in self.symmetric_keys:
            raise ValueError(f"Symmetric key {key_id} not found")

        try:
            key = self.symmetric_keys[key_id]

            # Generate random IV
            iv = secrets.token_bytes(12)  # 96 bits for GCM

            # Create cipher
            cipher = Cipher(
                algorithms.AES(key),
                modes.GCM(iv),
                backend=default_backend(),
            )
            encryptor = cipher.encryptor()

            # Encrypt and get authentication tag
            ciphertext = encryptor.update(plaintext) + encryptor.finalize()
            tag = encryptor.tag

            self.encryption_metrics["encryptions"] += 1

            return (iv + ciphertext, tag)

        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RuntimeError,
        ) as e:  # guardian: allow-broad-exception -- intentional error boundary, re-raises all caught exceptions to caller
            self.encryption_metrics["encryption_failures"] += 1
            logger.error(f"Symmetric encryption failed: {e}")
            raise

    def decrypt_symmetric(self, key_id: str, ciphertext: bytes, tag: bytes) -> bytes:
        """Decrypt data using AES-GCM with authentication."""
        if key_id not in self.symmetric_keys:
            raise ValueError(f"Symmetric key {key_id} not found")

        try:
            key = self.symmetric_keys[key_id]

            # Extract IV (first 12 bytes)
            iv = ciphertext[:12]
            actual_ciphertext = ciphertext[12:]

            # Create cipher
            cipher = Cipher(
                algorithms.AES(key),
                modes.GCM(iv, tag),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()

            # Decrypt
            plaintext = decryptor.update(actual_ciphertext) + decryptor.finalize()

            self.encryption_metrics["decryptions"] += 1

            return plaintext

        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RuntimeError,
        ) as e:  # guardian: allow-broad-exception -- intentional error boundary, re-raises all caught exceptions to caller
            logger.error(f"Symmetric decryption failed: {e}")
            raise

    def encrypt_asymmetric(self, key_id: str, plaintext: bytes) -> bytes:
        """Encrypt data using RSA with OAEP padding."""
        if key_id not in self.key_pairs:
            raise ValueError(f"Key pair {key_id} not found")

        try:
            _, public_key = self.key_pairs[key_id]

            # RSA encryption with OAEP padding
            ciphertext = public_key.encrypt(
                plaintext,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            self.encryption_metrics["encryptions"] += 1
            return ciphertext

        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RuntimeError,
        ) as e:  # guardian: allow-broad-exception -- intentional error boundary, re-raises all caught exceptions to caller
            self.encryption_metrics["encryption_failures"] += 1
            logger.error(f"Asymmetric encryption failed: {e}")
            raise

    def decrypt_asymmetric(self, key_id: str, ciphertext: bytes) -> bytes:
        """Decrypt data using RSA with OAEP padding."""
        if key_id not in self.key_pairs:
            raise ValueError(f"Key pair {key_id} not found")

        try:
            private_key, _ = self.key_pairs[key_id]

            # RSA decryption with OAEP padding
            plaintext = private_key.decrypt(
                ciphertext,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            self.encryption_metrics["decryptions"] += 1
            return plaintext

        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RuntimeError,
        ) as e:  # guardian: allow-broad-exception -- intentional error boundary, re-raises all caught exceptions to caller
            logger.error(f"Asymmetric decryption failed: {e}")
            raise

    def get_cryptography_metrics(self) -> dict[str, Any]:
        """Get cryptography metrics."""
        return {
            "symmetric_keys": len(self.symmetric_keys),
            "asymmetric_key_pairs": len(self.key_pairs),
            "metrics": self.encryption_metrics,
            "key_rotation_interval_days": self.key_rotation_interval.days,
        }


__all__ = ["PrecisionCryptographyManager"]
