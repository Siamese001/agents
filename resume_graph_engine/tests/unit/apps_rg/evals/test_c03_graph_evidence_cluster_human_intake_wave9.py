from __future__ import annotations

import copy
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from apps_rg.evals.c03_graph_evidence_cluster_human_intake import (
    ADJUDICATION_MANIFEST_SCHEMA_VERSION,
    CONTRACT_PATH,
    HUMAN_AUTHORITY_SCHEMA_VERSION,
    REVIEW_RETURN_MANIFEST_SCHEMA_VERSION,
    W9_RECEIPT_PATH,
    build_w9_blocked_receipt,
    collect_human_authority_issues,
    validate_completed_human_inputs,
    validate_human_intake_contract,
    validate_w9_receipt,
)
from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    QUERY_MANIFEST_PATH,
    collect_qrel_issues,
    ranking_identity_sha256,
)
from apps_rg.evals.c03_graph_evidence_cluster_review_packet import (
    W8_RECEIPT_PATH,
    build_prelabel_packet_content,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    REGISTRY_PATH,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

ROOT = Path(__file__).resolve().parents[4]
AUTHORITY_SIGNING_SECRET = "test-w9-authority-signing-secret-0123456789"


def _load(relative: Path | str) -> dict:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _complete_rankings(manifest: dict, registry: dict) -> dict[str, list[str]]:
    by_section = {
        str(section): sorted(
            str(cluster["cluster_id"])
            for cluster in registry["clusters"]
            if section in cluster["allowed_sections"]
        )
        for section in manifest["section_ids"]
    }
    return {
        f"{query['query_id']}|{section}": list(by_section[section])
        for query in manifest["queries"]
        for section in manifest["section_ids"]
    }


def _seal(value: dict, field: str) -> dict:
    sealed = dict(value)
    sealed[field] = canonical_sha256(sealed)
    return sealed


def _identity(value: str) -> str:
    return f"human-reviewer://{value}"


def _authority(
    *,
    w8: dict,
    packet_manifest: dict,
    identities: dict[str, str],
) -> dict:
    participants = []
    for distribution, identity_ref in identities.items():
        participants.append(
            {
                "distribution": distribution,
                "identity_ref": identity_ref,
                "identity_hash": hashlib.sha256(identity_ref.encode()).hexdigest(),
                "roles": (
                    ["adjudicator"]
                    if distribution == "adjudication"
                    else ["primary"]
                ),
                "qualification_ref": "cluster-relevance://qualified-human",
            }
        )
    authority = {
            "schema_version": HUMAN_AUTHORITY_SCHEMA_VERSION,
            "authority_mode": "TRUSTED_HUMAN_ROSTER_APPROVAL",
            "official_authority_eligible": True,
            "wave8_receipt_sha256": w8["receipt_sha256"],
            "packet_manifest_sha256": packet_manifest["manifest_sha256"],
            "packet_manifest_file_sha256": w8["controlled_packet"][
                "packet_manifest_file_sha256"
            ],
            "reviewer_cohort_manifest_sha256": w8["controlled_packet"][
                "reviewer_cohort_manifest_sha256"
            ],
            "issuer_ref": "authority-issuer://evaluation-owner",
            "approval_ref": "approval://cluster-human-review",
            "issued_at": "2026-08-02T22:00:00Z",
            "authorized_participants": participants,
            "unknown_is_pass": False,
    }
    signature_payload = json.dumps(
        authority, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    authority["external_signature"] = {
        "algorithm": "HMAC-SHA256",
        "key_id": "c03-w9-human-authority-v1",
        "signature": hmac.new(
            AUTHORITY_SIGNING_SECRET.encode("utf-8"), signature_payload, hashlib.sha256
        ).hexdigest(),
    }
    return _seal(authority, "receipt_digest")


def _grade(cluster_id: str) -> int:
    return int(hashlib.sha256(cluster_id.encode()).hexdigest()[0], 16) % 4


def _review_bundle(
    *,
    cohort: str,
    identity: str,
    packet: dict,
    packet_manifest: dict,
    source_items_sha: str,
    file_sha: str,
) -> dict:
    sealed_by_item = {
        row["item_ref"]: row
        for row in packet["sealed_mapping"]["cohorts"][cohort]
    }
    rows = []
    for item in packet["cohorts"][cohort]:
        sealed_candidates = {
            row["candidate_ref"]: row["cluster_id"]
            for row in sealed_by_item[item["item_ref"]]["candidates"]
        }
        rows.append(
            {
                "item_ref": item["item_ref"],
                "human_identity": identity,
                "candidate_grades": [
                    {
                        "candidate_ref": candidate["candidate_ref"],
                        "relevance_grade": _grade(
                            sealed_candidates[candidate["candidate_ref"]]
                        ),
                        "rationale": "Independent semantic relevance judgment.",
                    }
                    for candidate in item["candidates"]
                ],
            }
        )
    manifest = _seal(
        {
            "schema_version": REVIEW_RETURN_MANIFEST_SCHEMA_VERSION,
            "status": "COMPLETED_HUMAN_REVIEW",
            "cohort": cohort,
            "packet_manifest_sha256": packet_manifest["manifest_sha256"],
            "source_review_items_sha256": source_items_sha,
            "human_identity_ref": identity,
            "human_attestation": True,
            "qualification_ref": "cluster-relevance://qualified-human",
            "completed_at": "2026-08-02T22:30:00Z",
            "review_record_count": 48,
            "candidate_grade_count": 456,
            "reviews_file_sha256": file_sha,
        },
        "manifest_digest",
    )
    return {"manifest": manifest, "rows": rows, "observed_file_sha256": file_sha}


def _canonical_grade_maps(packet: dict) -> dict[str, dict[tuple[str, str, str], int]]:
    result: dict[str, dict[tuple[str, str, str], int]] = {}
    for cohort in ("reviewer_a", "reviewer_b"):
        values = {}
        for item in packet["sealed_mapping"]["cohorts"][cohort]:
            for candidate in item["candidates"]:
                key = (item["query_id"], item["section_id"], candidate["cluster_id"])
                values[key] = _grade(candidate["cluster_id"])
        result[cohort] = values
    return result


def _adjudication_bundle(
    *,
    identity: str,
    packet: dict,
    packet_manifest: dict,
    reviews: dict[str, dict],
    file_sha: str,
) -> dict:
    grades = _canonical_grade_maps(packet)
    sealed_by_item = {
        row["item_ref"]: row
        for row in packet["sealed_mapping"]["cohorts"]["reviewer_a"]
    }
    rows = []
    for item in packet["cohorts"]["reviewer_a"]:
        sealed_item = sealed_by_item[item["item_ref"]]
        cluster_by_ref = {
            row["candidate_ref"]: row["cluster_id"]
            for row in sealed_item["candidates"]
        }
        candidates = []
        for visible in item["candidates"]:
            cluster_id = cluster_by_ref[visible["candidate_ref"]]
            key = (sealed_item["query_id"], sealed_item["section_id"], cluster_id)
            primary = [grades[cohort][key] for cohort in ("reviewer_a", "reviewer_b")]
            candidates.append(
                {
                    "candidate_ref": visible["candidate_ref"],
                    "primary_grades": primary,
                    "final_relevance_grade": primary[0],
                    "rationale": "Independent final human adjudication.",
                }
            )
        rows.append(
            {
                "item_ref": item["item_ref"],
                "adjudicator_identity": identity,
                "candidate_adjudications": candidates,
            }
        )
    manifest = _seal(
        {
            "schema_version": ADJUDICATION_MANIFEST_SCHEMA_VERSION,
            "status": "COMPLETED_HUMAN_ADJUDICATION",
            "packet_manifest_sha256": packet_manifest["manifest_sha256"],
            "source_review_manifest_sha256": {
                cohort: reviews[cohort]["manifest"]["manifest_digest"]
                for cohort in ("reviewer_a", "reviewer_b")
            },
            "human_identity_ref": identity,
            "human_attestation": True,
            "qualification_ref": "cluster-relevance://qualified-human",
            "completed_at": "2026-08-02T23:00:00Z",
            "adjudication_record_count": 48,
            "candidate_adjudication_count": 456,
            "adjudications_file_sha256": file_sha,
        },
        "manifest_digest",
    )
    return {"manifest": manifest, "rows": rows, "observed_file_sha256": file_sha}


@pytest.fixture
def complete_inputs(monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("APPS_RG_C03_W9_AUTHORITY_HMAC_KEY", AUTHORITY_SIGNING_SECRET)
    query_manifest = _load(QUERY_MANIFEST_PATH)
    registry = _load(REGISTRY_PATH)
    w8 = _load(W8_RECEIPT_PATH)
    rankings = _complete_rankings(query_manifest, registry)
    packet = build_prelabel_packet_content(
        query_manifest=query_manifest,
        registry=registry,
        rankings=rankings,
        ranking_identity_sha256=ranking_identity_sha256(rankings),
        authority_bindings={
            "wave7_receipt_sha256": w8["source_baseline"]["wave7_receipt_sha256"],
            "query_manifest_sha256": query_manifest["query_manifest_sha256"],
            "registry_sha256": registry["registry_sha256"],
            "projection_generation_sha256": w8["source_baseline"][
                "projection_generation_sha256"
            ],
        },
        blinding_nonce="b" * 64,
        repository_root=ROOT,
    )
    packet_manifest = {"manifest_sha256": w8["controlled_packet"]["packet_manifest_sha256"]}
    identities = {
        "reviewer_a": _identity("alice"),
        "reviewer_b": _identity("ben"),
        "adjudication": _identity("casey"),
    }
    authority = _authority(w8=w8, packet_manifest=packet_manifest, identities=identities)
    source_items_sha = {"reviewer_a": "1" * 64, "reviewer_b": "2" * 64}
    reviews = {
        "reviewer_a": _review_bundle(
            cohort="reviewer_a",
            identity=identities["reviewer_a"],
            packet=packet,
            packet_manifest=packet_manifest,
            source_items_sha=source_items_sha["reviewer_a"],
            file_sha="3" * 64,
        ),
        "reviewer_b": _review_bundle(
            cohort="reviewer_b",
            identity=identities["reviewer_b"],
            packet=packet,
            packet_manifest=packet_manifest,
            source_items_sha=source_items_sha["reviewer_b"],
            file_sha="4" * 64,
        ),
    }
    adjudication = _adjudication_bundle(
        identity=identities["adjudication"],
        packet=packet,
        packet_manifest=packet_manifest,
        reviews=reviews,
        file_sha="5" * 64,
    )
    return {
        "query_manifest": query_manifest,
        "registry": registry,
        "w8": w8,
        "packet": packet,
        "packet_manifest": packet_manifest,
        "authority": authority,
        "authority_file_sha": "6" * 64,
        "source_items_sha": source_items_sha,
        "reviews": reviews,
        "adjudication": adjudication,
    }


def _validate(values: dict) -> dict:
    return validate_completed_human_inputs(
        w8_receipt=values["w8"],
        packet_manifest=values["packet_manifest"],
        packet_items=values["packet"]["cohorts"],
        sealed_mapping=values["packet"]["sealed_mapping"],
        source_review_items_sha256=values["source_items_sha"],
        authority_receipt=values["authority"],
        trusted_authority_file_sha256=values["authority_file_sha"],
        observed_authority_file_sha256=values["authority_file_sha"],
        review_bundles=values["reviews"],
        adjudication_bundle=values["adjudication"],
    )


def test_w9_contract_preserves_human_and_activation_boundaries() -> None:
    contract = _load(CONTRACT_PATH)

    validate_human_intake_contract(contract)

    assert contract["human_denominator"]["reviewer_judgment_slot_count"] == 912
    assert contract["human_denominator"]["adjudication_count"] == 456
    assert contract["machine_boundary"]["machine_labels_allowed"] is False
    assert contract["activation_boundary"]["production_promotion_authorized"] is False


def test_complete_three_human_inputs_emit_w7_compatible_qrels(
    complete_inputs: dict,
) -> None:
    report = _validate(complete_inputs)

    assert report["status"] == "PASS_HUMAN_QRELS_FROZEN"
    assert report["reviewer_judgment_count"] == 912
    assert report["adjudication_count"] == 456
    qrels = report["qrels"]
    assert qrels["judgment_count"] == 456
    assert not collect_qrel_issues(
        qrels,
        query_manifest=complete_inputs["query_manifest"],
        registry=complete_inputs["registry"],
        projection_generation_sha256=complete_inputs["w8"]["source_baseline"][
            "projection_generation_sha256"
        ],
        expected_ranking_identity_sha256=complete_inputs["w8"]["source_baseline"][
            "ranking_identity_sha256"
        ],
        expected_human_review_authority_receipt_sha256=complete_inputs[
            "authority_file_sha"
        ],
    )


def test_partial_review_never_freezes_qrels(complete_inputs: dict) -> None:
    values = copy.deepcopy(complete_inputs)
    values["reviews"]["reviewer_b"]["rows"][0]["candidate_grades"].pop()

    report = _validate(values)

    assert report["status"] == "BLOCKED_HUMAN_QREL_AUTHORITY"
    assert report["qrels"] is None
    assert any("CANDIDATE_DENOMINATOR" in issue for issue in report["issues"])


def test_nonhuman_or_unpinned_authority_is_rejected(complete_inputs: dict) -> None:
    values = copy.deepcopy(complete_inputs)
    participant = values["authority"]["authorized_participants"][0]
    participant["identity_ref"] = "human-reviewer://codex-agent"
    participant["identity_hash"] = hashlib.sha256(
        participant["identity_ref"].encode()
    ).hexdigest()
    values["authority"]["receipt_digest"] = canonical_sha256(
        {key: value for key, value in values["authority"].items() if key != "receipt_digest"}
    )

    issues, _ = collect_human_authority_issues(
        values["authority"],
        w8_receipt=values["w8"],
        packet_manifest=values["packet_manifest"],
        trusted_file_sha256="7" * 64,
        observed_file_sha256="8" * 64,
    )

    assert "AUTHORITY_EXTERNAL_FILE_PIN" in issues
    assert any(issue.startswith("AUTHORITY_NON_HUMAN") for issue in issues)


def test_authority_signature_cannot_be_replaced_with_a_self_consistent_digest(
    complete_inputs: dict,
) -> None:
    values = copy.deepcopy(complete_inputs)
    values["authority"]["authorized_participants"][0]["identity_ref"] = (
        "human-reviewer://forged-reviewer"
    )
    values["authority"]["authorized_participants"][0]["identity_hash"] = hashlib.sha256(
        b"human-reviewer://forged-reviewer"
    ).hexdigest()
    values["authority"]["receipt_digest"] = canonical_sha256(
        {key: value for key, value in values["authority"].items() if key != "receipt_digest"}
    )

    issues, _ = collect_human_authority_issues(
        values["authority"],
        w8_receipt=values["w8"],
        packet_manifest=values["packet_manifest"],
        trusted_file_sha256=values["authority_file_sha"],
        observed_file_sha256=values["authority_file_sha"],
    )

    assert "AUTHORITY_EXTERNAL_SIGNATURE_INVALID" in issues


def test_authority_requires_owner_held_signing_key(
    complete_inputs: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APPS_RG_C03_W9_AUTHORITY_HMAC_KEY")

    issues, _ = collect_human_authority_issues(
        complete_inputs["authority"],
        w8_receipt=complete_inputs["w8"],
        packet_manifest=complete_inputs["packet_manifest"],
        trusted_file_sha256=complete_inputs["authority_file_sha"],
        observed_file_sha256=complete_inputs["authority_file_sha"],
    )

    assert "AUTHORITY_EXTERNAL_SIGNING_KEY_UNAVAILABLE" in issues


def test_w9_blocked_receipt_is_readiness_not_human_evidence() -> None:
    contract = _load(CONTRACT_PATH)
    w8 = _load(W8_RECEIPT_PATH)
    receipt = build_w9_blocked_receipt(
        contract=contract,
        w8_receipt=w8,
        packet_manifest={
            "manifest_sha256": w8["controlled_packet"]["packet_manifest_sha256"]
        },
        source_commit="a" * 40,
        source_tree="b" * 40,
    )

    validate_w9_receipt(receipt)

    assert receipt["status"] == "BLOCKED_HUMAN_REVIEW_INPUTS"
    assert receipt["intake_readiness"]["observed_reviewer_judgment_slots"] == 0
    assert receipt["scope"]["human_qrels_frozen"] is False
    assert receipt["scope"]["production_promotion_authorized"] is False


def test_committed_w9_receipt_remains_non_authorizing() -> None:
    if not (ROOT / W9_RECEIPT_PATH).is_file():
        pytest.skip("W9 readiness receipt is generated after implementation tests")
    receipt = _load(W9_RECEIPT_PATH)

    validate_w9_receipt(receipt)

    assert receipt["intake_readiness"]["observed_adjudications"] == 0
    assert receipt["wave_exit_gates"]["production_promotion"] == "NOT_AUTHORIZED"
