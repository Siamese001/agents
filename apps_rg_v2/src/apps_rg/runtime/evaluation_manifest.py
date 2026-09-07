"""Frozen Apps RG inputs for post-run evaluation.

The product pipeline writes many receipts while it closes a run.  An evaluator
must not infer its input universe by recursively scanning that mutable tree.
This module emits one explicit, byte-bound allowlist after product
authorization and before Apps Eval starts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CANDIDATE_EVALUATION_MANIFEST = "candidate_evaluation_manifest.v2.json"
CANDIDATE_EVALUATION_MANIFEST_SCHEMA = "apps_rg.candidate_evaluation_manifest.v2"

EXPECTED_LANES: tuple[str, ...] = (
    "competencies",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "ey_bullets",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
    "ey_narrative",
    "executive_summary",
    "headline",
)

_ROOT_ARTIFACTS: tuple[tuple[str, str, bool], ...] = (
    ("final_resume_output_json", "FINAL_RESUME_OUTPUT.json", True),
    ("final_resume_output_text", "FINAL_RESUME_OUTPUT.txt", True),
    ("run_bundle_index", "RUN_BUNDLE_INDEX.json", True),
    ("runtime_identity_envelope", "runtime_identity_envelope.json", True),
    ("runtime_exhaust_bundle", "runtime_exhaust_bundle.json", True),
    ("preflight_product_entry", "e2e_preflight_product_entry_receipt.json", True),
    ("product_authorization", "apps_rg_product_authorization_receipt.json", True),
    ("whole_run_exit_review_packet", "apps_rg_whole_run_exit_review_packet.json", True),
    ("x3_disposition", "x3_disposition_receipt.json", True),
    ("u0_runtime_package", "u0_receipt.json", True),
    ("l1_static_plan_profile", "l1_plan_contract.json", False),
    ("l0_route_profile", "route_contract.json", True),
    ("c0_evidence_manifest", "c0_bypass_receipt.json", False),
    ("pa_compiled_prompt", "prompt_assembly_bypass_receipt.json", False),
    ("full_run_section_status", "full_run_section_status.json", True),
    ("cross_section_x2_gate_outputs", "modular_r4/final_resume_assembly/cross_section_x2_gate_outputs.json", True),
    ("final_resume_x2_gate_outputs", "modular_r4/final_resume_assembly/final_resume_x2_gate_outputs.json", True),
    ("uwg_commit_request", "commit_request.json", True),
    ("uwg_validation_receipt", "uwg_validation_receipt.json", True),
    ("uwg_commit_receipt", "uwg_commit_receipt.json", True),
)

_EXTRA_ROOT_ROLE_PATHS: dict[str, tuple[str, ...]] = {
    "cross_section_x2_gate_outputs": (
        "modular_r4/final_resume_assembly/cross_section_x2_gate_outputs.json",
        "cross_section_x2_gate_outputs.json",
        "final_resume_assembly/cross_section_x2_gate_outputs.json",
        "assembly/cross_section_x2_gate_outputs.json",
    ),
    "final_resume_x2_gate_outputs": (
        "modular_r4/final_resume_assembly/final_resume_x2_gate_outputs.json",
        "final_resume_x2_gate_outputs.json",
        "final_resume_assembly/final_resume_x2_gate_outputs.json",
        "assembly/final_resume_x2_gate_outputs.json",
    ),
}

_LANE_ARTIFACTS: tuple[tuple[str, str, bool], ...] = (
    ("lane_l2_output", "l2_output.json", True),
    ("lane_runtime_payload", "runtime_payload.json", True),
    ("lane_x2_gate_outputs", "x2_gate_outputs.json", True),
    ("lane_x1d_llm_judge_outputs", "x1d_llm_judge_outputs.json", True),
    ("lane_x3_disposition", "x3_disposition.json", True),
    ("lane_l6_shadow_eval_package", "l6_shadow_eval_package.json", True),
    ("lane_canonical_claim_ledger", "canonical_claim_ledger_v2.json", False),
)

_IDENTITY_KEYS = (
    "parent_run_id",
    "child_run_id",
    "section_attempt_id",
    "runtime_exhaust_bundle_id",
)


class CandidateEvaluationManifestError(ValueError):
    """A required Apps Eval input cannot be frozen or re-opened safely."""


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _contained(root: Path, ref: str) -> Path | None:
    raw = str(ref or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return None
    return resolved


def _identity_from_envelope(root: Path) -> dict[str, str]:
    envelope = _read_json(root / "runtime_identity_envelope.json")
    payload = envelope.get("payload")
    payload = payload if isinstance(payload, Mapping) else envelope
    identity = {
        "parent_run_id": str(payload.get("parent_run_id") or "").strip(),
        "child_run_id": str(payload.get("child_run_id") or "").strip(),
    }
    exhaust = root / "runtime_exhaust_bundle.json"
    identity["runtime_exhaust_bundle_id"] = (
        f"sha256:{_sha256_file(exhaust)}" if exhaust.is_file() else ""
    )
    return identity


def _lane_attempt_id(lane_root: Path) -> str:
    for filename in ("l2_output.json", "runtime_payload.json", "attempt_receipt.json"):
        payload = _read_json(lane_root / filename)
        for key in ("section_attempt_id", "run_id", "attempt_id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
    return ""


def _schema_version(path: Path) -> str:
    if path.suffix.lower() != ".json":
        return ""
    payload = _read_json(path)
    nested = payload.get("payload")
    nested = nested if isinstance(nested, Mapping) else payload
    return str(nested.get("schema_version") or nested.get("schema") or "").strip()


def _binding(
    *,
    root: Path,
    role: str,
    ref: str,
    required: bool,
    identity: Mapping[str, str],
    lane_id: str = "",
) -> dict[str, Any]:
    primary_ref = str(ref or "").replace("\\", "/")
    candidate_refs = _EXTRA_ROOT_ROLE_PATHS.get(role, (primary_ref,))
    path: Path | None = None
    resolved_ref = primary_ref
    for candidate_ref in candidate_refs:
        norm_ref = str(candidate_ref or "").replace("\\", "/")
        candidate_path = _contained(root, norm_ref)
        if candidate_path is not None and candidate_path.is_file():
            path = candidate_path
            resolved_ref = norm_ref
            break
    if path is None or not path.is_file():
        return {
            "role": role,
            "lane_id": lane_id,
            "artifact_ref": primary_ref,
            "required": required,
            "identity": dict(identity),
            "missing": True,
        }
    raw = path.read_bytes()
    return {
        "role": role,
        "lane_id": lane_id,
        "artifact_ref": resolved_ref,
        "required": required,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_length": len(raw),
        "schema_version": _schema_version(path),
        "identity": dict(identity),
    }


def _manifest_digest(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    return _canonical_digest(unsigned)


def build_candidate_evaluation_manifest(artifact_dir: Path | str) -> dict[str, Any]:
    """Return a new frozen candidate-input manifest without writing it."""

    root = Path(artifact_dir).resolve()
    if not root.is_dir():
        raise CandidateEvaluationManifestError("candidate_evaluation_run_root_missing")
    product_identity = _identity_from_envelope(root)
    bindings: list[dict[str, Any]] = []
    root_identity = {
        **product_identity,
        "section_attempt_id": f"whole_resume:{product_identity['child_run_id']}",
    }
    for role, ref, required in _ROOT_ARTIFACTS:
        bindings.append(
            _binding(
                root=root,
                role=role,
                ref=ref,
                required=required,
                identity=root_identity,
            )
        )
    final_output = _read_json(root / "FINAL_RESUME_OUTPUT.json")
    final_resume = final_output.get("final_resume_json")
    if isinstance(final_resume, Mapping):
        final_ref = str(final_resume.get("relpath") or "")
    else:
        final_ref = ""
    bindings.append(
        _binding(
            root=root,
            role="final_resume_json",
            ref=final_ref,
            required=True,
            identity=root_identity,
        )
    )
    for lane_id in EXPECTED_LANES:
        lane_root = root / "lanes" / lane_id
        attempt_id = _lane_attempt_id(lane_root) if lane_root.is_dir() else ""
        lane_identity = {
            "parent_run_id": product_identity["parent_run_id"],
            "child_run_id": (
                f"{product_identity['child_run_id']}:{lane_id}:{attempt_id}"
                if attempt_id
                else ""
            ),
            "section_attempt_id": attempt_id,
            "runtime_exhaust_bundle_id": product_identity["runtime_exhaust_bundle_id"],
        }
        for role, filename, required in _LANE_ARTIFACTS:
            bindings.append(
                _binding(
                    root=root,
                    role=role,
                    lane_id=lane_id,
                    ref=(Path("lanes") / lane_id / filename).as_posix(),
                    required=required,
                    identity=lane_identity,
                )
            )
    payload: dict[str, Any] = {
        "schema_version": CANDIDATE_EVALUATION_MANIFEST_SCHEMA,
        "run_id": root.name,
        "product_identity": product_identity,
        "artifact_bindings": bindings,
    }
    payload["manifest_sha256"] = _manifest_digest(payload)
    return payload


def emit_candidate_evaluation_manifest(artifact_dir: Path | str) -> Path:
    root = Path(artifact_dir).resolve()
    payload = build_candidate_evaluation_manifest(root)
    target = root / CANDIDATE_EVALUATION_MANIFEST
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def validate_candidate_evaluation_manifest(
    artifact_dir: Path | str,
) -> tuple[dict[str, Any], list[str]]:
    """Independently re-open a candidate manifest and every allowlisted byte."""

    root = Path(artifact_dir).resolve()
    path = root / CANDIDATE_EVALUATION_MANIFEST
    payload = _read_json(path)
    errors: list[str] = []
    if payload.get("schema_version") != CANDIDATE_EVALUATION_MANIFEST_SCHEMA:
        errors.append("candidate_evaluation_manifest_schema_invalid")
    declared_digest = str(payload.get("manifest_sha256") or "")
    if declared_digest != _manifest_digest(payload):
        errors.append("candidate_evaluation_manifest_digest_invalid")
    product_identity = payload.get("product_identity")
    product_identity = product_identity if isinstance(product_identity, Mapping) else {}
    if not all(str(product_identity.get(key) or "").strip() for key in ("parent_run_id", "child_run_id", "runtime_exhaust_bundle_id")):
        errors.append("candidate_evaluation_product_identity_missing")
    bindings = payload.get("artifact_bindings")
    bindings = bindings if isinstance(bindings, list) else []
    seen: set[tuple[str, str]] = set()
    for binding in bindings:
        if not isinstance(binding, Mapping):
            errors.append("candidate_evaluation_binding_invalid")
            continue
        role = str(binding.get("role") or "")
        lane_id = str(binding.get("lane_id") or "")
        key = (lane_id, role)
        if not role or key in seen:
            errors.append("candidate_evaluation_binding_role_duplicate")
        seen.add(key)
        identity = binding.get("identity")
        identity = identity if isinstance(identity, Mapping) else {}
        identity_keys = _IDENTITY_KEYS if lane_id else ("parent_run_id", "child_run_id")
        if any(not str(identity.get(name) or "").strip() for name in identity_keys):
            errors.append("candidate_evaluation_binding_identity_missing")
        required = binding.get("required") is True
        target = _contained(root, str(binding.get("artifact_ref") or ""))
        if target is None or not target.is_file():
            if required:
                errors.append("candidate_evaluation_binding_missing")
            continue
        raw = target.read_bytes()
        if binding.get("missing") is True:
            errors.append("candidate_evaluation_binding_unexpected_present")
        if str(binding.get("sha256") or "") != hashlib.sha256(raw).hexdigest():
            errors.append("candidate_evaluation_binding_digest_mismatch")
        try:
            expected_length = int(binding.get("byte_length"))
        except (TypeError, ValueError):
            expected_length = -1
        if expected_length != len(raw):
            errors.append("candidate_evaluation_binding_length_mismatch")
    if not bindings:
        errors.append("candidate_evaluation_bindings_missing")
    return payload, sorted(set(errors))


__all__ = [
    "CANDIDATE_EVALUATION_MANIFEST",
    "CANDIDATE_EVALUATION_MANIFEST_SCHEMA",
    "CandidateEvaluationManifestError",
    "EXPECTED_LANES",
    "build_candidate_evaluation_manifest",
    "emit_candidate_evaluation_manifest",
    "validate_candidate_evaluation_manifest",
]
