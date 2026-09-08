from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.material_claim_authority import (
    INVENTORY_VERSION,
    extract_material_spans,
    build_w3_authority_summary,
    reconcile_material_claim_inventory,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "material_claim_inventory.v1.schema.json"
OUTPUT = "Led Acme analytics. Improved revenue by 20%."


def _inventory(*, omit_last: bool = False) -> dict[str, object]:
    spans = extract_material_spans(OUTPUT)
    claims = [
        {
            "claim_id": f"claim-{index}",
            "claim_text": span.text,
            "output_start": span.start,
            "output_end": span.end,
            "materiality": "MATERIAL",
            "source_id": f"source-{index}",
            "source_excerpt_digest": f"sha256:excerpt-{index}",
            "graph_path_id": f"graph-path-{index}",
        }
        for index, span in enumerate(spans, start=1)
    ]
    if omit_last:
        claims.pop()
    return {
        "schema_version": INVENTORY_VERSION,
        "output_text": OUTPUT,
        "claims": claims,
    }


def _write_manifest(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_independent_extractor_uses_all_rendered_sentences_as_material_candidates() -> None:
    spans = extract_material_spans(OUTPUT)

    assert [(span.text, span.start, span.end) for span in spans] == [
        ("Led Acme analytics.", 0, 19),
        ("Improved revenue by 20%.", 20, 44),
    ]


def test_complete_inventory_reconciles_all_material_spans() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_inventory())

    result = reconcile_material_claim_inventory(_inventory())

    assert result["status"] == "PASS"
    assert result["material_span_count"] == 2
    assert result["system_claim_count"] == 2
    assert [row["status"] for row in result["reconciled_spans"]] == [
        "RECONCILED",
        "RECONCILED",
    ]
    assert result["authority"]["release_authorizing"] is False


def test_omitted_or_unbound_claims_fail_closed() -> None:
    omitted = reconcile_material_claim_inventory(_inventory(omit_last=True))
    assert omitted["status"] == "FAIL"
    assert "MATERIAL_SPAN_UNINVENTORIED" in omitted["failure_codes"]

    unbound = _inventory()
    claims = unbound["claims"]
    assert isinstance(claims, list)
    claims[0]["graph_path_id"] = ""
    result = reconcile_material_claim_inventory(unbound)
    assert result["status"] == "FAIL"
    assert "CLAIM_EVIDENCE_BINDING_INCOMPLETE" in result["failure_codes"]


def test_w3_default_is_not_measured_and_synthetic_grades_are_blocked(
    tmp_path: Path,
) -> None:
    default = build_w3_authority_summary()
    assert default["status"] == "NOT_MEASURED"
    assert default["human_truth"] == {"qrel": "UNKNOWN", "proof": "UNKNOWN"}
    assert "QREL_HUMAN_REVIEWS_PENDING" in default["not_measured_reasons"]
    assert default["authority"]["human_qualified"] is False

    invalid_manifest = {
        "schema_version": "apps_rg.w3_human_truth_manifest.v1",
        "manifest_id": "synthetic-forbidden",
        "qrel_review": {
            "status": "PENDING",
            "required_primary_reviews_per_item": 2,
            "required_adjudications_per_item": 1,
            "observed_primary_reviews": 0,
            "observed_adjudications": 0,
            "external_authority_receipt_sha256": "",
            "completed_receipt_digest": "",
            "synthetic_grades_created": True,
        },
        "proof_review": {
            "status": "PENDING",
            "required_primary_reviews_per_item": 2,
            "required_adjudications_per_item": 1,
            "observed_primary_reviews": 0,
            "observed_adjudications": 0,
            "external_authority_receipt_sha256": "",
            "completed_receipt_digest": "",
            "synthetic_grades_created": False,
        },
    }
    path = tmp_path / "synthetic.json"
    _write_manifest(path, invalid_manifest)
    result = build_w3_authority_summary(path, _inventory())
    assert result["status"] == "BLOCKED"
    assert "QREL_SYNTHETIC_GRADES_FORBIDDEN" in result["blocking_reasons"]
