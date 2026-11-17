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
    "MAX_PLAN_WORDS": ("config/governance/policy_registry.yaml", 0),
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
    "OUTREACH_MAX_CACHE_SIZE": (
        "outreach_engine/src/apps_lic/pipeline/briefing_resolver.py",
        128,
    ),
}

HOME_PATH_RE = re.compile(r"(?:/Users/[A-Za-z0-9_.\-]+|C:\\\\Users\\\\[A-Za-z0-9_.\-]+|C:\\\\Git\\\\)")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, AttributeError) if yaml is None else (OSError, ValueError, TypeError, yaml.YAMLError):  # guardian: allow-silent-swallow -- return empty dict on malformed YAML
        return {}


def _expand_owner_entries(raw: Any) -> set[str]:
    """Normalize string or list-of-strings owner/package entries to POSIX relative paths."""
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple, set)):
        items = [str(item) for item in raw if isinstance(item, str)]
    else:
        return set()
    return {item.strip().replace("\\", "/") for item in items if item.strip()}


def _matches_owner_or_package(rel: str, owners: Sequence[str] | set[str]) -> bool:
    """Match a relative path against exact file paths, trailing-slash prefixes, or split .py package dirs."""
    norm_rel = rel.replace("\\", "/")
    for owner in owners:
        norm_owner = owner.strip().replace("\\", "/")
        if not norm_owner:
            continue
        if norm_owner.endswith("/"):
            if norm_rel.startswith(norm_owner):
                return True
        elif norm_rel == norm_owner:
            return True
        elif norm_owner.endswith(".py") and (
            norm_rel.startswith(f"{norm_owner[:-3]}/") or norm_rel.startswith(f"{norm_owner[:-3]}_pkg/")
        ):
            return True
    return False


def _path_or_package_exists(repo_root: Path, rel_path: str) -> bool:
    """Return True when a declared module path exists as a file or a split Python package."""
    norm = rel_path.strip().replace("\\", "/")
    target = repo_root / norm
    if norm.endswith("/"):
        return target.is_dir()
    if target.is_file():
        return True
    if norm.endswith(".py"):
        for pkg_dir in (repo_root / norm[:-3], repo_root / f"{norm[:-3]}_pkg"):
            if pkg_dir.is_dir() and ((pkg_dir / "__init__.py").is_file() or any(pkg_dir.glob("*.py"))):
                return True
    return False


def _iter_target_py_files(repo_root: Path, *rel_paths: str) -> list[tuple[str, Path]]:
    """Expand file paths or package directories into deduplicated sorted (rel_path, Path) pairs."""
    seen: set[Path] = set()
    results: list[tuple[str, Path]] = []
    for raw_rel in rel_paths:
        norm = raw_rel.strip().replace("\\", "/")
        if not norm:
            continue
        candidates: list[Path] = []
        target = repo_root / norm
        if norm.endswith("/"):
            if target.is_dir():
                candidates.extend(sorted(target.rglob("*.py")))
        else:
            if target.is_file():
                candidates.append(target)
            if norm.endswith(".py"):
                for pkg_dir in (repo_root / norm[:-3], repo_root / f"{norm[:-3]}_pkg"):
                    if pkg_dir.is_dir():
                        candidates.extend(sorted(pkg_dir.rglob("*.py")))
        for py_path in candidates:
            if py_path not in seen and "tests" not in py_path.parts:
                seen.add(py_path)
                results.append((str(py_path.relative_to(repo_root)).replace("\\", "/"), py_path))
    return results


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

        if enforcer and not _path_or_package_exists(repo_root, enforcer):
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
            ev_targets = _iter_target_py_files(repo_root, "tools/implementation_plan_core/evidence_requirements.py")
            if ev_targets:
                texts = [(rel, p.read_text(encoding="utf-8", errors="replace")) for rel, p in ev_targets]
                has_registry_ref = any("policy_registry.yaml" in txt for _, txt in texts)
                if not has_registry_ref:
                    for ev_rel, ev_text in texts:
                        if re.search(r"^MAX_PLAN_WORDS\s*=\s*\d+", ev_text, re.M):
                            findings.append(
                                {
                                    "category": "POLICY_REGISTRY_BYPASS",
                                    "policy_id": pid,
                                    "file": ev_rel,
                                    "detail": (
                                        "evidence_requirements hardcodes MAX_PLAN_WORDS literal instead of "
                                        "resolving INV-WAVE-PLAN-MAX-WORDS from config/governance/policy_registry.yaml"
                                    ),
                                }
                            )

        if pid == "INV-OUTPUT-MAX-WORDS" and isinstance(threshold, int):
            hd_targets = _iter_target_py_files(repo_root, "tools/hook_dispatch.py")
            if hd_targets and not any("validate_word_budget_gate" in p.read_text(encoding="utf-8", errors="replace") for _, p in hd_targets):
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
            for md_rel in ("AGENTS.md", ".agents/rules/output-brevity-governance.md"):
                md_doc = repo_root / md_rel
                if md_doc.is_file():
                    md_txt = md_doc.read_text(encoding="utf-8", errors="replace")
                    m_ceil = re.search(r"Hard\s+Word\s+Ceiling[^\n]*?(\d{2,4})\s+words", md_txt, re.IGNORECASE)
                    if m_ceil and int(m_ceil.group(1)) != threshold:
                        findings.append(
                            {
                                "category": "MARKDOWN_POLICY_THRESHOLD_DRIFT",
                                "policy_id": pid,
                                "file": md_rel,
                                "observed": int(m_ceil.group(1)),
                                "canonical_value": threshold,
                                "detail": f"{md_rel} declares Hard Word Ceiling {m_ceil.group(1)} words != {pid} ({threshold})",
                            }
                        )

        if pid == "INV-WAVE-PLAN-MAX-WORDS" and isinstance(threshold, int) and threshold == 0:
            tpl_doc = repo_root / "docs" / "templates" / "wave_plan_template.md"
            if tpl_doc.is_file():
                tpl_txt = tpl_doc.read_text(encoding="utf-8", errors="replace")
                if re.search(r"hard\s+maximum\s+of\s+1,?000\s+words", tpl_txt, re.IGNORECASE):
                    findings.append(
                        {
                            "category": "MARKDOWN_POLICY_THRESHOLD_DRIFT",
                            "policy_id": pid,
                            "file": "docs/templates/wave_plan_template.md",
                            "detail": (
                                "docs/templates/wave_plan_template.md still states obsolete 'hard maximum of 1,000 words' "
                                "instead of unbounded INV-WAVE-PLAN-MAX-WORDS = 0"
                            ),
                        }
                    )

    return findings


_GLOBAL_AST_CACHE: dict[Path, tuple[int, str, ast.AST | None]] = {}


def _parse_cached(py: Path, ast_cache: dict[Path, ast.AST | None]) -> ast.AST | None:
    if py in ast_cache:
        return ast_cache[py]
    try:
        mtime_ns = py.stat().st_mtime_ns
    except OSError:
        mtime_ns = -1
    g_cached = _GLOBAL_AST_CACHE.get(py)
    if g_cached is not None and g_cached[0] == mtime_ns:
        ast_cache[py] = g_cached[2]
        return g_cached[2]
    raw_text = py.read_text(encoding="utf-8", errors="replace")
    try:
        tree: ast.AST | None = ast.parse(raw_text, filename=str(py))
    except SyntaxError:
        tree = None
    ast_cache[py] = tree
    if mtime_ns != -1:
        _GLOBAL_AST_CACHE[py] = (mtime_ns, raw_text, tree)
    return tree


DEFAULT_APPROVED_ENV_PATHS: tuple[str, ...] = (
    "infrastructure/", "config/", "tools/", "ops_scripts/", "scripts/",
    "agents/cli.py", "agents/live_preflight.py", "resume_engine/cli.py",
    "apps_model_telemetry/", "apps_eval/adapters/", "apps_eval/runner/",
    "resume_graph_engine/src/apps_rg/config/", "resume_graph_engine/tools/",
    "resume_graph_engine/src/apps_rg/runtime/env_bootstrap.py",
    "resume_graph_engine/src/apps_rg/runtime/embedding_settings.py",
    "resume_graph_engine/src/apps_rg/runtime/fact_vectors_bootstrap.py",
    "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_repair_policy.py",
)


def _load_guarded_thresholds(repo_root: Path) -> dict[str, tuple[set[str], int]]:
    """Load canonical threshold symbols and their owner files or packages from centralization_registry.yaml."""
    defaults: dict[str, tuple[set[str], int]] = {
        sym: ({owner_rel}, val) for sym, (owner_rel, val) in GUARDED_THRESHOLD_NAMES.items()
    }
    reg = _load_yaml(repo_root / "config" / "governance" / "centralization_registry.yaml")
    owners = reg.get("domain_threshold_owners", {})
    if not isinstance(owners, Mapping):
        return defaults
    for domain_cfg in owners.values():
        if not isinstance(domain_cfg, Mapping):
            continue
        allowed_owners: set[str] = set()
        for key in ("owner_file", "owner_package", "owner_packages", "Aggregator_ssot", "aggregator_package", "aggregator_packages"):
            allowed_owners |= _expand_owner_entries(domain_cfg.get(key))
        symbols = domain_cfg.get("canonical_symbols", {})
        if isinstance(symbols, Mapping) and allowed_owners:
            for sym_name, sym_val in symbols.items():
                sym_str = str(sym_name).strip()
                if not sym_str.startswith("INV-") and isinstance(sym_val, int):
                    defaults[sym_str] = (allowed_owners, sym_val)
    return defaults


def scan_hardcoded_threshold_literals(
    repo_root: Path,
    *,
    ast_cache: dict[Path, ast.AST | None] | None = None,
) -> list[dict[str, Any]]:
    """Detect magic word/sentence/length threshold literals defined outside their canonical owner."""
    cache = ast_cache if ast_cache is not None else {}
    findings: list[dict[str, Any]] = []
    guarded_map = _load_guarded_thresholds(repo_root)

    for rel_dir in list(PRODUCTION_SCAN_DIRS) + ["tools"]:
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
                        if isinstance(target, ast.Name) and target.id in guarded_map:
                            allowed_owners, canon_val = guarded_map[target.id]
                            owner_rel = sorted(allowed_owners)[0]
                            if not _matches_owner_or_package(rel, allowed_owners) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                                findings.append({
                                    "category": "DUPLICATE_CONSTANT_LITERAL", "file": rel, "line": node.lineno,
                                    "symbol": target.id, "observed": node.value.value,
                                    "canonical_owner": owner_rel, "canonical_value": canon_val,
                                    "detail": f"{rel}:{node.lineno} redefines {target.id}={node.value.value} outside canonical owner {owner_rel}",
                                })
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    field_name = node.target.id
                    if field_name in ("max_sentence_length", "max_words_per_sentence") and isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                        val = node.value.value
                        if "executive_summary" in rel and val != 45:
                            findings.append({
                                "category": "CONFLICTING_POLICY_DEFAULT", "file": rel, "line": node.lineno,
                                "symbol": field_name, "observed": val,
                                "canonical_owner": "EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE", "canonical_value": 45,
                                "detail": f"{rel}:{node.lineno} sets {field_name}={val} != EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE (45)",
                            })
                elif isinstance(node, ast.Dict):
                    for k_node, v_node in zip(node.keys, node.values):
                        if isinstance(k_node, ast.Constant) and k_node.value == "max_words" and isinstance(v_node, ast.Constant) and isinstance(v_node.value, int):
                            if _matches_owner_or_package(rel, ("apps_eval/scenarios.py",)) and v_node.value != 150:
                                findings.append({
                                    "category": "EVAL_SCENARIO_BOUND_DRIFT", "file": rel, "line": k_node.lineno,
                                    "symbol": "length_bounds.max_words", "observed": v_node.value,
                                    "canonical_owner": "EXEC_SUMMARY_MAX_WORDS", "canonical_value": 150,
                                    "detail": f"{rel}:{k_node.lineno} hardcodes apps_rg scenario max_words={v_node.value} != EXEC_SUMMARY_MAX_WORDS (150)",
                                })
    return findings


def scan_prompt_code_parity(repo_root: Path) -> list[dict[str, Any]]:
    """Detect prompt strings or templates whose numeric word bounds diverge from runtime validators."""
    findings: list[dict[str, Any]] = []
    repair_targets = _iter_target_py_files(
        repo_root,
        "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary/word_budget_repair.py",
        "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_lane.py",
    )
    for rel, fpath in repair_targets:
        for lineno, line in enumerate(fpath.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            m = re.search(r"\b(\d{2,3})\s*-\s*(\d{2,3})\s+words\b", line)
            if m and int(m.group(2)) != 150:
                findings.append({
                    "category": "PROMPT_VALIDATOR_BOUND_DRIFT", "file": rel, "line": lineno,
                    "observed_range": f"{m.group(1)}-{m.group(2)} words", "canonical_value": 150,
                    "detail": f"{rel}:{lineno} hardcodes repair target '{m.group(0)}' instead of referencing EXEC_SUMMARY_MAX_WORDS (150)",
                })

    brief_tpl = repo_root / "apps_research/prompt_assembly/templates/company_brief_synthesis_v1.yaml"
    spec_targets = _iter_target_py_files(repo_root, "apps_research/config/agent_spec_config.py")
    if brief_tpl.is_file() and spec_targets:
        tpl_text = brief_tpl.read_text(encoding="utf-8", errors="replace")
        m_light = re.search(r"LIGHT:.*?Max\s+(\d+)\s+words", tpl_text)
        m_brief = next(
            (m for _, sp in spec_targets if (m := re.search(r'mode_id="brief"[\s\S]{0,200}?max_words=(\d+)', sp.read_text(encoding="utf-8", errors="replace")))),
            None,
        )
        if m_brief and m_light and int(m_brief.group(1)) != int(m_light.group(1)):
            findings.append({
                "category": "TEMPLATE_CONFIG_BOUND_DRIFT",
                "file": "apps_research/prompt_assembly/templates/company_brief_synthesis_v1.yaml",
                "observed": int(m_light.group(1)), "canonical_value": int(m_brief.group(1)),
                "detail": f"company_brief_synthesis_v1.yaml specifies LIGHT Max {m_light.group(1)} words while agent_spec_config.py sets brief max_words={m_brief.group(1)}",
            })

    role_targets = _iter_target_py_files(
        repo_root,
        "resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py",
        "resume_graph_engine/src/apps_rg/runtime/sections/role_episode/",
    )
    if role_targets:
        combined_role_txt = "\n".join(p.read_text(encoding="utf-8", errors="replace") for _, p in role_targets)
        if "between 20 and {NARRATIVE_MAX_WORDS} words" in combined_role_txt and "min 15 words" in combined_role_txt:
            findings.append({
                "category": "PROMPT_VALIDATOR_MIN_WORD_DRIFT",
                "file": role_targets[0][0],
                "detail": "role_episode_lane.py prompts for 'between 20 and NARRATIVE_MAX_WORDS words' but validates against 8/10/15 minimum word thresholds",
            })

    # Scan .md, .txt, and .jinja consumer prompts and rubrics for placeholder/sentinel parity
    md_prompt_checks = (
        ("apps_research/config/prompts/apps_rg_targeting_brief_v1.md", "BLOCKED: COMPANY_NOT_IDENTIFIABLE"),
        ("apps_research/config/prompts/downstream_research_substrate_v1.md", "BLOCKED: COMPANY_NOT_IDENTIFIABLE"),
        ("apps_research/config/prompts/apps_lic_research_substrate_v1.md", "BLOCKED: COMPANY_NOT_IDENTIFIABLE"),
        ("apps_research/config/prompts/apps_exec_executive_brief_v1.md", "BLOCKED: COMPANY_NOT_IDENTIFIABLE"),
        ("apps_research/prompts/templates/downstream_research_substrate_v1.jinja", "BLOCKED: COMPANY_NOT_IDENTIFIABLE"),
        ("apps_research/prompts/templates/apps_lic_research_substrate_v1.jinja", "BLOCKED: COMPANY_NOT_IDENTIFIABLE"),
        ("apps_research/prompts/templates/apps_exec_executive_brief_v1.jinja", "BLOCKED: COMPANY_NOT_IDENTIFIABLE"),
    )
    for rel_md, req_token in md_prompt_checks:
        md_p = repo_root / rel_md
        if md_p.is_file():
            md_txt = md_p.read_text(encoding="utf-8", errors="replace")
            if req_token not in md_txt:
                findings.append(
                    {
                        "category": "MARKDOWN_PROMPT_SENTINEL_DRIFT",
                        "file": rel_md,
                        "detail": f"{rel_md} missing required fail-closed sentinel '{req_token}'",
                    }
                )
    return findings


def _load_env_lookup_ratchet(repo_root: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Load per-file and package-prefix ceiling ratchets for legacy os.environ/os.getenv lookups."""
    ratchet_path = repo_root / "config" / "governance" / "env_lookup_ratchet.json"
    if not ratchet_path.is_file():
        return {}, {}
    file_counts: dict[str, int] = {}
    pkg_counts: dict[str, int] = {}
    try:
        payload = json.loads(ratchet_path.read_text(encoding="utf-8"))
        for k, v in (payload.get("file_counts") or {}).items() if isinstance(payload.get("file_counts"), Mapping) else ():
            if isinstance(v, int):
                norm = str(k).strip().replace("\\", "/")
                if norm.endswith("/"):
                    pkg_counts[norm] = v
                else:
                    file_counts[norm] = v
        for k, v in (payload.get("package_counts") or {}).items() if isinstance(payload.get("package_counts"), Mapping) else ():
            if isinstance(v, int):
                norm = str(k).strip().replace("\\", "/")
                pkg_counts[norm if norm.endswith("/") else f"{norm}/"] = v
    except (OSError, ValueError, TypeError):
        return {}, {}
    return file_counts, pkg_counts


def _resolve_env_ratchet_bucket(rel: str, file_ratchet: Mapping[str, int], pkg_ratchet: Mapping[str, int]) -> tuple[str, int]:
    """Map a relative file path to its exact file, split-package, or prefix ratchet bucket."""
    if rel in file_ratchet:
        return f"file:{rel}", file_ratchet[rel]
    for owner_file, ceiling in sorted(file_ratchet.items()):
        if owner_file.endswith(".py") and (
            rel.startswith(f"{owner_file[:-3]}/") or rel.startswith(f"{owner_file[:-3]}_pkg/")
        ):
            return f"file:{owner_file}", ceiling
    matches = [(prefix, ceiling) for prefix, ceiling in pkg_ratchet.items() if rel.startswith(prefix)]
    if matches:
        prefix, ceiling = max(matches, key=lambda item: len(item[0]))
        return f"pkg:{prefix}", ceiling
    return f"unmatched:{rel}", 0


def _collect_docstring_node_ids(tree: ast.AST) -> set[int]:
    """Return AST node ids of module, class, and function docstring Constant nodes."""
    doc_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
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
    file_ratchet, pkg_ratchet = _load_env_lookup_ratchet(repo_root)
    approved_env_paths = _expand_owner_entries(reg.get("approved_env_loader_paths")) or set(DEFAULT_APPROVED_ENV_PATHS)
    env_buckets: dict[str, tuple[int, list[dict[str, Any]]]] = {}

    for rel_dir in list(PRODUCTION_SCAN_DIRS) + ["tools"]:
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

            g_entry = _GLOBAL_AST_CACHE.get(py)
            raw_text = g_entry[1] if g_entry is not None else py.read_text(encoding="utf-8", errors="replace")
            for lineno, line_txt in enumerate(raw_text.splitlines(), start=1):
                m_guard = re.search(r"#\s*guardian:\s*(.+)$", line_txt)
                if m_guard and "--" not in m_guard.group(1):
                    findings.append({
                        "category": "GUARDIAN_MISSING_RATIONALE", "file": rel, "line": lineno,
                        "detail": f"{rel}:{lineno} contains '# guardian:' comment without '-- <rationale>'",
                    })

            for node in ast.walk(tree):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "split":
                    findings.append({
                        "category": "UNASSIGNED_SPLIT_CALL_BUG", "file": rel, "line": node.lineno,
                        "detail": f"{rel}:{node.lineno} calls .split() as a bare expression without assigning result",
                    })
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    if node.value.id == "os" and node.attr in ("environ", "getenv") and not _matches_owner_or_package(rel, approved_env_paths):
                        file_env_hits.append({
                            "category": "UNCENTRALIZED_ENV_LOOKUP", "file": rel, "line": node.lineno,
                            "detail": f"{rel}:{node.lineno} accesses os.{node.attr} outside approved config loaders",
                        })
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids and HOME_PATH_RE.search(node.value):
                    findings.append({
                        "category": "HARDCODED_MACHINE_PATH", "file": rel, "line": node.lineno,
                        "detail": f"{rel}:{node.lineno} contains hardcoded machine path '{node.value[:60]}'",
                    })

            if file_env_hits:
                bucket_key, ceiling = _resolve_env_ratchet_bucket(rel, file_ratchet, pkg_ratchet)
                prev_ceiling, prev_hits = env_buckets.get(bucket_key, (ceiling, []))
                prev_hits.extend(file_env_hits)
                env_buckets[bucket_key] = (prev_ceiling, prev_hits)

    for _bucket_key, (ceiling, hits) in sorted(env_buckets.items()):
        hits.sort(key=lambda item: (item["file"], int(item["line"])))
        if len(hits) > ceiling:
            findings.extend(hits[ceiling:])

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
