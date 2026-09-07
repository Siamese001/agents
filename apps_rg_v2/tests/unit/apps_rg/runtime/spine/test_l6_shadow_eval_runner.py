from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.spine.l6_shadow_eval_runner import (
    _canonical_digest,
    _emit_l6_observability_closure_receipt,
    _validate_l5_certification_receipt,
    emit_l5_certification_receipt_from_core,
)


def _paths(root: Path) -> tuple[dict[str, Path], dict[str, Path], dict[str, Path], Path]:
    trace = {
        "trace_reconciliation": root / "trace_reconciliation.json",
        "trace_reconciliation_rows": root / "trace_reconciliation_rows.jsonl",
        "l6_trace_observability_summary": root / "l6_trace_observability_summary.json",
    }
    micro = {
        "l6_microstep_observations": root / "l6_microstep_observations.jsonl",
        "l6_microstep_coverage": root / "l6_microstep_coverage.json",
        "l6_microstep_rca": root / "l6_microstep_rca.json",
        "l6_microstep_patterns": root / "l6_microstep_patterns.json",
        "l6_microstep_future_run_proposals": root / "l6_microstep_future_run_proposals.json",
        "l6_apps_eval_alignment": root / "l6_apps_eval_alignment.json",
        "l6_apps_eval_grain_parity": root / "l6_apps_eval_grain_parity.json",
    }
    spans = {
        "span_export_json": root / "l6_v40_shadow_eval_spans.json",
        "span_export_jsonl": root / "l6_v40_shadow_eval_spans.jsonl",
    }
    package_path = root / "l6_v40_shadow_eval_package.json"
    for path in (*trace.values(), *micro.values(), *spans.values(), package_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    (root / "runtime_exhaust_bundle.json").write_text("{}\n", encoding="utf-8")
    (root / "exit_disposition_receipt.json").write_text("{}\n", encoding="utf-8")
    return trace, micro, spans, package_path


def _package() -> dict[str, object]:
    return {
        "section_id": "headline",
        "parent_run_id": "parent-1",
        "child_run_id": "child-1",
        "section_attempt_id": "attempt-1",
        "runtime_exhaust_bundle_id": "reb-1",
        "runtime_exhaust_bundle_digest": "sha256:" + "b" * 64,
        "microstep_contract_digest": "sha256:" + "c" * 64,
        "registry_digest": "sha256:" + "c" * 64,
        "l5_certification_valid": True,
        "valid_v40_shadow_exhaust": True,
        "readiness_decision": "READY_FOR_6B",
        "g28_audit_completeness": {"verdict": "PASS"},
        "g29_learning_firewall": {"verdict": "PASS"},
        "grain_parity_status": "WARN",
        "apps_eval_rows_bound": False,
        "evidence_class": "CONTRACT_ONLY_ADVISORY",
        "current_run_mutation_assertion": False,
        "current_run_x3_mutation_assertion": False,
        "direct_l4_write_assertion": False,
        "durable_write_assertion": False,
        "future_run_only_assertion": True,
    }


def test_contract_only_section_can_close_observability(tmp_path: Path) -> None:
    trace, micro, spans, package_path = _paths(tmp_path)
    path = _emit_l6_observability_closure_receipt(
        artifact_dir=tmp_path,
        repo_root=tmp_path,
        package_path=package_path,
        package=_package(),
        trace_reconciliation_paths=trace,
        microstep_paths=micro,
        span_paths=spans,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["observability_closure_status"] == "PASS"
    assert payload["eval_binding_status"] == "PENDING"
    assert payload["failed_checks"] == []
    assert payload["artifact_digests"]
    assert payload["registry_digest"] == payload["microstep_contract_digest"]
    assert payload["runtime_exhaust_bundle_digest"].startswith("sha256:")


def test_observability_closure_fails_on_gate_or_artifact_gap(tmp_path: Path) -> None:
    trace, micro, spans, package_path = _paths(tmp_path)
    micro["l6_microstep_rca"].unlink()
    package = _package()
    package["g29_learning_firewall"] = {"verdict": "FAIL"}
    path = _emit_l6_observability_closure_receipt(
        artifact_dir=tmp_path,
        repo_root=tmp_path,
        package_path=package_path,
        package=package,
        trace_reconciliation_paths=trace,
        microstep_paths=micro,
        span_paths=spans,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["observability_closure_status"] == "FAIL"
    assert "g29_pass" in payload["failed_checks"]
    assert "l6_microstep_rca_exists" in payload["failed_checks"]


def test_deferred_l5_projection_is_digest_bound_to_core_and_lane(tmp_path: Path) -> None:
    native = {
        "run_id": "lane-run",
        "parent_run_id": "product-run",
        "child_run_id": "lane-run",
        "section_attempt_id": "headline:lane-run:attempt:1",
        "tenant_id": "tenant-1",
    }
    (tmp_path / "apps_rg_section_runtime_exhaust_bundle.json").write_text(
        json.dumps(native), encoding="utf-8"
    )
    core = {
        "run_id": "core-run",
        "cert_status": "certified",
        "certification_status": "L5_CERTIFIED",
    }
    (tmp_path / "runtime_certification_binding.json").write_text(
        json.dumps({"artifact_hash": _canonical_digest(core), "payload": core}),
        encoding="utf-8",
    )
    (tmp_path / "product_certification_receipt.json").write_text(
        json.dumps(
            {
                "run_id": "lane-run",
                "product_certification": "ONE_SPINE_SECTION_CERTIFIED",
                "required_chain_complete": True,
                "proof_eligible": True,
            }
        ),
        encoding="utf-8",
    )

    receipt_path = emit_l5_certification_receipt_from_core(
        artifact_dir=tmp_path,
        repo_root=tmp_path,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    valid, gaps, ref, digest = _validate_l5_certification_receipt(
        artifact_dir=tmp_path,
        repo_root=tmp_path,
        ref=receipt_path.name,
        raw_exhaust=native,
    )

    assert valid is True
    assert gaps == []
    assert ref == receipt_path.name
    assert digest == receipt["receipt_digest"]
