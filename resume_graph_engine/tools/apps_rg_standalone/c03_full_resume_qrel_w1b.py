"""Materialize W1B derived multi-node clusters for full-resume QREL review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.owner_solo.c03_full_resume_qrel_derived_clusters import (  # noqa: E402
    DerivedClusterError,
    write_derived_bundle_registry,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        path, payload = write_derived_bundle_registry(args.repo_root)
    except DerivedClusterError as exc:
        print(json.dumps({"status": "W1B_BLOCKED", "reason": str(exc)}, indent=2))
        return 2
    print(
        json.dumps(
            {
                "status": payload["status"],
                "derived_registry_path": str(path),
                "derived_registry_sha256": payload["derived_registry_sha256"],
                "coverage": payload["coverage"],
                "human_qrels_created": False,
                "release_authorizing": False,
                "next_action": "W1C_REGENERATE_COMBINED_PROJECTION",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
