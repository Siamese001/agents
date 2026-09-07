"""W5 tests for the legacy orchestrator's governed-spine adapter."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any

from apps_rg.engines.resume_orchestrator_engine import ResumeOrchestratorEngine


@dataclass
class _Buffer:
    values: dict[str, Any] = field(default_factory=dict)

    def write(self, key: str, value: Any) -> None:
        self.values[key] = value


@dataclass
class _Context:
    target_company: str = "Anthropic"
    target_role: str = "Partnerships Architect"
    source_resume_text: str = "Built partner architecture programs."
    generation_mode: str = "strategic_tailor"
    artifact_dir: str = "artifacts/test-run"
    master_resume: dict[str, Any] = field(
        default_factory=lambda: {"headline": "Architecture leader"}
    )
    buffer: _Buffer = field(default_factory=_Buffer)


def test_w5_delegates_to_product_spine_and_emits_no_synthetic_hops_or_quality() -> None:
    context = _Context()
    observed: dict[str, Any] = {}

    def _runner(**kwargs: Any) -> dict[str, Any]:
        observed.update(kwargs)
        return {
            "execution_status": "completed",
            "exit_status": "allow",
            "outcome_authorized": True,
            "product_authorized": True,
            "pipeline_complete": True,
            "artifact_dir": "artifacts/test-run",
            "spine_run_manifest": "artifacts/test-run/spine_run_manifest.json",
            "terminal_manifest_ref": "artifacts/test-run/terminal.json",
            "pipeline_completion_receipt_ref": "artifacts/test-run/completion.json",
        }

    result = asyncio.run(
        ResumeOrchestratorEngine(context, product_runner=_runner).execute(
            "Lead partner architecture for enterprise AI deployments."
        )
    )

    assert observed["target_company"] == "Anthropic"
    assert observed["target_role"] == "Partnerships Architect"
    assert observed["job_description_text"] == (
        "Lead partner architecture for enterprise AI deployments."
    )
    assert result["status"] == "COMPLETE"
    assert result["receipt_refs"] == [
        "artifacts/test-run",
        "artifacts/test-run/spine_run_manifest.json",
        "artifacts/test-run/terminal.json",
        "artifacts/test-run/completion.json",
    ]
    assert "final_quality_score" not in result
    assert "ranked_content" not in context.buffer.values
    assert "hop1_extraction" not in context.buffer.values
    assert "hop2_enrichment" not in context.buffer.values
    assert "k9_competencies" not in context.buffer.values
    assert context.buffer.values["governed_run_receipt"] == result


def test_w5_removes_the_synthetic_scaffold_from_the_execution_source() -> None:
    source = inspect.getsource(ResumeOrchestratorEngine.execute)

    assert '"hop_stub"' not in source
    assert '"final_quality_score"' not in source
    assert '"ranked_content"' not in source


def test_w5_fails_closed_before_runner_when_required_context_is_missing() -> None:
    context = _Context(target_company="", target_role="")
    calls: list[dict[str, Any]] = []

    def _runner(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {}

    result = asyncio.run(
        ResumeOrchestratorEngine(context, product_runner=_runner).execute("")
    )

    assert result["status"] == "BLOCKED_INPUT"
    assert result["missing_inputs"] == [
        "target_company",
        "target_role",
        "job_description_text_or_ref",
    ]
    assert calls == []
    assert result["receipt_refs"] == []


def test_w5_anti_overfit_escalation_stops_before_product_execution() -> None:
    context = _Context(
        master_resume={
            "summary": "As we discussed last week, I delivered the migration as promised."
        }
    )
    calls: list[dict[str, Any]] = []

    def _runner(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {}

    result = asyncio.run(
        ResumeOrchestratorEngine(context, product_runner=_runner).execute(
            "Lead partner architecture."
        )
    )

    assert result["status"] == "ESCALATED_OVERFIT"
    assert result["overfit"]["escalate"] is True
    assert calls == []
    assert "final_quality_score" not in result


def test_w5_preserves_governed_block_without_upgrading_it_to_success() -> None:
    context = _Context()

    def _runner(**_kwargs: Any) -> dict[str, Any]:
        return {
            "execution_status": "failed",
            "exit_status": "error",
            "outcome_authorized": False,
            "product_authorized": False,
            "pipeline_complete": False,
            "artifact_dir": "artifacts/blocked-run",
            "fault": "UPSTREAM_EVIDENCE_MISSING",
        }

    result = asyncio.run(
        ResumeOrchestratorEngine(context, product_runner=_runner).execute(
            "Lead partner architecture."
        )
    )

    assert result["status"] == "BLOCKED"
    assert result["governed_result"]["fault"] == "UPSTREAM_EVIDENCE_MISSING"
    assert result["outcome_authorized"] is False
