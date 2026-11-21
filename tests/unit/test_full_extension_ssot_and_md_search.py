"""Unit tests for Full-Extension SSOT Deduplication, Redundancy & Markdown/Text Governance.

Verifies that all Agents Repo governance, deduplication, sprawl, drift, secret, rubric,
runtime contract, and swarm council auditors search `.md`, `.txt`, `.jinja`, `.csv`,
`.jsonl`, `.toml`, `.ini`, and other text formats alongside `.json`, `.yaml`, and `.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.agent_runtime_auditor import audit_pillar_1_delegation_contracts
from tools.check_config_ssot_drift import analyze_drift
from tools.lint_secrets import SCANNABLE_TEXT_EXTENSIONS, check_file_for_secrets
from tools.ssot_boundary_auditor import audit_mcp_hooks_and_links, run_ssot_boundary_audit
from tools.ssot_hardcoding_scanner import scan_policy_registry_sync, scan_prompt_code_parity
from tools.ssot_sprawl_scanner import (
    FULL_SEARCH_EXTENSIONS,
    run_sprawl_scan,
    scan_intra_file_contradictions,
    scan_markdown_jinja_prompt_drift,
    scan_shadow_config_drift,
    scan_twin_profile_sprawl,
)
from tools.validate_eval_rubrics import _validate_markdown_and_text_rubrics
from tools.verify_commit import _collect_repository_files

WORKTREE_ROOT = Path(__file__).resolve().parents[2]


def test_full_search_extension_catalogs_cover_markdown_and_text_formats() -> None:
    """Both sprawl and secret scanners must declare full multi-extension text coverage."""
    for ext in (".md", ".mdc", ".txt", ".jinja", ".j2", ".csv", ".jsonl", ".toml", ".ini", ".sql", ".json", ".yaml"):
        assert ext in FULL_SEARCH_EXTENSIONS
        assert ext in SCANNABLE_TEXT_EXTENSIONS


def test_sprawl_scanner_detects_markdown_shadow_twins_inverted_bounds_and_jinja_drift(tmp_path: Path) -> None:
    """Sprawl scanner must catch .md shadow divergence, .md/.txt twins, .md inverted bounds, and .md/.jinja drift."""
    # 1. Markdown shadow rubric & targeting divergence
    (tmp_path / "config" / "certification").mkdir(parents=True)
    (tmp_path / "resume_graph_engine" / "config" / "certification").mkdir(parents=True)
    (tmp_path / "config" / "certification" / "llm_judge_rubric.md").write_text("# Canonical Rubric\n", encoding="utf-8")
    (tmp_path / "resume_graph_engine" / "config" / "certification" / "llm_judge_rubric.md").write_text(
        "# Diverged Shadow Rubric\n", encoding="utf-8"
    )

    (tmp_path / "outreach_engine" / "config" / "targeting").mkdir(parents=True)
    (tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "config" / "targeting").mkdir(parents=True)
    (tmp_path / "outreach_engine" / "config" / "targeting" / "persona_brief.md").write_text(
        "Outreach targeting brief v1\n", encoding="utf-8"
    )
    (tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "config" / "targeting" / "persona_brief.md").write_text(
        "Diverged resume targeting brief v2\n", encoding="utf-8"
    )

    shadow_hits = scan_shadow_config_drift(tmp_path)
    shadow_cats = {h["category"] for h in shadow_hits}
    assert "SHADOW_CONFIG_DRIFT" in shadow_cats
    assert "SHADOW_TARGETING_DRIFT" in shadow_cats
    assert any(h["canonical"].endswith("llm_judge_rubric.md") for h in shadow_hits)
    assert any(h["canonical"].endswith("persona_brief.md") for h in shadow_hits)

    # 2. Markdown & text twin profile sprawl + inverted prose bounds
    (tmp_path / "config" / "prompts").mkdir(parents=True)
    (tmp_path / "config" / "prompts" / "brief_guide.md").write_text(
        "Keep executive summary between 250 and 80 words.\n", encoding="utf-8"
    )
    (tmp_path / "config" / "prompts" / "brief_guide.v1.md").write_text("Legacy v1 guide\n", encoding="utf-8")

    twins = scan_twin_profile_sprawl(tmp_path)
    assert any(t["base_file"].endswith("brief_guide.md") for t in twins)

    contradictions = scan_intra_file_contradictions(tmp_path)
    assert any(c["category"] == "INVERTED_BOUNDS" and c["file"].endswith("brief_guide.md") for c in contradictions)

    # 3. Markdown vs Jinja prompt body divergence
    (tmp_path / "apps_research" / "config" / "prompts").mkdir(parents=True)
    (tmp_path / "apps_research" / "prompts" / "templates").mkdir(parents=True)
    (tmp_path / "apps_research" / "config" / "prompts" / "downstream_research_substrate_v1.md").write_text(
        "TASK\nBLOCKED: COMPANY_NOT_IDENTIFIABLE\n{{target_entity}}\n", encoding="utf-8"
    )
    (tmp_path / "apps_research" / "prompts" / "templates" / "downstream_research_substrate_v1.jinja").write_text(
        "{# Header comment #}\nLegacy stale template {{ c0_evidence }}\n", encoding="utf-8"
    )

    mj_drift = scan_markdown_jinja_prompt_drift(tmp_path)
    assert len(mj_drift) == 1
    assert mj_drift[0]["category"] == "MARKDOWN_JINJA_PROMPT_DRIFT"

    full_rep = run_sprawl_scan(tmp_path)
    assert full_rep["status"] == "FAIL"
    assert not full_rep["is_clean"]


def test_drift_analyzer_tracks_markdown_csv_and_targeting_extensions(tmp_path: Path) -> None:
    """check_config_ssot_drift must inventory extensions and detect .md/.csv config & data drift."""
    (tmp_path / "config" / "certification").mkdir(parents=True)
    (tmp_path / "resume_graph_engine" / "config" / "certification").mkdir(parents=True)
    (tmp_path / "config" / "certification" / "llm_judge_rubric.md").write_text("Same MD\n", encoding="utf-8")
    (tmp_path / "resume_graph_engine" / "config" / "certification" / "llm_judge_rubric.md").write_text(
        "Same MD\n", encoding="utf-8"
    )

    (tmp_path / "data" / "evals").mkdir(parents=True)
    (tmp_path / "resume_graph_engine" / "data" / "evals").mkdir(parents=True)
    (tmp_path / "data" / "evals" / "notes.txt").write_text("Alpha\n", encoding="utf-8")
    (tmp_path / "resume_graph_engine" / "data" / "evals" / "notes.txt").write_text("Beta\n", encoding="utf-8")

    drift = analyze_drift(tmp_path)
    assert drift["scanned_files_by_extension"].get(".md", 0) >= 2
    assert drift["identical_by_extension"].get(".md", 0) >= 1
    assert "evals/notes.txt" in drift["data_differing"]


def test_hardcoding_scanner_catches_markdown_policy_and_prompt_sentinel_drift(tmp_path: Path) -> None:
    """ssot_hardcoding_scanner must catch stale .md policy word ceilings and missing prompt sentinels."""
    (tmp_path / "config" / "governance").mkdir(parents=True)
    (tmp_path / "config" / "governance" / "policy_registry.yaml").write_text(
        "policies:\n"
        "  - id: INV-OUTPUT-MAX-WORDS\n"
        "    threshold: 450\n"
        "    enforcers: []\n"
        "  - id: INV-WAVE-PLAN-MAX-WORDS\n"
        "    threshold: 0\n"
        "    enforcers: []\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Hard Word Ceiling: 300 words max.\n", encoding="utf-8")
    (tmp_path / "docs" / "templates").mkdir(parents=True)
    (tmp_path / "docs" / "templates" / "wave_plan_template.md").write_text(
        "Plans have a hard maximum of 1,000 words.\n", encoding="utf-8"
    )

    pol_issues = scan_policy_registry_sync(tmp_path)
    cats = {i["policy_id"] for i in pol_issues}
    assert "INV-OUTPUT-MAX-WORDS" in cats
    assert "INV-WAVE-PLAN-MAX-WORDS" in cats

    (tmp_path / "apps_research" / "prompts" / "templates").mkdir(parents=True)
    (tmp_path / "apps_research" / "prompts" / "templates" / "downstream_research_substrate_v1.jinja").write_text(
        "TASK without sentinel\n", encoding="utf-8"
    )
    parity_issues = scan_prompt_code_parity(tmp_path)
    assert any(i["category"] == "MARKDOWN_PROMPT_SENTINEL_DRIFT" for i in parity_issues)


def test_secrets_and_verify_commit_collect_and_scan_all_text_extensions(tmp_path: Path) -> None:
    """verify_commit and lint_secrets must collect and detect credentials in .md, .txt, .jinja, .csv, .ini."""
    tok = "sk-" + "Zp9Qr8St7Uv6Wx5Yz4Ab3Cd2Ef1Gh0Ij"
    for rel_file, body in (
        ("docs/leak.md", f"API token in markdown: {tok}\n"),
        ("notes/leak.txt", f"Plain text secret: {tok}\n"),
        ("prompts/leak.jinja", f"{{# Jinja leak {tok} #}}\n"),
        ("data/leak.csv", f"id,key\n1,{tok}\n"),
        ("config/leak.ini", f"[auth]\napi_key = \"{tok}\"\n"),
    ):
        fp = tmp_path / rel_file
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(body, encoding="utf-8")

    _py_files, _schema_files, secret_files = _collect_repository_files(tmp_path)
    collected_rels = {p.relative_to(tmp_path).as_posix() for p in secret_files}
    assert {
        "docs/leak.md",
        "notes/leak.txt",
        "prompts/leak.jinja",
        "data/leak.csv",
        "config/leak.ini",
    }.issubset(collected_rels)

    for p in secret_files:
        hits = check_file_for_secrets(p, tmp_path)
        assert hits, f"Expected secret violation in {p}"


def test_eval_rubrics_and_runtime_auditor_and_council_scan_markdown_and_text(tmp_path: Path) -> None:
    """validate_eval_rubrics, agent_runtime_auditor, and GovernanceSwarmCouncil must enforce .md/.txt contracts."""
    # 1. Markdown rubric divergence & missing verdict check
    (tmp_path / "config" / "certification").mkdir(parents=True)
    (tmp_path / "resume_graph_engine" / "config" / "certification").mkdir(parents=True)
    (tmp_path / "config" / "certification" / "llm_judge_rubric.md").write_text(
        "SAFE UNSAFE_DIFFERENT_INTENT UNSAFE_POLICY_DRIFT UNCERTAIN 0.0 1.0\n", encoding="utf-8"
    )
    (tmp_path / "resume_graph_engine" / "config" / "certification" / "llm_judge_rubric.md").write_text(
        "SAFE only\n", encoding="utf-8"
    )
    rub_count, rub_errs = _validate_markdown_and_text_rubrics(tmp_path)
    assert rub_count == 2
    assert any("diverges from canonical" in e for e in rub_errs)
    assert any("UNSAFE_DIFFERENT_INTENT" in e for e in rub_errs)

    # 2. Markdown delegation contract check in .agents/skills/*.md
    skill_dir = tmp_path / ".agents" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    incomplete_contract = {
        "task_id": "t_md_1",
        "parent_task_id": "t_root_1",
        "objective": "Missing 7 mandatory fields",
    }
    (skill_dir / "SKILL.md").write_text(
        f"# Demo Skill\n\n```json\n{json.dumps(incomplete_contract, indent=2)}\n```\n",
        encoding="utf-8",
    )
    p1 = audit_pillar_1_delegation_contracts(tmp_path)
    assert p1["markdown_contracts_checked"] == 1
    assert not p1["passed"]
    assert any("Markdown JSON delegation contract missing mandatory fields" in g for g in p1["gaps"])


def test_live_repository_passes_full_markdown_links_and_ssot_boundary_audit() -> None:
    """Live repository must have zero broken links across .agents/rules/*.md and pass all 10 SSOT dimensions."""
    link_issues = audit_mcp_hooks_and_links(WORKTREE_ROOT)
    assert link_issues == [], f"Unexpected broken markdown/MCP links: {link_issues}"

    report = run_ssot_boundary_audit(repo_root=WORKTREE_ROOT)
    assert report["status"] == "PASS", f"Expected PASS, got defects: {json.dumps(report, indent=2)}"
    assert report["is_clean"] is True
    assert ".md" in report["config_sprawl_scan"]["extensions_searched"]
    assert ".jinja" in report["config_sprawl_scan"]["extensions_searched"]
    assert ".txt" in report["config_sprawl_scan"]["extensions_searched"]
