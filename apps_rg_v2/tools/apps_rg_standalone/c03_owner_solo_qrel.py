"""Operate the non-authoritative OWNER_SOLO_PROVISIONAL C0.3 review lane."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.c03_owner_solo_qrel import (  # noqa: E402
    OwnerSoloQrelError,
    compute_owner_solo_metrics,
    correct_judgment,
    evaluate_owner_solo_non_retrieval_gates,
    finalize_owner_solo_qrels,
    load_owner_solo_context,
    next_blinded_candidate,
    packet_validation_receipt,
    record_judgment,
    status_receipt,
)


def _grade(value: str) -> int:
    if value not in {"0", "1", "2", "3"}:
        raise argparse.ArgumentTypeError("grade must be exactly 0, 1, 2, or 3")
    return int(value)


def _context(args: argparse.Namespace) -> dict:
    return load_owner_solo_context(
        repo_root=args.repo_root,
        exception_policy_path=args.exception_policy,
        execution_manifest_path=args.execution_manifest,
        packet_dir=args.packet_dir,
        runtime_dir=args.runtime_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--packet-dir",
        type=Path,
        default=Path(".runtime/c03-cluster-w8/prelabel_packet"),
    )
    parser.add_argument(
        "--exception-policy",
        type=Path,
        required=True,
        help="runtime-only owner-solo exception policy JSON",
    )
    parser.add_argument(
        "--execution-manifest",
        type=Path,
        required=True,
        help="runtime-only owner-solo execution manifest JSON",
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=Path(".runtime/c03-owner-solo-qrel"),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("packet-validate")
    commands.add_parser("next")
    commands.add_parser("gates")
    for name in ("record", "correct"):
        command = commands.add_parser(name)
        command.add_argument("--item-ref", required=True)
        command.add_argument("--candidate-ref", required=True)
        command.add_argument("--grade", required=True, type=_grade)
        command.add_argument("--rationale", required=True)
    commands.add_parser("finalize")
    commands.add_parser("metrics")
    args = parser.parse_args(argv)
    try:
        context = _context(args)
        if args.command == "status":
            result = status_receipt(context, write=True)
        elif args.command == "packet-validate":
            result = packet_validation_receipt(context, write=True)
        elif args.command == "next":
            result = next_blinded_candidate(context)
        elif args.command == "gates":
            result = evaluate_owner_solo_non_retrieval_gates(context)
        elif args.command == "record":
            result = record_judgment(
                context,
                item_ref=args.item_ref,
                candidate_ref=args.candidate_ref,
                grade=args.grade,
                rationale=args.rationale,
            )
        elif args.command == "correct":
            result = correct_judgment(
                context,
                item_ref=args.item_ref,
                candidate_ref=args.candidate_ref,
                grade=args.grade,
                rationale=args.rationale,
            )
        elif args.command == "finalize":
            result = finalize_owner_solo_qrels(context)
        else:
            result = compute_owner_solo_metrics(context)
    except OwnerSoloQrelError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
