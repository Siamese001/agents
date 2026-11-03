"""Integration and sandbox unit tests for the 10-Dimension SSOT & Centralization Boundary Auditor (Wave 3)."""

from __future__ import annotations

import json
from pathlib import Path

from tools.ssot_boundary_auditor import REPO_ROOT, run_ssot_boundary_audit
from tools.validate_sidecar_separation import DEFAULT_SIDECARS_ROOT, validate_sidecar_separation
from tools.validate_turn_gates import REQUIRED_AGENTS_HEADERS, REQUIRED_TIER1_TOOLS


def _create_clean_sandbox(sandbox: Path) -> None:
    prompts_dir = sandbox / "automations" / "prompts"
    prompts_dir.mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        (prompts_dir / md_file.name).write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")

    tools_dir = sandbox / "tools"
    tools_dir.mkdir(parents=True)
    for ep in set(REQUIRED_TIER1_TOOLS) | {
        "storage_worktree_hygiene.py",
        "ssot_boundary_auditor.py",
        "ssot_sprawl_scanner.py",
        "ssot_hardcoding_scanner.py",
        "e2e_functionality_auditor.py",
        "retrieval_surface_auditor.py",
        "validate_eval_rubrics.py",
        "cost_token_budget_auditor.py",
        "testing_gaps_auditor.py",
        "validate_turn_gates.py",
        "hook_dispatch.py",
    }:
        (tools_dir / ep).write_text("# validate_word_budget_gate\n", encoding="utf-8")

    (sandbox / "pytest.ini").write_text("[pytest]\naddopts = --timeout=180\n", encoding="utf-8")
    (sandbox / "docs").mkdir(parents=True)
    (sandbox / "docs" / "refactoring-wave-protocol.md").write_text("# Wave Protocol\n", encoding="utf-8")

    (sandbox / ".mcp.json").write_text(json.dumps({"mcpServers": {"filesystem": {"command": "npx"}}}), encoding="utf-8")
    (sandbox / ".agents" / "rules").mkdir(parents=True)
    for rule_name in ("conformance-map.md", "output-brevity-governance.md", "pr-governance.md"):
        (sandbox / ".agents" / "rules" / rule_name).write_text(f"# {rule_name}\n", encoding="utf-8")

    (sandbox / ".agents" / "skills" / "demo").mkdir(parents=True)
    (sandbox / ".agents" / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Short skill.\n---\n# Demo\n",
        encoding="utf-8",
    )
    (sandbox / ".agents" / "mcp_config.json").write_text(
        json.dumps({"mcpServers": {"filesystem": {"command": "npx"}}}),
        encoding="utf-8",
    )
    (sandbox / ".agents" / "hooks.json").write_text(
        (REPO_ROOT / ".agents" / "hooks.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (sandbox / ".antigravity").mkdir()
    boundary_raw = (REPO_ROOT / ".antigravity" / "runtime-boundary.json").read_text(encoding="utf-8")
    (sandbox / ".antigravity" / "runtime-boundary.json").write_text(boundary_raw, encoding="utf-8")
    for sub in json.loads(boundary_raw).get("allowedSubsystems", []):
        if isinstance(sub, str):
            (sandbox / sub).mkdir(parents=True, exist_ok=True)

    headers_md = "\n\n".join(f"## {h}" for h in REQUIRED_AGENTS_HEADERS)
    (sandbox / "AGENTS.md").write_text(f"# Agents\n\n{headers_md}\n", encoding="utf-8")

    gov_dir = sandbox / "config" / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    (sandbox / "config" / "provider_profiles.yaml").write_text(
        (REPO_ROOT / "config" / "provider_profiles.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (sandbox / "config" / "model_catalog.json").write_text(
        (REPO_ROOT / "config" / "model_catalog.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (gov_dir / "centralization_registry.yaml").write_text(
        "version: '1.0.0'\n"
        "domain_threshold_owners:\n"
        "  resume_executive_summary_shape:\n"
        "    canonical_symbols:\n"
        "      EXEC_SUMMARY_MAX_WORDS: 150\n"
        "      EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE: 45\n",
        encoding="utf-8",
    )
    (gov_dir / "policy_registry.yaml").write_text(
        (REPO_ROOT / "config" / "governance" / "policy_registry.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_clean_sandbox_passes_all_ten_dimensions(tmp_path: Path) -> None:
    sandbox = tmp_path / "clean_repo"
    _create_clean_sandbox(sandbox)

    rep = run_ssot_boundary_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert rep["is_clean"] is True, rep
    assert rep["status"] == "PASS"
    assert len(rep["dimension_status"]) == 10
    assert all(v == "PASS" for v in rep["dimension_status"].values())
    assert rep["total_centralization_defects"] == 0


def test_fault_injected_sandbox_fails_dims_7_to_10(tmp_path: Path) -> None:
    sandbox = tmp_path / "dirty_repo"
    _create_clean_sandbox(sandbox)

    # Dim 7: Multi-folder sprawl (60 vs 150 in rg_style_profile.yaml)
    rg_dir = sandbox / "resume_graph_engine" / "src" / "apps_rg"
    rg_dir.mkdir(parents=True)
    (rg_dir / "rg_style_profile.yaml").write_text(
        "section_style:\n  summary:\n    max_words: 60\n",
        encoding="utf-8",
    )

    # Dim 8: Policy registry bypass
    (sandbox / "tools" / "hook_dispatch.py").write_text("# missing live word budget call\n", encoding="utf-8")

    # Dim 9: Hardcoded threshold literal + unassigned split
    exec_dir = rg_dir / "runtime" / "sections" / "executive_summary"
    exec_dir.mkdir(parents=True)
    (exec_dir / "policy.py").write_text(
        "class VoiceRepairPolicy:\n"
        "    max_sentence_length: int = 35\n"
        "def check(s: str) -> None:\n"
        "    s.split()\n",
        encoding="utf-8",
    )

    # Dim 10: Prompt-to-code parity drift
    (exec_dir / "word_budget_repair.py").write_text(
        'PROMPT = "Rewrite at 105-120 words."\n',
        encoding="utf-8",
    )

    rep = run_ssot_boundary_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert rep["is_clean"] is False
    assert rep["status"] == "FAIL"
    assert rep["dimension_status"]["dim_7_multi_folder_config_sprawl"] == "FAIL"
    assert rep["dimension_status"]["dim_8_policy_registry_synchronization"] == "FAIL"
    assert rep["dimension_status"]["dim_9_unowned_hardcoded_thresholds"] == "FAIL"
    assert rep["dimension_status"]["dim_10_prompt_to_code_numeric_parity"] == "FAIL"
    assert rep["total_centralization_defects"] >= 4


def test_revamped_ssot_prompt_passes_sidecar_separation_and_shared_contract() -> None:
    res = validate_sidecar_separation(repo_root=REPO_ROOT, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert res["status"] == "PASS", res["violations"]
    assert res["is_clean"] is True
    prompt_text = (REPO_ROOT / "automations" / "prompts" / "agents_ssot_boundary_agent.md").read_text(encoding="utf-8")
    assert "10-Dimension" in prompt_text
    assert "ssot_sprawl_scanner.py" in prompt_text
    assert "ssot_hardcoding_scanner.py" in prompt_text
    assert "centralization_registry.yaml" in prompt_text
