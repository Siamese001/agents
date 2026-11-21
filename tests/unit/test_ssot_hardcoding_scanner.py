"""Fault-injection and sandbox unit tests for Wave 2 anti-hardcoding and prompt parity scanner."""

from __future__ import annotations

import json
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


def test_package_prefix_owner_allows_split_threshold_submodules_and_blocks_rogue(tmp_path: Path) -> None:
    gov_dir = tmp_path / "config" / "governance"
    gov_dir.mkdir(parents=True)
    (gov_dir / "centralization_registry.yaml").write_text(
        "version: '1.0.0'\n"
        "domain_threshold_owners:\n"
        "  resume_executive_summary_shape:\n"
        "    owner_file: 'resume_graph_engine/src/apps_rg/runtime/validators/executive_summary_x2.py'\n"
        "    owner_package:\n"
        "      - 'resume_graph_engine/src/apps_rg/runtime/validators/executive_summary/'\n"
        "      - 'resume_graph_engine/src/apps_rg/runtime/contracts/'\n"
        "    Aggregator_ssot: 'resume_graph_engine/src/apps_rg/runtime/sections/section_product_shape_ssot.py'\n"
        "    aggregator_package:\n"
        "      - 'resume_graph_engine/src/apps_rg/runtime/sections/shape_ssot/'\n"
        "    canonical_symbols:\n"
        "      EXEC_SUMMARY_MAX_WORDS: 150\n"
        "      EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE: 45\n"
        "  resume_narrative_and_headline_shape:\n"
        "    owner_file: 'resume_graph_engine/src/apps_rg/runtime/sections/section_product_shape_ssot.py'\n"
        "    owner_package:\n"
        "      - 'resume_graph_engine/src/apps_rg/runtime/sections/shape_ssot/'\n"
        "    canonical_symbols:\n"
        "      NARRATIVE_MAX_WORDS: 58\n",
        encoding="utf-8",
    )

    val_pkg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "validators" / "executive_summary"
    val_pkg.mkdir(parents=True)
    (val_pkg / "__init__.py").write_text("from .bounds import EXEC_SUMMARY_MAX_WORDS\n", encoding="utf-8")
    (val_pkg / "bounds.py").write_text(
        "EXEC_SUMMARY_MAX_WORDS = 150\nEXEC_SUMMARY_MAX_WORDS_PER_SENTENCE = 45\n",
        encoding="utf-8",
    )

    shape_pkg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "sections" / "shape_ssot"
    shape_pkg.mkdir(parents=True)
    (shape_pkg / "__init__.py").write_text("from .constants import NARRATIVE_MAX_WORDS\n", encoding="utf-8")
    (shape_pkg / "constants.py").write_text("NARRATIVE_MAX_WORDS = 58\n", encoding="utf-8")

    contracts_pkg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "contracts"
    contracts_pkg.mkdir(parents=True)
    (contracts_pkg / "shared_bounds.py").write_text("EXEC_SUMMARY_MAX_WORDS = 150\n", encoding="utf-8")

    # Module-to-package split (<stem>/constants.py) also resolves cleanly
    stem_pkg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "validators" / "executive_summary_x2"
    stem_pkg.mkdir(parents=True)
    (stem_pkg / "constants.py").write_text("EXEC_SUMMARY_MAX_WORDS = 150\n", encoding="utf-8")

    assert scan_hardcoded_threshold_literals(tmp_path) == []

    # Governed consumer directory still fails closed on unauthorized constant redefinition
    sec_exec = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "sections" / "executive_summary"
    sec_exec.mkdir(parents=True)
    (sec_exec / "rogue.py").write_text("EXEC_SUMMARY_MAX_WORDS = 120\n", encoding="utf-8")
    findings = scan_hardcoded_threshold_literals(tmp_path)
    assert len(findings) == 1
    assert findings[0]["category"] == "DUPLICATE_CONSTANT_LITERAL"
    assert findings[0]["file"].endswith("sections/executive_summary/rogue.py")


def test_env_ratchet_package_prefix_and_split_module_aggregation(tmp_path: Path) -> None:
    gov_dir = tmp_path / "config" / "governance"
    gov_dir.mkdir(parents=True)
    (gov_dir / "centralization_registry.yaml").write_text(
        "version: '1.0.0'\n"
        "approved_env_loader_paths:\n"
        "  - 'infrastructure/'\n"
        "  - 'resume_graph_engine/src/apps_rg/runtime/env_bootstrap.py'\n",
        encoding="utf-8",
    )
    (gov_dir / "env_lookup_ratchet.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "package_counts": {
                    "resume_graph_engine/src/apps_rg/runtime/sections/role_episode/": 2,
                },
                "file_counts": {
                    "resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py": 2,
                },
            }
        ),
        encoding="utf-8",
    )

    # Split approved env loader module -> package allowed
    boot_pkg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "env_bootstrap"
    boot_pkg.mkdir(parents=True)
    (boot_pkg / "loader.py").write_text("import os\nVAL = os.environ.get('X')\n", encoding="utf-8")

    # Package-prefix env ratchet allows <= 2 aggregate lookups across submodules
    role_pkg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "sections" / "role_episode"
    role_pkg.mkdir(parents=True)
    (role_pkg / "a.py").write_text("import os\nA = os.getenv('A')\n", encoding="utf-8")
    (role_pkg / "b.py").write_text("import os\nB = os.getenv('B')\n", encoding="utf-8")

    # Module-to-package split shares file_counts ceiling across submodules
    lane_pkg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "sections" / "role_episode_lane"
    lane_pkg.mkdir(parents=True)
    (lane_pkg / "p1.py").write_text("import os\nP1 = os.getenv('P1')\n", encoding="utf-8")
    (lane_pkg / "p2.py").write_text("import os\nP2 = os.getenv('P2')\n", encoding="utf-8")

    assert scan_ast_hygiene_and_env_sprawl(tmp_path) == []

    # Exceeding package aggregate ceiling by 1 fails closed
    (role_pkg / "c.py").write_text("import os\nC = os.getenv('C')\n", encoding="utf-8")
    findings = scan_ast_hygiene_and_env_sprawl(tmp_path)
    assert len(findings) == 1
    assert findings[0]["category"] == "UNCENTRALIZED_ENV_LOOKUP"
    assert findings[0]["file"].endswith("role_episode/c.py")


def test_policy_registry_sync_and_prompt_parity_support_split_packages(tmp_path: Path) -> None:
    gov_dir = tmp_path / "config" / "governance"
    gov_dir.mkdir(parents=True)
    (gov_dir / "policy_registry.yaml").write_text(
        "policies:\n"
        "  - id: INV-WAVE-PLAN-MAX-WORDS\n"
        "    threshold: 1000\n"
        "    enforcer: tools/validate_implementation_plan.py\n"
        "    rule_reference: docs/refactoring-wave-protocol.md\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "refactoring-wave-protocol.md").write_text("# protocol\n", encoding="utf-8")

    plan_pkg = tmp_path / "tools" / "validate_implementation_plan"
    plan_pkg.mkdir(parents=True)
    (plan_pkg / "__init__.py").write_text("from .core import main\n", encoding="utf-8")
    (plan_pkg / "core.py").write_text("def main():\n    return 0\n", encoding="utf-8")

    ev_pkg = tmp_path / "tools" / "implementation_plan_core" / "evidence_requirements"
    ev_pkg.mkdir(parents=True)
    (ev_pkg / "__init__.py").write_text("from .loader import MAX_PLAN_WORDS\n", encoding="utf-8")
    (ev_pkg / "loader.py").write_text("POLICY = 'config/governance/policy_registry.yaml'\nMAX_PLAN_WORDS = 1000\n", encoding="utf-8")

    assert scan_policy_registry_sync(tmp_path) == []

    exec_pkg = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "sections" / "executive_summary_lane"
    exec_pkg.mkdir(parents=True)
    (exec_pkg / "repair.py").write_text('PROMPT = "Target 105-120 words."\n', encoding="utf-8")
    parity_findings = scan_prompt_code_parity(tmp_path)
    assert any(f["category"] == "PROMPT_VALIDATOR_BOUND_DRIFT" and f["file"].endswith("executive_summary_lane/repair.py") for f in parity_findings)
