"""CLI tests for the Apps RG-only L1 W5/W6 evidence handoff."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apps_rg.evals.l1_cognitive_evaluation_cli import main
from apps_rg.evals.l1_cognitive_outcome_protocol import (
    build_l1_cognitive_paired_shadow_receipt,
    load_l1_cognitive_outcome_protocol,
)
from apps_rg.evals.l1_cognitive_rollout_gate import seal_l1_cognitive_handoff_record


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _captured_pair(index: int) -> dict[str, object]:
    token = f"{index:03d}"
    return {
        "pair_id": f"pair-{token}",
        "frozen_input_digest": _digest(f"input-{token}"),
        "provider_model_config_digest": _digest("provider-config"),
        "tool_config_digest": _digest("tool-config"),
        "control": {
            "run_ref": f"control-{token}",
            "run_id": f"control-{token}",
            "l1_v2_capsule_digest": _digest(f"control-capsule-{token}"),
            "l1_cognitive_treatment_execution_digest": _digest(
                f"control-execution-{token}"
            ),
            "compiled_prompt_digest": _digest(f"control-prompt-{token}"),
            "output_digest": _digest(f"control-output-{token}"),
            "completion_status": "PASS",
        },
        "candidate": {
            "run_ref": f"candidate-{token}",
            "run_id": f"candidate-{token}",
            "l1_cognitive_plan_digest": _digest(f"candidate-plan-{token}"),
            "l1_cognitive_advisory_digest": _digest(f"candidate-advisory-{token}"),
            "c0_outcome_set_digest": _digest(f"c0-{token}"),
            "l1_cognitive_revision_set_digest": _digest(f"candidate-revision-{token}"),
            "l1_cognitive_treatment_execution_digest": _digest(
                f"candidate-execution-{token}"
            ),
            "compiled_prompt_digest": _digest(f"candidate-prompt-{token}"),
            "output_digest": _digest(f"candidate-output-{token}"),
            "completion_status": "PASS",
        },
    }


def test_w0_baseline_writes_a_non_qualifying_source_bound_receipt(
    tmp_path: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "w0_baseline.json"

    code = main(["w0-baseline", "--output", str(output)])

    assert code == 0
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["summary"]["dominant_failure_slice"] == (
        "COMPOUND_AND_RELATION_DECOMPOSITION"
    )
    assert receipt["authority"]["human_qualified"] is False
    rendered = capsys.readouterr().out
    assert '"status": "TECHNICAL_BASELINE_COMPLETE"' in rendered
    assert '"does_not_measure_candidate_quality": true' in rendered


def test_freeze_input_writes_a_source_bound_receipt(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    jd = tmp_path / "jd.txt"
    briefing = tmp_path / "briefing.txt"
    resume = tmp_path / "resume.json"
    output = tmp_path / "frozen_input.json"
    jd.write_text("Lead a regulated AI platform.", encoding="utf-8")
    briefing.write_text("Use the supplied record only.", encoding="utf-8")
    resume.write_text("{}", encoding="utf-8")

    code = main(
        [
            "freeze-input",
            "--target-company",
            "Acme",
            "--target-role",
            "VP Engineering",
            "--target-level",
            "EXECUTIVE",
            "--generation-mode",
            "strategic_tailor",
            "--jd",
            str(jd),
            "--briefing",
            str(briefing),
            "--resume",
            str(resume),
            "--output",
            str(output),
        ]
    )

    assert code == 0
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "apps_rg.l1_cognitive_pair_input.v2"
    assert receipt["inputs"]["job_description"]["u0_payload_digest"].startswith(
        "sha256:"
    )
    assert '"status": "PASS"' in capsys.readouterr().out


def test_assemble_paired_cohort_writes_new_source_preserving_artifacts(
    tmp_path: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    protocol = load_l1_cognitive_outcome_protocol()
    source_paths: list[Path] = []
    for index in range(1, 4):
        source = tmp_path / f"pair-{index}.json"
        receipt = build_l1_cognitive_paired_shadow_receipt(
            protocol=protocol,
            pairs=[_captured_pair(index)],
        )
        source.write_text(json.dumps(receipt), encoding="utf-8")
        source_paths.append(source)
    combined = tmp_path / "combined.json"
    manifest = tmp_path / "cohort.json"

    code = main(
        [
            "assemble-paired-cohort",
            "--source-paired-receipt",
            str(source_paths[0]),
            "--source-paired-receipt",
            str(source_paths[1]),
            "--source-paired-receipt",
            str(source_paths[2]),
            "--paired-receipt-output",
            str(combined),
            "--cohort-manifest-output",
            str(manifest),
        ]
    )

    assert code == 0
    assert len(json.loads(combined.read_text(encoding="utf-8"))["pairs"]) == 3
    cohort = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(cohort["source_paired_receipts"]) == 3
    rendered = capsys.readouterr().out
    assert '"does_not_invoke_runtime": true' in rendered
    assert '"does_not_create_human_judgment": true' in rendered


def test_rollout_gate_writes_blocked_receipt_without_attempting_activation(
    tmp_path: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "rollout_gate.json"

    code = main(["rollout-gate", "--output", str(output)])

    assert code == 2
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "BLOCKED"
    assert receipt["authority"]["automatic_promotion"] is False
    assert receipt["authority"]["runtime_activation_performed"] is False
    assert '"status": "BLOCKED"' in capsys.readouterr().out


def test_seal_evidence_preserves_authored_content_without_attesting_to_it(
    tmp_path: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    authored = {
        "reviewer_identity_ref": "human-reviewer://reviewer-a",
        "blind_pair_id": "blind-pair-001",
        "variant_assessments": [],
    }
    source = tmp_path / "authored.json"
    output = tmp_path / "sealed.json"
    source.write_text(json.dumps(authored), encoding="utf-8")

    code = main(
        [
            "seal-evidence",
            "--input",
            str(source),
            "--digest-field",
            "record_digest",
            "--output",
            str(output),
        ]
    )

    assert code == 0
    assert json.loads(source.read_text(encoding="utf-8")) == authored
    assert json.loads(output.read_text(encoding="utf-8")) == (
        seal_l1_cognitive_handoff_record(authored, digest_field="record_digest")
    )
    rendered = capsys.readouterr().out
    assert '"status": "DIGEST_SEALED_NOT_VALIDATED"' in rendered
    assert '"does_not_create_human_judgment": true' in rendered
