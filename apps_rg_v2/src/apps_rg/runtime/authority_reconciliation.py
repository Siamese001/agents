"""Deterministic, zero-provider authority reconciliation for apps_rg runs.

This module is intentionally stdlib-only so historical run evidence can be
reopened inside :class:`ZeroProviderReplayGuard` without importing the apps_rg
package (whose normal runtime import graph may include provider SDKs).

The app-owned lane ``x3_disposition.json`` and
``exit_disposition_receipt.json`` are evidence mirrors.  Current section lanes
are authorized by their sealed producer-owned
``x3_disposition_receipt.json`` plus final-materialization and one-spine
receipts.  The whole-resume exit, rather than an individual section, owns
``X3D_ALLOW_FINISH``.  A content-bound
``apps_rg_core_runtime_authority.json`` remains supported only for historical
lane bundles that emitted it.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping


W1_RECONCILIATION_SCHEMA = "apps_rg.authority_reconciliation.v1"
W1_CORRECTION_SCHEMA = "apps_rg.authorization_correction.v1"
W1_PARALLEL_PROOF_SCHEMA = "apps_rg.l0_parallel_artifact_replay.v1"
W1_COMPLETION_SCHEMA = "apps_rg.authority_reconciliation_completion.v1"

W1_RECONCILIATION_FILENAME = "w1_authoritative_reconciliation.json"
W1_CORRECTION_FILENAME = "w1_authorization_correction_receipt.json"
W1_PARALLEL_PROOF_FILENAME = "w1_l0_parallel_replay_proof.json"
W1_COMPLETION_FILENAME = "w1_completion_receipt.json"

CORE_RUNTIME_AUTHORITY_ARTIFACT = "apps_rg_core_runtime_authority.json"
CORE_X3_DISPOSITION_ARTIFACT = "x3_disposition_receipt.json"
LANE_X3_MIRROR_ARTIFACT = "x3_disposition.json"
LANE_EXIT_MIRROR_ARTIFACT = "exit_disposition_receipt.json"
PRODUCT_AUTHORIZATION_ARTIFACT = "apps_rg_product_authorization_receipt.json"
WHOLE_RUN_EXIT_ARTIFACT = "apps_rg_whole_run_exit_review_packet.json"

X3D_ALLOW_FINISH = "X3D_ALLOW_FINISH"
X3A_DENY_REROUTE = "X3A_DENY_REROUTE"
X3_ALLOW = "X3_ALLOW"

GENERATED_LANES: tuple[str, ...] = (
    "headline",
    "executive_summary",
    "unify_narrative",
    "unify_bullets",
    "ibm_narrative",
    "ibm_bullets",
    "insurtech_narrative",
    "insurtech_bullets",
    "ey_narrative",
    "ey_bullets",
    "competencies",
)

_LEGACY_CORE_PRODUCER = "apps_rg.runtime.entrypoints.integrated_single_action_spine_run"
_SEALED_LANE_PRODUCER = "apps_rg.runtime.orchestration.app_single_action_spine"
_COMMON_LANE_REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "l2_handoff_receipt.json",
    "l2_spine_receipt.json",
    CORE_X3_DISPOSITION_ARTIFACT,
    LANE_X3_MIRROR_ARTIFACT,
    LANE_EXIT_MIRROR_ARTIFACT,
    "x2_gate_outputs.json",
)
_SEALED_LANE_REQUIRED_ARTIFACTS: tuple[str, ...] = (
    *_COMMON_LANE_REQUIRED_ARTIFACTS,
    "final_materialized_acceptance_contract.json",
    "one_spine_certification_receipt.json",
    "product_certification_receipt.json",
)
_MODULAR_LANE_REQUIRED_ARTIFACTS: tuple[str, ...] = (
    *_COMMON_LANE_REQUIRED_ARTIFACTS,
    "final_materialized_acceptance_contract.json",
    "section_front_spine_receipt.json",
    "exit_spine_receipt.json",
    "apps_rg_spine_proof.json",
)
_LEGACY_LANE_REQUIRED_ARTIFACTS: tuple[str, ...] = (
    *_COMMON_LANE_REQUIRED_ARTIFACTS,
    CORE_RUNTIME_AUTHORITY_ARTIFACT,
)


class AuthorityReconciliationError(RuntimeError):
    """Raised when a replay contract cannot be safely derived or emitted."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_digest(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _payload(value: Mapping[str, Any]) -> dict[str, Any]:
    nested = value.get("payload")
    return dict(nested) if isinstance(nested, Mapping) else dict(value)


def _binding(root: Path, path: Path) -> dict[str, Any]:
    target = path.resolve()
    try:
        ref = target.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise AuthorityReconciliationError(
            f"authority source escapes run root: {path}"
        ) from exc
    return {
        "artifact_ref": ref,
        "present": target.is_file(),
        "byte_length": target.stat().st_size if target.is_file() else 0,
        "sha256": _sha256_file(target) if target.is_file() else "",
    }


def _failed_checks(checks: Mapping[str, bool]) -> list[str]:
    return sorted(name for name, passed in checks.items() if not passed)


def _extract_core_x3(envelope: Mapping[str, Any]) -> str:
    payload = _payload(envelope)
    return str(payload.get("x3_disposition") or payload.get("x3_code") or "")


def _x2_pass(payload: Mapping[str, Any]) -> bool:
    gates = payload.get("gates")
    if not isinstance(gates, list) or not gates:
        return False
    return bool(
        all(isinstance(row, Mapping) and row.get("pass") is True for row in gates)
        and not list(payload.get("failed_gates") or ())
        and not list(payload.get("failed_gate_ids") or ())
        and int(payload.get("x2_failed") or 0) == 0
    )


def resolve_lane_artifact_root(source_run: Path | str, lane: str) -> Path:
    """Resolve a lane's artifact directory within either supported run layout.

    The canonical whole-resume CLI owns flat ``lanes/<lane>`` directories.
    Standalone modular R4 runs retain ``modular_r4/sections/<lane>``.  Prefer
    the flat directory whenever it exists so an integrated run cannot silently
    read stale or nonexistent modular paths.
    """
    root = Path(source_run).resolve()
    lane_id = str(lane).strip()
    flat_lane_root = root / "lanes" / lane_id
    if flat_lane_root.is_dir():
        return flat_lane_root
    return root / "modular_r4" / "sections" / lane_id


def derive_lane_authority(source_run: Path | str, lane: str) -> dict[str, Any]:
    """Recompute one lane's authority without trusting app X3 mirrors."""

    root = Path(source_run).resolve()
    lane_id = str(lane).strip()
    lane_root = resolve_lane_artifact_root(root, lane_id)
    legacy_core_authority_path = lane_root / CORE_RUNTIME_AUTHORITY_ARTIFACT
    legacy_core_contract = legacy_core_authority_path.is_file()
    one_spine_contract = (lane_root / "one_spine_certification_receipt.json").is_file()
    required_artifacts = (
        _LEGACY_LANE_REQUIRED_ARTIFACTS
        if legacy_core_contract
        else (
            _SEALED_LANE_REQUIRED_ARTIFACTS
            if one_spine_contract
            else _MODULAR_LANE_REQUIRED_ARTIFACTS
        )
    )
    paths = {name: lane_root / name for name in required_artifacts}
    docs = {name: _read_json(path) for name, path in paths.items()}

    handoff = docs["l2_handoff_receipt.json"]
    handoff_checks = handoff.get("checks")
    handoff_checks = dict(handoff_checks) if isinstance(handoff_checks, Mapping) else {}
    l2_spine = docs["l2_spine_receipt.json"]
    core_envelope = docs[CORE_X3_DISPOSITION_ARTIFACT]
    core_payload = _payload(core_envelope)
    core_authority = docs.get(CORE_RUNTIME_AUTHORITY_ARTIFACT, {})
    normalized = core_authority.get("normalized_contract")
    normalized = dict(normalized) if isinstance(normalized, Mapping) else {}
    normalized_x3 = normalized.get("x3")
    normalized_x3 = dict(normalized_x3) if isinstance(normalized_x3, Mapping) else {}
    normalized_spine = normalized.get("spine_proof")
    normalized_spine = (
        dict(normalized_spine) if isinstance(normalized_spine, Mapping) else {}
    )
    source_bindings = core_authority.get("source_artifact_bindings")
    source_bindings = source_bindings if isinstance(source_bindings, list) else []
    core_x3_binding = next(
        (
            row
            for row in source_bindings
            if isinstance(row, Mapping)
            and row.get("artifact_ref") == CORE_X3_DISPOSITION_ARTIFACT
        ),
        {},
    )
    mirror = docs[LANE_X3_MIRROR_ARTIFACT]
    exit_mirror = docs[LANE_EXIT_MIRROR_ARTIFACT]
    lane_x2 = docs["x2_gate_outputs.json"]
    final_acceptance = docs.get("final_materialized_acceptance_contract.json", {})
    one_spine = docs.get("one_spine_certification_receipt.json", {})
    product_certification = docs.get("product_certification_receipt.json", {})
    front_spine = docs.get("section_front_spine_receipt.json", {})
    exit_spine = docs.get("exit_spine_receipt.json", {})
    spine_proof_envelope = docs.get("apps_rg_spine_proof.json", {})
    spine_proof = _payload(spine_proof_envelope)
    spine_proof_digest = canonical_digest(spine_proof) if spine_proof else ""
    core_code = _extract_core_x3(core_envelope)
    normalized_code = str(normalized_x3.get("x3_disposition") or "")

    core_authority_body = dict(core_authority)
    stored_core_authority_digest = str(
        core_authority_body.pop("deterministic_digest", "") or ""
    )
    core_payload_digest = canonical_digest(core_payload) if core_payload else ""

    checks: dict[str, bool] = {
        "all_required_artifacts_present": all(
            path.is_file() for path in paths.values()
        ),
        "l2_handoff_schema_exact": handoff.get("schema_version")
        == "apps_rg_l2_handoff_receipt_v2",
        "l2_handoff_section_match": handoff.get("section_id") == lane_id,
        "l2_handoff_status_pass": handoff.get("handoff_status") == "PASS",
        "l2_handoff_checks_complete": bool(handoff_checks),
        "l2_handoff_checks_all_pass": bool(handoff_checks)
        and all(value is True for value in handoff_checks.values()),
        "l2_spine_schema_exact": l2_spine.get("schema_version")
        == "l2_spine_receipt_v2",
        "l2_spine_section_match": l2_spine.get("section_id") == lane_id,
        "l2_spine_status_pass": l2_spine.get("l2_spine_status") == "PASS",
        "l2_spine_precondition_pass": l2_spine.get("precondition_status") == "PASS",
        "l2_spine_no_direct_l4_write": l2_spine.get("direct_l4_write_allowed") is False,
        "core_x3_payload_hash_valid": bool(core_payload_digest)
        and core_envelope.get("artifact_hash") == core_payload_digest,
        "lane_x2_all_pass": _x2_pass(lane_x2),
        "lane_mirror_declared_nonauthoritative": mirror.get("section_x3_authoritative")
        is False
        and mirror.get("section_x3_mirror_only") is True
        and mirror.get("spine_x3_claimed") is False,
        "lane_mirror_points_to_core_receipt": mirror.get("core_exit_authority_ref")
        == CORE_X3_DISPOSITION_ARTIFACT,
        "lane_exit_mirror_declared_nonauthoritative": exit_mirror.get(
            "section_x3_authoritative"
        )
        is False
        and exit_mirror.get("section_x3_mirror_only") is True
        and exit_mirror.get("spine_x3_claimed") is False
        and exit_mirror.get("canonical_exit_claimed") is False,
        "final_materialized_acceptance_pass": mirror.get(
            "final_materialized_acceptance_ok"
        )
        is True,
    }
    if legacy_core_contract:
        checks.update(
            {
                "core_x3_producer_exact": core_envelope.get("producer_component")
                == _LEGACY_CORE_PRODUCER,
                "core_x3_exact_authorizing_code": core_code == X3D_ALLOW_FINISH,
                "lane_x3_exact_authorizing_code": core_code == X3D_ALLOW_FINISH,
                "core_authority_digest_valid": bool(stored_core_authority_digest)
                and stored_core_authority_digest
                == canonical_digest(core_authority_body),
                "core_authority_contract_valid": normalized.get("valid") is True,
                "core_authority_source_x3_bound": bool(core_x3_binding)
                and core_x3_binding.get("present") is True
                and core_x3_binding.get("hash_matches") is True,
                "core_authority_x3_matches_producer": bool(core_code)
                and normalized_code == core_code,
                "core_authority_spine_success": normalized_spine.get("success")
                is True,
                "core_authority_outcome_authorized": core_authority.get("status")
                == "PASS"
                and core_authority.get("outcome_authorized") is True,
            }
        )
    elif one_spine_contract:
        checks.update(
            {
                "sealed_lane_x3_producer_exact": core_envelope.get(
                    "producer_component"
                )
                == _SEALED_LANE_PRODUCER,
                "lane_x3_exact_authorizing_code": core_code == X3_ALLOW,
                # Keep the existing field as a compatibility alias for callers
                # that report this check, while making its section-level meaning
                # explicit in the canonical lane_x3_* field above.
                "core_x3_exact_authorizing_code": core_code == X3_ALLOW,
                "sealed_lane_final_materialization_pass": final_acceptance.get(
                    "pass"
                )
                is True
                and final_acceptance.get("x3_authorizes") is True
                and final_acceptance.get("x2_final_materialized_binding_pass")
                is True
                and final_acceptance.get("section_id") == lane_id,
                "sealed_lane_one_spine_certified": one_spine.get(
                    "certification_status"
                )
                == "PASS"
                and one_spine.get("required_chain_complete") is True
                and one_spine.get("all_required_artifacts_present") is True
                and one_spine.get("all_required_refs_valid") is True,
                "sealed_lane_product_certified": product_certification.get(
                    "product_certification"
                )
                == "ONE_SPINE_SECTION_CERTIFIED"
                and product_certification.get("proof_eligible") is True
                and product_certification.get("x3_code") == core_code,
                "lane_mirror_x3_matches_sealed_receipt": mirror.get("x3_code")
                == core_code,
            }
        )
    else:
        checks.update(
            {
                "sealed_lane_x3_producer_exact": core_envelope.get(
                    "producer_component"
                )
                == _SEALED_LANE_PRODUCER,
                "lane_x3_exact_authorizing_code": core_code == X3_ALLOW,
                "core_x3_exact_authorizing_code": core_code == X3_ALLOW,
                "sealed_lane_final_materialization_pass": final_acceptance.get(
                    "pass"
                )
                is True
                and final_acceptance.get("x3_authorizes") is True
                and final_acceptance.get("x2_final_materialized_binding_pass")
                is True
                and final_acceptance.get("section_id") == lane_id,
                "modular_lane_front_spine_pass": front_spine.get(
                    "schema_version"
                )
                == "section_front_spine_receipt_v1"
                and front_spine.get("section_id") == lane_id
                and front_spine.get("front_spine_status") == "PASS"
                and front_spine.get("precondition_status") == "PASS"
                and front_spine.get("product_visible") is True
                and front_spine.get("fixture_dev_only") is False,
                "modular_lane_exit_spine_pass": exit_spine.get("schema_version")
                == "exit_spine_receipt_v1"
                and exit_spine.get("section_id") == lane_id
                and exit_spine.get("exit_spine_status") == "PASS"
                and exit_spine.get("canonical_exit_authority_ref")
                == CORE_X3_DISPOSITION_ARTIFACT
                and exit_spine.get("section_x3_authoritative") is False
                and exit_spine.get("canonical_exit_claimed_on_exit_receipt") is False,
                "modular_lane_spine_proof_valid": spine_proof_envelope.get(
                    "producer_component"
                )
                == _SEALED_LANE_PRODUCER
                and bool(spine_proof_digest)
                and spine_proof_envelope.get("artifact_hash") == spine_proof_digest
                and spine_proof.get("schema_version") == "apps_rg.spine_proof.v1"
                and spine_proof.get("success") is True
                and spine_proof.get("exit_code") == 0
                and not list(spine_proof.get("blocking_gaps") or ()),
                "lane_mirror_x3_matches_sealed_receipt": mirror.get("x3_code")
                == core_code,
            }
        )
    failures = _failed_checks(checks)
    return {
        "lane": lane_id,
        "status": "PASS" if not failures else "BLOCKED",
        "authorized": not failures,
        "authority_contract_kind": (
            "legacy_core_normalization"
            if legacy_core_contract
            else (
                "sealed_section_lane"
                if one_spine_contract
                else "sealed_modular_lane"
            )
        ),
        "required_artifacts": list(required_artifacts),
        "authoritative_x3_code": core_code,
        "normalized_authoritative_x3_code": normalized_code,
        "mirror_x3_code": str(mirror.get("x3_code") or ""),
        "l2_handoff_status": str(handoff.get("handoff_status") or ""),
        "l2_spine_status": str(l2_spine.get("l2_spine_status") or ""),
        "model_id_used": str(handoff.get("model_id_used") or ""),
        "provider_lane_used": str(handoff.get("provider_lane_used") or ""),
        "tokens_emitted": int(handoff.get("tokens_emitted") or 0),
        "budget_ceiling": int(handoff.get("budget_ceiling") or 0),
        "checks": checks,
        "failed_checks": failures,
        "source_bindings": [
            *[_binding(root, path) for path in paths.values()],
            *(
                [_binding(root, legacy_core_authority_path)]
                if legacy_core_authority_path.is_file()
                else []
            ),
        ],
    }


def derive_final_assembly_authority(source_run: Path | str) -> dict[str, Any]:
    root = Path(source_run).resolve()
    receipt_path = (
        root / "modular_r4" / "final_resume_assembly" / "final_resume_receipt.json"
    )
    receipt = _read_json(receipt_path)
    review = receipt.get("review_lane_policy_summary")
    review = dict(review) if isinstance(review, Mapping) else {}
    semantics = receipt.get("assembly_proof_semantics")
    semantics = dict(semantics) if isinstance(semantics, Mapping) else {}
    checks = {
        "final_resume_receipt_present": receipt_path.is_file(),
        "assembly_gates_all_pass": receipt.get("gates_all_pass") is True,
        "structural_x2_all_pass": receipt.get("structural_x2_all_pass") is True,
        "cross_section_x2_all_pass": receipt.get("cross_section_x2_all_pass") is True,
        "cross_section_x2_product_pass": receipt.get("cross_section_x2_product_pass")
        is True,
        "whole_resume_graph_evidence_release_pass": receipt.get(
            "whole_resume_graph_evidence_release_pass"
        )
        is True,
        "review_policy_product_allow_claimed": review.get("product_allow_claimed")
        is True,
        "assembly_product_release_eligible": semantics.get("product_release_eligible")
        is True,
    }
    failures = _failed_checks(checks)
    return {
        "status": "PASS" if not failures else "BLOCKED",
        "product_release_eligible": not failures,
        "checks": checks,
        "failed_checks": failures,
        "source_binding": _binding(root, receipt_path),
    }


def _single_research_artifact(root: Path, filename: str) -> Path:
    candidates = sorted((root / "apps_research" / "runs").glob(f"*/{filename}"))
    return candidates[0] if len(candidates) == 1 else root / "__missing__" / filename


def _single_ledger_artifact(root: Path, suffix: str) -> Path:
    candidates = sorted((root / "e2e_ledger_receipts").glob(f"*_{suffix}.json"))
    return candidates[0] if len(candidates) == 1 else root / "__missing__" / suffix


def derive_entry_authority(source_run: Path | str) -> dict[str, Any]:
    """Derive Apps Research -> U0 -> L0 evidence independently of lane Exit."""

    root = Path(source_run).resolve()
    paths = {
        "fresh_preflight": root / "e2e_preflight_product_entry_receipt.json",
        "apps_research_exit": _single_research_artifact(
            root, "exit_disposition_receipt.json"
        ),
        "apps_research_handoff": _single_research_artifact(
            root, "apps_research_apps_rg_handoff_v2.json"
        ),
        "apps_rg_u0": root / "u0_receipt.json",
        "apps_rg_l1": _single_ledger_artifact(root, "apps_rg_l1"),
        "apps_rg_l0": _single_ledger_artifact(root, "apps_rg_l0"),
    }
    docs = {name: _read_json(path) for name, path in paths.items()}
    preflight = docs["fresh_preflight"]
    research_exit = docs["apps_research_exit"]
    handoff = docs["apps_research_handoff"]
    u0 = docs["apps_rg_u0"]
    l1 = docs["apps_rg_l1"]
    l0 = docs["apps_rg_l0"]
    identity = preflight.get("identity")
    identity = dict(identity) if isinstance(identity, Mapping) else {}
    checks = {
        "fresh_preflight_pass": preflight.get("status") == "PASS",
        "apps_research_exit_x3d": research_exit.get("x3_code") == X3D_ALLOW_FINISH,
        "apps_research_handoff_v2": handoff.get("schema_version")
        == "apps_research.apps_rg_handoff.v2",
        "apps_research_identity_match": bool(identity)
        and handoff.get("identity") == identity,
        "apps_rg_u0_pass": u0.get("status") == "PASS",
        "apps_rg_u0_identity_match": bool(identity) and u0.get("identity") == identity,
        "apps_rg_l1_pass": l1.get("status") == "PASS",
        "apps_rg_l1_full_resume_shape": l1.get("work_shape")
        == "full_resume_generation",
        "apps_rg_l1_identity_match": bool(identity) and l1.get("identity") == identity,
        "apps_rg_l0_pass": l0.get("status") == "PASS",
        "apps_rg_l0_managed_workflow": l0.get("execution_form") == "MANAGED_WORKFLOW",
        "apps_rg_l0_identity_match": bool(identity) and l0.get("identity") == identity,
    }
    failures = _failed_checks(checks)
    return {
        "status": "PASS" if not failures else "BLOCKED",
        "entry_authorized": not failures,
        "identity": identity,
        "checks": checks,
        "failed_checks": failures,
        "source_bindings": [_binding(root, path) for path in paths.values()],
    }


def derive_run_authority(source_run: Path | str) -> dict[str, Any]:
    root = Path(source_run).resolve()
    lanes = [derive_lane_authority(root, lane) for lane in GENERATED_LANES]
    entry = derive_entry_authority(root)
    assembly = derive_final_assembly_authority(root)
    lane_pass = all(row["authorized"] for row in lanes)
    reasons: list[str] = []
    if not entry["entry_authorized"]:
        reasons.append("ENTRY_AUTHORITY_BLOCKED")
    if not lane_pass:
        reasons.append("ONE_OR_MORE_AUTHORITATIVE_LANE_CONTRACTS_BLOCKED")
    if not assembly["product_release_eligible"]:
        reasons.append("FINAL_ASSEMBLY_PRODUCT_RELEASE_BLOCKED")
    product_authorized = bool(
        entry["entry_authorized"] and lane_pass and assembly["product_release_eligible"]
    )
    payload: dict[str, Any] = {
        "schema_version": W1_RECONCILIATION_SCHEMA,
        "wave": "W1",
        "replay_mode": "ARTIFACT_ONLY_ZERO_PROVIDER",
        "source_run_id": root.name,
        "entry_authority": entry,
        "lane_authority": lanes,
        "final_assembly_authority": assembly,
        "authoritative_lane_contracts_pass": lane_pass,
        "authorized_lane_count": sum(1 for row in lanes if row["authorized"]),
        "blocked_lane_count": sum(1 for row in lanes if not row["authorized"]),
        "authoritative_x3_codes": {
            str(row["lane"]): str(row["authoritative_x3_code"]) for row in lanes
        },
        "mirror_x3_codes": {
            str(row["lane"]): str(row["mirror_x3_code"]) for row in lanes
        },
        "product_authorized": product_authorized,
        "publish_allowed": product_authorized,
        "status": "PASS" if product_authorized else "BLOCKED",
        "failure_reasons": reasons,
        "unknown_never_pass": True,
    }
    payload["semantic_digest"] = canonical_digest(payload)
    return payload


def _parse_dag_dependencies(manifest_path: Path) -> dict[str, tuple[str, ...]]:
    """Parse the small lane/dependency portion of the YAML SSOT with stdlib only."""

    dependencies: dict[str, list[str]] = {}
    current = ""
    in_lanes = False
    in_dependencies = False
    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped == "lanes:":
            in_lanes = True
            continue
        if stripped == "waves:":
            break
        if not in_lanes or not stripped or stripped.startswith("#"):
            continue
        if raw_line.startswith("  - id: "):
            current = stripped.removeprefix("- id: ").strip()
            dependencies[current] = []
            in_dependencies = False
            continue
        if stripped == "depends_on:":
            in_dependencies = True
            continue
        if in_dependencies and raw_line.startswith("      - ") and current:
            dependencies[current].append(stripped.removeprefix("- ").strip())
            continue
        if raw_line.startswith("    ") and not raw_line.startswith("      "):
            in_dependencies = False
    return {lane: tuple(values) for lane, values in dependencies.items()}


def run_l0_parallel_artifact_replay(
    *,
    source_run: Path | str,
    dag_manifest_path: Path | str,
    max_parallel: int = 5,
) -> dict[str, Any]:
    """Exercise the real L0 dependency shape with saved bytes and no runtime calls."""

    root = Path(source_run).resolve()
    manifest = Path(dag_manifest_path).resolve(strict=True)
    dependencies = _parse_dag_dependencies(manifest)
    selected = tuple(GENERATED_LANES)
    manifest_complete = set(dependencies) == set(selected)
    dependency_ids_valid = all(
        dependency in dependencies
        for values in dependencies.values()
        for dependency in values
    )
    cap = max(2, min(int(max_parallel), len(selected)))
    root_lanes = tuple(lane for lane in selected if not dependencies.get(lane))
    barrier = threading.Barrier(len(root_lanes)) if len(root_lanes) > 1 else None
    lock = threading.Lock()
    active = 0
    max_active = 0
    root_barrier_passed: set[str] = set()

    def replay_lane(lane: str) -> dict[str, Any]:
        nonlocal active, max_active
        lane_root = resolve_lane_artifact_root(root, lane)
        lane_authority = derive_lane_authority(root, lane)
        required_artifacts = lane_authority.get("required_artifacts")
        required_artifacts = (
            required_artifacts if isinstance(required_artifacts, list) else []
        )
        bindings = [
            _binding(root, lane_root / str(name)) for name in required_artifacts
        ]
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            if barrier is not None and lane in root_lanes:
                barrier.wait(timeout=10)
                with lock:
                    root_barrier_passed.add(lane)
            return {
                "lane": lane,
                "artifact_replay_complete": all(row["present"] for row in bindings),
                "artifact_binding_digest": canonical_digest(bindings),
            }
        finally:
            with lock:
                active -= 1

    pending = set(selected)
    completed: dict[str, dict[str, Any]] = {}
    running: dict[Future[dict[str, Any]], str] = {}
    dependency_order_valid = True
    with ThreadPoolExecutor(max_workers=cap) as pool:
        while pending or running:
            for lane in selected:
                if len(running) >= cap or lane not in pending:
                    continue
                deps = dependencies.get(lane, ())
                if not all(
                    dep in completed and completed[dep]["artifact_replay_complete"]
                    for dep in deps
                ):
                    continue
                pending.remove(lane)
                running[pool.submit(replay_lane, lane)] = lane
            if running:
                future = next(as_completed(tuple(running)))
                lane = running.pop(future)
                completed[lane] = future.result()
                continue
            if pending:
                dependency_order_valid = False
                break

    overlap_proven = bool(
        len(root_lanes) > 1
        and len(root_barrier_passed) == len(root_lanes)
        and max_active >= 2
    )
    checks = {
        "dag_manifest_complete": manifest_complete,
        "dag_dependency_ids_valid": dependency_ids_valid,
        "all_lanes_replayed": set(completed) == set(selected),
        "all_lane_artifact_reads_complete": len(completed) == len(selected)
        and all(row["artifact_replay_complete"] for row in completed.values()),
        "dependency_order_valid": dependency_order_valid,
        "parallel_overlap_proven": overlap_proven,
        "parallel_cap_at_least_two": cap >= 2,
    }
    failures = _failed_checks(checks)
    payload: dict[str, Any] = {
        "schema_version": W1_PARALLEL_PROOF_SCHEMA,
        "wave": "W1",
        "status": "PASS" if not failures else "BLOCKED",
        "proof_scope": "REPLAY_ONLY_NON_PRODUCT",
        "scheduler": "concurrent.futures.ThreadPoolExecutor",
        "dependency_admission_semantics": (
            "saved_artifact_replay_complete_not_product_authority"
        ),
        "dag_manifest_ref": manifest.as_posix(),
        "dag_manifest_sha256": _sha256_file(manifest),
        "dependencies": {lane: list(dependencies.get(lane, ())) for lane in selected},
        "configured_max_parallel": cap,
        "max_active_workers_observed": max_active,
        "root_lanes": list(root_lanes),
        "root_barrier_parties": len(root_lanes),
        "root_barrier_passed_lanes": sorted(root_barrier_passed),
        "parallel_overlap_proven": overlap_proven,
        "lane_results": [completed[lane] for lane in selected if lane in completed],
        "checks": checks,
        "failed_checks": failures,
        "provider_or_model_execution": False,
    }
    payload["semantic_digest"] = canonical_digest(payload)
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:12]}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def emit_w1_authority_reconciliation(
    *,
    source_run: Path | str,
    output_dir: Path | str,
    dag_manifest_path: Path | str,
) -> dict[str, Any]:
    """Emit additive correction evidence; never mutate historical run bytes."""

    root = Path(source_run).resolve(strict=True)
    output = Path(output_dir).resolve()
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise AuthorityReconciliationError("W1 output cannot be inside source run")

    reconciliation = derive_run_authority(root)
    parallel = run_l0_parallel_artifact_replay(
        source_run=root,
        dag_manifest_path=dag_manifest_path,
    )
    original_auth_path = root / PRODUCT_AUTHORIZATION_ARTIFACT
    original_exit_path = root / WHOLE_RUN_EXIT_ARTIFACT
    original_auth = _read_json(original_auth_path)
    correction_checks = {
        "original_authorization_receipt_present": original_auth_path.is_file(),
        "original_authorization_claimed_success": original_auth.get("authorized")
        is True
        and original_auth.get("status") == "AUTHORIZED",
        "reconciliation_complete": reconciliation.get("semantic_digest", "") != "",
        "reconciliation_denies_product": reconciliation.get("product_authorized")
        is False,
        "candidate_output_preserved": (
            root / "outputs" / "generated_resume.json"
        ).is_file(),
        "parallel_replay_proof_pass": parallel.get("status") == "PASS",
    }
    correction_failures = _failed_checks(correction_checks)
    correction: dict[str, Any] = {
        "schema_version": W1_CORRECTION_SCHEMA,
        "wave": "W1",
        "status": "PASS" if not correction_failures else "BLOCKED",
        "correction_disposition": "SUPERSEDED_INVALID_AUTHORITY",
        "source_run_id": root.name,
        "original_authorization": _binding(root, original_auth_path),
        "original_whole_run_exit": _binding(root, original_exit_path),
        "original_authorized_claim": original_auth.get("authorized") is True,
        "corrected_product_authorized": False,
        "corrected_publish_allowed": False,
        "corrected_pipeline_complete": False,
        "candidate_artifacts_preserved": True,
        "source_artifacts_mutated": False,
        "new_uwg_operation_attempted": False,
        "apps_eval_executed": False,
        "l6_executed": False,
        "reconciliation_ref": W1_RECONCILIATION_FILENAME,
        "reconciliation_semantic_digest": reconciliation["semantic_digest"],
        "decisive_failure_reasons": reconciliation["failure_reasons"],
        "checks": correction_checks,
        "failed_checks": correction_failures,
    }
    correction["semantic_digest"] = canonical_digest(correction)

    completion_checks = {
        "authoritative_reconciliation_emitted": bool(
            reconciliation.get("semantic_digest")
        ),
        "historical_authorization_corrected": correction.get("status") == "PASS",
        "l0_parallel_replay_proven": parallel.get("status") == "PASS",
        "product_remains_denied": reconciliation.get("product_authorized") is False,
        "no_eval_or_l6_executed": correction.get("apps_eval_executed") is False
        and correction.get("l6_executed") is False,
        "no_new_uwg_operation": correction.get("new_uwg_operation_attempted") is False,
    }
    completion_failures = _failed_checks(completion_checks)
    completion: dict[str, Any] = {
        "schema_version": W1_COMPLETION_SCHEMA,
        "wave": "W1",
        "status": "PASS" if not completion_failures else "BLOCKED",
        "source_run_id": root.name,
        "scope_complete": not completion_failures,
        "w2_authorized": not completion_failures,
        "product_authorized": False,
        "pipeline_complete": False,
        "reconciliation_ref": W1_RECONCILIATION_FILENAME,
        "correction_ref": W1_CORRECTION_FILENAME,
        "parallel_replay_proof_ref": W1_PARALLEL_PROOF_FILENAME,
        "checks": completion_checks,
        "failed_checks": completion_failures,
    }
    completion["semantic_digest"] = canonical_digest(completion)

    _atomic_write_json(output / W1_RECONCILIATION_FILENAME, reconciliation)
    _atomic_write_json(output / W1_PARALLEL_PROOF_FILENAME, parallel)
    _atomic_write_json(output / W1_CORRECTION_FILENAME, correction)
    _atomic_write_json(output / W1_COMPLETION_FILENAME, completion)
    return {
        "reconciliation": reconciliation,
        "parallel_replay": parallel,
        "correction": correction,
        "completion": completion,
    }


__all__ = [
    "AuthorityReconciliationError",
    "CORE_RUNTIME_AUTHORITY_ARTIFACT",
    "CORE_X3_DISPOSITION_ARTIFACT",
    "GENERATED_LANES",
    "LANE_EXIT_MIRROR_ARTIFACT",
    "LANE_X3_MIRROR_ARTIFACT",
    "W1_COMPLETION_FILENAME",
    "W1_CORRECTION_FILENAME",
    "W1_PARALLEL_PROOF_FILENAME",
    "W1_RECONCILIATION_FILENAME",
    "canonical_digest",
    "derive_entry_authority",
    "derive_final_assembly_authority",
    "derive_lane_authority",
    "derive_run_authority",
    "emit_w1_authority_reconciliation",
    "lane_artifact_root",
    "run_l0_parallel_artifact_replay",
]
