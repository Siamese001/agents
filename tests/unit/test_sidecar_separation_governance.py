"""Behavioral governance and sidecar separation tests across all 7 Agents assurance workflows."""

from __future__ import annotations

import json
from pathlib import Path

from tools.validate_sidecar_separation import (
    AGENTS_CANONICAL_ROOT,
    DEFAULT_SIDECARS_ROOT,
    EXPECTED_AGENTS_SIDECARS,
    NEE_CANONICAL_ROOT,
    REPO_ROOT,
    REQUIRED_PROMPT_PARITY_MARKERS,
    REQUIRED_SHARED_CONTRACT_MARKERS,
    validate_sidecar_separation,
)


def test_live_sidecar_separation_passes_with_zero_collisions() -> None:
    """Verify live global sidecars have zero Agents background schedules while all 7 prompts bind dedicated auditors."""
    result = validate_sidecar_separation(
        repo_root=REPO_ROOT,
        sidecars_root=DEFAULT_SIDECARS_ROOT,
    )
    assert result["status"] == "PASS", f"Expected PASS, got violations: {result['violations']}"
    assert result["is_clean"] is True
    assert result["agents_scheduled_count"] == 0
    assert result["agents_prompt_count"] == 7
    assert result["agents_sidecar_count"] == 7
    assert result["nee_sidecar_count"] >= 3
    assert result["collision_count"] == 0
    assert result["violations"] == []


def test_all_seven_workflows_bind_distinct_executable_behavioral_auditors() -> None:
    """Verify every workflow binds a dedicated fail-closed Python auditor module (never verify_commit.py)."""
    expected_entrypoints = {
        "agents-storage-worktree-hygiene": "tools/storage_worktree_hygiene.py",
        "agents-ssot-boundary-governance": "tools/ssot_boundary_auditor.py",
        "agents-outreach-resume-functionality": "tools/e2e_functionality_auditor.py",
        "agents-research-retrieval-surface": "tools/retrieval_surface_auditor.py",
        "agents-evals-judge-assurance": "tools/validate_eval_rubrics.py",
        "agents-cost-token-budget": "tools/cost_token_budget_auditor.py",
        "agents-testing-gaps-assurance": "tools/testing_gaps_auditor.py",
    }
    assert {k: v["deterministic_entrypoint"] for k, v in EXPECTED_AGENTS_SIDECARS.items()} == expected_entrypoints
    for workflow_id, rel_ep in expected_entrypoints.items():
        ep_path = REPO_ROOT / rel_ep
        assert ep_path.is_file(), f"Missing dedicated auditor {rel_ep} for {workflow_id}"
        assert rel_ep != "tools/verify_commit.py"
        assert EXPECTED_AGENTS_SIDECARS[workflow_id]["requires_remediation_quota"] is True, (
            f"{workflow_id} must enforce C04 remediation quota without exemption"
        )


def test_validator_rejects_inline_heredoc_and_missing_auditor_invocation(tmp_path: Path) -> None:
    """Negative control: validator rejects print-only inline heredocs or missing auditor CLI invocation."""
    fake_repo = tmp_path / "repo"
    prompts_dir = fake_repo / "automations" / "prompts"
    prompts_dir.mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if md_file.name == "agents_e2e_functionality_assurance_agent.md":
            content = content.replace("e2e_functionality_auditor.py", "verify_commit.py") + "\npython - <<'PY'\nPY\n"
        (prompts_dir / md_file.name).write_text(content, encoding="utf-8")

    result = validate_sidecar_separation(repo_root=fake_repo, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert result["status"] == "FAIL"
    joined = "\n".join(result["violations"])
    assert "e2e_functionality_auditor.py" in joined
    assert "inline heredoc script" in joined


def test_validator_rejects_reintroduced_daily_schedule_or_cross_repo_grant(tmp_path: Path) -> None:
    """Negative control: verify validator fails closed if an agents-* background schedule or cross-repo grant appears."""
    fake_repo = tmp_path / "repo"
    prompts_dir = fake_repo / "automations" / "prompts"
    prompts_dir.mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        (prompts_dir / md_file.name).write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")

    fake_sidecars = tmp_path / "sidecars"
    fake_sidecars.mkdir(parents=True)

    for child in DEFAULT_SIDECARS_ROOT.iterdir():
        src = child / "sidecar.json"
        if child.is_dir() and src.is_file():
            dst_dir = fake_sidecars / child.name
            dst_dir.mkdir(parents=True)
            (dst_dir / "sidecar.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    rogue_dir = fake_sidecars / "agents-outreach-resume-functionality"
    rogue_dir.mkdir(parents=True)
    (rogue_dir / "sidecar.json").write_text(json.dumps({"builtin": "schedule"}), encoding="utf-8")

    nee_target = next(
        p for p in fake_sidecars.glob("*/sidecar.json") if not p.parent.name.startswith("agents-")
    )
    bad_payload = json.loads(nee_target.read_text(encoding="utf-8"))
    bad_payload.setdefault("agent_permissions", {}).setdefault("access_grants", []).append(
        f"read_file({AGENTS_CANONICAL_ROOT})"
    )
    nee_target.write_text(json.dumps(bad_payload, indent=2), encoding="utf-8")

    result = validate_sidecar_separation(repo_root=fake_repo, sidecars_root=fake_sidecars)
    assert result["status"] == "FAIL"
    assert result["is_clean"] is False
    assert result["agents_scheduled_count"] >= 2
    joined_violations = "\n".join(result["violations"])
    assert "Unapproved background schedule directory" in joined_violations
    assert AGENTS_CANONICAL_ROOT in joined_violations
    assert AGENTS_CANONICAL_ROOT != NEE_CANONICAL_ROOT


def test_all_seven_agents_prompts_enforce_parity_and_wave_plan_mandate() -> None:
    """Verify every Agents prompt specification enforces the 4-phase contract and wave plan mandate."""
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


def test_validator_rejects_prompt_missing_wave_plan_mandate_or_consolidate_marker(tmp_path: Path) -> None:
    """Negative control: validator fails closed if a prompt omits UNCONDITIONAL_WAVE_PLAN_MANDATE or --consolidate-sidecar."""
    fake_repo = tmp_path / "repo"
    prompts_dir = fake_repo / "automations" / "prompts"
    prompts_dir.mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if md_file.name == "agents_e2e_functionality_assurance_agent.md":
            content = content.replace("UNCONDITIONAL_WAVE_PLAN_MANDATE", "REMOVED_MANDATE")
        if md_file.name == "agents_cost_token_budget_agent.md":
            content = content.replace("--consolidate-sidecar", "--legacy-worktree-add")
        (prompts_dir / md_file.name).write_text(content, encoding="utf-8")

    result = validate_sidecar_separation(repo_root=fake_repo, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert result["status"] == "FAIL"
    assert any("UNCONDITIONAL_WAVE_PLAN_MANDATE" in v for v in result["violations"])
    assert any("--consolidate-sidecar" in v for v in result["violations"])


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

    pre_audit = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=False)
    assert pre_audit["pillar_status"]["pillar_2_sqlite_integrity_wal"] == "FINDINGS"
    assert pre_audit["pillar_status"]["pillar_5_stale_locks_temps"] == "FINDINGS"
    assert "orphaned_scratch.tmp" in pre_audit["stale_files"]

    post_audit = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=True)
    assert post_audit["status"] == "PASS"
    assert post_audit["is_clean"] is True
    assert post_audit["dbs"][0]["journal_mode"] == "wal"
    assert post_audit["dbs"][0]["integrity"] == "ok"
    assert post_audit["stale_files"] == []
    assert not stale_tmp.exists()


def test_eight_pillar_cost_and_caching_audit_passes_with_zero_substring_theater() -> None:
    """Verify the 8-pillar cost, multi-tier caching, and token budget auditor passes behaviorally on live repo."""
    from tools.cost_token_budget_auditor import (
        MIN_REQUIRED_ROI_MULTIPLE,
        compute_caching_roi_benchmark,
        run_eight_pillar_cost_token_audit,
    )

    auditor_src = (REPO_ROOT / "tools" / "cost_token_budget_auditor.py").read_text(encoding="utf-8")
    assert "if marker not in txt:" not in auditor_src

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


def test_eight_pillar_cost_auditor_detects_missing_caching_and_effort_drift(tmp_path: Path) -> None:
    """Negative control: verify 8-pillar auditor flags effort drift and missing caching modules."""
    from tools.cost_token_budget_auditor import run_eight_pillar_cost_token_audit
    from tools.hitl_governance import load_approved_provider_models

    approved_sample = sorted(load_approved_provider_models(REPO_ROOT))[0]
    sandbox = tmp_path / "broken_cost_repo"
    (sandbox / "config").mkdir(parents=True)
    (sandbox / "config" / "provider_profiles.yaml").write_text(
        "model_pin_ownership:\n"
        "  environment_model_override_allowed: true\n"
        "profiles:\n"
        "  external_openai_generator:\n"
        "    model_by_section:\n"
        f"      slalom_narrative: {approved_sample}\n"
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


def test_agents_sidecar_dispositions_skill_budget_and_eval_rubrics() -> None:
    """Verify all 7 Agents sidecar dispositions map to root skills within the 26-skill budget."""
    from tools.audit_skills_budget import audit_skills_budget
    from tools.validate_eval_rubrics import validate_eval_rubrics

    budget_rep = audit_skills_budget(REPO_ROOT)
    assert budget_rep["status"] == "PASS"
    assert budget_rep["is_clean"] is True
    assert budget_rep["skill_count"] == 10
    assert budget_rep["skill_count"] <= 26

    root_skills = {s["name"] for s in budget_rep["skills"]}
    for sidecar_id, spec in EXPECTED_AGENTS_SIDECARS.items():
        assert "disposition" in spec
        assert "target_skill" in spec
        assert spec["target_skill"] in root_skills

    eval_rep = validate_eval_rubrics(REPO_ROOT)
    assert eval_rep["status"] == "PASS"
    assert eval_rep["is_clean"] is True


def test_testing_gaps_auditor_passes_on_live_repo_and_rejects_hardcoded_root(tmp_path: Path) -> None:
    """Verify testing_gaps_auditor scans all 4 test roots with 0 zero-assertion tests and 0 mock violations."""
    from tools.testing_gaps_auditor import run_testing_gaps_audit

    rep = run_testing_gaps_audit(REPO_ROOT)
    assert rep["status"] == "PASS", rep
    assert rep["is_clean"] is True
    assert rep["total_test_files_scanned"] >= 890
    assert rep["zero_assertion_tests"] == []
    assert rep["mock_reachability_violations"] == []

    fake_repo = tmp_path / "repo"
    prompts_dir = fake_repo / "automations" / "prompts"
    prompts_dir.mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if md_file.name == "agents_testing_gaps_assurance_agent.md":
            content += f'\nroot = Path("{AGENTS_CANONICAL_ROOT}")\n'
        (prompts_dir / md_file.name).write_text(content, encoding="utf-8")

    result = validate_sidecar_separation(repo_root=fake_repo, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert result["status"] == "FAIL"
    assert any("hardcodes primary repo root" in v for v in result["violations"])


def test_prefix_prewarm_semantic_fact_digest_and_shared_disk_briefing_cache(tmp_path: Path) -> None:
    """Verify prefix pre-warming, semantic fact-digest cache gate, 30-day disk briefing reuse, and Argon 4 routing."""
    from tools.cost_token_budget_auditor import run_eight_pillar_cost_token_audit
    from tools.cost_token_budget_probes import load_repo_module, load_yaml_strict

    c02, err = load_repo_module(REPO_ROOT, "resume_graph_engine/src/apps_rg/runtime/c0/c02_semantic_cache_payload.py")
    assert err is None and c02 is not None
    payload = c02.build_c02_semantic_cache_payload(
        section_id="executive_summary",
        atoms=[{"fact_id": "fact_a", "claim_text": "Delivered $42M migration", "confidence": "HIGH", "proof_status": "VERIFIED"}],
        vector_query_receipt={"dense_search_refs": ["ref_1"], "hybrid_enrichment_item_count": 1},
        target_company="Acme",
        target_role="SVP",
        jd_digest="jd_1",
        run_id="run_1",
    )
    assert c02.verify_semantic_fact_digest_cache_hit(payload, candidate_similarity=0.99, candidate_fact_ids=["fact_a"]) is True
    assert c02.verify_semantic_fact_digest_cache_hit(payload, candidate_similarity=0.99, candidate_fact_ids=["fact_b"]) is False
    assert c02.verify_semantic_fact_digest_cache_hit(payload, candidate_similarity=0.95, candidate_fact_ids=["fact_a"]) is False

    prof_doc, prof_err = load_yaml_strict(REPO_ROOT / "config" / "provider_profiles.yaml")
    assert prof_err is None
    argon = prof_doc.get("ide_argon4_routing_policy") or {}
    assert argon.get("interactive_ide_enabled") is True
    assert argon.get("thinking_separation_guaranteed") is True
    assert "executive_summary" in (argon.get("high_reasoning_roles") or [])
    assert "competencies_graph_pool_selector" in (argon.get("medium_reasoning_roles") or [])

    audit_rep = run_eight_pillar_cost_token_audit(REPO_ROOT)
    assert audit_rep["status"] == "PASS"
    assert audit_rep["pillars"][7]["ide_argon4_routing_verified"] is True


def test_storage_hygiene_discovers_outreach_eval_dbs_and_expired_worktree_leases(tmp_path: Path) -> None:
    """Verify full-repo DB discovery across Outreach/Eval/Research and stale lock detection in artifacts/.worktrees."""
    import os
    import sqlite3
    import subprocess
    import time
    from tools.storage_worktree_hygiene import run_six_pillar_hygiene_audit

    sandbox = tmp_path / "full_storage_sandbox"
    (sandbox / "outreach_engine" / "data").mkdir(parents=True)
    (sandbox / "apps_eval" / "state").mkdir(parents=True)
    (sandbox / "resume_graph_engine" / "artifacts" / "apps_rg").mkdir(parents=True)
    (sandbox / ".worktrees" / "abandoned_wt").mkdir(parents=True)
    (sandbox / "automations" / "prompts").mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        (sandbox / "automations" / "prompts" / md_file.name).write_text(
            md_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    subprocess.run(["git", "init", "-b", "main", str(sandbox)], check=True, capture_output=True, timeout=30)

    for db_fp in (
        sandbox / "outreach_engine" / "data" / "outreach_state.sqlite",
        sandbox / "apps_eval" / "state" / "eval_ledger.db",
    ):
        conn = sqlite3.connect(str(db_fp), timeout=10)
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("CREATE TABLE item (id INTEGER PRIMARY KEY);")
        conn.commit()
        conn.close()

    old_ts = time.time() - 95000
    rg_lock = sandbox / "resume_graph_engine" / "artifacts" / "apps_rg" / "stale_build.lock"
    rg_lock.write_text("stale", encoding="utf-8")
    os.utime(rg_lock, (old_ts, old_ts))

    expired_lease = sandbox / ".worktrees" / "abandoned_wt" / ".sidecar_active_run.lock"
    expired_lease.write_text(json.dumps({"pid": 999999, "branch": "chore/old", "started_at": old_ts}), encoding="utf-8")
    os.utime(expired_lease, (old_ts, old_ts))

    pre = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=False)
    discovered_dbs = {d["db"] for d in pre["dbs"]}
    assert "outreach_engine/data/outreach_state.sqlite" in discovered_dbs
    assert "apps_eval/state/eval_ledger.db" in discovered_dbs
    assert "resume_graph_engine/artifacts/apps_rg/stale_build.lock" in pre["stale_files"]
    assert ".worktrees/abandoned_wt/.sidecar_active_run.lock" in pre["stale_files"]
    for inv_key in ("outreach_engine_mb", "resume_engine_mb", "apps_research_mb", "apps_eval_mb", "data_mb", "worktrees_mb"):
        assert inv_key in pre["storage_inventory"]

    post = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=True)
    assert post["status"] == "PASS", post
    assert all(d["journal_mode"] == "wal" for d in post["dbs"])
    assert post["stale_files"] == []


def test_validator_rejects_cron_timestamp_or_routing_mismatch_or_missing_manifest_flag(tmp_path: Path) -> None:
    """Negative control: reject retired cron timestamps, pre-preflight consolidation, and routing drift."""
    fake_repo = tmp_path / "repo"
    prompts_dir = fake_repo / "automations" / "prompts"
    routing_dir = fake_repo / ".agents" / "rules"
    prompts_dir.mkdir(parents=True)
    routing_dir.mkdir(parents=True)

    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        if md_file.name == "agents_storage_worktree_hygiene_agent.md":
            content += "\nLegacy schedule (`05:00 ET`, MODE: scheduled)\n"
        if md_file.name == "agents_ssot_boundary_agent.md":
            content = content.replace("--write-manifest", "--missing-manifest")
        (prompts_dir / md_file.name).write_text(content, encoding="utf-8")

    routing_src = (REPO_ROOT / ".agents" / "rules" / "sidecar-automation-routing.md").read_text(encoding="utf-8")
    (routing_dir / "sidecar-automation-routing.md").write_text(
        routing_src.replace("tools/e2e_functionality_auditor.py", "ops_scripts/run_e2e_authoritative_smoke.py"),
        encoding="utf-8",
    )

    result = validate_sidecar_separation(repo_root=fake_repo, sidecars_root=DEFAULT_SIDECARS_ROOT)
    assert result["status"] == "FAIL"
    joined = "\n".join(result["violations"])
    assert "retains retired daily cron timestamp" in joined
    assert "--write-manifest" in joined
    assert "tools/e2e_functionality_auditor.py" in joined


def test_skills_contract_integrity_and_zero_broken_links() -> None:
    """Verify all 7 skills satisfy the hardened contract with zero broken links or missing script paths."""
    from tools.audit_skills_budget import audit_skills_budget

    rep = audit_skills_budget(REPO_ROOT)
    assert rep["status"] == "PASS", f"audit_skills_budget failed: {rep.get('violations')}"
    assert rep["is_clean"] is True
    assert rep["skill_count"] == 7
    assert rep["violations"] == []
    assert rep["estimated_description_tokens"] <= rep["max_description_tokens"]

    # Verify every skill has a unique description
    descs = [s["description"].lower().strip() for s in rep["skills"]]
    assert len(descs) == len(set(descs)), "Duplicate skill descriptions detected"


def test_skills_auditor_rejects_broken_link_duplicate_desc_and_missing_script(tmp_path: Path) -> None:
    """Negative control: verify audit_skills_budget fails closed on broken links, missing scripts, and duplicates."""
    from tools.audit_skills_budget import audit_skills_budget

    fake_repo = tmp_path / "fake_repo"
    skills_root = fake_repo / ".agents" / "skills"
    skills_root.mkdir(parents=True)

    # 1. Broken link
    s1 = skills_root / "skill-one"
    s1.mkdir()
    (s1 / "SKILL.md").write_text(
        "---\nname: skill-one\ndescription: Unique description one.\n---\n\n"
        "# Skill One\nSee [broken link](missing_file.md)\n",
        encoding="utf-8",
    )

    # 2. Duplicate description & missing script
    s2 = skills_root / "skill-two"
    s2.mkdir()
    (s2 / "SKILL.md").write_text(
        "---\nname: skill-two\ndescription: Unique description one.\n---\n\n"
        "# Skill Two\nRun `python ops_scripts/nonexistent_script.py`\n",
        encoding="utf-8",
    )

    rep = audit_skills_budget(fake_repo)
    assert rep["status"] == "FAIL"
    assert rep["is_clean"] is False
    violations = "\n".join(rep["violations"])
    assert "Broken markdown link target 'missing_file.md'" in violations
    assert "Duplicate description" in violations
    assert "References nonexistent script 'ops_scripts/nonexistent_script.py'" in violations




