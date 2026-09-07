"""Production-path, zero-provider prerequisites for W5 qualification.

This module executes the real W0-W4 artifact replay entrypoints, exercises the
real W2 and W3 exception boundaries, and builds one deterministic positive
fixture through production authority validators.  It never calls a provider,
judge, embedding model, network endpoint, subprocess, or UWG.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import json
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


INTEGRATED_EXECUTION_SCHEMA = "apps_rg.w5_integrated_execution.v2"
INTEGRATED_EXECUTION_FILENAME = "integrated_execution_manifest.json"
FAULT_QUALIFICATION_SCHEMA = "apps_rg.w5_production_fault_qualification.v1"
FAULT_QUALIFICATION_FILENAME = "production_fault_qualification_manifest.json"
POSITIVE_CONTROL_SCHEMA = "apps_rg.w5_production_positive_control.v1"
POSITIVE_CONTROL_FILENAME = "positive_control_manifest.json"
POSITIVE_COMPLETION_SCHEMA = "apps_rg.w5_positive_control_completion.v1"

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


class W5EndToEndPipelineError(RuntimeError):
    """Raised when a real replay or governed positive control does not close."""


class ProductionBoundaryFault(RuntimeError):
    """Controlled fault injected at a real production stage boundary."""


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
        raise W5EndToEndPipelineError(
            f"{label}_unreadable:{type(exc).__name__}:{path}"
        ) from exc
    if not isinstance(value, dict):
        raise W5EndToEndPipelineError(f"{label}_not_object:{path}")
    return value


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise W5EndToEndPipelineError(
            f"{label}_unreadable:{type(exc).__name__}:{path}"
        ) from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, TypeError) as exc:
            raise W5EndToEndPipelineError(
                f"{label}_invalid_json:{line_number}:{path}"
            ) from exc
        if not isinstance(value, dict):
            raise W5EndToEndPipelineError(f"{label}_not_object:{line_number}:{path}")
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


def _semantic_valid(payload: Mapping[str, Any]) -> bool:
    body = dict(payload)
    observed = str(body.pop("semantic_digest", "") or "")
    return bool(observed) and observed == _canonical_digest(body)


def _manifest_digest_valid(
    payload: Mapping[str, Any],
    *,
    field: str = "manifest_sha256",
) -> bool:
    body = dict(payload)
    observed = str(body.pop(field, "") or "")
    return bool(observed) and observed == _canonical_digest(body)


def _binding(path: Path, *, root: Path, role: str = "") -> dict[str, Any]:
    target = path.resolve(strict=True)
    parent = root.resolve(strict=True)
    if not _contained(target, parent):
        raise W5EndToEndPipelineError(f"artifact_outside_output:{target}")
    result: dict[str, Any] = {
        "artifact_ref": target.relative_to(parent).as_posix(),
        "byte_length": target.stat().st_size,
        "sha256": _sha256_file(target),
    }
    if role:
        result["artifact_role"] = role
    return result


def _require(checks: Mapping[str, bool], *, label: str) -> None:
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise W5EndToEndPipelineError(f"{label}:" + ",".join(failed))


def _dag_manifest_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "config/domain_contract/workflow_manifest.resume_sections.v1.yaml"
    )


def _saved_judge_inventory(source: Path) -> dict[str, Any]:
    """Inventory canonical saved judge results without executing a judge."""

    artifacts: list[tuple[str, Path]] = [
        (
            lane,
            source / "modular_r4/sections" / lane / "x1d_llm_judge_outputs.json",
        )
        for lane in EXPECTED_LANES
    ]
    artifacts.extend(
        [
            (
                "full_resume",
                source
                / "modular_r4/final_resume_assembly"
                / "x1d_full_resume_judge_outputs.json",
            ),
            (
                "competencies_graph_pool_selector",
                source
                / "modular_r4/sections/competencies"
                / "competencies_graph_pool_selector_receipt.json",
            ),
        ]
    )
    results: list[dict[str, Any]] = []
    for scope, path in artifacts:
        doc = _read_json(path, label=f"saved_judges:{scope}")
        raw_judges = doc.get("judges")
        if isinstance(raw_judges, Mapping):
            judges = [dict(raw_judges)]
        elif isinstance(raw_judges, list):
            judges = [dict(row) for row in raw_judges if isinstance(row, Mapping)]
        else:
            judges = []
        for judge in judges:
            passed = judge.get("pass")
            if not isinstance(passed, bool):
                passed = judge.get("pass_")
            results.append(
                {
                    "scope": scope,
                    "judge_id": str(judge.get("judge_id") or ""),
                    "provider_name": str(judge.get("provider_name") or ""),
                    "provider_key": str(judge.get("provider_key") or ""),
                    "evaluator_mode": str(judge.get("evaluator_mode") or ""),
                    "provider_status": str(judge.get("provider_status") or ""),
                    "model_requested": str(judge.get("model_requested") or ""),
                    "model_actual": str(
                        judge.get("model_actual") or judge.get("model_name") or ""
                    ),
                    "pass": passed is True,
                    "provider_available": judge.get("provider_available") is True,
                    "provider_blocked": judge.get("provider_blocked") is True,
                    "mocked": judge.get("mocked") is True,
                    "advisory_only": judge.get("advisory_only") is True,
                    "proof_eligible_judge": judge.get("proof_eligible_judge") is True,
                    "fallback_used": judge.get("fallback_used") is True,
                    "artifact_ref": path.relative_to(source).as_posix(),
                    "artifact_sha256": _sha256_file(path),
                }
            )

    alias_lanes = (
        "competencies",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "ey_bullets",
    )
    legacy_aliases: list[dict[str, Any]] = []
    for lane in alias_lanes:
        path = (
            source
            / "modular_r4/sections"
            / lane
            / "bullet_pool_claude_selector_judge.json"
        )
        judge = _read_json(path, label=f"legacy_selector_alias:{lane}")
        legacy_aliases.append(
            {
                "scope": lane,
                "artifact_ref": path.relative_to(source).as_posix(),
                "artifact_sha256": _sha256_file(path),
                "judge_id": str(judge.get("judge_id") or ""),
                "provider_name": str(judge.get("provider_name") or ""),
                "model_actual": str(
                    judge.get("model_actual") or judge.get("model_name") or ""
                ),
                "provider_status": str(judge.get("provider_status") or ""),
                "pass": judge.get("pass") is True,
                "legacy_filename_only": True,
            }
        )

    model_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    for row in results:
        model = str(row["model_actual"])
        provider = str(row["provider_name"])
        model_counts[model] = model_counts.get(model, 0) + 1
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
    claude_results = [
        row for row in results if "claude" in str(row["model_actual"]).lower()
    ]
    checks = {
        "canonical_result_count_exact": len(results) == 21,
        "all_results_model_backed_pass": all(
            row["pass"] is True
            and row["evaluator_mode"] == "MODEL_BACKED"
            and row["provider_status"] == "MODEL_BACKED_PASS"
            and row["provider_available"] is True
            and row["provider_blocked"] is False
            and row["mocked"] is False
            and row["fallback_used"] is False
            for row in results
        ),
        "model_counts_exact": model_counts
        == {"gemini-3.6-flash": 12, "gpt-5.6-sol": 9},
        "provider_counts_exact": provider_counts
        == {"Google Gemini 3.6 Flash": 12, "OpenAI ChatGPT": 9},
        "no_claude_model_result": not claude_results,
        "legacy_alias_count_exact": len(legacy_aliases) == 5,
        "legacy_aliases_are_openai": all(
            row["model_actual"] == "gpt-5.6-sol"
            and row["provider_name"] == "OpenAI ChatGPT"
            and row["provider_status"] == "MODEL_BACKED_PASS"
            and row["pass"] is True
            for row in legacy_aliases
        ),
    }
    _require(checks, label=f"saved_judge_inventory_invalid:{source.name}")
    return {
        "evidence_scope": ("HISTORICAL_SAVED_JUDGE_OUTPUTS_NO_W5_JUDGE_EXECUTION"),
        "status": "PASS",
        "result_count": len(results),
        "passing_result_count": sum(row["pass"] is True for row in results),
        "advisory_result_count": sum(row["advisory_only"] is True for row in results),
        "model_counts": dict(sorted(model_counts.items())),
        "provider_counts": dict(sorted(provider_counts.items())),
        "actual_claude_judge_result_count": len(claude_results),
        "legacy_claude_named_artifact_count": len(legacy_aliases),
        "legacy_claude_named_artifacts": legacy_aliases,
        "results": results,
        "checks": checks,
    }


def _historical_model_route_inventory(source: Path) -> dict[str, Any]:
    """Seal historical research and generation model-route evidence.

    The inventory is deliberately diagnostic: ``status=PASS`` means every
    source byte and expected failure was accounted for.  It does not convert
    the historical Apps RG generation routes into successful authority.
    """

    ledger_path = source / "apps_research/runs/external_model_usage_ledger.jsonl"
    events = _read_jsonl(ledger_path, label="apps_research_usage_ledger")
    event_model_counts: dict[str, int] = {}
    event_provider_counts: dict[str, int] = {}
    claude_events: list[dict[str, Any]] = []
    for event in events:
        model = str(event.get("model") or event.get("requested_model") or "")
        provider = str(event.get("provider") or "")
        event_model_counts[model] = event_model_counts.get(model, 0) + 1
        event_provider_counts[provider] = event_provider_counts.get(provider, 0) + 1
        if any(
            "claude" in str(event.get(field) or "").lower()
            for field in ("model", "requested_model", "observed_model", "provider")
        ):
            claude_events.append(event)

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

    lane_rows: list[dict[str, Any]] = []
    for lane in EXPECTED_LANES:
        lane_root = source / "modular_r4/sections" / lane
        paths = {
            "l2_execution_packet": lane_root / "l2_execution_packet.json",
            "attempt_receipt": lane_root / "attempt_receipt.json",
            "provider_request": lane_root / "provider_request.json",
            "provider_response": lane_root / "provider_response.json",
            "l2_handoff_receipt": lane_root / "l2_handoff_receipt.json",
        }
        docs = {
            role: _read_json(path, label=f"model_route:{lane}:{role}")
            for role, path in paths.items()
        }
        packet = docs["l2_execution_packet"]
        attempt = docs["attempt_receipt"]
        request = docs["provider_request"]
        response = docs["provider_response"]
        handoff = docs["l2_handoff_receipt"]
        budget = packet.get("budget")
        budget = dict(budget) if isinstance(budget, Mapping) else {}
        local = attempt.get("local_check_results")
        local = dict(local) if isinstance(local, Mapping) else {}
        handoff_checks = handoff.get("checks")
        handoff_checks = (
            dict(handoff_checks) if isinstance(handoff_checks, Mapping) else {}
        )
        provider_envelope = response.get("provider_response")
        provider_envelope = (
            dict(provider_envelope) if isinstance(provider_envelope, Mapping) else {}
        )
        transport = provider_envelope.get("transport_response")
        transport = dict(transport) if isinstance(transport, Mapping) else {}
        raw_response = transport.get("raw_response")
        raw_response = dict(raw_response) if isinstance(raw_response, Mapping) else {}
        usage = raw_response.get("usage")
        usage = dict(usage) if isinstance(usage, Mapping) else {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)
        ceiling = int(budget.get("max_tokens") or 0)
        lane_rows.append(
            {
                "lane": lane,
                "signed_target_model": str(packet.get("target_model") or ""),
                "signed_canonical_provider": str(
                    packet.get("canonical_provider") or ""
                ),
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
                "handoff_provider_lane_used": str(
                    handoff.get("provider_lane_used") or ""
                ),
                "handoff_tokens_recorded": int(handoff.get("tokens_emitted") or 0),
                "recorded_model_id_matches": handoff_checks.get("model_id_matches")
                is True,
                "recorded_token_budget_pass": handoff_checks.get("token_budget_pass")
                is True,
                "recomputed_output_token_budget_pass": output_tokens <= ceiling,
                "handoff_status": str(handoff.get("handoff_status") or ""),
                "artifacts": [
                    _binding(path, root=source, role=role)
                    for role, path in sorted(paths.items())
                ],
            }
        )

    checks = {
        "apps_research_event_count_exact": len(events) == 17,
        "apps_research_event_models_exact": event_model_counts
        == {"gemini-3.6-flash": 7, "gpt-5.6-terra": 10},
        "apps_research_event_providers_exact": event_provider_counts
        == {"external_openai": 10, "google_gemini": 7},
        "apps_research_successful_attempts_exact": len(successful_attempts) == 3
        and success_model_counts == {"gemini-3.6-flash": 1, "gpt-5.6-terra": 2}
        and all(
            attempt["requested_model"] == attempt["observed_model"]
            and attempt["model_pin_valid"] is True
            and attempt["overall_success"] is True
            and attempt["application_output_valid"] is True
            and attempt["response_schema_valid"] is True
            and attempt["provider_status"] == "VALIDATED_SUCCESS"
            for attempt in successful_attempts
        ),
        "apps_research_no_claude": not claude_events,
        "apps_rg_lane_count_exact": len(lane_rows) == len(EXPECTED_LANES),
        "apps_rg_lane_ids_exact": {row["lane"] for row in lane_rows}
        == set(EXPECTED_LANES),
        "apps_rg_signed_claude_but_openai_route_exact": all(
            row["signed_target_model"] == "claude-sonnet-5"
            and row["signed_allowed_models"] == ["claude-sonnet-5"]
            and row["signed_canonical_provider"] == "openai"
            and row["attempt_claimed_model"] == "claude-sonnet-5"
            and row["attempt_claimed_provider_lane"] == "openai"
            and row["provider_requested"] == "external_openai"
            and row["provider_request_model"] == "gpt-5.6-luna"
            and row["provider_response_model"] == "gpt-5.6-luna"
            and row["handoff_model_id_used"] == "gpt-5.6-luna"
            and row["handoff_provider_lane_used"] == "openai"
            for row in lane_rows
        ),
        "apps_rg_real_provider_outputs_exact": all(
            row["runtime_generation_status"] == "REAL_LLM"
            and row["provider_attempted"] is True
            and row["provider_available"] is True
            and row["stub"] is False
            for row in lane_rows
        ),
        "apps_rg_recorded_model_failures_exact": all(
            row["recorded_model_id_matches"] is False
            and row["handoff_status"] == "FAIL"
            for row in lane_rows
        ),
        "apps_rg_total_token_accounting_reproduced": all(
            row["observed_input_tokens"] + row["observed_output_tokens"]
            == row["observed_total_tokens"]
            == row["handoff_tokens_recorded"]
            for row in lane_rows
        ),
        "apps_rg_recorded_budget_failures_are_false": all(
            row["recorded_token_budget_pass"] is False
            and row["recomputed_output_token_budget_pass"] is True
            for row in lane_rows
        ),
    }
    _require(checks, label=f"historical_model_route_inventory_invalid:{source.name}")
    return {
        "evidence_scope": "HISTORICAL_SAVED_MODEL_ROUTES_NO_W5_MODEL_EXECUTION",
        "status": "PASS",
        "routing_outcome": "FAIL_MODEL_PIN_MISMATCH",
        "token_accounting_outcome": "FALSE_FAILURE_TOTAL_VS_OUTPUT",
        "apps_research": {
            "usage_event_count": len(events),
            "usage_event_model_counts": dict(sorted(event_model_counts.items())),
            "usage_event_provider_counts": dict(sorted(event_provider_counts.items())),
            "successful_attempt_count": len(successful_attempts),
            "successful_attempt_model_counts": dict(
                sorted(success_model_counts.items())
            ),
            "claude_usage_event_count": len(claude_events),
            "successful_attempts": successful_attempts,
            "ledger_artifact": _binding(
                ledger_path,
                root=source,
                role="apps_research_external_model_usage_ledger",
            ),
        },
        "apps_rg_generation": {
            "lane_count": len(lane_rows),
            "target_claude_lane_count": sum(
                row["signed_target_model"] == "claude-sonnet-5" for row in lane_rows
            ),
            "actual_claude_lane_count": sum(
                "claude" in str(row["provider_response_model"]).lower()
                for row in lane_rows
            ),
            "model_mismatch_lane_count": sum(
                row["recorded_model_id_matches"] is False for row in lane_rows
            ),
            "recorded_token_budget_failure_lane_count": sum(
                row["recorded_token_budget_pass"] is False for row in lane_rows
            ),
            "recomputed_output_token_budget_failure_lane_count": sum(
                row["recomputed_output_token_budget_pass"] is False for row in lane_rows
            ),
            "token_accounting_false_failure_lane_count": sum(
                row["recorded_token_budget_pass"] is False
                and row["recomputed_output_token_budget_pass"] is True
                for row in lane_rows
            ),
            "lanes": lane_rows,
        },
        "artifact_count": 1 + (len(lane_rows) * 5),
        "checks": checks,
    }


def _stage_contract_inventory(
    *,
    source: Path,
    replay: Path,
    ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Reopen every terminal-ledger handoff binding byte-for-byte."""

    raw_entries = ledger.get("entries")
    raw_entries = raw_entries if isinstance(raw_entries, list) else []
    entries: list[dict[str, Any]] = []
    all_bindings_valid = True
    for entry_raw in raw_entries:
        if not isinstance(entry_raw, Mapping):
            all_bindings_valid = False
            continue
        bindings_raw = entry_raw.get("evidence_bindings")
        bindings_raw = bindings_raw if isinstance(bindings_raw, list) else []
        bindings: list[dict[str, Any]] = []
        for binding_raw in bindings_raw:
            if not isinstance(binding_raw, Mapping):
                all_bindings_valid = False
                continue
            binding = dict(binding_raw)
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
                authority_root is not None
                and ref
                and _contained(candidate, authority_root)
                and candidate.is_file()
                and binding.get("byte_length") == candidate.stat().st_size
                and binding.get("sha256") == _sha256_file(candidate)
            )
            all_bindings_valid = all_bindings_valid and valid
            bindings.append({**binding, "binding_valid": valid})
        entries.append(
            {
                "sequence": entry_raw.get("sequence"),
                "stage_id": str(entry_raw.get("stage_id") or ""),
                "status": str(entry_raw.get("status") or ""),
                "execution_complete": entry_raw.get("execution_complete") is True,
                "governed_outcome": str(entry_raw.get("governed_outcome") or ""),
                "authority_effect": str(entry_raw.get("authority_effect") or ""),
                "evidence_bindings": bindings,
            }
        )
    checks = {
        "entry_count_exact": len(entries) == len(EXPECTED_STAGE_IDS) == 21,
        "stage_sequence_exact": [row["stage_id"] for row in entries]
        == list(EXPECTED_STAGE_IDS),
        "sequence_numbers_exact": [row["sequence"] for row in entries]
        == list(range(21)),
        "all_stages_execution_complete": all(
            row["execution_complete"] is True for row in entries
        ),
        "all_stages_have_evidence": all(
            bool(row["evidence_bindings"]) for row in entries
        ),
        "all_evidence_bindings_valid": all_bindings_valid,
    }
    _require(checks, label=f"stage_contract_inventory_invalid:{source.name}")
    return {
        "status": "PASS",
        "entry_count": len(entries),
        "stage_sequence": [row["stage_id"] for row in entries],
        "status_by_stage": {row["stage_id"]: row["status"] for row in entries},
        "entries": entries,
        "checks": checks,
    }


def _install_minimal_apps_rg_namespace() -> None:
    """Load runtime modules without executing broad apps_rg initializers."""

    existing = sys.modules.get("apps_rg")
    if existing is not None:
        return
    apps_root = Path(__file__).resolve().parents[1]
    packages = {
        "apps_rg": apps_root,
        "apps_rg.runtime": apps_root / "runtime",
    }
    for name, path in packages.items():
        module = ModuleType(name)
        module.__package__ = name
        module.__path__ = [path.as_posix()]
        spec = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
        spec.submodule_search_locations = [path.as_posix()]
        module.__spec__ = spec
        module._apps_rg_minimal_runtime_namespace = True
        sys.modules[name] = module


def _run_chain_once(*, source: Path, output_root: Path) -> dict[str, Any]:
    _install_minimal_apps_rg_namespace()
    from apps_rg.runtime.apps_eval_replay import emit_w2_apps_eval_replay
    from apps_rg.runtime.authority_reconciliation import (
        emit_w1_authority_reconciliation,
    )
    from apps_rg.runtime.l6_shadow_replay import emit_w3_l6_shadow_replay
    from apps_rg.runtime.post_runtime_replay import (
        run_guarded_artifact_replay,
        run_w0_zero_provider_preflight,
    )
    from apps_rg.runtime.terminal_closeout_replay import (
        emit_w4_terminal_closeout_replay,
    )

    w0 = run_w0_zero_provider_preflight(
        source_run=source,
        output_root=output_root,
        require_clean_import_state=True,
    )

    def w1_operation(run: Path, output: Path) -> Mapping[str, Any]:
        return emit_w1_authority_reconciliation(
            source_run=run,
            output_dir=output,
            dag_manifest_path=_dag_manifest_path(),
        )

    w1 = run_guarded_artifact_replay(
        source_run=source,
        output_root=output_root,
        wave="W1",
        operation=w1_operation,
        receipt_filename="w1_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
    )

    def w2_operation(run: Path, output: Path) -> Mapping[str, Any]:
        return emit_w2_apps_eval_replay(source_run=run, output_dir=output)

    w2 = run_guarded_artifact_replay(
        source_run=source,
        output_root=output_root,
        wave="W2",
        operation=w2_operation,
        receipt_filename="w2_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
        expected_activity={
            "apps_eval_executed": True,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
    )

    def w3_operation(run: Path, output: Path) -> Mapping[str, Any]:
        return emit_w3_l6_shadow_replay(source_run=run, output_dir=output)

    w3 = run_guarded_artifact_replay(
        source_run=source,
        output_root=output_root,
        wave="W3",
        operation=w3_operation,
        receipt_filename="w3_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
        expected_activity={
            "apps_eval_executed": False,
            "l6_executed": True,
            "uwg_operation_attempted": False,
        },
    )

    def w4_operation(run: Path, output: Path) -> Mapping[str, Any]:
        return emit_w4_terminal_closeout_replay(
            source_run=run,
            output_dir=output,
        )

    w4 = run_guarded_artifact_replay(
        source_run=source,
        output_root=output_root,
        wave="W4",
        operation=w4_operation,
        receipt_filename="w4_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
        expected_activity={
            "apps_eval_executed": False,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
    )
    return {"W0": w0, "W1": w1, "W2": w2, "W3": w3, "W4": w4}


def _chain_contract(*, source: Path, replay: Path, output: Path) -> dict[str, Any]:
    paths = {
        "w0_receipt": replay / "w0_zero_provider_preflight_receipt.json",
        "w1_guard": replay / "w1/w1_zero_provider_guard_receipt.json",
        "w1_completion": replay / "w1/w1_completion_receipt.json",
        "w1_parallel": replay / "w1/w1_l0_parallel_replay_proof.json",
        "w2_guard": replay / "w2/w2_zero_provider_guard_receipt.json",
        "w2_completion": replay / "w2/w2_completion_receipt.json",
        "w3_guard": replay / "w3/w3_zero_provider_guard_receipt.json",
        "w3_completion": replay / "w3/w3_completion_receipt.json",
        "w3_calibration": replay / "w3/l6_judge_human_calibration_status.json",
        "w4_guard": replay / "w4/w4_zero_provider_guard_receipt.json",
        "w4_completion": replay / "w4/w4_completion_receipt.json",
        "w4_stage_ledger": replay / "w4/terminal_stage_ledger.json",
        "w4_terminal_manifest": replay / "w4/terminal_non_product_manifest.json",
        "w4_package_seal": replay / "w4/w4_terminal_closeout_package_seal.json",
    }
    docs = {role: _read_json(path, label=role) for role, path in paths.items()}
    w0 = docs["w0_receipt"]
    w1 = docs["w1_completion"]
    w1_parallel = docs["w1_parallel"]
    w2 = docs["w2_completion"]
    w3 = docs["w3_completion"]
    calibration = docs["w3_calibration"]
    w4 = docs["w4_completion"]
    terminal_manifest = docs["w4_terminal_manifest"]
    w4_package_seal = docs["w4_package_seal"]
    historical_judges = _saved_judge_inventory(source)
    historical_model_routes = _historical_model_route_inventory(source)
    stage_contracts = _stage_contract_inventory(
        source=source,
        replay=replay,
        ledger=docs["w4_stage_ledger"],
    )
    guards = [docs[f"w{index}_guard"] for index in range(1, 5)]
    zero_keys = (
        "provider_calls",
        "judge_calls",
        "embedding_calls",
        "model_calls",
        "network_attempts",
        "subprocess_attempts",
    )
    handoffs = {
        "w0_to_w1_source_identity": w0.get("source_run_id")
        == w1.get("source_run_id")
        == source.name,
        "w1_to_w2": w2.get("w1_completion_semantic_digest")
        == w1.get("semantic_digest"),
        "w2_to_w3": w3.get("w2_completion_semantic_digest")
        == w2.get("semantic_digest"),
        "w3_to_w4": w4.get("w3_completion_semantic_digest")
        == w3.get("semantic_digest"),
    }
    checks = {
        "all_docs_semantic": all(
            _semantic_valid(doc)
            for name, doc in docs.items()
            if name not in {"w4_terminal_manifest", "w4_package_seal"}
        ),
        "all_wave_guards_pass": all(guard.get("status") == "PASS" for guard in guards),
        "all_wave_counters_zero": all(
            all(guard.get(key) == 0 for key in zero_keys) for guard in guards
        ),
        "handoffs_exact": all(handoffs.values()),
        "l0_parallel_real": w1_parallel.get("status") == "PASS"
        and w1_parallel.get("parallel_overlap_proven") is True
        and int(w1_parallel.get("max_active_workers_observed") or 0) > 1
        and w1_parallel.get("provider_or_model_execution") is False,
        "w2_exact": w2.get("eval_execution_complete") is True
        and w2.get("eval_verdict") == "fail"
        and w2.get("release_blocked") is True
        and w2.get("preflight_verification_status") == "UNVERIFIABLE_KEY_MATERIAL",
        "w3_exact": w3.get("l6_execution_complete") is True
        and w3.get("binding_closure_status") == "FAIL"
        and w3.get("section_summary", {}).get("sections_total") == len(EXPECTED_LANES)
        and calibration.get("calibration_status") == "NOT_MEASURED"
        and calibration.get("human_labels_present") is False
        and calibration.get("n_calibration_samples") == 0,
        "w4_exact": w4.get("terminal_outcome") == "BLOCKED_NON_PRODUCT"
        and w4.get("terminal_closed") is True
        and w4.get("stage_summary", {}).get("entry_count") == 21
        and w4.get("stage_summary", {}).get("x2_aggregation_status") == "PASS",
        "w4_terminal_manifest_exact": terminal_manifest.get("schema_version")
        == "apps_rg.terminal_non_product_manifest.v1"
        and terminal_manifest.get("status") == "SEALED"
        and terminal_manifest.get("manifest_type") == "TERMINAL_NON_PRODUCT"
        and terminal_manifest.get("bound_receipt_count") == 38
        and terminal_manifest.get("remote_otel_role") == "OPTIONAL_MIRROR_NOT_AUTHORITY"
        and _manifest_digest_valid(terminal_manifest),
        "w4_package_seal_exact": w4_package_seal.get("schema_version")
        == "apps_rg.terminal_closeout_package_seal.v1"
        and w4_package_seal.get("status") == "PASS"
        and _manifest_digest_valid(w4_package_seal),
        "historical_judge_inventory_complete": historical_judges.get("status") == "PASS"
        and historical_judges.get("result_count") == 21
        and historical_judges.get("passing_result_count") == 21,
        "historical_model_route_inventory_complete": historical_model_routes.get(
            "status"
        )
        == "PASS"
        and historical_model_routes.get("routing_outcome") == "FAIL_MODEL_PIN_MISMATCH"
        and historical_model_routes.get("token_accounting_outcome")
        == "FALSE_FAILURE_TOTAL_VS_OUTPUT",
        "stage_contract_inventory_complete": stage_contracts.get("status") == "PASS"
        and stage_contracts.get("entry_count") == 21,
    }
    _require(checks, label=f"integrated_chain_invalid:{source.name}")
    return {
        "source_run_id": source.name,
        "replay_root": replay.relative_to(output).as_posix(),
        "record_id": w2["record_id"],
        "status": "PASS",
        "wave_sequence": ["W0", "W1", "W2", "W3", "W4"],
        "handoffs": handoffs,
        "l0_parallel": {
            "parallel_overlap_proven": True,
            "max_active_workers_observed": w1_parallel["max_active_workers_observed"],
            "provider_or_model_execution": False,
            "scheduler": w1_parallel["scheduler"],
            "configured_max_parallel": w1_parallel["configured_max_parallel"],
            "root_lanes": w1_parallel["root_lanes"],
            "dependencies": w1_parallel["dependencies"],
            "lane_results": w1_parallel["lane_results"],
            "dependency_admission_semantics": w1_parallel[
                "dependency_admission_semantics"
            ],
        },
        "historical_saved_judges": historical_judges,
        "historical_model_routes": historical_model_routes,
        "contract_handoffs": stage_contracts,
        "apps_eval": {
            "execution_complete": True,
            "verdict": "fail",
            "release_blocked": True,
            "record_id": w2["record_id"],
        },
        "l6": {
            "execution_complete": True,
            "binding_closure_status": "FAIL",
            "source_evidence_available_count": w3["section_summary"][
                "sections_source_evidence_available"
            ],
            "source_evidence_unavailable_count": w3["section_summary"][
                "sections_source_evidence_unavailable"
            ],
            "calibration_status": "NOT_MEASURED",
            "human_labels_present": False,
            "n_calibration_samples": 0,
        },
        "terminal": {
            "terminal_outcome": "BLOCKED_NON_PRODUCT",
            "terminal_closed": True,
            "stage_entry_count": 21,
            "x2_aggregation_status": "PASS",
            "local_failure_event_count": w4["telemetry_summary"]["event_count"],
            "l6_lane_event_count": w4["telemetry_summary"]["l6_lane_event_count"],
            "l6_calibration_event_count": w4["telemetry_summary"][
                "l6_calibration_event_count"
            ],
            "bound_receipt_count": terminal_manifest["bound_receipt_count"],
            "remote_otel_role": terminal_manifest["remote_otel_role"],
        },
        "checks": checks,
        "artifacts": [
            _binding(path, root=output, role=role)
            for role, path in sorted(paths.items())
        ],
    }


def execute_integrated_replays(
    *,
    source_runs: Sequence[Path | str],
    output_dir: Path | str,
) -> dict[str, Any]:
    """Execute the complete W0-W4 path twice and compare all derived bytes."""

    if len(source_runs) != 2:
        raise W5EndToEndPipelineError("integrated W5 replay requires two runs")
    sources = sorted(
        (Path(source).resolve(strict=True) for source in source_runs),
        key=lambda path: path.name,
    )
    output = Path(output_dir).resolve()
    # Keep internal roots deliberately short. Apps Eval's sealed package paths
    # are already deep enough to approach legacy Windows MAX_PATH limits.
    replay_output = output / "i"
    first_manifests: dict[str, Mapping[str, Any]] = {}
    final_replay_roots: dict[str, Path] = {}

    _install_minimal_apps_rg_namespace()
    from apps_rg.runtime.post_runtime_replay import build_source_manifest

    for source in sources:
        receipts = _run_chain_once(source=source, output_root=replay_output)
        replay = Path(receipts["W0"]["receipt_path"]).resolve(strict=True).parent
        final_replay_roots[source.name] = replay
        first_manifests[source.name] = build_source_manifest(replay)

    second_manifests: dict[str, Mapping[str, Any]] = {}
    for source in sources:
        receipts = _run_chain_once(source=source, output_root=replay_output)
        replay = Path(receipts["W0"]["receipt_path"]).resolve(strict=True).parent
        if replay != final_replay_roots[source.name]:
            raise W5EndToEndPipelineError("integrated replay identity changed")
        second_manifests[source.name] = build_source_manifest(replay)

    rows = []
    for source in sources:
        first = first_manifests[source.name]
        second = second_manifests[source.name]
        _require(
            {
                "full_tree_bytes_stable": first.get("content_sha256")
                == second.get("content_sha256"),
                "full_tree_file_count_stable": first.get("file_count")
                == second.get("file_count"),
                "full_tree_total_bytes_stable": first.get("total_bytes")
                == second.get("total_bytes"),
            },
            label=f"integrated_replay_nondeterministic:{source.name}",
        )
        contract = _chain_contract(
            source=source,
            replay=final_replay_roots[source.name],
            output=output,
        )
        contract["determinism"] = {
            "execution_count": 2,
            "first_tree_sha256": first["content_sha256"],
            "second_tree_sha256": second["content_sha256"],
            "full_tree_bytes_stable": True,
            "file_count": second["file_count"],
            "total_bytes": second["total_bytes"],
        }
        rows.append(contract)

    payload: dict[str, Any] = {
        "schema_version": INTEGRATED_EXECUTION_SCHEMA,
        "status": "PASS",
        "qualification_mode": "REAL_W0_W4_ZERO_PROVIDER_REPLAY",
        "case_count": len(rows),
        "cases": rows,
        "wave_sequence": ["W0", "W1", "W2", "W3", "W4"],
        "full_chain_execution_count_per_run": 2,
        "historical_saved_judge_result_count": sum(
            int(case["historical_saved_judges"]["result_count"]) for case in rows
        ),
        "historical_saved_judge_pass_count": sum(
            int(case["historical_saved_judges"]["passing_result_count"])
            for case in rows
        ),
        "historical_actual_claude_judge_result_count": sum(
            int(case["historical_saved_judges"]["actual_claude_judge_result_count"])
            for case in rows
        ),
        "historical_apps_research_usage_event_count": sum(
            int(case["historical_model_routes"]["apps_research"]["usage_event_count"])
            for case in rows
        ),
        "historical_apps_research_successful_attempt_count": sum(
            int(
                case["historical_model_routes"]["apps_research"][
                    "successful_attempt_count"
                ]
            )
            for case in rows
        ),
        "historical_apps_research_claude_usage_event_count": sum(
            int(
                case["historical_model_routes"]["apps_research"][
                    "claude_usage_event_count"
                ]
            )
            for case in rows
        ),
        "historical_apps_rg_generation_lane_count": sum(
            int(case["historical_model_routes"]["apps_rg_generation"]["lane_count"])
            for case in rows
        ),
        "historical_apps_rg_target_claude_lane_count": sum(
            int(
                case["historical_model_routes"]["apps_rg_generation"][
                    "target_claude_lane_count"
                ]
            )
            for case in rows
        ),
        "historical_apps_rg_actual_claude_lane_count": sum(
            int(
                case["historical_model_routes"]["apps_rg_generation"][
                    "actual_claude_lane_count"
                ]
            )
            for case in rows
        ),
        "historical_apps_rg_model_mismatch_lane_count": sum(
            int(
                case["historical_model_routes"]["apps_rg_generation"][
                    "model_mismatch_lane_count"
                ]
            )
            for case in rows
        ),
        "historical_apps_rg_recorded_token_budget_failure_lane_count": sum(
            int(
                case["historical_model_routes"]["apps_rg_generation"][
                    "recorded_token_budget_failure_lane_count"
                ]
            )
            for case in rows
        ),
        "historical_apps_rg_recomputed_output_token_budget_failure_lane_count": sum(
            int(
                case["historical_model_routes"]["apps_rg_generation"][
                    "recomputed_output_token_budget_failure_lane_count"
                ]
            )
            for case in rows
        ),
        "historical_apps_rg_token_accounting_false_failure_lane_count": sum(
            int(
                case["historical_model_routes"]["apps_rg_generation"][
                    "token_accounting_false_failure_lane_count"
                ]
            )
            for case in rows
        ),
        "contract_handoff_entry_count": sum(
            int(case["contract_handoffs"]["entry_count"]) for case in rows
        ),
        "source_runs_mutated": False,
        "provider_calls": 0,
        "judge_calls": 0,
        "embedding_calls": 0,
        "model_calls": 0,
        "network_attempts": 0,
        "subprocess_attempts": 0,
        "new_uwg_operations": 0,
    }
    path = _write_semantic(output / INTEGRATED_EXECUTION_FILENAME, payload)
    return {
        "manifest": _read_json(path, label="integrated_execution_manifest"),
        "manifest_path": path,
        "run_inputs": [
            {"source_run": source, "replay_root": final_replay_roots[source.name]}
            for source in sources
        ],
    }


def execute_production_fault_qualification(
    *,
    source_run: Path | str,
    output_dir: Path | str,
) -> dict[str, Any]:
    """Exercise W2 and W3 error handlers and resume only failed stages."""

    _install_minimal_apps_rg_namespace()
    from apps_rg.runtime.apps_eval_replay import emit_w2_apps_eval_replay
    from apps_rg.runtime.authority_reconciliation import (
        emit_w1_authority_reconciliation,
    )
    from apps_rg.runtime.l6_shadow_replay import emit_w3_l6_shadow_replay
    from apps_rg.runtime.post_runtime_replay import (
        PostRuntimeReplaySafetyError,
        run_guarded_artifact_replay,
        run_w0_zero_provider_preflight,
    )
    from apps_rg.runtime.terminal_closeout_replay import (
        emit_w4_terminal_closeout_replay,
    )

    source = Path(source_run).resolve(strict=True)
    output = Path(output_dir).resolve()
    replay_output = output / "f"
    w0 = run_w0_zero_provider_preflight(
        source_run=source,
        output_root=replay_output,
        require_clean_import_state=True,
    )
    replay = Path(w0["receipt_path"]).resolve(strict=True).parent

    def w1_operation(run: Path, wave_output: Path) -> Mapping[str, Any]:
        return emit_w1_authority_reconciliation(
            source_run=run,
            output_dir=wave_output,
            dag_manifest_path=_dag_manifest_path(),
        )

    run_guarded_artifact_replay(
        source_run=source,
        output_root=replay_output,
        wave="W1",
        operation=w1_operation,
        receipt_filename="w1_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
    )
    w1_completion_path = replay / "w1/w1_completion_receipt.json"
    w1_before = _sha256_file(w1_completion_path)

    def inject_eval(stage: str, attempt: int) -> None:
        if stage == "APPS_EVAL" and attempt == 1:
            raise ProductionBoundaryFault("controlled W2 production-boundary fault")

    def w2_fault_operation(run: Path, wave_output: Path) -> Mapping[str, Any]:
        return emit_w2_apps_eval_replay(
            source_run=run,
            output_dir=wave_output,
            fault_injector=inject_eval,
        )

    try:
        run_guarded_artifact_replay(
            source_run=source,
            output_root=replay_output,
            wave="W2",
            operation=w2_fault_operation,
            receipt_filename="w2_fault_zero_provider_guard_receipt.json",
            require_clean_import_state=True,
            expected_activity={
                "apps_eval_executed": True,
                "l6_executed": False,
                "uwg_operation_attempted": False,
            },
        )
    except PostRuntimeReplaySafetyError:
        pass
    else:  # pragma: no cover - the controlled boundary must fail
        raise W5EndToEndPipelineError("W2 production fault did not propagate")

    def w2_resume_operation(run: Path, wave_output: Path) -> Mapping[str, Any]:
        return emit_w2_apps_eval_replay(source_run=run, output_dir=wave_output)

    run_guarded_artifact_replay(
        source_run=source,
        output_root=replay_output,
        wave="W2",
        operation=w2_resume_operation,
        receipt_filename="w2_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
        expected_activity={
            "apps_eval_executed": True,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
    )
    _require(
        {"w1_not_replayed": _sha256_file(w1_completion_path) == w1_before},
        label="w2_resume_scope_invalid",
    )
    w1_after_eval_resume = _sha256_file(w1_completion_path)
    w2_completion_path = replay / "w2/w2_completion_receipt.json"
    w2_before = _sha256_file(w2_completion_path)

    def inject_l6(stage: str, attempt: int) -> None:
        if stage == "L6_SHADOW_OBSERVABILITY" and attempt == 1:
            raise ProductionBoundaryFault("controlled W3 production-boundary fault")

    def w3_fault_operation(run: Path, wave_output: Path) -> Mapping[str, Any]:
        return emit_w3_l6_shadow_replay(
            source_run=run,
            output_dir=wave_output,
            fault_injector=inject_l6,
        )

    try:
        run_guarded_artifact_replay(
            source_run=source,
            output_root=replay_output,
            wave="W3",
            operation=w3_fault_operation,
            receipt_filename="w3_fault_zero_provider_guard_receipt.json",
            require_clean_import_state=True,
            expected_activity={
                "apps_eval_executed": False,
                "l6_executed": True,
                "uwg_operation_attempted": False,
            },
        )
    except PostRuntimeReplaySafetyError:
        pass
    else:  # pragma: no cover - the controlled boundary must fail
        raise W5EndToEndPipelineError("W3 production fault did not propagate")

    def w3_resume_operation(run: Path, wave_output: Path) -> Mapping[str, Any]:
        return emit_w3_l6_shadow_replay(source_run=run, output_dir=wave_output)

    run_guarded_artifact_replay(
        source_run=source,
        output_root=replay_output,
        wave="W3",
        operation=w3_resume_operation,
        receipt_filename="w3_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
        expected_activity={
            "apps_eval_executed": False,
            "l6_executed": True,
            "uwg_operation_attempted": False,
        },
    )
    _require(
        {"w2_not_replayed": _sha256_file(w2_completion_path) == w2_before},
        label="w3_resume_scope_invalid",
    )
    w2_after_l6_resume = _sha256_file(w2_completion_path)

    def w4_operation(run: Path, wave_output: Path) -> Mapping[str, Any]:
        return emit_w4_terminal_closeout_replay(
            source_run=run,
            output_dir=wave_output,
        )

    run_guarded_artifact_replay(
        source_run=source,
        output_root=replay_output,
        wave="W4",
        operation=w4_operation,
        receipt_filename="w4_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
        expected_activity={
            "apps_eval_executed": False,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
    )

    paths = {
        "eval_error_receipt": replay / "w2/failures/apps_eval_error_receipt.json",
        "eval_error_span": replay / "w2/failures/apps_eval_error_span.json",
        "eval_resume_receipt": replay / "w2/failures/apps_eval_resume_receipt.json",
        "eval_fault_guard": replay / "w2/w2_fault_zero_provider_guard_receipt.json",
        "eval_success_guard": replay / "w2/w2_zero_provider_guard_receipt.json",
        "l6_error_receipt": replay / "w3/failures/l6_shadow_error_receipt.json",
        "l6_error_span": replay / "w3/failures/l6_shadow_error_span.json",
        "l6_resume_receipt": replay / "w3/failures/l6_shadow_resume_receipt.json",
        "l6_fault_guard": replay / "w3/w3_fault_zero_provider_guard_receipt.json",
        "l6_success_guard": replay / "w3/w3_zero_provider_guard_receipt.json",
        "terminal_completion": replay / "w4/w4_completion_receipt.json",
    }
    docs = {role: _read_json(path, label=role) for role, path in paths.items()}
    eval_error = docs["eval_error_receipt"]
    eval_resume = docs["eval_resume_receipt"]
    l6_error = docs["l6_error_receipt"]
    l6_resume = docs["l6_resume_receipt"]
    checks = {
        "all_artifacts_present": all(path.is_file() for path in paths.values()),
        "all_semantic": all(_semantic_valid(doc) for doc in docs.values()),
        "eval_real_boundary": eval_error.get("stage_id") == "APPS_EVAL"
        and eval_error.get("error_type") == "ProductionBoundaryFault"
        and "controlled W2 production-boundary fault"
        in str(eval_error.get("traceback") or ""),
        "eval_resume_only": eval_resume.get("resume_from_stage") == "APPS_EVAL"
        and eval_resume.get("w1_replayed") is False
        and eval_resume.get("generation_replayed") is False
        and eval_resume.get("judge_replayed") is False,
        "l6_real_boundary": l6_error.get("stage_id") == "L6_SHADOW_OBSERVABILITY"
        and l6_error.get("error_type") == "ProductionBoundaryFault"
        and "controlled W3 production-boundary fault"
        in str(l6_error.get("traceback") or ""),
        "l6_resume_only": l6_resume.get("resume_from_stage")
        == "L6_SHADOW_OBSERVABILITY"
        and l6_resume.get("w1_replayed") is False
        and l6_resume.get("w2_replayed") is False
        and l6_resume.get("apps_eval_replayed") is False
        and l6_resume.get("generation_replayed") is False,
        "fault_guards_failed": docs["eval_fault_guard"].get("status") == "FAIL"
        and docs["l6_fault_guard"].get("status") == "FAIL",
        "resume_guards_passed": docs["eval_success_guard"].get("status") == "PASS"
        and docs["l6_success_guard"].get("status") == "PASS",
        "terminal_recovered": docs["terminal_completion"].get("terminal_outcome")
        == "BLOCKED_NON_PRODUCT"
        and docs["terminal_completion"].get("terminal_closed") is True,
    }
    _require(checks, label="production_fault_qualification_invalid")
    payload: dict[str, Any] = {
        "schema_version": FAULT_QUALIFICATION_SCHEMA,
        "status": "PASS",
        "source_run_id": source.name,
        "replay_root": replay.relative_to(output).as_posix(),
        "fault_injection_mode": "REAL_PRODUCTION_STAGE_BOUNDARY",
        "eval_failure_recovered": True,
        "eval_resume_scope": "APPS_EVAL_ONLY_FROM_SAVED_W1",
        "eval_resume_upstream_binding": {
            "artifact_ref": w1_completion_path.relative_to(output).as_posix(),
            "before_sha256": w1_before,
            "after_sha256": w1_after_eval_resume,
            "unchanged": w1_before == w1_after_eval_resume,
        },
        "l6_failure_recovered": True,
        "l6_resume_scope": "L6_ONLY_FROM_SAVED_W2",
        "l6_resume_upstream_binding": {
            "artifact_ref": w2_completion_path.relative_to(output).as_posix(),
            "before_sha256": w2_before,
            "after_sha256": w2_after_l6_resume,
            "unchanged": w2_before == w2_after_l6_resume,
        },
        "terminal_closeout_after_recovery": True,
        "provider_calls": 0,
        "judge_calls": 0,
        "embedding_calls": 0,
        "model_calls": 0,
        "network_attempts": 0,
        "subprocess_attempts": 0,
        "new_uwg_operations": 0,
        "checks": checks,
        "artifacts": [
            _binding(path, root=output, role=role)
            for role, path in sorted(paths.items())
        ],
    }
    path = _write_semantic(output / FAULT_QUALIFICATION_FILENAME, payload)
    return {
        "manifest": _read_json(path, label="fault_qualification_manifest"),
        "manifest_path": path,
        "artifact_paths": paths,
        "replay_root": replay,
    }


def _fixture_identity() -> dict[str, str]:
    digest = "sha256:" + "a" * 64
    return {
        "producer_app_id": "apps_research",
        "consumer_app_id": "apps_rg",
        "parent_run_id": "w5-fixture-parent",
        "child_run_id": "w5-fixture-child",
        "request_id": "w5-fixture-request",
        "trace_root": "w5-fixture-trace",
        "tenant_id": "w5-fixture-tenant",
        "target_company": "W5 Deterministic Control",
        "target_role": "Partnerships Leader",
        "jd_sha256": digest,
        "brief_sha256": digest,
        "policy_hash": digest,
        "blueprint_hash": digest,
        "schema_version": "apps_research_rg_run_identity.v1",
    }


def _fixture_write(path: Path, payload: Mapping[str, Any]) -> Path:
    return _atomic_write_json(path, payload)


def _build_positive_fixture(root: Path) -> tuple[dict[str, str], dict[str, Any]]:
    identity = _fixture_identity()
    digest = "sha256:" + "b" * 64
    lane_statuses = []
    for lane in EXPECTED_LANES:
        lane_statuses.append(
            {
                "lane": lane,
                "executed": True,
                "x3_code": "X3_ALLOW",
                "x2_pass": "PASS",
                "x2_failed_gate_ids": "",
                "runtime_generation_status": "REAL_LLM",
                "product_quality_status": "PASS",
                "judges": [{"pass": True, "provider_status": "MODEL_BACKED_PASS"}],
            }
        )
        lane_root = root / "modular_r4/sections" / lane
        _fixture_write(
            lane_root / "c0_metrics.json",
            {
                "support_status": "PASS",
                "support_target_met": True,
                "evidence_counts": {"total": 1},
            },
        )
        _fixture_write(
            lane_root / "compiled_prompt_artifact.json",
            {
                "section_id": lane,
                "pa_prompt_hash": f"fixture-prompt-{lane}",
                "fec_bridge_ref": "final_evidence_contract.json",
                "final_evidence_contract_ref": "final_evidence_contract.json",
                "c0_fec_bridge_receipt_ref": "c0_fec_compose_receipt.json",
                "evidence_contract_consumed": True,
                "raw_proof_pool_direct_to_pa": False,
            },
        )
        _fixture_write(
            lane_root / "c0_fec_compose_receipt.json",
            {
                "fec_bridge_status": "PASS",
                "precondition_status": "PASS",
                "support_status": "PASS",
                "pa_entry_allowed": True,
                "raw_proof_pool_direct_to_pa": False,
            },
        )
        _fixture_write(
            lane_root / "x2_gate_outputs.json",
            {
                "gates": [{"gate_id": "x2_no_silent_mock_fallback", "pass": True}],
                "failed_gates": [],
                "x2_failed": 0,
            },
        )
        _fixture_write(
            lane_root / "x3_disposition.json",
            {
                "x3_code": "X3_ALLOW",
                "final_materialized_acceptance_ok": True,
                "section_x3_authoritative": False,
                "section_x3_mirror_only": True,
                "spine_x3_claimed": False,
                "core_exit_authority_ref": "x3_disposition_receipt.json",
            },
        )
        _fixture_write(
            lane_root / "exit_disposition_receipt.json",
            {
                "section_x3_authoritative": False,
                "section_x3_mirror_only": True,
                "spine_x3_claimed": False,
                "canonical_exit_claimed": False,
                "x3_disposition": {"x3_code": "X3_ALLOW"},
            },
        )
        _fixture_write(
            lane_root / "l2_handoff_receipt.json",
            {
                "schema_version": "apps_rg_l2_handoff_receipt_v2",
                "section_id": lane,
                "handoff_status": "PASS",
                "checks": {
                    "artifact_bytes_match": True,
                    "canonical_receipt_bundle_required": True,
                    "grounded_output": True,
                    "model_id_matches": True,
                    "packet_signature_verified": True,
                    "provider_lane_matches": True,
                    "replay_key_matches": True,
                    "token_budget_pass": True,
                    "token_usage_observed": True,
                },
                "model_id_used": "saved-output-control-fixture",
                "provider_lane_used": "no-provider-execution-fixture",
                "tokens_emitted": 100,
                "budget_ceiling": 4096,
            },
        )
        _fixture_write(
            lane_root / "l2_spine_receipt.json",
            {
                "schema_version": "l2_spine_receipt_v2",
                "section_id": lane,
                "l2_spine_status": "PASS",
                "precondition_status": "PASS",
                "direct_l4_write_allowed": False,
            },
        )
        core_payload = {
            "x3_disposition": "X3D_ALLOW_FINISH",
            "disposition": "X3D",
        }
        _fixture_write(
            lane_root / "x3_disposition_receipt.json",
            {
                "producer_component": (
                    "apps_rg.runtime.entrypoints."
                    "integrated_single_action_spine_run"
                ),
                "artifact_hash": _canonical_digest(core_payload),
                "payload": core_payload,
            },
        )
        core_authority = {
            "schema_version": "apps_rg.core_runtime_authority.v1",
            "source_artifact_bindings": [
                {
                    "artifact_ref": "x3_disposition_receipt.json",
                    "present": True,
                    "hash_matches": True,
                }
            ],
            "normalized_contract": {
                "valid": True,
                "x3": {"x3_disposition": "X3D_ALLOW_FINISH"},
                "spine_proof": {"success": True},
            },
            "status": "PASS",
            "outcome_authorized": True,
        }
        core_authority["deterministic_digest"] = _canonical_digest(core_authority)
        _fixture_write(
            lane_root / "apps_rg_core_runtime_authority.json",
            core_authority,
        )

    _fixture_write(root / "full_run_section_status.json", {"lanes": lane_statuses})
    _fixture_write(
        root / "FINAL_RESUME_OUTPUT.json",
        {
            "status": "PASS",
            "failed_gate_ids": [],
            "gates": [
                {
                    "gate_id": "final_resume_base_role_headers_preserved",
                    "pass": True,
                },
                {
                    "gate_id": "final_resume_education_copied_from_base",
                    "pass": True,
                },
                {
                    "gate_id": "final_resume_certifications_copied_from_base",
                    "pass": True,
                },
            ],
        },
    )
    assembly = root / "modular_r4/final_resume_assembly"
    _fixture_write(
        assembly / "final_resume.json",
        {
            "sections": [{"section_id": lane} for lane in EXPECTED_LANES]
            + [
                {"section_id": "early_career"},
                {"section_id": "education"},
                {"section_id": "certifications"},
            ],
            "locked_copy_invariants": {"dates": {"section_hash": "fixture"}},
        },
    )
    _fixture_write(
        assembly / "final_resume_x2_gate_outputs.json",
        {
            "all_pass": True,
            "failed_gate_ids": [],
            "gates": [{"gate_id": "x2_all_required_sections_present", "pass": True}],
        },
    )
    _fixture_write(
        assembly / "x1d_full_resume_judge_outputs.json",
        {
            "judges": [{"pass": True}, {"pass": True}],
            "aggregation": {
                "quorum_required": 2,
                "full_resume_coherence_pass": True,
                "blockers": [],
            },
        },
    )
    _fixture_write(
        assembly / "final_resume_receipt.json",
        {
            "gates_all_pass": True,
            "structural_x2_all_pass": True,
            "cross_section_x2_all_pass": True,
            "cross_section_x2_product_pass": True,
            "whole_resume_graph_evidence_release_pass": True,
            "review_lane_policy_summary": {"product_allow_claimed": True},
            "assembly_proof_semantics": {"product_release_eligible": True},
        },
    )
    _fixture_write(
        root / "e2e_preflight_product_entry_receipt.json",
        {"status": "PASS", "identity": identity},
    )
    _fixture_write(root / "u0_receipt.json", {"status": "PASS", "identity": identity})
    research = root / "apps_research/runs/w5-positive-control"
    _fixture_write(
        research / "exit_disposition_receipt.json",
        {"x3_code": "X3D_ALLOW_FINISH"},
    )
    _fixture_write(
        research / "apps_research_apps_rg_handoff_v2.json",
        {
            "schema_version": "apps_research.apps_rg_handoff.v2",
            "identity": identity,
        },
    )
    ledger = root / "e2e_ledger_receipts"
    _fixture_write(
        ledger / "0006_apps_rg_l1.json",
        {
            "status": "PASS",
            "work_shape": "full_resume_generation",
            "identity": identity,
        },
    )
    _fixture_write(
        ledger / "0007_apps_rg_l0.json",
        {
            "status": "PASS",
            "execution_form": "MANAGED_WORKFLOW",
            "identity": identity,
        },
    )
    outer_identity = {
        "run_id": identity["parent_run_id"],
        "request_id": identity["request_id"],
        "trace_root": identity["trace_root"],
    }
    _fixture_write(
        root / "runtime_execution_witness.json",
        {
            "payload": {
                **outer_identity,
                "c0": {"status": "BYPASSED_PRELOADED_CONTEXT"},
                "l2": {"executed": True, "status": "PASS", "fault": ""},
                "x1": {"status": "EXECUTED"},
                "x2": {
                    "status": "EXECUTED",
                    "x3_disposition": "X3A_DENY_REROUTE",
                },
                "x3": {
                    "status": "EMITTED",
                    "x3_disposition": "X3A_DENY_REROUTE",
                },
            }
        },
    )
    _fixture_write(
        root / "terminal_ret_packet.json",
        {"payload": {**outer_identity, "l2_fault": ""}},
    )
    _fixture_write(
        root / "prompt_assembly_bypass_receipt.json",
        {"payload": outer_identity},
    )
    _fixture_write(root / "outputs/generated_resume.json", {"sections": []})
    docx = root / "outputs/resume.docx"
    docx.parent.mkdir(parents=True, exist_ok=True)
    docx.write_bytes(b"w5-deterministic-control-docx")
    manifest = {
        "apps_rg_generation_status": "REAL_RESUME",
        "resume_shape": "REAL_RESUME",
        "full_resume_generated": True,
        "docx_output_required": True,
        "docx_verified": True,
        "generated_resume_json_relpath": "outputs/generated_resume.json",
        "resume_docx_relpath": "outputs/resume.docx",
        "required_artifacts": {
            "generated_resume_json": "verified",
            "resume_docx": "verified",
            "docx_verified": True,
        },
    }
    _fixture_write(root / "apps_rg_output_manifest.json", manifest)
    _fixture_write(
        root / "positive_control_fixture_metadata.json",
        {
            "schema_version": "apps_rg.w5_positive_fixture_metadata.v1",
            "qualification_only": True,
            "saved_output_fixture": True,
            "provider_execution": False,
            "judge_execution": False,
            "embedding_execution": False,
            "model_pin_qualified": False,
            "production_authority_granted": False,
            "publication_allowed": False,
            "fixture_digest": digest,
        },
    )
    return identity, manifest


def emit_production_positive_control(
    *,
    output_dir: Path | str,
) -> dict[str, Any]:
    """Build a saved-output fixture and run production authority validators."""

    _install_minimal_apps_rg_namespace()
    from apps_rg.runtime.package.apps_rg_full_resume_x3_eligibility import (
        evaluate_apps_rg_product_authority_eligibility,
    )
    from apps_rg.runtime.product_stage_authority import (
        emit_runtime_stage_authority_receipts,
    )
    from apps_rg.runtime.terminal_state import (
        TerminalStateMachine,
        persist_product_authorization_receipt,
    )
    from apps_rg.runtime.whole_run_exit import (
        WHOLE_RUN_EXIT_ARTIFACT,
        emit_whole_run_exit_review_packet,
        verify_whole_run_exit_review_packet,
    )

    output = Path(output_dir).resolve()
    fixture = output / "governed_positive_fixture"
    manifest_path = output / POSITIVE_CONTROL_FILENAME
    completion_path = output / "positive_control_completion.json"
    if manifest_path.is_file() and completion_path.is_file():
        valid, errors = verify_production_positive_control(manifest_path)
        if valid:
            completion = _read_json(completion_path, label="positive_completion")
            return {
                "completion": completion,
                "activity": {
                    "apps_eval_executed": False,
                    "l6_executed": False,
                    "uwg_operation_attempted": False,
                },
                "manifest_path": manifest_path.as_posix(),
            }
        raise W5EndToEndPipelineError(
            "existing positive control invalid:" + ",".join(errors)
        )

    identity, output_manifest = _build_positive_fixture(fixture)
    packet = emit_whole_run_exit_review_packet(
        artifact_dir=fixture,
        identity=identity,
    )
    packet_valid, packet_errors = verify_whole_run_exit_review_packet(
        fixture,
        expected_identity=identity,
    )
    stage_receipts = emit_runtime_stage_authority_receipts(
        artifact_dir=fixture,
        identity=identity,
    )
    eligible, eligibility_reasons = evaluate_apps_rg_product_authority_eligibility(
        manifest=output_manifest,
        run_root=fixture,
    )
    _require(
        {
            "whole_run_exit_pass": packet.get("status") == "PASS"
            and packet.get("x3_disposition") == "X3D_ALLOW_FINISH",
            "whole_run_exit_verified": packet_valid and not packet_errors,
            "stage_authority_pass": len(stage_receipts) == 6
            and all(
                _read_json(path, label=f"stage_authority:{stage}").get("status")
                == "PASS"
                for stage, path in stage_receipts.items()
            ),
            "product_eligibility_pass": eligible and not eligibility_reasons,
        },
        label="positive_production_validator_failure",
    )

    decision_path = _write_semantic(
        fixture / "qualification_fixture_uwg_decision.json",
        {
            "schema_version": "apps_rg.w5_fixture_uwg_decision.v1",
            "status": "COMMITTED",
            "qualification_only": True,
            "actual_uwg_operation_attempted": False,
        },
    )
    output_path = fixture / "outputs/generated_resume.json"
    state = TerminalStateMachine()
    product_state = state.close_product_authorization(
        authorized=True,
        decision_receipt_ref=decision_path.relative_to(fixture).as_posix(),
        decision_receipt_sha256=_sha256_file(decision_path),
        output_artifact_sha256=_sha256_file(output_path),
        closed_at_utc="1970-01-01T00:00:00+00:00",
    )
    authorization_path = persist_product_authorization_receipt(
        artifact_dir=fixture,
        identity=identity,
        state=product_state,
        decision_receipt_ref=decision_path.relative_to(fixture),
        output_artifact_ref=output_path.relative_to(fixture),
    )
    pipeline_state = state.record_pipeline_completion(
        complete=True,
        decisive_stage_id="MANDATORY_OUTPUTS",
    )
    state.seal()
    terminal_path = _write_semantic(
        fixture / "qualification_fixture_terminal_state.json",
        {
            "schema_version": "apps_rg.w5_fixture_terminal_state.v1",
            "status": "PASS",
            "qualification_only": True,
            "fixture_product_authorized": True,
            "fixture_pipeline_complete": True,
            "state_snapshot": state.snapshot(),
            "product_authorization": {
                "authorized": product_state.authorized,
                "status": product_state.status,
                "boundary": product_state.boundary,
                "immutable": product_state.immutable,
            },
            "pipeline_completion": {
                "complete": pipeline_state.complete,
                "status": pipeline_state.status,
                "decisive_stage_id": pipeline_state.decisive_stage_id,
            },
            "production_authority_granted": False,
            "publication_allowed": False,
        },
    )
    artifact_paths = {
        "fixture_metadata": fixture / "positive_control_fixture_metadata.json",
        "product_entry": fixture / "e2e_preflight_product_entry_receipt.json",
        "whole_run_exit": fixture / WHOLE_RUN_EXIT_ARTIFACT,
        "final_assembly": fixture
        / "modular_r4/final_resume_assembly/final_resume_receipt.json",
        "fixture_uwg_decision": decision_path,
        "product_authorization": authorization_path,
        "terminal_state": terminal_path,
        **{
            f"stage_authority_{stage.lower()}": path
            for stage, path in stage_receipts.items()
        },
    }
    body: dict[str, Any] = {
        "schema_version": POSITIVE_CONTROL_SCHEMA,
        "status": "PASS",
        "case_id": "governed_saved_output_production_validator_control",
        "fixture_class": "DETERMINISTIC_GOVERNED_SAVED_OUTPUT",
        "qualification_only": True,
        "production_authority_granted": False,
        "publication_allowed": False,
        "provider_execution": False,
        "judge_execution": False,
        "embedding_execution": False,
        "model_pin_qualified": False,
        "whole_run_exit_verified": True,
        "stage_authority_receipts_passed": len(stage_receipts),
        "product_eligibility_passed": True,
        "terminal_state_machine_passed": True,
        "fixture_product_authorized": True,
        "fixture_pipeline_complete": True,
        "production_validators": [
            "apps_rg.runtime.whole_run_exit.emit_whole_run_exit_review_packet",
            "apps_rg.runtime.whole_run_exit.verify_whole_run_exit_review_packet",
            "apps_rg.runtime.product_stage_authority.emit_runtime_stage_authority_receipts",
            "apps_rg.runtime.package.apps_rg_full_resume_x3_eligibility.evaluate_apps_rg_product_authority_eligibility",
            "apps_rg.runtime.terminal_state.TerminalStateMachine",
            "apps_rg.runtime.terminal_state.persist_product_authorization_receipt",
        ],
        "artifacts": [
            _binding(path, root=output, role=role)
            for role, path in sorted(artifact_paths.items())
        ],
    }
    positive_path = _write_semantic(manifest_path, body)
    positive = _read_json(positive_path, label="positive_control_manifest")
    valid, errors = verify_production_positive_control(positive_path)
    _require({"positive_control_verified": valid and not errors}, label="positive")
    completion = {
        "schema_version": POSITIVE_COMPLETION_SCHEMA,
        "wave": "W5_POSITIVE",
        "status": "PASS",
        "scope_complete": True,
        "qualification_only": True,
        "production_authority_granted": False,
        "publication_allowed": False,
        "positive_control_manifest": _binding(positive_path, root=output),
        "positive_control_semantic_digest": positive["semantic_digest"],
    }
    completion_path = _write_semantic(completion_path, completion)
    completion = _read_json(completion_path, label="positive_completion")
    return {
        "completion": completion,
        "activity": {
            "apps_eval_executed": False,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
        "manifest_path": positive_path.as_posix(),
    }


def verify_production_positive_control(
    path: Path | str,
) -> tuple[bool, list[str]]:
    manifest_path = Path(path).resolve(strict=True)
    output = manifest_path.parent
    manifest = _read_json(manifest_path, label="positive_control_manifest")
    rows = manifest.get("artifacts")
    rows = rows if isinstance(rows, list) else []
    errors: list[str] = []
    roles: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"artifact_not_object:{index}")
            continue
        role = str(row.get("artifact_role") or "")
        roles.add(role)
        ref = str(row.get("artifact_ref") or "")
        candidate = (output / ref).resolve()
        if not _contained(candidate, output) or not candidate.is_file():
            errors.append(f"artifact_missing:{role}")
            continue
        if row.get("byte_length") != candidate.stat().st_size:
            errors.append(f"artifact_length_mismatch:{role}")
        if row.get("sha256") != _sha256_file(candidate):
            errors.append(f"artifact_digest_mismatch:{role}")
    required_roles = {
        "fixture_metadata",
        "product_entry",
        "whole_run_exit",
        "final_assembly",
        "fixture_uwg_decision",
        "product_authorization",
        "terminal_state",
        *(
            f"stage_authority_{stage}"
            for stage in (
                "apps_rg_c0",
                "apps_rg_pa",
                "apps_rg_l2",
                "x1_review",
                "x2_aggregation",
                "x3_disposition",
            )
        ),
    }
    checks = {
        "schema": manifest.get("schema_version") == POSITIVE_CONTROL_SCHEMA,
        "status": manifest.get("status") == "PASS",
        "semantic": _semantic_valid(manifest),
        "qualification_only": manifest.get("qualification_only") is True,
        "no_real_authority": manifest.get("production_authority_granted") is False
        and manifest.get("publication_allowed") is False,
        "no_execution": manifest.get("provider_execution") is False
        and manifest.get("judge_execution") is False
        and manifest.get("embedding_execution") is False,
        "model_pin_not_claimed": manifest.get("model_pin_qualified") is False,
        "production_validators_passed": manifest.get("whole_run_exit_verified") is True
        and manifest.get("stage_authority_receipts_passed") == 6
        and manifest.get("product_eligibility_passed") is True
        and manifest.get("terminal_state_machine_passed") is True,
        "fixture_state_passed": manifest.get("fixture_product_authorized") is True
        and manifest.get("fixture_pipeline_complete") is True,
        "roles": roles == required_roles,
        "artifacts": not errors,
    }
    errors.extend(name for name, passed in checks.items() if not passed)
    return not errors, sorted(set(errors))


def execute_positive_control(
    *,
    source_run: Path | str,
    output_dir: Path | str,
) -> dict[str, Any]:
    """Run the positive control inside the same zero-provider guard."""

    _install_minimal_apps_rg_namespace()
    from apps_rg.runtime.post_runtime_replay import run_guarded_artifact_replay

    source = Path(source_run).resolve(strict=True)
    output = Path(output_dir).resolve()
    positive_root = output / "g"
    control_output = output / "p"

    def operation(_source: Path, _operation_dir: Path) -> Mapping[str, Any]:
        return emit_production_positive_control(output_dir=control_output)

    guard = run_guarded_artifact_replay(
        source_run=source,
        output_root=positive_root,
        wave="W5_POSITIVE",
        operation=operation,
        receipt_filename="w5_positive_zero_provider_guard_receipt.json",
        require_clean_import_state=True,
        expected_activity={
            "apps_eval_executed": False,
            "l6_executed": False,
            "uwg_operation_attempted": False,
        },
    )
    operation = guard["operation_result"]
    manifest_path = Path(str(operation["manifest_path"])).resolve(strict=True)
    valid, errors = verify_production_positive_control(manifest_path)
    _require({"positive_valid": valid and not errors}, label="positive_control")
    return {
        "manifest_path": manifest_path,
        "guard_path": Path(guard["receipt_path"]).resolve(strict=True),
        "operation_dir": Path(guard["operation_dir"]).resolve(strict=True),
    }


__all__ = [
    "FAULT_QUALIFICATION_FILENAME",
    "FAULT_QUALIFICATION_SCHEMA",
    "INTEGRATED_EXECUTION_FILENAME",
    "INTEGRATED_EXECUTION_SCHEMA",
    "POSITIVE_CONTROL_FILENAME",
    "POSITIVE_CONTROL_SCHEMA",
    "ProductionBoundaryFault",
    "W5EndToEndPipelineError",
    "emit_production_positive_control",
    "execute_integrated_replays",
    "execute_positive_control",
    "execute_production_fault_qualification",
    "verify_production_positive_control",
]
