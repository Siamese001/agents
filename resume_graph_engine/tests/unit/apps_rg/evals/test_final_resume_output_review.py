from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.evals.owner_solo.final_resume_output_review import (
    FinalResumeOutputReviewError,
    REVIEW_UNIT_OUTPUT,
    REVIEW_UNIT_SECTION,
    append_reviews,
    load_final_resume_output_bundle,
    render_html,
    selected_rationale,
    unreviewed,
    write_progress_receipt,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_completed_run(tmp_path: Path) -> Path:
    root = tmp_path / "completed_run"
    final_path = root / "modular_r4/final_resume_assembly/final_resume.json"
    final_path.parent.mkdir(parents=True)
    invariant_values = {
        "company_names": ["Unify Consulting", "IBM", "InsurTech", "EY", "Early Career"],
        "titles": ["SVP Engineering", "Partner", "CTO", "Principal", "Consultant"],
        "locations": ["Boca Raton, FL", "NY", "NY", "NY", "PA"],
        "dates": [
            {"start_date": "2023-02", "end_date": "present", "is_current": True}
        ]
        * 5,
    }
    final_resume = {
        "locked_copy_invariants": {
            key: {"copied_text_exact": json.dumps(value)}
            for key, value in invariant_values.items()
        },
        "sections": [
            {
                "section_id": "headline",
                "l2_output_snapshot": {"headline_line": "Applied AI platform leader"},
            },
            {
                "section_id": "executive_summary",
                "l2_output_snapshot": {
                    "resume_display_text": "Leads applied AI systems for enterprise buyers."
                },
            },
            {
                "section_id": "competencies",
                "l2_output_snapshot": {
                    "resume_display_text": "AI Platforms: governed agentic systems"
                },
            },
            {
                "section_id": "unify_narrative",
                "l2_output_snapshot": {"narrative_sentence": "Leads platform delivery."},
            },
            {
                "section_id": "unify_bullets",
                "l2_output_snapshot": {
                    "bullets": [
                        {"text": "Built an enterprise AI platform."},
                        {"bullet_text": "Scaled partner adoption."},
                    ]
                },
            },
            {
                "section_id": "ibm_narrative",
                "l2_output_snapshot": {
                    "narrative_sentence": "Led strategic AI alliances."
                },
            },
            {
                "section_id": "ibm_bullets",
                "l2_output_snapshot": {
                    "bullets": [{"bullet_text": "Built cloud data platforms."}]
                },
            },
            {
                "section_id": "insurtech_narrative",
                "l2_output_snapshot": {
                    "narrative_sentence": "Modernized insurance technology platforms."
                },
            },
            {
                "section_id": "insurtech_bullets",
                "l2_output_snapshot": {
                    "bullets": [{"bullet_text": "Launched cloud claims workflows."}]
                },
            },
            {
                "section_id": "ey_narrative",
                "l2_output_snapshot": {
                    "narrative_sentence": "Advised enterprise risk leaders."
                },
            },
            {
                "section_id": "ey_bullets",
                "l2_output_snapshot": {
                    "bullets": [{"bullet_text": "Delivered risk analytics programs."}]
                },
            },
        ],
    }
    final_path.write_text(json.dumps(final_resume), encoding="utf-8")
    rendered = root / "FINAL_RESUME_OUTPUT.txt"
    rendered.write_text(
        (
            "Candidate\n"
            "candidate@example.com\n\n"
            "HEADLINE\n"
            "Applied AI platform leader\n\n"
            "EXECUTIVE SUMMARY\n"
            "Leads applied AI systems for enterprise buyers.\n\n"
            "ENGINEERING & PLATFORM COMPETENCIES\n"
            "AI Platforms: governed agentic systems\n\n"
            "PROFESSIONAL EXPERIENCE\n\n"
            "Unify Consulting — SVP Engineering\n"
            "Boca Raton, FL | Feb 2023 – Present\n"
            "Leads platform delivery.\n"
            "• Built an enterprise AI platform.\n"
            "• Scaled partner adoption.\n\n"
            "IBM — Partner\n"
            "NY | Apr 2017 – Oct 2022\n"
            "Led strategic AI alliances.\n"
            "• Built cloud data platforms.\n\n"
            "InsurTech — CTO\n"
            "NY | Apr 2014 – Mar 2017\n"
            "Modernized insurance technology platforms.\n"
            "• Launched cloud claims workflows.\n\n"
            "EY — Principal\n"
            "NY | Oct 2009 – Mar 2014\n"
            "Advised enterprise risk leaders.\n"
            "• Delivered risk analytics programs.\n\n"
            "Early Career — Consultant\n"
            "PA | Oct 2002 – Sep 2009\n"
            "• Built quantitative models.\n\n"
            "EDUCATION\n"
            "Example University\n\n"
            "CERTIFICATIONS & CREDENTIALS\n"
            "Example Credential\n"
        ),
        encoding="utf-8",
    )
    (root / "job.txt").write_text(
        "Lead applied AI platform partnerships and enterprise adoption.",
        encoding="utf-8",
    )
    (root / "research_bridge_request.json").write_text(
        json.dumps(
            {
                "company_name": "Anthropic",
                "job_title": "Partnerships Lead",
                "job_description_ref": "job.txt",
            }
        ),
        encoding="utf-8",
    )
    contract = {
        "schema_version": "apps_rg.final_resume_output.v1",
        "status": "PASS",
        "final_resume_json": {
            "exists": True,
            "relpath": "modular_r4/final_resume_assembly/final_resume.json",
            "sha256": _sha(final_path),
        },
        "rendered_resume_text": {
            "exists": True,
            "relpath": "FINAL_RESUME_OUTPUT.txt",
            "sha256": _sha(rendered),
        },
        "gates": [
            {"gate_id": "final_resume_no_gap_markers", "pass": True},
            {"gate_id": "other", "pass": True},
        ],
    }
    (root / "FINAL_RESUME_OUTPUT.json").write_text(
        json.dumps(contract), encoding="utf-8"
    )
    return root


def test_default_loads_six_complete_rendered_resume_sections(tmp_path: Path) -> None:
    bundle = load_final_resume_output_bundle(_write_completed_run(tmp_path), repo_root=tmp_path)
    assert bundle["review_unit"] == REVIEW_UNIT_SECTION
    assert [candidate["display_label"] for candidate in bundle["candidates"]] == [
        "Top of Résumé — Headline & Executive Summary",
        "Engineering & Platform Competencies",
        "Unify Consulting — Experience",
        "IBM — Experience",
        "InsurTech Cloud Solutions — Experience",
        "Ernst & Young — Experience",
    ]
    assert len(bundle["candidates"]) == 6
    unify = bundle["candidates"][2]
    assert unify["unit_type"] == "complete_resume_section"
    assert unify["final_text"] == unify["section_context"]
    assert "Unify Consulting — SVP Engineering" in unify["final_text"]
    assert "• Built an enterprise AI platform." in unify["final_text"]
    assert "• Scaled partner adoption." in unify["final_text"]
    assert bundle["target"]["company"] == "Anthropic"


def test_legacy_output_unit_mode_keeps_exact_finished_bullets(tmp_path: Path) -> None:
    bundle = load_final_resume_output_bundle(
        _write_completed_run(tmp_path),
        repo_root=tmp_path,
        review_unit=REVIEW_UNIT_OUTPUT,
    )
    unify_bullets = [
        candidate
        for candidate in bundle["candidates"]
        if candidate["section_id"] == "unify_bullets"
    ]
    assert len(unify_bullets) == 2
    assert unify_bullets[0]["final_text"] == "• Built an enterprise AI platform."
    assert "Unify Consulting — SVP Engineering" in unify_bullets[0]["section_context"]
    assert "• Scaled partner adoption." in unify_bullets[0]["section_context"]
    assert bundle["target"]["company"] == "Anthropic"


def test_rejects_nonpassing_final_output(tmp_path: Path) -> None:
    root = _write_completed_run(tmp_path)
    manifest = root / "FINAL_RESUME_OUTPUT.json"
    contract = json.loads(manifest.read_text(encoding="utf-8"))
    contract["status"] = "FAIL"
    manifest.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(FinalResumeOutputReviewError, match="not a completed final résumé output"):
        load_final_resume_output_bundle(root, repo_root=tmp_path)


def test_rejects_contract_digest_mismatch(tmp_path: Path) -> None:
    root = _write_completed_run(tmp_path)
    (root / "FINAL_RESUME_OUTPUT.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(FinalResumeOutputReviewError, match="digest"):
        load_final_resume_output_bundle(root, repo_root=tmp_path)


def test_html_shows_final_text_and_context_not_graph_material(tmp_path: Path) -> None:
    bundle = load_final_resume_output_bundle(_write_completed_run(tmp_path), repo_root=tmp_path)
    section = next(
        candidate
        for candidate in bundle["candidates"]
        if candidate["section_id"] == "unify_experience"
    )
    page = render_html(bundle, [section], completed=0)
    assert "Complete final résumé section to rate" in page
    assert "Whole résumé section for context" not in page
    assert "Built an enterprise AI platform" in page
    assert "Scaled partner adoption" in page
    assert "Job description used for this résumé</summary><pre>" in page
    assert page.count('name="grade_1"') == 4
    assert "graph_evidence_cluster" not in page
    assert "Similarity" not in page


def test_append_only_final_output_events_and_progress(tmp_path: Path) -> None:
    bundle = load_final_resume_output_bundle(_write_completed_run(tmp_path), repo_root=tmp_path)
    ledger = tmp_path / "events.jsonl"
    candidate = bundle["candidates"][0]
    events = append_reviews(
        ledger,
        bundle,
        [
            {
                "unit_ref": candidate["unit_ref"],
                "grade": 3,
                "rationale": "Strong fit; keep as written",
            }
        ],
    )
    assert events[0]["retrieval_qrel"] is False
    assert events[0]["review_unit"] == REVIEW_UNIT_SECTION
    assert unreviewed(bundle, [events[0]])
    receipt = write_progress_receipt(ledger, bundle, tmp_path / "progress.json")
    assert receipt["completed_final_output_units"] == 1
    assert receipt["review_unit"] == REVIEW_UNIT_SECTION
    assert receipt["bge_retrieval_metrics_computable"] is False
    with pytest.raises(FinalResumeOutputReviewError, match="already rated"):
        append_reviews(
            ledger,
            bundle,
            [
                {
                    "unit_ref": candidate["unit_ref"],
                    "grade": 3,
                    "rationale": "Strong fit; keep as written",
                }
            ],
        )


def test_selected_rationale_requires_explicit_reason() -> None:
    with pytest.raises(FinalResumeOutputReviewError):
        selected_rationale("", "")
