from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from apps_rg.evals.authoritative.artifacts import file_sha256, seal_record
from apps_rg.evals.authoritative.cluster_retrieval import (
    CLUSTER_QRELS_SCHEMA,
    CLUSTER_RANKING_SCHEMA,
    CLUSTER_THRESHOLD_POLICY_SCHEMA,
    CLUSTER_UNIVERSE_SCHEMA,
    LOGICAL_RETRIEVAL_UNIT,
    QUALIFICATION_SCOPE,
    evaluate_authoritative_cluster_retrieval,
    seal_cluster_authority_bindings,
)

_HEX = "a" * 64
_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"


def _participant(name: str, roles: list[str]) -> dict[str, Any]:
    identity = f"human-reviewer://{name}"
    return {
        "cohort": "retrieval",
        "identity_ref": identity,
        "identity_hash": hashlib.sha256(identity.encode()).hexdigest(),
        "roles": roles,
        "qualification_ref": "retrieval-qualified",
    }


def _authority(tmp_path: Path) -> tuple[Path, str]:
    receipt = seal_record(
        {
            "schema_version": (
                "apps_rg.c03_human_eval.human_review_authority_receipt.v1"
            ),
            "authority_mode": "TRUSTED_HUMAN_ROSTER_APPROVAL",
            "official_authority_eligible": True,
            "packet_id": "cluster-eval-w1-test",
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
            "issued_at": "2026-08-02T00:00:00Z",
            "authorized_participants": [
                _participant("cluster-retrieval-1", ["primary"]),
                _participant("cluster-retrieval-2", ["primary"]),
                _participant("cluster-retrieval-adj", ["adjudicator"]),
            ],
            "unknown_is_pass": False,
        },
        digest_field="receipt_digest",
    )
    path = tmp_path / "human-authority.json"
    path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return path, file_sha256(path)


def _static_bindings() -> dict[str, str]:
    return {
        "graph_sha256": "1" * 64,
        "cluster_registry_sha256": "2" * 64,
        "corpus_sha256": "3" * 64,
        "model_artifact_sha256": "4" * 64,
        "projection_sha256": "5" * 64,
        "runtime_config_sha256": "6" * 64,
    }


def _threshold_policy(runtime_top_k: int = 2) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_THRESHOLD_POLICY_SCHEMA,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "runtime_top_k": runtime_top_k,
            "positive_relevance_floor": 2.0,
            "metric_thresholds": {
                "recall_at_runtime_k_minimum": 0.8,
                "ndcg_at_runtime_k_minimum": 0.8,
                "mrr_minimum": 0.8,
                "hard_negative_rejection_rate_minimum": 1.0,
                "top_k_redundancy_rate_maximum": 0.0,
            },
            "authority_bindings": seal_cluster_authority_bindings(
                _static_bindings()
            ),
        }
    )


def _case(suffix: str, split: str, authority_sha256: str) -> dict[str, Any]:
    query_text = f"product operations leadership {suffix}"
    bindings = seal_cluster_authority_bindings(
        {
            **_static_bindings(),
            "query_sha256": hashlib.sha256(query_text.encode()).hexdigest(),
        }
    )
    cluster_ids = [f"cluster-{suffix}-{index}" for index in range(4)]
    universe = seal_record(
        {
            "schema_version": CLUSTER_UNIVERSE_SCHEMA,
            "query_id": f"query-{suffix}",
            "query_text": query_text,
            "target_profile": "executive",
            "section": "experience",
            "graph_lane": "achievement",
            "employer": "Acme",
            "evidence_density": "MEDIUM",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "authority_bindings": bindings,
            "clusters": [
                {
                    "cluster_id": cluster_id,
                    "cluster_kind": (
                        "role_episode" if index < 2 else "capability_evidence"
                    ),
                    "cluster_authority_envelope_sha256": f"{index + 7:x}" * 64,
                    "member_node_ids": [f"node-{suffix}-{index}"],
                    "linked_fact_ids": [f"fact-{suffix}-{index}"],
                    "allowed_sections": ["experience"],
                    "activation_status": "ACTIVE_CONFIRMED",
                    "external_claim_policy": "source_bound_only",
                    "graph_path": ["person", f"node-{suffix}-{index}"],
                    "employer": "Acme" if index < 3 else "OtherCo",
                    "role": "Director",
                    "evidence_type": "role_episode",
                    "metric_bearing": index == 0,
                }
                for index, cluster_id in enumerate(cluster_ids)
            ],
        }
    )
    ranking = seal_record(
        {
            "schema_version": CLUSTER_RANKING_SCHEMA,
            "query_id": universe["query_id"],
            "universe_digest": universe["record_digest"],
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "authority_bindings": bindings,
            "split": split,
            "gate_k": 2,
            "ranking": [
                {"cluster_id": cluster_id, "rank": index + 1, "score": 1 - index / 10}
                for index, cluster_id in enumerate(cluster_ids)
            ],
        }
    )
    qrels = seal_record(
        {
            "schema_version": CLUSTER_QRELS_SCHEMA,
            "query_id": universe["query_id"],
            "universe_digest": universe["record_digest"],
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "authority_bindings": bindings,
            "authority_receipt_file_sha256": authority_sha256,
            "reviewer_identity_refs": [
                "human-reviewer://cluster-retrieval-1",
                "human-reviewer://cluster-retrieval-2",
            ],
            "adjudicator_identity_ref": (
                "human-reviewer://cluster-retrieval-adj"
            ),
            "labels": [
                {
                    "cluster_id": cluster_id,
                    "reviewer_identity_refs": [
                        "human-reviewer://cluster-retrieval-1",
                        "human-reviewer://cluster-retrieval-2",
                    ],
                    "adjudication_status": "ADJUDICATED",
                    "adjudicator_identity_ref": (
                        "human-reviewer://cluster-retrieval-adj"
                    ),
                    "relevance_grade": 3 if index < 2 else 0,
                    "expected_graph_path": [
                        "person",
                        f"node-{suffix}-{index}",
                    ],
                    "critical_hard_negative": index == 3,
                    "hard_negative_class": (
                        "WRONG_EMPLOYER" if index == 3 else "NONE"
                    ),
                    "near_duplicate_cluster_id": None,
                    "jd_concepts": ["productivity"] if index < 2 else [],
                    "claim_ids": [f"claim-{suffix}-{index}"] if index < 2 else [],
                }
                for index, cluster_id in enumerate(cluster_ids)
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


def _rebind_case(case: dict[str, Any]) -> None:
    case["universe"] = seal_record(case["universe"])
    case["expected_universe_digest"] = case["universe"]["record_digest"]
    for name in ("ranking", "qrels"):
        case[name]["universe_digest"] = case["universe"]["record_digest"]
        case[name] = seal_record(case[name])
        case[f"expected_{name}_digest"] = case[name]["record_digest"]


def _evaluate(
    tmp_path: Path,
    *,
    cases: list[dict[str, Any]] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    authority_path, authority_sha256 = _authority(tmp_path)
    selected_policy = policy or _threshold_policy()
    selected_cases = cases or [
        _case("cal", "CALIBRATION", authority_sha256),
        _case("hold", "HOLDOUT", authority_sha256),
    ]
    return evaluate_authoritative_cluster_retrieval(
        selected_cases,
        threshold_policy=selected_policy,
        expected_threshold_policy_digest=selected_policy["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha256,
    )


def test_cluster_retrieval_uses_cluster_ids_and_runtime_top_k(tmp_path: Path) -> None:
    receipt = _evaluate(tmp_path)

    assert receipt["status"] == "PASS"
    assert receipt["logical_retrieval_unit"] == LOGICAL_RETRIEVAL_UNIT
    assert receipt["qualification_scope"] == QUALIFICATION_SCOPE
    assert receipt["runtime_top_k"] == 2
    assert receipt["metrics"]["recall_at_2"] == 1.0
    assert receipt["metrics"]["ndcg_at_2"] == 1.0
    assert receipt["metrics"]["pooled_recall_at_2"] == 1.0
    assert receipt["authority"]["human_authority_verified"] is True
    assert receipt["authority"]["release_authorizing"] is False
    assert receipt["threshold_policy_digest"]
    assert receipt["generic_receipt_digest"]
    assert set(receipt["input_digests"]) == {"query-cal", "query-hold"}


def test_cluster_retrieval_contract_schemas_are_closed_and_valid(
    tmp_path: Path,
) -> None:
    authority_path, authority_sha256 = _authority(tmp_path)
    case = _case("cal", "CALIBRATION", authority_sha256)
    holdout = _case("hold", "HOLDOUT", authority_sha256)
    policy = _threshold_policy()
    receipt = evaluate_authoritative_cluster_retrieval(
        [case, holdout],
        threshold_policy=policy,
        expected_threshold_policy_digest=policy["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha256,
    )
    fixtures = {
        "cluster_candidate_universe.v1.schema.json": case["universe"],
        "cluster_system_ranking.v1.schema.json": case["ranking"],
        "cluster_retrieval_qrels.v1.schema.json": case["qrels"],
        "cluster_retrieval_threshold_policy.v1.schema.json": policy,
        "cluster_retrieval_receipt.v1.schema.json": receipt,
    }
    for filename, fixture in fixtures.items():
        schema = json.loads((_SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(fixture)


def test_cluster_retrieval_rejects_legacy_skill_identity(tmp_path: Path) -> None:
    authority_path, authority_sha256 = _authority(tmp_path)
    cases = [
        _case("cal", "CALIBRATION", authority_sha256),
        _case("hold", "HOLDOUT", authority_sha256),
    ]
    cases[0]["universe"]["clusters"][0]["skill_id"] = "legacy-skill"
    _rebind_case(cases[0])
    policy = _threshold_policy()

    receipt = evaluate_authoritative_cluster_retrieval(
        cases,
        threshold_policy=policy,
        expected_threshold_policy_digest=policy["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha256,
    )

    assert receipt["status"] == "UNKNOWN"
    assert any(
        "LEGACY_SKILL_OR_ASSERTION_ID_FORBIDDEN" in reason
        for reason in receipt["unknown_reasons"]
    )


def test_cluster_retrieval_rejects_corpus_sized_top_k(tmp_path: Path) -> None:
    policy = _threshold_policy(runtime_top_k=4)
    receipt = _evaluate(tmp_path, policy=policy)

    assert receipt["status"] == "UNKNOWN"
    assert any(
        "CLUSTER_TOP_K_NOT_BOUNDED" in reason
        for reason in receipt["unknown_reasons"]
    )


def test_cluster_retrieval_rejects_binding_drift(tmp_path: Path) -> None:
    authority_path, authority_sha256 = _authority(tmp_path)
    cases = [
        _case("cal", "CALIBRATION", authority_sha256),
        _case("hold", "HOLDOUT", authority_sha256),
    ]
    changed = dict(cases[0]["ranking"]["authority_bindings"])
    changed.pop("authority_envelope_sha256")
    changed["projection_sha256"] = "f" * 64
    cases[0]["ranking"]["authority_bindings"] = (
        seal_cluster_authority_bindings(changed)
    )
    cases[0]["ranking"] = seal_record(cases[0]["ranking"])
    cases[0]["expected_ranking_digest"] = cases[0]["ranking"]["record_digest"]
    policy = _threshold_policy()

    receipt = evaluate_authoritative_cluster_retrieval(
        cases,
        threshold_policy=policy,
        expected_threshold_policy_digest=policy["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha256,
    )

    assert receipt["status"] == "UNKNOWN"
    assert any(
        "CLUSTER_CASE_AUTHORITY_BINDING_MISMATCH" in reason
        for reason in receipt["unknown_reasons"]
    )
