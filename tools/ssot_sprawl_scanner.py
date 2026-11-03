#!/usr/bin/env python3
"""Multi-Folder Configuration Sprawl, Shadow-Copy & Cross-Format Drift Scanner.

Scans all 9 repository packages, declarative schemas, YAML profiles, MCP configs,
and pytest configurations to detect:
1. Shadow & duplicate configuration drift across directories (beyond root vs engine config/)
2. Intra-file semantic contradictions (e.g. conflicting summary word caps inside one schema)
3. Twin versioned profile sprawl (coexisting base and .v1/.company_brief.v1 profiles)
4. Cross-format declarative bound drift against canonical SSOT owners
"""

from __future__ import annotations

import argparse
import filecmp
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

KNOWN_DRIFT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "canonical_pipelines.yaml",
        "certification/schemas/apps_research_apps_rg_handoff.v2.schema.json",
        "certification/veto_policy_schema.json",
        "expected_wiring.yaml",
        "model_catalog.json",
        "routing_thresholds.yaml",
    }
)


def _load_structured(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        if path.suffix.lower() in (".yaml", ".yml") and yaml is not None:
            data = yaml.safe_load(text)
            return data if isinstance(data, dict) else None
    except Exception:  # guardian: allow-silent-swallow -- skip malformed file in value loader
        return None
    return None


def scan_shadow_config_drift(repo_root: Path) -> list[dict[str, Any]]:
    """Detect diverging duplicate or shadow configuration files across all repo roots."""
    findings: list[dict[str, Any]] = []
    root_cfg = repo_root / "config"
    engine_cfg = repo_root / "resume_graph_engine" / "config"

    if root_cfg.is_dir() and engine_cfg.is_dir():
        root_files = {p.relative_to(root_cfg) for p in root_cfg.rglob("*") if p.is_file()}
        engine_files = {p.relative_to(engine_cfg) for p in engine_cfg.rglob("*") if p.is_file()}
        for rel in sorted(root_files & engine_files):
            rel_str = str(rel).replace("\\", "/")
            if rel_str in KNOWN_DRIFT_ALLOWLIST:
                continue
            if not filecmp.cmp(root_cfg / rel, engine_cfg / rel, shallow=False):
                findings.append(
                    {
                        "category": "SHADOW_CONFIG_DRIFT",
                        "canonical": f"config/{rel_str}",
                        "shadow": f"resume_graph_engine/config/{rel_str}",
                        "detail": "Shadow config file diverges from canonical root config/",
                    }
                )

    explicit_pairs = (
        ("config/provider_profiles.yaml", "resume_graph_engine/src/apps_rg/config/provider_profiles.yaml"),
        ("config/model_catalog.json", "resume_graph_engine/src/apps_rg/config/model_catalog.json"),
    )
    for canon_rel, shadow_rel in explicit_pairs:
        c_path = repo_root / canon_rel
        s_path = repo_root / shadow_rel
        if c_path.is_file() and s_path.is_file():
            if not filecmp.cmp(c_path, s_path, shallow=False):
                findings.append(
                    {
                        "category": "SHADOW_CONFIG_DRIFT",
                        "canonical": canon_rel,
                        "shadow": shadow_rel,
                        "detail": f"Package shadow copy '{shadow_rel}' diverges from '{canon_rel}'",
                    }
                )

    root_pytest = repo_root / "pytest.ini"
    if root_pytest.is_file():
        r_txt = root_pytest.read_text(encoding="utf-8", errors="replace")
        r_to = re.search(r"--timeout=(\d+)", r_txt)
        nested_pytest_files = sorted(
            p
            for p in repo_root.glob("*/pytest.ini")
            if p.is_file() and p.parent.name not in (".git", ".venv", ".worktrees", "artifacts")
        )
        for sub_pytest in nested_pytest_files:
            rel_sub = str(sub_pytest.relative_to(repo_root)).replace("\\", "/")
            s_txt = sub_pytest.read_text(encoding="utf-8", errors="replace")
            s_to = re.search(r"--timeout=(\d+)", s_txt)
            if (r_to and not s_to) or (r_to and s_to and r_to.group(1) != s_to.group(1)):
                findings.append(
                    {
                        "category": "SHADOW_PYTEST_DRIFT",
                        "canonical": "pytest.ini",
                        "shadow": rel_sub,
                        "detail": f"Nested {rel_sub} timeout setting diverges from root pytest.ini",
                    }
                )

    mcp_root = _load_structured(repo_root / ".mcp.json")
    mcp_agents = _load_structured(repo_root / ".agents" / "mcp_config.json")
    if mcp_root is not None and mcp_agents is not None:
        r_srvs = set((mcp_root.get("mcpServers") or {}).keys())
        a_srvs = set((mcp_agents.get("mcpServers") or {}).keys())
        if r_srvs != a_srvs:
            findings.append(
                {
                    "category": "SHADOW_MCP_DRIFT",
                    "canonical": ".mcp.json",
                    "shadow": ".agents/mcp_config.json",
                    "detail": f"MCP server key mismatch: diff={sorted(r_srvs ^ a_srvs)}",
                }
            )

    return findings


def scan_intra_file_contradictions(repo_root: Path) -> list[dict[str, Any]]:
    """Scan declarative JSON/YAML schemas and profiles for internal bound contradictions."""
    findings: list[dict[str, Any]] = []
    candidate_dirs = (
        repo_root / "config",
        repo_root / "outreach_engine" / "config",
        repo_root / "outreach_engine" / "data",
        repo_root / "resume_graph_engine" / "config",
        repo_root / "resume_graph_engine" / "src" / "apps_rg",
        repo_root / "apps_research" / "config",
        repo_root / "apps_eval",
    )

    for base in candidate_dirs:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".json", ".yaml", ".yml"):
                continue
            data = _load_structured(path)
            if not data:
                continue
            rel = str(path.relative_to(repo_root)).replace("\\", "/")

            sec_summary_max = (
                data.get("properties", {})
                .get("sections", {})
                .get("properties", {})
                .get("summary", {})
                .get("properties", {})
                .get("word_count", {})
                .get("maximum")
            )
            def_summary_max = (
                data.get("definitions", {})
                .get("section_constraints", {})
                .get("properties", {})
                .get("summary", {})
                .get("max_words")
            )
            if (
                isinstance(sec_summary_max, int)
                and isinstance(def_summary_max, int)
                and sec_summary_max != def_summary_max
            ):
                findings.append(
                    {
                        "category": "INTRA_FILE_CONTRADICTION",
                        "file": rel,
                        "key_a": "properties.sections.properties.summary.properties.word_count.maximum",
                        "val_a": sec_summary_max,
                        "key_b": "definitions.section_constraints.properties.summary.max_words",
                        "val_b": def_summary_max,
                        "detail": (
                            f"Internal summary word limit contradiction in {rel}: "
                            f"{sec_summary_max} vs {def_summary_max}"
                        ),
                    }
                )

            def _check_inverted_bounds(node: Any, prefix: str = "") -> None:
                if isinstance(node, Mapping):
                    for min_k, max_k in (
                        ("min_words", "max_words"),
                        ("minimum", "maximum"),
                        ("minLength", "maxLength"),
                        ("minItems", "maxItems"),
                        ("min_lines", "max_lines"),
                    ):
                        lo = node.get(min_k)
                        hi = node.get(max_k)
                        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo > hi:
                            findings.append(
                                {
                                    "category": "INVERTED_BOUNDS",
                                    "file": rel,
                                    "key_a": f"{prefix}.{min_k}".lstrip("."),
                                    "val_a": lo,
                                    "key_b": f"{prefix}.{max_k}".lstrip("."),
                                    "val_b": hi,
                                    "detail": f"Inverted bounds in {rel} at '{prefix}': {min_k}={lo} > {max_k}={hi}",
                                }
                            )
                    for k, v in node.items():
                        _check_inverted_bounds(v, f"{prefix}.{k}" if prefix else str(k))
                elif isinstance(node, list):
                    for idx, item in enumerate(node):
                        _check_inverted_bounds(item, f"{prefix}[{idx}]")

            _check_inverted_bounds(data)

    return findings


def scan_twin_profile_sprawl(repo_root: Path) -> list[dict[str, Any]]:
    """Detect coexisting unversioned and versioned/variant twin configuration files."""
    findings: list[dict[str, Any]] = []
    scan_dirs = (
        repo_root / "apps_research" / "config",
        repo_root / "outreach_engine" / "config",
        repo_root / "outreach_engine" / "data",
        repo_root / "resume_graph_engine" / "config",
        repo_root / "resume_graph_engine" / "src" / "apps_rg",
        repo_root / "config",
    )
    variant_re = re.compile(r"^([a-z0-9_]+?)(?:s)?\.(?:[a-z0-9_]+\.)?v\d+\.(?:yaml|yml|json)$")

    for base in scan_dirs:
        if not base.is_dir():
            continue
        for dirpath in sorted({p.parent for p in base.rglob("*") if p.is_file()}):
            files_by_name = {p.name: p for p in dirpath.iterdir() if p.is_file()}
            for fname, fpath in sorted(files_by_name.items()):
                m = variant_re.match(fname)
                if not m:
                    continue
                stem = m.group(1)
                for candidate_base in (
                    f"{stem}.yaml",
                    f"{stem}s.yaml",
                    f"{stem}.json",
                    f"{stem}s.json",
                ):
                    if candidate_base in files_by_name and candidate_base != fname:
                        base_path = files_by_name[candidate_base]
                        findings.append(
                            {
                                "category": "TWIN_PROFILE_SPRAWL",
                                "base_file": str(base_path.relative_to(repo_root)).replace("\\", "/"),
                                "variant_file": str(fpath.relative_to(repo_root)).replace("\\", "/"),
                                "detail": (
                                    f"Coexisting base profile '{candidate_base}' and versioned twin '{fname}' "
                                    f"in '{dirpath.relative_to(repo_root)}'"
                                ),
                            }
                        )
    return findings


def scan_cross_format_bound_drift(repo_root: Path) -> list[dict[str, Any]]:
    """Verify declarative YAML/JSON bounds match canonical SSOT owner constants."""
    findings: list[dict[str, Any]] = []
    reg_path = repo_root / "config" / "governance" / "centralization_registry.yaml"
    reg = _load_structured(reg_path) or {}
    owners = reg.get("domain_threshold_owners", {})
    exec_owner = owners.get("resume_executive_summary_shape", {}).get("canonical_symbols", {})
    canon_exec_max_words = int(exec_owner.get("EXEC_SUMMARY_MAX_WORDS", 150))
    canon_exec_sent_words = int(exec_owner.get("EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE", 45))

    declarative_exec_checks = (
        ("resume_graph_engine/src/apps_rg/rg_style_profile.yaml", ("section_style", "summary", "max_words")),
        (
            "resume_graph_engine/src/apps_rg/rg_output_schema.json",
            ("definitions", "section_constraints", "properties", "summary", "max_words"),
        ),
        (
            "resume_graph_engine/src/apps_rg/prompt_assembly/section_contracts/executive_summary_contract.yaml",
            ("bounds", "paragraph_max_words"),
        ),
    )
    for rel_path, key_chain in declarative_exec_checks:
        fpath = repo_root / rel_path
        data = _load_structured(fpath)
        if not data:
            continue
        cur: Any = data
        for k in key_chain:
            cur = cur.get(k) if isinstance(cur, Mapping) else None
        if isinstance(cur, int) and cur != canon_exec_max_words:
            findings.append(
                {
                    "category": "CROSS_FORMAT_BOUND_DRIFT",
                    "file": rel_path,
                    "key": ".".join(key_chain),
                    "observed": cur,
                    "canonical": canon_exec_max_words,
                    "owner": "EXEC_SUMMARY_MAX_WORDS",
                    "detail": (
                        f"{rel_path}::{'.'.join(key_chain)} sets {cur} words != "
                        f"canonical EXEC_SUMMARY_MAX_WORDS ({canon_exec_max_words})"
                    ),
                }
            )

    tailor_v1 = repo_root / "resume_graph_engine/src/apps_rg/prompt_assembly/templates/strategic_tailor_v1.yaml"
    if tailor_v1.is_file():
        t1_text = tailor_v1.read_text(encoding="utf-8", errors="replace")
        m_w = re.search(r"summary:\s*\n(?:\s+[^\n]+\n)*?\s+max_words:\s*(\d+)", t1_text)
        if m_w and int(m_w.group(1)) != canon_exec_max_words:
            findings.append(
                {
                    "category": "CROSS_FORMAT_BOUND_DRIFT",
                    "file": "resume_graph_engine/src/apps_rg/prompt_assembly/templates/strategic_tailor_v1.yaml",
                    "key": "summary.max_words",
                    "observed": int(m_w.group(1)),
                    "canonical": canon_exec_max_words,
                    "owner": "EXEC_SUMMARY_MAX_WORDS",
                    "detail": (
                        f"strategic_tailor_v1.yaml sets summary.max_words={m_w.group(1)} != "
                        f"canonical EXEC_SUMMARY_MAX_WORDS ({canon_exec_max_words})"
                    ),
                }
            )

    contract_yaml = _load_structured(
        repo_root / "resume_graph_engine/src/apps_rg/prompt_assembly/section_contracts/executive_summary_contract.yaml"
    )
    if contract_yaml:
        sent_w = (contract_yaml.get("bounds") or {}).get("max_words_per_sentence")
        if isinstance(sent_w, int) and sent_w != canon_exec_sent_words:
            findings.append(
                {
                    "category": "CROSS_FORMAT_BOUND_DRIFT",
                    "file": "resume_graph_engine/src/apps_rg/prompt_assembly/section_contracts/executive_summary_contract.yaml",
                    "key": "bounds.max_words_per_sentence",
                    "observed": sent_w,
                    "canonical": canon_exec_sent_words,
                    "owner": "EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE",
                    "detail": (
                        f"executive_summary_contract.yaml sets max_words_per_sentence={sent_w} != "
                        f"canonical {canon_exec_sent_words}"
                    ),
                }
            )

    return findings


def run_sprawl_scan(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Run all 4 multi-folder configuration sprawl and cross-format drift scans."""
    root = repo_root.resolve()
    shadow = scan_shadow_config_drift(root)
    intra = scan_intra_file_contradictions(root)
    twins = scan_twin_profile_sprawl(root)
    cross_format = scan_cross_format_bound_drift(root)
    total = len(shadow) + len(intra) + len(twins) + len(cross_format)
    return {
        "status": "PASS" if total == 0 else "FAIL",
        "is_clean": total == 0,
        "total_findings": total,
        "shadow_config_drift": shadow,
        "intra_file_contradictions": intra,
        "twin_profile_sprawl": twins,
        "cross_format_bound_drift": cross_format,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-Folder Configuration Sprawl & Drift Scanner.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root path")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--advisory", action="store_true", help="Return exit code 0 even when findings exist")
    args = parser.parse_args(argv)

    report = run_sprawl_scan(args.repo_root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[{report['status']}] Configuration Sprawl Scan: total_findings={report['total_findings']} "
            f"(shadow={len(report['shadow_config_drift'])}, intra={len(report['intra_file_contradictions'])}, "
            f"twins={len(report['twin_profile_sprawl'])}, cross_format={len(report['cross_format_bound_drift'])})"
        )
    return 0 if (report["is_clean"] or args.advisory) else 1


if __name__ == "__main__":
    sys.exit(main())
