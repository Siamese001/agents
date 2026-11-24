"""CLI subcommand handlers for eval, show, and validate in apps_lic."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from apps_lic.cli_subcommands.parser_and_run import _emit_error
from apps_lic.domain.models import (
    AudiencePersona, CandidateFact, CandidateProfile, CandidateProfileLoader,
    ChannelType, OutreachMessageDraft, RecipientClass, RelationshipDistance, TargetOpportunity,
)
from apps_lic.pipeline.orchestrator import OutreachOrchestrator

_log = logging.getLogger(__name__)


def _reconstruct_eval_draft(run_dir: Path, manifest_data: dict[str, Any] | None = None) -> OutreachMessageDraft | None:
    m_ch = manifest_data.get("channel") if manifest_data else None
    m_persona = manifest_data.get("audience_persona") if manifest_data else None
    raw_facts = manifest_data.get("grounded_facts_used") if manifest_data else None
    m_facts = list(raw_facts) if isinstance(raw_facts, (list, tuple, set)) else []

    draft_file = run_dir / "outreach_draft.json"
    if draft_file.is_file():
        try:
            d = json.loads(draft_file.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                ch_raw = d.get("channel") or m_ch
                if ch_raw in ChannelType._value2member_map_:
                    persona_raw = d.get("audience_persona") or m_persona
                    persona = AudiencePersona.EXECUTIVE_RECRUITER if persona_raw in ("recruiter", "executive_recruiter", AudiencePersona.EXECUTIVE_RECRUITER.value) else AudiencePersona.EXECUTIVE_CONTACT
                    return OutreachMessageDraft(
                        draft_id=d.get("draft_id", "draft_eval"), channel=ChannelType(ch_raw),
                        subject=d.get("subject", ""), body=d.get("body", ""),
                        signature_block=d.get("signature_block", ""), audience_persona=persona,
                        grounded_facts_used=list(d.get("grounded_facts_used") or []),
                        research_metadata=dict(d.get("research_metadata") or {}),
                        metadata=dict(d.get("metadata") or {}),
                    )
            else:
                _log.warning("Ignoring non-object outreach_draft.json in %s", run_dir)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            _log.warning("Failed parsing outreach_draft.json in %s: %s", run_dir, exc)

    draft_md = run_dir / "outreach_draft.md"
    if draft_md.is_file():
        try:
            md_text = draft_md.read_text(encoding="utf-8")
            hm = re.search(r"^#\s+Outreach Draft:\s*([A-Za-z_]+)", md_text, re.MULTILINE)
            ch_raw = (hm.group(1).lower() if hm else None) or m_ch
            if ch_raw in ChannelType._value2member_map_:
                subj = next((l.split(":", 1)[1].strip() for l in md_text.splitlines() if l.startswith(("**Subject**:", "Subject:"))), "")
                bm = re.search(r"```text\s*\n(.*?)\n```", md_text, re.DOTALL)
                persona = AudiencePersona.EXECUTIVE_RECRUITER if m_persona in ("recruiter", "executive_recruiter", AudiencePersona.EXECUTIVE_RECRUITER.value) else AudiencePersona.EXECUTIVE_CONTACT
                return OutreachMessageDraft(
                    draft_id="draft_from_md", channel=ChannelType(ch_raw), subject=subj,
                    body=bm.group(1).strip() if bm else md_text.strip(),
                    grounded_facts_used=m_facts, audience_persona=persona,
                )
        except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
            _log.warning("Failed parsing outreach_draft.md in %s: %s", run_dir, exc)
    return None


def _reconstruct_eval_context(manifest_file: Path) -> tuple[CandidateProfile, TargetOpportunity]:
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Authentic saved context '{manifest_file.name}' not found")
    m = json.loads(manifest_file.read_text(encoding="utf-8"))
    cdata, odata = m.get("candidate"), m.get("opportunity")
    if not isinstance(cdata, dict) or not isinstance(odata, dict):
        raise ValueError(f"Corrupt manifest '{manifest_file.name}'")

    facts = [
        CandidateFact(fact_id=f["fact_id"], category=f.get("category", "general"), statement=f.get("statement", ""), metric=f.get("metric"), source_reference=f.get("source_reference"))
        for f in (cdata.get("verified_facts") or []) if isinstance(f, dict) and "fact_id" in f
    ]
    cand = CandidateProfile(
        candidate_id=cdata.get("candidate_id", ""), full_name=cdata.get("full_name", ""),
        target_title=cdata.get("target_title", ""), current_title=cdata.get("current_title", ""),
        executive_summary=cdata.get("executive_summary", ""), verified_facts=facts,
        key_competencies=list(cdata.get("key_competencies") or []), linkedin_url=cdata.get("linkedin_url", ""), phone=cdata.get("phone", ""),
    )
    rc_raw, rd_raw = odata.get("recipient_class"), odata.get("relationship_distance")
    rc = RecipientClass(rc_raw) if rc_raw in RecipientClass._value2member_map_ else RecipientClass.HIRING_MANAGER
    rd = RelationshipDistance(rd_raw) if rd_raw in RelationshipDistance._value2member_map_ else RelationshipDistance.COLD
    opp = TargetOpportunity(
        opportunity_id=odata.get("opportunity_id", ""), company_name=odata.get("company_name", ""),
        role_title=odata.get("role_title", ""), industry=odata.get("industry", ""),
        recipient_name=odata.get("recipient_name", ""), recipient_title=odata.get("recipient_title", ""),
        recipient_class=rc, relationship_distance=rd, strategic_priorities=list(odata.get("strategic_priorities") or []),
        briefing_text=odata.get("briefing_text", ""), research_digest=odata.get("research_digest", ""),
        evidence_items=list(odata.get("evidence_items") or []), sealed_resolution=odata.get("sealed_resolution"),
    )
    return cand, opp


def _handle_eval(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        return _emit_error(args, f"Run directory does not exist: {run_dir}")
    manifest_file = run_dir / "run_manifest.json"
    if not manifest_file.is_file():
        return _emit_error(args, f"Authentic saved context 'run_manifest.json' not found in: {run_dir}")

    try:
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        candidate, opportunity = _reconstruct_eval_context(manifest_file)
    except Exception as exc:
        return _emit_error(args, f"Failed to reconstruct authentic saved context from 'run_manifest.json': {exc}")

    draft = _reconstruct_eval_draft(run_dir, manifest_data=manifest_data)
    if draft is None:
        return _emit_error(args, f"Neither outreach_draft.json nor outreach_draft.md found or readable in: {run_dir}")

    try:
        orchestrator = OutreachOrchestrator()
        verdict = orchestrator.evaluate_authoritative_draft(draft, candidate, opportunity, artifact_dir=None)
        eval_report = orchestrator.judge.report_from_verdict(verdict)
    except Exception as exc:
        return _emit_error(args, f"Evaluation execution error: {exc}")
    val_dict = {
        "status": verdict.status, "is_valid": verdict.is_valid, "violations": verdict.violations,
        "warnings": verdict.warnings, "failure_reasons": verdict.failure_reasons, "scores": verdict.scores,
    }
    from infrastructure.config.env_loader import get_env_str

    overall_passed = verdict.passed
    if (
        getattr(args, "record_flywheel", True)
        and "pytest" not in sys.modules
        and not get_env_str("PYTEST_CURRENT_TEST")
    ):
        try:
            from agents.observability.eval_flywheel import EvalFlywheelEngine

            EvalFlywheelEngine().ingest_product_run(
                app_id="apps_lic",
                run_id=run_dir.name,
                x3_disposition="X3D_ALLOW_FINISH" if overall_passed else "X3B_ESCALATE_HITL",
                passed=overall_passed,
                failure_reasons=[str(r) for r in (verdict.failure_reasons or verdict.violations or ())],
                score=float(getattr(eval_report, "composite_score", 1.0 if overall_passed else 0.0)),
            )
        except (ImportError, OSError, ValueError, RuntimeError):  # guardian: allow-silent-swallow -- observer-only flywheel hook must never fail outreach eval
            pass

    if args.json:
        print(json.dumps({
            "status": "PASSED" if overall_passed else "FAILED", "is_valid": verdict.is_valid,
            "evaluation": eval_report.to_dict(), "validation": val_dict,
        }, indent=2))
        return 0 if overall_passed else 1

    print("\n" + "=" * 60 + f"\nLIVE EVALUATION REPORT FOR RUN: {run_dir.name}\n" + "=" * 60)
    print(f"Validation Status: {'PASSED' if verdict.is_valid else 'FAILED'}")
    if verdict.violations:
        print(f"Validation Violations: {verdict.violations}")
    print(f"Rubric Judge Status: {'PASSED' if eval_report.passed else 'FAILED'} (Composite: {eval_report.composite_score:.2f} [{eval_report.score_band}])")
    for k, v in eval_report.lens_scores.items():
        print(f"  - {k}: {v:.2f}")
    if eval_report.feedback:
        print(f"Feedback: {eval_report.feedback}")
    if eval_report.remediation_hints:
        print(f"Remediation Hints: {eval_report.remediation_hints}")
    print("=" * 60)
    return 0 if overall_passed else 1


def _handle_show(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        return _emit_error(args, f"Run directory does not exist: {run_dir}")

    is_json = getattr(args, "json", False)
    artifact_map = {
        "draft": ["outreach_draft.json", "outreach_draft.md"] if is_json else ["outreach_draft.md", "outreach_draft.json"],
        "campaign": ["campaign_sequence.json"], "evaluation": ["evaluation_report.json"], "validation": ["validation_report.json"],
        "research": ["apps_research/runs/*/company_brief.json", "apps_research/runs/*/company_brief.md"] if is_json else ["apps_research/runs/*/company_brief.md", "apps_research/runs/*/company_brief.json"],
        "manifest": ["run_manifest.json"], "receipt": ["run_receipt.json"],
        "bundle": ["outreach_sequence_bundle.json"],
        "review": ["outreach_sequence_review.md"],
        "csv": ["crm_sequence_import.csv"],
        "docx": ["executive_outreach_packet.docx"],
    }
    target_file = None
    for pattern in artifact_map.get(args.artifact, []):
        matches = list(run_dir.glob(pattern)) if "*" in pattern else [run_dir / pattern]
        for p in matches:
            if p.is_file():
                target_file = p
                break
        if target_file:
            break

    if not target_file or not target_file.is_file():
        return _emit_error(args, f"Artifact '{args.artifact}' was not found in: {run_dir}")

    if target_file.suffix.lower() == ".docx":
        payload = {
            "artifact": args.artifact,
            "file": target_file.name,
            "path": target_file.as_posix(),
            "size_bytes": target_file.stat().st_size,
        }
        if is_json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"{target_file.as_posix()} ({payload['size_bytes']} bytes)")
        return 0

    try:
        content = target_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return _emit_error(args, f"Failed reading artifact file '{target_file}': {exc}")
    if is_json and not target_file.name.endswith(".json"):
        print(json.dumps({"artifact": args.artifact, "file": target_file.name, "content": content}, indent=2))
    else:
        print(content)
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    body = str(getattr(args, "body", "") or "").strip()
    subject = str(getattr(args, "subject", "") or "").strip()
    draft_file = getattr(args, "draft_file", None)
    if not body:
        if draft_file == "-" or (not draft_file and not sys.stdin.isatty()):
            try:
                raw_d = sys.stdin.read().strip()
                if raw_d.startswith("{"):
                    try:
                        loaded_d = json.loads(raw_d)
                        if isinstance(loaded_d, dict):
                            body = str(loaded_d.get("body") or "").strip()
                            subject = subject or str(loaded_d.get("subject") or "").strip()
                        else:
                            body = raw_d
                    except json.JSONDecodeError:
                        body = raw_d
                else:
                    body = raw_d
            except Exception as exc:
                return _emit_error(args, f"Failed reading from stdin: {exc}")
        elif draft_file:
            p = Path(draft_file)
            if not p.is_file():
                return _emit_error(args, f"Draft file not found: {draft_file}")
            try:
                raw_d = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                return _emit_error(args, f"Failed reading draft file '{draft_file}': {exc}")
            if p.suffix.lower() == ".json":
                try:
                    loaded_d = json.loads(raw_d)
                    if isinstance(loaded_d, dict):
                        body = str(loaded_d.get("body") or "").strip()
                        subject = subject or str(loaded_d.get("subject") or "").strip()
                    else:
                        body = raw_d.strip()
                except json.JSONDecodeError:
                    body = raw_d.strip()
            else:
                body = raw_d.strip()
    if not body:
        return _emit_error(args, "No draft body provided (--body or --file required).")

    candidate = CandidateProfileLoader.load_default()
    priorities = [str(p).strip() for p in (getattr(args, "priorities", None) or []) if str(p).strip()]
    is_unverified = bool(getattr(args, "unverified", False))
    company = str(getattr(args, "company", None) or "Target Company").strip()
    role = str(getattr(args, "role", None) or "Engineering Leader").strip()
    opportunity = TargetOpportunity(
        opportunity_id="opp_validate", company_name=company, role_title=role, industry="Enterprise Technology",
        recipient_name="Hiring Leader", recipient_title=f"Head of {role}", recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD, strategic_priorities=priorities,
        briefing_text="UNVERIFIED OFFLINE FALLBACK" if is_unverified else f"Target Company: {company}",
        sealed_resolution={"is_verified": not is_unverified, "resolution_source": "HERMETIC_FALLBACK" if is_unverified else "MANUAL"},
    )
    channel = ChannelType(getattr(args, "channel", "inmail"))
    draft = OutreachMessageDraft(
        draft_id="draft_cli_validate", channel=channel, subject=subject, body=body,
        grounded_facts_used=[f.fact_id for f in candidate.verified_facts],
    )
    orchestrator = OutreachOrchestrator()
    verdict = orchestrator.evaluate_authoritative_draft(draft, candidate, opportunity)
    payload = {
        "status": verdict.status, "passed": verdict.passed, "is_valid": verdict.is_valid,
        "company": company, "strategic_priorities": priorities, "violations": verdict.violations,
        "warnings": verdict.warnings, "failure_reasons": verdict.failure_reasons,
        "scores": verdict.scores, "lens_scores": verdict.lens_scores,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print(f"Validation Status: {verdict.status} (passed={verdict.passed})")
        if verdict.violations:
            print(f"Violations: {verdict.violations}")
    return 0 if verdict.passed else 1


__all__ = [
    "_handle_eval",
    "_handle_show",
    "_handle_validate",
    "_reconstruct_eval_context",
    "_reconstruct_eval_draft",
]
