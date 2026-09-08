from __future__ import annotations

from apps_rg.runtime import spine_contracts


def test_spine_contracts_exports_only_verified_contract_symbols() -> None:
    assert set(spine_contracts.__all__) == {
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


def test_spine_contracts_export_local_contracts() -> None:
    for contract in (
        spine_contracts.CompiledPromptArtifact,
        spine_contracts.FinalEvidenceContract,
        spine_contracts.GraphTraversePolicy,
        spine_contracts.L1PlanContract,
        spine_contracts.L3ToL2StepContract,
        spine_contracts.RouteContract,
        spine_contracts.SealedL2Artifact,
        spine_contracts.ValidatedRequest,
        spine_contracts.X3Disposition,
    ):
        assert contract.__module__ == "apps_rg.runtime.spine_contracts"
