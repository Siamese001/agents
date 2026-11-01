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
