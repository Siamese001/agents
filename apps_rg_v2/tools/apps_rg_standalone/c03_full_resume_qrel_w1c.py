"""Generate the isolated W1C full-resume owner-solo C0.3 projection."""

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

from apps_rg.evals.owner_solo.c03_full_resume_qrel_w1c import (  # noqa: E402
    FullResumeQrelW1CError,
    materialize_w1c_projection,
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
    args = parser.parse_args(argv)
    if args.model_path is None:
        parser.error("--model-path or APPS_RG_EMBEDDING_MODEL_PATH is required")
    try:
        receipt, paths = materialize_w1c_projection(
            args.repo_root,
            model_path=args.model_path,
            device=args.device,
        )
    except FullResumeQrelW1CError as exc:
        print(json.dumps({"status": "W1C_BLOCKED", "reason": str(exc)}, indent=2))
        return 2
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "combined_registry_path": str(paths["combined_registry"]),
                "projection_path": str(paths["projection"]),
                "receipt_path": str(paths["receipt"]),
                "coverage": receipt["coverage"],
                "human_qrels_created": receipt["scope_guards"]["human_qrels_created"],
                "rankings_frozen": receipt["scope_guards"]["rankings_frozen"],
                "release_authorizing": False,
                "next_action": receipt["next_action"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
