"""Executive summary X2 proof gates for section-pinned primary model."""

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


def test_pre_x2_artifact_gate_does_not_require_final_receipts(tmp_path) -> None:
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


def test_executive_summary_model_allowlist_accepts_only_pinned_claude_primary() -> None:
    retired_openai_model = "gpt-" + "5.4-mini"
    assert pins.CLAUDE_GENERATOR_MODEL in ALLOWED_MODELS
    assert pins.RESEARCH_GENERATOR_MODEL not in ALLOWED_MODELS
    assert retired_openai_model not in ALLOWED_MODELS

    assert model_name_matches_allowed(pins.CLAUDE_GENERATOR_MODEL, ALLOWED_MODELS) is True
    assert model_name_matches_allowed("claude-haiku-3-5", ALLOWED_MODELS) is False
    assert model_name_matches_allowed(pins.RESEARCH_GENERATOR_MODEL, ALLOWED_MODELS) is False
    assert model_name_matches_allowed(retired_openai_model, ALLOWED_MODELS) is False
    assert (
        model_name_matches_allowed(pins.COMPETENCIES_SELECTOR_MODEL, ALLOWED_MODELS)
        is True
    )


def _collect_executive_summary_sources() -> dict[str, str]:
    sections_dir = resolve_apps_rg_path(
        Path(__file__).resolve().parents[4],
        "runtime",
        "sections",
    )
    files: list[Path] = []
    lane_file = sections_dir / "executive_summary_lane.py"
    if lane_file.is_file():
        files.append(lane_file)
    pkg_dir = sections_dir / "executive_summary"
    if pkg_dir.is_dir():
        files.extend(sorted(pkg_dir.rglob("*.py")))
    return {
        path.relative_to(sections_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in files
    }


def _count_path_join_literals(source: str, filename: str) -> int:
    import ast

    tree = ast.parse(source)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Constant)
        and node.right.value == filename
    )


def test_executive_summary_defers_empty_x1d_artifact_until_x2_failure() -> None:
    import ast

    sources = _collect_executive_summary_sources()
    assert sources, "executive_summary sources must exist"
    deferral_guard = (
        'if x2_failed_initial and not (artifact_dir / "x1d_llm_judge_outputs.json").is_file()'
    )
    matching = [rel for rel, src in sources.items() if deferral_guard in src]
    assert matching, (
        "Expected empty X1D artifact emission to stay gated behind x2_failed_initial"
    )
    for rel in matching:
        tree = ast.parse(sources[rel])
        guarded_empty_writes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and "x2_failed_initial" in ast.unparse(node.test)
            and "_write_x1d_judge_artifacts" in ast.unparse(node)
        ]
        assert guarded_empty_writes, rel


def test_executive_summary_defers_x2_only_fact_check_on_real_llm_success(
    tmp_path: Path,
) -> None:
    import json
    from apps_rg.runtime.sections.executive_summary.stage_closeout import (
        emit_final_fact_check_result,
    )

    sources = _collect_executive_summary_sources()
    assert sources, "executive_summary sources must exist"
    for rel, src in sources.items():
        assert '"status": "pending"' not in src, f"Pending placeholder found in {rel}"

    deferral_guard = 'if x2_failed_initial or runtime_generation_status != "REAL_LLM":'
    assert any(deferral_guard in src for src in sources.values())

    pkg_counts = sum(
        _count_path_join_literals(src, "fact_check_result.json")
        for rel, src in sources.items()
        if rel.startswith("executive_summary/")
    )
    lane_counts = _count_path_join_literals(
        sources.get("executive_summary_lane.py", ""),
        "fact_check_result.json",
    )
    assert pkg_counts in (0, 2) and lane_counts in (0, 2)
    assert (pkg_counts + lane_counts) > 0

    emit_final_fact_check_result(
        {
            "artifact_dir": tmp_path,
            "x2": [{"gate_id": "x2_word_budget", "pass": True}],
            "x3": {"x3_code": "PASS"},
            "product_quality_status": "GOOD",
        }
    )
    final_doc = json.loads((tmp_path / "fact_check_result.json").read_text(encoding="utf-8"))
    assert final_doc["passed"] is True
    assert final_doc["x3_code"] == "PASS"
    assert "status" not in final_doc
