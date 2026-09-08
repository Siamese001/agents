"""Apps RG-only W0 and W5/W6 evidence handoff CLI.

This CLI can generate the frozen W0 v1/v2 technical baseline, freeze
inputs/configuration, capture already-completed Apps RG shadow artifacts,
prepare blinded review material, seal exactly human-authored evidence records,
and verify supplied W6 evidence. It deliberately has no command that starts a
provider/runtime run, creates a human judgment, or activates a treatment.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.evals.l1_cognitive_baseline import (
    build_l1_cognitive_development_baseline_receipt,
    write_l1_cognitive_development_baseline_receipt,
)
from apps_rg.evals.l1_cognitive_blind_review_packet import (
    build_l1_cognitive_blind_review_material,
    write_l1_cognitive_blind_review_material,
)
from apps_rg.evals.l1_cognitive_paired_shadow_capture import (
    build_l1_cognitive_pair_config_receipt,
    build_l1_cognitive_pair_input_receipt,
    capture_l1_cognitive_paired_shadow,
)
from apps_rg.evals.l1_cognitive_paired_cohort import (
    assemble_l1_cognitive_paired_cohort,
)
from apps_rg.evals.l1_cognitive_outcome_protocol import (
    load_l1_cognitive_outcome_protocol,
)
from apps_rg.evals.l1_cognitive_rollout_gate import (
    build_l1_cognitive_rollout_gate,
    seal_l1_cognitive_handoff_record,
    validate_l1_cognitive_rollout_gate,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


def _read_mapping(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return dict(payload)


def _optional_mapping(path: Path | None, *, label: str) -> dict[str, Any] | None:
    return _read_mapping(path, label=label) if path is not None else None


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    destination = Path(path)
    sr.write_stage_receipt(destination, value)
    return destination


def _emit(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    baseline = commands.add_parser(
        "w0-baseline",
        help="write the source-bound development-only v1/v2 W0 baseline receipt",
    )
    baseline.add_argument("--output", type=Path, required=True)

    freeze_input = commands.add_parser(
        "freeze-input", help="write a source-bound, non-secret paired-input receipt"
    )
    freeze_input.add_argument("--target-company", required=True)
    freeze_input.add_argument("--target-role", required=True)
    freeze_input.add_argument("--target-level", required=True)
    freeze_input.add_argument("--generation-mode", required=True)
    freeze_input.add_argument("--jd", type=Path, required=True)
    freeze_input.add_argument("--briefing", type=Path, required=True)
    freeze_input.add_argument("--resume", type=Path, required=True)
    freeze_input.add_argument("--output", type=Path, required=True)

    freeze_config = commands.add_parser(
        "freeze-config",
        help="write a provider/tool configuration receipt for both arms",
    )
    freeze_config.add_argument("--generation-mode", required=True)
    freeze_config.add_argument("--lane-provider", default="")
    freeze_config.add_argument("--auto-research-internal", action="store_true")
    freeze_config.add_argument(
        "--non-product-provider-preflight-disabled", action="store_true"
    )
    freeze_config.add_argument("--output", type=Path, required=True)

    capture = commands.add_parser(
        "capture-pair",
        help="capture two already-completed Apps RG shadow-arm artifacts",
    )
    capture.add_argument("--campaign-root", type=Path, required=True)
    capture.add_argument("--pair-id", required=True)
    capture.add_argument("--control-run-root", type=Path, required=True)
    capture.add_argument("--candidate-run-root", type=Path, required=True)
    capture.add_argument("--frozen-input", type=Path, required=True)
    capture.add_argument("--config", type=Path, required=True)

    cohort = commands.add_parser(
        "assemble-paired-cohort",
        help="join one-pair Apps RG capture receipts without changing their evidence",
    )
    cohort.add_argument(
        "--source-paired-receipt",
        type=Path,
        action="append",
        required=True,
        help="one source receipt from capture-pair; repeat once per pair",
    )
    cohort.add_argument("--paired-receipt-output", type=Path, required=True)
    cohort.add_argument("--cohort-manifest-output", type=Path, required=True)

    blind = commands.add_parser(
        "build-blind-review",
        help="write a reviewer packet and separately sealed arm map",
    )
    blind.add_argument("--paired-receipt", type=Path, required=True)
    blind.add_argument(
        "--run-roots",
        type=Path,
        required=True,
        help="JSON object mapping each source pair ID to control/candidate run roots",
    )
    blind.add_argument("--repo-root", type=Path, required=True)
    blind.add_argument("--nonce", required=True)
    blind.add_argument("--packet-output", type=Path, required=True)
    blind.add_argument("--sealed-mapping-output", type=Path, required=True)

    seal = commands.add_parser(
        "seal-evidence",
        help=(
            "copy an authored W5/W6 record with its integrity digest; "
            "does not validate or attest"
        ),
    )
    seal.add_argument("--input", type=Path, required=True)
    seal.add_argument(
        "--digest-field",
        choices=("record_digest", "plan_digest", "approval_digest"),
        required=True,
    )
    seal.add_argument("--output", type=Path, required=True)

    rollout = commands.add_parser(
        "rollout-gate", help="write a non-activating W6 readiness receipt"
    )
    rollout.add_argument("--paired-receipt", type=Path)
    rollout.add_argument("--paired-cohort-manifest", type=Path)
    rollout.add_argument("--blind-review-packet", type=Path)
    rollout.add_argument("--sealed-mapping", type=Path)
    rollout.add_argument("--human-outcome", type=Path)
    rollout.add_argument("--cognitive-capability-outcome", type=Path)
    rollout.add_argument("--protected-holdout-outcome", type=Path)
    rollout.add_argument("--rollout-plan", type=Path)
    rollout.add_argument("--release-approval", type=Path)
    rollout.add_argument("--output", type=Path, required=True)

    return parser


def _run_freeze_input(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    receipt = build_l1_cognitive_pair_input_receipt(
        target_company=args.target_company,
        target_role=args.target_role,
        target_level=args.target_level,
        generation_mode=args.generation_mode,
        jd_path=args.jd,
        briefing_path=args.briefing,
        resume_path=args.resume,
    )
    path = _write_json(args.output, receipt)
    return 0, {"status": "PASS", "artifact": str(path), "receipt": receipt}


def _run_w0_baseline(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    receipt = build_l1_cognitive_development_baseline_receipt()
    from apps_rg.evals.l1_cognitive_qa import load_development_corpus

    path = write_l1_cognitive_development_baseline_receipt(
        output_path=args.output,
        receipt=receipt,
        corpus=load_development_corpus(),
    )
    return 0, {
        "status": "TECHNICAL_BASELINE_COMPLETE",
        "artifact": str(path),
        "receipt_digest": receipt["receipt_digest"],
        "dominant_failure_slice": receipt["summary"]["dominant_failure_slice"],
        "assertions": {
            "does_not_invoke_runtime": True,
            "does_not_create_human_judgment": True,
            "does_not_measure_candidate_quality": True,
        },
    }


def _run_freeze_config(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    receipt = build_l1_cognitive_pair_config_receipt(
        generation_mode=args.generation_mode,
        auto_research_internal=bool(args.auto_research_internal),
        non_product_provider_preflight_disabled=bool(
            args.non_product_provider_preflight_disabled
        ),
        lane_provider=args.lane_provider,
    )
    path = _write_json(args.output, receipt)
    return 0, {"status": "PASS", "artifact": str(path), "receipt": receipt}


def _run_capture_pair(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    paired = capture_l1_cognitive_paired_shadow(
        campaign_root=args.campaign_root,
        pair_id=args.pair_id,
        control_run_root=args.control_run_root,
        candidate_run_root=args.candidate_run_root,
        frozen_input_receipt=_read_mapping(
            args.frozen_input, label="frozen input receipt"
        ),
        config_receipt=_read_mapping(args.config, label="configuration receipt"),
    )
    return 0, {
        "status": "PASS",
        "artifact": str(
            Path(args.campaign_root) / "l1_cognitive_paired_shadow_receipt.json"
        ),
        "receipt": paired,
    }


def _run_assemble_paired_cohort(
    args: argparse.Namespace,
) -> tuple[int, dict[str, Any]]:
    source_paths = [Path(path).resolve() for path in args.source_paired_receipt]
    paired_output = Path(args.paired_receipt_output).resolve()
    manifest_output = Path(args.cohort_manifest_output).resolve()
    if paired_output == manifest_output:
        raise ValueError("paired cohort outputs must be distinct")
    if paired_output.exists() or manifest_output.exists():
        raise ValueError("paired cohort outputs must not already exist")
    if paired_output in source_paths or manifest_output in source_paths:
        raise ValueError("paired cohort outputs must differ from source receipts")
    paired_receipt, manifest = assemble_l1_cognitive_paired_cohort(
        protocol=load_l1_cognitive_outcome_protocol(),
        source_paired_receipts=[
            _read_mapping(path, label="source paired capture receipt")
            for path in source_paths
        ],
    )
    paired_path = _write_json(paired_output, paired_receipt)
    manifest_path = _write_json(manifest_output, manifest)
    return 0, {
        "status": "PASS",
        "paired_receipt_artifact": str(paired_path),
        "paired_receipt_digest": paired_receipt["receipt_digest"],
        "cohort_manifest_artifact": str(manifest_path),
        "cohort_manifest_digest": manifest["cohort_digest"],
        "pair_count": len(paired_receipt["pairs"]),
        "assertions": {
            "does_not_invoke_runtime": True,
            "does_not_create_human_judgment": True,
            "does_not_activate_treatment": True,
        },
    }


def _run_build_blind_review(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    paired = _read_mapping(args.paired_receipt, label="paired receipt")
    run_roots = _read_mapping(args.run_roots, label="run-roots mapping")
    packet, sealed = build_l1_cognitive_blind_review_material(
        paired_receipt=paired,
        run_roots=run_roots,
        repo_root=args.repo_root,
        nonce=args.nonce,
    )
    packet_path, mapping_path = write_l1_cognitive_blind_review_material(
        packet_path=args.packet_output,
        sealed_mapping_path=args.sealed_mapping_output,
        packet=packet,
        sealed_mapping=sealed,
    )
    return 0, {
        "status": "PENDING_HUMAN_REVIEW",
        "packet_artifact": str(packet_path),
        "sealed_mapping_artifact": str(mapping_path),
        "packet_digest": packet["packet_digest"],
        "sealed_mapping_digest": sealed["mapping_digest"],
    }


def _run_seal_evidence(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    source_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    if source_path == output_path:
        raise ValueError("sealed evidence output must differ from the authored input")
    if output_path.exists():
        raise ValueError("sealed evidence output already exists")
    sealed = seal_l1_cognitive_handoff_record(
        _read_mapping(source_path, label="authored evidence record"),
        digest_field=args.digest_field,
    )
    path = _write_json(output_path, sealed)
    return 0, {
        "status": "DIGEST_SEALED_NOT_VALIDATED",
        "artifact": str(path),
        "digest_field": args.digest_field,
        "digest": sealed[args.digest_field],
        "assertions": {
            "does_not_create_human_judgment": True,
            "does_not_attest_human_identity": True,
            "does_not_authorize_rollout": True,
        },
    }


def _run_rollout_gate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    sources = {
        "paired_receipt": _optional_mapping(
            args.paired_receipt, label="paired receipt"
        ),
        "paired_cohort_manifest": _optional_mapping(
            args.paired_cohort_manifest, label="paired cohort manifest"
        ),
        "blind_review_packet": _optional_mapping(
            args.blind_review_packet, label="blind review packet"
        ),
        "sealed_mapping": _optional_mapping(
            args.sealed_mapping, label="sealed mapping"
        ),
        "human_outcome": _optional_mapping(args.human_outcome, label="human outcome"),
        "cognitive_capability_outcome": _optional_mapping(
            args.cognitive_capability_outcome,
            label="cognitive capability outcome",
        ),
        "protected_holdout_outcome": _optional_mapping(
            args.protected_holdout_outcome, label="protected holdout outcome"
        ),
        "rollout_plan": _optional_mapping(args.rollout_plan, label="rollout plan"),
        "release_approval": _optional_mapping(
            args.release_approval, label="release approval"
        ),
    }
    receipt = build_l1_cognitive_rollout_gate(**sources)
    validate_l1_cognitive_rollout_gate(receipt, **sources)
    path = _write_json(args.output, receipt)
    result = {"artifact": str(path), **receipt}
    return (
        0 if receipt["status"] == "READY_FOR_HUMAN_OPERATED_LIMITED_ROLLOUT" else 2,
        result,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run a non-runtime Apps RG L1 evidence-handoff operation."""

    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "w0-baseline":
            code, result = _run_w0_baseline(args)
        elif args.command == "freeze-input":
            code, result = _run_freeze_input(args)
        elif args.command == "freeze-config":
            code, result = _run_freeze_config(args)
        elif args.command == "capture-pair":
            code, result = _run_capture_pair(args)
        elif args.command == "assemble-paired-cohort":
            code, result = _run_assemble_paired_cohort(args)
        elif args.command == "build-blind-review":
            code, result = _run_build_blind_review(args)
        elif args.command == "seal-evidence":
            code, result = _run_seal_evidence(args)
        else:
            code, result = _run_rollout_gate(args)
    except ValueError as exc:
        print(
            json.dumps({"status": "ERROR", "reason": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    _emit(result)
    return code
