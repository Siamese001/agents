from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from apps_rg.evals.l1_cognitive_paired_shadow_capture import (
    L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME,
    build_l1_cognitive_pair_config_receipt,
    build_l1_cognitive_pair_input_receipt,
)
from apps_rg.evals.l1_cognitive_shadow_runner import run_l1_cognitive_shadow_arm
from apps_rg.evals.l1_cognitive_shadow_runner import L1_COGNITIVE_SHADOW_TENANT_ID
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1_COGNITIVE_V3_CANDIDATE_ARM,
)
from apps_rg.runtime.spine.validated_request_contract import (
    load_validated_request_contract,
)


def _write_inputs(tmp_path: Path, repo_root: Path) -> tuple[Path, Path, Path]:
    jd = tmp_path / "jd.txt"
    brief = tmp_path / "brief.txt"
    jd.write_text(
        "Lead AI platform strategy for regulated insurance operations.",
        encoding="utf-8",
    )
    brief.write_text(
        "Use only the supplied candidate record and job description.", encoding="utf-8"
    )
    resume = (
        repo_root
        / "src"
        / "apps_rg"
        / "resume"
        / "base"
        / "amit_ayer_base_resume_v1.json"
    )
    return jd, brief, resume


def test_shadow_runner_binds_candidate_at_u0_and_emits_blocked_receipt_when_no_lane_prompts(
    monkeypatch, tmp_path: Path
) -> None:
    from apps_rg.evals import l1_cognitive_shadow_runner as runner
    from apps_rg.runtime.runtime_proof_layout import find_repo_root

    repo = find_repo_root()
    jd, brief, resume = _write_inputs(tmp_path, repo)
    frozen = build_l1_cognitive_pair_input_receipt(
        target_company="Example Insurer",
        target_role="SVP AI Platform",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
    )
    config = build_l1_cognitive_pair_config_receipt(
        generation_mode="strategic_tailor", auto_research_internal=False
    )
    observed: dict[str, object] = {}

    def fake_modular(*args, **kwargs):
        observed["input"] = args[0]
        observed["profile"] = args[3]
        observed["targeting"] = kwargs["lane_targeting"]
        observed["non_product_policy"] = os.environ.get(
            "APPS_RG_ALLOW_PRODUCT_SHORTCUTS"
        )
        return SimpleNamespace(
            decisive_status="FAIL", failure_reason="not_run_in_unit_test"
        )

    monkeypatch.setattr(
        runner,
        "_require_new_run_root",
        lambda *, artifact_dir, repo_root: artifact_dir.mkdir(
            parents=True, exist_ok=True
        ),
    )
    monkeypatch.setattr(runner, "run_modular_resume_generation", fake_modular)
    result = run_l1_cognitive_shadow_arm(
        artifact_dir=tmp_path / "candidate",
        target_company="Example Insurer",
        target_role="SVP AI Platform",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
        treatment_arm=L1_COGNITIVE_V3_CANDIDATE_ARM,
        repo_root=repo,
        frozen_input_receipt=frozen,
        config_receipt=config,
    )

    root = Path(result["artifact_dir"])
    treatment = json.loads(
        (root / "l1_cognitive_treatment.json").read_text(encoding="utf-8")
    )
    execution = json.loads(
        (root / "l1_cognitive_treatment_execution.json").read_text(encoding="utf-8")
    )
    assert treatment["arm"] == L1_COGNITIVE_V3_CANDIDATE_ARM
    assert treatment["assignment_origin"] == "U0_VALIDATED_INGRESS"
    assert (root / "l1_cognitive_plan.json").is_file()
    binding = json.loads(
        (root / L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME).read_text(encoding="utf-8")
    )
    assert binding["frozen_input"] == frozen
    assert binding["execution_config"] == config
    assert (root / "apps_rg_u0_validated_request.json").is_file()
    validated_request = load_validated_request_contract(
        root / "apps_rg_u0_validated_request.json"
    )
    assert validated_request.tenant_id == L1_COGNITIVE_SHADOW_TENANT_ID
    assert observed["input"].canonical_run_identity == {}
    assert execution["status"] == "BLOCKED"
    assert "no_compiled_prompt_artifacts_observed" in execution["errors"]
    assert observed["targeting"].jd_ref_used == str(jd.resolve())
    assert observed["profile"].phase1_invoke_real_lanes is True
    assert observed["non_product_policy"] == "1"


def test_shadow_runner_control_omits_v3_plan(monkeypatch, tmp_path: Path) -> None:
    from apps_rg.evals import l1_cognitive_shadow_runner as runner
    from apps_rg.runtime.runtime_proof_layout import find_repo_root

    repo = find_repo_root()
    jd, brief, resume = _write_inputs(tmp_path, repo)
    monkeypatch.setattr(
        runner,
        "_require_new_run_root",
        lambda *, artifact_dir, repo_root: artifact_dir.mkdir(
            parents=True, exist_ok=True
        ),
    )
    monkeypatch.setattr(
        runner,
        "run_modular_resume_generation",
        lambda *args, **kwargs: SimpleNamespace(
            decisive_status="FAIL", failure_reason="test"
        ),
    )
    result = run_l1_cognitive_shadow_arm(
        artifact_dir=tmp_path / "control",
        target_company="Example Insurer",
        target_role="SVP AI Platform",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
        treatment_arm=L1_COGNITIVE_V2_CONTROL_ARM,
        repo_root=repo,
    )

    root = Path(result["artifact_dir"])
    assert not (root / "l1_cognitive_plan.json").exists()
    execution = json.loads(
        (root / "l1_cognitive_treatment_execution.json").read_text(encoding="utf-8")
    )
    assert execution["treatment"]["arm"] == L1_COGNITIVE_V2_CONTROL_ARM
    assert execution["status"] == "BLOCKED"


def test_shadow_runner_retains_a_system_exit_from_a_lane(
    monkeypatch, tmp_path: Path
) -> None:
    from apps_rg.evals import l1_cognitive_shadow_runner as runner
    from apps_rg.runtime.runtime_proof_layout import find_repo_root

    repo = find_repo_root()
    jd, brief, resume = _write_inputs(tmp_path, repo)
    monkeypatch.setattr(
        runner,
        "_require_new_run_root",
        lambda *, artifact_dir, repo_root: artifact_dir.mkdir(
            parents=True, exist_ok=True
        ),
    )

    def fake_modular(*args, **kwargs):
        raise SystemExit("provider preflight terminated lane")

    monkeypatch.setattr(runner, "run_modular_resume_generation", fake_modular)
    result = run_l1_cognitive_shadow_arm(
        artifact_dir=tmp_path / "candidate-system-exit",
        target_company="Example Insurer",
        target_role="SVP AI Platform",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
        treatment_arm=L1_COGNITIVE_V3_CANDIDATE_ARM,
        repo_root=repo,
    )

    root = Path(result["artifact_dir"])
    outcome = json.loads(
        (root / "l1_cognitive_shadow_run_result.json").read_text(encoding="utf-8")
    )
    assert outcome["status"] == "FAIL"
    assert (
        outcome["modular_exception"] == "SystemExit:provider preflight terminated lane"
    )
    assert (root / "l1_cognitive_treatment_execution.json").is_file()


def test_shadow_runner_records_explicit_nonproduct_preflight_disable(
    monkeypatch, tmp_path: Path
) -> None:
    from apps_rg.evals import l1_cognitive_shadow_runner as runner
    from apps_rg.runtime.runtime_proof_layout import find_repo_root

    repo = find_repo_root()
    jd, brief, resume = _write_inputs(tmp_path, repo)
    observed: dict[str, str | None] = {}
    monkeypatch.delenv("APPS_RG_COMPETENCIES_PROVIDER_PREFLIGHT_DISABLE", raising=False)
    monkeypatch.setattr(
        runner,
        "_require_new_run_root",
        lambda *, artifact_dir, repo_root: artifact_dir.mkdir(
            parents=True, exist_ok=True
        ),
    )

    def fake_modular(*args, **kwargs):
        observed["preflight_disable"] = os.environ.get(
            "APPS_RG_COMPETENCIES_PROVIDER_PREFLIGHT_DISABLE"
        )
        return SimpleNamespace(decisive_status="FAIL", failure_reason="test")

    monkeypatch.setattr(runner, "run_modular_resume_generation", fake_modular)
    result = run_l1_cognitive_shadow_arm(
        artifact_dir=tmp_path / "candidate-preflight-disable",
        target_company="Example Insurer",
        target_role="SVP AI Platform",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
        treatment_arm=L1_COGNITIVE_V3_CANDIDATE_ARM,
        repo_root=repo,
        allow_nonproduct_provider_preflight_disable=True,
    )

    root = Path(result["artifact_dir"])
    manifest = json.loads(
        (root / "spine_run_manifest.json").read_text(encoding="utf-8")
    )
    assert observed["preflight_disable"] == "1"
    assert result["non_product_provider_preflight_disabled"] is True
    assert manifest["non_product_provider_preflight_disabled"] is True
    assert os.environ.get("APPS_RG_COMPETENCIES_PROVIDER_PREFLIGHT_DISABLE") is None
