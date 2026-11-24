"""Unit and adversarial tests for Clean-Slate Judge v3 Declarative Rubric Registry & Anti-Bloat Gate."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps_eval.graders.judge.v3_registry import (
    JudgeRubricRegistryV3,
    MAX_CHECK_WORDS,
    MAX_COLD_READ_WORDS,
    MAX_RENDERED_RUBRIC_CHARS,
    MAX_RENDERED_RUBRIC_WORDS,
    REQUIRED_CLUSTERS,
    UnknownJudgeProfileError,
    compute_rubric_doc_sha256,
    render_v3_rubric_prompt,
)
from tools.validate_judge_rubrics_v3 import validate_judge_rubrics_v3


def test_v3_registry_loads_all_five_clusters_within_word_caps() -> None:
    reg = JudgeRubricRegistryV3.load()
    profiles = reg.list_profiles()
    assert len(profiles) == 12
    observed_clusters = {p.cluster for p in profiles}
    assert observed_clusters == set(REQUIRED_CLUSTERS)

    for prof in profiles:
        assert 4 <= len(prof.checks) <= 6
        assert any(c.critical for c in prof.checks)
        assert abs(sum(c.weight for c in prof.checks) - 1.0) < 1e-6
        assert len(prof.cold_read_question.split()) <= MAX_COLD_READ_WORDS
        for chk in prof.checks:
            assert len(chk.question.split()) <= MAX_CHECK_WORDS
        rendered = render_v3_rubric_prompt(prof)
        assert len(rendered.split()) <= MAX_RENDERED_RUBRIC_WORDS
        assert len(rendered) <= MAX_RENDERED_RUBRIC_CHARS


def test_v3_registry_fail_closed_on_unknown_or_empty_tokens() -> None:
    reg = JudgeRubricRegistryV3.load()
    for bad_token in ("", "   ", "unknown_profile", "external_partner", "random_section_xyz"):
        with pytest.raises(UnknownJudgeProfileError):
            reg.get_profile(bad_token)


def test_v3_registry_resolves_documented_aliases() -> None:
    reg = JudgeRubricRegistryV3.load()
    assert reg.get_profile("executive_summary").profile_id == "resume_sections:executive_summary"
    assert reg.get_profile("full_resume_coherence").profile_id == "resume_whole_coherence:full_resume"
    assert reg.get_profile("x1d_quorum").profile_id == "outreach_sequence:outreach_multi_touch_sequence"
    assert reg.get_profile("company_brief").profile_id == "company_research_brief:company_brief_synthesis"
    assert reg.get_profile("human_calibration_studio").profile_id == "agent_trace_and_calibration:human_calibration_studio"


def test_anti_bloat_validator_rejects_bloated_checks_employer_nouns_and_tampered_sha(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest_on_disk = json.loads((repo_root / "config/governance/judge_rubrics_v3.json").read_text(encoding="utf-8"))
    assert manifest_on_disk.get("central_catalog_ref") == "core-governance:judge_archetypes_v3"
    src_v3 = JudgeRubricRegistryV3.load().to_document_dict()
    ext_path = repo_root / "config/governance/external_judge_rubric_v2.json"

    ok, errs, _ = validate_judge_rubrics_v3(repo_root / "config/governance/judge_rubrics_v3.json", ext_path)
    assert ok is True, errs

    # 1. Tampered digest fails closed
    tampered = copy.deepcopy(src_v3)
    tampered["profiles"]["resume_sections:headline"]["pass_threshold"] = 0.75
    bad_sha_path = tmp_path / "tampered.json"
    bad_sha_path.write_text(json.dumps(tampered), encoding="utf-8")
    ok_sha, errs_sha, _ = validate_judge_rubrics_v3(bad_sha_path, ext_path)
    assert ok_sha is False
    assert any("SHA-256 mismatch" in e for e in errs_sha)

    # 2. >25 word check clause-stuffing fails closed
    bloated = copy.deepcopy(src_v3)
    bloated["profiles"]["resume_sections:headline"]["checks"][0]["question"] = " ".join(["word"] * 28) + "?"
    bloated["rubric_sha256"] = compute_rubric_doc_sha256(bloated)
    bloated_path = tmp_path / "bloated.json"
    bloated_path.write_text(json.dumps(bloated), encoding="utf-8")
    ok_bloat, errs_bloat, _ = validate_judge_rubrics_v3(bloated_path, ext_path)
    assert ok_bloat is False
    assert any("25 words" in e or "<=25-word" in e for e in errs_bloat)

    # 3. Historical/employer noun contamination fails closed
    contaminated = copy.deepcopy(src_v3)
    contaminated["profiles"]["resume_sections:headline"]["cold_read_question"] = (
        "Does this Slalom and IBM candidate avoid BCBS 239 Guidewire clutter?"
    )
    contaminated["rubric_sha256"] = compute_rubric_doc_sha256(contaminated)
    contam_path = tmp_path / "contaminated.json"
    contam_path.write_text(json.dumps(contaminated), encoding="utf-8")
    ok_contam, errs_contam, _ = validate_judge_rubrics_v3(contam_path, ext_path)
    assert ok_contam is False
    assert any("Slalom" in e or "BCBS 239" in e for e in errs_contam)


def test_ide_blind_protocol_orthogonality_routes_argon_to_neon_zero_egress() -> None:
    from apps_eval.graders.judge.blind_protocol import build_sealed_blind_judge_bundle

    bundle = build_sealed_blind_judge_bundle(
        artifact_id="art-ide-1",
        raw_input={"text": "Grounded executive headline."},
        author_model_family="argon",
        rubric_id="resume_sections:headline",
    )
    assert bundle.author_model_family == "argon"
    assert bundle.required_judge_family == "neon"
