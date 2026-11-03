"""Fault-injection and sandbox unit tests for Wave 2 anti-hardcoding and prompt parity scanner."""

from __future__ import annotations

from pathlib import Path

from tools.ssot_hardcoding_scanner import (
    run_hardcoding_scan,
    scan_ast_hygiene_and_env_sprawl,
    scan_hardcoded_threshold_literals,
    scan_policy_registry_sync,
    scan_prompt_code_parity,
)


def test_policy_registry_sync_catches_hardcoded_plan_words_and_unwired_hook(tmp_path: Path) -> None:
    gov_dir = tmp_path / "config" / "governance"
    gov_dir.mkdir(parents=True)
    (gov_dir / "policy_registry.yaml").write_text(
        "policies:\n"
        "  - id: INV-WAVE-PLAN-MAX-WORDS\n"
        "    threshold: 1000\n"
        "    enforcer: tools/validate_implementation_plan.py\n"
        "    rule_reference: docs/refactoring-wave-protocol.md\n"
        "  - id: INV-OUTPUT-MAX-WORDS\n"
        "    threshold: 300\n"
        "    enforcer: tools/validate_turn_gates.py\n"
        "    rule_reference: .agents/rules/output-brevity-governance.md\n",
        encoding="utf-8",
    )

    tools_dir = tmp_path / "tools" / "implementation_plan_core"
    tools_dir.mkdir(parents=True)
    (tmp_path / "tools" / "validate_implementation_plan.py").write_text("# stub\n", encoding="utf-8")
    (tmp_path / "tools" / "validate_turn_gates.py").write_text("# stub\n", encoding="utf-8")
    (tmp_path / "tools" / "hook_dispatch.py").write_text("def handle_post_invocation():\n    pass\n", encoding="utf-8")
    (tools_dir / "evidence_requirements.py").write_text("MAX_PLAN_WORDS = 1000\n", encoding="utf-8")

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "refactoring-wave-protocol.md").write_text("# protocol\n", encoding="utf-8")
    (tmp_path / ".agents" / "rules").mkdir(parents=True)
    (tmp_path / ".agents" / "rules" / "output-brevity-governance.md").write_text("# rule\n", encoding="utf-8")

    findings = scan_policy_registry_sync(tmp_path)
    cats = {f["category"] for f in findings}
    assert "POLICY_REGISTRY_BYPASS" in cats
    assert "UNWIRED_LIVE_HOOK_GATE" in cats


def test_hardcoded_threshold_literals_catches_duplicate_constants_policy_defaults_and_eval_scenarios(
    tmp_path: Path,
) -> None:
    exec_dir = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "sections" / "executive_summary"
    exec_dir.mkdir(parents=True)
    (exec_dir / "policy.py").write_text(
        "class VoiceRepairPolicy:\n"
        "    max_word_count: int = 150\n"
        "    max_sentence_length: int = 35\n",
        encoding="utf-8",
    )
    (exec_dir / "rogue.py").write_text("EXEC_SUMMARY_MAX_WORDS = 120\n", encoding="utf-8")

    eval_dir = tmp_path / "apps_eval"
    eval_dir.mkdir(parents=True)
    (eval_dir / "scenarios.py").write_text(
        'def get_bounds():\n    return {"length_bounds": {"max_words": 160, "min_words": 12}}\n',
        encoding="utf-8",
    )

    findings = scan_hardcoded_threshold_literals(tmp_path)
    cats = {f["category"] for f in findings}
    assert "DUPLICATE_CONSTANT_LITERAL" in cats
    assert "CONFLICTING_POLICY_DEFAULT" in cats
    assert "EVAL_SCENARIO_BOUND_DRIFT" in cats


def test_prompt_code_parity_catches_105_120_repair_range_and_research_template_mismatch(tmp_path: Path) -> None:
    wb_dir = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "sections" / "executive_summary"
    wb_dir.mkdir(parents=True)
    (wb_dir / "word_budget_repair.py").write_text(
        'PROMPT = "Rewrite the SAME evidence arc at 105-120 words, preserving rows."\n',
        encoding="utf-8",
    )

    tpl_dir = tmp_path / "apps_research" / "prompt_assembly" / "templates"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "company_brief_synthesis_v1.yaml").write_text(
        "modes:\n  - LIGHT: Executive summary only. Max 500 words.\n",
        encoding="utf-8",
    )
    cfg_dir = tmp_path / "apps_research" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "agent_spec_config.py").write_text(
        'ArtifactModeConfig(mode_id="brief", max_words=1200)\n',
        encoding="utf-8",
    )

    findings = scan_prompt_code_parity(tmp_path)
    cats = {f["category"] for f in findings}
    assert "PROMPT_VALIDATOR_BOUND_DRIFT" in cats
    assert "TEMPLATE_CONFIG_BOUND_DRIFT" in cats


def test_ast_hygiene_catches_unassigned_split_uncentralized_env_and_hardcoded_home_path(tmp_path: Path) -> None:
    val_dir = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "validators"
    val_dir.mkdir(parents=True)
    user_root = "/Users/" + "alice/project"
    (val_dir / "achv_bullet.py").write_text(
        "import os\n"
        "def check(bullet: str) -> int:\n"
        "    bullet.split()\n"
        "    flag = os.environ.get('ROGUE_FLAG')\n"
        f"    p = '{user_root}'\n"
        "    return len(p)\n",
        encoding="utf-8",
    )

    findings = scan_ast_hygiene_and_env_sprawl(tmp_path)
    cats = {f["category"] for f in findings}
    assert "UNASSIGNED_SPLIT_CALL_BUG" in cats
    assert "UNCENTRALIZED_ENV_LOOKUP" in cats
    assert "HARDCODED_MACHINE_PATH" in cats


def test_clean_sandbox_passes_hardcoding_scan(tmp_path: Path) -> None:
    inf_dir = tmp_path / "infrastructure"
    inf_dir.mkdir(parents=True)
    (inf_dir / "settings.py").write_text(
        "import os\n"
        "def get_env(k: str) -> str:\n"
        "    return os.environ.get(k, '')\n",
        encoding="utf-8",
    )
    rep = run_hardcoding_scan(tmp_path)
    assert rep["is_clean"] is True
    assert rep["status"] == "PASS"
