"""Guard: no code path may emit a synthetic judge score or disguise a deterministic screen as a model call."""
from __future__ import annotations

import pathlib

from apps_eval.graders.judge.preflight_lint import screen_handoff_payload_deterministic
from apps_rg.runtime.judges import executive_summary_x1d as x


def test_legacy_inprocess_proof_judge_and_gate_closure_map_are_retired() -> None:
    judges_dir = pathlib.Path(x.__file__).resolve().parent
    assert not (judges_dir / "inprocess_proof_judge.py").exists()
    assert not (judges_dir / "executive_summary_x1d_gate_closure_map.py").exists()


def test_handoff_screen_emits_null_unit_score_and_false_llm_executed() -> None:
    rcpt = screen_handoff_payload_deterministic(
        body=b'{"claims": ["Grounded fact."], "company_name": "Acme"}',
    )
    assert rcpt.passed is True
    assert rcpt.evaluator_kind == "deterministic_gate"
    assert rcpt.llm_judge_executed is False
    assert rcpt.normalized_unit_score is None
    assert rcpt.tokens_spent == 0


def test_no_source_file_constructs_an_argon_response_id_for_judges() -> None:
    root = pathlib.Path(x.__file__).resolve().parents[2]
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if '"argon-" +' in text or "argon-' +" in text or 'f"argon-{' in text:
            offenders.append(str(path))
    assert offenders == []
