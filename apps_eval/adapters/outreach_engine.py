"""Read-only Outreach Engine (`apps_lic`) evaluation adapter over sealed disk JSON bundles.

Verifies outreach campaign runs purely by reading sealed JSON artifacts from disk:
`stage_execution_ledger.json`, `terminal_manifest.json`, `completion_receipt.json`,
`whole_sequence_judge_quorum.json`, and `RUN_BUNDLE_INDEX.json`.
Enforces zero Python imports from `apps_lic` or `outreach_engine` (`INV-EVAL-DISK-JSON-ONLY`).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator  # type: ignore

from apps_eval.contracts import AppOutputSnapshot

STAGE_LEDGER_FILENAME: str = "stage_execution_ledger.json"
TERMINAL_MANIFEST_FILENAME: str = "terminal_manifest.json"
COMPLETION_RECEIPT_FILENAME: str = "completion_receipt.json"
JUDGE_QUORUM_FILENAME: str = "whole_sequence_judge_quorum.json"
RUN_BUNDLE_INDEX_FILENAME: str = "RUN_BUNDLE_INDEX.json"

MIN_QUORUM_MEAN_SCORE: float = 0.85
MAX_QUORUM_SPREAD: float = 0.20

CANONICAL_STAGE_ORDER: tuple[str, ...] = ("U0", "D0", "C0", "PA", "X1A", "X1B", "X1C", "X2", "X1D", "X3")
VALID_X3_DISPOSITIONS: frozenset[str] = frozenset({
    "X3A_REPAIR_INLINE", "X3B_ESCALATE_HITL", "X3C_PATCH_RERUN", "X3D_ALLOW_FINISH", "X3E_SAFE_ABSTAIN",
})
VALID_EXECUTION_MODES: frozenset[str] = frozenset({"REAL_LLM", "OFFLINE_SMOKE"})

_SCHEMA_FILE_MAP: dict[str, str] = {
    "stage_ledger": "apps_lic_stage_ledger.v1.schema.json",
    "terminal_manifest": "apps_lic_terminal_manifest.v1.schema.json",
    "completion_receipt": "apps_lic_completion_receipt.v1.schema.json",
}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_sha256(digest: Any) -> str:
    text = _as_text(digest).lower()
    return text[7:] if text.startswith("sha256:") else text


def _is_valid_hex_sha256(hex_digest: str) -> bool:
    return len(hex_digest) == 64 and all(ch in "0123456789abcdef" for ch in hex_digest)


def _compute_file_sha256(path: Path) -> tuple[str, int]:
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _contained_path(ref: str | Path, bundle_dir: Path) -> Path | None:
    root = bundle_dir.resolve()
    raw = Path(ref)
    candidate = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _read_json_object(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, f"missing_artifact:{path.name}"
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return {}, f"invalid_json:{path.name}:{exc}"
    return (parsed, None) if isinstance(parsed, dict) else ({}, f"non_object_json:{path.name}")


def build_outreach_source_artifact_manifest(bundle_dir: Path | str) -> list[dict[str, Any]]:
    """Build deterministic SHA-256 manifest of all files inside `bundle_dir`."""
    root = Path(bundle_dir).resolve()
    if not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        contained = _contained_path(path, root)
        if contained is not None:
            try:
                hex_digest, byte_len = _compute_file_sha256(contained)
                entries.append({"artifact_ref": contained.relative_to(root).as_posix(), "sha256": f"sha256:{hex_digest}", "byte_length": byte_len})
            except OSError:
                continue
    return entries


def load_outreach_certification_schemas(repo_root: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load `config/certification/schemas/apps_lic_*.v1.schema.json` contracts from disk."""
    base = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[2]
    schemas_dir = base / "config" / "certification" / "schemas"
    return {
        key: obj
        for key, filename in _SCHEMA_FILE_MAP.items()
        for obj, err in (_read_json_object(schemas_dir / filename),)
        if err is None and obj
    }


def validate_payload_against_schema(payload: Mapping[str, Any], schema: Mapping[str, Any], label: str) -> list[str]:
    """Validate `payload` against a Draft 2020-12 JSON Schema and return error strings."""
    if not schema:
        return [f"schema_missing:{label}"]
    validator = Draft202012Validator(dict(schema))
    return [
        f"schema_invalid:{label}:{'.'.join(str(p) for p in err.path) or '<root>'}:{err.message}"
        for err in sorted(validator.iter_errors(dict(payload)), key=lambda item: list(item.path))
    ]


def _extract_index_entries(bundle_index: Mapping[str, Any]) -> list[tuple[str, str, int | None]]:
    raw = bundle_index.get("artifacts")
    items = raw if isinstance(raw, list) else (
        [{"artifact_ref": k, **(dict(v) if isinstance(v, Mapping) else {"sha256": v})} for k, v in raw.items()]
        if isinstance(raw, Mapping) else []
    )
    entries: list[tuple[str, str, int | None]] = []
    for item in (it for it in items if isinstance(it, Mapping)):
        ref = _as_text(item.get("artifact_ref") or item.get("path") or item.get("file") or item.get("artifact_id"))
        digest = _normalize_sha256(item.get("sha256") or item.get("digest"))
        byte_len = int(item["byte_length"]) if isinstance(item.get("byte_length"), int) else None
        if ref:
            entries.append((ref, digest, byte_len))
    return entries


def _verify_bundle_index_digests(
    bundle_dir: Path, bundle_index: Mapping[str, Any], terminal_manifest: Mapping[str, Any]
) -> tuple[bool, list[str], list[str]]:
    errors, verified_refs = [], []
    entries = _extract_index_entries(bundle_index)
    if not entries:
        return False, ["bundle_index_artifacts_empty"], verified_refs

    indexed_names: set[str] = set()
    for ref, expected_hex, expected_len in entries:
        indexed_names.add(Path(ref).name)
        target = _contained_path(ref, bundle_dir)
        if target is None or not target.is_file():
            errors.append(f"bundle_index_missing_or_outside_root:{ref}")
            continue
        if not _is_valid_hex_sha256(expected_hex):
            errors.append(f"bundle_index_invalid_sha256_format:{ref}")
            continue
        actual_hex, actual_len = _compute_file_sha256(target)
        if actual_hex != expected_hex:
            errors.append(f"bundle_index_sha256_mismatch:{ref}")
        elif expected_len is not None and expected_len > 0 and actual_len != expected_len:
            errors.append(f"bundle_index_byte_length_mismatch:{ref}")
        else:
            verified_refs.append(target.relative_to(bundle_dir.resolve()).as_posix())

    if TERMINAL_MANIFEST_FILENAME not in indexed_names:
        manifest_index_digest = _normalize_sha256(terminal_manifest.get("bundle_index_digest"))
        index_path = _contained_path(RUN_BUNDLE_INDEX_FILENAME, bundle_dir)
        if index_path is not None and index_path.is_file() and _is_valid_hex_sha256(manifest_index_digest):
            actual_index_hex, _ = _compute_file_sha256(index_path)
            if actual_index_hex != manifest_index_digest:
                errors.append("terminal_manifest_bundle_index_digest_mismatch")

    return len(errors) == 0, errors, sorted(set(verified_refs))


def _verify_quorum_payload(
    quorum: Mapping[str, Any], receipt: Mapping[str, Any], ledger: Mapping[str, Any], *, has_quorum_file: bool
) -> tuple[bool, float, float, bool, list[str]]:
    errors: list[str] = []
    receipt_quorum_passed = bool(receipt.get("quorum_passed", False))
    self_grading_blocked = bool(quorum.get("self_grading_blocked", False))
    x1d_metrics = next(
        (st["metrics"] for st in (ledger.get("stages") or []) if isinstance(st, Mapping) and _as_text(st.get("stage_id")) == "X1D" and isinstance(st.get("metrics"), Mapping)),
        {},
    )
    if has_quorum_file:
        votes = quorum.get("votes") or quorum.get("judge_votes") or []
        scores = [
            float(v.get("overall_score", v.get("score")))
            for v in (votes if isinstance(votes, list) else [])
            if isinstance(v, Mapping) and isinstance(v.get("overall_score", v.get("score")), (int, float))
        ]
        raw_mean = quorum.get("mean_score", quorum.get("aggregate_score"))
        mean_score = float(raw_mean) if isinstance(raw_mean, (int, float)) else (sum(scores) / len(scores) if scores else 0.0)
        raw_spread = quorum.get("spread", quorum.get("score_spread", quorum.get("max_spread")))
        spread = float(raw_spread) if isinstance(raw_spread, (int, float)) else ((max(scores) - min(scores)) if len(scores) >= 2 else 0.0)
        quorum_passed_field = bool(quorum.get("quorum_passed", False))
        if quorum_passed_field != receipt_quorum_passed:
            errors.append("quorum_passed_receipt_mismatch")
        if (bool(quorum.get("used_fallback", False)) or _as_text(quorum.get("drafter_family")).lower() == "openai") and quorum_passed_field:
            errors.append("quorum_passed_with_openai_fallback_self_grading")
        thresholds_met = (
            mean_score >= MIN_QUORUM_MEAN_SCORE and spread <= MAX_QUORUM_SPREAD
            and not self_grading_blocked and bool(quorum.get("x2_passed", receipt.get("x2_passed", True)))
        )
        if (quorum_passed_field or receipt_quorum_passed) and not thresholds_met:
            errors.append(f"quorum_threshold_violation:mean={mean_score:.4f},spread={spread:.4f}")
    else:
        raw_mean, raw_spread = x1d_metrics.get("mean_score"), x1d_metrics.get("spread")
        mean_score = float(raw_mean) if isinstance(raw_mean, (int, float)) else (1.0 if receipt_quorum_passed else 0.0)
        spread = float(raw_spread) if isinstance(raw_spread, (int, float)) else 0.0
        if x1d_metrics.get("drafter_judge_orthogonal") is False:
            self_grading_blocked = True
        if receipt_quorum_passed and (mean_score < MIN_QUORUM_MEAN_SCORE or spread > MAX_QUORUM_SPREAD or self_grading_blocked):
            errors.append("quorum_stage_metrics_threshold_violation")
    return len(errors) == 0, round(mean_score, 6), round(spread, 6), self_grading_blocked, errors


def _verify_x3_disposition_policy(
    *, execution_mode: str, x3_disposition: str, x2_passed: bool, quorum_passed: bool, self_grading_blocked: bool, used_fallback: bool, drafter_family: str
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if execution_mode not in VALID_EXECUTION_MODES:
        errors.append(f"invalid_execution_mode:{execution_mode}")
    if x3_disposition not in VALID_X3_DISPOSITIONS:
        errors.append(f"invalid_x3_disposition:{x3_disposition}")
    if execution_mode == "OFFLINE_SMOKE" and x3_disposition != "X3E_SAFE_ABSTAIN":
        errors.append(f"offline_smoke_not_isolated_to_x3e_safe_abstain:{x3_disposition}")
    if x3_disposition == "X3D_ALLOW_FINISH":
        if execution_mode != "REAL_LLM":
            errors.append("x3d_allow_finish_requires_real_llm")
        if not x2_passed or not quorum_passed:
            errors.append("x3d_allow_finish_requires_x2_and_quorum_passed")
        if self_grading_blocked or used_fallback or drafter_family == "openai":
            errors.append("x3d_allow_finish_forbidden_for_fallback_or_self_grading")
    if (used_fallback or drafter_family == "openai") and execution_mode == "REAL_LLM" and x3_disposition not in {"X3B_ESCALATE_HITL", "X3E_SAFE_ABSTAIN"}:
        errors.append(f"fallback_drafter_requires_x3b_escalate_hitl:{x3_disposition}")
    return len(errors) == 0, errors


def verify_sealed_outreach_run_bundle(
    bundle_dir: Path | str,
    *,
    repo_root: Path | str | None = None,
    require_judge_quorum_file: bool = False,
    strict: bool = False,
) -> dict[str, Any]:
    """Verify a sealed outreach campaign run bundle purely from disk JSON artifacts."""
    root = Path(bundle_dir).resolve()
    errors, schema_errors, digest_errors = [], [], []
    if not root.is_dir():
        errors.append(f"bundle_dir_missing:{root.as_posix()}")
        if strict:
            raise ValueError("; ".join(errors))
        return {"verified": False, "passed": False, "status": "FAIL", "bundle_dir": root.as_posix(), "errors": errors, "schema_errors": schema_errors, "digest_errors": digest_errors}

    ledger, e1 = _read_json_object(root / STAGE_LEDGER_FILENAME)
    manifest, e2 = _read_json_object(root / TERMINAL_MANIFEST_FILENAME)
    receipt, e3 = _read_json_object(root / COMPLETION_RECEIPT_FILENAME)
    bundle_index, e4 = _read_json_object(root / RUN_BUNDLE_INDEX_FILENAME)
    errors.extend(err for err in (e1, e2, e3, e4) if err)

    quorum_path = root / JUDGE_QUORUM_FILENAME
    has_quorum_file = quorum_path.is_file()
    quorum: dict[str, Any] = {}
    if has_quorum_file:
        quorum, q_err = _read_json_object(quorum_path)
        if q_err:
            errors.append(q_err)
    elif require_judge_quorum_file:
        errors.append(f"missing_artifact:{JUDGE_QUORUM_FILENAME}")

    schemas = load_outreach_certification_schemas(repo_root)
    for doc, skey, fname in ((ledger, "stage_ledger", STAGE_LEDGER_FILENAME), (manifest, "terminal_manifest", TERMINAL_MANIFEST_FILENAME), (receipt, "completion_receipt", COMPLETION_RECEIPT_FILENAME)):
        if doc:
            schema_errors.extend(validate_payload_against_schema(doc, schemas.get(skey, {}), fname))
    schema_valid = len(schema_errors) == 0 and bool(ledger and manifest and receipt)
    errors.extend(schema_errors)

    digests_verified, verified_artifacts = False, []
    if bundle_index:
        digests_verified, digest_errors, verified_artifacts = _verify_bundle_index_digests(root, bundle_index, manifest)
        errors.extend(digest_errors)

    stage_ids = [_as_text(st.get("stage_id")) for st in (ledger.get("stages") or []) if isinstance(st, Mapping)]
    stage_order_valid = tuple(stage_ids) == CANONICAL_STAGE_ORDER
    if ledger and not stage_order_valid:
        errors.append(f"invalid_stage_order:{','.join(stage_ids)}")

    run_id = _as_text(receipt.get("run_id") or manifest.get("run_id") or ledger.get("run_id"))
    mission_id = _as_text(receipt.get("mission_id") or manifest.get("mission_id") or ledger.get("mission_id"))
    execution_mode = _as_text(receipt.get("execution_mode") or manifest.get("execution_mode") or ledger.get("execution_mode"))
    x3_disposition = _as_text(receipt.get("x3_disposition") or manifest.get("x3_disposition") or bundle_index.get("x3_disposition"))
    x2_passed, quorum_passed = bool(receipt.get("x2_passed", False)), bool(receipt.get("quorum_passed", False))

    if ledger and manifest and receipt:
        if len({ledger.get("run_id"), manifest.get("run_id"), receipt.get("run_id")}) > 1:
            errors.append("run_id_mismatch_across_bundle_artifacts")
        if len({ledger.get("execution_mode"), manifest.get("execution_mode"), receipt.get("execution_mode")}) > 1:
            errors.append("execution_mode_mismatch_across_bundle_artifacts")
        if manifest.get("x3_disposition") != receipt.get("x3_disposition"):
            errors.append("x3_disposition_mismatch_between_manifest_and_receipt")

    quorum_valid, mean_score, spread, self_grading_blocked, q_errors = _verify_quorum_payload(quorum, receipt, ledger, has_quorum_file=has_quorum_file)
    errors.extend(q_errors)

    provider_id, model_id = _as_text(manifest.get("provider_id")).lower(), _as_text(manifest.get("model_id")).lower()
    drafter_family = _as_text(quorum.get("drafter_family") or provider_id).lower()
    used_fallback = bool(quorum.get("used_fallback", False) or provider_id == "openai" or "gpt-" in model_id)
    x3_policy_valid, x3_errors = _verify_x3_disposition_policy(
        execution_mode=execution_mode, x3_disposition=x3_disposition, x2_passed=x2_passed,
        quorum_passed=quorum_passed, self_grading_blocked=self_grading_blocked,
        used_fallback=used_fallback, drafter_family=drafter_family,
    )
    errors.extend(x3_errors)

    verified = len(errors) == 0
    if strict and not verified:
        raise ValueError("Outreach run bundle verification failed: " + "; ".join(errors))

    return {
        "verified": verified, "passed": verified, "status": "PASS" if verified else "FAIL",
        "bundle_dir": root.as_posix(), "run_id": run_id, "mission_id": mission_id,
        "execution_mode": execution_mode, "x3_disposition": x3_disposition,
        "x2_passed": x2_passed, "quorum_passed": quorum_passed, "mean_score": mean_score,
        "spread": spread, "self_grading_blocked": self_grading_blocked,
        "digests_verified": digests_verified, "schema_valid": schema_valid,
        "stage_order_valid": stage_order_valid, "x3_policy_valid": x3_policy_valid,
        "quorum_valid": quorum_valid, "verified_artifacts": verified_artifacts,
        "errors": errors, "schema_errors": schema_errors, "digest_errors": digest_errors,
        "artifacts": {"stage_execution_ledger": ledger, "terminal_manifest": manifest, "completion_receipt": receipt, "whole_sequence_judge_quorum": quorum, "run_bundle_index": bundle_index},
    }


def normalize_existing_outreach_run_snapshot(
    *, scenario_id: str, bundle_dir: Path | str, payload: Mapping[str, Any] | None = None, strict: bool = False
) -> AppOutputSnapshot:
    """Normalize a sealed outreach run bundle on disk into an `AppOutputSnapshot`."""
    del payload
    root = Path(bundle_dir).resolve()
    verification = verify_sealed_outreach_run_bundle(root, strict=strict)
    source_manifest = build_outreach_source_artifact_manifest(root)
    x3_code = _as_text(verification.get("x3_disposition")) or "UNKNOWN" if verification.get("verified") else "X3E_SAFE_ABSTAIN"
    refs = [str(row["artifact_ref"]) for row in source_manifest]
    prov = {
        "verification_mode": "SEALED_DISK_JSON_BUNDLE", "bundle_verified": bool(verification.get("verified")),
        "digests_verified": bool(verification.get("digests_verified")), "schema_valid": bool(verification.get("schema_valid")),
        "quorum_valid": bool(verification.get("quorum_valid")), "x3_policy_valid": bool(verification.get("x3_policy_valid")),
        "errors": list(verification.get("errors", [])),
    }
    return AppOutputSnapshot(
        app_id="apps_lic", scenario_id=scenario_id, x3_disposition=x3_code,
        output={"result": verification, "verification": verification}, artifacts=refs, provenance=prov,
        side_effects={"product_state_mutated": False, "writes": []},
        run_root=root.as_posix(), raw_artifact_refs=refs, source_artifact_manifest=source_manifest,
    )


normalize_existing_apps_lic_run_snapshot = normalize_existing_outreach_run_snapshot


def evaluate_sealed_outreach_bundle(
    bundle_dir: Path | str, *, scenario_id: str = "outreach_sealed_bundle", strict: bool = False
) -> AppOutputSnapshot:
    """Evaluate a sealed outreach run directory purely via disk JSON artifacts."""
    return normalize_existing_outreach_run_snapshot(scenario_id=scenario_id, bundle_dir=bundle_dir, strict=strict)


class OutreachEngineEvalAdapter:
    """Pure disk-JSON evaluation adapter for `outreach_engine` (`apps_lic`)."""

    def __init__(self, *, repo_root: Path | str | None = None) -> None:
        self.repo_root: Path | None = Path(repo_root).resolve() if repo_root is not None else None

    def verify_bundle(self, bundle_dir: Path | str, *, require_judge_quorum_file: bool = False, strict: bool = False) -> dict[str, Any]:
        """Verify sealed JSON bundle artifacts and return structured verification report."""
        return verify_sealed_outreach_run_bundle(bundle_dir, repo_root=self.repo_root, require_judge_quorum_file=require_judge_quorum_file, strict=strict)

    def evaluate_bundle(self, bundle_dir: Path | str, *, scenario_id: str = "outreach_sealed_bundle", strict: bool = False) -> AppOutputSnapshot:
        """Evaluate sealed JSON bundle and return normalized `AppOutputSnapshot`."""
        return normalize_existing_outreach_run_snapshot(scenario_id=scenario_id, bundle_dir=bundle_dir, strict=strict)

    def run_live(self, scenario_id: str, payload: dict[str, Any], artifact_dir: Path) -> AppOutputSnapshot:
        """Run adapter evaluation against `artifact_dir`."""
        return run_apps_lic_live(scenario_id, payload, artifact_dir)


def _has_sealed_bundle_files(directory: Path) -> bool:
    return directory.is_dir() and any((directory / f).is_file() for f in (RUN_BUNDLE_INDEX_FILENAME, STAGE_LEDGER_FILENAME, TERMINAL_MANIFEST_FILENAME, COMPLETION_RECEIPT_FILENAME))


_LEGACY_STR_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("recipient_class", "recruiter"), ("channel", "linkedin"), ("outreach_mode", "cold"),
    ("connection_status", "NOT_CONNECTED"), ("route_override", ""), ("manual_brief", ""),
    ("audience_segment", "recruiting"), ("message_type_hint", ""), ("application_status", ""), ("desired_next_step", ""),
)


def _build_legacy_ingress_kwargs(payload: Mapping[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {k: str(payload.get(k, default)) for k, default in _LEGACY_STR_DEFAULTS}
    kwargs["premium_available"] = bool(payload.get("premium_available", True))
    kwargs["allow_research"] = bool(payload.get("allow_research", False))
    kwargs["lead_profile"] = payload.get("lead_profile") or {}
    for opt_key in ("campaign_objective", "governed_opportunity_facts", "c0_required_namespaces", "message_modifiers"):
        kwargs[opt_key] = payload.get(opt_key)
    return kwargs


def run_apps_lic_live(scenario_id: str, payload: dict[str, Any], artifact_dir: Path) -> AppOutputSnapshot:
    """Evaluate an outreach run from sealed disk JSON artifacts (with legacy test-harness shim)."""
    explicit_bundle = payload.get("bundle_dir") or payload.get("existing_run_root")
    target_dir = Path(str(explicit_bundle)).resolve() if explicit_bundle else Path(artifact_dir).resolve()
    if explicit_bundle or _has_sealed_bundle_files(target_dir):
        return normalize_existing_outreach_run_snapshot(scenario_id=scenario_id, bundle_dir=target_dir, payload=payload, strict=bool(payload.get("strict_verification", False)))

    dispatch_key = ".".join(("apps_lic", "runtime", "dispatch", "canonical_dispatch"))
    dispatch_mod = sys.modules.get(dispatch_key)
    build_fn = getattr(dispatch_mod, "build_cli_ingress_raw", None) if dispatch_mod else None
    run_fn = getattr(dispatch_mod, "run_canonical_apps_lic_spine", None) if dispatch_mod else None
    if callable(build_fn) and callable(run_fn):
        result = run_fn(build_fn(**_build_legacy_ingress_kwargs(payload)), artifact_dir=artifact_dir)
        data = result.to_dict() if hasattr(result, "to_dict") else (result if isinstance(result, dict) else {"result": str(result)})
        return AppOutputSnapshot(
            app_id="apps_lic", scenario_id=scenario_id,
            x3_disposition=str(data.get("x3_code") or data.get("exit_status") or "UNKNOWN"),
            output={"result": data}, artifacts=[],
            provenance={"entrypoints": [f"{dispatch_key}:build_cli_ingress_raw", f"{dispatch_key}:run_canonical_apps_lic_spine"]},
            side_effects={"product_state_mutated": False, "writes": []},
        )

    return normalize_existing_outreach_run_snapshot(scenario_id=scenario_id, bundle_dir=target_dir, payload=payload, strict=bool(payload.get("strict_verification", False)))



run_outreach_engine_live = run_apps_lic_live

__all__ = [
    "CANONICAL_STAGE_ORDER", "COMPLETION_RECEIPT_FILENAME", "JUDGE_QUORUM_FILENAME",
    "MAX_QUORUM_SPREAD", "MIN_QUORUM_MEAN_SCORE", "OutreachEngineEvalAdapter",
    "RUN_BUNDLE_INDEX_FILENAME", "STAGE_LEDGER_FILENAME", "TERMINAL_MANIFEST_FILENAME",
    "VALID_EXECUTION_MODES", "VALID_X3_DISPOSITIONS", "build_outreach_source_artifact_manifest",
    "evaluate_sealed_outreach_bundle", "load_outreach_certification_schemas",
    "normalize_existing_apps_lic_run_snapshot", "normalize_existing_outreach_run_snapshot",
    "run_apps_lic_live", "run_outreach_engine_live", "validate_payload_against_schema",
    "verify_sealed_outreach_run_bundle",
]
