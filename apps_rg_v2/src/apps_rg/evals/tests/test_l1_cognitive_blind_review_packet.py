"""Tests for the non-promoting blind review packet builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.evals.l1_cognitive_blind_review_packet import (
    L1CognitiveBlindReviewPacketError,
    build_l1_cognitive_blind_review_material,
    write_l1_cognitive_blind_review_material,
)
from apps_rg.evals.l1_cognitive_outcome_protocol import (
    build_l1_cognitive_paired_shadow_receipt,
    load_l1_cognitive_outcome_protocol,
)
from apps_rg.evals.l1_cognitive_paired_shadow_capture import (
    build_l1_cognitive_pair_config_receipt,
    build_l1_cognitive_pair_input_receipt,
    build_l1_cognitive_shadow_run_binding,
)


def _digest(char: str) -> str:
    return "sha256:" + char * 64


def _bundle(*, digest: str) -> dict[str, object]:
    return {
        "target": {"company": "Acme", "role": "VP Engineering"},
        "source": {"final_resume_sha256": digest},
        "candidates": [
            {
                "unit_ref": f"unit-{index}",
                "display_label": f"Section {index}",
                "final_text": f"Finished text {index}",
                "final_text_sha256": digest,
            }
            for index in range(1, 7)
        ],
    }


def test_packet_hides_arms_and_seals_mapping(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    control_root = tmp_path / "control"
    candidate_root = tmp_path / "candidate"
    control_root.mkdir()
    candidate_root.mkdir()
    jd = tmp_path / "jd.txt"
    brief = tmp_path / "brief.txt"
    resume = tmp_path / "resume.json"
    jd.write_text("Required platform leadership", encoding="utf-8")
    brief.write_text("Targeting brief", encoding="utf-8")
    resume.write_text("{}", encoding="utf-8")
    frozen = build_l1_cognitive_pair_input_receipt(
        target_company="Acme",
        target_role="VP Engineering",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
    )
    config = build_l1_cognitive_pair_config_receipt(
        generation_mode="strategic_tailor", auto_research_internal=False
    )
    binding = build_l1_cognitive_shadow_run_binding(
        frozen_input_receipt=frozen,
        config_receipt=config,
    )
    pairs = [
        {
            "pair_id": "pair-001",
            "frozen_input_digest": frozen["input_digest"],
            "provider_model_config_digest": config["provider_model_config_digest"],
            "tool_config_digest": config["tool_config_digest"],
            "control": {
                "run_ref": "control/run.json",
                "run_id": "control-run",
                "l1_v2_capsule_digest": _digest("d"),
                "l1_cognitive_treatment_execution_digest": _digest("e"),
                "compiled_prompt_digest": _digest("f"),
                "output_digest": _digest("1"),
                "completion_status": "PASS",
            },
            "candidate": {
                "run_ref": "candidate/run.json",
                "run_id": "candidate-run",
                "l1_cognitive_plan_digest": _digest("2"),
                "l1_cognitive_advisory_digest": _digest("3"),
                "c0_outcome_set_digest": _digest("4"),
                "l1_cognitive_revision_set_digest": _digest("5"),
                "l1_cognitive_treatment_execution_digest": _digest("6"),
                "compiled_prompt_digest": _digest("7"),
                "output_digest": _digest("8"),
                "completion_status": "PASS",
            },
        }
    ]
    receipt = build_l1_cognitive_paired_shadow_receipt(
        protocol=load_l1_cognitive_outcome_protocol(), pairs=pairs
    )
    monkeypatch.setattr(
        "apps_rg.evals.l1_cognitive_blind_review_packet._read_execution_digest",
        lambda root, arm: _digest("e") if arm == "control" else _digest("6"),
    )
    monkeypatch.setattr(
        "apps_rg.evals.l1_cognitive_blind_review_packet.load_l1_cognitive_shadow_run_binding",
        lambda root: binding,
    )
    monkeypatch.setattr(
        "apps_rg.evals.l1_cognitive_blind_review_packet.load_final_resume_output_bundle",
        lambda root, **_kwargs: _bundle(
            digest="1" * 64 if Path(root) == control_root else "8" * 64
        ),
    )

    packet, sealed = build_l1_cognitive_blind_review_material(
        paired_receipt=receipt,
        run_roots={"pair-001": {"control": control_root, "candidate": candidate_root}},
        repo_root=tmp_path,
        nonce="a" * 64,
    )

    visible = json.dumps(packet, sort_keys=True)
    assert "l1_v2_control" not in visible
    assert "l1_cognitive_v3" not in visible
    assert packet["status"] == "PENDING_HUMAN_REVIEW"
    assert {row["arm"] for row in sealed["pairs"][0]["variants"]} == {
        "control",
        "candidate",
    }
    packet_path, mapping_path = write_l1_cognitive_blind_review_material(
        packet_path=tmp_path / "blind_review_packet.json",
        sealed_mapping_path=tmp_path / "sealed_mapping.json",
        packet=packet,
        sealed_mapping=sealed,
    )
    assert packet_path.is_file()
    assert mapping_path.is_file()


def test_packet_rejects_completed_pair_without_run_local_provenance(
    tmp_path: Path,
) -> None:
    control_root = tmp_path / "control"
    candidate_root = tmp_path / "candidate"
    control_root.mkdir()
    candidate_root.mkdir()
    receipt = build_l1_cognitive_paired_shadow_receipt(
        protocol=load_l1_cognitive_outcome_protocol(),
        pairs=[
            {
                "pair_id": "pair-without-provenance",
                "frozen_input_digest": _digest("a"),
                "provider_model_config_digest": _digest("b"),
                "tool_config_digest": _digest("c"),
                "control": {
                    "run_ref": "control",
                    "run_id": "control-run",
                    "l1_v2_capsule_digest": _digest("d"),
                    "l1_cognitive_treatment_execution_digest": _digest("e"),
                    "compiled_prompt_digest": _digest("f"),
                    "output_digest": _digest("1"),
                    "completion_status": "PASS",
                },
                "candidate": {
                    "run_ref": "candidate",
                    "run_id": "candidate-run",
                    "l1_cognitive_plan_digest": _digest("2"),
                    "l1_cognitive_advisory_digest": _digest("3"),
                    "c0_outcome_set_digest": _digest("4"),
                    "l1_cognitive_revision_set_digest": _digest("5"),
                    "l1_cognitive_treatment_execution_digest": _digest("6"),
                    "compiled_prompt_digest": _digest("7"),
                    "output_digest": _digest("8"),
                    "completion_status": "PASS",
                },
            }
        ],
    )

    with pytest.raises(
        L1CognitiveBlindReviewPacketError, match="provenance is invalid"
    ):
        build_l1_cognitive_blind_review_material(
            paired_receipt=receipt,
            run_roots={
                "pair-without-provenance": {
                    "control": control_root,
                    "candidate": candidate_root,
                }
            },
            repo_root=tmp_path,
            nonce="a" * 64,
        )
