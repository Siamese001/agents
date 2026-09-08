"""Freeze all 66 private full-resume owner-solo C0.3 rankings for review."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.c03_full_resume_qrel_w2 import (  # noqa: E402
    FullResumeQrelW2Error,
    materialize_w2_rankings,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=(
            Path(os.environ["APPS_RG_EMBEDDING_MODEL_PATH"])
            if os.environ.get("APPS_RG_EMBEDDING_MODEL_PATH")
            else None
        ),
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--w1c-receipt",
        type=Path,
        help="Exact ignored W1C receipt to consume when multiple receipts exist.",
    )
    args = parser.parse_args(argv)
    if args.model_path is None:
        parser.error("--model-path or APPS_RG_EMBEDDING_MODEL_PATH is required")
    try:
        receipt, paths = materialize_w2_rankings(
            args.repo_root,
            model_path=args.model_path,
            device=args.device,
            w1c_receipt_path=args.w1c_receipt,
        )
    except FullResumeQrelW2Error as exc:
        print(json.dumps({"status": "W2_BLOCKED", "reason": str(exc)}, indent=2))
        return 2
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "query_manifest_path": str(paths["query_manifest"]),
                "ranking_receipt_path": str(paths["receipt"]),
                "query_section_count": receipt["rankings"]["query_section_count"],
                "candidate_judgment_count": receipt["rankings"][
                    "candidate_judgment_count"
                ],
                "rankings_or_scores_distributed": receipt["reviewer_visibility"][
                    "ranks_or_scores_distributed"
                ],
                "human_qrels_created": receipt["scope_guards"]["human_qrels_created"],
                "release_authorizing": False,
                "next_action": receipt["next_action"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
