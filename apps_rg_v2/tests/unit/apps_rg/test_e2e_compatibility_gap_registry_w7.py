from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _probes(*, failed: set[str] | None = None, crash: str = ""):
    from apps_rg.runtime.e2e_compatibility_gap_registry import (
        CompatibilityProbeResult,
        default_probes,
    )

    failed = failed or set()
    probes = {}
    for probe_id in default_probes():
        if probe_id == crash:
            probes[probe_id] = lambda _root: (_ for _ in ()).throw(RuntimeError("boom"))
        elif probe_id in failed:
            probes[probe_id] = lambda _root, pid=probe_id: CompatibilityProbeResult(
                pid, False, ("injected_verifier_failure",)
            )
        else:
            probes[probe_id] = lambda _root, pid=probe_id: CompatibilityProbeResult(
                pid, True, (), (f"{pid}.json",)
            )
    return probes


def test_all_executable_probes_must_pass_before_gap_registry_can_be_empty(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_compatibility_gap_registry import (
        evaluate_compatibility_gap_registry,
        validate_compatibility_gap_registry,
    )

    receipt = evaluate_compatibility_gap_registry(
        artifact_dir=tmp_path,
        repo_root=REPO_ROOT,
        probes=_probes(),
        generated_at_utc="2026-08-09T00:00:00+00:00",
    )

    assert receipt["status"] == "PASS"
    assert receipt["open_gaps"] == []
    assert receipt["summary"] == {
        "probe_count": 6,
        "passed_probe_count": 6,
        "failed_probe_count": 0,
        "open_gap_count": 0,
    }
    validate_compatibility_gap_registry(receipt)


@pytest.mark.parametrize(
    "failed_probe",
    [
        "APP_RUNTIME_INDEPENDENCE",
        "APPS_RESEARCH_HANDOFF_CONSUMER_RECEIPT",
        "CORE_RUNTIME_AUTHORITY",
        "RECEIPT_DERIVED_STAGE_LEDGER",
        "MANDATORY_OUTPUT_BUNDLE",
        "TERMINAL_MANIFEST_AND_CLOSEOUT",
    ],
)
def test_every_failed_verifier_has_exactly_one_live_open_gap(
    tmp_path: Path, failed_probe: str
) -> None:
    from apps_rg.runtime.e2e_compatibility_gap_registry import (
        evaluate_compatibility_gap_registry,
    )

    receipt = evaluate_compatibility_gap_registry(
        artifact_dir=tmp_path,
        repo_root=REPO_ROOT,
        probes=_probes(failed={failed_probe}),
    )

    assert receipt["status"] == "BLOCKED_COMPATIBILITY_GAPS"
    assert [gap["probe_id"] for gap in receipt["open_gaps"]] == [failed_probe]
    assert receipt["summary"]["failed_probe_count"] == 1
    assert receipt["summary"]["open_gap_count"] == 1


def test_crashing_verifier_becomes_an_open_gap_instead_of_disappearing(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_compatibility_gap_registry import (
        evaluate_compatibility_gap_registry,
    )

    receipt = evaluate_compatibility_gap_registry(
        artifact_dir=tmp_path,
        repo_root=REPO_ROOT,
        probes=_probes(crash="TERMINAL_MANIFEST_AND_CLOSEOUT"),
    )

    gap = receipt["open_gaps"][0]
    assert gap["probe_id"] == "TERMINAL_MANIFEST_AND_CLOSEOUT"
    assert gap["errors"] == ["verifier_exception:RuntimeError:boom"]


def test_receipt_validation_rejects_hidden_failure_or_diagnostic_authorization(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.e2e_compatibility_gap_registry import (
        CompatibilityGapRegistryError,
        evaluate_compatibility_gap_registry,
        validate_compatibility_gap_registry,
    )

    receipt = evaluate_compatibility_gap_registry(
        artifact_dir=tmp_path,
        repo_root=REPO_ROOT,
        probes=_probes(failed={"CORE_RUNTIME_AUTHORITY"}),
    )
    receipt["open_gaps"] = []
    with pytest.raises(CompatibilityGapRegistryError):
        validate_compatibility_gap_registry(receipt)

    receipt = evaluate_compatibility_gap_registry(
        artifact_dir=tmp_path,
        repo_root=REPO_ROOT,
        probes=_probes(),
    )
    receipt["product_authorized"] = True
    with pytest.raises(CompatibilityGapRegistryError):
        validate_compatibility_gap_registry(receipt)


def test_default_registry_reports_real_missing_run_contracts_as_open_gaps(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_compatibility_gap_registry import (
        evaluate_compatibility_gap_registry,
    )

    receipt = evaluate_compatibility_gap_registry(
        artifact_dir=tmp_path,
        repo_root=REPO_ROOT,
    )

    assert receipt["status"] == "BLOCKED_COMPATIBILITY_GAPS"
    assert receipt["summary"]["failed_probe_count"] == 6
    assert receipt["summary"]["open_gap_count"] == 6
