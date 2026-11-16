"""Mechanical anti-regression gate for INV-ZERO-BUGFIX-BLAST-RADIUS-CAP.

Verifies that root-cause bug fixes, cohesive refactors, /boost subagents, and /swarm
workers remain free of artificial file-count, wave-count, plan-word, test-batch,
blast-radius confidence penalty, default subagent write-lock, and ghost-hook barriers,
while preserving <= 600-line file budgets and inter-subsystem boundaries.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml  # type: ignore

ROOT = Path(__file__).resolve().parents[1]

DEAD_GHOST_HOOK_TOKENS: tuple[str, ...] = (
    "pre_user_prompt_adg_ssot_gate.py",
    "post_agent_adg_audit.py",
    "pre_write_gate.py",
    "post_agent_runtime_rca_audit.py",
    "pre_write_plan_mint_gate.py",
    "post_agent_work_classification_audit.py",
    "pre_workflow_fanout_gate.py",
    "check_ssot_folder_routing.py",
)

AUDITED_RULE_FILES: tuple[str, ...] = (
    ".agents/rules/constitutional.md",
    ".agents/rules/adg_transport_open_per_turn_gate.md",
    ".agents/rules/adg-analysis-procedures.md",
    ".agents/rules/codex-config-lookup.md",
    ".agents/rules/ssot-folder-enforcement.md",
    ".agents/rules/work-item-classification.md",
)

FORBIDDEN_DEFERRAL_ROWS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\|\s*`BUG_DEFERRED`\s*\|", re.MULTILINE),
    re.compile(r"^\|\s*`BUG_SYSTEMIC`\s*\|", re.MULTILINE),
    re.compile(r"grep_search`\s+permitted\s+only\s+to\s+confirm\s+literals", re.IGNORECASE),
)


def validate_zero_bugfix_constraint_floor(repo_root: Path | None = None) -> dict[str, Any]:
    """Validate that zero artificial bug-fix, blast-radius, /boost, or /swarm caps exist."""
    root = Path(repo_root or ROOT).resolve()
    issues: list[str] = []

    # 1. Policy registry thresholds (INV-WAVE-PLAN-MAX-WORDS == 0, INV-ZERO-BUGFIX-BLAST-RADIUS-CAP == 0)
    pol_path = root / "config" / "governance" / "policy_registry.yaml"
    if pol_path.is_file():
        raw = yaml.safe_load(pol_path.read_text(encoding="utf-8"))
        policies = {
            str(p["id"]): p
            for p in (raw.get("policies", []) if isinstance(raw, dict) else [])
            if isinstance(p, dict) and p.get("id")
        }
        plan_words_pol = policies.get("INV-WAVE-PLAN-MAX-WORDS")
        if plan_words_pol is not None and int(plan_words_pol.get("threshold", 0) or 0) != 0:
            issues.append(
                f"INV-WAVE-PLAN-MAX-WORDS must remain 0 (unbounded), found {plan_words_pol.get('threshold')}"
            )
        zero_cap_pol = policies.get("INV-ZERO-BUGFIX-BLAST-RADIUS-CAP")
        if zero_cap_pol is not None and int(zero_cap_pol.get("threshold", 0) or 0) != 0:
            issues.append(
                f"INV-ZERO-BUGFIX-BLAST-RADIUS-CAP must remain 0, found {zero_cap_pol.get('threshold')}"
            )

    # 2. Root AGENTS.md and rule surfaces free of deferral matrices and dead ghost-hook citations
    agents_md = root / "AGENTS.md"
    if agents_md.is_file():
        agents_txt = agents_md.read_text(encoding="utf-8")
        if "Zero Blast-Radius Ceiling" not in agents_txt and (root / ".agents" / "rules" / "work-item-classification.md").is_file():
            issues.append("AGENTS.md missing 'Zero Blast-Radius Ceiling' bug-fix guarantee.")

    for rel_rule in AUDITED_RULE_FILES:
        rpath = root / rel_rule
        if not rpath.is_file():
            continue
        rtxt = rpath.read_text(encoding="utf-8")
        for ghost in DEAD_GHOST_HOOK_TOKENS:
            if ghost in rtxt:
                issues.append(f"{rel_rule} cites nonexistent legacy ghost script '{ghost}'.")
        for pat in FORBIDDEN_DEFERRAL_ROWS:
            if pat.search(rtxt):
                issues.append(f"{rel_rule} contains forbidden bug-deferral or grep-ban clause ('{pat.pattern}').")

    # 3. Runtime behavior invariants on primary repository workspace
    if (root / "tools" / "hitl_governance.py").is_file():
        from tools.adg_impact_tests import select_impacted_tests
        from tools.hitl_governance import calculate_calibrated_confidence
        from tools.prompt_scope_isolation import evaluate_prompt_stage_write_scope

        c_single = calculate_calibrated_confidence({"confidence": 0.80, "blast_radius_layers": 1})
        c_multi = calculate_calibrated_confidence({"confidence": 0.80, "blast_radius_layers": 5})
        if c_single != c_multi:
            issues.append(
                f"Multi-layer blast_radius_layers penalty reintroduced ({c_multi} != {c_single})."
            )

        blocked, _ = evaluate_prompt_stage_write_scope(
            "agents/orchestration/engine.py", root, agent_id="agents-domain-applications-pipeline"
        )
        if blocked:
            issues.append("PROMPT_STAGE_ALLOWED_WRITE_PATHS blocked cross-repo root-cause bug fix.")

        sample_batches = select_impacted_tests([], repo_root=root)
        if "batches" not in sample_batches:
            issues.append("select_impacted_tests missing unbounded batch contract.")

    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
    }
