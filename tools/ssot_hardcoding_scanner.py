#!/usr/bin/env python3
"""AST, Prompt, Rule & Evaluation Anti-Hardcoding and Parity Scanner.

Scans all 9 repository packages, governance tools, prompt templates, markdown rules,
and evaluation fixtures to detect:
1. Policy Registry bypasses and enforcer/hook desynchronization
2. Unowned hardcoded threshold literals (word/char/sentence/plan caps outside SSOT owners)
3. Prompt-to-code and template-to-config numeric bound mismatches
4. Uncentralized os.environ lookups, hardcoded absolute paths, and unassigned .split() bugs
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv

bootstrap_shared_venv(REPO_ROOT)

try:
    import yaml
except ImportError:  # guardian: allow-silent-swallow -- fallback if PyYAML unavailable
    yaml = None  # type: ignore

PRODUCTION_SCAN_DIRS: tuple[str, ...] = (
    "agents",
    "apps_model_telemetry",
    "outreach_engine",
    "resume_engine",
    "resume_graph_engine",
    "apps_research",
    "apps_eval",
    "infrastructure",
    "ops_scripts",
    "scripts",
)

GUARDED_THRESHOLD_NAMES: dict[str, tuple[str, int]] = {
    "MAX_PLAN_WORDS": ("config/governance/policy_registry.yaml", 1000),
    "EXEC_SUMMARY_MAX_WORDS": (
        "resume_graph_engine/src/apps_rg/runtime/validators/executive_summary_x2.py",
        150,
    ),
    "EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE": (
        "resume_graph_engine/src/apps_rg/runtime/validators/executive_summary_x2.py",
        45,
    ),
    "NARRATIVE_MAX_WORDS": (
        "resume_graph_engine/src/apps_rg/runtime/sections/section_product_shape_ssot.py",
        58,
    ),
}

HOME_PATH_RE = re.compile(r"(?:/Users/[A-Za-z0-9_.\-]+|C:\\\\Users\\\\[A-Za-z0-9_.\-]+|C:\\\\Git\\\\)")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:  # guardian: allow-silent-swallow -- return empty dict on malformed YAML
        return {}


def scan_policy_registry_sync(repo_root: Path) -> list[dict[str, Any]]:
    """Verify policy_registry.yaml enforcers and rules dynamically load or match registered thresholds."""
    findings: list[dict[str, Any]] = []
    pol_path = repo_root / "config" / "governance" / "policy_registry.yaml"
    pol_data = _load_yaml(pol_path)
    policies = pol_data.get("policies", [])
    if not isinstance(policies, list):
        return findings

    for pol in policies:
        if not isinstance(pol, Mapping):
            continue
        pid = str(pol.get("id", ""))
        enforcer = str(pol.get("enforcer", ""))
        rule_ref = str(pol.get("rule_reference", ""))
        threshold = pol.get("threshold")

        if enforcer and not (repo_root / enforcer).is_file():
            findings.append(
                {
                    "category": "MISSING_POLICY_ENFORCER",
                    "policy_id": pid,
                    "file": enforcer,
                    "detail": f"Policy {pid} references missing enforcer '{enforcer}'",
                }
            )
        if rule_ref and not (repo_root / rule_ref).is_file():
            findings.append(
                {
                    "category": "MISSING_POLICY_RULE_REF",
                    "policy_id": pid,
                    "file": rule_ref,
                    "detail": f"Policy {pid} references missing rule document '{rule_ref}'",
                }
            )

        if pid == "INV-WAVE-PLAN-MAX-WORDS":
            ev_path = repo_root / "tools" / "implementation_plan_core" / "evidence_requirements.py"
            if ev_path.is_file():
                ev_text = ev_path.read_text(encoding="utf-8", errors="replace")
                if "policy_registry.yaml" not in ev_text and re.search(r"^MAX_PLAN_WORDS\s*=\s*\d+", ev_text, re.M):
                    findings.append(
                        {
                            "category": "POLICY_REGISTRY_BYPASS",
                            "policy_id": pid,
                            "file": "tools/implementation_plan_core/evidence_requirements.py",
                            "detail": (
                                "evidence_requirements.py hardcodes MAX_PLAN_WORDS literal instead of "
                                "resolving INV-WAVE-PLAN-MAX-WORDS from config/governance/policy_registry.yaml"
                            ),
                        }
                    )

        if pid == "INV-OUTPUT-MAX-WORDS" and isinstance(threshold, int):
            hd_path = repo_root / "tools" / "hook_dispatch.py"
            if hd_path.is_file():
                hd_text = hd_path.read_text(encoding="utf-8", errors="replace")
                if "validate_word_budget_gate" not in hd_text:
                    findings.append(
                        {
                            "category": "UNWIRED_LIVE_HOOK_GATE",
                            "policy_id": pid,
                            "file": "tools/hook_dispatch.py",
                            "detail": (
                                "hook_dispatch.py handle_post_invocation does not invoke "
                                "validate_word_budget_gate to enforce INV-OUTPUT-MAX-WORDS during live turns"
                            ),
                        }
                    )

    return findings


def _parse_cached(py: Path, ast_cache: dict[Path, ast.AST | None]) -> ast.AST | None:
    if py in ast_cache:
        return ast_cache[py]
    try:
        tree: ast.AST | None = ast.parse(py.read_text(encoding="utf-8", errors="replace"), filename=str(py))
    except SyntaxError:
        tree = None
    ast_cache[py] = tree
    return tree


def scan_hardcoded_threshold_literals(
    repo_root: Path,
    *,
    ast_cache: dict[Path, ast.AST | None] | None = None,
) -> list[dict[str, Any]]:
    """Detect magic word/sentence/length threshold literals defined outside their canonical owner."""
    cache = ast_cache if ast_cache is not None else {}
    findings: list[dict[str, Any]] = []
    scan_targets = list(PRODUCTION_SCAN_DIRS) + ["tools"]

    for rel_dir in scan_targets:
        base = repo_root / rel_dir
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            if "tests" in py.parts:
                continue
            rel = str(py.relative_to(repo_root)).replace("\\", "/")
            tree = _parse_cached(py, cache)
            if tree is None:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in GUARDED_THRESHOLD_NAMES:
                            owner_rel, canon_val = GUARDED_THRESHOLD_NAMES[target.id]
                            if rel != owner_rel and isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                                findings.append(
                                    {
                                        "category": "DUPLICATE_CONSTANT_LITERAL",
                                        "file": rel,
                                        "line": node.lineno,
                                        "symbol": target.id,
                                        "observed": node.value.value,
                                        "canonical_owner": owner_rel,
                                        "canonical_value": canon_val,
                                        "detail": (
                                            f"{rel}:{node.lineno} redefines {target.id}={node.value.value} "
                                            f"outside canonical owner {owner_rel}"
                                        ),
                                    }
                                )

                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    field_name = node.target.id
                    if (
                        field_name in ("max_sentence_length", "max_words_per_sentence")
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, int)
                    ):
                        val = node.value.value
                        if "executive_summary" in rel and val != 45:
                            findings.append(
                                {
                                    "category": "CONFLICTING_POLICY_DEFAULT",
                                    "file": rel,
                                    "line": node.lineno,
                                    "symbol": field_name,
                                    "observed": val,
                                    "canonical_owner": "EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE",
                                    "canonical_value": 45,
                                    "detail": (
                                        f"{rel}:{node.lineno} sets {field_name}={val} != "
                                        "EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE (45)"
                                    ),
                                }
                            )

                elif isinstance(node, ast.Dict):
                    for k_node, v_node in zip(node.keys, node.values):
                        if (
                            isinstance(k_node, ast.Constant)
                            and k_node.value == "max_words"
                            and isinstance(v_node, ast.Constant)
                            and isinstance(v_node.value, int)
                        ):
                            val = v_node.value
                            if rel == "apps_eval/scenarios.py" and val != 150:
                                findings.append(
                                    {
                                        "category": "EVAL_SCENARIO_BOUND_DRIFT",
                                        "file": rel,
                                        "line": k_node.lineno,
                                        "symbol": "length_bounds.max_words",
                                        "observed": val,
                                        "canonical_owner": "EXEC_SUMMARY_MAX_WORDS",
                                        "canonical_value": 150,
                                        "detail": (
                                            f"{rel}:{k_node.lineno} hardcodes apps_rg scenario max_words={val} "
                                            "!= EXEC_SUMMARY_MAX_WORDS (150)"
                                        ),
                                    }
                                )

    return findings


def scan_prompt_code_parity(repo_root: Path) -> list[dict[str, Any]]:
    """Detect prompt strings or templates whose numeric word bounds diverge from runtime validators."""
    findings: list[dict[str, Any]] = []

    repair_files = (
        "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary/word_budget_repair.py",
        "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_lane.py",
    )
    for rel in repair_files:
        fpath = repo_root / rel
        if not fpath.is_file():
            continue
        for lineno, line in enumerate(fpath.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            m = re.search(r"\b(\d{2,3})\s*-\s*(\d{2,3})\s+words\b", line)
            if m:
                hi = int(m.group(2))
                if hi != 150:
                    findings.append(
                        {
                            "category": "PROMPT_VALIDATOR_BOUND_DRIFT",
                            "file": rel,
                            "line": lineno,
                            "observed_range": f"{m.group(1)}-{m.group(2)} words",
                            "canonical_value": 150,
                            "detail": (
                                f"{rel}:{lineno} hardcodes repair target '{m.group(0)}' instead of "
                                "referencing EXEC_SUMMARY_MAX_WORDS (150)"
                            ),
                        }
                    )

    brief_tpl = repo_root / "apps_research/prompt_assembly/templates/company_brief_synthesis_v1.yaml"
    spec_cfg = repo_root / "apps_research/config/agent_spec_config.py"
    if brief_tpl.is_file() and spec_cfg.is_file():
        tpl_text = brief_tpl.read_text(encoding="utf-8", errors="replace")
        spec_text = spec_cfg.read_text(encoding="utf-8", errors="replace")
        m_brief = re.search(r'mode_id="brief"[\s\S]{0,200}?max_words=(\d+)', spec_text)
        m_light = re.search(r"LIGHT:.*?Max\s+(\d+)\s+words", tpl_text)
        if m_brief and m_light and int(m_brief.group(1)) != int(m_light.group(1)):
            findings.append(
                {
                    "category": "TEMPLATE_CONFIG_BOUND_DRIFT",
                    "file": "apps_research/prompt_assembly/templates/company_brief_synthesis_v1.yaml",
                    "observed": int(m_light.group(1)),
                    "canonical_value": int(m_brief.group(1)),
                    "detail": (
                        f"company_brief_synthesis_v1.yaml specifies LIGHT Max {m_light.group(1)} words "
                        f"while agent_spec_config.py sets brief max_words={m_brief.group(1)}"
                    ),
                }
            )

    role_lane = repo_root / "resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py"
    if role_lane.is_file():
        rl_text = role_lane.read_text(encoding="utf-8", errors="replace")
        if "between 20 and {NARRATIVE_MAX_WORDS} words" in rl_text and "min 15 words" in rl_text:
            findings.append(
                {
                    "category": "PROMPT_VALIDATOR_MIN_WORD_DRIFT",
                    "file": "resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py",
                    "detail": (
                        "role_episode_lane.py prompts for 'between 20 and NARRATIVE_MAX_WORDS words' "
                        "but validates against 8/10/15 minimum word thresholds"
                    ),
                }
            )

    return findings


def _load_env_lookup_ratchet(repo_root: Path) -> dict[str, int]:
    """Load optional per-file ceiling ratchet for legacy os.environ/os.getenv lookups."""
    ratchet_path = repo_root / "config" / "governance" / "env_lookup_ratchet.json"
    if not ratchet_path.is_file():
        return {}
    try:
        payload = json.loads(ratchet_path.read_text(encoding="utf-8"))
        counts = payload.get("file_counts", {})
        if isinstance(counts, Mapping):
            return {str(k): int(v) for k, v in counts.items() if isinstance(v, int)}
    except (OSError, ValueError, TypeError):
        return {}
    return {}


def _collect_docstring_node_ids(tree: ast.AST) -> set[int]:
    """Return AST node ids of module, class, and function docstring Constant nodes."""
    doc_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                doc_ids.add(id(node.body[0].value))
    return doc_ids


def scan_ast_hygiene_and_env_sprawl(
    repo_root: Path,
    *,
    ast_cache: dict[Path, ast.AST | None] | None = None,
) -> list[dict[str, Any]]:
    """Detect unassigned .split() bugs, hardcoded user paths, and uncentralized os.environ reads."""
    cache = ast_cache if ast_cache is not None else {}
    findings: list[dict[str, Any]] = []
    reg = _load_yaml(repo_root / "config" / "governance" / "centralization_registry.yaml")
    env_ratchet = _load_env_lookup_ratchet(repo_root)
    approved_env_prefixes = tuple(
        reg.get(
            "approved_env_loader_paths",
            [
                "infrastructure/",
                "config/",
                "tools/",
                "ops_scripts/",
                "scripts/",
                "agents/cli.py",
                "agents/live_preflight.py",
                "resume_engine/cli.py",
                "apps_model_telemetry/",
                "apps_eval/adapters/",
                "apps_eval/runner/",
                "resume_graph_engine/src/apps_rg/config/",
                "resume_graph_engine/src/apps_rg/runtime/env_bootstrap.py",
                "resume_graph_engine/src/apps_rg/runtime/embedding_settings.py",
                "resume_graph_engine/src/apps_rg/runtime/fact_vectors_bootstrap.py",
                "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_repair_policy.py",
                "resume_graph_engine/tools/",
            ],
        )
    )

    scan_targets = list(PRODUCTION_SCAN_DIRS) + ["tools"]
    for rel_dir in scan_targets:
        base = repo_root / rel_dir
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            if "tests" in py.parts or py.name.startswith("test_") or py.name.endswith("_test.py"):
                continue
            rel = str(py.relative_to(repo_root)).replace("\\", "/")
            tree = _parse_cached(py, cache)
            if tree is None:
                continue

            doc_ids = _collect_docstring_node_ids(tree)
            file_env_hits: list[dict[str, Any]] = []

            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "split"
                ):
                    findings.append(
                        {
                            "category": "UNASSIGNED_SPLIT_CALL_BUG",
                            "file": rel,
                            "line": node.lineno,
                            "detail": f"{rel}:{node.lineno} calls .split() as a bare expression without assigning result",
                        }
                    )

                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    is_env = (node.value.id == "os" and node.attr in ("environ", "getenv"))
                    if is_env and not rel.startswith(approved_env_prefixes):
                        file_env_hits.append(
                            {
                                "category": "UNCENTRALIZED_ENV_LOOKUP",
                                "file": rel,
                                "line": node.lineno,
                                "detail": f"{rel}:{node.lineno} accesses os.{node.attr} outside approved config loaders",
                            }
                        )

                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
                    if HOME_PATH_RE.search(node.value):
                        findings.append(
                            {
                                "category": "HARDCODED_MACHINE_PATH",
                                "file": rel,
                                "line": node.lineno,
                                "detail": f"{rel}:{node.lineno} contains hardcoded machine path '{node.value[:60]}'",
                            }
                        )

            ratchet_ceiling = env_ratchet.get(rel, 0)
            if len(file_env_hits) > ratchet_ceiling:
                findings.extend(file_env_hits[ratchet_ceiling:])

    return findings


def run_hardcoding_scan(
    repo_root: Path = REPO_ROOT,
    *,
    ast_cache: dict[Path, ast.AST | None] | None = None,
) -> dict[str, Any]:
    """Execute all 4 anti-hardcoding, policy sync, prompt parity, and AST hygiene scans."""
    root = repo_root.resolve()
    shared_cache = ast_cache if ast_cache is not None else {}
    pol_sync = scan_policy_registry_sync(root)
    literals = scan_hardcoded_threshold_literals(root, ast_cache=shared_cache)
    parity = scan_prompt_code_parity(root)
    hygiene = scan_ast_hygiene_and_env_sprawl(root, ast_cache=shared_cache)
    total = len(pol_sync) + len(literals) + len(parity) + len(hygiene)
    return {
        "status": "PASS" if total == 0 else "FAIL",
        "is_clean": total == 0,
        "total_findings": total,
        "policy_registry_sync_issues": pol_sync,
        "hardcoded_threshold_literals": literals,
        "prompt_code_parity_issues": parity,
        "ast_hygiene_and_env_sprawl": hygiene,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AST, Prompt, Rule & Evaluation Anti-Hardcoding Scanner.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root path")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--advisory", action="store_true", help="Return exit code 0 even when findings exist")
    args = parser.parse_args(argv)

    report = run_hardcoding_scan(args.repo_root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[{report['status']}] Anti-Hardcoding Scan: total_findings={report['total_findings']} "
            f"(policy_sync={len(report['policy_registry_sync_issues'])}, "
            f"literals={len(report['hardcoded_threshold_literals'])}, "
            f"parity={len(report['prompt_code_parity_issues'])}, "
            f"hygiene={len(report['ast_hygiene_and_env_sprawl'])})"
        )
    return 0 if (report["is_clean"] or args.advisory) else 1


if __name__ == "__main__":
    sys.exit(main())
