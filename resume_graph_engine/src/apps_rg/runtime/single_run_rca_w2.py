"""Render the canonical JSON and Markdown RCA for one preserved Apps RG run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


MANIFEST_FILENAME = "single_run_w2_canonical_rca.json"
SUMMARY_FILENAME = "single_run_w2_canonical_rca.md"
SCHEMA_VERSION = "apps_rg.single_run_rca_w2.v1"


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object: {path}")
    return parsed, payload


def _binding(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "artifact_ref": path.name,
        "byte_length": len(payload),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "semantic_digest": str(json.loads(payload.decode("utf-8")).get("semantic_digest", "")),
    }


def _require_packet(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if packet.get("status") != "PASS" or packet.get("wave") != "W1" or packet.get("next_wave_authorized") is not True:
        raise ValueError("W1 packet does not authorize W2")
    if packet.get("extracted_counts") != {"generation_lanes": 11, "judges": 21, "contract_handoffs": 21}:
        raise ValueError("W1 packet does not contain the expected single-run scope")
    historical = packet.get("historical_run")
    if not isinstance(historical, dict):
        raise ValueError("W1 packet has no historical run")
    routes = historical.get("historical_model_routes")
    if not isinstance(routes, dict):
        raise ValueError("W1 packet has no historical model-route inventory")
    generation = routes.get("apps_rg_generation")
    if not isinstance(generation, dict):
        raise ValueError("W1 packet has no Apps RG generation inventory")
    required = {
        "lane_count": 11,
        "target_claude_lane_count": 11,
        "actual_claude_lane_count": 0,
        "model_mismatch_lane_count": 11,
        "recorded_token_budget_failure_lane_count": 11,
        "recomputed_output_token_budget_failure_lane_count": 0,
        "token_accounting_false_failure_lane_count": 11,
    }
    if any(generation.get(key) != value for key, value in required.items()):
        raise ValueError("W1 packet model-route RCA values are incomplete")
    return historical, generation


def _summary(manifest: dict[str, Any]) -> str:
    timeline = manifest["timeline"]
    rca = manifest["root_causes"]
    lines = [
        "# Single-run Apps RG RCA",
        "",
        f"Run: `{manifest['source_run_id']}`",
        "",
        "## Outcome",
        "",
        "The historical runtime completed generation, judging, and X2 aggregation, but the run is correctly sealed as `BLOCKED_NON_PRODUCT`. It is not a product-authorized or publishable run.",
        "",
        "## Root causes",
        "",
        f"1. Model identity: all {rca['model_identity']['affected_lanes']} L2 lanes signed `claude-sonnet-5` but actually routed `gpt-5.6-luna`; each L2 handoff therefore failed model identity.",
        f"2. Token accounting: all {rca['token_accounting']['affected_lanes']} recorded token-budget failures compared total input-plus-output tokens to an output-only ceiling. Recomputed output-token failures: {rca['token_accounting']['recomputed_output_token_failures']}.",
        "",
        "## Historical runtime",
        "",
        f"- Apps Research: {timeline['historical_runtime']['apps_research_usage_events']} usage events, {timeline['historical_runtime']['apps_research_successful_attempts']} successful logical attempts, and no Claude usage.",
        f"- L0: {timeline['historical_runtime']['generation_lanes']} saved lanes with observed parallelism of {timeline['historical_runtime']['max_parallel_workers']} workers.",
        f"- Judges: {timeline['historical_runtime']['judges_passed']}/{timeline['historical_runtime']['judges_total']} passed; no Claude judges.",
        f"- Aggregation: X2 `{timeline['historical_runtime']['x2_aggregation_status']}`.",
        "",
        "## Deterministic post-runtime reconstruction",
        "",
        f"- Apps Eval executed and returned `{timeline['post_runtime']['apps_eval_verdict']}`.",
        f"- L6 executed and closed `{timeline['post_runtime']['l6_binding_closure_status']}`; calibration is `{timeline['post_runtime']['l6_calibration_status']}` with no human labels.",
        "",
        "## Bound evidence",
        "",
        f"- Generation lanes: {manifest['evidence_counts']['generation_lanes']}",
        f"- Historical judges: {manifest['evidence_counts']['judges']}",
        f"- Contract handoffs: {manifest['evidence_counts']['contract_handoffs']}",
        f"- Verified W0-W4 replay artifacts: {manifest['evidence_counts']['verified_w5_artifacts']}",
        "",
        f"Canonical RCA semantic digest: `{manifest['semantic_digest']}`",
        "",
        "This rendering used only preserved artifacts. It did not execute Apps Research, generation, a provider, a model, a judge, embeddings, or network operations.",
        "",
    ]
    return "\n".join(lines)


def emit_single_run_w2_canonical_rca(*, w1_packet_path: Path, output_dir: Path) -> dict[str, Any]:
    """Render canonical single-run RCA artifacts from an already verified W1 packet."""

    packet_path = w1_packet_path.resolve(strict=True)
    packet, packet_bytes = _read_json(packet_path)
    historical, generation = _require_packet(packet)
    apps_research = historical["historical_model_routes"]["apps_research"]
    judges = historical["historical_saved_judges"]
    l0 = historical["l0_parallel"]
    apps_eval = historical["apps_eval"]
    l6 = historical["l6"]
    terminal = historical["terminal"]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "wave": "W2",
        "status": "PASS",
        "scope": "SINGLE_RUN_CANONICAL_RCA",
        "source_run_id": packet["source_run_id"],
        "source_manifest_sha256": packet["source_manifest_sha256"],
        "w1_packet": _binding(packet_path, packet_bytes),
        "terminal_state": {
            "pipeline_reconstructed": True,
            "terminal_outcome": terminal["terminal_outcome"],
            "production_authority_granted": False,
            "publication_allowed": False,
        },
        "root_causes": {
            "model_identity": {
                "affected_lanes": generation["model_mismatch_lane_count"],
                "signed_model": "claude-sonnet-5",
                "actual_model": "gpt-5.6-luna",
                "handoff_outcome": "ALL_11_L2_HANDOFFS_AND_SPINES_FAILED",
            },
            "token_accounting": {
                "affected_lanes": generation["token_accounting_false_failure_lane_count"],
                "recorded_token_budget_failures": generation["recorded_token_budget_failure_lane_count"],
                "recomputed_output_token_failures": generation["recomputed_output_token_budget_failure_lane_count"],
                "failure_mode": "TOTAL_TOKENS_COMPARED_TO_OUTPUT_ONLY_CEILING",
            },
        },
        "timeline": {
            "historical_runtime": {
                "apps_research_usage_events": apps_research["usage_event_count"],
                "apps_research_successful_attempts": apps_research["successful_attempt_count"],
                "apps_research_claude_usage_events": apps_research["claude_usage_event_count"],
                "generation_lanes": generation["lane_count"],
                "max_parallel_workers": l0["max_active_workers_observed"],
                "parallel_overlap_proven": l0["parallel_overlap_proven"],
                "judges_total": judges["result_count"],
                "judges_passed": judges["passing_result_count"],
                "actual_claude_judges": judges["actual_claude_judge_result_count"],
                "x2_aggregation_status": terminal["x2_aggregation_status"],
            },
            "post_runtime": {
                "apps_eval_executed": apps_eval["execution_complete"],
                "apps_eval_verdict": apps_eval["verdict"],
                "l6_executed": l6["execution_complete"],
                "l6_binding_closure_status": l6["binding_closure_status"],
                "l6_calibration_status": l6["calibration_status"],
                "human_labels_present": l6["human_labels_present"],
            },
        },
        "evidence_counts": {
            **packet["extracted_counts"],
            "verified_w5_artifacts": len(packet["verified_w5_artifacts"]),
        },
        "generation_lane_inventory": generation["lanes"],
        "judge_inventory": judges["results"],
        "contract_handoff_inventory": historical["contract_handoffs"]["entries"],
        "verified_w5_artifacts": packet["verified_w5_artifacts"],
        "next_wave_authorized": True,
    }
    manifest["semantic_digest"] = _digest(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / MANIFEST_FILENAME
    summary_path = output_dir / SUMMARY_FILENAME
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(_summary(manifest), encoding="utf-8", newline="\n")
    return {**manifest, "manifest_path": manifest_path.as_posix(), "summary_path": summary_path.as_posix()}


__all__ = ["MANIFEST_FILENAME", "SCHEMA_VERSION", "SUMMARY_FILENAME", "emit_single_run_w2_canonical_rca"]
