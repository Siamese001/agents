#!/usr/bin/env python3
"""Multi-Folder Configuration, Markdown, Prompt & Text Sprawl Scanner.

Scans all repository packages, declarative schemas, YAML profiles, Markdown (.md),
Jinja (.jinja/.j2), plain-text (.txt), CSV/JSONL, TOML/INI, and MCP configs to detect:
1. Shadow & duplicate configuration/targeting/rubric drift across directories (all extensions)
2. Intra-file semantic contradictions (JSON/YAML plus Markdown/text bound contradictions)
3. Twin versioned profile/prompt/briefing sprawl across .md, .txt, .jinja, .csv, .jsonl, .yaml, .json
4. Cross-format declarative & Markdown/Jinja bound and prompt body drift against canonical SSOT owners
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

KNOWN_DRIFT_ALLOWLIST: frozenset[str] = frozenset()

FULL_SEARCH_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".json",
        ".yaml",
        ".yml",
        ".md",
        ".mdc",
        ".txt",
        ".jinja",
        ".j2",
        ".csv",
        ".jsonl",
        ".toml",
        ".ini",
        ".sql",
    }
)

_JINJA_COMMENT_RE = re.compile(r"\{#[\s\S]*?#\}")
_MD_MIN_MAX_WORDS_RE = re.compile(
    r"\bbetween\s+(\d+)\s+and\s+(\d+)\s+(?:words|characters|sentences)\b",
    re.IGNORECASE,
)


def _strip_jinja_comments(text: str) -> str:
    return _JINJA_COMMENT_RE.sub("", text).strip()


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
    except (OSError, json.JSONDecodeError, ValueError, TypeError) if yaml is None else (OSError, json.JSONDecodeError, ValueError, TypeError, yaml.YAMLError):  # guardian: allow-silent-swallow -- skip malformed file in value loader
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
        ("config/certification/llm_judge_rubric.md", "resume_graph_engine/config/certification/llm_judge_rubric.md"),
        ("config/contracts/README.md", "resume_graph_engine/config/contracts/README.md"),
        ("config/runtime_trace/README.md", "resume_graph_engine/config/runtime_trace/README.md"),
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

    lic_targeting = repo_root / "outreach_engine" / "config" / "targeting"
    rg_targeting = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "config" / "targeting"
    if lic_targeting.is_dir() and rg_targeting.is_dir():
        lic_files = {
            p.relative_to(lic_targeting)
            for p in lic_targeting.rglob("*")
            if p.is_file() and p.suffix.lower() in FULL_SEARCH_EXTENSIONS and p.name != "README.md"
        }
        rg_files = {
            p.relative_to(rg_targeting)
            for p in rg_targeting.rglob("*")
            if p.is_file() and p.suffix.lower() in FULL_SEARCH_EXTENSIONS and p.name != "README.md"
        }
        for rel in sorted(lic_files & rg_files):
            rel_str = str(rel).replace("\\", "/")
            if not filecmp.cmp(lic_targeting / rel, rg_targeting / rel, shallow=False):
                findings.append(
                    {
                        "category": "SHADOW_TARGETING_DRIFT",
                        "canonical": f"resume_graph_engine/src/apps_rg/config/targeting/{rel_str}",
                        "shadow": f"outreach_engine/config/targeting/{rel_str}",
                        "detail": f"Shared targeting file '{rel_str}' diverges between outreach_engine and resume_graph_engine",
                    }
                )

    root_data = repo_root / "data"
    engine_data = repo_root / "resume_graph_engine" / "data"
    if root_data.is_dir() and engine_data.is_dir():
        r_data = {
            p.relative_to(root_data)
            for p in root_data.rglob("*")
            if p.is_file() and "cache" not in p.parts and p.suffix.lower() in FULL_SEARCH_EXTENSIONS
        }
        e_data = {
            p.relative_to(engine_data)
            for p in engine_data.rglob("*")
            if p.is_file() and "cache" not in p.parts and p.suffix.lower() in FULL_SEARCH_EXTENSIONS
        }
        for rel in sorted(r_data & e_data):
            rel_str = str(rel).replace("\\", "/")
            if rel_str in KNOWN_DRIFT_ALLOWLIST:
                continue
            if not filecmp.cmp(root_data / rel, engine_data / rel, shallow=False):
                findings.append(
                    {
                        "category": "SHADOW_DATA_DRIFT",
                        "canonical": f"data/{rel_str}",
                        "shadow": f"resume_graph_engine/data/{rel_str}",
                        "detail": f"Shadow data/markdown/csv file 'resume_graph_engine/data/{rel_str}' diverges from 'data/{rel_str}'",
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
    """Scan JSON/YAML schemas plus .md/.txt/.jinja templates and rules for internal bound contradictions."""
    findings: list[dict[str, Any]] = []
    candidate_dirs = (
        repo_root / "config",
        repo_root / "outreach_engine" / "config",
        repo_root / "outreach_engine" / "data",
        repo_root / "resume_graph_engine" / "config",
        repo_root / "resume_graph_engine" / "src" / "apps_rg",
        repo_root / "apps_research" / "config",
        repo_root / "apps_research" / "prompts",
        repo_root / "apps_eval",
        repo_root / ".agents" / "rules",
        repo_root / "automations" / "prompts",
    )

    for base in candidate_dirs:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            ext = path.suffix.lower()
            rel = str(path.relative_to(repo_root)).replace("\\", "/")

            if ext in (".md", ".txt", ".jinja", ".j2"):
                try:
                    raw_text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for m_range in _MD_MIN_MAX_WORDS_RE.finditer(raw_text):
                    lo_v, hi_v = int(m_range.group(1)), int(m_range.group(2))
                    if lo_v > hi_v:
                        findings.append(
                            {
                                "category": "INVERTED_BOUNDS",
                                "file": rel,
                                "key_a": "prose_min",
                                "val_a": lo_v,
                                "key_b": "prose_max",
                                "val_b": hi_v,
                                "detail": f"Inverted prose range '{m_range.group(0)}' in {rel}: {lo_v} > {hi_v}",
                            }
                        )
                continue

            if ext not in (".json", ".yaml", ".yml"):
                continue
            data = _load_structured(path)
            if not data:
                continue

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
    """Detect coexisting unversioned and versioned/variant twin files across YAML, JSON, MD, TXT, Jinja, CSV, JSONL."""
    findings: list[dict[str, Any]] = []
    scan_dirs = (
        repo_root / "apps_research" / "config",
        repo_root / "apps_research" / "prompts",
        repo_root / "outreach_engine" / "config",
        repo_root / "outreach_engine" / "data",
        repo_root / "resume_graph_engine" / "config",
        repo_root / "resume_graph_engine" / "src" / "apps_rg",
        repo_root / "config",
        repo_root / ".agents" / "rules",
        repo_root / "automations" / "prompts",
    )
    variant_exts = ("yaml", "yml", "json", "md", "txt", "jinja", "j2", "csv", "jsonl")
    ext_group = "|".join(variant_exts)
    variant_re = re.compile(
        rf"^([a-z0-9_\-]+?)(?:s)?(?:\.[a-z0-9_\-]+)?(?:\.|_)v\d+\.({ext_group})$",
        re.IGNORECASE,
    )

    for base in scan_dirs:
        if not base.is_dir():
            continue
        for dirpath in sorted({p.parent for p in base.rglob("*") if p.is_file()}):
            files_by_name = {p.name: p for p in dirpath.iterdir() if p.is_file()}
            for fname, fpath in sorted(files_by_name.items()):
                m = variant_re.match(fname)
                if not m:
                    continue
                stem, matched_ext = m.group(1), m.group(2).lower()
                candidate_exts = {matched_ext}
                if matched_ext in ("yaml", "yml", "json"):
                    candidate_exts.update({"yaml", "json"})
                elif matched_ext in ("md", "txt", "jinja", "j2"):
                    candidate_exts.update({"md", "txt", "jinja"})
                candidate_bases = sorted(
                    {
                        f"{base_stem}.{cext}"
                        for base_stem in (stem, f"{stem}s")
                        for cext in candidate_exts
                    }
                )
                for candidate_base in candidate_bases:
                    if candidate_base in files_by_name and candidate_base != fname:
                        base_path = files_by_name[candidate_base]
                        findings.append(
                            {
                                "category": "TWIN_PROFILE_SPRAWL",
                                "base_file": str(base_path.relative_to(repo_root)).replace("\\", "/"),
                                "variant_file": str(fpath.relative_to(repo_root)).replace("\\", "/"),
                                "detail": (
                                    f"Coexisting base file '{candidate_base}' and versioned twin '{fname}' "
                                    f"in '{dirpath.relative_to(repo_root)}'"
                                ),
                            }
                        )
    return findings


def scan_markdown_jinja_prompt_drift(repo_root: Path) -> list[dict[str, Any]]:
    """Verify .md prompt substrates and paired .jinja templates stay body-synchronized with zero drift."""
    findings: list[dict[str, Any]] = []
    md_prompts_dir = repo_root / "apps_research" / "config" / "prompts"
    jinja_templates_dir = repo_root / "apps_research" / "prompts" / "templates"
    if md_prompts_dir.is_dir() and jinja_templates_dir.is_dir():
        for md_path in sorted(md_prompts_dir.glob("*.md")):
            for j_ext in (".jinja", ".j2"):
                jinja_path = jinja_templates_dir / f"{md_path.stem}{j_ext}"
                if not jinja_path.is_file():
                    continue
                md_body = _strip_jinja_comments(md_path.read_text(encoding="utf-8", errors="replace"))
                j2_body = _strip_jinja_comments(jinja_path.read_text(encoding="utf-8", errors="replace"))
                if md_body != j2_body:
                    md_rel = str(md_path.relative_to(repo_root)).replace("\\", "/")
                    j2_rel = str(jinja_path.relative_to(repo_root)).replace("\\", "/")
                    findings.append(
                        {
                            "category": "MARKDOWN_JINJA_PROMPT_DRIFT",
                            "canonical": md_rel,
                            "shadow": j2_rel,
                            "detail": (
                                f"Paired Jinja template '{j2_rel}' diverges from canonical Markdown prompt '{md_rel}'"
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
    canon_exec_max_words = int(exec_owner.get("EXEC_SUMMARY_MAX_WORDS", 110))
    canon_exec_sent_words = int(exec_owner.get("EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE", 32))

    declarative_exec_checks = (
        ("resume_graph_engine/src/apps_rg/rg_style_profile.yaml", ("section_style", "summary", "max_words")),
        (
            "resume_graph_engine/src/apps_rg/rg_output_schema.json",
            ("definitions", "section_constraints", "properties", "summary", "max_words"),
        ),
        (
            "resume_graph_engine/src/apps_rg/prompt_assembly/section_contracts/executive_summary_contract.yaml",
            ("length", "paragraph_max_words"),
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
        for sec_key in ("length", "bounds"):
            sent_w = (contract_yaml.get(sec_key) or {}).get("max_words_per_sentence")
            if isinstance(sent_w, int) and sent_w != canon_exec_sent_words:
                findings.append(
                    {
                        "category": "CROSS_FORMAT_BOUND_DRIFT",
                        "file": "resume_graph_engine/src/apps_rg/prompt_assembly/section_contracts/executive_summary_contract.yaml",
                        "key": f"{sec_key}.max_words_per_sentence",
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
    """Run all multi-folder configuration, markdown, jinja, and cross-format drift scans."""
    root = repo_root.resolve()
    shadow = scan_shadow_config_drift(root)
    intra = scan_intra_file_contradictions(root)
    twins = scan_twin_profile_sprawl(root)
    md_jinja_drift = scan_markdown_jinja_prompt_drift(root)
    cross_format = scan_cross_format_bound_drift(root) + md_jinja_drift
    total = len(shadow) + len(intra) + len(twins) + len(cross_format)
    return {
        "status": "PASS" if total == 0 else "FAIL",
        "is_clean": total == 0,
        "total_findings": total,
        "extensions_searched": sorted(FULL_SEARCH_EXTENSIONS),
        "shadow_config_drift": shadow,
        "intra_file_contradictions": intra,
        "twin_profile_sprawl": twins,
        "markdown_jinja_prompt_drift": md_jinja_drift,
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
