"""Standalone CLI for authoritative evaluation control-plane operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .controller import execute_controller_plan
from .cluster_authority import evaluate_cluster_authority_pipeline
from .cluster_retrieval import evaluate_authoritative_cluster_retrieval
from .cluster_release import (
    freeze_cluster_calibration_thresholds,
    qualify_cluster_embedding_release,
)
from .cluster_runtime import evaluate_cluster_runtime_quality
from .grounding import evaluate_authoritative_grounding
from .manifest import validate_evaluation_manifest
from .repeatability import evaluate_controller_bound_repeatability
from .retrieval import evaluate_authoritative_retrieval
from .reviews import evaluate_authoritative_sections, evaluate_authoritative_whole_resume
from .validity import evaluate_authoritative_validity


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apps RG source-bound evaluation control plane")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--expected-digest", required=True)
    controller = subparsers.add_parser("run-controller")
    controller.add_argument("--plan", type=Path, required=True)
    controller.add_argument("--expected-plan-digest", required=True)
    controller.add_argument("--output-root", type=Path, required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument(
        "--lane",
        choices=(
            "retrieval",
            "cluster-retrieval",
            "cluster-authority",
            "cluster-runtime",
            "cluster-threshold-freeze",
            "cluster-release",
            "grounding",
            "sections",
            "whole-resume",
            "repeatability",
            "validity",
        ),
        required=True,
    )
    evaluate.add_argument("--request", type=Path, required=True)
    evaluate.add_argument("--output", type=Path)
    return parser


def _evaluate_request(lane: str, request: dict[str, object]) -> dict[str, object]:
    if "authority_receipt_path" in request:
        request["authority_receipt_path"] = Path(str(request["authority_receipt_path"]))
    if lane == "retrieval":
        cases = request.pop("cases")
        return evaluate_authoritative_retrieval(cases, **request)  # type: ignore[arg-type]
    if lane == "cluster-retrieval":
        cases = request.pop("cases")
        threshold_policy = request.pop("threshold_policy")
        return evaluate_authoritative_cluster_retrieval(
            cases,
            threshold_policy=threshold_policy,
            **request,
        )  # type: ignore[arg-type]
    if lane == "cluster-authority":
        return evaluate_cluster_authority_pipeline(**request)  # type: ignore[arg-type]
    if lane == "cluster-runtime":
        return evaluate_cluster_runtime_quality(**request)  # type: ignore[arg-type]
    if lane == "cluster-threshold-freeze":
        return freeze_cluster_calibration_thresholds(**request)  # type: ignore[arg-type]
    if lane == "cluster-release":
        return qualify_cluster_embedding_release(**request)  # type: ignore[arg-type]
    if lane == "grounding":
        return evaluate_authoritative_grounding(**request)
    if lane == "sections":
        input_bundle = request.pop("input_bundle")
        review_bundle = request.pop("review_bundle")
        return evaluate_authoritative_sections(input_bundle, review_bundle, **request)
    if lane == "whole-resume":
        bundle = request.pop("bundle")
        return evaluate_authoritative_whole_resume(bundle, **request)
    if lane == "repeatability":
        run_set = request.pop("run_set")
        return evaluate_controller_bound_repeatability(run_set, **request)
    return evaluate_authoritative_validity(**request)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    value = (
        json.loads(args.manifest.read_text(encoding="utf-8"))
        if args.command == "validate-manifest"
        else None
    )
    if args.command == "validate-manifest":
        reasons = validate_evaluation_manifest(value, expected_digest=args.expected_digest)
        print(
            json.dumps(
                {"status": "PASS" if not reasons else "UNKNOWN", "reasons": reasons},
                sort_keys=True,
            )
        )
        return 0 if not reasons else 2
    if args.command == "evaluate":
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("authoritative evaluation request must be an object")
        receipt = _evaluate_request(args.lane, request)
        encoded = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
        print(encoded, end="")
        return {"PASS": 0, "FAIL": 1}.get(str(receipt.get("status")), 2)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    run_set, manifest = execute_controller_plan(
        plan,
        output_root=args.output_root,
        expected_plan_digest=args.expected_plan_digest,
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "run_set_digest": run_set["bundle_digest"],
                "controller_manifest_digest": manifest["record_digest"],
            },
            sort_keys=True,
        )
    )
    return 0
