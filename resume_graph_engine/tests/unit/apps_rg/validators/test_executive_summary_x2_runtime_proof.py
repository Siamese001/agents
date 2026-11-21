"""Executive summary v2 X2 proof gates and contract emitter verification."""

from __future__ import annotations

from pathlib import Path

from tests.helpers import apps_rg_model_pins as pins

from apps_rg.repository_layout import resolve_apps_rg_path
from apps_rg.runtime.validators.executive_summary_x2 import (
    ALLOWED_MODELS,
    PRE_X2_REQUIRED_ARTIFACTS,
    check_required_artifacts,
    model_name_matches_allowed,
)


def test_pre_x2_artifact_gate_does_not_require_final_receipts(tmp_path: Path) -> None:
    for artifact in PRE_X2_REQUIRED_ARTIFACTS:
        path = tmp_path / artifact
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    ok, reason = check_required_artifacts(tmp_path, include_post_x2_receipts=False)

    assert ok is True
    assert reason is None

    full_ok, full_reason = check_required_artifacts(tmp_path)
    assert full_ok is False
    assert "fact_check_result.json" in str(full_reason)
    assert "real_l2_generation_result.json" in str(full_reason)
    assert "section_metric_receipt.json" in str(full_reason)
    assert "x3_disposition.json" in str(full_reason)


def test_executive_summary_model_allowlist_accepts_pinned_generator_models() -> None:
    from apps_rg.runtime.section_model_limits import resolve_section_generation_model

    exec_summary_pin = resolve_section_generation_model("executive_summary")
    retired_openai_model = "gpt-" + "5.4-mini"
    assert exec_summary_pin in ALLOWED_MODELS
    assert retired_openai_model not in ALLOWED_MODELS

    assert model_name_matches_allowed(exec_summary_pin, ALLOWED_MODELS) is True
    assert model_name_matches_allowed("claude-haiku-3-5", ALLOWED_MODELS) is False
    assert model_name_matches_allowed(retired_openai_model, ALLOWED_MODELS) is False


def test_executive_summary_v2_sources_emit_final_fact_check_without_pending_stub() -> None:
    sections_dir = resolve_apps_rg_path(
        Path(__file__).resolve().parents[4],
        "runtime",
        "sections",
    )
    v2_dir = sections_dir / "executive_summary_v2"
    assert v2_dir.is_dir(), "executive_summary_v2 package must exist"
    sources = {
        path.relative_to(sections_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(v2_dir.rglob("*.py"))
    }
    assert sources
    for rel, src in sources.items():
        assert '"status": "pending"' not in src, f"Pending placeholder found in {rel}"
    emitter_src = sources["executive_summary_v2/contract_emitter.py"]
    assert '"fact_check_result.json"' in emitter_src
    assert '"x1d_llm_judge_outputs.json"' in emitter_src
