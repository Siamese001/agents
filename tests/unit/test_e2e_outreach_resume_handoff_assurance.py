"""Counterfactual unit tests for E2E outreach and resume handoff assurance (Wave 1)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agents.e2e_artifacts import (
    resolve_and_verify_outreach_artifact,
    resolve_and_verify_resume_artifact,
)
from apps_lic.integrations.research_boundary_policy import (
    _find_valid_persisted_artifact_bundle,
    _read_candidate_brief,
)
from apps_lic.pipeline.compiler import PromptCompiler, _load_cached_yaml_template


def test_read_candidate_brief_handoff_keys_and_corrupt_json(tmp_path: Path) -> None:
    """Wave 1 (F-01): _read_candidate_brief preserves company_brief_text, rejects non-dict JSON, and survives corrupt JSON."""
    brief_json = tmp_path / "acme_brief.json"
    brief_json.write_text(
        json.dumps({"company_brief_text": "Acme modernizes regulated cloud risk platforms."}),
        encoding="utf-8",
    )
    assert _read_candidate_brief(brief_json) == "Acme modernizes regulated cloud risk platforms."

    alt_json = tmp_path / "alt_brief.json"
    alt_json.write_text(
        json.dumps({"brief_text": "AltCorp expands AI governance tooling."}),
        encoding="utf-8",
    )
    assert _read_candidate_brief(alt_json) == "AltCorp expands AI governance tooling."

    # Non-dict JSON list must not leak raw JSON syntax into prose company brief
    list_json = tmp_path / "list_brief.json"
    list_json.write_text('["not", "a", "brief"]', encoding="utf-8")
    assert _read_candidate_brief(list_json) == ""

    # Corrupt JSON must fail closed to empty string instead of raising uncaught JSONDecodeError
    corrupt_json = tmp_path / "corrupt_brief.json"
    corrupt_json.write_text("{corrupt json", encoding="utf-8")
    assert _read_candidate_brief(corrupt_json) == ""


def test_persisted_bundle_preserves_strategic_priorities_and_survives_non_dict_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wave 1 (F-01): _find_valid_persisted_artifact_bundle reads strategic_priorities and guards non-dict company_brief.json."""
    import apps_lic.integrations.managed_research_delegation as mrd

    monkeypatch.setattr(mrd, "_validate_persisted_research_artifacts", lambda result, request=None: (True, "ok", {}))

    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run_001"
    run_dir.mkdir(parents=True)

    (run_dir / "apps_research_apps_rg_handoff_v2.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "identity": {"company_name": "Acme Corp", "target_role": "VP AI Platform"},
                "exit_authorization": {"x3_code": "X3D_ALLOW_FINISH"},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": "run_001",
                "company_name": "Acme Corp",
                "is_verified": True,
                "confidence_score": 0.92,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "company_brief.md").write_text(
        "Acme Corp builds cloud systems.",
        encoding="utf-8",
    )
    (run_dir / "company_brief.json").write_text(
        json.dumps(
            {
                "strategic_priorities": [
                    "Scale governed multi-agent runtime",
                    "Harden evaluation release gates",
                ]
            }
        ),
        encoding="utf-8",
    )

    res, status = _find_valid_persisted_artifact_bundle(
        artifact_runs_root=runs_root,
        company_name="Acme Corp",
        job_title="VP AI Platform",
    )
    assert res is not None, f"Expected valid bundle, got status={status}"
    assert res.strategic_priorities == (
        "Scale governed multi-agent runtime",
        "Harden evaluation release gates",
    )

    # Non-dict company_brief.json must not raise AttributeError before artifact validation
    (run_dir / "company_brief.json").write_text('["unexpected_list"]', encoding="utf-8")
    res_list, _ = _find_valid_persisted_artifact_bundle(
        artifact_runs_root=runs_root,
        company_name="Acme Corp",
        job_title="VP AI Platform",
    )
    assert res_list is not None


def test_prompt_compiler_non_mapping_yaml_fails_closed_to_mapping(tmp_path: Path) -> None:
    """Wave 1 (F-02): _load_cached_yaml_template enforces dict return contract on scalar/list YAML."""
    _load_cached_yaml_template.cache_clear()
    scalar_tmpl = tmp_path / "scalar_template.yaml"
    scalar_tmpl.write_text("just a plain scalar string\n", encoding="utf-8")

    mtime = scalar_tmpl.stat().st_mtime
    loaded = _load_cached_yaml_template(str(scalar_tmpl.resolve()), mtime)
    assert loaded == {}
    assert isinstance(loaded, dict)

    compiler = PromptCompiler(templates_dir=tmp_path)
    assert compiler.load_template("scalar_template") == {}


def test_resume_x3_nested_or_empty_receipt_fails_closed(tmp_path: Path) -> None:
    """Wave 1 (F-03): resolve_and_verify_resume_artifact rejects nested X3D_BLOCK, empty dict, and non-dict receipts."""
    args = argparse.Namespace(json=True)

    # Case 1: Nested payload.x3_disposition == X3D_BLOCK must fail closed
    base_nested = tmp_path / "case_nested"
    resume_dir = base_nested / "resume"
    resume_dir.mkdir(parents=True)
    (resume_dir / "FINAL_RESUME_OUTPUT.txt").write_text("Valid resume content", encoding="utf-8")
    (resume_dir / "x3_disposition_receipt.json").write_text(
        json.dumps({"payload": {"x3_disposition": "X3D_BLOCK"}}),
        encoding="utf-8",
    )
    summary_nested: dict = {"stages": {}}
    with pytest.raises(RuntimeError, match="X3D_BLOCK|disposition"):
        resolve_and_verify_resume_artifact(
            run_id="test_nested_block",
            base_dir=base_nested,
            rg_code=0,
            summary_payload=summary_nested,
            args=args,
        )
    assert summary_nested["stages"]["resume_tailoring"]["status"] in {"BLOCKED", "FAILED"}

    # Case 2: Empty {} X3 receipt (missing disposition code) must fail closed
    base_empty = tmp_path / "case_empty"
    resume_empty = base_empty / "resume"
    resume_empty.mkdir(parents=True)
    (resume_empty / "FINAL_RESUME_OUTPUT.txt").write_text("Valid resume content", encoding="utf-8")
    (resume_empty / "x3_disposition_receipt.json").write_text("{}", encoding="utf-8")
    summary_empty: dict = {"stages": {}}
    with pytest.raises(RuntimeError, match="disposition"):
        resolve_and_verify_resume_artifact(
            run_id="test_empty_x3",
            base_dir=base_empty,
            rg_code=0,
            summary_payload=summary_empty,
            args=args,
        )

    # Case 3: Non-dict JSON list in X3 receipt must raise RuntimeError (not AttributeError)
    base_list = tmp_path / "case_list"
    resume_list = base_list / "resume"
    resume_list.mkdir(parents=True)
    (resume_list / "FINAL_RESUME_OUTPUT.txt").write_text("Valid resume content", encoding="utf-8")
    (resume_list / "x3_disposition_receipt.json").write_text('["not_a_dict"]', encoding="utf-8")
    summary_list: dict = {"stages": {}}
    with pytest.raises(RuntimeError, match="receipt|disposition"):
        resolve_and_verify_resume_artifact(
            run_id="test_list_x3",
            base_dir=base_list,
            rg_code=0,
            summary_payload=summary_list,
            args=args,
        )

    # Case 4: Non-dict outreach run_receipt.json must also fail closed
    outreach_dir = tmp_path / "outreach_list"
    outreach_dir.mkdir(parents=True)
    (outreach_dir / "campaign.json").write_text('{"messages": [1]}', encoding="utf-8")
    (outreach_dir / "run_receipt.json").write_text('["corrupt_list_receipt"]', encoding="utf-8")
    summary_outreach: dict = {"stages": {}}
    with pytest.raises(RuntimeError, match="receipt"):
        resolve_and_verify_outreach_artifact(
            outreach_artifact_dir=outreach_dir,
            oe_code=0,
            outreach_main_callable=lambda: 0,
            summary_payload=summary_outreach,
            args=args,
        )


def test_smoke_cli_parses_skip_resume_and_no_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wave 2 (F-04): ops_scripts/run_e2e_authoritative_smoke.py accepts --skip-resume and --no-write."""
    import ops_scripts.run_e2e_authoritative_smoke as smoke

    captured: dict[str, bool] = {}

    def fake_run_smoke(skip_resume: bool = True, **kwargs: object) -> int:
        captured["skip_resume"] = skip_resume
        captured["read_only"] = bool(kwargs.get("read_only", False))
        return 0

    monkeypatch.setattr(smoke, "run_smoke", fake_run_smoke)
    rc = smoke.main(["--skip-resume", "--no-write"])
    assert rc == 0
    assert captured == {"skip_resume": True, "read_only": True}


def test_precedent_bridge_fails_closed_on_gate_exception_and_mapping_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wave 2 (F-05): RuntimePrecedentBridge fails closed (SURFACE_HITL_ATOMIC) on gate error and supports MappingProxyType."""
    from types import MappingProxyType
    from agents.context.precedent_bridge import RuntimePrecedentBridge
    import tools.hitl_governance as hg

    bridge = RuntimePrecedentBridge(db_path=tmp_path / "prec.sqlite")

    def boom_gate(*args, **kwargs):
        raise RuntimeError("simulated gate fault")

    monkeypatch.setattr(hg, "evaluate_hitl_surfacing_gate", boom_gate)
    gate_err = bridge.evaluate_runtime_ambiguity(
        [{"label": "Option A", "confidence_score": 0.90}, {"label": "Option B", "confidence_score": 0.40}]
    )
    assert gate_err["should_surface"] is True
    assert gate_err["action"] == "SURFACE_HITL_ATOMIC"
    assert gate_err["margin"] == 0.0
    bridge.close()

    # Fallback mode (store unavailable) must read MappingProxyType scores
    bridge_nostore = RuntimePrecedentBridge.__new__(RuntimePrecedentBridge)
    bridge_nostore._store = None
    proxy_opts = [
        MappingProxyType({"label": "Primary", "confidence_score": 0.91}),
        MappingProxyType({"label": "Secondary", "confidence_score": 0.50}),
    ]
    res_proxy = bridge_nostore.evaluate_runtime_ambiguity(proxy_opts)
    assert res_proxy["top_score"] == 0.91
    assert res_proxy["should_surface"] is False


def test_reconstruct_eval_draft_logs_corrupt_json_and_falls_back_to_markdown(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Wave 2 (F-06): _reconstruct_eval_draft logs corrupt JSON/non-dict payloads and recovers valid markdown fallback."""
    import logging
    from apps_lic.__main__ import _reconstruct_eval_draft

    (tmp_path / "outreach_draft.json").write_text('["not_a_draft_object"]', encoding="utf-8")
    (tmp_path / "outreach_draft.md").write_text(
        "# Outreach Draft: email\n**Subject**: Platform Briefing\n```text\nGrounded executive note.\n```\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        draft = _reconstruct_eval_draft(tmp_path)
    assert draft is not None
    assert draft.subject == "Platform Briefing"
    assert any("outreach_draft.json" in rec.message for rec in caplog.records)

