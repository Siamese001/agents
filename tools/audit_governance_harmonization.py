#!/usr/bin/env python3
"""Cross-Surface Governance Harmonization & SSOT Drift Auditor (Tier 2 Stage 9).

Scans AGENTS.md, .agents/rules/*.md, .agents/skills/*/SKILL.md, .agents/hooks.json,
config/governance/policy_registry.yaml, and config/governance/risk_lanes_policy.json for:
1. Context budget compliance (AGENTS.md <= 200 lines, skills < 4000 tokens).
2. Policy registry & threshold parity (risk lanes fail-closed default, HITL margin,
   executive_summary 4.7/5.0 floor, required AI-SDLC policy IDs).
3. Broken script cross-references in rules and skills.
4. Hook-to-dispatcher handler parity in .agents/hooks.json vs tools/hook_dispatch.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.audit_skills_budget import audit_skills_budget
from tools.validate_turn_gates import load_policy_registry

REQUIRED_AI_SDLC_POLICY_IDS: tuple[str, ...] = (
    "INV-RISK-TIERED-CHANGE-LANES",
    "INV-EVALS-CONSTRUCT-VALIDITY-GATE",
    "INV-ANTI-OVERFITTING-MULTI-JD",
    "INV-GOVERNANCE-HARMONIZATION-GATE",
)

SCRIPT_REF_RE = re.compile(r"`(tools/[a-zA-Z0-9_./-]+\.py)`")
HOOK_FLAG_RE = re.compile(r"--hook\s+([a-zA-Z0-9_-]+)")
MAX_ALWAYS_ON_BYTES = 36000


def _check_always_on_budget(repo_root: Path) -> tuple[list[dict[str, Any]], int]:
    findings: list[dict[str, Any]] = []
    total_bytes = 0
    agents_md = repo_root / "AGENTS.md"
    if agents_md.is_file():
        total_bytes += agents_md.stat().st_size
    rules_dir = repo_root / ".agents" / "rules"
    if rules_dir.is_dir():
        for md_path in sorted(rules_dir.glob("*.md")):
            text = md_path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"^trigger:\s*always_on\b", text, re.MULTILINE):
                total_bytes += md_path.stat().st_size
    if total_bytes > MAX_ALWAYS_ON_BYTES:
        findings.append(
            {
                "severity": "CRITICAL",
                "category": "context_budget",
                "message": (
                    f"Combined AGENTS.md + always_on rules size ({total_bytes} bytes) "
                    f"exceeds {MAX_ALWAYS_ON_BYTES}-byte inline budget ceiling."
                ),
            }
        )
    return findings, total_bytes


def _check_model_decision_descriptions(repo_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rules_dir = repo_root / ".agents" / "rules"
    if not rules_dir.is_dir():
        return findings
    for md_path in sorted(rules_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        fm = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not fm:
            continue
        front = fm.group(1)
        if re.search(r"^trigger:\s*model_decision\b", front, re.MULTILINE) and not re.search(
            r"^description:\s*\S+", front, re.MULTILINE
        ):
            rel = md_path.relative_to(repo_root).as_posix()
            findings.append(
                {
                    "severity": "CRITICAL",
                    "category": "context_budget",
                    "message": f"model_decision rule '{rel}' is missing a non-empty 'description:' frontmatter field.",
                }
            )
    return findings


def _check_policy_and_threshold_parity(repo_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    policies = load_policy_registry(repo_root)
    for pid in REQUIRED_AI_SDLC_POLICY_IDS:
        if pid not in policies:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "category": "policy_parity",
                    "message": f"Required AI-SDLC policy '{pid}' missing from config/governance/policy_registry.yaml.",
                }
            )
        else:
            enforcer = str(policies[pid].get("enforcer") or "").strip()
            if enforcer and not (repo_root / enforcer).is_file():
                findings.append(
                    {
                        "severity": "CRITICAL",
                        "category": "policy_parity",
                        "message": f"Policy '{pid}' enforcer '{enforcer}' does not exist.",
                    }
                )
            rule_ref = str(policies[pid].get("rule_reference") or "").strip()
            if rule_ref and not (repo_root / rule_ref).is_file():
                findings.append(
                    {
                        "severity": "CRITICAL",
                        "category": "policy_parity",
                        "message": f"Policy '{pid}' rule_reference '{rule_ref}' does not exist.",
                    }
                )

    risk_path = repo_root / "config" / "governance" / "risk_lanes_policy.json"
    if not risk_path.is_file():
        findings.append(
            {
                "severity": "CRITICAL",
                "category": "policy_parity",
                "message": "Missing config/governance/risk_lanes_policy.json.",
            }
        )
    else:
        try:
            risk_data = json.loads(risk_path.read_text(encoding="utf-8"))
            if int(risk_data.get("default_unrecognized_lane", 0)) != 2:
                findings.append(
                    {
                        "severity": "CRITICAL",
                        "category": "threshold_drift",
                        "message": "risk_lanes_policy.json default_unrecognized_lane must equal 2 (fail-closed).",
                    }
                )
        except (OSError, ValueError) as exc:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "category": "policy_parity",
                    "message": f"Malformed risk_lanes_policy.json: {exc}",
                }
            )

    hitl_pol = policies.get("INV-HITL-AMBIGUITY-MARGIN") or {}
    if float(hitl_pol.get("threshold", 0.0)) != 0.20:
        findings.append(
            {
                "severity": "CRITICAL",
                "category": "threshold_drift",
                "message": f"INV-HITL-AMBIGUITY-MARGIN threshold drifted from 0.20: {hitl_pol.get('threshold')}",
            }
        )
    return findings


def _check_broken_script_refs(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    broken_refs: list[str] = []
    targets: list[Path] = []
    rules_dir = repo_root / ".agents" / "rules"
    if rules_dir.is_dir():
        targets.extend(sorted(rules_dir.glob("*.md")))
    skills_dir = repo_root / ".agents" / "skills"
    if skills_dir.is_dir():
        targets.extend(sorted(skills_dir.glob("*/SKILL.md")))

    for md_path in targets:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        rel_md = md_path.relative_to(repo_root).as_posix()
        for match in SCRIPT_REF_RE.finditer(text):
            ref = match.group(1)
            if "*" in ref or "<" in ref:
                continue
            if not (repo_root / ref).is_file():
                entry = f"{rel_md} -> {ref}"
                broken_refs.append(entry)
                findings.append(
                    {
                        "severity": "CRITICAL",
                        "category": "broken_reference",
                        "message": f"Broken script reference in {rel_md}: '{ref}' does not exist.",
                    }
                )
    return findings, sorted(set(broken_refs))


def _check_hooks_parity(repo_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    hooks_path = repo_root / ".agents" / "hooks.json"
    dispatch_path = repo_root / "tools" / "hook_dispatch.py"
    if not hooks_path.is_file() or not dispatch_path.is_file():
        return [
            {
                "severity": "CRITICAL",
                "category": "hooks_parity",
                "message": "Missing .agents/hooks.json or tools/hook_dispatch.py.",
            }
        ]
    dispatch_text = dispatch_path.read_text(encoding="utf-8", errors="ignore")
    hooks_text = hooks_path.read_text(encoding="utf-8", errors="ignore")
    for hook_name in sorted(set(HOOK_FLAG_RE.findall(hooks_text))):
        if f'"{hook_name}"' not in dispatch_text and f"'{hook_name}'" not in dispatch_text:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "category": "hooks_parity",
                    "message": f"Hook handler '{hook_name}' referenced in .agents/hooks.json not found in tools/hook_dispatch.py.",
                }
            )
    return findings


def audit_governance_harmonization(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    findings: list[dict[str, Any]] = []

    agents_md = root / "AGENTS.md"
    agents_lines = len(agents_md.read_text(encoding="utf-8").splitlines()) if agents_md.is_file() else 0
    if agents_lines == 0 or agents_lines > 200:
        findings.append(
            {
                "severity": "CRITICAL",
                "category": "context_budget",
                "message": f"AGENTS.md line count {agents_lines} violates <= 200 line invariant.",
            }
        )

    skills_res = audit_skills_budget(root)
    skills_tokens = int(skills_res.get("tokens", skills_res.get("estimated_description_tokens", 0)))
    skills_ok = bool(skills_res.get("is_clean", False)) and str(skills_res.get("status", "")).upper() == "PASS"
    if not skills_ok:
        findings.append(
            {
                "severity": "CRITICAL",
                "category": "context_budget",
                "message": f"Skills description token budget violated: {skills_tokens} / {skills_res.get('max_tokens', 4000)} (status={skills_res.get('status')}).",
            }
        )

    always_on_findings, always_on_bytes = _check_always_on_budget(root)
    findings.extend(always_on_findings)
    findings.extend(_check_model_decision_descriptions(root))
    findings.extend(_check_policy_and_threshold_parity(root))
    ref_findings, broken_refs = _check_broken_script_refs(root)
    findings.extend(ref_findings)
    findings.extend(_check_hooks_parity(root))

    critical = [f for f in findings if f.get("severity") == "CRITICAL"]
    return {
        "schema_version": "agents.governance_harmonization.v1",
        "status": "PASS" if not critical else "FAIL",
        "agents_md_lines": agents_lines,
        "always_on_bytes": always_on_bytes,
        "skills_tokens": skills_tokens,
        "broken_refs": broken_refs,
        "critical_count": len(critical),
        "finding_count": len(findings),
        "findings": findings,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit cross-surface governance harmonization and drift.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any CRITICAL finding.")
    parser.add_argument("--json-only", action="store_true", help="Emit pure JSON output.")
    args = parser.parse_args(argv)

    report = audit_governance_harmonization(Path(args.repo_root).resolve())
    if args.json_only:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[governance-harmonizer] status={report['status']} "
            f"agents_md_lines={report['agents_md_lines']}/200 "
            f"skills_tokens={report['skills_tokens']}/4000 "
            f"critical={report['critical_count']}"
        )
        for f in report["findings"]:
            print(f"  - [{f['severity']}:{f['category']}] {f['message']}")
    if args.strict and report["critical_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
