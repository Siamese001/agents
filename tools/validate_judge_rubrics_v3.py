#!/usr/bin/env python3
"""Anti-Bloat & Schema Gate for Clean-Slate Judge v3 Rubrics in `agents`.

Delegates core validation to centralized `~/.gemini/config/plugins/core-governance/mcp/judge_v3_rigor_engine.py`
while checking `agents`-specific 5-cluster coverage, 1:1 `human_calibration_studio` parity,
and `config/governance/judge_domain_guards_v3.json` forbidden-noun isolation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.graders.judge._core_governance_bridge import get_judge_v3_rigor_engine
from apps_eval.graders.judge.v3_registry import (
    DEFAULT_JUDGE_RUBRICS_V3_REL_PATH,
    JudgeRubricRegistryV3,
     REQUIRED_CLUSTERS,
)

DEFAULT_EXTERNAL_RUBRIC_V2_REL_PATH = Path("config/governance/external_judge_rubric_v2.json")
DEFAULT_DOMAIN_GUARDS_V3_REL_PATH = Path("config/governance/judge_domain_guards_v3.json")


def validate_judge_rubrics_v3(
    rubric_path: Path | None = None,
    external_rubric_path: Path | None = None,
    domain_guards_path: Path | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    r_path = Path(rubric_path) if rubric_path is not None else (REPO_ROOT / DEFAULT_JUDGE_RUBRICS_V3_REL_PATH)
    e_path = (
        Path(external_rubric_path)
        if external_rubric_path is not None
        else (REPO_ROOT / DEFAULT_EXTERNAL_RUBRIC_V2_REL_PATH)
    )
    g_path = (
        Path(domain_guards_path)
        if domain_guards_path is not None
        else (REPO_ROOT / DEFAULT_DOMAIN_GUARDS_V3_REL_PATH)
    )
    eng = get_judge_v3_rigor_engine()
    ok, errors, stats = eng.validate_repo_judge_rubrics_v3(
        r_path,
        domain_guards_path=g_path if g_path.is_file() else None,
        external_rubric_path=e_path,
        required_clusters=tuple(REQUIRED_CLUSTERS),
    )
    stats["clusters"] = list(REQUIRED_CLUSTERS)
    if r_path.is_file() and e_path.is_file():
        try:
            reg = JudgeRubricRegistryV3.load(r_path)
            studio_prof = reg.get_profile("agent_trace_and_calibration:human_calibration_studio")
            ext_doc = json.loads(e_path.read_text(encoding="utf-8"))
            ext_checks = {str(c["id"]): c for c in (ext_doc.get("checks") or []) if isinstance(c, dict) and c.get("id")}
            if set(studio_prof.check_ids) != set(ext_checks):
                errors.append(
                    f"1:1 studio parity mismatch: profile checks {sorted(studio_prof.check_ids)} != external v2 {sorted(ext_checks)}."
                )
        except Exception as exc:  # guardian: allow-broad-exception -- surface parity check error cleanly
            errors.append(f"Studio 1:1 parity check failed: {exc}")
    return len(errors) == 0, errors, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Judge v3 declarative rubric SSOT via core-governance.")
    parser.add_argument("--rubric-path", type=Path, default=None)
    parser.add_argument("--external-rubric-path", type=Path, default=None)
    parser.add_argument("--domain-guards-path", type=Path, default=None)
    parser.add_argument("--receipt-out", type=Path, default=None)
    args = parser.parse_args(argv)

    ok, errors, stats = validate_judge_rubrics_v3(
        args.rubric_path,
        args.external_rubric_path,
        args.domain_guards_path,
    )
    if args.receipt_out is not None:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        receipt = {"status": "PASS" if ok else "FAIL", "errors": errors, "stats": stats}
        raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        receipt["receipt_digest"] = hashlib.sha256(raw).hexdigest()
        args.receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not ok:
        for err in errors:
            print(f"[FAIL] {err}", file=sys.stderr)
        return 1

    print(f"[PASS] judge_rubrics_v3.json ({len(stats['profiles'])} profiles across {len(REQUIRED_CLUSTERS)} clusters)")
    for pid, pstat in sorted(stats["profiles"].items()):
        print(
            f"  - {pid:<52} | {pstat['rendered_words']:>3}w / {pstat['rendered_chars']:>4}c | "
            f"checks={pstat['check_count']} | thresh={pstat['pass_threshold']:.2f}"
        )
    print(f"[PASS] external_judge_rubric_v2.json sha256={stats.get('external_judge_rubric_v2_sha256', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
