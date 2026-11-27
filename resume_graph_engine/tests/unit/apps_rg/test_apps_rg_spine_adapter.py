"""Unit tests for canonical `apps_rg` spine front-contract invariants."""

from __future__ import annotations

import pytest

from apps_rg.runtime.section_spine_terminology import CANONICAL_SPINE_CHAIN
from apps_rg.runtime.spine.front_contracts import (
    FRONT_SPINE_CONTRACTS,
    SectionFrontSpinePreconditionError,
    activate_fixture_dev_bypass,
    deactivate_fixture_dev_bypass,
)


@pytest.mark.unit
class TestAppsRgSpineAdapter:
    """Verify real `apps_rg` spine contract invariants (replaces placeholder stubs)."""

    def test_canonical_spine_chain_non_empty_and_ordered(self) -> None:
        assert isinstance(CANONICAL_SPINE_CHAIN, tuple)
        assert len(CANONICAL_SPINE_CHAIN) >= 3
        assert "C0" in CANONICAL_SPINE_CHAIN

    def test_front_spine_contracts_declared(self) -> None:
        assert isinstance(FRONT_SPINE_CONTRACTS, tuple)
        assert len(FRONT_SPINE_CONTRACTS) >= 3
        assert "ValidatedRequest" in FRONT_SPINE_CONTRACTS

    def test_fixture_dev_bypass_rejects_product_certified_flag(self) -> None:
        deactivate_fixture_dev_bypass()
        with pytest.raises(ValueError, match="non_product_certified=True"):
            activate_fixture_dev_bypass(non_product_certified=False)
        assert issubclass(SectionFrontSpinePreconditionError, RuntimeError)
