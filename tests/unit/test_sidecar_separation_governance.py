"""Unit tests verifying sidecar separation between Agents Repo and Decision Intelligence Engine."""

from __future__ import annotations

import json
from pathlib import Path

from tools.validate_sidecar_separation import (
    AGENTS_CANONICAL_ROOT,
    DEFAULT_SIDECARS_ROOT,
    EXPECTED_AGENTS_SIDECARS,
    EXPECTED_NEE_SIDECARS,
    NEE_CANONICAL_ROOT,
    REPO_ROOT,
    REQUIRED_PROMPT_PARITY_MARKERS,
    REQUIRED_SHARED_CONTRACT_MARKERS,
    validate_sidecar_separation,
)


def test_live_sidecar_separation_passes_with_zero_collisions() -> None:
    """Verify live global sidecars and repository prompts pass all separation invariants."""
    result = validate_sidecar_separation(
        repo_root=REPO_ROOT,
        sidecars_root=DEFAULT_SIDECARS_ROOT,
    )
    assert result["status"] == "PASS", f"Expected PASS, got violations: {result['violations']}"
    assert result["is_clean"] is True
    assert result["agents_sidecar_count"] == 7
    assert result["nee_sidecar_count"] == 17
    assert result["collision_count"] == 0
    assert result["violations"] == []


def test_agents_sidecars_target_outreach_resume_and_apps_research() -> None:
    """Verify the 7 Agents prompt specifications cover outreach_engine, resume_engine, and apps_research."""
    prompts_dir = REPO_ROOT / "automations" / "prompts"
    combined_text = "\n".join(
        (prompts_dir / spec["prompt_file"]).read_text(encoding="utf-8")
        for spec in EXPECTED_AGENTS_SIDECARS.values()
    )
    assert "outreach_engine" in combined_text
    assert "resume_engine" in combined_text
    assert "resume_graph_engine" in combined_text
    assert "apps_research" in combined_text
    assert "AppsResearchBridge" in combined_text
    assert "ResearchRetrievalEngine" in combined_text
    assert "GovernedResearchRun" in combined_text
    assert "INV-REPO-SEPARATION-AGENTS-ONLY" in combined_text


def test_validator_rejects_cross_repo_permission_or_schedule_collision(tmp_path: Path) -> None:
    """Negative control: verify validator fails closed on cron collision or forbidden NEE permission grant."""
    fake_repo = tmp_path / "repo"
    prompts_dir = fake_repo / "automations" / "prompts"
    prompts_dir.mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        (prompts_dir / md_file.name).write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")

    fake_sidecars = tmp_path / "sidecars"
    fake_sidecars.mkdir(parents=True)

    # Copy all 17 NEE sidecars and 7 Agents sidecars into sandbox
    for sid in (*EXPECTED_AGENTS_SIDECARS.keys(), *EXPECTED_NEE_SIDECARS):
        src = DEFAULT_SIDECARS_ROOT / sid / "sidecar.json"
        dst_dir = fake_sidecars / sid
        dst_dir.mkdir(parents=True)
        (dst_dir / "sidecar.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    # Inject a schedule collision (06:00 ET used by corner-foresight-blindspot-scout) and a forbidden NEE grant
    bad_file = fake_sidecars / "agents-outreach-resume-functionality" / "sidecar.json"
    bad_payload = json.loads(bad_file.read_text(encoding="utf-8"))
    bad_payload["args"][0] = "CRON_TZ=America/New_York 0 6 * * *"
    bad_payload["agent_permissions"]["access_grants"].append(f"read_file({NEE_CANONICAL_ROOT})")
    bad_file.write_text(json.dumps(bad_payload, indent=2), encoding="utf-8")

    result = validate_sidecar_separation(repo_root=fake_repo, sidecars_root=fake_sidecars)
    assert result["status"] == "FAIL"
    assert result["is_clean"] is False
    joined_violations = "\n".join(result["violations"])
    assert "Cron schedule collision" in joined_violations
    assert "forbidden Decision Intelligence Engine grant" in joined_violations
    assert AGENTS_CANONICAL_ROOT != NEE_CANONICAL_ROOT


def test_all_seven_agents_prompts_enforce_decision_intelligence_parity_and_wave_plan_mandate() -> None:
    """Verify every Agents prompt specification enforces the 4-phase Decision Intelligence contract and wave plan mandate."""
    prompts_dir = REPO_ROOT / "automations" / "prompts"
    shared_text = (prompts_dir / "_shared_governance_contract.md").read_text(encoding="utf-8")
    for marker in REQUIRED_SHARED_CONTRACT_MARKERS:
        assert marker in shared_text, f"Missing '{marker}' in _shared_governance_contract.md"

    for sidecar_id, spec in EXPECTED_AGENTS_SIDECARS.items():
        prompt_path = prompts_dir / spec["prompt_file"]
        assert prompt_path.is_file(), f"Missing prompt for {sidecar_id}: {prompt_path}"
        text = prompt_path.read_text(encoding="utf-8")
        for marker in REQUIRED_PROMPT_PARITY_MARKERS:
            assert marker in text, f"{spec['prompt_file']} missing mandatory parity marker '{marker}'"
        assert NEE_CANONICAL_ROOT not in text


def test_validator_rejects_prompt_missing_wave_plan_mandate(tmp_path: Path) -> None:
    """Negative control: verify validator fails closed if a prompt omits UNCONDITIONAL_WAVE_PLAN_MANDATE."""
    fake_repo = tmp_path / "repo"
    prompts_dir = fake_repo / "automations" / "prompts"
    prompts_dir.mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if md_file.name == "agents_e2e_functionality_assurance_agent.md":
            content = content.replace("UNCONDITIONAL_WAVE_PLAN_MANDATE", "REMOVED_MANDATE")
        (prompts_dir / md_file.name).write_text(content, encoding="utf-8")

    result = validate_sidecar_separation(repo_root=fake_repo, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert result["status"] == "FAIL"
    assert any("UNCONDITIONAL_WAVE_PLAN_MANDATE" in v for v in result["violations"])


def test_storage_worktree_hygiene_six_pillar_audit_and_sqlite_wal_remediation(tmp_path: Path) -> None:
    """Verify 6-pillar storage/worktree hygiene scanner transitions SQLite DBs to WAL and prunes stale locks."""
    import os
    import sqlite3
    import subprocess
    import time
    from tools.storage_worktree_hygiene import run_six_pillar_hygiene_audit

    sandbox = tmp_path / "agents_sandbox"
    (sandbox / "artifacts" / "governance").mkdir(parents=True)
    (sandbox / "automations" / "prompts").mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        (sandbox / "automations" / "prompts" / md_file.name).write_text(
            md_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    subprocess.run(["git", "init", "-b", "main", str(sandbox)], check=True, capture_output=True, timeout=30)

    db_path = sandbox / "artifacts" / "governance" / "hitl_decisions.sqlite"
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=DELETE;")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT);")
    conn.execute("INSERT INTO t (val) VALUES ('a');")
    conn.commit()
    conn.close()

    stale_tmp = sandbox / "orphaned_scratch.tmp"
    stale_tmp.write_text("stale", encoding="utf-8")
    old_ts = time.time() - 90000
    os.utime(stale_tmp, (old_ts, old_ts))

    # Audit before remediation detects DELETE journal mode and stale .tmp file
    pre_audit = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=False)
    assert pre_audit["pillar_status"]["pillar_2_sqlite_integrity_wal"] == "FINDINGS"
    assert pre_audit["pillar_status"]["pillar_5_stale_locks_temps"] == "FINDINGS"
    assert "orphaned_scratch.tmp" in pre_audit["stale_files"]

    # Remediation transitions SQLite DB to WAL, checkpoints it, and removes stale .tmp file
    post_audit = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=True)
    assert post_audit["status"] == "PASS"
    assert post_audit["is_clean"] is True
    assert post_audit["dbs"][0]["journal_mode"] == "wal"
    assert post_audit["dbs"][0]["integrity"] == "ok"
    assert post_audit["stale_files"] == []
    assert not stale_tmp.exists()


def test_validator_rejects_prompt_missing_consolidate_sidecar_marker(tmp_path: Path) -> None:
    """Negative control: verify validator fails closed if a prompt omits --consolidate-sidecar in Phase 0."""
    fake_repo = tmp_path / "repo"
    prompts_dir = fake_repo / "automations" / "prompts"
    prompts_dir.mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if md_file.name == "agents_cost_token_budget_agent.md":
            content = content.replace("--consolidate-sidecar", "--legacy-worktree-add")
        (prompts_dir / md_file.name).write_text(content, encoding="utf-8")

    result = validate_sidecar_separation(repo_root=fake_repo, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert result["status"] == "FAIL"
    assert any("--consolidate-sidecar" in v for v in result["violations"])


def test_eight_pillar_cost_and_caching_audit_passes_on_live_repo() -> None:
    """Verify the 8-pillar cost, multi-tier caching, and token budget auditor passes on live repo."""
    from tools.cost_token_budget_auditor import (
        MIN_REQUIRED_ROI_MULTIPLE,
        compute_caching_roi_benchmark,
        run_eight_pillar_cost_token_audit,
    )

    report = run_eight_pillar_cost_token_audit(repo_root=REPO_ROOT)
    assert report["status"] == "PASS", f"Expected PASS, got gaps: {[p for p in report['pillars'] if p['gaps']]}"
    assert report["is_clean"] is True
    assert report["total_pillars"] == 8
    assert report["pillars_passing"] == 8
    assert report["total_gaps"] == 0

    roi = compute_caching_roi_benchmark()
    assert roi["roi_gate_passed"] is True
    assert roi["roi_multiple"] >= MIN_REQUIRED_ROI_MULTIPLE
    assert roi["token_savings_equivalent"] > 300_000

    cost_prompt = (REPO_ROOT / "automations" / "prompts" / "agents_cost_token_budget_agent.md").read_text(
        encoding="utf-8"
    )
    for surface in (
        "anthropic_prompt_cache.py",
        "anthropic_section_cache_payload.py",
        "c02_semantic_cache_payload.py",
        "semantic_cache_persistence_quarantine.py",
        "cache_identity.py",
        "briefing_cache.py",
        "briefing_resolver.py",
        "executive_summary_token_budget.py",
        "zero_llm_qualification.py",
        "model_token_governor.py",
        "cost_token_budget_auditor.py",
    ):
        assert surface in cost_prompt, f"Missing caching/tokenomics surface '{surface}' in prompt spec"


def test_eight_pillar_cost_auditor_detects_missing_caching_and_effort_drift(tmp_path: Path) -> None:
    """Negative control: verify 8-pillar auditor flags effort drift and missing caching modules."""
    from tools.cost_token_budget_auditor import run_eight_pillar_cost_token_audit

    sandbox = tmp_path / "broken_cost_repo"
    (sandbox / "config").mkdir(parents=True)
    # Write a provider profile with over-pinned 'high' effort on section generation and wrong governor cap
    (sandbox / "config" / "provider_profiles.yaml").write_text(
        "model_pin_ownership:\n"
        "  environment_model_override_allowed: true\n"
        "profiles:\n"
        "  external_openai_generator:\n"
        "    model_by_section:\n"
        "      slalom_narrative: gpt-5.6-luna\n"
        "    effort_by_section:\n"
        "      slalom_narrative: high\n"
        "runtime_limits:\n"
        "  model_token_governor:\n"
        "    max_input_tokens_per_attempt: 999999\n"
        "    max_reserved_tokens_per_run: 999999\n",
        encoding="utf-8",
    )

    report = run_eight_pillar_cost_token_audit(repo_root=sandbox)
    assert report["status"] == "ACTION_REQUIRED"
    assert report["is_clean"] is False
    assert report["total_gaps"] >= 7
    p1_gaps = "\n".join(report["pillars"][0]["gaps"])
    assert "environment_model_override_allowed: false" in p1_gaps
    assert "exceeds 'low' compact schema generation tier" in p1_gaps


