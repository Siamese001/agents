#!/usr/bin/env python3
"""Backfill verified 11/01/2026-11/03/2026 operator feedback lessons into FeedbackLearningStore."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.orchestration.learning_store import (  # noqa: E402
    DEFAULT_LEARNING_STORE_PATH,
    FeedbackLearningStore,
)

DEFAULT_MANIFEST_PATH = (
    _REPO_ROOT / "config" / "governance" / "feedback_learning_lessons_11-03-2026.json"
)


def backfill_lessons(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    db_path: Path | str | None = None,
) -> dict[str, object]:
    """Load verified feedback lessons from manifest and persist idempotently."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    lessons = payload.get("lessons", [])
    target_db = db_path or DEFAULT_LEARNING_STORE_PATH

    store = FeedbackLearningStore(target_db)
    recorded_hashes: list[str] = []
    try:
        for item in lessons:
            sig_hash = store.record_feedback_lesson(
                item["failure_kind"],
                item["constraint"],
                run_id=item["run_id"],
                repair_hint=item["repair_hint"],
                action_taken=item.get("action_taken", "OPERATOR_FEEDBACK_RESOLUTION"),
                outcome="SUCCESS",
            )
            recorded_hashes.append(sig_hash)
        summary = store.get_summary()
    finally:
        store.close()

    return {
        "status": "PASS",
        "manifest_path": str(manifest_path),
        "lessons_processed": len(recorded_hashes),
        "signature_hashes": recorded_hashes,
        "summary": summary,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill verified operator feedback lessons into FeedbackLearningStore."
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST_PATH),
        help="Path to feedback lessons JSON manifest",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional override path for feedback_learning.sqlite",
    )
    args = parser.parse_args(argv)

    result = backfill_lessons(Path(args.manifest).resolve(), db_path=args.db_path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
