"""Regression tests for section artifacts that are final by definition."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.sections import unify_bullets_lane, unify_narrative_lane


def test_unify_lanes_do_not_materialize_fact_check_before_x2(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The guarded writer must see the final fact receipt's first write."""
    for module, section_id in (
        (unify_bullets_lane, "unify_bullets"),
        (unify_narrative_lane, "unify_narrative"),
    ):
        json_writes: list[tuple[str, dict]] = []
        x2_writes: list[tuple[str, list[dict], str | None]] = []

        monkeypatch.setattr(
            module,
            "write_json",
            lambda path, payload: json_writes.append((Path(path).name, dict(payload))),
        )
        monkeypatch.setattr(
            module,
            "write_x2_gate_outputs",
            lambda path, gates, *, section_id=None: x2_writes.append(
                (Path(path).name, list(gates), section_id)
            ),
        )

        module._write_pre_x2_evaluation_state(tmp_path / section_id)

        assert json_writes == [
            ("x3_disposition.json", {"x3_code": "PENDING", "status": "pending"})
        ]
        assert x2_writes == [("x2_gate_outputs.json", [], section_id)]
        assert all(name != "fact_check_result.json" for name, _ in json_writes)
