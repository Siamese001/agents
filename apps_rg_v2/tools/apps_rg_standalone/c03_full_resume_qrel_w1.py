"""Run the fail-closed W1 full-resume QREL preflight."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.c03_full_resume_qrel_w1 import (  # noqa: E402
    FullResumeQrelW1Error,
    write_w1_preflight_receipt,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        result = write_w1_preflight_receipt(args.repo_root)
    except FullResumeQrelW1Error as exc:
        print(json.dumps({"status": "W1_BLOCKED", "reason": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "W1_READY_FOR_RANKING_GENERATION" else 2


if __name__ == "__main__":
    raise SystemExit(main())
