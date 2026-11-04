"""Deterministic W4 terminal closeout for blocked historical apps_rg runs.

The module is intentionally stdlib-only at import time.  It consumes the
sealed W0-W3 replay chain, preserves the source run byte-for-byte, records the
historical invalid authorization/UWG action without repeating it, and emits a
new ``TERMINAL_NON_PRODUCT`` closeout under the replay output root.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


W4_COMPLETION_SCHEMA = "apps_rg.terminal_closeout_replay_completion.v1"
W4_COMPLETION_FILENAME = "w4_completion_receipt.json"
W4_LEDGER_SCHEMA = "apps_rg.post_runtime_terminal_stage_ledger.v1"
W4_LEDGER_FILENAME = "terminal_stage_ledger.json"
W4_LEDGER_SEAL_SCHEMA = "apps_rg.post_runtime_terminal_stage_ledger_seal.v1"
W4_LEDGER_SEAL_FILENAME = "terminal_stage_ledger_seal.json"
W4_TRANSITION_SCHEMA = "apps_rg.terminal_non_product_transition.v1"
W4_TRANSITION_FILENAME = "terminal_non_product_transition_receipt.json"
W4_TERMINAL_MANIFEST_SCHEMA = "apps_rg.terminal_non_product_manifest.v1"
W4_TERMINAL_MANIFEST_FILENAME = "terminal_non_product_manifest.json"
W4_TERMINAL_SEAL_SCHEMA = "apps_rg.terminal_non_product_manifest_seal.v1"
W4_TERMINAL_SEAL_FILENAME = "terminal_non_product_manifest_seal.json"
W4_TELEMETRY_SCHEMA = "apps_rg.local_post_runtime_failure_event.v1"
W4_TELEMETRY_FILENAME = "local_failure_telemetry.jsonl"
W4_TELEMETRY_SUMMARY_SCHEMA = "apps_rg.local_failure_telemetry_summary.v1"
W4_TELEMETRY_SUMMARY_FILENAME = "local_failure_telemetry_summary.json"
W4_PACKAGE_SEAL_SCHEMA = "apps_rg.terminal_closeout_package_seal.v1"
W4_PACKAGE_SEAL_FILENAME = "w4_terminal_closeout_package_seal.json"
W2_SUPERSESSION_SCHEMA = "apps_rg.eval_package_supersession_manifest.v1"
W3_CALIBRATION_SCHEMA = "apps_rg.l6_judge_human_calibration_status.v1"
W3_CALIBRATION_FILENAME = "l6_judge_human_calibration_status.json"

TERMINAL_OUTCOME = "BLOCKED_NON_PRODUCT"
TERMINAL_STAGE_ID = "TERMINAL_NON_PRODUCT"
ALLOWED_STAGE_STATUSES = frozenset(
    {"PASS", "FAIL", "BLOCKED", "SKIPPED_WITH_CAUSE"}
)
REQUIRED_ZERO_ACTIVITY_COUNTERS = frozenset(
    {
        "blocked_import_attempts",
        "embedding_calls",
        "judge_calls",
        "model_calls",
        "network_attempts",
        "provider_calls",
        "subprocess_attempts",
    }
)
EXPECTED_SOURCE_STAGE_IDS: tuple[str, ...] = (
    "FRESH_PREFLIGHT",
    "APPS_RESEARCH_U0",
    "APPS_RESEARCH_RUNTIME",
    "APPS_RESEARCH_EXIT",
    "HANDOFF_BUNDLE_COMMIT",
    "APPS_RG_U0",
    "APPS_RG_L1",
    "APPS_RG_L0",
    "APPS_RG_C0",
    "APPS_RG_PA",
    "APPS_RG_L2",
    "X1_REVIEW",
    "X2_AGGREGATION",
    "X3_DISPOSITION",
    "PRODUCT_ELIGIBILITY",
)
EXPECTED_TERMINAL_STAGE_IDS: tuple[str, ...] = (
    *EXPECTED_SOURCE_STAGE_IDS,
    "UWG_COMMIT",
    "POST_RUNTIME_W0_FIREWALL",
    "POST_RUNTIME_W1_AUTHORITY",
    "APPS_EVAL",
    "L6_OBSERVABILITY",
    TERMINAL_STAGE_ID,
)
EXPECTED_LANES: tuple[str, ...] = (
    "competencies",
    "executive_summary",
    "ey_bullets",
    "ey_narrative",
    "headline",
    "ibm_bullets",
    "ibm_narrative",
    "insurtech_bullets",
    "insurtech_narrative",
    "unify_bullets",
    "unify_narrative",
)
REQUIRED_PACKAGE_ARTIFACT_ROLES = frozenset(
    {
        "local_failure_telemetry",
        "local_failure_telemetry_summary",
        "terminal_non_product_manifest",
        "terminal_non_product_manifest_seal",
        "terminal_stage_ledger",
        "terminal_stage_ledger_seal",
        "terminal_transition",
    }
)


class TerminalCloseoutReplayError(RuntimeError):
    """Raised when the saved evidence cannot support a safe W4 closeout."""


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _contained(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    parent = root.resolve()
    return resolved == parent or parent in resolved.parents


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise TerminalCloseoutReplayError(f"{label}_unreadable:{path}") from exc
    if not isinstance(payload, dict):
        raise TerminalCloseoutReplayError(f"{label}_not_object:{path}")
    return payload


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TerminalCloseoutReplayError(f"{label}_unreadable:{path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError) as exc:
            raise TerminalCloseoutReplayError(
                f"{label}_invalid_json:{line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise TerminalCloseoutReplayError(
                f"{label}_row_not_object:{line_number}"
            )
        rows.append(row)
    return rows


def _atomic_write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:12]}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    return _atomic_write_text(
        path,
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
    )


def _atomic_write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    return _atomic_write_text(
        path,
        "".join(
            json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
    )


def _semantic_digest_valid(payload: Mapping[str, Any]) -> bool:
    body = dict(payload)
    observed = str(body.pop("semantic_digest", "") or "")
    return bool(observed) and observed == _canonical_digest(body)


def _binding(path: Path, *, namespace: str, root: Path) -> dict[str, Any]:
    target = path.resolve(strict=True)
    parent = root.resolve()
    if not _contained(target, parent):
        raise TerminalCloseoutReplayError(
            f"binding_outside_namespace:{namespace}:{target}"
        )
    return {
        "artifact_namespace": namespace,
        "artifact_ref": target.relative_to(parent).as_posix(),
        "byte_length": target.stat().st_size,
        "sha256": _sha256_file(target),
    }


def _resolve_binding(
    binding: Any,
    *,
    roots: Mapping[str, Path],
    label: str,
) -> Path:
    if not isinstance(binding, Mapping):
        raise TerminalCloseoutReplayError(f"{label}_binding_missing")
    namespace = str(binding.get("artifact_namespace") or "")
    root = roots.get(namespace)
    if root is None:
        raise TerminalCloseoutReplayError(f"{label}_namespace_invalid:{namespace}")
    ref = str(binding.get("artifact_ref") or "").strip()
    if not ref:
        raise TerminalCloseoutReplayError(f"{label}_ref_missing")
    path = (root / ref).resolve()
    if not _contained(path, root):
        raise TerminalCloseoutReplayError(f"{label}_outside_root:{path}")
    if not path.is_file():
        raise TerminalCloseoutReplayError(f"{label}_missing:{path}")
    if type(binding.get("byte_length")) is not int or int(
        binding["byte_length"]
    ) != path.stat().st_size:
        raise TerminalCloseoutReplayError(f"{label}_length_mismatch:{path}")
    if str(binding.get("sha256") or "") != _sha256_file(path):
        raise TerminalCloseoutReplayError(f"{label}_digest_mismatch:{path}")
    return path


def _resolve_relative_file(root: Path, ref: Any, *, label: str) -> Path:
    text = str(ref or "").strip()
    if not text:
        raise TerminalCloseoutReplayError(f"{label}_ref_missing")
    path = (root / text).resolve()
    if not _contained(path, root):
        raise TerminalCloseoutReplayError(f"{label}_outside_root:{path}")
    if not path.is_file():
        raise TerminalCloseoutReplayError(f"{label}_missing:{path}")
    return path


def _relative_binding_valid(
    binding: Any,
    *,
    root: Path,
    expected: Path,
) -> bool:
    if not isinstance(binding, Mapping):
        return False
    try:
        path = _resolve_relative_file(
            root,
            binding.get("artifact_ref"),
            label="relative_binding",
        )
    except TerminalCloseoutReplayError:
        return False
    return (
        path == expected.resolve()
        and type(binding.get("byte_length")) is int
        and binding.get("byte_length") == path.stat().st_size
        and binding.get("sha256") == _sha256_file(path)
    )


def _require_checks(checks: Mapping[str, bool], *, label: str) -> None:
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise TerminalCloseoutReplayError(f"{label}:" + ",".join(failed))


def _zero_counters(payload: Mapping[str, Any]) -> bool:
    raw = payload.get("attempt_counters")
    counters = dict(raw) if isinstance(raw, Mapping) else {}
    return REQUIRED_ZERO_ACTIVITY_COUNTERS.issubset(counters) and all(
        type(value) is int and value == 0 for value in counters.values()
    )


def _validate_guard(
    payload: Mapping[str, Any],
    *,
    wave: str,
    source_run_id: str,
    source_manifest_sha256: str,
    completion: Mapping[str, Any] | None,
    expected_activity: Mapping[str, bool],
) -> None:
    checks = {
        "schema_exact": payload.get("schema_version")
        == "apps_rg.post_runtime_zero_provider_replay.v1",
        "wave_exact": payload.get("wave") == wave,
        "status_pass": payload.get("status") == "PASS"
        and payload.get("scope_complete") is True,
        "semantic_digest_valid": _semantic_digest_valid(payload),
        "source_bound": payload.get("source_run_id") == source_run_id,
        "source_manifest_continuity": payload.get("source_manifest_sha256")
        == source_manifest_sha256,
        "source_unchanged": payload.get("source_unchanged") is True,
        "zero_activity_counters": _zero_counters(payload),
        "clean_import_state": payload.get("clean_import_state") is True,
        "activity_exact": all(
            payload.get(name) is expected
            for name, expected in expected_activity.items()
        ),
    }
    if completion is not None:
        checks["completion_digest_bound"] = payload.get(
            "operation_completion_semantic_digest"
        ) == completion.get("semantic_digest")
        checks["completion_status_bound"] = payload.get(
            "operation_completion_status"
        ) == "PASS"
    _require_checks(checks, label=f"{wave.lower()}_guard_invalid")


def _verify_manifest_rows(
    rows: Any,
    *,
    roots: Mapping[str, Path],
    label: str,
    default_namespace: str = "",
) -> tuple[bool, list[str], dict[str, str]]:
    errors: list[str] = []
    observed: dict[str, str] = {}
    if not isinstance(rows, list) or not rows:
        return False, [f"{label}_artifacts_missing"], observed
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"{label}_artifact_not_object:{index}")
            continue
        role = str(row.get("artifact_role") or "")
        if not role:
            errors.append(f"{label}_artifact_role_missing:{index}")
            continue
        if role in seen:
            errors.append(f"{label}_artifact_role_duplicate:{role}")
        seen.add(role)
        resolved_row = dict(row)
        if not resolved_row.get("artifact_namespace") and default_namespace:
            resolved_row["artifact_namespace"] = default_namespace
        try:
            path = _resolve_binding(
                resolved_row,
                roots=roots,
                label=f"{label}:{role}",
            )
        except TerminalCloseoutReplayError as exc:
            errors.append(str(exc))
            continue
        observed[role] = _sha256_file(path)
    return not errors, errors, observed


def _validate_prior_chain(
    *,
    source: Path,
    output: Path,
) -> dict[str, Any]:
    replay_root = output.parent
    source_run_id = source.name
    roots = {"source_run": source, "replay_root": replay_root, "w4": output}

    w0_path = replay_root / "w0_zero_provider_preflight_receipt.json"
    w0 = _read_json(w0_path, label="w0_preflight")
    _require_checks(
        {
            "schema_exact": w0.get("schema_version")
            == "apps_rg.post_runtime_zero_provider_preflight.v1",
            "status_pass": w0.get("status") == "PASS"
            and w0.get("w0_scope_complete") is True,
            "semantic_digest_valid": _semantic_digest_valid(w0),
            "source_bound": w0.get("source_run_id") == source_run_id,
            "source_unchanged": w0.get("source_unchanged") is True,
            "zero_activity_counters": _zero_counters(w0),
            "clean_import_state": w0.get("clean_import_state") is True,
        },
        label="w0_evidence_invalid",
    )

    w1_dir = replay_root / "w1"
    w1_completion_path = w1_dir / "w1_completion_receipt.json"
    w1_reconciliation_path = w1_dir / "w1_authoritative_reconciliation.json"
    w1_correction_path = w1_dir / "w1_authorization_correction_receipt.json"
    w1_parallel_path = w1_dir / "w1_l0_parallel_replay_proof.json"
    w1_guard_path = w1_dir / "w1_zero_provider_guard_receipt.json"
    w1_completion = _read_json(w1_completion_path, label="w1_completion")
    w1_reconciliation = _read_json(
        w1_reconciliation_path, label="w1_reconciliation"
    )
    w1_correction = _read_json(w1_correction_path, label="w1_correction")
    w1_parallel = _read_json(w1_parallel_path, label="w1_parallel")
    w1_guard = _read_json(w1_guard_path, label="w1_guard")
    x3_codes = w1_reconciliation.get("authoritative_x3_codes")
    x3_codes = dict(x3_codes) if isinstance(x3_codes, Mapping) else {}
    _require_checks(
        {
            "completion_schema_exact": w1_completion.get("schema_version")
            == "apps_rg.authority_reconciliation_completion.v1",
            "completion_pass": w1_completion.get("status") == "PASS"
            and w1_completion.get("scope_complete") is True,
            "completion_digest_valid": _semantic_digest_valid(w1_completion),
            "completion_source_bound": w1_completion.get("source_run_id")
            == source_run_id,
            "completion_denies_product": w1_completion.get(
                "product_authorized"
            )
            is False
            and w1_completion.get("pipeline_complete") is False,
            "correction_schema_exact": w1_correction.get("schema_version")
            == "apps_rg.authorization_correction.v1",
            "correction_digest_valid": _semantic_digest_valid(w1_correction),
            "correction_source_bound": w1_correction.get("source_run_id")
            == source_run_id,
            "correction_denies_product": w1_correction.get(
                "corrected_product_authorized"
            )
            is False
            and w1_correction.get("corrected_pipeline_complete") is False
            and w1_correction.get("correction_disposition")
            == "SUPERSEDED_INVALID_AUTHORITY",
            "reconciliation_schema_exact": w1_reconciliation.get(
                "schema_version"
            )
            == "apps_rg.authority_reconciliation.v1",
            "reconciliation_digest_valid": _semantic_digest_valid(
                w1_reconciliation
            ),
            "reconciliation_source_bound": w1_reconciliation.get(
                "source_run_id"
            )
            == source_run_id,
            "reconciliation_blocks_all_lanes": w1_reconciliation.get(
                "status"
            )
            == "BLOCKED"
            and w1_reconciliation.get("authorized_lane_count") == 0
            and w1_reconciliation.get("blocked_lane_count") == len(EXPECTED_LANES)
            and set(x3_codes) == set(EXPECTED_LANES)
            and all(code == "X3A_DENY_REROUTE" for code in x3_codes.values()),
            "parallel_replay_pass": w1_parallel.get("status") == "PASS"
            and w1_parallel.get("parallel_overlap_proven") is True
            and w1_parallel.get("provider_or_model_execution") is False,
            "parallel_digest_valid": _semantic_digest_valid(w1_parallel),
        },
        label="w1_evidence_invalid",
    )
    _validate_guard(
        w1_guard,
        wave="W1",
        source_run_id=source_run_id,
        source_manifest_sha256=str(w0["source_manifest_sha256"]),
        completion=w1_completion,
        expected_activity={
            "apps_eval_executed": False,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
    )

    w2_dir = replay_root / "w2"
    w2_completion_path = w2_dir / "w2_completion_receipt.json"
    w2_guard_path = w2_dir / "w2_zero_provider_guard_receipt.json"
    w2_completion = _read_json(w2_completion_path, label="w2_completion")
    w2_guard = _read_json(w2_guard_path, label="w2_guard")
    _require_checks(
        {
            "schema_exact": w2_completion.get("schema_version")
            == "apps_rg.apps_eval_replay_completion.v1",
            "completion_pass": w2_completion.get("status") == "PASS"
            and w2_completion.get("scope_complete") is True,
            "semantic_digest_valid": _semantic_digest_valid(w2_completion),
            "source_bound": w2_completion.get("source_run_id") == source_run_id,
            "authority_denied": w2_completion.get("product_authorized") is False
            and w2_completion.get("pipeline_complete") is False,
            "eval_complete_fail": w2_completion.get("eval_execution_complete")
            is True
            and w2_completion.get("eval_verdict") == "fail"
            and w2_completion.get("release_blocked") is True,
            "w3_authorized": w2_completion.get("w3_authorized") is True,
        },
        label="w2_evidence_invalid",
    )
    _validate_guard(
        w2_guard,
        wave="W2",
        source_run_id=source_run_id,
        source_manifest_sha256=str(w0["source_manifest_sha256"]),
        completion=w2_completion,
        expected_activity={
            "apps_eval_executed": True,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
    )
    eval_record_path = _resolve_relative_file(
        w2_dir,
        (w2_completion.get("eval_record") or {}).get("artifact_ref"),
        label="w2_eval_record",
    )
    eval_record_binding = w2_completion.get("eval_record") or {}
    if _sha256_file(eval_record_path) != eval_record_binding.get("sha256"):
        raise TerminalCloseoutReplayError("w2_eval_record_digest_mismatch")
    eval_record = _read_json(eval_record_path, label="w2_eval_record")
    eval_record_id = str(eval_record.get("record_id") or "")
    _require_checks(
        {
            "record_id_present": bool(eval_record_id),
            "completion_record_id_matches": w2_completion.get("record_id")
            == eval_record_id,
            "eval_execution_complete": eval_record.get(
                "eval_execution_complete"
            )
            is True,
            "eval_verdict_fail": eval_record.get("eval_verdict") == "fail",
            "release_blocked": eval_record.get("release_blocked") is True,
        },
        label="w2_eval_record_invalid",
    )
    eval_seal_path = _resolve_relative_file(
        w2_dir,
        (w2_completion.get("eval_package_seal") or {}).get("artifact_ref"),
        label="w2_eval_seal",
    )
    if _sha256_file(eval_seal_path) != (
        w2_completion.get("eval_package_seal") or {}
    ).get("sha256"):
        raise TerminalCloseoutReplayError("w2_eval_seal_digest_mismatch")
    w2_supersession_path = _resolve_relative_file(
        w2_dir,
        (
            w2_completion.get("eval_package_supersession_manifest") or {}
        ).get("artifact_ref"),
        label="w2_eval_package_supersession_manifest",
    )
    if _sha256_file(w2_supersession_path) != (
        w2_completion.get("eval_package_supersession_manifest") or {}
    ).get("sha256"):
        raise TerminalCloseoutReplayError(
            "w2_eval_package_supersession_digest_mismatch"
        )
    w2_supersession = _read_json(
        w2_supersession_path,
        label="w2_eval_package_supersession_manifest",
    )
    _require_checks(
        {
            "schema_exact": w2_supersession.get("schema_version")
            == W2_SUPERSESSION_SCHEMA,
            "semantic_digest_valid": _semantic_digest_valid(w2_supersession),
            "status_pass": w2_supersession.get("status") == "PASS",
            "authoritative_record_exact": w2_supersession.get(
                "authoritative_record_id"
            )
            == eval_record_id,
            "canonical_package_exact": w2_supersession.get(
                "canonical_package_count"
            )
            == 1
            and w2_supersession.get("canonical_package_ids")
            == [eval_record_id],
            "superseded_packages_recoverable": w2_supersession.get(
                "destructive_delete_performed"
            )
            is False
            and w2_supersession.get("packages_recoverable") is True,
        },
        label="w2_eval_package_supersession_invalid",
    )

    w3_dir = replay_root / "w3"
    w3_completion_path = w3_dir / "w3_completion_receipt.json"
    w3_guard_path = w3_dir / "w3_zero_provider_guard_receipt.json"
    w3_seal_path = w3_dir / "w3_l6_shadow_package_seal.json"
    w3_bindings_path = w3_dir / "l6_section_apps_eval_bindings.json"
    w3_closure_path = w3_dir / "l6_apps_eval_binding_closure_receipt.json"
    w3_calibration_path = w3_dir / W3_CALIBRATION_FILENAME
    w3_completion = _read_json(w3_completion_path, label="w3_completion")
    w3_guard = _read_json(w3_guard_path, label="w3_guard")
    w3_seal = _read_json(w3_seal_path, label="w3_package_seal")
    w3_bindings = _read_json(w3_bindings_path, label="w3_bindings")
    w3_closure = _read_json(w3_closure_path, label="w3_closure")
    w3_calibration = _read_json(
        w3_calibration_path,
        label="w3_calibration",
    )
    w3_summary = w3_completion.get("section_summary")
    w3_summary = dict(w3_summary) if isinstance(w3_summary, Mapping) else {}
    w3_binding_rows = w3_bindings.get("bindings")
    w3_binding_rows = (
        list(w3_binding_rows) if isinstance(w3_binding_rows, list) else []
    )
    w3_binding_ids = [
        str(row.get("section_id") or "")
        for row in w3_binding_rows
        if isinstance(row, Mapping)
    ]
    _require_checks(
        {
            "schema_exact": w3_completion.get("schema_version")
            == "apps_rg.l6_shadow_replay_completion.v1",
            "completion_pass": w3_completion.get("status") == "PASS"
            and w3_completion.get("scope_complete") is True,
            "semantic_digest_valid": _semantic_digest_valid(w3_completion),
            "source_bound": w3_completion.get("source_run_id") == source_run_id,
            "record_chain_exact": w3_completion.get("record_id")
            == eval_record_id
            and w3_seal.get("record_id") == eval_record_id
            and w3_bindings.get("eval_record_id") == eval_record_id,
            "authority_denied": w3_completion.get("product_authorized") is False
            and w3_completion.get("pipeline_complete") is False,
            "observability_complete": w3_completion.get(
                "l6_execution_complete"
            )
            is True,
            "observed_failure_explicit": w3_completion.get(
                "l6_shadow_observability_verdict"
            )
            == "fail"
            and w3_completion.get("binding_closure_status") == "FAIL"
            and w3_completion.get("release_blocked") is True,
            "no_false_binding": w3_completion.get("apps_eval_rows_bound")
            is False,
            "all_lanes_inspected": w3_summary.get("sections_total")
            == len(EXPECTED_LANES)
            and w3_summary.get("sections_bound") == 0
            and set(w3_summary.get("observed_lane_ids") or [])
            == set(EXPECTED_LANES),
            "source_evidence_availability_exact": (
                int(w3_summary.get("sections_source_evidence_available") or 0)
                + int(
                    w3_summary.get("sections_source_evidence_unavailable") or 0
                )
                == len(EXPECTED_LANES)
                and set(
                    (
                        w3_summary.get("source_evidence_status_by_section")
                        or {}
                    ).values()
                )
                <= {
                    "AVAILABLE_SOURCE_EVIDENCE",
                    "UNAVAILABLE_SOURCE_EVIDENCE",
                }
            ),
            "w4_authorized": w3_completion.get("w4_authorized") is True,
            "bindings_digest_valid": _semantic_digest_valid(w3_bindings),
            "binding_rows_exact": len(w3_binding_rows) == len(EXPECTED_LANES)
            and len(w3_binding_ids) == len(w3_binding_rows)
            and set(w3_binding_ids) == set(EXPECTED_LANES)
            and len(set(w3_binding_ids)) == len(w3_binding_ids)
            and all(
                isinstance(row, Mapping)
                and row.get("binding_status")
                in {"PARITY_FAIL", "LEGACY_PACKAGE_ADVISORY"}
                and row.get("evidence_class") == "CONTRACT_ONLY_ADVISORY"
                and row.get("source_evidence_status")
                in {
                    "AVAILABLE_SOURCE_EVIDENCE",
                    "UNAVAILABLE_SOURCE_EVIDENCE",
                }
                and (
                    row.get("source_evidence_status")
                    != "UNAVAILABLE_SOURCE_EVIDENCE"
                    or row.get("binding_status") != "BOUND_PASS"
                )
                for row in w3_binding_rows
            ),
            "closure_digest_valid": _semantic_digest_valid(w3_closure),
            "closure_fail_exact": w3_closure.get("binding_closure_status")
            == "FAIL"
            and w3_closure.get("apps_eval_rows_bound") is False,
            "closure_availability_contract": (
                (w3_closure.get("checks") or {}).get(
                    "source_evidence_availability_classified"
                )
                is True
                and (w3_closure.get("checks") or {}).get(
                    "unavailable_source_evidence_never_bound"
                )
                is True
                and w3_closure.get("unavailable_source_evidence_count")
                == w3_summary.get("sections_source_evidence_unavailable")
            ),
            "calibration_schema_exact": w3_calibration.get("schema_version")
            == W3_CALIBRATION_SCHEMA,
            "calibration_digest_valid": _semantic_digest_valid(w3_calibration),
            "calibration_not_measured_exact": w3_calibration.get(
                "calibration_status"
            )
            == "NOT_MEASURED"
            and w3_calibration.get("human_labels_present") is False
            and w3_calibration.get("n_calibration_samples") == 0
            and w3_calibration.get("spearman_rho") is None
            and w3_calibration.get("p_value") is None
            and w3_calibration.get("informational_only") is True
            and w3_calibration.get("required_for_exit") is False
            and w3_calibration.get("release_authority_effect") == "NONE",
            "completion_calibration_exact": w3_completion.get(
                "calibration_status"
            )
            == "NOT_MEASURED"
            and w3_completion.get("human_labels_present") is False
            and w3_completion.get("n_calibration_samples") == 0
            and w3_completion.get("calibration_informational_only") is True
            and w3_completion.get("calibration_required_for_exit") is False,
            "package_seal_binding_valid": _relative_binding_valid(
                w3_completion.get("w3_package_seal"),
                root=w3_dir,
                expected=w3_seal_path,
            ),
            "bindings_binding_valid": _relative_binding_valid(
                w3_completion.get("l6_section_apps_eval_bindings"),
                root=w3_dir,
                expected=w3_bindings_path,
            ),
            "closure_binding_valid": _relative_binding_valid(
                w3_completion.get("l6_apps_eval_binding_closure"),
                root=w3_dir,
                expected=w3_closure_path,
            ),
            "calibration_binding_valid": _relative_binding_valid(
                w3_completion.get("l6_judge_human_calibration_status"),
                root=w3_dir,
                expected=w3_calibration_path,
            ),
        },
        label="w3_evidence_invalid",
    )
    _validate_guard(
        w3_guard,
        wave="W3",
        source_run_id=source_run_id,
        source_manifest_sha256=str(w0["source_manifest_sha256"]),
        completion=w3_completion,
        expected_activity={
            "apps_eval_executed": False,
            "l6_executed": True,
            "uwg_operation_attempted": False,
        },
    )
    w3_seal_body = {
        key: value for key, value in w3_seal.items() if key != "manifest_sha256"
    }
    seal_valid, seal_errors, _ = _verify_manifest_rows(
        w3_seal.get("artifacts"),
        roots={"w4": w3_dir},
        label="w3_package_seal",
        default_namespace="w4",
    )
    w3_seal_roles = {
        str(row.get("artifact_role") or "")
        for row in (w3_seal.get("artifacts") or [])
        if isinstance(row, Mapping)
    }
    required_w3_seal_roles = {
        "projection_l6_shadow_bridge",
        "l6_section_apps_eval_bindings",
        "l6_apps_eval_binding_closure",
        "l6_judge_human_calibration_status",
        *(f"{lane}_binding" for lane in EXPECTED_LANES),
    }
    _require_checks(
        {
            "schema_exact": w3_seal.get("schema_version")
            == "apps_rg.l6_shadow_replay_package_seal.v1",
            "status_pass": w3_seal.get("status") == "PASS",
            "manifest_digest_valid": w3_seal.get("manifest_sha256")
            == _canonical_digest(w3_seal_body),
            "artifact_count_exact": w3_seal.get("artifact_count")
            == len(w3_seal.get("artifacts") or []),
            "all_artifacts_valid": seal_valid and not seal_errors,
            "required_roles_present": required_w3_seal_roles
            <= w3_seal_roles,
        },
        label="w3_package_seal_invalid",
    )

    source_ledger_path = source / "e2e_stage_ledger.json"
    source_ledger = _read_json(source_ledger_path, label="source_stage_ledger")
    source_entries = source_ledger.get("entries")
    if not isinstance(source_entries, list):
        raise TerminalCloseoutReplayError("source_stage_ledger_entries_missing")
    observed_ids = [str(item.get("stage_id") or "") for item in source_entries]
    _require_checks(
        {
            "schema_exact": source_ledger.get("schema_version")
            == "apps_rg.e2e_stage_ledger.v2",
            "source_stages_exact": observed_ids == list(EXPECTED_SOURCE_STAGE_IDS),
            "source_sequences_exact": [item.get("sequence") for item in source_entries]
            == list(range(len(EXPECTED_SOURCE_STAGE_IDS))),
            "historical_statuses_exact": all(
                item.get("status") == "PASS" for item in source_entries
            ),
        },
        label="source_stage_ledger_invalid",
    )
    source_receipt_paths: dict[str, Path] = {}
    for entry in source_entries:
        stage_id = str(entry.get("stage_id") or "")
        receipt = _resolve_relative_file(
            source,
            entry.get("authoritative_receipt_ref"),
            label=f"source_ledger_receipt:{stage_id}",
        )
        if _sha256_file(receipt) != entry.get("authoritative_receipt_sha256"):
            raise TerminalCloseoutReplayError(
                f"source_ledger_receipt_digest_mismatch:{stage_id}"
            )
        source_receipt_paths[stage_id] = receipt

    uwg_path = source / "uwg_commit_receipt.json"
    product_authorization_path = source / "apps_rg_product_authorization_receipt.json"
    uwg = _read_json(uwg_path, label="historical_uwg_commit")
    product_authorization = _read_json(
        product_authorization_path, label="historical_product_authorization"
    )
    _require_checks(
        {
            "historical_uwg_schema_exact": uwg.get("schema_version")
            == "L4-UWG-1.0.0",
            "historical_uwg_commit_observed": uwg.get("commit_status")
            == "COMMITTED",
            "historical_product_authorization_schema_exact": (
                product_authorization.get("schema_version")
                == "apps_rg.product_authorization_receipt.v1"
            ),
            "historical_product_authorization_observed": product_authorization.get(
                "authorized"
            )
            is True,
            "historical_authorization_superseded": w1_correction.get(
                "original_authorized_claim"
            )
            is True
            and w1_correction.get("correction_disposition")
            == "SUPERSEDED_INVALID_AUTHORITY",
        },
        label="historical_authority_evidence_invalid",
    )

    return {
        "roots": roots,
        "replay_root": replay_root,
        "w0": w0,
        "w0_path": w0_path,
        "w1_completion": w1_completion,
        "w1_completion_path": w1_completion_path,
        "w1_reconciliation": w1_reconciliation,
        "w1_reconciliation_path": w1_reconciliation_path,
        "w1_correction": w1_correction,
        "w1_correction_path": w1_correction_path,
        "w1_parallel_path": w1_parallel_path,
        "w1_guard_path": w1_guard_path,
        "w2_completion": w2_completion,
        "w2_completion_path": w2_completion_path,
        "w2_guard_path": w2_guard_path,
        "eval_record": eval_record,
        "eval_record_path": eval_record_path,
        "eval_seal_path": eval_seal_path,
        "w2_supersession_path": w2_supersession_path,
        "w3_completion": w3_completion,
        "w3_completion_path": w3_completion_path,
        "w3_guard_path": w3_guard_path,
        "w3_seal_path": w3_seal_path,
        "w3_bindings": w3_bindings,
        "w3_bindings_path": w3_bindings_path,
        "w3_closure_path": w3_closure_path,
        "w3_calibration": w3_calibration,
        "w3_calibration_path": w3_calibration_path,
        "source_ledger": source_ledger,
        "source_ledger_path": source_ledger_path,
        "source_receipt_paths": source_receipt_paths,
        "uwg_path": uwg_path,
        "product_authorization_path": product_authorization_path,
    }


def _role_binding(role: str, binding: Mapping[str, Any]) -> dict[str, Any]:
    return {"artifact_role": role, **dict(binding)}


def _deduplicate_bindings(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("artifact_namespace") or ""),
            str(row.get("artifact_ref") or ""),
        )
        unique.setdefault(key, dict(row))
    return [unique[key] for key in sorted(unique)]


def _terminal_state() -> dict[str, Any]:
    return {
        "product_authorized": False,
        "post_runtime_execution_complete": True,
        "eval_verdict": "fail",
        "observability_complete": True,
        "terminal_closed": True,
        "terminal_outcome": TERMINAL_OUTCOME,
        "pipeline_complete": False,
    }


def _emit_transition_receipt(
    *,
    source: Path,
    output: Path,
    prior: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    receipt: dict[str, Any] = {
        "schema_version": W4_TRANSITION_SCHEMA,
        "wave": "W4",
        "status": "PASS",
        "source_run_id": source.name,
        "record_id": str(prior["w3_completion"].get("record_id") or ""),
        "transition": "AUTHORITY_FAILURE_TO_TERMINAL_NON_PRODUCT",
        "from_decisive_stage": "APPS_RG_L2",
        "to_terminal_stage": TERMINAL_STAGE_ID,
        "terminal_state": _terminal_state(),
        "authoritative_x3_code": "X3A_DENY_REROUTE",
        "historical_authorization_disposition": (
            "SUPERSEDED_INVALID_AUTHORITY"
        ),
        "historical_uwg_commit_observed": True,
        "new_uwg_operation_attempted": False,
        "candidate_artifacts_preserved": True,
        "source_artifacts_mutated": False,
        "causal_receipts": [
            _binding(
                prior["w1_reconciliation_path"],
                namespace="replay_root",
                root=prior["replay_root"],
            ),
            _binding(
                prior["w1_correction_path"],
                namespace="replay_root",
                root=prior["replay_root"],
            ),
            _binding(
                prior["w2_completion_path"],
                namespace="replay_root",
                root=prior["replay_root"],
            ),
            _binding(
                prior["w3_completion_path"],
                namespace="replay_root",
                root=prior["replay_root"],
            ),
        ],
    }
    receipt["semantic_digest"] = _canonical_digest(receipt)
    path = _atomic_write_json(output / W4_TRANSITION_FILENAME, receipt)
    return receipt, path


def _source_stage_outcome(stage_id: str) -> tuple[str, str, list[str], str]:
    if stage_id == "APPS_RG_L2":
        return (
            "FAIL",
            "ALL_11_L2_HANDOFFS_AND_SPINES_FAILED",
            [
                "ONE_OR_MORE_AUTHORITATIVE_LANE_CONTRACTS_BLOCKED",
                "FINAL_ASSEMBLY_PRODUCT_RELEASE_BLOCKED",
            ],
            "NONE",
        )
    if stage_id == "X1_REVIEW":
        return (
            "PASS",
            "EXECUTED_NON_AUTHORIZING_AFTER_L2_FAILURE",
            ["UPSTREAM_L2_AUTHORITY_FAILED"],
            "NON_PRODUCT_ONLY",
        )
    if stage_id == "X2_AGGREGATION":
        return (
            "PASS",
            "AGGREGATION_COMPLETED_NON_AUTHORIZING_AFTER_L2_FAILURE",
            ["UPSTREAM_L2_AUTHORITY_FAILED"],
            "NON_PRODUCT_ONLY",
        )
    if stage_id == "X3_DISPOSITION":
        return (
            "FAIL",
            "X3A_DENY_REROUTE",
            ["AUTHORITATIVE_L2_FAILURE"],
            "DENY_PRODUCT",
        )
    if stage_id == "PRODUCT_ELIGIBILITY":
        return (
            "BLOCKED",
            "SUPERSEDED_INVALID_AUTHORITY",
            ["X3A_DENY_REROUTE", "FINAL_ASSEMBLY_PRODUCT_RELEASE_BLOCKED"],
            "DENY_PRODUCT",
        )
    return "PASS", "COMPLETED", [], "NON_AUTHORIZING_RUNTIME_EVIDENCE"


def _emit_stage_ledger(
    *,
    source: Path,
    output: Path,
    prior: Mapping[str, Any],
    transition_path: Path,
) -> tuple[dict[str, Any], Path, dict[str, Any], Path]:
    replay_root = prior["replay_root"]
    w1_evidence = [
        _binding(
            prior["w1_reconciliation_path"],
            namespace="replay_root",
            root=replay_root,
        ),
        _binding(
            prior["w1_correction_path"],
            namespace="replay_root",
            root=replay_root,
        ),
    ]
    entries: list[dict[str, Any]] = []
    source_entries = {
        str(item.get("stage_id") or ""): item
        for item in prior["source_ledger"]["entries"]
    }
    for stage_id in EXPECTED_SOURCE_STAGE_IDS:
        original = source_entries[stage_id]
        status, outcome, causes, authority_effect = _source_stage_outcome(stage_id)
        evidence = [
            _binding(
                prior["source_receipt_paths"][stage_id],
                namespace="source_run",
                root=source,
            )
        ]
        if stage_id in {"APPS_RG_L2", "X3_DISPOSITION", "PRODUCT_ELIGIBILITY"}:
            evidence.extend(w1_evidence)
        entries.append(
            {
                "sequence": len(entries),
                "stage_id": stage_id,
                "status": status,
                "execution_complete": True,
                "historical_ledger_status": str(original.get("status") or ""),
                "status_derivation": (
                    "W1_AUTHORITATIVE_RECONCILIATION"
                    if stage_id
                    in {"APPS_RG_L2", "X3_DISPOSITION", "PRODUCT_ELIGIBILITY"}
                    else "SOURCE_CONTENT_ADDRESSED_LEDGER_RECEIPT"
                ),
                "governed_outcome": outcome,
                "cause_codes": causes,
                "authority_effect": authority_effect,
                "blocked_successors": (
                    ["X3_DISPOSITION", "PRODUCT_ELIGIBILITY", "UWG_COMMIT"]
                    if stage_id == "APPS_RG_L2"
                    else []
                ),
                "evidence_bindings": evidence,
            }
        )

    entries.append(
        {
            "sequence": len(entries),
            "stage_id": "UWG_COMMIT",
            "status": "FAIL",
            "execution_complete": True,
            "historical_commit_status": "COMMITTED",
            "new_uwg_operation_attempted": False,
            "status_derivation": "W1_AUTHORIZATION_CORRECTION",
            "governed_outcome": "HISTORICAL_COMMIT_SUPERSEDED_INVALID_AUTHORITY",
            "cause_codes": ["SUPERSEDED_INVALID_AUTHORITY"],
            "authority_effect": "DENY_REUSE_AND_PUBLICATION",
            "blocked_successors": [],
            "evidence_bindings": [
                _binding(
                    prior["uwg_path"], namespace="source_run", root=source
                ),
                _binding(
                    prior["product_authorization_path"],
                    namespace="source_run",
                    root=source,
                ),
                _binding(
                    prior["w1_correction_path"],
                    namespace="replay_root",
                    root=replay_root,
                ),
            ],
        }
    )
    entries.extend(
        [
            {
                "sequence": len(entries),
                "stage_id": "POST_RUNTIME_W0_FIREWALL",
                "status": "PASS",
                "execution_complete": True,
                "status_derivation": "W0_ZERO_PROVIDER_PREFLIGHT",
                "governed_outcome": "ZERO_PROVIDER_BOUNDARY_ESTABLISHED",
                "cause_codes": [],
                "authority_effect": "NONE",
                "blocked_successors": [],
                "evidence_bindings": [
                    _binding(
                        prior["w0_path"],
                        namespace="replay_root",
                        root=replay_root,
                    )
                ],
            },
            {
                "sequence": len(entries) + 1,
                "stage_id": "POST_RUNTIME_W1_AUTHORITY",
                "status": "PASS",
                "execution_complete": True,
                "status_derivation": "W1_COMPLETION_RECEIPT",
                "governed_outcome": "BLOCKED_NON_PRODUCT_AUTHORITY_RESOLVED",
                "cause_codes": [],
                "authority_effect": "DENY_PRODUCT",
                "blocked_successors": [],
                "evidence_bindings": [
                    _binding(
                        prior["w1_completion_path"],
                        namespace="replay_root",
                        root=replay_root,
                    ),
                    *w1_evidence,
                ],
            },
            {
                "sequence": len(entries) + 2,
                "stage_id": "APPS_EVAL",
                "status": "PASS",
                "execution_complete": True,
                "eval_verdict": "fail",
                "release_blocked": True,
                "status_derivation": "W2_COMPLETION_RECEIPT",
                "governed_outcome": "EVALUATION_COMPLETED_WITH_FAIL_VERDICT",
                "cause_codes": list(
                    prior["w2_completion"].get("admission_failure_modes") or []
                ),
                "authority_effect": "DENY_PRODUCT",
                "blocked_successors": [],
                "evidence_bindings": [
                    _binding(
                        prior["w2_completion_path"],
                        namespace="replay_root",
                        root=replay_root,
                    ),
                    _binding(
                        prior["eval_seal_path"],
                        namespace="replay_root",
                        root=replay_root,
                    ),
                ],
            },
            {
                "sequence": len(entries) + 3,
                "stage_id": "L6_OBSERVABILITY",
                "status": "PASS",
                "execution_complete": True,
                "observed_run_verdict": "fail",
                "grain_parity_status": "FAIL",
                "apps_eval_rows_bound": False,
                "source_evidence_unavailable_count": prior["w3_completion"][
                    "section_summary"
                ]["sections_source_evidence_unavailable"],
                "calibration_status": prior["w3_calibration"][
                    "calibration_status"
                ],
                "human_labels_present": False,
                "n_calibration_samples": 0,
                "calibration_informational_only": True,
                "status_derivation": "W3_COMPLETION_RECEIPT",
                "governed_outcome": "OBSERVABILITY_COMPLETED_WITH_FAILED_CLOSURE",
                "cause_codes": [
                    "ALL_REQUIRED_SECTIONS_NOT_BOUND",
                    "UNAVAILABLE_SOURCE_EVIDENCE",
                    "HUMAN_CALIBRATION_NOT_MEASURED",
                ],
                "authority_effect": "DENY_PRODUCT",
                "blocked_successors": [],
                "evidence_bindings": [
                    _binding(
                        prior["w3_completion_path"],
                        namespace="replay_root",
                        root=replay_root,
                    ),
                    _binding(
                        prior["w3_seal_path"],
                        namespace="replay_root",
                        root=replay_root,
                    ),
                    _binding(
                        prior["w3_closure_path"],
                        namespace="replay_root",
                        root=replay_root,
                    ),
                    _binding(
                        prior["w3_calibration_path"],
                        namespace="replay_root",
                        root=replay_root,
                    ),
                ],
            },
            {
                "sequence": len(entries) + 4,
                "stage_id": TERMINAL_STAGE_ID,
                "status": "PASS",
                "execution_complete": True,
                "status_derivation": "W4_TERMINAL_TRANSITION_RECEIPT",
                "governed_outcome": TERMINAL_OUTCOME,
                "cause_codes": ["AUTHORITATIVE_L2_FAILURE"],
                "authority_effect": "TERMINAL_DENY_PRODUCT",
                "blocked_successors": [],
                "evidence_bindings": [
                    _binding(
                        transition_path,
                        namespace="w4",
                        root=output,
                    )
                ],
            },
        ]
    )
    observed_sequences = [item["sequence"] for item in entries]
    if observed_sequences != list(range(len(entries))):
        raise TerminalCloseoutReplayError("derived_ledger_sequence_invalid")
    if any(item["status"] not in ALLOWED_STAGE_STATUSES for item in entries):
        raise TerminalCloseoutReplayError("derived_ledger_status_invalid")
    status_counts = Counter(str(item["status"]) for item in entries)
    ledger: dict[str, Any] = {
        "schema_version": W4_LEDGER_SCHEMA,
        "wave": "W4",
        "status": "SEALED",
        "source_run_id": source.name,
        "record_id": str(prior["w3_completion"].get("record_id") or ""),
        "allowed_stage_statuses": sorted(ALLOWED_STAGE_STATUSES),
        "decisive_failure_stage": "APPS_RG_L2",
        "decisive_failure_receipts": w1_evidence,
        "blocked_authority_successors": [
            "X3_DISPOSITION",
            "PRODUCT_ELIGIBILITY",
            "UWG_COMMIT",
        ],
        "entries": entries,
        "entry_count": len(entries),
        "stage_status_counts": dict(sorted(status_counts.items())),
        "entries_digest": _canonical_digest(entries),
        "terminal_state": _terminal_state(),
        "source_ledger_preserved": True,
        "source_artifacts_mutated": False,
        "new_uwg_operation_attempted": False,
    }
    ledger["semantic_digest"] = _canonical_digest(ledger)
    ledger_path = _atomic_write_json(output / W4_LEDGER_FILENAME, ledger)

    seal_body: dict[str, Any] = {
        "schema_version": W4_LEDGER_SEAL_SCHEMA,
        "status": "PASS",
        "source_run_id": source.name,
        "record_id": ledger["record_id"],
        "ledger": _binding(ledger_path, namespace="w4", root=output),
        "entry_count": ledger["entry_count"],
        "entries_digest": ledger["entries_digest"],
        "terminal_state_digest": _canonical_digest(ledger["terminal_state"]),
        "emission_phase": "POST_EMISSION_REOPENED_AND_VALIDATED",
    }
    ledger_seal = {**seal_body, "manifest_sha256": _canonical_digest(seal_body)}
    ledger_seal_path = _atomic_write_json(
        output / W4_LEDGER_SEAL_FILENAME, ledger_seal
    )
    return ledger, ledger_path, ledger_seal, ledger_seal_path


def _all_manifest_receipts(
    *,
    source: Path,
    output: Path,
    prior: Mapping[str, Any],
    ledger: Mapping[str, Any],
    transition_path: Path,
    ledger_path: Path,
    ledger_seal_path: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in ledger["entries"]:
        rows.extend(dict(item) for item in entry.get("evidence_bindings") or [])
    replay_root = prior["replay_root"]
    rows.extend(
        [
            _binding(
                prior["source_ledger_path"],
                namespace="source_run",
                root=source,
            ),
            _binding(
                prior["w1_parallel_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                prior["w1_guard_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                prior["w2_guard_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                prior["eval_record_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                prior["w2_supersession_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                prior["w3_guard_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                prior["w3_bindings_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                prior["w3_calibration_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                transition_path,
                namespace="w4",
                root=output,
            ),
            _binding(ledger_path, namespace="w4", root=output),
            _binding(ledger_seal_path, namespace="w4", root=output),
        ]
    )
    return _deduplicate_bindings(rows)


def _emit_terminal_manifest(
    *,
    source: Path,
    output: Path,
    prior: Mapping[str, Any],
    ledger: Mapping[str, Any],
    transition_path: Path,
    ledger_path: Path,
    ledger_seal_path: Path,
) -> tuple[dict[str, Any], Path, dict[str, Any], Path]:
    receipts = _all_manifest_receipts(
        source=source,
        output=output,
        prior=prior,
        ledger=ledger,
        transition_path=transition_path,
        ledger_path=ledger_path,
        ledger_seal_path=ledger_seal_path,
    )
    body: dict[str, Any] = {
        "schema_version": W4_TERMINAL_MANIFEST_SCHEMA,
        "manifest_type": TERMINAL_STAGE_ID,
        "status": "SEALED",
        "source_run_id": source.name,
        "record_id": str(prior["w3_completion"].get("record_id") or ""),
        "terminal_state": _terminal_state(),
        "decisive_failure_stage": "APPS_RG_L2",
        "authoritative_x3_code": "X3A_DENY_REROUTE",
        "historical_authorization_disposition": (
            "SUPERSEDED_INVALID_AUTHORITY"
        ),
        "historical_uwg_commit_observed": True,
        "new_uwg_operation_attempted": False,
        "source_run_manifest_sha256": prior["w0"]["source_manifest_sha256"],
        "stage_ledger": _binding(ledger_path, namespace="w4", root=output),
        "stage_ledger_seal": _binding(
            ledger_seal_path, namespace="w4", root=output
        ),
        "bound_receipt_count": len(receipts),
        "bound_receipts": receipts,
        "remote_otel_role": "OPTIONAL_MIRROR_NOT_AUTHORITY",
        "local_failure_telemetry_required": True,
        "source_artifacts_mutated": False,
        "candidate_artifacts_preserved": True,
    }
    manifest = {**body, "manifest_sha256": _canonical_digest(body)}
    manifest_path = _atomic_write_json(
        output / W4_TERMINAL_MANIFEST_FILENAME, manifest
    )
    seal_body: dict[str, Any] = {
        "schema_version": W4_TERMINAL_SEAL_SCHEMA,
        "status": "PASS",
        "source_run_id": source.name,
        "record_id": manifest["record_id"],
        "terminal_outcome": TERMINAL_OUTCOME,
        "terminal_manifest": _binding(
            manifest_path, namespace="w4", root=output
        ),
        "terminal_manifest_digest": manifest["manifest_sha256"],
        "terminal_closed": True,
        "product_authorized": False,
        "pipeline_complete": False,
        "emission_phase": "POST_EMISSION_REOPENED_AND_VALIDATED",
    }
    terminal_seal = {
        **seal_body,
        "manifest_sha256": _canonical_digest(seal_body),
    }
    terminal_seal_path = _atomic_write_json(
        output / W4_TERMINAL_SEAL_FILENAME, terminal_seal
    )
    return manifest, manifest_path, terminal_seal, terminal_seal_path


def verify_terminal_non_product_manifest(
    path: Path | str,
    *,
    source_run: Path | str,
    replay_root: Path | str,
) -> tuple[bool, list[str]]:
    manifest_path = Path(path).resolve(strict=True)
    output = manifest_path.parent
    source = Path(source_run).resolve(strict=True)
    replay = Path(replay_root).resolve(strict=True)
    manifest = _read_json(manifest_path, label="terminal_manifest")
    roots = {"source_run": source, "replay_root": replay, "w4": output}
    body = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    raw_rows = manifest.get("bound_receipts")
    manifest_rows_are_objects = isinstance(raw_rows, list) and all(
        isinstance(row, Mapping) for row in raw_rows
    )
    receipt_identities = (
        [
            (
                str(row.get("artifact_namespace") or ""),
                str(row.get("artifact_ref") or ""),
            )
            for row in raw_rows
        ]
        if manifest_rows_are_objects
        else []
    )
    stage_ledger_binding = manifest.get("stage_ledger")
    stage_ledger_binding = (
        dict(stage_ledger_binding)
        if isinstance(stage_ledger_binding, Mapping)
        else {}
    )
    stage_ledger_seal_binding = manifest.get("stage_ledger_seal")
    stage_ledger_seal_binding = (
        dict(stage_ledger_seal_binding)
        if isinstance(stage_ledger_seal_binding, Mapping)
        else {}
    )
    stage_ledger_identity = (
        str(stage_ledger_binding.get("artifact_namespace") or ""),
        str(stage_ledger_binding.get("artifact_ref") or ""),
    )
    stage_ledger_seal_identity = (
        str(stage_ledger_seal_binding.get("artifact_namespace") or ""),
        str(stage_ledger_seal_binding.get("artifact_ref") or ""),
    )
    rows_valid, row_errors, _ = _verify_manifest_rows(
        [
            {"artifact_role": f"receipt_{index:04d}", **dict(row)}
            for index, row in enumerate(raw_rows or [])
            if isinstance(row, Mapping)
        ],
        roots=roots,
        label="terminal_manifest",
    )
    expected_state = _terminal_state()
    checks = {
        "schema_exact": manifest.get("schema_version")
        == W4_TERMINAL_MANIFEST_SCHEMA,
        "filename_exact": manifest_path.name == W4_TERMINAL_MANIFEST_FILENAME,
        "manifest_type_exact": manifest.get("manifest_type")
        == TERMINAL_STAGE_ID,
        "status_sealed": manifest.get("status") == "SEALED",
        "source_run_bound": manifest.get("source_run_id") == source.name,
        "record_id_present": bool(str(manifest.get("record_id") or "")),
        "manifest_digest_valid": manifest.get("manifest_sha256")
        == _canonical_digest(body),
        "terminal_state_exact": manifest.get("terminal_state") == expected_state,
        "decisive_failure_exact": manifest.get("decisive_failure_stage")
        == "APPS_RG_L2",
        "authoritative_x3_exact": manifest.get("authoritative_x3_code")
        == "X3A_DENY_REROUTE",
        "historical_disposition_exact": manifest.get(
            "historical_authorization_disposition"
        )
        == "SUPERSEDED_INVALID_AUTHORITY",
        "historical_uwg_observed": manifest.get(
            "historical_uwg_commit_observed"
        )
        is True,
        "receipt_count_exact": type(manifest.get("bound_receipt_count")) is int
        and manifest.get("bound_receipt_count")
        == len(raw_rows or []),
        "receipt_rows_all_objects": manifest_rows_are_objects,
        "receipt_identities_unique": bool(receipt_identities)
        and len(receipt_identities) == len(set(receipt_identities)),
        "stage_ledger_binding_exact": _relative_binding_valid(
            stage_ledger_binding,
            root=output,
            expected=output / W4_LEDGER_FILENAME,
        ),
        "stage_ledger_seal_binding_exact": _relative_binding_valid(
            stage_ledger_seal_binding,
            root=output,
            expected=output / W4_LEDGER_SEAL_FILENAME,
        ),
        "stage_ledger_in_receipt_set": stage_ledger_identity
        in receipt_identities,
        "stage_ledger_seal_in_receipt_set": stage_ledger_seal_identity
        in receipt_identities,
        "all_receipts_reopened": rows_valid and not row_errors,
        "remote_collector_not_authority": manifest.get("remote_otel_role")
        == "OPTIONAL_MIRROR_NOT_AUTHORITY",
        "no_new_uwg": manifest.get("new_uwg_operation_attempted") is False,
        "source_not_mutated": manifest.get("source_artifacts_mutated") is False,
        "candidate_artifacts_preserved": manifest.get(
            "candidate_artifacts_preserved"
        )
        is True,
        "local_telemetry_required": manifest.get(
            "local_failure_telemetry_required"
        )
        is True,
    }
    errors = list(row_errors)
    errors.extend(name for name, passed in checks.items() if not passed)
    return not errors, sorted(set(errors))


def _event(
    *,
    record_id: str,
    sequence: int,
    observed_at: str,
    event_type: str,
    stage_id: str,
    payload: Mapping[str, Any],
    evidence: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    seed = f"{record_id}:{sequence}:{event_type}:{stage_id}"
    event_id = "evt-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    event: dict[str, Any] = {
        "schema_version": W4_TELEMETRY_SCHEMA,
        "event_id": event_id,
        "sequence": sequence,
        "observed_at": observed_at,
        "timestamp_source": "SEALED_EVAL_RECORD",
        "record_id": record_id,
        "event_type": event_type,
        "stage_id": stage_id,
        "authority": "LOCAL_SEALED_POST_RUNTIME_EVIDENCE",
        "remote_collector_role": "OPTIONAL_MIRROR_NOT_AUTHORITY",
        "payload": dict(payload),
        "evidence_bindings": [dict(item) for item in evidence],
    }
    event["semantic_digest"] = _canonical_digest(event)
    return event


def _emit_local_telemetry(
    *,
    output: Path,
    prior: Mapping[str, Any],
    ledger_path: Path,
    ledger_seal_path: Path,
    terminal_manifest_path: Path,
    terminal_seal_path: Path,
) -> tuple[list[dict[str, Any]], Path, dict[str, Any], Path]:
    replay_root = prior["replay_root"]
    record_id = str(prior["w3_completion"].get("record_id") or "")
    observed_at = str(prior["eval_record"].get("created_at") or "")
    if not observed_at:
        raise TerminalCloseoutReplayError("eval_record_created_at_missing")
    events: list[dict[str, Any]] = []

    def add(
        event_type: str,
        stage_id: str,
        payload: Mapping[str, Any],
        evidence: Iterable[Mapping[str, Any]],
    ) -> None:
        events.append(
            _event(
                record_id=record_id,
                sequence=len(events),
                observed_at=observed_at,
                event_type=event_type,
                stage_id=stage_id,
                payload=payload,
                evidence=evidence,
            )
        )

    w2_completion_binding = _binding(
        prior["w2_completion_path"],
        namespace="replay_root",
        root=replay_root,
    )
    add(
        "EVAL_ADMISSION_OBSERVED",
        "APPS_EVAL",
        {
            "execution_complete": True,
            "admission_status": prior["w2_completion"].get("admission_status"),
            "failure_modes": list(
                prior["w2_completion"].get("admission_failure_modes") or []
            ),
            "infrastructure_error": False,
        },
        [w2_completion_binding],
    )
    add(
        "DETERMINISTIC_GRADING_COMPLETED",
        "APPS_EVAL",
        {
            "execution_complete": True,
            "eval_verdict": "fail",
            "release_blocked": True,
            "with_judge": False,
            "saved_judge_artifacts_inspected": True,
        },
        [
            w2_completion_binding,
            _binding(
                prior["eval_seal_path"],
                namespace="replay_root",
                root=replay_root,
            ),
        ],
    )

    lane_rows = prior["w3_bindings"].get("bindings")
    if not isinstance(lane_rows, list):
        raise TerminalCloseoutReplayError("w3_lane_bindings_missing")
    rows_by_lane = {
        str(row.get("section_id") or ""): row
        for row in lane_rows
        if isinstance(row, Mapping)
    }
    if set(rows_by_lane) != set(EXPECTED_LANES):
        raise TerminalCloseoutReplayError("w3_lane_bindings_not_exact")
    for lane_id in EXPECTED_LANES:
        row = dict(rows_by_lane[lane_id])
        lane_path = (
            prior["replay_root"]
            / "w3"
            / "independent_bindings"
            / f"{lane_id}.binding.json"
        )
        lane_payload = _read_json(lane_path, label=f"w3_lane_binding:{lane_id}")
        if _canonical_digest(lane_payload) != _canonical_digest(row):
            raise TerminalCloseoutReplayError(
                f"w3_lane_binding_aggregate_mismatch:{lane_id}"
            )
        add(
            "L6_LANE_OBSERVATION_COMPLETED",
            "L6_OBSERVABILITY",
            {
                "lane_id": lane_id,
                "execution_complete": True,
                "binding_status": row.get("binding_status"),
                "source_evidence_status": row.get("source_evidence_status"),
                "source_evidence_reason_codes": list(
                    row.get("source_evidence_reason_codes") or []
                ),
                "evidence_class": row.get("evidence_class"),
                "apps_eval_row_count": row.get("apps_eval_row_count"),
                "l6_observation_row_count": row.get("l6_observation_row_count"),
                "proof_gaps": list(row.get("proof_gaps") or []),
            },
            [
                _binding(
                    lane_path,
                    namespace="replay_root",
                    root=replay_root,
                )
            ],
        )
    add(
        "L6_HUMAN_CALIBRATION_STATUS_RECORDED",
        "L6_OBSERVABILITY",
        {
            "calibration_status": prior["w3_calibration"].get(
                "calibration_status"
            ),
            "human_labels_present": prior["w3_calibration"].get(
                "human_labels_present"
            ),
            "n_calibration_samples": prior["w3_calibration"].get(
                "n_calibration_samples"
            ),
            "spearman_rho": prior["w3_calibration"].get("spearman_rho"),
            "p_value": prior["w3_calibration"].get("p_value"),
            "informational_only": prior["w3_calibration"].get(
                "informational_only"
            ),
            "required_for_exit": prior["w3_calibration"].get(
                "required_for_exit"
            ),
        },
        [
            _binding(
                prior["w3_calibration_path"],
                namespace="replay_root",
                root=replay_root,
            )
        ],
    )
    add(
        "APPS_EVAL_L6_BINDING_COMPLETED",
        "L6_OBSERVABILITY",
        {
            "execution_complete": True,
            "binding_closure_status": "FAIL",
            "apps_eval_rows_bound": False,
            "observed_run_verdict": "fail",
        },
        [
            _binding(
                prior["w3_bindings_path"],
                namespace="replay_root",
                root=replay_root,
            ),
            _binding(
                prior["w3_closure_path"],
                namespace="replay_root",
                root=replay_root,
            ),
        ],
    )
    add(
        "LEDGER_CLOSEOUT_COMPLETED",
        TERMINAL_STAGE_ID,
        {
            "execution_complete": True,
            "ledger_status": "SEALED",
            "terminal_outcome": TERMINAL_OUTCOME,
        },
        [
            _binding(ledger_path, namespace="w4", root=output),
            _binding(ledger_seal_path, namespace="w4", root=output),
        ],
    )
    add(
        "TERMINAL_SEALING_COMPLETED",
        TERMINAL_STAGE_ID,
        {
            "execution_complete": True,
            "terminal_closed": True,
            "terminal_outcome": TERMINAL_OUTCOME,
            "product_authorized": False,
            "pipeline_complete": False,
        },
        [
            _binding(
                terminal_manifest_path, namespace="w4", root=output
            ),
            _binding(terminal_seal_path, namespace="w4", root=output),
        ],
    )
    telemetry_path = _atomic_write_jsonl(output / W4_TELEMETRY_FILENAME, events)
    types = Counter(str(item["event_type"]) for item in events)
    summary: dict[str, Any] = {
        "schema_version": W4_TELEMETRY_SUMMARY_SCHEMA,
        "status": "PASS",
        "source_run_id": str(prior["w3_completion"].get("source_run_id") or ""),
        "record_id": record_id,
        "event_count": len(events),
        "event_type_counts": dict(sorted(types.items())),
        "l6_lane_event_count": types["L6_LANE_OBSERVATION_COMPLETED"],
        "l6_calibration_event_count": types[
            "L6_HUMAN_CALIBRATION_STATUS_RECORDED"
        ],
        "expected_l6_lane_event_count": len(EXPECTED_LANES),
        "required_boundary_events_present": all(
            types[name] > 0
            for name in (
                "EVAL_ADMISSION_OBSERVED",
                "DETERMINISTIC_GRADING_COMPLETED",
                "L6_LANE_OBSERVATION_COMPLETED",
                "L6_HUMAN_CALIBRATION_STATUS_RECORDED",
                "APPS_EVAL_L6_BINDING_COMPLETED",
                "LEDGER_CLOSEOUT_COMPLETED",
                "TERMINAL_SEALING_COMPLETED",
            )
        ),
        "local_authority": True,
        "remote_collector_role": "OPTIONAL_MIRROR_NOT_AUTHORITY",
        "telemetry": _binding(telemetry_path, namespace="w4", root=output),
        "events_digest": _canonical_digest(events),
    }
    summary["semantic_digest"] = _canonical_digest(summary)
    summary_path = _atomic_write_json(
        output / W4_TELEMETRY_SUMMARY_FILENAME, summary
    )
    return events, telemetry_path, summary, summary_path


def _emit_package_seal(
    *,
    output: Path,
    record_id: str,
    artifacts: Mapping[str, Path],
) -> tuple[dict[str, Any], Path]:
    rows = [
        _role_binding(role, _binding(path, namespace="w4", root=output))
        for role, path in sorted(artifacts.items())
    ]
    body: dict[str, Any] = {
        "schema_version": W4_PACKAGE_SEAL_SCHEMA,
        "status": "PASS",
        "record_id": record_id,
        "terminal_outcome": TERMINAL_OUTCOME,
        "artifact_count": len(rows),
        "artifacts": rows,
        "emission_phase": "POST_EMISSION_REOPENED_AND_VALIDATED",
    }
    seal = {**body, "manifest_sha256": _canonical_digest(body)}
    path = _atomic_write_json(output / W4_PACKAGE_SEAL_FILENAME, seal)
    return seal, path


def _verify_package_seal(
    output: Path, path: Path
) -> tuple[bool, list[str], dict[str, str]]:
    seal = _read_json(path, label="w4_package_seal")
    body = {key: value for key, value in seal.items() if key != "manifest_sha256"}
    rows_valid, row_errors, observed = _verify_manifest_rows(
        seal.get("artifacts"),
        roots={"w4": output},
        label="w4_package_seal",
    )
    artifact_rows = seal.get("artifacts")
    observed_roles = (
        {
            str(row.get("artifact_role") or "")
            for row in artifact_rows
            if isinstance(row, Mapping)
        }
        if isinstance(artifact_rows, list)
        else set()
    )
    checks = {
        "schema_exact": seal.get("schema_version") == W4_PACKAGE_SEAL_SCHEMA,
        "status_pass": seal.get("status") == "PASS",
        "terminal_outcome_exact": seal.get("terminal_outcome")
        == TERMINAL_OUTCOME,
        "manifest_digest_valid": seal.get("manifest_sha256")
        == _canonical_digest(body),
        "artifact_count_exact": seal.get("artifact_count")
        == len(artifact_rows or []),
        "required_artifact_roles_exact": observed_roles
        == REQUIRED_PACKAGE_ARTIFACT_ROLES,
        "all_artifacts_valid": rows_valid and not row_errors,
    }
    errors = list(row_errors)
    errors.extend(name for name, passed in checks.items() if not passed)
    return not errors, sorted(set(errors)), observed


def _execute_once(
    *,
    source: Path,
    output: Path,
    prior: Mapping[str, Any],
) -> dict[str, Any]:
    transition, transition_path = _emit_transition_receipt(
        source=source, output=output, prior=prior
    )
    ledger, ledger_path, ledger_seal, ledger_seal_path = _emit_stage_ledger(
        source=source,
        output=output,
        prior=prior,
        transition_path=transition_path,
    )
    manifest, manifest_path, terminal_seal, terminal_seal_path = (
        _emit_terminal_manifest(
            source=source,
            output=output,
            prior=prior,
            ledger=ledger,
            transition_path=transition_path,
            ledger_path=ledger_path,
            ledger_seal_path=ledger_seal_path,
        )
    )
    manifest_valid, manifest_errors = verify_terminal_non_product_manifest(
        manifest_path,
        source_run=source,
        replay_root=prior["replay_root"],
    )
    if not manifest_valid:
        raise TerminalCloseoutReplayError(
            "terminal_manifest_invalid:" + ",".join(manifest_errors)
        )
    terminal_seal_body = {
        key: value
        for key, value in terminal_seal.items()
        if key != "manifest_sha256"
    }
    _require_checks(
        {
            "ledger_digest_valid": _semantic_digest_valid(ledger),
            "ledger_seal_digest_valid": ledger_seal.get("manifest_sha256")
            == _canonical_digest(
                {
                    key: value
                    for key, value in ledger_seal.items()
                    if key != "manifest_sha256"
                }
            ),
            "ledger_seal_ledger_bound": _relative_binding_valid(
                ledger_seal.get("ledger"),
                root=output,
                expected=ledger_path,
            ),
            "terminal_seal_digest_valid": terminal_seal.get("manifest_sha256")
            == _canonical_digest(terminal_seal_body),
            "terminal_seal_manifest_file_bound": _relative_binding_valid(
                terminal_seal.get("terminal_manifest"),
                root=output,
                expected=manifest_path,
            ),
            "terminal_seal_manifest_bound": terminal_seal.get(
                "terminal_manifest_digest"
            )
            == manifest.get("manifest_sha256"),
        },
        label="w4_local_seal_invalid",
    )
    events, telemetry_path, telemetry_summary, telemetry_summary_path = (
        _emit_local_telemetry(
            output=output,
            prior=prior,
            ledger_path=ledger_path,
            ledger_seal_path=ledger_seal_path,
            terminal_manifest_path=manifest_path,
            terminal_seal_path=terminal_seal_path,
        )
    )
    artifacts = {
        "terminal_transition": transition_path,
        "terminal_stage_ledger": ledger_path,
        "terminal_stage_ledger_seal": ledger_seal_path,
        "terminal_non_product_manifest": manifest_path,
        "terminal_non_product_manifest_seal": terminal_seal_path,
        "local_failure_telemetry": telemetry_path,
        "local_failure_telemetry_summary": telemetry_summary_path,
    }
    package_seal, package_seal_path = _emit_package_seal(
        output=output,
        record_id=str(prior["w3_completion"].get("record_id") or ""),
        artifacts=artifacts,
    )
    package_valid, package_errors, artifact_digests = _verify_package_seal(
        output, package_seal_path
    )
    if not package_valid:
        raise TerminalCloseoutReplayError(
            "w4_package_seal_invalid:" + ",".join(package_errors)
        )
    return {
        "transition": transition,
        "transition_path": transition_path,
        "ledger": ledger,
        "ledger_path": ledger_path,
        "ledger_seal": ledger_seal,
        "ledger_seal_path": ledger_seal_path,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "terminal_seal": terminal_seal,
        "terminal_seal_path": terminal_seal_path,
        "events": events,
        "telemetry_path": telemetry_path,
        "telemetry_summary": telemetry_summary,
        "telemetry_summary_path": telemetry_summary_path,
        "package_seal": package_seal,
        "package_seal_path": package_seal_path,
        "package_artifact_digests": artifact_digests,
    }


def emit_w4_terminal_closeout_replay(
    *,
    source_run: Path | str,
    output_dir: Path | str,
) -> dict[str, Any]:
    """Close one saved failed run as a sealed non-product terminal outcome."""

    source = Path(source_run).resolve(strict=True)
    output = Path(output_dir).resolve()
    if _contained(output, source):
        raise TerminalCloseoutReplayError("W4 output cannot be inside source run")
    prior = _validate_prior_chain(source=source, output=output)

    first = _execute_once(source=source, output=output, prior=prior)
    first_seal_sha = _sha256_file(first["package_seal_path"])
    first_artifact_digests = dict(first["package_artifact_digests"])
    second = _execute_once(source=source, output=output, prior=prior)
    second_seal_sha = _sha256_file(second["package_seal_path"])
    second_artifact_digests = dict(second["package_artifact_digests"])

    state = second["manifest"]["terminal_state"]
    ledger = second["ledger"]
    entries = ledger["entries"]
    entries_by_stage = {str(item["stage_id"]): item for item in entries}
    checks = {
        "prior_w0_w3_chain_validated": True,
        "all_stage_statuses_governed": all(
            item.get("status") in ALLOWED_STAGE_STATUSES for item in entries
        ),
        "terminal_stage_coverage_exact": tuple(entries_by_stage)
        == EXPECTED_TERMINAL_STAGE_IDS
        and len(entries) == len(EXPECTED_TERMINAL_STAGE_IDS),
        "apps_eval_and_l6_recorded": entries_by_stage.get("APPS_EVAL", {}).get(
            "status"
        )
        == "PASS"
        and entries_by_stage.get("L6_OBSERVABILITY", {}).get("status") == "PASS",
        "l2_failure_authoritative": entries_by_stage.get("APPS_RG_L2", {}).get(
            "status"
        )
        == "FAIL",
        "aggregation_execution_preserved": entries_by_stage.get(
            "X2_AGGREGATION", {}
        ).get("status")
        == "PASS",
        "historical_uwg_failure_recorded": entries_by_stage.get(
            "UWG_COMMIT", {}
        ).get("status")
        == "FAIL"
        and entries_by_stage.get("UWG_COMMIT", {}).get(
            "new_uwg_operation_attempted"
        )
        is False,
        "terminal_state_exact": state == _terminal_state(),
        "terminal_manifest_sealed": second["manifest"].get("status") == "SEALED",
        "terminal_seal_pass": second["terminal_seal"].get("status") == "PASS",
        "local_failure_telemetry_complete": second["telemetry_summary"].get(
            "required_boundary_events_present"
        )
        is True
        and second["telemetry_summary"].get("l6_lane_event_count")
        == len(EXPECTED_LANES)
        and second["telemetry_summary"].get("l6_calibration_event_count") == 1,
        "remote_collector_not_authority": second["telemetry_summary"].get(
            "remote_collector_role"
        )
        == "OPTIONAL_MIRROR_NOT_AUTHORITY",
        "package_sealed": second["package_seal_path"].is_file(),
        "repeated_replay_seal_stable": first_seal_sha == second_seal_sha,
        "repeated_replay_artifact_bytes_stable": first_artifact_digests
        == second_artifact_digests,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    completion: dict[str, Any] = {
        "schema_version": W4_COMPLETION_SCHEMA,
        "wave": "W4",
        "status": "PASS" if not failed else "BLOCKED",
        "scope_complete": not failed,
        "w5_authorized": not failed,
        "source_run_id": source.name,
        "record_id": str(prior["w3_completion"].get("record_id") or ""),
        **_terminal_state(),
        "eval_execution_complete": True,
        "observed_run_verdict": "fail",
        "grain_parity_status": "FAIL",
        "source_evidence_unavailable_count": prior["w3_completion"][
            "section_summary"
        ]["sections_source_evidence_unavailable"],
        "calibration_status": prior["w3_calibration"]["calibration_status"],
        "human_labels_present": prior["w3_calibration"][
            "human_labels_present"
        ],
        "n_calibration_samples": prior["w3_calibration"][
            "n_calibration_samples"
        ],
        "calibration_informational_only": prior["w3_calibration"][
            "informational_only"
        ],
        "release_blocked": True,
        "authoritative_x3_code": "X3A_DENY_REROUTE",
        "historical_authorization_disposition": (
            "SUPERSEDED_INVALID_AUTHORITY"
        ),
        "historical_uwg_commit_observed": True,
        "new_uwg_operation_attempted": False,
        "candidate_artifacts_preserved": True,
        "source_artifacts_mutated": False,
        "stage_summary": {
            "entry_count": ledger["entry_count"],
            "stage_status_counts": ledger["stage_status_counts"],
            "decisive_failure_stage": ledger["decisive_failure_stage"],
            "apps_rg_l2_status": entries_by_stage["APPS_RG_L2"]["status"],
            "x2_aggregation_status": entries_by_stage["X2_AGGREGATION"][
                "status"
            ],
            "apps_eval_status": entries_by_stage["APPS_EVAL"]["status"],
            "l6_observability_status": entries_by_stage["L6_OBSERVABILITY"][
                "status"
            ],
            "terminal_status": entries_by_stage[TERMINAL_STAGE_ID]["status"],
        },
        "telemetry_summary": {
            "event_count": second["telemetry_summary"]["event_count"],
            "l6_lane_event_count": second["telemetry_summary"][
                "l6_lane_event_count"
            ],
            "l6_calibration_event_count": second["telemetry_summary"][
                "l6_calibration_event_count"
            ],
            "local_authority": second["telemetry_summary"]["local_authority"],
            "remote_collector_role": second["telemetry_summary"][
                "remote_collector_role"
            ],
        },
        "determinism_replay": {
            "execution_count": 2,
            "first_package_seal_sha256": first_seal_sha,
            "second_package_seal_sha256": second_seal_sha,
            "package_seal_bytes_stable": first_seal_sha == second_seal_sha,
            "artifact_bytes_stable": first_artifact_digests
            == second_artifact_digests,
        },
        "terminal_stage_ledger": _binding(
            second["ledger_path"], namespace="w4", root=output
        ),
        "terminal_stage_ledger_seal": _binding(
            second["ledger_seal_path"], namespace="w4", root=output
        ),
        "terminal_non_product_manifest": _binding(
            second["manifest_path"], namespace="w4", root=output
        ),
        "terminal_non_product_manifest_seal": _binding(
            second["terminal_seal_path"], namespace="w4", root=output
        ),
        "local_failure_telemetry": _binding(
            second["telemetry_path"], namespace="w4", root=output
        ),
        "w4_package_seal": _binding(
            second["package_seal_path"], namespace="w4", root=output
        ),
        "w3_completion_ref": prior["w3_completion_path"].as_posix(),
        "w3_completion_semantic_digest": prior["w3_completion"][
            "semantic_digest"
        ],
        "checks": checks,
        "failed_checks": failed,
    }
    completion["semantic_digest"] = _canonical_digest(completion)
    _atomic_write_json(output / W4_COMPLETION_FILENAME, completion)
    return {
        "completion": completion,
        "activity": {
            "apps_eval_executed": False,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
        "record_id": completion["record_id"],
        "terminal_manifest_path": second["manifest_path"].as_posix(),
        "terminal_stage_ledger_path": second["ledger_path"].as_posix(),
        "local_failure_telemetry_path": second["telemetry_path"].as_posix(),
        "w4_package_seal_path": second["package_seal_path"].as_posix(),
    }


__all__ = [
    "ALLOWED_STAGE_STATUSES",
    "EXPECTED_LANES",
    "EXPECTED_SOURCE_STAGE_IDS",
    "TERMINAL_OUTCOME",
    "TerminalCloseoutReplayError",
    "W4_COMPLETION_FILENAME",
    "W4_COMPLETION_SCHEMA",
    "emit_w4_terminal_closeout_replay",
    "verify_terminal_non_product_manifest",
]
