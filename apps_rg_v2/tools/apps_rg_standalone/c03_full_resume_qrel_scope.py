"""Validate the frozen W0 full-resume owner-solo QREL scope."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.c03_full_resume_qrel_scope import (  # noqa: E402
    FullResumeQrelScopeError,
    scope_status,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("command", choices=("status", "validate"), nargs="?", default="status")
    args = parser.parse_args(argv)
    try:
        result = scope_status(args.repo_root)
    except FullResumeQrelScopeError as exc:
        print(json.dumps({"status": "W0_BLOCKED", "reason": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "W0_FROZEN_READY_FOR_W1" else 2


if __name__ == "__main__":
    raise SystemExit(main())
