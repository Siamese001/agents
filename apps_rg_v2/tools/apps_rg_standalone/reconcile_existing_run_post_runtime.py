"""Replay existing apps_rg post-runtime evidence without provider execution."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_SRC_ROOT = REPO_ROOT / "src"
REPLAY_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/post_runtime_replay.py"
AUTHORITY_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/authority_reconciliation.py"
APPS_EVAL_REPLAY_MODULE_PATH = (
    REPO_ROOT / "src/apps_rg/runtime/apps_eval_replay.py"
)
L6_SHADOW_REPLAY_MODULE_PATH = (
    REPO_ROOT / "src/apps_rg/runtime/l6_shadow_replay.py"
)
TERMINAL_CLOSEOUT_REPLAY_MODULE_PATH = (
    REPO_ROOT / "src/apps_rg/runtime/terminal_closeout_replay.py"
)
DAG_MANIFEST_PATH = (
    REPO_ROOT
    / "src/apps_rg/config/domain_contract/workflow_manifest.resume_sections.v1.yaml"
)


def _load_replay_module() -> object:
    """Load the stdlib-only guard without executing ``apps_rg.__init__``."""

    module_name = "_apps_rg_zero_provider_replay"
    spec = importlib.util.spec_from_file_location(module_name, REPLAY_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load replay guard: {REPLAY_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_authority_module() -> object:
    """Load stdlib-only W1 reconciliation without executing apps_rg.__init__."""

    module_name = "_apps_rg_authority_reconciliation"
    spec = importlib.util.spec_from_file_location(module_name, AUTHORITY_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"unable to load authority reconciliation: {AUTHORITY_MODULE_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_apps_eval_replay_module() -> object:
    """Load stdlib-only W2 orchestration before installing the guard."""

    module_name = "_apps_rg_apps_eval_replay"
    spec = importlib.util.spec_from_file_location(
        module_name,
        APPS_EVAL_REPLAY_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"unable to load Apps Eval replay: {APPS_EVAL_REPLAY_MODULE_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_l6_shadow_replay_module() -> object:
    """Load stdlib-only W3 orchestration before installing the guard."""

    module_name = "_apps_rg_l6_shadow_replay"
    spec = importlib.util.spec_from_file_location(
        module_name,
        L6_SHADOW_REPLAY_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"unable to load L6 shadow replay: {L6_SHADOW_REPLAY_MODULE_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_terminal_closeout_replay_module() -> object:
    """Load stdlib-only W4 closeout before installing the guard."""

    module_name = "_apps_rg_terminal_closeout_replay"
    spec = importlib.util.spec_from_file_location(
        module_name,
        TERMINAL_CLOSEOUT_REPLAY_MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            "unable to load terminal closeout replay: "
            f"{TERMINAL_CLOSEOUT_REPLAY_MODULE_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=(
            "w0-preflight",
            "w1-authority",
            "w2-apps-eval",
            "w3-l6-shadow",
            "w4-terminal-closeout",
        ),
        default="w0-preflight",
        help=(
            "W0 establishes the boundary; W1 reconciles saved authority and "
            "proves replay-only L0 parallel orchestration; W2 emits a sealed "
            "deterministic Apps Eval verdict without L6 execution; W3 runs "
            "observer-only L6 and binds persisted lane observations; W4 "
            "seals the blocked run as TERMINAL_NON_PRODUCT."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local_src = str(LOCAL_SRC_ROOT)
        if local_src in sys.path:
            sys.path.remove(local_src)
        sys.path.insert(0, local_src)
        replay = _load_replay_module()
        if args.phase == "w0-preflight":
            receipt = replay.run_w0_zero_provider_preflight(
                source_run=args.source_run,
                output_root=args.output_root,
                require_clean_import_state=True,
            )
        elif args.phase == "w1-authority":
            authority = _load_authority_module()

            def _operation(source: Path, output_dir: Path) -> object:
                return authority.emit_w1_authority_reconciliation(
                    source_run=source,
                    output_dir=output_dir,
                    dag_manifest_path=DAG_MANIFEST_PATH,
                )

            receipt = replay.run_guarded_artifact_replay(
                source_run=args.source_run,
                output_root=args.output_root,
                wave="W1",
                operation=_operation,
                receipt_filename="w1_zero_provider_guard_receipt.json",
                require_clean_import_state=True,
            )
        elif args.phase == "w2-apps-eval":
            apps_eval_replay = _load_apps_eval_replay_module()

            def _operation(source: Path, output_dir: Path) -> object:
                return apps_eval_replay.emit_w2_apps_eval_replay(
                    source_run=source,
                    output_dir=output_dir,
                )

            receipt = replay.run_guarded_artifact_replay(
                source_run=args.source_run,
                output_root=args.output_root,
                wave="W2",
                operation=_operation,
                receipt_filename="w2_zero_provider_guard_receipt.json",
                require_clean_import_state=True,
                expected_activity={
                    "apps_eval_executed": True,
                    "l6_executed": False,
                    "uwg_operation_attempted": False,
                },
            )
        elif args.phase == "w3-l6-shadow":
            l6_shadow_replay = _load_l6_shadow_replay_module()

            def _operation(source: Path, output_dir: Path) -> object:
                return l6_shadow_replay.emit_w3_l6_shadow_replay(
                    source_run=source,
                    output_dir=output_dir,
                )

            receipt = replay.run_guarded_artifact_replay(
                source_run=args.source_run,
                output_root=args.output_root,
                wave="W3",
                operation=_operation,
                receipt_filename="w3_zero_provider_guard_receipt.json",
                require_clean_import_state=True,
                expected_activity={
                    "apps_eval_executed": False,
                    "l6_executed": True,
                    "uwg_operation_attempted": False,
                },
            )
        else:
            terminal_closeout = _load_terminal_closeout_replay_module()

            def _operation(source: Path, output_dir: Path) -> object:
                return terminal_closeout.emit_w4_terminal_closeout_replay(
                    source_run=source,
                    output_dir=output_dir,
                )

            receipt = replay.run_guarded_artifact_replay(
                source_run=args.source_run,
                output_root=args.output_root,
                wave="W4",
                operation=_operation,
                receipt_filename="w4_zero_provider_guard_receipt.json",
                require_clean_import_state=True,
                expected_activity={
                    "apps_eval_executed": False,
                    "l6_executed": False,
                    "uwg_operation_attempted": False,
                },
            )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "apps_rg.post_runtime_replay_cli_failure.v1",
                    "status": "FAIL",
                    "phase": args.phase,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    summary = {
        "status": receipt["status"],
        "wave": receipt["wave"],
        "replay_id": receipt["replay_id"],
        "receipt_path": receipt["receipt_path"],
        "semantic_digest": receipt["semantic_digest"],
        "source_manifest_sha256": receipt["source_manifest_sha256"],
        "source_unchanged": receipt["source_unchanged"],
        "provider_calls": receipt["provider_calls"],
        "judge_calls": receipt["judge_calls"],
        "embedding_calls": receipt["embedding_calls"],
        "model_calls": receipt["model_calls"],
        "network_attempts": receipt["network_attempts"],
        "subprocess_attempts": receipt["subprocess_attempts"],
        "model_span_delta": receipt["model_span_delta"],
        "apps_eval_executed": receipt["apps_eval_executed"],
        "l6_executed": receipt["l6_executed"],
        "next_wave_authorized": receipt["next_wave_authorized"],
    }
    if args.phase == "w1-authority":
        operation = receipt["operation_result"]
        reconciliation = operation["reconciliation"]
        correction = operation["correction"]
        parallel = operation["parallel_replay"]
        summary.update(
            {
                "entry_authority_status": reconciliation["entry_authority"]["status"],
                "authorized_lane_count": reconciliation["authorized_lane_count"],
                "blocked_lane_count": reconciliation["blocked_lane_count"],
                "corrected_product_authorized": correction[
                    "corrected_product_authorized"
                ],
                "correction_disposition": correction["correction_disposition"],
                "parallel_overlap_proven": parallel["parallel_overlap_proven"],
                "max_active_workers_observed": parallel["max_active_workers_observed"],
            }
        )
    elif args.phase == "w2-apps-eval":
        operation = receipt["operation_result"]
        completion = operation["completion"]
        summary.update(
            {
                "eval_execution_complete": completion[
                    "eval_execution_complete"
                ],
                "eval_verdict": completion["eval_verdict"],
                "release_blocked": completion["release_blocked"],
                "preflight_verification_status": completion[
                    "preflight_verification_status"
                ],
                "record_id": completion["record_id"],
                "deterministic_replay_count": completion[
                    "determinism_replay"
                ]["execution_count"],
                "deterministic_record_id_stable": completion[
                    "determinism_replay"
                ]["record_id_stable"],
                "deterministic_eval_record_bytes_stable": completion[
                    "determinism_replay"
                ]["eval_record_bytes_stable"],
                "eval_record_ref": completion["eval_record"]["artifact_ref"],
                "eval_package_seal_ref": completion["eval_package_seal"][
                    "artifact_ref"
                ],
                "saved_judge_artifact_row_count": completion[
                    "saved_judge_artifact_row_count"
                ],
                "l6_handoff_emitted": completion["l6_handoff_emitted"],
                "l6_shadow_bridge_executed": completion[
                    "l6_shadow_bridge_executed"
                ],
                "w3_authorized": completion["w3_authorized"],
            }
        )
    elif args.phase == "w3-l6-shadow":
        operation = receipt["operation_result"]
        completion = operation["completion"]
        section_summary = completion["section_summary"]
        summary.update(
            {
                "record_id": completion["record_id"],
                "l6_execution_complete": completion[
                    "l6_execution_complete"
                ],
                "l6_shadow_observability_verdict": completion[
                    "l6_shadow_observability_verdict"
                ],
                "binding_closure_status": completion[
                    "binding_closure_status"
                ],
                "release_blocked": completion["release_blocked"],
                "projection_consistency_only": completion[
                    "projection_consistency_only"
                ],
                "apps_eval_rows_bound": completion["apps_eval_rows_bound"],
                "evidence_class": completion["evidence_class"],
                "sections_total": section_summary["sections_total"],
                "sections_bound": section_summary["sections_bound"],
                "sections_v40": section_summary["sections_v40"],
                "sections_legacy": section_summary["sections_legacy"],
                "deterministic_replay_count": completion[
                    "determinism_replay"
                ]["execution_count"],
                "deterministic_artifact_bytes_stable": completion[
                    "determinism_replay"
                ]["artifact_bytes_stable"],
                "w3_package_seal_ref": completion["w3_package_seal"][
                    "artifact_ref"
                ],
                "w4_authorized": completion["w4_authorized"],
            }
        )
    elif args.phase == "w4-terminal-closeout":
        operation = receipt["operation_result"]
        completion = operation["completion"]
        stage_summary = completion["stage_summary"]
        telemetry_summary = completion["telemetry_summary"]
        summary.update(
            {
                "record_id": completion["record_id"],
                "product_authorized": completion["product_authorized"],
                "post_runtime_execution_complete": completion[
                    "post_runtime_execution_complete"
                ],
                "eval_verdict": completion["eval_verdict"],
                "observability_complete": completion[
                    "observability_complete"
                ],
                "terminal_closed": completion["terminal_closed"],
                "terminal_outcome": completion["terminal_outcome"],
                "pipeline_complete": completion["pipeline_complete"],
                "authoritative_x3_code": completion[
                    "authoritative_x3_code"
                ],
                "historical_uwg_commit_observed": completion[
                    "historical_uwg_commit_observed"
                ],
                "new_uwg_operation_attempted": completion[
                    "new_uwg_operation_attempted"
                ],
                "stage_entry_count": stage_summary["entry_count"],
                "stage_status_counts": stage_summary[
                    "stage_status_counts"
                ],
                "x2_aggregation_status": stage_summary[
                    "x2_aggregation_status"
                ],
                "local_failure_event_count": telemetry_summary[
                    "event_count"
                ],
                "l6_lane_event_count": telemetry_summary[
                    "l6_lane_event_count"
                ],
                "deterministic_replay_count": completion[
                    "determinism_replay"
                ]["execution_count"],
                "deterministic_artifact_bytes_stable": completion[
                    "determinism_replay"
                ]["artifact_bytes_stable"],
                "w5_authorized": completion["w5_authorized"],
            }
        )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
