#!/usr/bin/env python3
"""Skills capacity, contract integrity, and token budget auditor for the Agents repository.

Enforces:
1. Hard ceiling of <= 26 root skills and description token budget from policy_registry.yaml (INV-SKILLS-BUDGET-MAX-TOKENS).
2. Skill name invariant: frontmatter 'name' must match parent directory name.
3. Non-duplication invariant: zero duplicate skill names or descriptions.
4. Link integrity invariant: zero broken relative markdown links in SKILL.md.
5. Path reference invariant: all tools/*.py and ops_scripts/*.py references must exist on disk.
6. Single-document invariant: zero unlinked orphan .md files inside skill directories.
7. Schema validation: agents/openai.yaml and evals/*.json format and skill_name alignment.
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
DEFAULT_MAX_DESCRIPTION_TOKENS = 4000


def _resolve_max_description_tokens(repo_root: Path) -> int:
    registry_path = repo_root / "config" / "governance" / "policy_registry.yaml"
    if registry_path.is_file():
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
            for entry in raw.get("policies", []):
                if isinstance(entry, dict) and entry.get("id") == "INV-SKILLS-BUDGET-MAX-TOKENS":
                    val = entry.get("threshold")
                    if isinstance(val, (int, float)) and val > 0:
                        return int(val)
        except Exception:  # guardian: allow-silent-swallow -- fallback to default token limit
            pass
    return DEFAULT_MAX_DESCRIPTION_TOKENS


def _extract_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract frontmatter key-value pairs and the remaining body text."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    frontmatter_text = parts[1]
    body = parts[2]
    data: dict[str, str] = {}
    current_key: str | None = None
    multiline_buf: list[str] = []

    for line in frontmatter_text.splitlines():
        m_key = re.match(r"^([a-zA-Z0-9_\-]+)\s*:\s*(.*)$", line)
        if m_key:
            if current_key and multiline_buf:
                data[current_key] = " ".join(multiline_buf).strip().strip("\"'")
                multiline_buf = []
            current_key = m_key.group(1).strip()
            rest = m_key.group(2).strip()
            if rest in ("|", ">", "|-", ">-"):
                multiline_buf = []
            elif rest:
                data[current_key] = rest.strip("\"'")
                current_key = None
        elif current_key and line.startswith(("  ", "    ", "\t")):
            multiline_buf.append(line.strip())

    if current_key and multiline_buf:
        data[current_key] = " ".join(multiline_buf).strip().strip("\"'")

    return data, body


def audit_skills_budget(
    repo_root: Path = REPO_ROOT,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Audits root .agents/skills/*/SKILL.md against count, token, contract, and link ceilings."""
    root = repo_root.resolve()
    skills_dir = root / ".agents" / "skills"
    skill_dirs = sorted([d for d in skills_dir.iterdir() if d.is_dir()]) if skills_dir.is_dir() else []
    count = len(skill_dirs)

    max_desc_tokens = max_tokens or _resolve_max_description_tokens(root)
    total_words = 0
    skills_inventory: list[dict[str, Any]] = []
    violations: list[str] = []

    seen_names: set[str] = set()
    seen_descriptions: dict[str, str] = {}

    for s_dir in skill_dirs:
        skill_name = s_dir.name
        skill_md = s_dir / "SKILL.md"

        if not skill_md.is_file():
            violations.append(f"{skill_name}: Missing mandatory SKILL.md file")
            continue

        text = skill_md.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = _extract_frontmatter(text)

        # 1. Frontmatter name invariant
        fm_name = frontmatter.get("name", "").strip()
        if not fm_name:
            violations.append(f"{skill_name}/SKILL.md: Frontmatter missing 'name'")
        elif fm_name != skill_name:
            violations.append(
                f"{skill_name}/SKILL.md: Frontmatter name '{fm_name}' does not match directory '{skill_name}'"
            )

        # 2. Description invariant & token accounting
        desc = frontmatter.get("description", "").strip()
        if not desc:
            violations.append(f"{skill_name}/SKILL.md: Frontmatter missing 'description'")
        else:
            norm_desc = desc.lower().strip()
            if norm_desc in seen_descriptions:
                violations.append(
                    f"{skill_name}/SKILL.md: Duplicate description identical to {seen_descriptions[norm_desc]}"
                )
            else:
                seen_descriptions[norm_desc] = skill_name

        words = len(desc.split())
        total_words += words
        skills_inventory.append({
            "name": skill_name,
            "description": desc,
            "description_words": words,
        })

        if skill_name in seen_names:
            violations.append(f"{skill_name}: Duplicate skill directory name")
        seen_names.add(skill_name)

        # 3. Orphan markdown files check (only SKILL.md is allowed as .md file)
        extra_mds = sorted([f.name for f in s_dir.glob("*.md") if f.name != "SKILL.md"])
        if extra_mds:
            violations.append(
                f"{skill_name}: Stray un-consolidated companion markdown file(s) found: {extra_mds}. "
                "Consolidate procedures into SKILL.md."
            )

        # 4. Link integrity check (relative markdown links)
        for m in re.finditer(r"\[([^\]]+)\]\(([^)#\s]+)(?:#[^\)]*)?\)", body):
            link_target = m.group(2).strip()
            if link_target.startswith(("http://", "https://", "mailto:", "conversation:", "file://")):
                continue
            resolved_local = (s_dir / link_target).resolve()
            resolved_repo = (root / link_target).resolve()
            if not resolved_local.exists() and not resolved_repo.exists():
                violations.append(
                    f"{skill_name}/SKILL.md: Broken markdown link target '{link_target}'"
                )

        # 5. Tool and ops_scripts path reference existence check
        for m in re.finditer(r"(?:tools|ops_scripts)/[a-zA-Z0-9_\-./]+\.py", text):
            ref_path = m.group(0).strip()
            resolved_script = root / ref_path
            if not resolved_script.is_file():
                violations.append(
                    f"{skill_name}/SKILL.md: References nonexistent script '{ref_path}'"
                )

        # 6. Companion evals & agents schema validation
        openai_yaml = s_dir / "agents" / "openai.yaml"
        if openai_yaml.is_file():
            try:
                import yaml  # type: ignore

                y_data = yaml.safe_load(openai_yaml.read_text(encoding="utf-8")) or {}
                if not isinstance(y_data, dict) or "interface" not in y_data:
                    violations.append(f"{skill_name}/agents/openai.yaml: Missing 'interface' root mapping")
            except Exception as exc:
                violations.append(f"{skill_name}/agents/openai.yaml: Malformed YAML: {exc}")

        evals_json = s_dir / "evals" / "evals.json"
        if evals_json.is_file():
            try:
                e_data = json.loads(evals_json.read_text(encoding="utf-8"))
                if not isinstance(e_data, dict) or e_data.get("skill_name") != skill_name:
                    violations.append(
                        f"{skill_name}/evals/evals.json: 'skill_name' ({e_data.get('skill_name')}) does not match '{skill_name}'"
                    )
            except Exception as exc:
                violations.append(f"{skill_name}/evals/evals.json: Malformed JSON: {exc}")

        trigger_json = s_dir / "evals" / "trigger_queries.json"
        if trigger_json.is_file():
            try:
                t_data = json.loads(trigger_json.read_text(encoding="utf-8"))
                if not isinstance(t_data, list):
                    violations.append(f"{skill_name}/evals/trigger_queries.json: Expected JSON array of queries")
            except Exception as exc:
                violations.append(f"{skill_name}/evals/trigger_queries.json: Malformed JSON: {exc}")

    estimated_tokens = int(round(total_words * 1.3))
    if count > MAX_SKILLS_CAP:
        violations.append(f"Skill count ({count}) exceeds hard cap ({MAX_SKILLS_CAP})")
    if estimated_tokens > max_desc_tokens:
        violations.append(
            f"Description tokens ({estimated_tokens}) exceed budget ({max_desc_tokens} tokens)"
        )

    is_clean = len(violations) == 0
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "skill_count": count,
        "max_skills_cap": MAX_SKILLS_CAP,
        "utilization_pct": round((count / MAX_SKILLS_CAP) * 100.0, 2),
        "tokens": estimated_tokens,
        "estimated_description_tokens": estimated_tokens,
        "max_tokens": max_desc_tokens,
        "max_description_tokens": max_desc_tokens,
        "skills": skills_inventory,
        "violations": violations,
        "issues": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Agents repository skill budget and contract integrity.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root directory")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    rep = audit_skills_budget(args.repo_root.resolve())
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        status_tag = f"[{rep['status']}]"
        print(
            f"{status_tag} Skills Budget: {rep['skill_count']}/{rep['max_skills_cap']} skills "
            f"({rep['utilization_pct']}%), {rep['estimated_description_tokens']}/{rep['max_description_tokens']} tokens."
        )
        if not rep["is_clean"]:
            print("Violations:", file=sys.stderr)
            for v in rep["violations"]:
                print(f"  - {v}", file=sys.stderr)
    return 0 if rep["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
