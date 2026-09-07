from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.receipt_catalog import (
    CATALOG_VERSION,
    REQUIRED_RECEIPT_KINDS,
    build_qualification_summary,
    file_sha256,
    main,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "receipt_catalog.v1.schema.json"
PINS = {
    "input_digest": "sha256:input",
    "runtime_configuration_digest": "sha256:runtime",
    "data_split": "holdout",
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _authoritative_entry(
    root: Path,
    kind: str,
    *,
    status: str = "PASS",
    runtime_configuration_digest: str = "sha256:runtime",
) -> dict[str, object]:
    source = root / f"{kind}.json"
    _write_json(
        source,
        {
            "schema_version": "fixture.authoritative_receipt.v1",
            "status": status,
            "authority": {
                "technical_validation": True,
                "human_qualified": True,
                "release_authorized": False,
                "production_authorized": False,
            },
        },
    )
    return {
        "entry_id": f"entry-{kind}",
        "receipt_kind": kind,
        "path": source.name,
        "expected_file_sha256": file_sha256(source),
        "expected_schema_version": "fixture.authoritative_receipt.v1",
        "input_digest": PINS["input_digest"],
        "evaluator_version": f"fixture.{kind}.v1",
        "data_split": PINS["data_split"],
        "runtime_configuration_digest": runtime_configuration_digest,
        "authority_tier": "human_qualified",
    }


def _catalog(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": CATALOG_VERSION,
        "catalog_id": "fixture-catalog",
        "required_receipt_kinds": list(REQUIRED_RECEIPT_KINDS),
        "minimum_authority_tier": "human_qualified",
        "entries": entries,
    }


def _write_catalog(root: Path, entries: list[dict[str, object]]) -> Path:
    path = root / "catalog.json"
    _write_json(path, _catalog(entries))
    return path


def test_catalog_schema_is_valid() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_tracked_empty_catalog_is_explicitly_not_measured() -> None:
    summary = build_qualification_summary()

    assert summary["status"] == "NOT_MEASURED"
    assert summary["authority"]["release_authorizing"] is False
    assert summary["authority"]["apps_eval_role"] == "regression_diagnostic_only"
    assert summary["not_measured_reasons"] == sorted(
        f"AUTHORITATIVE_RECEIPT_MISSING_{kind}" for kind in REQUIRED_RECEIPT_KINDS
    )


def test_green_apps_eval_regression_cannot_replace_human_or_holdout_evidence(
    tmp_path: Path,
) -> None:
    regression = tmp_path / "regression.json"
    _write_json(
        regression,
        {
            "schema_version": "apps_eval.completed_eval.v3",
            "scorecard": {"verdict": "pass"},
            "regression": {"verdict": "pass"},
        },
    )
    catalog = _write_catalog(
        tmp_path,
        [
            {
                "entry_id": "apps-eval-green",
                "receipt_kind": "apps_eval_regression",
                "path": regression.name,
                "expected_file_sha256": file_sha256(regression),
                "expected_schema_version": "apps_eval.completed_eval.v3",
                "input_digest": PINS["input_digest"],
                "evaluator_version": "apps_eval.graders.deterministic.v2",
                "data_split": "holdout",
                "runtime_configuration_digest": PINS["runtime_configuration_digest"],
                "authority_tier": "regression_diagnostic",
            }
        ],
    )

    summary = build_qualification_summary(catalog)

    assert summary["status"] == "NOT_MEASURED"
    assert summary["regression_diagnostics"] == [
        {
            "entry_id": "apps-eval-green",
            "receipt_kind": "apps_eval_regression",
            "input_digest": PINS["input_digest"],
            "evaluator_version": "apps_eval.graders.deterministic.v2",
            "data_split": "holdout",
            "runtime_configuration_digest": PINS["runtime_configuration_digest"],
            "authority_tier": "regression_diagnostic",
            "status": "PASS",
            "reasons": [],
        }
    ]
    assert summary["authority"]["release_authorizing"] is False


def test_complete_compatible_authoritative_set_can_only_report_qualification(
    tmp_path: Path,
) -> None:
    catalog = _write_catalog(
        tmp_path,
        [_authoritative_entry(tmp_path, kind) for kind in REQUIRED_RECEIPT_KINDS],
    )

    summary = build_qualification_summary(catalog)

    assert summary["status"] == "PASS"
    assert summary["blocking_reasons"] == []
    assert summary["authority"] == {
        "minimum_receipt_tier": "human_qualified",
        "release_authorizing": False,
        "production_authorizing": False,
        "apps_eval_role": "regression_diagnostic_only",
    }


def test_duplicate_stale_and_incompatible_receipts_are_blocked(tmp_path: Path) -> None:
    entries = [_authoritative_entry(tmp_path, kind) for kind in REQUIRED_RECEIPT_KINDS]
    entries.append(dict(entries[0], entry_id="duplicate-g1"))
    duplicate_summary = build_qualification_summary(_write_catalog(tmp_path, entries))
    assert duplicate_summary["status"] == "BLOCKED"
    assert "AUTHORITATIVE_RECEIPT_DUPLICATE" in duplicate_summary["blocking_reasons"]

    stale_entries = [_authoritative_entry(tmp_path, kind) for kind in REQUIRED_RECEIPT_KINDS]
    stale_path = tmp_path / "G1.json"
    _write_json(stale_path, {"schema_version": "fixture.authoritative_receipt.v1", "status": "FAIL"})
    stale_summary = build_qualification_summary(_write_catalog(tmp_path, stale_entries))
    assert stale_summary["status"] == "BLOCKED"
    assert "RECEIPT_FILE_STALE_OR_TAMPERED" in stale_summary["blocking_reasons"]

    incompatible_entries = [_authoritative_entry(tmp_path, kind) for kind in REQUIRED_RECEIPT_KINDS]
    incompatible_entries[-1] = _authoritative_entry(
        tmp_path,
        REQUIRED_RECEIPT_KINDS[-1],
        runtime_configuration_digest="sha256:other-runtime",
    )
    incompatible_summary = build_qualification_summary(
        _write_catalog(tmp_path, incompatible_entries)
    )
    assert incompatible_summary["status"] == "BLOCKED"
    assert "AUTHORITATIVE_RECEIPT_SCOPE_INCOMPATIBLE" in incompatible_summary[
        "blocking_reasons"
    ]


def test_catalog_cannot_relabel_a_technical_p1_or_p2_receipt_as_human_qualified(
    tmp_path: Path,
) -> None:
    entries = [_authoritative_entry(tmp_path, kind) for kind in REQUIRED_RECEIPT_KINDS]
    p1_entry = next(entry for entry in entries if entry["receipt_kind"] == "P1")
    source = tmp_path / "P1.json"
    _write_json(
        source,
        {
            "schema_version": "fixture.authoritative_receipt.v1",
            "status": "PASS",
            "authority": {
                "technical_validation": True,
                "human_qualified": False,
                "release_authorized": False,
                "production_authorized": False,
            },
        },
    )
    p1_entry["expected_file_sha256"] = file_sha256(source)
    catalog = _write_catalog(tmp_path, entries)

    summary = build_qualification_summary(catalog)

    assert summary["status"] == "BLOCKED"
    assert "RECEIPT_PAYLOAD_AUTHORITY_INSUFFICIENT" in summary[
        "blocking_reasons"
    ]


def test_catalog_cli_is_fail_closed_for_the_tracked_incomplete_catalog(capsys) -> None:
    assert main([]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "NOT_MEASURED"
