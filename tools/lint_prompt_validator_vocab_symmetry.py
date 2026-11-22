#!/usr/bin/env python3
"""Prompt-to-Validator Shared Vocabulary Symmetry Linter (INV-PROMPT-VALIDATOR-VOCAB-SYMMETRY).

Prevents prompt-vs-validator Catch-22 retry loops across apps_rg by enforcing:
1. Canonical SSOT existence at resume_graph_engine/src/apps_rg/runtime/contracts/prompt_validator_vocab_ssot.py.
2. Every noun in HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS matches HEADLINE_EXECUTIVE_ABSTRACTION_RE.
3. Every recommended phrase in headline_pa._ALLOCATION_ROOT_COMPACT_PHRASES matches
   HEADLINE_EXECUTIVE_ABSTRACTION_RE, stays <= 3 words, and avoids HEADLINE_FORBIDDEN_PLUMBING_LABELS.
4. sanitize_allocated_skill_concept_hint(sid) across every skill_id in master_skills_arsenal_ledger.json
   produces zero COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS substrings.
5. Mandatory prompt producers and X2 validators import from prompt_validator_vocab_ssot without
   shadowing canonical regexes or frozenset lexicons locally.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

SSOT_REL_PATH = "resume_graph_engine/src/apps_rg/runtime/contracts/prompt_validator_vocab_ssot.py"
SSOT_MODULE_IMPORT = "apps_rg.runtime.contracts.prompt_validator_vocab_ssot"
ARSENAL_LEDGER_REL_PATH = "resume_graph_engine/src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
HEADLINE_PA_REL_PATH = "resume_graph_engine/src/apps_rg/runtime/sections/headline_pa.py"

MANDATORY_CONSUMER_IMPORTS: dict[str, tuple[str, ...]] = {
    "resume_graph_engine/src/apps_rg/runtime/sections/headline_pa.py": (
        "HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS",
        "HEADLINE_FORBIDDEN_PLUMBING_LABELS",
    ),
    "resume_graph_engine/src/apps_rg/runtime/sections/competencies_pa.py": (
        "COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS",
        "sanitize_allocated_skill_concept_hint",
    ),
    "resume_graph_engine/src/apps_rg/runtime/sections/ExecutiveVoiceRepairAgent.py": (
        "APPROVED_HEADLINE_SENIORITY_PREFIXES",
        "COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS",
        "HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS",
    ),
    "resume_graph_engine/src/apps_rg/runtime/validators/headline_x2.py": (
        "APPROVED_HEADLINE_SENIORITY_PREFIXES",
        "HEADLINE_EXECUTIVE_ABSTRACTION_RE",
    ),
    "resume_graph_engine/src/apps_rg/runtime/validators/bullet_quality_floor_x2.py": (
        "EXPERIENCE_STRONG_ACTION_VERBS",
    ),
    "resume_graph_engine/src/apps_rg/runtime/validators/narrative_quality_x2.py": (
        "NARRATIVE_AUTHORITY_SIGNALS",
        "NARRATIVE_STRONG_VERBS",
    ),
}

FORBIDDEN_LOCAL_CALL_SHADOWS: dict[str, tuple[str, ...]] = {
    "resume_graph_engine/src/apps_rg/runtime/validators/headline_x2.py": ("_EXECUTIVE_ABSTRACTION_RE",),
    "resume_graph_engine/src/apps_rg/runtime/validators/bullet_quality_floor_x2.py": ("STRONG_ACTION_VERBS",),
    "resume_graph_engine/src/apps_rg/runtime/validators/narrative_quality_x2.py": (
        "NARRATIVE_STRONG_VERBS",
        "NARRATIVE_AUTHORITY_SIGNALS",
    ),
}


def _load_ssot_module(ssot_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("_apps_rg_prompt_validator_vocab_ssot", ssot_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec from {ssot_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _extract_dict_str_values(tree: ast.AST, target_name: str) -> dict[str, str]:
    extracted: dict[str, str] = {}
    for node in ast.walk(tree):
        dict_node: ast.Dict | None = None
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == target_name for t in node.targets) and isinstance(
                node.value, ast.Dict
            ):
                dict_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == target_name and isinstance(node.value, ast.Dict):
                dict_node = node.value
        if dict_node is not None:
            for k_node, v_node in zip(dict_node.keys, dict_node.values):
                if (
                    isinstance(k_node, ast.Constant)
                    and isinstance(k_node.value, str)
                    and isinstance(v_node, ast.Constant)
                    and isinstance(v_node.value, str)
                ):
                    extracted[k_node.value] = v_node.value
    return extracted


def _collect_ssot_imports_and_shadows(
    tree: ast.AST,
    forbidden_call_targets: tuple[str, ...],
) -> tuple[set[str], list[str]]:
    imported_names: set[str] = set()
    shadowed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == SSOT_MODULE_IMPORT:
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in forbidden_call_targets:
                    shadowed.append(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
            if isinstance(node.target, ast.Name) and node.target.id in forbidden_call_targets:
                shadowed.append(node.target.id)
    return imported_names, shadowed


def audit_prompt_validator_vocab_symmetry(repo_root: Path) -> list[str]:
    """Return deterministic violation messages (empty list == PASS)."""
    violations: list[str] = []
    ssot_path = repo_root / SSOT_REL_PATH
    if not ssot_path.is_file():
        return [f"[Vocab Symmetry] Missing canonical SSOT module: {SSOT_REL_PATH}"]

    try:
        ssot = _load_ssot_module(ssot_path)
    except Exception as exc:  # guardian: allow-broad-exception -- syntax/import failure reported as deterministic lint violation
        return [f"[Vocab Symmetry] Failed to import {SSOT_REL_PATH}: {exc}"]

    nouns: tuple[str, ...] = tuple(getattr(ssot, "HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS", ()))
    abs_re: re.Pattern[str] | None = getattr(ssot, "HEADLINE_EXECUTIVE_ABSTRACTION_RE", None)
    forbidden_plumbing = {
        str(x).strip().lower() for x in getattr(ssot, "HEADLINE_FORBIDDEN_PLUMBING_LABELS", ())
    }
    forbidden_cred = {
        str(x).strip().lower() for x in getattr(ssot, "COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS", ())
    }
    sanitize_fn = getattr(ssot, "sanitize_allocated_skill_concept_hint", None)

    if not nouns or abs_re is None:
        violations.append(
            f"[Vocab Symmetry] {SSOT_REL_PATH}: HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS or HEADLINE_EXECUTIVE_ABSTRACTION_RE missing."
        )
    else:
        for noun in nouns:
            if not abs_re.search(noun):
                violations.append(
                    f"[Vocab Symmetry] Headline prompt noun {noun!r} is NOT accepted by HEADLINE_EXECUTIVE_ABSTRACTION_RE."
                )
            if noun.strip().lower() in forbidden_plumbing:
                violations.append(
                    f"[Vocab Symmetry] Headline prompt noun {noun!r} collides with HEADLINE_FORBIDDEN_PLUMBING_LABELS."
                )

    headline_pa_path = repo_root / HEADLINE_PA_REL_PATH
    if headline_pa_path.is_file() and abs_re is not None:
        pa_tree = ast.parse(headline_pa_path.read_text(encoding="utf-8"), filename=HEADLINE_PA_REL_PATH)
        root_phrases = _extract_dict_str_values(pa_tree, "_ALLOCATION_ROOT_COMPACT_PHRASES")
        for root_id, phrase in sorted(root_phrases.items()):
            wc = len(phrase.split())
            if wc > 3:
                violations.append(
                    f"[Vocab Symmetry] {HEADLINE_PA_REL_PATH}: {root_id} phrase {phrase!r} exceeds 3-word compact cap ({wc} words)."
                )
            if not abs_re.search(phrase):
                violations.append(
                    f"[Vocab Symmetry] {HEADLINE_PA_REL_PATH}: {root_id} phrase {phrase!r} fails HEADLINE_EXECUTIVE_ABSTRACTION_RE."
                )
            if phrase.strip().lower() in forbidden_plumbing:
                violations.append(
                    f"[Vocab Symmetry] {HEADLINE_PA_REL_PATH}: {root_id} phrase {phrase!r} is in HEADLINE_FORBIDDEN_PLUMBING_LABELS."
                )

    ledger_path = repo_root / ARSENAL_LEDGER_REL_PATH
    if ledger_path.is_file() and callable(sanitize_fn):
        ledger_data: dict[str, Any] = json.loads(ledger_path.read_text(encoding="utf-8"))
        skill_ids: set[str] = set()
        for row in ledger_data.get("skill_rows") or []:
            if isinstance(row, dict) and str(row.get("skill_id") or "").strip():
                skill_ids.add(str(row["skill_id"]).strip())
        for node in ledger_data.get("graph_nodes") or []:
            if isinstance(node, dict):
                nid = str(node.get("node_id") or node.get("skill_id") or "").strip()
                if nid.startswith("skill"):
                    skill_ids.add(nid)
        for sid in sorted(skill_ids):
            hint = str(sanitize_fn(sid)).lower()
            hint_tokens = set(re.findall(r"[a-z0-9]+", hint))
            leaked = sorted(hint_tokens & forbidden_cred)
            if leaked:
                violations.append(
                    f"[Vocab Symmetry] Skill concept hint for {sid!r} -> {hint!r} leaks forbidden credential tokens {leaked}."
                )

    for rel_path, expected_symbols in sorted(MANDATORY_CONSUMER_IMPORTS.items()):
        c_path = repo_root / rel_path
        if not c_path.is_file():
            violations.append(f"[Vocab Symmetry] Missing expected consumer module: {rel_path}")
            continue
        c_tree = ast.parse(c_path.read_text(encoding="utf-8"), filename=rel_path)
        imported, shadows = _collect_ssot_imports_and_shadows(
            c_tree,
            FORBIDDEN_LOCAL_CALL_SHADOWS.get(rel_path, ()),
        )
        missing = [sym for sym in expected_symbols if sym not in imported]
        if missing:
            violations.append(
                f"[Vocab Symmetry] {rel_path} must import {missing} from {SSOT_MODULE_IMPORT}."
            )
        for sh in shadows:
            violations.append(
                f"[Vocab Symmetry] {rel_path} locally redefines {sh} via Call instead of binding {SSOT_MODULE_IMPORT}."
            )

    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit prompt-to-validator shared vocabulary symmetry across apps_rg."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    violations = audit_prompt_validator_vocab_symmetry(repo_root)
    report = {
        "policy_id": "INV-PROMPT-VALIDATOR-VOCAB-SYMMETRY",
        "status": "PASS" if not violations else "FAIL",
        "violation_count": len(violations),
        "violations": violations,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if violations:
            for v in violations:
                print(v, file=sys.stderr)
        else:
            print("[PASS] INV-PROMPT-VALIDATOR-VOCAB-SYMMETRY: 0 violations.")
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
