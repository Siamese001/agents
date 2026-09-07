"""Verified apps_rg spine contract facade tests."""

from __future__ import annotations

import ast
from pathlib import Path

from apps_rg.runtime import spine_contracts


EXPECTED_EXPORTS = {
    "ALLOWED_PROMPT_SLOT_C0_EVIDENCE_DATA_ONLY",
    "AppsRgIngressPayload",
    "CompiledPromptArtifact",
    "EvidenceItem",
    "FinalEvidenceContract",
    "GraphTraversePolicy",
    "L1PlanContract",
    "L3_RUNTIME_RECEIPT_SCHEMA_VERSION",
    "L3RuntimeOrchestrationReceipt",
    "L3StepContractRef",
    "L3ToL2StepContract",
    "Origin",
    "PackageValidationReceipt",
    "PromptBlock",
    "RequestEnvelope",
    "RouteContract",
    "RouteGateReceipt",
    "RuntimeCustomizationPackage",
    "RuntimePosture",
    "STATUS_NOT_APPLICABLE",
    "STATUS_UNKNOWN",
    "SUPPORT_STATUS_BLOCKED",
    "SUPPORT_STATUS_CONFLICTED",
    "SUPPORT_STATUS_EMPTY",
    "SUPPORT_STATUS_PARTIAL",
    "SUPPORT_STATUS_PASS",
    "SUPPORT_STATUS_PASSING_VALUES",
    "SUPPORT_STATUS_WEAK",
    "SUPPORT_STATUS_WEAK_WITH_CAVEATS",
    "SealedL2Artifact",
    "ValidatedRequest",
    "X3Disposition",
    "compute_l3_runtime_digest",
    "lifecycle_trace_contract",
}

MISSING_CONTRACT_NAMES = {
    "CommitRequest",
    "ExitDispositionReceipt",
    "ExitReviewPacket",
    "RejectedRequest",
    "RuntimeExhaustBundle",
    "SealedSectionArtifact",
}


def test_spine_contracts_exports_only_verified_inventory_symbols() -> None:
    assert set(spine_contracts.__all__) == EXPECTED_EXPORTS


def test_spine_contracts_are_app_owned_contract_objects() -> None:
    for contract in (
        spine_contracts.ValidatedRequest,
        spine_contracts.L1PlanContract,
        spine_contracts.RouteContract,
        spine_contracts.GraphTraversePolicy,
        spine_contracts.FinalEvidenceContract,
        spine_contracts.CompiledPromptArtifact,
        spine_contracts.L3ToL2StepContract,
        spine_contracts.SealedL2Artifact,
        spine_contracts.X3Disposition,
    ):
        assert contract.__module__ == "apps_rg.runtime.spine_contracts"


def test_spine_contracts_has_no_missing_contract_placeholders() -> None:
    for name in MISSING_CONTRACT_NAMES:
        assert not hasattr(spine_contracts, name)


def test_spine_contracts_source_has_no_placeholder_assignments() -> None:
    source_path = Path(spine_contracts.__file__ or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    assigned_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    assigned_names.add(target.id)
    assert assigned_names.isdisjoint(MISSING_CONTRACT_NAMES)
