from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from apps_rg.evals.authoritative.artifacts import (
    file_sha256,
    record_digest_matches,
    seal_record,
)
from apps_rg.evals.authoritative.controller import PLAN_SCHEMA, execute_controller_plan
from apps_rg.evals.authoritative.grounding import (
    GRAPH_SCHEMA,
    SOURCE_SCHEMA,
    SYSTEM_SCHEMA,
    TRUTH_SCHEMA,
    evaluate_authoritative_grounding,
)
from apps_rg.evals.authoritative.manifest import (
    SCORE_GROUPS,
    seal_evaluation_manifest,
    validate_evaluation_manifest,
)
from apps_rg.evals.authoritative.repeatability import (
    STABILITY_POLICY_SCHEMA,
    evaluate_controller_bound_repeatability,
)
from apps_rg.evals.authoritative.native_receipts import normalize_native_receipt_bundle
from apps_rg.evals.authoritative.retrieval import (
    QRELS_SCHEMA,
    RANKING_SCHEMA,
    UNIVERSE_SCHEMA,
    evaluate_authoritative_retrieval,
)
from apps_rg.evals.authoritative.reviews import (
    GROUNDING_INDEX_SCHEMA,
    SECTION_ADJUDICATION_SCHEMA,
    SECTION_GROUNDING_INDEX_SCHEMA,
    evaluate_authoritative_sections,
    evaluate_authoritative_whole_resume,
)
from apps_rg.evals.repeatability.evaluation import scenario_registry_digest
from apps_rg.evals.authoritative.validity import (
    AUTOMATED_RESULTS_SCHEMA,
    HUMAN_PILOT_SCHEMA,
    POLICY_SCHEMA,
    evaluate_authoritative_validity,
)
from apps_rg.evals.c03_ci_ratchet import build_ratchet_receipt
from apps_rg.evals.meta_eval.evaluation import run_meta_evaluation
from apps_rg.evals.receipt_validation import validate_artifact
from apps_rg.evals.resume_graph_calibration import main as run_resume_graph_calibration
from apps_rg.evals.section_quality_benchmark.validation import seal_review_bundle

_ROOT = Path(__file__).resolve().parents[2]
_SECTION_TEST = _ROOT / "tests" / "test_section_quality_benchmark.py"
_WHOLE_TEST = _ROOT / "whole_resume" / "tests" / "test_whole_resume.py"
_RUNTIME_STUB = Path(__file__).resolve().parent / "runtime_stub.py"
_HEX = "a" * 64


def test_standalone_control_plane_imports_without_ops_scripts() -> None:
    assert callable(validate_artifact)
    assert callable(run_resume_graph_calibration)


def test_evaluation_manifest_is_closed_and_externally_pinned() -> None:
    manifest = seal_evaluation_manifest(
        {
            "evaluation_id": "apps-rg-v2-authoritative-pilot",
            "source_commit": "1" * 40,
            "corpus_digest": "2" * 64,
            "graph_digest": "3" * 64,
            "authority_receipt_file_sha256": "4" * 64,
            "truth_bundle_digests": {
                score_group: f"{index:x}" * 64
                for index, score_group in enumerate(SCORE_GROUPS, 1)
            },
            "threshold_policy_digests": {
                score_group: f"{index:x}" * 64
                for index, score_group in enumerate(SCORE_GROUPS, 8)
            },
            "split_commitments": {"calibration": "9" * 64, "holdout": "a" * 64},
            "score_groups": list(SCORE_GROUPS),
            "release_authorizing": False,
        }
    )
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "evaluation_manifest.v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert not validate_evaluation_manifest(manifest, expected_digest=manifest["record_digest"])
    tampered = deepcopy(manifest)
    tampered["corpus_digest"] = "f" * 64
    assert "PINNED_RECORD_DIGEST_INVALID" in validate_evaluation_manifest(
        tampered, expected_digest=manifest["record_digest"]
    )
    implementation_receipt = json.loads(
        (_ROOT / "MEASUREMENT_VALIDITY_IMPLEMENTATION_RECEIPT.json").read_text(
            encoding="utf-8"
        )
    )
    assert record_digest_matches(implementation_receipt)


def _participant(cohort: str, name: str, roles: list[str], qualification: str) -> dict[str, Any]:
    identity = f"human-reviewer://{name}"
    return {
        "cohort": cohort,
        "identity_ref": identity,
        "identity_hash": hashlib.sha256(identity.encode()).hexdigest(),
        "roles": roles,
        "qualification_ref": qualification,
    }


def _authority(tmp_path: Path) -> tuple[Path, str, dict[str, Any]]:
    participants = [
        _participant("proof", "proof-1", ["primary"], "proof-qualified"),
        _participant("proof", "proof-2", ["primary"], "proof-qualified"),
        _participant("proof", "proof-adj", ["adjudicator"], "proof-qualified"),
        _participant("retrieval", "retrieval-1", ["primary"], "retrieval-qualified"),
        _participant("retrieval", "retrieval-2", ["primary"], "retrieval-qualified"),
        _participant("retrieval", "retrieval-adj", ["adjudicator"], "retrieval-qualified"),
        _participant("w9", "w9-1", ["primary"], "resume-coach://qualified"),
        _participant("w9", "w9-2", ["primary"], "resume-coach://qualified"),
        _participant("w9", "w9-adj", ["adjudicator"], "resume-coach://qualified"),
    ]
    receipt = seal_record(
        {
            "schema_version": "apps_rg.c03_human_eval.human_review_authority_receipt.v1",
            "authority_mode": "TRUSTED_HUMAN_ROSTER_APPROVAL",
            "official_authority_eligible": True,
            "packet_id": "authoritative-test-packet",
            "packet_manifest_digest": _HEX,
            "prelabel_packet_manifest_sha256": "b" * 64,
            "source_freeze_receipt_digest": "c" * 64,
            "cohort_manifest_digests": {
                "proof": "d" * 64,
                "retrieval": "e" * 64,
                "w9": "f" * 64,
            },
            "issuer_ref": "authority-issuer://test-owner",
            "approval_ref": "approval://test-only",
            "issued_at": "2026-08-01T00:00:00Z",
            "authorized_participants": participants,
            "unknown_is_pass": False,
        },
        digest_field="receipt_digest",
    )
    path = tmp_path / "human-authority.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path, file_sha256(path), receipt


def _retrieval_case(suffix: str, split: str) -> dict[str, Any]:
    candidate_ids = [f"candidate-{suffix}-{index}" for index in range(4)]
    universe = seal_record(
        {
            "schema_version": UNIVERSE_SCHEMA,
            "query_id": f"query-{suffix}",
            "query_text": "productivity leadership",
            "target_profile": "executive",
            "section": "experience",
            "graph_lane": "achievement",
            "employer": "Acme",
            "evidence_density": "MEDIUM",
            "corpus_digest": "1" * 64,
            "graph_digest": "2" * 64,
            "candidates": [
                {
                    "candidate_id": candidate_id,
                    "graph_path": ["person", f"achievement-{index}"],
                    "employer": "Acme" if index < 3 else "OtherCo",
                    "role": "Director",
                    "evidence_type": "achievement",
                    "metric_bearing": index == 0,
                }
                for index, candidate_id in enumerate(candidate_ids)
            ],
        }
    )
    ranking = seal_record(
        {
            "schema_version": RANKING_SCHEMA,
            "query_id": universe["query_id"],
            "universe_digest": universe["record_digest"],
            "split": split,
            "gate_k": 2,
            "ranking": [
                {"candidate_id": candidate_id, "rank": index + 1, "score": 1 - index / 10}
                for index, candidate_id in enumerate(candidate_ids)
            ],
        }
    )
    qrels = seal_record(
        {
            "schema_version": QRELS_SCHEMA,
            "query_id": universe["query_id"],
            "universe_digest": universe["record_digest"],
            "authority_receipt_file_sha256": "",
            "reviewer_identity_refs": [
                "human-reviewer://retrieval-1",
                "human-reviewer://retrieval-2",
            ],
            "adjudicator_identity_ref": "human-reviewer://retrieval-adj",
            "labels": [
                {
                    "candidate_id": candidate_id,
                    "reviewer_identity_refs": [
                        "human-reviewer://retrieval-1",
                        "human-reviewer://retrieval-2",
                    ],
                    "adjudication_status": "ADJUDICATED",
                    "adjudicator_identity_ref": "human-reviewer://retrieval-adj",
                    "relevance_grade": 3 if index < 2 else 0,
                    "expected_graph_path": ["person", f"achievement-{index}"],
                    "critical_hard_negative": index == 3,
                    "hard_negative_class": "WRONG_EMPLOYER" if index == 3 else "NONE",
                    "near_duplicate_of": None,
                    "jd_concepts": ["productivity"] if index < 2 else [],
                    "claim_ids": [f"claim-{suffix}-{index}"] if index < 2 else [],
                }
                for index, candidate_id in enumerate(candidate_ids)
            ],
        }
    )
    return {
        "universe": universe,
        "expected_universe_digest": universe["record_digest"],
        "ranking": ranking,
        "expected_ranking_digest": ranking["record_digest"],
        "qrels": qrels,
        "expected_qrels_digest": qrels["record_digest"],
    }


def test_retrieval_requires_external_universe_and_human_authority(tmp_path: Path) -> None:
    authority_path, authority_sha, _ = _authority(tmp_path)
    cases = [_retrieval_case("cal", "CALIBRATION"), _retrieval_case("hold", "HOLDOUT")]
    for case in cases:
        case["qrels"]["authority_receipt_file_sha256"] = authority_sha
        case["qrels"] = seal_record(case["qrels"])
        case["expected_qrels_digest"] = case["qrels"]["record_digest"]
    receipt = evaluate_authoritative_retrieval(
        cases,
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert receipt["status"] == "PASS"
    attacked = deepcopy(cases)
    universe = attacked[0]["universe"]
    universe["candidates"] = universe["candidates"][:2]
    attacked[0]["universe"] = seal_record(universe)
    attacked_receipt = evaluate_authoritative_retrieval(
        attacked,
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert attacked_receipt["status"] == "UNKNOWN"
    assert any("EXTERNAL_DIGEST" in reason for reason in attacked_receipt["unknown_reasons"])

    malformed = deepcopy(cases)
    malformed[0]["ranking"]["ranking"][0]["rank"] = "not-an-integer"
    malformed[0]["ranking"] = seal_record(malformed[0]["ranking"])
    malformed[0]["expected_ranking_digest"] = malformed[0]["ranking"]["record_digest"]
    malformed_receipt = evaluate_authoritative_retrieval(
        malformed,
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert malformed_receipt["status"] == "UNKNOWN"
    assert any(
        "SYSTEM_RANKS_INVALID" in reason
        for reason in malformed_receipt["unknown_reasons"]
    )
    unreviewed = deepcopy(cases)
    unreviewed[0]["qrels"]["labels"][0]["reviewer_identity_refs"] = [
        "human-reviewer://retrieval-1"
    ]
    unreviewed[0]["qrels"] = seal_record(unreviewed[0]["qrels"])
    unreviewed[0]["expected_qrels_digest"] = unreviewed[0]["qrels"]["record_digest"]
    unreviewed_receipt = evaluate_authoritative_retrieval(
        unreviewed,
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert unreviewed_receipt["status"] == "UNKNOWN"
    assert any(
        "LABEL_REVIEWER_COVERAGE_INVALID" in reason
        for reason in unreviewed_receipt["unknown_reasons"]
    )


def _grounding_inputs(authority_sha: str) -> dict[str, Any]:
    source_text = "At Acme, improved team productivity by 20 percent in 2024."
    source = seal_record(
        {
            "schema_version": SOURCE_SCHEMA,
            "sources": [
                {
                    "source_id": "source-1",
                    "text": source_text,
                    "content_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
                }
            ],
        }
    )
    graph = seal_record(
        {
            "schema_version": GRAPH_SCHEMA,
            "paths": [
                {
                    "path_id": "path-1",
                    "source_id": "source-1",
                    "nodes": ["person", "role-acme", "achievement-20"],
                }
            ],
        }
    )
    bindings = {
        "employer": "Acme",
        "role": "Director",
        "date": "2024",
        "metric": "20 percent",
        "credential": None,
        "scope": "team",
        "certainty": "achieved",
    }
    claim_text = "At Acme, improved team productivity by 20 percent in 2024."
    system = seal_record(
        {
            "schema_version": SYSTEM_SCHEMA,
            "claims": [
                {
                    "claim_id": "claim-1",
                    "claim_text": claim_text,
                    "source_id": "source-1",
                    "locator": {"start": 0, "end": len(source_text)},
                    "graph_path_id": "path-1",
                    "predicted_bindings": bindings,
                    "predicted_support_disposition": "SUPPORTED",
                }
            ],
        }
    )
    truth = seal_record(
        {
            "schema_version": TRUTH_SCHEMA,
            "authority_receipt_file_sha256": authority_sha,
            "reviewer_identity_refs": [
                "human-reviewer://proof-1",
                "human-reviewer://proof-2",
            ],
            "adjudicator_identity_ref": "human-reviewer://proof-adj",
            "labels": [
                {
                    "claim_id": "claim-1",
                    "reviewer_identity_refs": [
                        "human-reviewer://proof-1",
                        "human-reviewer://proof-2",
                    ],
                    "adjudication_status": "ADJUDICATED",
                    "adjudicator_identity_ref": "human-reviewer://proof-adj",
                    "claim_text_digest": hashlib.sha256(claim_text.encode()).hexdigest(),
                    "source_excerpt_digest": hashlib.sha256(source_text.encode()).hexdigest(),
                    "expected_graph_path": ["person", "role-acme", "achievement-20"],
                    "expected_bindings": bindings,
                    "inflation_fields": [],
                    "materiality": "MATERIAL",
                    "entailment_grade": "FULL",
                    "components": [{"component_id": "claim-1-all", "entailment_grade": "FULL"}],
                }
            ],
        }
    )
    return {"source": source, "graph": graph, "system": system, "truth": truth}


def test_grounding_resolves_source_bytes_and_rejects_self_resealed_fiction(tmp_path: Path) -> None:
    authority_path, authority_sha, _ = _authority(tmp_path)
    values = _grounding_inputs(authority_sha)
    receipt = evaluate_authoritative_grounding(
        source_bundle=values["source"],
        expected_source_digest=values["source"]["record_digest"],
        graph_snapshot=values["graph"],
        expected_graph_digest=values["graph"]["record_digest"],
        system_claims=values["system"],
        expected_system_digest=values["system"]["record_digest"],
        truth_bundle=values["truth"],
        expected_truth_digest=values["truth"]["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert receipt["status"] == "PASS"
    attacked = deepcopy(values["system"])
    attacked["claims"][0]["claim_text"] = "Invented claim."
    attacked = seal_record(attacked)
    blocked = evaluate_authoritative_grounding(
        source_bundle=values["source"],
        expected_source_digest=values["source"]["record_digest"],
        graph_snapshot=values["graph"],
        expected_graph_digest=values["graph"]["record_digest"],
        system_claims=attacked,
        expected_system_digest=values["system"]["record_digest"],
        truth_bundle=values["truth"],
        expected_truth_digest=values["truth"]["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert blocked["status"] == "UNKNOWN"

    assert "PINNED_RECORD_DIFFERS_FROM_EXTERNAL_DIGEST" in blocked["unknown_reasons"]


def test_section_and_whole_resume_require_rostered_reviewers(tmp_path: Path) -> None:
    authority_path, authority_sha, authority = _authority(tmp_path)
    section_helpers = runpy.run_path(str(_SECTION_TEST))
    section_input = section_helpers["_input_bundle"]()
    reviews = section_helpers["_review_bundle"](section_input, reviewer_classes=("HUMAN",))
    expanded = []
    for review in reviews["reviews"]:
        first = deepcopy(review)
        first["reviewer_identity_ref"] = "human-reviewer://w9-1"
        second = deepcopy(review)
        second["review_id"] = f"{review['review_id']}-second"
        second["reviewer_identity_ref"] = "human-reviewer://w9-2"
        expanded.extend((first, second))
    reviews["reviews"] = expanded
    reviews = seal_review_bundle(reviews, section_input)
    adjudications = seal_record(
        {
            "schema_version": SECTION_ADJUDICATION_SCHEMA,
            "input_bundle_digest": section_input["bundle_digest"],
            "review_bundle_digest": reviews["bundle_digest"],
            "authority_receipt_file_sha256": authority_sha,
            "adjudications": [
                {
                    "case_id": case["case_id"],
                    "review_ids": [
                        review["review_id"]
                        for review in reviews["reviews"]
                        if review["case_id"] == case["case_id"]
                    ],
                    "adjudicator_identity_ref": "human-reviewer://w9-adj",
                    "qualification_ref": "resume-coach://qualified",
                }
                for case in section_input["lane_cases"]
            ],
        }
    )
    section_grounding_index = seal_record(
        {
            "schema_version": SECTION_GROUNDING_INDEX_SCHEMA,
            "authority_receipt_file_sha256": authority_sha,
            "artifacts": {
                artifact["artifact_id"]: {
                    "gate_id": "G3",
                    "status": "PASS",
                    "source_receipt_digest": "9" * 64,
                }
                for case in section_input["lane_cases"]
                for artifact in (case["candidate"], case.get("baseline"))
                if artifact is not None
            },
        }
    )
    section_receipt = evaluate_authoritative_sections(
        section_input,
        reviews,
        adjudication_bundle=adjudications,
        expected_adjudication_digest=adjudications["record_digest"],
        grounding_index=section_grounding_index,
        expected_grounding_index_digest=section_grounding_index["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert section_receipt["status"] == "PASS"
    untrusted = deepcopy(reviews)
    untrusted["reviews"][0]["reviewer_identity_ref"] = "reviewer://self-declared"
    untrusted = seal_review_bundle(untrusted, section_input)
    blocked_section = evaluate_authoritative_sections(
        section_input,
        untrusted,
        adjudication_bundle=adjudications,
        expected_adjudication_digest=adjudications["record_digest"],
        grounding_index=section_grounding_index,
        expected_grounding_index_digest=section_grounding_index["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert blocked_section["status"] == "UNKNOWN"
    ungrounded = deepcopy(section_grounding_index)
    first_artifact = next(iter(ungrounded["artifacts"].values()))
    first_artifact["status"] = "FAIL"
    ungrounded = seal_record(ungrounded)
    blocked_grounding = evaluate_authoritative_sections(
        section_input,
        reviews,
        adjudication_bundle=adjudications,
        expected_adjudication_digest=adjudications["record_digest"],
        grounding_index=ungrounded,
        expected_grounding_index_digest=ungrounded["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert blocked_grounding["status"] == "UNKNOWN"
    assert "SECTION_ARTIFACT_G3_BINDING_NONPASS" in blocked_grounding["unknown_reasons"]

    whole_helpers = runpy.run_path(str(_WHOLE_TEST))
    whole_bundle = whole_helpers["_bundle"]()
    for pair in whole_bundle["pairs"]:
        for index, review in enumerate(pair["reviews"], 1):
            review["reviewer_identity_ref"] = f"human-reviewer://w9-{index}"
            review["qualification_ref"] = "resume-coach://qualified"
    whole_bundle["human_review_evidence"]["authority_receipt_digest"] = authority["receipt_digest"]
    whole_helpers["_rebind"](whole_bundle)
    grounded: dict[str, Any] = {}
    for pair in whole_bundle["pairs"]:
        key = "resume_a" if pair["candidate_variant"] == "A" else "resume_b"
        for section in pair[key]["sections"]:
            for claim in section["claims"]:
                if claim["material"] is True:
                    grounded[claim["claim_id"]] = {
                        "gate_id": "G3",
                        "status": "PASS",
                        "source_receipt_digest": "9" * 64,
                    }
    grounding_index = seal_record(
        {
            "schema_version": GROUNDING_INDEX_SCHEMA,
            "authority_receipt_file_sha256": authority_sha,
            "claims": grounded,
        }
    )
    whole_receipt = evaluate_authoritative_whole_resume(
        whole_bundle,
        expected_bundle_digest=whole_bundle["bundle_digest"],
        grounding_index=grounding_index,
        expected_grounding_index_digest=grounding_index["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert whole_receipt["status"] == "PASS"
    changed_whole = deepcopy(whole_bundle)
    changed_section = changed_whole["pairs"][0]["resume_a"]["sections"][0]
    changed_section["text"] += " Changed."
    changed_section["claims"][0]["text"] += " Changed."
    whole_helpers["_rebind"](changed_whole)
    blocked_whole = evaluate_authoritative_whole_resume(
        changed_whole,
        expected_bundle_digest=whole_bundle["bundle_digest"],
        grounding_index=grounding_index,
        expected_grounding_index_digest=grounding_index["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert blocked_whole["status"] == "UNKNOWN"
    assert (
        "WHOLE_RESUME_BUNDLE_DIFFERS_FROM_EXTERNAL_DIGEST"
        in blocked_whole["unknown_reasons"]
    )


def _semantic_result(disposition: str) -> dict[str, Any]:
    return {
        "retrieved_candidate_ids": ["candidate-a", "candidate-b"],
        "selected_evidence_ids": ["evidence-a"],
        "selected_graph_path_ids": ["path-a"],
        "material_claim_ids": ["claim-a"],
        "bindings": {"claim-a": {"employer": "Acme", "date": "2024"}},
        "section_decisions": {"experience": ["claim-a"]},
        "grounding_dispositions": {"claim-a": "SUPPORTED"},
        "final_disposition": disposition,
        "output_quality_scores": {"grounding": 4, "relevance": 4},
        "output_text_by_section": {"experience": "Acceptable wording."},
    }


def test_repeatability_requires_actual_controller_receipts(tmp_path: Path) -> None:
    expected = {
        "rich_evidence": "GENERATE",
        "sparse_evidence": "ESCALATE",
        "conflicting_dates": "ESCALATE",
        "same_metric_multiple_employers": "ESCALATE",
        "similar_achievements_across_roles": "GENERATE",
        "missing_metric": "ABSTAIN",
        "unsupported_user_requested_claim": "ABSTAIN",
        "jd_prompt_injection": "ESCALATE",
        "requested_date_inflation": "ESCALATE",
        "requested_title_inflation": "ESCALATE",
        "legitimate_omission_vs_escalation": "GENERATE",
    }
    assert scenario_registry_digest()
    workdir = tmp_path / "controller-workdir"
    workdir.mkdir()
    subprocess.run(["git", "-C", str(workdir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(workdir), "config", "user.email", "tests@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(workdir), "config", "user.name", "Apps RG tests"],
        check=True,
        capture_output=True,
    )
    (workdir / "controller-source.txt").write_text("controller source\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(workdir), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(workdir), "commit", "-m", "controller source"],
        check=True,
        capture_output=True,
    )
    source_commit = subprocess.check_output(
        ["git", "-C", str(workdir), "rev-parse", "HEAD"], text=True
    ).strip()
    scenarios = []
    for scenario_id, disposition in expected.items():
        input_path = tmp_path / f"{scenario_id}.json"
        input_path.write_text(json.dumps(_semantic_result(disposition)), encoding="utf-8")
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "input_path": str(input_path),
                "command": [sys.executable, str(_RUNTIME_STUB)],
                "workdir": str(workdir),
                "execution_count": 3,
            }
        )
    plan = seal_record(
        {
            "schema_version": PLAN_SCHEMA,
            "evaluation_id": "controller-test",
            "controller_id": "controller://pytest",
            "source_commit": source_commit,
            "timeout_seconds": 30,
            "scenarios": scenarios,
        }
    )
    run_set, controller = execute_controller_plan(
        plan,
        output_root=tmp_path / "controller-output",
        expected_plan_digest=plan["record_digest"],
    )
    policy = seal_record(
        {
            "schema_version": STABILITY_POLICY_SCHEMA,
            "minimum_stability": {
                "retrieved_candidate_stability": 1.0,
                "evidence_selection_stability": 1.0,
                "material_claim_identity_stability": 1.0,
                "binding_stability": 1.0,
                "grounding_disposition_stability": 1.0,
                "semantic_output_stability": 1.0,
                "output_quality_score_stability": 1.0,
            },
        }
    )
    receipt = evaluate_controller_bound_repeatability(
        run_set,
        controller_manifest=controller,
        expected_controller_manifest_digest=controller["record_digest"],
        stability_policy=policy,
        expected_stability_policy_digest=policy["record_digest"],
        expected_source_commit=source_commit,
    )
    assert receipt["status"] == "PASS"
    forged = deepcopy(controller)
    forged["execution_receipts"][0]["controller_nonce"] = "forged"
    forged = seal_record(forged)
    blocked = evaluate_controller_bound_repeatability(
        run_set,
        controller_manifest=forged,
        expected_controller_manifest_digest=controller["record_digest"],
        stability_policy=policy,
        expected_stability_policy_digest=policy["record_digest"],
        expected_source_commit=source_commit,
    )
    assert blocked["status"] == "UNKNOWN"

    wrong_source = seal_record(
        {
            **{key: value for key, value in plan.items() if key != "record_digest"},
            "source_commit": "0" * 40,
        }
    )
    with pytest.raises(
        RuntimeError, match="HEAD does not match declared source_commit"
    ):
        execute_controller_plan(
            wrong_source,
            output_root=tmp_path / "wrong-source-output",
            expected_plan_digest=wrong_source["record_digest"],
        )
    assert not (tmp_path / "wrong-source-output").exists()


def test_evaluator_validity_uses_authorized_human_criterion_labels(tmp_path: Path) -> None:
    authority_path, authority_sha, _ = _authority(tmp_path)
    machine = run_meta_evaluation()
    results = [
        {"item_id": f"pilot-{index}", "grader_id": "G3", "status": "PASS" if index < 20 else "FAIL"}
        for index in range(40)
    ]
    automated = seal_record(
        {"schema_version": AUTOMATED_RESULTS_SCHEMA, "results": results}
    )
    human = seal_record(
        {
            "schema_version": HUMAN_PILOT_SCHEMA,
            "authority_receipt_file_sha256": authority_sha,
            "reviewer_identity_refs": [
                "human-reviewer://proof-1",
                "human-reviewer://proof-2",
            ],
            "adjudicator_identity_ref": "human-reviewer://proof-adj",
            "labels": [
                {
                    **result,
                    "reviewer_identity_refs": [
                        "human-reviewer://proof-1",
                        "human-reviewer://proof-2",
                    ],
                    "adjudication_status": "ADJUDICATED",
                    "adjudicator_identity_ref": "human-reviewer://proof-adj",
                }
                for result in results
            ],
        }
    )
    policy = seal_record(
        {
            "schema_version": POLICY_SCHEMA,
            "minimum_sample_size": 40,
            "minimum_positive_sample_size": 20,
            "minimum_negative_sample_size": 20,
            "minimum_exact_agreement": 0.95,
            "maximum_false_positive_upper_95": 0.2,
            "maximum_false_negative_upper_95": 0.2,
        }
    )
    receipt = evaluate_authoritative_validity(
        machine_receipt=machine,
        expected_machine_receipt_digest=machine["record_digest"],
        automated_results=automated,
        expected_automated_results_digest=automated["record_digest"],
        human_pilot=human,
        expected_human_pilot_digest=human["record_digest"],
        policy=policy,
        expected_policy_digest=policy["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert receipt["status"] == "PASS"
    assert receipt["metrics"]["human_grader_agreement"] == 1.0
    assert receipt["metrics"]["cross_grader_isolation_rate"] == 1.0
    one_class_human = deepcopy(human)
    for label in one_class_human["labels"]:
        label["status"] = "PASS"
    one_class_human = seal_record(one_class_human)
    one_class_automated = deepcopy(automated)
    for result in one_class_automated["results"]:
        result["status"] = "PASS"
    one_class_automated = seal_record(one_class_automated)
    one_class_receipt = evaluate_authoritative_validity(
        machine_receipt=machine,
        expected_machine_receipt_digest=machine["record_digest"],
        automated_results=one_class_automated,
        expected_automated_results_digest=one_class_automated["record_digest"],
        human_pilot=one_class_human,
        expected_human_pilot_digest=one_class_human["record_digest"],
        policy=policy,
        expected_policy_digest=policy["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha,
    )
    assert one_class_receipt["status"] == "UNKNOWN"
    assert any(
        "MINIMUM_NEGATIVE_SAMPLE_SIZE" in reason
        for reason in one_class_receipt["unknown_reasons"]
    )


def _native(
    status: str,
    authority: dict[str, Any],
    *,
    schema_version: str,
    gate_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": schema_version,
            "status": status,
            "metrics": {},
            "failure_codes": [],
            "unknown_reasons": [],
            "authority": authority,
            **({"gate_id": gate_id} if gate_id is not None else {}),
            **extra,
        }
    )


def test_ci_source_bound_mode_derives_receipts_and_rejects_forged_source_digest(
    tmp_path: Path,
) -> None:
    human = {"human_authority_verified": True}
    quality = {"human_authority_verified": True, "source_grounding_verified": True}
    grounding_native = _native(
        "PASS",
        human,
        schema_version="apps_rg.authoritative_grounding_receipt.v1",
        gate_results={
            "G2": {
                "gate_id": "G2",
                "status": "PASS",
                "metrics": {},
                "failure_codes": [],
                "unknown_reasons": [],
            },
            "G3": {
                "gate_id": "G3",
                "status": "PASS",
                "metrics": {"unsupported_material_claim_count": 0},
                "failure_codes": [],
                "unknown_reasons": [],
            },
        },
    )
    natives = {
        "retrieval_quality": _native(
            "PASS",
            human,
            schema_version="apps_rg.authoritative_retrieval_receipt.v1",
            gate_id="G1",
        ),
        "binding_accuracy": grounding_native,
        "factual_grounding": grounding_native,
        "section_quality": _native(
            "PASS",
            quality,
            schema_version="apps_rg.authoritative_section_quality_receipt.v1",
            source_report={"status": "PASS", "metrics": {}, "failure_codes": []},
        ),
        "whole_resume_quality": _native(
            "PASS",
            quality,
            schema_version="apps_rg.authoritative_whole_resume_receipt.v1",
            source_report={"status": "PASS", "metrics": {}, "failure_codes": []},
        ),
        "runtime_repeatability": _native(
            "PASS",
            {"runtime_execution_proven": True},
            schema_version="apps_rg.authoritative_repeatability_receipt.v1",
            gate_id="G5",
        ),
        "evaluator_validity": _native(
            "PASS",
            {
                "machine_critical_grader_validation_complete": True,
                "human_agreement_pilot_complete": True,
            },
            schema_version="apps_rg.authoritative_evaluator_validity_receipt.v1",
            gate_id="G6",
        ),
    }
    source_digests = {name: receipt["record_digest"] for name, receipt in natives.items()}
    baselines = {name: f"baseline::{name}::v1" for name in natives}
    normalized = normalize_native_receipt_bundle(
        natives,
        expected_source_digests=source_digests,
        baseline_signatures=baselines,
    )
    ci_helpers = runpy.run_path(str(_ROOT / "tests" / "test_c03_ci_sealed_receipts.py"))
    strict = tmp_path / "strict.xml"
    baseline = tmp_path / "baseline.xml"
    ci_helpers["_junit"](strict)
    ci_helpers["_junit"](baseline, baseline=True)
    receipt = build_ratchet_receipt(
        strict_junit=strict,
        baseline_junit=baseline,
        source_commit="source",
        base_commit="base",
        evaluation_receipts=normalized,
        expected_baselines=baselines,
        evaluation_receipts_source_bound=True,
    )
    assert receipt["status"] == "PASS"
    assert receipt["evaluation_receipt_mode"] == "SOURCE_BOUND_ALL_SCORE_GROUPS"
    forged_digests = dict(source_digests)
    forged_digests["retrieval_quality"] = "0" * 64
    forged = normalize_native_receipt_bundle(
        natives,
        expected_source_digests=forged_digests,
        baseline_signatures=baselines,
    )
    blocked = build_ratchet_receipt(
        strict_junit=strict,
        baseline_junit=baseline,
        source_commit="source",
        base_commit="base",
        evaluation_receipts=forged,
        expected_baselines=baselines,
        evaluation_receipts_source_bound=True,
    )
    assert blocked["status"] == "FAIL"

    malformed_native = _native(
        "PASS",
        human,
        schema_version="apps_rg.authoritative_grounding_receipt.v1",
        gate_results="caller-controlled-non-object",
    )
    normalized_malformed = normalize_native_receipt_bundle(
        {**natives, "binding_accuracy": malformed_native},
        expected_source_digests={
            **source_digests,
            "binding_accuracy": malformed_native["record_digest"],
        },
        baseline_signatures=baselines,
    )
    assert normalized_malformed["binding_accuracy"]["status"] == "UNKNOWN"
    machine_only_validity = _native(
        "PASS",
        {
            "machine_critical_grader_validation_complete": True,
            "human_agreement_pilot_complete": False,
        },
        schema_version="apps_rg.authoritative_evaluator_validity_receipt.v1",
        gate_id="G6",
    )
    normalized_machine_only = normalize_native_receipt_bundle(
        {**natives, "evaluator_validity": machine_only_validity},
        expected_source_digests={
            **source_digests,
            "evaluator_validity": machine_only_validity["record_digest"],
        },
        baseline_signatures=baselines,
    )
    assert normalized_machine_only["evaluator_validity"]["status"] == "UNKNOWN"
