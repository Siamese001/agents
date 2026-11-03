"""Property-based tests for apps_research.

Hypothesis explores topic / config variations; these tests enforce invariants
from `apps_research/SVP_ENGINEERING_REVIEW.md`:
  - Topic round-trips for any non-empty text.
  - Result types always expose gate_violations.
  - SourceEntry confidence enforces [0,1] across the full continuous range
    (when SourceEntry is exposed).

Plan: docs/archive/windsurf/legacy-tree/plans/apps-svp-plus-hardening-7c4e3a.md (P4 NEXT_STEP)
"""
from __future__ import annotations

import unittest
from typing import Any, Callable

try:
    from hypothesis import assume, given, settings, strategies as st
except ImportError:  # guardian: allow-silent-swallow -- deterministic property-test fallback when hypothesis is not installed
    class _Strategy:
        def __init__(self, samples: list[Any]) -> None:
            self.samples = list(samples)

        def filter(self, pred: Callable[[Any], bool]) -> "_Strategy":
            return _Strategy([x for x in self.samples if pred(x)])

    class _StrategiesNamespace:
        @staticmethod
        def text(min_size: int = 1, max_size: int = 200) -> _Strategy:
            return _Strategy(
                [
                    "Enterprise AI Platform Strategy",
                    "Cloud Modernization & Risk Governance",
                    "Partner Ecosystem Co-Sell Architecture",
                    "A" * min(max_size, max(min_size, 64)),
                ]
            )

        @staticmethod
        def integers() -> _Strategy:
            return _Strategy([0, 1, 7, 42, -5])

        @staticmethod
        def floats(min_value: float = 0.0, max_value: float = 1.0, allow_nan: bool = False) -> _Strategy:
            del allow_nan
            mid = round((min_value + max_value) / 2.0, 6)
            return _Strategy([min_value, mid, max_value])

        @staticmethod
        def one_of(*strategies: _Strategy) -> _Strategy:
            combined: list[Any] = []
            for strat in strategies:
                combined.extend(strat.samples)
            return _Strategy(combined)

    st = _StrategiesNamespace()  # type: ignore[assignment]

    def settings(**_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return _decorator

    def given(**kw_strategies: _Strategy) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            key, strat = next(iter(kw_strategies.items()))

            def _wrapped(self: Any) -> None:
                for val in strat.samples:
                    fn(self, **{key: val})

            _wrapped.__name__ = fn.__name__
            return _wrapped

        return _decorator

    def assume(condition: bool) -> None:
        if not condition:
            return

from apps_research.types import (
    ResearchConfig,
    ResearchRequest,
    ResearchResult,
)


NON_EMPTY_TEXT = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())


class TestResearchProperties(unittest.TestCase):
    @settings(max_examples=30, deadline=None)
    @given(topic=NON_EMPTY_TEXT)
    def test_topic_round_trip(self, topic: str) -> None:
        req = ResearchRequest(topic=topic)
        rebuilt = ResearchRequest.model_validate(req.model_dump())
        self.assertEqual(req.topic, rebuilt.topic)

    @settings(max_examples=10, deadline=None)
    @given(seed=st.integers())
    def test_default_result_has_gate_violations(self, seed: int) -> None:
        del seed
        result = ResearchResult()
        self.assertIsInstance(result.gate_violations, list)

    @settings(max_examples=15, deadline=None)
    @given(invalid_conf=st.one_of(
        st.floats(min_value=1.0001, max_value=2.0, allow_nan=False),
        st.floats(min_value=-1.0, max_value=-0.0001, allow_nan=False),
    ))
    def test_source_entry_rejects_out_of_range_confidence(self, invalid_conf: float) -> None:
        try:
            from apps_research.types import SourceEntry
        except ImportError:  # guardian: allow-return-none-swallow -- optional type export; property test skips on ImportError
            self.skipTest("SourceEntry not exported")
            return
        # Skip exactly 1.0 / 0.0 boundary (those should be allowed).
        assume(invalid_conf > 1.0 or invalid_conf < 0.0)
        with self.assertRaises(Exception):
            SourceEntry(
                source_id="src-001",
                title="Test Source",
                confidence=invalid_conf,
            )

    @settings(max_examples=15, deadline=None)
    @given(valid_conf=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_source_entry_accepts_in_range_confidence(self, valid_conf: float) -> None:
        try:
            from apps_research.types import SourceEntry
        except ImportError:  # guardian: allow-return-none-swallow -- optional type export; property test skips on ImportError
            self.skipTest("SourceEntry not exported")
            return
        entry = SourceEntry(
            source_id="src-001",
            title="Test Source",
            confidence=valid_conf,
        )
        # Round-trip preserves the value.
        rebuilt = SourceEntry.model_validate(entry.model_dump())
        self.assertAlmostEqual(rebuilt.confidence, valid_conf, places=6)


if __name__ == "__main__":
    unittest.main()
