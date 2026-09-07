"""Seal W5 evidence from real zero-provider post-runtime execution.

W5 does not synthesize substitute run, failure, or success evidence.  It
reopens artifacts emitted by the production W0-W4 replay entrypoints, the
production W2/W3 failure boundaries, and production authority validators.
The module remains stdlib-only at import time so callers can install the
zero-provider guard before qualification.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


W5_COMPLETION_SCHEMA = "apps_rg.zero_llm_qualification_completion.v3"
W5_COMPLETION_FILENAME = "w5_completion_receipt.json"
W5_COUNTS_SCHEMA = "apps_rg.zero_llm_qualification_counts.v3"
W5_COUNTS_FILENAME = "qualification_counts.json"
W5_TRIPWIRE_SCHEMA = "apps_rg.w5_provider_tripwire_proof.v1"
W5_TRIPWIRE_FILENAME = "provider_tripwire_proof.json"
W5_PACKAGE_SEAL_SCHEMA = "apps_rg.zero_llm_qualification_package_seal.v3"
W5_PACKAGE_SEAL_FILENAME = "w5_qualification_package_seal.json"

INTEGRATED_EXECUTION_SCHEMA = "apps_rg.w5_integrated_execution.v2"
FAULT_QUALIFICATION_SCHEMA = "apps_rg.w5_production_fault_qualification.v1"
POSITIVE_CONTROL_SCHEMA = "apps_rg.w5_production_positive_control.v1"
ZERO_PROVIDER_GUARD_SCHEMA = "apps_rg.post_runtime_zero_provider_replay.v1"

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
    "slalom_bullets",
    "slalom_narrative",
    "unify_bullets",
    "unify_narrative",
)

EXPECTED_STAGE_IDS: tuple[str, ...] = (
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
    "UWG_COMMIT",
    "POST_RUNTIME_W0_FIREWALL",
    "POST_RUNTIME_W1_AUTHORITY",
    "APPS_EVAL",
    "L6_OBSERVABILITY",
    "TERMINAL_NON_PRODUCT",
)

MODEL_ROUTE_LANE_ARTIFACT_ROLES = frozenset(
    {
        "l2_execution_packet",
        "attempt_receipt",
        "provider_request",
        "provider_response",
        "l2_handoff_receipt",
    }
)

ZERO_COUNTER_KEYS: tuple[str, ...] = (
    "provider_calls",
    "judge_calls",
    "embedding_calls",
    "model_calls",
    "network_attempts",
    "subprocess_attempts",
)

INTEGRATED_ARTIFACT_ROLES = frozenset(
    {
        "w0_receipt",
        "w1_guard",
        "w1_completion",
        "w1_parallel",
        "w2_guard",
        "w2_completion",
        "w3_guard",
        "w3_completion",
        "w3_calibration",
        "w4_guard",
        "w4_completion",
        "w4_stage_ledger",
        "w4_terminal_manifest",
        "w4_package_seal",
    }
)

FAULT_ARTIFACT_ROLES = frozenset(
    {
        "eval_error_receipt",
        "eval_error_span",
        "eval_resume_receipt",
        "eval_fault_guard",
        "eval_success_guard",
        "l6_error_receipt",
        "l6_error_span",
        "l6_resume_receipt",
        "l6_fault_guard",
        "l6_success_guard",
        "terminal_completion",
    }
)

POSITIVE_ARTIFACT_ROLES = frozenset(
    {
        "fixture_metadata",
        "product_entry",
        "whole_run_exit",
        "final_assembly",
        "fixture_uwg_decision",
        "product_authorization",
        "terminal_state",
        "stage_authority_apps_rg_c0",
        "stage_authority_apps_rg_pa",
        "stage_authority_apps_rg_l2",
        "stage_authority_x1_review",
        "stage_authority_x2_aggregation",
        "stage_authority_x3_disposition",
    }
)

W5_SEAL_ROLES = frozenset(
    {
        "integrated_execution_manifest",
        "production_fault_qualification_manifest",
        "production_positive_control_manifest",
        "positive_control_zero_provider_guard",
        "provider_tripwire_proof",
        "qualification_counts",
    }
)


class ZeroLlmQualificationError(RuntimeError):
    """Raised when W5 evidence is incomplete, inconsistent, or unsealed."""


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
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise ZeroLlmQualificationError(
            f"{label}_unreadable:{type(exc).__name__}:{path}"
        ) from exc
    if not isinstance(value, dict):
        raise ZeroLlmQualificationError(f"{label}_not_object:{path}")
    return value


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ZeroLlmQualificationError(
            f"{label}_unreadable:{type(exc).__name__}:{path}"
        ) from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ZeroLlmQualificationError(
                f"{label}_invalid_json:{line_number}:{path}"
            ) from exc
        if not isinstance(value, dict):
            raise ZeroLlmQualificationError(f"{label}_not_object:{line_number}:{path}")
        rows.append(value)
    return rows


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".tmp-{uuid.uuid4().hex[:8]}")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)
    return path


def _write_semantic(path: Path, payload: Mapping[str, Any]) -> Path:
    body = dict(payload)
    body["semantic_digest"] = _canonical_digest(body)
    return _atomic_write_json(path, body)


def _digest_valid(
    payload: Mapping[str, Any],
    *,
    field: str = "semantic_digest",
) -> bool:
    body = dict(payload)
    observed = str(body.pop(field, "") or "")
    return bool(observed) and observed == _canonical_digest(body)


def _require(checks: Mapping[str, bool], *, label: str) -> None:
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ZeroLlmQualificationError(f"{label}:" + ",".join(failed))


def _binding(path: Path, *, root: Path, role: str) -> dict[str, Any]:
    target = path.resolve(strict=True)
    authority_root = root.resolve(strict=True)
    if not _contained(target, authority_root):
        raise ZeroLlmQualificationError(f"artifact_outside_evidence_root:{target}")
    return {
        "artifact_role": role,
        "artifact_ref": target.relative_to(authority_root).as_posix(),
        "byte_length": target.stat().st_size,
        "sha256": _sha256_file(target),
    }


def _resolve_binding(
    binding: Any,
    *,
    root: Path,
    label: str,
) -> Path:
    if not isinstance(binding, Mapping):
        raise ZeroLlmQualificationError(f"{label}_binding_not_object")
    ref = str(binding.get("artifact_ref") or "").strip()
    if not ref:
        raise ZeroLlmQualificationError(f"{label}_binding_ref_missing")
    candidate = (root / ref).resolve()
    if not _contained(candidate, root) or not candidate.is_file():
        raise ZeroLlmQualificationError(f"{label}_artifact_missing:{ref}")
    if binding.get("byte_length") != candidate.stat().st_size:
        raise ZeroLlmQualificationError(f"{label}_artifact_length_mismatch")
    if binding.get("sha256") != _sha256_file(candidate):
        raise ZeroLlmQualificationError(f"{label}_artifact_digest_mismatch")
    return candidate


def _artifact_map(
    rows: Any,
    *,
    root: Path,
    expected_roles: frozenset[str],
    label: str,
) -> dict[str, Path]:
    if not isinstance(rows, list):
        raise ZeroLlmQualificationError(f"{label}_artifacts_not_list")
    paths: dict[str, Path] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ZeroLlmQualificationError(f"{label}_artifact_not_object:{index}")
        role = str(row.get("artifact_role") or "").strip()
        if not role or role in paths:
            raise ZeroLlmQualificationError(
                f"{label}_artifact_role_invalid:{role or index}"
            )
        paths[role] = _resolve_binding(
            row,
            root=root,
            label=f"{label}:{role}",
        )
    _require(
        {"artifact_roles_exact": set(paths) == expected_roles},
        label=label,
    )
    return paths


def _zero_top_level(payload: Mapping[str, Any]) -> bool:
    return all(payload.get(key) == 0 for key in ZERO_COUNTER_KEYS)


def _guard_zero(guard: Mapping[str, Any], *, status: str = "PASS") -> bool:
    counters = guard.get("attempt_counters")
    counters = dict(counters) if isinstance(counters, Mapping) else {}
    return bool(
        guard.get("schema_version") == ZERO_PROVIDER_GUARD_SCHEMA
        and guard.get("status") == status
        and _digest_valid(guard)
        and bool(counters)
        and all(counters.get(key) == 0 for key in ZERO_COUNTER_KEYS)
        and _zero_top_level(guard)
        and guard.get("uwg_operation_attempted") is False
        and guard.get("source_unchanged") is True
    )


def _normalize_inputs(
    run_inputs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Path]]:
    if len(run_inputs) != 2:
        raise ZeroLlmQualificationError("W5 requires exactly two real run inputs")
    normalized: list[dict[str, Path]] = []
    for index, row in enumerate(run_inputs):
        if not isinstance(row, Mapping):
            raise ZeroLlmQualificationError(f"run_input_not_object:{index}")
        source = Path(row.get("source_run", "")).resolve(strict=True)
        replay = Path(row.get("replay_root", "")).resolve(strict=True)
        if not source.is_dir() or not replay.is_dir():
            raise ZeroLlmQualificationError(f"run_input_not_directory:{index}")
        normalized.append({"source_run": source, "replay_root": replay})
    normalized.sort(key=lambda row: row["source_run"].name)
    if len({row["source_run"].name for row in normalized}) != 2:
        raise ZeroLlmQualificationError("W5 source run IDs must be unique")
    return normalized


def _verify_historical_saved_judges(
    *,
    inventory_raw: Any,
    source: Path,
) -> dict[str, Any]:
    inventory = dict(inventory_raw) if isinstance(inventory_raw, Mapping) else {}
    results_raw = inventory.get("results")
    results = results_raw if isinstance(results_raw, list) else []
    aliases_raw = inventory.get("legacy_claude_named_artifacts")
    aliases = aliases_raw if isinstance(aliases_raw, list) else []
    checks_recorded = inventory.get("checks")
    checks_recorded = (
        dict(checks_recorded) if isinstance(checks_recorded, Mapping) else {}
    )
    observed_models: dict[str, int] = {}
    observed_providers: dict[str, int] = {}
    identities: set[tuple[str, str, str]] = set()
    result_artifacts_valid = True
    result_payloads_match = True
    document_cache: dict[Path, dict[str, Any]] = {}
    for row_raw in results:
        if not isinstance(row_raw, Mapping):
            result_artifacts_valid = False
            result_payloads_match = False
            continue
        row = dict(row_raw)
        ref = str(row.get("artifact_ref") or "")
        candidate = (source / ref).resolve()
        valid = bool(
            ref
            and _contained(candidate, source)
            and candidate.is_file()
            and row.get("artifact_sha256") == _sha256_file(candidate)
        )
        result_artifacts_valid = result_artifacts_valid and valid
        if not valid:
            continue
        document = document_cache.get(candidate)
        if document is None:
            document = _read_json(candidate, label=f"saved_judge:{ref}")
            document_cache[candidate] = document
        raw_judges = document.get("judges")
        if isinstance(raw_judges, Mapping):
            judges = [dict(raw_judges)]
        elif isinstance(raw_judges, list):
            judges = [dict(judge) for judge in raw_judges if isinstance(judge, Mapping)]
        else:
            judges = []
        matching = []
        for judge in judges:
            passed = judge.get("pass")
            if not isinstance(passed, bool):
                passed = judge.get("pass_")
            model_actual = str(
                judge.get("model_actual") or judge.get("model_name") or ""
            )
            if (
                str(judge.get("judge_id") or "") == row.get("judge_id")
                and model_actual == row.get("model_actual")
                and str(judge.get("provider_status") or "")
                == row.get("provider_status")
                and (passed is True) == row.get("pass")
            ):
                matching.append(judge)
        result_payloads_match = result_payloads_match and len(matching) == 1
        model = str(row.get("model_actual") or "")
        provider = str(row.get("provider_name") or "")
        observed_models[model] = observed_models.get(model, 0) + 1
        observed_providers[provider] = observed_providers.get(provider, 0) + 1
        identities.add((ref, str(row.get("judge_id") or ""), model))

    alias_artifacts_valid = True
    aliases_are_openai = True
    for row_raw in aliases:
        if not isinstance(row_raw, Mapping):
            alias_artifacts_valid = False
            aliases_are_openai = False
            continue
        row = dict(row_raw)
        ref = str(row.get("artifact_ref") or "")
        candidate = (source / ref).resolve()
        valid = bool(
            ref
            and _contained(candidate, source)
            and candidate.is_file()
            and row.get("artifact_sha256") == _sha256_file(candidate)
        )
        alias_artifacts_valid = alias_artifacts_valid and valid
        if valid:
            judge = _read_json(candidate, label=f"legacy_judge_alias:{ref}")
            aliases_are_openai = aliases_are_openai and bool(
                row.get("legacy_filename_only") is True
                and row.get("model_actual") == "gpt-5.6-sol"
                and row.get("provider_name") == "OpenAI ChatGPT"
                and row.get("provider_status") == "MODEL_BACKED_PASS"
                and row.get("pass") is True
                and judge.get("model_actual") == "gpt-5.6-sol"
                and judge.get("provider_name") == "OpenAI ChatGPT"
                and judge.get("provider_status") == "MODEL_BACKED_PASS"
                and judge.get("pass") is True
            )

    checks = {
        "scope_exact": inventory.get("evidence_scope")
        == "HISTORICAL_SAVED_JUDGE_OUTPUTS_NO_W5_JUDGE_EXECUTION",
        "status_pass": inventory.get("status") == "PASS",
        "counts_exact": inventory.get("result_count") == len(results) == 21
        and inventory.get("passing_result_count") == 21,
        "results_unique": len(identities) == 21,
        "all_results_pass": all(
            isinstance(row, Mapping)
            and row.get("pass") is True
            and row.get("evaluator_mode") == "MODEL_BACKED"
            and row.get("provider_status") == "MODEL_BACKED_PASS"
            and row.get("provider_available") is True
            and row.get("provider_blocked") is False
            and row.get("mocked") is False
            and row.get("fallback_used") is False
            for row in results
        ),
        "model_counts_exact": observed_models
        == {"gemini-3.6-flash": 12, "gpt-5.6-sol": 9}
        == inventory.get("model_counts"),
        "provider_counts_exact": observed_providers
        == {"Google Gemini 3.6 Flash": 12, "OpenAI ChatGPT": 9}
        == inventory.get("provider_counts"),
        "no_claude_model_result": inventory.get("actual_claude_judge_result_count") == 0
        and all(
            "claude" not in str(row.get("model_actual") or "").lower()
            for row in results
            if isinstance(row, Mapping)
        ),
        "legacy_alias_count_exact": inventory.get("legacy_claude_named_artifact_count")
        == len(aliases)
        == 5,
        "legacy_aliases_are_openai": aliases_are_openai,
        "result_artifacts_valid": result_artifacts_valid,
        "result_payloads_match": result_payloads_match,
        "alias_artifacts_valid": alias_artifacts_valid,
        "recorded_checks_pass": bool(checks_recorded)
        and all(value is True for value in checks_recorded.values()),
    }
    _require(checks, label=f"historical_saved_judges_invalid:{source.name}")
    return {
        "status": "PASS",
        "result_count": 21,
        "passing_result_count": 21,
        "actual_claude_judge_result_count": 0,
    }


def _verify_historical_model_routes(
    *,
    inventory_raw: Any,
    source: Path,
) -> dict[str, Any]:
    """Reopen the saved routing bytes and independently reproduce the RCA."""

    inventory = dict(inventory_raw) if isinstance(inventory_raw, Mapping) else {}
    research_raw = inventory.get("apps_research")
    research = dict(research_raw) if isinstance(research_raw, Mapping) else {}
    generation_raw = inventory.get("apps_rg_generation")
    generation = dict(generation_raw) if isinstance(generation_raw, Mapping) else {}
    recorded_checks_raw = inventory.get("checks")
    recorded_checks = (
        dict(recorded_checks_raw) if isinstance(recorded_checks_raw, Mapping) else {}
    )

    ledger_path = _resolve_binding(
        research.get("ledger_artifact"),
        root=source,
        label="historical_model_routes:apps_research_ledger",
    )
    events = _read_jsonl(
        ledger_path,
        label="historical_model_routes:apps_research_ledger",
    )
    event_model_counts: dict[str, int] = {}
    event_provider_counts: dict[str, int] = {}
    claude_event_count = 0
    for event in events:
        model = str(event.get("model") or event.get("requested_model") or "")
        provider = str(event.get("provider") or "")
        event_model_counts[model] = event_model_counts.get(model, 0) + 1
        event_provider_counts[provider] = event_provider_counts.get(provider, 0) + 1
        if any(
            "claude" in str(event.get(field) or "").lower()
            for field in ("model", "requested_model", "observed_model", "provider")
        ):
            claude_event_count += 1

    successful_attempts = [
        {
            "logical_attempt": int(event.get("logical_attempt") or 0),
            "logical_attempt_id": str(event.get("logical_attempt_id") or ""),
            "section_id": str(event.get("section_id") or ""),
            "provider": str(event.get("provider") or ""),
            "requested_model": str(event.get("requested_model") or ""),
            "observed_model": str(event.get("observed_model") or ""),
            "total_tokens": int(event.get("total_tokens") or 0),
            "outcome": str(event.get("outcome") or ""),
            "provider_status": str(event.get("provider_status") or ""),
            "model_pin_valid": event.get("model_pin_valid") is True,
            "overall_success": event.get("overall_success") is True,
            "application_output_valid": event.get("application_output_valid") is True,
            "response_schema_valid": event.get("response_schema_valid") is True,
        }
        for event in events
        if event.get("outcome") == "SUCCESS"
    ]
    success_model_counts: dict[str, int] = {}
    for attempt in successful_attempts:
        model = str(attempt["observed_model"])
        success_model_counts[model] = success_model_counts.get(model, 0) + 1

    lanes_raw = generation.get("lanes")
    lanes = lanes_raw if isinstance(lanes_raw, list) else []
    lane_ids: set[str] = set()
    lane_rows_match = True
    target_claude_count = 0
    actual_claude_count = 0
    model_mismatch_count = 0
    recorded_budget_failure_count = 0
    recomputed_budget_failure_count = 0
    false_budget_failure_count = 0
    for index, row_raw in enumerate(lanes):
        if not isinstance(row_raw, Mapping):
            lane_rows_match = False
            continue
        row = dict(row_raw)
        lane = str(row.get("lane") or "")
        lane_ids.add(lane)
        paths = _artifact_map(
            row.get("artifacts"),
            root=source,
            expected_roles=MODEL_ROUTE_LANE_ARTIFACT_ROLES,
            label=f"historical_model_routes:{lane or index}",
        )
        docs = {
            role: _read_json(path, label=f"historical_model_routes:{lane}:{role}")
            for role, path in paths.items()
        }
        packet = docs["l2_execution_packet"]
        attempt = docs["attempt_receipt"]
        request = docs["provider_request"]
        response = docs["provider_response"]
        handoff = docs["l2_handoff_receipt"]
        budget_raw = packet.get("budget")
        budget = dict(budget_raw) if isinstance(budget_raw, Mapping) else {}
        local_raw = attempt.get("local_check_results")
        local = dict(local_raw) if isinstance(local_raw, Mapping) else {}
        handoff_checks_raw = handoff.get("checks")
        handoff_checks = (
            dict(handoff_checks_raw) if isinstance(handoff_checks_raw, Mapping) else {}
        )
        provider_envelope_raw = response.get("provider_response")
        provider_envelope = (
            dict(provider_envelope_raw)
            if isinstance(provider_envelope_raw, Mapping)
            else {}
        )
        transport_raw = provider_envelope.get("transport_response")
        transport = dict(transport_raw) if isinstance(transport_raw, Mapping) else {}
        raw_response_raw = transport.get("raw_response")
        raw_response = (
            dict(raw_response_raw) if isinstance(raw_response_raw, Mapping) else {}
        )
        usage_raw = raw_response.get("usage")
        usage = dict(usage_raw) if isinstance(usage_raw, Mapping) else {}
        ceiling = int(budget.get("max_tokens") or 0)
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)
        recorded_model_match = handoff_checks.get("model_id_matches") is True
        recorded_budget_pass = handoff_checks.get("token_budget_pass") is True
        recomputed_budget_pass = output_tokens <= ceiling
        expected = {
            "lane": lane,
            "signed_target_model": str(packet.get("target_model") or ""),
            "signed_canonical_provider": str(packet.get("canonical_provider") or ""),
            "signed_allowed_models": [
                str(model) for model in (packet.get("allowed_models") or [])
            ],
            "signed_output_token_ceiling": ceiling,
            "attempt_claimed_model": str(local.get("model_or_tool_name") or ""),
            "attempt_claimed_provider_lane": str(local.get("provider_lane") or ""),
            "provider_requested": str(request.get("provider_requested") or ""),
            "provider_request_model": str(request.get("model") or ""),
            "provider_request_max_tokens": int(request.get("max_tokens") or 0),
            "provider_response_model": str(response.get("model") or ""),
            "runtime_generation_status": str(
                response.get("runtime_generation_status") or ""
            ),
            "provider_attempted": response.get("provider_attempted") is True,
            "provider_available": response.get("provider_available") is True,
            "stub": response.get("stub") is True,
            "observed_input_tokens": input_tokens,
            "observed_output_tokens": output_tokens,
            "observed_total_tokens": total_tokens,
            "handoff_model_id_used": str(handoff.get("model_id_used") or ""),
            "handoff_provider_lane_used": str(handoff.get("provider_lane_used") or ""),
            "handoff_tokens_recorded": int(handoff.get("tokens_emitted") or 0),
            "recorded_model_id_matches": recorded_model_match,
            "recorded_token_budget_pass": recorded_budget_pass,
            "recomputed_output_token_budget_pass": recomputed_budget_pass,
            "handoff_status": str(handoff.get("handoff_status") or ""),
        }
        lane_rows_match = lane_rows_match and all(
            row.get(key) == value for key, value in expected.items()
        )
        target_claude_count += expected["signed_target_model"] == "claude-sonnet-5"
        actual_claude_count += "claude" in expected["provider_response_model"].lower()
        model_mismatch_count += recorded_model_match is False
        recorded_budget_failure_count += recorded_budget_pass is False
        recomputed_budget_failure_count += recomputed_budget_pass is False
        false_budget_failure_count += (
            recorded_budget_pass is False and recomputed_budget_pass is True
        )
        lane_rows_match = lane_rows_match and bool(
            expected["signed_target_model"] == "claude-sonnet-5"
            and expected["signed_allowed_models"] == ["claude-sonnet-5"]
            and expected["signed_canonical_provider"] == "openai"
            and expected["attempt_claimed_model"] == "claude-sonnet-5"
            and expected["attempt_claimed_provider_lane"] == "openai"
            and expected["provider_requested"] == "external_openai"
            and expected["provider_request_model"] == "gpt-5.6-luna"
            and expected["provider_response_model"] == "gpt-5.6-luna"
            and expected["runtime_generation_status"] == "REAL_LLM"
            and expected["provider_attempted"] is True
            and expected["provider_available"] is True
            and expected["stub"] is False
            and expected["handoff_model_id_used"] == "gpt-5.6-luna"
            and expected["handoff_provider_lane_used"] == "openai"
            and expected["recorded_model_id_matches"] is False
            and expected["recorded_token_budget_pass"] is False
            and expected["recomputed_output_token_budget_pass"] is True
            and expected["observed_input_tokens"] + expected["observed_output_tokens"]
            == expected["observed_total_tokens"]
            == expected["handoff_tokens_recorded"]
            and expected["handoff_status"] == "FAIL"
        )

    checks = {
        "scope_exact": inventory.get("evidence_scope")
        == "HISTORICAL_SAVED_MODEL_ROUTES_NO_W5_MODEL_EXECUTION",
        "status_pass": inventory.get("status") == "PASS",
        "routing_outcome_exact": inventory.get("routing_outcome")
        == "FAIL_MODEL_PIN_MISMATCH",
        "token_accounting_outcome_exact": inventory.get("token_accounting_outcome")
        == "FALSE_FAILURE_TOTAL_VS_OUTPUT",
        "artifact_count_exact": inventory.get("artifact_count") == 56,
        "research_counts_exact": research.get("usage_event_count") == len(events) == 17
        and research.get("usage_event_model_counts")
        == event_model_counts
        == {"gemini-3.6-flash": 7, "gpt-5.6-terra": 10}
        and research.get("usage_event_provider_counts")
        == event_provider_counts
        == {"external_openai": 10, "google_gemini": 7}
        and research.get("successful_attempt_count") == len(successful_attempts) == 3
        and research.get("successful_attempt_model_counts")
        == success_model_counts
        == {"gemini-3.6-flash": 1, "gpt-5.6-terra": 2}
        and research.get("claude_usage_event_count") == claude_event_count == 0,
        "research_success_attempts_exact": research.get("successful_attempts")
        == successful_attempts,
        "lane_rows_exact": lane_rows_match,
        "lane_counts_exact": generation.get("lane_count") == len(lanes) == 11
        and lane_ids == set(EXPECTED_LANES),
        "model_failure_counts_exact": generation.get("target_claude_lane_count")
        == target_claude_count
        == 11
        and generation.get("actual_claude_lane_count") == actual_claude_count == 0
        and generation.get("model_mismatch_lane_count") == model_mismatch_count == 11,
        "token_failure_counts_exact": generation.get(
            "recorded_token_budget_failure_lane_count"
        )
        == recorded_budget_failure_count
        == 11
        and generation.get("recomputed_output_token_budget_failure_lane_count")
        == recomputed_budget_failure_count
        == 0
        and generation.get("token_accounting_false_failure_lane_count")
        == false_budget_failure_count
        == 11,
        "recorded_checks_pass": bool(recorded_checks)
        and all(value is True for value in recorded_checks.values()),
    }
    _require(checks, label=f"historical_model_routes_invalid:{source.name}")
    return {
        "status": "PASS",
        "apps_research_usage_event_count": 17,
        "apps_research_successful_attempt_count": 3,
        "apps_research_claude_usage_event_count": 0,
        "apps_rg_generation_lane_count": 11,
        "apps_rg_target_claude_lane_count": 11,
        "apps_rg_actual_claude_lane_count": 0,
        "apps_rg_model_mismatch_lane_count": 11,
        "apps_rg_recorded_token_budget_failure_lane_count": 11,
        "apps_rg_recomputed_output_token_budget_failure_lane_count": 0,
        "apps_rg_token_accounting_false_failure_lane_count": 11,
    }


def _verify_contract_handoffs(
    *,
    inventory_raw: Any,
    ledger: Mapping[str, Any],
    source: Path,
    replay: Path,
) -> dict[str, Any]:
    inventory = dict(inventory_raw) if isinstance(inventory_raw, Mapping) else {}
    entries_raw = inventory.get("entries")
    entries = entries_raw if isinstance(entries_raw, list) else []
    ledger_entries_raw = ledger.get("entries")
    ledger_entries = ledger_entries_raw if isinstance(ledger_entries_raw, list) else []
    recorded_checks = inventory.get("checks")
    recorded_checks = (
        dict(recorded_checks) if isinstance(recorded_checks, Mapping) else {}
    )
    bindings_valid = True
    ledger_parity = len(entries) == len(ledger_entries)
    for index, row_raw in enumerate(entries):
        if not isinstance(row_raw, Mapping) or index >= len(ledger_entries):
            bindings_valid = False
            ledger_parity = False
            continue
        ledger_raw = ledger_entries[index]
        if not isinstance(ledger_raw, Mapping):
            ledger_parity = False
            continue
        row = dict(row_raw)
        ledger_parity = ledger_parity and bool(
            row.get("sequence") == ledger_raw.get("sequence")
            and row.get("stage_id") == ledger_raw.get("stage_id")
            and row.get("status") == ledger_raw.get("status")
            and row.get("execution_complete")
            == (ledger_raw.get("execution_complete") is True)
            and row.get("governed_outcome")
            == str(ledger_raw.get("governed_outcome") or "")
            and row.get("authority_effect")
            == str(ledger_raw.get("authority_effect") or "")
        )
        bindings_raw = row.get("evidence_bindings")
        bindings = bindings_raw if isinstance(bindings_raw, list) else []
        ledger_bindings_raw = ledger_raw.get("evidence_bindings")
        ledger_bindings = (
            ledger_bindings_raw if isinstance(ledger_bindings_raw, list) else []
        )
        ledger_parity = ledger_parity and len(bindings) == len(ledger_bindings)
        for binding_index, binding_raw in enumerate(bindings):
            if (
                not isinstance(binding_raw, Mapping)
                or binding_index >= len(ledger_bindings)
                or not isinstance(ledger_bindings[binding_index], Mapping)
            ):
                bindings_valid = False
                ledger_parity = False
                continue
            binding = dict(binding_raw)
            ledger_binding = dict(ledger_bindings[binding_index])
            projected = dict(binding)
            claimed_valid = projected.pop("binding_valid", None)
            ledger_parity = ledger_parity and projected == ledger_binding
            namespace = str(binding.get("artifact_namespace") or "")
            authority_root = {
                "source_run": source,
                "replay_root": replay,
                "w4": replay / "w4",
            }.get(namespace)
            ref = str(binding.get("artifact_ref") or "")
            candidate = (
                (authority_root / ref).resolve()
                if authority_root is not None and ref
                else Path()
            )
            valid = bool(
                claimed_valid is True
                and authority_root is not None
                and ref
                and _contained(candidate, authority_root)
                and candidate.is_file()
                and binding.get("byte_length") == candidate.stat().st_size
                and binding.get("sha256") == _sha256_file(candidate)
            )
            bindings_valid = bindings_valid and valid
    checks = {
        "status_pass": inventory.get("status") == "PASS",
        "entry_count_exact": inventory.get("entry_count")
        == len(entries)
        == len(EXPECTED_STAGE_IDS)
        == 21,
        "stage_sequence_exact": inventory.get("stage_sequence")
        == [
            str(row.get("stage_id") or "")
            for row in entries
            if isinstance(row, Mapping)
        ]
        == list(EXPECTED_STAGE_IDS),
        "sequence_numbers_exact": [
            row.get("sequence") for row in entries if isinstance(row, Mapping)
        ]
        == list(range(21)),
        "all_execution_complete": all(
            isinstance(row, Mapping) and row.get("execution_complete") is True
            for row in entries
        ),
        "status_map_exact": inventory.get("status_by_stage")
        == {
            str(row.get("stage_id") or ""): str(row.get("status") or "")
            for row in entries
            if isinstance(row, Mapping)
        },
        "ledger_parity": ledger_parity,
        "bindings_valid": bindings_valid,
        "ledger_semantic": _digest_valid(ledger),
        "recorded_checks_pass": bool(recorded_checks)
        and all(value is True for value in recorded_checks.values()),
    }
    _require(checks, label=f"contract_handoffs_invalid:{source.name}")
    return {"status": "PASS", "entry_count": 21}


def _verify_integrated_execution(
    *,
    manifest_path: Path,
    evidence_root: Path,
    run_inputs: Sequence[Mapping[str, Any]],
    source_manifest_builder: Callable[[Path | str], Mapping[str, Any]],
) -> dict[str, Any]:
    manifest = _read_json(manifest_path, label="integrated_execution_manifest")
    normalized = _normalize_inputs(run_inputs)
    cases = manifest.get("cases")
    cases = cases if isinstance(cases, list) else []
    expected_ids = [row["source_run"].name for row in normalized]
    case_ids = sorted(
        str(case.get("source_run_id") or "")
        for case in cases
        if isinstance(case, Mapping)
    )
    top_checks = {
        "schema_exact": manifest.get("schema_version") == INTEGRATED_EXECUTION_SCHEMA,
        "status_pass": manifest.get("status") == "PASS",
        "semantic_valid": _digest_valid(manifest),
        "mode_exact": manifest.get("qualification_mode")
        == "REAL_W0_W4_ZERO_PROVIDER_REPLAY",
        "two_real_cases": manifest.get("case_count") == 2
        and len(cases) == 2
        and case_ids == expected_ids,
        "wave_sequence_exact": manifest.get("wave_sequence")
        == ["W0", "W1", "W2", "W3", "W4"],
        "two_full_executions_per_run": manifest.get(
            "full_chain_execution_count_per_run"
        )
        == 2,
        "historical_judge_counts_exact": manifest.get(
            "historical_saved_judge_result_count"
        )
        == 42
        and manifest.get("historical_saved_judge_pass_count") == 42
        and manifest.get("historical_actual_claude_judge_result_count") == 0,
        "historical_model_route_counts_exact": manifest.get(
            "historical_apps_research_usage_event_count"
        )
        == 34
        and manifest.get("historical_apps_research_successful_attempt_count") == 6
        and manifest.get("historical_apps_research_claude_usage_event_count") == 0
        and manifest.get("historical_apps_rg_generation_lane_count") == 22
        and manifest.get("historical_apps_rg_target_claude_lane_count") == 22
        and manifest.get("historical_apps_rg_actual_claude_lane_count") == 0
        and manifest.get("historical_apps_rg_model_mismatch_lane_count") == 22
        and manifest.get("historical_apps_rg_recorded_token_budget_failure_lane_count")
        == 22
        and manifest.get(
            "historical_apps_rg_recomputed_output_token_budget_failure_lane_count"
        )
        == 0
        and manifest.get("historical_apps_rg_token_accounting_false_failure_lane_count")
        == 22,
        "contract_handoff_count_exact": manifest.get("contract_handoff_entry_count")
        == 42,
        "source_runs_preserved": manifest.get("source_runs_mutated") is False,
        "zero_execution_calls": _zero_top_level(manifest),
        "no_new_uwg": manifest.get("new_uwg_operations") == 0,
    }
    _require(top_checks, label="w5_integrated_manifest_invalid")

    by_source = {row["source_run"].name: row for row in normalized}
    record_ids: list[str] = []
    tree_digests: list[str] = []
    max_workers: list[int] = []
    saved_judge_results = 0
    contract_handoff_entries = 0
    model_route_counts = {
        "apps_research_usage_event_count": 0,
        "apps_research_successful_attempt_count": 0,
        "apps_research_claude_usage_event_count": 0,
        "apps_rg_generation_lane_count": 0,
        "apps_rg_target_claude_lane_count": 0,
        "apps_rg_actual_claude_lane_count": 0,
        "apps_rg_model_mismatch_lane_count": 0,
        "apps_rg_recorded_token_budget_failure_lane_count": 0,
        "apps_rg_recomputed_output_token_budget_failure_lane_count": 0,
        "apps_rg_token_accounting_false_failure_lane_count": 0,
    }
    for case_raw in cases:
        if not isinstance(case_raw, Mapping):
            raise ZeroLlmQualificationError("integrated_case_not_object")
        case = dict(case_raw)
        source_id = str(case.get("source_run_id") or "")
        run_input = by_source.get(source_id)
        if run_input is None:
            raise ZeroLlmQualificationError(
                f"integrated_case_source_unknown:{source_id}"
            )
        replay_ref = str(case.get("replay_root") or "")
        replay = (evidence_root / replay_ref).resolve()
        source = run_input["source_run"]
        if replay != run_input["replay_root"] or not _contained(replay, evidence_root):
            raise ZeroLlmQualificationError(
                f"integrated_case_replay_mismatch:{source_id}"
            )
        handoffs = case.get("handoffs")
        handoffs = dict(handoffs) if isinstance(handoffs, Mapping) else {}
        recorded_checks = case.get("checks")
        recorded_checks = (
            dict(recorded_checks) if isinstance(recorded_checks, Mapping) else {}
        )
        parallel = case.get("l0_parallel")
        parallel = dict(parallel) if isinstance(parallel, Mapping) else {}
        apps_eval = case.get("apps_eval")
        apps_eval = dict(apps_eval) if isinstance(apps_eval, Mapping) else {}
        l6 = case.get("l6")
        l6 = dict(l6) if isinstance(l6, Mapping) else {}
        terminal = case.get("terminal")
        terminal = dict(terminal) if isinstance(terminal, Mapping) else {}
        determinism = case.get("determinism")
        determinism = dict(determinism) if isinstance(determinism, Mapping) else {}
        paths = _artifact_map(
            case.get("artifacts"),
            root=evidence_root,
            expected_roles=INTEGRATED_ARTIFACT_ROLES,
            label=f"integrated_case:{source_id}",
        )
        docs = {
            role: _read_json(path, label=f"integrated:{source_id}:{role}")
            for role, path in paths.items()
        }
        current_tree = dict(source_manifest_builder(replay))
        source_tree = dict(source_manifest_builder(source))
        w0 = docs["w0_receipt"]
        guards = [docs[f"w{index}_guard"] for index in range(1, 5)]
        completion_sequence = [docs[f"w{index}_completion"] for index in range(1, 5)]
        terminal_manifest = docs["w4_terminal_manifest"]
        historical_judges = _verify_historical_saved_judges(
            inventory_raw=case.get("historical_saved_judges"),
            source=source,
        )
        historical_model_routes = _verify_historical_model_routes(
            inventory_raw=case.get("historical_model_routes"),
            source=source,
        )
        contract_handoffs = _verify_contract_handoffs(
            inventory_raw=case.get("contract_handoffs"),
            ledger=docs["w4_stage_ledger"],
            source=source,
            replay=replay,
        )
        dependencies = parallel.get("dependencies")
        dependencies = dict(dependencies) if isinstance(dependencies, Mapping) else {}
        lane_results_raw = parallel.get("lane_results")
        lane_results = lane_results_raw if isinstance(lane_results_raw, list) else []
        case_checks = {
            "status_pass": case.get("status") == "PASS",
            "wave_sequence_exact": case.get("wave_sequence")
            == ["W0", "W1", "W2", "W3", "W4"],
            "handoffs_exact": bool(handoffs)
            and all(value is True for value in handoffs.values()),
            "recorded_checks_pass": bool(recorded_checks)
            and all(value is True for value in recorded_checks.values()),
            "parallel_orchestration_real": parallel.get("parallel_overlap_proven")
            is True
            and int(parallel.get("max_active_workers_observed") or 0) > 1
            and parallel.get("provider_or_model_execution") is False
            and parallel.get("scheduler") == "concurrent.futures.ThreadPoolExecutor"
            and int(parallel.get("configured_max_parallel") or 0)
            >= int(parallel.get("max_active_workers_observed") or 0)
            and sorted(parallel.get("root_lanes") or [])
            == sorted(
                [
                    "competencies",
                    "ey_bullets",
                    "ibm_bullets",
                    "insurtech_bullets",
                    "unify_bullets",
                ]
            )
            and set(dependencies) == set(EXPECTED_LANES)
            and len(lane_results) == len(EXPECTED_LANES)
            and {
                str(row.get("lane") or "")
                for row in lane_results
                if isinstance(row, Mapping)
            }
            == set(EXPECTED_LANES)
            and all(
                isinstance(row, Mapping)
                and row.get("artifact_replay_complete") is True
                and str(row.get("artifact_binding_digest") or "").startswith("sha256:")
                for row in lane_results
            )
            and parallel.get("dependency_admission_semantics")
            == "saved_artifact_replay_complete_not_product_authority",
            "apps_eval_complete_fail": apps_eval.get("execution_complete") is True
            and apps_eval.get("verdict") == "fail"
            and apps_eval.get("release_blocked") is True
            and apps_eval.get("record_id") == case.get("record_id"),
            "l6_complete_fail": l6.get("execution_complete") is True
            and l6.get("binding_closure_status") == "FAIL"
            and l6.get("source_evidence_available_count") == 7
            and l6.get("source_evidence_unavailable_count") == 4
            and l6.get("calibration_status") == "NOT_MEASURED"
            and l6.get("human_labels_present") is False
            and l6.get("n_calibration_samples") == 0,
            "terminal_exact": terminal.get("terminal_outcome") == "BLOCKED_NON_PRODUCT"
            and terminal.get("terminal_closed") is True
            and terminal.get("stage_entry_count") == 21
            and terminal.get("x2_aggregation_status") == "PASS"
            and terminal.get("local_failure_event_count") == 17
            and terminal.get("l6_lane_event_count") == 11
            and terminal.get("l6_calibration_event_count") == 1
            and terminal.get("bound_receipt_count") == 38
            and terminal.get("remote_otel_role") == "OPTIONAL_MIRROR_NOT_AUTHORITY",
            "full_tree_deterministic": determinism.get("execution_count") == 2
            and determinism.get("full_tree_bytes_stable") is True
            and determinism.get("first_tree_sha256")
            == determinism.get("second_tree_sha256")
            == current_tree.get("content_sha256")
            and determinism.get("file_count") == current_tree.get("file_count")
            and determinism.get("total_bytes") == current_tree.get("total_bytes"),
            "source_still_unchanged": w0.get("source_manifest_sha256")
            == source_tree.get("content_sha256")
            and w0.get("source_unchanged") is True,
            "all_guards_zero": all(_guard_zero(guard) for guard in guards),
            "all_completions_semantic": all(
                _digest_valid(completion) for completion in completion_sequence
            ),
            "calibration_semantic": _digest_valid(docs["w3_calibration"]),
            "terminal_manifest_sealed": terminal_manifest.get("status") == "SEALED"
            and terminal_manifest.get("bound_receipt_count") == 38
            and _digest_valid(terminal_manifest, field="manifest_sha256"),
            "w4_package_sealed": docs["w4_package_seal"].get("status") == "PASS"
            and _digest_valid(docs["w4_package_seal"], field="manifest_sha256"),
            "historical_judges_complete": historical_judges.get("status") == "PASS"
            and historical_judges.get("result_count") == 21
            and historical_judges.get("passing_result_count") == 21
            and historical_judges.get("actual_claude_judge_result_count") == 0,
            "historical_model_routes_complete": historical_model_routes.get("status")
            == "PASS",
            "contract_handoffs_complete": contract_handoffs.get("status") == "PASS"
            and contract_handoffs.get("entry_count") == 21,
        }
        _require(case_checks, label=f"w5_integrated_case_invalid:{source_id}")
        record_ids.append(str(case["record_id"]))
        tree_digests.append(str(current_tree["content_sha256"]))
        max_workers.append(int(parallel["max_active_workers_observed"]))
        saved_judge_results += int(historical_judges["result_count"])
        contract_handoff_entries += int(contract_handoffs["entry_count"])
        for key in model_route_counts:
            model_route_counts[key] += int(historical_model_routes[key])

    _require(
        {"record_ids_unique": len(set(record_ids)) == 2},
        label="w5_integrated_identity_invalid",
    )
    return {
        "status": "PASS",
        "real_run_ids": expected_ids,
        "record_ids": record_ids,
        "replay_tree_digests": tree_digests,
        "max_active_workers_observed": max_workers,
        "real_run_count": 2,
        "apps_eval_record_count": 2,
        "l6_closure_count": 2,
        "terminal_manifest_count": 2,
        "full_chain_execution_count": 4,
        "historical_saved_judge_result_count": saved_judge_results,
        "historical_saved_judge_pass_count": saved_judge_results,
        "historical_actual_claude_judge_result_count": 0,
        "historical_apps_research_usage_event_count": model_route_counts[
            "apps_research_usage_event_count"
        ],
        "historical_apps_research_successful_attempt_count": model_route_counts[
            "apps_research_successful_attempt_count"
        ],
        "historical_apps_research_claude_usage_event_count": model_route_counts[
            "apps_research_claude_usage_event_count"
        ],
        "historical_apps_rg_generation_lane_count": model_route_counts[
            "apps_rg_generation_lane_count"
        ],
        "historical_apps_rg_target_claude_lane_count": model_route_counts[
            "apps_rg_target_claude_lane_count"
        ],
        "historical_apps_rg_actual_claude_lane_count": model_route_counts[
            "apps_rg_actual_claude_lane_count"
        ],
        "historical_apps_rg_model_mismatch_lane_count": model_route_counts[
            "apps_rg_model_mismatch_lane_count"
        ],
        "historical_apps_rg_recorded_token_budget_failure_lane_count": model_route_counts[
            "apps_rg_recorded_token_budget_failure_lane_count"
        ],
        "historical_apps_rg_recomputed_output_token_budget_failure_lane_count": model_route_counts[
            "apps_rg_recomputed_output_token_budget_failure_lane_count"
        ],
        "historical_apps_rg_token_accounting_false_failure_lane_count": model_route_counts[
            "apps_rg_token_accounting_false_failure_lane_count"
        ],
        "contract_handoff_entry_count": contract_handoff_entries,
    }


def _verify_fault_qualification(
    *,
    manifest_path: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    manifest = _read_json(
        manifest_path,
        label="production_fault_qualification_manifest",
    )
    recorded_checks = manifest.get("checks")
    recorded_checks = (
        dict(recorded_checks) if isinstance(recorded_checks, Mapping) else {}
    )
    paths = _artifact_map(
        manifest.get("artifacts"),
        root=evidence_root,
        expected_roles=FAULT_ARTIFACT_ROLES,
        label="production_fault_qualification",
    )
    docs = {
        role: _read_json(path, label=f"fault:{role}") for role, path in paths.items()
    }
    eval_error = docs["eval_error_receipt"]
    eval_span = docs["eval_error_span"]
    eval_resume = docs["eval_resume_receipt"]
    l6_error = docs["l6_error_receipt"]
    l6_span = docs["l6_error_span"]
    l6_resume = docs["l6_resume_receipt"]
    eval_binding = manifest.get("eval_resume_upstream_binding")
    eval_binding = dict(eval_binding) if isinstance(eval_binding, Mapping) else {}
    l6_binding = manifest.get("l6_resume_upstream_binding")
    l6_binding = dict(l6_binding) if isinstance(l6_binding, Mapping) else {}

    def _upstream_binding_valid(binding: Mapping[str, Any]) -> bool:
        ref = str(binding.get("artifact_ref") or "")
        candidate = (evidence_root / ref).resolve()
        return bool(
            ref
            and _contained(candidate, evidence_root)
            and candidate.is_file()
            and binding.get("unchanged") is True
            and binding.get("before_sha256")
            == binding.get("after_sha256")
            == _sha256_file(candidate)
        )

    checks = {
        "schema_exact": manifest.get("schema_version") == FAULT_QUALIFICATION_SCHEMA,
        "status_pass": manifest.get("status") == "PASS",
        "semantic_valid": _digest_valid(manifest),
        "real_boundaries": manifest.get("fault_injection_mode")
        == "REAL_PRODUCTION_STAGE_BOUNDARY",
        "recorded_checks_pass": bool(recorded_checks)
        and all(value is True for value in recorded_checks.values()),
        "eval_recovered": manifest.get("eval_failure_recovered") is True
        and manifest.get("eval_resume_scope") == "APPS_EVAL_ONLY_FROM_SAVED_W1"
        and _upstream_binding_valid(eval_binding),
        "l6_recovered": manifest.get("l6_failure_recovered") is True
        and manifest.get("l6_resume_scope") == "L6_ONLY_FROM_SAVED_W2"
        and _upstream_binding_valid(l6_binding),
        "terminal_recovered": manifest.get("terminal_closeout_after_recovery") is True
        and docs["terminal_completion"].get("terminal_outcome") == "BLOCKED_NON_PRODUCT"
        and docs["terminal_completion"].get("terminal_closed") is True,
        "qualification_calls_zero": _zero_top_level(manifest)
        and manifest.get("new_uwg_operations") == 0,
        "all_documents_semantic": all(_digest_valid(doc) for doc in docs.values()),
        "eval_error_durable": eval_error.get("status") == "CAPTURED"
        and eval_error.get("stage_id") == "APPS_EVAL"
        and eval_error.get("error_type") == "ProductionBoundaryFault"
        and eval_error.get("generation_retry_attempted") is False
        and eval_error.get("generation_replayed") is False
        and eval_error.get("judge_replayed") is False
        and eval_error.get("uwg_operation_attempted") is False,
        "eval_error_span_exact": eval_span.get("status") == "ERROR"
        and eval_span.get("trace_id") == eval_error.get("trace_id")
        and eval_span.get("span_id") == eval_error.get("span_id")
        and eval_span.get("provider_execution") is False
        and eval_span.get("generation_execution") is False
        and eval_span.get("judge_execution") is False
        and eval_span.get("uwg_execution") is False,
        "eval_resume_only": eval_resume.get("status") == "PASS"
        and eval_resume.get("resume_from_stage") == "APPS_EVAL"
        and eval_resume.get("w1_replayed") is False
        and eval_resume.get("generation_replayed") is False
        and eval_resume.get("judge_replayed") is False
        and eval_resume.get("uwg_operation_attempted") is False,
        "l6_error_durable": l6_error.get("status") == "CAPTURED"
        and l6_error.get("stage_id") == "L6_SHADOW_OBSERVABILITY"
        and l6_error.get("error_type") == "ProductionBoundaryFault"
        and l6_error.get("generation_replayed") is False
        and l6_error.get("apps_eval_replayed") is False
        and l6_error.get("judge_replayed") is False
        and l6_error.get("uwg_operation_attempted") is False,
        "l6_error_span_exact": l6_span.get("status") == "ERROR"
        and l6_span.get("trace_id") == l6_error.get("trace_id")
        and l6_span.get("span_id") == l6_error.get("span_id")
        and l6_span.get("provider_execution") is False
        and l6_span.get("generation_execution") is False
        and l6_span.get("judge_execution") is False
        and l6_span.get("uwg_execution") is False,
        "l6_resume_only": l6_resume.get("status") == "PASS"
        and l6_resume.get("resume_from_stage") == "L6_SHADOW_OBSERVABILITY"
        and l6_resume.get("w1_replayed") is False
        and l6_resume.get("w2_replayed") is False
        and l6_resume.get("apps_eval_replayed") is False
        and l6_resume.get("generation_replayed") is False
        and l6_resume.get("uwg_operation_attempted") is False,
        "fault_guards_failed_zero": _guard_zero(docs["eval_fault_guard"], status="FAIL")
        and _guard_zero(docs["l6_fault_guard"], status="FAIL"),
        "resume_guards_passed_zero": _guard_zero(docs["eval_success_guard"])
        and _guard_zero(docs["l6_success_guard"]),
    }
    _require(checks, label="w5_production_fault_qualification_invalid")
    return {
        "status": "PASS",
        "eval_failure_count": 1,
        "eval_recovery_count": 1,
        "l6_failure_count": 1,
        "l6_recovery_count": 1,
        "terminal_recovery_count": 1,
    }


def _verify_positive_control(
    *,
    manifest_path: Path,
    guard_path: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    if not _contained(manifest_path, evidence_root) or not _contained(
        guard_path, evidence_root
    ):
        raise ZeroLlmQualificationError("positive_control_outside_evidence_root")
    manifest = _read_json(manifest_path, label="positive_control_manifest")
    paths = _artifact_map(
        manifest.get("artifacts"),
        # The production positive-control contract owns a self-contained
        # package and therefore binds artifacts relative to its own root.
        root=manifest_path.parent,
        expected_roles=POSITIVE_ARTIFACT_ROLES,
        label="production_positive_control",
    )
    docs = {
        role: _read_json(path, label=f"positive:{role}") for role, path in paths.items()
    }
    guard = _read_json(guard_path, label="positive_control_guard")
    metadata = docs["fixture_metadata"]
    terminal = docs["terminal_state"]
    product_authorization = docs["product_authorization"]
    validators = manifest.get("production_validators")
    validators = validators if isinstance(validators, list) else []
    stage_docs = [
        docs[role]
        for role in sorted(POSITIVE_ARTIFACT_ROLES)
        if role.startswith("stage_authority_")
    ]
    checks = {
        "schema_exact": manifest.get("schema_version") == POSITIVE_CONTROL_SCHEMA,
        "status_pass": manifest.get("status") == "PASS",
        "semantic_valid": _digest_valid(manifest),
        "fixture_class_exact": manifest.get("fixture_class")
        == "DETERMINISTIC_GOVERNED_SAVED_OUTPUT",
        "qualification_only": manifest.get("qualification_only") is True,
        "no_real_authority_claim": manifest.get("production_authority_granted") is False
        and manifest.get("publication_allowed") is False,
        "no_execution_claim": manifest.get("provider_execution") is False
        and manifest.get("judge_execution") is False
        and manifest.get("embedding_execution") is False,
        "model_pin_not_claimed": manifest.get("model_pin_qualified") is False,
        "six_production_validators": len(validators) == 6
        and len(set(str(item) for item in validators)) == 6,
        "validator_results_pass": manifest.get("whole_run_exit_verified") is True
        and manifest.get("stage_authority_receipts_passed") == 6
        and manifest.get("product_eligibility_passed") is True
        and manifest.get("terminal_state_machine_passed") is True,
        "fixture_state_pass": manifest.get("fixture_product_authorized") is True
        and manifest.get("fixture_pipeline_complete") is True,
        "metadata_disclaims_authority": metadata.get("qualification_only") is True
        and metadata.get("saved_output_fixture") is True
        and metadata.get("provider_execution") is False
        and metadata.get("judge_execution") is False
        and metadata.get("embedding_execution") is False
        and metadata.get("model_pin_qualified") is False
        and metadata.get("production_authority_granted") is False
        and metadata.get("publication_allowed") is False,
        "whole_run_exit_pass": docs["whole_run_exit"].get("status") == "PASS"
        and docs["whole_run_exit"].get("x3_disposition") == "X3D_ALLOW_FINISH",
        "all_stage_authorities_pass": len(stage_docs) == 6
        and all(doc.get("status") == "PASS" for doc in stage_docs),
        "fixture_authorization_receipt": product_authorization.get("authorized")
        is True,
        "terminal_state_pass": terminal.get("status") == "PASS"
        and terminal.get("qualification_only") is True
        and terminal.get("fixture_product_authorized") is True
        and terminal.get("fixture_pipeline_complete") is True
        and terminal.get("production_authority_granted") is False
        and terminal.get("publication_allowed") is False,
        "guard_zero": _guard_zero(guard),
    }
    _require(checks, label="w5_production_positive_control_invalid")
    return {
        "status": "PASS",
        "fixture_class": manifest["fixture_class"],
        "production_validator_count": 6,
        "fixture_product_authorized": True,
        "fixture_pipeline_complete": True,
        "production_authority_granted": False,
        "publication_allowed": False,
    }


def _emit_tripwire_proof(
    *,
    output: Path,
    probe: Callable[[], Mapping[str, Any]],
) -> tuple[dict[str, Any], Path]:
    observed_raw = probe()
    observed = dict(observed_raw) if isinstance(observed_raw, Mapping) else {}
    counters = observed.get("controlled_attempt_counters")
    counters = dict(counters) if isinstance(counters, Mapping) else {}
    checks = {
        "probe_pass": observed.get("status") == "PASS",
        "provider_blocked": observed.get("provider_attempt_blocked") is True,
        "exception_exact": observed.get("exception_type") == "ProviderExecutionBlocked",
        "controlled_provider_attempt_exact": counters.get("provider_calls") == 1,
        "other_attempts_zero": all(
            counters.get(key) == 0
            for key in ZERO_COUNTER_KEYS
            if key != "provider_calls"
        ),
    }
    _require(checks, label="w5_provider_tripwire_invalid")
    payload: dict[str, Any] = {
        "schema_version": W5_TRIPWIRE_SCHEMA,
        "status": "PASS",
        "case_id": "provider_tripwire",
        "scope": "CONTROLLED_TRIPWIRE_PROBE_NOT_QUALIFICATION_ACTIVITY",
        "provider_attempt_blocked": True,
        "exception_type": "ProviderExecutionBlocked",
        "controlled_attempt_counters": counters,
        "qualification_attempt_counters_affected": False,
        "checks": checks,
    }
    path = _write_semantic(output / W5_TRIPWIRE_FILENAME, payload)
    return _read_json(path, label="provider_tripwire_proof"), path


def _verify_tripwire(path: Path) -> dict[str, Any]:
    proof = _read_json(path, label="provider_tripwire_proof")
    counters = proof.get("controlled_attempt_counters")
    counters = dict(counters) if isinstance(counters, Mapping) else {}
    checks = proof.get("checks")
    checks = dict(checks) if isinstance(checks, Mapping) else {}
    validations = {
        "schema_exact": proof.get("schema_version") == W5_TRIPWIRE_SCHEMA,
        "status_pass": proof.get("status") == "PASS",
        "semantic_valid": _digest_valid(proof),
        "scope_exact": proof.get("scope")
        == "CONTROLLED_TRIPWIRE_PROBE_NOT_QUALIFICATION_ACTIVITY",
        "provider_blocked": proof.get("provider_attempt_blocked") is True,
        "exception_exact": proof.get("exception_type") == "ProviderExecutionBlocked",
        "controlled_provider_attempt_exact": counters.get("provider_calls") == 1,
        "other_attempts_zero": all(
            counters.get(key) == 0
            for key in ZERO_COUNTER_KEYS
            if key != "provider_calls"
        ),
        "qualification_counters_unaffected": proof.get(
            "qualification_attempt_counters_affected"
        )
        is False,
        "recorded_checks_pass": bool(checks)
        and all(value is True for value in checks.values()),
    }
    _require(validations, label="w5_provider_tripwire_invalid")
    return {
        "status": "PASS",
        "controlled_provider_attempts": 1,
        "actual_provider_calls": 0,
    }


def _emit_counts(
    *,
    output: Path,
    integrated: Mapping[str, Any],
    faults: Mapping[str, Any],
    positive: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    payload: dict[str, Any] = {
        "schema_version": W5_COUNTS_SCHEMA,
        "status": "PASS",
        "integrated_real_runs": integrated["real_run_count"],
        "integrated_full_chain_executions": integrated["full_chain_execution_count"],
        "integrated_unique_apps_eval_records": integrated["apps_eval_record_count"],
        "integrated_l6_terminal_closures": integrated["l6_closure_count"],
        "integrated_non_product_terminal_manifests": integrated[
            "terminal_manifest_count"
        ],
        "historical_saved_judge_results": integrated[
            "historical_saved_judge_result_count"
        ],
        "historical_saved_judge_passes": integrated[
            "historical_saved_judge_pass_count"
        ],
        "historical_actual_claude_judge_results": integrated[
            "historical_actual_claude_judge_result_count"
        ],
        "historical_apps_research_usage_events": integrated[
            "historical_apps_research_usage_event_count"
        ],
        "historical_apps_research_successful_attempts": integrated[
            "historical_apps_research_successful_attempt_count"
        ],
        "historical_apps_research_claude_usage_events": integrated[
            "historical_apps_research_claude_usage_event_count"
        ],
        "historical_apps_rg_generation_lanes": integrated[
            "historical_apps_rg_generation_lane_count"
        ],
        "historical_apps_rg_target_claude_lanes": integrated[
            "historical_apps_rg_target_claude_lane_count"
        ],
        "historical_apps_rg_actual_claude_lanes": integrated[
            "historical_apps_rg_actual_claude_lane_count"
        ],
        "historical_apps_rg_model_mismatch_lanes": integrated[
            "historical_apps_rg_model_mismatch_lane_count"
        ],
        "historical_apps_rg_recorded_token_budget_failure_lanes": integrated[
            "historical_apps_rg_recorded_token_budget_failure_lane_count"
        ],
        "historical_apps_rg_recomputed_output_token_budget_failure_lanes": integrated[
            "historical_apps_rg_recomputed_output_token_budget_failure_lane_count"
        ],
        "historical_apps_rg_token_accounting_false_failure_lanes": integrated[
            "historical_apps_rg_token_accounting_false_failure_lane_count"
        ],
        "contract_handoff_entries": integrated["contract_handoff_entry_count"],
        "production_eval_faults": faults["eval_failure_count"],
        "production_eval_recoveries": faults["eval_recovery_count"],
        "production_l6_faults": faults["l6_failure_count"],
        "production_l6_recoveries": faults["l6_recovery_count"],
        "production_terminal_recoveries": faults["terminal_recovery_count"],
        "production_positive_control_cases": 1,
        "production_positive_validators": positive["production_validator_count"],
        "provider_calls": 0,
        "judge_calls": 0,
        "embedding_calls": 0,
        "model_calls": 0,
        "network_attempts": 0,
        "subprocess_attempts": 0,
        "new_uwg_operations": 0,
        "controlled_tripwire_provider_attempts": 1,
        "controlled_tripwire_attempts_excluded_from_execution_counts": True,
    }
    path = _write_semantic(output / W5_COUNTS_FILENAME, payload)
    return _read_json(path, label="qualification_counts"), path


def _verify_counts(counts: Mapping[str, Any]) -> None:
    checks = {
        "schema_exact": counts.get("schema_version") == W5_COUNTS_SCHEMA,
        "status_pass": counts.get("status") == "PASS",
        "semantic_valid": _digest_valid(counts),
        "real_runs_exact": counts.get("integrated_real_runs") == 2,
        "full_chain_executions_exact": counts.get("integrated_full_chain_executions")
        == 4,
        "eval_records_exact": counts.get("integrated_unique_apps_eval_records") == 2,
        "l6_closures_exact": counts.get("integrated_l6_terminal_closures") == 2,
        "terminal_manifests_exact": counts.get(
            "integrated_non_product_terminal_manifests"
        )
        == 2,
        "historical_judges_exact": counts.get("historical_saved_judge_results") == 42
        and counts.get("historical_saved_judge_passes") == 42
        and counts.get("historical_actual_claude_judge_results") == 0,
        "historical_model_routes_exact": counts.get(
            "historical_apps_research_usage_events"
        )
        == 34
        and counts.get("historical_apps_research_successful_attempts") == 6
        and counts.get("historical_apps_research_claude_usage_events") == 0
        and counts.get("historical_apps_rg_generation_lanes") == 22
        and counts.get("historical_apps_rg_target_claude_lanes") == 22
        and counts.get("historical_apps_rg_actual_claude_lanes") == 0
        and counts.get("historical_apps_rg_model_mismatch_lanes") == 22
        and counts.get("historical_apps_rg_recorded_token_budget_failure_lanes") == 22
        and counts.get(
            "historical_apps_rg_recomputed_output_token_budget_failure_lanes"
        )
        == 0
        and counts.get("historical_apps_rg_token_accounting_false_failure_lanes") == 22,
        "contract_handoffs_exact": counts.get("contract_handoff_entries") == 42,
        "faults_and_recoveries_exact": all(
            counts.get(key) == 1
            for key in (
                "production_eval_faults",
                "production_eval_recoveries",
                "production_l6_faults",
                "production_l6_recoveries",
                "production_terminal_recoveries",
            )
        ),
        "positive_control_exact": counts.get("production_positive_control_cases") == 1
        and counts.get("production_positive_validators") == 6,
        "execution_calls_zero": _zero_top_level(counts),
        "no_new_uwg": counts.get("new_uwg_operations") == 0,
        "tripwire_separate": counts.get("controlled_tripwire_provider_attempts") == 1
        and counts.get("controlled_tripwire_attempts_excluded_from_execution_counts")
        is True,
    }
    _require(checks, label="w5_qualification_counts_invalid")


def emit_w5_zero_llm_qualification(
    *,
    integrated_manifest_path: Path | str,
    fault_manifest_path: Path | str,
    positive_manifest_path: Path | str,
    positive_guard_path: Path | str,
    run_inputs: Sequence[Mapping[str, Any]],
    output_dir: Path | str,
    evidence_root: Path | str,
    source_manifest_builder: Callable[[Path | str], Mapping[str, Any]],
    provider_tripwire_probe: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate and seal production-path W5 evidence without LLM execution."""

    output = Path(output_dir).resolve()
    root = Path(evidence_root).resolve(strict=True)
    output.mkdir(parents=True, exist_ok=True)
    if not _contained(output, root):
        raise ZeroLlmQualificationError("qualification_outside_evidence_root")
    paths = {
        "integrated_execution_manifest": Path(integrated_manifest_path).resolve(
            strict=True
        ),
        "production_fault_qualification_manifest": Path(fault_manifest_path).resolve(
            strict=True
        ),
        "production_positive_control_manifest": Path(positive_manifest_path).resolve(
            strict=True
        ),
        "positive_control_zero_provider_guard": Path(positive_guard_path).resolve(
            strict=True
        ),
    }
    if not all(_contained(path, root) for path in paths.values()):
        raise ZeroLlmQualificationError("W5 input outside evidence root")

    integrated = _verify_integrated_execution(
        manifest_path=paths["integrated_execution_manifest"],
        evidence_root=root,
        run_inputs=run_inputs,
        source_manifest_builder=source_manifest_builder,
    )
    faults = _verify_fault_qualification(
        manifest_path=paths["production_fault_qualification_manifest"],
        evidence_root=root,
    )
    positive = _verify_positive_control(
        manifest_path=paths["production_positive_control_manifest"],
        guard_path=paths["positive_control_zero_provider_guard"],
        evidence_root=root,
    )
    _, tripwire_path = _emit_tripwire_proof(
        output=output,
        probe=provider_tripwire_probe,
    )
    tripwire = _verify_tripwire(tripwire_path)
    counts, counts_path = _emit_counts(
        output=output,
        integrated=integrated,
        faults=faults,
        positive=positive,
    )
    _verify_counts(counts)
    paths["provider_tripwire_proof"] = tripwire_path
    paths["qualification_counts"] = counts_path

    seal_body: dict[str, Any] = {
        "schema_version": W5_PACKAGE_SEAL_SCHEMA,
        "status": "PASS",
        "artifact_count": len(paths),
        "artifacts": [
            _binding(path, root=root, role=role) for role, path in sorted(paths.items())
        ],
    }
    seal_body["manifest_sha256"] = _canonical_digest(seal_body)
    seal_path = _atomic_write_json(output / W5_PACKAGE_SEAL_FILENAME, seal_body)

    completion_body: dict[str, Any] = {
        "schema_version": W5_COMPLETION_SCHEMA,
        "wave": "W5",
        "status": "PASS",
        "scope_complete": True,
        "w6_authorized": True,
        "qualification_mode": "PRODUCTION_PATH_ZERO_PROVIDER",
        "real_run_ids": integrated["real_run_ids"],
        "record_ids": integrated["record_ids"],
        "integrated_real_run_count": integrated["real_run_count"],
        "integrated_full_chain_execution_count": integrated[
            "full_chain_execution_count"
        ],
        "apps_eval_records": integrated["apps_eval_record_count"],
        "l6_terminal_closures": integrated["l6_closure_count"],
        "non_product_terminal_manifests": integrated["terminal_manifest_count"],
        "historical_saved_judge_results": integrated[
            "historical_saved_judge_result_count"
        ],
        "historical_saved_judge_passes": integrated[
            "historical_saved_judge_pass_count"
        ],
        "historical_actual_claude_judge_results": integrated[
            "historical_actual_claude_judge_result_count"
        ],
        "historical_apps_research_usage_events": integrated[
            "historical_apps_research_usage_event_count"
        ],
        "historical_apps_research_successful_attempts": integrated[
            "historical_apps_research_successful_attempt_count"
        ],
        "historical_apps_research_claude_usage_events": integrated[
            "historical_apps_research_claude_usage_event_count"
        ],
        "historical_apps_rg_generation_lanes": integrated[
            "historical_apps_rg_generation_lane_count"
        ],
        "historical_apps_rg_target_claude_lanes": integrated[
            "historical_apps_rg_target_claude_lane_count"
        ],
        "historical_apps_rg_actual_claude_lanes": integrated[
            "historical_apps_rg_actual_claude_lane_count"
        ],
        "historical_apps_rg_model_mismatch_lanes": integrated[
            "historical_apps_rg_model_mismatch_lane_count"
        ],
        "historical_apps_rg_recorded_token_budget_failure_lanes": integrated[
            "historical_apps_rg_recorded_token_budget_failure_lane_count"
        ],
        "historical_apps_rg_recomputed_output_token_budget_failure_lanes": integrated[
            "historical_apps_rg_recomputed_output_token_budget_failure_lane_count"
        ],
        "historical_apps_rg_token_accounting_false_failure_lanes": integrated[
            "historical_apps_rg_token_accounting_false_failure_lane_count"
        ],
        "contract_handoff_entries": integrated["contract_handoff_entry_count"],
        "production_fault_qualification": faults,
        "production_positive_control": positive,
        "provider_tripwire": tripwire,
        "provider_calls": 0,
        "judge_calls": 0,
        "embedding_calls": 0,
        "model_calls": 0,
        "network_attempts": 0,
        "subprocess_attempts": 0,
        "model_span_delta": 0,
        "source_files_changed": 0,
        "new_uwg_operations": 0,
        "live_generation_executed": False,
        "live_model_pin_qualified": False,
        "production_authority_granted": False,
        "publication_allowed": False,
        "qualification_counts": _binding(
            counts_path,
            root=root,
            role="qualification_counts",
        ),
        "w5_package_seal": _binding(
            seal_path,
            root=root,
            role="w5_package_seal",
        ),
    }
    completion_path = _write_semantic(
        output / W5_COMPLETION_FILENAME,
        completion_body,
    )
    completion = _read_json(completion_path, label="w5_completion")
    valid, errors = verify_w5_qualification(
        qualification_dir=output,
        evidence_root=root,
        run_inputs=run_inputs,
        source_manifest_builder=source_manifest_builder,
    )
    if not valid:
        raise ZeroLlmQualificationError(
            "w5_self_verification_failed:" + ",".join(errors)
        )
    return {
        "completion": completion,
        "completion_path": completion_path.as_posix(),
        "qualification_dir": output.as_posix(),
        "activity": {
            "apps_eval_executed": False,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
    }


def verify_w5_qualification(
    *,
    qualification_dir: Path | str,
    evidence_root: Path | str,
    run_inputs: Sequence[Mapping[str, Any]],
    source_manifest_builder: Callable[[Path | str], Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    """Reopen every W5 contract and all nested real replay tree bytes."""

    errors: list[str] = []
    try:
        output = Path(qualification_dir).resolve(strict=True)
        root = Path(evidence_root).resolve(strict=True)
        if not _contained(output, root):
            raise ZeroLlmQualificationError("qualification_outside_evidence_root")
        completion = _read_json(
            output / W5_COMPLETION_FILENAME,
            label="w5_completion",
        )
        counts_path = _resolve_binding(
            completion.get("qualification_counts"),
            root=root,
            label="w5_completion:qualification_counts",
        )
        seal_path = _resolve_binding(
            completion.get("w5_package_seal"),
            root=root,
            label="w5_completion:package_seal",
        )
        counts = _read_json(counts_path, label="qualification_counts")
        seal = _read_json(seal_path, label="w5_package_seal")
        seal_paths = _artifact_map(
            seal.get("artifacts"),
            root=root,
            expected_roles=W5_SEAL_ROLES,
            label="w5_package_seal",
        )
        completion_checks = {
            "schema_exact": completion.get("schema_version") == W5_COMPLETION_SCHEMA,
            "status_pass": completion.get("status") == "PASS",
            "semantic_valid": _digest_valid(completion),
            "scope_complete": completion.get("scope_complete") is True
            and completion.get("w6_authorized") is True,
            "mode_exact": completion.get("qualification_mode")
            == "PRODUCTION_PATH_ZERO_PROVIDER",
            "counts_exact": completion.get("integrated_real_run_count") == 2
            and completion.get("integrated_full_chain_execution_count") == 4
            and completion.get("apps_eval_records") == 2
            and completion.get("l6_terminal_closures") == 2
            and completion.get("non_product_terminal_manifests") == 2,
            "historical_judges_exact": completion.get("historical_saved_judge_results")
            == 42
            and completion.get("historical_saved_judge_passes") == 42
            and completion.get("historical_actual_claude_judge_results") == 0,
            "historical_model_routes_exact": completion.get(
                "historical_apps_research_usage_events"
            )
            == 34
            and completion.get("historical_apps_research_successful_attempts") == 6
            and completion.get("historical_apps_research_claude_usage_events") == 0
            and completion.get("historical_apps_rg_generation_lanes") == 22
            and completion.get("historical_apps_rg_target_claude_lanes") == 22
            and completion.get("historical_apps_rg_actual_claude_lanes") == 0
            and completion.get("historical_apps_rg_model_mismatch_lanes") == 22
            and completion.get("historical_apps_rg_recorded_token_budget_failure_lanes")
            == 22
            and completion.get(
                "historical_apps_rg_recomputed_output_token_budget_failure_lanes"
            )
            == 0
            and completion.get(
                "historical_apps_rg_token_accounting_false_failure_lanes"
            )
            == 22,
            "contract_handoffs_exact": completion.get("contract_handoff_entries") == 42,
            "execution_calls_zero": _zero_top_level(completion)
            and completion.get("model_span_delta") == 0
            and completion.get("source_files_changed") == 0
            and completion.get("new_uwg_operations") == 0,
            "no_live_claim": completion.get("live_generation_executed") is False
            and completion.get("live_model_pin_qualified") is False,
            "no_release_claim": completion.get("production_authority_granted") is False
            and completion.get("publication_allowed") is False,
            "seal_schema": seal.get("schema_version") == W5_PACKAGE_SEAL_SCHEMA,
            "seal_status": seal.get("status") == "PASS",
            "seal_count": seal.get("artifact_count") == len(W5_SEAL_ROLES),
            "seal_digest": _digest_valid(seal, field="manifest_sha256"),
        }
        _require(completion_checks, label="w5_completion_invalid")
        _verify_counts(counts)
        integrated = _verify_integrated_execution(
            manifest_path=seal_paths["integrated_execution_manifest"],
            evidence_root=root,
            run_inputs=run_inputs,
            source_manifest_builder=source_manifest_builder,
        )
        faults = _verify_fault_qualification(
            manifest_path=seal_paths["production_fault_qualification_manifest"],
            evidence_root=root,
        )
        positive = _verify_positive_control(
            manifest_path=seal_paths["production_positive_control_manifest"],
            guard_path=seal_paths["positive_control_zero_provider_guard"],
            evidence_root=root,
        )
        tripwire = _verify_tripwire(seal_paths["provider_tripwire_proof"])
        cross_checks = {
            "completion_run_ids": completion.get("real_run_ids")
            == integrated["real_run_ids"],
            "completion_record_ids": completion.get("record_ids")
            == integrated["record_ids"],
            "completion_faults": completion.get("production_fault_qualification")
            == faults,
            "completion_positive": completion.get("production_positive_control")
            == positive,
            "completion_tripwire": completion.get("provider_tripwire") == tripwire,
        }
        _require(cross_checks, label="w5_cross_contract_invalid")
    except (OSError, ValueError, ZeroLlmQualificationError) as exc:
        errors.append(str(exc))
    return not errors, sorted(set(errors))


__all__ = [
    "W5_COMPLETION_FILENAME",
    "W5_COMPLETION_SCHEMA",
    "W5_COUNTS_FILENAME",
    "W5_COUNTS_SCHEMA",
    "W5_PACKAGE_SEAL_FILENAME",
    "W5_PACKAGE_SEAL_SCHEMA",
    "W5_TRIPWIRE_FILENAME",
    "W5_TRIPWIRE_SCHEMA",
    "ZeroLlmQualificationError",
    "emit_w5_zero_llm_qualification",
    "verify_w5_qualification",
]
