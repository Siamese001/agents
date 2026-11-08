#!/usr/bin/env python3
"""Class A unit tests for Bayesian multi-factor confidence scoring and calibrated margin gating."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.hitl_governance import (
    DEFAULT_AMBIGUITY_THRESHOLD,
    DEFAULT_MIN_CONFIDENCE_FLOOR,
    HITLDecisionStore,
    calculate_calibrated_confidence,
    evaluate_hitl_surfacing_gate,
    parse_confidence_score,
)


class HitlConfidenceBayesianScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_hitl.sqlite"
        self.store = HITLDecisionStore(db_path=self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_calibrated_confidence_clamping_and_bounds(self) -> None:
        """Score must always clamp strictly between 0.05 and 0.99."""
        # Extreme negative penalty
        low_score = calculate_calibrated_confidence(
            option=0.10,
            risk_level="CRITICAL",
            is_irreversible=True,
            blast_radius_layers=5,
        )
        self.assertGreaterEqual(low_score, 0.05)

        # Extreme positive boost
        high_score = calculate_calibrated_confidence(
            option=0.98,
            evidence_refs=["ref1", "ref2", "ref3", "ref4"],
            has_verification_receipt=True,
            risk_level="LOW",
        )
        self.assertLessEqual(high_score, 0.99)

    def test_bayesian_learning_prior_lifecycle(self) -> None:
        """Outcome records must adjust category and option learning priors."""
        category = "refactoring_wave"

        # Initially zero adjustment
        initial_adj = self.store.query_learning_adjustment(category, "Option A")
        self.assertEqual(initial_adj, 0.0)

        # Record multiple successful executions
        for i in range(5):
            self.store.record_decision(
                decision_id=f"dec_{i}",
                task_id=f"task_{i}",
                category=category,
                options=["Option A", "Option B"],
                selected_option="Option A",
                operator_action="APPROVED",
                margin=0.25,
                calibrated_confidence=0.85,
                outcome="SUCCESS",
            )

        updated_adj = self.store.query_learning_adjustment(category, "Option A")
        self.assertGreater(updated_adj, 0.0)

        # Test failure penalizes the prior
        for i in range(5, 12):
            self.store.record_decision(
                decision_id=f"dec_{i}",
                task_id=f"task_{i}",
                category=category,
                options=["Option A", "Option B"],
                selected_option="Option A",
                operator_action="OVERRIDDEN",
                margin=0.05,
                calibrated_confidence=0.50,
                outcome="FAILED",
            )

        penalized_adj = self.store.query_learning_adjustment(category, "Option A")
        self.assertLess(penalized_adj, updated_adj)

    def test_ambiguity_margin_surfacing_gate(self) -> None:
        """Gate surfaces to human when delta <= 20%, proceeds autonomously when delta > 20%."""
        # Margin <= 0.20 -> Must surface
        payload_narrow = {
            "decision_id": "dec_narrow",
            "options": [
                {"label": "Approach A", "confidence": 0.75},
                {"label": "Approach B", "confidence": 0.65},
            ],
        }
        res_narrow = evaluate_hitl_surfacing_gate(payload_narrow)
        self.assertTrue(res_narrow["should_surface"])
        self.assertEqual(res_narrow["action"], "SURFACE_HITL_ATOMIC")
        self.assertAlmostEqual(res_narrow["margin"], 0.10, places=2)

        # Margin > 0.20 -> Autonomous proceed
        payload_wide = {
            "decision_id": "dec_wide",
            "options": [
                {"label": "Approach A", "confidence": 0.90},
                {"label": "Approach B", "confidence": 0.60},
            ],
        }
        res_wide = evaluate_hitl_surfacing_gate(payload_wide)
        self.assertFalse(res_wide["should_surface"])
        self.assertEqual(res_wide["action"], "PROCEED_AUTONOMOUSLY")
        self.assertAlmostEqual(res_wide["margin"], 0.30, places=2)


if __name__ == "__main__":
    unittest.main()
