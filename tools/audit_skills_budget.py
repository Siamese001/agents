#!/usr/bin/env python3
"""Skills capacity and description token budget auditor for the Agents repository.

Enforces the hard ceiling of <= 26 root skills and <= 2,000 description tokens.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_SKILLS_CAP = 26
MAX_DESCRIPTION_TOKENS = 2000


def _extract_description(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def audit_skills_budget(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Audits root .agents/skills/*/SKILL.md against count and token ceilings."""
    skills_dir = repo_root / ".agents" / "skills"
    skill_files = sorted(skills_dir.glob("*/SKILL.md")) if skills_dir.is_dir() else []
    count = len(skill_files)
    total_words = 0
    skills_inventory: list[dict[str, Any]] = []

    for sf in skill_files:
        desc = _extract_description(sf)
        words = len(desc.split())
        total_words += words
        skills_inventory.append({
            "name": sf.parent.name,
            "description_words": words,
        })

    estimated_tokens = int(round(total_words * 1.3))
    violations: list[str] = []
    if count > MAX_SKILLS_CAP:
        violations.append(f"Skill count {count} exceeds hard cap {MAX_SKILLS_CAP}")
    if estimated_tokens > MAX_DESCRIPTION_TOKENS:
        violations.append(f"Description tokens {estimated_tokens} exceed budget {MAX_DESCRIPTION_TOKENS}")

    is_clean = len(violations) == 0
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "skill_count": count,
        "max_skills_cap": MAX_SKILLS_CAP,
        "utilization_pct": round((count / MAX_SKILLS_CAP) * 100.0, 2),
        "estimated_description_tokens": estimated_tokens,
        "max_description_tokens": MAX_DESCRIPTION_TOKENS,
        "skills": skills_inventory,
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Agents repository skill budget.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rep = audit_skills_budget(args.repo_root.resolve())
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(
            f"[{rep['status']}] Skills Budget: {rep['skill_count']}/{rep['max_skills_cap']} skills "
            f"({rep['utilization_pct']}%), {rep['estimated_description_tokens']}/{rep['max_description_tokens']} tokens."
        )
    return 0 if rep["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
