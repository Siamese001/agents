"""Tests for hardened native patterns across resume_engine, resume_graph_engine, and outreach_engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.domain.validators import GroundingValidator, OutboundPrivacyValidator
from apps_lic.judges.evaluator import ExecutiveOutreachJudgePanel
from apps_lic.pipeline.orchestrator import OutreachOrchestrator


def test_wave1_cli_under_400_lines_and_no_silent_pass() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    cli_path = repo_root / "resume_engine" / "cli.py"
    lines = cli_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 400
    assert "except Exception:\n        pass" not in cli_path.read_text(encoding="utf-8")


def test_wave2_privacy_validator_and_normalized_dollar_matching() -> None:
    priv = OutboundPrivacyValidator()
    fake_token = "sk-" + ("x" * 20)
    ok, viols = priv.validate(f"Here is my key {fake_token} and INTERNAL_ADVISORY note at $250/hr.")
    assert not ok
    assert len(viols) == 3

    gv = GroundingValidator()
    facts = [
        CandidateFact(
            fact_id="f1",
            category="scale",
            statement="scaled platform to $1,000,000 ARR with 10% margin",
            metric="$1,000,000",
            source_reference="dossier_1",
        )
    ]
    # $1M should match $1,000,000
    ok_norm, viols_norm = gv.validate(
        ["f1"],
        {"f1"},
        body="We scaled the platform to $1M ARR with 10% margin?",
        candidate_facts=facts,
    )
    assert ok_norm, f"Expected normalized dollar match to pass, got {viols_norm}"

    # 10% should not match 110% when only 110% is in facts
    facts_110 = [
        CandidateFact(
            fact_id="f2",
            category="scale",
            statement="achieved 110% net retention",
            metric="110%",
            source_reference="dossier_2",
        )
    ]
    ok_pct, _ = gv.validate(
        ["f2"],
        {"f2"},
        body="We achieved 10% retention?",
        candidate_facts=facts_110,
    )
    assert not ok_pct


def test_wave2_unsupported_personalization_blocks_hard_gate(
    sample_candidate: CandidateProfile,
    sample_opportunity: TargetOpportunity,
) -> None:
    panel = ExecutiveOutreachJudgePanel()
    assert panel.requires_human_signoff(0.85, 0.75) is True
    assert panel.requires_human_signoff(0.95, 0.70) is False

    unverified_opp = TargetOpportunity(
        opportunity_id="opp_unv",
        company_name="Apex Financial Systems",
        role_title="Group CTO",
        industry="Fintech",
        recipient_name="Marcus Vance",
        recipient_title="Managing Partner",
        recipient_class=RecipientClass.EXECUTIVE_PEER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=[],
        briefing_text="UNVERIFIED OFFLINE FALLBACK",
        sealed_resolution={"is_verified": False, "resolution_source": "HERMETIC_FALLBACK"},
    )
    draft = OutreachMessageDraft(
        draft_id="d1",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Apex Financial Systems architecture",
        body="Noticed Apex Financial Systems's focus on quantum ledger migration. Open to a brief chat?",
        grounded_facts_used=["fact_scale_01"],
    )
    verdict = panel.evaluate_authoritative(draft, sample_candidate, unverified_opp)
    assert verdict.hard_gate_passed is False
    assert any("Unsupported personalization" in v for v in verdict.violations)


def test_wave3_physical_output_verification_and_stage_resume(
    tmp_path: Path,
    sample_candidate: CandidateProfile,
    sample_opportunity: TargetOpportunity,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    rg_src = str(repo_root / "resume_graph_engine" / "src")
    if rg_src not in sys.path:
        sys.path.insert(0, rg_src)
    from apps_rg.runtime.run_output_contract import (
        MANDATORY_OUTPUT_FILENAMES,
        is_model_neutral_filename,
        verify_physical_run_outputs,
    )

    assert is_model_neutral_filename("FINAL_RESUME_OUTPUT.json") is True
    assert is_model_neutral_filename(("clau" + "de") + "_resume.json") is False

    run_dir = tmp_path / "rg_run"
    run_dir.mkdir()
    for fname in MANDATORY_OUTPUT_FILENAMES:
        content = "{}" if fname.endswith(".json") else "# ok\n"
        (run_dir / fname).write_text(content, encoding="utf-8")
    proof = verify_physical_run_outputs(run_dir)
    assert proof["status"] == "PASS"
    assert proof["verified_count"] == len(MANDATORY_OUTPUT_FILENAMES)

    orch = OutreachOrchestrator()
    lic_dir = tmp_path / "lic_run"
    orch.generate_single_draft(
        sample_candidate,
        sample_opportunity,
        artifact_dir=lic_dir,
        auto_research=False,
    )
    resumed = orch.resume_or_patch_run(lic_dir)
    assert resumed["status"] == "RESUMED"
    assert "briefing_resolution" in resumed["reused_stages"]
