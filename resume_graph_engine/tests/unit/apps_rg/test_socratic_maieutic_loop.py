"""Unit tests for Socratic Maieutics (O5) A2A reasoning loop."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps_rg.runtime.reasoning.socratic_maieutic_loop import (
    SOCRATIC_MAIEUTICS_SCHEMA,
    BulletCausalBridgeReceipt,
    SocraticMaieuticLoop,
)


class TestSocraticMaieuticLoop(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.artifact_dir = Path(self.tmp_dir.name)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_execute_loop_produces_valid_receipt(self) -> None:
        loop = SocraticMaieuticLoop(artifact_dir=self.artifact_dir)

        receipt = loop.execute_loop(
            raw_fact_text="Cut deployment latency by 45% using event-driven microservices.",
            assertion_id="ev_0042",
            reb_context={"operating_context": "High-load transaction tier", "scale": "10M events/day"},
            reb_bundle_id="reb_bundle_99",
        )

        self.assertIsInstance(receipt, BulletCausalBridgeReceipt)
        self.assertEqual(receipt.schema_version, SOCRATIC_MAIEUTICS_SCHEMA)
        self.assertEqual(receipt.assertion_id, "ev_0042")
        self.assertEqual(receipt.reb_bundle_id, "reb_bundle_99")
        self.assertTrue(receipt.synthesized_bullet.startswith("Under monolithic deployment contention"))
        self.assertEqual(receipt.x2_entailment_status, "PASS")
        self.assertTrue(receipt.deterministic_digest.startswith("sha256:"))

        # Check persisted receipt file
        receipt_file = self.artifact_dir / "causal_bridge_ev_0042.json"
        self.assertTrue(receipt_file.is_file())
        persisted = json.loads(receipt_file.read_text(encoding="utf-8"))
        self.assertEqual(persisted["assertion_id"], "ev_0042")
        self.assertEqual(persisted["deterministic_digest"], receipt.deterministic_digest)

    def test_digest_stability(self) -> None:
        receipt = BulletCausalBridgeReceipt(
            assertion_id="ev_101",
            reb_bundle_id="reb_101",
            raw_fact_text="Test fact",
            synthesized_bullet="Synthesized bullet text",
            generated_at_utc="2026-09-07T00:00:00Z",
        )
        d1 = receipt.compute_digest()
        d2 = receipt.compute_digest()
        self.assertEqual(d1, d2)
        self.assertTrue(d1.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
