"""Unit tests for Proof-Carrying Text (O8) Verifier."""

from __future__ import annotations

import hashlib
import unittest

from apps_rg.runtime.validators.proof_carrying_text_verifier import (
    PCTCertificate,
    verify_pct_certificate,
)


class TestProofCarryingTextVerifier(unittest.TestCase):

    def test_verify_valid_certificate(self) -> None:
        text = "Engineered distributed streaming pipeline handling 2M events per second."
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        cert = {
            "text_hash": text_hash,
            "spans": [
                {"text_span": "distributed streaming pipeline", "claimed_fact_ids": ["ev_001"]},
                {"text_span": "2M events per second", "claimed_fact_ids": ["ev_002"]},
            ],
            "banned_words_clean": True,
        }

        allowed_facts = {"ev_001", "ev_002", "ev_003"}
        result = verify_pct_certificate(text, cert, allowed_facts)
        self.assertTrue(result)

    def test_verify_hash_mismatch_fails(self) -> None:
        text = "Engineered distributed streaming pipeline handling 2M events per second."
        cert = {
            "text_hash": "incorrect_sha256_hash",
            "spans": [{"text_span": "some text", "claimed_fact_ids": ["ev_001"]}],
            "banned_words_clean": True,
        }
        result = verify_pct_certificate(text, cert, {"ev_001"})
        self.assertFalse(result)

    def test_verify_unauthorized_fact_fails(self) -> None:
        text = "Engineered distributed streaming pipeline handling 2M events per second."
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        cert = {
            "text_hash": text_hash,
            "spans": [
                {"text_span": "distributed streaming pipeline", "claimed_fact_ids": ["ev_unauthorized"]},
            ],
            "banned_words_clean": True,
        }

        allowed_facts = {"ev_001", "ev_002"}
        result = verify_pct_certificate(text, cert, allowed_facts)
        self.assertFalse(result)

    def test_verify_empty_certificate_fails(self) -> None:
        result = verify_pct_certificate("sample text", {}, {"ev_001"})
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
