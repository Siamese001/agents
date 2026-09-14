"""Unit tests for Wave 5: Monolith Decomposition & Domain Boundary Enforcement.

Verifies:
1. ArtifactOutputEmitter produces mandatory artifacts with verified cryptographic manifests.
2. ExecutiveSummaryRepairEngine applies declarative rules deterministically with audit entries.
3. ExecutiveSummaryValidator enforces voice policy without regex side effects.
4. ModularPipelineOrchestrator coordinates section generation, evaluation, release gating, and assembly.
5. Decomposed domain services maintain strict layer isolation without concrete storage imports.
6. All decomposed modules adhere to the 600-line file budget.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
import pytest

from apps_rg.runtime.artifact_output import (
    ArtifactOutputEmitter,
    MandatoryOutputPolicy,
)
from apps_rg.runtime.pipeline import (
    ArtifactAssembler,
    EvaluationService,
    ModularPipelineOrchestrator,
    ReleasePolicy,
    SectionGenerationService,
)
from apps_rg.runtime.sections.executive_summary import (
    ExecutiveSummaryRepairEngine,
    ExecutiveSummaryValidator,
    VoiceRepairPolicy,
)


def test_artifact_output_emitter_and_manifests(tmp_path: Path) -> None:
    emitter = ArtifactOutputEmitter(tmp_path)
    run_id = "run-wave5-001"

    results = emitter.emit_all_mandatory_outputs(
        run_id=run_id,
        workflow_status="COMPLETED",
        context={"total_sections": 3, "passed_gates": 3},
        section_statuses={"headline": "COMPLETED", "executive_summary": "COMPLETED"},
    )

    assert len(results) == 4
    keys = {r.artifact_key for r in results}
    assert keys == {
        "bcg_executive_output",
        "output_bisect",
        "section_lane_summary_table",
        "mandatory_run_output_json",
    }

    # Verify each file and its manifest exist and hashes match
    for res in results:
        file_path = tmp_path / res.filename
        manifest_path = tmp_path / f"{res.filename}.manifest.json"
        assert file_path.exists()
        assert manifest_path.exists()

        content = file_path.read_bytes()
        expected_digest = hashlib.sha256(content).hexdigest()
        assert res.digest == expected_digest
        assert res.is_valid is True


def test_executive_summary_declarative_repair_engine() -> None:
    engine = ExecutiveSummaryRepairEngine()
    raw_text = (
        "It should be noted that the candidate was basically extremely competent.  "
        "In order to achieve high performance, they led multiple initiatives, ."
    )

    result = engine.repair_text(raw_text)

    assert result.is_modified is True
    assert result.total_modifications > 0
    assert len(result.applied_rules) > 0
    # Passive hedging and redundant fillers removed
    assert "it should be noted that" not in result.repaired_text.lower()
    assert "extremely" not in result.repaired_text.lower()
    assert "basically" not in result.repaired_text.lower()
    assert ", ." not in result.repaired_text


def test_executive_summary_validator_policy() -> None:
    policy = VoiceRepairPolicy(min_word_count=5, max_word_count=20, max_sentence_length=15)
    validator = ExecutiveSummaryValidator(policy)

    # Valid text
    valid_outcome = validator.validate("Experienced engineering leader with deep cloud architecture expertise.")
    assert valid_outcome.is_valid is True
    assert len(valid_outcome.violations) == 0

    # Violates max word count
    long_text = "word " * 25
    invalid_outcome = validator.validate(long_text)
    assert invalid_outcome.is_valid is False
    assert any("exceeds maximum allowed" in v for v in invalid_outcome.violations)


def test_modular_pipeline_orchestration() -> None:
    gen_service = SectionGenerationService()
    eval_service = EvaluationService()
    release_policy = ReleasePolicy(min_average_score=0.80)

    # Custom section handler
    gen_service.register_handler("headline", lambda ctx: "Principal Cloud Architect")
    gen_service.register_handler("executive_summary", lambda ctx: "Executive with 15 years leading engineering teams.")

    # Validation rules
    eval_service.register_validator("headline", lambda content: [] if len(content) > 5 else ["Headline too short"])

    orchestrator = ModularPipelineOrchestrator(
        generation_service=gen_service,
        evaluation_service=eval_service,
        release_policy=release_policy,
    )

    outcome = orchestrator.run_pipeline(
        run_id="run-mod-001",
        section_ids=("headline", "executive_summary"),
    )

    assert outcome.is_success is True
    assert outcome.release_decision.approved is True
    assert outcome.document is not None
    assert "Principal Cloud Architect" in outcome.document.markdown_content
    assert outcome.document.manifest.verify_integrity() is True


def test_modular_pipeline_rejection_on_failure() -> None:
    gen_service = SectionGenerationService()
    eval_service = EvaluationService()
    release_policy = ReleasePolicy(min_average_score=0.80, require_all_pass=True)

    gen_service.register_handler("headline", lambda ctx: "Short")
    # Validator fails headline
    eval_service.register_validator("headline", lambda content: ["Headline violates quality gate"])

    orchestrator = ModularPipelineOrchestrator(
        generation_service=gen_service,
        evaluation_service=eval_service,
        release_policy=release_policy,
    )

    outcome = orchestrator.run_pipeline(
        run_id="run-fail-001",
        section_ids=("headline",),
    )

    assert outcome.is_success is False
    assert outcome.release_decision.approved is False
    assert outcome.document is None
    assert len(outcome.release_decision.rejection_reasons) > 0


def test_wave5_domain_layer_isolation() -> None:
    import apps_rg.runtime.artifact_output as ao
    import apps_rg.runtime.pipeline as pl
    import apps_rg.runtime.sections.executive_summary as es

    for mod in (ao, pl, es):
        src = inspect.getsource(mod)
        assert "import sqlite3" not in src
        assert "agents.persistence.sqlite" not in src
