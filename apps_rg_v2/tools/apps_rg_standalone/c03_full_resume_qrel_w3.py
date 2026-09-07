"""Build or validate the W3 blinded full-resume owner-review packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.c03_full_resume_qrel_w3 import (  # noqa: E402
    DEFAULT_PACKET_DIR,
    FullResumeQrelW3Error,
    materialize_w3_packet,
    validate_w3_readiness_receipt,
)


def _safe_summary(value: dict[str, object]) -> dict[str, object]:
    """Return CLI fields that do not disclose the sealed mapping or nonce."""

    return {
        "status": value["status"],
        "reviewer_item_count": value.get("reviewer_item_count")
        or (value.get("packet") or {}).get("review_item_count"),
        "candidate_judgment_count": value.get("candidate_judgment_count")
        or (value.get("packet") or {}).get("candidate_judgment_count"),
        "reviewer_visible_rank_score_split_cluster_or_model_leakage": value.get(
            "reviewer_visible_rank_score_split_cluster_or_model_leakage"
        )
        if "reviewer_visible_rank_score_split_cluster_or_model_leakage" in value
        else (value.get("packet") or {}).get(
            "reviewer_visible_rank_score_split_cluster_or_model_leakage"
        ),
        "human_grades_present": value.get("human_grades_present")
        if "human_grades_present" in value
        else (value.get("review_progress") or {}).get("human_grades_created"),
        "next_action": value.get("next_action", "W3_START_BLINDED_OWNER_REVIEW_UI"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"), nargs="?", default="build")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--packet-dir", type=Path, default=REPO_ROOT / DEFAULT_PACKET_DIR)
    parser.add_argument("--w2-receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            receipt, _paths = materialize_w3_packet(
                args.repo_root,
                packet_dir=args.packet_dir,
                w2_receipt_path=args.w2_receipt,
            )
            summary = _safe_summary(receipt)
        else:
            validation = validate_w3_readiness_receipt(
                args.repo_root,
                packet_dir=args.packet_dir,
                w2_receipt_path=args.w2_receipt,
            )
            summary = _safe_summary(validation)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except FullResumeQrelW3Error as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
