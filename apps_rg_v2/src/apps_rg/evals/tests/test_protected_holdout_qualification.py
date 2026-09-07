from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.protected_holdout_qualification import (
    ABLATIONS,
    DIAGNOSTICS,
    MANIFEST_VERSION,
    PRIMARY_OUTCOMES,
    ZERO_GUARDRAILS,
    canonical_digest,
    validate_protected_holdout_qualification,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]


def _complete(root: Path) -> dict[str, object]:
    metric, data = root / "metric.py", root / "data.json"
    metric.write_text("metric", encoding="utf-8")
    data.write_text("data", encoding="utf-8")
    scope: dict[str, object] = {
        "source_commit": "source-commit", "preregistered_at": "2026-08-01T00:00:00Z", "holdout_accessed_at": "2026-08-02T00:00:00Z",
        "provider_model_pins_digest": "sha256:pins", "baseline_config_digest": "sha256:baseline", "candidate_config_digest": "sha256:candidate", "decision_rules_digest": "sha256:rules", "holdout_index_digest": "sha256:holdout",
        "scope_files": [{"path": "metric.py", "sha256": hashlib.sha256(metric.read_bytes()).hexdigest()}, {"path": "data.json", "sha256": hashlib.sha256(data.read_bytes()).hexdigest()}],
    }
    scope["preregistration_digest"] = canonical_digest(scope)
    return {
        "schema_version": MANIFEST_VERSION, "qualification_id": "w7-test", "status": "COMPLETE", "frozen_scope": scope,
        "results": {
            "upstream_receipts": {name: f"sha256:{name}" for name in (*PRIMARY_OUTCOMES, *DIAGNOSTICS, "guardrails")}, "synthetic_human_labels_created": False, "holdout_evaluation_count": 1,
            "primary_outcomes": {name: {"estimate": 0.2, "ci_lower": 0.1, "threshold": 0.0, "status": "PASS"} for name in PRIMARY_OUTCOMES},
            "diagnostics": {name: "PASS" for name in DIAGNOSTICS}, "ablations": {name: {"design": "PAIRED_RANDOMIZED", "status": "PASS"} for name in ABLATIONS},
            "guardrails": {name: 0 for name in ZERO_GUARDRAILS}, "slices": [{"slice_id": "protected-risk", "status": "PASS"}],
        },
    }


def _write(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_schema_and_default_pending_receipt_are_not_measured() -> None:
    schema = json.loads((EVALS_ROOT / "schemas" / "protected_holdout_qualification.v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(json.loads((EVALS_ROOT / "protected_holdout_qualification.v1.json").read_text(encoding="utf-8")))
    result = validate_protected_holdout_qualification()
    assert result["status"] == "NOT_MEASURED"
    assert result["authority"]["production_authorizing"] is False


def test_complete_bound_scope_passes_but_never_authorizes_release(tmp_path: Path) -> None:
    manifest = _complete(tmp_path)
    path = tmp_path / "receipt.json"
    _write(path, manifest)
    result = validate_protected_holdout_qualification(path, repo_root=tmp_path, observed_source_commit="source-commit")
    assert result["status"] == "PASS"
    assert result["authority"]["release_authorizing"] is False


def test_changed_scope_is_explicitly_stale_and_late_preregistration_blocks(tmp_path: Path) -> None:
    manifest = _complete(tmp_path)
    path = tmp_path / "receipt.json"
    _write(path, manifest)
    (tmp_path / "metric.py").write_text("changed", encoding="utf-8")
    stale = validate_protected_holdout_qualification(path, repo_root=tmp_path, observed_source_commit="source-commit")
    assert stale["status"] == "STALE_SCOPE"
    assert "P7_SCOPE_FILE_DIGEST_MISMATCH" in stale["stale_scope_reasons"]

    late_root = tmp_path / "late"
    late_root.mkdir()
    late = _complete(late_root)
    scope = late["frozen_scope"]
    assert isinstance(scope, dict)
    scope["preregistered_at"] = "2026-08-03T00:00:00Z"
    scope["preregistration_digest"] = canonical_digest({key: value for key, value in scope.items() if key != "preregistration_digest"})
    late_path = late_root / "late.json"
    _write(late_path, late)
    blocked = validate_protected_holdout_qualification(late_path, repo_root=late_root, observed_source_commit="source-commit")
    assert blocked["status"] == "BLOCKED"
    assert "P7_PREREGISTRATION_DOES_NOT_PREDATE_HOLDOUT" in blocked["blocking_reasons"]
