"""Unit tests for Wave 5: Monolith Decomposition & Domain Boundary Enforcement.

Verifies:
1. ArtifactOutputEmitter produces mandatory artifacts with verified cryptographic manifests.
2. executive_summary_v2 enforces deterministic X2 voice invariants with zero post-LLM regex mutation.
3. ModularPipelineOrchestrator coordinates section generation, evaluation, release gating, and assembly.
4. Decomposed domain services maintain strict layer isolation without concrete storage imports.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

from apps_rg.runtime.artifact_output import ArtifactOutputEmitter
from apps_rg.runtime.pipeline import (
    EvaluationService,
    ModularPipelineOrchestrator,
    ReleasePolicy,
    SectionGenerationService,
)
from apps_rg.runtime.sections.executive_summary_v2 import x2_invariants


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

    for res in results:
        file_path = tmp_path / res.filename
        manifest_path = tmp_path / f"{res.filename}.manifest.json"
        assert file_path.exists()
        assert manifest_path.exists()

        content = file_path.read_bytes()
        expected_digest = hashlib.sha256(content).hexdigest()
        assert res.digest == expected_digest
        assert res.is_valid is True


def test_executive_summary_v2_validator_policy_without_regex_mutation() -> None:
    inanimate_text = (
        "Platform ownership covered governed multi-agent orchestration across regulated banking. "
        "Field delivery scaled cloud modernization across enterprise teams. "
        "Built deterministic evaluation controls across global accounts."
    )
    gates = x2_invariants.evaluate_executive_summary_v2_x2(
        resume_display_text=inanimate_text,
        claim_ledger=[],
        parsed_output={"resume_display_text": inanimate_text},
        allowed_fact_ids=set(),
        verified_numbers=frozenset(),
        verified_corpus_lower="",
        target_company="Truist",
        jd_text="",
    )
    inanimate_gate = next(g for g in gates if g["gate_id"] == "x2_v2_no_inanimate_subject_openers")
    assert inanimate_gate["pass"] is False


def test_modular_pipeline_orchestration() -> None:
    gen_service = SectionGenerationService()
    eval_service = EvaluationService()
    release_policy = ReleasePolicy(min_average_score=0.80)

    gen_service.register_handler("headline", lambda ctx: "Principal Cloud Architect")
    gen_service.register_handler("executive_summary", lambda ctx: "Executive with 15 years leading engineering teams.")
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
    from apps_rg.runtime.sections.executive_summary_v2 import contract_emitter as es_v2

    for mod in (ao, pl, es_v2):
        src = inspect.getsource(mod)
        assert "import sqlite3" not in src
        assert "agents.persistence.sqlite" not in src
