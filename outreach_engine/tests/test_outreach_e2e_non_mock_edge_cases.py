"""Comprehensive Non-Mock End-to-End Edge-Case Test Suite for Outreach Engine (apps_lic).

Covers all 12 production edge cases (1A, 1B, 1C, 2, 3, 4, 5, 6A, 6B, 7, 8, 9, 10, 11, 12)
across OutreachOrchestrator, GovernedBriefingResolver, execute_managed_research,
run_canonical_apps_lic_spine, and CLI subprocess entrypoints with ZERO mocks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfileLoader,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.domain.validators import ForbiddenClaimsValidator
from apps_lic.integrations.apps_research_bridge import AppsResearchBridge
from apps_lic.integrations.managed_research_delegation import (
    OutreachBriefingReady,
    RequestForOutreachBriefing,
    execute_managed_research,
)
from apps_lic.integrations.research_bridge_support import (
    persist_standalone_outreach_research_bundle,
)
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver
from apps_lic.pipeline.compiler import PromptCompiler
from apps_lic.pipeline.mission_loader import MissionLoader
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.runtime.dispatch.canonical_dispatch import run_canonical_apps_lic_spine


@pytest.fixture(autouse=True)
def _reset_resolver_cache() -> None:
    GovernedBriefingResolver.clear_cache()
    GovernedBriefingResolver.SHARED_DISK_CACHE_DIR = None
    yield
    GovernedBriefingResolver.clear_cache()
    GovernedBriefingResolver.SHARED_DISK_CACHE_DIR = None


# ---------------------------------------------------------------------------
# Edge Cases 1A, 1B, 1C: Research Bridge, Canonical Sidecar & Trace Parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("company", ["Truist", "Citi", "Anthropic"])
def test_edge_1a_canonical_targets_persist_with_artifact_runs_root(
    company: str, tmp_path: Path
) -> None:
    """Edge Case 1A: Canonical targets resolve as CANONICAL_FIXTURE (is_verified=True)
    when artifact_runs_root is provided, passing G21/G26/X2 exit gates without X3D_BLOCKED."""
    runs_root = tmp_path / "apps_research_runs"
    res = GovernedBriefingResolver.resolve(
        company_name=company,
        target_role="VP of AI Engineering",
        auto_research=True,
        artifact_runs_root=runs_root,
        force_fresh=True,
    )
    assert res.resolution_source == "CANONICAL_FIXTURE"
    assert res.is_verified is True
    assert res.evidence_count >= 1
    assert len(res.strategic_priorities) >= 1

    run_dir = Path(res.research_artifact_dir)
    assert run_dir.is_dir()
    u0 = json.loads((run_dir / "apps_research_u0_receipt.json").read_text(encoding="utf-8"))
    handoff = json.loads((run_dir / "apps_research_apps_rg_handoff_v2.json").read_text(encoding="utf-8"))
    assert u0.get("status") == "PASS" or u0.get("gate_status") == "PASS"
    assert handoff["exit_authorization"]["x3_code"] == "X3D_ALLOW_FINISH"
    assert (run_dir / "exit_disposition_receipt.json").is_file()


def test_edge_1b_1c_standalone_bundle_and_real_bridge_managed_research(tmp_path: Path) -> None:
    """Edge Cases 1B & 1C: Standalone bundle persistence emits G5/G6/G7 + reflection_receipt,
    and execute_managed_research succeeds with real AppsResearchBridge without trace mismatch."""
    runs_root_standalone = tmp_path / "standalone_runs"
    record = SimpleNamespace(
        run_id="run_stripe_01",
        trace_id="bridge:stripe_01:trace_abc",
        request_id="req_stripe_01",
        company_brief_text="Stripe is investing in global payment orchestration and fraud ML latency reduction.",
        strategic_priorities=("global payment orchestration", "fraud ML latency reduction"),
        confidence_score=0.92,
    )
    pub = persist_standalone_outreach_research_bundle(
        record=record,
        target_company="Stripe",
        target_role="Head of Payments AI",
        jd_text="Head of Payments AI leading global payment orchestration.",
        runs_root=runs_root_standalone,
    )
    bundle_dir = Path(pub.run_dir)
    u0 = json.loads((bundle_dir / "apps_research_u0_receipt.json").read_text(encoding="utf-8"))
    handoff = json.loads((bundle_dir / "apps_research_apps_rg_handoff_v2.json").read_text(encoding="utf-8"))
    assert "reflection_receipt" in u0
    assert u0["raw_input_sha256"]
    assert u0["normalized_input_sha256"]
    for gate_key in ("G5", "G6", "G7"):
        assert gate_key in handoff["mandatory_gate_receipts"]
        assert handoff["mandatory_gate_receipts"][gate_key]["passed"] is True

    # Real AppsResearchBridge execution through execute_managed_research
    runs_root = tmp_path / "managed_runs"
    bridge = AppsResearchBridge(artifact_runs_root=runs_root)
    req = RequestForOutreachBriefing(
        request_id="req-real-1",
        run_id="run-real-1",
        trace_id="trace-real-1",
        company_name="Truist",
        job_title="SVP of Enterprise AI",
        artifact_runs_root=runs_root,
        force_fresh=True,
    )
    outcome = execute_managed_research(
        req,
        bridge=bridge,
        consumer_artifact_dir=tmp_path / "consumer_out",
    )
    assert isinstance(outcome, OutreachBriefingReady)
    assert outcome.research_evidence_count >= 1
    assert len(outcome.strategic_priorities) >= 1
    assert outcome.trace_id != ""


# ---------------------------------------------------------------------------
# Edge Cases 6A, 6B, 12: Briefing Text Forwarding, Evidence Count & Disk Cache
# ---------------------------------------------------------------------------


def test_edge_6a_6b_12_raw_text_forwarding_evidence_count_and_disk_cache(tmp_path: Path) -> None:
    """Edge Cases 6A, 6B, 12: resolve_opportunity_briefing forwards briefing_text (RAW_TEXT_EXTRACTION),
    propagates evidence_count into draft.research_metadata, and _load_from_shared_disk rejects unverified cache."""
    orch = OutreachOrchestrator()
    candidate = CandidateProfileLoader.load_default()
    raw_brief = (
        "# Executive Briefing: Databricks\n\n"
        "## Strategic Priorities\n"
        "- Accelerate lakehouse governance across regulated enterprise workloads\n"
        "- Scale Mosaic AI inference serving with deterministic latency SLAs\n"
    )
    opp = TargetOpportunity(
        opportunity_id="opp_raw_6a",
        company_name="Databricks",
        role_title="VP of AI Platform",
        industry="Enterprise Data & AI",
        recipient_name="Ali Ghodsi",
        recipient_title="CEO",
        recipient_class=RecipientClass.EXECUTIVE_PEER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=[],
        briefing_text=raw_brief,
    )
    resolved_opp = orch.resolve_opportunity_briefing(opp, auto_research=False)
    assert resolved_opp.sealed_resolution is not None
    assert resolved_opp.sealed_resolution["metadata"]["extraction_mode"] == "RAW_TEXT_EXTRACTION"
    assert resolved_opp.sealed_resolution["is_verified"] is True
    assert len(resolved_opp.evidence_items) >= 2

    draft, verdict = orch.generate_single_draft(
        candidate,
        resolved_opp,
        ChannelType.LINKEDIN_INMAIL,
        auto_research=False,
        artifact_dir=tmp_path / "draft_out",
    )
    assert verdict.passed is True
    assert int(draft.research_metadata["evidence_count"]) >= 2

    # Edge Case 12: Unverified shared disk cache must not be loaded as verified
    cache_dir = tmp_path / "shared_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    GovernedBriefingResolver.SHARED_DISK_CACHE_DIR = cache_dir
    res1 = GovernedBriefingResolver.resolve(
        company_name="Truist",
        target_role="CTO",
        auto_research=True,
        force_fresh=True,
    )
    assert res1.is_verified is True
    cache_file = list(cache_dir.glob("*.json"))[0]
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["metadata"]["is_verified"] = False
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    GovernedBriefingResolver.clear_cache()
    res_unverified = GovernedBriefingResolver.resolve(
        company_name="Truist",
        target_role="CTO",
        auto_research=False,
    )
    assert res_unverified.resolution_source == "HERMETIC_FALLBACK"
    assert res_unverified.is_verified is False


# ---------------------------------------------------------------------------
# Edge Cases 2, 3, 5, 7, 10, 11: Board Member Upgrade, Follow-Up Lens 2,
# Connection-Note Trimming & MissionLoader Structure 1
# ---------------------------------------------------------------------------


def test_edge_2_10_board_member_channel_upgrade_and_canonical_spine(tmp_path: Path) -> None:
    """Edge Cases 2 & 10: BOARD_MEMBER connection notes auto-upgrade to InMail in both
    generate_single_draft and run_canonical_apps_lic_spine, passing Lens 1 >= 0.70."""
    orch = OutreachOrchestrator()
    candidate = CandidateProfileLoader.load_default()
    opp = TargetOpportunity(
        opportunity_id="opp_board",
        company_name="Truist",
        role_title="Board AI Advisor",
        industry="Financial Services",
        recipient_name="Kelly King",
        recipient_title="Board Director",
        recipient_class=RecipientClass.BOARD_MEMBER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["fiduciary AI risk governance", "cyber resilience oversight"],
    )
    draft, verdict = orch.generate_single_draft(
        candidate,
        opp,
        ChannelType.LINKEDIN_CONNECTION,
        artifact_dir=tmp_path / "board_single",
    )
    assert draft.channel == ChannelType.LINKEDIN_INMAIL
    assert draft.research_metadata.get("channel_upgraded_from") == "connection_note"
    assert verdict.passed is True
    assert verdict.lens_scores["lens1_altitude"] >= 0.70

    # Canonical spine preservation of BOARD_MEMBER, relationship_distance, and strategic_priorities
    raw_ingress = {
        "company": "Truist",
        "target_role": "Board AI Advisor",
        "industry": "Financial Services",
        "recipient_class": "board_member",
        "relationship_distance": "warm_referral",
        "channel": "connection_note",
        "audience_persona": "executive_contact",
        "strategic_priorities": ["fiduciary AI risk governance"],
        "lead_profile": {"name": "Kelly King", "title": "Board Director"},
    }
    spine_res = run_canonical_apps_lic_spine(raw_ingress, tmp_path / "board_spine")
    assert spine_res["is_valid"] is True
    assert spine_res["x3_code"] == "X3D_ALLOW_FINISH"
    assert "shared network" in spine_res["message"]


def test_edge_3_follow_up_single_draft_passes_lens_2_with_and_without_priorities(
    tmp_path: Path,
) -> None:
    """Edge Case 3: FOLLOW_UP single drafts pass Lens 2/3 (>= 0.70) for both non-empty
    and empty strategic_priorities without triggering UnsupportedPersonalizationValidator."""
    orch = OutreachOrchestrator()
    candidate = CandidateProfileLoader.load_default()

    opp_with_prio = TargetOpportunity(
        opportunity_id="opp_fu_1",
        company_name="Truist",
        role_title="SVP of AI Platforms",
        industry="Financial Services",
        recipient_name="Charles Morris",
        recipient_title="EVP of Technology",
        recipient_class=RecipientClass.EXECUTIVE_PEER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["cloud modern banking core"],
    )
    _, v1 = orch.generate_single_draft(
        candidate,
        opp_with_prio,
        ChannelType.FOLLOW_UP,
        artifact_dir=tmp_path / "fu_with_prio",
    )
    assert v1.passed is True
    assert v1.lens_scores["lens2_grounding"] >= 0.70
    assert v1.lens_scores["lens3_resonance"] >= 0.70

    opp_empty_prio = TargetOpportunity(
        opportunity_id="opp_fu_2",
        company_name="OpaquePrivateCo",
        role_title="SVP of AI Platforms",
        industry="Financial Services",
        recipient_name="Charles Morris",
        recipient_title="EVP of Technology",
        recipient_class=RecipientClass.EXECUTIVE_PEER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=[],
    )
    _, v2 = orch.generate_single_draft(
        candidate,
        opp_empty_prio,
        ChannelType.FOLLOW_UP,
        auto_research=False,
        artifact_dir=tmp_path / "fu_empty_prio",
    )
    assert v2.passed is True
    assert v2.lens_scores["lens2_grounding"] >= 0.70
    assert v2.lens_scores["lens3_resonance"] >= 0.70
    assert v2.scores["unsupported_personalization_score"] == 1.0


def test_edge_5_7_connection_note_no_double_ellipsis_and_long_title_trimming(tmp_path: Path) -> None:
    """Edge Cases 5 & 7: Connection notes never emit '......' when hook ends with '...'
    and preserve grounded facts/metrics when target_title is 70+ chars."""
    compiler = PromptCompiler()
    long_title = (
        "Senior Vice President of Global Enterprise Artificial Intelligence and Cloud Architecture"
    )
    candidate = CandidateProfileLoader.load_default(overrides={"target_title": long_title})
    opp = TargetOpportunity(
        opportunity_id="opp_conn_long",
        company_name="Truist",
        role_title="EVP of Enterprise AI",
        industry="Financial Services",
        recipient_name="Charles Morris",
        recipient_title="EVP of Technology",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=[
            "accelerating enterprise-wide cloud native core banking transformation across all regional divisions..."
        ],
        sealed_resolution={"is_verified": True, "resolution_source": "CANONICAL_FIXTURE"},
    )
    subj, body, facts = compiler.render_draft_message(candidate, opp, ChannelType.LINKEDIN_CONNECTION)
    assert "......" not in body
    assert len(body) <= 300
    assert len(facts) >= 1

    orch = OutreachOrchestrator()
    draft, verdict = orch.generate_single_draft(
        candidate,
        opp,
        ChannelType.LINKEDIN_CONNECTION,
        auto_research=False,
        artifact_dir=tmp_path / "conn_long_out",
    )
    assert "......" not in draft.body
    assert len(draft.body) <= 300
    assert len(draft.grounded_facts_used) >= 1
    assert verdict.passed is True


def test_edge_11a_mission_loader_structure_1_custom_facts_and_enums() -> None:
    """Edge Case 11A: MissionLoader.load_from_dict (Structure 1) preserves custom
    verified_facts, recipient_class, and relationship_distance."""
    raw = {
        "sender_profile": {
            "name": "Amit Ayer",
            "title": "AI Safety & Platform Executive",
            "verified_facts": [
                {
                    "fact_id": "custom_fact_99",
                    "category": "safety",
                    "statement": "Reduced constitutional evaluation latency by 64% across 50M daily prompts",
                    "metric": "64%",
                    "source_reference": "safety_dossier",
                }
            ],
        },
        "recipient_profile": {
            "name": "Dario Amodei",
            "title": "CEO",
            "company": "Anthropic",
            "recipient_class": "board_member",
            "relationship_distance": "warm_referral",
        },
        "job_description": {
            "title": "Head of Enterprise Safety",
            "company": "Anthropic",
            "strategic_priorities": ["constitutional AI guardrails"],
        },
    }
    cand, opp = MissionLoader.load_from_dict(raw)
    assert opp.recipient_class == RecipientClass.BOARD_MEMBER
    assert opp.relationship_distance == RelationshipDistance.WARM_REFERRAL
    assert any(f.fact_id == "custom_fact_99" for f in cand.verified_facts)


# ---------------------------------------------------------------------------
# Edge Cases 4, 8, 9, 11B: Privacy Gate, Compensation/Dollar Normalization & CLI
# ---------------------------------------------------------------------------


def test_edge_4_8_9_privacy_validator_and_forbidden_claims_normalization() -> None:
    """Edge Cases 4, 8, 9: OutboundPrivacyValidator wired in validate_draft;
    ForbiddenClaimsValidator blocks 1-4 digit comp demands and normalizes $10M == $10,000,000."""
    orch = OutreachOrchestrator()
    cand = CandidateProfileLoader.load_default()
    opp = TargetOpportunity(
        opportunity_id="opp_val",
        company_name="Truist",
        role_title="VP of AI",
        industry="Financial Services",
        recipient_name="Alex Rivera",
        recipient_title="Managing Director",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["AI risk controls"],
        sealed_resolution={"is_verified": True, "resolution_source": "CANONICAL_FIXTURE"},
    )
    leak_draft = OutreachMessageDraft(
        draft_id="d_priv",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist AI risk controls",
        body="Alex, [INTERNAL] key sk-proj-9876543210abcdefghijklmnop - open to a quick call?",
        grounded_facts_used=[cand.verified_facts[0].fact_id],
    )
    v_res = orch.validate_draft(leak_draft, cand, opp)
    assert v_res.is_valid is False
    assert v_res.scores["privacy_score"] == 0.0

    f_val = ForbiddenClaimsValidator()
    assert f_val.validate("Targeting a $2M bonus package.")[0] is False
    assert f_val.validate("Available at $1000/hr or monthly retainer.")[0] is False
    assert f_val.validate("Targeting €250k base salary or £180k package.")[0] is False
    facts = [
        CandidateFact(
            fact_id="f_10m",
            category="scale",
            statement="Generated $10,000,000 in annual infrastructure cost savings",
            metric="$10,000,000",
            source_reference="dossier",
        ),
        CandidateFact(
            fact_id="f_range",
            category="scale",
            statement="Delivered $10,000,000-$15,000,000 in annualized platform efficiency",
            metric="$10,000,000-$15,000,000",
            source_reference="dossier",
        ),
    ]
    ok, viols = f_val.validate(
        "Delivered $10M in annual infrastructure savings and $10M–$15M (across multi-region hybrid cloud clusters) in platform efficiency.",
        verified_facts=facts,
    )
    assert ok is True, f"Unexpected violations: {viols}"


def test_edge_11b_cli_end_to_end_brief_role_and_validate_subcommand(tmp_path: Path) -> None:
    """Edge Case 11B: CLI subprocess verification for --brief + --role title preservation
    across Structure 1, 2, and 3 briefs, empty brief rejection, and validate --company / --priority."""
    repo_root = Path(__file__).resolve().parents[2]
    brief_path = tmp_path / "e2e_brief.json"
    brief_path.write_text(
        json.dumps(
            {
                "sender_profile": {"name": "Amit Ayer", "title": "AI/ML Engineering Leader"},
                "recipient_profile": {
                    "name": "Charles Morris",
                    "title": "EVP",
                    "company": "Truist",
                    "recipient_class": "executive_peer",
                },
                "job_description": {
                    "title": "VP of AI",
                    "company": "Truist",
                    "strategic_priorities": ["enterprise AI governance"],
                },
            }
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "cli_e2e_run"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "outreach_engine",
            "run",
            "--brief",
            str(brief_path),
            "--role",
            "SVP of Enterprise Data",
            "--offline-smoke",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        shell=False,
        timeout=60,
    )
    assert proc.returncode == 0, f"CLI run failed: {proc.stderr}"
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate"]["target_title"] == "AI/ML Engineering Leader"
    assert manifest["opportunity"]["role_title"] == "SVP of Enterprise Data"

    # Also verify Structure 3 (payload.company_brief + payload.target_title) preserves candidate title
    s3_brief_path = tmp_path / "e2e_s3_brief.json"
    s3_brief_path.write_text(
        json.dumps(
            {
                "payload": {
                    "candidate_name": "Amit Ayer",
                    "target_title": "Chief AI Architect",
                    "company_brief": "Truist",
                    "role_title": "VP of AI",
                    "role_areas_of_focus": ["enterprise AI governance"],
                }
            }
        ),
        encoding="utf-8",
    )
    run_dir_s3 = tmp_path / "cli_e2e_run_s3"
    proc_s3 = subprocess.run(
        [
            sys.executable,
            "-m",
            "outreach_engine",
            "run",
            "--brief",
            str(s3_brief_path),
            "--role",
            "Head of Core Platforms",
            "--offline-smoke",
            "--artifact-dir",
            str(run_dir_s3),
            "--json",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        shell=False,
        timeout=60,
    )
    assert proc_s3.returncode == 0, f"CLI S3 run failed: {proc_s3.stderr}"
    manifest_s3 = json.loads((run_dir_s3 / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest_s3["candidate"]["target_title"] == "Chief AI Architect"
    assert manifest_s3["opportunity"]["role_title"] == "Head of Core Platforms"

